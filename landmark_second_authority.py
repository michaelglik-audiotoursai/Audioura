"""landmark_second_authority.py — LOCAL-858B item 2.

A SECOND authority for a well-known landmark's coordinate, used when the primary
Wikidata-P625 lookup (``wikidata_landmark_lookup.lookup``) returns nothing —
Wikidata unreachable from Cloud Run egress, a 429 that never cleared, or no
in-scope P625. The cloud tour-532 failure showed the primary alone is not enough:
when it comes back empty the stop keeps the model's centroid guess and ships it.

CHAIN (ticket item 2):
  1. Serper ``/places`` by the landmark NAME, biased to the city centre, kept only
     when the hit's NAME matches the stop and its coordinate is INSIDE the city
     box / within the metro radius. ≈ $0.001, metered through the existing
     ``places_search`` door (so the budget meter sees it).
  2. Nominatim by name, same in-scope + name-match filter (free).

Results are CACHED exactly like the P625 lookup — the same
``landmark_coord_cache`` table (``wikidata_landmark_lookup._cache_get/_put``),
under a distinct language tag so a P625 row and a second-authority row never
collide. A repeat tour costs nothing and never re-hits the network.

Pure-logic seams (``places_fn``, ``nominatim_fn``) are injectable so the module
is unit-tested fully offline.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import Callable, List, Optional, Sequence, Tuple

__all__ = ["lookup_second_authority", "name_matches"]

# Same generous cross-city identity bound the P625 lookup uses when no bbox is
# known: an in-scope landmark is within this many km of the city centre.
_METRO_RADIUS_KM = float(os.environ.get("LANDMARK_METRO_RADIUS_KM", "35.0"))
# Pad a razor-tight geocoder bbox before the in-scope test (≈2 km), mirroring
# wikidata_landmark_lookup._BBOX_PAD_DEG.
_CITY_RADIUS_KM = float(os.environ.get("LANDMARK_CITY_RADIUS_KM", "15.0"))
_BBOX_PAD_DEG = float(os.environ.get("LANDMARK_BBOX_PAD_DEG", "0.02"))

# A dedicated language tag for second-authority cache rows so they never collide
# with the P625 rows (keyed by name|language|scope).
_SECOND_AUTHORITY_LANG = "__2nd__"


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# Honorifics / city-district qualifiers dropped from a name's distinctive core,
# mirroring pin_snap._name_distinctive_tokens so the two matchers agree.
_DROP_TOKENS = {
    "saigon", "hcmc", "ho", "chi", "minh", "city", "vietnam", "hanoi", "old",
    "new", "central", "district", "downtown", "sai", "gon", "the", "of", "and",
    "a", "an", "de", "la", "le", "temple", "market", "lake", "church",
    "cathedral", "pagoda", "museum", "opera", "house", "square", "park",
}


def _distinctive_tokens(name: str) -> set:
    core = {w for w in _fold(name).split() if len(w) >= 2}
    return {t for t in core if t not in _DROP_TOKENS}


def name_matches(stop_name: str, hit_name: str) -> bool:
    """[LOCAL-858B] True when a geocoder/Places hit NAME strongly matches the stop
    — they share a distinctive proper-noun core, OR one folded name contains the
    other. A bare-name hit for a DIFFERENT building shares no distinctive core and
    is rejected (the same guard pin_snap applies to a generic reference). When the
    stop name carries NO distinctive token (it is all generic class words, e.g.
    "Opera House"), fall back to folded containment so such landmarks still match
    their own listing."""
    a = _distinctive_tokens(stop_name)
    b = _distinctive_tokens(hit_name)
    fa, fb = _fold(stop_name), _fold(hit_name)
    if a and b and (a <= b or b <= a):
        return True
    if fa and fb and (fa in fb or fb in fa):
        return True
    return False


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _in_scope(pt: Tuple[float, float],
              scope_center: Optional[Tuple[float, float]],
              scope_bbox: Optional[Sequence[float]]) -> bool:
    """In-scope identity test: inside the (padded) bbox, else within the metro
    radius of the centre. With neither signal, accept (the caller's own pin_snap
    centroid / scope-sanity bounds still apply)."""
    # [LEAD 858B review] The centre radius ALWAYS applies when a centre is known:
    # HCMC's administrative bbox spans ~350 km, so "inside the bbox" alone let a
    # same-name temple 25 km away through (test_local791e Thien Hau). With no
    # centre and no bbox there is no identity signal at all -> refuse.
    if scope_center and _haversine_km(pt, scope_center) > _CITY_RADIUS_KM:
        return False
    if scope_bbox and len(scope_bbox) >= 4:
        try:
            south, north, west, east = (float(scope_bbox[0]), float(scope_bbox[1]),
                                        float(scope_bbox[2]), float(scope_bbox[3]))
            if (south - _BBOX_PAD_DEG) <= pt[0] <= (north + _BBOX_PAD_DEG) and \
               (west - _BBOX_PAD_DEG) <= pt[1] <= (east + _BBOX_PAD_DEG):
                return True
        except (TypeError, ValueError):
            pass
        return bool(scope_center)
    return bool(scope_center)


def _default_places_fn(name: str, scope: str,
                       scope_center: Optional[Tuple[float, float]],
                       scope_bbox: Optional[Sequence[float]]) -> List[dict]:
    """Live Serper /places, via the metered ``places_search`` door. [] on any
    failure or when Serper is not configured.

    [LOCAL-858B] ``places_search`` is passed an EMPTY scope on purpose: its
    restaurant/business scope-binding (the town-name mismatch reject, the
    neighbourhood radius) is tuned for a dining refill and, with the cloud's
    city-LESS scope string ("Ben Thanh Market and Saigon Opera House walk"), it
    treated that whole phrase as the "town" and REJECTED a genuine Ben Thanh Market
    hit whose address town was "Bến Thành / Ho Chi Minh City". We still bias the
    search to the city with ``scope_center`` (the Serper ``ll``), and this module
    applies its OWN in-scope identity test (``_in_scope``: padded bbox, else metro
    radius) plus the name match — so a same-name place in another city is still
    refused, without the dining town-match dropping the right one."""
    try:
        from places_search import places_search as _ps
        return _ps(name, scope="", scope_center=scope_center,
                   scope_bbox=None, limit=8) or []
    except Exception:
        return []


def _default_nominatim_fn(name: str, scope: str) -> List[Tuple[float, float, str]]:
    """Live Nominatim by "<name>, <scope-city>", via geocode_stops. Returns a
    one-element list [(lat, lng, display_name)] or []."""
    try:
        from geocode_stops import geocode_detailed as _gcd
    except Exception:
        return []
    q = f"{name}, {scope}".strip(" ,") if scope else name
    try:
        det = _gcd(q)
    except Exception:
        det = None
    if not det:
        return []
    return [(det["lat"], det["lng"], det.get("display_name") or name)]


def lookup_second_authority(
    name: str,
    scope: str = "",
    scope_center: Optional[Tuple[float, float]] = None,
    scope_bbox: Optional[Sequence[float]] = None,
    places_fn: Optional[Callable] = None,
    nominatim_fn: Optional[Callable] = None,
    use_cache: bool = True,
) -> Optional[Tuple[float, float, str]]:
    """Resolve a landmark NAME to a coordinate via the SECOND authority chain.

    Returns ``(lat, lng, source)`` — source "serper_places" or "nominatim" — for
    the first name-matched, in-scope hit, or None. Cached like the P625 lookup
    (same ``landmark_coord_cache`` table, distinct language tag). ``places_fn`` /
    ``nominatim_fn`` are injectable for offline tests; the live defaults go through
    the metered Serper door and geocode_stops.
    """
    nm = (name or "").strip()
    if not nm:
        return None

    _net_default = places_fn is None and nominatim_fn is None
    if use_cache and _net_default:
        try:
            from wikidata_landmark_lookup import _cache_get as _cg
            cached = _cg(nm, _SECOND_AUTHORITY_LANG, scope)
        except Exception:
            cached = None
        if cached is not None:
            coord, src = cached
            if coord is None:
                return None
            return (coord[0], coord[1], src or "serper_places")

    pfn = places_fn or (lambda n: _default_places_fn(n, scope, scope_center,
                                                      scope_bbox))
    nfn = nominatim_fn or (lambda n: _default_nominatim_fn(n, scope))

    hit: Optional[Tuple[float, float, str]] = None
    reached = False

    # 1) Serper /places — name-matched, in-box.
    try:
        rows = pfn(nm) or []
        if rows:
            reached = True
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                lat = float(r.get("lat") if r.get("lat") is not None
                            else r.get("latitude"))
                lng = float(r.get("lon") if r.get("lon") is not None
                            else r.get("longitude"))
            except (TypeError, ValueError):
                continue
            hit_name = (r.get("name") or r.get("title") or "")
            if not name_matches(nm, hit_name):
                continue
            if _in_scope((lat, lng), scope_center, scope_bbox):
                hit = (lat, lng, "serper_places")
                break
    except Exception:
        pass

    # 2) Nominatim fallback.
    if hit is None:
        try:
            rows = nfn(nm) or []
            if rows:
                reached = True
            for r in rows:
                try:
                    lat, lng = float(r[0]), float(r[1])
                except (TypeError, ValueError, IndexError):
                    continue
                hit_name = r[2] if len(r) > 2 else nm
                if not name_matches(nm, hit_name):
                    continue
                if _in_scope((lat, lng), scope_center, scope_bbox):
                    hit = (lat, lng, "nominatim")
                    break
        except Exception:
            pass

    if use_cache and _net_default:
        try:
            from wikidata_landmark_lookup import _cache_put as _cp
            if hit:
                _cp(nm, _SECOND_AUTHORITY_LANG, scope, (hit[0], hit[1]), hit[2])
            elif reached:
                _cp(nm, _SECOND_AUTHORITY_LANG, scope, None, "")
        except Exception:
            pass

    return hit
