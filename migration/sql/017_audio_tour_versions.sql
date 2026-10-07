-- 017_audio_tour_versions.sql  (LOCAL-606, D622)
--
-- Replace-on-change for regenerated tours: when a fresh/newly-assembled
-- delivery's text differs from the stored original row, the orchestrator
-- replaces the row's content/ZIP/stops_count (and lat/lng if NULL) and archives
-- the superseded version here first, so every replacement is reversible.
--
-- This file is the explicit, auditable form of the SAME objects that
-- tour_orchestrator_service._ensure_versioning_objects() creates self-healingly
-- at runtime (additive, idempotent). Applying this migration and running the
-- code produce identical schema; running the code without this migration still
-- works. No DROP, no DELETE — purely additive.

BEGIN;

-- A translation row (original_tour_id = some original id) is flipped TRUE when
-- its original's content is replaced, so the next translation request
-- regenerates it. The stale translation is never deleted.
ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS translation_stale BOOLEAN NOT NULL DEFAULT FALSE;

-- Append-only archive of every superseded original-row content. Each
-- replacement inserts the OLD values here first (version_no is per-tour,
-- 1,2,3,…). No FK to audio_tours.id on purpose: the archive must outlive any
-- later change to the tour row, and the restore helper reads it directly.
CREATE TABLE IF NOT EXISTS audio_tour_versions (
    id              SERIAL PRIMARY KEY,
    tour_id         INTEGER NOT NULL,
    version_no      INTEGER NOT NULL,
    tour_content    TEXT,
    zip_filename    VARCHAR(512),
    stops_count     INTEGER,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    replaced_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    replaced_by_job VARCHAR(128),
    CONSTRAINT uq_audio_tour_versions_tour_version UNIQUE (tour_id, version_no)
);

COMMENT ON TABLE audio_tour_versions IS
    'LOCAL-606/D622: append-only archive of superseded audio_tours original-row '
    'content (text, zip, stops, lat/lng) kept before a regenerated tour replaces '
    'it. Reversible via restore_tour_version.py. Never deleted.';

COMMENT ON COLUMN audio_tours.translation_stale IS
    'LOCAL-606/D622: TRUE when this translation''s original was replaced; the '
    'next translation request regenerates it. The row is not deleted.';

COMMIT;
