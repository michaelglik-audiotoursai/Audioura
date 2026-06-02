# iOS Mobile App Issues — Newsletter Article Download + Refresh Black Screen

**Date:** 2026-06-01  
**Reported by:** Sir Michael (testing v1.2.9+65 on iPhone)  
**For:** iOS Amazon-Q  
**Services status:** Services confirmed working (articles generated, audio produced, download endpoint returns 200)

---

## Issue A: Only 2 of 5 newsletter articles downloaded

**Steps to reproduce:**
1. Process newsletter `https://www.reloadnyc.com/r/ab1715bb?m=b04c903a-41e2-4fdf-a8fa-c27ee6adca20`
2. Services return 5 articles
3. User requests to download all 5 articles in Russian
4. Only 2 articles are downloaded and appear in the app

**Analysis:**

The services side works correctly:
- Newsletter processor found 5 articles (confirmed in DB)
- The news-orchestrator's `/download/{article_id}?language=ru` endpoint returns HTTP 200 with valid ZIP data (confirmed from log: "Download response size for ru: 1096222 bytes")
- Two articles successfully downloaded and extracted

**Likely cause (mobile-side):**
- The download loop may be timing out or failing silently after 2 articles
- A possible race condition in the sequential download logic
- The app may not be retrying failed downloads or reporting the failures

**What to check in iOS code:**
- `news_download_service.dart` or equivalent — look at the download loop logic
- Is there a timeout or concurrency limit causing early exit?
- Are failed downloads silently swallowed?

---

## Issue B: Black screen on "Refresh" button press

**Steps to reproduce:**
1. After articles are downloaded (2 of 5)
2. Press the "Refresh" button in the news/newsletter screen
3. Screen goes black
4. Only way out is to kill the app and restart

**Analysis:**

This is purely a mobile UI issue — no services calls are involved in "refresh" (it reloads locally cached data). The services logs show no additional requests during this period.

**Likely cause:**
- The refresh handler may be trying to reload a WebView or list while the state is inconsistent (e.g., some articles downloaded, some not)
- A null pointer or empty-state error in the news list rendering
- The WebView may be loading a stale or missing file path

**What to check in iOS code:**
- The "refresh" button handler in `home_screen.dart` or `news_list_screen.dart`
- Check if it tries to reload articles from disk and encounters a missing file for the 3 non-downloaded articles
- Check for unhandled exceptions in the refresh path

---

## Issue C: Single-article generation produces different article than the URL content

**Steps to reproduce:**
1. User pastes URL `https://www.reloadnyc.com/r/ab1715bb?m=b04c903a-41e2-4fdf-a8fa-c27ee6adca20` as a single news article (not newsletter)
2. Expected: Article about "The Last Great Head Fake in Software History" (the content at that URL)
3. Actual: Got a different article about "Analysis of 500+ verified Gartner and G2 reviews"

**Analysis (SERVICES CONFIRMED WORKING):**

Investigation found:
- The URL correctly redirects to `the-last-great-head-fake-in-software-history` (verified via curl)
- When processed as a newsletter earlier, services correctly extracted the right content (article `2723e285`)
- The article the user received (`ee72a68b`) has **no URL field** in the database — it was submitted as raw pasted text, not crawled from a URL
- The text the services received was: "Analysis of 500+ verified reviews across Gartner and G2: 67% of enterprise Einstein implementations..."
- This text does NOT match the article at the redirect URL — it appears to be from a different source

**Conclusion: The mobile app sent different content than the user expected.** Services faithfully processed whatever text was submitted. Possible causes:
- iOS clipboard captured different text than the user intended to paste
- The mobile app's "generate from URL" function extracted content from a different page element (sidebar, recommendation widget, or ad)
- The page content changed between when the user viewed it and when the app extracted it

**What to check in iOS code:**
- How does the mobile app handle "generate article from URL"? Does it crawl the URL itself or send it to services?
- If it crawls locally, check what content extraction logic it uses
- If it sends the URL to services, check which endpoint it calls (it should use the same newsletter-processor endpoint)

---

## Summary for iOS Amazon-Q

| Issue | Responsibility | Priority |
|---|---|---|
| A: Only 2/5 articles downloaded | **iOS** — download loop exits early | HIGH |
| B: Black screen on refresh | **iOS** — UI crash in refresh handler | HIGH |
| C: Wrong article from redirect URL | **iOS** — app sent wrong text to services | MEDIUM |

Please focus on Issues A and B. The services are returning correct data — the download endpoint gives HTTP 200 with valid ZIP data for each article ID.
