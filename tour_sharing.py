"""
Tour Sharing — shareable tour ID generation and URL building.
==============================================================
Produces deterministic, URL-safe 8-char IDs for sharing tours.
"""
import hashlib

# Base62 alphabet (URL-safe: A-Z, a-z, 0-9)
_BASE62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def _to_base62(num: int, length: int = 8) -> str:
    """Convert an integer to a base62 string of fixed length."""
    if num == 0:
        return _BASE62[0] * length
    chars = []
    while num > 0 and len(chars) < length:
        chars.append(_BASE62[num % 62])
        num //= 62
    # Pad to desired length
    while len(chars) < length:
        chars.append(_BASE62[0])
    return "".join(reversed(chars))


def generate_shareable_tour_id(location: str, tour_type: str, total_stops: int) -> str:
    """Generate a deterministic 8-char URL-safe shareable tour ID.

    The ID is derived from SHA256 of the same cache key used by tour_cache_layer1,
    then encoded as base62 (8 chars = ~47 bits of entropy).

    Args:
        location: Tour location string.
        tour_type: Tour category (museum, walking, etc.).
        total_stops: Number of stops.

    Returns:
        8-character alphanumeric string, deterministic per inputs.
    """
    raw = f"{location.strip().lower()}|{tour_type.strip().lower()}|{total_stops}"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    # Use first 6 bytes (48 bits) as integer for base62 encoding
    num = int.from_bytes(digest[:6], "big")
    return _to_base62(num, 8)


def build_share_url(tour_id: str, base_url: str = "https://audioura.io") -> str:
    """Build the full shareable URL for a tour.

    Args:
        tour_id: The 8-char shareable ID.
        base_url: Base URL (default: https://audioura.io).

    Returns:
        Full share URL: '{base_url}/tour/{tour_id}'
    """
    return f"{base_url.rstrip('/')}/tour/{tour_id}"


import logging
import psycopg2
from datetime import datetime
from typing import Optional

_logger = logging.getLogger(__name__)


def _ensure_shared_tours_table(conn) -> None:
    """Create shared_tours table if not exists (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shared_tours (
                tour_id VARCHAR(8) PRIMARY KEY,
                tour_text TEXT NOT NULL,
                location TEXT NOT NULL,
                tour_type TEXT NOT NULL,
                total_stops INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                share_count INTEGER DEFAULT 0
            )
        """)
    conn.commit()


def store_shared_tour(
    tour_id: str,
    tour_text: str,
    location: str,
    tour_type: str,
    total_stops: int,
    db_url: str,
) -> bool:
    """Store (upsert) a shared tour. Returns True on success."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_shared_tours_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO shared_tours (tour_id, tour_text, location, tour_type, total_stops)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tour_id) DO UPDATE
                SET tour_text = EXCLUDED.tour_text,
                    location = EXCLUDED.location,
                    tour_type = EXCLUDED.tour_type,
                    total_stops = EXCLUDED.total_stops
            """, (tour_id, tour_text, location, tour_type, total_stops))
        conn.commit()
        conn.close()
        _logger.info(f"Stored shared tour: {tour_id}")
        return True
    except Exception as e:
        _logger.error(f"Error storing shared tour {tour_id}: {e}")
        return False


def get_shared_tour(tour_id: str, db_url: str) -> Optional[dict]:
    """Retrieve a shared tour by ID. Returns row dict or None."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_shared_tours_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tour_id, tour_text, location, tour_type, total_stops, created_at, share_count FROM shared_tours WHERE tour_id = %s",
                (tour_id,),
            )
            row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "tour_id": row[0],
            "tour_text": row[1],
            "location": row[2],
            "tour_type": row[3],
            "total_stops": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "share_count": row[6],
        }
    except Exception as e:
        _logger.error(f"Error getting shared tour {tour_id}: {e}")
        return None
