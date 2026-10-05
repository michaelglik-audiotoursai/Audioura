-- LOCAL-582: Add tour_kind column to audio_tours.
--
-- tour_kind labels HOW a tour row was delivered:
--   'full'     — a normal multi-stop tour (the default for every existing row).
--   'overview' — rung 3 of the ladder (D607): the venue resolved and its own
--                site was reachable, but no works/exhibitions could be verified,
--                so the engine delivered ONE sourced orientation stop built from
--                the venue's own pages (museum_overview.py) instead of clean-
--                failing. The row is labelled honestly so the app and analytics
--                can tell an overview apart from a full tour.
--
-- Additive and idempotent: safe to run multiple times, never touches existing
-- data (every current row defaults to 'full'). The orchestrator ALSO self-heals
-- this column at write time (store_audio_tour), so a fresh DB that has not run
-- this migration still gets the column — this file is the explicit, reviewable
-- record of the schema change.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'tour_kind'
    ) THEN
        ALTER TABLE audio_tours ADD COLUMN tour_kind VARCHAR(16) NOT NULL DEFAULT 'full';
    END IF;
END $$;

-- Verification
SELECT 'local582_tour_kind_migration_complete' AS status;
