# Claude Code Review — v2.1.1+8 News Cloud Paths (commit `45137a5`)

**Date:** 2026-06-12
**Branch:** `services-migration`
**Head commit:** `45137a5`
**Prior version:** `2.1.1+8` (already bumped from previous batch)
**Context:** News services are deployed to cloud (gateway `audioura:v24`). This commit wires the app to send `X-API-Key` on all news/newsletter calls in cloud mode.

---

## What changed

**Single concern:** Replace hardcoded `{'Content-Type': 'application/json'}` headers with `await Endpoints.apiHeaders(Service.newsletter)` (or `Service.news`) on all news/newsletter HTTP calls. This adds the `X-API-Key` header in cloud mode, which the gateway requires.

**Files modified:** 2

### `lib/screens/home_screen.dart` — 5 call sites fixed

| Method | Line | Endpoint | Before | After |
|--------|------|----------|--------|-------|
| `_loadNewsletters` | ~1803 | `GET /newsletters_v2` | hardcoded headers | `apiHeaders(Service.newsletter)` |
| `_processNewsletterWithUrl` | ~1915 | `POST /process_newsletter` | hardcoded headers | `apiHeaders(Service.newsletter)` |
| `_processNewsletterUrl` | ~1978 | `POST /process_newsletter` | hardcoded headers | `apiHeaders(Service.newsletter)` |
| `_processNewsletter` | ~2075 | `POST /get_articles_by_newsletter_id` | hardcoded headers | `apiHeaders(Service.newsletter)` |
| `_downloadAndSaveArticle` | ~2324 | `GET /download/<id>` | hardcoded headers | `apiHeaders(Service.news)` |

**Pattern (each site):**

Before:
```dart
headers: {'Content-Type': 'application/json'},
```

After:
```dart
headers: await Endpoints.apiHeaders(Service.newsletter),
```

### `lib/screens/about_screen.dart` — 1 text change

Removed the outdated "News/newsletters remain local until deployed" message. Replaced with:
```dart
'✅ Cloud mode: all services (tours, news, newsletters) route through api.audioura.com.'
```

---

## What did NOT change (and why)

1. **URLs** — already correct. All news/newsletter calls already use `Endpoints.url(Service.newsletter, '/...')` or `Endpoints.base(Service.news)`. The `Endpoints` resolver routes to cloud or local based on `server_mode`. No URL changes needed.

2. **Cloud path prefixes** — `_cloudPaths[Service.news] = '/news'` and `_cloudPaths[Service.newsletter] = '/newsletter'` exist in `endpoints.dart` but are only used when `cloud_use_path_prefixes = true` (which is OFF by default). With prefixes OFF, the gateway routes by root path: `<cloud_base_url>/download/<id>`, `<cloud_base_url>/newsletters_v2`, etc. This matches the deployed gateway routing.

3. **Android path healing** — `my_news_screen.dart` healing logic uses `/Documents/` marker (iOS container paths). Android paths (`/data/user/0/com.audioura.app/app_flutter/...`) are stable across reinstalls, so no Android-specific marker is needed. Cloud-downloaded articles save to the same local path structure — no healing change needed.

4. **`my_news_screen.dart`** — no code changes. It reads from local filesystem (SharedPreferences paths). Download writes to local disk regardless of cloud/local mode.

---

## Questions for Claude

**Q1:** The article download call uses `Service.news` (`apiHeaders(Service.news)`) while all newsletter calls use `Service.newsletter`. Both resolve to the same cloud base URL when prefixes are OFF. In local mode, `Service.news` → port 5012, `Service.newsletter` → port 5017. The download endpoint (`/download/<id>`) lives on the news-orchestrator (5012). The newsletter endpoints (`/newsletters_v2`, `/process_newsletter`, `/get_articles_by_newsletter_id`) live on the newsletter-processor (5017). Is this service split correct for cloud mode too — i.e., does the gateway route `/download/` to the news service and `/newsletters_v2` etc. to the newsletter service, or are they all on one service behind the gateway?

**Q2:** `_downloadAndSaveArticle` constructs the URL manually (`'$dlBase/download/$articleId?user_id=$deviceId'`) instead of using `Endpoints.url(Service.news, '/download/$articleId?user_id=$deviceId')`. The `dlBase` comes from `Endpoints.base(Service.news)` so it's functionally equivalent — but the query parameter (`?user_id=...`) is embedded in the path string. Is this fine, or should it be a properly constructed `Uri` with query parameters for correctness?

---

## Test criteria

- [ ] Cloud mode: newsletter list loads (GET `/newsletters_v2` returns 200 with API key)
- [ ] Cloud mode: process a newsletter URL (POST `/process_newsletter` returns 200)
- [ ] Cloud mode: get articles by newsletter ID (POST `/get_articles_by_newsletter_id` returns 200)
- [ ] Cloud mode: download an article (GET `/download/<id>` returns ZIP bytes)
- [ ] Cloud mode: playback works after download
- [ ] Local mode: all above still works (regression — no API key sent, ports route correctly)
- [ ] Android reinstall: previously downloaded articles still play

---

## Verdict requested

Approve for Ubuntu build (this commit is additive to the already-approved v2.1.1+8 batch).
