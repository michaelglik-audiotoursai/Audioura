# Code Review — Quota/Auth Bypass Fix (2026-06-23)

**Task:** ClickUp 86aj6k3d7
**Commit:** `7d776ff` on `services-migration`
**Image:** `audioura:v29`, `api-gateway:v29`
**Revisions:** `news-orchestrator-00019-wl5`, `newsletter-processor-00009-k6n`, `api-gateway-00016-7jl`

---

## Vulnerability (CLOSED)

`news_orchestrator_service.py:75` read `source = data.get('source', 'direct')` from the request **body** and L83 skipped auth+quota when `source=='newsletter'`. Since `/generate-news` is publicly routed via the gateway, any client could POST `{"source":"newsletter","secret_id":"anonymous"}` and generate unlimited news (real OpenAI+Polly cost) with no auth and no quota.

## Fix

### 1. Gateway strips X-Internal-Service header (api-gateway/main.py:160)

**Before:**
```python
headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'transfer-encoding')}
```

**After:**
```python
headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'transfer-encoding', 'x-internal-service')}
```

Clients cannot inject `X-Internal-Service` through the gateway.

### 2. Orchestrator verifies caller identity (news_orchestrator_service.py:68–88)

**Before (VULNERABLE):**
```python
source = data.get('source', 'direct')
if source == 'newsletter':
    # skip auth + skip quota
```

**After (SECURE):**
```python
# Removed: source = data.get('source', ...)
_INTERNAL_SERVICE_SECRET = os.getenv('INTERNAL_SERVICE_SECRET', '')
caller_token = request.headers.get('X-Internal-Service', '')
is_trusted_internal = (
    _INTERNAL_SERVICE_SECRET
    and caller_token
    and hmac.compare_digest(caller_token, _INTERNAL_SERVICE_SECRET)
)

if is_trusted_internal:
    # Verified internal caller — skip per-article quota
else:
    # Full auth (401) + quota (429) for everyone else
```

Trust is gated on a **shared secret** in `INTERNAL_SERVICE_SECRET` env var (stored in Secret Manager), verified via `hmac.compare_digest`. The `data.get('source')` body field is completely deleted as a trust signal.

### 3. Newsletter-processor sends the internal header (newsletter_processor_service.py:2176)

```python
headers={
    'Content-Type': 'application/json; charset=utf-8',
    **(({'X-Internal-Service': INTERNAL_SERVICE_SECRET} if INTERNAL_SERVICE_SECRET else {})),
    **_get_auth_headers(NEWS_ORCHESTRATOR_URL)
}
```

Also removed `'source': 'newsletter'` from the JSON payload (line ~2152).

### 4. Quota debit (newsletter_processor_service.py:~989)

Inserts a tracking row into `article_requests` with `article_id='newsletter-debit-{id}'` and `status='newsletter_debit'`. This ensures `get_news_used_period()` counts 1 unit per newsletter (it counts `article_requests` rows for the user in the period).

---

## Verification Results

### Test 1: Exploit attempt (MUST return 401)
```
POST https://api.audioura.com/generate-news
Headers: X-API-Key: valid, X-Internal-Service: fake
Body: {"source":"newsletter","secret_id":"anonymous","article_text":"exploit test"}

RESULT: HTTP 401 ✅
```
The body `source` field is ignored. The fake `X-Internal-Service` header is stripped by the gateway.

### Test 2: Real newsletter via processor (MUST give 13/13)
```
POST https://api.audioura.com/process_newsletter
Body: {"newsletter_url": "...", "user_id": "USER-281301397", "test_mode": true}

RESULT: HTTP 200, articles_created=13, articles_failed=0, articles_detected=13 ✅
```
The newsletter-processor's `X-Internal-Service` header passes through because it calls the orchestrator directly (not via gateway).

### Test 3: Orchestrator log confirms internal auth
```
[QUOTA] Internal service call verified — skipping per-article quota (user=USER-281301397)
```
Confirmed in Cloud Logging for revision `news-orchestrator-00019-wl5`.

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `api-gateway/main.py` | 160 | Strip `x-internal-service` from proxied headers |
| `news_orchestrator_service.py` | 6 (import hmac) | Added `import hmac` |
| `news_orchestrator_service.py` | 68–120 | Replaced body-based `source` with header-based `X-Internal-Service` + `hmac.compare_digest` |
| `newsletter_processor_service.py` | 34–35 | Added `INTERNAL_SERVICE_SECRET` env var |
| `newsletter_processor_service.py` | ~2152 | Removed `'source': 'newsletter'` from payload |
| `newsletter_processor_service.py` | ~2176 | Added `X-Internal-Service` header to orchestrator call |
| `newsletter_processor_service.py` | ~989 | Quota debit: insert tracking row per newsletter |

## Infrastructure

- `INTERNAL_SERVICE_SECRET` created in Secret Manager (`internal-service-secret`)
- Set as env var on both `news-orchestrator` and `newsletter-processor`
- Gateway does NOT have this secret (doesn't need it)
