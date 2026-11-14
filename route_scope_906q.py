"""[LOCAL-906Q] An A-to-B tour is judged against its ROUTE CORRIDOR, never the destination alone.

Proof 906P ("<Origin> to <Mountain>, <Province>, <Country>", driving): the scope check judged every stop against the mountain's
district, removed a stream that sits ON the route near the origin, and wrote that rejection into known_out_of_scope.json.

* ``corridor``        -- the route's origin, destination, region and padded A-to-B box (None when the tour is not a route).
* ``label``           -- the scope text the judge sees: the whole corridor, not the destination.
* ``stop_in_corridor``-- a stop inside the box, or whose address names the region / origin / destination, is in scope.
* ``may_record``      -- False on a route tour: a rejection made against a route is never written to scope memory, and a
  stored entry never rejects a stop of a route tour.

Pure, free, never raises. Generic names only (D769).
"""
from __future__ import annotations

import re
from typing import Callable, Dict, Optional, Sequence, Tuple

import route_content_896 as rc
import route_order_909 as r909

TAG = "[LOCAL-906Q]"


def corridor(compute_box: bool = True, geocode_fn: Optional[Callable] = None) -> Optional[Dict]:
    """``{"origin", "destination", "region", "box"}`` of the current generation's route, else None. ``box`` is
    ``[south, north, west, east]`` (route_box's 25 km margin) or None when it cannot be placed."""
    try:
        info = r909.route()
        o = d = region = ""
        if info:
            o, d, region = info.get("origin", ""), info.get("destination", ""), info.get("region", "")
        elif rc.active():
            o, d = rc.endpoints()
        if not (o and d and rc.fold(o) != rc.fold(d)):
            return None
        box = rc.box() if rc.active() else None
        cached = r909._STATE.get("corridor_box_906q")
        if not box and cached:
            box = cached
        if not box and compute_box:
            try:
                box, _c, _n = rc.route_box([o, d], region, geocode_fn)
            except Exception:
                box = None
            if box:
                r909._STATE["corridor_box_906q"] = list(box)
        return {"origin": o, "destination": d, "region": region, "box": list(box) if box else None}
    except Exception:  # pragma: no cover
        return None


def label(corr: Dict) -> str:
    """The scope the judge is asked about."""
    parts = f"the route from {corr['origin']} to {corr['destination']}"
    if corr.get("region"):
        parts += f", {corr['region']}"
    return parts + " (the places on the way, near the start and around the destination all count)"


def _pin(poi: Dict) -> Optional[Tuple[float, float]]:
    try:
        return r909._poi_pin(poi)
    except Exception:
        return None


def stop_in_corridor(poi: Dict, corr: Optional[Dict]) -> bool:
    """In the padded A-to-B box, or the address names the region / origin / destination."""
    if not corr or not isinstance(poi, dict):
        return False
    pt = _pin(poi)
    if pt is not None and corr.get("box") and rc.in_box(corr["box"], pt[0], pt[1]):
        return True
    addr = rc.fold(str(poi.get("address") or ""))
    if not addr:
        return False
    for place in (corr.get("region"), corr.get("origin"), corr.get("destination")):
        for piece in re.split(r"[,;]", place or ""):
            f = rc.fold(piece).strip()
            if len(f) >= 3 and re.search(r"\b" + re.escape(f) + r"\b", addr):
                return True
    return False


def may_record(corr: Optional[Dict]) -> bool:
    """A rejection against a route's destination / corridor is never persisted."""
    return corr is None
