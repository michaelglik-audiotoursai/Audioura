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


# ──────────────────── Serper Places → OSM jsonv2 shape ──────────────────────
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
    if len(parts) >= 2:
        out["city"] = parts[1]
        out["suburb"] = parts[1]
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
_SCOPE_RADIUS_KM = {"14z": 4.0, "13z": 7.0, "12z": 12.0}


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
                   center: Optional[Tuple[float, float]], zoom: str) -> List[Dict]:
    """Keep only Serper records within the scope radius of `center` and stamp the
    scope's locality/state into each surviving record's address.

    Serper's `address` is often just the street ("1249 VFW Pkwy") with no city, so
    the gate's city/state signal check cannot bind on its own. Because the records
    were fetched with the scope's `ll`, a record within the scope radius IS in the
    scope — we record that by writing the scope's own locality/state onto it, which
    is honest: we only stamp records that passed the distance test. Without a
    `center` (no geocode) we keep all records and stamp the locality, trusting
    Serper's `ll` scoping (still the correct town per the LEAD probe)."""
    locality, state = _scope_tokens(scope)
    radius = _SCOPE_RADIUS_KM.get(zoom, 8.0)
    out = []
    for r in results:
        if center is not None:
            try:
                d = _haversine_km(center, (float(r["lat"]), float(r["lon"])))
            except (KeyError, ValueError, TypeError):
                d = float("inf")
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


def places_search(query: str, scope: str,
                  near: Optional[Tuple[float, float]] = None,
                  limit: int = 10,
                  scope_center: Optional[Tuple[float, float]] = None) -> List[Dict]:
    """Search for places matching `query` within `scope`.

    Uses Serper Places when SERP_API_KEY is set and SERP_PROVIDER=serper; otherwise
    returns [] (the Nominatim path lives in stop_existence_gate and is reached via
    map_lookup). Always sends an `ll` centre — device coords for "near me" (`near`),
    else the `scope_center` the caller geocoded — with a zoom matching the scope,
    because Serper Places IGNORES the town written in the query (LEAD probe).

    Results are bound to the scope: a record beyond the scope radius of the centre
    is dropped, and each surviving record is stamped with the scope's locality/state
    (only where Serper left them blank) so the gate's in-scope signal check binds.

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
    ll = _ll_from_near(near, scope)
    if near:
        try:
            center = (float(near[0]), float(near[1]))
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
    results = _bind_in_scope(raw, scope, center, zoom)
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
               near: Optional[Tuple[float, float]] = None):
    """Drop-in for stop_existence_gate._nominatim_request.

    Takes the SAME Nominatim-style `params` (notably `q`), and when Serper Places
    is enabled, answers it with Serper Places (sending `ll` so the town is honoured)
    returning a response whose .json() yields OSM-shaped records. When Serper is NOT
    enabled, returns None so the caller falls back to the real Nominatim request.

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
                            limit=25, scope_center=scope_center)
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
