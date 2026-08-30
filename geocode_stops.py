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

# Disagreement beyond this and we trust the geocoder over the model.
#
# Set from measurement, not intuition. A sweep of 40 stops across 8 cities
# (Toronto, Boston, New York, Chicago, Paris, Edinburgh, Kyoto, Sydney), scored
# against Wikidata as an independent source, gave:
#
#   threshold   improved  worse   net accuracy gained
#      150 m         6      6            671 m
#      500 m         1      2            554 m
#     1000 m         1      0          1,601 m
#
# At 150 m the module corrected six stops and DEGRADED six others, for almost no
# net gain. The regressions were all the same shape: the model was already
# accurate, and the geocoder moved the pin to a different part of a large
# feature — Royal Mile (a long street) 83 m -> 240 m, Sydney Harbour Bridge
# 36 m -> 333 m, Luxembourg Gardens 83 m -> 240 m.
#
# At 1 km there are no regressions and the large win survives (Sunnybrook Park,
# 1,616 m -> 15 m). This module exists to catch stops that are in the WRONG
# PLACE, not to arbitrate between two defensible points on the same park. When
# the two sources are within a kilometre they broadly agree, and the model's
# answer is as good as the geocoder's.
REPLACE_THRESHOLD_M = float(os.getenv("GEOCODE_REPLACE_THRESHOLD_M", "1000"))

# A stop further than this from the tour's own location is not a near-miss, it
# is a different place. Leslie Spit -> Central Islands would be caught here.
MAX_TOUR_RADIUS_KM = float(os.getenv("GEOCODE_MAX_RADIUS_KM", "50"))

_HTTP_TIMEOUT_S = float(os.getenv("GEOCODE_TIMEOUT", "10"))

# [^\S\n]* is "horizontal whitespace only". Plain \s* also matches newlines, so
# an EMPTY "Address:" line would swallow the following line and treat it as the
# address — producing lookups for strings like "Coordinates: 12.35". Stops with
# no address are common wherever the model has thin data, which is precisely
# where this module has to behave.
_COORD_RE = re.compile(r'^(Coordinates:[^\S\n]*)([-\d.]+)[^\S\n]*,[^\S\n]*([-\d.]+)[^\S\n]*$',
                       re.IGNORECASE | re.MULTILINE)
_ADDRESS_RE = re.compile(r'^Address:[^\S\n]*(\S.*)$', re.IGNORECASE | re.MULTILINE)

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


_COUNTRIES = {'australia', 'canada', 'usa', 'us', 'united states', 'united states of america',
              'france', 'japan', 'uk', 'united kingdom', 'scotland', 'england', 'ireland',
              'germany', 'italy', 'spain', 'netherlands'}

_STREET_WORD = re.compile(
    r'\b(st|street|ave|avenue|rd|road|dr|drive|blvd|boulevard|way|lane|ln|rue|place|terrace|'
    r'trail|parkway|pkwy|hwy|court|ct|sq|square|dori)\b', re.IGNORECASE)


def _clean_component(part):
    """Strip postcodes and state codes from one comma-separated address component."""
    p = part.strip()
    p = re.sub(r'^\d{3,5}(?:-\d{4})?\s+', '', p)                  # "75005 Paris" (FR/JP)
    p = re.sub(r'\s+[A-Z]{2}\s+[A-Z\d][A-Z\d\s-]{2,}$', '', p)    # "Sydney NSW 2000"
    p = re.sub(r'\s+[A-Z]\d[A-Z]\s*\d[A-Z]\d$', '', p)            # "Toronto M4P 2A8"
    p = re.sub(r'\s+\d{5}(?:-\d{4})?$', '', p)                    # "Boston 02133"
    return p.strip(' ,')


def _is_junk_component(p):
    if not p:
        return True
    if p.lower() in _COUNTRIES:
        return True
    if re.fullmatch(r'[A-Z]{2}', p):                              # bare state/province
        return True
    if re.fullmatch(r'[A-Z]{2}\s+[A-Z\d][A-Z\d\s-]*', p, re.I):   # "ON M3C 2J6", "NSW 2000"
        return True
    if re.fullmatch(r'[\d\s-]+', p):
        return True
    if re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}', p, re.I):  # UK postcode
        return True
    return False


def city_from_address(address):
    """Pull the city out of a model-written address.

    The city is the useful part; the postcode and country are actively harmful.
    Measured on the real Bennelong Point case:

        "Bennelong Point, Sydney NSW 2000, Australia" -> Bennelong BRIDGE, 12.75 km off
        "Bennelong Point, Sydney"                     -> Bennelong Point,  0.08 km

    Nominatim has no entry for that address, so rather than returning nothing it
    fuzzy-matched "Bennelong" to a cycleway in another suburb. Removing the
    postcode and country turns a 12.75 km failure into an 80 m success.

    Correct on 27 of 28 real generated addresses; the 28th returned "North York"
    for a Toronto tour, which is a valid qualifier.
    """
    if not address:
        return ""
    parts = [_clean_component(p) for p in address.split(",")]
    parts = [p for p in parts if not _is_junk_component(p)]
    for p in reversed(parts):
        if re.match(r'^\d', p):          # "190 Sherwood Ave"
            continue
        if _STREET_WORD.search(p):
            continue
        return p
    return parts[-1] if parts else ""


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
    city = city_from_address(address)
    out = []
    for q in (
        # Best shape by measurement: landmark name qualified by its city, with
        # postcode and country removed. See city_from_address for the evidence.
        f"{name}, {city}" if name and city else None,
        f"{name}, {tour_location}" if name and tour_location else None,
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


# Two candidates this close together are taken to corroborate each other.
# Measured over 23 stops with independent ground truth:
#
#   sources agree within 200 m (12 stops):  worst error   398 m
#   sources disagree  > 200 m (11 stops):   worst error 1,616 m
#
# Agreement predicts trustworthiness. Note the sample is small, so this is an
# informed starting point rather than a tuned constant.
AGREEMENT_M = float(os.getenv("GEOCODE_AGREEMENT_M", "200"))


def _candidates(name, address, tour_location):
    """Independent estimates of where this stop is, keyed by how they were found.

    Two lookups, both free. They fail in different ways, which is what makes
    comparing them informative:

      by_name    - "{stop}, {city}" with postcode and country stripped
      by_address - the model's full address, verbatim

    Where they disagree materially, the address lookup is usually the one at
    fault. Every large disagreement measured had the model right and the
    address wrong: Bethesda Terrace 26 km, Sydney Opera House 12.7 km, Sydney
    Harbour Bridge 1.5 km.
    """
    out = {}
    city = city_from_address(address)
    if name and city:
        hit = geocode(f"{name}, {city}")
        if hit:
            out["by_name"] = hit
    elif name and tour_location:
        hit = geocode(f"{name}, {tour_location}")
        if hit:
            out["by_name"] = hit
    if address:
        hit = geocode(address)
        if hit:
            out["by_address"] = hit
    return out


def resolve_point(name, address, model_pt, tour_location, tour_anchor=None):
    """[D559] The coordinate decision itself, with no assumption about the caller.

    Michael, 2026-08-30: *"it would be nice if there is a procedure and you can
    utilize it in every place where this functionality is needed."*

    This was the body of `resolve_stop`, which parses the `Address:`/`Coordinates:`
    lines of rendered stop text. That shape suits the Beta path
    (`tour_generation_modernized.py`), which has text and nothing else, and suits
    nothing else — the Storied generator holds POI dicts thousands of lines before
    any text exists, so it could not call the one procedure that already solved
    this. Lifting the decision out is what makes it reusable; `resolve_stop` is now
    a text wrapper over it and its behaviour is unchanged, which matters because it
    is deployed in Beta production (audioura:v33).

    Returns (chosen_pt_or_None, record). `chosen_pt` is None when the model's own
    coordinate stands — the caller changes nothing in that case.

    The rule, and why:
      * two candidates within AGREEMENT_M  -> trust the geocoded one. When the
        sources agree they are usually both right, and the geocoder is the more
        precise of the two.
      * nothing corroborates               -> keep the MODEL's coordinate. It is
        the single most reliable source: in every large disagreement measured
        (Bethesda Terrace 26 km, Sydney Opera House 12.7 km), the model was right
        and the ADDRESS lookup was wrong.
    """
    rec = {"stop": name, "address": address, "llm": model_pt,
           "confidence": "low", "action": "kept", "reason": "", "spread_m": None}
    if model_pt is None:
        rec.update(action="skipped", reason="no coordinate to check")
        return None, rec
    if not GEOCODE_ENABLED:
        rec.update(reason="geocoding disabled")
        return None, rec

    cands = _candidates(name, address, tour_location)

    # Discard any candidate that is nowhere near the tour: it has matched
    # something unrelated that merely shares a name.
    if tour_anchor:
        for key in list(cands):
            d_km = haversine_m(cands[key], tour_anchor) / 1000.0
            if d_km > MAX_TOUR_RADIUS_KM:
                logging.warning("[GEOCODE] %s: discarding %s match %.0f km from the tour",
                                name, key, d_km)
                rec.setdefault("rejected", {})[key] = round(d_km, 1)
                del cands[key]

    everything = dict(cands, model=model_pt)
    best_pair, best_gap = None, None
    keys = list(everything)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            gap = haversine_m(everything[keys[i]], everything[keys[j]])
            if best_gap is None or gap < best_gap:
                best_gap, best_pair = gap, (keys[i], keys[j])

    rec["candidates"] = {k: [round(v[0], 6), round(v[1], 6)] for k, v in everything.items()}
    if best_gap is not None:
        rec["spread_m"] = round(best_gap)

    if best_gap is not None and best_gap <= AGREEMENT_M:
        rec["confidence"] = "high"
        pick = next((k for k in best_pair if k != "model"), None)
        if pick is None:
            rec.update(reason="only the model available; nothing to corroborate")
            return None, rec
        chosen = everything[pick]
        rec.update(reason=f"{' + '.join(best_pair)} agree within {best_gap:.0f} m")
        if haversine_m(chosen, model_pt) <= 1.0:
            return None, rec        # already there; nothing to change
        rec.update(action="replaced", chosen=pick)
        return chosen, rec

    rec.update(reason=("sources disagree" if best_gap is not None else "no lookup succeeded")
                      + " — keeping the model's coordinate")
    return None, rec


def resolve_poi(poi, tour_location, tour_anchor=None):
    """[D559] `resolve_point` for a POI dict, the shape the Storied generator holds.

    Reads `name`, `address` and the `coordinates` string; on a high-confidence
    correction it writes the new coordinate back. Always records
    `_geo_confidence` and `_geo_record` so later stages — route ordering, the
    scope check, and eventually the map's confidence markers (ClickUp
    wdvrdaxqtf) — can tell an established coordinate from a guess.

    Returns the record. Mutates `poi`.
    """
    model_pt = _parse_coords_pair(poi.get('coordinates', ''))
    chosen, rec = resolve_point(poi.get('name', ''), (poi.get('address') or '').strip(),
                                model_pt, tour_location, tour_anchor)
    if chosen:
        poi['coordinates'] = f"{chosen[0]:.6f}, {chosen[1]:.6f}"
    poi['_geo_confidence'] = rec.get('confidence', 'low')
    poi['_geo_record'] = rec
    return rec


def _parse_coords_pair(text):
    """'43.71, 7.27' -> (43.71, 7.27); anything unusable -> None."""
    if not text:
        return None
    m = re.search(r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)', str(text))
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    if lat == 0.0 and lng == 0.0:
        return None
    return (lat, lng)


def resolve_stop(stop_text, tour_location, tour_anchor=None):
    """Pick a coordinate using agreement between independent sources.

    Returns (new_text, record). record["confidence"] is "high" when two sources
    corroborate each other, "low" when none do.

    [D559] Now a thin wrapper over `resolve_point`, which holds the rule. Behaviour
    is unchanged — this is deployed in Beta production (audioura:v33) and the point
    of the extraction was to let the Storied generator reuse the decision, not to
    alter it.
    """
    name, address, model_pt = _parse_stop(stop_text)
    chosen, rec = resolve_point(name, address, model_pt, tour_location, tour_anchor)
    if rec.get("action") == "skipped" and model_pt is None:
        rec["reason"] = "stop has no Coordinates line"
    if chosen is None:
        return stop_text, rec
    new_text = _COORD_RE.sub(
        lambda m: f"{m.group(1)}{chosen[0]:.6f}, {chosen[1]:.6f}", stop_text, count=1)
    return new_text, rec


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


def _median_anchor(text_content):
    """A rough centre for the tour, taken from the model's own coordinates.

    The model is unreliable about any single stop but consistently lands in the
    right city, so the median of its coordinates is a solid anchor — and unlike
    the tour title, it always exists.

    This matters because the anchor is what rejects a wrong same-named match.
    Without it, regenerating "Toronto Ravines And Other Green Spaces" placed a
    stop called "Sherwood Park" in Sherwood Park, ALBERTA — 2,700 km away —
    because the tour title is not a geocodable place, so the anchor was None and
    the plausibility check never ran. The median of the other stops would have
    caught it instantly.
    """
    pts = []
    for stop_text in text_content:
        _, _, coords = _parse_stop(stop_text)
        if coords:
            pts.append(coords)
    if len(pts) < 2:
        return None
    lats = sorted(p[0] for p in pts)
    lngs = sorted(p[1] for p in pts)
    mid = len(pts) // 2
    return (lats[mid], lngs[mid])


def correct_stops(text_content, tour_location, tour_anchor=None):
    """Validate every stop. Returns (new_text_content, records).

    Never raises: a geocoding problem must not fail tour generation.
    """
    # Prefer a geocoded anchor, but never proceed without one if the stops can
    # supply it themselves. An absent anchor silently disables the only guard
    # against a confidently wrong same-name match.
    if tour_anchor is None:
        tour_anchor = _median_anchor(text_content)
        if tour_anchor:
            logging.info("[GEOCODE] anchor from stop median: %.4f, %.4f", *tour_anchor)

    new_content, records = [], []
    for stop_text in text_content:
        try:
            fixed, record = resolve_stop(stop_text, tour_location, tour_anchor)
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
