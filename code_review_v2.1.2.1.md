# Code Review Request — v2.1.2+1 (M1 complete)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commit:** `262746f` on branch `services-migration`
**Scope:** All changes since v2.1.1+1 — ready for final review before Ubuntu build

---

## Summary of All Changes

M1 is now complete. All tour generation, status polling, and download calls across
all three files route through `Endpoints` — no hardcoded LAN IPs remain for the
tour/orchestrator/map-delivery paths. The compile blocker (missing `prefs` in
`_processAdditionalLanguages`) has been fixed.

---

## File 1: `screens/tour_generator_screen.dart`

### Imports — removed `config.dart`
```dart
// REMOVED (no longer needed — Config.defaultServerIp was only used in _processAdditionalLanguages):
import '../config.dart';
```

### `_generateTour` — foreground generation POST ✅
```dart
await Endpoints.url(Service.orchestrator, '/generate-complete-tour')
```

### `_pollAndAutoDownload` — status poll ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

### `_autoDownloadAndPlay` — status fetch + download ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
await Endpoints.url(Service.orchestrator, '/download/$finalTourId')
```

### `_saveTourInfo` — coordinates fetch ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

### `_generateTourBackground` — background generation POST ✅
```dart
await Endpoints.url(Service.orchestrator, '/generate-complete-tour')
```

### `_processAdditionalLanguages` — translated tour download ✅
```dart
// BEFORE:
final prefs = await SharedPreferences.getInstance();
final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
final url = 'http://$serverIp:5005/download-tour/$translatedId';
final resp = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 120));

// AFTER:
final prefs = await SharedPreferences.getInstance();   // retained — passed to _saveTourToMyToursTranslated
final resp = await http.get(
  await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId'),
).timeout(const Duration(seconds: 120));
```

**Q1:** `prefs` is obtained here and passed into `_saveTourToMyToursTranslated(translatedId,
resp.bodyBytes, appDir.path, prefs, lang)`. That method uses `prefs` to read/write
`saved_tours`. Is this the correct pattern, or should `_saveTourToMyToursTranslated`
obtain its own `prefs` instance? (`SharedPreferences.getInstance()` is a cached singleton
so either approach is safe — this is a style question.)

### `_downloadBackgroundTour` — status + download ✅
```dart
// BEFORE:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
await http.get(Uri.parse('http://$serverIp:5002/status/${tour['id']}'))
await http.get(Uri.parse('http://$serverIp:5002/download/${tour['id']}'))

// AFTER:
await http.get(await Endpoints.url(Service.orchestrator, '/status/${tour['id']}'))
await http.get(await Endpoints.url(Service.orchestrator, '/download/${tour['id']}'))
```
`prefs` instance retained — still used for `saved_tours` and `background_tours` writes.

### Remaining hardcoded URLs (intentionally deferred — M3 / news services not yet deployed)
| Method | URL | Port | Reason deferred |
|--------|-----|------|----------------|
| `_generateNews` | `http://$serverIp:5012/generate-news` | 5012 | News service — not in M1 scope |
| `_pollNewsAndAutoDownload` | `http://$serverIp:5012/status/$articleId` | 5012 | Same |
| `_downloadAndSaveNews` | `http://$serverIp:5012/download/$articleId` | 5012 | Same |
| `_processNewsletterUrl` | `http://$serverIp:5017/process_newsletter` | 5017 | Newsletter service — not deployed |

---

## File 2: `services/background_service.dart`

### Dead `apiBaseUrl` read removed ✅
```dart
// REMOVED:
final apiBaseUrl = tour['apiBaseUrl'];
```

### Dead `serverIp` local removed ✅
```dart
// REMOVED:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
```

### Status check ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

### Download ✅
```dart
await Endpoints.url(Service.orchestrator, '/download/$jobId')
```

---

## File 3: `services/background_tour_monitor.dart`

### Status check ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

### Download ✅
```dart
await Endpoints.url(Service.orchestrator, '/download/$jobId')
```

### 🔴 Two items still present — need your verdict:

**Item A — Dead `apiBaseUrl` cast in `checkBackgroundTourStatus`:**
```dart
final apiBaseUrl = tour['apiBaseUrl'] as String;  // ← key no longer stored in JSON
```
This will throw a `TypeError` at runtime for any tour stored after v2.1.1+1 (when
the key was removed from the pending tour JSON). New pending tours won't have this
key, so `tour['apiBaseUrl']` returns `null`, and `as String` throws.
**Recommend: remove this line.**

**Item B — Dead `serverIp` local in `_autoDownloadCompletedTour`:**
```dart
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
```
This local is declared but never used — the download call below it already uses
`Endpoints.url(Service.orchestrator, '/download/$jobId')`.
**Recommend: remove this line.**

**Q2:** Should I apply these two removals now before the build, or do you want
Claude to confirm first?

---

## Summary of Questions

| # | File | Topic | Priority |
|---|------|--------|----------|
| 1 | `tour_generator_screen.dart` | Style: pass `prefs` into `_saveTourToMyToursTranslated` vs. let it obtain its own — correct pattern? | Low |
| 2 | `background_tour_monitor.dart` | Dead `apiBaseUrl` cast (runtime crash risk) + dead `serverIp` local — remove before build? | **High** |

---

## Build Readiness

| Item | Status |
|------|--------|
| Compile blocker (`prefs` missing in `_processAdditionalLanguages`) | ✅ Fixed |
| Version monotonic (`2.1.1+1` → `2.1.2+1`) | ✅ Fixed |
| All orchestrator URLs migrated | ✅ |
| `_processAdditionalLanguages` → `Service.mapDelivery` | ✅ |
| Dead `apiBaseUrl`/`serverIp` in `background_service.dart` | ✅ Removed |
| Dead `apiBaseUrl` cast in `background_tour_monitor.dart` | ⚠️ Still present — runtime crash risk |
| Dead `serverIp` in `background_tour_monitor.dart` | ⚠️ Still present — harmless but untidy |

**Recommendation:** Fix Item A in `background_tour_monitor.dart` before building —
it is a guaranteed runtime crash for any backgrounded tour on v2.1.2+1 because all
new pending tours lack the `apiBaseUrl` key.

---

## Ubuntu Build Instructions

**Branch:** `services-migration` — no `git pull` needed on Ubuntu VM
```bash
bash build_flutter_clean.sh
```
**APK output:** `audioura-dev.apk` in `development/` folder

---

## Smoke Test Plan (priority order)

1. **Foreground single-language tour — local mode (regression)**
   Generate tab → request a tour → verify it generates, downloads, opens in player

2. **Multi-language tour — cloud mode** *(exercises `Service.mapDelivery` fix)*
   About → Cloud → enter gateway URL → Generate tab → select RU or KO + EN →
   request tour → verify English tour opens AND translated tour appears in My Tours

3. **Backgrounded tour completion — cloud mode** *(exercises `_downloadBackgroundTour` + `background_tour_monitor` fixes)*
   About → Cloud → "Generate in Background" → leave app → return →
   verify tour auto-downloads to My Tours
