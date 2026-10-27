"""overpass_fallback.py — LOCAL-788 item 3/B.

An Overpass outage must NEVER silently shrink the candidate list.

WHY THIS EXISTS
---------------
On GCloud (2026-10-27, tour 460) Overpass answered **502** while the tour was
being built. The existing Overpass clients log the 5xx and return ``None`` — with
no mirror and no alternative provider — so any candidate path that depends on
Overpass simply loses those candidates when Overpass is down. That is how a real,
in-scope place can be dropped by an infrastructure outage rather than by any
scope rule.

THE CONTRACT (the ticket's item 3)
----------------------------------
A 5xx / timeout / connection error from Overpass must:
  1. retry once on a second public MIRROR
     (overpass.kumi.systems / overpass.private.coffee) — this is handled inside
     the shared client ``osm_venue_facts._overpass_request``, which now walks the
     primary + mirror endpoints; and
  2. if every Overpass endpoint fails, continue with **Serper Places** using
     ``ll`` at the scope centre (``places_search.places_search``), so the
     candidate list is still populated.
It must never silently shrink the candidate list. Each step logs
``[LOCAL-788] overpass fallback <endpoint> <status>``.

This module is the ONE reusable seam a candidate-discovery path calls to get that
behaviour. It never raises: a total failure returns ``[]`` (the caller then
refuses honestly), never a partial list dressed up as complete.
"""
import logging
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _overpass_client(overpass_request: Optional[Callable]) -> Optional[Callable]:
    """The shared Overpass client (primary + mirror fallback lives inside it).
    Injectable for tests; defaults to the EXISTING client (no second client)."""
    if overpass_request is not None:
        return overpass_request
    try:
        from osm_venue_facts import _overpass_request as _req
        return _req
    except Exception as e:  # pragma: no cover
        logger.warning("[LOCAL-788] Overpass client unavailable (%s)", e)
        return None


def query_pois_with_fallback(
    overpass_query: str,
    serper_query: str,
    scope: str,
    scope_center: Optional[Tuple[float, float]] = None,
    scope_bbox=None,
    near: Optional[Tuple[float, float]] = None,
    limit: int = 25,
    context: str = "",
    overpass_request: Optional[Callable] = None,
    places_search_fn: Optional[Callable] = None,
) -> List[Dict]:
    """Return POI candidates, preferring Overpass and falling back to Serper.

    Order:
      1. Overpass via the shared client (which itself tries the primary endpoint
         then the public mirrors on a 5xx/timeout — see
         ``osm_venue_facts._overpass_request``). A non-empty ``elements`` list is
         returned, normalised to ``{"name","coordinates","lat","lng","address",
         "source":"osm","tags"}``.
      2. If Overpass returns no usable answer (every endpoint failed, or an empty
         body), fall back to **Serper Places** with ``ll`` at the scope centre
         (device coords for a "near me" request), scope-bound by LOCAL-786. The
         result is tagged ``source="serper"``.

    The candidate list is never silently shrunk: an Overpass outage escalates to
    Serper rather than returning fewer places. Returns ``[]`` only when BOTH
    providers yield nothing. Never raises.
    """
    _req = _overpass_client(overpass_request)
    elements = None
    if _req is not None and overpass_query:
        try:
            data = _req(overpass_query, context=context or "overpass-fallback")
            if isinstance(data, dict):
                elements = data.get("elements") or []
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("[LOCAL-788] Overpass client raised (%s); will try Serper", e)
            elements = None

    if elements:
        out = _normalise_overpass(elements)
        if out:
            return out[:max(0, limit)]

    # Overpass gave nothing (outage, or empty). Do NOT shrink the candidate list —
    # fall back to Serper Places with `ll` at the scope centre.
    print(f"  [LOCAL-788] overpass fallback serper (overpass empty/down for "
          f"{context or serper_query!r})")
    _ps_search = places_search_fn
    if _ps_search is None:
        try:
            from places_search import places_search as _ps_search
        except Exception as e:  # pragma: no cover
            logger.warning("[LOCAL-788] places_search unavailable for Serper "
                           "fallback (%s)", e)
            return []
    try:
        results = _ps_search(serper_query, scope, near=near, limit=limit,
                             scope_center=scope_center, scope_bbox=scope_bbox)
    except Exception as e:  # pragma: no cover
        logger.warning("[LOCAL-788] Serper fallback failed (%s)", e)
        return []
    out = _normalise_serper(results)
    print(f"  [LOCAL-788] overpass fallback serper count={len(out)}")
    return out[:max(0, limit)]


def _normalise_overpass(elements: List[dict]) -> List[Dict]:
    """OSM Overpass elements → the shared candidate shape. Nameless elements and
    coordinate-less elements are dropped (a stop must be a named place)."""
    out = []
    for el in elements or []:
        tags = el.get("tags", {}) or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        out.append({
            "name": name,
            "coordinates": f"{lat},{lon}",
            "lat": lat,
            "lng": lon,
            "address": tags.get("addr:full") or tags.get("addr:street") or "",
            "source": "osm",
            "tags": tags,
        })
    return out


def _normalise_serper(results: List[dict]) -> List[Dict]:
    """places_search OSM-shaped records → the shared candidate shape."""
    out = []
    for r in results or []:
        name = (r.get("name") or r.get("display_name") or "").strip()
        if not name:
            continue
        try:
            lat = float(r["lat"])
            lon = float(r["lon"])
        except (KeyError, ValueError, TypeError):
            continue
        addr = r.get("address") or {}
        addr_str = ""
        if isinstance(addr, dict):
            addr_str = addr.get("road") or addr.get("city") or ""
        out.append({
            "name": name,
            "coordinates": f"{lat},{lon}",
            "lat": lat,
            "lng": lon,
            "address": addr_str or r.get("display_name", ""),
            "source": "serper",
            "tags": {},
        })
    return out
