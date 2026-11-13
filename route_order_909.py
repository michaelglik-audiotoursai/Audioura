"""route_order_909.py -- LOCAL-909: an "A to B" tour starts at A, ends at B, and every stop carries a real pin.

Live proof 907E ("<Origin> to <Mountain>, <Province>, <Country>", driving, 3 stops) shipped:

  1. a route that started at the wrong end: stop 1 sat 45 km SOUTH of the origin, stop 2 back near it
  2. a stop pin in the sea (the model's coordinate, no reference, inside the padded province box)
  3. a last stop with no Coordinates (the 870 rule cleared its model pin), so its leg had no fillings
  4. no Directions from the origin to stop 1

Everything here is deterministic, name-free (D769) and offline-testable: every lookup is an injected callable.

  parse_route_request    "<A> to <B>[, region]" / "from <A> to <B>" -> origin, destination, region
  along / order_stops    the stops ordered by their projection on the A->B line; no stop doubles back > 20 %
  water_pins             an unverified model pin with no land address (reverse geocode) is unverified
  finalize_route_pins    water check -> restore every missing pin -> re-order on the final pins
  origin_directions      the first Directions line starts from the origin, not from stop 1
  ensure_text_coordinates  safety net: a delivered stop block without a Coordinates line gets the final pin
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import route_content_896 as rc

TAG = "[LOCAL-909]"
MAX_BACKTRACK = 0.20          # a stop may go back toward the origin by at most 20 % of the A->B distance
ROAD_CIRCUITY = 1.2           # road km per straight-line km when only two pins are known

Pt = Tuple[float, float]

# ── job-scoped state (same container the 896 route state uses) ────────────────────────────────────────────
_STATE = rc._ScopedDict(dict)


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def set_request(location: str, mode: str = "") -> Optional[Dict]:
    """Remember the generation's transport mode and its "A to B" request (None when it is not one)."""
    _STATE.clear()
    _STATE["mode"] = (mode or "").strip().lower()
    info = parse_route_request(location)
    if info:
        _STATE["route"] = info
    return info


def clear() -> None:
    _STATE.clear()


def is_driving() -> bool:
    return _STATE.get("mode", "") in ("vehicle", "driving", "car", "drive")


def route() -> Optional[Dict]:
    return _STATE.get("route")


def set_final_pins(pins: Dict[str, Pt]) -> None:
    _STATE["pins"] = dict(pins)


def final_pins() -> Dict[str, Pt]:
    return _STATE.get("pins") or {}


# ── request ────────────────────────────────────────────────────────────────────────────────────────────────
_NOT_A_PLACE = re.compile(r"(?i)\b(?:tour|walk(?:ing)?|driving|drive|cycling|biking|trip|guide|itinerary|visit|"
                          r"things|places|best)\b")
_A_TO_B = re.compile(r"^\s*(?:from\s+)?(?P<o>[^,]{2,60}?)\s+to\s+(?P<d>[^,]{2,60}?)\s*(?:,\s*(?P<r>.+?))?\s*$", re.I)


_LINKS = frozenset("of the de la le les du des del della da do dos das di van von sur upon on en am an im and & y e i at".split())
_OPENERS = frozenset("introduction intro welcome back return road journey gateway answer key letter ode tribute ticket "
                     "passport path way hello goodbye farewell homage guide ode".split())


def _proper_name(x: str) -> bool:
    """[LEAD review] A place name: every word capitalised (or a digit), except small linking words, and it starts capitalised."""
    ws = [w for w in re.split(r"[\s\-–—/]+", x.strip()) if w]
    if not ws or not (ws[0][:1].isupper() or ws[0][:1].isdigit()):
        return False
    return all(w[:1].isupper() or w[:1].isdigit() or w.lower() in _LINKS or w.startswith("(") for w in ws)


def parse_route_request(location: str) -> Optional[Dict]:
    """``{"origin", "destination", "region"}`` for "<A> to <B>[, region ...]" or "from <A> to <B>"; None otherwise.
    Grammar only: no place list."""
    m = _A_TO_B.match(location or "")
    if not m:
        return None
    o, d = m.group("o").strip(" .;"), m.group("d").strip(" .;")
    if not o or not d or rc.fold(o) == rc.fold(d) or _NOT_A_PLACE.search(o) or _NOT_A_PLACE.search(d):
        return None
    if not (_proper_name(o) and _proper_name(d)) or rc.fold(o).split()[0] in _OPENERS:
        return None          # [LEAD review] "Welcome to Saigon street food", "Back to the Future …" are not routes
    return {"origin": o, "destination": d, "region": (m.group("r") or "").strip()}


# ── geometry ───────────────────────────────────────────────────────────────────────────────────────────────
def km_between(a: Pt, b: Pt) -> float:
    dl = math.radians(b[0] - a[0])
    dg = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2.0))
    return 6371.0 * math.hypot(dl, dg)


def along(pt: Pt, a: Pt, b: Pt) -> float:
    """Projection of ``pt`` on the A->B line as a fraction of |AB| (0 = at A, 1 = at B; < 0 behind A, > 1 past B)."""
    cos = math.cos(math.radians((a[0] + b[0]) / 2.0))

    def xy(p: Pt) -> Tuple[float, float]:
        return (math.radians(p[1] - a[1]) * cos * 6371.0, math.radians(p[0] - a[0]) * 6371.0)
    bx, by = xy(b)
    px, py = xy(pt)
    n2 = bx * bx + by * by
    return 0.0 if n2 <= 0 else (px * bx + py * by) / n2


def max_backtrack(ts: Sequence[Optional[float]]) -> float:
    """Largest step back toward A between two consecutive stops with a known position (fraction of |AB|)."""
    known = [t for t in ts if t is not None]
    return max([0.0] + [known[i] - known[i + 1] for i in range(len(known) - 1)])


def order_stops(pins: Sequence[Optional[Pt]], a: Pt, b: Pt, dest_idx: Optional[int] = None) -> List[int]:
    """Indices in A->B order: sorted by projection, the destination stop last. A stop with no pin keeps its place
    right after the stop that preceded it in the given order (never dropped). Deterministic: ties on the index."""
    n = len(pins)
    ts = [None if p is None else along(p, a, b) for p in pins]
    known = sorted((i for i in range(n) if ts[i] is not None and i != dest_idx), key=lambda i: (ts[i], i))
    out: List[int] = list(known)
    if dest_idx is not None:
        out.append(dest_idx)
    for i in range(n):
        if ts[i] is not None or i == dest_idx:
            continue
        prev = next((j for j in range(i - 1, -1, -1) if j in out), None)
        at = 0 if prev is None else out.index(prev) + 1
        if dest_idx is not None and out and at > out.index(dest_idx):
            at = out.index(dest_idx)              # the destination stays last
        out.insert(at, i)
    return out


def _names(title: str, place: str) -> bool:
    return rc._names(title, place)


def dest_index(titles: Sequence[str], destination: str) -> Optional[int]:
    for i, t in enumerate(titles):
        if destination and _names(t, destination):
            return i
    return None


# ── pins ───────────────────────────────────────────────────────────────────────────────────────────────────
def _poi_pin(p: Dict) -> Optional[Pt]:
    import pin_snap
    if p.get("_no_coordinate"):
        return None
    return pin_snap._poi_coord(p)


def _unverified(p: Dict) -> bool:
    import pin_fallback_906d as pf
    try:
        return bool(pf._unverified(p))
    except Exception:
        return False


def _set_pin(p: Dict, pt: Pt, approximate: bool) -> None:
    p["coordinates"] = f"{pt[0]:.6f}, {pt[1]:.6f}"
    if "latitude" in p or "longitude" in p:
        p["latitude"], p["longitude"] = pt[0], pt[1]
    if approximate:
        p["coordinates_approximate"] = True
    p.pop("_no_coordinate", None)


def _clear_pin(p: Dict) -> None:
    p["coordinates"] = ""
    for k in ("latitude", "longitude", "lat", "lng", "lon"):
        if k in p:
            p[k] = None
    p["_no_coordinate"] = True


def water_pins(poi_list: List[Dict], land_fn: Optional[Callable], log: Optional[Callable] = None) -> List[int]:
    """0-based indices whose UNVERIFIED model pin has no land address (``land_fn(lat, lng)`` -> True / False /
    None; None = lookup failed = unknown, never water). Flags ``_pin_water_909``."""
    emit = _emit(log)
    out: List[int] = []
    if land_fn is None:
        return out
    for i, p in enumerate(poi_list or []):
        try:
            pt = _poi_pin(p)
            if pt is None or not _unverified(p):
                continue
            if land_fn(pt[0], pt[1]) is False:
                p["_pin_water_909"] = True
                out.append(i)
                emit(f"  {TAG} stop={i + 1} pin {pt[0]:.4f},{pt[1]:.4f} has no land address (open water) -> unverified")
        except Exception:
            continue
    return out


def _in_box(box: Optional[Sequence[float]], pt: Pt) -> bool:
    return not box or (box[0] <= pt[0] <= box[1] and box[2] <= pt[1] <= box[3])


def _pick_reference(i: int, p: Dict, rows: Sequence[Dict], route_refs: Optional[Dict], box, dest: str,
                    dest_pt: Optional[Pt]) -> Optional[Tuple[Pt, str, bool]]:
    """(pin, source, approximate) for stop i from a REAL source, best first; None when there is none."""
    row = rows[i] if rows and i < len(rows) and isinstance(rows[i], dict) else {}
    if row.get("snapped") and row.get("new_coordinate"):
        c = tuple(row["new_coordinate"])
        if _in_box(box, c):
            return c, "snap", False
    ref = row.get("reference")
    if ref and _in_box(box, tuple(ref[:2])) and not row.get("rejected_900b"):
        return (float(ref[0]), float(ref[1])), "place reference", False
    rr = (route_refs or {}).get(i)
    if rr and rr.get("coord") and _in_box(box, tuple(rr["coord"])):
        return tuple(rr["coord"]), "route place reference", False
    wl, wg = p.get("wikidata_lat"), p.get("wikidata_lng")
    if wl is not None and wg is not None and _in_box(box, (float(wl), float(wg))):
        return (float(wl), float(wg)), "wikidata", False
    pool = p.get("pool_coordinates") or p.get("_pool_coordinates")
    if pool:
        try:
            c = (float(pool[0]), float(pool[1]))
            if _in_box(box, c):
                return c, "pool", False
        except Exception:
            pass
    if dest and dest_pt and _names(str(p.get("name", "")), dest) and _in_box(box, dest_pt):
        return dest_pt, "destination geocode", True
    return None


def restore_pins(poi_list: List[Dict], rows: Sequence[Dict], a: Optional[Pt], b: Optional[Pt], dest: str,
                 dest_pt: Optional[Pt], box=None, route_refs: Optional[Dict] = None,
                 log: Optional[Callable] = None) -> List[int]:
    """Every stop of a route carries a pin. A stop with none (or a water pin) gets, in order: its snap /
    place reference, the route place reference, a Wikidata / pool coordinate, the destination's own geocode, its
    in-box land model pin (approximate), else a point between its neighbours on the A->B line (approximate).
    Logs ``[LOCAL-909] Stop N delivered without coordinates -> <fix>``. Returns the restored 0-based indices."""
    emit = _emit(log)
    fixed: List[int] = []
    n = len(poi_list or [])
    for i, p in enumerate(poi_list or []):
        try:
            water = bool(p.get("_pin_water_909"))
            cur = _poi_pin(p)
            if cur is not None and not water:
                continue
            src = _pick_reference(i, p, rows, route_refs, box, dest, dest_pt)
            if src:
                pt, why, approx = src
                _set_pin(p, pt, approx)
                p.pop("_pin_water_909", None)
                fixed.append(i)
                emit(f"  {TAG} Stop {i + 1} delivered without coordinates -> restored from {why} "
                     f"{pt[0]:.4f},{pt[1]:.4f}" if cur is None else
                     f"  {TAG} Stop {i + 1} offshore pin {cur[0]:.4f},{cur[1]:.4f} -> replaced by {why} "
                     f"{pt[0]:.4f},{pt[1]:.4f}")
                continue
            if cur is None and p.get("_model_pin_909") and _in_box(box, p["_model_pin_909"]):
                pt = tuple(p["_model_pin_909"])
                _set_pin(p, pt, True)
                fixed.append(i)
                emit(f"  {TAG} Stop {i + 1} delivered without coordinates -> kept the in-scope model pin "
                     f"{pt[0]:.4f},{pt[1]:.4f} (approximate)")
                continue
            if a and b:
                lo = next((_poi_pin(poi_list[j]) for j in range(i - 1, -1, -1)
                           if _poi_pin(poi_list[j]) is not None and not poi_list[j].get("_pin_water_909")), None) or a
                hi = next((_poi_pin(poi_list[j]) for j in range(i + 1, n)
                           if _poi_pin(poi_list[j]) is not None and not poi_list[j].get("_pin_water_909")), None) or b
                pt = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0)
                _set_pin(p, pt, True)
                p.pop("_pin_water_909", None)
                fixed.append(i)
                emit(f"  {TAG} Stop {i + 1} delivered without coordinates -> placed between its neighbours on "
                     f"the route {pt[0]:.4f},{pt[1]:.4f} (approximate)")
            elif cur is not None and water:
                _clear_pin(p)
                emit(f"  {TAG} Stop {i + 1} offshore pin {cur[0]:.4f},{cur[1]:.4f} -> cleared (no reference)")
        except Exception as err:  # pragma: no cover
            emit(f"  {TAG} pin restore for stop {i + 1} skipped (non-fatal): {err}")
    return fixed


def reorder_on_pins(poi_list: List[Dict], a: Pt, b: Pt, destination: str, log: Optional[Callable] = None,
                    only_if_backtrack: bool = False) -> List[Dict]:
    """A new list in A->B order (the destination stop last). With ``only_if_backtrack`` the order is changed
    only when the given one doubles back by more than MAX_BACKTRACK (the post-writing pass)."""
    emit = _emit(log)
    pins = [_poi_pin(p) for p in poi_list]
    ts = [None if pt is None else along(pt, a, b) for pt in pins]
    di = dest_index([str(p.get("name", "")) for p in poi_list], destination)
    back = max_backtrack(ts)
    if only_if_backtrack and back <= MAX_BACKTRACK and (di is None or di == len(poi_list) - 1):
        emit(f"  {TAG} route order kept (largest step back {back * 100:.0f}% <= {MAX_BACKTRACK * 100:.0f}%)")
        return poi_list
    order = order_stops(pins, a, b, di)
    new = [poi_list[i] for i in order]
    if order != list(range(len(poi_list))):
        emit(f"  {TAG} route ordered along the origin->destination line (was doubling back {back * 100:.0f}%): "
             f"{[str(p.get('name', '')) for p in new]}")
    return new


def endpoints_pts(geocode_fn: Optional[Callable], log: Optional[Callable] = None) -> Tuple[Optional[Pt], Optional[Pt]]:
    """(origin pin, destination pin) of the request, geocoded INSIDE its region (a bare name resolves to a
    same-named place on another continent). Cached for the generation; (None, None) when it is not a route."""
    info = route()
    if not info or geocode_fn is None:
        return None, None
    if "endpoints" in _STATE:
        return _STATE["endpoints"]
    emit = _emit(log)

    def one(name: str) -> Optional[Pt]:
        region = info.get("region") or ""
        short = re.sub(r"(?i)\s+(?:mountain|mount|mt\.?|hill|peak|lake|beach|temple|pagoda|park)$", "", name).strip()
        for q in dict.fromkeys([f"{name}, {region}" if region else name, f"{short}, {region}" if region and short else "",
                                name]):
            if not q:
                continue
            try:
                hit = geocode_fn(q)
            except Exception:
                hit = None
            if hit:
                return float(hit[0]), float(hit[1])
        return None
    a, b = one(info["origin"]), one(info["destination"])
    if a and b and km_between(a, b) < 1.0:
        a = b = None
    if a and b and km_between(a, b) > 400.0:      # [LEAD review] a same-named place elsewhere: not one drive
        emit(f"  {TAG} route endpoints {km_between(a, b):.0f} km apart -> not treated as a route")
        a = b = None
    _STATE["endpoints"] = (a, b)
    emit(f"  {TAG} route endpoints: origin={a} destination={b}")
    return a, b


def order_poi_list(poi_list: List[Dict], geocode_fn: Optional[Callable] = None, land_fn: Optional[Callable] = None,
                   log: Optional[Callable] = None) -> List[Dict]:
    """The pre-writing order: the stops by their projection on the origin->destination line, the destination stop
    last. A pin in open water (``land_fn``) or no pin leaves the stop in place (the post-snap pass fixes it with its
    final pin). Never raises; unchanged when the request is not "A to B" or an end cannot be placed."""
    emit = _emit(log)
    try:
        info = route()
        if not info or len(poi_list or []) < 2:
            return poi_list
        a, b = endpoints_pts(geocode_fn, log)
        if not (a and b):
            emit(f"  {TAG} route order skipped: origin/destination not placed")
            return poi_list
        pins = []
        for i, p in enumerate(poi_list):
            pt = _poi_pin(p)
            if pt is not None and land_fn is not None and _unverified(p):
                try:
                    if land_fn(pt[0], pt[1]) is False:
                        p["_pin_water_909"] = True
                        emit(f"  {TAG} stop={i + 1} pin {pt[0]:.4f},{pt[1]:.4f} is in open water -> ignored for ordering")
                        pt = None
                except Exception:
                    pass
            pins.append(pt)
        di = dest_index([str(p.get("name", "")) for p in poi_list], info["destination"])
        order = order_stops(pins, a, b, di)
        new = [poi_list[i] for i in order]
        back = max_backtrack([None if pins[i] is None else along(pins[i], a, b) for i in order])
        if order != list(range(len(poi_list))):
            emit(f"  {TAG} route ordered along {info['origin']!r} -> {info['destination']!r} "
                 f"(largest step back {back * 100:.0f}%): {[str(p.get('name', '')) for p in new]}")
        else:
            emit(f"  {TAG} route order already runs {info['origin']!r} -> {info['destination']!r}")
        return new
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} route order skipped (non-fatal): {err}")
        return poi_list


def finalize_route_pins(poi_list: List[Dict], rows: Sequence[Dict], info: Optional[Dict], origin_pt: Optional[Pt],
                        dest_pt: Optional[Pt], box=None, route_refs: Optional[Dict] = None,
                        land_fn: Optional[Callable] = None, log: Optional[Callable] = None) -> List[Dict]:
    """After the snap and 906D's last resort: (1) the water check, (2) every stop gets a pin, (3) the stops are
    re-ordered on the FINAL pins when they double back. Returns the (possibly re-ordered) list; never raises."""
    emit = _emit(log)
    try:
        if not info or not poi_list:
            return poi_list
        dest = info.get("destination") or ""
        for p in poi_list:                       # remember the model's own in-scope pin before a clear
            c = _poi_pin(p)
            if c is not None:
                p.setdefault("_model_pin_909", c)
        for p in poi_list:                       # a stale water flag: the snap has since placed it on a reference
            if p.get("_pin_water_909") and not _unverified(p):
                p.pop("_pin_water_909", None)
        water_pins(poi_list, land_fn, log)
        a = origin_pt
        d_i = dest_index([str(p.get("name", "")) for p in poi_list], dest)
        b = dest_pt or (_poi_pin(poi_list[d_i]) if d_i is not None else None)
        restore_pins(poi_list, rows, a, b, dest, dest_pt, box, route_refs, log)
        if a and b:
            poi_list = reorder_on_pins(poi_list, a, b, dest, log, only_if_backtrack=True)
        set_final_pins({str(p.get("name", "")): pt for p in poi_list for pt in [_poi_pin(p)] if pt})
        return poi_list
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} route pin pass skipped (non-fatal): {err}")
        return poi_list


# ── text ───────────────────────────────────────────────────────────────────────────────────────────────────
_COORD_LINE = re.compile(r"(?mi)^Coordinates:\s*-?\d")
_ADDR_LINE = re.compile(r"(?mi)^Address:[^\n]*\n?")
_DIR_LINE = re.compile(r"(?mi)^(Directions:\s*)(.*)$")
_COMPASS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")


def compass(a: Pt, b: Pt) -> str:
    ang = math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2.0)), b[0] - a[0])) % 360
    return _COMPASS[int((ang + 22.5) // 45) % 8]


def ensure_text_coordinates(tour_text: str, pins: Optional[Dict[str, Pt]] = None,
                            log: Optional[Callable] = None) -> str:
    """A stop block without a ``Coordinates:`` line gets the final pin of the stop of that title."""
    emit = _emit(log)
    pins = pins if pins is not None else final_pins()
    if not tour_text or not pins:
        return tour_text
    by = {rc.fold(k).strip(): v for k, v in pins.items()}
    out, pos = [], 0
    for s, e, num, title in rc._stop_blocks(tour_text):
        blk = tour_text[s:e]
        if _COORD_LINE.search(blk):
            continue
        pt = by.get(rc.fold(title).strip())
        if pt is None:
            continue
        line = f"Coordinates: {pt[0]:.4f}, {pt[1]:.4f}\n\n"
        m = _ADDR_LINE.search(blk)
        if m:
            at = s + m.end()
            ins = line if blk[m.end() - 1:m.end()] == "\n" else "\n\n" + line
            if blk[m.end():m.end() + 1] == "\n":          # the Address line is followed by its blank line
                at += 1
        else:
            hdr_end = blk.find("\n")
            at = s + (hdr_end + 1 if hdr_end >= 0 else len(blk))
            ins = line if blk[hdr_end + 1:hdr_end + 2] == "\n" else "\n" + line
            if blk[hdr_end + 1:hdr_end + 2] == "\n":
                at += 1
        out.append((at, ins))
        emit(f"  {TAG} Stop {num} delivered without coordinates -> Coordinates line restored from the final pin")
    for at, ins in sorted(out, reverse=True):
        tour_text = tour_text[:at] + ins + tour_text[at:]
    return tour_text


def origin_directions(tour_text: str, origin: str, origin_pt: Optional[Pt], log: Optional[Callable] = None) -> str:
    """The first Directions line starts from the ORIGIN: when it begins "From <Stop 1>", the leg origin -> Stop 1
    is put in front of it (distance + compass from the two pins). With no Directions line in Stop 1 one is added."""
    emit = _emit(log)
    if not tour_text or not origin:
        return tour_text
    blocks = rc._stop_blocks(tour_text)
    if not blocks:
        return tour_text
    s, e, num, title = blocks[0]
    blk = tour_text[s:e]
    cm = re.search(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", blk)
    lead = f"From {origin}, head to {title}"
    if origin_pt and cm:
        pt = (float(cm.group(1)), float(cm.group(2)))
        km = km_between(origin_pt, pt) * ROAD_CIRCUITY
        if km >= 1.0:
            lead = (f"From {origin}, head {compass(origin_pt, pt)} to {title} — it is roughly {km:.0f} km "
                    f"away.")
        else:
            lead = f"From {origin}, head to {title}."
    else:
        lead += "."
    dm = _DIR_LINE.search(blk)
    if dm and re.match(r"(?i)\s*from\s+" + re.escape(origin) + r"\b", dm.group(2)):
        return tour_text                              # already starts at the origin
    if dm:
        new_blk = blk[:dm.start()] + dm.group(1) + lead + " " + dm.group(2) + blk[dm.end():]
    else:
        new_blk = blk.rstrip("\n") + f"\n\nDirections: {lead}\n\n"
    emit(f"  {TAG} first Directions now start from the origin {origin!r} (was 'From {title}')")
    return tour_text[:s] + new_blk + tour_text[e:]


def finalize_text(tour_text: str, log: Optional[Callable] = None) -> str:
    """Delivery pass for an "A to B" tour (a no-op for any other): every stop block carries a Coordinates line and the
    first Directions start from the origin. Never raises."""
    emit = _emit(log)
    try:
        info = route()
        if not info or not tour_text:
            return tour_text
        out = ensure_text_coordinates(tour_text, None, log)
        a, _b = _STATE.get("endpoints") or (None, None)
        return origin_directions(out, info["origin"], a, log)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} delivery pass skipped (non-fatal): {err}")
        return tour_text
