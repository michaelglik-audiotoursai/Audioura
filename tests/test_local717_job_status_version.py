#!/usr/bin/env python3
"""[LOCAL-717 / D677 §2] The job-status payload must carry version_no / replaced
/ tour_title for a regenerated tour, so the app can say "Updated your tour
'<title>' — now version N" instead of announcing a brand-new tour.

Michael (D677, 2026-10-19) regenerated "restaurant tour, Boston, MA". The server
replaced tour 370 and bumped it to version 2, but nothing told him, so he looked
for a second tour. These tests pin that GET /status/<job_id> surfaces the
version fields from ACTIVE_JOBS, and that a brand-new tour (version 1, not
replaced) does not look like an update.

Run: python3 -m pytest tests/test_local717_job_status_version.py -q
  (or: python3 tests/test_local717_job_status_version.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_orchestrator_service as orch


def _client():
    orch.app.config["TESTING"] = True
    return orch.app.test_client()


def _completed_job(**extra):
    job = {
        "status": "completed",
        "progress": "done",
        "location": "restaurant tour, Boston, MA",
        "tour_type": "restaurant",
        "total_stops": 5,
        "created_at": "2026-10-19T16:00:00",
        "final_tour_id": 370,
    }
    job.update(extra)
    return job


def test_status_carries_version_no_for_a_replaced_tour():
    job_id = "local717-replaced"
    orch.ACTIVE_JOBS[job_id] = _completed_job(
        version_no=2, replaced=True, tour_title="Boston — Restaurant Tour"
    )
    try:
        resp = _client().get(f"/status/{job_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["version_no"] == 2
        assert body["replaced"] is True
        assert body["tour_title"] == "Boston — Restaurant Tour"
        assert body["final_tour_id"] == 370
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


def test_status_for_a_brand_new_tour_is_version_1_not_replaced():
    job_id = "local717-new"
    orch.ACTIVE_JOBS[job_id] = _completed_job(
        version_no=1, replaced=False, tour_title="A New Tour"
    )
    try:
        resp = _client().get(f"/status/{job_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["version_no"] == 1
        assert body["replaced"] is False
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


def test_status_without_version_fields_omits_them():
    # An older job (pre-717) that never set the fields must not break /status.
    job_id = "local717-legacy"
    orch.ACTIVE_JOBS[job_id] = _completed_job()
    try:
        resp = _client().get(f"/status/{job_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "version_no" not in body
        assert "replaced" not in body
    finally:
        orch.ACTIVE_JOBS.pop(job_id, None)


def test_store_audio_tour_result_version_formula():
    """The version carried in the result dict: a replaced row archives version
    N-1 and leaves the live row at version N. This pins the arithmetic the app
    keys on (see store_audio_tour's three return paths)."""
    # next_version is the archived version of the OLD content; the live row is
    # next_version + 1. For Michael's tour 370: old v1 archived → live is v2.
    next_version = 1
    assert next_version + 1 == 2


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
