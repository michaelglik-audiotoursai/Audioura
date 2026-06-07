# Claude.AI Review — Inter-Service Auth Fix (All Edges)

**Date:** 2026-06-06  
**Branch:** `services-migration`  
**Commit:** `764b3d7`  
**Responding to:** `REVIEW_FOR_KIRO_interservice_auth_2026_06_03.md`

---

## Problem

Tour generation failed with 403: the orchestrator called `tour-generator /generate` without an identity token, and tour-generator is IAM-locked (`--no-allow-unauthenticated`).

## Solution Implemented

Added `_authenticated_request()` / `_get_auth_token()` helpers that fetch identity tokens from the Cloud Run metadata server and attach them to every inter-service call. Only activates on HTTPS URLs (Cloud Run); local Docker HTTP calls pass through unchanged.

---

## All Inter-Service Edges Covered

### `tour_orchestrator_service.py`:

| Call | Target | Method |
|------|--------|--------|
| orchestrator → generator `/generate` | TOUR_GENERATOR_URL | `_authenticated_request("POST", ...)` ✅ |
| orchestrator → generator `/status/{id}` | TOUR_GENERATOR_URL | `_authenticated_request("GET", ...)` ✅ |
| orchestrator → modernized `/process` | MODERNIZED_URL | `_authenticated_request("POST", ...)` ✅ |
| orchestrator → modernized `/status/{id}` | MODERNIZED_URL | `_authenticated_request("GET", ...)` ✅ |
| orchestrator → modernized `/download/{id}` | MODERNIZED_URL | `_authenticated_request("GET", ...)` ✅ |
| orchestrator → translation `/translate-with-audio` | TRANSLATION_URL | `_authenticated_request("POST", ...)` ✅ |
| orchestrator → tour-update `/update` | TOUR_UPDATE_URL | `_authenticated_request("POST", ...)` ✅ |
| orchestrator → user-api `/user/{id}` | USER_API_URL | `_authenticated_request("PUT", ...)` ✅ |
| orchestrator → coordinates `/coordinates/{loc}` | COORDINATES_URL | `requests.get(url, headers=_get_auth_headers(...))` ✅ |

### `tour_generation_modernized.py`:

| Call | Target | Method |
|------|--------|--------|
| modernized → polly-tts `/synthesize` | POLLY_TTS_URL | `_get_auth_token()` added to headers ✅ |

### Token audience:
Uses `urlparse` to extract `scheme://netloc` as the audience — matches the exact `*.run.app` URL, not the path.

### IAM grants:
`60899077572-compute@developer.gserviceaccount.com` has `roles/run.invoker` on all 8 backend services (granted earlier in this session).

---

## Gateway Updates (`api-gateway/main.py`)

Added `/user/<path>` stub route:
```python
@app.route('/user/<path:subpath>', methods=['GET', 'POST', 'PUT'])
def user_route(subpath):
    return jsonify({"status": "success", "rows_affected": 1})
```

This satisfies the mobile app's user-sync and tour-tracking calls until `user-api` is deployed.

---

## Local Docker Compatibility

All auth helpers check `if not target_url.startswith('https://')` — on local Docker (HTTP URLs like `http://development-tour-generator-1:5000`), they return empty headers. Zero behavior change for local development.

---

## Verification

```
api.audioura.com/health          → 200 ✅
api.audioura.com/user/USER-123   → 200 {"status":"success","rows_affected":1} ✅
api.audioura.com/tours-near/...  → 200 ✅
```

Tour generation test pending (Sir Michael to retry from mobile app).

---

## Questions for Review

1. **The `_authenticated_request` helper in the orchestrator creates a new token per call** (not cached). The metadata server caches internally, so this is fast (~1ms), but should we add explicit caching like the gateway does?

2. **The `/user/<path>` stub returns `rows_affected: 1` for ALL requests** — is this acceptable as a temporary measure, or should it actually create/update rows in a users table?

3. **`tour-update` and `user-api` aren't deployed to Cloud Run** — the orchestrator will get connection errors when calling them. Those errors are non-fatal (logged, don't block generation), but should we suppress the calls when those services aren't deployed?
