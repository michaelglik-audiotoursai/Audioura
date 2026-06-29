# Investigation — Newsletter Issues #3 & #4 (Services)
**For:** Kiro Amazon-Q (Services)
**From:** Claude
**Date:** 2026-06-01
**Service:** `newsletter_processor_service.py`
**Logs traced:** `log_iphone_06012026_2045.txt`, `log_iphone_06012026_2058.txt`
**Source URL under test:** `https://www.reloadnyc.com/r/ab1715bb?m=b04c903a-41e2-4fdf-a8fa-c27ee6adca20`

---

## Caveat on evidence
These are **iPhone app** logs. They confirm the *symptoms* precisely but not the server's internal decisions. The decisive lines — per-article failure reasons and redirect quality scores — are written by `newsletter_processor_service.py` on `192.168.0.218`. To get exact drop reasons, pull that service's log for 20:48–20:54 on 2026-06-01. My root-cause pointers below are from the code; the server log will confirm which branch fired.

---

## Issue #3 — "Download all 5 in Russian" produced only 2

### What the log shows
`log_iphone_06012026_2058.txt` shows exactly **two** articles downloaded, both succeeding client-side:
- `ee72a68b-…_ru` — downloaded, ZIP extracted, saved (total 35). (line 1-18)
- `228b694d-…_ru` — download 200, 1,096,222 bytes, ZIP extracted, saved (total 36). (line 28-62)

Both client downloads returned HTTP 200 and extracted cleanly. So the loss is **not** on the phone — the server only had 2 deliverable articles to give.

### Root cause (server-side)
In `newsletter_processor_service.py`, detected articles are processed in a loop (line 1582) where **each article can be silently dropped into `failed_articles[]`** for many independent reasons, e.g.:
- Advertising URL filtered (line 1591-1598)
- Link error (line 1633)
- "Insufficient content" < 200 chars (line 1896-1897)
- "REJECTED: Advertising content detected" (line 2004)
- "REJECTED: Content too short after trimming" < 100 bytes (line 2010)
- DB constraint (line 2108), browser-automation error (line 1758)

So **5 detected → 3 rejected/failed → 2 created** is the expected behavior of this loop. The problem is that these rejections are **silent to the user**: `failed_articles` is accumulated server-side but the app just shows "2 articles," with no indication that 3 were dropped or why.

### Recommendation
1. **Surface `failed_articles` to the client.** Return the count and per-URL reason in the newsletter-processing response so the app can show "2 of 5 generated — 3 skipped (advertising/too short/…)". A silent shortfall reads as a bug even when the filters are working as designed.
2. **Pull the server log** for this run to confirm which of the six rejection branches fired for the 3 missing articles — that tells you whether the filters are too aggressive (e.g. ReloadNYC article bodies tripping the advertising/too-short checks) or the URLs were genuinely junk.
3. If the advertising/short-content thresholds are the culprit on legitimate ReloadNYC content, tune them (the `advertising_filter` and the 100/200-char floors at lines 2010 / 1896).

---

## Issue #4 — Generated article text differs from the source

### What the log shows
The two generated articles are titled/bodied (in the `title` / `original_request` fields, lines 15 & 60 of the 2058 log):
- *"Анализ более 500 проверенных отзывов компаний Gartner и G2… Einstein… окупаемости инвестиций…"*
- *"…поставщики SaaS проводят активные кампании по увеличению продаж (Agentforce, Now Assist, Breeze Intelligence)…"*

This is **Salesforce/Einstein enterprise-AI analysis** content — unrelated to a NYC daily newsletter. So the symptom ("different article text than what I copied") is confirmed in the data.

### Root cause (server-side)
`reloadnyc.com/r/ab1715bb?m=…` is a **click-tracking / redirect wrapper**, not a canonical article URL (the `/r/` path is the giveaway). The resolver at lines 499-545:
1. Fetches the original URL and scores its content quality (line 507).
2. Follows the full redirect chain with `allow_redirects=True` (line 516) and scores the final page (line 532).
3. **Picks whichever page scores higher** (`quality_improvement` logic, line 537+).

For a tracking wrapper this "best content wins" heuristic can land on a *different* article than the one the user was reading — it optimizes for content-quality score, not for "the specific article the user copied." Combined with the multi-article newsletter extraction path (the same code treats the URL as a newsletter and picks a main article + others), "generate an article from this link" yields whatever the extractor scores as the main story on the resolved page — here, an unrelated AI-industry piece.

### Recommendation
1. **Distinguish "single article from a URL" from "process a newsletter."** For issue #4 the user wanted *the content behind this specific link*. The pipeline should resolve the `/r/` redirect to its single final destination and extract **that** article only — not run newsletter multi-article detection and quality-shopping.
2. **Log and return the resolved final URL** to the client so the user can see what was actually fetched ("Generated from: <final_url>"). That makes a wrong resolution visible instead of silent.
3. **Verify the redirect actually resolved to a ReloadNYC article** in the server log (line 523 logs the chain `url -> final_redirect_url`). If `final_redirect_url` is *not* a reloadnyc.com article, the tracking link is resolving to a syndicated/sponsored target — handle that explicitly rather than extracting it as the article.

---

## Summary for triage
| Issue | Layer | Status | Core fix |
|---|---|---|---|
| #3 — 2 of 5 articles | services (`newsletter_processor_service.py`) | Working-as-coded but silent | Surface `failed_articles` to client; confirm/tune rejection thresholds from server log |
| #4 — wrong article text | services (`newsletter_processor_service.py`) | Redirect/quality heuristic picks wrong content | Single-URL mode resolves `/r/` to one final article; return resolved URL |
| #3 black screen on Refresh | iOS app (Amazon-Q) | Out of scope here | Separate mobile fix |

Neither is related to the tour-category or exhibit-verification work. Both root causes sit in `newsletter_processor_service.py` and both would be confirmed conclusively by that service's own log for the 20:48–20:54 window.
