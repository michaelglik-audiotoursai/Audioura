# Claude Code Review — v2.1.1+8 Launch Gating (Final, post-fixes)

**Date:** 2026-06-11
**Branch:** `services-migration`
**Head commit:** `a246461`
**Commits in this batch (6 total, oldest first):**
1. `0ecc0b4` — feat(account-deletion): add Delete My Account UI + server call + local data wipe
2. `e00802d` — feat(translate-existing): add Translate button on Listen page + shared TourTranslationHelper service
3. `141d7c8` — feat(attestation): add AppAttestationService + wire X-App-Attestation header into apiHeaders (Phases 1-2-5)
4. `2671197` — fix(account-deletion): P0 — re-read userId before DELETE, close app after wipe, warn on local mode, log before clear
5. `c500857` — feat(attestation): P1 — wire requestBody into all protected POST callers
6. `a246461` — refactor(translation): P2 — shared language constant, isTranslation() helper, single ZIP decode

**Context:** This is a re-review. An earlier draft had issues (Q1-Q8). Commits 4-6 address all P0/P1/P2 fixes from the first review. This doc shows the **final state** of each file.

**pubspec.yaml version:** still `2.1.1+7` — will bump to `+8` after this review passes.

---

## Feature 1 — Account Deletion (`about_screen.dart`)

### What it does
Red "Delete My Account" button in a "Danger Zone" section at the bottom of the About screen. Two-step confirmation. Calls server DELETE, wipes local, closes app.

### Final code — `_deleteAccount()`
```dart
Future<void> _deleteAccount() async {
  try {
    // Re-read user_id from prefs — don't use stale _userId field
    final prefs = await SharedPreferences.getInstance();
    final currentUserId = prefs.getString('user_id') ?? '';
    if (currentUserId.isEmpty || currentUserId.startsWith('Error')) {
      // Abort — show error snackbar
      return;
    }

    // Warn if in local mode
    final serverMode = prefs.getString('server_mode') ?? 'local';
    if (serverMode == 'local') {
      // Show dialog: "This deletes from LOCAL dev server, not production"
      // User can cancel or proceed
      if (proceedLocal != true) return;
    }

    // Call: DELETE /delete-account/<currentUserId> on orchestrator
    final uri = await Endpoints.url(Service.orchestrator, '/delete-account/$currentUserId');
    final headers = await Endpoints.apiHeaders(Service.orchestrator);
    final response = await http.delete(uri, headers: headers).timeout(const Duration(seconds: 15));

    // Only wipe local on 200
    if (response.statusCode == 200) {
      await _wipeLocalData();
      // Show snackbar "Account deleted. App will close."
      await Future.delayed(const Duration(seconds: 2));
      SystemNavigator.pop(); // Close app — fresh state on next launch
    } else {
      // 400/500/other: show error, data preserved, return
    }
  } on Exception catch (e) {
    // Network error: show connectivity error, data preserved
  }
}
```

### Final code — `_wipeLocalData()`
```dart
Future<void> _wipeLocalData() async {
  final prefs = await SharedPreferences.getInstance();
  await DebugLogHelper.addDebugLog('ACCOUNT: Wiping local data...');  // log BEFORE clear
  await prefs.clear();
  try {
    final docsDir = await getApplicationDocumentsDirectory();
    final toursDir = Directory('${docsDir.path}/tours');
    if (await toursDir.exists()) await toursDir.delete(recursive: true);
    final newsDir = Directory('${docsDir.path}/news');
    if (await newsDir.exists()) await newsDir.delete(recursive: true);
  } catch (e) {
    await DebugLogHelper.addDebugLog('ACCOUNT: Error deleting local files: $e');
  }
}
```

### Server contract
- Route: `DELETE /delete-account/<secret_id>` on `Service.orchestrator` (port 5002)
- 200: `{"deleted": true, "rows_removed": N}`
- 400: `{"error": "secret_id required"}`
- 500: `{"error": "deletion_failed", "message": "..."}`
- Idempotent. Server implementation in `tour_orchestrator_service.py` line 1543.

### New import
```dart
import 'package:flutter/services.dart';  // for SystemNavigator.pop()
```

### Design decisions
- `SystemNavigator.pop()` instead of `popUntil(isFirst)` — closes the app entirely so all in-memory state (including `_userId` field) is gone. On next launch, `initState` re-reads from empty prefs and generates a new user_id.
- `_generateUserId` is deterministic from device hardware — same device regenerates same id. That's acceptable: the server record is deleted, so the user starts fresh even with the same device id.
- Local mode warning prevents accidentally deleting from dev server when user meant to delete production account.

---

## Feature 2 — Existing-Tour Translation

### New file: `lib/services/tour_translation_helper.dart`
Static helper class. Extracted from `home_screen.dart`'s `_downloadTranslatedVersions` so both HomeScreen (at download time) and MyToursScreen (translate-after-download) share one code path.

Key elements:
```dart
class TourTranslationHelper {
  /// Canonical language list — single source of truth
  static const availableLanguages = <String, String>{
    'ru': 'Russian', 'zh': 'Chinese', 'fr': 'French',
    'es': 'Spanish', 'de': 'German', 'ja': 'Japanese',
    'ko': 'Korean', 'pt': 'Portuguese', 'it': 'Italian', 'ar': 'Arabic',
  };

  /// Shared predicate for checking translated-tour metadata
  static bool isTranslation(Map<String, dynamic> tour) {
    final val = tour['is_translation'];
    return val == true || val == 'true';
  }

  /// Main entry point — translate + download + save
  static Future<List<String>> downloadTranslatedVersions({
    required int tourId,
    required List<String> languages,
    required String parentEditTourId,
  }) async { ... }

  static Map<String, dynamic>? _extractTranslatedIds(Map<String, dynamic> result) { ... }
  static Future<void> _saveTranslatedTour(...) async { ... }
  static int _countStopsFromArchive(Archive archive) { ... }  // single decode — Q5 fix
}
```

### `my_tours_screen.dart` changes

**UI** — translate icon in tour list trailing row:
```dart
if (!TourTranslationHelper.isTranslation(tour))
  IconButton(
    icon: const Icon(Icons.translate, color: Color(0xFF8e44ad)),
    tooltip: 'Translate',
    onPressed: () => _showTranslateDialog(tour),
  ),
```

**`_showTranslateDialog(tour)`** (~120 lines):
1. Validates `tour_id` is non-null and numeric (shows orange snackbar if not)
2. Shows language selection dialog using `TourTranslationHelper.availableLanguages` + `FilterChip` in `StatefulBuilder`
3. On confirm: shows progress dialog, calls `TourTranslationHelper.downloadTranslatedVersions()`
4. Dismisses progress, shows success/partial-failure snackbar, reloads tour list

### Note on `home_screen.dart`
`_downloadTranslatedVersions` and `_saveTourToMyToursTranslated` still exist in `home_screen.dart` (not refactored to use the helper yet). This avoids a risky refactor on a file with LF line endings. The helper is a parallel path for now — can be consolidated in a future cleanup commit.

---

## Feature 3 — App Attestation (Phases 1-2-5)

### New file: `lib/services/app_attestation_service.dart`
```dart
class AppAttestationService {
  static Future<String?> getToken(Map<String, dynamic> requestBody) async {
    try {
      final nonce = _generateNonce(requestBody);
      if (Platform.isAndroid) return await _getPlayIntegrityToken(nonce);
      if (Platform.isIOS) return await _getAppAttestToken(nonce);
    } catch (e) {
      await DebugLogHelper.addDebugLog('ATTEST: Failed to get token: $e');
    }
    return null;  // never blocks the request
  }

  static String _generateNonce(Map<String, dynamic> requestBody) {
    return sha256.convert(utf8.encode(jsonEncode(requestBody))).toString();
  }

  // Stubs — return null until Phase 3 (Android) / Phase 4 (iOS)
  static Future<String?> _getPlayIntegrityToken(String nonce) async => null;
  static Future<String?> _getAppAttestToken(String nonce) async => null;
}
```

### `endpoints.dart` — `apiHeaders()` change
```dart
static Future<Map<String, String>> apiHeaders(Service s, {Map<String, dynamic>? requestBody}) async {
  final prefs = await SharedPreferences.getInstance();
  final headers = {'Content-Type': 'application/json'};
  final mode = prefs.getString('server_mode') ?? 'local';
  if (mode == 'cloud') {
    final key = (prefs.getString('gateway_api_key') ?? '').trim();
    if (key.isNotEmpty) headers['X-API-Key'] = key;

    // Attestation for cost-bearing endpoints only
    if (_isProtectedService(s) && requestBody != null) {
      final token = await AppAttestationService.getToken(requestBody);
      if (token != null) headers['X-App-Attestation'] = token;
    }
  }
  return headers;
}

static bool _isProtectedService(Service s) {
  return s == Service.orchestrator || s == Service.translation;
}
```

### Callers updated (P1 — commit `c500857`)
All protected POST call sites now pass `requestBody:`:
- `tour_generator_screen.dart` — foreground generate (line ~191)
- `tour_generator_screen.dart` — background generate (line ~1349)
- `translation_service.dart` — translate POST
- `tour_status_service.dart` — tour-status POST

Today: token is always `null` (stubs). When Phase 3/4 ship, these callers automatically get tokens without further changes.

### iOS MethodChannel contract (for Phase 4 hand-off to iOS-AQ)
```
Channel: 'com.audioura.app/attestation'
Method: 'getAssertion'
Args: {'nonce': String}
Returns: String (base64-encoded assertion) or null
```

---

## Files changed (complete list)

| File | Action | Commits |
|------|--------|---------|
| `lib/screens/about_screen.dart` | Modified — deletion UI + logic | `0ecc0b4`, `2671197` |
| `lib/services/tour_translation_helper.dart` | **New** — shared translation helper | `e00802d`, `a246461` |
| `lib/screens/my_tours_screen.dart` | Modified — translate icon + dialog | `e00802d`, `a246461` |
| `lib/services/app_attestation_service.dart` | **New** — attestation service (stubs) | `141d7c8` |
| `lib/config/endpoints.dart` | Modified — attestation in apiHeaders | `141d7c8` |
| `lib/screens/tour_generator_screen.dart` | Modified — requestBody wiring | `c500857` |
| `lib/services/translation_service.dart` | Modified — requestBody wiring | `c500857` |
| `lib/services/tour_status_service.dart` | Modified — requestBody wiring | `c500857` |

---

## Questions for Claude (remaining open items)

**Q1 — Nonce encoding contract:** The nonce is `sha256(jsonEncode(requestBody))`. Dart's `jsonEncode` uses insertion order for Maps. If the gateway re-derives the nonce from the HTTP body (parsing JSON → re-encoding → hashing), key order differences could cause a mismatch. Two options:
- (a) Gateway hashes the raw HTTP body bytes directly (no re-parse) — order doesn't matter.
- (b) Both sides sort keys before encoding.
Which does Claude recommend? (Non-blocking — token is null today.)

**Q2 — DebugLogHelper after prefs.clear():** In `_wipeLocalData`, the log call happens before `prefs.clear()`. But the `catch` block after directory deletion calls `DebugLogHelper.addDebugLog` again — after prefs are cleared. If DebugLogHelper writes to SharedPreferences, that second call re-creates a pref entry. Is this a problem, or does DebugLogHelper write to a file/memory buffer?

**Q3 — home_screen.dart duplication:** `_downloadTranslatedVersions` and `_saveTourToMyToursTranslated` still exist in `home_screen.dart` (not refactored to use `TourTranslationHelper`). This is intentional to avoid touching the LF-line-ending file in this commit batch. Should we consolidate in the next version, or is the duplication acceptable long-term?

---

## Verdict requested

Approve for Ubuntu build, or list specific line-level fixes required.
