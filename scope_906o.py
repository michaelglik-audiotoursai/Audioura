"""[LOCAL-906O] A stop that is not in the tour's region, and practical copy that does not belong in an audio tour.

Pure, free, never raises. Generic names only (D769).

* ``claims_other_place``  -- a text that places a stop in ANOTHER city / province than the tour's region.
* ``reject_stops``        -- selection: a stop whose own text says it is elsewhere AND whose pin lies outside the
  padded province box is removed (replaced from the pool when ``replace_fn`` gives one).
* ``drop_other_city_sentences`` -- delivery: "This museum is actually located in <another city>" is never delivered.
* ``is_practical``        -- ticket price / opening hours / queue / "as part of a half-day tour" copy.
* ``run_pass``            -- the delivery pass on a route / drive (other city, practical copy, template closing).
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence

import route_content_896 as rc

TAG = "[LOCAL-906O]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


def _fold(x: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", rc.fold(x or ""))).strip()


# ══ 1. a stop that places itself in another city ═════════════════════════════════════════════════════════
_ACTUALLY = re.compile(r"(?i)\b(?:actually|in\s+fact|really)\s+(?:located|situated|found|based|lies|sits)\s+"
                       r"(?:in|at|near|on|within)\b(?P<where>[^.!?]*)")
_LOCATED = re.compile(r"(?i)\b(?:located|situated|based)\s+(?:in|at)\s+(?P<where>[^.!?;]{3,140})")
_KIND = re.compile(r"(?i)\s+(?:mountain|mount|mt\.?|hill|peak|lake|beach|temple|pagoda|park|island|river|falls?|"
                   r"village|town|city|province|district|national\s+park)$")


def home_terms(origin: str = "", destination: str = "", region: str = "", titles: Sequence[str] = ()) -> List[str]:
    """The names that mean "inside the tour": origin, destination, the region's province / country, and the proper-name
    cores of the stop titles (folded)."""
    out: List[str] = []

    def add(x: str) -> None:
        x = _KIND.sub("", (x or "").strip(" ,.;")).strip()
        if len(_fold(x)) >= 3 and _fold(x) not in out:
            out.append(_fold(x))
    for x in (origin, destination):
        add(x)
    for part in re.split(r"[,;]", region or ""):
        add(part)
    try:
        import anchor_evidence_906m as a
        for t in titles or []:
            for n in a.name_cores(str(t)):
                add(n)
    except Exception:  # pragma: no cover
        pass
    return out


def _names_home(where: str, home: Sequence[str]) -> bool:
    hay = " " + _fold(where) + " "
    return any((" " + _fold(h) + " ") in hay for h in home)


def claims_other_place(text: str, home: Sequence[str], strict: bool = True) -> Optional[str]:
    """The place a text puts its subject in when that place names NOTHING of the tour's region (``home``); None when the
    text does not place the subject elsewhere. ``strict`` (delivery): only the correcting wording "actually located in
    X". Not strict (selection, backed by the pin test): any "located in X" with a proper name in X."""
    try:
        if not text or not home:
            return None
        for m in _ACTUALLY.finditer(text):
            w = m.group("where").strip()
            if w and not _names_home(w, home):
                return w[:80]
        if not strict:
            for m in _LOCATED.finditer(text):
                w = m.group("where").strip()
                if re.search(r"\b[A-ZÀ-Ỹ][\w'’\-]{2,}", w) and not _names_home(w, home):
                    return w[:80]
        return None
    except Exception:  # pragma: no cover
        return None


def _pin(p: Dict):
    try:
        import route_order_909 as r
        return r._poi_pin(p)
    except Exception:  # pragma: no cover
        return None


def reject_stops(poi_list: List[Dict], box: Optional[Sequence[float]], home: Sequence[str],
                 text_fn: Optional[Callable[[Dict], str]] = None, replace_fn: Optional[Callable] = None,
                 protect: Optional[Callable[[Dict], bool]] = None, log: Optional[Callable] = None) -> List[Dict]:
    """Selection. A stop whose OWN text (name / address / description, or ``text_fn``) says it is in another city than the
    tour's region, and whose pin is outside ``box`` (or has none), is rejected; ``replace_fn(stop)`` may return a
    replacement from the pool. A user stop (``protect``) is never rejected."""
    emit = _emit(log)
    try:
        if not poi_list or not home:
            return poi_list
        try:
            import pin_fallback_906d as pf
        except Exception:  # pragma: no cover
            pf = None
        out: List[Dict] = []
        for p in poi_list:
            if not isinstance(p, dict) or (protect and protect(p)):
                out.append(p)
                continue
            txt = " ".join(str(p.get(k) or "") for k in ("name", "address", "description", "summary", "why", "type"))
            if text_fn:
                txt += " " + str(text_fn(p) or "")
            where = claims_other_place(txt, home, strict=False)
            if not where:
                out.append(p)
                continue
            pt = _pin(p)
            outside = pt is None or (bool(box) and pf is not None and not pf.in_box(pt, list(box)))
            if not outside:
                out.append(p)
                continue
            rep = replace_fn(p) if replace_fn else None
            emit(f"  {TAG} stop {str(p.get('name', ''))!r} says it is in {where!r} (outside the tour's region, pin "
                 f"{pt}) -> {'replaced by ' + repr(str(rep.get('name', ''))) if rep else 'rejected'}")
            if rep:
                out.append(rep)
        return out
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} other-city selection guard skipped (non-fatal): {err}")
        return poi_list


def drop_other_city_sentences(tour_text: str, home: Sequence[str], log: Optional[Callable] = None) -> str:
    """Delivery: a body sentence that says the stop is "actually located in <another city>" is dropped."""
    emit = _emit(log)
    if not tour_text or not home:
        return tour_text
    try:
        import leftovers_906f as f

        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                where = claims_other_place(x, home, strict=True)
                if where:
                    emit(f'  {TAG} Stop {st["num"]}: places itself in {where!r}, outside the tour\'s region -> dropped: '
                         f'"{x[:90]}"')
                    edits[(i, j)] = []
            return edits
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} other-city sentence guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. practical / ticket copy ═══════════════════════════════════════════════════════════════════════════
_TIME = r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)"
_PRACTICAL = [re.compile(p) for p in (
    # ticket / entry prices, whatever the wording between "tickets" and the verb
    r"(?i)\btickets?\b[^.!?]{0,70}?\b(?:cost|costs|priced|price|start(?:s)?\s+(?:at|from)|range\s+from|are\s+(?:about|around|only))\b",
    r"(?i)\b(?:admission|entry|entrance)\s+(?:fees?|tickets?|prices?)\b[^.!?]{0,40}?\b(?:is|are|costs?|starts?)\b",
    # opening hours
    r"(?i)\b(?:open|opens|opened)\s+(?:daily|every\s+day|from|until|till|on\s+\w+days?)\b[^.!?]{0,60}?" + _TIME,
    r"(?i)\b(?:open|opens|closes?|closed)\b[^.!?]{0,30}?\b(?:at|by|until|till|from)\s+" + _TIME,
    r"(?i)\b(?:opening|visiting)\s+(?:hours|times)\b",
    # queues
    r"(?i)\bexpect\s+(?:long\s+|big\s+)?(?:lines|queues|waits?|waiting\s+periods?|crowds)\b",
    r"(?i)\b(?:lines|queues|waiting\s+periods?)\s+(?:that\s+|which\s+)?(?:might|may|can|could|will)\s+(?:slow|delay|make)\b",
    r"(?i)\b(?:popular|peak|busy)\s+(?:times|hours|periods|seasons?)\b[^.!?]{0,50}?\b(?:lines|queues|waits?|crowds)\b",
    # packaged tours
    r"(?i)\bas\s+part\s+of\s+(?:a|an|the)\s+(?:[\w\-]+\s+){0,2}?(?:half-day|full-day|day|guided|organi[sz]ed)\s+"
    r"(?:tours?|trips?|excursions?|packages?)\b",
    r"(?i)\b(?:half-day|full-day)\s+(?:tours?|excursions?|packages?)\b",
)]


def is_practical(sentence: str) -> bool:
    return any(rx.search(sentence or "") for rx in _PRACTICAL)


def drop_practical(tour_text: str, log: Optional[Callable] = None) -> str:
    """Ticket prices, opening hours, queue warnings and "as part of a half-day tour" copy never reach an audio tour of a
    route / a drive (a price or an hour is not the narrator's to promise)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import leftovers_906f as f

        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                if is_practical(x):
                    emit(f'  {TAG} Stop {st["num"]}: practical / ticket copy dropped: "{x[:90]}"')
                    edits[(i, j)] = []
            return edits
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} practical-copy guard skipped (non-fatal): {err}")
        return tour_text


def route_like() -> bool:
    """A route / drive: an "A to B" request, a described route or a driving tour."""
    try:
        import route_order_909 as r
        if r.route() or r.is_driving():
            return True
    except Exception:  # pragma: no cover
        pass
    try:
        return bool(rc.active())
    except Exception:  # pragma: no cover
        return False


def run_pass(tour_text: str, log: Optional[Callable] = None, force: bool = False) -> str:
    """The delivery pass on a route / drive: other-city sentences, practical copy, template closing. ``force`` for tests."""
    if not tour_text or not (force or route_like()):
        return tour_text
    t = tour_text
    try:
        import route_order_909 as r
        info = r.route() or {}
        o, d, reg = info.get("origin") or "", info.get("destination") or "", info.get("region") or ""
        if rc.active():
            ro, rd = rc.endpoints()
            o, d = o or ro, d or rd
        titles = [b[3] for b in rc._stop_blocks(t)]
        t = drop_other_city_sentences(t, home_terms(o, d, reg, titles), log)
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  {TAG} region guard skipped (non-fatal): {err}")
    t = drop_practical(t, log)
    try:
        import route_leftovers_906 as l906
        t = l906.drop_template_closing(t, log)       # the 906M generalized closing, on THIS path too
    except Exception as err:  # pragma: no cover
        _emit(log)(f"  {TAG} closing guard skipped (non-fatal): {err}")
    return t
