# Claude Review — Services K1–K9 + Mobile v2.1.2+1 (M1)

**Date:** 2026-06-03

---

# PART A — Services (K1–K9), commit set on `services-migration`

**Verdict:** ✅ Solid. Gateway hardening, the status endpoint, secrets, DB lockdown, and data import are all done and verified. One production risk remains (K3, acknowledged) and one test gap to close (the status endpoint wasn't actually exercised against a real row).

### Verified in code
- **K2 gateway** (`api-gateway/nginx.conf`): explicit routes for all needed paths, `/download/` and `/tour-status` added, **catch-all now `return 404`** (no longer proxies unknown paths to the orchestrator), `proxy_read_timeout 600` on generation. Correct. ✅
- **K1 status endpoint:** `@app.route('/tour-status', methods=['POST'])` exists (`tour_orchestrator_service.py:1004`). ✅
- **K7/K8:** the DB-querying smoke tests pass (tours-near returns 191 tours) **with `0.0.0.0/0` cleared**, which proves the unix-socket Cloud SQL connector works — K8 is verified by the fact that DB reads still succeed without the public IP. ✅

### Two things to address
1. **K1 was not actually verified to update a row.** Smoke Test 6 returned `{"rows_affected": 0}` — the endpoint returned 200 but matched **no** row. So you've proven it's wired, not that it works. Re-test with a **real** `tour_id` that exists in `tour_requests` and confirm `rows_affected: 1`. Also note the **contract for Mobile M2**: the endpoint keys on `tour_id` (updating `tour_requests`), whereas the old client path matched on `request_string` — Mobile AQ must send the `tour_xxx` id the app actually holds, or it'll repeat the `rows_affected: 0` no-op. Please confirm the app has that id at status-update time.
2. **K3 (backend auth) is the main outstanding production risk.** All backends are `--allow-unauthenticated`, so anyone can POST `tour-orchestrator/generate-complete-tour` and burn your OpenAI/Polly budget. The "nginx can't do OIDC" rationale is an over-simplification — it's *awkward*, not impossible (njs/lua fetching a token from the metadata server), but the cleaner path is a tiny auth proxy that mints ID tokens, or the GCP LB with IAM. **Acceptable for a short, attended test; lock down before broad/unattended use.** Keep the gateway the only public surface and set backends `--no-allow-unauthenticated` when you do.

Everything else (K4 secrets→Secret Manager, K5 delete dead service, K7 import incl. `custom_tours`) is done. K6 (news/newsletter) and K9 (DNS) remain as planned.

---

# PART B — Mobile Android v2.1.2+1 (M1), commit `40a9152`

**Verdict:** ✅ The foreground generation flow is correctly migrated — but **M1 is incomplete**: two more orchestrator calls and one map-delivery call still hardcode the LAN IP, so parts of the cloud flow (background-completion download and **multi-language** translated-version download) will still fail off-WiFi. Fix those before the cloud generation test, especially since you generate multi-language tours routinely.

### Verified migrated (foreground) ✅
`tour_generator_screen.dart` lines 191, 248, 523, 546, 703, 1273 all use `Endpoints.url(Service.orchestrator, …)`. The six sites in the doc are done, and `background_service.dart` / `background_tour_monitor.dart` are migrated too.

### 🔴 Missed sites still on the LAN IP (will break in cloud)
1. **`_downloadBackgroundTour` (`tour_generator_screen.dart:1427`)** — still hardcodes:
   - line 1436: `http://$serverIp:5002/status/${tour['id']}`
   - line 1452: `http://$serverIp:5002/download/${tour['id']}`
   - line 1430: `?? '192.168.0.217'` (another lingering `.217`)
   This is the path that downloads a tour that completed **while the app was backgrounded**. In cloud mode it hits the LAN IP → the background-completion download fails. Migrate both to `Endpoints.url(Service.orchestrator, …)` and drop the `serverIp`/`.217`.
2. **`_processAdditionalLanguages` (`tour_generator_screen.dart:424`)** — `http://$serverIp:5005/download-tour/$translatedId` (their Q5). This downloads the **translated** versions of a multi-language tour. Since you routinely generate RU/KO tours, this **breaks multi-language cloud generation** at the translated-download step. Not just cleanup — migrate to `Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId')` now.

So the net: a single-language foreground tour will generate+download in cloud, but a backgrounded completion or a multi-language tour will fail on download until these three lines are migrated.

### Answers to the five questions
- **Q1 (background_service uses `Endpoints` instead of stored `apiBaseUrl`):** Correct approach. The stored `apiBaseUrl` was a stale snapshot of the LAN URL — wrong in cloud mode. Reading the current mode via `Endpoints` is right.
- **Q2 / Q3 (dead `apiBaseUrl` / `serverIp` reads):** Remove them in `background_service.dart` — low priority but cheap. ⚠️ Caveat: don't blanket-assume `serverIp` is dead everywhere — in `_downloadBackgroundTour` it's **still live** (feeding the unmigrated 1436/1452). Remove only after those are migrated.
- **Q4 (`Endpoints.url()` async in `Timer.periodic` / background):** Safe **if these run in the main isolate** (an in-app `Timer.periodic`) — an `async` callback can `await`, and `SharedPreferences` works. The risk is only if `background_service`/`background_tour_monitor` run in a **true background isolate** (Android foreground-service plugin): there, `SharedPreferences.getInstance()` needs `DartPluginRegistrant.ensureInitialized()` and re-reads native prefs. Please confirm which, and **test that a backgrounded tour completes and downloads in cloud mode** — that exercises both this and the §missed-site #1 fix.
- **Q5 (`_processAdditionalLanguages` `:5005`):** Yes — migrate now (see above). It's a real cloud bypass for multi-language tours, not optional cleanup.

### Note on M3 deferrals
Leaving the news (`:5012`) and newsletter (`:5017`) calls hardcoded is fine for now — those services aren't deployed (K6 pending) and aren't part of M1. Migrate them to `Endpoints(Service.news / Service.newsletter)` when K6 lands and you want cloud news/newsletters.

---

## Bottom line
- **Services:** approved; re-test `/tour-status` against a real row (rows_affected:1), and lock down backends (K3) before broad use.
- **Mobile:** M1 foreground is correct, but **finish the migration** — `_downloadBackgroundTour` (1436/1452, + `.217`) and `_processAdditionalLanguages` (424) — before the cloud generation test, and specifically test a **multi-language** and a **backgrounded** generation in cloud mode, since those are the two paths the missed sites affect.
