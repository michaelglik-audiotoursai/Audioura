"""[LOCAL-906Q] Copy guards from the 906P Mac proof. Pure, free, never raises. Generic names only (D769).

* restaurant plug     -- "You can find some of the best seafood here at <Name> restaurant, right on the banks of the <River>."
                         dropped unless the stop IS that venue.
* day-trip / operator -- "<Stop> is part of a popular full-day trip ...", "Many visitors come here ... and then take ...",
                         "Tours from <City> often include ...".
* promotion           -- "<X> is considered a resort paradise along with <Y> and attracts tourists from all over the world."
* filler              -- "The mountain's presence extends beyond its spiritual and artistic significance." (no fact, no number).
* two communes        -- one site named in two communes: the one the stop's evidence names stays, the other sentence goes.
* dangling "for,"     -- a direction sentence with "for" and no distance / duration after it.
A stop is never emptied by these drops.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906Q]"

_NAME = r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+)(?:\s+(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+|(?i:of|de|la|le|du|del|the|and|&))){0,4}"
_VENUE = r"(?i:restaurant|caf[eé]|cafe|bar|eatery)"
_PLUG = re.compile(r"(?i:\b(?:you\s+can\s+find|you\s+can\s+try|you\s+can\s+enjoy|you\s+can\s+eat|find|try|enjoy)\b)[^.!?]{0,120}?"
                   r"(?i:\b(?:here\s+)?at)\s+(?:the\s+)?(?P<n>" + _NAME + r")\s+" + _VENUE + r"\b")

_DAYTRIP = [re.compile(p) for p in (
    r"(?i)\bis\s+part\s+of\s+(?:a|an|the)\s+(?:[\w\-]+\s+){0,3}?(?:full-day|half-day|one-day|two-day|day|\d+-day|\d+-hour)\s+"
    r"(?:[\w\-]+\s+){0,2}?(?:trips?|tours?|excursions?|itinerar\w+|circuits?)\b",
    r"(?i)\bmany\s+(?:visitors|tourists|travell?ers|people)\s+come\s+(?:here|to\s+(?:see|visit)\b)[^.!?]{0,140}?"
    r"\b(?:and\s+)?then\s+(?:take|visit|head|continue|travel|go|move|drive)\b",
    r"(?i)\btours?\s+(?:from|out\s+of|departing\s+from|leaving\s+from)\s+[^.!?]{2,50}?\s+(?:often|usually|typically|commonly|"
    r"frequently|generally)\s+(?:include|stop|visit|go|combine|feature|come)\b",
)]

_PROMO = [re.compile(p) for p in (
    r"(?i)\b(?:is|are)\s+considered\s+(?:a|an|the)\s+(?:[\w\-]+\s+){0,2}?(?:resort|tourist|holiday|vacation)\s+paradise\b",
    r"(?i)\battracts?\s+(?:tourists|visitors|travell?ers|holidaymakers)\s+from\s+(?:all\s+over|around|across)\s+the\s+world\b",
)]

_FILLER = re.compile(r"(?i)\b(?:presence|influence|significance|importance|impact|legacy|reach|appeal)\s+"
                     r"(?:extends|goes|reaches|stretches|reaches\s+out)\s+(?:far\s+)?beyond\s+(?:its|their|the)\b[^.!?]{0,80}[.!]?\s*$")


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _same_venue(name: str, title: str) -> bool:
    """The stop IS the venue the sentence names (or its title names a venue of the kind)."""
    tt = rc._content_tokens(re.sub(r"[<>]", " ", title or ""))
    nt = {w for w in rc._words(re.sub(r"[<>]", " ", name or "")) if len(w) >= 4 and w not in rc._NOISE}
    return bool(tt & nt)


def reason(x: str, title: str = "") -> Optional[str]:
    """Why the sentence is copy to drop, else None."""
    s = (x or "").strip()
    m = _PLUG.search(s)
    if m and not _same_venue(m.group("n"), title) and not re.search(r"(?i)\b(?:restaurant|caf[eé]|bar|eatery)\b", title or ""):
        return "restaurant plug"
    if any(rx.search(s) for rx in _DAYTRIP):
        return "day-trip / operator copy"
    if any(rx.search(s) for rx in _PROMO):
        return "promotional copy"
    if _FILLER.search(s) and not re.search(r"\d", s) and len(s.split()) <= 20:
        return "filler (no fact)"
    return None


def drop_copy(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            edits, left = {}, len(st["flat"])
            for i, j, x in st["flat"]:
                why = reason(x, st["title"])
                if why and left > 1:
                    emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                    edits[(i, j)] = []
                    left -= 1
            return edits
        import leftovers_906f as f
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} copy guard skipped (non-fatal): {err}")
        return tour_text


# ── one site, two communes ─────────────────────────────────────────────────────────────────────────────────
_UNIT = r"(?:commune|ward|district|township|municipality|parish)"
_NEAR = re.compile(r"\bnear\s+(?:the\s+)?(?P<n>" + _NAME + r")")
_LOC_IN = re.compile(r"(?i:\b(?:is\s+)?(?:located|situated|found)\s+in)\s+(?:the\s+)?(?P<n>" + _NAME + r")\s+" + _UNIT + r"\b")


def _in(ev: str, name: str) -> bool:
    f = rc.fold(name).strip()
    return bool(f) and bool(re.search(r"\b" + re.escape(f) + r"\b", rc.fold(ev)))


def two_communes(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """A stop with "near <A>" in one sentence and "located in <B> commune" in another: the commune the stop's evidence
    names stays; the other sentence is dropped. Neither / both in the evidence: nothing is dropped."""
    emit = _emit(log)
    if not tour_text or not evidence_by_title:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)

        def fn(st: Dict, _all: List[Dict]):
            ev = rc._ev_for(ev_map, st["title"]) or ""
            if not ev:
                return {}
            near = [(i, j, x, m.group("n")) for i, j, x in st["flat"] for m in [_NEAR.search(x)] if m]
            loc = [(i, j, x, m.group("n")) for i, j, x in st["flat"] for m in [_LOC_IN.search(x)] if m]
            for ni, nj, nx, a in near:
                for li, lj, lx, b in loc:
                    if (ni, nj) == (li, lj) or rc.fold(a) == rc.fold(b):
                        continue
                    ina, inb = _in(ev, a), _in(ev, b)
                    if inb and not ina:
                        drop, keep = (ni, nj, nx), b
                    elif ina and not inb:
                        drop, keep = (li, lj, lx), a
                    else:
                        continue
                    if len(st["flat"]) <= 1:
                        return {}
                    emit(f'  {TAG} Stop {st["num"]}: two communes for one site -> kept {keep!r} (in the evidence), '
                         f'dropped: "{drop[2][:90]}"')
                    return {(drop[0], drop[1]): []}
            return {}
        import leftovers_906f as f
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} two-commune guard skipped (non-fatal): {err}")
        return tour_text


# ── a dangling "for," in a direction sentence ──────────────────────────────────────────────────────────────
_DANGLING_FOR = re.compile(r"(?i)\bfor\s*(?:[,;.]|$)|\bfor\s+then\b")


def has_dangling_for(x: str) -> bool:
    return bool(_DANGLING_FOR.search((x or "").strip()))


def drop_dangling_for(tour_text: str, log: Optional[Callable] = None) -> str:
    """In every Orientation / Directions line a sentence with a dangling "for," (no distance or duration after "for")
    is dropped. A line is never emptied."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        lines = tour_text.split("\n")
        for k, ln in enumerate(lines):
            m = re.match(r"(?i)^(\s*(?:Directions|Orientation)\s*:\s*)(.*)$", ln)
            if not m or not has_dangling_for(m.group(2)):
                continue
            sents = rc.split_sentences(m.group(2))
            kept = [x for x in sents if not has_dangling_for(x)]
            if kept and len(kept) < len(sents):
                emit(f'  {TAG} dangling "for," direction sentence dropped: '
                     f'"{next(x for x in sents if has_dangling_for(x))[:90]}"')
                lines[k] = m.group(1) + " ".join(kept)
        return "\n".join(lines)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} dangling-for guard skipped (non-fatal): {err}")
        return tour_text


def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    t = drop_copy(tour_text, log)
    t = two_communes(t, evidence_by_title, log)
    return drop_dangling_for(t, log)
