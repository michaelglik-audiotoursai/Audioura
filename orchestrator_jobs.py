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
  * status — queued | processing | storing | completed | error. The sweep
    looks for non-terminal rows. [LOCAL-829] 'storing' is the brief window held
    by the single path that won the atomic store-claim; it is non-terminal, so a
    row stuck in 'storing' with an EXPIRED lease (a crash mid-store) is still
    resumable, while a 'storing' row with a LIVE lease is left alone.
  * lease_owner / lease_expires_at — a time-boxed lease so two instances never
    finish the same job twice. [LOCAL-829] The LIVE path (not just resume) now
    takes this lease and RENEWS it while it works, so a sweep on the same
    instance never resumes a thread that is still polling.

Every method is best-effort: a DB error is logged and swallowed so a transient
database problem never breaks live generation. When the DB is unreachable the
orchestrator simply behaves as it did before this module existed (the in-memory
path still delivers the tour on the instance that generated it); the durable
resume is the extra safety net, not a new hard dependency.
"""

import os
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Terminal statuses: a job in one of these will not be resumed.
TERMINAL_STATUSES = ('completed', 'error')

# [LOCAL-829] A short-lived, per-instance random suffix so two instances that
# share a K_REVISION (Cloud Run scales a revision to >1 instance) still mint
# DISTINCT lease owners. Without it, two live instances of the same revision
# would compute the same owner string and a renew/claim meant for one could be
# honoured for the other — exactly the cross-instance confusion the lease exists
# to prevent. Generated once per process.
_INSTANCE_RANDOM = uuid.uuid4().hex[:8]


def make_owner():
    """[LOCAL-829] A lease-owner token unique to THIS live run.

    Shape: ``<instance>:<pid>:<thread>`` where <instance> is K_REVISION (Cloud
    Run) or HOSTNAME (local) plus a per-process random id so two instances of the
    same revision never collide. The live path and the resume path each take the
    lease under their own owner and renew only while lease_owner matches, so a
    sweep on the SAME process as a live thread cannot steal or renew that
    thread's row (the defect behind LOCAL-829)."""
    instance = (
        os.getenv('K_REVISION')
        or os.getenv('INSTANCE_ID')
        or os.getenv('HOSTNAME')
        or 'unknown'
    )
    return f"{instance}-{_INSTANCE_RANDOM}:{os.getpid()}:{threading.get_ident()}"

# A stable id for the container/instance that owns a lease. Cloud Run exposes
# the revision/instance; fall back to hostname locally. Same convention as
# job_store.INSTANCE_ID.
INSTANCE_ID = (
    os.getenv('INSTANCE_ID')
    or os.getenv('K_REVISION')
    or os.getenv('HOSTNAME')
    or 'unknown'
)

# How long a lease is held before another instance may take the job.
# [LOCAL-829] The live path now RENEWS this lease on every poll iteration and
# during store (renew_lease), so the length only has to comfortably outlast one
# renew interval: the rule is lease_seconds >= 3x the renew interval, so a couple
# of missed renews (a slow poll, a brief DB blip) do not drop the lease under a
# live thread and invite a sweep to resume it. With the default 900 s lease and
# the orchestrator's ~10 s poll cadence that margin is large. Overridable for
# tests / tuning.
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


    def renew_lease(self, job_id, owner, lease_seconds=None):
        """[LOCAL-829] Extend the lease on a job this owner already holds.

        The whole point of the renew is that the LIVE path owns its row for the
        full duration of generation+store: a fresh orchestrate_tour_async takes
        the lease when it starts and calls this on every poll iteration and
        again during voice/store, so lease_expires_at is always in the future
        while the thread is alive. list_resumable only offers rows whose lease is
        free or expired, so a renewed row is never picked up by a sweep running
        on the same (or any) instance.

        The UPDATE touches the row ONLY when lease_owner = owner, so it is safe
        to call from the live thread: it can renew its own lease and nobody
        else's. Returns True when the row was renewed (we still own it), False
        when we do not (lease was stolen after expiry, or the job went terminal).
        Best-effort: a DB error returns False so the caller treats it like a lost
        lease and does not assume ownership it cannot prove.
        """
        lease_seconds = lease_seconds if lease_seconds is not None else DEFAULT_LEASE_SECONDS
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs renew_lease skipped (no DB): {conn_err}")
            return False
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE orchestrator_jobs
                SET lease_expires_at = NOW() + (%s || ' seconds')::interval,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                  AND lease_owner = %s
                  AND status NOT IN ('completed', 'error')
                RETURNING job_id
                """,
                (str(int(lease_seconds)), job_id, owner),
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return row is not None
        except Exception as db_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs renew_lease failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def claim_store(self, job_id, owner, lease_seconds=None):
        """[LOCAL-829] Atomically claim the right to store this job's tour.

        The single idempotency guard for the double-store defect: right before
        calling store_audio_tour, each path (live thread OR resumer) runs this.
        Exactly ONE wins — the UPDATE moves the row to 'storing' only when no
        other path is actively storing it: either the status is not yet
        'storing'/'completed', OR it is 'storing' but that claim's lease has
        expired (a crash mid-store, so a sweep legitimately re-claims it). A
        'completed' row is never re-claimed. Of two LIVE racers Postgres
        row-locks the job and only one UPDATE affects it; the winner gets a
        RETURNING row and stores, the loser gets None, logs, and stops. The lease
        is (re)taken by the winner so the store runs under a fresh lease.

        Returns True for the winner, False for the loser (or on any DB error, so
        a store never proceeds on an unproven claim).
        """
        lease_seconds = lease_seconds if lease_seconds is not None else DEFAULT_LEASE_SECONDS
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs claim_store skipped (no DB): {conn_err}")
            return False
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE orchestrator_jobs
                SET status = 'storing',
                    lease_owner = %s,
                    lease_expires_at = NOW() + (%s || ' seconds')::interval,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                  AND status <> 'completed'
                  AND (
                        status <> 'storing'
                        OR lease_expires_at IS NULL
                        OR lease_expires_at < NOW()
                        OR lease_owner = %s
                      )
                RETURNING job_id
                """,
                (owner, str(int(lease_seconds)), job_id, owner),
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return row is not None
        except Exception as db_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs claim_store failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def release_store_claim(self, job_id, owner=None):
        """[LOCAL-829] Undo a store claim when the store itself failed.

        The winner of claim_store sets status back to 'processing' and releases
        the lease, so a later sweep can retry the delivery. Only the current
        owner may do this; a no-op otherwise. A row left in 'storing' with an
        expired lease is still resumable (list_resumable keys on the lease, not
        the status), which covers the crash-after-claim case. Best-effort."""
        owner = owner or INSTANCE_ID
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs release_store_claim skipped (no DB): {conn_err}")
            return
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE orchestrator_jobs
                SET status = 'processing',
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s AND lease_owner = %s AND status = 'storing'
                """,
                (job_id, owner),
            )
            conn.commit()
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-829] orchestrator_jobs release_store_claim failed for {job_id}: {db_err}")
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
