# SUBMISSION_LOCAL-392.md

## Summary

**Beats are now assigned exclusively to the stop whose work they come from.**

LOCAL-391's retry logging exposed that every `BEAT RETRY` was demanding a person
of the wrong stop. The model was *correctly* refusing to comply — it was resisting
false associations. This ticket fixes the assignment logic so retries only ever
chase facts that are true of that stop.

## Root cause

`assign_beats_to_stops` used weak substring matching (person name ∈ work.publisher?)
and round-robin distribution. This caused:

- Reverdy (stop 3's collaborator) demanded of stop 1
- Freud (stop 2's subject) demanded of stop 3  
- Mourlot Frères + Fridman (stop 1's printer/donor) demanded of stop 2

The model refused because the associations were false. Every `never_written` was
actually correct model behavior. Retries were 3/3 on all three stops, tripling
generation cost for demands that could never succeed.

## Fix

### `story_beat_injector.py`

1. **New function: `attribute_beats_to_works(beats, works)`**  
   Tags each beat with `source_work_index` by checking which work's metadata
   (credit_line, publisher, collaborator, artist, title) references that person.
   Beats that match no single work are marked `exhibition_wide=True`.

2. **Rewritten: `assign_beats_to_stops()`**  
   Uses `source_work_index` as the definitive assignment. A beat from work A is
   NEVER assigned to work B's stop. Exhibition-wide beats are distributed without
   being demanded as required content.

3. **Updated: `get_required_beat_names()`**  
   Skips beats marked `exhibition_wide=True` — they supplement without being
   tracked by the retry mechanism.

4. **Updated: `build_story_beat_prompt_block()`**  
   Separates REQUIRED CONTENT (work-specific) from SUPPLEMENTARY PEOPLE
   (exhibition-wide). Only work-specific beats trigger rejection on omission.

### `generate_tour_text.py`

- Calls `attribute_beats_to_works()` immediately after extraction, before
  `assign_beats_to_stops()`. Passes the works list from the exhibition checklist.

## Derivation logging

Each beat's assignment is logged:
```
[LOCAL-392] beat='Boris Fridman' source_work='Le Lézard aux plumes d'or' -> stop 1
[LOCAL-392] beat='Torf' -> exhibition_wide (no single work match)
```

## Retry count (before → after)

- **Before:** ~9 retry lines (3 per stop × 3 stops with wrong demands), all
  ending in `beat_unrecoverable` for correct model behavior.
- **After:** 0 retries for correctly-assigned beats. Any remaining retry is a
  genuine model miss on a fact that IS true of that stop.

## Tests

- `test_local392_beat_stop_assignment.py` — 8 unit tests:
  - `test_attribution_assigns_correct_source_work_index` — attribution correctness
  - `test_beat_never_crosses_works` — **key test: beat from work A never in work B's stop**
  - `test_exhibition_wide_beats_not_required` — gallery patron not demanded
  - `test_attribution_prevents_wrong_stop_demand` — no Reverdy in stop 1, etc.
  - `test_correct_positive_assignments` — right people in right stops
  - `test_prompt_block_only_demands_work_specific_beats` — prompt fidelity
  - `test_fallback_without_attribution` — backwards compatibility
  - `test_venue_tour_unaffected` — Palais Lascaris case unchanged

- `run_local392_acceptance.py` — Real generation path (D307):
  - MFA 8-stop with all acceptance criteria from ticket
  - Palais Lascaris 4-stop D302 control case

## Expected red-on-revert

Reverting `attribute_beats_to_works` or the `source_work_index` handling in
`assign_beats_to_stops` causes `test_beat_never_crosses_works` and
`test_attribution_prevents_wrong_stop_demand` to fail. The tests break on
**logic** (cross-contamination resumes), not on a missing symbol (D296).

## Files changed

- `story_beat_injector.py` — new `attribute_beats_to_works()`, rewritten
  `assign_beats_to_stops()`, updated `get_required_beat_names()` and
  `build_story_beat_prompt_block()`
- `generate_tour_text.py` — 3-line addition: import + call `attribute_beats_to_works`
- `test_local392_beat_stop_assignment.py` — new (8 unit tests)
- `run_local392_acceptance.py` — new (acceptance runner)
- `SUBMISSION_LOCAL-392.md` — this file
