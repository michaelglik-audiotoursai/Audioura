"""
test_local702_organiser_steps_down.py — LOCAL-702 / D663 §1.

The organiser step-down state machine in communities_api.py. A community moves
active → handover → (active again | archived). Every transition is covered:

  (a) STEP DOWN            owner → handover; stays readable for members; refuses
                           new joins + pass sales (409 community_closed_to_new_
                           members); shows "Looking for a new organiser".
  (b) OFFER / PICK / ACCEPT a member volunteers, the owner picks one, the member
                           accepts → becomes owner, community reopens (active),
                           an organiser_terms acceptance is recorded (LOCAL-691).
  (c) ARCHIVE              no new organiser within 30 days → archived (the daily
                           tick); archived refuses new members too; members keep
                           their existing membership (downloads).
  (d) DELETE               a member-LESS community can be deleted by its owner; a
                           community WITH members cannot (409 has_members).

DB-backed, in-process Flask client (communities + entitlements blueprints), stub
IAP mode — the SAME harness as test_local700_communities_ux.py. Every row uses
the 'TEST-702-' prefix; cleanup touches only those rows.
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

TEST_PREFIX = "TEST-702-"


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
    ea = _load_module("entitlements_api_702", "user-tracking/entitlements_api.py")
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
    cur.execute("DELETE FROM document_acceptance WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _seed_level(user_id, level):
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


def _create(client, owner, name, level="l2", **overrides):
    _seed_level(owner, level)
    body = {"owner_user_id": owner, "name": name}
    # [LOCAL-704 / D665] Every community is paid and must offer a pass.
    if "pass_products" not in overrides:
        body["pass_products"] = [
            {"product_id": "audioura.pass.usd5", "length": "month"}]
    body.update(overrides)
    r = client.post("/communities", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _join_free(client, cid, user_id):
    """[LOCAL-704 / D665] Free join is gone — a member joins by buying a pass.
    Kept under the old name so the step-down tests read unchanged; it now does a
    stub pass purchase through /purchases/verify."""
    return client.post("/purchases/verify", json={
        "store": "stub",
        "transaction_id": TEST_PREFIX + f"txn-{user_id}-{cid}",
        "product": "audioura.pass.usd5", "length": "month",
        "user_id": user_id, "community_id": cid,
    })


def _set_stepped_down_days_ago(db, cid, days):
    """Backdate a community's stepped_down_at so the archive clock has elapsed."""
    cur = db.cursor()
    cur.execute(
        "UPDATE communities SET stepped_down_at = %s WHERE id = %s",
        (datetime.utcnow() - timedelta(days=days), cid),
    )
    db.commit()
    cur.close()


# ─── (a) STEP DOWN ──────────────────────────────────────────────────────────

def test_step_down_moves_active_to_handover(client):
    owner = TEST_PREFIX + "a-owner"
    c = _create(client, owner, TEST_PREFIX + "Steps Down A")
    assert c["status"] == "active"
    r = client.post(f"/communities/{c['id']}/step-down",
                    json={"owner_user_id": owner})
    assert r.status_code == 200
    j = r.get_json()
    assert j["status"] == "handover"
    assert j["looking_for_organiser"] is True
    assert j["accepts_new_members"] is False
    assert j["stepped_down_at"] is not None


def test_step_down_requires_owner(client):
    owner = TEST_PREFIX + "a-owner2"
    c = _create(client, owner, TEST_PREFIX + "Steps Down Owner Only")
    r = client.post(f"/communities/{c['id']}/step-down",
                    json={"owner_user_id": TEST_PREFIX + "stranger"})
    assert r.status_code == 403
    assert r.get_json()["error"] == "forbidden"


def test_step_down_unknown_community_404(client):
    r = client.post("/communities/99999999/step-down",
                    json={"owner_user_id": TEST_PREFIX + "nobody"})
    assert r.status_code == 404


def test_step_down_is_idempotent(client, db):
    owner = TEST_PREFIX + "a-idem"
    c = _create(client, owner, TEST_PREFIX + "Idem Step")
    r1 = client.post(f"/communities/{c['id']}/step-down", json={"owner_user_id": owner})
    assert r1.status_code == 200
    cur = db.cursor()
    cur.execute("SELECT stepped_down_at FROM communities WHERE id = %s", (c["id"],))
    first = cur.fetchone()[0]
    cur.close()
    # A second step-down must NOT reset the archive clock.
    r2 = client.post(f"/communities/{c['id']}/step-down", json={"owner_user_id": owner})
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "handover"
    cur = db.cursor()
    cur.execute("SELECT stepped_down_at FROM communities WHERE id = %s", (c["id"],))
    second = cur.fetchone()[0]
    cur.close()
    assert first == second


# ─── (a) CLOSED TO NEW MEMBERS (409) ────────────────────────────────────────

def test_handover_refuses_new_free_join_409(client):
    # [LOCAL-704 / D665] Free join is gone — it returns 402 pass_required for
    # every community (the handover 409 is covered by the pass-sale test below).
    owner = TEST_PREFIX + "a-closed"
    c = _create(client, owner, TEST_PREFIX + "Closed Free")
    client.post(f"/communities/{c['id']}/step-down", json={"owner_user_id": owner})
    r = _join_free(client, c["id"], TEST_PREFIX + "newcomer")
    # A pass buy on a handover community is refused with 409 (closed to new).
    assert r.status_code == 409
    assert r.get_json()["error"] == "community_closed_to_new_members"


def test_handover_refuses_new_pass_sale_409(client):
    owner = TEST_PREFIX + "a-paid"
    c = _create(client, owner, TEST_PREFIX + "Closed Paid", is_paid=True,
                pass_products=[{"product_id": "audioura.pass.usd5", "length": "month"}])
    client.post(f"/communities/{c['id']}/step-down", json={"owner_user_id": owner})
    r = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": TEST_PREFIX + "txn-closed",
        "product": "audioura.pass.usd5", "length": "month",
        "user_id": TEST_PREFIX + "paybuyer", "community_id": c["id"],
    })
    assert r.status_code == 409
    assert r.get_json()["error"] == "community_closed_to_new_members"


def test_existing_member_still_sees_page_in_handover(client):
    owner = TEST_PREFIX + "a-exist"
    c = _create(client, owner, TEST_PREFIX + "Member Stays")
    member = TEST_PREFIX + "early-member"
    assert _join_free(client, c["id"], member).status_code == 200
    # Owner adds an episode so the member has content to keep seeing.
    client.post(f"/communities/{c['id']}/episodes", json={
        "owner_user_id": owner,
        "episodes": [{"title": "Ep1", "audio_url": "https://o.example/1.mp3"}]})
    client.post(f"/communities/{c['id']}/step-down", json={"owner_user_id": owner})
    # The existing member still reads the page AND the episode list.
    r = client.get(f"/communities/{c['id']}", query_string={"user_id": member})
    assert r.status_code == 200
    j = r.get_json()
    assert j["status"] == "handover"
    assert j["looking_for_organiser"] is True
    assert len(j["episodes"]) == 1


# ─── (b) OFFER / PICK / ACCEPT (the hand-over) ──────────────────────────────

def test_full_handover_offer_pick_accept_reopens(client, db):
    owner = TEST_PREFIX + "b-owner"
    c = _create(client, owner, TEST_PREFIX + "Full Handover")
    cid = c["id"]
    member = TEST_PREFIX + "b-member"
    assert _join_free(client, cid, member).status_code == 200
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})

    # Member volunteers.
    r = client.post(f"/communities/{cid}/offer-organiser", json={"user_id": member})
    assert r.status_code == 200
    assert r.get_json()["my_offer"]["status"] == "offered"

    # Owner sees the volunteer and picks them.
    page = client.get(f"/communities/{cid}", query_string={"user_id": owner}).get_json()
    assert any(o["member_user_id"] == member for o in page["organiser_offers"])
    rp = client.post(f"/communities/{cid}/pick-organiser",
                     json={"owner_user_id": owner, "member_user_id": member})
    assert rp.status_code == 200

    # The picked member sees they were picked.
    mp = client.get(f"/communities/{cid}", query_string={"user_id": member}).get_json()
    assert mp["my_offer"]["picked"] is True

    # Member accepts → becomes owner, community reopens.
    ra = client.post(f"/communities/{cid}/accept-organiser", json={"user_id": member})
    assert ra.status_code == 200
    j = ra.get_json()
    assert j["status"] == "active"
    assert j["looking_for_organiser"] is False
    assert j["is_owner"] is True  # the member is now the owner

    # Ownership really transferred, clock cleared.
    cur = db.cursor()
    cur.execute("SELECT owner_user_id, status, stepped_down_at FROM communities WHERE id = %s", (cid,))
    row = cur.fetchone()
    cur.close()
    assert row[0] == member and row[1] == "active" and row[2] is None

    # [LOCAL-691] The organiser terms acceptance was recorded (checked directly
    # in the DB; the document-acceptance HTTP surface is a separate blueprint).
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM document_acceptance "
        "WHERE user_id = %s AND document = 'organiser_terms'", (member,))
    assert cur.fetchone()[0] >= 1
    cur.close()

    # Reopened: a NEW member can join again.
    assert _join_free(client, cid, TEST_PREFIX + "post-reopen").status_code == 200


def test_offer_refused_when_not_in_handover(client):
    owner = TEST_PREFIX + "b-active"
    c = _create(client, owner, TEST_PREFIX + "No Offer Active")
    r = client.post(f"/communities/{c['id']}/offer-organiser",
                    json={"user_id": TEST_PREFIX + "eager"})
    assert r.status_code == 409
    assert r.get_json()["error"] == "not_in_handover"


def test_pick_requires_owner(client):
    owner = TEST_PREFIX + "b-pickowner"
    c = _create(client, owner, TEST_PREFIX + "Pick Owner Only")
    cid = c["id"]
    member = TEST_PREFIX + "b-pm"
    _join_free(client, cid, member)
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    client.post(f"/communities/{cid}/offer-organiser", json={"user_id": member})
    r = client.post(f"/communities/{cid}/pick-organiser",
                    json={"owner_user_id": TEST_PREFIX + "imposter",
                          "member_user_id": member})
    assert r.status_code == 403


def test_pick_unknown_volunteer_404(client):
    owner = TEST_PREFIX + "b-nov"
    c = _create(client, owner, TEST_PREFIX + "Pick No Volunteer")
    cid = c["id"]
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    r = client.post(f"/communities/{cid}/pick-organiser",
                    json={"owner_user_id": owner,
                          "member_user_id": TEST_PREFIX + "never-offered"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "no_such_offer"


def test_accept_refused_when_not_picked(client):
    owner = TEST_PREFIX + "b-notpicked"
    c = _create(client, owner, TEST_PREFIX + "Accept Not Picked")
    cid = c["id"]
    member = TEST_PREFIX + "b-np"
    _join_free(client, cid, member)
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    client.post(f"/communities/{cid}/offer-organiser", json={"user_id": member})
    # No pick yet → accept is refused.
    r = client.post(f"/communities/{cid}/accept-organiser", json={"user_id": member})
    assert r.status_code == 403
    assert r.get_json()["error"] == "not_picked"


def test_pick_supersedes_previous_pick(client, db):
    owner = TEST_PREFIX + "b-super"
    c = _create(client, owner, TEST_PREFIX + "Pick Supersede")
    cid = c["id"]
    m1 = TEST_PREFIX + "vol1"
    m2 = TEST_PREFIX + "vol2"
    for m in (m1, m2):
        _join_free(client, cid, m)
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    client.post(f"/communities/{cid}/offer-organiser", json={"user_id": m1})
    client.post(f"/communities/{cid}/offer-organiser", json={"user_id": m2})
    client.post(f"/communities/{cid}/pick-organiser",
                json={"owner_user_id": owner, "member_user_id": m1})
    # Owner changes their mind and picks m2.
    client.post(f"/communities/{cid}/pick-organiser",
                json={"owner_user_id": owner, "member_user_id": m2})
    cur = db.cursor()
    cur.execute("SELECT member_user_id FROM community_organiser_offers "
                "WHERE community_id = %s AND status = 'picked'", (cid,))
    picked = [r[0] for r in cur.fetchall()]
    cur.close()
    assert picked == [m2]  # exactly one picked, and it is m2


def test_withdraw_offer(client):
    owner = TEST_PREFIX + "b-wd"
    c = _create(client, owner, TEST_PREFIX + "Withdraw")
    cid = c["id"]
    member = TEST_PREFIX + "b-wdm"
    _join_free(client, cid, member)
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    client.post(f"/communities/{cid}/offer-organiser", json={"user_id": member})
    r = client.post(f"/communities/{cid}/withdraw-offer", json={"user_id": member})
    assert r.status_code == 200
    # The owner no longer sees them as a live volunteer.
    page = client.get(f"/communities/{cid}", query_string={"user_id": owner}).get_json()
    assert all(o["member_user_id"] != member for o in page.get("organiser_offers", []))


# ─── (c) ARCHIVE after 30 days ──────────────────────────────────────────────

def test_archive_tick_archives_after_30_days(client, db):
    owner = TEST_PREFIX + "c-owner"
    c = _create(client, owner, TEST_PREFIX + "Archive Me")
    cid = c["id"]
    _join_free(client, cid, TEST_PREFIX + "c-member")
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    _set_stepped_down_days_ago(db, cid, 31)
    r = client.post("/communities/archive/run")
    assert r.status_code == 200
    assert cid in r.get_json()["archived"]
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": TEST_PREFIX + "c-member"}).get_json()
    assert page["status"] == "archived"
    assert page["archived"] is True
    assert page["archived_at"] is not None


def test_archive_tick_leaves_recent_handover(client, db):
    owner = TEST_PREFIX + "c-recent"
    c = _create(client, owner, TEST_PREFIX + "Still Looking")
    cid = c["id"]
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    _set_stepped_down_days_ago(db, cid, 10)  # under 30 days
    r = client.post("/communities/archive/run")
    assert r.status_code == 200
    assert cid not in r.get_json()["archived"]
    page = client.get(f"/communities/{cid}", query_string={"user_id": owner}).get_json()
    assert page["status"] == "handover"


def test_archive_tick_is_idempotent(client, db):
    owner = TEST_PREFIX + "c-idem"
    c = _create(client, owner, TEST_PREFIX + "Archive Idem")
    cid = c["id"]
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    _set_stepped_down_days_ago(db, cid, 40)
    first = client.post("/communities/archive/run").get_json()
    assert cid in first["archived"]
    second = client.post("/communities/archive/run").get_json()
    assert cid not in second["archived"]  # already archived — not touched again


def test_archived_refuses_new_members(client, db):
    owner = TEST_PREFIX + "c-closed"
    c = _create(client, owner, TEST_PREFIX + "Archived Closed")
    cid = c["id"]
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    _set_stepped_down_days_ago(db, cid, 31)
    client.post("/communities/archive/run")
    r = _join_free(client, cid, TEST_PREFIX + "too-late")
    assert r.status_code == 409
    assert r.get_json()["error"] == "community_closed_to_new_members"


def test_cannot_step_down_an_archived_community(client, db):
    owner = TEST_PREFIX + "c-nostep"
    c = _create(client, owner, TEST_PREFIX + "Archived No Step")
    cid = c["id"]
    client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    _set_stepped_down_days_ago(db, cid, 31)
    client.post("/communities/archive/run")
    r = client.post(f"/communities/{cid}/step-down", json={"owner_user_id": owner})
    assert r.status_code == 409
    assert r.get_json()["error"] == "already_archived"


# ─── (d) DELETE a member-less community (D663 §1 d) ─────────────────────────

def test_owner_deletes_memberless_community(client, db):
    owner = TEST_PREFIX + "d-empty"
    c = _create(client, owner, TEST_PREFIX + "Delete Me Empty")
    cid = c["id"]
    r = client.delete(f"/communities/{cid}", json={"owner_user_id": owner})
    assert r.status_code == 200
    assert r.get_json()["deleted"] is True
    cur = db.cursor()
    cur.execute("SELECT 1 FROM communities WHERE id = %s", (cid,))
    assert cur.fetchone() is None
    cur.close()


def test_delete_refused_when_members_exist(client):
    owner = TEST_PREFIX + "d-full"
    c = _create(client, owner, TEST_PREFIX + "Delete With Members")
    cid = c["id"]
    _join_free(client, cid, TEST_PREFIX + "d-member")
    r = client.delete(f"/communities/{cid}", json={"owner_user_id": owner})
    assert r.status_code == 409
    assert r.get_json()["error"] == "has_members"


def test_delete_requires_owner(client):
    owner = TEST_PREFIX + "d-owneronly"
    c = _create(client, owner, TEST_PREFIX + "Delete Owner Only")
    r = client.delete(f"/communities/{c['id']}",
                      json={"owner_user_id": TEST_PREFIX + "not-owner"})
    assert r.status_code == 403


def test_delete_unknown_community_404(client):
    r = client.delete("/communities/99999999",
                      json={"owner_user_id": TEST_PREFIX + "nobody"})
    assert r.status_code == 404
