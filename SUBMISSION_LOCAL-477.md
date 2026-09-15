# SUBMISSION — LOCAL-477 — Add Stop Must Not Pop The Screen It Is Editing

**Branch:** `LOCAL-477-add-stop-pops-screen`
**Base:** storied (`git merge-base --is-ancestor 117b6bf HEAD` → exit 0, verified before first commit)
**ClickUp:** `wdvrdayced`

## The defect

`audio_tour_app/lib/screens/edit_tour_screen.dart`, `_addNewStop()`.

The method built the new stop correctly (`modified: true, action: 'add'`) and added
it to `_stops`, then ran a stray **`Navigator.pop(context)`**. `_addNewStop` is wired
directly to the "Add Stop" `OutlinedButton.icon` (`onPressed: _addNewStop`) — **there is
no dialog to dismiss**, so that pop tore down `EditTourScreen` itself, returning the user
to the Listen page and discarding every unsaved edit in `_stops`. A trailing
`setState(() {})` then ran on the disposed widget.

### Call-site check (per task instruction)

Searched the whole app for `_addNewStop`. Exactly two hits: the definition and the single
button wiring at line 742 (`onPressed: _addNewStop`). Nothing reached it from a dialog, so
removing the pop leaves no dialog stranded.

## The fix

Removed the `Navigator.pop(context)`. The mutation of `_stops` (add + sort) and the reset
of `_newStopContent` are now wrapped in a single `setState`, so the new row appears and
Save All enables while the user stays on the edit screen — exactly the behaviour after
editing a stop's text. No `await` precedes the `setState`, so no `mounted` guard is needed;
the previous "setState after pop on a disposed widget" hazard is gone because there is no
pop.

```dart
setState(() {
  _stops.add(newStop);
  _stops.sort((a, b) => a['stop_number'].compareTo(b['stop_number']));
  _newStopContent = '';
});
unawaited(DebugLogHelper.addDebugLog('CRITICAL_ADD: ...'));
```

## Test coverage (AC #5)

New file: `test/add_stop_navigation_contract_test.dart`. The existing
`edit_stop_return_contract_test.dart` covers the *merge* contract but nothing covered
*navigation*. The new widget tests pump the real screen, tap the real "Add Stop" button,
and use a `NavigatorObserver` that counts pops:

1. **AC #1/#5** — after Add Stop, `popCount` is unchanged, `EditTourScreen` is still
   present, and a new "Stop 3" row with a "New" badge appears.
2. **AC #2** — a pre-edited stop 2 (`modified: true`, new text) still shows its edited text
   and "Modified" badge after an add.
3. **AC #3** — Save All starts disabled and becomes enabled after an add.
4. **AC #4** — `tester.takeException()` is null (no setState-on-disposed-widget).

**Red-with-pop proof:** I temporarily reinstated `Navigator.pop(context)` and re-ran. The
suite went red exactly where it should: AC #1/#5 reported `popCount Expected <0> Actual <1>`,
AC #2 lost the edited text (screen torn down), AC #3 could no longer find Save All. I then
removed the temporary pop and confirmed all 10 tests (4 new + 6 existing contract) pass.

### Test seam

The real `_loadTourStops` path does disk I/O and awaits `SharedPreferences` at
`initState` time. Those awaits are bound to `flutter test`'s fake-async zone and never
resolve, so a full-load widget test hangs (verified: valid-path load hung to timeout while
a bad-path early-return did not). To render the loaded list deterministically I added a
minimal, production-inert seam: an optional `debugInitialStops` parameter on
`EditTourScreen`. When provided (tests only), `initState` seeds `_stops` synchronously and
skips the async load. No production call site passes it, so on-device behaviour is
unchanged. The button, `_addNewStop`, the Navigator wiring, and Save-All gating under test
are all the real code — only loading is bypassed.

## Verification

- `flutter analyze lib/screens/edit_tour_screen.dart`: **14 issues, identical set and count
  to the pristine HEAD version** (compared via `git stash`). The only pre-existing warnings
  are an unused `path_provider` import and an unused `_originalStops` field — both present
  before my change. **No new issues introduced.**
- `flutter analyze test/add_stop_navigation_contract_test.dart`: **No issues found.**
- `flutter test test/add_stop_navigation_contract_test.dart test/edit_stop_return_contract_test.dart`:
  **All 10 tests pass.**
- Full suite: 99 pass, 1 fail. The single failure is the pre-existing stale
  `test/widget_test.dart` (template file importing the wrong package name
  `audio_tour_app` and a non-existent `MyApp`) — committed in "First commit", never touched
  by this task, unrelated to the fix.

## Scope adherence

- Did **not** touch the save path (`/tour/<id>/update-multiple-stops` gateway routing is
  server-side, ClickUp `wdvrdaycwj`).
- Did **not** touch the audio-editing 0-length issue (`tour_editing_service.dart`).
- Did **not** bump the version (pubspec stays `2.3.2+22`).
- Did **not** edit any of the protected docs (DECISIONS.md, CLAUDE.md, BACKLOG.md,
  STATUS.md, PENDING_REMINDERS.md, BUILD_NUMBERS.md).
- Did **not** install on Michael's device.

## Files changed

- `audio_tour_app/lib/screens/edit_tour_screen.dart` — removed stray pop, wrapped mutation
  in `setState`, added test-only `debugInitialStops` seam.
- `audio_tour_app/test/add_stop_navigation_contract_test.dart` — new navigation contract
  tests (AC #1–#5).
