# Claude Code Review — v2.1.1+8 News Download Path Fix (commit `580a3af`)

**Date:** 2026-06-12
**Branch:** `services-migration`
**Head commit:** `580a3af`
**Context:** The gateway routes `/download/<id>` to the tour orchestrator, not the news service. News article downloads in cloud mode need to use `/news-download/<id>` instead. This commit fixes the routing and uses proper `Uri` construction.

---

## What changed

### `lib/config/endpoints.dart` — new helper method

```dart
/// Returns the correct news article download URI, handling the cloud path
/// difference: local uses /download/<id>, cloud gateway uses /news-download/<id>.
static Future<Uri> newsDownloadUrl(String articleId, String userId) async {
  final prefs = await SharedPreferences.getInstance();
  final mode = prefs.getString('server_mode') ?? 'local';
  final baseUrl = await base(Service.news);
  final path = mode == 'cloud' ? '/news-download/$articleId' : '/download/$articleId';
  return Uri.parse('$baseUrl$path').replace(queryParameters: {'user_id': userId});
}
```

**Design:**
- Mode-aware: `/news-download/<id>` in cloud (gateway → news service's `/download`), `/download/<id>` in local (direct to news service on :5012)
- Returns a proper `Uri` with `user_id` as a query parameter (not string-concatenated)
- Language parameter added by the caller when needed

### `lib/screens/home_screen.dart` — `_downloadAndSaveArticle` rewritten

**Before:**
```dart
String downloadUrl;
final dlBase = await Endpoints.base(Service.news);
downloadUrl = '$dlBase/download/$articleId?user_id=$deviceId';
if (language != 'en') {
  downloadUrl += '&language=$language';
}
final downloadResponse = await http.get(
  Uri.parse(downloadUrl),
  headers: await Endpoints.apiHeaders(Service.news),
).timeout(Duration(seconds: 30));
```

**After:**
```dart
var downloadUri = await Endpoints.newsDownloadUrl(articleId, deviceId);
if (language != 'en') {
  final params = Map<String, String>.from(downloadUri.queryParameters);
  params['language'] = language;
  downloadUri = downloadUri.replace(queryParameters: params);
}
final downloadResponse = await http.get(
  downloadUri,
  headers: await Endpoints.apiHeaders(Service.news),
).timeout(Duration(seconds: 30));
```

**Improvements:**
1. Correct cloud path (`/news-download/<id>` instead of `/download/<id>`)
2. Proper `Uri` construction with typed query parameters (no manual `?`/`&` concatenation)
3. Mode branch lives in `Endpoints.newsDownloadUrl()` — single place to maintain

---

## Path routing summary (cloud mode, prefixes OFF)

| App calls | Gateway routes to | Correct? |
|-----------|-------------------|----------|
| `GET /news-download/<id>?user_id=...` | news-orchestrator → `/download/<id>` | ✅ Fixed |
| `GET /newsletters_v2` | newsletter-processor | ✅ Already correct |
| `POST /process_newsletter` | newsletter-processor | ✅ Already correct |
| `POST /get_articles_by_newsletter_id` | newsletter-processor | ✅ Already correct |
| `GET /download/<id>` | tour orchestrator | ⚠️ Tour download (not news) — correct for tours |

---

## Questions for Claude

**Q1:** `Uri.replace(queryParameters: params)` replaces ALL query parameters. The initial `newsDownloadUrl` sets `{'user_id': userId}`. When adding language, the code does `Map.from(downloadUri.queryParameters)` to preserve `user_id` before adding `language`. Is this the idiomatic Dart approach, or is there a cleaner way? (Works correctly — just asking about style.)

**Q2:** Should `newsDownloadUrl` live on `Endpoints` (infrastructure concern) or on a dedicated `NewsService` helper (domain concern)? The current placement is pragmatic (news is the only service with this cloud/local path split), but if more services develop similar path differences, should we generalize the pattern?

---

## Test criteria (cloud mode E2E)

- [ ] Newsletter list loads (GET `/newsletters_v2` → 200)
- [ ] Process newsletter (POST `/process_newsletter` → 200)
- [ ] List articles (POST `/get_articles_by_newsletter_id` → 200 with articles)
- [ ] **Download article** (GET `/news-download/<id>?user_id=...` → 200, ZIP bytes received)
- [ ] Playback works after download
- [ ] Multi-language download appends `&language=ru` correctly
- [ ] **Local mode regression**: same flow works (uses `/download/<id>` on :5012)

---

## Verdict requested

Approve for Ubuntu build. This is the last piece — news cloud paths are now fully wired.
