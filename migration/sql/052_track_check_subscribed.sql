-- 052: allow track = 'subscribed' in audio_tours (D712, wdvrdaz5vr).
-- Cloud SQL carries audio_tours_track_check = CHECK (track IN ('beta','storied')),
-- added outside the migration files during Track B. It rejects every Subscribed
-- tour at store time. No earlier migration widened it.
-- Idempotent; same NULL semantics as before (a CHECK passes on NULL).
-- Databases without the old constraint (the Mac) get the new one; all existing
-- values there are beta/storied/subscribed/NULL (verify query below).
BEGIN;
ALTER TABLE audio_tours DROP CONSTRAINT IF EXISTS audio_tours_track_check;
ALTER TABLE audio_tours ADD CONSTRAINT audio_tours_track_check
    CHECK (track IN ('beta', 'storied', 'subscribed'));
COMMIT;

-- Verify:
-- SELECT pg_get_constraintdef(oid) FROM pg_constraint
--  WHERE conrelid = 'audio_tours'::regclass AND conname = 'audio_tours_track_check';
--   -> CHECK (((track)::text = ANY (... 'beta' ... 'storied' ... 'subscribed' ...)))
-- SELECT track, count(*) FROM audio_tours GROUP BY 1;   -- row count unchanged
