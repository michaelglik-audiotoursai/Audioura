"""[LOCAL-905] Pool reuse runs the same guards as a fresh stop.

Wave 50 (cloud tour 552): the stop-pool reuse path returned a pooled pagoda whose pin was a raw model pin from an
earlier run (~33 km off) and whose body was empty, because the 900B / 902 / 903 pin checks and the body floor
only ever ran on freshly generated stops. Pure and offline: the caller supplies the scope context.

Context dict (all optional):
    scope_center   (lat, lng)  geocoded centre of the request
    scope_precision "BUILDING" | "CORRIDOR" | "DISTRICT" | "CITY" | ""   (the 900B vocabulary)
    route_box      [south, north, west, east]
    place_ref      (lat, lng)  the verified (903 snapped) place reference of a single-place request
"""
import math
import re
from typing import Callable, Dict, List, Optional, Tuple

SMALL_TOUR_MAX_STOPS = 2
PLACE_REF_KM = 15.0
_SCOPE_KM = {"BUILDING": 15.0, "CORRIDOR": 15.0, "DISTRICT": 15.0, "CITY": 25.0}
_UNKNOWN_PRECISION_KM = 100.0
_ROUTE_MARGIN_KM = 10.0
_SINGLE_SCOPES = ("DISTRICT", "BUILDING")
_SENT = re.compile(r"[^.!?]*[A-Za-z0-9][^.!?]*[.!?]?")


def skip_pool_for_small_tour(total_stops) -> bool:
    """Item 2: a 1-2 stop (single-place) tour never reuses the pool."""
    try:
        n = int(total_stops or 0)
    except (TypeError, ValueError):
        return False
    return 0 < n <= SMALL_TOUR_MAX_STOPS


def _coord(value) -> Optional[Tuple[float, float]]:
    if value is None:
        return None
    try:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            lat, lng = float(value[0]), float(value[1])
        else:
            parts = [x for x in re.split(r"[,\s;]+", str(value).strip()) if x]
            if len(parts) < 2:
                return None
            lat, lng = float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        return None
    if abs(lat) > 90 or abs(lng) > 180 or (lat == 0 and lng == 0):
        return None
    return (lat, lng)


def _km(a, b) -> float:
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def body_reject(row: Dict) -> str:
    """'' when the pooled row has a real body, else the reason. A body needs at least one sentence of 3+ words."""
    body = str(row.get("narration") or "").strip()
    if not body:
        return "empty body"
    if body.startswith("[") or "GENERATION_FAILED" in body:
        return "failed-generation body"
    for m in _SENT.finditer(body):
        if len(re.findall(r"[A-Za-z0-9']+", m.group(0))) >= 3:
            return ""
    return "no content sentence"


def pin_reject(row: Dict, ctx: Optional[Dict]) -> str:
    """'' when the pooled pin is acceptable (or cannot be judged), else the reason."""
    ctx = ctx or {}
    pin = _coord(row.get("coordinates"))
    if pin is None:
        return ""        # no pin: nothing to test (the fresh path's own no-pin rules apply downstream)
    box = ctx.get("route_box")
    if box and len(box) >= 4:
        m_lat = _ROUTE_MARGIN_KM / 111.0
        m_lng = _ROUTE_MARGIN_KM / (111.0 * max(0.2, math.cos(math.radians((box[0] + box[1]) / 2.0))))
        if not (box[0] - m_lat <= pin[0] <= box[1] + m_lat and box[2] - m_lng <= pin[1] <= box[3] + m_lng):
            return "pin outside the route box + 10 km"
    else:
        centre = _coord(ctx.get("scope_center"))
        prec = str(ctx.get("scope_precision") or "").upper()
        if centre is not None:
            limit = _SCOPE_KM.get(prec, _UNKNOWN_PRECISION_KM)
            km = _km(pin, centre)
            if km > limit:
                return f"pin {km:.0f} km from the scope centre > {limit:.0f} km"
    ref = _coord(ctx.get("place_ref"))
    if ref is not None and str(ctx.get("scope_precision") or "").upper() in _SINGLE_SCOPES:
        km = _km(pin, ref)
        if km > PLACE_REF_KM:
            return f"pin {km:.0f} km from the verified place reference > {PLACE_REF_KM:.0f} km"
    return ""


def row_reject(row: Dict, ctx: Optional[Dict]) -> str:
    return body_reject(row) or pin_reject(row, ctx)


def filter_rows(rows: List[Dict], ctx: Optional[Dict], log: Optional[Callable[[str], None]] = None
                ) -> Tuple[List[Dict], int]:
    """Item 1. Skip-only: returns (kept, rejected_count); nothing is deleted from the pool."""
    emit = log or (lambda _m: None)
    kept, n = [], 0
    for r in rows or []:
        why = row_reject(r, ctx)
        if why:
            n += 1
            emit(f"  [LOCAL-905] pool row '{r.get('title', '')}' rejected: {why}")
        else:
            kept.append(r)
    return kept, n


def build_context(location: str, total_stops=None, resolver: Optional[Callable] = None) -> Dict:
    """Best-effort scope context for a pool reuse (network via area_resolver; {} on any failure)."""
    ctx: Dict = {}
    try:
        if resolver is None:
            from area_resolver import resolve_area as resolver
        area = resolver(location)
        if area is None:
            return ctx
        if getattr(area, "center_lat", 0) or getattr(area, "center_lng", 0):
            ctx["scope_center"] = (area.center_lat, area.center_lng)
        if getattr(area, "place_ref_precision", "") == "place":
            ctx["place_ref"] = (area.place_ref_lat, area.place_ref_lng)
            ctx["scope_center"] = ctx["place_ref"]
            ctx["scope_precision"] = "DISTRICT"
        elif getattr(area, "neighborhood_name", ""):
            ctx["scope_precision"] = "DISTRICT"
        elif getattr(area, "city_name", ""):
            ctx["scope_precision"] = "CITY"
    except Exception:
        return {}
    return ctx


_STOP_HEAD = re.compile(r"(?mi)^Stop\s+\d+\s*:")
_COORD_LINE = re.compile(r"(?mi)^Coordinates\s*:\s*(.+?)\s*$")


def first_stop_pin(text: str):
    """Item 4: the first delivered stop's pin from the delivered text, (None, None) when it has none."""
    try:
        heads = list(_STOP_HEAD.finditer(text or ""))
        if not heads:
            return (None, None)
        end = heads[1].start() if len(heads) > 1 else len(text)
        m = _COORD_LINE.search(text, heads[0].end(), end)
        c = _coord(m.group(1)) if m else None
        return c if c else (None, None)
    except Exception:
        return (None, None)
