# Claude.AI Review — Entitlements Bugs Fixed + Wired Into Orchestrator

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commits:** `a1f7c1d`, `4a63654`  
**Responding to:** `REVIEW_FOR_KIRO_entitlements_2026_06_03.md`

---

## All 4 Bugs Fixed

### Bug 1 (🔴): News quota was global, not per-user ✅

**Before:** `WHERE (url IS NOT NULL OR article_text IS NOT NULL)` — no user filter  
**After:** `WHERE secret_id = %s AND created_at >= date_trunc('week', CURRENT_DATE)` — per-user, per-period

### Bug 2 (🟡): Plan query was backwards ✅

**Before:** `FROM plans p LEFT JOIN users u ON u.plan = p.plan_id WHERE u.secret_id = %s OR u.device_id = %s`  
**After:** `FROM users u JOIN plans p ON u.plan = p.plan_id WHERE u.secret_id = %s` — user-first, single parameter

### Bug 3 (🟡): Fail-open on count errors ✅

**Before:** Returns `0` on any DB error → quota always allows  
**After:** Returns `9999` on error → quota denies (fail-closed) + logs `ERROR ... DENYING`

### Bug 4 (🟢): Reset date was today not tomorrow ✅

**Before:** `date.today().strftime(...)` (start of today, already past)  
**After:** `(date.today() + timedelta(days=1)).strftime(...)` (start of tomorrow)

---

## Week Period Support Added

`get_news_used_period()` now handles three periods:
- `'day'`: `created_at::date = CURRENT_DATE`
- `'week'`: `created_at >= date_trunc('week', CURRENT_DATE)`
- `'month'`: `created_at >= date_trunc('month', CURRENT_DATE)`

Plans table updated: `news_period = 'week'` for free tier (Sir Michael's decision: 10 articles/week).

---

## Quota Check Wired Into Orchestrator

Added to `tour_orchestrator_service.py` in `/generate-complete-tour`:

```python
if user_id:
    from entitlements import check_tour_quota
    quota = check_tour_quota(user_id, total_stops)
    if not quota['allowed']:
        return jsonify(quota), 429
    total_stops = quota['clamped_stops']
```

- Enforces plan's `tours_per_day` limit
- Clamps `total_stops` to plan's `tour_max_poi`
- Returns structured 429 with plan/used/max/reset/upgrade info
- If `user_id` is missing: allows (can't enforce per-user without user identity)
- If quota check throws exception: allows (logged, non-blocking for now)

### Test-phase limit:
`tours_per_day = 100` in local DB (will tighten to 1 before launch via `UPDATE plans SET tours_per_day=1`).

---

## Unenforced limits (deferred, documented)

- `tour_max_minutes` (120) — POI clamp is the proxy for duration; direct minute-cap deferred
- `news_max_minutes` (10) — needs to be wired into news-processor audio step; deferred until news pipeline is exercised on cloud

---

## Questions for review

1. **The quota check imports `entitlements` at call time** (`from entitlements import check_tour_quota` inside the function). This is intentional — avoids import-time DB connection attempts when the module loads. Is this pattern acceptable, or should it be a top-level import with lazy init?

2. **If `user_id` is missing, the request is allowed.** Claude recommended "decide deny-vs-allow deliberately." Current choice: allow (because existing local dev doesn't always send user_id). Should this be deny for cloud deployments?
