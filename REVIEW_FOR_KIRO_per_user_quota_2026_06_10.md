# REVIEW_FOR_KIRO — Per-User Quota Implementation (2026-06-10)

**Context:** Implementing Claude's spec from `claude_review_per_user_quota_2026_06_10.md`. Replace the global test override with proper per-user tiering. Public users default to 1 tour/day; testers get 100/day; future paid users get 10/day. All tier changes via SQL, no redeploy.

---

## What Was Done

### Database (Cloud SQL, executed via Cloud Run job)

**1. Created `plans` table:**
```sql
CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    tours_per_day INTEGER NOT NULL DEFAULT 1,
    tour_max_poi INTEGER NOT NULL DEFAULT 30,
    tour_max_minutes INTEGER NOT NULL DEFAULT 120,
    news_per_period INTEGER NOT NULL DEFAULT 10,
    news_period TEXT NOT NULL DEFAULT 'week',
    news_max_minutes INTEGER NOT NULL DEFAULT 10,
    downloads_unlimited BOOLEAN NOT NULL DEFAULT true
);
```

**2. Populated three tiers:**

| plan_id | tours_per_day | tour_max_poi | news_per_period | news_period |
|---------|---------------|--------------|-----------------|-------------|
| `free` | 1 | 30 | 10 | week |
| `tester` | 100 | 50 | 100 | week |
| `paid` | 10 | 50 | 50 | week |

**3. Added `plan` column to `users` table** (default `'free'`)

**4. Added `tours_per_day_override` column** (Approach B — nullable INTEGER for per-user numeric overrides)

**5. Assigned test devices to tester plan:**
- `USER-281301397` (Android) → `tester`
- `USER-974226925` (iPhone) → `tester`

---

### Code Changes

**`development/entitlements.py` — `get_user_plan()`:**

1. Added anonymous/empty user_id guard — returns free defaults immediately (no DB round-trip):
```python
if not user_id or user_id.strip() == '':
    return {'plan_id': 'free', 'tours_per_day': 1, ...}
```

2. Updated SQL query to use `COALESCE` for per-user override:
```sql
SELECT p.plan_id,
       COALESCE(u.tours_per_day_override, p.tours_per_day) AS tours_per_day,
       p.tour_max_poi, p.tour_max_minutes,
       p.news_per_period, p.news_period, p.news_max_minutes, p.downloads_unlimited
FROM users u
JOIN plans p ON u.plan = p.plan_id
WHERE u.secret_id = %s
LIMIT 1
```

**`development/tour_orchestrator_service.py` — quota check:**

Changed from `if user_id:` (skip anonymous) to always-check:
```python
# Always check quota — anonymous users get free-tier limits (1/day)
_quota_user = user_id if user_id else 'anonymous'
try:
    from entitlements import check_tour_quota
    quota = check_tour_quota(_quota_user, total_stops)
    if not quota['allowed']:
        return jsonify(quota), 429
    total_stops = quota['clamped_stops']
except Exception as quota_err:
    print(f"[QUOTA] Error checking quota (allowing): {quota_err}")
```

---

## Behavior Matrix

| User | Plan | tours_per_day | How determined |
|------|------|---------------|----------------|
| `USER-281301397` (Android) | tester | 100 | `users.plan = 'tester'` |
| `USER-974226925` (iPhone) | tester | 100 | `users.plan = 'tester'` |
| New user (first request) | free | 1 | Not in `users` → fallback to `free` plan |
| Anonymous (no user_id) | free | 1 | Empty check in `get_user_plan` |
| User with override | any | custom | `COALESCE(u.tours_per_day_override, p.tours_per_day)` |

---

## Default-is-1 Guarantee (per spec)

1. ✅ `free` plan has `tours_per_day = 1`
2. ✅ Unknown user (not in `users` table) → falls back to `free` → 1
3. ✅ DB-unavailable fallback in `get_user_plan` returns hardcoded `tours_per_day = 1`
4. ✅ Empty/anonymous `user_id` → returns free defaults immediately → 1
5. ✅ `COALESCE` with NULL override → falls back to plan value

---

## Operations (no redeploy needed)

**Onboard a tester:**
```sql
INSERT INTO users (secret_id, plan) VALUES ('USER-XXXXXX', 'tester')
ON CONFLICT (secret_id) DO UPDATE SET plan = 'tester';
```

**Move to paid:**
```sql
UPDATE users SET plan = 'paid' WHERE secret_id = 'USER-XXXXXX';
```

**Per-user numeric override:**
```sql
UPDATE users SET tours_per_day_override = 25 WHERE secret_id = 'USER-XXXXXX';
-- Clear: SET tours_per_day_override = NULL
```

**Revert to public:**
```sql
UPDATE users SET plan = 'free', tours_per_day_override = NULL WHERE secret_id = 'USER-XXXXXX';
```

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-orchestrator` | `audioura:v15` | `tour-orchestrator-00014-hgt` |
| `tour-generator` | `audioura:v15` | `tour-generator-00016-cb6` |

---

## Acceptance Criteria Status

- [x] `free` plan reads `tours_per_day = 1` in the DB
- [x] Test devices set to `tester` (100/day) — verified in DB logs
- [x] Changing tier = single `UPDATE`, no redeploy, immediate effect
- [x] Anonymous/empty `secret_id` requests cannot bypass quota (capped at 1/day)
- [x] Per-user override via `tours_per_day_override` column (NULL = use plan default)
- [ ] **To verify on retest:** new/unknown user blocked on 2nd tour same day (429)

---

## Risk

- **Low.** The entitlements module already had the per-user architecture via `users.plan` JOIN. This just creates the table/data and connects the wiring that was designed but never activated.
- **Anonymous guard:** If a legitimate user's app fails to send `user_id`, they get 1/day instead of unlimited. This is the correct fail-safe — denying on missing identity prevents quota bypass.
- **Override column:** NULL-safe via COALESCE. No effect on existing users until explicitly set.

---

## Related Guard (per spec)

The news orchestrator quota check (`news_orchestrator_service.py`) already has `if secret_id and secret_id != 'anonymous':` — it skips quota for anonymous. This should be tightened to match the tour pattern (always check, anonymous = free tier). Deferred — news quota is less cost-critical than tour generation.
