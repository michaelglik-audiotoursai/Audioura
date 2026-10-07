"""
Stop Pool Store (LOCAL-590 / LOCAL-495) — reuse the stops already written.
==========================================================================
The whole-tour cache (`tour_cache_layer1`) keys on (venue, type, stop BUCKET)
and reuses a tour ONLY when a later request falls in the same bucket; a bigger
request is a full regeneration and no stop is ever reused across sizes. Michael,
2026-09-23: *"if somebody asks to generate a tour of the same venue that we
already had generated, we should use the material we had."*

This module is the **stop POOL** that makes that reuse real. A stop is stored
once per (venue identity, tour_type, cache version) as an **audio-independent
unit** — title, narration body, the structured fields the renderer needs
(address, coordinates, type/specialty, examples, operational details), its
sources and story elements, and a per-stop `generated_at`. A later tour of the
same place is then a SELECTION from this pool plus only the genuinely new stops.

Why audio-independent (D581.1 / the design's hard part 1.1 & 1.3):
  * **Directions and Orientation are properties of a SEQUENCE, not of a stop.**
    They change every time the stop's neighbours change, so they are NOT stored
    with the pooled stop; they are recomputed per selection by the caller (the
    single-building and outdoor assembly paths in generate_tour_text).
  * **Audio is a rendering of the stop's TEXT in one voice/engine.** It is keyed
    per rendered stop text (polly_tts_service), not per tour, so the pool stores
    only the text; audio reuse is decided downstream by matching voice+engine
    against the identical narration (LOCAL-590 step 5).
  * **Freshness is per stop, not per tour.** Each row carries `generated_at`, so
    a single stale stop can age out without discarding the whole venue's pool.

Table discipline (declared, additive, never DELETE):
  * `stop_pool` is created IF NOT EXISTS and only ever INSERTed/UPSERTed into.
    Nothing in this module issues DELETE or DROP. A superseded stop is UPDATEd
    in place (same venue+type+title) with the newer narration and a refreshed
    `generated_at`; its identity row is never removed. Retiring a generation is
    done the same way the whole-tour cache does it (LOCAL-588): bump
    TOUR_CACHE_VERSION so older rows become unreachable and age out naturally.

Venue identity (the design's hard part 1.4 / Michael's QID-first rule):
  * Prefer the resolved Wikidata QID (`venue_resolver.resolve_venue`), which is
    stable across phrasings and languages. Fall back to the SAME string
    normalisation the whole-tour cache uses (`tour_cache_layer1._normalize_location`)
    so "Miró" and "Miro" share one pool even without a QID.

The caller (generate_tour_text) owns ordering, orientation, directions and the
conclusion. This module only persists and returns the reusable stop units and
reports what it holds.
"""
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Dict, Optional

import psycopg2

logger = logging.getLogger(__name__)


# ── Pool version ─────────────────────────────────────────────────────────────
# Folded into the pool key exactly like tour_cache_layer1.TOUR_CACHE_VERSION, and
# kept in lock-step with it: a change that makes a cached WHOLE tour wrong makes a
# pooled STOP from the same code wrong too. We import the cache version so one
# bump retires both. If the import is unavailable (isolated unit test), fall back
# to a local constant with the same value.
try:
    from tour_cache_layer1 import TOUR_CACHE_VERSION as _POOL_VERSION
    from tour_cache_layer1 import _normalize_location as _normalize_location
except Exception:  # pragma: no cover - import shim for isolated tests
    _POOL_VERSION = 3

    _MEANINGLESS_PUNCT = re.compile(r"[,\.\u2019\u2018']")

    def _fold(s: str) -> str:
        if not s:
            return ""
        decomposed = unicodedata.normalize("NFKD", str(s).lower())
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", stripped).strip()

    def _normalize_location(location: str) -> str:
        folded = _fold(location)
        depunct = _MEANINGLESS_PUNCT.sub(" ", folded)
        return re.sub(r"\s+", " ", depunct).strip()


POOL_VERSION = _POOL_VERSION


# ── Venue identity ───────────────────────────────────────────────────────────

def venue_identity(location: str, qid: Optional[str] = None) -> str:
    """Return the stable pool identity for a venue.

    QID-first (Michael's rule): a resolved Wikidata QID is phrasing- and
    language-stable, so it is preferred when the caller already has one. Without
    a QID we fall back to the whole-tour cache's string normalisation so the two
    layers agree on what "the same venue" means (LOCAL-500).

    The returned string is the raw identity; `_pool_key` prefixes the version and
    tour_type. Kept separate so callers can log/compare identities directly.
    """
    if qid:
        q = str(qid).strip()
        if q:
            return f"qid:{q.upper()}"
    return f"loc:{_normalize_location(location)}"


def resolve_venue_identity(location: str, city: str = "") -> str:
    """Resolve `location` to a QID-based identity when possible, else normalise.

    Thin convenience wrapper that tries `venue_resolver.resolve_venue` and uses
    the QID if it comes back. Any failure (no network, unresolvable venue) falls
    back cleanly to the normalised-location identity — a resolver outage must not
    change which venue a stop is pooled under in a way that corrupts reuse, so a
    failed resolve is treated as "no QID", not an error.
    """
    try:
        from venue_resolver import resolve_venue
        entity = resolve_venue(location, city)
        if entity and getattr(entity, "qid", ""):
            return venue_identity(location, entity.qid)
    except Exception as e:
        logger.info(f"[POOL] venue resolve fell back to normalised location: {e}")
    return venue_identity(location)


def _pool_key(identity: str, tour_type: str) -> str:
    """Namespace a venue identity by pool version + tour_type.

    (version, identity, tour_type) is the pool's partition: all stops a venue has
    ever delivered for one tour_type under the current code live under one key.
    """
    return f"v{POOL_VERSION}|{identity}|{(tour_type or '').strip().lower()}"


# ── Delivered-tour parsing (audio-independent stop units) ────────────────────
#
# A pooled stop is extracted from the DELIVERED tour text, which is the single
# audio-independent artifact every path produces (the cache stores it too). We
# parse each "Stop N:" block into its title + the structured fields the renderer
# emits, and keep the narration BODY (the free prose) separately from the
# sequence-dependent lines (Orientation, Directions) which are NOT pooled.

_STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
# Structured field lines the renderer emits before/within a stop body.
_FIELD_LINES = {
    "address": re.compile(r'^Address:\s*(.+?)\s*$', re.M),
    "coordinates": re.compile(r'^Coordinates:\s*(.+?)\s*$', re.M),
    "type_specialty": re.compile(r'^Type/Specialty:\s*(.+?)\s*$', re.M),
    "specific_examples": re.compile(r'^Specific Examples:\s*(.+?)\s*$', re.M),
    "operational_details": re.compile(r'^(?:Operational Details|Museum Information):\s*(.+?)\s*$', re.M),
}
# Lines that are SEQUENCE-dependent and must NOT be pooled with the stop.
_SEQ_LINE = re.compile(r'^(?:Orientation|Directions):\s*.*$', re.M)
_SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')
# The closing recap opener (LOCAL-280).
_RECAP_FROM_TO = re.compile(r'\bFrom\s+.+?\s+to\s+.+?,\s+you have followed the thread\b')


def _strip_title_decorations(raw_title: str) -> str:
    """Return the bare stop title from a 'Stop N:' header value.

    The header may carry ' by {artist}' and ', {year}' decorations
    (generate_tour_text render loop). The pool keys on the bare title so the same
    artwork is one pooled stop regardless of how the decoration rendered; the
    artist/year are preserved separately in the stored unit.
    """
    title = raw_title
    # Strip a trailing ", 1888"-style year.
    m_year = re.search(r',\s*(\d{3,4})\s*$', title)
    year = m_year.group(1) if m_year else ""
    if m_year:
        title = title[:m_year.start()].rstrip()
    # Strip a trailing " by {artist}".
    artist = ""
    m_artist = re.search(r'\s+by\s+(.+?)\s*$', title)
    if m_artist:
        artist = m_artist.group(1).strip()
        title = title[:m_artist.start()].rstrip()
    return title, artist, year


def parse_delivered_stops(tour_content: str) -> List[Dict]:
    """Parse a delivered tour into a list of audio-independent stop units.

    Each returned dict carries:
        title                bare stop title (no artist/year decoration)
        artist, year         decoration recovered from the header (may be "")
        address, coordinates, type_specialty, specific_examples,
        operational_details  structured renderer fields (strings; "" if absent)
        narration            the free-prose BODY of the stop, with the
                             sequence-dependent Orientation/Directions lines and
                             the structured field lines removed — this is the
                             reusable, audio-independent text.
        raw_block            the full original block (kept for exact-reuse audio
                             matching when a stop is served unchanged).

    The closing recap and the trailing Sources block belong to the tour as a
    whole, not to a stop, so they are excluded from every unit.
    """
    text = tour_content or ""
    headers = list(_STOP_HEADER.finditer(text))
    if not headers:
        return []

    # The region that holds stop bodies ends at the recap or Sources, whichever
    # comes first after the last stop header.
    tail_cut = len(text)
    m_recap = _RECAP_FROM_TO.search(text, headers[-1].end())
    if m_recap:
        tail_cut = m_recap.start()
    m_src = _SOURCES_LINE.search(text)
    if m_src and m_src.start() < tail_cut:
        tail_cut = m_src.start()

    units = []
    for idx, hdr in enumerate(headers):
        start = hdr.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else tail_cut
        block = text[hdr.start():end].strip()
        body_region = text[start:end]

        title, artist, year = _strip_title_decorations(hdr.group(2).strip())

        unit = {
            "title": title,
            "artist": artist,
            "year": year,
            "raw_block": block,
        }
        # Pull structured fields.
        for field_name, pat in _FIELD_LINES.items():
            m = pat.search(body_region)
            unit[field_name] = m.group(1).strip() if m else ""

        # Narration = body with structured field lines AND sequence lines removed.
        narration = body_region
        for pat in _FIELD_LINES.values():
            narration = pat.sub("", narration)
        narration = _SEQ_LINE.sub("", narration)
        # Drop any trailing recap/sources that leaked into the last block.
        narration = _RECAP_FROM_TO.split(narration)[0]
        narration = _SOURCES_LINE.sub("", narration)
        unit["narration"] = re.sub(r'\n{3,}', '\n\n', narration).strip()

        units.append(unit)
    return units


# ── Schema (additive; never DELETE) ──────────────────────────────────────────

def _ensure_table(conn) -> None:
    """Create the additive `stop_pool` table if absent (idempotent).

    Declared here (LOCAL-590 deliverable 1). Primary key is
    (pool_key, title_norm) so the same artwork/subject under one
    (version, venue, tour_type) is exactly one pooled row. Nothing in this module
    ever DELETEs or DROPs; a superseded stop is UPDATEd in place.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_pool (
                pool_key TEXT NOT NULL,
                title_norm TEXT NOT NULL,
                venue_identity TEXT NOT NULL,
                tour_type TEXT NOT NULL,
                pool_version INTEGER NOT NULL,
                title TEXT NOT NULL,
                artist TEXT DEFAULT '',
                year TEXT DEFAULT '',
                narration TEXT NOT NULL,
                raw_block TEXT,
                address TEXT DEFAULT '',
                coordinates TEXT DEFAULT '',
                type_specialty TEXT DEFAULT '',
                specific_examples TEXT DEFAULT '',
                operational_details TEXT DEFAULT '',
                sources_json TEXT,
                story_elements_json TEXT,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                hit_count INTEGER DEFAULT 0,
                order_seq INTEGER DEFAULT 0,
                PRIMARY KEY (pool_key, title_norm)
            )
        """)
        # Migration path for a table created before order_seq existed.
        cur.execute("""
            ALTER TABLE stop_pool ADD COLUMN IF NOT EXISTS order_seq INTEGER DEFAULT 0
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_stop_pool_key
            ON stop_pool (pool_key)
        """)
    conn.commit()


def _title_norm(title: str) -> str:
    """Normalise a stop title for pool identity (accent-fold + collapse)."""
    return _normalize_location(title)


# ── Store ────────────────────────────────────────────────────────────────────

def store_delivered_tour(
    location: str,
    tour_type: str,
    tour_content: str,
    db_url: str,
    qid: Optional[str] = None,
    sources: Optional[List[str]] = None,
    story_elements_by_title: Optional[Dict[str, dict]] = None,
) -> int:
    """Parse a delivered tour and UPSERT each stop into the pool.

    Returns the number of stop units written (new or refreshed). Additive only:
    an existing title is UPDATEd in place with the newer narration + a refreshed
    `generated_at`; no row is ever removed. `sources` (tour-level source URLs)
    are stored on each stop as a reasonable default; `story_elements_by_title`
    (keyed by bare title) overrides per stop when the caller has them.
    """
    identity = venue_identity(location, qid)
    pool_key = _pool_key(identity, tour_type)
    units = parse_delivered_stops(tour_content)
    if not units:
        logger.info(f"[POOL] no parseable stops in delivered tour for {identity}")
        return 0

    sources_json_default = json.dumps(sources) if sources else None
    written = 0
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            # Base offset so NEW stops in this delivery append after everything
            # already pooled for this venue, while stops already present keep
            # their earlier (MIN) position — the venue's original order is stable.
            cur.execute(
                "SELECT COALESCE(MAX(order_seq), -1) FROM stop_pool WHERE pool_key = %s",
                (pool_key,),
            )
            base_seq = (cur.fetchone() or [-1])[0] + 1
            for seq_i, u in enumerate(units):
                tnorm = _title_norm(u["title"])
                if not tnorm:
                    continue
                se = (story_elements_by_title or {}).get(u["title"])
                se_json = json.dumps(se) if se else None
                cur.execute(
                    """
                    INSERT INTO stop_pool (
                        pool_key, title_norm, venue_identity, tour_type, pool_version,
                        title, artist, year, narration, raw_block,
                        address, coordinates, type_specialty, specific_examples,
                        operational_details, sources_json, story_elements_json,
                        order_seq, generated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (pool_key, title_norm) DO UPDATE SET
                        title = EXCLUDED.title,
                        artist = EXCLUDED.artist,
                        year = EXCLUDED.year,
                        narration = EXCLUDED.narration,
                        raw_block = EXCLUDED.raw_block,
                        address = EXCLUDED.address,
                        coordinates = EXCLUDED.coordinates,
                        type_specialty = EXCLUDED.type_specialty,
                        specific_examples = EXCLUDED.specific_examples,
                        operational_details = EXCLUDED.operational_details,
                        sources_json = COALESCE(EXCLUDED.sources_json, stop_pool.sources_json),
                        story_elements_json = COALESCE(EXCLUDED.story_elements_json, stop_pool.story_elements_json),
                        order_seq = LEAST(stop_pool.order_seq, EXCLUDED.order_seq),
                        generated_at = NOW()
                    """,
                    (
                        pool_key, tnorm, identity, (tour_type or "").strip().lower(),
                        POOL_VERSION, u["title"], u["artist"], u["year"],
                        u["narration"], u["raw_block"],
                        u["address"], u["coordinates"], u["type_specialty"],
                        u["specific_examples"], u["operational_details"],
                        sources_json_default, se_json, base_seq + seq_i,
                    ),
                )
                written += 1
        conn.commit()
        conn.close()
        logger.info(f"[POOL] stored {written} stop(s) under {pool_key}")
        return written
    except Exception as e:
        logger.error(f"[POOL] store error: {e}")
        return 0


# ── Retrieve ─────────────────────────────────────────────────────────────────

def get_pool_stops(
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
) -> List[Dict]:
    """Return every pooled stop for this venue (both QID and location identity).

    Ordered by stable delivery sequence (order_seq ASC) so a caller taking "the
    best N from the pool" gets the venue's original stop order — the core stops
    first, new stops appended after — not an alphabetical or write-time accident.

    Venue-identity robustness (D582 class): resolving a Wikidata QID is a network
    call that can succeed on one generation and fail on the next, which would
    silently split one venue's pool between a `qid:...` key and a `loc:...` key —
    a stored stop then never found on reuse. To defend against that, this reads
    BOTH the QID-based pool key (when a QID is supplied) AND the normalised-
    location key, and UNIONs them (dedup by normalised title, earliest order_seq
    wins). So however the resolver behaved when a stop was stored, it is found.

    Each dict mirrors the stored unit plus `generated_at` (ISO) and `hit_count`.
    Returns [] on any error or empty pool — an empty pool is a legitimate
    "nothing reusable yet", distinct from an exception which is logged.
    """
    keys = []
    if qid:
        keys.append(_pool_key(venue_identity(location, qid), tour_type))
    loc_key = _pool_key(venue_identity(location), tour_type)
    if loc_key not in keys:
        keys.append(loc_key)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, artist, year, narration, raw_block,
                       address, coordinates, type_specialty, specific_examples,
                       operational_details, sources_json, story_elements_json,
                       generated_at, hit_count, title_norm
                FROM stop_pool
                WHERE pool_key = ANY(%s)
                ORDER BY order_seq ASC, generated_at ASC, title_norm ASC
                """,
                (keys,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"[POOL] read error: {e}")
        return []

    stops = []
    _seen_titles = set()
    for r in rows:
        tnorm = r[14]
        if tnorm in _seen_titles:
            continue  # same stop under both keys — keep the first (earliest order_seq)
        _seen_titles.add(tnorm)
        stops.append({
            "title": r[0],
            "artist": r[1] or "",
            "year": r[2] or "",
            "narration": r[3],
            "raw_block": r[4] or "",
            "address": r[5] or "",
            "coordinates": r[6] or "",
            "type_specialty": r[7] or "",
            "specific_examples": r[8] or "",
            "operational_details": r[9] or "",
            "sources": json.loads(r[10]) if r[10] else [],
            "story_elements": json.loads(r[11]) if r[11] else None,
            "generated_at": r[12].isoformat() if r[12] else None,
            "hit_count": r[13] or 0,
        })
    logger.info(f"[POOL] {len(stops)} pooled stop(s) across keys {keys}")
    return stops


def pool_titles(
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
) -> List[str]:
    """Return the bare titles currently in the pool (for selection exclusion).

    A new-stop selection must EXCLUDE pooled titles so a bigger tour adds genuinely
    new subjects rather than regenerating ones it already has (LOCAL-590 step 2).
    """
    return [s["title"] for s in get_pool_stops(location, tour_type, db_url, qid=qid)]


def bump_hit_counts(
    location: str,
    tour_type: str,
    titles: List[str],
    db_url: str,
    qid: Optional[str] = None,
) -> None:
    """Increment hit_count for the pooled stops actually reused in a delivery.

    Pure accounting (how often a pooled stop has been served); never changes
    narration or removes rows.
    """
    if not titles:
        return
    identity = venue_identity(location, qid)
    pool_key = _pool_key(identity, tour_type)
    norms = [_title_norm(t) for t in titles if _title_norm(t)]
    if not norms:
        return
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE stop_pool SET hit_count = hit_count + 1 "
                "WHERE pool_key = %s AND title_norm = ANY(%s)",
                (pool_key, norms),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[POOL] hit-count update error: {e}")
