"""[LOCAL-906] Content leftovers of wave 51 (route 551, single-place 552). Pure, offline, name-free (D769).

  1. ``drop_unsupported_claims``   exclusivity claims ("the only country in ..."), year + named builder, both
                                   dropped unless the stop's own evidence states them.
  2. ``repin_area_stops``          an AREA stop of a route whose unverified model pin is not between its neighbours.
  4. ``drop_contradicting_orientation``  "at the foot of <X>" after earlier stops already went up <X>.
  5. ``drop_repeated_sentences``   a sentence already delivered in an earlier stop.
  6. ``tone_first_stop``           pollution / trash / crime / disease / disaster in the FIRST stop's body.
  7. ``drop_template_closing``     "Across these stops, one thread runs through ..." filler.
  ``content_pass`` runs 1 (claims), 4, 5, 6, 7 in order on a route or a single-place tour; the comparatives and the
  Directions wayfinding live in route_content_896 (``drop_unsupported_comparatives(force=True)``,
  ``normalize_directions``). Every function returns the text unchanged on any error.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import route_content_896 as rc

TAG = "[LOCAL-906]"
SINGLE_PLACE_MAX_STOPS = 2


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _ev_for(ev_map: Dict[str, str], title: str) -> Optional[str]:
    return rc._ev_for(ev_map, title)


def _merged_evidence(evidence_by_title: Optional[Dict[str, str]]) -> Dict[str, str]:
    ev = dict(rc._EVIDENCE_904)
    ev.update({str(k): str(v) for k, v in (evidence_by_title or {}).items()})
    return {rc.fold(k): v for k, v in ev.items()}


def in_scope(text: str, max_stops: int = SINGLE_PLACE_MAX_STOPS) -> bool:
    """The passes below are for a described route or a single-place tour (<= ``max_stops`` stops)."""
    return rc.active() or len(rc._stop_blocks(text or "")) <= max_stops


def _body_line_idx(lines: List[str], last: bool) -> List[int]:
    """Prose lines that are the stop's own body (keyed lines excluded; on the last stop only the first prose
    line, the rest is the tour's closing)."""
    idx = [i for i, ln in enumerate(lines) if i > 0 and ln.strip() and not rc._KEYED.match(ln)]
    return idx[:1] if last and idx else idx


def _content_sents(lines: List[str], last: bool) -> List[str]:
    out: List[str] = []
    for i in _body_line_idx(lines, last):
        out += [x for x in rc.split_sentences(lines[i]) if not rc._CLOSING_LINE.match(x)]
    return out


def _filter_body(block: str, last: bool, keep_fn: Callable[[str], bool]) -> Tuple[str, List[str]]:
    """Drop the body sentences ``keep_fn`` rejects. Returns (new block, dropped sentences). Lines that would
    become empty are removed."""
    lines = block.split("\n")
    dropped: List[str] = []
    for i in _body_line_idx(lines, last):
        sents = rc.split_sentences(lines[i])
        keep = [x for x in sents if rc._CLOSING_LINE.match(x) or keep_fn(x)]
        if len(keep) != len(sents):
            dropped += [x for x in sents if x not in keep]
            lines[i] = " ".join(keep) if keep else None
    if not dropped:
        return block, []
    return re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None)), dropped


# ── 1. false / unsupported claims ─────────────────────────────────────────────────────────────────────────
_EXCL_CUE = re.compile(
    r"(?i)\b(?:(?:is|are|was|were|as)\s+the\s+(?:only|sole|first)|the\s+(?:only|sole)\b|no\s+other\b|"
    r"the\s+one\s+and\s+only|the\s+first\s+(?:country|nation|region|province|state|place|city)|"
    r"only\s+(?:country|nation|region|province|state|place|city)\b)")
_EXCL_GEO = re.compile(r"(?i)\b(?:countr(?:y|ies)|nations?|regions?|provinces?|states?|continents?|world|islands?|"
                       r"cit(?:y|ies)|southeast|northeast|asia|europe|africa)\b")
_EXCL_NOISE = {"only", "sole", "first", "other", "country", "nation", "region", "province", "world", "that"}
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_BUILDER = re.compile(
    r"\bby\s+(?:(?:the|sculptor|architect|artist|monk|master|designer|builder|painter|engineer|king|emperor)\s+)*<?"
    r"((?:[A-ZÀ-Ỹ][^\W\d_]+)(?:\s+[A-ZÀ-Ỹ][^\W\d_]+){0,3})")


def is_exclusivity_claim(sentence: str) -> bool:
    """"<Country> is the only country in <Region> that grows <fruit>": an only / first / sole / no-other claim
    about a country, region or place."""
    return bool(_EXCL_CUE.search(sentence or "") and _EXCL_GEO.search(sentence or ""))


def exclusivity_in_evidence(sentence: str, evidence: str) -> bool:
    """The stop's own evidence makes the same exclusivity claim: one evidence sentence with a cue and >= 3
    distinctive tokens in common with ``sentence``."""
    mine = rc._content_tokens(sentence) - _EXCL_NOISE
    for es in rc.split_sentences(evidence or ""):
        if _EXCL_CUE.search(es) and len((rc._content_tokens(es) - _EXCL_NOISE) & mine) >= 3:
            return True
    return False


def year_builder(sentence: str) -> Optional[Tuple[str, List[str]]]:
    """(year, builder name tokens) when the sentence holds a year AND a named builder ("began in 1958 by <Person>")."""
    y = _YEAR.search(sentence or "")
    b = _BUILDER.search(sentence or "")
    if not (y and b):
        return None
    return y.group(1), [rc.fold(w) for w in b.group(1).split()]


def year_builder_in_evidence(year: str, names: Sequence[str], evidence: str, title: str = "") -> bool:
    """Both the year and every token of the builder's name are in the evidence (or in the title)."""
    if not evidence:
        return False
    ev_words = set(rc._words(evidence))
    return (year in evidence or year in title) and all(n in ev_words or n in set(rc._words(title)) for n in names)


def drop_unsupported_claims(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                            log: Optional[Callable] = None) -> str:
    """Item 1. On a route / single-place tour: an exclusivity claim, or a year + named builder sentence, that the
    stop's own evidence does not state is dropped (the whole sentence). Evidence is the 904 stash plus
    ``evidence_by_title``; a stop with no evidence states nothing, so both go. 905's floor refills an emptied stop."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:   # [LOCAL-906C] a regional superlative / exclusivity claim needs evidence for the SAME or a wider scope, on ANY tour
        import leftovers_906c as _c
        tour_text = _c.drop_unsupported_scope_claims(tour_text, evidence_by_title, log)
    except Exception as _e906c:  # pragma: no cover
        emit(f"  [LOCAL-906C] scope-claim guard skipped (non-fatal): {_e906c}")
    try:   # [LOCAL-906F] blocked claims, promo, cross-stop conflicts, leads, names, hyphens, person pronouns
        import leftovers_906f as _f906f
        tour_text = _f906f.run_pass(tour_text, evidence_by_title, log)
    except Exception as _e906f:  # pragma: no cover
        emit(f"  [LOCAL-906F] pass skipped (non-fatal): {_e906f}")
    if not in_scope(tour_text):
        return tour_text
    try:
        import leftovers_906c as _c
        ev_map = _merged_evidence(evidence_by_title)
        blocks = rc._stop_blocks(tour_text)
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            ev = _ev_for(ev_map, title) or ""

            def keep(x: str, _ev=ev, _t=title, _n=num) -> bool:
                if _c.check_claim(x, _ev, _t)[0] == "ok":
                    return True                      # [LOCAL-906C] scope-matched evidence states it
                if is_exclusivity_claim(x) and not exclusivity_in_evidence(x, _ev):
                    emit(f"  {TAG} Stop {_n} '{_t[:40]}': exclusivity claim not in the stop's evidence "
                         f"-> sentence dropped: \"{x[:100]}\"")
                    return False
                yb = year_builder(x)
                if yb and not year_builder_in_evidence(yb[0], yb[1], _ev, _t):
                    emit(f"  {TAG} Stop {_n} '{_t[:40]}': year {yb[0]} + builder not in the stop's evidence "
                         f"({'held neither' if not _ev else 'evidence lacks them'}) -> sentence dropped: \"{x[:100]}\"")
                    return False
                return True
            new, _dropped = _filter_body(tour_text[s:e], k == len(blocks) - 1, keep)
            pieces.append(new)
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} claim guard skipped (non-fatal): {err}")
        return tour_text


# ── 2. an area stop's pin lies between its neighbours ─────────────────────────────────────────────────────
MAX_OFF_SEGMENT_KM = 10.0
_AREA_WORD = re.compile(r"(?i)\b(?:area|region|district|province|countryside|farmland|farmlands|plain|plains|valley|"
                        r"delta|zone|corridor|plantations?|highlands?|uplands?|country|coast|coastline)\b")
_VENUE_WORD = re.compile(
    r"(?i)\b(?:temple|pagoda|statue|museum|market|station|hotel|resort|beach|mountain|mount|park|bridge|castle|church|"
    r"cathedral|monument|building|house|gallery|palace|tower|fort|cable|lake|river|square|harbou?r|port|restaurant|"
    r"cave|waterfall|summit|peak|shrine|mosque|garden|gardens|dunes?|lighthouse)\b")


def is_area_stop(title: str, type_text: str = "") -> bool:
    """A stop that is an area (a province, a stretch of farmland) and has no venue of its own."""
    t, ty = title or "", type_text or ""
    if ty and _AREA_WORD.search(ty) and not _VENUE_WORD.search(ty):
        return True
    return bool(_AREA_WORD.search(t) and not _VENUE_WORD.search(t) and not (ty and _VENUE_WORD.search(ty)))


def _xy(p: Tuple[float, float], o: Tuple[float, float]) -> Tuple[float, float]:
    """Kilometres east / north of ``o`` (equirectangular, fine at route scale)."""
    return ((p[1] - o[1]) * math.cos(math.radians((p[0] + o[0]) / 2.0)) * 111.195, (p[0] - o[0]) * 111.195)


def segment_position(p, a, b) -> Tuple[float, float, float]:
    """(t, off_km, along_km): ``t`` = projection of ``p`` on a->b as a fraction of the segment (outside 0..1 when
    behind a / beyond b); ``off_km`` = distance from ``p`` to the SEGMENT; ``along_km`` = how far outside the
    segment the projection falls (0 when inside)."""
    bx, by = _xy(b, a)
    px, py = _xy(p, a)
    L2 = bx * bx + by * by
    L = math.sqrt(L2)
    if L2 < 1e-9:
        return 0.5, math.hypot(px, py), 0.0
    t = (px * bx + py * by) / L2
    tc = min(1.0, max(0.0, t))
    off = math.hypot(px - tc * bx, py - tc * by)
    along = 0.0 if 0.0 <= t <= 1.0 else (-t * L if t < 0 else (t - 1.0) * L)
    return t, off, along


def _lerp(a, b, t) -> Tuple[float, float]:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def plan_repins(pins: List[Optional[Tuple[float, float]]], area: List[bool], verified: List[bool]
                ) -> Dict[int, Tuple[Tuple[float, float], float, str]]:
    """{index: (new pin, km, 'behind' | 'off the segment')} for the area stops (0-based) that need re-pinning.
    A stop needs it when it is an unverified area stop with a pin, not first / last, whose neighbours (the nearest
    stops on each side that are not themselves being re-pinned) have pins, and whose projection onto the
    neighbour segment falls outside it or lies more than 10 km from it. A run of consecutive such stops is
    spread evenly along the segment (its share of the route)."""
    n = len(pins)
    bad: Dict[int, Tuple[float, str]] = {}
    for i in range(1, n - 1):
        if not area[i] or verified[i] or pins[i] is None or pins[i - 1] is None or pins[i + 1] is None:
            continue
        t, off, along = segment_position(pins[i], pins[i - 1], pins[i + 1])
        if t < 0.0 or t > 1.0:
            bad[i] = (along, "behind")
        elif off > MAX_OFF_SEGMENT_KM:
            bad[i] = (off, "off the segment")
    out: Dict[int, Tuple[Tuple[float, float], float, str]] = {}
    i = 0
    while i < n:
        if i not in bad:
            i += 1
            continue
        j = i
        while j + 1 in bad:
            j += 1
        a, b = i - 1, j + 1
        if pins[a] is not None and pins[b] is not None:
            run = j - i + 1
            for q in range(i, j + 1):
                share = (q - i + 1) / (run + 1)
                out[q] = (_lerp(pins[a], pins[b], share), round(bad[q][0], 1), bad[q][1])
        i = j + 1
    return out


def repin_area_stops(poi_list: List[Dict], verified: Optional[Set[int]] = None,
                     log: Optional[Callable] = None) -> int:
    """Item 2 on the poi list (the pins the text is built from). ``verified`` = 0-based indices whose pin is
    verified (Wikidata / geocoded / user-given); those are never moved. Moved stops are flagged
    ``coordinates_approximate``. Returns the number moved. Never raises."""
    emit = _emit(log)
    try:
        if not rc.active() or len(poi_list or []) < 3:
            return 0
        import pin_snap
        verified = set(verified or ())
        pins, area, ver = [], [], []
        for i, p in enumerate(poi_list):
            pins.append(pin_snap._poi_coord(p))
            area.append(is_area_stop(str(p.get("name", "")),
                                     str(p.get("type_specialty") or p.get("type") or "")))
            ver.append(i in verified or bool(p.get("wikidata_lat") and p.get("wikidata_lng"))
                       or pin_snap._is_user_pin(p))
        plan = plan_repins(pins, area, ver)
        _PIN_INFO["verified"] = {i + 1 for i, v in enumerate(ver) if v}     # the text pass honours the same set
        for i, (pt, km, why) in sorted(plan.items()):
            p = poi_list[i]
            p["coordinates"] = f"{pt[0]:.6f}, {pt[1]:.6f}"
            if "latitude" in p or "longitude" in p:
                p["latitude"], p["longitude"] = pt[0], pt[1]
            p["coordinates_approximate"] = True
            emit(f"  {TAG} route area stop={i + 1} re-pinned between neighbours (was {km:.1f} km "
                 f"{'behind' if why == 'behind' else 'off the segment'})")
        return len(plan)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} area-stop re-pin skipped (non-fatal): {err}")
        return 0


_COORD_LINE = re.compile(r"(?mi)^(Coordinates:\s*)(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)[ \t]*$")
_TYPE_LINE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")


# The generator tells the delivery text pass which stops carry a VERIFIED pin (1-based numbers). The text alone
# cannot say, so without that information the text pass moves nothing (job-scoped, like the rest of the state).
_PIN_INFO = rc._ScopedDict(dict)


def set_verified_stops(numbers: Optional[Sequence[int]]) -> None:
    """1-based numbers of the stops whose pin is verified; ``None`` forgets the information."""
    if numbers is None:
        _PIN_INFO.pop("verified", None)
    else:
        _PIN_INFO["verified"] = set(int(n) for n in numbers)


def repin_area_stops_in_text(tour_text: str, verified: Optional[Set[int]] = None,
                             log: Optional[Callable] = None) -> str:
    """Item 2 on the delivered text's Coordinates lines (a safety net after the poi-level pass, and the replay's
    entry point). ``verified`` = 1-based stop numbers whose pin is verified; when omitted the set the generator
    stored (``set_verified_stops``) is used, and with neither nothing is moved."""
    emit = _emit(log)
    try:
        if verified is None:
            verified = _PIN_INFO.get("verified")
        if verified is None or not rc.active() or not tour_text:
            return tour_text
        blocks = rc._stop_blocks(tour_text)
        if len(blocks) < 3:
            return tour_text
        pins, area, ver, spans = [], [], [], []
        for s, e, num, title in blocks:
            blk = tour_text[s:e]
            m = _COORD_LINE.search(blk)
            pins.append((float(m.group(2)), float(m.group(3))) if m else None)
            spans.append((s + m.start(), s + m.end(), m.group(1)) if m else None)
            tm = _TYPE_LINE.search(blk)
            area.append(is_area_stop(title, tm.group(1) if tm else ""))
            ver.append(num in (verified or ()))
        plan = plan_repins(pins, area, ver)
        if not plan:
            return tour_text
        out, pos = [], 0
        for i, (pt, km, why) in sorted(plan.items()):
            a, b, head = spans[i]
            out.append(tour_text[pos:a])
            out.append(f"{head}{pt[0]:.6f}, {pt[1]:.6f}")
            pos = b
            emit(f"  {TAG} route area stop={blocks[i][2]} re-pinned between neighbours (was {km:.1f} km "
                 f"{'behind' if why == 'behind' else 'off the segment'})")
        out.append(tour_text[pos:])
        return "".join(out)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} area-stop re-pin (text) skipped (non-fatal): {err}")
        return tour_text


# ── 4. an Orientation that contradicts the stop order ─────────────────────────────────────────────────────
_AT_FOOT = re.compile(
    r"(?i)\b(?:at|to|near|reach(?:ed|ing)?|arriv\w+\s+at|stand(?:ing)?\s+at)?\s*(?:the\s+)?"
    r"(?:foot|base|bottom|entrance|gates?|front\s+door|doorstep)\s+of\s+(?:the\s+)?([^,.;:—–\-]{2,60})")
_WENT_UP = re.compile(r"(?i)\b(?:ascen\w+|summit|climb\w*|cable\s*car|peak|walk\s+on|at\s+the\s+top|uphill|inside|"
                      r"interior|enter\w*|up\s+the)\b")
_LINE_ORIENT = re.compile(r"(?mi)^(Orientation:\s*)(.*)$")
_LINE_DIRS = re.compile(r"(?mi)^Directions:\s*(.*)$")


def _name_tokens(text: str) -> Set[str]:
    toks = {t for t in rc._content_tokens(text)}
    sig = toks - rc._GENERIC_NOUN
    return sig or toks


def drop_contradicting_orientation(tour_text: str, log: Optional[Callable] = None) -> str:
    """Item 4. An Orientation sentence that puts the listener at the foot / base / entrance of a place an earlier
    stop already went up / into (an earlier title or Directions line says ascent / summit / Walk on and names the
    place) is dropped; an Orientation left empty is removed with its label."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            block = tour_text[s:e]
            m = _LINE_ORIENT.search(block)
            if not m or k == 0:
                pieces.append(block)
                continue
            prev = []
            for (ps, pe, _pn, ptitle) in blocks[:k]:
                dm = _LINE_DIRS.search(tour_text[ps:pe])
                prev.append((ptitle, dm.group(1) if dm else ""))
            went_up = any(_WENT_UP.search(t + " " + d) for t, d in prev)
            if not went_up:
                pieces.append(block)
                continue
            keep, dropped = [], []
            for x in rc.split_sentences(m.group(2)):
                fm = _AT_FOOT.search(x)
                named = False
                if fm:
                    want = _name_tokens(fm.group(1))
                    named = any(want & (rc._content_tokens(t + " " + d)) for t, d in prev)
                (dropped if (fm and named) else keep).append(x)
            if not dropped:
                pieces.append(block)
                continue
            for x in dropped:
                emit(f"  {TAG} Stop {num} '{title[:40]}': Orientation puts the listener at the foot / base of a place "
                     f"earlier stops already ascended -> dropped: \"{x[:100]}\"")
            if keep:
                new = block[:m.start()] + m.group(1) + " ".join(keep) + block[m.end():]
            else:
                new = block[:m.start()] + block[m.end():].lstrip("\n")
                new = re.sub(r"\n{3,}", "\n\n", new)
            pieces.append(new)
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} orientation guard skipped (non-fatal): {err}")
        return tour_text


# ── 5. a sentence already delivered in an earlier stop ────────────────────────────────────────────────────
REPEAT_OVERLAP = 0.85


def _tok(sentence: str) -> Set[str]:
    return set(rc._words(sentence))


def is_repeat(sentence: str, delivered: Sequence[Set[str]], thr: float = REPEAT_OVERLAP) -> bool:
    """Identical, or >= ``thr`` of the smaller word set shared with a delivered sentence (>= 5 words each)."""
    t = _tok(sentence)
    if len(t) < 5:
        return False
    for d in delivered:
        if len(d) >= 5 and len(t & d) / min(len(t), len(d)) >= thr:
            return True
    return False


def drop_repeated_sentences(tour_text: str, log: Optional[Callable] = None) -> str:
    """Item 5. A body sentence (or a near-duplicate) already delivered in an earlier stop is dropped from the later
    one, unless that would leave the later stop with no content sentence (then it stays; 905's floor decides)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        delivered: List[Set[str]] = []
        pieces, pos = [], 0
        for k, (s, e, num, title) in enumerate(blocks):
            pieces.append(tour_text[pos:s])
            pos = e
            block = tour_text[s:e]
            last = k == len(blocks) - 1
            own = _content_sents(block.split("\n"), last)
            rep = [x for x in own if is_repeat(x, delivered)]
            if rep and len(rep) < len(own):
                block, dropped = _filter_body(block, last, lambda x, _r=rep: x not in _r)
                for x in dropped:
                    emit(f"  {TAG} Stop {num} '{title[:40]}': sentence already delivered in an earlier stop "
                         f"-> dropped: \"{x[:100]}\"")
                own = _content_sents(block.split("\n"), last)
            elif rep:
                emit(f"  {TAG} Stop {num} '{title[:40]}': every body sentence repeats an earlier stop; left as is")
            delivered += [_tok(x) for x in own]
            pieces.append(block)
        pieces.append(tour_text[pos:])
        return "".join(pieces)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} repeat guard skipped (non-fatal): {err}")
        return tour_text


# ── 6. negative opening tone ──────────────────────────────────────────────────────────────────────────────
_NEGATIVE = re.compile(r"(?i)\b(?:pollut\w*|trash|litter\w*|garbage|crimes?|criminal\w*|theft|thieves|robber\w*|"
                       r"diseases?|epidemics?|outbreaks?|disasters?)\b")
_HISTORIC = re.compile(r"(?i)\b(?:war|wars|battle|siege|massacre|invasion|bombing|genocide|memorial|uprising|"
                       r"revolution|occupation|colonial|century|centuries|ancient|historic\w*)\b")
_LEISURE = ("walking", "driving", "biking", "cycling", "bicycle", "family", "scenic", "road", "hiking", "stroll")
_CATEGORY = re.compile(r"(?mi)^Tour-Category:\s*(\S.*?)\s*$")


def is_leisure(tour_text: str) -> bool:
    m = _CATEGORY.search(tour_text or "")
    cat = (m.group(1) if m else "").lower()
    return any(w in cat for w in _LEISURE)


def is_negative_tone(sentence: str) -> bool:
    return bool(_NEGATIVE.search(sentence or ""))


_SIGNATURE = rc._ScopedDict(dict)       # {stop title: signature-story text}, stashed by the generator (job-scoped)


def set_signature_stories(stories: Optional[Dict[str, object]]) -> None:
    """The stops' signature stories ({title: story dicts / strings}); flattened to text. Replaces the stash."""
    _SIGNATURE.clear()
    for k, v in (stories or {}).items():
        parts: List[str] = []
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            if isinstance(item, dict):
                parts += [str(x) for x in item.values() if isinstance(x, (str, int, float))]
            elif item:
                parts.append(str(item))
        _SIGNATURE[str(k)] = " ".join(parts)


def tone_first_stop(tour_text: str, signature_by_title: Optional[Dict[str, str]] = None,
                    log: Optional[Callable] = None) -> str:
    """Item 6. In the FIRST stop's body, a pollution / trash / crime / disease / disaster sentence that is not part of
    the stop's story (its signature story, or a historic event) is dropped on a leisure tour (walking / driving /
    biking / family), and moved after the stop's first positive sentence elsewhere."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if not blocks:
            return tour_text
        s, e, num, title = blocks[0]
        block = tour_text[s:e]
        last = len(blocks) == 1
        sig = ""
        for k, v in (signature_by_title or dict(_SIGNATURE)).items():
            if rc.fold(k) == rc.fold(title):
                sig = str(v or "")
        sig_tokens = rc._content_tokens(sig)

        def part_of_story(x: str) -> bool:
            return bool(_HISTORIC.search(x) or re.search(r"\b1[0-9]{3}\b|\b20[0-9]{2}\b", x)
                        or (sig_tokens and len(rc._content_tokens(x) & sig_tokens) >= 3))
        neg = [x for x in _content_sents(block.split("\n"), last) if is_negative_tone(x) and not part_of_story(x)]
        if not neg:
            return tour_text
        leisure = is_leisure(tour_text)
        if leisure:
            if len(neg) >= len(_content_sents(block.split("\n"), last)):
                return tour_text
            new, dropped = _filter_body(block, last, lambda x: x not in neg)
            for x in dropped:
                emit(f"  {TAG} Stop {num} '{title[:40]}': negative sentence in the first stop of a leisure tour "
                     f"-> dropped: \"{x[:100]}\"")
        else:
            lines = block.split("\n")
            new = block
            for i in _body_line_idx(lines, last):
                sents = rc.split_sentences(lines[i])
                if sents and sents[0] in neg:
                    pos_i = next((q for q, x in enumerate(sents) if x not in neg), None)
                    if pos_i is None:
                        continue
                    moved = sents[0]
                    sents = sents[1:pos_i + 1] + [moved] + sents[pos_i + 1:]
                    lines[i] = " ".join(sents)
                    emit(f"  {TAG} Stop {num} '{title[:40]}': negative opening moved after the first positive "
                         f"sentence: \"{moved[:100]}\"")
                    break
            new = "\n".join(lines)
        if new == block:
            return tour_text
        return tour_text[:s] + new + tour_text[e:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} tone guard skipped (non-fatal): {err}")
        return tour_text


# ── 7. template closing filler ────────────────────────────────────────────────────────────────────────────
_FILLER_CLOSING = re.compile(
    r"(?i)^(?:across\s+these\s+stops\b|taken\s+together,?\s+the\s+stops\s+add\s+up\b|"
    r"together,?\s+these\s+stops\s+(?:add\s+up|form|tell)\b)")


def drop_template_closing(tour_text: str, log: Optional[Callable] = None) -> str:
    """Item 7. "Across these stops, one thread runs through: ... Taken together, the stops add up to more than any one
    of them seen alone." is template filler; only the "That's N stops in all." line and the restaurant offer stay."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if not blocks:
            return tour_text
        s, e, num, title = blocks[-1]
        lines = tour_text[s:e].split("\n")
        changed = False
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or rc._KEYED.match(ln):
                continue
            sents = rc.split_sentences(ln)
            keep = [x for x in sents if not _FILLER_CLOSING.match(x)]
            if len(keep) != len(sents):
                for x in sents:
                    if x not in keep:
                        emit(f"  {TAG} closing: template filler dropped: \"{x[:100]}\"")
                lines[i] = " ".join(keep) if keep else None
                changed = True
        if not changed:
            return tour_text
        new = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if not new.endswith("\n") and tour_text[s:e].endswith("\n"):
            new += "\n"
        return tour_text[:s] + new + tour_text[e:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} closing guard skipped (non-fatal): {err}")
        return tour_text


# ── the pass ──────────────────────────────────────────────────────────────────────────────────────────────
def content_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                 log: Optional[Callable] = None) -> str:
    """Items 1 (claims), 4, 5, 6, 7 on a route or a single-place tour; anything else is returned untouched."""
    if not tour_text or not in_scope(tour_text):
        return tour_text
    t = drop_unsupported_claims(tour_text, evidence_by_title, log)
    t = drop_contradicting_orientation(t, log)
    try:   # [LOCAL-906C] no two stops share a filler body (before the repeated-sentence guard, so the 906 "left as is"
        import leftovers_906c as _c       # case never leaves an identical body twice); "You see the X here is" repaired
        t = _c.repair_you_see_here(t, log)
        t = _c.distinct_filler_bodies(t, evidence_by_title, log)
        t = _c.repair_pronoun_opener(t, log)          # [LOCAL-906E]
    except Exception as _e906c:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906C] filler guard skipped (non-fatal): {_e906c}")
    t = drop_repeated_sentences(t, log)
    t = rc.drop_within_stop_duplicates(t, log, evidence_by_title)   # [LOCAL-906B] the same fact twice in one stop
    t = tone_first_stop(t, None, log)
    t = drop_template_closing(t, log)
    return t
