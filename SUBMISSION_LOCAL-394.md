# SUBMISSION_LOCAL-394.md

## Problem

LOCAL-393's 120-word floor retry consumed the retry budget that the beat retry also
needs. When the Lézard stop exhausted its beat retries and had only 100 words, the
word floor retry had already consumed earlier attempts, pushing subsequent LLM calls
into failure territory. The generation function returned `GENERATION_FAILED`, and the
post-assembly gate (LOCAL-292) removed the entire stop block — deleting the richest
stop carrying Broder, Mourlot, Fridman and Miró.

A correctness mechanism that removes correct content has inverted its purpose.

## Root Cause

`_generate_description` has a single `_max_retries=2` retry budget shared by:
1. Word floor retry (`< 120` words → `continue`)
2. Beat retry (missing names → `continue`)
3. Period/material binding retry
4. Placeholder retry

When the word floor retry fires first and consumes an attempt, fewer attempts remain
for the beat retry. If a later attempt produces an API error or empty response, the
function returns `GENERATION_FAILED` — despite having a valid 100-word description
from an earlier attempt.

## Fix

**Track the best valid description** produced across all retry attempts. If the retry
loop ends in failure but a valid description was produced earlier, return that
description instead of `GENERATION_FAILED`.

Three changes:

1. **`_best_description` safety net** — before the word floor and beat retry checks,
   every non-placeholder description is compared to the current best; the longest one
   is retained. All four `GENERATION_FAILED` return paths and the safety fallback now
   check `_best_description` first.

2. **Word floor log format** — the "kept" log uses the exact format required by
   acceptance: `[LOCAL-394] stop='<title>' below_floor words=N — kept (never dropped)`.

3. **Post-assembly invariant** — after the empty stop removal gate, a loud invariant
   check verifies `len(poi_list) == _l292_requested_stops`. Any deviation is logged
   as `STOP COUNT INVARIANT VIOLATION`.

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | `_best_description` tracker; safety net on all GENERATION_FAILED paths; post-gen floor log; stop count invariant |
| `test_local394_never_drop_a_stop.py` | Unit tests (6): floor kept not dropped, count invariant, best_description safety net, real generation path |
| `run_local394_acceptance.py` | Live acceptance: MFA (3 stops, Lézard present, beats attributed) + Palais Lascaris control |

## Tests

**Expected red-on-revert count: 4**

Reverting LOCAL-394 (removing `_best_description` and the invariant) breaks:
- `test_stop_below_floor_is_kept_in_poi_list` — the LOCAL-394 floor section disappears
- `test_delivered_count_equals_selected_count` — the invariant check disappears
- `test_best_description_safety_net_in_generation_code` — `_best_description` disappears
- `test_real_generation_path_has_never_drop_invariant` — `[LOCAL-394] stop=` log disappears

All tests verify **logic**, not symbols (D296). At least one exercises the real
generation path (D307).

## Verification

```bash
python3 -m pytest test_local394_never_drop_a_stop.py -v   # 6 pass
python3 -m pytest test_local393_beat_subject_must_be_person.py -v   # 18 pass (no regression)
python3 -m pytest test_local392_beat_stop_assignment.py -v   # 8 pass (no regression)
```

Live acceptance (requires API keys + DB):
```bash
python3 run_local394_acceptance.py
```
