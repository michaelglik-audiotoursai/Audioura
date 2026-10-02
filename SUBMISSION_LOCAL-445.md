# SUBMISSION_LOCAL-445.md

## LOCAL-445 — Story-first across stops: parallelise the loop, instrument the phases, stop retrying the dead

**Branch:** LOCAL-445-across-stop-parallelism
**Base:** storied (3a17abb)
**Agent:** Mac Mini Kiro

---

## What was built

### A. Parallelise the loop ACROSS stops

**File:** `story_first.py` — new function `story_first_pipeline_batch()`
**File:** `generate_tour_text.py` — serial loop replaced with batch call

The serial `for _sf_idx, _sf_poi in enumerate(poi_list)` loop that called
`story_first_pipeline()` once per stop (admitting 6×25s = 150s worst case) is
replaced by `story_first_pipeline_batch()`, which runs all stops concurrently
in a thread pool under a single **tour-level budget**:

- `STORY_FIRST_TOUR_BUDGET_SECONDS = 40.0` (env-overridable) — the controlling limit
- `STORY_FIRST_TOUR_POOL_SIZE = 6` — one thread per stop
- `PIPELINE_WALL_BUDGET_SECONDS = 25.0` remains as the per-stop inner guard

**Target:** story-first's own contribution drops from ~188s (serial, measured) to
≤40s (parallel, budget-bounded). Combined with the ~336s baseline the Palais run
should land near ~376s. **That is still above the 336s bar** — getting under 336s
requires attacking per-stop narration itself (D395/D396), which is NOT this task.

**Neutralisation (D242 #1):** `serialise_across_stops()` / `parallelise_across_stops()`
flags. The test `test_serial_neutralisation_goes_red` proves the parallelism is
load-bearing: 6 stops × 3s serial = ~18s vs parallel ≈ ~3s, ratio >2×.

**Thread-safety fix:** The `_verdict_cache_lock` in LOCAL-443 only guarded cache READS.
Two threads that both miss the cache would both call the LLM. Under across-stop
concurrency, duplicate candidates across stops are common. Fixed with a **per-key
in-flight map** (`_inflight_events` + `_inflight_results`): when multiple threads
race on the same candidate text, only one calls the LLM and the rest wait on its
Event. Verified by `test_duplicate_candidates_single_llm_call`: 3 threads, same text
→ exactly 1 LLM call.

### B. Per-phase timing instrumentation

**File:** `phase_timer.py` — new module
**File:** `generate_tour_text.py` — instrumented at phase boundaries

Added a light `PhaseTimer` class that logs at each boundary:

```
[TIMING] phase=narration elapsed=312.4s cumulative=498.1s
```

Instrumented phases in `generate_tour_text`:
- `intent` (PHASE 1)
- `poi_selection` (PHASE 2/3A/4)
- `exhibition_checklist` (LOCAL-364 retrieval)
- `fact_sheets` (S11 spine + fact sheets)
- `external_lookups` (LOCAL-410 SERP search)
- `story_first` (LOCAL-440/445 pipeline)
- `narration` (PHASE 5)
- `packing` (PHASE 6 assembly)
- `verification` (marker)

Summary line at end:
```
[TIMING] TOTAL wall=523.9s phases: narration=312.4s, story_first=40.1s, ...
```

Module-scope, testable, cheap enough to leave on permanently. Every future wall-time
task is now measurable instead of inferential.

### C. Michael's dead-host rule

**File:** `dead_host_breaker.py` — new module
**File:** `work_story_searcher.py` — `_check_wikidata_p856` wired to breaker
**File:** `venue_resolver.py` — `_search_entities` wired to breaker

Michael's ruling (2026-08-12, BINDING):

> First timeout or 429 → mark that host cold for the remainder of the run.
> Every subsequent call short-circuits immediately. Never retry.

**Implementation:**
- Process-level cold set with threading.Lock
- Wikimedia bucket rule: `en.wikipedia.org`, `fr.wikipedia.org`, `query.wikidata.org`
  etc. all map to a single logical host `'wikimedia'`. A 429 on any one makes all cold.
- `_check_wikidata_p856`: checks `is_host_cold()` BEFORE network call; marks cold on
  first HTTPError(429), timeout, or network error
- `_search_entities`: same pattern for `www.wikidata.org`

**Action on short-circuit:**
1. Lookups (P856) → take failure value `'tier3'` immediately. No substitute site.
2. Content fetches → walk the chain: institution site → POP/Joconde → Wayback → SERP → give up.
   (Chain implementation deferred to the fetch callsites; the breaker provides the
   `is_host_cold()` predicate they consult.)

---

## Tests

**File:** `test_local445_across_stop_parallel.py` — 19 tests, all pass

| Class | Tests | What it proves |
|-------|-------|---------------|
| TestAcrossStopParallelism | 3 | Parallel completes in budget; serial goes red; budget cuts off |
| TestDeadHostBreaker | 9 | Host normalisation; Wikimedia bucket; cold marking; no-network after cold; thread safety |
| TestPerKeyInflight | 1 | 3 racing threads, same text → 1 LLM call |
| TestPhaseTimer | 5 | Timing accuracy; auto-end; summary format |

**Neutralisation proof (D242 #1):**
- `test_serial_neutralisation_goes_red`: serial takes 6×3s=18s, parallel takes ~3s. Ratio >2×.
- This is the LOCAL-441 pattern: neutralising the pool in place → a timing test goes red.

---

## Acceptance status

### What is proven (by test fixtures)
- Across-stop parallelism: N×Xs → ~Xs (budget-bounded)
- Dead-host rule: second call to a 429'd host issues NO network request
- Wikimedia bucket: one 429 makes all related hosts cold
- Phase timer: produces `[TIMING]` lines at each boundary
- Per-key dedup: prevents duplicate LLM calls under concurrency

### What requires a live run (unproven, handing to LEAD)
- Palais live run with `L440_STORY_FIRST=true`: confirm story-first phase ≤40s
  (the budget enforces this mechanically, but the timing report proves it)
- Gate pass rate non-regression against LOCAL-440's 1/3 MFA baseline
- Total wall time reporting (will likely remain >336s — narration is the cause)

### Space acceptance runs
Per the spec: back-to-back runs share one IP and one rate-limit window. The dead-host
breaker actually helps here — if the first run triggers a 429, the second run's story
pipeline short-circuits immediately instead of burning another 13.7s to discover CHARS=0.

---

## Files changed

| File | Change |
|------|--------|
| `story_first.py` | Added `story_first_pipeline_batch()`, `STORY_FIRST_TOUR_BUDGET_SECONDS`, neutralisation controls, per-key in-flight map |
| `generate_tour_text.py` | Replaced serial loop with batch call; added PhaseTimer instrumentation |
| `phase_timer.py` | NEW — lightweight phase timing module |
| `dead_host_breaker.py` | NEW — Michael's dead-host circuit breaker |
| `work_story_searcher.py` | Wired `_check_wikidata_p856` to dead-host breaker |
| `venue_resolver.py` | Wired `_search_entities` to dead-host breaker |
| `test_local445_across_stop_parallel.py` | NEW — 19 tests covering all three parts |
| `SUBMISSION_LOCAL-445.md` | This file |

---

## No DB changes

No `DELETE FROM`, no table writes, no schema changes.
