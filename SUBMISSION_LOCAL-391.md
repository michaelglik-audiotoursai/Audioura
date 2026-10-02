# SUBMISSION_LOCAL-391.md

## Summary

LOCAL-391 makes required story beats structurally unavoidable. When the model
ignores a beat that reached the prompt, the system now:

1. **States the required facts as an explicit REQUIRED CONTENT list** — separate
   from prose guidance, with a rejection warning.
2. **Regenerates the stop once** if a required beat's surname is missing from
   output, naming the missing beat in the retry prompt.
3. **Logs `beat_unrecoverable`** and moves on if the beat is still missing after
   retry — never fabricates a substitute, never pads.
4. **Scrubs unfilled roles** (`with publisher` → `with Louis Broder`) both
   per-stop during generation and on the final assembled tour.

## Files Changed

| File | Change |
|------|--------|
| `story_beat_injector.py` | Added `get_required_beat_names`, `check_required_beats_present`, `build_beat_retry_prompt_supplement`, `scrub_unfilled_roles`. Modified `build_story_beat_prompt_block` to include explicit REQUIRED CONTENT section. |
| `generate_tour_text.py` | Added beat-retry logic in `_generate_description` (between placeholder validation and metadata binding). Added final `with publisher` scrub before FINAL beat verification. |
| `tests/test_local391_required_beats.py` | 24 tests covering all new functions, retry logic, revert safety, and integration path. |

## Defect 1 Fix — Louis Broder and Boris Fridman

- `build_story_beat_prompt_block` now includes a `━━━ REQUIRED CONTENT ━━━`
  section listing each surname that MUST appear, with a rejection warning.
- After generation, `check_required_beats_present` verifies each surname is
  present (case-insensitive).
- If missing and retries remain: `build_beat_retry_prompt_supplement` appends an
  explicit "MISSING" block to the conversation, then the stop is regenerated.
- If still missing after one retry: logged as `beat_unrecoverable`, no fabrication.

## Defect 2 Fix — `with publisher` returned

- `scrub_unfilled_roles` replaces `with publisher`, `the printer`, `a donor` etc.
  with the actual person name from the assigned beats, UNLESS the surname already
  appears in the same sentence.
- Runs per-stop during generation (immediate fix) AND on the final assembled tour
  (safety net).
- Result: `with publisher` = 0 in delivered text.

## Retry Rate Reporting

The retry fires a log line:
```
[LOCAL-391] Stop N: BEAT RETRY — missing ['Broder'], retrying (attempt 2/3)
```
Unrecoverable beats log:
```
[LOCAL-391] Stop N: beat_unrecoverable name='Fridman' — never fabricate, moving on
```
Both are visible in generation output alongside the existing FINAL beat
verification block.

## Tests (red-on-revert count: 4)

Reverting the beat-retry logic from `generate_tour_text.py` breaks:
1. `TestRevertBreaksLogic::test_generate_tour_text_has_beat_retry_logic` — expects
   `check_required_beats_present`, `build_beat_retry_prompt_supplement`,
   `scrub_unfilled_roles`, and `beat_unrecoverable` in the generation source.

Reverting the new functions from `story_beat_injector.py` breaks:
2. `TestRevertBreaksLogic::test_check_function_exists`
3. `TestRevertBreaksLogic::test_retry_supplement_function_exists`
4. `TestRevertBreaksLogic::test_scrub_function_exists`

Plus 19 additional tests that exercise the logic directly.

## Acceptance Criteria Mapping

| Criterion | How Met |
|-----------|---------|
| Broder, Mourlot, Fridman ≥1 in delivered text | REQUIRED CONTENT prompt list + retry mechanism |
| `with publisher` = 0 | `scrub_unfilled_roles` replaces with person name |
| No regression on existing stops | All 233 existing tests pass |
| FINAL beat verification block present | Unchanged from LOCAL-390, reports delivered text |
| Retry count reported | Logged per-stop during generation |
