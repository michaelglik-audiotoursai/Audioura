-- ============================================================================
-- LOCAL-807B live-proof base schema (NOT a migration — proof DB only)
-- ============================================================================
-- The minimal structure the LOCAL-807 subscription routes read, lifted verbatim
-- (column-for-column) from the real migrations so migration 060 applies on top
-- unchanged:
--   * plans                — migration 003 base + migration 012 level columns
--   * device_entitlement   — migration 012
--   * purchases            — migration 012
--   * l1..l4 + tester rows — migration 012 seed (so previous_level drop-back and
--                            the /entitlements/me level lookup resolve)
-- The users/communities/seats/etc. tables are intentionally omitted: the
-- subscription routes under test (/subscriptions/verify, /iap/apple/notifications,
-- /entitlements/me) do not touch them. This file lands before 01_migration_060.sql.
-- ============================================================================

BEGIN;

-- plans: migration 003 base columns ------------------------------------------
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

-- plans: migration 012 level columns -----------------------------------------
ALTER TABLE plans ADD COLUMN IF NOT EXISTS tours_per_month        INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS fresh_per_pack         INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS edits_per_pack         INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS ops_per_pack           INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS max_stops              INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS max_new_stops_per_edit INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS by_reference_only      BOOLEAN DEFAULT FALSE;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS referrals_allowed      INTEGER DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS referral_period        VARCHAR(10);
ALTER TABLE plans ADD COLUMN IF NOT EXISTS seat_cap               INTEGER;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS can_sell               BOOLEAN DEFAULT FALSE;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS price_usd              NUMERIC(10,2) DEFAULT 0;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS inactivity_days        INTEGER;
-- plans: migration 016 columns read by _me_payload / _get_plan / _visible_levels.
ALTER TABLE plans ADD COLUMN IF NOT EXISTS display_name           VARCHAR(64);
ALTER TABLE plans ADD COLUMN IF NOT EXISTS hidden                 BOOLEAN NOT NULL DEFAULT FALSE;

-- Seed the standard level rows (migration 012 values) so a device can sit on a
-- base level and drop back to it when a subscription ends.
INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
    news_per_period, news_period, news_max_minutes, downloads_unlimited,
    tours_per_month, max_stops, can_sell, price_usd, display_name, hidden)
VALUES
  ('l1', 0, 0, 120, 10, 'month', 10, TRUE, 0,  0, FALSE, 0.00, 'Introduction', FALSE),
  ('l2', 1, 5, 120, 10, 'month', 10, TRUE, 3,  5, TRUE,  0.00, 'Free',         FALSE),
  ('l3', 999, 10, 300, 999, 'month', 60, TRUE, NULL, 10, TRUE, 10.00, '$10 Pack', FALSE),
  ('l4', 999, 25, 300, 999, 'month', 60, TRUE, NULL, 25, TRUE, 25.00, 'Curator',  FALSE)
ON CONFLICT (plan_id) DO NOTHING;

-- The subscription levels seeded by migration 060 are sold through the LOCAL-807
-- plans reveal screen, not the legacy level list, so hide them from
-- _visible_levels (which ranks only l1..l4). This runs AFTER 060 would — but
-- init order is base-first, so set it in 060's ON CONFLICT path instead; here we
-- only guarantee the base rows exist. (060 seeds sub_* with hidden defaulting
-- FALSE; _visible_levels puts them at rank 99 after l4 — harmless either way.)

-- device_entitlement: migration 012 -----------------------------------------
CREATE TABLE IF NOT EXISTS device_entitlement (
    user_id          VARCHAR(255) PRIMARY KEY,
    level            VARCHAR(20) NOT NULL DEFAULT 'l1' REFERENCES plans(plan_id),
    pack_started_at  TIMESTAMP,
    anniversary_at   TIMESTAMP,
    fresh_used       INTEGER NOT NULL DEFAULT 0,
    edits_used       INTEGER NOT NULL DEFAULT 0,
    ops_used         INTEGER NOT NULL DEFAULT 0,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_device_entitlement_level ON device_entitlement(level);
CREATE INDEX IF NOT EXISTS idx_device_entitlement_activity ON device_entitlement(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_device_entitlement_anniversary ON device_entitlement(anniversary_at);

-- purchases: migration 012 ---------------------------------------------------
CREATE TABLE IF NOT EXISTS purchases (
    id             SERIAL PRIMARY KEY,
    transaction_id VARCHAR(255) NOT NULL UNIQUE,
    store          VARCHAR(20)  NOT NULL,
    product        VARCHAR(50)  NOT NULL,
    user_id        VARCHAR(255) NOT NULL,
    amount         NUMERIC(10,2),
    verified_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_status     TEXT
);
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id);

-- tour_requests: the orchestrator writes one row per generation. _allowances_left
-- COUNTs rows (source='orchestrator', status='completed', scoped by day/month) to
-- compute "N new tours left" — this is the allowance the subscription selects a
-- level for. Columns as in the schema dump (migration 010).
CREATE TABLE IF NOT EXISTS tour_requests (
    id             SERIAL PRIMARY KEY,
    secret_id      VARCHAR(255),
    tour_id        VARCHAR(255),
    request_string TEXT,
    status         VARCHAR(50) DEFAULT 'started',
    started_at     TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    finished_at    TIMESTAMP,
    created_at     TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    language       VARCHAR(10) DEFAULT 'en',
    source         VARCHAR(50) DEFAULT 'orchestrator'
);
CREATE INDEX IF NOT EXISTS idx_tour_requests_secret ON tour_requests(secret_id);

-- audio_tours: minimal — the tour-purchase path reads id / original_tour_id.
-- Not exercised by the subscription path; present so no route 500s.
CREATE TABLE IF NOT EXISTS audio_tours (
    id               SERIAL PRIMARY KEY,
    tour_name        VARCHAR(255),
    request_string   TEXT,
    original_tour_id INTEGER,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- tour_unlocks: base table (migration 022). The entitlements code self-heals its
-- consumption columns + partial unique index at runtime (_ensure_unlock_consumption_schema).
CREATE TABLE IF NOT EXISTS tour_unlocks (
    id             SERIAL PRIMARY KEY,
    user_id        VARCHAR(255) NOT NULL,
    tour_id        INTEGER      NOT NULL,
    transaction_id VARCHAR(255),
    store          VARCHAR(20),
    price_usd      NUMERIC(10,2),
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tour_unlocks_user_tour UNIQUE (user_id, tour_id)
);
CREATE INDEX IF NOT EXISTS idx_tour_unlocks_user_tour ON tour_unlocks(user_id, tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_unlocks_tour ON tour_unlocks(tour_id);

-- l2_queue / l2_offers / l2_settings: migration 015 + 016's offer_ttl_minutes.
-- _me_payload calls l2_seats.queue_position / pending_offer on every request;
-- without these tables that lookup errors and aborts the request transaction
-- (the code catches the Python exception but Postgres has already marked the
-- transaction failed, so the next query — _visible_levels — fails too). The
-- real server has these tables; the proof DB needs them so /entitlements/me
-- behaves exactly as it does in production.
CREATE TABLE IF NOT EXISTS l2_queue (
    user_id      VARCHAR(255) PRIMARY KEY,
    joined_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(16) NOT NULL DEFAULT 'waiting',
    offer_misses INTEGER     NOT NULL DEFAULT 0,
    email        VARCHAR(320),
    created_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_l2_queue_status_joined ON l2_queue(status, joined_at);

CREATE TABLE IF NOT EXISTS l2_offers (
    id         SERIAL PRIMARY KEY,
    user_id    VARCHAR(255) NOT NULL,
    code       VARCHAR(32)  NOT NULL UNIQUE,
    offered_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP    NOT NULL,
    claimed_at TIMESTAMP,
    status     VARCHAR(16)  NOT NULL DEFAULT 'offered',
    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_l2_offers_user   ON l2_offers(user_id);
CREATE INDEX IF NOT EXISTS idx_l2_offers_status ON l2_offers(status);

CREATE TABLE IF NOT EXISTS l2_settings (
    id                   BOOLEAN PRIMARY KEY DEFAULT TRUE,
    auto_grant_threshold INTEGER NOT NULL,
    offer_expiry_hours   INTEGER NOT NULL,
    max_offer_misses     INTEGER NOT NULL DEFAULT 2,
    offer_ttl_minutes    INTEGER NOT NULL DEFAULT 10,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT l2_settings_singleton CHECK (id = TRUE)
);
INSERT INTO l2_settings (id, auto_grant_threshold, offer_expiry_hours, max_offer_misses)
VALUES (TRUE, 50, 72, 2) ON CONFLICT (id) DO NOTHING;

COMMIT;
