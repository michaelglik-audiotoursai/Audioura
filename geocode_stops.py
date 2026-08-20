"""
Validate and correct stop coordinates against a real geocoder.

WHY THIS EXISTS
Stop coordinates were produced entirely by a language model recalling latitude
and longitude from memory — coordinates_fromAI/app.py asks gpt-3.5-turbo for
them, and the tour-text model emits a "Coordinates:" line per stop. Nothing ever
checked the answers, and a hallucinated coordinate is indistinguishable from a
correct one downstream: tour_map_screen.dart plots whatever number it is given.

Yury Makedonov reported the consequence on 2026-08-16 (BETA-4, wdvrdaxqjn):

    "Location of #6 is wrong. It's over Central Islands. ... You may lose a
     couple of hours if you follow these directions - you need to take a ferry
     ride to Central Islands"

Measured against the live service on 2026-08-20, asking for real Toronto places:

    Leslie Spit parking, Toronto           ~2.2 km from the real position
    Crothers Woods, Toronto                ~1.0 km
    Tommy Thompson Park entrance, Toronto  ~2.4 km

The clearest proof is internal: "Leslie Spit parking" and "Tommy Thompson Park
entrance" are the SAME PLACE, and the model placed them ~1.3 km apart. A
geocoder cannot be self-inconsistent like that. The model is guessing.

APPROACH
Every stop already carries a name and an "Address:" line. Those are text, which
is what geocoders are for. We look the stop up in Nominatim (OpenStreetMap) —
the same data source the app already renders tiles from — and:

  * replace the model's coordinate when the geocoder disagrees materially,
  * keep the model's coordinate when they broadly agree,
  * flag a coordinate that is implausibly far from the tour itself when the
    geocoder cannot help.

FAIL-SOFT BY DESIGN
A geocoder outage must never break tour generation. Every failure path falls
back to the model's coordinate and records why. The one thing that is never
silently accepted is a coordinate that is absurdly far from the tour, because
that is the Central Islands case and it is the one that wastes a person's day.

Nominatim is free and needs no API key, but its usage policy requires an
identifying User-Agent and at most one request per second. Both are enforced
here. Tour generation is low volume, so this stays well inside the policy.
"""
import os
import re
import math
import time
import json
import logging
import urllib.parse
import urllib.request

# --- configuration -----------------------------------------------------------

GEOCODE_ENABLED = os.getenv("GEOCODE_STOPS", "1") not in ("0", "false", "False")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")

# Nominatim's policy requires a real contact point. Override per deployment.
USER_AGENT = os.getenv("GEOCODE_USER_AGENT", "Audioura/1.0 (audio tour generator; info@audioura.com)")

# Nominatim allows at most 1 request/second.
_MIN_INTERVAL_S = float(os.getenv("GEOCODE_MIN_INTERVAL", "1.1"))

# Disagreement beyond this and we trust the geocoder over the model. 150 m is
# wider than ordinary geocoder imprecision (a car park centroid vs its entrance)
# but far below the 1-2 km errors measured above.
REPLACE_THRESHOLD_M = float(os.getenv("GEOCODE_REPLACE_THRESHOLD_M", "150"))

# A stop further than this from the tour's own location is not a near-miss, it
# is a different place. Leslie Spit -> Central Islands would be caught here.
MAX_TOUR_RADIUS_KM = float(os.getenv("GEOCODE_MAX_RADIUS_KM", "50"))

_HTTP_TIMEOUT_S = float(os.getenv("GEOCODE_TIMEOUT", "10"))

_COORD_RE = re.compile(r'^(Coordinates:\s*)([-\d.]+)\s*,\s*([-\d.]+)\s*$', re.IGNORECASE | re.MULTILINE)
_ADDRESS_RE = re.compile(r'^Address:\s*(.+)$', re.IGNORECASE | re.MULTILINE)

_last_request_at = 0.0


def haversine_m(a, b):
    """Great-circle distance in metres between (lat, lng) pairs."""
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def geocode(query):
    """Resolve a free-text place to (lat, lng), or None.

    Returns None on any failure — no network, rate limited, no match, malformed
    response. Callers must treat None as "no opinion", never as an error.
    """
    global _last_request_at
    if not query or not query.strip():
        return None

    # Respect Nominatim's 1 req/sec policy.
    elapsed = time.time() - _last_request_at
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)

    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
            payload = json.load(resp)
        _last_request_at = time.time()
        if not payload:
            return None
        return float(payload[0]["lat"]), float(payload[0]["lon"])
    except Exception as e:
        _last_request_at = time.time()
        logging.warning("[GEOCODE] lookup failed for %r: %s", query, e)
        return None


def _parse_stop(stop_text):
    """Extract (name, address, (lat, lng)) from a stop's text. Any may be None."""
    lines = [l.strip() for l in stop_text.split("\n") if l.strip()]
    name = lines[0] if lines else None

    addr_m = _ADDRESS_RE.search(stop_text)
    address = addr_m.group(1).strip() if addr_m else None

    coord_m = _COORD_RE.search(stop_text)
    coords = None
    if coord_m:
        try:
            coords = (float(coord_m.group(2)), float(coord_m.group(3)))
        except ValueError:
            coords = None
    return name, address, coords


def _queries_for(name, address, tour_location):
    """Lookup strings, most specific first. Duplicates removed, order kept.

    The stop NAME is always the target; the address is only ever a qualifier.

    Never fall back to the address alone. Doing so caused a 16.8 km error in
    testing: "Leslie Spit parking, Leslie St, Toronto, ON" has no Nominatim
    match, the chain fell through to "Leslie St, Toronto, ON", and that matched
    Leslie *Street* — a long road running far north of the actual spit. The
    result was worse than the model's guess it was meant to correct. A street
    match is a plausible-looking point for the wrong place, which is precisely
    the failure mode this module exists to prevent.
    """
    out = []
    for q in (
        f"{name}, {tour_location}" if name and tour_location else None,
        f"{name}, {address}" if name and address else None,
        name,
    ):
        if q and q not in out:
            out.append(q)
    return out


_TOUR_PREFIX_RE = re.compile(
    r'^\s*(a\s+)?'
    r'((self[- ]guided|walking|driving|biking|cycling|museum|audio|guided)\s+)*tour\s+'
    r'(of|around|in|through|near|along)?\s*',
    re.IGNORECASE)

_TOUR_SUFFIX_RE = re.compile(
    r'\s*[-–—:]?\s*\b('
    r'(self[- ]guided\s+)?(walking|driving|biking|cycling|museum|audio|guided|food|restaurant|specialized)\s+tour'
    r'|audio\s+guided\s+tour|tour)\b\s*$',
    re.IGNORECASE)


def location_hint(tour_name):
    """Reduce a tour title to the place it is about.

    "Boston Common walking tour" -> "Boston Common". Used to qualify stop
    lookups; passing the full title would produce queries like
    "Frog Pond, Boston Common walking tour", which geocodes to nothing.
    """
    if not tour_name:
        return ""
    hint = tour_name.strip()
    # Strip repeatedly: "… museum tour" can follow "… walking tour" in titles.
    for _ in range(3):
        stripped = _TOUR_PREFIX_RE.sub("", hint)
        stripped = _TOUR_SUFFIX_RE.sub("", stripped).strip(" ,-–—:")
        if stripped == hint:
            break
        hint = stripped
    return hint


def correct_stop(stop_text, tour_location, tour_anchor=None):
    """Validate one stop's coordinates, returning (new_text, record).

    tour_anchor is a (lat, lng) for the tour as a whole, used only for the
    plausibility check. Pass None to skip that check.

    The text is returned unchanged unless we have positive reason to change it.
    """
    name, address, llm_coords = _parse_stop(stop_text)
    record = {
        "stop": name, "address": address,
        "llm": llm_coords, "geocoded": None,
        "action": "kept", "reason": "", "distance_m": None,
    }

    if llm_coords is None:
        record.update(action="skipped", reason="stop has no Coordinates line")
        return stop_text, record

    if not GEOCODE_ENABLED:
        record.update(action="kept", reason="geocoding disabled")
        return stop_text, record

    found = None
    for q in _queries_for(name, address, tour_location):
        found = geocode(q)
        if found:
            record["query"] = q
            break
    # The geocoder is not automatically trustworthy either. If it returns a
    # point that is nowhere near the tour, it has matched something unrelated
    # that merely shares a name — discard it rather than "correct" a coordinate
    # into a worse one.
    if found is not None and tour_anchor:
        anchor_km = haversine_m(found, tour_anchor) / 1000.0
        if anchor_km > MAX_TOUR_RADIUS_KM:
            logging.warning("[GEOCODE] discarding match for %r: %.1f km from the tour",
                            name, anchor_km)
            record["rejected_geocode"] = {"coords": found, "km_from_tour": round(anchor_km, 1)}
            found = None

    record["geocoded"] = found

    if found is None:
        # No external opinion. Fall back to a plausibility check: is the model's
        # coordinate even in the right part of the world?
        if tour_anchor:
            d_km = haversine_m(llm_coords, tour_anchor) / 1000.0
            record["distance_m"] = round(d_km * 1000)
            if d_km > MAX_TOUR_RADIUS_KM:
                record.update(
                    action="flagged",
                    reason=f"{d_km:.1f} km from the tour location and not geocodable",
                )
                return stop_text, record
        record.update(action="kept", reason="no geocoder match; coordinate is plausible")
        return stop_text, record

    distance = haversine_m(llm_coords, found)
    record["distance_m"] = round(distance)

    if distance <= REPLACE_THRESHOLD_M:
        record.update(action="kept", reason=f"geocoder agrees within {distance:.0f} m")
        return stop_text, record

    new_text = _COORD_RE.sub(
        lambda m: f"{m.group(1)}{found[0]:.6f}, {found[1]:.6f}", stop_text, count=1)
    record.update(action="replaced", reason=f"geocoder disagreed by {distance:.0f} m")
    return new_text, record


def correct_stops(text_content, tour_location, tour_anchor=None):
    """Validate every stop. Returns (new_text_content, records).

    Never raises: a geocoding problem must not fail tour generation.
    """
    new_content, records = [], []
    for stop_text in text_content:
        try:
            fixed, record = correct_stop(stop_text, tour_location, tour_anchor)
        except Exception as e:                      # pragma: no cover - defensive
            logging.warning("[GEOCODE] stop validation errored, keeping original: %s", e)
            fixed, record = stop_text, {"action": "error", "reason": str(e)}
        new_content.append(fixed)
        records.append(record)

    replaced = sum(1 for r in records if r["action"] == "replaced")
    flagged = sum(1 for r in records if r["action"] == "flagged")
    logging.info("[GEOCODE] %d stops: %d replaced, %d flagged", len(records), replaced, flagged)
    for r in records:
        if r["action"] in ("replaced", "flagged"):
            logging.info("[GEOCODE]   %s: %s -> %s (%s)",
                         r.get("stop"), r.get("llm"), r.get("geocoded"), r["reason"])
    return new_content, records
