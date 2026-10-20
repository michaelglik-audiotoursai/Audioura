-- LOCAL-723: Scope the daily paid-API limit to LISTENER spend only.
-- Additive migration only: one new nullable column on an existing table.
-- Run: psql -f migrations/local723_add_role_column.sql
--
-- Why: DAILY_PAID_LIMIT_USD (LOCAL-673) summed paid_api_calls by `service`, and
-- test/bench containers run the SAME services as the listener-facing stack, so a
-- night of test spend tripped the listeners' $8 limit although listeners spent $0
-- (LEAD, 2026-10-20 17:54). The meter now stamps `role = 'listener'` on rows from
-- the real listener stack (proven, not just env-labelled), and the limit query
-- sums ONLY role = 'listener'.
--
-- FAIL SAFE FOR LISTENERS: a row with NULL / non-'listener' role is NOT counted
-- toward the listeners' limit. Old rows written before this column existed are
-- NULL, so historical test spend can never trip the limit either. A test
-- container therefore cannot be counted even if the meter mislabels it.

ALTER TABLE paid_api_calls ADD COLUMN IF NOT EXISTS role text;

-- Partial index: the limit query filters status = 200 AND role = 'listener' for a
-- single NY day. A partial index on the listener rows keeps that per-minute query
-- cheap without indexing the (far larger) body of test/NULL rows.
CREATE INDEX IF NOT EXISTS idx_paid_api_calls_listener
    ON paid_api_calls (ts)
    WHERE status = 200 AND role = 'listener';
