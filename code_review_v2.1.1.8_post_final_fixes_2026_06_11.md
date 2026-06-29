# Claude Code Review — v2.1.1+8 Post-Final Fixes (commit `4338d99`)

**Date:** 2026-06-11
**Branch:** `services-migration`
**Head commit:** `4338d99`
**Prior review:** `code_review_v2.1.1.8_final_2026_06_11.md` — approved with two required changes.
**This commit:** Applies those two changes plus a comment annotation (Q3).

**pubspec.yaml version:** still `2.1.1+7` — will bump to `+8` after this review passes.

---

## Change 1 — Un-attest `/tour-status` (`tour_status_service.dart`)

**Problem identified in review:** `/tour-status` is a frequent, cheap status write (called on every generation state transition). Attaching Play Integrity tokens to it would burn API quota and add latency for a non-validated endpoint. The gateway only validates tokens on `/generate-complete-tour` and `/translate-with-audio`.

**Fix:** Removed `requestBody:` parameter from the `apiHeaders()` call in `tour_status_service.dart`. The status endpoint now gets standard headers (Content-Type + API key in cloud mode) but no attestation token.

**Before:**
```dart
final statusBody = {'tour_id': tourId, 'status': status};
final response = await http.post(
  await Endpoints.url(Service.orchestrator, '/tour-status'),
  headers: await Endpoints.apiHeaders(Service.orchestrator, requestBody: statusBody),
  body: jsonEncode(statusBody),
);
```

**After:**
```dart
final statusBody = {'tour_id': tourId, 'status': status};
final response = await http.post(
  await Endpoints.url(Service.orchestrator, '/tour-status'),
  headers: await Endpoints.apiHeaders(Service.orchestrator),
  body: jsonEncode(statusBody),
);
```

**Impact:** No behavioral change today (token is null). Prevents a latent quota/latency bug when Phase 3 ships.

---

## Change 2 — Platform-guard app close after deletion (`about_screen.dart`)

**Problem identified in review:** `SystemNavigator.pop()` cleanly exits on Android but on iOS it can leave a black screen (Apple discourages self-termination). The deletion flow needs different behavior per platform.

**Before:**
```dart
if (mounted) {
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text('Account deleted. App will close.'), backgroundColor: Colors.green),
  );
  await Future.delayed(const Duration(seconds: 2));
  SystemNavigator.pop();
}
```

**After:**
```dart
if (mounted) {
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text('Account deleted successfully.'), backgroundColor: Colors.green),
  );
  await Future.delayed(const Duration(seconds: 2));
  if (Platform.isAndroid) {
    SystemNavigator.pop();
  } else {
    // iOS: navigate to root — initState re-runs, prefs are empty, fresh user_id generated
    Navigator.of(context).popUntil((route) => route.isFirst);
  }
}
```

**Android behavior:** App closes. On next launch, `initState` runs from scratch against empty SharedPreferences → generates new user_id.

**iOS behavior:** Pops to root screen. The main screen's `_buildBody()` switch recreates child screens → `initState` re-runs → reads empty prefs → fresh state. No black screen. (Must verify on real iOS device before App Store submission.)

**Note:** `Platform.isAndroid` is already importable from the existing `import 'dart:io' show Platform, Directory;` at the top of the file.

---

## Change 3 — Sync comment in `home_screen.dart`

**Per Q3 recommendation:** Added a one-line comment above `_downloadTranslatedVersions` in `home_screen.dart`:

```dart
// ⚠️ Keep in sync with TourTranslationHelper.downloadTranslatedVersions() until consolidated.
```

This flags the duplication for the next person editing either copy. No logic change.

---

## Files changed

| File | Change | Lines |
|------|--------|-------|
| `lib/services/tour_status_service.dart` | Removed `requestBody:` from `apiHeaders()` call | ~1 line |
| `lib/screens/about_screen.dart` | Platform-branched app close (Android exit / iOS popUntil) | +6 / -4 |
| `lib/screens/home_screen.dart` | Added sync comment | +1 |

---

## Questions for Claude

**Q1:** On iOS, after `Navigator.of(context).popUntil((route) => route.isFirst)`, the root screen (`MainScreen`) is still mounted — its `initState` does **not** re-run (it was never disposed). The child screens (`HomeScreen`, `MyToursScreen`, etc.) will be rebuilt via `_buildBody()` and their `initState` will fire, reading empty prefs. But `MainScreen` itself may hold stale state (e.g., the tab index). Is this acceptable, or should we force a full widget tree rebuild (e.g., via a `Key` change on `MaterialApp`)? Severity: low — tab index defaulting to 0 is fine, but confirm no stale references leak.

**Q2:** The snackbar message changed from "App will close." to "Account deleted successfully." — should the iOS message be different (e.g., "Account deleted. Please restart the app for a clean state.") to set expectations that the app didn't fully close?

---

## Verdict requested

This is a minimal, targeted fix commit applying the two changes requested by the prior review. Approve for version bump to `2.1.1+8` and Ubuntu build.
