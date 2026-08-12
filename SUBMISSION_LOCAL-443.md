# SUBMISSION_LOCAL-443.md — Story-first earns its wall time

## Status: Implementation complete, pending live-artifact gate

## Summary

LOCAL-443 addresses the two diagnosed causes of LOCAL-440's wall-time regression
(Palais 336s→535s) and gate-rate stagnation (1/3 MFA):

1. **SERP snippets are ~150 chars — too short for a 3-sentence story arc.**
   → Full-page fetch extracts actual prose from tier1/tier2 URLs.
2. **Per-candidate gpt-4o-mini classification is the wall-time cost** (17–62
   candidates/stop × per-call latency, serial).
   → Pre-filter reduces volume to ≤10; concurrent classification amortises latency.

## Implementation (in `story_first.py`)

### A. Full-page fetch for promising URLs

- `fetch_full_pages(urls, budget_seconds)`: Fetches full HTML for the TOP ≤3
  tier1/tier2 SERP results per stop.
- `_fetch_single_page(url)`: HTTP fetch with LOCAL-427-style 429 retry (one
  retry after short backoff). Uses `urllib.request` for zero-dependency simplicity.
- `_extract_page_text(html)`: Paragraph extraction mirroring
  `exhibition_checklist._fetch_page` (LOCAL-373-safe regex, strips nav/scripts).
- Fetched pages feed into `story_gate.extract_candidate_story_units()` to produce
  actual story-arc candidates (3+ sentences) instead of 150-char fragments.
- Concurrent fetch: `ThreadPoolExecutor(max_workers=3)` with wall-budget (LOCAL-441
  pattern — `concurrent.futures.wait` with timeout).
- Neutralisation: `disable_fullpage_fetch()` / `enable_fullpage_fetch()` at module
  scope. Test `test_volume_explosion_when_disabled` proves removal degrades.

### B. Candidate pre-filter (zero-cost, before any LLM call)

- `prefilter_candidates(candidates, stop_name)`:
  1. SHA-256 deduplication (first 16 hex chars) within the stop.
  2. Reject if < 3 sentences (cannot have setup → struggle → resolution).
  3. Reject if no person-name-shaped token (multi-word proper noun regex).
  4. Cap at `PREFILTER_MAX_CANDIDATES = 10` (longest first — more likely arcs).
- Neutralisation: `disable_prefilter()` / `enable_prefilter()` at module scope.
  Test proves candidate volume explodes from 5 → 20 when disabled (D242 #1).

### C. Classification concurrency

- `evaluate_candidates_concurrent(candidates, snippets, ..., budget_seconds)`:
  - Phase 1: `ThreadPoolExecutor(max_workers=5)` dispatches `classify_story_unit`
    for all candidates concurrently (60% of classification budget).
  - Phase 2: Sequential verification for passing candidates (40% of budget).
  - `_verdict_cache_lock = threading.Lock()` guards cache reads in
    `_classify_single_candidate` to prevent redundant LLM calls. Dict assignment
    itself is atomic under CPython GIL.
- Budget-aware: when wall budget exhausted, returns what's verified so far and
  logs the early exit.

### D. Budget discipline (D395)

- `PIPELINE_WALL_BUDGET_SECONDS = 25.0` — hard per-stop wall budget for the
  ENTIRE pipeline (fetch + extract + pre-filter + classify + verify + adapt).
- Budget checks at every phase boundary. On exhaustion: return verified stories
  so far, set `budget_exhausted=True` in result, log.
- SERP query budget reduced to `min(15s, 50% of remaining)` to leave room.
- Full-page fetch budget: `min(remaining × 0.4, 10s)`.
- Classification budget: `remaining - 2s` (reserve 2s for adaptation).
- Expected per-stop cost: ≤10 candidates × gpt-4o-mini (~200 input tokens
  each) ≈ $0.0003/stop classification + $0.006/tour SERP = well within
  $0.05/tour budget.

## Test Results

```
test_local443_fullpage_prefilter.py: 21 passed (1.93s)
test_local427_fetch_backoff.py:      21 passed (3.88s) — no regression
test_local441_concurrent_lookups.py: 12 passed (14.39s) — no regression
```

## Neutralisation Proofs (D242 #1)

1. **Pre-filter disabled → volume explodes**: `test_volume_explosion_when_disabled`
   shows 5 valid candidates → 20 reach classifier when pre-filter off.
2. **Full-page fetch disabled**: `test_disabled_returns_empty` — zero candidates
   from pages. Without full-page text, only SERP snippets (~150 chars) serve as
   candidates; `extract_candidate_story_units` requires ≥3 sentences of prose.

## Acceptance Readiness

### Items requiring live runs (PARKED — awaiting LOCAL-442 merge):

1. **MFA Unbound live run** with `L440_STORY_FIRST=true` + D261/D262 env:
   target 3/3 gate pass. Unproven — requires live SERP + OpenAI calls.

2. **Palais Lascaris live run** with flag on: target ≤336s.
   The architectural improvements (pre-filter ≤10 candidates, concurrent
   classify, 25s budget cap) should reclaim the 535→336s regression:
   - Pre-filter: eliminates 60-80% of candidates before LLM (was 17-62, now ≤10)
   - Concurrency: 5 parallel classify calls ÷ serial = ~5× latency reduction
   - Budget cap: hard 25s/stop prevents runaway

3. **Cost per tour**: SERP ($0.001/query × 6 queries × 8 stops = $0.048) +
   classification ($0.0003/stop × 8 = $0.0024) + fetch (free) = ~$0.05/tour.

4. **Flip `L440_STORY_FIRST` default**: separate commit, clearly labeled.

## What's unproven

- Live MFA gate rate improvement (requires D261/D262 env + live SERP)
- Live Palais wall time (requires full pipeline execution on actual tour)
- Exact cost per tour under production conditions

These require live-artifact runs which are blocked on LOCAL-442 merging (both
touch `generate_tour_text.py`). The fixture tests validate the architectural
soundness; the live runs validate the outcome.

## Files changed

- `story_first.py` — rewritten with LOCAL-443 A/B/C/D enhancements
- `test_local443_fullpage_prefilter.py` — 21 tests (new)
- `SUBMISSION_LOCAL-443.md` — this file
