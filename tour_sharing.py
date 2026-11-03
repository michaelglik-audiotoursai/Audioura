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


def generate_shareable_tour_id(location: str, tour_type: str, total_stops: int,
                               audio_tour_id=None) -> str:
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
    # [LEAD 2026-10-09] A share points at ONE tour. Two tours with the same request text
    # (Boston walking 557 vs Kiro's test copy 558) got the SAME code, and the code kept
    # pointing at the first. When the tour id is known, the code derives from it.
    if audio_tour_id is not None:
        raw = f"audio_tour:{int(audio_tour_id)}"
    else:
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

# [LOCAL-856] Has the additive audio_tour_id ensure logged its marker in THIS
# process yet? The marker is logged exactly once per process so the required
# "[LOCAL-856] shared_tours.audio_tour_id ensured" line is emitted on the
# write-side service too, without spamming it on every share.
_SHARED_TOURS_AUDIO_TOUR_ID_LOGGED = False


def _ensure_shared_tours_table(conn) -> None:
    """Create shared_tours table if not exists (idempotent)."""
    global _SHARED_TOURS_AUDIO_TOUR_ID_LOGGED
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
        # [ST-1] A share must REFERENCE the tour, not duplicate its text.
        #
        # The original design stored a detached copy of tour_text. That copy has no
        # audio (audio_tours.audio_tour holds the BYTEA), no link to translations
        # (they chain off audio_tours.original_tour_id), and it drifts the moment the
        # tour is regenerated -- so the shared version silently becomes a different
        # tour than the one Kostya rode.
        #
        # Michael's Phase 1 requires a shared tour to behave exactly like one found on
        # the home page: download the original, or translate it. That only works on a
        # real audio_tours row.
        #
        # Additive and nullable on purpose: the 3 existing rows keep working through
        # tour_text while audio_tour_id is NULL, so nothing breaks and no data is lost.
        #
        # [LOCAL-856] This is the SAME additive ALTER the read service
        # (map_delivery/app.py) now also runs at its start. The cloud 404'd because
        # only this write path created the column and the write path was never hit
        # there; ensuring it on both sides closes that gap.
        cur.execute("""
            ALTER TABLE shared_tours
            ADD COLUMN IF NOT EXISTS audio_tour_id INTEGER
        """)
    conn.commit()
    if not _SHARED_TOURS_AUDIO_TOUR_ID_LOGGED:
        _SHARED_TOURS_AUDIO_TOUR_ID_LOGGED = True
        _logger.info("[LOCAL-856] shared_tours.audio_tour_id ensured")
        print("[LOCAL-856] shared_tours.audio_tour_id ensured", flush=True)


def ensure_shared_tours_schema(db_url: str) -> bool:
    """[LOCAL-856] Run the shared_tours ensure (table + additive audio_tour_id)
    once at service start, on its own connection. Call this from the startup of
    any service that mounts the sharing endpoints, so the column exists before the
    first request rather than only on the first share. Best-effort and non-fatal:
    returns True on success, False on any error (the per-request ensure in
    store_shared_tour / get_shared_tour remains the safety net)."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_shared_tours_table(conn)
        conn.close()
        return True
    except Exception as e:  # pragma: no cover - boot-time best effort
        _logger.warning(f"[LOCAL-856] startup ensure of shared_tours skipped "
                        f"(non-fatal): {e}")
        return False


def store_shared_tour(
    tour_id: str,
    tour_text: str,
    location: str,
    tour_type: str,
    total_stops: int,
    db_url: str,
    audio_tour_id: int = None,
) -> bool:
    """Store (upsert) a shared tour. Returns True on success.

    [ST-1] `audio_tour_id` is the tour this share POINTS AT. Pass it whenever the
    caller knows it -- it is what makes download and translation work, because those
    flows operate on real audio_tours rows. It is optional so existing callers keep
    compiling; a share without it still resolves through the stored text, which is
    the pre-ST-1 behaviour and is what the 3 legacy rows rely on.
    """
    try:
        conn = psycopg2.connect(db_url)
        _ensure_shared_tours_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO shared_tours
                    (tour_id, tour_text, location, tour_type, total_stops, audio_tour_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tour_id) DO UPDATE
                SET tour_text = EXCLUDED.tour_text,
                    location = EXCLUDED.location,
                    tour_type = EXCLUDED.tour_type,
                    total_stops = EXCLUDED.total_stops,
                    -- COALESCE so a later share that does not know the tour id cannot
                    -- erase a reference an earlier one established.
                    audio_tour_id = COALESCE(EXCLUDED.audio_tour_id,
                                             shared_tours.audio_tour_id)
            """, (tour_id, tour_text, location, tour_type, total_stops, audio_tour_id))
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
                "SELECT tour_id, tour_text, location, tour_type, total_stops, created_at, share_count, audio_tour_id FROM shared_tours WHERE tour_id = %s",
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
            # [ST-1] The tour this share points at. None for the 3 legacy rows, which
            # predate the reference and still resolve through tour_text. Callers must
            # handle None rather than assume a reference exists.
            "audio_tour_id": row[7],
        }
    except Exception as e:
        _logger.error(f"Error getting shared tour {tour_id}: {e}")
        return None
