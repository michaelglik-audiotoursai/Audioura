-- 062_audio_tour_versions_zip_bytes.sql — LOCAL-821B.
--
-- Additive ONLY. Adds a nullable `zip_bytes bytea` to audio_tour_versions so a
-- replaced tour's ZIP is reversible even when the ZIP lives in the DB column
-- audio_tours.audio_tour (GCloud), not as a file on disk.
--
-- WHY. D622 (binding, 2026-10-06): "A regenerated tour replaces the stale one of
-- the same name, keeping a reversible version … the old version goes to
-- audio_tour_versions, and the old ZIP is renamed, never deleted." The replace
-- archived the old TEXT (tour_content/zip_filename/stops/lat/lng) and, on a
-- filesystem deployment, RENAMED the old ZIP file to <name>.v<N>.zip. But on
-- GCloud the ZIP is not a file: it is the bytea column audio_tours.audio_tour.
-- There, the replace overwrote those bytes while archiving only the text, so the
-- restore could bring back text and stops but NOT audio — the replace was not
-- reversible (the real, narrow defect behind the 465 event).
--
-- The fix: before overwriting audio_tours.audio_tour, store_audio_tour copies the
-- OLD bytes into audio_tour_versions.zip_bytes in the SAME transaction as the
-- text snapshot, so restore_tour_version.py can bring back text, stops AND audio.
--
-- NULL for: rows archived before this column; and filesystem deployments where
-- the old ZIP is the renamed file on disk (the restore falls back to that file).
-- Behaviour is byte-for-byte unchanged for every existing row. Idempotent.
-- Never DELETE/DROP.
--
-- Mirrors the self-healing ADD COLUMN IF NOT EXISTS block in
-- tour_orchestrator_service._ensure_versioning_objects so a dev DB and a
-- migrated DB agree.

ALTER TABLE public.audio_tour_versions
    ADD COLUMN IF NOT EXISTS zip_bytes bytea;

COMMENT ON COLUMN public.audio_tour_versions.zip_bytes IS
    'LOCAL-821B: the OLD ZIP bytes archived when a tour whose ZIP lives in the DB '
    'column audio_tours.audio_tour is replaced, so the replace is reversible '
    '(restore brings back audio, not just text). NULL when the old ZIP was a '
    'renamed file on disk (filesystem deployment) or the row predates this column.';
