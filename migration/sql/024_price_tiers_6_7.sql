-- 024: two more tour price tiers — $19.99 (tier 6) and $49.99 (tier 7).
-- Michael, 2026-10-14: "Can we add $20 and $50?" Apple sells only fixed price
-- points, so guides pick from this list; prices use the same .99 pattern.
-- Additive and idempotent: widens the two 1..5 CHECKs to 1..7 and adds 2 rows.
BEGIN;
ALTER TABLE audio_tours DROP CONSTRAINT IF EXISTS chk_audio_tours_price_tier;
ALTER TABLE audio_tours ADD CONSTRAINT chk_audio_tours_price_tier
    CHECK (price_tier IS NULL OR (price_tier >= 1 AND price_tier <= 7));
ALTER TABLE price_tiers DROP CONSTRAINT IF EXISTS price_tiers_tier_check;
ALTER TABLE price_tiers ADD CONSTRAINT price_tiers_tier_check CHECK (tier >= 1 AND tier <= 7);
INSERT INTO price_tiers (tier, product_id, price_usd, label) VALUES
    (6, 'audioura.tour.tier6', 19.99, '$19.99'),
    (7, 'audioura.tour.tier7', 49.99, '$49.99')
ON CONFLICT (tier) DO NOTHING;
COMMIT;
