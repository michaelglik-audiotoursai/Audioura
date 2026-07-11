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
    Gets labels in BOTH English and the local language for cross-language matching.
    """
    query = f"""
    SELECT ?work ?workLabel ?workAltLabel ?workLabel_en WHERE {{
      {{ ?work wdt:P195 wd:{venue_qid}. }}
      UNION
      {{ ?work wdt:P276 wd:{venue_qid}. }}
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
        for r in results:
            work_uri = r.get("work", {}).get("value", "")
            work_qid = work_uri.split("/")[-1] if work_uri else ""
            label = r.get("workLabel", {}).get("value", "")
            label_en = r.get("workLabel_en", {}).get("value", "") or label
            alt_label = r.get("workAltLabel", {}).get("value", "")
            
            if work_qid and label and not label.startswith("Q"):  # Skip unresolved QIDs
                works.append({
                    "qid": work_qid,
                    "label_en": label_en,
                    "label_local": label,
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
CORPUS_VERSION = 1  # Increment when pipeline improvements invalidate cached data


# TODO(S94): remove in-code password fallback; prod must use DATABASE_URL/DB_PASSWORD env only
def _get_db_connection():
    """Get a Postgres connection for venue_corpus cache. Returns None if unavailable."""
    try:
        import psycopg2
        # Use VENUE_CACHE_DB_URL first, fall back to DATABASE_URL, then container default
        db_url = os.environ.get('VENUE_CACHE_DB_URL',
                 os.environ.get('DATABASE_URL', 'postgresql://admin:password123@postgres-2:5432/audiotours'))
        # Fix localhost references for container-to-container communication
        if '@localhost:' in db_url:
            db_url = db_url.replace('@localhost:', '@postgres-2:')
        # Fix auth mismatch: tour-generator uses admin:admin but postgres-2 expects password123
        if 'admin:admin@' in db_url and 'postgres-2' in db_url:
            db_url = db_url.replace('admin:admin@', 'admin:password123@')
        conn = psycopg2.connect(db_url, connect_timeout=5)
        # Auto-create venue_corpus table if not exists (idempotent)
        _ensure_table(conn)
        return conn
    except Exception as e:
        print(f"  [venue_cache] DB connection failed: {e}")
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
                    tier VARCHAR(10) NOT NULL,
                    corpus_version INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)
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
