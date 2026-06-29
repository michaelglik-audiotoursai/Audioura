# Claude Code Review — v2.1.1+8 Launch Gating (3 commits)

**Date:** 2026-06-11
**Branch:** `services-migration`
**Commits under review:**
- `0ecc0b4` — feat(account-deletion): add Delete My Account UI + server call + local data wipe
- `e00802d` — feat(translate-existing): add Translate button on Listen page + shared TourTranslationHelper service
- `141d7c8` — feat(attestation): add AppAttestationService + wire X-App-Attestation header into apiHeaders (Phases 1-2-5)

**Context:** These three features are launch-gating work for App Store / Play Store submission. Account deletion is a hard policy requirement. Translation-of-existing-tours is a user-value feature. Attestation is a security gate (stubs only — Phase 3/4 not yet implemented).

**Current app version in pubspec.yaml:** `2.1.1+7` (version not bumped yet — pending review approval)

---

## Commit 1 — Account Deletion (`about_screen.dart`)

### New imports added
```dart
import 'package:path_provider/path_provider.dart';
import 'dart:io' show Platform, Directory;
```

### UI addition (in `build()` method)
Red "Danger Zone" container with "Delete My Account" button at the bottom of the About screen, above the copyright text. Uses `ElevatedButton.icon` with `Icons.delete_forever`.

### `_confirmDeleteAccount()` — confirmation dialog
```dart
Future<void> _confirmDeleteAccount() async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Delete Account?'),
      content: const Text(
        'This will permanently delete your account and all data from our servers. '
        'All downloaded tours and articles on this device will also be removed.\n\n'
        'This action cannot be undone.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: () => Navigator.of(context).pop(true),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.red,
            foregroundColor: Colors.white,
          ),
          child: const Text('Delete Permanently'),
        ),
      ],
    ),
  );
  if (confirmed == true) {
    await _deleteAccount();
  }
}
```

### `_deleteAccount()` — server call + local wipe
```dart
Future<void> _deleteAccount() async {
  try {
    await DebugLogHelper.addDebugLog('ACCOUNT: Starting account deletion for $_userId');
    final uri = await Endpoints.url(Service.orchestrator, '/delete-account/$_userId');
    final headers = await Endpoints.apiHeaders(Service.orchestrator);
    final response = await http.delete(uri, headers: headers).timeout(const Duration(seconds: 15));

    if (response.statusCode == 200) {
      await DebugLogHelper.addDebugLog('ACCOUNT: Server deletion successful: ${response.body}');
    } else if (response.statusCode == 400) {
      // ... shows error snackbar, returns without wiping local
      return;
    } else {
      // ... shows error snackbar, returns without wiping local
      return;
    }

    await _wipeLocalData();

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Account deleted successfully.'), backgroundColor: Colors.green),
      );
      Navigator.of(context).popUntil((route) => route.isFirst);
    }
  } on Exception catch (e) {
    // ... shows connectivity error snackbar, data preserved
  }
}
```

### `_wipeLocalData()` — clear prefs + delete directories
```dart
Future<void> _wipeLocalData() async {
  final prefs = await SharedPreferences.getInstance();
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
  await DebugLogHelper.addDebugLog('ACCOUNT: Local data wiped.');
}
```

### Server contract (confirmed)
- Route: `DELETE /delete-account/<secret_id>` on orchestrator (`:5002`)
- 200: `{"deleted": true, "rows_removed": N}`
- 400: `{"error": "secret_id required"}`
- 500: `{"error": "deletion_failed", "message": "..."}`
- Idempotent

### Questions for Claude

**Q1:** After `prefs.clear()`, `DebugLogHelper.addDebugLog(...)` is called. If DebugLogHelper uses SharedPreferences internally, will that call fail or silently re-create a pref entry? Is the ordering correct, or should the log call come before `prefs.clear()`?

**Q2:** `Navigator.of(context).popUntil((route) => route.isFirst)` after deletion — is this sufficient to reset app state? The main screen's `initState()` will re-run and generate a new user_id from SharedPreferences (now empty), so next time it loads it'll create a fresh ID. Confirm this logic chain holds.

**Q3:** The `_userId` field used in the DELETE URL is read at `initState()` time. If the user changes something in About (like server IP) and the state reloads, could `_userId` become stale or empty? Should we re-read it from prefs right before the DELETE call?

---

## Commit 2 — Existing-Tour Translation (`tour_translation_helper.dart` + `my_tours_screen.dart`)

### New file: `lib/services/tour_translation_helper.dart`
A static helper class that extracts the translation+download logic previously only available in `home_screen.dart`. Key methods:
- `downloadTranslatedVersions({tourId, languages, parentEditTourId})` → returns `List<String>` of failed languages
- `_extractTranslatedIds(result)` — handles both server response shapes
- `_saveTranslatedTour(...)` — extracts ZIP, saves to filesystem, adds to SharedPreferences
- `_countStopsFromZip(zipBytes)` — counts stops from tour.json or MP3 count

### `my_tours_screen.dart` changes
- Added import: `import '../services/tour_translation_helper.dart';`
- Added translate icon in the tour list item trailing row:
```dart
if (tour['is_translation'] != true && tour['is_translation'] != 'true')
  IconButton(
    icon: const Icon(Icons.translate, color: Color(0xFF8e44ad)),
    tooltip: 'Translate',
    onPressed: () => _showTranslateDialog(tour),
  ),
```
- Added `_showTranslateDialog(tour)` method (130 lines): validates tour_id is numeric, shows language selection dialog with `FilterChip` widgets in a `StatefulBuilder`, shows progress dialog, calls `TourTranslationHelper.downloadTranslatedVersions()`, shows result snackbar, reloads tour list.

### Questions for Claude

**Q4:** The `is_translation` check uses both `!= true` and `!= 'true'` — this covers both boolean and string-serialized forms from SharedPreferences JSON. Is there a cleaner way, or is this dual-check necessary given that tour metadata is stored as JSON strings in SharedPreferences?

**Q5:** `_saveTranslatedTour` in the helper decodes the ZIP **twice** — once in the main body (to extract files) and once in `_countStopsFromZip` (to count stops). This is the same pattern as `home_screen.dart`. Should we pass the already-decoded `Archive` object to `_countStopsFromZip` instead of re-decoding from bytes? Low priority (performance on small ZIPs is negligible) but worth noting.

**Q6:** The translate dialog has 10 hardcoded languages. Should these come from a shared constant or config, or is hardcoding acceptable for v1 launch? (Same languages are used in the download dialog on the map screen.)

---

## Commit 3 — Attestation Phases 1-2-5 (`app_attestation_service.dart` + `endpoints.dart`)

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
    return null;
  }

  static String _generateNonce(Map<String, dynamic> requestBody) {
    final bodyString = jsonEncode(requestBody);
    return sha256.convert(utf8.encode(bodyString)).toString();
  }

  static Future<String?> _getPlayIntegrityToken(String nonce) async {
    // Stub — Phase 3
    return null;
  }

  static Future<String?> _getAppAttestToken(String nonce) async {
    // Stub — Phase 4
    return null;
  }
}
```

### `endpoints.dart` changes
- Added import: `import '../services/app_attestation_service.dart';`
- Changed `apiHeaders` signature: `apiHeaders(Service s, {Map<String, dynamic>? requestBody})`
- Added attestation logic inside the `mode == 'cloud'` block:
```dart
if (_isProtectedService(s) && requestBody != null) {
  final token = await AppAttestationService.getToken(requestBody);
  if (token != null) headers['X-App-Attestation'] = token;
}
```
- Added `_isProtectedService(Service s)` — returns true for `orchestrator` and `translation`

### Questions for Claude

**Q7:** The `apiHeaders` optional `requestBody` parameter means existing callers (which don't pass it) will never trigger attestation. This is intentional for Phase 1-2 (stubs). When Phase 3 ships, should we also update the callers in `tour_generator_screen.dart` to pass the request body? Or should attestation be opt-in only when the gateway enforces it?

**Q8:** The nonce is `sha256(jsonEncode(requestBody))`. If the JSON serialization order is non-deterministic (Dart's `jsonEncode` of a `Map` uses insertion order), could the gateway's verification fail if it re-serializes the body differently? Should we sort the keys before hashing, or is this a non-issue because the gateway validates the token opaquely (doesn't re-derive the nonce)?

---

## Scope / version

No version bump yet — these three commits should build cleanly on the existing `2.1.1+7` version. Version will be bumped after Claude review approval and successful Ubuntu build.

No `pubspec.yaml` dependency changes (all imports already existed: `crypto`, `path_provider`, `archive`, `http`).

No `AndroidManifest.xml` or `Info.plist` changes.

---

## Bottom line

Three features, three commits. Account deletion is the critical path item (App Store policy). Translation-of-existing is user value. Attestation is infrastructure prep (returns null until Phase 3/4).

Please review for:
1. Correctness of the deletion flow (server-first, local-wipe-only-on-success)
2. State management gaps after deletion (Q1-Q3)
3. Translation helper extraction correctness (Q4-Q6)
4. Attestation architecture (Q7-Q8)
5. Any compile-time issues I may have missed
