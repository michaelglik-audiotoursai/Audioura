# Review for Kiro Amazon-Q — Entitlements Implementation (commit `0103f60`)

**Date:** 2026-06-03
**Scope:** Services/GCloud only.
**Verdict:** ✅ The architecture is exactly right (data-driven `plans` table, per-user, structured 429, derived usage). ❌ **But there's a real bug that breaks per-user enforcement for news, plus a few correctness gaps to fix before wiring it in.** Details + your 3 questions below.

---

## Architecture — correct
`plans` table holds all limits; `users.plan` is the seam; usage is derived from existing tables; structured 429 with `upgrade` flag; downloads unlimited. This matches the spec and satisfies "no hardcoded limits / change tier = data change." Good.

## 🔴 Bug 1 — news quota is NOT per-user (it's global)
`get_news_used_period(user_id, period)` takes `user_id` but **never uses it**:
```python
SELECT COUNT(*) FROM article_requests
WHERE (url IS NOT NULL OR article_text IS NOT NULL)
AND created_at::date = CURRENT_DATE      -- no user filter!
```
This counts **every user's** news for today, so the 10/period limit is global — after 10 articles total across all users, everyone is blocked, and one user's usage counts against others. **Fix:** add the user filter, e.g. `AND secret_id = %s` (confirm the user column name on `article_requests` — likely `secret_id` or `user_id`) and pass `user_id` into the query. This is the most important fix; without it the news entitlement is wrong.

## 🟡 Bug 2 — `get_user_plan` query is backwards/fragile
```python
FROM plans p LEFT JOIN users u ON u.plan = p.plan_id
WHERE u.secret_id = %s OR u.device_id = %s
```
The intent is "given a user, get their plan," so it should read `FROM users u JOIN plans p ON u.plan = p.plan_id WHERE u.secret_id = %s`. As written it leads from `plans` and filters on the joined user, which only works incidentally and breaks oddly if the user's `plan` is NULL or the `device_id` column doesn't exist (the whole thing throws → silent free-default). Rewrite it user-first, and **confirm `users` actually has `secret_id` / `device_id` columns** (otherwise every call errors into the fallback).

## 🟡 Bug 3 — fail-OPEN on count errors
`get_tours_used_today` / `get_news_used_period` return **0** on any DB error → quota then always allows. So a transient DB blip = unlimited generation. For a cost-control system that's the wrong direction. Recommend: on a count error, treat as **at-limit (deny)** or at minimum log loudly and alert — don't silently grant unlimited. (The OpenAI/billing caps bound the worst case, but don't rely on them for this.)

## 🟡 Gap — two plan limits are defined but not enforced
`tour_max_minutes` (120) and `news_max_minutes` (10) are in the plan but neither `check_tour_quota` nor `check_news_quota` enforces them. POI-clamping partially bounds tour length, but not directly, and the 10-min news cap isn't applied at all. Either enforce them (cap tour duration / truncate news audio to the plan minutes) or document that POI-clamp is the intended proxy for tour duration and wire `news_max_minutes` at the news-audio step.

## 🟢 Minor — `reset` is today, not tomorrow
`tomorrow = date.today().strftime('%Y-%m-%d') + 'T00:00:00Z'` is the **start of today** (already past). Use `date.today() + timedelta(days=1)` for the real reset time. Informational field only, but it's wrong.

(Also: `password123` default in `_get_conn` is overridden by env — fine, just noting the pattern.)

---

## Your 3 questions

**Q1 — Wire `check_tour_quota` into the orchestrator now, or leave dormant?**
**Wire it now** (everyone defaults to `free`) — it's the cost control needed before any public exposure, it's ~5 lines, and testing it now validates the flow. Two conditions: **fix Bugs 1–3 first**, and **handle a missing `user_id` explicitly** (if the request has no user_id you can't enforce — decide deny-vs-allow deliberately; don't let "no user_id" become "unlimited"). 

⚠️ **One practical caveat for your own testing:** if you wire the `free` limit of **1 tour/day** now, you (and Sir Michael) can only generate **one tour per day per user** during testing — that will block the cloud smoke tests. So either bump the limit for the test phase (`UPDATE plans SET tours_per_day=100 WHERE plan_id='free'`, tighten before launch) or give your test user a high-limit plan. Wire it, but don't throttle your own testing to 1/day by accident.

**Q2 — `news_period`?** ✅ **Decided by Sir Michael: 10 articles per WEEK.** ⚠️ **This needs a code change, not just data** — `get_news_used_period` currently only handles `'day'` and `'month'`; `'week'` falls into the `else` branch and would silently behave as **monthly**. Add a `'week'` branch:
```python
elif period == 'week':
    cur.execute("""
        SELECT COUNT(*) FROM article_requests
        WHERE secret_id = %s          -- (Bug 1 fix: per-user filter)
        AND (url IS NOT NULL OR article_text IS NOT NULL)
        AND created_at >= date_trunc('week', CURRENT_DATE)
    """, (user_id,))
```
Then seed it: `UPDATE plans SET news_per_period=10, news_period='week' WHERE plan_id='free'`. Do **not** set `news_period='week'` without the code branch, or it will count monthly.

**Q3 — Populate `usage_counters` now?** No — derived counts from existing tables are fine at current volume (once Bug 1's user filter is added, the derived news count is correct too). Add counter-increments only when `COUNT(*)` gets slow (lots of history). Your instinct to wait is right.

---

## Bottom line
Right design, but **fix Bug 1 (news per-user) before anything else**, then Bugs 2–3 and the unenforced-minutes gap, then wire `check_tour_quota`/`check_news_quota` into the orchestrator/news services (Q1) with a generous test-phase limit so you don't throttle your own testing. Q2 is Sir Michael's call; Q3 (counters) waits.

**Note this is not the end of the services track** — beyond entitlements, the **`/user` gateway route + user-api deploy** is still outstanding (it's what makes the mobile `/tour-status` return `rows_affected: 1` instead of `0`).
