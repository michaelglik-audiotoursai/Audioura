"""
LOCAL-688 — "Why this score" + public page + stable scores + one free re-score.

No paid API calls: tour_editor_score.judge is monkeypatched to a canned grader,
so the 3-run averaging, the mapping and the detail JSON shape are tested without
touching OpenAI.

Groups:
  1. Stable scores (pure)   — three runs averaged per criterion before mapping;
     mapping unchanged (reuses LOCAL-685 bounds); detail JSON carries every run,
     a rubric_version and the evidence/summary.
  2. /how-we-score (pure)   — 200, HTML, contains all five criteria + the
     range rationale and the listener-takeover / free / re-score copy.
  3. score-explanation (DB) — an original returns its block; a translation
     returns the ORIGINAL's block (same score); an unscored tour → 404.
  4. rescore-request (DB)   — the owner may request once per content version;
     a second request for the SAME version → 409; a non-owner → 403; the score
     is cleared and the version stamped.

Safety: every DB row uses a tour_name / user_id starting with 'TEST-688-';
cleanup deletes ONLY those rows, by exact id after a prefix re-check. Never
touches another tour. DB tests skip when the database is unavailable.
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import tour_editor_score as tes  # noqa: E402

TEST_PREFIX = "TEST-688-"


# ─── canned grader (no OpenAI) ────────────────────────────────────────────────

class _Usage:
    def __init__(self, pin=100, pout=20):
        self.prompt_tokens = pin
        self.completion_tokens = pout


def _canned_judge(run_grades):
    """Return a judge(title,text,stops) that yields the given per-run grade dicts
    in order, each with evidence + summary."""
    seq = iter(run_grades)

    def judge(title, text, stops):
        g = next(seq)
        detail = {c: float(g[c]) for c in tes.CRITERIA}
        detail['evidence'] = {c: f"evidence for {c}" for c in tes.CRITERIA}
        detail['summary'] = "a one-line summary"
        return detail, _Usage()

    return judge


# ─── 1. Stable scores: averaging, mapping, detail shape ───────────────────────

def test_three_runs_are_averaged_per_criterion(monkeypatch):
    # story varies 6/7/8 → mean 7.0; others constant.
    runs = [
        {'story': 6, 'specificity': 7, 'place': 7, 'flow': 6, 'accuracy': 8},
        {'story': 7, 'specificity': 7, 'place': 7, 'flow': 6, 'accuracy': 8},
        {'story': 8, 'specificity': 7, 'place': 7, 'flow': 6, 'accuracy': 8},
    ]
    monkeypatch.setattr(tes, 'judge', _canned_judge(runs))
    score, detail = tes.score_text("T", "x" * 300, 5, runs=3)
    assert detail['story'] == 7.0           # (6+7+8)/3
    assert detail['specificity'] == 7.0
    assert detail['run_count'] == 3
    assert len(detail['runs']) == 3
    assert [r['story'] for r in detail['runs']] == [6.0, 7.0, 8.0]


def test_averaging_reduces_single_run_wobble(monkeypatch):
    # Two single runs 0.5 apart on every criterion would map to different
    # numbers; their average is the stable published score.
    low = {c: 6.0 for c in tes.CRITERIA}
    high = {c: 7.0 for c in tes.CRITERIA}
    monkeypatch.setattr(tes, 'judge', _canned_judge([low, high, low]))
    # runs = [6,7,6] mean 6.333 → rounds to 6.5 on the 0.5 grid per criterion.
    score, detail = tes.score_text("T", "x" * 300, 5, runs=3)
    for c in tes.CRITERIA:
        assert detail[c] == 6.5
    assert detail['rubric_avg'] == 6.5


def test_mapping_unchanged_from_local685():
    # The 5.0–8.0 mapping is the LOCAL-685 contract, untouched.
    assert tes.map_to_range(1) == 5.0
    assert tes.map_to_range(10) == 8.0
    assert 5.0 < tes.map_to_range(6.5) < 8.0


def test_detail_json_shape(monkeypatch):
    runs = [{c: 7 for c in tes.CRITERIA} for _ in range(3)]
    monkeypatch.setattr(tes, 'judge', _canned_judge(runs))
    score, detail = tes.score_text("Title", "x" * 300, 4, runs=3)
    # Published per-criterion grades.
    for c in tes.CRITERIA:
        assert c in detail and isinstance(detail[c], float)
    # Evidence per criterion + a summary.
    assert set(detail['evidence'].keys()) == set(tes.CRITERIA)
    assert detail['summary']
    # Provenance.
    assert detail['rubric_version'] == tes.RUBRIC_VERSION == 2
    assert detail['model'] == tes.MODEL
    assert detail['rubric_avg'] == 7.0
    # Tokens summed across the three runs.
    assert detail['tokens_in'] == 300
    assert detail['tokens_out'] == 60
    # The score itself is 5.0–8.0.
    assert 5.0 <= score <= 8.0


def test_run_count_respects_override(monkeypatch):
    runs = [{c: 7 for c in tes.CRITERIA} for _ in range(1)]
    monkeypatch.setattr(tes, 'judge', _canned_judge(runs))
    score, detail = tes.score_text("T", "x" * 300, 1, runs=1)
    assert detail['run_count'] == 1


# ─── map-delivery module loader (no DB at import for pure tests) ──────────────

def _load_md():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "map_delivery", "app.py")
    spec = importlib.util.spec_from_file_location("md_app_local688", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


# ─── 2. /how-we-score (pure, no DB) ───────────────────────────────────────────

def test_how_we_score_200_html_with_five_criteria():
    md = _load_md()
    md.app.testing = True
    client = md.app.test_client()
    r = client.get("/how-we-score")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/html")
    body = r.data.decode("utf-8").lower()
    # All five criteria named.
    assert "story" in body
    assert "specificity" in body
    assert "sense of place" in body or "place" in body
    assert "flow" in body
    assert "accuracy" in body
    # The 5–8 range rationale, the free promise, the re-score offer, and the
    # listener-takeover rule are all present.
    assert "5.0 and 8.0" in body or "5 to 8" in body
    assert "reserved for listeners" in body
    assert "free" in body
    assert "re-score" in body
    assert "fourth rating" in body


def test_how_we_score_grade_anchors_present():
    md = _load_md()
    md.app.testing = True
    body = md.app.test_client().get("/how-we-score").data.decode("utf-8")
    for anchor in ("3", "5", "6.5", "8", "9.5"):
        assert anchor in body


# ─── DB fixtures ──────────────────────────────────────────────────────────────

def _db_connect():
    """Connect to the TEST database (never production). Mirrors the host/port
    convention conftest.py uses to clean audiotours_test."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours_test",
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )


@pytest.fixture(scope="module")
def db():
    try:
        conn = _db_connect()
    except Exception:
        pytest.skip("database unavailable")
    # Skip the whole DB group if the LOCAL-688 columns are not present.
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='audio_tours' "
                    "AND column_name IN ('editor_score','rescore_requested_version')")
        if len(cur.fetchall()) < 2:
            cur.close()
            conn.close()
            pytest.skip("audio_tours missing LOCAL-685/688 columns (run migrations 025+026)")
        cur.close()
    except Exception:
        conn.close()
        pytest.skip("database unavailable")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def md_client(db):
    md = _load_md()
    md.get_db_connection = _db_connect
    md.app.testing = True
    return md.app.test_client()


def _cleanup(conn):
    cur = conn.cursor()
    # tour_requests first (ownership rows), then translations, then originals.
    try:
        cur.execute("SELECT DISTINCT secret_id FROM tour_requests WHERE secret_id LIKE %s",
                    (TEST_PREFIX + "%",))
        for (sid,) in cur.fetchall():
            if sid and str(sid).startswith(TEST_PREFIX):
                cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (sid,))
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


def _seed_scored_tour(conn, name, score, detail, original_tour_id=None, language="en"):
    import json
    from datetime import datetime, timezone
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id,
                                 editor_score, editor_score_detail, editor_scored_at,
                                 is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id,
         score, json.dumps(detail) if detail is not None else None,
         datetime.now(timezone.utc)),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


def _seed_unscored_tour(conn, name, original_tour_id=None, language="en"):
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


def _seed_creator(conn, tour_id, user_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
                (user_id,))
    cur.execute(
        """
        INSERT INTO tour_requests (secret_id, tour_id, request_string, status, created_at)
        VALUES (%s, %s, %s, 'completed', CURRENT_TIMESTAMP - INTERVAL '1 day')
        """,
        (user_id, str(tour_id), "creator"),
    )
    conn.commit()
    cur.close()


def _sample_detail():
    return {
        'story': 7.0, 'specificity': 6.5, 'place': 7.5, 'flow': 6.0, 'accuracy': 8.0,
        'evidence': {'story': 'A named figure drives the opening.',
                     'specificity': 'Dates and a street name appear.',
                     'place': 'Points at what you see at the fountain.',
                     'flow': 'Stops hand off cleanly.',
                     'accuracy': 'No internal contradictions.'},
        'summary': 'A competent, place-rooted walk with a strong lead.',
        'rubric_avg': 7.0, 'rubric_version': 2, 'model': 'gpt-4.1',
        'runs': [{'story': 7, 'specificity': 6.5, 'place': 7.5, 'flow': 6, 'accuracy': 8}],
    }


# ─── 3. score-explanation (DB) ────────────────────────────────────────────────

def test_score_explanation_original(db, md_client):
    _cleanup(db)
    try:
        tid = _seed_scored_tour(db, f"{TEST_PREFIX}exp orig", 6.9, _sample_detail())
        r = md_client.get(f"/tour/{tid}/score-explanation")
        assert r.status_code == 200
        j = r.get_json()
        assert j["score"] == 6.9
        assert j["label"] == "Audioura score"
        assert j["rubric_version"] == 2
        assert j["summary"]
        assert j["scored_at"]
        names = [c["name"] for c in j["criteria"]]
        assert names == ["story", "specificity", "place", "flow", "accuracy"]
        story = next(c for c in j["criteria"] if c["name"] == "story")
        assert story["grade"] == 7.0
        assert story["evidence"] == "A named figure drives the opening."
        assert story["label"] == "Story"
    finally:
        _cleanup(db)


def test_score_explanation_translation_returns_originals(db, md_client):
    _cleanup(db)
    try:
        orig = _seed_scored_tour(db, f"{TEST_PREFIX}exp en", 7.2, _sample_detail())
        ru = _seed_unscored_tour(db, f"{TEST_PREFIX}exp ru",
                                 original_tour_id=orig, language="ru")
        r = md_client.get(f"/tour/{ru}/score-explanation")
        assert r.status_code == 200
        j = r.get_json()
        # Same score + criteria as the original (the translation has none of its own).
        assert j["score"] == 7.2
        assert j["scored_tour_id"] == orig
        assert j["tour_id"] == ru
        story = next(c for c in j["criteria"] if c["name"] == "story")
        assert story["grade"] == 7.0
    finally:
        _cleanup(db)


def test_score_explanation_unscored_404(db, md_client):
    _cleanup(db)
    try:
        tid = _seed_unscored_tour(db, f"{TEST_PREFIX}exp none")
        r = md_client.get(f"/tour/{tid}/score-explanation")
        assert r.status_code == 404
    finally:
        _cleanup(db)


# ─── 4. rescore-request (DB) ──────────────────────────────────────────────────

def test_rescore_owner_once_then_409(db, md_client):
    _cleanup(db)
    try:
        tid = _seed_scored_tour(db, f"{TEST_PREFIX}rs own", 6.6, _sample_detail())
        owner = f"{TEST_PREFIX}rs-owner"
        _seed_creator(db, tid, owner)

        # First request: queued, score cleared, version stamped.
        r1 = md_client.post(f"/tour/{tid}/rescore-request", json={"user_id": owner})
        assert r1.status_code == 200
        j1 = r1.get_json()
        assert j1["status"] == "queued"
        version = j1["version"]

        cur = db.cursor()
        cur.execute("SELECT editor_score, rescore_requested_version FROM audio_tours WHERE id = %s",
                    (tid,))
        es, rrv = cur.fetchone()
        cur.close()
        assert es is None                      # score cleared → the tick re-scores
        assert int(rrv) == int(version)        # version stamped

        # Second request for the SAME version → 409.
        r2 = md_client.post(f"/tour/{tid}/rescore-request", json={"user_id": owner})
        assert r2.status_code == 409
        assert "message" in r2.get_json()
    finally:
        _cleanup(db)


def test_rescore_non_owner_403(db, md_client):
    _cleanup(db)
    try:
        tid = _seed_scored_tour(db, f"{TEST_PREFIX}rs no", 6.6, _sample_detail())
        owner = f"{TEST_PREFIX}rs-no-owner"
        other = f"{TEST_PREFIX}rs-no-other"
        _seed_creator(db, tid, owner)
        r = md_client.post(f"/tour/{tid}/rescore-request", json={"user_id": other})
        assert r.status_code == 403
        # The score was NOT cleared.
        cur = db.cursor()
        cur.execute("SELECT editor_score FROM audio_tours WHERE id = %s", (tid,))
        assert cur.fetchone()[0] is not None
        cur.close()
    finally:
        _cleanup(db)


def test_rescore_missing_user_403(db, md_client):
    _cleanup(db)
    try:
        tid = _seed_scored_tour(db, f"{TEST_PREFIX}rs anon", 6.6, _sample_detail())
        r = md_client.post(f"/tour/{tid}/rescore-request", json={})
        assert r.status_code == 403
    finally:
        _cleanup(db)


def test_rescore_translation_resolves_to_original(db, md_client):
    """A request against a TRANSLATION clears the ORIGINAL's score (the score
    lives on the original) and is owned by the original's creator."""
    _cleanup(db)
    try:
        orig = _seed_scored_tour(db, f"{TEST_PREFIX}rs tr en", 6.6, _sample_detail())
        ru = _seed_unscored_tour(db, f"{TEST_PREFIX}rs tr ru",
                                 original_tour_id=orig, language="ru")
        owner = f"{TEST_PREFIX}rs-tr-owner"
        _seed_creator(db, orig, owner)
        r = md_client.post(f"/tour/{ru}/rescore-request", json={"user_id": owner})
        assert r.status_code == 200
        assert r.get_json()["tour_id"] == orig
        cur = db.cursor()
        cur.execute("SELECT editor_score FROM audio_tours WHERE id = %s", (orig,))
        assert cur.fetchone()[0] is None
        cur.close()
    finally:
        _cleanup(db)
