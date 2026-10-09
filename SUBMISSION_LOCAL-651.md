# SUBMISSION — LOCAL-651: profile every phase, then overlap the independent waits (flag FAST_PIPELINE, default OFF)

**Branch:** `LOCAL-651-fast-pipeline`  **Base:** `subscribed` @ `8e12c846` (verified ancestor)
**Agent:** Mac Mini Kiro

> Goal (Michael 2026-10-09): optimize generation time without losing quality. Same calls, only overlapped. **Never** drop a step, shrink a budget, skip a retry, or cache across tours.

---

## Step 1 — Profile first, change nothing (`[TIMING-SUB]`)

### What was added

A thread-safe, **phase-aware** sub-timer in `phase_timer.py` (`SubTimer`). It emits one line per
network/LLM wait:

```
[TIMING-SUB] phase=<p> step=<name> elapsed=<s>
```

and accumulates a `(phase, step) → {total, calls, max}` table printed as a summary at the end of the
run. `PhaseTimer.start()` now also sets a module-global *current phase*, so every step is attributed
to the phase that is running when the call executes — including when `story_first` stops run
concurrently in the across-stop pool (every pool worker shares the `story_first` phase for its
lifetime).

Instrumentation sits at the **source** of each wait (each runs inside the active phase), so coverage
is complete without editing thousands of inline call sites in the 1.5 MB orchestrator:

| Phase | Instrumented waits |
|---|---|
| poi_selection | `resolve_venue`, `fetch_venue_works`, `discover_official_site`, `fetch_osm_venue_facts`, `venue_parts.build_tour_stops`, `venue_preflight.preflight` |
| external_lookups | `search_stories_for_stop`, `fetch_stop_knowledge`, `_serp_search` |
| story_first (per stop/step) | existing `[SF-STEP]` marks fed into the shared table: extract_anchor_facts, seek_stories, fullpage_fetch, build_candidates, prefilter, classify_verify, size_adapt |
| packing | `packing_prolog_llm`, `packing_rank_facts_llm`, `packing_part4_preview_llm`, `packing_stop_editor_llm`, `packing_conclusion_llm` |
| any phase (free) | LLM/search primitives `story_leads._openai`, `gemini_with_sources`, `serper_research` — these catch fact_sheets' paid calls automatically |

Pure profiling: **no logic change, no flag, no `FAST_PIPELINE` yet.** Decorators preserve function
identity (`functools.wraps`) and re-raise on error. Unit test `test_local651_sub_timer.py` (8 tests)
proves phase attribution, thread-safety under 16×50 concurrent records, decorator identity, and the
sorted summary.

### Profile run (own disposable container)

- Container: `local651-gen` (`docker run --rm`, spare port **5121**, image `local651-gen-img` built
  from this branch tree). **Not** `docker compose -p audioura`; no `audioura-*` container touched.
- `The Courtauld Gallery, London` — **3 stops**, `STORIED_MODE`, **cache OFF, pool OFF**,
  **FAST_PIPELINE OFF** (baseline serial pipeline).
- Metered through `paid_api_calls`; **spend = $0.7078** (cap $1.50). `audio_tours` count
  393 → **394** (+1 additive `is_test` row, id **590**). No DELETE.
- Stop titles delivered: *Manet's A Bar at the Folies-Bergère*, *Courtauld Institute*, *Paul Cézanne*.
- Log: `tours/local651_profile/local651_profile.log`.

### `[TIMING]` phases (this run)

```
intent=1.7s  poi_selection=91.1s  fact_sheets=40.4s  external_lookups=78.3s
story_first=193.4s  packing=60.7s  verification=0.0s     TOTAL wall=465.7s
```

Consistent with the LOCAL-649 baseline (`story_first` dominant, then poi_selection, external_lookups,
packing).

### Top waits (`[TIMING-SUB]`, summed across calls)

`total` is summed across all calls of that step (so a step that already runs in a pool shows a total
larger than its wall contribution); `max` is the worst single call ≈ its critical-path cost.

| # | phase | step | total s | calls | max s | serial / parallel today | depends on |
|---|---|---|---:|---:|---:|---|---|
| 1 | story_first | `gemini_with_sources` (per-stop grounded narrate) | 111.83 | 24 | 9.52 | **parallel across stops** (LOCAL-445 pool), **serial within a stop** | needs stop list + anchor facts (per stop) |
| 2 | external_lookups | `serp_search` | 46.13 | 27 | 5.71 | partly parallel (LOCAL-587 prefetch pool=5) + serial inline loop | needs final stop list |
| 3 | story_first | `serp_search` (story-seeking) | 30.17 | 22 | 3.04 | parallel across stops; pooled within a stop | per-stop anchor facts |
| 4 | external_lookups | `search_stories_for_stop` | 21.43 | 3 | 7.63 | **serial per-stop loop** (one call per stop) | needs final stop list |
| 5 | external_lookups | `fetch_stop_knowledge` | 16.75 | 3 | 6.33 | serial per-stop (fallback) | per stop |
| 6 | external_lookups | `gemini_with_sources` | 16.75 | 3 | 6.33 | serial per-stop | per stop |
| 7 | poi_selection (pre-phase) | `venue_preflight` | 14.27 | 1 | 14.27 | **serial, once, up front** (shows `phase=unknown` — runs before poi_selection timer starts) | venue name only |
| 8 | poi_selection | `fetch_osm_venue_facts` | 12.47 | 3 | 5.01 | **serial** (one per stop slot in the deterministic fill) | venue entity |
| 9 | poi_selection | `resolve_venue` (Wikidata) | 10.34 | 4 | 2.74 | **serial** (repeated resolve of the same venue) | venue name |
| 10 | poi_selection (pre-phase) | `gemini_with_sources` | 9.74 | 1 | 9.74 | serial, once | venue name |

Smaller: `packing_stop_editor_llm` 5.56s (per-stop editor, 1 call over all stops), `story_leads_openai`
5.05s/3, `fetch_venue_works` 0.41s/3, and the cross-stop packing passes (rank 2.60s, prolog 1.96s,
conclusion 0.93s, part4 0.70s).

### Where the serial time hides (dependency analysis → Step 2 plan)

1. **poi_selection deterministic fill (~44s of independent waits run one-after-another):**
   `venue_preflight` (14.3s) + `resolve_venue` (10.3s, called **4×** for the *same* venue) +
   `fetch_osm_venue_facts` (12.5s, once per stop) + `fetch_venue_works` (0.4s) + the up-front grounded
   `gemini_with_sources` (9.7s). The preflight, the Wikidata resolve/works, and the OSM facts are
   **independent inputs** that today run strictly in sequence. → **overlap them concurrently.**
2. **external_lookups is serial per stop** (`search_stories_for_stop` ×3, `fetch_stop_knowledge` ×3,
   its `gemini_with_sources` ×3) and runs **after** fact_sheets even though it only needs the final
   stop list. → **fan the per-stop lookups out, and start external_lookups concurrently with
   fact_sheets.**
3. **story_first** already parallelises across stops (LOCAL-445). The dominant wait is the per-stop
   `gemini_with_sources` grounded narrate (max 9.5s) and the story-seeking SERP; the pool size
   (`STORY_FIRST_TOUR_POOL_SIZE=6`) and the per-stop internal fan-out are the levers.
4. **packing** per-stop LLM pass is the stop editor (5.6s); the cross-stop passes (rank, prolog, part4,
   conclusion, D533/D636) must stay sequential and **after** the per-stop work.

---

## Step 2 — Overlap the independent waits (FAST_PIPELINE) — *in progress*

(Design + implementation below; default OFF byte-identical.)
