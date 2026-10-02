# STORY_FIRST_PROFILE.md — LOCAL-3498

**Where the `story_first` phase actually spends its time, measured on real tours.**

Agent: Mac Mini Kiro · Branch: `LOCAL-3498-story-first-profile` · Base: `storied` (e1341e6)
Do **not** optimise anything from this document. It is a measurement.

---

## TL;DR

- The single biggest opportunity is **PHASE 5.17 post-gate retry (`LOCAL-474`)** —
  **35.8–66.7 s, mean ≈ 50.7 s**, the largest sub-step in every run. It re-runs the
  full per-stop description writer **serially, one stop at a time**, and each of those
  regenerations internally retries several times (word-floor + positive-gate loops).
  It is embarrassingly parallel across stops and is run serially. **Estimated saving
  from running its per-stop regenerations concurrently: ≈ 35–50 s off a ~165 s phase**
  (see §5 for the arithmetic and its caveat).
- The **second** biggest is **PHASE 5.152 stop-specificity gate (`LOCAL-472`)** —
  **32.0–45.2 s, mean ≈ 39.9 s** — a per-stop LLM gate that also runs serially.
- A crucial framing correction: **the `story_first` phase name is misleading.** The
  LOCAL-440 "story-first pipeline" and the D474 story-pass are **museum-gated and did
  not run at all** for a church or an airport. What the phase timer actually wraps is
  **the per-stop description writer plus ~20 serial post-description gates.** That is
  where the 110–150 s lives.

---

## What was run

Required env (D261) for every run:
`DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours STORIED_MODE=true`
plus `STORY_FIRST_PROFILE=1` to switch on the sub-phase instrumentation added here.

`python3 preflight.py` first: **OpenAI OK, Gemini OK, Serper OK** — no paid service down.

Three tours, 4 stops each, `tour_type=''` (category inferred, the production path):

| # | Location | Inferred category | Total wall | `story_first` | Log |
|---|---|---|---|---|---|
| 1 | Our Lady Help of Christians Catholic Church, Newton MA | `walking` | 355.5 s | **169.5 s** | `L3498_BATCH_20260923_1222.log` |
| 2 | Boston Logan International Airport, Boston MA | `facility` | 320.3 s | **193.9 s** | same |
| 3 | Our Lady Help of Christians Catholic Church, Newton MA | `walking` | 320.2 s | **132.7 s** | same |

`story_first` is the largest or second-largest phase in all three (it ties/leads with
`poi_selection`). Confirming the ticket's premise: it is roughly half the tour.

> Note on category: neither location is `museum`, so the museum-gated
> `story_first_pipeline_batch` (LOCAL-440/445) and the D474 story pass **never
> executed**. The phase time below is entirely the description writer + the gate chain,
> which run for **all** tour types.

---

## How it was measured

`phase_timer.py` reports one number for the whole `story_first` phase. That phase spans
~5,400 lines of `generate_tour_text.py` (from `_phase_timer.start('story_first')` to
`_phase_timer.start('packing')`) and contains far more than "story-first".

A new module, **`story_first_profile.py`**, adds nested instrumentation that mirrors the
top-level `[TIMING]` line format:

```
  [STORY_FIRST] step=<name> elapsed=<s>s cumulative=<s>s
```

It measures two axes:
1. **Serial sub-steps** — each post-description gate wrapped with `sub_start`/`sub_end`.
   These run one after another on the orchestrating thread, so wall time == cost.
2. **Per-stop work** inside `_generate_description` (the description writer), recorded
   thread-safely by stop index because that function runs in a `ThreadPoolExecutor`.
   The report gives each stop's own wall time and the observed parallel span.

It is **gated behind `STORY_FIRST_PROFILE=1` and is a complete no-op otherwise** — a
normal run is byte-for-byte unchanged. Measured, not guessed.

---

## The breakdown (serial sub-steps)

Every step that ever exceeded 1 s, in seconds. `~0` means it ran but cost < 0.1 s.

| Sub-step (source) | church | airport | church2 | mean |
|---|---:|---:|---:|---:|
| **`postgate_retry_5_17`** (PHASE 5.17, LOCAL-474) | 49.6 | 66.7 | 35.8 | **50.7** |
| **`specificity_5_152`** (PHASE 5.152, LOCAL-472) | 45.2 | 32.0 | 42.5 | **39.9** |
| `unglossed_ref_5_157` (PHASE 5.157, LOCAL-269) | 24.6 | 12.8 | 19.8 | 19.1 |
| `description_generation` (parallel writer loop) | 19.3 | 22.5 | 9.3 | 17.0 |
| `style_validation_5_1` (PHASE 5.1, LOCAL-192) | 16.6 | 18.2 | 16.0 | 16.9 |
| `obligation_audit_5_20` (PHASE 5.20, LOCAL-444) | 5.1 | 6.0 | 0.0 | 3.7 |
| all other ~22 gates (R1–R10, entity/role/org/form/numeric/temporal, dangling, contradicted, venue-scope, audio-native, anti-preaching, story-valuation) | ~0.3 | ~0.3 | ~0.1 | ~0.2 |
| **instrumented sum** | 160.7 | 158.5 | 123.5 | 147.6 |
| **unattributed** (mostly the `LOCAL-439` story-unit gate) | 8.8 | 35.4 | 9.2 | 17.8 |
| **`story_first` phase wall** | **169.5** | **193.9** | **132.7** | **165.4** |

**Unattributed time** is the `LOCAL-439` STORY GATE — a per-stop gpt-4o-mini
classification that runs between the description writer and the first instrumented gate.
It is not wrapped by a sub-timer, so it shows up as the phase-wall minus the sum. On the
airport it was heavier (35 s: more candidates, 2 stops failing classification and
re-scored); on the churches it was ~9 s. It is a genuine, if secondary, cost centre and
would be the next thing to instrument.

---

## §4 — which steps are sequential-but-independent (parallelisation candidates)

These run **serially on the orchestrating thread** but operate per-stop with **no
cross-stop data dependency** — the same shape the causal chain had before it was
parallelised:

1. **`postgate_retry_5_17` — mean 50.7 s. THE opportunity.**
   For each eligible stop it re-invokes `_generate_description` (the full writer, with
   its own internal word-floor/positive-gate retry loop) and re-runs the gate chain on
   the result. In the logs the retries appear strictly one after another
   (`Generating description for Stop 1 … Stop 2 … Stop 3 … Stop 4`). On the airport all
   4 stops were retried in series, several LLM attempts each → 66.7 s. Each stop's retry
   is independent of the others (the only cross-stop input is the "already told" ban
   list, which is read-only at this point). **Independent, serial, and by far the
   heaviest — this is the causal-chain-style win.**

2. **`specificity_5_152` — mean 39.9 s.** Per-stop LLM gate (LOCAL-472) that scores each
   paragraph for transferability/grounding. Loops stops serially; no stop depends on
   another. Second-largest and independent.

3. **`unglossed_ref_5_157` — mean 19.1 s.** Per-stop triage→gloss→compose LLM passes
   (LOCAL-269). Runs per stop, serial; independent across stops.

4. **`style_validation_5_1` — mean 16.9 s.** Per-paragraph style retry (LOCAL-192).
   Already loops paragraphs across all stops; independent per paragraph, run serially.

5. **`LOCAL-439` story gate (unattributed, ~9–35 s).** Per-stop classification; each
   stop independent.

`obligation_audit_5_20` (LOCAL-444) was **disabled** in these runs
(`L444_OBLIGATION_AUDIT=false`); the 5–6 s recorded is the D512 verb-discovery web fetch
that runs in the same block, not the audit itself.

The remaining ~22 gates are cheap (< 0.1 s each) regex/deletion passes — **not worth
parallelising**; the overhead would exceed the work.

## which steps are per-stop, and whether they already run in parallel

- **`description_generation` (the writer) — ALREADY PARALLEL and working.**
  It uses `ThreadPoolExecutor(max_workers=min(len(poi_list), 5))`. The instrument proves
  the parallelism is real: per-stop wall times sum to far more than the observed span.

  | run | Σ per-stop wall | observed span | slowest stop |
  |---|---:|---:|---:|
  | church | 42.7 s | **19.3 s** | 19.3 s |
  | airport | 64.9 s | **22.5 s** | 22.5 s |
  | church2 | 28.4 s | **9.3 s** | 9.3 s |

  In every case the span ≈ the slowest single stop, i.e. the pool is saturating and the
  phase already pays only for the worst stop, not the sum. **No opportunity here.**

- **The heavy gates above (5.17, 5.152, 5.157, 5.1, 439) are per-stop but run SERIALLY.**
  That is the asymmetry: the *writer* was parallelised, but the *retry that re-runs the
  writer* and the *gates* were not. The retry is the most expensive per-stop work in the
  phase and it runs with a pool size of one.

---

## §5 — the single biggest opportunity and the estimated saving

**PHASE 5.17 post-gate retry (`LOCAL-474`), mean ≈ 50.7 s.**

It is per-stop, cross-stop-independent, and serial — the exact profile of `poi_selection`
before it was parallelised (which fell 354 s → 54 s). Each stop's retry both calls the
description LLM (often several times) and re-gates the result; those are independent
across stops.

**Estimate.** Treat 5.17 like the writer it wraps: if its per-stop regenerations ran in a
pool the way `description_generation` already does, its cost would collapse from the
**sum** of per-stop retries toward the **slowest single** retry. The writer data above
shows that collapse is real (Σ 42.7→19.3, 64.9→22.5, 28.4→9.3 — roughly a **2.3–3×**
reduction on 4 stops). Applying the same factor to 5.17:

- church: 49.6 s → ~17–21 s (**save ~30 s**)
- airport: 66.7 s → ~22–29 s (**save ~40 s**)
- church2: 35.8 s → ~12–16 s (**save ~20 s**)

→ **roughly 35–50 s off a ~165 s phase, ~20–25 % of `story_first`, ~10–15 % of the whole
tour.** Doing the same to `specificity_5_152` would add a similar-order second win.

**Caveat, stated plainly (this is a measurement, not a plan):** 5.17 is not a pure
map. It shares two pieces of state — the D534 "already told" ban list and the
D498 top-value allowance — that are consumed as it walks the stops. Parallelising it is
therefore not free the way the writer was; the shared state would have to be resolved up
front or the pass restructured. The number above is the *ceiling* the parallel writer
demonstrates is achievable for independent per-stop LLM work, not a promise that 5.17
reaches it without care. That design work is out of scope for LOCAL-3498 by instruction.

---

## Reproducing

```bash
git checkout LOCAL-3498-story-first-profile     # base storied @ e1341e6
python3 preflight.py                            # must print READY
python3 run_local3498_story_first_profile.py    # writes L3498_BATCH_<stamp>.log
grep '\[STORY_FIRST\]' L3498_BATCH_*.log         # the breakdown
```

Instrumentation lives in `story_first_profile.py` and is wired into
`generate_tour_text.py` at the `story_first` phase boundary; it is inert unless
`STORY_FIRST_PROFILE=1`.
