"""
venue_resolver.py — Wikidata-based venue entity resolution.
=============================================================
Resolves a venue string + city into structured Wikidata entity with:
- QID (unique identifier)
- Official website (P856)
- Coordinates (P625) — replaces fabricated/hardcoded coordinates
- Country → language (for local-language Wikipedia fetch)
- Artist link (P138/P921/P547 — for single-artist museum expansion)
- Works collection (P195/P276 SPARQL query → canonical titles)

Implements Generic Grounding Step 0 + Step 1 (works query).
Replaces: _KNOWN_VENUE_COORDS, hardcoded site URLs, _KNOWN_WORKS_BY_VENUE.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import requests

logger = logging.getLogger(__name__)

# ─── LOCAL-230: Per-run failure counter ──────────────────────────────────────
# Incremented when a network/API call fails (as opposed to returning a legitimate
# empty result). Reported in the generation log so tours built during outages
# are identifiable.
_network_failure_count = 0


def get_network_failure_count() -> int:
    """Return the number of network failures encountered this run."""
    return _network_failure_count


def reset_network_failure_count() -> None:
    """Reset the failure counter (call at start of each generation run)."""
    global _network_failure_count
    _network_failure_count = 0

_USER_AGENT = "Audioura/2.2 (tour-generation; contact: support@audioura.com)"
_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Country code → primary Wikipedia language
_COUNTRY_LANG = {
    "Q142": "fr",   # France
    "Q38": "it",    # Italy
    "Q183": "de",   # Germany
    "Q29": "es",    # Spain
    "Q30": "en",    # USA
    "Q145": "en",   # UK
    "Q31": "fr",    # Belgium (French)
    "Q39": "de",    # Switzerland (German)
    "Q55": "nl",    # Netherlands
    "Q36": "pl",    # Poland
    "Q159": "ru",   # Russia
    "Q17": "ja",    # Japan
}

# P31 (instance-of) values that indicate a museum/gallery
_MUSEUM_TYPES = {
    "Q33506",    # museum
    "Q207694",   # art museum
    "Q1007870",  # art gallery
    "Q7075",     # library (edge case)
    "Q2772772",  # sculpture garden
    "Q17431399", # national museum
    "Q1970365",  # natural history museum
}


@dataclass
class VenueEntity:
    """Resolved venue from Wikidata."""
    qid: str
    name: str
    official_url: str = ""
    lat: float = 0.0
    lng: float = 0.0
    country_qid: str = ""
    language: str = "en"
    inception: str = ""
    artist_qid: str = ""
    artist_name: str = ""
    works: List[Dict] = field(default_factory=list)  # [{qid, label_en, label_local}]


def _normalise_venue_name(venue_string: str) -> List[str]:
    """Generate lookup variants from a venue string with parentheticals/qualifiers.

    LOCAL-258: A parenthetical gloss (English name, alternate name, disambiguator)
    must not defeat lookup. Returns a list of search strings to try in order:
      1. Full string as-is (may work if Wikidata indexes the full form)
      2. Pre-parenthetical head (e.g. "Musee des Arts Asiatiques")
      3. Parenthetical content alone (e.g. "Asian Art Museum")

    Trailing place qualifiers (", Nice, France") are stripped consistently —
    they are handled as a city hint, not part of the venue search key.
    """
    # Strip trailing comma-separated place qualifiers (city, country)
    # These arrive as city hints via the caller; keeping them in the search
    # string confuses Wikidata.
    _stripped = re.sub(r',\s*[^,()]+$', '', venue_string).strip()
    # If that removed something that looks like country, try once more for city
    if _stripped != venue_string:
        _stripped = re.sub(r',\s*[^,()]+$', '', _stripped).strip()

    variants = []

    # Check for parenthetical content
    paren_match = re.match(r'^(.+?)\s*\((.+?)\)\s*$', _stripped)
    if paren_match:
        head = paren_match.group(1).strip()
        paren_content = paren_match.group(2).strip()
        # 1. Full string (might match a Wikidata alias)
        variants.append(_stripped)
        # 2. Pre-parenthetical head (most likely the official/local name)
        if head:
            variants.append(head)
        # 3. Parenthetical content (often the English name)
        if paren_content and paren_content != head:
            variants.append(paren_content)
    else:
        variants.append(_stripped)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def resolve_venue(venue_string: str, city: str = "") -> Optional[VenueEntity]:
    """Resolve a venue string to a Wikidata entity.
    
    Args:
        venue_string: The venue name (e.g. "Musée Matisse")
        city: Optional city for geo-disambiguation (e.g. "Nice")
        
    Returns:
        VenueEntity with structured data, or None if unresolvable.
    """
    # LOCAL-258: Extract city from trailing comma-separated segments if not provided.
    # E.g. "Musee des Arts Asiatiques (Asian Art Museum), Nice, France" → city="Nice"
    if not city and "," in venue_string:
        _parts = [p.strip() for p in venue_string.split(",")]
        if len(_parts) >= 2:
            # Heuristic: second segment is likely the city; skip country-looking words
            _COUNTRY_WORDS = {'france', 'italy', 'usa', 'uk', 'spain', 'germany',
                              'netherlands', 'belgium', 'switzerland', 'japan', 'china'}
            for _seg in _parts[1:]:
                if _seg.lower() not in _COUNTRY_WORDS and len(_seg) > 1:
                    city = _seg
                    break

    # LOCAL-258: Normalise venue name — strip parentheticals and trailing qualifiers,
    # then try each variant in order until we get candidates.
    _name_variants = _normalise_venue_name(venue_string)
    print(f"  [venue_resolver] Name variants: {_name_variants}")

    # Step 1: Search Wikidata for candidates — city-qualified FIRST, then bare
    # Wikipedia naming conventions: "X in City", "X (City)", "X, City"
    candidates = []

    # Try each normalised variant with the full search cascade
    for _variant in _name_variants:
        if city:
            # Try city-qualified queries first (Wikipedia disambiguation conventions)
            for _qual_query in [
                f"{_variant} in {city}",
                f"{_variant} ({city})",
                f"{_variant} {city}",
            ]:
                candidates = _search_entities(_qual_query)
                if candidates:
                    print(f"  [venue_resolver] City-qualified search hit: '{_qual_query}' → {len(candidates)} candidates")
                    break

        if not candidates:
            candidates = _search_entities(_variant)

        if candidates:
            break  # Found candidates with this variant

    if not candidates:
        # Fallback: try with city appended to each variant
        for _variant in _name_variants:
            if city:
                candidates = _search_entities(f"{_variant} {city}")
                if candidates:
                    break
    
    if not candidates:
        # Try shorter variants: strip common prefixes/honorifics
        for _variant in _name_variants:
            _shorter = re.sub(r'(?i)^(mus[ée]+e?\s*(national|nationale|municipal|municipale|d[eu]\s*)?)', 'Musée ', _variant).strip()
            if _shorter != _variant:
                candidates = _search_entities(_shorter)
                if candidates:
                    break
    
    if not candidates:
        # Try just the distinctive name words (e.g. "Marc Chagall" from "Musée national Marc Chagall")
        for _variant in _name_variants:
            _words = _variant.split()
            _distinctive = [w for w in _words if w.lower() not in
                           ('musée', 'musee', 'museum', 'national', 'nationale', 'gallery',
                            'galleria', 'the', 'of', 'de', 'du', 'des', 'le', 'la', 'les')]
            if _distinctive:
                _short_query = f"musée {' '.join(_distinctive)}"
                candidates = _search_entities(_short_query)
                if candidates:
                    break
    
    if not candidates:
        print(f"  [venue_resolver] No Wikidata candidates for '{venue_string}'")
        return None
    
    # Step 1b: Filter out disambiguation pages (never mine these as corpus)
    candidates = _filter_disambiguation_pages(candidates)
    if not candidates:
        print(f"  [venue_resolver] All candidates were disambiguation pages for '{venue_string}'")
        return None
    
    # Step 2: Filter by P31 instance-of (museum/gallery types) BEFORE geo
    museum_candidates = []
    for qid, label in candidates[:10]:
        entity_type = _get_instance_of(qid)
        if entity_type and entity_type in _MUSEUM_TYPES:
            museum_candidates.append((qid, label))
    
    if not museum_candidates:
        # Fallback: try all candidates with geo-disambiguation
        print(f"  [venue_resolver] No museum-typed candidates, trying geo-disambiguation on all")
        museum_candidates = candidates[:5]
    
    # Step 3: Geo-disambiguate if city provided — ALWAYS validate city match
    if city:
        if len(museum_candidates) > 1:
            best = _geo_disambiguate(museum_candidates, city)
            if best:
                museum_candidates = [best]
        elif len(museum_candidates) == 1:
            # Even with 1 candidate, validate it's actually in the requested city
            _qid, _label = museum_candidates[0]
            if not _validate_city_match(_qid, city):
                print(f"  [venue_resolver] Single candidate {_qid} ({_label}) failed city validation for '{city}'")
                # Try city-qualified search as last resort
                _city_candidates = _search_entities(f"{venue_string} in {city}")
                _city_candidates = _filter_disambiguation_pages(_city_candidates)
                if _city_candidates:
                    # Re-filter for museum types
                    for _cqid, _clabel in _city_candidates[:5]:
                        _ctype = _get_instance_of(_cqid)
                        if _ctype and _ctype in _MUSEUM_TYPES:
                            if _validate_city_match(_cqid, city):
                                museum_candidates = [(_cqid, _clabel)]
                                print(f"  [venue_resolver] City-validated replacement: {_cqid} ({_clabel})")
                                break
    
    if not museum_candidates:
        return None
    
    # Step 4: Fetch structured properties for the best candidate
    qid, label = museum_candidates[0]
    entity = _fetch_entity_properties(qid, label)
    
    if entity:
        print(f"  [venue_resolver] Resolved: '{venue_string}' → {entity.qid} ({entity.name})")
        print(f"    URL: {entity.official_url}")
        print(f"    Coords: {entity.lat}, {entity.lng}")
        print(f"    Language: {entity.language}")
        if entity.artist_name:
            print(f"    Artist: {entity.artist_name} ({entity.artist_qid})")
    
    return entity


def fetch_venue_works(venue_qid: str, language: str = "en") -> List[Dict]:
    """Fetch canonical works for a venue via SPARQL (P195/P276).
    
    Returns list of {qid, label_en, label_local, aliases, creator, creator_qid} for each work.
    Gets labels in BOTH English and the local language for cross-language matching.
    Includes P170 (creator) for exhibition-scoped filtering (LOCAL-362).
    """
    query = f"""
    SELECT ?work ?workLabel ?workAltLabel ?workLabel_en ?creatorLabel ?creator WHERE {{
      {{ ?work wdt:P195 wd:{venue_qid}. }}
      UNION
      {{ ?work wdt:P276 wd:{venue_qid}. }}
      OPTIONAL {{ ?work wdt:P170 ?creator. }}
      OPTIONAL {{ ?work rdfs:label ?workLabel_en. FILTER(LANG(?workLabel_en) = "en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
    }}
    LIMIT 200
    """
    
    try:
        resp = requests.get(
            _SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"SPARQL error: {resp.status_code}")
            return []
        
        data = resp.json()
        results = data.get("results", {}).get("bindings", [])
        
        works = []
        _seen_qids = set()
        for r in results:
            work_uri = r.get("work", {}).get("value", "")
            work_qid = work_uri.split("/")[-1] if work_uri else ""
            label = r.get("workLabel", {}).get("value", "")
            label_en = r.get("workLabel_en", {}).get("value", "") or label
            alt_label = r.get("workAltLabel", {}).get("value", "")
            creator_label = r.get("creatorLabel", {}).get("value", "")
            creator_uri = r.get("creator", {}).get("value", "")
            creator_qid = creator_uri.split("/")[-1] if creator_uri else ""
            
            # Deduplicate: same work may appear multiple times with different creators
            # (works with multiple creators) — keep first occurrence but merge creator info
            if work_qid and label and not label.startswith("Q"):  # Skip unresolved QIDs
                if work_qid in _seen_qids:
                    # Merge creator into existing entry
                    for existing in works:
                        if existing['qid'] == work_qid and creator_label:
                            if creator_label not in existing.get('creators', []):
                                existing.setdefault('creators', []).append(creator_label)
                            break
                    continue
                _seen_qids.add(work_qid)
                entry = {
                    "qid": work_qid,
                    "label_en": label_en,
                    "label_local": label,
                    "aliases": [a.strip() for a in alt_label.split(",") if a.strip()] if alt_label else [],
                    "creator": creator_label if creator_label and not creator_label.startswith("Q") else "",
                    "creator_qid": creator_qid if creator_label and not creator_label.startswith("Q") else "",
                    "creators": [creator_label] if creator_label and not creator_label.startswith("Q") else [],
                }
                works.append(entry)
        
        print(f"  [venue_resolver] SPARQL: {len(works)} works found for {venue_qid}")
        return works
        
    except Exception as e:
        logger.warning(f"SPARQL query failed: {e}")
        return []


def build_dynamic_aliases(works: List[Dict]) -> Dict[str, str]:
    """Build a CANONICAL_ALIASES dict from SPARQL-fetched works.
    
    Maps all normalized variants (labels + alt labels) to a single canonical form.
    Preserves W4 invariants:
    - Roman numerals are distinguishing (Song of Songs I ≠ Song of Songs II)
    - Numeral-aware: bare "Song of Songs" → cycle_names, not aliases
    
    Returns: {normalized_variant: canonical_label} dict
    """
    import unicodedata
    
    _ROMAN_NUMERALS = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
    
    def _norm(text):
        if not text:
            return ""
        nfkd = unicodedata.normalize('NFKD', text.lower())
        stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
        import re as _re
        stripped = _re.sub(r'[^\w\s]', ' ', stripped)
        return ' '.join(stripped.split())
    
    aliases = {}
    
    for work in works:
        canonical = work.get("label_en", "")
        if not canonical:
            continue
        
        # Collect all name variants for this work
        variants = set()
        variants.add(canonical)
        if work.get("label_local") and work["label_local"] != canonical:
            variants.add(work["label_local"])
        for alias in work.get("aliases", []):
            if alias and len(alias) >= 3:
                variants.add(alias)
        
        # W4: check if canonical has a numeral
        _canon_norm = _norm(canonical)
        _canon_words = _canon_norm.split()
        _has_numeral = any(w in _ROMAN_NUMERALS for w in _canon_words)
        
        # Map all normalized variants to the canonical form
        for variant in variants:
            _vnorm = _norm(variant)
            if not _vnorm or _vnorm == _canon_norm:
                continue
            
            # W4: if canonical has numeral, variant without matching numeral is ambiguous → skip
            _var_words = _vnorm.split()
            _var_numeral = None
            for w in _var_words:
                if w in _ROMAN_NUMERALS:
                    _var_numeral = w
                    break
            
            if _has_numeral and not _var_numeral:
                continue  # Bare name for a numbered work → ambiguous, don't alias
            
            aliases[_vnorm] = canonical
        
        # Also add the canonical itself as a self-mapping for lookup consistency
        aliases[_canon_norm] = canonical
    
    print(f"  [venue_resolver] Built {len(aliases)} dynamic aliases from {len(works)} works")
    return aliases


def build_canonical_titles_from_works(works: List[Dict]) -> Set[str]:
    """Extract canonical titles set from SPARQL works (for union with site+wiki extraction).
    
    Includes BOTH English and local-language labels for cross-language matching.
    Returns a set of canonical title strings.
    """
    titles = set()
    for work in works:
        label_en = work.get("label_en", "")
        if label_en and not label_en.startswith("Q") and len(label_en) >= 3:
            titles.add(label_en)
        local_label = work.get("label_local", "")
        if local_label and local_label != label_en and not local_label.startswith("Q") and len(local_label) >= 3:
            titles.add(local_label)
        # Also add aliases as canonical titles (they're valid names)
        for alias in work.get("aliases", []):
            if alias and len(alias) >= 3 and not alias.startswith("Q"):
                titles.add(alias)
    return titles


# --- Internal helpers ---

def _filter_disambiguation_pages(candidates: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Filter out Wikidata entities that are Wikipedia disambiguation pages.
    
    Detects disambiguation pages by:
    1. P31 = Q4167410 (Wikimedia disambiguation page)
    2. Description containing "disambiguation" or "Wikimedia"
    """
    if not candidates:
        return []
    
    filtered = []
    for qid, label in candidates:
        try:
            resp = requests.get(
                _WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "props": "claims|descriptions",
                    "languages": "en",
                    "format": "json",
                },
                headers={"User-Agent": _USER_AGENT},
                timeout=10,
            )
            if resp.status_code != 200:
                filtered.append((qid, label))  # Can't check — keep it
                continue
            
            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})
            descriptions = entity.get("descriptions", {})
            
            # Check P31 for Q4167410 (Wikimedia disambiguation page)
            is_disambig = False
            for claim in claims.get("P31", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if value.get("id") == "Q4167410":
                    is_disambig = True
                    break
            
            # Also check description
            if not is_disambig:
                en_desc = descriptions.get("en", {}).get("value", "").lower()
                if "disambiguation" in en_desc or "wikimedia" in en_desc:
                    is_disambig = True
            
            if is_disambig:
                print(f"  [venue_resolver] DISAMBIGUATION PAGE detected: {qid} ({label}) — skipping")
            else:
                filtered.append((qid, label))
                
        except Exception:
            filtered.append((qid, label))  # Can't check — keep it
    
    return filtered


def _validate_city_match(qid: str, city: str) -> bool:
    """Validate that a Wikidata entity is located in the specified city.
    
    Checks P131 (located in administrative territory) and P625 coordinates
    against the city. Returns True if the entity is confirmed in the city.
    """
    if not city:
        return True  # No city constraint — always valid
    
    # Check P131 chain first (most reliable)
    if _is_located_in(qid, city):
        return True
    
    # Fallback: check coordinates proximity
    city_lat, city_lng = _geocode_city(city)
    if city_lat is None or (city_lat == 0.0 and city_lng == 0.0):
        return False  # Can't verify (network failure or no coords)
    
    entity_lat, entity_lng = _get_coordinates(qid)
    if entity_lat is None or (entity_lat == 0.0 and entity_lng == 0.0):
        return False  # Entity has no coordinates (or network failed)
    
    dist = _haversine(city_lat, city_lng, entity_lat, entity_lng)
    return dist < 30  # Within 30km of city center


def _search_entities(query: str) -> Optional[List[Tuple[str, str]]]:
    """Search Wikidata for entities matching a query string.

    Returns:
        List of (qid, label) tuples on success (may be empty for no results).
        None on network/API failure (LOCAL-230: distinguishable from empty).
    """
    global _network_failure_count
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": 10,
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"[LOCAL-230] _search_entities failed: HTTP {resp.status_code} for query '{query}'")
            _network_failure_count += 1
            return None
        
        data = resp.json()
        results = [(r["id"], r.get("label", "")) for r in data.get("search", [])]
        return results
    except Exception as e:
        logger.error(f"[LOCAL-230] _search_entities failed: {type(e).__name__}: {e} (query='{query}')")
        _network_failure_count += 1
        return None


def _get_instance_of(qid: str) -> Optional[str]:
    """Get the P31 (instance-of) value for an entity. Returns first matching museum type or None.

    Returns:
        A museum-type QID string if the entity is a museum type.
        None if the entity is not a museum type OR if the lookup failed.
        (LOCAL-230: failure is now logged at ERROR and counted, even though
        the return value is the same — callers degrade identically either way.)
    """
    global _network_failure_count
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"[LOCAL-230] _get_instance_of failed: HTTP {resp.status_code} for qid '{qid}'")
            _network_failure_count += 1
            return None
        
        data = resp.json()
        entity = data.get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        
        # Check P31 (instance-of)
        for claim in claims.get("P31", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            type_qid = value.get("id", "")
            if type_qid in _MUSEUM_TYPES:
                return type_qid
        
        return None
    except Exception as e:
        logger.error(f"[LOCAL-230] _get_instance_of failed: {type(e).__name__}: {e} (qid='{qid}')")
        _network_failure_count += 1
        return None


def _geo_disambiguate(candidates: List[Tuple[str, str]], city: str) -> Optional[Tuple[str, str]]:
    """Pick the candidate closest to the named city using P625 coordinates + P131 chain.
    
    Strategy:
    1. Geocode the city via Wikidata search → get city coordinates
    2. For each candidate, fetch P625; compute haversine distance to city
    3. Candidates without P625: check P131 (located-in-administrative-territory) chain for city match
    4. Return closest by distance, or first P131 match, or first candidate as final fallback
    """
    import math
    
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    
    # Step 1: Get city coordinates from Wikidata
    city_lat, city_lng = _geocode_city(city)
    
    if city_lat is None or (city_lat == 0.0 and city_lng == 0.0):
        # Can't geocode city (or network failed) — fall back to P131 chain matching
        for qid, label in candidates:
            if _is_located_in(qid, city):
                print(f"  [venue_resolver] Geo-disambiguated by P131: {qid} ({label}) in {city}")
                return (qid, label)
        # Final fallback
        return candidates[0]
    
    # Step 2: Score candidates by distance to city center
    best_candidate = None
    best_distance = float('inf')
    
    for qid, label in candidates:
        lat, lng = _get_coordinates(qid)
        if lat is None or (lat == 0.0 and lng == 0.0):
            # No coordinates or network failed — check P131 as fallback
            if _is_located_in(qid, city):
                print(f"  [venue_resolver] Geo-disambiguated by P131 (no coords): {qid} ({label})")
                return (qid, label)
            continue
        
        dist = _haversine(city_lat, city_lng, lat, lng)
        if dist < best_distance:
            best_distance = dist
            best_candidate = (qid, label)
    
    if best_candidate and best_distance < 50:  # Within 50km of city center
        print(f"  [venue_resolver] Geo-disambiguated by distance: {best_candidate[0]} ({best_candidate[1]}) — {best_distance:.1f}km from {city}")
        return best_candidate
    
    # If no close candidate found, fall back to first
    return candidates[0]


def _geocode_city(city: str) -> Tuple[Optional[float], Optional[float]]:
    """Get coordinates for a city name via Wikidata search.

    Returns:
        (lat, lng) floats on success. (0.0, 0.0) if city found but no coords.
        (None, None) on network/API failure (LOCAL-230: distinguishable from absent).
    """
    global _network_failure_count
    try:
        # Search for the city
        results = _search_entities(city)
        if results is None:
            # _search_entities already logged and counted — propagate failure signal
            return None, None
        if not results:
            return 0.0, 0.0
        
        # Take first result and get its coordinates
        for qid, label in results[:3]:
            lat, lng = _get_coordinates(qid)
            if lat is None:
                # _get_coordinates already logged and counted — propagate failure
                return None, None
            if lat != 0.0 or lng != 0.0:
                return lat, lng
        
        return 0.0, 0.0
    except Exception as e:
        logger.error(f"[LOCAL-230] _geocode_city failed: {type(e).__name__}: {e} (city='{city}')")
        _network_failure_count += 1
        return None, None


def _get_coordinates(qid: str) -> Tuple[Optional[float], Optional[float]]:
    """Get P625 coordinates for a Wikidata entity.

    Returns:
        (lat, lng) floats on success. (0.0, 0.0) means entity has no P625 claim.
        (None, None) on network/API failure (LOCAL-230: distinguishable from absent).
    """
    global _network_failure_count
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"[LOCAL-230] _get_coordinates failed: HTTP {resp.status_code} for qid '{qid}'")
            _network_failure_count += 1
            return None, None
        
        data = resp.json()
        entity = data.get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        
        for claim in claims.get("P625", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            lat = value.get("latitude", 0.0)
            lng = value.get("longitude", 0.0)
            if lat or lng:
                return lat, lng
        
        return 0.0, 0.0
    except Exception as e:
        logger.error(f"[LOCAL-230] _get_coordinates failed: {type(e).__name__}: {e} (qid='{qid}')")
        _network_failure_count += 1
        return None, None


def _is_located_in(qid: str, city: str) -> bool:
    """Check if entity's P131 (located-in) chain contains the named city."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return False
        
        data = resp.json()
        entity = data.get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        
        city_lower = city.lower()
        
        # Check P131 values — get label for each and compare to city
        for claim in claims.get("P131", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            territory_qid = value.get("id", "")
            if territory_qid:
                # Get label for this territory
                label = _get_entity_label(territory_qid)
                if label and city_lower in label.lower():
                    return True
        
        return False
    except Exception:
        return False


def _get_entity_label(qid: str, lang: str = "en") -> str:
    """Get the label for a Wikidata entity in the specified language."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels",
                "languages": f"{lang}|fr|it|de|es",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        
        data = resp.json()
        entity = data.get("entities", {}).get(qid, {})
        labels = entity.get("labels", {})
        
        # Try requested language first, then fallback chain
        for l in [lang, "en", "fr", "it", "de", "es"]:
            if l in labels:
                return labels[l].get("value", "")
        
        return ""
    except Exception:
        return ""


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    import math
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _discover_site_from_wikipedia(qid: str, label: str) -> str:
    """When P856 is dead, discover the working site URL from Wikipedia external links.
    
    Fetches the venue's Wikipedia article and looks for museum/gallery-domain URLs
    that are likely the official site.
    """
    try:
        # Try multiple title variants
        _titles_to_try = [
            label,
            label.replace('-', ' '),
            label.title(),
            label.title().replace('-', ' '),
        ]
        # Also try with "Musée" capitalized and accent restored
        if label.lower().startswith('mus'):
            _name_after_musee = label.split(' ', 1)[1] if ' ' in label else label
            _name_after_musee = _name_after_musee.replace('-', ' ')
            _titles_to_try.append(f"Musée {_name_after_musee}")
            _titles_to_try.append(f"Musée national {_name_after_musee}")
            _titles_to_try.append(f"{_name_after_musee} Museum")
        
        links = []
        for _title in _titles_to_try:
            resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "parse", "page": _title, "prop": "externallinks", "format": "json"},
                headers={"User-Agent": _USER_AGENT},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            if "error" in data:
                continue
            
            links = data.get("parse", {}).get("externallinks", [])
            if links:
                break
        
        if not links:
            return ""
        
        # Filter for museum/institutional domains (not archives, geo tools, authorities)
        _SKIP_DOMAINS = {'archive.org', 'wikiwix.com', 'geohack.toolforge.org', 'viaf.org',
                        'loc.gov', 'bnf.fr', 'data.bnf.fr', 'dailymotion.com', 'evene.fr',
                        'wikidata.org', 'wikipedia.org'}
        
        for link in links:
            from urllib.parse import urlparse as _urlparse
            parsed = _urlparse(link)
            domain = parsed.netloc.lower()
            
            # Skip known non-site domains
            if any(skip in domain for skip in _SKIP_DOMAINS):
                continue
            
            # Skip the dead P856 domain itself
            if 'musee-chagall' in domain:
                continue
            
            # Look for museum-related domains
            if any(kw in domain or kw in parsed.path.lower() for kw in
                   ['musee', 'museum', 'gallery', 'collection', 'national']):
                # Found a likely museum site — extract base URL
                base_url = f"{parsed.scheme}://{parsed.netloc}{'/'.join(parsed.path.split('/')[:3])}/"
                # Verify it's reachable
                try:
                    _check = requests.head(base_url, headers={"User-Agent": _USER_AGENT},
                                          timeout=5, allow_redirects=True)
                    if _check.status_code < 400:
                        return base_url
                except Exception:
                    continue
        
        return ""
    except Exception as e:
        logger.warning(f"Wikipedia site discovery failed for {label}: {e}")
        return ""


def _infer_artist_from_name(venue_name: str) -> str:
    """Infer artist name from a museum name by stripping institutional prefixes.
    
    E.g. "musée Marc-Chagall" → "Marc Chagall"
         "Musée Matisse" → "Matisse"
    Returns empty string if no artist name can be inferred (e.g. "Uffizi Gallery").
    
    LOCAL-362: Reject candidates that are clearly NOT artist names — e.g. residual
    geographic words or institutional fragments like "Fine Boston".
    """
    # Strip common institutional words
    _STRIP_WORDS = {
        'musée', 'musee', 'museum', 'gallery', 'galleria', 'national', 'nationale',
        'municipal', 'municipale', 'fondation', 'foundation', 'centre', 'center',
        'the', 'of', 'de', 'du', 'des', 'le', 'la', 'les', "l'", 'art', 'arts',
        'moderne', 'modern', 'contemporain', 'contemporary', 'beaux',
    }
    
    # LOCAL-362: Words that should never appear in an inferred artist name.
    # These are geographic, institutional, or descriptive words that indicate
    # the venue name is NOT an artist-named museum.
    _REJECT_WORDS = {
        # Geographic
        'boston', 'new', 'york', 'paris', 'london', 'nice', 'rome', 'berlin',
        'chicago', 'los', 'angeles', 'san', 'francisco', 'washington',
        'philadelphia', 'houston', 'dallas', 'atlanta', 'denver', 'seattle',
        'miami', 'orleans', 'diego', 'francisco', 'antonio', 'jose',
        # US states
        'massachusetts', 'california', 'texas', 'florida', 'virginia',
        # Institutional/descriptive remnants
        'fine', 'applied', 'decorative', 'natural', 'history', 'science',
        'american', 'european', 'asian', 'african', 'ancient', 'medieval',
        'folk', 'craft', 'design', 'photography', 'film', 'children',
        'heritage', 'memorial', 'institute', 'institution', 'society',
        'university', 'college', 'school', 'academy', 'library',
        'city', 'state', 'county', 'district', 'region', 'province',
    }
    
    words = re.sub(r'[-–]', ' ', venue_name).split()
    name_words = [w for w in words if w.lower().rstrip("'") not in _STRIP_WORDS and len(w) > 1]
    
    if not name_words:
        return ""
    
    # LOCAL-362: Reject if ANY remaining word is in the reject list
    for w in name_words:
        if w.lower() in _REJECT_WORDS:
            return ""
    
    # Check if remaining words look like a person name (capitalized, 1-3 words)
    name_candidate = " ".join(name_words)
    if len(name_words) <= 3 and all(w[0].isupper() for w in name_words if w):
        return name_candidate
    
    return ""


def _fetch_entity_properties(qid: str, label: str) -> Optional[VenueEntity]:
    """Fetch P856, P625, P17, P571, and artist-link properties."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims|labels",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        entity_data = data.get("entities", {}).get(qid, {})
        claims = entity_data.get("claims", {})
        
        # P856 — official website
        official_url = ""
        for claim in claims.get("P856", []):
            url = claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
            if url:
                official_url = url
                break
        
        # If P856 is known-dead or unreachable, try to find alternative from Wikipedia
        # external links (the article often links to the actual working site)
        if official_url:
            # Quick reachability check (connect-only, 5s)
            try:
                _test = requests.head(official_url, headers={"User-Agent": _USER_AGENT},
                                     timeout=5, allow_redirects=True)
            except Exception as _p856_err:
                # P856 unreachable — search Wikipedia external links for alternative
                print(f"    [venue_resolver] P856 unreachable ({type(_p856_err).__name__}), searching Wikipedia...")
                _alt_url = _discover_site_from_wikipedia(qid, label)
                if _alt_url:
                    print(f"    [venue_resolver] P856 dead → discovered: {_alt_url}")
                    official_url = _alt_url
                else:
                    print(f"    [venue_resolver] No alternative site found in Wikipedia")
        
        # P625 — coordinates
        lat, lng = 0.0, 0.0
        for claim in claims.get("P625", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            lat = value.get("latitude", 0.0)
            lng = value.get("longitude", 0.0)
            break
        
        # P17 — country
        country_qid = ""
        for claim in claims.get("P17", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            country_qid = value.get("id", "")
            break
        
        language = _COUNTRY_LANG.get(country_qid, "en")
        
        # P571 — inception
        inception = ""
        for claim in claims.get("P571", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            inception = value.get("time", "")[:10] if value.get("time") else ""
            break
        
        # Artist link: P138 (named after), P921 (main subject), P547 (commemorates)
        artist_qid = ""
        artist_name = ""
        for prop in ("P138", "P921", "P547"):
            for claim in claims.get(prop, []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                _aqid = value.get("id", "")
                if _aqid:
                    artist_qid = _aqid
                    # Fetch artist name from their entity labels
                    artist_name = _get_entity_label(_aqid)
                    print(f"    [venue_resolver] Artist link: {prop} → {_aqid} ({artist_name})")
                    break
            if artist_qid:
                break
        
        # Fallback: infer artist from venue name (strip museum/gallery/national words)
        if not artist_name and label:
            _inferred = _infer_artist_from_name(label)
            if _inferred:
                artist_name = _inferred
                print(f"    [venue_resolver] Artist inferred from name: '{artist_name}'")
        
        return VenueEntity(
            qid=qid,
            name=label,
            official_url=official_url,
            lat=lat,
            lng=lng,
            country_qid=country_qid,
            language=language,
            inception=inception,
            artist_qid=artist_qid,
            artist_name=artist_name,
        )
        
    except Exception as e:
        logger.warning(f"Entity fetch error for {qid}: {e}")
        return None


# ============================================================
# PHASE 2: Venue Corpus Cache Layer
# ============================================================
# Caches discovery results in Postgres to avoid re-mining on repeat requests.
# TTL-based invalidation with separate positive (30d) and negative (5d) TTLs.
# Note: story_elements_json is Phase-2 interim; migrates to work-level when SQ-S8 lands.

import os
import json
from datetime import datetime, timedelta

VENUE_CACHE_TTL_DAYS = int(os.environ.get('VENUE_CACHE_TTL_DAYS', '30'))
VENUE_CACHE_NEGATIVE_TTL_DAYS = int(os.environ.get('VENUE_CACHE_NEGATIVE_TTL_DAYS', '5'))
CORPUS_VERSION = 4  # LOCAL-24: Work-vs-nonwork filter added; invalidate stale cached data


# TODO(S94): remove in-code password fallback; prod must use DATABASE_URL/DB_PASSWORD env only
def _is_inside_container():
    """Return True if running inside a Docker container (/.dockerenv present)."""
    return os.path.exists('/.dockerenv')


def _get_db_connection():
    """Get a Postgres connection for venue_corpus cache.

    Returns None if no DB is configured (normal on host without DATABASE_URL).
    Raises on misconfiguration (env var set but connection fails) — caller
    should not silently degrade when the user intended a cache.
    """
    try:
        import psycopg2
    except ImportError:
        print("  [venue_cache] psycopg2 not installed — venue cache unavailable")
        return None

    # Use VENUE_CACHE_DB_URL first, fall back to DATABASE_URL, then container default
    db_url = os.environ.get('VENUE_CACHE_DB_URL',
             os.environ.get('DATABASE_URL'))

    _url_from_env = db_url is not None

    if db_url is None:
        if _is_inside_container():
            # Container default: postgres-2 is on the Docker network
            db_url = 'postgresql://admin:password123@postgres-2:5432/audiotours'
        else:
            # Host with no DB env: venue cache simply not configured — this is fine
            print("  [venue_cache] No DATABASE_URL set (host mode) — venue cache skipped")
            return None

    # Rewrite localhost → postgres-2 ONLY inside a container (LOCAL-214)
    if _is_inside_container():
        if '@localhost:' in db_url:
            db_url = db_url.replace('@localhost:', '@postgres-2:')
        # Fix auth mismatch: tour-generator uses admin:admin but postgres-2 expects password123
        if 'admin:admin@' in db_url and 'postgres-2' in db_url:
            db_url = db_url.replace('admin:admin@', 'admin:password123@')

    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        # Auto-create venue_corpus table if not exists (idempotent)
        _ensure_table(conn)
        return conn
    except Exception as e:
        if _url_from_env:
            # User explicitly configured a DB URL but it doesn't work — this is a defect
            print(f"  [venue_cache] ERROR: DB connection FAILED (misconfiguration): {e}")
            print(f"  [venue_cache]   URL source: {'VENUE_CACHE_DB_URL' if os.environ.get('VENUE_CACHE_DB_URL') else 'DATABASE_URL'}")
            print(f"  [venue_cache]   This is a bug — the configured database is unreachable.")
        else:
            # Container default failed — also a defect (container should always reach postgres-2)
            print(f"  [venue_cache] ERROR: container default DB unreachable: {e}")
        return None


_TABLE_ENSURED = False

def _ensure_table(conn):
    """Create venue_corpus table if it doesn't exist (runs once per process)."""
    global _TABLE_ENSURED
    if _TABLE_ENSURED:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS venue_corpus (
                    qid VARCHAR(20) PRIMARY KEY,
                    venue_name TEXT NOT NULL,
                    official_url TEXT,
                    canonical_titles_json JSONB NOT NULL,
                    story_elements_json JSONB,
                    sparql_works_json JSONB,
                    pages_json JSONB,
                    language VARCHAR(10),
                    tier VARCHAR(20) NOT NULL,
                    corpus_version INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)
            # Ensure tier column is wide enough for 'exhibit_museum' (14 chars)
            cur.execute("ALTER TABLE venue_corpus ALTER COLUMN tier TYPE VARCHAR(20)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_venue_corpus_expires ON venue_corpus(expires_at)")
            conn.commit()
        _TABLE_ENSURED = True
    except Exception as e:
        print(f"  [venue_cache] Table creation failed: {e}")
        conn.rollback()


def cache_get(qid: str) -> Optional[Dict]:
    """Retrieve cached venue corpus by QID. Returns None if miss or expired."""
    conn = _get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT venue_name, official_url, canonical_titles_json, story_elements_json,
                       sparql_works_json, pages_json, language, tier, corpus_version, expires_at
                FROM venue_corpus
                WHERE qid = %s AND expires_at > NOW() AND corpus_version = %s
            """, (qid, CORPUS_VERSION))
            row = cur.fetchone()
            if row:
                print(f"  [venue_cache] HIT for {qid} (tier={row[7]}, expires={row[9]})")
                return {
                    'venue_name': row[0],
                    'official_url': row[1],
                    'canonical_titles': set(row[2]) if row[2] else set(),
                    'story_elements': row[3],
                    'sparql_works': row[4] if row[4] else [],
                    'pages': row[5],
                    'language': row[6],
                    'tier': row[7],
                }
            else:
                print(f"  [venue_cache] MISS for {qid}")
                return None
    except Exception as e:
        print(f"  [venue_cache] Read error: {e}")
        return None
    finally:
        conn.close()


def cache_put(qid: str, venue_name: str, official_url: str, canonical_titles,
              story_elements, sparql_works, pages, language: str, tier: str):
    """Store venue corpus in cache. Uses positive or negative TTL based on tier."""
    conn = _get_db_connection()
    if not conn:
        return
    
    # Negative caching: thin/unresolvable get shorter TTL (lets venue recover)
    if tier in ('thin', 'unresolvable'):
        ttl_days = VENUE_CACHE_NEGATIVE_TTL_DAYS
    else:
        ttl_days = VENUE_CACHE_TTL_DAYS
    
    expires_at = datetime.utcnow() + timedelta(days=ttl_days)
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO venue_corpus (qid, venue_name, official_url, canonical_titles_json,
                    story_elements_json, sparql_works_json, pages_json, language, tier,
                    corpus_version, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (qid) DO UPDATE SET
                    venue_name = EXCLUDED.venue_name,
                    official_url = EXCLUDED.official_url,
                    canonical_titles_json = EXCLUDED.canonical_titles_json,
                    story_elements_json = EXCLUDED.story_elements_json,
                    sparql_works_json = EXCLUDED.sparql_works_json,
                    pages_json = EXCLUDED.pages_json,
                    language = EXCLUDED.language,
                    tier = EXCLUDED.tier,
                    corpus_version = EXCLUDED.corpus_version,
                    created_at = CURRENT_TIMESTAMP,
                    expires_at = EXCLUDED.expires_at
            """, (
                qid, venue_name, official_url,
                json.dumps(list(canonical_titles)) if canonical_titles else json.dumps([]),
                json.dumps(story_elements) if story_elements else None,
                json.dumps(sparql_works) if sparql_works else None,
                json.dumps(pages) if pages else None,
                language, tier, CORPUS_VERSION, expires_at
            ))
            conn.commit()
            print(f"  [venue_cache] STORED {qid} (tier={tier}, ttl={ttl_days}d, expires={expires_at.date()})")
    except Exception as e:
        print(f"  [venue_cache] Write error: {e}")
        conn.rollback()
    finally:
        conn.close()
