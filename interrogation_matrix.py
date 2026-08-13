#!/usr/bin/env python3
"""interrogation_matrix.py — build the interrogation matrix from a stop description alone.

Before we can interrogate the internet for a story, we need to know WHAT TO ASK ABOUT.
That is a small fixed matrix of roles. Everything needed to fill it is already in the tour
— no corpus, no search, no DB, no network, no API key.

THE MATRIX IS NOT ART-CATALOGUE METADATA. The field names come from the museum case, but
each is a UNIVERSAL ROLE with a different filler per tour type:

    canonical_title — "the name of the smallest set". For a museum stop that is the
        stop/exhibit itself. Where the stop is not an individual object, fall through a
        LADDER: exhibit → exhibition → museum → city → state → country, first identifiable
        rung wins. For a restaurant tour: "whatever the user specified as the criteria for
        restaurant, if not the smallest area, if not province, if not then the country."

    english_title — "the translation of canonical_title into English, as most of the
        trusted sources are in English."

    artist — "the main person for the exhibit: for livre d'artiste it is the publisher,
        for painting it is the painter, for restaurant is the chef, for walking tour —
        whoever is in charge."

    publisher — "the publisher for livre d'artiste, for a restaurant it is the owner (as
        this position is basically an investor: who pays)."

    printed_by — "manufacture; for Exhibition is curator, for livre d'artiste is the
        printer."

    credit_line — "the keyword for which we will produce the story, taken from the
        sentences we want to fulfill."

    medium — "the title for excursion, whatever interests are named by the listener." In
        the MFA case that is the exhibition name.

    venue — "the location where the medium is displayed."

Record which ladder rung canonical_title landed on, so the caller knows how tight the
scope is. A stop resolved at "country" is a far weaker query seed than one resolved at
"exhibit", and the caller must be able to tell.

Every field carries provenance, never a bare value — following story_record_extract.py:
    {value, status, source, rung}
with status one of STRUCTURAL, CLAIMED, DERIVED, ABSENT.

A CLAIMED value is a question to go answer, not a fact.

    python3 interrogation_matrix.py --text-file TOUR_MFA_20260812_2030.txt --stop 2
    python3 interrogation_matrix.py --text-file fruitlands_museum_tour.txt --stop 1
"""
import argparse
import json
import os
import re
import sys
import textwrap
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import find_handles, measure, _fold, split_sentences  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# SLOT SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

SLOTS = [
    'canonical_title', 'english_title', 'artist', 'publisher',
    'printed_by', 'credit_line', 'medium', 'venue',
]

STATUSES = ('STRUCTURAL', 'CLAIMED', 'DERIVED', 'ABSENT')

# Ladder rungs for canonical_title, from tightest to loosest.
LADDER_RUNGS = ('exhibit', 'exhibition', 'museum', 'city', 'state', 'country')


def _cell(value: str, status: str, source: str, rung: str = '') -> Dict:
    """Create a provenance-bearing cell."""
    return {'value': value, 'status': status, 'source': source, 'rung': rung}


def _absent(rung: str = '') -> Dict:
    return {'value': '', 'status': 'ABSENT', 'source': '', 'rung': rung}


# ═══════════════════════════════════════════════════════════════════════════════
# STOP EXTRACTION — split a tour file into its stops
# ═══════════════════════════════════════════════════════════════════════════════

_STOP_HEADER = re.compile(r'^\s*(?:Stop|stop|STOP)\s+(\d+)\s*:\s*(.+?)\s*$', re.MULTILINE)


def extract_stops(full_text: str) -> Dict[int, Dict]:
    """Split a tour into individual stops with their text and headers."""
    matches = list(_STOP_HEADER.finditer(full_text))
    stops = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        title = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        stops[num] = {'title': title, 'text': full_text[start:end].strip()}
    return stops


def extract_tour_header(full_text: str) -> str:
    """Get everything before the first stop — the tour-level header."""
    m = _STOP_HEADER.search(full_text)
    if m:
        return full_text[:m.start()].strip()
    return ''


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR TYPE INFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

_WALKING_INDICATORS = re.compile(
    r'\b(walking\s+tour|walking|stroll|pedestrian|neighborhood|block|street)\b', re.I)
_MUSEUM_INDICATORS = re.compile(
    r'\b(museum|gallery|exhibit|exhibition|artwork|painting|sculpture)\b', re.I)
_RESTAURANT_INDICATORS = re.compile(
    r'\b(restaurant|dining|cuisine|chef|menu|bistro|café|cafe)\b', re.I)


def infer_tour_type(header: str, stop_text: str) -> str:
    """Infer tour type from header and stop text. Returns one of:
    museum_exhibition, museum, walking, restaurant, unknown.
    """
    combined = header + '\n' + stop_text
    low = combined.lower()

    # Check for walking tour
    if 'walking tour' in low or 'walking' in low.split('\n')[0]:
        return 'walking'

    # Check for restaurant
    if _RESTAURANT_INDICATORS.search(combined):
        restaurant_hits = len(_RESTAURANT_INDICATORS.findall(combined))
        if restaurant_hits >= 2:
            return 'restaurant'

    # Check for museum with exhibition
    if _MUSEUM_INDICATORS.search(combined):
        # Does the header or text name a specific exhibition?
        if re.search(r'\bexhibition\b', low) or re.search(
                r'^Step-by-Step.*?:.*?exhibition', combined, re.I | re.M):
            return 'museum_exhibition'
        return 'museum'

    return 'unknown'


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL EXTRACTION — what the tour format already encodes
# ═══════════════════════════════════════════════════════════════════════════════

_TITLE_LINE = re.compile(r'^\s*(?:Stop|stop|STOP)\s+\d+\s*:\s*(.+?)\s*$', re.MULTILINE)
_DIRECTIONS_LINE = re.compile(r'^\s*Directions\s*:\s*(.+?)\s*$', re.I | re.MULTILINE)
_ADDRESS_LINE = re.compile(r'^\s*Address\s*:\s*(.+?)\s*$', re.I | re.MULTILINE)
_TOUR_HEADER_LINE = re.compile(
    r'^Step-by-Step\s+Audio\s+Guided\s+Tour\s*:\s*(.+?)\s*$', re.I | re.MULTILINE)

# Exhibition name from the tour's first line
_EXHIBITION_IN_HEADER = re.compile(
    r'^Step-by-Step.*?:\s*(.+?)\s+(?:exhibition\s+)?at\s+(.+?)\s*[-–—]\s*'
    r'(Museum|Walking|Exhibit)\s+Tour', re.I | re.MULTILINE)
# Simpler: "X at Y - Z Tour"
_HEADER_AT_VENUE = re.compile(
    r'^Step-by-Step.*?:\s*(.+?)\s+at\s+(.+?)(?:\s*[-–—]\s*.+Tour)?$', re.I | re.MULTILINE)

# "Your final stop in Museum of Fine Arts, Boston: Au Soleil du Plafond."
_VENUE_FROM_DIRECTIONS = re.compile(
    r'\bstop\s+(?:in|at)\s+(.+?)(?:\s*[-–:.]|$)', re.I)
# "Continue through Museum of Fine Arts, Boston"
_VENUE_FROM_CONTINUE = re.compile(
    r'\bContinue\s+through\s+(.+?)(?:\s*[-–—.]|\s*$)', re.I)

# Parenthetical gloss: "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)"
_GLOSS = re.compile(r'^(.*?)\s*\(([^)]{4,80})\)\s*$')

# Location patterns for walking tours
_CITY_STATE_FROM_HEADER = re.compile(
    r'[-–—]\s*(.+?)\s*[-–—]\s*(?:Walking|Museum|Exhibit)\s+Tour', re.I)
# More general: "Beacon Hill, Boston"
_LOCATION_IN_HEADER = re.compile(
    r'^Step-by-Step.*?:\s*(.+?)(?:\s*[-–—])', re.I | re.MULTILINE)


def _extract_venue_from_tour(header: str, stop_text: str) -> Optional[Tuple[str, str]]:
    """Try to find the venue (the location that holds the exhibition)."""
    # From directions line
    dm = _DIRECTIONS_LINE.search(stop_text)
    if dm:
        vm = _VENUE_FROM_DIRECTIONS.search(dm.group(1))
        if vm:
            return (vm.group(1).strip().rstrip('.,;:'), 'Directions line')
        vc = _VENUE_FROM_CONTINUE.search(dm.group(1))
        if vc:
            return (vc.group(1).strip().rstrip('.,;:'), 'Directions line')

    # From the tour header
    m = _EXHIBITION_IN_HEADER.search(header)
    if m:
        return (m.group(2).strip().rstrip('.,;:'), 'tour header')

    m = _HEADER_AT_VENUE.search(header)
    if m:
        venue_candidate = m.group(2).strip().rstrip('.,;:')
        # Only accept if it looks like a place (contains a comma or known venue word)
        if ',' in venue_candidate or re.search(
                r'\b(museum|gallery|hall|center|centre|church|park|square)\b',
                venue_candidate, re.I):
            return (venue_candidate, 'tour header')

    return None


def _extract_exhibition_name(header: str, stop_text: str) -> Optional[Tuple[str, str]]:
    """Try to find the exhibition name (= medium slot)."""
    # From tour header: "Step-by-Step Audio Guided Tour: Picasso, Miro, Dali: Unbound
    # exhibition at MFA, Boston, MA - Museum Tour"
    m = _EXHIBITION_IN_HEADER.search(header)
    if m:
        return (m.group(1).strip().rstrip('.,;:'), 'tour header')

    # Check if header has "X at Y" pattern where X is the exhibition
    m = _HEADER_AT_VENUE.search(header)
    if m:
        candidate = m.group(1).strip()
        # Must not be just a place name (has to be a "title" not "Beacon Hill, Boston")
        if not re.match(r'^[A-Z][a-z]+\s+[A-Z]', candidate):
            return None
        # Reject if it's a place name with comma (city, state pattern)
        if re.match(r'^[^,]+,\s*[A-Z]{2}\b', candidate):
            return None
        return (candidate, 'tour header')

    # Look in the text for an exhibition named in quotes
    em = re.search(r'\bexhibition\s+[""]([^""]{4,70})[""]', stop_text, re.I)
    if em:
        return (em.group(1).strip(), 'prose reference')
    em = re.search(r'[""]([^""]{4,70})[""]\s+exhibition', stop_text, re.I)
    if em:
        return (em.group(1).strip(), 'prose reference')

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE EXTRACTION — who the prose says did what
# ═══════════════════════════════════════════════════════════════════════════════

# Principal person (artist role)
_PRINCIPAL_PATTERNS = [
    # "by X" for paintings / artworks
    (re.compile(r'\bby\s+(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'), 'artist attribution'),
    # "X's" possessive
    (re.compile(r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)\'s\s+(?:masterful|'
                r'illustrations?|work|paintings?|creative|bold|distinct|captivating|'
                r'masterpiece|contributions|intricate|exceptional)'), 'possessive attribution'),
    # "artist/painter/architect X"
    (re.compile(r'\b(?:artist|painter|architect|sculptor|author|writer|designer|'
                r'illustrator)\s+(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'),
     'role attribution'),
    # "X, a/an/the/known/renowned..."
    (re.compile(r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+),?\s+(?:a|an|the|known|'
                r'renowned|celebrated|prominent|famous|noted)\s+(?:figure|artist|painter|'
                r'architect|sculptor|publisher|printmaker|poet|writer|landscape|philanthropist'
                r'|reformer)'), 'appositive attribution'),
    # "created/designed/painted by X"
    (re.compile(r'\b(?:created|designed|painted|crafted|built|established|founded)\s+by\s+'
                r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'), 'passive attribution'),
]

# Publisher / who pays
_PUBLISHER_PATTERNS = [
    (re.compile(r'\bpublished\s+(?:by|to)\s+(?P<v>[A-Z][^.,;:]{2,55})'), 'published by'),
    (re.compile(r'\bcommissioned\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'), 'commissioned by'),
    (re.compile(r'\bpublishers?\s+such\s+as\s+(?P<v>[A-Z][^.,;:]{2,55})'), 'publisher mention'),
    (re.compile(r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*),\s*a\s+(?:visionary\s+)?'
                r'publisher'), 'appositive publisher'),
]

# Printed by / manufacture
_PRINTED_BY_PATTERNS = [
    (re.compile(r'\bprinted\s+by\s+(?:the\s+)?(?P<v>[A-Z][^.,;:]{2,55})'),
     'printed by'),
    (re.compile(r'\bat\s+(?:the\s+)?(?P<v>[A-Z][^.,;:]{2,55})\s+'
                r'(?:workshop|atelier|press|printshop|studio)'), 'at workshop'),
    # "collaboration between artist, poet, and X" where X is a printer
    (re.compile(r'\bcollaboration\s+between\b[^.]{0,80}\band\s+'
                r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)'), 'collaboration with'),
]


def _clean_name(v: str) -> str:
    """Clean extracted name."""
    v = re.sub(r'\s+', ' ', v).strip().rstrip('.,;:')
    # Remove trailing common words
    v = re.sub(r'\s+(?:and|in|to|for|with|this|the|a|is|was|at|on)$', '', v, flags=re.I)
    return v.strip()


def _extract_principal(stop_text: str, stop_title: str) -> Optional[Tuple[str, str]]:
    """Find the principal person (artist role) from stop text.

    Strategy: use story_opportunity_scan handles as the source of truth for WHO
    matters most in this stop. The person with the highest sentence count who is
    a proper noun and is NOT the stop title itself is the principal. This is far
    more reliable than regex patterns alone, because it captures the protagonist
    regardless of how they are introduced grammatically.

    Falls back to regex patterns if no proper-noun handle qualifies.
    """
    m = measure(stop_text)
    handles = m.get('handles', [])

    # Filter to proper nouns that are people (not places, not the title)
    _PLACE_WORDS = frozenset({'museum', 'gallery', 'library', 'park', 'square',
                              'street', 'church', 'chapel', 'hill', 'house',
                              'ave', 'boston', 'arts', 'fine', 'st', 'rd', 'ln',
                              'blvd', 'river', 'mountain', 'lake', 'bay',
                              'state', 'national', 'building'})
    _NOT_PEOPLE_PREFIXES = frozenset({'the', 'at', 'in', 'on', 'le', 'la', 'les'})
    title_folded = _fold(stop_title)

    person_handles = []
    for h in handles:
        if h['kind'] != 'proper noun':
            continue
        surface = h['surface']
        # Skip handles containing newlines (structural artifacts)
        if '\n' in surface:
            continue
        surface_folded = _fold(surface)
        # Skip if it IS the work title exactly (not a person appearing in the title)
        if title_folded and surface_folded == title_folded:
            continue
        # Skip handles starting with prepositions/articles (not person names)
        first_word = surface_folded.split()[0] if surface_folded.split() else ''
        if first_word in _NOT_PEOPLE_PREFIXES:
            continue
        # Skip obvious place names
        handle_words = set(surface_folded.split())
        if handle_words & _PLACE_WORDS:
            continue
        # Must appear in at least 2 sentences to be meaningful
        if h.get('sentences', 0) < 2:
            continue
        person_handles.append(h)

    if person_handles:
        # Pick the one with the most sentences (= most prominent)
        person_handles.sort(key=lambda x: (x.get('sentences', 0), x.get('agency', 0)),
                           reverse=True)
        best = person_handles[0]
        return (best['surface'], f"most prominent person ({best['sentences']} sentences)")

    # Fallback to regex patterns
    candidates = []
    for pat, source in _PRINCIPAL_PATTERNS:
        for match in pat.finditer(stop_text):
            name = _clean_name(match.group('v'))
            if len(name) < 4 or len(name.split()) < 2:
                continue
            if _fold(name) in _fold(stop_title):
                continue
            candidates.append((name, source, match.start()))

    if not candidates:
        return None

    # Prefer role/appositive attributions
    def score(c):
        name, source, pos = c
        s = 0
        if 'role attribution' in source or 'appositive' in source:
            s += 10
        if 'passive attribution' in source:
            s += 5
        s -= pos / 1000
        return s

    candidates.sort(key=score, reverse=True)
    return (candidates[0][0], candidates[0][1])


def _extract_publisher(stop_text: str) -> Optional[Tuple[str, str]]:
    """Find who pays (publisher role)."""
    for pat, source in _PUBLISHER_PATTERNS:
        m = pat.search(stop_text)
        if m:
            name = _clean_name(m.group('v'))
            if len(name) >= 3:
                return (name, source)
    return None


def _extract_printed_by(stop_text: str) -> Optional[Tuple[str, str]]:
    """Find the manufacturer (printed_by role)."""
    for pat, source in _PRINTED_BY_PATTERNS:
        m = pat.search(stop_text)
        if m:
            name = _clean_name(m.group('v'))
            if len(name) >= 3:
                return (name, source)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CREDIT LINE — the keyword the story will be built around
# ═══════════════════════════════════════════════════════════════════════════════

def _pick_credit_line(stop_text: str, exclude_values: List[str] = None) -> Optional[Tuple[str, str]]:
    """Pick the best credit_line from story_opportunity_scan handles.

    credit_line is the keyword the story will be built around, "taken from the
    sentences we want to fulfill." The best credit_line is the highest-value
    non-DEVELOPED handle: prefer FLAT (an established subject carrying no stakes),
    then MENTIONED, then DANGLING.

    Excludes handles that duplicate already-filled slots (e.g. canonical_title, artist).
    """
    exclude_folded = set(_fold(v) for v in (exclude_values or []) if v)

    m = measure(stop_text)
    handles = m.get('handles', [])

    # Priority order: FLAT > MENTIONED > DANGLING. Never DEVELOPED.
    by_state = {'FLAT': [], 'MENTIONED': [], 'DANGLING': []}
    _NOT_CREDIT_PREFIXES = frozenset({'the', 'at', 'in', 'on', 'le', 'la', 'les',
                                       'a', 'an', 'au', 'du', 'des', 'un', 'une'})
    _PLACE_WORDS_CL = frozenset({'museum', 'library', 'park', 'square',
                                  'street', 'church', 'chapel', 'house',
                                  'ave', 'boston', 'arts', 'fine', 'avenue', 'st',
                                  'rd', 'ln', 'blvd', 'mountain', 'lake',
                                  'bay', 'building'})
    # Handles ending in these are rooms/venues, not story subjects
    _VENUE_SUFFIXES = ('gallery', 'museum', 'room', 'hall', 'center', 'centre',
                       'farmhouse', 'house', 'building', 'st', 'ave', 'rd',
                       'street', 'avenue', 'blvd', 'ln', 'square')
    for h in handles:
        state = h.get('state', '')
        if state in by_state:
            # Skip handles containing newlines (structural artifacts)
            if '\n' in h['surface']:
                continue
            # Skip handles whose folded surface matches any excluded value
            hf = _fold(h['surface'])
            if any(hf in ex or ex in hf for ex in exclude_folded if ex):
                continue
            # Skip handles starting with prepositions/articles (fragments)
            first_word = hf.split()[0] if hf.split() else ''
            if first_word in _NOT_CREDIT_PREFIXES:
                continue
            # Skip if ALL significant words are place-like (pure location handles)
            handle_words = set(hf.split())
            non_place_words = handle_words - _PLACE_WORDS_CL
            if not non_place_words:
                continue
            # Skip handles ending in venue/room words (navigational references)
            last_word = hf.split()[-1] if hf.split() else ''
            if last_word in _VENUE_SUFFIXES:
                continue
            by_state[state].append(h)

    # Within each tier, prefer proper nouns, then titles, then loaded nouns.
    # Within same kind, prefer more sentences (more material to build on).
    def handle_score(h):
        kind_rank = {'proper noun': 3, 'title': 2, 'loaded noun': 1}.get(h['kind'], 0)
        return (kind_rank, h.get('sentences', 0))

    for state in ('FLAT', 'MENTIONED', 'DANGLING'):
        candidates = by_state[state]
        if candidates:
            candidates.sort(key=handle_score, reverse=True)
            best = candidates[0]
            return (best['surface'], f'story_opportunity_scan/{state}')

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL TITLE LADDER
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_canonical_title(
    stop_title: str, stop_text: str, tour_header: str, tour_type: str
) -> Tuple[str, str, str]:
    """Resolve canonical_title via the ladder. Returns (value, source, rung).

    Ladder: exhibit → exhibition → museum → city → state → country.
    First identifiable rung wins.
    """
    # Rung 1: exhibit (the stop title itself, if it names a specific thing)
    if stop_title:
        # Clean up quoted/numbered prefixes
        title_clean = re.sub(r'^\d+\.\s*', '', stop_title).strip()
        # Remove wrapping quotes
        title_clean = re.sub(r'^[""\']|[""\']$', '', title_clean).strip()
        # If there's a parenthetical gloss, use only the non-gloss portion
        gm = _GLOSS.match(title_clean)
        if gm:
            title_clean = gm.group(1).strip()
        if title_clean and len(title_clean) > 2:
            return (title_clean, 'stop heading', 'exhibit')

    # Rung 2: exhibition (from tour header)
    exh = _extract_exhibition_name(tour_header, stop_text)
    if exh:
        return (exh[0], exh[1], 'exhibition')

    # Rung 3: museum / venue
    venue = _extract_venue_from_tour(tour_header, stop_text)
    if venue:
        return (venue[0], venue[1], 'museum')

    # Rung 4: city (from address or header)
    addr_m = _ADDRESS_LINE.search(stop_text)
    if addr_m:
        # Try to extract city from address like "24 Beacon St, Boston, MA 02133"
        parts = addr_m.group(1).split(',')
        if len(parts) >= 2:
            city = parts[-2].strip() if len(parts) >= 3 else parts[-1].strip()
            city = re.sub(r'\s*\d{5}.*$', '', city).strip()
            city = re.sub(r'\s*[A-Z]{2}\s*$', '', city).strip()
            if city and len(city) > 2:
                return (city, 'address line', 'city')

    # Rung 5: state
    if addr_m:
        state_m = re.search(r'\b([A-Z]{2})\s+\d{5}', addr_m.group(1))
        if state_m:
            return (state_m.group(1), 'address line', 'state')

    # Rung 6: country (last resort)
    return ('', '', 'country')


# ═══════════════════════════════════════════════════════════════════════════════
# ENGLISH TITLE
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_english_title(
    canonical_title: str, stop_title: str, stop_text: str
) -> Tuple[str, str]:
    """Resolve english_title. Returns (value, source)."""
    if not canonical_title:
        return ('', '')

    # Check for parenthetical gloss in stop title
    gm = _GLOSS.match(stop_title)
    if gm:
        # The gloss IS the English title
        return (gm.group(2).strip(), 'parenthetical gloss in stop heading')

    # Quick check: common non-English words indicate the title is not English
    _NON_ENGLISH = re.compile(
        r'\b(du|de|des|le|la|les|au|aux|und|der|die|das|del|della|'
        r'il|gli|une|plafond|soleil|lézard|plumes|d\'or)\b', re.I)
    if _NON_ENGLISH.search(canonical_title):
        return ('', '')

    # If the title is all ASCII and doesn't contain known foreign words,
    # treat it as English
    try:
        canonical_title.encode('ascii')
        return (canonical_title, 'title is already English')
    except UnicodeEncodeError:
        pass

    # Mostly ASCII check (allow a few accented chars in English loan words)
    ascii_ratio = sum(1 for c in canonical_title if ord(c) < 128) / max(len(canonical_title), 1)
    if ascii_ratio > 0.9:
        # But check for accented characters that suggest non-English
        if not _NON_ENGLISH.search(canonical_title):
            return (canonical_title, 'title is already English')

    return ('', '')


# ═══════════════════════════════════════════════════════════════════════════════
# WALKING TOUR SPECIFICS
# ═══════════════════════════════════════════════════════════════════════════════

_PERSON_IN_CHARGE_PATTERNS = [
    # "designed by X"
    (re.compile(r'\b(?:designed|built|founded|established|created)\s+by\s+(?:architect\s+)?'
                r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'), 'designed/built by'),
    # "architect/designer X"
    (re.compile(r'\b(?:architect|designer|builder|founder)\s+'
                r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'), 'role title'),
]


def _extract_person_in_charge(stop_text: str) -> Optional[Tuple[str, str]]:
    """For walking tours: whoever is in charge."""
    for pat, source in _PERSON_IN_CHARGE_PATTERNS:
        m = pat.search(stop_text)
        if m:
            name = _clean_name(m.group('v'))
            if len(name) >= 4 and len(name.split()) >= 2:
                return (name, source)

    # Fall through to general principal extraction
    return _extract_principal(stop_text, '')


# ═══════════════════════════════════════════════════════════════════════════════
# VENUE EXTRACTION — city for walking tours
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_city_from_header(tour_header: str) -> Optional[Tuple[str, str]]:
    """Extract city/location from tour header for walking tours."""
    # "Step-by-Step Audio Guided Tour: Beacon Hill, Boston - Walking Tour"
    m = re.search(r'Step-by-Step\s+Audio\s+Guided\s+Tour\s*:\s*(.+?)\s*[-–—]\s*'
                  r'(?:Walking|Museum|Exhibit)\s+Tour', tour_header, re.I)
    if m:
        location = m.group(1).strip()
        return (location, 'tour header')
    # Fallback: anything after the colon and before a dash
    m = re.search(r':\s*(.+?)\s*[-–—]', tour_header)
    if m:
        location = m.group(1).strip()
        return (location, 'tour header')
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# THE MAIN BUILD
# ═══════════════════════════════════════════════════════════════════════════════

def build_matrix(stop_text: str, tour_type: str = '', user_interests: str = '',
                 tour_context: str = '') -> Dict[str, Dict]:
    """Build the interrogation matrix from a stop description alone.

    Args:
        stop_text: The text of a single stop (including its header line).
        tour_type: Optional hint ('museum_exhibition', 'museum', 'walking', 'restaurant').
                   If empty, inferred from the text.
        user_interests: What the listener named as their interest (becomes medium hint).
        tour_context: The rest of the tour when available — the ladder and medium often
                      need it, since a stop may not name its own exhibition while the
                      tour header does.

    Returns:
        Dict mapping slot names to provenance dicts {value, status, source, rung}.
    """
    # Extract structural information
    tour_header = extract_tour_header(tour_context) if tour_context else ''
    stops_from_context = extract_stops(tour_context) if tour_context else {}

    # Determine stop title from the stop_text itself
    title_m = _TITLE_LINE.search(stop_text)
    stop_title = title_m.group(1).strip() if title_m else ''

    # Infer tour type if not given
    if not tour_type:
        tour_type = infer_tour_type(tour_header or tour_context, stop_text)

    matrix: Dict[str, Dict] = {}

    # ─── canonical_title ───────────────────────────────────────────────────
    ct_val, ct_source, ct_rung = _resolve_canonical_title(
        stop_title, stop_text, tour_header, tour_type)
    if ct_val:
        matrix['canonical_title'] = _cell(ct_val, 'STRUCTURAL', ct_source, ct_rung)
    else:
        matrix['canonical_title'] = _absent('country')

    # ─── english_title ─────────────────────────────────────────────────────
    if ct_val:
        # Check if the stop title has a gloss
        et_val, et_source = _resolve_english_title(ct_val, stop_title, stop_text)
        if et_val:
            matrix['english_title'] = _cell(et_val, 'STRUCTURAL', et_source)
        else:
            matrix['english_title'] = _absent()
    else:
        matrix['english_title'] = _absent()

    # ─── artist (principal) ────────────────────────────────────────────────
    if tour_type == 'walking':
        principal = _extract_person_in_charge(stop_text)
    else:
        principal = _extract_principal(stop_text, stop_title)

    if principal:
        matrix['artist'] = _cell(principal[0], 'CLAIMED', principal[1])
    else:
        matrix['artist'] = _absent()

    # ─── publisher (who pays) ──────────────────────────────────────────────
    pub = _extract_publisher(stop_text)
    if pub:
        matrix['publisher'] = _cell(pub[0], 'CLAIMED', pub[1])
    else:
        matrix['publisher'] = _absent()

    # ─── printed_by (manufacture) ──────────────────────────────────────────
    pb = _extract_printed_by(stop_text)
    if pb:
        matrix['printed_by'] = _cell(pb[0], 'CLAIMED', pb[1])
    else:
        matrix['printed_by'] = _absent()

    # ─── medium (the exhibition name / excursion title) ────────────────────
    if user_interests:
        matrix['medium'] = _cell(user_interests, 'STRUCTURAL', 'user_interests')
    else:
        exh = _extract_exhibition_name(tour_header, stop_text)
        if exh:
            matrix['medium'] = _cell(exh[0], 'STRUCTURAL', exh[1])
        else:
            # For museum without exhibition, ABSENT is correct
            matrix['medium'] = _absent()

    # ─── venue (where the medium is displayed) ─────────────────────────────
    if tour_type == 'walking':
        # For walking tours, venue = the city
        city = _extract_city_from_header(tour_header)
        if city:
            # Extract just the city portion
            location = city[0]
            # "Beacon Hill, Boston" -> venue is the broader location
            parts = [p.strip() for p in location.split(',')]
            if len(parts) >= 2:
                # Use "City, State" if available
                venue_val = ', '.join(parts[-2:]) if len(parts) > 2 else location
            else:
                venue_val = location
            matrix['venue'] = _cell(venue_val, 'STRUCTURAL', city[1])
        else:
            # Try address
            addr_m = _ADDRESS_LINE.search(stop_text)
            if addr_m:
                parts = addr_m.group(1).split(',')
                if len(parts) >= 2:
                    city_name = parts[-2].strip() if len(parts) >= 3 else parts[-1].strip()
                    city_name = re.sub(r'\s*\d{5}.*$', '', city_name).strip()
                    state = ''
                    state_m = re.search(r'\b([A-Z]{2})\b', parts[-1]) if len(parts) >= 2 else None
                    if state_m:
                        state = state_m.group(1)
                    venue_val = f"{city_name}, {state}" if state else city_name
                    matrix['venue'] = _cell(venue_val, 'STRUCTURAL', 'address line')
                else:
                    matrix['venue'] = _absent()
            else:
                matrix['venue'] = _absent()
    else:
        venue = _extract_venue_from_tour(tour_header, stop_text)
        if venue:
            matrix['venue'] = _cell(venue[0], 'STRUCTURAL', venue[1])
        else:
            # Try from address
            addr_m = _ADDRESS_LINE.search(stop_text)
            if addr_m:
                # For museums, the venue IS the museum, derivable from directions
                matrix['venue'] = _absent()
            else:
                matrix['venue'] = _absent()

    # ─── credit_line (story keyword) ──────────────────────────────────────
    # Must come AFTER medium and venue so they can be excluded.
    # Exclude values already used in other slots to avoid redundancy.
    exclude = [
        matrix.get('canonical_title', {}).get('value', ''),
        matrix.get('english_title', {}).get('value', ''),
        matrix.get('artist', {}).get('value', ''),
        matrix.get('publisher', {}).get('value', ''),
        matrix.get('printed_by', {}).get('value', ''),
        matrix.get('venue', {}).get('value', ''),
        matrix.get('medium', {}).get('value', ''),
    ]
    cl = _pick_credit_line(stop_text, exclude_values=exclude)
    if cl:
        matrix['credit_line'] = _cell(cl[0], 'DERIVED', cl[1])
    else:
        matrix['credit_line'] = _absent()

    return matrix


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

_MARK = {'STRUCTURAL': '  ', 'CLAIMED': '? ', 'DERIVED': '~ ', 'ABSENT': '  '}


def report(matrix: Dict[str, Dict], tour_type: str, stop_num: int) -> None:
    print(f"\n{'=' * 78}")
    print(f"INTERROGATION MATRIX — stop {stop_num} ({tour_type})")
    print(f"{'=' * 78}\n")

    for slot in SLOTS:
        cell = matrix.get(slot, _absent())
        mark = _MARK[cell['status']]
        val = cell['value'] or '—'
        rung = f" [{cell['rung']}]" if cell.get('rung') else ''
        print(f" {mark}{slot:18} = {val:50} {cell['status']}{rung}")
        if cell['status'] == 'CLAIMED' and cell.get('source'):
            print(f"   {'':18}   from: {cell['source'][:60]}")

    print(f"\n{'-' * 78}")
    statuses = [matrix.get(s, _absent())['status'] for s in SLOTS]
    for st in STATUSES:
        count = statuses.count(st)
        if count:
            print(f"  {st:12} {count}")
    print(f"{'=' * 78}")


def coverage_table(results: List[Dict]) -> None:
    """Print a coverage table over multiple stops."""
    print(f"\n{'=' * 78}")
    print("COVERAGE TABLE")
    print(f"{'=' * 78}\n")

    # Header
    header = f"  {'tour':40} {'stop':>4}  "
    for slot in SLOTS:
        header += f"{slot[:6]:>7}"
    print(header)
    print(f"  {'-' * 74}")

    for r in results:
        row = f"  {r['tour'][:39]:40} {r['stop']:>4}  "
        for slot in SLOTS:
            cell = r['matrix'].get(slot, _absent())
            st = cell['status'][0]  # S, C, D, A
            row += f"{'':>3}{st:>4}"
        print(row)

    # Summary by tour type
    print(f"\n  {'-' * 74}")
    print(f"\n  ABSENT counts by tour type:")
    by_type = {}
    for r in results:
        t = r.get('tour_type', 'unknown')
        if t not in by_type:
            by_type[t] = []
        absent_count = sum(1 for s in SLOTS
                          if r['matrix'].get(s, _absent())['status'] == 'ABSENT')
        by_type[t].append(absent_count)

    for t, counts in sorted(by_type.items()):
        avg = sum(counts) / len(counts)
        print(f"    {t:25} avg={avg:.1f}  per-stop: {counts}")

    print(f"\n{'=' * 78}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--text-file', required=True,
                   help='Tour file to process')
    p.add_argument('--stop', type=int, default=0,
                   help='Stop number (0 = all stops)')
    p.add_argument('--tour-type', default='',
                   help='Tour type hint (museum_exhibition, museum, walking, restaurant)')
    p.add_argument('--json', dest='as_json', action='store_true')
    p.add_argument('--all', dest='run_all', action='store_true',
                   help='Process all stops and print coverage table')
    a = p.parse_args()

    full_text = open(a.text_file, encoding='utf-8').read()
    stops = extract_stops(full_text)

    if not stops:
        sys.exit(f"No stops found in {a.text_file}")

    tour_type = a.tour_type or infer_tour_type(
        extract_tour_header(full_text), list(stops.values())[0]['text'] if stops else '')

    if a.stop > 0:
        if a.stop not in stops:
            sys.exit(f"Stop {a.stop} not found. Available: {sorted(stops.keys())}")
        stop_data = stops[a.stop]
        matrix = build_matrix(
            stop_text=stop_data['text'],
            tour_type=tour_type,
            tour_context=full_text,
        )
        if a.as_json:
            print(json.dumps(matrix, ensure_ascii=False, indent=2))
        else:
            report(matrix, tour_type, a.stop)
    else:
        # Process all stops
        results = []
        tour_name = os.path.basename(a.text_file)
        for num in sorted(stops.keys()):
            stop_data = stops[num]
            matrix = build_matrix(
                stop_text=stop_data['text'],
                tour_type=tour_type,
                tour_context=full_text,
            )
            results.append({
                'tour': tour_name, 'stop': num,
                'tour_type': tour_type, 'matrix': matrix,
            })
            if not a.as_json:
                report(matrix, tour_type, num)

        if a.as_json:
            out = [{k: v for k, v in r.items() if k != 'matrix'} | {'matrix': r['matrix']}
                   for r in results]
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            coverage_table(results)


if __name__ == '__main__':
    main()
