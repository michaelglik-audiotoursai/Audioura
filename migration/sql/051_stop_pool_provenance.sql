-- 051_stop_pool_provenance.sql  (LOCAL-766, D713 / D590 / D141 / D690)
--
-- The stop pool (LOCAL-590) stores each reusable stop ONCE per
-- (venue identity, tour_type, cache version) in `stop_pool`, keyed
-- (pool_key, title_norm). A stop row has NO link to the tour(s) it was written
-- for, so an identical request by ANOTHER user is served the same stops — a free
-- rebuild of a PRICED (price_tier > 0) or COMMUNITY (community_id IS NOT NULL)
-- tour. Whole-tour reuse is already creator-scoped (LOCAL-727/D678); the POOL
-- was the remaining bypass (Michael, 2026-10-25 / D713).
--
-- This migration records PROVENANCE: which audio_tours row(s) each pool row
-- served. The delivery rule (stop_pool_sources.filter_protected_titles) then
-- skips a pooled stop at SELECTION time when ANY of its source tours is community
-- or priced, UNLESS the requester is that tour's creator_user_id. Checked at
-- delivery time, so pricing a tour or attaching it to a community LATER protects
-- it from then on — no column on stop_pool needs to change when a tour is priced.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no column retype):
--
--   stop_pool_sources — one row per (pool stop, source audio_tour). A pool stop
--     is (pool_key, title_norm) exactly as in stop_pool; audio_tour_id is the
--     ORIGINAL audio_tours.id (original_tour_id IS NULL) the stop was delivered
--     in. Many-to-many: one pooled stop may have served many tours (so many
--     provenance rows), and one tour contributes many stops. The composite PK
--     (pool_key, title_norm, audio_tour_id) makes re-recording the same link a
--     no-op (idempotent), so both the live-recording path and the backfill can
--     run repeatedly without creating duplicates.
--
-- A pooled stop with NO stop_pool_sources row has UNPROVEN provenance and stays
-- shareable exactly as today — the delivery rule only ever PROTECTS a stop it can
-- prove came from a protected tour; it never withholds a stop it cannot attribute
-- (the ticket's "rows whose source cannot be proven stay shareable").
--
-- FK to audio_tours is added guarded + ON DELETE CASCADE so (a) the migration is
-- safe on a DB where audio_tours somehow does not exist yet (the FK is simply
-- skipped, the table still works), and (b) if a source tour is ever removed by an
-- authorised path (D141 own-is_test rows only; never a purchase-bearing row,
-- D690) its dangling provenance rows go with it rather than protecting a stop by
-- a tour that no longer exists. This migration itself DELETEs nothing.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS and a
-- guarded FK add, wrapped in one transaction. Applying it twice is a no-op; the
-- provenance module's own self-healing DDL (identical) converges to the same
-- schema whether or not this file was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS stop_pool_sources (
    pool_key      TEXT    NOT NULL,            -- stop_pool.pool_key
    title_norm    TEXT    NOT NULL,            -- stop_pool.title_norm
    audio_tour_id INTEGER NOT NULL,            -- ORIGINAL audio_tours.id this stop served
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pool_key, title_norm, audio_tour_id)
);

-- Fast "which tours is this pooled stop's provenance?" (the delivery-rule read,
-- per pooled stop) and "which pooled stops did this tour source?" (bookkeeping).
CREATE INDEX IF NOT EXISTS idx_stop_pool_sources_stop
    ON stop_pool_sources (pool_key, title_norm);
CREATE INDEX IF NOT EXISTS idx_stop_pool_sources_tour
    ON stop_pool_sources (audio_tour_id);

-- FK to audio_tours(id), guarded so the migration is safe before audio_tours
-- exists and is not duplicated on a re-run. ON DELETE CASCADE: a provenance row
-- never outlives its source tour.
DO $$
BEGIN
    IF to_regclass('audio_tours') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_stop_pool_sources_tour'
             AND conrelid = 'stop_pool_sources'::regclass
       ) THEN
        ALTER TABLE stop_pool_sources
            ADD CONSTRAINT fk_stop_pool_sources_tour
            FOREIGN KEY (audio_tour_id) REFERENCES audio_tours(id)
            ON DELETE CASCADE;
    END IF;
END $$;

COMMENT ON TABLE stop_pool_sources IS
    'LOCAL-766/D713: provenance for the stop pool — one row per (pooled stop, '
    'source audio_tour). A pooled stop is skipped at delivery for a non-creator '
    'when ANY source tour is community (community_id NOT NULL) or priced '
    '(price_tier > 0). A pooled stop with no row here is unproven and stays '
    'shareable. Additive; never DELETEs.';

COMMIT;
