# SUBMISSION — LOCAL-484 · The stop count on Listen must follow the edit

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-484-listen-stop-count-stale`
**Base:** storied = `407c2c1` (verified: `git merge-base --is-ancestor 407c2c1 HEAD` → exit 0)

---

## The defect

On the Listen page (`my_tours_screen.dart:1359`), the stop count rendered from a value
written **once, at download time**:

```dart
Text('${tour['stops'] ?? '10'} stops • Created: ...')
```

`'stops'` is written into the `saved_tours` SharedPreferences entry when a tour is first
downloaded (`tour_generator_screen.dart:578`). The only writer that touched a saved tour
after an edit — `edit_tour_screen._updateLocalTourId` — set exactly one key, `new_tour_id`,
and left `'stops'` frozen forever. Add a stop, Save All, return to Listen → old count.

Two lies in one line, then:
1. `'stops'` never updated after an edit.
2. `?? '10'` invented "10 stops" for any tour that never stored a count.

---

## What I changed

Three small, pure, unit-testable top-level functions and their wiring. No divergent copy of
the list-rewrite logic — the existing walk was **extended**, per the task constraint.

### 1. `applyTourEditToSavedTours(savedTours, tourPath, {newTourId, stopCount})`
`edit_tour_screen.dart`. One walk over the `saved_tours` list, matches on `path`, and writes
**both** `new_tour_id` and `stops` in the same pass. `stopCount` is nullable: when the count
is unknown we leave `'stops'` untouched rather than guess. Malformed entries pass through
untouched. Returns a new list (the value handed to `prefs.setStringList`).

`_updateLocalTourId` was reduced to: read prefs → call this function → write prefs. It now
takes an optional `stopCount`.

### 2. `countStopsOnDisk(tourDirPath)`
`edit_tour_screen.dart`. Counts `audio_<n>.mp3` files directly in the tour directory.
Returns `null` (unknown) when the directory is missing or has no audio files — never a guess.

Wired into `_handleNewTourDownload`: after `downloadUpdatedTour` extracts the complete edited
tour into `tourPath`, we count the mp3s there and pass the number to `_updateLocalTourId`.
This runs **before** the in-memory `widget.tourData['path']` is repointed to the new id, so
it matches the same `tourPath` the `saved_tours` entry is keyed on.

### 3. `tourSubtitleLine(tour)`
`my_tours_screen.dart`. Builds the subtitle. Emits `"N stops • Created: …"` only when a count
is stored; when `stops` is absent or empty it emits just `"Created: …"`. The `?? '10'`
fallback is gone.

---

## Which count did I use, and why

**I count the stops written to disk. I do NOT use the server response, because the response
does not carry a count.**

I traced the Save-All response builder in `tour_editing_phase2.py::_bulk_save_core`
(the success `jsonify` at ~line 1932). The response is exactly:

```python
response = {
    "status": "success",
    "message": message,
    "stops": response_stops,          # the processed subset, NOT a merged total
    "new_tour_id": new_tour_info['new_tour_id'],
    "download_url": f"/tour/{new_tour_info['new_tour_id']}/download",
}
```

There is **no `stops_count`** field. The orchestrator persists `stops_count` server-side on
INSERT/UPDATE, but that value is not echoed back on the editing save path the app calls
(`/tour/<id>/update-multiple-stops`). The `stops` array present in the response reflects only
the stops the app sent for processing plus response bookkeeping — it is not the merged,
renumbered total, so it is not a trustworthy count either.

The download, by contrast, writes the **complete** edited tour to disk — one `audio_<n>.mp3`
per stop. That is authoritative and local. So the fix counts those files. The task said
"prefer the server's count where one is available; if not, count the stops on disk" — it is
not available, so I count disk, and I am saying so here explicitly.

---

## Acceptance criteria → evidence

| AC | Criterion | Covered by |
|----|-----------|------------|
| 1 | Add a stop, Save All → count includes it | `applyTourEditToSavedTours` writes new count; test "AC #1 — adding a stop raises the persisted count" |
| 2 | Delete a stop → count goes down | test "AC #2 — deleting a stop lowers the persisted count" |
| 3 | No stored count → no count shown (no "10 stops") | `tourSubtitleLine` omits the segment; tests "AC #3 …" (x2) |
| 4 | Text-only edit → count unchanged | `stopCount` null path; test "AC #4 — a text-only edit … leaves stops alone" |
| 5 | Count survives app restart (persisted) | written via `prefs.setStringList`; test "AC #5 — the new count survives a persistence round-trip" |
| 6 | Break the update → a test goes red | test "AC #6 — regression guard"; proven red below |

---

## Test output (real)

### New tests, in isolation — all green

```
$ flutter test test/listen_stop_count_test.dart
00:00 +0: LOCAL-484 applyTourEditToSavedTours AC #1 — adding a stop raises the persisted count
00:00 +1: LOCAL-484 applyTourEditToSavedTours AC #2 — deleting a stop lowers the persisted count
00:00 +2: LOCAL-484 applyTourEditToSavedTours AC #4 — a text-only edit (count unknown/null) leaves stops alone
00:00 +3: LOCAL-484 applyTourEditToSavedTours only the matched tour is touched; others pass through untouched
00:00 +4: LOCAL-484 applyTourEditToSavedTours malformed entries are preserved, not dropped
00:00 +5: LOCAL-484 applyTourEditToSavedTours AC #5 — the new count survives a persistence round-trip (encode → store → decode)
00:00 +6: LOCAL-484 applyTourEditToSavedTours AC #6 — regression guard: count actually changes after an add
00:00 +7: LOCAL-484 countStopsOnDisk counts audio_*.mp3 files (the authoritative disk count)
00:00 +8: LOCAL-484 countStopsOnDisk returns null when the directory has no audio files (unknown)
00:00 +9: LOCAL-484 countStopsOnDisk returns null when the directory does not exist
00:00 +10: LOCAL-484 tourSubtitleLine AC #1/#2 — renders the stored count
00:00 +11: LOCAL-484 tourSubtitleLine AC #3 — a tour with no stored count renders WITHOUT a count
00:00 +12: LOCAL-484 tourSubtitleLine AC #3 — an empty count string also renders without a count
00:00 +13: All tests passed!
```

### AC #6 — proving red (D242: exit=0 proves nothing; here is the failure)

I temporarily gated the count write with `if (false) { entry['stops'] = stopCount.toString(); }`
and re-ran. Five tests failed, including the regression guard:

```
Expected: not '5'
  Actual: '5'
If the edit no longer writes the stop count, this goes red — exactly the original LOCAL-484 defect.
00:00 +2 -5: LOCAL-484 applyTourEditToSavedTours AC #6 — regression guard: count actually changes after an add
...
00:00 +8 -5: Some tests failed.
```

Also red under the break: AC #1, AC #2, AC #5, and the malformed-entry count assertion
(`Expected: '7' Actual: '5'`, etc.). Restored the file immediately after; the count-write
line is back at `edit_tour_screen.dart:109`.

### Full suite

```
$ flutter test
00:06 +124 -1: Some tests failed.
```

The single failure is **pre-existing and out of scope**: `test/widget_test.dart` is the default
Flutter template smoke test. It imports `package:audio_tour_app/main.dart` and references
`MyApp`, but this package is named `audio_tour_app_dev` and has no `MyApp`. `git diff 407c2c1 --
test/widget_test.dart` shows no changes — it fails identically on the untouched base. I did not
touch it (LEAD/other tickets own that template).

Running the whole suite **except** that broken template → everything green, confirming my file
compiles cleanly alongside the rest and there are no regressions:

```
$ flutter test <all test/*.dart except widget_test.dart>
00:04 +124: All tests passed!
```

(The `Dart compiler exited unexpectedly` line that appears against my file only in the *full*
run is a cascade from `widget_test.dart`'s compilation failure in the shared batch — my file
compiles and runs fine on its own and in the exclude-widget_test run above.)

### Analyze

`flutter analyze` on the three changed files reports only pre-existing `info`/`warning`
lints elsewhere in `my_tours_screen.dart` (const constructors, an unused `_getDisplayTitle`,
etc.) — **none in the three functions I added or in `edit_tour_screen.dart`**.

---

## Files changed

- `audio_tour_app/lib/screens/edit_tour_screen.dart` — `applyTourEditToSavedTours`,
  `countStopsOnDisk`, `_updateLocalTourId` refactor + call-site wiring.
- `audio_tour_app/lib/screens/my_tours_screen.dart` — `tourSubtitleLine`, removed `?? '10'`.
- `audio_tour_app/test/listen_stop_count_test.dart` — 13 tests (new).

## Not touched (per PROCESS)

`html_audio_player_service.dart`, `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
`.continuous_dev/STATUS.md`, `BUILD_NUMBERS.md`, `PENDING_REMINDERS.md`, `pubspec.yaml`
version.
