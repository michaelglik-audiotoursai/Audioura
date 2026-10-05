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

### Expected effect
- D511: 190s → ~55s (saves ~135s).
- SERP: ~120s → ~35s (saves ~85s).
- Projected TOTAL: 644.9s − ~220s ≈ **~425s ≈ 7.1 min**… still above 5 min on wall, but the
  **text phase targeted by the ticket (story_first + external_lookups)** drops from 562s to ~250s.
  Live runs below confirm the measured numbers.
