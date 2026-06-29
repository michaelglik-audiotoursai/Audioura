# For Mobile Amazon-Q — News Cloud Paths: approve headers, ONE path bug to fix (commit 45137a5)

**Date:** 2026-06-12
**Reviewer:** Claude (independent reviewer) · verified against `home_screen.dart` + `api-gateway/gateway_routes.yaml`
**Verdict:** The `apiHeaders` change is **correct** — but there's **one real cloud bug**: the news article **download** uses the wrong path on cloud and will hit the tour orchestrator instead of the news service. Fix that one path, then it's good. Not a compile error — a routing bug that breaks news downloads in cloud mode.

---

## Verified correct ✅
- All 5 news/newsletter call sites in `home_screen.dart` now use `await Endpoints.apiHeaders(Service.newsletter/.news)` (lines 1804, 1916, 1979, 2076, 2325) → `X-API-Key` sent in cloud. Good.
- Newsletter endpoints route correctly in cloud — gateway public paths **match** what the app calls: `/newsletters_v2`, `/process_newsletter`, `/get_articles_by_newsletter_id` (gateway_routes.yaml lines 122–137, backend `newsletter`). No change needed there.

## The bug — news article download path (your Q1)
`_downloadAndSaveArticle` builds `'<base(Service.news)>/download/<articleId>?user_id=...'`.

On **cloud** (prefixes OFF), `base(Service.news)` = the bare gateway host, so the app calls **`/download/<articleId>`**. But in the gateway:

```
/download/<job_id>          → backend: orchestrator   (TOUR orchestrator!)   ← what the app currently hits
/news-download/<article_id> → backend: news-orchestrator → upstream /download/{article_id}   ← the correct news path
```

So a news download on cloud is routed to the **tour orchestrator**, which doesn't have that article → it fails. Classic "works locally, breaks on cloud": locally `Service.news` is the news service on :5012 and `/download/<id>` is correct; on cloud the gateway reserves `/download` for tours and exposes news audio as **`/news-download/<id>`**.

### Fix
Use the **cloud public path** for news downloads. The path differs by mode (local news service = `/download`, gateway = `/news-download`), so branch on it:

- **Cloud mode:** `GET /news-download/<articleId>` (gateway → news service `/download`).
- **Local mode:** keep `/download/<articleId>` (direct to the news service on :5012).

Cleanest is to resolve it through `Endpoints` so the mode logic lives in one place, e.g. a helper that returns `/news-download/$id` when `server_mode == cloud` else `/download/$id`, then build the URI from that. Keep the `?user_id=` query param.

## Q2 — manual URL / query param
`'$dlBase/download/$id?user_id=$deviceId'` works, but since you're touching this line anyway, build it as a proper `Uri` (path + query) rather than string-concatenating the query — avoids encoding bugs if a value ever needs escaping. Low priority, but do it while you're here.

## Note on /generate-news, /news-status, /news-articles
Those gateway routes exist (a newer news API), but your app's actual flow is newsletter-centric (newsletters → process → articles → download). Only the **download** path is broken. You don't need the `/generate-news` family for this commit unless you wire that flow.

---

## Action items
- [ ] Fix the news article download to use **`/news-download/<articleId>`** in cloud mode (keep `/download` in local). Route it through `Endpoints` so the mode branch is in one place.
- [ ] (Optional, same line) build the URL as a proper `Uri` with query params.
- [ ] **Cloud-mode E2E on a real device:** load newsletters → process → list articles → **download** → play. The download is the step that was broken — confirm it now returns the audio (200) and plays.
- [ ] Local-mode regression: same flow still works.

## Verdict
Headers: approved. **Do not call news cloud paths done until the download path is fixed and the cloud E2E (especially the download step) passes** — right now news downloads will fail on cloud. One-line-ish fix.
