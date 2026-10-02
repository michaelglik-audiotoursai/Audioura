"""osm_dining_facts.py — LOCAL-353: Source price/reservation/payment facts from OSM.

Queries OpenStreetMap (Overpass API) for dining stops to extract sourceable
operational facts: opening_hours, payment methods, reservation, price_range.

Design principle: SAME AS PRACTICAL FACTS GATE — only source what OSM says.
If a tag is absent, say nothing. Never infer a price band from cuisine type.

Returns:
  - formatted operational_details string (what the listener hears)
  - source_text (the raw OSM tag dump, for gate verification)
  - source_url (Overpass permalink for auditability)

Currency: derived from the venue's country via addr:country or the Overpass
area's country code. Never assumed.
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
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OsmDiningFacts:
    """Extracted dining facts from OSM for one stop."""
    stop_title: str
    osm_id: Optional[int] = None
    osm_type: Optional[str] = None  # 'node', 'way', 'relation'
    tags: Dict[str, str] = field(default_factory=dict)

    # Parsed facts
    opening_hours: str = ""
    payment_info: str = ""       # e.g. "Cash only" or "Credit cards accepted"
    reservation: str = ""        # e.g. "Reservations required" or "Reservations recommended"
    price_range: str = ""        # e.g. "€€" or OSM price_range tag
    cuisine: str = ""
    country_code: str = ""       # For currency derivation

    # Gate integration
    source_url: str = ""         # Overpass query URL
    source_text: str = ""        # Raw tag dump for gate verification

    def format_operational_details(self) -> str:
        """Format facts into a human-readable operational details string.

        Only includes facts that are present in OSM. Never invents.
        """
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

    def _humanize_hours(self, raw: str) -> str:
        """Convert OSM opening_hours to a listener-friendly sentence.

        Only light reformatting — the raw OSM value is already terse.
        If the format is too complex, pass it through as-is.
        """
        # Simple patterns: "Mo-Fr 12:00-14:00, 19:00-22:00"
        # Don't over-parse; the gate needs to verify against source
        raw = raw.strip()
        if not raw:
            return ""

        # Replace semicolons with commas for readability
        formatted = raw.replace(";", ",")

        # Check for "off" days
        off_match = re.search(r'(Sa|Su|Mo|Tu|We|Th|Fr)(?:-(Sa|Su|Mo|Tu|We|Th|Fr))?\s+off',
                              formatted, re.IGNORECASE)
        if off_match:
            # Convert day abbreviations to full names for the listener
            formatted = self._expand_days(formatted)

        return f"Open {formatted}" if not formatted.lower().startswith("open") else formatted

    def _expand_days(self, text: str) -> str:
        """Expand OSM day abbreviations to full names."""
        _DAY_MAP = {
            'Mo': 'Monday', 'Tu': 'Tuesday', 'We': 'Wednesday',
            'Th': 'Thursday', 'Fr': 'Friday', 'Sa': 'Saturday', 'Su': 'Sunday',
        }
        result = text
        for abbr, full in _DAY_MAP.items():
            # Only replace standalone abbreviations (word boundaries)
            result = re.sub(rf'\b{abbr}\b', full, result)
        return result

    def is_empty(self) -> bool:
        """True if no sourceable facts were found."""
        return not any([self.opening_hours, self.payment_info,
                        self.reservation, self.price_range])


# ---------------------------------------------------------------------------
# Overpass query
# ---------------------------------------------------------------------------

def _overpass_request(query: str, context: str = "") -> Optional[dict]:
    """Make a rate-limited Overpass API request.

    Returns parsed JSON or None on failure.
    Raises RuntimeError on persistent failure (for gate to classify as unknown).
    """
    import requests as _http

    global _overpass_last_request_time

    # Serialise and enforce minimum interval
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
                logger.warning(f"[OSM-DINING] Overpass 429 for {context!r} "
                               f"(attempt {attempt + 1}/2)")
                if attempt == 0:
                    time.sleep(10)
                    continue
                return None
            else:
                logger.warning(f"[OSM-DINING] Overpass HTTP {resp.status_code} "
                               f"for {context!r}")
                return None
        except (_http.exceptions.Timeout, _http.exceptions.ConnectionError) as e:
            logger.warning(f"[OSM-DINING] Overpass {type(e).__name__} for "
                           f"{context!r} (attempt {attempt + 1}/2)")
            if attempt == 0:
                time.sleep(5)
                continue
            return None

    return None


def _build_overpass_query(stop_title: str, city: str) -> str:
    """Build an Overpass query for a restaurant by name in a city.

    Searches for amenity=restaurant|cafe|ice_cream|bar with name matching.
    Returns all tags for matched elements.
    """
    # Escape quotes in stop_title for Overpass QL
    escaped_title = stop_title.replace('"', '\\"')
    # Simple regex: case-insensitive match
    # Use area search for the city
    query = (
        f'[out:json][timeout:15];'
        f'area["name"="{city}"]["admin_level"="8"]["boundary"="administrative"]->.searchArea;'
        f'('
        f'node["name"~"{escaped_title}",i]["amenity"~"restaurant|cafe|ice_cream|bar|fast_food"](area.searchArea);'
        f'way["name"~"{escaped_title}",i]["amenity"~"restaurant|cafe|ice_cream|bar|fast_food"](area.searchArea);'
        f');'
        f'out tags;'
    )
    return query


# ---------------------------------------------------------------------------
# Fact extraction from OSM tags
# ---------------------------------------------------------------------------

def _extract_payment_info(tags: Dict[str, str]) -> str:
    """Extract payment information from OSM tags.

    OSM uses: payment:cash, payment:credit_cards, payment:debit_cards,
    payment:contactless, etc.

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
        # Cards accepted but cash also fine — not notable enough to mention
        return ""
    elif cash == "yes" and credit == "" and debit == "":
        # Only cash tag present, no card info — not enough to assert "cash only"
        return ""

    return ""


def _extract_reservation(tags: Dict[str, str]) -> str:
    """Extract reservation info from OSM tags.

    OSM uses: reservation=yes/no/required/recommended
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


def _extract_price_range(tags: Dict[str, str]) -> str:
    """Extract price range from OSM tags.

    OSM uses: price_range (free text, often €€ or $$$)
    """
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_osm_dining_facts(
    stop_title: str,
    city: str,
) -> OsmDiningFacts:
    """Fetch sourceable dining facts from OpenStreetMap for a restaurant.

    Queries Overpass for the restaurant by name in the given city.
    Extracts opening_hours, payment info, reservation, and price_range.

    Args:
        stop_title: Restaurant name (e.g. "La Merenda")
        city: City name (e.g. "Nice")

    Returns:
        OsmDiningFacts with extracted facts and source provenance.
        If nothing found, returns empty OsmDiningFacts.
    """
    result = OsmDiningFacts(stop_title=stop_title)

    query = _build_overpass_query(stop_title, city)
    data = _overpass_request(query, context=stop_title)

    if not data or not data.get("elements"):
        logger.debug(f"[OSM-DINING] No OSM result for {stop_title!r} in {city}")
        return result

    # Find the best matching element (prefer one with most relevant tags)
    best_element = None
    best_score = -1

    for element in data["elements"]:
        tags = element.get("tags", {})
        score = 0
        if tags.get("opening_hours"):
            score += 3
        if any(k.startswith("payment:") for k in tags):
            score += 2
        if tags.get("reservation"):
            score += 2
        if tags.get("price_range"):
            score += 3
        if score > best_score:
            best_score = score
            best_element = element

    if best_element is None:
        # Elements exist but have no useful tags — still record the OSM match
        best_element = data["elements"][0]

    tags = best_element.get("tags", {})
    result.osm_id = best_element.get("id")
    result.osm_type = best_element.get("type", "node")
    result.tags = tags

    # Extract facts
    result.opening_hours = tags.get("opening_hours", "")
    result.payment_info = _extract_payment_info(tags)
    result.reservation = _extract_reservation(tags)
    result.price_range = _extract_price_range(tags)
    result.cuisine = tags.get("cuisine", "")
    result.country_code = _derive_country_code(tags)

    # Provenance
    result.source_url = (
        f"https://www.openstreetmap.org/{result.osm_type}/{result.osm_id}"
    )
    result.source_text = _build_source_text(tags, result.osm_id, result.osm_type)

    if not result.is_empty():
        print(f"  [LOCAL-353] OSM dining facts for {stop_title!r}: "
              f"{result.format_operational_details()}")
    else:
        print(f"  [LOCAL-353] OSM found {stop_title!r} but no price/hours/payment/reservation tags")

    return result


def fetch_osm_facts_for_stops(
    stops: List[Dict],
    city: str,
) -> Dict[str, OsmDiningFacts]:
    """Fetch OSM dining facts for multiple stops.

    Args:
        stops: List of stop dicts with at least 'name' key
        city: City name for the search area

    Returns:
        Dict mapping stop name → OsmDiningFacts
    """
    results = {}
    for stop in stops:
        name = stop.get("name", "")
        if not name:
            continue
        facts = fetch_osm_dining_facts(name, city)
        results[name] = facts
    return results


def extract_city_from_venue_name(venue_name: str) -> str:
    """Extract city name from venue_name string.

    Handles patterns like:
    - "restaurant tour in Old Nice (Vieux Nice), France"
    - "Old Nice, Nice, France"
    - "Nice, France"

    Returns the most likely city name.
    """
    # Remove parentheticals
    cleaned = re.sub(r'\([^)]*\)', ' ', venue_name)

    # Remove noise words
    _NOISE = {
        'france', 'italy', 'spain', 'usa', 'uk', 'the', 'tour',
        'restaurant', 'food', 'dining', 'culinary', 'old', 'new',
        'vieux', 'in', 'stop', 'stops', 'of', 'a', 'an',
    }

    # Split by comma — city is usually the first proper noun
    parts = [p.strip() for p in cleaned.split(',')]

    for part in parts:
        words = part.split()
        for word in words:
            clean_word = re.sub(r'[^a-zA-ZÀ-ÿ]', '', word)
            if (len(clean_word) >= 3 and
                    clean_word.lower() not in _NOISE and
                    clean_word[0].isupper()):
                return clean_word

    return ""
