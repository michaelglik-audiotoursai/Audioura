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
    # [LOCAL-686] 7 legacy .99 tiers + 34 round-dollar ladder tiers = 41.
    assert set(tiers.keys()) == set(range(1, 42))
    assert tiers[3]["label"] == "$4.99"
    assert tiers[6]["label"] == "$19.99" and tiers[7]["label"] == "$49.99"
    assert tiers[3]["product_id"] == "audioura.tour.tier3"
    # The ladder: round-dollar labels and usd<N> product ids (e.g. $35 = tier 29).
    assert tiers[29]["label"] == "$35"
    assert tiers[29]["product_id"] == "audioura.tour.usd35"
    assert tiers[41]["label"] == "$200"


def test_price_tiers_validation_and_labels():
    assert price_tiers_cfg.is_valid_tier(1) is True
    assert price_tiers_cfg.is_valid_tier(5) is True
    assert price_tiers_cfg.is_valid_tier(7) is True   # [LOCAL-684]
    assert price_tiers_cfg.is_valid_tier(8) is True   # [LOCAL-686] ladder start
    assert price_tiers_cfg.is_valid_tier(41) is True  # [LOCAL-686] ladder end
    assert price_tiers_cfg.is_valid_tier(42) is False # [LOCAL-686] past the ladder
    assert price_tiers_cfg.is_valid_tier(None) is False
    assert price_tiers_cfg.is_valid_tier(2.5) is False
    assert price_tiers_cfg.label_for_tier(None) == "Free"
    assert price_tiers_cfg.label_for_tier(4) == "$7.99"
    assert price_tiers_cfg.tier_for_product("audioura.tour.tier2") == 2
    assert price_tiers_cfg.tier_for_product("audioura.tour.usd35") == 29  # [LOCAL-686]
    assert price_tiers_cfg.tier_for_product("l3_pack_10") is None


# ─── 2. map-delivery Free/Paid filter helpers (pure, no DB) ───────────────────

def _load_md():
    md_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "map_delivery")
    path = os.path.join(md_dir, "app.py")
    # map_delivery/app.py imports its sibling modules (e.g. personal_match) by
    # bare name — in the container its own directory is the cwd. Mirror that so
    # the module loads outside the container too.
    if md_dir not in sys.path:
        sys.path.insert(0, md_dir)
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


# ─── 4. Translation: price inherited, unlock PER LANGUAGE (D653) ──────────────

def test_translation_inherits_price_but_unlocks_separately(db):
    """[LOCAL-677B / D653] A translation INHERITS its source's PRICE, but NOT its
    unlock. Buying one language unlocks that language only; the other still
    needs its own purchase. tour_unlocks keys on the language row's OWN id."""
    _cleanup(db)
    try:
        orig = _seed_tour(db, f"{TEST_PREFIX}tr orig")
        trans = _seed_tour(db, f"{TEST_PREFIX}tr ru", original_tour_id=orig, language="ru")
        owner = f"{TEST_PREFIX}tr-owner"
        _seed_creator(db, orig, owner)
        _make_curator(db, owner)

        # Price the original; the translation INHERITS the price.
        pricing_svc.set_price(owner, orig, 2)
        assert pricing_svc.get_price(trans)["price_tier"] == 2
        assert pricing_svc.get_price(trans)["price_label"] == "$2.99"

        # Pricing via the TRANSLATION id still resolves to the original for price.
        pricing_svc.set_price(owner, trans, 4)
        assert pricing_svc.get_price(orig)["price_tier"] == 4

        # An unlock recorded on the TRANSLATION keys on the translation's OWN id
        # and does NOT unlock the original (English still needs its own buy).
        buyer = f"{TEST_PREFIX}tr-buyer"
        _seed_user(db, buyer)
        pricing_svc.record_unlock(buyer, trans, transaction_id=f"{TEST_PREFIX}tr-txn",
                                  store="stub", price_usd=7.99)
        assert pricing_svc.is_unlocked(buyer, trans) is True
        assert pricing_svc.is_unlocked(buyer, orig) is False

        # The preview gate agrees: the translation is unlocked, the original is
        # still locked for the same buyer.
        assert pricing_svc.preview_state(buyer, trans)["locked"] is False
        assert pricing_svc.preview_state(buyer, orig)["locked"] is True
    finally:
        _cleanup(db)


def test_each_language_unlocks_independently_and_sales_pool(db):
    """[LOCAL-677B / D653] Buying Russian then English on the same tour are two
    separate unlocks; the curator's Sales count POOLS across the family."""
    _cleanup(db)
    try:
        orig = _seed_tour(db, f"{TEST_PREFIX}2x orig", price_tier=3)
        trans = _seed_tour(db, f"{TEST_PREFIX}2x ru", original_tour_id=orig, language="ru")
        buyer = f"{TEST_PREFIX}2x-buyer"
        _seed_user(db, buyer)

        # Both languages start locked for the buyer.
        assert pricing_svc.preview_state(buyer, orig)["locked"] is True
        assert pricing_svc.preview_state(buyer, trans)["locked"] is True

        # Buy Russian: Russian unlocks, English stays locked.
        pricing_svc.record_unlock(buyer, trans, transaction_id=f"{TEST_PREFIX}2x-ru-txn",
                                  store="stub", price_usd=4.99)
        assert pricing_svc.preview_state(buyer, trans)["locked"] is False
        assert pricing_svc.preview_state(buyer, orig)["locked"] is True
        # One sale so far (pooled view).
        assert pricing_svc.sales_count(orig) == 1

        # Buy English too: now both unlocked, two sales (2 × $4.99 = $9.98).
        pricing_svc.record_unlock(buyer, orig, transaction_id=f"{TEST_PREFIX}2x-en-txn",
                                  store="stub", price_usd=4.99)
        assert pricing_svc.preview_state(buyer, orig)["locked"] is False
        assert pricing_svc.sales_count(orig) == 2
        assert pricing_svc.sales_count(trans) == 2  # same pooled count via either id
    finally:
        _cleanup(db)


def test_verified_pools_across_languages(db):
    """[LOCAL-677B / D653] The Verified-listener mark comes from an unlock of ANY
    language: a buyer who unlocked the Russian copy is Verified on the English
    copy too (reviews/ratings pool across languages, D647)."""
    _cleanup(db)
    try:
        orig = _seed_tour(db, f"{TEST_PREFIX}vp orig", price_tier=3)
        trans = _seed_tour(db, f"{TEST_PREFIX}vp ru", original_tour_id=orig, language="ru")
        buyer = f"{TEST_PREFIX}vp-buyer"
        _seed_user(db, buyer)

        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, orig) is False
        cur.close()

        # Unlock ONLY the Russian translation.
        pricing_svc.record_unlock(buyer, trans, transaction_id=f"{TEST_PREFIX}vp-txn",
                                  store="stub", price_usd=4.99)

        # Verified on BOTH the original and the translation (pooled).
        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, orig) is True
        assert reviews_svc.compute_verified(cur, buyer, trans) is True
        cur.close()
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


def test_stub_tour_purchase_translation_unlocks_own_language(db, ent_client):
    """[LOCAL-677B / D653] Buying a TRANSLATION through /purchases/verify writes
    the unlock on the TRANSLATION's own id, not the original — so the original
    stays locked and English needs its own purchase."""
    _cleanup(db)
    try:
        orig = _seed_tour(db, f"{TEST_PREFIX}vt orig", price_tier=3)
        trans = _seed_tour(db, f"{TEST_PREFIX}vt ru", original_tour_id=orig, language="ru")
        buyer = f"{TEST_PREFIX}vt-buyer"
        _seed_user(db, buyer)
        r = ent_client.post("/purchases/verify", json={
            "store": "stub",
            "transaction_id": f"{TEST_PREFIX}vt-txn",
            "product": "audioura.tour.tier3",
            "user_id": buyer,
            "tour_id": str(trans),
        })
        assert r.status_code == 200
        j = r.get_json()
        assert j["unlocked"] is True
        # The unlock is on the translation's OWN id.
        assert int(j["tour_id"]) == trans

        cur = db.cursor()
        cur.execute("SELECT tour_id FROM tour_unlocks WHERE user_id = %s", (buyer,))
        unlocked_ids = {row[0] for row in cur.fetchall()}
        cur.close()
        assert trans in unlocked_ids
        assert orig not in unlocked_ids

        # Pricing agrees: Russian unlocked, English still locked.
        assert pricing_svc.preview_state(buyer, trans)["locked"] is False
        assert pricing_svc.preview_state(buyer, orig)["locked"] is True
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


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL-677C (D654) — pay BEFORE download: the 402 gate + the Stop-1 preview.
# ═══════════════════════════════════════════════════════════════════════════
#
# These exercise map-delivery's /download-tour/<id> gate and
# /tour/<id>/preview-audio against the test DB (the same in-process md_client).
# They seed a real little zip into audio_tours.audio_tour so the download and
# preview paths have bytes to serve. All rows use TEST-677- ids and are cleaned.

import io  # noqa: E402
import zipfile  # noqa: E402


def _make_tour_zip(num_stops=3):
    """A minimal tour zip with audio_1.mp3 … audio_<n>.mp3, each carrying
    DISTINCT bytes so a test can prove WHICH stop was served."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", "<html><body>tour</body></html>")
        for i in range(1, num_stops + 1):
            # Distinct, recognisable bytes per stop (not real mp3, but opaque to
            # the endpoint which only reads the member bytes).
            zf.writestr(f"audio_{i}.mp3", f"STOP-{i}-AUDIO-BYTES".encode())
    return buf.getvalue()


def _seed_tour_with_zip(conn, name, price_tier=None, original_tour_id=None,
                        language="en", num_stops=3):
    """Seed a tour row WITH an audio_tour zip blob so download/preview work."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id,
                                 price_tier, audio_tour, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id,
         price_tier, psycopg2.Binary(_make_tour_zip(num_stops))),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


import psycopg2  # noqa: E402


def test_download_gate_402_for_unbought_paid(db, md_client):
    """A PAID language row the caller has not unlocked is refused with HTTP 402
    purchase_required BEFORE the zip is streamed."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl paid", price_tier=3)
        stranger = f"{TEST_PREFIX}dl-stranger"
        _seed_user(db, stranger)

        r = md_client.get(f"/download-tour/{tid}?user_id={stranger}")
        assert r.status_code == 402
        j = r.get_json()
        assert j["error"] == "purchase_required"
        assert int(j["tour_id"]) == tid
        assert int(j["price_tier"]) == 3
        assert j["price"] == "4.99"  # the ticket's exact shape (no '$')
    finally:
        _cleanup(db)


def test_download_gate_200_after_stub_purchase_that_language(db, md_client, ent_client):
    """After a stub purchase of THAT language the download succeeds (200); the
    OTHER language of the same tour is still 402 (per-language, D653)."""
    _cleanup(db)
    try:
        orig = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl2 en", price_tier=3)
        ru = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl2 ru",
                                 original_tour_id=orig, language="ru")
        buyer = f"{TEST_PREFIX}dl2-buyer"
        _seed_user(db, buyer)

        # Both languages locked for the buyer at first.
        assert md_client.get(f"/download-tour/{orig}?user_id={buyer}").status_code == 402
        assert md_client.get(f"/download-tour/{ru}?user_id={buyer}").status_code == 402

        # Buy ENGLISH (the original id) through the stub purchase path.
        pr = ent_client.post("/purchases/verify", json={
            "store": "stub",
            "transaction_id": f"{TEST_PREFIX}dl2-en-txn",
            "product": "audioura.tour.tier3",
            "user_id": buyer,
            "tour_id": str(orig),
        })
        assert pr.status_code == 200

        # English now downloads (200); Russian is STILL 402 (needs its own buy).
        ok = md_client.get(f"/download-tour/{orig}?user_id={buyer}")
        assert ok.status_code == 200
        assert ok.headers["Content-Type"] == "application/zip"
        assert md_client.get(f"/download-tour/{ru}?user_id={buyer}").status_code == 402

        # Buy Russian too → Russian now downloads.
        pr2 = ent_client.post("/purchases/verify", json={
            "store": "stub",
            "transaction_id": f"{TEST_PREFIX}dl2-ru-txn",
            "product": "audioura.tour.tier3",
            "user_id": buyer,
            "tour_id": str(ru),
        })
        assert pr2.status_code == 200
        assert md_client.get(f"/download-tour/{ru}?user_id={buyer}").status_code == 200
    finally:
        _cleanup(db)


def test_download_gate_free_tour_unchanged(db, md_client):
    """A FREE tour downloads for anyone — the gate never fires."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl free")  # price_tier None
        stranger = f"{TEST_PREFIX}dl-free-stranger"
        _seed_user(db, stranger)
        r = md_client.get(f"/download-tour/{tid}?user_id={stranger}")
        assert r.status_code == 200
        assert r.headers["Content-Type"] == "application/zip"
    finally:
        _cleanup(db)


def test_download_gate_grandfathered_free_download_allowed(db, md_client):
    """A user who downloaded a row while it was FREE keeps access after the
    curator later prices it (grandfathering, honoured from tour_downloads)."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl gf")  # free at first
        user = f"{TEST_PREFIX}dl-gf-user"
        _seed_user(db, user)

        # Download while FREE → 200, and records a was_free grandfather row.
        assert md_client.get(f"/download-tour/{tid}?user_id={user}").status_code == 200

        # The curator now PRICES the tour.
        cur = db.cursor()
        cur.execute("UPDATE audio_tours SET price_tier = 3 WHERE id = %s", (tid,))
        db.commit()
        cur.close()

        # A brand-new user is now gated (402)…
        stranger = f"{TEST_PREFIX}dl-gf-stranger"
        _seed_user(db, stranger)
        assert md_client.get(f"/download-tour/{tid}?user_id={stranger}").status_code == 402

        # …but the grandfathered user still downloads (200).
        assert md_client.get(f"/download-tour/{tid}?user_id={user}").status_code == 200
    finally:
        _cleanup(db)


def test_download_gate_curator_downloads_own_tour(db, md_client):
    """The tour's CREATOR (curator) downloads their own paid tour unpriced."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}dl own", price_tier=3)
        owner = f"{TEST_PREFIX}dl-owner"
        _seed_creator(db, tid, owner)  # earliest tour_requests.secret_id = owner
        r = md_client.get(f"/download-tour/{tid}?user_id={owner}")
        assert r.status_code == 200
    finally:
        _cleanup(db)


def test_preview_audio_serves_only_stop_1(db, md_client):
    """GET /tour/<id>/preview-audio returns Stop 1's audio ONLY — the bytes are
    audio_1.mp3's, and no other stop's bytes are ever served. Works with NO
    unlock (a paid, un-bought tour previews)."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}prev paid", price_tier=3,
                                  num_stops=4)
        stranger = f"{TEST_PREFIX}prev-stranger"
        _seed_user(db, stranger)

        r = md_client.get(f"/tour/{tid}/preview-audio?user_id={stranger}")
        assert r.status_code == 200
        assert r.headers["Content-Type"] == "audio/mpeg"
        body = r.data
        # It is EXACTLY Stop 1's bytes…
        assert body == b"STOP-1-AUDIO-BYTES"
        # …and NONE of the other stops' bytes leaked into the response.
        assert b"STOP-2-AUDIO-BYTES" not in body
        assert b"STOP-3-AUDIO-BYTES" not in body
        assert b"STOP-4-AUDIO-BYTES" not in body
    finally:
        _cleanup(db)


def test_preview_audio_free_tour_also_previews(db, md_client):
    """A free tour previews too (Stop 1 bytes), with no unlock needed."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}prev free")
        r = md_client.get(f"/tour/{tid}/preview-audio")
        assert r.status_code == 200
        assert r.data == b"STOP-1-AUDIO-BYTES"
    finally:
        _cleanup(db)


def test_preview_audio_missing_tour_404(db, md_client):
    """A tour id with no audio → 404, never a 500 and never other bytes."""
    _cleanup(db)
    try:
        r = md_client.get("/tour/999999999/preview-audio")
        assert r.status_code == 404
    finally:
        _cleanup(db)
