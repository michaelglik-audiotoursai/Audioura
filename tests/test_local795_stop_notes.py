"""
LOCAL-795 — Per-stop notes ("Tell us about this place") tests.

Covers the ticket's server test list:
  * note insert — a clean note is stored `approved`, a flagged one `pending`
    with its reason (same auto-check as reviews, reused);
  * validation — empty / too-long text, a negative stop index;
  * unknown tour — a note on a tour id with no audio_tours row is rejected;
  * rate limit — at most 10 notes per user per 24 h (the 11th is refused);
  * the orchestrator endpoint POST /tour/<id>/stop/<n>/note (success + the
    user_id-required and validation 400s).

Safety: every row written here uses a user_id starting with 'TEST-795-'.
Cleanup deletes ONLY rows whose user_id has that exact prefix, by exact id,
across stop_notes, tour_requests and users. No other table is touched
destructively, and the suite skips entirely when the DB is unavailable.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available  # noqa: E402
import tour_reviews_service as reviews_svc  # noqa: E402

TEST_PREFIX = "TEST-795-"


# ─── 1. Pure validation (no DB) ───────────────────────────────────────────────

def test_validate_note_text_rejects_empty_and_too_long():
    with pytest.raises(ValueError):
        reviews_svc._validate_note_text(None)
    with pytest.raises(ValueError):
        reviews_svc._validate_note_text("   ")
    with pytest.raises(ValueError):
        reviews_svc._validate_note_text("x" * (reviews_svc.NOTE_MAX_CHARS + 1))
    # Exactly at the limit is fine; whitespace is trimmed.
    ok = reviews_svc._validate_note_text("  hello  ")
    assert ok == "hello"
    assert len(reviews_svc._validate_note_text("x" * reviews_svc.NOTE_MAX_CHARS)) \
        == reviews_svc.NOTE_MAX_CHARS


def test_validate_stop_index_rejects_negative_and_nonint():
    assert reviews_svc._validate_stop_index(0) == 0
    assert reviews_svc._validate_stop_index("3") == 3
    with pytest.raises(ValueError):
        reviews_svc._validate_stop_index(-1)
    with pytest.raises(ValueError):
        reviews_svc._validate_stop_index("abc")


# ─── DB-backed fixtures ────────────────────────────────────────────────────────

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
        ("stop_notes", "user_id"),
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
    cur.close()


def _seed_tour(conn, name, original_tour_id=None, language="en"):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


def _count_notes(conn, tour_id, user_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM stop_notes WHERE tour_id = %s AND user_id = %s",
        (int(tour_id), user_id),
    )
    n = cur.fetchone()[0]
    cur.close()
    return int(n)


# ─── 2. Insert + moderation status ────────────────────────────────────────────

def test_clean_note_is_approved_and_stored(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-795 clean tour")
        user = f"{TEST_PREFIX}clean"
        out = reviews_svc.submit_stop_note(
            user, tid, 2, "The balcony view over the river was the highlight.",
            stop_title="River Balcony", language="en")
        assert out["note_status"] == "approved"
        assert out["stop_index"] == 2
        assert out["stop_title"] == "River Balcony"
        assert out["language"] == "en"
        assert out["tour_id"] == tid
        assert _count_notes(db, tid, user) == 1
    finally:
        _cleanup(db)


def test_flagged_note_is_held_pending(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-795 flagged tour")
        user = f"{TEST_PREFIX}flag"
        out = reviews_svc.submit_stop_note(
            user, tid, 0, "see more at www.spam.com")
        assert out["note_status"] == "pending"
        assert out["status_reason"] == "url"
        # It is still stored (held for the LEAD queue, not dropped).
        assert _count_notes(db, tid, user) == 1
    finally:
        _cleanup(db)


# ─── 3. Unknown tour is rejected ──────────────────────────────────────────────

def test_note_on_unknown_tour_rejected(db):
    _cleanup(db)
    try:
        user = f"{TEST_PREFIX}unknown"
        # An id that does not exist in audio_tours.
        with pytest.raises(ValueError):
            reviews_svc.submit_stop_note(user, 999999999, 0, "ghost tour note")
    finally:
        _cleanup(db)


# ─── 4. Rate limit (10/day/user) ──────────────────────────────────────────────

def test_rate_limit_blocks_the_eleventh_note(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-795 ratelimit tour")
        user = f"{TEST_PREFIX}rl"
        # The first NOTE_RATE_LIMIT succeed...
        for i in range(reviews_svc.NOTE_RATE_LIMIT):
            reviews_svc.submit_stop_note(user, tid, i, f"note {i}")
        assert _count_notes(db, tid, user) == reviews_svc.NOTE_RATE_LIMIT
        # ...the next one is refused.
        with pytest.raises(ValueError):
            reviews_svc.submit_stop_note(user, tid, 99, "one too many")
        assert _count_notes(db, tid, user) == reviews_svc.NOTE_RATE_LIMIT
    finally:
        _cleanup(db)


# ─── 5. Translation maps to the original tour ─────────────────────────────────

def test_note_on_translation_keys_on_original(db):
    _cleanup(db)
    try:
        orig = _seed_tour(db, "TEST-795 original", language="en")
        trans = _seed_tour(db, "TEST-795 russian", original_tour_id=orig,
                           language="ru")
        user = f"{TEST_PREFIX}xlat"
        out = reviews_svc.submit_stop_note(
            user, trans, 1, "Отличная остановка", language="ru")
        # Stored under the ORIGINAL id, but the listener's language is kept.
        assert out["tour_id"] == orig
        assert out["language"] == "ru"
        assert _count_notes(db, orig, user) == 1
        assert _count_notes(db, trans, user) == 0
    finally:
        _cleanup(db)


# ─── 6. Orchestrator endpoint ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from flask import Flask
    app = Flask(__name__)
    reviews_svc.register_review_routes(app)
    return app.test_client()


def test_endpoint_submits_a_note(db, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-795 endpoint tour")
        user = f"{TEST_PREFIX}ep"
        r = client.post(
            f"/tour/{tid}/stop/3/note",
            json={"user_id": user, "note_text": "Loved the mosaics here.",
                  "stop_title": "Mosaic Hall", "language": "en"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["note_status"] == "approved"
        assert body["stop_index"] == 3
        assert _count_notes(db, tid, user) == 1
    finally:
        _cleanup(db)


def test_endpoint_requires_user_id_and_text(db, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-795 endpoint 400 tour")
        # Missing user_id → 400.
        r = client.post(f"/tour/{tid}/stop/0/note",
                        json={"note_text": "no user"})
        assert r.status_code == 400
        # Empty text → 400.
        r = client.post(f"/tour/{tid}/stop/0/note",
                        json={"user_id": f"{TEST_PREFIX}ep400", "note_text": "   "})
        assert r.status_code == 400
        # No JSON body → 400.
        r = client.post(f"/tour/{tid}/stop/0/note")
        assert r.status_code == 400
    finally:
        _cleanup(db)
