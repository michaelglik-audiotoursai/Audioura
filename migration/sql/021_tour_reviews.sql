-- 021_tour_reviews.sql  (LOCAL-672, D649)
--
-- "Reviews #4 — indicate the opinions of paid listeners" (Michael, 2026-10-10).
-- Builds on LOCAL-670's tour_ratings (1..10, the 7.5 prior, the median after 3,
-- D647). This migration adds, PURELY ADDITIVELY:
--
--   1. tour_ratings.verified BOOLEAN — a rating is "verified" when the rater has
--      a store-verified purchase that unlocked THIS tour (D624 fallback: a level
--      purchase active while the user generated/downloaded the tour). On a PAID
--      tour only verified ratings count toward the shown score; on a FREE tour
--      all download-gated ratings count (LOCAL-670 rule) with verified ones
--      marked. The flag is computed and written by tour_rating_service at rating
--      time, and un-set when the purchase is later refunded/revoked.
--
--   2. tour_reviews — an optional short text review (<= 500 chars) attached to a
--      rating, with a moderation status (pending | approved | rejected) and the
--      auto-check reason. One review per (tour, user) — a re-review UPSERTs. The
--      tour's creator may add ONE reply (<= 300 chars) through the same
--      auto-check; the reply and its status live on the same row.
--
--   3. review_helpful_votes — one "helpful" vote per (user, review); the shown
--      count is COUNT(*). A user cannot vote on their own review (enforced in
--      the service, which knows the review's author).
--
-- Translation mapping mirrors tour_ratings/tour_listens: a translation row
-- (audio_tours.original_tour_id set) shares its SOURCE tour's reviews. The
-- service resolves a translation id to its original before reading/writing, so
-- tour_id here is always an ORIGINAL audio_tours.id.
--
-- Purely additive: no DROP, no DELETE, no change to any existing column's type
-- or default. ADD COLUMN IF NOT EXISTS and CREATE TABLE IF NOT EXISTS are
-- idempotent, so applying this twice is a no-op; the service's own self-healing
-- DDL (identical) converges to the same schema whether or not this file was run.

BEGIN;

-- ─── 1. Verified flag on each rating (additive) ──────────────────────────────
-- NULL-safe default FALSE on every existing row: pre-672 ratings read as
-- unverified until the next rating write recomputes the flag. A free tour counts
-- them regardless; a paid tour simply does not count them until re-verified,
-- which is the safe direction (never over-counts a paid score).
ALTER TABLE tour_ratings
    ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tour_ratings.verified IS
    'LOCAL-672/D649: TRUE when the rater had a store-verified purchase unlocking '
    'this tour at rating time (D624 fallback: a level purchase active while they '
    'generated/downloaded it). Set by tour_rating_service; un-set on refund/revoke. '
    'On a PAID tour only verified ratings count toward the shown score; on a FREE '
    'tour all download-gated ratings count, verified ones marked "Verified listener".';

-- Fast "verified ratings for this tour" aggregation (paid-tour score + the
-- distribution's verified-only band counts).
CREATE INDEX IF NOT EXISTS idx_tour_ratings_tour_verified
    ON tour_ratings(tour_id, verified);


-- ─── 2. Text reviews (optional, moderated) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS tour_reviews (
    id              SERIAL PRIMARY KEY,
    tour_id         INTEGER NOT NULL,            -- references audio_tours.id (an ORIGINAL; translations map to their original_tour_id)
    user_id         VARCHAR(255) NOT NULL,       -- references users.secret_id; the review's author
    review_text     TEXT NOT NULL                -- the listener's words, <= 500 chars (enforced in the service + here)
                    CHECK (char_length(review_text) <= 500),
    review_status   VARCHAR(16) NOT NULL DEFAULT 'pending'   -- pending | approved | rejected
                    CHECK (review_status IN ('pending', 'approved', 'rejected')),
    status_reason   TEXT,                        -- why the auto-check held/rejected it (profanity | url | contact | ''), for the LEAD queue
    reply_text      TEXT                         -- the curator's single reply, <= 300 chars (NULL until a reply exists)
                    CHECK (reply_text IS NULL OR char_length(reply_text) <= 300),
    reply_status    VARCHAR(16)                  -- moderation status of the reply (same values); NULL until a reply exists
                    CHECK (reply_status IS NULL OR reply_status IN ('pending', 'approved', 'rejected')),
    reply_reason    TEXT,                        -- auto-check reason for the reply
    reply_user_id   VARCHAR(255),                -- the curator (tour creator) who replied; NULL until a reply exists
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reply_at        TIMESTAMP,                   -- when the reply was written
    -- One review per (tour, user). A re-review is an UPSERT onto this constraint
    -- (replaces the text, re-runs the auto-check), so there is never a duplicate.
    CONSTRAINT uq_tour_reviews_tour_user UNIQUE (tour_id, user_id)
);

-- The read path: approved reviews for a tour, newest first (verified ordering is
-- applied in the service, which joins the rating's verified flag).
CREATE INDEX IF NOT EXISTS idx_tour_reviews_tour_status
    ON tour_reviews(tour_id, review_status);
-- The LEAD moderation queue: everything still pending, oldest first.
CREATE INDEX IF NOT EXISTS idx_tour_reviews_status
    ON tour_reviews(review_status);


-- ─── 3. "Helpful" votes on reviews ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_helpful_votes (
    id          SERIAL PRIMARY KEY,
    review_id   INTEGER NOT NULL REFERENCES tour_reviews(id) ON DELETE CASCADE,
    user_id     VARCHAR(255) NOT NULL,           -- references users.secret_id; the voter
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- One vote per (user, review). Re-voting is idempotent (UPSERT DO NOTHING).
    -- A user cannot vote on their OWN review — enforced in the service, which
    -- knows the review's author; the DB keeps the uniqueness guarantee only.
    CONSTRAINT uq_review_helpful_votes_review_user UNIQUE (review_id, user_id)
);

-- Fast "how many helpful votes does this review have?" — the count shown and the
-- "Top" review sort key.
CREATE INDEX IF NOT EXISTS idx_review_helpful_votes_review
    ON review_helpful_votes(review_id);

COMMIT;
