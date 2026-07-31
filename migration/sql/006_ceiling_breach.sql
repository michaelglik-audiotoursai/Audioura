-- Migration 006: Add ceiling_breach column to cost_ledger
-- Part of LOCAL-64 (Enforce $1.30 cost ceiling)
--
-- Flags rows where cost exceeded either the design target ($0.15)
-- or the hard limit ($1.30). Values:
--   NULL             — cost was within target
--   'target_exceeded'   — cost > target but <= hard limit (warning)
--   'hard_limit_exceeded' — cost > hard limit (tour was NOT delivered)

BEGIN;

ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS ceiling_breach VARCHAR(32);

-- Index for monitoring queries (find all breaches quickly)
CREATE INDEX IF NOT EXISTS idx_cost_ledger_breach
ON cost_ledger (ceiling_breach)
WHERE ceiling_breach IS NOT NULL;

COMMIT;
