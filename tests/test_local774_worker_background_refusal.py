#!/usr/bin/env python3
"""[LOCAL-774] The "Generate in Background" path (tour_worker_service, the
Cloud Tasks worker) must carry the by_reference refusal's structured fields into
the job_status row so the orchestrator's /status can forward them to the app.

Before this fix the worker's text-gen poll loop raised
    Exception(f"Text generation error: {sdata.get('error')}")
— dropping error_code / message / suggestion / nearby_tours entirely — and
run_job's final update_job_status wrote only `error`. So a Free refusal delivered
via the background path reached the app as a bare prefixed string, exactly the
generic "Tour Generation Failed" dialog Michael saw.

This test drives the real /run-job route (the Cloud Tasks entry point) with the
network and DB mocked and the final-retry header set, so run_job writes the
terminal error status. The tour generator returns a by_reference refusal; we
assert the final update_job_status('error', ...) carries all four structured
fields as extra columns (update_job_status merges them into
job_status.output_data, which _read_job_from_db then exposes to /status).

Run: python3 -m pytest tests/test_local774_worker_background_refusal.py -q
  (or: python3 tests/test_local774_worker_background_refusal.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_worker_service as worker


_REFUSAL = {
    "error_code": "by_reference_no_material",
    "message": "This place hasn't been researched yet on the free level.",
    "suggestion": "Buy a $10 pack for a freshly researched tour.",
    "nearby_tours": [],
}


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _client():
    worker.app.config["TESTING"] = True
    return worker.app.test_client()


def test_worker_run_job_carries_structured_refusal_into_job_status():
    captured = []

    def fake_update(job_id, status, progress='', error=None, **extra):
        captured.append({"status": status, "progress": progress,
                         "error": error, "extra": extra})

    def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/generate"):
            return _FakeResp(200, {"job_id": "gen-local774"})
        if method == "GET" and "/status/" in url:
            # The tour-generator /status already forwards the four fields.
            return _FakeResp(200, {"status": "error",
                                   "error": ("Error in tour text generation: "
                                             + _REFUSAL["message"]),
                                   **_REFUSAL})
        raise AssertionError(f"unexpected request {method} {url}")

    def fake_rollback_conn():
        raise RuntimeError("no DB in unit test")  # usage rollback is non-fatal

    orig = (worker._read_job_status, worker.update_job_status,
            worker._authenticated_request, worker._get_db_conn)
    worker._read_job_status = lambda job_id: None
    worker.update_job_status = fake_update
    worker._authenticated_request = fake_request
    worker._get_db_conn = fake_rollback_conn
    try:
        resp = _client().post(
            "/run-job",
            json={"job_id": "job-local774",
                  "location": "Gyms near me, West Roxbury, MA",
                  "tour_type": "walking", "total_stops": 2,
                  "user_id": "free-dev"},
            # Final attempt -> run_job writes the terminal 'error' status.
            headers={"X-CloudTasks-TaskRetryCount":
                     str(worker.MAX_TASK_ATTEMPTS - 1)})
        assert resp.status_code in (200, 500)
    finally:
        (worker._read_job_status, worker.update_job_status,
         worker._authenticated_request, worker._get_db_conn) = orig

    error_writes = [c for c in captured if c["status"] == "error"]
    assert error_writes, f"no terminal error status written; calls={captured}"
    extra = error_writes[-1]["extra"]
    assert extra.get("error_code") == "by_reference_no_material", extra
    assert extra.get("message") == _REFUSAL["message"], extra
    assert extra.get("suggestion") == _REFUSAL["suggestion"], extra
    assert "nearby_tours" in extra, extra
    assert "Error in tour text generation:" not in (extra.get("message") or "")


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
