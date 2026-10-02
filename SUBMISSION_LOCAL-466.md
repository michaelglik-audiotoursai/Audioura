# SUBMISSION_LOCAL-466.md — More Than One Story Per Stop

## Summary

Implemented multi-story publishing for museum tour stops. When the D511/D523
credit_line loop produces multiple accepted stories from different credit_lines,
the stop can now publish up to `STORY_LOOP_MAX_STORIES` (default 2) instead of
discarding all but the best.

Michael's complaint on stop 3 of TOUR_MFA_UNBOUND_20260824_1557: the loop examined
4 credit_lines, all cleared the floor of 50, and binned three publishable stories.
The stop was short because the system already bought the material and threw it away.

## What was built

### 1. `story_production_loop.run_for_stop` — new `stories` field

The return dict now includes `stories`: a list of every candidate that passed the
gate, sorted best-index-first. Each entry carries `story`, `credit_line`, `index`,
`gate`, `sources`, `counts`, `kind`.

The existing `story` key is **unchanged** — it is still the single best story, so
nothing downstream that reads it breaks.

New constants:
- `STORY_LOOP_MAX_STORIES` (env, default 2)
- `STORY_LOOP_SECOND_MIN` (env, default 55)

### 2. `generate_tour_text.py` PHASE 5.20 — multi-story publishing

The publishing block now iterates through `_d511_res['stories']` applying four
rules in order:

1. **Distinct credit_lines only.** Same seed → same story told twice → skip.
2. **D518 merge as the duplicate guard.** Each additional story is merged against
   the current text (prose + prior stories). If the merge absorbs it (adds < 2
   sentences), it was a duplicate → drop.
3. **Order by index, best first.** Already sorted by the loop.
4. **Second story must score ≥ `STORY_LOOP_SECOND_MIN` (55).** The floor for
   publishing at all is 50; the bar for adding length is higher.

Sentence allowance is per-story (unchanged from `story_publish_gate.allowed_sentences`).
Two stories at 61 and 59 give roughly twice the text of one at 61.

### 3. Reporting

Log line: `[D511] stop N: 2 stories published (61, 59) from credit_lines 'X', 'Y'`

Summary line includes multi-story count:
`3/5 stops got a gated story (1 with multiple stories), ~$0.089, [D518] 4 duplicated
prose sentence(s) replaced`

### 4. Fallback path

If `stories` contains entries but all additional ones are filtered (duplicate or
below SECOND_MIN), the single best story still publishes via the original merge
path. A stop never publishes zero when the best story passed the gate.

## What this does NOT do

- **Does not pad.** If only one candidate passes, publishes one.
- **Does not repeat.** The merge is the guard; if a second story's content is
  absorbed, it was the first story again.
- **Does not raise cost.** Candidates are already bought under D523. This task
  spends no extra model calls. Verified: cost_usd comes from `n_serp` and `n_gem`
  counters, which are unchanged — only the publishing path is different.

## Tests

```
$ python3 tests/test_local466_multi_story.py       # 7 tests, all pass
$ python3 tests/test_story_append_merge.py         # existing, all pass
$ python3 tests/test_d523_story_selection_and_hygiene.py  # existing, all pass
```

Test cases for LOCAL-466:
1. Two distinct stories kept (different credit_lines, both ≥ SECOND_MIN, both add
   material).
2. Duplicate second rejected (merge absorbs it → <2 new sentences).
3. Only one candidate passes → publishes one.
4. `STORY_LOOP_MAX_STORIES=1` reproduces today's behaviour exactly.
5. Same credit_line → rejected.
6. Second below SECOND_MIN → rejected.
7. Contract: `run_for_stop` exposes `MAX_STORIES`, `SECOND_MIN`, `stories` field.

## Acceptance items pending

Items 1–3 require a live tour run (`run_loop_tour.py` with D261's env). The unit
tests cover the logic; the live run proves it works end-to-end with real model
outputs. That run should be executed separately with:

```bash
DISABLE_TOUR_CACHE=1 STORIED_MODE=true python3 run_loop_tour.py \
  "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
```

Cost comparison: the loop's `cost_usd` counter is unchanged — it counts serp calls
and gemini calls, and this task adds zero of either.
