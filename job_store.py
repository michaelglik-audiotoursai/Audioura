"""
Job Store ΓÇö Database-backed replacement for ACTIVE_JOBS in-memory dict.
===========================================================================

In Docker (single instance), services use ACTIVE_JOBS = {} which works fine.
In Cloud Run (multi-instance), polling /status/<job_id> may hit a different
container than the one that created the job ΓåÆ 404.

This module provides a drop-in replacement that stores job state in PostgreSQL,
making it accessible from any instance.

Feature flag: JOB_STORE_MODE env var
  - 'memory' (default): use in-memory dict (backwards compatible, local Docker)
  - 'database': use PostgreSQL job_status table (Cloud Run)

Usage:
    from job_store import get_job_store
    
    jobs = get_job_store()
    jobs.create('abc-123', service='tour-generator', location='Boston')
    jobs.update('abc-123', status='processing', progress='Step 2/5...')
    job = jobs.get('abc-123')  # returns dict or None
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

JOB_STORE_MODE = os.getenv('JOB_STORE_MODE', 'memory')


class MemoryJobStore:
    """In-memory job store (current behavior, single-instance only)."""

    def __init__(self):
        self._jobs = {}

    def create(self, job_id, **kwargs):
        """Create a new job entry."""
        self._jobs[job_id] = {
            'job_id': job_id,
            'status': kwargs.get('status', 'queued'),
            'progress': kwargs.get('progress', ''),
            'created_at': datetime.now().isoformat(),
            **kwargs
        }
        return self._jobs[job_id]

    def update(self, job_id, **kwargs):
        """Update job fields. Creates if not exists."""
        if job_id not in self._jobs:
            self._jobs[job_id] = {'job_id': job_id}
        self._jobs[job_id].update(kwargs)
        return self._jobs[job_id]

    def get(self, job_id):
        """Get job by ID. Returns dict or None."""
        return self._jobs.get(job_id)

    def delete(self, job_id):
        """Delete a job entry."""
        self._jobs.pop(job_id, None)

    def list_active(self):
        """List all non-completed jobs."""
        return {k: v for k, v in self._jobs.items()
                if v.get('status') not in ('completed', 'error')}

    # Dict-like access for backwards compatibility with ACTIVE_JOBS[job_id]
    def __getitem__(self, job_id):
        if job_id not in self._jobs:
            raise KeyError(job_id)
        return self._jobs[job_id]

    def __setitem__(self, job_id, value):
        self._jobs[job_id] = value

    def __contains__(self, job_id):
        return job_id in self._jobs

    def __delitem__(self, job_id):
        del self._jobs[job_id]


class DatabaseJobStore:
    """PostgreSQL-backed job store (multi-instance safe)."""

    def __init__(self, service_name='unknown'):
        self.service_name = service_name
        self._db_config = {
            'host': os.getenv('DB_HOST', 'postgres-2'),
            'database': os.getenv('DB_NAME', 'audiotours'),
            'user': os.getenv('DB_USER', 'admin'),
            'password': os.getenv('DB_PASSWORD', 'password123'),
            'port': os.getenv('DB_PORT', '5432')
        }

    def _get_conn(self):
        import psycopg2
        return psycopg2.connect(**self._db_config)

    def create(self, job_id, **kwargs):
        """Create a new job entry in DB."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            output_data = {k: v for k, v in kwargs.items()
                          if k not in ('status', 'progress', 'location', 'tour_type', 'total_stops', 'error')}
            cur.execute("""
                INSERT INTO job_status (job_id, service_name, status, progress, location, tour_type, total_stops, output_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    progress = EXCLUDED.progress,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                job_id, self.service_name,
                kwargs.get('status', 'queued'),
                kwargs.get('progress', ''),
                kwargs.get('location', ''),
                kwargs.get('tour_type', ''),
                kwargs.get('total_stops'),
                json.dumps(output_data) if output_data else '{}'
            ))
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return self.get(job_id)

    def update(self, job_id, **kwargs):
        """Update job fields in DB."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            # Build SET clause dynamically
            set_parts = ["updated_at = CURRENT_TIMESTAMP"]
            values = []
            field_map = {
                'status': 'status', 'progress': 'progress',
                'location': 'location', 'tour_type': 'tour_type',
                'total_stops': 'total_stops', 'error': 'error'
            }
            extra_data = {}
            for key, val in kwargs.items():
                if key in field_map:
                    set_parts.append(f"{field_map[key]} = %s")
                    values.append(val)
                else:
                    extra_data[key] = val

            if extra_data:
                set_parts.append("output_data = output_data || %s::jsonb")
                values.append(json.dumps(extra_data, default=str))

            values.append(job_id)
            sql = f"UPDATE job_status SET {', '.join(set_parts)} WHERE job_id = %s"
            cur.execute(sql, values)

            if cur.rowcount == 0:
                # Job doesn't exist yet, create it
                conn.rollback()
                cur.close()
                conn.close()
                return self.create(job_id, **kwargs)

            conn.commit()
            cur.close()
        finally:
            conn.close()
        return self.get(job_id)

    def get(self, job_id):
        """Get job by ID from DB. Returns dict or None."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT job_id, service_name, status, progress, location, tour_type,
                       total_stops, output_data, error, created_at, updated_at
                FROM job_status WHERE job_id = %s
            """, (job_id,))
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            result = {
                'job_id': row[0], 'service_name': row[1], 'status': row[2],
                'progress': row[3], 'location': row[4], 'tour_type': row[5],
                'total_stops': row[6], 'error': row[8],
                'created_at': row[9].isoformat() if row[9] else None,
                'updated_at': row[10].isoformat() if row[10] else None,
            }
            # Merge output_data into result
            if row[7]:
                output = row[7] if isinstance(row[7], dict) else json.loads(row[7])
                result.update(output)
            return result
        finally:
            conn.close()

    def delete(self, job_id):
        """Delete a job entry from DB."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM job_status WHERE job_id = %s", (job_id,))
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def list_active(self):
        """List all non-completed jobs for this service."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT job_id FROM job_status
                WHERE service_name = %s AND status NOT IN ('completed', 'error')
                ORDER BY created_at DESC LIMIT 50
            """, (self.service_name,))
            rows = cur.fetchall()
            cur.close()
            return {row[0]: self.get(row[0]) for row in rows}
        finally:
            conn.close()

    # Dict-like access for backwards compatibility
    def __getitem__(self, job_id):
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def __setitem__(self, job_id, value):
        if isinstance(value, dict):
            self.update(job_id, **value)
        else:
            self.update(job_id, status=str(value))

    def __contains__(self, job_id):
        return self.get(job_id) is not None

    def __delitem__(self, job_id):
        self.delete(job_id)


# ---------------------------------------------------------------------------
# [LOCAL-775 / D718] generator_jobs table: source-of-truth with memory cache.
# ---------------------------------------------------------------------------
#
# The DatabaseJobStore above is the old all-or-nothing design (JOB_STORE_MODE
# 'database'): a service writes EITHER to memory OR to the job_status table.
# D718 showed that is not enough for the tour-generator — a second Cloud Run
# instance that never saw the job answers the orchestrator's /status poll with
# 404 "Job not found" and the (already paid-for) tour is lost.
#
# The ruling is: job status goes to the database; the in-memory dict stays only
# as a cache. GeneratorJobsStore is the DB half (the generator_jobs table from
# migration 058); LayeredJobStore composes a MemoryJobStore cache in front of it
# so every write goes to BOTH and every read falls back to the table. A job the
# table knows is never "Job not found" from any instance.

# A stable id for the container/instance that owns a job, for D718 diagnostics.
# Cloud Run exposes the revision/instance; fall back to hostname locally.
INSTANCE_ID = (
    os.getenv('INSTANCE_ID')
    or os.getenv('K_REVISION')
    or os.getenv('HOSTNAME')
    or 'unknown'
)

# Flat generator fields that are real columns on generator_jobs. Everything else
# a caller passes splits into the result/error JSONB blobs (see _split_fields).
_GENERATOR_COLUMNS = ('status', 'progress', 'location', 'tour_type', 'total_stops')

# Keys that belong in the `error` JSONB (the structured refusal the app needs,
# LOCAL-580/597/774, plus related failure metadata). Anything else that is not a
# column goes into `result` (the completed-tour payload the orchestrator reads).
_ERROR_KEYS = frozenset((
    'error', 'error_code', 'error_type', 'message', 'suggestion',
    'nearby_tours', 'evidence_summary', 'coordinate_path',
))


def _split_fields(fields):
    """Split a flat generator job dict into (columns, result_extra, error_extra).

    columns      -> the typed generator_jobs columns present in `fields`
    result_extra -> non-column, non-error keys (output_file, tour_content,
                    coordinates, tour_kind, i_con_avg, qa_style_warning, …)
    error_extra  -> the structured-refusal / failure keys in _ERROR_KEYS
    """
    columns, result_extra, error_extra = {}, {}, {}
    for key, val in fields.items():
        if key in ('job_id', 'created_at', 'updated_at', 'instance_id'):
            continue  # managed by the store itself
        if key in _GENERATOR_COLUMNS:
            columns[key] = val
        elif key in _ERROR_KEYS:
            error_extra[key] = val
        else:
            result_extra[key] = val
    return columns, result_extra, error_extra


class GeneratorJobsStore:
    """PostgreSQL-backed store for the tour-generator's async jobs (generator_jobs).

    Every public method is best-effort: a DB error is logged and swallowed so a
    transient database problem never breaks generation (the LayeredJobStore's
    memory cache keeps serving). Reads return a flat dict shaped like the old
    ACTIVE_JOBS entry (columns + merged result/error JSON), or None.
    """

    def __init__(self, service_name='tour-generator'):
        self.service_name = service_name
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
        conn = psycopg2.connect(connect_timeout=5, **self._db_config)
        return conn

    def _ensure_table(self, conn):
        """Self-healing DDL: create generator_jobs if migration 058 hasn't run.

        Idempotent and identical in shape to migration/sql/058_generator_jobs.sql,
        so the store converges whether or not the migration was applied — the same
        pattern the other services use for their own tables.
        """
        if self._ddl_ensured:
            return
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS generator_jobs (
                job_id       VARCHAR(64) PRIMARY KEY,
                status       VARCHAR(20) NOT NULL DEFAULT 'queued',
                progress     TEXT,
                location     TEXT,
                tour_type    VARCHAR(50),
                total_stops  INTEGER,
                result       JSONB NOT NULL DEFAULT '{}'::jsonb,
                error        JSONB NOT NULL DEFAULT '{}'::jsonb,
                instance_id  VARCHAR(128),
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_generator_jobs_created
                ON generator_jobs (created_at)
        """)
        conn.commit()
        cur.close()
        self._ddl_ensured = True

    def upsert(self, job_id, **fields):
        """Insert or update a job row from a flat generator job dict.

        Columns are overwritten with any present values; result/error JSONB are
        MERGED (jsonb ||) so a later partial update (e.g. just a progress string,
        or just the structured refusal) never wipes earlier keys.
        """
        columns, result_extra, error_extra = _split_fields(fields)
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-775] generator_jobs upsert skipped (no DB): {conn_err}")
            return
        try:
            self._ensure_table(conn)
            cur = conn.cursor()

            # instance_id is carried in the INSERT, so the UPDATE branch reads it
            # from EXCLUDED — no extra placeholder (keeps params == %s count).
            set_parts = ["updated_at = CURRENT_TIMESTAMP", "instance_id = EXCLUDED.instance_id"]
            insert_cols = ["job_id", "instance_id"]
            insert_vals = [job_id, INSTANCE_ID]

            for col in _GENERATOR_COLUMNS:
                if col in columns:
                    insert_cols.append(col)
                    insert_vals.append(columns[col])
                    set_parts.append(f"{col} = EXCLUDED.{col}")

            # result/error JSONB: insert the extra dict, merge on conflict.
            insert_cols.append("result")
            insert_vals.append(json.dumps(result_extra, default=str) if result_extra else '{}')
            set_parts.append("result = generator_jobs.result || EXCLUDED.result")

            insert_cols.append("error")
            insert_vals.append(json.dumps(error_extra, default=str) if error_extra else '{}')
            set_parts.append("error = generator_jobs.error || EXCLUDED.error")

            placeholders = ", ".join(["%s"] * len(insert_vals))
            sql = (
                f"INSERT INTO generator_jobs ({', '.join(insert_cols)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT (job_id) DO UPDATE SET {', '.join(set_parts)}"
            )
            cur.execute(sql, insert_vals)
            conn.commit()
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-775] generator_jobs upsert failed for {job_id}: {db_err}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # upsert covers both create and update for the DB layer.
    create = upsert
    update = upsert

    def get(self, job_id):
        """Return the job as a flat dict (columns + merged result/error), or None."""
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-775] generator_jobs get skipped (no DB): {conn_err}")
            return None
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute("""
                SELECT job_id, status, progress, location, tour_type, total_stops,
                       result, error, instance_id, created_at, updated_at
                FROM generator_jobs WHERE job_id = %s
            """, (job_id,))
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            result = {
                'job_id': row[0],
                'status': row[1],
                'progress': row[2],
                'location': row[3],
                'tour_type': row[4],
                'total_stops': row[5],
                'instance_id': row[8],
                'created_at': row[9].isoformat() if row[9] else None,
                'updated_at': row[10].isoformat() if row[10] else None,
            }
            # Merge the result and error JSONB blobs back up to the flat shape the
            # /status endpoint and the orchestrator expect (tour_content, error_code…).
            for blob in (row[6], row[7]):
                if blob:
                    data = blob if isinstance(blob, dict) else json.loads(blob)
                    result.update(data)
            return result
        except Exception as db_err:
            logger.warning(f"[LOCAL-775] generator_jobs get failed for {job_id}: {db_err}")
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def delete(self, job_id):
        """Not used by the generator (jobs age out via the created_at index)."""
        return None

    def items(self):
        """All known jobs as (job_id, dict) pairs — best-effort, capped."""
        try:
            conn = self._get_conn()
        except Exception as conn_err:
            logger.warning(f"[LOCAL-775] generator_jobs items skipped (no DB): {conn_err}")
            return []
        try:
            self._ensure_table(conn)
            cur = conn.cursor()
            cur.execute("SELECT job_id FROM generator_jobs ORDER BY created_at DESC LIMIT 200")
            ids = [r[0] for r in cur.fetchall()]
            cur.close()
        except Exception as db_err:
            logger.warning(f"[LOCAL-775] generator_jobs items failed: {db_err}")
            ids = []
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return [(jid, self.get(jid)) for jid in ids]


class LayeredJobStore:
    """[LOCAL-775 / D718] In-memory cache in front of the generator_jobs table.

    Writes go to BOTH layers (write-through). Reads hit the memory cache first,
    then fall back to the table — so a job created on instance A is visible on
    instance B, which is the whole point of D718. The DB layer is best-effort:
    if the database is unreachable the store still behaves like the old
    in-memory dict, so generation never breaks on a transient DB problem.
    """

    def __init__(self, service_name='tour-generator'):
        self._memory = MemoryJobStore()
        self._db = GeneratorJobsStore(service_name=service_name)

    def create(self, job_id, **kwargs):
        self._memory.create(job_id, **kwargs)
        self._db.upsert(job_id, **kwargs)
        return self._memory.get(job_id)

    def update(self, job_id, **kwargs):
        self._memory.update(job_id, **kwargs)
        self._db.upsert(job_id, **kwargs)
        return self._memory.get(job_id)

    # A job in one of these states will not change again — its cache entry is
    # safe to trust without re-reading the source of truth.
    _TERMINAL = ('completed', 'error')

    def get(self, job_id):
        """Read memory first, then the generator_jobs table.

        [LOCAL-775 / D718] The table is the source of truth; memory is only a
        cache. A terminal (completed/error) cache entry is immutable, so it is
        returned directly. For a NON-terminal cache entry we re-consult the table
        and prefer it when it has advanced — otherwise an instance that cached a
        job as 'processing' (e.g. from an earlier poll) would keep serving that
        stale status even after ANOTHER instance finished the job and wrote the
        result. That exact staleness would re-lose the tour D718 is about.
        """
        cached = self._memory.get(job_id)
        if cached is not None and cached.get('status') in self._TERMINAL:
            return cached

        from_db = self._db.get(job_id)
        if from_db is not None:
            # Table wins for a live job: refresh the cache from it and return it.
            warm = {k: v for k, v in from_db.items() if k != 'job_id'}
            self._memory.update(job_id, **warm)
            return from_db
        # Not in the table (or DB unreachable) — fall back to whatever the cache
        # has, so a transient DB problem never loses a locally-known job.
        return cached

    def delete(self, job_id):
        self._memory.delete(job_id)
        self._db.delete(job_id)

    def list_active(self):
        return self._memory.list_active()

    def items(self):
        """Union of DB and memory jobs, DB values preferred (source of truth)."""
        merged = {}
        for jid, data in self._memory.items() if hasattr(self._memory, 'items') else self._memory._jobs.items():
            merged[jid] = data
        for jid, data in self._db.items():
            if data is not None:
                merged[jid] = data
        return list(merged.items())

    # Dict-like access, mirroring the old ACTIVE_JOBS dict and MemoryJobStore.
    def __getitem__(self, job_id):
        result = self.get(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def __setitem__(self, job_id, value):
        if isinstance(value, dict):
            self._memory[job_id] = value
            self._db.upsert(job_id, **value)
        else:
            self.update(job_id, status=str(value))

    def __contains__(self, job_id):
        if job_id in self._memory:
            return True
        return self._db.get(job_id) is not None

    def __delitem__(self, job_id):
        self.delete(job_id)


def get_job_store(service_name='unknown', mode=None):
    """
    Factory function. Returns the appropriate JobStore implementation.

    mode: explicit store mode for this caller. When None, falls back to the
          JOB_STORE_MODE env var (default 'memory'). The tour-generator passes
          'layered' so its D718 fix is on by default without changing the env
          for every other service.

    JOB_STORE_MODE / mode:
      'memory' (default)  in-memory dict (backwards compatible, local Docker)
      'database'          PostgreSQL job_status table (legacy all-or-nothing)
      'layered'           [LOCAL-775/D718] memory cache + generator_jobs table;
                          the DB is source of truth, memory is only a cache.
                          Multi-instance safe: a job created on one instance is
                          visible from any other, so the /status poll never 404s.
    """
    effective_mode = mode or JOB_STORE_MODE
    if effective_mode == 'layered':
        logger.info(f"Using LayeredJobStore (memory cache + generator_jobs) for service '{service_name}'")
        return LayeredJobStore(service_name=service_name)
    if effective_mode == 'database':
        logger.info(f"Using DatabaseJobStore for service '{service_name}'")
        return DatabaseJobStore(service_name=service_name)
    else:
        logger.info(f"Using MemoryJobStore for service '{service_name}'")
        return MemoryJobStore()
