"""
Cost Ceiling Monitor — dual-threshold per-tour cost guard.
============================================================
Two thresholds (both configurable via env vars):

  COST_TARGET (default $0.15)
      Design target. Exceeding → WARN. Tour still delivered.

  COST_HARD_LIMIT (default $2.00)
      Michael's directive (D45): "let's make the tour maximum from $1.30
      to $2.00." Exceeding → ABORT. Tour is NOT delivered. Error returned
      to caller.

The function also:
  - Flags the cost_ledger row (ceiling_breach column)
  - Increments an in-memory counter exposed on /health for alerting

Usage:
    from cost_ceiling_monitor import enforce_cost_ceiling, get_ceiling_stats

    result = enforce_cost_ceiling(
        total_cost=0.18,
        job_id="abc-123",
        user_id="user-xyz",
        tour_category="art and paintings",
    )
    if result["abort"]:
        # Stop generation, return error
        ...
"""

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# --- Configuration (env-var-tunable, no redeploy needed) ---
COST_TARGET = float(os.environ.get("COST_TARGET_USD", "0.15"))
COST_HARD_LIMIT = float(os.environ.get("COST_HARD_LIMIT_USD", "2.00"))

# --- In-memory counters for /health exposure ---
_lock = threading.Lock()
_ceiling_stats = {
    "target_warnings": 0,
    "hard_limit_aborts": 0,
    "last_abort_job_id": None,
    "last_abort_cost": None,
}


def get_ceiling_stats() -> dict:
    """Return current ceiling breach counters (for health endpoint)."""
    with _lock:
        return dict(_ceiling_stats)


def _flag_ledger_row(job_id: str, breach_level: str) -> None:
    """Flag the cost_ledger row with ceiling_breach info.

    breach_level: 'target_exceeded' or 'hard_limit_exceeded'
    Non-fatal — never crashes the caller.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "postgres-2"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "audiotours"),
            user=os.environ.get("DB_USER", "admin"),
            password=os.environ.get("DB_PASSWORD", "password123"),
        )
        cur = conn.cursor()

        # Ensure ceiling_breach column exists (idempotent ALTER)
        cur.execute("""
            DO $$
            BEGIN
                ALTER TABLE cost_ledger ADD COLUMN ceiling_breach VARCHAR(32);
            EXCEPTION
                WHEN duplicate_column THEN NULL;
            END $$;
        """)

        # Update the row(s) for this job
        cur.execute(
            "UPDATE cost_ledger SET ceiling_breach = %s WHERE job_id = %s",
            (breach_level, job_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"[COST_CEILING] Flagged ledger row: job={job_id}, breach={breach_level}")
    except Exception as e:
        logger.warning(f"[COST_CEILING] Failed to flag ledger row (non-fatal): {e}")


def enforce_cost_ceiling(
    total_cost: float,
    job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tour_category: str = "unknown",
) -> dict:
    """Check tour cost against both thresholds.

    Args:
        total_cost: Actual cost in USD for this tour generation.
        job_id: Correlation ID (for ledger flagging).
        user_id: The user who triggered generation.
        tour_category: Tour type label (for logging).

    Returns:
        dict:
            abort: bool — True if hard limit exceeded (caller MUST stop)
            warn: bool — True if target exceeded but under hard limit
            cost: float — the input cost
            target: float — the design target
            hard_limit: float — the absolute ceiling
            breach_level: str or None — 'target_exceeded' | 'hard_limit_exceeded' | None
            message: str — human-readable explanation
    """
    result = {
        "abort": False,
        "warn": False,
        "cost": total_cost,
        "target": COST_TARGET,
        "hard_limit": COST_HARD_LIMIT,
        "breach_level": None,
        "message": "",
    }

    # Case 1: Under target — all good
    if total_cost <= COST_TARGET:
        result["message"] = f"COST OK: ${total_cost:.4f} <= target ${COST_TARGET:.4f}"
        logger.info(f"[COST_CEILING] {result['message']} (category={tour_category})")
        print(f"[COST_CEILING] {result['message']}")
        return result

    # Case 2: Between target and hard limit — WARN
    if total_cost <= COST_HARD_LIMIT:
        result["warn"] = True
        result["breach_level"] = "target_exceeded"
        result["message"] = (
            f"COST WARNING: ${total_cost:.4f} exceeds target ${COST_TARGET:.4f} "
            f"(hard limit ${COST_HARD_LIMIT:.4f}, category={tour_category})"
        )
        logger.warning(f"[COST_CEILING] {result['message']}")
        print(f"[COST_CEILING] {result['message']}")

        with _lock:
            _ceiling_stats["target_warnings"] += 1

        # Flag the ledger row
        if job_id:
            _flag_ledger_row(job_id, "target_exceeded")

        return result

    # Case 3: Exceeds hard limit — ABORT
    result["abort"] = True
    result["breach_level"] = "hard_limit_exceeded"
    result["message"] = (
        f"COST HARD LIMIT EXCEEDED: ${total_cost:.4f} > ${COST_HARD_LIMIT:.4f} — "
        f"ABORTING tour delivery (category={tour_category}, user={user_id}). "
        f"Michael's directive (D45): ceiling is ${COST_HARD_LIMIT:.2f}."
    )
    logger.error(f"[COST_CEILING] {result['message']}")
    print(f"[COST_CEILING] {result['message']}")

    with _lock:
        _ceiling_stats["hard_limit_aborts"] += 1
        _ceiling_stats["last_abort_job_id"] = job_id
        _ceiling_stats["last_abort_cost"] = total_cost

    # Flag the ledger row
    if job_id:
        _flag_ledger_row(job_id, "hard_limit_exceeded")

    return result
