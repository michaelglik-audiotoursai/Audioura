"""
Cost Meter — per-operation cost ledger for Subscribed billing.
===============================================================
Records one row per billable operation into the `cost_ledger` table.
This is the single source of truth for "what did that operation cost us?"

Operation types:
    tour_generate           — fresh tour generation (LLM + TTS + search)
    tour_cache_hit          — tour served from cache (cost ≈ 0)
    translation_generate    — fresh translation (Google Translate + TTS)
    translation_cache_hit   — translation already existed (cost ≈ 0)
    news_generate           — fresh news audio generation
    photo_extension         — (future) photo-based tour extension

Usage:
    from cost_meter import record_operation
    record_operation(
        operation_type="tour_generate",
        user_id="abc123",
        our_cost_usd=0.069,
        cache_hit=False,
        job_id="job-uuid",
        breakdown={"llm": 0.052, "tts": 0.012, "search": 0.005},
    )
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg2

from cost_rates import CACHE_HIT_COST_USD

logger = logging.getLogger(__name__)

# Valid operation types (extensible — add here when new billable paths appear)
VALID_OPERATION_TYPES = frozenset([
    "tour_generate",
    "tour_cache_hit",
    "translation_generate",
    "translation_cache_hit",
    "news_generate",
    "photo_extension",
])


def _get_db_url() -> Optional[str]:
    """Get database URL from environment."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return db_url
    # Fallback: construct from individual env vars (matches service pattern)
    host = os.environ.get("DB_HOST", "postgres-2")
    port = os.environ.get("DB_PORT", "5432")
    dbname = os.environ.get("DB_NAME", "audiotours")
    user = os.environ.get("DB_USER", "admin")
    password = os.environ.get("DB_PASSWORD", "password123")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _ensure_table(conn) -> None:
    """Create cost_ledger table if not present (idempotent, for dev convenience).
    Production should use migration/sql/005_cost_ledger.sql + 007_cost_ledger_description.sql.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cost_ledger (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                operation_type VARCHAR(64) NOT NULL,
                user_id VARCHAR(128),
                our_cost_usd NUMERIC(12, 6) NOT NULL,
                cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
                job_id VARCHAR(128),
                breakdown JSONB,
                description VARCHAR(256),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Add description column if table already exists without it (migration path)
        cur.execute("""
            ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS description VARCHAR(256)
        """)
        # Index for user-level queries and time-range aggregations
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_ledger_user_time
            ON cost_ledger (user_id, created_at)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_ledger_job
            ON cost_ledger (job_id)
        """)
    conn.commit()


def record_operation(
    operation_type: str,
    our_cost_usd: float,
    cache_hit: bool,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    breakdown: Optional[dict] = None,
    description: Optional[str] = None,
) -> Optional[str]:
    """Record a billable operation in the cost ledger.

    Args:
        operation_type: One of VALID_OPERATION_TYPES.
        our_cost_usd: Actual cost to us in USD. For cache hits, pass CACHE_HIT_COST_USD (0.00).
        cache_hit: True if this was served from cache.
        user_id: The user who triggered the operation (may be None for internal jobs).
        job_id: Correlation ID (job_id from the orchestrator or generation service).
        breakdown: Optional JSON-serializable dict with component costs
                   e.g. {"llm": 0.05, "tts": 0.01, "search": 0.005}
        description: Human-readable label for Wallet display,
                     e.g. "Article: How I Built This" or "Tour: French Riviera biking".

    Returns:
        The ledger row UUID as a string, or None on failure.
    """
    if operation_type not in VALID_OPERATION_TYPES:
        logger.error(f"[COST_METER] Invalid operation_type: {operation_type}")
        return None

    # Enforce: cache hits must cost ~0
    if cache_hit and our_cost_usd > 0.001:
        logger.warning(
            f"[COST_METER] cache_hit=True but cost=${our_cost_usd:.4f} — forcing to {CACHE_HIT_COST_USD}. "
            f"This is likely a bug in the caller."
        )
        our_cost_usd = CACHE_HIT_COST_USD

    db_url = _get_db_url()
    if not db_url:
        logger.error("[COST_METER] No database URL available — cannot record cost")
        return None

    row_id = str(uuid.uuid4())
    breakdown_json = json.dumps(breakdown) if breakdown else None

    # Truncate description to 256 chars (DB column limit)
    if description and len(description) > 256:
        description = description[:253] + "..."

    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cost_ledger (id, operation_type, user_id, our_cost_usd, cache_hit, job_id, breakdown, description, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (row_id, operation_type, user_id, our_cost_usd, cache_hit, job_id, breakdown_json, description, datetime.now(timezone.utc)),
            )
        conn.commit()
        conn.close()

        _label = "CACHE_HIT" if cache_hit else "FRESH"
        logger.info(
            f"[COST_METER] {_label} | {operation_type} | ${our_cost_usd:.6f} | "
            f"user={user_id} | job={job_id}"
        )
        print(
            f"[COST_METER] {_label} | {operation_type} | ${our_cost_usd:.6f} | "
            f"user={user_id} | job={job_id}"
        )

        return row_id

    except Exception as e:
        logger.error(f"[COST_METER] Failed to record: {e}")
        print(f"[COST_METER] DB error: {e}")
        return None


def get_operation_cost(job_id: str) -> Optional[dict]:
    """Retrieve cost ledger entries for a given job_id.

    Returns a list of ledger rows (dicts) or None on error.
    """
    db_url = _get_db_url()
    if not db_url:
        return None

    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, operation_type, user_id, our_cost_usd, cache_hit, job_id, breakdown, created_at
                FROM cost_ledger
                WHERE job_id = %s
                ORDER BY created_at
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        conn.close()

        return [
            {
                "id": str(r[0]),
                "operation_type": r[1],
                "user_id": r[2],
                "our_cost_usd": float(r[3]),
                "cache_hit": r[4],
                "job_id": r[5],
                "breakdown": r[6] if isinstance(r[6], dict) else (json.loads(r[6]) if r[6] else None),
                "created_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]

    except Exception as e:
        logger.error(f"[COST_METER] Query failed: {e}")
        return None
