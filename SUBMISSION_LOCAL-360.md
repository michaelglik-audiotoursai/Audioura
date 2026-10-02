# SUBMISSION_LOCAL-360.md

## Summary

**Branch:** `kiro/local360-orchestrator-poll-resilience`  
**Base:** `storied`

A single slow status poll (ReadTimeout) was killing the entire tour job.
The generator was finishing the work — and the orchestrator was throwing it away
because a *progress check* took longer than 10 seconds. Fixed by making polls
resilient to transient failures.

---

## Files Changed

### `tour_orchestrator_service.py`

**Polling loop 1** (text-generation, line ~667):
- Wrapped `_authenticated_request("GET", .../status/...)` in
  `try/except (requests.Timeout, requests.ConnectionError)`.
- A failed poll logs with `[POLL-RESILIENCE]` prefix, increments a
  consecutive-failure counter, sleeps, and retries.
- Budget: 6 consecutive failures (~1 minute). On exhaustion, raises with a
  descriptive message including the failure count and elapsed wall-clock time.
- A successful poll resets the counter to 0.
- Per-poll timeout raised from 10 → 30 seconds.

**Polling loop 2** (modernized-service, line ~757):
- Identical treatment. Uses the same `_MAX_CONSECUTIVE_POLL_FAILURES` (6) and
  `_POLL_TIMEOUT` (30) constants defined in loop 1's scope.

### `tests/test_poll_resilience.py` (new)

10 pytest cases covering:
- Single timeout recovery (2 tests)
- Consecutive budget exhaustion (3 tests)
- Counter reset on success (3 tests)
- Original error propagation preserved (2 tests)

---

## Every Polling Loop Found

| # | Location (line ~) | Service polled | Fixed? |
|---|-------------------|---------------|--------|
| 1 | 667 | `tour-generator` `/status/{job_id_1}` | ✅ |
| 2 | 757 | `tour-processor` (modernized) `/status/{modernized_job_id}` | ✅ |

No other `while True` + status polling loops exist in the file.

---

## Overall Job Timeout

There is **no overall job timeout** in `orchestrate_tour_async`. The function
runs until either all steps complete or an exception is raised. Per the ticket:
"do not invent one — say so in the submission and leave it to LEAD."

---

## Test Output (verbatim)

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Applications/Xcode.app/Contents/Developer/usr/bin/python3
cachedir: .pytest_cache
rootdir: /Users/micha/audioura-worktrees/LOCAL-360
collecting ... collected 10 items

tests/test_poll_resilience.py::TestSingleTimeoutRecovery::test_timeout_on_poll_2_then_completes PASSED [ 10%]
tests/test_poll_resilience.py::TestSingleTimeoutRecovery::test_connection_error_on_poll_1_then_completes PASSED [ 20%]
tests/test_poll_resilience.py::TestConsecutiveBudgetExhaustion::test_six_consecutive_timeouts_fails PASSED [ 30%]
tests/test_poll_resilience.py::TestConsecutiveBudgetExhaustion::test_seven_consecutive_connection_errors_fails PASSED [ 40%]
tests/test_poll_resilience.py::TestConsecutiveBudgetExhaustion::test_five_consecutive_timeouts_then_success PASSED [ 50%]
tests/test_poll_resilience.py::TestCounterReset::test_timeout_success_timeout_success_completes PASSED [ 60%]
tests/test_poll_resilience.py::TestCounterReset::test_five_timeouts_success_five_timeouts_success PASSED [ 70%]
tests/test_poll_resilience.py::TestCounterReset::test_five_timeouts_success_then_six_timeouts_fails PASSED [ 80%]
tests/test_poll_resilience.py::TestOriginalBehaviourPreserved::test_status_error_still_raises PASSED [ 90%]
tests/test_poll_resilience.py::TestOriginalBehaviourPreserved::test_non_200_still_raises PASSED [100%]

======================== 10 passed, 1 warning in 0.17s =========================
```

---

## Live Run

**Not performed.** `OPENAI_API_KEY` is not set in this environment.
Unproven, handing to LEAD.

---

## Limitations

- The fix is purely in the orchestrator's polling loops. The generator's
  single-process Flask architecture (which makes it unresponsive during long
  crawls) is unchanged per ticket scope.
- The consecutive-failure budget (6) and poll timeout (30s) are constants
  local to the function, not configurable via env vars. If tuning is needed
  later, they can be extracted to env vars in a follow-up.
- No retry logic was added for the *initial* POST that starts the job or the
  download step — only the status polling loops. Those use different failure
  semantics (non-idempotent or large payload).
