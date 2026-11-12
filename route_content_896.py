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
_NUMW = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|"
         r"fifty|sixty|ninety|a\s+few|a\s+couple\s+of|couple\s+of|several|many|few|an?|half\s+an?)")
# [LOCAL-898] digits, number words, and the hyphenated adjective forms ("a 40-minute trip", "two-hour drive")
_MINUTES = re.compile(r"(?i)\b(?:\d+(?:\.\d+)?\s*(?:-\s*\d+\s*)?|" + _NUMW + r")[\s-]*(?:minutes?|mins?|hours?|hrs?)\b")


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


def _collapsed(name: str, km: float = 5.0) -> bool:
    """[LOCAL-897 live] A route place whose geocode sits on top of ANOTHER route place's geocode is a
    geocoder fallback (the destination resolved to the through-town's centre), not the place."""
    pt = place_point(name)
    if not pt:
        return False
    for other, opt in _POINTS.items():
        if other != fold(name).strip() and _km(pt, opt) <= km:
            return True
    return False


def stop_references(titles: Sequence[str], user_pins: Optional[Dict[int, Tuple[float, float]]] = None
                    ) -> Dict[int, Dict]:
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
    user_pins = user_pins or {}
    for i, t in enumerate(titles):                     # where the listener arrives at the destination
        if _names(t, d):
            arrived = i
            break
    dpt = place_point(d)
    if dpt and _collapsed(d):
        # the destination's geocode is another route place's: use the listener's own pin of a stop
        # at / after the arrival instead (a pin the user gave is authoritative), else no reference
        later = [user_pins[k] for k in sorted(user_pins) if arrived is not None and k >= arrived]
        dpt = tuple(later[0]) if later else None
    arrived = None
    for i, t in enumerate(titles):
        for pl in [*_STATE["through"], d]:
            pt = dpt if pl == d else (None if _collapsed(pl) else place_point(pl))
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
    r"|\b\d+(?:\.\d+)?\s*-?\s*(?:minute|min|hour|hr)s?\b"                     # [LOCAL-898] 40-minute, 2 hours
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|a\s+few|several|a\s+couple\s+of)[\s-]+(?:minute|hour)s?\b"
    r"|\b(?:to|toward|towards|on|from|in)\s+the\s+(?:north|south|east|west)(?:ern)?(?:east|west)?\b"
    r"(?!\s+(?:asia|china|coast|side))"
    r"|\b(?:north|south|east|west)(?:ward)?\s+(?:of|from)\b"
    r"|\bdrive\s+(?:north|south|east|west)\b")


def _has_travel(sentence: str) -> bool:
    return bool(_TRAVEL.search(sentence) or _MINUTES.search(sentence))   # [LOCAL-898] every time form


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


def _names_unpinned(sentence: str) -> bool:
    """The sentence names the origin's locality or the origin (not a pinned route place)."""
    f = fold(sentence)
    for l in _STATE["localities"]:
        if re.search(r"\b" + re.escape(l) + r"\b", f):
            return True
    o = _KIND_TAIL.sub("", _STATE["origin"] or "").strip()
    return bool(o) and not place_point(_STATE["origin"]) and fold(o) in f


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
                _other = [p for p in places if _names(x, p) and not _names(_t, p)]
                # a TIME claim ("N minutes") is never measured by two pins (896 rule for Directions): it always goes
                _time = bool(_MINUTES.search(x))
                if _has_travel(x) and (_time or not (_pinned and _other and not _names_unpinned(x))):
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


# [LOCAL-900] a place-type noun that every stop of that kind shares is not "a concrete noun from the evidence"
_GENERIC_NOUN = set("""city town village river lake sea coast beach mountain hill land place area spot site stop
    heart soul pulse rhythm life story history past present time moment world people visitor visitor
    scenery view landscape journey road street meets meet steady where this that""".split())


def _supported(sentence: str, support: set) -> bool:
    shared = _content_tokens(sentence) & support
    if not shared:
        return False
    # [LOCAL-900] only generic place-type words in common, no number -> mood filler ("the pulse of the city
    # meets the steady rhythm of the river")
    return bool({t for t in shared if t.isdigit() or t not in _GENERIC_NOUN})


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
        import place_names_900 as _pn900
        _alltpl = (sgg._SENSORY_TEMPLATES_DRIVING + sgg._SENSORY_TEMPLATES
                   + tuple(x for v in _pn900.SENSORY_BY_KIND.values() for x in v))
        tpl = [fold(t.format(t=nm))[:30] for t in _alltpl for nm in (title, _pn900.short_place_name(title))]
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
        # the route closing (and anything after it) rides on the last stop: split it off, never touched
        tail: List[str] = []
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or _KEYED.match(ln):
                continue
            sents = split_sentences(ln)
            ci = next((k for k, x in enumerate(sents) if _CLOSING_LINE.match(x)), None)
            if ci is not None:
                lines[i] = " ".join(sents[:ci])
                tail = [" ".join(sents[ci:])] + [x for x in lines[i + 1:] if x.strip()]
                lines = lines[:i + 1]
                break
        body_idx = [i for i, ln in enumerate(lines) if i > 0 and ln.strip() and not _KEYED.match(ln)]
        for i in body_idx:
            lines[i] = " ".join(fix(split_sentences(lines[i])))
        body_idx = [i for i in body_idx if lines[i].strip()]
        if thin and not any("legend" in lines[i].lower() for i in body_idx):
            # no evidence for this stop (or an emptied body): the D760 honest body, not mood-only text
            honest = sgg.sensory_body(title, [sgg.NO_HISTORY_DISCLOSURE], sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                      register="driving")
            if fold(" ".join(lines[i] for i in body_idx)) != fold(" ".join(honest)) and log:
                log(f"  [LOCAL-897] Stop {num} '{title[:40]}': no evidence for this destination -> honest "
                    f"non-factual body + disclosure (D760), not mood-only text")
            if body_idx:
                lines[body_idx[0]] = " ".join(honest)
                for i in body_idx[1:]:
                    lines[i] = None
            else:
                # before the Directions line when there is one, else at the end of the block
                di = next((i for i, ln in enumerate(lines) if ln and re.match(r"(?i)^directions\s*:", ln)), None)
                if di is None:
                    while lines and lines[-1] is not None and not lines[-1].strip():
                        lines.pop()
                    lines += ["", " ".join(honest), ""]
                else:
                    lines[di:di] = [" ".join(honest), ""]
        if tail:
            while lines and lines[-1] is not None and not lines[-1].strip():
                lines.pop()
            lines += [""] + [x for t_ in tail for x in (t_, "")]
        new_block = "\n".join(ln for ln in lines if ln is not None)
        pieces.append(re.sub(r"\n{3,}", "\n\n", new_block))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


def fill_empty_bodies(tour_text: str, log: Optional[Callable] = None) -> str:
    """[LOCAL-897 live] D760 on the delivered text: a route stop whose body ended up empty (the last stop
    lost its honest body when the closing was rebuilt) gets the honest non-factual body + disclosure."""
    if not active() or not tour_text:
        return tour_text
    import strict_grounding_gate as sgg
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        lines = block.split("\n")
        prose = [ln for i, ln in enumerate(lines) if i > 0 and ln.strip() and not _KEYED.match(ln)
                 and not _CLOSING_LINE.match(ln.strip())]
        if not prose:
            honest = " ".join(sgg.sensory_body(title, [sgg.NO_HISTORY_DISCLOSURE],
                                               sgg.MIN_NO_EVIDENCE_SENTENCES - 1, register="driving"))
            at = next((i for i, ln in enumerate(lines) if i > 0 and (re.match(r"(?i)^directions\s*:", ln)
                                                                  or _CLOSING_LINE.match(ln.strip()))), None)
            if at is None:
                while len(lines) > 1 and not lines[-1].strip():
                    lines.pop()
                lines += ["", honest, "", ""]
            else:
                lines[at:at] = [honest, ""]
            if log:
                log(f"  [LOCAL-897] Stop {num} '{title[:40]}': empty body on delivery -> honest body + D760 disclosure")
            block = "\n".join(lines)
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ══ [LOCAL-898] leftovers: Directions are only "Continue to / Walk on to", creators agree, headers differ ══
_ROAD_WORD = (r"(?:street|st\.|road|rd\.?|highway|hwy|avenue|ave\.?|boulevard|blvd|lane|expressway|"
              r"freeway|bypass|alley|bridge|junction|roundabout|intersection)")
_NOT_SCENERY = re.compile(
    r"(?i)\b(?:turn|turns|take|exit|merge|follow|head|heads|drive|driving|walk|continue|retrace|return|back|"
    r"descen\w*|ascen\w*|leav\w*|depart\w*|climb\w*|cable\s*car|enjoy|arriv\w*|reach\w*|left|right|onto|"
    r"north\w*|south\w*|east\w*|west\w*|kilomet\w*|km|meters?|metres?|miles?|minutes?|hours?|"
    r"mins?|away|down|winds?|twists?)\b|\b" + _ROAD_WORD + r"\b|\d|\b(?:NH|QL|AH)\s*\d|\bnational\s+route\b|\broute\s+\w*\d")
_SCENERY_CUE = re.compile(
    r"(?i)\b(?:notice|see|spot|pass|passes|admire|views?|vistas?|fields?|plantations?|greenery|forest|coast|"
    r"sea|river|hills?|lining|scenery|landscape|farms?|rice|trees|lush|colou?rful|orchards?|villages?|"
    r"fishing|boats?|dunes?|paddies|gardens?)\b")
_DIR_LINE = re.compile(r"(?mi)^Directions:[ \t]*(.*)$")


# [LOCAL-900] evaluative filler and exclamations are never part of a Directions line
_EVALUATIVE = re.compile(
    r"(?i)\b(?:lovely|beautiful|wonderful|amazing|great|fantastic|stunning|gorgeous|charming|delightful|incredible|"
    r"awesome|perfect|worth|explor\w*|enjoy\w*|nice|pleasant|must[- ]see|don'?t miss|spot to|place to)\b")


def _scenery_clause(directions_text: str) -> Optional[str]:
    """ONE short scenery sentence from a model Directions line: no turn, road name, number, compass
    point, distance, time, or going back / up / down; [LOCAL-900] no exclamation and no evaluative filler
    ("lovely", "worth exploring", "great spot"). None when no sentence qualifies."""
    for sent in split_sentences(directions_text):
        if (len(sent.split()) > 22 or "!" in sent or _EVALUATIVE.search(sent)
                or _NOT_SCENERY.search(sent) or not _SCENERY_CUE.search(sent)):
            continue
        return sent
    return None


def normalize_directions(tour_text: str, log: Optional[Callable] = None, walk_km: float = 1.0,
                         force: bool = False, max_km: Optional[float] = None) -> str:
    """[LOCAL-898] On a route a Directions line holds only: ``Continue to <next>.`` (``Walk on to
    <next>.`` when the next stop is under ``walk_km`` away or shares the pin), ``It is roughly D km
    away.`` when both ends are pinned and the stops are >= walk_km apart, and at most ONE scenery
    clause. No turns, road names, compass points, model minutes, or "retrace / descend". The last
    stop is left alone.

    [LOCAL-900B] ``force`` runs the same reduction on a tour that is not a described route (the single-place
    path); ``max_km`` is a distance no real leg of that tour exceeds: a longer one is a pin bug, logged loudly
    and left out of the line ("Continue to X.")."""
    if (not active() and not force) or not tour_text:
        return tour_text
    blocks = _stop_blocks(tour_text)
    out, pos = [], 0
    for k, (s, e, num, title) in enumerate(blocks):
        out.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        dm = _DIR_LINE.search(block) if k + 1 < len(blocks) else None
        if dm:
            nxt = blocks[k + 1]
            a, b = _pin(block), _pin(tour_text[nxt[0]:nxt[1]])
            d = _km(a, b) if a and b else None
            import place_names_900 as _pn900
            _nm = _pn900.short_place_name(nxt[3])          # [LOCAL-900] a short place name, not the raw title
            if d is not None and max_km is not None and d > max_km:
                if log:
                    log(f"  [LOCAL-900B] BUG SIGNAL: Stop {num} -> next stop is {d:.1f} km apart "
                        f"(> {max_km:.0f} km on a single-place tour); the pins are wrong. Distance left out.")
                d = None
            if d is not None and d < walk_km:
                line = f"Walk on to {_nm}."
            else:
                line = f"Continue to {_nm}."
                if d is not None:
                    line += f" It is roughly {d:.1f} km away."
            # [LOCAL-900] rebuilt from the template only: the model's own travel sentences are set aside
            _rest = " ".join(x for x in split_sentences(dm.group(1))
                             if not re.match(r"(?i)^(?:continue|walk on|head|go|proceed)\b.*\bto\b|^it is roughly\b", x))
            sc = _scenery_clause(_rest)
            if sc:
                line += " " + sc
            new = f"Directions: {line}"
            if new != dm.group(0):
                if log:
                    log(f"  [LOCAL-898] Stop {num}: Directions reduced to the continue/walk-on form")
                block = block[:dm.start()] + new + block[dm.end():]
        out.append(block)
    out.append(tour_text[pos:])
    return "".join(out)


def order_directions_last(tour_text: str, log: Optional[Callable] = None) -> str:
    """[LOCAL-898] The body always comes before Directions: a Directions line that sits above body
    prose in its block is moved below the last body line (the route closing, if any, stays last)."""
    if not tour_text:
        return tour_text
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        lines = block.split("\n")
        di = next((i for i, ln in enumerate(lines) if re.match(r"(?i)^directions\s*:", ln)), None)
        if di is not None:
            ci = next((i for i, ln in enumerate(lines) if i > 0 and _CLOSING_LINE.match(ln.strip())), len(lines))
            body = [i for i, ln in enumerate(lines) if 0 < i < ci and i != di and ln.strip() and not _KEYED.match(ln)]
            if body and body[-1] > di:
                dline = lines.pop(di)
                last = body[-1] - 1
                spaced = len(lines) > 1 and not lines[1].strip()
                lines[last + 1:last + 1] = ([""] if spaced else []) + [dline]
                block = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
                if not block.endswith("\n") and tour_text[s:e].endswith("\n"):
                    block += "\n"
                if log:
                    log(f"  [LOCAL-898] Stop {num}: Directions moved below the body")
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── distinct Type/Specialty per stop ─────────────────────────────────────────
_KIND_LABELS = (
    (re.compile(r"(?i)\b(?:cable\s*car|ropeway|gondola|funicular|chairlift)\b"), "Cable car ride"),
    (re.compile(r"(?i)\b(?:plantations?|farms?|fields?|orchards?|fruit|paddies|vineyards?|agricultur\w*)\b"), "Agricultural area"),
    (re.compile(r"(?i)\b(?:pagoda|temple|shrine|monastery|church|cathedral|mosque)\b"), "Place of worship"),
    (re.compile(r"(?i)\b(?:statue|monument|memorial|buddha|sculpture)\b"), "Monument or statue"),
    (re.compile(r"(?i)\b(?:museum|gallery)\b"), "Museum"),
    (re.compile(r"(?i)\bmarkets?\b"), "Market"),
    (re.compile(r"(?i)\b(?:summit|viewpoint|lookout|views?|vistas?|overlook)\b"), "Scenic viewpoint"),
    (re.compile(r"(?i)\b(?:beach|coast|bay|harbou?r|fishing)\b"), "Coastal area"),
    (re.compile(r"(?i)\b(?:river|lake|waterfall)\b"), "Water feature"),
    (re.compile(r"(?i)\b(?:mountain|mount|peak|hill)\b"), "Mountain area"),
    (re.compile(r"(?i)\b(?:city|town|village)\b"), "Town or village"),
)
_TYPE_LINE = re.compile(r"(?mi)^Type/Specialty:[ \t]*(.*)$")


def _kind_label(title: str) -> Optional[str]:
    for rx, label in _KIND_LABELS:
        if rx.search(title or ""):
            return label
    return None


def distinct_type_specialty(tour_text: str, log: Optional[Callable] = None) -> str:
    """[LOCAL-898] A stop whose Type/Specialty repeats the PREVIOUS stop's (a different place) gets a
    label derived from its own title; when the title says nothing about its kind the copied line is
    removed -- no label is better than the neighbour's."""
    if not active() or not tour_text:
        return tour_text
    pieces, pos, prev = [], 0, ""            # prev = the previous stop's line AS DELIVERED
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        m = _TYPE_LINE.search(block)
        cur = fold(m.group(1)).strip() if m else ""
        if m and cur and cur == prev:
            label = _kind_label(title)
            if label and fold(label) != cur:
                block = block[:m.start()] + f"Type/Specialty: {label}" + block[m.end():]
            else:
                block = (block[:m.start()] + block[m.end():].lstrip("\n")) if label is None else block
            if log:
                log(f"  [LOCAL-898] Stop {num} '{title[:40]}': Type/Specialty copied from the previous stop -> "
                    f"{label or 'removed'}")
        prev = cur
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── two people for one object ────────────────────────────────────────────────
_MAKER = r"(?:built|constructed|erected|carved|sculpted|created|made|cast)"
_DESIGNER = r"(?:designed|planned)"
_FOUNDER = r"(?:founded|established)"
_ROLE_RX = re.compile(
    r"(?i:\b(?P<verb>" + "|".join((_MAKER, _DESIGNER, _FOUNDER)) + r"))\b(?:\s+in\s+\d{3,4})?\s+by\s+(?:the\s+)?"
    r"(?:(?i:sculptor|architect|designer|master|artist|craftsman|builder|monk|abbot|emperor|king|prince)\s+)?"
    r"(?P<name>[A-ZÀ-Ỹ][^\W\d_]+(?:\s+[A-ZÀ-Ỹ][^\W\d_]+){0,3})")


def _role_of(verb: str) -> str:
    v = verb.lower()
    if re.fullmatch(_DESIGNER, v):
        return "designer"
    if re.fullmatch(_FOUNDER, v):
        return "founder"
    return "maker"


def _creator_claims(sentence: str) -> List[Tuple[str, str]]:
    return [(_role_of(m.group("verb")), m.group("name").strip()) for m in _ROLE_RX.finditer(sentence)]


def _same_person(a: str, b: str) -> bool:
    ta, tb = set(_words(a)), set(_words(b))
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def consistent_creators(tour_text: str, evidence_by_title: Optional[Dict[str, str]],
                        log: Optional[Callable] = None) -> str:
    """[LOCAL-898] Two stops naming DIFFERENT people for the same role (built/carved/designed/founded by)
    of the same object: keep the sentence whose name the evidence of the two stops states, drop the
    other; neither stated -> drop both; both stated -> leave. Same object = two or more content words
    shared by the sentences (plus their stops' titles), the names aside. ``evidence_by_title`` falsy
    (no evidence map available) -> unchanged."""
    if not active() or not tour_text or not evidence_by_title:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in evidence_by_title.items()}
    blocks = _stop_blocks(tour_text)
    claims = []          # (stop idx, sentence, role, name, object tokens)
    for bi, (s, e, num, title) in enumerate(blocks):
        for ln in tour_text[s:e].split("\n")[1:]:
            if not ln.strip() or _KEYED.match(ln) or _CLOSING_LINE.match(ln.strip()):
                continue
            for sent in split_sentences(ln):
                for role, name in _creator_claims(sent):
                    claims.append((bi, sent, role, name, _content_tokens(sent) | _content_tokens(title)))
    drop: Dict[int, set] = {}
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            (bi, si, ri, ni, ti), (bj, sj, rj, nj, tj) = claims[i], claims[j]
            if bi == bj or ri != rj or _same_person(ni, nj):
                continue
            gone = set(_words(ni)) | set(_words(nj))
            skip = set()
            for p in (_STATE["origin"], _STATE["destination"], *_STATE["through"]):
                skip |= _content_tokens(p)
            if len((ti - gone - skip) & (tj - gone - skip)) < 2:
                continue
            ev = fold(" ".join(str(ev_map.get(fold(blocks[x][3]), "")) for x in (bi, bj)))
            ev_words = " ".join(_words(ev))
            ok_i = " ".join(_words(ni)) in ev_words
            ok_j = " ".join(_words(nj)) in ev_words
            if ok_i and ok_j:
                continue
            if not ok_i:
                drop.setdefault(bi, set()).add(si)
            if not ok_j:
                drop.setdefault(bj, set()).add(sj)
    if not drop:
        return tour_text
    pieces, pos = [], 0
    for bi, (s, e, num, title) in enumerate(blocks):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        if bi in drop:
            def fix(sents: List[str], _d=drop[bi], _n=num, _t=title) -> List[str]:
                for x in sents:
                    if x in _d and log:
                        log(f"  [LOCAL-898] Stop {_n} '{_t[:40]}': conflicting creator not supported by the evidence "
                            f"-> sentence dropped: \"{x[:90]}\"")
                return [x for x in sents if x not in _d]
            block = _rewrite_prose(block, fix)
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ══ [LOCAL-900] wave 46 leftovers ═══════════════════════════════════════════
_TYPE_RX = re.compile(r"(?mi)^Type/Specialty:[ \t]*(.*)$")


def _neighbour_evidence(blocks, k: int, ev_map: Dict[str, str], tour_text: str, km: float = 1.0) -> List[str]:
    """Evidence of the OTHER stops at the same site (same pin, or < km) as stop ``k``."""
    mine = _pin(tour_text[blocks[k][0]:blocks[k][1]])
    out = []
    for j, (s, e, num, title) in enumerate(blocks):
        if j == k:
            continue
        other = _pin(tour_text[s:e])
        if mine and other and _km(mine, other) < km:
            out.append(str(ev_map.get(fold(title), "") or ""))
    return out


_HONEST_SKELETON = re.compile(
    r"(?i)look out at the road|look around you at the street|take a moment at|look out at the view|"
    r"courtyard and the quiet|listen to the sounds of the journey|listen for the sounds that belong|"
    r"feel the height")


_HONEST_DONE: set = set()      # [LOCAL-900B] folded bodies this module has already produced


def rebuild_honest_bodies(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                          log: Optional[Callable] = None) -> str:
    """[LOCAL-900] The D760 honest body of a route stop is rebuilt with (a) the SHORT place name, (b) the
    sensory sentences chosen by the stop's Type/Specialty or title kind (road/field -> the road; summit,
    cable car -> view and height; temple -> courtyard and quiet; otherwise neutral), and (c) one
    supported sentence from a neighbouring stop at the same site when it speaks about this stop's subject."""
    if not active() or not tour_text:
        return tour_text
    import strict_grounding_gate as sgg
    import place_names_900 as pn
    ev_map = {fold(str(k)): v for k, v in (evidence_by_title or {}).items()}
    blocks = _stop_blocks(tour_text)
    pieces, pos = [], 0
    disc = fold(sgg.NO_HISTORY_DISCLOSURE)[:30]
    for k, (s, e, num, title) in enumerate(blocks):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        lines = block.split("\n")
        body = [i for i, ln in enumerate(lines) if i > 0 and ln.strip() and not _KEYED.match(ln)
                and not _CLOSING_LINE.match(ln.strip())]
        text = " ".join(lines[i] for i in body)
        if body and disc in fold(text) and _HONEST_SKELETON.search(text) and not any(
                _CLOSING_LINE.match(x) for i in body for x in split_sentences(lines[i])):
            tm = _TYPE_RX.search(block)
            neigh = pn.neighbour_sentence(pn.short_place_name(title),
                                          _neighbour_evidence(blocks, k, ev_map, tour_text), split_sentences)
            honest = " ".join(sgg.sensory_body(title, [sgg.NO_HISTORY_DISCLOSURE], sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                               register="driving", kind_text=tm.group(1) if tm else "",
                                               supported_sentence=neigh))
            if fold(text) in _HONEST_DONE and (not neigh or fold(neigh) in fold(text)):
                # [LOCAL-900B] this body is already the output of an earlier rebuild (finalize_898 runs more than
                # once): a second pass, possibly without the evidence, must not overwrite the neighbour sentence
                pieces.append(block)
                continue
            _HONEST_DONE.add(fold(honest))
            if fold(honest) != fold(text):
                lines[body[0]] = honest
                for i in body[1:]:
                    lines[i] = None
                if log:
                    log(f"  [LOCAL-900] Stop {num} '{title[:40]}': honest body rebuilt (short name, "
                        f"kind={pn.stop_kind(title, tm.group(1) if tm else '')}, "
                        f"neighbour sentence={'yes' if neigh else 'no'})")
                block = "\n".join(ln for ln in lines if ln is not None)
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── superlatives about the same object ───────────────────────────────────────
_SUP_GROUP = {"longest": "long", "largest": "big", "biggest": "big", "tallest": "tall", "highest": "tall",
              "oldest": "old", "deepest": "deep", "widest": "wide", "smallest": "small"}
_SUP_RX = re.compile(r"(?i)\b(?P<sup>" + "|".join(_SUP_GROUP) + r")\s+(?P<obj>(?:[A-Za-z\-]+\s+){0,3}?[A-Za-z\-]+)"
                     r"\s+in\s+(?P<reg>(?:the\s+)?[A-ZÀ-Ỹ][^\W\d_]+(?:\s+[A-ZÀ-Ỹ][^\W\d_]+){0,2})")


def _superlatives(sentence: str) -> List[Dict]:
    out = []
    for m in _SUP_RX.finditer(sentence):
        obj = [w for w in _words(m.group("obj")) if w not in {"the", "a", "an", "one", "of", "all"}]
        if obj:
            out.append({"sup": m.group("sup").lower(), "grp": _SUP_GROUP[m.group("sup").lower()], "obj": set(obj),
                        "reg": set(_words(m.group("reg"))) - {"the"}, "span": m.span(), "text": sentence})
    return out


def _sup_in_evidence(c: Dict, evidence: str) -> bool:
    """The evidence states this superlative of this object in this region (word match, any wording of the
    same degree: largest = biggest)."""
    ev = " ".join(_words(evidence))
    for m in re.finditer(r"\b(" + "|".join(k for k, g in _SUP_GROUP.items() if g == c["grp"]) + r")\b", ev):
        win = set(ev[m.end():m.end() + 90].split())
        if (c["obj"] & win) and (c["reg"] & win):
            return True
    return False


def _cut_clause(sentence: str, c: Dict) -> Optional[str]:
    """The sentence without the superlative clause; None when nothing worth keeping is left."""
    a, b = c["span"]
    head = sentence[:a]
    head = re.sub(r"(?i)[,;]?\s*(?:and\s+)?(?:it\s+(?:is|was)\s+)?(?:(?:one of\s+)?the|a|an)\s*$", "", head).rstrip(" ,;")
    tail = sentence[b:].lstrip()
    rest = (head + (" " + tail if tail and tail[0] not in ".,;!?" else tail)).strip()
    rest = re.sub(r"(?i)[,;]\s*(?:and|which is|that is)\s*([.!?]?)$", r"\1", rest)
    rest = rest.rstrip(" ,;")
    if rest and rest[-1] not in ".!?":
        rest += "."
    return rest if len(rest.split()) >= 5 and not re.match(r"(?i)^(?:it|this|that)\s+(?:is|was)\s*\.?$", rest) else None


def consistent_superlatives(tour_text: str, evidence_by_title: Optional[Dict[str, str]],
                            log: Optional[Callable] = None) -> str:
    """[LOCAL-900] Two stops claiming a superlative of the SAME object (longest/largest/biggest/tallest/
    oldest ... in <region>) with a different degree or region: keep one, drop the other. The claim whose
    own stop's evidence states it wins; if both are stated the stop whose title names the object wins
    (else the earlier stop); if neither is stated both go. ``evidence_by_title`` falsy -> unchanged."""
    if not active() or not tour_text or not evidence_by_title:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in evidence_by_title.items()}
    blocks = _stop_blocks(tour_text)
    claims = []
    for bi, (s, e, num, title) in enumerate(blocks):
        ev = str(ev_map.get(fold(title), "") or "")
        for ln in tour_text[s:e].split("\n")[1:]:
            if not ln.strip() or _KEYED.match(ln) or _CLOSING_LINE.match(ln.strip()):
                continue
            for sent in split_sentences(ln):
                for c in _superlatives(sent):
                    c.update(bi=bi, ok=_sup_in_evidence(c, ev), titled=bool(c["obj"] & set(_words(title))))
                    claims.append(c)
    drop = []                                  # claims to remove
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            a, b = claims[i], claims[j]
            if a["bi"] == b["bi"] or len(a["obj"] & b["obj"]) < 2 and not (a["obj"] <= b["obj"] or b["obj"] <= a["obj"]):
                continue
            if a["grp"] == b["grp"] and a["reg"] == b["reg"]:
                continue                        # the same claim twice is not a conflict
            if a["ok"] and not b["ok"]:
                gone = [b]
            elif b["ok"] and not a["ok"]:
                gone = [a]
            elif not a["ok"] and not b["ok"]:
                gone = [a, b]
            else:
                keep = b if (b["titled"] and not a["titled"]) else a
                gone = [b if keep is a else a]
            for g in gone:
                if g not in drop:
                    drop.append(g)
    if not drop:
        return tour_text
    pieces, pos = [], 0
    for bi, (s, e, num, title) in enumerate(blocks):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        mine = [g for g in drop if g["bi"] == bi]
        if mine:
            def fix(sents: List[str], _m=mine, _n=num, _t=title) -> List[str]:
                out = []
                for x in sents:
                    hit = [g for g in _m if g["text"] == x]
                    if hit:
                        # [LOCAL-900B] the WHOLE sentence goes. Cutting only the clause left "Ta Cu Mountain is
                        # home to." and "This pagoda is home to, measuring 49 meters in length."
                        if log:
                            log(f"  [LOCAL-900] Stop {_n} '{_t[:40]}': conflicting superlative -> "
                                f"sentence dropped: \"{x[:90]}\"")
                        continue
                    out.append(x)
                return out
            block = _rewrite_prose(block, fix)
        pieces.append(block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


# ── a measurement the evidence does not hold ─────────────────────────────────
_MEASURE = re.compile(r"(?i)\b(?P<n>\d[\d,\.]*)\s*(?P<u>meters?|metres?|m|feet|ft|kilomet\w+|km|miles?|tons?|tonnes?|steps)\b")


def _ev_numbers(text: str) -> set:
    return {x.replace(",", "") for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


def cap_unsupported_numbers(tour_text: str, evidence_by_title: Optional[Dict[str, str]],
                            log: Optional[Callable] = None) -> str:
    """[LOCAL-900] A measurement (N meters / feet / km / ...) in a stop body whose number is in neither the
    stop's evidence nor its title is the unsupported-claim case: the clause (or sentence) carrying it is
    dropped. Stops with no evidence entry are left to the other caps. Travel distances are not touched
    (strip_body_travel owns those)."""
    if not active() or not tour_text or not evidence_by_title:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in evidence_by_title.items()}
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        ev = _ev_for(ev_map, title)
        if ev is None:
            if log:
                log(f"  [LOCAL-900B] Stop {num} '{title[:40]}': no evidence entry under this title; measurements "
                    f"are NOT checked for it")
            pieces.append(block)
            continue
        have = _ev_numbers(str(ev)) | _ev_numbers(title)

        def fix(sents: List[str], _n=num, _t=title, _have=have) -> List[str]:
            out = []
            for x in sents:
                bad = [m for m in _MEASURE.finditer(x) if m.group("n").replace(",", "").rstrip(".") not in _have
                       and not _has_travel(x[max(0, m.start() - 0):m.end() + 12] + " away")]
                if not bad:
                    out.append(x)
                    continue
                parts = re.split(r"(?i),\s*(?:and|but|which)\s+|;\s*", x)
                keep = [p for p in parts if not any(m.group(0) in p for m in bad)]
                y = " ".join(keep).strip() if keep and len(parts) > 1 else ""
                if y:
                    y = y[0].upper() + y[1:]
                    y = y if y[-1] in ".!?" else y + "."
                if log:
                    log(f"  [LOCAL-900] Stop {_n} '{_t[:40]}': measurement '{bad[0].group(0)}' not in the evidence -> "
                        f"{'clause' if y else 'sentence'} dropped: \"{x[:90]}\"")
                if y and len(y.split()) >= 5:
                    out.append(y)
            return out
        pieces.append(_rewrite_prose(block, fix))
    pieces.append(tour_text[pos:])
    return "".join(pieces)



# ══ [LOCAL-900B] wave 47 ════════════════════════════════════════════════════
_DANGLE_END = {"to", "of", "in", "at", "by", "for", "with", "from", "into", "than", "as", "the", "a", "an", "and",
               "or", "but", "is", "are", "was", "were", "has", "have", "had", "that", "which", "measuring",
               "covering", "spanning", "stretching", "standing", "reaching"}
_PARTICIPLE_OPEN = re.compile(r"(?i)^(?:measuring|covering|spanning|stretching|standing|reaching)\b")
_EMPTY_CLAUSE = re.compile(r"(?i),\s*,|\b(?:to|of|at|by|with|than)\s*,\s*(?:measuring|covering|spanning|standing|"
                           r"stretching|reaching|which|and)\b|\b(?:covers?|spans?)\s+of\s+the\b")


def is_fragment(sentence: str) -> bool:
    """A sentence that is not whole: it ends on a preposition / article / dangling verb, opens with a comma or a
    bare participle, or holds an empty clause between commas."""
    x = (sentence or "").strip()
    if not x:
        return False
    core = x.rstrip(" .!?;:\"'\u201d)")
    if not core:
        return True
    if x[0] in ",;" or _PARTICIPLE_OPEN.match(x):
        return True
    last = _words(core.split()[-1]) if core.split() else []
    if last and last[-1] in _DANGLE_END:
        return True
    return bool(_EMPTY_CLAUSE.search(x))


def drop_fragments(tour_text: str, log: Optional[Callable] = None, force: bool = False) -> str:
    """[LOCAL-900B] Final guard over every stop body (and Orientation): a sentence that is a fragment goes, whole.
    A body (or Orientation) emptied by it is left as it was only when ALL its sentences are fragments and the
    stop would otherwise be silent; an emptied Orientation line is removed."""
    if (not active() and not force) or not tour_text:
        return tour_text
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        lines = block.split("\n")
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip():
                continue
            mo = re.match(r"(?i)^(\s*orientation\s*:\s*)(.*)$", ln)
            if _KEYED.match(ln) and not mo:
                continue
            head, txt = (mo.group(1), mo.group(2)) if mo else ("", ln)
            sents = split_sentences(txt)
            closing = next((k for k, x in enumerate(sents) if _CLOSING_LINE.match(x)), len(sents))
            own, tail = sents[:closing], sents[closing:]
            keep = [x for x in own if not is_fragment(x)]
            if len(keep) == len(own):
                continue
            for x in own:
                if is_fragment(x) and log:
                    log(f"  [LOCAL-900B] Stop {num} '{title[:40]}': fragment sentence dropped: \"{x[:90]}\"")
            new = " ".join(keep + tail)
            lines[i] = (head + new) if new.strip() else (None if mo else "")
        new_block = "\n".join(x for x in lines if x is not None)
        if not any(ln.strip() and not _KEYED.match(ln) for ln in new_block.split("\n")[1:]):
            if log:
                log(f"  [LOCAL-900B] Stop {num} '{title[:40]}': every sentence is a fragment; body left as it was")
            new_block = block                  # never an emptied stop (fill_empty_bodies owns that on a route)
        pieces.append(new_block)
    pieces.append(tour_text[pos:])
    return "".join(pieces)


_CARRY_FILLER = re.compile(r"(?i)^.{2,120}?\bis one you might carry with you[.!]?$")


def drop_carry_filler(tour_text: str, log: Optional[Callable] = None) -> str:
    """[LOCAL-900B] The closing filler "<X> is one you might carry with you." names a stop and says nothing."""
    if not tour_text or "carry with you" not in tour_text.lower():
        return tour_text
    out = []
    for ln in tour_text.split("\n"):
        if "carry with you" in ln.lower():
            sents = split_sentences(ln)
            keep = [x for x in sents if not _CARRY_FILLER.match(x)]
            if len(keep) != len(sents):
                if log:
                    log("  [LOCAL-900B] closing filler '... is one you might carry with you.' dropped")
                ln = " ".join(keep)
                if not ln.strip():
                    continue
        out.append(ln)
    return "\n".join(out)


# ── [LOCAL-901] mood filler on the single-place path (897 cap, as 900B's _supported tightened it) ──────────
_MOOD = re.compile(
    r"(?i)\b(?:breeze|echo\w*|whisper\w*|seren(?:e|ity)|tranquil\w*|spiritual\w*|embod\w+|enduring|shifting|"
    r"tapestry|testament|symboli[sz]\w*|peace\w*|harmon\w+|essence|timeless|reverberat\w+|crossroads|gentl[ey]\w*|"
    r"creak\w*|exemplified|bygone|ethereal|palpable|enlightenment|passage\s+of|connection\s+between|"
    r"significance\s+of|natural\s+world|sense\s+of|reminder\s+of|stands?\s+as\s+a)\b")
_MOOD_DENSE = 2          # this many distinct mood terms and no number: filler whatever it names
_SUPPORT_LINE = re.compile(r"(?i)^\s*(specific examples|type/specialty)\s*:\s*(.*)$")


def mood_terms(sentence: str) -> set:
    return {m.group(0).lower() for m in _MOOD.finditer(sentence or "")}


def is_mood_filler(sentence: str, support: set) -> bool:
    """[LOCAL-901] A sentence that is mood, not information: no digit AND either dense in mood terms
    (>= 2) or carrying one and not ``_supported`` by the stop's own title / examples. A sentence with a
    number, or with no mood term at all, is never filler here."""
    if re.search(r"\d", sentence or ""):
        return False
    hits = mood_terms(sentence)
    if not hits:
        return False
    return len(hits) >= _MOOD_DENSE or not _supported(sentence, support)


def cap_single_place_filler(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                            log: Optional[Callable] = None) -> str:
    """[LOCAL-901] The 897 unsupported / mood-filler cap for the single-place path (where the 897 route
    pass never runs), applied to every stop body AND to the closing paragraph. Support is the stop's own
    title, its Type / Specific Examples lines and (when given) its evidence; the closing paragraph is
    supported by every stop's. ``That's N stops`` / the restaurant offer are never touched, and a stop
    whose whole body would go is left as it was. Pure, free, name-free."""
    if not tour_text:
        return tour_text
    blocks = _stop_blocks(tour_text)
    if not blocks:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in (evidence_by_title or {}).items()}

    def support_of(title: str, block: str) -> set:
        sup = _content_tokens(title)
        for ln in block.split("\n"):
            m = _SUPPORT_LINE.match(ln)
            if m:
                sup |= _content_tokens(m.group(2))
        sup |= _content_tokens(ev_map.get(fold(title), "") or "")
        return sup

    all_support = set()
    for s, e, _n, title in blocks:
        all_support |= support_of(title, tour_text[s:e])
    pieces, pos = [], 0
    for bi, (s, e, num, title) in enumerate(blocks):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        sup = support_of(title, block)
        lines = block.split("\n")
        dropped, kept_any, changed = [], False, False
        new_lines = list(lines)
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or _KEYED.match(ln):
                continue
            sents = split_sentences(ln)
            # the closing paragraph (a later paragraph of the LAST stop) is supported by every stop's
            keep, para_sup = [], (all_support if (bi == len(blocks) - 1 and _is_after_body(lines, i)) else sup)
            for x in sents:
                if _CLOSING_LINE.match(x):
                    keep.append(x)
                elif is_mood_filler(x, para_sup):
                    dropped.append(x)
                else:
                    keep.append(x)
                    kept_any = True
            if len(keep) != len(sents):
                new_lines[i] = " ".join(keep) if keep else None
                changed = True
        if changed and not kept_any:
            if log:
                log(f"  [LOCAL-901] Stop {num} '{title[:40]}': every body sentence reads as mood filler; body left as it was")
            pieces.append(block)
            continue
        if log:
            for x in dropped:
                log(f"  [LOCAL-901] Stop {num} '{title[:40]}': mood filler dropped (no support, no concrete fact): \"{x[:100]}\"")
        pieces.append(re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in new_lines if x is not None)))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


def _is_after_body(lines: List[str], i: int) -> bool:
    """True when line ``i`` is a later paragraph of the block (after the first body line): the closing."""
    first = next((k for k, ln in enumerate(lines) if k > 0 and ln.strip() and not _KEYED.match(ln)), None)
    return first is not None and i > first


def apply_single_place_guards(tour_text: str, log: Optional[Callable] = None, max_stops: int = 2,
                              max_km: float = 100.0,
                              evidence_by_title: Optional[Dict[str, str]] = None) -> str:
    """[LOCAL-900B] Guards that are not specific to a described route, for the delivery path of any tour: the
    carry-with-you filler goes, fragment sentences go, and a tour of at most ``max_stops`` stops (the single-place
    path, where the 898 normalizer never ran) gets its Directions reduced to the template, with a leg over
    ``max_km`` treated as a pin bug (logged, no distance spoken)."""
    if not tour_text:
        return tour_text
    t = drop_carry_filler(tour_text, log)
    if not active() and len(_stop_blocks(t)) <= max_stops:
        t = cap_single_place_filler(t, evidence_by_title, log)      # [LOCAL-901] mood filler + closing paragraph
    t = drop_fragments(t, log, force=True)
    if not active() and len(_stop_blocks(t)) <= max_stops:
        t = normalize_directions(t, log, force=True, max_km=max_km)
    return t


def _ev_for(ev_map: Dict[str, str], title: str) -> Optional[str]:
    """The evidence for a stop title: exact folded key, else a key that contains / is contained in it."""
    f = fold(title)
    if f in ev_map:
        return ev_map[f]
    for k, v in ev_map.items():
        if k and f and (k in f or f in k):
            return v
    return None


_COMPARATIVE = re.compile(r"(?i)\b(?:larger|bigger|taller|longer|older|higher|smaller|greater|wider|deeper)\s+than\b")
_CAP_WORD = re.compile(r"\b[A-ZÀ-Ỹ][^\W\d_]{2,}")


def drop_unsupported_comparatives(tour_text: str, evidence_by_title: Optional[Dict[str, str]],
                                  log: Optional[Callable] = None) -> str:
    """[LOCAL-900B] "larger than the statues at <A> and <B> in <C>": a comparison with other NAMED places that the
    stop's own evidence does not state. The whole sentence goes. Stops with no evidence entry are untouched."""
    if not active() or not tour_text or not evidence_by_title:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in evidence_by_title.items()}
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        ev = _ev_for(ev_map, title)
        if ev is None:
            pieces.append(block)
            continue
        have = set(_words(str(ev))) | set(_words(title))

        def fix(sents: List[str], _n=num, _t=title, _have=have) -> List[str]:
            out = []
            for x in sents:
                m = _COMPARATIVE.search(x)
                if m:
                    names = [w for w in _CAP_WORD.findall(x[m.end():])]
                    if names and any(fold(w) not in _have for w in names):
                        if log:
                            log(f"  [LOCAL-900B] Stop {_n} '{_t[:40]}': comparison with other places not in the "
                                f"evidence -> sentence dropped: \"{x[:90]}\"")
                        continue
                out.append(x)
            return out
        pieces.append(_rewrite_prose(block, fix))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_BY_CREATOR = re.compile(r"(?i)\bby\s+(?:the\s+)?(?:sculptor|architect|artist|monk|master|designer|builder|painter)\s+"
                         r"((?:[A-ZÀ-Ỹ][^\W\d_]+\s*){1,4})")


def cap_unsupported_facts(tour_text: str, evidence_by_title: Optional[Dict[str, str]],
                          log: Optional[Callable] = None) -> str:
    """[LOCAL-900B] A year, or a "by sculptor <Name>" creator, that neither the stop's evidence nor its title holds:
    the clause (or sentence) carrying it goes. Stops with no evidence entry are untouched (logged)."""
    if not active() or not tour_text or not evidence_by_title:
        return tour_text
    ev_map = {fold(str(k)): v for k, v in evidence_by_title.items()}
    pieces, pos = [], 0
    for s, e, num, title in _stop_blocks(tour_text):
        pieces.append(tour_text[pos:s])
        block = tour_text[s:e]
        pos = e
        ev = _ev_for(ev_map, title)
        if ev is None:
            if log:
                log(f"  [LOCAL-900B] Stop {num} '{title[:40]}': no evidence entry under this title; years / "
                    f"creators / measurements are NOT checked for it")
            pieces.append(block)
            continue
        evw, evtxt = set(_words(str(ev))), str(ev)

        def bad_in(x: str) -> List[str]:
            out = [m.group(0) for m in _YEAR.finditer(x) if m.group(0) not in evtxt and m.group(0) not in title]
            for m in _BY_CREATOR.finditer(x):
                toks = [fold(w) for w in m.group(1).split()]
                if toks and not all(t in evw for t in toks):
                    out.append(m.group(0).strip())
            return out

        def fix(sents: List[str], _n=num, _t=title) -> List[str]:
            out = []
            for x in sents:
                bad = bad_in(x)
                if not bad:
                    out.append(x)
                    continue
                parts = re.split(r"(?i),\s*(?:and|but|which)\s+|;\s*|,\s+(?=built|created|made|carved|sculpted)", x)
                keep = [p for p in parts if not bad_in(p)]
                y = " ".join(keep).strip() if keep and len(parts) > 1 else ""
                if not y:
                    # "..., built in 1963 by sculptor X." -> keep the head before the first bad comma clause
                    head = re.split(r",\s+", x)[0]
                    y = head if len(parts) == 1 and len(re.split(r",\s+", x)) > 1 and not bad_in(head) else ""
                if y:
                    y = y[0].upper() + y[1:]
                    y = y if y[-1] in ".!?" else y + "."
                if log:
                    log(f"  [LOCAL-900B] Stop {_n} '{_t[:40]}': '{bad[0]}' not in the evidence -> "
                        f"{'clause' if y and len(y.split()) >= 5 else 'sentence'} dropped: \"{x[:90]}\"")
                if y and len(y.split()) >= 5 and not is_fragment(y):
                    out.append(y)
            return out
        pieces.append(_rewrite_prose(block, fix))
    pieces.append(tour_text[pos:])
    return "".join(pieces)


def finalize_898(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                 log: Optional[Callable] = None) -> str:
    """[LOCAL-898] The route text leftovers, in order: creators agree, no emptied body, body above
    Directions, Directions reduced, distinct Type/Specialty."""
    if not active() or not tour_text:
        return tour_text
    t = consistent_creators(tour_text, evidence_by_title, log)
    t = consistent_superlatives(t, evidence_by_title, log)          # [LOCAL-900]
    t = cap_unsupported_numbers(t, evidence_by_title, log)          # [LOCAL-900]
    t = cap_unsupported_facts(t, evidence_by_title, log)            # [LOCAL-900B] years / creators
    t = drop_unsupported_comparatives(t, evidence_by_title, log)    # [LOCAL-900B]
    t = drop_fragments(t, log)                                      # [LOCAL-900B] whole sentences only
    t = fill_empty_bodies(t, log)
    t = rebuild_honest_bodies(t, evidence_by_title, log)            # [LOCAL-900]
    t = order_directions_last(t, log)
    t = normalize_directions(t, log)
    t = distinct_type_specialty(t, log)
    t = drop_fragments(t, log)                                      # [LOCAL-900B] after the rebuilds, too
    return t
