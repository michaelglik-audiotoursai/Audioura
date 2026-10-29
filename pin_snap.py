"""pin_snap.py — LOCAL-791C item 2.

Walking-stop coordinates are LLM-written and the 791B pin_proof table measured
them 0.5–6 km from the real place (Giac Lam Pagoda 2304 m, Xa Loi Pagoda 5956 m).
pin_proof PROVES the distance; this module FIXES it.

WHAT (ticket): for EVERY stop that has an IN-SCOPE reference — the same
Serper-Places / Nominatim / Wikidata P625 lookups pin_proof uses — snap the stop's
coordinate to that reference when the shipped pin is more than ``SNAP_THRESHOLD_M``
(150 m) away, and log ``[LOCAL-791C] pin snap <title> <m>``. A stop is left
unsnapped ONLY when no in-scope reference exists; that too is logged. After the
snap, a re-run of pin_proof should report ≤ 100 m for every referenced stop.

WHY a 150 m threshold and a 100 m target: 150 m is the shipped-pin error we act
on (anything closer is already a good pin and not worth a reference that may itself
sit on a different door of the same building); the reference we snap TO is the
authority pin_proof measures against, so a snapped stop lands ON it (0 m) and
clears the 100 m target. We never REPLACE a good pin with a worse one: the snap is
applied only when the measured error exceeds the threshold.

The reference lookup is INJECTABLE (``reference_fn``) so the snapper is unit-tested
offline; the live default calls ``pin_proof.reference_for_name`` (Serper Places
first, then Nominatim), with the SAME scope-sanity bound and bare-name stripping,
so the door the snap uses is the door the proof uses.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "snap_pin",
    "snap_poi_coordinates",
    "SNAP_THRESHOLD_M",
    "PIN_TARGET_M",
]

SNAP_THRESHOLD_M = 150.0
PIN_TARGET_M = 100.0

_COORD_PAIR_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[,/ ]\s*(-?\d+(?:\.\d+)?)")


def _parse_coord(s) -> Optional[Tuple[float, float]]:
    if isinstance(s, (tuple, list)) and len(s) == 2:
        try:
            lat, lng = float(s[0]), float(s[1])
        except (TypeError, ValueError):
            return None
        if abs(lat) > 90 or abs(lng) > 180:
            return None
        return (lat, lng)
    m = _COORD_PAIR_RE.search(str(s or ""))
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None
    if abs(lat) > 90 or abs(lng) > 180:
        return None
    return (lat, lng)


def _haversine_m(a, b) -> float:
    try:
        from geocode_stops import haversine_m as _hm
        return _hm(a, b)
    except Exception:
        import math
        R = 6371000.0
        lat1, lng1 = math.radians(a[0]), math.radians(a[1])
        lat2, lng2 = math.radians(b[0]), math.radians(b[1])
        h = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
        return 2 * R * math.asin(math.sqrt(h))


def _poi_coord(poi: Dict) -> Optional[Tuple[float, float]]:
    """A poi's current coordinate, from the 'coordinates' string or lat/lng."""
    c = _parse_coord(poi.get("coordinates"))
    if c:
        return c
    lat = poi.get("latitude", poi.get("lat"))
    lng = poi.get("longitude", poi.get("lng", poi.get("lon")))
    if lat is not None and lng is not None:
        return _parse_coord((lat, lng))
    return None


def _wikidata_coord(poi: Dict) -> Optional[Tuple[float, float]]:
    """A Wikidata P625 coordinate already on the poi (the strongest reference —
    it needs no network). Returns (lat, lng) or None."""
    lat = poi.get("wikidata_lat")
    lng = poi.get("wikidata_lng")
    if lat is not None and lng is not None:
        return _parse_coord((lat, lng))
    return None


def _default_reference(name: str, scope: str,
                       scope_center: Optional[Tuple[float, float]]
                       ) -> Optional[Tuple[float, float, str]]:
    """Live reference lookup: pin_proof.reference_for_name (Serper → Nominatim),
    the SAME door the proof uses."""
    try:
        from pin_proof import reference_for_name
        return reference_for_name(name, scope=scope, scope_center=scope_center)
    except Exception:
        return None


def _landmark_reference(name: str,
                        scope: str = "",
                        scope_center: Optional[Tuple[float, float]] = None,
                        scope_bbox: Optional[Sequence[float]] = None,
                        tour_language: str = "en",
                        landmark_fn: Optional[Callable] = None,
                        ) -> Optional[Tuple[float, float, str]]:
    """[LOCAL-803] A Wikidata-P625 landmark reference, consulted BEFORE the generic
    geocoders. Returns (lat, lng, source) or None.

    [LOCAL-803] PREFER a LIVE Wikidata P625 lookup (``wikidata_landmark_lookup``):
    wbsearchentities in the tour + local language, P625, filtered to the tour's
    scope (bbox / metro radius), cached with a TTL. This generalises the fix
    beyond the six HCMC landmarks to ANY city. It resolves "City Hall" → the real
    People's Committee Building and "Thien Hau Temple" → the Cholon temple by the
    place's OWN authority, exactly as the hand-written table did, and now also
    "Boston State House", "Nice Opera", "Hanoi Hoan Kiem Lake", etc.

    FALLBACK: when the live lookup returns nothing — Wikidata unreachable, a 429
    that never cleared, or no in-scope match — fall back to the offline
    ``landmark_reference`` table so the original six HCMC pins never regress when
    the network is down. (``landmark_fn`` injects the live lookup for tests.)
    """
    # 1) Live Wikidata P625 lookup (general, cached, rate-limited).
    try:
        if landmark_fn is not None:
            hit = landmark_fn(name)
        else:
            from wikidata_landmark_lookup import lookup as _wd_lookup
            hit = _wd_lookup(
                name, scope=scope, scope_center=scope_center,
                scope_bbox=list(scope_bbox) if scope_bbox else None,
                tour_language=tour_language or "en")
        if hit:
            return (float(hit[0]), float(hit[1]), str(hit[2]))
    except Exception:
        # Any failure in the live path must not drop the stop — fall through to
        # the offline table below.
        pass
    # 2) Offline table fallback (the original six HCMC landmarks).
    try:
        from landmark_reference import lookup as _lm_lookup
        tbl = _lm_lookup(name)
        if tbl:
            return (float(tbl[0]), float(tbl[1]), str(tbl[2]))
    except Exception:
        return None
    return None


def _name_distinctive_tokens(name: str):
    """Distinctive (proper-noun) tokens of a place name, class-folded, honorifics /
    city-district qualifiers dropped — the shared identity core for a name match.
    Delegates to identity_dedup when available."""
    try:
        from identity_dedup import _distinctive_tokens as _dt
        core = set(_dt(name))
    except Exception:
        import re as _re
        import unicodedata as _ud
        nfkd = _ud.normalize("NFKD", (name or "").lower())
        s = "".join(c for c in nfkd if not _ud.combining(c))
        s = _re.sub(r"[^\w\s]", " ", s)
        core = {w for w in s.split() if len(w) >= 2}
    _drop = {"saigon", "hcmc", "ho", "chi", "minh", "city", "vietnam", "old",
             "new", "central", "district", "downtown", "sai", "gon", "the", "of"}
    return {t for t in core if t not in _drop}


def _name_matches_reference(title: str, ref_name: str) -> bool:
    """[LOCAL-791E item 1] True when a reference NAME strongly matches the stop
    title — they share the distinctive proper-noun core (one token-set is a subset
    of the other, both non-empty). A generic "City Hall" vs a reference listing
    named for a DIFFERENT building shares no distinctive core and is rejected, so a
    wrong same-class snap (the 4.8 km City Hall bug) is refused. When the reference
    carries no usable name we cannot verify a match → treated as NOT matched (the
    caller only requires a match for generic geocoder references, not for the
    authority table / Wikidata)."""
    a = _name_distinctive_tokens(title)
    b = _name_distinctive_tokens(ref_name)
    if not a or not b:
        return False
    return a <= b or b <= a


def snap_pin(title: str,
             coordinate: Optional[Tuple[float, float]],
             scope: str = "",
             scope_center: Optional[Tuple[float, float]] = None,
             wikidata_coord: Optional[Tuple[float, float]] = None,
             threshold_m: float = SNAP_THRESHOLD_M,
             reference_fn: Optional[Callable] = None,
             max_snap_km: float = 15.0,
             stops_centroid: Optional[Tuple[float, float]] = None,
             max_centroid_km: float = 2.0,
             require_name_match: bool = True,
             use_landmark_table: bool = True,
             scope_bbox: Optional[Sequence[float]] = None,
             tour_language: str = "en",
             landmark_fn: Optional[Callable] = None,
             ) -> Dict:
    """Decide the snap for ONE stop.

    Returns a dict::

        {"title", "shipped", "reference", "source", "distance_m",
         "snapped": bool, "new_coordinate": (lat,lng)|None, "reason": str}

    * A Wikidata P625 coordinate already on the stop is the reference when present
      (``source='wikidata'``), with no network call.
    * Otherwise the reference is the injected / default Serper→Nominatim lookup.
    * ``snapped`` is True when a reference exists AND the shipped pin is more than
      ``threshold_m`` from it; ``new_coordinate`` is then the reference.
    * No reference → ``snapped`` False, ``reason`` says the stop is left unsnapped.

    SCOPE SANITY: a reference more than ``max_snap_km`` from ``scope_center`` is a
    same-name place in another city (Nominatim's bare-name match for a HCMC pagoda
    returned a shrine 40 km away). We do NOT snap to it — moving a pin tens of km
    across the region is worse than the shipped error — and leave the stop as-is,
    saying so in the reason. Disabled when scope_center is unknown.
    """
    out: Dict = {
        "title": title,
        "shipped": coordinate,
        "reference": None,
        "source": None,
        "distance_m": None,
        "snapped": False,
        "new_coordinate": None,
        "reason": "",
    }

    ref_pt: Optional[Tuple[float, float]] = None
    source: Optional[str] = None
    ref_name: str = ""
    # "authority" references (the stop's own Wikidata P625, or the P625 landmark
    # table) are the place's own identity, not a bare-name geocode — they are
    # exempt from the name-match requirement and the off-scope / centroid bounds.
    authority = False

    wd = wikidata_coord
    if wd:
        ref_pt, source, authority = wd, "wikidata", True
    else:
        # [LOCAL-791E items 1 & 5] Consult the Wikidata-P625 landmark table FIRST
        # on the LIVE path (no injected reference_fn). It resolves "City Hall" to
        # the real People's Committee Building and "Thien Hau Temple" to the Cholon
        # temple (by the place's own name / local-language name), where the generic
        # geocoder returned a wrong same-class place (item 1) or nothing (item 5).
        # An injected reference_fn (unit tests / offline replays) is a vouched-for
        # door and takes precedence, so the table is skipped for it.
        if use_landmark_table and reference_fn is None:
            lm = _landmark_reference(
                title, scope=scope, scope_center=scope_center,
                scope_bbox=scope_bbox, tour_language=tour_language,
                landmark_fn=landmark_fn)
            if lm:
                ref_pt = (float(lm[0]), float(lm[1]))
                source = lm[2] if len(lm) > 2 else "wikidata_p625"
                authority = True
        if ref_pt is None:
            rfn = reference_fn or (
                lambda n: _default_reference(n, scope, scope_center))
            try:
                ref = rfn(title)
            except Exception:
                ref = None
            if ref:
                try:
                    ref_pt = (float(ref[0]), float(ref[1]))
                    source = ref[2] if len(ref) > 2 else "reference"
                    ref_name = ref[3] if len(ref) > 3 else ""
                except (TypeError, ValueError, IndexError):
                    ref_pt = None

    if not ref_pt:
        out["reason"] = "no in-scope reference — left unsnapped"
        return out

    # [LOCAL-791E item 1] NAME-MATCH REQUIREMENT for a GENERIC geocoder reference.
    # A bare-name geocode ("City Hall") can land on a DIFFERENT same-class building
    # anywhere in the city — a wrong snap is worse than none. When the generic
    # reference carries a NAME, snap only if it strongly matches the stop (shared
    # distinctive proper-noun core); a mismatch is refused (kept pin). Authority
    # references (Wikidata P625 / the landmark table) are the place's own identity
    # and skip this check. When no name is available we cannot verify by name and
    # defer to the stops-centroid bound below.
    if require_name_match and not authority and ref_name:
        if not _name_matches_reference(title, ref_name):
            out["reference"] = ref_pt
            out["source"] = source
            out["reason"] = (
                f"reference name {ref_name!r} does not match stop — refused "
                f"(generic same-name/same-class match)")
            return out

    # [LOCAL-791E item 1] STOPS-CENTROID BOUND. The reference must sit within
    # ``max_centroid_km`` of the OTHER stops' centroid (not just the city centre):
    # the Old Saigon landmarks cluster in District 1, so a "City Hall" reference
    # 4.8 km south of that cluster is a wrong building — refuse and keep the pin.
    # Authority references are trusted (the place's own P625). Disabled when no
    # stops_centroid is supplied (unit tests that exercise only scope_center).
    if (not authority and stops_centroid and max_centroid_km):
        _cd = _haversine_m(ref_pt, stops_centroid) / 1000.0
        if _cd > max_centroid_km:
            out["reference"] = ref_pt
            out["source"] = source
            out["reason"] = (
                f"reference {_cd:.1f} km from stops' centroid "
                f"> {max_centroid_km:.1f} km — refused (wrong same-name place)")
            return out

    # SCOPE SANITY: refuse a reference implausibly far from the tour's centre — a
    # bare-name geocode that resolved to another city. Wikidata P625 / the landmark
    # table are trusted as-is (the place's own authority, not a name search).
    if (not authority and scope_center and max_snap_km
            and _haversine_m(ref_pt, scope_center) / 1000.0 > max_snap_km):
        out["reason"] = (f"reference {_haversine_m(ref_pt, scope_center)/1000.0:.0f} km "
                         f"from centre > {max_snap_km:.0f} km — left unsnapped "
                         f"(off-scope same-name match)")
        return out

    out["reference"] = ref_pt
    out["source"] = source

    if not coordinate:
        # No shipped pin at all: adopt the reference (better than nothing).
        out["snapped"] = True
        out["new_coordinate"] = ref_pt
        out["distance_m"] = None
        out["reason"] = "no shipped pin — adopted reference"
        return out

    dist = _haversine_m(coordinate, ref_pt)
    out["distance_m"] = round(dist, 1)

    # DON'T MAKE A GOOD PIN WORSE (LOCAL-791C live run, Thien Hau Temple): the
    # shipped pin sat in District 5 (~2 km from the HCMC centre, correct), but
    # Nominatim's bare-name match returned a same-name shrine 23 km north — inside
    # the loose 25 km bound, so it snapped and blew the walking route to 11 km.
    # A reference is only trustworthy when it is at least as central as the pin it
    # would replace: if the shipped pin is itself in-scope (close to centre) AND
    # the reference is markedly farther from centre than the shipped pin, the
    # reference is a wrong same-name place in another district/city — keep the
    # shipped pin. Wikidata P625 / the landmark table (the place's own authority)
    # are exempt.
    if (not authority and scope_center and coordinate):
        _ship_km = _haversine_m(coordinate, scope_center) / 1000.0
        _ref_km = _haversine_m(ref_pt, scope_center) / 1000.0
        if _ship_km <= 10.0 and _ref_km > _ship_km + 5.0:
            out["reason"] = (f"shipped pin {_ship_km:.0f} km from centre is in-scope; "
                             f"reference {_ref_km:.0f} km from centre is farther out "
                             f"— kept shipped pin (reference is an off-scope same-name "
                             f"match)")
            return out

    if dist > threshold_m:
        out["snapped"] = True
        out["new_coordinate"] = ref_pt
        out["reason"] = f"shipped pin {dist:.0f} m > {threshold_m:.0f} m threshold"
    else:
        out["reason"] = f"shipped pin {dist:.0f} m within {threshold_m:.0f} m — kept"
    return out


def snap_poi_coordinates(poi_list: List[Dict],
                         scope: str = "",
                         scope_center: Optional[Tuple[float, float]] = None,
                         threshold_m: float = SNAP_THRESHOLD_M,
                         reference_fn: Optional[Callable] = None,
                         log: Optional[Callable[[str], None]] = None,
                         max_centroid_km: float = 2.0,
                         require_name_match: bool = True,
                         scope_bbox: Optional[Sequence[float]] = None,
                         tour_language: str = "en",
                         landmark_fn: Optional[Callable] = None,
                         ) -> Tuple[List[Dict], List[Dict]]:
    """Snap every stop in ``poi_list`` to its reference when the shipped pin is
    more than ``threshold_m`` away AND the reference is trustworthy. Mutates each
    poi's ``coordinates`` (and latitude/longitude when present) in place and
    returns ``(poi_list, rows)`` where ``rows`` is the per-stop ``snap_pin``
    decision.

    [LOCAL-791E] A snap is only applied when the reference is the place's own
    authority (Wikidata P625 / the landmark table) OR a generic geocode whose NAME
    strongly matches the stop AND that sits within ``max_centroid_km`` of the OTHER
    stops' centroid. A reference that fails either test is REFUSED — the shipped
    pin is kept and ``[LOCAL-791E] snap refused <title> <reason>`` is logged — so a
    wrong same-name/same-class snap (the City Hall 4.8 km bug) never ships.

    Logs ``[LOCAL-791C] pin snap <title> <m>`` for each snapped stop, a
    ``[LOCAL-791E] snap refused …`` line for a reference rejected by the name /
    centroid guards, and a ``left unsnapped`` line for a stop with no reference."""
    emit = log or (lambda _m: None)
    rows: List[Dict] = []

    # An INJECTED reference_fn is a vouched-for reference (unit tests / offline
    # replays supply the KNOWN-correct door), so the name-match and stops-centroid
    # guards — which defend against the LIVE geocoder's wrong same-name matches —
    # are not applied to it. The guards are active only on the live default path.
    _injected = reference_fn is not None
    _rnm = require_name_match and not _injected
    _max_centroid = None if _injected else max_centroid_km

    # Precompute each stop's current coordinate so the stops-centroid is the
    # LEAVE-ONE-OUT centroid of the OTHER stops (a stop is never bounded against
    # its own pin, and one wrong pin does not pull its own bound).
    coords_all: List[Optional[Tuple[float, float]]] = [_poi_coord(p) for p in poi_list]

    def _centroid_excluding(idx: int) -> Optional[Tuple[float, float]]:
        pts = [c for j, c in enumerate(coords_all) if j != idx and c]
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts))

    # The centroid bound is ADAPTIVE to how spread the stops already are. For a
    # TIGHT cluster (an Old Saigon walking tour in District 1) it stays at
    # ``max_centroid_km`` (2 km), so a City Hall reference 4.8 km outside the
    # cluster is refused. For a city-SPANNING tour (pagodas across HCMC — the
    # named anchors alone are ~5 km apart) it widens to the stops' own radius + a
    # margin, so a genuinely far pagoda's correct reference is not refused. The
    # reference must still be no farther from the centroid than the stops
    # themselves reach, plus the base bound.
    def _adaptive_bound(idx: int, centroid: Optional[Tuple[float, float]]) -> float:
        if not centroid:
            return _max_centroid or 0.0
        other = [c for j, c in enumerate(coords_all) if j != idx and c]
        spread = max((_haversine_m(c, centroid) / 1000.0 for c in other),
                     default=0.0)
        return max(_max_centroid or 0.0, spread + (_max_centroid or 0.0))

    for i, poi in enumerate(poi_list):
        title = poi.get("name", "")
        coord = coords_all[i]
        wd = _wikidata_coord(poi)
        _centroid_i = None if _injected else _centroid_excluding(i)
        _bound_i = 0.0 if _injected else _adaptive_bound(i, _centroid_i)
        row = snap_pin(title, coord, scope=scope, scope_center=scope_center,
                       wikidata_coord=wd, threshold_m=threshold_m,
                       reference_fn=reference_fn,
                       stops_centroid=_centroid_i,
                       max_centroid_km=_bound_i,
                       require_name_match=_rnm,
                       scope_bbox=scope_bbox,
                       tour_language=tour_language,
                       landmark_fn=landmark_fn)
        rows.append(row)
        if row["snapped"] and row["new_coordinate"]:
            lat, lng = row["new_coordinate"]
            poi["coordinates"] = f"{lat:.6f}, {lng:.6f}"
            if "latitude" in poi or "longitude" in poi:
                poi["latitude"] = lat
                poi["longitude"] = lng
            poi["_pin_snapped"] = True
            poi["_pin_snap_source"] = row["source"]
            d = row["distance_m"]
            emit(f"[LOCAL-791C] pin snap {title} "
                 f"{('%.0f' % d) if d is not None else '?'}m "
                 f"→ {lat:.6f},{lng:.6f} ({row['source']})")
        elif row["reference"] is None:
            emit(f"[LOCAL-791C] pin snap {title} left unsnapped "
                 f"({row.get('reason') or 'no in-scope reference'})")
        elif "refused" in (row.get("reason") or ""):
            # A reference WAS found but the name-match / centroid guard rejected it.
            emit(f"[LOCAL-791E] snap refused {title} {row.get('reason')}")
        else:
            d = row["distance_m"]
            emit(f"[LOCAL-791C] pin ok {title} "
                 f"{('%.0f' % d) if d is not None else '?'}m within threshold")
    return poi_list, rows
