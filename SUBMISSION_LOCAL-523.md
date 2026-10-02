# SUBMISSION — LOCAL-523: The mobile loop for entering stops

**Branch:** `LOCAL-523-user-stops-mobile`
**Base:** `storied` @ `e1341e6` (verified `git merge-base --is-ancestor e1341e6 HEAD` → exit 0)

## What Michael asked for

> *an Audioura Mobile application loop for the user to enter the stops one by
> one, then present with the user's own selection, then generate the tour based
> on these stops.*

The generate screen gains a choice — **Audioura suggests the stops** (today's
behaviour, the default) or **I will name the stops**. Choosing the second opens
an add-one-at-a-time list with reorder and delete, then a review screen, then
generate.

## What I built

### 1. One mechanism, not two (D564)

The editor already grows a stop list one row at a time (`_addNewStop` /
`_reorderStops` in `edit_tour_screen.dart`). Rather than write a second, subtly
different list manager for the pre-generation loop, I extracted the *rules* of
that mechanism into a pure, unit-testable module:

`lib/utils/user_stops.dart`
- `buildUserStop` / `addStop` / `removeStopAt` / `reorderStops` / `renumberStops`
  — the same `Map<String, dynamic>` stop shape the editor uses
  (`{stop_number, title, text, audio_file, editable, action:'add'}`), and the
  same "renumber after every mutation" invariant the editor restores after a
  reorder.
- `validateNewStopEntry` / `validateStopList` / `isStopListReady` — the inline
  validation (see AC #3).
- `stopTitlesForGeneration` — the ordered names handed to generation.

### 2. The loop screen

`lib/screens/user_stops_screen.dart` — `UserStopsScreen`:
- **Build phase:** a text field + Add button adds one stop at a time; a
  `ReorderableListView` supports drag-to-reorder and per-row delete; warnings
  render **inline** as the list is built.
- **Review phase:** the ordered, numbered selection with a **Use these stops**
  button.
- Pops the ordered `List<Map<String, dynamic>>` on confirm, or `null` on
  Cancel/Back (so the caller's default path is untouched).

### 3. The opt-in on the generate screen

`lib/screens/tour_generator_screen.dart`:
- A `SegmentedButton` (Tours mode only): **Audioura suggests** (default) vs
  **I will name the stops**. State field `_stopMode` defaults to `'suggest'`.
- Choosing **I will name the stops** swaps the "Number of stops" field for an
  **Add / Edit your stops** button that opens `UserStopsScreen`.
- Both generate paths (`_generateTour` foreground and `_generateTourBackground`)
  derive the stop count from the reviewed list and attach the ordered names as
  `tourData['user_stops']` — only when the user opted in.

## Acceptance

1. **Default path unchanged for a user who does not opt in.** `_stopMode`
   defaults to `'suggest'`; in that branch the "Number of stops" field, the
   1–30 validation and the request body are byte-for-byte the original code.
   The `user_stops` key is only added under `_stopMode == 'name'`. ✅
2. **Stops can be added, reordered, deleted, and reviewed before generating.**
   The build phase (add/reorder/delete) → review phase → returns the ordered
   selection. Covered by pure-function and widget tests. ✅
3. **Validation warnings shown INLINE, not after generating.** Empty name,
   duplicate name, and count bounds are computed by `user_stops.dart` and
   painted inline as the user types / builds the list — the Review and
   "Use these stops" buttons stay disabled until the list is valid. ✅
4. **Flutter tests cover the loop; no new package.** 23 new tests across two
   files; no dependency added to `pubspec.yaml`. ✅

## Files

- `audio_tour_app/lib/utils/user_stops.dart` (new)
- `audio_tour_app/lib/screens/user_stops_screen.dart` (new)
- `audio_tour_app/lib/screens/tour_generator_screen.dart` (opt-in wired in)
- `audio_tour_app/test/user_stops_test.dart` (new — pure mechanism + validation)
- `audio_tour_app/test/user_stops_screen_test.dart` (new — the loop, widget-driven)

## Verification

```
$ flutter analyze lib/utils/user_stops.dart lib/screens/user_stops_screen.dart \
    test/user_stops_test.dart test/user_stops_screen_test.dart
No issues found!

$ flutter test
00:02 +155: All tests passed!
```

(155 = 132 pre-existing + 23 new. `flutter analyze` on the full
`tour_generator_screen.dart` reports only pre-existing `info`/`warning` lint;
no new errors introduced by this change.)

## Notes on scope

The backend `/generate-complete-tour` does not yet consume a `user_stops`
field; this change forwards it forward-compatibly (an unrecognised key is
ignored) so the mobile loop and the user's selection are complete and testable
now. Wiring the orchestrator to honour a user-supplied stop list is a separate
backend ticket.
