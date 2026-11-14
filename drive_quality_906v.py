"""[LOCAL-906V] Drive-quality and repeat guards from the LEAD Mac proofs of 906U. Pure, free, never raises. Generic names only (D769).

1. sensory_only          a model-written sensory sentence ("Around you, the sound of rustling leaves ...") states no fact: it does not
                         count as the stop's factual sentence, so a stop that has only that gets the 906I refill or the D760 disclosure.
2. backtrack             on an A-to-B tour a stop whose detour (d(prev,X) + d(X,next) - d(prev,next)) is over 50 % of the direct leg AND
                         that lies behind the origin is rejected, or replaced from the pool.
3. directions            a Directions block describes the leg from THIS stop to the next: "From <earlier stop>, ..." becomes "From here,
                         ...", and "to reach your destination" names the next stop (or the sentence goes when it does not name it).
4. copy                  day-tour / neighbour-pointer / "unforgettable" / "Exploring ... invites ..." sentences go.
5. thread template       "Across these stops, one thread runs through ..." never stays in the body of a stop that is not the last.
6. same-value distance   see ``distance_duplicate`` (also used by the 906I refill: a fact already stated is not appended again).
7. one event, one telling sentences of one stop that restate the same event (legend / recognition / healing, or >= 60 % of their content
                         words) are one sentence: the most specific stays.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import leftovers_906c as c
import route_content_896 as rc
import splice_copy_906r as sp

TAG = "[LOCAL-906V]"
BACKTRACK_DETOUR = 0.50            # detour over this share of the direct leg ...
Pt = Tuple[float, float]


def _emit(log: Optional[Callable]) -> Callable:
    return log if callable(log) else (lambda *_a, **_k: None)


def _short(title: str) -> str:
    t = re.sub(r"<[^>]*>", "", title or "").strip()
    return re.split(r"\s+[–—-]\s+", t)[0].strip()


# ══ 1. a sensory-only sentence is not a fact ══════════════════════════════════════════════════════════════
_SENSE_CUE = re.compile(r"(?i)\b(?:sounds?|scents?|smell\w*|aromas?|fragrance|rustl\w*|birdcalls?|birdsong|breeze|wind|light|glow\w*|"
                        r"warm\w*|cool\w*|hum|hush|echo\w*|quiet|silence|whisper\w*|air|shadows?|sunlight|atmosphere|leaves|earth)\b")
_SENSE_OPEN = re.compile(r"(?i)^(?:around\s+you|as\s+you\s+(?:stand|step|walk|pause|look|arrive|breathe)|you\s+(?:can\s+)?(?:hear|feel|smell|sense|"
                         r"notice)|listen|feel|notice|breathe|take\s+a\s+(?:moment|breath)|close\s+your\s+eyes|let\s+(?:the|your)|stay\s+a\s+while|"
                         r"look\s+(?:out|around)|here,?\s+(?:you|the)\s+(?:can\s+)?(?:hear|feel|smell|sense))\b")


def sensory_only(x: str) -> bool:
    """A sentence of sounds / scents / light with no digit and no proper name: mood, not information."""
    s = (x or "").strip()
    if not s or re.search(r"\d", s):
        return False
    words = re.findall(r"[^\W\d_][\w'’\-]*", s, re.UNICODE)
    if any(w[:1].isupper() for w in words[1:] if w not in ("I",)):
        return False
    cues = {m.group(0).lower() for m in _SENSE_CUE.finditer(s)}
    return bool(cues) and (bool(_SENSE_OPEN.match(s)) or len(cues) >= 2)


# ══ 2. a backtracking stop on an A-to-B drive ═════════════════════════════════════════════════════════════
def backtrack_reason(prev: Optional[Pt], pt: Optional[Pt], nxt: Optional[Pt], a: Optional[Pt], b: Optional[Pt]) -> Optional[str]:
    """Why ``pt`` (between ``prev`` and ``nxt``) is a backtracking stop of the A-to-B drive, else None."""
    if not (prev and pt and nxt and a and b):
        return None
    import route_order_909 as r
    direct = r.km_between(prev, nxt)
    if direct <= 0:
        return None
    detour = r.km_between(prev, pt) + r.km_between(pt, nxt) - direct
    if detour <= BACKTRACK_DETOUR * direct:
        return None
    t = r.along(pt, a, b)
    if t >= 0.0:
        return None
    return (f"detour {detour:.0f} km is {detour / direct * 100:.0f}% of the {direct:.0f} km leg and the stop lies behind the origin "
            f"({t * 100:.0f}% of the way)")


def replace_backtracks(poi_list: List[Dict], a: Optional[Pt], b: Optional[Pt], pool: Optional[Sequence[Dict]], dest: str = "",
                       protect: Optional[Callable[[Dict], bool]] = None, log: Optional[Callable] = None) -> List[Dict]:
    """An A-to-B tour: a backtracking stop is replaced by the pool candidate that does not backtrack (smallest detour of A->B), else
    dropped while at least two stops remain, else kept."""
    emit = _emit(log)
    try:
        if not (a and b) or len(poi_list or []) < 2:
            return poi_list
        import route_order_909 as r
        have = {rc.fold(str(p.get("name", ""))) for p in poi_list}
        pins = [None if p.get("_pin_water_909") else r._poi_pin(p) for p in poi_list]
        cands = []
        for q in pool or []:
            if not isinstance(q, dict) or rc.fold(str(q.get("name", ""))) in have:
                continue
            pt = r._poi_pin(q)
            if pt is not None and not q.get("_pin_water_909") and r.along(pt, a, b) >= 0.0:
                cands.append((r.detour_ratio(pt, a, b), str(q.get("name", "")), q, pt))
        cands.sort(key=lambda z: (z[0], z[1]))
        out: List[Dict] = []
        out_pins: List[Optional[Pt]] = []
        for i, p in enumerate(poi_list):
            name = str(p.get("name", ""))
            pt = pins[i]
            if pt is None or (dest and r._names(name, dest)) or (protect and protect(p)):
                out.append(p)
                out_pins.append(pt)
                continue
            prev = next((q for q in reversed(out_pins) if q), None) or a
            nxt = next((q for q in pins[i + 1:] if q), None) or b
            why = backtrack_reason(prev, pt, nxt, a, b)
            if not why:
                out.append(p)
                out_pins.append(pt)
                continue
            rep = next((z for z in cands if not backtrack_reason(prev, z[3], nxt, a, b) and z[0] < r.MAX_DETOUR), None)
            if rep is not None:
                cands.remove(rep)
                emit(f"  {TAG} backtrack stop rejected: {name!r} ({why}) -> replaced from the pool by {rep[1]!r}")
                out.append(rep[2])
                out_pins.append(rep[3])
            elif len(out) + (len(poi_list) - i - 1) >= 2:
                emit(f"  {TAG} backtrack stop rejected: {name!r} ({why}) -> dropped (no pool candidate)")
            else:
                emit(f"  {TAG} backtrack stop {name!r} ({why}) kept: removing it would leave fewer than two stops")
                out.append(p)
                out_pins.append(pt)
        return out
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} backtrack guard skipped (non-fatal): {err}")
        return poi_list


# ══ 4. copy ═══════════════════════════════════════════════════════════════════════════════════════════════
_COPY = [
    (re.compile(r"(?i)\bday\s+(?:tours?|trips?)\s+from\b|\b(?:many|most)\s+(?:visitors|travell?ers|tourists)\s+(?:take|book|join)\b[^.!?]{0,40}\btours?\b"),
     "day-tour copy"),
    (re.compile(r"(?i)\bif\s+you\s+(?:travel|drive|continue|go|head|ride)\b[^.!?]{0,50}\bfrom\s+here\b[^.!?]{0,30}\byou\s+(?:will\s+)?(?:reach|arrive|get|come)\b"
                r"|\banother\s+(?:popular|famous|well-known|worthwhile|nearby|must-see)\s+(?:destination|attraction|spot|stop|site)\b"),
     "neighbour pointer"),
    (re.compile(r"(?i)\b(?:that|which)\s+(?:many|most|visitors|travell?ers|people)\s+(?:\w+\s+){0,2}?unforgettable\b"
                r"|\bunique\s+and\s+breathtaking\b[^.!?]*\bunforgettable\b|\bunforgettable\b[^.!?]*\bunique\s+and\s+breathtaking\b"),
     "template superlative ('unforgettable')"),
]
_CLOSE_GERUND = re.compile(r"(?i)^(?:exploring|experiencing|visiting|discovering|seeing|walking|driving|wandering|taking\s+in|immersing\s+yourself)\b"
                           r"[^.!?]{0,220}?\b(?:allows?|invites?|lets?|helps?|gives?|offers?|encourages?|deepens?|enriches?|leaves?)\b")


def _no_fact(x: str) -> bool:
    if re.search(r"\d", x or ""):
        return False
    words = re.findall(r"[^\W\d_][\w'’\-]*", x or "", re.UNICODE)
    return sum(1 for w in words[1:] if w[:1].isupper()) <= 1


def copy_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    if not s:
        return None
    for rx, why in _COPY:
        if rx.search(s):
            return why
    if _CLOSE_GERUND.match(s) and _no_fact(s):
        return "closing / body template ('Exploring ... invites ...')"
    return None


# ══ 5. the tour-level thread template in a stop body ══════════════════════════════════════════════════════
_THREAD = re.compile(r"(?i)^(?:across\s+these\s+stops\b|taken\s+together,?\s+the\s+stops\s+add\s+up\b|together,?\s+these\s+stops\s+(?:add\s+up|form|tell)\b|"
                     r"from\s+[^,]{2,80},\s+this\s+route\s+is\s+the\s+one\s+you\s+chose\b|this\s+tour\s+followed\s+one\s+thread\b)")


def thread_template(x: str) -> bool:
    return bool(_THREAD.match((x or "").strip()))


# ══ 6. a fact already stated ══════════════════════════════════════════════════════════════════════════════
def distance_duplicate(cand: str, current: Sequence[str]) -> bool:
    """``cand`` states a distance (value, direction, reference city) that a sentence of ``current`` already states."""
    import final_906u as u
    mine = u.distances(cand)
    if not mine:
        return False
    for y in current:
        for v2, k2 in u.distances(y):
            if any(k2 == k and abs(v2 - v) <= 0.5 for v, k in mine if k):
                return True
    return False


# ══ 7. one event, one telling ═════════════════════════════════════════════════════════════════════════════
_CLASSES = {
    "legend": re.compile(r"(?i)\b(?:legends?|legendary|myths?|tales?|folklore|stor(?:y|ies))\b"),
    "recognition": re.compile(r"(?i)\b(?:recogni[sz]\w*|conferred|awarded|bestowed|honou?red|granted|decreed|designated)\b"),
    "healing": re.compile(r"(?i)\b(?:heal\w*|cured?|cures|treated|remed(?:y|ies)|miracul\w*)\b"),
}


def _classes(x: str) -> Set[str]:
    return {k for k, rx in _CLASSES.items() if rx.search(x or "")}


def _names(x: str, title: str) -> Set[str]:
    skip = set(rc.fold(title).split())
    words = re.findall(r"[^\W\d_][\w'’\-]*", x or "", re.UNICODE)
    return {rc.fold(w) for w in words[1:] if w[:1].isupper() and rc.fold(w) not in skip and len(w) > 2}


def same_telling(xa: str, xb: str, title: str = "") -> bool:
    ta, tb = rc._content_tokens(xa), rc._content_tokens(xb)
    if min(len(ta), len(tb)) >= 5 and len(ta & tb) / min(len(ta), len(tb)) >= 0.6:
        return True
    ca, cb = _classes(xa), _classes(xb)
    shared = ca & cb
    if len(shared) >= 2:
        return True
    if shared and (_names(xa, title) & _names(xb, title)):
        return True
    try:
        import derepetition_guard as dg
        return bool(dg._same_event(dg._event_key(xa), dg._event_key(xb)))
    except Exception:
        return False


def retold_pass(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            items = [(i, j, x) for i in sorted(tg) if not tg[i][0] for j, x in enumerate(tg[i][1])
                     if not c._is_disclosure(x) and not rc._CLOSING_LINE.match(x)]
            parent = list(range(len(items)))

            def find(k: int) -> int:
                while parent[k] != k:
                    parent[k] = parent[parent[k]]
                    k = parent[k]
                return k
            for a in range(len(items)):
                for b in range(a + 1, len(items)):
                    if same_telling(items[a][2], items[b][2], st["title"]):
                        parent[find(b)] = find(a)
            groups: Dict[int, List[int]] = {}
            for k in range(len(items)):
                groups.setdefault(find(k), []).append(k)
            edits: Dict = {}
            for members in groups.values():
                if len(members) < 2:
                    continue
                keep = max(members, key=lambda k: (rc.specificity(items[k][2]), -k))
                for k in members:
                    if k != keep:
                        i, j, x = items[k]
                        edits[(i, j)] = []
                        emit(f'  {TAG} Stop {st["num"]}: the same event told again -> dropped "{x[:80]}" '
                             f'(kept "{items[keep][2][:60]}")')
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} retold-event guard skipped (non-fatal): {err}")
        return tour_text


# ══ 3. Directions: the leg from THIS stop to the next ═════════════════════════════════════════════════════
_DIR = re.compile(r"(?i)^(\s*Directions\s*:\s*)(.*)$")
_FROM_OPEN = re.compile(r"^(?P<f>From\s+(?:the\s+)?)(?P<name>[^,.]{2,80}?)(?P<c>,\s*)(?P<rest>.+)$", re.S)
_DEST = re.compile(r"(?i)\b(?:to\s+reach|to\s+arrive\s+at|to\s+get\s+to|to\s+find)\s+your\s+destination\b|\byour\s+destination\b")
_GO_VERB = re.compile(r"(?i)^(?:head|turn|take|follow|continue|drive|go|proceed|keep|start|bear|merge|exit)\b")


def _toks(x: str) -> List[str]:
    return re.findall(r"[^\W_]+", rc.fold(x or ""), re.UNICODE)


def _mentions(x: str, title: str) -> bool:
    all_ = _toks(_short(title))
    core = [w for w in all_ if w not in {"the", "of", "and", "mountain", "mount", "temple", "pagoda"}] or all_
    words = set(_toks(x))
    return bool(core) and all(w in words for w in core)


def directions_pass(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        infos = c._stops_info(tour_text)
        for k in range(len(infos)):
            infos = c._stops_info(tour_text)
            if k >= len(infos):
                break
            st = infos[k]
            earlier = [infos[m]["title"] for m in range(k)]
            nxt = infos[k + 1]["title"] if k + 1 < len(infos) else None
            lines = list(st["lines"])
            changed = False
            for i, ln in enumerate(lines):
                m = _DIR.match(ln)
                if i == 0 or not m or not m.group(2).strip():
                    continue
                out: List[str] = []
                for x in rc.split_sentences(m.group(2)):
                    fo = _FROM_OPEN.match(x)
                    if fo and k >= 1 and _GO_VERB.match(fo.group("rest").strip()) and not _mentions(fo.group("name"), st["title"]):
                        who = next((t for t in earlier if _mentions(fo.group("name"), t)), None)
                        if who:
                            new = "From here, " + fo.group("rest").strip()
                            emit(f'  {TAG} Stop {st["num"]}: Directions opened "From {fo.group("name")[:40]}" (an earlier stop) -> "From here": "{x[:70]}"')
                            x, changed = new, True
                    if nxt is not None and _DEST.search(x):
                        if _mentions(x, nxt):
                            new = _DEST.sub(lambda mm: mm.group(0).replace("your destination", _short(nxt)), x)
                            emit(f'  {TAG} Stop {st["num"]}: "your destination" in a non-final leg -> "{_short(nxt)[:40]}"')
                            x, changed = new, True
                        else:
                            emit(f'  {TAG} Stop {st["num"]}: Directions sentence about "your destination" that does not name the next stop dropped: "{x[:80]}"')
                            changed = True
                            continue
                    out.append(x)
                lines[i] = (m.group(1) + " ".join(out)) if out else None
            if changed:
                block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
                if tour_text[st["s"]:st["e"]].endswith("\n") and not block.endswith("\n"):
                    block += "\n"
                tour_text = tour_text[:st["s"]] + block + tour_text[st["e"]:]
        return tour_text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} directions guard skipped (non-fatal): {err}")
        return tour_text


# ══ the sentence pass ═════════════════════════════════════════════════════════════════════════════════════
def sentence_pass(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            edits: Dict = {}
            for i in sorted(tg):
                for j, x in enumerate(tg[i][1]):
                    if c._is_disclosure(x):
                        continue
                    why = copy_reason(x)
                    if not why and not st["last"] and not tg[i][0] and thread_template(x):
                        why = "tour-level thread template in a stop body"
                    if why:
                        emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                        edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} sentence pass skipped (non-fatal): {err}")
        return tour_text


def closing_pass(tour_text: str, log: Optional[Callable] = None) -> str:
    """The closing paragraph of the last stop (the line that holds "That's N stops in all.") is not a body line to the stop plumbing:
    a template sentence in it ("Experiencing ... invites ...") goes too."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        infos = c._stops_info(tour_text)
        if not infos:
            return tour_text
        st = infos[-1]
        lines = list(st["lines"])
        changed = False
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or rc._KEYED.match(ln) or i in st["idx"]:
                continue
            sents = rc.split_sentences(ln)
            keep = [x for x in sents if c._is_disclosure(x) or not (copy_reason(x) or thread_template(x))]
            if len(keep) != len(sents):
                for x in sents:
                    if x not in keep:
                        emit(f'  {TAG} closing: {copy_reason(x) or "thread template"} dropped: "{x[:90]}"')
                lines[i] = " ".join(keep) if keep else None
                changed = True
        if not changed:
            return tour_text
        block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if tour_text[st["s"]:st["e"]].endswith("\n") and not block.endswith("\n"):
            block += "\n"
        return tour_text[:st["s"]] + block + tour_text[st["e"]:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} closing guard skipped (non-fatal): {err}")
        return tour_text


def run_pass(tour_text: str, log: Optional[Callable] = None) -> str:
    t = closing_pass(sentence_pass(tour_text, log), log)
    t = retold_pass(t, log)
    return directions_pass(t, log)


# [LEAD wave 57] a gallery / breadcrumb label ("<Country>/<Province>/<Place> 1.") leaked into a stop body on the cloud: a run of
# three or more Capitalised segments joined by "/" (optionally a trailing image number) is never narration.
_SEG = r"[A-Z\u00C0-\u1EF9][\w'\u2019\-]*(?:[ \t]+[\w'\u2019\-]+){0,6}"
_BREADCRUMB = re.compile(r"(?:(?<=[.!?:;])[ \t]+|^[ \t]*|(?<=[ \t]))" + _SEG + r"(?:[ \t]*/[ \t]*" + _SEG + r"){2,}(?:[ \t]+\d{1,3})?[ \t]*[.!?]?(?=[ \t]|$)",
                         re.M)
_META_LINE = re.compile(r"^(?:Stop\s+\d+:|Address:|Coordinates:|Type/Specialty:|Specific Examples:|Tour-Category:)")


def strip_breadcrumbs(tour_text: str, log: Optional[Callable] = None) -> str:
    """Drop gallery / breadcrumb labels from narration lines (header lines untouched); logged."""
    emit = _emit(log)
    out = []
    for line in (tour_text or "").split("\n"):
        if _META_LINE.match(line) or "/" not in line:
            out.append(line)
            continue
        new = _BREADCRUMB.sub(lambda m: (emit(f'  {TAG} breadcrumb / gallery label dropped: "{m.group(0).strip()[:90]}"') or ""), line)
        out.append(re.sub(r"[ \t]{2,}", " ", new).rstrip() if new != line else line)
    return "\n".join(out)


def last_word(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """After the 906U pass: the 906V guards; a stop they (or a sensory-only body) left without a factual sentence is refilled or takes
    the D760 disclosure body (906S ``factless_stops``), then the guards run once more."""
    emit = _emit(log)
    try:
        t = run_pass(strip_breadcrumbs(tour_text, log), log)
        import language_dest_906s as s906
        t2 = s906.factless_stops(t, evidence_by_title, log)
        if t2 != t:
            t2 = run_pass(t2, log)
        return t2
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} last word skipped (non-fatal): {err}")
        return tour_text
