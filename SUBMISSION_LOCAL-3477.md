# SUBMISSION — LOCAL-3477: Add Stop Must Not Pop The Screen It Is Editing

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3477-add-stop-pops-screen`
**Base:** `storied` (worktree HEAD `e1341e6`)
**ClickUp:** `wdvrdayced` (reopened)

## TL;DR

The reported defect — pressing **+ Add Stop** popping `EditTourScreen` and discarding unsaved
edits — is **already fixed in the committed history at this base**. The fix and a dedicated
navigation contract test landed in commit `c9e27ca` ("LOCAL-477: Add Stop must not pop the edit
screen"), which is an ancestor of my HEAD. LOCAL-3477 is a re-report (reopened ticket) of the same
defect; the code that produced Michael's on-device symptom no longer exists on the local `storied`
tree.

I verified the fix against every acceptance criterion, including empirically proving the test goes
**red** when the stray pop is reinstated, then reverting. No source change was required. This file
is the deliverable and is committed on the branch.

## Base verification

```
git rev-parse HEAD              -> e1341e6f82da16c3f4c2d92d831bc0718eeabaad
git merge-base --is-ancestor e1341e6 HEAD  -> exit 0  (BASE OK)
git merge-base --is-ancestor c9e27ca HEAD  -> exit 0  (FIX COMMIT IS ANCESTOR)
```

Branch created/checked out: `LOCAL-3477-add-stop-pops-screen`. Base is local `storied`, not
`origin/*`.

## What the code looks like now (`edit_tour_screen.dart`)

`_addNewStop()` (line ~662) — the buggy `Navigator.pop(context)` described in the ticket is gone.
The current, correct implementation:

```dart
void _addNewStop() {
  final existingNumbers = _stops.map((s) => s['stop_number'] as int).toList();
  final maxNumber = existingNumbers.isEmpty ? 0 : existingNumbers.reduce((a, b) => a > b ? a : b);
  final newStopNumber = maxNumber + 1;

  final newStop = {
    'stop_number': newStopNumber,
    'title': 'Stop $newStopNumber',
    'text': _newStopContent,
    'original_text': '',
    'audio_file': 'audio_$newStopNumber.mp3',
    'editable': true,
    'modified': true,
    'action': 'add',
  };

  // Mutate _stops and refresh the list. Do NOT pop the screen — the user
  // stays on the edit screen so the new row appears and Save All enables,
  // exactly as after editing a stop's text. (LOCAL-477)
  setState(() {
    _stops.add(newStop);
    _stops.sort((a, b) => a['stop_number'].compareTo(b['stop_number']));
    _newStopContent = '';
  });

  unawaited(DebugLogHelper.addDebugLog('CRITICAL_ADD: ...')); // sync callback
}
```

This matches the prescribed fix exactly:
- The stray `Navigator.pop(context)` is removed.
- The `_stops` mutation + `_newStopContent` reset are wrapped in a single `setState`.
- No `setState` trails after unrelated work; there is no `await` before it, so no `mounted`
  guard is needed (the only post-`setState` line is a synchronous fire-and-forget log).

## Call-site audit (the ticket's ⚠️ check)

`grep _addNewStop` across `audio_tour_app/lib` returns exactly two hits:
- **definition** at line 662
- **one call site** at line 855: `onPressed: _addNewStop` on the "Add Stop" `OutlinedButton.icon`.

There is **no dialog** invoking `_addNewStop`, so removing the pop leaves nothing dangling. The
other `Navigator.pop` calls in the file are unrelated and correct:
- line 291 — pop inside a different flow,
- line 642 — the Save path returning `widget.tourData` to the caller,
- line 869 — the **Cancel** button (`onPressed: () => Navigator.pop(context)`), which is
  supposed to leave the screen.

None of these are affected.

## Acceptance criteria — verification

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | + Add Stop keeps user on edit screen; new row appears | PASS | Test `pressing "+ Add Stop" keeps the user on the edit screen (AC #1, #5)` — asserts `EditTourScreen` still present and `Stop 3` / `New` rendered |
| 2 | Unsaved edits to other stops survive | PASS | Test `unsaved edits to other stops survive an add (AC #2)` — stop 2 still `EDITED text...` + `Modified` after add |
| 3 | Save All enabled after an add | PASS | Test `Save All becomes enabled after an add (AC #3)` — button `onPressed` goes null → non-null |
| 4 | No setState after pop; no "disposed widget" flake | PASS | Code has no post-pop setState; test `no "setState on disposed widget" flake after add (AC #4)` asserts `tester.takeException()` is null |
| 5 | A test that fails if the pop returns | PASS | `test/add_stop_navigation_contract_test.dart` uses a `_PopCountingObserver`; proven red below |

### AC #5 — proven red with the pop reinstated

I temporarily re-added `Navigator.pop(context)` after the `setState` in `_addNewStop` and ran the
suite:

```
00:00 +0 -3: Save All becomes enabled after an add (AC #3) [E]
00:00 +1 -3: Some tests failed.
```

3 of 4 tests failed (the pop tears down `EditTourScreen`, so the row/Save-All/observer assertions
break). I then reverted the file (`git checkout --`) and re-ran:

```
00:00 +4: All tests passed!
```

So the navigation coverage genuinely catches a screen teardown, satisfying AC #5.

## `flutter analyze` output (changed/relevant files)

`flutter analyze lib/screens/edit_tour_screen.dart test/add_stop_navigation_contract_test.dart`
→ exit 0, **14 issues, all pre-existing and none in the `_addNewStop` region**:

```
warning • Unused import: 'package:path_provider/path_provider.dart' • edit_tour_screen.dart:6:8
warning • The value of the field '_originalStops' isn't used        • edit_tour_screen.dart:188:30
info    • Don't use 'BuildContext's across async gaps                • edit_tour_screen.dart:387/402/446/473/491/553
info    • Use 'const' with the constructor to improve performance    • edit_tour_screen.dart:388/389/403/404/447/448
```

No errors. No new issues introduced by this task (I made no source changes). The two `warning`s
and all `info`s are unrelated to add-stop navigation and predate this ticket.

## Scope discipline — what I did NOT touch

- **Save path** untouched. The `endpoint not found` on Save All is the gateway not routing
  `/tour/<id>/update-multiple-stops` — server-side, tracked as ClickUp `wdvrdaycwj`. Not fixable
  here.
- **Audio-editing 0-length issue** untouched (`tour_editing_service.dart` lines 63/89) — separate,
  undiagnosed.
- **Version NOT bumped.** Per `BUILD_NUMBERS.md`, build 22 is shipped on both platforms and 23 is
  next; `pubspec.yaml` is unchanged.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`.
- Did not install anything on Michael's iPhone.

## Conclusion

No source change was needed: the defect described in LOCAL-3477 was already resolved at this base by
`c9e27ca`, and the guarding test is in place and provably effective. This submission documents the
verification. The deliverable is committed on `LOCAL-3477-add-stop-pops-screen` so it is not lost to
worktree pruning (the failure mode called out in the task).
