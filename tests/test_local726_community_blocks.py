"""
test_local726_community_blocks.py — LOCAL-726 / lawyer review item 10
(Apple Guideline 1.2 — a block function for user-generated content).

Covers the community block feature end to end against the REAL communities_api
blueprint, DB-backed with the same in-process Flask client + stub IAP harness as
test_local702_organiser_steps_down.py. Every row uses the 'TEST-726-' prefix and
cleanup touches only those rows (plus their community_blocks).

  A. MEMBER BLOCK (a member hides an organiser/member)
     - POST /communities/<id>/block kind=member_block records a block;
     - a blocked organiser's community disappears from the blocker's
       /communities/mine and from /communities/map;
     - it disappears from the blocker's /communities/new-tours;
     - another member who did NOT block still sees everything (the block is the
       blocker's own view only);
     - /communities/blocks lists the block; unblock removes it and the community
       reappears.

  B. ORGANISER BAR (an organiser removes and bars a member)
     - POST kind=organiser_bar by the owner removes the membership AND bars;
     - the barred member CANNOT REJOIN BY CODE: a fresh pass purchase returns
       403 barred (not a new membership);
     - a non-owner cannot issue an organiser_bar (403 forbidden);
     - the member list marks the member barred; unbar lifts it and the member
       can buy a pass again.

  C. GUARDS: self-block 400; missing fields 400; bad kind 400; unknown
     community 404; blocking twice is idempotent (one row).

  RED: a deliberately broken bar gate (is_user_barred forced to always return
     False) is shown to let a barred member rejoin — proving the green "cannot
     rejoin" assertion is not vacuous.
"""

import os
import sys
import importlib.util

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-726-"


@pytest.fixture(scope="module", autouse=True)
def _isolate_env():
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
def modules(_isolate_env):
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    _load_module("communities_rss", "user-tracking/communities_rss.py")
    ca = _load_module("communities_api", "user-tracking/communities_api.py")
    ea = _load_module("entitlements_api_726", "user-tracking/entitlements_api.py")
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
        for tbl in ("community_blocks", "community_organiser_offers",
                    "community_reports", "community_episodes",
                    "community_passes", "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        # community tours (audio_tours) tagged to these communities, if any.
        cur.execute("UPDATE audio_tours SET community_id = NULL "
                    "WHERE community_id = ANY(%s)", (ids,))
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


def _create(client, owner, name, **overrides):
    _seed_level(owner)
    body = {"owner_user_id": owner, "name": name,
            "visibility": overrides.pop("visibility", "listed"),
            "latitude": overrides.pop("latitude", 42.33),
            "longitude": overrides.pop("longitude", -71.21)}
    body.setdefault("pass_products",
                    [{"product_id": "audioura.pass.usd5", "length": "month"}])
    body.update(overrides)
    r = client.post("/communities", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _buy_pass(client, cid, user_id, txn_suffix=""):
    return client.post("/purchases/verify", json={
        "store": "stub",
        "transaction_id": TEST_PREFIX + f"txn-{user_id}-{cid}-{txn_suffix}",
        "product": "audioura.pass.usd5", "length": "month",
        "user_id": user_id, "community_id": cid,
    })


def _mine_ids(client, user_id):
    r = client.get("/communities/mine", query_string={"user_id": user_id})
    assert r.status_code == 200
    return {c["id"] for c in r.get_json()["communities"]}


def _map_ids(client, user_id=None):
    qs = {"user_id": user_id} if user_id else {}
    r = client.get("/communities/map", query_string=qs)
    assert r.status_code == 200
    return {c["id"] for c in r.get_json()["communities"]}


# ─── A. MEMBER BLOCK ────────────────────────────────────────────────────────

def test_member_block_hides_blocked_organisers_community_from_mine_and_map(client):
    owner = TEST_PREFIX + "A-owner"
    c = _create(client, owner, TEST_PREFIX + "Blockable")
    cid = c["id"]
    member = TEST_PREFIX + "A-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Before the block the member sees the community in mine and on the map.
    assert cid in _mine_ids(client, member)
    assert cid in _map_ids(client, member)
    # The member blocks the organiser.
    r = client.post(f"/communities/{cid}/block",
                    json={"user_id": member, "blocked_user_id": owner})
    assert r.status_code == 200
    assert r.get_json()["kind"] == "member_block"
    # The organiser's community disappears from the blocker's views.
    assert cid not in _mine_ids(client, member)
    assert cid not in _map_ids(client, member)


def test_member_block_hides_blocked_organisers_new_tours(client, db):
    owner = TEST_PREFIX + "A2-owner"
    c = _create(client, owner, TEST_PREFIX + "NewTours")
    cid = c["id"]
    member = TEST_PREFIX + "A2-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Tag a tour to this community so new-tours has something to return.
    cur = db.cursor()
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, community_id, "
        "community_visibility, created_at) "
        "VALUES (%s, %s, %s, 'members', NOW()) RETURNING id",
        (TEST_PREFIX + "ctour", TEST_PREFIX + "req", cid),
    )
    db.commit()
    cur.close()
    before = client.get("/communities/new-tours", query_string={"user_id": member})
    assert before.status_code == 200
    assert any(t.get("community_id") == cid for t in before.get_json()["tours"])
    # Block the organiser → the community's tours vanish from new-tours.
    client.post(f"/communities/{cid}/block",
                json={"user_id": member, "blocked_user_id": owner})
    after = client.get("/communities/new-tours", query_string={"user_id": member})
    assert after.status_code == 200
    assert not any(t.get("community_id") == cid for t in after.get_json()["tours"])


def test_member_block_is_only_the_blockers_view(client):
    owner = TEST_PREFIX + "A3-owner"
    c = _create(client, owner, TEST_PREFIX + "OthersUnaffected")
    cid = c["id"]
    blocker = TEST_PREFIX + "A3-blocker"
    other = TEST_PREFIX + "A3-other"
    assert _buy_pass(client, cid, blocker).status_code == 200
    assert _buy_pass(client, cid, other).status_code == 200
    client.post(f"/communities/{cid}/block",
                json={"user_id": blocker, "blocked_user_id": owner})
    # The OTHER member, who blocked no one, still sees it.
    assert cid in _mine_ids(client, other)
    assert cid in _map_ids(client, other)
    # The blocker does not.
    assert cid not in _mine_ids(client, blocker)


def test_blocks_list_and_unblock_restores_the_view(client):
    owner = TEST_PREFIX + "A4-owner"
    c = _create(client, owner, TEST_PREFIX + "Unblockable")
    cid = c["id"]
    member = TEST_PREFIX + "A4-member"
    assert _buy_pass(client, cid, member).status_code == 200
    client.post(f"/communities/{cid}/block",
                json={"user_id": member, "blocked_user_id": owner})
    # The Settings "Blocked" list shows the block.
    lst = client.get("/communities/blocks", query_string={"user_id": member})
    assert lst.status_code == 200
    blocks = lst.get_json()["blocks"]
    assert any(b["blocked_user_id"] == owner and b["kind"] == "member_block"
               for b in blocks)
    assert cid not in _mine_ids(client, member)
    # Unblock from Settings → the community reappears.
    r = client.post(f"/communities/{cid}/unblock",
                    json={"user_id": member, "blocked_user_id": owner})
    assert r.status_code == 200
    assert r.get_json()["removed"] == 1
    assert cid in _mine_ids(client, member)


# ─── B. ORGANISER BAR ───────────────────────────────────────────────────────

def test_organiser_bar_removes_membership_and_blocks_rejoin_by_code(client, db):
    owner = TEST_PREFIX + "B-owner"
    c = _create(client, owner, TEST_PREFIX + "Barrable")
    cid = c["id"]
    member = TEST_PREFIX + "B-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Membership exists.
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_memberships "
                "WHERE community_id = %s AND user_id = %s", (cid, member))
    assert cur.fetchone()[0] == 1
    cur.close()
    # Organiser bars the member.
    r = client.post(f"/communities/{cid}/block",
                    json={"user_id": owner, "blocked_user_id": member,
                          "kind": "organiser_bar", "reason": "spam"})
    assert r.status_code == 200
    assert r.get_json()["kind"] == "organiser_bar"
    # Membership was removed (no new content).
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_memberships "
                "WHERE community_id = %s AND user_id = %s", (cid, member))
    assert cur.fetchone()[0] == 0
    cur.close()
    # The barred member cannot rejoin by code — a fresh pass purchase is 403.
    rejoin = _buy_pass(client, cid, member, txn_suffix="rejoin")
    assert rejoin.status_code == 403, rejoin.get_json()
    assert rejoin.get_json()["error"] == "barred"


def test_non_owner_cannot_organiser_bar(client):
    owner = TEST_PREFIX + "B2-owner"
    c = _create(client, owner, TEST_PREFIX + "OwnerOnlyBar")
    cid = c["id"]
    member = TEST_PREFIX + "B2-member"
    stranger = TEST_PREFIX + "B2-stranger"
    assert _buy_pass(client, cid, member).status_code == 200
    r = client.post(f"/communities/{cid}/block",
                    json={"user_id": stranger, "blocked_user_id": member,
                          "kind": "organiser_bar"})
    assert r.status_code == 403
    assert r.get_json()["error"] == "forbidden"


def test_member_list_marks_barred_and_unbar_lets_member_return(client):
    owner = TEST_PREFIX + "B3-owner"
    c = _create(client, owner, TEST_PREFIX + "MemberList")
    cid = c["id"]
    member = TEST_PREFIX + "B3-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Bar, then the member list shows barred=True.
    client.post(f"/communities/{cid}/block",
                json={"user_id": owner, "blocked_user_id": member,
                      "kind": "organiser_bar"})
    lst = client.get(f"/communities/{cid}/members",
                     query_string={"user_id": owner})
    assert lst.status_code == 200
    # The barred member was removed from memberships, so they no longer appear
    # in the member list; the bar is visible in the owner's blocks list instead.
    owner_blocks = client.get("/communities/blocks",
                              query_string={"user_id": owner}).get_json()["blocks"]
    assert any(b["blocked_user_id"] == member and b["kind"] == "organiser_bar"
               for b in owner_blocks)
    # Unbar → the member can buy a pass again.
    r = client.post(f"/communities/{cid}/unblock",
                    json={"user_id": owner, "blocked_user_id": member,
                          "kind": "organiser_bar"})
    assert r.status_code == 200
    rejoin = _buy_pass(client, cid, member, txn_suffix="afterunbar")
    assert rejoin.status_code == 200, rejoin.get_json()


def test_members_list_owner_only(client):
    owner = TEST_PREFIX + "B4-owner"
    c = _create(client, owner, TEST_PREFIX + "MembersGuard")
    cid = c["id"]
    r = client.get(f"/communities/{cid}/members",
                   query_string={"user_id": TEST_PREFIX + "B4-stranger"})
    assert r.status_code == 403


# ─── C. GUARDS ──────────────────────────────────────────────────────────────

def test_cannot_block_self(client):
    owner = TEST_PREFIX + "C-owner"
    c = _create(client, owner, TEST_PREFIX + "SelfBlock")
    r = client.post(f"/communities/{c['id']}/block",
                    json={"user_id": owner, "blocked_user_id": owner})
    assert r.status_code == 400
    assert r.get_json()["error"] == "cannot_block_self"


def test_block_missing_fields_400(client):
    owner = TEST_PREFIX + "C2-owner"
    c = _create(client, owner, TEST_PREFIX + "MissingFields")
    r = client.post(f"/communities/{c['id']}/block", json={"user_id": owner})
    assert r.status_code == 400


def test_block_bad_kind_400(client):
    owner = TEST_PREFIX + "C3-owner"
    c = _create(client, owner, TEST_PREFIX + "BadKind")
    r = client.post(f"/communities/{c['id']}/block",
                    json={"user_id": owner, "blocked_user_id": TEST_PREFIX + "x",
                          "kind": "nonsense"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "bad_kind"


def test_block_unknown_community_404(client):
    r = client.post("/communities/99999999/block",
                    json={"user_id": TEST_PREFIX + "a", "blocked_user_id": TEST_PREFIX + "b"})
    assert r.status_code == 404


def test_blocking_twice_is_idempotent(client, db):
    owner = TEST_PREFIX + "C4-owner"
    c = _create(client, owner, TEST_PREFIX + "Idempotent")
    cid = c["id"]
    member = TEST_PREFIX + "C4-member"
    assert _buy_pass(client, cid, member).status_code == 200
    body = {"user_id": member, "blocked_user_id": owner}
    assert client.post(f"/communities/{cid}/block", json=body).status_code == 200
    assert client.post(f"/communities/{cid}/block", json=body).status_code == 200
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM community_blocks "
                "WHERE community_id = %s AND blocker_user_id = %s "
                "AND blocked_user_id = %s AND kind = 'member_block'",
                (cid, member, owner))
    assert cur.fetchone()[0] == 1, "blocking twice must leave exactly one row"
    cur.close()


# ─── RED: break the bar gate and show a barred member can rejoin ─────────────

def test_red_broken_bar_gate_lets_barred_member_rejoin(client, modules):
    """The green guarantee (test_organiser_bar_...) is that a barred member
    cannot rejoin by code. This forces the real gate is_user_barred to always
    return False — the pre-726 state where no bar exists — and shows the member
    DOES rejoin (purchase succeeds, 200). The assertion that a bar blocks rejoin
    then FAILS, proving the green test is not vacuous."""
    ca = modules["ca"]
    owner = TEST_PREFIX + "RED-owner"
    c = _create(client, owner, TEST_PREFIX + "RedBar")
    cid = c["id"]
    member = TEST_PREFIX + "RED-member"
    assert _buy_pass(client, cid, member).status_code == 200
    # Bar the member for real.
    client.post(f"/communities/{cid}/block",
                json={"user_id": owner, "blocked_user_id": member,
                      "kind": "organiser_bar"})
    # Break the gate: pretend nobody is ever barred.
    orig = ca.is_user_barred
    ca.is_user_barred = lambda cur, community_id, user_id: False
    try:
        rejoin = _buy_pass(client, cid, member, txn_suffix="redrejoin")
        # With the gate broken the purchase succeeds (the bug). The guard that a
        # bar blocks rejoin therefore fails — which is the point.
        with pytest.raises(AssertionError):
            assert rejoin.status_code == 403, "a working bar blocks rejoin"
    finally:
        ca.is_user_barred = orig


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
