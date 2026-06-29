# REVIEW_FOR_KIRO — Economist Newsletter Parsing Issue (2026-06-17)

**Context:** Testing v2.1.1+8 on iPhone. Economist newsletter processed locally (via `http://192.168.1.85:5017/process_newsletter`). The processor reported success and extracted 2 articles, but the content is garbled — titles and authors contain concatenated fragments from multiple articles, navigation text, and sidebar content.

---

## Problem

The newsletter processor extracted these two "articles" from the Economist URL `https://www.economist.com/united-states/2026/06/16/scammers-are-preying-on-americas-illegal-immigrants`:

**Article 1:**
```json
{
  "title": "ARTICLE: Science & technology",
  "url": "https://www.economist.com/topics/science-and-technology",
  "author": "the West A bad reputation and cultural ignorance are probably responsible 3 min read Science & technology How artificial intelligence got better at building itself What does \"recursive self-improvement\" mean for the technology? 9 min read Science & technology The chemicals that reduce wrinkles Vitamins"
}
```

**Article 2:**
```json
{
  "title": "Share Reuse this content More from United States As American cities grapple with homelessness, one offers a fix Denver's answer to a stubborn problem A new intelligence chief in America may oversee a shrinking office...",
  "url": "https://www.economist.com/united-states/2026/06/16/scammers-are-preying-on-americas-illegal-immigrants"
}
```

Both are clearly wrong:
- Article 1's URL is a **topic/category page**, not an article. The "author" field is a concatenation of sidebar teasers.
- Article 2's "title" is a mix of sharing buttons ("Share Reuse this content"), related article teasers, and navigation.

---

## Root Cause Analysis

The newsletter processor has no **Economist-specific selectors**. The Economist's HTML uses paywalled article structures that don't match any of the existing selector categories:
- Not Substack
- Not MailChimp
- Not a simple `<article>` tag
- Not email-format newsletter

The processor falls through all specific selectors to the **generic fallback** which:
1. Grabs `soup.get_text()` from the entire page (including navigation, sidebars, related articles teasers)
2. Feeds that to `detect_newsletter_patterns()` which finds internal links
3. Extracts URLs including topic pages (`/topics/science-and-technology`) as "articles"
4. The "author" and "title" fields are populated from whatever surrounding text the parser finds near those URLs

---

## Specific Issues

### 1. Wrong URL extracted as article
The topic page URL (`/topics/science-and-technology`) is NOT an article — it's a category listing page. The URL filter should reject category/topic pages.

### 2. Title concatenation
The "title" field for article 2 contains sharing widget text + sidebar content because the Economist places these adjacent in the DOM. Without site-specific selectors, the parser can't distinguish article title from surrounding chrome.

### 3. Author field garbage
The "author" field contains concatenated article teaser text from a sidebar "More from Science & technology" widget.

---

## Options

### Option A: Add Economist-specific selectors (targeted fix)
Add CSS selectors specific to the Economist's article structure. The Economist typically uses:
- `article[data-body-id]` or `.article__body` for main content
- `h1.article__headline` for the title
- `.article__lead-image + .article__body` pattern

**Pros:** Fixes this specific case properly.
**Cons:** Only fixes Economist; other paywalled sites will have similar issues. Each new site needs its own selectors.

### Option B: Improve generic extraction (broader fix)
1. **Reject topic/category URLs:** Filter out URLs matching `/topics/`, `/category/`, `/tag/`, `/section/`
2. **Better title extraction:** Don't use full `get_text()` as title — use `<h1>` only, truncate to first sentence
3. **Content validation:** Reject "articles" where the title exceeds 100 characters or contains share widget keywords ("Share", "Reuse this content", "More from")

**Pros:** Improves all sites, not just Economist.
**Cons:** May not fully fix Economist without specific selectors.

### Option C: Treat as paywall limitation (document + skip)
The Economist is a paywalled site. Without subscription credentials, the processor can only see the teaser content. Document this as a known limitation — the processor already has subscription-awareness for Boston Globe / NYTimes. Adding Economist would require the same credential-authenticated access pattern.

**Pros:** Honest about limitations; no wasted effort on partial fixes.
**Cons:** User sees garbage instead of a clear "subscription required" message.

### Option D: Hybrid (recommended)
1. Add generic URL filtering (reject `/topics/`, `/category/` URLs)
2. Add content validation (reject garbled titles > 100 chars or containing share widget text)
3. For Economist specifically: detect the domain and either use specific selectors OR return a clear "subscription may be required" message instead of garbage content

---

## Severity Assessment

- **Not a regression** — this behavior has existed since the newsletter processor was built. The Economist was never specifically supported.
- **Not blocking** — tours, translations, and other news sources work. This is one unsupported site.
- **User-visible** — the garbled content is confusing and looks like a bug.
- **The mobile routing issues** (news/newsletter calling local ports in cloud mode) are P0 and more urgent.

---

## Decision Needed

1. **Priority:** Fix now, or defer to post-launch polish?
2. **Approach:** Which option (A/B/C/D) to pursue?
3. **Scope:** Should the Economist be treated as a subscription site that requires credentials (like Boston Globe)?
