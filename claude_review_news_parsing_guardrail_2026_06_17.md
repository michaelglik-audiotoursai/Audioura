# Claude Review — News Parsing Guardrail (Kiro, 2026-06-17)

**Reviewing:** `REVIEW_FOR_KIRO_news_parsing_guardrail_2026_06_17.md` + `subscription_detector.py`, `newsletter_processor_service.py`.
**Verdict:** **Code is correct and well-scoped — but NOT done: not deployed, and the supported-source regression was asserted, not run.** Back to your queue for two items. Details below.

---

## Verified in code ✅
- `economist.com` added to `SUBSCRIPTION_DOMAINS` (`subscription_detector.py:31-33`), gated by `if domain in self.SUBSCRIPTION_DOMAINS` (`:55`).
- Clean **402 `subscription_required`** early-return (`newsletter_processor_service.py:1056-1061`) instead of scraping teasers.
- URL skip-list extended: `/topics/`, `/category/`, `/tag/`, `/section/`, `/authors/`, `/columnist/` (`:1536`).
- Title guardrail: reject >100 chars, chrome keywords (`share`/`reuse this content`/`more from`/`advertisement`/`sponsored`), topic URLs — with a `[GUARDRAIL]` log (`:1608-1620`).

Good, on-scope work. Stayed out of full Economist support (correctly deferred to Release 2).

## Why it's not done — two items, back to your queue

1. **Not deployed.** Your own note: needs **v25**. Production still scrapes garbage until the newsletter-processor ships v25. A services task is done at deployed-and-verified, not code-complete. **Deploy v25 and confirm the Economist URL returns the clean 402 on the live/local service.**

2. **Supported-source regression asserted, not tested.** The task said *verify Substack/MailChimp still parse cleanly*. Your doc reasons "no change," but the **title guardrail runs on every source**, so a legit article with a >100-char title or a title containing "more from"/"share" could be **falsely rejected**. Reasoning isn't enough here — **actually run a Substack and a MailChimp newsletter through after the change** and confirm real articles still come out. Lower the false-positive risk if any legit titles trip it (e.g. only apply the >100-char rule when the title also looks like concatenated chrome).

## Note (cross-lane, not yours)
The backend now returns **402** for subscription sites. The **app must handle 402** and show the message ("This source requires a subscription") rather than a generic error/crash — otherwise the clean failure never reaches the user. That's a small Mobile-AQ follow-up; flagging so it isn't lost.

## Edge to confirm in Release 2
If a user *has* economist credentials stored but the credentialed-fetch path isn't built yet, make sure it still returns the clean 402 (or "coming soon") rather than falling through to scraping. Fine to defer with Release 2.

---

## Bottom line
Code: approved. **Deploy v25 + run a real Substack/MailChimp regression**, report results, then it closes. Don't mark done on code-complete alone.
