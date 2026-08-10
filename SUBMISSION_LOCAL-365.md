# SUBMISSION_LOCAL-365.md

## Summary

A closed exhibition now produces a **typed failure** that the orchestrator
understands, instead of leaking apology text into `audio_tours` as a tour.

## Design Reasoning

The tension: a bare `None` (D273 regression) shows "Tour Generation Failed"
with no reason.  But returning text as if it were a tour creates a row, triggers
TTS, and shows in the tour list.

Resolution: use the **same structured-error channel** that already exists for
degradation failures — `_LAST_CLEAN_FAIL_EVIDENCE`.  The service layer already
reads this dict when `tour_text is None`, forwards `error_type` and
`evidence_summary` to the job store, and sets `status="error"`.  The orchestrator
sees `status_data["status"] == "error"` on the text-gen polling loop (line 710)
and raises, entering its own error handler which sets
`ACTIVE_JOBS[job_id]["status"] = "error"`.  The app renders error-status jobs
as a message, not as a stuck spinner.

The user-facing message now includes the exhibition title and closing date
(e.g. `The exhibition "Picasso, Miró, Dalí: Unbound" closed on 2025-03-09.`).

## Per-File Changes

### `generate_tour_text.py`
- **Closed-exhibition branch** (line ~4416): returns `None, None, (None, None)`
  (hard-failure convention) instead of `_closed_msg, output_file, (None, None)`.
- Populates `_LAST_CLEAN_FAIL_EVIDENCE` with:
  - `error_type: "exhibition_closed"`
  - `exhibition_title`, `closing_date`, `venue`, `reason`
- Removes `exhibition_closed: True` from `_LAST_GENERATION_COST` (nothing read it).
- Removes redundant second `global _LAST_CLEAN_FAIL_EVIDENCE` declaration at
  line ~4983 (the one in the exhibition branch covers the function scope).

### `generate_tour_text_service.py`
- The `if tour_text is None:` handler (line ~169) now branches on
  `error_type == "exhibition_closed"` to construct a user-facing message with
  the exhibition title and closing date.  Other error types still get the
  existing "venue could not be verified" message.

### `tests/test_local365_closed_exhibition_signal.py`
- 11 tests across 6 classes.  All import and call the real `generate_tour_text`
  or `generate_tour_async` — no inline re-implementation.
- Mocks: `analyze_tour_intent` (to skip Phase 1 LLM), `resolve_venue` (on
  `venue_resolver` module), `find_exhibition_checklist` (on `exhibition_checklist`
  module).  The branch logic in `generate_tour_text` is exercised unmodified.

## Red / Green Evidence

### RED (production change reverted)

```
$ git stash   # reverts generate_tour_text.py + generate_tour_text_service.py
$ python3 -m pytest tests/test_local365_closed_exhibition_signal.py -v
FAILED TestClosedExhibitionReturnsNone::test_returns_none_tuple_on_closed_exhibition
FAILED TestClosedExhibitionReturnsNone::test_no_output_file_written_on_closed_exhibition
FAILED TestClosedExhibitionEvidence::test_evidence_has_exhibition_closed_type
FAILED TestClosedExhibitionEvidence::test_evidence_contains_exhibition_title
FAILED TestClosedExhibitionEvidence::test_evidence_contains_closing_date
FAILED TestClosedExhibitionEvidence::test_evidence_contains_venue
FAILED TestClosedExhibitionZeroCost::test_generation_cost_is_zero
FAILED TestServiceLayerErrorMessage::test_service_sets_error_status_with_exhibition_info
=================== 8 failed, 3 passed ===================
```

(3 pass: `test_service_sets_exhibition_closed_error_type` only tests service
with pre-populated evidence; `test_open_exhibition_does_not_return_none` and
`test_palais_lascaris_not_affected` verify the negative — these should always pass.)

### GREEN (production change restored)

```
$ git stash pop
$ python3 -m pytest tests/test_local365_closed_exhibition_signal.py -v
=================== 11 passed in 12.33s ===================
```

## Row Count (code-path proof)

The test cannot insert into a real database (no postgres running in CI).
The proof is structural:

1. `generate_tour_text` returns `None` → the service sets `status="error"` and
   **returns** (line 189 of `generate_tour_text_service.py`).
2. The return happens BEFORE cost metering (line 193+), QA gate, file delivery,
   i-con evaluation, or the `status="completed"` update that reports `output_file`.
3. The orchestrator polls `/status/<job_id>` and receives `{"status": "error"}` →
   raises `Exception(...)` at line 711 → enters the `except` handler at line 1297.
4. The except handler sets `ACTIVE_JOBS[job_id]["status"] = "error"` and **returns**.
   `store_audio_tour` is NEVER called (it's at line 1061, inside the try block
   that already exited).

**Before the fix**: `store_audio_tour` was reached because `generate_tour_text`
returned non-None text → the service reported `status="completed"` → the
orchestrator proceeded to TTS + ZIP + store.

**After the fix**: zero `audio_tours` rows for closed exhibitions.  Cost = $0.00.

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| Closed exhibition → message, zero `audio_tours` rows | ✅ (flow-path proof above) |
| Open exhibition unaffected | ✅ `TestOpenExhibitionUnaffected` |
| Unscoped venue tours unchanged | ✅ `TestUnscopedVenueUnchanged::test_palais_lascaris_not_affected` |
| Museum bounds hold (75.0 / 81.2) | ✅ `test_local345_corpus_in_body.py::TestMuseumScoreBounds` + `test_local357_forced_stops.py::TestMuseumBoundsProperty` |
| App renders message, not stuck job | ✅ ACTIVE_JOBS status="error" with error_type="exhibition_closed" |
| No TTS generated (zero cost) | ✅ `TestClosedExhibitionZeroCost` + service returns before cost metering |

## Limitations

- The `venue_name` sanity check (line ~3728) can discard the intent's venue_name
  if the location string doesn't contain overlapping words (e.g. "MFA" vs
  "Museum of Fine Arts").  When this happens, `_exhibition_scope` is never set
  and the request falls through to Phase 3A.  This is pre-existing behaviour
  (LOCAL-362/364 scope detection) and not introduced by this change.
- The test mocks Phase 1 intent analysis — it cannot verify that the real LLM
  correctly classifies a closed-exhibition request as scoped.  This is covered
  by the existing LOCAL-364 integration tests.
