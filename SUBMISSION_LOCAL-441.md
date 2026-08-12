# SUBMISSION_LOCAL-441.md

## Summary

LOCAL-441 eliminates serial Wikidata P856 lookup wait from tour generation by
running them concurrently with a global wall-budget. Before: 38 serial timeouts ×
8s = 5–9.5 minutes. After: concurrent batch completes in ≤20s (budget), actual
measured 8.1s per batch.

## Changes (all in `work_story_searcher.py`)

1. **Module-scope constants** (importable by tests):
   - `EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS = 20.0`
   - `EXTERNAL_LOOKUP_POOL_SIZE = 10`
   - `EXTERNAL_LOOKUP_PER_TIMEOUT = 8`

2. **`batch_check_wikidata_p856(domains, budget_seconds, pool_size)`** — runs N
   lookups concurrently via `ThreadPoolExecutor`. When the budget expires, all
   unanswered lookups → tier3 (same outcome as a timeout today). Uses
   `shutdown(wait=False, cancel_futures=True)` so the caller doesn't block on
   still-running threads.

3. **`_classify_domain_quick(domain)`** — fast-path classification from rules
   alone (reject, tier1, tier2 by TLD/seed/list). Returns None when P856 is needed.
   Used to partition domains before the batch call.

4. **`_MODULE_DOMAIN_CACHE`** — module-level dict persisting across calls within
   a single process/run. Prevents re-asking the same domain.

5. **Refactored `search_stories_for_stop`** — now runs in 4 phases:
   - Phase 1: Execute all SERP queries (fast, ≤1s each)
   - Phase 2: Quick-classify domains from rules/cache
   - Phase 3: Batch remaining domains concurrently with wall-budget
   - Phase 4: Classify all results from the populated cache

6. **No changes to what is asked or how answers are judged** — same URLs, same
   SPARQL query, same parsing, same tier3/reject/tier1 semantics on failure.

## Env vars behind every number

- `DISABLE_TOUR_CACHE=1`
- `DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`
- `STORIED_MODE=true`
- `OPENAI_API_KEY=<set from .env>`
- `SERP_API_KEY=<set from .env>`
- `GENERATION_TIER=plus` (default)

## RED output (serial would be too slow)

```
test_serial_would_take_too_long:
  [RED] Serial execution of 10 lookups × 5.0s would take ≥50.0s
  [RED] Budget is 20.0s — batch must finish in ~budget time, NOT ~50.0s
PASSED
```

## Mocked-timing test results (12/12 pass)

```
test_batch_completes_within_budget:
  [GREEN] 10 lookups × 5.0s each
  [GREEN] Budget: 8.0s
  [GREEN] Actual elapsed: 5.15s
  [GREEN] Serial would have been: 50s
  [GREEN] Speedup: 9.7x
PASSED

test_budget_expires_treats_as_tier3:
  [GREEN] 20 domains, 3.0s each, budget=5.0s, pool=4
  [GREEN] Elapsed: 5.13s (budget enforced)
  [GREEN] All results: 20 (all get a tier)
PASSED

test_fast_lookups_return_quickly:
  [GREEN] 5 fast lookups (0.1s each)
  [GREEN] Elapsed: 0.25s (should be ~0.1s, not 20s budget)
PASSED

test_mixed_fast_and_slow:
  [GREEN] Mixed: 2 fast (museum) + 4 slow
  [GREEN] Elapsed: 4.09s (budget=4.0s)
  [GREEN] Results: {nationalmuseum.se: tier1, artmuseum.edu: tier1, ...rest: tier3}
PASSED

test_module_cache_persists_across_calls:
  [GREEN] Module cache hit — no P856 call made
PASSED

test_classify_domain_quick_avoids_p856:
  [GREEN] _classify_domain_quick('en.wikipedia.org') → tier1
  [GREEN] _classify_domain_quick('harvard.edu') → tier1
  [GREEN] _classify_domain_quick('pinterest.com') → reject
  [GREEN] _classify_domain_quick('totally-unknown-blog.xyz') → None (needs P856)
PASSED

test_batch_deduplicates_via_cache:
  [GREEN] Only 2 P856 calls made (cached domains skipped)
PASSED

TestConstants: 4/4 PASSED (all constants importable, sane ranges)
```

Full suite: **12 passed in 14.99s**

## Live run: Palais Lascaris (4 stops)

### Lookup counters

| Metric | Value |
|--------|-------|
| Domains checked (module cache) | 26 |
| Resolved as tier1 | 0 |
| Resolved as tier3 | 26 |
| P856 batch 1 (6 domains) | 8.1s |
| P856 batch 2 (1 domain) | 8.1s |
| Budget-expired | 0 (all completed within budget) |

All 26 domains timed out on Wikidata (server non-responsive) — same behavior as
before, but now concurrent instead of serial.

### Wall-clock

| Phase | Before (LEAD profile) | After (LOCAL-441) |
|-------|----------------------|-------------------|
| P856 external lookups | 5–9.5 min (38 serial timeouts × 8–15s) | ~16s (2 concurrent batches × 8s) |
| Total generation | ~10 min (Palais 595s, MFA 560s) | 336s (5.6 min) |

**External-lookup phase: ~16s total (target was ≤30s) ✓**

Note: total generation is 336s because per-stop LLM narration + story retries
are still serial (that is a separate task). The lookup wait is no longer dominant.

### D302 Control (Palais Lascaris)

| Check | Result |
|-------|--------|
| Stops generated | 4/4 ✓ |
| Date 1780 | ✓ (5 occurrences) |
| Date 1581 | ✓ (6 occurrences) |
| Date 1696 | ✓ (3 occurrences) |
| Date 1884 | ✗ (0 — D385 variance: stops selected are Harpe/1780, Sacqueboute/1581, Violes/1652, Basse/1696; Guitar/1884 was not in top-4 quality-ranked picks) |
| Stop 1 words | 311 ✓ |
| Stop 2 words | 230 ✓ |
| Stop 3 words | 177 ✓ |
| Stop 4 words | 397 ✓ |

D385 variance note: the quality-score packing algorithm now ranks Harpe (23.0),
Sacqueboute (23.0), Violes (20.0), Basse (18.0) above Guitar (17.5). This is
expected variance from LOCAL-438's quality-sorted selection — Guitar/1884 is the
5th pick, not in top 4. Story gate mode: LOG_ONLY.

## Files changed

- `work_story_searcher.py` — concurrent batch lookups + module cache + refactored flow
- `test_local441_concurrent_lookups.py` — 12 deterministic mocked-timing tests (NEW)
- `run_local441_acceptance.py` — live acceptance runner (NEW)
- `SUBMISSION_LOCAL-441.md` — this file (NEW)
