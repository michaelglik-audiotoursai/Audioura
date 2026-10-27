"""stop_existence_gate.py — verify stops actually exist at the claimed venue.

LOCAL-236: D127 established that stops can be invented by the model.
26 of 29 real tours had no venue_corpus when generated, so stop titles
were fabricated. This gate checks whether a stop is a real object the
venue actually holds, BEFORE narration.

A stop is VERIFIED if:
  1. venue_corpus canonical title or SPARQL work for the venue matches, OR
  2. stop_corpus passage names the stop AND the venue in the same source
     (D74's same-source rule), OR
  3. The venue's own catalogue page lists it (future: not implemented yet).

If none holds, the stop is UNVERIFIED and must not be narrated.

Mode control (LOCAL-245):
  STOP_EXISTENCE_GATE_MODE = off | log_only | enforce

  off      — gate disabled entirely, no verification, no logging
  log_only — verdicts computed and logged, nothing dropped
  enforce  — unverified stops dropped, tour may be shorter

  The mode is logged at startup so a run can never claim one mode while
  behaving in another.

Legacy compat (deprecated):
  ENABLE_STOP_EXISTENCE_GATE=1   → treated as 'enforce'
  DISABLE_STOP_EXISTENCE_GATE=1  → treated as 'off'
  neither set                    → treated as 'log_only'

  The new env var takes precedence when set.
"""

import json
import logging
import os
import re
import threading
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ──── LOCAL-320: Nominatim shared throttle ────────────────────────────────────
# Nominatim usage policy: max 1 request/second, descriptive User-Agent required.
# A throttled (429) or failed lookup must classify as "unknown" (retry), NEVER as
# "unverified" (which would reject a stop based on non-evidence). D162 rule:
# absence of evidence from a failed search is not evidence of absence.

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {
    "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
    "Accept": "application/json",
}
_NOMINATIM_MIN_INTERVAL = 1.1  # seconds between requests (slightly above 1s for safety)
_NOMINATIM_MAX_RETRIES = 3
_NOMINATIM_RETRY_BACKOFF = 2.0  # seconds base for exponential backoff

_nominatim_lock = threading.Lock()
_nominatim_last_request_time = 0.0


def _nominatim_request(params: dict, context: str = "") -> "requests.Response":
    """Make a rate-limited Nominatim request with retry on 429/timeout.

    LOCAL-320: Serialises all Nominatim requests at ≤1/second using a shared
    lock. Retries up to 3 times with exponential backoff on 429 or timeout.

    Returns:
        requests.Response with status 200

    Raises:
        RuntimeError: If all retries exhausted (429), timeout, or connection
        error. The caller MUST treat this as "unknown" — not "unverified".
    """
    import requests as _http

    global _nominatim_last_request_time

    for attempt in range(_NOMINATIM_MAX_RETRIES):
        # Serialise and enforce minimum interval
        with _nominatim_lock:
            now = time.time()
            elapsed = now - _nominatim_last_request_time
            if elapsed < _NOMINATIM_MIN_INTERVAL:
                sleep_time = _NOMINATIM_MIN_INTERVAL - elapsed
                time.sleep(sleep_time)
            _nominatim_last_request_time = time.time()

        try:
            resp = _http.get(
                _NOMINATIM_URL, params=params, headers=_NOMINATIM_HEADERS, timeout=10
            )
        except (_http.exceptions.Timeout, _http.exceptions.ConnectionError) as e:
            logger.warning(f"[EXISTENCE-GATE] Nominatim {type(e).__name__} for "
                           f"{context!r} (attempt {attempt + 1}/{_NOMINATIM_MAX_RETRIES})")
            if attempt < _NOMINATIM_MAX_RETRIES - 1:
                time.sleep(_NOMINATIM_RETRY_BACKOFF * (2 ** attempt))
                continue
            raise RuntimeError(
                f"Nominatim connection failed for {context!r} after "
                f"{_NOMINATIM_MAX_RETRIES} attempts: {e}"
            )

        if resp.status_code == 429:
            logger.warning(f"[EXISTENCE-GATE] Nominatim 429 for {context!r} "
                           f"(attempt {attempt + 1}/{_NOMINATIM_MAX_RETRIES})")
            if attempt < _NOMINATIM_MAX_RETRIES - 1:
                time.sleep(_NOMINATIM_RETRY_BACKOFF * (2 ** attempt))
                continue
            raise RuntimeError(
                f"Nominatim rate limited (429) for {context!r} after "
                f"{_NOMINATIM_MAX_RETRIES} retries"
            )

        if resp.status_code != 200:
            logger.warning(f"[EXISTENCE-GATE] Nominatim HTTP {resp.status_code} for "
                           f"{context!r}")
            # Non-429 errors: don't retry, but also don't silently return False
            # Return the response and let the caller decide
            raise RuntimeError(
                f"Nominatim HTTP {resp.status_code} for {context!r}"
            )

        return resp

    # Should not reach here, but safety
    raise RuntimeError(f"Nominatim request failed for {context!r}")


# ──── END LOCAL-320 ───────────────────────────────────────────────────────────


# ──── [LOCAL-779] BUSINESS POI CLASSIFICATION ─────────────────────────────────
# Gyms, cafés, shops, bakeries, bars, spas, climbing walls … are BUSINESSES. Like
# restaurants (LOCAL-281/313) they are rarely on Wikipedia/Wikidata, so the
# existence gate's Wikidata-P625/OSM landmark path (_check_walking_stop_existence)
# cannot vouch for them and DROPS every stop — the LOCAL-779 bug. They DO exist as
# named POIs in OpenStreetMap with an address and coordinates, so they verify the
# SAME way a restaurant does: a maps/places result whose name matches and whose
# address lies inside the toured scope. This keyword list (plus the existing
# dining keywords, plus the LLM intent when unsure) routes such a request to the
# generalized OSM business-existence path. Dining stays its own kind so the
# restaurant canary (LOCAL-281/313/557) is byte-for-byte unchanged.
_BUSINESS_KEYWORDS = (
    'gym', 'gyms', 'fitness', 'crossfit', 'yoga', 'pilates', 'climbing',
    'bouldering', 'spa', 'spas', 'salon', 'barber', 'barbershop',
    'cafe', 'cafes', 'café', 'cafés', 'coffee', 'coffeehouse', 'coffeeshop',
    'bakery', 'bakeries', 'patisserie', 'pâtisserie',
    'bar', 'bars', 'pub', 'pubs', 'brewery', 'breweries', 'brewpub', 'taproom',
    'winery', 'wineries', 'distillery', 'cidery',
    'shop', 'shops', 'store', 'stores', 'boutique', 'boutiques',
    'bookstore', 'bookshop', 'bookshops', 'bookstores',
    'market', 'grocery', 'deli', 'delis', 'creamery',
    'studio', 'studios',
)

# OSM category / type tokens that mark a BUSINESS. Broader than dining — it must
# accept amenity=gym/cafe/bar, leisure=fitness_centre/sports_centre, shop=* of any
# kind, and tourism=... when the name is a strong match. Kept deliberately wide:
# a business is "a commercial POI with a name and an address", and OSM tags these
# under amenity/leisure/shop/craft/office.
_BUSINESS_OSM_TYPES = (
    'gym', 'fitness_centre', 'fitness_center', 'sports_centre', 'sports_center',
    'climbing', 'dojo', 'yoga', 'pilates',
    'cafe', 'bar', 'pub', 'biergarten', 'nightclub', 'restaurant', 'fast_food',
    'bakery', 'pastry', 'confectionery', 'deli', 'butcher', 'greengrocer',
    'supermarket', 'convenience', 'books', 'clothes', 'shoes', 'gift',
    'hairdresser', 'beauty', 'spa', 'massage', 'cosmetics',
    'brewery', 'winery', 'distillery', 'alcohol', 'wine', 'coffee',
)
_BUSINESS_OSM_CATEGORIES = (
    'amenity', 'leisure', 'shop', 'craft', 'office', 'sport',
)


def classify_business_vs_landmark(poi_type: Optional[str]) -> str:
    """[LOCAL-779] Deterministic first pass: is this poi_type a BUSINESS or a LANDMARK?

    Returns 'business', 'dining', or 'landmark'.

      * 'dining'   — a food/restaurant poi_type (kept separate so the restaurant
                     canary stays unchanged; dining is a business but routes to the
                     dining path).
      * 'business' — gyms, cafés, shops, bakeries, bars, spas, climbing walls, …
                     a commercial POI class that lives on maps, not Wikipedia.
      * 'landmark' — anything else (monuments, historic sites, parks, museums,
                     filming locations, generic 'landmarks'): the default, so a
                     landmark tour's behaviour is untouched.

    Pure and deterministic — a keyword fact about the poi_type string. The caller
    layers the existing restaurant classification and an LLM intent fallback on
    top when this returns 'landmark' but the request is ambiguous.
    """
    if not poi_type:
        return 'landmark'
    raw = poi_type if isinstance(poi_type, str) else ' or '.join(poi_type)
    tl = _strip_accents(raw).lower()
    _DINING = ('restaurant', 'dining', 'food', 'culinary', 'eatery', 'bistro', 'brasserie')
    if any(kw in tl for kw in _DINING):
        return 'dining'
    toks = set(re.findall(r"[a-zà-ÿ]+", tl))
    for kw in _BUSINESS_KEYWORDS:
        k = _strip_accents(kw)
        # Whole-word for short tokens (bar, gym, spa) to avoid 'bar' in 'barn';
        # substring for longer ones so 'coffee shops' and 'climbing gym' both hit.
        if len(k) <= 4:
            if k in toks:
                return 'business'
        elif k in tl:
            return 'business'
    return 'landmark'


def _strip_accents(text: str) -> str:
    """Remove accents for matching (é→e, ô→o, etc.)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison: lowercase, strip accents, collapse whitespace."""
    t = _strip_accents(title).lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


def _content_words(title: str) -> List[str]:
    """Extract meaningful words (>=4 chars, no stopwords) from a title."""
    STOP = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
        'des', 'les', 'une', 'dans', 'sur', 'par', 'aux', 'son', 'ses',
        'qui', 'que', 'est', 'sont', 'art', 'arts', 'musee', 'museum',
        'stop', 'tour', 'nice', 'france',
    }
    words = _normalize_title(title).split()
    return [w for w in words if len(w) >= 4 and w not in STOP]


def _title_match(stop_title: str, canonical_title: str) -> bool:
    """Check if a stop title matches a canonical title.

    Uses normalized token overlap: >=60% of the shorter title's content words
    must appear in the longer. Also checks substring containment for short titles.
    """
    norm_stop = _normalize_title(stop_title)
    norm_canon = _normalize_title(canonical_title)

    # Exact match
    if norm_stop == norm_canon:
        return True

    # Substring containment (either direction)
    if len(norm_stop) > 5 and len(norm_canon) > 5:
        if norm_stop in norm_canon or norm_canon in norm_stop:
            return True

    # Token overlap
    stop_words = set(_content_words(stop_title))
    canon_words = set(_content_words(canonical_title))

    if not stop_words or not canon_words:
        return False

    # Check overlap against the shorter set
    shorter = stop_words if len(stop_words) <= len(canon_words) else canon_words
    longer = canon_words if len(stop_words) <= len(canon_words) else stop_words

    overlap = len(shorter & longer)
    if len(shorter) > 0 and overlap / len(shorter) >= 0.60:
        return True

    return False


def _find_venue_corpus_rows(venue_name: str, db_conn) -> list:
    """Find venue_corpus rows that match a venue name.

    Uses progressive relaxation:
    1. All significant words match (strict)
    2. Any 2 significant words match (relaxed)
    3. Single most specific word matches (last resort)

    Returns list of (venue_name, canonical_titles_json, sparql_works_json) tuples.
    """
    cur = db_conn.cursor()
    venue_words = [w for w in _content_words(venue_name) if len(w) >= 4]

    # Remove generic tour-type words that aren't venue identifiers
    TOUR_WORDS = {'tour', 'walking', 'biking', 'cycling', 'museum', 'visite',
                  'restaurant', 'экскурсия', 'тур', 'музей', 'musee'}
    venue_words = [w for w in venue_words if w not in TOUR_WORDS]

    if not venue_words:
        return []

    # Try strict: all words
    conditions = []
    params = []
    for w in venue_words[:4]:
        conditions.append("LOWER(venue_name) LIKE %s")
        params.append(f"%{w}%")

    query = f"""
        SELECT venue_name, canonical_titles_json, sparql_works_json
        FROM venue_corpus WHERE {' AND '.join(conditions)}
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    if rows:
        return rows

    # Try relaxed: any 2 words (for multi-word venue names)
    if len(venue_words) >= 2:
        conditions = []
        params = []
        for w in venue_words[:4]:
            conditions.append("LOWER(venue_name) LIKE %s")
            params.append(f"%{w}%")

        query = f"""
            SELECT venue_name, canonical_titles_json, sparql_works_json
            FROM venue_corpus WHERE {' OR '.join(
                f"({c1} AND {c2})"
                for i, c1 in enumerate(conditions)
                for c2 in conditions[i+1:]
            )}
        """
        # Flatten params for OR pairs
        pair_params = []
        for i in range(len(params)):
            for j in range(i + 1, len(params)):
                pair_params.extend([params[i], params[j]])
        if pair_params:
            cur.execute(query, pair_params)
            rows = cur.fetchall()
            if rows:
                return rows

    # Last resort: single most specific word (longest, not a city name)
    CITIES = {'nice', 'paris', 'france', 'monaco', 'antibes', 'boston',
              'philadelphia', 'ницца', 'франция'}
    specific_words = [w for w in venue_words if w not in CITIES]
    if not specific_words:
        specific_words = venue_words

    # Sort by length descending (longer words are more specific)
    specific_words.sort(key=len, reverse=True)
    for w in specific_words[:2]:
        cur.execute(
            "SELECT venue_name, canonical_titles_json, sparql_works_json "
            "FROM venue_corpus WHERE LOWER(venue_name) LIKE %s",
            (f"%{w}%",)
        )
        rows = cur.fetchall()
        if rows:
            return rows

    return []


def _check_venue_corpus(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check venue_corpus for canonical_titles_json or sparql_works_json match.

    Returns (verified: bool, evidence: str).
    """
    try:
        rows = _find_venue_corpus_rows(venue_name, db_conn)

        for vc_name, ct_json, sw_json in rows:
            # Check canonical_titles_json
            if ct_json:
                titles = ct_json if isinstance(ct_json, list) else []
                for ct in titles:
                    if isinstance(ct, str) and _title_match(stop_title, ct):
                        return True, f"venue_corpus canonical_title: {ct!r} at {vc_name!r}"
                    elif isinstance(ct, dict):
                        # Geographic POI format: {name: ..., qid: ..., lat: ..., lng: ...}
                        name = ct.get('name', '')
                        if name and _title_match(stop_title, name):
                            return True, f"venue_corpus canonical_title(geo): {name!r} at {vc_name!r}"

            # Check sparql_works_json
            if sw_json:
                works = sw_json if isinstance(sw_json, list) else []
                for w in works:
                    if isinstance(w, dict):
                        for key in ('label_en', 'label_local'):
                            label = w.get(key, '')
                            if label and _title_match(stop_title, label):
                                return True, f"venue_corpus sparql_work: {label!r} (QID:{w.get('qid','?')}) at {vc_name!r}"

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] venue_corpus check failed: {e}")
        return False, ""


def _find_stop_corpus_rows(venue_name: str, db_conn) -> list:
    """Find stop_corpus rows that match a venue name.

    Similar to _find_venue_corpus_rows but for the stop_corpus table.
    Returns list of (venue_name, stop_title, passages_json, source_pages) tuples.
    """
    cur = db_conn.cursor()
    venue_words = [w for w in _content_words(venue_name) if len(w) >= 4]

    TOUR_WORDS = {'tour', 'walking', 'biking', 'cycling', 'museum', 'visite',
                  'restaurant', 'экскурсия', 'тур', 'музей', 'musee'}
    venue_words = [w for w in venue_words if w not in TOUR_WORDS]

    if not venue_words:
        return []

    # Try strict: all words
    conditions = []
    params = []
    for w in venue_words[:4]:
        conditions.append("LOWER(venue_name) LIKE %s")
        params.append(f"%{w}%")

    query = f"""
        SELECT venue_name, stop_title, passages_json, source_pages
        FROM stop_corpus
        WHERE {' AND '.join(conditions)} AND passage_count > 0
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    if rows:
        return rows

    # Relaxed: any 2 words
    if len(venue_words) >= 2:
        or_conditions = []
        or_params = []
        for i in range(len(venue_words[:4])):
            for j in range(i + 1, len(venue_words[:4])):
                or_conditions.append(f"(LOWER(venue_name) LIKE %s AND LOWER(venue_name) LIKE %s)")
                or_params.extend([f"%{venue_words[i]}%", f"%{venue_words[j]}%"])

        if or_conditions:
            query = f"""
                SELECT venue_name, stop_title, passages_json, source_pages
                FROM stop_corpus
                WHERE ({' OR '.join(or_conditions)}) AND passage_count > 0
            """
            cur.execute(query, or_params)
            rows = cur.fetchall()
            if rows:
                return rows

    # Last resort: single most specific word
    CITIES = {'nice', 'paris', 'france', 'monaco', 'antibes', 'boston',
              'philadelphia', 'ницца', 'франция'}
    specific_words = [w for w in venue_words if w not in CITIES]
    if not specific_words:
        specific_words = venue_words
    specific_words.sort(key=len, reverse=True)

    for w in specific_words[:2]:
        cur.execute(
            "SELECT venue_name, stop_title, passages_json, source_pages "
            "FROM stop_corpus WHERE LOWER(venue_name) LIKE %s AND passage_count > 0",
            (f"%{w}%",)
        )
        rows = cur.fetchall()
        if rows:
            return rows

    return []


def _check_stop_corpus(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check stop_corpus for a passage that names BOTH the stop and the venue.

    D74 rule: venue confirmation must come from the same source as the subject claim.
    A stop_corpus row matching the stop title is not enough — the passages must
    mention both the stop subject and the venue in the same source.
    """
    try:
        rows = _find_stop_corpus_rows(venue_name, db_conn)

        for sc_venue, sc_stop, passages_json, source_pages in rows:
            # Check if this stop_corpus row matches our stop title
            if not _title_match(stop_title, sc_stop):
                continue

            # D74: passages must mention BOTH stop and venue in the same source
            # Check that at least one passage contains venue context
            if not passages_json:
                continue

            passages = passages_json if isinstance(passages_json, list) else []
            # Extract venue-identifying words (city name, museum name fragments)
            venue_signals = set()
            for part in re.split(r'[,\s]+', venue_name):
                part_clean = _strip_accents(part).lower()
                if len(part_clean) >= 4 and part_clean not in ('france', 'museum', 'musee'):
                    venue_signals.add(part_clean)

            for p in passages:
                p_text = p if isinstance(p, str) else (p.get('text', '') if isinstance(p, dict) else str(p))
                p_lower = _strip_accents(p_text).lower()

                # Check if passage has BOTH stop content and venue signal
                stop_words = _content_words(stop_title)
                has_stop = any(w in p_lower for w in stop_words) if stop_words else False
                has_venue = any(v in p_lower for v in venue_signals)

                if has_stop and has_venue:
                    return True, f"stop_corpus: {sc_stop!r} at {sc_venue!r} (same-source confirmed)"

            # If passages exist but none has both signals, it fails D74
            # (the passage might be about the subject in general but not at THIS venue)

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] stop_corpus check failed: {e}")
        return False, ""


def _classify_venue_kind(venue_name: str, db_conn, tour_type: Optional[str] = None,
                         poi_type: Optional[str] = None) -> Tuple[str, str]:
    """Classify a venue as 'institution', 'geographic_area', 'dining', or 'business'.

    LOCAL-239: An institution (museum, palace, named building) and a geographic
    area (walking route, region, coastal path) need different confirmation logic.

    LOCAL-281: A dining/restaurant tour needs a third kind. The question for a
    restaurant is "does Le Chantecler exist in Nice?" — not "does a source tie
    Le Chantecler to 'restaurant tour in Nice, France'" (our internal label).

    LOCAL-779: A BUSINESS tour (gyms, cafés, shops, bakeries, bars, spas,
    climbing walls) needs the same kind of answer as dining — "does a place with
    this name exist at an address inside the scope?" — but its signal is the
    intent's poi_type, NOT the tour_category (a "walking tour: gyms near me"
    arrives with tour_category='walking'). So the poi_type is classified via
    classify_business_vs_landmark and, when it says 'business', this returns the
    'business' kind so verify_stop_existence routes to the maps/places path.

    Classification priority:
      1. Explicit tour_type signal (or EXISTENCE_GATE_TOUR_TYPE env var):
         - restaurant/food/dining → 'dining'
      2. poi_type (or EXISTENCE_GATE_POI_TYPE env var) → 'dining'/'business' via
         classify_business_vs_landmark.
      3. venue_corpus.sparql_works_json presence:
         - Institution: has sparql_works_json (a list of held works from Wikidata)
         - Geographic area: no sparql_works_json (canonical_titles are POIs/sections)

    Returns:
        (kind: 'institution' | 'geographic_area' | 'dining' | 'business' | 'unknown',
         evidence: str)
    """
    # LOCAL-281: Check tour_type signal first (explicit kwarg or env fallback)
    _effective_tour_type = tour_type or os.environ.get('EXISTENCE_GATE_TOUR_TYPE', '')
    if _effective_tour_type:
        _tt_lower = _effective_tour_type.lower()
        _DINING_KEYWORDS = ('restaurant', 'food', 'dining', 'culinary', 'bistro', 'cafe', 'eatery')
        if any(kw in _tt_lower for kw in _DINING_KEYWORDS):
            return 'dining', f'tour_type={_effective_tour_type!r} signals dining'

    # LOCAL-779: poi_type signal — a gym/café/shop poi_type is a BUSINESS even when
    # the tour_category is 'walking'. Dining poi_types still route to 'dining' so
    # the restaurant canary is unchanged.
    _effective_poi_type = poi_type or os.environ.get('EXISTENCE_GATE_POI_TYPE', '')
    if _effective_poi_type:
        _biz_kind = classify_business_vs_landmark(_effective_poi_type)
        if _biz_kind == 'dining':
            return 'dining', f'poi_type={_effective_poi_type!r} signals dining'
        if _biz_kind == 'business':
            return 'business', f'poi_type={_effective_poi_type!r} signals business'

    try:
        rows = _find_venue_corpus_rows(venue_name, db_conn)
        if not rows:
            return 'unknown', 'no venue_corpus row found'

        # Check if ANY matched row has sparql_works_json
        for vc_name, ct_json, sw_json in rows:
            if sw_json:
                return 'institution', f'sparql_works_json present at {vc_name!r}'

        # No sparql — geographic area
        vc_name = rows[0][0]
        return 'geographic_area', f'no sparql_works_json at {vc_name!r}'
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] venue kind classification failed: {e}")
        return 'unknown', f'classification error: {e}'


def _check_stop_corpus_geographic(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check stop_corpus for a geographic area — relaxed confirmation.

    LOCAL-239: For geographic areas, the stop does NOT need to mention the
    venue name in its passage. A stop_corpus row matching the stop title under
    this venue, with at least one passage, is sufficient evidence that it is a
    real place in the region.

    This is fundamentally different from institutions: a museum stop must prove
    the object is AT that museum (same-source rule, D74). But Eze Village's
    Wikipedia article will never say "French Riviera walking area" — it just
    needs to be a real place that is geographically within the Riviera.
    """
    try:
        rows = _find_stop_corpus_rows(venue_name, db_conn)

        for sc_venue, sc_stop, passages_json, source_pages in rows:
            # Check if this stop_corpus row matches our stop title
            if not _title_match(stop_title, sc_stop):
                continue

            # For geographic areas: having a passage at all is sufficient
            if passages_json:
                passages = passages_json if isinstance(passages_json, list) else []
                if passages:
                    return True, f"stop_corpus(geographic): {sc_stop!r} at {sc_venue!r} ({len(passages)} passages)"

        return False, ""
    except Exception as e:
        logger.warning(f"[EXISTENCE-GATE] stop_corpus geographic check failed: {e}")
        return False, ""


def _check_geographic_existence_tier1(
    stop_title: str, venue_name: str
) -> Tuple[bool, str]:
    """Tier-1 existence check for geographic stops: Wikipedia + Wikidata.

    LOCAL-290 / D162 automated: A stop absent from our stop_corpus is NOT
    necessarily fabricated — it may simply be a real place we have not scraped.
    Before rejecting, check whether the place actually exists via:
      1. Wikipedia REST API (summary lookup by name)
      2. Wikipedia search API (search for name + region)
      3. Wikidata entity search (structured knowledge base)

    A fabricated place still fails (no Wikipedia article, no Wikidata entity).
    A real place that we simply haven't scraped now passes.

    Proximity constraint: the Wikipedia/Wikidata result must mention the region
    (from venue_name) OR be geolocated within a reasonable distance. This
    prevents "Le Chantecler in Lyon" from passing for a Nice tour (LOCAL-281
    test case that must still fail).
    """
    import requests as _http
    from urllib.parse import quote

    # Extract region signals from venue_name
    # e.g. "French Riviera walking area" → {"french", "riviera"}
    # e.g. "Nice, France cycling tour" → {"nice"}
    _region_signals = set()
    for part in re.split(r'[,\s]+', venue_name):
        part_clean = _strip_accents(part).lower().strip()
        if len(part_clean) >= 4 and part_clean not in (
            'area', 'walking', 'cycling', 'biking', 'tour', 'driving',
            'france', 'italy', 'spain', 'germany', 'england',  # country too broad
        ):
            _region_signals.add(part_clean)

    # Also add well-known sub-region names that a Wikipedia article would mention
    _RIVIERA_CITIES = {'nice', 'cannes', 'monaco', 'antibes', 'menton', 'grasse',
                       'villefranche', 'saint-tropez', 'eze', 'mougins', 'cagnes',
                       'vence', 'frejus', 'juan-les-pins', 'beaulieu'}
    _use_riviera_bbox = False
    if 'riviera' in _region_signals or 'french' in _region_signals:
        _use_riviera_bbox = True
        # For French Riviera tours, any Riviera city in the article is evidence
        _region_signals.update(_RIVIERA_CITIES)
        _region_signals.add('cote d azur')
        _region_signals.add('alpes-maritimes')
        _region_signals.add('alpes maritimes')
        _region_signals.add('mediterranean')
        # Remove overly broad signals that would match ANY French article
        _region_signals.discard('french')
        _region_signals.discard('france')

    _HEADERS = {
        "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
        "Accept": "application/json",
    }

    # --- Check 1: Wikipedia summary (en + fr) ---
    for lang in ('en', 'fr'):
        try:
            encoded_title = quote(stop_title.strip().replace(" ", "_"), safe="")
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
            resp = _http.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "")
                title_returned = data.get("title", "")
                description = data.get("description", "")
                full_text = _strip_accents(f"{extract} {description}").lower()

                # Check region proximity: does the article mention the region?
                has_region = any(sig in full_text for sig in _region_signals)

                # Also check coordinates if available
                coords = data.get("coordinates", {})
                if coords and not has_region:
                    # Geographic proximity check: is it in the right general area?
                    lat = coords.get("lat", 0)
                    lng = coords.get("lon", 0) or coords.get("lng", 0)
                    if lat and lng:
                        # French Riviera roughly: lat 43.2-43.8, lng 6.0-7.6
                        if _use_riviera_bbox:
                            if 43.0 <= lat <= 44.0 and 5.5 <= lng <= 7.8:
                                has_region = True

                if has_region:
                    return True, (f"wikipedia_{lang}_summary: '{title_returned}' "
                                  f"exists and mentions region")
                elif _title_match(stop_title, title_returned):
                    # Title matches but no region signal — could be the wrong place
                    # (e.g. "Lyon" article for a Nice tour). Don't verify.
                    logger.debug(f"[EXISTENCE-GATE] Wikipedia found '{title_returned}' but "
                                 f"no region signal for {venue_name}")
        except Exception as e:
            logger.debug(f"[EXISTENCE-GATE] Wikipedia {lang} summary check failed for "
                         f"{stop_title!r}: {e}")

    # --- Check 2: Wikipedia search (finds places mentioned in other articles) ---
    for lang in ('en', 'fr'):
        try:
            # Build search query with region hint
            region_hint = next((s for s in _region_signals
                                if s not in ('french', 'riviera', 'mediterranean')), "")
            search_query = f'"{stop_title}" {region_hint}'.strip()

            search_url = f"https://{lang}.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": search_query,
                "srnamespace": "0",
                "srlimit": "5",
                "format": "json",
            }
            resp = _http.get(search_url, params=params, headers=_HEADERS, timeout=8)
            if resp.status_code == 200:
                results = resp.json().get("query", {}).get("search", [])
                for r in results:
                    r_title = r.get("title", "")
                    snippet = _strip_accents(
                        re.sub(r'<[^>]+>', '', r.get("snippet", ""))
                    ).lower()

                    # Check if the result IS the place (title matches)
                    if _title_match(stop_title, r_title):
                        # Snippet or title matches — check region
                        if any(sig in snippet for sig in _region_signals):
                            return True, (f"wikipedia_{lang}_search: '{r_title}' "
                                          f"matches and snippet mentions region")
                        # Title matches exactly — fetch summary for region check
                        try:
                            art_url = (f"https://{lang}.wikipedia.org/api/rest_v1/"
                                       f"page/summary/{quote(r_title.replace(' ', '_'), safe='')}")
                            art_resp = _http.get(art_url, headers=_HEADERS,
                                                 timeout=5, allow_redirects=True)
                            if art_resp.status_code == 200:
                                art_data = art_resp.json()
                                art_text = _strip_accents(
                                    f"{art_data.get('extract', '')} "
                                    f"{art_data.get('description', '')}"
                                ).lower()
                                if any(sig in art_text for sig in _region_signals):
                                    return True, (f"wikipedia_{lang}_article: '{r_title}' "
                                                  f"exists in region")
                                # Coordinate check
                                art_coords = art_data.get("coordinates", {})
                                if art_coords:
                                    lat = art_coords.get("lat", 0)
                                    lng = art_coords.get("lon", 0) or art_coords.get("lng", 0)
                                    if lat and lng and _use_riviera_bbox:
                                        if 43.0 <= lat <= 44.0 and 5.5 <= lng <= 7.8:
                                            return True, (f"wikipedia_{lang}_coords: "
                                                          f"'{r_title}' at {lat:.2f},{lng:.2f} "
                                                          f"within Riviera bounds")
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"[EXISTENCE-GATE] Wikipedia {lang} search check failed for "
                         f"{stop_title!r}: {e}")

    # --- Check 3: Wikidata entity search ---
    try:
        wd_url = "https://www.wikidata.org/w/api.php"
        for lang in ('en', 'fr'):
            wd_params = {
                "action": "wbsearchentities",
                "search": stop_title,
                "language": lang,
                "limit": "5",
                "format": "json",
            }
            resp = _http.get(wd_url, params=wd_params, headers=_HEADERS, timeout=8)
            if resp.status_code == 200:
                wd_results = resp.json().get("search", [])
                for wd_r in wd_results:
                    wd_label = wd_r.get("label", "")
                    wd_desc = _strip_accents(wd_r.get("description", "")).lower()

                    if _title_match(stop_title, wd_label):
                        # Check if description mentions the region
                        if any(sig in wd_desc for sig in _region_signals):
                            return True, (f"wikidata_{lang}: '{wd_label}' "
                                          f"(QID:{wd_r.get('id', '?')}) "
                                          f"description mentions region")
                        # Geographic entity types that are inherently locatable
                        _GEO_TYPES = ('commune', 'village', 'town', 'city', 'cape',
                                      'peninsula', 'bay', 'beach', 'island', 'mountain',
                                      'hill', 'park', 'garden', 'road', 'street',
                                      'quarter', 'district', 'headland', 'port',
                                      'harbour', 'harbor', 'corniche', 'promontoire',
                                      'commune de france', 'commune française')
                        if any(gt in wd_desc for gt in _GEO_TYPES):
                            # It's a geographic entity — check proximity via SPARQL
                            # (lightweight: just fetch coordinates for the QID)
                            qid = wd_r.get('id', '')
                            if qid:
                                _coords = _fetch_wikidata_coords(qid, _HEADERS)
                                if _coords:
                                    lat, lng = _coords
                                    if _use_riviera_bbox:
                                        if 43.0 <= lat <= 44.0 and 5.5 <= lng <= 7.8:
                                            return True, (f"wikidata_{lang}_coords: "
                                                          f"'{wd_label}' (QID:{qid}) "
                                                          f"at {lat:.2f},{lng:.2f} "
                                                          f"within region")
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] Wikidata check failed for {stop_title!r}: {e}")

    # --- Check 4: Proper-noun extraction fallback ---
    # For compound names like "Old Town of Menton" or "Castle Hill of Nice",
    # extract the geographic proper noun and look it up directly.
    # If "Menton" has a Wikipedia article at the right coordinates, "Old Town of Menton" exists.
    _proper_nouns = _extract_geographic_proper_nouns(stop_title)
    for pn in _proper_nouns:
        try:
            import requests as _http_pn
            pn_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(pn.replace(' ', '_'), safe='')}"
            pn_resp = _http_pn.get(pn_url, headers=_HEADERS, timeout=8, allow_redirects=True)
            if pn_resp.status_code == 200:
                pn_data = pn_resp.json()
                pn_coords = pn_data.get("coordinates", {})
                if pn_coords:
                    lat = pn_coords.get("lat", 0)
                    lng = pn_coords.get("lon", 0) or pn_coords.get("lng", 0)
                    if lat and lng:
                        if _use_riviera_bbox:
                            if 43.0 <= lat <= 44.0 and 5.5 <= lng <= 7.8:
                                return True, (f"wikipedia_proper_noun: '{pn}' "
                                              f"at {lat:.2f},{lng:.2f} confirms "
                                              f"'{stop_title}' is in region")
                # No coords but article mentions region
                pn_text = _strip_accents(
                    f"{pn_data.get('extract', '')} {pn_data.get('description', '')}"
                ).lower()
                if any(sig in pn_text for sig in _region_signals if sig != pn.lower()):
                    return True, (f"wikipedia_proper_noun: '{pn}' article "
                                  f"mentions region, confirms '{stop_title}'")
        except Exception:
            pass

    return False, ""


def _extract_geographic_proper_nouns(stop_title: str) -> List[str]:
    """Extract likely geographic proper nouns from a compound stop name.

    "Old Town of Menton" → ["Menton"]
    "Castle Hill of Nice" → ["Nice"]
    "Cap d'Antibes Coastal Path" → ["Antibes"]
    "Promenade Maurice Rouvier" → ["Maurice Rouvier"]

    Strategy: split on prepositions (of, de, du, des, d') and take the trailing
    proper noun. Also try removing common geographic type prefixes.
    """
    candidates = []

    # Pattern 1: "X of Y" or "X de Y" — Y is likely the place
    m = re.search(r'\b(?:of|de|du|des|d\')\s+(.+)$', stop_title, re.IGNORECASE)
    if m:
        trailing = m.group(1).strip()
        if len(trailing) >= 3:
            candidates.append(trailing)

    # Pattern 2: Remove common geographic type prefixes
    _GEO_PREFIXES = (
        'old town', 'castle hill', 'fort', 'port', 'cape', 'bay',
        'beach', 'island', 'mount', 'hill', 'garden', 'park',
        'promenade', 'boulevard', 'place', 'square', 'corniche',
    )
    title_lower = stop_title.lower()
    for prefix in _GEO_PREFIXES:
        if title_lower.startswith(prefix):
            remainder = stop_title[len(prefix):].strip()
            # Remove leading "of", "de", etc.
            remainder = re.sub(r'^(?:of|de|du|des|d\')\s*', '', remainder, flags=re.IGNORECASE).strip()
            if len(remainder) >= 3:
                candidates.append(remainder)
                break

    return candidates
    """Fetch P625 (coordinate location) for a Wikidata entity."""
    import requests as _http
    try:
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetclaims",
            "entity": qid,
            "property": "P625",
            "format": "json",
        }
        resp = _http.get(url, params=params, headers=headers, timeout=8)
        if resp.status_code == 200:
            claims = resp.json().get("claims", {}).get("P625", [])
            if claims:
                mainsnak = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
                lat = mainsnak.get("latitude")
                lng = mainsnak.get("longitude")
                if lat is not None and lng is not None:
                    return (float(lat), float(lng))
    except Exception:
        pass
    return None


def _check_dining_existence(
    stop_title: str, venue_name: str, db_conn
) -> Tuple[bool, str]:
    """Check whether a restaurant/dining establishment exists at the claimed location.

    LOCAL-281: For dining tours, the "venue" is a city/region (our internal label,
    e.g. "Nice, France"). No source will ever tie a restaurant to that label. The
    right question is: "Does Le Chantecler exist in Nice?" — verified by external
    evidence from Wikipedia, Wikidata, or an authoritative culinary source.

    Strategy (using existing retrieval infrastructure):
      1. Wikipedia REST API: fetch summary for the restaurant name — if it exists
         and mentions the city/region, that's Tier-1 evidence.
      2. Wikipedia search API: search for "restaurant_name city" — if a search
         result's snippet mentions BOTH the stop name and the city, that's
         evidence (covers restaurants without standalone articles, e.g. Le
         Chantecler mentioned in the Hotel Negresco article).
      3. French Wikipedia (many Nice restaurants have fr.wiki coverage).
      4. Wikidata: search for the entity.

    A restaurant is VERIFIED if any one of these returns a positive signal tying
    the establishment to the geographic area in venue_name. A plausible name with
    no external trace remains UNVERIFIED.
    """
    import requests as _http
    from urllib.parse import quote

    # Extract city/location signal from venue_name
    # venue_name for restaurant tours is typically "Nice, France" or "Nice"
    # but can also be "restaurant tour in Old Nice (Vieux Nice), France"
    _city_signals = set()
    # Strip parenthetical content and split on delimiters
    _venue_cleaned = re.sub(r'\([^)]*\)', ' ', venue_name)
    for part in re.split(r'[,\s]+', _venue_cleaned):
        part_clean = _strip_accents(part).lower().strip()
        # Remove any leftover punctuation
        part_clean = re.sub(r'[^a-z]', '', part_clean)
        if len(part_clean) >= 3 and part_clean not in ('france', 'italy', 'spain', 'usa', 'uk',
                                                        'the', 'tour', 'restaurant', 'food',
                                                        'dining', 'culinary', 'old', 'new',
                                                        'vieux', 'stop', 'stops'):
            _city_signals.add(part_clean)

    # Stop title words for snippet matching — split on whitespace AND apostrophes
    _stop_words = [w for w in re.split(r"[\s'\u2019-]+", _strip_accents(stop_title).lower())
                   if len(w) >= 3 and w not in ('the', 'les', 'des', 'une', 'la', 'le', 'du')]

    def _snippet_has_evidence(snippet_text: str) -> bool:
        """Check if a snippet mentions the restaurant, the city, and a dining signal.
        
        Three requirements:
          1. Stop words present in snippet
          2. City signal present in snippet
          3. A dining-related word present (prevents museums/markets from passing)
          4. Proximity: city within 120 chars of stop word
        """
        s = _strip_accents(re.sub(r'<[^>]+>', '', snippet_text)).lower()
        # Also decode HTML entities
        s = s.replace('&#039;', "'").replace('&amp;', '&').replace('&quot;', '"')
        # Need at least half the stop words present
        word_hits = sum(1 for w in _stop_words if w in s)
        has_stop = word_hits >= max(1, len(_stop_words) // 2) if _stop_words else False
        if not has_stop:
            return False
        has_city = any(sig in s for sig in _city_signals) if _city_signals else False
        if not has_city:
            return False
        # Require a dining signal in the snippet
        _dining_snippet_signals = ('restaurant', 'chef', 'michelin', 'cuisine', 'bistro',
                                   'brasserie', 'gastronomic', 'dining', 'starred',
                                   'food', 'culinary', 'cook', 'kitchen',
                                   'hotel-restaurant', 'hôtel-restaurant')
        has_dining = any(sig in s for sig in _dining_snippet_signals)
        if not has_dining:
            return False
        # Proximity check: find closest distance between any stop word and any city signal
        for sw in _stop_words:
            sw_pos = s.find(sw)
            if sw_pos < 0:
                continue
            for cs in _city_signals:
                cs_pos = s.find(cs)
                if cs_pos < 0:
                    continue
                if abs(sw_pos - cs_pos) <= 120:
                    return True
        return False

    _HEADERS = {
        "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
        "Accept": "application/json",
    }

    # --- Check 1: Wikipedia summary for the restaurant ---
    try:
        encoded_title = quote(stop_title.strip().replace(" ", "_"), safe="")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        resp = _http.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get("extract", "")
            title_returned = data.get("title", "")
            description = data.get("description", "")
            full_text = f"{extract} {description}".lower()
            full_text_normalized = _strip_accents(full_text)

            # For dining verification, we need BOTH:
            #   1. City/location mention
            #   2. Evidence it's a dining/food establishment (not just any place)
            _restaurant_signals = ('restaurant', 'dining', 'chef', 'michelin', 'cuisine',
                                   'bistro', 'brasserie', 'gastronomic', 'starred', 'food',
                                   'culinary', 'menu', 'kitchen', 'cook', 'dine', 'meal')
            is_dining = any(sig in full_text for sig in _restaurant_signals)
            has_city = _city_signals and any(sig in full_text_normalized for sig in _city_signals)

            if has_city and is_dining:
                return True, f"wikipedia_summary: '{title_returned}' is dining+city"
            # If it's clearly about a restaurant (even without explicit city in summary)
            # but title matches exactly, accept it
            if is_dining and _title_match(stop_title, title_returned):
                return True, f"wikipedia_summary: '{title_returned}' is a restaurant"
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] Wikipedia summary check failed for {stop_title!r}: {e}")

    # --- Check 2: Wikipedia search — snippet-based evidence ---
    # Key insight: many restaurants don't have standalone articles but are mentioned
    # in other articles (e.g. Le Chantecler in the Hotel Negresco article).
    # We search and check if the SNIPPET mentions both the restaurant and the city.
    #
    # LOCAL-320: The article fallback (fetching full article when snippet is partial)
    # must require the article to be ABOUT the establishment. An article about
    # Six Flags Great Adventure matched "Safari" + "nice" (the English adjective)
    # and was accepted as evidence for "Le Safari" in Nice. This is wrong.
    # The fix: the article fallback requires EITHER:
    #   (a) The article title matches the stop title (it IS the restaurant's article), OR
    #   (b) The article mentions the FULL stop name (not just partial word overlap)
    #       AND a dining signal AND the city as a proper noun (word boundary).
    try:
        city_hint = next(iter(_city_signals), "")
        # Try multiple search variants: quoted exact name, then unquoted keywords
        _search_variants = [
            f'"{stop_title}" {city_hint} restaurant',  # exact match preferred
        ]
        # For names with apostrophes (L'Univers), also try without the article
        _clean_name = re.sub(r"^(L'|Le |La |Les |L )", "", stop_title, flags=re.IGNORECASE).strip()
        if _clean_name != stop_title:
            _search_variants.append(f'"{_clean_name}" {city_hint} restaurant')
            _search_variants.append(f'{_clean_name} {city_hint} restaurant chef')

        search_url = "https://en.wikipedia.org/w/api.php"
        for sq in _search_variants:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": sq,
                "srnamespace": "0",
                "srlimit": "5",
                "format": "json",
            }
            resp = _http.get(search_url, params=params, headers=_HEADERS, timeout=8)
            if resp.status_code == 200:
                results = resp.json().get("query", {}).get("search", [])
                for r in results:
                    snippet_raw = r.get("snippet", "")
                    if _snippet_has_evidence(snippet_raw):
                        r_title = r.get("title", "")
                        return True, f"wikipedia_search: snippet in '{r_title}' mentions stop+city"
                    # Fallback: if snippet has the restaurant but not the city,
                    # fetch the article summary and check if IT has both
                    snippet_clean = _strip_accents(re.sub(r'<[^>]+>', '', snippet_raw)).lower()
                    snippet_clean = snippet_clean.replace('&#039;', "'").replace('&amp;', '&')
                    stop_in_snippet = any(w in snippet_clean for w in _stop_words)
                    if stop_in_snippet and not _snippet_has_evidence(snippet_raw):
                        # Snippet mentions restaurant but not city — check article
                        try:
                            r_title = r.get("title", "")
                            # LOCAL-320: Article must be ABOUT the establishment.
                            # If article title doesn't match stop title, this is
                            # a tangential mention — require much stronger evidence.
                            _article_is_about_stop = _title_match(stop_title, r_title)

                            art_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(r_title.replace(' ', '_'), safe='')}"
                            art_resp = _http.get(art_url, headers=_HEADERS, timeout=5, allow_redirects=True)
                            if art_resp.status_code == 200:
                                art_data = art_resp.json()
                                art_text = _strip_accents(f"{art_data.get('extract', '')} {art_data.get('description', '')}").lower()

                                if _article_is_about_stop:
                                    # Article IS the restaurant — just need city mention
                                    art_has_city = any(sig in art_text for sig in _city_signals)
                                    if art_has_city:
                                        return True, f"wikipedia_article: '{r_title}' is about the establishment+city"
                                else:
                                    # Article is about something ELSE (e.g. Six Flags).
                                    # LOCAL-320: Require the FULL stop name (not just
                                    # partial words) to appear in the article, PLUS a
                                    # dining signal, PLUS the city as a word boundary.
                                    # This prevents "Safari" in "Six Flags" + "nice"
                                    # (adjective) from passing.
                                    _full_stop_normalized = _strip_accents(stop_title).lower()
                                    art_has_full_stop = _full_stop_normalized in art_text
                                    if not art_has_full_stop:
                                        continue

                                    # City must appear as a word boundary (not as substring
                                    # of another word or as the English adjective "nice")
                                    art_has_city_proper = False
                                    for sig in _city_signals:
                                        # Word boundary: preceded/followed by non-alpha
                                        pattern = r'(?<![a-z])' + re.escape(sig) + r'(?![a-z])'
                                        if re.search(pattern, art_text):
                                            art_has_city_proper = True
                                            break
                                    if not art_has_city_proper:
                                        continue

                                    # Dining signal required
                                    _dining_sigs = ('restaurant', 'chef', 'michelin',
                                                    'cuisine', 'bistro', 'dining', 'food')
                                    art_has_dining = any(sig in art_text for sig in _dining_sigs)
                                    if not art_has_dining:
                                        continue

                                    return True, f"wikipedia_article: '{r_title}' extract mentions stop+city+dining"
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] Wikipedia search check failed for {stop_title!r}: {e}")

    # --- Check 3: French Wikipedia (restaurants in France often have fr.wiki coverage) ---
    try:
        # Summary lookup
        encoded_title_fr = quote(stop_title.strip().replace(" ", "_"), safe="")
        url_fr = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{encoded_title_fr}"
        resp_fr = _http.get(url_fr, headers=_HEADERS, timeout=8, allow_redirects=True)
        if resp_fr.status_code == 200:
            data_fr = resp_fr.json()
            extract_fr = data_fr.get("extract", "")
            title_fr = data_fr.get("title", "")
            description_fr = data_fr.get("description", "")
            full_text_fr = f"{extract_fr} {description_fr}".lower()
            full_text_fr_normalized = _strip_accents(full_text_fr)

            # LOCAL-320: Require BOTH city AND dining signal (same logic as Check 1).
            # Previously just city was enough — but "Le Safari" could resolve to
            # an unrelated article that mentions "nice" (the adjective).
            _restaurant_signals_fr = ('restaurant', 'chef', 'michelin', 'cuisine', 'etoile',
                                      'gastronomique', 'bistrot', 'brasserie', 'table', 'cuisinier')
            has_city_fr = _city_signals and any(sig in full_text_fr_normalized for sig in _city_signals)
            is_dining_fr = any(sig in full_text_fr_normalized for sig in _restaurant_signals_fr)

            if has_city_fr and is_dining_fr:
                return True, f"wikipedia_fr_summary: '{title_fr}' is dining+city (fr.wiki)"
            # If title matches exactly and it's clearly a restaurant, accept
            if is_dining_fr and _title_match(stop_title, title_fr):
                return True, f"wikipedia_fr_summary: '{title_fr}' is a restaurant (fr.wiki)"

        # French Wikipedia search (snippet-based)
        _search_variants_fr = [
            f'"{stop_title}" {city_hint} restaurant',
        ]
        if _clean_name != stop_title:
            _search_variants_fr.append(f'"{_clean_name}" {city_hint} restaurant')
            _search_variants_fr.append(f'{_clean_name} {city_hint} restaurant chef')

        for sq_fr in _search_variants_fr:
            resp_fr_search = _http.get(
                "https://fr.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": sq_fr,
                        "srnamespace": "0", "srlimit": "5", "format": "json"},
                headers=_HEADERS, timeout=8
            )
            if resp_fr_search.status_code == 200:
                results_fr = resp_fr_search.json().get("query", {}).get("search", [])
                for r in results_fr:
                    snippet_raw = r.get("snippet", "")
                    if _snippet_has_evidence(snippet_raw):
                        r_title = r.get("title", "")
                        return True, f"wikipedia_fr_search: snippet in '{r_title}' mentions stop+city"
                    # Fallback: if snippet mentions restaurant + stop but not city,
                    # fetch the article intro via action API and check for city there
                    snippet_clean_fr = _strip_accents(re.sub(r'<[^>]+>', '', snippet_raw)).lower()
                    snippet_clean_fr = snippet_clean_fr.replace('&#039;', "'").replace('&amp;', '&')
                    stop_in_fr = any(w in snippet_clean_fr for w in _stop_words)
                    _dining_in_fr = any(sig in snippet_clean_fr for sig in (
                        'restaurant', 'chef', 'hotel-restaurant', 'hôtel-restaurant',
                        'cuisine', 'gastronomique', 'bistrot'))
                    if stop_in_fr and _dining_in_fr:
                        try:
                            r_title_fr = r.get("title", "")
                            # LOCAL-320: Same rule as English path — article must be
                            # ABOUT the establishment. Title match = strong signal.
                            _article_is_about_stop_fr = _title_match(stop_title, r_title_fr)

                            # Fetch article extract via action API (full text, no truncation)
                            art_resp_fr = _http.get(
                                "https://fr.wikipedia.org/w/api.php",
                                params={"action": "query", "prop": "extracts",
                                        "titles": r_title_fr,
                                        "explaintext": "true",
                                        "format": "json"},
                                headers=_HEADERS, timeout=8
                            )
                            if art_resp_fr.status_code == 200:
                                pages = art_resp_fr.json().get("query", {}).get("pages", {})
                                for _, page in pages.items():
                                    art_text_fr = _strip_accents(page.get("extract", "")).lower()

                                    if _article_is_about_stop_fr:
                                        # Article IS the restaurant — city mention suffices
                                        art_has_city = any(sig in art_text_fr for sig in _city_signals)
                                        if art_has_city:
                                            return True, f"wikipedia_fr_article: '{r_title_fr}' is about establishment+city"
                                    else:
                                        # Article is about something else — require full
                                        # stop name + city as word boundary + dining signal
                                        _full_stop_norm_fr = _strip_accents(stop_title).lower()
                                        if _full_stop_norm_fr not in art_text_fr:
                                            continue
                                        # City as word boundary
                                        art_has_city_proper_fr = False
                                        for sig in _city_signals:
                                            pattern = r'(?<![a-z])' + re.escape(sig) + r'(?![a-z])'
                                            if re.search(pattern, art_text_fr):
                                                art_has_city_proper_fr = True
                                                break
                                        if not art_has_city_proper_fr:
                                            continue
                                        return True, f"wikipedia_fr_article: '{r_title_fr}' mentions stop+city (dining context)"
                        except Exception:
                            pass
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] French Wikipedia check failed for {stop_title!r}: {e}")

    # --- Check 4: Wikidata entity search ---
    try:
        wd_url = "https://www.wikidata.org/w/api.php"
        wd_params = {
            "action": "wbsearchentities",
            "search": stop_title,
            "language": "en",
            "limit": "5",
            "format": "json",
        }
        resp_wd = _http.get(wd_url, params=wd_params, headers=_HEADERS, timeout=8)
        if resp_wd.status_code == 200:
            wd_results = resp_wd.json().get("search", [])
            for wd_r in wd_results:
                wd_label = wd_r.get("label", "")
                wd_desc = wd_r.get("description", "").lower()
                wd_desc_normalized = _strip_accents(wd_desc)
                if _title_match(stop_title, wd_label):
                    # Check if description mentions the city or restaurant-related terms
                    if _city_signals and any(sig in wd_desc_normalized for sig in _city_signals):
                        return True, f"wikidata: '{wd_label}' (QID:{wd_r.get('id','?')}) description mentions city"
                    if any(sig in wd_desc for sig in ('restaurant', 'dining', 'chef', 'michelin', 'cuisine')):
                        return True, f"wikidata: '{wd_label}' (QID:{wd_r.get('id','?')}) is a restaurant"
        # Also try Wikidata in French
        wd_params_fr = {
            "action": "wbsearchentities",
            "search": stop_title,
            "language": "fr",
            "limit": "5",
            "format": "json",
        }
        resp_wd_fr = _http.get(wd_url, params=wd_params_fr, headers=_HEADERS, timeout=8)
        if resp_wd_fr.status_code == 200:
            wd_results_fr = resp_wd_fr.json().get("search", [])
            for wd_r in wd_results_fr:
                wd_label = wd_r.get("label", "")
                wd_desc = wd_r.get("description", "").lower()
                wd_desc_normalized = _strip_accents(wd_desc)
                if _title_match(stop_title, wd_label):
                    if _city_signals and any(sig in wd_desc_normalized for sig in _city_signals):
                        return True, f"wikidata_fr: '{wd_label}' (QID:{wd_r.get('id','?')}) description mentions city"
                    if any(sig in wd_desc for sig in ('restaurant', 'chef', 'michelin', 'cuisine',
                                                      'gastronomique', 'etoile')):
                        return True, f"wikidata_fr: '{wd_label}' (QID:{wd_r.get('id','?')}) is a restaurant"
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] Wikidata check failed for {stop_title!r}: {e}")

    # --- Check 5: Nominatim / OpenStreetMap (LOCAL-313) ---
    # Restaurants exist as POIs in OpenStreetMap even when they have no Wikipedia
    # or Wikidata entry. Nominatim's structured search returns amenity=restaurant
    # entries with addresses. This is the cheapest, most reliable source for
    # "does this establishment exist at this address in this city?"
    #
    # Proximity constraint: the result must be in the city extracted from
    # venue_name. A restaurant in Lyon must not pass for a Nice tour.
    #
    # LOCAL-320: RuntimeError from _nominatim_request means the search FAILED
    # (throttled/timeout/connection error). This MUST propagate — it is NOT
    # "no evidence", it is "could not search". D162: absence of evidence from
    # a failed search is not evidence of absence.
    try:
        verified_osm, evidence_osm = _check_dining_nominatim(stop_title, venue_name, _city_signals)
        if verified_osm:
            return True, evidence_osm
    except RuntimeError:
        # LOCAL-320: Search failure — propagate so gate classifies as "unknown"
        raise
    except Exception as e:
        logger.debug(f"[EXISTENCE-GATE] Nominatim check failed for {stop_title!r}: {e}")

    return False, ""


def _check_dining_nominatim(
    stop_title: str, venue_name: str, city_signals: Set[str]
) -> Tuple[bool, str]:
    """Check restaurant existence via Nominatim (OpenStreetMap) geocoding.

    LOCAL-313: Most restaurants do not have Wikipedia articles. They DO exist as
    named POIs in OpenStreetMap. Nominatim's search API returns structured results
    including the display name, address components, and category.

    LOCAL-320: All Nominatim requests are serialised through _nominatim_request()
    which enforces ≤1 req/s, a descriptive User-Agent, and bounded retry on 429.
    A throttled/failed lookup raises RuntimeError (classified as "unknown" by
    the caller), never returns False (which would mean "searched and not found").

    Strategy:
      1. Search Nominatim for the restaurant name + city.
      2. A result must:
         a) Have a name that fuzzy-matches the stop title.
         b) Be in the correct city (address.city or address.town matches).
         c) Be a plausible dining category (amenity, tourism, shop categories
            that include restaurants/cafes/bars).
      3. First match confirms existence.
    """
    # Build city hint for search constraint
    # For venue_names like "restaurant tour in Old Nice (Vieux Nice), France"
    # we need to extract the actual city name (Nice), not noise words.
    _venue_cleaned = re.sub(r'\([^)]*\)', ' ', venue_name)
    city_hint = ""
    _NOISE_WORDS = {
        'france', 'italy', 'spain', 'usa', 'uk', 'the', 'tour',
        'restaurant', 'food', 'dining', 'culinary', 'old', 'new',
        'vieux', 'in', 'stop', 'stops',
    }
    for part in re.split(r'[,\s]+', _venue_cleaned):
        part_clean = part.strip()
        # Remove punctuation
        part_alpha = re.sub(r'[^a-zA-ZÀ-ÿ]', '', part_clean)
        if len(part_alpha) >= 3 and part_alpha.lower() not in _NOISE_WORDS:
            # Prefer a word that starts with uppercase (proper noun = city name)
            if part_alpha[0].isupper():
                city_hint = part_alpha
                break
    # Fallback: just use first qualifying city signal
    if not city_hint and city_signals:
        city_hint = next(iter(city_signals))

    if not city_hint:
        return False, ""

    # Nominatim search: "restaurant_name, city"
    search_query = f"{stop_title}, {city_hint}"
    params = {
        "q": search_query,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "5",
        "accept-language": "en,fr",
    }

    # LOCAL-320: Use shared throttled request (≤1/s, retries on 429)
    resp = _nominatim_request(params, context=stop_title)

    results = resp.json()
    if not results:
        return False, ""

    # Normalize stop title for matching
    norm_stop = _strip_accents(stop_title).lower()
    # Extract significant words for matching (≥3 chars, no articles)
    _stop_words_osm = [w for w in re.split(r"[\s'\u2019-]+", norm_stop)
                       if len(w) >= 3 and w not in ('the', 'les', 'des', 'une', 'la', 'le', 'du', 'chez')]

    # Dining-related OSM categories
    _DINING_CATEGORIES = (
        'restaurant', 'cafe', 'bar', 'pub', 'fast_food', 'bistro',
        'brasserie', 'food_court', 'ice_cream',
    )
    # Also accept by category/type fields in Nominatim results
    _DINING_TYPE_SIGNALS = (
        'restaurant', 'cafe', 'bar', 'pub', 'amenity', 'food',
        'bistro', 'brasserie',
    )

    for result in results:
        display_name = result.get("display_name", "")
        name = result.get("name", "")
        category = result.get("category", "")
        osm_type = result.get("type", "")
        address = result.get("address", {})

        # --- Name match: does this result refer to our restaurant? ---
        norm_name = _strip_accents(name).lower() if name else ""
        norm_display = _strip_accents(display_name).lower()

        # Check: at least 50% of stop words appear in result name or display_name
        name_words_hit = sum(1 for w in _stop_words_osm if w in norm_name or w in norm_display)
        if _stop_words_osm and name_words_hit < max(1, len(_stop_words_osm) * 0.5):
            continue

        # --- City match: is this result in the correct city? ---
        # LOCAL-320: Proximity MUST bind — a Chicago address must not pass for Nice.
        # Check structured address fields (not just display_name substring).
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("municipality", "") or address.get("village", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        result_county = _strip_accents(address.get("county", "")).lower()

        city_match = False
        for sig in city_signals:
            if sig in result_city or sig in result_state or sig in result_county:
                city_match = True
                break
        # Also check display_name for city signal (but only structured address
        # above truly guarantees proximity — this is a soft fallback)
        if not city_match:
            for sig in city_signals:
                if sig in norm_display:
                    city_match = True
                    break

        if not city_match:
            # LOCAL-320: Log the rejection so it's visible in diagnostics
            logger.debug(f"[EXISTENCE-GATE] Nominatim result '{name}' in "
                         f"'{result_city}' rejected — not in {city_signals}")
            continue

        # --- Category match: is this a dining establishment? ---
        # Nominatim returns category+type (e.g. category=amenity, type=restaurant)
        is_dining = (
            osm_type in _DINING_CATEGORIES or
            category in ('amenity',) and osm_type in _DINING_CATEGORIES or
            any(sig in osm_type for sig in _DINING_TYPE_SIGNALS) or
            any(sig in category for sig in _DINING_TYPE_SIGNALS)
        )

        # For well-known names, even if OSM category is 'tourism' or 'building',
        # accept if the name is a strong match (≥75% of words)
        strong_name_match = (
            _stop_words_osm and
            name_words_hit >= max(1, len(_stop_words_osm) * 0.75)
        )

        if is_dining or strong_name_match:
            addr_str = ""
            street = address.get("road", "")
            house = address.get("house_number", "")
            if street:
                addr_str = f" ({house} {street}, {result_city})".strip() if house else f" ({street}, {result_city})"
            return True, (f"nominatim_osm: '{name}' found in {result_city or city_hint}"
                          f"{addr_str} [category={category}/{osm_type}]")

    return False, ""


def _check_business_existence(
    stop_title: str, venue_name: str, city_signals: Set[str]
) -> Tuple[bool, str, Optional[Tuple[float, float]]]:
    """[LOCAL-779] Existence check for a BUSINESS stop via a maps/places lookup.

    This is the restaurant maps/places path (``_check_dining_nominatim``)
    generalized to any commercial POI — gyms, cafés, shops, bakeries, bars, spas,
    climbing walls. The question is the same one the restaurant path asks: "does a
    place with THIS name exist at an address INSIDE this scope?" A listing that
    matches by name and sits in the toured city is the evidence; its coordinates
    come straight from the result so the stop lands on the map at a real address.

    A fabricated branch (a name with no listing anywhere, or a listing in the
    wrong city) returns ``(False, "", None)`` and is dropped by ENFORCE, exactly
    as a fabricated landmark is.

    LOCAL-320 contract: all OSM calls go through ``_nominatim_request`` which
    raises RuntimeError on a throttled/failed lookup; that propagates so the gate
    classifies the stop as UNKNOWN (kept, retried) rather than searched-and-absent.

    Returns ``(verified, evidence, coords)`` where coords is ``(lat, lng)`` from
    the matched listing, or None when unverified.
    """
    # City hint for the search query — same extraction the dining path uses.
    _venue_cleaned = re.sub(r'\([^)]*\)', ' ', venue_name or '')
    city_hint = ""
    _NOISE_WORDS = {
        'france', 'italy', 'spain', 'usa', 'uk', 'the', 'tour', 'tours',
        'walking', 'cycling', 'biking', 'driving', 'near', 'me', 'in', 'of',
        'gym', 'gyms', 'cafe', 'cafes', 'coffee', 'shop', 'shops', 'store',
        'stores', 'bakery', 'bar', 'bars', 'fitness', 'stop', 'stops',
    }
    for part in re.split(r'[,\s]+', _venue_cleaned):
        part_alpha = re.sub(r'[^a-zA-ZÀ-ÿ]', '', part.strip())
        if len(part_alpha) >= 3 and part_alpha.lower() not in _NOISE_WORDS:
            if part_alpha[0].isupper():
                city_hint = part_alpha
                break
    if not city_hint and city_signals:
        city_hint = next(iter(city_signals))
    if not city_hint:
        return False, "", None

    params = {
        "q": f"{stop_title}, {city_hint}",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "5",
        "accept-language": "en,fr",
    }
    resp = _nominatim_request(params, context=stop_title)
    results = resp.json()
    if not results:
        return False, "", None

    norm_stop = _strip_accents(stop_title).lower()
    _stop_words = [w for w in re.split(r"[\s'\u2019-]+", norm_stop)
                   if len(w) >= 3 and w not in ('the', 'les', 'des', 'une', 'la', 'le', 'du')]

    for result in results:
        display_name = result.get("display_name", "")
        name = result.get("name", "")
        category = result.get("category", "")
        osm_type = result.get("type", "")
        address = result.get("address", {})

        # --- Name match ---
        norm_name = _strip_accents(name).lower() if name else ""
        norm_display = _strip_accents(display_name).lower()
        name_words_hit = sum(1 for w in _stop_words if w in norm_name or w in norm_display)
        if _stop_words and name_words_hit < max(1, len(_stop_words) * 0.5):
            continue

        # --- City/scope match: proximity MUST bind (a Dallas gym must not pass
        #     for a West Roxbury tour). Structured address fields first. ---
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("municipality", "") or address.get("village", "") or
            address.get("suburb", "") or address.get("neighbourhood", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        result_county = _strip_accents(address.get("county", "")).lower()
        city_match = False
        for sig in city_signals:
            if sig and (sig in result_city or sig in result_state or sig in result_county):
                city_match = True
                break
        if not city_match:
            for sig in city_signals:
                if sig and sig in norm_display:
                    city_match = True
                    break
        if not city_match:
            logger.debug(f"[EXISTENCE-GATE] Business result '{name}' in "
                         f"'{result_city}' rejected — not in {city_signals}")
            continue

        # --- Category match: is this a commercial/business POI? ---
        is_business = (
            osm_type in _BUSINESS_OSM_TYPES or
            category in _BUSINESS_OSM_CATEGORIES or
            any(sig in osm_type for sig in _BUSINESS_OSM_TYPES)
        )
        strong_name_match = (
            _stop_words and
            name_words_hit >= max(1, len(_stop_words) * 0.75)
        )
        if is_business or strong_name_match:
            # Coordinates from the matched listing.
            coords = None
            try:
                coords = (float(result["lat"]), float(result["lon"]))
            except (KeyError, ValueError, TypeError):
                coords = None
            street = address.get("road", "")
            house = address.get("house_number", "")
            if street:
                addr_str = f" ({house} {street}, {result_city})".strip() if house else f" ({street}, {result_city})"
            else:
                addr_str = f" ({result_city})" if result_city else ""
            evidence = (f"nominatim_osm: '{name}' found in {result_city or city_hint}"
                        f"{addr_str} [category={category}/{osm_type}]")
            return True, evidence, coords

    return False, "", None


def business_replenish_candidates(
    poi_type: str,
    scope: str,
    needed: int,
    exclude: Optional[Set[str]] = None,
    device_coords: Optional[Tuple[float, float]] = None,
) -> List[Dict]:
    """[LOCAL-779] Replenish a BUSINESS tour from a maps/places search directly.

    When the existence gate drops business stops and the tour is short, the right
    refill is NOT to ask an LLM for more names (it invents branches) — it is to ask
    the MAP for "<poi_type> in <scope>" and take the real listings it returns. Each
    candidate is already verified by construction (it came from the maps provider),
    carries a real address and coordinates, and is ranked by distance to the device
    (when the request said "near me" and the app sent coordinates) or to the scope
    centre otherwise.

    Pure w.r.t. the network seam: all OSM calls go through ``_nominatim_request``,
    which the tests monkeypatch. Raises nothing — a failed search yields [].

    Returns a list of ``{"name", "address", "coordinates", "lat", "lng",
    "evidence", "verified": True}`` dicts, at most ``needed`` long, nearest first.
    """
    exclude = {e.lower() for e in (exclude or set())}
    _pt = (poi_type or '').strip() or 'places'
    _scope = (scope or '').strip()
    if not _scope:
        return []

    # Rank origin: device coords when provided ("near me"), else the scope centre.
    origin = device_coords
    if origin is None:
        try:
            origin = _geocode_city_center(_scope, _city_signals_from_venue(_scope))
        except RuntimeError:
            origin = None

    params = {
        "q": f"{_pt} in {_scope}",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "20",
        "accept-language": "en",
    }
    try:
        resp = _nominatim_request(params, context=f"replenish:{_pt}@{_scope}")
        results = resp.json() or []
    except RuntimeError as e:
        logger.warning(f"[LOCAL-779] business replenish search failed: {e}")
        return []

    _scope_signals = _city_signals_from_venue(_scope)
    out = []
    for r in results:
        name = (r.get("name") or "").strip()
        if not name or name.lower() in exclude:
            continue
        category = r.get("category", "")
        osm_type = r.get("type", "")
        is_business = (
            osm_type in _BUSINESS_OSM_TYPES or
            category in _BUSINESS_OSM_CATEGORIES or
            any(sig in osm_type for sig in _BUSINESS_OSM_TYPES)
        )
        if not is_business:
            continue
        address = r.get("address", {})
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("municipality", "") or address.get("village", "") or
            address.get("suburb", "") or address.get("neighbourhood", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        # Scope proximity must bind — reject a same-named place elsewhere.
        if _scope_signals:
            if not any(sig and (sig in result_city or sig in result_state)
                       for sig in _scope_signals):
                _disp = _strip_accents(r.get("display_name", "")).lower()
                if not any(sig and sig in _disp for sig in _scope_signals):
                    continue
        try:
            lat, lng = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError, TypeError):
            continue
        street = address.get("road", "")
        house = address.get("house_number", "")
        if street:
            addr_str = f"{house} {street}, {result_city}".strip() if house else f"{street}, {result_city}"
        else:
            addr_str = r.get("display_name", "")
        out.append({
            "name": name,
            "address": addr_str,
            "coordinates": f"{lat},{lng}",
            "lat": lat,
            "lng": lng,
            "evidence": (f"nominatim_osm (replenish): '{name}' in "
                         f"{result_city or _scope} [category={category}/{osm_type}]"),
            "verified": True,
            "_dist": (_haversine_km_local(origin, (lat, lng)) if origin else 0.0),
        })
        exclude.add(name.lower())

    # Rank by distance (nearest first) when we have an origin; stable otherwise.
    out.sort(key=lambda d: d["_dist"])
    for d in out:
        d.pop("_dist", None)
    return out[:max(0, needed)]


# ──── [LOCAL-779B] DINING (RESTAURANT) MAPS-DIRECT CANDIDATES + CUISINE MATCH ──
# The LOCAL-779 LEAD bounce: a restaurant tour ("middle eastern restaurants near
# me, west Roxbury, MA") still failed because the dining category took its
# candidates ONLY from the LLM — which invented places in the wrong town (Newton)
# — and when PHASE 3C removed them nothing refilled from the map. The business
# path already refills from "<poi_type> in <scope>"; a restaurant poi_type just
# never reached it (it classifies as 'dining', and only 'business' was wired to
# business_replenish_candidates). The right refill for a restaurant is the same:
# ask the MAP for "<cuisine> restaurants in <scope>", keep the in-scope listings,
# and (unlike a generic business) enforce that the CUISINE matches.

# OSM amenity/type tokens that mark a dining establishment.
_DINING_OSM_TYPES = (
    'restaurant', 'cafe', 'bar', 'pub', 'fast_food', 'bistro', 'brasserie',
    'food_court', 'ice_cream', 'biergarten',
)

# Cuisine qualifier → the OSM `cuisine=` tokens / name-keywords that satisfy it.
# A listing matches a requested cuisine when its cuisine tag (or, absent a tag,
# its name/description) contains any of these. Deliberately curated so that a
# clear mismatch (Chinese "Dumpling House" for a Middle-Eastern request) is
# rejected while a genuine match (Lebanese, Turkish, shawarma, Sofra) is kept.
_CUISINE_SYNONYMS = {
    'middle eastern': (
        'middle_eastern', 'middle eastern', 'lebanese', 'turkish', 'arab',
        'arabic', 'persian', 'iranian', 'syrian', 'israeli', 'egyptian',
        'moroccan', 'mediterranean', 'shawarma', 'kebab', 'falafel', 'mezze',
        'halal', 'sofra', 'hummus', 'levantine', 'armenian',
    ),
    'italian': (
        'italian', 'pizza', 'pizzeria', 'pasta', 'trattoria', 'osteria',
        'ristorante', 'sicilian', 'tuscan', 'neapolitan',
    ),
    'mexican': ('mexican', 'taqueria', 'taco', 'tacos', 'burrito', 'tex-mex', 'tex_mex'),
    'chinese': ('chinese', 'dim_sum', 'dim sum', 'dumpling', 'dumplings', 'szechuan',
                'sichuan', 'cantonese', 'hunan', 'noodle', 'wok'),
    'japanese': ('japanese', 'sushi', 'ramen', 'izakaya', 'yakitori', 'tempura', 'udon'),
    'thai': ('thai', 'pad_thai', 'pad thai'),
    'indian': ('indian', 'tandoori', 'curry', 'biryani', 'punjabi', 'south_indian'),
    'french': ('french', 'brasserie', 'bistro', 'patisserie', 'creperie', 'crêperie'),
    'greek': ('greek', 'gyro', 'gyros', 'souvlaki', 'taverna'),
    'korean': ('korean', 'bbq', 'bibimbap', 'kimchi'),
    'vietnamese': ('vietnamese', 'pho', 'banh_mi', 'banh mi'),
    'spanish': ('spanish', 'tapas', 'paella'),
    'american': ('american', 'burger', 'burgers', 'bbq', 'barbecue', 'diner', 'steakhouse', 'steak'),
    'seafood': ('seafood', 'fish', 'oyster', 'lobster', 'raw_bar'),
    'sushi': ('sushi', 'japanese'),
    'vegan': ('vegan', 'vegetarian', 'plant_based'),
    'vegetarian': ('vegetarian', 'vegan'),
}

# Generic dining words that are NOT a cuisine qualifier (a bare "restaurant tour"
# has no cuisine constraint and matches any dining listing).
_GENERIC_DINING_WORDS = {
    'restaurant', 'restaurants', 'dining', 'food', 'foods', 'culinary', 'eatery',
    'eateries', 'bistro', 'bistros', 'brasserie', 'cafe', 'cafes', 'café', 'cafés',
    'cuisine', 'tour', 'tours', 'near', 'me', 'in', 'of', 'the', 'and', 'or',
    'places', 'place', 'spot', 'spots', 'best', 'top', 'good', 'great',
}


def _extract_cuisine_qualifier(poi_type: Optional[str]) -> str:
    """[LOCAL-779B] Pull the CUISINE/sub-type qualifier out of a dining poi_type.

    "middle eastern restaurants" → "middle eastern"; "Italian restaurants" →
    "italian"; "thai food" → "thai"; a bare "restaurants"/"dining" → "" (no
    cuisine constraint). Deterministic string surgery — it strips the generic
    dining words and returns what remains, lowercased and accent-folded.
    """
    if not poi_type:
        return ''
    raw = poi_type if isinstance(poi_type, str) else ' or '.join(poi_type)
    tl = _strip_accents(raw).lower()
    tl = tl.replace('/', ' ').replace('-', ' ')
    toks = [t for t in re.split(r'[^a-z]+', tl) if t]
    kept = [t for t in toks if t not in _GENERIC_DINING_WORDS]
    return ' '.join(kept).strip()


def _cuisine_from_request(request: Optional[str]) -> str:
    """[LOCAL-779B] Recover a CUISINE from a free-text request when the intent's
    poi_type dropped it (the live LLM often returns a bare "restaurants" for
    "middle eastern restaurants near me, …"). Scans the request for a known
    cuisine KEY (longest first, so "middle eastern" beats a bare word) and then
    for any cuisine SYNONYM. Returns the canonical cuisine key, or ''.

    Deterministic, no network. "middle eastern restaurants near me, west Roxbury,
    MA" → "middle eastern"; "Italian restaurants in the North End" → "italian";
    "restaurants in Newton" → "".
    """
    if not request:
        return ''
    tl = _strip_accents(request).lower().replace('_', ' ')
    tl = re.sub(r'[^a-z ]+', ' ', tl)
    tl = ' ' + ' '.join(tl.split()) + ' '
    # Match a canonical cuisine key first (multi-word keys like "middle eastern"
    # take priority — check longest keys first).
    for key in sorted(_CUISINE_SYNONYMS.keys(), key=len, reverse=True):
        if f' {key} ' in tl:
            return key
    # Then any synonym → map back to its canonical key.
    for key, syns in _CUISINE_SYNONYMS.items():
        for syn in syns:
            s = _strip_accents(syn).lower().replace('_', ' ')
            if len(s) >= 4 and f' {s} ' in tl:
                return key
    return ''


def _listing_cuisine_tokens(listing: Dict) -> str:
    """Collect the text that can carry a listing's cuisine: the OSM cuisine tag,
    then the name/display_name/type. Lowercased, accent-folded, joined."""
    parts = []
    extratags = listing.get('extratags') or {}
    if isinstance(extratags, dict):
        for k in ('cuisine', 'amenity', 'description', 'diet:vegan', 'diet:vegetarian'):
            v = extratags.get(k)
            if v:
                parts.append(str(v))
    for k in ('name', 'display_name', 'type', 'category'):
        v = listing.get(k)
        if v:
            parts.append(str(v))
    blob = _strip_accents(' '.join(parts)).lower()
    return blob.replace('_', ' ')


def cuisine_matches(cuisine: str, listing: Dict) -> bool:
    """[LOCAL-779B] Does a maps listing satisfy the requested CUISINE?

    An empty cuisine (a bare "restaurants" request) matches any dining listing.
    Otherwise the listing's cuisine tag (or, absent a tag, its name/description)
    must contain one of the cuisine's synonyms. "Dumpling House" (chinese) does
    NOT satisfy "middle eastern"; "Sofra Bakery & Café" (a Middle-Eastern café)
    and "Mamma Maria" (italian) are classified by their own cuisine — the
    "Mamma Maria is Italian, not Middle Eastern" guard.
    """
    cuisine = (cuisine or '').strip().lower()
    if not cuisine:
        return True
    blob = _listing_cuisine_tokens(listing)
    synonyms = _CUISINE_SYNONYMS.get(cuisine)
    if synonyms is None:
        # Unknown cuisine: fall back to a direct token containment of the request
        # words (each >= 3 chars) in the listing text.
        words = [w for w in cuisine.split() if len(w) >= 3]
        return any(w in blob for w in words) if words else True
    for syn in synonyms:
        s = _strip_accents(syn).lower().replace('_', ' ')
        if s in blob:
            return True
    return False


def cuisine_conflict(cuisine: str, listing: Dict) -> bool:
    """[LOCAL-779B] Does a listing POSITIVELY declare a DIFFERENT cuisine?

    Stricter-than-mismatch, used to vet an LLM-proposed survivor: we only drop it
    when the listing carries a clear signal of ANOTHER cuisine (an OSM
    ``cuisine=chinese`` tag, or a name like "Dumpling House"), never merely for
    the ABSENCE of a matching tag. OSM cuisine tags are sparse — a real North-End
    Italian place ("Mamma Maria") often has no cuisine tag at all, and dropping it
    for that would be wrong. So:

      * returns True  → the listing matches some OTHER cuisine and NOT the
                        requested one → a real conflict → drop it.
      * returns False → either it matches the requested cuisine, or it declares no
                        cuisine at all (UNKNOWN → keep).

    Dumpling House (chinese) vs "middle eastern" → True (drop). Mamma Maria (no
    tag) vs "italian" → False (keep). Mamma Maria (italian) vs "middle eastern" →
    True (drop) — the guard still holds when the tag is present.
    """
    cuisine = (cuisine or '').strip().lower()
    if not cuisine:
        return False
    # If it matches the requested cuisine, there is no conflict.
    if cuisine_matches(cuisine, listing):
        return False
    blob = _listing_cuisine_tokens(listing)
    # Is there a POSITIVE signal of a different known cuisine?
    for other, syns in _CUISINE_SYNONYMS.items():
        if other == cuisine:
            continue
        for syn in syns:
            s = _strip_accents(syn).lower().replace('_', ' ')
            # Require a reasonably specific token (avoid 'bar'/'bbq' collisions):
            # a cuisine tag match, or a >=4-char synonym appearing in the name.
            if len(s) >= 4 and s in blob:
                return True
    return False


def dining_replenish_candidates(
    poi_type: str,
    scope: str,
    needed: int,
    exclude: Optional[Set[str]] = None,
    device_coords: Optional[Tuple[float, float]] = None,
    cuisine: Optional[str] = None,
) -> List[Dict]:
    """[LOCAL-779B] Replenish a RESTAURANT tour from a maps/places search directly.

    The dining analogue of ``business_replenish_candidates``: ask the MAP for
    "<poi_type> in <scope>" (e.g. "middle eastern restaurants in West Roxbury,
    MA"), keep the listings that are a DINING category AND lie inside the scope
    AND whose CUISINE matches the qualifier, ranked by distance to the device
    ("near me") or the scope centre. Each candidate is verified by construction
    (it came from the maps provider), carries a real address + coordinates.

    When the area has no matching place, returns [] so the caller can refuse
    cleanly with a "widen the area" suggestion.

    Pure w.r.t. the network seam: all OSM calls go through ``_nominatim_request``,
    which the tests monkeypatch. A failed search yields [].

    Returns ``{"name", "address", "coordinates", "lat", "lng", "cuisine",
    "evidence", "verified": True}`` dicts, at most ``needed`` long, nearest first.
    """
    exclude = {e.lower() for e in (exclude or set())}
    _pt = (poi_type or '').strip() or 'restaurants'
    _scope = (scope or '').strip()
    if not _scope:
        return []
    # Cuisine: explicit override (recovered from the request) wins; else parse the
    # poi_type. A bare "restaurants" poi_type whose request said "middle eastern"
    # must still filter to Middle-Eastern places.
    _cuisine = (cuisine or '').strip().lower() or _extract_cuisine_qualifier(_pt)
    # Build the maps query with the cuisine up front so the provider returns the
    # right places ("middle eastern restaurants in …"), even when poi_type is bare.
    _q_pt = _pt
    if _cuisine and _cuisine not in _strip_accents(_pt).lower():
        _q_pt = f"{_cuisine} {_pt}"

    origin = device_coords
    if origin is None:
        try:
            origin = _geocode_city_center(_scope, _city_signals_from_venue(_scope))
        except RuntimeError:
            origin = None

    params = {
        "q": f"{_q_pt} in {_scope}",
        "format": "jsonv2",
        "addressdetails": "1",
        "extratags": "1",
        "limit": "25",
        "accept-language": "en",
    }
    try:
        resp = _nominatim_request(params, context=f"dining-replenish:{_q_pt}@{_scope}")
        results = resp.json() or []
    except RuntimeError as e:
        logger.warning(f"[LOCAL-779B] dining replenish search failed: {e}")
        return []

    _scope_signals = _city_signals_from_venue(_scope)
    out = []
    for r in results:
        name = (r.get("name") or "").strip()
        if not name or name.lower() in exclude:
            continue
        category = r.get("category", "")
        osm_type = r.get("type", "")
        is_dining = (
            osm_type in _DINING_OSM_TYPES or
            (category == 'amenity' and osm_type in _DINING_OSM_TYPES) or
            any(sig in osm_type for sig in _DINING_OSM_TYPES)
        )
        if not is_dining:
            continue
        # Scope proximity must bind — reject a same-cuisine place elsewhere.
        address = r.get("address", {})
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("municipality", "") or address.get("village", "") or
            address.get("suburb", "") or address.get("neighbourhood", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        if _scope_signals:
            if not any(sig and (sig in result_city or sig in result_state)
                       for sig in _scope_signals):
                _disp = _strip_accents(r.get("display_name", "")).lower()
                if not any(sig and sig in _disp for sig in _scope_signals):
                    continue
        # Cuisine/qualifier must match (Dumpling House rejected for Middle Eastern).
        if not cuisine_matches(_cuisine, r):
            logger.debug(f"[LOCAL-779B] '{name}' rejected — cuisine mismatch for "
                         f"{_cuisine!r}")
            continue
        try:
            lat, lng = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError, TypeError):
            continue
        street = address.get("road", "")
        house = address.get("house_number", "")
        if street:
            addr_str = f"{house} {street}, {result_city}".strip() if house else f"{street}, {result_city}"
        else:
            addr_str = r.get("display_name", "")
        _listing_cuisine = ''
        _et = r.get('extratags') or {}
        if isinstance(_et, dict):
            _listing_cuisine = (_et.get('cuisine') or '')
        out.append({
            "name": name,
            "address": addr_str,
            "coordinates": f"{lat},{lng}",
            "lat": lat,
            "lng": lng,
            "cuisine": _listing_cuisine,
            "evidence": (f"nominatim_osm (dining-replenish): '{name}' in "
                         f"{result_city or _scope} [category={category}/{osm_type}"
                         f"{(', cuisine=' + _listing_cuisine) if _listing_cuisine else ''}]"),
            "verified": True,
            "_dist": (_haversine_km_local(origin, (lat, lng)) if origin else 0.0),
        })
        exclude.add(name.lower())

    out.sort(key=lambda d: d["_dist"])
    for d in out:
        d.pop("_dist", None)
    return out[:max(0, needed)]


def verify_listing_cuisine(name: str, scope: str, cuisine: str) -> Optional[bool]:
    """[LOCAL-779B] Does the maps listing for THIS named place match the cuisine?

    Used to vet an LLM-proposed restaurant that survived the PHASE 3C address
    guard — the ticket's rule: an LLM candidate counts only if its listing
    verifies inside the scope AND its cuisine is not a different one. Looks the
    name up on the map (name + scope, extratags=1) and applies ``cuisine_conflict``
    to the first in-scope hit — so a real place with no OSM cuisine tag is KEPT
    (OSM tags are sparse) and only a positively-different cuisine is dropped.

    Returns:
      * True  — a listing was found with no conflicting cuisine (keep).
      * False — a listing was found that positively declares a DIFFERENT cuisine
                (drop it — e.g. Dumpling House for a Middle-Eastern request).
      * None  — no listing found, or the lookup failed (UNKNOWN; the caller
                decides — D162, never treat a failed search as a mismatch).
    """
    _cuisine = (cuisine or '').strip().lower()
    if not _cuisine:
        return True
    _scope = (scope or '').strip()
    if not name or not _scope:
        return None
    params = {
        "q": f"{name}, {_scope}",
        "format": "jsonv2",
        "addressdetails": "1",
        "extratags": "1",
        "limit": "5",
        "accept-language": "en",
    }
    try:
        resp = _nominatim_request(params, context=f"cuisine-verify:{name}@{_scope}")
        results = resp.json() or []
    except RuntimeError:
        return None
    if not results:
        return None
    _scope_signals = _city_signals_from_venue(_scope)
    norm_name = _strip_accents(name).lower()
    _nw = [w for w in re.split(r"[\s'\u2019-]+", norm_name) if len(w) >= 3]
    for r in results:
        _rn = _strip_accents(r.get("name", "") or r.get("display_name", "")).lower()
        if _nw and sum(1 for w in _nw if w in _rn) < max(1, len(_nw) * 0.5):
            continue
        address = r.get("address", {})
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("suburb", "") or address.get("neighbourhood", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        if _scope_signals and not any(
                sig and (sig in result_city or sig in result_state or
                         sig in _strip_accents(r.get("display_name", "")).lower())
                for sig in _scope_signals):
            continue
        # Drop ONLY on a positive different-cuisine signal (OSM cuisine tags are
        # sparse; absence of a matching tag is UNKNOWN, not a mismatch). This keeps
        # a real "Mamma Maria" for an Italian request while still dropping a
        # "Dumpling House" for a Middle-Eastern one.
        return not cuisine_conflict(_cuisine, r)
    return None


def verify_listing_in_scope(name: str, scope: str) -> Optional[bool]:
    """[LOCAL-779B] Does a maps listing for THIS named place EXIST inside the scope?

    The ticket's rule: "Use LLM candidates only as an extra source, and only if
    their listing verifies inside the scope." An LLM-proposed restaurant counts
    only when the MAP actually carries a listing by that name within the scope —
    otherwise it is an invented place (the LOCAL-779 bounce delivered a made-up
    "Mamma Maria's" in West Roxbury whose address merely looked right). This is a
    pure EXISTENCE check (no cuisine), the companion to ``verify_listing_cuisine``.

    Returns:
      * True  — a listing whose name matches was found inside the scope.
      * False — the map returned listings for the query but none matched the name
                inside the scope (the named place is not there).
      * None  — the lookup failed (network/RuntimeError). UNKNOWN; the caller
                decides. A successful-but-empty response is False, not None: the
                provider answered and the place was not found.
    """
    _scope = (scope or '').strip()
    if not name or not _scope:
        return None
    params = {
        "q": f"{name}, {_scope}",
        "format": "jsonv2",
        "addressdetails": "1",
        "extratags": "1",
        "limit": "5",
        "accept-language": "en",
    }
    try:
        resp = _nominatim_request(params, context=f"exists-verify:{name}@{_scope}")
        results = resp.json() or []
    except RuntimeError:
        return None
    _scope_signals = _city_signals_from_venue(_scope)
    norm_name = _strip_accents(name).lower()
    _nw = [w for w in re.split(r"[\s'\u2019-]+", norm_name) if len(w) >= 3]
    for r in results:
        _rn = _strip_accents(r.get("name", "") or r.get("display_name", "")).lower()
        if _nw and sum(1 for w in _nw if w in _rn) < max(1, len(_nw) * 0.5):
            continue
        address = r.get("address", {})
        result_city = _strip_accents(
            address.get("city", "") or address.get("town", "") or
            address.get("suburb", "") or address.get("neighbourhood", "")
        ).lower()
        result_state = _strip_accents(address.get("state", "")).lower()
        if _scope_signals and not any(
                sig and (sig in result_city or sig in result_state or
                         sig in _strip_accents(r.get("display_name", "")).lower())
                for sig in _scope_signals):
            continue
        return True
    # The provider answered but no listing matched the name inside the scope.
    return False


def _haversine_km_local(a, b) -> float:
    """Great-circle distance in km between two (lat, lng) pairs; inf if either None."""
    import math as _m
    if not a or not b:
        return float('inf')
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = _m.radians(lat1), _m.radians(lat2)
    dphi = _m.radians(lat2 - lat1)
    dlmb = _m.radians(lon2 - lon1)
    h = _m.sin(dphi / 2) ** 2 + _m.cos(p1) * _m.cos(p2) * _m.sin(dlmb / 2) ** 2
    return 2 * r * _m.asin(min(1.0, _m.sqrt(h)))


def _city_signals_from_venue(venue_name: str) -> Set[str]:
    """[LOCAL-779] Extract city/region proper-noun signals from a venue label.

    "Walking tour in Boston dedicated to Massachusetts politics …, Boston, MA"
    → {'boston', 'massachusetts'} (noise words — walking/tour/dedicated/politics
    and bare US state abbreviations — are dropped). Used to confirm a Wikidata /
    OSM hit is in the toured city, not a same-named place elsewhere.
    """
    _NOISE = {
        'walking', 'cycling', 'biking', 'driving', 'tour', 'tours', 'area',
        'dedicated', 'politics', 'current', 'affairs', 'history', 'historical',
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'about', 'through',
        'usa', 'uk', 'stop', 'stops', 'visit', 'guide', 'self', 'guided',
        'downtown', 'old', 'new', 'city', 'town', 'center', 'centre', 'district',
    }
    _US_STATE_ABBR = {
        'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id',
        'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms',
        'mo', 'mt', 'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc', 'nd', 'oh', 'ok',
        'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv',
        'wi', 'wy', 'dc',
    }
    signals: Set[str] = set()
    _cleaned = re.sub(r'\([^)]*\)', ' ', venue_name or '')
    for part in re.split(r'[,\s]+', _cleaned):
        p = _strip_accents(part).lower().strip()
        p = re.sub(r'[^a-z]', '', p)
        if len(p) < 3:
            continue
        if p in _NOISE or p in _US_STATE_ABBR:
            continue
        signals.add(p)
    return signals


def _geocode_city_center(venue_name: str, city_signals: Set[str]):
    """[LOCAL-779] Geocode the toured city to a (lat, lng) center via Nominatim.

    Returns None when no usable city token is found. Raises RuntimeError on a
    throttled/failed lookup (LOCAL-320) so the caller classifies the stop as
    UNKNOWN rather than searched-and-absent.
    """
    # Prefer a proper-noun city token (first capitalized word) from the raw label.
    _cleaned = re.sub(r'\([^)]*\)', ' ', venue_name or '')
    city_hint = ''
    _NOISE = {'walking', 'cycling', 'biking', 'driving', 'tour', 'tours', 'in',
              'the', 'area', 'dedicated', 'to', 'of', 'a', 'self', 'guided'}
    for part in re.split(r'[,\s]+', _cleaned):
        p = part.strip()
        alpha = re.sub(r'[^a-zA-ZÀ-ÿ]', '', p)
        if len(alpha) >= 3 and alpha.lower() not in _NOISE and alpha[0].isupper():
            city_hint = alpha
            break
    if not city_hint and city_signals:
        city_hint = next(iter(city_signals))
    if not city_hint:
        return None
    params = {
        "q": city_hint,
        "format": "jsonv2",
        "limit": "1",
        "accept-language": "en",
    }
    resp = _nominatim_request(params, context=f"city:{city_hint}")
    results = resp.json()
    if not results:
        return None
    try:
        return (float(results[0]["lat"]), float(results[0]["lon"]))
    except (KeyError, ValueError, IndexError):
        return None


def verify_stop_existence(
    stop_title: str,
    venue_name: str,
    db_conn,
    tour_type: Optional[str] = None,
    poi_type: Optional[str] = None,
) -> Dict:
    """Verify whether a stop actually exists at the claimed venue.

    LOCAL-239: Uses venue kind to determine verification strictness:
      - institution: source must tie the object to THAT institution (D74, D127)
      - geographic_area: stop must be a real place in the region (relaxed)
    LOCAL-281: Added 'dining' kind for restaurant tours.
      - dining: establishment must have external evidence of existence at the
        location (Wikipedia, Wikidata, or authoritative culinary source).
    LOCAL-779: Added 'business' kind for gym/café/shop/bar/spa tours.
      - business: a maps/places listing (OSM) whose name matches and whose
        address lies inside the scope; coordinates come from the listing.

    Returns:
        {
            'stop_title': str,
            'venue_name': str,
            'venue_kind': 'institution' | 'geographic_area' | 'dining' | 'business' | 'unknown',
            'verified': bool,
            'evidence': str (what confirmed it, or '' if unverified),
            'source': 'venue_corpus' | 'stop_corpus' | 'stop_corpus_geographic' | 'dining_external' | 'business_maps' | '',
            'coords': (lat, lng) | None,  # LOCAL-779: from a business maps listing
        }
    """
    # Classify venue kind first (tour_type for dining, poi_type for business)
    venue_kind, kind_evidence = _classify_venue_kind(
        venue_name, db_conn, tour_type=tour_type, poi_type=poi_type)

    result = {
        'stop_title': stop_title,
        'venue_name': venue_name,
        'venue_kind': venue_kind,
        'verified': False,
        'evidence': '',
        'source': '',
        'coords': None,
    }

    # Check 1: venue_corpus (canonical titles, SPARQL works)
    # This works for BOTH kinds — a canonical title match is always valid
    verified, evidence = _check_venue_corpus(stop_title, venue_name, db_conn)
    if verified:
        result['verified'] = True
        result['evidence'] = evidence
        result['source'] = 'venue_corpus'
        return result

    # Check 2: stop_corpus — logic depends on venue kind
    if venue_kind == 'geographic_area':
        # Relaxed: stop_corpus row with passages is sufficient (no same-source
        # venue mention required). A real place doesn't need to name our
        # internal label "French Riviera walking area" in its Wikipedia article.
        verified, evidence = _check_stop_corpus_geographic(stop_title, venue_name, db_conn)
        if verified:
            result['verified'] = True
            result['evidence'] = evidence
            result['source'] = 'stop_corpus_geographic'
            return result
        # [LOCAL-290 Fault 2 / D162] Corpus lookup failed — but a real place absent
        # from our scraping backlog must NOT be dropped as "no evidence". Fall through
        # to tier-1 existence check (Wikipedia/Wikidata) before declaring unverified.
        verified, evidence = _check_geographic_existence_tier1(stop_title, venue_name)
        if verified:
            result['verified'] = True
            result['evidence'] = evidence
            result['source'] = 'geographic_tier1_wikipedia'
            return result
    elif venue_kind == 'business':
        # LOCAL-779: Gym/café/shop/bar/spa verification via a maps/places lookup.
        # The question is "does a place with this name exist at an address inside
        # the scope?" — the same question the dining path asks, generalized to any
        # commercial POI. A match supplies the stop's coordinates straight from the
        # listing; a fabricated name with no listing (or one in the wrong city) is
        # dropped by ENFORCE exactly as a fabricated landmark is.
        #
        # LOCAL-320: RuntimeError from the OSM lookup means the search FAILED
        # (throttle/timeout/connection). That is UNKNOWN (keep, retry), never
        # searched-and-absent — D162.
        _biz_city_signals = _city_signals_from_venue(venue_name)
        try:
            verified, evidence, coords = _check_business_existence(
                stop_title, venue_name, _biz_city_signals)
            if verified:
                result['verified'] = True
                result['evidence'] = evidence
                result['source'] = 'business_maps'
                result['coords'] = coords
                return result
        except RuntimeError as e:
            result['evidence'] = f'search_failed: {e}'
            result['source'] = 'search_failed'
            result['search_failed'] = True
            logger.warning(f"[EXISTENCE-GATE] Business maps search failed for "
                           f"{stop_title!r}: {e}")
            return result
    elif venue_kind == 'dining':
        # LOCAL-281: Restaurant/dining verification via external sources.
        # The question is "does this establishment exist at this location?" —
        # verified via Wikipedia, Wikidata, or authoritative culinary sources.
        #
        # LOCAL-320: RuntimeError means search infrastructure failed (rate limit,
        # timeout, connection error). This is NOT "no evidence" — it is "could
        # not search". D162: a search that did not really run must never be
        # evidence of absence. Classify as "unknown" so the gate retries.
        try:
            verified, evidence = _check_dining_existence(stop_title, venue_name, db_conn)
            if verified:
                result['verified'] = True
                result['evidence'] = evidence
                result['source'] = 'dining_external'
                return result
        except RuntimeError as e:
            # Search failed — classify as "unknown" (not unverified)
            result['evidence'] = f'search_failed: {e}'
            result['source'] = 'search_failed'
            # Mark as unknown so the gate can distinguish from "searched and not found"
            result['search_failed'] = True
            logger.warning(f"[EXISTENCE-GATE] Search failed for {stop_title!r}: {e}")
            return result
    else:
        # Institution or unknown: strict same-source rule (D74, D127).
        # The passage must mention BOTH the stop and the venue.
        verified, evidence = _check_stop_corpus(stop_title, venue_name, db_conn)
        if verified:
            result['verified'] = True
            result['evidence'] = evidence
            result['source'] = 'stop_corpus'
            return result

    # Check 3: venue catalogue page — not implemented yet
    # (would require fetching venue's official collection page and checking)

    return result


def get_gate_mode() -> str:
    """Resolve the stop-existence gate mode from environment.

    Single source of truth: STOP_EXISTENCE_GATE_MODE env var.
    Valid values: 'off', 'log_only', 'enforce'.
    Default: 'off' (explicit — no silent behaviour).

    Legacy compat: if the new var is not set, falls back to the old flags:
        DISABLE_STOP_EXISTENCE_GATE=1 → 'off'
        ENABLE_STOP_EXISTENCE_GATE=1  → 'enforce'
        neither                       → 'log_only' (old default)

    Returns one of: 'off', 'log_only', 'enforce'.
    """
    mode = os.environ.get('STOP_EXISTENCE_GATE_MODE', '').strip().lower()
    if mode in ('off', 'log_only', 'enforce'):
        return mode

    # Legacy fallback
    if os.environ.get('DISABLE_STOP_EXISTENCE_GATE', '').strip() == '1':
        return 'off'
    if os.environ.get('ENABLE_STOP_EXISTENCE_GATE', '').strip() == '1':
        return 'enforce'
    return 'log_only'


def _log_gate_startup():
    """Log the resolved gate mode at startup. Call once per run."""
    mode = get_gate_mode()
    print(f"  [EXISTENCE-GATE] Mode at startup: {mode.upper()}")
    return mode


def run_existence_gate(
    poi_list: List[str],
    venue_name: str,
    db_conn,
    tour_type: Optional[str] = None,
    poi_type: Optional[str] = None,
) -> Dict:
    """Run the stop-existence gate over a list of candidate stops.

    Mode is read from STOP_EXISTENCE_GATE_MODE (or legacy flags).
      'off'      → gate completely disabled, no verification, no logging
      'log_only' → verdicts computed and logged, nothing dropped
      'enforce'  → unverified stops dropped from the returned list

    Args:
        poi_list: List of stop title strings to verify.
        venue_name: The venue/location string (city for restaurants, museum name
                    for institutions, area label for geographic).
        db_conn: Database connection.
        tour_type: Optional tour type hint (e.g. 'restaurant'). When provided,
                   used to classify venue kind. Falls back to
                   EXISTENCE_GATE_TOUR_TYPE env var if not passed.

    Returns:
        {
            'mode': 'off' | 'log_only' | 'enforce',
            'total_stops': int,
            'verified_stops': list of stop titles,
            'unverified_stops': list of stop titles,
            'verdicts': list of verify_stop_existence results,
            'action': 'ENFORCE' | 'LOG_ONLY' | 'OFF',
        }
    """
    mode = get_gate_mode()

    if mode == 'off':
        return {
            'mode': 'off',
            'total_stops': len(poi_list),
            'verified_stops': list(poi_list),
            'unverified_stops': [],
            'inconclusive_stops': [],
            'verdicts': [],
            'action': 'OFF',
        }

    # Run verification on all stops (both log_only and enforce)
    verdicts = []
    verified_stops = []
    unverified_stops = []
    inconclusive_stops = []  # LOCAL-320 bounce: third state — kept but NOT verified

    for stop_title in poi_list:
        verdict = verify_stop_existence(stop_title, venue_name, db_conn, tour_type=tour_type, poi_type=poi_type)
        verdicts.append(verdict)
        if verdict['verified']:
            verified_stops.append(stop_title)
        elif verdict.get('search_failed'):
            # LOCAL-320: Search infrastructure failed (rate limit, timeout).
            # D162: a search that did not really run must never be evidence of
            # absence. These stops are "unknown" — retry once after a pause.
            pass  # Will be retried below
        else:
            unverified_stops.append(stop_title)

    # LOCAL-320: Retry any search_failed stops after a pause (the throttle likely
    # just needed more time between requests). One retry per stop, max.
    _failed_stops = [v['stop_title'] for v in verdicts if v.get('search_failed')]
    if _failed_stops:
        print(f"  [EXISTENCE-GATE] {len(_failed_stops)} stop(s) had search failures — "
              f"retrying after pause")
        time.sleep(_NOMINATIM_MIN_INTERVAL * 2)  # Extra breathing room
        for i, stop_title in enumerate(_failed_stops):
            retry_verdict = verify_stop_existence(stop_title, venue_name, db_conn, tour_type=tour_type, poi_type=poi_type)
            # Replace the failed verdict
            for j, v in enumerate(verdicts):
                if v['stop_title'] == stop_title and v.get('search_failed'):
                    verdicts[j] = retry_verdict
                    break
            if retry_verdict['verified']:
                verified_stops.append(stop_title)
                print(f"    [RETRY OK] {stop_title!r} — {retry_verdict['evidence'][:60]}")
            elif retry_verdict.get('search_failed'):
                # LOCAL-320 bounce fix: Still failing after retry.
                # This is INCONCLUSIVE — NOT verified, NOT unverified.
                # The stop is kept for delivery (D162: don't reject based on a
                # search that never completed), but it MUST NOT enter
                # verified_stops and MUST NOT be counted as verified in the log.
                # A fabricated name must not be called "verified" just because
                # the search infrastructure failed. Michael's rule: a fabricated
                # stop costs 3× an illegitimate omission.
                inconclusive_stops.append(stop_title)
                # Mark the verdict so downstream can distinguish
                retry_verdict['inconclusive'] = True
                retry_verdict['search_failed'] = True
                for j, v in enumerate(verdicts):
                    if v['stop_title'] == stop_title:
                        verdicts[j] = retry_verdict
                        break
                print(f"    [RETRY FAILED] {stop_title!r} — INCONCLUSIVE "
                      f"(search still failing, kept for delivery but NOT verified)")
            else:
                unverified_stops.append(stop_title)
                print(f"    [RETRY] {stop_title!r} — genuinely unverified")

    # Log results — report inconclusive as its own count (never claim verified)
    n_ver = len(verified_stops)
    n_unver = len(unverified_stops)
    n_inconclusive = len(inconclusive_stops)
    pct_ver = n_ver / len(poi_list) * 100 if poi_list else 0

    _inc_suffix = f", {n_inconclusive} inconclusive" if n_inconclusive else ""
    if mode == 'enforce':
        action = 'ENFORCE'
        print(f"  [EXISTENCE-GATE] ENFORCE — {n_ver}/{len(poi_list)} stops verified "
              f"({pct_ver:.0f}%), dropping {n_unver} unverified{_inc_suffix}")
    else:
        action = 'LOG_ONLY'
        print(f"  [EXISTENCE-GATE] LOG_ONLY — {n_ver}/{len(poi_list)} stops verified "
              f"({pct_ver:.0f}%), {n_unver} would be dropped{_inc_suffix}")

    # Log individual verdicts
    for v in verdicts:
        if v['verified']:
            status = "VERIFIED"
        elif v.get('inconclusive'):
            status = "INCONCLUSIVE"
        else:
            status = "UNVERIFIED"
        ev = v['evidence'][:80] if v['evidence'] else "no evidence"
        print(f"    [{status}] {v['stop_title']!r:.50s} — {ev}")

    # ──── LOCAL-283: HARVEST PASSAGES ON VERIFICATION ─────────────────────
    # When a stop is verified (especially via name-in-a-list), attempt to
    # harvest fact-carrying passages from the same source into stop_corpus.
    harvest_summary = None
    try:
        from verification_harvester import harvest_on_verification
        harvest_summary = harvest_on_verification(verdicts, venue_name, db_conn)
    except ImportError:
        pass  # Module not available — skip silently
    except Exception as _harv_err:
        print(f"    [HARVEST] Error (non-fatal): {_harv_err}")
    # ──── END LOCAL-283 ───────────────────────────────────────────────────

    # ──── LOCAL-314: HARVEST DINING CORPUS ON VERIFICATION ────────────────
    # When dining stops verify via Nominatim/Wikipedia, harvest factual
    # passages (founding year, chef, dishes, price) into stop_corpus.
    dining_harvest_summary = None
    _resolved_tour_type = tour_type or os.environ.get('EXISTENCE_GATE_TOUR_TYPE', '')
    if _resolved_tour_type in ('restaurant', 'food', 'dining', 'culinary'):
        try:
            from dining_corpus_harvester import harvest_dining_on_verification
            dining_harvest_summary = harvest_dining_on_verification(verdicts, venue_name, db_conn)
        except ImportError:
            pass  # Module not available — skip silently
        except RuntimeError as _rt_err:
            # D220: 429 = search failure, not "no data"
            print(f"    [DINING-HARVEST] RuntimeError (non-fatal): {_rt_err}")
        except Exception as _dh_err:
            print(f"    [DINING-HARVEST] Error (non-fatal): {_dh_err}")
    # ──── END LOCAL-314 ───────────────────────────────────────────────────

    # ──── LOCAL-332: INTERPRETIVE ENRICHMENT ──────────────────────────────
    # After existence is confirmed, ask *what is interesting* about each stop
    # rather than searching its name (which yields directory listings).
    # This produces narrative-quality corpus with sources.
    interpretive_summary = None
    if os.environ.get('DISABLE_INTERPRETIVE_ENRICHMENT', '').strip() != '1':
        _ie_venue_kind = _resolved_tour_type or 'default'
        _ie_city = ''
        _ie_country = ''
        # Extract city/country from venue_name
        if venue_name:
            _parts = re.split(r'[,\-]', venue_name)
            for _p in _parts:
                _pw = _p.strip()
                if _pw and len(_pw) >= 3 and _pw[0].isupper():
                    _pw_lower = _pw.lower()
                    if _pw_lower not in ('old', 'restaurant', 'tour', 'museum', 'food', 'dining', 'vieux'):
                        if not _ie_city:
                            _ie_city = _pw
                        elif not _ie_country:
                            _ie_country = _pw
            # LOCAL-348: If city looks like a country (no comma-separated city found),
            # try to extract it from descriptive phrases like "tour in Old Nice (Vieux Nice)".
            _KNOWN_COUNTRIES = {'france', 'italy', 'spain', 'germany', 'japan', 'usa',
                                'uk', 'england', 'greece', 'portugal', 'netherlands',
                                'belgium', 'austria', 'switzerland', 'australia'}
            if _ie_city.lower() in _KNOWN_COUNTRIES or not _ie_city:
                # Promote current city to country if it's a country name
                if _ie_city and _ie_city.lower() in _KNOWN_COUNTRIES and not _ie_country:
                    _ie_country = _ie_city
                    _ie_city = ''
                # Try "in <City>" pattern within descriptive parts
                _in_match = re.search(
                    r'\bin\s+(?:Old\s+|Vieux\s+)?([A-Z][a-zA-Z\u00C0-\u017F]+(?:\s+[A-Z][a-zA-Z\u00C0-\u017F]+)?)',
                    venue_name
                )
                if _in_match:
                    _ie_city = _in_match.group(1)
                # Also try "of <City>" pattern (e.g. "walking tour of Vieux Nice")
                if not _ie_city:
                    _of_match = re.search(
                        r'\bof\s+(?:Old\s+|Vieux\s+)?([A-Z][a-zA-Z\u00C0-\u017F]+(?:\s+[A-Z][a-zA-Z\u00C0-\u017F]+)?)',
                        venue_name
                    )
                    if _of_match:
                        _ie_city = _of_match.group(1)
        try:
            from interpretive_enrichment import enrich_verified_stops
            interpretive_summary = enrich_verified_stops(
                verdicts=verdicts,
                venue_name=venue_name,
                venue_kind=_ie_venue_kind,
                city=_ie_city,
                country=_ie_country,
                db_conn=db_conn,
            )
        except ImportError:
            pass  # Module not available — skip silently
        except RuntimeError as _ie_rt:
            print(f"    [INTERPRETIVE] RuntimeError (non-fatal): {_ie_rt}")
        except Exception as _ie_err:
            print(f"    [INTERPRETIVE] Error (non-fatal): {_ie_err}")
    # ──── END LOCAL-332 ───────────────────────────────────────────────────

    return {
        'mode': mode,
        'total_stops': len(poi_list),
        'verified_stops': verified_stops,
        'unverified_stops': unverified_stops,
        'inconclusive_stops': inconclusive_stops,  # LOCAL-320 bounce: kept but not verified
        'verdicts': verdicts,
        'action': action,
        'harvest_summary': harvest_summary,
        'dining_harvest_summary': dining_harvest_summary,
        'interpretive_summary': interpretive_summary,
    }
