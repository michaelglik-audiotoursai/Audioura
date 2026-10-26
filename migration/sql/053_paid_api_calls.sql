-- 053: create the paid-API meter table on databases that lack it (Cloud SQL).
-- Why (wdvrdaz5yt, 2026-10-25): _meter/paid_api_meter.py writes every paid call
-- to paid_api_calls and DAILY_PAID_LIMIT_USD sums it. The table was created by
-- hand on the Mac (LOCAL-673) and never in a migration, so on Cloud SQL every
-- meter write was swallowed and the daily cap failed OPEN (blocked nothing).
-- Schema copied from the Mac DB (pg_dump -s), incl. LOCAL-723's role column.
-- Idempotent: no-op on the Mac.
BEGIN;
CREATE TABLE IF NOT EXISTS paid_api_calls (
    id      bigserial PRIMARY KEY,
    ts      timestamptz DEFAULT now(),
    kind    text,
    status  integer,
    service text,
    caller  text,
    url     text,
    model   text,
    usd     numeric(12,6),
    detail  jsonb,
    host    text,
    role    text
);
ALTER TABLE paid_api_calls ADD COLUMN IF NOT EXISTS role text;
CREATE INDEX IF NOT EXISTS idx_paid_api_calls_listener
    ON paid_api_calls (ts) WHERE status = 200 AND role = 'listener';
COMMIT;

-- Verify:
-- SELECT count(*) FROM paid_api_calls;            -- 0 on a fresh Cloud SQL
-- \d paid_api_calls                                -- 12 columns + the partial index
