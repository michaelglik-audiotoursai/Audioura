"""[LOCAL-906X] Two delivery guards from the LEAD Mac proofs of 906W. Pure, free, never raises. Generic names only (D769).

1. rise_pass       A "rises / climbs / ascends / gains / covers ... N m" sentence is judged against the heights the tour and its
                   evidence state:
                   - N above every stated elevation  -> dropped ("The ascent rises 1,279 meters" on a 649 m mountain);
                   - N is a stated LENGTH ("N m long", "N m in length") of a cable car / line / route and the verb is a rise verb
                     -> rewritten to "The line is about N meters long." when the evidence says exactly that, else dropped;
                   - "rises 649 meters above sea level" (N is an elevation) stays.
2. year_pass       A sentence that gives a year for a built object (statue, pagoda ...) that no evidence text states, while an
                   evidence sentence about the same object states another year, is dropped (the encyclopedia year wins). Logged.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Set, Tuple

import leftovers_906c as c
import leftovers_906f as f
import route_content_896 as rc
import splice_copy_906r as sp

TAG = "[LOCAL-906X]"


def _emit(log: Optional[Callable]) -> Callable:
    return log if callable(log) else (lambda *_a, **_k: None)


_NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
_UNIT = r"(?:m|meters?|metres?)\b"
_RISE_VERB = r"(?:rises?|rising|climbs?|climbing|ascends?|ascending|gains?|gaining|elevation\s+gain\s+of|covers?|covering)"
_RISE = re.compile(r"(?i)\b(?P<v>" + _RISE_VERB + r")\b(?P<mid>[^.!?\d]{0,40}?)\b(?P<n>" + _NUM + r")\s*(?P<u>" + _UNIT + r")")
_STRICT_RISE = re.compile(r"(?i)^(?:rises?|rising|climbs?|climbing|ascends?|ascending|gains?|gaining|elevation\s+gain\s+of)$")
_ELEV_CUE = re.compile(r"(?i)\b(?:above\s+sea\s+level|a\.?s\.?l\.?|elevation|altitude|high|tall|height|summit|peak|top\s+of|reaches|stands)\b")
_LEN_CUE = re.compile(r"(?i)\b(?:long|length|span\w*)\b")
_LINE_WORD = re.compile(r"(?i)\b(?:cable\s*car|cable-car|ropeway|gondola|line|route|trail|track|tramway|funicular)\b")
_ANY_M_FULL = re.compile(r"(?<![\w.,])(?P<n>" + _NUM + r")\s*(?P<u>" + _UNIT + r"|feet|foot|ft)\b", re.I)


def _val(n: str) -> float:
    try:
        return float(n.replace(",", ""))
    except Exception:
        return 0.0


def _meters(n: str, unit: str) -> float:
    v = _val(n)
    return v * 0.3048 if unit.lower() in ("feet", "foot", "ft") else v


def _elevations(sentences: List[str]) -> List[float]:
    """Heights (m) the sentences state for a mountain / site: a measure with an elevation cue and no length cue, never a rise claim."""
    out: List[float] = []
    for x in sentences:
        if _RISE.search(x) or _LEN_CUE.search(x) or not _ELEV_CUE.search(x):
            continue
        for m in _ANY_M_FULL.finditer(x):
            out.append(_meters(m.group("n"), m.group("u")))
    return out


def _lengths(sentences: List[str]) -> List[Tuple[float, str]]:
    """(metres, sentence) of every "N m long" / "N m in length" the sentences state about a line / cable car / route."""
    out: List[Tuple[float, str]] = []
    for x in sentences:
        if not _LEN_CUE.search(x):
            continue
        for m in _ANY_M_FULL.finditer(x):
            tail = x[m.end():m.end() + 25]
            head = x[max(0, m.start() - 40):m.start()]
            if re.match(r"(?i)\s*(?:-|\s)*(?:long|in\s+length)\b", tail) or re.search(r"(?i)\b(?:length|span\w*)\b[^.!?]{0,25}$", head):
                out.append((_meters(m.group("n"), m.group("u")), x))
    return out


def _all_sentences(tour_text: str, ev_map: Dict[str, str]) -> Tuple[List[str], List[str]]:
    tour: List[str] = []
    for st in f._stops(tour_text):
        tour.extend(x for _i, _j, x in st["flat"])
    ev: List[str] = []
    for v in ev_map.values():
        ev.extend(rc.split_sentences(v or ""))
    return tour, ev


def rise_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        tour_s, ev_s = _all_sentences(tour_text, ev_map)
        elevs = _elevations(tour_s + ev_s)
        lengths = _lengths(tour_s + ev_s)

        def fn(st: Dict, tg):
            edits: Dict = {}
            for i in sorted(tg):
                for j, x in enumerate(tg[i][1]):
                    if c._is_disclosure(x):
                        continue
                    m = _RISE.search(x)
                    if not m:
                        continue
                    n = _val(m.group("n"))
                    strict = bool(_STRICT_RISE.match(re.sub(r"\s+", " ", m.group("v").strip())))
                    stated_len = next((ls for (L, ls) in lengths if abs(L - n) < 0.5 and ls is not x), None)
                    if stated_len is not None and strict:
                        if _LINE_WORD.search(stated_len) and re.search(r"(?i)\b" + re.escape(m.group("n")) + r"\b", stated_len):
                            new = f"The line is about {m.group('n')} meters long."
                            emit(f'  {TAG} Stop {st["num"]}: a length stated as a rise -> rewritten "{new}" (was "{x[:90]}")')
                            edits[(i, j)] = [new]
                        else:
                            emit(f'  {TAG} Stop {st["num"]}: a length ({m.group("n")} m) stated as a rise dropped: "{x[:90]}"')
                            edits[(i, j)] = []
                        continue
                    if stated_len is not None and not strict:
                        continue                           # "covers N m" with N a stated length: a length, not a rise
                    higher = [e for e in elevs if e > 0]
                    if higher and n > max(higher) + 0.5:
                        emit(f'  {TAG} Stop {st["num"]}: "{m.group("v")} {m.group("n")} m" exceeds the stated elevation '
                             f'({max(higher):.0f} m) -> dropped: "{x[:90]}"')
                        edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} rise guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. a year no article states for a built object ════════════════════════════════════════════════════════
def _things(x: str) -> Set[str]:
    return {w for w in f._OBJECT_NOUNS if re.search(r"(?i)\b" + w + r"s?\b", x or "")}


def year_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text
        ev_text = " ".join(ev_map.values())
        ev_years = set(re.findall(r"\d{3,4}", ev_text))
        ev_claims = [(s, _things(s), set(f._YEAR.findall(s))) for v in ev_map.values() for s in rc.split_sentences(v or "")
                     if f._ANY_V.search(s) and f._YEAR.search(s)]

        def fn(st: Dict, tg):
            edits: Dict = {}
            for i in sorted(tg):
                for j, x in enumerate(tg[i][1]):
                    if c._is_disclosure(x) or not f._ANY_V.search(x):
                        continue
                    years = set(f._YEAR.findall(x))
                    things = _things(x)
                    if not years or not things:
                        continue
                    bad = sorted(y for y in years if y not in ev_years)
                    if not bad:
                        continue
                    other = next(((s, ys) for (s, th, ys) in ev_claims if th & things and bad[0] not in ys), None)
                    if other is None:
                        continue
                    emit(f'  {TAG} Stop {st["num"]}: year {bad[0]} for the {"/".join(sorted(things))} is in no article; the evidence says '
                         f'{"/".join(sorted(other[1]))} ("{other[0][:70]}") -> dropped: "{x[:90]}"')
                    edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} year guard skipped (non-fatal): {err}")
        return tour_text


def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    return year_pass(rise_pass(tour_text, evidence_by_title, log), evidence_by_title, log)
