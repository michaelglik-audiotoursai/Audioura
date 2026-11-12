"""route_content_896.py -- LOCAL-896: content rules for a described ROUTE (origin != destination).

A request such as "a driving tour from <origin> in <locality> to <destination> ..." gives the
listener a route, not a city. The pieces that assumed "one city, walking" misbehave on it:

  * the narrator stamps the ORIGIN's locality on every stop            -> ``strip_origin_locality``
  * "Continue driving 15 minutes ..." with no pin to measure from       -> ``simplify_directions``
  * "this route is the one you chose through the city"                  -> ``closing_sentence``
  * a sentence whose only support was dropped other-place evidence      -> ``sentences_backed_by``
  * a story the evidence itself calls a legend is dropped, not told     -> ``legend_disclosure``
  * pins are looked up in a city-sized scope, not along the route       -> ``route_box``

Everything here is deterministic and name-free (D769): it works from the request's own origin /
destination / locality strings and from the evidence text. State is module-level, set per
generation by ``set_route`` (the same pattern as ``aboutness.set_route_region``).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_STATE: Dict = {"origin": "", "destination": "", "through": [], "localities": [], "box": None}
# [LOCAL-897] geocode of each route place that route_box placed, keyed by the folded place name
_POINTS: Dict[str, Tuple[float, float]] = {}


# ── text helpers ─────────────────────────────────────────────────────────────
def fold(text: str) -> str:
    """Lower-case, diacritics removed, one char out per char in (indices stay aligned)."""
    out = []
    for ch in text or "":
        if ch in "đĐ":
            out.append("d")
            continue
        d = unicodedata.normalize("NFD", ch)
        out.append((d[0] if d else ch).lower())
    return "".join(out)


def _words(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", fold(text))


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


# ── route state ──────────────────────────────────────────────────────────────
def set_route(info: Optional[Dict], box: Optional[Sequence[float]] = None) -> None:
    """Remember the described route for this generation. ``info`` is
    ``user_list_integrity.derive_request_place``'s dict; ``None`` / a plain place clears."""
    if not info or not info.get("is_description"):
        clear_route()
        return
    o, d = (info.get("origin") or "").strip(), (info.get("destination") or "").strip()
    keep_out = " ".join(fold(x) for x in [d, info.get("region") or "", *(info.get("through") or [])])
    locs = []
    for part in re.split(r"[,;/&]|\band\b", info.get("origin_locality") or ""):
        p = " ".join(_words(part))
        if len(p) >= 4 and p not in locs and not re.search(r"\b" + re.escape(p) + r"\b", keep_out):
            locs.append(p)
    _STATE.update({"origin": o, "destination": d, "through": list(info.get("through") or []),
                   "localities": locs, "box": list(box) if box else None})


def clear_route() -> None:
    _STATE.update({"origin": "", "destination": "", "through": [], "localities": [], "box": None})


def active() -> bool:
    o, d = _STATE["origin"], _STATE["destination"]
    return bool(o and d and fold(o) != fold(d))


def endpoints() -> Tuple[str, str]:
    return _STATE["origin"], _STATE["destination"]


def box() -> Optional[List[float]]:
    return _STATE["box"]


def set_box(b: Optional[Sequence[float]]) -> None:
    _STATE["box"] = list(b) if b else None


# ── route region box (pins) ──────────────────────────────────────────────────
_KIND_TAIL = re.compile(r"(?i)\s+(?:mountain|mount|mt\.?|hill|peak|resort|hotel|pagoda|temple|beach|lake|river|"
                        r"national park|park|bay|island|village|town|city|market|station)$")


def _queries(name: str, region: str) -> List[str]:
    """Geocoder queries for one route place. Always inside the region when there is one: a bare
    name ("<name> Mountain") resolves to a same-named place on another continent."""
    base = [name.strip()]
    short = _KIND_TAIL.sub("", name.strip())
    if short and short != name.strip():
        base.append(short)
    if region:
        return [f"{x}, {region}" for x in base]
    return base


def route_box(places: Iterable[str], region: str = "", geocode_fn: Optional[Callable] = None,
              fallbacks: Iterable[str] = (), margin_km: float = 25.0
              ) -> Tuple[Optional[List[float]], Optional[Tuple[float, float]], int]:
    """Box covering the route: every place (origin, through, destination) geocoded inside
    ``region``. Returns (bbox [south, north, west, east] -- Nominatim order, centre (lat, lng),
    number of places placed). (None, None, n) when fewer than two places could be placed -- the
    caller then keeps its own scope. ``fallbacks`` are tried for a place that does not geocode
    (the origin's locality for a named venue). A point more than 150 km from the others is a
    geocoder miss and is left out. The margin is generous (25 km): the box is a scope for
    NAME-matched lookups, not a claim about where a stop is."""
    if geocode_fn is None:
        from geocode_stops import geocode as geocode_fn          # free Nominatim, no paid call
    import math
    import user_list_integrity as uli
    pts, fb, named = [], list(fallbacks), []
    for i, name in enumerate(p for p in places if p and p.strip()):
        hit = None
        for q in [name] + (fb if i == 0 else []):
            for query in _queries(q, region):
                try:
                    hit = geocode_fn(query)
                except Exception:
                    hit = None
                if hit:
                    break
            if hit:
                break
        if hit:
            pts.append((float(hit[0]), float(hit[1])))
            named.append((name, pts[-1]))

    def _km(a, b):
        dl = math.radians(b[0] - a[0])
        dg = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
        return 6371.0 * math.hypot(dl, dg)
    if len(pts) >= 3:
        keep = [p for p in pts if sum(1 for q in pts if q is not p and _km(p, q) <= 150.0) >= (len(pts) - 1) // 2]
        pts = keep or pts
    if len(pts) < 2:
        return None, None, len(pts)
    for nm, pt in named:                      # [LOCAL-897] remember each placed route place's own geocode
        if pt in pts:
            _POINTS[fold(nm).strip()] = pt
    s, w, n, e = uli.bbox_covering(pts, margin_km)
    centre = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return [s, n, w, e], centre, len(pts)


_BOX_CACHE: Dict = {}


def box_for_info(info: Dict, geocode_fn: Optional[Callable] = None
                 ) -> Tuple[Optional[List[float]], Optional[Tuple[float, float]]]:
    """``route_box`` for a derived request (origin + through + destination inside its region);
    successes are cached for the process."""
    if not info or not info.get("is_description"):
        return None, None
    places = [info.get("origin"), *(info.get("through") or []), info.get("destination")]
    places = [p for p in places if p]
    if len({fold(p) for p in places}) < 2:
        return None, None
    key = (tuple(places), info.get("region") or "")
    if key in _BOX_CACHE:
        return _BOX_CACHE[key]
    bb, ctr, _n = route_box(places, info.get("region") or "", geocode_fn,
                            fallbacks=[info.get("origin_locality") or ""])
    if bb:
        _BOX_CACHE[key] = (bb, ctr)
    return bb, ctr


def in_box(bbox: Optional[Sequence[float]], lat: float, lng: float) -> bool:
    """``bbox`` = [south, north, west, east]."""
    if not bbox or len(bbox) < 4:
        return False
    return bbox[0] <= lat <= bbox[1] and bbox[2] <= lng <= bbox[3]


# ── 1. sentences whose only support was dropped other-place evidence ─────────
_NOISE = frozenset(
    "the a an and or of in on at to for with from by is are was were be been it its this that these those "
    "you your we our they their there here as can will may also not but if so than then when which who "
    "have has had more most very one two three up down out into over under about around just still".split())


def _content_tokens(text: str) -> set:
    toks = set()
    for w in _words(text):
        if w.isdigit() or (len(w) >= 4 and w not in _NOISE):
            toks.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return toks


def sentences_backed_by(sentences: Sequence[str], dropped_evidence: str, kept_evidence: str,
                        title: str = "") -> List[str]:
    """Sentences supported by ``dropped_evidence`` (another place's text) and not by the evidence
    that was kept: >= 2 distinctive tokens (a number counts on its own) shared with the dropped text,
    after the stop's own title words, the route's places and the kept evidence are set aside. Word
    matching, not proper-name matching: a time of day or a generic fact is caught as well."""
    skip = _content_tokens(title) | _content_tokens(kept_evidence)
    for p in (_STATE["origin"], _STATE["destination"], *_STATE["through"], *_STATE["localities"]):
        skip |= _content_tokens(p)
    ev = _content_tokens(dropped_evidence) - skip
    nums = {t for t in ev if t.isdigit()}
    out = []
    for s in sentences:
        shared = (_content_tokens(s) - skip) & ev
        if len(shared) >= 2 or (shared & nums):
            out.append(s)
    return out


# ── 2. the origin's locality is not every stop's locality ────────────────────
_KEYED = re.compile(r"(?i)^\s*(coordinates|type/specialty|specific examples|directions|orientation|address|hours)\s*:")
_STOP_HDR = re.compile(r"(?m)^(Stop\s+(\d+):\s*(.+?))\s*$")


def _locality_alt() -> str:
    return "|".join(re.escape(l).replace(r"\ ", r"\s+") for l in sorted(_STATE["localities"], key=len, reverse=True))


def strip_origin_locality_sentence(sentence: str) -> Optional[str]:
    """Remove a locative phrase naming the origin's locality ("... in <locality>, <locality>",
    "this quiet corner of <locality>"). None when the sentence cannot be repaired (the locality is its
    subject / opening frame) and must go."""
    alt = _locality_alt()
    if not alt:
        return sentence
    f = fold(sentence)
    # the route's own place names (the origin "<brand> <locality> Resort") are not the locality stamp
    for nm in (_STATE["origin"], _STATE["destination"], *_STATE["through"]):
        fn = fold(nm).strip()
        if fn:
            f = re.sub(r"\b" + re.escape(fn) + r"\b", lambda m: "_" * len(m.group(0)), f)
    if not re.search(r"\b(?:" + alt + r")\b", f):
        return sentence
    if re.match(r"\W*(?:in|at|near|around|within)\s+(?:the\s+)?(?:" + alt + r")\b", f):
        return None
    pat = re.compile(r"[ \t]*,?[ \t]*\b(?:in|of|near|at|around|within|from)\s+(?:the\s+)?"
                     r"(?:" + alt + r")(?:\s*(?:,|and|&)\s*(?:" + alt + r"))*")
    new, pos = [], 0
    for m in pat.finditer(f):
        new.append(sentence[pos:m.start()])
        pos = m.end()
    new.append(sentence[pos:])
    out = "".join(new)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*([.!?])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    g = fold(out)
    for nm in (_STATE["origin"], _STATE["destination"], *_STATE["through"]):
        fn = fold(nm).strip()
        if fn:
            g = re.sub(r"\b" + re.escape(fn) + r"\b", lambda m: "_" * len(m.group(0)), g)
    # still named: fine only as a destination of travel ("the drive back to <locality>")
    for m in re.finditer(r"\b(?:" + alt + r")\b", g):
        if not re.search(r"\b(?:to|towards?|reach(?:ing)?)\s+(?:the\s+)?$", g[:m.start()]):
            return None
    return out


def _stop_blocks(text: str) -> List[Tuple[int, int, int, str]]:
    """[(start, end, number, title)] of every 'Stop N:' block."""
    hdrs = list(_STOP_HDR.finditer(text))
    res = []
    for i, m in enumerate(hdrs):
        end = hdrs[i + 1].start() if i + 1 < len(hdrs) else len(text)
        res.append((m.start(), end, int(m.group(2)), m.group(3).strip()))
    return res


def _rewrite_prose(block: str, fn: Callable[[List[str]], List[str]]) -> str:
    lines = block.split("\n")
    for i, ln in enumerate(lines):
        if i == 0 or not ln.strip() or _KEYED.match(ln):
            continue
        sents = split_sentences(ln)
        new = fn(sents)
        if new != sents:
            lines[i] = " ".join(new)
    return "\n".join(lines)


def strip_origin_locality(tour_text: str, log: Optional[Callable] = None) -> str:
    """With a route, a stop's locality comes from its own evidence or pin, never from the origin:
    every stop after the first whose title does not name the origin's locality loses the locative
    phrase; a sentence that cannot be repaired is dropped (a stop is never emptied)."""
    if not active() or not _STATE["localities"] or not tour_text:
        return tour_text
    alt = _locality_alt()
    pieces, pos = [], 0
    for k, (s, e, num, title) in enumerate(_stop_blocks(tour_text)):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        if k == 0 or re.search(r"\b(?:" + alt + r")\b", fold(title)):
            pieces.append(block)
            continue

        def fix(sents: List[str], _t=title, _n=num) -> List[str]:
            out = []
            for x in sents:
                y = strip_origin_locality_sentence(x)
                if y is None:
                    if log:
                        log(f"  [LOCAL-896] Stop {_n} '{_t[:40]}': dropped (stamps the origin's locality): \"{x[:90]}\"")
                    continue
                if y != x and log:
                    log(f"  [LOCAL-896] Stop {_n} '{_t[:40]}': origin locality removed: \"{x[:70]}\"")
                out.append(y)
            return out

        pieces.append(_rewrite_prose(block, fix))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── 3. directions on a route ─────────────────────────────────────────────────
_COORD = re.compile(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
_MINUTES = re.compile(r"(?i)\b\d+\s*(?:-\s*\d+\s*)?(?:minutes?|mins?)\b")


def _km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    import math
    dl = math.radians(b[0] - a[0])
    dg = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return 6371.0 * math.hypot(dl, dg)


def _pin(block: str) -> Optional[Tuple[float, float]]:
    m = _COORD.search(block)
    return (float(m.group(1)), float(m.group(2))) if m else None


def simplify_directions(tour_text: str, log: Optional[Callable] = None) -> str:
    """No minutes, compass points or turn-by-turn without a pin on BOTH ends: the Directions line
    becomes "Continue to <next stop>." (the last stop is left alone)."""
    if not active() or not tour_text:
        return tour_text
    blocks = _stop_blocks(tour_text)
    out, pos = [], 0
    for k, (s, e, num, title) in enumerate(blocks):
        out.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        if k + 1 < len(blocks):
            nxt = blocks[k + 1]
            a, b = _pin(block), _pin(tour_text[nxt[0]:nxt[1]])
            pinned = bool(a and b)
            if pinned:
                # pinned on both ends: a model-written "N minutes" that the pins contradict (a base
                # station 1 km from the previous stop is not "15 minutes" away) is replaced by the
                # measured straight-line distance
                dm = re.search(r"(?mi)^Directions:([^\n]*)$", block)
                if dm and _MINUTES.search(dm.group(1)):
                    d = _km(a, b)
                    tail = f", about {d:.0f} km away" if d >= 1.5 else ""
                    new = block[:dm.start()] + f"Directions: Continue to {nxt[3]}{tail}." + block[dm.end():]
                    if log:
                        log(f"  [LOCAL-896] Stop {num}: model minutes replaced by the pinned distance ({d:.1f} km)")
                    block = new
            if not pinned:
                new_title = nxt[3]
                new = re.sub(r"(?mi)^Directions:[^\n]*$", lambda _m: f"Directions: Continue to {new_title}.", block)
                if new != block and log:
                    log(f"  [LOCAL-896] Stop {num}: no pin on both ends -> directions reduced to 'Continue to <next>'")
                block = new
        out.append(block)
    out.append(tour_text[pos:])
    return "".join(out)


# ── 4. the closing of a route ────────────────────────────────────────────────
def closing_sentence() -> Optional[str]:
    if not active():
        return None
    o, d = endpoints()
    return (f"From {o} to {d}, this route is the one you chose — your own path, "
            f"in your own order.")


# ── 5. a legend the evidence itself calls a legend ───────────────────────────
_LEGEND_OBJ = re.compile(r"(?i)\blegends?\s+(?:of|about|that|says?|has\s+it\s+that)\s+([^.;!?]{6,160})")
_CAPWORD = re.compile(r"\b[A-ZÀ-Ỹ][^\W\d_]+")


_STEEPED = re.compile(r"(?i)\bis\s+steeped\s+in\s+a\s+legend\s+of\b")


def is_legend_disclosure(sentence: str) -> bool:
    s = sentence or ""
    if re.match(r"(?i)\s*local\s+legend\b", s) and "legend" in s.lower():
        return True
    return bool(_STEEPED.search(s))                 # [LOCAL-897] the evidence's own wording


def _legend_object(title: str, evidence: str) -> Optional[str]:
    tw = [w for w in _words(title) if len(w) >= 4 and w not in _NOISE]
    best = None
    for s in split_sentences(re.sub(r"\s+", " ", evidence or "")):
        if "legend" not in s.lower() or re.match(r"(?i)local legend", s):
            continue
        if tw and not any(w in _words(s) for w in tw):
            continue
        m = _LEGEND_OBJ.search(s)
        if not m:
            continue
        obj = m.group(1).strip(" ,")
        if re.search(r"(?i)\b(?:that|which|who|is|are|was|were)\b", obj) or len(obj.split()) > 12:
            continue
        caps = len(_CAPWORD.findall(obj))
        if caps and (best is None or caps > best[0]):
            best = (caps, obj)
    return best[1] if best else None


def legend_disclosure(title: str, evidence: str) -> Optional[str]:
    """ONE sentence framed as legend, in the evidence's own wording (\"<stop> is steeped in a legend
    of <object>\"), from an evidence sentence that names the stop and calls its story a legend.
    None when the evidence has no such sentence or no usable object. Never states the story as
    fact (D760). [LOCAL-897] The 896 form (\"a story told by locals rather than documented
    history\") claimed more than the evidence says -- the audit flagged it as unsupported."""
    tw = [w for w in _words(title) if len(w) >= 4 and w not in _NOISE]
    for sent in split_sentences(re.sub(r"\s+", " ", evidence or "")):     # the evidence's own sentence, verbatim
        if _STEEPED.search(sent) and len(sent.split()) <= 30 and (not tw or any(w in _words(sent) for w in tw)):
            return sent.strip()
    obj = _legend_object(title, evidence)
    return f"{title.strip()} is steeped in a legend of {obj}." if obj else None


def legend_fact(title: str, evidence: str) -> Optional[str]:
    """[LOCAL-897] A fact the evidence states PLAINLY about the same people as the legend (e.g. a
    royal recognition) is kept as fact: the evidence sentence that names the stop and shares a
    capitalised name with the legend object but does not itself say 'legend'."""
    obj = _legend_object(title, evidence)
    if not obj:
        return None
    names = {w.lower() for w in _CAPWORD.findall(obj)}
    tw = [w for w in _words(title) if len(w) >= 4 and w not in _NOISE]
    for s in split_sentences(re.sub(r"\s+", " ", evidence or "")):
        if "legend" in s.lower() or len(s) > 260:
            continue
        if tw and not any(w in _words(s) for w in tw):
            continue
        if len(names & {w.lower() for w in _CAPWORD.findall(s)}) >= 2:
            return s.strip()
    return None


def legend_sentences(title: str, evidence: str) -> List[str]:
    ld = legend_disclosure(title, evidence)
    if not ld:
        return []
    fact = legend_fact(title, evidence)
    return ([fact] if fact else []) + [ld]


# ── 6. [LOCAL-897] route places as a stop's own reference ────────────────────
def _title_tokens(text: str) -> set:
    return {w for w in _words(text) if w not in _NOISE}


def place_point(name: str) -> Optional[Tuple[float, float]]:
    return _POINTS.get(fold(name).strip())


def _names(title: str, place: str) -> bool:
    core = _KIND_TAIL.sub("", place.strip()) or place
    need = _title_tokens(core)
    return bool(need) and need <= _title_tokens(title)


def stop_references(titles: Sequence[str]) -> Dict[int, Dict]:
    """{stop index: {"coord": (lat, lng), "place": name, "why": ...}} -- a stop whose title names
    the route's destination (or another route place) uses that place's own geocode as its
    reference; the stops from the first one that names the DESTINATION onward are on the
    destination (a cable car, a statue and a summit view on the mountain you have reached).
    Generic: only the request's own place strings are used (D769)."""
    if not active():
        return {}
    o, d = endpoints()
    out: Dict[int, Dict] = {}
    arrived = None
    dpt = place_point(d)
    for i, t in enumerate(titles):
        for pl in [*_STATE["through"], d]:
            pt = place_point(pl)
            if pt and _names(t, pl):
                out[i] = {"coord": pt, "place": pl, "why": "title names the route place"}
                if pl == d:
                    arrived = i if arrived is None else arrived
                break
    if arrived is not None and dpt:
        for i in range(arrived + 1, len(titles)):
            out.setdefault(i, {"coord": dpt, "place": d, "why": "stop follows the arrival at the destination"})
    return out


# ── 7. [LOCAL-897] minutes / distances / compass inside a stop BODY ──────────
_TRAVEL = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?\s*)?(?:minutes?|mins?|km|kilomet(?:er|re)s?|miles?)\s+"
    r"(?:away|drive|ride|from\b|north|south|east|west)"
    r"|\b(?:takes?|about|roughly|approximately|within)\s+(?:an?\s+)?\d+\s*(?:-\s*\d+\s*)?(?:minutes?|mins?)\b"
    r"|\b(?:to|toward|towards|on|from|in)\s+the\s+(?:north|south|east|west)(?:ern)?(?:east|west)?\b"
    r"(?!\s+(?:asia|china|coast|side))"
    r"|\b(?:north|south|east|west)(?:ward)?\s+(?:of|from)\b"
    r"|\bdrive\s+(?:north|south|east|west)\b")


def _has_travel(sentence: str) -> bool:
    return bool(_TRAVEL.search(sentence))


def repair_travel_sentence(sentence: str) -> Optional[str]:
    """Drop the comma-bounded clause that carries a minutes / km / compass claim; None when the claim
    is the sentence's own frame (it cannot be repaired and the sentence goes)."""
    if not _has_travel(sentence):
        return sentence
    parts = re.split(r"(?<=,)\s+|\s+(?=—)|(?<=—)\s+", sentence)
    if len(parts) < 2:
        return None
    keep = [p for p in parts if not _has_travel(p)]
    if not keep or keep[0] != parts[0]:
        return None                       # the opening clause is the claim
    out = " ".join(keep).strip().rstrip(",—").rstrip()
    if not re.search(r"[.!?]$", out):
        out += "."
    return out if len(_words(out)) >= 5 and not _has_travel(out) else None


def strip_body_travel(tour_text: str, log: Optional[Callable] = None) -> str:
    """No \"N minutes/km away\" or compass direction in a stop BODY unless both ends are pinned (the
    stop, and the route place the sentence names). Directions lines are handled by
    ``simplify_directions``."""
    if not active() or not tour_text:
        return tour_text
    places = [p for p in (_STATE["destination"], *_STATE["through"]) if place_point(p)]
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        pinned = _pin(block) is not None

        def fix(sents: List[str], _n=num, _t=title, _pinned=pinned) -> List[str]:
            out = []
            for x in sents:
                if _has_travel(x) and not (_pinned and any(_names(x, p) for p in places)):
                    y = repair_travel_sentence(x)
                    if log:
                        log(f"  [LOCAL-897] Stop {_n} '{_t[:40]}': body distance/time/compass without both ends "
                            f"pinned -> {'clause dropped' if y else 'sentence dropped'}: \"{x[:90]}\"")
                    if y is None:
                        continue
                    x = y
                out.append(x)
            if not out:        # never an empty stop: the D760 honest body
                import strict_grounding_gate as _sgg
                out = _sgg.sensory_body(_t, [_sgg.NO_HISTORY_DISCLOSURE], _sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                        register="driving")
            return out
        pieces.append(_rewrite_prose(block, fix))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── 8. [LOCAL-897] a user-list sentence the evidence does not support ────────
_CLOSING_LINE = re.compile(r"(?i)^(?:from .{3,160}? this route is the one you chose|that['\u2019]s \d+ stops?|"
                           r"if you would like to eat)")


def _supported(sentence: str, support: set) -> bool:
    return bool(_content_tokens(sentence) & support)


def cap_unsupported(tour_text: str, evidence_by_title: Dict[str, str], log: Optional[Callable] = None) -> str:
    """On a route (user-list) tour: a sentence with NO support in the stop's own evidence AND no
    concrete noun from the evidence or the title is dropped (\"This tension between preservation and
    progress is etched into the land\" has neither). Evidence about another place has been set aside
    first. A stop whose evidence is thin keeps only the honest non-factual body + the D760
    disclosure -- not mood-only text. Pure, free, name-free."""
    if not active() or not tour_text:
        return tour_text
    import strict_grounding_gate as sgg
    ev_map = {fold(str(k)): v for k, v in (evidence_by_title or {}).items()}
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        ev = ev_map.get(fold(title), "") or ""
        try:
            import aboutness as _ab
            ev = _ab.strip_other_place_evidence(ev)[0]
        except Exception:
            pass
        thin = sgg._evidence_is_thin(ev)
        support = _content_tokens(ev) | _content_tokens(title)
        tpl = [fold(t.format(t=title))[:30] for t in sgg._SENSORY_TEMPLATES_DRIVING + sgg._SENSORY_TEMPLATES]
        disc = fold(sgg.NO_HISTORY_DISCLOSURE)[:30]

        def fix(sents: List[str], _n=num, _t=title, _thin=thin, _sup=support) -> List[str]:
            if sents and _CLOSING_LINE.match(sents[0]):
                return sents
            out = []
            for x in sents:
                fx = fold(x)
                if (fx[:30] in tpl or disc in fx or is_legend_disclosure(x)
                        or _CLOSING_LINE.match(x) or _supported(x, _sup)):
                    out.append(x)
                elif log:
                    log(f"  [LOCAL-897] Stop {_n} '{_t[:40]}': dropped (no support in the evidence, no concrete "
                        f"noun from evidence or title): \"{x[:100]}\"")
            return out

        lines = block.split("\n")
        body_idx = [i for i, ln in enumerate(lines) if i > 0 and ln.strip() and not _KEYED.match(ln)
                    and not _CLOSING_LINE.match(ln.strip())]
        for i in body_idx:
            lines[i] = " ".join(fix(split_sentences(lines[i])))
        body_idx = [i for i in body_idx if lines[i].strip()]
        if thin and body_idx and not any("legend" in lines[i].lower() for i in body_idx):
            # no evidence for this stop: the D760 honest body, not mood-only text
            honest = sgg.sensory_body(title, [sgg.NO_HISTORY_DISCLOSURE], sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                      register="driving")
            if fold(" ".join(lines[i] for i in body_idx)) != fold(" ".join(honest)) and log:
                log(f"  [LOCAL-897] Stop {num} '{title[:40]}': no evidence for this destination -> honest "
                    f"non-factual body + disclosure (D760), not mood-only text")
            lines[body_idx[0]] = " ".join(honest)
            for i in body_idx[1:]:
                lines[i] = None
        new_block = "\n".join(ln for ln in lines if ln is not None)
        pieces.append(re.sub(r"\n{3,}", "\n\n", new_block))
    pieces.append(tour_text[pos:])
    return "".join(pieces)
