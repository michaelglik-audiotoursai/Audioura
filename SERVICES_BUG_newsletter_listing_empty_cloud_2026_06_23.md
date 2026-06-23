# For Services Kiro — Cloud Newsletter Listing Returns Empty

**Date:** 2026-06-23
**Filed by:** Mobile Kiro
**ClickUp task:** 86aj6k3d7 (🟦 Backend Agent queue)
**Severity:** HIGH — Beta-blocking (Audio mode is broken on cloud)
**Environment:** Cloud mode, Android v2.1.1+9, gateway `api.audioura.com`

---

## Reproduction

1. In the app (cloud mode), submit newsletter URL: `https://www.reloadnyc.com/?ref=artificial-commonsense-newsletter`
2. Server returns 200: `{"newsletter_id": 284, "articles_created": 2, "status": "success"}`
3. App shows success → navigates to Audio tab → calls `GET /newsletters_v2`
4. **Result:** 200 with empty list — `{"newsletters": []}` (or equivalent empty)
5. No articles available for download

---

## Two bugs found in the cloud services

### Bug 1 — `/newsletters_v2` listing doesn't return the just-created newsletter

**Expected:** Newsletter ID 284 appears in the list after successful creation.
**Actual:** 0 newsletters returned.

**Possible root causes:**
- The cloud `newsletter-processor` (listing route) queries a different database instance than the one where `/process_newsletter` stores the data
- A server-side date filter or query scope excludes newly created newsletters
- The `/newsletters_v2` Cloud Run deployment isn't connected to the production PostgreSQL database

**Verification:** Run directly against the cloud DB:
```sql
SELECT * FROM newsletters WHERE id = 284;
```
If it exists in the DB but `/newsletters_v2` doesn't return it, it's a query/filter issue. If it doesn't exist, the creation service and the listing service use different DBs.

### Bug 2 — Newsletter processor uses Docker-internal hostname on cloud

**Evidence from response `_diagnostic`:**
```json
"failed_articles": [
  {"error": "HTTPConnectionPool(host='news-orchestrator-1', port=5012): Max retries exceeded with url: /generate-", "url": "https://www.reloadnyc.com/..."}
]
```

The cloud `newsletter-processor` is calling `news-orchestrator-1:5012` — a Docker Compose internal hostname that only works in the local development environment. On Cloud Run, this hostname doesn't resolve.

**Fix:** The newsletter-processor needs to call the news orchestrator via:
- Its Cloud Run URL (e.g., `https://news-orchestrator-xxxx.run.app/generate-news`)
- Or the gateway: `https://api.audioura.com/generate-news`

This is the same pattern that was already fixed on the mobile app side — local URLs were replaced with environment-aware routing. The server-side newsletter-processor needs the same treatment.

---

## Impact

- 8 of 10 detected articles failed to generate (only 2 succeeded — likely because they were already cached)
- Even the 2 that succeeded can't be accessed because `/newsletters_v2` returns empty
- **Audio mode is completely broken on cloud** — users see no content

---

## What the app does correctly (verified)

| Step | App behavior | Server response | Correct? |
|------|-------------|-----------------|----------|
| Submit URL | POST `/process_newsletter` | 200, newsletter_id: 284 | ✅ |
| Show result | "2 articles queued" | — | ✅ |
| Load list | GET `/newsletters_v2` | 200, 0 newsletters | ✅ (app shows server response) |
| Show empty | "No newsletters" | — | ✅ |

The app is correct. The server returns wrong data.

---

## Fix priority

1. **Bug 1** (listing empty) — must fix first, otherwise no content shows even if articles generate
2. **Bug 2** (Docker hostname) — fix for full article generation to work on cloud
