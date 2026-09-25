"""
Tour Cache Layer 1 — bucketed Postgres cache for generated tours.
======================================================================
Caches tour content by a deterministic key (normalised location + tour_type + stop BUCKET).
L1 = exact match on that key. L2 fuzzy matching is deferred to New Architecture.

Two independent causes of paying twice for one tour, fixed together:
LOCAL-500 normalises the location STRING; LOCAL-494 buckets the STOP COUNT.
They multiply — one venue with 3 phrasings x 3 stop counts was 9 paid
generations and is now 1.

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
[LOCAL-494 / D581] total_stops used to be part of the key, so the SAME venue at
4 stops and at 5 stops were two unrelated paid generations. We now key on a stop
BUCKET, cache the LARGEST count generated in that bucket, and TRIM on delivery to
the number the caller asked for. One generation therefore serves every request
whose count falls in the same bucket. The full stop-pool design is LOCAL-495; this
is step one only.
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


# ── Stop bucketing (LOCAL-494 / D581) ────────────────────────────────────────
#
# Buckets collapse nearby stop counts onto ONE cached generation. The cache
# stores the bucket's MAX count; delivery trims down to the requested count.
#
#   1-3  -> 3     small tours (a quick walk, a couple of rooms)
#   4-6  -> 6     the common museum/restaurant range
#   7-10 -> 10    long tours
#   11+  -> exact each large count keeps its own entry
#
# Why these edges: the cheapest thing to trim is a stop the listener never
# reaches, and trimming only ever REMOVES trailing stops, never fabricates. A
# bucket therefore has to be a run of counts where generating the ceiling and
# trimming down reads as well as generating the exact count would have. 1-3 /
# 4-6 / 7-10 are the three bands Michael's requests actually cluster in; beyond
# 10 the tours are rare and long enough that trimming a 20-stop tour to 11 wastes
# most of a paid generation, so 11+ stays exact. The ceiling (3/6/10) is what we
# generate and cache; every smaller count in the band is served by trimming it.
def _stop_bucket(total_stops: int) -> int:
    """Collapse a requested stop count onto the ceiling of its bucket.

    Returns the count that is actually generated and cached for this request.
    Requests in the same bucket share one cached generation.
    """
    try:
        n = int(total_stops)
    except (TypeError, ValueError):
        return total_stops
    if n <= 3:
        return 3
    if n <= 6:
        return 6
    if n <= 10:
        return 10
    return n  # 11+ : exact, no bucketing


def _cache_key(location: str, tour_type: str, total_stops: int) -> str:
    """Deterministic key: accent-folded location + tour_type + stop BUCKET.

    Both fixes apply, and they multiply rather than add:
      * LOCAL-500 normalises the location string, so "Miró" and "Miro" are one venue.
      * LOCAL-494 buckets the stop count, so 4 and 6 stops are one generation.
    """
    bucket = _stop_bucket(total_stops)
    raw = f"{_normalize_location(location)}|{tour_type.strip().lower()}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _legacy_cache_key(location: str, tour_type: str, total_stops: int) -> str:
    """The pre-LOCAL-500/494 key: `.strip().lower()` and the EXACT stop count.

    Read-only fallback so entries written before either change still resolve
    (migration-by-fallback — see get_cached_tour). Never used for writes.
    """
    raw = f"{location.strip().lower()}|{tour_type.strip().lower()}|{total_stops}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Trim-on-delivery with seam repair (LOCAL-494) ────────────────────────────

_STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
# The generator's own last-stop hand-off template (generate_tour_text.py:18626):
#   "Your final stop in {venue}: {name}."
_FINAL_STOP_DIR = re.compile(r'Your final stop in (.+?):\s*(.+?)\.\s*$')
# The closing recap opener (generate_tour_text.py epilog / LOCAL-280):
#   "From {first} to {last}, you have followed the thread of ..."
_RECAP_FROM_TO = re.compile(r'\bFrom\s+(.+?)\s+to\s+(.+?),\s+you have followed the thread\b')
# The recap count clause (LOCAL-280): "That's N stop(s)" possibly "and X kilometres".
_RECAP_COUNT = re.compile(r"That's\s+\d+\s+stops?")


def _split_stops(text):
    """Return list of (stop_number:int, start_index:int) for each 'Stop N:' header."""
    return [(int(m.group(1)), m.start()) for m in _STOP_HEADER.finditer(text or '')]


def trim_tour_to_stops(tour_content: str, target_stops: int) -> str:
    """Trim a cached tour down to the first `target_stops` stops, repairing the seam.

    The cache stores the largest count in a bucket; a caller who asked for fewer
    stops gets the tour trimmed here. Trimming:

      1. Keeps stops 1..target_stops in order, dropping every later stop block.
      2. Repairs the TRAILING SEAM: the new last stop must not hand off to a stop
         that is no longer present. Its "Directions:" line (which pointed at the
         next, now-removed stop) is rewritten to the generator's own final-stop
         form — "Your final stop in {venue}: {last name}." — or dropped if the
         venue cannot be recovered.
      3. Rewrites the closing recap so it names only delivered stops: the
         "From {first} to {last}" endpoints and the "That's N stops" count are
         corrected, and any enumerated highlight clauses that name a trimmed stop
         are removed.
      4. Preserves the trailing "Sources:" block verbatim.

    If the tour already has <= target_stops stops, it is returned unchanged
    (exact-match delivery is never altered — acceptance criterion 4).
    """
    text = tour_content or ''
    stops = _split_stops(text)
    if not stops or target_stops is None or target_stops < 1:
        return text
    if len(stops) <= target_stops:
        return text  # nothing to trim — exact/undersized delivery unchanged

    kept = stops[:target_stops]
    last_num = kept[-1][0]
    first_name = _STOP_HEADER.match(text[kept[0][1]:]).group(2).strip()
    last_name = _STOP_HEADER.match(text[kept[-1][1]:]).group(2).strip()

    # Everything from the (target_stops+1)-th header onward is the removed tail,
    # which also holds the closing recap + Sources folded after the last stop.
    cut_index = stops[target_stops][1]
    head = text[:cut_index]
    tail = text[cut_index:]

    # --- Recover the trailing block (recap + Sources) from the removed tail. ---
    # The recap and "Sources:" line live AFTER the real last stop of the full
    # tour, so they are inside `tail`. We keep them but repair their content.
    sources_block = ''
    m_src = re.search(r'(?ms)^\s*Sources:\s.*\Z', tail)
    if m_src:
        sources_block = m_src.group(0).strip()

    recap_block = ''
    m_recap = _RECAP_FROM_TO.search(tail)
    if m_recap:
        # Take the recap sentence run: from "From ... thread" up to Sources.
        recap_start = m_recap.start()
        recap_end = m_src.start() if m_src else len(tail)
        recap_block = tail[recap_start:recap_end].strip()

    # --- Repair the trailing seam on the new last stop. ---
    # Find the last "Directions:" line inside the kept region and rewrite it.
    kept_region = head
    venue = _recover_venue(text)
    dir_pat = re.compile(r'(?m)^Directions:.*$')
    dir_matches = list(dir_pat.finditer(kept_region))
    if dir_matches:
        last_dir = dir_matches[-1]
        if venue:
            replacement = f"Directions: Your final stop in {venue}: {last_name}."
        else:
            # No venue recoverable — drop the dangling hand-off entirely rather
            # than point at a trimmed stop.
            replacement = ""
        head = (kept_region[:last_dir.start()] + replacement +
                kept_region[last_dir.end():])
        # Collapse any blank-line gap a dropped line would leave behind.
        head = re.sub(r'\n{3,}', '\n\n', head)

    head = head.rstrip()

    # --- Repair the closing recap so it names only delivered stops. ---
    if recap_block:
        recap_block = _repair_recap(recap_block, first_name, last_name,
                                    target_stops)

    # --- Reassemble: head + recap + Sources. ---
    parts = [head]
    if recap_block:
        parts.append(recap_block)
    if sources_block:
        parts.append(sources_block)
    return "\n\n".join(p for p in parts if p).strip() + "\n"


def _recover_venue(text):
    """Recover the venue name used by the generator's transition templates.

    Prefers the exact string that already appears in an existing
    "Your final stop in {venue}:" or "Continue through {venue} — next is"
    line, so the repaired seam matches the tour's own wording. Falls back to
    the venue in the title line ("...Audio Guided Tour: {venue}").
    """
    m = re.search(r'Your final stop in (.+?):', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'Continue through (.+?) — next is', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'(?m)^Step-by-Step Audio Guided Tour:\s*(.+?)\s*$', text)
    if m:
        # Title is "{venue}, {city}, {country}" — keep the leading venue phrase.
        return m.group(1).split(',')[0].strip()
    return ''


def _repair_recap(recap_block, first_name, last_name, target_stops):
    """Rewrite the closing recap so it names only the delivered stops.

    - "From {first} to {X}" → X becomes the new last delivered stop.
    - "That's N stops" → N becomes target_stops.
    - Any enumerated highlight clause ("— A, b, and c.") that names a stop no
      longer present is dropped down to a bare count sentence, because the
      highlights are LLM-composed and may reference a trimmed stop.
    """
    out = recap_block

    # 1. Fix the From→to endpoints.
    def _fix_from_to(m):
        return f"From {first_name} to {last_name}, you have followed the thread"
    out = _RECAP_FROM_TO.sub(_fix_from_to, out, count=1)

    # 2. Fix the "That's N stops" count.
    stop_word = "stop" if target_stops == 1 else "stops"
    out = _RECAP_COUNT.sub(f"That's {target_stops} {stop_word}", out, count=1)

    # 3. The recap enumeration ("That's N stops — clause, clause, and clause.")
    #    lists specific highlights that may name a trimmed stop. Rather than risk
    #    naming a stop we removed, reduce the count sentence to just the count.
    #    Split on the em-dash the generator uses (LOCAL-280 assembly).
    out = re.sub(
        r"(That's\s+\d+\s+stops?(?:\s+and\s+[\d.]+\s+kilometres)?)\s+—\s+[^.]*\.",
        r"\1.",
        out,
    )
    return out.strip()


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
    """Look up a cached tour by (location, tour_type, stop BUCKET).

    Tries the normalised LOCAL-500 key first. If that misses, falls back to the
    pre-normalisation legacy key so older entries still resolve (migration-by-
    fallback — no DB rewrite needed). A legacy hit is re-stored under the current
    key on the next store_tour, so the estate converges naturally.

    [LOCAL-494] The cache stores the LARGEST count generated in the bucket. If the
    caller asked for fewer stops than were cached, the tour is trimmed on delivery
    (with seam repair) here — and that trimmed delivery is still a cache HIT, not
    a generation.

    Returns the (possibly trimmed) cached tour_content string, or None if not found.
    """
    key = _cache_key(location, tour_type, total_stops)
    legacy_key = _legacy_cache_key(location, tour_type, total_stops)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tour_cache SET hit_count = hit_count + 1 "
                "WHERE cache_key = %s RETURNING tour_content, total_stops",
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
            content, cached_stops = row[0], row[1]
            bucket = _stop_bucket(total_stops)
            if cached_stops and total_stops and total_stops < cached_stops:
                # Bucket hit for a smaller count: trim down and repair the seam.
                trimmed = trim_tour_to_stops(content, total_stops)
                logger.info(
                    f"Cache HIT (trimmed {cached_stops}→{total_stops}, bucket={bucket}): "
                    f"{location} / {tour_type} / {total_stops}"
                )
                return trimmed
            logger.info(
                f"Cache HIT (bucket={bucket}): {location} / {tour_type} / {total_stops}"
            )
            return content
        logger.info(
            f"Cache MISS (bucket={_stop_bucket(total_stops)}): "
            f"{location} / {tour_type} / {total_stops}"
        )
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
    """Store (upsert) a tour in the bucketed cache. Returns True on success.

    [LOCAL-494] Entries are keyed on the stop BUCKET and must hold the LARGEST
    count in that bucket, because delivery can only trim DOWN (removing trailing
    stops), never grow a cached tour. On conflict we therefore keep whichever
    generation has the greater total_stops: a bigger generation replaces a
    smaller one, a smaller generation does NOT overwrite a bigger one.
    """
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
                    total_stops = EXCLUDED.total_stops,
                    created_at = NOW()
                WHERE EXCLUDED.total_stops > tour_cache.total_stops
                """,
                (key, location, tour_type, total_stops, tour_content, spine_json),
            )
        conn.commit()
        conn.close()
        logger.info(
            f"Cache STORE (bucket={_stop_bucket(total_stops)}): "
            f"{location} / {tour_type} / {total_stops} (key={key[:12]}…)"
        )
        return True
    except Exception as e:
        logger.error(f"Cache store error: {e}")
        return False
