-- ============================================================================
-- Migration 012: Subscription levels (LOCAL-595)
-- Design of record: SUBSCRIPTION_LEVELS.md (D613, ClickUp wdvrdayu5a)
-- ============================================================================
--
-- PURPOSE:
--   Add the data-driven level model (L1/L2/L3/L4/Tester) on top of the
--   existing `plans` table, a per-device allowance-state table, and a
--   server-side purchase ledger. The wallet/PPU model is SUPERSEDED but its
--   tables and the old `plans` rows (free/ppu/unlimited) are kept untouched.
--
-- EVERY NUMBER in the levels table is a COLUMN here — changeable by SQL with
-- no redeploy. The code holds no tier constants.
--
-- IDEMPOTENCY:
--   Additive only. Every ALTER uses IF NOT EXISTS, every INSERT uses
--   ON CONFLICT, every CREATE uses IF NOT EXISTS. Safe to run many times.
--   NO DELETE, NO DROP. The user-row migration lives separately in
--   013_migrate_users_to_levels.sql so this schema file is pure structure.
-- ============================================================================

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- 1. Extend `plans` with one column per number in the levels table.
--    The old quota columns (tours_per_day, tour_max_poi, ...) are retained so
--    free/ppu/unlimited rows and the legacy check_tour_quota path keep working.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE plans ADD COLUMN IF NOT EXISTS tours_per_month        INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS fresh_per_pack         INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS edits_per_pack         INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS ops_per_pack           INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS max_stops              INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS max_new_stops_per_edit INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS by_reference_only      BOOLEAN DEFAULT FALSE;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS referrals_allowed      INTEGER DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS referral_period        VARCHAR(10);  -- 'lifetime' | 'month' | NULL
ALTER TABLE plans ADD COLUMN IF NOT EXISTS seat_cap               INTEGER;      -- NULL = no cap
ALTER TABLE plans ADD COLUMN IF NOT EXISTS can_sell               BOOLEAN DEFAULT FALSE;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS price_usd              NUMERIC(10,2) DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS inactivity_days        INTEGER;      -- NULL/0 = never

-- ───────────────────────────────────────────────────────────────────────────
-- 2. Seed the five level rows with the exact values from the design doc.
--    INSERT ... ON CONFLICT DO UPDATE so re-running this migration re-asserts
--    the canonical values (these rows are owned by this migration).
--
--    Legend (NULL where a dimension does not apply to a level):
--      tours_per_day / tours_per_month : L2/Tester daily & monthly fresh caps
--      fresh_per_pack / edits_per_pack : L3 consumable pack counters
--      ops_per_pack                    : L4 combined (new + edit) pool
--      max_stops                       : hard ceiling per tour (clamp/refuse)
--      max_new_stops_per_edit          : cap on stops a single edit may add
--      by_reference_only               : L2 — reuse researched stops only
--      referrals_allowed/referral_period/seat_cap/can_sell/price_usd/inactivity_days
--
--    NOTE: the legacy NOT NULL quota columns (tours_per_day, tour_max_poi,
--    tour_max_minutes, news_per_period, news_period, news_max_minutes,
--    downloads_unlimited) must be supplied for every row. tours_per_day is
--    reused for the new model's daily cap; the others are given sane values.
-- ───────────────────────────────────────────────────────────────────────────

-- L1 Install — listen/download/reuse only; NO new tours.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack,
    max_stops, max_new_stops_per_edit, by_reference_only,
    referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days
) VALUES (
    'l1', 0, 0, 120,
    10, 'month', 10, TRUE,
    0, 0, 0, 0,
    0, 0, FALSE,
    0, NULL, NULL, FALSE, 0.00, NULL
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_month = EXCLUDED.tours_per_month,
    fresh_per_pack = EXCLUDED.fresh_per_pack,
    edits_per_pack = EXCLUDED.edits_per_pack,
    ops_per_pack = EXCLUDED.ops_per_pack,
    max_stops = EXCLUDED.max_stops,
    max_new_stops_per_edit = EXCLUDED.max_new_stops_per_edit,
    by_reference_only = EXCLUDED.by_reference_only,
    referrals_allowed = EXCLUDED.referrals_allowed,
    referral_period = EXCLUDED.referral_period,
    seat_cap = EXCLUDED.seat_cap,
    can_sell = EXCLUDED.can_sell,
    price_usd = EXCLUDED.price_usd,
    inactivity_days = EXCLUDED.inactivity_days;

-- L2 Free — 1/day, 3/month, <=5 stops, by reference only. 7 idle days -> L1.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack,
    max_stops, max_new_stops_per_edit, by_reference_only,
    referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days
) VALUES (
    'l2', 1, 5, 120,
    10, 'month', 10, TRUE,
    3, NULL, NULL, NULL,
    5, 0, TRUE,
    0, NULL, 100, FALSE, 0.00, 7
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_month = EXCLUDED.tours_per_month,
    fresh_per_pack = EXCLUDED.fresh_per_pack,
    edits_per_pack = EXCLUDED.edits_per_pack,
    ops_per_pack = EXCLUDED.ops_per_pack,
    max_stops = EXCLUDED.max_stops,
    max_new_stops_per_edit = EXCLUDED.max_new_stops_per_edit,
    by_reference_only = EXCLUDED.by_reference_only,
    referrals_allowed = EXCLUDED.referrals_allowed,
    referral_period = EXCLUDED.referral_period,
    seat_cap = EXCLUDED.seat_cap,
    can_sell = EXCLUDED.can_sell,
    price_usd = EXCLUDED.price_usd,
    inactivity_days = EXCLUDED.inactivity_days;

-- L3 $10 pack — 5 fresh per pack, <=10 stops; edits 5 per pack, <=10 new/edit;
--               3 lifetime referrals.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack,
    max_stops, max_new_stops_per_edit, by_reference_only,
    referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days
) VALUES (
    'l3', 999, 10, 300,
    999, 'month', 60, TRUE,
    NULL, 5, 5, NULL,
    10, 10, FALSE,
    3, 'lifetime', NULL, FALSE, 10.00, NULL
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_month = EXCLUDED.tours_per_month,
    fresh_per_pack = EXCLUDED.fresh_per_pack,
    edits_per_pack = EXCLUDED.edits_per_pack,
    ops_per_pack = EXCLUDED.ops_per_pack,
    max_stops = EXCLUDED.max_stops,
    max_new_stops_per_edit = EXCLUDED.max_new_stops_per_edit,
    by_reference_only = EXCLUDED.by_reference_only,
    referrals_allowed = EXCLUDED.referrals_allowed,
    referral_period = EXCLUDED.referral_period,
    seat_cap = EXCLUDED.seat_cap,
    can_sell = EXCLUDED.can_sell,
    price_usd = EXCLUDED.price_usd,
    inactivity_days = EXCLUDED.inactivity_days;

-- L4 $25 round — 25 ops (new + edit, any mix), <=25 stops, <=10 new/edit;
--                5/month referrals; can sell (flag only, enforced later).
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack,
    max_stops, max_new_stops_per_edit, by_reference_only,
    referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days
) VALUES (
    'l4', 999, 25, 300,
    999, 'month', 60, TRUE,
    NULL, NULL, NULL, 25,
    25, 10, FALSE,
    5, 'month', NULL, TRUE, 25.00, NULL
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_month = EXCLUDED.tours_per_month,
    fresh_per_pack = EXCLUDED.fresh_per_pack,
    edits_per_pack = EXCLUDED.edits_per_pack,
    ops_per_pack = EXCLUDED.ops_per_pack,
    max_stops = EXCLUDED.max_stops,
    max_new_stops_per_edit = EXCLUDED.max_new_stops_per_edit,
    by_reference_only = EXCLUDED.by_reference_only,
    referrals_allowed = EXCLUDED.referrals_allowed,
    referral_period = EXCLUDED.referral_period,
    seat_cap = EXCLUDED.seat_cap,
    can_sell = EXCLUDED.can_sell,
    price_usd = EXCLUDED.price_usd,
    inactivity_days = EXCLUDED.inactivity_days;

-- Tester — 10/day, 50/month, <=5 stops, <=5 new/edit; 3 referrals; cap 50/mo.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack,
    max_stops, max_new_stops_per_edit, by_reference_only,
    referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days
) VALUES (
    'tester', 10, 5, 300,
    999, 'month', 60, TRUE,
    50, NULL, NULL, NULL,
    5, 5, FALSE,
    3, 'month', NULL, FALSE, 0.00, NULL
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_month = EXCLUDED.tours_per_month,
    fresh_per_pack = EXCLUDED.fresh_per_pack,
    edits_per_pack = EXCLUDED.edits_per_pack,
    ops_per_pack = EXCLUDED.ops_per_pack,
    max_stops = EXCLUDED.max_stops,
    max_new_stops_per_edit = EXCLUDED.max_new_stops_per_edit,
    by_reference_only = EXCLUDED.by_reference_only,
    referrals_allowed = EXCLUDED.referrals_allowed,
    referral_period = EXCLUDED.referral_period,
    seat_cap = EXCLUDED.seat_cap,
    can_sell = EXCLUDED.can_sell,
    price_usd = EXCLUDED.price_usd,
    inactivity_days = EXCLUDED.inactivity_days;

-- ───────────────────────────────────────────────────────────────────────────
-- 3. Per-device allowance state.
--    One row per device (keyed on the anonymous secret_id / user_id). Holds
--    the current level, the open pack/anniversary window, and the running
--    counters the enforcement reads/writes. NO personal data.
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS device_entitlement (
    user_id          VARCHAR(255) PRIMARY KEY,
    level            VARCHAR(20) NOT NULL DEFAULT 'l1' REFERENCES plans(plan_id),
    pack_started_at  TIMESTAMP,          -- when the current L3/L4 pack began; NULL for L1/L2
    anniversary_at   TIMESTAMP,          -- pack_started_at + 1 calendar month (clamped)
    fresh_used       INTEGER NOT NULL DEFAULT 0,  -- fresh generations used this pack
    edits_used       INTEGER NOT NULL DEFAULT 0,  -- stop-adding edits used this pack
    ops_used         INTEGER NOT NULL DEFAULT 0,  -- combined ops used this pack (L4)
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_entitlement_level
    ON device_entitlement(level);
CREATE INDEX IF NOT EXISTS idx_device_entitlement_activity
    ON device_entitlement(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_device_entitlement_anniversary
    ON device_entitlement(anniversary_at);

-- ───────────────────────────────────────────────────────────────────────────
-- 4. Purchase ledger. Server-side record of each verified IAP. transaction_id
--    is UNIQUE so the same purchase can never grant twice. Holds NO personal
--    data — only the anonymous user_id/device and store metadata.
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS purchases (
    id             SERIAL PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL UNIQUE,
    store          VARCHAR(20)  NOT NULL,          -- 'apple' | 'google' | 'stub'
    product        VARCHAR(50)  NOT NULL,          -- e.g. 'l3_pack_10' | 'l4_round_25'
    user_id        VARCHAR(255) NOT NULL,
    amount         NUMERIC(10,2),
    verified_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_status     TEXT                            -- verifier's raw response/status
);

CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id);

COMMIT;
