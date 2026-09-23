"""
Tour Cache Layer 1 — exact-match Postgres cache for generated tours.
======================================================================
Caches tour content by a deterministic key (location + tour_type + total_stops).
L1 = exact match only. L2 fuzzy matching is deferred to New Architecture.

[LOCAL-500] Cache-key normalisation — the SAFE half only.
---------------------------------------------------------
`tour_cache` was storing the same venue twice when it differed only by an accent,
a comma or a double space:

    Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA   (6 hits)
    Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA   (3 hits)

Same exhibition, nine requests, two paid generations. The old key was
`SHA256(location.strip().lower() | tour_type | total_stops)` — `.lower()` was the
only normalisation, so any accent or stray punctuation minted a new venue. This is
the D243 defect class ("accent-fold every stop_corpus join") never applied to the
cache key.

The fix is STRING NORMALISATION ONLY: accent-fold, collapse whitespace, strip
meaningless punctuation, casefold. We deliberately do NOT do coordinate or
fuzzy/semantic venue matching — merging two genuinely different venues serves a
listener the wrong tour, which is far worse than paying twice. That decision is
LEAD's to make separately.
"""
import hashlib
import logging
import re
import unicodedata
import psycopg2
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Punctuation that carries no venue-identity meaning. Commas, periods and
# apostrophes (both ASCII and typographic) only ever separate or decorate; they
# never distinguish two different venues. Stripped to spaces (not deleted) so
# "Boston,MA" and "Boston, MA" both fold to "boston ma" rather than "bostonma".
_MEANINGLESS_PUNCT = re.compile(r"[,\.\u2019\u2018']")


def _fold(s: str) -> str:
    """Accent-strip, lowercase and collapse whitespace.

    'Éditions  Verve' -> 'editions verve'; 'Joan Miró' -> 'joan miro'.

    NFKD then drop combining marks, so this handles both the precomposed form
    (U+00E9) and the decomposed one (e + U+0301). Mirrors the canonical
    text_fold.fold / scope_memory._fold primitive (D243). Kept as a local copy so
    the cache layer has no import-time dependency on the gate chain.
    """
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(s).lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


def _normalize_location(location: str) -> str:
    """Normalise a venue string to a canonical form for the cache key (LOCAL-500).

    Safe, string-only normalisation:
      1. Accent-fold + casefold via NFKD  (Miró -> miro, Musée -> musee)
      2. Strip meaningless punctuation (',' '.' ''') to spaces
      3. Collapse internal whitespace

    Steps 2+3 together also normalise state/country suffix spacing:
    'Boston, MA' and 'Boston MA' both become 'boston ma'.

    Deliberately NOT done: coordinate matching, fuzzy/semantic identity, token
    reordering, or dropping words. Those can merge DIFFERENT venues; this must not.
    """
    folded = _fold(location)
    depunct = _MEANINGLESS_PUNCT.sub(" ", folded)
    return re.sub(r"\s+", " ", depunct).strip()


def _cache_key(location: str, tour_type: str, total_stops: int) -> str:
    """Deterministic, accent-folded cache key (LOCAL-500).

    SHA256 of '{normalized_location}|{tour_type}|{total_stops}'.
    """
    raw = f"{_normalize_location(location)}|{tour_type.strip().lower()}|{total_stops}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _legacy_cache_key(location: str, tour_type: str, total_stops: int) -> str:
    """The pre-LOCAL-500 key: only `.strip().lower()` on location.

    Retained solely so entries written before the normalisation change still
    resolve on read (migration-by-fallback — see get_cached_tour). Never used for
    writes; new stores always use the normalised _cache_key.
    """
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

    Tries the normalised LOCAL-500 key first. If that misses, falls back to the
    pre-LOCAL-500 legacy key so entries written before normalisation still
    resolve (migration-by-fallback — no DB rewrite needed). A legacy hit is
    re-stored under the normalised key on the next store_tour, so the estate
    converges to normalised keys naturally.

    Returns the cached tour_content string, or None if not found.
    """
    key = _cache_key(location, tour_type, total_stops)
    legacy_key = _legacy_cache_key(location, tour_type, total_stops)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tour_cache SET hit_count = hit_count + 1 WHERE cache_key = %s RETURNING tour_content",
                (key,),
            )
            row = cur.fetchone()
            if not row and legacy_key != key:
                # Fall back to a pre-normalisation entry, if one exists.
                cur.execute(
                    "UPDATE tour_cache SET hit_count = hit_count + 1 WHERE cache_key = %s RETURNING tour_content",
                    (legacy_key,),
                )
                row = cur.fetchone()
                if row:
                    logger.info(
                        f"Cache HIT (legacy key): {location} / {tour_type} / {total_stops}"
                    )
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
