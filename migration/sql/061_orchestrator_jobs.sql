-- 061_orchestrator_jobs.sql  (LOCAL-821)
--
-- "Cloud Run sent SIGTERM to the orchestrator while it was polling a Met museum
-- tour. The generator FINISHED (5 real works, already persisted in
-- generator_jobs, LOCAL-775) but the orchestrator was gone: no audio_tours row,
-- tour_requests 279 stuck at 'started'." (GCloud_Storied wave-4, 2026-10-30)
--
-- The orchestrator's delivery runs in a daemon thread (orchestrate_tour_async).
-- Everything it needs to finish the tour — the generator's text job id and the
-- original request parameters — lived ONLY in the in-memory ACTIVE_JOBS dict, so
-- SIGTERM (Cloud Run's 10s-then-SIGKILL shutdown; the handler waits at most
-- 240s) killed the thread with the process and there was no durable record a
-- fresh instance could pick the job up from. Any tour longer than ~15 min dies
-- this way.
--
-- This table is that durable record. One row per orchestrator job, written at
-- /generate BEFORE generation starts and updated as the pipeline advances:
--   * generator_job_id — the tour-generator's text job id (job_id_1). With it a
--     resumed orchestration SKIPS the /generate call and re-polls the EXISTING
--     generator job via generator_jobs (LOCAL-775): a completed job still
--     returns its tour_content, so delivery reuses the normal poll path and no
--     text is re-generated (no new spend).
--   * params JSONB — the full orchestrate_tour_async argument set (location,
--     tour_type, total_stops, user_id, request_string, language, persona, stops,
--     mode, is_test, community_id, community_visibility). A fresh instance
--     reconstructs the exact call from this.
--   * status — queued | processing | completed | error. Non-terminal rows are
--     what the resume/sweep looks for.
--   * lease_owner / lease_expires_at — a time-boxed lease so two instances
--     (sweep + a resume-on-boot, or two instances both sweeping) never finish
--     the same job twice. An instance may only pick up a job whose lease is NULL
--     or expired; it then owns the job until it finishes or the lease lapses.
--
-- The orchestrator has matching self-healing DDL (orchestrator_jobs.py
-- _ensure_table), so the store converges whether or not this file was applied —
-- the same additive pattern as generator_jobs / audio_tours. Purely ADDITIVE:
-- CREATE ... IF NOT EXISTS + guarded ALTER ADD COLUMN, idempotent, no DROP, no
-- DELETE. Old rows age out via idx_orchestrator_jobs_updated later (no cleanup
-- job in this task).

BEGIN;

CREATE TABLE IF NOT EXISTS orchestrator_jobs (
    job_id            VARCHAR(64) PRIMARY KEY,                 -- the orchestrator's uuid4 job id (= tour_requests.tour_id)
    generator_job_id  VARCHAR(64),                             -- the tour-generator text job id (job_id_1); NULL until /generate returns
    status            VARCHAR(20) NOT NULL DEFAULT 'queued',   -- queued | processing | completed | error
    params            JSONB NOT NULL DEFAULT '{}'::jsonb,      -- full orchestrate_tour_async args to reconstruct the call
    error             TEXT,                                    -- terminal failure reason (status='error')
    lease_owner       VARCHAR(128),                            -- instance id currently finishing the job (NULL = free)
    lease_expires_at  TIMESTAMP,                               -- when the lease lapses and another instance may take over
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Guarded ADD COLUMN for a table created by an earlier partial run (idempotent;
-- mirrors the store's own self-healing DDL in orchestrator_jobs.py).
ALTER TABLE orchestrator_jobs ADD COLUMN IF NOT EXISTS generator_job_id VARCHAR(64);
ALTER TABLE orchestrator_jobs ADD COLUMN IF NOT EXISTS params           JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE orchestrator_jobs ADD COLUMN IF NOT EXISTS error            TEXT;
ALTER TABLE orchestrator_jobs ADD COLUMN IF NOT EXISTS lease_owner      VARCHAR(128);
ALTER TABLE orchestrator_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMP;

-- The resume/sweep scans for non-terminal rows ordered by how stale they are;
-- this index makes "which jobs need picking up?" cheap.
CREATE INDEX IF NOT EXISTS idx_orchestrator_jobs_status_updated
    ON orchestrator_jobs (status, updated_at);

COMMENT ON TABLE orchestrator_jobs IS
    'LOCAL-821: durable record of every orchestrator tour job so a tour whose '
    'generation outlived the instance (Cloud Run SIGTERM) is finished by the '
    'next instance. generator_job_id lets a resume re-poll the EXISTING '
    'generator_jobs result (no re-generation); params reconstructs the '
    'orchestrate_tour_async call; lease_owner/lease_expires_at stop two '
    'instances finishing the same job twice. Additive; never DROPs or DELETEs.';

COMMIT;
