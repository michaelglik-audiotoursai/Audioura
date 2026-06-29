# Claude Code Review — v2.1.1+9 Cloud Fixes (commit `2836d7b`)

**Date:** 2026-06-17
**Branch:** `services-migration`
**Head commit:** `2836d7b`
**Context:** A#82 iPhone smoke test found 2 cloud-mode failures (Tests 8 and 9). All local-mode tests pass. This commit fixes both.

---

## Bug Fix 1 — `auth_required` on cloud tour generation

### Problem
Gateway returns 401: `{"allowed":false,"error":"auth_required","message":"A valid user id is required to generate tours."}`

The request body sent to `/generate-complete-tour` contained only `location`, `tour_type`, `total_stops` — no `user_id`. The cloud gateway's entitlements middleware requires `user_id` to look up the user's plan/quota. Local orchestrator doesn't check this, so it only failed on cloud.

### Fix (2 sites in `tour_generator_screen.dart`)

Added to both foreground and background generation, right after `_parseTourRequest()`:
```dart
// Include user_id — required by cloud gateway for auth
final prefs = await SharedPreferences.getInstance();
final userId = prefs.getString('user_id') ?? '';
if (userId.isNotEmpty) tourData['user_id'] = userId;
```

**Foreground** (line ~187):
```dart
Map<String, dynamic> tourData = _parseTourRequest(sanitizedInput);
tourData['total_stops'] = stopCount;
final prefs = await SharedPreferences.getInstance();
final userId = prefs.getString('user_id') ?? '';
if (userId.isNotEmpty) tourData['user_id'] = userId;

final response = await http.post(
  await Endpoints.url(Service.orchestrator, '/generate-complete-tour'),
  headers: await Endpoints.apiHeaders(Service.orchestrator, requestBody: tourData),
  body: jsonEncode(tourData),
);
```

**Background** (line ~1347): identical pattern.

### Note
`SharedPreferences.getInstance()` is already called in the same method scope for both generation paths. The extra `prefs` call here is a second `getInstance()` in the same async frame — `SharedPreferences.getInstance()` is a cached singleton so this has zero performance cost.

---

## Bug Fix 2 — Hardcoded local URLs for news/newsletter

### Problem
`tour_generator_screen.dart` had 4 HTTP calls using `'http://$serverIp:5012/...'` and `'http://$serverIp:5017/...'` that bypassed the `Endpoints` resolver. In cloud mode they still hit the local WiFi server.

Mac Mini A#82 bug report (`a82_bug_report_test9.md`) confirmed the exact same finding.

### Fix (4 sites)

| # | Before | After |
|---|--------|-------|
| 1 | `Uri.parse('http://$serverIp:5012/generate-news')` | `await Endpoints.url(Service.news, '/generate-news')` |
| 2 | `Uri.parse('http://$serverIp:5012/status/$articleId')` | `await Endpoints.newsStatusUrl(articleId)` |
| 3 | `'http://$serverIp:5012/download/$articleId'` | `await Endpoints.newsDownloadUrl(articleId, userId)` |
| 4 | `Uri.parse('http://$serverIp:5017/process_newsletter')` | `await Endpoints.url(Service.newsletter, '/process_newsletter')` |

All 4 also had headers changed from `{'Content-Type': 'application/json'}` to `await Endpoints.apiHeaders(Service.news/newsletter)` (adds `X-API-Key` in cloud mode).

### New helper in `endpoints.dart`
```dart
/// Returns the correct news status polling URI.
/// Local: /status/<id>, Cloud: /news-status/<id>
static Future<Uri> newsStatusUrl(String articleId) async {
  final prefs = await SharedPreferences.getInstance();
  final mode = prefs.getString('server_mode') ?? 'local';
  final baseUrl = await base(Service.news);
  final path = mode == 'cloud' ? '/news-status/$articleId' : '/status/$articleId';
  return Uri.parse('$baseUrl$path');
}
```

This parallels the existing `newsDownloadUrl()` pattern — cloud gateway uses `/news-status/<id>` (renamed to avoid collision with tour `/status/<id>`), local news service uses `/status/<id>` directly.

---

## Files changed

| File | Change |
|------|--------|
| `lib/screens/tour_generator_screen.dart` | Added `user_id` to tourData (2 sites), migrated 4 hardcoded URLs to Endpoints |
| `lib/config/endpoints.dart` | Added `newsStatusUrl()` helper |

---

## Questions for Claude

**Q1:** The `user_id` is now included in the request body for tour generation. On local mode, the orchestrator doesn't use it — it just ignores extra fields. On cloud, the gateway reads `user_id` from the body before forwarding. Is there any risk of the local orchestrator treating `user_id` as a location string or otherwise misinterpreting it? (I believe not — it reads only `location`, `tour_type`, `total_stops` — but confirm.)

**Q2:** `SharedPreferences.getInstance()` is called twice in `_generateTour` after this fix (once for the existing `tour_id_` tracking, once for `user_id`). Both are in the same async method. Should we consolidate into a single `getInstance()` call at the top for clarity, or is the current form acceptable given that `getInstance()` is a cached singleton?

---

## Test expectations (cloud mode)

- [ ] Tour generation: 200 response (no more 401 `auth_required`)
- [ ] News article generation: routes to `api.audioura.com/generate-news` (not local IP)
- [ ] News status polling: routes to `api.audioura.com/news-status/<id>` (not local `/status/<id>`)
- [ ] News download: routes to `api.audioura.com/news-download/<id>` (not local `/download/<id>`)
- [ ] Newsletter processing: routes to `api.audioura.com/process_newsletter` (not local `:5017`)
- [ ] Local mode regression: all above still work on WiFi

---

## Verdict requested

Approve for version bump to `2.1.1+9` and Ubuntu build.
