#!/usr/bin/env python3
"""walking_directions_guard.py — LOCAL-650 fix 2.

On a WALKING tour, the Directions on each stop must lead to the NEXT stop — by
its name — and say roughly how far it is.

Michael, 2026-10-09 (tour 557, "Walking tour in Boston … Massachusetts politics
and current affairs", 5 stops):

    Stop 4 (Old State House) Directions: "… head north on Washington Street …
    until you reach the Massachusetts State House …"

That names STOP 1, not the next stop (Stop 5). The route itself was ordered
correctly (nearest-neighbour + 2-opt in generate_tour_text._compute_route_order);
the per-stop Directions PROSE — written by the LLM — named the wrong landmark as
the destination. ``directions_guarantee`` only checks that *a* hand-off is
PRESENT, not that it points at the correct next stop, so a wrong-target line
passes it untouched.

This module is the deterministic, every-path TEXT guard that closes that gap for
WALKING/outdoor tours (museum tours are left to directions_guarantee, which uses
the venue's room flow). It is pure and offline. For each non-last stop it:

  1. reads the stop's own ``Directions:`` line;
  2. decides whether that line leads to the NEXT stop. A line is WRONG when it
     presents a DIFFERENT delivered stop as the destination ("until you reach
     <some other stop>") and does not name the next stop as the destination;
  3. when WRONG, replaces the line with a correct, deterministic hand-off that
     names the next stop; when RIGHT (or merely generic), keeps the prose;
  4. appends an approximate straight-line distance to the next stop, computed
     from the two stops' coordinates (haversine), when both are known and no
     distance is already stated.

The last stop is never given a hand-off. Idempotent: a correct line with a
distance already present is left unchanged.
"""
import re
from math import radians, sin, cos, asin, sqrt
from typing import List, Optional, Tuple

try:
    from stop_pool_store import _STOP_HEADER, _SOURCES_LINE
except Exception:  # pragma: no cover
    _STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
    _SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')

_DIRECTIONS_LINE_RE = re.compile(r'(?im)^(Directions:[ \t]*)([^\n]*?)[ \t]*$')
_COORDS_LINE_RE = re.compile(r'(?im)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')

# Phrases that mark the DESTINATION a Directions line claims you arrive at.
_ARRIVAL_CUE_RE = re.compile(
    r'(?i)(?:until you reach|when you (?:reach|see|arrive)|you(?:\'ll| will) '
    r'(?:reach|see|arrive|find|know you(?:\'ve| have) arrived)|arrive at|'
    r'you have arrived at|you reach|towards?|toward|to the|head (?:to|for)|'
    r'make your way to|continue to|proceed to)\s+')

# Already-present distance phrase (so we don't double-append).
_DISTANCE_RE = re.compile(
    r'(?i)\b(?:about|approximately|roughly|around)?\s*'
    r'\d+(?:\.\d+)?\s*(?:m|meters?|metres?|km|kilometers?|kilometres?|'
    r'miles?|min(?:ute)?s?)\b'
    r"|\ba (?:short|quick|brief) (?:walk|stroll)\b"
    r"|\bminutes?[\u2019']?s?\s+walk\b"
    r"|\bminute[\u2019']?s\s+walk\b")


# ─────────────────────────────────────────────────────────────────────────────
# Geometry (mirrors stop_route_sequencer / generate_tour_text._haversine_km)
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def _approx_distance_phrase(km: Optional[float]) -> str:
    """A natural, approximate distance phrase, or '' when unknown/zero."""
    if km is None or km <= 0:
        return ""
    meters = km * 1000.0
    if meters < 120:
        return "about a minute's walk away"
    if meters < 1000:
        rounded = int(round(meters / 50.0) * 50)
        return f"roughly {rounded} meters away"
    miles = km * 0.621371
    if miles < 1.3:
        return f"roughly {km:.1f} km (about a {max(1, int(round(km / 0.08)))}-minute walk) away"
    return f"roughly {km:.1f} km away"


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def _tour_category(text: str) -> str:
    m = re.search(r'(?im)^Tour-Category:\s*(.+?)\s*$', text or "")
    return re.sub(r'\s+', ' ', m.group(1).strip().lower()) if m else ""


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').strip().lower()).strip(' .,:;"\'')


def _bare_title(raw: str) -> str:
    t = re.sub(r',\s*\d{3,4}\s*$', '', (raw or "").strip())
    t = re.sub(r'\s+by\s+.+$', '', t, flags=re.IGNORECASE)
    return t.strip()


def _blocks(text: str) -> List[dict]:
    """[{num, name, start, end, coord, directions_span}] for each Stop block."""
    src = _SOURCES_LINE.search(text)
    end_body = src.start() if src else len(text)
    headers = [h for h in _STOP_HEADER.finditer(text) if h.start() < end_body]
    out = []
    for i, h in enumerate(headers):
        start = h.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else end_body
        seg = text[start:end]
        cm = _COORDS_LINE_RE.search(seg)
        coord = None
        if cm:
            try:
                lat, lng = float(cm.group(1)), float(cm.group(2))
                if not (lat == 0.0 and lng == 0.0):
                    coord = (lat, lng)
            except ValueError:
                coord = None
        out.append({
            'num': int(h.group(1)),
            'name': _bare_title(h.group(2)),
            'start': start,
            'end': end,
            'coord': coord,
        })
    return out


def _directions_target_is_wrong(dir_text: str, next_name: str,
                                other_names: List[str]) -> bool:
    """True when a Directions line presents a DIFFERENT delivered stop as the
    destination and does not name the next stop as where you arrive.

    Conservative: only flags when the line names another stop at an ARRIVAL cue
    ("until you reach <other>") AND does not also name the next stop. A line that
    merely passes a landmark in transit, or that names the next stop, is kept.
    """
    low = " " + _norm(dir_text) + " "
    nn = _norm(next_name)
    names_next = bool(nn) and nn in low
    if names_next:
        return False
    # Does it claim arrival at some OTHER delivered stop?
    for other in other_names:
        on = _norm(other)
        if not on or on == nn:
            continue
        # The other stop appears right after an arrival cue.
        for m in _ARRIVAL_CUE_RE.finditer(dir_text):
            tail = _norm(dir_text[m.end():m.end() + len(other) + 40])
            if tail.startswith(on) or on in tail[:len(on) + 15]:
                return True
    return False


def analyze(text: str) -> List[dict]:
    """Diagnose each non-last walking stop's Directions. Returns a list of
    ``{num, name, next, has_directions, wrong_target, has_distance}``."""
    if _tour_category(text) in ('museum', 'building', 'venue'):
        return []
    blocks = _blocks(text)
    report = []
    for i in range(len(blocks) - 1):
        seg = text[blocks[i]['start']:blocks[i]['end']]
        nxt = blocks[i + 1]
        dm = _DIRECTIONS_LINE_RE.search(seg)
        others = [b['name'] for j, b in enumerate(blocks) if j != i and j != i + 1]
        dir_text = dm.group(2) if dm else ""
        report.append({
            'num': blocks[i]['num'],
            'name': blocks[i]['name'],
            'next': nxt['name'],
            'has_directions': bool(dm),
            'wrong_target': bool(dm) and _directions_target_is_wrong(
                dir_text, nxt['name'], others),
            'has_distance': bool(dir_text) and bool(_DISTANCE_RE.search(dir_text)),
        })
    return report


def count_wrong_target_directions(text: str) -> int:
    return sum(1 for r in analyze(text) if r['wrong_target'])


# ─────────────────────────────────────────────────────────────────────────────
# Correction
# ─────────────────────────────────────────────────────────────────────────────

def _correct_handoff(next_name: str, dist_phrase: str) -> str:
    base = f"From here, make your way to {next_name}"
    if dist_phrase:
        base += f" — it is {dist_phrase}"
    return base + "."


def ensure_walking_directions_lead_to_next(text: str,
                                          verified_stop_coords: dict = None
                                          ) -> Tuple[str, dict]:
    """Make every non-last WALKING stop's Directions lead to the NEXT stop, with
    an approximate distance. Returns ``(new_text, report)`` where report is
    ``{'corrected': n, 'distance_added': n, 'details': [...]}``.

    • A wrong-target line (names a different delivered stop as the destination) is
      REPLACED with a deterministic hand-off naming the next stop (+ distance).
    • A right/generic line is kept; an approximate distance is appended when both
      coordinates are known and no distance is already stated.
    • A non-last stop with NO Directions line gets one created (naming the next
      stop + distance). The last stop is never touched.

    ``verified_stop_coords``: optional {stop_number: (lat, lng)} from verified
    sources (Wikidata P625, geocoder). When provided, distances are computed ONLY
    between stop pairs where BOTH stops appear in this dict. When omitted (None),
    all coordinates parsed from the text are used (legacy behaviour).

    Deterministic and idempotent. Museum/building/venue tours are a no-op.
    """
    if _tour_category(text) in ('museum', 'building', 'venue'):
        return text, {'corrected': 0, 'distance_added': 0, 'details': []}
    blocks = _blocks(text)
    if len(blocks) < 2:
        return text, {'corrected': 0, 'distance_added': 0, 'details': []}

    corrected = 0
    distance_added = 0
    details = []

    # Rebuild back-to-front so offsets stay valid.
    pieces: List[str] = [text[blocks[-1]['end']:]]
    for i in range(len(blocks) - 1, -1, -1):
        b = blocks[i]
        seg = text[b['start']:b['end']]
        if i < len(blocks) - 1:
            nxt = blocks[i + 1]
            others = [o['name'] for j, o in enumerate(blocks)
                      if j != i and j != i + 1]
            km = None
            if verified_stop_coords is not None:
                # [LOCAL-650B] Only compute distance when BOTH stops have verified
                # coordinates. Unverified (LLM-guessed) coordinates can be wildly
                # wrong, producing false distances (D643).
                vc_a = verified_stop_coords.get(b['num'])
                vc_b = verified_stop_coords.get(nxt['num'])
                if vc_a and vc_b:
                    km = _haversine_km(vc_a, vc_b)
            elif b['coord'] and nxt['coord']:
                km = _haversine_km(b['coord'], nxt['coord'])
            dist_phrase = _approx_distance_phrase(km)

            dm = _DIRECTIONS_LINE_RE.search(seg)
            if dm:
                dir_text = dm.group(2).strip()
                wrong = _directions_target_is_wrong(dir_text, nxt['name'], others)
                if wrong:
                    new_line = dm.group(1) + _correct_handoff(nxt['name'], dist_phrase)
                    seg = seg[:dm.start()] + new_line + seg[dm.end():]
                    corrected += 1
                    if dist_phrase:
                        distance_added += 1
                    details.append({'stop': b['num'], 'action': 'replaced_wrong_target',
                                    'next': nxt['name']})
                else:
                    # Right/generic: ensure next stop is named and append distance.
                    add_bits = []
                    if _norm(nxt['name']) not in _norm(dir_text):
                        add_bits.append(f"Continue to {nxt['name']}")
                    if dist_phrase and not _DISTANCE_RE.search(dir_text):
                        if add_bits:
                            add_bits[-1] += f" — it is {dist_phrase}"
                        else:
                            add_bits.append(f"It is {dist_phrase}")
                    if add_bits:
                        suffix = " " + ". ".join(add_bits).rstrip('.') + "."
                        new_line = dm.group(1) + dir_text.rstrip() + suffix
                        seg = seg[:dm.start()] + new_line + seg[dm.end():]
                        if dist_phrase and not _DISTANCE_RE.search(dir_text):
                            distance_added += 1
                        details.append({'stop': b['num'], 'action': 'augmented',
                                        'next': nxt['name']})
            else:
                # No Directions line at all — create one before the block ends.
                new_line = "Directions: " + _correct_handoff(nxt['name'], dist_phrase)
                seg = seg.rstrip() + "\n\n" + new_line + "\n\n"
                corrected += 1
                if dist_phrase:
                    distance_added += 1
                details.append({'stop': b['num'], 'action': 'created',
                                'next': nxt['name']})
        pieces.append(seg)
    pieces.append(text[:blocks[0]['start']])
    new_text = "".join(reversed(pieces))
    new_text = re.sub(r'\n{3,}', '\n\n', new_text)
    return new_text, {'corrected': corrected, 'distance_added': distance_added,
                      'details': details}


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    print("analysis:")
    for r in analyze(t):
        print("  ", r)
    print("wrong-target before:", count_wrong_target_directions(t))
    fixed, rep = ensure_walking_directions_lead_to_next(t)
    print("report:", rep)
    print("wrong-target after:", count_wrong_target_directions(fixed))
