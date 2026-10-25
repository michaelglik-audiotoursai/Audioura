-- 043s (storied, LOCAL-765 + LEAD D714, 2026-10-25): Beta/Storied names stay unique;
-- Subscribed rows are outside that rule.
--
-- Cloud SQL has uq_audio_tours_original_name = UNIQUE (lower(tour_name)) WHERE
-- original_tour_id IS NULL — global, no track. Subscribed (D708) shares the DB and
-- may legitimately hold a tour with the same name as a Beta/Storied tour (and
-- per-creator duplicates of its own, D678). Storied's store lookup reuses any
-- non-Subscribed original by name (D714), so Beta/Storied keep exactly one row per
-- name and the race protection of a UNIQUE index — now scoped to non-Subscribed rows.
--
-- Order matters: create the narrower unique index FIRST (the current data already
-- satisfies it — it is a subset of the old index's rows), then drop the old one.
-- Idempotent. Additive in effect for Beta/Storied (same uniqueness), relaxing only
-- for track='subscribed'.
--
-- ROLLBACK (only if no Subscribed same-name rows exist yet):
--   CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tours_original_name
--       ON audio_tours (lower(tour_name)) WHERE original_tour_id IS NULL;
--   DROP INDEX IF EXISTS uq_audio_tours_original_name_nonsub;

ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) NOT NULL DEFAULT 'beta';

CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tours_original_name_nonsub
    ON audio_tours (lower(tour_name))
    WHERE original_tour_id IS NULL AND (track IS NULL OR track <> 'subscribed');

DROP INDEX IF EXISTS uq_audio_tours_original_name;

CREATE INDEX IF NOT EXISTS idx_audio_tours_name_track
    ON audio_tours (lower(tour_name), track)
    WHERE original_tour_id IS NULL;
