# Code Review Request — v2.1.1+2 (M1 complete + full cleanup)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commit:** `9265ac6` on branch `services-migration`
**Scope:** All changes from v2.1.1+1 → v2.1.1+2. Ready for final review before Ubuntu build.

---

## What Changed — Full Summary

Three files changed. Goal: complete M1 (all tour/orchestrator/map-delivery URLs through
`Endpoints`), fix a compile blocker, fix a runtime crash, and eliminate all `print()`
violations.

---

## File 1: `screens/tour_generator_screen.dart`

### 1a. Removed `config.dart` import
`Config.defaultServerIp` was the only usage — eliminated when `_processAdditionalLanguages`
was migrated away from the hardcoded IP.

### 1b. `_processAdditionalLanguages` — translated download migrated to `Service.mapDelivery`
```dart
// BEFORE:
final prefs = await SharedPreferences.getInstance();
final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
final url = 'http://$serverIp:5005/download-tour/$translatedId';
final resp = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 120));

// AFTER:
final prefs = await SharedPreferences.getInstance();  // retained — passed to _saveTourToMyToursTranslated
final resp = await http.get(
  await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId'),
).timeout(const Duration(seconds: 120));
```
`prefs` is still obtained here and passed into `_saveTourToMyToursTranslated(translatedId,
resp.bodyBytes, appDir.path, prefs, lang)` which uses it to read/write `saved_tours`.

**Q1:** Is passing `prefs` as a parameter the right pattern here, or should
`_saveTourToMyToursTranslated` call `SharedPreferences.getInstance()` itself?
(Both are safe since it's a cached singleton — style question only.)

### 1c. `_downloadBackgroundTour` — status + download migrated to `Service.orchestrator`
```dart
// BEFORE:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
await http.get(Uri.parse('http://$serverIp:5002/status/${tour['id']}'))
await http.get(Uri.parse('http://$serverIp:5002/download/${tour['id']}'))

// AFTER:
await http.get(await Endpoints.url(Service.orchestrator, '/status/${tour['id']}'))
await http.get(await Endpoints.url(Service.orchestrator, '/download/${tour['id']}'))
```
`serverIp` local and `'192.168.0.217'` fallback removed. `prefs` retained for
`saved_tours`/`background_tours` writes.

### 1d. All `print()` calls replaced with `DebugLogHelper.addDebugLog()`
14 occurrences across: `_generateTour`, `_saveTourInfo`, `_showError`, `_showSuccess`,
`_generateTourBackground`, `_showNotificationPermissionDialog`,
`_requestNotificationPermissionAndStartBackground`, `_saveNewsInfo`.

### 1e. Remaining hardcoded URLs (intentionally deferred)
| Method | Port | Reason |
|--------|------|--------|
| `_generateNews` | 5012 | News service — not deployed, not M1 scope |
| `_pollNewsAndAutoDownload` | 5012 | Same |
| `_downloadAndSaveNews` | 5012 | Same |
| `_processNewsletterUrl` | 5017 | Newsletter service — not deployed |

**Q2:** Are these four deferrals correct? News/newsletter services are not yet on
Cloud Run, so migrating them to `Endpoints(Service.news/newsletter)` now would
work locally but have no cloud target. Confirm defer until those services deploy.

---

## File 2: `services/background_service.dart`

### 2a. Dead `apiBaseUrl` read removed
```dart
// REMOVED:
final apiBaseUrl = tour['apiBaseUrl'];
```
Key was removed from pending tour JSON in v2.1.1+1. Now correctly absent.

### 2b. Dead `serverIp` local removed from `_autoDownloadBackgroundTour`
```dart
// REMOVED:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
```
Download call already used `Endpoints.url(Service.orchestrator, ...)`.

### 2c. All `print()` calls replaced with `DebugLogHelper.addDebugLog()`
7 occurrences. Also fixed duplicate log lines introduced during an earlier partial
replacement pass.

### 2d. Status check and download — already migrated in previous session ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
await Endpoints.url(Service.orchestrator, '/download/$jobId')
```

---

## File 3: `services/background_tour_monitor.dart`

### 3a. Dead `apiBaseUrl` cast removed — was a **runtime crash**
```dart
// REMOVED:
final apiBaseUrl = tour['apiBaseUrl'] as String;
```
The `apiBaseUrl` key was removed from pending tour JSON in v2.1.1+1. All new pending
tours lack this key, so `tour['apiBaseUrl']` returns `null`. The `as String` cast
throws a `TypeError` at runtime — guaranteed crash for every backgrounded tour.

### 3b. Dead `serverIp` local removed from `_autoDownloadCompletedTour`
```dart
// REMOVED:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
```
Download call already used `Endpoints.url(Service.orchestrator, '/download/$jobId')`.

### 3c. Status check and download — already migrated in previous session ✅
```dart
await Endpoints.url(Service.orchestrator, '/status/$jobId')
await Endpoints.url(Service.orchestrator, '/download/$jobId')
```

---

## Complete Endpoints Migration Audit

### ✅ All migrated — tour/orchestrator/map-delivery paths
| File | Method | Endpoint | Service |
|------|--------|----------|---------|
| `tour_generator_screen.dart` | `_generateTour` | `/generate-complete-tour` | orchestrator |
| `tour_generator_screen.dart` | `_pollAndAutoDownload` | `/status/$jobId` | orchestrator |
| `tour_generator_screen.dart` | `_autoDownloadAndPlay` | `/status/$jobId`, `/download/$finalTourId` | orchestrator |
| `tour_generator_screen.dart` | `_saveTourInfo` | `/status/$jobId` | orchestrator |
| `tour_generator_screen.dart` | `_generateTourBackground` | `/generate-complete-tour` | orchestrator |
| `tour_generator_screen.dart` | `_processAdditionalLanguages` | `/download-tour/$translatedId` | mapDelivery |
| `tour_generator_screen.dart` | `_downloadBackgroundTour` | `/status/${tour['id']}`, `/download/${tour['id']}` | orchestrator |
| `background_service.dart` | `checkBackgroundTours` | `/status/$jobId` | orchestrator |
| `background_service.dart` | `_autoDownloadBackgroundTour` | `/download/$jobId` | orchestrator |
| `background_tour_monitor.dart` | `checkBackgroundTourStatus` | `/status/$jobId` | orchestrator |
| `background_tour_monitor.dart` | `_autoDownloadCompletedTour` | `/download/$jobId` | orchestrator |

### ⏸ Deferred — news/newsletter (services not yet on Cloud Run)
| File | Method | Port |
|------|--------|------|
| `tour_generator_screen.dart` | `_generateNews` | 5012 |
| `tour_generator_screen.dart` | `_pollNewsAndAutoDownload` | 5012 |
| `tour_generator_screen.dart` | `_downloadAndSaveNews` | 5012 |
| `tour_generator_screen.dart` | `_processNewsletterUrl` | 5017 |

---

## Summary of Questions

| # | Topic | Priority |
|---|-------|----------|
| Q1 | `prefs` passed as parameter vs. obtained inside `_saveTourToMyToursTranslated` — correct pattern? | Low |
| Q2 | Defer news (`:5012`) and newsletter (`:5017`) until those services deploy to Cloud Run? | Confirm |

---

## Build Readiness Checklist

| Item | Status |
|------|--------|
| Compile blocker (`prefs` missing in `_processAdditionalLanguages`) | ✅ Fixed |
| Runtime crash (`apiBaseUrl as String` cast in `background_tour_monitor`) | ✅ Fixed |
| Version monotonic (`2.1.1+1` → `2.1.1+2`) | ✅ Fixed |
| All orchestrator URLs migrated (11 sites across 3 files) | ✅ |
| `_processAdditionalLanguages` → `Service.mapDelivery` | ✅ |
| Dead `apiBaseUrl` reads removed (both files) | ✅ |
| Dead `serverIp` locals removed (both files) | ✅ |
| All `print()` replaced with `DebugLogHelper.addDebugLog()` | ✅ |
| News/newsletter URLs (`:5012`, `:5017`) | ⏸ Deferred |

---

## Ubuntu Build & Smoke Test

**Branch:** `services-migration` — no `git pull` needed on Ubuntu VM
```bash
bash build_flutter_clean.sh
```
**APK:** `audioura-dev.apk` in `development/` folder

### Priority smoke tests
1. **Foreground single-language — local mode** (regression): Generate → tour completes, downloads, opens in player
2. **Multi-language — cloud mode** (exercises `Service.mapDelivery` fix): Generate with RU+EN → English opens, Russian appears in My Tours
3. **Backgrounded tour — cloud mode** (exercises `_downloadBackgroundTour` + `background_tour_monitor` fixes): "Generate in Background" → leave app → return → tour in My Tours
