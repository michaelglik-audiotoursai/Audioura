"""
test_local704_dollar_minimum_and_member_count.py — LOCAL-704 / D665 + D666.

Every community member pays at least $1 to join; every community shows its
member count; the organiser is never a member; and after launch a community
that drops below 2 active members is warned weekly and archived only after a
full week at 0 active members.

Covered (every spec case in the task):

  * pass_required on create       — a create with no pass option → 400.
  * pass_required on free join     — the free-join endpoint → 402 for any
                                    community.
  * $1 product verifies + grants   — audioura.pass.usd1 (stub) grants membership.
  * member_count excludes owner    — the owner never counts; expired members
                                    never count.
  * owner join/buy → 409           — owner_cannot_join on both paths.
  * owner plays without a pass      — the owner sees episodes with no membership.
  * demo book club migration       — a free community + its free member is
                                    converted to $1/month and the member is
                                    grandfathered 30 days.
  * post-launch drop to 1          — warnings on day 0, day 7, day 14 (not
                                    daily); back to 2 → warnings stop.
  * 0 members 6 days → still active; 7 days → archived (no_members).
  * 1 member for 30 days → never archived.

DB-backed, in-process Flask client (communities + entitlements blueprints), stub
IAP mode — the SAME harness as test_local703_launch_window.py. Every row uses the
'TEST-704-' prefix; cleanup touches only those rows.
"""

import os
import sys
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-704-"


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
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
    _load_module("communities_rss", "user-tracking/communities_rss.py")
    ca = _load_module("communities_api", "user-tracking/communities_api.py")
    ea = _load_module("entitlements_api_704", "user-tracking/entitlements_api.py")
    ea.API_KEY = ""
    ea.IAP_VERIFY_MODE = "stub"
    return {"ca": ca, "ea": ea}


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
    cur.execute("SELECT id FROM communities WHERE name LIKE %s", (TEST_PREFIX + '%',))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        for tbl in ("community_organiser_offers", "community_reports",
                    "community_episodes", "community_passes",
                    "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _seed_level(user_id, level="l2"):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
            "VALUES (%s, %s, NOW()) "
            "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level",
            (user_id, level),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _create(client, owner, name, product="audioura.pass.usd5", **overrides):
    _seed_level(owner)
    body = {"owner_user_id": owner, "name": name}
    if "pass_products" not in overrides:
        body["pass_products"] = [{"product_id": product, "length": "month"}]
    body.update(overrides)
    return client.post("/communities", json=body)


def _buy(client, cid, user_id, product="audioura.pass.usd5", length="month", txid=None):
    txid = txid or (TEST_PREFIX + f"txn-{user_id}-{cid}")
    return client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": txid,
        "product": product, "length": length,
        "user_id": user_id, "community_id": cid,
    })


def _page(client, cid, user_id=None):
    q = {"user_id": user_id} if user_id else None
    return client.get(f"/communities/{cid}", query_string=q).get_json()


def _row(db, cid):
    cur = db.cursor()
    cur.execute(
        "SELECT status, launched_at, archived_reason, low_members_since, "
        "last_low_warning_at, zero_members_since FROM communities WHERE id = %s",
        (cid,))
    r = cur.fetchone()
    cur.close()
    return {"status": r[0], "launched_at": r[1], "archived_reason": r[2],
            "low_since": r[3], "last_warn": r[4], "zero_since": r[5]}


def _set_member_expiry(db, cid, user_id, when):
    cur = db.cursor()
    cur.execute(
        "UPDATE community_memberships SET expires_at = %s "
        "WHERE community_id = %s AND user_id = %s", (when, cid, user_id))
    db.commit()
    cur.close()


def _now():
    return datetime.now(timezone.utc)


# ─── D665: pass_required ────────────────────────────────────────────────────

def test_create_without_pass_is_pass_required(client):
    _seed_level(TEST_PREFIX + "np-owner")
    r = client.post("/communities", json={
        "owner_user_id": TEST_PREFIX + "np-owner",
        "name": TEST_PREFIX + "No Pass", "pass_products": []})
    assert r.status_code == 400
    assert r.get_json()["error"] == "pass_required"


def test_free_join_is_pass_required_for_any_community(client):
    c = _create(client, TEST_PREFIX + "fj-owner", TEST_PREFIX + "FJ").get_json()
    r = client.post(f"/communities/{c['id']}/join",
                    json={"user_id": TEST_PREFIX + "fj-m1"})
    assert r.status_code == 402
    assert r.get_json()["error"] == "pass_required"


# ─── D665: the $1 pass verifies + grants ────────────────────────────────────

def test_dollar_pass_verifies_and_grants(client, db):
    owner = TEST_PREFIX + "d1-owner"
    c = _create(client, owner, TEST_PREFIX + "Dollar",
                product="audioura.pass.usd1").get_json()
    cid = c["id"]
    r = _buy(client, cid, TEST_PREFIX + "d1-m1", product="audioura.pass.usd1")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["amount"] == 1.0
    # The member is active.
    page = _page(client, cid, TEST_PREFIX + "d1-m1")
    assert page["my_status"]["active"] is True


# ─── D665: member_count excludes owner and expired members ──────────────────

def test_member_count_excludes_owner_and_expired(client, db):
    owner = TEST_PREFIX + "mc-owner"
    c = _create(client, owner, TEST_PREFIX + "Counted").get_json()
    cid = c["id"]
    # Owner on the page → not counted.
    assert _page(client, cid, owner)["member_count"] == 0
    _buy(client, cid, TEST_PREFIX + "mc-m1")
    _buy(client, cid, TEST_PREFIX + "mc-m2")
    assert _page(client, cid, owner)["member_count"] == 2
    # Expire one member → the count drops to 1 (expired members don't count).
    _set_member_expiry(db, cid, TEST_PREFIX + "mc-m1", _now() - timedelta(days=1))
    assert _page(client, cid, owner)["member_count"] == 1


# ─── D665 addendum: owner is not a member ───────────────────────────────────

def test_owner_cannot_buy_or_join_own_community(client):
    owner = TEST_PREFIX + "oc-owner"
    c = _create(client, owner, TEST_PREFIX + "Owner").get_json()
    cid = c["id"]
    rb = _buy(client, cid, owner, txid=TEST_PREFIX + "oc-self")
    assert rb.status_code == 409
    assert rb.get_json()["error"] == "owner_cannot_join"
    rj = client.post(f"/communities/{cid}/join", json={"user_id": owner})
    assert rj.status_code == 409
    assert rj.get_json()["error"] == "owner_cannot_join"


def test_owner_plays_everything_without_a_pass(client):
    owner = TEST_PREFIX + "op-owner"
    c = _create(client, owner, TEST_PREFIX + "OwnerPlays").get_json()
    cid = c["id"]
    # Owner adds an episode, then (with NO membership) still sees the episode
    # list and the page reports them as owner with full access.
    client.post(f"/communities/{cid}/episodes", json={
        "owner_user_id": owner,
        "episodes": [{"title": "Ep1", "audio_url": "https://o.example/1.mp3"}]})
    page = _page(client, cid, owner)
    assert page["is_owner"] is True
    assert page["my_status"]["is_member"] is False
    assert len(page["episodes"]) == 1
    # The episodes endpoint also serves the owner without a membership.
    r = client.get(f"/communities/{cid}/episodes", query_string={"user_id": owner})
    assert r.status_code == 200
    assert len(r.get_json()["episodes"]) == 1


# ─── D665: demo book club migration + 30-day grandfather ────────────────────

def test_free_community_converted_and_member_grandfathered(client, db, modules):
    """A pre-rule FREE community with a free member: the migration's conversion
    logic (applied here to a TEST community so the shared demo book club is not
    touched) sets is_paid, adds a $1/month option, and grandfathers the free
    member 30 days."""
    owner = TEST_PREFIX + "bc-owner"
    _seed_level(owner)
    # Build a FREE community + a free (NULL-expiry) member directly, mimicking a
    # community created before D665.
    cur = db.cursor()
    cur.execute(
        "INSERT INTO communities (owner_user_id, name, is_paid, visibility, "
        "status, join_code, launch_deadline) "
        "VALUES (%s, %s, FALSE, 'private', 'active', %s, NOW() + INTERVAL '168 hours') "
        "RETURNING id",
        (owner, TEST_PREFIX + "Book Club", TEST_PREFIX[:8].replace('-', '') + "1"))
    cid = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO community_memberships (user_id, community_id, expires_at) "
        "VALUES (%s, %s, NULL)", (TEST_PREFIX + "bc-m1", cid))
    db.commit()
    cur.close()

    # Run the conversion the migration performs (scoped to this one community so
    # the shared DB's real demo book club is never touched by the test).
    cur = db.cursor()
    cur.execute(
        "INSERT INTO community_passes (community_id, product_id, length, duration_days) "
        "VALUES (%s, 'audioura.pass.usd1', 'month', 30) ON CONFLICT DO NOTHING", (cid,))
    cur.execute(
        "UPDATE community_memberships SET expires_at = NOW() + INTERVAL '30 days' "
        "WHERE community_id = %s AND expires_at IS NULL", (cid,))
    cur.execute("UPDATE communities SET is_paid = TRUE WHERE id = %s", (cid,))
    db.commit()
    cur.close()

    # The community is now paid, offers a $1/month pass, and the grandfathered
    # member is active for ~30 days.
    page = _page(client, cid, owner)
    assert page["is_paid"] is True
    assert any(p["label"] == "$1 / month" for p in page["passes"])
    mpage = _page(client, cid, TEST_PREFIX + "bc-m1")
    assert mpage["my_status"]["active"] is True
    # A grandfathered (unpaid) member does NOT count toward the paid member
    # count (transaction_id is NULL).
    assert page["member_count"] == 0


# ─── D666: post-launch low-members warnings (day 0, 7, 14; not daily) ───────

def _launch(client, cid):
    _buy(client, cid, TEST_PREFIX + "L-a")
    _buy(client, cid, TEST_PREFIX + "L-b")


def test_drop_to_one_warns_day0_7_14_not_daily_and_stops_when_back(client, db, modules):
    ca = modules["ca"]
    owner = TEST_PREFIX + "lw-owner"
    c = _create(client, owner, TEST_PREFIX + "LowWarn").get_json()
    cid = c["id"]
    _launch(client, cid)
    assert _row(db, cid)["launched_at"] is not None

    # Drop to 1: expire member L-b. Now 1 active member (L-a).
    _set_member_expiry(db, cid, TEST_PREFIX + "L-b", _now() - timedelta(hours=1))

    conn = get_connection()
    cur = conn.cursor()
    t0 = _now()
    # Day 0 → warns.
    res0 = ca.run_launch_window(cur, now=t0)
    conn.commit()
    assert cid in res0["low_members_warned"]
    assert cid not in res0["archived_no_members"]

    # A run the NEXT DAY must NOT warn again (weekly, not daily).
    res1 = ca.run_launch_window(cur, now=t0 + timedelta(days=1))
    conn.commit()
    assert cid not in res1["low_members_warned"]

    # Day 7 → warns again.
    res7 = ca.run_launch_window(cur, now=t0 + timedelta(days=7, minutes=1))
    conn.commit()
    assert cid in res7["low_members_warned"]

    # Day 14 → warns again.
    res14 = ca.run_launch_window(cur, now=t0 + timedelta(days=14, minutes=2))
    conn.commit()
    assert cid in res14["low_members_warned"]

    # Back to 2 active members (give L-b a fresh pass) → warnings stop, trackers
    # clear.
    cur.close()
    conn.close()
    _buy(client, cid, TEST_PREFIX + "L-b", txid=TEST_PREFIX + "renew-b")
    conn = get_connection()
    cur = conn.cursor()
    res_ok = ca.run_launch_window(cur, now=t0 + timedelta(days=15))
    conn.commit()
    assert cid not in res_ok["low_members_warned"]
    cur.close()
    conn.close()
    assert _row(db, cid)["low_since"] is None


# ─── D666: 0 members for 6 days still active, 7 days archived ───────────────

def test_zero_members_six_days_active_seven_days_archived(client, db, modules):
    ca = modules["ca"]
    owner = TEST_PREFIX + "z-owner"
    c = _create(client, owner, TEST_PREFIX + "ZeroArch").get_json()
    cid = c["id"]
    _launch(client, cid)
    # Drop to 0: expire BOTH members.
    _set_member_expiry(db, cid, TEST_PREFIX + "L-a", _now() - timedelta(hours=1))
    _set_member_expiry(db, cid, TEST_PREFIX + "L-b", _now() - timedelta(hours=1))

    conn = get_connection()
    cur = conn.cursor()
    t0 = _now()
    ca.run_launch_window(cur, now=t0)  # day 0: stamp zero_members_since
    conn.commit()
    # Day 6 → still active (not yet a week at 0).
    ca.run_launch_window(cur, now=t0 + timedelta(days=6))
    conn.commit()
    cur.close(); conn.close()
    assert _row(db, cid)["status"] == "active"

    conn = get_connection(); cur = conn.cursor()
    res7 = ca.run_launch_window(cur, now=t0 + timedelta(days=7, minutes=1))
    conn.commit(); cur.close(); conn.close()
    assert cid in res7["archived_no_members"]
    row = _row(db, cid)
    assert row["status"] == "archived"
    assert row["archived_reason"] == "no_members"


def test_one_member_for_thirty_days_never_archived(client, db, modules):
    ca = modules["ca"]
    owner = TEST_PREFIX + "o1-owner"
    c = _create(client, owner, TEST_PREFIX + "OneForever").get_json()
    cid = c["id"]
    _launch(client, cid)
    # Drop to exactly 1 (expire one member only) and keep it there for 30 days.
    _set_member_expiry(db, cid, TEST_PREFIX + "L-b", _now() - timedelta(hours=1))

    conn = get_connection()
    cur = conn.cursor()
    t0 = _now()
    for day in range(0, 31):
        ca.run_launch_window(cur, now=t0 + timedelta(days=day))
        conn.commit()
    cur.close(); conn.close()
    # Between 1 and 2 members it keeps running — never archived.
    assert _row(db, cid)["status"] == "active"
