-- ============================================================================
-- Migration 010: Create and populate audiotours_subscribed database schema
-- LOCAL-211: Subscribed database preparation
-- ============================================================================
--
-- PURPOSE:
--   Create the `audiotours_subscribed` database with all tables that the
--   subscribed-track services need. This is an EMPTY schema — no data is
--   copied from `audiotours`.
--
-- IDEMPOTENCY:
--   Every CREATE TABLE uses IF NOT EXISTS, every ALTER uses IF NOT EXISTS,
--   every INSERT uses ON CONFLICT. Safe to run multiple times.
--
-- EXECUTION:
--   This script must be run INSIDE the audiotours_subscribed database.
--   The database itself must be created first (see companion script
--   migration/create_subscribed_db.sh).
--
-- TABLES DERIVED FROM CODE ANALYSIS:
--   The subscribed stack (tour-orchestrator, tour-generator, news-orchestrator)
--   with wallet_ledger.py, cost_meter.py, wallet_api.py needs these tables:
--
--   Base tables (from tour_orchestrator_service.py, news_orchestrator_service.py):
--     audio_tours, users, tour_requests, article_requests, news_audios,
--     coordinates, map_requests, job_status
--
--   Billing tables (from wallet_ledger.py, cost_meter.py, wallet_api.py):
--     wallet_ledger, wallet_balance_cache, wallet_subscription, cost_ledger
--
--   Entitlement tables (from 003_entitlements.sql):
--     plans, usage_counters
--
--   Subscription state tables (from 005_subscription_state.sql):
--     subscriptions, subscription_transactions, low_balance_events
--
--   Feature tables (from migrations 008):
--     news_cache, user_stop_feedback, user_class_prefs
-- ============================================================================

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 1: Base tables (storied structure, empty in subscribed)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Plans must come before users (FK: users.plan → plans.plan_id)
CREATE TABLE IF NOT EXISTS plans (
    plan_id VARCHAR(20) PRIMARY KEY,
    tours_per_day INTEGER NOT NULL DEFAULT 1,
    tour_max_poi INTEGER NOT NULL DEFAULT 30,
    tour_max_minutes INTEGER NOT NULL DEFAULT 120,
    news_per_period INTEGER NOT NULL DEFAULT 10,
    news_period VARCHAR(10) NOT NULL DEFAULT 'day',
    news_max_minutes INTEGER NOT NULL DEFAULT 10,
    downloads_unlimited BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed plan rows (idempotent)
INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('free', 1, 30, 120, 10, 'week', 10, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('ppu', 999, 50, 300, 999, 'day', 60, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
VALUES ('unlimited', 999, 50, 300, 999, 'day', 60, TRUE)
ON CONFLICT (plan_id) DO NOTHING;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    secret_id VARCHAR(255) PRIMARY KEY,
    app_version VARCHAR(50) DEFAULT 'unknown',
    is_deleted BOOLEAN DEFAULT FALSE,
    app_uninstalled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    plan VARCHAR(20) DEFAULT 'free' REFERENCES plans(plan_id),
    tours_per_day_override INTEGER
);

-- Audio tours table
CREATE TABLE IF NOT EXISTS audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL DEFAULT '',
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    language VARCHAR(10) DEFAULT 'en',
    original_tour_id INTEGER REFERENCES audio_tours(id),
    tour_content TEXT,
    content_language VARCHAR(10) DEFAULT 'en',
    stops_count INTEGER DEFAULT 0,
    creator_type VARCHAR(50) DEFAULT 'Official',
    description TEXT,
    derived_from_tour_id INTEGER REFERENCES audio_tours(id),
    draft BOOLEAN DEFAULT FALSE,
    tour_blob_uri VARCHAR(512),
    storied_mode BOOLEAN DEFAULT FALSE,
    i_con_avg NUMERIC(3,2),
    i_con_min NUMERIC(3,2),
    zip_filename VARCHAR(512),
    is_test BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_audio_tours_language ON audio_tours(language);
CREATE INDEX IF NOT EXISTS idx_audio_tours_location ON audio_tours(lat, lng);
CREATE INDEX IF NOT EXISTS idx_audio_tours_original ON audio_tours(original_tour_id);
CREATE INDEX IF NOT EXISTS idx_audio_tours_request_string ON audio_tours(request_string);
CREATE INDEX IF NOT EXISTS idx_audio_tours_tour_name ON audio_tours(tour_name);
CREATE INDEX IF NOT EXISTS idx_audio_tours_zip_filename ON audio_tours(zip_filename) WHERE zip_filename IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tours_original_name ON audio_tours(lower(tour_name)) WHERE original_tour_id IS NULL;

-- Tour requests
CREATE TABLE IF NOT EXISTS tour_requests (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    tour_id VARCHAR(255),
    request_string TEXT,
    status VARCHAR(50) DEFAULT 'started',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    language VARCHAR(10) DEFAULT 'en',
    source VARCHAR(50) DEFAULT 'orchestrator'
);

CREATE INDEX IF NOT EXISTS idx_tour_requests_language ON tour_requests(language);

-- Article requests
CREATE TABLE IF NOT EXISTS article_requests (
    id SERIAL PRIMARY KEY,
    secret_id TEXT REFERENCES users(secret_id),
    article_id VARCHAR(500) UNIQUE,
    request_string TEXT,
    article_topics INTEGER NOT NULL DEFAULT 0,
    article_text BYTEA,
    status VARCHAR(50) DEFAULT 'started',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    major_points JSONB,
    url TEXT UNIQUE,
    article_type VARCHAR(50) DEFAULT 'Others',
    subscription_required BOOLEAN DEFAULT FALSE,
    subscription_domain TEXT,
    language VARCHAR(10) DEFAULT 'en',
    original_article_id VARCHAR(500) REFERENCES article_requests(article_id),
    content_language VARCHAR(10) DEFAULT 'en'
);

CREATE INDEX IF NOT EXISTS idx_article_requests_article_id ON article_requests(article_id);
CREATE INDEX IF NOT EXISTS idx_article_requests_language ON article_requests(language);
CREATE INDEX IF NOT EXISTS idx_article_requests_secret_id ON article_requests(secret_id);
CREATE INDEX IF NOT EXISTS idx_article_subscription ON article_requests(subscription_required, subscription_domain);

-- News audios
CREATE TABLE IF NOT EXISTS news_audios (
    id SERIAL PRIMARY KEY,
    article_id TEXT NOT NULL REFERENCES article_requests(article_id),
    article_name TEXT NOT NULL,
    news_article BYTEA,
    number_requested INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    article_type VARCHAR(50) DEFAULT 'Others',
    language VARCHAR(10) DEFAULT 'en',
    original_article_id TEXT,
    news_blob_uri VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS idx_news_audios_article_id ON news_audios(article_id);
CREATE INDEX IF NOT EXISTS idx_news_audios_language ON news_audios(language);

-- Coordinates
CREATE TABLE IF NOT EXISTS coordinates (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Map requests
CREATE TABLE IF NOT EXISTS map_requests (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255) REFERENCES users(secret_id),
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job status (from 002_phase_b_cloud_readiness.sql)
CREATE TABLE IF NOT EXISTS job_status (
    job_id VARCHAR(64) PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress TEXT,
    location TEXT,
    tour_type VARCHAR(50),
    total_stops INTEGER,
    output_data JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_status_service_created ON job_status(service_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_status_created ON job_status(created_at);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 2: Entitlements (from 003_entitlements.sql)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS usage_counters (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    period_key VARCHAR(20) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, period_key, kind)
);

CREATE INDEX IF NOT EXISTS idx_usage_counters_user_period ON usage_counters(user_id, period_key);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 3: Subscription state (from 005_subscription_state.sql)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('ppu', 'unlimited')),
    state VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'lapsed', 'cancelled', 'billing_retry')),
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    provider_subscription_id VARCHAR(255),
    credit_balance_usd NUMERIC(10, 4) DEFAULT 0.0,
    cost_used_this_period_usd NUMERIC(10, 4) DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_active_user
    ON subscriptions(user_id) WHERE state IN ('active', 'billing_retry');
CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_id
    ON subscriptions(provider_subscription_id);

CREATE TABLE IF NOT EXISTS subscription_transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(secret_id) ON DELETE CASCADE,
    transaction_type VARCHAR(30) NOT NULL,
    transaction_id VARCHAR(100),
    operation_type VARCHAR(50),
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

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 4: Cost ledger (from 005_cost_ledger.sql + 006 + 007)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS cost_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_type VARCHAR(64) NOT NULL,
    user_id VARCHAR(128),
    our_cost_usd NUMERIC(12, 6) NOT NULL,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    job_id VARCHAR(128),
    breakdown JSONB,
    ceiling_breach VARCHAR(32),
    description VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_ledger_user_time ON cost_ledger(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_job ON cost_ledger(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_operation_type ON cost_ledger(operation_type, created_at);
CREATE INDEX IF NOT EXISTS idx_cost_ledger_breach ON cost_ledger(ceiling_breach) WHERE ceiling_breach IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 5: Wallet ledger (from 006_wallet_ledger.sql)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS wallet_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(128) NOT NULL,
    movement_type VARCHAR(64) NOT NULL,
    amount_cents INTEGER NOT NULL,
    balance_after_cents INTEGER NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL,
    description TEXT,
    reference_id VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency ON wallet_ledger(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time ON wallet_ledger(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_reference ON wallet_ledger(reference_id);

CREATE TABLE IF NOT EXISTS wallet_balance_cache (
    user_id VARCHAR(128) PRIMARY KEY,
    balance_cents INTEGER NOT NULL DEFAULT 0,
    last_ledger_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wallet_subscription (
    user_id VARCHAR(128) PRIMARY KEY,
    tier VARCHAR(32) NOT NULL DEFAULT 'free',
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    monthly_cost_spent_cents INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 6: News cache (from 008_news_cache.sql)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS news_cache (
    cache_key VARCHAR(64) PRIMARY KEY,
    article_id VARCHAR(255) NOT NULL,
    article_text_hash VARCHAR(64) NOT NULL,
    major_points_count INTEGER NOT NULL DEFAULT 0,
    request_string TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count INTEGER DEFAULT 0,
    content_length INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_news_cache_created_at ON news_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_news_cache_article_id ON news_cache(article_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SECTION 7: Swipe preferences (from 008_swipe_preferences.sql)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS user_stop_feedback (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    tour_id INTEGER,
    job_id VARCHAR(255),
    stop_index INTEGER NOT NULL,
    swipe SMALLINT NOT NULL CHECK (swipe IN (-1, 1)),
    class_details NUMERIC(4,3) NOT NULL,
    class_historic NUMERIC(4,3) NOT NULL,
    class_social NUMERIC(4,3) NOT NULL,
    i_con NUMERIC(3,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usf_user_id ON user_stop_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_usf_tour_stop ON user_stop_feedback(tour_id, stop_index);

CREATE TABLE IF NOT EXISTS user_class_prefs (
    user_id VARCHAR(255) PRIMARY KEY,
    alpha_details NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_details NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    alpha_historic NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_historic NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    alpha_social NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    beta_social NUMERIC(8,4) NOT NULL DEFAULT 1.0,
    pref_details NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    pref_historic NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    pref_social NUMERIC(5,4) NOT NULL DEFAULT 0.5000,
    swipe_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
