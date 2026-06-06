# Code Review Request — v2.1.1+3 final (all blockers fixed)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commits:** `4cfc29a` + `7c5cc46` + `787a7f6` on branch `services-migration`
**Scope:** Changes from v2.1.1+2 → v2.1.1+3. Ready for final review before Ubuntu build.

---

## Context

Gateway `https://api.audioura.com` is live (6/6 smoke tests passing). This version completes:
- **M2**: raw-SQL removal, `tour_status_service.dart` → REST
- **M3**: `about_screen.dart` gateway text
- **Blocker A**: `X-API-Key` header on cost-bearing cloud POSTs
- **Blocker B**: `translation_service.dart` migrated from hardcoded LAN IP to `Endpoints`
- **Finding 1**: `test_update_api.dart` deleted (dangling imports)

---

## What Changed — Full Summary

### `config/endpoints.dart` — new `apiHeaders()` helper (Blocker A)

```dart
static Future<Map<String, String>> apiHeaders(Service s) async {
  final prefs = await SharedPreferences.getInstance();
  final headers = {'Content-Type': 'application/json'};
  final mode = prefs.getString('server_mode') ?? 'local';
  if (mode == 'cloud') {
    final key = (prefs.getString('gateway_api_key') ?? '').trim();
    if (key.isNotEmpty) headers['X-API-Key'] = key;
  }
  return headers;
}
```
- Local mode: returns `{'Content-Type': 'application/json'}` only — LAN services don't require a key
- Cloud mode: adds `X-API-Key` from `gateway_api_key` SharedPreferences value
- If key is empty in cloud mode, header is omitted (will 401 — user must set it in About)

### `services/translation_service.dart` — migrated to `Endpoints` (Blocker B)

```dart
// BEFORE:
final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
final baseUrl = 'http://$serverIp:5030';
final response = await http.post(Uri.parse('$baseUrl/translate-with-audio'),
  headers: {'Content-Type': 'application/json'}, ...);

// AFTER:
final uri = await Endpoints.url(Service.translation, '/translate-with-audio');
final headers = await Endpoints.apiHeaders(Service.translation);
final response = await http.post(uri, headers: headers, ...);
```
- `config.dart` import removed
- Resolves to `http://192.168.0.218:5030` in local, `https://api.audioura.com/translate-with-audio` in cloud
- `X-API-Key` included in cloud mode via `apiHeaders()`

### `services/tour_status_service.dart` — `apiHeaders()` added (Blocker A)

```dart
// BEFORE:
headers: {'Content-Type': 'application/json'},

// AFTER:
headers: await Endpoints.apiHeaders(Service.orchestrator),
```

### `screens/tour_generator_screen.dart` — `apiHeaders()` on both generate POSTs (Blocker A)

Both `/generate-complete-tour` POSTs (foreground `_generateTour` and background `_generateTourBackground`) updated:
```dart
// BEFORE:
headers: {'Content-Type': 'application/json'},

// AFTER:
headers: await Endpoints.apiHeaders(Service.orchestrator),
```

### `screens/about_screen.dart` — API key field added (Blocker A)

New `_apiKeyController` + `gateway_api_key` SharedPreferences key:
- Obscured text field in cloud mode section
- `_saveApiKey()` method persists to SharedPreferences
- Loaded in `_loadAppInfo()`, disposed in `dispose()`
- Helper text: "Required for cloud generation. Never share or commit this key."

### Files deleted (9 total — Finding 1 + M2)
`direct_db_update`, `direct_jdbc_update`, `direct_postgres_connection`, `direct_update_api`,
`postgres_direct`, `server_api`, `test_update_api` (services/), plus 2 stale root-level copies.

---

## Known Services Dependency (not a mobile fix)

`trackTourRequest` PUT → `Service.userDb /user/$userId` — in cloud mode the `/user` gateway
route is not yet deployed, so `tour_requests` row is never created → `rows_affected: 0` on
status updates. Generation and download are unaffected. Expect `rows_affected: 0` in cloud
smoke tests until Kiro deploys the `/user` route.

---

## Build Readiness Checklist

| Item | Status |
|------|--------|
| `Endpoints.apiHeaders()` injects `X-API-Key` in cloud only | ✅ |
| `gateway_api_key` stored in SharedPreferences, never committed | ✅ |
| Both `/generate-complete-tour` POSTs use `apiHeaders()` | ✅ |
| `/tour-status` POST uses `apiHeaders()` | ✅ |
| `TranslationService` → `Endpoints.url(Service.translation)` + `apiHeaders()` | ✅ |
| `config.dart` import removed from `translation_service.dart` | ✅ |
| API key field in About screen (obscured, cloud section only) | ✅ |
| 9 raw-SQL/dead files deleted, no remaining imports | ✅ |
| `cloud_use_path_prefixes` default `false` | ✅ |
| Version monotonic (`2.1.1+2` → `2.1.1+3`) | ✅ |
| Services dependency (`/user` route) documented | ✅ noted |

---

## Questions for Claude

| # | Topic | Priority |
|---|-------|----------|
| Q1 | `apiHeaders()` silently omits `X-API-Key` if key is empty in cloud mode (will get 401). Should it throw or log a warning instead so the user knows why generation failed? | Medium |
| Q2 | `tour_id_$jobId` / `request_$jobId` keys accumulate in SharedPreferences and are never cleaned up after terminal status. Worth adding cleanup? | Low |

---

## Ubuntu Build & Smoke Tests

**Branch:** `services-migration` — no `git pull` needed on Ubuntu VM
```bash
bash build_flutter_clean.sh
```

### Priority smoke tests
1. **Local WiFi — foreground** (regression): generate → completes → opens in player →
   debug logs show `TOUR_STATUS: tour_xxx → completed — rows_affected: 1` ✅
2. **Cloud — foreground generation** (About → Cloud → URL + API key set, prefixes OFF, off-WiFi):
   generate → completes → opens → `rows_affected: 0` expected (services dep) — generation must succeed ✅
3. **Cloud — multi-language**: generate RU+EN → English opens, Russian in My Tours
   (exercises `Endpoints.url(Service.translation)` fix)
4. **Cloud — backgrounded tour**: Generate in Background → leave app → return → tour in My Tours
