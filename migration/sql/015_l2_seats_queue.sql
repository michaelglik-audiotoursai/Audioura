-- ============================================================================
-- Migration 015: L2 seats, FIFO queue, claim offers, settings (LOCAL-596)
-- Design of record: SUBSCRIPTION_LEVELS.md — "L2 seats and queue" (D613).
-- ============================================================================
--
-- PURPOSE:
--   Add the data for the L2 seat lifecycle on top of the LOCAL-595 schema
--   (migration 012). Specifically:
--     * l2_queue    — the FIFO waiting list (one row per device).
--     * l2_offers   — claim offers handed to the head of the queue when a seat
--                     frees. The app shows the offer; it expires after 72 h.
--     * l2_settings — a SINGLETON settings row for the two numbers that are NOT
--                     already columns on `plans`: the auto-grant threshold (50)
--                     and the offer expiry (72 h). The code holds NO constants:
--                     seat cap (100) and inactivity days (7) already live on the
--                     `plans.l2` row (migration 012); these two live here.
--
--   Seats in use are NOT stored — they are COUNTED: a device holds an L2 seat
--   iff device_entitlement.level = 'l2'. There is no denormalised counter to
--   drift out of sync.
--
-- IDEMPOTENCY:
--   Additive only. Every CREATE uses IF NOT EXISTS, the settings INSERT uses
--   ON CONFLICT DO NOTHING (so re-running never clobbers a value an operator
--   changed by hand). NO DELETE, NO DROP. Safe to run many times.
--
-- PREREQUISITE: 012_subscription_levels.sql (device_entitlement, plans.l2).
-- Run INSIDE the target database.
-- ============================================================================

BEGIN;

-- ───────────────────────────────────────────────────────────────────────────
-- 1. FIFO queue. One row per device. `joined_at` orders the queue; `status`
--    tracks the device through its lifecycle:
--      waiting  — in line, no offer yet
--      offered  — holds a live claim offer (see l2_offers)
--      claimed  — accepted an offer and became L2 (terminal for this row)
--      expired  — missed too many offers; dropped out (terminal)
--      left     — voluntarily left the queue (terminal)
--    user_id is UNIQUE so a device can hold at most one queue row; re-joining
--    reuses the row (see the API's ON CONFLICT upsert).
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS l2_queue (
    user_id      VARCHAR(255) PRIMARY KEY,
    joined_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(16) NOT NULL DEFAULT 'waiting',
    offer_misses INTEGER     NOT NULL DEFAULT 0,  -- expired offers before 'expired'
    created_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);

-- Order the FIFO scan (waiting first, oldest first) cheaply.
CREATE INDEX IF NOT EXISTS idx_l2_queue_status_joined
    ON l2_queue(status, joined_at);

-- ───────────────────────────────────────────────────────────────────────────
-- 2. Claim offers. When a seat frees, the head of the queue gets a row here
--    with a short random `code`. The app shows it; the device claims with the
--    code. `expires_at` is `offered_at` + the offer-expiry setting (72 h).
--    `claimed_at` is set when the device successfully claims. A device may have
--    at most one LIVE (unclaimed, unexpired) offer — enforced by the job that
--    only writes one, plus the claim path that checks the latest.
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS l2_offers (
    id         SERIAL PRIMARY KEY,
    user_id    VARCHAR(255) NOT NULL,
    code       VARCHAR(32)  NOT NULL UNIQUE,
    offered_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP    NOT NULL,
    claimed_at TIMESTAMP,
    status     VARCHAR(16)  NOT NULL DEFAULT 'offered',  -- offered|claimed|expired
    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_l2_offers_user   ON l2_offers(user_id);
CREATE INDEX IF NOT EXISTS idx_l2_offers_status ON l2_offers(status);

-- ───────────────────────────────────────────────────────────────────────────
-- 3. Singleton settings row. Only the two numbers that are not already columns
--    on `plans`. `id` is pinned to TRUE with a CHECK so the table holds exactly
--    one row — a config singleton, not a growing table. ON CONFLICT DO NOTHING
--    so re-running the migration never overwrites a hand-tuned value.
--
--      auto_grant_threshold : auto-grant L2 on install only while seats in use
--                             are strictly BELOW this (design: 50).
--      offer_expiry_hours   : a claim offer lives this many hours (design: 72).
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS l2_settings (
    id                   BOOLEAN PRIMARY KEY DEFAULT TRUE,
    auto_grant_threshold INTEGER NOT NULL,
    offer_expiry_hours   INTEGER NOT NULL,
    max_offer_misses     INTEGER NOT NULL DEFAULT 2,  -- expired offers before 'expired'
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT l2_settings_singleton CHECK (id = TRUE)
);

INSERT INTO l2_settings (id, auto_grant_threshold, offer_expiry_hours, max_offer_misses)
VALUES (TRUE, 50, 72, 2)
ON CONFLICT (id) DO NOTHING;

COMMIT;
