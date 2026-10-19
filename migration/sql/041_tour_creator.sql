-- 041: a tour belongs to its creator (LOCAL-718 / D678). Additive, idempotent.
--
-- Problem (D678): the orchestrator's save path found an "existing tour" by name
-- alone (lower(tour_name) WHERE original_tour_id IS NULL) and REPLACED it as a
-- new version. The UNIQUE index uq_audio_tours_original_name enforced that
-- global, cross-user namespace. So a SECOND person generating the same name
-- overwrote the FIRST creator's tour — a paid tour included.
--
-- Ruling (D678):
--   1. Record the creator at INSERT (new column, no backfill — existing rows
--      stay NULL = "unknown creator").
--   2. Same creator + same name (case-insensitive) → a new version of THAT tour.
--   3. A different creator, or a NULL-creator existing row → a NEW, separate
--      tour (new id, own share code). Nothing is replaced across creators.
--   4. The unique index becomes a NON-unique index on
--      (lower(tour_name), creator_user_id). LEAD applies this after the code is
--      merged; this agent tests it only on its own DB copy.
--
-- Reversible: the DROP below is undone by re-creating the unique index — the
-- exact statement is in the comment beside the DROP.

-- 1. Record the creator. No backfill: existing rows keep NULL.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS creator_user_id TEXT;

-- 2. New non-unique index for the per-creator, per-name lookup on originals.
--    Non-unique on purpose: two creators MAY hold the same name (two rows), and
--    a creator's own re-generation finds their one row to version it.
CREATE INDEX IF NOT EXISTS idx_audio_tours_name_creator
    ON audio_tours (lower(tour_name), creator_user_id)
    WHERE original_tour_id IS NULL;

-- 3. Drop the old global-namespace unique index. Replaced by rule 4 above.
--    To RESTORE it (reverse this migration), run exactly:
--      CREATE UNIQUE INDEX IF NOT EXISTS uq_audio_tours_original_name
--          ON audio_tours (lower(tour_name)) WHERE original_tour_id IS NULL;
DROP INDEX IF EXISTS uq_audio_tours_original_name;
