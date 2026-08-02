##### READY FOR REVIEW

# SUBMISSION_LOCAL-127: i_con_avg and i_con_min — No Key Exists (resubmission)

**Task:** LOCAL-127 — Populate tour-level i_con aggregates  
**Branch:** `kiro/local127-icon-aggregate`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-02 (resubmission after bounce)  

---

## Commit

```
git rev-list --count storied..HEAD: 1
Commit: 98d1a80
```

## Bounce Summary

Previous submission populated 41/88 tours using stop-title matching. Tours 21,
27, 28 (same venue, different text, Alpha/Bravo pair) received identical scores
(avg=3.56, min=3.00) — proving the title match measures the *venue*, not the *tour*.

This resubmission investigates the real key, finds none, and reverts.

---

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `tests/test_local127_icon_aggregate.py` | +181 | Evidence test proving no key exists |
| `SUBMISSION_LOCAL-127.md` | this file | Submission artifact |

**Code files UNCHANGED** — the faulty `update_tour_icon_aggregates()` function from
the previous submission is removed (branch reset). No title-matching code remains.
`generate_tour_text_service.py` and `tour_orchestrator_service.py` are at their
`storied` baseline.

---

## Criterion 1: What i_con measures (unchanged from previous submission)

**i_con** = informational-context score. Per-paragraph quality on a 1/3/5 scale:

| Score | Meaning |
|-------|---------|
| 1 | No information — aesthetic wallpaper the visitor detects unaided |
| 3 | Information with little emotional appeal — plaque-level facts |
| 5 | Interesting information — grounded specifics advancing a story |

**Computing code:** `icon_evaluator.py`
- Scale: `_ICON_SYSTEM_PROMPT` (lines 182–199)
- Scoring: GPT-4o-mini with few-shot calibration (lines 218–256)
- Stop score = mean of paragraph scores (line 324)

**Is 1.65 a sensible average?** No — 556/1002 rows are `i_con = 0.00` from
early evaluator runs that failed. Excluding zeros: **446 valid rows, avg = 3.71,
range 2.00–5.00**. The scale discriminates usefully.

---

## Criterion 2: Root cause — UNFINISHED WORK (deeper than first reported)

The columns exist but cannot be populated because **there is no key between
`stop_metrics` and `audio_tours`**. This is not just "a final write-back step
that was never built" — the tables are structurally unlinked.

**Evidence chain:**

1. `stop_metrics.tour_id` is NULL on all 1002 rows.
2. `job_status` table is empty (0 rows) — no job_id ↔ tour mapping there.
3. `audio_tours` has no `job_id` column.
4. `cost_ledger.job_id` overlaps with `stop_metrics.job_id` (62 of 167 jobs)
   but `cost_ledger` has no `tour_id` reference either.
5. **The paragraph text stored in `stop_metrics` does NOT appear in any
   `audio_tours.tour_content`** — the evaluator ran on different LLM generations
   than those stored as final tours.

**Pipeline flow that causes this:**

```
Step 1: generate_tour_text_service.py
  → runs icon_evaluator on generated text
  → writes stop_metrics with job_id
  → the generated text may or may not become the final stored tour
  (if cache hit, or if re-generation happens, a different text is stored)

Step 2: tour_orchestrator_service.py (separate process, later)
  → calls store_audio_tour()
  → inserts into audio_tours
  → has no reference to the text generation job_id
  → stop_metrics.tour_id is never backfilled
```

The critical gap: step 1 doesn't know the tour_id (it doesn't exist yet),
and step 2 doesn't record the job_id that produced the stop_metrics.

**Classification:** UNFINISHED WORK — the FK column was added to the schema
but the pipeline was never wired to populate it.

---

## Criterion 3: Why the values CANNOT be populated today

The title-matching approach fails because:

1. **Title collision.** Tours 21, 27, 28 share identical stop titles (8 stops
   each, all "L'Armure d'Andô Naoyuki", "Statue de Bouddha", etc.). Different
   text, different quality — but title match assigns the same score.

2. **Multi-job ambiguity.** "Abraham et les trois anges" appears in 33 different
   jobs with different i_con values. Which job's score wins is arbitrary.

3. **Text mismatch.** The evaluator evaluated DIFFERENT generated text than what
   ended up in `audio_tours.tour_content`. Tour 27 Stop 2 says "Embrace the
   stillness of this ancient masterpiece…" but stop_metrics says "Stand directly
   in front of the 'Statue de Bouddha'…" — completely different generations.

**Correct state:** Both columns NULL on all 88 tours. A wrong number in a
quality column is worse than empty — ranking will eventually read it.

---

## Criterion 4: The finding (instead of distribution)

Since no values can be correctly populated, there is no tour-level distribution
to report. The per-stop distribution (which IS valid) is:

```
stop_metrics: 1002 rows total
  i_con = 0 (failed evaluations): 556
  i_con > 0 (valid): 446
  Valid mean: 3.71, min: 2.00, max: 5.00
```

This tells us the evaluator works and the scale discriminates. Once the key
problem is solved, tour-level aggregates will produce meaningful rankings.

---

## Reverted values — before/after

```
BEFORE (from previous bounced submission):
  audio_tours: 88 rows
  i_con_avg populated: 41 (WRONG — title-matched)
  i_con_min populated: 41 (WRONG — title-matched)
  Tours 21, 27, 28 all showed: avg=3.56, min=3.00 (COLLISION)

AFTER (this submission):
  audio_tours: 88 rows
  i_con_avg populated: 0 (reverted to NULL)
  i_con_min populated: 0 (reverted to NULL)
```

---

## Proposed fix (follow-up task): wire job_id through the pipeline

```
A. Add text_job_id column to audio_tours
   ALTER TABLE audio_tours ADD COLUMN text_job_id VARCHAR;

B. In tour_orchestrator_service.py store_audio_tour():
   Store the text generation job_id alongside the tour

C. After store:
   UPDATE stop_metrics SET tour_id = <new_tour_id>
   WHERE job_id = <text_job_id>

D. Then compute aggregates:
   UPDATE audio_tours SET
     i_con_avg = (SELECT AVG(i_con) FROM stop_metrics WHERE tour_id = X AND i_con > 0),
     i_con_min = (SELECT MIN(i_con) FROM stop_metrics WHERE tour_id = X AND i_con > 0)
   WHERE id = X

E. Backfill: for future tours, this happens atomically.
   For existing 88 tours — they were generated before the key was wired,
   so their stop_metrics (if any) would need paragraph-text fingerprint
   matching or re-evaluation.
```

---

## Constraints verified

```
audio_tours row count BEFORE: 88
audio_tours row count AFTER:  88
✓ No DELETE, no INSERT — only UPDATE (to NULL)

tours-near/43.7009358/7.2683912?radius=50 = [1, 12, 14, 17, 21, 24, 27, 28, 29]  ✓
```

---

## Limitations

1. **Both aggregate columns remain NULL.** This is the correct state given
   the missing key. Populating them requires a pipeline change (follow-up task).

2. **The 88 existing tours may never get correct aggregates.** Their stop_metrics
   (if they exist) evaluate different text than what was stored. Only re-running
   the evaluator on the stored `tour_content` would produce correct per-tour scores.

3. **Docker build blocked.** Cannot verify that removing the orchestrator wiring
   doesn't break anything at runtime. The removed code was wrapped in try/except
   (non-fatal), and the function it called no longer exists — so the service will
   be fine.
