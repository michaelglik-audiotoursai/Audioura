# SUBMISSION — LOCAL-482 · WKWebView Cannot Read A File It Was Not Given Access To

**Branch:** `LOCAL-482-editor-audio-file-access`
**Base:** `storied` = `c2be1ff` (verified: `git merge-base --is-ancestor c2be1ff HEAD` → exit 0; HEAD started exactly at c2be1ff)
**Agent:** Mac Mini Kiro

---

## 1. Diagnosis — confirmed

The report: editing a stop shows the Original Audio box flash, then **"Failed to load audio"**.

**Confirmed by code inspection** (the two contrasting access models):

- **Editor (broken)** — `lib/services/html_audio_player_service.dart`:
  - `_createAudioHtml` emitted `<source src="file://$audioPath">` (absolute).
  - `loadAudio` called `controller.loadData(data: html, baseUrl: WebUri('file://'))`.
  - On iOS `loadData` → WKWebView `loadHTMLString(_:baseURL:)`, which grants the page
    read access **only to the baseURL's own directory**. The baseURL was the bare
    `file://` root → the page could read **nothing**, so the `<source>` into
    `.../Documents/tours/<tour>/audio_N.mp3` was sandbox-blocked. The `<audio>` element
    errored, the retry loop (`:193-214`, 5×800 ms) burned out, and the field showed
    "Failed to load audio".

- **Listen tab / news player (working)** — `news_player_screen.dart:75`,
  `tour_player_screen.dart:71` load `file://$dir/index.html` **by URL**. The baseURL is
  then the tour directory, so WKWebView's read grant covers the audio beside it. Same
  files, same WebView package, different access grant.

The LOCAL-478 `AUDIO_LOAD:` log already reports `existsSync`; the failure is not a missing
file (the editor even guards that path and shows a distinct message), so the sandbox-scope
diagnosis holds rather than a path bug.

---

## 2. The fix — match the players' access model

`lib/services/html_audio_player_service.dart`:

- Added **`EditorAudioAccessModel`** — a pure, unit-testable value object built from the
  audio path. It yields:
  - `directory` — the audio's own directory (the WKWebView read-access scope),
  - `relativeSrc` — just the filename, so `<source src="audio_N.mp3">` resolves **inside**
    the granted scope (never an absolute `file://` URL),
  - `scratchHtmlPath` — `<dir>/.audioura_editor_scratch.html`,
  - `loadUrl` — `file://<dir>/.audioura_editor_scratch.html`.
- `loadAudio` now **writes the scratch HTML into the audio's directory** and calls
  `controller.loadUrl(URLRequest(url: WebUri(loadUrl)))` — mirroring the working players.
- `_createAudioHtml` now takes the **relative** src.

This is the "preferred, cheapest, closest to what already works" shape from the task.
Alternatives considered:
- `loadFile` + `allowingReadAccessTo` Documents — broader grant than needed; the players
  don't use it, so this keeps the editor consistent with them.
- `InAppLocalhostServer` — a whole HTTP server per editor open; heavy, more surface area.
- Base64 `data:` URI — **rejected** (task's last resort): a 3 MB mp3 → ~4 MB inline text
  per stop, per open.

### Cleanup (AC #5)
- Scratch file is **dot-prefixed** (`.audioura_editor_scratch.html`) and **not** `*.mp3`,
  so existing tour parsers ignore it — they count `*.mp3` only
  (`tour_generator_screen.dart:563`, `tour_translation_helper.dart:166`).
- `_deleteScratchHtml()` runs before each fresh load (clears stale/crash leftovers) and via
  the new public `dispose()`.
- `EditStopScreen.dispose()` now calls `_htmlAudioPlayer.dispose()`
  (`lib/screens/edit_stop_screen.dart`), so nothing is left in the tour directory to leak
  into a re-zip / download / sync.

---

## 3. Proof

### 3a. On a real iOS simulator with a real MP3 (AC #2, AC #4, AC #5)

`integration_test/editor_audio_load_test.dart` mounts a **real `InAppWebView`**, writes a
**real, decodable 1 s MP3** (ffmpeg `libmp3lame`, base64 in `integration_test/mp3_fixture.dart`)
into a real `.../Documents/tours/local482_it/` dir, and drives
`HtmlAudioPlayerService.loadAudio`.

Run: `flutter test integration_test/editor_audio_load_test.dart -d <iPhone 17 sim>`
(CocoaPods 1.17.0 was installed via Homebrew so iOS plugin builds work.)

```
+0: AC#2 — original audio loads on a real WebView via the editor access model
AUDIO_LOAD: Resolving original audio: .../Documents/tours/local482_it/audio_1.mp3 (exists: true)
HTML_AUDIO: Wrote scratch player .../tours/local482_it/.audioura_editor_scratch.html (src="audio_1.mp3")
HTML_AUDIO: Loaded audio player by URL file:///.../tours/local482_it/.audioura_editor_scratch.html for .../audio_1.mp3
HTML_AUDIO: decoded duration=1.0448979591836736s error=null for .../tours/local482_it/audio_1.mp3
HTML_AUDIO: Deleted scratch player .../tours/local482_it/.audioura_editor_scratch.html
+1: AC#4 — a genuinely missing file still fails clearly
AUDIO_LOAD: Resolving original audio: .../tours/local482_missing/audio_1.mp3 (exists: false)
HTML_AUDIO: File does not exist: .../tours/local482_missing/audio_1.mp3
+2: All tests passed!
```

- **AC#2:** `decoded duration=1.0448…s error=null` — WKWebView actually **read + decoded**
  the audio via `loadUrl(file://<dir>/.audioura_editor_scratch.html)` + relative
  `src="audio_1.mp3"`. (The intermediate `readyState:1, error:null, duration:1.0448,
  currentSrc:file://…/audio_1.mp3` diag confirmed the media element itself, not just my
  assertion.)
- **AC#4:** missing file → `loadAudio` returns `false`, distinct log, no papering over.
- **AC#5:** scratch HTML deleted on `dispose()`; the test also asserts exactly one `.mp3`
  remains (the real one) — the scratch file is never counted as audio.

### 3b. Break the fix → test goes red (AC #6)

The access model is pinned by `test/editor_audio_access_model_test.dart` (5 tests). To prove
it bites, I restored the old model in `EditorAudioAccessModel.forAudioPath`
(`relativeSrc: 'file://$audioPath'`, `loadUrl: 'file://'`) and re-ran:

```
+2 -2: Some tests failed.
Expected: 'audio_3.mp3'   Actual: 'file:///…/audio_3.mp3'   (relative-src test)
Expected: 'file:///…/.audioura_editor_scratch.html'   Actual: 'file://'   (load-URL-scope test)
```

Reverted → `All tests passed!` (5/5).

### 3c. Honest finding — the simulator does NOT reproduce the on-device sandbox block

I also tried to make the **integration** test go red by faithfully restoring the original
`loadData(baseUrl: WebUri('file://'))` + absolute src in `loadAudio`. On the **iOS
simulator it still decoded** (`duration=1.0448s error=null`). The simulator's WKWebView is
**more permissive with `file://` access than a physical device** — it does not enforce the
directory-scoped grant the way the device does. That is exactly why Michael saw the failure
on a real device/TestFlight build and why it never showed in a simulator.

Consequence: the device-only "break it red" cannot be demonstrated on this simulator. The
**AC#6 "test that pins the access model" is the unit test** (§3b), which goes red
deterministically and independently of the platform's permissiveness. The integration test
proves the positive direction (real WebView really reads the file through the new model).

---

## 4. AC checklist

| AC | Status | Evidence |
|----|--------|----------|
| 1. Editor loads original audio (real duration, no "Failed to load audio") | ✅ | §3a `decoded duration=1.0448s error=null` |
| 2. Proven on real device/simulator with real audio; log lines pasted | ✅ | §3a AUDIO_LOAD/HTML_AUDIO lines, iPhone 17 sim |
| 3. Listen tab / news player untouched | ✅ | Only `html_audio_player_service.dart` + editor `dispose()` changed; players still load `file://$dir/index.html` |
| 4. Missing file still reports a clear failure | ✅ | §3a AC#4 test: `File does not exist` → `false` |
| 5. No scratch file left after editor closes | ✅ | §3a `Deleted scratch player …`; dot-prefixed, non-`.mp3`, ignored by parsers |
| 6. Break the fix → pinning test goes red | ✅ | §3b unit test 2 failures on the broken model |

---

## 5. Verification commands & results

- `flutter test test/editor_audio_access_model_test.dart test/edit_stop_audio_load_test.dart`
  → **12/12 passed** (5 new access-model + 7 existing LOCAL-478).
- `flutter test` (full) → **111 passed, 2 failed**. The 2 failures are `test/widget_test.dart`
  (stale default template referencing `package:audio_tour_app/main.dart` + `MyApp`, neither of
  which exists — package is `audio_tour_app_dev`). **Pre-existing**: verified by stashing my
  `lib/` changes and re-running — it fails identically. Not caused by this task.
- `flutter analyze` on all touched files → my new files (`html_audio_player_service.dart`,
  `editor_audio_access_model_test.dart`, `integration_test/*`) report **No issues found**.
  The remaining `info`/`warning` items in `edit_stop_screen.dart` are pre-existing
  (`prefer_const_constructors`, unused legacy `_REMOVED`/dialog helpers) and untouched by my
  one-line `dispose()` addition.

## 6. Notes / constraints honored

- Did **not** bump `pubspec.yaml` version (still `2.3.2+25`); only added the
  `integration_test` dev-dependency.
- Did not touch the generator, prose gates, or any of the protected docs
  (`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, etc.).
- Recorder service (`html_audio_recorder_service.dart`) left as-is — out of scope (Original
  Audio player only) and it writes to a different flow.
- CocoaPods 1.17.0 installed via Homebrew (dev tooling) to enable iOS integration builds.

## 7. Files changed

- `lib/services/html_audio_player_service.dart` — `EditorAudioAccessModel`, `loadAudio`
  rewrite (write scratch HTML + `loadUrl`), `_deleteScratchHtml`, `dispose`, relative src.
- `lib/screens/edit_stop_screen.dart` — `dispose()` calls `_htmlAudioPlayer.dispose()`.
- `test/editor_audio_access_model_test.dart` — new, pins the access model (AC #6).
- `integration_test/editor_audio_load_test.dart` — new, on-device proof (AC #2/#4/#5).
- `integration_test/mp3_fixture.dart` — new, real base64 MP3 fixture.
- `pubspec.yaml` — added `integration_test` dev-dependency (no version bump).
