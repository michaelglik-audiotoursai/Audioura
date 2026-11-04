"""[LOCAL-863] Resolve a tour request's CITY reliably, and sanity-check it.

Wave 27 (tour 534, rolled back): "Sophia's biking tour in Ho Chi Minh City,
Vietnam" geocoded its centre to (20.9103, 105.5750), a feature named after Hồ
Chí Minh near HANOI, ~1,150 km from HCMC. The scope bbox then fell back to the
WHOLE OF VIETNAM. Every user-stop name lookup missed (25 km from a Hanoi
centre), so even high-confidence share-link hits were thrown away.

This module provides:

* a small CURATED table of major tour cities (centre + bbox + country), matched
  on accent-folded whole-word aliases. It is offline and deterministic, and is
  the first answer for those cities;
* ``requested_country`` to read the country named in the request;
* ``point_in_country`` as a coarse country-bbox sanity check;
* ``is_attraction_hit`` / ``is_country_level_hit`` to reject a Nominatim row
  that is a mausoleum / statue / trail / museum, or a whole country / state,
  when a CITY centre was asked for;
* ``resolve_city_scope``: curated first, then Nominatim restricted to
  ``featuretype=city`` + ``countrycodes``, keeping only a row whose
  ``addresstype`` is city-like, which is not an attraction, and which lies inside
  the requested country.

Pure helpers never raise. Network is injectable (``fetch``) so tests stay offline.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


def fold(text) -> str:
    """Lower-case, strip diacritics (đ→d), collapse whitespace."""
    s = str(text or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# ── Countries ───────────────────────────────────────────────────────────────
# Coarse [south, north, west, east] boxes. Only used to REJECT an obviously
# wrong-country hit; generous margins are deliberate.
COUNTRY_BBOX: Dict[str, Tuple[float, float, float, float]] = {
    "vn": (8.0, 23.6, 102.0, 110.0),
    "us": (18.0, 72.0, -180.0, -66.0),
    "fr": (41.0, 51.5, -5.5, 10.0),
    "nl": (50.6, 53.7, 3.2, 7.3),
    "gb": (49.8, 61.0, -8.7, 2.0),
    "it": (35.4, 47.2, 6.5, 18.6),
    "es": (35.9, 43.9, -9.5, 4.4),
    "de": (47.2, 55.1, 5.8, 15.1),
    "pt": (36.8, 42.2, -9.6, -6.1),
    "th": (5.6, 20.5, 97.3, 105.7),
    "kh": (10.4, 14.7, 102.3, 107.7),
    "jp": (24.0, 45.6, 122.9, 146.0),
}

# Alias (folded) → ISO-2. Whole-word matched against the folded request.
COUNTRY_ALIASES: Dict[str, str] = {
    "vietnam": "vn", "viet nam": "vn",
    "usa": "us", "united states": "us", "united states of america": "us",
    "u s a": "us",
    "france": "fr",
    "netherlands": "nl", "the netherlands": "nl", "holland": "nl",
    "united kingdom": "gb", "uk": "gb", "england": "gb", "scotland": "gb",
    "italy": "it", "spain": "es", "germany": "de", "portugal": "pt",
    "thailand": "th", "cambodia": "kh", "japan": "jp",
}

# US state names/abbreviations imply 'us' (Boston, MA).
_US_STATE_TOKENS = {
    "ma", "massachusetts", "ny", "new york", "ca", "california", "il",
    "illinois", "wa", "washington", "pa", "pennsylvania", "dc",
}


def _has_word(folded_text: str, folded_alias: str) -> bool:
    if not folded_alias:
        return False
    return re.search(r"(?:^| )" + re.escape(folded_alias) + r"(?: |$)",
                     folded_text) is not None


def is_country_name(text) -> bool:
    """True when ``text`` is JUST a country name ("Vietnam", "France")."""
    return fold(text) in COUNTRY_ALIASES


def requested_country(*texts) -> Optional[str]:
    """ISO-2 of the country named in the request texts, or None."""
    for t in texts:
        ft = fold(t)
        if not ft:
            continue
        for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
            if _has_word(ft, alias):
                return COUNTRY_ALIASES[alias]
        # "Boston, MA" style: a trailing US state token.
        parts = [fold(p) for p in str(t).split(",") if p.strip()]
        if len(parts) >= 2 and parts[-1] in _US_STATE_TOKENS:
            return "us"
    return None


def point_in_country(lat: float, lng: float, cc: Optional[str]) -> bool:
    """True when (lat, lng) lies in the coarse bbox of ``cc``. An unknown /
    missing country cannot refute the point (returns True)."""
    if not cc:
        return True
    box = COUNTRY_BBOX.get(cc.lower())
    if not box:
        return True
    s, n, w, e = box
    try:
        return s <= float(lat) <= n and w <= float(lng) <= e
    except (TypeError, ValueError):
        return False


# ── Curated cities ──────────────────────────────────────────────────────────
# name, cc, (lat, lng), [south, north, west, east], aliases (folded, whole-word)
# Centres are city-centre reference points (e.g. HCMC = District 1 / Nguyen Hue,
# Hanoi = Hoan Kiem). Bboxes cover the urban area a city tour could reach, NOT
# the full provincial boundary.
_CURATED: List[Dict] = [
    {"name": "Ho Chi Minh City", "cc": "vn", "center": (10.7769, 106.7009),
     "bbox": (10.70, 10.88, 106.60, 106.82),
     "aliases": ("ho chi minh city", "hcmc", "saigon", "sai gon",
                 "tp hcm", "tphcm", "thanh pho ho chi minh", "hcm city")},
    {"name": "Hanoi", "cc": "vn", "center": (21.0285, 105.8542),
     "bbox": (20.95, 21.10, 105.75, 105.92),
     "aliases": ("hanoi", "ha noi")},
    {"name": "Da Nang", "cc": "vn", "center": (16.0544, 108.2022),
     "bbox": (15.95, 16.15, 108.10, 108.32),
     "aliases": ("da nang", "danang")},
    {"name": "Hoi An", "cc": "vn", "center": (15.8801, 108.3380),
     "bbox": (15.84, 15.93, 108.28, 108.42),
     "aliases": ("hoi an",)},
    {"name": "Nha Trang", "cc": "vn", "center": (12.2388, 109.1967),
     "bbox": (12.15, 12.32, 109.12, 109.25),
     "aliases": ("nha trang",)},
    {"name": "Mui Ne", "cc": "vn", "center": (10.9333, 108.2833),
     "bbox": (10.90, 10.98, 108.20, 108.40),
     "aliases": ("mui ne",)},
    {"name": "Phan Thiet", "cc": "vn", "center": (10.9289, 108.1021),
     "bbox": (10.88, 10.98, 108.03, 108.17),
     "aliases": ("phan thiet",)},
    {"name": "Hue", "cc": "vn", "center": (16.4637, 107.5909),
     "bbox": (16.40, 16.52, 107.52, 107.65),
     # 'hue' only with a Vietnam context, see _ALIAS_NEEDS_COUNTRY.
     "aliases": ("hue",)},
    {"name": "Boston", "cc": "us", "center": (42.3601, -71.0589),
     "bbox": (42.23, 42.40, -71.19, -70.99),
     "aliases": ("boston",)},
    {"name": "Paris", "cc": "fr", "center": (48.8566, 2.3522),
     "bbox": (48.81, 48.91, 2.22, 2.47),
     "aliases": ("paris",)},
    {"name": "Nice", "cc": "fr", "center": (43.7102, 7.2620),
     "bbox": (43.65, 43.76, 7.18, 7.33),
     "aliases": ("nice",)},
    {"name": "Amsterdam", "cc": "nl", "center": (52.3676, 4.9041),
     "bbox": (52.28, 52.43, 4.73, 5.07),
     "aliases": ("amsterdam",)},
]

# Aliases that are ordinary words; accept them only when the request also names
# the city's country ("a nice walk" must not resolve to Nice, France).
_ALIAS_NEEDS_COUNTRY = {"nice", "hue"}


def find_curated_city(*texts) -> Optional[Dict]:
    """The curated city named in ``texts`` (longest alias wins), or None.

    A city whose country differs from the request's explicit country is
    rejected (Paris, Texas will not resolve to Paris, France)."""
    cc_req = requested_country(*texts)
    best = None
    best_len = 0
    for t in texts:
        ft = fold(t)
        if not ft:
            continue
        for city in _CURATED:
            for alias in city["aliases"]:
                if len(alias) <= best_len or not _has_word(ft, alias):
                    continue
                if alias in _ALIAS_NEEDS_COUNTRY and cc_req != city["cc"]:
                    continue
                if cc_req and cc_req != city["cc"]:
                    continue
                best, best_len = city, len(alias)
    if not best:
        return None
    return {
        "name": best["name"], "country_code": best["cc"],
        "lat": best["center"][0], "lng": best["center"][1],
        "bbox": list(best["bbox"]), "source": "curated",
    }


def curated_is_most_specific(scope) -> Optional[Dict]:
    """The curated city when it IS the scope's most specific (leading) comma
    segment, e.g. "Ho Chi Minh City, Vietnam" or "Boston, MA". For "West
    Roxbury, Boston, MA" it returns None, because a sub-area is more specific
    and must keep its own (tighter) geocode."""
    parts = [p.strip() for p in str(scope or "").split(",") if p.strip()]
    if not parts:
        return None
    hit = find_curated_city(parts[0], scope)
    if not hit:
        return None
    lead = fold(parts[0])
    for city in _CURATED:
        if city["name"] == hit["name"] and lead in city["aliases"]:
            return hit
    return None


def bbox_as_nominatim(bbox: Sequence[float]) -> List[str]:
    """[s, n, w, e] floats → Nominatim-style list of strings."""
    return [str(float(x)) for x in bbox]


# ── Nominatim row checks ────────────────────────────────────────────────────
_CITY_ADDRESSTYPES = {
    "city", "municipality", "town", "village", "suburb", "city_district",
    "borough", "quarter", "neighbourhood", "hamlet",
}
_COUNTRY_LEVEL = {
    "country", "continent", "ocean", "sea", "state", "province", "region",
    "county", "state_district",
}
_ATTRACTION_CLASSES = {
    "tourism", "historic", "amenity", "leisure", "building", "man_made",
    "shop", "craft", "office", "highway", "railway", "aeroway", "natural",
    "waterway",
}
_ATTRACTION_TYPES = {
    "attraction", "monument", "memorial", "statue", "mausoleum", "museum",
    "artwork", "viewpoint", "castle", "ruins", "tomb", "grave_yard",
    "path", "footway", "track", "trail", "cycleway", "bridleway",
    "park", "garden", "place_of_worship",
}


def _row_class(row: Dict) -> str:
    return str(row.get("category") or row.get("class") or "").strip().lower()


def is_country_level_hit(row: Dict) -> bool:
    if not isinstance(row, dict):
        return False
    at = str(row.get("addresstype") or "").strip().lower()
    typ = str(row.get("type") or "").strip().lower()
    if at in _COUNTRY_LEVEL:
        return True
    return _row_class(row) == "boundary" and typ in _COUNTRY_LEVEL


def is_attraction_hit(row: Dict) -> bool:
    """True for a mausoleum / statue / trail / museum / park and similar
    features, which are never a CITY centre."""
    if not isinstance(row, dict):
        return False
    at = str(row.get("addresstype") or "").strip().lower()
    if at in _CITY_ADDRESSTYPES:
        return False
    cls = _row_class(row)
    typ = str(row.get("type") or "").strip().lower()
    return cls in _ATTRACTION_CLASSES or typ in _ATTRACTION_TYPES


def is_city_hit(row: Dict) -> bool:
    """A Nominatim row that is a city/town-level place (by addresstype, or a
    place=city|town|... node), not a country and not an attraction."""
    if not isinstance(row, dict):
        return False
    if is_country_level_hit(row) or is_attraction_hit(row):
        return False
    at = str(row.get("addresstype") or "").strip().lower()
    typ = str(row.get("type") or "").strip().lower()
    cls = _row_class(row)
    if at in _CITY_ADDRESSTYPES:
        return True
    if cls in ("place", "boundary") and typ in (
            _CITY_ADDRESSTYPES | {"administrative"}):
        return True
    return False


def row_ok_for_country(row: Dict, cc: Optional[str]) -> bool:
    try:
        return point_in_country(float(row["lat"]), float(row["lon"]), cc)
    except (KeyError, TypeError, ValueError):
        return False


# ── Resolver ────────────────────────────────────────────────────────────────
_REQUEST_NOISE = re.compile(
    r"^.*?\b(?:tour|walk|ride|trip|crawl|route|itinerary)\b\s+(?:in|of|around|"
    r"through|across|at)\s+", re.IGNORECASE)


def city_candidates(*texts) -> List[str]:
    """City-name candidates from request/scope text: each text's comma tails
    with a leading "<anything> tour in" stripped and a trailing country
    dropped. Most-specific first, de-duplicated."""
    out: List[str] = []
    for t in texts:
        if not t:
            continue
        s = _REQUEST_NOISE.sub("", str(t)).strip(" ,")
        parts = [p.strip() for p in s.split(",") if p.strip()]
        parts = [p for p in parts if not is_country_name(p)]
        for p in parts:
            if p and p.lower() not in (x.lower() for x in out):
                out.append(p)
    return out


def resolve_city_scope(*texts, fetch: Optional[Callable[[Dict], list]] = None,
                       log: Callable[[str], None] = print) -> Optional[Dict]:
    """Resolve the CITY of a request.

    Order: the curated table, then Nominatim (via ``fetch(params)->rows``) with
    ``featuretype=city`` and the requested ``countrycodes``. A Nominatim row is
    accepted only when it is a city-level place, NOT an attraction, NOT a
    country/state, and INSIDE the requested country. Returns ``{name,
    country_code, lat, lng, bbox, source}`` or None. Never raises."""
    try:
        cur = find_curated_city(*texts)
        if cur:
            log(f"  [LOCAL-863] city resolved {cur['name']!r} "
                f"center=({cur['lat']:.4f}, {cur['lng']:.4f}) source=curated")
            return cur
        if fetch is None:
            return None
        cc = requested_country(*texts)
        for cand in city_candidates(*texts):
            params = {"q": cand, "format": "jsonv2", "limit": "5",
                      "featuretype": "city", "accept-language": "en"}
            if cc:
                params["countrycodes"] = cc
            try:
                rows = fetch(params) or []
            except Exception:
                rows = []
            for row in rows:
                if not is_city_hit(row):
                    continue
                if not row_ok_for_country(row, cc):
                    log(f"  [LOCAL-863] city candidate {cand!r} rejected: "
                        f"outside requested country {cc!r}")
                    continue
                try:
                    lat, lng = float(row["lat"]), float(row["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                bb = row.get("boundingbox")
                bbox = [float(x) for x in bb] if bb and len(bb) >= 4 else None
                log(f"  [LOCAL-863] city resolved {cand!r} "
                    f"center=({lat:.4f}, {lng:.4f}) source=nominatim_city")
                return {"name": cand, "country_code": cc, "lat": lat,
                        "lng": lng, "bbox": bbox, "source": "nominatim_city"}
        return None
    except Exception:
        return None


def center_is_sane(lat, lng, *texts) -> bool:
    """A resolved centre must lie inside the request's country and, when the
    request names a curated city, within 25 km of that city's centre."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if not point_in_country(lat, lng, requested_country(*texts)):
        return False
    cur = find_curated_city(*texts)
    if cur:
        return haversine_km(lat, lng, cur["lat"], cur["lng"]) <= 25.0
    return True


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
