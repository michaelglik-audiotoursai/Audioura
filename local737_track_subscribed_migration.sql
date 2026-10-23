-- 048 / LOCAL-737: relabel the Mac Mini's LOCAL rows from 'storied' to
-- 'subscribed'.
--
-- ============================================================================
-- LOCAL DATABASE ONLY — DECLARED, NOT APPLIED BY THE AGENT.
-- ============================================================================
-- This file is NOT in migration/sql/ and MUST NEVER be copied there or run
-- through migration/apply_to_cloud.sh. It is a one-off DATA fix for the Mac
-- Mini's local Postgres only. LEAD applies it after the LOCAL-737 code merges.
-- On GCloud, Subscribed gets its own fresh rows (track='subscribed') from day
-- one, so there is nothing to relabel there — see SUBMISSION_LOCAL-737.md for
-- the GCloud migration list.
--
-- WHY
--   Until LOCAL-737, the Mac Mini ran the Subscribed code against the local DB
--   while the only non-beta track value the code accepted was 'storied'. Every
--   tour the Subscribed app generated locally was therefore written as
--   track='storied'. Now that 'subscribed' is a first-class track (D708), those
--   rows must carry their true track so the Subscribed app lists/looks them up
--   under track='subscribed' and the (name, creator, track) key (migration 043)
--   keeps Subscribed and Beta apart.
--
-- SCOPE / SAFETY
--   * UPDATE only — no DELETE, no schema change. The 'track' column already
--     exists (migration 007/043, self-healed by the orchestrator).
--   * Touches ONLY rows currently track='storied'. Beta rows (track='beta' or
--     NULL) are untouched, so Beta behaviour is unchanged.
--   * No purchase-bearing rows are removed (D690) — this only relabels a column.
--   * Wrapped in a transaction with an explicit before/after row-count check so
--     the operator sees exactly how many rows changed and can ROLLBACK if the
--     numbers look wrong.
--   * There is NO local Beta/Storied split on this machine: the Mac Mini only
--     ever ran the Subscribed code, so every 'storied' row here is a Subscribed
--     tour. If that assumption is ever false, inspect the pre-count output
--     before COMMIT.
--
-- REVERSIBLE
--   Reverse with the mirror statement:
--     UPDATE audio_tours SET track='storied' WHERE track='subscribed';
--
-- HOW LEAD APPLIES IT (local only), e.g.:
--   docker exec -i <local_postgres> psql -U admin -d audiotours \
--       < local737_track_subscribed_migration.sql
-- Review the NOTICE row counts; COMMIT happens automatically only if the
-- UPDATE succeeds. To abort, run inside a manual transaction and ROLLBACK.
-- ============================================================================

BEGIN;

-- 0. Safety: ensure the track column exists (matches orchestrator self-heal).
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) NOT NULL DEFAULT 'beta';

-- 1. BEFORE counts — recorded so the operator can compare with the AFTER block.
DO $$
DECLARE
    n_storied   BIGINT;
    n_subscribed BIGINT;
    n_beta      BIGINT;
BEGIN
    SELECT count(*) INTO n_storied    FROM audio_tours WHERE track = 'storied';
    SELECT count(*) INTO n_subscribed FROM audio_tours WHERE track = 'subscribed';
    SELECT count(*) INTO n_beta       FROM audio_tours WHERE track = 'beta' OR track IS NULL;
    RAISE NOTICE 'LOCAL-737 BEFORE: storied=%  subscribed=%  beta/null=%',
                 n_storied, n_subscribed, n_beta;
END $$;

-- 2. The relabel. Count of affected rows is reported by psql as "UPDATE <n>".
UPDATE audio_tours SET track = 'subscribed' WHERE track = 'storied';

-- 3. AFTER counts — storied should now be 0; subscribed should have grown by
--    exactly the number of rows that were storied before; beta/null unchanged.
DO $$
DECLARE
    n_storied   BIGINT;
    n_subscribed BIGINT;
    n_beta      BIGINT;
BEGIN
    SELECT count(*) INTO n_storied    FROM audio_tours WHERE track = 'storied';
    SELECT count(*) INTO n_subscribed FROM audio_tours WHERE track = 'subscribed';
    SELECT count(*) INTO n_beta       FROM audio_tours WHERE track = 'beta' OR track IS NULL;
    RAISE NOTICE 'LOCAL-737 AFTER:  storied=%  subscribed=%  beta/null=%',
                 n_storied, n_subscribed, n_beta;
    IF n_storied <> 0 THEN
        RAISE EXCEPTION 'LOCAL-737: % storied rows remain after relabel — aborting', n_storied;
    END IF;
END $$;

-- Verification sentinel row (matches the local582 convention).
SELECT 'local737_track_subscribed_migration_complete' AS status;

COMMIT;
