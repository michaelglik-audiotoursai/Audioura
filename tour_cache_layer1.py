"""
Tour Cache Layer 1 — exact-match Postgres cache for generated tours.
======================================================================
Caches tour content by a deterministic key (location + tour_type + total_stops).
L1 = exact match only. L2 fuzzy matching is deferred to New Architecture.
"""
import hashlib
import logging
import psycopg2
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _cache_key(location: str, tour_type: str, total_stops: int) -> str:
    """Generate deterministic cache key: SHA256 of '{location}|{tour_type}|{total_stops}'."""
    raw = f"{location.strip().lower()}|{tour_type.strip().lower()}|{total_stops}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_table(conn) -> None:
    """Create tour_cache table if it doesn't exist (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tour_cache (
                cache_key VARCHAR(64) PRIMARY KEY,
                location TEXT NOT NULL,
                tour_type TEXT NOT NULL,
                total_stops INTEGER NOT NULL,
                tour_content TEXT NOT NULL,
                spine_json TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                hit_count INTEGER DEFAULT 0
            )
        """)
    conn.commit()


def get_cached_tour(
    location: str, tour_type: str, total_stops: int, db_url: str
) -> Optional[str]:
    """Look up an exact-match cached tour.

    Returns the cached tour_content string, or None if not found.
    """
    key = _cache_key(location, tour_type, total_stops)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tour_cache SET hit_count = hit_count + 1 WHERE cache_key = %s RETURNING tour_content",
                (key,),
            )
            row = cur.fetchone()
            conn.commit()
        conn.close()
        if row:
            logger.info(f"Cache HIT: {location} / {tour_type} / {total_stops}")
            return row[0]
        logger.info(f"Cache MISS: {location} / {tour_type} / {total_stops}")
        return None
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
        return None


def store_tour(
    location: str,
    tour_type: str,
    total_stops: int,
    tour_content: str,
    db_url: str,
    spine_json: Optional[str] = None,
) -> bool:
    """Store (upsert) a tour in the cache. Returns True on success."""
    key = _cache_key(location, tour_type, total_stops)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tour_cache (cache_key, location, tour_type, total_stops, tour_content, spine_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE
                SET tour_content = EXCLUDED.tour_content,
                    spine_json = EXCLUDED.spine_json,
                    created_at = NOW()
                """,
                (key, location, tour_type, total_stops, tour_content, spine_json),
            )
        conn.commit()
        conn.close()
        logger.info(f"Cache STORE: {location} / {tour_type} / {total_stops} (key={key[:12]}…)")
        return True
    except Exception as e:
        logger.error(f"Cache store error: {e}")
        return False
