#!/usr/bin/env python3
"""
User Quality Index (LOCAL-312)

Private per-user aggregate of tour quality scores. Purpose: review solicitation.
Michael's words: "later on we may want to ask people for review: then we need
to know who to ask... of course we will keep user's index private."

Design constraints:
  - PRIVATE BY CONSTRUCTION. Never returned by any user-facing endpoint.
  - If a client can request it, the design is wrong.
  - No admin endpoint in this module — internal function call only.
  - Keyed to secret_id (the existing user identifier from audio_tours).
  - Does not introduce new identifying data.
  - Author-edit scores below threshold are recorded internally but
    NEVER produce a user-visible message.

Schema (additive):
    CREATE TABLE user_quality_index (
        secret_id       VARCHAR(255) PRIMARY KEY,
        mean_score      REAL NOT NULL,
        tour_count      INTEGER NOT NULL DEFAULT 0,
        last_scored_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

This module has NO Flask routes. It cannot be wired to an endpoint without
adding code to another module — making accidental exposure structurally hard.
"""
import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


def _get_connection():
    """Get a psycopg2 connection via the shared db_connection helper."""
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from db_connection import get_connection
    return get_connection()


def ensure_user_quality_index_table():
    """Create user_quality_index table if it does not exist (additive schema only).

    This is idempotent — safe to call on every startup.
    """
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_quality_index (
                secret_id       VARCHAR(255) PRIMARY KEY,
                mean_score      REAL NOT NULL,
                tour_count      INTEGER NOT NULL DEFAULT 0,
                last_scored_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def update_user_index(secret_id: str, tour_score: float) -> None:
    """Update the running average for a user after a tour is scored.

    Uses incremental mean: new_mean = old_mean + (score - old_mean) / new_count.
    This avoids re-reading all historical scores.

    Args:
        secret_id: The user's secret_id (from tour_requests/users table).
        tour_score: The total tour score from the rubric scorer.
    """
    if not secret_id or tour_score is None:
        return

    conn = _get_connection()
    try:
        cur = conn.cursor()
        # Upsert with incremental mean calculation
        cur.execute("""
            INSERT INTO user_quality_index (secret_id, mean_score, tour_count, last_scored_at)
            VALUES (%s, %s, 1, NOW())
            ON CONFLICT (secret_id) DO UPDATE SET
                mean_score = (
                    user_quality_index.mean_score * user_quality_index.tour_count + %s
                ) / (user_quality_index.tour_count + 1),
                tour_count = user_quality_index.tour_count + 1,
                last_scored_at = NOW();
        """, (secret_id, tour_score, tour_score))
        conn.commit()
        cur.close()
    except Exception as e:
        # Index update must NOT block delivery
        print(f"[USER_INDEX] WARNING: Could not update user index: {e}")
    finally:
        conn.close()


def get_user_index(secret_id: str) -> Optional[Dict]:
    """Internal-only: retrieve a user's quality index.

    Returns None if user has no scored tours.

    THIS IS NOT AN ENDPOINT. There is no route that calls this.
    It exists for internal admin queries and future review-solicitation logic.
    """
    if not secret_id:
        return None

    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT mean_score, tour_count, last_scored_at
            FROM user_quality_index
            WHERE secret_id = %s;
        """, (secret_id,))
        row = cur.fetchone()
        cur.close()
        if row:
            return {
                "secret_id": secret_id,
                "mean_score": round(row[0], 2),
                "tour_count": row[1],
                "last_scored_at": row[2].isoformat() if row[2] else None,
            }
        return None
    finally:
        conn.close()


def record_author_edit_score(
    secret_id: str,
    tour_id: int,
    score: float,
    delta: Optional[dict] = None,
) -> None:
    """Record that an author edit scored below threshold — INTERNAL ONLY.

    This is the "we should know about this" record Michael asked for.
    Complete: score, delta (which stops changed band), but NEVER surfaces
    to the author.

    The record goes into author_edit_scores (separate from user_quality_index)
    so there is no path from client → this data.
    """
    if not secret_id or score is None:
        return

    conn = _get_connection()
    try:
        cur = conn.cursor()
        import json
        cur.execute("""
            INSERT INTO author_edit_scores
                (secret_id, tour_id, score, delta, recorded_at)
            VALUES (%s, %s, %s, %s, NOW());
        """, (
            secret_id,
            tour_id,
            round(score, 2),
            json.dumps(delta) if delta else None,
        ))
        conn.commit()
        cur.close()
        print(
            f"[AUTHOR_EDIT] Recorded below-threshold edit: "
            f"secret_id={secret_id[:8]}... tour_id={tour_id} score={score:.1f}"
        )
    except Exception as e:
        # Recording must NOT block delivery
        print(f"[AUTHOR_EDIT] WARNING: Could not record edit score: {e}")
    finally:
        conn.close()


def ensure_author_edit_scores_table():
    """Create author_edit_scores table if it does not exist (additive schema only).

    Stores internal-only records of author edits that scored below threshold.
    No user-facing endpoint ever reads this table.
    """
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS author_edit_scores (
                id              SERIAL PRIMARY KEY,
                secret_id       VARCHAR(255) NOT NULL,
                tour_id         INTEGER,
                score           REAL NOT NULL,
                delta           JSONB,
                recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_author_edit_scores_secret_id
            ON author_edit_scores (secret_id);
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()
