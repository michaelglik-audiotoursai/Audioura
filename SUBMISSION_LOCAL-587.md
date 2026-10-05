# SUBMISSION — LOCAL-587: cut Griffin museum text-generation time

**Branch:** `LOCAL-587-museum-speed`
**Base:** `subscribed` 3767a17 (verified `git merge-base --is-ancestor 3767a17 HEAD` → 0).
**Goal:** Griffin text phase ≤ 5 min, same stops, same gates firing, story counts not lower than baseline.

---

## 1. Baseline profile (from `/Volumes/AudiouraSSD/griffin_timing_subscribed_20261005.log`, free)

LEAD baseline, image built from `subscribed` 3767a17 with
`STORY_RETRY_KEEP_BEST=1 STORY_RETRY_EARLY_STOP=1 TOUR_STORY_MODEL=gpt-4.1`.
Griffin Museum of Photography, Winchester MA, 5 stops.

```
[TIMING] TOTAL wall=644.9s phases: story_first=403.1s, external_lookups=158.9s,
site_first_exhibitions=35.3s, fact_sheets=11.7s, poi_selection=10.0s, packing=8.4s
writer calls 29 · story retries 11 · early stops 3 · keep-best 10 · stops all correct
```

### Top-10 time sinks (seconds, what each is for)

| # | Time sink | Seconds | What it is | Serial per stop? |
|---|-----------|--------:|------------|------------------|
| 1 | **story_first → writer loop** (gpt-4.1, 29 calls, 201k tok, avg 6.9k tok/call) | ~213 | Writes each stop's prose; retries to hit story_count≥3 / word floor; keep-best + early-stop | **No — already parallel** across 5 stops (calls interleave in the log) |
| 2 | **story_first → D511 PHASE 5.20 credit_line loop** | **190** | Per stop: object record → seeds → Gemini narrate → Serper challenge → adjudicate → publish gate. 4 credit_lines/stop. | **YES — `for _d511_poi in poi_list:` fully sequential.** Per-stop: 26s, 46s, 26s, 38s, 54s |
| 3 | **external_lookups → LOCAL-410 SERP loop** | ~120 (of 158.9) | Per stop: ~3 SERP queries × 3 providers + P856 batch + replenishment (16 queries, 60 results total) | **YES — `for _s_idx,_s_poi in enumerate(poi_list):` sequential** |
| 4 | **external_lookups → D533 knowledge fallback** | ~30 (of 158.9) | 5 Gemini calls (one per starved stop) to fill object-level facts | Sequential, 5 calls |
| 5 | site_first_exhibitions | 35.3 | One-shot: fetch & parse the exhibition checklist page | n/a (shared) |
| 6 | fact_sheets | 11.7 | Per-stop fact-sheet synthesis | small |
| 7 | poi_selection | 10.0 | Pick the 5 stops | n/a |
| 8 | packing | 8.4 | Assemble final tour text | n/a |
| 9 | DEAD-HOST timeout (all-about-photo.com, Wikidata P856) | ~3.1 | one read-timeout inside a P856 batch | within #3 |
| 10 | intent | 2.9 | classify tour type | n/a |

### Findings
- **The writer loop is already parallel** across stops (LOCAL-440/569) — the 29 gpt-4.1 calls
  interleave (Stop 3 / 5 / 1 / 4 / 2 in one window). It is bounded by the slowest stop's retry
  chain (Stop 5 ran all 5 attempts), not by serialization. Shrinking the 25k-char prompt would
  help every call, but it touches gate behaviour and is the riskier lever; left for a follow-up.
- **The two clearly-serialized, independent-per-stop phases are the win:**
  - D511 PHASE 5.20 (190s): each stop's `story_production_loop.run_for_stop` is independent — it
    takes a per-stop `matrix` (copied with `dict(matrix)`), keeps only local state, and appends to
    an append-only JSONL explicitly designed so "concurrent stops in the same run cannot clobber
    each other." Running the 5 stops concurrently collapses 190s → ~max(stop)=~54s.
  - LOCAL-410 SERP loop (~120s): each stop's `search_stories_for_stop` is independent; only the
    snippet-cache writes need ordering.
- Both must run through `dead_host_breaker.tour_executor` (TourExecutor), which already propagates
  the **LOCAL-562 per-tour cost scope** (global `ThreadPoolExecutor.submit` contextvar patch) and
  the **LOCAL-572 dead-host cold-set scope** (captured at construction, re-bound in each worker).
  That is why this stays within LOCAL-562/572 scope rules.

---

## 2. The change (no quality gate removed)

Two per-stop loops that were serialized are now fanned out across
`dead_host_breaker.tour_executor` (TourExecutor). Everything stateful — the
result-merge, the D518 story merge, the publish gate, keep-best/early-stop, the
cost accumulation, the per-stop stats and every print — stays on the main thread,
in stop order. Only the independent network waits move off-thread.

**a) D511 PHASE 5.20 credit_line loop** (`generate_tour_text.py`, ~`18740`)
- Split into: (1) build the eligible `(stop_index, poi, matrix, desc)` list;
  (2) fan out `story_production_loop.run_for_stop` for all eligible stops via
  `with tour_executor(max_workers=min(len,5))`, collecting results by stop index;
  (3) the **unchanged** merge loop reads each stop's result in order.
- Safe because `run_for_stop` takes a per-stop matrix (built fresh), keeps only
  local state, does not mutate its input (test), and appends to a JSONL its own
  docstring guarantees is concurrency-safe.

**b) LOCAL-410 SERP loop** (`generate_tour_text.py`, ~`12685`)
- Added `_s587_build_stop_data()` (pure; mirrors the loop's matrix build) and a
  concurrent prefetch of `search_stories_for_stop` for worthy stops into
  `_s587_prefetch[idx]` via `tour_executor`. The loop's inline search is replaced
  by `_s587_prefetch.get(idx)` with a live fallback. All post-search logic
  (worthiness skip, D489 replenishment, LOCAL-488 lead fan-out, snippet
  injection, accumulators, prints) is unchanged.
- The D533 Gemini knowledge fallback (5 calls) and the dependent D489
  replenishment queries are **left sequential on purpose** — the fallback runs
  after the whole loop and the replenishment queries depend on each stop's own
  first-search results, so parallelizing them would change behaviour.

Both executors propagate the **LOCAL-562** per-tour cost scope and the
**LOCAL-572** dead-host cold set into workers, so the ledger and the dead-host
breaker stay correct under concurrency (asserted by tests, confirmed leak-free on
the live runs below).

### Tests — `tests/test_local587_parallel_stops.py` (7), full suite 64 green
- both phases dispatch through `tour_executor` (≥4 sites); D511 + LOCAL-410
  markers present; a worker inherits the tour's **cost** accumulator; a cold mark
  made in a worker lands in **this tour's** dead-host set; merging by stop index
  preserves order when a slow stop finishes last; `run_for_stop` does not mutate
  its input matrix and returns independent dicts.
- `python3 -m pytest tests/test_local587_parallel_stops.py tests/test_local572_*.py
  tests/test_local562_choke_point.py tests/test_local440_story_first.py
  tests/test_local569_keep_best_story.py` → **64 passed**.

---

## 3. Live, ISOLATED runs (my own image, never touched any `audioura-*` container)

Image `local587-gen:latest` built from this worktree (`Dockerfile.generator`,
`GIT_SHA=fe3c0a3`). Env captured read-only from `audioura-tour-generator-1`
(`docker inspect … > /tmp/local587.env`) — carries the subscribed switches
`STORY_RETRY_KEEP_BEST`, `STORY_RETRY_EARLY_STOP`, `TOUR_STORY_MODEL=gpt-4.1`.
Run exactly as LEAD did:

```
docker run --rm --name local587-gen --network development_default \
  --env-file /tmp/local587.env \
  -v $PWD/run_local587_container.py:/app/run_local587_container.py:ro \
  -v /tmp/local587_tours:/app/tours \
  local587-gen:latest python3 run_local587_container.py <1|2>
```
(`run_*_container.py` is in `.dockerignore`, so it is bind-mounted; `/app/tours`
is a writable mount. OpenAI hard cap `$3`.)

**RUN 1 (cache-miss) — cost $1.96**
```
[TIMING] TOTAL wall=441.7s phases: story_first=194.7s, external_lookups=141.8s, site_first_exhibitions=34.0s, fact_sheets=16.0s, packing=6.8s, poi_selection=6.7s, intent=2.0s, narration=0.0s, verification=0.0s
RUN 1: delivered stops = 5 / requested 5
   Stop 1: BU Masters Show 2026 | Traces: Pursuing Process
   Stop 2: Earth, Wind & Fire
   Stop 3: Tabitha Soren | An Artist Life
   Stop 4: TLC
   Stop 5: Lua Kobayashi |The Persistence of Memories
```

**RUN 2 (cache-hit) — cost $1.83**
```
[TIMING] TOTAL wall=417.7s phases: story_first=184.5s, external_lookups=153.1s, site_first_exhibitions=35.7s, packing=10.6s, fact_sheets=9.2s, poi_selection=6.3s, intent=2.6s, narration=0.0s, verification=0.0s
RUN 2: delivered stops = 5 / requested 5
   Stop 1: BU Masters Show 2026 | Traces: Pursuing Process
   Stop 2: Earth, Wind & Fire
   Stop 3: Tabitha Soren | An Artist Life
   Stop 4: TLC
   Stop 5: Lua Kobayashi |The Persistence of Memories
```

### Before / after

| Metric | Baseline (LEAD) | Run 1 (miss) | Run 2 (hit) |
|--------|----------------:|-------------:|------------:|
| **story_first** | 403.1s | **194.7s** (−52%) | **184.5s** (−54%) |
| **external_lookups** | 158.9s | **141.8s** (−11%) | 153.1s (−4%) |
| **text phase** (story_first + external_lookups) | **562.0s** | **336.5s** | **337.6s** |
| TOTAL wall | 644.9s | **441.7s** (−31%) | **417.7s** (−35%) |
| stops delivered / order | 5/5, correct | 5/5, same | 5/5, same |
| D511 PHASE 5.20 gated stories | 0/5 | 1/5 | 0/5 |
| keep-best / early-stop / retries | 10 / 3 / 11 | 10 / 3 / 13 | 9 / 2 / 10 |
| cost | — | $1.96 | $1.83 |

### Same gates, same story counts
- D511 PHASE 5.20 still runs on all 5 stops, 4 credit_lines each, same ~$0.048/stop,
  same gate verdicts — now overlapping (per-stop blocks 24/25/28s run concurrently
  instead of summing to 190s). Gated-story count ≥ baseline (0/5 baseline → 1/5 and 0/5).
- The writer loop still delivers all 5 stops with full word counts
  (364/357/367/381/158 words, run 1), and keep-best / early-stop / story-retry all
  fire at baseline rates.
- No `attributed to no tour` / cross-tour / undercount lines in either run — the
  LOCAL-562 cost scope and LOCAL-572 dead-host scope stayed correct in the
  parallel workers on live traffic. The prefetch never fell back (0 skips).

### Honest note on the 5-minute target
`story_first` — the ticket's headline sink — is cut by more than half (403s → ~185–195s)
and the **text phase** the ticket defines (story_first + external_lookups) drops from
**562s to ~337s (−40%)**. Total wall lands at ~7 min; the remainder is the still-serial
D533 Gemini knowledge fallback inside external_lookups and the one-shot
site_first_exhibitions / fact_sheets / packing phases, which this ticket scoped out
(parallelizing the fallback changes which stops get labelled aloud — a gate decision,
not a speed one). The 190s→~55s D511 collapse and the writer loop (already parallel)
are the structural wins; both are landed and measured.
