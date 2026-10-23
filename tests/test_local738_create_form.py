"""
LOCAL-738 — Community create-form server rules (Michael's review C2/C2b/C2c).

Two server rules this ticket adds to communities_api.py:
  * GET /communities/pass-prices — the allowed pass PRICES for a NEW community,
    in price order, built from the single APPLE_LIVE_PASS_PRODUCTS list crossed
    with the catalogue. The app's price chips come from here (no second copy).
  * POST /communities — now accepts and stores release_cadence (day|week|month|
    year, default 'week'); the community page payload returns it. A bad cadence
    is 400 bad_release_cadence.

DB-backed, in-process Flask client (communities + entitlements blueprints), stub
IAP mode, mirroring test_local700_communities_ux.py. Every row uses the
'TEST-738-' prefix; cleanup touches only those rows.

Requires migration 048 (communities.release_cadence) applied to audiotours_test.
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

TEST_PREFIX = "TEST-738-"


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
    ea = _load_module("entitlements_api_738", "user-tracking/entitlements_api.py")
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
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


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
    _seed_level(owner, "l2")
    body = {"owner_user_id": owner, "name": name,
            "pass_products": [{"product_id": "audioura.pass.usd1", "length": "month"}]}
    body.update(overrides)
    return client.post("/communities", json=body)


# ─── §2: pass-prices matches APPLE_LIVE_PASS_PRODUCTS ───────────────────────────

def test_pass_prices_matches_apple_live_products(client, modules):
    r = client.get("/communities/pass-prices")
    assert r.status_code == 200
    prices = r.get_json()["prices"]
    ids = {p["product_id"] for p in prices}
    assert ids == set(modules["ca"].APPLE_LIVE_PASS_PRODUCTS)
    # Every row carries a price and a label.
    for p in prices:
        assert isinstance(p["price_usd"], (int, float))
        assert p["label"]


def test_pass_prices_in_ascending_price_order(client):
    r = client.get("/communities/pass-prices")
    prices = r.get_json()["prices"]
    amounts = [p["price_usd"] for p in prices]
    assert amounts == sorted(amounts)


def test_pass_prices_excludes_off_list_products(client, modules):
    # $15 is NOT in APPLE_LIVE_PASS_PRODUCTS → never offered to the organiser.
    r = client.get("/communities/pass-prices")
    ids = {p["product_id"] for p in r.get_json()["prices"]}
    assert "audioura.pass.usd15" not in ids


# ─── §4 (C2c): create stores release_cadence (default week) ─────────────────────

def test_create_defaults_release_cadence_to_week(client):
    r = _create(client, TEST_PREFIX + "owner-def", TEST_PREFIX + "Default Cadence")
    assert r.status_code == 201
    assert r.get_json()["release_cadence"] == "week"


def test_create_stores_chosen_release_cadence(client):
    r = _create(client, TEST_PREFIX + "owner-mo", TEST_PREFIX + "Monthly Cadence",
                release_cadence="month")
    assert r.status_code == 201
    cid = r.get_json()["id"]
    assert r.get_json()["release_cadence"] == "month"
    # The community page payload returns it too.
    page = client.get(f"/communities/{cid}")
    assert page.status_code == 200
    assert page.get_json()["release_cadence"] == "month"


def test_create_rejects_bad_release_cadence(client):
    r = _create(client, TEST_PREFIX + "owner-bad", TEST_PREFIX + "Bad Cadence",
                release_cadence="fortnight")
    assert r.status_code == 400
    assert r.get_json()["error"] == "bad_release_cadence"


# ─── §2 (C2): an off-list pass price is refused with the real error ─────────────

def test_create_refuses_off_list_pass_price(client):
    # The exact failure from Michael's phone: a $15 product the stores lack.
    r = _create(client, TEST_PREFIX + "owner-15", TEST_PREFIX + "Fifteen Dollar",
                pass_products=[{"product_id": "audioura.pass.usd15",
                                "length": "year"}])
    assert r.status_code == 400
    assert r.get_json()["error"] == "pass_product_not_available"
    # The message names the allowed prices (the form shows this real message).
    assert "$1" in r.get_json()["message"] or "1" in r.get_json()["message"]
