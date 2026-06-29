# Tasks for Mobile Amazon-Q (Audioura Android app)

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code + Android build only. (GCloud services are Kiro's; iOS *build mechanics* are iOS Amazon-Q's — but the Dart you write here is shared, see §iOS.)
**Source:** Phase E gateway review.

> All of this is shared Dart in `lib/`. Do **not** ask Kiro to change services for these, and do **not** make iOS-specific edits — iOS inherits your Dart automatically (see the iOS section).

---

## M1 — Route tour generation through `Endpoints` (the cloud-generation blocker)  ⭐ critical
Tour generation/status/job-download still hardcode `http://$serverIp:5002`, so in cloud mode they hit the LAN IP and fail off-WiFi. Migrate **all six sites** to the orchestrator via the gateway:

| File | Lines | Change |
|---|---|---|
| `screens/tour_generator_screen.dart` | 37, 107 | delete `_apiBaseUrl` field (and its `.217` default) |
| `screens/tour_generator_screen.dart` | 202, 1283 | `POST` → `Endpoints.url(Service.orchestrator, '/generate-complete-tour')` |
| `screens/tour_generator_screen.dart` | 1448 | `GET` → `Endpoints.url(Service.orchestrator, '/status/$id')` |
| `screens/tour_generator_screen.dart` | 1464 | `GET` → `Endpoints.url(Service.orchestrator, '/download/$id')` |
| `services/background_service.dart` | 105, 111 | `GET` → `Endpoints.url(Service.orchestrator, '/download/$jobId')` |
| `services/background_tour_monitor.dart` | 146 | same |

After this, cloud mode routes generation through the gateway → orchestrator. This is the gate for testing "generate a tour on cellular."

## M2 — Switch tour-status writes to Kiro's REST endpoint (after K1 lands)
Kiro is adding `POST /tour-status` on the orchestrator (he'll publish the exact body/response). When ready:
- Change `services/tour_status_service.dart` to call `Endpoints.url(Service.orchestrator, '/tour-status')` instead of `DirectDbUpdate`.
- **Delete** the six near-duplicate raw-SQL updaters: `direct_db_update.dart`, `direct_jdbc_update.dart`, `direct_postgres_connection.dart`, `direct_update_api.dart`, `postgres_direct.dart`, `server_api.dart`. (These were never "DEV ONLY" — they were the live status path; the comment was wrong.)
- Remove/guard `api_tester.dart` (genuine test harness — fine to exclude from release).
**Blocked on:** Kiro publishing the K1 contract. Do M1 first; M2 when K1 is ready.

## M3 — Small follow-ups from the v2.1.1 review
- `config/endpoints.dart`: make the prefix interpolation explicit — `'$cloudBase${_cloudPaths[s] ?? ''}'` (prevents a silent `"null"` if a new `Service` is added without a path). Low priority.
- Audit for any other lingering `.217` defaults and `http://$serverIp:` literals that bypass `Endpoints` (the generation flow was the big one; confirm nothing else routes around the resolver).

## M4 — Build, version, and test on Android
- Bump `pubspec.yaml` version (e.g., `2.1.2+1`).
- Smoke test **local WiFi** first (regression: generation still works via LAN).
- Then **cloud generation on cellular:** About → Cloud, `cloud_base_url = <gateway URL>` (Kiro's `api-gateway-…run.app` now, `https://api.audioura.com` later), "gateway path routing" **unchecked** (the nginx gateway routes by root path), go off-WiFi, generate a tour.
- Expectation: generation runs and the tour becomes downloadable; `/status` polling reports progress. Until K1+M2 land, "My Tours" status bookkeeping may be off — that's expected.

---

## iOS correlation (hand this section to iOS Amazon-Q)

Everything above is **shared Flutter Dart** — iOS does **not** re-implement any of it. For the correlated iPhone build, iOS Amazon-Q should:
1. Build the **same commit** of `services-migration` (the one carrying M1–M3), from the shared `lib/`.
2. Keep the version in lockstep — it's driven by the shared `pubspec.yaml`, so the iOS build number matches automatically. `flutter pub get` → `cd ios && pod install` → build/sign the `Runner` target.
3. **No iOS networking/Info.plist change needed:** local-mode HTTP already works on iPhone (Flutter's `dart:io` HttpClient bypasses iOS ATS), and cloud mode is HTTPS. Optional only: add `NSLocalNetworkUsageDescription` for cleaner iOS 14+ prompts.
4. Run the same parity smoke tests (local generation, cloud generation off-WiFi, existing-tour download, refresh-no-black-screen, mic voice search).

iOS makes **no Dart edits** — doing so would fork the codebase. iOS-only files that may legitimately change are confined to `ios/` (Info.plist, signing, Podfile).

---

### Order
M1 now (unblocks cloud generation testing) → M4 test → M2 once Kiro ships K1 → M3 cleanup anytime. iOS builds the same commit after M1 (and again after M2).
