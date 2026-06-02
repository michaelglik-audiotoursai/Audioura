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


def generate_tour_text(location, tour_type, output_file=None, total_stops=None):
    """
    Generate audio tour text using OpenAI API with geo coordinates.
    
    Args:
        location: Location for the tour
        tour_type: Type of tour (e.g., "sculpture", "architecture")
        output_file: File to save the tour text (optional)
        total_stops: Number of stops requested
    
    Returns:
        tuple: (tour_text, output_file, coordinates)
    """
    import api_call_logger
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
    
    # PHASE 1: Analyze user intent with AI
    print(f"\nPHASE 1: Analyzing tour intent with AI...")
    # BUG 2 FIX: Mobile app hardcodes tour_type="museum" for ALL requests.
    # Check whether LOCATION ALONE encodes the real category (e.g. "restaurant tour
    # in Newton, MA"). If so, suppress the mobile-injected tour_type so GPT doesn't
    # return museum cafes instead of standalone restaurants.
    # Passing "" as tour_type ensures the category comes only from the location string,
    # not from the (potentially wrong) mobile-supplied tour_type.
    _pre_category = _classify_tour_category(location, "")
    if _pre_category in ('restaurant', 'walking', 'specialized'):
        # Location string already encodes the real intent — don't prepend tour_type
        user_request = location
        print(f"  [Bug2Fix] tour_type='{tour_type}' suppressed for intent analysis (pre_category='{_pre_category}'); using location only")
    else:
        user_request = f"{tour_type} {location}"
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
            if (_interior and _scope
                    and _scope.strip().lower().rstrip('.').split()[-1] in _INSTITUTION_TAIL
                    and intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT')):
                intent['venue_name'] = _scope
                print(f"  [venue promotion] scope '{_scope}' promoted to venue_name "
                      f"(interior preposition + institutional noun)")
        
        # If PHASE 1 identified a specific venue AND the location string does not
        # explicitly request a non-museum tour type, force museum category.
        # Safety net (_EXPLICIT_NON_MUSEUM_TOUR_RE) prevents GPT-hallucinated venue_names
        # on "walking tour starting at X" / "restaurant tour near X" requests from
        # silently flipping the category. See S15 Claude review §3.
        if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location):
            tour_category = 'museum'
            print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
        else:
            if intent.get('venue_name'):
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
        if _museum_venue_name:
            _museum_venue_constraint = (
                f"\nCRITICAL CONSTRAINT — THIS IS A SINGLE-VENUE MUSEUM TOUR:\n"
                f"- ALL {total_stops} stops MUST be rooms, galleries, exhibits, or areas physically "
                f"located INSIDE '{_museum_venue_name}'.\n"
                f"- Do NOT suggest any other museums, institutions, or locations outside this building.\n"
                f"- Each stop name should be a specific gallery, room, exhibit, or collection within "
                f"'{_museum_venue_name}' (e.g. 'East Wing Gallery', 'Underground Railroad Exhibit').\n"
                f"- If you are unsure whether a specific exhibit currently exists at '{_museum_venue_name}', "
                f"use well-known permanent collections or named galleries that are verifiably part of this venue.\n"
                f"- NEVER fabricate exhibit names or claim exhibits exist that you cannot verify."
            )

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

    phase_3a_prompt = (
        f"You are a knowledgeable local guide for {location}.\n"
        f"List exactly {total_stops} specific, real, well-known {poi_type_hint} relevant to: {user_request}.\n\n"
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

        # -------- PHASE 3C: address-based location guard --------
        # Runs BEFORE Part C so rejected stops can be replaced by the replacement loop.
        # Museum tours with a single venue are skipped -- all stops are inside one building.
        if tour_category != 'museum' or not _museum_venue_name:
            location_rejects = [p for p in poi_list if not _address_matches_location(p.get('address', ''), location)]
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
                # Also apply PHASE 3C address check to replacements
                if tour_category != 'museum' or not _museum_venue_name:
                    survived = [p for p in survived if _address_matches_location(p.get('address', ''), location)]
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
    
    # PHASE 5: Generate detailed descriptions for each POI (parallelized)
    print(f"\nPHASE 5: Generating detailed descriptions for each POI (parallel)...")

    def _generate_description(args):
        idx, poi = args
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
        # Add venue containment constraint for single-venue museum tours
        if tour_category == 'museum' and _museum_venue_name:
            description_prompt += f"""
CRITICAL CONSTRAINT: Every stop MUST be a room, gallery, exhibit, or area physically located INSIDE '{_museum_venue_name}'. Do NOT include artifacts, collections, or rooms that are housed at any other institution, even if thematically related to the same person or topic. If '{poi_name}' is not actually inside '{_museum_venue_name}', describe what IS at that location within the venue instead.
"""

        description_prompt += f"""
Format your response as follows:
Orientation: [Brief orientation text explaining the best viewing position]

[Detailed 300-word description of the exhibit]

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
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
        futures = {executor.submit(_generate_description, (i, poi)): i for i, poi in enumerate(poi_list)}
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
        if intent and intent.get('geographic_scope') and intent.get('scope_precision', '').upper() in ('BUILDING', 'DISTRICT'):
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
        description = poi.get("description", f"[Description for {poi_name} could not be generated.]")
        
        # Format the POI header
        poi_header = f"Stop {stop_num}: {poi_name}"
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
        # Museum tours: first stop only (all exhibits in same building)
        # All other tours: every stop (different geo locations need map pins)
        coords_eligible = (tour_category == 'museum' and i == 0) or (tour_category != 'museum')
        if coords_eligible and poi.get("coordinates"):
            poi_content += f"Coordinates: {poi['coordinates']}\n\n"
        
        # Add type/specialty if available
        if poi.get("type_specialty"):
            poi_content += f"Type/Specialty: {poi['type_specialty']}\n\n"
        
        # Add specific examples if available
        if poi.get("specific_examples"):
            poi_content += f"Specific Examples: {poi['specific_examples']}\n\n"
        
        # Add operational details if available
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
            entrance_directions = poi.get("directions", "")
            if entrance_directions:
                poi_content += entrance_directions + " "
        
        # Add the orientation text
        poi_content += orientation + "\n\n"
        
        # Add description
        poi_content += description + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(poi_list) - 1:
            next_poi = poi_list[i + 1]
            directions = next_poi.get("directions", "")
            
            # Debug: Print the directions
            print(f"DEBUG - Directions for Stop {stop_num} to {stop_num+1}: '{directions}'")
            
            # Always include the standard phrase with the next stop name
            poi_content += f"Please resume the tour at {next_poi['name']} by following these directions: "
            
            # CRITICAL FIX: Use the CURRENT POI's directions to get TO the next POI
            # The directions should be stored in the NEXT POI but describe how to get there FROM current POI
            if directions and directions.strip() and "Continue to" not in directions:
                # Use the detailed walking directions provided by AI
                poi_content += directions.strip()
                print(f"  ✅ Using detailed walking directions: {directions[:50]}...")
            else:
                # Fallback to generic direction only if no detailed directions available
                poi_content += f"Continue to '{next_poi['name']}'."
                print(f"  ⚠️ Using generic directions - no detailed directions found")
        else:
            # For the last POI, add the conclusion
            if tour_type.lower() in location.lower():
                # If tour type is already in the location name, don't repeat it
                conclusion = f"Thank you for joining this tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            else:
                conclusion = f"Thank you for joining this {tour_type} tour of {location}. We hope you have enjoyed the journey through art, history, and nature, and that you leave inspired by the beauty and creativity that surrounds you."
            
            poi_content += conclusion
        
        # Add to complete tour
        complete_tour += poi_content + "\n\n"
    
    # Print word count statistics
    print("\n=== Word Count Statistics ===")
    for poi in poi_list:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================\n")
    
    # Print total cost
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
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