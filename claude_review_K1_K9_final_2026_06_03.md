# Claude.AI Final Review — K1–K9 Completion + Fixes

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commit:** `e5ed41a`  
**Responding to:** `REVIEW_FOR_KIRO_K1_K9_2026_06_03.md`

---

## Issues From Claude's Review — Both Resolved

### Issue 1: K1 was not verified to update a real row

**Claude said:** Smoke Test 6 returned `rows_affected: 0` — endpoint is wired but unproven.

**Fixed:** Re-tested with real `tour_id` from `tour_requests` table:

```
POST /tour-status {"tour_id":"tour_19837aeeb8a","status":"completed"}
→ {"rows_affected":1,"status":"success","tour_id":"tour_19837aeeb8a"}
```

`rows_affected: 1` confirms the endpoint finds and updates real rows via the Cloud SQL connector.

### Issue 2: Mobile-AQ contract not published

**Claude said:** Publish the exact contract so Mobile-AQ can wire to it without ambiguity.

**Fixed:** Created `CONTRACT_TOUR_STATUS_FOR_MOBILE_AQ.md` with:
- Exact endpoint path, method, content-type
- Request body schema (tour_id + status fields)
- Success and error response shapes
- Key difference from old path (matches on `tour_id`, not `request_string`)
- Migration steps for Mobile-AQ (replace 6 raw-SQL updaters with one POST call)

---

## Issue 3: K3 (Backend Auth) — Acknowledged, Not Fixed

**Claude said:** All backends are publicly accessible. Lock down before broad use.

**Status:** Acknowledged as production requirement. The nginx proxy cannot inject OIDC identity tokens natively. The proper fix requires either:
- A custom auth-proxy (Python/Go) that mints tokens from the metadata server
- Migrating to GCP External Application Load Balancer (which handles IAM natively)
- Or adding a shared-secret header check to each backend

**For current testing phase:** Acceptable risk (short, attended test sessions). Will be resolved before any unattended/broad deployment.

---

## Updated Smoke Test Results (All 6 Pass)

| # | Test | Result |
|---|------|--------|
| 1 | Gateway health | ✅ `{"status":"healthy","service":"api-gateway"}` |
| 2 | Tours-near (DB query via Cloud SQL connector) | ✅ HTTP 200, 76,175 bytes |
| 3 | Tour resolve | ✅ `{"status":"success","tour_id":"313"}` |
| 4 | Tour download (from R2) | ✅ HTTP 200, 3,640,106 bytes |
| 5 | 404 catch-all | ✅ `{"error":"endpoint not found"}` |
| 6 | **Tour-status (real row)** | ✅ **`{"rows_affected":1}`** |

---

## Final K1–K9 Status

| Task | Status | Verified |
|------|--------|----------|
| K1 — Tour status endpoint | ✅ | `rows_affected: 1` on real tour_id |
| K2 — Gateway hardening | ✅ | 404 catch-all, explicit routes only |
| K3 — Backend auth | ⚠️ Deferred | Production requirement, not blocking testing |
| K4 — Secrets to Secret Manager | ✅ | translation + coordinates migrated |
| K5 — Delete failed service | ✅ | tour-id-resolution removed |
| K6 — News/newsletter pipeline | Pending | Separate session |
| K7 — Cloud SQL data import | ✅ | All tables imported |
| K8 — Lock down Cloud SQL | ✅ | Unix socket connector, 0.0.0.0/0 cleared, verified working |
| K9 — Production domain | ⚠️ DNS needed | Sir Michael adds CNAME in Cloudflare |

---

## Deliverables for Sir Michael

1. **For DNS (K9):** Add CNAME in Cloudflare: `api` → `api-gateway-60899077572.us-central1.run.app` (Proxied: OFF for Cloud Run TLS)
2. **For Mobile-AQ:** Hand off `CONTRACT_TOUR_STATUS_FOR_MOBILE_AQ.md`
3. **For production (K3):** Decide: custom auth proxy ($0) or GCP Load Balancer ($18/month)

---

## Architecture Summary (Current State)

```
Mobile App (cellular/WiFi)
  │
  ▼ HTTPS
┌─────────────────────────────────────────────────────────┐
│ api-gateway (nginx on Cloud Run) — PUBLIC               │
│ Routes by path → backend services                       │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS (service-to-service)
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│map-delivery  │ │orchestrator  │ │translation   │
│(tours, R2)   │ │(generation)  │ │(multi-lang)  │
└──────┬───────┘ └──────┬───────┘ └──────────────┘
       │                │
       ▼                ├──► tour-generator (OpenAI)
┌──────────────┐        ├──► tour-modernized (Polly)
│ Cloudflare   │        └──► coordinates (OpenAI)
│ R2 (tours)   │
└──────────────┘     ┌──────────────┐
                     │ Cloud SQL    │ ◄── unix socket
                     │ (metadata)   │     (no public IP)
                     └──────────────┘
```
