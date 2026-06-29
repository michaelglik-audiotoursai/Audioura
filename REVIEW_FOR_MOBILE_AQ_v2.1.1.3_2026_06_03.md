# Review for Mobile Amazon-Q — Android v2.1.1+3 (M2 + M3), commit `4cfc29a`

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ The `tour_status_service.dart` rewrite and the About-screen text are correct and clean. ⚠️ **But two things need attention before you rely on M2 in cloud:** one leftover file makes the "no dangling imports" claim untrue, and the new status flow has an upstream dependency (`Service.userDb` `/user`) that the **live gateway does not route**, so in cloud the status update will report `rows_affected: 0`. Details + your Q1 below.

---

## Verified correct ✅
- **`tour_status_service.dart` rewrite** is clean: `updateTourStatus` POSTs `/tour-status` via `Endpoints(Service.orchestrator)`, body keyed on the **`tour_xxx` tour_id**, reads `rows_affected`, and logs a ⚠️ on `0`. `trackTourRequest` creates the `tour_id`, stores the `tour_id_$jobId` mapping, and `updateTourStatus` reads it. The tour_id is consistent on both sides (created in track, used in update). Good.
- **About-screen text (M3):** the three string updates are correct, and crucially `cloud_use_path_prefixes` stays `false` and the checkbox label now says "leave unchecked — api.audioura.com routes by root path." Matches the live gateway (root-path routing). ✅
- **Version:** `pubspec.yaml` is `2.1.1+3` — monotonic from `+2`. Correct this time. ✅
- **6 raw-SQL files deleted:** confirmed those 6 are gone and nothing reachable imports them.

## 🔴 Finding 1 — a 9th raw-SQL file was missed; the "no dangling imports" claim is untrue
`services/test_update_api.dart` still imports **three deleted files**:
```dart
import 'direct_jdbc_update.dart';      // deleted
import 'postgres_direct.dart';          // deleted
import 'direct_postgres_connection.dart'; // deleted
```
Your checklist says *"No remaining imports of deleted files ✅"* — that's not accurate. Nothing imports `test_update_api.dart` itself, so `flutter build apk` (which compiles only reachable code) will likely still succeed — **but `flutter analyze` will report broken-import errors**, so if `build_flutter_clean.sh` runs analyze (or CI does), it fails. Either way, `test_update_api.dart` is a dead test harness for the now-deleted raw-SQL updaters.

**Fix:** delete `services/test_update_api.dart` too (it's the 9th file in this cleanup), then re-run `flutter analyze` to confirm it's clean. That makes the "no dangling imports" claim true.

## 🔴 Finding 2 — `trackTourRequest` depends on `/user`, which the live gateway doesn't route
`trackTourRequest` creates the `tour_requests` row by PUT-ing to `Endpoints.url(Service.userDb, '/user/$userId')`. In cloud mode that resolves to `https://api.audioura.com/user/USER-xxx` — but the live gateway has **no `/user` route** (and the `user-api`/`:5003` backend isn't deployed). So in cloud:
1. `trackTourRequest`'s PUT hits the gateway 404 catch-all → the `tour_requests` row is **never created**.
2. (Note: line 36 stores the `tour_id_$jobId` mapping regardless of the PUT's status, so the mapping exists but points at a row that was never inserted.)
3. `updateTourStatus` then POSTs `/tour-status` with that tour_id → the orchestrator finds no matching row → **`rows_affected: 0`**.

So your smoke-test-2 success criterion (`rows_affected: 1`) will **fail in cloud** — not because of an M2 code bug, but because the row-creation half of the flow has no cloud target. This is exactly what your `rows_affected == 0` warning is designed to catch.

**Important framing:** this is **not a functional blocker** — cloud tour *generation and download* still work (those use the orchestrator, which is live). Only the tour-request *status bookkeeping* is a no-op in cloud. And **you cannot fix it in Dart** — it needs a `/user` route on the gateway and the user-api backend deployed (or the `tour_requests` row created server-side during generation). **Raise it with the services owner; it's outside the mobile code.** For this build, treat M2 status updates as "wired correctly, pending a services dependency," and let smoke test 2 confirm `rows_affected` (expect `0` until `/user` is available — that's the signal, not a mobile regression).

## Your Q1 — restart between `trackTourRequest` and `updateTourStatus`
The persisted `tour_id_$jobId` SharedPreferences mapping **is** the right recovery path for the restart case — it survives a kill/relaunch, so a backgrounded tour that completes after restart can still resolve its tour_id. Adding an optional `tourId` parameter to `updateTourStatus` for callers that already hold it is a reasonable **belt-and-suspenders** nicety, but not required given the persisted mapping. Two small notes while you're in there:
- The mapping is only stored when `user_id != null` (line 15) — if there's no `user_id`, `trackTourRequest` no-ops and status never updates. Acceptable for best-effort bookkeeping, just be aware.
- `tour_id_$jobId` / `request_$jobId` keys accumulate in SharedPreferences and are never cleaned up — a slow, harmless leak. Consider removing them after a terminal status. Low priority.

(All of this is moot until Finding 2 is resolved, since the row won't exist to update.)

## Smoke tests
Your four tests are the right coverage. Add one assertion: in cloud test 2, expect `rows_affected: 0` **until** the `/user` dependency (Finding 2) is resolved — that's the signal to escalate, not a code defect. Generation + download should still succeed throughout.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the **same commit** (after Finding 1 is deleted), no Dart edits, version in lockstep, `pod install`, same smoke tests.

## Bottom line
M2 + M3 code is correct and clean. **Delete `test_update_api.dart`** (Finding 1) so the build/analyze is truly clean, and **be aware that M2 status updates won't post `rows_affected: 1` in cloud until the `/user` gateway route + user-api are available** (Finding 2 — a services dependency, not a mobile fix). Q1: the persisted mapping is sufficient; the optional param is a nice-to-have. Version is correct at `2.1.1+3`.
