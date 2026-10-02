# STORY_FIRST_PROFILE.md

**Task:** LOCAL-518 — profile where the `story_first` phase spends its 110–150s.
**Branch:** LOCAL-518-story-first-profile
**Base:** storied = **e1341e6** (verified: `git merge-base --is-ancestor e1341e6 HEAD` exits 0)
**Agent:** Mac Mini Kiro
**Env (D261):** `DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours STORIED_MODE=true` + `L440_STORY_FIRST=true GENERATION_TIER=plus`
**Preflight (on e1341e6):** OpenAI OK (4999/5000), Gemini OK, Serper OK (499/500) → READY. Batch was safe to run.

> Re-measured on the correct base. A prior pass measured this on the stale tree
> (7a97e72, 7 commits behind current storied). That matters: on e1341e6 the museum
> phase profile is materially different (external_lookups and packing are now large,
> see below), which is exactly the D358 failure mode — stale-tree numbers describe old
> code. All numbers here come from live runs on e1341e6.

---

## Headline: the premise is wrong. `story_first` is NOT half the tour.

The `[TIMING] phase=story_first` line does not measure the story-first pipeline.
It measures **Phase 5 per-stop narration**, mislabeled by a phase-timer boundary bug.
I instrumented the story-first pipeline's own internal steps (the thing the task asked
me to profile) and measured it directly on three live runs on e1341e6:

| Run | Category | `[TIMING] phase=story_first` | **story_first pipeline TRUE wall** | narration label | Total wall |
|-----|----------|------------------------------|------------------------------------|-----------------|-----------|
| Our Lady Help of Christians Catholic Church, Newton MA | walking | **123.1s** | **0.0s — pipeline never ran** | 0.0s | 272.8s |
| Boston Logan International Airport, Boston MA | facility/walking | **116.4s** | **0.0s — pipeline never ran** | 0.0s | 193.2s |
| Museum of Fine Arts, Boston MA | museum | **489.3s** | **8.94s** (`[SF-AGG] wall`) | 0.1s | 1328.7s |

Read the church and airport rows carefully. The label says `story_first=123.1s` /
`116.4s` — dead in the "110–150s" band the task cites — yet the story-first pipeline
**did not execute at all** (zero `[SF-STEP]` lines emitted, zero cost, zero stories).
That 123.1s / 116.4s is **100% Phase 5 narration** accumulated under the wrong label.

On the museum run, where the pipeline *does* run and every step was measured, its real
wall time is **8.94s** — comfortably inside its own tour-level budget. The 489.3s
attributed to `story_first` is again almost entirely per-stop narration.

**Nobody had profiled `story_first` because the number everyone was looking at was
never `story_first`.**

---

## Why the label is wrong (root cause — verified on e1341e6)

`generate_tour_text.py` uses `PhaseTimer`, whose `start()` auto-ends the previous phase
(`phase_timer.py`). The phase boundaries are declared in this order on the current base:

```
11010   _phase_timer.start('narration')          # PHASE 5 banner prints here
11078   _phase_timer.start('external_lookups')   # immediately ends 'narration'
11730   _phase_timer.start('story_first')        # story-first batch call is at 11792
   …    story_first_pipeline_batch() returns in ~9s (museum) or is skipped (non-museum) …
14531   ThreadPoolExecutor(max_workers=…)  ← the REAL Phase 5 narration loop runs HERE
17115   _phase_timer.start('packing')            # ends 'story_first'
```

The `narration` label is opened at line 11010 and closed ~68 lines later by the
`external_lookups` start — it only ever wraps some framing/beat setup, so it clocks
**~0.0–0.1s**. The actual per-stop narration ThreadPool loop lives at **line 14531**,
which is *inside* the `story_first` span (11730 → 17115). Every second the narration
loop spends is therefore booked to `story_first`.

This is consistent across all three runs: `narration ≈ 0s` while `story_first` ≈ (real
per-stop narration time). It is a **phase-attribution bug, not a story-first performance
problem.**

---

## The story_first pipeline's real internal breakdown (measured on e1341e6, MFA)

Instrumentation in `story_first.py`: each internal step of `story_first_pipeline()`
prints `[SF-STEP] … step=<name> elapsed=<s>`, each stop prints a `[SF-BREAKDOWN]`, and
`story_first_pipeline_batch()` prints `[SF-AGG]` mean/max across stops.

| Step | What it does | Network/LLM? | Per-stop | Parallel across stops? |
|------|--------------|--------------|----------|------------------------|
| `1_extract_anchor_facts` | regex over stop_data + fact sheet | no | yes | yes |
| `2_seek_stories` | SERP story-seeking queries | Serper | yes | yes |
| `2b_fullpage_fetch` | fetch tier1/2 pages | HTTP | yes | yes |
| `2d_build_candidates` | extract story units + assemble corpus | no | yes | yes |
| `3_prefilter` | zero-cost structural filter | no | yes | yes |
| `4_classify_verify` | gpt-4o-mini classify + verify | LLM | yes | yes |
| `5_size_adapt` | summarise/expand (maybe 1 SERP + 1 LLM) | sometimes | yes | yes |

**Measured `[SF-AGG]` (MFA, 4 stops, batch wall = 8.94s):**

```
MEAN per-stop step:  4_classify_verify=3.53s, 2_seek_stories=1.36s,
                     5_size_adapt=0.60s, 2b_fullpage_fetch=0.22s,
                     2d_build_candidates=0.00s, 3_prefilter=0.00s,
                     1_extract_anchor_facts=0.00s
MAX  per-stop step:  4_classify_verify=5.43s, 5_size_adapt=2.40s,
 (critical-path)     2_seek_stories=1.83s, 2b_fullpage_fetch=0.71s
```

Per-stop `[SF-BREAKDOWN]` totals: 2.84s, 4.72s, 6.38s, 8.94s.

### Sequential-but-independent steps (the causal-chain treatment candidates)
Within a single stop the steps run **sequentially**: seek → fetch → build → prefilter →
classify/verify → size-adapt. They are **not** independent, though: `2b_fullpage_fetch`
needs URLs from `2_seek_stories`; `4_classify_verify` needs candidates from
`2d_build_candidates`. This is a genuine data-dependency chain, so it is **not** a free
parallelisation win the way the causal chain was. There is no sequential-but-independent
pair here worth restructuring — the dominant step (`4_classify_verify`, 3.5s mean) has
nothing it could run beside without its input.

### Per-stop steps and their parallelism status
**Every** step above is per-stop, and they **already run in parallel across stops** via
`story_first_pipeline_batch()` (LOCAL-445). Proof from this run: the per-stop
`[SF-BREAKDOWN]` totals sum to **2.84 + 4.72 + 6.38 + 8.94 = 22.88s**, but the batch
wall (`[SF-AGG] wall`) is **8.94s** — the stops overlapped (22.88s of work in 8.94s of
wall). **Across-stop parallelism is on and working. LOCAL-445 already took that win.**

---

## Where the tour's wall time actually goes (e1341e6, museum run)

Because I re-measured on the correct base, here is the honest current phase profile for
the museum tour (the only one where the full pipeline runs). It differs from the stale
tree — external_lookups and packing are now large — which is the whole reason re-running
on e1341e6 mattered:

```
[TIMING] TOTAL wall=1328.7s
  story_first     = 489.3s   ← ~99% is mislabeled per-stop narration; pipeline itself 8.94s
  packing         = 396.4s
  external_lookups= 229.4s
  poi_selection   = 164.1s
  fact_sheets     =  47.9s
  intent          =   1.5s
  narration       =   0.1s   ← the mislabel: the real narration is under story_first
  verification    =   0.0s
```

For the two required (non-museum) tours the profile is simpler because story_first is
gated off entirely:

```
Church:  TOTAL 272.8s  = story_first(narration) 123.1s + poi_selection 119.8s
                         + fact_sheets 16.3s + packing 11.6s + intent 1.9s
Airport: TOTAL 193.2s  = story_first(narration) 116.4s + poi_selection 48.4s
                         + fact_sheets 15.7s + packing 10.8s + intent 1.8s
```

---

## Single biggest opportunity + estimated saving

**The biggest opportunity is not in `story_first` at all — it is Phase 5 per-stop
narration, which is what the `story_first` label is actually measuring.**

On the three runs the per-stop narration (booked under `story_first`) is:

- Church: **123.1s** (45% of the 272.8s tour)
- Airport: **116.4s** (60% of the 193.2s tour)
- MFA: **~480s** (489.3s label − 8.94s real pipeline)

Two concrete, independent items (this task measures only — no optimisation performed):

1. **Fix the phase label (near-zero code cost, high trust value).** Move
   `_phase_timer.start('narration')` to wrap the actual generation ThreadPool at line
   14531, and let `story_first` end when `story_first_pipeline_batch()` returns. This
   saves **0s wall** but makes every future `[TIMING]` report honest — it is the exact
   defect that made this task necessary and had a whole team believing story_first was
   half the tour. Without this fix, any future story_first "optimisation" will be
   measured against a number that is really narration and will look like it did nothing.

2. **Attack Phase 5 per-stop narration itself (the real wall-time win).** The loop at
   14531 already uses a `ThreadPoolExecutor`, yet on a 4-stop tour it still costs
   ~120s (church/airport). That means the per-stop critical path — the `gpt-4o`
   narration call with a large prompt, plus post-generation gate/retry passes that
   re-invoke the LLM — is ~30s per stop and is not fully hidden by the pool.
   - **Estimated saving:** cutting the per-stop narration critical path by ~40%
     (smaller prompt / fewer retry round-trips / a cheaper model where quality allows)
     takes a ~120s narration phase to **~72s**, i.e. **~48s off a ~193–273s tour
     (≈18–25%)**. This is an estimate bounded by the measurement above; realising it is
     a separate optimisation task.

**What `story_first` itself would save if optimised: ~0s.** It is 8.94s of a 1328.7s
museum tour and 0s of the church/airport tours. Optimising the story-first pipeline is
not worth doing; the label is the bug.

---

## Method / reproducibility

- Base gate: `git merge-base --is-ancestor e1341e6 HEAD` exits 0 (branch rebased onto
  current storied e1341e6 before measuring).
- Instrumentation: `story_first.py` — per-step `_mark()` timers in
  `story_first_pipeline()` (`[SF-STEP]`, `[SF-BREAKDOWN]`); cross-stop aggregation
  (`[SF-AGG]`) in `story_first_pipeline_batch()`. Negligible overhead, left on.
- Harness: `run_local518_profile.py "<location>" <stops> [tour_type]` — sets D261 env,
  forces `L440_STORY_FIRST=true GENERATION_TIER=plus`, tees stdout, extracts
  `[SF-*]`/`[TIMING]` lines, writes a raw `LOCAL518_*.log`.
- Raw logs committed (all from e1341e6 runs):
  `LOCAL518_our_lady_help_of_christians_catholic_chu.log`,
  `LOCAL518_boston_logan_international_airport_bosto.log`,
  `LOCAL518_museum_of_fine_arts_boston_ma.log`.

## Note on the requested venues
The task named a **church** and an **airport**. Measured fact: the church classifies as
`walking` and the airport as `facility`/`walking`; `story_first` is gated to
`tour_category == 'museum'`, so it **never runs for either** (zero `[SF-STEP]` lines).
They were still run (as required) and are the cleanest proof of the mislabel: 123.1s /
116.4s under the `story_first` label with the pipeline provably idle. One MFA museum run
supplies the real internal-step breakdown.

## No DB changes, no optimisation performed
Instrumentation only. No schema changes, no writes, no behaviour change to generation.
