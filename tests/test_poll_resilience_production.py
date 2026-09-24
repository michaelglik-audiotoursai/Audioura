#!/usr/bin/env python3
"""
LOCAL-360 regression tests that drive the PRODUCTION polling loop.

`tests/test_poll_resilience.py` re-implements the loop in a local harness, so
every case in it passes with `tour_orchestrator_service.py` fully reverted.
These tests patch `_authenticated_request` on the real module and call
`orchestrate_tour_async`, so they go red when the fix is removed.

Note on failure semantics: `orchestrate_tour_async` swallows every exception
and records it on `ACTIVE_JOBS[job_id]["error"]`, so these tests assert on that
recorded string rather than on a propagated exception.

Safety: the module's failure path issues `DELETE FROM tour_requests`. DB_HOST is
pinned to an unresolvable name below so these tests can never reach a live DB.
"""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@invalid.test.localdomain/none")

import tour_orchestrator_service as tos  # noqa: E402


@pytest.fixture(autouse=True)
def _unreachable_db(monkeypatch):
    """
    Point the failure-path DELETE at a host that cannot resolve.

    Scoped via monkeypatch rather than set at module import: DB_HOST is read
    with os.getenv() at call time, and a module-level assignment leaked into
    every other suite in the same pytest session.
    """
    monkeypatch.setenv("DB_HOST", "invalid.test.localdomain")

# Raised by the fake transport on the first call AFTER the text-gen poll loop.
# Seeing this in the recorded error proves the loop was survived.
PAST_THE_LOOP = "PAST-THE-LOOP-MARKER"


def _resp(status_code, payload):
    class _R:
        pass

    r = _R()
    r.status_code = status_code
    r.text = str(payload)
    r.json = lambda: payload
    return r


def _make_transport(script, calls):
    """Fake `_authenticated_request` driven by a scripted /status sequence."""
    def fake_request(method, url, **kwargs):
        if url.endswith("/generate"):
            return _resp(200, {"job_id": "text-job-1"})
        if "/status/" in url:
            calls["n"] += 1
            if not script:
                raise AssertionError("poll script exhausted inside the loop")
            item = script.pop(0)
            if isinstance(item, Exception):
                raise item
            return _resp(200, item)
        raise Exception(PAST_THE_LOOP)

    return fake_request


def _drive(monkeypatch, script):
    """Run orchestrate_tour_async against `script`; return (poll_count, error_str)."""
    calls = {"n": 0}
    monkeypatch.setattr(tos, "_authenticated_request", _make_transport(list(script), calls))
    monkeypatch.setattr(tos.time, "sleep", lambda *_a, **_k: None)

    job_id = "lead-test-job"
    tos.ACTIVE_JOBS[job_id] = {"status": "queued", "progress": ""}
    try:
        tos.orchestrate_tour_async(job_id, "Museum of Fine Arts, Boston", "museum", 8)
        return calls["n"], str(tos.ACTIVE_JOBS[job_id].get("error", ""))
    finally:
        tos.ACTIVE_JOBS.pop(job_id, None)


def test_single_timeout_survives(monkeypatch):
    """
    One ReadTimeout mid-poll must NOT fail the job — this is Michael's MFA bug.
    With the try/except reverted the loop aborts after 2 polls with a Timeout.
    """
    polls, err = _drive(monkeypatch, [
        {"status": "in_progress", "progress": "Crawling mfa.org"},
        requests.Timeout("Read timed out. (read timeout=30)"),
        {"status": "completed", "output_file": "/tmp/tour.txt"},
    ])
    assert polls == 3, f"loop must poll past the timeout, not abort on it (got {polls})"
    assert PAST_THE_LOOP in err, f"expected to exit past the loop, got: {err}"


def test_counter_resets_after_success(monkeypatch):
    """
    5 timeouts, a success, then 5 more must NOT trip the budget of 6.
    Proves the reset is real and not a cumulative counter.
    """
    script = (
        [requests.Timeout("t") for _ in range(5)]
        + [{"status": "in_progress", "progress": "still crawling"}]
        + [requests.Timeout("t") for _ in range(5)]
        + [{"status": "completed", "output_file": "/tmp/tour.txt"}]
    )
    polls, err = _drive(monkeypatch, script)
    assert polls == 12, f"expected 12 polls before leaving the loop, got {polls}"
    assert PAST_THE_LOOP in err, f"expected to exit past the loop, got: {err}"



def _poll_failure_budget():
    """The orchestrator's consecutive-poll-failure budget, read from the source.

    The constant is a local inside orchestrate_tour_async, so it cannot be imported;
    parse it out rather than duplicating the number in this file.
    """
    import re, pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "tour_orchestrator_service.py"
    m = re.search(r"_MAX_CONSECUTIVE_POLL_FAILURES\s*=\s*(\d+)", src.read_text())
    assert m, "could not find _MAX_CONSECUTIVE_POLL_FAILURES in the orchestrator"
    return int(m.group(1))


def test_budget_exhaustion_still_fails(monkeypatch):
    """Enough straight timeouts is a genuinely dead generator — the job must fail.

    [LOCAL-547, 2026-09-23] Budget raised 6 -> 30. The invariant this test protects is
    unchanged and still asserted: a generator that never answers must eventually fail
    the job rather than hang. Only the threshold moved, and it moved because 6 was
    killing LIVE generations -- Museum of Fine Arts, Boston starved the trivial status
    endpoint for 200s+ while successfully writing the tour, and the orchestrator
    reported failure for a job that was working. Busy is not dead.

    Read from the module rather than hard-coded, so tuning the budget in production
    does not require editing an assertion here -- pinning the number is what made this
    test fail for a deliberate change instead of for a regression.
    """
    budget = _poll_failure_budget()
    polls, err = _drive(monkeypatch,
                        [requests.Timeout("Read timed out") for _ in range(budget)])
    assert polls == budget, f"expected exactly {budget} polls before giving up, got {polls}"
    assert f"{budget} consecutive poll failures" in err, err
    assert PAST_THE_LOOP not in err, "must not proceed past a dead generator"


def test_generator_reported_error_still_aborts(monkeypatch):
    """A real status=error is not a transient failure — it must abort at once."""
    polls, err = _drive(monkeypatch, [{"status": "error", "error": "OOM killed"}])
    assert polls == 1
    assert "OOM killed" in err, err
    assert PAST_THE_LOOP not in err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
