-- 022_tour_price_tiers.sql  (LOCAL-677, D624 / D652)
--
-- Curator paid tours — the for-sale flag, the price tier, and the per-buyer
-- unlock ledger. Builds on LOCAL-595's purchase model (purchases, device_
-- entitlement, plans.can_sell = the Curator entitlement) and LOCAL-670/672's
-- per-tour rating/verified model (map_delivery already READS audio_tours.is_paid
-- and tour_reviews_service already has a per-tour "unlocked this tour" fallback).
--
-- WHAT THIS ADDS, PURELY ADDITIVELY:
--
--   1. audio_tours.price_tier SMALLINT NULL — the price TIER a curator set on
--      their own tour. NULL = FREE (the default for every existing row). The
--      tier NUMBER (1..5) maps to a dollar price in the price_tiers config table
--      below; the app and server never hard-code a dollar amount (D652: Michael
--      sets the tiers).
--
--   2. audio_tours.is_paid BOOLEAN GENERATED — kept in lock-step with price_tier
--      by the database itself (price_tier IS NOT NULL). map_delivery's
--      _is_paid_select already reads audio_tours.is_paid when the column exists,
--      so the moment this migration runs, a priced tour reads as paid with no
--      service code change. A GENERATED column cannot drift out of sync with the
--      tier and needs no trigger.
--
--   3. tour_unlocks — one row per (user, tour) a buyer has unlocked, written by
--      the purchase-verify path after the store verifies the transaction. UNIQUE
--      (user_id, tour_id) makes a replayed/duplicate purchase a no-op (idempotent
--      unlock, the same guarantee as purchases.transaction_id). A translation
--      shares its SOURCE tour's unlock: the service resolves a translation id to
--      its original before reading/writing, so tour_id here is an ORIGINAL
--      audio_tours.id.
--
--   4. price_tiers — the config table of record for the five tiers (D652 LEAD
--      defaults: $1.99 / $2.99 / $4.99 / $7.99 / $9.99, each a consumable store
--      product id). EVERY number is a ROW here, changeable by SQL with no
--      redeploy, exactly like the plans table. The code holds the fallback
--      constants (price_tiers.py) only for a DB that predates this table.
--
-- Purely additive: no DROP, no DELETE, no change to any existing column's type
-- or default. ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / INSERT ...
-- ON CONFLICT are idempotent, so applying this twice is a no-op; the pricing
-- service's own self-healing DDL (identical) converges to the same schema
-- whether or not this file was ever run.
--
-- NOT in this migration (later task, D624 §4): payouts, Stripe, the curator
-- ledger. This is the for-sale flag, the tiers, the preview and the unlock only.

BEGIN;

-- ─── 1. price_tier + generated is_paid on audio_tours ────────────────────────
-- price_tier: 1..5 (a row in price_tiers), or NULL for a FREE tour. SMALLINT,
-- nullable, default NULL — every existing tour stays free until a curator prices
-- it. A CHECK keeps a stored tier in the 1..5 range (NULL always allowed).
ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS price_tier SMALLINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.constraint_column_usage
        WHERE table_name = 'audio_tours' AND constraint_name = 'chk_audio_tours_price_tier'
    ) THEN
        ALTER TABLE audio_tours
            ADD CONSTRAINT chk_audio_tours_price_tier
            CHECK (price_tier IS NULL OR (price_tier >= 1 AND price_tier <= 5));
    END IF;
END $$;

-- is_paid: GENERATED, always STORED as (price_tier IS NOT NULL). The database
-- keeps it in sync with the tier — it can never drift, and setting/clearing the
-- tier flips is_paid automatically. map_delivery reads this column directly.
ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS is_paid BOOLEAN
    GENERATED ALWAYS AS (price_tier IS NOT NULL) STORED;

COMMENT ON COLUMN audio_tours.price_tier IS
    'LOCAL-677/D624: the price TIER a curator set on their own tour (1..5, a row '
    'in price_tiers). NULL = FREE (the default). The dollar amount lives in '
    'price_tiers, never hard-coded in code or the app (D652: Michael sets them).';
COMMENT ON COLUMN audio_tours.is_paid IS
    'LOCAL-677: GENERATED from price_tier (price_tier IS NOT NULL). Kept in sync '
    'by the database — a priced tour is paid, a NULL-tier tour is free. Read by '
    'map_delivery._is_paid_select and tour_reviews_service.is_paid_tour.';

-- A translation inherits its SOURCE tour's price. The services resolve a
-- translation to its original before reading price_tier, so no column is needed
-- on the translation row; this index speeds the per-tour price lookup either way.
CREATE INDEX IF NOT EXISTS idx_audio_tours_price_tier ON audio_tours(price_tier);


-- ─── 2. price_tiers config table (D652 defaults; Michael owns the numbers) ───
-- Each tier: a number (1..5), the store product id the app sells (consumable),
-- the buyer price in USD, and a human label. Audioura's 10% split and the store
-- fee are NOT here (payouts are a later task, D624 §4) — this table is only what
-- the buyer pays and which product unlocks it.
CREATE TABLE IF NOT EXISTS price_tiers (
    tier         SMALLINT PRIMARY KEY CHECK (tier >= 1 AND tier <= 5),
    product_id   VARCHAR(64)  NOT NULL,          -- store product id, e.g. 'audioura.tour.tier1' (consumable)
    price_usd    NUMERIC(10,2) NOT NULL,         -- what the buyer pays
    label        VARCHAR(32)  NOT NULL,          -- display label, e.g. '$4.99'
    active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- LEAD's proposed defaults (D652). ON CONFLICT re-asserts the canonical values
-- so re-running the migration restores them; Michael changes a price with one
-- UPDATE and no redeploy.
INSERT INTO price_tiers (tier, product_id, price_usd, label) VALUES
    (1, 'audioura.tour.tier1', 1.99, '$1.99'),
    (2, 'audioura.tour.tier2', 2.99, '$2.99'),
    (3, 'audioura.tour.tier3', 4.99, '$4.99'),
    (4, 'audioura.tour.tier4', 7.99, '$7.99'),
    (5, 'audioura.tour.tier5', 9.99, '$9.99')
ON CONFLICT (tier) DO UPDATE SET
    product_id = EXCLUDED.product_id,
    price_usd  = EXCLUDED.price_usd,
    label      = EXCLUDED.label,
    active     = TRUE;


-- ─── 3. tour_unlocks — per-buyer unlock ledger ───────────────────────────────
-- One row = one buyer permanently owns one tour. Written by /purchases/verify
-- (or the per-tour unlock path) AFTER the store verifies the transaction.
-- UNIQUE(user_id, tour_id) makes a replayed purchase a no-op: the same buyer can
-- never create two unlock rows for the same tour, so an unlock is idempotent
-- exactly like purchases.transaction_id. tour_id is an ORIGINAL audio_tours.id
-- (translations resolve to their original before writing).
CREATE TABLE IF NOT EXISTS tour_unlocks (
    id             SERIAL PRIMARY KEY,
    user_id        VARCHAR(255) NOT NULL,         -- the buyer (anonymous device secret_id)
    tour_id        INTEGER      NOT NULL,         -- ORIGINAL audio_tours.id the buyer unlocked
    transaction_id VARCHAR(255),                  -- the store transaction that unlocked it (NULL for a non-store grant)
    store          VARCHAR(20),                   -- 'apple' | 'google' | 'stub'
    price_usd      NUMERIC(10,2),                 -- what the buyer paid (snapshot of the tier price at unlock time)
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tour_unlocks_user_tour UNIQUE (user_id, tour_id)
);

-- Fast "has this user unlocked this tour?" (the preview gate + verified rating).
CREATE INDEX IF NOT EXISTS idx_tour_unlocks_user_tour ON tour_unlocks(user_id, tour_id);
-- Fast "how many sales does this tour have?" (the curator's Sales count).
CREATE INDEX IF NOT EXISTS idx_tour_unlocks_tour ON tour_unlocks(tour_id);

COMMENT ON TABLE tour_unlocks IS
    'LOCAL-677/D624: one row per (buyer, tour) unlocked by a verified purchase. '
    'UNIQUE(user_id,tour_id) → a replayed transaction never unlocks twice. tour_id '
    'is an ORIGINAL audio_tours.id (a translation shares its source tour''s unlock).';

COMMIT;
