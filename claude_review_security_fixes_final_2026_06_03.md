# Claude.AI Final Review — Security Fixes (Per Production Readiness Review)

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commit:** `26380ab`  
**Responding to:** `REVIEW_FOR_KIRO_production_ready_2026_06_03.md`

---

## Finding 1 Fixed: `/download/<id>` Route Collision

**Problem:** Two routes with same URL pattern — Flask matched the first (orchestrator), making news downloads dead.

**Fix:** Renamed news article download route from `/download/<article_id>` to `/news-download/<article_id>`:

```python
# Before (collision):
@app.route('/download/<job_id>')       → orchestrator (tour ZIP)
@app.route('/download/<article_id>')   → news-orchestrator (DEAD)

# After (distinct paths):
@app.route('/download/<job_id>')        → orchestrator (tour ZIP)
@app.route('/news-download/<article_id>') → news-orchestrator (news article)
```

Mobile-AQ needs to use `/news-download/<id>` for article downloads (not `/download/<id>`).

---

## Finding 2 Fixed: Budget Protection via API Key

**Problem:** Public gateway forwarded `/generate-complete-tour` and `/translate-with-audio` to backends with valid tokens — anyone could trigger OpenAI/Polly spend.

**Fix:** Added `X-API-Key` header verification on all cost-bearing endpoints:

```python
API_KEY = os.getenv('GATEWAY_API_KEY', '')

def require_api_key():
    if not API_KEY:
        return None  # No key = open (dev mode)
    client_key = request.headers.get('X-API-Key', '')
    if client_key != API_KEY:
        return jsonify({"error": "unauthorized", "message": "Valid X-API-Key header required"}), 401
    return None
```

### Protected endpoints (require `X-API-Key` header):
- `POST /generate-complete-tour` — OpenAI + Polly cost
- `POST /translate-with-audio` — Polly cost
- `POST /process_newsletter` — OpenAI cost
- `POST /tour-status` — writes data

### Open endpoints (no key needed):
- `GET /tours-near/...` — read only
- `GET /download-tour/...` — read only (from R2)
- `GET /tour/<id>/resolve` — read only
- `GET /status/<id>` — read only
- `GET /health` — health check
- `GET /newsletters_v2` — read only
- `GET /get_articles_by_newsletter_id` — read only
- `GET /news-download/<id>` — read only

### API Key stored in Secret Manager:
- Secret name: `gateway-api-key`
- Bound to api-gateway as env var `GATEWAY_API_KEY`
- Mobile app must send: `X-API-Key: <value>` header

### Verification:
```
Without key:  POST /generate-complete-tour → 401 {"error":"unauthorized"}  ✅
With key:     POST /generate-complete-tour → 200 {"job_id":"...","status":"queued"}  ✅
Read endpoint: GET /tours-near/42.36/-71.06 → 200 (no key needed)  ✅
```

---

## IAM Backend Lock Verification

Explicitly removed `allUsers` invoker binding from `map-delivery` and `tour-orchestrator`. The `--no-allow-unauthenticated` flag was set on all 10 backends earlier; the explicit binding removal ensures it's enforced (IAM propagation can take a few minutes).

---

## Updated `remind_Services_ai.md`

Updated with:
- Production URL: `https://api.audioura.com`
- Gateway API key in Secret Manager
- Mobile app X-API-Key header requirement
- All backends IAM-locked
- Cloud SQL unix socket (no public IP)

---

## Mobile-AQ Contract Update

The mobile app needs to add this header on cost-bearing requests:
```
X-API-Key: <value from Secret Manager 'gateway-api-key'>
```

The API key value needs to be communicated to Mobile-AQ securely (not in a committed doc). Recommend: Sir Michael copies it from GCP Console and provides it directly to the mobile app config.

---

## Security Posture (Updated)

| Layer | Protection |
|-------|-----------|
| Edge | Cloudflare DDoS + CDN (orange cloud) |
| TLS | Cloudflare → GCP LB (Full strict), Google-managed cert |
| API gateway | Only public surface; routes to locked backends |
| Cost-bearing endpoints | **X-API-Key required** (401 without it) |
| Read-only endpoints | Open (no key needed for tour list/download) |
| Backend services | IAM-locked (403 without identity token) |
| Database | No public IP, unix socket from Cloud Run only |
| Secrets | All in GCP Secret Manager |
| Budget | Protected — unauthenticated users can read but cannot trigger spend |
