# REVIEW_FOR_KIRO — Gateway Parity: News/Newsletter Routes (2026-06-08)

**Context:** News articles and newsletters work locally but not on cloud because the API gateway was missing routes. Per Claude's directive, implementing Section 3 (immediate fix) to unblock testing.

---

## Problem

The gateway (`api-gateway/main.py`) is a hand-maintained route list. Locally, the app calls services directly by port — every `@app.route` is reachable. On cloud, only routes explicitly registered in the gateway are reachable. The gateway was missing critical news/newsletter routes.

---

## Changes Made

### Routes added to `api-gateway/main.py`:

| Route | Method | Backend | Auth | Purpose |
|-------|--------|---------|------|---------|
| `/generate-news` | POST | news-orchestrator | API key | Submit article for processing |
| `/news-status/<article_id>` | GET | news-orchestrator | Public | Poll article processing status |
| `/news-articles` | GET | news-orchestrator | List available articles |
| `/news-download/<article_id>` | GET | news-orchestrator | Public | Download processed article ZIP |
| `/submit_credentials` | POST | newsletter | API key | Submit encrypted subscription credentials |
| `/get_user_consolidation_status/<device_id>` | GET | newsletter | Public | Check consolidation status |

### Routes fixed:

| Route | Fix |
|-------|-----|
| `/get_articles_by_newsletter_id` | Changed from `GET` to `POST` (matching the service's actual method) |

### Routes deliberately NOT exposed:

| Route | Reason |
|-------|--------|
| `/decrypt_credentials` | Handles raw credentials; service-to-service only |

### Path naming (collision avoidance):

- News status uses `/news-status/<article_id>` (not `/status/<article_id>`) to avoid colliding with the existing tour status route at `/status/<job_id>`.
- News article list uses `/news-articles` (not `/articles`) for the same reason.

---

## Mobile-AQ Coordination Needed

The app must call these **cloud-specific** path names when in cloud mode:

| Local path (direct to service) | Cloud path (through gateway) |
|------|------|
| `http://...:5012/generate-news` | `https://api.audioura.com/generate-news` |
| `http://...:5012/status/<id>` | `https://api.audioura.com/news-status/<id>` |
| `http://...:5012/articles` | `https://api.audioura.com/news-articles` |
| `http://...:5012/download/<id>` | `https://api.audioura.com/news-download/<id>` |

`/generate-news` keeps its name (no collision). The status/articles/download paths are renamed to avoid tour-endpoint collisions.

---

## Deployment

| Service | Revision |
|---------|----------|
| `api-gateway` | `api-gateway-00010-nxm` |

Verified healthy: `https://api.audioura.com/health` → `{"status": "healthy", "service": "api-gateway", "auth": "enabled"}`

---

## Deferred: YAML-driven gateway (Section 4)

Claude's recommended durable fix — convert `main.py` to load routes from `gateway_routes.yaml` + add a parity test — is the right long-term answer. Not implementing this session; current hand-fix unblocks news testing. The parity test would prevent this class of bug from recurring.

---

## Full current gateway route surface (post-fix)

### Map Delivery
- `GET /tours-near/<path>` — public
- `GET /download-tour/<tour_id>` — public
- `GET /tour/<tour_id>/resolve` — public
- `GET|POST /search-tours` — public

### Tour Orchestrator
- `POST /generate-complete-tour` — API key
- `GET /status/<job_id>` — public
- `GET /download/<job_id>` — public
- `POST /tour-status` — API key
- `GET /jobs` — public

### Translation
- `POST /translate-with-audio` — API key

### News Orchestrator
- `POST /generate-news` — API key ← NEW
- `GET /news-status/<article_id>` — public ← NEW
- `GET /news-articles` — public ← NEW
- `GET /news-download/<article_id>` — public (was existing)

### Newsletter Processor
- `POST /process_newsletter` — API key
- `GET /newsletters_v2` — public
- `POST /get_articles_by_newsletter_id` — public ← METHOD FIXED (was GET)
- `POST /submit_credentials` — API key ← NEW
- `GET /get_user_consolidation_status/<device_id>` — public ← NEW

### Other
- `GET /health` — public
- `POST|GET /sync` — stub
- `GET|POST|PUT /user/<path>` — stub

---

## Risk

- **New routes:** Low risk. Additive — existing routes unchanged. Each new route proxies to the same backend endpoint the local setup calls directly.
- **Method fix (`GET` → `POST`):** Breaking for any client already calling it as GET on cloud — but it wasn't working anyway (service returns 405 for GET), so net effect is fixing a broken endpoint.
- **`/decrypt_credentials` NOT exposed:** Deliberate security decision. This endpoint handles raw credential material and must only be reachable service-to-service (via OIDC tokens between Cloud Run services).
