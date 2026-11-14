"""[LOCAL-906U] Delivery guards from the LEAD Mac proofs of 906T ("<Origin> to <Mountain>" drive, 551, 552). Pure, free, never raises.
Generic names only (D769).

2.  A-to-B Orientation   -- the Orientation of an A-to-B tour starts at the origin: "Leave <Destination> ..." directions (and the route
                            steps that follow them), the "Each stop on this journey ..." template and a second route sentence go.
3.  headline / operator  -- a Title-Case sentence with "&", or ending in Tour/Tours/Trip/Package, or starting with Discover/Explore/Book is a
                            page headline; "recommended routes" / "travel tips" / "plan your visit" is operator copy.
4.  refill bar           -- ``bar_pass``: a sentence that is verbatim evidence (so it was added after generation) meets the 906K refill bar
                            wherever it stands (see ``refill_quality_906k.refill_reject``).
5.  one disclosure       -- one "We could not confirm verified historical details ..." per stop.
6.  dangling start       -- "Among its notable features ..." as the first sentence: "its" is the stop title.
7.  two distances        -- two "<n> km <bearing> of <City>" in one stop: the encyclopedia's value, else the first, is kept.
8.  sensory detail       -- a colour / material the stop's evidence does not carry is dropped; "From the vehicle" is not used on a stop
                            whose arriving Directions say "Walk".
9.  "lies from" fragment -- "<X> lies from the tram's summit station, ..." (the measure was removed).
10. unhedged record      -- "<Name>, the tallest <X> in <Country>" that the stop's evidence does not carry is hedged ("one of the tallest").
11. hours copy           -- "<X> is open all year round." is practical copy and goes.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

import leftovers_906c as c
import route_content_896 as rc
import splice_copy_906r as sp

TAG = "[LOCAL-906U]"


def _emit(log: Optional[Callable]) -> Callable:
    return log if callable(log) else (lambda *_a, **_k: None)


_SMALL = frozenset("a an and as at but by for from in into of on or the to with via de la le du von van".split())


# ══ 3. headline / operator copy ═══════════════════════════════════════════════════════════════════════════
def title_case_ratio(x: str) -> float:
    words = [w for w in re.findall(r"[^\W\d_][\w'’\-]*", x or "", re.UNICODE) if w.lower() not in _SMALL]
    if not words:
        return 0.0
    return sum(1 for w in words if w[:1].isupper()) / len(words)


_HEAD_START = re.compile(r"(?i)^(?:discover|explore|book)\b")
_HEAD_END = re.compile(r"(?i)\b(?:tours?|trips?|packages?)\s*[.!?]?\s*$")
_OPERATOR_COPY = re.compile(r"(?i)\b(?:recommended\s+(?:routes?|itineraries|tours?)|(?:expert|insider|useful|handy|helpful)\s+(?:travel\s+)?tips|"
                            r"travel\s+tips|help\s+(?:you\s+)?plan\s+your\s+(?:visit|trip|journey)|plan\s+your\s+(?:visit|trip))\b")


def headline_reason(x: str) -> Optional[str]:
    """Why ``x`` is a page headline / operator copy, else None."""
    s = (x or "").strip()
    if not s:
        return None
    if _OPERATOR_COPY.search(s):
        return "operator copy (routes / travel tips / plan your visit)"
    n = len(re.findall(r"[^\W\d_][\w'’\-]*", s, re.UNICODE))
    if n >= 2 and title_case_ratio(s) >= 0.6:
        if "&" in s:
            return "page headline (Title Case with '&')"
        if _HEAD_END.search(s):
            return "page headline (Title Case ending in Tour / Trip / Package)"
        if _HEAD_START.match(s):
            return "page headline (Title Case starting with Discover / Explore / Book)"
    return None


# ══ 11. hours / season copy ═══════════════════════════════════════════════════════════════════════════════
_HOURS = re.compile(
    r"(?i)\b(?:open|opens|opened|closed|closes|operates|operating|available|runs)\b[^.!?]{0,40}?\b(?:all\s+year(?:\s+round)?|year[-\s]round|every\s+day|"
    r"daily|seven\s+days(?:\s+a\s+week)?|7\s+days|(?:from|between|until|till|at)\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m|p\.?m|h)?\b|"
    r"\d{1,2}(?::\d{2})?\s*(?:a\.?m|p\.?m)\b|(?:in|during)\s+(?:the\s+)?(?:summer|winter|spring|autumn|fall|dry|rainy|high|peak|low|off)\s+season|"
    r"(?:on\s+)?(?:weekdays|weekends|mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?))\b"
    r"|\b(?:opening|business|visiting|operating)\s+(?:hours|times)\b|\bhours\s+of\s+operation\b|\bseasonal\s+(?:hours|opening)\b")


def hours_reason(x: str) -> Optional[str]:
    return "opening-hours / season copy" if _HOURS.search(x or "") else None


# ══ 9. "lies from" with no measure ════════════════════════════════════════════════════════════════════════
_LIES_FROM = re.compile(r"(?i)\b(?:lies|lie|lay|stands?|sits?|rests?|is\s+(?:located|situated|found|positioned)|are\s+(?:located|situated))\s+from\b")


def lies_from_fragment(x: str) -> bool:
    """A "lies / stands / is located from <X>" sentence: the measure that stood before "from" is gone."""
    m = _LIES_FROM.search(x or "")
    if not m:
        return False
    return True


# ══ 8. sensory colour / material and "From the vehicle" ═══════════════════════════════════════════════════
_COLOURS = {
    "golden": "gold", "gold": "gold", "gilded": "gold", "gilt": "gold", "white": "white", "whitewashed": "white", "red": "red", "crimson": "red",
    "vermilion": "red", "black": "black", "silver": "silver", "silvery": "silver", "bronze": "bronze", "grey": "grey", "gray": "grey",
    "yellow": "yellow", "orange": "orange", "pink": "pink", "purple": "purple", "ochre": "ochre", "ocher": "ochre", "amber": "amber",
    "marble": "marble", "granite": "granite", "brick": "brick", "bricks": "brick", "wooden": "wood", "stone": "stone", "concrete": "concrete",
    "jade": "jade", "copper": "copper", "lacquered": "lacquer", "terracotta": "terracotta",
}
_SENSORY = re.compile(r"(?i)\b(?:you\s+(?:can\s+)?(?:see|notice|spot|glimpse)|catch(?:es|ing)?|gleam\w*|glow\w*|shimmer\w*|glint\w*|surfaces?|hues?|"
                      r"tints?|shine[sd]?|shining|gleaming|glisten\w*|reflect\w*|sunlight|sunlit|stand(?:s|ing)?\s+out)\b")


def colour_words(x: str) -> List[str]:
    return sorted({_COLOURS[w] for w in re.findall(r"[a-z]+", (x or "").lower()) if w in _COLOURS})


def colour_reason(x: str, evidence: str) -> Optional[str]:
    """A sensory sentence naming a colour / material the stop's evidence does not carry (or contradicts)."""
    if not _SENSORY.search(x or ""):
        return None
    cols = colour_words(x)
    if not cols:
        return None
    ev_cols = set(colour_words(evidence or ""))
    missing = [w for w in cols if w not in ev_cols]
    if not missing:
        return None
    other = sorted(ev_cols - set(cols))
    if other and any(k in ev_cols for k in ("white", "red", "black", "gold", "silver", "grey", "yellow")):
        return f"sensory colour '{missing[0]}' contradicts the evidence ({', '.join(other[:3])})"
    return f"sensory colour / material '{missing[0]}' is not in the stop's evidence"


_VEHICLE = re.compile(r"(?i)^(\s*)from\s+the\s+(?:vehicle|car|window|bus|scooter|motorbike)\s*,\s*")
_LOWER_OK = frozenset("the a an you your this these it we there here as with when".split())


def fix_vehicle(x: str) -> Optional[str]:
    """"From the vehicle, you see ..." -> "From here, you see ..." (a stop reached on foot)."""
    m = _VEHICLE.match(x or "")
    if not m:
        return None
    rest = x[m.end():]
    first = (re.match(r"[^\W\d_]+", rest) or [None])[0] if rest else None
    if first and first.lower() in _LOWER_OK and rest[:1].isupper():
        rest = rest[:1].lower() + rest[1:]
    return f"{m.group(1)}From here, {rest}"


def _arrived_on_foot(directions_prev: str) -> bool:
    return bool(re.search(r"(?i)\b(?:walk|walking|stroll|on foot|hike|hiking)\b", directions_prev or ""))


# ══ 6. dangling start ═════════════════════════════════════════════════════════════════════════════════════
_ITS_OPEN = re.compile(r"^(?P<w>Among|Within|Inside|Beyond|Throughout)\s+its\b")


def _short_title(title: str) -> str:
    t = re.sub(r"<[^>]*>", "", title or "").strip()
    t = re.split(r"\s+[–—-]\s+", t)[0].strip()
    return t


def fix_dangling_its(x: str, title: str) -> Optional[str]:
    m = _ITS_OPEN.match((x or "").strip())
    t = _short_title(title)
    if not m or not t:
        return None
    poss = t + ("'" if t.endswith("s") else "'s")
    return f"{m.group('w')} {poss}" + x.strip()[m.end():]


# ══ 7. two distances ══════════════════════════════════════════════════════════════════════════════════════
_DIST = re.compile(r"(?i)\b(?P<n>\d+(?:[.,]\d+)?)\s*-?\s*(?P<u>km|kilomet(?:er|re)s?|miles?|mi)\b\s+(?:(?:to\s+the\s+)?(?:north|south|east|west)(?:[\s-]*(?:north|south)?(?:east|west)?)?\w*)\s+"
                   r"(?:of|from)\s+(?P<ref>(?:[A-ZÀ-Ỹ][\w'’\-]*\s*){1,3})")
_CITY_NOISE = frozenset("city town the of district province".split())


def _ref_key(ref: str) -> str:
    return " ".join(w for w in rc.fold(ref).split() if w not in _CITY_NOISE)


def distances(x: str) -> List[Tuple[float, str]]:
    out = []
    for m in _DIST.finditer(x or ""):
        try:
            v = float(m.group("n").replace(",", "."))
        except ValueError:
            continue
        if m.group("u").lower().startswith(("mi",)):
            v *= 1.609
        out.append((round(v, 1), _ref_key(m.group("ref"))))
    return out


# ══ 5. one disclosure per stop ═════════════════════════════════════════════════════════════════════════════
def one_disclosure(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        out, pos = [], 0
        for s, e, num, title in rc._stop_blocks(tour_text):
            out.append(tour_text[pos:s])
            pos = e
            block = tour_text[s:e]
            lines = block.split("\n")
            seen = False
            changed = False
            for i, ln in enumerate(lines):
                if i == 0 or not ln.strip() or rc._KEYED.match(ln):
                    continue
                sents = rc.split_sentences(ln)
                if not any(c._is_disclosure(x) for x in sents):
                    continue
                keep = []
                for x in sents:
                    if c._is_disclosure(x):
                        if seen:
                            emit(f'  {TAG} Stop {num}: second disclosure sentence dropped: "{x[:70]}"')
                            changed = True
                            continue
                        seen = True
                    keep.append(x)
                lines[i] = " ".join(keep) if keep else None
            if changed:
                block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
                if tour_text[s:e].endswith("\n") and not block.endswith("\n"):
                    block += "\n"
            out.append(block)
        out.append(tour_text[pos:])
        return "".join(out)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} disclosure guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. the A-to-B Orientation ═════════════════════════════════════════════════════════════════════════════
_AB_HEAD = re.compile(r"(?is)^\s*(?:Step-by-step\s+audio[\s-]*guided\s+tour\s+from|.{0,40}?\btour\s+from)\s+(?P<a>.+?)\s+to\s+(?P<b>.+?)(?:\s+in\s+|\s+[-–—]\s+|\.|,|\n)")
_AB_TITLE = re.compile(r"(?m)^\s*(?P<a>[^\n]{2,80}?)\s+to\s+(?P<b>[^\n]{2,80}?)\s+[-–—]\s+(?:driving|walking|cycling|biking|transit)\s+tour\b")
_TEMPLATE = re.compile(r"(?i)^each\s+stop\s+on\s+this\s+(?:journey|route|tour|drive|walk)\s+(?:reveals|shows|illustrates|explores|highlights|tells)\b")
_ROUTE_SENT = re.compile(r"(?i)^the\s+route\s+starts\s+(?:at|from|in)\b")
_LEAVE = re.compile(r"(?i)^(?:from\s+here,?\s+)?(?:leave|leaving|depart(?:ing)?\s+from|set\s+out\s+from|head\s+out\s+from|exit)\b")
_STEP = re.compile(r"(?i)^(?:continue|keep\s+(?:going|driving|walking)|turn|take|follow|head|drive|go|proceed|pass|cross|along\s+the\s+way|on\s+the\s+way)\b")
_GENERIC_PLACE = frozenset("mountain mount hill peak temple pagoda lake river beach island park the of city town".split())


def ab_endpoints(tour_text: str, origin: str = "", destination: str = "") -> Tuple[str, str]:
    if origin and destination:
        return origin, destination
    head = (tour_text or "")[:600]
    m = _AB_HEAD.match(head) or _AB_TITLE.search(head)
    if m:
        return (origin or m.group("a").strip()), (destination or m.group("b").strip())
    return origin, destination


def _core(name: str) -> List[str]:
    toks = [w for w in rc.fold(name).split() if w]
    core = [w for w in toks if w not in _GENERIC_PLACE]
    return core or toks


def names_place(x: str, place: str) -> bool:
    core = _core(place)
    if not core:
        return False
    words = set(rc.fold(x).split())
    return all(w in words for w in core)


def fix_ab_orientation(tour_text: str, origin: str = "", destination: str = "", log: Optional[Callable] = None) -> str:
    """The Orientation of Stop 1 of an A-to-B tour starts at the origin: no "Leave <Destination>" directions, no "Each stop on this
    journey ..." template, one route sentence ("The route starts at <Origin>; from there, head to <Stop 1>.")."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        a, b = ab_endpoints(tour_text, origin, destination)
        if not a or not b:
            return tour_text
        infos = c._stops_info(tour_text)
        if not infos:
            return tour_text
        first = infos[0]
        line_no = next((i for i, ln in enumerate(first["lines"]) if i > 0 and re.match(r"(?i)^\s*orientation\s*:", ln)), None)
        if line_no is None:
            return tour_text
        m = re.match(r"(?i)^(\s*Orientation\s*:\s*)(.*)$", first["lines"][line_no])
        prefix, text = m.group(1), m.group(2)
        sents = rc.split_sentences(text)
        keep: List[str] = []
        dropping_steps = False
        route_kept = False
        changed = False
        first_title = _short_title(first["title"])
        for x in sents:
            why = None
            if _TEMPLATE.match(x):
                why = "template opening ('Each stop on this journey ...')"
            elif _LEAVE.match(x.strip()) and names_place(x, b) and not names_place(x, a):
                why = f"directions that leave the destination '{b[:30]}' on an A-to-B tour"
                dropping_steps = True
            elif dropping_steps and (_STEP.match(x.strip()) or re.match(r"(?i)^along\s+the\s+way\b", x.strip())):
                why = "route step that follows directions from the destination"
            elif names_place(x, b) and re.search(r"(?i)\b(?:leave|leaving|depart)\b", x) and re.search(r"(?i)\b(?:head|drive|continue|turn|kilomet|km)\b", x):
                why = f"directions that leave the destination '{b[:30]}' on an A-to-B tour"
                dropping_steps = True
            elif _ROUTE_SENT.match(x.strip()):
                if route_kept:
                    why = "second route sentence"
                else:
                    route_kept = True
                    if not names_place(x, a):
                        x = f"The route starts at {a}; from there, head to {first_title}."
                        changed = True
            if why:
                emit(f'  {TAG} Stop 1 Orientation: {why} dropped: "{x[:90]}"')
                changed = True
                continue
            if not _STEP.match(x.strip()):
                dropping_steps = False
            keep.append(x)
        if not changed:
            return tour_text
        if not route_kept:
            keep.append(f"The route starts at {a}; from there, head to {first_title}.")
        lines = list(first["lines"])
        lines[line_no] = prefix + " ".join(keep)
        return tour_text[:first["s"]] + "\n".join(lines) + tour_text[first["e"]:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} A-to-B orientation guard skipped (non-fatal): {err}")
        return tour_text


# ══ the sentence pass ═════════════════════════════════════════════════════════════════════════════════════
def _directions_of(info: Dict) -> str:
    for ln in info["lines"]:
        if re.match(r"(?i)^\s*directions\s*:", ln):
            return ln
    return ""


def sentence_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        infos = c._stops_info(tour_text)
        prev_dir = {infos[k]["num"]: _directions_of(infos[k - 1]) if k else "" for k in range(len(infos))}
        all_ev = " ".join(v for v in ev_map.values() if v)

        def fn(st: Dict, tg):
            edits: Dict = {}
            ev = rc._ev_for(ev_map, st["title"]) or ""
            on_foot = _arrived_on_foot(prev_dir.get(st["num"], ""))
            ordered = [(i, j, x) for i in sorted(tg) for j, x in enumerate(tg[i][1])]
            # 7. two distances in one body: keep the encyclopedia's, else the first
            seen: Dict[str, Tuple[float, int, int, str]] = {}
            drop_dist = set()
            for i, j, x in ordered:
                if tg[i][0]:
                    continue                                          # the Orientation line
                for v, key in distances(x):
                    if not key:
                        continue
                    if key in seen and abs(seen[key][0] - v) > 0.5:
                        pv, pi, pj, px = seen[key]
                        import refill_quality_906k as k
                        keep_new = k.source_of(x, ev, st["title"]) == "article" and k.source_of(px, ev, st["title"]) != "article"
                        loser = (pi, pj, px, pv) if keep_new else (i, j, x, v)
                        drop_dist.add((loser[0], loser[1]))
                        who = "the encyclopedia's" if (keep_new or k.source_of(px, ev, st["title"]) == "article") else "the first"
                        emit(f'  {TAG} Stop {st["num"]}: two distances from "{key}" ({pv:g} and {v:g}): '
                             f'{who} kept, dropped: "{loser[2][:80]}"')
                        if keep_new:
                            seen[key] = (v, i, j, x)
                    elif key not in seen:
                        seen[key] = (v, i, j, x)
            first_body = True
            for i, j, x in ordered:
                if (i, j) in drop_dist:
                    edits[(i, j)] = []
                    continue
                prefix = tg[i][0]
                new, why = x, None
                if not prefix and first_body and j == 0:
                    fixed = fix_dangling_its(x, st["title"])
                    if fixed:
                        emit(f'  {TAG} Stop {st["num"]}: "its" with no antecedent at the start of the stop -> "{fixed[:70]}"')
                        new = fixed
                if not prefix:
                    first_body = False
                why = headline_reason(new) or hours_reason(new)
                if not why and lies_from_fragment(new):
                    why = "fragment ('lies from' with no measure)"
                if not why:
                    why = colour_reason(new, ev)
                if why:
                    emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                    edits[(i, j)] = []
                    continue
                if on_foot:
                    fv = fix_vehicle(new)
                    if fv:
                        emit(f'  {TAG} Stop {st["num"]}: "From the vehicle" on a stop reached on foot -> "From here": "{x[:60]}"')
                        new = fv
                rec = _hedge_record(new, ev, st["title"])
                if rec and rec != new:
                    emit(f'  {TAG} Stop {st["num"]}: record the stop\'s evidence does not carry -> hedged: "{x[:80]}" -> "{rec[:80]}"')
                    new = rec
                if new != x:
                    edits[(i, j)] = [new]
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} sentence pass skipped (non-fatal): {err}")
        return tour_text


# ══ 10. the apposition record ═════════════════════════════════════════════════════════════════════════════
_APPOS = re.compile(r",\s+the\s+(?:very\s+)?(?:tallest|largest|biggest|longest|highest|oldest|deepest|widest|greatest)\s+(?:[\w'’\-]+\s+){0,3}?in\s+"
                    r"(?:all\s+(?:of\s+)?)?[A-ZÀ-Ỹ][\w'’\-]*")


def _carried(x: str, evidence: str) -> bool:
    """The evidence states the same record: a sentence with the superlative, the head noun and the scope of the apposition."""
    m = _APPOS.search(x or "")
    if not m:
        return True
    seg = re.findall(r"[a-z]+", rc.fold(m.group(0)))
    sup = next((w for w in seg if w in {"tallest", "largest", "biggest", "longest", "highest", "oldest", "deepest", "widest", "greatest"}), "")
    scope = seg[-1] if seg else ""
    head = ""
    if "in" in seg:
        pre = seg[:len(seg) - 1 - seg[::-1].index("in")]
        head = (pre[-1] if pre else "")
    head = head[:-1] if len(head) > 4 and head.endswith("s") else head
    for es in rc.split_sentences(evidence or ""):
        words = re.findall(r"[a-z]+", rc.fold(es))
        stems = {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words}
        if sup in words and scope in words and (not head or head in stems) and not re.search(r"(?i)\bone\s+of\b|\bamong\b", es):
            return True
    return False


def _hedge_record(x: str, evidence: str, title: str) -> Optional[str]:
    """"<Name>, the tallest <X> in <Country>" that the stop's own evidence does not carry: "one of the tallest <X>s"."""
    if not _APPOS.search(x or "") or _carried(x, evidence):
        return None
    new = c._hedge_text(x)
    return new if new and new != x else None


# ══ 4. the refill bar, wherever the sentence stands ════════════════════════════════════════════════════════
def bar_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """A body sentence that IS an evidence sentence (verbatim: it was added after generation) meets the 906K refill bar here too."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import refill_quality_906k as k
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text
        evsents = {rc.fold(x) for v in ev_map.values() for x in rc.split_sentences(v or "")}

        def fn(st: Dict, tg):
            edits = {}
            blob = rc._ev_for(ev_map, st["title"]) or ""
            for i in sorted(tg):
                if tg[i][0]:
                    continue
                for j, x in enumerate(tg[i][1]):
                    if rc.fold(x) not in evsents:
                        continue
                    why = k.refill_reject(x, st["title"], None, k.source_of(x, blob, st["title"]), st.get("type", ""), bool(blob))
                    if why and why.startswith("not about this stop"):
                        emit(f'  {TAG} Stop {st["num"]}: a sentence added after generation fails the refill bar ({why}) -> dropped: "{x[:80]}"')
                        edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} refill bar skipped (non-fatal): {err}")
        return tour_text


# ══ the pass ══════════════════════════════════════════════════════════════════════════════════════════════
def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None,
             origin: str = "", destination: str = "") -> str:
    t = fix_ab_orientation(tour_text, origin, destination, log)
    t = bar_pass(t, evidence_by_title, log)
    t = sentence_pass(t, evidence_by_title, log)
    return one_disclosure(t, log)


def last_word(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """After every other delivery pass: the 906U guards; a stop they left without a supported sentence is refilled (906K bar) or takes the
    no-history disclosure body (906S), and the text is guarded once more."""
    emit = _emit(log)
    try:
        t = run_pass(tour_text, evidence_by_title, log)
        if t != tour_text:
            import language_dest_906s as s906
            t2 = s906.factless_stops(t, evidence_by_title, log)
            if t2 != t:
                t2 = run_pass(t2, evidence_by_title, log)
            t = t2
        return t
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} last word skipped (non-fatal): {err}")
        return tour_text
