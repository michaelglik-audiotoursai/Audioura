# Claude.AI Code Review — Phase E: API Gateway + Full Tour Generation Pipeline

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commits:** `6c2c97f`, `0bbb195`  
**Scope:** Deploy remaining services, wire inter-service URLs, create nginx API gateway  
**Status:** Full tour generation pipeline deployed; single URL for mobile app

---

## What was deployed

### New Cloud Run services (this session):

| Service | URL | Purpose |
|---|---|---|
| translation-service | `https://translation-service-60899077572.us-central1.run.app` | Multi-language tour translation |
| coordinates | `https://coordinates-60899077572.us-central1.run.app` | OpenAI-based geocoding |
| **api-gateway** | `https://api-gateway-60899077572.us-central1.run.app` | **Nginx reverse proxy — single entry point** |

### Updated services:

| Service | Change |
|---|---|
| tour-orchestrator | Inter-service URLs updated: TOUR_GENERATOR_URL, MODERNIZED_URL, TRANSLATION_URL, COORDINATES_URL, POLLY_TTS_URL now point to their Cloud Run URLs |

### Total Cloud Run services now: 8

| Service | Role | Status |
|---|---|---|
| api-gateway | Nginx reverse proxy (single URL) | ✅ |
| map-delivery | Tour list + download (R2) | ✅ |
| tour-orchestrator | Tour workflow coordination | ✅ |
| tour-generator | AI text generation (OpenAI) | ✅ |
| tour-modernized | Audio + ZIP creation (Polly) | ✅ |
| polly-tts | AWS Polly TTS wrapper | ✅ |
| translation-service | Multi-language translation | ✅ |
| coordinates | Location geocoding (OpenAI) | ✅ |

---

## API Gateway Design (Deliverable B — cheap nginx variant)

**File:** `api-gateway/Dockerfile` + `api-gateway/nginx.conf`

A minimal nginx reverse-proxy on Cloud Run that routes by URL path to the correct backend service:

```
Mobile App → https://api-gateway-...run.app/{path}
    /tours-near/*           → map-delivery
    /download-tour/*        → map-delivery
    /tour/ID/resolve        → map-delivery
    /search-tours           → map-delivery
    /generate-complete-tour → tour-orchestrator
    /status/*               → tour-orchestrator
    /translate-with-audio   → translation-service
    /* (catch-all)          → tour-orchestrator
```

### Key nginx config decisions:

- `proxy_ssl_server_name on` — required for Cloud Run (SNI-based routing)
- `proxy_set_header Host <backend>.run.app` — Cloud Run requires the correct Host header
- `proxy_read_timeout 300` for generation (can take minutes)
- Regex route for `/tour/(\d+)/resolve` to match the resolve pattern

### Cost:
- **$0/month when idle** (Cloud Run scales to zero)
- Negligible per-request cost at test volume
- vs. $18/month for a GCP Load Balancer (the "proper" solution for production)

---

## Inter-Service URL Wiring

The orchestrator now has all service URLs configured:

```
TOUR_GENERATOR_URL=https://tour-generator-60899077572.us-central1.run.app
MODERNIZED_URL=https://tour-modernized-60899077572.us-central1.run.app
TRANSLATION_URL=https://translation-service-60899077572.us-central1.run.app
COORDINATES_URL=https://coordinates-60899077572.us-central1.run.app
POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app
```

Tour-modernized also has `POLLY_TTS_URL` set (updated in previous session).

---

## Tour Generation Pipeline on Cloud (end-to-end flow)

```
Mobile App (cellular)
  → POST api-gateway/generate-complete-tour
    → tour-orchestrator (coordinates, calls generator + modernized)
      → tour-generator (OpenAI text generation)
      → tour-modernized (Polly TTS audio, creates ZIP)
        → polly-tts (AWS Polly synthesis)
    → Store ZIP in DB (Cloud SQL)
    → Set tour_blob_uri (for future R2 delivery)
  → GET api-gateway/status/{job_id}
    → tour-orchestrator (returns progress/completion)
  → GET api-gateway/download-tour/{id}
    → map-delivery (reads from R2 or DB)
```

---

## Test Results

| Test | Result |
|------|--------|
| `api-gateway/health` | ✅ 200 |
| `api-gateway/tours-near/42.36/-71.06` | ✅ 200, 76 KB (191 tours) |
| `api-gateway/tour/313/resolve` | ✅ 200, correct tour info |
| Mobile app tour download via gateway | ✅ (verified earlier) |
| Tour generation via gateway | Ready to test (pipeline fully wired) |

---

## Questions for Review

1. **The nginx proxy passes secrets in its Host header** to backend services. Is there a security concern with `proxy_set_header Host <backend>.run.app`? Cloud Run validates the Host header for routing but the proxy itself is `--allow-unauthenticated`. Should the backend services require IAM auth and the proxy use a service account token?

2. **The catch-all route (`location /`)** sends unknown paths to the orchestrator. Should it return 404 instead to prevent accidental exposure of orchestrator endpoints not intended for the mobile app?

3. **The `proxy_read_timeout 300`** for tour generation may not be enough — a 10-stop tour with translations can take 3-5 minutes. Should this be increased to 600? (Cloud Run's max request timeout is 3600s.)

4. **Translation and coordinates services have secrets as plain env vars** (not Secret Manager bindings). This was done to avoid the newline issue. Should these be migrated back to Secret Manager once we have a reliable no-newline workflow?

5. **`tour-id-resolution` service** was created but never successfully deployed (port issue). It's now redundant since the resolve endpoint was added to map-delivery. Should we delete the failed service from Cloud Run?

---

## What's NOT yet deployed (per Claude spec)

| Deliverable | Status |
|---|---|
| A (Tour status REST endpoint) | Not yet — mobile still uses direct DB update for status. Works on local; cloud generation returns progress via /status but mobile doesn't call it for status updates |
| C (News/newsletter services) | Not deployed — newsletters only work on local |
| D (Cloud SQL data import — remaining tables) | Pending |
| E (Lock down Cloud SQL) | Pending — `0.0.0.0/0` still open |

These are needed for full production readiness but not for the tour generation test.
