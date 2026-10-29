"""wikidata_landmark_lookup.py — LOCAL-803.

A GENERAL, runtime replacement for the hand-written ``landmark_reference.py``
table of six HCMC landmarks. For a walking/landmark stop it asks Wikidata for the
place itself and returns its authoritative P625 coordinate, so pin_snap can snap
"City Hall" to the real People's Committee Building or "Thien Hau Temple" to the
Cholon temple in ANY city — not just the six that were typed out by hand.

HOW (ticket LOCAL-803):
  1. ``wbsearchentities`` by the stop name in the TOUR language AND, when the
     area implies a non-English language, the LOCAL language (so "Thien Hau
     Temple" resolves via "Chùa Bà Thiên Hậu", "Nice Opera" via "Opéra de Nice").
  2. For each candidate QID fetch its P625 coordinate and its P131 ("located in
     the administrative territorial entity") chain. KEEP a candidate only when its
     P625 is INSIDE the tour's scope bbox (or, when no bbox is known, within a
     generous metro radius of the scope centre) — this is the identity guard that
     a bare-name search alone cannot give. Return that candidate's P625.
  3. Cache the (name, language, scope) → coordinate result in the existing venue
     cache DB with a TTL, so a repeat tour costs nothing and never re-hits the API.
  4. Respect Wikidata's limits: ONE in-flight request at a time (a process-wide
     lock), a contactable User-Agent, and 429/5xx backoff with Retry-After. A 429
     is retried, never surfaced as "no landmark" — so a rate limit never drops a
     stop (the caller then keeps the shipped pin or falls back to the table).

The network layer is INJECTABLE (``fetch_fn``) so the module is unit-tested with
recorded Wikidata responses, fully offline. The live default reuses
``venue_resolver._request_with_backoff`` (the battle-tested 429/Retry-After path)
and ``venue_resolver._USER_AGENT``.
"""
from __future__ import annotations

import math
import os
import re
import threading
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "lookup",
    "local_lang_for_scope",
    "WIKIDATA_API",
    "LANDMARK_CACHE_TTL_DAYS",
]

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# A landmark's P625 coordinate is stable (a building does not move), so a long
# positive TTL is safe; a MISS (no in-scope landmark found) gets a short TTL so a
# transient emptiness is retried soon. Both are overridable via env.
LANDMARK_CACHE_TTL_DAYS = int(os.environ.get("LANDMARK_CACHE_TTL_DAYS", "90"))
LANDMARK_CACHE_NEGATIVE_TTL_DAYS = int(
    os.environ.get("LANDMARK_CACHE_NEGATIVE_TTL_DAYS", "3"))

# One in-flight Wikidata request across the whole process — Wikidata throttles a
# concurrent pipeline hard, and the ticket requires a single in-flight request.
_WIKIDATA_LOCK = threading.Lock()

# When no scope bbox is known, keep a candidate whose P625 is within this many km
# of the scope centre. Generous on purpose: this is an identity guard against a
# same-name place in ANOTHER city, not a walkability test (GEO-CHECK does that).
_METRO_RADIUS_KM = 35.0


# ───────────────────────────── text helpers ─────────────────────────────────

def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# City/country keywords → the primary local Wikipedia/Wikidata language code. Used
# ONLY to add a SECOND wbsearchentities pass in the local language; a wrong guess
# merely means we search in the tour language alone. Mirrors the small table in
# serper_plus_research so the two stay aligned.
_LOCAL_LANG_TABLE = [
    (("france", "french", "nice", "paris", "lyon", "marseille", "riviera"), "fr"),
    (("italy", "italian", "rome", "florence", "venice", "milan", "naples"), "it"),
    (("spain", "spanish", "madrid", "barcelona", "seville", "valencia"), "es"),
    (("germany", "german", "berlin", "munich", "hamburg", "cologne"), "de"),
    (("portugal", "portuguese", "lisbon", "porto"), "pt"),
    (("netherlands", "dutch", "amsterdam", "rotterdam", "hague"), "nl"),
    (("vietnam", "vietnamese", "hanoi", "ho chi minh", "saigon", "hue", "hoi an"),
     "vi"),
    (("japan", "japanese", "tokyo", "kyoto", "osaka"), "ja"),
    (("china", "chinese", "beijing", "shanghai", "guangzhou"), "zh"),
    (("russia", "russian", "moscow", "petersburg"), "ru"),
    (("greece", "greek", "athens", "thessaloniki"), "el"),
    (("poland", "polish", "warsaw", "krakow"), "pl"),
    (("sweden", "swedish", "stockholm"), "sv"),
    (("thailand", "thai", "bangkok", "chiang mai"), "th"),
    (("korea", "korean", "seoul", "busan"), "ko"),
]


def local_lang_for_scope(scope: str) -> str:
    """Best-effort local-language code for a scope/city string ('' when none or
    English). "Old Saigon walking tour, District 1, Ho Chi Minh City" → 'vi'."""
    c = (scope or "").lower()
    for keys, code in _LOCAL_LANG_TABLE:
        if any(k in c for k in keys):
            return code
    return ""


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _in_bbox(pt: Tuple[float, float],
             bbox: Optional[List[float]]) -> bool:
    """True when ``pt`` (lat, lng) is inside ``bbox`` = [south, north, west, east]
    (Nominatim jsonv2 order). A malformed bbox yields False so the caller falls
    back to the radius test rather than trusting a broken box."""
    if not bbox or len(bbox) < 4:
        return False
    try:
        south, north, west, east = (float(bbox[0]), float(bbox[1]),
                                     float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return False
    lat, lng = pt
    return south <= lat <= north and west <= lng <= east


# [LOCAL-813 Cause A] Degrees to pad a geocoded neighbourhood bbox by before the
# in-scope test. ~0.02° ≈ 2 km at mid latitudes — enough to admit a landmark on
# the very edge of a razor-tight Nominatim neighbourhood box (Eikan-dō Zenrin-ji
# sat ~380 m north of the "Higashiyama, Kyoto" box), far too small to admit a
# same-name place in another city (that is the metro-radius guard's job).
_BBOX_PAD_DEG = float(os.environ.get("LANDMARK_BBOX_PAD_DEG", "0.02"))


def _pad_bbox(bbox: Optional[List[float]], pad_deg: float) -> Optional[List[float]]:
    """Return ``bbox`` = [south, north, west, east] grown by ``pad_deg`` on every
    side, or the input unchanged when it is missing/malformed/pad<=0."""
    if not bbox or len(bbox) < 4 or pad_deg <= 0:
        return bbox
    try:
        south, north, west, east = (float(bbox[0]), float(bbox[1]),
                                     float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return bbox
    return [south - pad_deg, north + pad_deg, west - pad_deg, east + pad_deg]


# ──────────────────────── live Wikidata fetch layer ─────────────────────────

def _default_fetch(action: str, params: Dict) -> Optional[Dict]:
    """The LIVE Wikidata call: a single in-flight GET with the shared
    User-Agent and the venue_resolver 429/Retry-After backoff. Returns the parsed
    JSON dict, or None on a hard failure (exhausted retries / network error / a
    429 that never cleared). ``action`` is 'wbsearchentities' or 'wbgetentities'
    (for logging only; the action is also in ``params``).

    Serialised on ``_WIKIDATA_LOCK`` so only ONE Wikidata request is in flight at
    a time across the process, as the ticket requires.

    OFFLINE GUARD: the live network path fires only when ``LANDMARK_LIVE_LOOKUP``
    is truthy (set on the production tour path). The unit suite is OFFLINE
    (conftest) and never sets it, so ``lookup`` deterministically returns None
    here and the caller falls back to the offline table — tests that exercise the
    live logic inject their own ``fetch_fn`` (recorded responses), which bypasses
    this guard entirely.
    """
    if str(os.environ.get("LANDMARK_LIVE_LOOKUP", "")).strip().lower() \
            not in ("1", "true", "yes", "on"):
        return None
    try:
        import requests  # noqa: F401
        from venue_resolver import _request_with_backoff, _USER_AGENT
    except Exception:
        return None
    with _WIKIDATA_LOCK:
        resp = _request_with_backoff(
            WIKIDATA_API, params=params,
            headers={"User-Agent": _USER_AGENT}, timeout=12,
            host_for_cold="https://www.wikidata.org",
            label=f"wikidata_landmark:{action}")
    if resp is None or getattr(resp, "status_code", None) != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def _search_entities(name: str, language: str,
                     fetch_fn: Callable) -> List[str]:
    """wbsearchentities → list of candidate QIDs (best first), [] on failure."""
    data = fetch_fn("wbsearchentities", {
        "action": "wbsearchentities", "search": name,
        "language": language or "en", "uselang": language or "en",
        "type": "item", "format": "json", "limit": 8,
    })
    if not data:
        return []
    out: List[str] = []
    for hit in (data.get("search") or []):
        qid = hit.get("id")
        if qid:
            out.append(qid)
    return out


def _entity_p625(qid: str, fetch_fn: Callable
                 ) -> Optional[Tuple[float, float]]:
    """P625 coordinate (lat, lng) for a QID, or None when absent/unavailable."""
    data = fetch_fn("wbgetentities", {
        "action": "wbgetentities", "ids": qid, "props": "claims",
        "format": "json",
    })
    if not data:
        return None
    ent = (data.get("entities") or {}).get(qid) or {}
    claims = ent.get("claims") or {}
    for claim in claims.get("P625", []) or []:
        val = (((claim.get("mainsnak") or {}).get("datavalue") or {})
               .get("value") or {})
        lat = val.get("latitude")
        lng = val.get("longitude")
        if lat is not None and lng is not None and (lat or lng):
            try:
                return (float(lat), float(lng))
            except (TypeError, ValueError):
                continue
    return None


# ─────────────────────────────── cache layer ────────────────────────────────

_CACHE_TABLE_ENSURED = False


def _cache_key(name: str, language: str, scope: str) -> str:
    """A stable key for a (name, language, scope) lookup — folded so trivial case
    / accent / whitespace variants share a cache row."""
    return f"{_fold(name)}|{(language or 'en').lower()}|{_fold(scope)}"


def _ensure_cache_table(conn) -> bool:
    """Create the landmark coord-cache table if absent. Returns True on success.
    A dedicated small table (keyed by name+lang+scope, not by QID) lives in the
    SAME venue-cache DB as venue_corpus — the "existing venue cache table" the
    ticket points at — so it shares the connection, TTL discipline and expiry
    index, without overloading the QID-keyed corpus rows."""
    global _CACHE_TABLE_ENSURED
    if _CACHE_TABLE_ENSURED:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS landmark_coord_cache (
                    cache_key   TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    language    VARCHAR(10),
                    scope       TEXT,
                    qid         VARCHAR(20),
                    lat         DOUBLE PRECISION,
                    lng         DOUBLE PRECISION,
                    found       BOOLEAN NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at  TIMESTAMP NOT NULL
                )
            """)
            try:
                conn.commit()
            except Exception:
                pass
        try:
            from db_safe_ddl import safe_ddl
            safe_ddl(
                conn,
                "CREATE INDEX IF NOT EXISTS idx_landmark_coord_cache_expires "
                "ON landmark_coord_cache(expires_at)",
                needed_check_sql=(
                    "SELECT 1 WHERE NOT EXISTS ("
                    "  SELECT 1 FROM pg_indexes "
                    "  WHERE tablename = 'landmark_coord_cache' "
                    "    AND indexname = 'idx_landmark_coord_cache_expires')"),
                label="LOCAL-803")
        except Exception:
            pass
        _CACHE_TABLE_ENSURED = True
        return True
    except Exception as e:
        print(f"  [landmark_cache] table creation failed (non-fatal): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def _cache_get(name: str, language: str, scope: str
               ) -> Optional[Tuple[Optional[Tuple[float, float]], str]]:
    """Return a cached result: ``((lat,lng)|None, qid)`` when a non-expired row
    exists (the coord is None for a cached MISS), else None (true cache miss).
    Reuses venue_resolver's DB connection factory so the landmark cache lives in
    the same venue-cache database. Silent no-op when no DB is configured."""
    try:
        from venue_resolver import _get_db_connection
    except Exception:
        return None
    conn = _get_db_connection()
    if not conn:
        return None
    try:
        if not _ensure_cache_table(conn):
            return None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT lat, lng, found, qid FROM landmark_coord_cache
                WHERE cache_key = %s AND expires_at > NOW()
            """, (_cache_key(name, language, scope),))
            row = cur.fetchone()
        if not row:
            return None
        lat, lng, found, qid = row
        if found and lat is not None and lng is not None:
            return ((float(lat), float(lng)), qid or "")
        return (None, qid or "")
    except Exception as e:
        print(f"  [landmark_cache] read error (non-fatal): {e}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _cache_put(name: str, language: str, scope: str,
               coord: Optional[Tuple[float, float]], qid: str) -> None:
    """Store a lookup result (a hit with coord+qid, or a MISS with coord=None).
    Positive results get the long TTL; a MISS gets the short negative TTL so a
    transient emptiness is retried soon. Silent no-op when no DB is configured."""
    try:
        from venue_resolver import _get_db_connection
    except Exception:
        return
    conn = _get_db_connection()
    if not conn:
        return
    from datetime import datetime, timedelta
    found = coord is not None
    ttl = (LANDMARK_CACHE_TTL_DAYS if found
           else LANDMARK_CACHE_NEGATIVE_TTL_DAYS)
    expires_at = datetime.utcnow() + timedelta(days=ttl)
    lat = coord[0] if coord else None
    lng = coord[1] if coord else None
    try:
        if not _ensure_cache_table(conn):
            return
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO landmark_coord_cache
                    (cache_key, name, language, scope, qid, lat, lng, found,
                     expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    qid = EXCLUDED.qid, lat = EXCLUDED.lat, lng = EXCLUDED.lng,
                    found = EXCLUDED.found, created_at = CURRENT_TIMESTAMP,
                    expires_at = EXCLUDED.expires_at
            """, (_cache_key(name, language, scope), name,
                  (language or "en").lower(), scope, qid or None,
                  lat, lng, found, expires_at))
            try:
                conn.commit()
            except Exception:
                pass
    except Exception as e:
        print(f"  [landmark_cache] write error (non-fatal): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ────────────────────────────── public lookup ───────────────────────────────

def lookup(name: str,
           scope: str = "",
           scope_center: Optional[Tuple[float, float]] = None,
           scope_bbox: Optional[List[float]] = None,
           tour_language: str = "en",
           fetch_fn: Optional[Callable] = None,
           use_cache: bool = True,
           ) -> Optional[Tuple[float, float, str, str]]:
    """Resolve a landmark NAME to its authoritative Wikidata P625 coordinate.

    Returns ``(lat, lng, "wikidata_p625", qid)`` for the first candidate whose
    P625 lies inside the tour's scope (bbox when given, else within the metro
    radius of ``scope_center``), or None when no in-scope landmark is found OR
    Wikidata could not be reached (the caller then keeps the shipped pin or falls
    back to the offline table).

    Queries ``wbsearchentities`` in the TOUR language and — when the scope implies
    a non-English local language — the LOCAL language too, so the place resolves
    by its own-language name. Results are cached by (name, language, scope) with a
    TTL in the venue-cache DB.

    ``fetch_fn(action, params) -> dict|None`` is the injectable network seam used
    by the tests (recorded responses). The live default is ``_default_fetch``
    (single in-flight, UA, 429 backoff).
    """
    if not (name or "").strip():
        return None
    fetch = fetch_fn or _default_fetch
    _net_default = fetch_fn is None
    langs: List[str] = []
    for lg in (tour_language or "en", local_lang_for_scope(scope)):
        lg = (lg or "").strip().lower()
        if lg and lg not in langs:
            langs.append(lg)
    if not langs:
        langs = ["en"]

    # Cache key is per LANGUAGE-SET + scope; use the primary (first) language as
    # the stored language tag so repeat tours in the same language share the row.
    primary_lang = langs[0]
    if use_cache and _net_default:
        cached = _cache_get(name, primary_lang, scope)
        if cached is not None:
            coord, qid = cached
            if coord is None:
                return None
            return (coord[0], coord[1], "wikidata_p625", qid)

    def _in_scope(pt: Tuple[float, float]) -> bool:
        if scope_bbox:
            # [LOCAL-813 Cause A] The scope bbox is the GEOCODER's extent for the
            # named neighbourhood ("Higashiyama, Kyoto"), and Nominatim draws it
            # razor-tight — Eikan-dō Zenrin-ji (a genuine Higashiyama temple) sits
            # ~380 m north of the box's north edge and was rejected, so the stop
            # fell to the generic geocoder and shipped 343 m off. A landmark on the
            # NEIGHBOURHOOD EDGE is still in scope: pad the box by a small margin
            # (~2 km) before the test. The identity guard against a same-name place
            # in ANOTHER city stays the metro-radius test below (and pin_snap's own
            # centroid / scope-sanity bounds), which a 2 km pad never reaches.
            if _in_bbox(pt, _pad_bbox(scope_bbox, _BBOX_PAD_DEG)):
                return True
            # Still outside even the padded box. When a scope centre is known, fall
            # back to the metro-radius identity test rather than a hard reject —
            # the box can be mis-sized (a point geocode returns a tiny box), and the
            # radius is the real cross-city guard. With no centre, reject.
            if scope_center:
                return _haversine_km(pt, scope_center) <= _METRO_RADIUS_KM
            return False
        if scope_center:
            return _haversine_km(pt, scope_center) <= _METRO_RADIUS_KM
        # No scope signal at all → cannot verify identity; accept the first P625
        # (the caller's own centroid / scope-sanity bounds in pin_snap still
        # apply on the live path). This matches the old table's trust model.
        return True

    seen_qids: set = set()
    hit: Optional[Tuple[float, float, str]] = None  # (lat,lng,qid)
    reached = False  # did ANY search call come back (not a hard network failure)?

    for lang in langs:
        qids = _search_entities(name, lang, fetch)
        if qids:
            reached = True
        for qid in qids:
            if qid in seen_qids:
                continue
            seen_qids.add(qid)
            pt = _entity_p625(qid, fetch)
            if pt is None:
                # Could be "no P625" or a network failure; either way try the
                # next candidate. (A hard failure on EVERY call leaves hit=None
                # and reached possibly False → treated as unreachable below.)
                continue
            reached = True
            if _in_scope(pt):
                hit = (pt[0], pt[1], qid)
                break
        if hit:
            break

    if hit:
        if use_cache and _net_default:
            _cache_put(name, primary_lang, scope, (hit[0], hit[1]), hit[2])
        return (hit[0], hit[1], "wikidata_p625", hit[2])

    # No in-scope landmark. Cache a MISS (short TTL) ONLY when Wikidata actually
    # answered — a hard-unreachable lookup must NOT be cached as "no landmark",
    # so the caller can fall back and a later tour retries.
    if reached and use_cache and _net_default:
        _cache_put(name, primary_lang, scope, None, "")
    return None
