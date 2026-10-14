-- 027: a content rating for every tour, like a movie rating (LOCAL-687 / D656).
-- Additive, idempotent. Decided by a model (tour_content_rating.py), NOT a
-- bad-word list — word lists flag "class", "Assisi", "Scunthorpe".
--
--   content_rating        general | mature | not_allowed. NULL = NOT RATED YET,
--                         which the listing layer treats as `general` so old
--                         tours keep working until they are scored.
--     general      — listed for everyone.
--     mature       — strong language, alcohol-focused, crime, gambling,
--                    nightlife, casinos. Listed ONLY to confirmed-18+ listeners
--                    (the request carries adult=1).
--     not_allowed  — sexual services / adult entertainment, explicit sex, hate,
--                    encouraging illegal acts. NEVER listed.
--   content_rating_reason the model's one-line justification for the rating.
--   review_status         pending | approved | rejected. NULL = no review
--                         needed (a `general` rating lists immediately).
--                         Anything not clearly general is set to 'pending' by
--                         the rater and waits for human review before it lists.
--   content_rated_at      when the rating was written. Written by
--                         tour_content_rating.py; cleared/overwritten on rescore.
--
-- Translations are NOT rated on their own: they inherit the ORIGINAL's rating
-- (read through original_tour_id), exactly as editor_score / ratings do.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS content_rating VARCHAR(16)
    CHECK (content_rating IS NULL
           OR content_rating IN ('general', 'mature', 'not_allowed'));
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS content_rating_reason TEXT;
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS review_status VARCHAR(16)
    CHECK (review_status IS NULL
           OR review_status IN ('pending', 'approved', 'rejected'));
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS content_rated_at TIMESTAMPTZ;

-- The listing layer filters on content_rating + review_status on every request
-- (hide not_allowed, hide pending/rejected, hide mature unless adult=1). A
-- partial index keeps that cheap and leaves the common NULL/general rows out.
CREATE INDEX IF NOT EXISTS idx_audio_tours_content_rating
    ON audio_tours (content_rating, review_status)
    WHERE content_rating IS NOT NULL;
