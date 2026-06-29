# REVIEW / SPEC FOR KIRO (Amazon-Q) — Per-User Quota Override

**Date:** 2026-06-10 · **Lane:** Cloud services (entitlements) — services only, no mobile changes.
**Author:** Claude (independent reviewer) · **Owner to implement:** Kiro.

## Goal
Replace the blunt test-phase override `UPDATE plans SET tours_per_day=100` (which raises the limit for
**everyone**) with a **per-user** quota. Public/unknown users must default to **1 tour/day**; specific testers
(and, later, paid users) get a higher limit. The tier must be **changeable manually server-side via SQL — no
redeploy** — and later assignable by a paid/phone-verification process.

## Current state (verified in `entitlements.py`)
- Limits live in the `plans` table (`tours_per_day`, `tour_max_poi`, `news_per_period`, etc.).
- `users` table has `secret_id` (the user id) and `plan` (FK → `plans.plan_id`, default `free`).
- `get_user_plan(user_id)` does a user-first join: `users u JOIN plans p ON u.plan = p.plan_id WHERE u.secret_id = %s`.
  If the user isn't found it falls back to the `free` plan; if the DB is unavailable it returns a hardcoded
  default with `tours_per_day = 1`.
- `check_tour_quota` blocks at `used_today >= plan['tours_per_day']` (429), fail-CLOSED on count errors.
- **The problem:** the test override edited the shared `free` row, so it lifted the cap globally. That must be reverted.

The good news: the architecture is already per-user via `users.plan`. We can get per-user quotas with **minimal or
zero code change.**

---

## Required changes

### Step 1 — Revert the global test override (do first)
```sql
UPDATE plans SET tours_per_day = 1 WHERE plan_id = 'free';
```
Confirms public default is 1/day again.

### Step 2 — Recommended approach (A): tier via `users.plan` — NO code change
Create a `tester` (and a future `paid`) plan, then assign individuals to it. The existing join already honors this.

```sql
-- Create / update tiers. Match the real column list of your plans table.
INSERT INTO plans
  (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES
  ('tester', 100, 50, 240, 100, 'week', 30, true),
  ('paid',    10, 50, 240,  50, 'week', 30, true)
ON CONFLICT (plan_id) DO UPDATE SET
  tours_per_day = EXCLUDED.tours_per_day,
  tour_max_poi  = EXCLUDED.tour_max_poi;
```

Onboard a tester (manual, server-side, no redeploy):
```sql
UPDATE users SET plan = 'tester' WHERE secret_id = '<device_secret_id>';
```
Move someone back to public, or to paid:
```sql
UPDATE users SET plan = 'free' WHERE secret_id = '<id>';   -- back to 1/day
UPDATE users SET plan = 'paid' WHERE secret_id = '<id>';   -- future paid tier
```

**Why this is the primary recommendation:** zero code change, instant, uses the system exactly as designed,
and the same mechanism serves the future paid tier and the "third party tells us over the phone who paid →
we flip their plan" workflow.

### Step 3 — Optional approach (B): true per-user numeric override
Use this **in addition** only if you want to give a single user a custom number without creating a plan.

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS tours_per_day_override INTEGER;  -- NULL = use plan default
```
Then change the user-first query in `get_user_plan` to prefer the override:
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
Set a one-off override:
```sql
UPDATE users SET tours_per_day_override = 25 WHERE secret_id = '<id>';  -- NULL to clear
```
`NULL` means "fall back to the plan," so the default path is unchanged.

> Recommendation: ship **A** now (it fully satisfies the request). Add **B** later only if per-user numbers are needed.

---

## Default-is-1 guarantee (must hold)
1. `free` plan `tours_per_day = 1` (after Step 1).
2. Unknown / not-in-`users` user → falls back to `free` → 1.
3. DB-unavailable fallback in `get_user_plan` already returns `tours_per_day = 1`.
4. With approach B, `COALESCE` leaves the default at the plan value when override is `NULL`.

So any user who hasn't been explicitly elevated gets exactly 1 tour/day.

## Related guard (please verify while here)
`get_tours_used_today` counts by `secret_id`. If anonymous requests arrive with an empty/NULL `secret_id`,
the count can be shared or bypassed. Recommend: reject quota-gated requests that lack a stable `secret_id`
(treat missing id as free-tier AND non-bypassable), so the per-user cap can't be sidestepped by sending no id.
(This is the "anonymous user_id bypasses quota" item from the launch digest.)

## Acceptance criteria
- [ ] After Step 1, a brand-new/unknown user is blocked on their **2nd** tour same day (429, `limit=tours_per_day`, `max=1`).
- [ ] A user set to `plan='tester'` can generate up to 100/day.
- [ ] Changing a user's tier is a single `UPDATE` with **no service redeploy** and takes effect on the next request.
- [ ] `free` plan reads `tours_per_day=1` in the DB.
- [ ] (If B is implemented) clearing the override (`NULL`) returns the user to their plan default.
- [ ] Anonymous/empty-`secret_id` requests cannot exceed 1/day.

## Rollback
- Approach A: `DELETE FROM plans WHERE plan_id IN ('tester','paid');` and reset any elevated users to `free`.
- Approach B: `ALTER TABLE users DROP COLUMN tours_per_day_override;` and revert the `get_user_plan` query.

## Out of scope (do not touch in this doc's work)
- Mobile app changes. The app already reads the 429 quota response; no client change is required for tiering.
- Payment processing / billing integration (future, separate lane).
- News quota numbers — only mirror the same per-user pattern if/when desired (`news_per_period` already lives in `plans`).
