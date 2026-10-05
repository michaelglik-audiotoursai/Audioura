# SUBMISSION — LOCAL-581

**Mobile: show WHY a tour failed, offer the suggestion, and make "Try again" actually retry**

- **Agent:** Mac Mini Kiro (Flutter)
- **Branch:** `LOCAL-581-actionable-errors`
- **Base:** `subscribed` = `00805de` (`git merge-base --is-ancestor 00805de HEAD` → exit 0)
- **App version:** `2.4.1+27` (unchanged — LEAD bumps on install)
- **No server changes** (LOCAL-580 owns the server contract). **No GCloud.**

---

## The two defects (Michael, 2026-10-05, app 2.4.1+27 on the local stack)

1. The server returned an actionable message —
   `We could not find enough verified material about "Griffin Museum of Photography" to build a
   tour. Try a broader request — for example a walking tour of the surrounding neighbourhood.` —
   but the app showed the generic **"Unable to generate tour. Please try again."**
2. **"Try again" dismissed the message and started nothing.**

---

## 1. Where the error was shown, and why the server text was lost

**File:** `audio_tour_app/lib/screens/tour_generator_screen.dart`, in `_pollAndAutoDownload(...)`,
the `status == 'error' || status == 'failed'` branch of the status poll.

Before this change the branch built two separate strings:

```dart
String errorMessage = 'Tour generation failed';
String userFriendlyMessage = 'Unable to generate tour. Please try again.';
...
if (status['error'] != null) {
  errorMessage = status['error'].toString();   // <-- the server's words went HERE
}
if (status['user_error'] != null) { userFriendlyMessage = userError['message']...; }
else if (status['user_message'] != null) { userFriendlyMessage = status['user_message']...; }
...
_showServicesErrorDialog(userFriendlyMessage, suggestions);   // <-- but the DIALOG showed THIS
```

The server's `error` text was captured into `errorMessage`, which was only ever written to the
debug log. The dialog rendered `userFriendlyMessage`, which stayed at the generic default unless the
response happened to carry `user_error.message` or `user_message`. The plain `error` field —
exactly what the Griffin Museum response used — was never shown. That is defect #1.

The "Try Again" button in `_showServicesErrorDialog` did only
`Navigator.pop(context); _tourRequestController.clear();` — it dismissed the dialog and *cleared the
box*, starting no job. That is defect #2.

---

## 2–4. The fix

### A pure, testable resolver — `audio_tour_app/lib/utils/tour_error_resolver.dart`

`resolveTourError(Map status)` turns a failed job-status map into a display-ready `ResolvedTourError`:

- **Message precedence (first non-empty wins):** `error` → `message` (LOCAL-580 top-level) →
  `user_error.message` → `user_message` → **generic fallback** `kGenericTourError`
  ("Unable to generate tour. Please try again.") **only when the server sent nothing**
  (`isServerMessage` is then `false`). This is why the server's own words now reach the user.
- **Suggestion (LOCAL-580 contract):** parses `suggestion {label, request, tour_type}`. A missing or
  malformed suggestion yields `null` — the button is simply not shown, no crash on a missing field.
  (Until LOCAL-580 lands, there is no `suggestion`, so no button.)
- **Retryability:** `error_code venue_no_verifiable_content` ⇒ `canRetry = false`.

### Wiring — `tour_generator_screen.dart`

- The error branch now calls `resolveTourError(status)` (line ~409). The long-standing
  `error_type` / "no stops" heuristics are kept **only** as the fallback when the server sent no
  message (`!resolved.isServerMessage`), so no previously-handled case regresses.
- `_showServicesErrorDialog` → **`_showTourErrorDialog(ResolvedTourError)`** (def line ~964), which:
  - renders `resolved.message` (the server's text when present);
  - shows a green **suggestion button** labelled `suggestion.label` that starts that generation
    (only when a suggestion exists);
  - shows a context-aware primary action:
    - **"Try again"** when `canRetry` — re-submits the identical request; **disabled while a job
      runs** (`_isGenerating`) or if there is no snapshot yet;
    - **"Edit request"** when `!canRetry` (e.g. `venue_no_verifiable_content`) — returns the user to
      the form with their text kept.

### Retry re-submits the IDENTICAL request

`_generateTour` snapshots the validated request into `_LastTourRequest` (line ~216), captured **after**
the duplicate-check gate so a retry never re-triggers the duplicate dialog. The snapshot holds the
raw request text, stop mode, user stops, stop-count field, and selected languages.

- `_retryLastTour()` (line ~1061) restores the form from the snapshot and calls `_generateTour()`, so
  the request body is rebuilt byte-for-byte from the same inputs (location text, tour type via
  `parseTourRequest`, `total_stops`, `user_stops`, languages).
- `_startSuggestedTour(suggestion)` (line ~1077) sets the request text to the suggested request,
  keeps the **same stop count**, and submits.
- `_editRequest()` (line ~1092) refocuses the form and shows a hint snackbar; the text is untouched.

### Incidental fix

The 10-second background-refresh `Timer.periodic` created in `initState` was never cancelled — it
outlived the screen (a leak) and made widget tests fail with "A Timer is still pending". It is now
stored as `_refreshTimer` and cancelled in `dispose()`.

---

## 5. Tests, analyze, build

### Unit tests — `audio_tour_app/test/tour_error_resolver_test.dart` (14 tests)
Server message shown verbatim (the Griffin Museum string); generic fallback only when the server
sent nothing; `error` wins over `message`/`user_message`; blank `error` falls through; full / partial
/ malformed / non-map suggestion handling; `venue_no_verifiable_content` not retryable; legacy
`user_error.suggestions` collected.

### Widget tests — `audio_tour_app/test/tour_error_actionable_test.dart` (5 tests)
Drive the **real** `TourGeneratorScreen` through its submit → poll → error path, with `http`
intercepted by `MockClient` via `http.runWithClient` and the app in **local** server mode (so no
attestation and no live server are touched). The MockClient records POST bodies to
`/generate-complete-tour` and serves scripted `/status/<id>` error payloads. Covered:

1. server error shown verbatim; generic string absent; **"Try again"** present (defects #1, #2);
2. generic fallback shown only when the server sent no message;
3. **"Try again" starts a SECOND job with a byte-identical request body** (asserts
   `generateBodies[1] == generateBodies[0]`, `total_stops == 7`);
4. **suggestion button starts a new job** with `location == "walking tour of Winchester MA"` and the
   **same** `total_stops == 12`;
5. `venue_no_verifiable_content` shows **"Edit request"** (not "Try again"), starts **no** second
   job, and keeps the user's text.

### Results
- `flutter analyze` on the four touched files: **no errors, no warnings.** (The project baseline has
  ~1386 pre-existing issues in unrelated orphan files — `audio_handler.dart`, `tour_service.dart`,
  `widgets/map_page.dart`, `subscription_management_screen.dart` — none touched here.)
- `flutter test`: **233 passing.** The only failures are the pre-existing `local109_swipe_e2e_test`
  cases, which require a live backend on `:5102` (`SocketException: Connection refused` on this
  machine). That file was not touched by this change.

### iOS build (not installed)
```
. "$HOME/Audioura/build_secrets.env"
flutter build ios --release --dart-define=GATEWAY_API_KEY="$GATEWAY_API_KEY"
```
Result: `✓ Built build/ios/iphoneos/Runner.app (29.9MB)` (signed with development team
`4HGRU6TKGQ`).

**Artifact path:**
`/Volumes/AudiouraSSD/audioura-worktrees/LOCAL-581/audio_tour_app/build/ios/iphoneos/Runner.app`

**Not installed** — LEAD installs in place with `devicectl` (D606).

---

## Files changed
- `audio_tour_app/lib/utils/tour_error_resolver.dart` (new — pure resolver)
- `audio_tour_app/lib/screens/tour_generator_screen.dart` (wire resolver, actionable dialog, retry /
  suggestion / edit, snapshot, timer cancel)
- `audio_tour_app/test/tour_error_resolver_test.dart` (new — 14 unit tests)
- `audio_tour_app/test/tour_error_actionable_test.dart` (new — 5 widget tests)
