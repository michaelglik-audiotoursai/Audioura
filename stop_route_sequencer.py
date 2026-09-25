"""
Stop Route Sequencer — order the stops the user chose, then connect them.
==========================================================================
[LOCAL-522] A user lists stops in the order they *remembered* them, not the
order they *walk* them. Per D581, Directions and Orientation are properties of
a SEQUENCE, not of an individual stop — so they must be computed for the user's
own set, in the order that set is actually travelled, and never inherited from
some other tour.

This module does one job, purely and deterministically, with no network calls:

  1. ORDER the stops the user chose.
       • Walking / outdoor tours  -> geographic order (nearest-neighbour + 2-opt,
         the same proven routing used by generate_tour_text._compute_route_order,
         lifted here so it can be unit-tested in isolation).
       • Building / venue tours    -> the venue's own flow (floor, then a room /
         gallery sequence index the caller supplies), because inside a building
         "nearest in straight-line metres" is meaningless — you follow the rooms.
       • A stop with no position keeps its relative place; it is never dropped.

  2. HONOUR a forced order verbatim.
       When the user says "do them in THIS order", we do them in that order,
       full stop — no re-optimisation, no reshuffling.

  3. ATTACH the seams.
       Every stop hands off to the NEXT one by name ("directions"), and the last
       stop closes the tour cleanly ("closing"). A seam never points at a stop
       that is not in the list — the hand-off target is always drawn from the
       ordered list itself, so criterion 4 holds by construction.

The public entry point is `sequence_stops(...)`. It returns a NEW list of NEW
dicts (the input is never mutated) where each stop has, in addition to whatever
fields it arrived with:

    stop['position']   1-based position in the walked order
    stop['directions'] hand-off to the next stop (absent on the last stop)
    stop['closing']    closing line (present ONLY on the last stop)

Nothing here talks to an LLM or the network: seams are deterministic templates.
generate_tour_text.py may (and does) replace the templated directions text with
richer LLM-generated prose downstream — but the SEQUENCE and the hand-off TARGET
computed here are the contract, and they are testable without a key.
"""

from math import radians, sin, cos, asin, sqrt
import logging
import re


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers (self-contained; mirror generate_tour_text._haversine_km)
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(a, b):
    """Great-circle distance in km between two (lat, lng) tuples."""
    lat1, lon1 = a
    lat2, lon2 = b
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def _parse_coords(s):
    """Parse a 'lat, lng' string into (float, float), or None if unparseable."""
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', s or '')
    return (float(m.group(1)), float(m.group(2))) if m else None


def _extract_coord(poi):
    """Return (lat, lng) for a stop, or None if it has no usable position.

    Accepts the several shapes stops arrive in across the codebase:
      • poi['latitude'] / poi['longitude']         (numbers)
      • poi['wikidata_lat'] / poi['wikidata_lng']  (verified P625)
      • poi['coordinates'] = 'lat, lng'            (GPT-generated string)
    A (0.0, 0.0) pair is treated as "no position" — it is the null-island
    sentinel the generators emit when they have nothing.
    """
    if not isinstance(poi, dict):
        return None
    lat = poi.get('latitude')
    lng = poi.get('longitude')
    if lat is None or lng is None:
        lat = poi.get('wikidata_lat')
        lng = poi.get('wikidata_lng')
    if lat is None or lng is None:
        parsed = _parse_coords(poi.get('coordinates', ''))
        if parsed:
            lat, lng = parsed
    if lat is None or lng is None:
        return None
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if lat_f == 0.0 and lng_f == 0.0:
        return None
    return (lat_f, lng_f)


def _stop_name(poi):
    """Best-effort display name for a stop."""
    if isinstance(poi, dict):
        return (poi.get('name') or poi.get('title') or '').strip() or 'this stop'
    return str(poi).strip() or 'this stop'


def _normalize_name(name):
    """Loose comparison key for matching a forced-order label to a stop name."""
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


# ─────────────────────────────────────────────────────────────────────────────
# Geographic ordering: nearest-neighbour + 2-opt, every start tried (D559)
# ─────────────────────────────────────────────────────────────────────────────

def _order_geographic(poi_list):
    """Return poi_list reordered into a short walking route.

    Stops with coordinates are ordered by nearest-neighbour + 2-opt from every
    start (deterministic; ties break on lower start index). Stops without
    coordinates keep their relative place among the stops they sat between.
    A graceful no-op when fewer than 3 stops carry coordinates.
    """
    coords = [(i, _extract_coord(poi)) for i, poi in enumerate(poi_list)]
    with_coords = [(idx, c) for idx, c in coords if c is not None]
    without_coords = [idx for idx, c in coords if c is None]

    if len(with_coords) < 3:
        return list(poi_list)

    n = len(with_coords)

    def _route_distance(route):
        return sum(
            _haversine_km(with_coords[route[k]][1], with_coords[route[k + 1]][1])
            for k in range(len(route) - 1)
        )

    def _nearest_neighbour(start_idx):
        visited = [False] * n
        route = [start_idx]
        visited[start_idx] = True
        for _ in range(n - 1):
            cur = with_coords[route[-1]][1]
            best_next, best_dist = None, float('inf')
            for j in range(n):
                if not visited[j]:
                    d = _haversine_km(cur, with_coords[j][1])
                    if d < best_dist:
                        best_dist, best_next = d, j
            if best_next is not None:
                route.append(best_next)
                visited[best_next] = True
        return route

    def _two_opt(route):
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    cand = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                    if _route_distance(cand) < _route_distance(route) - 1e-12:
                        route, improved = cand, True
        return route

    best_order, best_len = None, None
    for start in range(n):
        cand = _two_opt(_nearest_neighbour(start))
        length = _route_distance(cand)
        if best_len is None or length < best_len - 1e-9:
            best_order, best_len = cand, length

    ordered_indices = [with_coords[o][0] for o in best_order]

    # Re-insert the no-coordinate stops after the last coord-stop that preceded
    # them in the ORIGINAL order, so they keep their relative place.
    if without_coords:
        result_indices = list(ordered_indices)
        for nc_idx in without_coords:
            insert_after = None
            for oi in range(nc_idx - 1, -1, -1):
                if oi in ordered_indices:
                    insert_after = result_indices.index(oi)
                    break
            if insert_after is not None:
                result_indices.insert(insert_after + 1, nc_idx)
            else:
                result_indices.insert(0, nc_idx)
    else:
        result_indices = ordered_indices

    return [poi_list[i] for i in result_indices]


# ─────────────────────────────────────────────────────────────────────────────
# Venue-flow ordering: floor, then the room/gallery sequence the venue defines
# ─────────────────────────────────────────────────────────────────────────────

def _order_venue_flow(poi_list):
    """Return poi_list reordered by the venue's own flow.

    Inside a building, straight-line distance is meaningless — you move through
    rooms in the order the building lays them out. The caller expresses that
    order with two optional numeric fields per stop:

        poi['floor']         lower floors first (default 0)
        poi['flow_index']    position within the floor / gallery run (default 0)

    Ordering is a STABLE sort on (floor, flow_index), so stops that share a key
    — or carry no flow hint at all — keep the order the user gave them. This is
    a no-op when the venue provides no flow hints, which is the correct
    behaviour: with no signal, the user's order stands.
    """
    # [2026-09-23, kiro critic] Fill missing hints in a FORWARD pass, in the user's
    # own order, BEFORE sorting. An un-hinted stop inherits the hint of the stop
    # before it, so it keeps its place.
    #
    # Defaulting a missing flow_index to 0 made it sort ahead of everything: a user
    # who put "Gift Shop" LAST with no hint got it moved to FIRST, because 0 < 1.
    # The docstring's promise -- "with no signal, the user's order stands" -- held
    # only when NO stop carried a hint. This cannot be done inside the sort key:
    # sort calls the key in an unspecified order, so "the stop before it" is only
    # meaningful in a separate pass.
    def _num(v, fallback):
        try:
            return float(v)
        except (TypeError, ValueError):
            return fallback

    filled, floor_c, flow_c = [], 0.0, 0.0
    for idx, poi in enumerate(poi_list):
        d = poi if isinstance(poi, dict) else {}
        floor_c = _num(d.get('floor', floor_c), floor_c)
        flow_c = _num(d.get('flow_index', flow_c), flow_c)
        filled.append(((floor_c, flow_c, idx), poi))

    filled.sort(key=lambda t: t[0])       # idx keeps it stable
    return [poi for _, poi in filled]



# ─────────────────────────────────────────────────────────────────────────────
# Forced order: honour the user's own sequence verbatim
# ─────────────────────────────────────────────────────────────────────────────

# Warnings from the most recent sequence_stops() call. The function returns a plain
# list for backward compatibility, so this is how a caller learns that part of the
# user's instruction could not be honoured.
LAST_WARNINGS = []


def unmatched_forced_labels(poi_list, forced_order):
    """Names the user gave that match no stop — a typo, not an instruction to drop.

    [2026-09-23, kiro critic] `_apply_forced_order` ignores an unmatched name
    silently. It never LOSES a stop — the unnamed one is appended — but the user's
    intent for it is discarded without a word: someone typing "Alter" for "Altar"
    gets that stop moved to the END of the tour, the opposite of what they asked,
    with nothing said. Same family as the failures fixed elsewhere today, where a
    thing that did not work was indistinguishable from a thing that did.
    """
    have = {_normalize_name(p.get('name', '') if isinstance(p, dict) else p)
            for p in (poi_list or [])}
    return [lbl for lbl in (forced_order or [])
            if _normalize_name(lbl) not in have]


def _apply_forced_order(poi_list, forced_order):
    """Reorder poi_list to match `forced_order` exactly.

    `forced_order` is a list of stop names (matched case/space-insensitively).
    Named stops come first, in the user's stated order. Any stop the user did
    NOT name is appended afterwards in its original relative order, so a forced
    order can never drop a stop. Unmatched names in forced_order are ignored
    (they refer to nothing in the list).
    """
    remaining = list(poi_list)
    ordered = []
    for label in forced_order:
        target = _normalize_name(label)
        for k, poi in enumerate(remaining):
            if _normalize_name(_stop_name(poi)) == target:
                ordered.append(remaining.pop(k))
                break
    ordered.extend(remaining)  # never lose an unnamed stop
    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# Seams: hand off to the next stop, and close the last one
# ─────────────────────────────────────────────────────────────────────────────

def _directions_to_next(from_poi, to_poi, tour_category):
    """A deterministic hand-off cue that NAMES the next stop.

    The target is always `to_poi`, which is drawn from the ordered list, so the
    seam can never point outside the list.
    """
    to_name = _stop_name(to_poi)
    if tour_category in ('museum', 'building', 'venue'):
        return f"Continue to {to_name}."
    return f"From here, make your way to {to_name}."


def _closing_line(last_poi, tour_category, venue_name=""):
    """A clean closing for the final stop — it never points at another stop."""
    last_name = _stop_name(last_poi)
    where = f" of {venue_name}" if venue_name else ""
    return (
        f"{last_name} is the final stop{where}. "
        f"This is where the tour ends — thank you for walking it through to the end."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def sequence_stops(
    poi_list,
    tour_category="walking",
    forced_order=None,
    venue_name="",
):
    """Order the stops the user chose, then connect them with seams.

    Args:
        poi_list: list of stop dicts (each with at least a 'name'). Not mutated.
        tour_category: 'walking'/'restaurant'/outdoor -> geographic order;
                       'museum'/'building'/'venue'     -> venue-flow order.
        forced_order: optional list of stop names. When given, the stops are put
                      in exactly this order (verbatim) and NO re-optimisation
                      happens. Stops not named are appended in original order.
        venue_name: optional venue name, woven into the closing line.

    Returns:
        A NEW list of NEW stop dicts in walked order. Each stop gains:
            'position'   1-based order index
            'directions' hand-off naming the next stop (omitted on the last)
            'closing'    closing line (present only on the last stop)

    Guarantees (the LOCAL-522 acceptance criteria):
        1. A jumbled list comes back in a walkable order.
        2. Every stop's Directions names the NEXT stop; the last one closes.
        3. A forced order is honoured verbatim.
        4. No seam points at a stop that is not in the list.
    """
    stops = list(poi_list or [])
    if not stops:
        return []

    # 1 / 3 — ORDER (forced order wins outright; otherwise order for the mode)
    if forced_order:
        _unmatched = unmatched_forced_labels(stops, forced_order)
        LAST_WARNINGS.clear()
        if _unmatched:
            # Do not silently discard what the user asked for. sequence_stops
            # returns a plain list, so the warning goes to the log and to
            # LAST_WARNINGS for any caller that wants to surface it.
            _msg = ("you asked to place " +
                    ", ".join(f'\"{u}\"' for u in _unmatched[:4]) +
                    " but no stop of that name is in the tour — check the spelling; "
                    "those stops kept their original position")
            LAST_WARNINGS.append(_msg)
            logging.warning("[SEQUENCE] %s", _msg)
        ordered = _apply_forced_order(stops, forced_order)
    elif tour_category in ('museum', 'building', 'venue'):
        ordered = _order_venue_flow(stops)
    else:
        ordered = _order_geographic(stops)

    # Work on copies so the caller's dicts are never mutated.
    result = []
    for poi in ordered:
        if isinstance(poi, dict):
            result.append(dict(poi))
        else:
            result.append({'name': str(poi)})

    # 2 / 4 — SEAMS (targets are drawn only from `result`, so never off-list)
    last = len(result) - 1
    for i, stop in enumerate(result):
        stop['position'] = i + 1
        stop.pop('directions', None)
        stop.pop('closing', None)
        if i < last:
            stop['directions'] = _directions_to_next(stop, result[i + 1], tour_category)
        else:
            stop['closing'] = _closing_line(stop, tour_category, venue_name)

    return result


def route_length_km(poi_list):
    """Total straight-line walking distance (km) across a sequence of stops.

    Skips legs where either endpoint lacks a position. Useful for verifying that
    a reordering actually shortened the walk.
    """
    coords = [_extract_coord(p) for p in (poi_list or [])]
    total = 0.0
    for a, b in zip(coords, coords[1:]):
        if a is not None and b is not None:
            total += _haversine_km(a, b)
    return total
