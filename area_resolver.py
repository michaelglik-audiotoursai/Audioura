"""Area resolver for walking-tour generalization (Phase 3).

Resolves location strings to area entities (city/neighborhood) via Wikidata,
with disambiguation. Genuinely shared utilities (disambiguation-page filtering,
coordinate lookup, haversine distance) are imported from venue_resolver.py — see
_filter_disambiguation_pages/_get_coordinates/_haversine import below (A3).
City-match validation is NOT shared: venue_resolver's version matches a free-text
city name via label string comparison (no resolved QID available at that call
site), while this module always has a resolved city_qid and validates via exact
QID match on the P131 chain, which is strictly more precise. Forcing these two
together would trade venue_resolver's necessary fallback for area_resolver's more
reliable QID check — kept separate deliberately, not an oversight.

Usage:
    from area_resolver import resolve_area, AreaResolution
    result = resolve_area("Beacon Hill, Boston")
    # → AreaResolution(city_qid='Q100', neighborhood_qid='Q800861', ...)
"""

import re
import math
import requests
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

from venue_resolver import (
    _filter_disambiguation_pages,
    _get_coordinates,
    _haversine as _haversine_km,
)

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
_USER_AGENT = "Audioura/2.2 (tour-generation; contact: support@audioura.com)"

# Landmark class roots for SPARQL (A1: explicit UNION)
LANDMARK_ROOTS = [
    "Q811979",   # architectural structure
    "Q4989906",  # monument
    "Q22698",    # park
    "Q174782",   # town square (plaza)
    "Q860861",   # sculpture
    "Q557141",   # public art
    "Q12280",    # bridge
    "Q16970",    # church building
    "Q5003624",  # memorial
    "Q839954",   # archaeological site
]

# Default bounding radii (A2)
NEIGHBORHOOD_RADIUS_KM = 1.5
CITY_RADIUS_KM = 2.0
MAX_RADIUS_KM = 3.0


@dataclass
class AreaResolution:
    """Resolved area from Wikidata."""
    city_qid: str = ""
    city_name: str = ""
    neighborhood_qid: str = ""
    neighborhood_name: str = ""
    center_lat: float = 0.0
    center_lng: float = 0.0
    bounding_radius_km: float = CITY_RADIUS_KM
    language: str = "en"
    country_qid: str = ""
    resolved: bool = False


@dataclass
class Landmark:
    """A discovered landmark with Wikidata-sourced data."""
    name: str
    qid: str = ""
    lat: float = 0.0
    lng: float = 0.0
    type_label: str = ""  # monument, park, church, etc.
    wikipedia_url: str = ""


def resolve_area(location_string: str) -> Optional[AreaResolution]:
    """Resolve a location string to a city/neighborhood area entity.
    
    Parses "Beacon Hill, Boston" → neighborhood + city, resolves both via Wikidata,
    applies disambiguation (A3: shared helpers from venue_resolver).
    
    Returns AreaResolution or None if unresolvable.
    """
    # Parse location into components
    neighborhood, city = _parse_location(location_string)
    
    if not city and not neighborhood:
        print(f"  [area_resolver] Could not parse location: '{location_string}'")
        return None
    
    # If only one component, treat as city
    if not city and neighborhood:
        city = neighborhood
        neighborhood = ""
    
    print(f"  [area_resolver] Parsed: city='{city}', neighborhood='{neighborhood}'")
    
    # Resolve city to QID
    city_qid, city_coords = _resolve_city(city)
    if not city_qid:
        print(f"  [area_resolver] Could not resolve city: '{city}'")
        return None
    
    city_lat, city_lng = city_coords
    
    # [LOCAL-3] If the resolved "city" is actually a country (e.g. "Nice, france" was
    # parsed as neighborhood="Nice", city="france"), swap: the neighborhood is really
    # the city. This handles "City, Country" inputs that were misinterpreted as
    # "Neighborhood, City" by the comma-split logic.
    if neighborhood and _is_country_type(city_qid):
        print(f"  [area_resolver] '{city}' resolved as country ({city_qid}), swapping: city='{neighborhood}'")
        city = neighborhood
        neighborhood = ""
        city_qid, city_coords = _resolve_city(city)
        if not city_qid:
            print(f"  [area_resolver] Could not resolve swapped city: '{city}'")
            return None
        city_lat, city_lng = city_coords
    
    print(f"  [area_resolver] City resolved: {city} → {city_qid} ({city_lat:.4f}, {city_lng:.4f})")
    
    # Resolve neighborhood if present
    neighborhood_qid = ""
    center_lat, center_lng = city_lat, city_lng
    radius_km = CITY_RADIUS_KM
    
    # [LOCAL-46] If the resolved entity is a region (not a city), use a wider radius.
    # Regions like "French Riviera" cover 50-100km+ of coastline — a 2km radius
    # would miss almost everything. Skip the check if already confirmed as a city type
    # (avoids redundant API call for common city resolutions).
    if not _is_city_type(city_qid) and _is_region_type(city_qid):
        radius_km = REGION_RADIUS_KM
        print(f"  [area_resolver] Entity is a region — using wider radius: {radius_km}km")
    
    if neighborhood:
        neighborhood_qid, nbhood_coords = _resolve_neighborhood(neighborhood, city, city_qid)
        if neighborhood_qid and nbhood_coords[0] != 0.0:
            center_lat, center_lng = nbhood_coords
            radius_km = NEIGHBORHOOD_RADIUS_KM
            print(f"  [area_resolver] Neighborhood resolved: {neighborhood} → {neighborhood_qid} "
                  f"({center_lat:.4f}, {center_lng:.4f})")
        elif neighborhood_qid:
            print(f"  [area_resolver] Neighborhood resolved: {neighborhood} → {neighborhood_qid} (no P625, using city center)")
        else:
            print(f"  [area_resolver] Neighborhood '{neighborhood}' not on Wikidata — using city center")
    
    # Detect language from country
    language = _detect_language(city_qid)
    country_qid = _get_country(city_qid)
    
    result = AreaResolution(
        city_qid=city_qid,
        city_name=city,
        neighborhood_qid=neighborhood_qid,
        neighborhood_name=neighborhood,
        center_lat=center_lat,
        center_lng=center_lng,
        bounding_radius_km=radius_km,
        language=language,
        country_qid=country_qid,
        resolved=True,
    )
    print(f"  [area_resolver] Resolved: center=({center_lat:.4f}, {center_lng:.4f}), "
          f"radius={radius_km}km, lang={language}")
    return result


def discover_landmarks(area: AreaResolution) -> List[Landmark]:
    """Discover landmarks in the resolved area via Wikidata SPARQL + Wikipedia.
    
    Three parallel discovery paths (A1, A2):
    1. SPARQL coordinate bounding box (PRIMARY for neighborhoods)
    2. P131 chain query (SECONDARY confidence filter)
    3. Wikipedia article extraction (neighborhood/city article)
    
    Returns list of Landmark objects with QID, coordinates, type.
    """
    landmarks = []
    
    # Path 1: SPARQL coordinate bounding box (A2: PRIMARY)
    sparql_landmarks = _sparql_coordinate_query(
        area.center_lat, area.center_lng, area.bounding_radius_km
    )
    landmarks.extend(sparql_landmarks)
    print(f"  [landmark_discovery] SPARQL coordinate query: {len(sparql_landmarks)} landmarks")
    
    # Path 2: If SPARQL yields < 5, try P131 chain (for city-level)
    if len(landmarks) < 5 and area.city_qid:
        p131_landmarks = _sparql_p131_query(area.neighborhood_qid or area.city_qid)
        # Deduplicate by QID
        existing_qids = {lm.qid for lm in landmarks if lm.qid}
        for lm in p131_landmarks:
            if lm.qid and lm.qid not in existing_qids:
                landmarks.append(lm)
                existing_qids.add(lm.qid)
        print(f"  [landmark_discovery] P131 chain supplement: +{len(p131_landmarks)} candidates "
              f"(total after dedup: {len(landmarks)})")
    
    # Path 3: Wikipedia article extraction
    wiki_landmarks = _wikipedia_landmark_extraction(area)
    existing_names = {lm.name.lower() for lm in landmarks}
    wiki_added = 0
    for lm in wiki_landmarks:
        if lm.name.lower() not in existing_names:
            landmarks.append(lm)
            existing_names.add(lm.name.lower())
            wiki_added += 1
    print(f"  [landmark_discovery] Wikipedia extraction: +{wiki_added} new names "
          f"(total: {len(landmarks)})")
    
    return landmarks


# ============================================================
# Internal helpers
# ============================================================

def _parse_location(location_string: str) -> Tuple[str, str]:
    """Parse 'Neighborhood, City' or 'City, State/Country' into (neighborhood, city)."""
    # Remove common tour-type phrases (as standalone phrases, not eating the rest of the string)
    clean = re.sub(r'\b(?:walking tour|biking tour|driving tour|audio tour|guided tour|self[- ]guided tour|tour|historic district)\b', '', location_string, flags=re.IGNORECASE).strip()
    
    # [LOCAL-46] Strip ALL transport-mode keywords from anywhere in the string.
    # After "tour" is stripped above, orphaned transport words remain (e.g. "French
    # Riviera biking" → "French Riviera biking" because "biking tour" was split into
    # separate "biking" + stripped "tour"). This comprehensive list matches the
    # _TRANSPORT_STRIP_WORDS set in generate_tour_text.py — kept aligned to avoid drift.
    _TRANSPORT_WORDS_RE = re.compile(
        r'\b(?:biking|cycling|bike|walking|hiking|running|driving|horseback|horse|'
        r'camel|camelback|dog|dogsled|dogsledding|sledding|mushing|husky|'
        r'auto|car|jeep|motorcycle|scooter|segway|safari|'
        r'boat|kayak|kayaking|canoe|canoeing|sailing)\b',
        re.IGNORECASE
    )
    clean = _TRANSPORT_WORDS_RE.sub('', clean)
    
    # [LOCAL-3] Strip leading transport-mode and filler words from the entire string.
    # Upstream normalization may leave orphaned mode words (e.g. "walking  in Nice, france"
    # after "tour" is stripped). These break the comma-split logic by attaching to the
    # neighborhood segment. Strip them here so the parser sees clean location names.
    _MODE_FILLER_RE = re.compile(
        r'^(?:(?:walking|biking|cycling|driving|running|self[- ]guided|guided|audio)\s+)*'
        r'(?:(?:tour|tours)\s+)?'
        r'(?:(?:in|of|around|through|to)\s+)?',
        re.IGNORECASE
    )
    clean = _MODE_FILLER_RE.sub('', clean).strip()
    
    # Collapse multiple spaces left by stripped words
    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    
    parts = [p.strip() for p in clean.split(',')]
    
    # [LOCAL-3] Also strip filler words from individual segments after split —
    # handles cases where the filler word is only on one segment (e.g. already-split
    # "in Nice" as parts[0]).
    _SEGMENT_FILLER_RE = re.compile(r'^(?:in|of|around|through|to|near)\s+', re.IGNORECASE)
    parts = [_SEGMENT_FILLER_RE.sub('', p).strip() for p in parts]
    # Remove empty segments that result from stripping
    parts = [p for p in parts if p]
    
    if len(parts) >= 2:
        # "Beacon Hill, Boston" or "Beacon Hill, Boston, MA"
        # First part is neighborhood/area, second is city
        neighborhood = parts[0]
        city = parts[1]
        # If third part looks like a state/country, append to city
        if len(parts) >= 3 and len(parts[2]) <= 3:
            city = f"{parts[1]}, {parts[2]}"
        return neighborhood, city
    elif parts:
        # Single name — treat as city
        return "", parts[0]
    else:
        # Everything was stripped — fall back to original input minus obvious tour words
        fallback = re.sub(r'\b(?:tour|tours)\b', '', location_string, flags=re.IGNORECASE).strip().strip(',').strip()
        parts = [p.strip() for p in fallback.split(',') if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
        elif parts:
            return "", parts[0]
        return "", location_string


def _resolve_city(city: str) -> Tuple[str, Tuple[float, float]]:
    """Resolve a city (or region) name to its Wikidata QID + coordinates.
    
    [LOCAL-46] Also resolves named regions (e.g. 'French Riviera' → Côte d'Azur Q182095).
    Priority: city/town > region > any entity with coordinates.
    """
    # Search Wikidata
    candidates = _search_entities(city)
    if not candidates:
        return "", (0.0, 0.0)
    
    # Filter disambiguation pages (A3)
    candidates = _filter_disambiguation_pages(candidates)
    if not candidates:
        return "", (0.0, 0.0)
    
    # Pick the first candidate that has P625 coordinates and is a city/town
    for qid, label in candidates[:5]:
        if _is_city_type(qid):
            lat, lng = _get_coordinates(qid)
            if lat != 0.0 or lng != 0.0:
                return qid, (lat, lng)
    
    # [LOCAL-46] Second pass: accept named regions (Côte d'Azur, Tuscany, etc.)
    for qid, label in candidates[:5]:
        if _is_region_type(qid):
            lat, lng = _get_coordinates(qid)
            if lat != 0.0 or lng != 0.0:
                print(f"  [area_resolver] Resolved as region: {label} → {qid}")
                return qid, (lat, lng)
    
    # Fallback: first candidate with coordinates
    for qid, label in candidates[:3]:
        lat, lng = _get_coordinates(qid)
        if lat != 0.0 or lng != 0.0:
            return qid, (lat, lng)
    
    return "", (0.0, 0.0)


def _resolve_neighborhood(neighborhood: str, city: str, city_qid: str) -> Tuple[str, Tuple[float, float]]:
    """Resolve a neighborhood name within a city, with disambiguation (A3)."""
    # Try city-qualified searches
    for query in [f"{neighborhood} {city}", f"{neighborhood} ({city})", neighborhood]:
        candidates = _search_entities(query)
        candidates = _filter_disambiguation_pages(candidates)
        
        for qid, label in candidates[:5]:
            # Validate: must be in the city (P131 chain or proximity)
            if _validate_city_match(qid, city, city_qid):
                lat, lng = _get_coordinates(qid)
                return qid, (lat, lng)
    
    return "", (0.0, 0.0)


def _search_entities(query: str) -> List[Tuple[str, str]]:
    """Search Wikidata for entities matching a query string."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "type": "item",
                "limit": 10,
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("search", []):
            results.append((item["id"], item.get("label", "")))
        return results
    except Exception:
        return []



def _validate_city_match(qid: str, city: str, city_qid: str) -> bool:
    """Validate an entity is in the specified city (P131 chain or 30km proximity)."""
    try:
        # Check P131 chain
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
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            claims = entity.get("claims", {})
            
            # Walk P131 chain (up to 3 levels)
            for claim in claims.get("P131", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                admin_qid = value.get("id", "")
                if admin_qid == city_qid:
                    return True
                # Check one more level up
                if admin_qid:
                    resp2 = requests.get(
                        _WIKIDATA_API,
                        params={"action": "wbgetentities", "ids": admin_qid, "props": "claims", "format": "json"},
                        headers={"User-Agent": _USER_AGENT},
                        timeout=5,
                    )
                    if resp2.status_code == 200:
                        entity2 = resp2.json().get("entities", {}).get(admin_qid, {})
                        for c2 in entity2.get("claims", {}).get("P131", []):
                            v2 = c2.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                            if v2.get("id") == city_qid:
                                return True
        
        # Fallback: coordinate proximity (30km)
        entity_lat, entity_lng = _get_coordinates(qid)
        city_lat, city_lng = _get_coordinates(city_qid)
        if entity_lat != 0.0 and city_lat != 0.0:
            dist = _haversine_km(entity_lat, entity_lng, city_lat, city_lng)
            return dist <= 30.0
            
    except Exception:
        pass
    
    return False


def _is_city_type(qid: str) -> bool:
    """Check if a Wikidata entity is a city/town/municipality type."""
    city_types = {"Q515", "Q1549591", "Q486972", "Q3957", "Q7930989", "Q15284"}  # city, big city, municipality, town, city/town, municipality of US
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            for claim in entity.get("claims", {}).get("P31", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if value.get("id") in city_types:
                    return True
    except Exception:
        pass
    return False


def _is_country_type(qid: str) -> bool:
    """Check if a Wikidata entity is a country/sovereign state type.
    
    [LOCAL-3] Used to detect when _parse_location's 'city' candidate is actually a
    country (e.g. 'france' → Q142), so resolve_area can swap the neighborhood→city.
    """
    country_types = {
        "Q6256",      # country
        "Q3624078",   # sovereign state
        "Q7275",      # state (political entity)
        "Q1763527",   # constituent country
        "Q15634554",  # state with limited recognition
    }
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            for claim in entity.get("claims", {}).get("P31", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if value.get("id") in country_types:
                    return True
    except Exception:
        pass
    return False


# [LOCAL-46] Region radius: for named geographic regions (coastlines, riviera, valleys),
# use a much wider bounding radius than city-level tours.
REGION_RADIUS_KM = 15.0

def _is_region_type(qid: str) -> bool:
    """Check if a Wikidata entity is a geographic region (not city, not country).
    
    [LOCAL-46] Handles named regions like Côte d'Azur (Q182095), Tuscany, etc.
    These are larger than cities but smaller than countries — they need a wider
    bounding radius for landmark discovery but are valid tour areas.
    """
    region_types = {
        "Q82794",     # geographic region
        "Q1620908",   # geographic area
        "Q15642541",  # coastal region
        "Q34763",     # peninsula
        "Q39816",     # valley
        "Q35145263",  # coastal plain
        "Q185113",    # coast (general)
        "Q93352",     # coast (specific — e.g. French Riviera)
        "Q917448",    # riviera
        "Q11828004",  # historical region
        "Q3455524",   # historical administrative region
        "Q36784",     # administrative region (France: Provence-Alpes-Côte d'Azur)
        "Q200266",    # metropolitan area
    }
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(qid, {})
            for claim in entity.get("claims", {}).get("P31", []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if value.get("id") in region_types:
                    return True
    except Exception:
        pass
    return False




def _detect_language(city_qid: str) -> str:
    """Detect language from city's country (P17 → P37 official language)."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={"action": "wbgetentities", "ids": city_qid, "props": "claims", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(city_qid, {})
            # Get country (P17)
            for claim in entity.get("claims", {}).get("P17", []):
                country_qid = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
                if country_qid:
                    # Lookup country's official language (P37)
                    resp2 = requests.get(
                        _WIKIDATA_API,
                        params={"action": "wbgetentities", "ids": country_qid, "props": "claims", "format": "json"},
                        headers={"User-Agent": _USER_AGENT},
                        timeout=10,
                    )
                    if resp2.status_code == 200:
                        country = resp2.json().get("entities", {}).get(country_qid, {})
                        for lang_claim in country.get("claims", {}).get("P37", []):
                            lang_qid = lang_claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
                            # Map common language QIDs to ISO codes
                            lang_map = {
                                "Q150": "fr", "Q652": "it", "Q1860": "en", "Q188": "de",
                                "Q1321": "es", "Q7737": "ru", "Q5146": "pt", "Q9176": "ko",
                                "Q5287": "ja", "Q7850": "zh",
                            }
                            if lang_qid in lang_map:
                                return lang_map[lang_qid]
    except Exception:
        pass
    return "en"


def _get_country(city_qid: str) -> str:
    """Get country QID for a city."""
    try:
        resp = requests.get(
            _WIKIDATA_API,
            params={"action": "wbgetentities", "ids": city_qid, "props": "claims", "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entity = data.get("entities", {}).get(city_qid, {})
            for claim in entity.get("claims", {}).get("P17", []):
                return claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
    except Exception:
        pass
    return ""


def _sparql_coordinate_query(lat: float, lng: float, radius_km: float) -> List[Landmark]:
    """Find landmarks near coordinates using Wikipedia geosearch API.
    
    Primary discovery path (A2). Uses Wikipedia's geosearch which is faster
    and more reliable than Wikidata SPARQL wikibase:around.
    Then enriches with Wikidata QIDs for verified landmarks.
    """
    radius_m = int(radius_km * 1000)
    # Wikipedia geosearch caps at 10000m
    radius_m = min(radius_m, 10000)
    
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{lat}|{lng}",
                "gsradius": radius_m,
                "gslimit": 50,
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        results = data.get("query", {}).get("geosearch", [])
        
        landmarks = []
        # Filter: skip list/timeline/category-style articles
        skip_prefixes = ('list of', 'timeline of', 'history of', 'category:',
                        'demographics of', 'geography of')
        
        for r in results:
            title = r.get("title", "")
            if not title:
                continue
            if title.lower().startswith(skip_prefixes):
                continue
            # Skip the area article itself
            if 'beacon hill' in title.lower() and 'boston' in title.lower():
                continue
                
            lm_lat = r.get("lat", 0.0)
            lm_lng = r.get("lon", 0.0)
            
            landmarks.append(Landmark(
                name=title,
                qid="",  # Will be enriched via Wikidata lookup if needed
                lat=lm_lat,
                lng=lm_lng,
                type_label="",
            ))
        
        # Enrich top landmarks with Wikidata QIDs (batch lookup)
        _enrich_with_qids(landmarks[:30])
        
        return landmarks
        
    except requests.exceptions.Timeout:
        print(f"  [landmark_discovery] Wikipedia geosearch timeout")
        return []
    except Exception as e:
        print(f"  [landmark_discovery] Geosearch error: {e}")
        return []


def _enrich_with_qids(landmarks: List[Landmark]):
    """Enrich landmarks with Wikidata QIDs via Wikipedia→Wikidata sitelink lookup."""
    if not landmarks:
        return
    
    # Batch lookup: get Wikidata item IDs for Wikipedia titles
    titles = [lm.name for lm in landmarks[:30]]
    titles_str = "|".join(titles)
    
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": titles_str,
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return
        
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        
        # Build title→QID map
        title_to_qid = {}
        for page_id, page in pages.items():
            if page_id == "-1":
                continue
            title = page.get("title", "")
            qid = page.get("pageprops", {}).get("wikibase_item", "")
            if title and qid:
                title_to_qid[title] = qid
        
        # Apply QIDs to landmarks
        for lm in landmarks:
            if lm.name in title_to_qid:
                lm.qid = title_to_qid[lm.name]
                
    except Exception:
        pass


def _sparql_p131_query(area_qid: str) -> List[Landmark]:
    """SPARQL query using P131 chain (secondary, for cities without neighborhood-level data)."""
    type_values = " ".join(f"wd:{qid}" for qid in LANDMARK_ROOTS)
    
    query = f"""
    SELECT ?item ?itemLabel ?coord ?typeLabel WHERE {{
      VALUES ?type {{ {type_values} }}
      ?item wdt:P31/wdt:P279* ?type .
      ?item wdt:P131* wd:{area_qid} .
      ?item wdt:P625 ?coord .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    LIMIT 300
    """
    
    try:
        resp = requests.get(
            _WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        landmarks = []
        seen_qids = set()
        
        for binding in data.get("results", {}).get("bindings", []):
            item_uri = binding.get("item", {}).get("value", "")
            qid = item_uri.split("/")[-1] if item_uri else ""
            if not qid or qid in seen_qids:
                continue
            seen_qids.add(qid)
            
            label = binding.get("itemLabel", {}).get("value", "")
            if label.startswith("Q") and label[1:].isdigit():
                continue
            
            coord_str = binding.get("coord", {}).get("value", "")
            lm_lat, lm_lng = _parse_wkt_point(coord_str)
            
            type_label = binding.get("typeLabel", {}).get("value", "")
            
            landmarks.append(Landmark(
                name=label, qid=qid, lat=lm_lat, lng=lm_lng, type_label=type_label,
            ))
        
        return landmarks
        
    except Exception:
        return []


def _wikipedia_landmark_extraction(area: AreaResolution) -> List[Landmark]:
    """Extract landmark names from the area's Wikipedia article (section headers, bold names)."""
    landmarks = []
    
    # Fetch the neighborhood or city Wikipedia article
    target_name = area.neighborhood_name or area.city_name
    if not target_name:
        return []
    
    try:
        # Use Wikipedia API to get article text
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": target_name,
                "prop": "extracts",
                "explaintext": True,
                "format": "json",
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        
        for page_id, page in pages.items():
            if page_id == "-1":
                continue
            text = page.get("extract", "")
            if not text:
                continue
            
            # Extract from section headers (== Name ==)
            sections = re.findall(r'^==+\s*(.+?)\s*==+', text, re.MULTILINE)
            # Filter out generic sections and geographic/political names
            generic = {'history', 'geography', 'demographics', 'economy', 'transportation',
                      'education', 'government', 'politics', 'climate', 'references',
                      'see also', 'external links', 'further reading', 'notes',
                      'notable residents', 'sister cities', 'demographics', 'culture',
                      'media', 'sports', 'infrastructure', 'architecture', 'overview',
                      'etymology', 'description', 'location', 'population', 'gallery',
                      'places', 'communities', 'countries', 'states', 'regions',
                      'canada', 'united states', 'united kingdom', 'england', 'wales',
                      'scotland', 'ireland', 'australia', 'france', 'germany', 'italy',
                      'other uses', 'fictional places', 'people', 'music', 'film',
                      'television', 'books', 'other', 'arts and entertainment'}
            for section in sections:
                section_lower = section.lower().strip()
                if (section_lower not in generic and 
                    len(section) > 3 and len(section) < 60 and
                    not section_lower.startswith('list of') and
                    not section_lower.startswith('see ') and
                    # Must look like a proper name (starts with capital, not all caps)
                    section[0].isupper() and not section.isupper()):
                    landmarks.append(Landmark(name=section))
            
    except Exception:
        pass
    
    return landmarks


def _parse_wkt_point(wkt: str) -> Tuple[float, float]:
    """Parse 'Point(lng lat)' WKT format to (lat, lng)."""
    match = re.search(r'Point\(([-\d.]+)\s+([-\d.]+)\)', wkt)
    if match:
        lng = float(match.group(1))
        lat = float(match.group(2))
        return (lat, lng)
    return (0.0, 0.0)




# ============================================================
# Landmark verification (A4: separate function, not in museum path)
# ============================================================

def verify_landmarks(poi_list: List[Dict], area: AreaResolution, landmarks: List[Landmark]) -> Dict:
    """Verify GPT-proposed walking-tour stops against discovered landmarks.
    
    A4: Separate function sharing helpers with _verify_works_v2 but NOT threaded
    through the museum path.
    
    A5: Wire verified flag — verified landmarks stated plainly, unverified get
    B1-strength hedged narration.
    
    A7: P625 coordinates from Wikidata replace fabricated coordinates.
    
    Returns dict with:
        - pois: list of verified/unverified POI dicts (with verified flag + coordinates)
        - evidence_log: per-stop verification evidence
        - canonical_landmarks: the discovered landmark names (for logging)
        - tier: computed tier string
    """
    if not landmarks:
        return {
            "pois": poi_list,
            "evidence_log": {},
            "canonical_landmarks": set(),
            "tier": "unresolvable",
        }
    
    # Build canonical name set for matching
    canonical_names = set()
    landmark_by_name = {}  # lowercase name → Landmark
    for lm in landmarks:
        if lm.name:
            canonical_names.add(lm.name)
            landmark_by_name[lm.name.lower()] = lm
            # Also add without common prefixes (The, Saint, St.)
            _stripped = re.sub(r'^(The|Saint|St\.?)\s+', '', lm.name, flags=re.IGNORECASE)
            if _stripped != lm.name:
                landmark_by_name[_stripped.lower()] = lm
    
    evidence_log = {}
    verified_pois = []
    n_verified = 0
    
    for poi in poi_list:
        stop_name = poi.get('name', '')
        if not stop_name:
            continue
        
        # Try to match against canonical landmarks
        matched_landmark = _match_stop_to_landmark(stop_name, landmarks)
        
        if matched_landmark:
            # VERIFIED: landmark found in discovered set
            poi['verified'] = True
            # A7: Replace coordinates with Wikidata P625 if available
            if matched_landmark.lat != 0.0 or matched_landmark.lng != 0.0:
                poi['wikidata_lat'] = matched_landmark.lat
                poi['wikidata_lng'] = matched_landmark.lng
            poi['wikidata_qid'] = matched_landmark.qid
            evidence_log[stop_name] = {
                "status": "VERIFIED",
                "canonical_name": matched_landmark.name,
                "qid": matched_landmark.qid,
                "type": matched_landmark.type_label,
                "coordinates": f"{matched_landmark.lat:.6f}, {matched_landmark.lng:.6f}" if matched_landmark.lat else "",
            }
            n_verified += 1
        else:
            # UNVERIFIED: not in discovered landmarks
            # A5: verified=False triggers hedged narration
            poi['verified'] = False
            evidence_log[stop_name] = {
                "status": "UNVERIFIED",
                "reason": "not in discovered landmarks",
            }
        
        verified_pois.append(poi)
    
    # Compute tier based on evidence
    n_landmarks_with_qid = sum(1 for lm in landmarks if lm.qid)
    if n_verified == 0 and n_landmarks_with_qid == 0:
        tier = "unresolvable"
    elif n_landmarks_with_qid >= 8:
        tier = "rich"
    elif n_landmarks_with_qid >= 3:
        tier = "medium"
    else:
        tier = "thin"
    
    print(f"  [verify_landmarks] {n_verified}/{len(poi_list)} stops verified against "
          f"{len(landmarks)} discovered landmarks (tier: {tier})")
    
    return {
        "pois": verified_pois,
        "evidence_log": evidence_log,
        "canonical_landmarks": canonical_names,
        "tier": tier,
    }


def _normalize_landmark_name(name: str) -> str:
    """Normalize a landmark name for matching: accent-fold, lowercase, strip articles/prepositions.

    LOCAL-290 (Fault 3 / D187 pattern): "Old Town of Menton" must match "Old Town Menton",
    "Île Sainte-Marguerite" must match "Ile Sainte-Marguerite", "La Croisette" must match
    "Cannes Croisette". The key operations:
      1. Accent folding (Île→Ile, Èze→Eze, Château→Chateau)
      2. Strip French/English articles and short prepositions
      3. Collapse whitespace and punctuation
    """
    import unicodedata
    # Accent fold
    nfkd = unicodedata.normalize('NFKD', name)
    folded = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase
    s = folded.lower().strip()
    # Remove punctuation (hyphens→spaces, apostrophes→space to split elisions like d'Or→d Or)
    s = s.replace("'", " ").replace("\u2019", " ").replace("-", " ")
    s = re.sub(r'[^\w\s]', ' ', s)
    # Strip articles and short prepositions (French + English)
    _ARTICLES = {'the', 'a', 'an', 'le', 'la', 'les', 'l', 'de', 'du', 'des',
                 'un', 'une', 'of', 'et', 'and', 'd', 'au', 'aux', 'en', 'sur'}
    words = s.split()
    content = [w for w in words if w not in _ARTICLES and len(w) > 1]
    return ' '.join(content) if content else ' '.join(words)


def _match_stop_to_landmark(stop_name: str, landmarks: List[Landmark]) -> Optional[Landmark]:
    """Match a GPT-proposed stop name to a discovered landmark.

    LOCAL-290 (Fault 3): Uses accent-folded, article-stripped normalization so that
    "Old Town of Menton" matches "Old Town Menton" and "Île Sainte-Marguerite" matches
    "Ile Sainte-Marguerite". This is the D187 pattern — name fragmentation that caused
    0/7 matches against 28 discovered landmarks.
    """
    stop_norm = _normalize_landmark_name(stop_name)
    stop_lower = stop_name.lower().strip()

    for lm in landmarks:
        if not lm.name:
            continue
        lm_norm = _normalize_landmark_name(lm.name)
        lm_lower = lm.name.lower().strip()

        # Exact normalized match
        if stop_norm == lm_norm:
            return lm

        # Substring containment on normalized forms (either direction)
        if len(stop_norm) >= 4 and len(lm_norm) >= 4:
            if stop_norm in lm_norm or lm_norm in stop_norm:
                return lm

        # Also try raw lowercase substring (handles "Cap Ferrat" in "Saint-Jean-Cap-Ferrat")
        if len(stop_lower) >= 4 and len(lm_lower) >= 4:
            if stop_lower in lm_lower or lm_lower in stop_lower:
                return lm

        # Word-overlap score (Jaccard-style) on normalized content words
        stop_words = set(stop_norm.split())
        lm_words = set(lm_norm.split())
        if stop_words and lm_words:
            overlap = len(stop_words & lm_words)
            shorter = min(len(stop_words), len(lm_words))
            # Match if >=60% of the SHORTER name's words appear in the longer
            if shorter > 0 and overlap / shorter >= 0.60:
                return lm

    return None


# ============================================================
# Cache integration (A6: key by area QID, store radius)
# ============================================================

def cache_get_area(area: AreaResolution) -> Optional[List[Landmark]]:
    """Check venue_corpus cache for previously discovered landmarks.
    
    A6: Key by area QID (neighborhood or city), stores radius in pages_json.
    """
    qid = area.neighborhood_qid or area.city_qid
    if not qid:
        return None
    
    try:
        import os
        db_url = os.environ.get("DATABASE_URL", "postgresql://admin:password123@postgres-2:5432/audiotours")
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT canonical_titles_json, pages_json, tier
            FROM venue_corpus
            WHERE qid = %s AND expires_at > NOW() AND corpus_version >= 3
        """, (qid,))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        import json
        titles_data = row[0]  # JSONB → dict/list
        pages_data = row[1]   # Contains radius + landmark details
        tier = row[2]
        
        if isinstance(titles_data, str):
            titles_data = json.loads(titles_data)
        if isinstance(pages_data, str):
            pages_data = json.loads(pages_data)
        
        # Reconstruct Landmark objects from cached data
        landmarks = []
        if isinstance(titles_data, list):
            for item in titles_data:
                if isinstance(item, dict):
                    landmarks.append(Landmark(
                        name=item.get("name", ""),
                        qid=item.get("qid", ""),
                        lat=item.get("lat", 0.0),
                        lng=item.get("lng", 0.0),
                        type_label=item.get("type_label", ""),
                    ))
        
        if landmarks:
            print(f"  [area_cache] HIT for {qid}: {len(landmarks)} landmarks (tier={tier})")
            return landmarks
        return None
        
    except Exception as e:
        print(f"  [area_cache] Read error: {e}")
        return None


def cache_put_area(area: AreaResolution, landmarks: List[Landmark], tier: str):
    """Store discovered landmarks in venue_corpus cache.
    
    A6: Stores radius in pages_json so future radius changes don't silently reuse.
    """
    qid = area.neighborhood_qid or area.city_qid
    if not qid:
        return
    
    try:
        import os, json
        db_url = os.environ.get("DATABASE_URL", "postgresql://admin:password123@postgres-2:5432/audiotours")
        ttl_days = int(os.environ.get("VENUE_CACHE_TTL_DAYS", "30"))
        
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Serialize landmarks
        titles_json = json.dumps([{
            "name": lm.name,
            "qid": lm.qid,
            "lat": lm.lat,
            "lng": lm.lng,
            "type_label": lm.type_label,
        } for lm in landmarks])
        
        # Pages_json stores metadata including radius (A6)
        pages_json = json.dumps({
            "radius_km": area.bounding_radius_km,
            "center_lat": area.center_lat,
            "center_lng": area.center_lng,
            "discovery_method": "wikipedia_geosearch",
            "n_with_qid": sum(1 for lm in landmarks if lm.qid),
        })
        
        venue_name = f"{area.neighborhood_name or area.city_name} walking area"
        
        cur.execute("""
            INSERT INTO venue_corpus (qid, venue_name, canonical_titles_json, pages_json, 
                                     tier, language, corpus_version, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, 3, NOW() + INTERVAL '%s days')
            ON CONFLICT (qid) DO UPDATE SET
                canonical_titles_json = EXCLUDED.canonical_titles_json,
                pages_json = EXCLUDED.pages_json,
                tier = EXCLUDED.tier,
                corpus_version = 3,
                expires_at = NOW() + INTERVAL '%s days'
        """, (qid, venue_name, titles_json, pages_json, tier, area.language, ttl_days, ttl_days))
        
        conn.commit()
        conn.close()
        print(f"  [area_cache] STORED {qid}: {len(landmarks)} landmarks (tier={tier}, TTL={ttl_days}d)")
        
    except Exception as e:
        print(f"  [area_cache] Write error (non-fatal): {e}")
