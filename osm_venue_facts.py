"""osm_venue_facts.py — LOCAL-355: Source practical facts from OSM for ALL venue kinds.

Generalises LOCAL-353's dining-only approach to museums, galleries, parks,
landmarks, viewpoints, and any other venue that has OSM presence.

Design principle: SAME AS PRACTICAL FACTS GATE — only source what OSM says.
If a tag is absent, say nothing. Never infer fee from venue category, never
infer queue advice from popularity.

Venue type detection:
  - Dining: amenity=restaurant|cafe|ice_cream|bar|fast_food
  - Museum/Gallery: tourism=museum|gallery, amenity=museum|arts_centre
  - Park/Garden: leisure=park|garden
  - Viewpoint: tourism=viewpoint
  - Historic: historic=castle|monument|memorial|ruins|archaeological_site
  - Artwork: tourism=artwork
  - Attraction: tourism=attraction

Extracted fields vary by kind:
  - ALL: opening_hours, fee, website
  - Dining: payment, reservation, price_range, cuisine
  - Museum: fee (admission), description (may contain pricing), wheelchair
  - Park: opening_hours (seasonal), fee
  - Viewpoint/landmark: opening_hours if gated, fee if charged

Returns:
  - formatted sentence (what the listener hears) — one sentence per Michael's format
  - source_text (raw OSM tag dump, for gate verification)
  - source_url (OSM permalink for auditability)
"""

import logging
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_HEADERS = {
    "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
}

# Rate limiting: Overpass recommends max 2 requests per 10s
_overpass_lock = threading.Lock()
_overpass_last_request_time = 0.0
_OVERPASS_MIN_INTERVAL = 5.0  # Conservative: 1 request per 5 seconds


# ---------------------------------------------------------------------------
# Venue kind classification
# ---------------------------------------------------------------------------

# OSM tag → venue kind mapping.
# Order matters: first match wins.
_VENUE_KIND_RULES = [
    # (tag_key, tag_value_regex, kind)
    ("amenity", r"restaurant|cafe|ice_cream|bar|fast_food", "dining"),
    ("tourism", r"museum|gallery", "museum"),
    ("amenity", r"museum|arts_centre", "museum"),
    ("leisure", r"park|garden", "park"),
    ("tourism", r"viewpoint", "viewpoint"),
    ("tourism", r"artwork", "artwork"),
    ("tourism", r"attraction", "attraction"),
    ("historic", r"castle|monument|memorial|ruins|archaeological_site", "historic"),
]

# Overpass query filter groups — what to search for in OSM
# Each group is a set of tag filters; we search all that could match.
_OVERPASS_FILTERS = [
    # Dining
    '["amenity"~"restaurant|cafe|ice_cream|bar|fast_food"]',
    # Museum/Gallery
    '["tourism"~"museum|gallery"]',
    '["amenity"~"museum|arts_centre"]',
    # Parks
    '["leisure"~"park|garden"]',
    # Tourism/historic
    '["tourism"~"viewpoint|artwork|attraction"]',
    '["historic"~"castle|monument|memorial|ruins|archaeological_site"]',
]


def classify_venue_kind(tags: Dict[str, str]) -> str:
    """Classify an OSM element into a venue kind based on its tags.

    Returns one of: 'dining', 'museum', 'park', 'viewpoint', 'artwork',
    'attraction', 'historic', or 'unknown'.
    """
    for tag_key, pattern, kind in _VENUE_KIND_RULES:
        value = tags.get(tag_key, "")
        if value and re.match(pattern, value, re.IGNORECASE):
            return kind
    return "unknown"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OsmVenueFacts:
    """Extracted practical facts from OSM for one venue/stop."""
    stop_title: str
    venue_kind: str = "unknown"  # dining, museum, park, viewpoint, etc.
    osm_id: Optional[int] = None
    osm_type: Optional[str] = None  # 'node', 'way', 'relation'
    tags: Dict[str, str] = field(default_factory=dict)

    # Universal facts
    opening_hours: str = ""
    fee: str = ""            # "yes", "no", or "" (absent)
    fee_details: str = ""    # From description or charge tag (e.g. "€8, reduced €6")
    website: str = ""        # For timed entry / booking

    # Dining-specific
    payment_info: str = ""   # e.g. "Cash only"
    reservation: str = ""    # e.g. "Reservations required"
    price_range: str = ""    # e.g. "€€"
    cuisine: str = ""

    # Museum-specific
    wheelchair: str = ""     # yes/no/limited

    # Metadata
    country_code: str = ""
    source_url: str = ""
    source_text: str = ""

    def format_practical_sentence(self) -> str:
        """Format facts into ONE listener-friendly sentence.

        Michael's format (D264): a band or a fact plus the practical gotcha.
        "Free on the first Sunday of the month, otherwise €10, timed entry
        booked online" is the shape.

        Only includes facts present in OSM. Never invents.
        """
        if self.venue_kind == "dining":
            return self._format_dining()
        elif self.venue_kind == "museum":
            return self._format_museum()
        elif self.venue_kind in ("park", "viewpoint", "historic", "attraction", "artwork"):
            return self._format_outdoor()
        else:
            return self._format_generic()

    def _format_dining(self) -> str:
        """Format dining facts — preserves LOCAL-353 behaviour."""
        parts = []
        if self.opening_hours:
            parts.append(self._humanize_hours(self.opening_hours))
        if self.payment_info:
            parts.append(self.payment_info)
        if self.reservation:
            parts.append(self.reservation)
        if self.price_range:
            parts.append(self.price_range)
        return ". ".join(parts) if parts else ""

    def _format_museum(self) -> str:
        """Format museum facts — fee + hours + booking in one sentence."""
        parts = []

        # Fee / admission is the museum equivalent of price band
        if self.fee == "no":
            if self.fee_details:
                parts.append(self.fee_details)
            else:
                parts.append("Free admission")
        elif self.fee == "yes":
            if self.fee_details:
                parts.append(self.fee_details)
            else:
                parts.append("Admission charged")

        # Opening hours
        if self.opening_hours:
            parts.append(self._humanize_hours(self.opening_hours))

        # Booking/timed entry
        if self.reservation:
            parts.append(self.reservation)

        return ", ".join(parts) if parts else ""

    def _format_outdoor(self) -> str:
        """Format park/viewpoint/historic facts."""
        parts = []

        if self.fee == "no":
            parts.append("Free access")
        elif self.fee == "yes":
            if self.fee_details:
                parts.append(self.fee_details)
            else:
                parts.append("Admission charged")

        if self.opening_hours:
            parts.append(self._humanize_hours(self.opening_hours))

        return ", ".join(parts) if parts else ""

    def _format_generic(self) -> str:
        """Fallback for unknown venue kinds."""
        parts = []
        if self.opening_hours:
            parts.append(self._humanize_hours(self.opening_hours))
        if self.fee == "no":
            parts.append("Free")
        elif self.fee == "yes" and self.fee_details:
            parts.append(self.fee_details)
        return ", ".join(parts) if parts else ""

    def _humanize_hours(self, raw: str) -> str:
        """Convert OSM opening_hours to a listener-friendly phrase.

        Light reformatting only — the gate verifies against source.
        """
        raw = raw.strip()
        if not raw:
            return ""
        formatted = raw.replace(";", ",")
        return f"open {formatted}" if not formatted.lower().startswith("open") else formatted

    def is_empty(self) -> bool:
        """True if no sourceable facts were found."""
        return not any([self.opening_hours, self.payment_info,
                        self.reservation, self.price_range,
                        self.fee, self.fee_details])

    # Backward compatibility: LOCAL-353 used format_operational_details
    def format_operational_details(self) -> str:
        """Alias for backward compatibility with osm_dining_facts interface."""
        return self.format_practical_sentence()


# ---------------------------------------------------------------------------
# Overpass query
# ---------------------------------------------------------------------------

def _overpass_request(query: str, context: str = "") -> Optional[dict]:
    """Make a rate-limited Overpass API request.

    Returns parsed JSON or None on failure.
    """
    import requests as _http

    global _overpass_last_request_time

    with _overpass_lock:
        now = time.time()
        elapsed = now - _overpass_last_request_time
        if elapsed < _OVERPASS_MIN_INTERVAL:
            time.sleep(_OVERPASS_MIN_INTERVAL - elapsed)
        _overpass_last_request_time = time.time()

    for attempt in range(2):
        try:
            resp = _http.post(
                _OVERPASS_URL,
                data={"data": query},
                headers=_OVERPASS_HEADERS,
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                logger.warning(f"[OSM-VENUE] Overpass 429 for {context!r} "
                               f"(attempt {attempt + 1}/2)")
                if attempt == 0:
                    time.sleep(10)
                    continue
                return None
            else:
                logger.warning(f"[OSM-VENUE] Overpass HTTP {resp.status_code} "
                               f"for {context!r}")
                return None
        except (_http.exceptions.Timeout, _http.exceptions.ConnectionError) as e:
            logger.warning(f"[OSM-VENUE] Overpass {type(e).__name__} for "
                           f"{context!r} (attempt {attempt + 1}/2)")
            if attempt == 0:
                time.sleep(5)
                continue
            return None

    return None


def _build_overpass_query(stop_title: str, city: str, venue_hint: str = "") -> str:
    """Build an Overpass query for any venue type by name in a city.

    Searches across all relevant amenity/tourism/leisure/historic types.
    If venue_hint is provided, narrows the search to that category.
    """
    escaped_title = stop_title.replace('"', '\\"')

    # Build filter clauses for all venue types
    if venue_hint == "dining":
        filters = ['["amenity"~"restaurant|cafe|ice_cream|bar|fast_food"]']
    elif venue_hint == "museum":
        filters = [
            '["tourism"~"museum|gallery"]',
            '["amenity"~"museum|arts_centre"]',
        ]
    elif venue_hint == "park":
        filters = ['["leisure"~"park|garden"]']
    else:
        # Search all types
        filters = _OVERPASS_FILTERS

    # Build union of node/way/relation queries for each filter
    statements = []
    for filt in filters:
        statements.append(
            f'node["name"~"{escaped_title}",i]{filt}(area.searchArea);'
        )
        statements.append(
            f'way["name"~"{escaped_title}",i]{filt}(area.searchArea);'
        )
        statements.append(
            f'relation["name"~"{escaped_title}",i]{filt}(area.searchArea);'
        )

    union = "\n".join(statements)

    query = (
        f'[out:json][timeout:15];\n'
        f'area["name"="{city}"]["admin_level"="8"]["boundary"="administrative"]->.searchArea;\n'
        f'(\n{union}\n);\n'
        f'out tags;'
    )
    return query


# ---------------------------------------------------------------------------
# Fact extraction from OSM tags
# ---------------------------------------------------------------------------

def _extract_payment_info(tags: Dict[str, str]) -> str:
    """Extract payment information from OSM tags.

    OSM uses: payment:cash, payment:credit_cards, payment:debit_cards.
    Returns a listener-friendly summary, e.g. "Cash only" or empty string.
    """
    cash = tags.get("payment:cash", "")
    credit = tags.get("payment:credit_cards", "")
    debit = tags.get("payment:debit_cards", "")

    if cash == "yes" and credit == "no" and debit == "no":
        return "Cash only"
    elif cash == "no" and (credit == "yes" or debit == "yes"):
        return "Card payments only"
    elif credit == "yes" or debit == "yes":
        return ""
    elif cash == "yes" and credit == "" and debit == "":
        return ""
    return ""


def _extract_reservation(tags: Dict[str, str]) -> str:
    """Extract reservation info from OSM tags.

    OSM uses: reservation=yes/no/required/recommended
    Also checks booking:* tags for museum timed entry.
    """
    res = tags.get("reservation", "")
    if res == "required":
        return "Reservations required"
    elif res == "recommended":
        return "Reservations recommended"
    elif res == "yes":
        return "Reservations accepted"
    elif res == "no":
        return "No reservations"
    return ""


def _extract_fee(tags: Dict[str, str]) -> Tuple[str, str]:
    """Extract fee/admission info from OSM tags.

    Returns (fee_tag, fee_details) where:
      - fee_tag is 'yes', 'no', or '' (absent)
      - fee_details is human-readable pricing if available

    Sources for details:
      - charge tag (e.g. "8 EUR")
      - description:en tag (may contain pricing breakdown)

    NEVER infers pricing from venue type.
    """
    fee = tags.get("fee", "")

    # Look for explicit charge tag
    charge = tags.get("charge", "")
    fee_details = ""

    if charge:
        fee_details = charge

    # Check description:en for pricing info (common for French national museums)
    desc_en = tags.get("description:en", "")
    if desc_en and not fee_details:
        # Only extract if it contains explicit price patterns
        price_match = re.search(
            r'(?:Full rate|Admission|Entry|Tarif).*?[€$£]\s*\d+',
            desc_en, re.IGNORECASE
        )
        if price_match:
            fee_details = desc_en.strip()

    return fee, fee_details


def _extract_price_range(tags: Dict[str, str]) -> str:
    """Extract price range from OSM tags (dining)."""
    return tags.get("price_range", "")


def _derive_country_code(tags: Dict[str, str]) -> str:
    """Derive country code from OSM address tags."""
    return tags.get("addr:country", "").upper()


def _build_source_text(tags: Dict[str, str], osm_id: int, osm_type: str) -> str:
    """Build the source_text for gate verification.

    This is the raw tag dump that the practical facts gate verifies against.
    """
    lines = [f"OSM {osm_type} {osm_id} tags:"]
    for key, value in sorted(tags.items()):
        lines.append(f"  {key} = {value}")
    return "\n".join(lines)


def _score_element(element: dict) -> int:
    """Score an OSM element by how many practical facts it carries."""
    tags = element.get("tags", {})
    score = 0
    if tags.get("opening_hours"):
        score += 3
    if tags.get("fee"):
        score += 3
    if tags.get("charge"):
        score += 2
    if any(k.startswith("payment:") for k in tags):
        score += 2
    if tags.get("reservation"):
        score += 2
    if tags.get("price_range"):
        score += 3
    if tags.get("website"):
        score += 1
    if tags.get("description:en"):
        score += 1
    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_osm_venue_facts(
    stop_title: str,
    city: str,
    venue_hint: str = "",
) -> OsmVenueFacts:
    """Fetch sourceable practical facts from OpenStreetMap for any venue.

    Queries Overpass for the venue by name in the given city.
    Extracts opening_hours, fee, payment, reservation, etc. based on kind.

    Args:
        stop_title: Venue name (e.g. "Musée des Arts Asiatiques")
        city: City name (e.g. "Nice")
        venue_hint: Optional kind hint ('dining', 'museum', 'park')
                   to narrow the Overpass query.

    Returns:
        OsmVenueFacts with extracted facts and source provenance.
        If nothing found, returns empty OsmVenueFacts.
    """
    result = OsmVenueFacts(stop_title=stop_title)

    query = _build_overpass_query(stop_title, city, venue_hint)
    data = _overpass_request(query, context=stop_title)

    if not data or not data.get("elements"):
        logger.debug(f"[OSM-VENUE] No OSM result for {stop_title!r} in {city}")
        return result

    # Find the best matching element (most practical-fact tags)
    best_element = None
    best_score = -1

    for element in data["elements"]:
        score = _score_element(element)
        if score > best_score:
            best_score = score
            best_element = element

    if best_element is None:
        best_element = data["elements"][0]

    tags = best_element.get("tags", {})
    result.osm_id = best_element.get("id")
    result.osm_type = best_element.get("type", "node")
    result.tags = tags

    # Classify venue kind from actual tags
    result.venue_kind = classify_venue_kind(tags)

    # Extract universal facts
    result.opening_hours = tags.get("opening_hours", "")
    fee, fee_details = _extract_fee(tags)
    result.fee = fee
    result.fee_details = fee_details
    result.website = tags.get("website", "")

    # Extract kind-specific facts
    if result.venue_kind == "dining":
        result.payment_info = _extract_payment_info(tags)
        result.reservation = _extract_reservation(tags)
        result.price_range = _extract_price_range(tags)
        result.cuisine = tags.get("cuisine", "")
    elif result.venue_kind == "museum":
        result.reservation = _extract_reservation(tags)
        result.wheelchair = tags.get("wheelchair", "")
    else:
        # Parks, viewpoints, historic — check reservation (some gated parks)
        result.reservation = _extract_reservation(tags)

    result.country_code = _derive_country_code(tags)

    # Provenance
    result.source_url = (
        f"https://www.openstreetmap.org/{result.osm_type}/{result.osm_id}"
    )
    result.source_text = _build_source_text(tags, result.osm_id, result.osm_type)

    if not result.is_empty():
        print(f"  [LOCAL-355] OSM venue facts for {stop_title!r} "
              f"(kind={result.venue_kind}): "
              f"{result.format_practical_sentence()}")
    else:
        print(f"  [LOCAL-355] OSM found {stop_title!r} but no practical tags")

    return result


def fetch_osm_facts_for_stops(
    stops: List[Dict],
    city: str,
    venue_hint: str = "",
) -> Dict[str, OsmVenueFacts]:
    """Fetch OSM facts for multiple stops.

    Args:
        stops: List of stop dicts with at least 'name' key
        city: City name for the search area
        venue_hint: Optional category hint to narrow queries

    Returns:
        Dict mapping stop name → OsmVenueFacts
    """
    results = {}
    for stop in stops:
        name = stop.get("name", "")
        if not name:
            continue
        facts = fetch_osm_venue_facts(name, city, venue_hint)
        results[name] = facts
    return results


def extract_city_from_venue_name(venue_name: str) -> str:
    """Extract city name from venue_name string.

    Handles patterns like:
    - "restaurant tour in Old Nice (Vieux Nice), France"
    - "Musée Matisse, Nice, France"
    - "Nice, France"
    - "Nice walking area"

    Strategy: prefer a standalone city name in middle comma-parts over
    the first proper noun (which is often the venue name itself).
    """
    # Remove parentheticals
    cleaned = re.sub(r'\([^)]*\)', ' ', venue_name)

    # Noise words — covers dining AND museum/park tour phrasing
    _NOISE = {
        'france', 'italy', 'spain', 'usa', 'uk', 'the', 'tour',
        'restaurant', 'food', 'dining', 'culinary', 'old', 'new',
        'vieux', 'in', 'stop', 'stops', 'of', 'a', 'an',
        'museum', 'musée', 'musee', 'gallery', 'galerie',
        'park', 'parc', 'garden', 'jardin', 'walking', 'area',
        'historic', 'monument', 'castle', 'national', 'des', 'arts',
    }

    # Country names that are NOT cities
    _COUNTRIES = {
        'france', 'italy', 'spain', 'usa', 'uk', 'germany', 'monaco',
        'switzerland', 'belgium', 'netherlands',
    }

    # Split by comma
    parts = [p.strip() for p in cleaned.split(',')]

    # Strategy 1: if there are multiple comma-parts, prefer a middle part
    # that is a single proper noun (likely the city)
    if len(parts) >= 2:
        for part in parts[1:]:  # Skip first part (usually venue name)
            words = part.split()
            # Single-word proper nouns that aren't countries or noise
            candidates = [
                w for w in words
                if (len(w) >= 3 and
                    w[0].isupper() and
                    w.lower() not in _NOISE and
                    w.lower() not in _COUNTRIES)
            ]
            if candidates:
                return candidates[0]

    # Strategy 2: fall back to first proper noun in any part
    for part in parts:
        words = part.split()
        for word in words:
            clean_word = re.sub(r'[^a-zA-ZÀ-ÿ]', '', word)
            if (len(clean_word) >= 3 and
                    clean_word.lower() not in _NOISE and
                    clean_word.lower() not in _COUNTRIES and
                    clean_word[0].isupper()):
                return clean_word

    return ""


# ---------------------------------------------------------------------------
# Backward-compatible re-exports for LOCAL-353 callers
# ---------------------------------------------------------------------------

# These aliases let existing code that imports from osm_dining_facts
# work unchanged if it's redirected here.
OsmDiningFacts = OsmVenueFacts
fetch_osm_dining_facts = fetch_osm_venue_facts
