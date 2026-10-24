-- 049_organiser_audio_tours.sql  (LOCAL-754B, D658 addendum 2 / D708)
--
-- The organiser builds a REAL tour from their OWN hosted audio (RSS/MP3 links).
-- The audio_tours row is like a generated community tour (community_id,
-- community_visibility, lat/lng, stops_count), PLUS a source marker and the
-- rights acceptance. Three additive, idempotent columns on audio_tours. NO
-- DROP, NO DELETE, NO retype — every existing row reads NULL and behaves
-- exactly as before (the columns are inert for a generated/ordinary tour).
--
--   source_kind         — NULL for a generated/ordinary tour; 'organiser_audio'
--                         for a tour the organiser built from their hosted
--                         audio. The package carries remote_audio.json and NO
--                         MP3 (Audioura never stores the files, D658 addendum
--                         2); the app and the translation gate key off this one
--                         value. Translation of an organiser-audio tour is NOT
--                         offered (D708).
--   rights_accepted_by  — the user_id (the organiser) who ticked "I have the
--                         right to publish this audio to my members" (D754,
--                         required per tour). Stored WHO.
--   rights_accepted_at  — WHEN they accepted (the per-tour rights timestamp).
--
-- The package ZIP still lives in audio_tours.audio_tour (BYTEA) exactly like a
-- generated tour, so the existing download serving (/download/<id>, map-delivery
-- /download-tour/<id> with its membership gate) and the community page tour list
-- (_tours_for) work unchanged — an organiser-audio tour is indistinguishable on
-- Listen. Editing archives the old content to audio_tour_versions (migration
-- 017) for the version bump, the same mechanism a generated edit uses.

BEGIN;

ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS source_kind VARCHAR(32);

ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS rights_accepted_by VARCHAR(128);

ALTER TABLE audio_tours
    ADD COLUMN IF NOT EXISTS rights_accepted_at TIMESTAMP WITHOUT TIME ZONE;

-- A partial index for "the organiser-audio tours" read (small, hot on the
-- community page and the translation gate).
CREATE INDEX IF NOT EXISTS idx_audio_tours_source_kind
    ON audio_tours (source_kind) WHERE source_kind IS NOT NULL;

COMMENT ON COLUMN audio_tours.source_kind IS
    'LOCAL-754B/D658 addendum 2: NULL = generated/ordinary tour; '
    '''organiser_audio'' = built from the organiser''s hosted audio (package has '
    'remote_audio.json, no MP3; translation not offered, D708).';
COMMENT ON COLUMN audio_tours.rights_accepted_by IS
    'LOCAL-754B/D754: the organiser who accepted "I have the right to publish '
    'this audio to my members" for an organiser-audio tour (required per tour).';
COMMENT ON COLUMN audio_tours.rights_accepted_at IS
    'LOCAL-754B/D754: when the organiser accepted the per-tour publish rights.';

COMMIT;
