"""[LOCAL-906P] Delivery guards from the 906O Mac proof: record hedge as the LAST word, photo-caption / list-stub junk, a glued
sentence, a cable car with impossible numbers, an unsupported superlative in the closing.

Pure, free, never raises. Generic names only (D769).

* ``hedge_guard``        -- an unhedged size superlative ("the longest Reclining Buddha in <Country>") whose stop says "one of the
  largest" elsewhere (the evidence, or another sentence of the same stop) becomes "one of the longest ...". Runs LAST (after every
  refill / key-fact injection / cross-stop move), so a late-added sentence is caught. One stop never says both.
* ``drop_junk``          -- an image caption ("A person observes ..."), a list stub (ends in ":", " - " bullets, "is located as
  follows") is never delivered.
* ``fix_glued``          -- "... shifts that shaped The <Name> River, once known as ..., runs ..." is a cut sentence + a sentence that
  starts with "The": the cut fragment goes.
* ``cable_car_numbers``  -- a rise ("ascends 1,279 meters") above the place's known elevation, or a cable car number no evidence of
  the stop carries, is dropped (logged; no earlier path named it).
* ``closing_claims``     -- a superlative in the closing that no stop states is dropped.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906P]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _each(text: str, fn):
    import leftovers_906f as f
    return f._each_stop(text, fn)


# ══ 1. the hedge, last ═══════════════════════════════════════════════════════════════════════════════════
_PAST_RECORD = re.compile(r"(?i)\b(?:was|were|had\s+been)\s+(?:once\s+|formerly\s+)?the\s+(?:largest|biggest|longest|tallest|highest|"
                          r"oldest|deepest|widest)\b[^.!?]{0,100}?\b(?:until|up\s+to|before|till|through|prior\s+to)\s+\d{4}")


def _size_claim(x: str, hedged: bool) -> Optional[Dict]:
    cl = c.scoped_claim(x, include_hedged=True)
    if cl and cl["cls"] in c._SIZE_CLASSES and bool(cl["hedged"]) == hedged:
        return cl
    return None


def _evidence_hedges(evidence: str) -> bool:
    """The stop's evidence hedges a size record in ANY scope ("one of the largest in <Region>"), or says it WAS the largest
    up to a year (so it no longer is)."""
    for es in rc.split_sentences(evidence or ""):
        if _PAST_RECORD.search(es):
            return True
        for e in c.scoped_claims(es, include_hedged=True):
            if e["hedged"] and e["cls"] in c._SIZE_CLASSES:
                return True
    return False


def hedge_guard(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                log: Optional[Callable] = None) -> str:
    """An UNHEDGED size superlative in a stop that also (a) says "one of the largest ..." in another sentence, or (b) whose
    evidence hedges / dates the record, is rewritten as the hedged form ("one of the longest ..."). Logged."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)

        def fn(st: Dict, _all: List[Dict]):
            title = st["title"]
            ev = (rc._ev_for(ev_map, title) or "") if ev_map else ""
            hedged_here = any(_size_claim(x, True) for _i, _j, x in st["flat"])
            ev_hedge = _evidence_hedges(ev)
            if not (hedged_here or ev_hedge):
                return {}
            edits: Dict[Tuple[int, int], List[str]] = {}
            for i, j, x in st["flat"]:
                cl = _size_claim(x, False)
                if not cl or c._local_scope(cl, title):
                    continue
                new = c._hedge_text(x)
                if new and new != x:
                    why = "the stop's evidence hedges the record" if ev_hedge else "the same stop says \"one of the ...\""
                    emit(f'  {TAG} Stop {st["num"]}: record claim hedged ({why}): "{x[:80]}" -> "{new[:80]}"')
                    edits[(i, j)] = [new]
            return edits
        return _each(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} hedge guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. captions and list stubs ═══════════════════════════════════════════════════════════════════════════
_CAPTION = [re.compile(p) for p in (
    r"(?i)^(?:an?|the)\s+(?:person|people|man|woman|child|children|boy|girl|couple|group(?:\s+of\s+\w+)?|tourists?|visitors?|"
    r"hikers?|travell?ers?|swimmers?|worker|workers)\s+(?:observes?|observing|watch(?:es|ing)?|looks?|looking|gazes?|stands?|standing|"
    r"sits?|sitting|walks?|walking|poses?|posing|holds?|holding|takes?|taking|enjoys?|enjoying|admires?|admiring|views?|"
    r"photographs?|collects?|picks?|cleans?)\b",
    r"(?i)\bpictured\b",
    r"(?i)^(?:photo|image|picture|figure|fig\.?)\s*[:\d]",
    r"(?i)\bphoto\s+of\b",
    r"(?i)\(\s*(?:photo|image|picture)\b",
    r"(?i)\bphoto(?:graph)?\s+(?:by|credit|courtesy)\b",
    r"(?i)\bimage\s+(?:credit|courtesy|source)\b",
)]
_LIST_STUB = [re.compile(p) for p in (
    r":\s*[\"”’)]?\s*$",
    r":\s*[-–•*]\s+\S",
    r"(?i)\b(?:is|are)\s+(?:geographically\s+)?(?:located|situated|bordered|divided)\s+as\s+follows\b",
    r"(?i)\bas\s+follows\s*[:,]",
    r"(?:^|\s)[-–•]\s+(?:To|In|On|At|The|From)\s+(?:the\s+)?(?:north|south|east|west|[A-Z])",
    r"\s-\s+\S.*\s-\s+\S",
)]


def junk_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    if any(rx.search(s) for rx in _CAPTION):
        return "photo caption"
    if any(rx.search(s) for rx in _LIST_STUB):
        return "list stub"
    return None


def drop_junk(tour_text: str, log: Optional[Callable] = None) -> str:
    """Image-caption / list-stub sentences are never delivered (a stop is never emptied by it)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            edits, left = {}, len(st["flat"])
            for i, j, x in st["flat"]:
                why = junk_reason(x)
                if why and left > 1:
                    emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                    edits[(i, j)] = []
                    left -= 1
            return edits
        return _each(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} junk guard skipped (non-fatal): {err}")
        return tour_text


# ══ 3. a glued sentence ══════════════════════════════════════════════════════════════════════════════════
_GLUE = re.compile(r"(?<=[a-z])\s+(?P<the>The)\s+(?=[A-ZÀ-Ỹ][\w'’\-]*(?:\s+[A-ZÀ-Ỹ][\w'’\-]*)+)")
_GLUE_OK_LEFT = re.compile(r"(?i)(?:^(?:that|which|who|whom)|(?:ed|ing))$")
_GLUE_BAD_LEFT = frozenset("red bed shed speed need feed seed breed proceed indeed".split())


def glued_split(x: str) -> Optional[str]:
    """The right-hand sentence of ``x`` when ``x`` is a cut sentence glued to a sentence that starts with "The", else None."""
    for m in _GLUE.finditer(x or ""):
        left, right = x[:m.start()], x[m.start("the"):]
        w = re.findall(r"[A-Za-zÀ-ỹ'’\-]+$", left)
        if not w or left.rstrip()[-1:] in ",;:" or w[0].lower() in _GLUE_BAD_LEFT or not _GLUE_OK_LEFT.search(w[0]):
            continue
        if len(left.split()) < 5 or len(right.split()) < 6 or right[-1:] not in ".!?":
            continue
        if not re.match(r"The\s+(?:[A-ZÀ-Ỹ][\w'’\-]*\s+){1,5}[A-ZÀ-Ỹ][\w'’\-]*\s*(?:,|\s[a-z])", right):
            continue
        return right
    return None


def fix_glued(tour_text: str, log: Optional[Callable] = None) -> str:
    """"... shaped The <Name> River, once known as ..., runs ..." -> the cut left part is dropped, the "The ..." sentence stays."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                right = glued_split(x)
                if right:
                    emit(f'  {TAG} Stop {st["num"]}: glued sentence (a cut fragment + a sentence starting with "The") -> '
                         f'fragment dropped: "{x[:70]}"')
                    edits[(i, j)] = [right]
            return edits
        return _each(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} glued-sentence guard skipped (non-fatal): {err}")
        return tour_text


# ══ 4. the cable car's numbers ═══════════════════════════════════════════════════════════════════════════
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT = r"(?:kilometres?|kilometers?|metres?|meters?|km|feet|foot|ft|m)"
_TO_M = {"m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0, "km": 1000.0, "kilometer": 1000.0,
         "kilometers": 1000.0, "kilometre": 1000.0, "kilometres": 1000.0, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048}
_CABLE = re.compile(r"(?i)\b(?:cable\s*car|cableway|gondola|funicular|chair\s*lift|aerial\s+(?:tram|lift)|tramway|ropeway|"
                    r"ski\s*lift|lift\s+system)\b")
_RISE = re.compile(r"(?i)\b(?:ascend|ascends|ascending|rise|rises|rising|climb|climbs|climbing|gain|gains|gaining|lift|lifts|"
                   r"elevates?|raises?)\b[^.!?]{0,30}?\b(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\b"
                   r"|\b(?:vertical\s+(?:rise|drop|gain|climb)|elevation\s+gain|height\s+gain|rise)\s+of\s+(?:about\s+|around\s+|nearly\s+)?"
                   r"(?P<n2>" + _NUM + r")\s*-?\s*(?P<u2>" + _UNIT + r")\b")
_ANY_NUM = re.compile(r"(?i)(?<![\w.])(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\b")
_ELEV_EV = [re.compile(p) for p in (
    r"(?i)(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\s+(?:above|over)\s+(?:the\s+)?(?:mean\s+)?sea",
    r"(?i)\b(?:elevation|altitude)\s+(?:of\s+|is\s+|at\s+|reaches\s+)?(?:about\s+|around\s+|nearly\s+)?(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\b",
    r"(?i)\b(?:summit|peak|top)\b[^.!?]{0,40}?(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\b",
    r"(?i)\b(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\s*-?\s*(?:high|tall)\s+(?:mountain|hill|peak|mount|summit)\b",
    r"(?i)\b(?:mountain|hill|peak|mount)\b[^.!?]{0,60}?\b(?:is|stands|reaches|rises\s+to|measures)\s+(?:at\s+)?(?:about\s+|around\s+|nearly\s+)?"
    r"(?P<n>" + _NUM + r")\s*-?\s*(?P<u>" + _UNIT + r")\b(?:\s*-?\s*(?:high|tall))?",
)]


def _meters(n: str, u: str) -> Optional[float]:
    f = _TO_M.get(u.lower())
    return None if f is None else float(n.replace(",", "")) * f


def place_elevations(text: str) -> List[float]:
    """Elevations (meters) a text states for a place: above sea level / elevation / altitude / summit / "N m high mountain"."""
    out: List[float] = []
    for s in rc.split_sentences(text or ""):
        for rx in _ELEV_EV:
            for m in rx.finditer(s):
                v = _meters(m.group("n"), m.group("u"))
                if v and v not in out:
                    out.append(v)
    return out


def evidence_values(text: str) -> List[float]:
    return [v for m in _ANY_NUM.finditer(text or "") for v in [_meters(m.group("n"), m.group("u"))] if v]


def _traceable(v: float, values: Sequence[float]) -> bool:
    return any(abs(v - w) <= 0.03 * max(v, w, 1e-9) for w in values)


def cable_car_numbers(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                      log: Optional[Callable] = None) -> str:
    """A cable-car / ascent sentence with a rise above the place's known elevation, or with a number the stop's own evidence does
    not carry, is dropped. Elevation: the stop's evidence, else every stop's. A stop with no evidence is judged on the elevation
    alone."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        all_elev: List[float] = []
        for v in (ev_map or {}).values():
            all_elev += place_elevations(v)

        def fn(st: Dict, _all: List[Dict]):
            title = st["title"]
            ev = (rc._ev_for(ev_map, title) or "") if ev_map else ""
            elev = place_elevations(ev) or all_elev
            top = max(elev) if elev else None
            vals = evidence_values(ev)
            flat = st["flat"]
            edits, left = {}, len(flat)
            for k, (i, j, x) in enumerate(flat):
                prev = flat[k - 1][2] if k else ""
                cue = bool(_CABLE.search(x) or _CABLE.search(prev) or re.search(r"(?i)\bfrom\s+the\s+(?:base|bottom|foot)\b", x))
                if not cue:
                    continue
                reason = None
                for m in _RISE.finditer(x):
                    v = _meters(m.group("n") or m.group("n2"), m.group("u") or m.group("u2"))
                    if v is None:
                        continue
                    if top is not None and v > top * 1.05:
                        reason = f"rise {v:.0f} m exceeds the place's known elevation {top:.0f} m"
                    elif vals and not _traceable(v, vals):
                        reason = f"rise {v:.0f} m is in no evidence of the stop"
                    if reason:
                        break
                if not reason and _CABLE.search(x) and vals:
                    for m in _ANY_NUM.finditer(x):
                        v = _meters(m.group("n"), m.group("u"))
                        if v and v >= 100 and not _traceable(v, vals):
                            reason = f"number {m.group(0)} is in no evidence of the stop"
                            break
                if reason and left > 1:
                    emit(f'  {TAG} Stop {st["num"]}: cable car / ascent number dropped ({reason}): "{x[:90]}"')
                    edits[(i, j)] = []
                    left -= 1
            return edits
        return _each(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} cable-car number guard skipped (non-fatal): {err}")
        return tour_text


# ══ 5. the closing states nothing the stops did not ══════════════════════════════════════════════════════
_SUPER = re.compile(r"(?i)\b(?:the\s+)?(?P<w>largest|biggest|greatest|longest|tallest|highest|oldest|deepest|widest|smallest|"
                    r"only|first)\s+(?P<noun>[a-z][\w\-]*)")


def closing_claims(tour_text: str, log: Optional[Callable] = None) -> str:
    """A superlative in the CLOSING (the sentences on / after the "That's N stops in all." line) that no stop body states
    ("the tallest lighthouse") is dropped: a closing never delivers what the stops did not say, supported."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if not blocks:
            return tour_text
        s, e, _num, _title = blocks[-1]
        body_text = rc.fold(" ".join(tour_text[bs:be] for bs, be, _n, _t in blocks[:-1]))
        lines = tour_text[s:e].split("\n")
        seen_count, changed = False, False
        for idx, ln in enumerate(lines):
            if idx == 0 or not ln.strip() or rc._KEYED.match(ln):
                continue
            sents = rc.split_sentences(ln)
            has_count = any(re.match(r"(?i)that['\u2019]s\s+\d+\s+stops?", x) for x in sents)
            if not (has_count or seen_count):
                continue
            seen_count = True
            earlier = rc.fold(" ".join(lines[1:idx]))
            keep = []
            for x in sents:
                if rc._CLOSING_LINE.match(x):
                    keep.append(x)
                    continue
                bad = None
                for m in _SUPER.finditer(x):
                    key = rc.fold(m.group("w") + " " + m.group("noun"))
                    if key and key not in body_text and key not in earlier:
                        bad = m.group(0)
                        break
                if bad:
                    emit(f'  {TAG} closing: superlative "{bad}" is stated by no stop -> sentence dropped: "{x[:100]}"')
                    changed = True
                    continue
                keep.append(x)
            lines[idx] = " ".join(keep) if keep else None
        if not changed:
            return tour_text
        new = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if not new.endswith("\n") and tour_text[s:e].endswith("\n"):
            new += "\n"
        return tour_text[:s] + new + tour_text[e:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} closing-claim guard skipped (non-fatal): {err}")
        return tour_text


# ══ the passes ═══════════════════════════════════════════════════════════════════════════════════════════
def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """Junk, glued sentence, cable-car numbers, raw measure splice, closing: the removals (inside the 906F pass)."""
    t = drop_junk(tour_text, log)
    t = fix_glued(t, log)
    t = cable_car_numbers(t, evidence_by_title, log)
    try:
        import refill_quality_906k as k

        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                new, did = k.fix_bad_splice(x)
                if did:
                    _emit(log)(f'  {TAG} Stop {st["num"]}: measure noun spliced as raw text -> clause cut: "{x[:80]}"')
                    edits[(i, j)] = [new]
            return edits
        t = _each(t, fn)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  {TAG} splice guard skipped (non-fatal): {err}")
    return closing_claims(t, log)


def final_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """The very last delivery guard: the hedge on whatever the earlier passes (refills, moves, key-fact injection) left."""
    return hedge_guard(tour_text, evidence_by_title, log)
