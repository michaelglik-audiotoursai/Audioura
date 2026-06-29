# REVIEW_FOR_KIRO — News Parsing Guardrail (2026-06-17)

**Task:** "News parsing guardrail" — prevent garbage content from paywalled/unsupported sites from reaching users.
**Scope:** Cheap guardrail only. No full Economist support (that's Release 2 / credential pattern).

---

## Changes Made

### 1. Subscription domain early check (`newsletter_processor_service.py`)

Before any content extraction begins, the processor checks if the URL belongs to a known paywalled domain. If so, and the user has no verified credentials for that domain, it returns a clean error:

```python
# If known subscription site + no credentials → clean message, don't scrape garbage
return jsonify({
    "status": "error",
    "message": "This source (economist.com) requires a subscription. Please add your subscription credentials...",
    "error_type": "subscription_required",
    "subscription_domain": _domain
}), 402
```

### 2. Added Economist to subscription domains (`subscription_detector.py`)

```python
'economist.com': {
    'indicators': ['subscribe', 'subscription', 'premium', 'subscriber only', 'log in'],
    'paywall_text': ['Subscribe to The Economist', 'This article is for subscribers', 'Subscriber only']
}
```

### 3. Reject topic/category URLs (`newsletter_processor_service.py`)

Extended the URL skip list in the fallback URL extraction:

```python
'/topics/', '/category/', '/tag/', '/section/', '/authors/', '/columnist/'
```

These are never individual articles — they're listing/navigation pages that produce garbage when scraped.

### 4. Reject garbage titles (`newsletter_processor_service.py`)

Before articles are processed, a validation pass removes entries with:
- Titles exceeding 100 characters (indicates concatenated navigation/sidebar text)
- Titles containing chrome keywords: "share", "reuse this content", "more from", "advertisement", "sponsored"
- URLs that are topic/category pages (double-check after pattern detection)

```python
_chrome_keywords = ['share', 'reuse this content', 'more from', 'advertisement', 'sponsored']
for a in article_urls:
    if len(title) > 100: reject
    if any(kw in title.lower() for kw in _chrome_keywords): reject
    if '/topics/' in url: reject
```

---

## Effect on the Economist Test Case

**Before:** Processor scraped the Economist page, extracted 2 garbled "articles" with concatenated navigation text as titles/authors.

**After:** Processor detects `economist.com` as a known subscription domain → immediately returns 402 with `"subscription_required"` message → no garbage content shown to user.

---

## Effect on Other Sites

- **Supported sites (Substack, MailChimp, etc.):** No change — they don't hit the subscription check and their content extraction works via dedicated selectors.
- **Other paywalled sites (WSJ, WashPost):** Same clean 402 message if no credentials stored.
- **Non-paywalled sites with bad extractions:** The title validation catches garbled titles from any source, and the URL filter catches category pages universally.

---

## Files Modified

| File | Change |
|------|--------|
| `development/subscription_detector.py` | Added `economist.com` to `SUBSCRIPTION_DOMAINS` |
| `development/newsletter_processor_service.py` | Early subscription check + URL filter extension + title validation guardrail |

---

## `py_compile`

Both files: exit 0 (clean).

---

## Deployment Note

Not yet deployed — needs next image build (v25). The guardrail affects the newsletter-processor service (uses monolithic `audioura` image). Also relevant for local Docker since the test was run locally.

---

## What This Does NOT Fix (deferred to Release 2)

- Full Economist article extraction with credentials (needs Boston Globe / NYT-style credential auth pattern)
- The input-URL mismatch question (user pasted article URL into newsletter digest processor)
- Other new paywalled sites not in `SUBSCRIPTION_DOMAINS`
