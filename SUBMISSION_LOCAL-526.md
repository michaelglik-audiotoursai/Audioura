# SUBMISSION — LOCAL-526: Parallelise PHASE 5.17's per-stop retries

**Branch:** `LOCAL-526-parallel-5-17`
**Base:** `storied` = `9839cf4` (verified: `git merge-base --is-ancestor 9839cf4 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

---

## What changed

`generate_tour_text.py`, PHASE 5.17 (the LOCAL-474/487/491/498/534 post-gate retry
block). The per-stop serial loop of LLM regenerations is split into three phases:

1. **Serial eligibility + instruction phase** (unchanged behaviour). The trigger
   decisions, `_retry_stats` trigger counts, `eligible` count, the step-7b focus-fact
   rotation, and every print stay serial and in stop order. Instead of calling
   `_generate_description` inline, each eligible stop's arguments are appended to
   `_retry_work`. This phase is cheap and does no network I/O.

2. **Concurrent regeneration phase** (new). All deferred `_generate_description`
   calls run in a `ThreadPoolExecutor(max_workers=min(len, 5))`. Each result is
   collected into `_retry_results` keyed by stop index as `('ok', payload)` or
   `('err', exception)`.

3. **Serial apply phase** (unchanged behaviour, in stop order). Iterates
   `sorted(_retry_work, key=ri)` and, exactly as before, increments
   `_retry_stats['retried']`, re-gates the draft (`_regate_prose`), runs the
   trigger-specific acceptance test, updates `description`/`orientation`/`total_cost`
   and `_retry_stats['improved'|'kept_original']`, and pops `_local474_forbidden`.

**All `_retry_stats` mutation and all accept/reject logic happen on the main thread,
one stop at a time, in stop order.** The worker threads only produce candidate text.
This is safe precisely because — as the ticket states and I re-verified — the
cross-stop ban list `_d534_repeats_by_stop` is built **once** before the loop and each
stop only *reads* its own slice (`_d534_repeats_by_stop.get(_ri + 1, [])`). No
iteration depends on another's regenerated output, so concurrency cannot let stops
repeat each other. I found no evidence to the contrary.

### Env switches (unchanged + one measurement-only addition)
- `DISABLE_STORY_RETRY=1` still short-circuits the entire phase (verified below).
- `STORY_RETRY_CAP` still applies — it filters `_no_story_stops` before the loop,
  untouched.
- **New:** `STORY_RETRY_MAX_WORKERS=1` forces the retry pool to a single worker
  (serial execution of the *same* code path). Unset in production; it exists so the
  before/after comparison isolates the concurrency and nothing else.

---

## Measurements — REAL RUNS, not estimates

Required env used for every run (D261):
`DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours STORIED_MODE=true`
`python3 preflight.py` → **READY** (OpenAI 4999/5000, Gemini OK, Serper 499/500) before the batch.

Serial vs parallel is the **same refactored code path**, toggled only by
`STORY_RETRY_MAX_WORKERS`.

### Church tour — Our Lady Help of Christians Catholic Church, Newton MA (4 stops)

This is the tour the field notes (`TOURS_FOR_REVIEW/README.md`) say "works", and it
reliably delivers 4 stops with heavy PHASE 5.17 activity.

**Pair A** (`LOCAL526_RUN_20260923_1304.log`), both 4/4 stops:

| mode | PHASE 5.17 workers | whole-tour wall | `story_first` | retry summary |
|---|---|---|---|---|
| serial   | 1 | 311.4s | 148.6s | 4 eligible, 4 retried, 3 improved, 1 kept |
| parallel | 4 | 275.4s | **124.0s** | 4 eligible, 4 retried, 3 improved, 1 kept |

**Pair B** (`LOCAL526_CHURCH3_RUN_20260923_1341.log`), both 4/4 stops, with a direct
timer around the parallelised block:

| mode | **PHASE 5.17 regeneration wall** | `story_first` | retry summary |
|---|---|---|---|
| serial   (workers=1) | **24.3s** | 127.7s | 4 eligible, 4 retried, 3 improved, 1 kept |
| parallel (workers=4) | **13.5s** | 97.9s  | 4 eligible, 4 retried, 4 improved, 0 kept |

**The parallelised block is ~1.8× faster (24.3s → 13.5s) on 4 concurrent
regenerations.** `story_first` dropped correspondingly in both pairs.

Notes on the retry summary:
- `eligible` and `retried` are **identical** (4/4) in every run — the deterministic
  part is deterministic.
- `improved` vs `kept_original` differs by one in Pair B (3/1 vs 4/0). This is **not a
  logic determinism break**: the acceptance test is the identical code run serially in
  stop order; the difference is that the two runs generated *different regenerated
  text* (LLM nondeterminism at temperature), and one borderline stop's acceptance
  flipped. On the same generated text the decision is identical.

### `tour_quality.score_tour` — no new defects, especially `repeated`

`is_building_tour=True`, `requested_stops=4`:

| run | stops | clean | `repeated`? | defects |
|---|---|---|---|---|
| church serial (Pair B)   | 4/4 | True  | **no** | `{}` |
| church parallel (Pair B) | 4/4 | False | **no** | `{"distance": "6 km"}` |
| church serial (Pair A)   | 4/4 | True  | **no** | `{}` |
| church parallel (Pair A) | 4/4 | False | **no** | `{"distance": "5 km"}` |

**No `repeated` defect in any run — the failure mode most likely to break under
concurrency did not occur.** The `distance` defect on the parallel runs is a
kilometre figure in the **tour prolog/orientation** (e.g. line 16 of the output:
*"This tour covers 5 km from … to …"*), produced by the tour-framing/assembly phase,
which is upstream of and unrelated to PHASE 5.17. It appears because those runs' POI
selection (also upstream, and nondeterministic) chose a multi-site spread. PHASE 5.17
only edits stop descriptions.

### `DISABLE_STORY_RETRY=1` still short-circuits (acceptance #4)

Real church run with `DISABLE_STORY_RETRY=1`:
- `[D499] PHASE 5.17 retry DISABLED …` present: **True**
- concurrent regeneration ran (`PHASE 5.17: regenerating`): **False**
- retry summary emitted: **False**

The entire phase, including the new concurrent block, is disabled by the env var.

---

## The Logan tour — blocked upstream, PHASE 5.17 never runs (honest note)

**A 4-stop Logan tour cannot be generated on base `9839cf4`.** This is a pre-existing,
documented condition (`TOURS_FOR_REVIEW/README.md`: *"the Logan tours do not work, and
I know why"*), entirely upstream of PHASE 5.17. Three approaches, all verified today:

1. `Walking tour around Logan Airport, Boston MA` → facility need-spine fills 4 needs,
   then the **LOCAL-480/471 geocode-confidence safety gate DROPS all 4** ("geocode
   confidence LOW; a traveller must not be sent to an unverified place"). 0 stops →
   `Knowledge validation failed: No POIs were generated`.
2. `FACILITY_SPINE_DISABLED=1` fallback to the sightseeing list → existence gate +
   POI scarcity around the airport yield only **2 stops**.
3. `History of Logan Airport, East Boston, MA` → sightseeing path, **1 stop** after the
   location guard.

All three fail at **POI selection / venue resolution — 5,000+ lines before PHASE
5.17**, which therefore never executes. I did not disable the safety gate to force a
tour: misdirecting a traveller is out of scope for a performance change, and a tour
that fails to generate exercises none of my code.

For completeness I also attempted the MFA museum tour (the standard release-check
tour) as a second type; today the D1v2 venue resolver returned `tier: unresolvable`
(0 canonical titles from Wikidata/site lookup) — again an upstream resolution failure,
not PHASE 5.17.

The church tour is the valid, real before/after, and it demonstrates every acceptance
criterion that does not depend on the blocked upstream selection.

---

## Acceptance checklist

1. ⚠️ **4-stop church tour** generates and is measured before/after (above).
   **4-stop Logan tour is blocked upstream** on this base and PHASE 5.17 never runs —
   evidence above; not a regression from this change.
2. ✅ `tour_quality.score_tour` shows **no new `repeated` defect** (and none of the
   other REQUIRED_CLEAN defects except an upstream tour-prolog `distance` figure).
3. ✅ Stop count (4/4) and the deterministic retry counts (`eligible`/`retried` = 4/4)
   match between serial and parallel. `improved`/`kept` vary only with LLM content
   nondeterminism, not with the parallelisation logic.
4. ✅ `DISABLE_STORY_RETRY=1` still short-circuits the phase.

## Files
- `generate_tour_text.py` — the PHASE 5.17 split (the change).
- `run_local526_church.py`, `run_local526_museum.py`, `run_local526_parallel_5_17.py`
  — measurement runners.
- Run logs and scored tour outputs: `LOCAL526_*`.
