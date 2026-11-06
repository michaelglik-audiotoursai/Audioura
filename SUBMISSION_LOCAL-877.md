# SUBMISSION — LOCAL-877 (Sophia's app defects). Code by Kiro; finished and verified by LEAD after the Kiro session stalled at 4 h on the Android harness.

## What changed
- `main_screen.dart`: on resume, a tab that is not at its root, or has any live tour session, is NEVER reset. Data is refreshed in place. This was the cause of "it takes me back to your page" and of "the audio stops when I reopen".
- `player_session.dart` (new): remembers the current tour, stop and position; offers "Resume" after a cold start.
- `persistent_player_bar.dart` + `player_bar_js.dart` (new): a bottom bar on every screen while a tour plays or is paused mid-stop. It has a large play/pause, previous/next stop, the title and progress; tapping it opens the tour.
- `swipe_feedback_widget.dart` + `stop_feedback_service.dart`: after a choice the thumbs collapse to "✓ thanks · change"; they can be dismissed and the answer changed (an update, not a duplicate); they never cover the bar.

## Verification
- `test/player_resume_local877_test.dart`: 18 pass.
- Full Flutter suite: 1291 pass, 8 fail. Those are the same 8 that fail on the base (known since LOCAL-868).
- `flutter analyze` on the changed files: 0 errors.
- **iOS simulator integration (real background/foreground): PASS.**
  - Markers: PLAYING_STOP1 → RESUMED → SAME_STOP_STILL_PLAYING → NEXT_STOP2_PLAYING → PAUSED_FROM_BAR.
  - Screenshots: `submission_screens/LOCAL-877/ios_*`.
- **Android:**
  - the debug APK builds and installs on the emulator;
  - stop 1 plays (markers PLAYING_STOP1, READY_FOR_BACKGROUND; screenshots `android_1/2`);
  - **the harness hangs after backgrounding**: the integration-test driver does not resume. That is likely a test-harness limitation on Android, but it means the Android resume is **NOT proven**.
- Nothing was installed on any real phone. A Pixel 4 is attached to the Mac; it was never targeted.
