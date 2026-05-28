# Claude Code Review Request: Blog Homepage Pattern Detection

**Date**: 2026-05-28  
**File Changed**: `newsletter_pattern_detector.py`  
**Deployed To**: `newsletter-processor-1:/app/newsletter_pattern_detector.py`  
**Issue**: Newsletter processor only extracting 1 article from blog-style newsletter homepages instead of all listed articles

---

## Symptom

User submitted `https://www.reloadnyc.com/?ref=artificial-commonsense-newsletter` for newsletter processing. The browser shows 12 news articles on the page. The Docker newsletter processor (`newsletter-processor-1:5017`) returned only 1 article (the main page content itself).

---

## Analysis

The newsletter processing pipeline has three stages for finding articles:

1. **Main content extraction** — extracts the page itself as one article (worked correctly, produced 1 article)
2. **Pattern detection** (`newsletter_pattern_detector.py`) — uses platform-specific patterns to find linked articles
3. **Fallback URL extraction** — `extract_all_clickable_urls()` + domain-based filtering

### Why pattern detection failed:

The `detect_newsletter_patterns()` function routes to different detectors based on URL patterns:
- `quora.com` → Quora pattern
- `mailchi.mp` / MailChimp classes → MailChimp button pattern  
- `view.email.` / `email.` / `newsletter.` → Email newsletter pattern
- **Everything else** → `detect_generic_read_more_pattern()`

`reloadnyc.com` falls into the "everything else" bucket. The `detect_generic_read_more_pattern()` function **only** looks for links containing text like "read more", "continue reading", "full article", etc. The reloadnyc.com page is a Ghost-powered blog homepage where articles are presented as `<a>` tags wrapping the full article card (title + summary + author + date) — no "read more" text anywhere.

### Why fallback URL extraction also failed:

`extract_all_clickable_urls()` correctly finds all 12+ URLs on the page. However, the filtering logic in `process_newsletter()` only keeps URLs matching:
- Known news domains (bostonglobe.com, nytimes.com, reuters.com, etc.)
- Company/investor domains (`investor.`, `/press-release`, etc.)
- PR wire domains (prnewswire.com, businesswire.com, etc.)

Internal `reloadnyc.com/article-slug/` URLs don't match any of these filters, so they're all discarded.

---

## Solution

Added a new `detect_blog_homepage_pattern()` function that identifies blog/newsletter homepage listings. It's called as a fallback inside `detect_generic_read_more_pattern()` when no "read more" links are found.

### How it works:

1. Parses the base URL to get the newsletter's domain
2. Collects all `<a>` links pointing to the **same domain** with meaningful paths
3. Filters out navigation/utility paths (`/page/`, `/tag/`, `/about/`, `/subscribe/`, etc.)
4. Requires substantial link text (≥20 chars) to distinguish article cards from nav links
5. Extracts title and summary from the link text (handles headings, "By Author" patterns, date patterns)
6. **Threshold**: Only activates if 3+ unique same-domain article links are found (prevents false positives from self-referencing pages)
7. Deduplicates by URL path

### Key design decisions:

- **Same-domain only**: Prevents picking up external ad/partner links. The insight is that blog homepages list their own articles.
- **Minimum 3 articles threshold**: A page with 1-2 same-domain links is likely just navigation. 3+ strongly suggests an article listing.
- **Title extraction heuristics**: Tries `<h1>`-`<h6>` inside the link first, then splits on "By " author attribution, then falls back to sentence boundaries.
- **Date stripping**: Removes trailing date patterns like "—28 May 2026" from titles.
- **No changes to `newsletter_processor_service.py`**: The fix is entirely in the pattern detector, keeping the change minimal and isolated.

### Platforms this covers:

- Ghost (reloadnyc.com confirmed)
- WordPress blog homepages
- Substack archive pages
- Any blog that lists articles as linked cards on the homepage

---

## Test Results

### Local test (Python script):
```
RESULTS: Found 12 articles (all pattern: blog_homepage)
```

### Live Docker endpoint test:
```json
{
    "articles_created": 13,
    "articles_failed": 0,
    "articles_found": 13,
    "status": "success"
}
```

13 = 1 main page content + 12 blog articles detected by new pattern.

### Container logs confirm:
```
INFO: Blog homepage pattern detected: 12 same-domain article links found on reloadnyc.com
INFO: FINAL RESULTS: Found=13, Created=13, Failed=0
```

---

## Questions for Review

1. Is the 3-article minimum threshold appropriate, or should it be 2 (to catch smaller newsletters)?
2. The title extraction uses heuristics (split on "By ", sentence boundaries, 80-char cutoff). Are there edge cases that could produce poor titles?
3. Should the function also check for `<article>` or `<section>` HTML5 semantic elements as an additional signal that the page is a blog listing?
4. The function currently has no max limit on articles returned — it relies on the existing `max_articles` cap in `process_newsletter()`. Should it have its own cap?

---

## Files Changed

| File | Change |
|------|--------|
| `newsletter_pattern_detector.py` | Added `detect_blog_homepage_pattern()` function; updated `detect_generic_read_more_pattern()` to call it as fallback; added `from urllib.parse import urlparse, urljoin` import |
