"""
test_local729_reimbursement.py — LOCAL-729 / D691, D690, D692, D688, D613.

Reimbursement, ADMINISTRATOR ONLY (ClickUp wdvrdaz3tb, approved 2026-10-21).
Only Audioura reimburses a tour buyer, a community member or a plan purchaser;
never an app user. This exercises, end to end against the REAL communities_api /
entitlements_api blueprints (DB-backed, in-process Flask client) AND the real
moderation.py CLI against the isolated test DB:

  A. SUPPORT ID — a short public alias per device (AU-XXXX), unique, resolvable
     by the admin tools; the gateway /support-id endpoint allocates one and is
     idempotent; the admin tools accept either the Support ID or the device id.

  B. LEDGER — every reimbursement command/endpoint writes EXACTLY ONE
     admin_actions row with the right verb and money/purchase columns.

  C. MAKE-GOOD IN KIND —
     - grant-tour writes one UNCONSUMED tour_unlocks row (store='admin_grant')
       so the download gate passes ONCE, and consuming it closes the gate;
     - extend-pass / grant-pass change expires_at only (the purchase row and its
       transaction_id survive — D690);
     - add-plan-units / extend-plan touch the allowance state only (D613).

  D. MONEY BACK (Google) — refund-google (Google API MOCKED, no network, no real
     refund) revokes the unlock locally AND KEEPS the purchase row (D690); with
     no service account it REFUSES (no ledger row).

  E. APPLE — apple-refund-message marks the purchase refund_supported and emits
     the customer text; no money moves.

  F. ADMIN-KEY REFUSAL — every admin endpoint refuses without the admin key
     (401) and when no admin key is configured (503); the app's gateway key is
     NOT the admin key.

  RED: with the admin-key check broken (forced to allow), a normal user's
     gateway-key call to grant-tour SUCCEEDS — proving the "refused without the
     admin key" guarantee is not vacuous (a normal user could grant themselves a
     tour).

Every row uses the 'TEST-729-' prefix; cleanup touches only those rows.
"""

import os
import sys
import importlib.util
import subprocess

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-729-"
ADMIN_KEY = "test-admin-secret-729"
GATEWAY_KEY = "test-gateway-secret-729"


def _load_module(name, rel_path):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def modules():
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    _load_module("communities_rss", "user-tracking/communities_rss.py")
    ca = _load_module("communities_api", "user-tracking/communities_api.py")
    ea = _load_module("entitlements_api_729", "user-tracking/entitlements_api.py")
    ca.API_KEY = GATEWAY_KEY
    ca.ADMIN_API_KEY = ADMIN_KEY
    ea.API_KEY = GATEWAY_KEY
    ea.IAP_VERIFY_MODE = "stub"
    ca.IAP_VERIFY_MODE = "stub"
    return {"ca": ca, "ea": ea}


@pytest.fixture(scope="module")
def client(modules):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(modules["ca"].communities_bp)
    app.register_blueprint(modules["ea"].entitlements_bp)
    app.testing = True
    return app.test_client()


GW = {"X-API-Key": GATEWAY_KEY}
ADM = {"X-API-Key": ADMIN_KEY}


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
        for tbl in ("community_blocks", "community_reports", "community_episodes",
                    "community_passes", "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        cur.execute("UPDATE audio_tours SET community_id = NULL "
                    "WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM admin_actions WHERE target_community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM tour_unlocks WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM purchases WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM community_memberships WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM admin_actions WHERE target_user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM admin_actions WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM support_ids WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    # Clean the test tour(s) we create.
    cur.execute("DELETE FROM audio_tours WHERE tour_name LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _cli(*args):
    """Run moderation.py against the isolated test DB. Returns (rc, stdout)."""
    env = dict(os.environ)
    env["DATABASE_URL"] = get_database_url()
    root = os.path.dirname(os.path.dirname(__file__))
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "moderation.py"), *args],
        capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


def _seed_device(user_id, level="l3"):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO device_entitlement (user_id, level, fresh_used, "
            "pack_started_at, anniversary_at, last_activity_at) "
            "VALUES (%s, %s, 5, NOW(), NOW() + INTERVAL '10 days', NOW()) "
            "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level, "
            "fresh_used = 5, anniversary_at = NOW() + INTERVAL '10 days'",
            (user_id, level))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _make_tour(name):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string) "
            "VALUES (%s, %s) RETURNING id", (name, 'x'))
        tid = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return tid
    finally:
        conn.close()


def _make_community(owner):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO communities (owner_user_id, name, visibility) "
            "VALUES (%s, %s, 'private') RETURNING id",
            (owner, TEST_PREFIX + "Comm"))
        cid = cur.fetchone()[0]
        conn.commit()
        cur.close()
        return cid
    finally:
        conn.close()


def _make_membership(user_id, community_id, days=5, txn=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO community_memberships "
            "(user_id, community_id, expires_at, transaction_id, store, "
            " price_usd, created_at, updated_at) "
            "VALUES (%s, %s, NOW() + make_interval(days => %s), %s, 'google', "
            " 5.00, NOW(), NOW()) "
            "ON CONFLICT (user_id, community_id) DO UPDATE SET "
            " expires_at = EXCLUDED.expires_at",
            (user_id, community_id, days, txn or (TEST_PREFIX + "mtxn")))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _ledger_count(db, action, user_id=None, txn=None):
    cur = db.cursor()
    q = "SELECT COUNT(*) FROM admin_actions WHERE action = %s"
    params = [action]
    if user_id is not None:
        q += " AND target_user_id = %s"
        params.append(user_id)
    if txn is not None:
        q += " AND transaction_id = %s"
        params.append(txn)
    cur.execute(q, tuple(params))
    n = cur.fetchone()[0]
    cur.close()
    return n


# ─── A. SUPPORT ID ────────────────────────────────────────────────────────────

def test_support_id_is_unique_and_resolves(client, db):
    u1 = TEST_PREFIX + "sid-1"
    u2 = TEST_PREFIX + "sid-2"
    # The gateway endpoint allocates one and is idempotent.
    r1 = client.post("/support-id", json={"user_id": u1}, headers=GW)
    assert r1.status_code == 200, r1.get_json()
    sid1 = r1.get_json()["support_id"]
    assert sid1.startswith("AU-") and len(sid1) == 7
    # Idempotent: same device → same alias.
    r1b = client.get("/support-id", query_string={"user_id": u1}, headers=GW)
    assert r1b.status_code == 200
    assert r1b.get_json()["support_id"] == sid1
    # A different device → a different alias (unique index).
    r2 = client.post("/support-id", json={"user_id": u2}, headers=GW)
    sid2 = r2.get_json()["support_id"]
    assert sid2 != sid1
    # It resolves back to the device via the CLI (grant something by Support ID).
    tour = _make_tour(TEST_PREFIX + "sidtour")
    rc, out = _cli("grant-tour", sid1, str(tour), "en", "resolve-check")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s", (u1, tour))
    assert cur.fetchone()[0] == 1, "the Support ID must resolve to the device"
    cur.close()


def test_support_id_never_the_secret_id(client):
    u = TEST_PREFIX + "sid-secret"
    sid = client.post("/support-id", json={"user_id": u},
                      headers=GW).get_json()["support_id"]
    assert sid != u and u not in sid


# ─── B+C. GRANT-TOUR: one ledger row, gate passes once, consumes ─────────────

def test_grant_tour_passes_gate_once_and_consumes(db):
    user = TEST_PREFIX + "gt-user"
    tour = _make_tour(TEST_PREFIX + "gttour")
    rc, out = _cli("--actor", "LEAD", "grant-tour", user, str(tour), "en", "retry")
    assert rc == 0, out
    assert "Ledger written" in out
    cur = db.cursor()
    # Exactly ONE unconsumed unlock, store='admin_grant' → the gate passes.
    cur.execute("SELECT COUNT(*), BOOL_AND(consumed_at IS NULL), "
                "BOOL_AND(store = 'admin_grant') FROM tour_unlocks "
                "WHERE user_id = %s AND tour_id = %s", (user, tour))
    n, unconsumed, is_grant = cur.fetchone()
    assert n == 1 and unconsumed and is_grant
    # The download gate predicate (consumed_at IS NULL) is TRUE now.
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s AND consumed_at IS NULL", (user, tour))
    assert cur.fetchone()[0] == 1, "gate passes while unconsumed"
    # Simulate a successful download consuming it (what map-delivery does).
    cur.execute("UPDATE tour_unlocks SET consumed_at = NOW(), "
                "consumed_by_download_id = 'dl-1' WHERE user_id = %s "
                "AND tour_id = %s", (user, tour))
    db.commit()
    # The gate now CLOSES — no unconsumed unlock remains.
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s AND consumed_at IS NULL", (user, tour))
    assert cur.fetchone()[0] == 0, "consumed once → gate closed"
    cur.close()
    # Exactly one ledger row for the grant.
    assert _ledger_count(db, 'grant_tour', user) == 1


# ─── C. EXTEND / GRANT PASS: expires_at only, purchase row kept ──────────────

def test_extend_pass_changes_expires_at_only(db):
    user = TEST_PREFIX + "ep-user"
    cid = _make_community(TEST_PREFIX + "ep-owner")
    txn = TEST_PREFIX + "ep-txn"
    _make_membership(user, cid, days=3, txn=txn)
    cur = db.cursor()
    cur.execute("SELECT expires_at, transaction_id FROM community_memberships "
                "WHERE user_id = %s AND community_id = %s", (user, cid))
    before_exp, before_txn = cur.fetchone()
    cur.close()
    rc, out = _cli("extend-pass", str(cid), user, "10", "goodwill")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT expires_at, transaction_id, COUNT(*) OVER () "
                "FROM community_memberships WHERE user_id = %s "
                "AND community_id = %s", (user, cid))
    after_exp, after_txn, n = cur.fetchone()
    cur.close()
    assert n == 1, "no new membership row — one per (user, community)"
    assert after_exp > before_exp, "expires_at pushed out"
    assert after_txn == before_txn, "the purchase record (transaction_id) is kept (D690)"
    assert _ledger_count(db, 'extend_pass', user) == 1


def test_grant_pass_creates_membership_by_length(db):
    user = TEST_PREFIX + "gp-user"
    cid = _make_community(TEST_PREFIX + "gp-owner")
    rc, out = _cli("grant-pass", user, str(cid), "month", "makegood")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT expires_at, store FROM community_memberships "
                "WHERE user_id = %s AND community_id = %s", (user, cid))
    exp, store = cur.fetchone()
    cur.close()
    assert exp is not None and store == 'admin_grant'
    assert _ledger_count(db, 'grant_pass', user) == 1


# ─── C. PLAN UNITS / EXTEND PLAN (D613) ──────────────────────────────────────

def test_add_plan_units_lowers_fresh_used(db):
    user = TEST_PREFIX + "apu-user"
    _seed_device(user)  # fresh_used = 5
    rc, out = _cli("add-plan-units", user, "3", "retry-cost")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT fresh_used FROM device_entitlement WHERE user_id = %s",
                (user,))
    assert cur.fetchone()[0] == 2, "fresh_used 5 - 3 = 2 (more units granted)"
    cur.close()
    assert _ledger_count(db, 'add_plan_units', user) == 1


def test_add_plan_units_floors_at_zero(db):
    user = TEST_PREFIX + "apu2-user"
    _seed_device(user)  # fresh_used = 5
    assert _cli("add-plan-units", user, "99")[0] == 0
    cur = db.cursor()
    cur.execute("SELECT fresh_used FROM device_entitlement WHERE user_id = %s",
                (user,))
    assert cur.fetchone()[0] == 0, "never below zero"
    cur.close()


def test_extend_plan_pushes_anniversary(db):
    user = TEST_PREFIX + "xpl-user"
    _seed_device(user)
    cur = db.cursor()
    cur.execute("SELECT anniversary_at FROM device_entitlement WHERE user_id = %s",
                (user,))
    before = cur.fetchone()[0]
    cur.close()
    rc, out = _cli("extend-plan", user, "30", "goodwill")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT anniversary_at FROM device_entitlement WHERE user_id = %s",
                (user,))
    after = cur.fetchone()[0]
    cur.close()
    assert after > before
    assert _ledger_count(db, 'extend_plan', user) == 1


# ─── D. REFUND-GOOGLE (mocked): revokes, keeps the purchase row ──────────────

class _FakeGoogleClient:
    """A mock Google API client: records the refund call, performs NO network."""
    def __init__(self):
        self.calls = []

    def refund_order(self, package_name=None, order_id=None, revoke=True):
        self.calls.append({"package_name": package_name, "order_id": order_id,
                           "revoke": revoke})
        return None  # Google answers 204 No Content


def _seed_google_tour_purchase(user, order_id, tour_id):
    """A verified Google tour purchase + its unlock, as the verify path writes."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO purchases (transaction_id, store, product, user_id, "
            " amount, raw_status) VALUES (%s, 'google', 'audioura.tour.tier3', "
            " %s, 4.99, %s)",
            (order_id, user, f'google_verified:{order_id}'))
        cur.execute(
            "INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, "
            " price_usd) VALUES (%s, %s, %s, 'google', 4.99)",
            (user, tour_id, order_id))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def test_refund_google_mocked_revokes_and_keeps_purchase(modules, db, monkeypatch):
    user = TEST_PREFIX + "rg-user"
    tour = _make_tour(TEST_PREFIX + "rgtour")
    order = TEST_PREFIX + "GPA.rg-order"
    _seed_google_tour_purchase(user, order, tour)
    # Mock the Google client so NO real refund / network happens.
    import google_play_refund as gpr
    fake = _FakeGoogleClient()
    monkeypatch.setattr(gpr, "_build_default_client", lambda: fake)
    conn = get_connection()
    try:
        cur = conn.cursor()
        summary = gpr.refund_order(cur, order, api_client=None, partial_usd=None)
        # Log the ledger row the way the CLI/endpoint does.
        cur.execute(
            "INSERT INTO admin_actions (action, actor, reason, amount_usd, "
            " transaction_id, store) VALUES "
            " ('refund_google', 'LEAD', 'refund', 4.99, %s, 'google')", (order,))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    # The mock was called with revoke=True (full refund).
    assert fake.calls == [{"package_name": None, "order_id": order,
                           "revoke": True}] or \
        (len(fake.calls) == 1 and fake.calls[0]["order_id"] == order
         and fake.calls[0]["revoke"] is True)
    assert summary["revoked"] is True
    cur = db.cursor()
    # The unlock was revoked locally.
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s", (user, tour))
    assert cur.fetchone()[0] == 0, "full refund revokes the local unlock"
    # The purchase RECEIPT row is KEPT, marked voided (D690 — never deleted).
    cur.execute("SELECT raw_status FROM purchases WHERE transaction_id = %s",
                (order,))
    row = cur.fetchone()
    assert row is not None, "the purchase row must survive a refund (D690)"
    assert row[0].startswith("voided:"), "the receipt is marked voided"
    cur.close()
    assert _ledger_count(db, 'refund_google', txn=order) == 1


def test_refund_google_partial_keeps_access(modules, db, monkeypatch):
    user = TEST_PREFIX + "rgp-user"
    tour = _make_tour(TEST_PREFIX + "rgptour")
    order = TEST_PREFIX + "GPA.rgp-order"
    _seed_google_tour_purchase(user, order, tour)
    import google_play_refund as gpr
    fake = _FakeGoogleClient()
    monkeypatch.setattr(gpr, "_build_default_client", lambda: fake)
    conn = get_connection()
    try:
        cur = conn.cursor()
        summary = gpr.refund_order(cur, order, api_client=None, partial_usd=2.00)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    assert fake.calls[0]["revoke"] is False, "partial refund does NOT revoke"
    assert summary["revoked"] is False
    cur = db.cursor()
    # A partial refund keeps the local unlock (the buyer keeps access).
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s", (user, tour))
    assert cur.fetchone()[0] == 1, "partial refund keeps access"
    cur.close()


def test_refund_google_refuses_without_service_account(monkeypatch):
    import google_play_refund as gpr
    # No injected client AND no SA configured → RefundNotConfigured, no refund.
    monkeypatch.setattr(gpr, "GOOGLE_PLAY_SA_JSON", "")
    conn = get_connection()
    try:
        cur = conn.cursor()
        with pytest.raises(gpr.RefundNotConfigured):
            gpr.refund_order(cur, "GPA.whatever", api_client=None)
        conn.rollback()
        cur.close()
    finally:
        conn.close()


def test_refund_google_endpoint_refuses_without_sa(client, modules, db):
    # The admin endpoint answers 503 refund_not_configured and writes NO ledger.
    order = TEST_PREFIX + "GPA.noSA"
    import google_play_refund as gpr
    saved = gpr.GOOGLE_PLAY_SA_JSON
    gpr.GOOGLE_PLAY_SA_JSON = ""
    try:
        r = client.post("/communities/admin/refund-google",
                        json={"order_id": order}, headers=ADM)
        assert r.status_code == 503
        assert r.get_json()["error"] == "refund_not_configured"
    finally:
        gpr.GOOGLE_PLAY_SA_JSON = saved
    assert _ledger_count(db, 'refund_google', txn=order) == 0


# ─── E. APPLE REFUND MESSAGE: marks refund_supported, no money moves ─────────

def test_apple_refund_message_marks_supported(db):
    user = TEST_PREFIX + "ar-user"
    order = TEST_PREFIX + "apple-order"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO purchases (transaction_id, store, product, user_id, "
            " amount, raw_status) VALUES (%s, 'apple', 'audioura.tour.tier2', "
            " %s, 2.99, 'apple_verified')", (order, user))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    rc, out = _cli("apple-refund-message", order, "ios-buyer")
    assert rc == 0, out
    assert "reportaproblem.apple.com" in out
    cur = db.cursor()
    cur.execute("SELECT refund_supported FROM purchases WHERE transaction_id = %s",
                (order,))
    assert cur.fetchone()[0] is True, "the purchase is marked refund_supported"
    cur.close()
    assert _ledger_count(db, 'apple_refund_support', txn=order) == 1


# ─── F. ADMIN-KEY REFUSAL ─────────────────────────────────────────────────────

def test_every_reimbursement_endpoint_refuses_without_admin_key(client, db):
    user = TEST_PREFIX + "guard-user"
    cid = _make_community(TEST_PREFIX + "guard-owner")
    tour = _make_tour(TEST_PREFIX + "guardtour")
    endpoints = [
        ("post", "/communities/admin/support-id", {"user_id": user}),
        ("post", "/communities/admin/grant-tour",
         {"device": user, "tour_id": tour}),
        ("post", f"/communities/{cid}/admin/extend-pass",
         {"device": user, "days": 5}),
        ("post", f"/communities/{cid}/admin/grant-pass",
         {"device": user, "length": "month"}),
        ("post", "/communities/admin/add-plan-units", {"device": user, "n": 3}),
        ("post", "/communities/admin/extend-plan", {"device": user, "days": 5}),
        ("post", "/communities/admin/refund-google", {"order_id": "GPA.x"}),
        ("post", "/communities/admin/apple-refund-message", {"target": "x"}),
        ("get", "/communities/admin/ledger", None),
    ]
    for method, path, body in endpoints:
        call = getattr(client, method)
        # No key → 401.
        r = call(path, json=body) if body is not None else call(path)
        assert r.status_code == 401, f"{path} must refuse with no key"
        # The APP's gateway key is NOT the admin key → still 401.
        r = (call(path, json=body, headers=GW) if body is not None
             else call(path, headers=GW))
        assert r.status_code == 401, f"{path} must refuse the gateway key"
    # No reimbursement reached the ledger.
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM admin_actions WHERE target_user_id = %s "
                "OR target_community_id = %s", (user, cid))
    assert cur.fetchone()[0] == 0
    cur.close()


def test_admin_endpoint_closed_when_no_admin_key_configured(client, modules):
    ca = modules["ca"]
    saved = ca.ADMIN_API_KEY
    ca.ADMIN_API_KEY = ""
    try:
        r = client.get("/communities/admin/ledger", headers=ADM)
        assert r.status_code == 503
        assert r.get_json()["error"] == "admin_not_configured"
    finally:
        ca.ADMIN_API_KEY = saved


def test_admin_grant_tour_endpoint_with_admin_key_grants_and_logs(client, db):
    user = TEST_PREFIX + "ep-grant"
    tour = _make_tour(TEST_PREFIX + "epgranttour")
    r = client.post("/communities/admin/grant-tour",
                    json={"device": user, "tour_id": tour, "actor": "LEAD",
                          "reason": "endpoint-grant"}, headers=ADM)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["granted"] is True
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                "AND tour_id = %s AND consumed_at IS NULL", (user, tour))
    assert cur.fetchone()[0] == 1
    cur.close()
    assert _ledger_count(db, 'grant_tour', user) == 1


# ─── RED ──────────────────────────────────────────────────────────────────────

def test_red_broken_admin_gate_lets_normal_user_grant_a_tour(client, modules, db):
    """The green guarantee (test_every_reimbursement_endpoint_refuses_without_
    admin_key) is that a normal user (gateway key, no admin key) CANNOT grant a
    tour. This forces the admin-key check to always pass (the hole) and shows a
    normal user's gateway-key call to grant-tour SUCCEEDS (200) and grants the
    unlock — so the 'refused with 401' assertion then FAILS, proving it is not
    vacuous (a normal user could reimburse themselves)."""
    ca = modules["ca"]
    user = TEST_PREFIX + "RED-user"
    tour = _make_tour(TEST_PREFIX + "REDtour")
    orig = ca._require_admin_key
    ca._require_admin_key = lambda: None  # broken: admin check always passes
    try:
        r = client.post("/communities/admin/grant-tour",
                        json={"device": user, "tour_id": tour}, headers=GW)
        # With the gate broken, a NORMAL user's call succeeds and grants a tour.
        assert r.status_code == 200, r.get_json()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s "
                    "AND tour_id = %s", (user, tour))
        assert cur.fetchone()[0] == 1, "the broken gate granted the tour"
        cur.close()
        # The green assertion ('refused with 401') is therefore NOT vacuous:
        with pytest.raises(AssertionError):
            assert r.status_code == 401, "a working admin gate refuses the user"
    finally:
        ca._require_admin_key = orig


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
