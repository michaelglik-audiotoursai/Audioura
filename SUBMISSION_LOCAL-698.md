# LOCAL-698 — Player: tapping another stop must stop the one playing (never two stops at once)

**Branch:** `LOCAL-698-one-stop-at-a-time`
**Base:** `subscribed` (`26364ceb` — "Bump app to 2.4.19+55 (697 + 699 merged)")
**Build:** `2.4.19+55` → **`2.4.19+56`**

## The report
Michael, 2026-10-15 (Pixel-4, a **downloaded Russian translation**): tapping a
different stop while one is already speaking starts the second **without**
stopping the first — both play at once. This had been fixed before (BETA-1,
Yury Makedonov) and regressed.

## Root cause
Every stop in a tour/news page is rendered server-side as its own
`<audio controls>` element (see `tour_generation_modernized.py`,
`translation-service/translation_service.py`, `news_processor_service.py`).
Each element therefore carries its **own native play button**.

The player page's in-page JavaScript (built in `tour_player_screen.dart`) only
*wraps the app's helper functions* — `window.goToStop`, `nextStop`,
`previousStop`, and the `play` **reporting** listeners that notify Flutter which
stop is active. None of those paths pause the other `<audio>` elements. When the
listener taps a stop's **native** control, the browser calls that element's
`HTMLMediaElement.play()` **directly** — bypassing every app helper — so nothing
pauses the element already playing. Two stops overlap.

## Why the old (BETA-1) fix did not hold
Two independent reasons:

1. **Wrong layer.** The earlier fix added "pause the others first" *inside the
   app's JS helpers* (`playAudio` / `goToStop` / `playAudioByIndex`). A native
   control tap never calls those helpers — it calls the element's own `.play()`
   — so the guard was simply never reached. Any later page/markup change that
   routed a tap straight to a native control (or any stop rendered as a plain
   `<audio controls>`) silently reopened the bug.
2. **Already-downloaded content.** A downloaded tour, and **every translation**
   (each translation is its own pre-generated HTML file with a different
   name/path), ships the HTML to the device at download time. A server-side or
   Dart-only change cannot retroactively rewrite a file the listener already
   has — which is exactly the artifact in Michael's report (a *downloaded*
   Russian translation).

## The fix — one shared controller, enforced at the lowest level
`audio_tour_app/lib/services/single_playback_controller.dart` holds a small,
self-contained JavaScript controller (`kSinglePlaybackControllerJs`) that
**patches `HTMLMediaElement.prototype.play` on the page itself**. After the
patch, *every* play path — a native control tap, `window.playAudio()`,
`goToStop()`, `playAudioByIndex()`, autoplay, a voice command, anything — first
calls `pauseAllExcept(target)`, which pauses and rewinds every other
`audio`/`video` element **before** the chosen one starts. That is the core
invariant: **at most one media element is ever non-paused.**

Rapid double-taps are made safe with a **monotonic sequence token**
(`__audiouraPlaySeq`): every accepted `play()` bumps it and becomes the single
owner; an older request whose `play()` promise resolves late finds a newer owner
in charge and pauses itself, so the **latest** tap always wins and two stops
never coexist. A capture-phase `play` event listener is a belt-and-braces
collapse to a single player for any path a future engine quirk might introduce.
The script is **idempotent** (guarded by `__audiouraSinglePlayInstalled`), so it
can be injected repeatedly with no ill effect.

### Where it is wired in
Both WebView-based players inject the controller on **every** page load:

- `audio_tour_app/lib/screens/tour_player_screen.dart`
- `audio_tour_app/lib/screens/news_player_screen.dart`

Each injects it two ways, for defence in depth:

1. `addUserScript(..., injectionTime: AT_DOCUMENT_START)` in `onWebViewCreated`
   — installs the patch **before any page script or autoplay can run**, on every
   navigation.
2. An idempotent `evaluateJavascript(kSinglePlaybackControllerJs)` in
   `onLoadStop` — a safety net ensuring the patch is present before anything can
   auto-start.

Because the guard is injected by the Flutter shell at runtime (not baked into
the tour HTML), it **also fixes tours and translations that were already
downloaded** before this build — closing reason (2) above. And because it
patches the prototype rather than wrapping app helpers, it covers native control
taps — closing reason (1).

## Files changed
- `audio_tour_app/lib/services/single_playback_controller.dart` *(new)* — the controller JS + doc.
- `audio_tour_app/lib/screens/tour_player_screen.dart` — inject at document-start + onLoadStop.
- `audio_tour_app/lib/screens/news_player_screen.dart` — inject at document-start + onLoadStop.
- `audio_tour_app/test/single_playback_controller_test.dart` *(new)* — proof test.
- `audio_tour_app/pubspec.yaml` — build bump `2.4.19+55` → `2.4.19+56`.

## Tests
`audio_tour_app/test/single_playback_controller_test.dart` — **5/5 pass**.

- **Dart contract (4 tests):** pins that the shipped constant patches
  `HTMLMediaElement.prototype.play`, selects `audio, video` and pauses the
  others, carries the monotonic sequence token, and is idempotent.
- **Real-JS behaviour (1 test, executed in Node):** the test reads the **actual
  shipped JS** out of `single_playback_controller.dart`, runs it in Node against
  a faithful `HTMLMediaElement`/`document` mock where a stop's native control
  calls `element.play()` directly (the exact path that regressed), then asserts
  the scenario from the ticket:
  - start stop 1, **tap stop 3 → player count = 1**, and the one playing is
    stop 3; and
  - a rapid double-tap (stop 2 then stop 4) also collapses to **player count = 1**
    with the latest (stop 4) the one playing.

Run: `cd audio_tour_app && flutter test test/single_playback_controller_test.dart`

> Note: `flutter test` cannot host a real WebView, so the Node harness exercises
> the real JS directly. It is skipped (with the Dart-contract assertions still
> covering the shim) only if `node` is absent; here it ran on node v26.5.0.

## Build verification
- `flutter analyze` on the changed files: **0 errors, 0 warnings** (68
  pre-existing `info`-level `prefer_const` lints only, none introduced here).
- **Android:** `flutter build apk --debug` → `✓ Built build/app/outputs/flutter-apk/app-debug.apk`.
- **iOS:** `flutter build ios --debug --no-codesign` → `✓ Built build/ios/iphoneos/Runner.app`.

## Status: unproven on-device
The one-stop invariant is proven against the real shipped JavaScript (Node
harness) and both platforms compile. It has **not** yet been exercised on a
physical Pixel-4 with a downloaded translation; that live confirmation is the
remaining step.
