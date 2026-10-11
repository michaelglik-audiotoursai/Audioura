-- 020_tour_listens.sql  (LOCAL-670B)
--
-- Michael (2026-10-10): "Can we not allow rating if people did not listen to at
-- least 2 stops, similar to Audible, where they politely say that the user did
-- not hear enough to rate the tour?"
--
-- A row here records that a given user heard a given stop of a given tour "to
-- the end" (the app writes it when the stop's audio reaches >= 80% or the end).
-- The rating gate (POST /tour/<id>/rating) then requires the user to have >= 2
-- DISTINCT listened stops before a tour rating is accepted — or, for a short
-- tour, ALL of its stops when it has fewer than 2.
--
-- Translation mapping mirrors tour_ratings: a translation row
-- (audio_tours.original_tour_id set) shares its SOURCE tour's listens. The
-- service resolves a translation id to its original before reading/writing, so
-- tour_id here is always an ORIGINAL audio_tours.id.
--
-- Purely additive: no DROP, no DELETE, no change to any existing table. CREATE
-- TABLE IF NOT EXISTS is idempotent, so applying this twice is a no-op and the
-- service's own self-healing CREATE (identical DDL) converges to the same
-- schema whether or not this file was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS tour_listens (
    id          SERIAL PRIMARY KEY,
    tour_id     INTEGER NOT NULL,            -- references audio_tours.id (an ORIGINAL; translations map to their original_tour_id)
    user_id     VARCHAR(255) NOT NULL,       -- references users.secret_id
    stop_index  INTEGER NOT NULL             -- 0-based index of the stop the user finished
                CHECK (stop_index >= 0),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- One row per (tour, user, stop). The POST is idempotent: re-finishing a
    -- stop UPSERTs onto this constraint and never adds a duplicate, so the
    -- distinct-stop count is simply COUNT(*) for the (tour, user) pair.
    CONSTRAINT uq_tour_listens_tour_user_stop UNIQUE (tour_id, user_id, stop_index)
);

-- Fast "how many distinct stops has this user finished on this tour?" — the
-- single read the rating gate performs.
CREATE INDEX IF NOT EXISTS idx_tour_listens_tour_user ON tour_listens(tour_id, user_id);

COMMIT;
