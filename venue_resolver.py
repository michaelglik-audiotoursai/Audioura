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


def resolve_venue(venue_string: str, city: str = "") -> Optional[VenueEntity]:
    """Resolve a venue string to a Wikidata entity.
    
    Args:
        venue_string: The venue name (e.g. "Musée Matisse")
        city: Optional city for geo-disambiguation (e.g. "Nice")
        
    Returns:
        VenueEntity with structured data, or None if unresolvable.
    """
    # Step 1: Search Wikidata for candidates — try multiple query strategies
    candidates = _search_entities(venue_string)
    
    if not candidates:
        # Try with city appended
        candidates = _search_entities(f"{venue_string} {city}")
    
    if not candidates:
        # Try shorter variants: strip common prefixes/honorifics
        _shorter = re.sub(r'(?i)^(mus[ée]+e?\s*(national|nationale|municipal|municipale|d[eu]\s*)?)', 'Musée ', venue_string).strip()
        if _shorter != venue_string:
            candidates = _search_entities(_shorter)
    
    if not candidates:
        # Try just the distinctive name words (e.g. "Marc Chagall" from "Musée national Marc Chagall")
        _words = venue_string.split()
        _distinctive = [w for w in _words if w.lower() not in
                       ('musée', 'musee', 'museum', 'national', 'nationale', 'gallery',
                        'galleria', 'the', 'of', 'de', 'du', 'des', 'le', 'la', 'les')]
        if _distinctive:
            _short_query = f"musée {' '.join(_distinctive)}"
            candidates = _search_entities(_short_query)
    
    if not candidates:
        print(f"  [venue_resolver] No Wikidata candidates for '{venue_string}'")
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
    
    # Step 3: Geo-disambiguate if city provided
    if city and len(museum_candidates) > 1:
        best = _geo_disambiguate(museum_candidates, city)
        if best:
            museum_candidates = [best]
    
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
    
    Returns list of {qid, label_en, label_local, aliases} for each work.
    """
    query = f"""
    SELECT ?work ?workLabel ?workAltLabel WHERE {{
      {{ ?work wdt:P195 wd:{venue_qid}. }}
      UNION
      {{ ?work wdt:P276 wd:{venue_qid}. }}
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
        for r in results:
            work_uri = r.get("work", {}).get("value", "")
            work_qid = work_uri.split("/")[-1] if work_uri else ""
            label = r.get("workLabel", {}).get("value", "")
            alt_label = r.get("workAltLabel", {}).get("value", "")
            
            if work_qid and label and not label.startswith("Q"):  # Skip unresolved QIDs
                works.append({
                    "qid": work_qid,
                    "label_en": label,
                    "label_local": label,  # Same for now; could add local-lang label
                    "aliases": [a.strip() for a in alt_label.split(",") if a.strip()] if alt_label else [],
                })
        
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
    
    Returns a set of canonical title strings.
    """
    titles = set()
    for work in works:
        label = work.get("label_en", "")
        if label and not label.startswith("Q") and len(label) >= 3:
            titles.add(label)
        local_label = work.get("label_local", "")
        if local_label and local_label != label and not local_label.startswith("Q"):
            titles.add(local_label)
    return titles


# --- Internal helpers ---

def _search_entities(query: str) -> List[Tuple[str, str]]:
    """Search Wikidata for entities matching a query string."""
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
            return []
        
        data = resp.json()
        results = [(r["id"], r.get("label", "")) for r in data.get("search", [])]
        return results
    except Exception as e:
        logger.warning(f"Wikidata search error: {e}")
        return []


def _get_instance_of(qid: str) -> Optional[str]:
    """Get the P31 (instance-of) value for an entity. Returns first matching museum type or None."""
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
    except Exception:
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
    
    if city_lat == 0.0 and city_lng == 0.0:
        # Can't geocode city — fall back to P131 chain matching
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
        if lat == 0.0 and lng == 0.0:
            # No coordinates — check P131 as fallback
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


def _geocode_city(city: str) -> Tuple[float, float]:
    """Get coordinates for a city name via Wikidata search."""
    try:
        # Search for the city
        results = _search_entities(city)
        if not results:
            return 0.0, 0.0
        
        # Take first result and get its coordinates
        for qid, label in results[:3]:
            lat, lng = _get_coordinates(qid)
            if lat != 0.0 or lng != 0.0:
                return lat, lng
        
        return 0.0, 0.0
    except Exception:
        return 0.0, 0.0


def _get_coordinates(qid: str) -> Tuple[float, float]:
    """Get P625 coordinates for a Wikidata entity."""
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
            return 0.0, 0.0
        
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
    except Exception:
        return 0.0, 0.0


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


def _infer_artist_from_name(venue_name: str) -> str:
    """Infer artist name from a museum name by stripping institutional prefixes.
    
    E.g. "musée Marc-Chagall" → "Marc Chagall"
         "Musée Matisse" → "Matisse"
    Returns empty string if no artist name can be inferred (e.g. "Uffizi Gallery").
    """
    # Strip common institutional words
    _STRIP_WORDS = {
        'musée', 'musee', 'museum', 'gallery', 'galleria', 'national', 'nationale',
        'municipal', 'municipale', 'fondation', 'foundation', 'centre', 'center',
        'the', 'of', 'de', 'du', 'des', 'le', 'la', 'les', "l'", 'art', 'arts',
        'moderne', 'modern', 'contemporain', 'contemporary', 'beaux',
    }
    
    words = re.sub(r'[-–]', ' ', venue_name).split()
    name_words = [w for w in words if w.lower().rstrip("'") not in _STRIP_WORDS and len(w) > 1]
    
    if not name_words:
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
