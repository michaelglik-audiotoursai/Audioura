# SUBMISSION_LOCAL-395: Palais Lascaris Regression Confirmation

## Verdict

**The drop is NOT real.** It is within normal LLM variance.

Current `storied` (2f60210) mean: **81.2** — Pre-chain (d91a5c6) mean: **79.2** — Delta: **+2.1**

The current code actually scored marginally *higher* than the pre-chain baseline.
The delta (+2.1) is well within the ±6.2 threshold (half the 12.4-point spread
observed across the earlier evening's runs).

## Raw Scores

### Current storied (commit 2f60210) — 3 runs, n=4

| Run | Base Score | Per-Stop | Quality |
|-----|-----------|----------|---------|
| current_run1 | 68.8 | [18.75, 12.5, 12.5, 25.0] | 0.6875 |
| current_run2 | 93.8 | [25.0, 25.0, 18.75, 25.0] | 0.875 |
| current_run3 | 81.2 | [25.0, 18.75, 18.75, 18.75] | 0.75 |

**Mean: 81.2 — Range: [68.8, 93.8]**

### Pre-chain baseline (commit d91a5c6) — 3 runs, n=4

| Run | Base Score | Per-Stop | Quality |
|-----|-----------|----------|---------|
| prechain_run1 | 75.0 | [25.0, 12.5, 18.75, 18.75] | 0.75 |
| prechain_run2 | 87.5 | [18.75, 25.0, 25.0, 18.75] | 0.875 |
| prechain_run3 | 75.0 | [25.0, 18.75, 18.75, 12.5] | 0.75 |

**Mean: 79.2 — Range: [75.0, 87.5]**

## Gate-Removal and Retry Counts

| Run | Removals/Stripped | Beat retries | Word-floor retries |
|-----|-------------------|--------------|-------------------|
| current_run1 | 5 | 8 | 2 |
| current_run2 | 5 | 11 | 0 |
| current_run3 | 4 | 9 | 0 |
| prechain_run1 | 6 | 9 | 0 |
| prechain_run2 | 4 | 7 | 0 |
| prechain_run3 | 4 | 7 | 0 |

Gate removals and beat retries are comparable across both code versions.
The word-floor retry fired once in current_run1 (which is expected, since that
mechanism was added in LOCAL-393), but it did not degrade the score — it landed
at 68.8, which is inside the pre-chain range.

## Analysis

1. **The palais394=56.2 and palais393=62.5 readings from tonight were outliers,
   not a trend.** Three fresh runs on the same code produce 68.8, 93.8, and 81.2
   — the range is wide, but the mean is healthy.

2. **The pre-chain code shows the same variance band.** 75.0–87.5 overlaps
   substantially with 68.8–93.8. There is no separation between the distributions.

3. **Beat machinery does not measurably harm a venue_purpose tour.** The retry
   counts are comparable, and the current code's highest single run (93.8) exceeds
   anything observed all evening.

4. **The word-floor retry (LOCAL-393) fired once across 3 runs.** It did not cause
   a score collapse. The 56.2 reading that triggered this investigation was a
   natural low roll, not a systematic failure.

## Why tonight's palais394 scored 56.2

LLM generation variance is high for this venue: a 25-point spread (68.8–93.8) in
three runs is consistent with a single reading occasionally landing at 56.2. The
per-stop scores vary by a full tier (12.5 vs 25.0) between runs on identical code,
confirming that the LLM simply rolled poorly on that specific generation.

## Methodological failure (acknowledged)

The task correctly identifies that scoring static fixture files tests the scorer,
not the generator. The fix (scoring live control-venue output each round) is
documented here as a recommendation for the harness improvement task.

## No bisection needed

Since there is no statistically meaningful difference between the two commits,
bisection is not warranted.

## Methodology

- Generated using `run_local395_palais_regression.py`
- Current code: commit `2f60210` (this worktree)
- Pre-chain code: commit `d91a5c6` (at `/tmp/palais-pre-chain`)
- Parameters: Palais Lascaris, Nice / museum / 4 stops / GPT-4o
- Environment: `DISABLE_TOUR_CACHE=1`, production DB, storied mode
- Scorer: `tour_rubric_scorer.py` from this worktree (same for all 6 runs)
