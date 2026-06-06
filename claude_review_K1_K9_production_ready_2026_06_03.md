# Claude.AI Final Review — K1–K9 Production Ready

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Status:** All tasks complete. Production domain live. All smoke tests passing.

---

## Production URL

```
https://api.audioura.com
```

Cloudflare proxy ON (orange cloud) + Full (strict) SSL + GCP Load Balancer + Google-managed certificate.

---

## Architecture (Final State)

```
Mobile App (anywhere in the world)
  │
  ▼ HTTPS
┌─────────────────────────────────────────────────────────┐
│ Cloudflare (DDoS, CDN, orange cloud proxy)              │
│ api.audioura.com → A record → 34.36.147.30              │
│ SSL/TLS: Full (strict)                                  │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────┐
│ GCP External Application Load Balancer                  │
│ IP: 34.36.147.30 (static)                               │
│ Google-managed SSL cert for api.audioura.com (ACTIVE)   │
│ URL Map → Serverless NEG → api-gateway Cloud Run        │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS + Identity Token
                         ▼
┌─────────────────────────────────────────────────────────┐
│ api-gateway (Python auth-proxy on Cloud Run) — PUBLIC   │
│ Mints Google identity tokens from metadata server       │
│ Routes by path to locked backend services               │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
│map-      │ │tour-     │ │transla-  │ │news-orchestrator │
│delivery  │ │orchestra-│ │tion      │ │newsletter-proc   │
│(R2 tours)│ │tor       │ │service   │ │news-generator    │
└──────────┘ └──────────┘ └──────────┘ └──────────────────┘
       │          │
       ▼          ├──► tour-generator (OpenAI)
┌──────────┐      ├──► tour-modernized (Polly TTS)
│Cloudflare│      ├──► coordinates (OpenAI)
│R2 (blobs)│      └──► polly-tts (AWS Polly)
└──────────┘
                  ┌──────────────────────┐
                  │ Cloud SQL (Postgres)  │
                  │ Unix socket connector │
                  │ No public IP          │
                  └──────────────────────┘
```

---

## K1–K9 Final Status

| Task | Status | Verification |
|------|--------|-------------|
| K1 — Tour status endpoint | ✅ | `POST /tour-status` → `rows_affected: 1` on real row |
| K2 — Gateway hardening | ✅ | 404 catch-all, explicit routes only |
| K3 — Backend auth | ✅ | Python auth-proxy mints ID tokens; all 10 backends `--no-allow-unauthenticated` |
| K4 — Secrets to Secret Manager | ✅ | translation + coordinates migrated |
| K5 — Delete failed service | ✅ | tour-id-resolution removed |
| K6 — News/newsletter deploy | ✅ | news-orchestrator, news-generator, newsletter-processor deployed |
| K7 — Cloud SQL data import | ✅ | All tables imported (263 tours, 751 news, article_requests, custom_tours) |
| K8 — Lock down Cloud SQL | ✅ | Unix socket connector, no public IP |
| K9 — Production domain | ✅ | GCP LB ($18/mo) + Google-managed cert + Cloudflare proxy |

---

## Cloud Run Services (11 total)

| Service | Auth | max-instances | Purpose |
|---------|------|---------------|---------|
| api-gateway | PUBLIC | 3 | Auth-proxy, routes to backends |
| map-delivery | IAM-locked | 2 | Tour list + download (R2) |
| tour-orchestrator | IAM-locked | 1 | Tour generation workflow |
| tour-generator | IAM-locked | 1 | AI text generation (OpenAI) |
| tour-modernized | IAM-locked | 1 | Audio + ZIP creation (Polly) |
| polly-tts | IAM-locked | 2 | AWS Polly TTS wrapper |
| translation-service | IAM-locked | 2 | Multi-language translation |
| coordinates | IAM-locked | 2 | Location geocoding (OpenAI) |
| news-orchestrator | IAM-locked | 1 | News workflow |
| news-generator | IAM-locked | 1 | News content processing |
| newsletter-processor | IAM-locked | 1 | Newsletter crawling |

---

## Production Smoke Tests (All Pass via `https://api.audioura.com`)

| # | Test | Result |
|---|------|--------|
| 1 | `GET /health` | ✅ `{"auth":"enabled","service":"api-gateway","status":"healthy"}` |
| 2 | `GET /tours-near/42.36/-71.06` | ✅ HTTP 200, 76,175 bytes (191 tours) |
| 3 | `GET /tour/313/resolve` | ✅ `{"status":"success","tour_id":"313","tour_name":"Faneuil Hall..."}` |
| 4 | `GET /download-tour/313` | ✅ HTTP 200, 3,640,106 bytes (served from R2) |
| 5 | `GET /nonexistent` | ✅ `{"error":"endpoint not found"}` (404) |
| 6 | `POST /tour-status` | ✅ `{"rows_affected":1,"status":"success"}` |

---

## GCP Infrastructure

| Resource | Details | Monthly Cost |
|----------|---------|-------------|
| Cloud Run (11 services) | Scale to zero | ~$0 idle, cents/request |
| Cloud SQL (db-f1-micro) | PostgreSQL 15, unix socket, no public IP | ~$10 |
| Load Balancer | Global HTTPS, static IP 34.36.147.30 | ~$18 |
| Artifact Registry | Docker images (audioura:v1–v6, api-gateway:v1–v3) | ~$0.50 |
| Secret Manager | 6 secrets | ~$0 |
| **Total floor** | | **~$28.50/month** |

---

## Security Posture

| Layer | Protection |
|-------|-----------|
| Edge | Cloudflare DDoS + CDN (orange cloud proxy) |
| TLS | Google-managed cert (LB) + Cloudflare cert (edge) — Full (strict) |
| API access | Only api-gateway is publicly reachable |
| Backend services | All 10 require IAM identity token (gateway mints them) |
| Database | No public IP; unix socket from Cloud Run only |
| Secrets | All in GCP Secret Manager (no plaintext in code/env) |
| Budget protection | Backends locked — unauthenticated users can't trigger OpenAI/Polly spend |

---

## Mobile App Configuration

```
Cloud base URL: https://api.audioura.com
Gateway path routing: OFF (gateway routes by root path)
```

Available endpoints:
- `/tours-near/{lat}/{lng}` — tour map
- `/download-tour/{id}` — tour download (from R2)
- `/tour/{id}/resolve` — tour metadata
- `/generate-complete-tour` — new tour generation
- `/status/{job_id}` — generation progress
- `/tour-status` — update tour request status
- `/translate-with-audio` — translation
- `/process_newsletter` — newsletter processing
- `/newsletters_v2` — newsletter list
- `/sync` — user sync (stub, returns success)

---

## What's Left (Post-Launch)

| Item | Priority | Notes |
|------|----------|-------|
| Run `--clear` on BYTEA columns | LOW | After verifying R2 delivery for ~1 week in production |
| Wire `DatabaseJobStore` into orchestrator | LOW | Needed only if scaling past 1 instance |
| Deploy voice-control, user-api, treats | LOW | Not needed for core tour/newsletter flow |
| Stop Cloud SQL between sessions | OPTIONAL | Saves ~$10/month during inactive periods |
