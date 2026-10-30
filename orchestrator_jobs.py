"""
Orchestrator Jobs store — durable record of every orchestrator tour job.
===========================================================================

[LOCAL-821] Cloud Run sends SIGTERM to the orchestrator while a tour is still
generating. The orchestrator's delivery runs in a daemon thread
(tour_orchestrator_service.orchestrate_tour_async); everything it needs to
finish the tour — the generator's text job id and the original request
parameters — lived ONLY in the in-memory ACTIVE_JOBS dict, so the shutdown
killed the thread with the process and no fresh instance could pick the job up.
The generator result was already safe in generator_jobs (LOCAL-775) but the
tour was still lost: no audio_tours row, tour_requests stuck at 'started'.

This module is the durable record that closes that gap. One row per orchestrator
job (table orchestrator_jobs, migration 061), written at /generate before
generation starts and updated as the pipeline advances:

  * generator_job_id — the tour-generator's text job id (job_id_1). A resumed
    orchestration re-polls this EXISTING generator job instead of calling
    /generate again, so a completed generator job returns its tour_content and
    delivery reuses the normal poll path with no re-generation (no new spend).
  * params — the full orchestrate_tour_async argument set, so a fresh instance
    reconstructs the exact call.
  * status — queued | processing | completed | error. The sweep looks for
    non-terminal rows.
  * lease_owner / lease_expires_at — a time-boxed lease so two instances never
    finish the same job twice.

Every method is best-effort: a DB error is logged and swallowed so a transient
database problem never breaks live generation. When the DB is unreachable the
orchestrator simply behaves as it did before this module existed (the in-memory
path still delivers the tour on the instance that generated it); the durable
resume is the extra safety net, not a new hard dependency.
"""

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Terminal statuses: a job in one of these will not be resumed.
TERMINAL_STATUSES = ('completed', 'error')

# A stable id for the container/instance that owns a lease. Cloud Run exposes
# the revision/instance; fall back to hostname locally. Same convention as
# job_store.INSTANCE_ID.
INSTANCE_ID = (
    os.getenv('INSTANCE_ID')
    or os.getenv('K_REVISION')
    or os.getenv('HOSTNAME')
    or 'unknown'
)

# How long a lease is held before another instance may take the job. The finish
# path renews nothing fancy; the lease just has to outlast a normal delivery
# (download + modernized + store). Overridable for tests / tuning.
DEFAULT_LEASE_SECONDS = int(os.getenv('ORCH_JOB_LEASE_SECONDS', '900'))  # 15 min

# The orchestrate_tour_async parameters we persist in params JSONB. Keeping the
# list explicit (rather than **kwargs) means a new argument is a deliberate
# change here, not a silent drop — the exact failure mode LOCAL-547 warns about.
PARAM_KEYS = (
    'location', 'tour_type', 'total_stops', 'user_id', 'request_string',
    'language', 'persona', 'is_test', 'stops', 'mode',
    'community_id', 'community_visibility',
)


class OrchestratorJobsStore:
    """PostgreSQL-backed store for orchestrator tour jobs (orchestrator_jobs).

    Best-effort throughout: DB errors are logged and swallowed. The lease
    operations are the exception to "swallow and return None" only in that they
    return a boolean/row so the caller knows whether it won the lease.
    """

    def __init__(self):
        self._db_config = {
            'host': os.getenv('DB_HOST', 'postgres-2'),
            'database': os.getenv('DB_NAME', 'audiotours'),
            'user': os.getenv('DB_USER', 'admin'),
            'password': os.getenv('DB_PASSWORD', 'password123'),
            'port': os.getenv('DB_PORT', '5432'),
        }
        self._ddl_ensured = False

    def _get_conn(self):
        import psycopg2
        return psycopg2.connect(connect_timeout=5, **self._db_config)

    def _ensure_table(self, conn):
        """Self-healing DDL: create orchestrator_jobs if migration 061 hasn't run.

        Idempotent and identical in shape to
        migration/sql/061_orchestrator_jobs.sql, so the store converges whether
        or not the migration was applied — the same pattern generator_jobs and
        audio_tours use for their own tables.
        """
        if self._ddl_ensured:
            return
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orchestrator_jobs (
                job_id            VARCHAR(64) PRIMARY KEY,
                generator_job_id  VARCHAR(64),
                status            VARCHAR(20) NOT NULL DEFAULT 'queued',
                params            JSONB NOT NULL DEFAULT '{}'::jsonb,
                error             TEXT,
                lease_owner       VARCHAR(128),
                lease_expires_at  TIMESTAMP,
                created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orchestrator_jobs_status_updated
                ON orchestrator_jobs (status, updated_at)
        """)
        conn.commit()
        cur.close()
        self._ddl_ensured = True

    @staticmethod
    def _extract_params(fields):
        """Pull the known orchestrate_tour_async params out of a flat dict."""
        return {k: fields[k] for k in PARAM_KEYS if k in fields}

    # -- lifecycle writes ---------------------------------------------------

    def create(self, job_id, **params):
        """Record a new job at /generate time (status 'queued').

        ON CONFLICT DO NOTHING: /generate owns creation, so a retry of the same
        request id is a no-op rather than a reset of an advancing job.
        """
        param_blob = self._extract_params(params)
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs create skipped (no DB): {conn_err}")
            return
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orchestrator_jobs (job_id, status, params)
                VALUES (%s, 'queued', %s)
                ON CONFLICT (job_id) DO NOTHING
                """,
                (job_id, json.dumps(param_blob, default=str)),
            )
            conn.commit()
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs create failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def set_generator_job_id(self, job_id, generator_job_id):
        """Persist the generator's text job id as soon as /generate returns it,
        and move the job to 'processing'. This is the single most important
        write for resume: without generator_job_id a fresh instance cannot
        re-attach to the already-running (or already-finished) generator job."""
        self._update(job_id, generator_job_id=generator_job_id, status='processing')

    def mark_processing(self, job_id):
        self._update(job_id, status='processing')

    def mark_completed(self, job_id):
        """Terminal success. Also clears the lease so the row reads clean."""
        self._update(job_id, status='completed', error=None,
                     lease_owner=None, lease_expires_at=None)

    def mark_error(self, job_id, reason=None):
        """Terminal failure with a reason. Clears the lease."""
        self._update(job_id, status='error', error=(str(reason)[:2000] if reason else None),
                     lease_owner=None, lease_expires_at=None)

    def _update(self, job_id, **fields):
        """Internal: UPDATE the named columns on a job row. Best-effort.

        Columns accepted: generator_job_id, status, error, lease_owner,
        lease_expires_at. `error` is set even to NULL when passed explicitly so a
        resumed success clears a prior reason; other columns are only touched
        when present.
        """
        allowed = ('generator_job_id', 'status', 'error', 'lease_owner', 'lease_expires_at')
        set_parts = ['updated_at = CURRENT_TIMESTAMP']
        values = []
        for col in allowed:
            if col in fields:
                set_parts.append(f"{col} = %s")
                values.append(fields[col])
        if len(set_parts) == 1:
            return  # nothing to update
        values.append(job_id)
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs update skipped (no DB): {conn_err}")
            return
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                f"UPDATE orchestrator_jobs SET {', '.join(set_parts)} WHERE job_id = %s",
                values,
            )
            conn.commit()
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs update failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # -- reads --------------------------------------------------------------

    def get(self, job_id):
        """Return the job row as a flat dict (params merged up), or None."""
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs get skipped (no DB): {conn_err}")
            return None
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT job_id, generator_job_id, status, params, error,
                       lease_owner, lease_expires_at, created_at, updated_at
                FROM orchestrator_jobs WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
            cur.close()
            return self._row_to_dict(row)
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs get failed for {job_id}: {db_err}")
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _row_to_dict(row):
        if not row:
            return None
        params = row[3]
        if params and not isinstance(params, dict):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        params = params or {}
        result = {
            'job_id': row[0],
            'generator_job_id': row[1],
            'status': row[2],
            'params': params,
            'error': row[4],
            'lease_owner': row[5],
            'lease_expires_at': row[6].isoformat() if row[6] else None,
            'created_at': row[7].isoformat() if row[7] else None,
            'updated_at': row[8].isoformat() if row[8] else None,
        }
        # Merge params up to the flat shape orchestrate_tour_async wants.
        for k in PARAM_KEYS:
            result.setdefault(k, params.get(k))
        return result

    def list_resumable(self, min_age_seconds=0, limit=50):
        """Return non-terminal jobs whose lease is free or expired, oldest first.

        min_age_seconds lets the caller ignore jobs that only just started on
        another live instance (updated within the last N seconds), so the sweep
        does not race a healthy in-flight job. A job that has not advanced for
        min_age_seconds is a candidate: either the owning instance is gone or it
        is genuinely stalled, and re-attaching to its generator job is safe
        because the lease still serialises the finish.
        """
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs list_resumable skipped (no DB): {conn_err}")
            return []
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT job_id, generator_job_id, status, params, error,
                       lease_owner, lease_expires_at, created_at, updated_at
                FROM orchestrator_jobs
                WHERE status NOT IN ('completed', 'error')
                  AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
                  AND updated_at < NOW() - (%s || ' seconds')::interval
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (str(int(min_age_seconds)), int(limit)),
            )
            rows = cur.fetchall()
            cur.close()
            return [self._row_to_dict(r) for r in rows]
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs list_resumable failed: {db_err}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # -- lease --------------------------------------------------------------

    def acquire_lease(self, job_id, lease_seconds=None, owner=None):
        """Atomically take the lease on a non-terminal job and return its row,
        or None if another instance holds a live lease (or the job is terminal).

        The single UPDATE ... WHERE (lease free/expired) ... RETURNING is the
        whole concurrency guard: Postgres row-locks the job, so of two instances
        racing to resume the same job exactly one UPDATE affects the row and only
        that instance gets a RETURNING row. The loser sees None and moves on.
        """
        lease_seconds = lease_seconds if lease_seconds is not None else DEFAULT_LEASE_SECONDS
        owner = owner or INSTANCE_ID
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs acquire_lease skipped (no DB): {conn_err}")
            return None
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE orchestrator_jobs
                SET lease_owner = %s,
                    lease_expires_at = NOW() + (%s || ' seconds')::interval,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                  AND status NOT IN ('completed', 'error')
                  AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
                RETURNING job_id, generator_job_id, status, params, error,
                          lease_owner, lease_expires_at, created_at, updated_at
                """,
                (owner, str(int(lease_seconds)), job_id),
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return self._row_to_dict(row)
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs acquire_lease failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def release_lease(self, job_id, owner=None):
        """Give back a lease without changing the job status (e.g. the finish
        could not complete this round and should be retried by a later sweep).
        Only the current owner may release — a no-op otherwise."""
        owner = owner or INSTANCE_ID
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs release_lease skipped (no DB): {conn_err}")
            return
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE orchestrator_jobs
                SET lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s AND lease_owner = %s
                """,
                (job_id, owner),
            )
            conn.commit()
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-821] orchestrator_jobs release_lease failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


_SINGLETON = None


def get_orchestrator_jobs_store():
    """Process-wide singleton (so _ddl_ensured is shared and the first call pays
    the DDL check once)."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = OrchestratorJobsStore()
    return _SINGLETON
