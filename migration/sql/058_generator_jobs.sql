-- 058_generator_jobs.sql  (LOCAL-775)
--
-- "Generator job status lives in memory — a second Cloud Run instance answers
-- 'Job not found' and the tour is lost." (D718, GCloud_Storied 2026-10-26 ~19:48Z)
--
-- tour-generator-subscribed briefly ran 2 instances despite maxScale=1 (a
-- revision rollout; Cloud Run can also exceed maxScale for a moment). The
-- orchestrator's status poll landed on the instance that did NOT own the job
-- and got {"error":"Job not found"} 404 (generate_tour_text_service.py
-- /status/<job_id>, ~1328/1386). The owning instance kept generating
-- (~$0.35 metered) and no tour was stored.
--
-- Ruling (D718): generator job status goes to the database; the in-memory dict
-- (ACTIVE_JOBS) stays only as a cache. A job the table knows about is never
-- "Job not found" — any instance can read its real status and, when done, its
-- result. This table is that source of truth for the tour-generator.
--
-- A note on job_status (migration 002/010): that pre-existing table was the
-- all-or-nothing JOB_STORE_MODE='database' design — a service wrote to memory
-- OR to the DB, never both, and it has no instance_id. D718 asks for a
-- cache-with-source-of-truth layering and an owning-instance column, so this
-- adds a PURPOSE-BUILT table for the generator rather than overloading
-- job_status. job_status is left untouched.
--
-- Columns map 1:1 to the fields the tour-generator /status endpoint returns
-- today (generate_tour_text_service.py get_job_status):
--   * status / progress / location / tour_type / total_stops — the live poll
--     fields the orchestrator reads every 10 s.
--   * result  JSONB — everything the orchestrator needs to deliver the tour
--     from ANY instance: output_file, tour_content (the full tour text — the
--     HTTP/Cloud-Run-safe delivery path the orchestrator already prefers),
--     coordinates, tour_kind, i_con_avg, qa_style_warning. Storing tour_content
--     here is what makes the result retrievable off the owning instance (D718
--     point 3); the orchestrator already reads it from the status payload.
--   * error   JSONB — the structured refusal the app needs (LOCAL-580/597/774):
--     error (legacy prefixed string), error_code, error_type, message,
--     suggestion, nearby_tours, plus coordinate_path and evidence_summary.
--   * instance_id — which container owns/last-wrote the job, for diagnosing the
--     exact 2-instance overlap that caused D718.
--   * created_at / updated_at — lifecycle timestamps; created_at is indexed so
--     old rows can age out later (NO cleanup job in this task, per the ruling).
--
-- Purely ADDITIVE: no DROP, no DELETE, no change to any existing column. CREATE
-- TABLE/INDEX IF NOT EXISTS + guarded ALTER ADD COLUMN are idempotent, so
-- applying this twice is a no-op and the service's own self-healing DDL
-- (identical shape) converges whether or not this file was ever run.

BEGIN;

CREATE TABLE IF NOT EXISTS generator_jobs (
    job_id       VARCHAR(64) PRIMARY KEY,                 -- the generator's uuid4 job id
    status       VARCHAR(20) NOT NULL DEFAULT 'queued',   -- queued | processing | completed | error
    progress     TEXT,                                    -- latest human progress string the poll shows
    location     TEXT,                                    -- the requested place (as the user typed it)
    tour_type    VARCHAR(50),                             -- requested tour type (may be '')
    total_stops  INTEGER,                                 -- requested stop count
    result       JSONB NOT NULL DEFAULT '{}'::jsonb,      -- completed-job payload: output_file, tour_content, coordinates, tour_kind, …
    error        JSONB NOT NULL DEFAULT '{}'::jsonb,      -- structured refusal: error, error_code, error_type, message, suggestion, nearby_tours, …
    instance_id  VARCHAR(128),                            -- container/instance that owns/last-wrote this job (D718 diagnostics)
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Guarded ADD COLUMN for a table created by an earlier partial run (idempotent;
-- mirrors the store's own self-healing DDL in job_store.py).
ALTER TABLE generator_jobs ADD COLUMN IF NOT EXISTS result      JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE generator_jobs ADD COLUMN IF NOT EXISTS error       JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE generator_jobs ADD COLUMN IF NOT EXISTS instance_id VARCHAR(128);

-- Age-out index: "which rows are old enough to drop later?" No cleanup job runs
-- in this task — this only makes a future one cheap (D718 point 1).
CREATE INDEX IF NOT EXISTS idx_generator_jobs_created
    ON generator_jobs (created_at);

COMMENT ON TABLE generator_jobs IS
    'LOCAL-775 (D718): source-of-truth for tour-generator async job status. The '
    'in-memory ACTIVE_JOBS dict is now only a cache; a job this table knows is '
    'never "Job not found", so a second Cloud Run instance can answer the '
    'orchestrator poll and, on completion, return the tour (result.tour_content). '
    'result/error are JSONB so the full structured refusal (LOCAL-580/597/774) '
    'and the delivery payload survive across instances. instance_id records the '
    'owning container for diagnosing the 2-instance overlap. Additive; never '
    'DROPs or DELETEs — old rows age out via idx_generator_jobs_created later.';

COMMIT;
