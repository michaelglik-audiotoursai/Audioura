# SUBMISSION — LOCAL-572: Dead-host marks must end with the tour, not the process

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-572-cold-host-per-tour`
**Base:** storied (`f1d0808`) — verified `git merge-base --is-ancestor f1d0808 HEAD` exits 0.

## The defect

`dead_host_breaker.py` kept a **module-level** cold set. Michael's binding ruling
(2026-08-12): on the first 429/timeout, mark the host cold "for the remainder of the
run" — and a run is one tour. But `reset_cold_hosts()` is only called by tests and
`repro449.py`; no production code called it. The tour-generator container and Cloud Run
instances are long-lived processes, so **one Wikimedia 429 disabled Wikipedia + Wikidata
for every later tour served by that process** until restart. Museum tours then clean-fail
as `[D1] Tier: unresolvable`.

## Fix

The cold set is now scoped to one top-level tour generation via `contextvars.ContextVar`.

### `dead_host_breaker.py`
- `_tour_cold_hosts: ContextVar[Optional[Set]]` holds the active tour's cold set;
  `_default_cold_hosts` is the module-level fallback.
- `_active_cold_set()` returns the tour's set when a scope is active, else the default set.
- `mark_host_cold` / `is_host_cold` / `get_cold_hosts` / `reset_cold_hosts` all operate on
  `_active_cold_set()`. **Public API signatures unchanged.** When no tour scope is active
  (direct unit-test calls, callers that never enter a tour) they use the default set, so
  pre-LOCAL-572 behaviour is preserved for those callers.
- New: `begin_tour_scope()` / `end_tour_scope(token)` / `tour_scope` (context manager)
  install a fresh empty set for one tour.
- New: `copy_tour_context()` returns the active cold-set object; `run_in_tour_context(set, fn, …)`
  re-binds that same set in a worker thread. (A shared `contextvars.Context` cannot be entered
  by more than one worker at a time — "cannot enter context: … is already entered" — so we
  re-bind the var per worker to the same shared, lock-guarded set object instead.)

### Top-level entry (cite)
- `generate_tour_text.py:5897` — `begin_tour_scope()` is called at `generate_tour_text(...)`
  entry, right beside the existing `reset_network_failure_count()` per-run reset. This is the
  single top-level entry the services call for a new tour (the Flask routes in
  `generate_tour_text_service.py:604` / `tour_orchestrator_service.py` dispatch to it on a
  per-request `threading.Thread`, so each tour already runs in its own contextvar state —
  concurrency isolation falls out for free).

### Worker-thread propagation (per-tour fan-out points)
- `story_first.py` `story_first_pipeline_batch(...)` — the across-stop pool captures
  `copy_tour_context()` and submits each stop via `run_in_tour_context(...)`.
- `work_story_searcher.py` `batch_check_wikidata_p856(...)` — same pattern for the per-domain
  P856 pool, so the first 429 within a tour keeps the Wikidata bucket cold for the remaining
  domains in that tour.

Within one tour the rule is unchanged: first 429/timeout → cold, no retries.

## Tests

`tests/test_local572_cold_host_per_tour.py` (7 tests, all green on this branch):

- **(a)** `test_cold_mark_does_not_persist_across_tours` — host cold in tour 1 is NOT cold in
  tour 2 run afterwards in the same process. Plus `test_wikipedia_recovers_next_tour`.
- **(b)** `test_cold_persists_within_tour_across_stops`,
  `test_cold_mark_from_worker_thread_visible_tour_wide` (mark made in a worker thread is visible
  tour-wide), `test_wikimedia_bucket_still_shared_within_tour`.
- **(c)** `test_concurrent_tours_isolated` and `test_concurrent_tours_via_real_batch` (end-to-end
  through the real `story_first_pipeline_batch` fan-out) — a cold mark in one tour does not leak
  into a concurrently-running tour.

### (a) is RED on storied — shown

storied has no `begin_tour_scope()`, so the scenario was reproduced using only the storied
public API (two back-to-back tours in one process, no reset between them — because production
never resets):

```
=== storied has begin_tour_scope? ===  ->  0 (absent)
  [DEAD-HOST] Marked cold: wikimedia (429)
tour2 sees Wikidata cold = True
AssertionError: RED on storied: cold mark from tour 1 LEAKED into tour 2
```

Same scenario on this branch: `test_cold_mark_does_not_persist_across_tours` **PASSED**.

### Full suite (exits)

New suite:
```
tests/test_local572_cold_host_per_tour.py ....... 7 passed in 0.54s
```

Dead-host regression check (LOCAL-445/447/448/449/450/451 + D495):
```
122 passed, 2 deselected, 1 warning in 34.73s
```

The 2 deselected tests
(`test_local445_across_stop_parallel.py::TestDeadHostBreaker::test_p856_marks_cold_on_first_429`
and `::test_p856_marks_cold_on_timeout`) are **pre-existing failures on storied** — verified by
restoring the storied versions of `dead_host_breaker.py` and `work_story_searcher.py` and running
them: both fail identically (`'unverified' != 'tier3'`, a stale D495/D459 expectation in the test,
unrelated to this change). They are not regressions from LOCAL-572.

`python3 -m py_compile dead_host_breaker.py story_first.py work_story_searcher.py generate_tour_text.py` → OK.

## Live generation

None run. No DB writes, no GCloud, no DELETE.
