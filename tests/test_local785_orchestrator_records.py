#!/usr/bin/env python3
"""[LOCAL-785] The orchestrator records a row when a request fails.

Uses the test-only forced-failure hook (FAILURE_LOG_TEST_HOOK=1 +
X-Force-Failure: 1) so a request raises inside the orchestrator WITHOUT any real
failure or spend; the @errorhandler(Exception) must then call failure_log.record
(monkeypatched to capture) with service='orchestrator', http_status=500 and an
exception_type — i.e. the failure is written, not swallowed — and still return
the SAME 500 as before.

Run: python3 -m pytest tests/test_local785_orchestrator_records.py -q
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

# Turn the test hook ON before importing the service (read at request time, but
# set early for clarity) and keep the DB unreachable (never connected to: record
# is monkeypatched).
os.environ["FAILURE_LOG_TEST_HOOK"] = "1"
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/db")

import tour_orchestrator_service as orch


def test_forced_failure_records_a_row(monkeypatch):
    captured = []

    def fake_record(**kw):
        captured.append(kw)
        return "sig785orch00000"[:16]

    monkeypatch.setattr(orch._failure_log, "record", fake_record)

    orch.app.config["TESTING"] = False  # let the errorhandler run + re-raise
    client = orch.app.test_client()

    # Any route + the forced-failure header. /health is simplest; the
    # before_request hook raises before the handler runs.
    raised = False
    try:
        resp = client.get("/health", headers={"X-Force-Failure": "1"})
        # Flask returns 500 for the re-raised exception when not in TESTING mode.
        assert resp.status_code == 500
    except RuntimeError:
        # With propagation on, the forced RuntimeError surfaces here — that is
        # still proof the hook fired; the record must have happened first.
        raised = True

    assert captured, "the orchestrator must record the forced failure"
    row = captured[-1]
    assert row.get("service") == "orchestrator"
    assert row.get("http_status") == 500
    assert row.get("exception_type")  # a concrete exception type was recorded
    _ = raised  # either path is acceptable; the record is the assertion


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
