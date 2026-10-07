"""[LOCAL-605] Tour-level coordinate resolution — one place, every path.

Why this exists
---------------
`generate_tour_text` returns a ``(text, output_file, (lat, lng))`` triple, but
every non-fresh delivery path returns ``(None, None)`` for the coordinates:

* the stop-pool fast path (first-tour and pooled reuse) — ``stop_pool_orchestrator``
  returns a dict with no coordinates, and the generator hands back ``(None, None)``;
* the by-reference refusal/short-circuit (LOCAL-597);
* the site-first / overview path (LOCAL-582).

The orchestrator stores whatever it receives, and ``tours-near`` filters on
``lat``/``lng``, so a pooled/overview tour with ``(None, None)`` is invisible in
"tours near me" and has no map pin (LOCAL-605).

The fix is to resolve a real tour-level coordinate from the delivered content and
the venue, at the single choke point in the service, for ALL paths:

1. the venue's own coordinates for a CONTAINED venue (museum/facility) — from the
   venue resolver (Wikidata P625) or by geocoding the D611 venue address; else
2. Stop 1's ``Coordinates:`` line from the delivered text.

A tour delivered without resolvable coordinates is an ERROR (fail-closed): the
caller logs it with the path name and does not silently deliver ``(None, None)``.

Everything here is pure/best-effort and import-light so it is trivially testable
with stubs; network/DB lookups are guarded and degrade to ``None``.
"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple

Coord = Tuple[Optional[float], Optional[float]]

__all__ = [
    "parse_stop1_coordinates",
    "parse_coordinates_text",
    "resolve_venue_coordinates",
    "resolve_tour_coordinates",
    "coordinates_present",
    "MissingTourCoordinates",
]


class MissingTourCoordinates(Exception):
    """Raised (or surfaced) when a delivered tour has no resolvable coordinates.

    Carries the delivery path name so the fail-closed log says WHICH path failed.
    """

    def __init__(self, path: str, message: str = ""):
        self.path = path
        super().__init__(message or f"tour delivered with no resolvable coordinates (path={path})")


# ── coordinate parsing ───────────────────────────────────────────────────────

# Decimal pair, e.g. "42.364459, -71.055797"
_DECIMAL_RE = re.compile(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)')
# DMS-ish signed-hemisphere pair, e.g. "10.2231° N, 103.9600° E"
_HEMISPHERE_RE = re.compile(
    r'(\d+\.\d+)\s*[°]?\s*([NSns]).*?(\d+\.\d+)\s*[°]?\s*([EWew])')


def coordinates_present(coords: Optional[Coord]) -> bool:
    """True only when BOTH lat and lng are real, finite numbers.

    ``None``, ``(None, None)``, a one-element tuple, or non-numeric values all
    count as absent. ``(0, 0)`` is treated as ABSENT: the orchestrator uses it as
    an explicit "could not resolve" sentinel (never a real tour location), so it
    must not satisfy the fail-closed assertion.
    """
    if not coords or len(coords) < 2:
        return False
    lat, lng = coords[0], coords[1]
    try:
        if lat is None or lng is None:
            return False
        latf, lngf = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if latf != latf or lngf != lngf:  # NaN
        return False
    if latf == 0.0 and lngf == 0.0:   # (0,0) sentinel — not a real location
        return False
    if not (-90.0 <= latf <= 90.0) or not (-180.0 <= lngf <= 180.0):
        return False
    return True


def parse_coordinates_text(coords_text: str) -> Coord:
    """Parse a single ``Coordinates:`` VALUE into ``(lat, lng)`` or ``(None, None)``.

    Handles both delivered formats (mirrors the normal path in
    generate_tour_text):
      * decimal: ``42.364459, -71.055797``
      * hemisphere: ``10.2231° N, 103.9600° E`` (S/W negate).
    """
    if not coords_text:
        return (None, None)
    text = str(coords_text).strip()
    m = _HEMISPHERE_RE.search(text)
    if m:
        try:
            lat = float(m.group(1))
            if m.group(2).upper() == 'S':
                lat = -lat
            lng = float(m.group(3))
            if m.group(4).upper() == 'W':
                lng = -lng
            return (lat, lng)
        except (TypeError, ValueError):
            pass
    m = _DECIMAL_RE.search(text)
    if m:
        try:
            return (float(m.group(1)), float(m.group(2)))
        except (TypeError, ValueError):
            pass
    return (None, None)


def parse_stop1_coordinates(tour_content: str) -> Coord:
    """Extract Stop 1's ``Coordinates:`` line from delivered tour text.

    Returns the FIRST ``Coordinates:`` value in the content (Stop 1 leads), parsed
    to ``(lat, lng)``, or ``(None, None)`` when there is no usable line.
    """
    if not tour_content:
        return (None, None)
    m = re.search(r'^\s*Coordinates:\s*(.+?)\s*$', tour_content, re.IGNORECASE | re.MULTILINE)
    if not m:
        return (None, None)
    return parse_coordinates_text(m.group(1))


# ── venue coordinate resolution (contained venues) ────────────────────────────

def _geocode_address(address: str) -> Coord:
    """Best-effort geocode of a street address → ``(lat, lng)`` or ``(None, None)``.

    Uses the project's OSM/Nominatim helper when available; never raises.
    """
    if not address or not address.strip():
        return (None, None)
    try:
        import osm_venue_facts as _osm
    except Exception:
        return (None, None)
    for fn_name in ("geocode_address", "geocode", "forward_geocode"):
        fn = getattr(_osm, fn_name, None)
        if callable(fn):
            try:
                res = fn(address)
            except Exception:
                continue
            coord = _coord_from_any(res)
            if coordinates_present(coord):
                return coord
    return (None, None)


def _coord_from_any(obj) -> Coord:
    """Pull ``(lat, lng)`` out of a tuple/list/dict/entity shape, best-effort."""
    if obj is None:
        return (None, None)
    if isinstance(obj, (tuple, list)) and len(obj) >= 2:
        try:
            return (float(obj[0]), float(obj[1]))
        except (TypeError, ValueError):
            return (None, None)
    if isinstance(obj, dict):
        for la, lo in (("lat", "lng"), ("lat", "lon"), ("latitude", "longitude")):
            if obj.get(la) is not None and obj.get(lo) is not None:
                try:
                    return (float(obj[la]), float(obj[lo]))
                except (TypeError, ValueError):
                    return (None, None)
        return (None, None)
    lat = getattr(obj, "lat", None)
    lng = getattr(obj, "lng", None)
    if lng is None:
        lng = getattr(obj, "lon", None)
    try:
        if lat is not None and lng is not None:
            return (float(lat), float(lng))
    except (TypeError, ValueError):
        return (None, None)
    return (None, None)


def resolve_venue_coordinates(location: str) -> Coord:
    """Resolve a CONTAINED venue's own coordinates: resolver (P625) → D611 address.

    1. ``venue_resolver.resolve_venue`` → entity ``.lat``/``.lng`` (Wikidata P625).
    2. Fall back to geocoding the venue's sourced street address (the D611 address
       used by the About-museum stop, via ``stop_pool_orchestrator._resolve_venue_address``).

    Best-effort and non-fatal; returns ``(None, None)`` when nothing resolves.
    """
    if not location:
        return (None, None)
    clean = location
    try:
        from about_museum_stop import clean_venue_request_name
        clean = clean_venue_request_name(location) or location
    except Exception:
        clean = location

    # 1) Resolver / Wikidata P625.
    try:
        from venue_resolver import resolve_venue
        ent = resolve_venue(clean)
        if ent is not None:
            coord = _coord_from_any(ent)
            if coordinates_present(coord):
                return coord
    except Exception:
        pass

    # 2) D611 venue street address → geocode.
    try:
        from stop_pool_orchestrator import _resolve_venue_address
        address = _resolve_venue_address(location)
        coord = _geocode_address(address)
        if coordinates_present(coord):
            return coord
    except Exception:
        pass

    return (None, None)


# ── the one entry point every path uses ───────────────────────────────────────

def resolve_tour_coordinates(
    tour_content: str,
    location: str,
    coordinates: Optional[Coord] = None,
    *,
    contained: Optional[bool] = None,
    path: str = "unknown",
) -> Tuple[Coord, str]:
    """Resolve real tour-level coordinates for a delivered tour, any path.

    Order of preference:
      * if ``coordinates`` already carries a real pair, keep it (source="generator");
      * for a CONTAINED venue, the venue's own coordinates (source="venue");
      * otherwise Stop 1's ``Coordinates:`` line (source="stop1");
      * a last fallback tries Stop 1 then venue regardless of containment, so a
        contained venue with no resolver hit still gets Stop 1's pin.

    Returns ``((lat, lng), source)``. ``source`` is "none" when nothing resolved —
    the caller decides whether that is fatal (it is, for a delivered tour).

    Pure except for the venue lookup, which is guarded/best-effort.
    """
    # 0) Already have real coordinates from the generator — trust them.
    if coordinates_present(coordinates):
        return ((float(coordinates[0]), float(coordinates[1])), "generator")

    if contained is None:
        contained = _is_contained_venue(location)

    stop1 = parse_stop1_coordinates(tour_content)

    if contained:
        venue = resolve_venue_coordinates(location)
        if coordinates_present(venue):
            return (venue, "venue")
        if coordinates_present(stop1):
            return (stop1, "stop1")
    else:
        if coordinates_present(stop1):
            return (stop1, "stop1")
        venue = resolve_venue_coordinates(location)
        if coordinates_present(venue):
            return (venue, "venue")

    return ((None, None), "none")


def _is_contained_venue(location: str) -> bool:
    """Best-effort: is this a contained venue (museum/facility)? Default False."""
    try:
        from stop_pool_orchestrator import _classify, _is_contained
        return bool(_is_contained(_classify(location, "")))
    except Exception:
        return False
