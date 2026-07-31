-- Migration 005: Cost Ledger table for per-operation cost metering
-- Part of LOCAL-60 (Subscribed #1 — true per-operation cost metering)
-- 
-- Records one row per billable operation so we can answer:
-- "What did that operation cost us?" for every billable path.
--
-- A cache hit records cost=0.00 with cache_hit=TRUE.
-- A fresh generation records the real API spend with cache_hit=FALSE.

BEGIN;

CREATE TABLE IF NOT EXISTS cost_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_type VARCHAR(64) NOT NULL,
    user_id VARCHAR(128),
    our_cost_usd NUMERIC(12, 6) NOT NULL,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    job_id VARCHAR(128),
    breakdown JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookups by user + time range (for billing summaries)
CREATE INDEX IF NOT EXISTS idx_cost_ledger_user_time
ON cost_ledger (user_id, created_at);

-- Fast lookups by job (for per-request audit)
CREATE INDEX IF NOT EXISTS idx_cost_ledger_job
ON cost_ledger (job_id);

-- Fast lookups by operation type (for aggregate cost reports)
CREATE INDEX IF NOT EXISTS idx_cost_ledger_operation_type
ON cost_ledger (operation_type, created_at);

COMMENT ON TABLE cost_ledger IS 'Per-operation cost ledger for Subscribed billing. One row per billable operation.';
COMMENT ON COLUMN cost_ledger.operation_type IS 'Enum-like: tour_generate, tour_cache_hit, translation_generate, translation_cache_hit, news_generate, photo_extension';
COMMENT ON COLUMN cost_ledger.our_cost_usd IS 'True cost to us in USD. Cache hits = 0.00.';
COMMENT ON COLUMN cost_ledger.cache_hit IS 'TRUE when served from cache (cost should be ~0).';
COMMENT ON COLUMN cost_ledger.breakdown IS 'JSON breakdown of cost components: {"llm": ..., "tts": ..., "search": ...}';

COMMIT;
