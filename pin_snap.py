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


def snap_pin(title: str,
             coordinate: Optional[Tuple[float, float]],
             scope: str = "",
             scope_center: Optional[Tuple[float, float]] = None,
             wikidata_coord: Optional[Tuple[float, float]] = None,
             threshold_m: float = SNAP_THRESHOLD_M,
             reference_fn: Optional[Callable] = None,
             max_snap_km: float = 15.0,
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

    wd = wikidata_coord
    if wd:
        ref_pt, source = wd, "wikidata"
    else:
        rfn = reference_fn or (lambda n: _default_reference(n, scope, scope_center))
        try:
            ref = rfn(title)
        except Exception:
            ref = None
        if ref:
            try:
                ref_pt = (float(ref[0]), float(ref[1]))
                source = ref[2] if len(ref) > 2 else "reference"
            except (TypeError, ValueError, IndexError):
                ref_pt = None

    if not ref_pt:
        out["reason"] = "no in-scope reference — left unsnapped"
        return out

    # SCOPE SANITY: refuse a reference implausibly far from the tour's centre — a
    # bare-name geocode that resolved to another city. Wikidata P625 on the stop
    # is trusted as-is (it is the place's own authority, not a name search).
    if (source != "wikidata" and scope_center and max_snap_km
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
    # shipped pin. Wikidata P625 (the place's own authority) is exempt.
    if (source != "wikidata" and scope_center and coordinate):
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
                         ) -> Tuple[List[Dict], List[Dict]]:
    """Snap every stop in ``poi_list`` to its in-scope reference when the shipped
    pin is more than ``threshold_m`` away. Mutates each poi's ``coordinates`` (and
    latitude/longitude when present) in place and returns ``(poi_list, rows)`` where
    ``rows`` is the per-stop decision from ``snap_pin``.

    Logs ``[LOCAL-791C] pin snap <title> <m>`` for each snapped stop and a
    ``left unsnapped`` line for each stop with no in-scope reference."""
    emit = log or (lambda _m: None)
    rows: List[Dict] = []
    for poi in poi_list:
        title = poi.get("name", "")
        coord = _poi_coord(poi)
        wd = _wikidata_coord(poi)
        row = snap_pin(title, coord, scope=scope, scope_center=scope_center,
                       wikidata_coord=wd, threshold_m=threshold_m,
                       reference_fn=reference_fn)
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
        else:
            d = row["distance_m"]
            emit(f"[LOCAL-791C] pin ok {title} "
                 f"{('%.0f' % d) if d is not None else '?'}m within threshold")
    return poi_list, rows
