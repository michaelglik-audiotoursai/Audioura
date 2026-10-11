-- 019_tour_ratings.sql  (LOCAL-670)
--
-- A listener rates a TOUR from 1 to 10. One rating per (user, tour); a later
-- rating replaces the earlier one (UPSERT on the UNIQUE constraint). This is
-- the per-TOUR judgement Michael asked for, distinct from the per-STOP thumbs
-- in user_stop_feedback — which this migration does NOT touch.
--
-- Shown score rule (D647, computed in the rating service, not here):
--   0 ratings  → 7.5, labelled "New"
--   1–3        → average of (7.5 + the real ratings)   e.g. 7.5 & 9 → 8.3
--   ≥ 4        → median of the real ratings only (the 7.5 prior is dropped)
--   always shown with the count, e.g. "8.3 · 2 ratings", "7.5 · New"
--
-- A translation shares its SOURCE tour's ratings: the service maps a
-- translation row (audio_tours.original_tour_id set) to its original before
-- reading/writing, so tour_id here is always an ORIGINAL audio_tours.id.
--
-- Purely additive: no DROP, no DELETE, no change to any existing table. CREATE
-- TABLE IF NOT EXISTS is idempotent, so applying this twice is a no-op and the
-- service's own self-healing CREATE (identical DDL) converges to the same
-- schema whether or not this file was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS tour_ratings (
    id          SERIAL PRIMARY KEY,
    tour_id     INTEGER NOT NULL,            -- references audio_tours.id (an ORIGINAL; translations map to their original_tour_id)
    user_id     VARCHAR(255) NOT NULL,       -- references users.secret_id
    rating      SMALLINT NOT NULL            -- whole-number tour rating, 1..10
                CHECK (rating >= 1 AND rating <= 10),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- One rating per (user, tour). A re-rate is an UPSERT onto this constraint,
    -- so the latest rating replaces the earlier one with no duplicate rows.
    CONSTRAINT uq_tour_ratings_tour_user UNIQUE (tour_id, user_id)
);

-- Fast grouped aggregation per tour (count + array for median/average), used by
-- the rating service and map-delivery's one grouped query across many tours.
CREATE INDEX IF NOT EXISTS idx_tour_ratings_tour_id ON tour_ratings(tour_id);
-- Fast lookup of a single user's rating of a tour (the GET and the UPSERT read).
CREATE INDEX IF NOT EXISTS idx_tour_ratings_tour_user ON tour_ratings(tour_id, user_id);

COMMIT;
