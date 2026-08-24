"""
Modified version of generate_tour_text.py that includes geo coordinates for the first stop
"""
import os
from cost_rates import llm_cost as _llm_cost

# Sixth "built and inert" defect (D131): a rule implemented, wired, and then
# skipped at runtime because the root module was not importable from whatever
# cwd the process happened to have. Put this file's own directory on sys.path
# so every sibling module resolves regardless of how we are invoked.
import sys as _sys, os as _os
_MODULE_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _MODULE_DIR not in _sys.path:
    _sys.path.insert(0, _MODULE_DIR)


# ──── [LOCAL-437] MODULE-SCOPE PREDICATE: checklist exemption from existence gate ────
# This predicate is the SINGLE source of truth for whether exhibition-sourced
# stops bypass the existence gate. Tests IMPORT this — do not re-type it.
def should_exempt_from_existence_gate(deterministic_fill_used: bool, exhibition_stops_source: str) -> bool:
    """Return True if stops should be exempt from the LOCAL-245 existence gate.

    The existence gate (LOCAL-245) verifies stops against independent web evidence
    (Wikipedia, Wikidata, OSM). For temporary exhibition works (livres d'artiste on
    loan), no such evidence exists — they are on the venue's own page and nowhere else.

    Checklist-derived stops are already grounded against the venue's exhibition page
    by LOCAL-372 (title_appears_in_page). That is a stricter, source-specific check
    for this class of work. The existence gate's independent-web requirement does not
    apply to them.

    The exemption covers: 'checklist', 'partial', 'prose_llm' sources.
    It does NOT cover: 'creator_filter', 'none', or non-deterministic paths.
    """
    return (
        deterministic_fill_used
        and exhibition_stops_source in ('checklist', 'partial', 'prose_llm')
    )


def check_part4_attribution(part4_text: str, stop_data: list) -> list:
    """Check that Part 4's '<fact> at <stop name>' attributions are correct.

    Part 4 is 1–2 sentences naming one fact from each of ≥2 stops, using the
    pattern "<fact> at <stop name>".  The correct scope is the attribution
    clause terminated by a preposition + stop name — NOT a fixed character
    window.

    Algorithm:
      1. Find every "at/of/in <stop name>" pattern in the text — these are
         explicit attribution markers that bind preceding facts to a location.
      2. Stop names appearing WITHOUT a preceding preposition are treated as
         fact content (e.g. "Moses and Monotheism" is a work title, not a
         location attribution).
      3. Each date is attributed to the NEXT attribution marker after it
         (since the Part 4 pattern is "<fact with date> at <stop>").  Dates
         after the last marker are attributed to that last marker's stop.
      4. For each date, verify it exists in the attributed stop's description.
         If it belongs to a different stop, report a misattribution.

    Returns a list of error strings (empty means pass).
    """
    import re as _re
    if not part4_text or not stop_data:
        return []

    _p4_lower = part4_text.lower()

    # Step 1: find "at/of/in <stop_name>" attribution markers
    _attribution_markers = []  # list of (prep_start, stop_name_end, stop_dict)
    for _s in stop_data:
        _sn_lower = _s['name'].lower()
        _pattern = r'\b(at|of|in)\s+' + _re.escape(_sn_lower)
        for _m in _re.finditer(_pattern, _p4_lower):
            _attribution_markers.append((_m.start(), _m.end(), _s))

    # Fallback: if no preposition-based markers found, locate stop names directly
    if not _attribution_markers:
        for _s in stop_data:
            _sn_lower = _s['name'].lower()
            _pos = _p4_lower.find(_sn_lower)
            if _pos != -1:
                _attribution_markers.append((_pos, _pos + len(_sn_lower), _s))

    if len(_attribution_markers) < 1:
        return []

    _attribution_markers.sort(key=lambda x: x[0])

    # Step 2: find all 4-digit year dates
    _all_dates = [(m.start(), m.group()) for m in _re.finditer(r'\b(\d{4})\b', _p4_lower)]

    _errors = []
    for _date_pos, _date_val in _all_dates:
        # Skip dates that fall inside a stop-name mention (part of the name itself)
        _inside_name = False
        for _mk_start, _mk_end, _ in _attribution_markers:
            if _mk_start <= _date_pos <= _mk_end:
                _inside_name = True
                break
        if _inside_name:
            continue

        # Attribute to the NEXT marker after the date (pattern: "<fact> at <stop>")
        _attributed_stop = None
        for _mk_start, _mk_end, _mk_stop in _attribution_markers:
            if _mk_start > _date_pos:
                _attributed_stop = _mk_stop
                break
        if _attributed_stop is None:
            # Date after all markers — attribute to last stop
            _attributed_stop = _attribution_markers[-1][2]

        # Verify: the date must appear in the attributed stop's description
        _attr_desc_lower = _attributed_stop['description'].lower()
        if _date_val not in _attr_desc_lower:
            # Is it in a DIFFERENT stop's description? (misattribution)
            _other_has_it = any(
                _date_val in other['description'].lower()
                for other in stop_data
                if other['name'] != _attributed_stop['name']
            )
            if _other_has_it:
                _errors.append(
                    f"FAIL: date '{_date_val}' attributed to "
                    f"'{_attributed_stop['name']}' but belongs to a different stop")

    return _errors


def should_inject_venue_snippet(exhibition_checklist_result, stop_name: str = '') -> dict:
    """Decide whether the venue's own page text should lead the verification snippet list.

    When the source is the venue itself (not a third-party review site), the
    venue page IS the authoritative source and its text should be the first
    verification snippet so claims grounded in it survive verification.

    Args:
        exhibition_checklist_result: The result object from find_exhibition_checklist.
            Must have: is_third_party (bool), page_text (str), content_url/exhibition_url (str).
        stop_name: Name of the stop (for logging/diagnostics).

    Returns:
        dict with keys:
            'inject': bool — whether to inject the venue snippet
            'snippet': dict|None — the snippet dict ready to prepend, or None
            'reason': str — why injection was or was not chosen
    """
    if not exhibition_checklist_result:
        return {'inject': False, 'snippet': None, 'reason': 'no exhibition_checklist_result'}

    if getattr(exhibition_checklist_result, 'is_third_party', False):
        return {'inject': False, 'snippet': None,
                'reason': 'source is third-party, not venue'}

    _page_text = getattr(exhibition_checklist_result, 'page_text', '') or ''
    if not _page_text or len(_page_text) <= 50:
        return {'inject': False, 'snippet': None,
                'reason': f'page_text too short ({len(_page_text)} chars)'}

    _url = (getattr(exhibition_checklist_result, 'content_url', '') or
            getattr(exhibition_checklist_result, 'exhibition_url', '') or '')

    _snippet = {
        'title': f"Venue Exhibition Page — {stop_name}" if stop_name else "Venue Exhibition Page",
        'snippet': _page_text[:5000],
        'url': _url,
    }

    return {'inject': True, 'snippet': _snippet,
            'reason': f'venue source, {len(_page_text)} chars from {_url}'}


def story_pass_model() -> str:
    """The model for the per-stop description call — the story pass only.

    D370: gpt-3.5 cannot sustain a sourced story (0-2 story sentences, gate
    FAILED); gpt-4o passes it. But setting TOUR_LLM_MODEL=gpt-4o globally makes
    the tour fail to generate outright — every phase reads that one variable,
    and gpt-4o read the POI-discovery prompt as "find art venues in Boston",
    six museums, which BLOCKER4b correctly rejected. The upstream phases are
    tuned to gpt-3.5's literalism, so the switch has to be exactly this narrow.
    """
    return os.environ.get("TOUR_STORY_MODEL", "gpt-4o")


def _tour_llm_cost(tokens: int, model: str = None) -> float:
    """Cost of a call at the model actually in use.

    LOCAL-197 moved rates into cost_rates.py; LOCAL-194 made the model runtime
    config. Both matter here: pricing a gpt-4o-mini call at gpt-3.5-turbo rates
    overstates our cost ~7x, and Subscribed charges the user 5x that number.

    D370 added `model`: the story pass runs on a different model from the rest
    of the pipeline, so its caller must pass the model it actually called.
    """
    return _llm_cost(total_tokens=tokens,
                     model=model or os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"))

import sys
import json
import time
import logging
import requests

# Module-level logger for ImportError reporting (LOCAL-63: never swallow ImportError silently)
_import_logger = logging.getLogger("generate_tour_text.imports")
if not _import_logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    _import_logger.addHandler(_h)
    _import_logger.setLevel(logging.DEBUG)
from concurrent.futures import ThreadPoolExecutor, as_completed
from enhanced_tour_templates_fixed import get_enhanced_tour_template, validate_enhanced_poi_knowledge
from poi_inclusion_exceptions import should_include_in_restaurant_tour, should_include_in_walking_tour
# NOTE: tour_type_detector.detect_tour_type() is intentionally NOT used here.
# The local _classify_tour_category() below (two-arg version returning lowercase category)
# serves a different purpose from the imported one (one-arg, returns CONTEXTUAL/OPERATIONAL).
from enhanced_prompt_generator import generate_enhanced_prompt
from datetime import datetime
import re
import unicodedata  # [LOCAL-372 LEAD] module scope — a function-scope import here
                    # would shadow the name for the whole function (D278)
from collections import Counter
from math import radians, sin, cos, asin, sqrt
from tour_settings import (
    WALKING_LEG_TARGET_KM, WALKING_LEG_HARD_KM, WALKING_TOTAL_HARD_KM,
    MAX_REPLACEMENT_ATTEMPTS,
)

# ---------------------------------------------------------------------------
# [LOCAL-324] Module-level helper: build the material/period patch sentence.
# Extracted so production and tests share one implementation (no reimplementation).
# ---------------------------------------------------------------------------

def _build_material_period_patch(material_english, period_english):
    """Build the patch sentence for missing material and/or period metadata.

    Args:
        material_english: English material name (str) if material is missing
                          from the description, else None.
        period_english:   English period string (str) if period is missing
                          from the description, else None.

    Returns:
        A grammatical standalone English sentence, or empty string if neither
        input is provided.

    Three reachable cases:
        both   -> "This work, crafted from {material}, dates from the {period}."
        mat    -> "This work was crafted from {material}."
        period -> "This work dates from the {period}."
    """
    if material_english and period_english:
        return f"This work, crafted from {material_english}, dates from the {period_english}."
    elif material_english:
        return f"This work was crafted from {material_english}."
    elif period_english:
        return f"This work dates from the {period_english}."
    return ""


# ---------------------------------------------------------------------------
# [LOCAL-330] Module-level helper: extract a clean place name from the raw
# location/request string for the prolog location slot.
#
# The request string has a known shape:
#   prefix: "<anything> tour (in|of|through|around|across|along|,) <place>"
#   suffix: "<place> <anything> tour"
#
# We anchor on the word "tour" followed by a preposition (or comma). This
# avoids a category-word list entirely (D236) — no list means no list to
# extend, no place names corrupted by matching category words inside them
# (Hyde Park, Central Park, Boat Quay, Garden District, etc.).
#
# "Tours, France" is safe: "Tours" is not followed by a preposition.
# "Tour Eiffel, Paris" is safe: "Tour" is not followed by a preposition.
# ---------------------------------------------------------------------------

# Prefix: "<anything> tour in Old Nice" → "Old Nice"
# Matches everything from the start up to and including "tour(s)" + preposition/comma.
# The key insight: require a preposition or comma AFTER "tour" — this is what
# distinguishes "dog sledding tour in Big Lake" from "Tours, France".
_PROLOG_TOUR_PREFIX_RE = re.compile(
    r'^.+?\btours?\s*'
    r'(?:in|of|through|around|across|along|,)\s*',
    re.IGNORECASE,
)

# Suffix: "Musée Matisse, Nice, France museum tour" → "Musée Matisse, Nice, France"
# Also handles dash-separated: "Big Lake, AK - Dog Sledding Tour" → "Big Lake, AK"
# Two shapes:
#   1. " - <anything> tour(s)" at end (dash separator — clear delimiter)
#   2. " <word> tour(s)" at end (single word before tour, like "museum tour")
# We limit the non-dash form to a single word to avoid eating into place names
# like "France" in "Nice, France museum tour".
_PROLOG_TOUR_SUFFIX_RE = re.compile(
    r'(?:'
    r'\s+-\s+.+?\btours?'   # " - Dog Sledding Tour"
    r'|'
    r'\s+\w+\s+tours?'      # " museum tour" (single word before tour)
    r')$',
    re.IGNORECASE,
)


def _prolog_place(location: str) -> str:
    """Derive a clean place name from a raw tour request string.

    The request string has a known construction:
        "<anything> tour (in|of|through|around|across|along|,) <place>"
    We anchor on 'tour' + preposition — no category-word list needed (D236).

    If no such prefix exists, try a trailing suffix form:
        "<place> - <words> tour" or "<place> <words> tour"

    If neither matches, the location is already a place name — return unchanged.

    Examples:
        "restaurant tour in Old Nice (Vieux Nice), France"
            → "Old Nice (Vieux Nice), France"
        "dog sledding tour in Big Lake, Alaska"
            → "Big Lake, Alaska"
        "food and wine tour of Tuscany"
            → "Tuscany"
        "Musée Matisse, Nice, France museum tour"
            → "Musée Matisse, Nice, France"
        "Hyde Park, London"
            → "Hyde Park, London"  (unchanged)
        "Tours, France"
            → "Tours, France"  (unchanged)
        "Tour Eiffel, Paris"
            → "Tour Eiffel, Paris"  (unchanged)
    """
    # Try prefix strip first
    stripped = _PROLOG_TOUR_PREFIX_RE.sub('', location, count=1)
    if stripped != location:
        stripped = re.sub(r'\s{2,}', ' ', stripped).strip().strip(',').strip()
        if not stripped:
            return location
        # After prefix strip, also try suffix (handles "tour, Place - Category Tour")
        further = _PROLOG_TOUR_SUFFIX_RE.sub('', stripped, count=1)
        if further != stripped:
            further = re.sub(r'\s{2,}', ' ', further).strip().strip(',').strip()
            if further:
                return further
        return stripped

    # Try suffix strip (no prefix matched)
    stripped = _PROLOG_TOUR_SUFFIX_RE.sub('', location, count=1)
    if stripped != location:
        stripped = re.sub(r'\s{2,}', ' ', stripped).strip().strip(',').strip()
        if stripped:
            return stripped
        return location

    # No prefix or suffix matched — location is already a place name
    return location


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
    r'|pub\s+crawl|bike|cycling|biking|shopping'
    r'|movie|film|book|literary|novel)'
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

# Transport mode detection — graduated distance tiers for non-walking tours
# (KIRO_REVIEW_07 + KIRO_REVIEW_08: replaces binary wide_area_transport with tiered modes)
_TRANSPORT_MODE_KEYWORDS = {
    'animal':  re.compile(r'\b(camel(?:back)?|horse(?:back)?|dog|dogsled(?:ding)?|sled\s*dog|mushing|husky)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
    'bike':    re.compile(r'\b(bike|biking|cycling)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
    'vehicle': re.compile(r'\b(auto|car|driving|jeep|off[- ]road|motorcycle|scooter)\b(?:\s+\w+)?\s*tour\b', re.IGNORECASE),
    'country_scale': re.compile(r'\broad\s*trip\b|\bcross[- ]country\b|\bsafari\b|\bnational(?:\s+parks?)?\s+tour\b', re.IGNORECASE),
}

# [LOCAL-46] Flat set of all transport-mode keywords for stripping from location strings.
# Derived from _TRANSPORT_MODE_KEYWORDS above — single source of truth, kept in sync.
# Includes walking/hiking variants that also pollute area resolution.
_TRANSPORT_STRIP_WORDS = {
    # From 'animal' mode
    'camel', 'camelback', 'horse', 'horseback', 'dog', 'dogsled', 'dogsledding',
    'sledding', 'mushing', 'husky',
    # From 'bike' mode
    'bike', 'biking', 'cycling',
    # From 'vehicle' mode
    'auto', 'car', 'driving', 'jeep', 'motorcycle', 'scooter',
    # From 'country_scale' mode (words that aren't geographic)
    'safari',
    # Walking/hiking variants (not in _TRANSPORT_MODE_KEYWORDS but same bug class)
    'walking', 'hiking', 'running',
    # Boat/water variants (future-proofing same pattern)
    'boat', 'kayak', 'kayaking', 'canoe', 'canoeing', 'sailing',
    # General
    'segway',
}
# Compiled regex for stripping transport words from location strings (word boundaries)
_TRANSPORT_STRIP_RE = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in sorted(_TRANSPORT_STRIP_WORDS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)

# Total route distance caps per transport mode (km)
_TRANSPORT_TOTAL_HARD_KM = {
    # 'on_foot' uses existing WALKING_TOTAL_HARD_KM constant
    'animal':   20,
    'bike':     120,   # [LOCAL-46] 30→120: regional biking tours (French Riviera) cover 80-100km
    'vehicle':  400,
    # 'country_scale' has no distance limit — uses containment check instead
}

# Country enclave table for country_scale containment validation
_COUNTRY_ENCLAVES = {
    'italy':        ['vatican city', 'san marino'],
    'south africa': ['lesotho'],
    'france':       ['monaco'],
    'spain':        ['andorra'],
    'switzerland':  ['liechtenstein'],
    'austria':      ['liechtenstein'],
}


# ============================================================
# [LOCAL-22] Name-corruption guard: reject GPT names that are
# sentences, descriptions, or contain meta-references.
# This is the ROOT-CAUSE fix — prevents corruption from entering
# poi_list rather than trying to sanitize it downstream.
# ============================================================
_NAME_CORRUPTION_INDICATORS = re.compile(
    r'(?i)'
    r'(?:'
    # Sentence-like openings: "Located at...", "This stop...", "Visit the..."
    r'^(located\s+at|situated\s+(at|in|on)|this\s+(stop|place|location|exhibit)|'
    r'visit\s+the|explore\s+the|discover\s+the|experience\s+the|'
    r'featuring\s|invites?\s+(visitors?|you)|offers?\s+(visitors?|a)|'
    r'showcasing\s|known\s+for\s|famous\s+for\s|home\s+to\s|'
    r'dedicated\s+to\s|a\s+(celebration|journey|tribute|showcase))'
    r'|'
    # Contains 'Stop N' self-reference (meta-reference)
    r"'Stop\s+\d+'|\"Stop\s+\d+\"|Stop\s+\d+\s+(invites?|offers?|features?|showcases?)"
    r')'
)

# Address fragment patterns that should never appear in a name
_ADDRESS_IN_NAME_RE = re.compile(
    r'(?i)'
    r'(?:'
    # Postal codes (French, US, UK, etc.)
    r'\b\d{5}\b'
    r'|'
    # Street-address patterns ("123 Main St", "405 Promenade")
    r'\b\d{1,5}\s+(rue|avenue|boulevard|promenade|street|road|drive|lane|place|way)\b'
    r'|'
    # "des Anglais" style French address fragments
    r'\bdes\s+[A-Z][a-zà-ú]+'
    r')'
)


def _is_name_corrupted(name):
    """Return True if a candidate POI name looks like a sentence/description
    rather than a clean entity name. Used to REJECT bad GPT outputs at ingestion.
    
    Criteria for corruption:
    1. Contains > 12 words (entity names are short noun phrases)
    2. Contains sentence punctuation (periods, semicolons) mid-string
    3. Matches known corruption patterns (sentence openings, meta-refs)
    4. Contains address fragments (postal codes, street numbers)
    """
    if not name:
        return True
    
    words = name.split()
    
    # Criterion 1: Too many words for an entity name
    if len(words) > 12:
        return True
    
    # Criterion 2: Contains sentence-terminating punctuation mid-string
    # (Allow commas for things like "The Starry Night, 1889" or apostrophes)
    # Strip trailing punctuation first — some names legitimately end with a period
    _inner = name.rstrip('.!?;')
    if any(c in _inner for c in '.!?;'):
        return True
    
    # Criterion 3: Matches sentence/description patterns
    if _NAME_CORRUPTION_INDICATORS.search(name):
        return True
    
    # Criterion 4: Contains address fragments
    if _ADDRESS_IN_NAME_RE.search(name):
        return True
    
    return False


def _detect_transport_mode(location):
    """Detect transport mode from location text (Layer 1 — keyword matching).
    Returns one of: 'animal', 'bike', 'vehicle', 'country_scale', or 'on_foot' (default)."""
    for mode, pattern in _TRANSPORT_MODE_KEYWORDS.items():
        if pattern.search(location):
            return mode
    return 'on_foot'


def _stop_in_country_scope(stop_address, country_scope):
    """Check if a stop's address is within the given country or its enclaves."""
    if not country_scope or not stop_address:
        return False
    target = country_scope.strip().lower()
    # Extract country from address (typically the last comma-separated part)
    parts = [p.strip().lower() for p in stop_address.split(',')]
    stop_country = parts[-1] if parts else ''
    if stop_country == target:
        return True
    return stop_country in _COUNTRY_ENCLAVES.get(target, [])


# Unusual transport modes that get the verification call (cost control — common modes skip it)
_UNUSUAL_TRANSPORT_MODES = {'animal'}


def _verify_transport_accessibility(poi_list, transport_mode, location, api_key):
    """For unusual transport modes only, ask a single cheap AI call which candidate
    stops are NOT plausibly reachable via the stated mode. Advisory: on any failure,
    keep all stops — never crash, never empty the tour."""
    if transport_mode not in _UNUSUAL_TRANSPORT_MODES:
        return poi_list  # no-op for common modes

    if not poi_list:
        return poi_list

    stop_list_str = "\n".join(f"- {p['name']} ({p.get('address', '')})" for p in poi_list)
    prompt = (
        f"These are candidate stops for a {transport_mode} tour in {location}.\n\n"
        f"Which of these stops would NOT be plausibly reachable as part of a {transport_mode} route "
        f"(e.g. inside a building, a shopping mall or paved commercial district, a resort/hotel, "
        f"or a location that would realistically require a car to reach)?\n\nStops:\n{stop_list_str}\n\n"
        "Return ONLY a JSON array of the stop names to EXCLUDE. Empty array [] if all stops are fine."
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                "messages": [
                    {"role": "system", "content": "You return ONLY a valid JSON array. No markdown, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 200,
            },
            timeout=15,
        )
        if response.status_code == 200:
            excluded_names = json.loads(response.json()["choices"][0]["message"]["content"])
            if excluded_names:
                print(f"  [TRANSPORT-VERIFY] Excluding {len(excluded_names)} stop(s) not reachable by {transport_mode}: {excluded_names}")
                excluded_set = set(n.lower() for n in excluded_names)
                return [p for p in poi_list if p['name'].lower() not in excluded_set]
            else:
                print(f"  [TRANSPORT-VERIFY] All stops OK for {transport_mode}")
    except Exception as e:
        print(f"  [TRANSPORT-VERIFY] Verification failed (advisory, keeping all stops): {e}")
    return poi_list  # fail permissively


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


def _compute_route_order(poi_list):
    """[LOCAL-7] Compute a deterministic walking-route order using nearest-neighbor + 2-opt.
    
    Uses real Wikidata P625 coordinates for verified stops; falls back to GPT-guessed
    coordinates for unverified ones. Stops with no usable coordinates keep their
    relative position. Returns the reordered list (new list, does not mutate input).
    
    Graceful no-op: returns input unchanged if <3 stops have coordinates.
    """
    # Extract coordinates for each stop
    coords = []
    for i, poi in enumerate(poi_list):
        lat = poi.get('latitude') or poi.get('wikidata_lat')
        lng = poi.get('longitude') or poi.get('wikidata_lng')
        # Fallback: parse 'coordinates' string field (GPT-generated)
        if not lat or not lng:
            parsed = _parse_coords(poi.get('coordinates', ''))
            if parsed:
                lat, lng = parsed
        if lat and lng and (float(lat) != 0.0 or float(lng) != 0.0):
            coords.append((i, (float(lat), float(lng))))
        else:
            coords.append((i, None))
    
    # Separate stops with coordinates from those without
    with_coords = [(idx, c) for idx, c in coords if c is not None]
    without_coords = [idx for idx, c in coords if c is None]
    
    # Need at least 3 stops with coordinates for routing to matter
    if len(with_coords) < 3:
        print(f"  [ROUTE-ORDER] Only {len(with_coords)} stops with coordinates — skipping algorithmic routing")
        return poi_list
    
    # --- Nearest-neighbor ---
    n = len(with_coords)
    # Start from the stop closest to the centroid (reasonable starting point)
    centroid_lat = sum(c[0] for _, c in with_coords) / n
    centroid_lng = sum(c[1] for _, c in with_coords) / n
    centroid = (centroid_lat, centroid_lng)
    
    # Find starting stop: closest to centroid
    start_idx = min(range(n), key=lambda i: _haversine_km(with_coords[i][1], centroid))
    
    visited = [False] * n
    order = [start_idx]
    visited[start_idx] = True
    
    for _ in range(n - 1):
        current = order[-1]
        current_coord = with_coords[current][1]
        best_next = None
        best_dist = float('inf')
        for j in range(n):
            if not visited[j]:
                d = _haversine_km(current_coord, with_coords[j][1])
                if d < best_dist:
                    best_dist = d
                    best_next = j
        if best_next is not None:
            order.append(best_next)
            visited[best_next] = True
    
    # --- 2-opt improvement ---
    def _route_distance(route):
        total = 0.0
        for i in range(len(route) - 1):
            total += _haversine_km(with_coords[route[i]][1], with_coords[route[i+1]][1])
        return total
    
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                new_order = order[:i] + order[i:j+1][::-1] + order[j+1:]
                if _route_distance(new_order) < _route_distance(order):
                    order = new_order
                    improved = True
    
    # Map back to original poi_list indices
    ordered_indices = [with_coords[o][0] for o in order]
    
    # Insert stops without coordinates: place each one between its nearest neighbors
    # in the ordered list (simple heuristic: maintain their relative position among
    # the coordinate-bearing stops they were between in the original list)
    if without_coords:
        # Place each no-coord stop right after the last coord-stop that preceded it in the original order
        result_indices = list(ordered_indices)
        for nc_idx in without_coords:
            # Find the last coord-bearing stop before nc_idx in the original order
            insert_after = None
            for oi in range(nc_idx - 1, -1, -1):
                if oi in ordered_indices:
                    # Find position of oi in result_indices
                    insert_after = result_indices.index(oi)
                    break
            if insert_after is not None:
                result_indices.insert(insert_after + 1, nc_idx)
            else:
                # No preceding coord stop — insert at beginning
                result_indices.insert(0, nc_idx)
    else:
        result_indices = ordered_indices
    
    # Build reordered list
    reordered = [poi_list[i] for i in result_indices]
    
    # Log the routing result
    total_dist = _route_distance(order)
    print(f"  [ROUTE-ORDER] Computed route for {len(with_coords)} stops with coords "
          f"({len(without_coords)} without): {total_dist:.2f}km total")
    
    return reordered


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


def strip_llm_json_fences(text: str) -> str:
    """Strip markdown code fences and surrounding prose from an LLM response.

    LLMs (especially GPT-4o) intermittently wrap JSON in ```json ... ``` fences
    or embed it in conversational prose.  This function extracts the JSON payload
    so that json.loads succeeds regardless of wrapping.

    Strategy:
      1. If the text already starts with '{' or '[', return as-is (no stripping needed).
      2. Strip ```json or ``` fences (single or triple backtick variants).
      3. If that still doesn't yield leading '{'/']', try to find the first '{' or '['
         and return from there to the matching last '}' or ']'.
    """
    stripped = text.strip()

    # Fast path: already valid JSON start
    if stripped and stripped[0] in ('{', '['):
        return stripped

    # Strip triple-backtick fences: ```json\n...\n``` or ```\n...\n```
    import re as _re
    fence_pattern = _re.compile(
        r'^```(?:json|JSON)?\s*\n?(.*?)\n?\s*```\s*$',
        _re.DOTALL
    )
    m = fence_pattern.search(stripped)
    if m:
        inner = m.group(1).strip()
        if inner and inner[0] in ('{', '['):
            return inner

    # Strip single-backtick wrapping (less common but observed)
    if stripped.startswith('`') and stripped.endswith('`'):
        inner = stripped.strip('`').strip()
        if inner and inner[0] in ('{', '['):
            return inner

    # Last resort: find the first { or [ and last } or ]
    first_brace = -1
    for i, ch in enumerate(stripped):
        if ch in ('{', '['):
            first_brace = i
            break

    if first_brace >= 0:
        # Find matching close
        open_ch = stripped[first_brace]
        close_ch = '}' if open_ch == '{' else ']'
        last_close = stripped.rfind(close_ch)
        if last_close > first_brace:
            return stripped[first_brace:last_close + 1]

    # Nothing worked — return original (json.loads will fail with a clear error)
    return stripped


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
    "scope_precision": "One of exactly these four strings: BUILDING (one structure) | CORRIDOR (one street or strip) | DISTRICT (a neighbourhood, quarter, square, or named area) | CITY (a whole town with no tighter anchor given).",
    "transport_mode": "How the visitor physically moves between stops. One of: on_foot (walking, default), animal (ANY animal-powered movement: camel, horseback, dog sled, elephant, donkey, husky, etc.), bike (cycling), vehicle (car, jeep, scooter, driving, or any motorized/robotic conveyance: segway, robot, drone-follow, golf cart), country_scale (road trip, cross-country, safari, national parks tour). Default: on_foot.",
    "country_scope": "If this is a country-scale tour (road trip, safari, cross-country, national parks), the country name (e.g. 'Italy', 'USA'). Null otherwise."
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
- "Camel tour in the desert of Abu Dhabi" → transport_mode: "animal", country_scope: null
- "Road trip across Italy" → transport_mode: "country_scale", country_scope: "Italy"
- "Horseback tour of the ranch trails, Wyoming" → transport_mode: "animal", country_scope: null
- "dog sledding tour near Big Lake, AK" → transport_mode: "animal", country_scope: null
- "robot riding tour of the tech campus" → transport_mode: "vehicle", country_scope: null
- "segway tour of Golden Gate Park" → transport_mode: "vehicle", country_scope: null
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
        "messages": [
            {"role": "system", "content": "You are a tour planning assistant. Respond only with valid JSON."},
            {"role": "user", "content": intent_prompt}
        ],
        "temperature": 0,  # Extraction task — zero variance for deterministic results
        "max_tokens": 400
    }
    
    # Retry on malformed JSON or null venue_name when request implies a venue
    # (LLM occasionally echoes schema text or declines to extract an obvious venue)
    _MAX_INTENT_RETRIES = 2
    _VENUE_INDICATOR_WORDS = {'museum', 'musée', 'musee', 'gallery', 'galleria', 'palais',
                              'palazzo', 'palace', 'castle', 'château', 'house', 'mansion',
                              'cathedral', 'basilica', 'library', 'institute', 'center',
                              'centre', 'villa', 'temple', 'church', 'abbey', 'priory'}
    _request_implies_venue = any(w in user_request.lower().split() for w in _VENUE_INDICATOR_WORDS)
    
    for _intent_attempt in range(_MAX_INTENT_RETRIES):
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
                # Strip markdown fences / surrounding prose (GPT-4o intermittently wraps JSON)
                cleaned_text = strip_llm_json_fences(intent_text)
                if cleaned_text != intent_text:
                    print(f"  [INTENT] Stripped LLM fences from response")
                parsed = json.loads(cleaned_text)
                
                # Check for null venue_name when request implies a venue
                if (_request_implies_venue and 
                    not parsed.get('venue_name') and
                    _intent_attempt < _MAX_INTENT_RETRIES - 1):
                    print(f"  [INTENT] venue_name=null but request implies a venue "
                          f"(attempt {_intent_attempt + 1}/{_MAX_INTENT_RETRIES}) — retrying")
                    continue  # Retry
                
                return parsed
            else:
                print(f"Intent analysis failed: {response.status_code}")
                return None
        except json.JSONDecodeError as e:
            print(f"Intent analysis JSON parse error (attempt {_intent_attempt + 1}/{_MAX_INTENT_RETRIES}): {e}")
            print(f"  [INTENT] Raw response that failed parse: {repr(intent_text)}")
            if _intent_attempt < _MAX_INTENT_RETRIES - 1:
                print(f"  Retrying intent analysis...")
                continue  # Retry
            return None
        except Exception as e:
            print(f"Intent analysis error: {e}")
            return None
    # If we get here without returning, all retries failed
    return None

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
        "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
        address = (poi.get('address', '') or '').strip()
        desc = (poi.get('description', '') or '')[:400]

        # [LOCAL-359] Include address in the judge prompt when available.
        # The address is authoritative — it was returned by Phase 3A alongside the name.
        address_line = ""
        if address:
            address_line = (
                f"Address (authoritative): {address}\n"
                f"NOTE: The address is a verified fact. If the address is clearly within "
                f"'{scope_name}', answer true regardless of what you recall about the name.\n"
            )

        prompt = (
            f"You are a geography fact-checker for location tours.\n"
            f"The tour must stay strictly within: '{scope_name}'.\n"
            f"Stop name: '{name}'\n"
            f"{address_line}"
            f"Description snippet:\n{desc}\n\n"
            f"Question: Is this stop physically located INSIDE or within the bounds of "
            f"'{scope_name}'? A stop that is in the same town but OUTSIDE '{scope_name}' "
            f"is NOT inside.\n"
            "Respond ONLY with valid JSON:\n"
            '{"inside_scope": true/false, "confidence": "high/medium/low", "reason": "<brief>"}'
        )
        data = {
            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
            # [LOCAL-359] Removal requires HIGH confidence. Rationale: removing a stop
            # is destructive and unrecoverable within the run (the tour simply gets
            # shorter). Keeping a marginal stop costs nothing — it's still a real place
            # in the general area. The Le Safari false-positive (medium confidence,
            # wrong answer) demonstrates that medium is not reliable enough for a
            # destructive action. Only high-confidence "outside" verdicts justify removal.
            if inside or conf in ("low", "medium"):
                survivors.append(poi)
                print(f"   OK '{poi['name']}' — inside '{scope_name}': {reason} (conf={conf})")
            else:
                print(f"   X SCOPE-CHECK REMOVED '{poi['name']}' — outside '{scope_name}': {reason} (conf={conf})")

    kept = [first_stop] + survivors + tail
    return kept


def _build_closing_recap(poi_list, ranked_facts_for_recap, api_key=None):
    """[LOCAL-280] Build a closing recap sentence from delivered tour content.

    The recap replaces any thank-you sentence. It states scale (stop count +
    total distance) then names real content chosen by the LOCAL-276 intrigue
    ranking. Every fact referenced must appear verbatim in its stop's delivered
    description — the D177 rule.

    Scaling (per Michael):
      2 stops:  both stops, briefly — one clause each
      3–5:     scale + top 2 by intrigue
      6+:      scale + top 2–3 by intrigue; never list every stop

    Composition (bounce 3 fix): An LLM call composes each recap item into a
    short clause (≤12 words) that names the stop and its fact. This replaces
    the regex extraction that produced truncated spans and dangling pronouns.
    The LLM may only rephrase — never add facts. D177 verification runs on
    the source fact; the composed clause is a faithful restatement.

    Args:
        poi_list: The list of POIs with 'name', 'description', coordinates.
        ranked_facts_for_recap: List of dicts from LOCAL-276 intrigue ranking,
            each with 'stop', 'best_fact', 'reason'. Only non-celebrity_trivia
            entries, sorted by intrigue priority.
        api_key: OpenAI API key for the composition call.

    Returns:
        str: The recap sentence, or "" if nothing can be verified.
    """
    from math import radians, sin, cos, asin, sqrt

    def _hav(a, b):
        lat1, lon1 = a; lat2, lon2 = b
        dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
        h = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * 6371.0 * asin(sqrt(h))

    # --- Count delivered stops (only those with real descriptions) ---
    # [LOCAL-379] Defect 3 fix: n_delivered (the count stated in "That's N stops")
    # must equal the number of Stop N: headings actually present in the tour.
    # A stop with a heading and thin content (e.g. post-grounding-gate) is still
    # a delivered stop. Only truly failed/empty stops are excluded.
    delivered = []
    content_rich = []  # Stops with enough content for recap highlight extraction
    for p in poi_list:
        desc = p.get('description', '')
        if (desc and not desc.startswith('[') and
            'GENERATION_FAILED' not in desc):
            delivered.append(p)
            if len(desc.split()) >= 30:
                content_rich.append(p)

    n_delivered = len(delivered)
    if n_delivered < 2:
        print("  [LOCAL-280] Recap: fewer than 2 delivered stops — skipped")
        return ""

    # --- Compute total route distance ---
    coords = []
    for p in delivered:
        lat = p.get('latitude') or p.get('wikidata_lat')
        lng = p.get('longitude') or p.get('wikidata_lng')
        if not lat or not lng:
            _cs = p.get('coordinates', '')
            _m = re.match(r'\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)', _cs or '')
            if _m:
                lat, lng = float(_m.group(1)), float(_m.group(2))
        if lat and lng:
            coords.append((float(lat), float(lng)))

    total_km = 0.0
    if len(coords) >= 2:
        for i in range(len(coords) - 1):
            total_km += _hav(coords[i], coords[i + 1])

    # --- Select facts by intrigue ranking ---
    # Verify each ranked fact actually appears in its stop's delivered text.
    verified_highlights = []
    _d177_rejected = 0
    _nav_rejected = 0

    # [LOCAL-280 bounce 4] Import navigation detector — navigation sentences are
    # never recap facts. R1 *exempts* navigation from imperative checks, so
    # check_r1_imperatives cannot catch them. We must reject explicitly.
    from style_validator_detector import _is_style_navigation_sentence as _is_nav_sentence

    # Collect all delivered stop names for the cross-stop naming guard.
    _all_stop_names = [p['name'].lower() for p in delivered]

    if ranked_facts_for_recap:
        for rf in ranked_facts_for_recap:
            rf_stop = rf.get('stop', '')
            rf_fact = rf.get('best_fact', '')
            rf_reason = rf.get('reason', '')
            if not rf_stop or not rf_fact:
                continue

            # [LOCAL-280 bounce 4] NAVIGATION FILTER — reject Directions text.
            # _is_style_navigation_sentence catches verb+directional patterns.
            # Also reject broader imperative navigation starts that the sentence-
            # level detector may miss (e.g. "Pedal from X to Y" without a
            # canonical directional word).
            if _is_nav_sentence(rf_fact):
                _nav_rejected += 1
                print(f"  [LOCAL-280] Recap: NAVIGATION rejected for '{rf_stop}': "
                      f"\"{rf_fact[:80]}...\"")
                continue
            # Broader catch: first word is a transport/route verb
            _first_word = rf_fact.split()[0].lower().rstrip('.,;:') if rf_fact else ''
            if _first_word in ('head', 'turn', 'continue', 'proceed', 'walk',
                               'cycle', 'follow', 'cross', 'step', 'pedal',
                               'ride', 'bike', 'drive', 'hike', 'stroll',
                               'cruise', 'trot', 'gallop', 'start', 'set'):
                _nav_rejected += 1
                print(f"  [LOCAL-280] Recap: NAVIGATION (verb start) rejected for '{rf_stop}': "
                      f"\"{rf_fact[:80]}...\"")
                continue

            # [LOCAL-280 bounce 4] CROSS-STOP NAMING GUARD — a recap clause
            # credited to stop A must not name stop B. This catches cases where
            # a Directions sentence like "Cycle from A towards B" passes as a
            # fact for A but actually describes the route to B.
            _other_stops = [s for s in _all_stop_names if s != rf_stop.lower()]
            _fact_lower = rf_fact.lower()
            _names_other_stop = False
            for _other in _other_stops:
                if _other in _fact_lower:
                    _nav_rejected += 1
                    _names_other_stop = True
                    print(f"  [LOCAL-280] Recap: CROSS-STOP rejected for '{rf_stop}': "
                          f"names '{_other}' — \"{rf_fact[:80]}...\"")
                    break
            if _names_other_stop:
                continue

            # Find the matching delivered stop
            matched_poi = None
            for p in delivered:
                if p['name'].lower() == rf_stop.lower():
                    matched_poi = p
                    break
                # Fuzzy: check if stop name is contained
                if rf_stop.lower() in p['name'].lower() or p['name'].lower() in rf_stop.lower():
                    matched_poi = p
                    break
            if not matched_poi:
                print(f"  [LOCAL-280] Recap: stop '{rf_stop}' not found in delivered — skipped")
                continue
            # D177 verification: fact text must appear in the delivered description
            desc = matched_poi.get('description', '')
            # Normalize whitespace for comparison
            _norm_desc = ' '.join(desc.split())
            _norm_fact = ' '.join(rf_fact.split())
            if _norm_fact not in _norm_desc:
                # Try a shorter substring (first 60 chars) — the ranking may have
                # truncated the sentence slightly
                _short = _norm_fact[:60]
                if _short not in _norm_desc:
                    print(f"  [LOCAL-280] Recap: D177 FAILED for '{rf_stop}': fact not in delivered text")
                    print(f"    Fact: \"{rf_fact[:80]}...\"")
                    _d177_rejected += 1
                    continue
            verified_highlights.append({
                'stop': matched_poi['name'],
                'fact': rf_fact,
                'reason': rf_reason,
            })

    # --- Fallback: if ranking unavailable, extract key facts manually ---
    if not verified_highlights:
        # Pick from delivered stops: find sentences with dates or key events.
        from style_validator_detector import check_r1_imperatives as _check_r1
        for p in delivered:
            desc = p.get('description', '')
            sents = re.split(r'(?<=[.!?])\s+', desc.strip())
            _stop_candidates = 0
            for s in sents:
                if len(s) < 30:
                    continue
                # Skip imperatives and navigation
                if _check_r1(s):
                    continue
                # [LOCAL-280 bounce 4] Explicit navigation filter
                if _is_nav_sentence(s):
                    _nav_rejected += 1
                    continue
                _first_w = s.split()[0].lower().rstrip('.,') if s else ''
                if _first_w in ('head', 'turn', 'continue', 'proceed', 'walk',
                                'cycle', 'follow', 'cross', 'step', 'pedal',
                                'ride', 'bike', 'drive', 'hike', 'stroll',
                                'cruise', 'trot', 'gallop', 'start', 'set'):
                    _nav_rejected += 1
                    continue
                # [LOCAL-280 bounce 4] Cross-stop naming guard
                _other_stops_fb = [n for n in _all_stop_names
                                   if n != p['name'].lower()]
                _s_lower = s.lower()
                _skip_cross = False
                for _other in _other_stops_fb:
                    if _other in _s_lower:
                        _nav_rejected += 1
                        _skip_cross = True
                        break
                if _skip_cross:
                    continue
                # Accept: has a date, OR has a proper noun with a past-tense verb
                _has_date = bool(re.search(r'\b\d{3,4}\b', s))
                _has_event = bool(re.search(
                    r'\b(built|designed|destroyed|seized|founded|opened|'
                    r'constructed|completed|liberated|imprisoned|spent|'
                    r'became|arrived|transformed|painted|created)\b',
                    s, re.IGNORECASE))
                if _has_date or _has_event:
                    verified_highlights.append({
                        'stop': p['name'],
                        'fact': s.strip(),
                        'reason': 'dated_event' if _has_date else 'cause',
                    })
                    _stop_candidates += 1
                    if _stop_candidates >= 3:
                        break
            if len(verified_highlights) >= 8:
                break

    if not verified_highlights:
        print(f"  [LOCAL-280] Recap: no verifiable highlights found "
              f"({_d177_rejected} rejected by D177, {_nav_rejected} rejected as navigation) — skipped")
        return ""

    # --- Determine how many highlights to include ---
    if n_delivered == 2:
        max_highlights = 2
    elif n_delivered <= 5:
        max_highlights = 2
    else:
        max_highlights = min(3, len(verified_highlights))

    # Deduplicate by stop (one fact per stop)
    _seen_stops = set()
    _deduped = []
    for h in verified_highlights:
        if h['stop'] not in _seen_stops:
            _deduped.append(h)
            _seen_stops.add(h['stop'])
    verified_highlights = _deduped

    selected = verified_highlights[:max_highlights]

    # At 2 stops, we need both. If selected has fewer than 2 (e.g. ranking
    # only returned 1), fill from the other delivered stop.
    if n_delivered == 2 and len(selected) < 2:
        _covered = {h['stop'] for h in selected}
        for p in delivered:
            if p['name'] not in _covered and len(selected) < 2:
                # Grab a fact sentence from this stop
                desc = p.get('description', '')
                sents = re.split(r'(?<=[.!?])\s+', desc.strip())
                for s in sents:
                    if len(s) < 30:
                        continue
                    _has_date = bool(re.search(r'\b\d{3,4}\b', s))
                    _has_event = bool(re.search(
                        r'\b(built|designed|destroyed|seized|founded|opened|'
                        r'constructed|completed|liberated|imprisoned|spent|'
                        r'became|arrived|transformed|painted|created)\b',
                        s, re.IGNORECASE))
                    if _has_date or _has_event:
                        selected.append({
                            'stop': p['name'],
                            'fact': s.strip(),
                            'reason': 'dated_event' if _has_date else 'cause',
                        })
                        break

    # --- Build the recap sentence ---
    # Scale part: "That's N stops and X kilometres"
    _stop_word = "stop" if n_delivered == 1 else "stops"
    if total_km >= 1:
        scale_part = f"That's {n_delivered} {_stop_word} and {total_km:.0f} kilometres"
    else:
        scale_part = f"That's {n_delivered} {_stop_word}"

    # --- LLM COMPOSITION (bounce 3 fix) ---
    # One batched call composes all recap items into short clauses.
    # Each clause names its stop and the key fact, ≤12 words.
    # The LLM may only rephrase the supplied fact — never add.
    clauses = _compose_recap_clauses_llm(selected, api_key)

    if not clauses:
        print(f"  [LOCAL-280] Recap: composition call failed — skipped")
        return ""

    # --- Assemble the sentence ---
    def _lc_if_not_proper(s):
        """Lowercase first char if it's a common word (The/This/That/A/An/In/It)."""
        if not s:
            return s
        _lc_starts = ('The ', 'This ', 'That ', 'These ', 'Those ',
                      'It ', 'In ', 'A ', 'An ', 'Here')
        if any(s.startswith(p) for p in _lc_starts):
            return s[0].lower() + s[1:]
        return s

    if n_delivered == 2:
        if len(clauses) >= 2:
            content_part = f" — {clauses[0]} and {_lc_if_not_proper(clauses[1])}"
        elif len(clauses) == 1:
            content_part = f" — {clauses[0]}"
        else:
            content_part = ""
    else:
        if len(clauses) == 1:
            content_part = f" — including {_lc_if_not_proper(clauses[0])}"
        elif len(clauses) == 2:
            content_part = f" — {clauses[0]} and {_lc_if_not_proper(clauses[1])}"
        else:
            content_part = f" — {clauses[0]}, {_lc_if_not_proper(clauses[1])}, and {_lc_if_not_proper(clauses[2])}"

    recap = scale_part + content_part + "."

    # Print verification
    print(f"  [LOCAL-280] Recap built: {len(recap.split())} words, {len(clauses)} composed clauses"
          f" ({_d177_rejected} D177 rejected, {_nav_rejected} navigation rejected)")
    for i, h in enumerate(selected[:len(clauses)]):
        print(f"    [{h['stop']}] ({h['reason']}): \"{h['fact'][:80]}...\"")
        print(f"      → composed: \"{clauses[i]}\"")
    print(f"    D177 verified: all {len(selected[:len(clauses)])} source facts present in delivered text")

    return recap


def _compose_recap_clauses_llm(selected_highlights, api_key):
    """[LOCAL-280 bounce 3] Compose recap clauses via a single batched LLM call.

    Each recap item is composed into a short noun phrase (≤12 words) that names
    its stop and the key fact. The LLM may only rephrase the supplied fact —
    never add facts. This replaces the regex extraction that produced truncated
    spans and dangling pronouns.

    Like LOCAL-269's gloss call: same constraint (rephrase only), batched,
    single call.

    Args:
        selected_highlights: List of dicts with 'stop', 'fact', 'reason'.
        api_key: OpenAI API key.

    Returns:
        list[str]: Composed clauses (one per highlight), or [] on failure.
    """
    import time

    if not selected_highlights:
        return []

    if not api_key:
        print("  [LOCAL-280] Recap composition: no API key — using fallback")
        return _compose_recap_clauses_fallback(selected_highlights)

    # Build the prompt: one item per line, ask for short clauses
    _items_text = ""
    for i, h in enumerate(selected_highlights):
        _items_text += f"\n{i+1}. STOP: {h['stop']}\n   FACT: {h['fact']}\n"

    _compose_prompt = f"""You are composing a tour recap. For each item below, write ONE short clause
(maximum 12 words, no period) that names the stop and states the key fact.

RULES:
- The clause must name the stop so the listener knows which place is meant.
- The clause must be self-contained — no pronouns without antecedents (no "he", "she", "it" unless the referent is named in the same clause).
- Never truncate mid-phrase. Every clause must read as complete English.
- The stop name appears ONCE per clause, never twice.
- You may ONLY rephrase the supplied fact. Do NOT add facts, dates, or details that are not in the FACT line.
- Do NOT use imperatives ("Visit...", "Step into...", "Cycle along...").
- Shape examples:
  "the 1561 fort at Saint-Hospice on Paloma Beach"
  "the Carlton Hotel, designed by Charles Dalmas in 1913"
  "Èze Village, seized in 1543 and razed by Louis XIV"
  "the Mougins studio where Picasso spent his final years"
  "Villefranche-sur-Mer, founded as a free port"

ITEMS:{_items_text}
OUTPUT: Return one clause per line (no numbering, no bullet points, no periods). Same order as input."""

    _start = time.time()
    try:
        _resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                "messages": [
                    {"role": "system", "content": "You rephrase facts into short clauses. You never invent. You return plain text, one clause per line."},
                    {"role": "user", "content": _compose_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 300,
            },
            timeout=20,
        )
        _elapsed = time.time() - _start

        if _resp.status_code == 200:
            _result = _resp.json()
            _usage = _result.get("usage", {})
            _cost = (_usage.get("prompt_tokens", 0) / 1000 * 0.005) + \
                    (_usage.get("completion_tokens", 0) / 1000 * 0.015)
            _tokens = _usage.get("total_tokens", 0)
            print(f"  [LOCAL-280] Recap composition: {_elapsed:.1f}s, ${_cost:.4f}, {_tokens} tokens")

            _text = _result["choices"][0]["message"]["content"].strip()
            # Parse: one clause per line
            _lines = [ln.strip().rstrip('.') for ln in _text.split('\n') if ln.strip()]
            # Remove any numbering prefix (1. or 1) or bullet)
            _cleaned = []
            for ln in _lines:
                ln = re.sub(r'^\d+[\.\)]\s*', '', ln)
                ln = re.sub(r'^[-•]\s*', '', ln)
                ln = ln.strip().rstrip('.')
                if ln:
                    _cleaned.append(ln)

            if len(_cleaned) < len(selected_highlights):
                print(f"  [LOCAL-280] Recap composition: got {len(_cleaned)} clauses "
                      f"for {len(selected_highlights)} items — padding with fallback")
                # Pad with fallback clauses
                _fb = _compose_recap_clauses_fallback(selected_highlights[len(_cleaned):])
                _cleaned.extend(_fb)

            # Validate each clause:
            _valid = []
            for i, clause in enumerate(_cleaned[:len(selected_highlights)]):
                _words = clause.split()
                # Reject: >15 words, contains imperative start, or has no stop reference
                if len(_words) > 15:
                    clause = ' '.join(_words[:12]).rstrip('.,;')
                # Reject bare pronouns at start
                if re.match(r'^(?:he|she|it|they)\b', clause, re.IGNORECASE):
                    # Use fallback for this item
                    _fb_single = _compose_recap_clauses_fallback([selected_highlights[i]])
                    clause = _fb_single[0] if _fb_single else selected_highlights[i]['stop']
                # Reject imperatives
                _imp_starts = ('visit', 'step', 'cycle', 'walk', 'head',
                               'follow', 'cross', 'take', 'proceed', 'ride')
                if clause.split()[0].lower().rstrip('.,') in _imp_starts:
                    _fb_single = _compose_recap_clauses_fallback([selected_highlights[i]])
                    clause = _fb_single[0] if _fb_single else selected_highlights[i]['stop']
                _valid.append(clause)

            return _valid[:len(selected_highlights)]
        else:
            _elapsed = time.time() - _start
            print(f"  [LOCAL-280] Recap composition failed (HTTP {_resp.status_code}) "
                  f"after {_elapsed:.1f}s — using fallback")
            return _compose_recap_clauses_fallback(selected_highlights)

    except Exception as e:
        _elapsed = time.time() - _start
        print(f"  [LOCAL-280] Recap composition error: {e} ({_elapsed:.1f}s) — using fallback")
        return _compose_recap_clauses_fallback(selected_highlights)


def _compose_recap_clauses_fallback(selected_highlights):
    """Deterministic fallback when LLM is unavailable. Produces safe, minimal clauses.

    This is NOT the regex extraction from bounce 1/2. It produces the stop name
    only — deliberately minimal rather than risk truncation or dangling pronouns.
    Used only when: no API key, API exhausted, or network error.
    """
    clauses = []
    for h in selected_highlights:
        stop = h['stop']
        fact = h.get('fact', '')
        # Try to extract a date from the fact for minimal context
        _date = re.search(r'\b(\d{4})\b', fact)
        if _date:
            clauses.append(f"{stop} ({_date.group(1)})")
        else:
            clauses.append(stop)
    return clauses


def nearest_treat_to_any_stop(treat_rows, stop_points, radius_km):
    """[D519] The nearest treat standing within `radius_km` of any stop, or None.

    Pure, so it can be tested without a database — the reason it is out here
    rather than inline in the 4,000-line closing builder it serves.

    `treat_rows`   iterable of (name, lat, lng), straight off the `treats` table.
    `stop_points`  iterable of (stop_name, (lat, lng)).

    Returns `{'treat', 'stop', 'km'}` or None. A row with unparseable coordinates
    is skipped, never guessed at.
    """
    from math import radians, sin, cos, asin, sqrt

    def _h(a, b):
        lat1, lon1 = a; lat2, lon2 = b
        dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
        x = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * 6371.0 * asin(sqrt(x))

    best = None
    for _row in treat_rows or []:
        try:
            _tname, _tlat, _tlng = _row[0], float(_row[1]), float(_row[2])
        except (TypeError, ValueError, IndexError):
            continue
        for _sname, _sll in stop_points or []:
            try:
                d = _h((float(_sll[0]), float(_sll[1])), (_tlat, _tlng))
            except (TypeError, ValueError, IndexError):
                continue
            if d <= radius_km and (best is None or d < best['km']):
                best = {'treat': _tname, 'stop': _sname, 'km': d}
    return best


def _build_closing_offer(poi_list, tour_category, transport_mode, location, sentence_budget=3):
    """[LOCAL-273/275] Build a ≤3 sentence closing offer from verified data.

    Three sentences (Michael's spec, LOCAL-275 addendum):
      Sentence 1: A similar tour (same category) near the last stop — existence-verified.
      Sentence 2: Restaurant tour (verified in audio_tours) OR museum fallback,
                  with the Treat Page folded in **only when a real treat is within
                  `TREAT_PAGE_NEAR_KM` of a real stop** (D519 — it used to close
                  every tour unconditionally). Never claims savings exist — only
                  that the page shows *whether* there are any.
      Sentence 3: News articles capability.

    Every sentence here is optional. The closing may come back empty, and that is
    a correct outcome, not a degraded one.

    Returns: str (the closing text, may be empty if nothing verifies).
    Falls back to a one-sentence factual summary if neither part can be built.
    """
    from math import radians, sin, cos, asin, sqrt

    def _haversine(a, b):
        lat1, lon1 = a; lat2, lon2 = b
        dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
        h = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * 6371.0 * asin(sqrt(h))

    def _poi_latlng(_p):
        """(lat, lng) for one stop, or None. Same three sources, one place."""
        _la = _p.get('latitude') or _p.get('wikidata_lat')
        _ln = _p.get('longitude') or _p.get('wikidata_lng')
        if not _la or not _ln:
            _cm = re.match(r'\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)',
                           _p.get('coordinates', '') or '')
            if _cm:
                _la, _ln = _cm.group(1), _cm.group(2)
        try:
            return (float(_la), float(_ln)) if _la and _ln else None
        except (TypeError, ValueError):
            return None

    # Get last stop coordinates
    last_poi = poi_list[-1]
    _last_ll = _poi_latlng(last_poi)
    if not _last_ll:
        print("  [LOCAL-273] No coordinates for last stop — closing offer skipped")
        return ""
    last_lat, last_lng = _last_ll
    last_name = last_poi.get('name', '')
    all_stop_names = {p['name'].lower() for p in poi_list}

    # ─── Connect to DB for verification ─────────────────────────────────
    try:
        import psycopg2
        # Use the same connection logic as the generation pipeline:
        # VENUE_CACHE_DB_URL > DATABASE_URL > host defaults (localhost:5433)
        _co_db_url = os.environ.get('VENUE_CACHE_DB_URL',
                     os.environ.get('DATABASE_URL'))
        if not _co_db_url:
            # Host mode: construct from individual env vars (same as db_connection.py)
            _co_host = os.environ.get('DB_HOST', 'localhost')
            _co_port = os.environ.get('DB_PORT', '5433')
            _co_dbname = os.environ.get('DB_NAME', 'audiotours')
            _co_user = os.environ.get('DB_USER', 'admin')
            _co_password = os.environ.get('DB_PASSWORD', 'password123')
            _co_db_url = f"postgresql://{_co_user}:{_co_password}@{_co_host}:{_co_port}/{_co_dbname}"
        _co_conn = psycopg2.connect(_co_db_url, connect_timeout=5)
    except Exception as _co_err:
        print(f"  [LOCAL-273] DB connection failed: {_co_err} — closing offer skipped")
        return ""

    sentences = []

    # ─── Part 1: Similar tour nearby (same category) ────────────────────
    # Query stop_corpus for stops in the same geographic area that are NOT
    # already in this tour. Use coordinates to find the nearest verified one.
    try:
        _co_cur = _co_conn.cursor()
        # For outdoor tours (walking/biking), use 'French Riviera walking area' or similar
        # For museum tours, look for other museums in venue_corpus
        if tour_category == 'museum':
            # Find other museums nearby using city names in venue_name
            _co_cur.execute("""
                SELECT venue_name, qid FROM venue_corpus
                WHERE (LOWER(venue_name) LIKE '%musee%' OR LOWER(venue_name) LIKE '%museum%')
            """)
            _museum_rows = _co_cur.fetchall()
            best_museum = None
            best_dist = float('inf')
            # Known city coordinates for distance estimation
            _city_coords = {
                'nice': (43.7102, 7.2620),
                'antibes': (43.5804, 7.1251),
                'monaco': (43.7384, 7.4246),
                'cannes': (43.5528, 7.0174),
            }
            for mname, mqid in _museum_rows:
                if mname.lower() in all_stop_names:
                    continue
                # Skip the current venue (the one we're in)
                # Match by checking if the museum name overlaps with the location
                _mname_lower = mname.lower()
                _loc_lower_p1 = location.lower()
                # Don't suggest the same museum we just toured
                if any(w in _mname_lower for w in re.findall(r'[a-z]{5,}', _loc_lower_p1)
                       if w not in ('france', 'musee', 'museum')):
                    continue
                # Determine museum city
                museum_city = None
                if 'nice' in _mname_lower:
                    museum_city = 'nice'
                elif 'antibes' in _mname_lower:
                    museum_city = 'antibes'
                elif 'monaco' in _mname_lower:
                    museum_city = 'monaco'
                elif 'cannes' in _mname_lower:
                    museum_city = 'cannes'
                if museum_city and museum_city in _city_coords:
                    d = _haversine((last_lat, last_lng), _city_coords[museum_city])
                    if d < 50 and d < best_dist:
                        best_dist = d
                        best_museum = mname

            if best_museum:
                _museum_display = best_museum.split(',')[0].strip()
                sentences.append(
                    f"If you would like another museum tour, the {_museum_display} "
                    f"is {best_dist:.0f} kilometers from here."
                )
                print(f"  [LOCAL-273] Part 1 (museum similar): {_museum_display} ({best_dist:.0f} km)")
        else:
            # Outdoor tour: find a verified stop nearby that is NOT in this tour
            _co_cur.execute("""
                SELECT stop_title FROM stop_corpus
                WHERE LOWER(venue_name) LIKE '%riviera%'
                   OR LOWER(venue_name) LIKE '%nice%'
                   OR LOWER(venue_name) LIKE '%walking area%'
            """)
            _sc_rows = _co_cur.fetchall()
            # Also check canonical_titles from venue_corpus for geographic coords
            _co_cur.execute("""
                SELECT canonical_titles_json FROM venue_corpus
                WHERE LOWER(venue_name) LIKE '%riviera%'
                   OR LOWER(venue_name) LIKE '%nice%walking%'
            """)
            _vc_rows = _co_cur.fetchall()
            # Build a list of (name, lat, lng) from canonical_titles
            candidates = []
            for row in _vc_rows:
                if row[0]:
                    for t in row[0]:
                        if isinstance(t, dict) and t.get('name') and t.get('lat') and t.get('lng'):
                            lat, lng = float(t['lat']), float(t['lng'])
                            if (lat != 0.0 or lng != 0.0):
                                candidates.append((t['name'], lat, lng))
            # Also add stop_corpus titles (without coords — use Wikipedia geosearch later)
            _sc_names = {r[0] for r in _sc_rows}

            # Filter: must be verified (in stop_corpus), not already in tour
            best_offer = None
            best_dist = float('inf')
            for name, lat, lng in candidates:
                if name.lower() in all_stop_names:
                    continue
                if name.lower() == last_name.lower():
                    continue
                # Only offer stops that are in stop_corpus (existence-verified)
                name_in_corpus = any(
                    name.lower() == sc_n.lower() or sc_n.lower() in name.lower()
                    for sc_n in _sc_names
                )
                if not name_in_corpus:
                    continue
                d = _haversine((last_lat, last_lng), (lat, lng))
                # Offer something 5–60 km away (interesting distance for cycling/walking)
                if 3 < d < 60 and d < best_dist:
                    best_dist = d
                    best_offer = name

            if best_offer:
                # Determine mode label for the sentence
                if transport_mode == 'bike':
                    _mode_phrase = "a cycling tour"
                elif transport_mode == 'vehicle':
                    _mode_phrase = "a driving tour"
                elif transport_mode == 'animal':
                    _mode_phrase = "a tour"
                else:
                    _mode_phrase = "a walking tour"
                _dist_str = f"{best_dist:.0f} kilometers" if best_dist >= 2 else f"{best_dist*1000:.0f} meters"
                sentences.append(
                    f"{best_offer} is {_dist_str} from here — we can build {_mode_phrase} there."
                )
                print(f"  [LOCAL-273] Part 1 (similar): {best_offer} ({best_dist:.1f} km, verified in stop_corpus)")
            else:
                print("  [LOCAL-273] Part 1: no verified nearby stop found — omitted")

    except Exception as e:
        print(f"  [LOCAL-273] Part 1 error: {e}")

    # ─── Part 2: Restaurant tour (or museum fallback) + Treat Page ─────
    # [LOCAL-275] Michael's spec: "a recommendation restaurant tour, or visit a
    # museum (if there is one)" — restaurant preferred, museum fallback.
    # Treat Page folded in: "the Treat Page shows whether there are real savings
    # at local shops and restaurants around here."
    try:
        _co_cur = _co_conn.cursor()
        _part2_tour_clause = ""
        _part2_verified = False

        # Try restaurant tour first: check audio_tours for an existing restaurant
        # tour with coordinates near the last stop (proves capability).
        _co_cur.execute("""
            SELECT id, tour_name, lat, lng FROM audio_tours
            WHERE (LOWER(request_string) LIKE '%%restaurant%%'
                   OR LOWER(tour_name) LIKE '%%restaurant%%')
              AND lat IS NOT NULL AND lng IS NOT NULL
              AND is_test = false
        """)
        _restaurant_rows = _co_cur.fetchall()
        _best_restaurant = None
        _best_restaurant_dist = float('inf')
        for _rid, _rname, _rlat, _rlng in _restaurant_rows:
            d = _haversine((last_lat, last_lng), (float(_rlat), float(_rlng)))
            if d < 40 and d < _best_restaurant_dist:
                _best_restaurant_dist = d
                _best_restaurant = (_rid, _rname)

        if _best_restaurant:
            _part2_tour_clause = "If you would like to eat nearby we can build you a restaurant tour"
            _part2_verified = True
            print(f"  [LOCAL-275] Part 2 (restaurant): verified via audio_tours id={_best_restaurant[0]} "
                  f"'{_best_restaurant[1]}' ({_best_restaurant_dist:.1f} km from last stop)")
        else:
            # Fallback: museum tour (same logic as LOCAL-273)
            if tour_category != 'museum':
                _co_cur.execute("""
                    SELECT venue_name, qid FROM venue_corpus
                    WHERE (LOWER(venue_name) LIKE '%%musee%%' OR LOWER(venue_name) LIKE '%%museum%%')
                """)
                _nearby_museums = []
                _city_coords_p2 = {
                    'nice': (43.7102, 7.2620),
                    'antibes': (43.5804, 7.1251),
                    'monaco': (43.7384, 7.4246),
                    'cannes': (43.5528, 7.0174),
                }
                for mname, mqid in _co_cur.fetchall():
                    mname_lower = mname.lower()
                    museum_city = None
                    if 'nice' in mname_lower:
                        museum_city = 'nice'
                    elif 'antibes' in mname_lower:
                        museum_city = 'antibes'
                    elif 'monaco' in mname_lower:
                        museum_city = 'monaco'
                    elif 'cannes' in mname_lower:
                        museum_city = 'cannes'
                    if museum_city and museum_city in _city_coords_p2:
                        d = _haversine((last_lat, last_lng), _city_coords_p2[museum_city])
                        if d < 40:
                            _nearby_museums.append((mname, d))

                if _nearby_museums:
                    _nearby_museums.sort(key=lambda x: x[1])
                    _closest_museum = _nearby_museums[0][0]
                    _museum_display = _closest_museum.split(',')[0].strip()
                    _part2_tour_clause = f"If you would like to visit a museum, the {_museum_display} is nearby"
                    _part2_verified = True
                    print(f"  [LOCAL-275] Part 2 (museum fallback): {_museum_display} ({_nearby_museums[0][1]:.1f} km)")
                else:
                    print("  [LOCAL-275] Part 2: no restaurant or museum verified nearby")
            else:
                print("  [LOCAL-275] Part 2: museum tour category, no restaurant found nearby")

        # ─── [D519] Is there actually a treat near a stop? ────────────────
        #
        # Michael, 2026-08-24: **only mention the Treat Page if it is genuinely
        # near a stop of the tour, any tour type, and it must not be the
        # obligatory closing of every tour.**
        #
        # It was unconditional: every tour ever generated ended with it,
        # including the three-stop MFA tour whose nearest treat is in another
        # country. The sentence never claimed savings existed — but a listener
        # who opens the page on a promise and finds it empty has been sent
        # somewhere for nothing, and hearing the same sentence close every tour
        # is what made it read as an advertisement rather than an offer.
        #
        # Near ANY stop, not just the last: the app's own Treat Page is
        # location-aware (`treats_screen.dart` → `/treats-near/{lat}/{lng}`), and
        # a listener is at every stop in turn, not only at the end.
        #
        # FAILS CLOSED. No `treats` table, no coordinates, a query error — the
        # sentence is omitted. Silence costs nothing; an unbacked promise does.
        _treat_near = None
        try:
            _treat_radius_km = float(os.environ.get('TREAT_PAGE_NEAR_KM', '1.0'))
            _co_cur.execute("""
                SELECT ad_name, lat, lng FROM treats
                WHERE lat IS NOT NULL AND lng IS NOT NULL
            """)
            _treat_rows = _co_cur.fetchall()
            _stop_points = [(p.get('name', ''), _poi_latlng(p)) for p in poi_list]
            _stop_points = [(n, ll) for n, ll in _stop_points if ll]
            _treat_near = nearest_treat_to_any_stop(
                _treat_rows, _stop_points, _treat_radius_km)
            if _treat_near:
                print(f"  [D519] Treat Page: '{_treat_near['treat']}' is "
                      f"{_treat_near['km']:.2f} km from stop "
                      f"'{_treat_near['stop'][:40]}' — mention EARNED")
            else:
                print(f"  [D519] Treat Page: no treat within "
                      f"{_treat_radius_km:.1f} km of any of "
                      f"{len(_stop_points)} stop(s) ({len(_treat_rows)} treat(s) "
                      f"with coordinates) — mention OMITTED")
        except Exception as _tp_err:
            print(f"  [D519] Treat Page: proximity unverifiable "
                  f"({type(_tp_err).__name__}: {_tp_err}) — mention OMITTED")
            try:
                _co_conn.rollback()
            except Exception:
                pass

        _treat_clause = ("the Treat Page shows whether there are real savings at "
                         "local shops and restaurants around here"
                         if _treat_near else "")

        # Build sentence(s) for Part 2: tour clause + Treat Page.
        # The Treat Page is location-aware (treats_screen.dart calls /treats-near/{lat}/{lng}).
        # Never claim savings exist — only that the page shows *whether* there are any.
        #
        # [LOCAL-275/280] Sentence budget management:
        #   - sentence_budget=2 (recap present): merge Part 1 + Part 2 + Treat Page
        #     into ONE sentence so news still fits within the 2-sentence budget.
        #     Michael's spec: "the similar-tour offer and the capability offer,
        #     merged, with the Treat Page" = one sentence.
        #   - sentence_budget=3 (no recap): original logic —
        #     When Part 1 produced a sentence: combine Part 2 + Treat Page into ONE.
        #     When Part 1 is absent: split into TWO sentences.
        # [D519] Each of these four branches is now conditional on `_treat_clause`
        # being non-empty. When no treat is near a stop the tour offer stands on
        # its own, and when neither verifies Part 2 contributes nothing at all —
        # which is the point: no sentence is owed a place in the closing.
        _has_part1 = len(sentences) > 0
        if _part2_tour_clause:
            if sentence_budget <= 2 and _has_part1:
                # Tight budget: merge Part 1 (similar tour) into Part 2 + Treat Page
                # as a single sentence. Drop Part 1's standalone sentence and build
                # a combined one that mentions both offers.
                _part1_text = sentences.pop(0)  # Remove Part 1 standalone
                # Extract the destination from Part 1 for a brief mention
                _p1_dest_match = re.search(r'^(.+?)\s+is\s+\d+\s+kilomet', _part1_text)
                _p2_tail = f", and {_treat_clause}" if _treat_clause else ""
                if _p1_dest_match:
                    _p1_dest = _p1_dest_match.group(1)
                    sentences.append(
                        f"There is also a tour of {_p1_dest} nearby; "
                        f"{_part2_tour_clause[0].lower() + _part2_tour_clause[1:]}"
                        f"{_p2_tail}."
                    )
                else:
                    # Fallback: just use Part 2 (+ Treats) — drop Part 1 text
                    sentences.append(f"{_part2_tour_clause}{_p2_tail}.")
            elif _has_part1 or sentence_budget <= 2:
                # Combined: fits the budget alongside Part 1 + news
                sentences.append(
                    f"{_part2_tour_clause}"
                    f"{(', and ' + _treat_clause) if _treat_clause else ''}."
                )
            else:
                # Split: two sentences to fill the Part 1 gap
                sentences.append(f"{_part2_tour_clause}.")
                if _treat_clause:
                    sentences.append(_treat_clause[0].upper() + _treat_clause[1:] + ".")
            if _treat_clause:
                print(f"  [LOCAL-275/D519] Part 2: tour offer + Treat Page "
                      f"(treat verified {_treat_near['km']:.2f} km from a stop)")
            else:
                print("  [LOCAL-275/D519] Part 2: tour offer only — no treat near a stop")
        elif _treat_clause:
            # No tour verified — Treat Page alone, and only because a real treat
            # is standing next to a real stop.
            sentences.append(_treat_clause[0].upper() + _treat_clause[1:] + ".")
            print(f"  [LOCAL-275/D519] Part 2: Treat Page only, "
                  f"{_treat_near['km']:.2f} km from stop '{_treat_near['stop'][:40]}'")
        else:
            print("  [LOCAL-275/D519] Part 2: nothing verified — no tour offer, "
                  "no Treat Page")

        # News capability — always offer if the path exists on this branch
        # Verify: news_orchestrator_service.py exists and has /generate-news
        _news_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'news_orchestrator_service.py')
        if os.path.exists(_news_path):
            sentences.append(
                "We can also generate news articles for you to listen to on the way back."
            )
            print("  [LOCAL-275] Part 2 (news): news_orchestrator_service.py confirmed")
        else:
            print(f"  [LOCAL-275] Part 2: news path not found at {_news_path} — news offer omitted")

    except Exception as e:
        print(f"  [LOCAL-275] Part 2 error: {e}")

    # ─── Cap at sentence_budget ─────────────────────────────────────────
    if len(sentences) > sentence_budget:
        sentences = sentences[:sentence_budget]

    if sentences:
        result = " ".join(sentences)
        print(f"  [LOCAL-275] Closing offer: {len(sentences)} sentence(s)")
        return result

    # ─── Fallback: one-sentence factual summary ─────────────────────────
    # Tour should not end mid-thought. Summarize what was covered.
    _stop_names_str = " and ".join(p['name'] for p in poi_list[-2:]) if len(poi_list) >= 2 else poi_list[0]['name']
    fallback = f"This tour covered {_stop_names_str}."
    print(f"  [LOCAL-275] Closing offer fallback (no verification passed)")
    return fallback


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
            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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

    # [LOCAL-22 Fix A] D1v2-verified stops are NEVER deleted by the prose validator.
    # Authority hierarchy: corpus-verified evidence > GPT-3.5-turbo prose judgment.
    # Only unverified fills (verified=False explicitly) get sent to the GPT check.
    d1v2_verified = []
    unverified_candidates = []
    for p in candidates:
        if p.get('verified', True):  # True or absent = verified (D1v2 default)
            d1v2_verified.append(p)
        else:
            unverified_candidates.append(p)
    
    _n_verified_kept = len(d1v2_verified)
    _n_unverified_check = len(unverified_candidates)
    print(f"   Authority: {_n_verified_kept} D1v2-verified (kept unconditionally), "
          f"{_n_unverified_check} unverified (will check)")

    # Single-venue museum tours: verify EVERY unverified stop's description is inside the venue.
    if len(unverified_candidates) <= 12:
        suspect = list(unverified_candidates)
        clean = []
    else:
        # Fallback to name-based pre-filter only for unusually large tours (cost guard)
        suspect = [p for p in unverified_candidates if _is_suspect(p.get('name', ''))]
        clean = [p for p in unverified_candidates if not _is_suspect(p.get('name', ''))]
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

    # Reassemble in original order: stop 0 always first, then d1v2_verified + clean + checked survivors
    all_survivors = d1v2_verified + clean + checked_survivors
    all_survivors.sort(key=lambda p: poi_list.index(p))
    return [first_stop] + all_survivors


from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Module-level: populated on unresolvable clean-fail for structured error response
_LAST_CLEAN_FAIL_EVIDENCE = {}

# [B1b] Module-level: populated after successful generation with final poi_list (including verified flags)
_LAST_POI_LIST = []

# Module-level: populated after D1v2 verification with the computed tier
_LAST_VERIFICATION_TIER = ""

# [LOCAL-60] Module-level: populated after generation with cost breakdown
# Allows the service layer to read the cost without changing the function signature.
# Keys: total_cost, total_tokens, cache_hit, breakdown (dict with llm/tts/search)
_LAST_GENERATION_COST = {"total_cost": 0.0, "total_tokens": 0, "cache_hit": False, "breakdown": {}}

# ──────────────────────────────────────────────────────────────────────────────
def _sentences_removed_by_gates(before: str, after: str):
    """[LOCAL-474] Sentences present before the gate chain and absent after it.

    Module scope so it is testable without a key, a DB or a network — D421 bounced
    a task for exactly the opposite arrangement, where the only way to test a
    validator was to grep the source of the function it lived in.
    """
    from unsupported_claim_gate import _split_sentences
    kept = {s.strip() for s in _split_sentences(after or '')}
    return [s.strip() for s in _split_sentences(before or '')
            if s.strip() and s.strip() not in kept]


def _regate_prose(prose: str, poi: dict) -> str:
    """[LOCAL-474] Re-apply the DETERMINISTIC deletion gates to regenerated prose.

    Only the free, offline gates: the retry happens after the chain has run and
    will not run again, so anything it invents would otherwise ship ungated.
    Non-fatal throughout — a gate that errors must not lose the text.

    [LOCAL-477] The first version ran three gates — unsupported-claim, role-claim
    and temporal — because those were the three that had caught fabrications. That
    was too narrow, and run 3 proved it: the retried stop came back ending

        "What deeper meanings might lie beneath the vibrant hues of the lizard's
         feathers?"

    a rhetorical question, which the prompt forbids in capitals and which R2
    (PHASE 5.141) deletes — but R2 runs BEFORE the retry and never saw it. The
    retry was escaping every STYLE gate in the chain while being checked by the
    three FACT gates.

    The general principle, learned twice now: **anything that regenerates text
    after the chain must re-run the chain, not a favourite subset of it.** A retry
    is a new draft and deserves the same scrutiny as the first one.
    """
    if not prose or not prose.strip():
        return prose
    out = prose

    # Markdown leakage. The model emits "** " into prose that will be SPOKEN;
    # run 3 shipped an orientation beginning `** "Au Soleil du Plafond,"`.
    out = re.sub(r'\*{1,3}', '', out)
    out = re.sub(r'^\s*#{1,6}\s*', '', out, flags=re.MULTILINE)
    out = re.sub(r'[ \t]{2,}', ' ', out).strip()

    # R2 — rhetorical questions (PHASE 5.141).
    try:
        from style_validator_detector import apply_r2_to_description
        out, _r2_del, _ = apply_r2_to_description(out)
    except Exception:
        pass

    # Belt and braces: R2 works per paragraph, and the rule that matters most for
    # audio is that the stop must not END on a question.
    try:
        from unsupported_claim_gate import _split_sentences
        _sents = _split_sentences(out)
        while _sents and _sents[-1].rstrip().endswith('?'):
            _sents.pop()
        out = ' '.join(_sents).strip() or out
    except Exception:
        pass
    try:
        from unsupported_claim_gate import apply_unsupported_claim_gate
        out, _ = apply_unsupported_claim_gate(out, corpus_passages=[],
                                              api_key=None, model=None)
    except Exception:
        pass
    try:
        from stop_claim_audit import apply_role_claim_gate
        rec = {'publisher': poi.get('publisher', '') or '',
               'credit_line': poi.get('credit_line', '') or '',
               'artist': poi.get('artist', '') or ''}
        out, _ = apply_role_claim_gate(out, rec, poi.get('_corpus_text', '') or '')
    except Exception:
        pass
    try:
        from temporal_coherence_gate import check_temporal_coherence
        from unsupported_claim_gate import _split_sentences
        out = ' '.join(s for s in _split_sentences(out)
                       if not check_temporal_coherence(s))
    except Exception:
        pass
    return out.strip()


# [LOCAL-413] build_snippet_block — module-scope function for testability.
# Previously this logic was inlined in the per-stop prompt assembly loop.
# Lifted here so tests can assert on the returned string directly.
# ──────────────────────────────────────────────────────────────────────────────

def build_snippet_block(snippets, artist, specifics):
    """Build the prompt snippet block from ranked snippets, artist, and specifics.

    Parameters:
      snippets: list of dicts with 'title', 'snippet', 'url' keys (already ranked/capped)
      artist: full artist name (e.g. 'Joan Miró') — used for attribution rule
      specifics: list of candidate specifics strings (e.g. ['edition/number: 24/50', ...])

    Returns:
      str: the snippet injection block ready to append to the description prompt
    """
    block = "\nREFERENCE MATERIAL (retrieved from published sources — cite nothing these do not support):\n"
    for si, snip in enumerate(snippets, 1):
        s_title = snip.get('title', '')[:100]
        s_text = snip.get('snippet', '')[:250]
        block += f"  [{si}] {s_title}\n      {s_text}\n"

    if specifics:
        block += "\n━━━ CANDIDATE SPECIFICS (extracted from the snippets above) ━━━\n"
        for cs in specifics[:8]:
            block += f"  • {cs}\n"
        block += "━━━ END CANDIDATE SPECIFICS ━━━\n"

    _artist_surname = artist.split()[-1] if artist else ''

    block += """
STORY INSTRUCTION (LOCAL-407/412/419):
Use the reference material above. Your text MUST include at least TWO of the following NAMED FIELDS if the snippets provide them:

  1. DATE — the year the work was created or published (e.g. "1955", "1974")
  2. PUBLISHER — the publisher's name (e.g. "Tériade", "Louis Broder")
  3. PRINTER — the printer's name (e.g. "Mourlot Frères", "Crommelynck")
  4. EDITION — the edition size or number (e.g. "edition of 220", "set of 10")
  5. MEDIUM/TECHNIQUE — what it is made of (e.g. "lithographs on Arches wove paper", "drypoints on sheepskin")
  6. COLLABORATOR — who wrote the text or poems (e.g. "Pierre Reverdy", "Sigmund Freud")

PRIORITY RULE: a concrete detail ALWAYS beats a general claim. "published by Tériade in 1955, printed by Mourlot Frères in an edition of 220" beats "an intriguing fusion of visual and textual elements."

FAILURE MODE TO AVOID: Do NOT write sentences like "reveals a deep connection" or "beckons us to question" or "stands out for its intriguing fusion" — these are EMPTY. Instead write: WHO made it, WHEN, HOW (technique), WHERE (printer/workshop), and HOW MANY (edition).

Rules:
  - Name people explicitly (never "the publisher" — use their actual name)
  - State specific actions (not "influenced" or "collaborated" — what did they DO?)
  - Do NOT assert interactions unless the material confirms both people were alive and working together
  - Dates must be accurate. If unsupported, omit rather than invent.
  - "X and Y worked together" / "X's collaboration with Y" is NOT a story — it is the
    identity form. A story requires: who did what, with what material consequence.
  - NO HALLUCINATED SENSORY CLAIMS: never assert a sensation the listener cannot verify
    (smell, sound, temperature, texture) unless the material states it.

STORY REQUIREMENT (LOCAL-421/423 — NON-NEGOTIABLE):
Your description MUST contain at least ONE STORY of no fewer than THREE SENTENCES.
A story = a claim about PEOPLE AND CONSEQUENCES: a relationship, a decision, a dispute,
a gift, a reason something was made the way it was.

VERIFICATION CONSTRAINT (LOCAL-423 — HARD GATE):
Every factual claim in your story (dates, numbers, locations, attributions) will be
verified against the reference material above. If a claim cannot be found in the
snippets, it will be STRIPPED from the delivered text. DO NOT invent details that
the snippets do not support — even if you believe them to be true. If the snippets
say "a Russian collector", do NOT say "a Boston-based collector". If the snippets
do not state a donation year, do NOT assert one. Write ONLY what the sources confirm.
Self-contradictions (e.g. "15 lithographs" in one sentence and "40 lithographs" in
another) cause AUTOMATIC REJECTION — pick one number and cite which snippet supports it.

WHAT COUNTS AS A STORY:
  - "Boris Fridman donated this work to the MFA in 2003. Fridman, a Boston-based collector
    who specialized in livres d'artiste, assembled one of the largest private collections
    of artist's books in New England. His gift brought the museum's holdings of
    Surrealist-era printed works to a critical mass."
  - "Dalí chose Freud's Moses and Monotheism because he considered Freud's work
    foundational to Surrealism. Dalí had attempted to visit Freud in London in 1938
    and sketched the dying psychoanalyst during that meeting."
  - "Louis Broder commissioned this work from Miró as part of a deliberate campaign to
    revive the livre d'artiste tradition after the war. Broder's editions were tiny —
    rarely more than 150 copies — and he insisted on direct collaboration between
    artist, poet, and printer at the same workshop."

WHAT DOES NOT COUNT:
  - A list of facts with no narrative thread (just naming publisher + printer + date)
  - "Invites you to ponder" / "transcends boundaries" / "a testament to" (evaluation)
  - An interpretation the writer supplies without sourcing it to a person or event
  - Describing the image/object itself (that is ekphrasis, not story)

If the reference material supports NO story, you must still try to build one from the
entities you do have (donor, publisher, printer) — state who they were and what their
involvement meant. If truly nothing supports even that, write only what you can verify.

ENTITY NAMING RULE (LOCAL-421 — NON-NEGOTIABLE):
Every named person in the credit line (donor, publisher, printer, collaborator) MUST
appear BY NAME in your text. Never write "the generous donation" when the data says
"Gift of Boris Fridman". Never write "the publisher" when you know the name. The name
IS the story's starting point.
"""
    # [LOCAL-407] Artist name is NON-NEGOTIABLE in the snippet block
    if _artist_surname:
        block += f"""
ARTIST ATTRIBUTION (LOCAL-407 — NON-NEGOTIABLE):
The artist for this work is {artist}. The surname "{_artist_surname}" MUST appear
in your text. The people named in the snippets (publishers, printers, donors) are
IN ADDITION TO the artist, never instead of. If you write about Broder or Mourlot
without mentioning {_artist_surname}, your response will be REJECTED.
"""
    return block


# [LOCAL-402] Direct snippet injection — bypasses the extract/score pipeline.
# Populated by the runner BEFORE calling generate_tour_text().
# Keys: stop_name (str) → list of {'title': str, 'snippet': str, 'url': str}
# When non-empty, the per-stop prompt injects these as reference material
# with an instruction to write one grounded story about a named person.
_DIRECT_SNIPPETS_PER_STOP: dict = {}

# [LOCAL-323] REMOVED module-level globals _CURRENT_JOB_USER_ID / _CURRENT_JOB_ID.
# They were not thread-safe: concurrent jobs sharing the same module meant one
# thread's write would clobber another's. Fixed by threading user_id/job_id as
# parameters through generate_tour_text() → generate_spine(). See bounce review.


# [LOCAL-326] Phase-boundary cost ceiling check.
# Reads COST_HARD_LIMIT from the same env var as cost_ceiling_monitor.py —
# single source of truth. Check is pure in-memory comparison (no DB round-trip).
_PHASE_COST_HARD_LIMIT = float(os.environ.get("COST_HARD_LIMIT_USD", "1.30"))


class _SkipPostRoundCheck(Exception):
    """[D493] No replenishment round was issued, so there is nothing to re-measure.

    Control flow, not an error. It exists so the post-round check reports nothing
    rather than reporting "NO CHANGE", which would read as a round that ran and
    failed instead of a round that was never issued. The log must not describe
    spending that did not happen.
    """


class _CostCeilingBreached(Exception):
    """Raised when accumulated generation cost exceeds COST_HARD_LIMIT at a phase boundary.

    Carries the phase name and current cost so the caller can assemble a partial tour.
    """
    def __init__(self, phase: str, cost: float, limit: float):
        self.phase = phase
        self.cost = cost
        self.limit = limit
        super().__init__(
            f"[LOCAL-326] Cost ceiling breached at {phase}: "
            f"${cost:.4f} > ${limit:.4f} — stopping generation"
        )


def _check_phase_boundary_cost(total_cost: float, phase_name: str) -> None:
    """Compare accumulated cost against hard limit. Raise on breach.

    Called at natural phase boundaries — no DB call, no LLM call.
    Normal tours (~$0.07) pass this in < 1µs.
    """
    if total_cost > _PHASE_COST_HARD_LIMIT:
        print(f"[LOCAL-326] COST CEILING BREACHED at {phase_name}: "
              f"${total_cost:.4f} > ${_PHASE_COST_HARD_LIMIT:.4f}")
        raise _CostCeilingBreached(phase_name, total_cost, _PHASE_COST_HARD_LIMIT)


def _is_artist_human(artist_qid: str) -> bool:
    """Check if a Wikidata entity is a human (P31=Q5).
    
    Used to validate that a resolved 'artist' is actually a person/creator
    before running the artist-placement rejection check. Prevents nonsense
    rejections when P921/P138 points to a concept (e.g. 'United States Constitution').
    """
    if not artist_qid:
        return False
    try:
        import requests as _req
        resp = _req.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities",
                "ids": artist_qid,
                "props": "claims",
                "format": "json",
            },
            headers={"User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)"},
            timeout=10,
        )
        if resp.status_code != 200:
            return False
        
        data = resp.json()
        entity = data.get("entities", {}).get(artist_qid, {})
        claims = entity.get("claims", {})
        
        # Check P31 (instance-of) for Q5 (human)
        for claim in claims.get("P31", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if value.get("id") == "Q5":
                return True
        
        return False
    except Exception:
        return False


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


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL-372: Lifted helpers for theme-word filter (testable at module scope)
# ═══════════════════════════════════════════════════════════════════════════════

def theme_word_match(work_lower: str, theme_words) -> str:
    """Check if any theme word matches `work_lower` on a word boundary.
    
    Returns the matching theme word, or '' if none matched.
    Uses whitespace/punctuation boundaries but treats apostrophes as part of a word
    (so 'or' does not match inside "d'or", and 'art' does not match inside "l'art").
    
    [LOCAL-372] Lifted to module scope for testability.
    """
    import re as _re_tw
    for tw in theme_words:
        # Use a custom boundary pattern: the theme word must be surrounded by
        # whitespace, start/end of string, or punctuation OTHER THAN apostrophe/hyphen.
        # This prevents French contractions (d'or, l'art) from false-matching.
        _escaped = _re_tw.escape(tw)
        # Lookbehind: start of string OR whitespace OR punctuation (not ' or -)
        # Lookahead: end of string OR whitespace OR punctuation (not ' or -)
        _pattern = (r'(?:^|(?<=[\s,;:.!?()\[\]{}"/]))'
                    + _escaped +
                    r'(?:$|(?=[\s,;:.!?()\[\]{}"/]))')
        if _re_tw.search(_pattern, work_lower):
            return tw
    return ''


# Keywords indicating an exhibition is about books, prints, or illustrated volumes.
# When these appear in the exhibition requirements/name, theme-word drops are suppressed.
_BOOK_EXHIBITION_KEYWORDS = frozenset([
    'livre', 'livres', 'book', 'books', 'unbound',
    'print', 'prints', 'illustrated', 'illustration', 'illustrations',
    'lithograph', 'lithographs', 'etching', 'etchings',
    'artist book', 'artists book', "artist's book", "artists' books",
    "livres d'artiste", "livre d'artiste",
    'woodcut', 'woodcuts', 'engraving', 'engravings',
])


def _is_book_exhibition_scope(exhibition_scope) -> bool:
    """Determine if the exhibition scope concerns books/prints/illustrated volumes.
    
    When True, theme-word drops are suppressed because in such exhibitions,
    book-related words ARE legitimate artwork descriptors.
    
    [LOCAL-372] Lifted to module scope for testability.
    """
    if not exhibition_scope:
        return False
    _requirements = (exhibition_scope.get('requirements', '') or '').lower()
    if not _requirements:
        return False
    # Check if any book-exhibition keyword appears in requirements
    for kw in _BOOK_EXHIBITION_KEYWORDS:
        if kw in _requirements:
            return True
    return False


def title_appears_in_page(title, page_text, min_word_overlap=0.7):
    """
    [LOCAL-372 LEAD] Is `title` actually present in the venue page it came from?

    LOCAL-372 skips D1v2 for exhibition-sourced stops, and the reasoning is right:
    D1v2 verifies against the venue's SPARQL/canonical titles, which describe the
    PERMANENT collection, so it will always reject works from a temporary show —
    that is what deleted 'Le Lézard aux plumes d'or'.

    But "skip verification" is not the same as "verify against the right source".
    As submitted, an exhibition stop had no grounding check at all: a title the
    extraction LLM invented would be delivered unchallenged, in the one path whose
    whole premise is that the venue's own page is authoritative.

    So verify against that page. Tolerant of reformatting — accents folded,
    punctuation dropped, case ignored — but requires most significant words of the
    title to be present, which an invented title will not satisfy.
    """
    if not title or not page_text:
        return False

    def _fold(s):
        n = unicodedata.normalize('NFKD', s.lower())
        n = ''.join(c for c in n if not unicodedata.combining(c))
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', n)).strip()

    t_norm, p_norm = _fold(title), _fold(page_text)
    if not t_norm:
        return False
    if t_norm in p_norm:
        return True

    words = [w for w in t_norm.split() if len(w) >= 4]
    if not words:
        # Very short title — require exact normalized containment, already failed.
        return False
    present = sum(1 for w in words if w in p_norm)
    return (present / len(words)) >= min_word_overlap


def _verify_works_v2(poi_list, venue_name, exhibition_scope=None):
    """[D1 v2] In-collection verification using story_miner canonical title matching.
    
    Uses venue_resolver for entity resolution (Generic Grounding Step 0+1) and
    story_miner for canonical title matching (T0a) and story corpus.
    
    Sources for canonical titles (union, per LEAD amendment #1):
    - SPARQL works query (P195/P276) — highest precision
    - Official site extraction (from P856)
    - Wikipedia extraction (EN + local language)
    
    Args:
        poi_list: List of POI dicts to verify.
        venue_name: Full venue name string for entity resolution.
        exhibition_scope: Optional dict from _exhibition_scope (has 'requirements', 'artists', etc.)
                          When the exhibition is about books/prints/illustrated volumes, the
                          theme-word filter is exempted (LOCAL-372).
    
    Returns (verified_pois, evidence_log, venue_corpus, story_corpus_result) or None.
    """
    try:
        from story_miner import (
            fetch_venue_narrative_corpus,
            match_candidate_to_canonical,
            check_stop_disjointness,
        )
    except ImportError:
        _import_logger.error("[D1v2] MISSING: story_miner (fetch_venue_narrative_corpus, match_candidate_to_canonical, check_stop_disjointness) — corpus mining DISABLED for this tour")
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
        _import_logger.error("[D1v2] MISSING: venue_resolver (resolve_venue, fetch_venue_works, build_canonical_titles_from_works) — venue resolution DISABLED")
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
        # [LOCAL-30] Reconstruct combined_text from cached pages (pages is a list of dicts)
        _cached_pages = _cache_hit.get('pages') or []
        if isinstance(_cached_pages, list):
            combined_text = '\n\n'.join(p.get('text', '') for p in _cached_pages if isinstance(p, dict) and p.get('text'))
        elif isinstance(_cached_pages, dict):
            combined_text = _cached_pages.get('combined_text', '')
        else:
            combined_text = ''
        # [LOCAL-30] Reconstruct source_urls from official_url (always available in cache)
        _cache_source_urls = []
        if _cache_hit.get('official_url'):
            _cache_source_urls = [_cache_hit['official_url']]
        # [LOCAL-30] Re-extract catalogue works from cached pages
        _cache_catalogue_works = []
        if _cached_pages and isinstance(_cached_pages, list):
            from story_miner import extract_catalogue_works_from_pages
            _cache_catalogue_works = extract_catalogue_works_from_pages(_cached_pages)
        # [LOCAL-30] Reconstruct theme_words from canonical_titles
        # Theme words are single lowercase words that appear in multiple titles
        _cache_theme_words = set()
        if canonical_titles:
            from collections import Counter as _Counter
            _all_words = []
            for _ct in canonical_titles:
                _all_words.extend(w.lower() for w in _ct.split() if len(w) > 3)
            _word_counts = _Counter(_all_words)
            _cache_theme_words = {w for w, c in _word_counts.items() if c >= 3}
        corpus_result = {
            'canonical_titles': canonical_titles,
            'combined_text': combined_text,
            'pages': _cached_pages,
            'cycle_names': set(),
            'theme_words': _cache_theme_words,
            'source_urls': _cache_source_urls,
            'per_work_contexts': {},
            'catalogue_works': _cache_catalogue_works,
        }
        cycle_names = corpus_result['cycle_names']
        print(f"  [D1v2] Cache HIT: {len(canonical_titles)} canonical titles (tier={_cache_hit['tier']})"
              f", {len(_cache_catalogue_works)} catalogue works, combined_text={len(combined_text)} chars")
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
            venue_qid=_venue_entity.qid if _venue_entity else "",
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
                    venue_qid=_venue_entity.qid if _venue_entity else "",
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
    
    # [LOCAL-34] Track bare SPARQL titles that need enrichment at stop-naming time.
    # When SPARQL returns a bare single-word title (e.g., "Raquel"), we keep it as-is
    # for matching purposes, but build a richer display title from corpus context.
    _bare_sparql_enrichments = {}  # bare_title → enriched_title
    if sparql_titles and combined_text:
        for _st in sparql_titles:
            if len(_st.split()) <= 1 and len(_st) < 12:
                # Bare word — search for context in corpus
                _st_lower = _st.lower()
                _st_pos = combined_text.lower().find(_st_lower)
                if _st_pos >= 0:
                    _ctx_start = max(0, _st_pos - 200)
                    _ctx_end = min(len(combined_text), _st_pos + 200)
                    _ctx = combined_text[_ctx_start:_ctx_end]
                    _period_match = re.search(
                        r'(?:fin\s+du\s+|d[eé]but\s+du\s+)?'
                        r'([IVXLC]+e\s+si[eè]cle|\d{4})',
                        _ctx, re.IGNORECASE
                    )
                    _material_match = re.search(
                        r'(cuir\s+dor[eé]|portrait|peinture|sculpture|bronze|'
                        r'panneau|bois|marbre|toile|huile|cuivre|ivoire|'
                        r'gilded\s+leather|painted\s+leather|panel)',
                        _ctx, re.IGNORECASE
                    )
                    _parts = []
                    if _material_match:
                        _parts.append(_material_match.group(1).strip())
                    if _period_match:
                        _parts.append(_period_match.group(0).strip())
                    if _parts:
                        _enriched = f"{_st} ({', '.join(_parts)})"
                        _bare_sparql_enrichments[_st] = _enriched
                        print(f"  [LOCAL-34] Will enrich bare title at stop-naming: '{_st}' → '{_enriched}'")
    
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

    # --- LOCAL-24: Work-vs-Nonwork Filter ---
    # Classify all canonical titles and remove non-works (programs, workshops,
    # section headings, streets, museum-meta labels). Tag galleries distinctly.
    from story_miner import filter_corpus_titles
    _title_sources = corpus_result.get('title_sources', {}) if 'corpus_result' in dir() and corpus_result else {}
    _filter_result = filter_corpus_titles(
        raw_titles=canonical_titles,
        sparql_works=sparql_works,
        source_urls_map=_title_sources,
        venue_name=venue_name,
        venue_address="",  # Could be enriched from venue entity if available
        preferred_language=_language if '_language' in dir() else "en",
    )
    # Replace canonical_titles with only classified works (galleries are tracked separately)
    canonical_titles = _filter_result['works']
    _gallery_titles = _filter_result['galleries']
    _excluded_titles = _filter_result['excluded']
    _cross_lang_aliases = _filter_result['aliases']
    
    # Store classification in corpus_result for downstream audit
    # CRITICAL: Also update corpus_result['canonical_titles'] so R4 replenishment
    # uses the FILTERED set (prevents excluded titles from being re-verified via R4)
    if 'corpus_result' in dir() and corpus_result and isinstance(corpus_result, dict):
        corpus_result['filter_result'] = _filter_result
        corpus_result['canonical_titles'] = canonical_titles  # LOCAL-24: filtered set
        corpus_result['bare_sparql_enrichments'] = _bare_sparql_enrichments  # LOCAL-34
    
    print(f"  [D1v2-LOCAL24] After filter: {len(canonical_titles)} works, "
          f"{len(_gallery_titles)} galleries, {len(_excluded_titles)} excluded")

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
    
    # LOCAL-28: Pre-inject catalogue works as verified candidates
    # These are museum-published documented works with structured metadata —
    # highest confidence, no GPT guessing needed.
    _catalogue_works = corpus_result.get('catalogue_works', [])
    _catalogue_titles_injected = set()
    if _catalogue_works:
        from story_miner import _normalize as _norm_cat
        for cw in _catalogue_works:
            _cat_title = cw.get('title', '')
            if not _cat_title or _cat_title in _catalogue_titles_injected:
                continue
            # Check against existing canonical titles (they should be there from corpus extraction)
            if _cat_title in canonical_titles or any(
                _norm_cat(_cat_title) == _norm_cat(ct) for ct in canonical_titles
            ):
                verified_pois.append({
                    'name': _cat_title,
                    'address': '',  # Will be resolved later
                })
                _catalogue_titles_injected.add(_cat_title)
                # [LOCAL-31] Validate period/material against the entry's own description.
                # The text-based parser may attribute metadata from an adjacent entry
                # when section boundaries aren't clean. Only trust period/material
                # if they actually appear within the entry's own description text.
                _cw_desc = cw.get('description', '')
                _cw_period = cw.get('period', '')
                _cw_material = cw.get('material', '')
                _cw_origin = cw.get('origin', '')
                
                # Period validation: must appear in the entry's own description
                if _cw_period and _cw_desc:
                    _period_in_desc = _cw_period.lower() in _cw_desc.lower()
                    if not _period_in_desc:
                        # Check if any part of the period string is in the description
                        # e.g., "Xe siècle" might appear as "Xe siècle" in description
                        _period_core = re.search(r'[IVXLC]+e\s+si[eè]cle|\d{4}', _cw_period)
                        if _period_core:
                            _period_in_desc = _period_core.group(0).lower() in _cw_desc.lower()
                    if not _period_in_desc:
                        print(f"  [LOCAL-31] Dropping period '{_cw_period}' for '{_cat_title}' — "
                              f"not found in entry's own description (likely cross-entry bleed)")
                        _cw_period = ''
                
                # Material validation: at least one keyword must appear in description
                if _cw_material and _cw_desc:
                    _mat_words = [m.strip().lower() for m in _cw_material.split(',')]
                    _mat_in_desc = any(mw in _cw_desc.lower() for mw in _mat_words if len(mw) > 3)
                    if not _mat_in_desc:
                        print(f"  [LOCAL-31] Dropping material '{_cw_material}' for '{_cat_title}' — "
                              f"not found in entry's own description (likely cross-entry bleed)")
                        _cw_material = ''
                
                evidence_log[_cat_title] = {
                    "status": "VERIFIED",
                    "canonical_title": _cat_title,
                    "snippet": _cw_desc[:200],
                    "method": "catalogue_work",
                    "material": _cw_material,
                    "period": _cw_period,
                    "origin": _cw_origin,
                }
        if _catalogue_titles_injected:
            print(f"  [LOCAL-28] Pre-injected {len(_catalogue_titles_injected)} catalogue works as verified POIs")
    
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
    
    # Extract artist name for rejection checks — USE ENTITY DATA, not regex on venue name
    # Only run artist-placement check when the resolved artist is a real person/creator
    _venue_artist = ""
    artist_article = ""
    if _venue_entity and _venue_entity.artist_qid:
        # Validate: artist must be a human (P31=Q5) to be a real creator
        if _is_artist_human(_venue_entity.artist_qid):
            _venue_artist = _venue_entity.artist_name
            if _venue_artist:
                artist_article = fetch_wikipedia_summary(_venue_artist)
                print(f"  [D1v2] Artist-check: valid creator '{_venue_artist}' ({_venue_entity.artist_qid})")
        else:
            print(f"  [D1v2] artist-check skipped (no valid creator) — "
                  f"artist_qid={_venue_entity.artist_qid} ({_venue_entity.artist_name}) is not a human")
    elif _venue_entity:
        print(f"  [D1v2] artist-check skipped (no valid creator) — no artist_qid on entity")
    else:
        # No entity resolved — skip artist check entirely (better than regex guessing)
        print(f"  [D1v2] artist-check skipped (no valid creator) — venue not resolved")

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
            # [LOCAL-97] Don't overwrite existing catalogue_work entries — they carry
            # period/material metadata that the C5-1 binding block needs.
            _existing_ev_for_title = evidence_log.get(work_name)
            if not (_existing_ev_for_title and _existing_ev_for_title.get('method') == 'catalogue_work'):
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
            # [LOCAL-34] Apply enrichment for bare SPARQL titles
            if _best_title in _bare_sparql_enrichments:
                _best_title = _bare_sparql_enrichments[_best_title]
                print(f"  [LOCAL-34] Stop title enriched: '{canonical_title}' → '{_best_title}'")
            poi['name'] = _best_title
            verified_pois.append(poi)
            continue
        
        # Step 2: Check if it's a theme word / cycle name (should not be a stop)
        # [LOCAL-372] Word-boundary matching: `tw in _work_lower` is plain containment
        # which matches substrings (e.g. 'or' inside "d'or"). Use \b word boundaries.
        # Also: exempt when exhibition is about books/prints/illustrated volumes —
        # in that domain, book-words ARE the artworks.
        _work_lower = work_name.lower()
        _theme_word_matched = theme_word_match(_work_lower, corpus_result['theme_words'])
        if _theme_word_matched:
            # [LOCAL-372] Scope-aware exemption: if exhibition is about books/prints,
            # book-related theme words should not disqualify works.
            if _is_book_exhibition_scope(exhibition_scope):
                print(f"  [D1v2] EXEMPT '{work_name}' — theme word '{_theme_word_matched}' "
                      f"matched but exhibition is book/print-scoped (LOCAL-372)")
            else:
                print(f"  [D1v2] DROPPED '{work_name}' — theme/book word '{_theme_word_matched}', not a work title")
                evidence_log[work_name] = {"status": "DROPPED", "reason": f"theme word: '{_theme_word_matched}'"}
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
        # [LOCAL-372] Loud warning when filtering removed ALL candidates
        _dropped_entries = [k for k, v in evidence_log.items() if v.get('status') == 'DROPPED']
        if _dropped_entries:
            print(f"  [D1v2] ⚠️  ALL {len(_dropped_entries)} candidate(s) were DROPPED — "
                  f"every work was filtered out, producing unresolvable from non-empty input")
            for _dk in _dropped_entries:
                _dr = evidence_log[_dk].get('reason', '?')
                print(f"    DROPPED: '{_dk}' — {_dr}")
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
            # [LOCAL-97] Do NOT overwrite existing catalogue_work entries in evidence_log.
            # Catalogue entries carry period/material metadata that the C5-1 binding block needs.
            _existing_ev = evidence_log.get(_vp.get('name', ''))
            if not (_existing_ev and _existing_ev.get('method') == 'catalogue_work'):
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
    
    # Detect exhibit_museum tier: entity resolved + SPARQL works scarce (< 5)
    # but we still verified candidates against exhibit-name corpus (sections/quotes)
    _is_exhibit_museum = (
        _venue_entity and _venue_entity.qid and
        _evidence_strength < 5 and
        _n_verified >= 1 and
        len(canonical_titles) > len(sparql_titles)  # More titles from site/wiki than SPARQL
    )
    
    if _is_exhibit_museum:
        _tier = 'exhibit_museum'
        print(f"  [D1v2] Exhibit museum detected: {_evidence_strength} SPARQL QIDs, "
              f"{len(canonical_titles)} total titles (mostly from site/wiki sections)")
    else:
        _tier = compute_tier(_n_verified, _evidence_strength)
    
    print(f"  [D1v2] {_n_verified}/{len(poi_list)} works verified — tier: {_tier}")
    
    # --- REQUIRE_LISTING_VERIFICATION: unified fill control ---
    # When REQUIRE_LISTING_VERIFICATION=true: strict mode (cap at verified count, old behavior)
    # When false (default): fills are allowed — caller handles unified fill logic for all tiers.
    # (The old EXHIBIT_FILL_HEDGED logic is superseded by the unified caller-side fill in R4.)
    
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


# ============================================================
# [LOCAL-27] Truthfulness guards: sourced-or-omit for metadata
# ============================================================


def _is_valid_visitor_info(text: str) -> bool:
    """[LOCAL-32/33] Validity gate for visitor information text.
    
    Returns True only if the text contains at least one recognisable fact:
    - A closed day (e.g., "Closed on Tuesday", "Fermé le mardi")
    - Opening hours with times (e.g., "10:00 to 17:00", "10am-5pm")
    - Admission/pricing info (e.g., "Free admission", "€8", "$15")
    
    Rejects:
    - Raw nav fragments ("tarifs Télécharger le recueil 2026")
    - Garbled mixed-language text without coherent facts
    - Text that's just download links or button labels
    """
    if not text or len(text.strip()) < 5:
        return False
    
    _text_lower = text.lower()
    
    # REJECTION signals — if these dominate, it's nav junk
    _NAV_JUNK_PATTERNS = re.compile(
        r'(?:'
        r't[eé]l[eé]charger|download|recueil|d[eé]lib[eé]ration|'
        r'cliquez?\s+(?:ici|here)|en\s+savoir\s+plus|'
        r'read\s+more|learn\s+more|voir\s+(?:les?|tous)|'
        r"retrouvez|s[\u2019']inscrire|sign\s+up"
        r')', re.IGNORECASE
    )
    _nav_junk_count = len(_NAV_JUNK_PATTERNS.findall(text))
    if _nav_junk_count >= 2:
        return False
    
    # VALID FACT detection — need at least one
    has_valid_fact = False
    
    # 1. Closed day detection (EN and FR)
    _closed_day_re = re.compile(
        r'(?:'
        r'closed?\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
        r'ferm[eé]\s+(?:le\s+)?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)|'
        r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+closed'
        r')', re.IGNORECASE
    )
    if _closed_day_re.search(text):
        has_valid_fact = True
    
    # 2. Opening hours with actual times
    _hours_re = re.compile(
        r'(?:'
        r'\d{1,2}[h:]\d{0,2}\s*[-–àa to]+\s*\d{1,2}[h:]\d{0,2}|'  # 10h-17h or 10:00 to 17:00
        r'\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*[-–to]+\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)|'  # 10am-5pm
        r'(?:open|ouvert)\s+(?:every|tous\s+les|daily|all)\s+(?:day|jours?)'  # "Open every day"
        r')', re.IGNORECASE
    )
    if _hours_re.search(text):
        has_valid_fact = True
    
    # 3. Admission/pricing info
    _admission_re = re.compile(
        r'(?:'
        r'free\s+admission|admission\s+free|entr[eé]e\s+(?:libre|gratuite)|gratuit|'
        r'(?:admission|entry|ticket)\s*[:.]?\s*\$?\d+|'
        r'\d+\s*(?:€|EUR|\$|£)|'
        r'(?:\$|€|£)\s*\d+'
        r')', re.IGNORECASE
    )
    if _admission_re.search(text):
        has_valid_fact = True
    
    # 4. Check coherence: text should not be excessively fragmented
    words = text.split()
    if len(words) > 3:
        short_word_ratio = sum(1 for w in words if len(w) <= 2) / len(words)
        if short_word_ratio > 0.6:
            return False
    
    # 5. Mixed-language month names = garbled seasonal range
    _en_months = {'january', 'february', 'march', 'april', 'may', 'june',
                  'july', 'august', 'september', 'october', 'november', 'december'}
    _fr_months = {'janvier', 'février', 'fevrier', 'mars', 'avril', 'mai', 'juin',
                  'juillet', 'août', 'aout', 'septembre', 'octobre', 'novembre', 'décembre', 'decembre'}
    _text_words = set(_text_lower.split())
    has_en_month = bool(_text_words & _en_months)
    has_fr_month = bool(_text_words & _fr_months)
    if has_en_month and has_fr_month:
        if not (_closed_day_re.search(text) or _admission_re.search(text)):
            return False
    
    return has_valid_fact


# [LOCAL-36] Raw source fetcher for practical facts gate provenance
def _fetch_visitor_info_raw_source(base_site_url: str) -> str:
    """Fetch the raw text content from the venue's visitor info page.
    
    Unlike _fetch_visitor_info_from_site which extracts and translates,
    this returns the raw source text for verification by the practical facts gate.
    The gate needs the original source content to verify that claims are supported.
    """
    if not base_site_url:
        return ""
    
    from urllib.parse import urljoin, urlparse
    
    _VISITOR_INFO_PATHS_RELATIVE = [
        'tarifs-et-horaires', 'horaires-et-tarifs', 'infos-pratiques',
        'informations-pratiques', 'plan-your-visit', 'visit',
        'visitor-information', 'hours-admission', 'hours-and-admission',
        'opening-hours', 'practical-information',
        'tarifs', 'horaires', 'visite',
    ]
    
    _parsed_info_url = urlparse(base_site_url)
    _info_path_segments = [s for s in _parsed_info_url.path.rstrip('/').split('/') if s]
    _is_deep_path = len(_info_path_segments) > 1
    
    _urls_to_try = []
    if _is_deep_path:
        _venue_base = base_site_url.rstrip('/')
        for slug in _VISITOR_INFO_PATHS_RELATIVE:
            _urls_to_try.append(_venue_base + '/' + slug)
    else:
        for slug in _VISITOR_INFO_PATHS_RELATIVE:
            _urls_to_try.append(urljoin(base_site_url, '/' + slug))
    
    for _url in _urls_to_try:
        try:
            resp = requests.get(_url, headers={'User-Agent': 'Audioura/2.2'},
                              timeout=10, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                _text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                _text = re.sub(r'<style[^>]*>.*?</style>', '', _text, flags=re.DOTALL)
                _text = re.sub(r'<[^>]+>', ' ', _text)
                _text = re.sub(r'\s+', ' ', _text).strip()
                if len(_text) > 100:
                    return _text[:5000]
        except Exception:
            continue
    
    return ""


def _fetch_visitor_info_from_site(base_site_url: str, language: str = "en") -> str:
    """Attempt to fetch practical visitor information (hours, admission) from the venue's official site.
    
    Returns a sourced string with hours/admission info, or empty string if not reliably extractable.
    The function looks for known tarif/horaire pages and extracts structured data.
    It NEVER generates or interpolates — it only returns text literally found on the site.
    
    [LOCAL-29 Fix B] When the tour language differs from the source page language,
    the extracted info is translated to the tour language via structured field extraction
    and reformatting, preserving the sourced data while presenting it accessibly.
    """
    if not base_site_url:
        return ""
    
    from urllib.parse import urljoin, urlparse
    
    # Known URL patterns for visitor info pages across museum sites
    _VISITOR_INFO_PATHS_RELATIVE = [
        'tarifs-et-horaires', 'horaires-et-tarifs', 'infos-pratiques',
        'informations-pratiques', 'plan-your-visit', 'visit',
        'visitor-information', 'hours-admission', 'hours-and-admission',
        'opening-hours', 'practical-information',
        'tarifs', 'horaires', 'visite',
    ]
    
    _base_domain = urlparse(base_site_url).netloc
    _fetched_text = ""
    
    # LOCAL-33: Scope visitor-info probing to the venue's own section.
    # When base_site_url is deep (portal site), visitor info paths on the
    # domain root belong to the portal, not the venue. Only try sibling
    # pages within the venue's path prefix.
    _parsed_info_url = urlparse(base_site_url)
    _info_path_segments = [s for s in _parsed_info_url.path.rstrip('/').split('/') if s]
    _is_deep_path = len(_info_path_segments) > 1
    
    _urls_to_try = []
    if _is_deep_path:
        # Deep path: only try as siblings/children of the venue URL
        _venue_base = base_site_url.rstrip('/')
        for slug in _VISITOR_INFO_PATHS_RELATIVE:
            _urls_to_try.append(_venue_base + '/' + slug)
        print(f"  [LOCAL-33] Visitor info scoped to venue section (deep path)")
    else:
        # Bare domain: try as root-level paths (original behavior)
        for slug in _VISITOR_INFO_PATHS_RELATIVE:
            _urls_to_try.append(urljoin(base_site_url, '/' + slug))
    
    for _url in _urls_to_try:
        try:
            resp = requests.get(_url, headers={'User-Agent': 'Audioura/2.2'},
                              timeout=10, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                # Extract just the text content
                _text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                _text = re.sub(r'<style[^>]*>.*?</style>', '', _text, flags=re.DOTALL)
                _text = re.sub(r'<[^>]+>', ' ', _text)
                _text = re.sub(r'\s+', ' ', _text).strip()
                if len(_text) > 100:
                    _fetched_text = _text[:5000]
                    print(f"  [LOCAL-27] Visitor info page found: {_url}")
                    break
        except Exception:
            continue
    
    if not _fetched_text:
        print(f"  [LOCAL-27] No visitor info page found for {base_site_url}")
        return ""
    
    # Extract structured hours/admission from the page text
    # We look for patterns that clearly indicate hours and admission prices
    _info_parts = []
    
    # Hours patterns (French and English)
    _hours_patterns = [
        # French patterns
        re.compile(r'(?:ouvert|ouverture)[^.]{0,100}(?:\d{1,2}h?\d{0,2}\s*[-–àa]\s*\d{1,2}h?\d{0,2})', re.IGNORECASE),
        re.compile(r'(?:fermé|fermeture)[^.]{0,80}(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)', re.IGNORECASE),
        re.compile(r'\d{1,2}h?\d{0,2}\s*[-–àa]\s*\d{1,2}h?\d{0,2}[^.]{0,60}(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|tous les jours)', re.IGNORECASE),
        # English patterns
        re.compile(r'(?:open|hours)[^.]{0,100}(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)\s*[-–to]+\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))', re.IGNORECASE),
        re.compile(r'(?:closed)\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)', re.IGNORECASE),
    ]
    
    # Admission patterns (French and English)
    _admission_patterns = [
        re.compile(r'(?:gratuit|free|admission\s+free|entr[eé]e\s+(?:libre|gratuite))', re.IGNORECASE),
        re.compile(r'(?:tarif|admission|entry|ticket)[^.]{0,60}(?:\d+\s*(?:€|EUR|dollars?|\$|£)|\d+(?:\.\d{2})?)', re.IGNORECASE),
        re.compile(r'(?:\d+\s*(?:€|EUR))[^.]{0,60}(?:tarif|plein|réduit|adult|enfant|child)', re.IGNORECASE),
    ]
    
    for pattern in _hours_patterns:
        matches = pattern.findall(_fetched_text)
        if matches:
            # Take the first clear match — truncate to reasonable length
            _match_text = matches[0] if isinstance(matches[0], str) else matches[0][0] if matches[0] else ''
            if _match_text and len(_match_text) > 10:
                _info_parts.append(_match_text.strip()[:150])
                break
    
    for pattern in _admission_patterns:
        matches = pattern.findall(_fetched_text)
        if matches:
            _match_text = matches[0] if isinstance(matches[0], str) else matches[0][0] if matches[0] else ''
            if _match_text and len(_match_text) > 3:
                _info_parts.append(_match_text.strip()[:100])
                break
    
    if not _info_parts:
        print(f"  [LOCAL-27] Could not extract structured hours/admission from visitor info page")
        return ""
    
    _raw_result = '. '.join(_info_parts)
    print(f"  [LOCAL-27] Extracted visitor info: {_raw_result[:80]}...")
    
    # [LOCAL-32/33] Validity gate: verify the extracted text parses into recognisable
    # hours/closure/admission facts. If it doesn't, it's raw nav junk — omit entirely.
    if not _is_valid_visitor_info(_raw_result):
        print(f"  [LOCAL-33] Visitor info FAILED validity gate — omitting (raw: '{_raw_result[:100]}')")
        return ""
    
    # [LOCAL-29 Fix B] Translate to tour language if source is in a different language.
    # Use structured extraction + deterministic translation for common patterns,
    # so we keep the sourced data without relying on GPT to paraphrase.
    if language and language.lower() != "fr":
        _translated = _translate_visitor_info_to_language(_raw_result, language)
        if _translated:
            # Also validate the translated result
            if _is_valid_visitor_info(_translated):
                print(f"  [LOCAL-29] Visitor info translated to '{language}': {_translated[:80]}...")
                return _translated
            else:
                print(f"  [LOCAL-33] Translated visitor info FAILED validity gate — omitting")
                return ""
    
    return _raw_result


def _extract_visitor_info_from_corpus(combined_text: str, language: str = "en") -> str:
    """[LOCAL-34] Extract visitor info from already-fetched corpus text.
    
    Fallback for venues where hours/tariffs are on the main page rather than
    a dedicated child page. Searches the combined_text for recognisable
    closed-day, hours, and admission patterns.
    
    Returns a concise visitor info string (EN), or empty if none found.
    """
    if not combined_text or len(combined_text) < 200:
        return ""
    
    _info_parts = []
    _text = combined_text
    
    # 1. Closed-day detection (French source → translate to EN)
    _closed_fr = re.search(
        r'(?:Fermé|fermé)\s+(?:le\s+)?'
        r'(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)',
        _text
    )
    # Also handle reversed pattern: "Mardi: Fermé" (schedule-table format)
    _closed_fr_rev = re.search(
        r'(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s*[:]\s*'
        r'(?:Fermé|fermé)',
        _text, re.IGNORECASE
    )
    _closed_en = re.search(
        r'[Cc]losed\s+(?:on\s+)?'
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
        _text
    )
    _FR_TO_EN_DAYS = {
        'lundi': 'Monday', 'mardi': 'Tuesday', 'mercredi': 'Wednesday',
        'jeudi': 'Thursday', 'vendredi': 'Friday', 'samedi': 'Saturday',
        'dimanche': 'Sunday',
    }
    if _closed_fr:
        _day_fr = _closed_fr.group(1).lower()
        _day_en = _FR_TO_EN_DAYS.get(_day_fr, _day_fr.capitalize())
        _info_parts.append(f"Closed on {_day_en}")
    elif _closed_fr_rev:
        _day_fr = _closed_fr_rev.group(1).lower()
        _day_en = _FR_TO_EN_DAYS.get(_day_fr, _day_fr.capitalize())
        _info_parts.append(f"Closed on {_day_en}")
    elif _closed_en:
        _info_parts.append(f"Closed on {_closed_en.group(1)}")
    
    # 2. Opening hours — look for time ranges (French format: 10h00 - 18h00)
    # Find ALL time ranges and pick the widest (main venue hours, not subsidiary)
    _all_hours = re.findall(
        r'(\d{1,2})[hH](\d{2})?\s*[-–àa]\s*(\d{1,2})[hH](\d{2})?',
        _text
    )
    if _all_hours:
        # Pick the time range with the widest span (hours)
        _best_range = None
        _best_span = 0
        for _match in _all_hours:
            _h1 = int(_match[0])
            _h2 = int(_match[2])
            _span = _h2 - _h1
            if _span > _best_span:
                _best_span = _span
                _best_range = _match
        if _best_range:
            _h1 = _best_range[0]
            _m1 = _best_range[1] or '00'
            _h2 = _best_range[2]
            _m2 = _best_range[3] or '00'
            _open_str = f"{_h1}:{_m1}"
            _close_str = f"{_h2}:{_m2}"
            _info_parts.append(f"Open {_open_str} to {_close_str}")
    
    # 3. Admission / pricing
    # Look for "gratuit" / free indicators
    _free_match = re.search(
        r'(?:gratuit|entr[eé]e\s+(?:libre|gratuite)|free\s+admission|admission\s+free)',
        _text, re.IGNORECASE
    )
    # Look for specific pricing (€ amounts)
    _price_match = re.search(
        r'(\d+)\s*€', _text
    )
    if _free_match:
        # Check if it's conditionally free (for specific groups) vs universally free
        _free_context_start = max(0, _free_match.start() - 100)
        _free_context = _text[_free_context_start:_free_match.end() + 50].lower()
        if 'moins de 18' in _free_context or 'étudiant' in _free_context or 'enfant' in _free_context:
            # Conditional free — report the paid price if available
            if _price_match:
                _info_parts.append(f"Admission {_price_match.group(1)}€ (free for under 18, students)")
            else:
                _info_parts.append("Free for under 18 and students")
        else:
            _info_parts.append("Free admission")
    elif _price_match:
        _info_parts.append(f"Admission {_price_match.group(1)}€")
    
    if not _info_parts:
        return ""
    
    _result = '. '.join(_info_parts)
    
    # Validate using the standard gate
    if not _is_valid_visitor_info(_result):
        return ""
    
    return _result


def _translate_visitor_info_to_language(raw_info: str, target_language: str) -> str:
    """[LOCAL-29 Fix B] Translate sourced visitor info to the target language.
    
    Uses deterministic pattern-based translation for common French museum patterns.
    This preserves the sourced factual content while presenting it in the tour's language.
    Does NOT use GPT — purely mechanical translation of known patterns.
    
    Supported: French → English (primary use case for Q3330160 / Musée des Arts Asiatiques).
    Returns empty string if translation is not possible (caller falls back to raw text).
    """
    if not raw_info:
        return ""
    
    if target_language.lower() not in ("en", "english"):
        # For non-English targets, we'd need a broader translation mechanism.
        # For now, return empty to fall back to raw (better than nothing).
        # Future: could use GPT translation with strict "translate only, do not rephrase" instruction.
        return ""
    
    result = raw_info
    
    # --- Day translations ---
    _FR_TO_EN_DAYS = {
        'lundi': 'Monday', 'mardi': 'Tuesday', 'mercredi': 'Wednesday',
        'jeudi': 'Thursday', 'vendredi': 'Friday', 'samedi': 'Saturday',
        'dimanche': 'Sunday',
    }
    for fr_day, en_day in _FR_TO_EN_DAYS.items():
        result = re.sub(r'\b' + fr_day + r'\b', en_day, result, flags=re.IGNORECASE)
    
    # --- Common phrases ---
    _PHRASE_TRANSLATIONS = [
        (r'\b[Ff]erm[eé]\s+le\b', 'Closed on'),
        (r'\b[Ff]erm[eé]\b', 'Closed'),
        (r'\b[Oo]uvert\s+tous\s+les\s+jours\b', 'Open every day'),
        (r'\b[Oo]uvert\b', 'Open'),
        (r'\b[Ee]ntr[eé]e\s+gratuite\b', 'Free admission'),
        (r'\b[Ee]ntr[eé]e\s+libre\b', 'Free admission'),
        (r'\b[Gg]ratuit\b', 'Free'),
        (r'\b[Tt]arif\s+plein\b', 'Full price'),
        (r'\b[Tt]arif\s+r[eé]duit\b', 'Reduced price'),
        (r'\b[Ss]auf\b', 'except'),
        (r'\b[Ee]t\b', 'and'),
        (r'\ble\s+(?=Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)', ''),  # Remove French article before translated days
        (r'\b[Dd]e\b(?=\s+\d)', 'from'),
        (r'\b[àa]\b(?=\s+\d)', 'to'),
        (r'\bjours?\s+f[eé]ri[eé]s?\b', 'public holidays'),
        (r'\btous\s+les\s+jours\b', 'every day'),
        (r'\bouverture\b', 'Opening'),
        (r'\bfermeture\b', 'Closing'),
        (r'\bhoraires?\b', 'Hours'),
    ]
    for pattern, replacement in _PHRASE_TRANSLATIONS:
        result = re.sub(pattern, replacement, result)
    
    # --- Time format: convert "10h" → "10:00", "10h30" → "10:30" ---
    result = re.sub(r'(\d{1,2})h(\d{2})', r'\1:\2', result)
    result = re.sub(r'(\d{1,2})h\b', r'\1:00', result)
    
    # --- LOCAL-32/33: Month translations ---
    _FR_TO_EN_MONTHS = {
        'janvier': 'January', 'février': 'February', 'fevrier': 'February',
        'mars': 'March', 'avril': 'April', 'mai': 'May', 'juin': 'June',
        'juillet': 'July', 'août': 'August', 'aout': 'August',
        'septembre': 'September', 'octobre': 'October',
        'novembre': 'November', 'décembre': 'December', 'decembre': 'December',
    }
    for fr_month, en_month in _FR_TO_EN_MONTHS.items():
        result = re.sub(r'\b' + fr_month + r'\b', en_month, result, flags=re.IGNORECASE)
    
    # --- LOCAL-32/33: Ordinal formatting (1 er → 1st, etc.) ---
    result = re.sub(r'(\d+)\s*(?:er|ère)\b', r'\1st', result)
    result = re.sub(r'(\d+)\s*(?:ème|e)\b', r'\1th', result)
    
    # --- LOCAL-32/33: Remaining French connectors in date ranges ---
    result = re.sub(r'\bdu\b', 'from', result, flags=re.IGNORECASE)
    result = re.sub(r'\bau\b', 'to', result, flags=re.IGNORECASE)
    
    # --- LOCAL-32/33: Clean up multiple spaces and awkward punctuation ---
    result = re.sub(r'\s{2,}', ' ', result)
    result = re.sub(r'\s+([.,;:])', r'\1', result)
    
    # If result is still mostly French (more than 50% unchanged), return empty
    # to signal that translation was incomplete
    if result == raw_info:
        return ""
    
    # LOCAL-32/33: Post-translation coherence check — if significant French fragments remain,
    # truncate to just the coherent English portion or return empty
    _residual_french = re.findall(r'\b(?:du|au|le|la|les|er|ère|ème)\b', result)
    if len(_residual_french) > 3:
        # Too much residual French — try to salvage by taking just the first sentence
        _first_sentence = result.split('.')[0].strip()
        if _first_sentence and _is_valid_visitor_info(_first_sentence):
            result = _first_sentence
        else:
            return ""
    
    return result.strip()


def _check_type_prose_contradiction(poi_list: list) -> list:
    """[LOCAL-27] Check that each stop's declared type_specialty is consistent with its prose description.
    
    Returns list of contradiction warnings. Clears type_specialty on contradicting stops.
    """
    # Period/era keywords that would contradict each other
    _PERIOD_GROUPS = {
        'contemporary': {'contemporary', 'modern', '20th century', '21st century', 'post-war'},
        'ancient': {'ancient', 'antiquity', 'roman', 'greek', 'egyptian', 'tang dynasty',
                   'song dynasty', 'ming dynasty', 'han dynasty', 'byzantine'},
        'medieval': {'medieval', 'middle ages', 'gothic', 'romanesque', '12th century',
                    '13th century', '14th century'},
        'renaissance': {'renaissance', '15th century', '16th century', 'baroque'},
    }
    
    warnings = []
    for poi in poi_list:
        _type = (poi.get('type_specialty') or '').lower()
        _desc = (poi.get('description') or '').lower()
        
        if not _type or not _desc:
            continue
        
        # Find which period group the declared type belongs to
        _declared_period = None
        for period_name, keywords in _PERIOD_GROUPS.items():
            if any(kw in _type for kw in keywords):
                _declared_period = period_name
                break
        
        if not _declared_period:
            continue
        
        # Check if the prose mentions a DIFFERENT period
        for period_name, keywords in _PERIOD_GROUPS.items():
            if period_name == _declared_period:
                continue
            # Count how many times a contradicting period is mentioned in prose
            _contradictions = sum(1 for kw in keywords if kw in _desc)
            if _contradictions >= 2:
                _warning = (f"Stop '{poi.get('name', '?')}': type_specialty says "
                           f"'{_type}' but prose references {period_name} ({_contradictions} mentions)")
                warnings.append(_warning)
                print(f"  [LOCAL-27] CONTRADICTION: {_warning}")
                # Clear the contradicting type_specialty
                poi['type_specialty'] = ''
                break
    
    return warnings


# [LOCAL-361] F3 name guard and the stop-heading invariant live at module scope so
# they can be tested directly. Testing a copy of this logic is not evidence — the
# original submission's 25 cases all passed against a reverted generate_tour_text.py.

# GPT injections typically open with one of these; real artwork titles do not.
_F3_INJECTION_OPENERS = re.compile(r'^(This|Here|The following|In this|Welcome to)\s', re.IGNORECASE)
# A sentence-ending mark followed by a lowercase word is running prose, not a title.
# Real titles capitalize after punctuation: "What Are We? Where Are We Going?"
_F3_SENTENCE_SHAPE = re.compile(r'[.!?;]\s+[a-z]')
_F3_MAX_TITLE_WORDS = 15


def f3_name_is_corrupt(poi_name, verified=True):
    """
    True when `poi_name` looks like GPT injected prose into the name field.

    Punctuation alone is NOT corruption (D274) — "Whaam!", "No. 14",
    "St. Jerome in His Study" and Gauguin's "Where Do We Come From? What Are We?
    Where Are We Going?" are all real titles that the old `any(c in name for c in
    '.!?;')` check deleted.

    D1v2-verified names are exempt from the shape heuristics: the corpus already
    vouched for them. The length ceiling still applies to everything, since an
    over-long name breaks TTS and rendering regardless of provenance.
    """
    if len(poi_name.split()) > _F3_MAX_TITLE_WORDS:
        return True
    if verified:
        return False
    return bool(_F3_SENTENCE_SHAPE.search(poi_name) or _F3_INJECTION_OPENERS.match(poi_name))


def missing_stop_headers(complete_tour, rendered_headers):
    """
    Return the rendered stop headers absent from the assembled tour.

    Checks survival of the headers actually emitted rather than counting
    `^Stop \\d+:` lines. Counting is wrong in two directions: a description body
    whose line opens "Stop 3: ..." inflates the count (D2 only rewrites those in
    storied mode), and a count can match while the wrong header went missing.
    """
    return [h for h in rendered_headers if h not in complete_tour]


# [LOCAL-369] Credit-line provenance. At module scope so it can be tested directly —
# the original submission verified the prohibition with an inspect.getsource string
# assertion, which passes against any tree where the words happen to appear (D277).

# The prohibition is a constant so the test and the prompt cannot drift apart.
PROVENANCE_PROHIBITION = (
    "PROHIBITION: Do NOT infer or assert the donor's motive, wealth, financial condition,\n"
    "or any biographical predicate not contained in retrieved text. Stating \"Gift of [name]\"\n"
    "is the documented fact; \"donated because…\" or \"could no longer afford…\" is fabrication."
)

_CREDIT_LINE_MIN_WORD_OVERLAP = 0.6


def _strip_parenthetical_translation(title: str) -> str:
    """Strip a parenthetical translation from a title.

    'Le Lézard aux plumes d\\'or (The Lizard with Golden Feathers)' → 'Le Lézard aux plumes d\\'or'

    Only strips a trailing parenthetical — interior parentheses in genuine titles
    (e.g. 'Moses (detail)') are left alone if they don't span to the end.
    """
    if not title:
        return title
    stripped = re.sub(r'\s*\([^)]+\)\s*$', '', title).strip()
    return stripped if stripped else title


def match_credit_line(poi_name, works, _normalize=None):
    """
    Return the museum-published credit line for `poi_name`, or '' if no confident match.

    Deliberately stricter than the surrounding fact-matching. A false match here
    does not merely attach an irrelevant fact — it credits someone's gift to an
    object they did not give.

    The submitted version matched on a bare 10-character normalized prefix, the
    pattern LOCAL-29 had already tightened elsewhere "to prevent cross-contamination
    between adjacent entries with similar short prefixes". Measured collisions under
    that rule, all real title pairs:

        'The Lizard with Golden Feathers' vs 'The Lizard King'
        'Adoration of the Shepherds'      vs 'Adoration of the Magi'
        'Au Soleil du Plafond'            vs 'Au Soleil Couchant'

    Requires an exact normalized match, or mutual prefix containment AND at least
    60% word overlap.

    [LOCAL-378] Also strips parenthetical translations before comparison:
    'Le Lézard aux plumes d'or (The Lizard with Golden Feathers)' now matches
    'Le Lézard aux plumes d'or' in the works list. The parenthetical inflated
    the word count and diluted the overlap below threshold.
    """
    if not poi_name or not works:
        return ''
    if _normalize is None:
        from story_miner import _normalize as _normalize

    # [LOCAL-378] Try matching with the parenthetical stripped first, then with the full name.
    # This handles the common case where the tour heading carries a translation
    # parenthetical that the works entry does not have (or vice versa).
    poi_variants = [_strip_parenthetical_translation(poi_name)]
    if poi_variants[0] != poi_name:
        poi_variants.append(poi_name)
    else:
        # poi_name had no parenthetical — only one variant
        pass

    for poi_variant in poi_variants:
        poi_norm = _normalize(poi_variant)
        if not poi_norm:
            continue
        poi_words = {w for w in poi_norm.split() if len(w) >= 4}

        for work in works:
            credit = (work.get('credit_line') or '').strip()
            if not credit:
                continue
            work_title = work.get('title', '')
            # Also strip parenthetical from the work title for symmetric matching
            for title_variant in [_strip_parenthetical_translation(work_title), work_title]:
                title_norm = _normalize(title_variant)
                if not title_norm:
                    continue

                if poi_norm == title_norm:
                    return credit

                if not (poi_norm[:10] in title_norm and title_norm[:10] in poi_norm):
                    continue

                title_words = {w for w in title_norm.split() if len(w) >= 4}
                if not poi_words or not title_words:
                    continue
                overlap = len(poi_words & title_words) / max(len(poi_words), len(title_words))
                if overlap >= _CREDIT_LINE_MIN_WORD_OVERLAP:
                    return credit

    return ''


def match_work_for_stop(poi_name, works, _normalize=None):
    """[LOCAL-378] Return the full work dict for `poi_name`, or None if no match.

    Uses the same parenthetical-aware matching logic as match_credit_line but
    returns the entire work dict (title, artist, date, medium, credit_line, etc.)
    so that the caller can extract medium, publisher, and other provenance data.
    """
    if not poi_name or not works:
        return None
    if _normalize is None:
        from story_miner import _normalize as _normalize

    poi_variants = [_strip_parenthetical_translation(poi_name)]
    if poi_variants[0] != poi_name:
        poi_variants.append(poi_name)

    for poi_variant in poi_variants:
        poi_norm = _normalize(poi_variant)
        if not poi_norm:
            continue
        poi_words = {w for w in poi_norm.split() if len(w) >= 4}

        for work in works:
            work_title = work.get('title', '')
            for title_variant in [_strip_parenthetical_translation(work_title), work_title]:
                title_norm = _normalize(title_variant)
                if not title_norm:
                    continue

                if poi_norm == title_norm:
                    return work

                if not (poi_norm[:10] in title_norm and title_norm[:10] in poi_norm):
                    continue

                title_words = {w for w in title_norm.split() if len(w) >= 4}
                if not poi_words or not title_words:
                    continue
                overlap = len(poi_words & title_words) / max(len(poi_words), len(title_words))
                if overlap >= _CREDIT_LINE_MIN_WORD_OVERLAP:
                    return work

    return None


def build_provenance_block(credit_line):
    """Prompt injection carrying a credit line plus the prohibition. '' when absent."""
    if not credit_line or not credit_line.strip():
        return ''
    # [LOCAL-408] Extract the donor name from "Gift of [Name]" pattern.
    # If a donor is named, make naming them MANDATORY (not permissive).
    _donor_name = ''
    import re as _re_prov
    _gift_match = _re_prov.search(r'Gift of ([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)', credit_line)
    if _gift_match:
        _donor_name = _gift_match.group(1)
    _donor_mandate = ''
    if _donor_name:
        _donor_surname = _donor_name.split()[-1]
        _donor_mandate = (
            f"\nMANDATORY: Name the donor \"{_donor_name}\" (surname \"{_donor_surname}\") "
            f"in your text. Do NOT write \"a gift to the museum\" without naming who gave it.\n"
        )
    return (
        "\nPROVENANCE (museum-published credit line — you MUST name the donor):\n"
        f"  {credit_line.strip()}\n"
        f"{_donor_mandate}"
        f"{PROVENANCE_PROHIBITION}\n"
    )


def recover_medium_from_page_text(work_title, page_text):
    """[LOCAL-380] Attempt to recover a medium/form from exhibition page prose.

    When the structured `medium` field is empty but the page prose describes the
    work's physical form (e.g. "livre d'artiste", "illustrated book"), extract it.

    Returns the recovered medium string, or '' if nothing found.
    """
    if not work_title or not page_text:
        return ''

    # Normalise title for search
    title_lower = work_title.lower().strip()
    page_lower = page_text.lower()

    # Find the title in the page text (or a significant fragment of it)
    title_pos = page_lower.find(title_lower)
    if title_pos == -1:
        # Try first significant words (at least 3 chars each)
        title_words = [w for w in title_lower.split() if len(w) >= 3]
        if len(title_words) >= 2:
            # Search for first two significant words together
            fragment = ' '.join(title_words[:3])
            title_pos = page_lower.find(fragment)
    if title_pos == -1:
        return ''

    # Extract a window around the title mention (300 chars before and after)
    window_start = max(0, title_pos - 300)
    window_end = min(len(page_text), title_pos + len(title_lower) + 300)
    window = page_text[window_start:window_end]

    # Look for medium/form indicators in the window
    _MEDIUM_PATTERNS = [
        # "livre d'artiste" or "livres d'artiste"
        re.compile(r"livres?\s+d['']\s*artiste", re.IGNORECASE),
        # "illustrated book" / "artist's book"
        re.compile(r"(?:illustrated|artist'?s?)\s+book", re.IGNORECASE),
        # "book with N [color] lithographs/etchings/prints"
        re.compile(r"book\s+(?:with|featuring|of)\s+\d+\s+\w*\s*(?:lithograph|etching|print|woodcut|engraving)s?", re.IGNORECASE),
        # "color lithographs" / "original lithographs"
        re.compile(r"\d+\s+(?:color|colour|original)?\s*(?:lithograph|etching|print|woodcut|engraving)s?", re.IGNORECASE),
        # "portfolio of prints"
        re.compile(r"portfolio\s+(?:of|with)\s+\w+\s*(?:lithograph|etching|print|engraving)s?", re.IGNORECASE),
    ]

    for pat in _MEDIUM_PATTERNS:
        m = pat.search(window)
        if m:
            return m.group(0).strip()

    return ''


def extract_collaborator_from_page_text(work_title, artist, page_text):
    """[LOCAL-380] Extract a collaborating writer/poet from exhibition page prose.

    Museum pages often name both the visual artist and the literary collaborator
    for illustrated books (e.g. "Juan Gris and French poet Pierre Reverdy's
    Au Soleil du Plafond"). When the page names a co-author/collaborator near
    the work title, return their name.

    Returns the collaborator name string, or '' if not found.
    """
    if not work_title or not page_text:
        return ''

    title_lower = work_title.lower().strip()
    page_lower = page_text.lower()

    # Find the title in the page text
    title_pos = page_lower.find(title_lower)
    if title_pos == -1:
        title_words = [w for w in title_lower.split() if len(w) >= 3]
        if len(title_words) >= 2:
            fragment = ' '.join(title_words[:3])
            title_pos = page_lower.find(fragment)
    if title_pos == -1:
        return ''

    # Extract a window around the title (400 chars before, 200 after)
    window_start = max(0, title_pos - 400)
    window_end = min(len(page_text), title_pos + len(title_lower) + 200)
    window = page_text[window_start:window_end]

    # Patterns for collaborator mentions near the title
    _COLLAB_PATTERNS = [
        # "Artist and [adjective] [role] Name's Title" or "Artist and Name's Title"
        re.compile(
            r'(?:' + re.escape((artist or '').split()[-1] if artist else '') + r')'
            r'\s+and\s+(?:\w+\s+)?(?:poet|writer|author|novelist)?\s*'
            r'([A-Z][a-z\u00e0-\u00ff]+(?:\s+[A-Z][a-z\u00e0-\u00ff]+)+)',
            re.UNICODE
        ) if artist else None,
        # "with text by Name" / "with poems by Name"
        re.compile(
            r'with\s+(?:text|poems?|prose|writing)\s+by\s+'
            r'([A-Z][a-z\u00e0-\u00ff]+(?:\s+[A-Z][a-z\u00e0-\u00ff]+)+)',
            re.UNICODE
        ),
        # "Name and Artist's Title" (collaborator listed first)
        re.compile(
            r'([A-Z][a-z\u00e0-\u00ff]+(?:\s+[A-Z][a-z\u00e0-\u00ff]+)+)\s+and\s+'
            r'(?:' + re.escape((artist or '').split()[-1] if artist else '') + r')',
            re.UNICODE
        ) if artist else None,
    ]

    for pat in _COLLAB_PATTERNS:
        if pat is None:
            continue
        m = pat.search(window)
        if m:
            name = m.group(1).strip()
            # Reject if the "collaborator" is the artist themselves
            if artist and name.lower() == artist.lower():
                continue
            # Reject if it looks like a place name or institution
            _reject_words = {'museum', 'gallery', 'fine', 'arts', 'institute',
                             'university', 'library', 'press', 'edition'}
            name_words_lower = {w.lower() for w in name.split()}
            if name_words_lower & _reject_words:
                continue
            return name

    return ''


# [LOCAL-381] Words in titles that the model may misread as describing the
# physical form or placement of the artwork.  When any of these appear in the
# title, the work identity block adds a positive disambiguation clause.
_TITLE_MISLEADING_WORDS = frozenset([
    'plafond', 'ceiling', 'mur', 'wall', 'fenêtre', 'fenetre', 'window',
    'soleil', 'sun', 'dome', 'voûte', 'voute', 'vault', 'toit', 'roof',
    'colonne', 'column', 'porte', 'door', 'sol', 'floor', 'ciel', 'sky',
])


def _title_has_misleading_words(title):
    """[LOCAL-381] Return True if title contains words that could be misread as
    describing the object's physical form or architectural placement."""
    if not title:
        return False
    # Tokenize: split on whitespace and punctuation, lowercase
    words = set(re.findall(r"[a-zà-ÿ]+", title.lower()))
    return bool(words & _TITLE_MISLEADING_WORDS)


def build_work_identity_block(matched_work):
    """[LOCAL-379/381] Build a WORK IDENTITY block from any available fields.

    Emits whenever at least ONE of artist, date, medium, publisher, or credit_line
    is available. If medium is empty, explicitly prohibits spatial/medium claims.

    [LOCAL-381] When the title contains words suggesting architecture or placement
    (e.g. "plafond", "ceiling"), adds a positive title disambiguation: the title
    is a title (poetic/metaphorical), NOT a description of the object's form.
    The work identity positively asserts what the object IS when medium is known.

    Returns '' only when matched_work is None or has no usable fields at all.
    """
    if not matched_work:
        return ''

    artist = (matched_work.get('artist') or '').strip()
    date = (matched_work.get('date') or '').strip()
    medium = (matched_work.get('medium') or '').strip()
    publisher = (matched_work.get('publisher') or '').strip()
    credit_line = (matched_work.get('credit_line') or '').strip()
    collaborator = (matched_work.get('collaborator') or '').strip()
    title = (matched_work.get('title') or '').strip()

    # Bail if nothing useful is available
    if not any([artist, date, medium, publisher, credit_line]):
        return ''

    lines = ["\nWORK IDENTITY (LOCAL-379 — grounded facts from exhibition checklist):"]

    if artist:
        lines.append(f"  Artist: {artist}")
    if collaborator:
        lines.append(f"  Collaborator: {collaborator}")
    if date:
        lines.append(f"  Date: {date}")
    if medium:
        lines.append(f"  Medium: {medium}")
    else:
        lines.append("  Medium: UNKNOWN — do NOT describe physical form, placement, "
                     "or spatial relationship. Do NOT say 'painting', 'sculpture', "
                     "'ceiling', 'installation', 'mural', 'glass', or assert any medium. "
                     "Do NOT tell the visitor where to stand or look. "
                     "Do NOT use phrases like 'look up', 'stand beneath', "
                     "'positioned above you', or describe the work's physical orientation. "
                     "The work's physical form is unknown — prefer stating what IS known "
                     "(artist, date, collaborator, publisher) at greater length.")
    if publisher:
        lines.append(f"  Publisher: {publisher}")
    if credit_line:
        lines.append(f"  Credit line: {credit_line}")

    # [LOCAL-381] Title disambiguation — positive assertion that the title is a
    # title, not a description of the object's form or location.
    _title_misleads = _title_has_misleading_words(title)
    if _title_misleads:
        lines.append("")
        lines.append(
            f"  TITLE NOTE: \"{title}\" is the TITLE of this work — a poetic or "
            f"metaphorical name. It does NOT describe the object's physical form, "
            f"material, or placement in the gallery. Words in the title that "
            f"suggest architecture or location (ceiling, wall, sun, sky, etc.) "
            f"refer to the work's SUBJECT or IMAGERY, never its physical medium. "
            f"This object is NOT a ceiling, NOT an installation, NOT a mural, "
            f"NOT glass — it is {'a ' + medium if medium else 'a book/printed work (livre d artiste)'}."
        )

    lines.append("")  # trailing newline separator
    lines.append("You MUST name the artist in your description. If a collaborator or "
                 "author is given, name them too. These are grounded facts — use them.")
    if not medium:
        lines.append("ORIENTATION CONSTRAINT: Since the medium/form is unknown, your "
                     "Orientation section must NOT give spatial directions (where to stand, "
                     "where to look, what is above/below/beside). Instead, simply name the "
                     "work and introduce what is known about it (artist, date, context).")
        lines.append("MINIMUM LENGTH: You have grounded facts (artist, date, collaborator, "
                     "publisher). Write at LEAST 120 words using these facts — discuss the "
                     "artist's career, the collaboration, the historical context. Do NOT "
                     "cut the description short.")
    lines.append("")

    return '\n'.join(lines)

def r4_scope_cap(exhibition_scope, poi_list_len, total_stops):
    """
    [LOCAL-370] Decide whether R4 replenishment may run, and the honest stop count.

    Returns (suppressed, capped_total_stops).

    D275: an unsatisfiable scope must produce a SHORTER, honest tour rather than
    backfill. LOCAL-362 suppressed the deterministic bypass for scoped requests
    but not replenishment, so venue-wide fill returned through a different door —
    the 2026-08-10 MFA run delivered seven venue-wide works that way (D284).

    At module scope because the guard otherwise lives only in a while-loop
    condition inside a 7,900-line function, and the submitted tests for it
    re-implemented that condition inline and passed against a reverted tree
    (D277/D285). This is the third recurrence; lifting is the remedy that works.
    """
    suppressed = exhibition_scope is not None
    if suppressed and poi_list_len < total_stops:
        return True, poi_list_len
    return suppressed, total_stops


# [LOCAL-420] Stub detection and material fallback — module-level for testability.
# A listener must never be told the system failed.
_STUB_TAIL = "A detailed narration could not be generated for this stop."


def _is_stub_text(text):
    """[LOCAL-420] Return True if text is the empty-stop stub that must never ship."""
    if not text:
        return False
    return _STUB_TAIL in text


def _build_material_fallback(poi_name, artist, matched_work, credit_line, candidate_specifics):
    """[LOCAL-420] Build a short, factual paragraph from whatever material IS on hand.

    A listener must never be told the system failed. When no LLM attempt passes
    the gate, we still have: the work title, artist, medium, credit line, and any
    candidate specifics extracted from snippets. Build a real (if thin) narration
    from those. The result won't pass the positive gate's "concrete fact" check
    in most cases, but it IS real prose that a listener can hear without
    embarrassment — unlike the stub.
    """
    parts = []

    # Opening: name the work and artist
    if artist and artist.strip() and artist.strip().lower() not in ('unknown', 'n/a', 'various'):
        parts.append(f"{poi_name} is a work by {artist}.")
    else:
        parts.append(f"Here we have {poi_name}.")

    # Medium / technique from matched_work
    if matched_work:
        medium = (matched_work.get('medium') or '').strip()
        if medium:
            parts.append(f"This piece is executed in {medium.lower()}.")
        date = (matched_work.get('date') or '').strip()
        if date:
            parts.append(f"It dates to {date}.")
        collaborator = (matched_work.get('collaborator') or '').strip()
        if collaborator:
            parts.append(f"It was created in collaboration with {collaborator}.")

    # Credit line (provenance)
    if credit_line:
        # Use credit line as-is if it's short; summarize if long
        if len(credit_line) <= 120:
            parts.append(credit_line.rstrip('.') + '.')
        else:
            # Take first sentence of credit line
            first_sent = credit_line.split('.')[0].strip()
            if first_sent:
                parts.append(first_sent + '.')

    # Candidate specifics from snippet extraction
    if candidate_specifics:
        # Pick up to 3 most informative specifics
        _specs = []
        for cs in candidate_specifics[:3]:
            # Format: "material: lithograph on vellum" → "lithograph on vellum"
            if ':' in cs:
                val = cs.split(':', 1)[1].strip()
            else:
                val = cs.strip()
            # [LOCAL-420] Filter out broken specifics (too short or clearly not a fact)
            if val and len(val) > 3 and ' ' in val:
                _specs.append(val)
        if _specs:
            parts.append("Notable details include " + ", ".join(_specs) + ".")

    # Ensure we have at least something beyond just the opening line
    result = " ".join(parts)
    return result


def resolve_final_description(attempts, material_context):
    """[LOCAL-422] Resolve the final description from attempt history.

    This is the decision that the per-stop generation loop makes when all
    retries are exhausted (gate failure, refusal persists, etc.):
      1. Track the best valid description across attempts — stubs are excluded.
      2. If a valid best exists, return it. Otherwise build a material fallback.

    Args:
        attempts: list of dicts, each with keys:
            'description' (str): the generated text for this attempt
            'orientation' (str): orientation text
            'word_count' (int): word count
            'tokens_used' (int): tokens consumed
            'call_cost' (float): cost of the call
        material_context: dict with keys:
            'poi_name' (str): name of the point of interest
            'artist' (str): artist name
            'matched_work' (dict or None): matched work metadata
            'credit_line' (str): credit line text
            'candidate_specifics' (list): extracted specifics from snippets

    Returns:
        str: the final description that ships to the listener
    """
    # Track the best valid description — stubs excluded via _is_stub_text.
    _best = None  # (orientation, description, word_count, tokens_used, call_cost)
    for attempt in attempts:
        desc = attempt.get('description', '')
        if desc and not _is_stub_text(desc):
            wc = len(desc.split())
            best_wc = _best[2] if _best else 0
            if wc > best_wc:
                _best = (
                    attempt.get('orientation', ''),
                    desc,
                    wc,
                    attempt.get('tokens_used', 0),
                    attempt.get('call_cost', 0.0),
                )

    # Resolution: prefer best valid attempt; else build from material.
    if _best:
        return _best[1]
    return _build_material_fallback(
        material_context['poi_name'],
        material_context['artist'],
        material_context.get('matched_work'),
        material_context.get('credit_line', ''),
        material_context.get('candidate_specifics', []),
    )


def verify_stop_claims(story_text: str, snippets: list, credit_line: str = '',
                       stop_name: str = '') -> dict:
    """Verify a single stop's claims against its source snippets.

    This is the production decision function — the same logic that runs inside
    generate_tour_text after story generation. It:
      1. Calls verify_story_candidate (from story_verifier)
      2. Applies D369's vacuous-check: 0 claims extracted → forced FAIL
      3. Returns the verification result dict

    Extracted as a standalone function so tests can bind to it directly.
    """
    from story_verifier import verify_story_candidate

    result = verify_story_candidate(
        story_text=story_text,
        snippets=snippets,
        credit_line=credit_line,
        stop_name=stop_name,
    )

    # [LEAD, D369] A verifier that extracted ZERO claims has verified NOTHING.
    if result['claims_extracted'] == 0:
        result['passed'] = False
        result.setdefault('rejection_reasons', []).append(
            'VACUOUS: 0 claims extracted — nothing was verified')

    return result


def _extract_city_from_resolved_entity(venue_entity) -> str:
    """Extract city name from a VenueEntity by inspecting its name and URL.

    Used by LOCAL-465 exhibition resolution gate to compare the resolved
    venue's city against the city in the user's request.
    """
    # Check if the venue name contains a city after a comma
    # e.g. "Museum of Fine Arts, Houston" → "Houston"
    name = getattr(venue_entity, 'name', '') or ''
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        for p in parts[1:]:
            if p and p[0].isupper():
                return p

    # Heuristic from URL domain — known museum abbreviation patterns
    url = getattr(venue_entity, 'official_url', '') or ''
    _DOMAIN_CITY_MAP = {
        'mfah.org': 'Houston',
        'mfa.org': 'Boston',
        'metmuseum.org': 'New York',
        'artic.edu': 'Chicago',
        'lacma.org': 'Los Angeles',
        'sfmoma.org': 'San Francisco',
        'nga.gov': 'Washington',
        'philamuseum.org': 'Philadelphia',
        'dma.org': 'Dallas',
    }
    url_lower = url.lower()
    for domain, city in _DOMAIN_CITY_MAP.items():
        if domain in url_lower:
            return city

    return ''


def generate_tour_text(location, tour_type, output_file=None, total_stops=None, persona=None, user_id=None, job_id=None, forced_stops=None):
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
        user_id: Optional user_id for cost attribution (LOCAL-323).
                 Threaded to spine_generator for per-operation ledger rows.
        job_id: Optional job correlation ID for cost_meter recording.
        forced_stops: Optional list of stop names (LOCAL-357 verification harness).
                 When provided, bypasses Phase 3A candidate generation entirely
                 and uses these exact stop names in the given order.
                 Everything downstream (corpus, enrichment, gates) runs unchanged.
                 The output is stamped with a FORCED STOPS banner so it cannot be
                 mistaken for a naturally-generated tour.
                 THIS IS A VERIFICATION HARNESS — NOT A PRODUCT FEATURE.
    
    Returns:
        tuple: (tour_text, output_file, coordinates)
    """
    import api_call_logger

    # [LOCAL-230] Reset per-run network failure counter
    try:
        from venue_resolver import reset_network_failure_count
        reset_network_failure_count()
    except ImportError:
        pass

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
                _import_logger.error("[Storied] MISSING: onboarding_preference (UserPersona, PERSONA_TONE_OVERRIDE) — persona customization DISABLED")
                print(f"  [Storied] onboarding_preference not available — persona skipped")
                _persona_enum = None
                _persona_tone = ""
    api_call_logger.log("GENERATE_TOUR_TEXT_FUNCTION_ENTRY", {
        "location": location,
        "tour_type": tour_type,
        "total_stops_parameter": total_stops,
        "output_file": output_file,
    })

    # [LOCAL-245] Log existence gate mode at startup — single source of truth
    try:
        from stop_existence_gate import get_gate_mode
        _existence_gate_mode = get_gate_mode()
        print(f"  [LOCAL-245] Stop-existence gate mode: {_existence_gate_mode.upper()}")
    except ImportError:
        _existence_gate_mode = 'off'
        print(f"  [LOCAL-245] Stop-existence gate: unavailable (import failed)")

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
    
    # [LOCAL-60] Declare global for cost exposure
    global _LAST_GENERATION_COST
    global _LAST_POI_LIST  # [LOCAL-326] needed for partial-tour early returns
    global _DIRECT_SNIPPETS_PER_STOP  # [LOCAL-410] Allow generation path to populate search results

    # -------- [S20] Storied: check tour cache before generation --------
    _cache_hit = None
    _disable_cache = os.environ.get("DISABLE_TOUR_CACHE", "").strip() == "1"
    if _storied_mode and not _disable_cache:
        _db_url = os.environ.get("DATABASE_URL")
        if _db_url:
            try:
                from tour_cache_layer1 import get_cached_tour
                _cache_hit = get_cached_tour(location, tour_type, total_stops, _db_url)
                if _cache_hit:
                    print(f"CACHE HIT: {location} / {tour_type} / {total_stops}")
                    # [LOCAL-60] Record cache hit cost = 0
                    _LAST_GENERATION_COST = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "cache_hit": True,
                        "breakdown": {"llm": 0.0, "tts": 0.0, "search": 0.0},
                    }
                    # Return cached tour immediately
                    if output_file:
                        with open(output_file, "w", encoding="utf-8") as _cf:
                            _cf.write(_cache_hit)
                    return _cache_hit, output_file, (None, None)
                else:
                    print(f"CACHE MISS: {location} / {tour_type} / {total_stops}")
            except ImportError:
                _import_logger.error("[S20] MISSING: tour_cache_layer1 (get_cached_tour) — tour caching DISABLED")
                print(f"  [S20] tour_cache_layer1 not available — cache skipped")
            except Exception as e:
                print(f"  [S20] Cache check error: {e}")
        else:
            print(f"  [S20] DATABASE_URL not set — cache skipped")

    # [LOCAL-445-B] Phase timing instrumentation
    from phase_timer import PhaseTimer
    _phase_timer = PhaseTimer()

    # PHASE 1: Analyze user intent with AI
    _phase_timer.start('intent')
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

    # [LOCAL-46 Bug A] Strip transport-mode keywords from the normalized location.
    # After "tour" is stripped, orphaned words like "biking" remain and poison
    # area resolution (e.g. "French Riviera biking" cannot resolve on Wikidata).
    # Uses _TRANSPORT_STRIP_RE derived from _TRANSPORT_MODE_KEYWORDS — single source of truth.
    _loc_before_transport_strip = _location_normalized
    _location_normalized = _TRANSPORT_STRIP_RE.sub('', _location_normalized)
    # Collapse multiple spaces and clean up
    _location_normalized = re.sub(r'\s{2,}', ' ', _location_normalized).strip().strip(',').strip()
    if _location_normalized != _loc_before_transport_strip:
        print(f"  [LOCAL-46] Stripped transport words: '{_loc_before_transport_strip}' → '{_location_normalized}'")
    
    _pre_category = _classify_tour_category(_location_normalized, "")
    if _pre_category in ('restaurant', 'walking', 'specialized'):
        # Location string already encodes the real intent — don't prepend tour_type
        user_request = _location_normalized
        print(f"  [Bug2Fix] tour_type='{tour_type}' suppressed for intent analysis (pre_category='{_pre_category}'); using location only")
    else:
        user_request = f"{tour_type} {_location_normalized}"
    intent = analyze_tour_intent(user_request, api_key)

    # Transport mode detection (Layer 1: keyword, Layer 2: intent field)
    _transport_keyword = _detect_transport_mode(location)
    _transport_from_intent = (intent.get('transport_mode', 'on_foot') if intent else 'on_foot')
    # Keyword match takes priority; fall back to intent's answer
    transport_mode = _transport_keyword if _transport_keyword != 'on_foot' else _transport_from_intent
    _country_scope = intent.get('country_scope') if intent else None
    print(f"  [TRANSPORT] mode={transport_mode}, country_scope={_country_scope} (keyword={_transport_keyword}, intent={_transport_from_intent})")

    # Guardrail: detect potential unrecognized transport modes in the location text
    _unrecognized_mode_re = re.compile(r'\b(\w+)(?:back)?\s+(?:riding|ridding|sledding|drawn)\s+tour\b', re.IGNORECASE)
    _unrecognized_match = _unrecognized_mode_re.search(location)
    if _unrecognized_match and transport_mode == 'on_foot':
        _candidate_word = _unrecognized_match.group(1).lower()
        if _candidate_word not in ('self', 'walking', 'sight'):  # exclude false positives
            print(f"  [TRANSPORT] UNRECOGNIZED MODE CANDIDATE: '{_candidate_word}' — using intent LLM answer: {_transport_from_intent}")
    
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
        if intent.get('venue_name') and transport_mode == 'on_foot' and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
            tour_category = 'museum'
            print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
        else:
            if intent.get('venue_name'):
                if _MULTI_BUILDING_INSTITUTION_RE.search(location):
                    print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains multi-building institution keyword")
                else:
                    print(f"  [S15] venue_name='{intent['venue_name']}' overridden — location contains explicit non-museum phrase")
            # Touchpoint 1: suppress tour_type when pre_category or transport_mode gives a strong signal
            _effective_tour_type = "" if (_pre_category in ('restaurant', 'specialized') or transport_mode != 'on_foot') else tour_type
            tour_category = _classify_tour_category(location, _effective_tour_type)
            if tour_category == 'specialized':
                tour_category = 'book'
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        # Touchpoint 1: suppress tour_type when pre_category or transport_mode gives a strong signal
        _effective_tour_type = "" if (_pre_category in ('restaurant', 'specialized') or transport_mode != 'on_foot') else tour_type
        tour_category = _classify_tour_category(location, _effective_tour_type)
        if tour_category == 'specialized':
            tour_category = 'book'
    
    # [CLASSIFY-FIX] Venue-indicator override — runs ONCE after both branches converge.
    # If tour_category is 'walking' but the location string contains known venue words
    # (palais, museum, gallery, etc.), override to 'museum'. This catches BOTH failure modes:
    # (1) intent extraction returned None entirely (second branch above)
    # (2) intent succeeded but venue_name=null, S15 didn't fire (first branch, else clause)
    _VENUE_WORDS_FOR_CLASSIFY = {'museum', 'musée', 'musee', 'gallery', 'galleria', 'palais',
                                 'palazzo', 'palace', 'castle', 'château', 'house', 'mansion',
                                 'cathedral', 'basilica', 'library', 'institute', 'villa',
                                 'temple', 'church', 'abbey'}
    if tour_category == 'walking':
        _loc_words = set(location.lower().split())
        if _loc_words & _VENUE_WORDS_FOR_CLASSIFY:
            _matched_word = (_loc_words & _VENUE_WORDS_FOR_CLASSIFY).pop()
            print(f"  [CLASSIFY-FIX] Location contains venue word '{_matched_word}' — overriding walking → museum")
            tour_category = 'museum'
    
    # PHASE 2: Detect tour type and get appropriate template
    _phase_timer.start('poi_selection')
    # NOTE: tour_category already set above — do NOT call _classify_tour_category again here
    # (that was the bug: it overwrote the venue_name-based 'museum' decision with 'walking').
    # [LOCAL-46 Bug B] Display the transport mode as the detected category when applicable.
    # The logical tour_category stays 'walking' (same verification/template path) but the
    # reported category reflects what the user actually asked for.
    _display_category = tour_category
    if tour_category == 'walking' and transport_mode != 'on_foot':
        _display_category = transport_mode.upper()  # e.g. "BIKE", "VEHICLE", "ANIMAL"
    else:
        _display_category = tour_category.upper()
    print(f"\nDetected tour category: {_display_category}")
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

    # Transport-mode stop constraint (KIRO_REVIEW_09, Issue 1 Part A)
    _TRANSPORT_STOP_CONSTRAINTS = {
        'animal': ("\nCRITICAL CONSTRAINT — THIS IS A CAMELBACK/HORSEBACK TOUR:\n"
                   "Every stop MUST be reachable on horse/camel-back along an outdoor route "
                   "(trails, dunes, oases, open landscape). Do NOT suggest stops that require "
                   "entering a building, a paved shopping district, or any location primarily "
                   "accessed by car — those are not reachable as part of this ride.\n"),
        'bike': ("\nCRITICAL CONSTRAINT — THIS IS A BIKING TOUR:\n"
                 "Stops should be reachable via bike paths, roads, or trails suitable for cycling "
                 "— avoid stops requiring highway travel or building interiors inaccessible by bike.\n"),
        'vehicle': ("\nCRITICAL CONSTRAINT — THIS IS A DRIVING TOUR:\n"
                    "Stops should be reachable by car and have parking or roadside access.\n"),
    }
    _transport_stop_constraint = _TRANSPORT_STOP_CONSTRAINTS.get(transport_mode, "")

    # [LOCAL-285] Restaurant/dining venue constraint — guides Phase 3A toward actual
    # eating establishments rather than museums or landmarks that happen to be notable.
    # [LOCAL-329] Enhanced: asks for notability reasons to select by documentedness.
    _restaurant_venue_constraint = ""
    if tour_category == 'restaurant':
        # Determine the area name for the constraint
        _restaurant_area = (intent.get('geographic_scope') or '').strip() if intent else ''
        if not _restaurant_area:
            # Fall back to location (e.g. "Nice, France")
            _restaurant_area = location
        _restaurant_venue_constraint = (
            f"\nCRITICAL CONSTRAINT — THIS IS A RESTAURANT/DINING TOUR:\n"
            f"- Every stop MUST be a named, real, currently-operating eating establishment "
            f"(restaurant, bistro, brasserie, café, trattoria, tavern, or similar).\n"
            f"- Each stop must have a verifiable street address in or near {_restaurant_area}.\n"
            f"- Do NOT include museums, galleries, parks, monuments, or any non-dining venue.\n"
            f"- Do NOT include fictional or closed restaurants.\n"
            f"- Prefer restaurants that are NOTABLE and DOCUMENTED — venues that people write "
            f"about because they have a distinctive story (founding year, named chef, "
            f"signature dish, culinary tradition, architectural feature, historical event).\n"
            f"- For each restaurant, include a 'reason' field explaining WHY it is notable. "
            f"The reason must cite a SPECIFIC fact: a year, a named person, a named dish, "
            f"a documented tradition, or a verifiable event. "
            f"Do NOT use vague phrases like 'popular', 'top-ranked', 'well-known', "
            f"or 'appears in many lists'.\n"
            f"- Include a mix of styles/price ranges unless the request specifies otherwise.\n"
        )
        print(f"  [LOCAL-285/329] Restaurant constraint injected for area='{_restaurant_area}'")

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
        if transport_mode == 'on_foot':
            _compactness_constraint = (
                f"\nWALKING-TOUR COMPACTNESS — this is a walking tour:\n"
                f"- All stops must form ONE compact cluster, close enough to walk between comfortably.\n"
                f"- No stop should be more than a 10–15 minute walk (roughly {WALKING_LEG_TARGET_KM:.0f} km) "
                f"from its nearest neighbour in the tour.\n"
                f"- Prefer a tight set of stops in one walkable area over famous landmarks scattered "
                f"across the city. A shorter, denser route is better than a long, spread-out one.\n"
                f"- Prefer landmarks that are DOCUMENTED — places with a specific story (a date, "
                f"a named architect, a historical event). Include a 'reason' for each.\n"
            )
        elif transport_mode == 'bike':
            # [LOCAL-46] Biking tour: wider spacing, route coherence still matters
            _bike_limit = _TRANSPORT_TOTAL_HARD_KM.get('bike', 120)
            _compactness_constraint = (
                f"\nBIKING-TOUR ROUTE — this is a cycling/biking tour:\n"
                f"- Stops should form a coherent route that a cyclist can follow in sequence.\n"
                f"- Adjacent stops may be up to 5–10 km apart (a comfortable cycling leg).\n"
                f"- Total route length should stay under {_bike_limit} km.\n"
                f"- Prefer scenic roads, coastal paths, or designated cycling routes.\n"
                f"- Stops should be accessible by bicycle (not inside buildings or pedestrian-only zones).\n"
            )
        elif transport_mode == 'vehicle':
            _vehicle_limit = _TRANSPORT_TOTAL_HARD_KM.get('vehicle', 400)
            _compactness_constraint = (
                f"\nDRIVING-TOUR ROUTE — this is a driving/vehicle tour:\n"
                f"- Stops should form a coherent driving route in logical sequence.\n"
                f"- Adjacent stops may be 10–50 km apart.\n"
                f"- Total route length should stay under {_vehicle_limit} km.\n"
                f"- Stops should be accessible by car with parking available nearby.\n"
            )
        elif transport_mode == 'animal':
            _animal_limit = _TRANSPORT_TOTAL_HARD_KM.get('animal', 20)
            _compactness_constraint = (
                f"\nANIMAL-POWERED TOUR ROUTE — this is an animal-powered tour:\n"
                f"- Stops should form a coherent trail route suitable for the animal.\n"
                f"- Adjacent stops should be 1–3 km apart.\n"
                f"- Total route length should stay under {_animal_limit} km.\n"
                f"- Stops should be on trails or terrain accessible to the animal.\n"
            )
        elif transport_mode == 'country_scale':
            _compactness_constraint = (
                f"\nCROSS-COUNTRY ROUTE — this is a long-distance tour:\n"
                f"- Stops should form a coherent route across the region/country.\n"
                f"- Include major landmarks and points of interest along the way.\n"
                f"- Route should be geographically logical (no random zig-zagging).\n"
            )

    # -------- [LOCAL-30] DETERMINISTIC SELECTION: documented works fill first --------
    # When a museum venue has enough catalogue/SPARQL works to fill the tour,
    # use those directly as Phase 3A output. No GPT randomness, no fabrication.
    # This is the ONLY path that guarantees reproducibility.
    # [LOCAL-362] SUPPRESSED when a scoped request (exhibition/artist filter) is detected.
    _deterministic_fill_used = False
    # Pre-compute scope detection for the early block (full detection runs below)
    _early_scope_detected = False
    if intent and intent.get('venue_name') and tour_category == 'museum':
        _early_req = (intent.get('requirements') or '').strip()
        _early_poi = (intent.get('poi_type') or '').strip().lower()
        # LOCAL-362: Same logic as main scope detection — exact match for poi_type
        _early_poi_is_exhibition = _early_poi in ('exhibit', 'exhibition', 'exhibits')
        if _early_req or _early_poi_is_exhibition:
            _early_scope_detected = True
            print(f"  [LOCAL-362] Scoped request detected (requirements='{_early_req}') — "
                  f"early deterministic bypass suppressed")
    if tour_category == 'museum' and _museum_venue_name and not _early_scope_detected:
        try:
            from venue_resolver import resolve_venue, fetch_venue_works, build_canonical_titles_from_works, cache_get as _det_cache_get
            from story_miner import extract_catalogue_works_from_pages, fetch_venue_narrative_corpus
            
            _det_city_hint = ""
            if "," in location:
                parts = [p.strip() for p in location.split(",")]
                _det_city_hint = parts[1] if len(parts) >= 2 else ""
            _det_entity = resolve_venue(_museum_venue_name, _det_city_hint)
            
            if _det_entity and _det_entity.qid:
                # Gather documented works from all sources
                _det_documented = []  # List of {title, source} dicts
                _det_seen_titles_norm = set()
                
                from story_miner import _normalize as _det_norm
                
                # Source 1: Catalogue works (highest confidence — museum-published)
                _det_cache = _det_cache_get(_det_entity.qid) if _det_entity.qid else None
                _det_catalogue_works = []
                if _det_cache and _det_cache.get('pages'):
                    _det_pages = _det_cache['pages']
                    if isinstance(_det_pages, list):
                        _det_catalogue_works = extract_catalogue_works_from_pages(_det_pages)
                
                for cw in _det_catalogue_works:
                    _t = cw.get('title', '').strip()
                    _tn = _det_norm(_t)
                    if _t and _tn not in _det_seen_titles_norm:
                        _det_documented.append({'title': _t, 'source': 'catalogue',
                                                'material': cw.get('material', ''),
                                                'period': cw.get('period', ''),
                                                'origin': cw.get('origin', '')})
                        _det_seen_titles_norm.add(_tn)
                
                # Source 2: SPARQL works (Wikidata-verified, second highest)
                _det_sparql = fetch_venue_works(_det_entity.qid, _det_entity.language)
                _det_sparql_seen_qids = set()
                for w in _det_sparql:
                    _wqid = w.get('qid', '')
                    if _wqid in _det_sparql_seen_qids:
                        continue
                    _det_sparql_seen_qids.add(_wqid)
                    _t = w.get('label_local', '') or w.get('label_en', '')
                    _tn = _det_norm(_t)
                    if _t and _tn not in _det_seen_titles_norm:
                        _det_documented.append({'title': _t, 'source': 'sparql'})
                        _det_seen_titles_norm.add(_tn)
                
                # Source 3: Cached canonical titles that survived LOCAL-24 filter
                if _det_cache and _det_cache.get('canonical_titles'):
                    for _ct in _det_cache['canonical_titles']:
                        _tn = _det_norm(_ct)
                        if _ct and _tn not in _det_seen_titles_norm:
                            _det_documented.append({'title': _ct, 'source': 'canonical'})
                            _det_seen_titles_norm.add(_tn)
                
                print(f"  [LOCAL-30] Deterministic selection: {len(_det_documented)} documented works "
                      f"({len(_det_catalogue_works)} catalogue, {len(_det_sparql_seen_qids)} SPARQL)")
                
                # If documented works >= total_stops, fill deterministically
                if len(_det_documented) >= total_stops:
                    # Priority order: catalogue first (richest metadata), then SPARQL, then canonical
                    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
                    _det_documented.sort(key=lambda d: _priority.get(d['source'], 9))
                    
                    # Apply bare-noun filter (shouldn't be needed but defence-in-depth)
                    from story_miner import is_bare_generic_noun
                    _det_documented = [d for d in _det_documented if not is_bare_generic_noun(d['title'])]
                    
                    # Take total_stops * 2 (D1v2 will filter, so give it room)
                    _det_take = min(len(_det_documented), total_stops * 2)
                    poi_list = [_new_poi(d['title']) for d in _det_documented[:_det_take]]
                    
                    print(f"  [LOCAL-30] DETERMINISTIC BYPASS: {len(poi_list)} documented works → Phase 3A SKIPPED")
                    print(f"   Stops proposed (deterministic, no GPT):")
                    for p in poi_list[:total_stops]:
                        _src = next((d['source'] for d in _det_documented if d['title'] == p['name']), '?')
                        print(f"     - {p['name']} [{_src}]")
                    _deterministic_fill_used = True
                else:
                    print(f"  [LOCAL-30] Documented works ({len(_det_documented)}) < total_stops ({total_stops}) "
                          f"— will use documented as base, GPT fills remainder")
        except Exception as _det_err:
            print(f"  [LOCAL-30] Deterministic selection check failed (falling through to Phase 3A): {_det_err}")
            import traceback
            traceback.print_exc()

    # ──── [LOCAL-357] FORCED STOPS HARNESS ────────────────────────────────────
    # When forced_stops is provided, bypass ALL candidate generation (Phase 3A,
    # LOCAL-30 deterministic selection) and inject the exact stop list.
    # Everything downstream (D1v2 verification, existence gate, corpus loading,
    # enrichment, composition, QA gates) runs unchanged.
    # THIS IS A VERIFICATION HARNESS — NOT A PRODUCT FEATURE.
    _forced_stops_active = False
    if forced_stops is not None and len(forced_stops) > 0:
        _forced_stops_active = True
        poi_list = [_new_poi(name) for name in forced_stops]
        # Override total_stops to match the forced list length
        total_stops = len(forced_stops)
        print(f"\n{'=' * 70}")
        print(f"[LOCAL-357] FORCED STOPS ACTIVE — verification harness mode")
        print(f"  Stops forced: {forced_stops}")
        print(f"  Count: {len(forced_stops)}")
        print(f"  All downstream gates and corpus loading will run unchanged.")
        print(f"{'=' * 70}")
        # Skip selection-reason tracking (no GPT selection happened)
        _selection_reasons = {}
    # ──── END [LOCAL-357] FORCED STOPS ────────────────────────────────────────

    # ──── [LOCAL-362] EXHIBITION-SCOPED REQUEST DETECTION ─────────────────────
    # When Phase 1 returns a non-empty `requirements` (or poi_type contains
    # 'exhibit') alongside a venue_name, the tour is scoped to something
    # INSIDE the venue — e.g. a named exhibition, a specific artist's works,
    # a particular gallery wing. The deterministic bypass (which fills from
    # the venue's most-documented works) is exactly wrong for this case.
    _exhibition_scope = None  # None = unscoped, else dict with scope info
    _exh_name_resolved = ''   # [D506] set when the checklist is fetched
    _exhibition_scope_artists = []  # Artist names extracted from requirements

    if intent and intent.get('venue_name') and tour_category == 'museum':
        _scope_requirements = (intent.get('requirements') or '').strip()
        _scope_poi_type = (intent.get('poi_type') or '').strip().lower()
        # LOCAL-362: Scope detection. A request is scoped when:
        # 1. requirements is non-empty (primary signal — Phase 1 identified criteria), OR
        # 2. poi_type is exactly "exhibit" or "exhibition" (not "museum exhibits" which is generic)
        _poi_is_exhibition = _scope_poi_type in ('exhibit', 'exhibition', 'exhibits')
        _is_scoped = bool(_scope_requirements) or _poi_is_exhibition

        if _is_scoped:
            # Extract artist names from requirements and/or from the original request
            # Pattern: "Picasso, Miró, Dalí: Unbound exhibition" → artists = [Picasso, Miró, Dalí]
            # Also handles: "Impressionist paintings" (no specific artists)
            import unicodedata as _ud362
            
            def _extract_scope_artists(request_text: str, requirements: str) -> list:
                """Extract artist names from a scoped exhibition request.
                
                Looks for patterns like:
                - "Picasso, Miró, Dalí: exhibition name"
                - "Picasso and Miró exhibition"
                - "works by Picasso"
                """
                artists = []
                
                # Pattern 1: "Name1, Name2, Name3: ..." (colon-separated prefix)
                _colon_match = re.match(r'^([^:]+):\s*', request_text)
                if _colon_match:
                    _prefix = _colon_match.group(1)
                    # Split by comma and 'and'
                    _parts = re.split(r'\s*,\s*|\s+and\s+', _prefix)
                    for p in _parts:
                        p = p.strip()
                        # Must look like a name: capitalized, 1-3 words, not a stop word
                        _name_words = p.split()
                        if (1 <= len(_name_words) <= 4 and 
                            all(w[0].isupper() for w in _name_words if w) and
                            p.lower() not in ('the', 'a', 'an', 'some')):
                            artists.append(p)
                
                # Pattern 2: "works by X" / "art by X" in requirements
                if not artists and requirements:
                    _by_match = re.search(r'\b(?:works?|art|paintings?|sculptures?)\s+by\s+(.+)', 
                                         requirements, re.IGNORECASE)
                    if _by_match:
                        _by_text = _by_match.group(1)
                        _parts = re.split(r'\s*,\s*|\s+and\s+', _by_text)
                        for p in _parts:
                            p = p.strip().rstrip('.')
                            _name_words = p.split()
                            if 1 <= len(_name_words) <= 4 and all(w[0].isupper() for w in _name_words if w):
                                artists.append(p)
                
                # Pattern 3: "X and Y exhibition" / "X, Y exhibition" in requirements
                if not artists and requirements:
                    _exh_match = re.match(r'^(.+?)\s+exhibition\b', requirements, re.IGNORECASE)
                    if _exh_match:
                        _exh_prefix = _exh_match.group(1)
                        _parts = re.split(r'\s*,\s*|\s+and\s+', _exh_prefix)
                        for p in _parts:
                            p = p.strip()
                            _name_words = p.split()
                            if 1 <= len(_name_words) <= 4 and all(w[0].isupper() for w in _name_words if w):
                                artists.append(p)
                
                return artists
            
            _exhibition_scope_artists = _extract_scope_artists(location, _scope_requirements)
            
            _exhibition_scope = {
                'requirements': _scope_requirements,
                'poi_type': _scope_poi_type,
                'artists': _exhibition_scope_artists,
                'venue_name': intent['venue_name'],
            }
            print(f"\n  [LOCAL-362] SCOPED REQUEST DETECTED:")
            print(f"    Requirements: {_scope_requirements}")
            print(f"    POI type: {_scope_poi_type}")
            print(f"    Artists extracted: {_exhibition_scope_artists}")
            print(f"    → Deterministic bypass will be SUPPRESSED (venue-wide fill is wrong for scoped requests)")
    # ──── END [LOCAL-362] ─────────────────────────────────────────────────────

    # -------- [LOCAL-30] DETERMINISTIC SELECTION: documented works fill first --------
    # When a museum venue has enough catalogue/SPARQL works to fill the tour,
    # use those directly as Phase 3A output. No GPT randomness, no fabrication.
    # This is the ONLY path that guarantees reproducibility.
    _deterministic_fill_used = False
    # [LOCAL-364] Track which path produced the stops for exhibition-scoped requests.
    # Used downstream for honest-degradation labelling in the tour text.
    _exhibition_stops_source = 'none'  # 'checklist', 'partial', 'prose_llm', 'creator_filter', 'none'
    _exhibition_checklist_result = None
    if _forced_stops_active:
        # [LOCAL-357] forced_stops bypasses ALL selection — mark as deterministic
        _deterministic_fill_used = True
        _exhibition_stops_source = 'checklist'
        print(f"\nPHASE 3A: SKIPPED (forced stops — LOCAL-357 verification harness)")
        print(f"OK PHASE 3A parsed {len(poi_list)} candidate POI(s):")
        for p in poi_list:
            print(f"   - {p['name']} [FORCED]")
    elif _exhibition_scope is not None:
        # ──── [LOCAL-364] EXHIBITION CHECKLIST RETRIEVAL ──────────────────────
        _phase_timer.start('exhibition_checklist')
        # PRIMARY PATH: Retrieve the actual exhibition object list from the
        # venue's own site. The LOCAL-362 creator filter becomes the FALLBACK.
        # An exhibition is a specific, curated, time-bound checklist — not the
        # set of works by its headline artists that the venue happens to own.
        _exhibition_checklist_result = None
        _exhibition_stops_source = 'none'  # 'checklist', 'partial', 'prose_llm', 'creator_filter', 'none'

        try:
            from exhibition_checklist import find_exhibition_checklist, ExhibitionChecklistResult
            from venue_resolver import resolve_venue, fetch_venue_works, cache_get as _det_cache_get
            from story_miner import extract_catalogue_works_from_pages
            from story_miner import _normalize as _det_norm

            _det_city_hint = ""
            # LOCAL-362: Use intent's venue_name for city extraction
            _scope_venue = _exhibition_scope['venue_name']
            if "," in _scope_venue:
                _scope_parts = [p.strip() for p in _scope_venue.split(",")]
                _det_city_hint = _scope_parts[1] if len(_scope_parts) >= 2 else ""
            elif "," in location:
                _loc_parts = [p.strip() for p in location.split(",")]
                for _seg in _loc_parts[1:]:
                    _seg_lower = _seg.lower().strip()
                    if _seg_lower in ('ma', 'ny', 'ca', 'usa') or len(_seg.split()) <= 2:
                        if not any(_seg.strip() == a for a in _exhibition_scope_artists):
                            _det_city_hint = _seg.strip()
                            break

            _det_entity = resolve_venue(_scope_venue, _det_city_hint)

            # ─── LOCAL-364: Try exhibition checklist FIRST ─────────────────────
            if _det_entity and _det_entity.official_url:
                # [LOCAL-425] Use module-scope extract_exhibition_name for robust
                # extraction. The previous regex approach failed when the intent's
                # venue_name ("Museum of Fine Arts, Boston") didn't match the
                # abbreviation in the user's string ("MFA").
                from exhibition_checklist import extract_exhibition_name as _extract_exh_name
                _exh_name_for_search = _extract_exh_name(location)

                # If extraction returned the full location unchanged, try the old
                # venue-name-based approach as fallback
                if _exh_name_for_search == location:
                    _venue_name_for_strip = _exhibition_scope.get('venue_name', '')
                    if _venue_name_for_strip:
                        _at_pattern = re.compile(
                            r'\s+at\s+' + re.escape(_venue_name_for_strip.split(',')[0].strip()) + r'\b.*$',
                            re.IGNORECASE
                        )
                        _stripped = _at_pattern.sub('', _exh_name_for_search)
                        if _stripped and _stripped != _exh_name_for_search:
                            _exh_name_for_search = _stripped.strip()
                        elif ',' in location and _venue_name_for_strip.split(',')[0].strip().lower() in location.lower():
                            _vn_lower = _venue_name_for_strip.split(',')[0].strip().lower()
                            _loc_lower = location.lower()
                            _idx = _loc_lower.find(_vn_lower)
                            if _idx > 0:
                                _pre = location[:_idx].rstrip()
                                if _pre.lower().endswith(' at'):
                                    _exh_name_for_search = _pre[:-3].strip()
                                else:
                                    _exh_name_for_search = _pre.rstrip(',').strip()

                # Fallback: if stripping left us with nothing or just whitespace,
                # use requirements, then location
                if not _exh_name_for_search.strip():
                    _exh_name_for_search = _exhibition_scope.get('requirements', '') or location

                # [D506] Carry it forward. This name is resolved here, used to
                # fetch the checklist, and was then dropped — which is why
                # LOCAL-423's two visitor-framed queries have never run.
                _exh_name_resolved = _exh_name_for_search
                print(f"\n  [LOCAL-364] ═══ EXHIBITION CHECKLIST RETRIEVAL ═══")
                print(f"  [LOCAL-364] Exhibition search term: '{_exh_name_for_search}'")
                print(f"  [LOCAL-364] Venue URL: {_det_entity.official_url}")

                _exhibition_checklist_result = find_exhibition_checklist(
                    venue_base_url=_det_entity.official_url,
                    exhibition_name=_exh_name_for_search,
                    venue_name=_scope_venue,
                    venue_language=_det_entity.language,
                )

                print(f"  [LOCAL-364] Result: {_exhibition_checklist_result}")

                # [LOCAL-426] Log provenance clearly: where the content actually came from
                if getattr(_exhibition_checklist_result, 'is_third_party', False):
                    print(f"  [LOCAL-426] ⚠️  THIRD-PARTY SOURCE — works came from "
                          f"{_exhibition_checklist_result.content_url}, "
                          f"NOT from {_exhibition_checklist_result.exhibition_url}")
                elif getattr(_exhibition_checklist_result, 'is_from_archive', False):
                    _wb_ts = getattr(_exhibition_checklist_result, 'wayback_snapshot_timestamp', '?')
                    _wb_age = getattr(_exhibition_checklist_result, 'wayback_age_days', '?')
                    print(f"  [LOCAL-430] 📦 ARCHIVED SOURCE — venue's own words via web.archive.org "
                          f"(snapshot: {_wb_ts}, age: {_wb_age} days)")
                    print(f"    Original URL: {_exhibition_checklist_result.exhibition_url}")
                    print(f"    Content URL: {_exhibition_checklist_result.content_url}")

                # Handle result
                if _exhibition_checklist_result.is_closed:
                    # Exhibition has closed — do NOT tour it (LOCAL-365)
                    # Signal failure via None return + structured evidence in
                    # _LAST_CLEAN_FAIL_EVIDENCE so the service layer can surface
                    # a typed error without creating a tour row or invoking TTS.
                    print(f"\n  [LOCAL-365] ⚠️  EXHIBITION CLOSED — refusing to tour a dismounted show")
                    print(f"    Exhibition: {_exhibition_checklist_result.exhibition_title}")
                    print(f"    Closed: {_exhibition_checklist_result.closing_date}")
                    print(f"    Reason: {_exhibition_checklist_result.reason}")
                    global _LAST_CLEAN_FAIL_EVIDENCE
                    _LAST_CLEAN_FAIL_EVIDENCE = {
                        "error_type": "exhibition_closed",
                        "exhibition_title": _exhibition_checklist_result.exhibition_title,
                        "closing_date": str(_exhibition_checklist_result.closing_date),
                        "venue": _scope_venue,
                        "reason": _exhibition_checklist_result.reason,
                    }
                    _LAST_GENERATION_COST = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "cache_hit": False,
                        "breakdown": {"llm": 0.0, "tts": 0.0, "search": 0.0},
                    }
                    return None, None, (None, None)

                elif _exhibition_checklist_result.has_works:
                    # SUCCESS: Use the exhibition checklist as stops
                    _checklist_works = _exhibition_checklist_result.works
                    _exhibition_stops_source = _exhibition_checklist_result.path  # 'checklist', 'partial', or 'prose_llm'

                    if len(_checklist_works) < total_stops and _exhibition_checklist_result.path == 'partial':
                        print(f"  [LOCAL-364] Partial checklist: {len(_checklist_works)} works "
                              f"(site shows highlights only), requested {total_stops}")
                        # Use what we have; shortfall is honestly stated
                        total_stops = min(total_stops, len(_checklist_works))
                    elif len(_checklist_works) < total_stops:
                        total_stops = len(_checklist_works)

                    _det_take = min(len(_checklist_works), total_stops * 2)
                    poi_list = [_new_poi(w['title']) for w in _checklist_works[:_det_take]]
                    _deterministic_fill_used = True

                    _path_label = _exhibition_checklist_result.path.upper()
                    print(f"  [LOCAL-364/368] ✓ {_path_label} PATH: {len(poi_list)} works from exhibition page")
                    # [LOCAL-426] Show the actual content source, not the venue URL
                    _display_source = (getattr(_exhibition_checklist_result, 'content_url', '')
                                       or _exhibition_checklist_result.exhibition_url)
                    print(f"    Source: {_display_source}")
                    if getattr(_exhibition_checklist_result, 'is_third_party', False):
                        print(f"    Venue: {_exhibition_checklist_result.exhibition_url} (unreachable)")
                    print(f"    Shape: {_exhibition_checklist_result.page_shape}")
                    print(f"    Stops from exhibition {_path_label.lower()}:")
                    for p in poi_list[:total_stops]:
                        _w = next((w for w in _checklist_works if w['title'] == p['name']), {})
                        _artist_info = f" (by {_w['artist']})" if _w.get('artist') else ''
                        # [LOCAL-426] Show per-work source_url if different from venue
                        _work_source = _w.get('source_url', '')
                        _source_tag = f" [source: {_work_source}]" if _work_source else ''
                        print(f"      - {p['name']}{_artist_info}{_source_tag}")

            # ─── LOCAL-364/362 FALLBACK: creator filter ────────────────────────
            # If checklist retrieval failed (no exhibition page found, prose-only,
            # no venue URL), fall back to LOCAL-362's creator filter.
            # The key difference: we LABEL this fallback honestly.
            if not _deterministic_fill_used:
                _fallback_reason = ''
                if _exhibition_checklist_result:
                    _fallback_reason = _exhibition_checklist_result.reason
                else:
                    _fallback_reason = 'No venue URL available for exhibition page crawl'

                print(f"\n  [LOCAL-364] Checklist unavailable — falling back to creator filter")
                print(f"    Reason: {_fallback_reason}")
                _exhibition_stops_source = 'creator_filter'

                if _det_entity and _det_entity.qid:
                    # ──── LOCAL-362 CREATOR FILTER (now labelled as fallback) ──────
                    _det_documented = []
                    _det_seen_titles_norm = set()

                    # Source 1: Catalogue works
                    _det_cache = _det_cache_get(_det_entity.qid) if _det_entity.qid else None
                    _det_catalogue_works = []
                    if _det_cache and _det_cache.get('pages'):
                        _det_pages = _det_cache['pages']
                        if isinstance(_det_pages, list):
                            _det_catalogue_works = extract_catalogue_works_from_pages(_det_pages)

                    for cw in _det_catalogue_works:
                        _t = cw.get('title', '').strip()
                        _tn = _det_norm(_t)
                        if _t and _tn not in _det_seen_titles_norm:
                            _det_documented.append({'title': _t, 'source': 'catalogue',
                                                    'creator': cw.get('artist', ''),
                                                    'material': cw.get('material', ''),
                                                    'period': cw.get('period', ''),
                                                    'origin': cw.get('origin', '')})
                            _det_seen_titles_norm.add(_tn)

                    # Source 2: SPARQL works (includes creator via LOCAL-362)
                    _det_sparql = fetch_venue_works(_det_entity.qid, _det_entity.language)
                    _det_sparql_seen_qids = set()
                    for w in _det_sparql:
                        _wqid = w.get('qid', '')
                        if _wqid in _det_sparql_seen_qids:
                            continue
                        _det_sparql_seen_qids.add(_wqid)
                        _t = w.get('label_local', '') or w.get('label_en', '')
                        _tn = _det_norm(_t)
                        if _t and _tn not in _det_seen_titles_norm:
                            _det_documented.append({
                                'title': _t, 'source': 'sparql',
                                'creator': w.get('creator', ''),
                                'creators': w.get('creators', []),
                            })
                            _det_seen_titles_norm.add(_tn)

                    print(f"  [LOCAL-362] Total documented works at venue: {len(_det_documented)} "
                          f"({len(_det_catalogue_works)} catalogue, {len(_det_sparql_seen_qids)} SPARQL)")

                    # Filter by scope artists
                    _scope_filtered = []
                    if _exhibition_scope_artists:
                        _scope_artists_norm = []
                        for a in _exhibition_scope_artists:
                            _a_nfkd = _ud362.normalize('NFKD', a.lower())
                            _a_stripped = ''.join(c for c in _a_nfkd if not _ud362.combining(c))
                            _scope_artists_norm.append(_a_stripped)
                            _parts = _a_stripped.split()
                            if len(_parts) > 1:
                                _scope_artists_norm.append(_parts[-1])

                        def _creator_matches_scope(work_entry: dict) -> bool:
                            """Check if a work's creator matches any of the scope artists."""
                            creators_to_check = []
                            if work_entry.get('creator'):
                                creators_to_check.append(work_entry['creator'])
                            if work_entry.get('creators'):
                                creators_to_check.extend(work_entry['creators'])
                            for creator in creators_to_check:
                                if not creator:
                                    continue
                                _c_nfkd = _ud362.normalize('NFKD', creator.lower())
                                _c_stripped = ''.join(c for c in _c_nfkd if not _ud362.combining(c))
                                for _an in _scope_artists_norm:
                                    if _an in _c_stripped or _c_stripped.endswith(_an):
                                        return True
                            return False

                        _scope_filtered = [d for d in _det_documented if _creator_matches_scope(d)]
                        print(f"  [LOCAL-362] After artist-scope filter: {len(_scope_filtered)} works "
                              f"match artists {_exhibition_scope_artists}")

                        for _artist in _exhibition_scope_artists:
                            _a_nfkd = _ud362.normalize('NFKD', _artist.lower())
                            _a_stripped = ''.join(c for c in _a_nfkd if not _ud362.combining(c))
                            _artist_count = sum(1 for d in _scope_filtered
                                               if _a_stripped in _ud362.normalize('NFKD', (d.get('creator', '') or '').lower()))
                            print(f"    {_artist}: {_artist_count} works")

                    # Decide: use filtered if we have enough
                    if _scope_filtered and len(_scope_filtered) >= 1:
                        if len(_scope_filtered) < total_stops:
                            print(f"  [LOCAL-362] HONEST DEGRADATION: only {len(_scope_filtered)} works "
                                  f"match scope, but {total_stops} requested.")
                            print(f"    → Tour will have {len(_scope_filtered)} stops (scope-constrained).")
                            total_stops = len(_scope_filtered)

                        _det_take = min(len(_scope_filtered), total_stops * 2)
                        poi_list = [_new_poi(d['title']) for d in _scope_filtered[:_det_take]]
                        _deterministic_fill_used = True

                        print(f"  [LOCAL-362] SCOPED SELECTION (FALLBACK): {len(poi_list)} works by "
                              f"{', '.join(_exhibition_scope_artists)} → Phase 3A SKIPPED")
                        print(f"  [LOCAL-364] ⚠️  NOTE: These are works by the exhibition's artists "
                              f"in the venue's permanent collection — NOT necessarily works in the exhibition.")
                        print(f"    Fallback reason: {_fallback_reason}")
                        print(f"   Stops proposed (creator-filtered, FALLBACK path):")
                        for p in poi_list[:total_stops]:
                            _src = next((d['source'] for d in _scope_filtered if d['title'] == p['name']), '?')
                            _cr = next((d.get('creator', '?') for d in _scope_filtered if d['title'] == p['name']), '?')
                            print(f"     - {p['name']} [{_src}] (creator: {_cr})")
                    else:
                        print(f"  [LOCAL-362] No works match scope artists in SPARQL/catalogue — "
                              f"falling through to Phase 3A (GPT will use requirements)")
                else:
                    print(f"  [LOCAL-362] Venue resolution failed — falling through to Phase 3A")

        except ImportError as _imp_err:
            # exhibition_checklist module not available — fall through gracefully
            print(f"  [LOCAL-364] exhibition_checklist module unavailable ({_imp_err}) — "
                  f"falling back to LOCAL-362 creator filter")
            _exhibition_stops_source = 'creator_filter'
            # Re-run just the LOCAL-362 path without the checklist
            try:
                from venue_resolver import resolve_venue, fetch_venue_works, cache_get as _det_cache_get
                from story_miner import extract_catalogue_works_from_pages
                from story_miner import _normalize as _det_norm

                _det_city_hint = ""
                _scope_venue = _exhibition_scope['venue_name']
                if "," in _scope_venue:
                    _scope_parts = [p.strip() for p in _scope_venue.split(",")]
                    _det_city_hint = _scope_parts[1] if len(_scope_parts) >= 2 else ""

                _det_entity = resolve_venue(_scope_venue, _det_city_hint)
                if _det_entity and _det_entity.qid:
                    _det_sparql = fetch_venue_works(_det_entity.qid, _det_entity.language)
                    if _det_sparql and _exhibition_scope_artists:
                        # Same creator-filter as LOCAL-362
                        _scope_artists_norm = []
                        for a in _exhibition_scope_artists:
                            _a_nfkd = _ud362.normalize('NFKD', a.lower())
                            _a_stripped = ''.join(c for c in _a_nfkd if not _ud362.combining(c))
                            _scope_artists_norm.append(_a_stripped)
                            _parts = _a_stripped.split()
                            if len(_parts) > 1:
                                _scope_artists_norm.append(_parts[-1])

                        _scope_filtered = []
                        for w in _det_sparql:
                            _cr = w.get('creator', '')
                            if _cr:
                                _c_nfkd = _ud362.normalize('NFKD', _cr.lower())
                                _c_stripped = ''.join(c for c in _c_nfkd if not _ud362.combining(c))
                                if any(_an in _c_stripped for _an in _scope_artists_norm):
                                    _scope_filtered.append({
                                        'title': w.get('label_local', '') or w.get('label_en', ''),
                                        'source': 'sparql', 'creator': _cr,
                                    })
                        if _scope_filtered:
                            if len(_scope_filtered) < total_stops:
                                total_stops = len(_scope_filtered)
                            poi_list = [_new_poi(d['title']) for d in _scope_filtered[:total_stops * 2]]
                            _deterministic_fill_used = True
                            print(f"  [LOCAL-362 fallback] {len(poi_list)} works by "
                                  f"{', '.join(_exhibition_scope_artists)}")
            except Exception:
                pass
        except Exception as _scope_err:
            print(f"  [LOCAL-364] Exhibition checklist failed (falling through to Phase 3A): {_scope_err}")
            import traceback
            traceback.print_exc()
        # ──── END [LOCAL-364/362] ─────────────────────────────────────────────
    elif tour_category == 'museum' and _museum_venue_name:
        try:
            from venue_resolver import resolve_venue, fetch_venue_works, build_canonical_titles_from_works, cache_get as _det_cache_get
            from story_miner import extract_catalogue_works_from_pages, fetch_venue_narrative_corpus
            
            _det_city_hint = ""
            if "," in location:
                parts = [p.strip() for p in location.split(",")]
                _det_city_hint = parts[1] if len(parts) >= 2 else ""
            _det_entity = resolve_venue(_museum_venue_name, _det_city_hint)
            
            if _det_entity and _det_entity.qid:
                # Gather documented works from all sources
                _det_documented = []  # List of {title, source} dicts
                _det_seen_titles_norm = set()
                
                from story_miner import _normalize as _det_norm
                
                # Source 1: Catalogue works (highest confidence — museum-published)
                _det_cache = _det_cache_get(_det_entity.qid) if _det_entity.qid else None
                _det_catalogue_works = []
                if _det_cache and _det_cache.get('pages'):
                    _det_pages = _det_cache['pages']
                    if isinstance(_det_pages, list):
                        _det_catalogue_works = extract_catalogue_works_from_pages(_det_pages)
                
                for cw in _det_catalogue_works:
                    _t = cw.get('title', '').strip()
                    _tn = _det_norm(_t)
                    if _t and _tn not in _det_seen_titles_norm:
                        _det_documented.append({'title': _t, 'source': 'catalogue',
                                                'material': cw.get('material', ''),
                                                'period': cw.get('period', ''),
                                                'origin': cw.get('origin', '')})
                        _det_seen_titles_norm.add(_tn)
                
                # Source 2: SPARQL works (Wikidata-verified, second highest)
                _det_sparql = fetch_venue_works(_det_entity.qid, _det_entity.language)
                _det_sparql_seen_qids = set()
                for w in _det_sparql:
                    _wqid = w.get('qid', '')
                    if _wqid in _det_sparql_seen_qids:
                        continue
                    _det_sparql_seen_qids.add(_wqid)
                    _t = w.get('label_local', '') or w.get('label_en', '')
                    _tn = _det_norm(_t)
                    if _t and _tn not in _det_seen_titles_norm:
                        _det_documented.append({'title': _t, 'source': 'sparql'})
                        _det_seen_titles_norm.add(_tn)
                
                # Source 3: Cached canonical titles that survived LOCAL-24 filter
                if _det_cache and _det_cache.get('canonical_titles'):
                    for _ct in _det_cache['canonical_titles']:
                        _tn = _det_norm(_ct)
                        if _ct and _tn not in _det_seen_titles_norm:
                            _det_documented.append({'title': _ct, 'source': 'canonical'})
                            _det_seen_titles_norm.add(_tn)
                
                print(f"  [LOCAL-30] Deterministic selection: {len(_det_documented)} documented works "
                      f"({len(_det_catalogue_works)} catalogue, {len(_det_sparql_seen_qids)} SPARQL)")
                
                # If documented works >= total_stops, fill deterministically
                if len(_det_documented) >= total_stops:
                    # -------- [LOCAL-284] Corpus-depth tiebreak for museum selection --------
                    # D170 says stop selection stays free — no artificial constraints.
                    # But for a MUSEUM, the candidate set is a closed list of real objects,
                    # all equally "notable". Choosing objects we can actually describe over
                    # ones with zero corpus is not narrowing — it is competence.
                    #
                    # ────── [LOCAL-328] Source-weighted quality score ──────
                    # D241: passage_count is ANTI-CORRELATED with quality.
                    # web_search passages accumulate sludge (directory listings,
                    # keyword blobs) while museum_official passages are dense
                    # with catalogue facts.  Sort by source-weighted quality
                    # score (sludge excluded, sources weighted by measured
                    # fact yield) instead of raw passage_count.
                    _depth_map = {}  # normalized_title -> quality_score (float)
                    try:
                        from venue_resolver import _get_db_connection as _depth_get_conn
                        _depth_conn = _depth_get_conn()
                        if _depth_conn:
                            _depth_cur = _depth_conn.cursor()
                            # Use significant venue words for matching stop_corpus rows
                            _venue_words_for_depth = [
                                w for w in _det_norm(_museum_venue_name).split()
                                if len(w) >= 4 and w not in ('museum', 'musee', 'nice', 'france', 'paris')
                            ]
                            # Build LIKE conditions: all significant words must match
                            _depth_conditions = []
                            _depth_params = []
                            for _vw in _venue_words_for_depth[:3]:
                                _depth_conditions.append("LOWER(venue_name) LIKE %s")
                                _depth_params.append(f"%{_vw}%")
                            if _depth_conditions:
                                _depth_cur.execute(
                                    "SELECT stop_title, passages_json FROM stop_corpus "
                                    f"WHERE {' AND '.join(_depth_conditions)} AND passage_count > 0",
                                    _depth_params
                                )
                                # Compute quality score per stop (source-weighted, sludge excluded)
                                from corpus_source_quality import classify_passage, compute_quality_score
                                import json as _depth_json
                                for _dt, _pj in _depth_cur.fetchall():
                                    _passages_raw = _depth_json.loads(_pj) if isinstance(_pj, str) else _pj
                                    _classified = [classify_passage(p) for p in (_passages_raw or [])]
                                    _depth_map[_det_norm(_dt)] = compute_quality_score(_classified)
                            _depth_cur.close()
                            _depth_conn.close()
                            if _depth_map:
                                print(f"  [LOCAL-328] Quality score map: {len(_depth_map)} objects scored (source-weighted, sludge excluded)")
                    except Exception as _depth_err:
                        print(f"  [LOCAL-328] Quality score lookup failed (non-fatal): {_depth_err}")
                    
                    # Sort: (-quality_score, source_priority, title for stability)
                    # [LOCAL-328] For MUSEUMS: source-weighted quality score is the
                    # PRIMARY signal. This replaces passage_count (D241: anti-correlated
                    # with quality — web_search sludge inflates counts without adding
                    # facts). Quality score = sum of non-sludge passages weighted by
                    # source type yield (museum_official 3.0, wikipedia 2.5, etc.).
                    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
                    _det_documented.sort(key=lambda d: (
                        -_depth_map.get(_det_norm(d['title']), 0),
                        _priority.get(d['source'], 9),
                        d['title'],
                    ))
                    
                    # Apply bare-noun filter (shouldn't be needed but defence-in-depth)
                    from story_miner import is_bare_generic_noun
                    _det_documented = [d for d in _det_documented if not is_bare_generic_noun(d['title'])]
                    
                    # Take total_stops * 2 (D1v2 will filter, so give it room)
                    _det_take = min(len(_det_documented), total_stops * 2)
                    poi_list = [_new_poi(d['title']) for d in _det_documented[:_det_take]]
                    
                    print(f"  [LOCAL-30] DETERMINISTIC BYPASS: {len(poi_list)} documented works → Phase 3A SKIPPED")
                    print(f"   Stops proposed (deterministic, quality-score ranked):")
                    for p in poi_list[:total_stops]:
                        _src = next((d['source'] for d in _det_documented if d['title'] == p['name']), '?')
                        _qscore = _depth_map.get(_det_norm(p['name']), 0)
                        print(f"     - {p['name']} [{_src}] (quality={_qscore:.1f})")
                    _deterministic_fill_used = True
                else:
                    print(f"  [LOCAL-30] Documented works ({len(_det_documented)}) < total_stops ({total_stops}) "
                          f"— will use documented as base, GPT fills remainder")
        except Exception as _det_err:
            print(f"  [LOCAL-30] Deterministic selection check failed (falling through to Phase 3A): {_det_err}")
            import traceback
            traceback.print_exc()

    # For museum tours with D1v2 verification: ask for 2x candidates to improve hit rate
    # [LOCAL-290 Fault 1] For ALL tours, request N + margin so the existence gate has
    # candidates to work with. Previously non-museum tours asked for exactly N — if GPT
    # returned N-1 or the gate dropped any, the tour was already short.
    _phase3a_count = total_stops + max(3, total_stops // 2)  # at least N+3, up to N+N/2
    _phase3a_count = min(_phase3a_count, 20)  # hard cap to avoid bloating the prompt
    if tour_category == 'museum' and _museum_venue_name:
        _phase3a_count = min(total_stops * 2, 20)
        print(f"  [R4] Museum tour: asking for {_phase3a_count} candidates (2x for D1v2 filtering)")
    else:
        print(f"  [LOCAL-290] Asking for {_phase3a_count} candidates (N={total_stops} + margin for gate filtering)")

    if _deterministic_fill_used:
        if not _forced_stops_active:
            # Skip Phase 3A entirely — poi_list already filled deterministically
            print(f"\nPHASE 3A: SKIPPED (deterministic fill from {len(poi_list)} documented works)")
            print(f"OK PHASE 3A parsed {len(poi_list)} candidate POI(s):")
            for p in poi_list:
                print(f"   - {p['name']}")
        # [LOCAL-329] No selection reasons when deterministic fill is used
        _selection_reasons = {}
    else:
        pass  # Fall through to normal Phase 3A GPT call below

    if not _deterministic_fill_used:
        # [LOCAL-425] Exhibition-aware Phase 3A: when an exhibition is named but
        # the checklist/creator-filter couldn't supply works, override the
        # museum constraint to ask for EXHIBITION works specifically, not the
        # venue's permanent highlights.
        if _exhibition_scope is not None and _museum_venue_constraint:
            _exh_name_display = _exhibition_scope.get('requirements', '') or location
            # Also try to use the cleaner extracted name
            try:
                from exhibition_checklist import extract_exhibition_name as _p3a_exh_name
                _exh_name_display = _p3a_exh_name(location)
            except ImportError:
                pass
            _museum_venue_name_p3a = _exhibition_scope.get('venue_name', '').split(',')[0].strip()
            _museum_venue_constraint = (
                f"\nCRITICAL CONSTRAINT — THIS IS A NAMED EXHIBITION TOUR:\n"
                f"- The user is requesting a tour of the exhibition '{_exh_name_display}' "
                f"at '{_museum_venue_name_p3a}'.\n"
                f"- List the {total_stops} most notable ARTWORKS that are part of THIS SPECIFIC "
                f"EXHIBITION — not the museum's permanent collection highlights.\n"
                f"- Each stop MUST be named after an ARTWORK in the exhibition.\n"
                f"- Only include works you are confident are IN THIS EXHIBITION.\n"
                f"- Do NOT list the museum's iconic permanent-collection works unless they are "
                f"explicitly part of this exhibition.\n"
                f"- Do NOT fabricate artwork names.\n"
            )
            print(f"  [LOCAL-425] Phase 3A constraint overridden for exhibition: '{_exh_name_display}'")

        # [LOCAL-329] Include "reason" in the JSON schema for restaurant/walking tours
        # so the LLM returns notability reasons at selection time.
        if tour_category == 'restaurant':
            _phase3a_json_hint = '[{"name": "...", "address": "...", "reason": "Founded in 1927 by the Acchiardo family; known for handmade ravioli and slow-cooked daube niçoise"}, ...]'
        elif tour_category == 'walking':
            _phase3a_json_hint = '[{"name": "...", "address": "...", "reason": "Brief reason why this landmark is notable — a specific date, person, or event"}, ...]'
        else:
            _phase3a_json_hint = '[{"name": "...", "address": "..."}, ...]'

        phase_3a_prompt = (
            f"You are a knowledgeable local guide for {location}.\n"
            f"List exactly {_phase3a_count} specific, real, well-known {poi_type_hint} relevant to: {user_request}.\n\n"
            "Requirements:\n"
            "- Use REAL, SPECIFIC names of actual establishments or landmarks.\n"
            "- NEVER use generic placeholders like 'Restaurant 1', 'Stop 1', 'Location A'.\n"
            "- Include a complete street address with ZIP code where applicable.\n"
            + _museum_venue_constraint
            + _restaurant_venue_constraint
            + _transport_stop_constraint
            + _scope_constraint
            + _compactness_constraint
            + "\n\nReturn ONLY a JSON array, no other text, no markdown fences:\n"
            + _phase3a_json_hint
        )
        phase_3a_data = {
            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
        if not _deterministic_fill_used:
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
            total_cost += _tour_llm_cost(tokens_used)
            print(f"PHASE 3A API call cost: ${_tour_llm_cost(tokens_used):.4f} ({tokens_used} tokens)")

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

            # [LOCAL-329] Track selection reasons for substance filtering and corpus persistence
            _selection_reasons = {}  # name_lower → reason text
            _hollow_reason_rejects = []  # names rejected for ranking-only reasons

            for c in candidates:
                if not isinstance(c, dict):
                    continue
                name = (c.get("name") or "").strip()
                if not name:
                    continue
                if re.match(r'^(Restaurant|Store|Shop|Location|Business|Walking Tour)\s*\d*$', name):
                    print(f"   ! Rejected generic name from PHASE 3A: '{name}'")
                    continue
                # [LOCAL-22] Root-cause guard: reject names that are sentences/descriptions
                if _is_name_corrupted(name):
                    print(f"   ! [LOCAL-22] Rejected corrupted name from PHASE 3A: '{name[:80]}'")
                    continue

                # [LOCAL-329] Capture and filter selection reasons
                reason = (c.get("reason") or "").strip()
                if reason and tour_category in ('restaurant', 'walking'):
                    from selection_reason_filter import reason_has_substance
                    if reason_has_substance(reason):
                        _selection_reasons[name.lower()] = reason
                    else:
                        # Hollow reason — the venue may still be real, but the LLM
                        # couldn't cite a specific fact. Deprioritize.
                        _hollow_reason_rejects.append(name)
                        print(f"   ! [LOCAL-329] Hollow reason for '{name}': '{reason[:80]}'")
                        continue  # skip this candidate

                poi_list.append(_new_poi(name, c.get("address") or ""))

            # [LOCAL-329] Report substance filtering
            if _hollow_reason_rejects:
                print(f"  [LOCAL-329] Substance filter: {len(_hollow_reason_rejects)} candidate(s) "
                      f"rejected for ranking-only reasons")
            if _selection_reasons:
                print(f"  [LOCAL-329] Captured {len(_selection_reasons)} substantive selection reason(s)")

            if len(poi_list) == 0:
                print(f"X PHASE 3A: no usable POIs after parsing")
                return None, None, (None, None)

            print(f"OK PHASE 3A parsed {len(poi_list)} candidate POI(s):")
            for p in poi_list:
                print(f"   - {p['name']}" + (f" @ {p['address']}" if p['address'] else ""))

            # [TRANSPORT-VERIFY] For unusual transport modes, verify stops are reachable
            poi_list = _verify_transport_accessibility(poi_list, transport_mode, location, api_key)

        # -------- [D1] In-collection verification for museum tours --------
        _d1_evidence_log = {}
        _d1_venue_corpus = ""
        _story_corpus_result = None
        _d1v2_result = None  # [LOCAL-72] Initialize for non-museum paths (prevents NameError in three_class_retrieval)
        if tour_category == 'museum' and _museum_venue_name:
            global _LAST_VERIFICATION_TIER
            # [LOCAL-372] Skip D1v2 verification when stops come from the venue's own
            # exhibition page. These works are already grounded by their source — 
            # verifying them against SPARQL/Wikidata would reject exhibition-specific
            # works that aren't individually catalogued in the museum's permanent collection.
            if _deterministic_fill_used and _exhibition_stops_source in ('checklist', 'partial', 'prose_llm'):
                print(f"  [D1/LOCAL-372] SKIP D1v2 — stops sourced from exhibition {_exhibition_stops_source} "
                      f"(D1v2 checks the PERMANENT collection; a temporary show is not in it)")
                # [LOCAL-372 LEAD] Skipping D1v2 is right, but these stops still need
                # grounding — just against the source that IS authoritative here. Verify
                # each title actually appears on the venue page it was extracted from,
                # otherwise an invented title ships unchallenged.
                _exh_page_text = getattr(_exhibition_checklist_result, 'page_text', '') or ''
                if _exh_page_text:
                    _grounded, _ungrounded = [], []
                    for _p in poi_list:
                        if title_appears_in_page(_p.get('name', ''), _exh_page_text):
                            _grounded.append(_p)
                        else:
                            _ungrounded.append(_p.get('name', ''))
                    if _ungrounded:
                        print(f"  [D1/LOCAL-372] DROPPED {len(_ungrounded)} stop(s) absent from the "
                              f"exhibition page (not extracted from it — likely invented):")
                        for _u in _ungrounded:
                            print(f"      - {_u}")
                    poi_list = _grounded
                    if not poi_list:
                        print(f"  [D1/LOCAL-372] No exhibition stop survived page grounding — clean fail")
                else:
                    print(f"  [D1/LOCAL-372] WARNING: no page_text captured — exhibition stops "
                          f"are ungrounded this run")
                print(f"  [D1/LOCAL-372] {len(poi_list)} exhibition stop(s) grounded against the venue page")
                _verification_tier = 'exhibit_museum'
                _LAST_VERIFICATION_TIER = _verification_tier
            else:
                # Try new story_miner-based verification (T0a/T1)
                # Pass full location string so D1v2 can parse city for venue disambiguation
                _d1v2_venue_arg = _museum_venue_name
                if ',' not in _d1v2_venue_arg and ',' in _location_normalized:
                    # Append city/state from location if venue name alone lacks it
                    _d1v2_venue_arg = _location_normalized
                _d1v2_result = _verify_works_v2(poi_list, _d1v2_venue_arg, exhibition_scope=_exhibition_scope)
                if isinstance(_d1v2_result, VerificationResult):
                    _verification_tier = _d1v2_result.tier
                    _LAST_VERIFICATION_TIER = _verification_tier
                    if _d1v2_result.tier == 'unresolvable':
                        # Clean fail with structured error
                        print(f"  [D1] Tier: unresolvable — clean fail (entity={_d1v2_result.entity_resolved}, sparql={_d1v2_result.sparql_count})")
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
                    # NOTE: This legacy path only applies when REQUIRE_LISTING_VERIFICATION=true.
                    # When false, the unified fill logic below handles ALL tiers.
                    _require_listing_verification = os.environ.get('REQUIRE_LISTING_VERIFICATION', 'false').lower() in ('true', '1', 'yes')
                    if _require_listing_verification and _verification_tier == 'thin' and len(poi_list) < 3 and len(_pre_d1v2_candidates) >= 3:
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

            # -------- [R4] Bounded replenishment loop (runs FIRST, before any fill) --------
            # [LOCAL-19 FIX] R4 now runs BEFORE UNIFIED-FILL so it sees only verified
            # stops. Previously UNIFIED-FILL padded the count with unverified candidates,
            # making R4's `while len(poi_list) < total_stops` condition false — R4 never
            # ran, and the unverified fills were later stripped by the LOCAL-16 gate,
            # leaving a permanent shortfall.
            #
            # New ordering:
            #   1. R4 replenishment (verified-only count → triggers correctly)
            #   2. UNIFIED-FILL (last-resort unverified padding)
            #   3. LOCAL-16 GATE (strips unverified for museum tours before Phase 5)
            #
            # [LOCAL-370] EXCEPTION: When _exhibition_scope is not None, R4 must NOT
            # fire. D275 requires an unsatisfiable scope to produce a shorter, honest
            # tour rather than backfilling from the venue-wide collection. R4 draws
            # from the entire venue, which defeats exhibition scoping. If the scope
            # yields 3 works, the tour has 3 stops.
            _require_listing_verification = os.environ.get('REQUIRE_LISTING_VERIFICATION', 'false').lower() in ('true', '1', 'yes')

            # [LOCAL-370] Skip R4 entirely for exhibition-scoped requests
            _r4_suppressed_by_scope, total_stops = r4_scope_cap(
                _exhibition_scope, len(poi_list), total_stops)
            if _r4_suppressed_by_scope:
                print(f"\n  [LOCAL-370] R4 replenishment SUPPRESSED (exhibition-scoped request)")
                print(f"    Scope: {_exhibition_scope.get('requirements', '')}")
                print(f"    Honest stop count: {total_stops} (no venue-wide backfill — D275)")

            if _require_listing_verification:
                # OLD BEHAVIOR: cap at verified for medium/thin, thin sparse gets capped at 5
                if _verification_tier in ('medium', 'thin'):
                    if _verification_tier == 'thin' and len(poi_list) < 3:
                        _thin_cap = min(total_stops, 5)
                        print(f"  [R4] THIN tier with sparse coverage ({len(poi_list)} stops, "
                              f"{sum(1 for p in poi_list if p.get('verified', True))} verified) — "
                              f"allowing up to {_thin_cap} stops for Wikidata-resolved venue")
                        total_stops = _thin_cap
                    else:
                        _n_verified_in_list = sum(1 for p in poi_list if p.get('verified', True))
                        total_stops = len(poi_list)
                        print(f"  [R4] SKIPPED (REQUIRE_LISTING_VERIFICATION=true) — tier={_verification_tier}, "
                              f"total_stops={total_stops} ({_n_verified_in_list} verified)")

            # R4 replenishment: re-prompt GPT for fresh candidates and verify against corpus
            # Runs against verified-only count (UNIFIED-FILL has NOT yet padded poi_list)
            _r4_all_tried_names = set(_normalize_name(p['name']) for p in poi_list)
            _r4_all_tried_names.update(_normalize_name(k) for k in _d1_evidence_log.keys())
            _r4_round = 0
            _R4_MAX_ROUNDS = 3
            _R4_MAX_CANDIDATES = 30
            _r4_all_dropped_pois = []  # Accumulate R4-generated candidates that failed verification
            
            while not _r4_suppressed_by_scope and len(poi_list) < total_stops and _r4_round < _R4_MAX_ROUNDS and len(_r4_all_tried_names) < _R4_MAX_CANDIDATES:
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
                    "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
                    total_cost += _tour_llm_cost(tokens_used)
                    
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
                        # [LOCAL-22] Root-cause guard: reject names that are sentences/descriptions
                        if _is_name_corrupted(name):
                            print(f"    [LOCAL-22] Rejected corrupted name from R4: '{name[:80]}'")
                            _r4_all_tried_names.add(_normalize_name(name))
                            continue
                        _r4_all_tried_names.add(_normalize_name(name))
                        _r4_new_pois.append(_new_poi(name, c.get("address") or ""))
                    
                    if not _r4_new_pois:
                        print(f"    [R4] No new candidates after dedup")
                        break
                    
                    # Verify new candidates
                    if _story_corpus_result:
                        from story_miner import match_candidate_to_canonical
                        _r4_enrichments = _story_corpus_result.get('bare_sparql_enrichments', {})
                        _r4_verified = []
                        for p in _r4_new_pois:
                            match = match_candidate_to_canonical(
                                p['name'],
                                _story_corpus_result['canonical_titles'],
                                _story_corpus_result['combined_text']
                            )
                            if match:
                                # [LOCAL-34] Rename POI to the canonical title (with enrichment)
                                _r4_canonical = match[0]
                                if _r4_canonical in _r4_enrichments:
                                    _r4_canonical = _r4_enrichments[_r4_canonical]
                                p = dict(p)  # Don't mutate original
                                p['name'] = _r4_canonical
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
                                _r4_all_dropped_pois.append(p)  # Accumulate for POST-R4 fill
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

            # -------- [UNIFIED-FILL] Runs AFTER R4 (unverified last-resort padding) --------
            # [LOCAL-19] Moved here from before R4. Now R4 has already had its chance
            # to find verified replacements. UNIFIED-FILL only pads remaining gaps.
            if not _require_listing_verification:
                if len(poi_list) < total_stops and _verification_tier in ('thin', 'medium', 'exhibit_museum'):
                    _verified_names_fill = set(p['name'].lower() for p in poi_list)
                    _evidence_keys_fill = set(_normalize_name(k) for k in _d1_evidence_log.keys()
                                              if _d1_evidence_log[k].get('status') == 'VERIFIED')
                    _fill_candidates = []
                    for p in _pre_d1v2_candidates:
                        _cand_name = p['name']
                        _cand_norm = _normalize_name(_cand_name)
                        # Skip if already in verified list (exact or normalized match)
                        if _cand_name.lower() in _verified_names_fill or _cand_norm in _evidence_keys_fill:
                            continue
                        # Skip if already in poi_list (R4 may have added it as verified)
                        if _cand_name.lower() in set(p2['name'].lower() for p2 in poi_list):
                            continue
                        # PALAIS-FIX D1: Skip REJECTED candidates (located at other venue)
                        _ev_entry = _d1_evidence_log.get(_cand_name, {})
                        if isinstance(_ev_entry, dict) and _ev_entry.get('status') == 'REJECTED':
                            continue
                        # LOCAL-24: Apply work-vs-nonwork filter to fill candidates
                        # Prevents programs/workshops from entering the tour as unverified fills
                        from story_miner import classify_corpus_entry
                        _fill_class = classify_corpus_entry(
                            title=_cand_name,
                            venue_name=_museum_venue_name,
                        )
                        if _fill_class['kind'] == 'excluded':
                            print(f"  [UNIFIED-FILL] LOCAL-24 blocked: '{_cand_name}' ({_fill_class['rule']})")
                            continue
                        # Every fill candidate is explicitly unverified
                        p['verified'] = False
                        _fill_candidates.append(p)
                    _fill_needed = total_stops - len(poi_list)
                    _fill_added = _fill_candidates[:_fill_needed]
                    if _fill_added:
                        poi_list = list(poi_list) + _fill_added
                        print(f"  [UNIFIED-FILL] tier={_verification_tier}: added {len(_fill_added)} unverified fills "
                              f"(from {len(_pre_d1v2_candidates)} pre-D1v2 candidates, "
                              f"total now {len(poi_list)}/{total_stops})")
                    else:
                        print(f"  [UNIFIED-FILL] tier={_verification_tier}: no eligible fill candidates")

            # -------- [POST-R4-FILL] From R4-dropped candidates --------
            if not _require_listing_verification and len(poi_list) < total_stops:
                _n_verified_current = sum(1 for p in poi_list if p.get('verified', True))
                _n_unverified_current = len(poi_list) - _n_verified_current
                # Rich tier: cap at 50% unverified; non-rich: no cap (fill to total_stops)
                if _verification_tier not in ('thin', 'medium', 'exhibit_museum'):
                    _max_unverified = max(1, total_stops // 2)
                    _unverified_budget = _max_unverified - _n_unverified_current
                else:
                    _unverified_budget = total_stops - len(poi_list)
                if _unverified_budget > 0:
                    _verified_names_post = set(p['name'].lower() for p in poi_list)
                    _evidence_keys_post = set(_normalize_name(k) for k in _d1_evidence_log.keys()
                                              if _d1_evidence_log[k].get('status') == 'VERIFIED')
                    _post_r4_fill = []
                    # Source: R4-dropped candidates (generated by R4 but failed verification)
                    _fill_pool = list(_r4_all_dropped_pois)
                    for p in _fill_pool:
                        _cand_name = p['name']
                        _cand_norm = _normalize_name(_cand_name)
                        if _cand_name.lower() in _verified_names_post or _cand_norm in _evidence_keys_post:
                            continue
                        _ev_entry = _d1_evidence_log.get(_cand_name, {})
                        if isinstance(_ev_entry, dict) and _ev_entry.get('status') == 'REJECTED':
                            continue
                        # Skip if already in poi_list
                        if _cand_name.lower() in set(p2['name'].lower() for p2 in poi_list):
                            continue
                        # LOCAL-24: Apply work-vs-nonwork filter
                        from story_miner import classify_corpus_entry
                        _post_fill_class = classify_corpus_entry(
                            title=_cand_name,
                            venue_name=_museum_venue_name,
                        )
                        if _post_fill_class['kind'] == 'excluded':
                            print(f"  [POST-R4-FILL] LOCAL-24 blocked: '{_cand_name}' ({_post_fill_class['rule']})")
                            continue
                        p['verified'] = False
                        _post_r4_fill.append(p)
                        if len(_post_r4_fill) >= _unverified_budget:
                            break
                    _post_r4_needed = min(len(_post_r4_fill), total_stops - len(poi_list))
                    _post_r4_added = _post_r4_fill[:_post_r4_needed]
                    if _post_r4_added:
                        poi_list = list(poi_list) + _post_r4_added
                        _tier_label = "50% cap" if _verification_tier not in ('thin', 'medium', 'exhibit_museum') else "no cap"
                        print(f"  [POST-R4-FILL] Added {len(_post_r4_added)} unverified fills "
                              f"(tier={_verification_tier}, {_tier_label}, "
                              f"total now {len(poi_list)}/{total_stops})")

            # -------- [LOCAL-16 GATE] D1v2-verified-only filter for museum tours --------
            # No unverified stop may reach Phase 5 for museum tours. This is the
            # centralized choke-point: after ALL candidate-gathering (R4, UNIFIED-FILL,
            # POST-R4-FILL), strip anything not D1v2-verified. Accept honest shortfall.
            # Also deduplicates by canonical title (round 3 finding).
            if tour_category == 'museum':
                _pre_gate_count = len(poi_list)
                _seen_canonical = set()
                _gate_survivors = []
                _gate_removed = []

                # Build a reverse lookup: normalized poi name → canonical_title
                # D1v2 renames poi['name'] to the canonical form, so the evidence_log
                # key (original GPT name) differs from poi['name']. We need to find
                # the canonical_title for each poi by checking:
                #   1. Direct key lookup (works for R4 stops)
                #   2. Canonical_title match (works for D1v2 renamed stops)
                def _find_canonical_for_poi(poi_name):
                    """Find the canonical title for a poi by any method."""
                    # Direct lookup (R4 uses poi name as key)
                    ev = _d1_evidence_log.get(poi_name, {})
                    if isinstance(ev, dict) and ev.get('canonical_title'):
                        return ev['canonical_title']
                    # Reverse lookup: poi was renamed TO canonical, so check if
                    # any evidence entry has canonical_title matching poi_name
                    _poi_norm = _normalize_name(poi_name)
                    for _key, _val in _d1_evidence_log.items():
                        if isinstance(_val, dict) and _val.get('status') == 'VERIFIED':
                            _ct = _val.get('canonical_title', '')
                            if _ct and _normalize_name(_ct) == _poi_norm:
                                return _ct
                    return None

                for p in poi_list:
                    # Check verification status
                    if not p.get('verified', True):
                        _gate_removed.append(p['name'])
                        continue
                    # Canonical-title dedup: if two stops map to the same canonical,
                    # keep only the first one encountered
                    _canon = _find_canonical_for_poi(p['name'])
                    if _canon:
                        _canon_norm = _normalize_name(_canon)
                        if _canon_norm in _seen_canonical:
                            _gate_removed.append(f"{p['name']} (dup canonical: {_canon})")
                            continue
                        _seen_canonical.add(_canon_norm)
                    _gate_survivors.append(p)

                if _gate_removed:
                    print(f"  [LOCAL-16 GATE] D1v2-verified-only filter for museum tour")
                    print(f"    Removed {len(_gate_removed)} stop(s):")
                    for _rm in _gate_removed:
                        print(f"      ✗ {_rm}")
                    poi_list = _gate_survivors
                    print(f"    After: {len(poi_list)} verified stop(s)")
                    if len(poi_list) < total_stops:
                        print(f"    [LOCAL-16 GATE] Accepting honest shortfall: {len(poi_list)}/{total_stops} stops")
                        # Cap total_stops to prevent Part C and other downstream loops
                        # from re-filling with unverified candidates
                        total_stops = len(poi_list)
                    if len(poi_list) == 0:
                        _LAST_CLEAN_FAIL_EVIDENCE.clear()
                        _LAST_CLEAN_FAIL_EVIDENCE.update({
                            "error_type": "all_unverified",
                            "tier": _verification_tier,
                            "pre_gate_count": _pre_gate_count,
                        })
                        return None, None, (None, None)
                else:
                    print(f"  [LOCAL-16 GATE] All {len(poi_list)} stops are D1v2-verified ✓")

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
                # Count only VERIFIED stops for the suspect-venue check
                _n_verified_for_blocker = sum(1 for p in poi_list if p.get('verified', True))
                if _n_verified_for_blocker == 0:
                    # No verified stops: keep current behavior (use full list)
                    _blocker1_threshold = max(1, len(poi_list) // 2)
                else:
                    _blocker1_threshold = max(1, _n_verified_for_blocker // 2)

                if len(_suspect_venues) >= _blocker1_threshold:
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

        # -------- [WALK-D1] Landmark verification for walking tours (Phase 3) --------
        elif tour_category == 'walking':
            try:
                from area_resolver import resolve_area, discover_landmarks, verify_landmarks, cache_get_area, cache_put_area
                
                _area = resolve_area(_location_normalized)
                if _area and _area.resolved:
                    # Check cache first
                    _cached_landmarks = cache_get_area(_area)
                    if _cached_landmarks:
                        _landmarks = _cached_landmarks
                    else:
                        _landmarks = discover_landmarks(_area)
                        # Cache the results
                        if _landmarks:
                            _walk_tier = "rich" if sum(1 for l in _landmarks if l.qid) >= 8 else "medium"
                            cache_put_area(_area, _landmarks, _walk_tier)
                    
                    if _landmarks:
                        _walk_result = verify_landmarks(poi_list, _area, _landmarks)
                        _verification_tier = _walk_result['tier']
                        _d1_evidence_log = _walk_result['evidence_log']
                        
                        # A7: Replace coordinates with Wikidata P625 for verified stops
                        for poi in _walk_result['pois']:
                            if poi.get('wikidata_lat') and poi.get('wikidata_lng'):
                                poi['latitude'] = poi['wikidata_lat']
                                poi['longitude'] = poi['wikidata_lng']
                        
                        poi_list = _walk_result['pois']
                        _pre_d1v2_candidates = list(poi_list)  # For unified fill compatibility
                        
                        print(f"  [WALK-D1] Verified {sum(1 for p in poi_list if p.get('verified'))} stops, "
                              f"tier={_verification_tier}")
                else:
                    print(f"  [WALK-D1] Area resolution failed for '{_location_normalized}' — proceeding unverified")
            except Exception as e:
                print(f"  [WALK-D1] Error in walking-tour verification (non-fatal): {e}")

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
                f"DO NOT include any of these already-used or rejected names: {forbidden_str}.\n"
                + _transport_stop_constraint +
                "\nRequirements:\n"
                "- REAL, SPECIFIC names; never generic placeholders.\n"
                "- Complete street address with ZIP where applicable.\n\n"
                "Return ONLY a JSON array, no other text:\n"
                '[{"name": "...", "address": "..."}, ...]'
            )
            replacement_data = {
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
                total_cost += _tour_llm_cost(tokens_used)

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
                    # [LOCAL-22] Root-cause guard: reject names that are sentences/descriptions
                    if _is_name_corrupted(name):
                        print(f"   ! [LOCAL-22] Rejected corrupted name from Part C: '{name[:80]}'")
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
                
                # [TRANSPORT-VERIFY] Also verify Part C replacements for transport accessibility
                if survived:
                    survived = _verify_transport_accessibility(survived, transport_mode, location, api_key)

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

        # ──── [LOCAL-212] COVERAGE-AWARE STOP SELECTION ────────────────────────
        # When enabled (DISABLE_COVERAGE_SELECTION != '1'), reorder candidates
        # so COVERED stops are preferred over CREATOR_ONLY, VENUE_ONLY, EMPTY.
        # This is the structural fix: instead of prompting the model not to
        # fabricate on stops with no material, select stops that HAVE material.
        _coverage_selection_disabled = os.environ.get('DISABLE_COVERAGE_SELECTION', '').strip() == '1'

        if not _coverage_selection_disabled and len(poi_list) > total_stops:
            try:
                from stop_corpus_reader import get_stop_corpus_for_tour
                from corpus_coverage import assess_stop_coverage

                # Determine venue name for corpus lookup
                _cs_venue = (_museum_venue_name or location) if tour_category == 'museum' else location
                _cs_stop_names = [p['name'] for p in poi_list]

                # Get DB connection for corpus lookup
                _cs_conn = None
                _cs_db_failure = False
                try:
                    # Try venue_resolver first (same pattern as the later corpus fetch)
                    from venue_resolver import _get_db_connection as _cs_get_conn
                    _cs_conn = _cs_get_conn()
                except Exception as _cs_err1:
                    print(f"  [LOCAL-230] ERROR: Coverage selection DB connect failed (venue_resolver): {type(_cs_err1).__name__}: {_cs_err1}")
                    _cs_db_failure = True
                if not _cs_conn:
                    try:
                        import psycopg2
                        _cs_db_url = os.environ.get(
                            'DATABASE_URL',
                            'postgresql://admin:password123@localhost:5433/audiotours'
                        )
                        _cs_conn = psycopg2.connect(_cs_db_url, connect_timeout=5)
                    except Exception as _cs_err2:
                        print(f"  [LOCAL-230] ERROR: Coverage selection DB connect failed (direct): {type(_cs_err2).__name__}: {_cs_err2}")
                        _cs_db_failure = True

                # [LOCAL-230] Count coverage-selection DB failure in the per-run counter
                if _cs_db_failure:
                    try:
                        import venue_resolver as _vr_mod
                        _vr_mod._network_failure_count += 1
                    except (ImportError, AttributeError):
                        pass

                if _cs_conn:
                    _cs_corpus = get_stop_corpus_for_tour(
                        venue_name=_cs_venue,
                        stop_names=_cs_stop_names,
                        conn=_cs_conn,
                    )
                    _cs_conn.close()

                    # Assess coverage for each candidate
                    _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}
                    _cs_verdicts = {}  # stop_name → verdict string

                    for _cs_name in _cs_stop_names:
                        _cs_data = _cs_corpus.get(_cs_name)
                        if _cs_data and _cs_data.get('passages'):
                            _cs_roles = _cs_data.get('passage_roles')
                            _cs_assessment = assess_stop_coverage(
                                _cs_name, _cs_venue, _cs_data['passages'],
                                passage_roles=_cs_roles
                            )
                        else:
                            _cs_assessment = {'verdict': 'EMPTY'}
                        _cs_verdicts[_cs_name] = _cs_assessment['verdict']

                    # ──── [LOCAL-349] YIELD-BASED SUB-RANKING WITHIN COVERED TIER ────
                    # COVERED candidates are NOT equivalent. A stop with 4 clean
                    # passages from interpretive_enrichment (Acchiardo) vastly
                    # outperforms one with 1 clean passage from web_search
                    # (La Rossettisserie). Rank by expected yield using the
                    # source-weighted quality score from LOCAL-328.
                    #
                    # Yield is a TIE-BREAKER among viable candidates within a
                    # coverage tier — geography, ordering and walkability already
                    # constrain selection (LOCAL-212 route logic) and remain the
                    # primary structural constraint via position order.
                    _cs_quality_scores = {}  # stop_name → quality_score
                    try:
                        from corpus_source_quality import get_bulk_quality_scores
                        # Re-open connection (the reader may have closed it)
                        _cs_yield_conn = None
                        try:
                            from venue_resolver import _get_db_connection as _cs_yc
                            _cs_yield_conn = _cs_yc()
                        except Exception:
                            pass
                        if not _cs_yield_conn:
                            try:
                                import psycopg2 as _cs_pg2
                                _cs_yield_conn = _cs_pg2.connect(
                                    os.environ.get('DATABASE_URL',
                                                   'postgresql://admin:password123@localhost:5433/audiotours'),
                                    connect_timeout=5
                                )
                            except Exception:
                                pass
                        if _cs_yield_conn:
                            _cs_quality_scores = get_bulk_quality_scores(
                                [p['name'] for p in poi_list], _cs_yield_conn
                            )
                            _cs_yield_conn.close()
                    except (ImportError, Exception) as _cs_yield_err:
                        print(f"  [LOCAL-349] Yield scoring unavailable: {_cs_yield_err}")

                    # Sort by (coverage_tier, -quality_score).
                    # Within each tier, higher quality_score sorts first.
                    # When quality_scores are unavailable (all 0), original
                    # position order is preserved (stable sort).
                    poi_list.sort(key=lambda p: (
                        _COVERAGE_PRIORITY.get(
                            _cs_verdicts.get(p['name'], 'EMPTY'), 3
                        ),
                        -_cs_quality_scores.get(p['name'], 0.0),
                    ))

                    # Log the selection
                    _cs_selected = poi_list[:total_stops]
                    _cs_dropped = poi_list[total_stops:]
                    _cs_selected_verdicts = [_cs_verdicts.get(p['name'], 'EMPTY') for p in _cs_selected]
                    _cs_dropped_verdicts = [_cs_verdicts.get(p['name'], 'EMPTY') for p in _cs_dropped]

                    # Count fallbacks
                    _cs_covered_count = sum(1 for v in _cs_selected_verdicts if v == 'COVERED')
                    _cs_fallback_count = total_stops - _cs_covered_count
                    if _cs_fallback_count > 0:
                        _cs_fallback_reasons = []
                        for v in ('CREATOR_ONLY', 'VENUE_ONLY', 'EMPTY'):
                            _cs_cnt = sum(1 for sv in _cs_selected_verdicts if sv == v)
                            if _cs_cnt > 0:
                                _cs_fallback_reasons.append(f"{_cs_cnt}×{v}")
                        print(f"  [LOCAL-212] Coverage selection: {_cs_covered_count} COVERED, "
                              f"fallback needed: {', '.join(_cs_fallback_reasons)} "
                              f"(not enough covered candidates to fill {total_stops} stops)")
                    else:
                        print(f"  [LOCAL-212] Coverage selection: all {total_stops} stops COVERED")

                    print(f"  [LOCAL-212] Selected: {[p['name'] + '=' + _cs_verdicts.get(p['name'], '?') for p in _cs_selected]}")
                    if _cs_dropped:
                        print(f"  [LOCAL-212] Dropped:  {[p['name'] + '=' + _cs_verdicts.get(p['name'], '?') for p in _cs_dropped]}")

                    # [LOCAL-349] Log yield scores when available
                    if _cs_quality_scores and any(v > 0 for v in _cs_quality_scores.values()):
                        _cs_sel_scores = [(p['name'], _cs_quality_scores.get(p['name'], 0.0)) for p in _cs_selected]
                        _cs_drop_scores = [(p['name'], _cs_quality_scores.get(p['name'], 0.0)) for p in _cs_dropped]
                        print(f"  [LOCAL-349] Yield scores (selected): {[f'{n}={s:.1f}' for n, s in _cs_sel_scores]}")
                        if _cs_drop_scores:
                            print(f"  [LOCAL-349] Yield scores (dropped):  {[f'{n}={s:.1f}' for n, s in _cs_drop_scores]}")
                else:
                    if _cs_db_failure:
                        print(f"  [LOCAL-212] Coverage selection: DB connection FAILED — falling back to position order")
                    else:
                        print(f"  [LOCAL-212] Coverage selection: DB unavailable — falling back to position order")
            except ImportError as _cs_err:
                print(f"  [LOCAL-212] Coverage selection: import failed ({_cs_err}) — falling back to position order")
            except Exception as _cs_err:
                print(f"  [LOCAL-212] Coverage selection error (non-fatal): {_cs_err}")
        elif _coverage_selection_disabled:
            print(f"  [LOCAL-212] Coverage selection: DISABLED by DISABLE_COVERAGE_SELECTION=1")
        # ──── END [LOCAL-212] COVERAGE-AWARE STOP SELECTION ───────────────────

        # ──── [LOCAL-465] EXHIBITION RESOLUTION GATE ──────────────────────────
        # After venue resolution and coverage selection, before descriptions.
        # Detects: (1) venue city mismatch, (2) zero coverage, (3) near-match.
        # On NOT_FOUND or DID_YOU_MEAN: abort without generating.
        try:
            from exhibition_resolution import resolve_request, ExhibitionNotFound, is_strict_mode

            if is_strict_mode() and _exhibition_scope is not None and _venue_entity:
                # Build coverage dict from LOCAL-212 results
                _er_verdicts = {}
                _er_covered_count = 0
                _er_total_selected = len(poi_list[:total_stops])
                try:
                    _er_verdicts = _cs_verdicts
                    _er_covered_count = _cs_covered_count
                except NameError:
                    # Coverage selection was disabled or DB unavailable — skip coverage check
                    _er_covered_count = _er_total_selected  # Assume covered to avoid false reject

                _er_coverage = {
                    'covered_count': _er_covered_count,
                    'total_selected': _er_total_selected,
                    'verdicts': _er_verdicts,
                    'fallback_reasons': [],
                }

                # Build resolved_venue dict
                _er_resolved = {
                    'name': _venue_entity.name,
                    'qid': _venue_entity.qid,
                    'official_url': _venue_entity.official_url,
                    'city': _extract_city_from_resolved_entity(_venue_entity),
                }

                # Build candidates list from canonical_titles (already in scope from venue resolution)
                _er_candidates = []
                try:
                    if canonical_titles:
                        _er_candidates = [{'title': t} for t in canonical_titles if t]
                except NameError:
                    pass

                _er_result = resolve_request(
                    request=location,
                    resolved_venue=_er_resolved,
                    coverage=_er_coverage,
                    candidates=_er_candidates,
                )

                if _er_result['verdict'] in ('NOT_FOUND', 'DID_YOU_MEAN'):
                    # Log the rejection
                    print(f"\n  [LOCAL-465] EXHIBITION NOT FOUND: {_er_result['reason']} "
                          f"| request={location!r} "
                          f"| resolved={_venue_entity.name} ({_venue_entity.qid}) "
                          f"| coverage={_er_covered_count}/{_er_total_selected}")

                    # Surface structured evidence for the service layer
                    _LAST_CLEAN_FAIL_EVIDENCE.clear()
                    _LAST_CLEAN_FAIL_EVIDENCE.update({
                        'error_type': 'exhibition_not_found',
                        'verdict': _er_result['verdict'],
                        'reason': _er_result['reason'],
                        'user_message': _er_result['user_message'],
                        'suggestions': _er_result['suggestions'],
                        'request': location,
                        'resolved_venue': _venue_entity.name,
                    })
                    _LAST_GENERATION_COST = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "cache_hit": False,
                        "breakdown": {"llm": 0.0, "tts": 0.0, "search": 0.0},
                    }
                    return None, None, (None, None)
        except ImportError:
            pass  # exhibition_resolution not available — proceed normally
        except Exception as _er_err:
            print(f"  [LOCAL-465] Exhibition resolution gate error (non-fatal): {_er_err}")
        # ──── END [LOCAL-465] EXHIBITION RESOLUTION GATE ──────────────────────

        # ──── [LOCAL-245] STOP-EXISTENCE GATE (INLINE ENFORCEMENT) ────────────
        # Three modes: off / log_only / enforce.
        # In enforce mode, unverified stops are removed from poi_list before
        # narration. The tour may be shorter — this is logged explicitly.
        #
        # [LOCAL-437] EXEMPTION: Checklist-derived stops (exhibition page works)
        # are exempt from the existence gate. They are already grounded against
        # the venue's own page by LOCAL-372 — a stricter check than the gate's
        # independent-web-evidence requirement. Uses the module-scope predicate
        # should_exempt_from_existence_gate() which is imported by the test.
        _seg_requested_stops = total_stops  # [LOCAL-290] Save original request count for replenishment
        _seg_checklist_exempt = should_exempt_from_existence_gate(
            _deterministic_fill_used, _exhibition_stops_source
        )
        if _seg_checklist_exempt:
            print(f"  [LOCAL-437] EXISTENCE-GATE: EXEMPT — stops sourced from exhibition "
                  f"{_exhibition_stops_source} (already grounded against venue page by LOCAL-372)")
        try:
            from stop_existence_gate import get_gate_mode, run_existence_gate, verify_stop_existence

            _seg_mode = get_gate_mode()
            if _seg_mode != 'off' and not _seg_checklist_exempt:
                # Get DB connection (same pattern as LOCAL-212)
                _seg_conn = None
                try:
                    from venue_resolver import _get_db_connection as _seg_get_conn
                    _seg_conn = _seg_get_conn()
                except Exception:
                    pass
                if not _seg_conn:
                    try:
                        import psycopg2
                        _seg_db_url = os.environ.get('DATABASE_URL')
                        if _seg_db_url:
                            _seg_conn = psycopg2.connect(_seg_db_url, connect_timeout=5)
                    except Exception:
                        pass

                if _seg_conn:
                    _seg_venue = (_museum_venue_name or location) if tour_category == 'museum' else location
                    _seg_stop_names = [p['name'] for p in poi_list]
                    # LOCAL-313: pass tour_category so dining tours use the correct
                    # verification path (Nominatim/OSM) instead of museum-shaped checks
                    _seg_result = run_existence_gate(_seg_stop_names, _seg_venue, _seg_conn, tour_type=tour_category)
                    _seg_conn.close()

                    if _seg_mode == 'enforce' and _seg_result['unverified_stops']:
                        _seg_unverified_set = set(_seg_result['unverified_stops'])
                        _seg_before = len(poi_list)
                        poi_list = [p for p in poi_list if p['name'] not in _seg_unverified_set]
                        _seg_after = len(poi_list)
                        _seg_dropped = _seg_before - _seg_after
                        if _seg_dropped > 0:
                            print(f"  [LOCAL-245] EXISTENCE-GATE ENFORCE: dropped {_seg_dropped} unverified stop(s), "
                                  f"{_seg_after} remain (requested {_seg_requested_stops})")
                            for _seg_u in _seg_result['unverified_stops']:
                                print(f"    DROPPED: {_seg_u!r}")
                            if _seg_after < _seg_requested_stops:
                                print(f"  [LOCAL-245] EXISTENCE-GATE: tour SHORT — "
                                      f"{_seg_after}/{_seg_requested_stops} stops, triggering replenishment")
                    # LOCAL-320 bounce: Log inconclusive stops (kept but not verified)
                    _seg_inconclusive = _seg_result.get('inconclusive_stops', [])
                    if _seg_inconclusive:
                        print(f"  [LOCAL-320] {len(_seg_inconclusive)} INCONCLUSIVE stop(s) "
                              f"(kept for delivery, eligible for replacement if verified alternative found)")
                        for _seg_inc in _seg_inconclusive:
                            print(f"    INCONCLUSIVE: {_seg_inc!r}")
                else:
                    print(f"  [LOCAL-245] EXISTENCE-GATE: DB unavailable — gate cannot run, proceeding without")
            else:
                if _seg_checklist_exempt:
                    pass  # Already logged above at [LOCAL-437]
                else:
                    print(f"  [LOCAL-245] EXISTENCE-GATE: OFF (STOP_EXISTENCE_GATE_MODE=off)")
        except ImportError as _seg_err:
            print(f"  [LOCAL-245] EXISTENCE-GATE: import failed ({_seg_err}) — proceeding without")
        except Exception as _seg_err:
            print(f"  [LOCAL-245] EXISTENCE-GATE error (non-fatal): {_seg_err}")
        # ──── END [LOCAL-245] STOP-EXISTENCE GATE ─────────────────────────────

        # ──── [LOCAL-290 Fault 4] GEOGRAPHIC REPLENISHMENT ────────────────────
        # When the existence gate drops stops from a non-museum tour, replenish
        # by asking GPT for fresh candidates and verifying them through the same
        # gate. A replenished stop must pass the same verification as an original.
        # This mirrors R4 for museum tours but uses the existence gate (not D1v2).
        if (tour_category != 'museum' and len(poi_list) < _seg_requested_stops
                and len(poi_list) > 0):
            _rep_needed = _seg_requested_stops - len(poi_list)
            _rep_tried = set(p['name'].lower() for p in poi_list)
            # Also exclude all names we already tried (including dropped ones)
            _rep_tried.update(n.lower() for n in (_seg_result.get('unverified_stops', [])
                                                  if '_seg_result' in dir() else []))
            _REP_MAX_ROUNDS = 2
            _rep_round = 0

            print(f"\n  [LOCAL-290] REPLENISHMENT: need {_rep_needed} more stops "
                  f"(have {len(poi_list)}/{_seg_requested_stops})")

            while len(poi_list) < _seg_requested_stops and _rep_round < _REP_MAX_ROUNDS:
                _rep_round += 1
                _rep_ask = min(_rep_needed + 4, 12)
                _rep_forbidden = sorted(_rep_tried)[:30]
                _rep_forbidden_str = "; ".join(_rep_forbidden) if _rep_forbidden else "(none)"

                _rep_prompt = (
                    f"You are a knowledgeable local guide for {location}.\n"
                    f"List exactly {_rep_ask} specific, real, well-known {poi_type_hint} "
                    f"relevant to: {user_request}.\n"
                    f"DO NOT include: {_rep_forbidden_str}\n"
                    "Requirements:\n"
                    "- Use REAL, SPECIFIC names of actual places/landmarks.\n"
                    "- These must be well-documented places that appear on Wikipedia or maps.\n"
                    "- Include a complete street address where applicable.\n"
                    '\nReturn ONLY a JSON array: [{"name": "...", "address": "..."}]'
                )
                _rep_data = {
                    "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                    "messages": [
                        {"role": "system", "content": "Return ONLY valid JSON arrays."},
                        {"role": "user", "content": _rep_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                }
                try:
                    _rep_resp = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers, data=json.dumps(_rep_data)
                    )
                    if _rep_resp.status_code != 200:
                        print(f"    [LOCAL-290] Replenishment API error {_rep_resp.status_code}")
                        break
                    _rep_result = _rep_resp.json()
                    _rep_text = _rep_result["choices"][0]["message"]["content"]
                    tokens_used = _rep_result["usage"]["total_tokens"]
                    total_tokens += tokens_used
                    total_cost += _tour_llm_cost(tokens_used)

                    _rep_candidates = _parse_json_array_loose(_rep_text)
                    if not _rep_candidates:
                        print(f"    [LOCAL-290] Replenishment round {_rep_round}: unparseable response")
                        continue

                    # Deduplicate and verify through existence gate
                    _rep_new_names = []
                    for c in _rep_candidates:
                        if not isinstance(c, dict):
                            continue
                        name = (c.get("name") or "").strip()
                        if not name or name.lower() in _rep_tried:
                            continue
                        if _is_name_corrupted(name):
                            _rep_tried.add(name.lower())
                            continue
                        _rep_tried.add(name.lower())
                        _rep_new_names.append((name, c.get("address") or ""))

                    if not _rep_new_names:
                        print(f"    [LOCAL-290] Replenishment round {_rep_round}: no new candidates after dedup")
                        break

                    # Verify new candidates through the same existence gate
                    _rep_conn = None
                    try:
                        from venue_resolver import _get_db_connection as _rep_get_conn
                        _rep_conn = _rep_get_conn()
                    except Exception:
                        pass
                    if not _rep_conn:
                        try:
                            import psycopg2
                            _rep_db_url = os.environ.get('DATABASE_URL')
                            if _rep_db_url:
                                _rep_conn = psycopg2.connect(_rep_db_url, connect_timeout=5)
                        except Exception:
                            pass

                    if _rep_conn:
                        _rep_venue = location
                        _rep_name_list = [n for n, _ in _rep_new_names]
                        # LOCAL-313: pass tour_category for dining verification
                        _rep_gate_result = run_existence_gate(
                            _rep_name_list, _rep_venue, _rep_conn, tour_type=tour_category)
                        _rep_conn.close()

                        _rep_verified_names = set(_rep_gate_result.get('verified_stops', []))
                        _rep_added = 0
                        for name, addr in _rep_new_names:
                            if name in _rep_verified_names and len(poi_list) < _seg_requested_stops:
                                poi_list.append(_new_poi(name, addr))
                                _rep_added += 1
                                # Find evidence for logging
                                _rep_ev = ""
                                for v in _rep_gate_result.get('verdicts', []):
                                    if v.get('stop_title') == name:
                                        _rep_ev = v.get('evidence', '')[:60]
                                        break
                                print(f"    [LOCAL-290] REPLENISHED: '{name}' — {_rep_ev}")
                        print(f"    [LOCAL-290] Round {_rep_round}: +{_rep_added} verified, "
                              f"total now {len(poi_list)}/{_seg_requested_stops}")
                    else:
                        print(f"    [LOCAL-290] Replenishment: DB unavailable for verification")
                        break
                except Exception as e:
                    print(f"    [LOCAL-290] Replenishment error: {e}")
                    break

            if len(poi_list) < _seg_requested_stops:
                print(f"  [LOCAL-290] Replenishment exhausted: {len(poi_list)}/{_seg_requested_stops} stops")
                total_stops = len(poi_list)
            else:
                total_stops = _seg_requested_stops
                print(f"  [LOCAL-290] Replenishment SUCCESS: {len(poi_list)}/{_seg_requested_stops} stops")
        # ──── END [LOCAL-290] GEOGRAPHIC REPLENISHMENT ────────────────────────

        # ──── LOCAL-320 bounce: INCONCLUSIVE REPLACEMENT ──────────────────────
        # If any stops are inconclusive (search failed, kept for delivery),
        # try to find verified replacements. Prefer a verified stop over an
        # unchecked one. If no replacement verifies, keep the inconclusive stop
        # (do not lose delivery — D162).
        _seg_inconclusive_set = set(_seg_result.get('inconclusive_stops', [])
                                    if '_seg_result' in dir() else [])
        if (tour_category != 'museum' and _seg_inconclusive_set
                and _seg_mode == 'enforce' and len(poi_list) > 0):
            _inc_tried = set(p['name'].lower() for p in poi_list)
            _inc_tried.update(n.lower() for n in (_seg_result.get('unverified_stops', [])
                                                  if '_seg_result' in dir() else []))
            print(f"\n  [LOCAL-320] INCONCLUSIVE REPLACEMENT: attempting to replace "
                  f"{len(_seg_inconclusive_set)} inconclusive stop(s) with verified alternatives")

            _inc_ask = min(len(_seg_inconclusive_set) + 4, 12)
            _inc_forbidden = sorted(_inc_tried)[:30]
            _inc_forbidden_str = "; ".join(_inc_forbidden) if _inc_forbidden else "(none)"

            _inc_prompt = (
                f"You are a knowledgeable local guide for {location}.\n"
                f"List exactly {_inc_ask} specific, real, well-known {poi_type_hint} "
                f"relevant to: {user_request}.\n"
                f"DO NOT include: {_inc_forbidden_str}\n"
                "Requirements:\n"
                "- Use REAL, SPECIFIC names of actual places/landmarks.\n"
                "- These must be well-documented places that appear on Wikipedia or maps.\n"
                "- Include a complete street address where applicable.\n"
                '\nReturn ONLY a JSON array: [{"name": "...", "address": "..."}]'
            )
            _inc_data = {
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                "messages": [
                    {"role": "system", "content": "Return ONLY valid JSON arrays."},
                    {"role": "user", "content": _inc_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 600,
            }
            try:
                _inc_resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers, data=json.dumps(_inc_data)
                )
                if _inc_resp.status_code == 200:
                    _inc_result = _inc_resp.json()
                    _inc_text = _inc_result["choices"][0]["message"]["content"]
                    tokens_used = _inc_result["usage"]["total_tokens"]
                    total_tokens += tokens_used
                    total_cost += _tour_llm_cost(tokens_used)

                    _inc_candidates = _parse_json_array_loose(_inc_text)
                    _inc_new_names = []
                    for c in (_inc_candidates or []):
                        if not isinstance(c, dict):
                            continue
                        name = (c.get("name") or "").strip()
                        if not name or name.lower() in _inc_tried:
                            continue
                        if _is_name_corrupted(name):
                            _inc_tried.add(name.lower())
                            continue
                        _inc_tried.add(name.lower())
                        _inc_new_names.append((name, c.get("address") or ""))

                    if _inc_new_names:
                        _inc_conn = None
                        try:
                            from venue_resolver import _get_db_connection as _inc_get_conn
                            _inc_conn = _inc_get_conn()
                        except Exception:
                            pass
                        if not _inc_conn:
                            try:
                                import psycopg2
                                _inc_db_url = os.environ.get('DATABASE_URL')
                                if _inc_db_url:
                                    _inc_conn = psycopg2.connect(_inc_db_url, connect_timeout=5)
                            except Exception:
                                pass

                        if _inc_conn:
                            _inc_name_list = [n for n, _ in _inc_new_names]
                            _inc_gate_result = run_existence_gate(
                                _inc_name_list, location, _inc_conn, tour_type=tour_category)
                            _inc_conn.close()

                            _inc_verified_names = set(_inc_gate_result.get('verified_stops', []))
                            _inc_replaced = 0
                            # Replace inconclusive stops with verified alternatives
                            for name, addr in _inc_new_names:
                                if name in _inc_verified_names and _seg_inconclusive_set:
                                    # Find an inconclusive stop to replace
                                    _target = next(iter(_seg_inconclusive_set))
                                    _seg_inconclusive_set.discard(_target)
                                    # Swap in poi_list
                                    for idx, p in enumerate(poi_list):
                                        if p['name'] == _target:
                                            poi_list[idx] = _new_poi(name, addr)
                                            _inc_replaced += 1
                                            _inc_ev = ""
                                            for v in _inc_gate_result.get('verdicts', []):
                                                if v.get('stop_title') == name:
                                                    _inc_ev = v.get('evidence', '')[:60]
                                                    break
                                            print(f"    [LOCAL-320] REPLACED inconclusive '{_target}' "
                                                  f"with verified '{name}' — {_inc_ev}")
                                            break
                            if _inc_replaced:
                                print(f"    [LOCAL-320] Replaced {_inc_replaced} inconclusive stop(s)")
                            else:
                                print(f"    [LOCAL-320] No verified replacements found — "
                                      f"keeping inconclusive stops for delivery")
                        else:
                            print(f"    [LOCAL-320] DB unavailable for inconclusive replacement")
                    else:
                        print(f"    [LOCAL-320] No new candidates for inconclusive replacement")
                else:
                    print(f"    [LOCAL-320] Inconclusive replacement API error {_inc_resp.status_code}")
            except Exception as _inc_err:
                print(f"    [LOCAL-320] Inconclusive replacement error (non-fatal): {_inc_err}")
        # ──── END LOCAL-320 INCONCLUSIVE REPLACEMENT ──────────────────────────

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

        # [LOCAL-326] Phase-boundary cost checkpoint: before Phase 3B.
        # Saves Phase 3B + Phase 5 on breach.
        _check_phase_boundary_cost(total_cost, "pre-Phase3B")

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
            # [LOCAL-27] Museum tours: do NOT ask GPT to invent type_specialty,
            # specific_examples, or operational_details. These fields must be
            # sourced from verified data or omitted entirely.
            _is_museum_tour = (tour_category == 'museum' and _museum_venue_name)
            if _is_museum_tour:
                _json_schema_block = (
                    "[\n  {\n"
                    '    "name": "<must match one of the input names exactly>",\n'
                    '    "address": "<complete street address with ZIP>",\n'
                    '    "coordinates": "<lat, lng in decimal format>",\n'
                    '    "directions_from_previous": "<turn-by-turn directions + one observational sentence>"\n'
                    "  }\n]"
                )
            else:
                _json_schema_block = (
                    "[\n  {\n"
                    '    "name": "<must match one of the input names exactly>",\n'
                    '    "address": "<complete street address with ZIP>",\n'
                    '    "coordinates": "<lat, lng in decimal format>",\n'
                    '    "type_specialty": "<short type/specialty description>",\n'
                    '    "specific_examples": "<2-3 concrete examples of what visitors will see/experience>",\n'
                    '    "operational_details": "<hours, prices, reservations, busy times>",\n'
                    '    "directions_from_previous": "<turn-by-turn directions + one observational sentence>"\n'
                    "  }\n]"
                )
            prompt = (
                f"For a tour of {location}, the following {len(current_poi_list)} stop(s) have been selected "
                "in the order shown (this order has been optimised algorithmically — do NOT change it):\n"
                + "\n".join(s_lines) + "\n\n"
                "For each stop IN THE EXACT ORDER ABOVE, provide all the JSON fields below.\n"
                "For stop #1, 'directions_from_previous' should describe how to reach it from a reasonable arrival point (T station, parking, main street).\n"
                f"For subsequent stops, 'directions_from_previous' should be {'turn-by-turn walking directions' if transport_mode == 'on_foot' else f'route directions suitable for {transport_mode} travel'} from the IMMEDIATELY PREVIOUS stop in the list.\n"
                "IMPORTANT: each 'directions_from_previous' should END with one brief observational or connective sentence — "
                "something the visitor might notice in transit (a change in architecture, a glimpse of something ahead, the sound of a market). "
                "Keep this to ONE sentence after the navigation, not a full paragraph.\n\n"
                "Return ONLY a JSON array, no markdown fences, no commentary:\n"
                + _json_schema_block
            )
            req_data = {
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
                total_cost += _tour_llm_cost(tokens_used)
                print(f"PHASE 3B API call cost: ${_tour_llm_cost(tokens_used):.4f} ({tokens_used} tokens)")
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
                    # [LOCAL-27] For museum tours: never populate type_specialty,
                    # specific_examples, or operational_details from GPT output.
                    # These will be sourced from corpus data downstream or omitted.
                    if _is_museum_tour:
                        merged['type_specialty'] = ''
                        merged['specific_examples'] = ''
                        merged['operational_details'] = ''
                    else:
                        merged['type_specialty'] = (entry.get('type_specialty') or '').strip()
                        merged['specific_examples'] = (entry.get('specific_examples') or '').strip()
                        merged['operational_details'] = (entry.get('operational_details') or '').strip()
                    # [PALAIS-FIX B1] verified flag must survive the Phase 3B rebuild —
                    # it drives hedged narration and stop_metrics persistence downstream
                    if orig and 'verified' in orig:
                        merged['verified'] = orig['verified']
                    new_list.append(merged)
                print(f"OK PHASE 3B: ordered {len(new_list)} stop(s) with structured details and directions")
                return new_list
            except Exception as e:
                print(f"! PHASE 3B exception: {e}; keeping current order")
                return current_poi_list

        # [LOCAL-7] Deterministic route ordering: compute optimal walking order
        # BEFORE asking GPT for structured details/directions. Uses real Wikidata
        # coordinates for verified stops, GPT's guessed coordinates as fallback.
        if tour_category == 'walking' and len(poi_list) >= 3:
            poi_list = _compute_route_order(poi_list)

        # ──── [LOCAL-329] PERSIST SELECTION REASONS AS CORPUS ─────────────────
        # Selection-stage reasons are leads, not claims. Persist them in stop_corpus
        # with source attribution so downstream content has material to work with.
        # Only persist for stops that survived all gates (existence, type, geo).
        if _selection_reasons and tour_category in ('restaurant', 'walking'):
            try:
                from selection_reason_filter import persist_selection_reasons
                _surviving_names = [p['name'] for p in poi_list]
                _venue_for_reasons = location
                _reasons_persisted = persist_selection_reasons(
                    _selection_reasons, _surviving_names, _venue_for_reasons
                )
                if _reasons_persisted > 0:
                    print(f"  [LOCAL-329] Persisted {_reasons_persisted} selection reason(s) to stop_corpus")
            except ImportError as _sr_err:
                print(f"  [LOCAL-329] Selection reason persistence: import failed ({_sr_err})")
            except Exception as _sr_err:
                print(f"  [LOCAL-329] Selection reason persistence error (non-fatal): {_sr_err}")
        # ──── END [LOCAL-329] ─────────────────────────────────────────────────

        print(f"\nPHASE 3B: Requesting structured details and walking directions for {len(poi_list)} stop(s)...")
        api_call_logger.log("PHASE_3B_REQUEST", {
            "location": location,
            "stop_count": len(poi_list),
        })

        poi_list = _run_phase_3b(poi_list)

        # -------- [LOCAL-27] Corpus-sourced metadata for museum tours --------
        # After Phase 3B, populate type_specialty from VERIFIED corpus data only.
        # Never invent: if corpus doesn't confirm the metadata, leave it blank.
        if tour_category == 'museum' and _museum_venue_name and _story_corpus_result:
            _per_work_ctx = _story_corpus_result.get('per_work_contexts', {})
            _combined_corpus = _story_corpus_result.get('combined_text', '')
            try:
                from story_miner import _normalize
            except ImportError:
                _import_logger.error("[D1v2] MISSING: story_miner._normalize — using inline fallback (corpus matching degraded)")
                import unicodedata
                def _normalize(text):
                    if not text: return ""
                    nfkd = unicodedata.normalize('NFKD', text.lower())
                    return ''.join(c for c in nfkd if not unicodedata.combining(c))
            for poi in poi_list:
                _poi_norm = _normalize(poi['name'])
                # Try to derive type_specialty from corpus sentences about this work
                _corpus_type = ''
                for _title, _sents in _per_work_ctx.items():
                    if _poi_norm[:8] in _normalize(_title) or _normalize(_title)[:8] in _poi_norm:
                        # Look for medium/technique/period mentions in corpus sentences
                        for _s in _sents[:5]:
                            _s_lower = _s.lower()
                            _medium_matches = re.findall(
                                r'\b(oil on canvas|gouache|lithograph|mosaic|stained glass|'
                                r'sculpture|bronze|marble|ceramic|watercolor|watercolour|'
                                r'tempera|fresco|etching|woodcut|tapestry|pastel|charcoal|'
                                r'ink|acrylic|mixed media|installation|photograph|'
                                r'huile sur toile|peinture|gravure|mosaïque|vitrail)\b',
                                _s_lower
                            )
                            if _medium_matches:
                                _corpus_type = _medium_matches[0].title()
                                break
                        if _corpus_type:
                            break
                if _corpus_type:
                    poi['type_specialty'] = _corpus_type
                    print(f"  [LOCAL-27] type_specialty for '{poi['name']}' sourced from corpus: {_corpus_type}")
                # specific_examples: only populate if we have concrete corpus evidence
                # (per_work_contexts sentences that name specific verifiable items)
                # Otherwise leave blank — better absent than invented
            print(f"  [LOCAL-27] Corpus-sourced metadata applied to {len(poi_list)} stops")

        # -------- [LOCAL-39] Source visitor info from official site (museum tours only) --------
        # Composes LOCAL-35 (structured extraction) with LOCAL-36 (provenance gate):
        # - LOCAL-35's visitor_facts_extractor extracts closed_days, hours (seasonal),
        #   admission (conditional) as structured fields. Never flattens "Free" incorrectly.
        # - LOCAL-36's practical_facts_gate verifies each claim against the raw source.
        # - LOCAL-39 wires them together: structured facts + raw source in one fetch.
        _visitor_info_source_url = ''
        _visitor_info_source_text = ''
        if tour_category == 'museum' and _museum_venue_name:
            _sourced_visitor_info = ''
            _official_url_for_info = ''
            if _story_corpus_result and _story_corpus_result.get('source_urls'):
                _official_url_for_info = _story_corpus_result['source_urls'][0]
            if _official_url_for_info:
                try:
                    from visitor_facts_extractor import fetch_visitor_info_with_provenance
                    _provenance_result = fetch_visitor_info_with_provenance(
                        _official_url_for_info, language="en")
                    _sourced_visitor_info = _provenance_result.formatted_info
                    _visitor_info_source_url = _provenance_result.source_url
                    _visitor_info_source_text = _provenance_result.source_text
                except ImportError:
                    print(f"  [LOCAL-39] visitor_facts_extractor not available, falling back to old method")
                    _sourced_visitor_info = _fetch_visitor_info_from_site(_official_url_for_info, language="en")
                    _visitor_info_source_url = _official_url_for_info
                    _visitor_info_source_text = _fetch_visitor_info_raw_source(_official_url_for_info)
            # -------- [LOCAL-91] Corpus-text fallback with provenance --------
            # Originally LOCAL-34/75 extracted visitor info from combined_text without
            # provenance. LOCAL-91 rewires this: iterates story_miner's individual pages
            # (each with URL + raw text) so practical_facts_gate can verify claims.
            # Falls back to combined_text extraction (LOCAL-34 style) only when pages
            # are unavailable, but in that case no provenance means the gate will still
            # reject unverifiable claims — as designed.
            if not _sourced_visitor_info and _story_corpus_result and _story_corpus_result.get('pages'):
                try:
                    from visitor_facts_extractor import extract_visitor_facts_from_text
                    _corpus_pages = _story_corpus_result['pages']
                    _best_corpus_facts = None
                    _best_corpus_score = -1
                    _best_corpus_page_url = ''
                    _best_corpus_page_text = ''
                    for _cp in _corpus_pages:
                        _cp_text = _cp.get('text', '')
                        _cp_url = _cp.get('url', '')
                        if not _cp_text or len(_cp_text) < 100:
                            continue
                        # Detect language for extraction
                        _cp_lower = _cp_text[:2000].lower()
                        _fr_sig = sum(1 for w in ['fermé', 'horaires', 'tarifs', 'ouvert', 'gratuit', 'mardi']
                                      if w in _cp_lower)
                        _en_sig = sum(1 for w in ['closed', 'hours', 'admission', 'open', 'free', 'tuesday']
                                      if w in _cp_lower)
                        _cp_lang = "en" if _en_sig > _fr_sig else "fr"
                        _cp_facts = extract_visitor_facts_from_text(_cp_text, _cp_lang)
                        # Score: admission with price is critical
                        _cp_score = 0
                        _cp_score += min(len(_cp_facts.hours), 2) * 2
                        if _cp_facts.admission:
                            _cp_score += 3
                            if re.search(r'€\d+|\d+\s*€', _cp_facts.admission):
                                _cp_score += 2
                        if _cp_facts.closed_days:
                            _cp_score += 1
                        if _cp_score > _best_corpus_score:
                            _best_corpus_score = _cp_score
                            _best_corpus_facts = _cp_facts
                            _best_corpus_page_url = _cp_url
                            _best_corpus_page_text = _cp_text
                    # Use if we found anything substantive (at least closed day OR admission)
                    if _best_corpus_facts and not _best_corpus_facts.is_empty():
                        _formatted = _best_corpus_facts.format_en()
                        if _formatted and len(_formatted) >= 10:
                            _sourced_visitor_info = _formatted
                            _visitor_info_source_url = _best_corpus_page_url
                            _visitor_info_source_text = _best_corpus_page_text[:10000]
                            print(f"  [LOCAL-91] Corpus fallback: visitor info extracted from {_best_corpus_page_url}")
                            print(f"  [LOCAL-91] Corpus fallback Museum Information: {_formatted}")
                except ImportError:
                    print(f"  [LOCAL-91] visitor_facts_extractor not available for corpus fallback")
                except Exception as _cf_err:
                    print(f"  [LOCAL-91] Corpus fallback error (non-fatal): {_cf_err}")
            # [LOCAL-34] Secondary fallback: combined_text (no provenance — gate will
            # reject unverifiable claims, which is correct behavior)
            if not _sourced_visitor_info and _story_corpus_result and _story_corpus_result.get('combined_text'):
                _sourced_visitor_info = _extract_visitor_info_from_corpus(
                    _story_corpus_result['combined_text'], language="en"
                )
                if _sourced_visitor_info:
                    print(f"  [LOCAL-34] Visitor info extracted from corpus text (main page fallback, no provenance)")
            if _sourced_visitor_info and poi_list:
                poi_list[0]['operational_details'] = _sourced_visitor_info
                print(f"  [LOCAL-39] Museum Information sourced from official site for stop 1")
            else:
                for poi in poi_list:
                    poi['operational_details'] = ''
                print(f"  [LOCAL-39] No visitor info sourced — Museum Information field OMITTED")

        # -------- [LOCAL-353] Source operational details from OSM (restaurant tours) --------
        # For restaurant/dining tours, query OpenStreetMap for sourceable operational
        # facts: opening_hours, payment methods, reservation, price_range.
        # These replace GPT-invented operational_details (which the gate correctly kills).
        # The OSM source text is stored so the practical facts gate can verify each claim.
        _osm_dining_source_url = ''
        _osm_dining_source_text = ''
        if tour_category == 'restaurant' and poi_list:
            try:
                from osm_dining_facts import fetch_osm_dining_facts, extract_city_from_venue_name
                _osm_city = extract_city_from_venue_name(location)
                if _osm_city:
                    print(f"  [LOCAL-353] Querying OSM for dining operational details (city: {_osm_city})")
                    _osm_source_texts = []
                    _osm_source_urls = []
                    for poi in poi_list:
                        _osm_facts = fetch_osm_dining_facts(poi['name'], _osm_city)
                        if not _osm_facts.is_empty():
                            # Replace GPT-invented operational_details with OSM-sourced facts
                            poi['operational_details'] = _osm_facts.format_operational_details()
                            _osm_source_texts.append(_osm_facts.source_text)
                            _osm_source_urls.append(_osm_facts.source_url)
                            print(f"  [LOCAL-353] {poi['name']}: sourced → {poi['operational_details']}")
                        else:
                            # No OSM operational data — clear GPT invention (gate would kill it anyway)
                            poi['operational_details'] = ''
                            print(f"  [LOCAL-353] {poi['name']}: no sourceable facts in OSM — omitted")
                    # Combine all OSM source texts for the gate
                    if _osm_source_texts:
                        _osm_dining_source_text = "\n\n".join(_osm_source_texts)
                        _osm_dining_source_url = ", ".join(_osm_source_urls[:3])
                        # Store for the practical facts gate downstream
                        _visitor_info_source_url = _osm_dining_source_url
                        _visitor_info_source_text = _osm_dining_source_text
                else:
                    print(f"  [LOCAL-353] Could not extract city from location — OSM lookup skipped")
            except ImportError:
                print(f"  [LOCAL-353] osm_dining_facts not available — operational details unchanged")
            except Exception as _osm_err:
                print(f"  [LOCAL-353] OSM dining facts error (non-fatal): {_osm_err}")

            # -------- [LOCAL-354] Source price band from dining guides --------
            # OSM carries payment/hours but no price for Nice restaurants.
            # Le Fooding and Gault&Millau publish price indications.
            # Combine into one sentence per Michael's format:
            #   "An average dinner or lunch would cost under €50 but credit cards are not accepted"
            try:
                from guide_price_band import get_dining_sentence, build_price_source_text
                print(f"  [LOCAL-354] Sourcing price bands from dining guides")
                for poi in poi_list:
                    # Get payment info from what OSM already found
                    _poi_payment = ''
                    if 'operational_details' in poi and poi['operational_details']:
                        # Extract payment fragment if present
                        if 'Cash only' in poi['operational_details']:
                            _poi_payment = 'Cash only'
                        elif 'Card payments only' in poi['operational_details']:
                            _poi_payment = 'Card payments only'

                    sentence, guide_url, guide_source = get_dining_sentence(
                        poi['name'], _poi_payment
                    )
                    if sentence:
                        # Replace operational_details with the combined sentence
                        poi['operational_details'] = sentence
                        # Append guide source to the gate source texts
                        if guide_source:
                            _osm_source_texts.append(guide_source)
                            if guide_url:
                                _osm_source_urls.append(guide_url)
                        print(f"  [LOCAL-354] {poi['name']}: → {sentence}")
                    elif not poi.get('operational_details'):
                        print(f"  [LOCAL-354] {poi['name']}: no guide price, no OSM facts — silence")

                # Rebuild combined source text with guide additions
                if _osm_source_texts:
                    _osm_dining_source_text = "\n\n".join(_osm_source_texts)
                    _osm_dining_source_url = ", ".join(_osm_source_urls[:5])
                    _visitor_info_source_url = _osm_dining_source_url
                    _visitor_info_source_text = _osm_dining_source_text
            except ImportError:
                print(f"  [LOCAL-354] guide_price_band not available — price bands unchanged")
            except Exception as _guide_err:
                print(f"  [LOCAL-354] Guide price band error (non-fatal): {_guide_err}")

        # -------- [LOCAL-355] Source operational details from OSM (non-dining tours) --------
        # For museum, walking, and park tours: query OSM for practical visitor facts
        # (opening_hours, fee/admission, timed entry). Same provenance model as LOCAL-353.
        if tour_category in ('museum', 'walking') and poi_list:
            try:
                from osm_venue_facts import fetch_osm_venue_facts, extract_city_from_venue_name as _extract_city
                _osm_city = _extract_city(location)
                if _osm_city:
                    _venue_hint = 'museum' if tour_category == 'museum' else ''
                    print(f"  [LOCAL-355] Querying OSM for venue facts (city: {_osm_city}, hint: {_venue_hint or 'auto'})")
                    _osm_source_texts_355 = []
                    _osm_source_urls_355 = []
                    for poi in poi_list:
                        _osm_facts = fetch_osm_venue_facts(poi['name'], _osm_city, venue_hint=_venue_hint)
                        if not _osm_facts.is_empty():
                            # Only replace if no visitor info was already sourced (LOCAL-34/39)
                            if not poi.get('operational_details'):
                                poi['operational_details'] = _osm_facts.format_practical_sentence()
                            _osm_source_texts_355.append(_osm_facts.source_text)
                            _osm_source_urls_355.append(_osm_facts.source_url)
                            print(f"  [LOCAL-355] {poi['name']}: sourced → {_osm_facts.format_practical_sentence()}")
                        else:
                            print(f"  [LOCAL-355] {poi['name']}: no practical facts in OSM")
                    if _osm_source_texts_355:
                        # Append to existing source text (don't overwrite LOCAL-34 website sources)
                        _osm_355_combined = "\n\n".join(_osm_source_texts_355)
                        if _visitor_info_source_text:
                            _visitor_info_source_text += "\n\n" + _osm_355_combined
                        else:
                            _visitor_info_source_text = _osm_355_combined
                            _visitor_info_source_url = ", ".join(_osm_source_urls_355[:3])
                else:
                    print(f"  [LOCAL-355] Could not extract city from location — OSM lookup skipped")
            except ImportError:
                print(f"  [LOCAL-355] osm_venue_facts not available — operational details unchanged")
            except Exception as _osm_err:
                print(f"  [LOCAL-355] OSM venue facts error (non-fatal): {_osm_err}")

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
                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
                        total_cost += _tour_llm_cost(tokens_used)
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
                                total_cost += _tour_llm_cost(tokens_used)
                                print(f"   Cluster refetch OK '{poi['name']}': {coords}")
                            else:
                                print(f"   Cluster refetch FAILED '{poi['name']}' -- no map pin")


        # -------- Walking-compactness geometric verification --------
        # Deterministic. Catches gross dispersion the PHASE 3A prompt missed.
        # Straight-line distance is a guaranteed LOWER BOUND on walking distance, so a
        # leg over the hard limit is unarguably too far to walk.
        # ADVISORY: never raises ValueError, never removes all stops.
        # Touchpoint 4: graduated distance tiers by transport_mode (KIRO_REVIEW_08)
        if tour_category == 'walking' and transport_mode != 'country_scale':
            pts = [(p, _parse_coords(p.get('coordinates', ''))) for p in poi_list]
            pts_valid = [(p, c) for p, c in pts if c]
            if len(pts_valid) >= 3:
                _total_limit = _TRANSPORT_TOTAL_HARD_KM.get(transport_mode, WALKING_TOTAL_HARD_KM)
                legs = [_haversine_km(pts_valid[i][1], pts_valid[i+1][1]) for i in range(len(pts_valid) - 1)]
                total_route_km = sum(legs)
                medoid = min(pts_valid, key=lambda pc: sum(_haversine_km(pc[1], o) for _, o in pts_valid))[1]
                outliers = []
                # Per-leg check only applies to on_foot — animal/bike/vehicle skip straight to total check
                if transport_mode == 'on_foot':
                    for i, leg in enumerate(legs):
                        if leg > WALKING_LEG_HARD_KM:
                            a, b = pts_valid[i], pts_valid[i+1]
                            farther = a[0] if _haversine_km(a[1], medoid) > _haversine_km(b[1], medoid) else b[0]
                            outliers.append(farther)
                if total_route_km > _total_limit and not outliers:
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
                            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
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
                                total_cost += _tour_llm_cost(rep_tokens)
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
                                    total_cost += _tour_llm_cost(tok_r)
                                    print(f"   GEO-CHECK coords OK '{poi_r['name']}': {coords_r}")
                                else:
                                    print(f"   GEO-CHECK coords FAILED '{poi_r['name']}'")

                    # Re-order the combined set (survivors + replacements)
                    if len(poi_list) > 1:
                        # [LOCAL-7] Re-apply deterministic route ordering after geo-check replacements
                        if tour_category == 'walking' and len(poi_list) >= 3:
                            poi_list = _compute_route_order(poi_list)
                        print(f"\nPHASE 3B (re-order after GEO-CHECK): {len(poi_list)} stop(s)...")
                        poi_list = _run_phase_3b(poi_list)

                elif outliers:
                    print(f"   GEO-CHECK: all stops flagged — keeping original list (advisory only)")
                else:
                    print(f"   GEO-CHECK: all {len(poi_list)} stops within walking distance (max leg {max(legs):.2f} km, total {total_route_km:.2f} km)")
            else:
                print(f"   GEO-CHECK: skipped (fewer than 3 stops have coordinates)")

        # Country-scale containment check (KIRO_REVIEW_08)
        # For country_scale tours, validate each stop is within the target country (or its enclaves)
        if tour_category == 'walking' and transport_mode == 'country_scale' and _country_scope:
            out_of_country = []
            for p in poi_list:
                addr = p.get('address', '')
                if addr and not _stop_in_country_scope(addr, _country_scope):
                    out_of_country.append(p)
                    print(f"   COUNTRY-CHECK: '{p['name']}' address '{addr}' NOT in '{_country_scope}' — flagged")
                else:
                    print(f"   COUNTRY-CHECK: '{p['name']}' OK (in '{_country_scope}' or enclave)")
            if out_of_country and (len(poi_list) - len(out_of_country)) >= 2:
                for p in out_of_country:
                    forbidden_norms.add(_normalize_name(p['name']))
                poi_list = [p for p in poi_list if p not in out_of_country]
                print(f"   COUNTRY-CHECK: {len(out_of_country)} out-of-country stop(s) removed; {len(poi_list)} remain")
            elif out_of_country:
                print(f"   COUNTRY-CHECK: all stops flagged — keeping original list (advisory only)")

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
    except _CostCeilingBreached as _ccb:
        # [LOCAL-326] Cost ceiling breached before Phase 5. We have poi_list with names
        # but no descriptions yet. Assemble a stub tour listing the stops so downstream
        # knows what was planned. This is the "degrade, not vanish" path.
        print(f"[LOCAL-326] Assembling partial tour (no descriptions): "
              f"breached at {_ccb.phase}, ${_ccb.cost:.4f} > ${_ccb.limit:.4f}")
        _partial_header = (
            f"Step-by-Step Audio Guided Tour: {location}\n"
            f"Tour-Category: {tour_category}\n"
            f"[PARTIAL TOUR — generation stopped at {_ccb.phase} due to cost ceiling "
            f"(${_ccb.cost:.4f} > ${_ccb.limit:.4f})]\n\n"
        )
        _partial_body = ""
        for _pi, _pp in enumerate(poi_list):
            _partial_body += f"Stop {_pi + 1}: {_pp.get('name', 'Unknown')}\n"
            if _pp.get('address'):
                _partial_body += f"Address: {_pp['address']}\n"
            _partial_body += "[Description not generated — cost ceiling reached]\n\n"
        _partial_tour = _partial_header + _partial_body
        # Expose cost for metering (cost was spent even though tour is partial)
        _LAST_GENERATION_COST = {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "cache_hit": False,
            "breakdown": {"llm": total_cost, "tts": 0.0, "search": 0.0},
        }
        if output_file:
            with open(output_file, "w", encoding="utf-8") as _pf:
                _pf.write(_partial_tour)
        return _partial_tour, output_file, (None, None)
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
    
    # [LOCAL-183] Helper: merge stop_corpus passages into per_work_contexts dict
    # so that generate_fact_sheets_parallel picks them up via its title-match logic.
    def _merge_stop_corpus_into_per_work(per_work_contexts: dict, stop_corpus_data: dict) -> dict:
        """Merge stop_corpus passages into per_work_contexts.

        per_work_contexts is {title: [sentences]}. For each stop that has
        stop_corpus data, add its passages as sentences keyed by the stop name.
        Existing entries are preserved (stop_corpus supplements, doesn't replace).
        """
        merged = dict(per_work_contexts) if per_work_contexts else {}
        if not stop_corpus_data:
            return merged
        for stop_name, sc_data in stop_corpus_data.items():
            if sc_data and sc_data.get('passages'):
                existing = merged.get(stop_name, [])
                # Add stop_corpus passages as sentences (truncated for safety)
                new_sentences = [p[:500] for p in sc_data['passages']]
                merged[stop_name] = existing + new_sentences
        return merged

    # -------- [S11] Storied: generate spine + fact sheets when STORIED_MODE=true --------
    _phase_timer.start('fact_sheets')
    _storied_spine = None
    _storied_fact_sheets = None
    _saved_prolog = ""  # [R2] Prolog text to be folded into Stop 1 (no standalone Introduction block)
    _three_class_results = {}  # [LOCAL-37] poi_name → three-class retrieval result
    _diversity_adjusted_selections = {}  # [LOCAL-37] poi_name → diversity-adjusted element selection
    _stop_corpus_data = {}  # [LOCAL-183] poi_name → {passages, sources} from stop_corpus table
    _corpus_gate_shortened_stops = set()  # [LOCAL-198] Stops flagged for venue-only narration
    _corpus_gate_empty_stops = set()  # [LOCAL-209] Stops with NO corpus at all (stricter than VENUE_ONLY)
    _corpus_gate_creator_only_stops = set()  # [LOCAL-203] Stops with only creator-role passages
    _corpus_gate_log = []  # [LOCAL-198] Per-stop gate decisions
    _thread_result = None  # [LOCAL-186] Initialize before storied block so closure doesn't NameError
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
                        canonical_titles=_story_corpus_result.get('canonical_titles'),
                    )
                    # Persist story elements to file
                    if _story_elements and output_file:
                        _elem_path = output_file.replace('.txt', '_story_elements.json')
                        persist_story_elements(_story_elements, _elem_path)
                    # [LOCAL-21] Update venue_corpus cache with extracted story elements
                    if _story_elements and _d1v2_result and hasattr(_d1v2_result, 'qid') and _d1v2_result.qid:
                        try:
                            from venue_resolver import _get_db_connection
                            _se_conn = _get_db_connection()
                            if _se_conn:
                                with _se_conn.cursor() as _se_cur:
                                    _se_cur.execute(
                                        "UPDATE venue_corpus SET story_elements_json = %s WHERE qid = %s",
                                        (json.dumps(_story_elements), _d1v2_result.qid)
                                    )
                                    _se_conn.commit()
                                    print(f"  [§3] Updated venue_corpus.story_elements_json for {_d1v2_result.qid} ({len(_story_elements)} elements)")
                                _se_conn.close()
                        except Exception as _db_err:
                            print(f"  [§3] DB update non-fatal: {_db_err}")
                except ImportError:
                    _import_logger.error("[§3] MISSING: story_element_extractor (extract_story_elements) — story element extraction DISABLED")
                    print(f"  [§3] story_element_extractor not available")
                except Exception as _se_err:
                    print(f"  [§3] Story element extraction error: {_se_err}")

            # [LOCAL-369] Thread A: For scoped exhibitions, feed the exhibition's own
            # prose into story element extraction. The venue corpus (story_miner) captures
            # the permanent collection; an exhibition has its own framing text that
            # contains the cross-stop themes worth discovering.
            if (_exhibition_scope is not None and _exhibition_checklist_result
                    and getattr(_exhibition_checklist_result, 'page_text', '')):
                try:
                    from story_element_extractor import extract_story_elements_from_pages
                    _exh_page_text = _exhibition_checklist_result.page_text
                    _exh_pages = [{
                        'url': _exhibition_checklist_result.exhibition_url or 'exhibition_page',
                        'text': _exh_page_text,
                        'title': _exhibition_checklist_result.exhibition_title or '',
                    }]
                    _exh_elements = extract_story_elements_from_pages(
                        pages=_exh_pages,
                        venue_name=_venue_name,
                        api_key=api_key,
                        max_pages=1,
                    )
                    if _exh_elements:
                        # Merge exhibition elements into story_elements, deduplicating by text
                        _existing_texts = {e.get('text', '')[:80] for e in _story_elements}
                        _added = 0
                        for _ee in _exh_elements:
                            if _ee.get('text', '')[:80] not in _existing_texts:
                                _story_elements.append(_ee)
                                _existing_texts.add(_ee.get('text', '')[:80])
                                _added += 1
                        print(f"  [LOCAL-369] Exhibition prose → {_added} new story elements "
                              f"(total now {len(_story_elements)})")
                    else:
                        print(f"  [LOCAL-369] Exhibition prose yielded no story elements")
                except ImportError:
                    print(f"  [LOCAL-369] story_element_extractor not available for exhibition prose")
                except Exception as _exh_err:
                    print(f"  [LOCAL-369] Exhibition prose extraction error (non-fatal): {_exh_err}")

            # [LOCAL-37] Three-class retrieval: tag elements + fetch category context
            _three_class_results = {}  # poi_name → retrieval result
            try:
                from three_class_retrieval import (
                    retrieve_three_classes_for_stop, tag_elements_by_class,
                    compute_tour_class_balance, CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL,
                )
                
                # Tag existing story elements by class
                if _story_elements:
                    _story_elements = tag_elements_by_class(_story_elements)
                
                # Retrieve category-level context for each stop (free path only)
                _catalogue_works = (_story_corpus_result.get('catalogue_works', [])
                                    if _story_corpus_result else [])
                _per_work_ctx = (_story_corpus_result.get('per_work_contexts', {})
                                 if _story_corpus_result else {})
                _venue_lang = 'en'
                if _d1v2_result and hasattr(_d1v2_result, 'language'):
                    _venue_lang = _d1v2_result.language or 'en'
                
                for poi in poi_list:
                    _stop_dict = {
                        'name': poi.get('name', ''),
                        'canonical_title': poi.get('name', ''),
                        'artist': artist if 'artist' in dir() else '',
                    }
                    _tcr = retrieve_three_classes_for_stop(
                        _stop_dict,
                        per_work_contexts=_per_work_ctx,
                        catalogue_works=_catalogue_works,
                        language=_venue_lang,
                        tour_category=tour_category,
                        tour_location=location,
                    )
                    _three_class_results[poi.get('name', '')] = _tcr
                    if _tcr.get('category'):
                        print(f"  [LOCAL-37] {poi.get('name', '')[:30]}: category='{_tcr['category']}' "
                              f"has_context={bool(_tcr.get('category_context', {}).get(CLASS_HISTORIC, ''))}")
                    # [LOCAL-47] Log retrieval tier for outdoor stops
                    if tour_category != 'museum' and _tcr.get('retrieval_tier'):
                        _n_facts = len(_tcr.get('retrieval_facts', []))
                        print(f"  [LOCAL-47] {poi.get('name', '')[:30]}: tier={_tcr['retrieval_tier']}, facts={_n_facts}")
                
                print(f"  [LOCAL-37] Three-class retrieval: {len(_three_class_results)} stops processed, "
                      f"{sum(1 for v in _three_class_results.values() if v.get('category'))} with category")
                # [LOCAL-47] Summary for outdoor tours
                if tour_category != 'museum':
                    _tier_counts = {}
                    for _v in _three_class_results.values():
                        _t = _v.get('retrieval_tier', 'empty')
                        _tier_counts[_t] = _tier_counts.get(_t, 0) + 1
                    print(f"  [LOCAL-47] Outdoor retrieval tiers: {_tier_counts}")
            except ImportError as _tcr_err:
                _import_logger.error("[LOCAL-37] MISSING: three_class_retrieval — three-class context DISABLED: %s", _tcr_err)
                print(f"  [LOCAL-37] three_class_retrieval not available: {_tcr_err}")
            except Exception as _tcr_err:
                print(f"  [LOCAL-37] Three-class retrieval error (non-fatal): {_tcr_err}")

            # [SQ-S6b] Theme thread discovery — cross-stop narrative threads
            _thread_result = None
            try:
                from theme_thread_discoverer import discover_theme_threads
                _thread_result = discover_theme_threads(
                    story_elements=_story_elements,
                    poi_names=_poi_names,
                    venue_name=_venue_name,
                    api_key=api_key,
                )
                if _thread_result:
                    print(f"  [SQ-S6b] Thread discovery: mode={_thread_result.mode}, "
                          f"threads={len(_thread_result.threads)}")
                    if _thread_result.threads:
                        for _t in _thread_result.threads:
                            print(f"    → '{_t.name}': coverage={_t.coverage:.0%}, weight={_t.weight:.2f}, "
                                  f"elements={_t.supporting_elements}")
                    if output_file and _thread_result.mode == "threaded":
                        _thread_path = output_file.replace('.txt', '_threads.json')
                        with open(_thread_path, 'w', encoding='utf-8') as _tf:
                            json.dump(_thread_result.to_dict(), _tf, indent=2, ensure_ascii=False)
            except ImportError:
                print(f"  [SQ-S6b] theme_thread_discoverer not available")
            except Exception as _th_err:
                print(f"  [SQ-S6b] Thread discovery error (non-fatal): {_th_err}")

            _storied_spine = generate_spine(
                venue_name=_venue_name,
                poi_list=_poi_names,
                tour_category=tour_category,
                api_key=api_key,
                theme_name="",
                story_elements=_story_elements if _story_elements else None,
                thread_result=_thread_result,
                user_id=user_id,
                job_id=job_id,
            )

            # [LOCAL-278] Fold the spine's cost into the pipeline total. It was
            # metered to the ledger but excluded from this line, so every cost
            # figure reported was ~half the truth (D185). LOCAL-278 could not
            # touch this file while LOCAL-277 held it; this is the one line it
            # said would close the gap.
            try:
                import spine_generator as _sg
                _spine_cost = (_sg.LAST_SPINE_COST or {}).get("cost_usd", 0.0)
                if _spine_cost:
                    total_cost += _spine_cost
                    print(f"  [LOCAL-278] Spine cost folded into total: ${_spine_cost:.4f}")
            except Exception as _e:
                print(f"  [LOCAL-278] Spine cost not folded (non-fatal): {_e}")

            # [LOCAL-111] Spine quality gate — score and retry on low quality.
            # Design: D14 quality instrumentation — scoring failure logs WARNING
            # and delivers the spine as-is. Never blocks a tour because a scorer errored.
            _SPINE_QUALITY_THRESHOLD = 2  # Retry if score <= 1 (2+ criteria failed)
            _SPINE_QUALITY_MAX_RETRIES = 1  # One retry only (cost ceiling headroom)
            if _storied_spine:
                try:
                    from spine_quality_scorer import score_spine as _score_spine
                    _sq_score, _sq_breakdown = _score_spine(_storied_spine, total_stops=len(_poi_names))
                    print(f"  [LOCAL-111] Spine quality: {_sq_score}/4 | {_sq_breakdown}")

                    _sq_retries = 0
                    while _sq_score < _SPINE_QUALITY_THRESHOLD and _sq_retries < _SPINE_QUALITY_MAX_RETRIES:
                        _sq_retries += 1
                        print(f"  [LOCAL-111] Score {_sq_score}/4 < threshold {_SPINE_QUALITY_THRESHOLD} — retry {_sq_retries}/{_SPINE_QUALITY_MAX_RETRIES}")
                        _retry_spine = generate_spine(
                            venue_name=_venue_name,
                            poi_list=_poi_names,
                            tour_category=tour_category,
                            api_key=api_key,
                            theme_name="",
                            story_elements=_story_elements if _story_elements else None,
                            thread_result=_thread_result,
                            user_id=user_id,
                            job_id=job_id,
                        )
                        if _retry_spine:
                            _retry_score, _retry_breakdown = _score_spine(_retry_spine, total_stops=len(_poi_names))
                            print(f"  [LOCAL-111] Retry spine quality: {_retry_score}/4 | {_retry_breakdown}")
                            if _retry_score > _sq_score:
                                _storied_spine = _retry_spine
                                _sq_score = _retry_score
                                _sq_breakdown = _retry_breakdown
                                print(f"  [LOCAL-111] Retry improved score: {_sq_score}/4 (accepted)")
                            else:
                                print(f"  [LOCAL-111] Retry did not improve ({_retry_score} <= {_sq_score}), keeping original")
                        else:
                            print(f"  [LOCAL-111] Retry generation failed — keeping original spine")

                    if _sq_score < _SPINE_QUALITY_THRESHOLD:
                        print(f"  [LOCAL-111] WARNING: Final spine score {_sq_score}/4 still below threshold {_SPINE_QUALITY_THRESHOLD} — delivering anyway")
                except Exception as _sq_err:
                    # D14: quality instrumentation must never block delivery
                    import logging as _sq_logging
                    _sq_logging.getLogger("generate_tour_text").warning(
                        f"[LOCAL-111] Spine quality scoring failed — delivering spine unscored: {_sq_err}"
                    )
                    print(f"  [LOCAL-111] WARNING: Spine scoring failed ({type(_sq_err).__name__}: {_sq_err}) — delivering spine unscored")

            if _storied_spine:
                print(f"  [Storied] Spine generated: {len(_storied_spine.get('arc', []))} arc entries (mode={_storied_spine.get('story_mode', '?')})")
            else:
                print(f"  [Storied] Spine generation failed — descriptions will proceed without spine")

            # [LOCAL-183] Fetch per-stop corpus for generation grounding.
            # This is the wire D31/D54/D57 identified as missing: stop_corpus
            # was only read by the detector, never by the generator.
            # Feature flag: set DISABLE_STOP_CORPUS=1 to suppress (for controlled A/B comparison).
            _stop_corpus_disabled = os.environ.get('DISABLE_STOP_CORPUS', '').strip() == '1'
            if _stop_corpus_disabled:
                print(f"  [LOCAL-183] stop_corpus: DISABLED by DISABLE_STOP_CORPUS=1 env var")
            if not _stop_corpus_disabled:
                try:
                    from stop_corpus_reader import get_stop_corpus_for_tour
                    # Use venue_resolver's connection first; fall back to DATABASE_URL
                    _sc_conn = None
                    try:
                        from venue_resolver import _get_db_connection as _get_sc_conn
                        _sc_conn = _get_sc_conn()
                    except Exception:
                        pass
                    if not _sc_conn:
                        # Fallback: direct connection using DATABASE_URL or defaults
                        try:
                            import psycopg2
                            _sc_db_url = os.environ.get(
                                'DATABASE_URL',
                                'postgresql://admin:password123@localhost:5433/audiotours'
                            )
                            _sc_conn = psycopg2.connect(_sc_db_url, connect_timeout=5)
                        except Exception:
                            pass
                    if _sc_conn:
                        _stop_corpus_data = get_stop_corpus_for_tour(
                            venue_name=_venue_name,
                            stop_names=_poi_names,
                            conn=_sc_conn,
                        )
                        _sc_conn.close()
                        _sc_with_data = sum(1 for v in _stop_corpus_data.values() if v is not None)
                        _sc_total_passages = sum(
                            len(v['passages']) for v in _stop_corpus_data.values() if v is not None
                        )
                        print(f"  [LOCAL-183] stop_corpus: {_sc_with_data}/{len(_poi_names)} stops have per-stop passages ({_sc_total_passages} total passages)")
                    else:
                        print(f"  [LOCAL-183] stop_corpus: DB connection unavailable — skipping")
                except ImportError as _sc_err:
                    _import_logger.error("[LOCAL-183] MISSING: stop_corpus_reader — per-stop corpus DISABLED: %s", _sc_err)
                    print(f"  [LOCAL-183] stop_corpus_reader not available: {_sc_err}")
                except Exception as _sc_err:
                    print(f"  [LOCAL-183] stop_corpus fetch error (non-fatal): {_sc_err}")

            # ──── [LOCAL-198] CORPUS COVERAGE GATE ────────────────────────────────
            # When enabled (DISABLE_CORPUS_GATE != '1'), checks each stop's corpus
            # for actual subject coverage. Stops with only venue-level text get
            # flagged for shortened, venue-grounded narration.
            # [LOCAL-209] Gate now iterates _poi_names unconditionally — a stop
            # absent from _stop_corpus_data is EMPTY, not invisible.
            _corpus_gate_disabled = os.environ.get('DISABLE_CORPUS_GATE', '').strip() == '1'
            
            if not _corpus_gate_disabled:
                try:
                    # LEAD fixup on merge: the canonical module is at the repo
                    # root. `tests/` is not in the tour-generator image, so an
                    # import from there fails in Docker and the gate silently
                    # never runs — the LOCAL-192 defect, two rounds later.
                    from corpus_coverage import (
                        assess_stop_coverage, extract_content_words, _extract_passage_texts
                    )
                    print(f"  [LOCAL-198] Corpus gate: ENABLED — checking stop coverage...")
                    
                    for _poi_name in _poi_names:
                        _sc_data = _stop_corpus_data.get(_poi_name)
                        if _sc_data and _sc_data.get('passages'):
                            _passages_text = _sc_data['passages']
                            # [LOCAL-203] Pass passage_roles for role-aware verdicts
                            _passage_roles = _sc_data.get('passage_roles')
                            _assessment = assess_stop_coverage(
                                _poi_name, _venue_name, _passages_text,
                                passage_roles=_passage_roles
                            )
                        else:
                            # [LOCAL-209] No corpus row at all → EMPTY verdict.
                            # Previously this was unreachable when _stop_corpus_data was empty.
                            _assessment = {'verdict': 'EMPTY', 'content_words': extract_content_words(_poi_name, _venue_name), 'subject_match_words': []}
                        
                        if _assessment['verdict'] == 'COVERED':
                            _corpus_gate_log.append({
                                'stop': _poi_name, 'verdict': 'COVERED', 'action': 'PASSED'
                            })
                            print(f"  [CORPUS-GATE] stop='{_poi_name}' "
                                  f"verdict=COVERED action=PASSED")
                        elif _assessment['verdict'] == 'CREATOR_ONLY':
                            # [LOCAL-203] CREATOR_ONLY: narration may discuss the maker
                            # but must not describe the object itself.
                            _corpus_gate_creator_only_stops.add(_poi_name)
                            _corpus_gate_log.append({
                                'stop': _poi_name, 'verdict': 'CREATOR_ONLY', 'action': 'CREATOR_RESTRICTED'
                            })
                            print(f"  [CORPUS-GATE] stop='{_poi_name}' "
                                  f"verdict=CREATOR_ONLY action=CREATOR_RESTRICTED")
                        elif _assessment['verdict'] == 'EMPTY':
                            # [LOCAL-209] EMPTY: no corpus at all — stricter than VENUE_ONLY.
                            # [LOCAL-408] BUT: if direct snippets exist for this stop, they
                            # provide verified reference material. The corpus gate must NOT
                            # override them — doing so suppresses specifics the user injected.
                            _has_direct_snippets = (
                                _DIRECT_SNIPPETS_PER_STOP
                                and (_DIRECT_SNIPPETS_PER_STOP.get(_poi_name)
                                     or _DIRECT_SNIPPETS_PER_STOP.get(f"__stop_{_poi_names.index(_poi_name)}__", []))
                            )
                            if _has_direct_snippets:
                                # Treat as PASSED — direct snippets ARE the verified material
                                _corpus_gate_log.append({
                                    'stop': _poi_name, 'verdict': 'EMPTY', 'action': 'PASSED_VIA_SNIPPETS'
                                })
                                print(f"  [CORPUS-GATE] stop='{_poi_name}' "
                                      f"verdict=EMPTY action=PASSED_VIA_SNIPPETS (direct snippets override)")
                            else:
                                _corpus_gate_empty_stops.add(_poi_name)
                                _corpus_gate_log.append({
                                    'stop': _poi_name, 'verdict': 'EMPTY', 'action': 'EMPTY_RESTRICTED'
                                })
                                print(f"  [CORPUS-GATE] stop='{_poi_name}' "
                                      f"verdict=EMPTY action=EMPTY_RESTRICTED")
                        else:
                            # VENUE_ONLY — shorten narration
                            _corpus_gate_shortened_stops.add(_poi_name)
                            _action = 'SHORTENED'
                            _corpus_gate_log.append({
                                'stop': _poi_name, 'verdict': _assessment['verdict'], 'action': _action
                            })
                            print(f"  [CORPUS-GATE] stop='{_poi_name}' "
                                  f"verdict={_assessment['verdict']} action={_action}")
                    
                    _passed = sum(1 for g in _corpus_gate_log if g['action'] == 'PASSED')
                    _creator_only = sum(1 for g in _corpus_gate_log if g['action'] == 'CREATOR_RESTRICTED')
                    _empty = sum(1 for g in _corpus_gate_log if g['action'] == 'EMPTY_RESTRICTED')
                    _shortened = sum(1 for g in _corpus_gate_log if g['action'] == 'SHORTENED')
                    print(f"  [LOCAL-198] Corpus gate: {_passed} PASSED, {_creator_only} CREATOR_ONLY, {_empty} EMPTY, {_shortened} SHORTENED")
                except ImportError:
                    print(f"  [LOCAL-198] Corpus gate: module not importable — gate DISABLED")
                except Exception as _gate_err:
                    print(f"  [LOCAL-198] Corpus gate error (non-fatal): {_gate_err}")
            elif _corpus_gate_disabled:
                print(f"  [LOCAL-198] Corpus gate: DISABLED by DISABLE_CORPUS_GATE=1")
            # ──── END [LOCAL-198] CORPUS COVERAGE GATE ────────────────────────────

            _storied_fact_sheets = generate_fact_sheets_parallel(
                poi_list=_poi_names,
                venue_name=_venue_name,
                tour_category=tour_category,
                api_key=api_key,
                # [LOCAL-12 Fix A] Route already-fetched venue corpus into fact-sheet generation
                venue_corpus=_d1_venue_corpus if _d1_venue_corpus else "",
                # [LOCAL-183] Merge stop_corpus passages into per_work_contexts so
                # fact extraction benefits from per-stop sourced material.
                per_work_contexts=_merge_stop_corpus_into_per_work(
                    _story_corpus_result.get('per_work_contexts', {}) if _story_corpus_result else {},
                    _stop_corpus_data,
                ),
            )
            if _storied_fact_sheets:
                _valid_sheets = sum(1 for fs in _storied_fact_sheets if fs is not None)
                print(f"  [Storied] Fact sheets: {_valid_sheets}/{len(_poi_names)} generated")
            else:
                print(f"  [Storied] Fact sheet generation failed — descriptions will proceed without facts")
                _storied_fact_sheets = []
        except ImportError as e:
            _import_logger.error("[Storied] MISSING: spine/fact generation modules (spine_generator, fact_extractor) — spine and fact sheets DISABLED: %s", e)
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
            _import_logger.error("[S25] MISSING: story_type_assigner (assign_story_types) — story type assignment DISABLED: %s", e)
            print(f"  [S25] story_type_assigner not available: {e}")
        except Exception as e:
            print(f"  [S25] Error assigning story types: {e}")

    # -------- [LOCAL-37] Tour-level class diversity (wire apply_tour_diversity) --------
    _diversity_adjusted_selections = {}  # poi_name → {selected_elements, runner_up_elements}
    if _storied_mode and tour_category == 'museum':
        try:
            from story_element_extractor import apply_tour_diversity, select_stop_elements
            from story_selection import select_stories_for_stop, STOP_WORD_BUDGET
            from work_story_searcher import normalize_work_key, work_stories_get
            
            # Pre-compute selections for all stops using quality-sorted packing (LOCAL-438)
            _all_selections = []
            _selection_names = []
            for poi in poi_list:
                poi_name = poi.get('name', '')
                _artist_for_sel = poi.get('artist', '')
                _wk = normalize_work_key(poi_name, _artist_for_sel)
                _cached = work_stories_get(_wk)
                if _cached and _cached.get('elements'):
                    # [LOCAL-438] Route through quality-sorted packing selector
                    _packed = select_stories_for_stop(_cached['elements'], budget=STOP_WORD_BUDGET)
                    # Convert packing result to selection format expected downstream
                    _packed_set = set(id(p) for p in _packed)
                    _runners = [e for e in _cached['elements'] if id(e) not in _packed_set]
                    _sel = {
                        'selected_elements': _packed,
                        'runner_up_elements': _runners[:2],
                    }
                    _all_selections.append(_sel)
                    _selection_names.append(poi_name)
                    if _packed:
                        _packed_words = sum(e.get('_word_count', len(e.get('text', '').split())) for e in _packed)
                        print(f"  [LOCAL-438] Stop '{poi_name[:40]}': packed {len(_packed)} stories, "
                              f"{_packed_words}w / {STOP_WORD_BUDGET}w budget")
                else:
                    _all_selections.append({'selected_elements': [], 'runner_up_elements': []})
                    _selection_names.append(poi_name)
            
            # Apply diversity (modifies in place)
            if _all_selections:
                _all_selections = apply_tour_diversity(_all_selections, max_same_type=2)
                # Store adjusted selections for use in per-stop B6 wiring
                for i, sel in enumerate(_all_selections):
                    _diversity_adjusted_selections[_selection_names[i]] = sel
                
                # Log diversity result
                _swaps = sum(1 for s in _all_selections if s.get('_class_diversity_swap'))
                if _swaps:
                    print(f"  [LOCAL-37] Tour diversity: {_swaps} class-rebalancing swaps applied")
                else:
                    print(f"  [LOCAL-37] Tour diversity: no swaps needed (naturally balanced)")
        except ImportError as e:
            _import_logger.error("[LOCAL-37] MISSING: tour diversity module (apply_tour_diversity) — class diversity balancing DISABLED: %s", e)
            print(f"  [LOCAL-37] Tour diversity import failed: {e}")
        except Exception as e:
            print(f"  [LOCAL-37] Tour diversity error (non-fatal): {e}")

    # [LOCAL-188] Feature flag: set DISABLE_STYLE_CONSTRAINTS=1 to suppress the
    # declarative-prose style rules from the narration prompt (for controlled A/B comparison).
    _style_constraints_disabled = os.environ.get('DISABLE_STYLE_CONSTRAINTS', '').strip() == '1'
    if _style_constraints_disabled:
        print(f"  [LOCAL-188] Style constraints DISABLED by DISABLE_STYLE_CONSTRAINTS=1 env var")
    else:
        print(f"  [LOCAL-188] Style constraints ACTIVE (declarative prose rules injected)")

    # [LOCAL-412] Condensed from ~1400 chars to ~700 chars each. Same rules, fewer examples.
    _STYLE_CONSTRAINT_BLOCK_MUSEUM = """
DECLARATIVE PROSE (LOCAL-188 — enforced by validation):
- NO IMPERATIVES aimed at listener: "Feel the weight", "Notice", "Imagine", "Discover" → BANNED. Write "The weight is visible in..." instead.
- NO QUESTIONS. No question marks. "How does this manifest?" → "This manifests in..."
- NO "as you explore/wander/stroll". State what IS, not what the listener does.
- NO PRESCRIBED FEELINGS: "You feel the solemnity" → BANNED. Describe the object, not the listener.
- NO HALLUCINATED SENSES: "You can almost hear..." → BANNED. Only current sensory facts.
Exempt: navigation directions ("Turn left", "Continue past").
"""

    _STYLE_CONSTRAINT_BLOCK_OUTDOOR = """
DECLARATIVE PROSE (LOCAL-188 — enforced by validation):
- NO IMPERATIVES aimed at listener: "Feel the weight", "Notice", "Imagine", "Discover" → BANNED. Write "The weight is visible in..." instead.
- NO QUESTIONS. No question marks. "How does this manifest?" → "This manifests in..."
- NO "as you explore/wander/stroll". State what IS, not what the listener does.
- NO PRESCRIBED FEELINGS: "You feel the solemnity" → BANNED. Describe the object, not the listener.
- NO HALLUCINATED SENSES: "You can almost hear..." → BANNED. Only current sensory facts.
Exempt: navigation directions ("Turn left", "Continue past").
"""

    # [LOCAL-326] Phase-boundary cost checkpoint: before Phase 5.
    # Saves the expensive per-stop description generation on breach.
    # Cannot raise here (would escape to caller without partial assembly),
    # so return a partial tour directly.
    if total_cost > _PHASE_COST_HARD_LIMIT:
        print(f"[LOCAL-326] COST CEILING BREACHED at pre-Phase5: "
              f"${total_cost:.4f} > ${_PHASE_COST_HARD_LIMIT:.4f} — "
              f"assembling partial tour with {len(poi_list)} stops (no descriptions)")
        _partial_header = (
            f"Step-by-Step Audio Guided Tour: {location}\n"
            f"Tour-Category: {tour_category}\n"
            f"[PARTIAL TOUR — generation stopped before Phase 5 due to cost ceiling "
            f"(${total_cost:.4f} > ${_PHASE_COST_HARD_LIMIT:.4f})]\n\n"
        )
        _partial_body = ""
        for _pi, _pp in enumerate(poi_list):
            _partial_body += f"Stop {_pi + 1}: {_pp.get('name', 'Unknown')}\n"
            if _pp.get('address'):
                _partial_body += f"Address: {_pp['address']}\n"
            if _pp.get('directions'):
                _partial_body += f"Directions: {_pp['directions']}\n"
            _partial_body += "[Description not generated — cost ceiling reached]\n\n"
        _partial_tour = _partial_header + _partial_body
        _LAST_GENERATION_COST = {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "cache_hit": False,
            "breakdown": {"llm": total_cost, "tts": 0.0, "search": 0.0},
        }
        if output_file:
            with open(output_file, "w", encoding="utf-8") as _pf:
                _pf.write(_partial_tour)
        return _partial_tour, output_file, first_poi_coordinates

    # PHASE 5: Generate detailed descriptions for each POI (parallelized)
    _phase_timer.start('narration')
    print(f"\nPHASE 5: Generating detailed descriptions for each POI (parallel)...")

    # -------- [LOCAL-382/LOCAL-387] Exhibition thesis / venue purpose framing detection --------
    # Moved here (from post-assembly) so _framing_case is bound before _generate_description
    # closure captures it. Without this, museum tours crash with NameError.
    _framing_case = 'none'
    _framing_source_phrase = '-'
    _framing_page_text = ''
    if tour_category == 'museum':
        try:
            from exhibition_thesis import detect_framing_case, build_exhibition_thesis_prolog_block, build_exhibition_thesis_stop_block
            _venue_text_for_framing = ''
            if _story_corpus_result and _story_corpus_result.get('combined_text'):
                _venue_text_for_framing = _story_corpus_result['combined_text']
            _framing_case, _framing_source_phrase = detect_framing_case(
                exhibition_checklist_result=_exhibition_checklist_result,
                exhibition_scope=_exhibition_scope,
                venue_combined_text=_venue_text_for_framing,
            )
            if _framing_case == 'exhibition':
                _framing_page_text = getattr(_exhibition_checklist_result, 'page_text', '') or ''
            print(f"\n  [LOCAL-382] framing={_framing_case} source='{_framing_source_phrase[:80]}'")
        except ImportError as _ft_err:
            print(f"  [LOCAL-382] exhibition_thesis module unavailable ({_ft_err}) — framing=none")
        except Exception as _ft_err:
            print(f"  [LOCAL-382] Framing detection error (non-fatal): {_ft_err} — framing=none")

    # -------- [LOCAL-383] Story beat extraction — mine people + actions from page text --------
    _story_beats_per_stop = None
    _all_story_beats = []
    if _storied_mode and tour_category == 'museum':
        try:
            from story_beat_injector import extract_story_beats, assign_beats_to_stops, attribute_beats_to_works
            # Use the framing page text (exhibition case) or combined corpus text
            _beat_source_text = _framing_page_text or ''
            if not _beat_source_text and _story_corpus_result:
                _beat_source_text = _story_corpus_result.get('combined_text', '')
            if _beat_source_text:
                _all_story_beats = extract_story_beats(_beat_source_text)
                if _all_story_beats:
                    _poi_names_for_beats = [p['name'] for p in poi_list]
                    # Get matched works from exhibition checklist if available
                    _matched_works_for_beats = None
                    if hasattr(_exhibition_checklist_result, 'works') and _exhibition_checklist_result:
                        _matched_works_for_beats = getattr(_exhibition_checklist_result, 'works', None)
                    # [LOCAL-392] Attribute beats to their source works BEFORE assignment
                    if _matched_works_for_beats:
                        _all_story_beats = attribute_beats_to_works(
                            _all_story_beats, _matched_works_for_beats)
                    _story_beats_per_stop = assign_beats_to_stops(
                        _all_story_beats, _poi_names_for_beats,
                        matched_works=_matched_works_for_beats,
                        framing_case=_framing_case,
                    )
                    _beat_people = set(b['person'] for b in _all_story_beats if b['role'] not in ('circumstance', 'stakes'))
                    print(f"\n  [LOCAL-383] Extracted {len(_all_story_beats)} story beats, "
                          f"{len(_beat_people)} named people: {', '.join(sorted(_beat_people)[:6])}")
                else:
                    print(f"\n  [LOCAL-383] No story beats found in page text ({len(_beat_source_text)} chars)")
            else:
                print(f"\n  [LOCAL-383] No page text available for story beat extraction")
        except ImportError as _sb_err:
            _import_logger.error(f"[LOCAL-383] MISSING: story_beat_injector — story beats DISABLED: {_sb_err}")
        except Exception as _sb_err:
            print(f"  [LOCAL-383] Story beat extraction error (non-fatal): {_sb_err}")

    # -------- [LOCAL-410] Wire SERP search into generation path --------
    _phase_timer.start('external_lookups')
    # Previously, search_stories_for_stop was only called by acceptance runners
    # which populated _DIRECT_SNIPPETS_PER_STOP before calling generate_tour_text().
    # The real generation path (generate_tour_async) never did this — so search-sourced
    # facts never reached the prompt. This block fixes that gap.
    _local410_chain_log = {}  # stop_name → {queries_issued, serp_results, snippets_injected}
    if (_storied_mode and tour_category == 'museum'
            and not _DIRECT_SNIPPETS_PER_STOP
            and os.environ.get('GENERATION_TIER', 'plus') != 'free'):
        try:
            from work_story_searcher import search_stories_for_stop, synthesize_queries
            from work_story_searcher import set_venue_domain
            # [D495] Register the toured venue's own site so its pages — and its
            # collection subdomain — classify tier1 without a Wikidata lookup.
            # This replaces adding one museum to the hand-maintained seed list:
            # the seed held 13 domains and not the venue we had been generating
            # against for a week, and the next venue would have had the same hole.
            # `_det_entity` is rebound in several branches above, so read it the
            # defensive way rather than assuming it is bound.
            _venue_ent = locals().get('_det_entity')
            _venue_site = getattr(_venue_ent, 'official_url', '') if _venue_ent else ''
            if _venue_site:
                print(f"  [D495] venue domain seeded tier1: {set_venue_domain(_venue_site)}")
            else:
                set_venue_domain('')
                print(f"  [D495] no venue URL resolved — venue-domain seeding inactive "
                      f"for this run (falls back to Wikidata + disk cache)")
            print(f"\n  [LOCAL-410] SERP search wiring — searching for stories on {len(poi_list)} stops...")
            _local410_snippets = {}
            _local410_total_queries = 0
            _local410_total_results = 0
            _worthiness_skipped = 0  # [LOCAL-486] step 2

            for _s_idx, _s_poi in enumerate(poi_list):
                _s_name = _s_poi.get('name', '')
                _s_artist = _s_poi.get('artist', '')
                # [LOCAL-419] Enrich stop data from exhibition checklist for better queries.
                # _new_poi() only carries name/artist — publisher/credit_line/medium are empty.
                # But the checklist works list HAS these fields. Without them, synthesize_queries
                # can't build targeted collaborator queries (stop 1 works because its credit_line
                # has publisher+printer; stops 2+3 get only 4 generic queries).
                _s_publisher = _s_poi.get('publisher', '')
                _s_credit_line = _s_poi.get('credit_line', '')
                _s_medium = _s_poi.get('medium', '')
                _s_english_title = _s_poi.get('english_title', _s_name)
                if (not _s_publisher or not _s_credit_line) and _exhibition_checklist_result and hasattr(_exhibition_checklist_result, 'works'):
                    _s_matched_work = match_work_for_stop(_s_name, _exhibition_checklist_result.works)
                    if _s_matched_work:
                        if not _s_publisher:
                            _s_publisher = _s_matched_work.get('publisher', '')
                        if not _s_credit_line:
                            _s_credit_line = _s_matched_work.get('credit_line', '')
                        if not _s_medium:
                            _s_medium = _s_matched_work.get('medium', '')
                        if not _s_artist:
                            _s_artist = _s_matched_work.get('artist', '')
                        if _s_english_title == _s_name:
                            _s_english_title = _s_matched_work.get('english_title', _s_name) or _s_name
                        print(f"    [LOCAL-419] Enriched stop {_s_idx+1} from checklist: "
                              f"publisher='{_s_publisher[:30]}' credit_line='{_s_credit_line[:50]}' "
                              f"medium='{_s_medium[:40]}'")
                # [LOCAL-491] Persist the enriched matrix back onto the POI.
                # LOCAL-419 enriches publisher/credit_line/medium/artist from the
                # checklist into LOCAL VARIABLES only, so by PHASE 5.17 the POI
                # dict still has the empty fields `_new_poi()` gave it. The first
                # live rotation went straight to the `venue` fact — the weakest
                # one on the list — because publisher, printer and credit_line
                # were all invisible to it. The rotation was working; it was being
                # handed an empty matrix.
                # [D500] "Not specified" IS NOT A VALUE. The prose_llm extractor
                # writes it into publisher, credit_line and medium whenever the
                # exhibition page does not mention them — and it usually does not,
                # because that page is marketing copy, not the object record. On
                # the 08-20 baseline, stop 2 carried it in THREE slots.
                #
                # An unknown field must be EMPTY, not a string that looks like
                # data. Filled-with-a-placeholder is worse than empty in three
                # measured ways: `synthesize_queries` searched for the literal
                # phrase (LOCAL-498, fixed downstream — this is the source it
                # was fixed downstream OF); `_credit_line_carries_a_fact` scored
                # it as a fact because it is 13 characters and the guard is
                # len<12; and the slot count reports 7/9 filled on a stop with
                # 3 informative slots.
                #
                # Filtered HERE, where the checklist values enter, so every
                # consumer below — query synthesis, the worthiness scorer, the
                # story matrix, the focus-fact rotation — sees the same absence.
                from text_fold import is_placeholder as _d500_ph
                _s_publisher = '' if _d500_ph(_s_publisher) else _s_publisher
                _s_credit_line = '' if _d500_ph(_s_credit_line) else _s_credit_line
                _s_medium = '' if _d500_ph(_s_medium) else _s_medium
                _s_artist = '' if _d500_ph(_s_artist) else _s_artist
                # [D506] The three agents the record never carried. `printer`
                # is D500's `builder` role — obtainable from the object record
                # (D501) and never previously handed to query synthesis at all.
                _s_printer = (_s_poi.get('printed_by', '')
                              or _s_poi.get('printer', '') or '')
                if _d500_ph(_s_printer):
                    _s_printer = ''
                _s_collaborator = (_s_poi.get('collaborator', '') or '')
                if _d500_ph(_s_collaborator):
                    _s_collaborator = ''
                # The donor is inside the credit line; `synthesize_queries`
                # extracts it itself, but only if the credit line is present.
                _s_donor = (_s_poi.get('donor', '') or '')
                if _d500_ph(_s_donor):
                    _s_donor = ''

                _d500_dropped = [n for n, v in (('publisher', _s_publisher),
                                                ('credit_line', _s_credit_line),
                                                ('medium', _s_medium),
                                                ('artist', _s_artist)) if not v]
                if _d500_dropped:
                    print(f"    [D500] Stop {_s_idx+1}: placeholder cleared from "
                          f"{_d500_dropped} — unknown, not 'Not specified'")

                for _mk, _mv in (('publisher', _s_publisher),
                                 ('credit_line', _s_credit_line),
                                 ('medium', _s_medium),
                                 ('artist', _s_artist),
                                 ('english_title', _s_english_title)):
                    if _mv and not _s_poi.get(_mk):
                        _s_poi[_mk] = _mv

                # [D506] THE STOP RECORD MUST CARRY THE WHOLE MATRIX.
                #
                # `synthesize_queries` reads eleven fields. This dict supplied
                # eight, and the three it omitted are the ones that make the
                # queries visitor-shaped instead of catalogue-shaped:
                #
                #   exhibition_name — gates the TWO queries that are Michael's own
                #       Step 2 framing, "what story can be told to visitors of
                #       {exhibition} about {work}, {credit_line}" (D366/LOCAL-423).
                #       D426 diagnosed this unreachable on 2026-08-13 and it was
                #       never wired. Those queries have never run in production.
                #   printer / printed_by — D501 can now supply Mourlot from the
                #       object record; without this key the printer queries
                #       ("Mourlot workshop history", "Tériade Mourlot
                #       collaboration") cannot be built.
                #   collaborator — gates the "why collaborated" pair.
                #
                # Measured on Au Soleil du Plafond: the eight-field record yields
                # 4 queries, none naming a person other than the artist; the full
                # matrix yields 15, including the donor's motive and the
                # collaboration's reason.
                _s_stop_data = {
                    'canonical_title': _s_name,
                    'artist': _s_artist,
                    'venue_city': location.split(',')[1].strip() if ',' in location else '',
                    'venue_lang': 'en',
                    'venue_name': _museum_venue_name or location.split(',')[0].strip(),
                    'publisher': _s_publisher,
                    'credit_line': _s_credit_line,
                    'medium': _s_medium,
                    'english_title': _s_english_title,
                    'exhibition_name': _exh_name_resolved,
                    'printer': _s_printer,
                    'printed_by': _s_printer,
                    'collaborator': _s_collaborator,
                    'local_title': _s_poi.get('local_title', ''),
                    'donor': _s_donor,
                }
                # -------- [LOCAL-486] STEP 2: is this stop worth mining? --------
                # Michael's step 2, never previously implemented: "we analyze the
                # tour stops and determine that some of them would benefit from
                # stories". Until now every museum stop was mined at full cost —
                # 3-6 SERP queries plus ranking plus a story pass — including
                # stops with no named agent, no credit-line fact, no specific
                # medium and no specific title, which cannot produce a Fact →
                # Stop → Exhibition chain no matter what the queries return.
                #
                # Asymmetric on purpose: a wrong "yes" wastes cents, a wrong "no"
                # silently loses a story and nothing downstream would show it. A
                # stop is mined on ANY one of four signals; only a stop with zero
                # is skipped. See story_worthiness.py.
                _s_worth = {'worth_mining': True, 'score': -1, 'why': 'not assessed'}
                try:
                    from story_worthiness import assess_stop_worthiness
                    _s_worth = assess_stop_worthiness(_s_stop_data)
                except Exception as _sw_err:
                    print(f"    [LOCAL-486] worthiness check failed, mining anyway "
                          f"(non-fatal): {_sw_err}")
                _s_poi['_worthiness'] = _s_worth
                # Log the decision EVERY time, not only on a skip. The first live
                # run of this check was silent because all three stops were worth
                # mining — correct behaviour, and no evidence whatever that the
                # code had run. The live-artifact gate wants the log line, not the
                # absence of one.
                print(f"    [LOCAL-486] Stop {_s_idx+1} worthiness: "
                      f"score={_s_worth['score']}/4 mine={_s_worth['worth_mining']} "
                      f"— {_s_worth['why'][:90]}")
                if not _s_worth['worth_mining']:
                    print(f"    [LOCAL-486] Stop {_s_idx+1} '{_s_name[:40]}' NOT MINED — "
                          f"{_s_worth['why']}")
                    _local410_snippets[_s_name] = []
                    _local410_snippets[f"__stop_{_s_idx}__"] = []
                    _local410_chain_log[_s_name] = {
                        'queries_issued': 0, 'serp_results': 0, 'snippets_injected': 0,
                        'mining_status': 'skipped_unworthy', 'query_log': [],
                    }
                    _worthiness_skipped += 1
                    continue

                _s_result = search_stories_for_stop(
                    _s_stop_data, tour_type='contained',
                    generation_tier=os.environ.get('GENERATION_TIER', 'plus'),
                )
                _s_raw = _s_result.get('results', [])
                _s_query_log = _s_result.get('query_log', [])
                _s_queries_issued = len(_s_query_log)
                _s_serp_count = len(_s_raw)
                _local410_total_queries += _s_queries_issued
                _local410_total_results += _s_serp_count

                # [LOCAL-412] When cache hits, search returns results=[] but
                # cached_elements contains mined story facts. Convert them to
                # snippet-like dicts so the injection/ranking pipeline can use them.
                _s_cached_elements = _s_result.get('cached_elements', [])
                if not _s_raw and _s_cached_elements:
                    print(f"    [LOCAL-412] Stop {_s_idx+1}: cache hit — "
                          f"converting {len(_s_cached_elements)} cached elements to snippets")
                    for _ce in _s_cached_elements:
                        _ce_text = _ce.get('text', '')
                        _ce_sentence = _ce.get('source_sentence', '')
                        # Prefer source_sentence (grounded), fall back to text (synthesized)
                        _ce_snippet_text = _ce_sentence if _ce_sentence else _ce_text
                        if _ce_snippet_text:
                            _s_raw.append({
                                'title': f"[{_ce.get('type', 'fact')}] {', '.join(_ce.get('people', []))[:60]}",
                                'snippet': _ce_snippet_text[:300],
                                'url': _ce.get('source_url', ''),
                                'domain': _ce.get('source_domain', ''),
                                'tier': 'tier1',  # Cached elements were already T1/T2 vetted
                            })
                    _s_serp_count = len(_s_raw)

                # Build snippet list for this stop
                _s_snippets = []
                for _sr in _s_raw:
                    if _sr.get('title') or _sr.get('snippet'):
                        _s_snippets.append({
                            'title': _sr.get('title', ''),
                            'snippet': _sr.get('snippet', ''),
                            'url': _sr.get('url', ''),
                            'tier': _sr.get('tier', ''),  # [LOCAL-414] Carry tier through to ranker
                            'domain': _sr.get('domain', ''),
                        })

                # [LOCAL-410] Inject credit_line as a leading snippet (source of Fridman etc.)
                _s_credit = _s_poi.get('credit_line', '')
                if not _s_credit and _exhibition_checklist_result and hasattr(_exhibition_checklist_result, 'works'):
                    _s_matched = match_work_for_stop(_s_name, _exhibition_checklist_result.works)
                    if _s_matched:
                        _s_credit = _s_matched.get('credit_line', '')
                        # Also pick up publisher if available
                        _s_publisher = _s_matched.get('publisher', '')
                        if _s_publisher and _s_publisher not in _s_credit:
                            _s_credit = f"Published by {_s_publisher}. {_s_credit}".strip()
                if _s_credit:
                    _credit_snippet = {
                        'title': f"Exhibition Checklist — {_s_name}",
                        'snippet': _s_credit,
                        'url': '',
                    }
                    _s_snippets.insert(0, _credit_snippet)
                    print(f"      [credit_line] {_s_credit[:100]}")

                # -------- [LOCAL-489] STEP 3.4: "if too small, learn more" --------
                # Production could already SEE thin material (corpus_coverage,
                # wired since LOCAL-198) and could not ACT on it — the corpus
                # gate's only response is to restrict what the narration may
                # claim. Restricting is not learning. The stop stays thin and the
                # narration gets blamed for it.
                #
                # ONE round, at most STORY_REPLENISH_QUERIES (3) queries, never
                # re-issuing a query already sent. This is the one step on
                # Michael's list that can spend without bound, so the caps are
                # structural rather than advisory.
                if os.environ.get('DISABLE_STORY_REPLENISH', '').strip() != '1':
                    try:
                        from story_replenish import (needs_replenishment,
                                                     build_followup_queries)
                        from corpus_coverage import assess_stop_coverage
                        _rp_passages = [s.get('snippet', '') for s in _s_snippets
                                        if s.get('snippet')]
                        _rp_cov = assess_stop_coverage(
                            _s_name, _museum_venue_name or '', _rp_passages)
                        _rp = needs_replenishment(_rp_passages, _rp_cov)

                        # [D489 step a] REPORT ONLY — never gates, never spends.
                        # Every instrument above counts material; none asks what
                        # KIND it is. On the 01:15 tour all three stops cleared
                        # the volume test and the story detector still refused
                        # all three. LEAD's claim is that the two verdicts
                        # disagree constantly; that is the shape that was wrong
                        # in D423, so this logs both and decides nothing. The
                        # disagreement rate over real runs is what earns the
                        # re-query loop, or kills the idea.
                        try:
                            from material_kind import summarise_stop
                            print("    " + summarise_stop(
                                _s_name, _rp_passages,
                                volume_verdict=str(_rp.get('verdict', ''))))
                        except Exception as _mk_err:
                            print(f"    [D489] material-kind report unavailable "
                                  f"(non-fatal): {_mk_err}")

                        if _rp['needs_more']:
                            _reason = ('thin' if _rp['thin'] else '') + \
                                      ('+uncovered' if _rp['uncovered'] else '') + \
                                      ('+eventless' if _rp.get('eventless') else '')
                            print(f"    [LOCAL-489] Stop {_s_idx+1} needs more material "
                                  f"({_reason.strip('+')}): {_rp['passage_count']} passages, "
                                  f"{_rp['total_chars']} chars, verdict={_rp['verdict']}")
                            # [D493] MEASURED AT ZERO YIELD — detect, do not spend.
                            #
                            # The 12:10 run, with LOCAL-498's post-round check
                            # finally able to answer the question:
                            #
                            #   stop 1: active -> active,  8342 -> 11565 chars, eventful=0
                            #   stop 2: active -> active,  3420 ->  4599 chars, eventful=0
                            #
                            # Two rounds, +3223 and +1179 characters of genuinely
                            # new material, ZERO eventful sentences. The trigger
                            # picks the right stops (D492: same two every run,
                            # zero variance); the ACTION does nothing, because
                            # more queries of the same shape against the same
                            # auction-catalogue sources return the same prose.
                            #
                            # So the two are separated. `eventless` keeps
                            # diagnosing — that is D489a's whole value and it
                            # costs nothing — and stops buying. thin/uncovered
                            # stops still get their round; that path was never
                            # the one measured at zero.
                            #
                            # Re-enable with STORY_REPLENISH_ON_EVENTLESS=1 once
                            # D492(d) source ranking and (c) event-shaped queries
                            # land, which is what would make the round worth
                            # issuing.
                            _rp_eventless_only = (_rp.get('eventless')
                                                  and not _rp['thin']
                                                  and not _rp['uncovered'])
                            # [D494] DEFAULT FLIPPED TO ON, by Michael, 12:22:
                            #   "I do not care a lot about cost at the moment, I
                            #    care about good stories being produced and their
                            #    generation put in production. The cost we will
                            #    calculate later."
                            #
                            # D493 turned this OFF because two rounds bought 4,400
                            # characters and zero eventful sentences. That was a
                            # COST argument — spend for no yield — and cost is
                            # explicitly not the constraint right now.
                            #
                            # It is also a thin sample: two stops, one exhibition,
                            # two runs. Leaving it on keeps LOCAL-498's post-round
                            # measurement accumulating on every tour, which is the
                            # only way to learn whether the round ever helps on
                            # other venues, and it cannot make a tour worse — a
                            # round that adds nothing usable adds nothing.
                            #
                            # STORY_REPLENISH_ON_EVENTLESS=0 turns it off again.
                            _rp_skip = (_rp_eventless_only and os.environ.get(
                                'STORY_REPLENISH_ON_EVENTLESS', '1').strip() == '0')
                            if _rp_skip:
                                print(f"      [D493] eventless only — diagnosed, not "
                                      f"replenished. The round was measured at zero "
                                      f"yield (D493); set STORY_REPLENISH_ON_EVENTLESS=1 "
                                      f"to issue it anyway.")
                                _s_poi['_replenished'] = {
                                    'queries': 0, 'reason': 'eventless_diagnosed_only',
                                    'chars_before': _rp['total_chars'],
                                    'kind_before': _rp.get('kind'),
                                    'kind_after': _rp.get('kind')}
                            _rp_issued = {q for q in (_s_query_log or []) if isinstance(q, str)}
                            _rp_queries = ([] if _rp_skip else
                                           build_followup_queries(_s_stop_data, _rp_issued))
                            if not _rp_queries and not _rp_skip:
                                print(f"      [LOCAL-489] no targeted follow-up available "
                                      f"— the matrix has no second agent to ask about")
                            for _rq in _rp_queries:
                                try:
                                    from work_story_searcher import _serp_search
                                    _rq_results, _ = _serp_search(_rq)
                                except Exception as _rq_err:
                                    print(f"      [LOCAL-489] follow-up failed: {_rq_err}")
                                    continue
                                _added = 0
                                for _rr in (_rq_results or []):
                                    _rs = _rr.get('snippet') or ''
                                    if _rs:
                                        _s_snippets.append(_rr)
                                        _added += 1
                                _local410_total_queries += 1
                                _local410_total_results += len(_rq_results or [])
                                print(f"      [LOCAL-489] +{_added} from: {_rq[:78]}")
                            # [LOCAL-498] DID THE ROUND WORK? Re-classify after.
                            #
                            # Without this the loop spends its capped budget and
                            # nobody can tell whether it bought a story or more
                            # of the same. The 12:05 run fired correctly on both
                            # eventless stops, added 17 and 24 passages, and the
                            # log could not say whether either stop was still
                            # eventless afterwards — which is the only question
                            # that matters about a replenishment round.
                            #
                            # Reports; never re-fires. One round stays one round.
                            _rp_after_passages = [s.get('snippet', '') for s in _s_snippets
                                                  if s.get('snippet')]
                            _rp_after_kind = 'unknown'
                            try:
                                if _rp_skip:
                                    # Nothing was issued, so there is nothing to
                                    # re-measure. Saying "NO CHANGE" here would
                                    # read as a failed round rather than an
                                    # unissued one — the log must not describe
                                    # spending that did not happen.
                                    raise _SkipPostRoundCheck()
                                from material_kind import classify_material
                                _rp_after = classify_material(_rp_after_passages)
                                _rp_after_kind = _rp_after['kind']
                                _rp_worked = (_rp.get('kind') != _rp_after_kind)
                                print(f"      [LOCAL-498] after replenishment: "
                                      f"kind {_rp.get('kind')} -> {_rp_after_kind}, "
                                      f"{_rp['total_chars']} -> "
                                      f"{sum(len(p) for p in _rp_after_passages)} chars, "
                                      f"eventful={_rp_after['eventful_sentences']} "
                                      f"{'(CHANGED)' if _rp_worked else '(NO CHANGE — the round bought more of the same)'}")
                                if _rp_after.get('best_sentence'):
                                    print(f"         best now: "
                                          f"\"{_rp_after['best_sentence'][:110]}\"")
                            except _SkipPostRoundCheck:
                                pass
                            except Exception as _rpa_err:
                                print(f"      [LOCAL-498] post-round check "
                                      f"unavailable (non-fatal): {_rpa_err}")

                            if _rp_skip:
                                _s_poi.setdefault('_replenished', {})
                            else:
                                _s_poi['_replenished'] = {
                                    'queries': len(_rp_queries),
                                    'reason': _reason.strip('+'),
                                    'chars_before': _rp['total_chars'],
                                    'kind_before': _rp.get('kind'),
                                    'kind_after': _rp_after_kind}
                    except ImportError as _rp_err:
                        print(f"    [LOCAL-489] replenishment unavailable ({_rp_err})")
                    except Exception as _rp_err:
                        print(f"    [LOCAL-489] replenishment failed (non-fatal): {_rp_err}")

                # -------- [LOCAL-488] STEP 4: ask a SECOND model --------
                # Michael's step 4: "we generate query and ask it to multiple
                # entities such as AI OpenAI.API — do we use any other AI? and/or
                # Serp and/or Gemini". Production asked exactly one model.
                # `story_leads.py` implements the fan-out and had zero production
                # callers; the 429 that blocked it on 2026-08-13 is long gone —
                # the account returns HTTP 200 on both live model names.
                #
                # THE PRIZE IS NOT MORE LEADS, IT IS AGREEMENT. Two models
                # independently proposing the same dated event is the strongest
                # grounding signal available, and it is the ONLY one that can
                # catch a misattribution: D482's Hogarth Press is real and really
                # did publish Freud, just not that edition, so no entity-presence
                # check can ever see it. Agreement can.
                #
                # Runs only for stops step 2 judged worth mining, so the second
                # model is never spent on a stop that had nothing to say.
                if os.environ.get('DISABLE_STORY_LEADS', '').strip() != '1':
                    try:
                        from story_leads import (run as _leads_run, available_providers,
                                                 families_agreeing, provider_family)
                        _provs = available_providers()
                        if len({provider_family(_p) for _p in _provs}) < 2:
                            print(f"    [LOCAL-488] providers {_provs} span fewer than "
                                  f"two model families — cross-model agreement needs "
                                  f"two; set GEMINI_API_KEY")
                        else:
                            _lr = _leads_run(
                                subject=_s_artist or _s_name,
                                work=_s_english_title or _s_name,
                                venue=_museum_venue_name or location,
                                providers=_provs,
                                verify_top=int(os.environ.get('STORY_LEADS_VERIFY', '3')),
                            )
                            _confirmed = [c for c in _lr['checked']
                                          if c.get('status') == 'CONFIRMED']
                            # Distinct model FAMILIES, not provider strings:
                            # gemini + gemini_grounded is one model answering
                            # twice, which is not corroboration.
                            _agreed = [l for l in _lr['leads'] if families_agreeing(l) > 1]
                            print(f"    [LOCAL-488] step 4: {len(_provs)} providers, "
                                  f"{len(_lr['leads'])} leads, {len(_agreed)} with "
                                  f"cross-model agreement, {len(_confirmed)} SERP-confirmed")
                            # Confirmed leads go in FIRST — they are dated, checked
                            # and carry citations, which is exactly the material the
                            # story prompt is starved of.
                            for _cl in _confirmed:
                                _s_snippets.insert(0, {
                                    'title': f"Cross-model lead ({'+'.join(_cl.get('providers', []) or ['?'])})",
                                    'snippet': f"{_cl.get('year', '')} {_cl.get('claim', '')}".strip(),
                                    'url': (_cl.get('citations') or [''])[0],
                                })
                            if _confirmed:
                                print(f"      → injected {len(_confirmed)} confirmed "
                                      f"lead(s) ahead of the SERP snippets")
                            _s_poi['_leads_agreement'] = {
                                'providers': _provs, 'leads': len(_lr['leads']),
                                'agreed': len(_agreed), 'confirmed': len(_confirmed)}
                    except ImportError as _ld_err:
                        print(f"    [LOCAL-488] story_leads not importable — "
                              f"step 4 stays single-model ({_ld_err})")
                    except Exception as _ld_err:
                        print(f"    [LOCAL-488] lead fan-out failed (non-fatal): {_ld_err}")

                _local410_snippets[_s_name] = _s_snippets
                _local410_snippets[f"__stop_{_s_idx}__"] = _s_snippets

                _local410_chain_log[_s_name] = {
                    'queries_issued': _s_queries_issued,
                    'serp_results': _s_serp_count,
                    'snippets_injected': len(_s_snippets),
                    'mining_status': _s_result.get('story_mining_status', 'unknown'),
                    'query_log': _s_query_log,
                }
                print(f"    Stop {_s_idx+1} '{_s_name[:50]}': "
                      f"queries={_s_queries_issued} serp_results={_s_serp_count} "
                      f"snippets={len(_s_snippets)}")
                # Print top 2 snippets for traceability
                for _snip in _s_snippets[:2]:
                    print(f"      → {_snip.get('snippet', '')[:120]}")

            # Populate the module-level dict so per-stop injection picks it up
            if _local410_snippets:
                _DIRECT_SNIPPETS_PER_STOP = _local410_snippets
                _total_raw = sum(len(v) for k, v in _local410_snippets.items() if not k.startswith('__'))
                print(f"\n  [LOCAL-410] SERP search complete: {_local410_total_queries} queries, "
                      f"{_local410_total_results} results, "
                      f"{_total_raw} total snippets")
                if _worthiness_skipped:
                    # Report what step 2 saved, in the unit that matters. At the
                    # measured 3-6 queries per stop this is the whole point of
                    # the check, and an unreported saving is one nobody can A/B.
                    print(f"  [LOCAL-486] step 2 skipped {_worthiness_skipped} unworthy "
                          f"stop(s) — roughly {_worthiness_skipped * 4} queries not issued")
                # [LOCAL-411] Report that ranking+capping will be applied at injection time
                from snippet_ranker import SNIPPET_CAP_PER_STOP as _411_cap
                print(f"  [LOCAL-411] Snippet ranking+capping enabled: "
                      f"cap={_411_cap}/stop, {_total_raw} raw → max {_411_cap * len(poi_list)} injected")
            else:
                print(f"\n  [LOCAL-410] SERP search complete but yielded 0 snippets")

            # Chain instrumentation summary
            print(f"\n  [LOCAL-410] CHAIN INSTRUMENTATION:")
            for _cl_name, _cl_data in _local410_chain_log.items():
                print(f"    {_cl_name[:50]}: serp_results={_cl_data['serp_results']} "
                      f"elements_extracted=- beats_injected=- (measured post-generation)")

        except ImportError as _s410_err:
            print(f"  [LOCAL-410] work_story_searcher import failed — SERP search DISABLED: {_s410_err}")
        except Exception as _s410_err:
            print(f"  [LOCAL-410] SERP search error (non-fatal, generation continues without stories): {_s410_err}")
            import traceback
            traceback.print_exc()

    # -------- [LOCAL-440/445] Story-first pipeline: seek + verify + size-adapt --------
    _phase_timer.start('story_first')
    # Michael's 4-step process (D393): for each stop, BEFORE narration, seek stories
    # specifically (not just facts), verify them against sources, adapt size, then
    # hand to the LOCAL-438 packer.
    # LOCAL-445: Runs all stops CONCURRENTLY (thread pool) under a single tour-level
    # budget (STORY_FIRST_TOUR_BUDGET_SECONDS=40s), replacing the serial loop that
    # admitted 150s+ of added wall time.
    _local440_results = {}  # stop_name → pipeline result dict
    _local440_total_cost = 0.0
    _local440_total_elapsed = 0.0
    # [LEAD D400] L440_STORY_FIRST gates the live path OFF by default: the pipeline
    # regressed Palais wall time 336s -> 535s (per-candidate gpt-4o-mini classification)
    # for no gate improvement. LOCAL-443 (full-page fetch + candidate pre-filter) earns
    # the right to flip this on. Acceptance runs set L440_STORY_FIRST=true explicitly.
    _l440_env_enabled = os.environ.get('L440_STORY_FIRST', 'false').lower() == 'true'
    if (_storied_mode and tour_category == 'museum' and _l440_env_enabled
            and os.environ.get('GENERATION_TIER', 'plus') != 'free'):
        try:
            from story_first import story_first_pipeline_batch, is_story_seeking_enabled
            if is_story_seeking_enabled():
                print(f"\n  [LOCAL-445] Story-first pipeline — processing {len(poi_list)} stops (parallel)...")

                # Build stop entries for the batch
                _sf_stop_entries = []
                for _sf_idx, _sf_poi in enumerate(poi_list):
                    _sf_name = _sf_poi.get('name', '')
                    _sf_stop_data = {
                        'canonical_title': _sf_name,
                        'artist': _sf_poi.get('artist', ''),
                        'medium': _sf_poi.get('medium', ''),
                        'credit_line': _sf_poi.get('credit_line', ''),
                        'publisher': _sf_poi.get('publisher', ''),
                        'venue_name': _museum_venue_name or location.split(',')[0].strip(),
                        'exhibition_name': _sf_poi.get('exhibition_name', ''),
                        'venue_city': location.split(',')[1].strip() if ',' in location else '',
                        'venue_lang': 'en',
                        'english_title': _sf_poi.get('english_title', _sf_name),
                    }
                    # Enrich from exhibition checklist
                    if _exhibition_checklist_result and hasattr(_exhibition_checklist_result, 'works'):
                        _sf_matched = match_work_for_stop(_sf_name, _exhibition_checklist_result.works)
                        if _sf_matched:
                            for _sf_field in ('publisher', 'credit_line', 'medium', 'artist'):
                                if not _sf_stop_data.get(_sf_field):
                                    _sf_stop_data[_sf_field] = _sf_matched.get(_sf_field, '')

                    # Gather existing snippets for this stop (from LOCAL-410)
                    _sf_snippets = []
                    if _DIRECT_SNIPPETS_PER_STOP:
                        _sf_snippets = (_DIRECT_SNIPPETS_PER_STOP.get(_sf_name, [])
                                        or _DIRECT_SNIPPETS_PER_STOP.get(f"__stop_{_sf_idx}__", []))

                    _sf_stop_entries.append({
                        'name': _sf_name,
                        'stop_data': _sf_stop_data,
                        'snippets': _sf_snippets,
                        'credit_line': _sf_stop_data.get('credit_line', ''),
                        'existing_search_results': _sf_snippets,
                        '_idx': _sf_idx,  # for snippet injection below
                    })

                # [LOCAL-445] Run all stops concurrently under tour-level budget
                _local440_results = story_first_pipeline_batch(_sf_stop_entries)
                _local440_total_cost = sum(r.get('cost_usd', 0.0)
                                           for r in _local440_results.values())
                _local440_total_elapsed = max(
                    (r.get('elapsed_seconds', 0.0) for r in _local440_results.values()),
                    default=0.0
                )

                # Post-process: merge results into caches (serial, fast)
                for _sf_entry in _sf_stop_entries:
                    _sf_name = _sf_entry['name']
                    _sf_idx = _sf_entry['_idx']
                    _sf_result = _local440_results.get(_sf_name)
                    if not _sf_result:
                        continue

                    _sf_stories = _sf_result.get('stories', [])
                    print(f"    Stop {_sf_idx+1} '{_sf_name[:40]}': "
                          f"verified_stories={len(_sf_stories)} "
                          f"elapsed={_sf_result.get('elapsed_seconds', 0):.1f}s "
                          f"cost=${_sf_result.get('cost_usd', 0):.4f}")

                    # [LOCAL-440] Merge story-first results into cached elements
                    # so the LOCAL-438 packer can include them in selection
                    if _sf_stories:
                        from work_story_searcher import normalize_work_key, work_stories_get
                        _sf_wk = normalize_work_key(_sf_name, _sf_entry['stop_data'].get('artist', ''))
                        _sf_cached = work_stories_get(_sf_wk)
                        if _sf_cached and _sf_cached.get('elements'):
                            _sf_cached['elements'].extend(_sf_stories)
                        else:
                            pass  # Packer integration at S25/line ~8644 picks these up
                        # Also inject into _DIRECT_SNIPPETS_PER_STOP for Phase 5 prompt
                        for _sf_story in _sf_stories:
                            _sf_snippet = {
                                'title': f"[Story-first] {', '.join(_sf_story.get('people', [])[:2])}",
                                'snippet': _sf_story['text'][:300],
                                'url': _sf_story.get('source_domain', ''),
                                'tier': 'tier1',
                                '_story_first': True,
                            }
                            if _sf_name in _DIRECT_SNIPPETS_PER_STOP:
                                _DIRECT_SNIPPETS_PER_STOP[_sf_name].insert(0, _sf_snippet)
                            elif f"__stop_{_sf_idx}__" in _DIRECT_SNIPPETS_PER_STOP:
                                _DIRECT_SNIPPETS_PER_STOP[f"__stop_{_sf_idx}__"].insert(0, _sf_snippet)
                            else:
                                _DIRECT_SNIPPETS_PER_STOP[_sf_name] = [_sf_snippet]

                _verified_total = sum(r.get('verified_count', 0) for r in _local440_results.values())
                print(f"\n  [LOCAL-445] Story-first complete: "
                      f"wall_elapsed={_local440_total_elapsed:.1f}s, "
                      f"total_cost=${_local440_total_cost:.4f}, "
                      f"verified_stories={_verified_total} across {len(poi_list)} stops")
            else:
                print(f"\n  [LOCAL-440] Story-seeking DISABLED — fallback to current behaviour")
        except ImportError as _sf440_err:
            print(f"  [LOCAL-440] story_first import failed — story-first pipeline DISABLED: {_sf440_err}")
        except Exception as _sf440_err:
            print(f"  [LOCAL-440] Story-first pipeline error (non-fatal): {_sf440_err}")
            import traceback
            traceback.print_exc()

    # [LOCAL-26] Helper: detect when GPT echoed back a template placeholder instead of content
    # [LOCAL-295] Refactored: returns a classification tuple instead of bare bool.
    #   ("placeholder", reason)  — true placeholder echo, should retry/reject
    #   ("short_valid", word_count) — real prose that is merely short (thin corpus)
    #   (None, None)              — normal content, no issue
    def _classify_placeholder_leak(text):
        """Classify text as placeholder echo, short-but-valid prose, or normal content.

        Returns:
            ("placeholder", reason_str) — genuine placeholder echo; retry is warranted
            ("short_valid", word_count)  — real prose, just short; keep it, do not retry
            (None, None)                — normal content, no issue
        """
        if not text or not text.strip():
            return ("placeholder", "empty_text")
        stripped = text.strip()
        # Bracketed line matching "[...word description...]"
        if re.search(r'\[.*\bword\b.*\bdescription\b.*\]', stripped, re.IGNORECASE):
            return ("placeholder", "bracketed_word_description_echo")
        # Output wholly enclosed in square brackets (entire text is a placeholder)
        if stripped.startswith('[') and stripped.endswith(']') and '\n' not in stripped:
            return ("placeholder", "wholly_bracketed")
        # [LOCAL-295] Short text: distinguish placeholder from valid short prose.
        # A placeholder is template-like (contains instruction keywords, ellipsis patterns,
        # or is just a POI name echo). Short real prose contains sentences with periods
        # and reads as natural language.
        word_count = len(stripped.split())
        if word_count < 30:
            # Check for signs this IS a placeholder/instruction echo, not real prose
            _lower = stripped.lower()
            _is_placeholder_like = (
                # Contains instruction/template keywords
                re.search(r'\b(insert|placeholder|description here|your .* here|todo|tbd)\b', _lower) or
                # Mostly ellipsis or filler tokens
                stripped.count('...') >= 2 or
                # Echoes back the prompt structure (e.g. "Create a detailed description for...")
                re.search(r'\b(create a|write a|generate a)\s+(detailed|brief)?\s*(description|narration)', _lower) or
                # Just a bare name or title with no sentence structure
                (word_count < 8 and '.' not in stripped)
            )
            if _is_placeholder_like:
                return ("placeholder", f"short_and_template_like ({word_count} words)")
            # It's short but reads as real prose — this is a thin-corpus result, not a leak
            return ("short_valid", word_count)
        return (None, None)

    # [LOCAL-295] Backward-compat wrapper — other code paths that just need bool
    def _detect_placeholder_leak(text):
        """Return True only for genuine placeholder echoes (not short-but-valid prose)."""
        classification, _ = _classify_placeholder_leak(text)
        return classification == "placeholder"

    # [LOCAL-415] LLM refusal detector — catches meta-responses where the model
    # apologises to the listener, references its own constraints, or refuses to
    # produce content. These must NEVER ship as tour text.
    _LLM_REFUSAL_PATTERNS = [
        # Direct refusals
        r'\bI cannot provide\b',
        r'\bI can\'t provide\b',
        r'\bI\'m unable to\b',
        r'\bI am unable to\b',
        r'\bI\'m sorry,?\s+(?:but\s+)?I\b',
        r'\bI apologize\b',
        r'\bI apologise\b',
        # Self-referential meta-commentary
        r'\bas an AI\b',
        r'\bas a language model\b',
        r'\bmy training data\b',
        r'\bmy knowledge cutoff\b',
        r'\bgiven constraints\b',
        r'\bgiven the (?:given |)constraints\b',
        r'\bmissing surnames\b',
        # Model talking to the user about its own process
        r'\bI missed out on\b',
        r'\bI will rectify\b',
        r'\byour patience is appreciated\b',
        r'\bpatience is appreciated\b',
        r'\blet me (?:re)?try\b',
        r'\bI\'ll rectify\b',
        r'\bI need (?:more|additional) (?:information|context|details)\b',
        # Constraint acknowledgment
        r'\bbased on the given constraints\b',
        r'\bcannot (?:fulfill|complete|generate)\b',
        r'\bunable to (?:fulfill|complete|generate)\b',
        # Apologising to the listener (not a character in the tour)
        r'\bI (?:apologize|apologise) for (?:the|any)\b',
        r'\bplease (?:bear with|be patient)\b',
        # [LOCAL-415] Additional patterns found in live testing
        r'\bthere was an issue with your request\b',
        r'\bplease provide the necessary\b',
        r'\bplease provide (?:more|the) (?:details|information|context)\b',
        r'\bI (?:don\'t|do not) have (?:enough|sufficient)\b',
        r'\binsufficient (?:information|data|context)\b',
        # Model addressing user about missing requirements
        r'\bmissing required names?\b',
        r'\bensure to include\b',
        r'\bnotify me if you require\b',
        r'\brequire further assistance\b',
        r'\bif you (?:could|can) provide\b',
        r'\bI (?:cannot|can\'t) (?:proceed|continue)\b',
        r'\bmistake in the (?:initial )?instructions\b',
    ]
    _LLM_REFUSAL_RE = re.compile('|'.join(_LLM_REFUSAL_PATTERNS), re.IGNORECASE)

    def _detect_llm_refusal(text):
        """[LOCAL-415] Detect LLM meta-response / refusal in generated text.

        Returns:
            (True, matched_pattern_text) if refusal detected
            (False, None) if text appears to be genuine content
        """
        if not text or not text.strip():
            return (False, None)
        match = _LLM_REFUSAL_RE.search(text)
        if match:
            return (True, match.group(0))
        return (False, None)

    # [LOCAL-420] Stub detection — references module-level _is_stub_text and _build_material_fallback.

    def _generate_description(args):
        idx, poi, spine_stop, fact_sheet, story_type = args
        stop_num = idx + 1
        poi_name = poi["name"]
        artist = poi["artist"]
        year = poi["year"]

        print(f"\nGenerating description for Stop {stop_num}: {poi_name} by {artist}, {year}...")

        description_prompt = ""
        if tour_category == 'museum':
            # [LOCAL-41] Audio-native prompt: no rhetorical questions, no mid-tour
            # re-introductions, orientation states WHY not just where, varied
            # connective language instead of "broader context" template.
            _stop_context_line = ""
            if stop_num > 1:
                # [LOCAL-41 Fix 3] Listener is already inside. Do NOT re-introduce the venue.
                _stop_context_line = (
                    "\nIMPORTANT: The listener is ALREADY inside this museum and has been "
                    "walking for several stops. Do NOT re-introduce the museum or its city. "
                    "Do NOT say 'As you step into [museum name]' or 'Welcome to'. "
                    "Begin directly with this specific exhibit.\n"
                )
            # [LOCAL-41 Fix 4] Rotate connective framing — never say "broader context" every stop
            description_prompt = f"""Create a detailed audio description for {poi_name} at {location}, focusing on {tour_type}.
{_stop_context_line}
Start with a brief orientation that names "{poi_name}" specifically (not "the exhibit" or "this piece") and tells the listener WHERE to stand or look AND WHY — what becomes visible, legible, or striking from that position that they would miss otherwise.

Then provide a detailed description of the exhibit. Include:
- What the work physically depicts or consists of — what the visitor sees
- One specific technique, material choice, or compositional decision and WHY it matters
- One piece of historical or cultural context that changes how the visitor understands it
- If relevant: how this piece connects to the broader collection or {tour_type}

NAME THE OBJECT, AND SAY WHAT IT COST (D468-D471 — the two rules that moved the score):
- AT LEAST ONE SENTENCE MUST NAME A PHYSICAL PROPERTY OF THE THING IN FRONT OF THE
  LISTENER — its medium, material, technique, edition size, count, binding, colour or
  condition — and tie that property to the story. "A set of ten drypoints and
  lithographs on sheepskin" is the standard; "an important work" is not. The listener
  is standing in front of the object; a story that never mentions it is a caption about
  something else. Take the property from the source material. If the material names
  none, write nothing about the physical object rather than inventing a property.
- SAY WHAT IT COST OR WHAT WAS AT STAKE. What was lost, refused, destroyed, left
  unfinished, done only once, done for the last time, or done despite something. That
  is the difference between a story and a caption. It must come from the source
  material — if there is no such consequence there, write without one rather than
  inventing drama.

EXPLAIN-WHAT-YOU-NAME RULE (critical):
Every concept, motif, symbol, technique, cultural reference, or person you mention
MUST get at least one clause of explanation. If you cannot explain it in a clause, cut it.
- BAD: "the rich cultural heritage of Bengal" (names but explains nothing)
- GOOD: "the Pala dynasty tradition of Bengal, where Buddhist monasteries commissioned
  bronze casting between the 8th and 12th centuries"
- BAD: "delicate floral motifs adorning the crown" (what do they mean?)
- GOOD: "lotus petals on the crown — a symbol of spiritual purity in Hindu iconography,
  also found on temple lintels across Southeast Asia"
- BAD: "Each intricate detail tells a story of creation and rebirth"
  (asserts meaning without delivering it)
- GOOD: "The four arms each hold a specific object: the axe that severs attachment,
  the rope that pulls devotees from illusion, the tusk broken as a writing implement,
  and the sweetmeat representing the reward of a disciplined life"
The stop's own subject (the exhibit itself) needs no gloss — the whole stop explains it.
But a person referenced in passing (e.g. Ulysses Grant) needs one clause: "the American
Civil War general who became president." If most visitors won't know it, explain it or cut it.

NO UNSUPPORTED PRAISE: Do not end paragraphs with evaluative claims ("a truly remarkable
achievement", "a testament to the artist's genius") unless you have just provided the
specific evidence that earns the evaluation. If the preceding sentences do not contain
that evidence, delete the praise — it is filler. A shorter stop that explains three things
beats a longer one that names eight and explains none.

AUDIO RULES (this will be heard, not read):
- NEVER end with a rhetorical question. End on a statement — an image, a fact, or a thought the listener can carry forward.
- NEVER list more than three items in a row. Listeners lose track after three.
- Write for the EAR: short-to-medium sentences, concrete language, no parenthetical asides.

NO PREACHING — NEVER INSTRUCT THE LISTENER (critical):
- NEVER end by telling the listener to consider, reflect, imagine, or feel something.
  End on a FACT or OBSERVATION. The listener is an adult — no commands, no "Take a moment to..."
{_STYLE_CONSTRAINT_BLOCK_MUSEUM if not _style_constraints_disabled else ""}
NO CONDESCENSION / NO DESCRIBING THE OBVIOUS:
- Never "To truly appreciate..." or "It is worth noting..." — just state the thing.
- The listener is in front of the object. Describe what they'd MISS, not what's obvious.
"""
        else:
            _mode_context = f" (traveling by {transport_mode})" if transport_mode != 'on_foot' else ""
            
            # [LOCAL-72] Adaptive word target based on retrieval tier
            _outdoor_tcr = _three_class_results.get(poi_name) if _three_class_results else None
            _outdoor_tier = _outdoor_tcr.get('retrieval_tier', 'empty') if _outdoor_tcr else 'empty'
            _outdoor_facts = _outdoor_tcr.get('retrieval_facts', []) if _outdoor_tcr else []
            
            # [LOCAL-72] No hard word cap. Rich/medium stops get facts injected (below),
            # but we don't constrain the LLM's natural length. The baseline produced
            # 300-500 words per stop; constraining that thins content.
            
            description_prompt = f"""Create a detailed description for the stop "{poi_name}" on a {tour_category} tour{_mode_context} of {location}.

Start with an orientation section that explains how the visitor arrives at this stop and what they should look for.

Then provide a detailed description. Include:
- The specific evidence for why this place matters — a fact, a number, a named person, not adjectives
- Historical or cultural context: name a date, a person, an event, a cause-and-effect
- Ground the listener in the physical present — weave in a real sound, texture, or smell they can perceive right now at this spot
- How this stop connects to the tour's theme — show the connection, don't just assert it

EXPLAIN-WHAT-YOU-NAME RULE (critical):
Every concept, motif, symbol, person, or cultural reference you mention MUST get at least
one clause of explanation. If you cannot explain it in a clause, cut the reference.
- BAD: "the vibrant world of this ancient masterpiece" (vibrant how? which world?)
- GOOD: "the gilt lacquer catches overhead light differently depending on your angle —
  the craftsman applied seven layers, sanding each to translucence before the next"
- BAD: "a person of great historical significance" (say WHO and WHY)
- GOOD: "Commodore Perry, whose 1853 arrival with four warships forced Japan to open
  its ports after two centuries of isolation"
The stop's own subject needs no gloss. But anything mentioned in passing that most
visitors won't know MUST get one explanatory clause or be cut entirely.

NO UNSUPPORTED PRAISE: Do not end paragraphs with evaluative claims unless the preceding
sentences contain the specific evidence that earns them. Delete praise that isn't earned
by evidence immediately before it.

Do NOT use museum/gallery framing (no "exhibit", no "viewing platform", no "artwork" unless it genuinely is one).
Do NOT use academic narration words: never write "thesis", "framing", or "premise" in your output.
Do NOT invent specific named people or attribute quotes unless they are well-documented public figures associated with this location.

AUDIO RULES (this will be heard, not read):
- NEVER end with a rhetorical question. End on a statement — an image, a fact, or a thought the listener can carry forward.
- NEVER list more than three items in a row. Listeners lose track after three.
- Write for the EAR: short-to-medium sentences, concrete language, no parenthetical asides.

NO PREACHING — NEVER INSTRUCT THE LISTENER (critical):
- NEVER end a stop by telling the listener what to feel, notice, consider, reflect on,
  or carry away. End on a FACT or an OBSERVATION, not an instruction.
- BANNED CLOSINGS: "Consider what other..." / "Let the whispers guide..."
  "Take a moment to..." / "Allow yourself to..." / "Reflect on..." / "Ponder..."
  "Imagine..." / "Let this be a reminder..." / "Carry this with you as..."
- The listener is an adult. Do NOT tell them what they "should" feel or do.
- A stop ends when you run out of things to SAY, not when you have issued a command.
{_STYLE_CONSTRAINT_BLOCK_OUTDOOR if not _style_constraints_disabled else ""}
NO CONDESCENSION:
- NEVER write "To truly appreciate/understand [X], one must..." — just state the context.
- NEVER write "It is worth noting that..." or "It is important to understand that..."
"""
            # [LOCAL-186] Venue disambiguation — prevent entity conflation (D62).
            # When a stop name is ambiguous (e.g., "Musée Picasso" exists in Paris AND
            # Antibes), tell the model WHICH entity this stop refers to by using the
            # tour location and stop address as disambiguators.
            _disambig_city = ""
            if poi.get('address'):
                # Extract city from address (typically "..., City, Country" or "City, Postcode")
                _addr_parts = [p.strip() for p in poi['address'].split(',')]
                if len(_addr_parts) >= 2:
                    _disambig_city = _addr_parts[-2] if len(_addr_parts) >= 3 else _addr_parts[0]
            if not _disambig_city:
                # Extract city from tour location
                from three_class_retrieval import _extract_city_hints_from_tour_location
                _city_hints = _extract_city_hints_from_tour_location(location)
                if _city_hints:
                    _disambig_city = _city_hints[0]
            if _disambig_city:
                description_prompt += f"""
VENUE DISAMBIGUATION (D62 — critical, prevents entity conflation):
This stop is "{poi_name}" located in/near {_disambig_city} on this tour of {location}.
If multiple places share this name (e.g., museums in different cities), you are describing
ONLY the one in {_disambig_city}. Do NOT use facts about a same-named institution in another
city. If you are uncertain which facts apply to THIS specific location, omit them rather
than risk conflation.
"""

            # [LOCAL-47] Inject retrieved facts for outdoor stops
            if _outdoor_facts:
                _facts_block = "\n".join(f"  - {f}" for f in _outdoor_facts[:5])
                description_prompt += f"""
RETRIEVED FACTS (incorporate these checkable facts into your description — they are confirmed from sources):
{_facts_block}

SUBSTANCE RULE: Your description MUST include at least 2 of the facts above. Each fact you use
must appear as a specific, checkable claim (with a date, a name, or a number). Do NOT
paraphrase them into vague atmosphere. If you cannot find a way to include them naturally,
state them directly.

GROUNDING RULE (D50/D62 — critical): For specific historical claims (founding year, collection
size, building name, architect, named events), use ONLY the retrieved facts above. Do NOT
supplement with facts from your training data that are not in these passages — such facts may
apply to a same-named entity in a different city. If the passages do not mention a founding
year, collection size, or building name, do NOT supply one from memory.
"""
            # [LOCAL-72] 80-word cap REMOVED — it stripped facts in practice.
            # When retrieval is empty, we still allow full-length descriptions.
            # The model can use its own knowledge; the substance rule only applies
            # when we have retrieved facts to inject.
            # [LOCAL-47] Inject category-level context for outdoor stops
            if _outdoor_tcr and _outdoor_tcr.get('category_context', {}).get('historic'):
                _hist_ctx = _outdoor_tcr['category_context']['historic'][:500]
                description_prompt += f"""
HISTORICAL CONTEXT (from verified sources about this area — use specific facts from this, not vague atmosphere):
{_hist_ctx}
"""

        # [LOCAL-6 Fix 1] Varied sentence openings — cycle through styles by stop index
        # so consecutive stops in the same tour open with genuinely different structure.
        # [LOCAL-41] Removed "direct question" opener — rhetorical questions are confusing
        # in audio (the listener cannot answer; narration just stops). All openers must be
        # statements or scene-setting, never questions.
        _OPENING_STYLES = [
            "Open with a vivid sensory detail — a sound, smell, texture, or visual that immediately places the listener at this location.",
            "Open with a specific historical fact or date that anchors the listener in time before describing the present.",
            "Open by addressing the listener directly in a scene-setting moment — 'As you stand here...' or 'Look up and notice...'",
            "Open with a brief, surprising contrast — what this place once was versus what it is now, or how it differs from its surroundings.",
            "Open with a local anecdote or piece of folklore connected to this spot — a story a resident might tell.",
            "Open with the broader significance of this place in a single declarative sentence before zooming into detail.",
            "Open with a physical detail of the object itself — its scale, its material, a visible mark of age or craftsmanship that rewards close looking.",
        ]
        _opening_style = _OPENING_STYLES[idx % len(_OPENING_STYLES)]
        description_prompt += f"""
OPENING STYLE (mandatory for this stop): {_opening_style}
This instruction overrides any default opening pattern — do NOT open with a generic introduction or the same structure as other stops.
BANNED OPENERS (never use these, regardless of which style is assigned above):
- "Nestled in..." / "Nestled among..." / "Nestled between..."
- "In the heart of..." / "At the heart of..."
- "Located in..." / "Situated in..." / "Tucked away in..."
- Any variation that opens with a generic locative clause placing the stop geographically before saying anything interesting about it.
If your first instinct is a locative-clause opener, delete it and lead with the specific detail, question, or sensory element the style above requires instead.
"""

        # [LOCAL-6 Fix 4] Per-category personality/tone — distinct product feel per tour type
        _CATEGORY_TONE = {
            'museum': "Contemplative and precise — linger on details, share what you've noticed after hours in this room. "
                      "Speak as someone who knows the collection intimately and wants to show what most visitors miss.",
            'restaurant': "Warm, sensory, and convivial — evoke tastes, aromas, textures, the buzz of a busy kitchen. "
                          "Speak as a food-loving local who knows the story behind the menu.",
            'walking': "Historical-narrative and grounded — anchor each place in its real history and layers of time. "
                       "Speak as a knowledgeable neighbor walking alongside the listener through familiar streets.",
            'movie': "Cinematic and evocative — draw parallels between the real place and its on-screen life. "
                     "Speak as someone who sees the film/show layered onto the physical location.",
            'book': "Literary and reflective — connect place to prose, atmosphere to narrative. "
                    "Speak as a reader who has stood where the characters stood and felt the world come alive.",
        }
        _cat_tone = _CATEGORY_TONE.get(tour_category, '')
        if _cat_tone:
            description_prompt += f"""
CATEGORY VOICE: {_cat_tone}
This tone should permeate the entire description — not as a single inserted sentence, but as the underlying sensibility.
"""

        # [PALAIS-FIX B1] Hedged narration for unverified stops — moved EARLY for GPT attention
        # [LOCAL-6 Fix 3] Reframed as narrative aside instead of flat institutional disclaimer
        if not poi.get('verified', True):
            description_prompt += """
NARRATIVE HONESTY — UNVERIFIED WORK: This artwork's presence at this venue has NOT been
independently confirmed. Frame this uncertainty as part of the story — not as a bureaucratic
disclaimer, but as an intriguing layer of the narrative. Use phrasing like:
"The story goes that this piece...", "If the records are right, what you're looking at is...",
"There's a fascinating claim that this work..., though its exact provenance here remains a
matter of debate among scholars."
The uncertainty itself is interesting — present it that way. NEVER state the work's presence
as certain fact, but also avoid robotically repeating "believed to be" or "reportedly" — vary
your uncertainty markers and weave them into the storytelling naturally.
"""

        # [HEDGE-NM] Hedging safety net for non-museum categories (movie/book/walking/restaurant/etc.)
        # [A5] Walking tours (Phase 3) have real per-stop verification via area_resolver's
        # verify_landmarks() — a verified=True landmark should read as confidently as a
        # verified museum work, not get the blanket "no fact-checking performed" framing.
        # Other non-museum categories (restaurant/movie/book/etc.) never set 'verified' at
        # all, so they're untouched here and keep the unconditional safety net they've
        # always had — poi.get('verified', True) would silently exempt them otherwise.
        _hedge_nm_applies = tour_category != 'museum' and (
            tour_category != 'walking' or not poi.get('verified', True)
        )
        if _hedge_nm_applies:
            description_prompt += """
NARRATIVE HONESTY — UNVERIFIED CLAIMS: No independent fact-checking has been performed on
specific claims about people, events, or history for this stop. When you include a specific
claim (a named person, a particular event, a date), frame uncertainty as part of the narrative
rather than as a flat disclaimer:
Instead of "reportedly" or "believed to be" (which sound clinical), use storytelling framing:
"The story passed down through the neighborhood is that...",
"Local tradition holds that..., though the details have shifted in each retelling",
"One account — perhaps embellished over the years — describes...",
"If you ask a local, they'll tell you that...".
The uncertainty itself adds texture — present it as an intriguing element, not a legal caveat.
General, well-known facts (a neighborhood's founding era, a cuisine's regional origin) can be
stated plainly. The narrative-honesty requirement applies specifically to particular people or
events tied to this specific stop. Do NOT invent specific names, dates, or incidents.
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
                        _import_logger.error("[S24] MISSING: derepetition_guard (FORBIDDEN_PHRASES) — global phrase filtering DISABLED for stop descriptions")
                        _global_phrases = []
                    _all_forbidden = _type_forbidden + _global_phrases
                    # [LOCAL-412] Cap at 15 phrases to keep prompt under 20K.
                    # The full 50+ regex list was 2114 chars — the model doesn't
                    # parse regex anyway. Keep only the most common offenders.
                    if _all_forbidden:
                        _all_forbidden = _all_forbidden[:15]
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

        # [SQ-S6b] Thread context injection — cross-stop narrative threads
        if _thread_result and _thread_result.mode == "threaded" and _thread_result.per_stop_thread_context:
            _stop_thread_ctx = _thread_result.per_stop_thread_context[idx] if idx < len(_thread_result.per_stop_thread_context) else None
            if _stop_thread_ctx and _stop_thread_ctx.get("threads_active"):
                _thread_block = "\nTHEME THREAD CONTEXT (weave these cross-stop connections into your narrative):\n"
                for _ta in _stop_thread_ctx["threads_active"]:
                    _thread_block += f"- Thread \"{_ta['name']}\" (weight {_ta['weight']:.0%}): {'; '.join(_ta['element_summaries'][:2])}\n"
                # Callbacks: specific cross-stop references
                if _stop_thread_ctx.get("callbacks"):
                    _thread_block += "CROSS-STOP CALLBACKS (reference these specific items from earlier stops BY NAME):\n"
                    for _cb in _stop_thread_ctx["callbacks"][:2]:
                        _from_name = poi_list[_cb['from_stop']]['name'] if _cb['from_stop'] < len(poi_list) else f"Stop {_cb['from_stop']+1}"
                        _thread_block += f"  - From {_from_name}: {_cb['element_text'][:100]}\n"
                description_prompt += _thread_block

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
        # [C5-1] [LOCAL-29 Fix A] [LOCAL-31 Fix] Inject BOUNDED per-work catalogue metadata.
        # LOCAL-29 fixed the extraction boundaries. LOCAL-31 fixes the injection to be
        # structurally binding: period and material are injected as HARD constraints that
        # GPT must include verbatim, not as soft "GROUNDED FACTS" that it can ignore.
        # Also: origin/provenance is now injected with explicit framing rules to prevent
        # the model from asserting unsourced cultural identity.
        _c51_period = None
        _c51_material = None
        _c51_origin = None
        if tour_category == 'museum' and poi_name:
            _c51_grounded = []
            # Source 1: evidence_log catalogue metadata (period, material, origin) — per-work
            if poi_name in _d1_evidence_log:
                _ev = _d1_evidence_log[poi_name]
                if isinstance(_ev, dict) and _ev.get('method') == 'catalogue_work':
                    if _ev.get('period'):
                        _c51_period = _ev['period']
                    if _ev.get('material'):
                        _c51_material = _ev['material']
                    if _ev.get('origin'):
                        _c51_origin = _ev['origin']
            # Source 2: per_work_contexts (bounded by catalogue section boundaries)
            if _story_corpus_result and _story_corpus_result.get('per_work_contexts'):
                _pwc = _story_corpus_result['per_work_contexts']
                from story_miner import _normalize as _c51_norm
                _poi_norm = _c51_norm(poi_name)
                for _title, _sents in _pwc.items():
                    _title_norm = _c51_norm(_title)
                    if (_poi_norm[:10] in _title_norm or _title_norm[:10] in _poi_norm
                            or _poi_norm == _title_norm):
                        _c51_grounded.extend(s[:200] for s in _sents[:3])
                        break

            # [LOCAL-31] [LOCAL-98] Build the hard-binding injection block.
            # Period and material are MANDATORY VERBATIM inclusions.
            # Origin is framed as catalogued geographic attribution, not cultural identity.
            # LOCAL-98: The binding block is NO LONGER injected here in the middle of the prompt.
            # It is instead appended as the FINAL instruction (after format/length) so it benefits
            # from recency bias in GPT-3.5-turbo. The block is built here, stored in _binding_block,
            # and appended later (search for "LOCAL-98 FINAL BINDING").
            _binding_block = ""
            if _c51_period or _c51_material or _c51_origin or _c51_grounded:
                _binding_block = "\n"
                if _c51_origin:
                    _binding_block += f"CATALOGUED REGION: {_c51_origin}\n"
                    _binding_block += (
                        f'  → The museum catalogues this as originating from the {_c51_origin} region. '
                        f'You may mention this geographic origin IF you frame it as the catalogue\'s attribution '
                        f'(e.g., "catalogued as originating from {_c51_origin}"). '
                        f'Do NOT assert cultural identity (no "Bengali artwork", no "Bengali culture") — '
                        f'state only what the catalogue states. If you are uncertain, omit provenance entirely.\n'
                    )
                if _c51_grounded:
                    _binding_block += "ADDITIONAL CONTEXT:\n" + '. '.join(_c51_grounded) + "\n"
                # [LOCAL-98] Inject origin/context as informational (not binding);
                # the date/material FINAL BINDING goes at the end of the prompt.
                if _binding_block.strip():
                    description_prompt += _binding_block
        
        # [LOCAL-369] Thread B: Inject credit_line as a grounded provenance fact.
        # The credit line is a published, museum-asserted datum from the exhibition checklist.
        # The narrator may use it as a factual statement (e.g., "Gift of Boris Fridman")
        # but MUST NOT infer motive, wealth, or financial condition from the donation.
        _credit_line_for_stop = ''
        _matched_work = None
        if (tour_category == 'museum' and poi_name
                and _exhibition_checklist_result
                and getattr(_exhibition_checklist_result, 'works', None)):
            _matched_work = match_work_for_stop(
                poi_name, _exhibition_checklist_result.works)
            if _matched_work:
                _credit_line_for_stop = (_matched_work.get('credit_line') or '').strip()
        description_prompt += build_provenance_block(_credit_line_for_stop)

        # [LOCAL-379/381] WORK IDENTITY BLOCK: Inject artist, date, medium, publisher
        # whenever ANY field is available — not only when medium is non-empty.
        # This fixes Defect 1 (block suppressed for thin/empty medium) and
        # Defect 2 (correct artist never named in prose).
        # [LOCAL-380/381] When medium is empty, attempt recovery from page prose.
        # Also extract collaborator from page prose when available.
        _matched_medium = ''
        if _matched_work:
            if not (_matched_work.get('medium') or '').strip():
                # [LOCAL-380] Attempt medium recovery from exhibition page prose
                _page_text_for_recovery = getattr(_exhibition_checklist_result, 'page_text', '') or ''
                _recovered_medium = recover_medium_from_page_text(
                    _matched_work.get('title', ''), _page_text_for_recovery)
                if _recovered_medium:
                    _matched_work['medium'] = _recovered_medium
                    print(f"  [LOCAL-380] Recovered medium from page prose: '{_recovered_medium}'")
            # [LOCAL-380] Extract collaborator from page prose
            if not (_matched_work.get('collaborator') or '').strip():
                _page_text_for_collab = getattr(_exhibition_checklist_result, 'page_text', '') or ''
                _recovered_collab = extract_collaborator_from_page_text(
                    _matched_work.get('title', ''),
                    _matched_work.get('artist', ''),
                    _page_text_for_collab)
                if _recovered_collab:
                    _matched_work['collaborator'] = _recovered_collab
                    print(f"  [LOCAL-380] Recovered collaborator from page prose: '{_recovered_collab}'")
            if (_matched_work.get('medium') or '').strip():
                _matched_medium = _matched_work['medium'].strip()
        _work_identity_block = build_work_identity_block(_matched_work)
        _provenance_block_chars = len(_work_identity_block)
        print(f"  [LOCAL-381] stop='{poi_name}' matched_work={_matched_work is not None} "
              f"medium='{_matched_medium}' work_identity_chars={_provenance_block_chars}")
        description_prompt += _work_identity_block

        # [LOCAL-382] Exhibition thesis / venue purpose framing per stop
        if _framing_case != 'none' and tour_category == 'museum':
            try:
                _thesis_stop_block = build_exhibition_thesis_stop_block(
                    framing_case=_framing_case,
                    page_text=_framing_page_text,
                    matched_work=_matched_work,
                )
                if _thesis_stop_block:
                    description_prompt += _thesis_stop_block
            except Exception as _ts_err:
                print(f"  [LOCAL-382] Thesis stop injection error (non-fatal): {_ts_err}")

        # [LOCAL-383] Story beat injection — per-stop people + actions
        if _storied_mode and _story_beats_per_stop and idx < len(_story_beats_per_stop):
            try:
                from story_beat_injector import build_story_beat_prompt_block
                _stop_beats = _story_beats_per_stop[idx]
                _beat_block = build_story_beat_prompt_block(
                    _stop_beats, framing_case=_framing_case,
                )
                if _beat_block:
                    description_prompt += _beat_block
                    _beat_people_this_stop = [b['person'] for b in _stop_beats if b['role'] not in ('circumstance', 'stakes')]
                    if _beat_people_this_stop:
                        print(f"  [LOCAL-383] Stop {stop_num} beats: {', '.join(_beat_people_this_stop[:3])}")
            except ImportError:
                pass  # Already logged at extraction time
            except Exception as _sb_stop_err:
                print(f"  [LOCAL-383] Story beat injection error stop {stop_num} (non-fatal): {_sb_stop_err}")

        # [§4] Story element injection — per-work facts from story_elements
        # [LOCAL-29] Tightened matching: use [:10] prefix AND require >= 60% word overlap
        # to prevent cross-contamination between adjacent entries with similar short prefixes.
        if tour_category == 'museum' and _story_corpus_result and poi_name:
            _per_work_ctx = _story_corpus_result.get('per_work_contexts', {})
            # Find matching work contexts
            _work_facts = []
            for _title, _sents in _per_work_ctx.items():
                from story_miner import _normalize
                _norm_poi = _normalize(poi_name)
                _norm_title = _normalize(_title)
                # Strict match: exact OR 10-char prefix contained OR >= 60% word overlap
                _is_match = (
                    _norm_poi == _norm_title or
                    (_norm_poi[:10] in _norm_title and _norm_title[:10] in _norm_poi) or
                    (len(_norm_poi) > 10 and _norm_poi[:10] in _norm_title)
                )
                if not _is_match:
                    # Word overlap check as fallback
                    _poi_words = set(w for w in _norm_poi.split() if len(w) >= 4)
                    _title_words = set(w for w in _norm_title.split() if len(w) >= 4)
                    if _poi_words and _title_words:
                        _overlap = len(_poi_words & _title_words)
                        _is_match = _overlap >= max(1, len(_poi_words) * 0.6)
                if _is_match:
                    _work_facts.extend(_sents[:3])
                    break  # [LOCAL-29] Stop after first match — no accumulation from multiple entries
            # Also use evidence snippet from D1
            if poi_name in _d1_evidence_log:
                _ev = _d1_evidence_log[poi_name]
                if isinstance(_ev, dict) and _ev.get('snippet'):
                    _work_facts.append(_ev['snippet'])
            if _work_facts:
                _facts_text = '. '.join(f[:200] for f in _work_facts[:4])
                # [LOCAL-322] Replace known French material terms with English in the
                # injected context, so the LLM doesn't echo them into English prose.
                # This is the same map used for FINAL BINDING translation.
                _fr_en_context_map = {
                    'xylogravure polychrome': 'polychrome woodblock print',
                    'xylogravure': 'woodblock print',
                    'xylographie': 'woodcut',
                    'bois laqué': 'lacquered wood',
                    'cuir laqué': 'lacquered leather',
                    'soie brodée': 'embroidered silk',
                    'terre cuite': 'terracotta',
                    "feuille d'or": 'gold leaf',
                    'schiste gris': 'grey schist',
                    'schiste': 'schist',
                    'acier': 'steel',
                    'cuivre': 'copper',
                    'cuir': 'leather',
                    'soie': 'silk',
                    'laque': 'lacquer',
                    'bois': 'wood',
                    'marbre': 'marble',
                    'porcelaine': 'porcelain',
                    'céramique': 'ceramic',
                    'ivoire': 'ivory',
                    'laiton': 'brass',
                    'grès': 'stoneware',
                    'fer': 'iron',
                    'argent': 'silver',
                    'papier': 'paper',
                    'encre': 'ink',
                    'huile': 'oil',
                    'dorure': 'gilding',
                }
                # Replace longest matches first to avoid partial substitution
                for _fr_ctx, _en_ctx in sorted(_fr_en_context_map.items(), key=lambda x: -len(x[0])):
                    if _fr_ctx in _facts_text.lower():
                        import re as _re322ctx
                        _facts_text = _re322ctx.sub(
                            r'\b' + _re322ctx.escape(_fr_ctx) + r'\b',
                            _en_ctx,
                            _facts_text,
                            flags=_re322ctx.IGNORECASE
                        )
                description_prompt += f"\nDOCUMENTED FACTS FOR THIS WORK (incorporate at least one):\n{_facts_text}\n"

        # [LOCAL-402/403] Direct snippet injection — bypasses the extract/score pipeline.
        # When _DIRECT_SNIPPETS_PER_STOP has material for this stop, inject raw
        # search snippets as reference material with grounded-story instructions.
        # [LOCAL-403] Lookup by name first, then by index (handles title string mismatches
        # between the runner's canonical_title and the generation pipeline's poi_name).
        _local402_snippets_injected = False
        _candidate_specifics = []  # [LOCAL-407] initialized here for both-sides logging scope
        _all_snippet_text = ''  # [LOCAL-417] initialized here so required-names gate can check it
        _417_suppressed_beat_names = set()  # [LOCAL-417] names suppressed from required-names (no snippet evidence)
        _prompt_size_before_snippets = len(description_prompt)  # [LOCAL-411] track pre-snippet size
        if _DIRECT_SNIPPETS_PER_STOP and poi_name:
            _stop_snippets = _DIRECT_SNIPPETS_PER_STOP.get(poi_name, [])
            # [LOCAL-403] Fallback: try index-based lookup (key = "__stop_N__")
            if not _stop_snippets:
                _stop_snippets = _DIRECT_SNIPPETS_PER_STOP.get(f"__stop_{idx}__", [])
            # [LOCAL-403] Fallback: normalized fuzzy match on keys
            if not _stop_snippets:
                from story_miner import _normalize
                _norm_poi = _normalize(poi_name)
                for _skey, _sval in _DIRECT_SNIPPETS_PER_STOP.items():
                    if _skey.startswith("__stop_"):
                        continue
                    if _normalize(_skey) == _norm_poi:
                        _stop_snippets = _sval
                        break
            if _stop_snippets:
                # [LOCAL-411] Rank and cap snippets — top 5, not all 30.
                # Score by story quality (named person + verb of consequence + date).
                # Biography-only snippets are rejected outright (LOCAL-406 Part B).
                from snippet_ranker import rank_and_cap_snippets, SNIPPET_CAP_PER_STOP
                _ranked_snippets, _ranking_report = rank_and_cap_snippets(
                    _stop_snippets, artist=artist, work_title=poi_name,
                    category=tour_category,  # [D495] scopes the catalogue exemption
                )
                print(f"  [LOCAL-411] Stop {stop_num} snippet ranking: "
                      f"input={_ranking_report['input_count']} "
                      f"bio_rejected={_ranking_report['rejected_biography_only']} "
                      f"tier3_demoted={_ranking_report['tier3_demoted']} "
                      f"market_demoted={_ranking_report['market_demoted']} "
                      f"cap={_ranking_report['cap_applied']} "
                      f"output={_ranking_report['output_count']} "
                      f"usable={_ranking_report['usable_count']} "
                      f"(t1t2={_ranking_report['tier1_tier2_in_output']}, "
                      f"t3={_ranking_report['tier3_in_output']}, "
                      f"market={_ranking_report['market_in_output']}"
                      f"{', RESCUED' if _ranking_report['starvation_rescued'] else ''})")
                if _ranking_report['scores']:
                    print(f"    Top scores: {_ranking_report['scores'][:3]}")

                # Replace unranked list with ranked+capped list for injection
                _stop_snippets = _ranked_snippets

                # [LOCAL-407] Extract candidate specifics from snippet text.
                # These are concrete, checkable facts — numbers, named materials,
                # named techniques, named literary forms — that the prose MUST prefer
                # over general claims like "revolutionized" or "had no precedent".
                import re as _re407
                _candidate_specifics = []
                _all_snippet_text = ' '.join(
                    _snip.get('snippet', '') for _snip in _stop_snippets
                )
                # [LOCAL-408] Also scan work identity medium — it contains verified
                # specifics like "40 color lithographs" and "publisher's vellum" that
                # the regex should extract as candidate specifics.
                if _matched_work and _matched_work.get('medium'):
                    _all_snippet_text += ' ' + _matched_work['medium']
                # Numbers: edition sizes, plate counts, dates
                for _num_match in _re407.finditer(
                    r'(?:numbered|edition of|limited to|signed and numbered)\s+(\d+[/]\d+|\d+)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"edition/number: {_num_match.group(0).strip()}")
                # [LOCAL-419] Set/suite/copy sizes: "set of 10", "suite of 11", "one of 220 copies"
                for _set_match in _re407.finditer(
                    r'(?:set\s+of|suite\s+of|one\s+of\s+(?:only\s+)?)\s*(\d+)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"edition/number: {_set_match.group(0).strip()}")
                for _copies_match in _re407.finditer(
                    r'(\d+)\s+(?:copies|impressions)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"edition/number: {_copies_match.group(0).strip()}")
                # Named materials: Japan paper, Arches, vellum, sheepskin, etc.
                for _mat_match in _re407.finditer(
                    r'(?:on|printed on|paper:?|publisher[\'\u2019]?s?)\s+(Japan(?:\s+paper)?|Arches|vellum|Rives|wove|laid|sheepskin|parchment)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"material: {_mat_match.group(0).strip()}")
                # Plate/lithograph counts (including drypoints)
                for _plate_match in _re407.finditer(
                    r'(\d+)\s+(?:colou?r\s+)?(?:lithograph|etching|aquatint|plate|woodcut|drypoint)s?',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"plate count: {_plate_match.group(0).strip()}")
                # [LOCAL-419] Named publishers/printers from snippets
                # Matches: "published by X", "publisher: X", "Publisher X ;", "printed by X", "Printer X ;"
                for _pub_match in _re407.finditer(
                    r'(?:[Pp]ublish(?:ed|er)\s*(?:by|:| )\s*|[Pp]rint(?:ed|er)\s*(?:by|:| )\s*)'
                    r'([A-Z\u00C0-\u024F][\w\u00C0-\u024F]+(?:\s+[\w\u00C0-\u024F]+){0,4}?)(?:\s*[;.,]|\s*$)',
                    _all_snippet_text):
                    _pub_name = _pub_match.group(1).strip()
                    # Skip generic words that aren't names
                    if _pub_name.lower() not in ('the', 'a', 'an', 'by', 'in', 'on', 'paris', 'new'):
                        _candidate_specifics.append(f"publisher/printer: {_pub_name}")
                # Literary forms: poem, prose, text, fable
                for _form_match in _re407.finditer(
                    r'(?:based on|illustrat(?:ing|es?)|accompanying|wrote the|his own)\s+'
                    r'(poem|prose|text|fable|novel|essay|verse)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"literary form: {_form_match.group(0).strip()}")
                # Named literary work references
                for _form_match2 in _re407.finditer(
                    r"(?:Miró'?s?|artist'?s?)\s+(poem|fantasy|surrealist fantasy)",
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"literary form: {_form_match2.group(0).strip()}")
                # Dates with context
                for _date_match in _re407.finditer(
                    r'(\d{4}),?\s+(?:no\.?\s*\d+)',
                    _all_snippet_text, _re407.IGNORECASE):
                    _candidate_specifics.append(f"catalogue ref: {_date_match.group(0).strip()}")
                # Deduplicate
                _candidate_specifics = list(dict.fromkeys(_candidate_specifics))

                if _candidate_specifics:
                    print(f"  [LOCAL-407] Stop {stop_num}: {len(_candidate_specifics)} candidate specifics extracted: "
                          f"{[cs[:40] for cs in _candidate_specifics[:4]]}")

                # [LOCAL-413] Use module-scope build_snippet_block for testability
                _snippet_block = build_snippet_block(_stop_snippets, artist, _candidate_specifics)
                description_prompt += _snippet_block
                _local402_snippets_injected = True
                print(f"  [LOCAL-402] Stop {stop_num}: injected {len(_stop_snippets)} snippets as reference material")

        # [B6] Scored story elements → generation wiring (per-status phrasing)
        # Reads ranked elements from work_stories cache and injects them with
        # status-appropriate instructions: documented→fact, reported→attribution,
        # legend→"the story goes…", disputed→both sides with sources.
        # [LOCAL-37] Uses diversity-adjusted selections when available.
        # [LOCAL-438] Fallback uses quality-sorted packing instead of rank-and-cap.
        if tour_category == 'museum' and poi_name and artist:
            try:
                from work_story_searcher import normalize_work_key, work_stories_get
                from story_selection import select_stories_for_stop, STOP_WORD_BUDGET
                from three_class_retrieval import classify_element, CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL
                
                # [LOCAL-37] Use pre-computed diversity-adjusted selection if available
                _b6_selection = _diversity_adjusted_selections.get(poi_name) if _diversity_adjusted_selections else None
                if not _b6_selection:
                    # [LOCAL-438] Fallback: quality-sorted packing from cache
                    _b6_work_key = normalize_work_key(poi_name, artist)
                    _b6_cached = work_stories_get(_b6_work_key)
                    if _b6_cached and _b6_cached.get('elements'):
                        _packed = select_stories_for_stop(_b6_cached['elements'], budget=STOP_WORD_BUDGET)
                        _packed_set = set(id(p) for p in _packed)
                        _runners = [e for e in _b6_cached['elements'] if id(e) not in _packed_set]
                        _b6_selection = {
                            'selected_elements': _packed,
                            'runner_up_elements': _runners[:2],
                        }
                
                if _b6_selection:
                    _b6_selected = _b6_selection.get('selected_elements', [])
                    _b6_runners = _b6_selection.get('runner_up_elements', [])[:2]
                    if _b6_selected:
                        _b6_block = "\nSTORY ELEMENTS (use these as primary material, follow phrasing rules per status):\n"
                        # [LOCAL-37] Show class distribution for transparency
                        _b6_classes_used = set()
                        for _elem in _b6_selected:
                            _status = _elem.get('corroboration_status', 'reported')
                            _text = _elem.get('text', '')[:200]
                            _etype = _elem.get('type', '')
                            _eclass = classify_element(_elem)
                            _b6_classes_used.add(_eclass)
                            _class_tag = f"[{_eclass.upper()}]"
                            if _status == 'documented':
                                _b6_block += f"  {_class_tag} [FACT — state directly, no attribution needed] ({_etype}): {_text}\n"
                            elif _status == 'reported':
                                _src_domain = _elem.get('source_domain', 'sources')
                                _b6_block += f"  {_class_tag} [REPORTED — use inline attribution: \"According to {_src_domain}...\"] ({_etype}): {_text}\n"
                            elif _status == 'legend':
                                _b6_block += f"  {_class_tag} [LEGEND — frame as: \"The story goes that...\"] ({_etype}): {_text}\n"
                            elif _status == 'disputed':
                                _b6_block += f"  {_class_tag} [DISPUTED — expose both sides with sources] ({_etype}): {_text}\n"
                            else:
                                _b6_block += f"  {_class_tag} [{_status}] ({_etype}): {_text}\n"
                        if _b6_runners:
                            _b6_block += "  TEXTURE (weave in if natural):\n"
                            for _elem in _b6_runners:
                                _eclass = classify_element(_elem)
                                _b6_block += f"    [{_eclass.upper()}] ({_elem.get('type','')}) {_elem.get('text','')[:120]}\n"
                        
                        # [LOCAL-37] Instruct GPT to balance across classes
                        _missing_classes = {CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL} - _b6_classes_used
                        if len(_b6_classes_used) < 3:
                            _b6_block += (
                                "\n  CLASS BALANCE: Your description should include material from "
                                "multiple classes (Details=physical facts, Historical=era/style context, "
                                "Social=people). Avoid producing only vague historical atmosphere.\n"
                            )
                        description_prompt += _b6_block
                
                # [LOCAL-37] Inject category-level historical context if available
                _tcr_result = _three_class_results.get(poi_name) if _three_class_results else None
                if _tcr_result and _tcr_result.get('category_context', {}).get(CLASS_HISTORIC):
                    _cat_ctx = _tcr_result['category_context'][CLASS_HISTORIC]
                    _category_name = _tcr_result.get('category', '')
                    if _cat_ctx and len(_cat_ctx) > 100:
                        # Inject with framing guard
                        _cat_excerpt = _cat_ctx[:600]
                        description_prompt += (
                            f"\nCATEGORY CONTEXT (about '{_category_name}' in general — "
                            f"frame as category facts, NEVER claim these facts are about this specific object):\n"
                            f"{_cat_excerpt}\n"
                            f"RULE: When using this context, say 'objects of this type...' or "
                            f"'{_category_name} pieces were typically...', NEVER 'this {_category_name} was...'\n"
                        )
            except ImportError:
                _import_logger.error("[B6] MISSING: story element wiring modules — elements→generation per-status phrasing DISABLED for this stop")
            except Exception as _b6_err:
                print(f"  [B6] Story element wiring error (stop {stop_num}): {_b6_err}")

        # Add venue containment constraint for single-venue museum tours
        if tour_category == 'museum' and _museum_venue_name:
            description_prompt += f"""
CRITICAL CONSTRAINT: This artwork/exhibit MUST be something that is physically on display at '{_museum_venue_name}'. Describe the ARTWORK itself — its visual qualities, technique, symbolism, and story. If you know which room or hall it's in, mention that briefly. If you don't know the exact room, do NOT fabricate one — just describe the work directly.
"""
            # [LOCAL-48] Exhibition-vs-object verification (Musée Matisse fabrication fix)
            description_prompt += """
EXHIBITION VS OBJECT RULE (critical — prevents fabrication):
A catalogue entry may be an EXHIBITION, a GALLERY, or a PROGRAMME rather than a physical object.
Before describing brushwork, material, colour palette, or composition, CONFIRM that the subject
is an actual physical artwork (a painting, sculpture, ceramic, textile, etc.).
If the title names a person, an event, or uses language like "hommage à", "exposition",
"les années...", it is likely an EXHIBITION or PROGRAMME, not a canvas or object.
- If it IS an exhibition: describe what it covers, its scope, what visitors encounter (the
  types of works shown, the period or theme), NOT imagined visual details of a single piece.
- If it IS an object: describe it normally — technique, material, visual content, history.
Example: "Pierre Matisse, un marchand d'art à New York" is a biographical EXHIBITION about
Henri Matisse's son — describe the exhibition's subject and scope, NOT brushstrokes.
"""
            # [LOCAL-48] Thin-corpus honesty guard (Palais Lascaris fabrication fix)
            # LOCAL-72 A/B test: rule PRESENT → mean 39.7 facts (stdev 2.1, min 38);
            # rule REMOVED → mean 32.7 facts (stdev 7.0, min 26). The rule acts as a
            # fact-density stabiliser, not a thinning instruction. Restored per LEAD.
            # Note: 0 fabrications in 3 rule-removed runs — the rule does not earn its
            # keep as an anti-fabrication guard; it earns it by pointing the model at
            # the fact sheet, which stabilises output density.
            description_prompt += f"""
THIN-CORPUS HONESTY RULE (critical — prevents fabrication):
If you do not have verified, specific information about this particular work's visual content,
material, or history, DO NOT INVENT details. Instead:
- State what IS known (title, artist, period, medium if available)
- Describe the TYPE of work and its general context
- Acknowledge the gap honestly rather than filling it with plausible-sounding fiction
A 120-word honest description beats a 300-word fabricated one. When your knowledge is thin,
be SHORT and FACTUAL. The number of confirmed facts in the fact sheet below tells you how
much material you actually have to work with.
"""
            # [D5] No artist bio repetition in descriptions
            description_prompt += """
Do NOT repeat the artist's biographical background (birth year, nationality, school associations like 'École de Paris', artistic formats like 'stained glass and stage sets'). That information belongs in the tour introduction only. Here, focus EXCLUSIVELY on THIS SPECIFIC ARTWORK — what it depicts, its technique, its story, what to look for with your eyes.
"""
            # [Cycle 4] Ban forbidden cliché phrases that GPT overuses
            # [LOCAL-412] Consolidated: removed verbose BANNED PHRASES and UNEARNED ADJECTIVES
            # blocks (~1600 chars). The regex DO NOT USE line + DECLARATIVE PROSE rules already
            # cover this. Replaced with a short, high-signal instruction.
            description_prompt += """
BANNED PHRASES — do NOT use any of these in your description:
- "vibrant colors" / "dreamlike imagery" / "dreamlike quality"
- "creative genius" / "artistic prowess" / "masterpiece that"
- "stir the soul" / "touch the heart" / "pulsate with life"
- "symphony of emotions" / "tapestry of dreams" / "weaves a narrative"
- "truly remarkable" / "a testament to" / "stands as a testament"
- "captivating artistry" / "mesmerizing world" / "intricate details"
- "invites you to explore/discover/reflect" / "immerse yourself in"
- "invites contemplation" / "invites the viewer" / "invites us to"
- "can't help but" / "feast for the eyes" / "step into a world"
- "created by God" / "fall into sin" / "disobedience" / "the fall of humanity"
Instead, use SPECIFIC, CONCRETE language: name colors precisely (cerulean, ochre, vermilion), describe actual compositional choices, mention documented historical context.

UNEARNED ADJECTIVES — these words are BANNED unless the same sentence or the one before it
contains the specific evidence that earns them:
- "vibrant" — ONLY permitted if you name the specific colors/contrasts that make it vibrant
- "stunning" — ONLY if you describe what causes the visual impact (scale? technique? contrast?)
- "remarkable" — ONLY if you state what distinguishes it from comparable works
- "mesmerizing" — ONLY if you explain the optical or compositional mechanism
- "exquisite" — ONLY if you describe the craftsmanship detail (grain, jointwork, brushstroke)
- "breathtaking" — ONLY if you name the physical feature that produces the effect
- "captivating" — ONLY if you explain what holds attention and why
If you cannot provide that evidence in the same breath, delete the adjective. A bare noun
is better than a noun preceded by an unearned superlative.
"""
            description_prompt += """
FACTUAL INTEGRITY RULE: Do NOT invent visual specifics or biographical claims not in the fact sheet above. You may describe the general biblical SUBJECT (e.g. "depicts the parting of the Red Sea") but do NOT assert specific visual details as facts (colors, composition) unless grounded in the facts above. Never call a work "the artist's final masterpiece" or similar unverifiable superlatives.
"""
            # [C5-5] Truthful framing for multi-work cycles
            if 'biblical message' in poi_name.lower() or 'message biblique' in poi_name.lower():
                description_prompt += """
NOTE: "The Biblical Message" (Message Biblique) is the name of the COMPLETE CYCLE of 17 large-scale paintings by Chagall, illustrating Genesis, Exodus, and the Song of Songs. Describe it as a cycle/series of paintings, NOT as a single painting. The museum was PURPOSE-BUILT to house this cycle (inaugurated 1973).
"""

        # [LOCAL-12 Fix D] Specificity gate: adaptive description length.
        # When confirmed facts are fewer than 2 AND no corpus context was injected,
        # reduce description target and instruct GPT not to pad with generic prose.
        # [LOCAL-44] Length scales with substance: short stops stay short, rich stops may run longer.
        # [LOCAL-98] Catalogue metadata (period/material) IS substance — a stop with these
        # must never get the 120-word "be SHORT" instruction that competes with binding.
        # [LOCAL-379] A matched work with a WORK IDENTITY block IS substance — the model
        # has artist, date, medium to write about. Do not constrain to 120 words.
        _confirmed_count = len(fact_sheet.get('confirmed_facts', [])) if fact_sheet else 0
        _had_corpus = fact_sheet.get('had_corpus_context', False) if fact_sheet else False
        _has_catalogue_metadata = bool(_c51_period or _c51_material)
        _has_work_identity = bool(_work_identity_block)
        _specificity_short = (_confirmed_count < 2 and not _had_corpus
                              and not _has_catalogue_metadata and not _has_work_identity)

        if _specificity_short:
            _word_target = "120"
            _word_target_instruction = (
                f"Write EXACTLY {_word_target} words (NOT 300). You have very limited verified information "
                f"about this specific exhibit. Be honest and concise: describe only what you can confirm, "
                f"note what is unknown, and do NOT pad with generic appreciation language like "
                f"'a testament to the artist's genius' or 'invites contemplation'. "
                f"Brevity with real content is better than length with filler."
            )
        elif _confirmed_count >= 5 or (_had_corpus and _confirmed_count >= 3):
            # Rich stop: more confirmed facts justify longer treatment
            _word_target = "350"
            _word_target_instruction = (
                f"You have rich verified material for this stop. Write up to {_word_target} words, "
                f"using the extra space ONLY for additional sourced facts or explained connections — "
                f"NOT for padding, praise, or instructing the listener."
            )
        else:
            _word_target = "280"
            _word_target_instruction = ""

        # [LOCAL-381] Build orientation instruction that respects medium constraint.
        # When medium is unknown AND the title contains misleading architectural words,
        # the orientation must NOT give spatial directions — prevents the model from
        # re-inferring "ceiling" from "Plafond" in the title.
        _orientation_has_misleading_title = (
            _matched_work is not None
            and not _matched_medium
            and _title_has_misleading_words(_matched_work.get('title', ''))
        )
        if _orientation_has_misleading_title:
            _orientation_instruction = (
                "Orientation: (introduce the work by naming it and stating what is "
                "known — artist, date, collaborator — but do NOT describe physical "
                "form, do NOT say where to stand or look, do NOT describe placement "
                "or spatial orientation of the work)"
            )
        else:
            _orientation_instruction = (
                "Orientation: (write a brief orientation text explaining the best "
                "viewing position here)"
            )

        description_prompt += f"""
Format your response as follows:
{_orientation_instruction}

Then write the description directly — a flowing, {_word_target}-word narrative about the exhibit. Do NOT wrap it in brackets, placeholders, or formatting markers. Just write the prose.

MINIMUM LENGTH: Your description (after the Orientation section) MUST be at least 120 words. If you do not have 120 words of verified content, discuss the artistic form, the collaboration, or the exhibition context to reach the floor. Never deliver fewer than 120 words.

DO NOT include any section headers other than "Orientation:" - the description should flow naturally after the orientation section.
DO NOT include directions to the next stop - these will be added separately.
"""
        if _word_target_instruction:
            description_prompt += f"\nLENGTH CONSTRAINT: {_word_target_instruction}\n"

        # [LOCAL-209] CORPUS GATE: EMPTY — no corpus exists for this stop at all.
        # Stricter than VENUE_ONLY: there is no venue-level material either.
        # The paragraph must not assert dates, measurements, nicknames, or attributions.
        if hasattr(poi_name, '__hash__') and poi_name in _corpus_gate_empty_stops:
            description_prompt += f"""
CORPUS GATE: EMPTY (D50 enforcement — LOCAL-209):
There is NO verified source material for "{poi_name}" — no stop-level corpus,
no venue-level corpus, nothing. Every specific claim you might generate about
this place comes from your training data and CANNOT be verified.

YOU MUST NOT:
- Assert any specific date, year, century, or historical period
- State any measurement (depth, height, distance, area)
- Attribute a nickname, title, or epithet to this place
- Name specific people, architects, artists, or historical figures
- Claim specific events happened here
- Describe specific architectural features as fact

YOU MAY ONLY:
- Name the stop and its general geographic context (e.g. "a coastal town east of Nice")
- Describe what is physically visible to a cyclist arriving now (sea, buildings, streets)
- Provide wayfinding and orientation ("look to your left", "the harbor is ahead")
- Use hedging language ("this area is known for…", "visitors often notice…")
- Note the atmosphere and sensory experience (sounds, smells, light)

Write 60-80 words maximum. This is an orientation-only placeholder. No factual claims.
"""
        # [LOCAL-198] CORPUS GATE: SHORTENED narration for stops without subject coverage.
        # When the gate detected this stop as VENUE_ONLY, override the prompt
        # to request only venue-grounded content that does NOT describe the artwork.
        elif hasattr(poi_name, '__hash__') and poi_name in _corpus_gate_shortened_stops:
            description_prompt += f"""
CRITICAL CORPUS GATE RESTRICTION (D50 enforcement — LOCAL-198):
The corpus for this stop does NOT contain information about the specific artwork/exhibit
"{poi_name}". The available text is about the venue generally.

YOU MUST NOT:
- Describe the artwork's appearance, materials, technique, or composition
- Name the artist's practice, style, or art-historical movement
- Claim anything about what the visitor will see at this specific stop
- Invent details about the work from your training data

YOU MAY ONLY:
- Note the stop's name and its location within the venue
- Share venue-level facts that ARE in the corpus (opening date, general collection scope)
- Describe the physical surroundings and wayfinding
- Acknowledge that detailed information about this specific work is limited

Write 80-100 words maximum. This is a venue-grounded placeholder, not a full stop narration.
"""
        # [LOCAL-203] CORPUS GATE: CREATOR_ONLY — may discuss the maker, must not describe the object.
        elif hasattr(poi_name, '__hash__') and poi_name in _corpus_gate_creator_only_stops:
            description_prompt += f"""
CORPUS GATE: CREATOR_ONLY (D75 enforcement — LOCAL-203):
The corpus for this stop contains information about the MAKER/ARTIST of "{poi_name}",
but does NOT contain verified information about the specific object/artwork itself.

YOU MAY:
- Discuss the artist's or maker's biography, career, and significance
- Mention their techniques, style, and historical context — IF stated in the passages
- Note that this maker created the work at this stop

YOU MUST NOT:
- Describe the object's appearance, dimensions, materials, or condition
- Claim what the visitor will see at this specific stop
- Invent details about the physical work from your training data
- State facts about the object that are not in the provided passages

Ground all claims about the maker in the passages provided. Do not describe the object.
"""

        # [LOCAL-183] Inject per-stop corpus passages with provenance and grounding rule.
        # This is the production wiring that D31/D54/D57 identified as missing:
        # stop_corpus was only read by the detector, never fed to the generator.
        if _stop_corpus_data and poi_name in _stop_corpus_data:
            _sc_stop_data = _stop_corpus_data[poi_name]
            if _sc_stop_data and _sc_stop_data.get('passages'):
                try:
                    from stop_corpus_reader import format_passages_for_prompt
                    _sc_prompt_block = format_passages_for_prompt(_sc_stop_data, poi_name)
                    if _sc_prompt_block:
                        description_prompt += _sc_prompt_block
                except ImportError:
                    pass  # Module unavailable — non-fatal, already logged at fetch time

        # [S43] Storied: inject persona tone override into description prompt
        if _storied_mode and _persona_tone:
            description_prompt += f"""
NARRATIVE TONE: Write this description with a {_persona_tone} tone — emphasize aspects that would appeal to someone with this sensibility.
"""

        # [LOCAL-98] FINAL BINDING — inject catalogue date/material requirements as the
        # LAST instruction in the prompt. Rationale: GPT-3.5-turbo exhibits strong recency
        # bias; instructions near the end of the user message are followed most reliably.
        # Previously this block was buried among 10+ competing rules (brevity, banned phrases,
        # exhibition checks) and the model paraphrased or dropped the required facts.
        # The block now uses explicit English target strings and a "FINAL REQUIREMENT" header
        # to maximise compliance.
        #
        # [LOCAL-322] FR→EN material mapping. The catalogue materials extracted by
        # story_miner._extract_material() are in French. The narration is English.
        # This mapping translates every French material term the extractor can
        # return (its _MATERIALS list) into its standard English art-history
        # equivalent. Built from the actual corpus terms, not invented.
        _FR_EN_MATERIAL_MAP = {
            'acier': 'steel',
            'cuivre': 'copper',
            'cuir': 'leather',
            'soie': 'silk',
            'laque': 'lacquer',
            'schiste': 'schist',
            'chlorite': 'chlorite',
            'bois': 'wood',
            'bronze': 'bronze',
            'marbre': 'marble',
            'porcelaine': 'porcelain',
            'céramique': 'ceramic',
            'jade': 'jade',
            'ivoire': 'ivory',
            'laiton': 'brass',
            'terre cuite': 'terracotta',
            'grès': 'stoneware',
            'fer': 'iron',
            'argent': 'silver',
            'papier': 'paper',
            'encre': 'ink',
            'gouache': 'gouache',
            'huile': 'oil',
            'aquarelle': 'watercolor',
            'pastel': 'pastel',
            "feuille d'or": 'gold leaf',
            'dorure': 'gilding',
            'xylogravure': 'woodblock print',
            'soie brodée': 'embroidered silk',
            'bois laqué': 'lacquered wood',
            'cuir laqué': 'lacquered leather',
            'polychrome': 'polychrome',
            'laqué': 'lacquered',
            'laquée': 'lacquered',
            'or': 'gold',
        }

        # [LOCAL-322] Translate a single French material term to English.
        # If the full term matches, use it. Otherwise try each word.
        # Returns None if no translation is known (caller should omit, not emit French).
        def _translate_material_to_english(fr_term):
            """Translate a French material term to English using the corpus-derived map."""
            fr_lower = fr_term.strip().lower()
            if fr_lower in _FR_EN_MATERIAL_MAP:
                return _FR_EN_MATERIAL_MAP[fr_lower]
            # Try multi-word compound (e.g., "bois laqué")
            for fr_key, en_val in _FR_EN_MATERIAL_MAP.items():
                if fr_key == fr_lower:
                    return en_val
            return None

        # [LOCAL-322] Translate the full comma-separated material string.
        # Returns (english_primary, english_all_list) where english_primary is
        # the first material translated (or None), and english_all_list are all
        # successfully translated terms.
        _material_english = None  # The primary material in English
        _material_english_all = []  # All translated materials
        if _c51_material:
            _mat_parts = [p.strip() for p in _c51_material.split(',')]
            for _mp in _mat_parts:
                _en = _translate_material_to_english(_mp)
                if _en:
                    _material_english_all.append(_en)
            _material_english = _material_english_all[0] if _material_english_all else None

        if _c51_period or _c51_material:
            _final_binding = "\n━━━ FINAL REQUIREMENT (non-negotiable — your description will be REJECTED if these are missing) ━━━\n"
            if _c51_period:
                # Build explicit English equivalent for the period
                import re as _re98
                _period_english = _c51_period  # default: use as-is
                # Map common French period strings to English
                _century_m = _re98.search(r'((?:X{0,3}(?:IX|IV|V?I{0,3})))e\s+si[eè]cle', _c51_period)
                if _century_m:
                    _rom = _century_m.group(1).upper()
                    _rom_map = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,
                                'IX':9,'X':10,'XI':11,'XII':12,'XIII':13,'XIV':14,'XV':15,
                                'XVI':16,'XVII':17,'XVIII':18,'XIX':19,'XX':20}
                    _arab = _rom_map.get(_rom, '')
                    if _arab:
                        _suffix = 'th'
                        if _arab == 1: _suffix = 'st'
                        elif _arab == 2: _suffix = 'nd'
                        elif _arab == 3: _suffix = 'rd'
                        _period_english = f"{_arab}{_suffix} century"
                        # Preserve qualifiers like "2nde moitié du"
                        if 'moitié' in _c51_period.lower():
                            if '2nde moitié' in _c51_period.lower() or 'seconde moitié' in _c51_period.lower():
                                _period_english = f"second half of the {_arab}{_suffix} century"
                            elif '1ère moitié' in _c51_period.lower() or 'première moitié' in _c51_period.lower():
                                _period_english = f"first half of the {_arab}{_suffix} century"
                        elif 'début' in _c51_period.lower():
                            _period_english = f"early {_arab}{_suffix} century"
                        elif 'fin' in _c51_period.lower():
                            _period_english = f"late {_arab}{_suffix} century"
                elif _re98.match(r'^\d{4}$', _c51_period.strip()):
                    _period_english = _c51_period.strip()  # raw year stays as-is

                _final_binding += f'YOUR DESCRIPTION MUST CONTAIN THIS DATE: "{_period_english}"\n'
                _final_binding += f'  Write the exact string "{_period_english}" somewhere in your text. Not "around that time", not a vague century — the literal string "{_period_english}".\n'
            if _c51_material:
                # [LOCAL-322] Use English material name in the prompt binding.
                # If no English translation exists, omit material binding entirely
                # (a false pass costs nothing; a false fail ships broken French prose).
                if _material_english:
                    _final_binding += f'YOUR DESCRIPTION MUST MENTION THIS MATERIAL: "{_material_english}"\n'
                    _final_binding += f'  Mention that this work is made of/crafted from "{_material_english}" somewhere in your text.\n'
                    # [LOCAL-322] If there are additional translated materials, mention them
                    if len(_material_english_all) > 1:
                        _all_en_str = ', '.join(_material_english_all)
                        _final_binding += f'  The full material list in English is: {_all_en_str}. You may mention multiple materials.\n'
                else:
                    # [LOCAL-322] No known English translation — do not ask the LLM to
                    # write an untranslatable French term. Skip material binding.
                    print(f"  [LOCAL-322] Stop {stop_num}: no EN translation for material '{_c51_material}' — skipping material binding")
            # [LOCAL-322] Prevent French material terms from leaking into English narration
            # from the DOCUMENTED FACTS context injected earlier.
            _final_binding += 'LANGUAGE: Write ONLY in English. If the context above contains French terms for materials or techniques (e.g., "xylogravure", "bois", "soie"), translate them to English (e.g., "woodblock print", "wood", "silk"). Never write French words in your description.\n'
            _final_binding += "━━━ END FINAL REQUIREMENT ━━━\n"
            description_prompt += _final_binding

        # [LOCAL-408] FACTS FIRST — move required names and specifics to the TOP
        # of the prompt (primacy effect). The model sees these before the style rules.
        # This addresses the diagnosis: specifics reach the prompt but are buried under
        # 60+ lines of instructions at position 15000+ in a 21000-char prompt.
        #
        # [LOCAL-417] CRITICAL FIX: Only demand names the pipeline actually supplied.
        # If a person from story beats does not appear in any snippet text for this
        # stop, we MUST NOT tell the model their name is required — that creates an
        # unsatisfiable constraint and the model reports the impossibility instead of
        # writing prose. The denylist cannot catch every rephrasing of "I can't do
        # what you asked"; the fix is to never ask for what we didn't provide.
        _facts_first_block = ""
        if _DIRECT_SNIPPETS_PER_STOP and tour_category == 'museum':
            _ff_parts = []
            # Required names from story beats — ONLY those with snippet evidence
            if _storied_mode and _story_beats_per_stop and idx < len(_story_beats_per_stop):
                _ff_beats = _story_beats_per_stop[idx]
                _ff_required = [b for b in _ff_beats if b['role'] not in ('circumstance', 'stakes')
                                and not b.get('exhibition_wide')]
                # [LOCAL-417] Filter: only demand names that appear in the snippet text
                # for this stop. A name the pipeline never supplied cannot be required.
                _snippet_text_lower = _all_snippet_text.lower() if _all_snippet_text else ''
                _ff_verified = []
                _ff_suppressed = []
                for _ffb in _ff_required:
                    _ff_surname = _ffb['person'].split()[-1]
                    # Check if the person's surname appears anywhere in snippet text
                    if _snippet_text_lower and _ff_surname.lower() in _snippet_text_lower:
                        _ff_verified.append(_ffb)
                    else:
                        _ff_suppressed.append(_ffb)
                if _ff_suppressed:
                    print(f"  [LOCAL-417] Stop {stop_num}: SUPPRESSED {len(_ff_suppressed)} required names "
                          f"(no snippet evidence): {[b['person'] for b in _ff_suppressed]}")
                    # [LOCAL-417] Track suppressed names so beat retry doesn't demand them
                    _417_suppressed_beat_names = set(b['person'].split()[-1] for b in _ff_suppressed)
                if _ff_verified:
                    _ff_parts.append("━━━ NAMES THAT MUST APPEAR (your text is rejected without these) ━━━")
                    for _ffb in _ff_verified[:4]:
                        _ff_surname = _ffb['person'].split()[-1]
                        _ff_parts.append(f"  • {_ff_surname} ({_ffb['person']}, {_ffb['role'].replace('_',' ')})")
                    # Add the artist only if artist is known
                    if artist:
                        _ff_artist_surname = artist.split()[-1]
                        _ff_parts.append(f"  • {_ff_artist_surname} ({artist}, artist)")
                    _ff_parts.append("━━━ END REQUIRED NAMES ━━━")
                    _ff_parts.append("")
                elif artist:
                    # No story-beat names verified, but artist is known — still require artist
                    _ff_artist_surname = artist.split()[-1]
                    _ff_parts.append("━━━ NAMES THAT MUST APPEAR (your text is rejected without these) ━━━")
                    _ff_parts.append(f"  • {_ff_artist_surname} ({artist}, artist)")
                    _ff_parts.append("━━━ END REQUIRED NAMES ━━━")
                    _ff_parts.append("")

            # Candidate specifics (concrete facts from snippets)
            if _candidate_specifics:
                _ff_parts.append("━━━ CONCRETE FACTS TO USE (prefer these over general claims) ━━━")
                for _ffc in _candidate_specifics[:6]:
                    _ff_parts.append(f"  • {_ffc}")
                _ff_parts.append("━━━ END CONCRETE FACTS ━━━")
                _ff_parts.append("")

            if _ff_parts:
                _facts_first_block = "\n".join(_ff_parts) + "\n\n"

        # [LOCAL-408] Prepend facts-first block to the prompt
        if _facts_first_block:
            # Insert after the first line (task statement) to maintain structure
            _first_newline = description_prompt.find('\n')
            if _first_newline > 0:
                description_prompt = (
                    description_prompt[:_first_newline + 1]
                    + "\n" + _facts_first_block
                    + description_prompt[_first_newline + 1:]
                )
            else:
                description_prompt = _facts_first_block + description_prompt

        # [LOCAL-411] Report prompt size after FACTS FIRST insertion
        _prompt_size_final = len(description_prompt)
        if _local402_snippets_injected:
            _snippet_added_chars = _prompt_size_final - _prompt_size_before_snippets
            print(f"  [LOCAL-411] Stop {stop_num} prompt size: "
                  f"before_snippets={_prompt_size_before_snippets} "
                  f"after={_prompt_size_final} "
                  f"(+{_snippet_added_chars} from snippets+instructions, "
                  f"facts_first={'yes' if _facts_first_block else 'no'})")
            if _prompt_size_final > 20000:
                print(f"  [LOCAL-411] WARNING: prompt exceeds 20K chars ({_prompt_size_final})")

        # [LOCAL-414] Universal artist attribution — fires for ALL museum stops
        # when artist is known, regardless of snippet presence. Placed at the END
        # of the prompt (recency bias) so it cannot be overridden by snippets that
        # name a different artist's different work.
        if tour_category == 'museum' and artist:
            _414_artist_surname = artist.split()[-1]
            description_prompt += f"""
━━━ ARTIST ATTRIBUTION (LOCAL-414 — NON-NEGOTIABLE, FINAL AUTHORITY) ━━━
The artist of THIS specific work is: {artist}
The surname "{_414_artist_surname}" MUST appear in your text.

If the reference material above mentions OTHER artists or OTHER works (by different
artists), you may reference them only as CONTEXT — but your text MUST primarily be
about THIS work by {artist}. Naming a different artist's different work does NOT
satisfy this requirement. Your text will be REJECTED if "{_414_artist_surname}" is absent.
━━━ END ARTIST ATTRIBUTION ━━━
"""

        # [LOCAL-421] STORY REINFORCEMENT — recency effect: last instruction wins.
        # gpt-3.5-turbo buries names in evaluative prose unless told exactly what shape
        # the text must take. This block is the LAST thing in the prompt.
        # -------- [LOCAL-490 / D474] THE STORY PASS --------
        # The block below this one is the LOCAL-421 "final story shape"
        # reinforcement: instructions telling the model what a story looks like,
        # appended to a prompt that is simultaneously doing orientation,
        # directions, transitions, category voice and physical description. It
        # has to shout ("read this LAST — it overrides everything above")
        # precisely because it is competing.
        #
        # D474: the lab scores 64 doing one job, production 42.8 doing six. And
        # steps 5 and 7 of Michael's seven both need "the story for this stop" to
        # EXIST as an object — to be scored, sized to 3-5 sentences, and rotated
        # when invalid. It never did; there was only a whole stop description.
        #
        # So: run the story separately, and hand this prompt a FINISHED story
        # instead of an instruction to produce one. Behind STORY_PASS_ENABLED so
        # the comparison is a flag flip rather than a revert, which is a better
        # form of Michael's "land it alone" rule than landing it alone.
        _story_pass_result = None
        if _storied_mode and tour_category == 'museum':
            try:
                from story_pass import generate_story_for_stop, is_enabled as _sp_on
                if _sp_on():
                    # The ranked, capped snippets this stop is about to be
                    # written from — the same material the description prompt
                    # gets, so the story pass is never working from less.
                    # `_stop_snippets` is assigned inside the LOCAL-402 branch, so
                    # it can be undefined here on a stop with no direct snippets.
                    # locals() rather than a bare reference: a NameError would be
                    # swallowed by the except below and silently disable the pass
                    # for that stop, which is the kind of quiet degradation this
                    # session has spent all night removing.
                    _sp_source = locals().get('_stop_snippets') or []
                    _sp_material = []
                    for _sp_s in (_sp_source or []):
                        _sp_t = _sp_s.get('snippet') if isinstance(_sp_s, dict) else str(_sp_s)
                        if _sp_t:
                            _sp_material.append(_sp_t)
                    # [D498] Step 3a: filled slot-by-slot from `story_pass`'s own
                    # vocabulary, so the producer cannot drift from the consumer.
                    # `_sp_sources` maps each slot to where production holds it;
                    # any slot the prompt reads and this dict does not fill is a
                    # KeyError here rather than a silently empty line there.
                    from story_pass import MATRIX_KEYS
                    _sp_sources = {
                        'canonical_title': poi.get('name', ''),
                        'english_title': poi.get('english_title', ''),
                        'artist': poi.get('artist', ''),
                        'publisher': poi.get('publisher', ''),
                        'printed_by': poi.get('printed_by', '') or poi.get('printer', ''),
                        'medium': poi.get('medium', ''),
                        'credit_line': poi.get('credit_line', ''),
                        'venue_name': _museum_venue_name or '',
                        # Step 7b's rotating fact, when a previous attempt set one.
                        'focus_fact': poi.get('_focus_fact', ''),
                    }
                    _sp_matrix = {k: _sp_sources[k] for k in MATRIX_KEYS}
                    _sp_filled = sum(1 for k in MATRIX_KEYS if _sp_matrix[k])
                    print(f"  [D498] Stop {stop_num} matrix: {_sp_filled}/{len(MATRIX_KEYS)} "
                          f"slots filled — empty: "
                          f"{[k for k in MATRIX_KEYS if not _sp_matrix[k]] or 'none'}")
                    # [D500] The slot count is not the useful number. A story
                    # needs an AGENT, so report how many of the three the stop
                    # actually has — hero, sponsor, builder. Measured on the
                    # 08-20 baseline: stops 2 and 3 have exactly ONE (the artist),
                    # which is the quantity behind "there is nobody to write about".
                    try:
                        from story_roles import summarise as _d500_roles
                        print(f"  {_d500_roles(_sp_matrix, tour_category)}")
                    except Exception as _d500_err:
                        print(f"  [D500] role report unavailable (non-fatal): {_d500_err}")
                    # Step 7c: 3-5 sentences, and a larger allowance only for the
                    # stop currently scoring highest — "in most valuable we can
                    # take a larger size".
                    from story_pass import MAX_SENTENCES, MAX_SENTENCES_TOP
                    _sp_max = (MAX_SENTENCES_TOP
                               if poi.get('_is_top_value_stop') else MAX_SENTENCES)
                    _story_pass_result = generate_story_for_stop(
                        _sp_matrix, _sp_material, max_sentences=_sp_max,
                        forbidden=poi.get('_local474_forbidden', '') or '')
                    poi['_story_pass'] = _story_pass_result
                    print(f"  [LOCAL-490] Stop {stop_num} story pass: "
                          f"ok={_story_pass_result['ok']} "
                          f"({_story_pass_result['reason']}), "
                          f"${_story_pass_result['cost']:.4f}")
                    if _story_pass_result['ok']:
                        print(f"    story: \"{_story_pass_result['story'][:150]}\"")
            except ImportError as _sp_err:
                print(f"  [LOCAL-490] story_pass not importable — falling back to "
                      f"the inline shape instructions ({_sp_err})")
            except Exception as _sp_err:
                print(f"  [LOCAL-490] story pass failed (non-fatal): {_sp_err}")

        if _storied_mode and tour_category == 'museum' and _story_pass_result \
                and _story_pass_result.get('ok'):
            # A finished story. The prompt's job here is to CARRY it, not to
            # invent one — so this instruction is short, and it is a
            # prohibition on tampering rather than a lesson in narrative shape.
            description_prompt += f"""

━━━ THE STORY FOR THIS STOP (already written and fact-checked) ━━━
{_story_pass_result['story']}
━━━ END STORY ━━━

This story is REQUIRED and comes first in your description. Reproduce its facts
exactly — every name, date and number. You may adjust wording to flow into the
surrounding text; you may NOT add a fact to it, remove a named person from it,
or replace it with a story of your own.

After the story, add physical description and context if there is room. Do not
introduce any further named person who does not appear above.
"""
        elif _storied_mode and tour_category == 'museum':
            _story_reinforcement = """

━━━ FINAL STORY SHAPE (read this LAST — it overrides everything above) ━━━
Your description MUST contain a NARRATIVE of at least THREE consecutive sentences
that follows this shape:

  SENTENCE 1: Name a person (donor/publisher/printer/collaborator) and state
    ONE SPECIFIC THING they did — a decision, a commission, a gift.
    Example: "Louis Broder commissioned Miró for this portfolio because Broder
    specialized in limited editions requiring direct artist-printer collaboration."

  SENTENCE 2: State the CONSEQUENCE or REASON — why it mattered, what it caused,
    what it meant for the work.
    Example: "Broder's editions were produced with artist, poet, and printer working
    in the same workshop — Mourlot's atelier on Rue de Chabrol in Paris."

  SENTENCE 3: Connect to a SECOND named person or to the wider story.
    Example: "Boris Fridman, a Russian collector who assembled livres d'artiste,
    donated this work to the MFA, adding to the museum's holdings of
    collaborative printed works."

WHAT TO AVOID:
  - "X's collaboration... showcasing a unique fusion" (evaluation, not story)
  - "stands as a testament to" (evaluation)
  - "the transformative power of" (empty abstraction)
  - "goes beyond mere artistic interpretation" (empty)

Write the story FIRST, then add physical description if space allows.
━━━ END FINAL STORY SHAPE ━━━
"""
            description_prompt += _story_reinforcement

        # [LOCAL-474] The post-gate retry sets this. It goes LAST, after every other
        # instruction, because it is the one thing the previous draft got wrong and
        # instructions nearest the end carry most weight. Absent on a first draft.
        if poi.get('_local474_forbidden'):
            description_prompt += poi['_local474_forbidden']

        description_data = {
            "model": story_pass_model(),  # D370 — story pass only, not the pipeline default
            "messages": [
                {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
                {"role": "user", "content": description_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }

        # [LOCAL-408] Dump the literal prompt for stop 1 to a file for diagnosis.
        # This answers: do the specifics reach the prompt at all?
        # Only dump when _DIRECT_SNIPPETS_PER_STOP is populated (MFA tour, not Palais control).
        if stop_num == 1 and _DIRECT_SNIPPETS_PER_STOP:
            _prompt_dump_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_dump_stop1.txt')
            try:
                with open(_prompt_dump_path, 'w', encoding='utf-8') as _pdf:
                    _pdf.write("=" * 80 + "\n")
                    _pdf.write("LITERAL PROMPT SENT TO LLM — STOP 1\n")
                    _pdf.write(f"Generated: {datetime.now().isoformat()}\n")
                    _pdf.write(f"Model: {description_data['model']}\n")
                    _pdf.write(f"Temperature: {description_data['temperature']}\n")
                    _pdf.write(f"Max tokens: {description_data['max_tokens']}\n")
                    _pdf.write("=" * 80 + "\n\n")
                    _pdf.write("--- SYSTEM MESSAGE ---\n")
                    _pdf.write(description_data['messages'][0]['content'])
                    _pdf.write("\n\n--- USER MESSAGE ---\n")
                    _pdf.write(description_data['messages'][1]['content'])
                    _pdf.write("\n\n" + "=" * 80 + "\n")
                    _pdf.write(f"Total user message length: {len(description_data['messages'][1]['content'])} chars\n")
                    # [LOCAL-408] Log whether candidate specifics were found
                    _pdf.write(f"\n--- CANDIDATE SPECIFICS STATUS ---\n")
                    _pdf.write(f"candidate_specifics found: {len(_candidate_specifics)}\n")
                    if _candidate_specifics:
                        for _cs_item in _candidate_specifics:
                            _pdf.write(f"  • {_cs_item}\n")
                    else:
                        _pdf.write("  (none extracted — snippets may be empty or regex missed)\n")
                    _pdf.write(f"\n--- SNIPPET INJECTION STATUS ---\n")
                    _pdf.write(f"_local402_snippets_injected: {_local402_snippets_injected}\n")
                    _pdf.write(f"_DIRECT_SNIPPETS_PER_STOP keys: {list(_DIRECT_SNIPPETS_PER_STOP.keys()) if _DIRECT_SNIPPETS_PER_STOP else 'None/empty'}\n")
                print(f"  [LOCAL-408] Prompt dump written to: {_prompt_dump_path}")
            except Exception as _dump_err:
                print(f"  [LOCAL-408] Prompt dump FAILED: {_dump_err}")

        # [LOCAL-26] Retry loop with placeholder-leak validation
        # [LOCAL-394] Track best valid description across retries. A stop is NEVER
        # dropped to satisfy a length or beat rule — if all retries fail, we return
        # the best description produced rather than GENERATION_FAILED.
        _max_retries = 2
        _best_description = None  # (orientation, description, word_count, tokens_used, call_cost)
        _attempts_for_resolution = []  # [LOCAL-422] Accumulated for resolve_final_description
        for _attempt in range(_max_retries + 1):
            try:
                description_response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    data=json.dumps(description_data),
                    timeout=90  # [LOCAL-292] Explicit timeout — prevents unbounded stall
                )

                if description_response.status_code == 200:
                    description_result = description_response.json()
                    description_text = description_result["choices"][0]["message"]["content"]

                    tokens_used = description_result["usage"]["total_tokens"]
                    # D370: price at the model this call actually used, not the
                    # pipeline default — otherwise a gpt-4o story pass is billed
                    # at gpt-3.5 rates and Subscribed charges 5x that understatement.
                    call_cost = _tour_llm_cost(tokens_used, model=description_data["model"])
                    print(f"Stop {stop_num} API call cost: ${call_cost:.4f} "
                          f"({tokens_used} tokens, model={description_data['model']})")

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
                        # [LOCAL-251] Tour-type-appropriate fallback when LLM doesn't
                        # include "Orientation:" section. The description is the full response.
                        orientation = "Position yourself to best view this location." if tour_category != 'museum' else "Look for this work in the galleries."
                        description = description_text.strip()

                    # [LOCAL-256] Strip "Description:" label the LLM sometimes echoes
                    # as a field header between orientation and body text. This is a
                    # schema field name that must never reach TTS-bound narration.
                    if description:
                        description = re.sub(r'^Description:\s*\n?', '', description, count=1, flags=re.IGNORECASE).strip()
                    if orientation:
                        orientation = re.sub(r'^Description:\s*\n?', '', orientation, count=1, flags=re.IGNORECASE).strip()

                    # [LOCAL-26] [LOCAL-295] Validate: classify description as placeholder/short/normal
                    _leak_class, _leak_detail = _classify_placeholder_leak(description)
                    if _leak_class == "placeholder":
                        # Log verbatim rejected text for diagnosis
                        _rejected_wc = len(description.split()) if description else 0
                        print(f"  [LOCAL-295] Stop {stop_num}: PLACEHOLDER REJECTED (reason: {_leak_detail})")
                        print(f"  [LOCAL-295]   verbatim ({_rejected_wc} words): {repr(description[:200])}")
                        if _attempt < _max_retries:
                            # [LOCAL-295] Vary the request: bump temperature to avoid identical retry
                            description_data["temperature"] = min(0.7 + 0.15 * (_attempt + 1), 1.0)
                            print(f"  [LOCAL-26] Stop {stop_num}: placeholder leak detected (attempt {_attempt+1}), retrying (temp={description_data['temperature']:.2f})...")
                            continue  # retry with varied temperature
                        else:
                            # All retries exhausted — produce honest short description, never ship placeholder
                            print(f"  [LOCAL-26] Stop {stop_num}: placeholder leak persists after {_max_retries+1} attempts, using fallback")
                            description = f"{poi_name} — an exhibit at this venue. Detailed information was not available at generation time."

                    # [LOCAL-415] LLM refusal gate — detect meta-responses (model apologising,
                    # referencing constraints, refusing to generate). These must NEVER ship.
                    _is_refusal, _refusal_match = _detect_llm_refusal(description)
                    if _is_refusal and _leak_class != "placeholder":
                        _rejected_wc = len(description.split()) if description else 0
                        print(f"  [LOCAL-415] Stop {stop_num}: LLM REFUSAL DETECTED — matched: '{_refusal_match}'")
                        print(f"  [LOCAL-415]   verbatim ({_rejected_wc} words): {repr(description[:300])}")
                        if _attempt < _max_retries:
                            # Retry with higher temperature and explicit "do not apologize" reinforcement
                            description_data["temperature"] = min(0.7 + 0.2 * (_attempt + 1), 1.0)
                            # [LOCAL-415] Add a system-level override to prevent refusal on retry
                            if len(description_data.get("messages", [])) > 0:
                                description_data["messages"].append({
                                    "role": "user",
                                    "content": (
                                        "Your previous response was a refusal/apology instead of content. "
                                        "You MUST produce a description of the artwork/exhibit using the "
                                        "reference material provided. Do NOT apologize, do NOT reference "
                                        "constraints, do NOT address the listener about your own limitations. "
                                        "Write the tour narration directly."
                                    ),
                                })
                            print(f"  [LOCAL-415] Stop {stop_num}: refusal detected (attempt {_attempt+1}), "
                                  f"retrying with anti-refusal reinforcement (temp={description_data['temperature']:.2f})...")
                            continue  # retry
                        else:
                            # All retries exhausted — fail loudly with diagnostic, never ship refusal
                            print(f"  [LOCAL-415] Stop {stop_num}: REFUSAL PERSISTS after {_max_retries+1} attempts — "
                                  f"using fallback (NEVER shipping model apology as tour text)")
                            # [LOCAL-422] Use resolve_final_description — the single call site
                            # for stub-exclusion + material-fallback decision.
                            _material_ctx = {
                                'poi_name': poi_name, 'artist': artist,
                                'matched_work': _matched_work,
                                'credit_line': _credit_line_for_stop,
                                'candidate_specifics': _candidate_specifics,
                            }
                            description = resolve_final_description(
                                _attempts_for_resolution, _material_ctx)
                            print(f"  [LOCAL-422] Stop {stop_num}: resolved final description "
                                  f"({len(description.split())} words)")
                            # Mark as non-refusal for downstream (it's now our honest fallback)
                            _is_refusal = False

                    elif _leak_class == "short_valid":
                        # [LOCAL-295] Short but valid prose — keep it. Do NOT retry identically.
                        # This is thin corpus, not a generation failure.
                        print(f"  [LOCAL-295] Stop {stop_num}: SHORT BUT VALID — keeping ({_leak_detail} words, corpus likely thin)")
                        print(f"  [LOCAL-295]   verbatim: {repr(description[:300])}")
                        # Reset temperature in case it was bumped by a prior retry
                        description_data["temperature"] = 0.7

                    # [LOCAL-417] POSITIVE ASSERTION GATE (D353): assert what the text IS,
                    # not what it must not say. A stop must:
                    #   1. Name its own subject (the work/exhibit the stop is about)
                    #   2. State at least one concrete fact about it
                    #   3. Address the listener, never the operator — no second-person
                    #      instructions about "your description", no "notify me", no
                    #      references to requirements or constraints
                    # This survives rephrasing; a string denylist does not.
                    # Runs AFTER refusal gate and placeholder gate — only on text that
                    # passed those checks and isn't already a fallback.
                    if (description and _leak_class != "placeholder" and not _is_refusal
                            and not description.startswith(f"{poi_name} — located in this gallery")
                            and not description.startswith(f"{poi_name} — an exhibit")):
                        _417_gate_pass = True
                        _417_gate_failures = []

                        # Check 1: text names its subject (work title or a significant word from it)
                        _417_desc_lower = description.lower()
                        _417_poi_lower = poi_name.lower()
                        _417_poi_words = [w for w in re.findall(r'\b[a-z]{3,}\b', _417_poi_lower)
                                          if w not in ('the', 'and', 'for', 'from', 'with', 'that', 'this')]
                        _417_subject_named = (_417_poi_lower in _417_desc_lower or
                                             any(w in _417_desc_lower for w in _417_poi_words))
                        if not _417_subject_named:
                            _417_gate_pass = False
                            _417_gate_failures.append(f"subject not named (expected '{poi_name}' or significant word)")

                        # Check 2: at least one concrete fact (a date, number, proper noun
                        # beyond the title, or specific material/technique)
                        _417_has_fact = bool(re.search(
                            r'\b(?:1[0-9]{3}|20[0-2][0-9])\b'  # year (1000-2029)
                            r'|\b\d+\s*(?:cm|inches|feet|meters|ft|in)\b'  # measurement
                            r'|\b\d{2,}[,.]?\d*\s*(?:works?|objects?|pieces?|items?|artifacts?)\b'  # collection count
                            r'|\b(?:oil on canvas|bronze|marble|lithograph|watercolor|fresco|'
                            r'tempera|etching|woodcut|ceramic|terracotta|limestone|granite)\b'  # material
                            r'|\b(?:donated|acquired|commissioned|exhibited|installed|founded|opened'
                            r'|built|constructed|designed|crafted|created)\s+(?:in|by|for)\b'  # provenance/creation verb
                            r'|\b(?:17th|18th|19th|20th|21st)[\s-]+century\b',  # century reference (with hyphen)
                            description, re.IGNORECASE
                        ))
                        if not _417_has_fact:
                            _417_gate_pass = False
                            _417_gate_failures.append("no concrete fact (date, measurement, material, or provenance)")

                        # Check 3: addresses listener, not operator — no operator-directed language
                        _417_operator_patterns = re.compile(
                            r'\byour (?:description|text|narrative|response|prompt|request)\b'
                            r'|\bnotify me\b'
                            r'|\brequire(?:s|d)? further assistance\b'
                            r'|\bensure to include\b'
                            r'|\bmissing required\b'
                            r'|\bspecified individuals\b'
                            r'|\byour (?:instructions?|requirements?|constraints?)\b'
                            r'|\bprovide (?:more|the|additional) (?:details?|information|context)\b'
                            r'|\bin your (?:narrative|description|text)\b',
                            re.IGNORECASE
                        )
                        _417_operator_match = _417_operator_patterns.search(description)
                        if _417_operator_match:
                            _417_gate_pass = False
                            _417_gate_failures.append(f"operator-directed language: '{_417_operator_match.group(0)}'")

                        if not _417_gate_pass:
                            print(f"  [LOCAL-417] Stop {stop_num}: POSITIVE GATE FAILED — {_417_gate_failures}")
                            print(f"  [LOCAL-417]   verbatim: {repr(description[:300])}")
                            # [LOCAL-420] Save gate-rejected text as _best_description candidate.
                            # It failed the gate but it IS real prose — better than a stub or
                            # material fallback. Track it so we can fall back to it on final failure.
                            if description and not _is_stub_text(description):
                                _cur_wc = len(description.split())
                                _best_wc = _best_description[2] if _best_description else 0
                                if _cur_wc > _best_wc:
                                    _best_description = (orientation, description, _cur_wc, tokens_used, call_cost)
                            # [LOCAL-422] Accumulate for resolve_final_description
                            _attempts_for_resolution.append({
                                'description': description, 'orientation': orientation,
                                'word_count': len(description.split()) if description else 0,
                                'tokens_used': tokens_used, 'call_cost': call_cost,
                            })
                            if _attempt < _max_retries:
                                description_data["temperature"] = min(0.7 + 0.2 * (_attempt + 1), 1.0)
                                print(f"  [LOCAL-417] Stop {stop_num}: retrying (attempt {_attempt+1}, "
                                      f"temp={description_data['temperature']:.2f})...")
                                continue  # retry
                            else:
                                print(f"  [LOCAL-417] Stop {stop_num}: GATE FAILED after {_max_retries+1} attempts — "
                                      f"using fallback (never shipping operator-directed text)")
                                # [LOCAL-422] Use resolve_final_description — the single call site
                                # for stub-exclusion + material-fallback decision.
                                _material_ctx = {
                                    'poi_name': poi_name, 'artist': artist,
                                    'matched_work': _matched_work,
                                    'credit_line': _credit_line_for_stop,
                                    'candidate_specifics': _candidate_specifics,
                                }
                                description = resolve_final_description(
                                    _attempts_for_resolution, _material_ctx)
                                print(f"  [LOCAL-422] Stop {stop_num}: resolved final description "
                                      f"({len(description.split())} words)")

                    # [LOCAL-394] Track best valid description — a stop is NEVER dropped.
                    # Save every non-placeholder description; keep the longest one.
                    # [LOCAL-420] The stub must never become _best_description — exclude it.
                    if description and _leak_class != "placeholder" and not _is_stub_text(description):
                        _cur_wc = len(description.split())
                        _best_wc = _best_description[2] if _best_description else 0
                        if _cur_wc > _best_wc:
                            _best_description = (orientation, description, _cur_wc, tokens_used, call_cost)

                    # [LOCAL-422] Accumulate for resolve_final_description
                    if description and _leak_class != "placeholder":
                        _attempts_for_resolution.append({
                            'description': description, 'orientation': orientation,
                            'word_count': len(description.split()) if description else 0,
                            'tokens_used': tokens_used, 'call_cost': call_cost,
                        })

                    # [LOCAL-393] Word-count floor: if output is real prose but below 120 words,
                    # retry ONCE asking for more detail. If still below after retry, keep it
                    # and log — thin grounded material is an honest outcome.
                    if description and _leak_class != "placeholder":
                        _wc_floor_count = len(description.split())
                        if _wc_floor_count < 120 and _attempt < _max_retries:
                            print(f"  [LOCAL-393] Stop {stop_num}: WORD FLOOR — {_wc_floor_count} words < 120, "
                                  f"retrying (attempt {_attempt+2}/{_max_retries+1})")
                            # Append a reinforcement message asking to expand
                            description_data["messages"].append({
                                "role": "user",
                                "content": (
                                    f"Your response was only {_wc_floor_count} words. The MINIMUM is 120 words. "
                                    "Expand by discussing the artistic form, historical context, or collaboration "
                                    "details you can verify from the fact sheet. Do NOT invent details — use what "
                                    "you know and acknowledge gaps honestly. Rewrite the full description."
                                ),
                            })
                            description_data["temperature"] = min(0.7 + 0.1 * (_attempt + 1), 0.95)
                            continue  # retry
                        elif _wc_floor_count < 120:
                            print(f"  [LOCAL-394] stop='{poi_name}' below_floor words={_wc_floor_count} "
                                  f"— kept (never dropped)")

                    # [LOCAL-391] Required beat retry: if assigned beats are missing
                    # from the output, retry ONCE with the missing names explicitly
                    # called out. If still missing after retry, log beat_unrecoverable.
                    # [LOCAL-417] ONLY check beats whose names were NOT suppressed
                    # (i.e., only those the prompt actually demanded). Suppressed names
                    # have no snippet evidence — retrying for them is pointless and wastes
                    # the model's context on unsatisfiable constraints.
                    if (_storied_mode and _story_beats_per_stop
                            and idx < len(_story_beats_per_stop)
                            and _story_beats_per_stop[idx]
                            and description and not description.startswith('[')):
                        try:
                            from story_beat_injector import (
                                check_required_beats_present,
                                build_beat_retry_prompt_supplement,
                                scrub_unfilled_roles,
                            )
                            _beat_found, _beat_missing = check_required_beats_present(
                                description, _story_beats_per_stop[idx]
                            )
                            # [LOCAL-417] Filter out suppressed names — never retry for them
                            if _417_suppressed_beat_names and _beat_missing:
                                _beat_missing = [
                                    name for name in _beat_missing
                                    if name not in _417_suppressed_beat_names
                                ]
                            # [LOCAL-391] Scrub unfilled roles ('with publisher' → person name)
                            description, _role_subs = scrub_unfilled_roles(
                                description, _story_beats_per_stop[idx]
                            )
                            if _role_subs > 0:
                                print(f"  [LOCAL-391] Stop {stop_num}: scrubbed {_role_subs} unfilled role(s)")
                                # Re-check after scrub (the name may now be present)
                                _beat_found, _beat_missing = check_required_beats_present(
                                    description, _story_beats_per_stop[idx]
                                )
                                # [LOCAL-417] Re-filter suppressed names after re-check
                                if _417_suppressed_beat_names and _beat_missing:
                                    _beat_missing = [
                                        name for name in _beat_missing
                                        if name not in _417_suppressed_beat_names
                                    ]

                            if _beat_missing and _attempt < _max_retries:
                                # Retry: add the missing-beat supplement to the prompt
                                _retry_supplement = build_beat_retry_prompt_supplement(
                                    _beat_missing, _story_beats_per_stop[idx]
                                )
                                # Append to messages (user role reinforcement)
                                description_data["messages"].append({
                                    "role": "user",
                                    "content": _retry_supplement,
                                })
                                description_data["temperature"] = min(0.7 + 0.15 * (_attempt + 1), 1.0)
                                print(f"  [LOCAL-391] Stop {stop_num}: BEAT RETRY — missing {_beat_missing}, "
                                      f"retrying (attempt {_attempt+2}/{_max_retries+1})")
                                continue  # retry within the _attempt loop
                            elif _beat_missing:
                                # Exhausted retries — log as unrecoverable
                                for _missing_name in _beat_missing:
                                    print(f"  [LOCAL-391] Stop {stop_num}: beat_unrecoverable "
                                          f"name='{_missing_name}' — never fabricate, moving on")
                            # else: all beats present, proceed normally
                        except ImportError:
                            pass  # story_beat_injector not available — skip
                        except Exception as _beat_retry_err:
                            print(f"  [LOCAL-391] Stop {stop_num}: beat retry check error (non-fatal): {_beat_retry_err}")

                    # [LOCAL-431] Story sentence count enforcement: if the description has
                    # fewer than 3 story sentences (named person + story verb + consequence),
                    # retry with an explicit demand for narrative structure. The gate at
                    # line ~11143 runs AFTER assembly and is informational; this retry runs
                    # DURING generation and gives the LLM a second chance to write stories.
                    # Explicitly forbidden: lowering min_story_sentences or loosening the
                    # classifier (D376). This retry asks the model to restructure, not to
                    # weaken the bar.
                    if (_storied_mode and tour_category == 'museum'
                            and description and not description.startswith('[')
                            and _attempt < _max_retries):
                        try:
                            from story_gate import extract_story_sentences, is_story_sentence
                            _l431_story_sents = extract_story_sentences(description)
                            _l431_story_count = len(_l431_story_sents)
                            if _l431_story_count < 3:
                                # [LOCAL-432] Build a retry supplement that:
                                # 1. Names the exact deficit count
                                # 2. Shows rejected sentences with reasons
                                # 3. Names available people from beats
                                _l431_needed = 3 - _l431_story_count
                                import re as _l432_re

                                # Identify rejected sentences and why they failed
                                _l432_all_sents = _l432_re.split(r'(?<=[.!?])\s+', description.strip())
                                _l432_rejected = []
                                for _s in _l432_all_sents:
                                    if _s and len(_s) >= 30 and not is_story_sentence(_s):
                                        # Diagnose why it failed
                                        from story_gate import _STORY_VERB_PATTERNS, _PERSON_NAME_PATTERN, _NON_STORY_MARKERS
                                        _has_name = bool(_PERSON_NAME_PATTERN.search(_s))
                                        _has_verb = bool(_STORY_VERB_PATTERNS.search(_s))
                                        _is_eval = bool(_NON_STORY_MARKERS.search(_s))
                                        if _is_eval:
                                            _reason = "evaluative/promotional — replace with action"
                                        elif not _has_name and not _has_verb:
                                            _reason = "no named person, no story verb"
                                        elif not _has_name:
                                            _reason = "no named person (add a surname)"
                                        elif not _has_verb:
                                            _reason = "no story verb (add what they DID)"
                                        else:
                                            _reason = "fails classifier (missing consequence)"
                                        _l432_rejected.append((_s[:120], _reason))

                                # Collect available people from beats for this stop
                                _l432_people_block = ""
                                if (_story_beats_per_stop and idx < len(_story_beats_per_stop)
                                        and _story_beats_per_stop[idx]):
                                    _l432_beat_people = []
                                    for _b in _story_beats_per_stop[idx]:
                                        if _b['role'] not in ('circumstance', 'stakes'):
                                            _l432_beat_people.append(
                                                f"  • {_b['person']} — {_b['action']}")
                                    if _l432_beat_people:
                                        _l432_people_block = (
                                            "\nAVAILABLE PEOPLE (from sourced research — use these):\n"
                                            + "\n".join(_l432_beat_people[:4]) + "\n"
                                        )

                                # Build the rejected-sentences block (max 4 examples)
                                _l432_rejected_block = ""
                                if _l432_rejected:
                                    _l432_rejected_lines = []
                                    for _text, _reason in _l432_rejected[:4]:
                                        _l432_rejected_lines.append(
                                            f"  ✗ \"{_text}...\" — {_reason}")
                                    _l432_rejected_block = (
                                        "\nYOUR SENTENCES THAT FAILED (do NOT repeat these shapes):\n"
                                        + "\n".join(_l432_rejected_lines) + "\n"
                                    )

                                _l431_retry_msg = (
                                    f"STORY SENTENCE DEFICIT: you wrote {_l431_story_count} story "
                                    f"sentence(s) but the minimum is 3. You need EXACTLY "
                                    f"{_l431_needed} more.\n"
                                    f"{_l432_rejected_block}"
                                    f"{_l432_people_block}\n"
                                    "A PASSING story sentence = a named person (surname) + a STORY VERB "
                                    "(commissioned, donated, chose, published, founded, insisted, collaborated, "
                                    "established, specialized, assembled, refused, persuaded, visited, met, "
                                    "produced, crafted, created) + "
                                    "a material consequence or result.\n\n"
                                    "WHAT PASSES:\n"
                                    "  • \"Schnitzer specialized in ceremonial brass for the Bavarian court, producing this instrument in 1581.\"\n"
                                    "  • \"Fischer published a study of this specific instrument in the Historic Brass Society Journal in 1989.\"\n"
                                    "  • \"Tériade commissioned Gris to illustrate the poems, resulting in 11 lithographs.\"\n\n"
                                    f"Rewrite the FULL description. It MUST contain at least 3 total "
                                    f"story sentences — {_l431_story_count} you already have plus "
                                    f"{_l431_needed} new ones. Each new sentence must name a specific "
                                    "person by surname and state what they did with a concrete outcome. "
                                    "Keep all existing verified facts. Replace evaluative prose with narrative."
                                )
                                description_data["messages"].append({
                                    "role": "user",
                                    "content": _l431_retry_msg,
                                })
                                description_data["temperature"] = min(0.7 + 0.1 * (_attempt + 1), 0.95)
                                print(f"  [LOCAL-432] Stop {stop_num}: STORY RETRY — "
                                      f"story_count={_l431_story_count} < 3, need {_l431_needed} more, "
                                      f"retrying (attempt {_attempt+2}/{_max_retries+1})")
                                continue  # retry within the _attempt loop
                        except ImportError:
                            pass  # story_gate not available
                        except Exception as _l431_err:
                            print(f"  [LOCAL-431] Stop {stop_num}: story retry error (non-fatal): {_l431_err}")

                    # [LOCAL-408] Donor name patch: if the provenance says "Gift of [Name]"
                    # and the text says "gift" or "gifted" without the donor's surname,
                    # insert the name. This handles gpt-3.5-turbo's tendency to anonymize donors.
                    if description and _credit_line_for_stop:
                        import re as _re408_donor
                        _donor_match = _re408_donor.search(
                            r'Gift of ([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+)',
                            _credit_line_for_stop
                        )
                        if _donor_match:
                            _donor_full = _donor_match.group(1)
                            _donor_surname = _donor_full.split()[-1]
                            if _donor_surname.lower() not in description.lower():
                                # Donor name missing — find "gift" or "gifted" and inject name
                                _gift_pattern = _re408_donor.compile(
                                    r'((?:a\s+)?gift(?:ed)?\s+(?:to|of|from)\s+(?:the\s+)?)',
                                    _re408_donor.IGNORECASE
                                )
                                _gift_match = _gift_pattern.search(description)
                                if _gift_match:
                                    # Replace "Gifted to the" with "a gift from [Name] to"
                                    _insert_pos = _gift_match.start()
                                    description = (
                                        description[:_insert_pos]
                                        + f"a gift from {_donor_full} to "
                                        + description[_gift_match.end():]
                                    )
                                    print(f"  [LOCAL-408] Stop {stop_num}: patched donor name "
                                          f"'{_donor_surname}' into text (was anonymized)")
                                else:
                                    # No "gift" pattern found — append a sentence
                                    description = description.rstrip()
                                    if not description.endswith('.'):
                                        description += '.'
                                    description += (
                                        f" This work entered the collection as a gift from "
                                        f"{_donor_full}."
                                    )
                                    print(f"  [LOCAL-408] Stop {stop_num}: appended donor sentence "
                                          f"'{_donor_full}' (no gift reference found to patch)")

                    # [LOCAL-31] [LOCAL-98] Post-generation metadata binding validation.
                    # If the catalogue record specified a period or material, verify
                    # they actually appear in the generated description. If not:
                    # - LOCAL-98: RETRY first (up to retry budget), with binding reinforcement
                    # - Fallback: patch missing material/period into the text
                    if _c51_period or _c51_material:
                        _desc_lower = description.lower()
                        # Check period: extract century number from catalogue period
                        _period_ok = True
                        if _c51_period:
                            import re as _re31
                            _century_match = _re31.search(r'((?:I{1,3}|IV|VI{0,3}|IX|X{0,3}I{0,3}V?)e)\s+si[eè]cle', _c51_period)
                            _year_match = _re31.match(r'^(\d{4})$', _c51_period.strip())
                            if _century_match:
                                _expected_century = _century_match.group(1).lower()
                                # Check if this century appears OR its Arabic equivalent
                                _roman_to_arabic = {'ie': '1', 'iie': '2', 'iiie': '3', 'ive': '4',
                                                    've': '5', 'vie': '6', 'viie': '7', 'viiie': '8',
                                                    'ixe': '9', 'xe': '10', 'xie': '11', 'xiie': '12',
                                                    'xiiie': '13', 'xive': '14', 'xve': '15', 'xvie': '16',
                                                    'xviie': '17', 'xviiie': '18', 'xixe': '19', 'xxe': '20'}
                                _arabic_century = _roman_to_arabic.get(_expected_century, '')
                                _ordinal_variants = []
                                if _arabic_century:
                                    _ordinal_variants = [
                                        f"{_arabic_century}th century", f"{_arabic_century}th-century",
                                        f"{_arabic_century}th cent",
                                    ]
                                    # Special ordinals
                                    if _arabic_century == '1': _ordinal_variants.extend(['1st century', '1st-century'])
                                    elif _arabic_century == '2': _ordinal_variants.extend(['2nd century', '2nd-century'])
                                    elif _arabic_century == '3': _ordinal_variants.extend(['3rd century', '3rd-century'])
                                    # [LOCAL-98] Also accept qualified variants (second half of the Xth century)
                                    _ordinal_variants.extend([
                                        f"half of the {_arabic_century}th century",
                                        f"half of the {_arabic_century}th-century",
                                        f"early {_arabic_century}th century",
                                        f"late {_arabic_century}th century",
                                    ])
                                    if _arabic_century == '1': _ordinal_variants.extend([
                                        'half of the 1st century', 'early 1st century', 'late 1st century'])
                                    elif _arabic_century == '2': _ordinal_variants.extend([
                                        'half of the 2nd century', 'early 2nd century', 'late 2nd century'])
                                    elif _arabic_century == '3': _ordinal_variants.extend([
                                        'half of the 3rd century', 'early 3rd century', 'late 3rd century'])
                                _period_found = (
                                    _expected_century in _desc_lower or
                                    _c51_period.lower() in _desc_lower or
                                    any(v in _desc_lower for v in _ordinal_variants)
                                )
                                if not _period_found:
                                    _period_ok = False
                                    print(f"  [LOCAL-98] Stop {stop_num}: catalogue period '{_c51_period}' missing from description.")
                                    if _attempt < _max_retries:
                                        print(f"  [LOCAL-98] Stop {stop_num}: retrying (attempt {_attempt+1}) with binding enforcement...")
                                        continue
                            elif _year_match:
                                # [LOCAL-98] Raw year case (e.g., "1879")
                                _expected_year = _year_match.group(1)
                                if _expected_year not in _desc_lower:
                                    _period_ok = False
                                    print(f"  [LOCAL-98] Stop {stop_num}: catalogue year '{_expected_year}' missing from description.")
                                    if _attempt < _max_retries:
                                        print(f"  [LOCAL-98] Stop {stop_num}: retrying (attempt {_attempt+1}) with binding enforcement...")
                                        continue
                            else:
                                # [LOCAL-98] Other period formats — check literal presence
                                # [LOCAL-322] Also accept _period_english (the translated form).
                                # For era names (e.g., "Époque Edo"), the LLM writes "Edo period"
                                # which won't match the French literal. Same bug shape as material.
                                _period_literal_found = (
                                    _c51_period.lower() in _desc_lower or
                                    _period_english.lower() in _desc_lower
                                )
                                # [LOCAL-322] Also try extracting key era name (e.g., "Edo" from "Époque Edo")
                                if not _period_literal_found:
                                    import re as _re322p
                                    _era_name_m = _re322p.search(r'(?:[EÉ]poque|[EÈ]re)\s+(?:d[e\']?\s*)?([\w]+)', _c51_period, _re322p.IGNORECASE)
                                    if _era_name_m:
                                        _era_keyword = _era_name_m.group(1).lower()
                                        if _era_keyword in _desc_lower:
                                            _period_literal_found = True
                                if not _period_literal_found:
                                    _period_ok = False
                                    print(f"  [LOCAL-98] Stop {stop_num}: catalogue period '{_c51_period}' missing from description.")
                                    if _attempt < _max_retries:
                                        print(f"  [LOCAL-98] Stop {stop_num}: retrying (attempt {_attempt+1}) with binding enforcement...")
                                        continue

                        # Check material
                        # [LOCAL-322] Language-aware check: compare the ENGLISH
                        # translation against English prose. If no translation
                        # exists, treat as satisfied (false pass is harmless;
                        # false fail ships broken French prose).
                        _material_ok = True
                        if _c51_material:
                            if _material_english:
                                # Check English term in description
                                if _material_english.lower() not in _desc_lower:
                                    # [LOCAL-322] Also accept common variants/synonyms
                                    # e.g., "schist" matches "grey schist", "lacquer" matches "lacquered"
                                    _mat_stem = _material_english.lower().rstrip('ed').rstrip('er')
                                    if len(_mat_stem) >= 4 and _mat_stem not in _desc_lower:
                                        _material_ok = False
                                        print(f"  [LOCAL-98] Stop {stop_num}: material '{_material_english}' (from FR '{_c51_material.split(',')[0].strip()}') missing from description.")
                                        if _attempt < _max_retries and _period_ok:
                                            print(f"  [LOCAL-98] Stop {stop_num}: retrying (attempt {_attempt+1}) for material...")
                                            continue
                                    # else: stem found (e.g., "lacquer" in "lacquered wood") — pass
                            else:
                                # [LOCAL-322] No English translation known — skip check.
                                # A false pass costs nothing; a false fail injects French.
                                print(f"  [LOCAL-322] Stop {stop_num}: no EN translation for '{_c51_material.split(',')[0].strip()}' — treating as satisfied")

                        # [LOCAL-31] [LOCAL-322] Patch missing material/period into the description
                        # (last resort after retries exhausted).
                        # LOCAL-322: patches now use ENGLISH terms and form a complete sentence.
                        if not _period_ok or not _material_ok:
                            _patch_parts = []
                            if not _material_ok and _material_english:
                                # [LOCAL-322] Use English material name, never French
                                _patch_parts.append(f"crafted from {_material_english}")
                            if not _period_ok and _c51_period:
                                # [LOCAL-322] Use _period_english (computed earlier) not raw French
                                _patch_parts.append(f"dating from the {_period_english}")
                                # Also fix any WRONG century that was detected in the text
                                if _arabic_century:
                                    # Replace wrong ordinal century with correct one
                                    _wrong_ordinal = _re31.compile(
                                        r'\b\d{1,2}(?:st|nd|rd|th)[\s-]century',
                                        _re31.IGNORECASE
                                    )
                                    _correct_ordinal = f"{_arabic_century}th-century"
                                    if _arabic_century == '1': _correct_ordinal = "1st-century"
                                    elif _arabic_century == '2': _correct_ordinal = "2nd-century"
                                    elif _arabic_century == '3': _correct_ordinal = "3rd-century"
                                    description = _wrong_ordinal.sub(_correct_ordinal, description)
                            if _patch_parts:
                                # [LOCAL-324] Call the extracted module-level helper.
                                _patch_sentence = _build_material_period_patch(
                                    material_english=_material_english if (not _material_ok and _material_english) else None,
                                    period_english=_period_english if (not _period_ok and _c51_period) else None,
                                )
                                # Insert after first sentence
                                _first_period_idx = description.find('. ')
                                if _first_period_idx > 20:
                                    description = (description[:_first_period_idx + 2]
                                                   + _patch_sentence + " "
                                                   + description[_first_period_idx + 2:].lstrip())
                                else:
                                    description = _patch_sentence + " " + description
                                print(f"  [LOCAL-31] Stop {stop_num}: patched missing metadata into description (EN: {', '.join(_patch_parts)}).")

                        # [LOCAL-31] Check for unsourced provenance assertion
                        # If no origin in catalogue, but description asserts one, flag it
                        if not _c51_origin:
                            # No catalogue origin — check if model invented one
                            _provenance_assertions = _re31.findall(
                                r'\b(Bengali|Indian|Chinese|Japanese|Thai|Cambodian|'
                                r'Vietnamese|Burmese|Tibetan|Nepalese|Korean)\s+'
                                r'(?:artwork|art|culture|tradition|heritage|civilization)',
                                description, _re31.IGNORECASE
                            )
                            if _provenance_assertions:
                                print(f"  [LOCAL-31] Stop {stop_num}: UNSOURCED PROVENANCE "
                                      f"'{_provenance_assertions[0]}' — removing assertion.")
                                for _pa in _provenance_assertions:
                                    # Replace "Bengali artwork" → "this artwork"
                                    description = _re31.sub(
                                        rf'\b{_re31.escape(_pa)}\s+(artwork|art|culture|tradition|heritage|civilization)',
                                        r'this \1',
                                        description, flags=_re31.IGNORECASE
                                    )
                        elif _c51_origin:
                            # Has catalogue origin — check if model over-asserted it as cultural identity
                            # Map French catalogue origin names to their English adjective forms
                            _origin_adjective_map = {
                                'bengale': 'bengali', 'bihar': 'bihari', 'japon': 'japanese',
                                'chine': 'chinese', 'inde': 'indian', 'corée': 'korean',
                                'cambodge': 'cambodian', 'thaïlande': 'thai', 'vietnam': 'vietnamese',
                                'birmanie': 'burmese', 'tibet': 'tibetan', 'népal': 'nepalese',
                                'indonésie': 'indonesian', 'rajasthan': 'rajasthani',
                                'tamil nadu': 'tamil', 'gandhara': 'gandharan',
                            }
                            _origin_lower = _c51_origin.lower()
                            _adj_form = _origin_adjective_map.get(_origin_lower, _origin_lower + 'i')
                            # Check for over-assertion patterns: "Bengali culture", "ancient Bengali artwork"
                            _identity_pattern = _re31.compile(
                                rf'\b(?:ancient\s+)?{_re31.escape(_adj_form)}\s+'
                                r'(?:culture|civilization|heritage|tradition|artistic\s+tradition)',
                                _re31.IGNORECASE
                            )
                            _identity_assertions = _identity_pattern.findall(description)
                            if _identity_assertions:
                                print(f"  [LOCAL-31] Stop {stop_num}: over-asserted origin "
                                      f"'{_identity_assertions[0]}' — softening to catalogued attribution.")
                                description = _identity_pattern.sub(
                                    f"the artistic traditions of the {_c51_origin} region",
                                    description
                                )

                    word_count = len(description.split())
                    print(f"Stop {stop_num} description word count: {word_count} words")

                    # [LOCAL-407] Both-sides logging: which snippet facts were offered vs used.
                    # This disciplines the pipeline — we can see exactly which concrete specifics
                    # the model received and which it chose to include (or ignore).
                    if _local402_snippets_injected and _candidate_specifics:
                        _desc_lower = description.lower()
                        _used_specifics = []
                        _ignored_specifics = []
                        for _cs in _candidate_specifics:
                            # Extract the key value from "type: value" format
                            _cs_value = _cs.split(':', 1)[-1].strip().lower()
                            # Check if any significant fragment (>3 chars) appears
                            _cs_tokens = [t for t in _cs_value.split() if len(t) > 3]
                            _found = any(t in _desc_lower for t in _cs_tokens) if _cs_tokens else False
                            if _found:
                                _used_specifics.append(_cs)
                            else:
                                _ignored_specifics.append(_cs)
                        print(f"  [LOCAL-407] Stop {stop_num} snippet-specifics audit:")
                        print(f"    offered: {len(_candidate_specifics)}")
                        print(f"    used:    {len(_used_specifics)} — {_used_specifics[:3]}")
                        print(f"    ignored: {len(_ignored_specifics)} — {_ignored_specifics[:3]}")
                    elif _local402_snippets_injected:
                        print(f"  [LOCAL-407] Stop {stop_num}: snippets injected but no candidate specifics extracted")

                    # [LOCAL-407] Artist-presence verification (fail-open log, not gate)
                    if _local402_snippets_injected and artist:
                        _artist_sn = artist.split()[-1].lower()
                        if _artist_sn and _artist_sn not in description.lower():
                            print(f"  [LOCAL-407] ⚠️ Stop {stop_num}: artist '{artist}' ABSENT from description!")

                    # [LOCAL-414] Post-generation banned-phrase scrub.
                    # The ban is in the prompt but the LLM occasionally ignores it.
                    # Rather than retry (expensive, same result), scrub the phrase
                    # from the delivered text. The phrase adds no information loss.
                    _414_BANNED_PHRASES = [
                        'invites contemplation',
                        'invites the viewer',
                        'invites us to',
                        'invites you to explore',
                        'invites you to discover',
                        'invites you to reflect',
                        'a testament to',
                        'stands as a testament',
                        'feast for the eyes',
                        'step into a world',
                        'stir the soul',
                        'pulsate with life',
                    ]
                    _414_banned_found = []
                    if description:
                        _desc_lower_414 = description.lower()
                        for _bp in _414_BANNED_PHRASES:
                            if _bp in _desc_lower_414:
                                _414_banned_found.append(_bp)
                        if _414_banned_found:
                            # Scrub: remove sentences containing banned phrases
                            import re as _re414
                            for _bp in _414_banned_found:
                                # Remove the sentence containing the banned phrase
                                _pattern = _re414.compile(
                                    r'[^.!?]*\b' + _re414.escape(_bp) + r'\b[^.!?]*[.!?]\s*',
                                    _re414.IGNORECASE
                                )
                                description = _pattern.sub('', description).strip()
                            print(f"  [LOCAL-414] Stop {stop_num}: SCRUBBED banned phrases from output: {_414_banned_found}")

                    return idx, orientation, description, word_count, tokens_used, call_cost
                else:
                    # [LOCAL-292] Retry transient failures following _PROLOG_MAX_RETRIES pattern (LOCAL-119)
                    _DESC_TRANSIENT_CODES = {429, 500, 502, 503, 504}
                    if description_response.status_code in _DESC_TRANSIENT_CODES and _attempt < _max_retries:
                        _backoff = min(2 ** (_attempt + 1), 8)  # cap at 8s
                        print(f"  [LOCAL-292] Stop {stop_num}: transient failure (HTTP {description_response.status_code}), "
                              f"retrying in {_backoff}s (attempt {_attempt + 2}/{_max_retries + 1})")
                        time.sleep(_backoff)
                        continue  # retry within the existing _attempt loop
                    print(f"Stop {stop_num} error: API returned status code {description_response.status_code}")
                    if _attempt < _max_retries:
                        print(f"  [LOCAL-292] Stop {stop_num}: non-transient failure (HTTP {description_response.status_code}), "
                              f"retrying (attempt {_attempt + 2}/{_max_retries + 1})")
                        continue  # retry once even for non-transient (covers flaky 4xx)
                    # [LOCAL-394] Never drop a stop — use best description if we have one
                    if _best_description:
                        _bo, _bd, _bwc, _bt, _bc = _best_description
                        print(f"  [LOCAL-394] Stop {stop_num}: API failed but prior valid description exists "
                              f"({_bwc} words) — kept (never dropped)")
                        return idx, _bo, _bd, _bwc, _bt, _bc
                    # [LOCAL-251] Tour-type-appropriate fallback; mark as generation failure
                    _fallback_orient = "Position yourself to best view this location." if tour_category != 'museum' else "Look for this work in the galleries."
                    return idx, _fallback_orient, f"[GENERATION_FAILED:{poi_name}]", 0, 0, 0.0

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as _net_err:
                # [LOCAL-292] Network transient — retry with backoff (follows LOCAL-119 pattern)
                if _attempt < _max_retries:
                    _backoff = min(2 ** (_attempt + 1), 8)  # cap at 8s
                    print(f"  [LOCAL-292] Stop {stop_num}: network error ({type(_net_err).__name__}), "
                          f"retrying in {_backoff}s (attempt {_attempt + 2}/{_max_retries + 1})")
                    time.sleep(_backoff)
                    continue  # retry
                print(f"Stop {stop_num} error: {str(_net_err)}")
                # [LOCAL-394] Never drop a stop — use best description if we have one
                if _best_description:
                    _bo, _bd, _bwc, _bt, _bc = _best_description
                    print(f"  [LOCAL-394] Stop {stop_num}: network error but prior valid description exists "
                          f"({_bwc} words) — kept (never dropped)")
                    return idx, _bo, _bd, _bwc, _bt, _bc
                # [LOCAL-251] Tour-type-appropriate fallback; mark as generation failure
                _fallback_orient = "Position yourself to best view this location." if tour_category != 'museum' else "Look for this work in the galleries."
                return idx, _fallback_orient, f"[GENERATION_FAILED:{poi_name}]", 0, 0, 0.0

            except Exception as e:
                # [LOCAL-292] Unexpected error — retry once (may be transient JSON parse error)
                if _attempt < _max_retries:
                    print(f"  [LOCAL-292] Stop {stop_num}: unexpected error ({type(e).__name__}: {e}), "
                          f"retrying (attempt {_attempt + 2}/{_max_retries + 1})")
                    continue  # retry
                print(f"Stop {stop_num} error: {str(e)}")
                # [LOCAL-394] Never drop a stop — use best description if we have one
                if _best_description:
                    _bo, _bd, _bwc, _bt, _bc = _best_description
                    print(f"  [LOCAL-394] Stop {stop_num}: error but prior valid description exists "
                          f"({_bwc} words) — kept (never dropped)")
                    return idx, _bo, _bd, _bwc, _bt, _bc
                # [LOCAL-251] Tour-type-appropriate fallback; mark as generation failure
                _fallback_orient = "Position yourself to best view this location." if tour_category != 'museum' else "Look for this work in the galleries."
                return idx, _fallback_orient, f"[GENERATION_FAILED:{poi_name}]", 0, 0, 0.0

        # [LOCAL-394] Safety fallback — use best description if we have one (never drop a stop)
        if _best_description:
            _bo, _bd, _bwc, _bt, _bc = _best_description
            print(f"  [LOCAL-394] Stop {stop_num}: loop exhausted but prior valid description exists "
                  f"({_bwc} words) — kept (never dropped)")
            return idx, _bo, _bd, _bwc, _bt, _bc
        # Only reach here if no valid description was ever produced
        _fallback_orient = "Position yourself to best view this location." if tour_category != 'museum' else "Look for this work in the galleries."
        return idx, _fallback_orient, f"[GENERATION_FAILED:{poi_name}]", 0, 0, 0.0

    max_workers = min(len(poi_list), 5)
    _phase5_ceiling_breached = False  # [LOCAL-326] Track mid-Phase5 breach
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # [S9/S10/S11] Pass spine_stop and fact_sheet per stop (None when not in Storied mode)
        _spine_arc = _storied_spine.get("arc", []) if _storied_mode and _storied_spine else []
        _fact_sheets_list = _storied_fact_sheets if _storied_mode and _storied_fact_sheets else []
        futures = {}
        # [LOCAL-474] Keep each stop's generation arguments so the post-gate retry
        # can re-run _generate_description for a stop the gates hollowed out. These
        # are otherwise local to this loop and unreachable 1,200 lines later.
        _regen_args_by_idx = {}
        for i, poi in enumerate(poi_list):
            spine_stop = _spine_arc[i] if i < len(_spine_arc) else None
            fact_sheet = _fact_sheets_list[i] if i < len(_fact_sheets_list) else None
            story_type = poi.get('story_type')
            _regen_args_by_idx[i] = (spine_stop, fact_sheet, story_type)
            futures[executor.submit(_generate_description, (i, poi, spine_stop, fact_sheet, story_type))] = i
        for future in as_completed(futures):
            idx, orientation, description, word_count, tokens_used, call_cost = future.result()
            poi_list[idx]["orientation"] = orientation
            # [LOCAL-22] Strip any "Stop N:" prefix that GPT echoed into description text.
            # This is the ROOT CAUSE of the stop-title corruption: GPT's description response
            # sometimes starts with "Stop N: Located at..." which, when rendered into the
            # final text file, creates a line matching ^Stop\s+\d+: — the QA regex
            # then picks it up as the stop heading instead of the real one.
            if description:
                # Strip from beginning of text AND from beginning of any line within
                description = re.sub(r'^Stop\s+\d+:\s*', '', description, flags=re.IGNORECASE | re.MULTILINE).strip()
            poi_list[idx]["description"] = description
            poi_list[idx]["word_count"] = word_count
            total_tokens += tokens_used
            total_cost += call_cost
            # [LOCAL-326] Check cost after each stop completes. On breach, mark
            # remaining stops as ungenerated but do NOT cancel already-inflight
            # futures (they were launched in parallel). The ceiling prevents
            # further phases from running — the savings is real.
            if not _phase5_ceiling_breached and total_cost > _PHASE_COST_HARD_LIMIT:
                _phase5_ceiling_breached = True
                _completed_stop_count = sum(
                    1 for p in poi_list
                    if p.get("description") and not p["description"].startswith("[GENERATION_FAILED")
                )
                print(f"[LOCAL-326] COST CEILING BREACHED during Phase 5: "
                      f"${total_cost:.4f} > ${_PHASE_COST_HARD_LIMIT:.4f} — "
                      f"{_completed_stop_count}/{len(poi_list)} stops completed")
    
    # [LOCAL-388] Post-generation: verify story beats reached the prose, log per stop
    # [LOCAL-390] NOTE: This early check is INFORMATIONAL ONLY — it runs against the
    # raw LLM output BEFORE gates (5.158 entity grounding, 5.159 form-claim, etc.)
    # and before Phase 6 assembly. The AUTHORITATIVE verification runs after full
    # assembly — see "[LOCAL-390] FINAL beat verification" below.
    if _storied_mode and _story_beats_per_stop and not _phase5_ceiling_breached:
        try:
            from story_beat_injector import verify_beats_in_output
            for _vi, _vpoi in enumerate(poi_list):
                if _vi >= len(_story_beats_per_stop):
                    break
                _vdesc = _vpoi.get('description', '')
                _vname = _vpoi.get('name', f'Stop {_vi+1}')
                _vbeats = _story_beats_per_stop[_vi]
                _vresult = verify_beats_in_output(_vbeats, _vdesc, _vname)
                _dropped_str = str(_vresult['dropped']) if _vresult['dropped'] else '[]'
                print(f"  [LOCAL-388] PRE-GATE stop='{_vname}' beats_assigned={_vresult['beats_assigned']} "
                      f"beats_in_output={_vresult['beats_in_output']} dropped={_dropped_str}")
        except Exception as _v388_err:
            print(f"  [LOCAL-388] Beat verification error (non-fatal): {_v388_err}")

    # [LOCAL-421] Story gate — verify each stop has ≥3 story sentences + named entities
    if _storied_mode and tour_category == 'museum' and not _phase5_ceiling_breached:
        try:
            from story_gate import verify_stop_story, extract_story_sentences, get_classification_cost, reset_classification_cost
            reset_classification_cost()
            print(f"\n  [LOCAL-439] STORY GATE: checking story-units per stop (D394)...")
            _l421_all_pass = True
            for _sg_i, _sg_poi in enumerate(poi_list):
                _sg_desc = _sg_poi.get('description', '')
                _sg_name = _sg_poi.get('name', f'Stop {_sg_i+1}')
                if not _sg_desc or _sg_desc.startswith('['):
                    continue

                # Get credit line for this stop
                _sg_credit = _sg_poi.get('credit_line', '')
                if not _sg_credit and _exhibition_checklist_result and hasattr(_exhibition_checklist_result, 'works'):
                    _sg_matched = match_work_for_stop(_sg_name, _exhibition_checklist_result.works)
                    if _sg_matched:
                        _sg_credit = _sg_matched.get('credit_line', '')

                _sg_result = verify_stop_story(
                    description=_sg_desc,
                    credit_line=_sg_credit,
                    stop_name=_sg_name,
                    framing_case=_framing_case,
                    venue_purpose=_framing_source_phrase if _framing_case == 'venue_purpose' else '',
                )
                _sg_status = "✓ PASS" if _sg_result['passed'] else "✗ FAIL"
                print(f"    {_sg_status} stop='{_sg_name}': story_units={_sg_result['story_unit_count']}, "
                      f"entities_ok={_sg_result['entities_present']}, "
                      f"thesis_ok={_sg_result['thesis_threaded']}")
                if not _sg_result['passed']:
                    _l421_all_pass = False
                    for _sg_f in _sg_result['failures']:
                        print(f"      → {_sg_f}")
                if _sg_result.get('interest_scores'):
                    for _is in _sg_result['interest_scores']:
                        print(f"      interest: emotional={_is['emotional_content']}, new_info={_is['new_information']}, "
                              f"deduction={_is['deduction']}, total={_is['interest_score']}")
                if _sg_result['entities_missing']:
                    print(f"      entities_missing: {_sg_result['entities_missing']}")

            _sg_cost = get_classification_cost()
            if _sg_cost['total_cost_usd'] > 0:
                print(f"  [LOCAL-439] Classification cost: ${_sg_cost['total_cost_usd']:.6f} "
                      f"(input={_sg_cost['input_tokens']}, output={_sg_cost['output_tokens']})")

            if _l421_all_pass:
                print(f"  [LOCAL-439] STORY GATE: ALL STOPS PASSED")
            else:
                print(f"  [LOCAL-439] STORY GATE: SOME STOPS FAILED (informational — does not block delivery)")
                # [LOCAL-431] Blocking wiring: when _L421_GATE_BLOCKS is True,
                # a story gate failure refuses delivery through LOCAL-365's
                # clean-fail path. Gate stays informational per LOCAL-439 spec.
                _L421_GATE_BLOCKS = os.environ.get("L421_GATE_BLOCKS", "false").lower() == "true"
                if _L421_GATE_BLOCKS:
                    # Collect per-stop failure evidence
                    _l431_failed_stops = []
                    for _sg_i2, _sg_poi2 in enumerate(poi_list):
                        _sg_desc2 = _sg_poi2.get('description', '')
                        _sg_name2 = _sg_poi2.get('name', f'Stop {_sg_i2+1}')
                        if not _sg_desc2 or _sg_desc2.startswith('['):
                            continue
                        _sg_credit2 = _sg_poi2.get('credit_line', '')
                        _sg_result2 = verify_stop_story(
                            description=_sg_desc2, credit_line=_sg_credit2,
                            stop_name=_sg_name2, framing_case=_framing_case,
                            venue_purpose=_framing_source_phrase if _framing_case == 'venue_purpose' else '',
                        )
                        if not _sg_result2['passed']:
                            _l431_failed_stops.append({
                                'stop_name': _sg_name2,
                                'story_unit_count': _sg_result2['story_unit_count'],
                                'failures': _sg_result2['failures'],
                            })
                    print(f"\n  [LOCAL-431] ⚠️  STORY GATE BLOCKING — refusing delivery")
                    for _fs in _l431_failed_stops:
                        print(f"    FAIL: {_fs['stop_name']}: story_units={_fs['story_unit_count']}")
                        for _ff in _fs['failures']:
                            print(f"      → {_ff}")
                    _LAST_CLEAN_FAIL_EVIDENCE.clear()
                    _LAST_CLEAN_FAIL_EVIDENCE.update({
                        "error_type": "story_gate_failed",
                        "failed_stops": _l431_failed_stops,
                        "reason": (
                            f"{len(_l431_failed_stops)} stop(s) have no verified story-unit. "
                            "Each stop must contain at least one story-unit of ≥3 sentences "
                            "with a named person, real actions, and an arc (D394)."
                        ),
                    })
                    _LAST_GENERATION_COST = {
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "cache_hit": False,
                        "breakdown": {"llm": 0.0, "tts": 0.0, "search": 0.0},
                    }
                    return None, None, (None, None)
        except ImportError as _sg_err:
            print(f"  [LOCAL-439] Story gate import error (non-fatal): {_sg_err}")
        except Exception as _sg_err:
            print(f"  [LOCAL-439] Story gate error (non-fatal): {_sg_err}")

    # [LOCAL-423] STORY VERIFICATION — Michael's Step 4: verify claims against sources.
    # Verification GATES selection (runs after generation, before delivery).
    # Every load-bearing claim must trace to a retrieved source.
    # Entity disambiguation: exclude wrong-person snippets.
    # Self-contradiction detection: "15 lithographs" + "40 lithographs" = reject.
    _l423_verification_results = {}
    if _storied_mode and tour_category == 'museum' and not _phase5_ceiling_breached:
        try:
            from story_verifier import verify_story_candidate, disambiguate_snippets
            print(f"\n  [LOCAL-423] STORY VERIFICATION: checking claims against sources...")
            _l423_all_pass = True
            _l423_any_rejected = False

            for _sv_i, _sv_poi in enumerate(poi_list):
                _sv_desc = _sv_poi.get('description', '')
                _sv_name = _sv_poi.get('name', f'Stop {_sv_i+1}')
                if not _sv_desc or _sv_desc.startswith('['):
                    continue

                # Get credit line for this stop
                _sv_credit = _sv_poi.get('credit_line', '')
                if not _sv_credit and _exhibition_checklist_result and hasattr(_exhibition_checklist_result, 'works'):
                    _sv_matched = match_work_for_stop(_sv_name, _exhibition_checklist_result.works)
                    if _sv_matched:
                        _sv_credit = _sv_matched.get('credit_line', '')

                # Get the snippets that were used to generate this stop
                _sv_snippets = []
                if _DIRECT_SNIPPETS_PER_STOP:
                    _sv_snippets = _DIRECT_SNIPPETS_PER_STOP.get(_sv_name, [])
                    if not _sv_snippets:
                        _sv_snippets = _DIRECT_SNIPPETS_PER_STOP.get(f"__stop_{_sv_i}__", [])

                # [LOCAL-427/428] Inject venue page text as a verification snippet when
                # the source is the venue itself (not a third-party). Decision logic
                # is now at module scope as should_inject_venue_snippet() — testable.
                _venue_inject = should_inject_venue_snippet(_exhibition_checklist_result, _sv_name)
                if _venue_inject['inject']:
                    _sv_snippets = [_venue_inject['snippet']] + list(_sv_snippets)
                    if _sv_i == 0:
                        print(f"    [LOCAL-427] Venue page text injected as verification source "
                              f"({_venue_inject['reason']})")

                _sv_result = verify_stop_claims(
                    story_text=_sv_desc,
                    snippets=_sv_snippets,
                    credit_line=_sv_credit,
                    stop_name=_sv_name,
                )

                _l423_verification_results[_sv_name] = _sv_result
                _sv_status = "✓ PASS" if _sv_result['passed'] else "✗ FAIL"
                print(f"    {_sv_status} stop='{_sv_name}': "
                      f"claims={_sv_result['claims_extracted']}, "
                      f"sourced={_sv_result['claims_sourced']}, "
                      f"unsourced={_sv_result['claims_unsourced']}, "
                      f"contradicted={_sv_result['claims_contradicted']}")

                if not _sv_result['passed']:
                    _l423_all_pass = False
                    _l423_any_rejected = True
                    for _sv_reason in _sv_result['rejection_reasons'][:5]:
                        print(f"      → {_sv_reason}")

                if _sv_result['evidence']:
                    print(f"      evidence ({len(_sv_result['evidence'])} sourced claims):")
                    for _ev in _sv_result['evidence'][:3]:
                        print(f"        claim='{_ev['claim_text']}' ← {_ev['source_url'][:60]}")

                if _sv_result['disambiguation_excluded']:
                    print(f"      disambiguation: excluded {len(_sv_result['disambiguation_excluded'])} snippets")
                    for _dex in _sv_result['disambiguation_excluded']:
                        print(f"        • '{_dex['title'][:50]}': {_dex['reason']}")

            if _l423_all_pass:
                print(f"  [LOCAL-423] STORY VERIFICATION: ALL STOPS PASSED — every extracted claim is sourced")
            else:
                print(f"  [LOCAL-423] STORY VERIFICATION: SOME STOPS HAVE UNSOURCED CLAIMS")
                print(f"  [LOCAL-423] Unsourced claims will be stripped from delivered text")

                # Strip unsourced claims from the delivered text
                # (Michael's rule: "A claim with no source must not ship")
                for _strip_name, _strip_result in _l423_verification_results.items():
                    if _strip_result['passed']:
                        continue
                    # Find the corresponding POI and remove unsourced sentences
                    for _strip_poi in poi_list:
                        if _strip_poi.get('name') != _strip_name:
                            continue
                        _strip_desc = _strip_poi.get('description', '')
                        if not _strip_desc:
                            break
                        # Remove sentences containing unsourced claims
                        _sentences = re.split(r'(?<=[.!?])\s+', _strip_desc.strip())
                        _kept = []
                        _removed = []
                        _unsourced_texts = {d['text'].lower() for d in _strip_result['unsourced_details']}
                        _contradiction_texts = set()
                        for _ct1, _ct2, _ in _strip_result['contradictions']:
                            _contradiction_texts.add(_ct1.lower())
                            _contradiction_texts.add(_ct2.lower())

                        for _sent in _sentences:
                            _sent_lower = _sent.lower()
                            _has_unsourced = any(ut in _sent_lower for ut in _unsourced_texts)
                            _has_contradiction = any(ct in _sent_lower for ct in _contradiction_texts)
                            if _has_unsourced or _has_contradiction:
                                _removed.append(_sent)
                            else:
                                _kept.append(_sent)

                        if _removed:
                            _strip_poi['description'] = ' '.join(_kept)
                            print(f"    [LOCAL-423] Stripped {len(_removed)} sentence(s) from '{_strip_name}':")
                            for _rm in _removed:
                                print(f"      ✗ \"{_rm[:100]}\"")
                        break

        except ImportError as _sv_err:
            print(f"  [LOCAL-423] Story verifier import error (non-fatal): {_sv_err}")
        except Exception as _sv_err:
            print(f"  [LOCAL-423] Story verifier error (non-fatal): {_sv_err}")

    # [LOCAL-474] Snapshot every stop's prose BEFORE the deletion-gate chain runs.
    # The retry after the chain diffs against this to learn exactly which sentences
    # were removed, without having to modify all ten gates to report in a common
    # format. Same technique as gate_fp_probe.py.
    _pre_gate_prose = {i: (p.get('description') or '') for i, p in enumerate(poi_list)}

    # [LOCAL-394] 120-word floor enforcement — log stops under minimum but NEVER drop them.
    # The floor is a retry trigger inside _generate_description, not a post-generation filter.
    if _storied_mode and not _phase5_ceiling_breached:
        _WORD_FLOOR = 120
        for _fi, _fpoi in enumerate(poi_list):
            _fdesc = _fpoi.get('description', '')
            _fwc = len(_fdesc.split()) if _fdesc else 0
            if _fwc < _WORD_FLOOR and _fdesc and not _fdesc.startswith('['):
                print(f"  [LOCAL-394] stop='{_fpoi.get('name', f'Stop {_fi+1}')}' below_floor "
                      f"words={_fwc} — kept (never dropped)")

    # [LOCAL-326] If cost ceiling was breached during Phase 5, skip all post-processing
    # (Phase 5.1, 5.5, 5.6, 5.10 etc.) and assemble a partial tour immediately.
    # Stops that completed before the breach have full descriptions; others don't.
    if _phase5_ceiling_breached:
        _completed_stops = [
            p for p in poi_list
            if p.get("description") and not p["description"].startswith("[GENERATION_FAILED")
        ]
        _n_completed = len(_completed_stops)
        print(f"[LOCAL-326] Assembling partial tour: {_n_completed}/{len(poi_list)} stops have descriptions")
        _partial_header = (
            f"Step-by-Step Audio Guided Tour: {location}\n"
            f"Tour-Category: {tour_category}\n"
            f"[PARTIAL TOUR — {_n_completed} of {len(poi_list)} stops generated; "
            f"cost ceiling reached during Phase 5 (${total_cost:.4f} > ${_PHASE_COST_HARD_LIMIT:.4f})]\n\n"
        )
        _partial_body = ""
        for _pi, _pp in enumerate(poi_list):
            _stop_name = _pp.get('name', 'Unknown')
            _partial_body += f"Stop {_pi + 1}: {_stop_name}\n"
            if _pp.get('address'):
                _partial_body += f"Address: {_pp['address']}\n"
            if _pp.get('orientation'):
                _partial_body += f"\n{_pp['orientation']}\n"
            _desc = _pp.get('description', '')
            if _desc and not _desc.startswith("[GENERATION_FAILED"):
                _partial_body += f"\n{_desc}\n"
            else:
                _partial_body += "\n[Description not generated — cost ceiling reached]\n"
            _partial_body += "\n"
        _partial_tour = _partial_header + _partial_body
        _LAST_GENERATION_COST = {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "cache_hit": False,
            "breakdown": {"llm": total_cost, "tts": 0.0, "search": 0.0},
        }
        _LAST_POI_LIST = list(poi_list)
        if output_file:
            with open(output_file, "w", encoding="utf-8") as _pf:
                _pf.write(_partial_tour)
        return _partial_tour, output_file, first_poi_coordinates

    # -------- [LOCAL-192] PHASE 5.1: Style validation + per-paragraph retry --------
    # D63: prompt instruction alone does not fix style faults. Validate generated
    # text and re-ask for paragraphs that violate error-severity rules (R1–R4).
    # R7 is warning-only (D62) — does NOT trigger retry.
    # One retry per paragraph max. If retry also fails, keep the better of two.
    # Behind DISABLE_STYLE_RETRY=1 flag for A/B measurement.
    _style_retry_disabled = os.environ.get('DISABLE_STYLE_RETRY', '').strip() == '1'
    if _style_retry_disabled:
        print(f"\n  [LOCAL-192] Style retry DISABLED by DISABLE_STYLE_RETRY=1 env var")
    else:
        print(f"\n  [LOCAL-192] PHASE 5.1: Style validation + per-paragraph retry...")
        _style_retry_count = 0
        _style_retry_tokens = 0
        _style_retry_cost = 0.0
        _style_retry_successes = 0
        _style_retry_failures = 0

        # Import the validator (same one used in measurement — D55: do not modify it)
        # [LOCAL-192 fix 1] Validator now lives at repo root (same directory as this file),
        # so it is importable without sys.path manipulation — works inside Docker too.
        try:
            from style_validator_detector import validate_paragraph as _sv_validate_paragraph
        except ImportError:
            _sv_validate_paragraph = None
            print(f"  [LOCAL-192] WARNING: style_validator_detector not importable — retry skipped")

        if _sv_validate_paragraph:
            _ERROR_SEVERITIES = {'error'}  # Only error-severity triggers retry (not 'warning')

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue  # Skip failed/placeholder descriptions

                _stop_num = _si + 1
                _poi_name = _poi.get('name', f'Stop {_stop_num}')

                # Split description into paragraphs — keep ALL segments for reassembly,
                # but only validate content paragraphs (>30 chars). Short segments
                # (assembly lines, spacing) pass through unchanged.
                # [LOCAL-192 fix 2] Previous code dropped ≤30-char paragraphs on reassembly.
                _all_segments = [p for p in _desc.split('\n\n') if p.strip()]
                if not _all_segments:
                    continue

                _new_paragraphs = []
                _stop_had_retry = False
                _stop_retry_tokens = 0
                _stop_retry_cost = 0.0

                for _pi, _seg in enumerate(_all_segments):
                    _para = _seg.strip()
                    # Short segments: keep as-is, do not validate
                    if len(_para) <= 30:
                        _new_paragraphs.append(_para)
                        continue

                    _result = _sv_validate_paragraph(_para)

                    # Check for ERROR-severity findings only (R7 is warning → skip)
                    _error_findings = [f for f in _result.get('findings', [])
                                       if f.get('severity') in _ERROR_SEVERITIES]

                    if not _error_findings or _result.get('is_navigation'):
                        _new_paragraphs.append(_para)
                        continue

                    # ── This paragraph has error-severity violations → retry ──
                    _style_retry_count += 1
                    _stop_had_retry = True

                    # Build the retry prompt: tell the model exactly which rule it broke
                    # and quote the offending sentence. Fabrication guard (D50): only
                    # rewrite using what's already in the paragraph.
                    _violated_rules = set(f['rule_id'] for f in _error_findings)
                    _offending_sentences = [f['sentence'][:150] for f in _error_findings[:3]]

                    _retry_prompt = f"""Rewrite the following paragraph to fix style violations.

PARAGRAPH TO REWRITE:
\"\"\"{_para}\"\"\"

VIOLATIONS FOUND:
"""
                    for _ef in _error_findings[:3]:
                        _retry_prompt += f"- Rule {_ef['rule_id']}: {_ef['suggestion']}\n"
                        _retry_prompt += f"  Offending sentence: \"{_ef['sentence'][:150]}\"\n"

                    _retry_prompt += f"""
REWRITE RULES (all mandatory):
1. Fix the violations listed above — remove prescribed feelings, imperatives, suggestive exploration, or questions as indicated.
2. DO NOT ADD ANY NEW FACTS, claims, dates, names, or information not already present in the paragraph above. Rewrite using ONLY what is already stated. Adding facts risks fabrication.
3. Keep the same approximate length (±20%).
4. Keep the same subject matter and narrative flow.
5. Write declarative prose only — state what IS, not what the listener should feel or do.
6. Return ONLY the rewritten paragraph text. No explanations, no headers, no "Here is the rewrite:".
"""

                    # LEAD, merging LOCAL-192 into LOCAL-194: the rewriter must be
                    # the same model as the writer, or a model A/B silently compares
                    # new-model prose against old-model repairs.
                    _retry_data = {
                        "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                        "messages": [
                            {"role": "system", "content": "You are a copy editor fixing style violations in audio tour narration. You rewrite only — never add new information."},
                            {"role": "user", "content": _retry_prompt}
                        ],
                        "temperature": 0.3,  # Lower temp for more faithful rewrite
                        "max_tokens": 500
                    }

                    try:
                        _retry_resp = requests.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers=headers,
                            data=json.dumps(_retry_data)
                        )

                        if _retry_resp.status_code == 200:
                            _retry_result = _retry_resp.json()
                            _retry_text = _retry_result["choices"][0]["message"]["content"].strip()
                            _retry_tok = _retry_result["usage"]["total_tokens"]
                            _retry_c = _tour_llm_cost(_retry_tok)
                            _style_retry_tokens += _retry_tok
                            _style_retry_cost += _retry_c
                            _stop_retry_tokens += _retry_tok
                            _stop_retry_cost += _retry_c

                            # Strip any preamble the model might add
                            _retry_text = re.sub(r'^(?:Here (?:is|\'s) the rewrite[d paragraph]*[:\s]*|Rewritten paragraph[:\s]*)', '', _retry_text, flags=re.IGNORECASE).strip()
                            # Strip wrapping quotes if present
                            if _retry_text.startswith('"""') and _retry_text.endswith('"""'):
                                _retry_text = _retry_text[3:-3].strip()
                            elif _retry_text.startswith('"') and _retry_text.endswith('"'):
                                _retry_text = _retry_text[1:-1].strip()

                            # Validate the retry
                            _retry_validation = _sv_validate_paragraph(_retry_text)
                            _retry_errors = [f for f in _retry_validation.get('findings', [])
                                             if f.get('severity') in _ERROR_SEVERITIES]

                            if not _retry_errors:
                                # Retry is clean — use it
                                _new_paragraphs.append(_retry_text)
                                _style_retry_successes += 1
                                print(f"  [LOCAL-192] Stop {_stop_num} para {_pi+1}: retry FIXED ({', '.join(_violated_rules)})")
                            else:
                                # Retry also has errors — keep whichever has fewer
                                if len(_retry_errors) < len(_error_findings):
                                    _new_paragraphs.append(_retry_text)
                                    _style_retry_successes += 1  # partial improvement
                                    print(f"  [LOCAL-192] Stop {_stop_num} para {_pi+1}: retry IMPROVED ({len(_error_findings)}→{len(_retry_errors)} errors)")
                                else:
                                    _new_paragraphs.append(_para)  # keep original
                                    _style_retry_failures += 1
                                    print(f"  [LOCAL-192] Stop {_stop_num} para {_pi+1}: retry FAILED — keeping original ({', '.join(_violated_rules)})")
                        else:
                            # API error — keep original
                            _new_paragraphs.append(_para)
                            _style_retry_failures += 1
                            print(f"  [LOCAL-192] Stop {_stop_num} para {_pi+1}: retry API error {_retry_resp.status_code} — keeping original")
                    except Exception as _retry_err:
                        _new_paragraphs.append(_para)
                        _style_retry_failures += 1
                        print(f"  [LOCAL-192] Stop {_stop_num} para {_pi+1}: retry exception — keeping original: {_retry_err}")

                # Reassemble description if any paragraph was retried
                if _stop_had_retry:
                    poi_list[_si]["description"] = '\n\n'.join(_new_paragraphs)
                    # [LOCAL-192 fix 3] Add only THIS stop's retry cost, not the
                    # cumulative total (previous code was quadratic double-counting).
                    total_tokens += _stop_retry_tokens
                    total_cost += _stop_retry_cost

            # Summary
            print(f"  [LOCAL-192] Style retry summary: {_style_retry_count} paragraphs retried, "
                  f"{_style_retry_successes} fixed/improved, {_style_retry_failures} kept original")
            print(f"  [LOCAL-192] Retry cost: ${_style_retry_cost:.4f} ({_style_retry_tokens} tokens)")

    # -------- [LOCAL-255] PHASE 5.13: R1 imperative rewrite --------
    # Michael scored R1 2/5 twice. At 36% of paragraphs, deletion would gut every
    # tour. Rewrite first (deterministic rules + LLM fallback); delete only pure
    # instructions with no content. Behind DISABLE_R1_REWRITE=1 flag.
    _r1_rewrite_disabled = os.environ.get('DISABLE_R1_REWRITE', '').strip() == '1'
    if _r1_rewrite_disabled:
        print(f"\n  [LOCAL-255] R1 rewrite DISABLED by DISABLE_R1_REWRITE=1 env var")
    else:
        print(f"\n  [LOCAL-255] PHASE 5.13: R1 imperative rewrite...")
        try:
            from style_validator_detector import apply_r1_to_description as _r1_apply
        except ImportError:
            _r1_apply = None
            print(f"  [LOCAL-255] WARNING: apply_r1_to_description not importable — R1 rewrite skipped")

        if _r1_apply:
            _r1_total_rewritten = 0
            _r1_total_deleted = 0
            _r1_total_llm_tokens = 0
            _r1_stops_affected = 0

            # Get API key for LLM fallback
            _r1_api_key = api_key  # From enclosing generate_tour_text scope
            _r1_model = os.environ.get('TOUR_LLM_MODEL', 'gpt-4o-mini')

            for _si, _poi in enumerate(poi_list):
                _stop_rewritten = 0
                _stop_deleted = 0
                _stop_llm_tok = 0

                # Process description
                _desc = _poi.get('description', '')
                if _desc and not _desc.startswith('['):
                    _new_desc, _rewritten, _deleted, _llm_tok = _r1_apply(
                        _desc, api_key=_r1_api_key, model=_r1_model
                    )
                    if _rewritten > 0 or _deleted > 0:
                        poi_list[_si]['description'] = _new_desc
                        _stop_rewritten += _rewritten
                        _stop_deleted += _deleted
                        _stop_llm_tok += _llm_tok

                # Process orientation (same treatment)
                _orient = _poi.get('orientation', '')
                if _orient and not _orient.startswith('['):
                    _new_orient, _o_rewritten, _o_deleted, _o_llm_tok = _r1_apply(
                        _orient, api_key=_r1_api_key, model=_r1_model
                    )
                    if _o_rewritten > 0 or _o_deleted > 0:
                        poi_list[_si]['orientation'] = _new_orient
                        _stop_rewritten += _o_rewritten
                        _stop_deleted += _o_deleted
                        _stop_llm_tok += _o_llm_tok

                if _stop_rewritten > 0 or _stop_deleted > 0:
                    _r1_total_rewritten += _stop_rewritten
                    _r1_total_deleted += _stop_deleted
                    _r1_total_llm_tokens += _stop_llm_tok
                    _r1_stops_affected += 1
                    print(f"  [LOCAL-255] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_stop_rewritten} rewritten, {_stop_deleted} deleted")

            # Cost accounting for LLM tokens used
            if _r1_total_llm_tokens > 0:
                _r1_llm_cost = _tour_llm_cost(_r1_total_llm_tokens)
                total_tokens += _r1_total_llm_tokens
                total_cost += _r1_llm_cost
            else:
                _r1_llm_cost = 0.0

            print(f"  [LOCAL-255] R1 summary: {_r1_total_rewritten} rewritten, "
                  f"{_r1_total_deleted} deleted, "
                  f"{_r1_stops_affected} stops affected, "
                  f"LLM tokens: {_r1_total_llm_tokens} (${_r1_llm_cost:.4f})")

            # D55 safety check: if deletion > 10% of total R1 hits, warn
            _r1_total_hits = _r1_total_rewritten + _r1_total_deleted
            if _r1_total_hits > 0 and _r1_total_deleted / _r1_total_hits > 0.10:
                print(f"  [LOCAL-255] WARNING: deletion rate {_r1_total_deleted}/{_r1_total_hits} "
                      f"= {_r1_total_deleted/_r1_total_hits:.1%} exceeds 10% — "
                      f"rewriter may be failing and quietly shortening tours")

    # -------- [LOCAL-251] PHASE 5.14: R7 hallucinated-sensory deletion --------
    # Michael scored this class 1/5. R7 has fired without a deletion path since
    # LOCAL-247. Now it deletes. Behind DISABLE_R7_DELETION=1 flag. $0.00 — deterministic.
    _r7_deletion_disabled = os.environ.get('DISABLE_R7_DELETION', '').strip() == '1'
    if _r7_deletion_disabled:
        print(f"\n  [LOCAL-251] R7 deletion DISABLED by DISABLE_R7_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-251] PHASE 5.14: R7 hallucinated-sensory deletion...")
        try:
            from style_validator_detector import apply_r7_to_description as _r7_apply
        except ImportError:
            _r7_apply = None
            print(f"  [LOCAL-251] WARNING: apply_r7_to_description not importable — R7 deletion skipped")

        if _r7_apply:
            _r7_total_deleted = 0
            _r7_total_paras_emptied = 0
            _r7_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r7_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r7_total_deleted += _deleted
                    _r7_total_paras_emptied += _emptied
                    _r7_stops_affected += 1
                    print(f"  [LOCAL-251] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-251] R7 summary: {_r7_total_deleted} sentences deleted, "
                  f"{_r7_total_paras_emptied} paragraphs emptied, "
                  f"{_r7_stops_affected} stops affected")

    # -------- [LOCAL-261] PHASE 5.141: R2 question deletion --------
    # D165: R2 fires but had no path to the output. Questions (?) are always
    # wrong in narration. Behind DISABLE_R2_DELETION=1 flag. $0.00 — deterministic.
    _r2_deletion_disabled = os.environ.get('DISABLE_R2_DELETION', '').strip() == '1'
    if _r2_deletion_disabled:
        print(f"\n  [LOCAL-261] R2 deletion DISABLED by DISABLE_R2_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-261] PHASE 5.141: R2 question deletion...")
        try:
            from style_validator_detector import apply_r2_to_description as _r2_apply
        except ImportError:
            _r2_apply = None
            print(f"  [LOCAL-261] WARNING: apply_r2_to_description not importable — R2 deletion skipped")

        if _r2_apply:
            _r2_total_deleted = 0
            _r2_total_paras_emptied = 0
            _r2_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r2_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r2_total_deleted += _deleted
                    _r2_total_paras_emptied += _emptied
                    _r2_stops_affected += 1
                    print(f"  [LOCAL-261] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-261] R2 summary: {_r2_total_deleted} sentences deleted, "
                  f"{_r2_total_paras_emptied} paragraphs emptied, "
                  f"{_r2_stops_affected} stops affected")

    # -------- [LOCAL-261] PHASE 5.142: R3 suggestive-exploration deletion --------
    # D165: R3 fires but had no path to the output. "you might discover…" is
    # always wrong. Behind DISABLE_R3_DELETION=1 flag. $0.00 — deterministic.
    _r3_deletion_disabled = os.environ.get('DISABLE_R3_DELETION', '').strip() == '1'
    if _r3_deletion_disabled:
        print(f"\n  [LOCAL-261] R3 deletion DISABLED by DISABLE_R3_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-261] PHASE 5.142: R3 suggestive-exploration deletion...")
        try:
            from style_validator_detector import apply_r3_to_description as _r3_apply
        except ImportError:
            _r3_apply = None
            print(f"  [LOCAL-261] WARNING: apply_r3_to_description not importable — R3 deletion skipped")

        if _r3_apply:
            _r3_total_deleted = 0
            _r3_total_paras_emptied = 0
            _r3_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r3_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r3_total_deleted += _deleted
                    _r3_total_paras_emptied += _emptied
                    _r3_stops_affected += 1
                    print(f"  [LOCAL-261] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-261] R3 summary: {_r3_total_deleted} sentences deleted, "
                  f"{_r3_total_paras_emptied} paragraphs emptied, "
                  f"{_r3_stops_affected} stops affected")

    # -------- [LOCAL-261] PHASE 5.143: R4 prescribed-feeling deletion --------
    # D165: R4 fires but had no path to the output. Michael's reference case:
    # "you are surrounded by history and natural beauty" — scored 1/5.
    # Behind DISABLE_R4_DELETION=1 flag. $0.00 — deterministic.
    _r4_deletion_disabled = os.environ.get('DISABLE_R4_DELETION', '').strip() == '1'
    if _r4_deletion_disabled:
        print(f"\n  [LOCAL-261] R4 deletion DISABLED by DISABLE_R4_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-261] PHASE 5.143: R4 prescribed-feeling deletion...")
        try:
            from style_validator_detector import apply_r4_to_description as _r4_apply
        except ImportError:
            _r4_apply = None
            print(f"  [LOCAL-261] WARNING: apply_r4_to_description not importable — R4 deletion skipped")

        if _r4_apply:
            _r4_total_deleted = 0
            _r4_total_paras_emptied = 0
            _r4_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r4_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r4_total_deleted += _deleted
                    _r4_total_paras_emptied += _emptied
                    _r4_stops_affected += 1
                    print(f"  [LOCAL-261] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-261] R4 summary: {_r4_total_deleted} sentences deleted, "
                  f"{_r4_total_paras_emptied} paragraphs emptied, "
                  f"{_r4_stops_affected} stops affected")

    # -------- [LOCAL-261] PHASE 5.144: R8 prompt-leakage deletion --------
    # D165: R8 fires but had no path to the output. Model restating its own
    # instructions as narration. Behind DISABLE_R8_DELETION=1 flag. $0.00.
    _r8_deletion_disabled = os.environ.get('DISABLE_R8_DELETION', '').strip() == '1'
    if _r8_deletion_disabled:
        print(f"\n  [LOCAL-261] R8 deletion DISABLED by DISABLE_R8_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-261] PHASE 5.144: R8 prompt-leakage deletion...")
        try:
            from style_validator_detector import apply_r8_to_description as _r8_apply
        except ImportError:
            _r8_apply = None
            print(f"  [LOCAL-261] WARNING: apply_r8_to_description not importable — R8 deletion skipped")

        if _r8_apply:
            _r8_total_deleted = 0
            _r8_total_paras_emptied = 0
            _r8_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r8_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r8_total_deleted += _deleted
                    _r8_total_paras_emptied += _emptied
                    _r8_stops_affected += 1
                    print(f"  [LOCAL-261] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-261] R8 summary: {_r8_total_deleted} sentences deleted, "
                  f"{_r8_total_paras_emptied} paragraphs emptied, "
                  f"{_r8_stops_affected} stops affected")

    # -------- [LOCAL-216] PHASE 5.15: R9 generic-sentence deletion --------
    # D89: a sentence that fits any stop belongs to no stop — delete it.
    # Behind DISABLE_R9_DELETION=1 flag. $0.00 — deterministic, no LLM call.
    _r9_deletion_disabled = os.environ.get('DISABLE_R9_DELETION', '').strip() == '1'
    if _r9_deletion_disabled:
        print(f"\n  [LOCAL-216] R9 deletion DISABLED by DISABLE_R9_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-216] PHASE 5.15: R9 generic-sentence deletion...")
        try:
            from style_validator_detector import apply_r9_to_description as _r9_apply
        except ImportError:
            _r9_apply = None
            print(f"  [LOCAL-216] WARNING: apply_r9_to_description not importable — R9 skipped")

        if _r9_apply:
            _r9_total_deleted = 0
            _r9_total_paras_emptied = 0
            _r9_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r9_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r9_total_deleted += _deleted
                    _r9_total_paras_emptied += _emptied
                    _r9_stops_affected += 1
                    print(f"  [LOCAL-216] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-216] R9 summary: {_r9_total_deleted} sentences deleted, "
                  f"{_r9_total_paras_emptied} paragraphs emptied, "
                  f"{_r9_stops_affected} stops affected")

    # -------- [LOCAL-235] PHASE 5.155: R10 unfulfilled-promise deletion --------
    # Michael (Round 2): "Either tell us the story or get rid of the sentence!"
    # A sentence names a subject (story, tale, history, legacy) without delivering
    # a concrete payload. Behind DISABLE_R10_DELETION=1 flag. $0.00 — deterministic.
    _r10_deletion_disabled = os.environ.get('DISABLE_R10_DELETION', '').strip() == '1'
    if _r10_deletion_disabled:
        print(f"\n  [LOCAL-235] R10 deletion DISABLED by DISABLE_R10_DELETION=1 env var")
    else:
        print(f"\n  [LOCAL-235] PHASE 5.155: R10 unfulfilled-promise deletion...")
        try:
            from style_validator_detector import apply_r10_to_description as _r10_apply
        except ImportError as _r10_err:
            _r10_apply = None
            print(f"  [LOCAL-235] ERROR: R10 NOT APPLIED — apply_r10_to_description "
                  f"unimportable ({_r10_err}). This is a defect, not a configuration: "
                  f"the module sits beside this file. sys.path[0]={sys.path[0]}")

        if _r10_apply:
            _r10_total_deleted = 0
            _r10_total_paras_emptied = 0
            _r10_stops_affected = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _new_desc, _deleted, _emptied = _r10_apply(_desc)
                if _deleted > 0 or _emptied > 0:
                    poi_list[_si]['description'] = _new_desc
                    _r10_total_deleted += _deleted
                    _r10_total_paras_emptied += _emptied
                    _r10_stops_affected += 1
                    print(f"  [LOCAL-235] Stop {_si+1} '{_poi.get('name', '')[:30]}': "
                          f"{_deleted} sentence(s) deleted, {_emptied} paragraph(s) emptied")

            print(f"  [LOCAL-235] R10 summary: {_r10_total_deleted} sentences deleted, "
                  f"{_r10_total_paras_emptied} paragraphs emptied, "
                  f"{_r10_stops_affected} stops affected")

    # -------- [LOCAL-263] PHASE 5.156: Unsupported-claim gate --------
    # D166: a claim survives only if something adjacent substantiates it.
    # Four claim types (PROMISE, SENSORY, FEELING, QUALITY), one shared test.
    # Subsumes R4/R7/R9/R10 for coverage — old detectors kept reporting.
    # Behind DISABLE_UNSUPPORTED_CLAIM_GATE=1 flag. $0.00 unless escalation fires.
    _ucg_disabled = os.environ.get('DISABLE_UNSUPPORTED_CLAIM_GATE', '').strip() == '1'
    if _ucg_disabled:
        print(f"\n  [LOCAL-263] Unsupported-claim gate DISABLED by DISABLE_UNSUPPORTED_CLAIM_GATE=1 env var")
    else:
        print(f"\n  [LOCAL-263] PHASE 5.156: Unsupported-claim gate...")
        try:
            from unsupported_claim_gate import apply_gate_to_stop_descriptions as _ucg_apply
        except ImportError as _ucg_err:
            _ucg_apply = None
            print(f"  [LOCAL-263] WARNING: unsupported_claim_gate not importable — gate skipped ({_ucg_err})")

        if _ucg_apply:
            _ucg_api_key = api_key  # For escalation if needed
            _ucg_model = os.environ.get('ESCALATION_MODEL', 'gpt-4o-mini')

            _ucg_stats = _ucg_apply(
                poi_list,
                stop_corpus_data=_stop_corpus_data if '_stop_corpus_data' in dir() else None,
                api_key=_ucg_api_key,
                model=_ucg_model,
            )

            print(f"  [LOCAL-263] Unsupported-claim gate summary:")
            print(f"    Sentences removed: {_ucg_stats['total_removed']}")
            print(f"    Sentences kept (substantiated): {_ucg_stats['total_kept_substantiated']}")
            print(f"    By type: PROMISE={_ucg_stats['claim_types_removed']['PROMISE']}, "
                  f"SENSORY={_ucg_stats['claim_types_removed']['SENSORY']}, "
                  f"FEELING={_ucg_stats['claim_types_removed']['FEELING']}, "
                  f"QUALITY={_ucg_stats['claim_types_removed']['QUALITY']}")
            print(f"    Escalation calls: {_ucg_stats['escalation_calls']}")
            if _ucg_stats['escalation_cost'] > 0:
                print(f"    Escalation cost: ${_ucg_stats['escalation_cost']:.4f} "
                      f"({_ucg_stats['escalation_tokens']} tokens)")
                total_tokens += _ucg_stats['escalation_tokens']
                total_cost += _ucg_stats['escalation_cost']
            print(f"    Stops affected: {_ucg_stats['stops_affected']}")

            # D55 safety: if total removal exceeds 15%, stop and report
            _total_sentences_in_tour = 0
            for _poi_check in poi_list:
                _desc_check = _poi_check.get('description', '')
                if _desc_check and not _desc_check.startswith('['):
                    from style_validator_detector import _split_sentences as _ss_check
                    _total_sentences_in_tour += len([
                        s for s in _ss_check(_desc_check) if len(s) >= 15
                    ])
            if _total_sentences_in_tour > 0:
                _ucg_removal_rate = _ucg_stats['total_removed'] / _total_sentences_in_tour
                print(f"    Deletion rate: {_ucg_removal_rate:.1%} "
                      f"({_ucg_stats['total_removed']}/{_total_sentences_in_tour})")
                if _ucg_removal_rate > 0.15:
                    print(f"  [LOCAL-263] WARNING: Deletion rate {_ucg_removal_rate:.1%} "
                          f"exceeds 15% ceiling — review before shipping")

    # -------- [LOCAL-269] PHASE 5.157: Unglossed-reference gate --------
    # The inverse of LOCAL-263: a fact that assumes knowledge the listener lacks.
    # Detects named entities with no explanation, triages via model, supplies gloss.
    # Behind DISABLE_UNGLOSSED_REFERENCE_GATE=1 flag.
    _urg_disabled = os.environ.get('DISABLE_UNGLOSSED_REFERENCE_GATE', '').strip() == '1'
    if _urg_disabled:
        print(f"\n  [LOCAL-269] Unglossed-reference gate DISABLED by DISABLE_UNGLOSSED_REFERENCE_GATE=1 env var")
    else:
        print(f"\n  [LOCAL-269] PHASE 5.157: Unglossed-reference gate...")
        try:
            from unglossed_reference_gate import apply_gate_to_stop_descriptions as _urg_apply
        except ImportError as _urg_err:
            _urg_apply = None
            print(f"  [LOCAL-269] WARNING: unglossed_reference_gate not importable — gate skipped ({_urg_err})")

        if _urg_apply:
            _urg_api_key = api_key
            _urg_model = os.environ.get('GLOSS_MODEL', 'gpt-4o-mini')

            _urg_stats = _urg_apply(
                poi_list,
                stop_corpus_data=_stop_corpus_data if '_stop_corpus_data' in dir() else None,
                api_key=_urg_api_key,
                model=_urg_model,
                # [LOCAL-496] The venue is the setting, not an unexplained
                # reference. Degrading "Fine Arts" out of "Museum of Fine Arts,
                # Boston" produced "The Museum Boston", which LOCAL-479 then
                # could not ground, so it dropped the sentence — and the donor
                # in it. One wrong deletion, three gates deep.
                #
                # `_museum_venue_name` (resolved at :5157), NOT `location`.
                # `location` here is the request string — "Picasso, Miro, Dali:
                # Unbound exhibition at MFA, Boston, MA" — whose capitalised
                # spans are Picasso, Miro and Dali. Exempting those would make
                # the gate blind to the three artists it most needs to check.
                venue_name=(_museum_venue_name
                            if '_museum_venue_name' in dir() else None),
            )

            print(f"  [LOCAL-269] Unglossed-reference gate summary (LOCAL-287: compose, not splice):")
            print(f"    References detected: {_urg_stats['total_detected']}")
            print(f"    Glossed (composed): {_urg_stats['total_glossed']}")
            print(f"    Suppressed (already explained): {_urg_stats.get('total_suppressed', 0)}")
            print(f"    Degraded (name dropped): {_urg_stats['total_degraded']}")
            print(f"    Guard failures: {_urg_stats.get('total_guard_failed', 0)}")
            print(f"    Known (skipped): {_urg_stats['total_known']}")
            print(f"    Triage: {_urg_stats['triage_tokens']} tokens, "
                  f"${_urg_stats['triage_cost']:.4f}, {_urg_stats['triage_latency']:.1f}s")
            print(f"    Gloss: {_urg_stats['gloss_tokens']} tokens, "
                  f"${_urg_stats['gloss_cost']:.4f}, {_urg_stats['gloss_latency']:.1f}s")
            print(f"    Compose: {_urg_stats.get('compose_tokens', 0)} tokens, "
                  f"${_urg_stats.get('compose_cost', 0.0):.4f}, {_urg_stats.get('compose_latency', 0.0):.1f}s")
            print(f"    Total added cost: ${_urg_stats['total_cost']:.4f}")
            if _urg_stats['total_cost'] > 0:
                total_tokens += _urg_stats['total_tokens']
                total_cost += _urg_stats['total_cost']
            print(f"    Stops affected: {_urg_stats['stops_affected']}")
            if _urg_stats['all_glosses']:
                print(f"    Glosses applied:")
                for g in _urg_stats['all_glosses']:
                    action = g.get('action', '')
                    if g.get('gloss'):
                        print(f"      • {g['entity']} → \"{g['gloss']}\" [source: {g.get('source', 'composed')}]")
                    elif action == 'suppressed':
                        print(f"      • {g['entity']} → SUPPRESSED (already explained)")
                    elif action == 'guard_failed':
                        print(f"      • {g['entity']} → GUARD FAILED ({g.get('reason', '?')}), name dropped")
                    else:
                        print(f"      • {g['entity']} → DEGRADED (name dropped)")
            if _urg_stats.get('guard_failures'):
                print(f"    Guard failures detail:")
                for gf in _urg_stats['guard_failures']:
                    print(f"      ✗ {gf['entity']}: \"{gf['gloss']}\" — {gf['reason']}")

    # -------- [LOCAL-378] PHASE 5.158: Prose entity grounding gate --------
    # Fires ONLY for exhibition-scoped museum tours. Removes all mentions of
    # persons not grounded in the exhibition page text or artist checklist.
    # [LOCAL-385] Now scans ALL fields in GATED_PROSE_FIELDS (description + orientation).
    # Scope limitation (Defect 5): unscoped museum tours (Palais Lascaris, etc.)
    # remain ungated. This is intentional and documented — do not widen.
    # [LOCAL-390] Track gate-removed names for final beat verification cause analysis.
    _gate_removed_names = []
    if (tour_category == 'museum' and _exhibition_checklist_result
            and getattr(_exhibition_checklist_result, 'page_text', '')):
        print(f"\n  [LOCAL-385] PHASE 5.158: Prose entity grounding gate (scans all prose fields)...")
        try:
            from prose_entity_grounding_gate import apply_prose_entity_grounding_gate
            _peg_stop_names = [p.get('name', '') for p in poi_list]
            # [LOCAL-390] Collect all person names from story beats — these are
            # grounded by definition (extracted from the page text) and must not
            # be stripped by the entity grounding gate.
            _peg_pre_grounded = []
            if _story_beats_per_stop:
                for _sblist in _story_beats_per_stop:
                    for _sb in _sblist:
                        if _sb.get('role') not in ('circumstance', 'stakes'):
                            _peg_pre_grounded.append(_sb['person'])
            _peg_stats = apply_prose_entity_grounding_gate(
                poi_list,
                _exhibition_checklist_result,
                stop_names=_peg_stop_names,
                pre_grounded_names=_peg_pre_grounded if _peg_pre_grounded else None,
            )
            print(f"  [LOCAL-385] Prose entity grounding gate summary:")
            print(f"    Persons detected: {_peg_stats['persons_detected']}")
            print(f"    Persons grounded: {_peg_stats['persons_grounded']}")
            print(f"    Persons ungrounded: {_peg_stats['persons_ungrounded']}")
            print(f"    Sentences dropped: {_peg_stats['sentences_dropped']}")
            print(f"    Stops affected: {_peg_stats['stops_affected']}")
            if _peg_stats['ungrounded_names']:
                print(f"    Ungrounded: {_peg_stats['ungrounded_names']}")
                _gate_removed_names = list(_peg_stats['ungrounded_names'])
        except ImportError as _peg_err:
            print(f"  [LOCAL-385] WARNING: prose_entity_grounding_gate not importable — gate skipped ({_peg_err})")
        except Exception as _peg_err:
            print(f"  [LOCAL-385] ERROR: prose entity grounding gate failed (non-fatal): {_peg_err}")
    else:
        if tour_category == 'museum':
            # [LOCAL-458] D3: distinguish empty corpus from no scope
            if _exhibition_checklist_result and not getattr(_exhibition_checklist_result, 'page_text', ''):
                print(f"\n  [LOCAL-458] entity gate SKIPPED: corpus=0 chars (retrieval returned no page text)")
            else:
                print(f"\n  [LOCAL-458] entity gate SKIPPED: no exhibition scope (unscoped museum tour)")

    # -------- [LOCAL-458] PHASE 5.158b: Role-claim gate --------
    # Detects ROLE→AGENT claims (e.g. "published by The Hogarth Press") where
    # the agent is INVENTED: stop-record slot is empty AND agent is absent from
    # the grounding corpus. Drops sentences containing invented role claims.
    # Same scope as the person gate: exhibition-scoped museum tours only.
    if (tour_category == 'museum' and _exhibition_checklist_result
            and getattr(_exhibition_checklist_result, 'page_text', '')):
        _rcg_corpus = getattr(_exhibition_checklist_result, 'page_text', '') or ''
        _rcg_works = getattr(_exhibition_checklist_result, 'works', None) or []
        print(f"\n  [LOCAL-458] PHASE 5.158b: Role-claim gate...")
        try:
            from stop_claim_audit import apply_role_claim_gate_to_poi_list
            _rcg_stats = apply_role_claim_gate_to_poi_list(
                poi_list,
                _exhibition_checklist_result,
                _rcg_corpus,
            )
            print(f"  [LOCAL-458] entity gate: corpus={len(_rcg_corpus)} chars, "
                  f"{_rcg_stats['role_claims_detected']} role claims, "
                  f"{_rcg_stats['entities_checked']} entities, "
                  f"{_rcg_stats['claims_dropped']} dropped")
            if _rcg_stats['drop_log']:
                for _rl in _rcg_stats['drop_log']:
                    print(f"    [LOCAL-458] field={_rl['field']} stop='{_rl['stop'][:30]}' "
                          f"role={_rl['role']} agent='{_rl['agent']}' "
                          f"reason='{_rl['reason']}'")
                    for _ds in _rl['dropped_sentences']:
                        print(f"      dropped: \"{_ds[:100]}\"")
        except ImportError as _rcg_err:
            print(f"  [LOCAL-458] WARNING: stop_claim_audit not importable — gate skipped ({_rcg_err})")
        except Exception as _rcg_err:
            print(f"  [LOCAL-458] ERROR: role-claim gate failed (non-fatal): {_rcg_err}")
    else:
        if tour_category == 'museum':
            if _exhibition_checklist_result and not getattr(_exhibition_checklist_result, 'page_text', ''):
                print(f"\n  [LOCAL-458] entity gate SKIPPED: corpus=0 chars (retrieval returned no page text)")
            else:
                print(f"\n  [LOCAL-458] entity gate SKIPPED: no exhibition scope (unscoped museum tour)")

    # -------- [LOCAL-479] PHASE 5.158c: Organisation grounding gate --------
    # The grammar-independent sibling of 5.158b. The Hogarth Press fabrication
    # escaped the role-claim gate on three separate runs in three constructions
    # (passive, active, em-dash parenthetical), each fixed by adding a pattern —
    # a losing race against a generative model. This asks only whether the
    # organisation is grounded anywhere at all, which no rephrasing can dodge.
    # Same scope and same bar as 5.158b: exhibition-scoped museum tours, and an
    # org absent from BOTH the record and the corpus is the only thing that drops.
    # Behind DISABLE_ORG_GROUNDING_GATE=1, like every other gate in this chain, so
    # its effect on tour quality can be A/B measured rather than assumed. D480: a
    # single run is a sample, so the comparison is a mean over >=3 runs each way.
    _org_gate_disabled = os.environ.get('DISABLE_ORG_GROUNDING_GATE', '').strip() == '1'
    if _org_gate_disabled:
        print(f"\n  [LOCAL-479] Organisation grounding gate DISABLED by env var")
    elif (tour_category == 'museum' and _exhibition_checklist_result
            and getattr(_exhibition_checklist_result, 'page_text', '')):
        # [LOCAL-482] Ground against the SERP snippets and stop corpus as well as
        # the exhibition page. Measured A/B over 3 runs each way: the gate cost
        # 5.4 index points (38.3 with, 43.7 without), and the reason is visible in
        # the drop log — it caught "The Hogarth Press" (a real fabrication, the one
        # Michael has objected to most) but also dropped "Éditions Verve", which is
        # the actual publisher of Au Soleil du Plafond and simply is not mentioned
        # on the MFA's exhibition page.
        #
        # A museum's own page is a thin evidence base for a question about
        # publishers. The snippets we already retrieved and paid for are a much
        # larger one, and using them narrows the false-rejection half of the trade
        # without touching the false-acceptance half: an organisation named nowhere
        # in ANY of our evidence is still dropped.
        _org_corpus = getattr(_exhibition_checklist_result, 'page_text', '') or ''
        try:
            _org_extra = []
            for _osn in (_DIRECT_SNIPPETS_PER_STOP or {}).values():
                for _os in (_osn or []):
                    if isinstance(_os, dict):
                        _org_extra.append(f"{_os.get('title','')} {_os.get('snippet','')}")
            for _oe in (_stop_corpus_data or {}).values():
                for _op in ((_oe or {}).get('passages') or []):
                    _org_extra.append(str(_op))
            if _org_extra:
                _org_corpus = _org_corpus + '\n' + '\n'.join(_org_extra)
        except Exception as _oc_err:
            print(f"  [LOCAL-482] could not widen org corpus (non-fatal): {_oc_err}")
        print(f"\n  [LOCAL-479] PHASE 5.158c: Organisation grounding gate "
              f"(corpus {len(_org_corpus)} chars)...")
        try:
            from prose_entity_grounding_gate import apply_org_grounding_gate
            _org_stats = apply_org_grounding_gate(
                poi_list, _org_corpus,
                exempt=[location, _exhibition_name if '_exhibition_name' in dir() else ''],
            )
            print(f"  [LOCAL-479] orgs detected={_org_stats['orgs_detected']} "
                  f"grounded={_org_stats['orgs_grounded']} "
                  f"ungrounded={_org_stats['orgs_ungrounded']} "
                  f"sentences_dropped={_org_stats['sentences_dropped']}")
            for _ol in _org_stats['drop_log']:
                print(f"    [LOCAL-479] field={_ol['field']} stop='{_ol['stop'][:30]}' "
                      f"org='{_ol['org']}' — ungrounded")
                for _od in _ol['dropped_sentences']:
                    print(f"      dropped: \"{_od[:100]}\"")
        except ImportError as _org_err:
            print(f"  [LOCAL-479] WARNING: org gate not importable — skipped ({_org_err})")
        except Exception as _org_err:
            print(f"  [LOCAL-479] ERROR: org gate failed (non-fatal): {_org_err}")

    # -------- [LOCAL-384] PHASE 5.159: Form-claim gate --------
    # The model repeatedly infers physical form from titles (e.g. "Au Soleil du
    # Plafond" → "ceiling mural"). Five prompt-level rounds failed. This gate
    # enforces at the output level: scan delivered text for physical form and
    # placement claims, check against the known medium, remove unsupported claims.
    # [LOCAL-385] Now scans ALL fields in GATED_PROSE_FIELDS (description + orientation).
    # Same scope as the person gate: exhibition-scoped museum tours only.
    if (tour_category == 'museum' and _exhibition_checklist_result
            and getattr(_exhibition_checklist_result, 'works', None)):
        print(f"\n  [LOCAL-385] PHASE 5.159: Form-claim gate (scans all prose fields)...")
        try:
            from prose_entity_grounding_gate import apply_form_claim_gate
            _fcg_stats = apply_form_claim_gate(
                poi_list,
                _exhibition_checklist_result,
            )
            print(f"  [LOCAL-385] Form-claim gate summary:")
            print(f"    Claims detected: {_fcg_stats['claims_detected']}")
            print(f"    Claims kept (compatible): {_fcg_stats['claims_kept']}")
            print(f"    Claims removed: {_fcg_stats['claims_removed']}")
            print(f"    Metaphor-exempt (kept): {_fcg_stats['claims_metaphor_exempt']}")
            print(f"    Sentences dropped: {_fcg_stats['sentences_dropped']}")
            print(f"    Stops affected: {_fcg_stats['stops_affected']}")
            if _fcg_stats['removal_log']:
                for _rl in _fcg_stats['removal_log']:
                    print(f"    [LOCAL-385] field={_rl['field']} stop='{_rl['stop']}' "
                          f"term='{_rl['term']}' medium='{_rl['medium']}' "
                          f"dropped: \"{_rl['sentence'][:80]}\"")
        except ImportError as _fcg_err:
            print(f"  [LOCAL-385] WARNING: form-claim gate not importable — gate skipped ({_fcg_err})")
        except Exception as _fcg_err:
            print(f"  [LOCAL-385] ERROR: form-claim gate failed (non-fatal): {_fcg_err}")
    else:
        if tour_category == 'museum':
            print(f"\n  [LOCAL-385] Form-claim gate SKIPPED "
                  f"(no exhibition scope — unscoped museum tours are not gated)")

    # -------- [LOCAL-386/389] PHASE 5.160: Numeric-claim gate --------
    # An ungrounded statistic ("over 1.2 million visitors annually") passed both
    # the person gate and the form-claim gate because neither inspects numeric claims.
    # This gate scans all GATED_PROSE_FIELDS for quantitative claims (statistics,
    # superlatives, dimensions, percentages) and drops sentences whose numbers are
    # not in the exhibition page_text OR the work identity block (credit line, date,
    # medium). Same scope as the other gates: exhibition-scoped museum tours only.
    # [LOCAL-389] Precision: rejects garbage matches (', in' etc.) — a claim must
    # be a recognisable quantity with at least one digit (or a superlative).
    if (tour_category == 'museum' and _exhibition_checklist_result
            and getattr(_exhibition_checklist_result, 'page_text', '')
            and not os.environ.get('DISABLE_NUMERIC_CLAIM_GATE')):
        print(f"\n  [LOCAL-389] PHASE 5.160: Numeric-claim gate (scans all prose fields)...")
        try:
            from prose_entity_grounding_gate import apply_numeric_claim_gate
            _ncg_stats = apply_numeric_claim_gate(
                poi_list,
                _exhibition_checklist_result,
            )
            print(f"  [LOCAL-389] Numeric-claim gate summary:")
            print(f"    Claims detected: {_ncg_stats['claims_detected']}")
            print(f"    Grounded (identity block): {_ncg_stats['claims_grounded_identity']}")
            print(f"    Grounded (page text): {_ncg_stats['claims_grounded_page']}")
            print(f"    Ungrounded (dropped): {_ncg_stats['claims_ungrounded']}")
            print(f"    Sentences dropped: {_ncg_stats['sentences_dropped']}")
            print(f"    Stops affected: {_ncg_stats['stops_affected']}")
            if _ncg_stats['drop_log']:
                for _dl in _ncg_stats['drop_log']:
                    print(f"    [LOCAL-389] field={_dl['field']} stop='{_dl['stop']}' "
                          f"claim='{_dl['claim_text']}' "
                          f"context='{_dl.get('claim_context', '')}' "
                          f"dropped: \"{_dl['sentence'][:80]}\"")
        except ImportError as _ncg_err:
            print(f"  [LOCAL-389] WARNING: numeric-claim gate not importable — gate skipped ({_ncg_err})")
        except Exception as _ncg_err:
            print(f"  [LOCAL-389] ERROR: numeric-claim gate failed (non-fatal): {_ncg_err}")
    else:
        if tour_category == 'museum':
            if os.environ.get('DISABLE_NUMERIC_CLAIM_GATE'):
                print(f"\n  [LOCAL-389] Numeric-claim gate DISABLED "
                      f"(DISABLE_NUMERIC_CLAIM_GATE=1)")
            else:
                print(f"\n  [LOCAL-389] Numeric-claim gate SKIPPED "
                      f"(no exhibition scope — unscoped museum tours are not gated)")

    # -------- [LOCAL-402] PHASE 5.161: Temporal coherence gate --------
    # Catches impossible temporal relations: interactions between people whose
    # dates make it impossible (e.g. "Dalí collaborated with Freud" — Freud d.1939).
    # This is DISTINCT from the person grounding gate (which checks facts, not relations)
    # and from the form-claim gate (which checks physical assertions).
    # Scope: ALL museum tours with STORIED_MODE=true. No exhibition scope required.
    if _storied_mode and tour_category == 'museum':
        print(f"\n  [LOCAL-402] PHASE 5.161: Temporal coherence gate (impossible relations)...")
        try:
            from temporal_coherence_gate import apply_temporal_coherence_gate
            _tcg_snippets = _DIRECT_SNIPPETS_PER_STOP if _DIRECT_SNIPPETS_PER_STOP else None
            _tcg_stats = apply_temporal_coherence_gate(
                poi_list,
                snippets_per_stop=_tcg_snippets,
            )
            print(f"  [LOCAL-402] Temporal coherence gate summary:")
            print(f"    Relations checked: {_tcg_stats['relations_checked']}")
            print(f"    Relations rejected: {_tcg_stats['relations_rejected']}")
            print(f"    Sentences removed: {_tcg_stats['sentences_removed']}")
            print(f"    Stops affected: {_tcg_stats['stops_affected']}")
            if _tcg_stats['rejection_log']:
                for _trl in _tcg_stats['rejection_log']:
                    print(f"    [LOCAL-402] coherence reject: '{_trl['sentence'][:80]}' "
                          f"— {_trl['reason']}")
        except ImportError as _tcg_err:
            print(f"  [LOCAL-402] WARNING: temporal_coherence_gate not importable — gate skipped ({_tcg_err})")
        except Exception as _tcg_err:
            print(f"  [LOCAL-402] ERROR: temporal coherence gate failed (non-fatal): {_tcg_err}")
    else:
        if _storied_mode:
            print(f"\n  [LOCAL-402] Temporal coherence gate SKIPPED (non-museum tour)")

    # -------- [LOCAL-229] PHASE 5.16: CONTRADICTED claim block --------
    # D100 (Michael, 2026-08-04): "We should not publish if we are reasonably sure
    # that the data is incorrect." If any sentence group contains a CONTRADICTED
    # claim, drop that group from the narration. UNSUPPORTED does NOT block (D100).
    # Behind DISABLE_CONTRADICTED_BLOCK=1 for A/B measurement.
    _contradicted_block_disabled = os.environ.get('DISABLE_CONTRADICTED_BLOCK', '').strip() == '1'
    if _contradicted_block_disabled:
        print(f"\n  [LOCAL-229] CONTRADICTED block DISABLED by DISABLE_CONTRADICTED_BLOCK=1 env var")
    else:
        print(f"\n  [LOCAL-229] PHASE 5.16: CONTRADICTED claim block (D100 enforcement)...")
        _cb_groups_blocked = 0
        _cb_stops_affected = 0
        _cb_log_entries = []

        try:
            from claim_check import check_paragraph as _cb_check_paragraph, CONTRADICTED as _CB_CONTRADICTED
            from sentence_group_scorer import split_into_sentence_groups as _cb_split_groups

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    continue

                _stop_name = _poi.get('name', f'Stop {_si + 1}')
                _venue_for_check = _museum_venue_name if tour_category == 'museum' else ''

                # Get corpus passages for this stop
                _cb_passages = []
                if _stop_corpus_data and _stop_name in _stop_corpus_data:
                    _sc_entry = _stop_corpus_data[_stop_name]
                    if _sc_entry and _sc_entry.get('passages'):
                        _cb_passages = _sc_entry['passages']

                if not _cb_passages:
                    # No corpus passages → claim_check cannot find contradictions
                    continue

                # Split each paragraph into sentence groups and check each group
                _paragraphs = [p.strip() for p in _desc.split('\n\n') if p.strip()]
                _new_paragraphs = []
                _stop_blocked = False

                for _para in _paragraphs:
                    if len(_para) <= 30:
                        _new_paragraphs.append(_para)
                        continue

                    _groups = _cb_split_groups(_para)
                    _surviving_groups = []

                    for _group_sentences in _groups:
                        _group_text = ' '.join(_group_sentences)

                        # Run claim_check on this group
                        _claim_result = _cb_check_paragraph(
                            _group_text,
                            stop_title=_stop_name,
                            venue_name=_venue_for_check,
                            passages=_cb_passages,
                        )

                        _contradicted_count = _claim_result['verdict_counts'].get('contradicted', 0)

                        if _contradicted_count > 0:
                            # BLOCK: drop this sentence group
                            _cb_groups_blocked += 1
                            _stop_blocked = True

                            # Log the block: claim, contradicting passage, action
                            _contradicted_claims = [
                                c for c in _claim_result['claims']
                                if c['verdict'] == _CB_CONTRADICTED
                            ]
                            for _cc in _contradicted_claims:
                                _log_entry = {
                                    'stop': _stop_name,
                                    'stop_index': _si + 1,
                                    'claim': _cc['text'],
                                    'claim_sentence': _cc.get('sentence', ''),
                                    'contradicting_evidence': _cc.get('evidence', ''),
                                    'group_text': _group_text[:200],
                                    'action': 'DROPPED',
                                }
                                _cb_log_entries.append(_log_entry)
                                print(f"  [LOCAL-229] BLOCKED Stop {_si+1} '{_stop_name[:30]}': "
                                      f"claim='{_cc['text'][:60]}' "
                                      f"contradicted_by='{(_cc.get('evidence') or '')[:80]}' → DROPPED")
                        else:
                            _surviving_groups.append(_group_text)

                    # Reassemble paragraph from surviving groups
                    if _surviving_groups:
                        _new_paragraphs.append(' '.join(_surviving_groups))
                    # else: entire paragraph dropped (all groups blocked)

                if _stop_blocked:
                    _cb_stops_affected += 1
                    # Reassemble description
                    _new_desc = '\n\n'.join(_new_paragraphs).strip()
                    poi_list[_si]['description'] = _new_desc

            # Summary
            print(f"  [LOCAL-229] CONTRADICTED block summary: {_cb_groups_blocked} group(s) blocked, "
                  f"{_cb_stops_affected} stop(s) affected")
            if _cb_log_entries:
                print(f"  [LOCAL-229] Block log ({len(_cb_log_entries)} entries):")
                for _le in _cb_log_entries:
                    print(f"    stop={_le['stop_index']} claim='{_le['claim'][:50]}' "
                          f"evidence='{_le['contradicting_evidence'][:50]}' action={_le['action']}")

        except ImportError as _cb_import_err:
            print(f"  [LOCAL-229] WARNING: import failed — CONTRADICTED block skipped: {_cb_import_err}")

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

    # -------- PHASE 5.7: Dangling-reference scrub --------
    # [LOCAL-22] If any stops were removed by 5.5b or 5.6, re-number and clean up
    # "Stop N" references in descriptions/orientations where N > final stop count.
    _final_stop_count = len(poi_list)
    for i, p in enumerate(poi_list):
        p['stop_number'] = i + 1
    # Scrub dangling "Stop N" references from descriptions and orientations
    for p in poi_list:
        for _field_key in ('description', 'orientation'):
            _text = p.get(_field_key, '') or ''
            if not _text:
                continue
            # Remove sentences referencing Stop N where N > final count
            _scrubbed = _text
            for _n in range(_final_stop_count + 1, _final_stop_count + 20):
                # "whereabouts of Stop N" or "find Stop N" or "at Stop N"
                _scrubbed = re.sub(
                    rf'(?i)[^.]*\bStop\s+{_n}\b[^.]*\.\s*', '', _scrubbed
                )
            if _scrubbed != _text:
                p[_field_key] = _scrubbed.strip()
                print(f"  [PHASE 5.7] Scrubbed dangling Stop reference(s) from {_field_key} "
                      f"of stop {p['stop_number']}: '{p['name']}'")
    print(f"OK PHASE 5.7: Dangling-reference scrub complete ({_final_stop_count} stops)")

    # -------- [LOCAL-318] PHASE 5.7b: Dangling-demonstrative scrub --------
    # Detect "this/these/that/those + noun" where the noun has no antecedent in
    # the same stop's spoken text. Schema lines are excluded as antecedents.
    # Repair from corpus if possible; delete sentence otherwise.
    print(f"\n  [LOCAL-318] PHASE 5.7b: Dangling-demonstrative scrub...")
    try:
        from dangling_demonstrative_gate import apply_dangling_demonstrative_gate as _ddg_apply
    except ImportError as _ddg_err:
        _ddg_apply = None
        print(f"  [LOCAL-318] WARNING: dangling_demonstrative_gate not importable — gate skipped ({_ddg_err})")

    if _ddg_apply:
        _ddg_stats = _ddg_apply(
            poi_list,
            stop_corpus_data=_stop_corpus_data if '_stop_corpus_data' in dir() else None,
        )
        print(f"  [LOCAL-318] Dangling-demonstrative scrub summary:")
        print(f"    Detected: {_ddg_stats['total_detected']}")
        print(f"    Repaired (name substituted): {_ddg_stats['total_repaired']}")
        print(f"    Deleted (unrepairable): {_ddg_stats['total_deleted']}")
        print(f"    Stops affected: {_ddg_stats['stops_affected']}")
        if _ddg_stats['findings']:
            for _f in _ddg_stats['findings']:
                if _f['action'] == 'repaired':
                    print(f"    [{_f['stop']}] REPAIRED: '{_f['demonstrative_np']}' → {_f['after'][:80]}")
                else:
                    print(f"    [{_f['stop']}] DELETED: '{_f['demonstrative_np']}' in: {_f['sentence'][:80]}")
    print(f"OK PHASE 5.7b: Dangling-demonstrative scrub complete")

    # -------- [LOCAL-27] PHASE 5.8: Self-contradiction check --------
    # Verify that declared type_specialty is consistent with prose description.
    # If contradicting, clear the type_specialty rather than ship a lie.
    if tour_category == 'museum' and _museum_venue_name:
        print(f"\nPHASE 5.8: Type/prose contradiction check (LOCAL-27)...")
        _contradictions = _check_type_prose_contradiction(poi_list)
        if _contradictions:
            print(f"  [LOCAL-27] Fixed {len(_contradictions)} type/prose contradiction(s)")
        else:
            print(f"  [LOCAL-27] No type/prose contradictions detected")

    # -------- [LOCAL-41] PHASE 5.9: Audio-native post-processing --------
    # Strip trailing rhetorical questions from descriptions (GPT sometimes
    # ignores the "no questions" instruction). Also strip the formulaic
    # "Within the broader context of the museum" scaffolding phrase.
    print(f"\nPHASE 5.9: Audio-native cleanup (LOCAL-41)...")
    _audio_fixes = 0
    _broader_context_count = 0
    for p in poi_list:
        for _field_key in ('description', 'orientation'):
            _text = p.get(_field_key, '') or ''
            if not _text:
                continue
            _original = _text

            # Strip trailing rhetorical questions (last sentence ending with ?)
            # Only strip if it's the last sentence — mid-text questions are sometimes OK
            _sentences = re.split(r'(?<=[.!?])\s+', _text.strip())
            while _sentences and _sentences[-1].rstrip().endswith('?'):
                _sentences.pop()
                _audio_fixes += 1
            _text = ' '.join(_sentences)

            # Replace "Within the broader context of the museum/collection"
            # with nothing (the surrounding prose usually flows without it)
            _text_new = re.sub(
                r'[Ww]ithin the broader context of (the museum|the collection|this museum|this collection|' + re.escape(tour_type) + r')[,.]?\s*',
                '', _text
            )
            if _text_new != _text:
                _broader_context_count += 1
                _text = _text_new

            if _text != _original:
                p[_field_key] = _text.strip()
    print(f"  [LOCAL-41] Stripped {_audio_fixes} trailing question(s), "
          f"removed {_broader_context_count} 'broader context' instance(s)")

    # -------- [LOCAL-474] PHASE 5.17: Post-gate retry --------
    #
    # THE MEASURED PROBLEM (D472). The gate chain above is allowed to delete
    # sentences and nothing regenerates what it removed. On the 2026-08-18 release
    # run, stop 2 "Au Soleil du Plafond" came out as two sentences scoring 21,
    # because the temporal gate CORRECTLY deleted "In 1955, Juan Gris collaborated
    # with Pierre Reverdy" — Gris died in 1927 — and nothing replaced it. The gate
    # was right and the tour got worse. A correct deletion with no second attempt
    # is indistinguishable from having had no material at all.
    #
    # The 120-word floor at LOCAL-394 does not catch this: it runs BEFORE the chain
    # and only logs. This is the same floor, re-checked after the deletions, with a
    # regeneration behind it.
    #
    # WHY IT IS A RETRY AND NOT A RE-ROLL. Regenerating blind would reproduce the
    # same false claim — the model has no idea why anything was removed. The removed
    # sentences are fed back as an explicit prohibition, which is the production
    # equivalent of the lab loop's rotating focus fact (STORY_BASELINE.md §5①):
    # a second attempt that has learned something from the first.
    #
    # Bounded: one retry per stop, only for stops that fell below the floor BECAUSE
    # of the gates, and the result is kept only if it is longer than what the gates
    # left. It can therefore never make a stop worse than not running.
    # [LOCAL-477] Strip markdown from EVERY prose field, not only retried ones.
    # Run 3 shipped an orientation beginning `** "Au Soleil du Plafond,"` on a stop
    # the retry never touched, so this is a property of normal generation. These
    # fields are going to a text-to-speech voice: asterisks and hashes are either
    # read aloud or produce an audible stumble, and no gate in the chain looks for
    # them.
    _md_cleaned = 0
    for _mpoi in poi_list:
        for _mf in ('description', 'orientation'):
            _mv = _mpoi.get(_mf) or ''
            if not _mv or _mv.startswith('['):
                continue
            _clean = re.sub(r'\*{1,3}', '', _mv)
            _clean = re.sub(r'^\s*#{1,6}\s*', '', _clean, flags=re.MULTILINE)
            _clean = re.sub(r'[ \t]{2,}', ' ', _clean).strip()
            if _clean != _mv:
                _mpoi[_mf] = _clean
                _md_cleaned += 1
    if _md_cleaned:
        print(f"\n  [LOCAL-477] stripped markdown from {_md_cleaned} prose field(s) "
              f"— these are spoken aloud")

    _retry_stats = {'eligible': 0, 'retried': 0, 'improved': 0, 'kept_original': 0,
                    'trigger_floor': 0, 'trigger_no_story': 0,
                    'trigger_top_value': 0}  # [D498]
    # [D499] `DISABLE_STORY_RETRY=1` switches off the WHOLE of PHASE 5.17 — the
    # LOCAL-474 hollowed-by-gates retry, step 7a, step 7b's rotation and step 7c's
    # allowance. Added because there was no way to generate a tour with step 7
    # inactive: `STORY_PASS_ENABLED=0` disables the story pass but NOT this block,
    # which is gated only on storied mode. The first attempt at a step-0 baseline
    # was contaminated as a result — 7a fired on 3 stops and 7b rotated on 3, in a
    # run whose whole purpose was to show the tour BEFORE step 7 touches it.
    #
    # Off by default; this changes no production behaviour. It also gives step 7
    # as a whole a single A/B lever, which it did not have.
    _retry_disabled = os.environ.get('DISABLE_STORY_RETRY', '').strip() == '1'
    if _retry_disabled:
        print("\n  [D499] PHASE 5.17 retry DISABLED by env var — steps 7a, 7b and "
              "7c inactive, and the LOCAL-474 hollowed-stop retry with them")
    if _storied_mode and not _phase5_ceiling_breached and not _retry_disabled:
        _RETRY_FLOOR = 120

        # -------- [LOCAL-487] STEP 7a: retry on "NO VALID STORY" --------
        # Michael's step 7 says: "If there are no valid stories, we go to the next
        # fact ... and repeat from #4." The retry as built fires on a 120-word
        # FLOOR instead, which is a different question. A stop can be 200 words of
        # valid, grounded, entirely storyless prose — someone described, nothing
        # risked, refused or lost — and never retry. Length is not story.
        #
        # The bar used here is MICHAEL'S OWN, not an invented index threshold:
        # `story_opportunity_scan.verdict` already encodes "at least one story of
        # >= 3 consecutive sentences about one person, carrying an action and
        # something at stake". It was written, tested, and had zero production
        # callers — the fourth orphan module wired tonight.
        #
        # An index threshold was the obvious alternative and is worse: the index
        # is calibrated against one human judgement (D474), so a number picked off
        # it would be a threshold on a threshold. The structural bar needs no
        # calibration.
        # The cap below ranks storyless stops by the step-5 index, and PHASE 5.21
        # — which normally sets it — runs AFTER this. Compute it here too. The
        # pass is pure and free (no API call), and 5.21 recomputes it afterwards
        # so the final report reflects any text this retry changes.
        try:
            from story_index_pass import apply_story_index, build_index_corpus
            apply_story_index(poi_list, corpus=build_index_corpus(
                _exhibition_checklist_result, _stop_corpus_data))
        except Exception as _pi_err:
            print(f"  [LOCAL-487] pre-retry index unavailable, cap will fall back "
                  f"to stop order (non-fatal): {_pi_err}")

        # -------- [D498] STEP 7c: "in most valuable we can take a larger size" --------
        # `MAX_SENTENCES_TOP = 7` has existed since LOCAL-491 and was UNREACHABLE:
        # `_is_top_value_stop` occurred exactly once in the repository — the line
        # reading it at the story pass. Nothing ever set it, so every stop was
        # capped at MAX_SENTENCES = 5 and the record credited step 7c as landed.
        #
        # It could not be fixed by adding the missing assignment, and that is the
        # real content of this fix. "Most valuable" is a statement about the
        # step-5 index; the index scores WRITTEN prose; the story pass chooses the
        # sentence budget BEFORE any prose exists. There is no moment during the
        # first pass at which the answer is knowable.
        #
        # So the larger allowance is spent where the answer DOES exist: here,
        # after the index has been computed, in the retry phase that already
        # regenerates stops. The top stop is marked and joins the retry set; the
        # story pass reads the flag on regeneration and writes to 7 sentences.
        #
        # ACCEPTANCE IS AN INDEX IMPROVEMENT, not length. A longer retry that
        # scores worse is a worse stop, and "it got longer" is the acceptance bug
        # LOCAL-487 removed from the storyless trigger — re-importing it here
        # would undo that lesson one screen further down.
        _top_value_idx = None
        if os.environ.get('DISABLE_STORY_TOP_SIZE', '').strip() != '1':
            _scored_stops = [(i, p.get('_story_index')) for i, p in enumerate(poi_list)
                             if isinstance(p.get('_story_index'), (int, float))
                             and (p.get('description') or '')
                             and not (p.get('description') or '').startswith('[')]
            if _scored_stops:
                _top_value_idx = max(_scored_stops, key=lambda t: (t[1], -t[0]))[0]
                poi_list[_top_value_idx]['_is_top_value_stop'] = True
                from story_pass import MAX_SENTENCES, MAX_SENTENCES_TOP, sentences_in
                # THE STORY, not the description. Measured on the 14:28 live run:
                # stop 2's story pass wrote 5 sentences — exactly at the cap, so
                # the larger allowance was the whole point — while its assembled
                # description was 9, because the description also carries
                # orientation, directions and transitions. Counting the
                # description made `_top_value` false for every stop and left 7c
                # dead in a new way. The unit tests could not see this; they
                # asserted the flag was written, not what it was measured against.
                _sp_res = poi_list[_top_value_idx].get('_story_pass') or {}
                _cur_sent = sentences_in(_sp_res.get('story') or '')
                print(f"\n  [D498] step 7c: most valuable stop is "
                      f"{_top_value_idx + 1} '{poi_list[_top_value_idx].get('name','')[:38]}' "
                      f"(index {poi_list[_top_value_idx].get('_story_index')}) — allowance "
                      f"{MAX_SENTENCES} -> {MAX_SENTENCES_TOP} sentences on regeneration, "
                      f"story currently {_cur_sent} sentence(s)"
                      f"{' — no story pass result, cannot judge' if not _sp_res else ''}")

        _no_story_stops = set()
        try:
            from story_opportunity_scan import measure as _sos_measure, verdict as _sos_verdict
            for _vi, _vpoi in enumerate(poi_list):
                _vtext = _vpoi.get('description') or ''
                if not _vtext or _vtext.startswith('['):
                    continue
                try:
                    _vv = _sos_verdict(_sos_measure(_vtext))
                except Exception:
                    continue
                _vpoi['_story_verdict'] = _vv
                if _vv.get('needs_additional_story'):
                    _no_story_stops.add(_vi)
            if _no_story_stops:
                print(f"\n  [LOCAL-487] step 7a: {len(_no_story_stops)} stop(s) have "
                      f"NO VALID STORY by Michael's bar (3+ consecutive sentences, "
                      f"one person, an action and something at stake)")
                for _vi in sorted(_no_story_stops):
                    _why = (poi_list[_vi].get('_story_verdict') or {}).get('why', '')
                    print(f"    stop {_vi + 1} '{poi_list[_vi].get('name', '')[:38]}': {_why[:110]}")

                # CAP THE SPEND. Measured 2026-08-19 00:3x: the bar rejects
                # EVERY stop of a current production tour — a finding in its own
                # right, and consistent with the lab-vs-production gap (D472).
                # But "retry everything that fails the bar" is one extra
                # generation per stop, roughly tripling the cost of a tour, on a
                # trigger that has never been shown to improve anything.
                #
                # So the retry goes to the WORST stop only: the one Michael reads
                # first when a tour disappoints, ranked by the step-5 index that
                # is already computed. One extra generation per tour, bounded.
                # Raising the cap is a cost decision and wants the A/B D484 sizes
                # at 15 runs per arm — not a quiet constant change.
                _retry_cap = int(os.environ.get('STORY_RETRY_CAP', '1') or '1')
                if len(_no_story_stops) > _retry_cap:
                    _ranked = sorted(
                        _no_story_stops,
                        key=lambda i: (poi_list[i].get('_story_index', 999), i))
                    _kept = set(_ranked[:_retry_cap])
                    print(f"    [LOCAL-487] cap={_retry_cap}: retrying only the weakest "
                          f"— stop {sorted(_kept)[0] + 1} "
                          f"'{poi_list[sorted(_kept)[0]].get('name','')[:34]}' "
                          f"(index {poi_list[sorted(_kept)[0]].get('_story_index','?')})")
                    _no_story_stops = _kept
        except ImportError as _sos_err:
            print(f"  [LOCAL-487] story_opportunity_scan not importable — "
                  f"7a falls back to the word floor alone ({_sos_err})")

        for _ri, _rpoi in enumerate(poi_list):
            _now = _rpoi.get('description') or ''
            _before = _pre_gate_prose.get(_ri, '')
            if not _now or _now.startswith('['):
                continue
            _now_wc = len(_now.split())

            # Trigger 1 (LOCAL-474, unchanged): the gates hollowed the stop out.
            _hollowed = (_now_wc < _RETRY_FLOOR
                         and len(_before.split()) - _now_wc >= 15)
            # Trigger 2 (LOCAL-487): there is no valid story, at any length.
            _storyless = _ri in _no_story_stops
            # Trigger 3 [D498]: this is the most valuable stop and it may now be
            # written longer. Only worth a generation if it is not already using
            # the larger allowance.
            _top_value = (_ri == _top_value_idx)
            if _top_value:
                # The STORY's length, not the description's — see the note at the
                # flag assignment. No story-pass result means we cannot tell
                # whether the allowance would buy anything, so do not spend.
                from story_pass import (MAX_SENTENCES as _D498_MAX,
                                        sentences_in as _D498_sent)
                _sp_r = _rpoi.get('_story_pass') or {}
                _top_value = bool(_sp_r) and 0 < _D498_sent(
                    _sp_r.get('story') or '') <= _D498_MAX

            if not _hollowed and not _storyless and not _top_value:
                continue
            # A stop that was never worth mining has no second fact to rotate to;
            # retrying it spends money on the same absent corpus. Step 2 already
            # decided this, so read its answer rather than guessing again.
            if _storyless and not _hollowed:
                _w = _rpoi.get('_worthiness') or {}
                if _w.get('worth_mining') is False:
                    continue
            # [D498] Counted separately, and BEFORE the floor/no-story branch, so
            # the summary cannot report a trigger that fired as zero. The existing
            # two-way `trigger_floor if _hollowed else trigger_no_story` does
            # exactly that: on the 08-20 run step 7a detected 2 storyless stops
            # and the summary printed "0 storyless", because both were also
            # hollowed and the ternary can only credit one.
            if _hollowed:
                _retry_stats['trigger_floor'] += 1
            if _storyless:
                _retry_stats['trigger_no_story'] += 1
            if _top_value and not _hollowed and not _storyless:
                _retry_stats['trigger_top_value'] += 1
            _retry_stats['eligible'] += 1

            _removed = _sentences_removed_by_gates(_before, _now)
            # [LOCAL-487] A storyless stop has nothing REMOVED to forbid — the
            # gates were happy with it; it is simply not a story. Aborting here
            # on an empty `_removed`, as the LOCAL-474 version did, would have
            # made trigger 2 fire and then do nothing at all, which is the exact
            # silent-no-op shape this session has been fixing since 21:00.
            if not _removed and not _storyless:
                continue

            _stop_label = _rpoi.get('name', f'Stop {_ri + 1}')
            if _storyless and not _removed:
                _why = (_rpoi.get('_story_verdict') or {}).get('why', 'no valid story')
                print(f"\n  [LOCAL-487] PHASE 5.17: retry '{_stop_label[:44]}' — "
                      f"{_now_wc}w and NO VALID STORY: {_why[:120]}")
            else:
                print(f"\n  [LOCAL-474] PHASE 5.17: retry '{_stop_label[:44]}' — "
                      f"{len(_before.split())}w → {_now_wc}w after gates, "
                      f"{len(_removed)} sentence(s) removed")
                for _rm in _removed:
                    print(f"    removed: \"{_rm[:100]}\"")

            _spine_stop, _fact_sheet, _story_type = _regen_args_by_idx.get(
                _ri, (None, None, None))
            # [LOCAL-476] Forbid the RELATIONSHIP, not the sentence.
            #
            # The first version of this listed the removed sentences and said "do
            # not repeat or rephrase". The model rephrased anyway — "the
            # collaboration between Juan Gris and Pierre Reverdy" came back as
            # "Juan Gris and Pierre Reverdy embarked on a profound artistic
            # collaboration", the same false claim in a form the gate could not
            # see. Naming the sentence teaches the model which WORDS to avoid;
            # naming the underlying assertion is the only version that cannot be
            # satisfied by a paraphrase.
            _instruction = ''
            if _removed:
                _forbidden = '\n'.join(f'- "{s.strip()}"' for s in _removed)
                _instruction += (
                    "\n\nCLAIMS ALREADY REJECTED FOR THIS STOP. A fact-check removed "
                    "each of the following from a previous draft because it is FALSE:"
                    "\n" + _forbidden + "\n\n"
                    "Do not restate these claims in ANY form. This is a ban on the "
                    "underlying assertion, not on the wording — rephrasing it, "
                    "nominalising the verb, softening it with 'reportedly' or "
                    "'is said to have', or implying it indirectly all count as "
                    "restating it. In particular, do not assert that two people "
                    "worked together, met, or corresponded at any date if a claim "
                    "above says they did. Write about something else that the source "
                    "material supports.\n")
            # -------- [LOCAL-491] STEP 7b: ROTATE TO THE NEXT FACT --------
            # Michael's step 7: "If there are no valid stories, we go to the next
            # fact ... and repeat from #4." Production forbade the rejected claim
            # and asked again on the same subject — a retry, not a rotation. D476
            # recorded the result: the model nominalised the verb and shipped the
            # same falsehood in a form the gate could not see. Telling a model
            # what NOT to write leaves it exactly where it was.
            #
            # Rotation changes the subject instead. The next fact off the matrix
            # becomes the focus, and the story pass is pointed at it.
            #
            # NOT via credit_line, which is what Michael specified: LOCAL-406
            # regex-parses donor and printer out of that field, so a fact written
            # there is read as a person's name. `focus_fact` is its own slot.
            try:
                from story_focus_fact import next_focus_fact, MAX_ROTATIONS
                _tried = set(_rpoi.get('_focus_tried') or [])
                if len(_tried) < MAX_ROTATIONS:
                    _fmatrix = {
                        'canonical_title': _rpoi.get('name', ''),
                        'english_title': _rpoi.get('english_title', ''),
                        'artist': _rpoi.get('artist', ''),
                        'publisher': _rpoi.get('publisher', ''),
                        'printed_by': _rpoi.get('printed_by', '') or _rpoi.get('printer', ''),
                        'credit_line': _rpoi.get('credit_line', ''),
                        'medium': _rpoi.get('medium', ''),
                        'venue_name': _museum_venue_name or '',
                    }
                    _next = next_focus_fact(_fmatrix, _tried)
                    if _next:
                        _rpoi['_focus_fact'] = _next['fact']
                        _rpoi['_focus_tried'] = sorted(_tried | {_next['key']})
                        print(f"    [LOCAL-491] step 7b: rotating to the "
                              f"{_next['key']} fact — {_next['why']}")
                        print(f"      focus: \"{_next['fact'][:100]}\"")
                    else:
                        print(f"    [LOCAL-491] step 7b: no unused fact left on the "
                              f"matrix — retrying without a rotation")
            except ImportError as _ff_err:
                print(f"    [LOCAL-491] focus-fact rotation unavailable ({_ff_err})")
            except Exception as _ff_err:
                print(f"    [LOCAL-491] rotation failed (non-fatal): {_ff_err}")

            if _storyless:
                # [LOCAL-487] The storyless case needs the opposite instruction
                # from the forbidding one: nothing was wrong, something is
                # MISSING. State the bar the draft failed, in the same terms the
                # detector used, so the second attempt is aimed at it.
                _instruction += (
                    "\n\nTHIS DRAFT HAS NO STORY, AND THAT IS WHAT MUST CHANGE.\n"
                    "It may be accurate and well written; it is still a description. "
                    "A story here means: ONE named person, across THREE OR MORE "
                    "consecutive sentences, DOING something — deciding, refusing, "
                    "persuading, travelling, failing — with something at stake for "
                    "them. Not 'X was an artist who worked in Paris'. Something "
                    "happened, to someone, and it mattered.\n"
                    "Use only the source material supplied. If the material will not "
                    "support such a story, write the shorter factual account rather "
                    "than inventing one — an invented story is worse than none.\n")
            _rpoi['_local474_forbidden'] = _instruction
            try:
                _retry_stats['retried'] += 1
                _r = _generate_description(
                    (_ri, _rpoi, _spine_stop, _fact_sheet, _story_type))
                _new_desc = _r[2] or ''
                # RE-GATE THE RETRY. The gate chain has already run and will not run
                # again, so an ungated retry could ship a fresh fabrication that the
                # first draft would have had caught — turning a safety improvement
                # into a hole. The deterministic gates are re-applied here, and the
                # comparison is made on what SURVIVES them, not on the raw draft.
                _new_desc = _regate_prose(_new_desc, _rpoi)
                # [LOCAL-487] ACCEPTANCE DEPENDS ON WHY WE RETRIED.
                #
                # For a hollowed-out stop, longer is the right test: the gates
                # deleted text and the retry is trying to replace it.
                #
                # For a STORYLESS stop it is exactly the wrong test — the entire
                # premise of step 7a is that length is not story, so accepting a
                # retry for being longer would re-import the bug in the acceptance
                # criterion after removing it from the trigger. The storyless
                # retry is kept only if it now CLEARS MICHAEL'S BAR, judged by the
                # same detector that rejected the first draft.
                _accept = False
                if _new_desc and not _new_desc.startswith('['):
                    if _top_value and not _hollowed and not _storyless:
                        # [D498] The most valuable stop was already the best one.
                        # Spending a generation on it is only justified by a
                        # MEASURED improvement, so it is judged on the step-5
                        # index — not on length, which is what it was allowed to
                        # add. `apply_story_index` is pure and costs no API call.
                        try:
                            from story_index_pass import (
                                apply_story_index as _d498_idx,
                                build_index_corpus as _d498_corpus)
                            _before_ix = _rpoi.get('_story_index')
                            _probe = [{'name': _rpoi.get('name', ''),
                                       'description': _new_desc}]
                            _d498_idx(_probe, corpus=_d498_corpus(
                                _exhibition_checklist_result, _stop_corpus_data))
                            _after_ix = _probe[0].get('_story_index')
                            _accept = (isinstance(_after_ix, (int, float))
                                       and isinstance(_before_ix, (int, float))
                                       and _after_ix > _before_ix)
                            print(f"    [D498] step 7c judged on the index, not on "
                                  f"length: {_before_ix} -> {_after_ix}, "
                                  f"accepted={_accept}")
                        except Exception as _d498_err:
                            print(f"    [D498] index unavailable — the longer draft "
                                  f"is REJECTED rather than accepted unmeasured "
                                  f"({_d498_err})")
                            _accept = False
                    elif _storyless and not _hollowed:
                        try:
                            from story_opportunity_scan import (
                                measure as _am, verdict as _av)
                            _accept = not _av(_am(_new_desc)).get(
                                'needs_additional_story', True)
                            print(f"    [LOCAL-487] retry judged on the story bar, "
                                  f"not on length: cleared={_accept}")
                        except Exception:
                            _accept = len(_new_desc.split()) > _now_wc
                    else:
                        _accept = len(_new_desc.split()) > _now_wc
                if _accept:
                    _rpoi['description'] = _new_desc
                    if _r[1]:
                        _rpoi['orientation'] = _r[1]
                    total_cost += _r[5] if len(_r) > 5 else 0
                    _retry_stats['improved'] += 1
                    print(f"    [LOCAL-474] regenerated and re-gated: "
                          f"{len(_new_desc.split())}w (was {_now_wc}w)")
                else:
                    _retry_stats['kept_original'] += 1
                    print(f"    [LOCAL-474] retry not better after re-gating — "
                          f"keeping the original gated text")
            except Exception as _rt_err:
                _retry_stats['kept_original'] += 1
                print(f"    [LOCAL-474] retry failed (non-fatal): {_rt_err}")
            finally:
                _rpoi.pop('_local474_forbidden', None)

        if _retry_stats['eligible']:
            print(f"\n  [LOCAL-474] retry summary: {_retry_stats['eligible']} eligible, "
                  f"{_retry_stats['retried']} retried, {_retry_stats['improved']} improved, "
                  f"{_retry_stats['kept_original']} kept original")
            print(f"  [LOCAL-487] triggers: {_retry_stats['trigger_floor']} hollowed "
                  f"by gates, {_retry_stats['trigger_no_story']} storyless "
                  f"(step 7a — Michael's bar, independent of length), "
                  f"{_retry_stats['trigger_top_value']} top-value "
                  f"(step 7c — larger allowance). Triggers overlap and are counted "
                  f"separately; they do not sum to 'eligible'.")
            print(f"  [LOCAL-474] each regenerated stop was re-gated before being "
                  f"accepted; a retry can only replace text it beats after gating.")

    # -------- [LOCAL-44] PHASE 5.10: Anti-preaching post-processing --------
    # Strip trailing sentences that instruct the listener what to feel, notice,
    # consider, or carry away. GPT often ignores prompt bans on these closings.
    print(f"\nPHASE 5.10: Anti-preaching cleanup (LOCAL-44)...")
    _PREACHING_CLOSERS = [
        # Imperative/instructive closings
        re.compile(r'^(As you stand (before|here|in front of).*?,?\s*)?(consider|reflect|ponder|imagine|let)\b', re.IGNORECASE),
        re.compile(r'^take\s+a\s+moment\s+to\b', re.IGNORECASE),
        re.compile(r'^allow\s+(yourself|your\s+(mind|imagination))\s+to\b', re.IGNORECASE),
        re.compile(r'^let\s+(the|this|these|your)\b', re.IGNORECASE),
        re.compile(r'^carry\s+(this|these|the)\b.*\b(with you|forward|away)\b', re.IGNORECASE),
        re.compile(r'^(perhaps|maybe)\s+(you\'ll|you\s+will|one\s+day|next\s+time)', re.IGNORECASE),
        # "What other X await your discovery"
        re.compile(r'\bwhat\s+other\s+\w+\s+(await|might|could)\b', re.IGNORECASE),
        # "To truly appreciate" condescension
        re.compile(r'^to\s+(truly|fully|really)\s+(appreciate|understand|grasp|comprehend)\b', re.IGNORECASE),
        # "It is worth noting / important to understand"
        re.compile(r'^it\s+is\s+(worth|important)\s+(noting|to\s+(note|understand|remember))\b', re.IGNORECASE),
    ]
    _preaching_count = 0
    for p in poi_list:
        _desc = p.get('description', '') or ''
        if not _desc:
            continue
        # Check last 1-2 sentences for preaching pattern
        _sentences = re.split(r'(?<=[.!?])\s+', _desc.strip())
        _removed = 0
        while _sentences:
            _last = _sentences[-1].strip()
            _is_preaching = False
            for _pp in _PREACHING_CLOSERS:
                if _pp.search(_last):
                    _is_preaching = True
                    break
            if _is_preaching:
                _sentences.pop()
                _removed += 1
                if _removed >= 2:
                    break  # Never strip more than 2 trailing sentences
            else:
                break
        if _removed:
            _preaching_count += _removed
            p['description'] = ' '.join(_sentences).strip()
    print(f"  [LOCAL-44] Stripped {_preaching_count} preaching closer(s)")

    # -------- [LOCAL-444] PHASE 5.20: Obligation audit --------
    # Post-draft per-stop obligation audit. Runs gpt-4o-mini per stop to identify
    # unfulfilled obligations (pointers that are never dereferenced).
    # Gated by L444_OBLIGATION_AUDIT env (default OFF, see D404; repair loop also OFF).
    # [LEAD D404] Default flipped to OFF. LEAD measured the audit at mean 4.06s/stop
    # live (3 calls: 3.50/5.81/2.86s) = ~24s added on a 6-stop tour, ~32s on 8 —
    # serial, on the default path, while D395/D402 are actively fighting wall time.
    # The calls are trivially parallelisable across stops; LOCAL-445 owns that and
    # the phase timers that will prove the cost. Flip on there, not here.
    _obligation_audit_enabled = os.environ.get('L444_OBLIGATION_AUDIT', 'false').lower() == 'true'
    _obligation_repair_enabled = os.environ.get('L444_OBLIGATION_REPAIR', 'false').lower() == 'true'

    if _obligation_audit_enabled:
        print(f"\n  [LOCAL-444] PHASE 5.20: Obligation audit (per-stop)...")
        try:
            from sentence_obligations import audit_stop_obligations, reset_audit_cost, get_audit_cost
            reset_audit_cost()
            _obl_audit_results = []
            _obl_total_unfulfilled = 0

            for _si, _poi in enumerate(poi_list):
                _desc = _poi.get('description', '')
                if not _desc or _desc.startswith('['):
                    _obl_audit_results.append(None)
                    continue

                _stop_name = _poi.get('name', f'Stop {_si + 1}')
                try:
                    _obl_result = audit_stop_obligations(_desc)
                    _obl_audit_results.append(_obl_result)
                    _unf = _obl_result['unfulfilled_count']
                    _obl_total_unfulfilled += _unf
                    if _unf > 0:
                        print(f"    Stop {_si+1} ({_stop_name}): {_unf} unfulfilled / {_obl_result['total_obligations']} total")
                except Exception as _obl_err:
                    print(f"    Stop {_si+1} ({_stop_name}): audit error — {_obl_err}")
                    _obl_audit_results.append(None)

            print(f"  [LOCAL-444] Obligation audit complete: {_obl_total_unfulfilled} total unfulfilled, cost=${get_audit_cost():.4f}")

            # Store results on poi_list for downstream (scorer reads unfulfilled_count)
            for _si, _poi in enumerate(poi_list):
                if _si < len(_obl_audit_results) and _obl_audit_results[_si] is not None:
                    _poi['_obligation_audit'] = _obl_audit_results[_si]
                    _poi['_unfulfilled_count'] = _obl_audit_results[_si]['unfulfilled_count']

        except ImportError as _obl_import_err:
            print(f"  [LOCAL-444] Obligation audit SKIPPED (import error: {_obl_import_err})")
        except Exception as _obl_err:
            print(f"  [LOCAL-444] Obligation audit FAILED: {_obl_err}")
    else:
        print(f"\n  [LOCAL-444] Obligation audit DISABLED by L444_OBLIGATION_AUDIT=false")

    # -------- [D512] Discover this domain's verbs of making, once --------
    #
    # Michael, 2026-08-23: *"'Add the making verbs' has to be different for each
    # museum type, so maybe in addition to the hardcoded set of verbs at the
    # beginning of the tour generation we can ask (only once) the verbs from
    # Serper appropriate for the museum type."*
    #
    # `_AGENCY_VERB` has been hand-extended three times and the hole reappeared
    # on 2026-08-23: `scratched`, `sketched`, `pulled` are absent, so on an
    # exhibition ABOUT people making objects the making sentences scored as
    # having no action. One SERP query (~$0.001), page-fetched for enough text
    # to measure frequency, and the pattern is WIDENED — never narrowed, so a
    # bad discovery can only make the scanner generous, not blind.
    if _storied_mode:
        try:
            from domain_verbs import install as _d512_install
            _d512_medium = ''
            for _d512_p in poi_list:
                if (_d512_p.get('medium') or '').strip():
                    _d512_medium = _d512_p['medium']
                    break
            _d512_install(venue_name=_museum_venue_name or location,
                          exhibition=_exh_name_resolved or '',
                          category=tour_category, medium=_d512_medium)
        except Exception as _d512_err:
            print(f"  [D512] verb discovery skipped (non-fatal): {_d512_err}")

    # -------- [D511] PHASE 5.20: the credit_line loop --------
    #
    # Michael, 2026-08-23: *"We have developed the loop of credit_line values,
    # query generation with calling Gemini and asserting sources with Serper, and
    # evaluated and developed stories. I want all of this into production before
    # I generate a new tour."*
    #
    # Eight modules were built this week and none had a production caller —
    # the orphan pattern the 7-step plan opened by complaining about. They are
    # composed in `story_production_loop.run_for_stop`, so this is ONE call
    # rather than four separate incisions into a 16,000-line function.
    #
    # HERE, after the gates and before the index, because the loop needs
    # POST-GATE prose: its credit_lines are mined from the stop's own text, and
    # mining pre-gate text would build a question on a sentence about to be
    # deleted. PHASE 5.21 then re-scores whatever this replaces.
    #
    # OFF BY DEFAULT (`STORY_LOOP_ENABLED=1`). It adds ~$0.05 and ~60s per stop,
    # which must be a decision rather than a surprise — and the flag is what
    # makes the A/B possible at all, since a single old-vs-new pair is noise at
    # sd 4.9 (D484, D480's three-run rule).
    if _storied_mode and tour_category == 'museum':
        try:
            from story_production_loop import run_for_stop as _d511_run, is_enabled as _d511_on
            from story_append_merge import merge_story_into_description as _d518_merge
            if _d511_on():
                print(f"\n  [D511] PHASE 5.20: credit_line loop — "
                      f"object record, seeds, challenge, adjudicate, gate")
                _d511_venue_url = getattr(locals().get('_det_entity'), 'official_url', '') or ''
                _d511_stats = {'stops': 0, 'accepted': 0, 'cost': 0.0,
                               'replaced': 0}
                for _d511_i, _d511_poi in enumerate(poi_list):
                    _d511_desc = _d511_poi.get('description') or ''
                    if not _d511_desc or _d511_desc.startswith('['):
                        continue
                    _d511_stats['stops'] += 1
                    print(f"\n  [D511] stop {_d511_i+1}: "
                          f"{_d511_poi.get('name','')[:44]}")
                    _d511_matrix = {
                        'canonical_title': _d511_poi.get('name', ''),
                        'english_title': _d511_poi.get('english_title', ''),
                        'artist': _d511_poi.get('artist', ''),
                        'publisher': _d511_poi.get('publisher', ''),
                        'printed_by': _d511_poi.get('printed_by', '') or _d511_poi.get('printer', ''),
                        'printer': _d511_poi.get('printer', '') or _d511_poi.get('printed_by', ''),
                        'collaborator': _d511_poi.get('collaborator', ''),
                        'credit_line': _d511_poi.get('credit_line', ''),
                        'medium': _d511_poi.get('medium', ''),
                        'venue_name': _museum_venue_name or '',
                    }
                    _d511_res = _d511_run(
                        _d511_matrix, _d511_desc,
                        exhibition=_exh_name_resolved or location,
                        venue_url=_d511_venue_url,
                        extra_entities=[_d511_poi.get('artist', '')])
                    _d511_stats['cost'] += _d511_res.get('cost_usd', 0.0)
                    total_cost += _d511_res.get('cost_usd', 0.0)
                    _d511_poi['_d511'] = _d511_res
                    if _d511_res.get('story'):
                        # [D518] The story REPLACES the prose it overlaps.
                        #
                        # This was `_d511_desc.rstrip() + ' ' + story` — plain
                        # concatenation — and Michael, 2026-08-24: *"saying things
                        # twice is the worst for listeners… Moreover, selecting the
                        # story topic based on the sentences made this problem."*
                        # The credit_lines are mined from this same prose, so the
                        # loop is guaranteed to research what the prose already
                        # said. On 2026-08-23 stop 3 ran "an Egyptian priest"
                        # (wrong) and "of Egyptian nobility" (right, corrected by
                        # the adjudicator) six sentences apart in one stop.
                        _d511_poi['_pre_d511_description'] = _d511_desc
                        _d511_merged, _d511_mrep = _d518_merge(
                            _d511_desc, _d511_res['story'],
                            work_titles=[_d511_poi.get('name', ''),
                                         _d511_poi.get('english_title', '')],
                            verbose=True)
                        _d511_poi['description'] = _d511_merged
                        _d511_poi['_d518_merge'] = _d511_mrep
                        _d511_stats['replaced'] += _d511_mrep['n_dropped']
                        print(f"    [D518] {_d511_mrep['n_dropped']} of "
                              f"{_d511_mrep['n_prose']} prose sentence(s) replaced "
                              f"by the story"
                              f"{' (drop cap hit)' if _d511_mrep['capped'] else ''}")
                        _d511_stats['accepted'] += 1
                        print(f"    [D511] story ACCEPTED from credit_line "
                              f"'{_d511_res['credit_line'][:44]}' "
                              f"(index {_d511_res.get('index')}, "
                              f"{_d511_res['gate']['max_sentences']} sentences)")
                    else:
                        # Michael's ruling: publishing nothing is correct, and a
                        # stop with no story is a retrieval failure to fix
                        # upstream, not a threshold to lower.
                        print(f"    [D511] no story passed the gate — stop keeps "
                              f"its descriptive text and publishes no story")
                print(f"\n  [D511] PHASE 5.20 summary: "
                      f"{_d511_stats['accepted']}/{_d511_stats['stops']} stops "
                      f"got a gated story, ~${_d511_stats['cost']:.3f}, "
                      f"[D518] {_d511_stats['replaced']} duplicated prose "
                      f"sentence(s) replaced")
        except ImportError as _d511_imp:
            print(f"  [D511] loop not importable, skipped (non-fatal): {_d511_imp}")
        except Exception as _d511_err:
            print(f"  [D511] loop FAILED, tour continues unchanged "
                  f"(non-fatal): {type(_d511_err).__name__}: {_d511_err}")

    # -------- [LOCAL-485] PHASE 5.21: Story valuation index (Michael's step 5) --------
    #
    # Michael's step 5 is "we evaluate the story assigning a value index".
    # `evaluate_story` has existed and been improved twice (D468 counts the object,
    # D470 fixed a year read as metres) and had **zero references in this file**.
    # It is step 5 of seven, built and unplugged — which is the shape of most of
    # the gap between the lab's 64 and production's 43 (SEVEN_POINTS_PLAN.md).
    #
    # IT REPORTS. IT DOES NOT GATE. D474 is explicit: the index is calibrated
    # against a single human judgement — Michael's, on one exhibition — and a gate
    # built on one calibration point will confidently delete good material. Wiring
    # it as a gate is a separate decision that needs its own evidence.
    #
    # WHY THIS IS FIRST of the seven, despite changing not one word of any tour:
    # it is the only way to know whether anything else helped. Before it, the sole
    # quality signal was a full tour run scored offline — $0.16, ~2.5 minutes, and
    # a single-run sd of 4.9 index points (D484), so a 3-run mean resolves nothing
    # smaller than ~10 points. A per-stop index printed during generation is free,
    # immediate, and per-stop, which is the granularity every remaining step needs.
    #
    # Runs last, immediately before assembly, so it scores exactly what ships —
    # after every gate, the retry, the anti-preaching strip and the obligation
    # audit have had their say.
    _story_index_stats = {}
    print(f"\n  [LOCAL-485] PHASE 5.21: Story valuation index (report only, never gates)...")
    try:
        from story_index_pass import (apply_story_index, build_index_corpus,
                                      format_index_report)
        _story_index_stats = apply_story_index(
            poi_list,
            corpus=build_index_corpus(_exhibition_checklist_result, _stop_corpus_data),
        )
        print(format_index_report(_story_index_stats))
    except ImportError as _xierr:
        print(f"  [LOCAL-485] WARNING: story_index_pass not importable — skipped ({_xierr})")
    except Exception as _xierr:
        print(f"  [LOCAL-485] ERROR: story index failed (non-fatal): {_xierr}")

    # PHASE 6: Assemble the complete tour
    _phase_timer.start('packing')
    print(f"\nPHASE 6: Assembling the complete tour...")
    
    # Create a better title that doesn't duplicate information
    # Use tour_category (internally corrected) not tour_type (raw client value) for display
    # For non-on_foot transport modes, derive a mode-specific display name
    _TRANSPORT_DISPLAY_NAMES = {
        'on_foot': None,  # uses tour_category as before
        'bike': 'Cycling',
        'vehicle': 'Driving',
        'country_scale': 'Road Trip',
    }
    # For animal mode, derive from the specific keyword matched
    _ANIMAL_DISPLAY_NAMES = {
        'camel': 'Camelback', 'camelback': 'Camelback',
        'horse': 'Horseback', 'horseback': 'Horseback',
        'dog': 'Dog Sledding', 'dogsled': 'Dog Sledding', 'dogsledding': 'Dog Sledding',
        'mushing': 'Dog Sledding', 'husky': 'Dog Sledding',
    }
    if transport_mode == 'animal':
        # Find which keyword matched to get the right display name
        import re as _re_title
        _animal_match = _re_title.search(r'\b(camel(?:back)?|horse(?:back)?|dog|dogsled(?:ding)?|mushing|husky)\b', location, _re_title.IGNORECASE)
        _display_category = _ANIMAL_DISPLAY_NAMES.get(_animal_match.group(1).lower(), 'Animal') if _animal_match else 'Animal'
    elif transport_mode in _TRANSPORT_DISPLAY_NAMES and _TRANSPORT_DISPLAY_NAMES[transport_mode]:
        _display_category = _TRANSPORT_DISPLAY_NAMES[transport_mode]
    else:
        _display_category = tour_category.replace('_', ' ').title()

    if tour_type.lower() in location.lower():
        # If tour type is already in the location name, don't repeat it
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        # Otherwise, create a title that incorporates the category naturally
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {_display_category} Tour"
    
    # [LOCAL-286] Tour-Category header: write the effective category.
    # For non-on_foot tours that classify as 'walking' (biking, driving, animal),
    # the header should reflect the transport mode, not the generic 'walking' fallback.
    _header_category = tour_category
    if tour_category == 'walking' and transport_mode == 'bike':
        _header_category = 'biking'
    elif tour_category == 'walking' and transport_mode == 'vehicle':
        _header_category = 'driving'
    elif tour_category == 'walking' and transport_mode == 'animal':
        _header_category = 'animal'
    elif tour_category == 'walking' and transport_mode == 'country_scale':
        _header_category = 'road_trip'
    complete_tour = tour_title + "\n" + f"Tour-Category: {_header_category}" + "\n\n"

    # -------- [LOCAL-11] Venue-identity mining (free path — no new API calls) --------
    _venue_identity_prompt_block = ""
    if tour_category == 'museum' and _story_corpus_result and _story_corpus_result.get('combined_text'):
        try:
            from story_miner import extract_venue_identity, format_venue_identity_for_prompt
            _venue_identity = extract_venue_identity(
                _story_corpus_result['combined_text'],
                _museum_venue_name or location,
            )
            # [LOCAL-21] When story elements exist, suppress founding facts from venue-identity
            # injection to avoid G4 conflicts (founding dates/verbs trigger G4 but may not match
            # story_elements). Architecture/design/programs are safe (no causal verbs).
            if _story_elements and 'founding' in _venue_identity:
                del _venue_identity['founding']
            _venue_identity_prompt_block = format_venue_identity_for_prompt(
                _venue_identity,
                _museum_venue_name or location,
            )
        except Exception as _vi_err:
            print(f"  [LOCAL-11] Venue-identity mining error (non-fatal): {_vi_err}")

    # [LOCAL-387] Framing detection moved to Phase 5 preamble (before _generate_description
    # closure) — see line ~8171. Variables _framing_case, _framing_source_phrase,
    # _framing_page_text are already bound.

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
            
            # [LOCAL-11] Inject venue-identity facts into prolog prompt when available
            _identity_section = ""
            if _venue_identity_prompt_block:
                _identity_section = f"\n\n{_venue_identity_prompt_block}"
            
            # [LOCAL-259] Four-part prolog structure per Michael's specification.
            # Parts: 1) Tour name + transport, 2) Route/physicality, 3) Purpose/intrigue, 4) Forward connection.
            # Each part is sourced from real data: transport_mode, coordinates, stop_corpus.

            # --- Part 2 data: compute distance from coordinates ---
            _prolog_stop_names = [p.get('name', '') for p in poi_list]
            _prolog_coords = []
            for _pp in poi_list:
                _pc = _parse_coords(_pp.get('coordinates', ''))
                if _pc:
                    _prolog_coords.append(_pc)
            _prolog_total_km = 0.0
            if len(_prolog_coords) >= 2:
                for _ci in range(len(_prolog_coords) - 1):
                    _prolog_total_km += _haversine_km(_prolog_coords[_ci], _prolog_coords[_ci + 1])
            _prolog_distance_str = f"{_prolog_total_km:.0f} km" if _prolog_total_km >= 1 else f"{_prolog_total_km * 1000:.0f} m"

            # [LOCAL-286] Distance floor: if under 50 meters, the distance is
            # meaningless (single-building / co-located stops). Omit it entirely.
            _prolog_distance_meaningful = (_prolog_total_km * 1000) >= 50

            # [LOCAL-286] Detect museum tours for prolog specialization
            _is_museum_prolog = (tour_category == 'museum')

            # Transport mode display
            _prolog_transport_display = {
                'on_foot': 'walking', 'bike': 'cycling', 'vehicle': 'driving',
                'animal': 'riding', 'country_scale': 'road trip'
            }.get(transport_mode, transport_mode)

            # [LOCAL-330] Derive a clean place name for the prolog location slot.
            # Uses the module-level _prolog_place() helper (prefix-anchored strip).
            _prolog_place_name = _prolog_place(location)

            # --- Part 3 data: extract sourced facts from stop_corpus ---
            _prolog_corpus_facts = {}  # stop_name → [fact strings]
            if _stop_corpus_data:
                for _sc_name, _sc_data in _stop_corpus_data.items():
                    if _sc_data and _sc_data.get('passages'):
                        _facts_for_stop = []
                        for _passage in _sc_data['passages'][:8]:
                            # Extract sentences with dates or proper nouns + verbs
                            _p_sents = re.split(r'(?<=[.!?])\s+', _passage)
                            for _ps in _p_sents:
                                if len(_ps) < 20:
                                    continue
                                _has_date = bool(re.search(r'\b\d{3,4}\b', _ps))
                                _has_proper = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', _ps))
                                _has_verb = bool(re.search(
                                    r'\b(?:built|founded|opened|painted|wrote|designed|'
                                    r'constructed|captured|destroyed|transformed|visited|'
                                    r'published|established|ordered|integrated|settled|'
                                    r'mentioned|served|drew|required|created)\b', _ps, re.IGNORECASE))
                                if _has_date or (_has_proper and _has_verb):
                                    _facts_for_stop.append(_ps.strip())
                        _prolog_corpus_facts[_sc_name] = _facts_for_stop[:6]

            # Also gather from _story_elements if available
            _prolog_story_facts = []
            if _story_elements:
                for _se in _story_elements[:12]:
                    _se_text = _se.get('text', '')
                    if _se_text and len(_se_text) > 15:
                        _prolog_story_facts.append(f"({_se.get('type','?')}) {_se_text}")

            # Build the corpus facts section for the prompt
            _corpus_facts_prompt = ""
            if _prolog_corpus_facts:
                _corpus_lines = []
                for _cfn, _cff in _prolog_corpus_facts.items():
                    if _cff:
                        _corpus_lines.append(f"\n  [{_cfn}]:")
                        for _cf in _cff:
                            _corpus_lines.append(f"    - {_cf[:200]}")
                _corpus_facts_prompt = "\n".join(_corpus_lines)
            if _prolog_story_facts:
                _corpus_facts_prompt += "\n\n  [Story elements]:\n" + "\n".join(
                    f"    - {sf}" for sf in _prolog_story_facts[:8])

            # --- Part 4 data: REMOVED from spine prompt (LOCAL-270) ---
            # Part 4 (forward connection) is now composed AFTER stop narrations
            # are generated and gated, from the actual delivered text.
            # See PHASE 5.96 below.

            # --- Build the three-part prolog prompt (LOCAL-270: Part 4 moved to post-narration) ---
            # [LOCAL-286] Part 1 and Part 2 branch for museums vs geographic tours.
            # Museums: no locomotion word, venue+collection instead; stop count instead of distance.
            # Geographic: existing behaviour (transport mode, endpoints, distance).
            if _is_museum_prolog:
                _part1_instruction = (
                    'State the tour name and the venue. Do NOT mention walking or any mode of '
                    'transport — inside a museum, walking is the default and stating it is empty. '
                    'Example shape: "You are about to explore the [venue name] in [city]." '
                    'Name the venue and its collection or character.'
                )
                _part2_instruction = (
                    f"Describe what the visitor will encounter: {len(_prolog_stop_names)} works "
                    f"from the collection. Do NOT use geographic language like 'route', 'stretches', "
                    f"'journey', or state a distance — these are rooms, not a road. "
                    f"Say something true about the tour's shape: the number of works, the nature of "
                    f"the collection, or a unifying medium/period if the stop names suggest one. "
                    f"Do NOT invent floor or wing locations unless the sourced facts explicitly state them."
                )
            else:
                _part1_instruction = (
                    f'State the tour name and mode of transport. '
                    f'Example shape: "You are about to embark on a [{_prolog_transport_display}] '
                    f'journey through [{_prolog_place_name}]."'
                )
                if len(_prolog_stop_names) >= 2 and _prolog_stop_names[0] != _prolog_stop_names[-1] and _prolog_distance_meaningful:
                    _part2_instruction = (
                        f"State the transport mode again concretely, name the endpoints "
                        f"({_prolog_stop_names[0]} to {_prolog_stop_names[-1]}), give the "
                        f"approximate distance ({_prolog_distance_str}). Describe only terrain/"
                        f"landscape features that are KNOWN from the sourced facts or that are "
                        f"trivially true of the geography (e.g. \"coastal\" for a coast). Do NOT "
                        f"invent elevation, flatness, or terrain claims unless supported by corpus "
                        f"facts above."
                    )
                elif len(_prolog_stop_names) >= 2 and _prolog_stop_names[0] != _prolog_stop_names[-1] and not _prolog_distance_meaningful:
                    # [LOCAL-286] Distance under floor — omit the distance clause entirely
                    _part2_instruction = (
                        f"Name the endpoints ({_prolog_stop_names[0]} to {_prolog_stop_names[-1]}). "
                        f"Do NOT state a distance — the stops are too close together for distance "
                        f"to be meaningful. Describe only terrain/landscape features that are KNOWN "
                        f"from the sourced facts or that are trivially true of the geography."
                    )
                else:
                    _part2_instruction = (
                        "State the transport mode again concretely and describe what the visitor "
                        "will experience at this single stop. Do NOT describe a route between two "
                        "endpoints — this tour has only one location."
                    )

            _prolog_prompt = f"""[LOCAL-259/LOCAL-270] Write a tour prolog in EXACTLY three sequential parts. Each part has a specific purpose. Output them as one flowing paragraph (no labels, no numbering), but ensure all three parts are present in order.

TOUR DATA:
- Tour name/location: {_prolog_place_name}
- Transport mode: {_prolog_transport_display}
- Tour category: {'museum' if _is_museum_prolog else 'geographic'}
- Stops: {', '.join(_prolog_stop_names)}
- Number of stops: {len(_prolog_stop_names)}
- Stop 1 coordinates: {poi_list[0].get('coordinates', 'unknown') if poi_list else 'unknown'}
- Stop {len(poi_list)} coordinates: {poi_list[-1].get('coordinates', 'unknown') if poi_list else 'unknown'}
- Approximate straight-line distance between first and last stop: {_prolog_distance_str if _prolog_distance_meaningful else 'N/A (single building)'}
- Theme: {_connecting_thread}"""

            # [LOCAL-364] Honest degradation: inject a note into the prolog when
            # the exhibition checklist could not be retrieved and we fell back to
            # the creator filter. The listener should know.
            if _exhibition_scope is not None and _exhibition_stops_source == 'creator_filter':
                _364_fallback_note = (
                    f"\n- IMPORTANT NOTE FOR PROLOG: This tour was requested as an exhibition "
                    f"tour, but the exhibition's actual checklist could not be retrieved from "
                    f"the venue website. The stops below are works by the exhibition's artists "
                    f"from the venue's permanent collection. Mention this honestly in Part 1: "
                    f"'We were unable to confirm the exact works on display in the exhibition, "
                    f"so this tour features works by the same artists from the museum's collection.'"
                )
                _prolog_prompt += _364_fallback_note
            elif _exhibition_scope is not None and _exhibition_stops_source == 'partial':
                _364_partial_note = (
                    f"\n- NOTE: This tour draws from a partial exhibition checklist (only "
                    f"highlighted works were published on the venue website). Mention briefly "
                    f"that additional works may be on display."
                )
                _prolog_prompt += _364_partial_note

            _prolog_prompt += f"""

SOURCED FACTS (use ONLY these for any factual claim):
{_corpus_facts_prompt if _corpus_facts_prompt else '  (no corpus facts available — use only general geographic/transport facts for Part 2, omit specific historical claims in Part 3)'}

THE THREE PARTS (produce in this exact order, flowing as natural prose):

PART 1 — TOUR INTRODUCTION (1-2 sentences):
{_part1_instruction}

PART 2 — TOUR SHAPE (2-3 sentences):
{_part2_instruction}

PART 3 — PURPOSE/INTRIGUE (2-4 sentences):
This is the story hook — WHY someone takes this tour. Thread sourced facts into a causal or thematic sentence. Use ONLY facts from the SOURCED FACTS section above. If the facts support a causal link (X led to Y, which explains Z), write it. If they do NOT support a causal chain, write the plainest true version: state two sourced facts without manufacturing a connection between them. A false causal claim is worse than a plain factual one.

DO NOT include a forward connection to upcoming stops — that will be added separately after the stops are written.

CONSTRAINTS:
- Total length: 80-150 words (MUST be at least 80 words — short prologs are rejected)
- Second-person present tense throughout
- Every date, name, or causal claim MUST come from SOURCED FACTS above
- No questions at the end
- ABSOLUTELY NO sensory fabrication: no "sun-drenched", "azure waters", "gentle breeze", "sparkling", "shimmering", "rugged cliffs" unless you have evidence. State geography plainly: "coastal", "hillside", "peninsula".
- No adjective-heavy fillers like "rich tapestry", "vibrant pulse", "timeless charm"
- Return ONLY the paragraph text, no labels or part markers"""

            # [LOCAL-21] Append grounding constraint if story elements exist
            if _story_elements:
                _elem_facts = "\n".join(
                    f"  - ({e.get('type','?')}) {e.get('text','')}"
                    for e in _story_elements[:10]
                )
                _prolog_prompt += f"""

GROUNDING CONSTRAINT (reinforcement):
These are the documented story elements. Any historical claim must trace to one of these:
{_elem_facts}"""

            # [SQ-S6b] Inject thread promise into prolog prompt
            _thread_prolog_section = ""
            if _thread_result and _thread_result.mode == "threaded" and _thread_result.prolog_promise:
                _thread_prolog_section = f"""

NARRATIVE THREAD (weave into Part 3 as the central intrigue):
{_thread_result.prolog_promise}"""

            _prolog_prompt += _thread_prolog_section

            # [LOCAL-382] Inject exhibition thesis / venue purpose into prolog
            if _framing_case != 'none':
                try:
                    _thesis_prolog_block = build_exhibition_thesis_prolog_block(
                        framing_case=_framing_case,
                        source_phrase=_framing_source_phrase,
                        page_text=_framing_page_text,
                    )
                    if _thesis_prolog_block:
                        _prolog_prompt += _thesis_prolog_block
                        print(f"  [LOCAL-382] Thesis block injected into prolog ({len(_thesis_prolog_block)} chars)")
                except Exception as _tp_err:
                    print(f"  [LOCAL-382] Thesis prolog injection error (non-fatal): {_tp_err}")

            # [LOCAL-119] Prolog LLM call with retry for transient failures.
            # Transient: timeout, connection error, HTTP 429/500/502/503/504.
            # Non-transient (no retry): 400/401/403/404 — prompt or auth issue.
            import requests as _prolog_requests
            _prolog_logger = logging.getLogger("generate_tour_text.prolog")
            _PROLOG_TRANSIENT_CODES = {429, 500, 502, 503, 504}
            _PROLOG_MAX_RETRIES = 1  # 1 retry = 2 attempts total
            _prolog_attempt = 0
            _prolog_success = False
            _prolog_last_status = None

            while _prolog_attempt <= _PROLOG_MAX_RETRIES:
                try:
                    _prolog_resp = _prolog_requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                            "messages": [
                                {"role": "system", "content": "You write immersive, literary audio tour introductions."},
                                {"role": "user", "content": _prolog_prompt},
                            ],
                            "temperature": 0.8,
                            "max_tokens": 380,
                        },
                        timeout=15,
                    )
                    _prolog_last_status = _prolog_resp.status_code
                    if _prolog_resp.status_code == 200:
                        _prolog_text = _prolog_resp.json()["choices"][0]["message"]["content"].strip()
                        if _prolog_text.startswith('"') and _prolog_text.endswith('"'):
                            _prolog_text = _prolog_text[1:-1].strip()
                        _saved_prolog = _prolog_text
                        _prolog_success = True
                        if _prolog_attempt > 0:
                            print(f"  [R2] Prolog saved for Stop 1 ({len(_prolog_text.split())} words) [retry succeeded]")
                        else:
                            print(f"  [R2] Prolog saved for Stop 1 ({len(_prolog_text.split())} words)")
                        break
                    elif _prolog_resp.status_code in _PROLOG_TRANSIENT_CODES:
                        # Transient — retry after backoff
                        _prolog_attempt += 1
                        if _prolog_attempt <= _PROLOG_MAX_RETRIES:
                            _backoff = 2 ** _prolog_attempt  # 2s on first retry
                            _prolog_logger.warning(
                                f"[LOCAL-119] Prolog LLM transient failure (HTTP {_prolog_resp.status_code}), "
                                f"retrying in {_backoff}s (attempt {_prolog_attempt + 1}/{_PROLOG_MAX_RETRIES + 1})"
                            )
                            time.sleep(_backoff)
                        else:
                            _prolog_logger.warning(
                                f"[LOCAL-119] Prolog LLM transient failure (HTTP {_prolog_resp.status_code}), "
                                f"retries exhausted — falling back"
                            )
                    else:
                        # Non-transient (400/401/403/404) — do not retry, just fall back
                        _prolog_logger.warning(
                            f"[LOCAL-119] Prolog LLM non-transient failure (HTTP {_prolog_resp.status_code}), "
                            f"no retry — falling back"
                        )
                        break
                except (_prolog_requests.exceptions.Timeout, _prolog_requests.exceptions.ConnectionError) as _net_err:
                    # Network-level transient failure — retry
                    _prolog_attempt += 1
                    if _prolog_attempt <= _PROLOG_MAX_RETRIES:
                        _backoff = 2 ** _prolog_attempt
                        _prolog_logger.warning(
                            f"[LOCAL-119] Prolog LLM network error ({type(_net_err).__name__}), "
                            f"retrying in {_backoff}s (attempt {_prolog_attempt + 1}/{_PROLOG_MAX_RETRIES + 1})"
                        )
                        time.sleep(_backoff)
                    else:
                        _prolog_logger.warning(
                            f"[LOCAL-119] Prolog LLM network error ({type(_net_err).__name__}), "
                            f"retries exhausted — falling back"
                        )
                except Exception as _parse_err:
                    # Unexpected error (e.g. JSON parse failure on 200) — non-transient
                    _prolog_logger.warning(
                        f"[LOCAL-119] Prolog LLM unexpected error ({type(_parse_err).__name__}: {_parse_err}), "
                        f"no retry — falling back"
                    )
                    break

            # [LOCAL-119] Improved fallback: if prolog generation failed, use Stop 1's
            # first POI description sentence (full prose) rather than the raw hook
            # (which is a terse 11-25 word formulaic question).
            if not _prolog_success:
                # Try to get Stop 1's description as better fallback prose
                _fallback_used = None
                if poi_list and poi_list[0].get("description"):
                    _stop1_desc = poi_list[0]["description"].strip()
                    # Extract first two sentences (gives ~30-60 words of real prose)
                    _sentences = re.split(r'(?<=[.!])\s+', _stop1_desc)
                    if len(_sentences) >= 2:
                        _fallback_prose = ' '.join(_sentences[:2])
                        _saved_prolog = _fallback_prose
                        _fallback_used = "stop1_prose"
                    elif _sentences:
                        _saved_prolog = _sentences[0]
                        _fallback_used = "stop1_first_sentence"
                # If Stop 1 description unavailable, fall back to raw hook (last resort)
                if not _fallback_used and _tour_hook:
                    _saved_prolog = _tour_hook
                    _fallback_used = "raw_hook"

                if _fallback_used:
                    _prolog_logger.warning(
                        f"[LOCAL-119] Prolog fallback active: using '{_fallback_used}' "
                        f"({len(_saved_prolog.split())} words). Tour delivery continues."
                    )
                else:
                    _prolog_logger.warning(
                        "[LOCAL-119] Prolog generation failed and no fallback text available. "
                        "Tour will open directly on Stop 1 content without prolog."
                    )
        except Exception as e:
            # [LOCAL-119] Outer safety net — prolog failure must NEVER block tour delivery.
            # This catches any error not handled inside the retry loop (e.g. spine parsing).
            _prolog_logger = logging.getLogger("generate_tour_text.prolog")
            _prolog_logger.warning(
                f"[LOCAL-119] Prolog block outer error ({type(e).__name__}: {e}). "
                f"Tour delivery continues without prolog."
            )

    # -------- [LOCAL-244] PHASE 5.9: Prolog gating (R9, R10, subject routine) --------
    # D64: the prolog is generated by a separate LLM call and injected at assembly.
    # Until LOCAL-244 it bypassed all style/quality gates. Now we apply the same
    # gates that run over stop descriptions: R9 (generic), R10 (unfulfilled promise),
    # and the subject routine. Prolog findings are logged SEPARATELY.
    if _saved_prolog:
        _prolog_words_before = len(_saved_prolog.split())
        _prolog_deletions_verbatim = []
        _prolog_r9_deleted = 0
        _prolog_r10_deleted = 0
        _prolog_subject_expanded = 0
        _prolog_subject_deleted = 0
        _prolog_subject_cost = 0.0

        print(f"\n  [LOCAL-244] PHASE 5.9: Prolog gating (R9, R10, subject routine)...")
        print(f"  [LOCAL-244] Prolog before gates: {_prolog_words_before} words")

        # --- R9: generic-sentence deletion on prolog ---
        _r9_disabled_for_prolog = os.environ.get('DISABLE_R9_DELETION', '').strip() == '1'
        if not _r9_disabled_for_prolog:
            try:
                from style_validator_detector import apply_r9_to_description as _prolog_r9_apply
                _prolog_after_r9, _pr9_del, _pr9_emp = _prolog_r9_apply(_saved_prolog)
                if _pr9_del > 0:
                    # Identify what was removed
                    _old_sents = set(s.strip() for p in _saved_prolog.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _prolog_after_r9.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _prolog_deletions_verbatim.append(('R9_GENERIC', s))
                    _saved_prolog = _prolog_after_r9
                    _prolog_r9_deleted = _pr9_del
                    print(f"  [LOCAL-244] Prolog R9: {_pr9_del} sentence(s) deleted")
                else:
                    print(f"  [LOCAL-244] Prolog R9: 0 deletions")
            except ImportError as _e:
                print(f"  [LOCAL-244] Prolog R9: SKIPPED (import error: {_e})")

        # --- [LOCAL-286] R7: hallucinated-sensory deletion on prolog ---
        # The prolog was never passed through R7 (PHASE 5.14 iterates poi_list only).
        # Round 34 proved the gap: "azure waters", "sun-kissed peninsula", "rugged cliffs"
        # all survived because R7 never saw the prolog text.
        _r7_disabled_for_prolog = os.environ.get('DISABLE_R7_DELETION', '').strip() == '1'
        if not _r7_disabled_for_prolog:
            try:
                from style_validator_detector import apply_r7_to_description as _prolog_r7_apply
                _prolog_after_r7, _pr7_del, _pr7_emp = _prolog_r7_apply(_saved_prolog)
                if _pr7_del > 0:
                    _old_sents = set(s.strip() for p in _saved_prolog.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _prolog_after_r7.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _prolog_deletions_verbatim.append(('R7_HALLUCINATED_SENSORY', s))
                    _saved_prolog = _prolog_after_r7
                    print(f"  [LOCAL-286] Prolog R7: {_pr7_del} sentence(s) deleted")
                else:
                    print(f"  [LOCAL-286] Prolog R7: 0 deletions")
            except ImportError as _e:
                print(f"  [LOCAL-286] Prolog R7: SKIPPED (import error: {_e})")

        # --- R10: unfulfilled-promise deletion on prolog ---
        _r10_disabled_for_prolog = os.environ.get('DISABLE_R10_DELETION', '').strip() == '1'
        if not _r10_disabled_for_prolog:
            try:
                from style_validator_detector import apply_r10_to_description as _prolog_r10_apply
                _prolog_after_r10, _pr10_del, _pr10_emp = _prolog_r10_apply(_saved_prolog)
                if _pr10_del > 0:
                    _old_sents = set(s.strip() for p in _saved_prolog.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _prolog_after_r10.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _prolog_deletions_verbatim.append(('R10_UNFULFILLED_PROMISE', s))
                    _saved_prolog = _prolog_after_r10
                    _prolog_r10_deleted = _pr10_del
                    print(f"  [LOCAL-244] Prolog R10: {_pr10_del} sentence(s) deleted")
                else:
                    print(f"  [LOCAL-244] Prolog R10: 0 deletions")
            except ImportError as _e:
                print(f"  [LOCAL-244] Prolog R10: SKIPPED (import error: {_e})")

        # --- Subject routine: expand or remove promises in prolog ---
        _subject_disabled_for_prolog = os.environ.get('DISABLE_SUBJECT_ROUTINE', '').strip() == '1'
        if not _subject_disabled_for_prolog and _saved_prolog.strip():
            try:
                from subject_validate_expand import process_paragraph as _prolog_subject_process
                from subject_validate_expand import is_subject_routine_enabled as _prolog_sr_enabled
                if _prolog_sr_enabled():
                    # Use Stop 1 name as context for the subject routine
                    _stop1_name = poi_list[0]['name'] if poi_list else "Tour Introduction"
                    _sr_result = _prolog_subject_process(
                        paragraph=_saved_prolog,
                        stop_title=_stop1_name,
                        venue_name=location if location else "",
                        conn=None,
                        existence_verified=True,
                    )
                    _prolog_subject_expanded = _sr_result['expanded_count']
                    _prolog_subject_deleted = _sr_result['deleted_count']
                    _prolog_subject_cost = _sr_result['cost']
                    if _sr_result['expanded_count'] > 0 or _sr_result['deleted_count'] > 0:
                        _saved_prolog = _sr_result['processed']
                        for p in _sr_result.get('promises_found', []):
                            if p.get('outcome') == 'deleted':
                                _prolog_deletions_verbatim.append(
                                    ('SUBJECT_DELETED', p.get('sentence', '')))
                    print(f"  [LOCAL-244] Prolog subject: {_prolog_subject_expanded} expanded, "
                          f"{_prolog_subject_deleted} deleted, cost=${_prolog_subject_cost:.4f}")
                else:
                    print(f"  [LOCAL-244] Prolog subject: routine not enabled")
            except ImportError as _e:
                print(f"  [LOCAL-244] Prolog subject: SKIPPED (import error: {_e})")

        _prolog_words_after = len(_saved_prolog.split()) if _saved_prolog.strip() else 0
        print(f"  [LOCAL-244] Prolog after gates: {_prolog_words_after} words "
              f"(delta: {_prolog_words_after - _prolog_words_before})")
        if _prolog_deletions_verbatim:
            print(f"  [LOCAL-244] Prolog deletions ({len(_prolog_deletions_verbatim)}):")
            for _rule, _sent in _prolog_deletions_verbatim:
                print(f"    [{_rule}] \"{_sent[:100]}{'...' if len(_sent) > 100 else ''}\"")

        # If prolog collapsed to near-nothing, warn but still inject what remains
        if _prolog_words_after < 15 and _prolog_words_before > 30:
            print(f"  [LOCAL-244] ⚠️  WARNING: Prolog collapsed from {_prolog_words_before} to "
                  f"{_prolog_words_after} words — nearly empty stub")

        # -------- [LOCAL-251] PHASE 5.91: Prolog stop-name disambiguation --------
        # The prolog previews content from multiple stops. Because it is injected
        # into stop 1, a deictic reference like "this town" or "this village" after
        # mentioning a stop-2 landmark will be heard as referring to stop 1.
        # Fix: when a sentence mentions a named feature from a later stop and is
        # followed by a deictic ("this town", "this village", "this modern town",
        # "this coastal town"), replace the deictic with the stop's actual name.
        if _saved_prolog and len(poi_list) > 1:
            _stop_names_for_prolog = [p.get('name', '') for p in poi_list]
            _stop1_name = _stop_names_for_prolog[0] if _stop_names_for_prolog else ''
            # Build a map: feature → stop name (for stops beyond stop 1)
            # Features come from the corpus and from the stop names themselves
            _later_stop_features = {}
            for _psi in range(1, len(poi_list)):
                _ps_name = poi_list[_psi].get('name', '')
                if _ps_name:
                    _later_stop_features[_ps_name.lower()] = _ps_name
                    # Also register short forms (e.g. "Villefranche" for "Villefranche-sur-Mer")
                    _short = _ps_name.split('-')[0].split(',')[0].strip()
                    if len(_short) > 3:
                        _later_stop_features[_short.lower()] = _ps_name

            # Check if the prolog mentions any later-stop name followed by a deictic
            _deictic_pattern = re.compile(
                r'\bthis\s+(?:modern|coastal|ancient|medieval|historic|charming|quaint|vibrant|picturesque|small|old)?\s*'
                r'(?:town|village|city|place|port|harbor|harbour|commune|settlement)\b',
                re.IGNORECASE
            )
            _prolog_sentences = re.split(r'(?<=[.!?])\s+', _saved_prolog)
            _prolog_modified = False
            for _psi, _psent in enumerate(_prolog_sentences):
                _psent_lower = _psent.lower()
                _found_later_stop = None
                for _feat_key, _feat_stop in _later_stop_features.items():
                    if _feat_key in _psent_lower:
                        _found_later_stop = _feat_stop
                        break
                if _found_later_stop and _found_later_stop.lower() != _stop1_name.lower():
                    # This sentence references a later stop — check for deictics
                    _dm = _deictic_pattern.search(_psent)
                    if _dm:
                        _replacement = _found_later_stop
                        _prolog_sentences[_psi] = _psent[:_dm.start()] + _replacement + _psent[_dm.end():]
                        _prolog_modified = True
                        print(f"  [LOCAL-251] Prolog disambiguated: '{_dm.group()}' → '{_replacement}'")
            if _prolog_modified:
                _saved_prolog = ' '.join(_prolog_sentences)

    # -------- [LOCAL-246] PHASE 5.95: Orientation gating (R9, R10) --------
    # D136/D137: Orientation paragraphs are generated by the same LLM call as
    # descriptions but extracted separately ("Orientation:" split) and injected
    # at assembly without passing through any gate. Same class of gap as the
    # prolog (LOCAL-244). Gate them now with R9 and R10, same thresholds.
    # Navigation exemption (D107, D122) is built into both R9 and R10: any
    # sentence classified as route-movement (_is_style_navigation_sentence) is
    # skipped by both deleters. Orientation text that directs physical bearing
    # via route verbs + directional words survives; unfulfilled promises do not.
    _orient_total_words_before = 0
    _orient_total_words_after = 0
    _orient_stops_affected = 0
    _orient_deletions_verbatim = []

    print(f"\n  [LOCAL-246] PHASE 5.95: Orientation gating (R9, R10)...")

    _r9_disabled_for_orient = os.environ.get('DISABLE_R9_DELETION', '').strip() == '1'
    _r10_disabled_for_orient = os.environ.get('DISABLE_R10_DELETION', '').strip() == '1'

    for _oi, _opoi in enumerate(poi_list):
        _orient_text = _opoi.get('orientation', '')
        if not _orient_text or not _orient_text.strip():
            continue
        # Skip default/fallback orientation (nothing to gate)
        if _orient_text.strip() in (
            "Position yourself to best view this location.",
            "Position yourself to best view this artwork.",
            "Look for this work in the galleries.",
        ):
            continue

        _ow_before = len(_orient_text.split())
        _orient_total_words_before += _ow_before
        _orient_changed = False

        # --- R7: hallucinated-sensory deletion on orientation ---
        _r7_disabled_for_orient = os.environ.get('DISABLE_R7_DELETION', '').strip() == '1'
        if not _r7_disabled_for_orient:
            try:
                from style_validator_detector import apply_r7_to_description as _orient_r7_apply
                _orient_after_r7, _or7_del, _or7_emp = _orient_r7_apply(_orient_text)
                if _or7_del > 0:
                    _old_sents = set(s.strip() for p in _orient_text.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _orient_after_r7.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _orient_deletions_verbatim.append((_oi + 1, 'R7_HALLUCINATED_SENSORY', s))
                    _orient_text = _orient_after_r7
                    _orient_changed = True
                    print(f"    Stop {_oi+1} orientation R7: {_or7_del} sentence(s) deleted")
            except ImportError as _e:
                print(f"    Stop {_oi+1} orientation R7: SKIPPED (import error: {_e})")

        # --- R9: generic-sentence deletion on orientation ---
        if not _r9_disabled_for_orient:
            try:
                from style_validator_detector import apply_r9_to_description as _orient_r9_apply
                _orient_after_r9, _or9_del, _or9_emp = _orient_r9_apply(_orient_text)
                if _or9_del > 0:
                    _old_sents = set(s.strip() for p in _orient_text.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _orient_after_r9.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _orient_deletions_verbatim.append((_oi + 1, 'R9_GENERIC', s))
                    _orient_text = _orient_after_r9
                    _orient_changed = True
                    print(f"    Stop {_oi+1} orientation R9: {_or9_del} sentence(s) deleted")
            except ImportError as _e:
                print(f"    Stop {_oi+1} orientation R9: SKIPPED (import error: {_e})")

        # --- R10: unfulfilled-promise deletion on orientation ---
        if not _r10_disabled_for_orient:
            try:
                from style_validator_detector import apply_r10_to_description as _orient_r10_apply
                _orient_after_r10, _or10_del, _or10_emp = _orient_r10_apply(_orient_text)
                if _or10_del > 0:
                    _old_sents = set(s.strip() for p in _orient_text.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    _new_sents = set(s.strip() for p in _orient_after_r10.split('\n\n')
                                     for s in re.split(r'(?<=[.!?])\s+', p) if s.strip())
                    for s in _old_sents - _new_sents:
                        _orient_deletions_verbatim.append((_oi + 1, 'R10_UNFULFILLED_PROMISE', s))
                    _orient_text = _orient_after_r10
                    _orient_changed = True
                    print(f"    Stop {_oi+1} orientation R10: {_or10_del} sentence(s) deleted")
            except ImportError as _e:
                print(f"    Stop {_oi+1} orientation R10: SKIPPED (import error: {_e})")

        if _orient_changed:
            # If orientation collapsed to nothing, use a minimal fallback
            if not _orient_text.strip():
                _orient_text = "Position yourself to best view this location."
                print(f"    Stop {_oi+1} orientation: COLLAPSED — using fallback")
            poi_list[_oi]['orientation'] = _orient_text
            _orient_stops_affected += 1

        _ow_after = len(_orient_text.split()) if _orient_text.strip() else 0
        _orient_total_words_after += _ow_after

    print(f"  [LOCAL-246] Orientation gating summary:")
    print(f"    Words before: {_orient_total_words_before}")
    print(f"    Words after:  {_orient_total_words_after}")
    print(f"    Delta: {_orient_total_words_after - _orient_total_words_before}")
    print(f"    Stops affected: {_orient_stops_affected}/{len(poi_list)}")
    if _orient_deletions_verbatim:
        print(f"    Deletions ({len(_orient_deletions_verbatim)}):")
        for _stop_n, _rule, _sent in _orient_deletions_verbatim:
            print(f"      [Stop {_stop_n}][{_rule}] \"{_sent[:100]}{'...' if len(_sent) > 100 else ''}\"")

    # Collapse warning (same threshold as prolog)
    if _orient_total_words_before > 0:
        _orient_ratio = _orient_total_words_after / _orient_total_words_before
        if _orient_ratio < 0.3:
            print(f"  [LOCAL-246] ⚠️  WARNING: Orientation collapsed to {_orient_ratio:.0%} of original — "
                  f"listener may not know where to stand")

    # -------- [LOCAL-270] PHASE 5.96: Compose Part 4 from delivered narrations --------
    # [LOCAL-280] Also persist intrigue-ranked facts for the closing recap.
    _recap_ranked_facts = []  # Will be populated by LOCAL-276 ranking if available

    # Part 4 (forward connection) was removed from the prolog prompt because the spine
    # writes it before stop narrations exist. Now that all descriptions are generated
    # and gated, compose Part 4 from the actual delivered text.
    # Rules:
    #   - Every entity named in Part 4 must appear in that stop's final text (verified)
    #   - At least two stops named, by name
    #   - No fact from a stop that produced no description
    #   - 1-2 sentences max
    #   - If too little content survives, emit NO Part 4 rather than a vague one
    if _saved_prolog and _storied_mode and poi_list:
        print(f"\n  [LOCAL-270] PHASE 5.96: Composing Part 4 (forward connection) from delivered narrations...")

        # Gather delivered descriptions — only stops with real content
        _p4_stop_data = []
        for _p4i, _p4poi in enumerate(poi_list):
            _p4_desc = _p4poi.get('description', '')
            _p4_name = _p4poi.get('name', '')
            # Skip stops with no description or generation failures
            if (not _p4_desc or _p4_desc.startswith('[') or
                'GENERATION_FAILED' in _p4_desc or
                len(_p4_desc.split()) < 30):
                continue
            _p4_stop_data.append({
                'index': _p4i,
                'name': _p4_name,
                'description': _p4_desc,
            })

        print(f"    Stops with delivered content: {len(_p4_stop_data)}/{len(poi_list)}")

        if len(_p4_stop_data) >= 2:
            # Build a summary of each stop's key facts for the LLM
            _p4_stop_summaries = []
            for _p4s in _p4_stop_data:
                # Extract sentences with dates, proper nouns, or specific facts
                _p4_sents = re.split(r'(?<=[.!?])\s+', _p4s['description'])
                _p4_fact_sents = []
                for _p4sent in _p4_sents:
                    if len(_p4sent) < 20:
                        continue
                    _has_date = bool(re.search(r'\b\d{3,4}\b', _p4sent))
                    _has_proper = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', _p4sent))
                    if _has_date or _has_proper:
                        _p4_fact_sents.append(_p4sent.strip())
                _p4_stop_summaries.append({
                    'name': _p4s['name'],
                    'facts': _p4_fact_sents[:10],  # Cap to avoid token overflow
                })

            _p4_stops_text = ""
            for _p4sum in _p4_stop_summaries:
                if _p4sum['facts']:
                    _p4_stops_text += f"\n  [{_p4sum['name']}]:\n"
                    for _p4f in _p4sum['facts'][:6]:
                        _p4_stops_text += f"    - {_p4f[:200]}\n"

            if _p4_stops_text.strip():
                # ──── [LOCAL-276] INTRIGUE RANKING ────────────────────────────────
                # One batched model call ranks ALL candidate facts by intrigue before
                # composition. This replaces the "pick by name recognition" failure
                # D177 identified. The ranking chooses AMONG verified facts — it does
                # not write new ones, does not alter text, and does not replace D177
                # verification (which still runs on the composed output).
                #
                # What counts as intrigue (in order):
                #   1. A reversal — something became the opposite of what it was
                #   2. A mystery or unresolved thing
                #   3. A cause — X happened because Y
                #   4. A specific dated event with consequence
                #
                # What does NOT count:
                #   - Ownership/residence/visitation by a celebrity
                #   - Attribution with no event ("designed by X" unless the design IS the story)
                _rank_prompt = f"""You are ranking candidate facts from a tour for use in a preview sentence.

CANDIDATE FACTS BY STOP:
{_p4_stops_text}

TASK: For each stop, rank the facts from MOST to LEAST intriguing. Return the single best fact per stop.

INTRIGUE CRITERIA (in order of priority):
1. REVERSAL — something became the opposite of what it was (e.g. a confectioner who became a casino director; a fishing village that became a playground for the elite)
2. MYSTERY — an unresolved or unexplained thing (e.g. the Man in the Iron Mask, whose identity remains debated)
3. CAUSE — X happened because Y, a causal chain
4. DATED EVENT WITH CONSEQUENCE — a specific event that changed something (e.g. a festival cancelled by mobilisation; a castle destroyed in a war)

NOT INTRIGUING (penalise these — rank them last):
- Ownership, residence or visitation by a celebrity: "once owned by", "graced by", "hosted", "visited by" — unless the PERSON's story is itself a reversal
- Attribution with no event: "designed by X", "built by Y" — unless the design or construction itself carries a story
- A famous name with no tension: merely naming a celebrity who was there is trivia, not a story

OUTPUT FORMAT (one line per stop, JSON array):
[
  {{"stop": "<stop name>", "best_fact": "<the exact sentence text>", "rank": 1, "reason": "<which criterion: reversal/mystery/cause/dated_event/celebrity_trivia>"}},
  ...
]

Return ONLY the JSON array. Do not alter the fact text — copy it exactly as provided above."""

                _rank_start = time.time()
                _rank_cost = 0.0
                _rank_tokens = 0
                _ranked_facts = None  # Will hold the parsed ranking if successful

                try:
                    _rank_resp = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                            "messages": [
                                {"role": "system", "content": "You rank facts by narrative interest. You never invent facts. You return valid JSON only."},
                                {"role": "user", "content": _rank_prompt},
                            ],
                            "temperature": 0.1,
                            "max_tokens": 1200,
                        },
                        timeout=30,
                    )
                    _rank_elapsed = time.time() - _rank_start

                    if _rank_resp.status_code == 200:
                        _rank_result = _rank_resp.json()
                        _rank_usage = _rank_result.get("usage", {})
                        _rank_cost = (_rank_usage.get("prompt_tokens", 0) / 1000 * 0.005) + \
                                     (_rank_usage.get("completion_tokens", 0) / 1000 * 0.015)
                        _rank_tokens = _rank_usage.get("total_tokens", 0)
                        total_cost += _rank_cost
                        total_tokens += _rank_tokens

                        _rank_text = _rank_result["choices"][0]["message"]["content"].strip()
                        # Parse JSON — handle markdown code fences
                        _rank_json_text = _rank_text
                        if '```' in _rank_json_text:
                            _fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', _rank_json_text, re.DOTALL)
                            if _fence_match:
                                _rank_json_text = _fence_match.group(1).strip()

                        try:
                            _ranked_facts = json.loads(_rank_json_text)
                            print(f"    [LOCAL-276] Intrigue ranking completed: {_rank_elapsed:.1f}s, ${_rank_cost:.4f}, {_rank_tokens} tokens")
                            print(f"    [LOCAL-276] Ranked {len(_ranked_facts)} stops:")
                            for _rf in _ranked_facts:
                                _rf_stop = _rf.get('stop', '?')
                                _rf_reason = _rf.get('reason', '?')
                                _rf_fact = _rf.get('best_fact', '?')[:80]
                                print(f"      [{_rf_stop}] ({_rf_reason}): {_rf_fact}...")
                        except (json.JSONDecodeError, TypeError) as _je:
                            print(f"    [LOCAL-276] Ranking JSON parse failed: {_je}")
                            print(f"    [LOCAL-276] Raw response: {_rank_text[:300]}")
                            _ranked_facts = None
                    else:
                        _rank_elapsed = time.time() - _rank_start
                        print(f"    [LOCAL-276] Ranking call failed (HTTP {_rank_resp.status_code}) after {_rank_elapsed:.1f}s")

                except Exception as _rank_err:
                    _rank_elapsed = time.time() - _rank_start
                    print(f"    [LOCAL-276] Ranking call error: {_rank_err}")

                # ──── Build the RANKED stops text for composition ────────────────
                # If ranking succeeded, rebuild _p4_stops_text using only the top-
                # ranked fact per stop. EXCLUDE celebrity_trivia — those are the
                # "guest list" entries D177 identified as the problem. If ranking
                # failed, fall through to the original (unranked) list.
                #
                # Priority order for the composition LLM: reversal > mystery >
                # cause > dated_event. Stops with only celebrity_trivia are omitted.
                _INTRIGUE_PRIORITY = {
                    'reversal': 1,
                    'mystery': 2,
                    'cause': 3,
                    'dated_event': 4,
                }
                _EXCLUDED_REASONS = {'celebrity_trivia'}

                if _ranked_facts and isinstance(_ranked_facts, list):
                    # Filter and sort
                    _intriguing_facts = []
                    _excluded_count = 0
                    for _rf in _ranked_facts:
                        _rf_reason = _rf.get('reason', '').lower().strip()
                        if _rf_reason in _EXCLUDED_REASONS:
                            _excluded_count += 1
                            _rf_stop = _rf.get('stop', '?')
                            print(f"      [LOCAL-276] EXCLUDED ({_rf_reason}): [{_rf_stop}] {_rf.get('best_fact', '')[:60]}...")
                            continue
                        _intriguing_facts.append(_rf)

                    # Sort by intrigue priority (reversal first)
                    _intriguing_facts.sort(
                        key=lambda x: _INTRIGUE_PRIORITY.get(x.get('reason', '').lower().strip(), 99)
                    )

                    print(f"    [LOCAL-276] {len(_intriguing_facts)} intriguing / {_excluded_count} excluded (celebrity_trivia)")

                    # [LOCAL-280] Persist for closing recap — same ranking, same verification
                    _recap_ranked_facts = list(_intriguing_facts)

                    if len(_intriguing_facts) >= 2:
                        _ranked_stops_text = ""
                        for _rf in _intriguing_facts:
                            _rf_stop = _rf.get('stop', '')
                            _rf_fact = _rf.get('best_fact', '')
                            if _rf_stop and _rf_fact:
                                _ranked_stops_text += f"\n  [{_rf_stop}]:\n"
                                _ranked_stops_text += f"    - {_rf_fact[:200]}\n"

                        if _ranked_stops_text.strip():
                            _p4_stops_text = _ranked_stops_text
                            print(f"    [LOCAL-276] Using ranked facts for composition ({len(_intriguing_facts)} stops)")
                        else:
                            print(f"    [LOCAL-276] Ranked text empty — using unranked fallback")
                    else:
                        print(f"    [LOCAL-276] Fewer than 2 intriguing facts — using unranked fallback")
                else:
                    print(f"    [LOCAL-276] Using unranked facts (ranking unavailable)")
                # ──── END [LOCAL-276] INTRIGUE RANKING ────────────────────────────

                # LLM call to compose Part 4 — with one retry on verification failure
                _p4_prompt = f"""Write 1-2 sentences connecting a tour introduction to its upcoming stops. Name SPECIFIC content from at least two different stops, using the stop names.

STOP NAMES (in tour order): {', '.join(f'Stop {s["index"]+1}: {s["name"]}' for s in _p4_stop_data)}

DELIVERED STOP CONTENT (these are the ONLY facts you may reference — do NOT invent or add ANY fact not listed here):
{_p4_stops_text}

RULES:
- Pick exactly ONE specific fact (a date, person, or event) from at least 2 DIFFERENT stops
- ALWAYS include the stop name next to its fact — format: "<fact> at <stop name>"
- When referencing a stop, use its EXACT name from the list above — do NOT swap stop names
- A fact about Moses and Monotheism must be attributed to the stop named "Moses and Monotheism", not to a different stop
- Example: "In the stops ahead, you will encounter Monet's 1888 paintings at Cap d'Antibes and the 1706 destruction of Eze Village's fortifications."
- Second-person present tense
- 1-2 sentences ONLY (max 50 words)
- Do NOT use vague language: no "rich history", "many tales", "more stories", "fascinating", "explore the history"
- ONLY name facts that appear VERBATIM in the DELIVERED STOP CONTENT above
- Return ONLY the sentence(s), no labels or markers"""

                import requests as _p4_requests
                _p4_logger = logging.getLogger("generate_tour_text.part4")

                _p4_max_attempts = 2
                _p4_success = False
                _p4_text = ""
                _p4_total_cost = 0.0

                for _p4_attempt in range(_p4_max_attempts):
                    try:
                        _p4_resp = _p4_requests.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={
                                "model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo"),
                                "messages": [
                                    {"role": "system", "content": "You write concise, factual tour preview sentences. Use ONLY facts from the provided content."},
                                    {"role": "user", "content": _p4_prompt},
                                ],
                                "temperature": 0.3 + (_p4_attempt * 0.2),  # slightly higher on retry
                                "max_tokens": 120,
                            },
                            timeout=15,
                        )
                        if _p4_resp.status_code != 200:
                            print(f"    Part 4 LLM call failed (HTTP {_p4_resp.status_code}) — attempt {_p4_attempt+1}")
                            continue

                        _p4_result = _p4_resp.json()
                        _p4_text = _p4_result["choices"][0]["message"]["content"].strip()
                        if _p4_text.startswith('"') and _p4_text.endswith('"'):
                            _p4_text = _p4_text[1:-1].strip()

                        # Cost tracking
                        _p4_usage = _p4_result.get("usage", {})
                        _p4_cost = (_p4_usage.get("prompt_tokens", 0) / 1000 * 0.005) + \
                                   (_p4_usage.get("completion_tokens", 0) / 1000 * 0.015)
                        _p4_total_cost += _p4_cost
                        total_cost += _p4_cost
                        total_tokens += _p4_usage.get("total_tokens", 0)
                        print(f"    Part 4 LLM cost: ${_p4_cost:.4f} ({_p4_usage.get('total_tokens', 0)} tokens) [attempt {_p4_attempt+1}]")

                        # --- STRUCTURAL VERIFICATION ---
                        # Simplified approach: check that every factual claim (date, multi-word
                        # proper noun) in Part 4 exists in at least one stop's delivered text.
                        # Then verify at least 2 different stops are referenced by name.
                        _p4_verified = True
                        _p4_stops_referenced = 0
                        _p4_verification_log = []

                        # All delivered descriptions combined (for global fact check)
                        _all_desc_lower = ' '.join(s['description'].lower() for s in _p4_stop_data)

                        # Count how many stops are referenced by name
                        _p4_lower = _p4_text.lower()
                        for _p4s in _p4_stop_data:
                            _sname = _p4s['name'].lower()
                            # Check full name or significant portion (>5 chars)
                            if _sname in _p4_lower:
                                _p4_stops_referenced += 1
                            else:
                                # Try significant name parts
                                _sig_parts = [p for p in _sname.split() if len(p) > 4
                                              and p not in ('saint', 'sainte', 'ville')]
                                if any(sp in _p4_lower for sp in _sig_parts):
                                    _p4_stops_referenced += 1

                        # Check all dates in Part 4 exist in delivered descriptions
                        _p4_dates = re.findall(r'\b(\d{4})\b', _p4_text)
                        for _pd in _p4_dates:
                            if _pd not in _all_desc_lower:
                                _p4_verified = False
                                _p4_verification_log.append(
                                    f"FAIL: date '{_pd}' not found in any stop description")

                        # Check multi-word proper nouns (person/place names) exist in descriptions
                        # Pattern: "Word Word" or "Word de Word" etc.
                        _p4_multi_proper = re.findall(
                            r'\b([A-Z][a-zéèêëàâùûôîïç]+(?:\s+(?:de|du|la|le|des|von|van|di|d\'|sur|en)?\s*[A-Z][a-zéèêëàâùûôîïç]+)+)\b',
                            _p4_text)
                        _p4_skip_names = {s['name'] for s in _p4_stop_data}
                        _p4_skip_phrases = {
                            'French Riviera', 'Mediterranean Sea', 'Cap d\'Antibes',
                        }
                        for _pm in _p4_multi_proper:
                            _pm_clean = _pm.strip()
                            # Skip stop names themselves
                            if any(_pm_clean.lower() in sn.lower() or sn.lower() in _pm_clean.lower()
                                   for sn in _p4_skip_names):
                                continue
                            if _pm_clean in _p4_skip_phrases:
                                continue
                            # Check if at least one significant word (>4 chars) appears in descriptions
                            _pm_words = [w for w in _pm_clean.split()
                                         if len(w) > 4 and w.lower() not in
                                         {'french', 'riviera', 'saint', 'sainte', 'grand',
                                          'petit', 'coast', 'route', 'along', 'about'}]
                            if _pm_words and not any(w.lower() in _all_desc_lower for w in _pm_words):
                                _p4_verified = False
                                _p4_verification_log.append(
                                    f"FAIL: '{_pm_clean}' not found in any stop description")

                        # Must reference at least 2 stops by name
                        if _p4_stops_referenced < 2:
                            _p4_verified = False
                            _p4_verification_log.append(
                                f"FAIL: only {_p4_stops_referenced} stop(s) referenced by name, need ≥2")

                        # [LOCAL-481] Strip the label artifact before verifying.
                        # Delivered runs contained "At this work: Le Lézard aux
                        # plumes d'or (…), you'll delve into a collaborative
                        # masterpiece." The prompt asks for "<fact> at <stop name>"
                        # and the model answers with a label. Spoken aloud, "at this
                        # work colon" is nonsense. Cheaper to remove deterministically
                        # than to add another prompt rule the model may ignore.
                        # The preposition keeps its original case: replacing with a
                        # literal "At " produced "Then, At Au Soleil du Plafond".
                        _p4_text = re.sub(
                            r'\b(at|in)\s+th(?:is|e)\s+(?:work|stop|piece|item)\s*:\s*',
                            lambda m: m.group(1) + ' ', _p4_text,
                            flags=re.IGNORECASE).strip()

                        # Check for vague language (R10-style)
                        _vague_patterns = [
                            r'\bmore stories\b', r'\bmany tales\b', r'\bmany more\b',
                            r'\brich history\b', r'\bfascinating\b', r'\bhints at\b',
                            r'\bmore awaits\b', r'\bstories await\b', r'\bmore to discover\b',
                            r'\bmore wonders\b', r'\bcountless\b', r'\bexplore the history\b',
                            # [LOCAL-481] Observed in delivered runs and just as empty
                            # as the twelve above: a "preview" that previews nothing.
                            r'\bcollaborative masterpiece\b', r'\bdelve into\b',
                            r'\bunravel the depths\b', r'\bwitness how\b',
                            r'\btranscend(?:s)? time\b', r'\bunseen layers\b',
                        ]
                        for _vp in _vague_patterns:
                            if re.search(_vp, _p4_text, re.IGNORECASE):
                                _p4_verified = False
                                _p4_verification_log.append(
                                    f"FAIL: vague language detected in Part 4")
                                break

                        # [LOCAL-428] Cross-reference validation via clause-scoped
                        # attribution. Replaces the broken ±80-char window from
                        # LOCAL-427 (see D376). Now at module scope as
                        # check_part4_attribution() — testable and correct.
                        _p4_xref_errors = check_part4_attribution(_p4_text, _p4_stop_data)
                        for _xref_err in _p4_xref_errors:
                            _p4_verified = False
                            _p4_verification_log.append(_xref_err)

                        if _p4_verified:
                            _p4_success = True
                            break
                        else:
                            print(f"    ✗ Part 4 attempt {_p4_attempt+1} FAILED verification:")
                            print(f"      Candidate: \"{_p4_text}\"")
                            for _vlog in _p4_verification_log:
                                print(f"      {_vlog}")

                    except Exception as _p4_err:
                        _p4_logger.warning(f"[LOCAL-270] Part 4 attempt {_p4_attempt+1} error: {_p4_err}")
                        print(f"    Part 4 attempt {_p4_attempt+1} error ({type(_p4_err).__name__})")

                if _p4_success:
                    # Append Part 4 to the prolog (before "Your first stop is X.")
                    _saved_prolog = _saved_prolog.rstrip() + " " + _p4_text.strip()
                    print(f"    ✓ Part 4 composed and verified ({len(_p4_text.split())} words):")
                    print(f"      \"{_p4_text}\"")
                    print(f"      Stops referenced: {_p4_stops_referenced}")
                else:
                    print(f"    ✗ Part 4 FAILED all {_p4_max_attempts} attempts — omitting")
                    if _p4_text:
                        print(f"      Last candidate: \"{_p4_text}\"")

                print(f"    Part 4 total cost: ${_p4_total_cost:.4f}")
            else:
                print(f"    No factual sentences found in delivered stops — omitting Part 4")
        else:
            print(f"    Fewer than 2 stops with content — omitting Part 4")
    elif not _saved_prolog:
        print(f"\n  [LOCAL-270] PHASE 5.96: No prolog — skipping Part 4 composition")

    # -------- [LOCAL-286] PHASE 5.97: Prolog-body deduplication --------
    # If the prolog (including Part 4) repeats a clause ≥8 consecutive words
    # in any stop body, the listener hears the same thing twice within 90 seconds.
    # Remove the duplicated sentence from the stop body to prevent this.
    if _saved_prolog and poi_list:
        print(f"\n  [LOCAL-286] PHASE 5.97: Prolog-body deduplication (≥8 word overlap)...")
        _prolog_words_list = _saved_prolog.lower().split()
        _dedup_total_removed = 0

        # Build all 8-word sequences from the prolog
        _prolog_8grams = set()
        for _wi in range(len(_prolog_words_list) - 7):
            _prolog_8grams.add(' '.join(_prolog_words_list[_wi:_wi + 8]))

        if _prolog_8grams:
            for _di, _dpoi in enumerate(poi_list):
                _d_desc = _dpoi.get('description', '')
                if not _d_desc or _d_desc.startswith('['):
                    continue

                _d_sentences = re.split(r'(?<=[.!?])\s+', _d_desc)
                _kept_sentences = []
                _removed_in_stop = 0

                for _d_sent in _d_sentences:
                    _d_sent_words = _d_sent.lower().split()
                    _has_overlap = False
                    if len(_d_sent_words) >= 8:
                        for _si in range(len(_d_sent_words) - 7):
                            _test_gram = ' '.join(_d_sent_words[_si:_si + 8])
                            if _test_gram in _prolog_8grams:
                                _has_overlap = True
                                break
                    if _has_overlap:
                        _removed_in_stop += 1
                        print(f"    Stop {_di+1} '{_dpoi.get('name', '')[:30]}': "
                              f"removed duplicate sentence: \"{_d_sent[:80]}...\"")
                    else:
                        _kept_sentences.append(_d_sent)

                if _removed_in_stop > 0:
                    poi_list[_di]['description'] = ' '.join(_kept_sentences)
                    _dedup_total_removed += _removed_in_stop

        print(f"  [LOCAL-286] Deduplication: {_dedup_total_removed} sentence(s) removed from stop bodies")

    # -------- [LOCAL-292] EMPTY STOP REMOVAL GATE --------
    # A stop whose description failed generation must be removed entirely from the
    # delivered tour. A stop with a header and no narration is worse than a missing
    # stop — the listener is told to stand somewhere and then told nothing.
    # This gate runs BEFORE assembly so the empty stop never enters the text.
    # [LOCAL-295] Use _classify_placeholder_leak instead of bare <15 word check,
    # so short-but-valid prose (thin corpus) is preserved.
    _l292_requested_stops = len(poi_list)
    _l292_failed_stops = []
    _l292_survivors = []
    for _l292_poi in poi_list:
        _l292_desc = _l292_poi.get('description', '')
        _l292_is_failure = (
            'GENERATION_FAILED' in _l292_desc or
            _l292_desc.startswith('[') or
            (not _l292_desc.strip())
        )
        if not _l292_is_failure:
            # [LOCAL-295] Check if it's a genuine placeholder (not short-valid prose)
            _l292_class, _l292_detail = _classify_placeholder_leak(_l292_desc)
            if _l292_class == "placeholder":
                _l292_is_failure = True
                print(f"  [LOCAL-295] Gate rejected '{_l292_poi['name']}': placeholder ({_l292_detail})")
        if _l292_is_failure:
            _l292_failed_stops.append(_l292_poi['name'])
        else:
            _l292_survivors.append(_l292_poi)

    if _l292_failed_stops:
        print(f"\n  [LOCAL-292] ⚠️  EMPTY STOP REMOVAL GATE: {len(_l292_failed_stops)} stop(s) removed for failed/empty description")
        for _l292_name in _l292_failed_stops:
            print(f"    REMOVED: '{_l292_name}' — no narration generated (would ship as empty shell)")
        poi_list = _l292_survivors
        # Renumber surviving stops sequentially
        for _l292_i, _l292_p in enumerate(poi_list):
            _l292_p['stop_number'] = _l292_i + 1
        # Update total_stops to reflect reality
        total_stops = len(poi_list)
        print(f"    SUMMARY: requested={_l292_requested_stops} / generated={_l292_requested_stops - len(_l292_failed_stops)} / "
              f"failed={len(_l292_failed_stops)} / delivered={len(poi_list)}")
    else:
        print(f"\n  [LOCAL-292] Empty stop removal gate: PASSED (all {_l292_requested_stops} stops have narration)")

    # [LOCAL-292] Rebuild tour title with correct stop count if stops were removed
    if _l292_failed_stops and poi_list:
        # The tour_title line is the first line of complete_tour; rebuild complete_tour header
        if tour_type.lower() in location.lower():
            tour_title = f"Step-by-Step Audio Guided Tour: {location}"
        else:
            tour_title = f"Step-by-Step Audio Guided Tour: {location} - {_display_category} Tour"
        complete_tour = tour_title + "\n" + f"Tour-Category: {_header_category}" + "\n\n"

    if len(poi_list) == 0:
        print(f"  [LOCAL-292] ✗ ALL stops failed generation — cannot deliver tour")
        return None, None, (None, None)

    # [LOCAL-394] INVARIANT: delivered stop count must equal selected work count.
    # A stop is never dropped to satisfy a length or beat rule. Any deviation is
    # logged loudly. The only legitimate removal is GENERATION_FAILED (no valid
    # description was EVER produced for that stop across all retries).
    if len(poi_list) != _l292_requested_stops:
        print(f"  [LOCAL-394] ⚠️  STOP COUNT INVARIANT VIOLATION: "
              f"selected={_l292_requested_stops} delivered={len(poi_list)} "
              f"— {_l292_requested_stops - len(poi_list)} stop(s) lost!")
        for _l394_name in _l292_failed_stops:
            print(f"    [LOCAL-394] LOST: '{_l394_name}'")
    else:
        print(f"  [LOCAL-394] Stop count invariant: OK ({len(poi_list)} selected == {len(poi_list)} delivered)")

    # [LOCAL-361] Track actually-rendered headers for D2 and heading-count invariant
    _rendered_headers = []

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
        # [LOCAL-361] Refined heuristic: a CORRUPT name is one where GPT injected a
        # full sentence (has sentence-ending punctuation followed by a space and a
        # lowercase word, e.g. ". the"). Real artwork titles may contain ?, !, ., ;
        # (e.g. "Whaam!", "No. 14", "Where Do We Come From? What Are We?").
        # D1v2-verified titles are exempt — the corpus already vouched for them.
        _f3_is_verified = poi.get('verified', True)  # True or absent = verified (D1v2 default)
        if f3_name_is_corrupt(poi_name, _f3_is_verified):
            print(f"  [F3] ⚠️ NAME TOO LONG/CORRUPT at stop {stop_num}: '{poi_name[:80]}'")
            # Truncate to first 12 words if corrupted
            _clean_name = ' '.join(poi_name.split()[:12]).rstrip('.,;:!?')
            poi_header = f"Stop {stop_num}: {_clean_name}"
            if artist and artist.lower() != "unknown artist":
                poi_header += f" by {artist}"
            if year:
                poi_header += f", {year}"
        
        # [LOCAL-361] Record the actual rendered header for D2 truth set
        _rendered_headers.append(poi_header)

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
            # [LOCAL-427] All stops get coordinates, even in a single-building museum.
            # The mobile app needs a pin for each stop; omitting coordinates for
            # stops 2+ caused D373's "no Coordinates" defect.
            coords_eligible = True
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
        _orientation_prefix = "Orientation: "
        _entrance_directive = ""
        if i == 0:
            # For the first POI, include directions from the entrance
            # [C5-3] Museum tours: skip fabricated entrance directions entirely
            if tour_category != 'museum' or not _museum_venue_name:
                entrance_directions = poi.get("directions", "")
                if entrance_directions:
                    # [LOCAL-264] held back so the general description can go first,
                    # inside the Orientation section
                    _entrance_directive = entrance_directions + " "
        
        # [LOCAL-264] Michael, 2026-08-05. Two corrections, in order:
        #   1. the tour's general description must precede the where-to-go directive;
        #   2. but BOTH sit INSIDE the Orientation section — the literal word
        #      "Orientation:" has to come first, because "the verbalization and
        #      translation depend on that word to start."
        # So Stop 1 reads:
        #   Orientation: <general description of the tour> <where to go>
        # and the prolog is never emitted as a separate block above the label.
        if i == 0 and _saved_prolog:
            _orientation_prefix += _saved_prolog.strip() + " "

        # [LOCAL-268] Michael, 2026-08-05: after the general description, NAME the
        # stop before describing it. "the listner coudl have forgiven what this stop
        # is and where he should stand to start the tour." The listener hears
        # narration, not the "Stop 1:" header, so without this they are standing
        # somewhere unnamed. Deterministic, no model call.
        if i == 0 and _saved_prolog:
            _stop_name = (poi.get("name") or "").strip()
            if _stop_name:
                _orientation_prefix += f"Your first stop is {_stop_name}. "

        _orientation_prefix += _entrance_directive

        # Add the orientation text — [LOCAL-388] Uniform: all stops get orientation
        # Strip any leading "Orientation:" from the LLM text to avoid duplication
        _clean_orientation = re.sub(r'^Orientation:\s*', '', orientation, flags=re.IGNORECASE).strip()
        if tour_category == 'museum' and _museum_venue_name:
            # [LOCAL-388] Consistent orientation across all stops.
            # Previously R3 dropped weak orientations for non-stop-1 stops.
            # Now: always emit. If the orientation is the generic fallback and
            # we have no prolog, still emit it so TTS sees "Orientation:" on every stop.
            _is_generic_fallback = _clean_orientation in (
                "Position yourself to best view this artwork.",
                "Position yourself to best view this location.",
                "Look for this work in the galleries.",
            )
            if _is_generic_fallback and i > 0:
                # Non-stop-1 generic fallback: emit a stop-specific orientation
                _stop_name_for_orient = (poi.get("name") or "").strip()
                _clean_orientation = f"Look for {_stop_name_for_orient} in the galleries." if _stop_name_for_orient else _clean_orientation
            poi_content += f"{_orientation_prefix}{_clean_orientation}\n\n"
        else:
            poi_content += f"{_orientation_prefix}{_clean_orientation}\n\n"
        
        # Add description
        poi_content += description + "\n\n"
        
        # Add directions to next stop or conclusion
        if i < len(poi_list) - 1:
            next_poi = poi_list[i + 1]
            
            # [T4] DETERMINISTIC TRANSITION TEMPLATES — no LLM content in transitions
            # This eliminates the splice-corruption bug class entirely
            # [LOCAL-44] Removed "Ask museum staff for directions" (people know that).
            # Venue name appears at most twice across all transitions in a single-venue tour.
            if tour_category == 'museum' and _museum_venue_name:
                # Museum tours: mostly name-only transitions; venue name only on first and last
                if i == 0:
                    _transition = f"Continue through {_museum_venue_name} — next is {next_poi['name']}."
                elif i == len(poi_list) - 2:
                    _transition = f"Your final stop in {_museum_venue_name}: {next_poi['name']}."
                else:
                    # Interior transitions: just name the next stop, no venue repetition
                    _interior_templates = [
                        f"Next: {next_poi['name']}.",
                        f"Proceed to {next_poi['name']}.",
                        f"Continue to {next_poi['name']}.",
                    ]
                    _transition = _interior_templates[(i - 1) % len(_interior_templates)]
            else:
                # Outdoor tours: use generated directions if available
                directions = next_poi.get("directions", "")
                if _storied_mode:
                    try:
                        from directions_generator import generate_walking_directions
                        _storied_directions = generate_walking_directions(poi_name, next_poi['name'], location, api_key, transport_mode=transport_mode)
                        if _storied_directions:
                            directions = _storied_directions
                    except ImportError as _dir_imp_err:
                        _import_logger.error(f"[LOCAL-146] MISSING: directions_generator (generate_walking_directions) — directions DISABLED: {_dir_imp_err}")
                    except Exception as _dir_err:
                        _import_logger.error(f"[LOCAL-146] directions_generator.generate_walking_directions FAILED: {type(_dir_err).__name__}: {_dir_err}")
                if directions and directions.strip():
                    # [LOCAL-253] Validate pre-existing directions (from POI data) against mode
                    from directions_generator import validate_directions_mode
                    _dir_violations = validate_directions_mode(directions.strip(), transport_mode)
                    if _dir_violations:
                        for _dv in _dir_violations:
                            print(f"  ❌ [LOCAL-253] PRE-EXISTING DIRECTIONS REJECTED: {_dv}")
                        _transition = f"Continue to {next_poi['name']}."
                    else:
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
                
                # [LOCAL-41] Audio-native closing: synthesize 2–3 stops in service of a
                # point, never enumerate all stops. Listeners hearing a full list feel
                # they missed something — it manufactures anxiety where the tour should land.
                _first = _poi_names[0]
                _last = poi_name
                # Pick one interior highlight (middle stop, roughly)
                _mid_idx = len(_poi_names) // 2
                _mid = _poi_names[_mid_idx] if len(_poi_names) > 2 else None
                
                epilog = f"\n\n"
                
                # [SQ-S6b] Thread payoff in epilog — pay off the narrative promise
                if _thread_result and _thread_result.mode == "threaded" and _thread_result.epilog_payoff:
                    epilog += _thread_result.epilog_payoff + " "
                
                # Use ONLY documented story elements for closing facts (never GPT-generated spine text)
                if _story_elements:
                    _closing_facts = [e.get('text', '') for e in _story_elements 
                                     if e.get('type') in ('date', 'superlative', 'turning_point') and e.get('text')]
                    if _closing_facts:
                        _fact = _closing_facts[0]
                        epilog += _fact + " "
                
                # [LOCAL-280] CLOSING RECAP — replaces any thank-you sentence.
                # Sentence 1: recap built from the tour that was actually delivered.
                # States scale + names real content, using the LOCAL-276 intrigue
                # ranking (same ranking, same verification as Part 4).
                # No thank-you, no "we hope you enjoyed" — show substance instead.
                _recap = _build_closing_recap(poi_list, _recap_ranked_facts, api_key=api_key)
                if _recap:
                    epilog += _recap + " "
                    _offer_budget = 2  # recap took sentence 1
                    print(f"  [LOCAL-280] Recap added: \"{_recap}\"")
                else:
                    _offer_budget = 3  # no recap — offer gets full budget
                    print(f"  [LOCAL-280] No recap — closing offer gets full 3-sentence budget")

                # [LOCAL-273/280] Closing offer: concrete, verified.
                # When recap present: 2 sentences (similar-tour+Treats, news).
                # When no recap: 3 sentences (original budget).
                _closing_offer = _build_closing_offer(
                    poi_list, tour_category, transport_mode, location,
                    sentence_budget=_offer_budget
                )
                if _closing_offer:
                    # [D521] The "Closing:" label is GONE. Michael, 2026-08-24:
                    # *"Make sure that the title words such as Narration and
                    # Closing are not end up in the actual tour as that would be
                    # annoying for the listeners. 'Directions' and 'Orientation'
                    # are fine because they let listeners know that they are not
                    # part of the stop description."*
                    #
                    # That distinction is the whole rule and it is a good one:
                    # Directions and Orientation tell a listener what KIND of
                    # thing is coming and why it is not about the object in front
                    # of them. "Closing" tells them nothing they cannot hear.
                    #
                    # It was added so the scorer need not guess at recap
                    # templates. The scorer no longer needs it — `_CLOSING_OFFER_RE`
                    # matches the recap ("That's N stops"), the offer verbs and the
                    # news offer by content, and still matches the old label so
                    # tours already on disk score identically.
                    epilog += _closing_offer.lstrip()
                
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
                # Beta: factual closing (no preaching)
                poi_content += ""  # No separate conclusion needed — last stop ends on its own content
        
        # Add to complete tour
        complete_tour += poi_content + "\n\n"
    
    # [D2] Strip GPT self-references to "Stop N" in description bodies
    if _storied_mode:
        import re as _d2_re
        # Build set of REAL header lines from actually-rendered headers [LOCAL-361]
        _real_headers = set(_rendered_headers)
        
        _d2_lines = complete_tour.split('\n')
        _d2_cleaned = []
        for _line in _d2_lines:
            # Only preserve lines that are KNOWN real headers
            if _line.strip() in _real_headers:
                _d2_cleaned.append(_line)
            elif _d2_re.match(r'^Stop\s+\d+:', _line):
                # Line looks like a header but isn't a real one — it's GPT leakage
                # Strip the "Stop N:" prefix and replace remaining "Stop N" references
                _cleaned = _d2_re.sub(r'^Stop\s+\d+:\s*', '', _line, count=1)
                _cleaned = _d2_re.sub(r'\bStop\s+\d+\b', 'this work', _cleaned)
                _d2_cleaned.append(_cleaned)
            else:
                # Replace self-referential "Stop N" with context-appropriate text
                _d2_cleaned.append(_d2_re.sub(r'\bStop\s+\d+\b', 'this work', _line))
        complete_tour = '\n'.join(_d2_cleaned)

    # [LOCAL-361] HARD INVARIANT: rendered heading count MUST equal stop count.
    # A mismatch means a stop silently vanished — fail loudly at generation time.
    _lost_headers = missing_stop_headers(complete_tour, _rendered_headers)
    if _lost_headers:
        print(f"  [LOCAL-361] ✗ STOP HEADING LOST: {len(_lost_headers)} of "
              f"{len(_rendered_headers)} rendered headers absent from the tour")
        for _lh in _lost_headers:
            print(f"    missing: {_lh}")
        raise ValueError(
            f"[LOCAL-361] {len(_lost_headers)} of {len(poi_list)} stop headings "
            f"vanished after rendering: {_lost_headers}. This is a generation bug "
            f"— refusing to deliver a short tour."
        )

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
                                    # [LOCAL-22] Strip any "Stop N:" prefix from rewritten text
                                    # The rewrite GPT sometimes echoes "Stop N:" context into its output
                                    _rewritten = re.sub(r'^Stop\s+\d+:\s*', '', _rewritten, flags=re.IGNORECASE | re.MULTILINE).strip()
                                    # Also strip "Stop N" meta-references
                                    _rewritten = re.sub(r'\bStop\s+\d+\b', 'this work', _rewritten)
                                    # [LOCAL-22] Safe scoped replacement: find the target stop's
                                    # block by locating its header, then replace ONLY within that block.
                                    # Do NOT use re.split on Stop headers (corrupts header boundaries).
                                    _header_pattern = re.compile(rf'^Stop\s+{_stop_b}:', re.MULTILINE)
                                    _header_match = _header_pattern.search(complete_tour)
                                    if _header_match:
                                        _block_start = _header_match.start()
                                        # Find the NEXT stop header to delimit the block end
                                        _next_header = re.search(r'^Stop\s+\d+:', complete_tour[_block_start + 1:], re.MULTILINE)
                                        _block_end = (_block_start + 1 + _next_header.start()) if _next_header else len(complete_tour)
                                        _block_text = complete_tour[_block_start:_block_end]
                                        if _sentence_b in _block_text:
                                            _new_block = _block_text.replace(_sentence_b, _rewritten, 1)
                                            complete_tour = complete_tour[:_block_start] + _new_block + complete_tour[_block_end:]
                                            _rewrite_count += 1
                                            print(f"REPETITION FIXED: Stop {_stop_b} sentence rewritten")
                                        else:
                                            # Sentence not in expected block — skip (don't corrupt)
                                            print(f"  [S29] Sentence not found in Stop {_stop_b} block — skipping")
                                    else:
                                        print(f"  [S29] Stop {_stop_b} header not found — skipping")
                        if _rewrite_count > 0:
                            print(f"  [S29] {_rewrite_count} sentence(s) rewritten")
                    except ImportError:
                        _import_logger.error("[S29] MISSING: derepetition_guard.rewrite_repeated_sentence — repetition rewriting DISABLED")
                        print(f"  [S29] rewrite_repeated_sentence not available — skipping rewrites")
                    except Exception as _rw_err:
                        print(f"  [S29] Rewrite error: {_rw_err}")
            else:
                print(f"  [S27] No cross-stop repetition detected")
        except ImportError:
            _import_logger.error("[S27] MISSING: derepetition_guard (detect_cross_stop_repetition) — cross-stop repetition check DISABLED")
            print(f"  [S27] derepetition_guard not available — repetition check skipped")
        except Exception as e:
            print(f"  [S27] Repetition check error: {e}")

    # -------- [LOCAL-47] Tour-title / location repetition cap --------
    if tour_category != 'museum':
        try:
            from derepetition_guard import cap_location_repetition, count_phrase_occurrences
            # Extract the core location phrase (strip "tour", "biking", etc.)
            _loc_phrase_clean = re.sub(
                r'\b(tour|tours|biking|cycling|bike|walking|walk|self[- ]guided)\b',
                '', location, flags=re.IGNORECASE
            ).strip().strip(',').strip()
            # Also try the full location string
            _loc_count_full = count_phrase_occurrences(complete_tour, location)
            _loc_count_clean = count_phrase_occurrences(complete_tour, _loc_phrase_clean) if _loc_phrase_clean != location else 0
            
            # Cap the most-repeated variant
            if _loc_count_full > 2:
                complete_tour = cap_location_repetition(complete_tour, location, max_occurrences=2)
                print(f"  [LOCAL-47] Capped '{location}' from {_loc_count_full} to ≤2 occurrences")
            if _loc_phrase_clean and _loc_count_clean > 2:
                complete_tour = cap_location_repetition(complete_tour, _loc_phrase_clean, max_occurrences=2)
                print(f"  [LOCAL-47] Capped '{_loc_phrase_clean}' from {_loc_count_clean} to ≤2 occurrences")
        except ImportError:
            print(f"  [LOCAL-47] derepetition_guard not available — location cap skipped")
        except Exception as _cap_err:
            print(f"  [LOCAL-47] Location cap error: {_cap_err}")

    # -------- [LOCAL-22] Final stop-header sanitization --------
    # After ALL post-processing (D2, S29), ensure no fake "Stop N:" lines exist.
    # Only the REAL headers (one per stop, produced at PHASE 6 assembly) may start with "Stop N:".
    _real_header_set = set()
    for i, poi in enumerate(poi_list):
        _h = f"Stop {i + 1}: {poi['name']}"
        if poi['artist'] and poi['artist'].lower() != "unknown artist":
            _h += f" by {poi['artist']}"
        if poi['year']:
            _h += f", {poi['year']}"
        _real_header_set.add(_h)
    
    _final_lines = complete_tour.split('\n')
    _sanitized_lines = []
    _corruption_fixed = 0
    for _line in _final_lines:
        if re.match(r'^Stop\s+\d+:', _line) and _line.strip() not in _real_header_set:
            # This line looks like a header but isn't a real one — strip the prefix
            _fixed = re.sub(r'^Stop\s+\d+:\s*', '', _line)
            _sanitized_lines.append(_fixed)
            _corruption_fixed += 1
        else:
            _sanitized_lines.append(_line)
    if _corruption_fixed:
        complete_tour = '\n'.join(_sanitized_lines)
        print(f"  [LOCAL-22] Final sanitization: removed {_corruption_fixed} fake Stop N: header(s)")

    # -------- [LOCAL-36] Practical facts QA gate --------
    # Verify provenance of every practical claim before delivery.
    # Claims without traceable source are DROPPED — silence is correct.
    try:
        from practical_facts_gate import gate_and_fix as _practical_gate
        _pf_source_url = ''
        _pf_source_text = ''
        try:
            _pf_source_url = _visitor_info_source_url
            _pf_source_text = _visitor_info_source_text
        except NameError:
            pass
        complete_tour, _pf_result = _practical_gate(
            complete_tour,
            source_url=_pf_source_url,
            source_text=_pf_source_text,
            verbose=True,
        )
        if not _pf_result.passed:
            print(f"  [LOCAL-36] PRACTICAL FACTS GATE: {len(_pf_result.dropped_claims)} claim(s) dropped")
        else:
            print(f"  [LOCAL-36] PRACTICAL FACTS GATE: PASSED ({len(_pf_result.verified_claims)} verified)")
    except ImportError:
        _import_logger.error("[LOCAL-36] MISSING: practical_facts_gate — practical facts verification DISABLED")
        print("  [LOCAL-36] practical_facts_gate not available — skipped")
    except Exception as _pf_err:
        print(f"  [LOCAL-36] Practical facts gate error (non-fatal): {_pf_err}")

    # -------- [LOCAL-251] [LOCAL-292] Generation failure gate --------
    # A generation failure must not reach the output silently. If any stop
    # contains a [GENERATION_FAILED:...] or [Description for ... could not be generated.]
    # placeholder, the ENTIRE stop block must be removed — not just the marker.
    # A header + address with no narration is worse than a missing stop.
    # [LOCAL-292] After removal, the failure must be logged at the same prominence
    # as an existence-gate drop, and recorded in the run's summary counts.
    _gen_fail_pattern = re.compile(r'\[(?:GENERATION_FAILED:[^\]]+|Description for [^\]]+ could not be generated\.)\]')
    _gen_fail_matches = _gen_fail_pattern.findall(complete_tour)
    if _gen_fail_matches:
        print(f"\n  [LOCAL-251] ⚠️  GENERATION FAILURE GATE: {len(_gen_fail_matches)} placeholder(s) detected!")
        print(f"  [LOCAL-292] ⚠️  GENERATION FAILURE — SAME SEVERITY AS EXISTENCE-GATE DROP:")
        _l292_post_assembly_failed = []
        for _gf in _gen_fail_matches:
            # Extract the stop name from the marker
            _gf_name_match = re.search(r'(?:GENERATION_FAILED:|Description for )([^\]]+?)(?:\]| could not)', _gf)
            _gf_stop_name = _gf_name_match.group(1).strip() if _gf_name_match else _gf
            _l292_post_assembly_failed.append(_gf_stop_name)
            print(f"    ✗ FAILED: '{_gf_stop_name}' — description generation failed after retries")
            print(f"    REMOVING ENTIRE STOP BLOCK (not just marker)")

        # [LOCAL-292] Remove entire stop blocks containing failure markers.
        # A stop block runs from "Stop N:" to the next "Stop M:" or end of text.
        _stop_block_fail_pattern = re.compile(
            r'Stop\s+\d+:[^\n]*\n'
            r'(?:(?!Stop\s+\d+:).)*?'
            r'\[(?:GENERATION_FAILED:[^\]]+|Description for [^\]]+ could not be generated\.)\]'
            r'(?:(?!Stop\s+\d+:).)*',
            re.DOTALL
        )
        complete_tour = _stop_block_fail_pattern.sub('', complete_tour)

        # Also strip any orphaned markers not inside a stop block
        complete_tour = _gen_fail_pattern.sub('', complete_tour)
        # Strip leaked orientation fallbacks
        complete_tour = complete_tour.replace("Look for this work in the galleries.", "")
        complete_tour = complete_tour.replace("Position yourself to best view this location.", "")

        # [LOCAL-292] Renumber remaining stops sequentially so count matches reality
        _remaining_stop_headers = list(re.finditer(r'Stop\s+\d+:', complete_tour))
        # Renumber in reverse to avoid offset shifts
        for _rs_i, _rs_m in enumerate(reversed(_remaining_stop_headers), 1):
            _correct_num = len(_remaining_stop_headers) - _rs_i + 1
            complete_tour = complete_tour[:_rs_m.start()] + f"Stop {_correct_num}:" + complete_tour[_rs_m.end():]
        _l292_delivered_post = len(_remaining_stop_headers)

        print(f"  [LOCAL-292] RUN SUMMARY: requested={_l292_requested_stops} / "
              f"failed_pre_assembly={len(_l292_failed_stops)} / "
              f"failed_post_assembly={len(_l292_post_assembly_failed)} / "
              f"delivered={_l292_delivered_post}")

        # Clean up double-spaces and triple-newlines left behind
        complete_tour = re.sub(r'  +', ' ', complete_tour)
        complete_tour = re.sub(r'\n\s*\n\s*\n', '\n\n', complete_tour)

    # -------- [LOCAL-256] Bare field-label gate --------
    # Schema field names (Description:, Orientation:, etc.) must never reach the
    # TTS-bound artifact. LOCAL-250 round 7 v1 bounced on this exact defect;
    # LOCAL-255 round 12 shipped it again because the LLM echoed "Description:"
    # after the orientation split. The fix at the split point (above) prevents
    # new occurrences; this gate catches any that slip through assembly.

    # -------- [LOCAL-285] Empty venue phrase gate --------
    # An empty venue span (e.g. "through ." or "through ,") must never reach TTS.
    # This catches the case where the prolog model emits a template with a blank
    # location/venue variable. Fix: replace with the location if available.
    _empty_venue_pattern = re.compile(r'(through|across|around|in|of)\s+([.,;!])')
    _empty_venue_matches = _empty_venue_pattern.findall(complete_tour)
    if _empty_venue_matches:
        print(f"\n  [LOCAL-285] ⚠️  EMPTY VENUE PHRASE GATE: {len(_empty_venue_matches)} empty venue span(s) detected!")
        # Fill with the location name (first comma-segment for brevity)
        _venue_fill = location.split(',')[0].strip() if location else "this area"
        for _ev_prep, _ev_punct in _empty_venue_matches:
            _old = f"{_ev_prep} {_ev_punct}"
            _new = f"{_ev_prep} {_venue_fill}{_ev_punct}"
            print(f"    FIXING: '{_old}' → '{_new}'")
        complete_tour = _empty_venue_pattern.sub(
            lambda m: f"{m.group(1)} {_venue_fill}{m.group(2)}", complete_tour
        )

    # -------- [LOCAL-285] Self-referential route guard --------
    # A single-stop tour must not say "from X to X" or "take you from X to X".
    # This catches the case where the prolog describes a route between identical endpoints.
    _self_route_pattern = re.compile(
        r'((?:from|between)\s+)(.{3,80}?)(\s+to\s+)\2',
        re.IGNORECASE
    )
    _self_route_matches = _self_route_pattern.findall(complete_tour)
    if _self_route_matches:
        print(f"\n  [LOCAL-285] ⚠️  SELF-REFERENTIAL ROUTE GATE: {len(_self_route_matches)} self-route(s) detected!")
        for _sr_prefix, _sr_name, _sr_mid in _self_route_matches:
            _old_route = f"{_sr_prefix}{_sr_name}{_sr_mid}{_sr_name}"
            print(f"    REMOVING: '{_old_route}'")
        # Remove the self-referential route clause (including surrounding commas/sentences)
        # Strategy: remove "from X to X" and the distance clause that follows
        _self_route_sentence = re.compile(
            r'[^.]*(?:from|between)\s+(.{3,80}?)\s+to\s+\1[^.]*\.\s*',
            re.IGNORECASE
        )
        complete_tour = _self_route_sentence.sub(' ', complete_tour)
        # Clean up double-spaces
        complete_tour = re.sub(r'  +', ' ', complete_tour)
        complete_tour = re.sub(r'\n\s*\n\s*\n', '\n\n', complete_tour)

    _BARE_FIELD_LABELS = re.compile(
        r'^\s*(?:Description|Orientation|Directions|Sources|Coordinates|'
        r'Type/Specialty|Specific Examples|Museum Information|Operational Details):\s*$',
        re.MULTILINE
    )
    _field_label_matches = _BARE_FIELD_LABELS.findall(complete_tour)
    if _field_label_matches:
        print(f"\n  [LOCAL-256] ⚠️  BARE FIELD-LABEL GATE: {len(_field_label_matches)} label(s) in output!")
        for _fl in _field_label_matches:
            print(f"    STRIPPING: '{_fl.strip()}'")
        # Strip bare labels — they carry no content for TTS
        complete_tour = _BARE_FIELD_LABELS.sub('', complete_tour)
        # Clean up resulting empty lines
        complete_tour = re.sub(r'\n\s*\n\s*\n', '\n\n', complete_tour)

    # -------- [D523] Spoken-text hygiene: the last pass before a human hears it --
    #
    # Two defects that survived every gate because no gate reads the assembled
    # text as SOUND. "At this work:" is spoken "at this work colon"; a full stop
    # with nothing after it welds two words into one that does not exist.
    #
    # The template-seam strip already existed at the Part 4 verifier and the 12:23
    # tour routed around it by putting the seam in the stop-1 orientation, which a
    # different generator writes. Here it sees the finished tour, so there is no
    # path around it. The missing space has now been reported as a "known defect"
    # three times without being fixed, on the grounds that it is upstream; it is
    # upstream, and it is also two lines to repair, and 5 of the last 6 runs
    # shipped one.
    try:
        from spoken_text_hygiene import clean_spoken_text as _d523_clean
        complete_tour, _d523_rep = _d523_clean(complete_tour, verbose=True)
    except Exception as _d523_e:
        print(f"  [D523] spoken-text hygiene skipped (non-fatal): {_d523_e}")

    # -------- [D523] Facts we have already paid to verify --------
    #
    # The 12:23 tour asserted "Moses was an Egyptian priest" — Freud argued
    # NOBLEMAN — with nothing in the tour contradicting it. The defect checker
    # looks for a self-contradiction, so it stayed silent: a tour that is
    # confidently wrong in one direction is worse, and nothing was watching it.
    #
    # Narrow by charter. See the module docstring for the three conditions an
    # entry must meet; the short version is that the wrong version must have been
    # observed in a delivered tour and the right one established by RETRIEVAL.
    # The real fix is to ground the descriptive-prose generator in the same corpus
    # the story loop retrieves; until then, a fact bought once should not be
    # re-emitted wrongly on the next run.
    try:
        from known_fact_corrections import apply_corrections as _d523_fix
        complete_tour, _d523_fired = _d523_fix(complete_tour, verbose=True)
    except Exception as _d523_e2:
        print(f"  [D523] fact corrections skipped (non-fatal): {_d523_e2}")

    # -------- [LOCAL-260] PHASE post-assembly: Prolog structure validation --------
    # Michael's four-part prolog specification: the opening must have (in order):
    #   1. Tour name + transportation mode
    #   2. Directions and physicality expectation
    #   3. Purpose / intrigue with sourced facts
    #   4. Forward connection to stops (naming actual stop content)
    # This is a REPORT-ONLY check — it never deletes or rewrites.
    # Deterministic and free (no LLM calls).
    if _saved_prolog:
        try:
            from prolog_structure_validator import validate_prolog_structure
            _prolog_stop_names = [p.get('name', '') for p in poi_list] if poi_list else []
            _prolog_meta = {
                'transport_mode': transport_mode if 'transport_mode' in dir() else 'on_foot',
                'tour_name': location if location else '',
                'stop_names': _prolog_stop_names,
                'full_tour_content': complete_tour if 'complete_tour' in dir() else '',
            }
            _prolog_violations = validate_prolog_structure(_saved_prolog, _prolog_meta)
            _prolog_errors = [v for v in _prolog_violations if v['severity'] == 'error']
            if _prolog_violations:
                print(f"\n  [LOCAL-260] PROLOG STRUCTURE VALIDATION: "
                      f"{len(_prolog_errors)} error(s), "
                      f"{len(_prolog_violations) - len(_prolog_errors)} warning(s)")
                for _pv in _prolog_violations:
                    print(f"    [{_pv['severity'].upper()}] Part {_pv['part']}: "
                          f"{_pv['code']} — {_pv['message']}")
            else:
                print(f"\n  [LOCAL-260] PROLOG STRUCTURE VALIDATION: ✓ all four parts present and conforming")
        except ImportError as _e:
            print(f"\n  [LOCAL-260] Prolog structure validation SKIPPED (import: {_e})")
        except Exception as _e:
            print(f"\n  [LOCAL-260] Prolog structure validation error (non-fatal): {_e}")

    # -------- [LOCAL-391] Final 'with publisher' scrub on assembled tour --------
    # Catch any unfilled role phrases that survived assembly. The per-stop scrub
    # runs during generation, but this catches edge cases from assembly/concatenation.
    if _storied_mode and _story_beats_per_stop and not _phase5_ceiling_breached:
        try:
            from story_beat_injector import scrub_unfilled_roles, _UNFILLED_ROLE_PATTERN
            # Count occurrences before scrub
            _unfilled_before = len(_UNFILLED_ROLE_PATTERN.findall(complete_tour))
            if _unfilled_before > 0:
                # Build a combined beat list for all stops
                _all_beats_combined = []
                for _sb_list in _story_beats_per_stop:
                    _all_beats_combined.extend(_sb_list)
                complete_tour, _final_role_subs = scrub_unfilled_roles(complete_tour, _all_beats_combined)
                if _final_role_subs > 0:
                    print(f"  [LOCAL-391] Final assembly scrub: replaced {_final_role_subs} unfilled role(s)")
        except Exception as _391_scrub_err:
            print(f"  [LOCAL-391] Final scrub error (non-fatal): {_391_scrub_err}")

    # -------- [LOCAL-390] FINAL beat verification — measures the delivered text --------
    # This is the AUTHORITATIVE check. It runs against complete_tour AFTER every
    # gate (5.158 entity grounding, 5.159 form-claim, 5.16 contradicted-block),
    # after Phase 6 assembly, after D2 reference stripping, after all post-assembly
    # transforms. If a beat name is absent HERE, it is truly absent from what the
    # listener receives.
    if _storied_mode and _story_beats_per_stop and not _phase5_ceiling_breached:
        try:
            from story_beat_injector import verify_beats_in_final_tour
            _stop_names_for_verify = [p.get('name', f'Stop {i+1}') for i, p in enumerate(poi_list)]
            _final_results = verify_beats_in_final_tour(
                _story_beats_per_stop,
                complete_tour,
                _stop_names_for_verify,
                gate_removed_names=_gate_removed_names if '_gate_removed_names' in dir() else None,
            )
            print(f"\n  [LOCAL-390] FINAL beat verification (measured from delivered text):")
            for _fri, _fr in enumerate(_final_results):
                _fr_name = _stop_names_for_verify[_fri] if _fri < len(_stop_names_for_verify) else f'Stop {_fri+1}'
                _fr_dropped_str = str(_fr['dropped']) if _fr['dropped'] else '[]'
                _fr_causes = ''
                if _fr['drop_causes']:
                    _cause_parts = [f"{name}={cause}" for name, cause in _fr['drop_causes'].items()]
                    _fr_causes = f" causes=[{', '.join(_cause_parts)}]"
                print(f"    stop='{_fr_name}' beats_assigned={_fr['beats_assigned']} "
                      f"beats_in_output={_fr['beats_in_output']} dropped={_fr_dropped_str}{_fr_causes}")
        except Exception as _v390_err:
            print(f"  [LOCAL-390] Final beat verification error (non-fatal): {_v390_err}")

    # Print word count statistics
    print("\n=== Word Count Statistics ===")
    for poi in poi_list:
        print(f"Stop {poi['stop_number']}: {poi['name']} - {poi['word_count']} words")
    print("===========================\n")
    
    # Print total cost
    print(f"\nTotal API cost: ${total_cost:.4f} ({total_tokens} tokens)")
    
    # -------- [S20] Storied: store in cache after successful generation --------
    if _storied_mode and complete_tour and not _forced_stops_active:
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
                _import_logger.error("[S20] MISSING: tour_cache_layer1 (store_tour) — tour cache storage DISABLED")
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
        # [LOCAL-357] Stamp forced-stops banner at top of output file
        if _forced_stops_active:
            _forced_banner = (
                "=" * 70 + "\n"
                "⚠️  FORCED STOPS — VERIFICATION HARNESS (LOCAL-357)\n"
                "    This tour was generated with a forced stop list.\n"
                "    It is NOT a naturally-selected tour and must not be\n"
                "    scored as evidence of selection quality.\n"
                f"    Forced: {forced_stops}\n"
                "=" * 70 + "\n\n"
            )
            f.write(_forced_banner)
        f.write(complete_tour)
    
    print(f"\nTour text generated successfully!")

    # [LOCAL-230] Report network/API failure count for this generation run
    try:
        from venue_resolver import get_network_failure_count
        _l230_failures = get_network_failure_count()
        if _l230_failures > 0:
            print(f"  [LOCAL-230] ⚠ NETWORK FAILURES: {_l230_failures} API call(s) failed during this generation — tour may be degraded")
        else:
            print(f"  [LOCAL-230] Network failures: 0 (all API calls succeeded)")
    except ImportError:
        pass
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
    
    # [B1b] Expose poi_list at module level for stop_metrics verified-flag mapping
    _LAST_POI_LIST = list(poi_list)

    # [LOCAL-60] Expose generation cost at module level for cost metering
    _LAST_GENERATION_COST = {
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "cache_hit": False,
        "breakdown": {
            "llm": total_cost,  # Currently all tracked cost is LLM tokens
            "tts": 0.0,         # TTS cost tracked separately at orchestrator level
            "search": 0.0,      # Search cost tracked separately via work_story_searcher
        },
    }

    # -------- [LOCAL-410] Post-generation chain instrumentation --------
    # Print the full chain: serp_results → snippets_injected → beats_in_delivered_text
    if _local410_chain_log and complete_tour:
        print(f"\n{'=' * 72}")
        print(f"  [LOCAL-410] CHAIN INSTRUMENTATION (post-generation)")
        print(f"{'=' * 72}")
        _stop_blocks = re.split(r'(?=^Stop\s+\d+:)', complete_tour, flags=re.MULTILINE)
        for _cl_name, _cl_data in _local410_chain_log.items():
            # Count how many snippet-sourced facts appear in the delivered text
            _beats_found = 0
            _cl_snippets = _DIRECT_SNIPPETS_PER_STOP.get(_cl_name, []) if _DIRECT_SNIPPETS_PER_STOP else []
            for _snip in _cl_snippets[:12]:
                _snip_text = _snip.get('snippet', '')
                # Check if key phrases from the snippet appear in the tour
                _snip_words = [w for w in _snip_text.split() if len(w) >= 5]
                _distinctive_phrases = []
                for _wi in range(0, len(_snip_words) - 2, 3):
                    _phrase = ' '.join(_snip_words[_wi:_wi+3])
                    _distinctive_phrases.append(_phrase)
                for _dp in _distinctive_phrases[:5]:
                    if _dp.lower() in complete_tour.lower():
                        _beats_found += 1
                        break
            _cl_data['beats_in_delivered_text'] = _beats_found
            print(f"    {_cl_name[:50]}: "
                  f"serp_results={_cl_data['serp_results']} "
                  f"snippets_injected={_cl_data['snippets_injected']} "
                  f"beats_in_delivered_text={_beats_found}")
        print(f"{'=' * 72}")

    # Reset module-level snippets after use (don't pollute next generation)
    _DIRECT_SNIPPETS_PER_STOP = {}

    # [LOCAL-445-B] Final timing summary
    _phase_timer.start('verification')  # End packing, start verification marker
    _phase_timer.end('verification')  # Immediately end (verification is interspersed above)
    _phase_timer.summary()

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