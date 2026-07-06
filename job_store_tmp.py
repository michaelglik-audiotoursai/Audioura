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


def get_job_store(service_name='unknown'):
    """
    Factory function. Returns the appropriate JobStore implementation.
    
    JOB_STORE_MODE:
      'memory' (default) ΓÇö in-memory dict (backwards compatible, local Docker)
      'database' ΓÇö PostgreSQL job_status table (Cloud Run multi-instance safe)
    """
    if JOB_STORE_MODE == 'database':
        logger.info(f"Using DatabaseJobStore for service '{service_name}'")
        return DatabaseJobStore(service_name=service_name)
    else:
        logger.info(f"Using MemoryJobStore for service '{service_name}'")
        return MemoryJobStore()
