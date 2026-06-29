# Claude Review — Quota Accounting Fix (2026-06-24)

**Task:** ClickUp 86aj6k3d7  
**Commit reviewed:** `b6ceb89` on `services-migration`  
**Image:** `audioura:v30`  
**Verdict:** ✅ PASS — closing task

---

## What I verified

### 1. Code change matches the claim

`entitlements.py` diff (commit b6ceb89) — only file changed. The refactored `get_news_used_period` (L149–197) now uses a single parameterised query with a `NOT EXISTS` subquery:

```sql
SELECT COUNT(*) FROM article_requests ar
WHERE ar.secret_id = %s
{date_filter}
AND NOT EXISTS (
    SELECT 1 FROM newsletters_article_link nal
    WHERE nal.article_requests_id = ar.article_id
)
```

Column names match the table definition confirmed in `newsletter_processor_service.py` (L686, L1748, L2212): `newsletters_article_link.article_requests_id` → `article_requests.article_id`. ✔

### 2. Debit row is NOT in newsletters_article_link

`newsletter_processor_service.py:993–999` inserts the debit row with `article_id = "newsletter-debit-{newsletter_id}"` and `status='newsletter_debit'`. No corresponding insert into `newsletters_article_link` follows. So the debit row passes the NOT EXISTS filter and correctly counts as 1 unit. ✔

### 3. SQL injection risk — none

`date_filter` is constructed from three hardcoded Python string literals in an if/elif/else block; no user input reaches the f-string. Only `user_id` is substituted via `%s`. ✔

### 4. Security fix regression check

`news_orchestrator_service.py` still has:
- `hmac.compare_digest(caller_token, _INTERNAL_SERVICE_SECRET)` at L89
- `data.get('source')` body-field trust: **absent** (not present anywhere in file)

No regression from the Round 3 security fix (commit 7d776ff). ✔

---

## Accounting result

| Event | Units counted |
|-------|--------------|
| 1 newsletter (13 articles + 1 debit row) | **1** (13 articles excluded by NOT EXISTS) |
| 1 direct article | **1** |
| Free plan (10/week) | 10 newsletters or 10 direct articles or any mix |

This matches the intended design stated in the task.

---

## Conclusion

Single-file change, correct logic, no regressions, no security or injection issues. Closing.
