-- ============================================================================
-- Migration 016: Plan display names, hidden levels, level codes, queue email,
--                offer TTL in minutes (LOCAL-604)
-- Design of record: SUBSCRIPTION_LEVELS.md (D613) + LEAD ruling D619.
-- ============================================================================
--
-- PURPOSE (Michael's plan-page requests, 2026-10-06):
--   1. Each plan gets a human DISPLAY NAME, editable by SQL, that the app
--      renders instead of the l1/l2/... ids:
--         l1 "Introduction", l2 "Free", l3 "$10 Pack", l4 "Curator".
--   2. tester and admin are HIDDEN: never shown or described on the plan page.
--      The app renders only rows with hidden=false, in plan order.
--   3. LEVEL CODES: LEAD generates codes that move a device to ANY level
--      (including tester and admin). Codes are stored as sha256 HASHES ONLY —
--      never a plaintext column. Codes are reusable and revocable.
--   4. The L2 queue stores an email ONLY while a device is queued or holds an
--      unclaimed offer (nulled on claim/leave/expiry) — the offer code is
--      delivered by email (D619 reverses D613's "no email").
--   5. Offer expiry changes from 72 h to 10 MINUTES: l2_settings gets an
--      offer_ttl_minutes column defaulting to 10. The old offer_expiry_hours
--      column is retained (additive migration — no DROP) but the code now
--      reads offer_ttl_minutes.
--
-- IDEMPOTENCY:
--   Additive only. Every ALTER uses IF NOT EXISTS, every CREATE uses
--   IF NOT EXISTS, every data write uses ON CONFLICT / guarded UPDATE. There is
--   NO DELETE and NO DROP. Safe to run many times.
--
-- PREREQUISITES:
--   012_subscription_levels.sql (plans, device_entitlement),
--   014_admin_level.sql        (the 'admin' plan row),
--   015_l2_seats_queue.sql     (l2_queue, l2_settings).
-- Run INSIDE the target database.
-- ============================================================================

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- 1. Plan display names + hidden flag.
--    display_name: the words the app shows. NULL means "fall back to plan_id".
--    hidden:       TRUE => never shown/described on the plan page.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE plans ADD COLUMN IF NOT EXISTS display_name VARCHAR(64);
ALTER TABLE plans ADD COLUMN IF NOT EXISTS hidden       BOOLEAN NOT NULL DEFAULT FALSE;

-- Set the display names and visibility per D619. Guarded UPDATEs (not INSERTs)
-- so this only touches rows the earlier migrations already created, and never
-- clobbers a plan_id that does not exist here.
UPDATE plans SET display_name = 'Introduction', hidden = FALSE WHERE plan_id = 'l1';
UPDATE plans SET display_name = 'Free',         hidden = FALSE WHERE plan_id = 'l2';
UPDATE plans SET display_name = '$10 Pack',     hidden = FALSE WHERE plan_id = 'l3';
UPDATE plans SET display_name = 'Curator',      hidden = FALSE WHERE plan_id = 'l4';
UPDATE plans SET display_name = 'Tester',       hidden = TRUE  WHERE plan_id = 'tester';
UPDATE plans SET display_name = 'Administrator',hidden = TRUE  WHERE plan_id = 'admin';

-- ───────────────────────────────────────────────────────────────────────────
-- 2. Level codes. LEAD-generated codes that set a device's level to ANY level.
--    SHA-256 HASHES ONLY — the plaintext code is never stored, logged, or
--    written to a file by the task. There is DELIBERATELY no plaintext column:
--    a test asserts the only code-bearing column is the hash.
--
--      code_hash  : lowercase hex sha256 of the plaintext code (PRIMARY KEY).
--      level      : the plan_id this code grants (FK into plans; any level,
--                   including tester and admin).
--      created_at : when LEAD created it.
--      revoked_at : set to NOW() to revoke; a revoked code is refused.
--      uses       : incremented on every successful claim (codes are reusable,
--                   so Michael can switch back and forth).
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS level_codes (
    code_hash  CHAR(64)     PRIMARY KEY,                       -- hex sha256, lowercase
    level      VARCHAR(20)  NOT NULL REFERENCES plans(plan_id),
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP,                                       -- NULL => active
    uses       INTEGER      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_level_codes_level ON level_codes(level);

-- ───────────────────────────────────────────────────────────────────────────
-- 3. Queue email. Stored ONLY while a device is queued or holds an unclaimed
--    offer; the code nulls it on claim, leave and expiry. Nullable, no default.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE l2_queue ADD COLUMN IF NOT EXISTS email VARCHAR(320);

-- ───────────────────────────────────────────────────────────────────────────
-- 4. Offer TTL in minutes (design D619: 10). Additive — the old
--    offer_expiry_hours column stays (no DROP) but the seat core now reads
--    offer_ttl_minutes. ON CONFLICT DO NOTHING in migration 015 means an
--    operator-tuned value is never clobbered; here we only set the column
--    where it is still NULL (freshly added), defaulting it to 10.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE l2_settings ADD COLUMN IF NOT EXISTS offer_ttl_minutes INTEGER NOT NULL DEFAULT 10;

-- Freshly-added column defaults to 10 on existing singleton rows; this UPDATE
-- is a no-op after the first run (the DEFAULT already filled it).
UPDATE l2_settings SET offer_ttl_minutes = 10 WHERE offer_ttl_minutes IS NULL;

COMMIT;
