# Claude Review — Economist Parsing: Priority + Approach Decision (2026-06-17)

**Reviewing:** `REVIEW_FOR_KIRO_economist_parsing_2026_06_17.md`
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Decision in one line:** **Defer full Economist support to post-launch — but ship a cheap "don't show garbage" guardrail in the Beta.** Approach D, split by timeline, and treat the Economist as a **paywalled subscription site** (credential pattern), not a selector problem. Reasoning below, including one correction to the options.

---

## Agreeing with Kiro
- **Not a regression, not a launch blocker.** Pre-existing, one unsupported site, other sources work. The full fix is post-launch. ✓
- The hybrid (Option D) is the right *end state*. ✓

## The correction — selectors can't beat a paywall (re: Option A)
The Economist is **paywalled**. The full article isn't in the public HTML — only teasers/nav/sidebar are. So **Option A (Economist-specific selectors) cannot work**: even perfect selectors on the public page extract teaser chrome, which is exactly the garbage you're seeing. This isn't "we need better selectors," it's "this is a paywalled site." The repo already proves the intended pattern: `subscription_detector.py`, `subscription_article_processor.py`, and credential auth for **Boston Globe + NYT**. The Economist belongs in *that* pattern, not generic scraping.

So **Scope question (#3): yes** — the Economist is a subscription site and should be handled like Boston Globe/NYT (credential-authenticated fetch), deferred to post-launch.

## The thing that should ship for the Beta — don't render garbage
Garbled titles/authors make the app look **broken** to testers, and Audio mode is half the app. The cheap, broad win (the validation slice of Option D) prevents the worst symptom across **all** sites, not just the Economist:
- **Reject junk URLs** — `/topics/`, `/category/`, `/tag/`, `/section/` (extend the existing `advertising_url_filter.py`).
- **Sanity-check extracted fields** — reject "articles" whose title is > ~100 chars or contains chrome keywords ("Share", "Reuse this content", "More from").
- **Use `subscription_detector`** — if the domain is a known paywalled site (add Economist), return a clean **"This source may require a subscription"** message instead of scraping teasers into garbage.

A clean failure is acceptable for an unsupported site; **garbage is not.** That's the only part worth doing before July 1.

## Two things the doc didn't flag

1. **Probable input mismatch.** The test fed a single **article** URL (`/united-states/2026/06/16/scammers…`) to `/process_newsletter`, which is a **digest** extractor — it looks for article *links* on the page, so on an article page it grabs nav + "More from" teasers. Confirm the intended UX: are users meant to register newsletter/digest URLs, or article URLs? If the app lets them paste an article URL as a "newsletter," that's a validation/UX gap on top of the paywall issue. This affects how often testers will hit it.

2. **Test the sources you'll actually support.** The priority hinges on which sources testers will realistically use. **Before launch, verify the common ones work cleanly** (Substack, MailChimp, the sites you intend to support — the repo has handlers/tests for these). If only paywalled sites like the Economist break, it's a footnote. If common ones break, that's higher priority than this ticket implies.

---

## Decision

1. **Priority:** Defer full Economist support to **post-launch (Release 2)**. Ship only the **garbage-guardrail** (validation + subscription-detect message) in the Beta — small, broad, prevents the "looks broken" symptom.
2. **Approach:** **Option D, split** — now: URL filter + content validation + `subscription_detector` "subscription required" message (reuse existing infra); later: Economist via the **existing credential pattern** (Boston Globe/NYT style). **Not A** (selectors can't beat the paywall), not B alone (generic scraping can't either).
3. **Scope:** Yes — Economist = paywalled subscription site → credential flow, post-launch.

**Plus:** confirm the article-URL-vs-newsletter-URL input question, and verify the *supported* sources parse cleanly before launch — that's the real Beta risk, not the Economist itself.
