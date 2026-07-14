"""
Modified version of generate_tour_text.py that includes geo coordinates for the first stop
"""
import os
import sys
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from enhanced_tour_templates_fixed import get_enhanced_tour_template, validate_enhanced_poi_knowledge
from poi_inclusion_exceptions import should_include_in_restaurant_tour, should_include_in_walking_tour
# NOTE: tour_type_detector.detect_tour_type() is intentionally NOT used here.
# The local _classify_tour_category() below (two-arg version returning lowercase category)
# serves a different purpose from the imported one (one-arg, returns CONTEXTUAL/OPERATIONAL).
from enhanced_prompt_generator import generate_enhanced_prompt
from datetime import datetime
import re
from collections import Counter
from math import radians, sin, cos, asin, sqrt
from tour_settings import (
    WALKING_LEG_TARGET_KM, WALKING_LEG_HARD_KM, WALKING_TOTAL_HARD_KM,
    MAX_REPLACEMENT_ATTEMPTS,
)

# PHASE 3C: neighborhood/borough -> canonical city map for address-based location guard.
# Covers USPS city names that differ from the city users request tours in.
_NEIGHBORHOOD_TO_CITY = {
    # Boston neighborhoods with separate USPS city names
    'east boston': 'boston', 'jamaica plain': 'boston', 'roxbury': 'boston',
    'dorchester': 'boston', 'south boston': 'boston', 'mattapan': 'boston',
    'brighton': 'boston', 'allston': 'boston', 'hyde park': 'boston',
    'roslindale': 'boston', 'west roxbury': 'boston', 'charlestown': 'boston',
    # NYC boroughs
    'brooklyn': 'new york', 'queens': 'new york', 'bronx': 'new york', 'staten island': 'new york',
    # Newton villages
    'newton centre': 'newton', 'west newton': 'newton', 'newton corner': 'newton',
    'newton highlands': 'newton', 'newtonville': 'newton',
}

# S15 safety net: if the location string explicitly names a non-museum tour type,
# do NOT force museum category on the strength of venue_name alone.
# Prevents GPT-hallucinated venue_names on walking/restaurant requests from
# silently flipping the category and injecting a single-venue museum constraint.
# Word-boundary anchored to avoid false positives ("touring" vs "tour").
_EXPLICIT_NON_MUSEUM_TOUR_RE = re.compile(
    r'\b(walking|restaurant|food|dining|culinary|self[- ]guided|architecture|architectural'
    r'|pub\s+crawl|bike|cycling|biking|shopping)'
    r'\s+tour\b',
    re.IGNORECASE,
)

# Multi-building institution keywords — these should NOT be classified as single-venue museum
# even if GPT returns a venue_name. They imply multiple distinct locations.
# PLURAL-ONLY: "libraries" (multi) blocks museum; "library" (single) does not.
_MULTI_BUILDING_INSTITUTION_RE = re.compile(
    r'\b(libraries|churches|schools|synagogues|mosques|temples'
    r'|buildings|branches|historic\s+houses|fire\s+stations)\b',
    re.IGNORECASE,
)

def compute_tier(n_verified: int, evidence_strength: int) -> str:
    """Return the degradation tier given verification count and evidence strength.

    Parameters
    ----------
    n_verified : int
        Number of verified entries (0 means entity could not be resolved).
    evidence_strength : int
        Number of unique QIDs returned from SPARQL works query.

    Returns
    -------
    str
        One of 'unresolvable', 'rich', 'medium', 'thin'.
    """
    if n_verified == 0:
        return "unresolvable"
    elif evidence_strength >= 8:
        return "rich"
    elif evidence_strength >= 3:
        return "medium"
    else:
        return "thin"


def _haversine_km(a, b):
    """Straight-line distance in km between two (lat, lng) tuples."""
    lat1, lon1 = a; lat2, lon2 = b
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * 6371.0 * asin(sqrt(h))


def _parse_coords(s):
    """Parse 'lat, lng' string into (float, float) or None."""
    m = re.match(r'\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', s or '')
    return (float(m.group(1)), float(m.group(2))) if m else None


def _address_matches_location(address, loc):
    """Return True if any address token (after postcode stripping, short-token filtering,
    and neighborhood aliasing) appears in the location string, or if we cannot determine
    a mismatch (empty address, single token).
    Module-level so both PHASE 3C and Part C replacement checks can call it.
    """
    if not address:
        print(f"   PHASE 3C: WARN address empty -- cannot verify location")
        return True
    parts = [p.strip().lower() for p in address.split(',')]
    if len(parts) < 2:
        return True
    loc_lower = loc.lower()
    loc_words = set(re.findall(r'[a-z]+', loc_lower))
    # Strip postcode-looking tokens, UK-style postcodes, and short tokens (<=3 chars)
    # that are state/country codes (MA, UK, US) — they match too broadly.
    text_parts = [
        p for p in parts
        if len(p) >= 4
        and not re.match(r'^\d{4,6}(\s*[a-z]{0,4})?$', p)          # pure zip: '02458', '02458-1234'
        and not re.match(r'^[a-z]{1,2}\d{1,2}[a-z]?\s*\d[a-z]{2}$', p)  # UK postcode
        and not re.match(r'^[a-z]{2}\s+\d{4,6}', p)                 # state+zip: 'ma 01901'
    ]
    for token in text_parts:
        effective = _NEIGHBORHOOD_TO_CITY.get(token, token)
        # Word-set subset check: all words in effective must appear as whole words in loc.
        # Prevents 'lynn' matching 'lynnfield', 'york' matching 'new york' (reverse).
        effective_words = set(re.findall(r'[a-z]+', effective))
        if effective_words and effective_words.issubset(loc_words):
            return True
    return False

def analyze_tour_intent(user_request, api_key):
    """
    Enhanced AI-based intent analysis to detect specialized themes like books, movies, products.
    Cost: ~$0.0008 per analysis
    """
    intent_prompt = f"""Analyze this tour request and extract the key information:

Request: "{user_request}"

Please provide ONLY a JSON response with these fields:
{{
    "poi_type": "specific type of locations requested (e.g., restaurants, shops, stores, museums, book locations, movie filming sites, etc.) — IMPORTANT: poi_type must always be a single string, never a JSON array. If multiple types are detected, combine them with 'or' — e.g. 'restaurants or museums'.",
    "location": "geographic area",
    "theme_type": "BOOK/MOVIE/PRODUCT/STANDARD - identify if this is a themed tour",
    "theme_name": "name of book, movie, or specific product if applicable",
    "requirements": "any specific criteria mentioned",
    "business_hours_relevant": true/false,
    "accessibility_mentioned": true/false,
    "needs_research": true/false,
    "venue_name": "The full official name of the institution ONLY when the ENTIRE tour is bounded by one specific building or campus (e.g. a single museum, historic house, gallery, or library). Use the institution's complete official name including suffixes like 'Museum', 'Gallery', 'Library' — never a shortened nickname (e.g. 'Museum of Fine Arts, Boston' not 'MFA'). Return null if the tour spans a city, district, neighborhood, multiple venues, or any open-ended area. If you are unsure whether the request names a specific bounded institution or just a region, return null.",
    "geographic_scope": "The most specific bounded area the tour must stay within, in the user's own terms — a street or corridor, a square, a named district or quarter, a waterfront, a campus, a market, a cluster of blocks, or a single building. Copy the phrasing the request uses. If the request only names a whole city or town with no tighter anchor, return that city/town name. Never invent a tighter scope than the request states.",
    "scope_precision": "One of exactly these four strings: BUILDING (one structure) | CORRIDOR (one street or strip) | DISTRICT (a neighbourhood, quarter, square, or named area) | CITY (a whole town with no tighter anchor given)."
}}

Examples:
- "Tour of restaurants in North End, Boston" → poi_type: "restaurants", theme_type: "STANDARD", venue_name: null
- "Walking tour based on Tomorrow and Tomorrow and Tomorrow book" → poi_type: "book locations", theme_type: "BOOK", theme_name: "Tomorrow, and Tomorrow, and Tomorrow", venue_name: null
- "Harry Potter filming locations in Boston" → poi_type: "filming locations", theme_type: "MOVIE", theme_name: "Harry Potter", venue_name: null
- "Fancy cheese shops in Cambridge" → poi_type: "cheese shops", theme_type: "PRODUCT", theme_name: "fancy cheese", venue_name: null
- "Jackson Homestead and Museum Newton, MA" → poi_type: "museum exhibits", theme_type: "STANDARD", venue_name: "Jackson Homestead and Museum"
- "Tour inside the MFA Boston" → poi_type: "museum exhibits", theme_type: "STANDARD", venue_name: "Museum of Fine Arts, Boston"
- "Tour of the Met" → poi_type: "museum exhibits", theme_type: "STANDARD", venue_name: "The Metropolitan Museum of Art"
- "Walking tour in Newton, MA" → poi_type: "landmarks", theme_type: "STANDARD", venue_name: null
- "Restaurant tour in Newton Center" → poi_type: "restaurants", theme_type: "STANDARD", venue_name: null
- "Cambridge museums tour" → poi_type: "museums", theme_type: "STANDARD", venue_name: null
- "Boston Museum of Science and surroundings" → poi_type: "science exhibits", theme_type: "STANDARD", venue_name: null
- "Walking tour starting at Faneuil Hall, Boston" → poi_type: "landmarks", theme_type: "STANDARD", venue_name: null
- "Restaurant tour near the Prudential Center, Boston" → poi_type: "restaurants", theme_type: "STANDARD", venue_name: null
- "Architecture tour around the Lyman Estate" → poi_type: "buildings", theme_type: "STANDARD", venue_name: null
- "Self-guided tour of Beacon Hill" → poi_type: "landmarks", theme_type: "STANDARD", venue_name: null
- "walking tour over Beacon St in Brookline, ma" → geographic_scope: "Beacon St, Brookline", scope_precision: "CORRIDOR"
- "Fairbanks House Tour in Dedham, ma" → venue_name: "Fairbanks House", geographic_scope: "Fairbanks House", scope_precision: "BUILDING"
- "tour of the old mill district in Lowell" → geographic_scope: "the old mill district, Lowell", scope_precision: "DISTRICT"
- "walking tour around the harbor in Gloucester" → geographic_scope: "the harbor waterfront, Gloucester", scope_precision: "DISTRICT"
- "walking tour in Newton, MA" → geographic_scope: "Newton, MA", scope_precision: "CITY"
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a tour planning assistant. Respond only with valid JSON."},
            {"role": "user", "content": intent_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 400
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            result = response.json()
            intent_text = result["choices"][0]["message"]["content"]
            print(f"Intent analysis response: {intent_text}")
            return json.loads(intent_text)
        else:
            print(f"Intent analysis failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"Intent analysis error: {e}")
        return None

def validate_poi_knowledge(poi_list, intent, location, api_key):
    """
    Enhanced validation for specialized themes and generic POI detection.
    Returns True if knowledge is sufficient, False if insufficient.
    """
    if not poi_list or len(poi_list) == 0:
        return False, "No POIs were generated"
    
    # Enhanced generic patterns detection
    generic_patterns = [
        r'^(Store|Shop|Restaurant|Location|Exhibit|Building|Stop)\s+\d+$',
        r'^(Unknown|Generic|Sample)\s+',
        r'^[A-Za-z]+\s+\d+$',  # Single word + number pattern
        r'^Walking Tour \d+$',  # Specific pattern from the issue
        r'^Tour Stop \d+$',
        r'^Point \d+$'
    ]
    
    # Check for fictional content patterns (hallucinations)
    fictional_patterns = [
        r'sculpture titled "Tomorrow.*?Tomorrow.*?Tomorrow"',
        r'Created by renowned artist\s*,',  # Missing artist name
        r'stands the impressive.*?monumental work',
        r'fusion of art, history, and culture'
    ]
    
    generic_count = 0
    fictional_count = 0
    
    for poi in poi_list:
        poi_name = poi.get('name', '')
        poi_description = poi.get('description', '')
        
        # Check for generic names
        for pattern in generic_patterns:
            if re.match(pattern, poi_name):
                generic_count += 1
                break
        
        # Check for fictional/hallucinated content
        full_text = f"{poi_name} {poi_description}"
        for pattern in fictional_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                fictional_count += 1
                break
    
    # Enhanced validation for themed tours
    if intent and intent.get('theme_type') in ['BOOK', 'MOVIE']:
        theme_name = intent.get('theme_name', '')
        if generic_count > 0 or fictional_count > 0:
            return False, f"Unable to generate authentic locations for '{theme_name}'. The AI is creating fictional content instead of real locations. Please try a different theme or provide more specific location details."
    
    # Standard validation for regular tours
    if generic_count > len(poi_list) / 2:
        poi_type = intent.get('poi_type', 'locations') if intent else 'locations'
        if isinstance(poi_type, list):
            poi_type = " or ".join(poi_type)
        return False, f"Insufficient data available for {poi_type} in {location}. Please try a different location or POI type."
    
    if fictional_count > 0:
        return False, f"AI generated fictional content instead of real locations. Please try a more specific request."
    
    return True, "Knowledge validation passed"

def verify_poi_matches_type(poi_name, poi_type, api_key):
    """
    Verify each POI matches the requested type.
    Cost: ~$0.0004 per POI
    """
    verification_prompt = f"""Is "{poi_name}" actually a {poi_type.rstrip('s')}?

Respond with ONLY a JSON object:
{{
    "matches": true/false,
    "reason": "brief explanation",
    "confidence": "high/medium/low"
}}

Example: For "Paul Revere House" and poi_type "restaurant":
{{"matches": false, "reason": "Paul Revere House is a historic museum, not a restaurant", "confidence": "high"}}
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a location verification assistant. Respond only with valid JSON."},
            {"role": "user", "content": verification_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 100
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            result = response.json()
            verification_text = result["choices"][0]["message"]["content"]
            return json.loads(verification_text)
        else:
            return {"matches": True, "reason": "verification failed", "confidence": "low"}
    except Exception as e:
        print(f"POI verification error: {e}")
        return {"matches": True, "reason": "verification failed", "confidence": "low"}


def _validate_stops_within_scope(poi_list, scope_name, headers, max_check=12):
    """
    PHASE 5.6 — Geographic-scope containment guard.

    Runs when the request is bounded to a tight named place (BUILDING/DISTRICT scope)
    but no museum venue_name was detected, so PHASE 5.5b did not fire.
    Verifies every generated stop is actually inside scope_name and removes
    famous-but-out-of-scope landmarks (e.g. "Walden Pond" for a "Robbins House" request).

    Checks EVERY stop (no institution-marker pre-filter), because out-of-scope
    landmarks usually have no institutional marker in their names.
    Stop 0 is kept unconditionally (graceful degradation). Original order preserved.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not poi_list or not scope_name:
        return poi_list

    def _check_one(poi):
        name = poi.get('name', '')
        desc = (poi.get('description', '') or '')[:400]
        prompt = (
            f"You are a geography fact-checker for location tours.\n"
            f"The tour must stay strictly within: '{scope_name}'.\n"
            f"Stop name: '{name}'\n"
            f"Description snippet:\n{desc}\n\n"
            f"Question: Is this stop physically located INSIDE or within the bounds of "
            f"'{scope_name}'? A stop that is in the same town but OUTSIDE '{scope_name}' "
            f"is NOT inside.\n"
            "Respond ONLY with valid JSON:\n"
            '{"inside_scope": true/false, "confidence": "high/medium/low", "reason": "<brief>"}'
        )
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a geography fact-checker. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 60,
        }
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions",
                                headers=headers, data=json.dumps(data))
            if resp.status_code != 200:
                return poi, True, "low", f"API error {resp.status_code} - keeping"
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            return (poi, parsed.get("inside_scope", True),
                    parsed.get("confidence", "low"), parsed.get("reason", ""))
        except Exception as e:
            return poi, True, "low", f"check error: {e}"

    first_stop = poi_list[0]
    candidates = poi_list[1:1 + max_check]
    tail = poi_list[1 + max_check:]

    survivors = []
    if candidates:
        with ThreadPoolExecutor(max_workers=min(len(candidates), 5)) as ex:
            futures = {ex.submit(_check_one, p): p for p in candidates}
            results = [f.result() for f in as_completed(futures)]
        results.sort(key=lambda x: candidates.index(x[0]))
        for poi, inside, conf, reason in results:
            if inside or conf == "low":
                survivors.append(poi)
                print(f"   OK '{poi['name']}' — inside '{scope_name}': {reason}")
            else:
                print(f"   X SCOPE-CHECK REMOVED '{poi['name']}' — outside '{scope_name}': {reason}")

    kept = [first_stop] + survivors + tail
    return kept


def _classify_tour_category(location, tour_type):
    """
    Detect the appropriate tour template based on location and tour_type.
    
    Returns: 'restaurant', 'walking', 'museum', or 'specialized'
    """
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()
    
    # EXPLICIT WALKING TOUR detection (highest priority — overrides everything)
    # If the user explicitly says "walking tour" in the location, honor that
    # even if a museum name appears as one of the stops
    explicit_walking_phrases = ['walking tour', 'walk tour', 'walking in', 'walk in']
    if any(phrase in location_lower for phrase in explicit_walking_phrases):
        return 'walking'
    
    # Restaurant/Food tour detection
    food_keywords = ['restaurant', 'food', 'dining', 'culinary', 'eat', 'cafe', 'bistro', 'eatery']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in food_keywords):
        return 'restaurant'
    
    # Museum indicators — check location first, then tour_type as fallback
    # Only check tour_type if location doesn't suggest a different category
    museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in museum_keywords):
        return 'museum'
    
    # Specialized tour indicators
    specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story', 'literary', 'filming']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in specialized_keywords):
        return 'specialized'
    
    # Walking tour indicators (default for cities, neighborhoods)
    walking_keywords = ['city', 'downtown', 'neighborhood', 'district', 'street', 'avenue', 'center', 'town']
    if any(keyword in location_lower for keyword in walking_keywords):
        return 'walking'
    
    # Default to walking tour
    return 'walking'



def _validate_museum_stop_descriptions(poi_list, venue_name, headers):
    """
    PHASE 5.5 — Post-description guard for single-venue museum tours.

    Cheap pre-filter first (zero API cost): stops whose name contains an
    institutional marker word but shares fewer than 2 words with venue_name
    are flagged as suspect and sent to OpenAI for confirmation.  Stops that
    don't look like external institutions pass through without an API call.

    Stop index 0 (the venue itself) is always kept unconditionally — this
    guarantees at least one correct stop even if everything else is removed.

    Returns the filtered poi_list (original order preserved).
    """
    if not poi_list:
        return poi_list

    _INSTITUTION_MARKERS = {
        'museum', 'gallery', 'institute', 'society',
        'foundation', 'university', 'college', 'library'
    }
    # Stop words excluded from overlap count so common words don't mask different institutions
    _OVERLAP_STOP_WORDS = {'the', 'of', 'and', 'in', 'at', 'a', 'an', 'for'}

    def _is_suspect(stop_name):
        """True if stop_name looks like a different institution than venue_name."""
        name_words = set(re.findall(r'[a-z]+', stop_name.lower()))
        if not (name_words & _INSTITUTION_MARKERS):
            return False  # no institutional marker — probably a room/exhibit
        # Exclude stop words AND the institutional marker itself from the overlap count
        # so that "Newton and Museum of History" doesn't share {and, museum} with
        # "Jackson Homestead and Museum" and slip through as non-suspect.
        name_content = name_words - _OVERLAP_STOP_WORDS - _INSTITUTION_MARKERS
        venue_content = set(re.findall(r'[a-z]+', venue_name.lower())) - _OVERLAP_STOP_WORDS - _INSTITUTION_MARKERS
        substantive_overlap = (name_content & venue_content) - _INSTITUTION_MARKERS
        return len(substantive_overlap) < 1  # < 1 shared substantive word — suspect

    def _check_one(poi):
        name = poi.get('name', '')
        description = poi.get('description', '') or ''
        snippet = description[:600]
        prompt = (
            f"You are a fact-checker for museum audio tours.\n"
            f"The tour is for the venue: '{venue_name}'.\n"
            f"Stop name: '{name}'\n"
            f"Description snippet:\n{snippet}\n\n"
            f"Question: Does this description refer to content (a room, gallery, exhibit, "
            f"collection, or area) that is physically located INSIDE '{venue_name}'?\n"
            f"Or does it describe a DIFFERENT institution or a fabricated/non-existent exhibit?\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"inside_venue": true/false, "confidence": "high/medium/low", "reason": "<brief>"}'
        )
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a fact-checker. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 60,
        }
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(data),
            )
            if resp.status_code != 200:
                return poi, True, "low", f"API error {resp.status_code} — keeping stop"
            result = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(result)
            return poi, parsed.get("inside_venue", True), parsed.get("confidence", "low"), parsed.get("reason", "")
        except Exception as e:
            return poi, True, "low", f"check error: {e}"

    # Stop 0 is always the venue itself — keep unconditionally (guarantees graceful degradation)
    first_stop = poi_list[0]
    candidates = poi_list[1:]  # only check stops 1..N

    # Single-venue museum tours: verify EVERY stop's description is inside the venue.
    # The name-only pre-filter (_is_suspect) missed exhibits that belong to a DIFFERENT
    # museum but whose names contain no institutional marker (e.g. "Thoreau's Bedroom"
    # is housed at the Concord Museum, not The Old Manse).
    # Cost is tiny: typical 3-7 stops × 1 gpt-3.5-turbo call each.
    if len(candidates) <= 12:
        suspect = list(candidates)
        clean = []
    else:
        # Fallback to name-based pre-filter only for unusually large tours (cost guard)
        suspect = [p for p in candidates if _is_suspect(p.get('name', ''))]
        clean = [p for p in candidates if not _is_suspect(p.get('name', ''))]
    print(f"   Pre-filter: {len(clean)} clean, {len(suspect)} suspect (will call OpenAI for suspect only)")

    # Run OpenAI checks only on suspect stops (parallel)
    checked_survivors = []
    if suspect:
        with ThreadPoolExecutor(max_workers=min(len(suspect), 5)) as executor:
            futures = {executor.submit(_check_one, poi): poi for poi in suspect}
            results = [future.result() for future in as_completed(futures)]
        results.sort(key=lambda x: suspect.index(x[0]))
        for poi, inside_venue, confidence, reason in results:
            if inside_venue or confidence == "low":
                status = "OK" if inside_venue else "OK (low-confidence, keeping)"
                print(f"   {status} '{poi['name']}' — {reason}")
                checked_survivors.append(poi)
            else:
                print(f"   X  REMOVED '{poi['name']}' — not inside venue: {reason}")

    # Reassemble in original order: stop 0 always first, then clean + checked survivors
    all_survivors = clean + checked_survivors
    all_survivors.sort(key=lambda p: poi_list.index(p))
    return [first_stop] + all_survivors


from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Module-level: populated on unresolvable clean-fail for structured error response
_LAST_CLEAN_FAIL_EVIDENCE = {}



@dataclass
class VerificationResult:
    """Result of _verify_works_v2 with tier computation for degradation ladder.
    
    Tiers (computed from positive evidence only, fail-closed):
    - rich: >=8 verified works + site corpus found -> full found-mode
    - medium: 3-7 verified works -> verified stops + interpretive narrative (invented mode)
    - thin: 1-2 verified works + Wikipedia available -> fewer honest stops, no fabricated names
    - unresolvable: 0 verified works or entity resolution failed -> clean fail
    """
    pois: List[Dict[str, Any]]
    evidence_log: Dict[str, Any]
    combined_text: str
    corpus_result: Dict[str, Any]
    tier: str  # 'rich', 'medium', 'thin', 'unresolvable' — NO DEFAULT, always explicit
    sparql_count: int = 0
    site_reachable: bool = False
    wiki_available: bool = False
    entity_resolved: bool = False
    qid: str = ''


def _verify_works_v2(poi_list, venue_name):
    """[D1 v2] In-collection verification using story_miner canonical title matching.
    
    Uses venue_resolver for entity resolution (Generic Grounding Step 0+1) and
    story_miner for canonical title matching (T0a) and story corpus.
    
    Sources for canonical titles (union, per LEAD amendment #1):
    - SPARQL works query (P195/P276) — highest precision
    - Official site extraction (from P856)
    - Wikipedia extraction (EN + local language)
    
    Returns (verified_pois, evidence_log, venue_corpus, story_corpus_result) or None.
    """
    try:
        from story_miner import (
            fetch_venue_narrative_corpus,
            match_candidate_to_canonical,
            check_stop_disjointness,
        )
    except ImportError:
        print("  [D1v2] story_miner not available — verification cannot proceed")
        return None  # Caller handles clean-fail

    # --- Generic Grounding: resolve venue via Wikidata ---
    _base_site_url = ""
    _wiki_title = ""
    _language = "en"
    _venue_entity = None
    
    try:
        from venue_resolver import resolve_venue, fetch_venue_works, build_canonical_titles_from_works
        
        # Parse city from venue_name (heuristic: last comma-separated segment)
        _city = ""
        _venue_search = venue_name  # The search term for Wikidata
        if "," in venue_name:
            parts = [p.strip() for p in venue_name.split(",")]
            # City is typically second-to-last (before country)
            if len(parts) >= 3:
                _city = parts[1]
                _venue_search = parts[0]  # Just the museum name
            elif len(parts) == 2:
                _city = parts[1]
                _venue_search = parts[0]
        
        _venue_entity = resolve_venue(_venue_search, _city)
        
        if _venue_entity:
            _base_site_url = _venue_entity.official_url
            _language = _venue_entity.language
            # Build Wikipedia title from entity name
            _wiki_title = _venue_entity.name
            print(f"  [D1v2] Venue resolved: {_venue_entity.qid} → URL={_base_site_url}, lang={_language}")
        else:
            print(f"  [D1v2] Venue resolver returned None — falling back to heuristic")
    except ImportError:
        print("  [D1v2] venue_resolver not available — using heuristic fallback")
    except Exception as e:
        print(f"  [D1v2] venue_resolver error: {e} — using heuristic fallback")
    
    # Fallback: if venue resolver didn't provide a site URL and we have nothing,
    # the degradation ladder will handle fewer verified stops. No hardcoded URLs.
    if not _base_site_url:
        print(f"  [D1v2] No official site discovered — will rely on Wikipedia + SPARQL")
    
    if not _wiki_title:
        _wiki_title = venue_name.replace("Musee", "Musée").replace("National ", "")
    
    # Wikipedia variants for fallback
    _wiki_variants = [_wiki_title]
    if _venue_entity and _venue_entity.language == "fr":
        _wiki_variants.append(f"{_wiki_title} (Nice)" if "nice" in venue_name.lower() else _wiki_title)
    elif "matisse" in venue_name.lower():
        _wiki_variants.append("Musée Matisse (Nice)")

    # --- CACHE CHECK: try venue_corpus cache before mining ---
    _cache_hit = None
    if _venue_entity and _venue_entity.qid:
        try:
            from venue_resolver import cache_get
            _cache_hit = cache_get(_venue_entity.qid)
        except Exception as e:
            print(f"  [D1v2] Cache check failed (proceeding with fresh mining): {e}")
    
    if _cache_hit:
        # Cache hit — use cached corpus directly
        canonical_titles = _cache_hit['canonical_titles']
        sparql_works = _cache_hit.get('sparql_works') or []
        sparql_titles = set(build_canonical_titles_from_works(sparql_works)) if sparql_works else set()
        combined_text = ''  # Will be re-fetched if needed below
        corpus_result = {
            'canonical_titles': canonical_titles,
            'combined_text': _cache_hit.get('pages', {}).get('combined_text', '') if isinstance(_cache_hit.get('pages'), dict) else '',
            'pages': _cache_hit.get('pages') or [],
            'cycle_names': set(),
            'theme_words': set(),
            'source_urls': [],
        }
        combined_text = corpus_result['combined_text']
        cycle_names = corpus_result['cycle_names']
        print(f"  [D1v2] Cache HIT: {len(canonical_titles)} canonical titles (tier={_cache_hit['tier']})")
    else:
        # Cache miss — fresh mining (existing code below)
        pass

    # --- SPARQL works (source 1 of 3 for canonical titles) ---
    sparql_titles = set() if not _cache_hit else sparql_titles
    sparql_works = [] if not _cache_hit else sparql_works
    if _venue_entity and _venue_entity.qid and not _cache_hit:
        try:
            sparql_works = fetch_venue_works(_venue_entity.qid, _language)
            sparql_titles = build_canonical_titles_from_works(sparql_works)
            print(f"  [D1v2] SPARQL source: {len(sparql_titles)} canonical titles")
        except Exception as e:
            print(f"  [D1v2] SPARQL query failed (degrading, not fabricating): {e}")

    # --- Fetch the expanded narrative corpus (sources 2+3: official site + Wikipedia) ---
    if not _cache_hit:
        corpus_result = fetch_venue_narrative_corpus(
            venue_name=venue_name,
            base_site_url=_base_site_url,
            wikipedia_title=_wiki_title,
            language=_language,
        )
    
    # If no pages fetched, try variants (skip on cache hit — already have data)
    if not _cache_hit:
        if not corpus_result.get('pages') or len(corpus_result.get('combined_text', '')) < 500:
            for variant in _wiki_variants[1:]:
                _alt = fetch_venue_narrative_corpus(
                    venue_name=venue_name,
                    base_site_url=_base_site_url,
                    wikipedia_title=variant,
                    language=_language,
                )
                if _alt.get('combined_text', '') and len(_alt['combined_text']) > len(corpus_result.get('combined_text', '')):
                    corpus_result = _alt
                    break

        # --- Union canonical titles (LEAD amendment #1): SPARQL + site + wiki extraction ---
        site_wiki_titles = corpus_result['canonical_titles']
        canonical_titles = site_wiki_titles | sparql_titles
        cycle_names = corpus_result['cycle_names']
        combined_text = corpus_result['combined_text']
    
    if not _cache_hit:
        print(f"  [D1v2] Canonical titles union: {len(site_wiki_titles)} site/wiki + {len(sparql_titles)} SPARQL = {len(canonical_titles)} total")
    
    # Remove site-extracted titles that are substrings of longer SPARQL titles
    # (prevents truncated site extractions from polluting the canonical set)
    # Uses normalized comparison (accent-stripped, punctuation-stripped) for matching
    from story_miner import _normalize as _norm_for_dedup
    _to_remove = set()
    _norm_map = {t: _norm_for_dedup(t) for t in canonical_titles}
    for t in canonical_titles:
        _nt = _norm_map[t]
        for other in canonical_titles:
            if t != other:
                _no = _norm_map[other]
                if len(_nt) < len(_no) and _nt in _no:
                    _to_remove.add(t)
                    break
    if _to_remove:
        canonical_titles -= _to_remove
        print(f"  [D1v2] Removed {len(_to_remove)} substring titles (prefer longer forms)")

    if not canonical_titles:
        print(f"  [D1v2] No canonical titles discovered — tier: unresolvable")
        _has_site = len(corpus_result.get('combined_text', '')) > 1000 if 'corpus_result' in dir() and corpus_result else False
        _has_wiki = bool(corpus_result.get('pages')) if 'corpus_result' in dir() and corpus_result else False
        return VerificationResult(
            pois=[], evidence_log={}, combined_text='',
            corpus_result=corpus_result if 'corpus_result' in dir() and corpus_result else {},
            tier='unresolvable',
            sparql_count=len(sparql_works),
            site_reachable=_has_site, wiki_available=_has_wiki,
            entity_resolved=bool(_venue_entity and _venue_entity.qid),
            qid=_venue_entity.qid if (_venue_entity and _venue_entity.qid) else '',
        )

    # Verify each candidate against canonical titles
    evidence_log = {}
    verified_pois = []
    _verified_qids = set()  # [A6] Track QIDs to prevent duplicate stops (same work, different labels)
    
    # Build title→QID lookup from SPARQL works for deduplication
    _title_to_qid = {}
    for work in sparql_works:
        qid = work.get('qid', '')
        if not qid:
            continue
        for label_key in ('label_en', 'label_local'):
            lbl = work.get(label_key, '')
            if lbl:
                from story_miner import _normalize as _norm_title
                _title_to_qid[_norm_title(lbl)] = qid
        for alias in work.get('aliases', []):
            if alias:
                _title_to_qid[_norm_title(alias)] = qid
    
    # Inject dynamic aliases from SPARQL works (replaces hardcoded CANONICAL_ALIASES)
    if sparql_works:
        try:
            from venue_resolver import build_dynamic_aliases
            import story_miner as _sm
            _sm.CANONICAL_ALIASES = build_dynamic_aliases(sparql_works)
            print(f"  [D1v2] Injected {len(_sm.CANONICAL_ALIASES)} dynamic aliases")
            # Build bilingual word map from SPARQL label pairs (generic, works for any language)
            _sm.build_bilingual_map_from_sparql(sparql_works)
            print(f"  [D1v2] Built bilingual map: {len(_sm._BILINGUAL_MAP)} word pairs")
        except Exception as e:
            print(f"  [D1v2] Dynamic alias build failed: {e}")
    
    # Also check for rejection using artist article (same logic as before)
    from rag_retriever import fetch_wikipedia_summary
    import re as _d1v2_re
    
    # Extract artist name for rejection checks
    _cleaned = _d1v2_re.sub(
        r"(?i)(mus[ée]+e?|museum|gallery|national|the|of|art|centre|center)\s*",
        " ", venue_name
    ).strip()
    _venue_artist = " ".join(w for w in _cleaned.split() if w and len(w) > 1).strip()
    artist_article = ""
    if _venue_artist:
        artist_article = fetch_wikipedia_summary(_venue_artist)

    _rejection_indicators = ['hadassah', 'jerusalem', 'metropolitan opera',
                             'new york', 'pompidou', 'louvre', 'hermitage',
                             'uffizi', 'tate', 'prado', 'moma', 'guggenheim']

    for poi in poi_list:
        work_name = poi.get('name', '')
        
        # Step 1: Try canonical title match
        match = match_candidate_to_canonical(work_name, canonical_titles, combined_text)
        if match:
            canonical_title, snippet = match
            
            # [A6] QID-based dedup: if this canonical title maps to a QID we already have, skip
            from story_miner import _normalize as _norm_check
            _matched_qid = _title_to_qid.get(_norm_check(canonical_title), '')
            if _matched_qid and _matched_qid in _verified_qids:
                print(f"  [D1v2] DEDUP '{work_name}' → same QID as already-verified work ({_matched_qid})")
                evidence_log[work_name] = {"status": "DROPPED", "reason": f"duplicate QID {_matched_qid}"}
                continue
            
            if _matched_qid:
                _verified_qids.add(_matched_qid)
            
            print(f"  [D1v2] VERIFIED '{work_name}' → canonical: '{canonical_title}'")
            evidence_log[work_name] = {
                "status": "VERIFIED",
                "canonical_title": canonical_title,
                "snippet": snippet,
                "method": "canonical_title_match",
                "qid": _matched_qid,
            }
            # Use the EXACT canonical title as the stop name (prevents GPT truncation)
            # If the matched canonical is a substring of a longer SPARQL title, prefer the SPARQL form
            poi = dict(poi)  # Don't mutate the original
            _best_title = canonical_title
            if sparql_titles:
                from story_miner import _normalize as _nt_check
                _norm_ct = _nt_check(canonical_title)
                for st in sparql_titles:
                    _norm_st = _nt_check(st)
                    if _norm_ct != _norm_st and _norm_ct in _norm_st:
                        _best_title = st  # Use the longer SPARQL form
                        break
            # Ensure title starts with uppercase (Wikidata sometimes stores lowercase)
            if _best_title and _best_title[0].islower():
                _best_title = _best_title[0].upper() + _best_title[1:]
            poi['name'] = _best_title
            verified_pois.append(poi)
            continue
        
        # Step 2: Check if it's a theme word / cycle name (should not be a stop)
        _work_lower = work_name.lower()
        if any(tw in _work_lower for tw in corpus_result['theme_words']):
            print(f"  [D1v2] DROPPED '{work_name}' — theme/book word, not a work title")
            evidence_log[work_name] = {"status": "DROPPED", "reason": "theme word"}
            continue
        if any(cn.lower() in _work_lower or _work_lower in cn.lower() 
               for cn in cycle_names):
            print(f"  [D1v2] DROPPED '{work_name}' — cycle/collection name (prolog material)")
            evidence_log[work_name] = {"status": "DROPPED", "reason": "cycle name"}
            continue
        
        # Step 3: Rejection check using artist article
        if artist_article:
            _artist_lower = artist_article.lower()
            _rejected = False
            for _other in _rejection_indicators:
                if _other in _artist_lower and _other not in venue_name.lower():
                    # Check if this work name + other venue are in proximity
                    from story_miner import _normalize
                    _norm_work = _normalize(work_name)
                    _work_pos = _artist_lower.find(_norm_work[:8]) if _norm_work else -1
                    if _work_pos >= 0:
                        _context = _artist_lower[max(0, _work_pos-200):_work_pos+200]
                        if _other in _context:
                            print(f"  [D1v2] REJECTED '{work_name}' — artist article places near '{_other}'")
                            evidence_log[work_name] = {"status": "REJECTED", "reason": f"located at {_other}"}
                            _rejected = True
                            break
            if _rejected:
                continue
        
        # Step 4: No match — DROPPED
        print(f"  [D1v2] DROPPED '{work_name}' — no canonical title match")
        evidence_log[work_name] = {"status": "DROPPED", "reason": "no canonical match"}

    # Degradation ladder: compute tier based on verified count
    # 0 verified = unresolvable, 1-2 = thin, 3-7 = medium, 8+ = rich
    # For thin tier (1-2 works): return them — caller decides behavior
    if len(verified_pois) == 0:
        print(f"  [D1v2] 0 works verified — tier: unresolvable")
        _has_site = len(corpus_result.get('combined_text', '')) > 1000
        _has_wiki = bool(corpus_result.get('pages'))
        return VerificationResult(
            pois=[], evidence_log=evidence_log, combined_text=combined_text,
            corpus_result=corpus_result, tier='unresolvable',
            sparql_count=len(sparql_works),
            site_reachable=_has_site, wiki_available=_has_wiki,
            entity_resolved=bool(_venue_entity and _venue_entity.qid),
            qid=_venue_entity.qid if (_venue_entity and _venue_entity.qid) else '',
        )

    # [A6+] Normalized-title dedup: site-extracted titles carry no QID, so QID-dedup alone
    # cannot catch a site-title and SPARQL-title of the same work. Use the same normalization
    # that D3(e) uses (lowercase, strip accents, strip punctuation, collapse whitespace).
    import unicodedata as _ud_dedup
    def _normalize_for_title_dedup(title):
        _nfkd = _ud_dedup.normalize('NFKD', title.lower())
        _norm = ''.join(c for c in _nfkd if not _ud_dedup.combining(c))
        _norm = re.sub(r'[^\w\s]', ' ', _norm).strip()
        return ' '.join(_norm.split())

    _verified_normalized_titles = set()
    _deduped_pois = []
    for _vp in verified_pois:
        _vp_norm = _normalize_for_title_dedup(_vp.get('name', ''))
        if _vp_norm in _verified_normalized_titles:
            print(f"  [D1v2] TITLE-DEDUP dropped '{_vp.get('name', '')[:50]}' (normalized duplicate)")
            evidence_log[_vp.get('name', '')] = {"status": "DROPPED", "reason": "normalized title duplicate"}
            continue
        _verified_normalized_titles.add(_vp_norm)
        _deduped_pois.append(_vp)
    
    if len(_deduped_pois) < len(verified_pois):
        print(f"  [D1v2] Title-dedup removed {len(verified_pois) - len(_deduped_pois)} duplicate(s): {len(_deduped_pois)} remain")
    verified_pois = _deduped_pois

    if len(verified_pois) < 3 and len(verified_pois) == 0:
        print(f"  [D1v2] After title-dedup: 0 verified — unresolvable")
        _has_site_corpus = len(corpus_result.get('combined_text', '')) > 1000
        _has_wiki = bool(corpus_result.get('pages'))
        return VerificationResult(
            pois=[], evidence_log=evidence_log, combined_text=combined_text,
            corpus_result=corpus_result, tier='unresolvable',
            sparql_count=len(sparql_works) if 'sparql_works' in dir() else 0,
            site_reachable=_has_site_corpus, wiki_available=_has_wiki,
            entity_resolved=bool(_venue_entity and _venue_entity.qid) if '_venue_entity' in dir() else False,
            qid=_venue_entity.qid if ('_venue_entity' in dir() and _venue_entity and _venue_entity.qid) else '',
        )

    # --- Tier computation (fail-closed: only positive evidence promotes) ---
    # B8: evidence_strength = unique QID count from SPARQL works (not label count)
    # This prevents bilingual label inflation (e.g., Roi David + King David = 1 QID, not 2)
    _has_site_corpus = len(corpus_result.get('combined_text', '')) > 1000
    _has_wiki = bool(corpus_result.get('pages'))
    _n_verified = len(verified_pois)
    
    # Count unique QIDs from SPARQL works (the definitive evidence measure)
    _unique_sparql_qids = set(w.get('qid', '') for w in sparql_works if w.get('qid')) if 'sparql_works' in dir() and sparql_works else set()
    _evidence_strength = len(_unique_sparql_qids)
    
    _tier = compute_tier(_n_verified, _evidence_strength)
    
    print(f"  [D1v2] {_n_verified}/{len(poi_list)} works verified — tier: {_tier}")
    
    # --- CACHE WRITE: store results for future requests ---
    if _venue_entity and _venue_entity.qid and not _cache_hit:
        try:
            from venue_resolver import cache_put
            cache_put(
                qid=_venue_entity.qid,
                venue_name=venue_name,
                official_url=_base_site_url or '',
                canonical_titles=canonical_titles,
                story_elements=corpus_result.get('story_elements'),
                sparql_works=sparql_works,
                pages=corpus_result.get('pages'),
                language=_language,
                tier=_tier,
            )
        except Exception as e:
            print(f"  [D1v2] Cache write failed (non-fatal): {e}")
    
    return VerificationResult(
        pois=verified_pois,
        evidence_log=evidence_log,
        combined_text=combined_text,
        corpus_result=corpus_result,
        tier=_tier,
        sparql_count=_evidence_strength,
        site_reachable=_has_site_corpus,
        wiki_available=_has_wiki,
        entity_resolved=bool(_venue_entity and _venue_entity.qid) if '_venue_entity' in dir() else False,
        qid=_venue_entity.qid if ('_venue_entity' in dir() and _venue_entity and _venue_entity.qid) else '',
    )


def _verify_works_in_collection(poi_list, venue_name):
    """[D1] In-collection verification gate for museum tours.
    
    Verifies candidate works belong in the specified venue using multi-source lookup:
    1. Venue article (try multiple name variations) — VERIFICATION source
    2. Museum official site — VERIFICATION source
    3. Artist's main article — REJECTION only (names works at OTHER venues)
    4. Reverse lookup per work — VERIFICATION if mentions venue/city, REJECTION if elsewhere
    
    Matching: normalized token-overlap >=60% of content words.
    Returns filtered poi_list, or None if <4 verify or all fetches fail.
    """
    from rag_retriever import fetch_wikipedia_summary
    import re as _d1_re
    import unicodedata

    def _normalize_for_match(text):
        """Normalize text for token matching: lowercase, strip accents, remove articles/years."""
        if not text:
            return ""
        # Decompose unicode and strip accent marks
        nfkd = unicodedata.normalize('NFKD', text.lower())
        stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
        # Remove leading "the", parenthetical years, punctuation
        stripped = _d1_re.sub(r'^the\s+', '', stripped)
        stripped = _d1_re.sub(r'\s*\([^)]*\d{4}[^)]*\)', '', stripped)
        stripped = _d1_re.sub(r'[^\w\s]', ' ', stripped)
        return ' '.join(stripped.split())

    def _content_tokens(text):
        """Extract content words (>=3 chars, not stopwords) for overlap matching."""
        _STOP = {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
                 'his', 'her', 'has', 'had', 'its', 'who', 'which', 'their', 'about',
                 'one', 'two', 'three', 'not', 'but', 'all', 'can', 'will', 'been'}
        words = _normalize_for_match(text).split()
        return [w for w in words if len(w) >= 3 and w not in _STOP]

    def _token_overlap(work_name, corpus_text):
        """Check if >=60% of work name's content tokens appear in corpus text.
        Also handles French/inflected variants by checking 4+ char prefix matches."""
        work_tokens = _content_tokens(work_name)
        if not work_tokens:
            return False, 0.0
        corpus_norm = _normalize_for_match(corpus_text)
        corpus_words = set(corpus_norm.split())
        
        matched = 0
        for token in work_tokens:
            if token in corpus_norm:
                matched += 1
            elif len(token) >= 5:
                # Try prefix matching for inflected forms (startswith, not substring)
                _prefix = token[:5]
                if any(word.startswith(_prefix) for word in corpus_words if len(word) >= 5):
                    matched += 1
        
        overlap = matched / len(work_tokens) if work_tokens else 0.0
        return overlap >= 0.60, overlap

    # Extract artist name from venue
    cleaned = _d1_re.sub(
        r"(?i)(mus[ée]+e?|museum|gallery|national|the|of|art|centre|center)\s*",
        " ", venue_name
    ).strip()
    _venue_artist = " ".join(w for w in cleaned.split() if w and len(w) > 1).strip()

    # --- SOURCE 1: Venue Wikipedia article (multiple name variations) ---
    _venue_variations = [
        venue_name,
        venue_name.replace("National ", ""),
        # Accented variants (Wikipedia action API is accent-sensitive)
        venue_name.replace("Musee", "Musée"),
        venue_name.replace("Musee National", "Musée").replace("National ", ""),
        f"Musée Marc Chagall" if "chagall" in venue_name.lower() else "",
        f"{_venue_artist} Museum" if _venue_artist else "",
        f"Musee {_venue_artist}" if _venue_artist else "",
        f"Musée national {_venue_artist}",
        f"Musée national Marc-Chagall" if "chagall" in venue_name.lower() else "",
    ]
    venue_article = ""
    _best_venue_article = ""
    for _var in _venue_variations:
        if not _var:
            continue
        _candidate = fetch_wikipedia_summary(_var)
        if _candidate and len(_candidate) > 100:
            # Validate: the article should be about THIS venue (check for Nice/France/the actual venue name)
            _cand_lower = _candidate[:2000].lower()
            _is_right_venue = (
                'nice' in _cand_lower or 
                'france' in _cand_lower or
                venue_name.lower()[:15] in _cand_lower or
                'alpes-maritimes' in _cand_lower
            )
            if _is_right_venue:
                if len(_candidate) > len(_best_venue_article):
                    _best_venue_article = _candidate
                    print(f"  [D1] Venue article candidate via: '{_var}' ({len(_candidate)} chars)")
                # If we found a substantial article (>500 chars), stop searching
                if len(_best_venue_article) > 500:
                    break
            else:
                print(f"  [D1] Skipped '{_var}' ({len(_candidate)} chars) — wrong venue (not Nice/France)")
    venue_article = _best_venue_article
    if venue_article:
        print(f"  [D1] Venue article selected: {len(venue_article)} chars")
    
    # If no validated venue article, note it
    if not venue_article:
        print(f"  [D1] No venue article found for Nice/France — using museum site only")
    
    # --- SOURCE 2: Museum's official collection page ---
    _museum_site_content = ""
    try:
        import requests as _d1_req
        from html.parser import HTMLParser
        
        class _TextExtractor(HTMLParser):
            """Extract visible text from HTML, ignoring scripts/styles."""
            def __init__(self):
                super().__init__()
                self._text = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style', 'noscript'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script', 'style', 'noscript'):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    self._text.append(data)
            def get_text(self):
                return ' '.join(self._text)
        
        _site_urls = []
        if "chagall" in venue_name.lower():
            _site_urls.append("https://musees-nationaux-alpesmaritimes.fr/chagall/en/collection")
        for _url in _site_urls:
            try:
                _site_resp = _d1_req.get(_url, headers={'User-Agent': 'Audioura/2.2'}, timeout=8)
                if _site_resp.status_code == 200 and len(_site_resp.text) > 500:
                    # Extract plain text from HTML for better matching
                    _extractor = _TextExtractor()
                    _extractor.feed(_site_resp.text)
                    _museum_site_content = _extractor.get_text()[:30000]
                    print(f"  [D1] Museum site fetched: {_url} ({len(_museum_site_content)} chars text)")
                    break
            except Exception:
                continue
    except Exception:
        pass

    # --- SOURCE 3: Artist article (REJECTION ONLY — names works at other venues) ---
    artist_article = ""
    if _venue_artist:
        artist_article = fetch_wikipedia_summary(_venue_artist)
        if artist_article:
            print(f"  [D1] Artist article fetched: '{_venue_artist}' ({len(artist_article)} chars)")

    _all_fetches_failed = not venue_article and not artist_article and not _museum_site_content
    
    # Build VENUE-LINKED corpus: venue article + museum site (NOT artist article)
    # Artist article is used for REJECTION only, never for verification
    # Keep original case — _token_overlap normalizes internally
    _venue_corpus = venue_article + " " + _museum_site_content

    # Extract city from venue article for reverse-lookup verification
    _venue_city = ""
    if venue_article:
        _city_match = _d1_re.search(r'\bin\s+([A-Z][a-zé]+(?:\s+[A-Z][a-zé]+)?)', venue_article)
        if _city_match:
            _venue_city = _city_match.group(1)
    if not _venue_city and ',' in venue_name:
        _venue_city = venue_name.split(',')[-1].strip().split()[0] if venue_name.split(',')[-1].strip() else ""
    if _venue_city:
        print(f"  [D1] Venue city: '{_venue_city}'")

    # Evidence log for D3 grounding assertion
    _evidence_log = {}
    
    # Rejection indicators: venues that indicate a work is NOT at our target museum
    _rejection_indicators = ['hadassah', 'jerusalem', 'metropolitan opera',
                             'new york', 'pompidou', 'louvre', 'hermitage',
                             'uffizi', 'tate', 'prado', 'moma', 'guggenheim']
    
    verified_pois = []
    for poi in poi_list:
        work_name = poi.get('name', '')
        _norm_name = _normalize_for_match(work_name)

        # --- CHECK 1: Token-overlap in VENUE-LINKED corpus (venue article + museum site) ---
        if _venue_corpus and _norm_name and len(_norm_name) > 3:
            overlaps, pct = _token_overlap(work_name, _venue_corpus)
            if overlaps:
                print(f"  [D1] VERIFIED '{work_name}' via venue corpus (token overlap {pct:.0%})")
                _evidence_log[work_name] = f"venue corpus overlap {pct:.0%}"
                verified_pois.append(poi)
                continue
            # Also check exact normalized name substring match
            if _norm_name in _normalize_for_match(_venue_corpus):
                print(f"  [D1] VERIFIED '{work_name}' via venue corpus (exact substring)")
                _evidence_log[work_name] = "venue corpus exact substring"
                verified_pois.append(poi)
                continue

        # --- CHECK 2: Reverse lookup — fetch work's own article ---
        _lookup_query = f"{work_name} {_venue_artist}" if _venue_artist else work_name
        work_article = fetch_wikipedia_summary(_lookup_query)
        if work_article:
            _all_fetches_failed = False
            _work_lower = work_article.lower()

            # REJECTION: article places work at a DIFFERENT venue/city
            _rejected = False
            for _other in _rejection_indicators:
                if _other in _work_lower and _other not in venue_name.lower():
                    if _d1_re.search(rf'(located|housed|installed|displayed|held|collection|synagogue|opera|commission)\s*.{{0,40}}{_other}', _work_lower):
                        print(f"  [D1] REJECTED '{work_name}' — located elsewhere ({_other})")
                        _evidence_log[work_name] = f"REJECTED: located at {_other}"
                        _rejected = True
                        break
            if _rejected:
                continue

            # VERIFICATION: work article mentions the venue or city
            _venue_lower = venue_name.lower()[:15]
            if _venue_lower in _work_lower or (_venue_city and _venue_city.lower() in _work_lower):
                print(f"  [D1] VERIFIED '{work_name}' via reverse lookup (mentions venue/city)")
                _evidence_log[work_name] = "reverse lookup: mentions venue/city"
                verified_pois.append(poi)
                continue

            # Work article exists but doesn't mention this venue — DROPPED
            print(f"  [D1] DROPPED '{work_name}' — article found but no venue/city link")
            _evidence_log[work_name] = "DROPPED: no venue link in article"
            continue
        else:
            # No article found — check if venue corpus has partial evidence
            # Require at least 2 long (5+ char) words from the name in corpus for confidence
            _corpus_lower = _venue_corpus.lower() if _venue_corpus else ""
            if _corpus_lower and _norm_name:
                _long_words = [w for w in _content_tokens(work_name) if len(w) >= 5]
                if len(_long_words) >= 2:
                    _matches = [w for w in _long_words if w in _corpus_lower]
                    if len(_matches) >= 2:
                        print(f"  [D1] VERIFIED '{work_name}' via venue corpus (multi-word match: {_matches})")
                        _evidence_log[work_name] = f"venue corpus multi-word match: {_matches}"
                        verified_pois.append(poi)
                        continue
                elif len(_long_words) == 1 and _long_words[0] in _corpus_lower:
                    # Single long word — only verify if the word is very specific (>7 chars)
                    if len(_long_words[0]) >= 7:
                        print(f"  [D1] VERIFIED '{work_name}' via venue corpus (specific word: {_long_words[0]})")
                        _evidence_log[work_name] = f"venue corpus specific word: {_long_words[0]}"
                        verified_pois.append(poi)
                        continue
            
            # --- CHECK 3: Artist article as REJECTION-ONLY source ---
            # If the artist article explicitly places this work elsewhere, reject it
            _rejected = False
            if artist_article:
                _artist_lower = artist_article.lower()
                _norm_tokens = _content_tokens(work_name)
                # Only check if the work name appears in artist article at all
                _name_in_artist = _norm_name in _artist_lower or (
                    _norm_tokens and all(t in _artist_lower for t in _norm_tokens if len(t) >= 4)
                )
                if _name_in_artist:
                    # Found in artist article — check if it's placed elsewhere
                    for _other in _rejection_indicators:
                        if _other in _artist_lower:
                            # Find if the work name and the other-venue are in proximity
                            _work_pos = _artist_lower.find(_norm_name[:10]) if _norm_name else -1
                            if _work_pos >= 0:
                                _context = _artist_lower[max(0, _work_pos-200):_work_pos+200]
                                if _other in _context and _other not in venue_name.lower():
                                    print(f"  [D1] REJECTED '{work_name}' — artist article places near '{_other}'")
                                    _evidence_log[work_name] = f"REJECTED: artist article context -> {_other}"
                                    _rejected = True
                                    break
            if _rejected:
                continue
            
            print(f"  [D1] DROPPED '{work_name}' — no evidence from any source")
            _evidence_log[work_name] = "DROPPED: no evidence"
            continue

    # All fetches failed → network error
    if _all_fetches_failed and len(poi_list) > 0:
        print(f"  [D1] All fetches failed — NETWORK ERROR (job will fail)")
        return None

    # Log evidence summary
    print(f"  [D1] Evidence log:")
    for work, evidence in _evidence_log.items():
        print(f"    {work}: {evidence}")

    # Fewer than 4 verified
    if len(verified_pois) < 4:
        print(f"  [D1] Only {len(verified_pois)} work(s) verified — need at least 4 (fail-closed)")
        return None

    print(f"  [D1] {len(verified_pois)}/{len(poi_list)} works verified for '{venue_name}'")
    return verified_pois, _evidence_log, _venue_corpus


def generate_tour_text(location, tour_type, output_file=None, total_stops=None, persona=None):
    """
    Generate audio tour text using OpenAI API with geo coordinates.
    
    Args:
        location: Location for the tour
        tour_type: Type of tour (e.g., "sculpture", "architecture")
        output_file: File to save the tour text (optional)
        total_stops: Number of stops requested
        persona: Optional persona string (e.g. "art_lover", "history_buff").
                 When STORIED_MODE=true and persona is provided, biases story-type
                 assignment and injects persona tone into descriptions.
                 When STORIED_MODE=false or persona=None: no effect.
    
    Returns:
        tuple: (tour_text, output_file, coordinates)
    """
    import api_call_logger

    # --- Storied: persona handling ---
    _storied_mode = os.environ.get("STORIED_MODE", "false").lower() == "true"
    _persona_enum = None
    _persona_tone = ""
    if _storied_mode and persona:
        try:
            from onboarding_preference import UserPersona, PERSONA_TONE_OVERRIDE
            _persona_enum = UserPersona(persona.strip().lower())
            _persona_tone = PERSONA_TONE_OVERRIDE.get(_persona_enum, "")
            print(f"  [Storied] Persona='{_persona_enum.value}' tone='{_persona_tone}'")
        except (ValueError, ImportError):
            # Unknown persona value or module not available — default gracefully
            try:
                from onboarding_preference import UserPersona, PERSONA_TONE_OVERRIDE
                from onboarding_preference import UserPersona as _UP
                _persona_enum = _UP.FIRST_TIME_VISITOR
                _persona_tone = PERSONA_TONE_OVERRIDE.get(_persona_enum, "")
                print(f"  [Storied] Unknown persona '{persona}' → defaulting to FIRST_TIME_VISITOR")
            except ImportError:
                print(f"  [Storied] onboarding_preference not available — persona skipped")
                _persona_enum = None
                _persona_tone = ""
    api_call_logger.log("GENERATE_TOUR_TEXT_FUNCTION_ENTRY", {
        "location": location,
        "tour_type": tour_type,
        "total_stops_parameter": total_stops,
        "output_file": output_file,
    })
    # Get API key from environment variable or prompt user (only if interactive)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Only prompt if running interactively (not from service)
        if __name__ == "__main__":
            api_key = input("Enter your OpenAI API key: ")
        if not api_key:
            print("Error: OpenAI API key is required")
            return None, None, (None, None)

    # Headers for API calls
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Get number of stops - only prompt if not provided
    if not total_stops:
        # Only prompt if running interactively (not from service)
        if __name__ == "__main__":
            total_stops = int(input("How many total stops would you like in the tour? (default: 10): ") or "10")
        else:
            total_stops = 10  # Default for service calls
    
    api_call_logger.log("TOTAL_STOPS_FINALIZED", {
        "location": location,
        "total_stops_final": total_stops,
        "source": "parameter" if total_stops else ("user_input" if __name__ == "__main__" else "service_default"),
    })
    
    # Track API costs
    total_tokens = 0
    total_cost = 0
    
    # -------- [S20] Storied: check tour cache before generation --------
    _cache_hit = None
    if _storied_mode:
        _db_url = os.environ.get("DATABASE_URL")
        if _db_url:
            try:
                from tour_cache_layer1 import get_cached_tour
                _cache_hit = get_cached_tour(location, tour_type, total_stops, _db_url)
                if _cache_hit:
                    print(f"CACHE HIT: {location} / {tour_type} / {total_stops}")
                    # Return cached tour immediately
                    if output_file:
                        with open(output_file, "w", encoding="utf-8") as _cf:
                            _cf.write(_cache_hit)
                    return _cache_hit, output_file, (None, None)
                else:
                    print(f"CACHE MISS: {location} / {tour_type} / {total_stops}")
            except ImportError:
                print(f"  [S20] tour_cache_layer1 not available — cache skipped")
            except Exception as e:
                print(f"  [S20] Cache check error: {e}")
        else:
            print(f"  [S20] DATABASE_URL not set — cache skipped")

    # PHASE 1: Analyze user intent with AI
    print(f"\nPHASE 1: Analyzing tour intent with AI...")
    # BUG 2 FIX: Mobile app hardcodes tour_type="museum" for ALL requests.
    # Check whether LOCATION ALONE encodes the real category (e.g. "restaurant tour
    # in Newton, MA"). If so, suppress the mobile-injected tour_type so GPT doesn't
    # return museum cafes instead of standalone restaurants.
    # Passing "" as tour_type ensures the category comes only from the location string,
    # not from the (potentially wrong) mobile-supplied tour_type.
    
    # [BLOCKER 1] Normalize: strip trailing "tour"/"tours" from location before analysis.
    # "Musée National Marc Chagall tour, Nice" → "Musée National Marc Chagall, Nice"
    # This prevents the model from reading "tour" as "a tour OF Nice" instead of
    # "a tour INSIDE the Chagall museum."
    _location_normalized = re.sub(r'\b[Tt]ours?\b', '', location).strip().strip(',').strip()
    if _location_normalized != location:
        print(f"  [BLOCKER1] Stripped 'tour' from location: '{location}' → '{_location_normalized}'")
    
    _pre_category = _classify_tour_category(_location_normalized, "")
    if _pre_category in ('restaurant', 'walking', 'specialized'):
        # Location string already encodes the real intent — don't prepend tour_type
        user_request = _location_normalized
        print(f"  [Bug2Fix] tour_type='{tour_type}' suppressed for intent analysis (pre_category='{_pre_category}'); using location only")
    else:
        user_request = f"{tour_type} {_location_normalized}"
    intent = analyze_tour_intent(user_request, api_key)
    
    if intent:
        print(f"✅ Intent Analysis Results:")
        print(f"   POI Type: {intent.get('poi_type')}")
        print(f"   Location: {intent.get('location')}")
        print(f"   Requirements: {intent.get('requirements')}")
        print(f"   Business Hours Relevant: {intent.get('business_hours_relevant')}")
        print(f"   Accessibility Mentioned: {intent.get('accessibility_mentioned')}")
        print(f"   Venue Name: {intent.get('venue_name')}")

        # Sanity-check venue_name: require word-overlap with prefix matching to handle
        # abbreviations ("Met" ↔ "Metropolitan") and word-order differences.
        # Stop words only (NOT institutional markers) are excluded — institutional markers
        # are kept so "museum" in venue vs location can count as a match.
        _SANITY_STOP_WORDS = {
            'the', 'of', 'and', 'in', 'on', 'at', 'to', 'a', 'an',
            'for', 'with', 'by', 'from', 'or', 'tour', 'tours',
            'inside', 'visit', 'walk', 'walking'
        }
        def _venue_matches_location(venue_name_s, location_s):
            def content_words(s):
                return [w for w in re.findall(r'[a-z]+', s.lower())
                        if len(w) >= 3 and w not in _SANITY_STOP_WORDS]
            v = content_words(venue_name_s)
            l = content_words(location_s)
            if not v or not l:
                return True  # can't judge — permissive
            for vw in v:
                for lw in l:
                    if vw == lw or vw.startswith(lw) or lw.startswith(vw):
                        return True
            return False
        raw_venue = intent.get('venue_name')
        if raw_venue and not _venue_matches_location(raw_venue, location):
            print(f"  [venue_name sanity] '{raw_venue}' has no word overlap with '{location}' — discarding")
            intent['venue_name'] = None
        elif raw_venue:
            print(f"  [venue_name sanity] '{raw_venue}' OK")
        
        # Venue promotion: when venue_name is null but request uses interior preposition
        # and scope ends in an institutional building noun, promote scope to venue_name.
        # This catches "tour IN Robbins House and Monument Square museum" patterns.
        # Does NOT promote district nouns (square, campus, area) — those stay as scope.
        if not intent.get('venue_name'):
            _req_lower = (location or '').lower()
            _scope = (intent.get('geographic_scope') or '').strip()
            _INSTITUTION_TAIL = ('museum', 'house', 'gallery', 'library',
                                 'homestead', 'mansion', 'estate', 'manse')
            _interior = re.search(r'\b(in|inside|within|of)\b', _req_lower)
            if _interior and _scope and intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT'):
                # Strip trailing city/state (e.g., "Robbins House, Concord" → check "House")
                _scope_core = _scope.split(',')[0].strip().lower().rstrip('.')
                _scope_words = _scope_core.split()
                # Check if any of the last 3 words is an institutional noun
                _tail_words = _scope_words[-3:] if len(_scope_words) >= 3 else _scope_words
                if any(w in _INSTITUTION_TAIL for w in _tail_words):
                    intent['venue_name'] = _scope.split(',')[0].strip()  # Use name without city
                    print(f"  [venue promotion] scope '{_scope}' promoted to venue_name "
                          f"(interior preposition + institutional noun)")
        
        # If PHASE 1 identified a specific venue AND the location string does not
        # explicitly request a non-museum tour type, force museum category.
        # Safety net (_EXPLICIT_NON_MUSEUM_TOUR_RE) prevents GPT-hallucinated venue_names
        # on "walking tour starting at X" / "restaurant tour near X" requests from
        # silently flipping the category. See S15 Claude review §3.
        if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
            tour_category = 'museum'
            print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
        else:
            if intent.get('venue_name'):
                if _MULTI_BUILDING_INSTITUTION_RE.search(location):
                    print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains multi-building institution keyword")
                else:
                    print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains explicit non-museum phrase")
            tour_category = _classify_tour_category(location, tour_type)
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        tour_category = _classify_tour_category(location, tour_type)
    
    # PHASE 2: Detect tour type and get appropriate template
    # NOTE: tour_category already set above — do NOT call _classify_tour_category again here
    # (that was the bug: it overwrote the venue_name-based 'museum' decision with 'walking').
    print(f"\nDetected tour category: {tour_category.upper()}")
    print(f"Using {tour_category} template for {location} - {tour_type}")
    
    # ============================================================
    # PHASE 3A: Fetch candidate POI names + addresses (lightweight)
    # PHASE 4.5: Knowledge validation
    # PHASE 4:   Type verification (parallel, skipped for walking)
    # Part C:    Replacement loop (bounded retries)
    # PHASE 3B:  Ordering + structured details + directions
    # ============================================================
    poi_list = []
    first_poi_coordinates = (None, None)  # Default if we can't get coordinates

    # -------- Local helpers (closures over api_key, intent, tour_category) --------
    def _parse_json_array_loose(text):
        """Defensive JSON-array parsing: direct -> markdown-strip -> regex-extract."""
        if not text:
            return None
        t = text.strip()
        m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', t, re.DOTALL)
        if m:
            t = m.group(1).strip()
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
        m = re.search(r'\[\s*\{.*\}\s*\]', t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None

    def _normalize_name(name):
        if not name:
            return ""
        return re.sub(r'\s+', ' ', name.strip()).lower()

    def _verify_against_intent(stops):
        """Run PHASE 4 type verification in parallel. Returns (survivors, excluded_count)."""
        if not (intent and intent.get('poi_type') and tour_category not in ('walking', 'museum')):
            return list(stops), 0
        if not stops:
            return [], 0

        print(f"   PHASE 4: Verifying {len(stops)} POI(s) against type '{intent['poi_type']}' (parallel)...")

        def _verify_one(poi):
            poi_type_val = intent["poi_type"]
            if isinstance(poi_type_val, list):
                poi_type_val = " or ".join(poi_type_val)
            return poi, verify_poi_matches_type(poi["name"], poi_type_val, api_key)

        results = []
        with ThreadPoolExecutor(max_workers=min(len(stops), 5)) as executor:
            futures = {executor.submit(_verify_one, poi): poi for poi in stops}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x: stops.index(x[0]))

        survivors = []
        excluded = 0
        for poi, verification in results:
            if verification["matches"] or verification["confidence"] == "low":
                survivors.append(poi)
                if verification["matches"]:
                    print(f"   OK Verified {poi['name']} - {verification['reason']}")
                else:
                    print(f"   OK Included {poi['name']} (verification failed, low confidence)")
            else:
                poi_desc = poi.get("description", "") or ""
                if "restaurant" in intent["poi_type"].lower() or "food" in intent["poi_type"].lower():
                    should, reason = should_include_in_restaurant_tour(poi["name"], poi_desc, verification["reason"])
                else:
                    should, reason = should_include_in_walking_tour(poi["name"], poi_desc, verification["reason"])
                if should:
                    survivors.append(poi)
                    print(f"   OK Included {poi['name']} - {reason}")
                else:
                    excluded += 1
                    print(f"   X  Excluded {poi['name']} - {verification['reason']}")
        return survivors, excluded

    def _new_poi(name, address=""):
        return {
            "stop_number": 0,
            "name": (name or "").strip(),
            "address": (address or "").strip(),
            "artist": "",
            "year": "",
            "directions": "",
            "coordinates": "",
            "type_specialty": "",
            "specific_examples": "",
            "operational_details": "",
            "description": "",
        }

    # Determine poi_type hint for prompts
    if intent and intent.get('poi_type'):
        raw = intent['poi_type']
        poi_type_hint = " or ".join(raw) if isinstance(raw, list) else raw
    else:
        poi_type_hint = f"{tour_type} stops"

    if tour_type.lower() in location.lower():
        user_request = location
    else:
        # BUG 2 FIX: if location alone encodes the category, don't prepend tour_type
        if _pre_category in ('restaurant', 'walking', 'specialized'):
            user_request = location
        else:
            user_request = f"{tour_type} {location}"

    api_call_logger.log("GENERATING_PROMPT", {
        "location": location,
        "user_request": user_request,
        "total_stops": total_stops,
    })

    # -------- PHASE 3A: names + addresses only --------
    print(f"\nPHASE 3A: Fetching {total_stops} candidate POI(s) for {location}...")

    # Museum single-venue constraint: use venue_name from PHASE 1 intent (Claude option b).
    # intent['venue_name'] is set by GPT when the request is for a tour inside a single
    # named institution. Falls back to regex strip for robustness if intent is unavailable.
    _museum_venue_constraint = ""
    _museum_venue_name = ""
    if tour_category == 'museum':
        # Prefer PHASE 1 intent result (most accurate, handles all formats).
        # IMPORTANT: only apply the single-venue constraint when intent explicitly provides
        # a venue_name. If intent is None (API failure) OR intent returned venue_name: null
        # (multi-venue / city-wide request), do NOT fall back to regex — the mobile app
        # hardcodes tour_type="museum" so tour_category=='museum' even for city-wide museum
        # tours where a single-venue constraint would be wrong.
        if intent and intent.get('venue_name'):
            _museum_venue_name = intent['venue_name'].strip()
            print(f"  [Museum constraint] Venue from intent='{_museum_venue_name}'")
        else:
            # intent is None (API error) or venue_name is null (multi-venue / city-wide).
            # Skip the constraint entirely — do not apply a fabricated venue name.
            _museum_venue_name = ""
            print(f"  [Museum constraint] No venue_name from intent — single-venue constraint skipped")
        # [BLOCKER4a] Deterministic venue fallback: extract venue from location string
        # when intent failed to identify it. Case-insensitive.
        if not _museum_venue_name and tour_category == 'museum':
            _VENUE_WORDS_RE = re.compile(
                r'(?i)\b(mus[ée]+e?|museum|gallery|galerie|palais|villa|château|chateau|library|institute)\b'
            )
            # Take the first comma-segment of the normalized location
            _first_segment = _location_normalized.split(',')[0].strip()
            if _VENUE_WORDS_RE.search(_first_segment) and len(_first_segment.split()) >= 2:
                # Looks like a proper venue name — use it (title-cased)
                _museum_venue_name = _first_segment.title()
                print(f"  [BLOCKER4a] venue_name from location fallback: '{_museum_venue_name}'")
        if _museum_venue_name:
            _museum_venue_constraint = (
                f"\nCRITICAL CONSTRAINT — THIS IS A SINGLE-VENUE MUSEUM TOUR (WORKS-FIRST):\n"
                f"- List the {total_stops} most famous, notable, or significant ARTWORKS, PAINTINGS, "
                f"SCULPTURES, or PERMANENT EXHIBITS at '{_museum_venue_name}'.\n"
                f"- Each stop MUST be named after the ARTWORK or EXHIBIT itself — NOT a room name.\n"
                f"  Good examples: 'Song of Songs' (painting series), 'The Creation of the World' (mosaic), "
                f"'Jerusalem Windows' (stained glass studies)\n"
                f"  Bad examples: 'East Wing Gallery', 'Room 3', 'The Main Hall'\n"
                f"- For each work, if you know which room/gallery/hall it is displayed in, include that "
                f"as a note in the address field (e.g. 'Concert Hall, Avenue Docteur Ménard...'). "
                f"If you do NOT know the room, just use the museum's street address.\n"
                f"- Do NOT suggest any other museums, institutions, or locations outside this building.\n"
                f"- Do NOT fabricate artwork names — only include works you are confident exist at this museum.\n"
                f"- NEVER list nearby museums or cultural institutions as stops — they are OUTSIDE this venue.\n"
                f"- Prefer the museum's most iconic/signature pieces that visitors specifically come to see."
            )
            
            # Pre-resolve venue to get canonical titles as hints for GPT
            # This helps GPT propose works that will actually verify
            try:
                from venue_resolver import resolve_venue, fetch_venue_works, build_canonical_titles_from_works
                _city_hint = ""
                if "," in location:
                    parts = [p.strip() for p in location.split(",")]
                    _city_hint = parts[1] if len(parts) >= 2 else ""
                _pre_entity = resolve_venue(_museum_venue_name, _city_hint)
                if _pre_entity and _pre_entity.qid:
                    _pre_works = fetch_venue_works(_pre_entity.qid, _pre_entity.language)
                    _pre_titles = build_canonical_titles_from_works(_pre_works)
                    if _pre_titles:
                        # Deduplicate by QID: one title per work (prefer local language label)
                        _seen_qids = set()
                        _deduped_hints = []
                        for w in _pre_works:
                            qid = w.get('qid', '')
                            if qid in _seen_qids:
                                continue
                            _seen_qids.add(qid)
                            # Prefer local label (what the museum displays)
                            _deduped_hints.append(w.get('label_local', '') or w.get('label_en', ''))
                        _hint_sample = sorted(_deduped_hints)[:12]
                        _museum_venue_constraint += (
                            f"\n\nKNOWN WORKS AT THIS VENUE (use these as guidance — include some from this list):\n"
                            f"  {'; '.join(_hint_sample)}\n"
                            f"Each work should appear ONLY ONCE in your list — do NOT list the same work under multiple names.\n"
                        )
                        print(f"  [Phase3A] Injected {len(_hint_sample)} canonical title hints from Wikidata (QID-deduped)")
            except Exception as _pre_err:
                print(f"  [Phase3A] Pre-resolution failed (non-fatal): {_pre_err}")

    # -------- Scope + compactness constraints for PHASE 3A --------
    _geo_scope = (intent.get('geographic_scope') or '').strip() if intent else ''
    _scope_precision = (intent.get('scope_precision') or '').strip().upper() if intent else ''
    _scope_constraint = ''
    if _geo_scope and _scope_precision in ('CORRIDOR', 'DISTRICT'):
        _scope_constraint = (
            f"\nGEOGRAPHIC SCOPE — ALL stops MUST be located within: {_geo_scope}.\n"
            f"- Do NOT include well-known landmarks elsewhere in the city just because "
            f"they are famous — if it is outside {_geo_scope}, it does not belong.\n"
        )
        print(f"  [S17] scope_constraint injected: precision={_scope_precision}, scope='{_geo_scope}'")
    else:
        print(f"  [S17] no scope_constraint (precision='{_scope_precision}', scope='{_geo_scope}')")

    _compactness_constraint = ''
    if tour_category == 'walking':
        _compactness_constraint = (
            f"\nWALKING-TOUR COMPACTNESS — this is a walking tour:\n"
            f"- All stops must form ONE compact cluster, close enough to walk between comfortably.\n"
            f"- No stop should be more than a 10–15 minute walk (roughly {WALKING_LEG_TARGET_KM:.0f} km) "
            f"from its nearest neighbour in the tour.\n"
            f"- Prefer a tight set of stops in one walkable area over famous landmarks scattered "
            f"across the city. A shorter, denser route is better than a long, spread-out one.\n"
        )

    # For museum tours with D1v2 verification: ask for 2x candidates to improve hit rate
    _phase3a_count = total_stops
    if tour_category == 'museum' and _museum_venue_name:
        _phase3a_count = min(total_stops * 2, 20)
        print(f"  [R4] Museum tour: asking for {_phase3a_count} candidates (2x for D1v2 filtering)")

    phase_3a_prompt = (
        f"You are a knowledgeable local guide for {location}.\n"
        f"List exactly {_phase3a_count} specific, real, well-known {poi_type_hint} relevant to: {user_request}.\n\n"
        "Requirements:\n"
        "- Use REAL, SPECIFIC names of actual establishments or landmarks.\n"
        "- NEVER use generic placeholders like 'Restaurant 1', 'Stop 1', 'Location A'.\n"
        "- Include a complete street address with ZIP code where applicable.\n"
        + _museum_venue_constraint
        + _scope_constraint
        + _compactness_constraint
        + "\n\nReturn ONLY a JSON array, no other text, no markdown fences:\n"
        '[{"name": "...", "address": "..."}, ...]'
    )
    phase_3a_data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
            {"role": "user", "content": phase_3a_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 800,
    }
    api_call_logger.log("PHASE_3A_REQUEST", {
        "location": location,
        "total_stops": total_stops,
        "poi_type_hint": poi_type_hint,
    })

    try:
        info_response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(phase_3a_data),
        )
        if info_response.status_code != 200:
            print(f"X PHASE 3A failed: status {info_response.status_code}")
            print(info_response.text)
            return None, None, (None, None)

        info_result = info_response.json()
        info_text = info_result["choices"][0]["message"]["content"]
        tokens_used = info_result["usage"]["total_tokens"]
        total_tokens += tokens_used
        total_cost += tokens_used / 1000 * 0.002
        print(f"PHASE 3A API call cost: ${tokens_used / 1000 * 0.002:.4f} ({tokens_used} tokens)")

        api_call_logger.log_openai_call(phase_3a_prompt, total_stops, info_text, info_response.status_code)

        with open("openai_simple_debug.txt", "w", encoding="utf-8") as simple_debug:
            simple_debug.write("=== EXACT PROMPT SENT TO OPENAI (PHASE 3A) ===\n")
            simple_debug.write(phase_3a_prompt)
            simple_debug.write("\n\n=== OPENAI RESPONSE ===\n")
            simple_debug.write(info_text)
            simple_debug.write(f"\n\n=== ANALYSIS ===\nRequested stops: {total_stops}\n")
            simple_debug.write(f"See full chain log: {api_call_logger.get_log_path()}\n")

        # Insufficient-knowledge detection (kept from previous behaviour)
        insufficient_knowledge_indicators = [
            "I don't have sufficient knowledge",
            "I am unable to provide",
            "I cannot provide real-time information",
            "insufficient data available",
            "I don't know actual locations",
            "I lack specific knowledge",
        ]
        for indicator in insufficient_knowledge_indicators:
            if indicator.lower() in info_text.lower():
                print(f"X AI KNOWLEDGE INSUFFICIENT: {info_text[:200]}...")
                return None, None, (None, None)

        candidates = _parse_json_array_loose(info_text)
        if not candidates or not isinstance(candidates, list):
            print(f"X PHASE 3A returned unparseable response: {info_text[:300]}")
            return None, None, (None, None)

        for c in candidates:
            if not isinstance(c, dict):
                continue
            name = (c.get("name") or "").strip()
            if not name:
                continue
            if re.match(r'^(Restaurant|Store|Shop|Location|Business|Walking Tour)\s*\d*$', name):
                print(f"   ! Rejected generic name from PHASE 3A: '{name}'")
                continue
            poi_list.append(_new_poi(name, c.get("address") or ""))

        if len(poi_list) == 0:
            print(f"X PHASE 3A: no usable POIs after parsing")
            return None, None, (None, None)

        print(f"OK PHASE 3A parsed {len(poi_list)} candidate POI(s):")
        for p in poi_list:
            print(f"   - {p['name']}" + (f" @ {p['address']}" if p['address'] else ""))

        # -------- [D1] In-collection verification for museum tours --------
        _d1_evidence_log = {}
        _d1_venue_corpus = ""
        _story_corpus_result = None
        if tour_category == 'museum' and _museum_venue_name:
            # Try new story_miner-based verification (T0a/T1)
            _d1v2_result = _verify_works_v2(poi_list, _museum_venue_name)
            if isinstance(_d1v2_result, VerificationResult):
                _verification_tier = _d1v2_result.tier
                if _d1v2_result.tier == 'unresolvable':
                    # Clean fail with structured error
                    print(f"  [D1] Tier: unresolvable — clean fail (entity={_d1v2_result.entity_resolved}, sparql={_d1v2_result.sparql_count})")
                    global _LAST_CLEAN_FAIL_EVIDENCE
                    _LAST_CLEAN_FAIL_EVIDENCE = {
                        "error_type": "thin_evidence",
                        "entity_resolved": _d1v2_result.entity_resolved,
                        "qid": _d1v2_result.qid,
                        "sparql_works": _d1v2_result.sparql_count,
                        "site_reachable": _d1v2_result.site_reachable,
                        "wikipedia_available": _d1v2_result.wiki_available,
                        "tier": "unresolvable",
                    }
                    return None, None, (None, None)
                # Extract fields from VerificationResult
                _pre_d1v2_candidates = list(poi_list)  # Save original GPT candidates before filtering
                poi_list = _d1v2_result.pois
                _d1_evidence_log = _d1v2_result.evidence_log
                _d1_venue_corpus = _d1v2_result.combined_text
                _story_corpus_result = _d1v2_result.corpus_result
                print(f"  [D1] Tier: {_verification_tier} ({len(poi_list)} verified works)")
                
                # [PALAIS-FIX] For thin tier with sparse Wikidata: restore GPT candidates
                # The venue IS real (Wikidata-resolved) but its artwork catalog is incomplete.
                # Keep GPT-proposed works in degraded mode rather than zero-stop-rejecting.
                if _verification_tier == 'thin' and len(poi_list) < 3 and len(_pre_d1v2_candidates) >= 3:
                    # D1: Only restore candidates whose evidence-log status is "DROPPED / no canonical match"
                    # NEVER restore REJECTED candidates (positive evidence they hang at another venue)
                    _verified_names = set(p['name'].lower() for p in poi_list)
                    # D2: Also exclude by evidence-log keys (handles canonical-rename variants)
                    _evidence_keys_normalized = set(_normalize_name(k) for k in _d1_evidence_log.keys()
                                                   if _d1_evidence_log[k].get('status') == 'VERIFIED')
                    _unverified = []
                    for p in _pre_d1v2_candidates:
                        _cand_name = p['name']
                        _cand_norm = _normalize_name(_cand_name)
                        # Skip if already in verified list (exact or normalized match)
                        if _cand_name.lower() in _verified_names or _cand_norm in _evidence_keys_normalized:
                            continue
                        # D1: Skip if evidence-log shows REJECTED (located at other venue)
                        _ev_entry = _d1_evidence_log.get(_cand_name, {})
                        if isinstance(_ev_entry, dict) and _ev_entry.get('status') == 'REJECTED':
                            continue
                        # D3: Tag as unverified for narration hedging + stop_metrics
                        p['verified'] = False
                        _unverified.append(p)
                    # Cap at 5 unverified additions
                    _restored = _unverified[:5]
                    poi_list = list(poi_list) + _restored
                    # D3: Accurate log line — print actual restored count, not pre-filter count
                    print(f"  [D1] THIN tier degraded mode: restored {len(_restored)} unverified GPT candidates "
                          f"(filtered from {len(_pre_d1v2_candidates)} total, "
                          f"Wikidata catalog too sparse for strict filtering)")
            else:
                # _verify_works_v2 returned None or unexpected type — fail-closed (unresolvable)
                print(f"  [D1] D1v2 returned unexpected result — demoting to unresolvable (fail-closed)")
                _LAST_CLEAN_FAIL_EVIDENCE.clear()
                _LAST_CLEAN_FAIL_EVIDENCE.update({
                    "error_type": "thin_evidence",
                    "entity_resolved": False,
                    "qid": "",
                    "sparql_works": 0,
                    "site_reachable": False,
                    "wikipedia_available": False,
                    "tier": "unresolvable",
                })
                return None, None, (None, None)

            # -------- [R4] Bounded replenishment loop --------
            # For medium/thin tiers: don't pad with unverifiable stops (use only verified)
            # Exception: if thin tier has too few verified works (< 3), allow GPT-proposed
            # works to proceed in degraded mode — the venue is Wikidata-resolved, so it's
            # a real museum; Wikidata just has sparse artwork listings for it.
            if _verification_tier in ('medium', 'thin'):
                if _verification_tier == 'thin' and len(poi_list) < 3:
                    # Sparse Wikidata coverage — trust GPT for this Wikidata-verified venue
                    # Cap to a reasonable number but don't zero-stop-reject
                    _thin_cap = min(total_stops, 5)
                    print(f"  [R4] THIN tier with sparse coverage ({len(poi_list)} stops, "
                          f"{sum(1 for p in poi_list if p.get('verified', True))} verified) — "
                          f"allowing up to {_thin_cap} stops for Wikidata-resolved venue")
                    total_stops = _thin_cap
                else:
                    _n_verified_in_list = sum(1 for p in poi_list if p.get('verified', True))
                    total_stops = len(poi_list)
                    print(f"  [R4] SKIPPED — tier={_verification_tier}, total_stops={total_stops} "
                          f"({_n_verified_in_list} verified + {total_stops - _n_verified_in_list} unverified)")
            # If verified < requested, re-prompt for MORE candidates and verify (rich tier only)
            _r4_all_tried_names = set(_normalize_name(p['name']) for p in poi_list)
            _r4_all_tried_names.update(_normalize_name(k) for k in _d1_evidence_log.keys())
            _r4_round = 0
            _R4_MAX_ROUNDS = 3
            _R4_MAX_CANDIDATES = 30
            
            while len(poi_list) < total_stops and _r4_round < _R4_MAX_ROUNDS and len(_r4_all_tried_names) < _R4_MAX_CANDIDATES:
                _r4_round += 1
                _r4_needed = total_stops - len(poi_list)
                _r4_ask = min(_r4_needed + 5, 15)  # Ask for extras to improve hit rate
                print(f"\n  [R4] Replenishment round {_r4_round}/{_R4_MAX_ROUNDS}: need {_r4_needed} more, asking for {_r4_ask}")
                
                # Build exclusion list
                _r4_forbidden = sorted(_r4_all_tried_names)[:50]
                _r4_forbidden_str = "; ".join(_r4_forbidden) if _r4_forbidden else "(none)"
                
                _r4_prompt = (
                    f"You are a knowledgeable art historian. "
                    f"List exactly {_r4_ask} INDIVIDUAL ARTWORKS at '{_museum_venue_name}'.\n"
                    f"DO NOT include: {_r4_forbidden_str}\n"
                    f"DO NOT include the name of the exhibition/collection itself.\n"
                    f"Each must be a real, named, individual artwork (painting, mosaic, sculpture, stained glass).\n"
                )
                # Add hints from discovered canonical titles (helps GPT propose correct works)
                if _story_corpus_result and _story_corpus_result.get('canonical_titles'):
                    _hint_titles = sorted(_story_corpus_result['canonical_titles'] - _r4_all_tried_names)[:10]
                    if _hint_titles:
                        _r4_prompt += f"HINT — these works are known to be at this venue: {'; '.join(_hint_titles)}\n"
                        _r4_prompt += "You may include works from this list AND other works you know are there.\n"
                _r4_prompt += f"Return ONLY a JSON array: [{{\"name\": \"...\", \"address\": \"...\"}}]"
                _r4_data = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "Return ONLY valid JSON arrays."},
                        {"role": "user", "content": _r4_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                }
                try:
                    _r4_resp = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers, data=json.dumps(_r4_data)
                    )
                    if _r4_resp.status_code != 200:
                        print(f"    [R4] API error {_r4_resp.status_code}")
                        break
                    _r4_result = _r4_resp.json()
                    _r4_text = _r4_result["choices"][0]["message"]["content"]
                    tokens_used = _r4_result["usage"]["total_tokens"]
                    total_tokens += tokens_used
                    total_cost += tokens_used / 1000 * 0.002
                    
                    _r4_candidates = _parse_json_array_loose(_r4_text)
                    if not _r4_candidates:
                        print(f"    [R4] Unparseable response — retrying")
                        continue
                    
                    # Build POI objects and verify
                    _r4_new_pois = []
                    for c in _r4_candidates:
                        if not isinstance(c, dict):
                            continue
                        name = (c.get("name") or "").strip()
                        if not name or _normalize_name(name) in _r4_all_tried_names:
                            continue
                        _r4_all_tried_names.add(_normalize_name(name))
                        _r4_new_pois.append(_new_poi(name, c.get("address") or ""))
                    
                    if not _r4_new_pois:
                        print(f"    [R4] No new candidates after dedup")
                        break
                    
                    # Verify new candidates
                    if _story_corpus_result:
                        from story_miner import match_candidate_to_canonical
                        _r4_verified = []
                        for p in _r4_new_pois:
                            match = match_candidate_to_canonical(
                                p['name'],
                                _story_corpus_result['canonical_titles'],
                                _story_corpus_result['combined_text']
                            )
                            if match:
                                _r4_verified.append(p)
                                _d1_evidence_log[p['name']] = {
                                    "status": "VERIFIED",
                                    "canonical_title": match[0],
                                    "snippet": match[1],
                                    "method": "R4_replenishment",
                                }
                                print(f"    [R4] VERIFIED '{p['name']}' → '{match[0]}'")
                            else:
                                print(f"    [R4] dropped '{p['name']}'")
                        
                        _r4_added = _r4_verified[:_r4_needed]
                        poi_list.extend(_r4_added)
                        print(f"    [R4] Round {_r4_round}: +{len(_r4_added)} verified, total now {len(poi_list)}")
                    else:
                        print(f"    [R4] No corpus for verification — skipping")
                        break
                        
                except Exception as e:
                    print(f"    [R4] Error: {e}")
                    break
            
            if len(poi_list) < total_stops:
                print(f"  [R4] Replenishment exhausted: {len(poi_list)}/{total_stops} stops (stop_count_warning)")
            else:
                print(f"  [R4] Target reached: {len(poi_list)}/{total_stops} stops")

        # -------- [BLOCKER 1] Single-venue validation --------
        # For a named single museum, check if POIs look like other museums/venues
        # instead of interior rooms/exhibits. Reject and note for retry.
        if tour_category == 'museum':
            _VENUE_INDICATORS = ('musée', 'museum', 'galerie', 'gallery', 'palais',
                                 'villa', 'château', 'castle', 'cathedral', 'church',
                                 'basilica', 'temple', 'theatre', 'theater', 'opera',
                                 'bibliothèque', 'library', 'institut', 'centre',
                                 'opéra', 'théâtre', 'chapelle', 'cathédrale')
            if _museum_venue_name:
                _venue_norm = _museum_venue_name.lower()
                _suspect_venues = []
                for p in poi_list:
                    _pname = p['name'].lower()
                    # Check if POI name contains a venue-type word AND is not the target venue
                    for indicator in _VENUE_INDICATORS:
                        if indicator in _pname and _venue_norm not in _pname and _pname not in _venue_norm:
                            _suspect_venues.append(p['name'])
                            break
                if len(_suspect_venues) >= max(1, len(poi_list) // 2):
                    print(f"  [BLOCKER1] ⚠️ Phase 3A returned {len(_suspect_venues)} stops that look like "
                          f"OTHER venues (not interior rooms of '{_museum_venue_name}'):")
                    for sv in _suspect_venues:
                        print(f"    ✗ {sv}")
                    print(f"  [BLOCKER1] This indicates the model misread the request as 'a tour OF the city' "
                          f"rather than 'a tour INSIDE the venue'. Rejecting — will retry or fail cleanly.")
                    # Structured clean-fail evidence (D3: was missing → mobile got Type: null)
                    _LAST_CLEAN_FAIL_EVIDENCE.clear()
                    _LAST_CLEAN_FAIL_EVIDENCE.update({
                        "error_type": "venue_misread",
                        "venue_name": _museum_venue_name,
                        "suspect_venues": _suspect_venues[:5],
                        "total_stops": len(poi_list),
                        "tier": _verification_tier if '_verification_tier' in dir() else 'unknown',
                    })
                    return None, None, (None, None)
            # [BLOCKER4b] Address-scatter check: a contained museum tour should have
            # at most 2-3 distinct addresses (all inside one building).
            _unique_addresses = set()
            for p in poi_list:
                addr = (p.get('address') or '').strip().lower()
                if addr and len(addr) > 10:
                    # Normalize: take first 30 chars to group similar addresses
                    _unique_addresses.add(addr[:30])
            if len(_unique_addresses) >= len(poi_list) // 2 and len(poi_list) >= 5:
                print(f"  [BLOCKER4b] ⚠️ Address scatter: {len(_unique_addresses)} distinct addresses "
                      f"for {len(poi_list)} stops — a contained museum tour should have 1-2 addresses.")
                print(f"  [BLOCKER4b] Rejecting — this looks like a city-wide museum tour, not interior rooms.")
                # [PALAIS-FIX B2] Structured clean-fail evidence for BLOCKER4b
                _LAST_CLEAN_FAIL_EVIDENCE.clear()
                _LAST_CLEAN_FAIL_EVIDENCE.update({
                    "error_type": "address_scatter",
                    "venue_name": _museum_venue_name,
                    "unique_addresses": len(_unique_addresses),
                    "tier": _verification_tier if '_verification_tier' in dir() else 'unknown',
                })
                return None, None, (None, None)

        # -------- PHASE 4.5: knowledge validation (names + descriptions) --------
        print(f"\nPHASE 4.5: Validating AI knowledge for {location}...")
        # NOTE: at this point descriptions are not yet generated (PHASE 5 is later).
        # validate_enhanced_poi_knowledge checks names now; descriptions are validated
        # again after PHASE 5 via _validate_museum_stop_descriptions() for museum tours.
        knowledge_valid, knowledge_message = validate_enhanced_poi_knowledge(poi_list, intent, location)
        if not knowledge_valid:
            print(f"X Knowledge validation failed: {knowledge_message}")
            return None, None, (None, None)
        print(f"OK Knowledge validation passed: {knowledge_message}")

        # Snapshot before PHASE 4
        poi_list_before_verification = list(poi_list)

        # -------- PHASE 4: parallel type verification (skipped for walking + museum) --------
        # Museum tours: every stop is a room/exhibit inside a known venue — type verification
        # provides no signal and the wrong stops in the hallucination bug all passed it anyway.
        if intent and intent.get('poi_type') and tour_category not in ('walking', 'museum'):
            print(f"\nPHASE 4: Verifying POIs match requested type '{intent['poi_type']}' (parallel)...")
            poi_list, excluded_count = _verify_against_intent(poi_list)
            if excluded_count > 0:
                print(f"\n! PHASE 4 excluded {excluded_count} POI(s)")
        else:
            excluded_count = 0
            print(f"\nPHASE 4: skipped (tour_category='{tour_category}', no type-verification required)")

        excluded_names = {p["name"] for p in poi_list_before_verification if p not in poi_list}

        # Build forbidden name set BEFORE PHASE 3C so PHASE 3C rejects flow into Part C.
        # Part C uses this set to avoid re-fetching names already proposed or rejected.
        forbidden_norms = set()
        for p in poi_list_before_verification:
            forbidden_norms.add(_normalize_name(p["name"]))
        for p in poi_list:
            forbidden_norms.add(_normalize_name(p["name"]))

        # -------- Detect user-explicit stops --------
        # When the user request contains "with stops at X, Y, Z" or "stops: X, Y, Z",
        # those POI names are sacrosanct — PHASE 3C must NOT remove them based on address.
        # The user knows better than the address validator which stops they want.
        _explicit_stop_names = set()
        _explicit_match = re.search(r'(?:with\s+)?stops\s+(?:at|:)\s*(.+?)(?:,\s*(?:[A-Z]{2})\s*$|$)', location, re.IGNORECASE)
        if _explicit_match:
            _explicit_raw = _explicit_match.group(1)
            # Split on commas, strip whitespace and leading dots/periods
            _explicit_candidates = [s.strip().strip('.').strip() for s in _explicit_raw.split(',')]
            # Filter out state/city suffixes (short tokens like "MA", "Milton")
            for cand in _explicit_candidates:
                if len(cand) > 3 and not re.match(r'^[A-Z]{2}$', cand.strip()):
                    _explicit_stop_names.add(_normalize_name(cand))
            if _explicit_stop_names:
                print(f"   [PHASE 3C bypass] User-explicit stops detected: {_explicit_stop_names}")

        # -------- PHASE 3C: address-based location guard --------
        # Runs BEFORE Part C so rejected stops can be replaced by the replacement loop.
        # Museum tours with a single venue are skipped -- all stops are inside one building.
        # Walking tours are skipped -- the GEO-CHECK (coordinate-based distance validation)
        # after Phase 3B is a better proximity check than town-name matching. Stops on town
        # borders (e.g. Milton/Dorchester/Hyde Park) share geography but differ in postal city,
        # so address matching produces false rejections for walking tours.
        if tour_category == 'walking':
            print(f"   PHASE 3C: skipped for walking tours (GEO-CHECK handles proximity)")
        elif tour_category != 'museum' or not _museum_venue_name:
            location_rejects = []
            for p in poi_list:
                p_norm = _normalize_name(p['name'])
                # Skip address check for user-explicit stops
                if p_norm in _explicit_stop_names:
                    print(f"   PHASE 3C: KEPT '{p['name']}' (user-explicit stop, address check bypassed)")
                    continue
                if not _address_matches_location(p.get('address', ''), location):
                    location_rejects.append(p)
            if location_rejects:
                for p in location_rejects:
                    print(f"   PHASE 3C: REMOVED '{p['name']}' -- address '{p['address']}' not in '{location}'")
                    forbidden_norms.add(_normalize_name(p['name']))
                poi_list = [p for p in poi_list if p not in location_rejects]
                print(f"   PHASE 3C: {len(location_rejects)} out-of-area stop(s) removed; {len(poi_list)} remain")
            else:
                print(f"   PHASE 3C: all {len(poi_list)} stops pass location guard")

            if len(poi_list) == 0:
                raise ValueError(f"PHASE 3C rejected all stops for location '{location}'")

        # -------- Part C: replacement loop (bounded) --------
        attempts = 0

        while len(poi_list) < total_stops and attempts < MAX_REPLACEMENT_ATTEMPTS:
            attempts += 1
            needed = total_stops - len(poi_list)
            print(f"\nPart C: Fetching {needed} replacement POI(s), attempt {attempts}/{MAX_REPLACEMENT_ATTEMPTS}...")

            # Build the "do not use" list of original-cased names for the prompt
            forbidden_display = sorted(set(
                p["name"] for p in poi_list_before_verification
            ) | set(
                p["name"] for p in poi_list
            ) | set(excluded_names))
            forbidden_str = "; ".join(forbidden_display) if forbidden_display else "(none)"

            replacement_prompt = (
                f"You are a knowledgeable local guide for {location}.\n"
                f"Suggest exactly {needed} additional specific, real, well-known {poi_type_hint} in {location}.\n"
                f"DO NOT include any of these already-used or rejected names: {forbidden_str}.\n\n"
                "Requirements:\n"
                "- REAL, SPECIFIC names; never generic placeholders.\n"
                "- Complete street address with ZIP where applicable.\n\n"
                "Return ONLY a JSON array, no other text:\n"
                '[{"name": "...", "address": "..."}, ...]'
            )
            replacement_data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                    {"role": "user", "content": replacement_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            }
            try:
                rep_response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(replacement_data),
                )
                if rep_response.status_code != 200:
                    print(f"   Part C attempt {attempts}: API error {rep_response.status_code}")
                    continue
                rep_result = rep_response.json()
                rep_text = rep_result["choices"][0]["message"]["content"]
                tokens_used = rep_result["usage"]["total_tokens"]
                total_tokens += tokens_used
                total_cost += tokens_used / 1000 * 0.002

                new_candidates = _parse_json_array_loose(rep_text)
                if not new_candidates or not isinstance(new_candidates, list):
                    print(f"   Part C attempt {attempts}: unparseable response")
                    continue

                new_stops = []
                for c in new_candidates:
                    if not isinstance(c, dict):
                        continue
                    name = (c.get("name") or "").strip()
                    if not name:
                        continue
                    if re.match(r'^(Restaurant|Store|Shop|Location|Business|Walking Tour)\s*\d*$', name):
                        continue
                    norm = _normalize_name(name)
                    if norm in forbidden_norms:
                        continue
                    new_stops.append(_new_poi(name, c.get("address") or ""))
                    forbidden_norms.add(norm)

                print(f"   Part C attempt {attempts}: AI returned {len(new_stops)} usable candidate(s)")

                # Verify the new stops too (same PHASE 4 logic)
                survived, _ = _verify_against_intent(new_stops)
                # Also apply PHASE 3C address check to replacements (skip for walking tours)
                if tour_category == 'walking':
                    pass  # GEO-CHECK handles proximity for walking tours
                elif tour_category != 'museum' or not _museum_venue_name:
                    survived = [p for p in survived if _address_matches_location(p.get('address', ''), location)]
                
                # [Cycle 4] D1 re-verification for museum tour Part C candidates
                # Filter out candidates that are OTHER museums/venues (not artworks)
                if tour_category == 'museum' and _museum_venue_name and survived:
                    _VENUE_INDICATORS_PARTC = ('musée', 'museum', 'musee', 'galerie', 'gallery',
                                               'palais', 'villa', 'château', 'castle', 'cathedral',
                                               'church', 'basilica', 'temple', 'theatre', 'theater',
                                               'opera', 'bibliothèque', 'library', 'institut', 'centre')
                    _venue_lower = _museum_venue_name.lower()
                    _partc_filtered = []
                    for _pc in survived:
                        _pc_name_lower = _pc['name'].lower()
                        # Reject if it's clearly another venue/institution
                        _is_other_venue = False
                        for _vi in _VENUE_INDICATORS_PARTC:
                            if _vi in _pc_name_lower and _venue_lower not in _pc_name_lower and _pc_name_lower not in _venue_lower:
                                _is_other_venue = True
                                break
                        if _is_other_venue:
                            print(f"   Part C D1: REJECTED '{_pc['name']}' — looks like another venue")
                        else:
                            _partc_filtered.append(_pc)
                    survived = _partc_filtered
                
                survived = survived[:needed]
                poi_list.extend(survived)
                # forbid every attempted name so subsequent attempts diverge
                for p in new_stops:
                    forbidden_norms.add(_normalize_name(p["name"]))
                print(f"   Part C attempt {attempts}: {len(survived)} survived; total now {len(poi_list)}")
            except Exception as e:
                print(f"   Part C attempt {attempts}: exception {e}")
                continue

        # Hard cap and final sanity
        if len(poi_list) > total_stops:
            poi_list = poi_list[:total_stops]
        if len(poi_list) == 0:
            print(f"X All POIs were filtered out; cannot continue")
            return None, None, (None, None)
        if len(poi_list) < total_stops:
            print(f"! Final count {len(poi_list)} < requested {total_stops}; orchestrator will surface stop_count_warning")

        for i, p in enumerate(poi_list):
            p["stop_number"] = i + 1

        # -------- PHASE 3B: ordering + structured details + directions --------
        # Extracted into _run_phase_3b() so it can be called again after geo-check replacements.
        def _run_phase_3b(current_poi_list):
            """Order stops, fill structured details, get directions. Returns updated poi_list."""
            if len(current_poi_list) <= 1:
                return current_poi_list
            s_lines = [
                f'- {p["name"]}' + (f' (Address: {p["address"]})' if p.get('address') else '')
                for p in current_poi_list
            ]
            prompt = (
                f"For a tour of {location}, the following {len(current_poi_list)} stop(s) have been selected:\n"
                + "\n".join(s_lines) + "\n\n"
                "Reorder them for an OPTIMAL walking route (minimise backtracking).\n"
                "- Keep the overall route as short as possible; minimise the longest single leg "
                "between any two consecutive stops.\n"
                "For each stop in the NEW order, provide all the JSON fields below.\n"
                "For stop #1, 'directions_from_previous' should describe how to reach it from a reasonable arrival point (T station, parking, main street).\n"
                "For subsequent stops, 'directions_from_previous' should be turn-by-turn walking directions from the IMMEDIATELY PREVIOUS stop in the new order.\n\n"
                "Return ONLY a JSON array, no markdown fences, no commentary:\n"
                "[\n  {\n"
                '    "name": "<must match one of the input names exactly>",\n'
                '    "address": "<complete street address with ZIP>",\n'
                '    "coordinates": "<lat, lng in decimal format>",\n'
                '    "type_specialty": "<short type/specialty description>",\n'
                '    "specific_examples": "<2-3 concrete examples of what visitors will see/experience>",\n'
                '    "operational_details": "<hours, prices, reservations, busy times>",\n'
                '    "directions_from_previous": "<turn-by-turn>"\n'
                "  }\n]"
            )
            req_data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 2000,
            }
            nonlocal total_tokens, total_cost
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(req_data),
                )
                if resp.status_code != 200:
                    print(f"! PHASE 3B failed (status {resp.status_code}); keeping current order")
                    return current_poi_list
                b_result = resp.json()
                b_text = b_result["choices"][0]["message"]["content"]
                tokens_used = b_result["usage"]["total_tokens"]
                total_tokens += tokens_used
                total_cost += tokens_used / 1000 * 0.002
                print(f"PHASE 3B API call cost: ${tokens_used / 1000 * 0.002:.4f} ({tokens_used} tokens)")
                parsed = _parse_json_array_loose(b_text)
                if not parsed or not isinstance(parsed, list):
                    print(f"! PHASE 3B unparseable response; keeping current order")
                    return current_poi_list
                canonical_by_norm = {_normalize_name(p['name']): p for p in current_poi_list}
                parsed_normalized = []
                unknown = []
                for entry in parsed:
                    if not isinstance(entry, dict):
                        continue
                    norm = _normalize_name(entry.get('name', ''))
                    if norm in canonical_by_norm:
                        entry['name'] = canonical_by_norm[norm]['name']
                        parsed_normalized.append(entry)
                    else:
                        unknown.append(entry.get('name', ''))
                if unknown:
                    print(f"! PHASE 3B introduced unknown names (ignored): {unknown}")
                if not parsed_normalized:
                    print(f"! PHASE 3B produced no recognisable entries; keeping current order")
                    return current_poi_list
                present_norms = {_normalize_name(e['name']) for e in parsed_normalized}
                for orig in current_poi_list:
                    if _normalize_name(orig['name']) not in present_norms:
                        print(f"! PHASE 3B dropped POI; re-appending: {orig['name']}")
                        parsed_normalized.append({
                            'name': orig['name'], 'address': orig.get('address', ''),
                            'coordinates': orig.get('coordinates', ''),
                            'type_specialty': '', 'specific_examples': '',
                            'operational_details': '', 'directions_from_previous': '',
                        })
                if len(parsed_normalized) > total_stops:
                    parsed_normalized = parsed_normalized[:total_stops]
                new_list = []
                for idx, entry in enumerate(parsed_normalized):
                    norm = _normalize_name(entry['name'])
                    orig = canonical_by_norm.get(norm)
                    merged = _new_poi(entry['name'], entry.get('address') or (orig.get('address') if orig else ''))
                    merged['stop_number'] = idx + 1
                    merged['directions'] = (entry.get('directions_from_previous') or '').strip()
                    merged['coordinates'] = (entry.get('coordinates') or (orig.get('coordinates', '') if orig else '')).strip()
                    merged['type_specialty'] = (entry.get('type_specialty') or '').strip()
                    merged['specific_examples'] = (entry.get('specific_examples') or '').strip()
                    merged['operational_details'] = (entry.get('operational_details') or '').strip()
                    new_list.append(merged)
                print(f"OK PHASE 3B: ordered {len(new_list)} stop(s) with structured details and directions")
                return new_list
            except Exception as e:
                print(f"! PHASE 3B exception: {e}; keeping current order")
                return current_poi_list

        print(f"\nPHASE 3B: Requesting structured details and walking directions for {len(poi_list)} stop(s)...")
        api_call_logger.log("PHASE_3B_REQUEST", {
            "location": location,
            "stop_count": len(poi_list),
        })

        poi_list = _run_phase_3b(poi_list)

        # -------- Coordinates fallback: request for any stop missing coordinates --------
        # PHASE 3B sometimes omits coordinates for one or more stops. Request them
        # individually (parallel) so every stop gets a map pin.
        def _fetch_coords(poi):
            prompt = (
                f"Provide GPS coordinates for '{poi['name']}'"
                + (f" at {poi['address']}" if poi.get('address') else f" in {location}")
                + ".\nFormat: Latitude: [number]\nLongitude: [number]\nOnly coordinates, nothing else."
            )
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You provide accurate GPS coordinates. Respond only with Latitude and Longitude lines."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 60,
            }
            try:
                resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(data))
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"]
                    lat_m = re.search(r'Latitude:\s*(-?\d+\.\d+)', text, re.IGNORECASE)
                    lng_m = re.search(r'Longitude:\s*(-?\d+\.\d+)', text, re.IGNORECASE)
                    if lat_m and lng_m:
                        return poi, f"{lat_m.group(1)}, {lng_m.group(1)}", resp.json()["usage"]["total_tokens"]
            except Exception as e:
                print(f"   Coords fallback error for '{poi['name']}': {e}")
            return poi, "", 0

        missing_coords = [p for p in poi_list if not p.get('coordinates')]
        if missing_coords:
            print(f"\nCoordinates fallback: requesting coords for {len(missing_coords)} stop(s) missing them...")
            with ThreadPoolExecutor(max_workers=min(len(missing_coords), 5)) as executor:
                futures = {executor.submit(_fetch_coords, p): p for p in missing_coords}
                for future in as_completed(futures):
                    poi, coords, tokens_used = future.result()
                    if coords:
                        poi['coordinates'] = coords
                        total_tokens += tokens_used
                        total_cost += tokens_used / 1000 * 0.002
                        print(f"   Coords fallback OK '{poi['name']}': {coords}")
                    else:
                        print(f"   Coords fallback FAILED '{poi['name']}' — no map pin for this stop")

        # -------- Duplicate-coordinate cluster detection --------
        # GPT sometimes returns the same lat/lng for all stops on a linear route.
        # If >=50% of stops share one coordinate string, clear them and re-run the fallback.
        coord_counts = Counter(p.get('coordinates', '') for p in poi_list if p.get('coordinates'))
        if coord_counts:
            top_coord, top_count = coord_counts.most_common(1)[0]
            if top_coord and top_count >= max(2, len(poi_list) // 2):
                clustered = [p for p in poi_list if p.get('coordinates') == top_coord]
                print(f"   Coords cluster detected: {top_count} stops share '{top_coord}', refetching...")
                for p in clustered:
                    p['coordinates'] = ''
                missing_coords2 = [p for p in poi_list if not p.get('coordinates')]
                if missing_coords2:
                    with ThreadPoolExecutor(max_workers=min(len(missing_coords2), 5)) as executor:
                        futures2 = {executor.submit(_fetch_coords, p): p for p in missing_coords2}
                        for future in as_completed(futures2):
                            poi, coords, tokens_used = future.result()
                            if coords:
                                poi['coordinates'] = coords
                                total_tokens += tokens_used
                                total_cost += tokens_used / 1000 * 0.002
                                print(f"   Cluster refetch OK '{poi['name']}': {coords}")
                            else:
                                print(f"   Cluster refetch FAILED '{poi['name']}' -- no map pin")


        # -------- Walking-compactness geometric verification --------
        # Deterministic. Catches gross dispersion the PHASE 3A prompt missed.
        # Straight-line distance is a guaranteed LOWER BOUND on walking distance, so a
        # leg over the hard limit is unarguably too far to walk.
        # ADVISORY: never raises ValueError, never removes all stops.
        if tour_category == 'walking':
            pts = [(p, _parse_coords(p.get('coordinates', ''))) for p in poi_list]
            pts_valid = [(p, c) for p, c in pts if c]
            if len(pts_valid) >= 3:
                legs = [_haversine_km(pts_valid[i][1], pts_valid[i+1][1]) for i in range(len(pts_valid) - 1)]
                total_route_km = sum(legs)
                medoid = min(pts_valid, key=lambda pc: sum(_haversine_km(pc[1], o) for _, o in pts_valid))[1]
                outliers = []
                for i, leg in enumerate(legs):
                    if leg > WALKING_LEG_HARD_KM:
                        a, b = pts_valid[i], pts_valid[i+1]
                        farther = a[0] if _haversine_km(a[1], medoid) > _haversine_km(b[1], medoid) else b[0]
                        outliers.append(farther)
                if total_route_km > WALKING_TOTAL_HARD_KM and not outliers:
                    outliers = [max(pts_valid, key=lambda pc: _haversine_km(pc[1], medoid))[0]]
                # Dedupe (a stop can be flagged by two adjacent legs)
                seen_ids = set()
                outliers = [o for o in outliers if id(o) not in seen_ids and not seen_ids.add(id(o))]
                # Protect user-explicit stops from GEO-CHECK removal — the user knows
                # their named stops may be far apart (regional/driving tour); honor the request.
                if _explicit_stop_names:
                    protected = [o for o in outliers if _normalize_name(o['name']) in _explicit_stop_names]
                    if protected:
                        for p in protected:
                            print(f"   GEO-CHECK: KEPT '{p['name']}' (user-explicit stop, distance check bypassed)")
                        outliers = [o for o in outliers if o not in protected]
                if outliers and (len(poi_list) - len(outliers)) >= 2:
                    for p in outliers:
                        print(f"   GEO-CHECK: REMOVED '{p['name']}' — exceeds walking-tour distance limit")
                        forbidden_norms.add(_normalize_name(p['name']))
                    poi_list = [p for p in poi_list if p not in outliers]
                    print(f"   GEO-CHECK: {len(outliers)} dispersed stop(s) removed; {len(poi_list)} remain")

                    # Fetch replacements for removed stops
                    needed = total_stops - len(poi_list)
                    if needed > 0:
                        accepted_names = "; ".join(p['name'] for p in poi_list)
                        scope_hint = f" located within {_geo_scope}" if _geo_scope else f" in {location}"
                        forbidden_display = "; ".join(sorted(forbidden_norms))
                        rep_prompt = (
                            f"You are a knowledgeable local guide for {location}.\n"
                            f"Suggest exactly {needed} additional specific, real, well-known {poi_type_hint}"
                            f"{scope_hint}, close to these already-accepted stops: {accepted_names}.\n"
                            f"DO NOT include any of these already-used or rejected names: {forbidden_display}.\n\n"
                            "Requirements:\n"
                            "- REAL, SPECIFIC names; never generic placeholders.\n"
                            "- Complete street address with ZIP where applicable.\n"
                            "- Must be within comfortable walking distance of the accepted stops.\n\n"
                            "Return ONLY a JSON array, no other text:\n"
                            '[{"name": "...", "address": "..."}, ...]'
                        )
                        rep_data = {
                            "model": "gpt-3.5-turbo",
                            "messages": [
                                {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                                {"role": "user", "content": rep_prompt}
                            ],
                            "temperature": 0.7,
                            "max_tokens": 500,
                        }
                        try:
                            rep_resp = requests.post(
                                "https://api.openai.com/v1/chat/completions",
                                headers=headers,
                                data=json.dumps(rep_data),
                            )
                            if rep_resp.status_code == 200:
                                rep_tokens = rep_resp.json()["usage"]["total_tokens"]
                                total_tokens += rep_tokens
                                total_cost += rep_tokens / 1000 * 0.002
                                new_candidates = _parse_json_array_loose(rep_resp.json()["choices"][0]["message"]["content"])
                                if new_candidates and isinstance(new_candidates, list):
                                    new_stops = []
                                    for c in new_candidates:
                                        if not isinstance(c, dict):
                                            continue
                                        name = (c.get('name') or '').strip()
                                        if not name or _normalize_name(name) in forbidden_norms:
                                            continue
                                        new_stops.append(_new_poi(name, c.get('address') or ''))
                                        forbidden_norms.add(_normalize_name(name))
                                    poi_list.extend(new_stops[:needed])
                                    print(f"   GEO-CHECK replacement: {min(len(new_stops), needed)} stop(s) added; total now {len(poi_list)}")
                        except Exception as e:
                            print(f"   GEO-CHECK replacement exception: {e}")

                    # Fetch coordinates for any new stops that don't have them
                    missing_geo = [p for p in poi_list if not p.get('coordinates')]
                    if missing_geo:
                        print(f"   GEO-CHECK: fetching coords for {len(missing_geo)} replacement stop(s)...")
                        with ThreadPoolExecutor(max_workers=min(len(missing_geo), 5)) as executor:
                            futures_geo = {executor.submit(_fetch_coords, p): p for p in missing_geo}
                            for future in as_completed(futures_geo):
                                poi_r, coords_r, tok_r = future.result()
                                if coords_r:
                                    poi_r['coordinates'] = coords_r
                                    total_tokens += tok_r
                                    total_cost += tok_r / 1000 * 0.002
                                    print(f"   GEO-CHECK coords OK '{poi_r['name']}': {coords_r}")
                                else:
                                    print(f"   GEO-CHECK coords FAILED '{poi_r['name']}'")

                    # Re-order the combined set (survivors + replacements)
                    if len(poi_list) > 1:
                        print(f"\nPHASE 3B (re-order after GEO-CHECK): {len(poi_list)} stop(s)...")
                        poi_list = _run_phase_3b(poi_list)

                elif outliers:
                    print(f"   GEO-CHECK: all stops flagged — keeping original list (advisory only)")
                else:
                    print(f"   GEO-CHECK: all {len(poi_list)} stops within walking distance (max leg {max(legs):.2f} km, total {total_route_km:.2f} km)")
            else:
                print(f"   GEO-CHECK: skipped (fewer than 3 stops have coordinates)")

        # -------- Coordinates for the first POI (used by orchestrator) --------
        if poi_list and poi_list[0].get("coordinates"):
            try:
                coords_text = poi_list[0]["coordinates"]
                coord_match = re.search(r'(\d+\.\d+)\s*[°]?\s*([NS]).*?(\d+\.\d+)\s*[°]?\s*([EW])', coords_text, re.IGNORECASE)
                if coord_match:
                    lat = float(coord_match.group(1))
                    if coord_match.group(2).upper() == 'S':
                        lat = -lat
                    lng = float(coord_match.group(3))
                    if coord_match.group(4).upper() == 'W':
                        lng = -lng
                    first_poi_coordinates = (lat, lng)
                else:
                    nums = re.findall(r'-?\d+\.\d+', coords_text)
                    if len(nums) >= 2:
                        first_poi_coordinates = (float(nums[0]), float(nums[1]))
                if first_poi_coordinates != (None, None):
                    print(f"Extracted first POI coordinates: {first_poi_coordinates}")
            except Exception as e:
                print(f"Error parsing first POI coordinates: {e}")

        # [T5] Venue coordinate from geocoding/known sources (not model output)
        # Known museum coordinates (authoritative, from Wikipedia/Google Maps)
        _KNOWN_VENUE_COORDS = {
            'chagall': (43.7102, 7.2703),  # Musée National Marc Chagall, Nice
            'matisse': (43.7196, 7.2755),  # Musée Matisse, Nice (Villa des Arènes, Cimiez)
        }
        _geocoded_coord = None
        for _key, _coord in _KNOWN_VENUE_COORDS.items():
            if _key in (_museum_venue_name or '').lower():
                _geocoded_coord = _coord
                print(f"  [T5] Venue coordinate from known database: {_geocoded_coord}")
                break
        
        # Fallback: try to extract from Wikipedia article (Wikidata coordinates)
        if not _geocoded_coord and _story_corpus_result:
            _wiki_text = _story_corpus_result.get('combined_text', '')
            # Look for coordinate patterns in Wikipedia articles
            _coord_match = re.search(r'(\d{2}\.\d{3,6})\s*[°]?\s*N.*?(\d+\.\d{3,6})\s*[°]?\s*E', _wiki_text)
            if _coord_match:
                _geocoded_coord = (float(_coord_match.group(1)), float(_coord_match.group(2)))
                print(f"  [T5] Venue coordinate from Wikipedia: {_geocoded_coord}")
        
        # [D4] Museum tours: use single venue coordinate for all interior stops
        if tour_category == 'museum' and _museum_venue_name:
            _venue_coord = _geocoded_coord if _geocoded_coord else first_poi_coordinates
            if _venue_coord and _venue_coord != (None, None):
                for p in poi_list:
                    p['coordinates'] = f"{_venue_coord[0]}, {_venue_coord[1]}"
                _source = "geocoded" if _geocoded_coord else "model (fallback)"
                print(f"  [D4] Museum single-coordinate: all stops set to {_venue_coord} (source: {_source})")

        # Print extracted POI information
        print("\n=== Extracted POI Information ===")
        for p in poi_list:
            print(f"{p['stop_number']}. {p['name']}")
            if p.get('address'):
                print(f"   Address: {p['address']}")
            if p.get('coordinates'):
                print(f"   Coordinates: {p['coordinates']}")
            if p.get('directions'):
                snippet = p['directions'][:80] + ('...' if len(p['directions']) > 80 else '')
                print(f"   Directions: {snippet}")
        print("================================\n")

    except ValueError as e:
        # Explicit zero-stop signal from PHASE 3C — always surface as error regardless of intent.
        # Must be caught BEFORE the generic Exception handler to prevent the last-resort
        # fallback from producing a 'completed' tour full of 'Location N' placeholders.
        print(f"X PHASE 3C rejected all stops: {e}")
        return None, None, (None, None)
    except Exception as e:
        print(f"Error in PHASE 3A/3B pipeline: {str(e)}")
        import traceback
        traceback.print_exc()
        if intent:
            poi_type = intent.get('poi_type', 'locations')
            print(f"X Unable to generate tour: Insufficient data available for {poi_type} in {location}.")
            return None, None, (None, None)
        # Last-resort fallback (no intent): keep behaviour for robustness
        for i in range(total_stops):
            poi_list.append({
                "stop_number": i + 1,
                "name": f"Location {i + 1}",
                "artist": "",
                "year": "",
                "directions": "",
                "coordinates": "",
                "description": "",
            })
    
    # -------- [S11] Storied: generate spine + fact sheets when STORIED_MODE=true --------
    _storied_spine = None
    _storied_fact_sheets = None
    _saved_prolog = ""  # [R2] Prolog text to be folded into Stop 1 (no standalone Introduction block)
    if _storied_mode:
        print(f"\n[Storied] STORIED_MODE=true — generating spine + fact sheets...")
        try:
            from spine_generator import generate_spine
            from fact_extractor import generate_fact_sheets_parallel

            _poi_names = [p["name"] for p in poi_list]
            _venue_name = (_museum_venue_name or location) if tour_category == 'museum' else location

            # [§3] Extract story elements before spine generation (if corpus available)
            _story_elements = []
            if _story_corpus_result and _story_corpus_result.get('pages'):
                try:
                    from story_element_extractor import extract_story_elements_from_pages, persist_story_elements
                    _story_elements = extract_story_elements_from_pages(
                        pages=_story_corpus_result['pages'],
                        venue_name=_venue_name,
                        api_key=api_key,
                        max_pages=5,
                    )
                    # Persist story elements
                    if _story_elements and output_file:
                        _elem_path = output_file.replace('.txt', '_story_elements.json')
                        persist_story_elements(_story_elements, _elem_path)
                except ImportError:
                    print(f"  [§3] story_element_extractor not available")
                except Exception as _se_err:
                    print(f"  [§3] Story element extraction error: {_se_err}")

            _storied_spine = generate_spine(
                venue_name=_venue_name,
                poi_list=_poi_names,
                tour_category=tour_category,
                api_key=api_key,
                theme_name="",
                story_elements=_story_elements if _story_elements else None,
            )
            if _storied_spine:
                print(f"  [Storied] Spine generated: {len(_storied_spine.get('arc', []))} arc entries (mode={_storied_spine.get('story_mode', '?')})")
            else:
                print(f"  [Storied] Spine generation failed — descriptions will proceed without spine")

            _storied_fact_sheets = generate_fact_sheets_parallel(
                poi_list=_poi_names,
                venue_name=_venue_name,
                tour_category=tour_category,
                api_key=api_key,
            )
            if _storied_fact_sheets:
                _valid_sheets = sum(1 for fs in _storied_fact_sheets if fs is not None)
                print(f"  [Storied] Fact sheets: {_valid_sheets}/{len(_poi_names)} generated")
            else:
                print(f"  [Storied] Fact sheet generation failed — descriptions will proceed without facts")
                _storied_fact_sheets = []
        except ImportError as e:
            print(f"  [Storied] Import error (spine/fact modules not available): {e}")
        except Exception as e:
            print(f"  [Storied] Error generating spine/facts: {e}")
    else:
        print(f"\n[Storied] STORIED_MODE=false — skipping spine + fact sheets")

    # -------- [S25] Storied: assign story types when STORIED_MODE=true --------
    if _storied_mode:
        try:
            from story_type_assigner import assign_story_types
            assign_story_types(poi_list, tour_category, persona=_persona_enum)
            _assigned_types = [p.get('story_type', '?') for p in poi_list]
            print(f"  [S25] Story types assigned: {_assigned_types}")
        except ImportError as e:
            print(f"  [S25] story_type_assigner not available: {e}")
        except Exception as e:
            print(f"  [S25] Error assigning story types: {e}")

    # PHASE 5: Generate detailed descriptions for each POI (parallelized)
    print(f"\nPHASE 5: Generating detailed descriptions for each POI (parallel)...")

    def _generate_description(args):
        idx, poi, spine_stop, fact_sheet, story_type = args
        stop_num = idx + 1
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]

        print(f"\nGenerating description for Stop {stop_num}: {poi_name} by {artist}, {year}...")

        description_prompt = f"""Create a detailed description for {poi_name} in a walking tour of {location} focusing on {tour_type}.

Start with an orientation section that explains where the visitor should position themselves to best view and appreciate this exhibit.

Then provide a detailed description of the exhibit that is EXACTLY 300 words long. Include:
- The artistic, historical, and cultural significance of the work
- Information about the artist and their creative process
- How this piece fits into the broader context of {tour_type}
- Interesting details that would engage visitors
"""

        # [S24] Storied: inject story-type tone + forbidden-phrase ban
        if story_type:
            try:
                import json as _st_json
                with open("story_type_taxonomy.json", "r", encoding="utf-8") as _st_f:
                    _taxonomy = _st_json.load(_st_f)
                _type_entry = next((t for t in _taxonomy["types"] if t["type"] == story_type), None)
                if _type_entry:
                    _tone_instruction = _type_entry.get("tone_instruction", "")
                    if _tone_instruction:
                        description_prompt = f"STYLE: {_tone_instruction}\n\n" + description_prompt
                    # Combine type-specific forbidden phrases with global FORBIDDEN_PHRASES
                    _type_forbidden = _type_entry.get("forbidden_phrases", [])
                    try:
                        from derepetition_guard import FORBIDDEN_PHRASES as _GLOBAL_FORBIDDEN
                        _global_phrases = [p.pattern for p in _GLOBAL_FORBIDDEN]
                    except ImportError:
                        _global_phrases = []
                    _all_forbidden = _type_forbidden + _global_phrases
                    if _all_forbidden:
                        description_prompt += f"\nDO NOT USE these phrases: {', '.join(_all_forbidden)}\n"
            except Exception as _st_err:
                print(f"  [S24] Story-type injection error (stop {stop_num}): {_st_err}")
        # [S9] Storied: inject spine context if provided
        if spine_stop:
            _emotional_beat = spine_stop.get('emotional_beat', '')
            _unique_angle = spine_stop.get('unique_angle', '')
            _cliffhanger = spine_stop.get('cliffhanger', '')
            _callback = spine_stop.get('callback', '')
            spine_block = f"""
NARRATIVE SPINE CONTEXT (use to shape your description):
- Emotional beat for this stop: {_emotional_beat}
- Unique angle to emphasize: {_unique_angle}"""
            if _callback:
                spine_block += f"\n- Callback to weave in: {_callback}"
            if _cliffhanger:
                spine_block += f"\n- End with a forward-looking hook: {_cliffhanger}"
            description_prompt += spine_block + "\n"

        # [S10] Storied: inject fact sheet if provided
        # [BLOCKER 2] Only inject facts marked as verified/confident.
        # Never assert artist attribution that isn't grounded for this specific POI.
        if fact_sheet:
            _confirmed = fact_sheet.get('confirmed_facts', [])
            _surprising = fact_sheet.get('surprising_detail', '')
            _attribution_ok = fact_sheet.get('attribution_confident', False)
            if _confirmed and _attribution_ok:
                facts_str = "; ".join(_confirmed[:5])
                description_prompt += f"""
VERIFIED FACTS (incorporate these for accuracy — these are confirmed for this specific POI):
{facts_str}
"""
            elif _confirmed:
                # Facts exist but attribution isn't confident — use as context, not as assertions
                facts_str = "; ".join(_confirmed[:3])
                description_prompt += f"""
CONTEXTUAL INFORMATION (use as background only — do NOT assert these as facts about this specific exhibit):
{facts_str}
"""
            if _surprising and _attribution_ok:
                description_prompt += f"""
MANDATORY INCLUSION — work this surprising detail into the description naturally:
{_surprising}
"""
        # [C5-1] Inject D1 venue corpus evidence as additional grounding
        if tour_category == 'museum' and _d1_venue_corpus and poi_name:
            import re as _c51_re
            _work_lower = poi_name.lower()
            # Extract sentences from venue corpus that mention this work's key words
            _key_words = [w for w in _work_lower.split() if len(w) >= 4 and w not in ('the','and','for')]
            if _key_words:
                _corpus_sentences = [s.strip() for s in _d1_venue_corpus.split('.') if any(kw in s.lower() for kw in _key_words)]
                if _corpus_sentences:
                    _grounded_facts = '. '.join(_corpus_sentences[:3])
                    description_prompt += f"\nGROUNDED FACTS FROM MUSEUM SOURCES (use these dates/details as MANDATORY content):\n{_grounded_facts}\n"
        
        # [§4] Story element injection — per-work facts from story_elements
        if tour_category == 'museum' and _story_corpus_result and poi_name:
            _per_work_ctx = _story_corpus_result.get('per_work_contexts', {})
            # Find matching work contexts
            _work_facts = []
            for _title, _sents in _per_work_ctx.items():
                from story_miner import _normalize
                if _normalize(poi_name)[:8] in _normalize(_title) or _normalize(_title)[:8] in _normalize(poi_name):
                    _work_facts.extend(_sents[:3])
            # Also use evidence snippet from D1
            if poi_name in _d1_evidence_log:
                _ev = _d1_evidence_log[poi_name]
                if isinstance(_ev, dict) and _ev.get('snippet'):
                    _work_facts.append(_ev['snippet'])
            if _work_facts:
                _facts_text = '. '.join(f[:200] for f in _work_facts[:4])
                description_prompt += f"\nDOCUMENTED FACTS FOR THIS WORK (incorporate at least one):\n{_facts_text}\n"

        # [B6] Scored story elements → generation wiring (per-status phrasing)
        # Reads ranked elements from work_stories cache and injects them with
        # status-appropriate instructions: documented→fact, reported→attribution,
        # legend→"the story goes…", disputed→both sides with sources.
        if tour_category == 'museum' and poi_name and artist:
            try:
                from work_story_searcher import normalize_work_key, work_stories_get
                from story_element_extractor import select_stop_elements
                _b6_work_key = normalize_work_key(poi_name, artist)
                _b6_cached = work_stories_get(_b6_work_key)
                if _b6_cached and _b6_cached.get('elements'):
                    _b6_selection = select_stop_elements(_b6_cached['elements'], max_selected=3)
                    _b6_selected = _b6_selection.get('selected_elements', [])
                    _b6_runners = _b6_selection.get('runner_up_elements', [])[:2]
                    if _b6_selected:
                        _b6_block = "\nSTORY ELEMENTS (use these as primary material, follow phrasing rules per status):\n"
                        for _elem in _b6_selected:
                            _status = _elem.get('corroboration_status', 'reported')
                            _text = _elem.get('text', '')[:200]
                            _etype = _elem.get('type', '')
                            if _status == 'documented':
                                _b6_block += f"  [FACT — state directly, no attribution needed] ({_etype}): {_text}\n"
                            elif _status == 'reported':
                                _src_domain = _elem.get('source_domain', 'sources')
                                _b6_block += f"  [REPORTED — use inline attribution: \"According to {_src_domain}...\"] ({_etype}): {_text}\n"
                            elif _status == 'legend':
                                _b6_block += f"  [LEGEND — frame as: \"The story goes that...\"] ({_etype}): {_text}\n"
                            elif _status == 'disputed':
                                _b6_block += f"  [DISPUTED — expose both sides with sources] ({_etype}): {_text}\n"
                            else:
                                _b6_block += f"  [{_status}] ({_etype}): {_text}\n"
                        if _b6_runners:
                            _b6_block += "  TEXTURE (weave in if natural):\n"
                            for _elem in _b6_runners:
                                _b6_block += f"    ({_elem.get('type','')}) {_elem.get('text','')[:120]}\n"
                        description_prompt += _b6_block
            except ImportError:
                pass
            except Exception as _b6_err:
                print(f"  [B6] Story element wiring error (stop {stop_num}): {_b6_err}")

        # Add venue containment constraint for single-venue museum tours
        if tour_category == 'museum' and _museum_venue_name:
            description_prompt += f"""
CRITICAL CONSTRAINT: This artwork/exhibit MUST be something that is physically on display at '{_museum_venue_name}'. Describe the ARTWORK itself — its visual qualities, technique, symbolism, and story. If you know which room or hall it's in, mention that briefly. If you don't know the exact room, do NOT fabricate one — just describe the work and tell the visitor to ask museum staff for its current location.
"""
            # [D5] No artist bio repetition in descriptions
            description_prompt += """
Do NOT repeat the artist's biographical background (birth year, nationality, school associations like 'École de Paris', artistic formats like 'stained glass and stage sets'). That information belongs in the tour introduction only. Here, focus EXCLUSIVELY on THIS SPECIFIC ARTWORK — what it depicts, its technique, its story, what to look for with your eyes.
"""
            # [Cycle 4] Ban forbidden cliché phrases that GPT overuses
            description_prompt += """
BANNED PHRASES — do NOT use any of these in your description:
- "vibrant colors" / "dreamlike imagery" / "dreamlike quality"
- "creative genius" / "artistic prowess" / "masterpiece that"
- "stir the soul" / "touch the heart" / "pulsate with life"
- "symphony of emotions" / "tapestry of dreams" / "weaves a narrative"
- "truly remarkable" / "a testament to" / "stands as a testament"
- "captivating artistry" / "mesmerizing world" / "intricate details"
- "invites you to explore/discover/reflect" / "immerse yourself in"
- "can't help but" / "feast for the eyes" / "step into a world"
Instead, use SPECIFIC, CONCRETE language: name colors precisely (cerulean, ochre, vermilion), describe actual compositional choices, mention documented historical context.
"""
            description_prompt += """
FACTUAL INTEGRITY RULE: Do NOT invent visual specifics or biographical claims not in the fact sheet above. You may describe the general biblical SUBJECT (e.g. "depicts the parting of the Red Sea") but do NOT assert specific visual details as facts (colors, composition) unless grounded in the facts above. Never call a work "the artist's final masterpiece" or similar unverifiable superlatives.
"""
            # [C5-5] Truthful framing for multi-work cycles
            if 'biblical message' in poi_name.lower() or 'message biblique' in poi_name.lower():
                description_prompt += """
NOTE: "The Biblical Message" (Message Biblique) is the name of the COMPLETE CYCLE of 17 large-scale paintings by Chagall, illustrating Genesis, Exodus, and the Song of Songs. Describe it as a cycle/series of paintings, NOT as a single painting. The museum was PURPOSE-BUILT to house this cycle (inaugurated 1973).
"""

        description_prompt += f"""
Format your response as follows:
Orientation: [Brief orientation text explaining the best viewing position]

[Detailed 300-word description of the exhibit]

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
"""

        # [PALAIS-FIX B1] Hedged narration for unverified stops
        if not poi.get('verified', True):
            description_prompt += """
IMPORTANT: This artwork's presence at this venue has NOT been independently verified.
Use hedged phrasing: "attributed to...", "believed to be on display...", "reportedly features...".
Do NOT state the work's presence as certain fact.
"""

        # [S43] Storied: inject persona tone override into description prompt
        if _storied_mode and _persona_tone:
            description_prompt += f"""
NARRATIVE TONE: Write this description with a {_persona_tone} tone — emphasize aspects that would appeal to someone with this sensibility.
"""

        description_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
                {"role": "user", "content": description_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }

        try:
            description_response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(description_data)
            )

            if description_response.status_code == 200:
                description_result = description_response.json()
                description_text = description_result["choices"][0]["message"]["content"]

                tokens_used = description_result["usage"]["total_tokens"]
                call_cost = tokens_used / 1000 * 0.002
                print(f"Stop {stop_num} API call cost: ${call_cost:.4f} ({tokens_used} tokens)")

                parts = description_text.split("Orientation:", 1)
                if len(parts) > 1:
                    orientation_text = parts[1].strip()
                    description_parts = orientation_text.split("\n\n", 1)
                    if len(description_parts) > 1:
                        orientation = description_parts[0].strip()
                        description = description_parts[1].strip()
                    else:
                        orientation = orientation_text
                        description = ""
                else:
                    orientation = "Position yourself directly in front of the exhibit for the best view."
                    description = description_text.strip()

                word_count = len(description.split())
                print(f"Stop {stop_num} description word count: {word_count} words")
                return idx, orientation, description, word_count, tokens_used, call_cost
            else:
                print(f"Stop {stop_num} error: API returned status code {description_response.status_code}")
                return idx, "Position yourself directly in front of the exhibit for the best view.", f"[Description for {poi_name} could not be generated.]", 0, 0, 0.0

        except Exception as e:
            print(f"Stop {stop_num} error: {str(e)}")
            return idx, "Position yourself directly in front of the exhibit for the best view.", f"[Description for {poi_name} could not be generated.]", 0, 0, 0.0

    max_workers = min(len(poi_list), 5)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # [S9/S10/S11] Pass spine_stop and fact_sheet per stop (None when not in Storied mode)
        _spine_arc = _storied_spine.get("arc", []) if _storied_mode and _storied_spine else []
        _fact_sheets_list = _storied_fact_sheets if _storied_mode and _storied_fact_sheets else []
        futures = {}
        for i, poi in enumerate(poi_list):
            spine_stop = _spine_arc[i] if i < len(_spine_arc) else None
            fact_sheet = _fact_sheets_list[i] if i < len(_fact_sheets_list) else None
            story_type = poi.get('story_type')
            futures[executor.submit(_generate_description, (i, poi, spine_stop, fact_sheet, story_type))] = i
        for future in as_completed(futures):
            idx, orientation, description, word_count, tokens_used, call_cost = future.result()
            poi_list[idx]["orientation"] = orientation
            poi_list[idx]["description"] = description
            poi_list[idx]["word_count"] = word_count
            total_tokens += tokens_used
            total_cost += call_cost
    
    # -------- PHASE 5.5: post-description validation for museum tours --------
    # Fix 4 (Claude session 7): second validate_enhanced_poi_knowledge() call for ALL tour types.
    # At this point descriptions are populated — the fictional-content patterns now have text to match.
    print(f"\nPHASE 5.5a: Post-description knowledge validation (all tour types)...")
    knowledge_valid2, knowledge_message2 = validate_enhanced_poi_knowledge(poi_list, intent, location)
    if not knowledge_valid2:
        print(f"X Post-description validation failed: {knowledge_message2}")
        return None, None, (None, None)
    print(f"OK Post-description validation passed: {knowledge_message2}")

    if tour_category == 'museum' and _museum_venue_name:
        print(f"\nPHASE 5.5b: Validating descriptions are inside '{_museum_venue_name}'...")
        poi_list = _validate_museum_stop_descriptions(poi_list, _museum_venue_name, headers)
        # Stop 0 is always kept by _validate_museum_stop_descriptions, so len >= 1
        print(f"OK PHASE 5.5b: {len(poi_list)} stop(s) passed venue description validation")

    # PHASE 5.6: Geographic-scope containment — only when the museum guard did NOT run
    if not (tour_category == 'museum' and _museum_venue_name):
        # Use geographic_scope if precision is tight enough (BUILDING or DISTRICT)
        _scope_for_check = ''
        if intent and intent.get('geographic_scope') and intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT', 'CORRIDOR'):
            _scope_for_check = intent['geographic_scope']
        if _scope_for_check:
            _before = len(poi_list)
            print(f"\nPHASE 5.6: Validating stops are within '{_scope_for_check}'...")
            poi_list = _validate_stops_within_scope(poi_list, _scope_for_check, headers)
            print(f"OK PHASE 5.6: {len(poi_list)}/{_before} stop(s) within scope")
            if len(poi_list) <= max(1, _before // 2):
                print(f"  [PHASE 5.6] >50% of stops were outside '{_scope_for_check}' — "
                      f"scope is likely a small single venue; delivering {len(poi_list)} verified stop(s).")

    # PHASE 6: Assemble the complete tour
    print(f"\nPHASE 6: Assembling the complete tour...")
    
    # Create a better title that doesn't duplicate information
    if tour_type.lower() in location.lower():
        # If tour type is already in the location name, don't repeat it
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        # Otherwise, create a title that incorporates the tour type naturally
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"
    
    complete_tour = tour_title + "\n" + f"Tour-Category: {tour_category}" + "\n\n"

    # -------- [PROLOG] Storied: prepend journey prolog --------
    if _storied_mode and _storied_spine:
        try:
            _connecting_thread = _storied_spine.get("connecting_thread", "")
            _tour_hook = _storied_spine.get("tour_hook", "")
            _arc = _storied_spine.get("arc", [])
            _chapter_previews = []
            for entry in _arc[:5]:  # Preview first 5 chapters max
                role = entry.get("chapter_role", "")
                angle = entry.get("unique_angle", "")
                if role and angle:
                    _chapter_previews.append(f"{role}: {angle}")
            
            _prolog_prompt = f"""Write a compelling 80-150 word tour introduction that frames this experience as a journey — a book of connected chapters.

Theme/connecting thread: {_connecting_thread}
Tour hook: {_tour_hook}
Chapter previews: {'; '.join(_chapter_previews)}

Requirements:
- Write in second-person present tense ("You are about to embark...")
- Name the journey's central theme/goal
- Preview how the stops connect into one arc (each reveals a different facet)
- Make it read like a book's opening page — compelling, with a sense of discovery
- 80-150 words exactly
- Do NOT end with a question
- Return ONLY the paragraph, no quotes or labels"""

            import requests as _prolog_requests
            _prolog_resp = _prolog_requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You write immersive, literary audio tour introductions."},
                        {"role": "user", "content": _prolog_prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 300,
                },
                timeout=15,
            )
            if _prolog_resp.status_code == 200:
                _prolog_text = _prolog_resp.json()["choices"][0]["message"]["content"].strip()
                if _prolog_text.startswith('"') and _prolog_text.endswith('"'):
                    _prolog_text = _prolog_text[1:-1].strip()
                # [R2] Do NOT emit standalone Introduction block — save for Stop 1
                _saved_prolog = _prolog_text
                print(f"  [R2] Prolog saved for Stop 1 ({len(_prolog_text.split())} words)")
            else:
                # Fallback to simple hook
                if _tour_hook:
                    _saved_prolog = _tour_hook
                    print(f"  [R2] Prolog fallback (hook) saved for Stop 1")
        except Exception as e:
            print(f"  [PROLOG] Error: {e}")
            if _storied_spine.get("tour_hook"):
                _saved_prolog = _storied_spine['tour_hook']

    # Add each POI with its description and directions
    for i, poi in enumerate(poi_list):
        stop_num = i + 1   # always sequential; ignore whatever AI emitted
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]
        orientation = poi.get("orientation", "Position yourself to best view this location.")
        # Strip any "Stop N:" prefix the AI may have echoed into the orientation text
        orientation = re.sub(r'^Stop\s+\d+:\s*', '', orientation, count=1, flags=re.IGNORECASE).strip()
        if not orientation:
            orientation = "Position yourself to best view this location."
        # [D6] Museum tours: strip ALL fabricated navigation from Orientation
        if tour_category == 'museum' and _museum_venue_name:
            orientation = re.sub(r'(?i)\b(head|walk|turn|continue|proceed)\s+(north|south|east|west|northeast|northwest|southeast|southwest)\b[^.]*\.?\s*', '', orientation)
            orientation = re.sub(r'(?i)\b(on|along|down)\s+\w+\s+(street|avenue|road|boulevard|ave|st|rd|blvd)\b[^.]*\.?\s*', '', orientation)
            # [C5-3] Kill distance-based fabricated directions
            orientation = re.sub(r'(?i)(walk|head|go)\s+(straight\s+)?(ahead\s+)?for\s+\d+\s*m(eters?|\.?)\b[^.]*\.?\s*', '', orientation)
            orientation = re.sub(r'(?i)then\s+turn\s+(left|right)\b[^.]*\.?\s*', '', orientation)
            orientation = re.sub(r'(?i)(the\s+)?destination\s+will\s+be\b[^.]*\.?\s*', '', orientation)
            orientation = re.sub(r'(?i)start\s+at\s+the\s+main\s+entrance\b[^.]*\.?\s*', '', orientation)
            orientation = orientation.strip() or "Position yourself to best view this artwork."
        description = poi.get("description", f"[Description for {poi_name} could not be generated.]")
        
        # Format the POI header
        poi_header = f"Stop {stop_num}: {poi_name}"
        if artist and artist.lower() != "unknown artist":
            poi_header += f" by {artist}"
        if year:
            poi_header += f", {year}"
        
        # [F3] Header assertion: ensure GPT hasn't injected flowery text into the name field
        _expected_header_start = f"Stop {stop_num}: {poi['name']}"
        if not poi_header.startswith(_expected_header_start):
            print(f"  [F3] ⚠️ HEADER MISMATCH at stop {stop_num}:")
            print(f"    Expected start: '{_expected_header_start}'")
            print(f"    Got: '{poi_header}'")
            # Force-correct the header to the clean version
            poi_header = _expected_header_start
            if artist and artist.lower() != "unknown artist":
                poi_header += f" by {artist}"
            if year:
                poi_header += f", {year}"
        # Also assert the name itself is a short noun phrase (no sentences/descriptions)
        if len(poi_name.split()) > 15 or any(c in poi_name for c in '.!?;'):
            print(f"  [F3] ⚠️ NAME TOO LONG/CORRUPT at stop {stop_num}: '{poi_name[:80]}'")
            # Truncate to first 12 words if corrupted
            _clean_name = ' '.join(poi_name.split()[:12]).rstrip('.,;:!?')
            poi_header = f"Stop {stop_num}: {_clean_name}"
            if artist and artist.lower() != "unknown artist":
                poi_header += f" by {artist}"
            if year:
                poi_header += f", {year}"
        
        # Start the POI content with all extracted information
        poi_content = poi_header + "\n\n"
        
        # Add address if available
        if poi.get("address"):
            poi_content += f"Address: {poi['address']}\n\n"
        
        # Add coordinates if available
        # Museum tours with a single venue: first stop only (all exhibits in same building)
        # Museum tours with DIFFERENT coordinates per stop: every stop (multiple buildings)
        # All other tours: every stop (different geo locations need map pins)
        if tour_category == 'museum':
            # Check if stops have different coordinates (multi-building "museum" like libraries)
            all_coords = [p.get("coordinates") for p in poi_list if p.get("coordinates")]
            unique_coords = set(all_coords)
            is_single_building = len(unique_coords) <= 1
            coords_eligible = (i == 0) if is_single_building else True
        else:
            coords_eligible = True
        if coords_eligible and poi.get("coordinates"):
            poi_content += f"Coordinates: {poi['coordinates']}\n\n"
        
        # Add type/specialty if available
        if poi.get("type_specialty"):
            poi_content += f"Type/Specialty: {poi['type_specialty']}\n\n"
        
        # Add specific examples if available
        if poi.get("specific_examples"):
            poi_content += f"Specific Examples: {poi['specific_examples']}\n\n"
        
        # [D7] Museum: operational details only on first stop
        if tour_category == 'museum' and _museum_venue_name:
            if i == 0 and poi.get("operational_details"):
                poi_content += f"Museum Information: {poi['operational_details']}\n\n"
        else:
            if poi.get("operational_details"):
                poi_content += f"Operational Details: {poi['operational_details']}\n\n"
        
        print(f"  DEBUG - POI {stop_num} content includes:")
        print(f"    Specific Examples: {bool(poi.get('specific_examples'))}")
        print(f"    Operational Details: {bool(poi.get('operational_details'))}")
        print(f"    Walking Directions: {bool(poi.get('directions'))}")
        
        # Add orientation section
        poi_content += "Orientation: "
        if i == 0:
            # For the first POI, include directions from the entrance
            # [C5-3] Museum tours: skip fabricated entrance directions entirely
            if tour_category != 'museum' or not _museum_venue_name:
                entrance_directions = poi.get("directions", "")
                if entrance_directions:
                    poi_content += entrance_directions + " "
        
        # Add the orientation text — [R3] only if substantive (museum tours)
        if tour_category == 'museum' and _museum_venue_name:
            # R3: Orientation only if it contains a grounded viewing note
            _has_substance = bool(re.search(
                r'(?i)(mosaic|reflected|window|pond|corner|ceiling|floor|left wall|right wall|'
                r'lower|upper|behind|above|below|stained glass|tapestry|sculpture)',
                orientation
            ))
            if _has_substance and orientation != "Position yourself to best view this artwork.":
                poi_content += f"Orientation: {orientation}\n\n"
            # else: skip orientation entirely — go straight to description
        else:
            poi_content += f"Orientation: {orientation}\n\n"
        
        # [R2] For Stop 1: inject prolog before description
        if i == 0 and _saved_prolog:
            poi_content += f"{_saved_prolog}\n\n"
        
        # Add description
        poi_content += description + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(poi_list) - 1:
            next_poi = poi_list[i + 1]
            
            # [T4] DETERMINISTIC TRANSITION TEMPLATES — no LLM content in transitions
            # This eliminates the splice-corruption bug class entirely
            if tour_category == 'museum' and _museum_venue_name:
                # Museum tours: rotating deterministic templates with venue name (satisfies venue coherence)
                _transition_templates = [
                    f"Continue exploring {_museum_venue_name} — proceed to {next_poi['name']}.",
                    f"Your next stop at {_museum_venue_name}: {next_poi['name']}. Ask museum staff for directions.",
                    f"Proceed to {next_poi['name']}, also here at {_museum_venue_name}.",
                    f"Next in {_museum_venue_name}'s collection: {next_poi['name']}.",
                ]
                _transition = _transition_templates[i % len(_transition_templates)]
            else:
                # Walking tours: use generated directions if available
                directions = next_poi.get("directions", "")
                if _storied_mode:
                    try:
                        from directions_generator import generate_walking_directions
                        _storied_directions = generate_walking_directions(poi_name, next_poi['name'], location, api_key)
                        if _storied_directions:
                            directions = _storied_directions
                    except (ImportError, Exception):
                        pass
                if directions and directions.strip():
                    _transition = directions.strip()
                else:
                    _transition = f"Continue to {next_poi['name']}."
            
            poi_content += f"\nDirections: {_transition}\n\n"
            print(f"  [T4] Transition to Stop {stop_num+1}: {_transition[:60]}...")
        else:
            # For the last POI — EPILOG when Storied, generic conclusion when Beta
            if _storied_mode and _storied_spine:
                # [G4] Build epilog ONLY from deterministic content + documented story elements
                # Do NOT use spine's closing_revelation (may contain fabricated claims)
                _poi_names = [p["name"] for p in poi_list]
                _recap_list = ", ".join(_poi_names[:-1]) + f", and {_poi_names[-1]}" if len(_poi_names) > 1 else _poi_names[0]
                
                epilog = f"\n\nAs this journey comes to a close, reflect on the path you've taken — from {_poi_names[0]} through to here at {poi_name}. "
                
                # Use ONLY documented story elements for closing facts (never GPT-generated spine text)
                if _story_elements:
                    _closing_facts = [e.get('text', '') for e in _story_elements 
                                     if e.get('type') in ('date', 'superlative', 'turning_point') and e.get('text')]
                    if _closing_facts:
                        _fact = _closing_facts[0]
                        epilog += _fact + " "
                
                epilog += f"\n\nYou've experienced {_recap_list} — each a chapter in a story that only reveals its full meaning when read together."
                epilog += f"\n\nIf you'd like to explore more, consider generating another tour — perhaps a different perspective on this same place, or a new destination entirely. The next journey awaits."
                
                poi_content += epilog
                
                # [R1] Sources line — credit found stories
                if _story_corpus_result and _story_corpus_result.get('source_urls'):
                    _src_urls = _story_corpus_result['source_urls']
                    _src_domains = set()
                    for u in _src_urls:
                        from urllib.parse import urlparse as _up
                        _domain = _up(u).netloc
                        if _domain:
                            _src_domains.add(_domain)
                    if _src_domains:
                        _sources_text = ", ".join(sorted(_src_domains))
                        poi_content += f"\n\nSources: This tour draws on information from {_sources_text} and the Wikipedia article on the museum."
                
                print(f"  [EPILOG] Journey epilog added to last stop")
            else:
                # Beta: standard conclusion
                if tour_type.lower() in location.lower():
                    conclusion = f"Thank you for joining this tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
                else:
                    conclusion = f"Thank you for joining this {tour_type} tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
                poi_content += conclusion
        
        # Add to complete tour
        complete_tour += poi_content + "\n\n"
    
    # [D2] Strip GPT self-references to "Stop N" in description bodies
    if _storied_mode:
        import re as _d2_re
        # Split into stop blocks, clean description text only (not headers)
        _d2_lines = complete_tour.split('\n')
        _d2_cleaned = []
        for _line in _d2_lines:
            # Don't touch headers (lines starting with "Stop N:")
            if _d2_re.match(r'^Stop\s+\d+:', _line):
                _d2_cleaned.append(_line)
            else:
                # Replace self-referential "Stop N" with context-appropriate text
                _d2_cleaned.append(_d2_re.sub(r'\bStop\s+\d+\b', 'this work', _line))
        complete_tour = '\n'.join(_d2_cleaned)

    # -------- [S27] Storied: post-assembly de-repetition check --------
    if _storied_mode:
        try:
            from derepetition_guard import check_cross_stop_repetition
            _rep_pairs = check_cross_stop_repetition(complete_tour)
            if _rep_pairs:
                for pair in _rep_pairs:
                    print(f"REPETITION WARN: Stop {pair.get('stop_a','')} and Stop {pair.get('stop_b','')} share near-identical sentence (sim={pair.get('similarity',0):.2f})")
                print(f"  [S27] {len(_rep_pairs)} repetition pair(s) found (log only, no rewrite)")
                # [S29] Auto-rewrite flagged repetitions (cap at 10)
                _rewrite_count = 0
                _MAX_REWRITES = 10
                if _rep_pairs and _rewrite_count < _MAX_REWRITES:
                    try:
                        from derepetition_guard import rewrite_repeated_sentence
                        for pair in _rep_pairs[:_MAX_REWRITES]:
                            _sentence_b = pair.get('sentence_b', '')
                            _stop_b = pair.get('stop_b', '')
                            _story_type_b = ''  # Get from poi_list if available
                            for p in poi_list:
                                if str(p.get('stop_number', '')) == str(_stop_b):
                                    _story_type_b = p.get('story_type', '')
                                    break
                            if _sentence_b:
                                _rewritten = rewrite_repeated_sentence(_sentence_b, f"Stop {_stop_b}", _story_type_b, api_key)
                                if _rewritten and _rewritten != _sentence_b:
                                    # [D2] Scoped replacement: only within the target stop's block
                                    import re as _d2_re_inner
                                    _stop_blocks = _d2_re_inner.split(r'(Stop \d+:)', complete_tour)
                                    _replaced = False
                                    _rebuilt = []
                                    for _bi, _block in enumerate(_stop_blocks):
                                        if not _replaced and _sentence_b in _block:
                                            # Check this is the right stop block
                                            _prev_header = _stop_blocks[_bi - 1] if _bi > 0 else ''
                                            if f"Stop {_stop_b}:" in _prev_header or f"Stop {_stop_b}:" in _block:
                                                _block = _block.replace(_sentence_b, _rewritten, 1)
                                                _replaced = True
                                        _rebuilt.append(_block)
                                    if _replaced:
                                        complete_tour = ''.join(_rebuilt)
                                    else:
                                        # Fallback: if block matching failed, do scoped replace
                                        complete_tour = complete_tour.replace(_sentence_b, _rewritten, 1)
                                    _rewrite_count += 1
                                    print(f"REPETITION FIXED: Stop {_stop_b} sentence rewritten")
                        if _rewrite_count > 0:
                            print(f"  [S29] {_rewrite_count} sentence(s) rewritten")
                    except ImportError:
                        print(f"  [S29] rewrite_repeated_sentence not available — skipping rewrites")
                    except Exception as _rw_err:
                        print(f"  [S29] Rewrite error: {_rw_err}")
            else:
                print(f"  [S27] No cross-stop repetition detected")
        except ImportError:
            print(f"  [S27] derepetition_guard not available — repetition check skipped")
        except Exception as e:
            print(f"  [S27] Repetition check error: {e}")

    # Print word count statistics
    print("\n=== Word Count Statistics ===")
    for poi in poi_list:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================\n")
    
    # Print total cost
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
    # -------- [S20] Storied: store in cache after successful generation --------
    if _storied_mode and complete_tour:
        _db_url = os.environ.get("DATABASE_URL")
        if _db_url:
            try:
                from tour_cache_layer1 import store_tour
                _spine_json_str = None
                if _storied_spine:
                    import json as _cache_json
                    _spine_json_str = _cache_json.dumps(_storied_spine)
                store_tour(location, tour_type, total_stops, complete_tour, _db_url, spine_json=_spine_json_str)
                print(f"CACHE STORE: {location} / {tour_type} / {total_stops}")
            except ImportError:
                pass
            except Exception as e:
                print(f"  [S20] Cache store error: {e}")

    # Save to file if output_file is provided
    if not output_file:
        # Create default filename based on location and tour type
        safe_location = ''.join(c if c.isalnum() else '_' for c in location)
        safe_tour_type = ''.join(c if c.isalnum() else '_' for c in tour_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{safe_location}_{safe_tour_type}_tour_{timestamp}.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(complete_tour)
    
    print(f"\nTour text generated successfully!")
    print(f"Saved to: {output_file}")
    
    # [C5-5] Persist D1 evidence JSON
    if _d1_evidence_log and output_file:
        import json as _ej
        _evidence_path = output_file.replace('.txt', '_evidence.json')
        try:
            with open(_evidence_path, 'w', encoding='utf-8') as _ef:
                _ej.dump(_d1_evidence_log, _ef, indent=2, ensure_ascii=False)
            print(f"  [C5-5] Evidence persisted: {_evidence_path}")
        except Exception as _ee:
            print(f"  [C5-5] Evidence persist error: {_ee}")

    # Show a preview
    preview_length = min(500, len(complete_tour))
    print(f"\nPreview of the generated tour:\n")
    print(complete_tour[:preview_length] + "...\n")
    
    return complete_tour, output_file, first_poi_coordinates

if __name__ == "__main__":
    print("=== Audio Tour Generator with Coordinates ===\n")
    
    # Get location
    location = input("Enter the location (e.g., 'deCordova Sculpture Park in Lincoln, MA'): ")
    if not location:
        location = "deCordova Sculpture Park in Lincoln, MA"
        print(f"Using default location: {location}")
    
    # Get tour type
    tour_type = input("Enter the tour focus (e.g., 'sculpture', 'architecture'): ")
    if not tour_type:
        tour_type = "sculpture"
        print(f"Using default tour focus: {tour_type}")
    
    # Get output file (optional)
    output_file = input("Enter output file name (press Enter for auto-generated): ")
    
    # Generate the tour text
    tour_text, output_file, coordinates = generate_tour_text(location, tour_type, output_file)
    
    print(f"First POI coordinates: {coordinates}")