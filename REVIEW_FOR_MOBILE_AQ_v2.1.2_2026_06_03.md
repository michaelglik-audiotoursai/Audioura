# Review for Mobile Amazon-Q — Android v2.1.2+1 (M1), commit `40a9152`

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Verdict:** ✅ The foreground generation flow is correctly migrated — but **M1 is incomplete**: two more orchestrator calls and one map-delivery call still hardcode the LAN IP, so parts of the cloud flow (background-completion download and **multi-language** translated-version download) will still fail off-WiFi. Fix those before the cloud generation test — especially since Sir Michael generates multi-language tours routinely.

---

## Verified migrated (foreground) ✅
`tour_generator_screen.dart` lines 191, 248, 523, 546, 703, 1273 all use `Endpoints.url(Service.orchestrator, …)`. The six sites in your doc are done, and `background_service.dart` / `background_tour_monitor.dart` are migrated too.

## 🔴 Missed sites still on the LAN IP (will break in cloud)

1. **`_downloadBackgroundTour` (`tour_generator_screen.dart:1427`)** — still hardcodes:
   - line 1436: `http://$serverIp:5002/status/${tour['id']}`
   - line 1452: `http://$serverIp:5002/download/${tour['id']}`
   - line 1430: `?? '192.168.0.217'` (another lingering `.217`)
   This is the path that downloads a tour that completed **while the app was backgrounded**. In cloud mode it hits the LAN IP → background-completion download fails. Migrate both to `Endpoints.url(Service.orchestrator, …)` and drop the `serverIp`/`.217`.

2. **`_processAdditionalLanguages` (`tour_generator_screen.dart:424`)** — `http://$serverIp:5005/download-tour/$translatedId` (your Q5). This downloads the **translated** versions of a multi-language tour. Since RU/KO tours are generated routinely, this **breaks multi-language cloud generation** at the translated-download step. Not just cleanup — migrate to `Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId')` now.

Net: a single-language foreground tour will generate+download in cloud, but a backgrounded completion or a multi-language tour will fail on download until these three lines are migrated.

## Answers to your five questions
- **Q1 (background_service uses `Endpoints` instead of stored `apiBaseUrl`):** Correct approach. The stored `apiBaseUrl` was a stale snapshot of the LAN URL — wrong in cloud mode. Reading the current mode via `Endpoints` is right.
- **Q2 / Q3 (dead `apiBaseUrl` / `serverIp` reads):** Remove them in `background_service.dart` — low priority but cheap. ⚠️ Caveat: don't assume `serverIp` is dead everywhere — in `_downloadBackgroundTour` it's **still live** (feeding the unmigrated 1436/1452). Remove only after those are migrated.
- **Q4 (`Endpoints.url()` async in `Timer.periodic` / background):** Safe **if these run in the main isolate** (an in-app `Timer.periodic`) — an `async` callback can `await`, and `SharedPreferences` works. The risk is only if `background_service`/`background_tour_monitor` run in a **true background isolate** (Android foreground-service plugin): there, `SharedPreferences.getInstance()` needs `DartPluginRegistrant.ensureInitialized()` and re-reads native prefs. Please confirm which, and **test that a backgrounded tour completes and downloads in cloud mode** — that exercises both this and missed-site #1.
- **Q5 (`_processAdditionalLanguages` `:5005`):** Yes — migrate now (see above). It's a real cloud bypass for multi-language tours, not optional cleanup.

## M2 — coming next (do NOT start until Kiro publishes the contract)
When Kiro ships the `POST /tour-status` contract, you'll switch `tour_status_service.dart` from `DirectDbUpdate` to `Endpoints.url(Service.orchestrator, '/tour-status')` and delete the six raw-SQL updater classes. Heads-up from the services review: that endpoint keys on **`tour_id`** (the `tour_xxx` request id), not `request_string` — make sure the app sends the id the endpoint expects (Kiro will confirm), or the update will silently affect 0 rows.

## M3 deferrals — fine for now
Leaving the news (`:5012`) and newsletter (`:5017`) calls hardcoded is acceptable — those services aren't deployed yet and aren't part of M1. Migrate them to `Endpoints(Service.news / Service.newsletter)` when the news/newsletter services land and you want cloud news/newsletters.

## iOS correlation (hand this to iOS Amazon-Q)
These are shared Dart changes — iOS does **not** re-implement them. Once you commit the fixes above, iOS Amazon-Q builds the **same commit** from the shared `lib/` (no Dart edits, no Info.plist/ATS change needed), keeps the version in lockstep (driven by `pubspec.yaml`), runs `pod install`, and runs the parity smoke tests — including a **multi-language** and a **backgrounded** cloud generation, since those are the paths the missed sites affect.

## Bottom line
M1 foreground is correct, but **finish the migration** — `_downloadBackgroundTour` (1436/1452, + `.217`) and `_processAdditionalLanguages` (424) — before the cloud generation test, and specifically test a **multi-language** and a **backgrounded** generation in cloud mode. M2 waits on Kiro's contract.
