-- 021_sync_offline_outbox.sql  (LOCAL-670C)
--
-- Michael (2026-10-10): tours play fully offline, so the app records "listened",
-- ratings, reviews and per-stop thumbs LOCALLY and ships them in one batch when a
-- connection returns:  POST /sync { user_id, items:[…] }, idempotent on a
-- client-generated UUID.
--
-- Two additive tables back that endpoint:
--
--   * sync_items  — one row per processed client UUID. The batch is idempotent
--     on it: a retried item (dropped connection after the server committed) is a
--     no-op that reports "duplicate". This is what makes per-stop THUMBS
--     idempotent too, since user_stop_feedback has no natural unique key.
--
--   * tour_review_sync — the raw text-review store for reviews arriving through
--     the offline outbox (LOCAL-672 lands the curated review UI later; the
--     outbox can already carry a review today and "nothing is lost" is the
--     rule). DELIBERATELY a distinct table from any existing `tour_reviews` so
--     this never collides with another feature's schema. One review per (tour,
--     user); a later review replaces the earlier one, like tour_ratings.
--     tour_id is always an ORIGINAL audio_tours.id (translations map to their
--     source before writing).
--
-- Purely additive: no DROP, no DELETE, no change to any existing table. CREATE
-- TABLE IF NOT EXISTS is idempotent, and tour_rating_service's own self-healing
-- CREATE (identical DDL) converges to the same schema whether or not this file
-- was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS sync_items (
    client_uuid  VARCHAR(64) PRIMARY KEY,     -- the client-generated UUID of the outbox item
    user_id      VARCHAR(255) NOT NULL,       -- references users.secret_id
    item_type    VARCHAR(32) NOT NULL,        -- listened | rating | thumb | review
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tour_review_sync (
    id         SERIAL PRIMARY KEY,
    tour_id    INTEGER NOT NULL,              -- references audio_tours.id (an ORIGINAL)
    user_id    VARCHAR(255) NOT NULL,         -- references users.secret_id
    review     TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tour_review_sync_tour_user UNIQUE (tour_id, user_id)
);

COMMIT;
