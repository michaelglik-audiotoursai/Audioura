# Code Review — Newsletter Quota Accounting Fix (2026-06-24)

**Task:** ClickUp 86aj6k3d7
**Commit:** `b6ceb89` on `services-migration`
**Image:** `audioura:v30`
**Revisions:** `news-orchestrator-00020-b7t`, `newsletter-processor-00010-crc`

---

## Problem

`get_news_used_period` (entitlements.py:149) counted ALL `article_requests` rows for the user. A newsletter with 13 articles + 1 debit row = 14 units consumed. One newsletter exhausted a free user's entire weekly quota (10/week).

## Fix

Modified `get_news_used_period` to **exclude** newsletter-sourced articles using a `NOT EXISTS` subquery on `newsletters_article_link`:

**Before (entitlements.py:149–185):**
```python
cur.execute("""
    SELECT COUNT(*) FROM article_requests 
    WHERE secret_id = %s
    AND created_at >= date_trunc('week', CURRENT_DATE)
""", (user_id,))
```

**After (entitlements.py:149–196):**
```python
cur.execute(f"""
    SELECT COUNT(*) FROM article_requests ar
    WHERE ar.secret_id = %s
    {date_filter}
    AND NOT EXISTS (
        SELECT 1 FROM newsletters_article_link nal
        WHERE nal.article_requests_id = ar.article_id
    )
""", (user_id,))
```

### What counts toward quota now:
- ✅ Direct single-article requests (1 per article)
- ✅ Newsletter debit rows (`status='newsletter_debit'`, 1 per newsletter)
- ❌ Newsletter-linked articles (excluded — covered by the debit row)

### Result:
- 1 newsletter with 13 articles = **1 quota unit** (the debit row)
- 1 direct article = **1 quota unit**
- Free plan (10/week): user can process 10 newsletters OR 10 direct articles OR any mix

## Verification

```
POST /process_newsletter (test_mode=true, USER-281301397)
→ STATUS=200, articles_created=13, articles_failed=0, articles_detected=13 ✅
```

The orchestrator logs confirm internal service auth works (`"Internal service call verified — skipping per-article quota"`), and the SQL excludes newsletter-linked rows from the count.

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `entitlements.py` | 149–196 | `get_news_used_period` now uses `NOT EXISTS (newsletters_article_link)` to exclude newsletter articles |
