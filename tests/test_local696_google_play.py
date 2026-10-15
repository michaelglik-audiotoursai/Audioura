"""
test_local696_google_play.py — LOCAL-696: end-to-end tests for the Google Play
purchase path through /purchases/verify, plus the voided-purchases poller
reversing a grant, against the test DB.

Harness mirrors tests/test_local677_paid_tours.py: an in-process Flask client for
the entitlements blueprint (user-tracking/entitlements_api.py) pointed at the
test DB, with IAP_VERIFY_MODE=google and a FAKE Google API client injected via
entitlements_api._GOOGLE_API_CLIENT_OVERRIDE so NO network and NO service-account
file are needed. Every row uses a user_id / tour_name starting with 'TEST-696-';
cleanup deletes ONLY those rows, by exact id after a prefix re-check.

Covers (the ticket's test list, server/DB half):
  * google purchased -> granted + unlock written, keyed on the Google orderId;
  * replayed purchase token (same order) -> idempotent 409, exactly one unlock;
  * missing service account (override cleared) -> 503 google_verify_unconfigured,
    NEVER a grant;
  * wrong product (Google says a different product) -> refused (402);
  * a LEVEL purchase through the google path grants the level;
  * voided purchase -> the poller removes the unlock (reconcile against the DB).

Skips if no database is available (pure verifier matrix lives in
user-tracking/test_local696_google_verifier.py and always runs).
"""

import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "google")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, check_db_available, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-696-"
ORDER_ID = "GPA.696-0001-0002-00003"
TOKEN = "token-696-abc"


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    """Own this module's entitlements env (google mode, no auth) and restore it,
    mirroring 677/693 so collection order can't poison us."""
    keys = ("GATEWAY_API_KEY", "IAP_VERIFY_MODE", "ALLOW_UNAUTHENTICATED_ENTITLEMENTS",
            "GOOGLE_PLAY_SA_JSON")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["GATEWAY_API_KEY"] = ""
    os.environ["IAP_VERIFY_MODE"] = "google"
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    os.environ.pop("GOOGLE_PLAY_SA_JSON", None)  # unconfigured by default
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ─── Fake Google client (same shape as the pure-test one) ─────────────────────
class FakeApiClient:
    def __init__(self, response):
        self._response = response
        self.acknowledged = []
        self.consumed = []

    def get_product_purchase(self, package_name, product_id, token):
        return dict(self._response)

    def acknowledge_product(self, package_name, product_id, token):
        self.acknowledged.append(token)

    def consume_product(self, package_name, product_id, token):
        self.consumed.append(token)


def _purchase(order_id=ORDER_ID, product_id=None, state=0):
    d = {'orderId': order_id, 'purchaseState': state,
         'acknowledgementState': 0, 'consumptionState': 0}
    if product_id is not None:
        d['productId'] = product_id
    return d


# ─── module loaders ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ea():
    """Load entitlements_api pointed at the test DB, in google mode."""
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    if ut_dir not in sys.path:
        sys.path.insert(0, ut_dir)
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_696", os.path.join(ut_dir, "entitlements_api.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["entitlements_api_696"] = mod
    spec.loader.exec_module(mod)
    mod.API_KEY = ""
    mod.IAP_VERIFY_MODE = "google"
    mod.DATABASE_URL = get_database_url()
    return mod


@pytest.fixture(scope="module")
def client(ea):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    yield conn
    conn.close()


# ─── seed/cleanup (TEST-696- only) ────────────────────────────────────────────
def _cleanup(conn):
    cur = conn.cursor()
    for table, col in (
        ("tour_unlocks", "user_id"),
        ("purchases", "user_id"),
        ("device_entitlement", "user_id"),
        ("users", "secret_id"),
    ):
        try:
            cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE %s",
                        (TEST_PREFIX + "%",))
            keys = [r[0] for r in cur.fetchall()
                    if r[0] and str(r[0]).startswith(TEST_PREFIX)]
            for k in keys:
                cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (k,))
            conn.commit()
        except Exception:
            conn.rollback()
    # also clean purchases keyed by our order ids (store transaction, not user)
    try:
        cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s",
                    ("GPA.696-%",))
        conn.commit()
    except Exception:
        conn.rollback()
    try:
        cur.execute("SELECT id FROM audio_tours WHERE tour_name LIKE %s",
                    (TEST_PREFIX + "%",))
        for (tid,) in cur.fetchall():
            cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
        conn.commit()
    except Exception:
        conn.rollback()
    cur.close()


def _seed_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
                (user_id,))
    conn.commit()
    cur.close()


def _seed_tour(conn, name, price_tier=None):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, lat, lng, "
        "content_language, language, price_tier, is_test) "
        "VALUES (%s,%s,43.70,7.26,'en','en',%s,TRUE) RETURNING id",
        (name, name, price_tier))
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


# ─── Tour purchase via the google path ────────────────────────────────────────
def test_google_tour_purchase_grants_and_is_idempotent(db, ea, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}g tour", price_tier=3)
        buyer = f"{TEST_PREFIX}g-buyer"
        _seed_user(db, buyer)

        fake = FakeApiClient(_purchase(product_id="audioura.tour.tier3"))
        ea._GOOGLE_API_CLIENT_OVERRIDE = fake
        try:
            body = {
                "store": "google",
                "product_id": "audioura.tour.tier3",
                "order_id": ORDER_ID,
                "purchase_token": TOKEN,
                "user_id": buyer,
                "tour_id": str(tid),
            }
            r = client.post("/purchases/verify", json=body)
            assert r.status_code == 200, r.get_json()
            j = r.get_json()
            assert j["verified"] is True and j["unlocked"] is True
            assert int(j["tour_id"]) == tid
            # The authoritative Google orderId is the recorded transaction id.
            assert j["transaction_id"] == ORDER_ID
            # The verifier acknowledged AND consumed the purchase.
            assert fake.acknowledged == [TOKEN]
            assert fake.consumed == [TOKEN]

            # The purchase ledger row is keyed on the orderId, store='google'.
            cur = db.cursor()
            cur.execute("SELECT store FROM purchases WHERE transaction_id = %s", (ORDER_ID,))
            assert cur.fetchone()[0] == "google"
            cur.close()

            # Replay the SAME order -> 409 idempotent, still exactly one unlock.
            r2 = client.post("/purchases/verify", json=body)
            assert r2.status_code == 409
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id=%s AND tour_id=%s",
                        (buyer, tid))
            assert cur.fetchone()[0] == 1
            cur.close()
        finally:
            ea._GOOGLE_API_CLIENT_OVERRIDE = None
    finally:
        _cleanup(db)


def test_google_wrong_product_refused(db, ea, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}wp tour", price_tier=3)
        buyer = f"{TEST_PREFIX}wp-buyer"
        _seed_user(db, buyer)
        # Google reports a DIFFERENT product than the one requested.
        fake = FakeApiClient(_purchase(product_id="audioura.tour.tier1"))
        ea._GOOGLE_API_CLIENT_OVERRIDE = fake
        try:
            r = client.post("/purchases/verify", json={
                "store": "google",
                "product_id": "audioura.tour.tier3",
                "order_id": "GPA.696-wrong-prod",
                "purchase_token": TOKEN,
                "user_id": buyer,
                "tour_id": str(tid),
            })
            assert r.status_code == 402, r.get_json()
            assert "google_product_mismatch" in (r.get_json().get("raw_status") or "")
            # Nothing unlocked.
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id=%s", (buyer,))
            assert cur.fetchone()[0] == 0
            cur.close()
        finally:
            ea._GOOGLE_API_CLIENT_OVERRIDE = None
    finally:
        _cleanup(db)


def test_google_missing_sa_returns_503(db, ea, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}na tour", price_tier=3)
        buyer = f"{TEST_PREFIX}na-buyer"
        _seed_user(db, buyer)
        # No override AND no SA path -> _google_api_client() returns None -> 503.
        ea._GOOGLE_API_CLIENT_OVERRIDE = None
        ea.GOOGLE_PLAY_SA_JSON = ""
        r = client.post("/purchases/verify", json={
            "store": "google",
            "product_id": "audioura.tour.tier3",
            "order_id": "GPA.696-no-sa",
            "purchase_token": TOKEN,
            "user_id": buyer,
            "tour_id": str(tid),
        })
        assert r.status_code == 503, r.get_json()
        assert r.get_json()["error"] == "google_verify_unconfigured"
        # Never granted.
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id=%s", (buyer,))
        assert cur.fetchone()[0] == 0
        cur.close()
    finally:
        _cleanup(db)


def test_google_level_purchase_grants_level(db, ea, client):
    _cleanup(db)
    try:
        buyer = f"{TEST_PREFIX}lvl-buyer"
        _seed_user(db, buyer)
        fake = FakeApiClient(_purchase(order_id="GPA.696-level-01",
                                       product_id="audioura.pack.l3"))
        ea._GOOGLE_API_CLIENT_OVERRIDE = fake
        try:
            r = client.post("/purchases/verify", json={
                "store": "google",
                "product_id": "audioura.pack.l3",
                "order_id": "GPA.696-level-01",
                "purchase_token": "token-level",
                "user_id": buyer,
            })
            assert r.status_code == 200, r.get_json()
            j = r.get_json()
            assert j.get("verified") is True
            assert j.get("granted_level") == "l3"
            cur = db.cursor()
            cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (buyer,))
            assert cur.fetchone()[0] == "l3"
            cur.close()
        finally:
            ea._GOOGLE_API_CLIENT_OVERRIDE = None
    finally:
        _cleanup(db)


# ─── Voided poller reverses a grant against the real DB ───────────────────────
def test_voided_poller_removes_unlock(db, ea, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}void tour", price_tier=3)
        buyer = f"{TEST_PREFIX}void-buyer"
        _seed_user(db, buyer)

        void_order = "GPA.696-void-0001"
        fake = FakeApiClient(_purchase(order_id=void_order,
                                       product_id="audioura.tour.tier3"))
        ea._GOOGLE_API_CLIENT_OVERRIDE = fake
        try:
            r = client.post("/purchases/verify", json={
                "store": "google",
                "product_id": "audioura.tour.tier3",
                "order_id": void_order,
                "purchase_token": "token-void",
                "user_id": buyer,
                "tour_id": str(tid),
            })
            assert r.status_code == 200
        finally:
            ea._GOOGLE_API_CLIENT_OVERRIDE = None

        # The unlock exists.
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id=%s AND tour_id=%s",
                    (buyer, tid))
        assert cur.fetchone()[0] == 1
        cur.close()

        # Reconcile a void for that order against the real DB.
        ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
        if ut_dir not in sys.path:
            sys.path.insert(0, ut_dir)
        import google_play_voided_poller as voided
        cur = db.cursor()
        summary = voided.reconcile_voided_purchases(
            cur, [{"orderId": void_order, "purchaseToken": "token-void"}])
        db.commit()
        cur.close()
        assert summary["reversed"]["tour_unlock"] == 1

        # The unlock is gone; the ledger row is marked voided (audit, kept).
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id=%s AND tour_id=%s",
                    (buyer, tid))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT raw_status FROM purchases WHERE transaction_id=%s", (void_order,))
        assert cur.fetchone()[0].startswith("voided:")
        cur.close()

        # Idempotent: reconciling the same void again reverses nothing.
        cur = db.cursor()
        summary2 = voided.reconcile_voided_purchases(cur, [{"orderId": void_order}])
        db.commit()
        cur.close()
        assert summary2["already_voided"] == 1
    finally:
        _cleanup(db)
