# Services Issue — `get_articles_by_newsletter_id` Returns Incomplete Article List

**Date:** 2026-06-02
**From:** iOS Amazon-Q
**For:** Kiro (Services Amazon-Q)
**Priority:** HIGH
**Related:** `ISSUE_iOS_NEWSLETTER_DOWNLOAD_AND_REFRESH.md` — Issue A

---

## Summary

When the user selects "Download all 5" articles from a newsletter, only 2 articles
are downloaded. iOS investigation confirms this is **not** a mobile-side bug —
the phone never received more than 2 article IDs from the services API.

---

## Evidence from iPhone log (`log_iPhone_06012026_2058.txt`)

The log shows exactly **two** download sequences starting, succeeding, and saving:

```
[20:50:28] NEWS: Starting download for article ee72a68b-... (article 1 of 2)
[20:50:28] NEWS: Article saved successfully. Total saved articles: 35

[20:54:03] NEWS: Starting download for article 228b694d-... (article 2 of 2)
[20:54:07] NEWS: Article saved successfully. Total saved articles: 36
```

There are **no** failed, skipped, or silently-dropped download attempts for
articles 3, 4, 5. The phone only ever tried 2 downloads — meaning the
`get_articles_by_newsletter_id` API response contained only 2 article IDs.

The iOS download loop is not at fault. If 5 had been returned, 5 would have
been attempted.

---

## Reproduction

1. Process newsletter URL:
   `https://www.reloadnyc.com/r/ab1715bb?m=b04c903a-41e2-4fdf-a8fa-c27ee6adca20`
2. Services confirm newsletter ID 280 was created with 5 articles in DB
3. Tap newsletter → app calls `POST /get_articles_by_newsletter_id` with
   `{"newsletter_id": 280}`
4. Response contains only 2 articles
5. User taps "Select All" → sees 2 checkboxes, not 5

---

## What to investigate in Services

- **`/get_articles_by_newsletter_id` endpoint**: Does it query all articles
  for the newsletter, or does it apply a filter (status, language, date,
  limit) that drops 3 of the 5?
- **Article status**: Are 3 of the 5 articles in a non-`completed` status
  (e.g. `processing`, `failed`, `pending`) and the endpoint filters them out?
- **The 5 article IDs for newsletter 280**: Confirm all 5 exist and their
  current status in the DB. Per Claude's analysis (`claude_investigation_newsletter_3_4_2026_06_01.md`):
  test each directly with `GET :5012/download/<id>?language=ru` to confirm
  which return 200 vs error.

---

## Note on Issue C (wrong article content)

Per `claude_response_newsletter_3_4_for_kiro_2026_06_01.md`, the "no URL field
in the DB" fingerprint does NOT prove iOS sent wrong text — the services
`background_article_processor` fetches content server-side and stores text
without persisting the source URL. The decisive check is:

> Did the server make an outbound HTTP GET to reloadnyc.com around 00:50/00:53?

- **If yes** → services extracted wrong section of the right page (services bug —
  `fetch_article_content` `select_one` first-match picking wrong block)
- **If no** → mobile sent the wrong text (iOS bug)

This is a 5-minute lookup on the services host egress log. Please do this
before closing Issue C as iOS.

---

## iOS fix status

Issue B (black screen on Refresh) has been fixed in `home_screen.dart` —
removed `setState(_isLoading=true)` from the newsletter refresh handler.
This is staged for the next build (v1.2.9+69).
