# REVIEW_FOR_KIRO — News Inter-Service Auth Fix (2026-06-12)

**Context:** The news orchestrator's downstream calls to news-generator and news-processor were returning 403 because it sent bare HTTP requests without OIDC identity tokens. All Cloud Run backends are IAM-locked (`--no-allow-unauthenticated`).

---

## Problem

The news orchestrator used plain `requests.post()` for inter-service calls. On Cloud Run, IAM-locked services require a Google OIDC identity token in the `Authorization: Bearer` header. Without it → 403 Forbidden.

The tour orchestrator already had `_authenticated_request()` for this. The news orchestrator was missing it.

---

## Fix

Added `_get_auth_headers(target_url)` to `news_orchestrator_service.py`:

```python
def _get_auth_headers(target_url):
    """Get OIDC identity token for inter-service calls on Cloud Run.
    Returns empty dict locally (services are unauthenticated in Docker)."""
    if target_url.startswith('http://'):
        return {}  # Local Docker — no auth needed
    # Cloud Run: fetch identity token from metadata server
    audience = target_url.rstrip('/')
    # ... token fetch + cache (3500s TTL) ...
    return {'Authorization': f"Bearer {token}"}
```

Applied to both downstream calls:
- `NEWS_GENERATOR_URL/process-article` — auth headers added ✅
- `NEWS_PROCESSOR_URL/process-audio` — auth headers added ✅

**Local Docker compatibility:** `http://` URLs (local) get no auth (empty dict). `https://` URLs (Cloud Run) get OIDC tokens. Same code works in both environments.

---

## Verification

```
Generator response: 200  ✅ (was 403 before fix)
Processor response: 500  (Polly TTS failed: 403 — separate AWS issue)
```

The inter-service auth fix is confirmed working for the generator call. The processor's 500 is a downstream AWS Polly credentials issue (not related to this fix — see below).

---

## Remaining: Polly TTS 403 (separate issue)

The news-processor calls the polly-tts Cloud Run service → polly-tts calls AWS Polly → AWS returns 403. This is either:
- Expired/invalid AWS credentials on the polly-tts service, OR
- The news-processor also needs to send OIDC auth when calling polly-tts (same pattern as above)

This is a configuration investigation, not a code architecture issue. The pattern is the same — any Cloud Run service calling another needs OIDC tokens.

---

## Deployment

| Service | Revision | Image | Change |
|---------|----------|-------|--------|
| `news-orchestrator` | `news-orchestrator-00012-x58` | `audioura:v23` | Added `_get_auth_headers` + applied to generator/processor calls |

---

## File Modified

| File | Change |
|------|--------|
| `development/news_orchestrator_service.py` | Added OIDC token helper + applied to both inter-service calls |

---

## `py_compile`

Exit 0 (clean).
