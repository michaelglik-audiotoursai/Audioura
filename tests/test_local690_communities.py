"""
LOCAL-690 — Communities phase 1 server tests (D657 / D658 + addenda).

One test per rule in the ticket. DB-backed tests use the shared test database
(audiotours_test on localhost:5433) via an in-process Flask client mounting the
communities + entitlements blueprints. RSS parsing is tested with a MOCK HTTP
getter — no real network request is ever made.

Rules covered:
  * create: owner/name required; waiver community forced Private; Listed needs a
    location; paid community needs ≥1 pass; a unique 8-char code with a digit.
  * invite code resolves to the community page (join flow); a non-member sees
    the "This tour belongs to <Community>. Join to listen" framing; a disabled
    community resolves to 404.
  * free join works for a free community; a paid community refuses a free join.
  * pass purchase (stub): grants a membership with expiry = now + duration_days;
    idempotent on transaction_id; buying again EXTENDS/REPLACES the expiry
    (nothing renews); a pass not offered is refused; a disabled community is
    refused.
  * expiry blocks NEW content: an EXPIRED member cannot list episodes (403); an
    ACTIVE member can; the OWNER always can. (Downloaded audio is the device's —
    the server never serves/deletes it, so there is nothing to "lock" here.)
  * episodes: owner adds MP3 links (no content check); a feed import parses one
    RSS URL into episode metadata (title, order, URL) with a MOCK getter; a
    re-import upserts on guid, not duplicates.
  * reminders: one 3-days-before reminder and one at-expiry reminder, each once.
  * map: only Listed+located+not-disabled communities appear; Private never.
  * report: writes a row and returns the owner_user_id (report → owner).

Safety: every row uses an owner/user id or community name starting with
'TEST-690-'. Cleanup deletes ONLY rows reachable from communities whose name has
that exact prefix, plus purchases with that transaction prefix. No other table
is touched.
"""

import os
import sys
import importlib.util
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-690-"


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    """[LOCAL-693B] Own this module's entitlements env and restore it afterwards.
    Other modules (595/604/596) set GATEWAY_API_KEY / IAP_VERIFY_MODE at import
    and never restore them; with those set, our fresh entitlements import would
    require an X-API-Key and 401 our calls. Force the vars we need, then restore
    exactly what was there so we poison no one else."""
    keys = ("GATEWAY_API_KEY", "IAP_VERIFY_MODE", "ALLOW_UNAUTHENTICATED_ENTITLEMENTS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["GATEWAY_API_KEY"] = ""
    os.environ["IAP_VERIFY_MODE"] = "stub"
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _load_module(name, rel_path):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def modules(_isolate_entitlements_env):
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    rss = _load_module("communities_rss", "user-tracking/communities_rss.py")
    ca = _load_module("communities_api", "user-tracking/communities_api.py")
    ea = _load_module("entitlements_api_690", "user-tracking/entitlements_api.py")
    # [LOCAL-693B] Pin the import-time-cached auth/verify knobs to this module's
    # intent so a stale import order cannot leave auth required or 'apple' mode.
    ea.API_KEY = ""
    ea.IAP_VERIFY_MODE = "stub"
    return {"rss": rss, "ca": ca, "ea": ea}


@pytest.fixture(scope="module")
def client(modules):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(modules["ca"].communities_bp)
    app.register_blueprint(modules["ea"].entitlements_bp)
    app.testing = True
    return app.test_client()


@pytest.fixture
def db():
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(db):
    cur = db.cursor()
    # Find TEST communities and delete their dependent rows, then themselves.
    cur.execute("SELECT id FROM communities WHERE name LIKE %s", (TEST_PREFIX + '%',))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        for tbl in ("community_reports", "community_episodes", "community_passes",
                    "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    # [LOCAL-700] The plan gate reads device_entitlement.level; our _create
    # seeds TEST owners at l2 so creation is allowed. Clean those rows too.
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _seed_owner_level(owner_user_id, level='l2'):
    """[LOCAL-700] Give an owner a plan so the create gate (free plan or above)
    lets them through. The gate reads device_entitlement.level; a brand-new TEST
    owner has no row (→ l1 Introduction → 403), so seed l2 (Free) by default."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
            "VALUES (%s, %s, NOW()) "
            "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level",
            (owner_user_id, level),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _create(client, **overrides):
    owner = overrides.pop("owner_user_id", TEST_PREFIX + "owner")
    # [LOCAL-700] Ensure the owner is on the free plan or above so create passes
    # the plan gate (the gate itself is tested separately in test_local700).
    _seed_owner_level(owner)
    body = {
        "owner_user_id": owner,
        "name": overrides.pop("name", TEST_PREFIX + "Book Club"),
    }
    body.update(overrides)
    return client.post("/communities", json=body)


# ─── RSS parsing (pure + mock HTTP) ────────────────────────────────────────────

RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Owner Feed</title>
    <item>
      <title>Episode One</title>
      <guid>guid-1</guid>
      <enclosure url="https://owner.example/ep1.mp3" type="audio/mpeg" length="123"/>
    </item>
    <item>
      <title>Episode Two</title>
      <guid>guid-2</guid>
      <enclosure url="https://owner.example/ep2.mp3" type="audio/mpeg" length="456"/>
    </item>
    <item>
      <title>No Audio Item</title>
      <guid>guid-3</guid>
    </item>
  </channel>
</rss>"""


def test_rss_parse_metadata_only_order_and_url(modules):
    eps = modules["rss"].parse_feed(RSS_FIXTURE)
    # The audio-less item is skipped; two episodes in feed order.
    assert len(eps) == 2
    assert eps[0]["position"] == 1 and eps[0]["title"] == "Episode One"
    assert eps[0]["audio_url"] == "https://owner.example/ep1.mp3"
    assert eps[0]["guid"] == "guid-1"
    assert eps[1]["position"] == 2 and eps[1]["title"] == "Episode Two"


def test_rss_fetch_and_parse_uses_injected_getter(modules):
    calls = {}

    def fake_get(url, timeout=10):
        calls["url"] = url
        return RSS_FIXTURE

    eps = modules["rss"].fetch_and_parse("https://owner.example/feed.xml", http_get=fake_get)
    assert calls["url"] == "https://owner.example/feed.xml"  # no real network
    assert len(eps) == 2


def test_rss_bad_body_raises(modules):
    with pytest.raises(modules["rss"].FeedParseError):
        modules["rss"].parse_feed("not xml at all <<<")


# ─── create rules ──────────────────────────────────────────────────────────────

def test_create_requires_owner_and_name(client):
    r = client.post("/communities", json={"owner_user_id": TEST_PREFIX + "o"})
    assert r.status_code == 400


def test_create_waiver_forces_private(client):
    r = _create(client, name=TEST_PREFIX + "Waiver", waiver_text="Sign here",
                visibility="listed", latitude=1.0, longitude=2.0)
    assert r.status_code == 201
    j = r.get_json()
    # A waiver community is ALWAYS Private even when 'listed' was requested.
    assert j["has_waiver"] is True
    assert j["visibility"] == "private"


def test_create_listed_needs_location(client):
    r = _create(client, name=TEST_PREFIX + "Listed", visibility="listed")
    assert r.status_code == 400
    assert r.get_json()["error"] == "listed_needs_location"


def test_create_paid_needs_passes(client):
    r = _create(client, name=TEST_PREFIX + "Paid", is_paid=True)
    assert r.status_code == 400
    assert r.get_json()["error"] == "paid_needs_passes"


def test_create_generates_unique_code_with_digit(client, modules):
    r = _create(client, name=TEST_PREFIX + "Coded")
    assert r.status_code == 201
    code = r.get_json()["join_code"]
    assert len(code) == 8
    assert any(c.isdigit() for c in code)  # recognised by isShareCodeShape
    assert "invite_message" in r.get_json()
    assert code in r.get_json()["invite_message"]


# ─── invite code / join flow ────────────────────────────────────────────────────

def test_resolve_by_code_shows_join_framing_for_non_member(client):
    r = _create(client, name=TEST_PREFIX + "Joinable")
    code = r.get_json()["join_code"]
    stranger = TEST_PREFIX + "stranger"
    r2 = client.get(f"/communities/by-code/{code}?user_id={stranger}")
    assert r2.status_code == 200
    j = r2.get_json()
    assert j["join_message"] == f'This tour belongs to {j["name"]}. Join to listen.'
    assert j["my_status"]["is_member"] is False


def test_resolve_disabled_community_404(client, db):
    r = _create(client, name=TEST_PREFIX + "Disabled")
    cid = r.get_json()["id"]
    code = r.get_json()["join_code"]
    cur = db.cursor()
    cur.execute("UPDATE communities SET disabled = TRUE WHERE id = %s", (cid,))
    db.commit()
    cur.close()
    r2 = client.get(f"/communities/by-code/{code}")
    assert r2.status_code == 404


def test_free_join_and_paid_refuses_free_join(client):
    free = _create(client, name=TEST_PREFIX + "Free").get_json()
    member = TEST_PREFIX + "freemember"
    r = client.post(f"/communities/{free['id']}/join", json={"user_id": member})
    assert r.status_code == 200
    assert r.get_json()["my_status"]["active"] is True

    paid = _create(client, name=TEST_PREFIX + "PaidC", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    r2 = client.post(f"/communities/{paid['id']}/join", json={"user_id": member})
    assert r2.status_code == 402


# ─── pass purchase + expiry (the non-renewing model) ────────────────────────────

def test_pass_purchase_grants_membership_with_expiry(client, db, modules):
    paid = _create(client, name=TEST_PREFIX + "PaidPass", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    buyer = TEST_PREFIX + "buyer1"
    body = {"store": "stub", "transaction_id": TEST_PREFIX + "txn1",
            "product": "audioura.pass.usd5", "length": "month", "user_id": buyer,
            "community_id": paid["id"]}
    r = client.post("/purchases/verify", json=body)
    assert r.status_code == 200
    j = r.get_json()
    assert j["verified"] is True
    assert j["membership"]["duration_days"] == 30
    assert j["membership"]["length"] == "month"
    # expiry ≈ now + 30 days
    exp = datetime.fromisoformat(j["membership"]["expires_at"])
    assert timedelta(days=29) < (exp - datetime.utcnow()) < timedelta(days=31)


def test_pass_purchase_idempotent(client):
    paid = _create(client, name=TEST_PREFIX + "Idem", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "day"}]).get_json()
    body = {"store": "stub", "transaction_id": TEST_PREFIX + "txn-idem",
            "product": "audioura.pass.usd5", "length": "day", "user_id": TEST_PREFIX + "b2",
            "community_id": paid["id"]}
    r1 = client.post("/purchases/verify", json=body)
    assert r1.status_code == 200
    r2 = client.post("/purchases/verify", json=body)
    assert r2.status_code == 409  # already_verified, no second extension


def test_buying_again_extends_expiry(client, db):
    paid = _create(client, name=TEST_PREFIX + "Renew", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "day"},
                                  {"product_id": "audioura.pass.usd5", "length": "year"}]).get_json()
    buyer = TEST_PREFIX + "renewer"
    # First a 1-day pass (same store product, length=day).
    client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "r-day",
        "product": "audioura.pass.usd5", "length": "day", "user_id": buyer,
        "community_id": paid["id"]})
    cur = db.cursor()
    cur.execute("SELECT expires_at FROM community_memberships WHERE user_id=%s AND community_id=%s",
                (buyer, paid["id"]))
    exp1 = cur.fetchone()[0]
    # Buy again — a 1-year pass (SAME product, length=year). ONE row, a FRESH
    # (later) expiry.
    client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "r-year",
        "product": "audioura.pass.usd5", "length": "year", "user_id": buyer,
        "community_id": paid["id"]})
    cur.execute("SELECT COUNT(*), MAX(expires_at) FROM community_memberships WHERE user_id=%s AND community_id=%s",
                (buyer, paid["id"]))
    n, exp2 = cur.fetchone()
    cur.close()
    assert n == 1              # one row — nothing stacks
    assert exp2 > exp1         # the new (year) expiry is later


def test_pass_not_offered_refused(client):
    # The community offers only usd5/month. A different PRICE and a different
    # LENGTH of the same price are both "not offered" (the option is the
    # (product, length) pair, LEAD review of LOCAL-690).
    paid = _create(client, name=TEST_PREFIX + "Offer", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    # A different product entirely → not offered.
    r = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "no-offer",
        "product": "audioura.pass.usd50", "length": "year",
        "user_id": TEST_PREFIX + "b3", "community_id": paid["id"]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "pass_not_offered"
    # The RIGHT product but a LENGTH the community did not offer → not offered.
    r2 = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "wrong-len",
        "product": "audioura.pass.usd5", "length": "year",
        "user_id": TEST_PREFIX + "b3", "community_id": paid["id"]})
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "pass_not_offered"


def test_one_price_product_two_communities_two_lengths(client, db):
    """[LOCAL-690C] The heart of the LEAD review: ONE store product per PRICE
    serves every community AND every length. The SAME audioura.pass.usd5 buys a
    1-DAY pass in community A and a 1-MONTH pass in community B — two
    memberships, each with the length's own expiry."""
    a = _create(client, name=TEST_PREFIX + "A-day", is_paid=True,
                pass_products=[{"product_id": "audioura.pass.usd5", "length": "day"}]).get_json()
    b = _create(client, name=TEST_PREFIX + "B-month", is_paid=True,
                pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    buyer = TEST_PREFIX + "multi-buyer"

    ra = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "m-a",
        "product": "audioura.pass.usd5", "length": "day",
        "user_id": buyer, "community_id": a["id"]})
    rb = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "m-b",
        "product": "audioura.pass.usd5", "length": "month",
        "user_id": buyer, "community_id": b["id"]})
    assert ra.status_code == 200 and rb.status_code == 200
    # Same store product, different lengths → different durations.
    assert ra.get_json()["membership"]["duration_days"] == 1
    assert rb.get_json()["membership"]["duration_days"] == 30

    # Two separate memberships, each with the right expiry window.
    cur = db.cursor()
    cur.execute("SELECT community_id, expires_at FROM community_memberships "
                "WHERE user_id=%s ORDER BY expires_at", (buyer,))
    rows = cur.fetchall()
    cur.close()
    assert len(rows) == 2
    now = datetime.utcnow()
    by_comm = {cid: exp for cid, exp in rows}
    # A ≈ now + 1 day, B ≈ now + 30 days.
    assert timedelta(hours=20) < (by_comm[a["id"]] - now) < timedelta(days=2)
    assert timedelta(days=29) < (by_comm[b["id"]] - now) < timedelta(days=31)


def test_catalogue_has_34_price_products_no_length(client, db):
    """[LOCAL-690C] The pass catalogue is the 34 ladder PRICES with NO length —
    one Apple product per price (D658 LEAD review). The length lives on the
    community option, not the catalogue."""
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_pass_products "
                "WHERE product_id LIKE 'audioura.pass.usd%' AND active = TRUE")
    assert cur.fetchone()[0] >= 34  # the 34 ladder prices (seed is exactly 34)
    # The catalogue carries NO length column (one product per price).
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'community_pass_products'")
    cols = {r[0] for r in cur.fetchall()}
    assert "length" not in cols
    assert "duration_days" not in cols
    # The LENGTH + duration_days live on the OPTION table instead.
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'community_passes'")
    opt_cols = {r[0] for r in cur.fetchall()}
    assert "length" in opt_cols
    assert "duration_days" in opt_cols
    cur.close()


# ─── expiry blocks NEW content ──────────────────────────────────────────────────

def test_expired_member_cannot_list_episodes_owner_and_active_can(client, db, modules):
    paid = _create(client, name=TEST_PREFIX + "Episodes", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    cid = paid["id"]
    owner = TEST_PREFIX + "owner"
    # Owner adds an episode (no content check).
    r = client.post(f"/communities/{cid}/episodes", json={
        "owner_user_id": owner,
        "episodes": [{"title": "Stop 1", "audio_url": "https://owner.example/s1.mp3"}]})
    assert r.status_code == 200 and r.get_json()["added"] == 1

    # Owner can always list.
    ro = client.get(f"/communities/{cid}/episodes?user_id={owner}")
    assert ro.status_code == 200 and len(ro.get_json()["episodes"]) == 1

    # Active member can list.
    member = TEST_PREFIX + "activemember"
    client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "act",
        "product": "audioura.pass.usd5", "length": "month", "user_id": member,
        "community_id": cid})
    ra = client.get(f"/communities/{cid}/episodes?user_id={member}")
    assert ra.status_code == 200

    # Force that member's membership to be EXPIRED, then they are blocked (403).
    cur = db.cursor()
    cur.execute("UPDATE community_memberships SET expires_at = %s WHERE user_id=%s AND community_id=%s",
                (datetime.utcnow() - timedelta(days=1), member, cid))
    db.commit()
    cur.close()
    rx = client.get(f"/communities/{cid}/episodes?user_id={member}")
    assert rx.status_code == 403
    assert rx.get_json()["is_member"] is True

    # A non-member is also blocked.
    rn = client.get(f"/communities/{cid}/episodes?user_id={TEST_PREFIX}nobody")
    assert rn.status_code == 403


# ─── feed import (mock HTTP) ────────────────────────────────────────────────────

def test_import_feed_parses_and_reimport_upserts(client, db, modules):
    r = _create(client, name=TEST_PREFIX + "FeedC",
                feed_url="https://owner.example/feed.xml").get_json()
    cid = r["id"]
    owner = TEST_PREFIX + "owner"

    # Inject the mock getter so no network request is made.
    modules["ca"]._feed_http_get = lambda url, timeout=10: RSS_FIXTURE

    r1 = client.post(f"/communities/{cid}/import-feed", json={"owner_user_id": owner})
    assert r1.status_code == 200
    assert r1.get_json()["imported"] == 2

    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_episodes WHERE community_id=%s", (cid,))
    assert cur.fetchone()[0] == 2

    # Re-import the SAME feed → upsert on guid, still 2 (no duplicates).
    r2 = client.post(f"/communities/{cid}/import-feed", json={"owner_user_id": owner})
    assert r2.status_code == 200
    cur.execute("SELECT COUNT(*) FROM community_episodes WHERE community_id=%s", (cid,))
    assert cur.fetchone()[0] == 2
    cur.close()
    modules["ca"]._feed_http_get = None


def test_import_feed_owner_only(client, modules):
    r = _create(client, name=TEST_PREFIX + "FeedOwner",
                feed_url="https://owner.example/feed.xml").get_json()
    modules["ca"]._feed_http_get = lambda url, timeout=10: RSS_FIXTURE
    rr = client.post(f"/communities/{r['id']}/import-feed",
                     json={"owner_user_id": TEST_PREFIX + "not-owner"})
    assert rr.status_code == 403
    modules["ca"]._feed_http_get = None


# ─── reminders (3 days before + at expiry, each once) ───────────────────────────

def test_reminders_before_and_at_expiry_each_once(client, db, modules):
    paid = _create(client, name=TEST_PREFIX + "Remind", is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}]).get_json()
    cid = paid["id"]
    # Member A: expiring in 2 days → before-reminder bucket.
    a = TEST_PREFIX + "rem-a"
    # Member B: already expired → expiry-reminder bucket.
    b = TEST_PREFIX + "rem-b"
    for u in (a, b):
        client.post("/purchases/verify", json={
            "store": "stub", "transaction_id": TEST_PREFIX + "rm-" + u[-5:],
            "product": "audioura.pass.usd5", "length": "month", "user_id": u,
            "community_id": cid})
    cur = db.cursor()
    cur.execute("UPDATE community_memberships SET expires_at=%s WHERE user_id=%s AND community_id=%s",
                (datetime.utcnow() + timedelta(days=2), a, cid))
    cur.execute("UPDATE community_memberships SET expires_at=%s WHERE user_id=%s AND community_id=%s",
                (datetime.utcnow() - timedelta(hours=1), b, cid))
    db.commit()

    res = modules["ca"].run_reminders(cur)
    db.commit()
    # A got a before-reminder; B got an expiry-reminder.
    cur.execute("SELECT id FROM community_memberships WHERE user_id=%s AND community_id=%s", (a, cid))
    a_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM community_memberships WHERE user_id=%s AND community_id=%s", (b, cid))
    b_id = cur.fetchone()[0]
    assert a_id in res["before"]
    assert b_id in res["expiry"]

    # Running again sends NEITHER again (each reminder once).
    res2 = modules["ca"].run_reminders(cur)
    db.commit()
    assert a_id not in res2["before"]
    assert b_id not in res2["expiry"]
    cur.close()


# ─── map listing + report ───────────────────────────────────────────────────────

def test_map_only_lists_listed_located_not_disabled(client, db):
    listed = _create(client, name=TEST_PREFIX + "OnMap", visibility="listed",
                     latitude=42.0, longitude=-71.0).get_json()
    _create(client, name=TEST_PREFIX + "Private")  # private, never on map
    r = client.get("/communities/map")
    assert r.status_code == 200
    names = {c["name"] for c in r.get_json()["communities"]}
    assert (TEST_PREFIX + "OnMap") in names
    assert (TEST_PREFIX + "Private") not in names
    # Every map entry carries the community badge.
    for c in r.get_json()["communities"]:
        if c["name"] == TEST_PREFIX + "OnMap":
            assert c["badge"] == "community"


def test_report_goes_to_owner(client):
    owner = TEST_PREFIX + "reportowner"
    c = _create(client, owner_user_id=owner, name=TEST_PREFIX + "Reported").get_json()
    r = client.post(f"/communities/{c['id']}/report",
                    json={"user_id": TEST_PREFIX + "reporter", "reason": "spam"})
    assert r.status_code == 200
    assert r.get_json()["owner_user_id"] == owner


def test_mine_lists_origin_for_member(client):
    free = _create(client, name=TEST_PREFIX + "MineC").get_json()
    member = TEST_PREFIX + "mine-member"
    client.post(f"/communities/{free['id']}/join", json={"user_id": member})
    r = client.get(f"/communities/mine?user_id={member}")
    assert r.status_code == 200
    comms = r.get_json()["communities"]
    assert any(c["name"] == TEST_PREFIX + "MineC" and c["origin"] == "community"
               for c in comms)


# ─── pure helpers ────────────────────────────────────────────────────────────────

def test_compute_expiry_and_active(modules):
    ca = modules["ca"]
    now = datetime(2026, 1, 1, 12, 0, 0)
    assert ca.compute_expiry(now, 30) == now + timedelta(days=30)
    assert ca.is_membership_active(None) is True            # free never expires
    assert ca.is_membership_active(now + timedelta(days=1), now) is True
    assert ca.is_membership_active(now - timedelta(days=1), now) is False


def test_is_community_pass_product(modules):
    ca = modules["ca"]
    # One product per PRICE now (no length suffix) — still recognised by prefix.
    assert ca.is_community_pass_product("audioura.pass.usd5") is True
    assert ca.is_community_pass_product("audioura.pass.usd200") is True
    assert ca.is_community_pass_product("audioura.tour.tier3") is False
    assert ca.is_community_pass_product("l3_pack_10") is False
    assert ca.is_community_pass_product(None) is False


def test_duration_days_for_length_and_label(modules):
    ca = modules["ca"]
    assert ca.duration_days_for_length("day") == 1
    assert ca.duration_days_for_length("week") == 7
    assert ca.duration_days_for_length("month") == 30
    assert ca.duration_days_for_length("year") == 365
    assert ca.duration_days_for_length("decade") is None
    # The page label composes the catalogue PRICE label with the option length.
    assert ca.pass_label_for("$5", "month") == "$5 / month"
