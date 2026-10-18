-- ============================================================================
-- Migration 039: Per-plan article character limit (LOCAL-708 / D670)
-- ============================================================================
--
-- WHY (D670):
--   Michael wants the Administrator plan to listen to (and read) articles up to
--   ~5 pages. Today the article text limit keys on retired wallet tiers
--   (free / ppu / unlimited) and the audio path is hard-capped at 5,000 chars.
--   This migration moves the limit into the `plans` table, one column per plan,
--   so it is changeable by SQL with no redeploy — same mechanism as every other
--   number in the D613 levels model (see 012_subscription_levels.sql).
--
-- WHAT:
--   Add `plans.article_char_limit INTEGER` (nullable). article_truncation.py
--   reads it for the listener's plan and falls back to a CODE DEFAULT of 5,000
--   when the column is NULL or missing (older DBs / plans with no value).
--
--   Per-plan values (D670):
--       l1     5000   (install / free listen tier)
--       l2     5000   (free generate tier)
--       l3    10000   ($10 pack)
--       l4    15000   ($25 round)
--       admin 15000   (Administrator / Michael's own devices — ~5 pages)
--       tester 15000  (internal testers get the top limit)
--       free   5000   (legacy wallet plan, retained)
--       ppu    5000   \ legacy wallet plans — leave at the code default so a
--       unlimited 5000 / stray legacy row never reads a surprising value
--
--   NEWS_FREE_CHAR_LIMIT / NEWS_SUBSCRIBED_CHAR_LIMIT env vars still work as a
--   GLOBAL CEILING on top of the per-plan value (emergency throttle, no
--   redeploy) — enforced in article_truncation.py, not here.
--
-- IDEMPOTENCY:
--   Additive only. ADD COLUMN IF NOT EXISTS + per-plan UPDATE. No DELETE, no
--   DROP. Safe to run many times. LEAD applies migrations.
-- ============================================================================

BEGIN;

-- 1. The column. Nullable: a NULL means "use the code default (5,000)".
ALTER TABLE plans ADD COLUMN IF NOT EXISTS article_char_limit INTEGER;

-- 2. Per-plan values (D670). UPDATE (not INSERT) — these plan rows already
--    exist from migrations 010/012/014. A plan with no row here keeps NULL and
--    the code default applies.
UPDATE plans SET article_char_limit =  5000 WHERE plan_id = 'l1';
UPDATE plans SET article_char_limit =  5000 WHERE plan_id = 'l2';
UPDATE plans SET article_char_limit = 10000 WHERE plan_id = 'l3';
UPDATE plans SET article_char_limit = 15000 WHERE plan_id = 'l4';
UPDATE plans SET article_char_limit = 15000 WHERE plan_id = 'admin';
UPDATE plans SET article_char_limit = 15000 WHERE plan_id = 'tester';

-- Legacy wallet plans (free/ppu/unlimited) — set the free-tier value explicitly
-- so the column is populated for every known plan; code default would give the
-- same 5,000 but an explicit value is clearer for an operator reading the table.
UPDATE plans SET article_char_limit =  5000 WHERE plan_id = 'free';
UPDATE plans SET article_char_limit =  5000 WHERE plan_id = 'ppu';
UPDATE plans SET article_char_limit =  5000 WHERE plan_id = 'unlimited';

COMMIT;
