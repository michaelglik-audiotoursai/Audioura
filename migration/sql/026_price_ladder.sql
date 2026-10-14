-- 026_price_ladder.sql  (LOCAL-686)
--
-- A fine PRICE LADDER so a guide can pick (almost) any round-dollar price and
-- the app snaps a typed amount to the nearest step. Michael, 2026-10-14: guides
-- pick their own price; Apple/Google sell only pre-created products at fixed
-- prices, so Audioura ships a ladder of products and the guide's typed price
-- snaps to the nearest one ("Typing $37 gives 'Your price: $35'").
--
-- THE LADDER — round dollars, 34 steps, added as tiers 8..41:
--     $2..$20 every $1   (19 steps)  → tiers 8..26
--     $25..$50 every $5  (6 steps)   → tiers 27..32
--     $60..$100 every $10 (5 steps)  → tiers 33..37
--     $125..$200 every $25 (4 steps) → tiers 38..41
-- Product ids are 'audioura.tour.usd<N>' (consumables, e.g. audioura.tour.usd35
-- = $35), labels are the integer dollar amount ("$35").
--
-- IN-PICKER FLAG: migration 022/024's seven .99 tiers (1..7) stay ACTIVE so a
-- tour already priced with one of them keeps its price (tour 557 is tier 3,
-- "$4.99"), but the picker should offer ONLY the ladder. A new column
-- price_tiers.in_picker BOOLEAN DEFAULT TRUE marks which tiers the guide's
-- picker shows; this migration sets it FALSE for the seven legacy tiers and TRUE
-- for the 34 ladder tiers.
--
-- Purely additive and idempotent: it widens the two 1..7 CHECKs to 1..41, adds
-- the in_picker column (default TRUE), re-asserts the 34 ladder rows (ON CONFLICT
-- DO UPDATE), and sets in_picker on the legacy and ladder tiers. Applying it a
-- second time changes nothing. No DROP of data, no DELETE, no row removed; the
-- legacy tiers 1..7 are untouched except their in_picker flag.

BEGIN;

-- ─── 1. Widen the two tier-range CHECKs from 1..7 to 1..41 ───────────────────
ALTER TABLE audio_tours DROP CONSTRAINT IF EXISTS chk_audio_tours_price_tier;
ALTER TABLE audio_tours ADD CONSTRAINT chk_audio_tours_price_tier
    CHECK (price_tier IS NULL OR (price_tier >= 1 AND price_tier <= 41));

ALTER TABLE price_tiers DROP CONSTRAINT IF EXISTS price_tiers_tier_check;
ALTER TABLE price_tiers ADD CONSTRAINT price_tiers_tier_check
    CHECK (tier >= 1 AND tier <= 41);

-- ─── 2. in_picker column: which tiers the guide's price picker offers ────────
-- DEFAULT TRUE so any new tier shows unless explicitly hidden. The legacy .99
-- tiers (1..7) are set FALSE below (kept active for already-priced tours, but
-- off the picker); the 34 ladder tiers are TRUE.
ALTER TABLE price_tiers ADD COLUMN IF NOT EXISTS in_picker BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN price_tiers.in_picker IS
    'LOCAL-686: TRUE if the guide''s price picker offers this tier. The 34 ladder '
    'tiers (8..41) are TRUE; the seven legacy .99 tiers (1..7) are FALSE — still '
    'ACTIVE so tours already priced with them keep their price, but off the picker.';

-- ─── 3. The 34 ladder rows (tiers 8..41) — round dollars, in_picker TRUE ─────
-- ON CONFLICT DO UPDATE re-asserts the canonical product id / price / label /
-- in_picker so re-running restores them; Michael can still change a price with
-- one UPDATE and no redeploy.
INSERT INTO price_tiers (tier, product_id, price_usd, label, in_picker) VALUES
    (8,  'audioura.tour.usd2',   2.00,  '$2',   TRUE),
    (9,  'audioura.tour.usd3',   3.00,  '$3',   TRUE),
    (10, 'audioura.tour.usd4',   4.00,  '$4',   TRUE),
    (11, 'audioura.tour.usd5',   5.00,  '$5',   TRUE),
    (12, 'audioura.tour.usd6',   6.00,  '$6',   TRUE),
    (13, 'audioura.tour.usd7',   7.00,  '$7',   TRUE),
    (14, 'audioura.tour.usd8',   8.00,  '$8',   TRUE),
    (15, 'audioura.tour.usd9',   9.00,  '$9',   TRUE),
    (16, 'audioura.tour.usd10',  10.00, '$10',  TRUE),
    (17, 'audioura.tour.usd11',  11.00, '$11',  TRUE),
    (18, 'audioura.tour.usd12',  12.00, '$12',  TRUE),
    (19, 'audioura.tour.usd13',  13.00, '$13',  TRUE),
    (20, 'audioura.tour.usd14',  14.00, '$14',  TRUE),
    (21, 'audioura.tour.usd15',  15.00, '$15',  TRUE),
    (22, 'audioura.tour.usd16',  16.00, '$16',  TRUE),
    (23, 'audioura.tour.usd17',  17.00, '$17',  TRUE),
    (24, 'audioura.tour.usd18',  18.00, '$18',  TRUE),
    (25, 'audioura.tour.usd19',  19.00, '$19',  TRUE),
    (26, 'audioura.tour.usd20',  20.00, '$20',  TRUE),
    (27, 'audioura.tour.usd25',  25.00, '$25',  TRUE),
    (28, 'audioura.tour.usd30',  30.00, '$30',  TRUE),
    (29, 'audioura.tour.usd35',  35.00, '$35',  TRUE),
    (30, 'audioura.tour.usd40',  40.00, '$40',  TRUE),
    (31, 'audioura.tour.usd45',  45.00, '$45',  TRUE),
    (32, 'audioura.tour.usd50',  50.00, '$50',  TRUE),
    (33, 'audioura.tour.usd60',  60.00, '$60',  TRUE),
    (34, 'audioura.tour.usd70',  70.00, '$70',  TRUE),
    (35, 'audioura.tour.usd80',  80.00, '$80',  TRUE),
    (36, 'audioura.tour.usd90',  90.00, '$90',  TRUE),
    (37, 'audioura.tour.usd100', 100.00, '$100', TRUE),
    (38, 'audioura.tour.usd125', 125.00, '$125', TRUE),
    (39, 'audioura.tour.usd150', 150.00, '$150', TRUE),
    (40, 'audioura.tour.usd175', 175.00, '$175', TRUE),
    (41, 'audioura.tour.usd200', 200.00, '$200', TRUE)
ON CONFLICT (tier) DO UPDATE SET
    product_id = EXCLUDED.product_id,
    price_usd  = EXCLUDED.price_usd,
    label      = EXCLUDED.label,
    in_picker  = EXCLUDED.in_picker,
    active     = TRUE;

-- ─── 4. Hide the seven legacy .99 tiers from the picker (keep them active) ───
-- Tours already priced with tiers 1..7 keep their price; they just no longer
-- appear in the guide's picker (the ladder is the only thing offered).
UPDATE price_tiers SET in_picker = FALSE WHERE tier BETWEEN 1 AND 7;

COMMIT;
