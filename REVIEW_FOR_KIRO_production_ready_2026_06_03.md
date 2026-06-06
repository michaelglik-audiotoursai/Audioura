# Review for Kiro Amazon-Q — K1–K9 Production Readiness (Services)

**Date:** 2026-06-03
**Scope:** Services/GCloud only.
**Liveness:** ✅ **`https://api.audioura.com` is live** — I fetched `GET /health` independently and got `{"auth":"enabled","service":"api-gateway","status":"healthy"}` over HTTPS through Cloudflare + the GCP LB.
**Production-readiness verdict:** ✅ **Production-ready for the tour flow** (list, resolve, download from R2, generate, status, tour-status). **Two items to fix before relying on it broadly:** a route collision that breaks **news** downloads, and an **open cost-bearing endpoint** that the "budget protection" claim doesn't actually cover. Details below.

---

## What I verified is solid
- **Live + TLS:** `/health` answers through Cloudflare (Full strict) → GCP LB (Google-managed cert, `34.36.147.30`) → gateway. Confirmed first-hand.
- **K3 genuinely resolved:** the gateway (`api-gateway/main.py`) is a Python auth-proxy that mints Google identity tokens from the metadata server and attaches `Authorization: Bearer …` per backend; backends are claimed `--no-allow-unauthenticated`. This is the right pattern and a real improvement over the earlier nginx setup. The `Authorization` header is correctly **overwritten** with the minted token (client can't inject its own), and host/length/transfer-encoding headers are stripped both ways.
- **K1 status endpoint:** code is sound (whitelisted status, parameterized SQL, `finished_at` on completed, matches on `tour_id`), and `rows_affected: 1` confirms it updates real rows.
- **K2 hardening:** explicit routes + 404 errorhandler. Good.
- **K7/K8:** DB reads work with no public IP (unix-socket connector verified by passing queries). Secrets in Secret Manager. R2 dual-read on map-delivery.

So the tour path is genuinely production-grade.

---

## 🔴 Finding 1 — `/download/<id>` route collision breaks NEWS downloads
In `main.py` there are **two** routes with the same URL rule:
- line 109: `@app.route('/download/<job_id>')` → **orchestrator** (tour job ZIP)
- line 141: `@app.route('/download/<article_id>')` → **news-orchestrator** (news article)

Flask/Werkzeug registers both but matches the **first** for any `/download/<anything>`, so **`download_article` is dead** — every `/download/...` goes to the orchestrator. News article downloads (the app hits `…/download/<article_id>`) will mis-route to the orchestrator and fail. Tours are unaffected (they use `/download-tour/<id>`), which is why your 6 smoke tests passed — none exercise news download.

**Fix:** give news downloads a distinct path, e.g. `@app.route('/news-download/<article_id>')` → news-orchestrator (and align the app's news-download path when news is wired). Do this before cloud news article download is relied on (K6 just deployed news, so it's now reachable in principle).

---

## 🔴 Finding 2 — "budget protection" is incomplete: the public gateway still proxies generation
The security table says *"Backends locked — unauthenticated users can't trigger OpenAI/Polly spend."* That's only half true. The **backends** can't be hit directly (good, IAM-locked), but the **gateway is public and forwards** `/generate-complete-tour` and `/translate-with-audio` to those backends **with a valid minted token**. So anyone who knows `https://api.audioura.com/generate-complete-tour` can `POST` and trigger OpenAI + Polly spend. The IAM lock prevents *bypassing* the gateway; it does **not** prevent abuse *through* it. Cloudflare gives DDoS protection, not per-call authorization.

**This is the most important remaining item.** A scripted attacker could run up a real OpenAI/AWS bill. Recommended, in order:
1. **Immediate, cheap:** set a **GCP billing budget + alert** (and an OpenAI usage cap) so runaway spend is bounded and visible. Optionally a Cloudflare **rate-limit/WAF rule** on `/generate-complete-tour` and `/translate-with-audio`.
2. **Real fix:** require a **client credential** on the cost-bearing endpoints — a shared API key the mobile app sends in a header the gateway verifies, or app-attestation / a signed token. Read-only endpoints (`/tours-near`, `/download-tour`, `/tour/<id>/resolve`) can stay open; gate the ones that cost money or write data (`/generate-complete-tour`, `/translate-with-audio`, `/tour-status`).

Until one of these is in place, treat the deployment as a **soft launch** — fine for your own testing, risky to publicize the URL.

---

## 🟡 Minor / verify
- **Confirm the IAM lock empirically:** `curl` a backend `*.run.app` directly (e.g. map-delivery) and confirm **403**. The code mints tokens, but please verify the deployed `--no-allow-unauthenticated` flag is actually applied to all 10 backends, not just intended.
- **Proxy buffers the whole body:** `proxy_request` uses `stream=True` but then reads `resp.content` (full body in memory). Fine for ≤19 MB ZIPs, but with `api-gateway` at `max-instances=3` and concurrent large downloads, memory can spike — make sure the gateway Cloud Run service has adequate memory, or switch to true streaming (`resp.iter_content`). Low priority.
- **Token-fetch failure path:** if the metadata token fetch fails, `proxy_request` forwards with **no** `Authorization` → the backend returns 403 → client sees an error. That's acceptable (fails closed), just worth a log/alert so a metadata hiccup is visible.

## Acknowledged / correct as-is
- **DatabaseJobStore not wired + `max=1` pins** on orchestrator/generator/modernized/news — correct for `JOB_STORE_MODE=memory`. Keep the pins until it's wired; don't let those autoscale.
- **`--clear` deferred** — right call; keep BYTEA until R2 delivery is verified in production (~1 week), then `--verify` → `--clear`.
- **Cost floor ~$28.50/mo** — reasonable; stopping Cloud SQL between sessions is a fine optional saving.

---

## Bottom line
`api.audioura.com` is **live and production-ready for the tour flow** — confirmed first-hand, with a clean LB + Cloudflare + IAM-locked-backends architecture. Before broad/public exposure, close the two findings: (1) fix the `/download` collision so **news** downloads route to news-orchestrator, and (2) close the budget-abuse vector on the public generation/translation endpoints (billing alert now; client auth/rate-limit as the real fix). The minor items are cleanup. Nothing here concerns the mobile app.
