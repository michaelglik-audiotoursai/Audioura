-- 023_tour_downloads.sql  (LOCAL-677C, D654)
--
-- Pay-before-download grandfathering ledger.
--
-- D654 moves the paywall to BEFORE the download: map_delivery's
-- /download-tour/<id> returns 402 purchase_required for a paid language row the
-- caller has not unlocked. The one exception the ticket requires is
-- GRANDFATHERING: "a user who downloaded this row while it was free keeps
-- access". 677B recorded that only client-side (an is_paid snapshot on the
-- phone), which the server cannot see. This table is the SERVER-SIDE record.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY:
--
--   tour_downloads — one row the FIRST time a (user, tour) pair downloads a
--   tour, carrying whether the row was FREE at that moment (price_tier IS NULL →
--   was_free = TRUE). The 402 gate honours a was_free=TRUE row: a listener who
--   pulled the tour while it was free keeps downloading it after the curator
--   later prices it. A row downloaded while already paid (via a purchase) is
--   recorded was_free=FALSE and grants nothing on its own — the unlock does.
--
--   tour_id is the LANGUAGE ROW's OWN id (the id the client downloads), matching
--   the per-language unlock model of 677B/D653: grandfathering is per language,
--   exactly like the unlock.
--
-- UNIQUE(user_id, tour_id) makes the FIRST free download the one that counts: a
-- later re-download after pricing is an INSERT ... ON CONFLICT DO NOTHING, so it
-- never flips a free grandfather row to paid, and never creates a second row.
--
-- Purely additive: no DROP, no DELETE, no change to any existing column. CREATE
-- TABLE IF NOT EXISTS / the service's own self-healing DDL converge to the same
-- schema whether or not this file was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS tour_downloads (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(255) NOT NULL,          -- the downloader (anonymous device secret_id)
    tour_id     INTEGER      NOT NULL,          -- the LANGUAGE ROW's OWN audio_tours.id
    was_free    BOOLEAN      NOT NULL,          -- TRUE if the row was free (price_tier NULL) at download time
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tour_downloads_user_tour UNIQUE (user_id, tour_id)
);

-- Fast "did this user download this tour while it was free?" (the 402 gate).
CREATE INDEX IF NOT EXISTS idx_tour_downloads_user_tour ON tour_downloads(user_id, tour_id);

COMMENT ON TABLE tour_downloads IS
    'LOCAL-677C/D654: one row per (user, tour) first download, with was_free = '
    'the row was free at that moment. The pay-before-download 402 gate honours a '
    'was_free=TRUE row (grandfathering: downloaded free, keeps access). tour_id '
    'is the LANGUAGE ROW''s own id — grandfathering is per language, like unlock.';

COMMIT;
