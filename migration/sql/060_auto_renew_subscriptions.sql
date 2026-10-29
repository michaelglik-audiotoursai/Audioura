-- ============================================================================
-- Migration 060: Auto-renewing subscriptions (LOCAL-807)
-- Design of record: D733 + D734 (Michael, 2026-10-29, ClickUp LOCAL-807)
-- ============================================================================
--
-- PURPOSE:
--   Add the server state for AUTO-RENEWING subscriptions (Apple first, Google
--   ready) on top of the existing data-driven level model (migration 012).
--   An active subscription maps a device to a level with tours_per_month=N; the
--   existing allowance code (subscription_levels / entitlements_api) then gates
--   exactly as it does for any level. When the subscription expires the device
--   drops back to its previous level.
--
-- WHY A NEW TABLE (`auto_renew_subscriptions`), NOT the migration-005 one:
--   Migration 005 already defines a `subscriptions` table for the SUPERSEDED
--   wallet/PPU model (tier IN ('ppu','unlimited'), credit_balance_usd, ...).
--   Its lifecycle and columns are unrelated to store-driven auto-renewal
--   (original_transaction_id, grace/billing_retry, notification dedupe). Reusing
--   that table would overload two different meanings onto one row and collide on
--   its CHECK constraints. A separate, purpose-built table keeps both models
--   intact and is additive — migration 005 is untouched.
--
-- PRODUCTS (D734 — prices are DATA here, never hard-coded in app/server):
--   Day pass   $2.99  Apple NON-renewing / Google one-time: 24h, 3 new tours.
--   Weekly     $4.99  AUTO-RENEW: 5 new tours per week.
--   Monthly    $9.99  AUTO-RENEW: 10 new tours per month.
--   Annual    $79.99  AUTO-RENEW: 10 new tours per month.
--   (The $10 five-tour pack, l3, is unchanged — migration 012.)
--
-- IDEMPOTENCY:
--   Additive only. Every CREATE/ALTER uses IF NOT EXISTS, every INSERT uses
--   ON CONFLICT. Safe to run many times. NO DELETE, NO DROP.
-- ============================================================================

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- 1. tours_per_week on `plans`.
--    The level model (012) already has tours_per_month. The Weekly plan grants
--    a weekly allowance, so add a sibling column rather than overloading
--    tours_per_month. NULL means "this level has no weekly cap" (every existing
--    row), so behaviour is byte-for-byte unchanged for them.
-- ───────────────────────────────────────────────────────────────────────────
ALTER TABLE plans ADD COLUMN IF NOT EXISTS tours_per_week INTEGER;

-- One column so the store-facing product id and the D734 term length live in
-- the DB next to the level, readable by the /entitlements/me payload and the
-- plans screen without any hard-coded map in code. NULL for non-subscription
-- levels. `sub_period` is the renewal/term period in plain words.
ALTER TABLE plans ADD COLUMN IF NOT EXISTS store_product_id VARCHAR(100);
ALTER TABLE plans ADD COLUMN IF NOT EXISTS sub_period VARCHAR(10);  -- 'day'|'week'|'month'|'year'|NULL
ALTER TABLE plans ADD COLUMN IF NOT EXISTS auto_renews BOOLEAN DEFAULT FALSE;

-- ───────────────────────────────────────────────────────────────────────────
-- 2. Seed the four subscription-level plan rows. EVERY number is a column —
--    changeable by UPDATE, no redeploy. Prices are the D734 values but are DATA
--    (Michael's final yes pending): correct a price with one UPDATE here.
--
--    Legend of the dimensions that matter for a subscription level:
--      tours_per_day/tours_per_week/tours_per_month : the fresh-tour allowance
--        the enforcement reads for the period;
--      downloads_unlimited : catalog downloads + translations included (D734);
--      price_usd           : the store display price (also shown on the plans
--        screen when the store price is unavailable);
--      store_product_id    : the Apple/Google product id this level is bought as;
--      sub_period          : the term length; auto_renews : true for week/month/
--        year (renewal terms shown), false for the day pass (non-renewing).
--      max_stops           : a per-tour stop ceiling matching the paid levels.
-- ───────────────────────────────────────────────────────────────────────────

-- Day pass — 24h, 3 new tours, NON-renewing. tours_per_day holds the 3 (the day
-- IS the whole term), tours_per_week/month NULL.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, tours_per_week, max_stops, can_sell, price_usd,
    store_product_id, sub_period, auto_renews
) VALUES (
    'sub_day', 3, 10, 300,
    999, 'month', 60, TRUE,
    NULL, NULL, 10, FALSE, 2.99,
    'audioura.sub.day', 'day', FALSE
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_week = EXCLUDED.tours_per_week,
    tours_per_month = EXCLUDED.tours_per_month,
    downloads_unlimited = EXCLUDED.downloads_unlimited,
    max_stops = EXCLUDED.max_stops,
    price_usd = EXCLUDED.price_usd,
    store_product_id = EXCLUDED.store_product_id,
    sub_period = EXCLUDED.sub_period,
    auto_renews = EXCLUDED.auto_renews;

-- Weekly — 5 new tours per week, AUTO-RENEW.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, tours_per_week, max_stops, can_sell, price_usd,
    store_product_id, sub_period, auto_renews
) VALUES (
    'sub_week', 999, 10, 300,
    999, 'month', 60, TRUE,
    NULL, 5, 10, FALSE, 4.99,
    'audioura.sub.weekly', 'week', TRUE
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_week = EXCLUDED.tours_per_week,
    tours_per_month = EXCLUDED.tours_per_month,
    downloads_unlimited = EXCLUDED.downloads_unlimited,
    max_stops = EXCLUDED.max_stops,
    price_usd = EXCLUDED.price_usd,
    store_product_id = EXCLUDED.store_product_id,
    sub_period = EXCLUDED.sub_period,
    auto_renews = EXCLUDED.auto_renews;

-- Monthly — 10 new tours per month, AUTO-RENEW.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, tours_per_week, max_stops, can_sell, price_usd,
    store_product_id, sub_period, auto_renews
) VALUES (
    'sub_month', 999, 10, 300,
    999, 'month', 60, TRUE,
    10, NULL, 10, FALSE, 9.99,
    'audioura.sub.monthly', 'month', TRUE
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_week = EXCLUDED.tours_per_week,
    tours_per_month = EXCLUDED.tours_per_month,
    downloads_unlimited = EXCLUDED.downloads_unlimited,
    max_stops = EXCLUDED.max_stops,
    price_usd = EXCLUDED.price_usd,
    store_product_id = EXCLUDED.store_product_id,
    sub_period = EXCLUDED.sub_period,
    auto_renews = EXCLUDED.auto_renews;

-- Annual — 10 new tours per month (same monthly allowance), AUTO-RENEW yearly.
INSERT INTO plans (
    plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, tours_per_week, max_stops, can_sell, price_usd,
    store_product_id, sub_period, auto_renews
) VALUES (
    'sub_year', 999, 10, 300,
    999, 'month', 60, TRUE,
    10, NULL, 10, FALSE, 79.99,
    'audioura.sub.annual', 'year', TRUE
)
ON CONFLICT (plan_id) DO UPDATE SET
    tours_per_day = EXCLUDED.tours_per_day,
    tours_per_week = EXCLUDED.tours_per_week,
    tours_per_month = EXCLUDED.tours_per_month,
    downloads_unlimited = EXCLUDED.downloads_unlimited,
    max_stops = EXCLUDED.max_stops,
    price_usd = EXCLUDED.price_usd,
    store_product_id = EXCLUDED.store_product_id,
    sub_period = EXCLUDED.sub_period,
    auto_renews = EXCLUDED.auto_renews;

-- Human display names for the subscription levels, so the plans screen's active
-- banner reads "Weekly — renews … · 5 new tours left" and not the raw plan_id
-- (display_name is read by entitlements_api._me_payload / _visible_levels,
-- migration 016). Guarded UPDATEs — they only touch the rows seeded above, and
-- re-asserting them is idempotent. LOCAL-807B live-run fix: the seeds set every
-- other number but left display_name NULL, so the banner showed "sub_week".
UPDATE plans SET display_name = 'Day pass' WHERE plan_id = 'sub_day';
UPDATE plans SET display_name = 'Weekly'   WHERE plan_id = 'sub_week';
UPDATE plans SET display_name = 'Monthly'  WHERE plan_id = 'sub_month';
UPDATE plans SET display_name = 'Annual'   WHERE plan_id = 'sub_year';

-- ───────────────────────────────────────────────────────────────────────────
-- 3. The auto-renewing subscription state table. One row per subscription
--    (keyed by the store's ORIGINAL transaction id / purchase token), holding
--    the lifecycle the store notifications drive. Holds NO personal data — only
--    the anonymous device user_id and store metadata.
--
--    `previous_level` records what the device was on the moment the sub first
--    became active, so expiry/revoke drops it back to exactly that level
--    (D733 §4) rather than guessing. `status` is the full lifecycle the
--    notifications report.
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_renew_subscriptions (
    id                       SERIAL PRIMARY KEY,
    user_id                  VARCHAR(255) NOT NULL,
    store                    VARCHAR(20)  NOT NULL,          -- 'apple' | 'google' | 'stub'
    product_id               VARCHAR(100) NOT NULL,          -- store product id (audioura.sub.*)
    level                    VARCHAR(20)  NOT NULL REFERENCES plans(plan_id),
    original_transaction_id  VARCHAR(255) NOT NULL,          -- Apple originalTransactionId / Google purchaseToken
    status                   VARCHAR(20)  NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'grace', 'billing_retry',
                          'expired', 'revoked', 'refunded')),
    period_start             TIMESTAMPTZ,
    period_end               TIMESTAMPTZ,                    -- current paid-through / expiry
    auto_renew               BOOLEAN NOT NULL DEFAULT TRUE,
    previous_level           VARCHAR(20),                    -- level to drop back to on expiry
    last_event_at            TIMESTAMPTZ,                    -- signedDate/eventTime of the last applied event
    created_at               TIMESTAMPTZ DEFAULT now(),
    updated_at               TIMESTAMPTZ DEFAULT now()
);

-- The original transaction id is the subscription's identity: one row per
-- subscription, so store notifications UPSERT on it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_auto_renew_sub_original_txn
    ON auto_renew_subscriptions (original_transaction_id);

-- Look up a device's subscription(s) quickly for the /entitlements/me payload.
CREATE INDEX IF NOT EXISTS idx_auto_renew_sub_user
    ON auto_renew_subscriptions (user_id);

-- Find subscriptions due to expire (the entitlement reconcile reads this).
CREATE INDEX IF NOT EXISTS idx_auto_renew_sub_period_end
    ON auto_renew_subscriptions (period_end);

-- ───────────────────────────────────────────────────────────────────────────
-- 4. Notification dedupe ledger. Store server notifications (Apple ASSN v2,
--    Google RTDN) carry a UNIQUE id per event; an event must be applied AT MOST
--    ONCE (stores re-deliver on any non-2xx, and Pub/Sub is at-least-once). We
--    record every notification uuid we have applied; a repeat is a no-op.
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subscription_notifications (
    id                 SERIAL PRIMARY KEY,
    store              VARCHAR(20)  NOT NULL,                -- 'apple' | 'google'
    notification_uuid  VARCHAR(255) NOT NULL,                -- Apple notificationUUID / Google messageId
    notification_type  VARCHAR(50),                          -- SUBSCRIBED, DID_RENEW, ...
    original_transaction_id VARCHAR(255),
    received_at        TIMESTAMPTZ DEFAULT now(),
    raw                TEXT                                   -- decoded summary for audit (no secrets)
);

-- A notification uuid is applied at most once (idempotency key).
CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_notifications_uuid
    ON subscription_notifications (store, notification_uuid);

COMMIT;
