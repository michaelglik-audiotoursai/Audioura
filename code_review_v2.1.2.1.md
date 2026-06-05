# Code Review Request — v2.1.2+1 (M1: Tour Generation through Endpoints)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commit:** `40a9152` on branch `services-migration`
**Reviewing:** M1 from `TASKS_FOR_MOBILE_AQ_android_2026_06_03.md`

---

## What Changed

**M1 — Route all tour generation through `Endpoints(Service.orchestrator)`**

Previously all generation/status/download calls in tour generation hardcoded
`http://$serverIp:5002`, bypassing the `Endpoints` resolver and breaking in
cloud mode. This commit migrates all 6 sites to `Endpoints.url(Service.orchestrator, ...)`.

### Files changed:
1. `screens/tour_generator_screen.dart` — main screen
2. `services/background_service.dart` — background polling service
3. `services/background_tour_monitor.dart` — background monitor service
4. `pubspec.yaml` — version `2.1.1+1` → `2.1.2+1`

---

## File 1: `screens/tour_generator_screen.dart`

### What was removed
- `String _apiBaseUrl = 'http://192.168.0.217:5002'` field (line 37)
- `_loadServerIp()` method (lines 107–115) and its call in `initState()`
- All `Uri.parse('$_apiBaseUrl/...')` usages replaced
- All `print()` calls replaced with `DebugLogHelper.addDebugLog()`
- `apiBaseUrl` key removed from `_pendingTours` state map and pending tour JSON

### 6 migrated call sites

**1. Foreground generation POST (`_generateTour`)**
```dart
// Before:
Uri.parse('$_apiBaseUrl/generate-complete-tour')
// After:
await Endpoints.url(Service.orchestrator, '/generate-complete-tour')
```

**2. Status polling GET (`_pollAndAutoDownload`)**
```dart
// Before:
Uri.parse('$_apiBaseUrl/status/$jobId')
// After:
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

**3. Download GET — `_autoDownloadAndPlay` (status fetch for final_tour_id)**
```dart
// Before:
Uri.parse('$_apiBaseUrl/status/$jobId')
// After:
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

**4. Download GET — `_autoDownloadAndPlay` (tour download)**
```dart
// Before:
Uri.parse('$_apiBaseUrl/download/$finalTourId')
// After:
await Endpoints.url(Service.orchestrator, '/download/$finalTourId')
```

**5. Coordinates fetch GET — `_saveTourInfo`**
```dart
// Before:
Uri.parse('$_apiBaseUrl/status/$jobId')
// After:
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

**6. Background generation POST (`_generateTourBackground`)**
```dart
// Before:
Uri.parse('$_apiBaseUrl/generate-complete-tour')
// After:
await Endpoints.url(Service.orchestrator, '/generate-complete-tour')
```

### Pending tour JSON — `apiBaseUrl` key removed
Both places that store pending tour data no longer include `apiBaseUrl`:
```dart
// Before:
{'jobId': jobId, 'location': ..., 'apiBaseUrl': _apiBaseUrl, 'startTime': ...}
// After:
{'jobId': jobId, 'location': ..., 'startTime': ...}
```

**Q1:** `background_service.dart` reads `apiBaseUrl` from the stored pending tour JSON
(`tour['apiBaseUrl']`) for its status check. Now that key is gone — see File 2 for
how this is handled. Is the approach correct?

---

## File 2: `services/background_service.dart`

### Import added
```dart
import '../config/endpoints.dart';
```

### Status check migrated
```dart
// Before:
final apiBaseUrl = tour['apiBaseUrl'];
await DebugLogHelper.addDebugLog('Checking tour status: $apiBaseUrl/status/$jobId');
final response = await http.get(Uri.parse('$apiBaseUrl/status/$jobId'));

// After:
final statusUri = await Endpoints.url(Service.orchestrator, '/status/$jobId');
await DebugLogHelper.addDebugLog('Checking tour status: $statusUri');
final response = await http.get(statusUri);
```

Note: `final apiBaseUrl = tour['apiBaseUrl']` is still read from the JSON earlier
in the loop but is now unused. It will harmlessly be `null` for new entries (the key
was removed from the stored JSON). Old entries already in SharedPreferences from
before this build will still have the key and it will be read but ignored.

**Q2:** Should the `final apiBaseUrl = tour['apiBaseUrl']` read be explicitly
removed from the loop to keep the code clean? It is dead code now that nothing
uses it. Or is it acceptable to leave since it's harmless?

### Download migrated
```dart
// Before:
await http.get(Uri.parse('http://$serverIp:5002/download/$jobId'))

// After:
await http.get(await Endpoints.url(Service.orchestrator, '/download/$jobId'))
```

The `final serverIp = prefs.getString('server_ip') ?? '192.168.0.217'` line is
still present above this call but is now unused (was only needed for the hardcoded URL).

**Q3:** Same question — should the now-unused `serverIp` local variable be removed?

---

## File 3: `services/background_tour_monitor.dart`

### Import added
```dart
import '../config/endpoints.dart';
```

### Status check migrated
```dart
// Before:
final apiBaseUrl = tour['apiBaseUrl'] as String;
Uri.parse('$apiBaseUrl/status/$jobId')

// After:
await Endpoints.url(Service.orchestrator, '/status/$jobId')
```

### Download migrated
```dart
// Before:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
Uri.parse('http://$serverIp:5002/download/$jobId')

// After:
await Endpoints.url(Service.orchestrator, '/download/$jobId')
```

Same dead-variable concern as File 2 — `serverIp` and `apiBaseUrl` reads may
remain in the file but are now unused.

**Q4:** Is there any concern about `background_tour_monitor.dart` calling
`Endpoints.url()` from a background isolate or timer context? `Endpoints.url()`
calls `SharedPreferences.getInstance()` which is async — is this safe in a
`Timer.periodic` callback?

---

## M3 Audit — Remaining `.217` / hardcoded `:5002` literals

Per the task spec, M3 requires auditing for any remaining bypasses. Known
remaining hardcoded URLs **not yet migrated** (intentionally deferred):

| File | Hardcoded URL | Notes |
|------|--------------|-------|
| `tour_generator_screen.dart` `_generateNews()` | `http://$serverIp:5012/generate-news` | News generation — separate service, not orchestrator. Not part of M1. |
| `tour_generator_screen.dart` `_pollNewsAndAutoDownload()` | `http://$serverIp:5012/status/$articleId` | Same |
| `tour_generator_screen.dart` `_downloadAndSaveNews()` | `http://$serverIp:5012/download/$articleId` | Same |
| `tour_generator_screen.dart` `_processNewsletterUrl()` | `http://$serverIp:5017/process_newsletter` | Newsletter — separate service |
| `tour_generator_screen.dart` `_processAdditionalLanguages()` | `http://$serverIp:5005/download-tour/$translatedId` | Uses map-delivery port — should be `Service.mapDelivery` |

**Q5:** The `_processAdditionalLanguages` method in `tour_generator_screen.dart`
still uses `http://$serverIp:5005/download-tour/$translatedId` (map-delivery service).
This was not in the M1 task spec (which only listed the 6 orchestrator sites), but
it is a bypass of `Endpoints`. Should this be migrated now as part of M3 cleanup,
or left for a separate pass? It would be a 2-line change:
```dart
// Replace:
final url = 'http://$serverIp:5005/download-tour/$translatedId';
final resp = await http.get(Uri.parse(url))...
// With:
final resp = await http.get(await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId'))...
```

---

## Summary of Questions

| # | File | Topic | Priority |
|---|------|--------|----------|
| 1 | `background_service.dart` | `apiBaseUrl` key gone from JSON — is the Endpoints approach correct for background status polling? | Medium |
| 2 | `background_service.dart` | Dead `apiBaseUrl` read from tour JSON — remove? | Low |
| 3 | `background_service.dart` | Dead `serverIp` local — remove? | Low |
| 4 | `background_tour_monitor.dart` | Is `Endpoints.url()` (async SharedPreferences) safe in Timer.periodic callback? | Medium |
| 5 | `tour_generator_screen.dart` | Should `_processAdditionalLanguages` `:5005` URL be migrated now? | Medium |

---

## Build Status
- **Commit:** `40a9152` — pushed to `services-migration`
- **Version:** `2.1.2+1`
- **Ubuntu build:** pending
- **Expected test:** About → Cloud → gateway URL → off WiFi → Generate tour → tour completes and downloads
