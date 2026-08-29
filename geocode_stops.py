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
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# --- configuration -----------------------------------------------------------

GEOCODE_ENABLED = os.getenv("GEOCODE_STOPS", "1") not in ("0", "false", "False")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")

# Nominatim's policy requires a real contact point. Override per deployment.
USER_AGENT = os.getenv("GEOCODE_USER_AGENT", "Audioura/1.0 (audio tour generator; info@audioura.com)")

# Nominatim allows at most 1 request/second.
# Nominatim's free tier permits 1 request/second. Set to 0 to remove the wait
# entirely -- that is the single knob to turn on the day a paid geocoder or a
# self-hosted instance removes the limit. No rebuild and no code change: it is
# read from the environment, so `gcloud run services update --set-env-vars
# GEOCODE_MIN_INTERVAL=0` is the whole migration for this half.
#
# NOTE, so the expectation is right: setting this to 0 alone makes tours only
# modestly faster, because lookups still run one after another. The remaining
# win needs them to overlap -- see GEOCODE_MAX_PARALLEL below.
_MIN_INTERVAL_S = float(os.getenv("GEOCODE_MIN_INTERVAL", "1.1"))

# How many stops may be resolved concurrently. 1 keeps today's strictly
# sequential behaviour, which is what the free tier requires. Raising it is the
# other half of the paid-geocoder migration, and it is what actually makes tour
# generation faster: a 10-stop tour issues roughly 32 lookups, so at 1.1s apart
# it spends about 35 seconds waiting. Both knobs are read here so that day is a
# configuration change rather than a project.
_MAX_PARALLEL = max(1, int(os.getenv("GEOCODE_MAX_PARALLEL", "1")))

# A 429 means we asked too fast, not that the place is unknown. Retry once.
_MAX_ATTEMPTS = max(1, int(os.getenv("GEOCODE_MAX_ATTEMPTS", "2")))
_RETRY_BACKOFF_S = float(os.getenv("GEOCODE_RETRY_BACKOFF", "1.5"))

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
_throttle_lock = threading.Lock()

# Per-tour counters, thread-local so concurrent generations do not pollute each
# other's numbers. These exist to answer one question with evidence rather than
# opinion: IS THE 1 REQ/SEC LIMIT ACTUALLY COSTING US ANYTHING YET?
#
# Until there are real users the answer is "no", and paying for a commercial
# geocoder would be premature. The metric line emitted at the end of every tour
# makes the moment it starts to matter observable instead of a guess:
#
#   [GEOCODE] tour summary | stops=10 lookups=32 throttle_wait=34.8s
#             rate_limited=0 replaced=4 unverified=2
#
# Suggested trigger to revisit: any tour where rate_limited > 0 outside a test,
# or where throttle_wait exceeds roughly a third of total generation time.
_stats = threading.local()


def _stats_reset():
    _stats.data = {"lookups": 0, "throttle_wait_s": 0.0, "rate_limited": 0}


def _stats_add(key, amount):
    d = getattr(_stats, "data", None)
    if d is None:
        _stats_reset()
        d = _stats.data
    d[key] = d.get(key, 0) + amount


def get_stats():
    """Counters for the current tour on this thread."""
    return dict(getattr(_stats, "data", None) or
                {"lookups": 0, "throttle_wait_s": 0.0, "rate_limited": 0})


def haversine_m(a, b):
    """Great-circle distance in metres between (lat, lng) pairs."""
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _throttle():
    """Wait until it is our turn to call Nominatim. Returns seconds spent waiting.

    WHY A LOCK. This was a bare `global _last_request_at` with a read, a sleep and
    a write, and no lock. That enforces 1 req/sec for a single sequential caller,
    which is how it was measured. Production is not that: tour-modernized runs
    --concurrency=5 on --max-instances=1 and each tour generates in its own
    thread, so every thread read the same _last_request_at before any of them
    updated it, all slept the same short interval, and all fired together. The
    effective rate became N req/sec against a policy of 1.

    Observed in production 2026-08-29 with three tours submitted together:

        [GEOCODE] lookup failed for '584 Komatsucho, ... Kyoto, Japan':
                  HTTP Error 429: Too many requests

    Nothing broke -- the module fails soft -- but coordinate correction silently
    stopped for those stops, which is the failure this module exists to prevent,
    happening precisely when the service is busiest and invisibly.

    Set GEOCODE_MIN_INTERVAL=0 to disable the wait entirely (see _MIN_INTERVAL_S).
    """
    global _last_request_at
    if _MIN_INTERVAL_S <= 0:
        return 0.0
    with _throttle_lock:
        elapsed = time.time() - _last_request_at
        wait = _MIN_INTERVAL_S - elapsed
        if wait > 0:
            time.sleep(wait)
        else:
            wait = 0.0
        _last_request_at = time.time()
        return wait


def geocode(query):
    """Resolve a free-text place to (lat, lng), or None.

    Returns None on any failure — no network, rate limited, no match, malformed
    response. Callers must treat None as "no opinion", never as an error.
    """
    if not query or not query.strip():
        return None

    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    # One retry on 429. A rate-limit answer is not "no opinion" -- it means we
    # asked too fast, and giving up turns a throttling event into a permanently
    # unverified stop.
    for attempt in range(_MAX_ATTEMPTS):
        waited = _throttle()
        _stats_add("throttle_wait_s", waited)
        _stats_add("lookups", 1)
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
                payload = json.load(resp)
            if not payload:
                return None
            return float(payload[0]["lat"]), float(payload[0]["lon"])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _stats_add("rate_limited", 1)
                if attempt + 1 < _MAX_ATTEMPTS:
                    backoff = _RETRY_BACKOFF_S * (2 ** attempt)
                    logging.warning("[GEOCODE] rate limited on %r, retrying in %.1fs",
                                    query, backoff)
                    time.sleep(backoff)
                    continue
            logging.warning("[GEOCODE] lookup failed for %r: %s", query, e)
            return None
        except Exception as e:
            logging.warning("[GEOCODE] lookup failed for %r: %s", query, e)
            return None
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


# Countries, so a trailing country is never mistaken for the city.
#
# This was a 16-name set, which meant every country outside it -- most of the
# world -- survived the filter and was returned AS THE CITY: 'Madagascar',
# 'Brazil', 'Turkey', 'India', 'Kenya', 'Argentina'. Wrong on 8 of 12 real
# address shapes; every one it got right happened to be one of the 16.
#
# A POSITIONAL RULE WAS TRIED FIRST AND REJECTED. "Drop the last component when
# there are 3+" looks elegant and needs no data, but it beheads an address that
# legitimately ends with a city: "Boston Common, 139 Tremont St, Boston" -> the
# rule returns 'Boston Common'. Position cannot tell 'Boston' from 'Madagascar';
# only knowledge can. The list is the honest tool. Country names are stable, so
# the maintenance burden this was meant to avoid is close to zero.
_COUNTRIES = {
    'afghanistan', 'albania', 'algeria', 'andorra', 'angola', 'argentina', 'armenia',
    'australia', 'austria', 'azerbaijan', 'bahamas', 'bahrain', 'bangladesh', 'barbados',
    'belarus', 'belgium', 'belize', 'benin', 'bhutan', 'bolivia', 'bosnia',
    'bosnia and herzegovina', 'botswana', 'brazil', 'brunei', 'bulgaria', 'burkina faso',
    'burundi', 'cambodia', 'cameroon', 'canada', 'cape verde', 'chad', 'chile', 'china',
    'colombia', 'congo', 'costa rica', 'croatia', 'cuba', 'cyprus', 'czechia',
    'czech republic', 'denmark', 'djibouti', 'dominican republic', 'ecuador', 'egypt',
    'el salvador', 'england', 'estonia', 'eswatini', 'ethiopia', 'fiji', 'finland',
    'france', 'gabon', 'gambia', 'georgia', 'germany', 'ghana', 'gibraltar', 'greece',
    'greenland', 'guatemala', 'guinea', 'guyana', 'haiti', 'honduras', 'hong kong',
    'hungary', 'iceland', 'india', 'indonesia', 'iran', 'iraq', 'ireland', 'israel',
    'italy', 'ivory coast', 'jamaica', 'japan', 'jordan', 'kazakhstan', 'kenya',
    'kosovo', 'kuwait', 'kyrgyzstan', 'laos', 'latvia', 'lebanon', 'lesotho', 'liberia',
    'libya', 'liechtenstein', 'lithuania', 'luxembourg', 'macau', 'madagascar', 'malawi',
    'malaysia', 'maldives', 'mali', 'malta', 'mauritania', 'mauritius', 'mexico',
    'moldova', 'monaco', 'mongolia', 'montenegro', 'morocco', 'mozambique', 'myanmar',
    'namibia', 'nepal', 'netherlands', 'new zealand', 'nicaragua', 'niger', 'nigeria',
    'north korea', 'north macedonia', 'northern ireland', 'norway', 'oman', 'pakistan',
    'palestine', 'panama', 'papua new guinea', 'paraguay', 'peru', 'philippines',
    'poland', 'portugal', 'puerto rico', 'qatar', 'romania', 'russia',
    'russian federation', 'rwanda', 'saudi arabia', 'scotland', 'senegal', 'serbia',
    'seychelles', 'sierra leone', 'singapore', 'slovakia', 'slovenia', 'somalia',
    'south africa', 'south korea', 'south sudan', 'spain', 'sri lanka', 'sudan',
    'suriname', 'sweden', 'switzerland', 'syria', 'taiwan', 'tajikistan', 'tanzania',
    'thailand', 'togo', 'trinidad and tobago', 'tunisia', 'turkey', 'turkiye',
    'turkmenistan', 'uganda', 'ukraine', 'united arab emirates', 'united kingdom',
    'united states', 'united states of america', 'uruguay', 'uzbekistan', 'vatican city',
    'venezuela', 'vietnam', 'wales', 'yemen', 'zambia', 'zimbabwe',
    # common abbreviations and informal forms the model actually writes
    'uae', 'uk', 'us', 'usa', 'u.s.', 'u.s.a.', 'u.k.', 'great britain', 'britain',
    'holland', 'south korea (rok)', 'the netherlands', 'the bahamas', 'the gambia',
}

_STREET_WORD = re.compile(
    r'\b(st|street|ave|avenue|rd|road|dr|drive|blvd|boulevard|way|lane|ln|rue|place|terrace|'
    r'trail|parkway|pkwy|hwy|court|ct|sq|square|dori)\b', re.IGNORECASE)


def _clean_component(part):
    """Strip postcodes and state codes from one comma-separated address component."""
    p = part.strip()
    # NL postcodes lead with digits AND two letters: "1071 DJ Amsterdam". This has
    # to run before the generic leading-digits strip below, which would leave
    # "DJ Amsterdam" -- and _is_junk_component then matches that as a state+code
    # pair (case-insensitively) and discards the city entirely.
    p = re.sub(r'^\d{4}\s*[A-Z]{2}\s+', '', p)                    # "1071 DJ Amsterdam" (NL)
    p = re.sub(r'^\d{3,5}(?:-\d{4})?\s+', '', p)                  # "75005 Paris" (FR/JP)
    # {2,3} not {2}: three-letter state codes are the common case in Australia
    # (NSW, QLD, VIC, TAS, ACT). With {2} the docstring's own worked example --
    # "Sydney NSW 2000" -- fell straight through and was returned verbatim.
    p = re.sub(r'\s+[A-Z]{2,3}\s+[A-Z\d][A-Z\d\s-]{2,}$', '', p)  # "Sydney NSW 2000"
    p = re.sub(r'\s+[A-Z]\d[A-Z]\s*\d[A-Z]\d$', '', p)            # "Toronto M4P 2A8"
    # UK outward+inward code. The state-code rule above cannot catch it because
    # the outward half contains a digit ("EH1"), so [A-Z]{2,3} never matches.
    p = re.sub(r'\s+[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$', '', p)    # "Edinburgh EH1 2NG"
    p = re.sub(r'\s+[A-Z]\d{4}$', '', p)                          # "Buenos Aires C1087" (AR)
    # Trailing numeric postcode of any common length, optionally hyphenated:
    # "Boston 02133", "Antananarivo 101", "Mumbai 400050",
    # "Rio de Janeiro 22070-002". Anchored to the end and requires preceding
    # whitespace, so a house number at the START is untouched (that is handled
    # above) and "Route 66" as a whole component is left alone by the street-word
    # filter downstream rather than here.
    p = re.sub(r'\s+\d{3,6}(?:-\d{3,4})?$', '', p)                # "Boston 02133"
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

    The city is the useful part; the postcode and country are noise. The city is
    also what anchors the reversed-coordinate check in fix_reversed_coordinates(),
    so returning a country there makes the anchor a country CENTROID rather than a
    city -- coarser than intended, and silently so.

    Measured 2026-08-29 against the deployed image, on 12 real address shapes:
    8 were wrong before this was fixed, and every one that was RIGHT happened to
    be in the old 16-country allowlist. Two independent bugs:

      1. Countries were filtered against a 16-name set, so 'Madagascar',
         'Brazil', 'Turkey', 'India', 'Kenya' and 'Argentina' were returned as
         cities. _COUNTRIES is now comprehensive -- see the note there on why a
         positional "drop the last component" rule was tried and rejected.
      2. _clean_component matched state codes with [A-Z]{2}, so three-letter
         Australian states did not match and 'Sydney NSW 2000' was returned
         verbatim -- the function's own worked example.

    A NOTE ON A CLAIM THAT DOES NOT REPRODUCE. This docstring used to assert that
    "Bennelong Point, Sydney NSW 2000" resolves 12.75 km off while
    "Bennelong Point, Sydney" resolves to 80 m. Re-measured 2026-08-29 against
    live Nominatim: the two forms return the IDENTICAL coordinate, 0.00 km apart,
    as do 'Copacabana, Brazil' vs 'Copacabana, Rio de Janeiro' and
    'Sultanahmet, Turkey' vs 'Sultanahmet, Istanbul'. Either Nominatim improved or
    the original measurement was of something else. Do not repeat the 12.75 km
    figure as fact, and do not justify work on this function by claiming it costs
    lookup accuracy -- the measured cost is zero. The reason to keep it correct is
    the anchor, and that the next reader should be able to trust what it says.
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


def resolve_stop(stop_text, tour_location, tour_anchor=None):
    """Pick a coordinate using agreement between independent sources.

    Returns (new_text, record). record["confidence"] is "high" when two sources
    corroborate each other, "low" when none do.

    The rule, and why:
      * two candidates within AGREEMENT_M  -> trust the geocoded one. When the
        sources agree they are usually both right, and the geocoder is the more
        precise of the two.
      * nothing corroborates               -> keep the MODEL's coordinate. It is
        the single most reliable source: in every large disagreement measured,
        the model was right and the address lookup was wrong.

    So a lookup can improve a coordinate, but only when something independent
    backs it up. Left alone otherwise.
    """
    name, address, model_pt = _parse_stop(stop_text)
    rec = {"stop": name, "address": address, "llm": model_pt,
           "confidence": "low", "action": "kept", "reason": "", "spread_m": None}

    if model_pt is None:
        rec.update(action="skipped", reason="stop has no Coordinates line")
        return stop_text, rec
    if not GEOCODE_ENABLED:
        rec.update(reason="geocoding disabled")
        return stop_text, rec

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
        # Prefer a geocoded member of the agreeing pair over the model's value.
        pick = next((k for k in best_pair if k != "model"), None)
        if pick is None:
            rec.update(reason=f"only the model available; nothing to corroborate")
            return stop_text, rec
        chosen = everything[pick]
        if haversine_m(chosen, model_pt) <= 1.0:
            rec.update(reason=f"{' + '.join(best_pair)} agree within {best_gap:.0f} m")
            return stop_text, rec
        new_text = _COORD_RE.sub(
            lambda m: f"{m.group(1)}{chosen[0]:.6f}, {chosen[1]:.6f}", stop_text, count=1)
        rec.update(action="replaced", chosen=pick,
                   reason=f"{' + '.join(best_pair)} agree within {best_gap:.0f} m")
        return new_text, rec

    rec.update(reason=("sources disagree" if best_gap is not None else "no lookup succeeded")
                      + " — keeping the model's coordinate")
    return stop_text, rec


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


def _swap_coord_line(stop_text):
    """Return stop_text with its Coordinates pair reversed."""
    return _COORD_RE.sub(lambda m: f"{m.group(1)}{m.group(3)}, {m.group(2)}", stop_text, count=1)


def fix_reversed_coordinates(text_content):
    """Repair tours whose stops were written longitude-first.

    The generator sometimes emits the pair the wrong way round for an entire
    tour. Every stop then plots on the far side of the world, and the tour is
    not merely inaccurate but unusable. Observed in Madagascar tours:

        Rova of Antananarivo   Coordinates: 47.5224, -18.9110
            as written  9,899 km from Antananarivo
            swapped         3.9 km

    Two checks, cheapest first:

    1. Latitude outside +/-90 is impossible. No reference data needed, and it is
       always wrong. (It would NOT have caught the Madagascar case, where 47.52
       is a perfectly valid latitude -- hence the second check.)

    2. Compare the whole tour against its own city, taken from the stops'
       addresses. If the stops are dramatically closer when swapped, the pair is
       reversed. The margin is not subtle: ~9,900 km against ~4 km. Requiring a
       10x improvement across a majority of stops makes a false positive
       implausible -- a correctly-written tour cannot be 10x better mirrored
       unless it sits almost exactly on the equator AND the prime meridian.

    Runs before anything else, so the plausibility anchor is computed from
    corrected values. Without that ordering the guard rejects the CORRECT
    geocoder answers, because the anchor is itself in the wrong ocean.

    Returns (text_content, record).
    """
    rec = {"checked": len(text_content), "action": "none", "reason": ""}
    parsed = []
    for t in text_content:
        name, address, coords = _parse_stop(t)
        if coords:
            parsed.append((t, name, address, coords))
    if not parsed:
        return text_content, rec

    impossible = [p for p in parsed if abs(p[3][0]) > 90]
    if impossible:
        logging.warning("[GEOCODE] %d stop(s) have an impossible latitude (>90)", len(impossible))
        rec["impossible_latitude"] = len(impossible)

    city = ""
    for _, _, address, _ in parsed:
        city = city_from_address(address)
        if city:
            break
    if not city:
        if impossible:
            fixed = [_swap_coord_line(t) if abs(c[0]) > 90 else t for t, _, _, c in parsed]
            rec.update(action="swapped", reason="latitude outside +/-90 and no city to check against")
            return fixed, rec
        rec.update(reason="no city available to test against")
        return text_content, rec

    ref = geocode(city)
    if not ref:
        rec.update(reason=f"could not geocode the tour city {city!r}")
        return text_content, rec

    better = 0
    for _, _, _, coords in parsed:
        as_is = haversine_m(coords, ref)
        flipped = haversine_m((coords[1], coords[0]), ref)
        if flipped * 10 < as_is:
            better += 1

    rec.update(city=city, stops_better_swapped=better)
    if better > len(parsed) / 2:
        logging.warning(
            "[GEOCODE] REVERSED COORDINATES: %d of %d stops are >10x closer to %s when "
            "swapped — correcting the whole tour", better, len(parsed), city)
        rec.update(action="swapped",
                   reason=f"{better}/{len(parsed)} stops are 10x closer to {city} when reversed")
        return [_swap_coord_line(t) for t in text_content], rec

    rec.update(reason="coordinate order looks correct")
    return text_content, rec


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
    # Repair a wholly reversed tour FIRST. The anchor below is the median of the
    # stops, so if every coordinate is mirrored the anchor lands in the wrong
    # ocean and the guard then rejects the correct geocoder answers.
    text_content, swap_rec = fix_reversed_coordinates(text_content)
    if swap_rec.get("action") == "swapped":
        logging.warning("[GEOCODE] tour coordinates were reversed and have been corrected: %s",
                        swap_rec.get("reason"))

    # Prefer a geocoded anchor, but never proceed without one if the stops can
    # supply it themselves. An absent anchor silently disables the only guard
    # against a confidently wrong same-name match.
    if tour_anchor is None:
        tour_anchor = _median_anchor(text_content)
        if tour_anchor:
            logging.info("[GEOCODE] anchor from stop median: %.4f, %.4f", *tour_anchor)

    _stats_reset()
    started = time.time()

    def _one(stop_text):
        try:
            return resolve_stop(stop_text, tour_location, tour_anchor)
        except Exception as e:                      # pragma: no cover - defensive
            logging.warning("[GEOCODE] stop validation errored, keeping original: %s", e)
            return stop_text, {"action": "error", "reason": str(e)}

    if _MAX_PARALLEL > 1 and len(text_content) > 1:
        # Only reachable once GEOCODE_MAX_PARALLEL is raised, which is the paid-
        # geocoder path. The throttle still applies per request, so this is safe
        # to enable at any interval -- it just stops being a bottleneck when the
        # interval is 0. Order is preserved: map() returns results in order.
        with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
            results = list(pool.map(_one, text_content))
    else:
        results = [_one(s) for s in text_content]

    new_content = [r[0] for r in results]
    records = [r[1] for r in results]

    replaced = sum(1 for r in records if r["action"] == "replaced")
    flagged = sum(1 for r in records if r["action"] == "flagged")
    logging.info("[GEOCODE] %d stops: %d replaced, %d flagged", len(records), replaced, flagged)
    for r in records:
        if r["action"] in ("replaced", "flagged"):
            logging.info("[GEOCODE]   %s: %s -> %s (%s)",
                         r.get("stop"), r.get("llm"), r.get("geocoded"), r["reason"])

    # One greppable line per tour. This is the evidence for deciding WHEN the
    # free-tier rate limit starts costing something -- see the note on _stats.
    s = get_stats()
    unverified = sum(1 for r in records if r["action"] not in ("replaced", "kept"))
    logging.warning(
        "[GEOCODE] tour summary | stops=%d lookups=%d throttle_wait=%.1fs "
        "rate_limited=%d replaced=%d unverified=%d elapsed=%.1fs "
        "min_interval=%.2f max_parallel=%d",
        len(records), s["lookups"], s["throttle_wait_s"], s["rate_limited"],
        replaced, unverified, time.time() - started, _MIN_INTERVAL_S, _MAX_PARALLEL)

    return new_content, records
