-- ============================================================================
-- 009_referral_abuse_controls.sql — LOCAL-115: Referral abuse prevention
-- ============================================================================
-- Adds UNIQUE constraint on (referral_code, new_user_id) to prevent duplicate
-- redemptions. Safe to apply: LEAD verified 0 duplicates exist in current data.
--
-- Precondition check (run before applying):
--   SELECT referral_code, new_user_id, COUNT(*)
--   FROM referral_redemptions
--   GROUP BY referral_code, new_user_id
--   HAVING COUNT(*) > 1;
--   → Must return 0 rows
-- ============================================================================

-- Add UNIQUE constraint to prevent same user redeeming same code twice
ALTER TABLE referral_redemptions
    ADD CONSTRAINT uq_referral_redemptions_code_user
    UNIQUE (referral_code, new_user_id);
