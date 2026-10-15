"""
LOCAL-700 — Communities UX round 1 server tests (D657 / D658 + addenda).

Three server rules this ticket adds to communities_api.py:
  * GET /communities/name-available?name= — case- AND space-insensitive, trimmed
    uniqueness check; a disabled community does not reserve its name.
  * POST /communities — the create gate: the owner must be on the free plan or
    above (device_entitlement.level != 'l1' Introduction), else 403
    plan_required; a duplicate name is 409 name_taken.
  * POST /communities/<id>/regenerate-code — owner only; the OLD code stops
    working (by-code → 404) and the NEW code resolves.

DB-backed, in-process Flask client (the communities + entitlements blueprints),
stub IAP mode, exactly like test_local690_communities.py. Every row uses the
'TEST-700-' prefix; cleanup touches only those rows (communities by name prefix,
their children, purchases + device_entitlement by user-id prefix).
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

TEST_PREFIX = "TEST-700-"


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    """Own this module's entitlements env and restore it afterwards (mirrors
    test_local690_communities._isolate_entitlements_env): other modules set
    GATEWAY_API_KEY / IAP_VERIFY_MODE at import and never restore them."""
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
    ea = _load_module("entitlements_api_700", "user-tracking/entitlements_api.py")
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
        for tbl in ("community_reports", "community_episodes", "community_passes",
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
    """Create a community for an owner seeded at `level` (default l2 Free so the
    create passes the plan gate). Pass level=None to skip seeding (owner stays
    Introduction/l1 → the gate refuses)."""
    if level is not None:
        _seed_level(owner, level)
    body = {"owner_user_id": owner, "name": name}
    body.update(overrides)
    return client.post("/communities", json=body)


# ─── §4: name-available (case/space-insensitive) ────────────────────────────────

def test_name_available_true_for_free_name(client):
    r = client.get("/communities/name-available",
                   query_string={"name": TEST_PREFIX + "Totally Free Name"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["available"] is True
    assert j["name"] == TEST_PREFIX + "Totally Free Name"


def test_name_available_false_once_taken(client):
    name = TEST_PREFIX + "The Wandering Owls"
    assert _create(client, TEST_PREFIX + "owner-a", name).status_code == 201
    r = client.get("/communities/name-available", query_string={"name": name})
    assert r.status_code == 200
    assert r.get_json()["available"] is False


def test_name_available_is_case_and_space_insensitive(client):
    _create(client, TEST_PREFIX + "owner-b", TEST_PREFIX + "Night  Owls")
    # Different case AND different inner spacing collide with the stored name.
    # (The stored name is "TEST-700-Night  Owls"; each variant keeps the same
    # tokens — prefix, Night, Owls — so only case/spacing differs.)
    variants = [
        TEST_PREFIX + "Night owls",
        TEST_PREFIX + "NIGHT OWLS",
        TEST_PREFIX + "Night   Owls  ",
    ]
    for v in variants:
        r = client.get("/communities/name-available", query_string={"name": v})
        assert r.status_code == 200, v
        assert r.get_json()["available"] is False, v


def test_name_available_blank_name_is_unavailable(client):
    r = client.get("/communities/name-available", query_string={"name": "   "})
    assert r.status_code == 200
    assert r.get_json()["available"] is False


def test_disabled_community_does_not_reserve_name(client, db):
    name = TEST_PREFIX + "Reusable Name"
    cid = _create(client, TEST_PREFIX + "owner-c", name).get_json()["id"]
    cur = db.cursor()
    cur.execute("UPDATE communities SET disabled = TRUE WHERE id = %s", (cid,))
    db.commit()
    cur.close()
    r = client.get("/communities/name-available", query_string={"name": name})
    assert r.get_json()["available"] is True


# ─── §3: plan gate on create (403 plan_required) ────────────────────────────────

def test_create_refused_for_introduction_level(client):
    # No entitlement row → default Introduction (l1) → refused.
    owner = TEST_PREFIX + "intro-owner"
    r = _create(client, owner, TEST_PREFIX + "Intro Tried", level=None)
    assert r.status_code == 403
    j = r.get_json()
    assert j["error"] == "plan_required"
    assert j["level"] == "l1"


def test_create_refused_for_explicit_l1(client):
    owner = TEST_PREFIX + "l1-owner"
    r = _create(client, owner, TEST_PREFIX + "L1 Tried", level="l1")
    assert r.status_code == 403
    assert r.get_json()["error"] == "plan_required"


def test_create_allowed_for_free_plan(client):
    owner = TEST_PREFIX + "free-owner"
    r = _create(client, owner, TEST_PREFIX + "Free Made It", level="l2")
    assert r.status_code == 201
    assert r.get_json()["name"] == TEST_PREFIX + "Free Made It"


def test_create_allowed_for_paid_plan(client):
    owner = TEST_PREFIX + "paid-owner"
    r = _create(client, owner, TEST_PREFIX + "Paid Made It", level="l4")
    assert r.status_code == 201


def test_create_duplicate_name_409(client):
    name = TEST_PREFIX + "Only One Of These"
    assert _create(client, TEST_PREFIX + "dup-a", name).status_code == 201
    # A different owner (also on a plan) cannot take the same name.
    r = _create(client, TEST_PREFIX + "dup-b", name)
    assert r.status_code == 409
    assert r.get_json()["error"] == "name_taken"


def test_create_duplicate_name_case_insensitive_409(client):
    _create(client, TEST_PREFIX + "ci-a", TEST_PREFIX + "Night Owls")
    r = _create(client, TEST_PREFIX + "ci-b", TEST_PREFIX + "night  owls")
    assert r.status_code == 409
    assert r.get_json()["error"] == "name_taken"


# ─── §4: regenerate code (owner only; old 404, new works) ───────────────────────

def test_regenerate_code_owner_only_old_dies_new_works(client):
    owner = TEST_PREFIX + "regen-owner"
    created = _create(client, owner, TEST_PREFIX + "Rotatable").get_json()
    cid = created["id"]
    old_code = created["join_code"]

    # The old code resolves before rotation.
    assert client.get(f"/communities/by-code/{old_code}").status_code == 200

    # A non-owner cannot rotate.
    rbad = client.post(f"/communities/{cid}/regenerate-code",
                       json={"owner_user_id": TEST_PREFIX + "not-owner"})
    assert rbad.status_code == 403

    # The owner rotates: a NEW code comes back, with a ready invite message.
    rok = client.post(f"/communities/{cid}/regenerate-code",
                      json={"owner_user_id": owner})
    assert rok.status_code == 200
    new_code = rok.get_json()["join_code"]
    assert new_code != old_code
    assert len(new_code) == 8 and any(c.isdigit() for c in new_code)
    assert new_code in rok.get_json()["invite_message"]

    # The OLD code no longer resolves; the NEW code does.
    assert client.get(f"/communities/by-code/{old_code}").status_code == 404
    assert client.get(f"/communities/by-code/{new_code}").status_code == 200


def test_regenerate_code_unknown_community_404(client):
    r = client.post("/communities/99999999/regenerate-code",
                    json={"owner_user_id": TEST_PREFIX + "nobody"})
    assert r.status_code == 404


def test_regenerate_code_requires_owner_user_id(client):
    owner = TEST_PREFIX + "regen-owner2"
    cid = _create(client, owner, TEST_PREFIX + "Rotatable2").get_json()["id"]
    r = client.post(f"/communities/{cid}/regenerate-code", json={})
    assert r.status_code == 400
