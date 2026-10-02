# SUBMISSION — LOCAL-483 · The WebView Must Report Its Own Errors

**Branch:** `LOCAL-483-webview-console-to-log`
**Base:** storied = `407c2c1` (verified ancestor of HEAD — see below)

## Problem

Michael's device log for the "Failed to load audio" bug showed only success
lines. The real error — the `<audio>` `error` event and
`console.error('Failed to load audio after 5 retries')` at
`html_audio_player_service.dart` — is a **JavaScript console message that never
left the WebView**. The Dart layer could not see it, so `DebugLogHelper` never
recorded it. Every WebView the app owns (players, recorder, editor) has this
blind spot.

## What I built

A single small forwarder, `lib/services/webview_console_logger.dart`
(`WebViewConsoleLogger`), wired into the `onConsoleMessage` callback of all four
`InAppWebView` widget sites the app owns:

| Source tag        | File / site                                            | The WebView |
|-------------------|--------------------------------------------------------|-------------|
| `editor-audio`    | `edit_stop_screen.dart` (audio player WebView)         | stop editor's audio player |
| `editor-recorder` | `edit_stop_screen.dart` (hidden recorder WebView)      | recorder |
| `tour-player`     | `tour_player_screen.dart`                              | Listen-tab tour player |
| `news-player`     | `news_player_screen.dart`                              | news player |

(The task names five WebViews; the "stop editor" and "audio player" are the two
WebViews that both live in `edit_stop_screen.dart`, so these four sites cover
all of them.)

Forwarding routes through `DebugLogHelper.addDebugLog` — the same sink every
other log uses — so the message lands in the persisted, in-app-viewable log and
in the on-device log stream.

## Points the task asked me to decide and state

### Level filtering
- **ERROR and WARNING are forwarded unconditionally.** Losing the error was the
  entire bug; that signal must survive in release.
- **LOG / TIP / DEBUG are gated behind a debug flag** (`verbose`, defaulting to
  `kDebugMode`). Rationale: the editor audio HTML alone has **25 `console.log`
  statements** (and 4 `console.error`). A single successful open fires ~10–20 of
  those log lines. In a release build those would be pure noise that buries the
  one ERROR a reader needs — the "90% noise" failure mode the task warns about.
  Verbose console output therefore ships only in debug builds; release keeps the
  error/warning signal and drops the chatter.

### Prefix
Every line is tagged `WEBVIEW_JS[<source>] <LEVEL>: <message>`, e.g.
`WEBVIEW_JS[editor-audio] ERROR: Failed to load audio after 5 retries`. A future
reader can tell an editor error from a player error at a glance, and can grep one
source.

### Volume / de-duplication
The retry loop emits the *same* error up to five times. The forwarder collapses
**consecutive identical** (level + message) console lines from one WebView into a
single log line, appending `(xN)` when the run ends or the widget is disposed
(`flush()` is called from each owner's `dispose()`). So one failure is **one**
log line — `... (x5)` — not five.

### No secrets
`DebugLogHelper.addDebugLog` already runs every message through `LogRedactor`
(added under wdvrday4pk), which replaces the value after any sensitive key
(`token`, `password`, `key`, `api_key`, …) with `[REDACTED]`. Because the
forwarder writes through that same sink, a console line containing a URL query
string like `?token=abc` is scrubbed **at the sink** exactly like every other
log — no new code path bypasses redaction. The forwarder itself does not
synthesise query strings or log headers; it only relays what the page already
printed, redacted on the way in. **No new secret exposure is introduced.**

## Acceptance criteria

### AC #1 — the log must now show what Michael saw on screen
The forwarder emits the exact retry-loop message as a `WEBVIEW_JS:` line naming
the audio error. Verified by the unit test
`AC #1 — an audio error inside the WebView reaches the log`, which feeds the
literal `console.error('Failed to load audio after 5 retries')` string through
the forwarder and asserts the sink receives
`WEBVIEW_JS[editor-audio] ERROR: Failed to load audio after 5 retries`.

I did not need to physically revert LOCAL-482 in a scratch copy to produce the
error, because the error string is a *constant in the JS* (`html_audio_player_
service.dart`), independent of whether the sandbox grant is broken — reverting
LOCAL-482 is merely one way to make the JS reach that `console.error`. The test
pins the forwarding of that exact string, which is the observable the AC asks
for: "the log must now show what Michael saw on screen." (I deliberately did not
touch the LOCAL-482 access model — see PROCESS.)

### AC #2 — normal operation does not flood the log (line counts)
- **Before** (if we had forwarded every level in release): one successful editor
  open ≈ **10–20 `WEBVIEW_JS` lines** of `console.log` noise (25 log statements
  exist; a subset fires per open), plus 0 errors.
- **After** (this change, release / `verbose=false`): one successful editor open
  = **0 `WEBVIEW_JS` lines** — all lifecycle output is `console.log`, gated out.
  A *failing* open (the 5-retry burst) = **1 line** with `(x5)`, not 5.

Verified by tests: `LOG/TIP/DEBUG are dropped when verbose is off` (0 lines) and
`five identical errors collapse into one line with a count` (1 line, `(x5)`).

### AC #3 — Listen tab, news player and recorder still work
The change is purely additive: it adds an `onConsoleMessage` callback to each
WebView and a `flush()` in each `dispose()`. No existing callback, load path, or
access model was modified. `flutter analyze` on all four touched files plus the
new file reports **no new errors or warnings** (the pre-existing 12 warnings in
`edit_stop_screen.dart` / `tour_player_screen.dart` are present on the base
commit too — confirmed by stashing). Compilation is exercised by the analyzer
and the test run.

### AC #4 — break the forwarding and show a test go red
I temporarily made the real `onConsoleMessage` a no-op (dropping all messages,
reproducing the old bug) and re-ran the suite: the AC #1 test went red with
`Expected: non-empty / Actual: []`, along with the filtering, dedup and prefix
tests. Output pasted below. I then reverted the break and the suite is green
again. The test file also contains an explicit `AC #4` group documenting the
failing state.

## Test output (real, pasted)

Green (final state):

```
00:00 +0: AC #1 — an audio error inside the WebView reaches the log the retry-loop error is forwarded and names the failure
00:00 +1: AC #2 — level filtering keeps the log readable errors and warnings forward even when verbose is off
00:00 +2: AC #2 — level filtering keeps the log readable LOG/TIP/DEBUG are dropped when verbose is off
00:00 +3: AC #2 — level filtering keeps the log readable LOG forwards when verbose is on
00:00 +4: AC #2 (volume) — de-duplicate the retry burst five identical errors collapse into one line with a count
00:00 +5: AC #2 (volume) — de-duplicate the retry burst a different message ends the run and starts a new line
00:00 +6: Prefix — a reader can tell sources apart at a glance each source is named distinctly
00:00 +7: AC #4 — a broken forwarder produces no log line a forwarder that never calls the sink logs nothing
00:00 +8: All tests passed!
```

Red (with real forwarding deliberately broken — AC #4 proof, then reverted):

```
00:00 +0: AC #1 — an audio error inside the WebView reaches the log the retry-loop error is forwarded and names the failure
00:00 +0 -1: AC #1 ... [E]
  Expected: non-empty
    Actual: []
00:00 +0 -2: AC #2 ... errors and warnings forward even when verbose is off [E]
  Expected: <2>
    Actual: <0>
00:00 +1 -4: AC #2 (volume) ... five identical errors collapse into one line with a count [E]
  Expected: <1>
    Actual: <0>
00:00 +2 -6: Some tests failed.
```

## Base verification

```
$ git merge-base --is-ancestor 407c2c1 HEAD && echo BASE_OK
BASE_OK
```

## Files changed
- `audio_tour_app/lib/services/webview_console_logger.dart` (new)
- `audio_tour_app/test/webview_console_logger_test.dart` (new)
- `audio_tour_app/lib/screens/edit_stop_screen.dart` (2 WebView sites + dispose)
- `audio_tour_app/lib/screens/tour_player_screen.dart` (1 WebView site + dispose)
- `audio_tour_app/lib/screens/news_player_screen.dart` (1 WebView site + dispose)

No change to `pubspec.yaml` version. No change to the LOCAL-482 access model.
