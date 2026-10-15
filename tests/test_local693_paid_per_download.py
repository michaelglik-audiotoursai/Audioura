"""LOCAL-693 — D660: every download of a paid tour is paid; a failed download
never consumes the purchase.

Covers the ticket's test list:
  * buy → download OK → second download 402 → buy again → download OK;
  * a failed/cut-off download does NOT consume the purchase (simulate by never
    confirming the download-complete);
  * two languages = two purchases (per-language unlock, D653) each consumed
    independently;
  * grandfathered (downloaded-while-free) and curator-own downloads are
    unchanged and never consume an unlock;
  * /unlock-state reports unlocked=has an UNCONSUMED purchase and the
    downloads_bought / downloads_used counts;
  * a verified buyer stays verified after the purchase is consumed (any purchase
    counts, D647).

Harness mirrors tests/test_local677_paid_tours.py: an in-process Flask client
for map-delivery (map_delivery/app.py) and for the entitlements blueprint
(user-tracking/entitlements_api.py), both pointed at the test DB. Every row uses
a user_id / tour_name starting with 'TEST-693-'; cleanup deletes ONLY those rows.

Requires migration 031 (tour_unlocks.consumed_at + the partial active-unlock
unique index) applied to the test DB; the services also self-heal the schema, so
the suite converges either way.
"""

import importlib.util
import io
import os
import sys
import zipfile

import psycopg2
import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, check_db_available, get_database_url  # noqa: E402
import tour_pricing_service as pricing_svc  # noqa: E402
import tour_reviews_service as reviews_svc  # noqa: E402
import tour_rating_service as rating_svc  # noqa: E402

TEST_PREFIX = "TEST-693-"


# ─── module loaders (mirror 677) ──────────────────────────────────────────────

def _load_md():
    md_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "map_delivery")
    path = os.path.join(md_dir, "app.py")
    if md_dir not in sys.path:
        sys.path.insert(0, md_dir)
    spec = importlib.util.spec_from_file_location("md_app_local693", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


def _make_tour_zip(num_stops=3):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", "<html><body>tour</body></html>")
        for i in range(1, num_stops + 1):
            zf.writestr(f"audio_{i}.mp3", f"STOP-{i}-AUDIO".encode())
    return buf.getvalue()


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    # Ensure migration 031 schema is present (the service self-heals too).
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)")
        cur.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname='uq_tour_unlocks_user_tour' AND conrelid='tour_unlocks'::regclass) "
            "THEN ALTER TABLE tour_unlocks DROP CONSTRAINT uq_tour_unlocks_user_tour; END IF; END $$;"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tour_unlocks_active "
            "ON tour_unlocks (user_id, tour_id) WHERE consumed_at IS NULL"
        )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def md_client(db):
    md = _load_md()
    md.get_db_connection = lambda: psycopg2.connect(get_database_url())
    md.app.testing = True
    return md.app.test_client()


@pytest.fixture(scope="module")
def ent_client():
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_693", os.path.join(ut_dir, "entitlements_api.py"))
    ea = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ea)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    return app.test_client()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _cleanup(conn):
    cur = conn.cursor()
    for table, col in (
        ("tour_unlocks", "user_id"),
        ("tour_ratings", "user_id"),
        ("purchases", "user_id"),
        ("tour_downloads", "user_id"),
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


def _seed_tour_with_zip(conn, name, price_tier=None, original_tour_id=None,
                        language="en", num_stops=3):
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


def _seed_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
                (user_id,))
    conn.commit()
    cur.close()


def _seed_creator(conn, tour_id, user_id):
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


def _buy(ent_client, user_id, tour_id, txn):
    return ent_client.post("/purchases/verify", json={
        "store": "stub",
        "transaction_id": txn,
        "product": "audioura.tour.tier3",
        "user_id": user_id,
        "tour_id": str(tour_id),
    })


def _download(md_client, tour_id, user_id):
    """GET /download-tour and return (status, download_id-from-header)."""
    r = md_client.get(f"/download-tour/{tour_id}?user_id={user_id}")
    dlid = r.headers.get("X-Download-Id", "") if r.status_code == 200 else ""
    return r.status_code, dlid


def _confirm(md_client, tour_id, user_id, download_id):
    return md_client.post(
        f"/tour/{tour_id}/download-complete",
        json={"user_id": user_id, "download_id": download_id},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Core D660 lifecycle
# ═══════════════════════════════════════════════════════════════════════════

def test_buy_download_second_402_rebuy_download(db, md_client, ent_client):
    """buy → download OK → confirm → second download 402 → buy again → OK."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}cycle", price_tier=3)
        buyer = f"{TEST_PREFIX}cycle-buyer"
        _seed_user(db, buyer)

        # 1. Buy.
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}cycle-t1").status_code == 200

        # 2. First download succeeds and carries a download id to confirm.
        st, dlid = _download(md_client, tid, buyer)
        assert st == 200
        assert dlid, "a paid, unlocked download must return X-Download-Id"

        # 3. Confirm the completed download → spends the purchase.
        c = _confirm(md_client, tid, buyer, dlid)
        assert c.status_code == 200
        cj = c.get_json()
        assert cj["consumed"] is True
        assert cj["remaining_unconsumed"] == 0

        # 4. The SECOND download is now refused (402) — one download per buy.
        st2, _ = _download(md_client, tid, buyer)
        assert st2 == 402

        # 5. Buy AGAIN (new transaction) → a fresh active unlock.
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}cycle-t2").status_code == 200

        # 6. Download succeeds again.
        st3, dlid3 = _download(md_client, tid, buyer)
        assert st3 == 200 and dlid3

        # Two purchases bought, one consumed so far (the 2nd not yet confirmed).
        bought, used = _counts(db, buyer, tid)
        assert bought == 2 and used == 1
    finally:
        _cleanup(db)


def test_failed_download_does_not_consume(db, md_client, ent_client):
    """A failed/cut-off download does NOT consume the purchase: if the app never
    confirms (download-complete not called), the unlock stays unconsumed and the
    listener downloads again for free."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}fail", price_tier=3)
        buyer = f"{TEST_PREFIX}fail-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}fail-t1").status_code == 200

        # Download starts (200) but the client is cut off — NO confirm call.
        st, dlid = _download(md_client, tid, buyer)
        assert st == 200 and dlid
        # Nothing consumed.
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 0

        # The listener RETRIES — still allowed (still unconsumed), FOR FREE.
        st2, dlid2 = _download(md_client, tid, buyer)
        assert st2 == 200 and dlid2
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 0

        # This time the download completes and is confirmed → now consumed.
        assert _confirm(md_client, tid, buyer, dlid2).get_json()["consumed"] is True
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 1
        # And the next download is refused.
        assert _download(md_client, tid, buyer)[0] == 402
    finally:
        _cleanup(db)


def test_two_languages_two_purchases_consume_independently(db, md_client, ent_client):
    """Two languages = two purchases (D653); consuming one does not touch the
    other."""
    _cleanup(db)
    try:
        en = _seed_tour_with_zip(db, f"{TEST_PREFIX}2l en", price_tier=3)
        ru = _seed_tour_with_zip(db, f"{TEST_PREFIX}2l ru",
                                 original_tour_id=en, language="ru")
        buyer = f"{TEST_PREFIX}2l-buyer"
        _seed_user(db, buyer)

        assert _buy(ent_client, buyer, en, f"{TEST_PREFIX}2l-en").status_code == 200
        assert _buy(ent_client, buyer, ru, f"{TEST_PREFIX}2l-ru").status_code == 200

        # Download + confirm ENGLISH.
        st, dlid = _download(md_client, en, buyer)
        assert st == 200
        assert _confirm(md_client, en, buyer, dlid).get_json()["consumed"] is True

        # English now 402; Russian still downloads (its own unconsumed unlock).
        assert _download(md_client, en, buyer)[0] == 402
        st_ru, dlid_ru = _download(md_client, ru, buyer)
        assert st_ru == 200
        assert _confirm(md_client, ru, buyer, dlid_ru).get_json()["consumed"] is True
        # Now Russian is 402 too.
        assert _download(md_client, ru, buyer)[0] == 402
    finally:
        _cleanup(db)


def test_grandfathered_download_never_consumes(db, md_client):
    """A grandfathered (downloaded-while-free) user keeps downloading after the
    tour is priced, and no unlock is involved so nothing is consumed. The
    download carries NO X-Download-Id (nothing to confirm)."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}gf")  # free at first
        user = f"{TEST_PREFIX}gf-user"
        _seed_user(db, user)
        # Download while free.
        st, dlid = _download(md_client, tid, user)
        assert st == 200 and dlid == ""  # free download → no consume token

        # Curator prices it.
        cur = db.cursor()
        cur.execute("UPDATE audio_tours SET price_tier = 3 WHERE id = %s", (tid,))
        db.commit()
        cur.close()

        # Grandfathered user still downloads, repeatedly, with no token.
        for _ in range(3):
            st, dlid = _download(md_client, tid, user)
            assert st == 200 and dlid == ""
        # No unlock rows at all for this user.
        bought, used = _counts(db, user, tid)
        assert bought == 0 and used == 0
    finally:
        _cleanup(db)


def test_curator_download_never_consumes(db, md_client):
    """The curator downloads their own paid tour unpriced and unconsumed, with
    no X-Download-Id (no purchase to spend)."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}own", price_tier=3)
        owner = f"{TEST_PREFIX}own-owner"
        _seed_creator(db, tid, owner)
        for _ in range(2):
            st, dlid = _download(md_client, tid, owner)
            assert st == 200 and dlid == ""
        bought, used = _counts(db, owner, tid)
        assert bought == 0 and used == 0
    finally:
        _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
# unlock-state counts + verified-stays-verified
# ═══════════════════════════════════════════════════════════════════════════

def test_unlock_state_reports_unconsumed_and_counts(db, md_client, ent_client):
    """/unlock-state (via preview_state): unlocked=has unconsumed purchase;
    downloads_bought / downloads_used reflect the per-download accounting."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}state", price_tier=3)
        buyer = f"{TEST_PREFIX}state-buyer"
        _seed_user(db, buyer)

        # Before any purchase: locked, 0/0.
        s0 = pricing_svc.preview_state(buyer, tid)
        assert s0["is_paid"] is True
        assert s0["unlocked"] is False and s0["locked"] is True
        assert s0["downloads_bought"] == 0 and s0["downloads_used"] == 0

        # Buy → unlocked True, 1 bought / 0 used.
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}state-t1").status_code == 200
        s1 = pricing_svc.preview_state(buyer, tid)
        assert s1["unlocked"] is True and s1["locked"] is False
        assert s1["downloads_bought"] == 1 and s1["downloads_used"] == 0

        # Download + confirm → consumed: unlocked back to False, 1 bought / 1 used.
        st, dlid = _download(md_client, tid, buyer)
        assert st == 200
        assert _confirm(md_client, tid, buyer, dlid).get_json()["consumed"] is True
        s2 = pricing_svc.preview_state(buyer, tid)
        assert s2["unlocked"] is False and s2["locked"] is True
        assert s2["downloads_bought"] == 1 and s2["downloads_used"] == 1
    finally:
        _cleanup(db)


def test_verified_buyer_stays_verified_after_consume(db, md_client, ent_client):
    """A verified buyer stays verified after the purchase is consumed by a
    download (any purchase counts, D647/D660)."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}vfy", price_tier=3)
        buyer = f"{TEST_PREFIX}vfy-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}vfy-t1").status_code == 200

        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, tid) is True
        cur.close()

        # Consume the purchase with a confirmed download.
        st, dlid = _download(md_client, tid, buyer)
        assert st == 200
        assert _confirm(md_client, tid, buyer, dlid).get_json()["consumed"] is True

        # Still verified (the unlock row remains, only stamped consumed).
        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, tid) is True
        cur.close()

        # And a rating recorded now is still stored verified.
        rating_svc.record_listen(buyer, tid, 0)
        out = rating_svc.record_rating(buyer, tid, 9)
        assert out["verified"] is True
    finally:
        _cleanup(db)


# ─── small DB helper ──────────────────────────────────────────────────────────

def _counts(conn, user_id, tour_id):
    """(downloads_bought, downloads_used) straight from the DB for assertions."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), COUNT(consumed_at) FROM tour_unlocks "
        "WHERE user_id = %s AND tour_id = %s",
        (user_id, int(tour_id)),
    )
    row = cur.fetchone()
    cur.close()
    return (int(row[0]), int(row[1]))
