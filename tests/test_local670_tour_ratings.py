"""
LOCAL-670 — Tour ratings (1–10) tests.

Covers:
  1. The pure score rule (compute_score): 0/1/3/4/7 ratings, the median switch,
     half-up rounding, and the brief's worked example (7.5 & 9 → 8.3).
  2. record_rating / get_rating against the DB: insert, aggregate, REPLACE on
     re-rate, and TRANSLATION → source mapping (a rating of the translation
     counts for the original).
  3. The orchestrator endpoints POST/GET /tour/<id>/rating via an in-process
     Flask test client (register_rating_routes on a fresh app — no running
     service, so this is not a @service test).
  4. map-delivery's min_rating filter and rating_* fields via the map_delivery
     app's Flask test client.

Safety (ticket §6): every rating row written here uses a user_id starting with
'TEST-670-'. Cleanup deletes ONLY rows whose user_id has that exact prefix,
by exact id. No other table is touched destructively.
"""

import os
import sys
import importlib.util

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available  # noqa: E402
import tour_rating_service as svc  # noqa: E402

TEST_PREFIX = "TEST-670-"


# ─── 1. Pure score rule (no DB) ───────────────────────────────────────────────

def test_zero_ratings_is_default_new():
    r = svc.compute_score([])
    assert r == {"score": 7.5, "count": 0, "label": "New"}


def test_one_rating_blends_the_prior_brief_example():
    # The brief: "7.5 and 9 → 8.3" — one real 9, blended with the 7.5 prior.
    r = svc.compute_score([9])
    assert r["score"] == 8.3
    assert r["count"] == 1
    assert r["label"] == "1 rating"


def test_three_ratings_still_average_including_prior():
    # 1..3 ratings → average of (7.5 + ratings). mean(7.5,6,7,8)=7.125 → 7.1.
    r = svc.compute_score([6, 7, 8])
    assert r["score"] == 7.1
    assert r["count"] == 3
    assert r["label"] == "3 ratings"


def test_four_ratings_switches_to_median_of_real_only():
    # >= 4 → median of the real ratings only, prior dropped.
    # [1,9,9,10] median = (9+9)/2 = 9.0 (the 7.5 is NOT included).
    r = svc.compute_score([1, 9, 9, 10])
    assert r["score"] == 9.0
    assert r["count"] == 4


def test_seven_ratings_median_odd_count():
    # [1,2,8,9,10,10,10] sorted → middle element = 9.
    r = svc.compute_score([10, 1, 9, 2, 10, 8, 10])
    assert r["score"] == 9.0
    assert r["count"] == 7


def test_median_drops_the_prior_so_a_low_outlier_cannot_sink_a_good_tour():
    # Four 10s and one 1: median is 10 (robust), not dragged down by the 1,
    # and the 7.5 prior is gone at >= 4.
    r = svc.compute_score([10, 10, 10, 10, 1])
    assert r["score"] == 10.0


def test_half_up_rounding():
    # mean(7.5, 9) = 8.25 → half-up → 8.3 (not 8.2).
    assert svc.compute_score([9])["score"] == 8.3


# ─── DB-backed fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def _force_test_db_target():
    """[LOCAL-675 item 4] Belt-and-braces isolation: force this module's DB-backed
    tests at the TEST database regardless of what an earlier module left in the
    environment. test_local447/448 (and others) set AUDIOURA_DB_TARGET=production
    or DB_NAME=audiotours; AUDIOURA_DB_TARGET outranks pytest auto-detection in
    db_connection, so a leaked value routed these tests at production and the
    conftest write-guard raised ProductionWriteGuardError at setup. We pin the
    test target here and restore the prior environment afterwards, so the module
    is green both alone and in the full `pytest tests` run."""
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
    yield conn
    conn.close()


def _cleanup(conn):
    """Delete only our TEST-670- rows, by exact id after a prefix check.

    Covers tour_ratings and, since LOCAL-670B gated the rating POST behind
    listened stops, tour_listens too (the endpoint test records a couple).
    tour_listens may not exist on an older schema — guarded so cleanup never
    fails the suite.
    """
    cur = conn.cursor()
    cur.execute("SELECT id, user_id FROM tour_ratings WHERE user_id LIKE %s",
                (TEST_PREFIX + "%",))
    ids = [row[0] for row in cur.fetchall() if row[1].startswith(TEST_PREFIX)]
    for i in ids:
        cur.execute("DELETE FROM tour_ratings WHERE id = %s", (i,))
    try:
        cur.execute("SELECT id, user_id FROM tour_listens WHERE user_id LIKE %s",
                    (TEST_PREFIX + "%",))
        lids = [row[0] for row in cur.fetchall() if row[1].startswith(TEST_PREFIX)]
        for i in lids:
            cur.execute("DELETE FROM tour_listens WHERE id = %s", (i,))
    except Exception:
        conn.rollback()
    conn.commit()
    cur.close()


def _seed_tour(conn, name, original_tour_id=None, language="en", is_test=True):
    """Insert a minimal audio_tours row (test DB only) and return its id.

    is_test defaults True (hidden from /tours-near, fine for direct /tour-info
    and rating reads). Pass is_test=False for the /tours-near list test, which
    filters out test tours.
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id, is_test),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


# ─── 2. record_rating / get_rating against the DB ─────────────────────────────

def test_record_and_get_roundtrip(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 roundtrip tour")

        # 0 ratings → default.
        assert svc.get_rating(tid) == {"score": 7.5, "count": 0, "label": "New"}

        # One rating of 9 → 8.3.
        out = svc.record_rating(f"{TEST_PREFIX}a", tid, 9)
        assert out["score"] == 8.3 and out["count"] == 1

        # Second user rates 10 → mean(7.5,9,10)=8.83..→8.8.
        out = svc.record_rating(f"{TEST_PREFIX}b", tid, 10)
        assert out["count"] == 2 and out["score"] == 8.8

        assert svc.get_rating(tid)["count"] == 2
    finally:
        _cleanup(db)


def test_rerate_replaces_not_appends(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 rerate tour")
        svc.record_rating(f"{TEST_PREFIX}c", tid, 9)
        out = svc.record_rating(f"{TEST_PREFIX}c", tid, 2)  # same user re-rates
        # Still ONE rating (replaced), now mean(7.5, 2) = 4.75 → 4.8.
        assert out["count"] == 1
        assert out["score"] == 4.8
    finally:
        _cleanup(db)


def test_invalid_ratings_rejected(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 invalid tour")
        for bad in (0, 11, -3, 5.5, "x"):
            with pytest.raises(ValueError):
                svc.record_rating(f"{TEST_PREFIX}bad", tid, bad)
    finally:
        _cleanup(db)


def test_translation_shares_source_ratings(db):
    _cleanup(db)
    try:
        orig = _seed_tour(db, "TEST-670 source tour")
        trans = _seed_tour(db, "TEST-670 russian copy",
                           original_tour_id=orig, language="ru")

        # Rate via the TRANSLATION id — it must count for the source.
        svc.record_rating(f"{TEST_PREFIX}t1", trans, 8)
        # Rate the ORIGINAL directly too.
        svc.record_rating(f"{TEST_PREFIX}t2", orig, 6)

        via_source = svc.get_rating(orig)
        via_translation = svc.get_rating(trans)
        # Both report the SAME aggregate (2 ratings), proving the mapping.
        assert via_source == via_translation
        assert via_source["count"] == 2
    finally:
        _cleanup(db)


# ─── 3. Orchestrator endpoints (in-process Flask client) ──────────────────────

@pytest.fixture(scope="module")
def orchestrator_client():
    from flask import Flask
    app = Flask(__name__)
    svc.register_rating_routes(app)
    return app.test_client()


def test_endpoint_post_then_get(db, orchestrator_client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 endpoint tour")

        # [LOCAL-670B] The rating POST is now gated behind >= 2 listened stops.
        # Record two so this endpoint test exercises the record/read path it is
        # about, not the gate (which has its own suite).
        svc.record_listen(f"{TEST_PREFIX}ep", tid, 0)
        svc.record_listen(f"{TEST_PREFIX}ep", tid, 1)

        resp = orchestrator_client.post(
            f"/tour/{tid}/rating",
            json={"user_id": f"{TEST_PREFIX}ep", "rating": 9},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["score"] == 8.3 and body["count"] == 1

        resp = orchestrator_client.get(f"/tour/{tid}/rating")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1
    finally:
        _cleanup(db)


def test_endpoint_rejects_bad_rating(db, orchestrator_client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 endpoint bad tour")
        resp = orchestrator_client.post(
            f"/tour/{tid}/rating",
            json={"user_id": f"{TEST_PREFIX}ep", "rating": 99},
        )
        assert resp.status_code == 400
        # Missing user_id.
        resp = orchestrator_client.post(f"/tour/{tid}/rating", json={"rating": 5})
        assert resp.status_code == 400
    finally:
        _cleanup(db)


# ─── 4. map-delivery rating fields + min_rating filter ────────────────────────

@pytest.fixture(scope="module")
def md_module():
    """Load map_delivery/app.py and point its DB at the test database."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "map_delivery", "app.py")
    spec = importlib.util.spec_from_file_location("md_app_local670", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    md.get_db_connection = lambda: get_connection()
    # Reset the cached table-presence probe so it re-checks on the test DB.
    md._HAS_TOUR_RATINGS = None
    # The map-delivery queries LEFT JOIN audio_tour_versions (LOCAL-657/666),
    # which the truncated test DB may not have. Ensure a minimal, additive copy
    # exists so the join resolves — test-only setup, never touches production.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audio_tour_versions (
            id SERIAL PRIMARY KEY,
            tour_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            replaced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    return md


def test_map_delivery_rating_fields_and_min_rating(db, md_module):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 md tour", is_test=False)
        # 9 and 10 → 8.8.
        svc.record_rating(f"{TEST_PREFIX}m1", tid, 9)
        svc.record_rating(f"{TEST_PREFIX}m2", tid, 10)

        client = md_module.app.test_client()

        # tour-info carries the rating fields.
        info = client.get(f"/tour-info/{tid}").get_json()
        assert info["rating_score"] == 8.8
        assert info["rating_count"] == 2
        assert info["rating_label"] == "2 ratings"

        # tours-near includes it (test tour is at 43.70,7.26).
        near = client.get("/tours-near/43.70/7.26?radius=5").get_json()
        ids = {t["id"] for t in near["tours"]}
        assert tid in ids

        # min_rating=9 excludes an 8.8 tour; min_rating=8 includes it.
        near9 = client.get("/tours-near/43.70/7.26?radius=5&min_rating=9").get_json()
        assert tid not in {t["id"] for t in near9["tours"]}
        near8 = client.get("/tours-near/43.70/7.26?radius=5&min_rating=8").get_json()
        assert tid in {t["id"] for t in near8["tours"]}
    finally:
        _cleanup(db)


def test_map_delivery_unrated_tour_is_default(db, md_module):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-670 md unrated tour")
        client = md_module.app.test_client()
        info = client.get(f"/tour-info/{tid}").get_json()
        assert info["rating_score"] == 7.5
        assert info["rating_count"] == 0
        assert info["rating_label"] == "New"
    finally:
        _cleanup(db)
