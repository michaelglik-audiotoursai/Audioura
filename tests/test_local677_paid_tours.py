"""
LOCAL-677 — Curator paid tours tests.

Covers the ticket's test list (§6):
  * the curator-only price      — a non-curator is refused (not_curator); a
    curator who does not own the tour is refused (not_owner); a curator who owns
    it may set/clear a valid tier; a bad tier is refused (invalid_tier);
  * translation inheritance     — a translation shares its SOURCE tour's price
    and unlock;
  * the preview lock and unlock — a paid tour is `locked` for a stranger (Stop 1
    free, the rest locked) and NOT locked once the buyer has an unlock row;
  * the stub purchase writes an unlock idempotently — the /purchases/verify
    tour path (IAP_VERIFY_MODE=stub) writes exactly one tour_unlocks row and a
    replay is a no-op (409, still unlocked);
  * the Free/Paid filter        — map-delivery's price filter helpers select the
    right tours and the search endpoint honours ?price=free|paid;
  * verified-after-unlock       — tour_reviews_service.compute_verified reads
    tour_unlocks and marks a buyer's rating "Verified listener".

Pure helpers (price_tiers config, the map-delivery filter helpers) run with no
DB. The DB-backed and endpoint tests use an in-process Flask client.

Safety (ticket): every row written here uses a user_id / tour_name starting
with 'TEST-677-'. Cleanup deletes ONLY rows whose key has that exact prefix, by
exact id after a prefix re-check, across tour_unlocks, tour_ratings, purchases,
tour_requests, users and audio_tours. No other table is touched destructively.
"""

import os
import sys
import importlib.util

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# The entitlements stub path needs these BEFORE importing entitlements_api so
# the module reads stub mode and the local unauthenticated bypass at import.
os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, check_db_available, get_database_url  # noqa: E402
import price_tiers as price_tiers_cfg  # noqa: E402
import tour_pricing_service as pricing_svc  # noqa: E402
import tour_rating_service as rating_svc  # noqa: E402
import tour_reviews_service as reviews_svc  # noqa: E402

TEST_PREFIX = "TEST-677-"


# ─── 1. price_tiers config (pure, DB-authoritative with fallback) ─────────────

def test_price_tiers_fallback_constants():
    tiers = price_tiers_cfg.load_price_tiers()  # no cursor → code defaults
    assert set(tiers.keys()) == {1, 2, 3, 4, 5}
    assert tiers[3]["label"] == "$4.99"
    assert tiers[3]["product_id"] == "audioura.tour.tier3"


def test_price_tiers_validation_and_labels():
    assert price_tiers_cfg.is_valid_tier(1) is True
    assert price_tiers_cfg.is_valid_tier(5) is True
    assert price_tiers_cfg.is_valid_tier(6) is False
    assert price_tiers_cfg.is_valid_tier(None) is False
    assert price_tiers_cfg.is_valid_tier(2.5) is False
    assert price_tiers_cfg.label_for_tier(None) == "Free"
    assert price_tiers_cfg.label_for_tier(4) == "$7.99"
    assert price_tiers_cfg.tier_for_product("audioura.tour.tier2") == 2
    assert price_tiers_cfg.tier_for_product("l3_pack_10") is None


# ─── 2. map-delivery Free/Paid filter helpers (pure, no DB) ───────────────────

def _load_md():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "map_delivery", "app.py")
    spec = importlib.util.spec_from_file_location("md_app_local677", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


def test_md_price_filter_parse_and_pass():
    md = _load_md()
    assert md._parse_price_filter({"price": "free"}) == "free"
    assert md._parse_price_filter({"price": "paid"}) == "paid"
    assert md._parse_price_filter({"price": "PAID"}) == "paid"
    assert md._parse_price_filter({"price": "nonsense"}) is None
    assert md._parse_price_filter({}) is None

    # None filter → everything passes.
    assert md._passes_price_filter(None, True) is True
    assert md._passes_price_filter(None, False) is True
    # free → only free tours.
    assert md._passes_price_filter("free", False) is True
    assert md._passes_price_filter("free", True) is False
    # paid → only paid tours.
    assert md._passes_price_filter("paid", True) is True
    assert md._passes_price_filter("paid", False) is False


# ─── DB fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(conn):
    cur = conn.cursor()
    for table, col in (
        ("tour_unlocks", "user_id"),
        ("tour_ratings", "user_id"),
        ("purchases", "user_id"),
        ("tour_requests", "secret_id"),
        ("users", "secret_id"),
    ):
        try:
            cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE %s",
                        (TEST_PREFIX + "%",))
            keys = [row[0] for row in cur.fetchall()
                    if row[0] and str(row[0]).startswith(TEST_PREFIX)]
            for k in keys:
                cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (k,))
            conn.commit()
        except Exception:
            conn.rollback()
    # Tours: delete translations (original_tour_id set) first to avoid the FK,
    # then originals. Only our TEST-677- named rows, by exact id.
    try:
        cur.execute("SELECT id FROM audio_tours WHERE tour_name LIKE %s AND original_tour_id IS NOT NULL",
                    (TEST_PREFIX + "%",))
        for (tid,) in cur.fetchall():
            cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
        conn.commit()
        cur.execute("SELECT id FROM audio_tours WHERE tour_name LIKE %s", (TEST_PREFIX + "%",))
        for (tid,) in cur.fetchall():
            cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
        conn.commit()
    except Exception:
        conn.rollback()
    cur.close()


def _seed_tour(conn, name, original_tour_id=None, language="en", price_tier=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id,
                                 price_tier, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id, price_tier),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


def _seed_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
                (user_id,))
    conn.commit()
    cur.close()


def _seed_creator(conn, tour_id, user_id):
    """Make user_id the tour's creator (earliest tour_requests row)."""
    _seed_user(conn, user_id)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tour_requests (secret_id, tour_id, request_string, status, created_at)
        VALUES (%s, %s, %s, 'completed', CURRENT_TIMESTAMP - INTERVAL '1 day')
        """,
        (user_id, str(tour_id), "creator"),
    )
    conn.commit()
    cur.close()


def _set_level(conn, user_id, level):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO device_entitlement (user_id, level, last_activity_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level, updated_at = NOW()
        """,
        (user_id, level),
    )
    conn.commit()
    cur.close()


def _make_curator(conn, user_id):
    """A device whose level has can_sell=TRUE. l4 is the Curator level (D613)."""
    _seed_user(conn, user_id)
    _set_level(conn, user_id, "l4")


# ─── 3. Curator-only price ────────────────────────────────────────────────────

def test_non_curator_cannot_price(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}np tour")
        owner = f"{TEST_PREFIX}np-owner"
        _seed_creator(db, tid, owner)
        _set_level(db, owner, "l2")  # NOT a curator
        with pytest.raises(pricing_svc.PricingError) as ei:
            pricing_svc.set_price(owner, tid, 3)
        assert ei.value.code == "not_curator"
    finally:
        _cleanup(db)


def test_curator_but_not_owner_refused(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}no tour")
        owner = f"{TEST_PREFIX}no-owner"
        other = f"{TEST_PREFIX}no-other"
        _seed_creator(db, tid, owner)
        _make_curator(db, other)  # a curator, but not the owner
        with pytest.raises(pricing_svc.PricingError) as ei:
            pricing_svc.set_price(other, tid, 3)
        assert ei.value.code == "not_owner"
    finally:
        _cleanup(db)


def test_curator_owner_sets_and_clears_price(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}set tour")
        owner = f"{TEST_PREFIX}set-owner"
        _seed_creator(db, tid, owner)
        _make_curator(db, owner)

        out = pricing_svc.set_price(owner, tid, 3)
        assert out["is_paid"] is True
        assert out["price_tier"] == 3
        assert out["price_label"] == "$4.99"

        # Invalid tier refused.
        with pytest.raises(pricing_svc.PricingError) as ei:
            pricing_svc.set_price(owner, tid, 99)
        assert ei.value.code == "invalid_tier"

        # Clear (free again).
        cleared = pricing_svc.set_price(owner, tid, None)
        assert cleared["is_paid"] is False
        assert cleared["price_label"] == "Free"
    finally:
        _cleanup(db)


# ─── 4. Translation inheritance ───────────────────────────────────────────────

def test_translation_inherits_price_and_unlock(db):
    _cleanup(db)
    try:
        orig = _seed_tour(db, f"{TEST_PREFIX}tr orig")
        trans = _seed_tour(db, f"{TEST_PREFIX}tr ru", original_tour_id=orig, language="ru")
        owner = f"{TEST_PREFIX}tr-owner"
        _seed_creator(db, orig, owner)
        _make_curator(db, owner)

        # Price the original; the translation inherits it.
        pricing_svc.set_price(owner, orig, 2)
        assert pricing_svc.get_price(trans)["price_tier"] == 2
        assert pricing_svc.get_price(trans)["price_label"] == "$2.99"

        # Pricing via the TRANSLATION id resolves to the original.
        pricing_svc.set_price(owner, trans, 4)
        assert pricing_svc.get_price(orig)["price_tier"] == 4

        # An unlock recorded on the translation keys on the original and is
        # therefore shared by both.
        buyer = f"{TEST_PREFIX}tr-buyer"
        _seed_user(db, buyer)
        pricing_svc.record_unlock(buyer, trans, transaction_id=f"{TEST_PREFIX}tr-txn",
                                  store="stub", price_usd=7.99)
        assert pricing_svc.is_unlocked(buyer, orig) is True
        assert pricing_svc.is_unlocked(buyer, trans) is True
    finally:
        _cleanup(db)


# ─── 5. Preview lock + unlock ─────────────────────────────────────────────────

def test_preview_lock_and_unlock(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}lock tour", price_tier=3)
        stranger = f"{TEST_PREFIX}lock-stranger"
        buyer = f"{TEST_PREFIX}lock-buyer"
        _seed_user(db, stranger)
        _seed_user(db, buyer)

        # A paid tour is locked for a stranger: Stop 1 free, the rest locked.
        s = pricing_svc.preview_state(stranger, tid)
        assert s["is_paid"] is True
        assert s["locked"] is True
        assert s["unlocked"] is False
        assert s["free_preview_stops"] == 1

        # After an unlock the buyer is not locked.
        pricing_svc.record_unlock(buyer, tid, transaction_id=f"{TEST_PREFIX}lock-txn",
                                  store="stub", price_usd=4.99)
        b = pricing_svc.preview_state(buyer, tid)
        assert b["locked"] is False
        assert b["unlocked"] is True

        # A FREE tour is never locked.
        free_tid = _seed_tour(db, f"{TEST_PREFIX}lock free")
        f = pricing_svc.preview_state(stranger, free_tid)
        assert f["is_paid"] is False
        assert f["locked"] is False
    finally:
        _cleanup(db)


# ─── 6. Idempotent unlock + sales count ───────────────────────────────────────

def test_record_unlock_idempotent_and_sales_count(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}sales tour", price_tier=1)
        b1 = f"{TEST_PREFIX}sales-b1"
        b2 = f"{TEST_PREFIX}sales-b2"
        _seed_user(db, b1)
        _seed_user(db, b2)

        r1 = pricing_svc.record_unlock(b1, tid, transaction_id=f"{TEST_PREFIX}s-t1", store="stub")
        assert r1["created"] is True
        # Same buyer, same tour → no new row.
        r1b = pricing_svc.record_unlock(b1, tid, transaction_id=f"{TEST_PREFIX}s-t1b", store="stub")
        assert r1b["created"] is False
        # A second buyer adds a sale.
        pricing_svc.record_unlock(b2, tid, transaction_id=f"{TEST_PREFIX}s-t2", store="stub")

        assert pricing_svc.sales_count(tid) == 2
    finally:
        _cleanup(db)


# ─── 7. Stub purchase endpoint writes an unlock idempotently ──────────────────

@pytest.fixture(scope="module")
def ent_client():
    # Point the entitlements module at the SAME database the tests use.
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_677", os.path.join(ut_dir, "entitlements_api.py"))
    ea = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ea)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


def test_stub_tour_purchase_unlocks_idempotently(db, ent_client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}buy tour", price_tier=3)
        buyer = f"{TEST_PREFIX}buy-buyer"
        _seed_user(db, buyer)
        body = {
            "store": "stub",
            "transaction_id": f"{TEST_PREFIX}buy-txn",
            "product": "audioura.tour.tier3",
            "user_id": buyer,
            "tour_id": str(tid),
        }
        r = ent_client.post("/purchases/verify", json=body)
        assert r.status_code == 200
        j = r.get_json()
        assert j["verified"] is True
        assert j["unlocked"] is True
        assert int(j["tour_id"]) == tid
        assert float(j["amount"]) == 4.99

        # Replay → 409 already_verified, still unlocked, no second row.
        r2 = ent_client.post("/purchases/verify", json=body)
        assert r2.status_code == 409
        assert r2.get_json()["unlocked"] is True

        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s AND tour_id = %s",
                    (buyer, tid))
        assert cur.fetchone()[0] == 1
        cur.close()

        # A tour purchase does NOT change the buyer's level.
        cur = db.cursor()
        cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (buyer,))
        row = cur.fetchone()
        # Either no entitlement row at all, or still l1 — never promoted to l3/l4.
        assert row is None or row[0] in ("l1", "l2")
        cur.close()
    finally:
        _cleanup(db)


def test_stub_tour_purchase_requires_tour_id(db, ent_client):
    _cleanup(db)
    try:
        buyer = f"{TEST_PREFIX}buy-noid"
        _seed_user(db, buyer)
        r = ent_client.post("/purchases/verify", json={
            "store": "stub",
            "transaction_id": f"{TEST_PREFIX}noid-txn",
            "product": "audioura.tour.tier1",
            "user_id": buyer,
        })
        assert r.status_code == 400
        assert r.get_json()["error"] == "missing_fields"
    finally:
        _cleanup(db)


# ─── 8. Free/Paid filter end to end (search endpoint) ─────────────────────────

@pytest.fixture(scope="module")
def md_client(db):
    md = _load_md()
    # Route the loaded module at the test DB.
    import psycopg2
    md.get_db_connection = lambda: psycopg2.connect(get_database_url())
    md.app.testing = True
    return md.app.test_client()


def test_search_price_filter(db, md_client):
    _cleanup(db)
    try:
        # is_test must be FALSE for the search endpoint to surface the rows.
        cur = db.cursor()
        cur.execute(
            "INSERT INTO audio_tours (tour_name,request_string,lat,lng,content_language,language,price_tier,is_test) "
            "VALUES (%s,%s,43.70,7.26,'en','en',3,FALSE) RETURNING id",
            (f"{TEST_PREFIX}flt paid", f"{TEST_PREFIX}flt paid"))
        paid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO audio_tours (tour_name,request_string,lat,lng,content_language,language,is_test) "
            "VALUES (%s,%s,43.70,7.26,'en','en',FALSE) RETURNING id",
            (f"{TEST_PREFIX}flt free", f"{TEST_PREFIX}flt free"))
        free = cur.fetchone()[0]
        db.commit()
        cur.close()

        q = f"/search-tours?pattern={TEST_PREFIX}flt&lat=43.70&lng=7.26"

        paid_ids = [t["id"] for t in md_client.get(q + "&price=paid").get_json()["tours"]]
        assert paid in paid_ids and free not in paid_ids

        free_ids = [t["id"] for t in md_client.get(q + "&price=free").get_json()["tours"]]
        assert free in free_ids and paid not in free_ids

        allr = md_client.get(q).get_json()["tours"]
        all_ids = {t["id"] for t in allr}
        assert paid in all_ids and free in all_ids
        # The paid tour carries its price label; the free one shows Free.
        by = {t["id"]: t for t in allr}
        assert by[paid]["price_label"] == "$4.99"
        assert by[paid]["is_paid"] is True
        assert by[free]["price_label"] == "Free"
        assert by[free]["is_paid"] is False
    finally:
        _cleanup(db)


# ─── 9. Verified-after-unlock ─────────────────────────────────────────────────

def test_verified_after_unlock(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, f"{TEST_PREFIX}ver tour", price_tier=3)
        buyer = f"{TEST_PREFIX}ver-buyer"
        _seed_user(db, buyer)

        cur = db.cursor()
        # No unlock yet → not verified.
        assert reviews_svc.compute_verified(cur, buyer, tid) is False
        cur.close()

        # Unlock the tour (as the stub purchase path would).
        pricing_svc.record_unlock(buyer, tid, transaction_id=f"{TEST_PREFIX}ver-txn",
                                  store="stub", price_usd=4.99)

        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, tid) is True
        cur.close()

        # And a rating recorded now is stored verified → "Verified listener".
        # (record_rating computes verified via the same path.)
        rating_svc.record_listen(buyer, tid, 0)
        out = rating_svc.record_rating(buyer, tid, 9)
        assert out["verified"] is True
    finally:
        _cleanup(db)
