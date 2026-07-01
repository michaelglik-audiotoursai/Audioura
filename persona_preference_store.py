"""
Persona Preference Store — Postgres-backed user persona persistence.
=====================================================================
Stores and retrieves user persona preferences. Table created idempotently.
Pattern matches tour_cache_layer1.py.
"""
import logging
from typing import Optional

import psycopg2

from onboarding_preference import UserPersona

logger = logging.getLogger(__name__)


def _ensure_table(conn) -> None:
    """Create user_preferences table if not exists (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                persona TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


def save_persona(user_id: str, persona: UserPersona, db_url: str) -> bool:
    """Save (upsert) a user's persona preference. Returns True on success."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_preferences (user_id, persona, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET persona = EXCLUDED.persona, updated_at = NOW()
            """, (user_id, persona.value))
        conn.commit()
        conn.close()
        logger.info(f"Saved persona {persona.value} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving persona for {user_id}: {e}")
        return False


def get_persona(user_id: str, db_url: str) -> Optional[UserPersona]:
    """Retrieve a user's persona preference. Returns UserPersona or None."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT persona FROM user_preferences WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return UserPersona(row[0])
    except Exception as e:
        logger.error(f"Error getting persona for {user_id}: {e}")
        return None
