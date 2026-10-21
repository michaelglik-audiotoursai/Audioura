"""
test_local728_admin_moderation.py — LOCAL-728 / D691, D690, D658.

D691 removed user-level blocking: members and organisers REPORT to Audioura,
and only the ADMINISTRATOR bars a member from a community or bans a user from
the service. This exercises that end to end against the REAL communities_api
blueprint (DB-backed, same in-process Flask client + stub IAP harness as the
LOCAL-726 test it replaces) AND the real moderation.py CLI against the isolated
test DB. Every row uses the 'TEST-728-' prefix; cleanup touches only those rows.

  A. REPORT TO AUDIOURA
     - POST /communities/<id>/report writes ONE community_reports row with the
       reason code + optional detail + status 'open' (it reaches the server);
     - the old user-block endpoints are GONE / admin-gated: the user key cannot
       bar, ban, or list reports.

  B. ADMIN-KEY REFUSAL
     - every admin endpoint refuses without the admin key (401), and refuses
       when no admin key is configured (503);
     - the app's gateway key is NOT the admin key — a gateway-key request to an
       admin endpoint is still refused.

  C. ADMIN BAR / BAN / LIFT via the moderation.py CLI (isolated DB)
     - `bar` ends the membership BY EXPIRY (never DELETE — D690: the row, the
       purchase record, survives) and records an admin_bar; the barred member
       cannot rejoin by code (403 barred);
     - `unbar` lifts it; the member can buy a pass again;
     - `ban` writes an active service_bans row; a banned user's purchase AND
       community creation are refused (403 banned); downloaded audio is never
       touched (we never DELETE a membership/purchase row);
     - `unban` lifts the ban; the user can purchase again;
     - EVERY action writes an admin_actions ledger row (who, when, target,
       reason, report id).

  RED: with the admin check broken (is_user_service_banned forced False), a
     banned user's purchase succeeds — proving the "banned user is refused"
     assertion is not vacuous.
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

TEST_PREFIX = "TEST-728-"
ADMIN_KEY = "test-admin-secret-728"
GATEWAY_KEY = "test-gateway-secret-728"


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
    ea = _load_module("entitlements_api_728", "user-tracking/entitlements_api.py")
    # The app sends the GATEWAY key on every call; the admin surface requires a
    # DISTINCT admin key the app never carries.
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


# Headers: the APP sends the gateway key; the ADMIN sends the admin key.
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
        for tbl in ("community_blocks", "community_organiser_offers",
                    "community_reports", "community_episodes",
                    "community_passes", "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        cur.execute("UPDATE audio_tours SET community_id = NULL "
                    "WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM admin_actions WHERE target_community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM service_bans WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM admin_actions WHERE target_user_id LIKE %s", (TEST_PREFIX + '%',))
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


def _create(client, owner, name, **overrides):
    _seed_level(owner)
    body = {"owner_user_id": owner, "name": name,
            "visibility": overrides.pop("visibility", "listed"),
            "latitude": overrides.pop("latitude", 42.33),
            "longitude": overrides.pop("longitude", -71.21)}
    body.setdefault("pass_products",
                    [{"product_id": "audioura.pass.usd5", "length": "month"}])
    body.update(overrides)
    r = client.post("/communities", json=body, headers=GW)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _buy_pass(client, cid, user_id, txn_suffix=""):
    return client.post("/purchases/verify", json={
        "store": "stub",
        "transaction_id": TEST_PREFIX + f"txn-{user_id}-{cid}-{txn_suffix}",
        "product": "audioura.pass.usd5", "length": "month",
        "user_id": user_id, "community_id": cid,
    }, headers=GW)


def _cli(*args):
    """Run moderation.py against the isolated test DB. Returns (rc, stdout)."""
    env = dict(os.environ)
    env["DATABASE_URL"] = get_database_url()
    root = os.path.dirname(os.path.dirname(__file__))
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "moderation.py"), *args],
        capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


# ─── A. REPORT TO AUDIOURA ───────────────────────────────────────────────────

def test_report_writes_one_row_to_audioura(client, db):
    owner = TEST_PREFIX + "A-owner"
    c = _create(client, owner, TEST_PREFIX + "Reportable")
    cid = c["id"]
    reporter = TEST_PREFIX + "A-reporter"
    r = client.post(f"/communities/{cid}/report",
                    json={"user_id": reporter, "reason": "offensive",
                          "detail": "bad words in stop 2"}, headers=GW)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["reported"] is True
    report_id = r.get_json()["report_id"]
    # The row reached the server with reason + detail + status open.
    cur = db.cursor()
    cur.execute("SELECT reporter_user_id, reason, detail, status "
                "FROM community_reports WHERE id = %s", (report_id,))
    row = cur.fetchone()
    cur.close()
    assert row == (reporter, "offensive", "bad words in stop 2", "open")


def test_report_does_not_return_owner(client):
    # D691: the report goes to Audioura, NOT the owner — the response no longer
    # leaks the owner id the way the LOCAL-726 version did.
    owner = TEST_PREFIX + "A2-owner"
    c = _create(client, owner, TEST_PREFIX + "NoOwnerLeak")
    r = client.post(f"/communities/{c['id']}/report",
                    json={"reason": "spam"}, headers=GW)
    assert r.status_code == 200
    assert "owner_user_id" not in r.get_json()


# ─── B. ADMIN-KEY REFUSAL ─────────────────────────────────────────────────────

def test_admin_endpoints_refuse_without_admin_key(client):
    owner = TEST_PREFIX + "B-owner"
    c = _create(client, owner, TEST_PREFIX + "AdminGuard")
    cid = c["id"]
    user = TEST_PREFIX + "B-user"
    # No key at all → 401.
    assert client.post(f"/communities/{cid}/admin/bar",
                       json={"user_id": user}).status_code == 401
    assert client.post("/communities/admin/ban",
                       json={"user_id": user}).status_code == 401
    assert client.get("/communities/admin/reports").status_code == 401
    # The APP's gateway key is NOT the admin key → still 401.
    assert client.post(f"/communities/{cid}/admin/bar",
                       json={"user_id": user}, headers=GW).status_code == 401
    assert client.post("/communities/admin/ban",
                       json={"user_id": user}, headers=GW).status_code == 401
    assert client.get("/communities/admin/reports", headers=GW).status_code == 401
    # The ADMIN key works.
    assert client.get("/communities/admin/reports", headers=ADM).status_code == 200


def test_admin_endpoint_closed_when_no_admin_key_configured(client, modules):
    ca = modules["ca"]
    saved = ca.ADMIN_API_KEY
    ca.ADMIN_API_KEY = ""
    try:
        r = client.get("/communities/admin/reports", headers=ADM)
        assert r.status_code == 503
        assert r.get_json()["error"] == "admin_not_configured"
    finally:
        ca.ADMIN_API_KEY = saved


def test_the_old_user_block_endpoints_are_gone(client):
    # D691 removed user-level blocking entirely. The old routes 404.
    owner = TEST_PREFIX + "B3-owner"
    c = _create(client, owner, TEST_PREFIX + "NoUserBlock")
    cid = c["id"]
    assert client.post(f"/communities/{cid}/block",
                       json={"user_id": "x", "blocked_user_id": "y"},
                       headers=GW).status_code == 404
    assert client.post(f"/communities/{cid}/unblock",
                       json={"user_id": "x", "blocked_user_id": "y"},
                       headers=GW).status_code == 404
    assert client.get("/communities/blocks",
                      query_string={"user_id": "x"}, headers=GW).status_code == 404
    assert client.get(f"/communities/{cid}/members",
                      query_string={"user_id": owner}, headers=GW).status_code == 404


# ─── C. ADMIN BAR / BAN / LIFT via the CLI ────────────────────────────────────

def test_cli_bar_ends_membership_by_expiry_and_blocks_rejoin(client, db):
    owner = TEST_PREFIX + "C-owner"
    c = _create(client, owner, TEST_PREFIX + "CliBar")
    cid = c["id"]
    member = TEST_PREFIX + "C-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Admin bars via the CLI.
    rc, out = _cli("--actor", "LEAD", "bar", str(cid), member, "spam")
    assert rc == 0, out
    assert "Ledger written" in out
    # Membership is ENDED by expiry — the row (purchase record) is KEPT (D690).
    cur = db.cursor()
    cur.execute("SELECT COUNT(*), BOOL_AND(expires_at <= clock_timestamp()::timestamp), "
                "BOOL_AND(transaction_id IS NOT NULL) FROM community_memberships "
                "WHERE community_id = %s AND user_id = %s", (cid, member))
    n, expired, has_txn = cur.fetchone()
    assert n == 1 and expired and has_txn, "membership must be expired, not deleted"
    # An admin_bar row exists.
    cur.execute("SELECT COUNT(*) FROM community_blocks WHERE community_id = %s "
                "AND blocked_user_id = %s AND kind = 'admin_bar'", (cid, member))
    assert cur.fetchone()[0] == 1
    # The ledger recorded it.
    cur.execute("SELECT actor, reason FROM admin_actions WHERE action = 'bar' "
                "AND target_user_id = %s AND target_community_id = %s",
                (member, cid))
    assert cur.fetchone() == ("LEAD", "spam")
    cur.close()
    # The barred member cannot rejoin by code.
    rejoin = _buy_pass(client, cid, member, txn_suffix="rejoin")
    assert rejoin.status_code == 403, rejoin.get_json()
    assert rejoin.get_json()["error"] == "barred"


def test_cli_unbar_lets_member_return(client, db):
    owner = TEST_PREFIX + "C2-owner"
    c = _create(client, owner, TEST_PREFIX + "CliUnbar")
    cid = c["id"]
    member = TEST_PREFIX + "C2-member"
    assert _buy_pass(client, cid, member).status_code == 200
    assert _cli("bar", str(cid), member)[0] == 0
    assert _buy_pass(client, cid, member, "x").status_code == 403
    rc, out = _cli("unbar", str(cid), member)
    assert rc == 0, out
    # The member can buy a pass again.
    assert _buy_pass(client, cid, member, "afterunbar").status_code == 200
    # The lift is itself a ledger row.
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM admin_actions WHERE action = 'unbar' "
                "AND target_user_id = %s", (member,))
    assert cur.fetchone()[0] == 1
    cur.close()


def test_cli_ban_refuses_purchase_and_creation_then_unban_restores(client, db):
    owner = TEST_PREFIX + "C3-owner"
    c = _create(client, owner, TEST_PREFIX + "CliBan")
    cid = c["id"]
    baduser = TEST_PREFIX + "C3-bad"
    _seed_level(baduser)
    # Before the ban the user can buy.
    assert _buy_pass(client, cid, baduser, "pre").status_code == 200
    # Admin bans via the CLI.
    rc, out = _cli("--actor", "LEAD", "ban", baduser, "abuse")
    assert rc == 0, out
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM service_bans WHERE user_id = %s "
                "AND lifted_at IS NULL", (baduser,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM admin_actions WHERE action = 'ban' "
                "AND target_user_id = %s", (baduser,))
    assert cur.fetchone()[0] == 1
    cur.close()
    # A banned user's PURCHASE is refused.
    r = _buy_pass(client, cid, baduser, "postban")
    assert r.status_code == 403, r.get_json()
    assert r.get_json()["error"] == "banned"
    # A banned user's community CREATION is refused.
    rc2 = client.post("/communities",
                      json={"owner_user_id": baduser,
                            "name": TEST_PREFIX + "BannedCreate",
                            "visibility": "private",
                            "pass_products": [
                                {"product_id": "audioura.pass.usd5",
                                 "length": "month"}]},
                      headers=GW)
    assert rc2.status_code == 403
    assert rc2.get_json()["error"] == "banned"
    # Downloaded audio is never touched — the membership row still exists.
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_memberships WHERE user_id = %s",
                (baduser,))
    assert cur.fetchone()[0] == 1, "a ban must never delete a purchase/membership"
    cur.close()
    # Unban restores purchasing.
    assert _cli("unban", baduser)[0] == 0
    assert _buy_pass(client, cid, baduser, "afterunban").status_code == 200


def test_cli_reports_and_log_render(client):
    owner = TEST_PREFIX + "C4-owner"
    c = _create(client, owner, TEST_PREFIX + "CliReports")
    cid = c["id"]
    client.post(f"/communities/{cid}/report",
                json={"user_id": TEST_PREFIX + "C4-r", "reason": "spam",
                      "detail": "x"}, headers=GW)
    rc, out = _cli("reports")
    assert rc == 0, out
    assert "Community reports" in out and str(cid) in out
    # A bar then shows in the ledger view.
    _cli("bar", str(cid), TEST_PREFIX + "C4-m", "r")
    rc2, out2 = _cli("log")
    assert rc2 == 0
    assert "bar" in out2


def test_disable_and_enable_community_via_cli(client, db):
    owner = TEST_PREFIX + "C5-owner"
    c = _create(client, owner, TEST_PREFIX + "CliDisable")
    cid = c["id"]
    assert _cli("disable", str(cid), "policy")[0] == 0
    cur = db.cursor()
    cur.execute("SELECT disabled FROM communities WHERE id = %s", (cid,))
    assert cur.fetchone()[0] is True
    cur.close()
    # The code now resolves to not_found/closed for a new member.
    r = client.get(f"/communities/{cid}", headers=GW)
    assert r.get_json()["disabled"] is True
    assert _cli("enable", str(cid))[0] == 0
    cur = db.cursor()
    cur.execute("SELECT disabled FROM communities WHERE id = %s", (cid,))
    assert cur.fetchone()[0] is False
    cur.close()


# ─── RED ──────────────────────────────────────────────────────────────────────

def test_red_broken_ban_gate_lets_banned_user_buy(client, modules, db):
    """The green guarantee (test_cli_ban_...) is that a banned user's purchase
    is refused. This forces the real gate is_user_service_banned to always
    return False (the pre-728 state) and shows the banned user DOES buy (200) —
    so the 'refused with 403 banned' assertion then FAILS, proving it is not
    vacuous."""
    ca = modules["ca"]
    owner = TEST_PREFIX + "RED-owner"
    c = _create(client, owner, TEST_PREFIX + "RedBan")
    cid = c["id"]
    baduser = TEST_PREFIX + "RED-bad"
    _seed_level(baduser)
    assert _cli("ban", baduser, "abuse")[0] == 0
    orig = ca.is_user_service_banned
    ca.is_user_service_banned = lambda cur, user_id: False
    try:
        r = _buy_pass(client, cid, baduser, "redbuy")
        with pytest.raises(AssertionError):
            assert r.status_code == 403, "a working ban refuses the purchase"
    finally:
        ca.is_user_service_banned = orig


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
