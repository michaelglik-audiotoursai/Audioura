-- 054_failure_events.sql  (LOCAL-785, D723)
--
-- Michael, 2026-10-26 (D723): "Record all failures so later we can identify
-- what happened. If it's our fault we fix it; if it's the user's mistake we
-- make the interface more intuitive."
--
-- Today a failure vanishes: tour_requests only carries 'failed' with no reason,
-- the generator's logs expire, and an APP failure leaves no trace at all. The
-- cloud downloads of tours 445/446 on 2026-10-26 failed SILENTLY and were only
-- found because GCloud_Storied read the raw container logs by hand. This table
-- is the ONE durable place every server AND app failure is recorded, so the
-- failure_report.py tool (LOCAL-785) can group, count, triage and prioritise
-- them for LEAD.
--
-- WHAT THIS ADDS, PURELY ADDITIVELY:
--
--   failure_events — one row per recorded failure, written by the server
--   recorder (failure_log.record) on every job failure / refusal / clean-fail /
--   5xx, and by the app via POST /client-failure. The `signature` groups
--   like failures (sha1 of service+error_code+exception_type+normalised message,
--   first 16 hex chars) so the report counts "the same failure" across ids,
--   numbers and quoted strings. `triage` is the human/auto classification of
--   WHOSE fault it is (our_bug | ux | external | absence | unknown); the
--   recorder's auto-triage seeds it (triage_source='auto') and LEAD overrides
--   it with failure_report.py --mark (triage_source='lead'). `resolved_by`
--   points at the ticket that fixed it (e.g. 'LOCAL-NNN').
--
-- A 90-day retention job is OUT of scope (D723) — this migration only creates
-- the table. No DROP, no DELETE, no change to any existing table. CREATE TABLE
-- IF NOT EXISTS + CREATE INDEX IF NOT EXISTS make a re-run a no-op; the
-- recorder's own self-healing DDL converges to the same schema whether or not
-- this file was ever run. Applying it adds a table, never a row.

BEGIN;

CREATE TABLE IF NOT EXISTS failure_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    user_id         TEXT,                  -- device secret_id / listener id, when known
    app_version     TEXT,                  -- app build (client failures) or service version
    platform        TEXT,                  -- 'android' | 'ios' | 'server' | ...
    track           TEXT,                  -- 'subscribed' | 'beta' | 'storied' | NULL
    surface         TEXT,                  -- where it happened: 'generate', 'download', 'translate', 'play', 'purchase', ...
    error_code      TEXT,                  -- the LOCAL-774 stable error_code when present
    message         TEXT,                  -- one plain-language line (truncated by the recorder)
    request_text    TEXT,                  -- the user's request / location string, when known
    tour_id         TEXT,                  -- tour id involved, when known
    job_id          TEXT,                  -- orchestrator/generator job id, when known
    exception_type  TEXT,                  -- e.g. 'ValueError', 'TimeoutException'
    frames          TEXT,                  -- top 8 stack frames as text (newline-joined)
    http_status     INTEGER,               -- HTTP status for a wire failure, when known
    service         TEXT,                  -- which service recorded it: 'orchestrator', 'generator', 'app', ...
    signature       CHAR(16)     NOT NULL, -- sha1(service+error_code+exception_type+normalised message)[:16]
    triage          TEXT         NOT NULL DEFAULT 'unknown', -- our_bug | ux | external | absence | unknown
    triage_source   TEXT         NOT NULL DEFAULT 'auto',    -- auto | lead
    resolved_by     TEXT                   -- ticket that fixed it, e.g. 'LOCAL-NNN'
);

-- The report groups by signature over a time window and lists the newest
-- example of each group — index both axes of that query.
CREATE INDEX IF NOT EXISTS idx_failure_events_signature_ts
    ON failure_events (signature, ts DESC);

-- "everything since <when>" (the --since window, and the recency weight).
CREATE INDEX IF NOT EXISTS idx_failure_events_ts
    ON failure_events (ts DESC);

-- Guard the two closed vocabularies the report and --mark rely on. Added
-- separately and guarded so a re-run does not error on an already-present
-- constraint, and so no existing row can violate it (the table is new).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_failure_events_triage'
    ) THEN
        ALTER TABLE failure_events
            ADD CONSTRAINT chk_failure_events_triage
            CHECK (triage IN ('our_bug', 'ux', 'external', 'absence', 'unknown'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_failure_events_triage_source'
    ) THEN
        ALTER TABLE failure_events
            ADD CONSTRAINT chk_failure_events_triage_source
            CHECK (triage_source IN ('auto', 'lead'));
    END IF;
END$$;

COMMENT ON TABLE failure_events IS
    'LOCAL-785/D723: one row per recorded failure (server job failure/refusal/'
    'clean-fail/5xx via failure_log.record, and app failures via POST '
    '/client-failure). signature groups like failures (sha1 of service+'
    'error_code+exception_type+normalised message, [:16]); triage = whose fault '
    '(our_bug|ux|external|absence|unknown), seeded auto and overridden by LEAD '
    'with failure_report.py --mark; resolved_by = the fixing ticket. Read by '
    'failure_report.py. 90-day retention is out of scope.';

COMMIT;

-- Verify:
-- SELECT count(*) FROM failure_events;     -- 0 on a fresh DB
-- \d failure_events                          -- 20 columns + 2 indexes + 2 checks
