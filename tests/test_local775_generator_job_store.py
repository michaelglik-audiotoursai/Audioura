#!/usr/bin/env python3
"""[LOCAL-775 / D718] Generator job status must survive crossing instances.

GCloud_Storied, 2026-10-26 ~19:48Z (D718): tour-generator-subscribed briefly ran
2 instances during a revision rollout. The orchestrator's /status poll landed on
the instance that did NOT own the job and got {"error":"Job not found"} 404
(generate_tour_text_service.py get_job_status). The owning instance kept
generating (~$0.35 metered) and no tour was stored.

Ruling: job status goes to the database (generator_jobs table); the in-memory
dict stays only as a cache. A job the table knows is never "Job not found", and
the final result is retrievable from ANY instance.

These are the RED-FIRST tests. They model two generator instances as two
LayeredJobStore objects (two independent in-memory caches) sharing ONE database,
exactly the shape of the 2-instance overlap. On the base tree there is no
LayeredJobStore and no generator_jobs table, so these fail; on the branch they
pass.

They need a PostgreSQL to point at. Set the DB_* env vars (DB_HOST, DB_PORT,
DB_NAME, DB_USER, DB_PASSWORD) to a throwaway database; if none is reachable the
DB-backed tests SKIP (they never touch a production table and write only to the
additive generator_jobs table in whatever DB you point them at).

Run:
  python3 -m pytest tests/test_local775_generator_job_store.py -q
  (or: python3 tests/test_local775_generator_job_store.py)
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import job_store


def _db_reachable():
    """True when the configured DB accepts a connection (else tests SKIP)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
            dbname=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


_DB_OK = _db_reachable()
_SKIP_REASON = (
    "no PostgreSQL reachable via DB_* env — set DB_HOST/DB_PORT/DB_NAME/DB_USER/"
    "DB_PASSWORD to a throwaway database to run the cross-instance tests"
)

try:
    import pytest
    _skip_db = pytest.mark.skipif(not _DB_OK, reason=_SKIP_REASON)
except Exception:  # pytest not present (direct __main__ run)
    def _skip_db(fn):
        return fn


def _two_instances():
    """Two LayeredJobStore objects = two generator instances, one shared DB."""
    inst_a = job_store.LayeredJobStore(service_name='tour-generator-test')
    inst_b = job_store.LayeredJobStore(service_name='tour-generator-test')
    return inst_a, inst_b


# --------------------------------------------------------------------------
# Store-level cross-instance behaviour (the heart of D718)
# --------------------------------------------------------------------------

@_skip_db
def test_job_started_on_A_is_visible_on_B_not_job_not_found():
    """A job created on instance A must be readable on instance B (shared DB).

    This is the 404 that lost Michael's tour: B had never seen the job in its own
    memory, so the old code answered "Job not found". With the table as source of
    truth, B.get(job_id) returns the real queued/processing status.
    """
    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"

    # A starts the job (mirrors ACTIVE_JOBS[job_id] = {...} + update to processing).
    inst_a[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "location": "DeCordova Sculpture Park, Lincoln, MA",
        "tour_type": "",
        "total_stops": 1,
    }
    inst_a.update(job_id, status="processing", progress="Starting tour text generation...")

    # B has this job in neither its own memory cache...
    assert job_id not in inst_b._memory
    # ...yet it is NOT "Job not found": B reads it from the shared table.
    assert job_id in inst_b, "instance B must know the job via generator_jobs (no 404)"
    seen = inst_b.get(job_id)
    assert seen is not None
    assert seen["status"] == "processing"
    assert seen["progress"] == "Starting tour text generation..."
    assert seen["location"] == "DeCordova Sculpture Park, Lincoln, MA"
    assert seen["total_stops"] == 1


@_skip_db
def test_A_finishes_and_B_returns_the_result():
    """Once A completes the job (storing tour_content), B returns the tour.

    The orchestrator delivers from status_data['tour_content']; storing it in the
    generator_jobs.result JSONB is what makes the finished tour retrievable from
    the instance that did not generate it (D718 point 3).
    """
    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"
    tour_text = "Stop 1: The Lincoln Armory\n\nA real one-stop tour body." * 3

    inst_a[job_id] = {
        "status": "queued", "progress": "", "location": "Lincoln, MA",
        "tour_type": "", "total_stops": 1,
    }
    inst_a.update(
        job_id,
        status="completed",
        progress="Tour text generation completed successfully!",
        output_file="lincoln_tour.txt",
        coordinates=[42.42, -71.30],
        tour_content=tour_text,
        tour_kind="full",
    )

    got = inst_b.get(job_id)
    assert got is not None
    assert got["status"] == "completed"
    assert got["tour_content"] == tour_text, "the finished tour must be readable on B"
    assert got["output_file"] == "lincoln_tour.txt"
    assert got["coordinates"] == [42.42, -71.30]
    assert got["tour_kind"] == "full"


@_skip_db
def test_structured_refusal_survives_across_instances():
    """An error job's structured refusal (LOCAL-580/597/774) must survive to B.

    error_code / message / suggestion / nearby_tours are stored in the error
    JSONB so the app still gets a tappable refusal even when the poll hits the
    non-owning instance.
    """
    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"
    inst_a[job_id] = {
        "status": "queued", "progress": "", "location": "Gyms near me, West Roxbury, MA",
        "tour_type": "", "total_stops": 2,
    }
    inst_a.update(
        job_id,
        status="error",
        error="Error in tour text generation: not researched yet on the free level.",
        error_code="by_reference_no_material",
        message="This place hasn't been researched yet on the free level.",
        suggestion="Buy a $10 pack, or pick a nearby tour.",
        nearby_tours=[{"id": 123, "name": "West Roxbury Walk"}],
    )

    got = inst_b.get(job_id)
    assert got is not None
    assert got["status"] == "error"
    assert got["error_code"] == "by_reference_no_material"
    assert got["message"] == "This place hasn't been researched yet on the free level."
    assert got["suggestion"] == "Buy a $10 pack, or pick a nearby tour."
    assert got["nearby_tours"] == [{"id": 123, "name": "West Roxbury Walk"}]


@_skip_db
def test_partial_updates_merge_not_clobber():
    """A later progress-only update must not wipe earlier result/error keys.

    The generator upserts at every status change; the result/error JSONB merge
    (jsonb ||) keeps earlier keys so a progress tick doesn't erase, say, a stored
    coordinate or a structured field written a moment earlier.
    """
    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"
    inst_a[job_id] = {"status": "queued", "progress": "", "location": "X",
                      "tour_type": "", "total_stops": 1}
    inst_a.update(job_id, status="processing", i_con_avg=0.81)   # a result-blob key
    inst_a.update(job_id, progress="halfway")                    # progress-only tick
    got = inst_b.get(job_id)
    assert got["i_con_avg"] == 0.81, "earlier result key must not be clobbered"
    assert got["progress"] == "halfway"


@_skip_db
def test_cached_in_progress_does_not_mask_completion_on_another_instance():
    """A non-terminal cache entry must not hide a completion written elsewhere.

    Found by the live kill-owner proof: instance B polled a job while it was
    'processing' (caching it), then instance A completed the job and stored the
    tour, then A was killed. B must return 'completed' with the tour_content from
    the table — not keep serving its stale cached 'processing'. Otherwise the
    tour is lost exactly as in D718, just one step later.
    """
    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"
    tour_text = "Stop 1: The DeCordova Terrace\n\nA real one-stop tour body."

    inst_a[job_id] = {"status": "queued", "progress": "", "location": "Lincoln, MA",
                      "tour_type": "", "total_stops": 1}
    inst_a.update(job_id, status="processing", progress="Working...")

    # B polls while in progress -> caches 'processing' in its own memory.
    first = inst_b.get(job_id)
    assert first["status"] == "processing"
    assert job_id in inst_b._memory  # proven cached

    # A finishes and stores the tour, then (conceptually) goes away.
    inst_a.update(job_id, status="completed",
                  progress="Tour text generation completed successfully!",
                  output_file="decordova.txt", tour_content=tour_text, tour_kind="full")

    # B must now see the completion from the table, not its stale cached status.
    after = inst_b.get(job_id)
    assert after["status"] == "completed", "cache must not mask a completion on another instance"
    assert after["tour_content"] == tour_text, "the finished tour must be retrievable on B"


# --------------------------------------------------------------------------
# Flask-level: the /status endpoint on instance B answers, not 404
# --------------------------------------------------------------------------

@_skip_db
def test_generator_status_endpoint_answers_from_other_instance():
    """The generator's GET /status/<job_id> must answer on an instance that only
    knows the job through the shared table — the exact request that 404'd."""
    import generate_tour_text_service as gen

    inst_a, inst_b = _two_instances()
    job_id = f"local775-{uuid.uuid4()}"
    inst_a[job_id] = {
        "status": "processing", "progress": "Working...",
        "location": "Lincoln, MA", "tour_type": "", "total_stops": 1,
    }

    gen.app.config["TESTING"] = True
    client = gen.app.test_client()
    orig = gen.ACTIVE_JOBS
    gen.ACTIVE_JOBS = inst_b  # serve from the NON-owning instance
    try:
        resp = client.get(f"/status/{job_id}")
        assert resp.status_code == 200, "non-owning instance must not 404 (D718)"
        body = resp.get_json()
        assert body["status"] == "processing"
        assert body["location"] == "Lincoln, MA"
    finally:
        gen.ACTIVE_JOBS = orig


# --------------------------------------------------------------------------
# Orchestrator: a generator 404 is tolerated for up to 60 s (D718 point 4).
# These drive the REAL poll loop in orchestrate_tour_async (no DB needed); they
# swap _authenticated_request for a scripted transport and restore it after.
# --------------------------------------------------------------------------

def _orch_resp(status_code, payload):
    class _R:
        pass
    r = _R()
    r.status_code = status_code
    r.text = str(payload)
    r.json = lambda: payload
    return r


_ORCH_PAST_LOOP = "PAST-THE-LOOP-MARKER-775"


def _drive_orch(script, fake_now=None):
    """Run orchestrate_tour_async against a scripted /status sequence.

    script items: dicts -> 200 JSON bodies; ints -> an HTTP status code with no
    useful body (used for 404). Returns (poll_count, recorded_error_string).
    """
    import tour_orchestrator_service as tos

    calls = {"n": 0}
    script = list(script)

    def fake_request(method, url, **kwargs):
        if url.endswith("/generate"):
            return _orch_resp(200, {"job_id": "text-job-775"})
        if "/status/" in url:
            calls["n"] += 1
            if not script:
                raise AssertionError("poll script exhausted inside the loop")
            item = script.pop(0)
            if isinstance(item, int):
                return _orch_resp(item, {"error": "Job not found"})
            return _orch_resp(200, item)
        raise Exception(_ORCH_PAST_LOOP)

    orig_req = tos._authenticated_request
    orig_sleep = tos.time.sleep
    orig_dt = tos.datetime
    tos._authenticated_request = fake_request
    tos.time.sleep = lambda *_a, **_k: None
    os.environ.setdefault("DB_HOST", "invalid.test.localdomain")
    if fake_now is not None:
        tos.datetime = fake_now
    job_id = "local775-orch"
    tos.ACTIVE_JOBS[job_id] = {"status": "queued", "progress": ""}
    try:
        tos.orchestrate_tour_async(job_id, "DeCordova Sculpture Park, Lincoln, MA", "museum", 1)
        return calls["n"], str(tos.ACTIVE_JOBS[job_id].get("error", ""))
    finally:
        tos._authenticated_request = orig_req
        tos.time.sleep = orig_sleep
        tos.datetime = orig_dt
        tos.ACTIVE_JOBS.pop(job_id, None)


def test_orchestrator_tolerates_transient_404_then_succeeds():
    """A single 404 (rollover gap) followed by a good status must NOT fail the job.

    This is the D718 fix: the old code raised immediately on any non-200, so a
    404 from a second instance threw away the tour the owner was still making.
    """
    polls, err = _drive_orch([
        {"status": "in_progress", "progress": "Researching"},
        404,                                   # poll lands on the non-owning instance
        {"status": "in_progress", "progress": "Still researching"},
        {"status": "completed", "output_file": "/tmp/t.txt", "tour_content": "Stop 1: x"},
    ])
    assert polls == 4, f"loop must poll past the 404, not abort on it (got {polls})"
    assert _ORCH_PAST_LOOP in err, f"expected to exit past the loop, got: {err}"


def test_orchestrator_fails_after_404_grace_exhausted():
    """A 404 that persists beyond the 60 s grace must eventually fail the job.

    The clock is advanced ~65 s per poll so the grace (60 s) is exceeded without
    tripping the 5-minute stall limit or the 40-minute absolute cap.
    """
    import datetime as _dt_mod

    base = _dt_mod.datetime(2026, 10, 28, 12, 0, 0)
    state = {"t": 0}

    class _FakeDateTime:
        @staticmethod
        def now():
            # Advance 40 s per read. Setup reads (_poll_started_at,
            # _last_progress_at) take the early values; by the 2nd/3rd poll the
            # 404 clock exceeds its 60 s grace, while the 5-minute stall limit and
            # 40-minute cap are not reached within these few polls.
            t = state["t"]
            state["t"] += 40
            return base + _dt_mod.timedelta(seconds=t)

    polls, err = _drive_orch([404, 404, 404, 404, 404, 404], fake_now=_FakeDateTime)
    assert "404" in err and "Job not found" in err, f"expected a 404 give-up error, got: {err}"
    assert _ORCH_PAST_LOOP not in err, "must not proceed past an unknown job"


if __name__ == "__main__":
    if not _DB_OK:
        print(f"SKIP DB TESTS: {_SKIP_REASON}")
    failures = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        # DB-dependent tests only run when a DB is reachable.
        needs_db = name != "test_orchestrator_tolerates_transient_404_then_succeeds" \
            and name != "test_orchestrator_fails_after_404_grace_exhausted"
        if needs_db and not _DB_OK:
            print(f"SKIP {name} (no DB)")
            continue
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
