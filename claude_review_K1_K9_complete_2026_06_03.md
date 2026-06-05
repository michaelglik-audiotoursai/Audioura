# Claude.AI Final Code Review — K1–K9 Tasks Complete

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Scope:** All service-side tasks for cloud production readiness

---

## 1. What Changed in Each Service

### `tour_orchestrator_service.py`
- Added `POST /tour-status` endpoint (K1) — accepts `{tour_id, status}`, updates `tour_requests` table via DB, returns `{status, tour_id, rows_affected}`
- `app.run` changed to `port=int(os.getenv('PORT', '5002')), debug=False`
- All DB connections use `os.getenv()` (from earlier Phase B)
- Inter-service URLs all env-var-driven, set to Cloud Run URLs in deployment

### `map_delivery_service.py`
- Added `GET /tour/<id>/resolve` endpoint (for mobile app tour resolution)
- All 5 `audio_tours` queries widened to `(audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)`
- R2 dual-read logic on all paths that consume blob data
- R2 lazy-init helper `_get_blob_storage()`
- `app.run` changed to `PORT` env var + `debug=False`

### `api-gateway/nginx.conf` (K2)
- Explicit routes only: `/tours-near/`, `/download-tour/`, `/tour/ID/resolve`, `/search-tours`, `/generate-complete-tour`, `/status/`, `/download/`, `/tour-status`, `/jobs`, `/translate-with-audio`, `/sync`
- Catch-all returns `404` JSON (not proxy to orchestrator)
- `proxy_read_timeout 600` for generation endpoints
- `proxy_ssl_server_name on` + correct Host headers for Cloud Run SNI

### All 9 active service files
- `app.run(debug=True)` → `app.run(port=int(os.getenv('PORT', 'XXXX')), debug=False)`
- DB credentials via `os.getenv()` (Phase B)

### `blobstorage.py`
- R2 endpoint URL auto-strips bucket-path suffix
- `upload()` returns bare key (not `r2://` URI)
- Retry config: `max_attempts=3`, `connect_timeout=10`, `read_timeout=30`

### `job_store.py`
- Both MemoryJobStore and DatabaseJobStore functional
- Services use `.update()` method (not nested dict mutation) for DB-mode safety

---

## 2. Key Decisions + Issues Hit

| Decision | Rationale |
|----------|-----------|
| Nginx proxy vs GCP Load Balancer | $0/month (scales to zero) vs $18/month. Nginx chosen for testing; LB for production later. |
| K3 (backend auth) deferred | Nginx can't inject OIDC tokens. Proper fix requires custom proxy or GCP LB with IAM. Documented as production requirement. |
| Cloud SQL connector (unix socket) | Free, no public IP needed, no VPC connector hourly billing. |
| Single Docker image for all services | Simpler build/push, ~400 MB. Per-service images are a later optimization. |
| `JOB_STORE_MODE=memory` + pin max=1 | Pragmatic for testing. DatabaseJobStore ready but not wired into orchestrator yet. |
| Secret Manager newline issue | PowerShell `echo` adds `\r\n`. Fix: `[IO.File]::WriteAllText` + `--data-file`, or web console. |

### Issues Hit:
1. **Missing Python modules** (9 files existed only in Docker container, never committed — recovered)
2. **Flask `debug=True`** delays port binding past Cloud Run startup probe
3. **`COPY *.py`** in Dockerfile grabbed stale files that broke imports → `.dockerignore` created
4. **R2 secret key was 63 chars** (should be 64) — user re-pasted correct key
5. **DB password committed to git** — rotated immediately, doc scrubbed

---

## 3. Smoke Test Results (All 6 Pass)

```
Test 1 — Health:         ✅ {"status":"healthy","service":"api-gateway"}
Test 2 — Tours-near:     ✅ HTTP 200, 76,175 bytes (191 tours)
Test 3 — Tour resolve:   ✅ {"status":"success","tour_id":"313","tour_name":"Faneuil Hall..."}
Test 4 — Tour download:  ✅ HTTP 200, 3,640,106 bytes (from R2)
Test 5 — 404 catch-all:  ✅ {"error":"endpoint not found","service":"api-gateway"}
Test 6 — Tour-status:    ✅ {"status":"success","rows_affected":0}
```

Mobile off-WiFi tests also passed:
- Map loads 191 tours ✅
- Tour resolve + download works ✅
- Vietnam tours visible via location search ✅

---

## 4. Gotchas for Mobile-AQ

### K1 Contract — Tour Status API:
```
POST /tour-status
Content-Type: application/json
Body: {"tour_id": "tour_19e73f4059d", "status": "completed|failed|started|processing"}
Response: {"status": "success", "tour_id": "...", "rows_affected": 1}
```

### Endpoint availability via gateway:
| Path | Available | Notes |
|------|-----------|-------|
| `/tours-near/{lat}/{lng}` | ✅ | Returns tour list |
| `/download-tour/{id}` | ✅ | Returns ZIP from R2 |
| `/tour/{id}/resolve` | ✅ | Returns tour metadata |
| `/generate-complete-tour` | ✅ | POST, returns job_id |
| `/status/{job_id}` | ✅ | Poll for generation progress |
| `/tour-status` | ✅ | POST to update tour request status |
| `/translate-with-audio` | ✅ | POST for translation |
| `/sync` | ⚠️ Stub | Returns `{"status":"success"}` (placeholder) |
| `/process_newsletter` | ❌ | Not yet deployed (K6 pending) |

### Important for mobile app:
- Use `https://api-gateway-60899077572.us-central1.run.app` as cloud base URL
- All paths are at root (no port numbers, no `/map-delivery/` prefix)
- Gateway path routing checkbox: **OFF** (nginx routes by root path already)
- The `/sync` endpoint is a stub — full user sync needs `user-api` deployed

---

## 5. Gotchas for Production

| Item | Status | Risk |
|------|--------|------|
| Backend auth (K3) | **DEFERRED** — all backends publicly accessible | Anyone can call orchestrator and spend OpenAI/Polly budget. Lock down before broad use. |
| Cloud SQL `0.0.0.0/0` | ✅ Cleared | Services connect via unix socket connector |
| DB password in git history | Rotated (defunct) | Low risk — old value doesn't work. BFG clean optional. |
| `--clear` for BYTEA columns | **NOT RUN** — dual-read active | Safe to run after production verification period |
| Custom domain (`api.audioura.com`) | **DNS action needed** | Sir Michael adds CNAME: `api` → `api-gateway-60899077572.us-central1.run.app` in Cloudflare |
| News/newsletter services (K6) | **Not yet deployed** | Only tour generation + download works on cloud |

---

## 6. K1–K9 Final Status

| Task | Status | Notes |
|------|--------|-------|
| K1 — Tour status endpoint | ✅ | `POST /tour-status` deployed |
| K2 — Gateway hardening | ✅ | 404 catch-all, explicit routes |
| K3 — Backend auth | ⚠️ Deferred | Nginx can't do OIDC; needs custom proxy or LB |
| K4 — Secrets to Secret Manager | ✅ | translation + coordinates migrated |
| K5 — Delete failed service | ✅ | tour-id-resolution removed |
| K6 — News/newsletter pipeline | Pending | Separate deploy session |
| K7 — Cloud SQL data import | ✅ | All tables imported (article_requests, news_audios, custom_tours) |
| K8 — Lock down Cloud SQL | ✅ | Unix socket connector, `0.0.0.0/0` cleared |
| K9 — Production domain | ⚠️ DNS needed | Sir Michael adds CNAME in Cloudflare |
