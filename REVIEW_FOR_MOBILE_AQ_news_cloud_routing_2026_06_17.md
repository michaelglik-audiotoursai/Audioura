# FOR MOBILE AMAZON-Q — News/Newsletter Cloud Routing Broken (2026-06-17)

**Lane:** Mobile (Flutter app) — iOS and Android.
**Found by:** Services Kiro, from iPhone log `log_iphone_06172026_1837.txt`.
**Severity:** P0 — news and newsletter features are completely broken on cloud.

---

## Problem

When in cloud mode, the app still calls **local** URLs for news and newsletter endpoints instead of the cloud gateway (`api.audioura.com`).

### Evidence from log:

**Newsletter processing:**
```
NEWSLETTER ERROR: ❌ https://www.lennysnewsletter.com/...: 5017/process_newsletter
```
The app calls port `5017` (local newsletter-processor) instead of `https://api.audioura.com/process_newsletter`.

Later:
```
NEWSLETTER: Making POST request to: http://192.168.1.85:5017/process_newsletter
NEWSLETTER: Making POST request to: http://192.168.1.85:5017/get_articles_by_newsletter_id
```
Explicit local IP + port.

**News article generation:**
```
NEWS GENERATION ERROR: ClientException with SocketException: Operation timed out
address = 192.168.0.218, port = 64436, uri=http://192.168.0.218:5012/generate-news
```
The app calls `http://192.168.0.218:5012/generate-news` (local WiFi) instead of `https://api.audioura.com/generate-news`.

---

## What's working

- `https://api.audioura.com/health` → ✅ (connectivity check passes)
- Tour generation on cloud → ✅ (works correctly)
- Translation on cloud → ✅
- Newsletter listing (`/newsletters_v2`) → ✅ (log shows 200, newsletters loaded)

So the app's base URL / cloud-mode detection works for **some** endpoints but not for news/newsletter.

---

## Cloud gateway routes available

These are live and tested on the server:

| App action | Cloud path | Method |
|------------|-----------|--------|
| Generate news article | `POST /generate-news` | API key required |
| Poll news status | `GET /news-status/<article_id>` | Public |
| List news articles | `GET /news-articles` | Public |
| Download news | `GET /news-download/<article_id>` | Public |
| Process newsletter | `POST /process_newsletter` | API key required |
| List newsletters | `GET /newsletters_v2` | Public |
| Get articles by newsletter | `POST /get_articles_by_newsletter_id` | Public |

---

## What to fix

In `endpoints.dart` (or wherever cloud/local URL routing is configured):

1. **News generation:** cloud mode should call `https://api.audioura.com/generate-news` (not `http://<local_ip>:5012/generate-news`)
2. **Newsletter processing:** cloud mode should call `https://api.audioura.com/process_newsletter` (not `http://<local_ip>:5017/process_newsletter`)
3. **Get articles by newsletter:** cloud mode should call `https://api.audioura.com/get_articles_by_newsletter_id` (not `http://<local_ip>:5017/get_articles_by_newsletter_id`)

The `/newsletters_v2` endpoint is already routing correctly (it returned 200 with data).

---

## Note on path renames (collision avoidance)

On cloud, some news endpoints use **different path names** than the local service to avoid collisions with tour endpoints:

| Local (direct to service) | Cloud (through gateway) |
|---------------------------|------------------------|
| `/generate-news` | `/generate-news` (same) |
| `/status/<id>` | `/news-status/<id>` (renamed) |
| `/articles` | `/news-articles` (renamed) |
| `/download/<id>` | `/news-download/<id>` (renamed) |

If the app polls status or downloads after generation, those paths need the cloud-mode mapping too.
