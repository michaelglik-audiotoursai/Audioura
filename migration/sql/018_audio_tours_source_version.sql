-- 018_audio_tours_source_version.sql  (LOCAL-666)
--
-- A translation row (original_tour_id set, e.g. Russian 615 of tour 557) is
-- never replaced in place. LOCAL-606 makes a FRESH row whenever its source
-- changes, so the translation always has NO audio_tour_versions archive rows of
-- its own and LOCAL-657 computes it as "v1" (no label). The listener expects the
-- Russian copy of v10 to say v10.
--
-- source_version records, at translation time, the SOURCE tour's current version
-- (COALESCE(MAX(version_no),0)+1 over audio_tour_versions for original_tour_id).
-- map-delivery then reports a translation row's version from source_version, so a
-- translation of v10 shows v10 while still carrying its own created_at as the
-- "updated" date.
--
-- This file is the explicit, auditable form of the SAME column the translation
-- service adds self-healingly at runtime (additive, idempotent). Applying this
-- migration and running the code produce identical schema; running the code
-- without this migration still works. No DROP, no DELETE — purely additive.

BEGIN;

-- NULL on every existing row (originals and pre-666 translations alike). A NULL
-- source_version makes map-delivery fall back to the live source version (or the
-- row's own version for an original), so old data is never wrong — it just lacks
-- the pinned snapshot until the next translation.
ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS source_version INTEGER;

COMMENT ON COLUMN audio_tours.source_version IS
    'LOCAL-666: for a translation row (original_tour_id set), the SOURCE tour''s '
    'version at translation time (COALESCE(MAX(version_no),0)+1 over '
    'audio_tour_versions for original_tour_id). NULL on originals and on '
    'pre-666 translations; map-delivery falls back to the source''s live version '
    'then. Lets a translation of v10 display v10 instead of v1.';

COMMIT;
