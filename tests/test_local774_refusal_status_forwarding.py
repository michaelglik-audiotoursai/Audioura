#!/usr/bin/env python3
"""[LOCAL-774] A Free-level by_reference refusal must reach the app as a
STRUCTURED refusal through the orchestrator's GET /status/<job_id>.

Michael (TestFlight 2.4.32, Subscribed cloud, 2026-10-26 16:07): a fresh Free
install asked for "Gyms near me, West Roxbury, MA" and got a generic red
"Tour Generation Failed — Error in tour text generation: This place hasn't been
researched yet on the free level." dialog with only Dismiss / Try again. That is
the LOCAL-597 by_reference refusal (error_code=by_reference_no_material, plus a
suggestion "Buy a $10 pack…" and up to 3 nearby_tours) — but between the
generator, the orchestrator job status and the app, error_code / suggestion /
nearby_tours were lost and only a prefixed `error` string survived.

The generator (generate_tour_text.py) and the tour-generator /status endpoint
already carry all four fields (error_code, message, suggestion, nearby_tours);
the drop is in the ORCHESTRATOR:
  * its /status error branch (memory AND database) emitted only `error`;
  * its text-gen poll loop copied error_code/message/suggestion into ACTIVE_JOBS
    but NOT nearby_tours.

These tests pin that GET /status/<job_id> surfaces all four fields for an error
job, on BOTH the in-memory (thread mode) and the database (cloud_tasks/worker
"Generate in Background") paths.

Run: python3 -m pytest tests/test_local774_refusal_status_forwarding.py -q
  (or: python3 tests/test_local774_refusal_status_forwarding.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_orchestrator_service as orch


# The exact structured refusal the generator (l2_by_reference._refusal) produces
# and the tour-generator /status endpoint forwards — what the orchestrator
# receives and must pass through to the app.
_REFUSAL_FIELDS = {
    "error_code": "by_reference_no_material",
    "message": "This place hasn't been researched yet on the free level.",
    "suggestion": (
        "Buy a $10 pack for a freshly researched tour, or pick one of these "
        "nearby tours: West Roxbury Walk (#123); Roslindale Square (#124)."
    ),
    "nearby_tours": [
        {"id": 123, "name": "West Roxbury Walk"},
        {"id": 124, "name": "Roslindale Square"},
    ],
}


def _client():
    orch.app.config["TESTING"] = True
    return orch.app.test_client()


def _error_job(**extra):
    # Mirrors an ACTIVE_JOBS error row after orchestrate_tour_async's poll loop
    # copied the generator's structured fields in. `error` carries the legacy
    # prefixed string (what the orchestrator raises) — the app must NOT be forced
    # to show it when a structured message exists.
    job = {
        "status": "error",
        "progress": "Text generation: Starting tour text generation...",
        "location": "Gyms near me, West Roxbury, MA",
        "tour_type": "",
        "total_stops": 2,
        "created_at": "2026-10-26T16:07:00",
        "error": (
            "Error in tour text generation: "
            "This place hasn't been researched yet on the free level."
        ),
    }
    job.update(extra)
    return job


def test_status_memory_forwards_all_four_structured_refusal_fields():
    """Thread mode (Generate Now): the in-memory /status branch must emit
    error_code, message, suggestion AND nearby_tours."""
    job_id = "local774-mem"
    orch.ACTIVE_JOBS[job_id] = _error_job(**_REFUSAL_FIELDS)
    try:
        resp = _client().get(f"/status/{job_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "error"
        assert body["error_code"] == "by_reference_no_material"
        assert body["message"] == _REFUSAL_FIELDS["message"]
        assert body["suggestion"] == _REFUSAL_FIELDS["suggestion"]
        assert body["nearby_tours"] == _REFUSAL_FIELDS["nearby_tours"]
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


def test_status_memory_message_is_not_the_prefixed_string():
    """The structured `message` must stay the clean server copy — never the
    "Error in tour text generation:" wrapper that fooled Michael."""
    job_id = "local774-mem-msg"
    orch.ACTIVE_JOBS[job_id] = _error_job(**_REFUSAL_FIELDS)
    try:
        body = _client().get(f"/status/{job_id}").get_json()
        assert "Error in tour text generation:" not in body["message"]
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


def test_status_database_forwards_all_four_structured_refusal_fields(monkeypatch=None):
    """Database mode (Generate in Background / cloud_tasks): the worker writes the
    structured fields into job_status.output_data; _read_job_from_db merges them;
    the /status DB branch must emit all four."""
    job_id = "local774-db"
    # Force the DB branch: not in memory, and JOB_STORE_MODE/GENERATION_MODE gate.
    orch.ACTIVE_JOBS.pop(job_id, None)
    db_job = {
        "job_id": job_id,
        "status": "error",
        "progress": "Text generation: Starting tour text generation...",
        "location": "Gyms near me, West Roxbury, MA",
        "tour_type": "",
        "total_stops": 2,
        "created_at": "2026-10-26T16:07:00",
        "error": (
            "Error in tour text generation: "
            "This place hasn't been researched yet on the free level."
        ),
    }
    db_job.update(_REFUSAL_FIELDS)

    orig_mode = orch.GENERATION_MODE
    orig_read = orch._read_job_from_db
    orch.GENERATION_MODE = "cloud_tasks"
    orch._read_job_from_db = lambda jid: db_job if jid == job_id else None
    try:
        resp = _client().get(f"/status/{job_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "error"
        assert body["error_code"] == "by_reference_no_material"
        assert body["message"] == _REFUSAL_FIELDS["message"]
        assert body["suggestion"] == _REFUSAL_FIELDS["suggestion"]
        assert body["nearby_tours"] == _REFUSAL_FIELDS["nearby_tours"]
        assert "Error in tour text generation:" not in body["message"]
    finally:
        orch.GENERATION_MODE = orig_mode
        orch._read_job_from_db = orig_read


def test_non_refusal_error_still_only_emits_error():
    """A plain (non-structured) failure has no error_code/message/suggestion/
    nearby_tours — the status payload must not invent them."""
    job_id = "local774-plain"
    orch.ACTIVE_JOBS[job_id] = _error_job(error="Some internal failure.")
    try:
        body = _client().get(f"/status/{job_id}").get_json()
        assert body["error"] == "Some internal failure."
        assert "error_code" not in body
        assert "nearby_tours" not in body
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
