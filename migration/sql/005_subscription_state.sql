-- Migration 005: Subscription state for Subscribed feature
-- Branch: kiro/local61-payment-provider
-- Design of record: SUBSCRIBED_DESIGN.md
--
-- Strategy: ADD a subscriptions table rather than overloading the users table.
-- Rationale: The users table is the identity table (secret_id, app_version, etc).
-- Subscription state has its own lifecycle (periods, provider IDs, balances) that
-- changes independently of user identity. A separate table also means:
--   1. free users have NO subscription row (exactly the same as today)
--   2. the plans FK on users stays intact (quota dimensions still work for free)
--   3. subscription history is naturally versioned (one row per subscription)
--
-- The existing `plans` table and its FK from `users.plan` are untouched.
-- Two new plan rows (ppu, unlimited) are added to `plans` for the FK reference,
-- but the real subscription state lives in `subscriptions`.

-- Add ppu and unlimited to plans (quota columns set generously since billing
-- replaces quota gating for paid tiers; these are safety ceilings only).
INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('ppu', 999, 50, 300, 999, 'day', 60, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('unlimited', 999, 50, 300, 999, 'day', 60, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

-- Subscription state table
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('ppu', 'unlimited')),
    state VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'lapsed', 'cancelled', 'billing_retry')),
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    provider_subscription_id VARCHAR(255),  -- RevenueCat/Apple original_transaction_id
    credit_balance_usd NUMERIC(10, 4) DEFAULT 0.0,  -- PPU balance (can go negative on refund)
    cost_used_this_period_usd NUMERIC(10, 4) DEFAULT 0.0,  -- Unlimited cost accumulator
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Only one active subscription per user at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_active_user
    ON subscriptions(user_id) WHERE state IN ('active', 'billing_retry');

CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_id
    ON subscriptions(provider_subscription_id);

-- Transaction ledger: every financial event (purchases, debits, refunds)
CREATE TABLE IF NOT EXISTS subscription_transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    transaction_type VARCHAR(30) NOT NULL,
        -- Types: subscription_purchase, consumable_purchase, renewal,
        --        usage_debit, refund_clawback, expiry, restore
    transaction_id VARCHAR(100),  -- provider-side transaction ID
    operation_type VARCHAR(50),   -- tour_generation, news_article, translation, etc.
    our_cost_usd NUMERIC(10, 6),
    user_charge_usd NUMERIC(10, 4),
    resulting_balance_usd NUMERIC(10, 4),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sub_txn_user_created
    ON subscription_transactions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sub_txn_type
    ON subscription_transactions(transaction_type);

-- Low-balance events (pending reminders)
CREATE TABLE IF NOT EXISTS low_balance_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    current_balance_usd NUMERIC(10, 4) NOT NULL,
    threshold_usd NUMERIC(10, 4) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_low_balance_pending
    ON low_balance_events(user_id, acknowledged) WHERE acknowledged = FALSE;
