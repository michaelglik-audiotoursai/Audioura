"""pin_proof.py — LOCAL-791B item 3.

Prove a tour's pins. For every stop, compare the stop's SHIPPED coordinate to an
independent geocode of the SAME name (Serper Places first, then Nominatim) and
report the distance in metres. Target: every pin within ≤ 100 m of the real place.

WHY (ticket): LOCAL-791 item 3 was implemented (repair_inherited_coordinates), but
the LOCAL-791 submission "reported no distances" — the live table only listed the
pins, never proved them against an authority. This module produces the missing
proof: a per-stop distance table and a pass/fail against the 100 m target, run
after a live generation so the submission can show real numbers.

HOW:
  * ``parse_coordinate(s)``        — "10.7769, 106.7030" → (10.7769, 106.7030).
  * ``parse_tour_stops(text)``     — pull (title, coordinate) for each "Stop N:"
                                     block of a delivered tour.
  * ``reference_for_name(...)``    — geocode a stop NAME via Serper Places (if
                                     enabled) else Nominatim, returning
                                     (lat, lng, source) or None.
  * ``pin_report(stops, scope,…)`` — build the per-stop distance rows + a summary.
  * ``format_pin_table(report)``   — a Markdown table for the submission.

The geocoders are INJECTABLE (``serper_fn`` / ``nominatim_fn``) so the report is
unit-testable offline; in a live run the defaults call the real
``places_search.places_search`` and ``geocode_stops.geocode``. Distances use the
project's own ``geocode_stops.haversine_m`` so the numbers match the repair gate's.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "parse_coordinate",
    "parse_tour_stops",
    "reference_for_name",
    "pin_report",
    "format_pin_table",
    "PIN_TARGET_M",
]

PIN_TARGET_M = 100.0

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_COORD_LINE_RE = re.compile(r"(?mi)^\s*Coordinates:\s*(.+)$")
_COORD_PAIR_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*[,/ ]\s*(-?\d+(?:\.\d+)?)")


def parse_coordinate(s: str) -> Optional[Tuple[float, float]]:
    """Parse a "lat, lng" string into (lat, lng) floats, or None.

    Accepts comma, slash or whitespace separators. Rejects an out-of-range pair
    (|lat|>90 or |lng|>180) so a stray number pair is not read as a coordinate."""
    if not s:
        return None
    m = _COORD_PAIR_RE.search(str(s))
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None
    if abs(lat) > 90 or abs(lng) > 180:
        return None
    return (lat, lng)


def parse_tour_stops(text: str) -> List[Dict]:
    """Extract the ordered stops of a delivered tour as
    ``[{"title": str, "coordinate": (lat,lng)|None}, …]``.

    Pairs each "Stop N:" header with the next "Coordinates:" line in the text.
    A stop with no coordinate line gets coordinate=None (still reported, flagged
    as unproven)."""
    if not text:
        return []
    out: List[Dict] = []
    # Positions of each stop header, so a Coordinates line is bound to the stop it
    # falls under (the first coordinate line AFTER the header, before the next).
    headers = list(_STOP_HEADER_RE.finditer(text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        cm = _COORD_LINE_RE.search(block)
        coord = parse_coordinate(cm.group(1)) if cm else None
        out.append({"title": h.group(1).strip(), "coordinate": coord})
    return out


# ───────────────────────── reference geocoders ──────────────────────────────
def _default_serper(name: str, scope: str,
                    scope_center: Optional[Tuple[float, float]]
                    ) -> Optional[Tuple[float, float]]:
    """Serper Places lookup for one NAME; returns the first result's (lat, lng)
    or None.

    Pin proof verifies a SPECIFIC named place, so it must NOT scope-bind the
    result (a real pagoda 4 km from the city centre is the right answer, not a
    spillover to drop). We call Serper Places directly with an `ll` bias toward the
    scope centre and take the nearest/first result; the metered door
    (serper_meter) still prices the call. Falls back to the scope-bound
    places_search when the raw door is unavailable."""
    try:
        import places_search as _ps
        if not _ps.serper_places_enabled():
            return None
        ll = None
        if scope_center:
            try:
                ll = f"@{float(scope_center[0])},{float(scope_center[1])},12z"
            except (TypeError, ValueError, IndexError):
                ll = None
        raw = _ps._serper_places_call(name, ll)
        if not raw and scope:
            # Disambiguate a bare name to the right city by naming it in the query.
            raw = _ps._serper_places_call(f"{name}, {scope}", ll, location=scope)
        if raw:
            r = raw[0]
            try:
                return (float(r.get("lat")), float(r.get("lon")),
                        str(r.get("title") or r.get("name") or ""))
            except (TypeError, ValueError):
                pass
        # Last resort: the scope-bound search (may drop an out-of-radius hit).
        recs = _ps.places_search(name, scope, scope_center=scope_center, limit=1)
    except Exception:
        return None
    if not recs:
        return None
    r = recs[0]
    try:
        return (float(r.get("lat")), float(r.get("lon")),
                str(r.get("title") or r.get("name") or ""))
    except (TypeError, ValueError):
        return None


def _default_nominatim(name: str, scope: str) -> Optional[Tuple[float, float]]:
    """Nominatim lookup via geocode_stops.geocode (name + scope town)."""
    try:
        import geocode_stops as _gs
        q = f"{name}, {scope}" if scope and scope.lower() not in name.lower() else name
        return _gs.geocode(q)
    except Exception:
        return None


def _bare_place_name(name: str) -> str:
    """Strip a trailing architectural-FEATURE word a narration title may append
    ("Notre-Dame Cathedral Basilica facade" → "Notre-Dame Cathedral Basilica";
    "Opera House grand staircase" → "Opera House"), plus a parenthetical gloss, so
    the reference lookup queries the PLACE, not a part of it. Conservative: only a
    known feature word at the very end is removed."""
    n = re.sub(r"\s*\([^)]*\)\s*", " ", name or "").strip()
    feature = (r"facade|portico|grand\s+staircase|staircase|vestibule|nave|"
               r"courtyard|altar|dome|spire|tower|entrance|lobby|atrium|"
               r"interior|exterior|rooftop|roof|garden|forecourt|steps|"
               r"main\s+hall|great\s+hall|hall")
    n2 = re.sub(r"\s+(?:" + feature + r")$", "", n, flags=re.IGNORECASE).strip()
    return n2 or n


def reference_for_name(name: str,
                       scope: str = "",
                       scope_center: Optional[Tuple[float, float]] = None,
                       serper_fn: Optional[Callable] = None,
                       nominatim_fn: Optional[Callable] = None,
                       max_reference_km: float = 15.0,
                       ) -> Optional[Tuple[float, float, str]]:
    """Independent reference coordinate for a stop NAME.

    Tries Serper Places first (the authority the places path itself uses), then
    Nominatim. Returns (lat, lng, source) where source is "serper" or "nominatim",
    or None when neither resolves. ``serper_fn``/``nominatim_fn`` override the
    default lookups for offline tests.

    SANITY BOUND: a reference more than ``max_reference_km`` from ``scope_center``
    is a same-name place in another city (Serper's bare-name match for "City Hall"
    returned Florida) — it is rejected and the next source is tried. The lookup
    uses the BARE place name (a trailing "facade"/"staircase"/… feature word and a
    parenthetical gloss are stripped) so a narration sub-part title still resolves
    to its building."""
    lookup_name = _bare_place_name(name)
    sfn = serper_fn or (lambda n: _default_serper(n, scope, scope_center))
    nfn = nominatim_fn or (lambda n: _default_nominatim(n, scope))

    def _in_scope(pt) -> bool:
        if not scope_center or not pt:
            return True
        try:
            return _haversine_m(pt, scope_center) / 1000.0 <= max_reference_km
        except Exception:
            return True

    try:
        s = sfn(lookup_name)
    except Exception:
        s = None
    if s and _in_scope((float(s[0]), float(s[1]))):
        # _default_serper returns (lat, lng, title); an injected serper_fn may
        # return (lat, lng) — then no name is available. Append the name only when
        # present so the legacy 3-tuple (lat, lng, source) shape is preserved.
        _sname = s[2] if (isinstance(s, (tuple, list)) and len(s) > 2) else ""
        return ((float(s[0]), float(s[1]), "serper", _sname) if _sname
                else (float(s[0]), float(s[1]), "serper"))
    try:
        n = nfn(lookup_name)
    except Exception:
        n = None
    if n and _in_scope((float(n[0]), float(n[1]))):
        _nname = n[2] if (isinstance(n, (tuple, list)) and len(n) > 2) else ""
        return ((float(n[0]), float(n[1]), "nominatim", _nname) if _nname
                else (float(n[0]), float(n[1]), "nominatim"))
    return None


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


def pin_report(stops: Sequence[Dict],
               scope: str = "",
               scope_center: Optional[Tuple[float, float]] = None,
               target_m: float = PIN_TARGET_M,
               serper_fn: Optional[Callable] = None,
               nominatim_fn: Optional[Callable] = None,
               ) -> Dict:
    """Build the pin-proof report for a list of ``{"title","coordinate"}`` stops.

    For each stop, geocode its NAME independently and compute the distance from its
    shipped coordinate to that reference. Returns::

        {"rows": [{"title","coordinate","reference","source","distance_m",
                   "within_target"}, …],
         "target_m": float,
         "proven": int,            # stops with a reference AND distance<=target
         "measured": int,          # stops with a reference (distance computed)
         "total": int,
         "all_within_target": bool}  # True when every MEASURED stop is within target
    """
    rows: List[Dict] = []
    measured = 0
    proven = 0
    for st in stops:
        title = st.get("title", "")
        coord = st.get("coordinate")
        ref = reference_for_name(title, scope, scope_center,
                                 serper_fn=serper_fn, nominatim_fn=nominatim_fn)
        row: Dict = {
            "title": title,
            "coordinate": coord,
            "reference": None,
            "source": None,
            "distance_m": None,
            "within_target": None,
        }
        if ref and coord:
            row["reference"] = (ref[0], ref[1])
            row["source"] = ref[2]
            d = _haversine_m(coord, (ref[0], ref[1]))
            row["distance_m"] = round(d, 1)
            row["within_target"] = d <= target_m
            measured += 1
            if row["within_target"]:
                proven += 1
        elif ref and not coord:
            row["reference"] = (ref[0], ref[1])
            row["source"] = ref[2]
        rows.append(row)
    all_within = measured > 0 and all(
        r["within_target"] for r in rows if r["distance_m"] is not None)
    return {
        "rows": rows,
        "target_m": target_m,
        "proven": proven,
        "measured": measured,
        "total": len(rows),
        "all_within_target": all_within,
    }


def _fmt_coord(c) -> str:
    if not c:
        return "—"
    return f"{c[0]:.5f}, {c[1]:.5f}"


def format_pin_table(report: Dict) -> str:
    """Render a pin-proof report as a Markdown table for the submission."""
    lines = [
        f"| # | Stop | Shipped pin | Reference ({report['target_m']:.0f} m target) "
        f"| Source | Distance | ≤ target |",
        "|---|------|-------------|-----------|--------|----------|----------|",
    ]
    for i, r in enumerate(report["rows"], 1):
        dist = "—" if r["distance_m"] is None else f"{r['distance_m']:.0f} m"
        ok = "—" if r["within_target"] is None else ("✅" if r["within_target"] else "❌")
        lines.append(
            f"| {i} | {r['title']} | {_fmt_coord(r['coordinate'])} "
            f"| {_fmt_coord(r['reference'])} | {r['source'] or '—'} | {dist} | {ok} |")
    lines.append("")
    lines.append(
        f"**{report['proven']}/{report['measured']} measured pins within "
        f"{report['target_m']:.0f} m** "
        f"(total stops: {report['total']}; "
        f"all measured within target: {report['all_within_target']}).")
    return "\n".join(lines)
