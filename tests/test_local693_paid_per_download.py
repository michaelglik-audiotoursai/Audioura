"""LOCAL-693 / LOCAL-693B — D660 (+ LEAD review): every download of a paid tour
is paid, consumption is decided SERVER-SIDE, and a failed download is restored
once.

LOCAL-693B LEAD review of 693: in 693 a purchase was consumed only when the app
called POST /tour/<id>/download-complete — a modified app (or a direct API call;
the gateway key ships in the app) could skip it and download forever. 693B moves
the decision server-side: map-delivery stamps consumed_at when the streaming
generator yields the LAST byte of the zip. A cut-off stream closes the generator
early (GeneratorExit) and never reaches that point, so a failed download still
never consumes (D660). The app no longer confirms success; it reports FAILURE
via POST /tour/<id>/download-failed, and the server restores that purchase ONCE,
only within 24h of consumption (second restore → 409; past 24h → 409).

Covers the ticket's test list:
  * buy → full download consumes → second download 402 → buy again → OK;
  * a cut-off stream (close the generator before the last byte) does NOT consume;
  * download-failed restores once (200), a second report 409, and a report past
    the 24h window 409;
  * two languages = two purchases (D653) consumed independently;
  * grandfathered (downloaded-while-free) and curator-own downloads never consume;
  * /unlock-state counts (downloads_bought / downloads_used);
  * a verified buyer stays verified after the purchase is consumed (D647/D660).

Harness mirrors tests/test_local677_paid_tours.py: an in-process Flask client for
map-delivery (map_delivery/app.py) and for the entitlements blueprint
(user-tracking/entitlements_api.py), both pointed at the test DB. Every row uses
a user_id / tour_name starting with 'TEST-693-'; cleanup deletes ONLY those rows.

Requires migrations 031 (consumed_at + partial active-unlock index) and 032
(restored_at); the services self-heal the schema, so the suite converges either
way.

[LOCAL-693B test isolation] This module OWNS its entitlements env: an autouse
fixture forces IAP_VERIFY_MODE=stub, empties GATEWAY_API_KEY and sets
ALLOW_UNAUTHENTICATED_ENTITLEMENTS before the entitlements module is imported,
and restores every variable on teardown — so it passes alone AND inside the
combined `pytest tests -k "677 or 686 or 690 or 691 or 693"` regardless of which
other module (595/604/596 set GATEWAY_API_KEY at import) ran first.
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

from db_connection import get_connection, check_db_available, get_database_url  # noqa: E402
import tour_pricing_service as pricing_svc  # noqa: E402
import tour_reviews_service as reviews_svc  # noqa: E402
import tour_rating_service as rating_svc  # noqa: E402

TEST_PREFIX = "TEST-693-"


# ─── [LOCAL-693B] own-your-env isolation ──────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    """Force the entitlements env this module needs and RESTORE it afterwards.

    Another module (e.g. test_local595_api / 604 / 596) sets GATEWAY_API_KEY and
    IAP_VERIFY_MODE unconditionally at import time and never restores them; with
    those set, our fresh import of entitlements_api would require an X-API-Key
    and reject our calls with 401. We save, force, and restore the three vars so
    this module is correct no matter the collection order — and we leave the env
    exactly as we found it so we do not poison anyone else."""
    keys = ("GATEWAY_API_KEY", "IAP_VERIFY_MODE", "ALLOW_UNAUTHENTICATED_ENTITLEMENTS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["GATEWAY_API_KEY"] = ""            # empty → unauth path allowed
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
    # ZIP_STORED (no compression) with sizeable payloads so a realistic zip spans
    # several 8KB stream chunks — the cut-off test then genuinely closes the
    # generator mid-stream, before the final byte, exercising the GeneratorExit
    # (no-consume) path rather than finishing in a single chunk.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("index.html", "<html><body>tour</body></html>")
        for i in range(1, num_stops + 1):
            zf.writestr(f"audio_{i}.mp3", (f"STOP-{i}-AUDIO-".encode() * 2048))
    return buf.getvalue()


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    # Ensure migrations 031 + 032 schema is present (the service self-heals too).
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)")
        cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ")
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
def md_module(db):
    md = _load_md()
    md.get_db_connection = lambda: psycopg2.connect(get_database_url())
    md.app.testing = True
    return md


@pytest.fixture(scope="module")
def md_client(md_module):
    return md_module.app.test_client()


@pytest.fixture(scope="module")
def ent_client(_isolate_entitlements_env):
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_693", os.path.join(ut_dir, "entitlements_api.py"))
    ea = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ea)
    # Belt-and-braces: the module caches API_KEY / IAP_VERIFY_MODE at import from
    # env. Pin them to this module's intent so a stale import order cannot leave
    # auth required or the verifier in 'apple' mode.
    ea.API_KEY = ""
    ea.IAP_VERIFY_MODE = "stub"
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
    """GET /download-tour and FULLY read the body (so the streaming generator
    runs to the last byte → server-side consume for a paid, unlocked download).
    Returns (status, consumes_header)."""
    r = md_client.get(f"/download-tour/{tour_id}?user_id={user_id}")
    body = r.get_data()  # drain the whole stream → generator reaches its end
    consumes = r.headers.get("X-Download-Consumes-Unlock", "") if r.status_code == 200 else ""
    assert body is not None
    return r.status_code, consumes


def _download_cutoff(md_module, tour_id, user_id):
    """Simulate a cut-off download: drive the Flask app's response generator and
    CLOSE it before the last byte, exactly as a client disconnect does. The
    generator's GeneratorExit path must then NOT consume the unlock.

    Returns the status code of the response (200 for a streamed paid download).
    """
    client = md_module.app.test_client()
    r = client.get(f"/download-tour/{tour_id}?user_id={user_id}",
                   buffered=False)
    if r.status_code != 200:
        r.close()
        return r.status_code
    # Pull ONE chunk, then close the iterator → raises GeneratorExit inside
    # generate() before the final byte is yielded.
    it = r.iter_encoded()
    try:
        next(it)  # first 8KB chunk (zip is larger split across chunks? ensure)
    except StopIteration:
        pass
    r.close()  # closes the underlying generator → GeneratorExit, no consume
    return 200


def _confirm_failed(md_client, tour_id, user_id, reason="save_or_validate_failed"):
    return md_client.post(
        f"/tour/{tour_id}/download-failed",
        json={"user_id": user_id, "reason": reason},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Core D660 lifecycle — consumption is SERVER-SIDE (full stream consumes)
# ═══════════════════════════════════════════════════════════════════════════

def test_buy_full_download_consumes_second_402_rebuy(db, md_client, ent_client):
    """buy → FULL download consumes server-side → second download 402 → buy
    again → download OK."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}cycle", price_tier=3)
        buyer = f"{TEST_PREFIX}cycle-buyer"
        _seed_user(db, buyer)

        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}cycle-t1").status_code == 200

        # Full download: the server consumes when it finishes streaming.
        st, consumes = _download(md_client, tid, buyer)
        assert st == 200
        assert consumes == "1", "a paid, unlocked download must declare it consumes"
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 1

        # Second download now refused — one download per buy, no app call needed.
        st2, _ = _download(md_client, tid, buyer)
        assert st2 == 402

        # Buy AGAIN → fresh active unlock → download OK, consumes again.
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}cycle-t2").status_code == 200
        st3, consumes3 = _download(md_client, tid, buyer)
        assert st3 == 200 and consumes3 == "1"
        bought, used = _counts(db, buyer, tid)
        assert bought == 2 and used == 2
    finally:
        _cleanup(db)


def test_cutoff_stream_does_not_consume(db, md_module, md_client, ent_client):
    """A cut-off stream (generator closed before the last byte) does NOT consume:
    the listener can download again, for free, until a full stream completes."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}cut", price_tier=3,
                                  num_stops=12)  # bigger zip → multiple chunks
        buyer = f"{TEST_PREFIX}cut-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}cut-t1").status_code == 200

        # Cut off mid-stream — nothing consumed.
        assert _download_cutoff(md_module, tid, buyer) == 200
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 0, "a cut-off stream must not consume"

        # Retry, still unconsumed → still allowed, for free.
        assert _download_cutoff(md_module, tid, buyer) == 200
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 0

        # Now a FULL download completes → consumed server-side.
        st, consumes = _download(md_client, tid, buyer)
        assert st == 200 and consumes == "1"
        bought, used = _counts(db, buyer, tid)
        assert bought == 1 and used == 1
        # And the next download is refused.
        assert _download(md_client, tid, buyer)[0] == 402
    finally:
        _cleanup(db)


def test_download_failed_restores_once_then_409(db, md_client, ent_client):
    """download-failed restores ONE consumed purchase (200), a second report for
    the same purchase is 409, and the restored purchase lets ONE more download
    through before it is consumed again."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}restore", price_tier=3)
        buyer = f"{TEST_PREFIX}restore-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}restore-t1").status_code == 200

        # Full download consumes server-side.
        assert _download(md_client, tid, buyer) == (200, "1")
        assert _counts(db, buyer, tid) == (1, 1)
        # Second download refused.
        assert _download(md_client, tid, buyer)[0] == 402

        # App reports the save FAILED → server restores the purchase once (200).
        r = _confirm_failed(md_client, tid, buyer)
        assert r.status_code == 200
        assert r.get_json()["restored"] is True
        # Restored → unconsumed again.
        assert _counts(db, buyer, tid) == (1, 0)

        # A SECOND failed report for the same (now already-restored) purchase 409.
        r2 = _confirm_failed(md_client, tid, buyer)
        assert r2.status_code == 409
        assert r2.get_json()["restored"] is False
        assert r2.get_json()["reason"] in ("not_consumed", "already_restored")

        # The restored purchase allows ONE more download, which consumes it.
        assert _download(md_client, tid, buyer) == (200, "1")
        assert _counts(db, buyer, tid) == (1, 1)

        # Now that it is consumed AGAIN but already restored once, a failed report
        # is refused: one restore per purchase.
        r3 = _confirm_failed(md_client, tid, buyer)
        assert r3.status_code == 409
        assert r3.get_json()["reason"] == "already_restored"
    finally:
        _cleanup(db)


def test_download_failed_past_24h_is_409(db, md_client, ent_client):
    """A failed report is refused (409) when the consumption is older than the
    24h restore window."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}old", price_tier=3)
        buyer = f"{TEST_PREFIX}old-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}old-t1").status_code == 200

        # Full download consumes.
        assert _download(md_client, tid, buyer) == (200, "1")
        # Backdate the consumption to 25h ago → outside the window.
        cur = db.cursor()
        cur.execute(
            "UPDATE tour_unlocks SET consumed_at = NOW() - INTERVAL '25 hours' "
            "WHERE user_id = %s AND tour_id = %s AND consumed_at IS NOT NULL",
            (buyer, int(tid)),
        )
        db.commit()
        cur.close()

        r = _confirm_failed(md_client, tid, buyer)
        assert r.status_code == 409
        assert r.get_json()["reason"] == "window_expired"
        # Still consumed — not restored.
        assert _counts(db, buyer, tid) == (1, 1)
    finally:
        _cleanup(db)


def test_download_failed_without_consumption_is_409(db, md_client, ent_client):
    """A failed report with nothing consumed (e.g. the download never completed)
    is a 409 — there is no purchase to restore."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}none", price_tier=3)
        buyer = f"{TEST_PREFIX}none-buyer"
        _seed_user(db, buyer)
        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}none-t1").status_code == 200
        # No download happened → nothing consumed.
        r = _confirm_failed(md_client, tid, buyer)
        assert r.status_code == 409
        assert r.get_json()["reason"] == "not_consumed"
        assert _counts(db, buyer, tid) == (1, 0)
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

        # Full download ENGLISH → consumes EN only.
        assert _download(md_client, en, buyer) == (200, "1")
        assert _download(md_client, en, buyer)[0] == 402
        # Russian still downloads (its own unconsumed unlock) → consumes RU.
        assert _download(md_client, ru, buyer) == (200, "1")
        assert _download(md_client, ru, buyer)[0] == 402
    finally:
        _cleanup(db)


def test_grandfathered_download_never_consumes(db, md_client):
    """A grandfathered (downloaded-while-free) user keeps downloading after the
    tour is priced, with no unlock involved (consumes header '0')."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}gf")  # free at first
        user = f"{TEST_PREFIX}gf-user"
        _seed_user(db, user)
        st, consumes = _download(md_client, tid, user)
        assert st == 200 and consumes == "0"

        cur = db.cursor()
        cur.execute("UPDATE audio_tours SET price_tier = 3 WHERE id = %s", (tid,))
        db.commit()
        cur.close()

        for _ in range(3):
            st, consumes = _download(md_client, tid, user)
            assert st == 200 and consumes == "0"
        bought, used = _counts(db, user, tid)
        assert bought == 0 and used == 0
    finally:
        _cleanup(db)


def test_curator_download_never_consumes(db, md_client):
    """The curator downloads their own paid tour unpriced and unconsumed
    (consumes header '0')."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}own", price_tier=3)
        owner = f"{TEST_PREFIX}own-owner"
        _seed_creator(db, tid, owner)
        for _ in range(2):
            st, consumes = _download(md_client, tid, owner)
            assert st == 200 and consumes == "0"
        bought, used = _counts(db, owner, tid)
        assert bought == 0 and used == 0
    finally:
        _cleanup(db)


# ═══════════════════════════════════════════════════════════════════════════
# unlock-state counts + verified-stays-verified
# ═══════════════════════════════════════════════════════════════════════════

def test_unlock_state_reports_unconsumed_and_counts(db, md_client, ent_client):
    """preview_state: unlocked=has unconsumed purchase; downloads_bought /
    downloads_used reflect the per-download accounting."""
    _cleanup(db)
    try:
        tid = _seed_tour_with_zip(db, f"{TEST_PREFIX}state", price_tier=3)
        buyer = f"{TEST_PREFIX}state-buyer"
        _seed_user(db, buyer)

        s0 = pricing_svc.preview_state(buyer, tid)
        assert s0["is_paid"] is True
        assert s0["unlocked"] is False and s0["locked"] is True
        assert s0["downloads_bought"] == 0 and s0["downloads_used"] == 0

        assert _buy(ent_client, buyer, tid, f"{TEST_PREFIX}state-t1").status_code == 200
        s1 = pricing_svc.preview_state(buyer, tid)
        assert s1["unlocked"] is True and s1["locked"] is False
        assert s1["downloads_bought"] == 1 and s1["downloads_used"] == 0

        # Full download consumes server-side.
        assert _download(md_client, tid, buyer) == (200, "1")
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

        # Consume the purchase with a full download.
        assert _download(md_client, tid, buyer) == (200, "1")

        cur = db.cursor()
        assert reviews_svc.compute_verified(cur, buyer, tid) is True
        cur.close()

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
