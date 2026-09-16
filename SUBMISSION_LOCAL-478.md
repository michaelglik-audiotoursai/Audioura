# SUBMISSION — LOCAL-478 · Original Audio Fails Silently In The Stop Editor

**Branch:** `LOCAL-478-editor-original-audio`
**Base:** `storied` @ `6e37476` (`git merge-base --is-ancestor 6e37476 HEAD` → exit 0)
**ClickUp:** `wdvrdayced`

## The finding — the log's silence was the bug

Michael's device showed `Original Audio 00:00 -- 00:00`, would not play, and
his log contained **zero** `AUDIO_LOAD:` lines (`grep -c AUDIO_LOAD → 0`) even
though the same session showed `EDIT API: ... 200`. Only one exit from
`_loadSelectedAudio` logs nothing at all:

```dart
Future<void> _loadSelectedAudio() async {
  if (_audioWebViewController == null) return;   // silent bail
```

`_loadSelectedAudio` runs from several call sites (initState-driven preview,
dropdown-change handlers) as well as from `onWebViewCreated`. When it ran before
the audio `InAppWebView` had finished creating, the controller was null and the
request evaporated — no log, no UI, no retry. That silent `return` was the
primary defect.

A second, compounding cause: `audioPath` is built from
`widget.tourData['path']`, an absolute path. iOS reassigns the app container
UUID on reinstall/update, and Michael had just moved 2.3.2 (22) → (23) via
TestFlight, so stored absolute paths point into a container that no longer
exists. The Listen screen already heals this (`my_tours_screen.dart` →
`LISTEN: Healed stale container paths in saved_tours`); the editor did not.

## What changed

### 1. The failure is now visible and self-diagnosing
`edit_stop_screen.dart::_loadSelectedAudio`:
- The bare `return` is replaced by a **logged, deferred** outcome:
  `AUDIO_LOAD: Controller not ready ... deferring load until WebView is created`.
- Before loading, it logs the resolved path and existence so the next field
  report distinguishes the two causes without a code read:
  `AUDIO_LOAD: Resolving original audio: <path> (exists: <bool>)`.
- On a genuine failure (file missing, or `HtmlAudioPlayerService.loadAudio`
  returns false) it logs `AUDIO_LOAD: FAILED — ...` **and** shows a red
  SnackBar via `_showAudioError`. `00:00 -- 00:00` with no explanation no longer
  happens. (AC #3)

### 2. The null-controller ordering is fixed by retry, not a drop
- A `_pendingAudioLoad` flag records a load that ran too early.
- `onWebViewCreated` assigns the controller and then replays the load
  (`AUDIO_LOAD: WebView ready — retrying deferred load`), so a request that
  arrived before the WebView existed is retried once the controller is ready
  rather than dropped. (AC #1)

### 3. Path healing is reused, not reimplemented
- The Listen screen's rule (`/tours/` marker → re-anchor onto the current
  Documents dir) is lifted verbatim into one shared pure function
  `lib/utils/tour_path_healer.dart::healTourPath(path, docsDir)`.
- `my_tours_screen._healTourPaths` now **calls** that function instead of its
  old inline copy, and the editor calls the same function before touching the
  original audio file. One implementation, so the two screens cannot drift.
  A heal is logged: `AUDIO_LOAD: Healed stale container path: <old> -> <new>`.
  (AC #2)

### 4. A test that goes red if the silent return comes back
The null-controller decision is expressed as a pure, top-level
`planAudioLoad({required bool controllerReady})` returning
`AudioLoadPlan.proceed` / `AudioLoadPlan.deferAndLog`, which the production
method consumes. `test/edit_stop_audio_load_test.dart` pins:
`controllerReady == false → deferAndLog` (a logged, retryable outcome — never a
silent no-op). Reintroducing the bare `return` (removing the defer branch)
breaks that mapping and the test fails. The same file tests `healTourPath`. (AC #4)

## Verification

`flutter analyze` on the changed files — **0 error-level issues**. Remaining
output is pre-existing `info` (`prefer_const_constructors`) / `warning`
(`unused_element`) lints elsewhere in these large files, none introduced here:

```
$ flutter analyze lib/screens/edit_stop_screen.dart lib/utils/tour_path_healer.dart test/edit_stop_audio_load_test.dart
... (only prefer_const_constructors info lines, unrelated build code) ...
$ flutter analyze lib/screens/my_tours_screen.dart | grep -c "error •"
0
```

`flutter test` on the relevant suites — **all pass**:

```
$ flutter test test/edit_stop_audio_load_test.dart test/edit_stop_return_contract_test.dart
00:00 +13: All tests passed!
```

Full suite: 102 pass, 1 fail. The single failure is `test/widget_test.dart`,
which is broken **at the base commit `6e37476`** — it imports
`package:audio_tour_app/main.dart` while the package is `audio_tour_app_dev`.
Pre-existing and out of scope for this task.

### AC #5 — device `AUDIO_LOAD:` lines
**Not captured.** The task forbids installing on Michael's iPhone (he is on
TestFlight 2.3.2 (23)), and no separate device was provisioned in this
worktree. The instrumentation is in place so the next field/simulator run emits
the diagnostic lines above; the log evidence should be attached from a device
that is not Michael's before final sign-off.

## Scope discipline
- Did **not** touch the save path (narration corruption is server-side,
  `wdvrdayd3d`).
- Did **not** touch `_addNewStop` (LOCAL-477).
- Did **not** bump the version or edit any of the protected docs
  (`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`).

## Files
- `audio_tour_app/lib/utils/tour_path_healer.dart` (new) — shared healer.
- `audio_tour_app/lib/screens/edit_stop_screen.dart` — visible/logged load,
  retry, healing, `planAudioLoad`, `_showAudioError`.
- `audio_tour_app/lib/screens/my_tours_screen.dart` — `_healTourPaths` now calls
  the shared `healTourPath`.
- `audio_tour_app/test/edit_stop_audio_load_test.dart` (new) — AC #4 + healing.
