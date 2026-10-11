#!/usr/bin/env python3
"""test_local670b_listened_gate.py — LOCAL-670B.

Michael (2026-10-10): "Can we not allow rating if people did not listen to at
least 2 stops, similar to Audible, where they politely say that the user did
not hear enough to rate the tour?"

These tests exercise the SERVER half of that gate in tour_rating_service:

  * record_listen() is idempotent — finishing the same stop twice adds one row.
  * The rating POST (register_rating_routes) returns 403 `not_enough_listened`
    at 0 and 1 distinct listened stops, and 200 once 2 distinct stops are in.
  * A tour with fewer than 2 stops (stops_count = 1) is rateable after that one
    stop — the threshold is min(2, stops_count), never above the tour length.
  * A translation (original_tour_id set) maps to its SOURCE: a listen posted on
    the translation id counts toward the source's gate, and rating the source is
    unlocked by listens recorded on the translation.
  * The polite message carries the running count.

All DB rows use the TEST-670- user-id prefix and are deleted only by exact id
after a prefix check (no blanket DELETEs; never touches non-test rows).
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available  # noqa: E402
import tour_rating_service as svc  # noqa: E402

TEST_PREFIX = "TEST-670-"


# ─── Pure threshold rule (no DB for the arithmetic) ───────────────────────────

def test_required_is_two_for_a_normal_tour():
    assert svc.REQUIRED_LISTENED_STOPS == 2


# ─── DB-backed fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    # Self-healing DDL so the suite runs whether or not the migration was applied.
    cur = conn.cursor()
    svc._ensure_tour_listens_table(cur)
    conn.commit()
    cur.close()
    yield conn
    conn.close()


def _cleanup(conn):
    """Delete only our TEST-670- listen and rating rows, by exact id."""
    cur = conn.cursor()
    for table in ("tour_listens", "tour_ratings"):
        cur.execute(
            f"SELECT id, user_id FROM {table} WHERE user_id LIKE %s",
            (TEST_PREFIX + "%",),
        )
        ids = [row[0] for row in cur.fetchall() if row[1].startswith(TEST_PREFIX)]
        for i in ids:
            cur.execute(f"DELETE FROM {table} WHERE id = %s", (i,))
    conn.commit()
    cur.close()


def _seed_tour(conn, name, stops_count=None, original_tour_id=None,
               language="en", is_test=True):
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
         stops_count, is_test),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


def _rating_client():
    app = Flask(__name__)
    svc.register_rating_routes(app)
    return app.test_client()


# ─── record_listen idempotency ────────────────────────────────────────────────

def test_record_listen_is_idempotent(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 idempotent", stops_count=5)
        user = TEST_PREFIX + "idem"

        r1 = svc.record_listen(user, tid, 0)
        assert r1["listened_count"] == 1
        # Re-finishing the SAME stop must not add a second distinct stop.
        r2 = svc.record_listen(user, tid, 0)
        assert r2["listened_count"] == 1

        # A different stop advances the count.
        r3 = svc.record_listen(user, tid, 1)
        assert r3["listened_count"] == 2

        # Exactly one row per (tour,user,stop).
        cur = db.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tour_listens WHERE tour_id = %s AND user_id = %s",
            (tid, user),
        )
        assert cur.fetchone()[0] == 2
        cur.close()
    finally:
        _cleanup(db)


# ─── The 403 gate at 0 / 1 / 2 stops ──────────────────────────────────────────

def test_rating_blocked_at_zero_stops(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 zero", stops_count=5)
        client = _rating_client()
        resp = client.post(f"/tour/{tid}/rating",
                            json={"user_id": TEST_PREFIX + "z", "rating": 9})
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "not_enough_listened"
        assert body["required"] == 2
        assert body["listened_count"] == 0
        assert "0 so far" in body["message"]
    finally:
        _cleanup(db)


def test_rating_blocked_at_one_stop_with_count_in_message(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 one", stops_count=5)
        user = TEST_PREFIX + "one"
        svc.record_listen(user, tid, 0)

        client = _rating_client()
        resp = client.post(f"/tour/{tid}/rating",
                            json={"user_id": user, "rating": 8})
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "not_enough_listened"
        assert body["listened_count"] == 1
        assert body["required"] == 2
        assert "1 so far" in body["message"]
    finally:
        _cleanup(db)


def test_rating_allowed_at_two_stops(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 two", stops_count=5)
        user = TEST_PREFIX + "two"
        svc.record_listen(user, tid, 0)
        svc.record_listen(user, tid, 3)

        client = _rating_client()
        resp = client.post(f"/tour/{tid}/rating",
                            json={"user_id": user, "rating": 9})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["count"] == 1  # the rating landed
    finally:
        _cleanup(db)


# ─── A short tour: fewer than 2 stops needs ALL of them ───────────────────────

def test_one_stop_tour_is_rateable_after_one_stop(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 1-stop", stops_count=1)
        user = TEST_PREFIX + "short"

        # Required collapses to the tour length (1), not the global 2.
        cur = db.cursor()
        assert svc.required_listened_stops(cur, tid) == 1
        cur.close()

        client = _rating_client()
        # Still blocked at zero stops.
        resp0 = client.post(f"/tour/{tid}/rating",
                            json={"user_id": user, "rating": 7})
        assert resp0.status_code == 403

        # One stop is now enough.
        svc.record_listen(user, tid, 0)
        resp1 = client.post(f"/tour/{tid}/rating",
                            json={"user_id": user, "rating": 7})
        assert resp1.status_code == 200
    finally:
        _cleanup(db)


# ─── Translation maps to its source ───────────────────────────────────────────

def test_translation_listens_count_toward_source_gate(db):
    _cleanup(db)
    try:
        source = _seed_tour(db, "TEST-670 source", stops_count=5)
        translation = _seed_tour(db, "TEST-670 ru", stops_count=5,
                                 original_tour_id=source, language="ru")
        user = TEST_PREFIX + "trans"

        # Two listens posted on the TRANSLATION id...
        svc.record_listen(user, translation, 0)
        svc.record_listen(user, translation, 1)

        # ...unlock rating the SOURCE id (shared gate, like shared ratings).
        client = _rating_client()
        resp = client.post(f"/tour/{source}/rating",
                            json={"user_id": user, "rating": 10})
        assert resp.status_code == 200

        # And rating the translation id is equally unlocked.
        _cleanup(db)
        svc.record_listen(user, translation, 0)
        svc.record_listen(user, translation, 1)
        resp2 = client.post(f"/tour/{translation}/rating",
                            json={"user_id": user, "rating": 10})
        assert resp2.status_code == 200
    finally:
        _cleanup(db)


def test_listened_status_read_only(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 status", stops_count=5)
        user = TEST_PREFIX + "stat"
        svc.record_listen(user, tid, 2)
        info = svc.listened_status(user, tid)
        assert info["listened_count"] == 1
        assert info["required"] == 2
        assert info["enough"] is False
    finally:
        _cleanup(db)


# ─── stop_index validation ────────────────────────────────────────────────────

def test_record_listen_rejects_negative_stop(db):
    with pytest.raises(ValueError):
        svc.record_listen(TEST_PREFIX + "bad", 1, -1)


def test_listened_post_requires_stop_index(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 missing-arg", stops_count=5)
        client = _rating_client()
        resp = client.post(f"/tour/{tid}/listened",
                            json={"user_id": TEST_PREFIX + "m"})
        assert resp.status_code == 400
    finally:
        _cleanup(db)


if __name__ == "__main__":
    import unittest
    sys.exit(pytest.main([__file__, "-v"]))
