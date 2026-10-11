#!/usr/bin/env python3
"""test_local670c_sync.py — LOCAL-670C server batch sync (POST /sync).

Michael (2026-10-10): tours play fully offline, so the app records "listened",
ratings, reviews and per-stop thumbs LOCALLY and ships them in one batch when a
connection returns. This suite exercises the SERVER half:

  * idempotency on the client UUID — re-sending an item is a no-op "duplicate";
  * an offline listen-then-rate pair in ONE batch is accepted together (the
    670B gate counts the batch's own listens);
  * a timestamp more than 10 minutes in the future is rejected;
  * a `listened` event for a stop the tour does not have is rejected;
  * a translation id maps to its SOURCE (670B rule);
  * D650 — a `thumb` is accepted as an internal signal and never touches the
    tour's 1–10 score.

Pure helpers (future-skew, timestamp parse, ordering) run with NO database. The
DB-backed cases skip cleanly when the database is unavailable, exactly like the
670B suite, and only ever delete their own TEST-670C- rows by exact id.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available  # noqa: E402
import tour_rating_service as svc  # noqa: E402

TEST_PREFIX = "TEST-670C-"


# ─── Pure helpers (no DB) ─────────────────────────────────────────────────────

def test_future_skew_rule():
    now = datetime(2026, 10, 11, 1, 0, 0, tzinfo=timezone.utc)
    assert svc._is_future_skew(now + timedelta(minutes=5), now) is False
    assert svc._is_future_skew(now + timedelta(minutes=11), now) is True
    assert svc._is_future_skew(now - timedelta(days=1), now) is False
    assert svc._is_future_skew(None, now) is False  # missing ts is not future


def test_parse_created_at_handles_z_suffix():
    dt = svc._parse_created_at("2026-10-11T01:02:03.000Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 1 and dt.minute == 2
    assert svc._parse_created_at(None) is None
    assert svc._parse_created_at("not-a-date") is None


def test_listens_ordered_before_ratings():
    r = svc._sync_order_rank
    assert r("listened") < r("thumb") < r("rating")
    assert r("listened") < r("review") < r("rating")


# ─── DB-backed fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _force_test_db_target():
    """[LOCAL-675 item 4] Belt-and-braces isolation (matches test_local670 /
    test_local670b): force this module's DB-backed tests at the TEST database
    regardless of what an earlier module left in the environment. test_local447/448
    set AUDIOURA_DB_TARGET=production, which outranks pytest auto-detection in
    db_connection and tripped the conftest production-write guard here (green
    alone, ERROR in the full `pytest tests` run — the same family of leak the
    Addendum flags for this file after the LOCAL-672 merge). Restored afterwards
    so nothing leaks onward."""
    _saved = {k: os.environ.get(k) for k in
              ("AUDIOURA_DB_TARGET", "DB_NAME", "DATABASE_URL")}
    os.environ["AUDIOURA_DB_TARGET"] = "test"
    os.environ.pop("DB_NAME", None)       # don't let a leaked explicit name win
    os.environ.pop("DATABASE_URL", None)  # nor a leaked full URL
    yield
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def db(_force_test_db_target):
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    cur = conn.cursor()
    svc._ensure_tour_listens_table(cur)
    svc._ensure_sync_tables(cur)
    conn.commit()
    cur.close()
    yield conn
    conn.close()


def _cleanup(conn):
    """Delete only our TEST-670C- rows, by exact id."""
    cur = conn.cursor()
    for table in ("tour_listens", "tour_ratings", "tour_review_sync",
                  "user_stop_feedback", "sync_items"):
        try:
            cur.execute(
                f"SELECT user_id FROM {table} WHERE user_id LIKE %s",
                (TEST_PREFIX + "%",),
            )
        except Exception:  # noqa: BLE001 — table may not exist on a bare DB
            conn.rollback()
            continue
        # Delete by the same predicate (all our rows carry the prefix in user_id).
        cur.execute(
            f"DELETE FROM {table} WHERE user_id LIKE %s",
            (TEST_PREFIX + "%",),
        )
    conn.commit()
    cur.close()


def _seed_tour(conn, name, stops_count=None, original_tour_id=None,
               language="en"):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id,
                                 stops_count, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id,
         stops_count, True),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


# ─── Idempotency ──────────────────────────────────────────────────────────────

def test_batch_is_idempotent_on_client_uuid(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C idem", stops_count=5)
        user = TEST_PREFIX + "idem"
        items = [
            {"client_uuid": "c-idem-1", "type": "listened",
             "user_id": user, "tour_id": str(tid), "stop_index": 0},
        ]
        r1 = svc.process_sync_batch(user, items)
        assert r1["results"][0]["status"] == "accepted"

        # Re-send the SAME item → duplicate, and still exactly one listen row.
        r2 = svc.process_sync_batch(user, items)
        assert r2["results"][0]["status"] == "duplicate"

        cur = db.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tour_listens WHERE tour_id=%s AND user_id=%s",
            (tid, user),
        )
        assert cur.fetchone()[0] == 1
        cur.close()
    finally:
        _cleanup(db)


# ─── listen + rate in one batch ───────────────────────────────────────────────

def test_offline_listen_then_rate_accepted_together(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C listen+rate", stops_count=5)
        user = TEST_PREFIX + "lr"
        items = [
            # Deliberately give the rating FIRST in the payload; the server
            # applies listens before ratings so the gate counts them in-batch.
            {"client_uuid": "c-r", "type": "rating",
             "user_id": user, "tour_id": str(tid), "rating": 9},
            {"client_uuid": "c-l0", "type": "listened",
             "user_id": user, "tour_id": str(tid), "stop_index": 0},
            {"client_uuid": "c-l1", "type": "listened",
             "user_id": user, "tour_id": str(tid), "stop_index": 1},
        ]
        res = svc.process_sync_batch(user, items)
        status = {r["client_uuid"]: r["status"] for r in res["results"]}
        assert status["c-l0"] == "accepted"
        assert status["c-l1"] == "accepted"
        assert status["c-r"] == "accepted"  # gate satisfied by this batch

        # The rating really landed.
        rating = svc.get_rating(tid)
        assert rating["count"] == 1
    finally:
        _cleanup(db)


def test_rate_without_enough_listens_is_rejected(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C rate-only", stops_count=5)
        user = TEST_PREFIX + "ro"
        items = [
            {"client_uuid": "c-ro-l", "type": "listened",
             "user_id": user, "tour_id": str(tid), "stop_index": 0},
            {"client_uuid": "c-ro-r", "type": "rating",
             "user_id": user, "tour_id": str(tid), "rating": 8},
        ]
        res = svc.process_sync_batch(user, items)
        status = {r["client_uuid"]: r["status"] for r in res["results"]}
        assert status["c-ro-l"] == "accepted"
        # Only 1 listen < required 2 → the rating is rejected (invalid).
        assert status["c-ro-r"] == "invalid"
        assert svc.get_rating(tid)["count"] == 0
    finally:
        _cleanup(db)


# ─── Rejections: future skew & nonexistent stop ───────────────────────────────

def test_future_timestamp_rejected(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C future", stops_count=5)
        user = TEST_PREFIX + "fut"
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        items = [
            {"client_uuid": "c-fut", "type": "listened", "created_at": future,
             "user_id": user, "tour_id": str(tid), "stop_index": 0},
        ]
        res = svc.process_sync_batch(user, items)
        assert res["results"][0]["status"] == "invalid"

        cur = db.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tour_listens WHERE tour_id=%s AND user_id=%s",
            (tid, user),
        )
        assert cur.fetchone()[0] == 0  # nothing written
        cur.close()
    finally:
        _cleanup(db)


def test_listen_for_nonexistent_stop_rejected(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C badstop", stops_count=3)
        user = TEST_PREFIX + "bs"
        items = [
            # stop_index 9 does not exist in a 3-stop tour.
            {"client_uuid": "c-bs", "type": "listened",
             "user_id": user, "tour_id": str(tid), "stop_index": 9},
        ]
        res = svc.process_sync_batch(user, items)
        assert res["results"][0]["status"] == "invalid"
    finally:
        _cleanup(db)


# ─── Translation maps to source ───────────────────────────────────────────────

def test_translation_listens_count_toward_source(db):
    _cleanup(db)
    try:
        source = _seed_tour(db, "TEST-670C src", stops_count=5)
        translation = _seed_tour(db, "TEST-670C ru", stops_count=5,
                                 original_tour_id=source, language="ru")
        user = TEST_PREFIX + "tr"
        items = [
            {"client_uuid": "c-tr-l0", "type": "listened",
             "user_id": user, "tour_id": str(translation), "stop_index": 0},
            {"client_uuid": "c-tr-l1", "type": "listened",
             "user_id": user, "tour_id": str(translation), "stop_index": 1},
            {"client_uuid": "c-tr-r", "type": "rating",
             "user_id": user, "tour_id": str(source), "rating": 10},
        ]
        res = svc.process_sync_batch(user, items)
        status = {r["client_uuid"]: r["status"] for r in res["results"]}
        assert status["c-tr-r"] == "accepted"
        # Rating keyed on the SOURCE id.
        assert svc.get_rating(source)["count"] == 1
    finally:
        _cleanup(db)


# ─── D650: a thumb is an internal signal, never the tour score ────────────────

def test_thumb_accepted_and_not_in_tour_score(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C thumb", stops_count=5)
        user = TEST_PREFIX + "th"
        items = [
            {"client_uuid": "c-th", "type": "thumb",
             "user_id": user, "tour_id": str(tid), "stop_index": 0,
             "swipe": 1, "class_details": 0.5, "class_historic": 0.3,
             "class_social": 0.2, "i_con": 4.0},
        ]
        res = svc.process_sync_batch(user, items)
        assert res["results"][0]["status"] == "accepted"
        # D650: the per-stop thumb must NOT create any tour rating.
        assert svc.get_rating(tid)["count"] == 0
    finally:
        _cleanup(db)


# ─── review is stored (nothing is lost before LOCAL-672) ──────────────────────

def test_review_is_stored(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670C review", stops_count=5)
        user = TEST_PREFIX + "rv"
        items = [
            {"client_uuid": "c-rv", "type": "review",
             "user_id": user, "tour_id": str(tid),
             "review": "Loved the harbour stop."},
        ]
        res = svc.process_sync_batch(user, items)
        assert res["results"][0]["status"] == "accepted"

        cur = db.cursor()
        cur.execute(
            "SELECT review FROM tour_review_sync WHERE tour_id=%s AND user_id=%s",
            (tid, user),
        )
        row = cur.fetchone()
        assert row is not None and "harbour" in row[0]
        cur.close()
    finally:
        _cleanup(db)


# ─── Route-level smoke (no DB write needed for a 400) ─────────────────────────

def _client():
    app = Flask(__name__)
    svc.register_rating_routes(app)
    return app.test_client()


def test_sync_route_requires_items_list():
    client = _client()
    resp = client.post("/sync", json={"user_id": "u"})
    assert resp.status_code == 400

    resp2 = client.post("/sync", json={"user_id": "u", "items": "notalist"})
    assert resp2.status_code == 400


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
