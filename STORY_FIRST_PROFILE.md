# STORY_FIRST_PROFILE.md

**Task:** LOCAL-518 — profile where the `story_first` phase spends its 110–150s.
**Branch:** LOCAL-518-story-first-profile
**Base:** storied (7a97e72)
**Agent:** Mac Mini Kiro
**Env (D261):** `DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours STORIED_MODE=true` + `L440_STORY_FIRST=true GENERATION_TIER=plus`
**Preflight:** OpenAI OK (4999/5000), Gemini OK, Serper OK — batch was safe to run.

---

## Headline: the premise is wrong. `story_first` is NOT half the tour.

The `[TIMING] phase=story_first` line does not measure the story-first pipeline.
It measures **Phase 5 narration**, mislabeled. I instrumented the story-first
pipeline's own internal steps (the thing the task asked me to profile) and measured
it directly on four live runs:

| Run | Category | `[TIMING] phase=story_first` | **story_first pipeline TRUE wall** | narration label | Total wall |
|-----|----------|------------------------------|------------------------------------|-----------------|-----------|
| Our Lady Help of Christians Church, Newton MA | walking | **129.8s** | **0.0s — pipeline never ran** | 0.0s | 285.3s |
| Boston Logan International Airport, Boston MA | facility | **131.4s** | **0.0s — pipeline never ran** | 0.0s | 218.4s |
| Museum of Fine Arts, Boston MA (run 1) | museum | **433.9s** | **9.8s** | 0.1s | 1250.4s |
| Museum of Fine Arts, Boston MA (run 2) | museum | **559.0s** | **6.2s** | 0.1s | 1291.6s |

Read the church and airport rows carefully. The label says `story_first=129.8s` /
`131.4s` — dead in the "110–150s" band the task cites — yet the story-first pipeline
**did not execute at all** (zero `[SF-STEP]` lines emitted, zero cost, zero stories).
The 129.8s / 131.4s is **100% Phase 5 narration** accumulated under the wrong label.

On the two museum runs, where the pipeline *does* run, its real wall time is
**6.2s and 9.8s** — comfortably inside its own 40s tour-level budget. The 434s / 559s
attributed to `story_first` is again almost entirely narration.

**Nobody had profiled `story_first` because the number everyone was looking at was
never `story_first`.**

---

## Why the label is wrong (root cause)

`generate_tour_text.py` uses `PhaseTimer`, whose `start()` auto-ends the previous
phase (`phase_timer.py`). The phase boundaries are declared in this order:

```
10993   _phase_timer.start('narration')          # PHASE 5 banner prints here
11061   _phase_timer.start('external_lookups')   # immediately ends 'narration'
11713   _phase_timer.start('story_first')        # story-first batch call is here
   …    story_first_pipeline_batch() returns in 6–10s (museum) or is skipped …
14517   ThreadPoolExecutor(...)  ← the REAL Phase 5 narration loop runs HERE
17086   _phase_timer.start('packing')            # ends 'story_first'
```

The `narration` label is opened at line 10993 and closed ~68 lines later by the
`external_lookups` start — it only ever wraps some framing/beat setup, so it clocks
**~0.0–0.1s**. The actual per-stop narration ThreadPool loop lives at **line 14517**,
which is *inside* the `story_first` span (11713 → 17086). Every second the narration
loop spends is therefore booked to `story_first`.

This is consistent across all four runs: `narration ≈ 0s` and `story_first` ≈ (real
narration time). It is a **phase-attribution bug, not a story-first performance
problem.**

---

## The story_first pipeline's real internal breakdown (measured)

Instrumentation added in `story_first.py`: each internal step of
`story_first_pipeline()` prints `[SF-STEP] … step=<name> elapsed=<s>`, each stop
prints a `[SF-BREAKDOWN]`, and `story_first_pipeline_batch()` prints `[SF-AGG]`
mean/max across stops. Steps:

| Step | What it does | Network/LLM? | Per-stop | Parallel across stops? |
|------|--------------|--------------|----------|------------------------|
| `1_extract_anchor_facts` | regex over stop_data + fact sheet | no | yes | yes |
| `2_seek_stories` | SERP story-seeking queries (≤6, pool=5) | Serper | yes | yes |
| `2b_fullpage_fetch` | fetch ≤3 tier1/2 pages (pool=3) | HTTP | yes | yes |
| `2d_build_candidates` | extract story units + assemble corpus | no | yes | yes |
| `3_prefilter` | zero-cost structural filter | no | yes | yes |
| `4_classify_verify` | gpt-4o-mini classify + verify (pool=5) | LLM | yes | yes |
| `5_size_adapt` | summarise/expand (maybe 1 SERP + 1 LLM) | sometimes | yes | yes |

**Measured `[SF-AGG]` (MFA, 4 stops):**

```
Run 1 (batch wall 9.8s):
  MEAN per-stop: 4_classify_verify=2.58s, 2_seek_stories=1.84s,
                 2b_fullpage_fetch=0.90s, 5_size_adapt=0.50s, rest ≈ 0s
  MAX  per-stop: 4_classify_verify=4.00s, 2_seek_stories=3.73s,
                 2b_fullpage_fetch=2.67s, 5_size_adapt=2.01s

Run 2 (batch wall 6.2s):
  MEAN per-stop: 4_classify_verify=2.89s, 2_seek_stories=1.70s,
                 2b_fullpage_fetch=0.79s, rest ≈ 0s
  MAX  per-stop: 4_classify_verify=3.80s, 2_seek_stories=2.63s,
                 2b_fullpage_fetch=1.13s
```

### Sequential-but-independent steps (the causal-chain treatment candidates)
Within a single stop, the steps run **sequentially**: seek → fetch → build →
prefilter → classify/verify → size-adapt. They are *not* independent, though:
`2b_fullpage_fetch` needs URLs from `2_seek_stories`; `4_classify_verify` needs
candidates from `2d_build_candidates`. This is a genuine data dependency chain, so
it is **not** a free parallelisation win the way the causal chain was.

The one arguably-independent pair is `2_seek_stories` (SERP) vs the later
verification corpus assembly, but at 1.7–1.8s mean it is not worth restructuring.

### Per-stop steps and their parallelism status
**Every** step above is per-stop, and they **already run in parallel across stops**
via `story_first_pipeline_batch()` (LOCAL-445): a `ThreadPoolExecutor(max_workers=6)`
runs all stops concurrently under a 40s tour-level budget. The evidence: summing the
per-stop `[SF-BREAKDOWN]` totals (2.9 + 3.0 + 7.6 + 9.8 = 23.3s for run 1) exceeds the
batch wall (9.8s) — proof the stops overlapped. **Across-stop parallelism is on and
working.** There is no serial-loop win left here; LOCAL-445 already took it.

---

## Single biggest opportunity + estimated saving

**The biggest opportunity is not in `story_first` at all — it is Phase 5 narration,
which is what the `story_first` label is actually measuring.** On the four runs it is:

- Church: **129.8s** (46% of the 285.3s tour)
- Airport: **131.4s** (60% of the 218.4s tour)
- MFA r1: **~424s** (434s label − 10s real pipeline); MFA r2: **~553s**

Two concrete, independent wins:

1. **Fix the phase label (near-zero cost, high trust value).** Move
   `_phase_timer.start('narration')` to wrap the actual generation ThreadPool at
   line 14517 (and let `story_first` end when the batch returns). This does not save
   wall time but makes every future timing report honest — the exact defect that made
   this task necessary. **Saving: 0s wall, but it stops the whole team chasing a ghost.**

2. **Attack Phase 5 narration itself (the real wall-time win).** It already uses a
   `ThreadPoolExecutor(max_workers=5)`, but on a 4-stop tour taking 130s+, the
   per-stop narration LLM call (`gpt-4o`, large prompt) is the dominant cost. The
   biggest single lever is the **`gpt-4o` model / prompt size on the per-stop call**,
   plus the post-generation gate/retry passes that re-invoke the LLM.
   - **Estimated saving:** the church/airport tours have 4 stops and ~130s of
     narration ⇒ ~32s of critical-path time per stop even with pool=5 (i.e. retries
     and gates are serialising work). Cutting the per-stop narration critical path by
     ~40% (smaller prompt / fewer retry round-trips / `gpt-4o-mini` where quality
     allows) would take a ~130s narration phase to **~80s**, i.e. **~50s off a
     ~240–285s tour (≈18–20%)**. This estimate is bounded by measurement, not code
     changes — this task does not optimise anything (per the AC).

**What `story_first` itself would save if optimised: ~0s.** It is 6–10s of a
1250s museum tour and 0s of the church/airport tours. Optimising it is not worth doing.

---

## Method / reproducibility

- Instrumentation: `story_first.py` — per-step `_mark()` timers in
  `story_first_pipeline()`; cross-stop aggregation (`[SF-AGG]`) in
  `story_first_pipeline_batch()`. Left on permanently (negligible overhead).
- Harness: `run_local518_profile.py "<location>" <stops> [tour_type]` — sets D261 env,
  forces `L440_STORY_FIRST=true`, tees stdout, extracts `[SF-*]`/`[TIMING]` lines,
  writes a raw `LOCAL518_*.log`.
- Raw logs committed: `LOCAL518_our_lady_help_of_christians_catholic_chu.log`,
  `LOCAL518_boston_logan_international_airport_bosto.log`,
  `LOCAL518_museum_of_fine_arts_boston_ma.log`.
- Existing test suite `test_local445_across_stop_parallel.py`: 17/19 pass; the 2
  failures (`TestDeadHostBreaker` P856 tier3 vs unverified) are **pre-existing on the
  base commit** (verified via `git stash`) and unrelated to this instrumentation.

## Note on the requested venues
The task named a **church** and an **airport**. Measured fact: the church classifies
as `walking` (LOCAL-485 venue-class guard) and the airport as `facility`
(LOCAL-480 facility guard); `story_first` is gated to `tour_category == 'museum'`, so
it **never runs for either**. They were still run (as required) and are the cleanest
proof of the mislabel: 129.8s / 131.4s under the `story_first` label with the pipeline
provably idle. Two MFA museum runs supply the real internal-step breakdown.

## No DB changes, no optimisation performed
Instrumentation only. No schema changes, no writes, no behaviour change to generation.
