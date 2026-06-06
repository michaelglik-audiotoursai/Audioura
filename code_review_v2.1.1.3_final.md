# Code Review Request — v2.1.1+3 final (M2 + M3, Finding 1 fixed)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commits:** `4cfc29a` (M2+M3) + `7c5cc46` (delete test_update_api.dart) on branch `services-migration`
**Scope:** All changes from v2.1.1+2 → v2.1.1+3. Ready for final review before Ubuntu build.

---

## Context

Gateway `https://api.audioura.com` is live and smoke-tested (6/6 passing).
All M1 tour/orchestrator/map-delivery URL migrations are committed in v2.1.1+2.
This version completes M2 (raw-SQL removal) and M3 (about_screen gateway text).
A prior Claude review of `4cfc29a` found two issues — Finding 1 is fixed in `7c5cc46`;
Finding 2 is a services dependency (documented below, no Dart fix possible).

---

## What Changed

### `services/tour_status_service.dart` — full rewrite (M2)

**Before:** Three-layer raw-SQL fallback chain via `direct_db_update`, `direct_update_api`,
`server_api` — all matched on `request_string`. Hardcoded `http://$serverIp:5003`.

**After:**
```dart
// trackTourRequest — user registration via Endpoints
await http.put(
  await Endpoints.url(Service.userDb, '/user/$userId'),
  ...
);
// stores tour_id_$jobId mapping in SharedPreferences

// updateTourStatus — REST via orchestrator
await http.post(
  await Endpoints.url(Service.orchestrator, '/tour-status'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({'tour_id': tourId, 'status': status}),
);
// logs rows_affected, warns if 0
```
- Keyed on `tour_xxx` tour_id (not `request_string`)
- `tour_id_$jobId` mapping persisted in SharedPreferences — survives app restart
- All `print()` → `DebugLogHelper.addDebugLog()`
- ~75 lines (was ~120)

### `screens/about_screen.dart` — text only (M3)

| Location | Before | After |
|----------|--------|-------|
| Cloud URL `helperText` | `'e.g. https://map-delivery-xxx-uc.a.run.app'` | `'Gateway: https://api.audioura.com'` |
| Cloud status text | `'⚠️ Cloud mode: only map-delivery is deployed…'` (orange) | `'✅ Cloud mode: tour generation and map delivery live at api.audioura.com…'` (green) |
| Prefix checkbox label | `'…enable only when audioura.com gateway is deployed'` | `'…leave unchecked — api.audioura.com routes by root path'` |

`cloud_use_path_prefixes` default remains `false` — gateway routes by root path, not prefixes.

### Files deleted (9 total — 949 lines removed)

| File | Reason |
|------|--------|
| `services/direct_db_update.dart` | Raw SQL via `:5003/execute_sql` |
| `services/direct_jdbc_update.dart` | Duplicate raw-SQL updater |
| `services/direct_postgres_connection.dart` | Duplicate raw-SQL updater |
| `services/direct_update_api.dart` | Duplicate raw-SQL updater |
| `services/postgres_direct.dart` | Duplicate raw-SQL updater |
| `services/server_api.dart` | Duplicate raw-SQL updater |
| `services/test_update_api.dart` | Dead test harness; imported 3 of the above (broken imports) |
| `lib/direct_db_update.dart` | Stale root-level copy |
| `lib/tour_status_service.dart` | Stale root-level copy |

No remaining imports of any deleted file in the lib tree — verified by directory scan.

---

## Known Services Dependency (not a mobile bug)

**`trackTourRequest` PUT → `Service.userDb /user/$userId`** — in cloud mode this resolves to
`https://api.audioura.com/user/USER-xxx`. The live gateway has no `/user` route and `user-api`
(`:5003`) is not yet deployed. So in cloud:
- The `tour_requests` row is never created (PUT hits 404)
- `updateTourStatus` finds no matching row → `rows_affected: 0`

The `rows_affected: 0` ⚠️ warning in the debug log is the signal. Tour **generation and
download** are unaffected — only status bookkeeping is a no-op until the services dependency
is resolved. Cannot be fixed in Dart; requires `/user` gateway route + user-api deployment.

**Smoke test expectation:** `rows_affected: 0` in cloud is expected and correct until
services dependency resolved. `rows_affected: 1` in local WiFi mode is the regression check.

---

## Build Readiness Checklist

| Item | Status |
|------|--------|
| `POST /tour-status` via `Endpoints.url(Service.orchestrator)` | ✅ |
| Keyed on `tour_xxx` tour_id (not `request_string`) | ✅ |
| `rows_affected` logged, ⚠️ on 0 | ✅ |
| All `print()` → `DebugLogHelper.addDebugLog()` | ✅ |
| All 9 raw-SQL/dead files deleted | ✅ |
| No remaining imports of deleted files | ✅ |
| `about_screen.dart` gateway URL/text correct | ✅ |
| `cloud_use_path_prefixes` default `false` | ✅ |
| Version monotonic (`2.1.1+2` → `2.1.1+3`) | ✅ |
| Services dependency documented (Finding 2) | ✅ noted — not a mobile fix |

---

## Questions for Claude

| # | Topic | Priority |
|---|-------|----------|
| Q1 | `tour_id_$jobId` / `request_$jobId` keys accumulate in SharedPreferences and are never cleaned up after terminal status. Worth adding cleanup, or acceptable as-is for now? | Low |

---

## Ubuntu Build & Smoke Tests

**Branch:** `services-migration` — no `git pull` needed on Ubuntu VM
```bash
bash build_flutter_clean.sh
```

### Priority smoke tests
1. **Local WiFi — foreground** (regression): generate → completes → opens in player →
   debug logs show `rows_affected: 1` ✅
2. **Cloud — foreground generation** (About → Cloud → `https://api.audioura.com`, prefixes OFF,
   off-WiFi): generate → completes → opens → debug logs show `rows_affected: 0` ⚠️ expected
   (services dependency) — generation + download must still succeed ✅
3. **Cloud — multi-language**: generate with RU+EN → English opens, Russian appears in My Tours
4. **Cloud — backgrounded tour**: Generate in Background → leave app → return → tour in My Tours
