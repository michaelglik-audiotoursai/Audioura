# SUBMISSION — LOCAL-475: The Edit Screen And Its Caller Must Agree

**Branch:** `LOCAL-475-edit-stop-contract`
**Base:** `storied` @ `bd109fa` (verified `git merge-base --is-ancestor bd109fa HEAD` → exit 0)
**ClickUp:** `wdvrdayced`
**Version:** `2.3.2+22` — left unchanged (matches `BUILD_NUMBERS.md`, row 22 "NEXT, claimed").

## The defect (one cause, two field bugs)

`edit_tour_screen.dart` `_editStop` pushes `EditStopScreen` and expects the pushed
route to return **the updated stop as a `Map<String, dynamic>`**, which it assigns
into `_stops[index]`. `_hasAnyChanges()` — the gate for the "Save All" button — reads
only map keys (`modified`, `action`, `moved`).

`edit_stop_screen.dart` never returned a map. Its two live exit paths popped `true`:

- **`_markAsModified`** (the "modified" button): mutates `widget.stopData`
  (`modified: true`, `text`, `action`), then `Navigator.pop(context, true)`.
- **`_deleteStop`**: sets `widget.stopData['action'] = 'delete'`, then `Navigator.pop(context, true)`.

Result: the caller assigned a **bool** into `_stops[index]`. Every later
`stop['modified']` / `stop['action']` read then operated on a bool, always false →
**Save All stayed greyed out** ("changed stop 2, Save All greyed"), and **add-stop
failed** the same way (an added stop's `action: 'add'` never survived).

## The fix (both files change together — they were changed apart; that is the bug)

### `edit_stop_screen.dart` — return the stop map on the two real exit paths
Both methods already mutate `widget.stopData` in place, so returning that same map
object is the smallest correct change and matches what the caller already assumes.

```
_markAsModified: Navigator.pop(context, true)  →  Navigator.pop(context, widget.stopData)
_deleteStop:     Navigator.pop(context, true)  →  Navigator.pop(context, widget.stopData)
```

**Deliberately left unchanged** (verified by reading all ~47 pop sites):
- All `pop(context, true/false)` inside `showDialog`/`AlertDialog` builders — these are
  confirm/cancel dialog dismissals (AC #5). Changing them would break unrelated flows.
- The no-change early return `pop(context)` in `_markAsModified` and the body/appbar
  "Cancel" `pop(context)` — they return `null` so cancelling makes no false change (AC #4).
- `_resetToOriginal` — it never pops the screen; it only resets the text field in place.
- Dead code `_saveChanges_REMOVED` / `_trackAudioGenerationAndRefresh` (only referenced
  by each other; the live UI calls neither) — left untouched as out of scope.

### `edit_tour_screen.dart` — one testable merge point with a map-only guard (AC #6)
`_editStop`'s inline merge was extracted into a top-level pure function
`applyEditStopResult(stops, editedStop, result)`:
- `null` result → no merge, returns `false` (cancel path, AC #4).
- non-`Map<String, dynamic>` result → **rejected** via `assert(false, ...)`; `_stops`
  is never corrupted. This is precisely the guard that would have caught the original
  bug (AC #6). `_editStop` still logs an `EDIT_CONTRACT_VIOLATION` debug line for a
  non-map result before delegating.
- valid map → assigned into `_stops[index]`, returns `true`.

Extracting it to a top-level function lets the contract be unit-tested without standing
up the whole `EditStopScreen` widget (which needs InAppWebView + native recorder).

## Tests (AC #7 — break the contract, see red)

`test/edit_stop_return_contract_test.dart` (6 tests, all green):
1. save path: a Map result merges back into `stops` (AC #1)
2. added stop reaches the list with `action=add` (AC #2)
3. delete path: `action=delete` map merges (AC #3)
4. cancel/no-change: `null` result leaves `stops` untouched (AC #4)
5. `stops` only ever contains maps after a valid merge (AC #6)
6. **non-map result (the old `pop(true)` bug) throws `AssertionError` and never
   corrupts `stops`** (AC #7) — reverting `edit_stop_screen` to `pop(context, true)`
   feeds a bool through this path and turns this test red.

## Verification

- `flutter test test/edit_stop_return_contract_test.dart` → **6/6 passed**.
- `flutter test` (full suite) → my 6 pass; the only failure is the pre-existing
  `widget_test.dart` (default counter template referencing package `audio_tour_app`/
  `MyApp`, but the package is `audio_tour_app_dev`). Confirmed failing on base `bd109fa`
  with my source changes stashed — unrelated to this task.
- `flutter analyze lib/screens/edit_stop_screen.dart lib/screens/edit_tour_screen.dart`
  → **0 errors**. Remaining items are pre-existing `info`/`warning` lints
  (`prefer_const_constructors`, `unused_import` on line 6, `unused_field` on line 87,
  `use_build_context_synchronously`). No analyzer issue lands on any line I added or
  modified.

## Not done (per task guardrails)
- Did **not** bump the version (`2.3.2+22` unchanged).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`, `ios/Runner/Info.plist`, or `pubspec.yaml`.
- Did **not** build/sideload to Michael's iPhone or rebuild Docker images (needs LEAD approval).

## Files changed
- `audio_tour_app/lib/screens/edit_stop_screen.dart` (2 exit pops)
- `audio_tour_app/lib/screens/edit_tour_screen.dart` (`applyEditStopResult` + `_editStop`)
- `audio_tour_app/test/edit_stop_return_contract_test.dart` (new)
