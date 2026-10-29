"""places_search.py — the ONE place-search provider for business/restaurant POIs.

LOCAL-783.
==========
WHY THIS EXISTS
---------------
LOCAL-779/779B gave restaurant and business tours a maps refill: when PHASE 3C or
the existence gate empties the stop list, the engine asks the MAP for
"<cuisine> restaurants in <scope>" / "<poi_type> in <scope>" and takes the real,
in-scope listings. But that bulk search (and the per-name verification) went to the
FREE Nominatim endpoint, which "returned 0 live for both West Roxbury and the North
End" (LOCAL-779B, Known limitation). The refill — the thing that rescues a tour when
the LLM proposes the wrong town — was therefore empty in practice.

We already pay for Serper (SERP_PROVIDER=serper, SERP_API_KEY on the generator,
metered by the paid-API meter). Serper has a Places endpoint
(https://google.serper.dev/places) that returns name, address, lat/lng, category,
rating and cid — exactly the fields the gate needs.

LEAD PROBE (2026-10-26, 3 credits) — HOW TO CALL SERPER PLACES
--------------------------------------------------------------
  * {"q":"middle eastern restaurants in West Roxbury, MA","gl":"us"}
        → El Dorado Hills, CA results. The town in `q` is IGNORED.
  * {"q":"middle eastern restaurants","location":"West Roxbury, …"}
        → a mix of Dedham/Watertown/Allston + the 3 local ones (too wide).
  * {"q":"middle eastern restaurants West Roxbury MA","ll":"@42.2794,-71.1595,14z",
     "gl":"us"}
        → EXACTLY Al Wadi, Stardust, Bread Thyme — what Google shows.
So we ALWAYS send `ll` (the scope's geocoded centre, or the device's coordinates
for "near me") with a zoom matching the scope (neighbourhood ~14z, city ~12z), and
then keep only results inside the scope (the caller's distance / signal check).

WHAT THIS GUARANTEES
--------------------
  * places_search(query, scope, near=None, limit=10) → a list of normalised
    place dicts (OSM-jsonv2 SHAPED so the existing gate filters work unchanged).
  * When SERP_API_KEY is set AND SERP_PROVIDER=serper → Serper Places, metered
    once per uncached call through serper_meter.serper_post() (priced at the
    Places rate, $0.002, by the meter). Otherwise → Nominatim (today's behaviour).
  * map_lookup(params, context) is a DROP-IN for
    stop_existence_gate._nominatim_request: it takes the same `params` dict (with
    `q`), returns an object with a .json() that yields OSM-shaped records. The gate
    keeps calling one function; this module decides the provider.
  * CACHE: identical (provider, query, ll) within 24 h reuse the result, so a
    repeated tour does not re-bill. In-process, thread-safe, TTL 24 h.

NORMALISATION
-------------
A Serper Places result:
    {"title","address","latitude","longitude","category","type","rating","cid",…}
becomes the OSM jsonv2 shape the gate already consumes:
    {"name","display_name","category","type","lat","lon","address":{…},
     "extratags":{"cuisine":…}}
so cuisine_matches / scope proximity / distance ranking in stop_existence_gate run
byte-for-byte unchanged no matter which provider answered.
"""
import json
import os
import re
import threading
import time
import unicodedata
from typing import Dict, List, Optional, Tuple

try:  # metered Serper door (LOCAL-707). Present on host and in containers.
    from serper_meter import serper_post as _serper_post
except Exception:  # pragma: no cover - fail open to Nominatim
    _serper_post = None

_PLACES_ENDPOINT = "https://google.serper.dev/places"

# ──────────────────────── 24 h identical-query cache ─────────────────────────
_CACHE_TTL_SECONDS = 24 * 60 * 60
_cache_lock = threading.Lock()
_cache: Dict[str, Tuple[float, List[Dict]]] = {}


def _cache_get(key: str) -> Optional[List[Dict]]:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        ts, value = hit
        if now - ts > _CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        # Return a shallow copy so a caller mutating a record can't poison the cache.
        return [dict(r) for r in value]


def _cache_put(key: str, value: List[Dict]) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), [dict(r) for r in value])


def clear_cache() -> None:
    """Drop the whole 24 h cache (tests call this between cases)."""
    with _cache_lock:
        _cache.clear()


# ──────────────────────────── provider selection ────────────────────────────
def serper_places_enabled() -> bool:
    """True when the Serper Places provider should be used: a key is present AND
    SERP_PROVIDER is serper (the deployed default). Otherwise Nominatim is used."""
    key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPER_API_KEY")
    provider = (os.environ.get("SERP_PROVIDER", "serper") or "").strip().lower()
    return bool(key) and provider == "serper" and _serper_post is not None


def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


# [LOCAL-791 defects 6 & 10] A map listing's `title` is a raw Google Maps label,
# NOT a clean place name. Two kinds of noise ride in it and, uncleaned, become the
# stop's spoken title:
#
#   defect 10 — a GOOGLE CATEGORY SUFFIX after a colon: "Stardust: Inspired
#               Mediterranean , Persian" (West Roxbury, Mac e2e). The ": <list>"
#               tail is the venue's Google categories, not part of its name, so it
#               is stripped — leaving "Stardust". A stray " ," left by the split is
#               tidied.
#
#   defect 6  — a bracketed TAG LIST in a script other than the place's own and
#               the tour language: "An Spa - Healing & Relax (Massage Mũi Né -
#               샴푸와 컨디셔너, 마사지)" (Korean marketing keywords). A parenthetical
#               whose content is MOSTLY a foreign (non-Latin) script is marketing
#               noise and is dropped — leaving "An Spa - Healing & Relax".
#
# Conservative: a parenthetical in the SAME script as the name (a Latin gloss, a
# Vietnamese local name) is kept, and a short category list is only cut when it
# follows a colon (so a real name containing a colon keeps its first clause, which
# is the name). Pure, deterministic, no network.

# A run of ONE OR MORE non-Latin letters (CJK, Hangul, Arabic, Cyrillic, Thai …).
# Latin (incl. Vietnamese diacritics) is NFKD-stripped to ASCII first, so only a
# genuinely different script survives as a "foreign" letter here.
_NON_LATIN_LETTER_RE = re.compile(
    r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0E00-\u0E7F"
    r"\u1100-\u11FF\u3040-\u30FF\u3130-\u318F\uAC00-\uD7AF"
    r"\u4E00-\u9FFF\u3400-\u4DBF]")


def _is_mostly_foreign_script(text: str) -> bool:
    """True when `text`'s LETTERS are mostly a non-Latin script (CJK, Hangul,
    Arabic, Cyrillic, Thai …). Vietnamese and other Latin-with-diacritics text is
    NOT foreign (it folds to ASCII letters). Used to spot a marketing tag list in
    another language inside a parenthetical."""
    foreign = len(_NON_LATIN_LETTER_RE.findall(text or ""))
    latin = sum(1 for c in (text or "") if c.isascii() and c.isalpha())
    if foreign == 0:
        return False
    return foreign >= latin


def clean_place_title(title: str) -> str:
    """Clean a raw map-listing title into a stop title (defects 6 & 10).

    1. Drop any parenthetical / bracketed group whose content is MOSTLY a foreign
       (non-Latin) script — a marketing tag list in another language.
    2. Strip a trailing ": <category list>" Google-category suffix.
    3. Tidy stray " ," / doubled spaces / leftover punctuation.

    Returns the cleaned name; never returns empty (falls back to the original
    stripped title if cleaning would empty it)."""
    raw = (title or "").strip()
    if not raw:
        return raw
    out = raw

    # 1. Foreign-script bracketed tag lists: ( … ), [ … ], 【 … 】.
    def _drop_foreign_bracket(m: "re.Match") -> str:
        inner = m.group(1)
        return "" if _is_mostly_foreign_script(inner) else m.group(0)
    out = re.sub(r"\(([^()]*)\)", _drop_foreign_bracket, out)
    out = re.sub(r"\[([^\[\]]*)\]", _drop_foreign_bracket, out)
    out = re.sub(r"\u3010([^\u3010\u3011]*)\u3011", _drop_foreign_bracket, out)

    # 2. Google category suffix after a colon: keep the name (first clause). Only
    #    when the tail reads as a category list (contains a comma, or is short), so
    #    a real titled work "Blue: A Study" is not truncated unless it looks like a
    #    Maps category tail.
    cm = re.match(r"^(?P<name>[^:]+):\s*(?P<tail>.+)$", out)
    if cm:
        name = cm.group("name").strip()
        tail = cm.group("tail").strip()
        # A Maps category tail is a COMMA-joined list of category words with no
        # sentence punctuation — "Inspired Mediterranean , Persian". Requiring a
        # comma keeps a real colon-titled work safe ("Blue: A Study of Light",
        # "Nocturne: Blue and Gold" are never truncated — their tail has no comma).
        if name and "," in tail and not re.search(r"[.!?]", tail):
            out = name

    # 3. Tidy: collapse " ," / " ;" spacing, doubled spaces, trailing separators.
    out = re.sub(r"\s+([,;])", r"\1", out)
    out = re.sub(r"[,;\-\s]+$", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out or raw


# ──────────────────── Serper Places → OSM jsonv2 shape ──────────────────────
# [LOCAL-805B] Address comma-parts that are NOT a town name. A Serper address is
# a free-text, locale-shaped string; the part after the street is only sometimes
# the town. Vietnamese addresses carry an extra segment between the street and the
# ward — "12 Đặng Trần Côn, P, Bến Thành, …" (the "P" is a truncated "Phường"
# ward marker) and "114 Lê Thị Hồng Gấm, Street, Bến Thành, …" (a literal
# "Street" tail on the road). Taking the second part blindly then read the town as
# "p" / "street", and the town-name mismatch guard dropped a genuinely in-scope
# spa. These tokens are street-type words and admin-unit prefixes — never a town —
# so the locality parser skips them and takes the first real locality part.
_ADDR_NON_TOWN_TOKENS = frozenset((
    # Street-type words (English + common abbreviations).
    "street", "st", "road", "rd", "avenue", "ave", "av", "boulevard", "blvd",
    "lane", "ln", "drive", "dr", "way", "court", "ct", "place", "pl", "square",
    "sq", "alley", "highway", "hwy", "route", "rt", "parkway", "pkwy",
    # Vietnamese admin-unit prefixes that ride in as their own comma-part: a bare
    # "P" / "P." / "Phường" (ward), "Q"/"Quận" alone (district w/o a number),
    # "TP"/"Thành Phố" (city) prefix, "X"/"Xã" (commune), "TT" (town).
    "p", "phuong", "q", "quan", "tp", "x", "xa", "tt",
))


def _is_locality_part(part: str) -> bool:
    """[LOCAL-805B] True when a comma-part of an address reads as a genuine
    locality (town / ward / city) rather than noise — a pure number/postcode, a
    street-type word, or a bare single-letter admin-unit prefix ("P", "Q")."""
    folded = _strip_accents(part or "").lower().strip()
    if not folded:
        return False
    if not any(ch.isalpha() for ch in folded):  # pure number / postcode
        return False
    if len(folded) <= 1:  # a truncated single-letter prefix ("P")
        return False
    if folded in _ADDR_NON_TOWN_TOKENS:  # street-type word or admin prefix
        return False
    return True


def _first_locality_part(parts: List[str]) -> str:
    """[LOCAL-805B] The first genuine locality comma-part AFTER the leading street
    part (index 0), skipping noise segments. "" when none. "12 Đặng Trần Côn, P,
    Bến Thành, Hồ Chí Minh 700000, Vietnam" → "Bến Thành"; "678 Washington St,
    Norwood, MA 02062" → "Norwood" (unchanged)."""
    for cand in parts[1:]:
        if _is_locality_part(cand):
            return cand.strip()
    return ""


def _parse_address_components(address: str) -> Dict[str, str]:
    """Best-effort split of a Serper `address` string into the OSM address sub-dict
    fields the gate reads (road, house_number, city, state, suburb). Serper gives a
    single formatted string like "1249 VFW Pkwy, West Roxbury, MA 02132"; we parse
    enough of it that the gate's scope proximity check (which looks at city / state
    / suburb / display_name) can bind. Unknown parts are simply omitted — the gate
    also falls back to a display_name substring match, so a partial parse is safe."""
    out: Dict[str, str] = {}
    if not address:
        return out
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return out
    # First part: "1249 VFW Pkwy" → house_number + road.
    street = parts[0]
    m = re.match(r"^(\d+[A-Za-z]?(?:[-/]\d+)?)\s+(.*)$", street)
    if m:
        out["house_number"] = m.group(1)
        out["road"] = m.group(2)
    else:
        out["road"] = street
    # Middle parts: city / suburb. Last part often "MA 02132" → state (+ postcode).
    # [LOCAL-805B] Pick the first GENUINE locality part after the street, skipping
    # a noise segment ("P" ward prefix, a literal "Street" tail) so a Vietnamese
    # address does not set city="p"/"street". Falls back to parts[1] only if no
    # part reads as a locality (keeps the old behaviour for a bare two-part string).
    if len(parts) >= 2:
        _loc = _first_locality_part(parts) or parts[1]
        out["city"] = _loc
        out["suburb"] = _loc
    if len(parts) >= 3:
        tail = parts[-1]
        sm = re.match(r"^([A-Za-z .]+?)\s*(\d{4,6})?$", tail)
        if sm and sm.group(1):
            out["state"] = sm.group(1).strip()
    return out


def _normalize_serper_place(p: Dict) -> Optional[Dict]:
    """Map one Serper Places result to the OSM jsonv2 shape the gate consumes.

    Returns None for a result with no usable name or coordinates."""
    name = (p.get("title") or p.get("name") or "").strip()
    if not name:
        return None
    # [LOCAL-791 defects 6 & 10] Clean the raw Maps label into a stop title: drop
    # a foreign-script marketing tag list ("An Spa … (… 샴푸와 컨디셔너, 마사지)") and a
    # trailing ": <category list>" Google-category suffix ("Stardust: Inspired
    # Mediterranean , Persian" → "Stardust"), before the name becomes the title.
    name = clean_place_title(name)
    if not name:
        return None
    try:
        lat = float(p.get("latitude"))
        lon = float(p.get("longitude"))
    except (TypeError, ValueError):
        return None
    address_str = (p.get("address") or "").strip()
    # Serper gives a free-text `category` / `type` (e.g. "Middle Eastern restaurant",
    # "Lebanese restaurant", "Gym"). The gate's dining/business detection wants an
    # OSM `type` token (restaurant/cafe/gym/…) and reads `extratags.cuisine` for the
    # cuisine. We map the category text into both: a coarse OSM type, and a cuisine
    # tag that carries the full category text so cuisine_matches() can read it.
    category_text = _strip_accents(
        str(p.get("category") or p.get("type") or "")).lower()
    osm_type, osm_category = _osm_type_from_category(category_text, name)
    display = name
    if address_str:
        display = f"{name}, {address_str}"
    rec = {
        "name": name,
        "display_name": display,
        "category": osm_category,
        "type": osm_type,
        "lat": str(lat),
        "lon": str(lon),
        "address": _parse_address_components(address_str),
        # Carry the full Serper category text as the cuisine signal; cuisine_matches
        # reads extratags.cuisine first. "Lebanese restaurant" → matches middle
        # eastern; "Chinese restaurant" → conflicts. The amenity key preserves the
        # OSM look so _listing_cuisine_tokens picks it up.
        "extratags": {"cuisine": category_text} if category_text else {},
        # Provenance (not read by the gate, useful in evidence/logs).
        "_serper_cid": p.get("cid"),
        "_serper_rating": p.get("rating"),
        "_serper_category": p.get("category") or p.get("type"),
        # [LOCAL-800] Customer-voice fields, carried straight off the SAME Places
        # response so the "What people say" paragraph (customer_voice.py) can be
        # built with NO extra Serper call: the Google rating is already here
        # (_serper_rating), and these add the review COUNT, the price band and the
        # venue's own website. Each is None/absent when Serper did not provide it —
        # the paragraph omits any item with no source and never invents a number.
        "_serper_rating_count": p.get("ratingCount") or p.get("reviewsCount"),
        "_serper_price_level": p.get("priceLevel"),
        "_serper_website": p.get("website"),
        # [LOCAL-786] Carry the raw formatted address so the town-mismatch guard can
        # read the town Serper gave ("…, Norwood, MA 02062") even when the structured
        # address parse left `city` blank.
        "_serper_address": address_str,
    }
    return rec


# OSM amenity/type tokens the gate recognises (mirrors stop_existence_gate's
# _DINING_OSM_TYPES / _BUSINESS_OSM_TYPES so a Serper record routes identically to
# a Nominatim one). Dining first (so "restaurant"/"cafe"/"bar" classify as dining),
# then the broader business tokens.
_DINING_CATEGORY_HINTS = (
    "restaurant", "cafe", "café", "coffee", "bar", "pub", "bakery", "bistro",
    "brasserie", "diner", "eatery", "pizzeria", "steakhouse", "grill",
    "ice cream", "fast food", "food",
)
_DINING_OSM_TYPE = {
    "restaurant": "restaurant", "cafe": "cafe", "café": "cafe", "coffee": "cafe",
    "bar": "bar", "pub": "pub", "bakery": "bakery", "bistro": "bistro",
    "brasserie": "brasserie", "diner": "restaurant", "eatery": "restaurant",
    "pizzeria": "restaurant", "steakhouse": "restaurant", "grill": "restaurant",
    "ice cream": "ice_cream", "fast food": "fast_food", "food": "restaurant",
}
_BUSINESS_OSM_TYPE = {
    "gym": "gym", "fitness": "fitness_centre", "yoga": "yoga", "pilates": "pilates",
    "climbing": "climbing", "spa": "spa", "salon": "hairdresser",
    "barber": "hairdresser", "bakery": "bakery", "book": "books",
    "grocery": "supermarket", "supermarket": "supermarket", "market": "greengrocer",
    "brewery": "brewery", "winery": "winery", "distillery": "distillery",
    "shop": "clothes", "store": "clothes", "boutique": "clothes",
}

# Serper's Places `category` for a food establishment is frequently a bare CUISINE
# ("Middle Eastern", "Lebanese", "Italian", "Mediterranean") with no "restaurant"
# token at all. Those are dining venues, so a category whose text matches any of
# these cuisine words classifies as a restaurant. Mirrors the cuisine keys/synonyms
# in stop_existence_gate so a Serper record routes to the dining path exactly as a
# "<cuisine> restaurant" one would.
_CUISINE_CATEGORY_WORDS = (
    "middle eastern", "mediterranean", "lebanese", "turkish", "persian", "arab",
    "arabic", "syrian", "israeli", "egyptian", "moroccan", "armenian", "levantine",
    "italian", "pizza", "pasta", "trattoria", "osteria", "ristorante", "sicilian",
    "mexican", "taqueria", "tex-mex", "chinese", "dim sum", "szechuan", "cantonese",
    "japanese", "sushi", "ramen", "izakaya", "thai", "indian", "tandoori", "curry",
    "french", "greek", "korean", "vietnamese", "pho", "spanish", "tapas",
    "american", "seafood", "vegan", "vegetarian", "halal", "kebab", "falafel",
    "shawarma", "gyro", "burger", "bbq", "barbecue", "noodle", "dumpling",
)


def _osm_type_from_category(category_text: str, name: str) -> Tuple[str, str]:
    """Infer an OSM (type, category) pair from Serper's free-text category and the
    name. Dining categories map to amenity/restaurant-family; businesses to their
    OSM leisure/shop/amenity token. Falls back to a generic amenity when unsure so
    a named place is still kept by the gate's strong-name-match branch."""
    blob = f"{category_text} {_strip_accents(name).lower()}"
    for hint in _DINING_CATEGORY_HINTS:
        if hint in blob:
            return _DINING_OSM_TYPE.get(hint, "restaurant"), "amenity"
    # A bare cuisine category ("Middle Eastern", "Lebanese") is a restaurant.
    for word in _CUISINE_CATEGORY_WORDS:
        if word in category_text:
            return "restaurant", "amenity"
    for hint, osm in _BUSINESS_OSM_TYPE.items():
        if hint in blob:
            # Gyms/fitness are leisure in OSM; shops are shop; the rest amenity.
            if osm in ("gym", "fitness_centre", "climbing", "yoga", "pilates"):
                return osm, "leisure"
            if osm in ("clothes", "books", "supermarket", "greengrocer"):
                return osm, "shop"
            return osm, "amenity"
    # Unknown category: keep as a generic amenity; the gate's strong-name-match
    # path still accepts it when the name clearly matches the query.
    return "yes", "amenity"


# ────────────────────────────── Serper call ─────────────────────────────────
def _zoom_for_scope(scope: str) -> str:
    """Pick a Serper `ll` zoom matching the scope size: a neighbourhood / small
    locality ~14z, a bare city ~12z. Heuristic on the scope text — a scope with a
    neighbourhood-ish token (two capitalised words before the state, or a known
    neighbourhood marker) zooms tighter. Conservative: default 13z sits between."""
    s = (scope or "").strip()
    if not s:
        return "13z"
    head = s.split(",")[0].strip()
    words = [w for w in head.split() if w]
    # Multi-word locality (e.g. "West Roxbury", "North End", "Jamaica Plain") →
    # neighbourhood zoom. Single-word head (e.g. "Brookline", "Boston") → city.
    if len(words) >= 2:
        return "14z"
    return "12z"


def _serper_places_call(query: str, ll: Optional[str], gl: str = "us",
                        location: Optional[str] = None) -> List[Dict]:
    """POST one Serper Places query and return the normalised OSM-shaped records.
    Metered exactly once via serper_meter.serper_post (priced at the Places rate).
    Returns [] on any failure (fail-open — the caller falls back / refuses)."""
    if _serper_post is None:
        return []
    payload: Dict[str, object] = {"q": query, "gl": gl}
    if ll:
        payload["ll"] = ll
    if location:
        payload["location"] = location
    try:
        status, body = _serper_post(_PLACES_ENDPOINT, payload)
    except Exception:
        return []
    if status != 200 or not body:
        return []
    try:
        data = json.loads(body.decode("utf-8", "ignore"))
    except Exception:
        return []
    places = data.get("places") or []
    out = []
    for p in places:
        rec = _normalize_serper_place(p)
        if rec is not None:
            out.append(rec)
    return out


def _ll_from_near(near: Optional[Tuple[float, float]], scope: str) -> Optional[str]:
    """Build the Serper `ll` string "@lat,lng,ZZz" from device coords ("near me")
    when provided, else None (the caller passes a scope-centre `ll` via map_lookup).
    """
    if not near:
        return None
    try:
        lat, lng = float(near[0]), float(near[1])
    except (TypeError, ValueError, IndexError):
        return None
    return f"@{lat},{lng},{_zoom_for_scope(scope)}"


# ─────────────────────────────── public API ─────────────────────────────────
def _haversine_km(a, b) -> float:
    """Great-circle km between two (lat, lng) pairs; inf if either is missing."""
    import math
    if not a or not b:
        return float("inf")
    try:
        lat1, lon1 = float(a[0]), float(a[1])
        lat2, lon2 = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError):
        return float("inf")
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


# Scope radius (km) by the `ll` zoom. A neighbourhood (14z) tour keeps places
# within ~4 km of the centre; a city (12z) within ~10 km. Serper's `ll` already
# biases to the centre, so this is a backstop that drops a spillover result from
# a neighbouring town when Serper reaches past the scope.
#
# [LOCAL-786] The radius is no longer a fixed per-zoom value. Tour 454 shipped
# Byblos in Norwood (~10 km) on a West Roxbury request because the old 14z radius
# (4 km) was both too loose for a neighbourhood AND silently skipped when no centre
# was geocoded. The radius now follows the SCOPE PRECISION, and the geocoder's
# bounding box (when present) is preferred over any fixed radius.
#   NEIGHBOURHOOD (West Roxbury, North End, Jamaica Plain): ~2.5 km
#   CITY: ~8 km for a small city, up to ~15 km for a large one
#   REGION/COUNTRY: wide (unchanged) — no tightening.
#   "near me" (device coordinates): 3 km of the device by default.
_NEIGHBOURHOOD_RADIUS_KM = 2.5
_CITY_RADIUS_SMALL_KM = 8.0
_CITY_RADIUS_LARGE_KM = 15.0
_REGION_RADIUS_KM = 60.0
_NEAR_ME_RADIUS_KM = 3.0
# [LOCAL-805] A "<business> near <LANDMARK>" request centres on a single POINT
# landmark (Ben Thanh Market, Boston Common, Fenway Park). The listener means
# "walkable from that spot", so the search radius is tighter than a whole
# neighbourhood — ~1.5 km. LOCAL-802's ×2 widening grows it to ~3 km once before
# delivering fewer than requested.
_LANDMARK_RADIUS_KM = 1.5
# How far outside the bbox a record may sit and still be kept (the geocoder's bbox
# is tight to the named area; a 500 m margin forgives a border address).
_BBOX_MARGIN_KM = 0.5
# Point-landmark class words: when the scope HEAD ends in one of these, the scope
# is a single landmark to centre on (a market, square, common, park, cathedral,
# …), NOT a residential neighbourhood. Used only to pick the tighter LANDMARK
# radius; a known neighbourhood/region marker still wins (checked first).
_LANDMARK_CLASS_WORDS = (
    "market", "square", "common", "park", "cathedral", "basilica", "pagoda",
    "temple", "tower", "monument", "plaza", "piazza", "fountain", "gardens",
    "palace", "castle", "pier", "wharf", "bridge", "stadium", "arena",
)

# A scope whose locality token matches one of these (or whose head is two or more
# words, the classic "West Roxbury" / "North End" / "Jamaica Plain" shape) is a
# NEIGHBOURHOOD. A single-word locality ("Brookline", "Boston") is a CITY.
_NEIGHBOURHOOD_MARKERS = (
    "west roxbury", "north end", "jamaica plain", "east boston", "south boston",
    "hyde park", "roslindale", "dorchester", "roxbury", "mattapan", "brighton",
    "allston", "charlestown", "beacon hill", "back bay", "south end", "fenway",
    "downtown", "chinatown", "seaport", "mission hill", "west end",
)
# Large cities whose metropolitan reach justifies the wider CITY radius (~15 km).
_LARGE_CITY_MARKERS = (
    "new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia",
    "san antonio", "san diego", "dallas", "san jose", "london", "paris", "tokyo",
    "toronto", "atlanta", "miami", "seattle", "boston", "san francisco",
)
# Region/state-level scope words — these skip the tight radius entirely.
_REGION_MARKERS = (
    "county", "state", "province", "region", "riviera", "cape cod", "the berkshires",
    "new england", "bay area", "metro",
)


def _scope_precision(scope: str) -> str:
    """Classify a scope string into LANDMARK / NEIGHBOURHOOD / CITY / REGION.

    LANDMARK: a single point landmark to centre on (Ben Thanh Market, Boston
    Common, Fenway Park) — a "<business> near <landmark>" search centre (LOCAL-805).
    NEIGHBOURHOOD: a named city sub-area (West Roxbury, North End, Jamaica Plain) —
    detected by a known neighbourhood marker OR a multi-word locality head.
    CITY: a single-word locality (Brookline, Boston).
    REGION: a county/state/region word, which skips the tight radius.
    """
    s = (scope or "").strip().lower()
    if not s:
        return "CITY"
    for marker in _REGION_MARKERS:
        if marker in s:
            return "REGION"
    head = s.split(",")[0].strip()
    for marker in _NEIGHBOURHOOD_MARKERS:
        if marker == head or marker in head:
            return "NEIGHBOURHOOD"
    # [LOCAL-805] A landmark-class head ("… Market", "… Common", "… Park",
    # "… Cathedral") is a POINT to centre a near-landmark search on — tighter than
    # a residential neighbourhood. Checked AFTER the known-neighbourhood markers so
    # a neighbourhood that happens to end in "Park" (e.g. "Hyde Park") stays a
    # neighbourhood.
    _head_words = head.split()
    if _head_words and _head_words[-1] in _LANDMARK_CLASS_WORDS:
        return "LANDMARK"
    words = [w for w in head.split() if w]
    if len(words) >= 2:
        return "NEIGHBOURHOOD"
    return "CITY"


def _radius_for_precision(precision: str, scope: str = "") -> float:
    """Scope radius (km) for a precision level. CITY widens for a large city."""
    p = (precision or "").upper()
    if p == "LANDMARK":
        return _LANDMARK_RADIUS_KM
    if p == "NEIGHBOURHOOD":
        return _NEIGHBOURHOOD_RADIUS_KM
    if p == "REGION":
        return _REGION_RADIUS_KM
    # CITY: small by default, wider for a recognised large city.
    s = (scope or "").strip().lower()
    for marker in _LARGE_CITY_MARKERS:
        if marker in s:
            return _CITY_RADIUS_LARGE_KM
    return _CITY_RADIUS_SMALL_KM


def _parse_bbox(bbox) -> Optional[Tuple[float, float, float, float]]:
    """Parse a Nominatim jsonv2 boundingbox [south, north, west, east] (strings or
    floats) into a (south, north, west, east) float tuple, or None if unusable."""
    if not bbox:
        return None
    try:
        south, north, west, east = (float(bbox[0]), float(bbox[1]),
                                    float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError, IndexError):
        return None
    if south > north:
        south, north = north, south
    if west > east:
        west, east = east, west
    return (south, north, west, east)


def _inside_bbox(lat: float, lon: float,
                 bbox: Tuple[float, float, float, float],
                 margin_km: float = _BBOX_MARGIN_KM) -> bool:
    """True when (lat, lon) is inside `bbox` expanded by `margin_km` on every side.
    The latitude margin is a fixed km→deg; the longitude margin widens with
    latitude (deg per km grows toward the poles)."""
    import math
    south, north, west, east = bbox
    dlat = margin_km / 111.0
    coslat = max(0.01, math.cos(math.radians((south + north) / 2.0)))
    dlon = margin_km / (111.0 * coslat)
    return (south - dlat) <= lat <= (north + dlat) and \
           (west - dlon) <= lon <= (east + dlon)


def _scope_town(scope: str) -> str:
    """The scope's town token, normalised (accent-stripped, lowercase). "West
    Roxbury, MA" → "west roxbury"; "North End, Boston" → "north end"."""
    locality, _ = _scope_tokens(scope)
    return _strip_accents(locality).lower().strip()


# [LOCAL-805B] (`_ADDR_NON_TOWN_TOKENS`, `_is_locality_part`, `_first_locality_part`
# are defined above, next to `_parse_address_components`, and reused here.)


def _address_town(rec: Dict) -> str:
    """The town/locality named in a record's address, normalised. Reads the
    OSM-shaped address sub-dict first (city/town/suburb), then falls back to
    parsing the display_name / raw Serper address string. "" when no town is
    discernible.

    [LOCAL-805B] The raw-address fallback no longer takes the second comma-part
    blindly. A Serper address like "12 Đặng Trần Côn, P, Bến Thành, Hồ Chí Minh
    700000, Vietnam" has a noise segment ("P" — a truncated ward prefix) between
    the street and the real locality, and "…, Street, Bến Thành, …" has a literal
    "Street" tail on the road part; reading parts[1] returned "p" / "street" as the
    "town", and the town-name mismatch guard then dropped an in-scope place. The
    parser now skips the leading street part AND any non-town noise segment
    (street-type words, bare admin-unit prefixes, pure numbers/postcodes), and
    returns the first genuine locality part — "Bến Thành" in both cases. For a
    clean US address ("678 Washington St, Norwood, MA 02062") the first non-noise
    part after the street is still "Norwood" (unchanged). The structured-address
    read (`_parse_address_components`) applies the same skip, so a record whose
    `address.city` was set from the noise segment no longer reports it here."""
    addr = rec.get("address") or {}
    for key in ("city", "town", "municipality", "village"):
        v = addr.get(key)
        if v and _is_locality_part(str(v)):
            return _strip_accents(v).lower().strip()
    # Serper's raw address ("678 Washington St, Norwood, MA 02062" / "12 Đặng Trần
    # Côn, P, Bến Thành, Hồ Chí Minh 700000, Vietnam"). Skip the leading street
    # part, then take the first comma-part that is a real locality.
    raw = rec.get("_serper_address") or rec.get("display_name") or ""
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    loc = _first_locality_part(parts)
    return _strip_accents(loc).lower().strip() if loc else ""


def _scope_tokens(scope: str):
    """Locality + state tokens from a scope string, for stamping onto a Serper
    record's address so the gate's string-based in-scope check binds. "West
    Roxbury, MA" → ("West Roxbury", "MA")."""
    s = (scope or "").strip()
    if not s:
        return "", ""
    parts = [p.strip() for p in s.split(",") if p.strip()]
    locality = parts[0] if parts else ""
    state = parts[1] if len(parts) >= 2 else ""
    return locality, state


def _bind_in_scope(results: List[Dict], scope: str,
                   center: Optional[Tuple[float, float]], zoom: str,
                   bbox=None, near_me: bool = False) -> List[Dict]:
    """Keep only Serper records that lie inside the scope, then stamp the scope's
    locality/state onto each survivor so the gate's string signal check binds.

    [LOCAL-786] "Inside the scope" is decided by, in order:
      1. TOWN-NAME MISMATCH — a record whose address names a town DIFFERENT from the
         scope's town AND which also falls outside the bbox is rejected, even if a
         radius would allow it (Byblos "Norwood, MA" on a West Roxbury request).
      2. BOUNDING BOX — when the geocoder gave a bbox, a record must sit inside it
         (plus a 500 m margin). The bbox is tighter and truer than any fixed radius.
      3. RADIUS — otherwise the record must be within the scope-precision radius of
         `center`: NEIGHBOURHOOD ~2.5 km, CITY ~8/15 km, "near me" 3 km.

    Serper's `address` is often just the street ("1249 VFW Pkwy") with no city, so
    we stamp the scope's own locality/state onto every survivor — honest, because a
    record only survives once it has passed the geographic test above. A record with
    NO coordinates is kept only when there is no bbox and no centre to test against
    (we cannot prove it is outside).
    """
    locality, state = _scope_tokens(scope)
    scope_town = _scope_town(scope)
    parsed_bbox = _parse_bbox(bbox)
    if near_me:
        radius = _NEAR_ME_RADIUS_KM
    else:
        radius = _radius_for_precision(_scope_precision(scope), scope)

    out = []
    for r in results:
        # Record coordinates (may be missing).
        try:
            rlat = float(r["lat"])
            rlon = float(r["lon"])
            have_coords = True
        except (KeyError, ValueError, TypeError):
            rlat = rlon = None
            have_coords = False

        in_bbox = (parsed_bbox is not None and have_coords and
                   _inside_bbox(rlat, rlon, parsed_bbox))

        # 1) Town-name mismatch: a different town AND outside the bbox → reject.
        rec_town = _address_town(r)
        if (scope_town and rec_town and rec_town != scope_town and
                scope_town not in rec_town and rec_town not in scope_town and
                not in_bbox):
            continue

        # 2) Bounding box preference: when a bbox exists and the record has coords,
        #    it must be inside it (margin included).
        if parsed_bbox is not None and have_coords:
            if not in_bbox:
                continue
        # 3) Radius fallback (no usable bbox, or a near-me search): distance test.
        elif center is not None and have_coords:
            d = _haversine_km(center, (rlat, rlon))
            if d > radius:
                continue

        addr = dict(r.get("address") or {})
        # Stamp scope locality/state only where Serper left them blank, so a real
        # city/state Serper did provide is never overwritten.
        if locality and not addr.get("city"):
            addr["city"] = locality
        if locality and not addr.get("suburb"):
            addr["suburb"] = locality
        if state and not addr.get("state"):
            addr["state"] = state
        r = dict(r)
        r["address"] = addr
        # Also append the scope to display_name so the display-name fallback binds.
        dn = r.get("display_name") or r.get("name") or ""
        scope_str = ", ".join(t for t in (locality, state) if t)
        if scope_str and scope_str.lower() not in dn.lower():
            r["display_name"] = f"{dn}, {scope_str}" if dn else scope_str
        out.append(r)
    return out


def _parse_coords(value) -> Optional[Tuple[float, float]]:
    """[LOCAL-788] Parse a stored coordinate value into (lat, lon), or None.

    Accepts a "lat, lon" / "lat,lon" string (how the stop pool stores it) or a
    (lat, lon) tuple/list. Returns None when the value is empty, malformed, or
    out of range — a row with no usable coordinates is NOT a place we can
    geographically test (the caller keeps it; see ``row_in_scope``)."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (tuple, list)):
            lat, lon = float(value[0]), float(value[1])
        else:
            parts = [p.strip() for p in str(value).split(",")]
            if len(parts) < 2:
                return None
            lat, lon = float(parts[0]), float(parts[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def row_in_scope(coordinates, address: str, scope: str,
                 scope_center: Optional[Tuple[float, float]] = None,
                 scope_bbox=None,
                 near: Optional[Tuple[float, float]] = None) -> Tuple[bool, str, float]:
    """[LOCAL-788] Does a single already-known place lie inside ``scope``?

    This is the SAME scope test LOCAL-786's ``_bind_in_scope`` applies to a fresh
    Serper lookup — radius by scope precision, bbox + 500 m margin, near-me 3 km,
    and the town-name mismatch reject — reused for a REUSED (pooled or mined) stop
    so a place that was researched for one request cannot be silently carried into
    a tighter-scoped request it does not belong to (tour 454: Byblos, Norwood, on a
    West Roxbury request). It re-runs the geographic gate ONLY; it never sources or
    bills.

    Args:
        coordinates: the stop's coordinates, as a "lat, lon" string (pool shape),
            a (lat, lon) pair, or "" when the stop has none.
        address: the stop's free-text address (used for the town-name mismatch).
        scope: the request's scope string (the tour's venue/area, e.g.
            "West Roxbury, MA").
        scope_center: the scope's geocoded centre (lat, lon), for the radius test.
        scope_bbox: the scope's geocoded bounding box [south, north, west, east],
            preferred over the radius when present.
        near: device coordinates (lat, lon) for a "near me" request — binds the
            3 km near-me radius to the device rather than the scope centre.

    Returns ``(keep, reason, distance_km)``:
        keep         — True when the stop is in scope (or cannot be proven out of
                       scope because it has no coordinates and there is nothing to
                       test against — LOCAL-786's "no coords" rule).
        reason       — "" when kept; otherwise one of "town-name mismatch (<town>)",
                       "outside bbox", or "<km> km > <radius> km radius".
        distance_km  — distance to the scope centre / device in km (inf when it
                       cannot be computed). For the reject log line.

    A stop with NO coordinates is kept (we cannot prove it is outside), matching
    ``_bind_in_scope``'s treatment of a coordinate-less record.
    """
    coords = _parse_coords(coordinates)
    near_me = near is not None
    if near_me:
        try:
            center = (float(near[0]), float(near[1]))
        except (TypeError, ValueError, IndexError):
            center = None
        radius = _NEAR_ME_RADIUS_KM
        parsed_bbox = None  # near-me binds to the device, not the scope's bbox
    else:
        center = None
        if scope_center is not None:
            try:
                center = (float(scope_center[0]), float(scope_center[1]))
            except (TypeError, ValueError, IndexError):
                center = None
        radius = _radius_for_precision(_scope_precision(scope), scope)
        parsed_bbox = _parse_bbox(scope_bbox)

    # No coordinates: nothing to test against → keep (cannot prove it is outside).
    if coords is None:
        return True, "", float("inf")
    rlat, rlon = coords

    dist = _haversine_km(center, (rlat, rlon)) if center is not None else float("inf")
    in_bbox = (parsed_bbox is not None and _inside_bbox(rlat, rlon, parsed_bbox))

    # 1) Town-name mismatch: a different town AND outside the bbox → reject.
    scope_town = _scope_town(scope)
    rec_town = _address_town({"_serper_address": address or "",
                              "display_name": address or ""})
    if (scope_town and rec_town and rec_town != scope_town and
            scope_town not in rec_town and rec_town not in scope_town and
            not in_bbox):
        return False, f"town-name mismatch ({rec_town})", dist

    # 2) Bounding box preference.
    if parsed_bbox is not None:
        if not in_bbox:
            return False, "outside bbox", dist
        return True, "", dist

    # 3) Radius fallback.
    if center is not None and dist > radius:
        return False, f"{dist:.1f} km > {radius:.1f} km radius", dist

    return True, "", dist


def places_search(query: str, scope: str,
                  near: Optional[Tuple[float, float]] = None,
                  limit: int = 10,
                  scope_center: Optional[Tuple[float, float]] = None,
                  scope_bbox=None) -> List[Dict]:
    """Search for places matching `query` within `scope`.

    Uses Serper Places when SERP_API_KEY is set and SERP_PROVIDER=serper; otherwise
    returns [] (the Nominatim path lives in stop_existence_gate and is reached via
    map_lookup). Always sends an `ll` centre — device coords for "near me" (`near`),
    else the `scope_center` the caller geocoded — with a zoom matching the scope,
    because Serper Places IGNORES the town written in the query (LEAD probe).

    Results are bound to the scope ([LOCAL-786]): the geocoder's bounding box
    (`scope_bbox`, when given) is preferred over a fixed radius; otherwise a
    scope-PRECISION radius binds (NEIGHBOURHOOD ~2.5 km, CITY ~8/15 km, "near me"
    3 km). A record whose address names a different town and which falls outside the
    bbox is rejected outright. Each survivor is stamped with the scope's
    locality/state (only where Serper left them blank) so the gate's in-scope signal
    check binds.

    Returns at most `limit` normalised OSM-shaped place dicts. Identical
    (query, ll) within 24 h reuse the cached result, so a repeated tour does not
    re-bill. The caller still applies its own in-scope distance / signal check and
    the cuisine match — this function sources, normalises and scope-binds.
    """
    q = (query or "").strip()
    scope = (scope or "").strip()
    if not q:
        return []
    if not serper_places_enabled():
        return []
    zoom = _zoom_for_scope(scope)
    center = None
    near_me = False
    ll = _ll_from_near(near, scope)
    if near:
        try:
            center = (float(near[0]), float(near[1]))
            near_me = True
        except (TypeError, ValueError, IndexError):
            center = None
    if ll is None and scope_center:
        try:
            center = (float(scope_center[0]), float(scope_center[1]))
            ll = f"@{center[0]},{center[1]},{zoom}"
        except (TypeError, ValueError, IndexError):
            center = None
            ll = None
    cache_key = f"serper_places|{q.lower()}|{ll or ''}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached[:max(0, limit)]
    raw = _serper_places_call(q, ll)
    # Near-me binds to the device radius (bbox is the scope's, not the device's).
    results = _bind_in_scope(raw, scope, center, zoom,
                             bbox=(None if near_me else scope_bbox),
                             near_me=near_me)
    _cache_put(cache_key, results)
    return results[:max(0, limit)]


class _Resp:
    """A minimal requests.Response-shaped object: the gate reads only .json()."""
    __slots__ = ("_data",)

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def map_lookup(params: dict, context: str = "",
               scope_center: Optional[Tuple[float, float]] = None,
               near: Optional[Tuple[float, float]] = None,
               scope_bbox=None):
    """Drop-in for stop_existence_gate._nominatim_request.

    Takes the SAME Nominatim-style `params` (notably `q`), and when Serper Places
    is enabled, answers it with Serper Places (sending `ll` so the town is honoured)
    returning a response whose .json() yields OSM-shaped records. When Serper is NOT
    enabled, returns None so the caller falls back to the real Nominatim request.

    `scope_bbox` ([LOCAL-786]) is the scope's geocoded bounding box
    ([south, north, west, east]); when present it is preferred over the fixed radius
    in the scope-binding step, so a place in a neighbouring town is dropped even when
    it would fall inside a radius.

    The caller is responsible for the in-scope filter (it already is — the gate's
    scope-signal/distance checks run on whatever records come back), so map_lookup
    only SOURCES. A Serper failure returns an empty-result response (a successful-
    but-empty answer), never None, so the gate treats it as "searched, none found"
    rather than falling through to a second provider for the same query.
    """
    if not serper_places_enabled():
        return None
    q = (params or {}).get("q") or ""
    results = places_search(q, scope=_scope_from_query(q), near=near,
                            limit=25, scope_center=scope_center,
                            scope_bbox=scope_bbox)
    return _Resp(results)


def _scope_from_query(q: str) -> str:
    """Pull the scope text out of a Nominatim-style query. The gate builds queries
    like "<cuisine> restaurants in West Roxbury, MA" or "<name>, West Roxbury, MA";
    the scope is what follows the last " in " (bulk search) or the first comma
    (per-name verify). Best-effort — only used to pick the `ll` zoom."""
    s = (q or "").strip()
    if not s:
        return ""
    low = s.lower()
    idx = low.rfind(" in ")
    if idx != -1:
        return s[idx + 4:].strip()
    if "," in s:
        return s.split(",", 1)[1].strip()
    return s
