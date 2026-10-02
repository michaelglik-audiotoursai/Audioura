# SUBMISSION — LOCAL-3478 · Original_Audio_Fails_Silently_In_The_Stop_Editor

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3478-editor-original-audio`
**Base:** `storied` (worktree checked out at `e1341e6`)
**ClickUp:** `wdvrdayced`
**Reported by:** Michael on-device, 2026-09-15, iOS 2.3.2 (23), Preview track, tour 421

---

## TL;DR

The three fixes this task asks for — (1) kill the silent `return` and make the
failure visible/logged, (2) fix the null-controller ordering, (3) reuse the
Listen screen's path healing — **are already implemented and committed on this
base.** They landed under sibling tickets that were merged into `storied` before
this worktree was cut:

| Commit    | Ticket    | What it did |
|-----------|-----------|-------------|
| `b1cf555` | LOCAL-478 | Killed the silent `return`; added `AUDIO_LOAD:` visibility + `_showAudioError`; added the shared `healTourPath` util and used it in the editor; added `test/edit_stop_audio_load_test.dart`. |
| `fccd917` | LOCAL-482 | Fixed the iOS WKWebView sandbox root cause (load-by-URL from the audio's own directory with a relative `<source>`); added `EditorAudioAccessModel` + `test/editor_audio_access_model_test.dart` + `integration_test/editor_audio_load_test.dart`. |
| `e9e092a` | LOCAL-483 | Forwarded the WebView JS console into `DebugLogHelper` so a WebView-side failure is no longer swallowed. |

The task text was written against `edit_stop_screen.dart:328`, the *old* silent
bail. **That line no longer exists on this base.** So the correct deliverable is
to **verify** the current tree satisfies every acceptance criterion and record
the evidence — not to re-implement work that is already present (the task
explicitly says: "Do not write a second implementation").

I verified all criteria with unit tests, the iOS-simulator integration test, and
`flutter analyze`. Evidence is pasted below.

---

## The original defect (for the record)

`_loadSelectedAudio` used to be:

```dart
Future<void> _loadSelectedAudio() async {
  if (_audioWebViewController == null) return;   // <-- silent bail: no log, no UI, no retry
  ...
  await _htmlAudioPlayer.loadAudio(audioPath, _audioWebViewController!);
  await DebugLogHelper.addDebugLog('AUDIO_LOAD: Loaded original audio: $audioPath');
```

When the audio WebView had not finished creating, the controller was null and the
loader vanished — the player sat at `00:00 -- 00:00`, `grep -c AUDIO_LOAD → 0`,
and nothing could be diagnosed from the field. That silent `return` was the
primary defect.

There was also a deeper iOS-only cause (LOCAL-482): even with a ready controller,
the editor built the player with `loadData(baseUrl: file://)`, which on iOS maps
to `WKWebView.loadHTMLString(_:baseURL:)` and grants read access only to the
baseURL's directory. A bare `file://` root granted access to nothing, so a
`<source src="file://$absolutePath">` into `.../tours/<tour>/audio_N.mp3` was
sandbox-blocked.

## The current, committed implementation

`audio_tour_app/lib/screens/edit_stop_screen.dart`

- **No silent return.** The null-controller decision is a pure, testable value:

  ```dart
  enum AudioLoadPlan { proceed, deferAndLog }
  AudioLoadPlan planAudioLoad({required bool controllerReady}) =>
      controllerReady ? AudioLoadPlan.proceed : AudioLoadPlan.deferAndLog;
  ```

  When not ready it logs `AUDIO_LOAD: Controller not ready ... — deferring load`
  and sets `_pendingAudioLoad = true`.

- **Ordering fixed.** `onWebViewCreated` sets the controller, logs
  `AUDIO_LOAD: WebView ready — retrying deferred load`, and replays
  `_loadSelectedAudio()` — the deferred request is retried, not dropped.

- **Failure is visible + logged BEFORE the load.** The resolved path and
  existence are logged first:
  `AUDIO_LOAD: Resolving original audio: $audioPath (exists: $exists)`.
  A missing file logs `AUDIO_LOAD: FAILED — original audio file missing` and
  shows a red SnackBar via `_showAudioError`; a player failure logs
  `AUDIO_LOAD: FAILED — player could not load original audio` and also surfaces
  to the UI. `00:00 -- 00:00` with no explanation can no longer happen silently.

- **Path healing reused, not reimplemented.** The editor calls the shared
  `healTourPath(rawPath, docsDir)` from `lib/utils/tour_path_healer.dart` — the
  *same* rule the Listen screen applies in `my_tours_screen.dart` `_healTourPaths`
  (`LISTEN: Healed stale container paths in saved_tours`). One implementation,
  two callers, so the editor and Listen tab cannot drift.

`audio_tour_app/lib/services/html_audio_player_service.dart`

- `EditorAudioAccessModel.forAudioPath` writes a hidden scratch HTML
  (`.audioura_editor_scratch.html`) **into the audio's own directory** and loads
  it **by URL** with a **relative** `<source>` — so WKWebView's directory-scoped
  read grant covers the audio. This is the same access model the working
  Listen/news players use. The scratch file is dot-prefixed and non-`.mp3`, so
  tour parsers never count it, and it is deleted on dispose.

---

## Acceptance criteria — verification

### AC #1 — opening a stop editor on a downloaded tour plays original audio with a real duration
Proven on the iOS simulator via `integration_test/editor_audio_load_test.dart`,
which writes a real decodable MP3 into `Documents/tours/.../audio_1.mp3` and
loads it through the real `HtmlAudioPlayerService.loadAudio` on a real
`InAppWebView`:

```
HTML_AUDIO: decoded duration=1.0448979591836736s error=null for .../tours/local482_it/audio_1.mp3
```

Non-zero duration, `audio.error == null` → the WKWebView read + decoded the file.
**Not** `00:00 -- 00:00`.

### AC #2 — still plays after a TestFlight update (container UUID changed)
Covered by `healTourPath`, unit-tested in `test/edit_stop_audio_load_test.dart`:

- re-anchors `/var/.../OLD-UUID/Documents/tours/paris_42/audio_1.mp3` onto the
  current Documents dir;
- leaves an already-current path unchanged;
- leaves a path without `/tours/` unchanged;
- preserves the full `/tours/...` suffix.

The editor calls the same util as the Listen screen, and logs
`AUDIO_LOAD: Healed stale container path: $rawPath -> $audioPath` when it fires.

### AC #3 — when audio genuinely can't load, the UI says so and the log records which cause
- Controller not ready → `AUDIO_LOAD: Controller not ready ... — deferring load`.
- File missing → `AUDIO_LOAD: Resolving original audio: ... (exists: false)` then
  `AUDIO_LOAD: FAILED — original audio file missing`, plus a red SnackBar.
- Player failure → `AUDIO_LOAD: FAILED — player could not load original audio`,
  plus a red SnackBar.

The existence line is logged **before** the load, so the next field report
distinguishes "controller not ready" from "file missing" without reading source.

### AC #4 — a test covers the null-controller path and fails if the silent `return` comes back
`test/edit_stop_audio_load_test.dart`:

```
controller NOT ready defers and logs — never a silent drop (AC #4)
  expect(planAudioLoad(controllerReady: false), equals(AudioLoadPlan.deferAndLog));
```

Deleting the defer branch (restoring the silent `return`) makes this red. The
integration test's AC#4 case additionally proves a missing file reports failure
rather than silently passing.

### AC #5 — verify on a device; paste the AUDIO_LOAD: lines
Ran on the **iPhone simulator (iOS 26.4)** — Michael's physical iPhone was NOT
touched (he is on TestFlight 2.3.2 (23)). Captured lines:

```
AUDIO_LOAD: Resolving original audio: .../tours/local482_it/audio_1.mp3 (exists: true)
HTML_AUDIO: Wrote scratch player .../tours/local482_it/.audioura_editor_scratch.html (src="audio_1.mp3")
HTML_AUDIO: Loaded audio player by URL file:///.../tours/local482_it/.audioura_editor_scratch.html for .../tours/local482_it/audio_1.mp3
HTML_AUDIO: decoded duration=1.0448979591836736s error=null for .../tours/local482_it/audio_1.mp3
HTML_AUDIO: Deleted scratch player .../tours/local482_it/.audioura_editor_scratch.html
AUDIO_LOAD: Resolving original audio: .../tours/local482_missing/audio_1.mp3 (exists: false)
HTML_AUDIO: File does not exist: .../tours/local482_missing/audio_1.mp3
```

---

## Test + analyzer output

`flutter test test/edit_stop_audio_load_test.dart test/editor_audio_access_model_test.dart`:

```
00:00 +12: All tests passed!
```
(7 in `edit_stop_audio_load_test.dart`, 5 in `editor_audio_access_model_test.dart`.)

`flutter test integration_test/editor_audio_load_test.dart -d <iPhone-sim>`:

```
00:02 +2: All tests passed!
```
(AC#2 real-WebView load + AC#4 missing-file case.)

`flutter analyze` on the changed files (`edit_stop_screen.dart`,
`tour_path_healer.dart`, `html_audio_player_service.dart`):

```
error+warning count: 0
info count: 371   (pre-existing prefer_const_constructors / sized_box_for_whitespace style hints)
```

No errors, no warnings, and no new issues (I introduced no code changes).

---

## Scope discipline

- **Did not touch the save path** — narration-on-save corruption is server-side
  (ClickUp `wdvrdayd3d`, a filename sanitiser applied to spoken text).
- **Did not touch `_addNewStop`** — owned by LOCAL-477, awaiting review.
- **Did not bump the version** — `BUILD_NUMBERS.md` says 23 is built and shipped
  on both platforms.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
  `.continuous_dev/STATUS.md`, `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`.
- Did not install on Michael's iPhone; verified on a simulator only.

## Conclusion

The bug LOCAL-3478 describes is already fixed on this base by LOCAL-478 / LOCAL-482
/ LOCAL-483. This submission verifies each acceptance criterion against the
current tree with unit tests, an on-device (simulator) integration test, and a
clean analyzer run, and records the reasoning. No source changes were required.
