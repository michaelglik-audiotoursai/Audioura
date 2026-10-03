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


---

## r2 — every worker thread must be inside the tour scope

**Base:** `LOCAL-572-cold-host-per-tour` HEAD = `a2a10c5` — verified
`git merge-base --is-ancestor a2a10c5 HEAD` exits 0.

### Why r1 bounced

The ContextVar design was right, but only 3 pools copied the context. A worker
thread that does **not** copy the context starts with the default (empty)
contextvar state and so falls back to the **process-level default set** — the
exact leak this task removes. The per-stop parallel pools (LOCAL-441/445), where
most Wikipedia/Wikidata fetches run, were raw `ThreadPoolExecutor`s, so a 429
marked from a stop worker in tour 1 still poisoned every later tour in the
process.

### 1. One helper, used everywhere on the tour path

Added to `dead_host_breaker.py`:

- **`TourExecutor`** (subclass of `concurrent.futures.ThreadPoolExecutor`) +
  factory **`tour_executor(max_workers=…)`**. It captures the active tour's cold
  set **once, at construction** (the constructor runs on the tour thread, inside
  the scope), and its `submit()` / `map()` run every callable through
  `run_in_tour_context(captured_set, …)`. So no matter which thread calls
  `submit`, the worker re-binds the tour's set and a 429 marked by a worker
  stays cold for this tour only. When no tour scope is active it behaves exactly
  like a plain `ThreadPoolExecutor` (falls through to the default set).
- **`tour_thread(target=…, args=…, kwargs=…, **thread_kwargs)`** — same idea for
  a bare `threading.Thread`: captures the tour set on the calling thread and
  re-binds it inside the new thread's target.

### Pools converted (file:line on a2a10c5 → now `tour_executor`)

Every `ThreadPoolExecutor` reachable from `generate_tour_text()`:

- `generate_tour_text.py` — **10** pools: lines 1602, 2966, 6390, 10013, 10038,
  10150, 10650, 10778, 14994, 17135. Module-level `from dead_host_breaker import
  tour_executor` added.
- `fact_extractor.py:233` — per-POI RAG context fan-out.
- `story_element_extractor.py:779` — concurrent Tier-1/2 page fetch.
- `venue_parts.py:709` — grounded story-chain `pool.map(_one, pairs)`.
- `story_first.py` — lines 396 (SERP search), 630 (full-page fetch), 959
  (candidate classify), and 1592 (per-stop across-stop pool — the r1 manual
  `copy_tour_context`/`run_in_tour_context` wrap simplified to `tour_executor`).
- `work_story_searcher.py:385` — per-domain P856 pool (r1 manual wrap likewise
  simplified to `tour_executor`).

`scope_memory.py` has **no** pool — the earlier count was a comment match
(`ThreadPoolExecutor` appears only in a prose comment at line 67).

### Services intentionally left as-is (never run inside a tour)

These create a `threading.Thread`/pool but do so **outside** any tour scope —
they are the per-request dispatchers that *launch* a tour on a fresh thread, or
background workers unrelated to tour generation. There is no tour scope for them
to inherit, and converting them would be wrong:

- `tour_orchestrator_service.py` (1791, 1803), `generate_tour_text_service.py`
  (675), `tour_generation_service.py` (186) — Flask routes that spawn the
  per-request tour thread. `generate_tour_text()` opens its own scope *inside*
  that thread (r1).
- `modified_tour_orchestrator_service.py` (413),
  `modified_generate_tour_text_service.py` (109) — modified variants of the
  above, same role.
- `background_article_processor_service.py` (60) — background queue worker, not
  on the tour path.
- `translation-service/translation_service.py` (27) — separate microservice.
- `tour_generation_modernized.py` (486, 545) — dispatcher threads, not tour
  internals.

### 2. Safety net: 15-minute expiry on the default set only

The module-level default cold set is now a dict `host -> monotonic mark time`.
Entries older than **15 minutes** (`_DEFAULT_COLD_TTL_SECONDS = 900`) are purged
on the next read/write (`_purge_expired_default_locked`). So if any pool is ever
missed, a stray 429 recorded in the default set self-heals in 15 min instead of
poisoning the process forever. **Inside a tour scope nothing expires** — the
tour set stays a plain `set()`; Michael's rule is unchanged (first 429 = cold
for the rest of the tour, no time-based mid-tour recovery). The public API
(`mark_host_cold` / `is_host_cold` / `get_cold_hosts` / `reset_cold_hosts`)
branches on `_in_tour_scope()`; signatures unchanged.

### 3. Lint test — `tests/test_local572_pools_in_scope.py`

Walks the AST of each tour-call-graph module and fails on any
`ThreadPoolExecutor(` or `threading.Thread(` **call** that is not
`tour_executor`/`tour_thread`. Import statements are not calls, so
`from concurrent.futures import ThreadPoolExecutor` (still needed for
`as_completed`/`wait`) does not trip it. The guarded module list is explicit in
the test.

- **GREEN on HEAD:** `2 passed`.
- **Would be RED on a2a10c5:** the same detection logic run against the a2a10c5
  sources finds **18** raw constructions (gtt 10, fact 1, story_element 1,
  venue 1, story_first 4, wss 1 — including the two r1 manual wraps that still
  wrapped a raw pool).

### 4. Behaviour test with a real pool — `tests/test_local572_real_pool_cross_tour.py`

Two back-to-back tours in one process, each in its own thread (as the services
run them). Tour 1 marks a host cold from **inside a `tour_executor` per-stop
worker**; asserts the mark is visible to all stops and the tour-1 main thread,
then asserts tour 2's pool workers + main thread do **not** see it cold and the
process default set stays empty.

- **GREEN on HEAD:**
  ```
  tests/test_local572_real_pool_cross_tour.py .   1 passed in 0.10s
  ```
- **RED on a2a10c5** (reproduced with the base public API, since `tour_executor`
  doesn't exist there — a raw per-stop pool worker marks cold with no context
  copy; a later tour's raw worker reads the same process default set):
  ```
    [DEAD-HOST] Marked cold: wikimedia (429)
  AssertionError: RED on a2a10c5: tour1 cold mark LEAKED into tour2 via process default set
  ```

### Regression (exits)

```
tests/test_local572_cold_host_per_tour.py ....... 7 passed            (exit 0)
tests/test_local572_pools_in_scope.py ..          2 passed            (exit 0)
tests/test_local572_real_pool_cross_tour.py .     1 passed            (exit 0)
test_local445_across_stop_parallel.py             17 passed, 2 failed (exit 0 w/ -k deselect: 17 passed, 2 deselected)
```

The 2 failures in `test_local445_across_stop_parallel.py`
(`test_p856_marks_cold_on_first_429`, `test_p856_marks_cold_on_timeout`:
`'unverified' != 'tier3'`) are the **same pre-existing failures documented in
r1** — confirmed again by running them in a pristine detached worktree at
`a2a10c5`: they fail identically there with none of these changes. Likewise the
2 budget-sensitive failures in `test_local441_concurrent_lookups.py`
(`test_budget_expires_treats_as_tier3`, `test_mixed_fast_and_slow`) fail
identically on a clean `a2a10c5` worktree — not regressions from LOCAL-572.

`python3 -m py_compile` on all converted modules → OK.

### Live generation

None. No DB writes, no GCloud, no DELETE.
