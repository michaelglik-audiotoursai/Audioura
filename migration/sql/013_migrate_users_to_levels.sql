-- ============================================================================
-- Migration 013: Migrate existing local users onto the levels model (LOCAL-595)
-- Design of record: SUBSCRIPTION_LEVELS.md (D613) — "Migration of existing
-- local users (LEAD decision)".
-- ============================================================================
--
-- MAPPING (LEAD decision):
--   unlimited, ppu, and Michael's USER-1073427300  -> tester
--   free                                            -> l2 (grandfathered)
--
-- This populates `device_entitlement` from the current `users.plan`. It does
-- NOT change `users.plan` and does NOT touch the old `plans` rows — those are
-- kept exactly as the design requires.
--
-- SAFETY:
--   * NO DELETE anywhere.
--   * ON CONFLICT (user_id) DO NOTHING — a device that already has an
--     entitlement row (e.g. a real L3/L4 purchase) is never overwritten, so
--     re-running is safe and idempotent.
--   * Row counts per plan are reported BEFORE and AFTER via RAISE NOTICE.
--
-- PREREQUISITE: 012_subscription_levels.sql must have run (device_entitlement,
-- plans l1..tester). Run this INSIDE the target database.
-- ============================================================================

BEGIN;

-- Michael's device id (per the design). A single place to change it.
\set michael_user_id 'USER-1073427300'

DO $$
DECLARE
    n_free      INTEGER;
    n_ppu       INTEGER;
    n_unlimited INTEGER;
    n_other     INTEGER;
    de_before   INTEGER;
    de_after    INTEGER;
    de_l1       INTEGER;
    de_l2       INTEGER;
    de_tester   INTEGER;
BEGIN
    -- ── BEFORE ──────────────────────────────────────────────────────────────
    SELECT COUNT(*) INTO n_free      FROM users WHERE plan = 'free';
    SELECT COUNT(*) INTO n_ppu       FROM users WHERE plan = 'ppu';
    SELECT COUNT(*) INTO n_unlimited FROM users WHERE plan = 'unlimited';
    SELECT COUNT(*) INTO n_other     FROM users WHERE plan NOT IN ('free','ppu','unlimited') OR plan IS NULL;
    SELECT COUNT(*) INTO de_before   FROM device_entitlement;

    RAISE NOTICE '================ LOCAL-595 user migration: BEFORE ================';
    RAISE NOTICE 'users by plan: free=%  ppu=%  unlimited=%  other/NULL=%', n_free, n_ppu, n_unlimited, n_other;
    RAISE NOTICE 'device_entitlement rows before: %', de_before;
END $$;

-- ── free -> l2 ──────────────────────────────────────────────────────────────
INSERT INTO device_entitlement (user_id, level, last_activity_at)
SELECT secret_id, 'l2', NOW()
FROM users
WHERE plan = 'free'
ON CONFLICT (user_id) DO NOTHING;

-- ── ppu / unlimited -> tester ────────────────────────────────────────────────
INSERT INTO device_entitlement (user_id, level, last_activity_at)
SELECT secret_id, 'tester', NOW()
FROM users
WHERE plan IN ('ppu', 'unlimited')
ON CONFLICT (user_id) DO NOTHING;

-- ── Michael's device -> tester (explicit, in case his plan differs or his row
--    exists only in `users`). If the device already has a row, keep it. ──────
INSERT INTO device_entitlement (user_id, level, last_activity_at)
VALUES (:'michael_user_id', 'tester', NOW())
ON CONFLICT (user_id) DO NOTHING;

DO $$
DECLARE
    de_after  INTEGER;
    de_l1     INTEGER;
    de_l2     INTEGER;
    de_tester INTEGER;
    de_other  INTEGER;
BEGIN
    -- ── AFTER ────────────────────────────────────────────────────────────────
    SELECT COUNT(*) INTO de_after  FROM device_entitlement;
    SELECT COUNT(*) INTO de_l1     FROM device_entitlement WHERE level = 'l1';
    SELECT COUNT(*) INTO de_l2     FROM device_entitlement WHERE level = 'l2';
    SELECT COUNT(*) INTO de_tester FROM device_entitlement WHERE level = 'tester';
    SELECT COUNT(*) INTO de_other  FROM device_entitlement WHERE level NOT IN ('l1','l2','tester');

    RAISE NOTICE '================ LOCAL-595 user migration: AFTER =================';
    RAISE NOTICE 'device_entitlement rows after: %', de_after;
    RAISE NOTICE 'device_entitlement by level: l1=%  l2=%  tester=%  other(l3/l4)=%', de_l1, de_l2, de_tester, de_other;
    RAISE NOTICE '==================================================================';
END $$;

COMMIT;
