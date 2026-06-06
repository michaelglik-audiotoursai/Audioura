# Code Review Request — v2.1.1+3 (M2 complete + M3 about_screen updates)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Commit:** `4cfc29a` on branch `services-migration`
**Scope:** All changes from v2.1.1+2 → v2.1.1+3. Ready for final review before Ubuntu build.

---

## Context

Gateway `https://api.audioura.com` is live and smoke-tested (6/6 passing).
All M1 tour/orchestrator/map-delivery URL migrations are already committed in v2.1.1+2.
This version completes M2 (raw-SQL removal) and M3 (about_screen gateway text updates).

---

## What Changed — Full Summary

Two files changed, eight files deleted.

---

## File 1: `services/tour_status_service.dart` — full rewrite (M2)

### Before
- Imported `server_api.dart`, `direct_db_update.dart`, `direct_update_api.dart`
- `trackTourRequest` used hardcoded `http://$serverIp:5003/user/$userId`
- `updateTourStatus` had a three-layer fallback chain:
  1. `DirectUpdateApi.updateTourStatus` → raw HTTP to `:5003`
  2. `ServerApi.updateTourStatus` → raw SQL via `:5003/execute_sql`
  3. `DirectDbUpdate.updateTourStatus` → matched on `request_string` (wrong key)
- Multiple `print()` calls present
- ~120 lines

### After
```dart
// trackTourRequest — user registration via Endpoints
final response = await http.put(
  await Endpoints.url(Service.userDb, '/user/$userId'),
  ...
);

// updateTourStatus — REST via orchestrator
final response = await http.post(
  await Endpoints.url(Service.orchestrator, '/tour-status'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({'tour_id': tourId, 'status': status}),
);
// Logs rows_affected — warns if 0
```
- All `print()` replaced with `DebugLogHelper.addDebugLog()`
- Keyed on `tour_xxx` tour_id (stored mapping `tour_id_$jobId` in SharedPreferences)
- Logs `rows_affected` with ⚠️ warning if 0
- ~75 lines (net −45 lines, −3 imports)

### Key behavioral difference
Old path matched on `request_string` as fallback. New path matches exclusively on `tour_id`
(`tour_XXXXXXXXXXX` format). The `tour_id_$jobId` mapping is set in `trackTourRequest` and
read in `updateTourStatus` — both must be called in the same session for the mapping to exist.

**Q1:** If the app is killed between `trackTourRequest` and `updateTourStatus` (e.g. backgrounded
tour that completes after a restart), `tour_id_$jobId` is still in SharedPreferences (persisted).
Is this the correct recovery path, or should `updateTourStatus` also accept the tour_id directly
as a parameter for cases where the caller already has it?

---

## File 2: `screens/about_screen.dart` — text updates (M3)

Three string changes only — no logic changes:

| Location | Before | After |
|----------|--------|-------|
| Cloud URL field `helperText` | `'e.g. https://map-delivery-xxx-uc.a.run.app'` | `'Gateway: https://api.audioura.com'` |
| Cloud warning text | `'⚠️ Cloud mode: only map-delivery is deployed…'` (orange) | `'✅ Cloud mode: tour generation and map delivery live at api.audioura.com…'` (green) |
| Path prefix checkbox label | `'Use gateway path routing (enable only when audioura.com gateway is deployed)'` | `'Use gateway path routing (leave unchecked — api.audioura.com routes by root path)'` |

The `cloud_use_path_prefixes` default remains `false` — the live gateway routes by root path,
not by `/service-name/` prefixes, so the checkbox must stay unchecked.

---

## Files Deleted (M2)

Eight files removed — 891 lines of raw-SQL client code eliminated:

| File | Reason |
|------|--------|
| `services/direct_db_update.dart` | Raw SQL via `:5003/execute_sql` — replaced by REST |
| `services/direct_jdbc_update.dart` | Duplicate raw-SQL updater |
| `services/direct_postgres_connection.dart` | Duplicate raw-SQL updater |
| `services/direct_update_api.dart` | Duplicate raw-SQL updater |
| `services/postgres_direct.dart` | Duplicate raw-SQL updater |
| `services/server_api.dart` | Duplicate raw-SQL updater |
| `lib/direct_db_update.dart` | Stale root-level copy |
| `lib/tour_status_service.dart` | Stale root-level copy |

Verified: no remaining imports of any deleted file in the lib tree (compile check passed).

---

## Build Readiness Checklist

| Item | Status |
|------|--------|
| `tour_status_service.dart` uses `Endpoints` throughout | ✅ |
| `POST /tour-status` keyed on `tour_id` (not `request_string`) | ✅ |
| `rows_affected` logged with ⚠️ warning on 0 | ✅ |
| All `print()` replaced with `DebugLogHelper.addDebugLog()` | ✅ |
| All 6 raw-SQL service files deleted | ✅ |
| No remaining imports of deleted files | ✅ |
| `about_screen.dart` gateway URL/text updated | ✅ |
| `cloud_use_path_prefixes` default stays `false` | ✅ |
| Version monotonic (`2.1.1+2` → `2.1.1+3`) | ✅ |

---

## Summary of Questions

| # | Topic | Priority |
|---|-------|----------|
| Q1 | If app restarts between `trackTourRequest` and `updateTourStatus`, SharedPreferences mapping survives — is this sufficient, or should `updateTourStatus` accept `tour_id` directly as optional param? | Low |

---

## Ubuntu Build & Smoke Tests

**Branch:** `services-migration` — no `git pull` needed on Ubuntu VM
```bash
bash build_flutter_clean.sh
```
**APK:** `audioura-dev.apk` in `development/` folder

### Priority smoke tests (cloud mode — `https://api.audioura.com`, prefixes OFF)
1. **Foreground single-language local** (regression): generate → completes → opens in player
2. **Foreground cloud generation**: About → Cloud → `cloud_base_url = https://api.audioura.com` → off-WiFi → generate → check debug logs for `TOUR_STATUS: tour_xxx → completed — rows_affected: 1`
3. **Multi-language cloud**: generate with RU+EN → English opens, Russian in My Tours
4. **Backgrounded tour cloud**: Generate in Background → leave app → return → tour in My Tours

### Key log lines to verify in smoke test 2
```
TOUR_TRACK: Created tour_id tour_xxx for job <uuid> — HTTP 200
TOUR_STATUS: tour_xxx → completed — rows_affected: 1
```
`rows_affected: 0` means the tour_id didn't match a DB row — flag for Kiro.
