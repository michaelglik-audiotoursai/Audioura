# Claude Review — Phase E API Gateway + Generation Pipeline (commits `6c2c97f`, `0bbb195`)

**Date:** 2026-06-03
**Reviewing:** `claude_review_phase_e_gateway_2026_06_03.md` (Kiro)
**Verdict:** ✅ The nginx gateway is well-built and the server-side pipeline is correctly wired — you can drive end-to-end generation **with curl against the gateway today.** ❌ **But the mobile app cannot trigger cloud generation yet**: the entire generate/status/download-by-job flow in the app still calls `http://$serverIp:5002` directly, bypassing `Endpoints`/the gateway. So "tour generation via gateway: ready to test" is true for curl, not for the phone. That missing mobile migration is the #1 fix. Plus the 5 questions.

---

## 1. The gateway nginx config — correct for the routes it handles
I read `api-gateway/nginx.conf`. The routing is sound:
- `/tours-near/`, `/download-tour/`, `/tour/(\d+)/resolve`, `/search-tours` → map-delivery ✅
- `/generate-complete-tour`, `/status/`, `/jobs` → orchestrator ✅
- `/translate-with-audio` → translation ✅
- `proxy_ssl_server_name on` + `Host: <backend>.run.app` is exactly right for Cloud Run SNI routing ✅
- trailing-slash `proxy_pass` semantics and `$request_uri` on the regex/`/status/` locations are correct ✅

The resolve consolidation is consistent: the app's `Service.tourIdResolution` path `/tour/<id>/resolve` lands on map-delivery (which now hosts that endpoint), matching the gateway rule. Good. So **server-side, the pipeline is genuinely wired** and testable via curl.

---

## 2. 🔴 The blocker — the mobile app's generation flow bypasses the gateway
The download/list paths were migrated to `Endpoints` in v2.1.1, **but tour generation was not.** It still hardcodes `http://$serverIp:5002`:

- `tour_generator_screen.dart:37` — `_apiBaseUrl = 'http://192.168.0.217:5002'` (also still the `.217` default the v2.1.1 review claimed was removed)
- `tour_generator_screen.dart:107` — `_apiBaseUrl = 'http://$serverIp:5002'`
- `:202` / `:1283` — `POST $_apiBaseUrl/generate-complete-tour`
- `:1448` — `GET http://$serverIp:5002/status/<id>`
- `:1464` — `GET http://$serverIp:5002/download/<id>`
- `background_service.dart:105/111`, `background_tour_monitor.dart:146` — `GET http://$serverIp:5002/download/<jobId>`

In **cloud mode** `serverIp` is the LAN IP (`192.168.0.218`), which is **unreachable off-WiFi**. So from the phone in cloud mode, generation POST, status polls, and the job download all fail — they never reach the gateway. **Cloud tour generation is not testable from the device until these are migrated to `Endpoints.url(Service.orchestrator, '/...')`.**

**Fix (Mobile Amazon-Q):** migrate all six sites above to the orchestrator service via `Endpoints`, e.g.:
```dart
final genUri = await Endpoints.url(Service.orchestrator, '/generate-complete-tour');
final statusUri = await Endpoints.url(Service.orchestrator, '/status/$id');
final dlUri = await Endpoints.url(Service.orchestrator, '/download/$jobId');
```
Drop the `_apiBaseUrl` field entirely. After this, cloud mode routes generation through the gateway → orchestrator. (Also fixes the lingering `.217` default.) Until this ships, the gateway generation test can only be done with curl, not the app.

---

## 3. Answers to the five questions

**Q1 — Host header "secrets" + backend auth.** Two parts:
- The `Host: <backend>.run.app` header is **not a secret** — it's just the Cloud Run hostname, required for routing. No concern there.
- The real concern is that the gateway **and** the backends are `--allow-unauthenticated`. That means anyone on the internet can POST directly to `tour-orchestrator/generate-complete-tour` and trigger OpenAI + Polly work → **cost-abuse risk** (someone runs up your OpenAI/AWS bill). For a short, attended test it's tolerable. Before anything longer: make backends `--no-allow-unauthenticated` and have the gateway attach a Google-signed **identity token** (`Authorization: Bearer …` for the backend's audience) so only the gateway can invoke them. A lightweight interim is a shared-secret header the backends check, but IAM identity tokens are the real answer.

**Q2 — catch-all → 404?** Yes, tighten it — but carefully, because the app reaches the orchestrator's `/download/<jobId>` **through** the catch-all today. So don't just 404 everything: replace the catch-all with **explicit** orchestrator routes (`/download/`, `/generate-complete-tour`, `/status/`, `/jobs`) and make the default `location /` `return 404`. That stops unknown paths from probing the orchestrator while keeping the job-download path working.

**Q3 — `proxy_read_timeout 300`.** Depends on whether generation is async. If `/generate-complete-tour` returns a `job_id` quickly and the app polls `/status` (which is the pattern your logs show — "status: queued"), then 300s is plenty and you should **keep it async**. If it blocks until the tour is fully built, 300s is risky **and raising nginx alone won't help** — you'd also have to raise the **api-gateway's own Cloud Run request timeout** (default 300s) *and* the **orchestrator's** `--timeout`, all three. Recommendation: confirm the async/poll model and keep it; don't rely on a multi-minute synchronous HTTP call through two Cloud Run hops. If any leg is synchronous, set all three timeouts to 600.

**Q4 — translation/coordinates secrets as plain env vars.** Migrate them back to Secret Manager. A plaintext OpenAI key in a Cloud Run env var is visible to anyone with Cloud Run **viewer** IAM and persists in **revision history** — a meaningful exposure. You now have the reliable no-newline workflow (`[IO.File]::WriteAllText` → `--data-file`), so there's no reason to keep them inline. Should-fix before production; acceptable only for the short test window.

**Q5 — delete the failed `tour-id-resolution` service.** Yes. It's redundant (resolve moved to map-delivery), never deployed cleanly, and a dangling/failed Cloud Run service is just clutter and one more public surface. Remove it.

---

## 4. Deliverable A interplay — set test expectations
Even after §2 is fixed, note: the app's **separate** status bookkeeping via `TourStatusService`/`DirectDbUpdate` (raw SQL to `:5003`) still won't work in cloud (it uses `serverIp` directly and `:5003` isn't deployed). The app's `tour_generator_screen` status **polling** of `/status` will work once migrated (§2), so generation progress/completion can be tracked — but any place that writes status via `DirectDbUpdate` will silently fail in cloud. So when you test cloud generation after §2: expect the tour to generate and become downloadable, and `/status` polling to report progress, but don't be surprised if "My Tours" status bookkeeping is off until **Deliverable A (REST status endpoint)** lands.

---

## 5. Bottom line
- **Gateway: approved.** nginx routing is correct; server-side generation pipeline is wired and curl-testable now.
- **🔴 Mobile blocker:** generation/status/job-download still hit `serverIp:5002` directly — migrate those six sites to `Endpoints(Service.orchestrator)` (Mobile AQ) before the phone can do cloud generation. This is the gate for your "generate a tour on cellular" test.
- **Before more than a short test:** lock backends behind IAM (Q1), tighten the catch-all to 404 + explicit routes (Q2), move the OpenAI keys back to Secret Manager (Q4), delete the dead resolution service (Q5), and confirm generation stays async (Q3).
- News/newsletter (C), data import (D), and DB lockdown (E) remain per the spec — not needed for the tour-generation test, but newsletters won't work on cloud until C + D land.
