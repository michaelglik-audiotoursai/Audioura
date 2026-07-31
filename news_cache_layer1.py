"""
News Cache Layer 1 — exact-match Postgres cache for generated news audio.
==========================================================================
Caches the finished audio ZIP by a deterministic key derived from the article
text content + major_points_count. This ensures:
  - Same article text → same cache entry (URL-agnostic; handles republishing)
  - Changed article content → cache miss (handles content updates at same URL)
  - Different major_points_count → different cache entry (different narration shape)

TTL: 24 hours by default. News is time-sensitive; stale audio is worse than
paying twice. The TTL is configurable via NEWS_CACHE_TTL_HOURS env var.

Mirrors tour_cache_layer1.py — one cache concept, not two.
"""
import hashlib
import logging
import os
import psycopg2
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# TTL in hours — news articles go stale; default 24h is conservative.
NEWS_CACHE_TTL_HOURS = int(os.getenv("NEWS_CACHE_TTL_HOURS", "24"))


def _cache_key(article_text: str, major_points_count: int) -> str:
    """Generate deterministic cache key: SHA256 of '{normalized_text}|{major_points_count}'.

    Normalization: strip + collapse whitespace. This handles trivial formatting
    differences without changing semantic content.
    """
    import re
    normalized = re.sub(r'\s+', ' ', article_text.strip())
    raw = f"{normalized}|{major_points_count}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ensure_table(conn) -> None:
    """Create news_cache table if it doesn't exist (idempotent).
    Production should use migration/sql/008_news_cache.sql.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news_cache (
                cache_key VARCHAR(64) PRIMARY KEY,
                article_id VARCHAR(255) NOT NULL,
                article_text_hash VARCHAR(64) NOT NULL,
                major_points_count INTEGER NOT NULL DEFAULT 0,
                request_string TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                hit_count INTEGER DEFAULT 0,
                content_length INTEGER DEFAULT 0
            )
        """)
        # Index for TTL expiration queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_cache_created_at
            ON news_cache (created_at)
        """)
    conn.commit()


def get_cached_news(
    article_text: str,
    major_points_count: int,
    db_url: str,
) -> Optional[Tuple[str, bytes]]:
    """Look up a cached news article by content hash.

    Returns (article_id, audio_zip_bytes) if found and not expired, else None.
    The caller uses the article_id to reference the existing news_audios row.
    """
    key = _cache_key(article_text, major_points_count)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            # Check cache with TTL enforcement
            cur.execute(
                """
                UPDATE news_cache
                SET hit_count = hit_count + 1
                WHERE cache_key = %s
                  AND created_at > NOW() - INTERVAL '%s hours'
                RETURNING article_id
                """,
                (key, NEWS_CACHE_TTL_HOURS),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                conn.close()
                logger.info(f"[NEWS_CACHE] MISS: key={key[:12]}… (ttl={NEWS_CACHE_TTL_HOURS}h)")
                return None

            article_id = row[0]

            # Fetch the actual audio ZIP from news_audios
            cur.execute(
                "SELECT news_article FROM news_audios WHERE article_id = %s",
                (article_id,),
            )
            audio_row = cur.fetchone()
            conn.commit()
            conn.close()

            if not audio_row or audio_row[0] is None:
                # Cache entry exists but audio is gone — treat as miss
                logger.warning(f"[NEWS_CACHE] STALE: key={key[:12]}… article_id={article_id} has no audio")
                return None

            audio_bytes = audio_row[0]
            if hasattr(audio_bytes, 'tobytes'):
                audio_bytes = audio_bytes.tobytes()
            elif not isinstance(audio_bytes, bytes):
                audio_bytes = bytes(audio_bytes)

            logger.info(
                f"[NEWS_CACHE] HIT: key={key[:12]}… article_id={article_id} "
                f"size={len(audio_bytes)} bytes"
            )
            return (article_id, audio_bytes)

    except Exception as e:
        logger.warning(f"[NEWS_CACHE] Read error: {e}")
        return None


def store_news(
    article_text: str,
    major_points_count: int,
    article_id: str,
    db_url: str,
    request_string: Optional[str] = None,
    content_length: int = 0,
) -> bool:
    """Store (upsert) a news article in the cache.

    We only store the article_id reference — the audio itself lives in news_audios.
    This avoids duplicating the (large) ZIP blob.

    Returns True on success.
    """
    key = _cache_key(article_text, major_points_count)
    text_hash = hashlib.sha256(article_text.encode("utf-8")).hexdigest()
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_cache (cache_key, article_id, article_text_hash,
                                       major_points_count, request_string, content_length, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (cache_key) DO UPDATE
                SET article_id = EXCLUDED.article_id,
                    article_text_hash = EXCLUDED.article_text_hash,
                    request_string = EXCLUDED.request_string,
                    content_length = EXCLUDED.content_length,
                    created_at = NOW(),
                    hit_count = 0
                """,
                (key, article_id, text_hash, major_points_count,
                 request_string, content_length),
            )
        conn.commit()
        conn.close()
        logger.info(
            f"[NEWS_CACHE] STORE: key={key[:12]}… article_id={article_id} "
            f"points={major_points_count}"
        )
        return True
    except Exception as e:
        logger.error(f"[NEWS_CACHE] Store error: {e}")
        return False


def invalidate_expired(db_url: str) -> int:
    """Remove cache entries older than TTL. Returns count of removed entries.

    Called opportunistically — not on every request (performance).
    """
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM news_cache
                WHERE created_at <= NOW() - INTERVAL '%s hours'
                RETURNING cache_key
                """,
                (NEWS_CACHE_TTL_HOURS,),
            )
            removed = cur.rowcount
        conn.commit()
        conn.close()
        if removed > 0:
            logger.info(f"[NEWS_CACHE] Expired {removed} entries (TTL={NEWS_CACHE_TTL_HOURS}h)")
        return removed
    except Exception as e:
        logger.error(f"[NEWS_CACHE] Expiration error: {e}")
        return 0
