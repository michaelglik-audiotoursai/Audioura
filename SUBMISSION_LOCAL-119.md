##### READY FOR REVIEW

# LOCAL-119: Prolog Resilience — A network blip gives the listener a terse question instead of an opening

**Branch:** `kiro/local119-prolog-resilience`  
**Commit:** `bdfb5d4`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02

---

## Summary

When the prolog-generation LLM call in `generate_tour_text.py:6170` fails (network
timeout, HTTP 5xx), the old code fell back to the raw `tour_hook` — an 11–25 word
formulaic question like "What secrets lie beneath the sun-soaked elegance of Nice's
vibrant streets?" This is terse, question-form, and a poor opening for a tour.

This fix adds:
1. A retry with exponential backoff for transient failures
2. An improved fallback hierarchy (Stop 1's first two prose sentences > raw hook)
3. WARNING-level logging on all failure paths
4. A safety net ensuring prolog failure never blocks tour delivery

---

## Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text.py` | Lines ~6169–6270: replaced bare LLM call + weak fallback with retry loop, transient/non-transient classification, improved fallback hierarchy, and dedicated WARNING logger |
| `tests/test_local119_prolog_resilience.py` | New — 25 tests covering retry logic, fallback quality, non-retry on non-transient errors, tour delivery continuity, code structure verification |
| `SUBMISSION_LOCAL-119.md` | New — this file |

---

## Acceptance Evidence

### AC1: Evidence of how often the fallback path is taken

**It has never fired in available logs.** Container logs for `audioura-tour-generator-1`
show 6 successful prolog generations (`[R2] Prolog saved for Stop 1`) and zero instances
of `[R2] Prolog fallback` or `[PROLOG] Error`. All 3 storied tours in the database
(IDs 27, 28, 29) have proper expanded prologs in their Stop 1 content.

There is no database-level prolog failure log (the `cost_ledger` and `job_status` tables
have no prolog-specific entries). The fallback path's only record would be stdout in
the container logs, which rotate. **Conclusion: the fallback has never fired in the
available log window (18 hours of container uptime), but cannot be proven never-fired
historically because container logs don't persist across restarts.**

### AC2: Retry implemented with transient/non-transient distinction

**Transient (retry once after 2s backoff):**
- HTTP status codes: 429, 500, 502, 503, 504
- Network exceptions: `requests.exceptions.Timeout`, `requests.exceptions.ConnectionError`

**Non-transient (no retry, immediate fallback):**
- HTTP status codes: 400, 401, 403, 404 (any code not in the transient set and ≠ 200)
- Unexpected exceptions (e.g., JSON parse failure on a 200 response)

**Rationale:** A 429 or 5xx is the server saying "try later" — a retry after 2 seconds
has high probability of success. A 400/401/403 means the request itself is wrong (bad
prompt, bad key, wrong endpoint) — retrying burns money with zero chance of success.
Only 1 retry (2 total attempts) to keep the time impact ≤ 17s worst case (15s timeout
+ 2s backoff) and the cost impact at +$0.0008.

### AC3: Forced failure evidence (test output)

```
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_retry_on_500_then_success PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_retry_on_429_then_success PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_retry_on_timeout_then_success PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_retry_on_connection_error_then_success PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_two_500s_exhausts_retries_uses_stop1_prose PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_two_timeouts_exhausts_retries PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_no_retry_on_400 PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_no_retry_on_401 PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_fallback_prefers_stop1_prose_over_raw_hook PASSED
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_tour_never_blocked_by_prolog_failure PASSED
```

**Forced single failure → retry succeeds:** `test_retry_on_500_then_success` — HTTP 500
on first attempt, 2s backoff logged at WARNING, second attempt returns 200, prolog saved.

**Forced double failure → improved fallback:** `test_two_500s_exhausts_retries_uses_stop1_prose` —
two 500s exhaust retries, fallback uses Stop 1's first two prose sentences ("The grand
hall opens before you. Its marble floors gleam under crystal chandeliers.") instead of the
raw hook question.

### AC4: Tour delivered in every failure case with WARNING logged

```
tests/test_local119_prolog_resilience.py::TestPrologRetryLogic::test_tour_never_blocked_by_prolog_failure PASSED
```

This test forces all four failure types (double 500, 400, double timeout, double
connection error) and asserts:
1. No exception propagates (the block completes)
2. All log records are at WARNING level (not ERROR, not raised)

The outer `except Exception` safety net (line ~6267) ensures even unexpected errors
in the retry loop itself cannot block tour delivery.

### AC5: Cost of a retry against the $1.30 ceiling

| Component | Cost |
|-----------|------|
| Baseline tour cost | $0.068 |
| One prolog retry (GPT-3.5-turbo, ~400 tokens) | +$0.0008 |
| **Worst-case total** | **$0.0688** |

The retry adds $0.0008 in the worst case (transient failure that resolves on retry).
If both attempts fail, only one API call was billed (the failed retry returns an error
before consuming tokens on the provider side for 5xx; for timeouts, partial billing is
possible but ≤ $0.0008). Against the $1.30 ceiling, this is negligible (5.3% of baseline,
0.053% of ceiling).

---

## Verbatim Evidence

### Evidence: Container logs show zero fallback occurrences

```
$ docker logs audioura-tour-generator-1 2>&1 | grep -i "prolog fallback\|PROLOG.*Error\|R2.*fallback"
(no output)
```

### Evidence: 6 successful prolog generations in current log window

```
$ docker logs audioura-tour-generator-1 2>&1 | grep -c "\[R2\] Prolog saved"
6
```

### Evidence: All storied tours have proper expanded prologs

Tour 27 Stop 1: "You are about to embark on a journey through the Asian Arts Museum of Nice, a book of interconnected chapters..."
Tour 28 Stop 1: "You are about to embark on a captivating journey through the Asian Arts Museum of Nice, a cultural gem inaugurated on October 16, 1998..."
Tour 29 Stop 1: "You are about to embark on a journey through the sun-soaked streets of the French Riviera, a tapestry woven with threads..."

All are 80–190 word expanded prologs, not raw hook questions.

### Evidence: Full test suite passes

```
$ python3 -m pytest tests/test_local119_prolog_resilience.py -v
======================== 25 passed, 1 warning in 0.18s =========================
```

### Evidence: Syntax valid

```
$ python3 -c "import py_compile; py_compile.compile('generate_tour_text.py', doraise=True)"
(no error)
```

---

## Limitations

1. **No live LLM failure test** — Cannot trigger a real OpenAI failure without Docker
   rebuild (constraint: builder is hung). Retry logic is proven via mock-based unit tests
   that replicate the exact code path. A live proof would require a running container
   with the new code, which requires a Docker build.

2. **No live audio playback verification** — Cannot confirm the fallback text sounds
   acceptable when spoken by Polly TTS. The Stop 1 prose fallback is grammatically
   complete English sentences, which Polly handles well, but this is inferred not proven.

3. **Historical fallback frequency unknown** — Container logs rotate on restart. The
   current 18-hour window shows zero fallbacks, but cannot prove it has never occurred
   over the lifetime of the service.

4. **No integration test against the full pipeline** — The change is structurally
   validated (syntax check + static analysis tests) and behaviorally validated (25
   mock-based tests), but not exercised via a real `generate_tour_text()` invocation
   due to the Docker build constraint.

---

## Database Verification

```
Row count before: 88
Row count after:  88
```

No rows inserted, deleted, or modified.
