# Code Review Request — v2.1.1+1
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commit:** `a877a50` on branch `services-migration`
**Reviewing:** Fixes applied in response to `claude_review_v1.2.9.72_response_2026_06_03.md`

---

## What Changed in This Build

This build implements all four actionable fixes from the Claude v1.2.9+72 review, plus a major version bump:

1. **Q1 — Cloud path prefix fix** (`endpoints.dart`, `about_screen.dart`)
2. **Q2 — Remove unused `serverIp` parameter** (`home_screen.dart`)
3. **Q3 — Rename `processUri2`** (`home_screen.dart`)
4. **Q5 — DEV ONLY warning comments** (`direct_db_update.dart`, `api_tester.dart`)
5. **Version bump** `1.2.9+72` → `2.1.1+1` (major restart)

Q4 (multiple SharedPreferences.getInstance() calls) confirmed as non-issue — no code change made.

---

## File 1: `lib/config/endpoints.dart` (Q1 fix)

```dart
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

enum Service {
  orchestrator,    // :5002
  userDb,          // :5003
  mapDelivery,     // :5005
  news,            // :5012
  newsletter,      // :5017
  customAudio,     // :5023
  tourIdResolution,// :5025
  translation,     // :5030
}

class Endpoints {
  static const _localPorts = {
    Service.orchestrator: 5002,
    Service.userDb: 5003,
    Service.mapDelivery: 5005,
    Service.news: 5012,
    Service.newsletter: 5017,
    Service.customAudio: 5023,
    Service.tourIdResolution: 5025,
    Service.translation: 5030,
  };

  // Path prefix appended to cloud_base_url for each service.
  // Used when a single gateway/domain routes all services.
  static const _cloudPaths = {
    Service.orchestrator: '/orchestrator',
    Service.userDb: '/user',
    Service.mapDelivery: '/map-delivery',
    Service.news: '/news',
    Service.newsletter: '/newsletter',
    Service.customAudio: '/custom-audio',
    Service.tourIdResolution: '/tour-id',
    Service.translation: '/translation',
  };

  /// Returns the base URL for [s] based on current server_mode.
  /// Local:  http://<server_ip>:<port>
  /// Cloud (interim, bare per-service host):  <cloud_base_url>   (no prefix)
  /// Cloud (gateway, cloud_use_path_prefixes=true):  <cloud_base_url><path_prefix>
  static Future<String> base(Service s) async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('server_mode') ?? 'local';
    if (mode == 'cloud') {
      final cloudBase = (prefs.getString('cloud_base_url') ?? '').trim();
      if (cloudBase.isEmpty) throw StateError('Cloud base URL not set — open About and enter it.');
      // Interim (bare per-service host): prefixes OFF by default.
      // Enable when a gateway that routes+strips path prefixes is deployed.
      final usePrefix = prefs.getBool('cloud_use_path_prefixes') ?? false;
      return usePrefix ? '$cloudBase${_cloudPaths[s]}' : cloudBase;
    }
    final ip = prefs.getString('server_ip') ?? Config.defaultServerIp;
    return 'http://$ip:${_localPorts[s]}';
  }

  /// Convenience: returns a fully-formed [Uri] for [s] + [path].
  static Future<Uri> url(Service s, String path) async =>
      Uri.parse('${await base(s)}$path');
}
```

**Q1 — What changed:** Added `cloud_use_path_prefixes` boolean flag (defaults `false`).
- `false` (default/interim): `base()` returns bare `cloudBase` — no prefix appended. Works against bare Cloud Run per-service hosts like `https://map-delivery-xxx.run.app`.
- `true` (future/gateway): `base()` appends `_cloudPaths[s]` — e.g. `/map-delivery`. Correct when `audioura.com` gateway routes by prefix and strips before forwarding.

**Questions for Claude:**
1. When `usePrefix = true`, the expression is `'$cloudBase${_cloudPaths[s]}'`. `_cloudPaths[s]` returns `String?` (nullable map lookup). In practice all 8 enum values are in the map so it will never be null — but Dart will silently interpolate `null` as the string `"null"` if a value were missing. Should we add a non-null assertion `_cloudPaths[s]!` or a fallback `_cloudPaths[s] ?? ''` to make the intent explicit and prevent a silent bug if a new Service is added without a corresponding `_cloudPaths` entry?

---

## File 2: `lib/screens/about_screen.dart` (Q1 UI)

**Only the changed section is shown — the rest of the file is unchanged.**

State field added:
```dart
bool _usePathPrefixes = false; // true = gateway mode (prefix routing)
```

Load in `_loadAppInfo()`:
```dart
final savedUsePathPrefixes = prefs.getBool('cloud_use_path_prefixes') ?? false;
// ... inside setState():
_usePathPrefixes = savedUsePathPrefixes;
```

New method:
```dart
Future<void> _setUsePathPrefixes(bool value) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool('cloud_use_path_prefixes', value);
  setState(() { _usePathPrefixes = value; });
  await DebugLogHelper.addDebugLog('ABOUT: Gateway path routing set to: $value');
}
```

Checkbox added inside the `if (_serverMode == 'cloud')` column (after the existing warning text):
```dart
const SizedBox(height: 8),
Row(
  children: [
    Checkbox(
      value: _usePathPrefixes,
      onChanged: (val) => _setUsePathPrefixes(val ?? false),
    ),
    const Expanded(
      child: Text(
        'Use gateway path routing (enable only when audioura.com gateway is deployed)',
        style: TextStyle(fontSize: 12),
      ),
    ),
  ],
),
```

**Questions for Claude:**
2. The checkbox is only visible when `_serverMode == 'cloud'`. However the `cloud_use_path_prefixes` flag persists in SharedPreferences regardless. If a user enables the flag, switches back to local mode, and later someone adds new code that checks `cloud_use_path_prefixes` without checking `server_mode` first — it could silently apply prefixes in local mode. Should we either (a) reset `cloud_use_path_prefixes` to `false` when switching to local mode in `_setServerMode()`, or (b) in `Endpoints.base()` only read the flag inside the `mode == 'cloud'` block (which it already does)? Is the current implementation safe?

---

## File 3: `lib/screens/home_screen.dart` (Q2 + Q3)

### Q2 — Removed unused `serverIp` parameter from `_downloadTranslatedVersions`

**Before:**
```dart
Future<List<String>> _downloadTranslatedVersions(
  int tourId,
  List<String> languages,
  String serverIp,        // ← was unused inside the method
  String parentEditTourId,
) async {
```

**After:**
```dart
Future<List<String>> _downloadTranslatedVersions(
  int tourId,
  List<String> languages,
  String parentEditTourId,
) async {
```

Both callers updated:

`_downloadSingleTourSilent`:
```dart
// Before:
return await _downloadTranslatedVersions(tourId, nonEnglish, serverIp, parentEditTourId);
// After:
return await _downloadTranslatedVersions(tourId, nonEnglish, parentEditTourId);
```

`_downloadSingleTour`:
```dart
// Before:
final failures = await _downloadTranslatedVersions(tourId, nonEnglishLanguages, serverIp, parentEditTourId);
// After:
final failures = await _downloadTranslatedVersions(tourId, nonEnglishLanguages, parentEditTourId);
```

**Questions for Claude:**
3. Both callers previously passed `serverIp` as a local variable. That variable no longer exists in either caller after the v1.2.9+72 migration. The code compiled and ran because Dart would have thrown a compile error if `serverIp` were used — confirming it was truly dead. Just asking for confirmation: is there any edge case where removing the `serverIp` parameter could affect the translation download flow? The method body uses only `Endpoints.url()` internally.

---

### Q3 — Renamed `processUri2` → `processUri` in `_processNewsletterUrl`

**Before (in `_processNewsletterUrl`):**
```dart
final processUri2 = await Endpoints.url(Service.newsletter, '/process_newsletter');
final requestUrl = processUri2.toString();
```

**After:**
```dart
final processUri = await Endpoints.url(Service.newsletter, '/process_newsletter');
final requestUrl = processUri.toString();
```

Note: `_processNewsletterWithUrl` (a separate method) also uses a local variable named `processUri` — no conflict since they are in different method scopes.

**Questions for Claude:**
4. No functional change — purely cosmetic. Confirming there is no naming conflict: `processUri` in `_processNewsletterWithUrl` and `processUri` in `_processNewsletterUrl` are in separate method scopes. Is the rename correct and complete?

---

## File 4 & 5: DEV ONLY warning comments (Q5)

### `lib/services/direct_db_update.dart`
```dart
// ⚠️ DEV ONLY — NEVER expose on Cloud Run. These endpoints issue raw SQL directly
// to the database. Must never have public ingress. Guard: uses server_ip directly
// (unreachable off-WiFi in cloud mode) — do NOT migrate to Endpoints resolver.
import 'package:http/http.dart' as http;
```

### `lib/services/api_tester.dart`
```dart
// ⚠️ DEV ONLY — NEVER expose on Cloud Run. Tests raw SQL/postgres endpoints
// that must never have public ingress. Do NOT migrate to Endpoints resolver.
import 'package:http/http.dart' as http;
```

**Questions for Claude:**
5. Claude's previous review suggested adding a runtime guard: **no-op when `server_mode != 'local'`** as defense-in-depth. We only added header comments. Should we implement the runtime guard in both files? For example, at the top of `DirectDbUpdate.updateTourStatus()` and `ApiTester.testAllEndpoints()`:
   ```dart
   final prefs = await SharedPreferences.getInstance();
   if ((prefs.getString('server_mode') ?? 'local') != 'local') return false; // or return
   ```
   Is this worth doing now, or is the comment sufficient given that these files already use `server_ip` directly (making them unreachable in cloud mode)?

---

## Summary of Questions

| # | File | Topic | Priority |
|---|------|--------|----------|
| 1 | `endpoints.dart` | Nullable `_cloudPaths[s]` in prefix expression | Low — all 8 entries exist, but defensive coding question |
| 2 | `about_screen.dart` | `cloud_use_path_prefixes` flag persistence when in local mode | Low — already safe by code structure, asking for confirmation |
| 3 | `home_screen.dart` | Confirm `serverIp` param removal has no hidden side effect | Low — dead code removal, asking for confirmation |
| 4 | `home_screen.dart` | Confirm `processUri` rename is conflict-free | Trivial |
| 5 | `direct_db_update.dart` / `api_tester.dart` | Should runtime `server_mode` guard be added? | Medium — defense-in-depth question |

---

## Build Status
- **Commit:** `a877a50` — pushed to `services-migration`
- **Version:** `2.1.1+1`
- **Ubuntu build:** pending (awaiting user action)
- **iOS build:** not applicable (Android Amazon-Q scope only)
