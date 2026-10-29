-- 059_stop_pool_fresh_until.sql — LOCAL-806 P6 research library.
--
-- Additive ONLY. Adds the research-library freshness date to stop_pool.
--
-- WHY. The P6 pilot pre-researches the most-requested destinations cheaply
-- (research ≈ $0.001/query on Serper) and keeps the result, so a customer's
-- request there is BUILT from stored research instead of researched from
-- scratch. Each pre-researched stop carries a `fresh_until` date; the reuse
-- reader (stop_pool_store.get_pool_stops) serves a row only while that date is
-- in the future, and the refresh job (research_library_refresh.py) re-researches
-- a row as it nears expiry — so a stale row is REFRESHED, never served.
--
-- Freshness windows (set by the builder, not here): museums/landmarks 90 days,
-- businesses (restaurants/places) 30 days.
--
-- An ordinary delivered-tour stop has fresh_until = NULL and is NEVER aged out
-- by this column — behaviour is byte-for-byte unchanged for every existing row
-- and every ordinary delivery. Orthogonal to news_generated_at (LOCAL-655, a
-- 7-day clock for dated news items): a stop may carry either, both or neither.
--
-- Mirrors the self-healing ADD COLUMN IF NOT EXISTS block in
-- stop_pool_store._ensure_table so a dev DB and a migrated DB agree. Idempotent.
-- Never DELETE/DROP.

ALTER TABLE public.stop_pool
    ADD COLUMN IF NOT EXISTS fresh_until timestamp with time zone;

COMMENT ON COLUMN public.stop_pool.fresh_until IS
    'LOCAL-806: research-library freshness date. A pre-researched (P6 pilot) stop '
    'is served from the pool only while fresh_until is in the future; past that it '
    'is ignored by get_pool_stops and re-researched by research_library_refresh.py. '
    'NULL for an ordinary delivered-tour stop (never aged out by this column). '
    'Museums/landmarks 90 days, businesses 30 days.';

-- Partial index: only library rows (fresh_until NOT NULL) are indexed, so the
-- refresh scan and the reader's freshness filter are cheap and ordinary pooled
-- stops add nothing to the index.
CREATE INDEX IF NOT EXISTS idx_stop_pool_fresh_until
    ON public.stop_pool (fresh_until) WHERE fresh_until IS NOT NULL;
