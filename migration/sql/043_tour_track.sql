-- 043: a tour belongs to its creator AND its track (LOCAL-727 / bug 432,
-- ClickUp wdvrdaz108). Additive, idempotent.
--
-- Problem (432): on the shared GCloud DB a Beta tour and a Storied/Preview tour
-- with byte-identical names, the SAME (non-NULL) creator, generated ~1 s apart,
-- COLLAPSED into ONE audio_tours row with mixed columns. The orchestrator's
-- existing-tour lookup (D678 / migration 041) was scoped by
-- (lower(tour_name), creator_user_id) but NOT by `track`, so the second track's
-- store matched the first track's row and REPLACED it — the first track's tour
-- vanished while the job reported success.
--
-- `track` is per-DEPLOYMENT, not per-request: Beta and Storied are separate
-- Cloud Run services (TRACK_B_STORIED_VS_BETA.md) that each always write their
-- own value into the SAME database. So the lookup key must include it.
--
-- Ruling (LOCAL-727):
--   1. The existing-tour lookup key becomes
--      (lower(tour_name), creator_user_id, track) WHERE original_tour_id IS NULL.
--      A different track always falls through to INSERT and gets its own row.
--   2. Same creator + same name + SAME track still versions the one row
--      (legitimate regeneration), unchanged from D678.
--   3. The `track` column already exists (migration 007 / self-healed by the
--      orchestrator, VARCHAR(16) NOT NULL DEFAULT 'beta'); no backfill needed —
--      existing rows are 'beta', which is correct for pre-Storied data.
--   4. LEAD applies this after the code is merged; this agent tests it only on
--      its own throwaway DB schema. The orchestrator self-heals the column, so
--      the code is correct even before this index exists; the index only makes
--      the track-scoped lookup fast.
--
-- Reversible: the DROP below is undone by re-creating the old index — the exact
-- statement is in the comment beside the DROP. The 041 creator-only index may
-- be left in place (harmless) or dropped once this one is in use.

-- 0. Safety: ensure the track column exists (matches the orchestrator's
--    self-heal). Additive, idempotent; existing rows default to 'beta'.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) NOT NULL DEFAULT 'beta';

-- 1. New non-unique index for the per-creator, per-name, PER-TRACK lookup on
--    originals. Non-unique on purpose: a creator may hold the same name on both
--    tracks (two rows), and a same-track re-generation finds its one row to
--    version it.
CREATE INDEX IF NOT EXISTS idx_audio_tours_name_creator_track
    ON audio_tours (lower(tour_name), creator_user_id, track)
    WHERE original_tour_id IS NULL;

-- 2. Drop the superseded creator-only index from 041 (the new index above
--    covers the same lookups with the track column appended).
--    To RESTORE it (reverse this migration), run exactly:
--      CREATE INDEX IF NOT EXISTS idx_audio_tours_name_creator
--          ON audio_tours (lower(tour_name), creator_user_id)
--          WHERE original_tour_id IS NULL;
DROP INDEX IF EXISTS idx_audio_tours_name_creator;
