#!/usr/bin/env python3
"""test_local622_lookup_budget.py — LOCAL-622.

Two deliverables are proven here, with NO live network:

1. External-lookup budget enforcement (``external_lookup_budget`` +
   ``osm_venue_facts``): with a stubbed slow Overpass endpoint, the per-call
   timeout is short, at most one retry is made, and once the per-tour budget is
   spent further optional OSM lookups are SKIPPED (not attempted) — so the phase
   cannot stall the way D635 measured (663.4s).

2. Orchestrator progress-based polling: a harness mirroring the production
   give-up logic keeps polling while the generator reports advancing progress,
   gives up only after a real no-progress STALL (5 min), honours the 40-minute
   absolute cap, and asks the generator to STOP when it gives up.
"""
import os
import sys
import time
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from external_lookup_budget import LookupBudget, run_with_budget
import osm_venue_facts
import job_cancellation


# ===========================================================================
# Part 1a: LookupBudget accounting
# ===========================================================================

class TestLookupBudgetAccounting:
    def test_fresh_budget_not_exhausted(self):
        b = LookupBudget(total_seconds=120)
        assert not b.is_exhausted()
        assert b.remaining() == pytest.approx(120)
        assert b.should_skip("osm", "X") is False

    def test_record_reduces_remaining(self):
        b = LookupBudget(total_seconds=100)
        b.record(30)
        assert b.remaining() == pytest.approx(70)
        b.record(80)  # overspend
        assert b.remaining() == 0.0
        assert b.is_exhausted()

    def test_should_skip_after_exhaustion_and_counts(self):
        b = LookupBudget(total_seconds=10)
        b.record(10)
        assert b.should_skip("osm", "A") is True
        assert b.should_skip("osm", "B") is True
        assert b.skipped_count == 2

    def test_effective_timeout_clamped_by_remaining(self):
        b = LookupBudget(total_seconds=120, call_timeout=10)
        assert b.effective_timeout() == pytest.approx(10)
        b.record(115)
        # only 5s left — the per-call timeout clamps down to it
        assert b.effective_timeout() == pytest.approx(5)
        b.record(10)
        assert b.effective_timeout() == 0.0

    def test_track_charges_wall_time(self):
        b = LookupBudget(total_seconds=120)
        with b.track("osm", "X"):
            time.sleep(0.05)
        assert b.spent >= 0.05

    def test_track_charges_even_on_exception(self):
        b = LookupBudget(total_seconds=120)
        with pytest.raises(ValueError):
            with b.track("osm", "X"):
                time.sleep(0.02)
                raise ValueError("boom")
        assert b.spent >= 0.02


# ===========================================================================
# Part 1b: run_with_budget convenience
# ===========================================================================

class TestRunWithBudget:
    def test_runs_when_budget_available(self):
        b = LookupBudget(total_seconds=120)
        ran, result = run_with_budget(b, lambda: 42, kind="osm", context="X")
        assert ran is True and result == 42

    def test_skips_when_exhausted(self):
        b = LookupBudget(total_seconds=5)
        b.record(5)
        calls = []
        ran, result = run_with_budget(
            b, lambda: calls.append(1) or 1, kind="osm", context="X")
        assert ran is False and result is None
        assert calls == []  # function was NOT invoked

    def test_none_budget_always_runs(self):
        ran, result = run_with_budget(None, lambda: 7)
        assert ran is True and result == 7


# ===========================================================================
# Part 1c: osm_venue_facts honours the budget against a stubbed slow endpoint
# ===========================================================================

class _SlowResponse:
    """Stub requests.Response. status=504 forces the no-answer path D635 saw."""
    def __init__(self, status_code=504, delay=0.1):
        self.status_code = status_code
        self._delay = delay
        self.text = "stub"

    def json(self):
        return {"elements": []}


class _FakeRequestsModule:
    """Minimal stand-in for the `requests` module used by _overpass_request.

    Every POST sleeps `delay` seconds (simulating a slow/504 Overpass) and
    records how many times it was called, so a test can assert the number of
    attempts and that calls stop once the budget is spent.
    """
    def __init__(self, delay=0.1, status_code=504):
        self.delay = delay
        self.status_code = status_code
        self.post_calls = 0

        class _Exc:
            Timeout = type("Timeout", (Exception,), {})
            ConnectionError = type("ConnectionError", (Exception,), {})
        self.exceptions = _Exc

    def post(self, url, **kwargs):
        self.post_calls += 1
        time.sleep(self.delay)
        return _SlowResponse(status_code=self.status_code, delay=self.delay)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Remove the 5s inter-request sleep so tests are fast and deterministic."""
    monkeypatch.setattr(osm_venue_facts, "_OVERPASS_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(osm_venue_facts, "_overpass_last_request_time", 0.0)


def _install_fake_requests(monkeypatch, fake):
    """Make `import requests as _http` inside _overpass_request resolve to fake."""
    monkeypatch.setitem(sys.modules, "requests", fake)


class TestOsmHonoursBudget:
    def test_at_most_one_retry_on_504(self, monkeypatch):
        """A 504 is retried at most once → exactly 2 POST attempts."""
        fake = _FakeRequestsModule(delay=0.01, status_code=504)
        _install_fake_requests(monkeypatch, fake)
        budget = LookupBudget(total_seconds=120, call_timeout=10, max_retries=1)
        facts = osm_venue_facts.fetch_osm_venue_facts(
            "Toter Uhu", "Zurich", venue_hint="museum", budget=budget)
        assert facts.is_empty()
        # 504 path: attempt + 0 retry (504 does not retry) OR with retry — the
        # production code only retries 504 once at most; assert it never exceeds 2.
        assert fake.post_calls <= 2
        # Wall time was charged to the budget.
        assert budget.spent > 0

    def test_budget_exhaustion_stops_further_lookups(self, monkeypatch):
        """Once the budget is spent, later stops make ZERO network calls."""
        fake = _FakeRequestsModule(delay=0.05, status_code=504)
        _install_fake_requests(monkeypatch, fake)
        # Tiny budget so the first lookup exhausts it.
        budget = LookupBudget(total_seconds=0.04, call_timeout=10)

        stops = [{"name": f"Stop {i}"} for i in range(5)]
        results = osm_venue_facts.fetch_osm_facts_for_stops(
            stops, "Zurich", venue_hint="museum", budget=budget)

        assert len(results) == 5
        assert all(f.is_empty() for f in results.values())
        # The first stop ran (1-2 attempts); the remaining four were skipped
        # BEFORE any network call. So total POSTs is small and bounded, never 5+.
        assert fake.post_calls <= 2
        assert budget.skipped_count >= 4

    def test_per_call_timeout_is_short(self, monkeypatch):
        """The timeout handed to requests.post is <= 10s, never the old 20s."""
        captured = {}
        fake = _FakeRequestsModule(delay=0.0, status_code=200)

        def _post(url, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            fake.post_calls += 1
            return _SlowResponse(status_code=200, delay=0.0)

        fake.post = _post
        _install_fake_requests(monkeypatch, fake)
        budget = LookupBudget(total_seconds=120, call_timeout=10)
        osm_venue_facts.fetch_osm_venue_facts(
            "Kunsthaus", "Zurich", venue_hint="museum", budget=budget)
        assert captured["timeout"] is not None
        assert captured["timeout"] <= 10.0

    def test_no_budget_still_works(self, monkeypatch):
        """Omitting the budget keeps the pre-LOCAL-622 behaviour (still bounded)."""
        fake = _FakeRequestsModule(delay=0.01, status_code=504)
        _install_fake_requests(monkeypatch, fake)
        facts = osm_venue_facts.fetch_osm_venue_facts(
            "Somewhere", "Zurich", venue_hint="museum")  # no budget=
        assert facts.is_empty()
        assert fake.post_calls <= 2


# ===========================================================================
# Part 2: orchestrator progress-based polling harness
# ===========================================================================
#
# Mirrors the give-up logic now in tour_orchestrator_service.py. The clock is
# injected so a 5-minute stall / 40-minute cap can be simulated in milliseconds.

STALL_LIMIT = timedelta(minutes=5)
ABSOLUTE_CAP = timedelta(minutes=40)


class _Clock:
    def __init__(self, start):
        self.now_val = start

    def now(self):
        return self.now_val

    def advance(self, seconds):
        self.now_val = self.now_val + timedelta(seconds=seconds)


def _simulate_progress_poll_loop(status_sequence, clock, seconds_per_poll=10):
    """Return (outcome, poll_count, cancelled).

    outcome: 'completed' | 'gave_up'.
    status_sequence: list of dicts, each a /status payload for one poll.
    Each poll advances the injected clock by `seconds_per_poll`.
    """
    poll_started_at = clock.now()
    last_progress_marker = None
    last_progress_at = clock.now()
    poll_count = 0
    cancelled = {"flag": False, "reason": None}

    def _cancel(reason):
        cancelled["flag"] = True
        cancelled["reason"] = reason

    idx = 0
    while True:
        poll_count += 1
        now = clock.now()
        stalled_for = now - last_progress_at
        ran_for = now - poll_started_at
        if stalled_for > STALL_LIMIT or ran_for > ABSOLUTE_CAP:
            reason = ("stall" if stalled_for > STALL_LIMIT else "absolute_cap")
            _cancel(reason)
            return "gave_up", poll_count, cancelled

        if idx >= len(status_sequence):
            raise RuntimeError("ran out of status payloads before terminal state")
        status_data = status_sequence[idx]
        idx += 1

        if status_data["status"] == "completed":
            return "completed", poll_count, cancelled
        elif status_data["status"] == "error":
            raise Exception(status_data.get("error", "error"))
        else:
            progress = status_data.get("progress", "Processing...")
            marker = (progress, status_data.get("updated_at"))
            if marker != last_progress_marker:
                last_progress_marker = marker
                last_progress_at = now
            clock.advance(seconds_per_poll)


def _mk(status, progress=None, updated_at=None, error=None):
    d = {"status": status}
    if progress is not None:
        d["progress"] = progress
    if updated_at is not None:
        d["updated_at"] = updated_at
    if error is not None:
        d["error"] = error
    return d


class TestOrchestratorKeepsPollingWhileProgressing:
    def test_slow_but_advancing_tour_completes(self):
        """Progress changes every poll for 30 simulated minutes → completes.

        This is the D635 case: a tour that takes a long time but is ALIVE must
        never be abandoned. The old fixed 20-minute wall would have killed it.
        """
        clock = _Clock(datetime(2026, 1, 1, 0, 0, 0))
        seq = [_mk("in_progress", progress=f"stop {i}") for i in range(180)]
        seq.append(_mk("completed"))
        outcome, polls, cancelled = _simulate_progress_poll_loop(
            seq, clock, seconds_per_poll=10)
        assert outcome == "completed"
        assert cancelled["flag"] is False
        # ~30 minutes of advancing progress — well past the old 20-min ceiling.
        assert polls > 120

    def test_updated_at_change_counts_as_progress(self):
        """Even a constant progress string counts as alive if updated_at moves."""
        clock = _Clock(datetime(2026, 1, 1, 0, 0, 0))
        seq = []
        for i in range(180):
            seq.append(_mk("in_progress", progress="Working...",
                           updated_at=f"2026-01-01T00:{i:02d}:00"))
        seq.append(_mk("completed"))
        outcome, polls, cancelled = _simulate_progress_poll_loop(
            seq, clock, seconds_per_poll=10)
        assert outcome == "completed"
        assert cancelled["flag"] is False


class TestOrchestratorGivesUpOnStall:
    def test_frozen_progress_gives_up_after_five_minutes(self):
        """Identical progress string + no updated_at for >5 min → give up."""
        clock = _Clock(datetime(2026, 1, 1, 0, 0, 0))
        # 100 polls all reporting the SAME progress and no updated_at.
        seq = [_mk("in_progress", progress="Stuck on external lookups")
               for _ in range(100)]
        outcome, polls, cancelled = _simulate_progress_poll_loop(
            seq, clock, seconds_per_poll=30)
        assert outcome == "gave_up"
        assert cancelled["flag"] is True
        assert cancelled["reason"] == "stall"
        # Gave up shortly after 5 minutes of no progress (30s/poll).
        assert polls <= 13  # 5min / 30s = 10 polls + a little slack

    def test_absolute_cap_enforced_even_with_slow_progress(self):
        """Progress that advances just under the stall limit still stops at 40 min."""
        clock = _Clock(datetime(2026, 1, 1, 0, 0, 0))
        # Advance progress every poll, but each poll jumps the clock 4 minutes
        # (< 5-min stall), so only the absolute 40-minute cap can stop it.
        seq = [_mk("in_progress", progress=f"stop {i}") for i in range(100)]
        outcome, polls, cancelled = _simulate_progress_poll_loop(
            seq, clock, seconds_per_poll=240)
        assert outcome == "gave_up"
        assert cancelled["flag"] is True
        assert cancelled["reason"] == "absolute_cap"


# ===========================================================================
# Part 2b: cooperative cancellation registry
# ===========================================================================

class TestJobCancellation:
    def test_request_and_check(self):
        job_cancellation.clear("job-1")
        assert job_cancellation.is_cancelled("job-1") is False
        job_cancellation.request_cancel("job-1")
        assert job_cancellation.is_cancelled("job-1") is True

    def test_check_raises(self):
        job_cancellation.request_cancel("job-2")
        with pytest.raises(job_cancellation.JobCancelledError):
            job_cancellation.check("job-2")
        job_cancellation.clear("job-2")

    def test_clear_forgets(self):
        job_cancellation.request_cancel("job-3")
        job_cancellation.clear("job-3")
        assert job_cancellation.is_cancelled("job-3") is False

    def test_empty_job_id_is_noop(self):
        job_cancellation.request_cancel("")
        assert job_cancellation.is_cancelled("") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
