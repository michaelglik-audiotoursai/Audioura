"""[LOCAL-906K] Refill quality bar + the 906J leftovers (promo, mode words, conflicting measures).

Pure, free, never raises. Generic names only (D769).

* ``refill_reject`` -- the bar every refill / filler sentence must clear (906I thin refill, 906C filler branch (a),
  904 / 905 refills). Returns the REASON a candidate is refused, or None. A refused candidate is logged by
  ``reject_logged``; no sentence is better than a bad one (the stop stays thin or takes the D760 disclosed body).
* ``is_venue_promo`` -- "you can visit <Name> restaurant", "if you want to try ... you can ...", "Choose ... with or
  without a guide" (unless the stop IS that venue).
* ``fix_mode_words`` -- "as you walk here" / "walk around" on a driving tour.
* ``resolve_measure_conflicts`` -- two values for one measure: the article's wins; web pages alone disagreeing -> omit.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Set, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906K]"
MAX_WORDS = 45


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


# ══ 1. the refill quality bar ════════════════════════════════════════════════════════════════════════════
_ELLIPSIS = re.compile(r"\.{2,}|…|\[\s*\.\.\.\s*\]")
_PRICE = re.compile(
    r"(?i)[$€£¥₫฿]|\b(?:usd|eur|gbp|vnd|baht|dollars?|euros?|dong)\b|\bper\s+(?:adult|person|child|head|night|ticket|guest)\b"
    r"|\bfrom\s+\d[\d.,]*\s*(?:usd|eur|vnd)\b|\b\d+(?:\.\d+)?\s*(?:/|out\s+of)\s*5\b|\b\d[\d.,]*\s+(?:stars?|reviews?|ratings?)\b"
    r"|\b(?:rated|rating|reviews?|tripadvisor)\b|\bpassengers?\s*(?:/|per)\s*(?:hour|hr)\b|\b(?:/|per)\s*hour\b"
    r"|\b(?:cheap|affordable|discount\w*|luxury\s+from|free\s+cancell?ation)\b")
_SELLING = re.compile(r"(?i)\b(?:video|videos|click|clicking|book(?:ing|ed|s)?|tour\s+packages?|packages?|tickets?|watch|"
                      r"subscribe|itinerary|booking|reserve|reservations?|promo\w*)\b")
_GLUED = re.compile(r"\b[A-Za-z]{2,}\d+\b|[a-z]{2,}[A-Z][a-z]|[.!?][A-Z][a-z]")
_WORLD = re.compile(r"(?i)\bworld['’]s\b|\bin\s+the\s+world\b|\bin\s+all\s+(?:of\s+)?the\s+world\b|\bthe\s+(?:only|sole)\b|"
                    r"\b(?:world|guinness|national)[\s-]records?\b|\brecord[\s-]breaking\b|\b(?:holds?|held)\s+(?:the\s+)?records?\b|"
                    r"\bno\s+other\b|\bnowhere\s+else\b|\bunique\s+(?:in|to)\b|\bone\s+and\s+only\b")
_PLACE_NOUNS = ("village|bridge|temple|pagoda|mountain|mount|lake|river|falls|waterfall|tower|palace|castle|cave|park|market|"
                "beach|island|statue|church|cathedral|mosque|monastery|shrine|fort|square|garden|museum|hill|valley|peak|"
                "summit|gate|harbou?r|port|resort|hotel|restaurant|cafe|café")
_LANDMARK_SPAN = re.compile(r"(?:<[^>]{1,40}>|(?:[A-ZÀ-Ỹ][\w'’\-]+\s+){0,3}[A-ZÀ-Ỹ][\w'’\-]+)")
_PLACE_NOUN_RX = re.compile(r"(?i)\b(?:" + _PLACE_NOUNS + r")\b")
_SOURCE_CACHE: Dict[Tuple[int, str], Set[str]] = {}


def _fold_set(text: str) -> Set[str]:
    return set(rc._words(re.sub(r"[<>]", " ", text or "")))


def _tour_words(tour_text: Optional[str]) -> Set[str]:
    return _fold_set(tour_text or "")


def _title_tokens(title: str, type_text: str = "") -> Set[str]:
    toks = set(rc._content_tokens(re.sub(r"[<>]", " ", title or "")))
    words = rc._words(re.sub(r"[<>]", " ", title or ""))
    if words:
        toks.add(words[-1])
    for w in rc._words(type_text or ""):
        if len(w) >= 5:
            toks.add(w)
    return {t[:-1] if len(t) > 4 and t.endswith("s") else t for t in toks}


def about_stop(cand: str, title: str, type_text: str = "") -> bool:
    toks = _title_tokens(title, type_text)
    if not toks:
        return True
    words = {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in rc._words(cand)}
    return bool(toks & words)


def other_landmark(cand: str, title: str, tour_text: Optional[str]) -> Optional[str]:
    """A named landmark (a name carrying a place noun) that is neither this stop's title nor anywhere in the tour."""
    known = _tour_words(tour_text) | _fold_set(title)
    if tour_text is None:
        known = _fold_set(title)
    for m in _LANDMARK_SPAN.finditer(cand or ""):
        span = m.group(0)
        inner = re.sub(r"[<>]", " ", span)
        if not _PLACE_NOUN_RX.search(inner):
            continue
        # a capitalised sentence opener ("The Reclining Buddha ...") is not a landmark name by itself
        toks = [w for w in rc._words(inner) if w not in rc._NOISE]
        if not toks:
            continue
        if all(w in known for w in toks):
            continue
        # only the tokens that make this a NAME (not the leading capitalised sentence word) count as unknown
        if m.start() == 0 and not span.startswith("<") and len(toks) == 1:
            continue
        return span.strip()
    return None


def source_of(cand: str, blob: str, title: str) -> str:
    """'article' when the sentence is a sentence of the stop's OWN article, else 'snippet' (a search result / web line)."""
    try:
        import key_fact_coverage as kfc
        own = {rc.fold(x) for x in kfc.own_prose_sentences(blob or "", title)}
        return "article" if rc.fold(cand) in own else "snippet"
    except Exception:  # pragma: no cover
        return "snippet"


def refill_reject(cand: str, title: str, tour_text: Optional[str] = None, source: str = "article",
                  type_text: str = "", own_evidence: bool = False) -> Optional[str]:
    """The reason ``cand`` may not be used as a refill / filler sentence, else None (it is clean)."""
    x = (cand or "").strip()
    if not x:
        return "empty"
    if _ELLIPSIS.search(x):
        return "truncated (ellipsis)"
    if x[-1:] not in ".!?" or not (x[:1].isupper() or x[:1] in "<\"'“"):
        return "not a whole sentence"
    n = len(x.split())
    if n > MAX_WORDS:
        return f"run-on ({n} words)"
    if _PRICE.search(x):
        return "price / rating / capacity figure"
    if _SELLING.search(x):
        return "video / booking / selling word"
    if _GLUED.search(x):
        return "glued tokens"
    if _WORLD.search(x) or c.record_claim(x):
        return "world / record / exclusivity claim"
    m = c._SUP_RX.search(x)
    if m and not c._ONE_OF.search(x[:m.start()].rstrip() + " "):
        return "unhedged superlative claim"
    if c.scoped_claim(x) is not None:
        return "scoped superlative claim"
    try:
        import leftovers_906f as _f
        if _f.is_promo(x) or is_venue_promo(x, title):
            return "promo copy"
    except Exception:  # pragma: no cover
        pass
    if not own_evidence and not about_stop(x, title, type_text):   # a sentence of the stop's OWN evidence is keyed to it already
        return "not about this stop"
    other = other_landmark(x, title, tour_text)
    if other:
        return f"names another place ({other[:30]})"
    if source != "article":
        try:
            import place_names_900 as pn
            if not pn.is_clean_neighbour_sentence(x):
                return "search snippet that is not a clean complete sentence"
        except Exception:  # pragma: no cover
            pass
    return None


def reject_logged(cand: str, title: str, tour_text: Optional[str], log: Optional[Callable], num: object = "?",
                  source: str = "article", type_text: str = "", own_evidence: bool = False) -> bool:
    """True = refused (and logged with the reason)."""
    why = refill_reject(cand, title, tour_text, source, type_text, own_evidence)
    if why:
        _emit(log)(f'  {TAG} Stop {num}: refill candidate rejected ({why}): "{(cand or "")[:90]}"')
        return True
    return False


# ══ 5. venue promo ═══════════════════════════════════════════════════════════════════════════════════════
_VENUE_NOUN = r"(?:restaurant|caf[eé]|cafe|shop|bar|bistro|eatery|store|stall|diner|bakery|inn|hotel|resort|homestay|bistro)"
_VENUE_PROMO = [re.compile(p) for p in (
    r"(?i)\byou\s+(?:can|could|may|might)\s+(?:also\s+)?(?:visit|try|eat\s+at|dine\s+at|stop\s+(?:at|by|in)|stay\s+at|shop\s+at|"
    r"drop\s+(?:in|by)(?:\s+at)?|head\s+(?:to|over\s+to))\s+(?:the\s+)?(?:[\w'’\-<>]+\s+){0,4}?" + _VENUE_NOUN + r"\b",
    r"(?i)\byou\s+(?:can|could|may|might)\s+(?:also\s+)?(?:visit|try|eat\s+at|dine\s+at|stop\s+(?:at|by)|stay\s+at)\s+"
    r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+(?:\s+[A-ZÀ-Ỹ][\w'’\-]+){0,3})\s+(?:right\s+)?(?:here|there|nearby|close\s+by|next\s+door)\b",
    r"(?i)\bif\s+you\s+(?:want|wish|would\s+like|'d\s+like|are\s+(?:hungry|thirsty|looking|keen))\s+to\s+"
    r"(?:try|taste|sample|eat|buy|shop|stay|drink|dine|grab)\b[^.!?]*?\byou\s+(?:can|could|may|might)\b",
    r"(?i)\bchoose\b[^.!?]{0,90}\bwith\s+or\s+without\s+(?:a\s+)?(?:guide|tour\s+guide)\b",
    r"(?i)\bwith\s+or\s+without\s+(?:a\s+)?(?:tour\s+)?guide\b",
    r"(?i)\b(?:hotel\s+)?pick-?\s?ups?\s+(?:is|are)\s+(?:also\s+)?(?:available|included|offered|provided)\b",   # [LEAD 906L]
    r"(?i)\b(?:hotel\s+)?(?:transfers?|drop-?offs?)\s+(?:is|are)\s+(?:also\s+)?(?:available|included|offered|provided)\b",
)]
_VENUE_TITLE = re.compile(r"(?i)\b" + _VENUE_NOUN + r"\b|\bmarket\b|\bfood\b|\bkitchen\b|\bbrewery\b|\bwinery\b")


def is_venue_promo(sentence: str, title: str = "") -> bool:
    """Promo copy for a venue, unless the stop IS that venue (its title is / names a venue of the kind, or the named place
    is the stop's own title)."""
    x = sentence or ""
    if not any(rx.search(x) for rx in _VENUE_PROMO):
        return False
    if _VENUE_TITLE.search(title or ""):
        return False
    tt = rc._content_tokens(re.sub(r"[<>]", " ", title or ""))
    m = re.search(r"(?i)\b(?:visit|try|eat\s+at|dine\s+at|stop\s+(?:at|by|in)|stay\s+at|shop\s+at|drop\s+(?:in|by)(?:\s+at)?|"
                  r"head\s+(?:to|over\s+to))\s+(?:the\s+)?(?P<obj>(?:<[^>]{1,40}>|[\w'’\-]+)(?:\s+(?:<[^>]{1,40}>|[\w'’\-]+)){0,3})", x)
    obj = {w for w in rc._words(re.sub(r"[<>]", " ", m.group("obj"))) if len(w) >= 4 and w not in rc._NOISE} if m else set()
    return not (tt & obj)              # the venue the sentence sends you to is the stop itself


# ══ 6. mode words on a driving tour ══════════════════════════════════════════════════════════════════════
_DRIVING = re.compile(r"(?im)^\s*Tour-Category:\s*(?:driving|drive|car|road(?:\s*trip)?|motor\w*|scooter)\b|\A[^\n]*\bdriving\s+tour\b")
_AS_WALK = re.compile(r"(?i)\b(?:as|while|when)\s+you\s+(?:walk|stroll|wander)(?:\s+around)?\s+(?:here|there)\b")
_AS_WALK2 = re.compile(r"(?i)\b(?:as|while|when)\s+you\s+(?:walk|stroll|wander)\s+around\b")
_WALK_AROUND = re.compile(r"(?i)\b(?:walk|stroll|wander)\s+around\b")


def is_driving(tour_text: str) -> bool:
    return bool(_DRIVING.search(tour_text or ""))


_DET_AFTER = r"(?=\s+(?:the|a|an|this|that|these|those|its|their|<))"


def _cap_at_start(whole: str, pos: int, rep: str) -> str:
    """[LOCAL-906N] A replacement that lands at a sentence start is capitalised."""
    before = whole[:pos]
    if (not before.strip() or re.search(r"[.!?:]\s*$", before)) and rep[:1].islower():
        return rep[0].upper() + rep[1:]
    return rep


def _mode_fix(x: str) -> str:
    """[LOCAL-906N] \"As you walk around the market, ...\" -> \"Around the market, ...\" (was \"here the market, ...\");
    \"As you walk here, ...\" -> \"Here, ...\"; \"walk around\" -> \"look around\"; every rewrite at a sentence start is
    re-capitalised."""
    def sub(rx, rep, s):
        out, last = [], 0
        for m in rx.finditer(s):
            r = rep(m) if callable(rep) else rep
            out.append(s[last:m.start()])
            out.append(_cap_at_start("".join(out), len("".join(out)), r))
            last = m.end()
        out.append(s[last:])
        return "".join(out)
    y = sub(re.compile(_AS_WALK.pattern + _DET_AFTER, re.I), "around", x)       # "as you walk here the market" -> "around the market"
    y = sub(_AS_WALK, "here", y)
    y = sub(_AS_WALK2, "around", y)
    y = sub(_WALK_AROUND, "look around", y)
    y = re.sub(r"\s+,", ",", re.sub(r"(?i)\b(here|around)\s+\1\b", r"\1", y))
    if y != x and y[:1].islower():
        y = y[0].upper() + y[1:]
    return y


def fix_mode_words(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text or not is_driving(tour_text):
        return tour_text
    try:
        import leftovers_906f as f

        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                y = _mode_fix(x)
                if y != x:
                    emit(f'  {TAG} Stop {st["num"]}: walking word on a driving tour: "{x[:70]}" -> "{y[:70]}"')
                    edits[(i, j)] = [y]
            return edits
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} mode-word guard skipped (non-fatal): {err}")
        return tour_text


# ══ 7. conflicting numbers ═══════════════════════════════════════════════════════════════════════════════
_UNIT_M = {"m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0, "km": 1000.0, "kilometer": 1000.0,
           "kilometers": 1000.0, "kilometre": 1000.0, "kilometres": 1000.0, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048}
_DIM = {"long": "length", "length": "length", "high": "height", "tall": "height", "height": "height", "wide": "width",
        "width": "width", "deep": "depth", "depth": "depth"}
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_MEAS_A = re.compile(r"(?i)\b(?P<n>" + _NUM + r")(?P<sep>\s*-?\s*)(?P<u>kilometres?|kilometers?|metres?|meters?|km|feet|foot|ft|m)\b"
                     r"(?P<sep2>\s*-?\s*)(?P<d>long|high|tall|wide|deep)\b")
_MEAS_B = re.compile(r"(?i)\b(?P<d>height|length|width|depth)\s+of\s+(?:about\s+|around\s+|some\s+|nearly\s+)?(?P<n>" + _NUM +
                     r")(?P<sep>\s*-?\s*)(?P<u>kilometres?|kilometers?|metres?|meters?|km|feet|foot|ft|m)\b")


def _tonum(s: str) -> float:
    return float(s.replace(",", ""))


def measures(text: str) -> List[Dict]:
    out: List[Dict] = []
    for rx in (_MEAS_A, _MEAS_B):
        for m in rx.finditer(text or ""):
            u = m.group("u").lower()
            if u not in _UNIT_M:
                continue
            out.append({"dim": _DIM[m.group("d").lower()], "m": _tonum(m.group("n")) * _UNIT_M[u], "span": (m.start(), m.end()),
                        "raw": m.group(0), "num": m.group("n"), "unit": m.group("u")})
    return sorted(out, key=lambda z: z["span"][0])


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 0.05 * max(a, b, 1e-9)


def _article_text(ev: str, title: str, entries: List[Dict]) -> Tuple[str, str]:
    """(article text, web text) of the stop's evidence."""
    art, web = [], []
    for en in entries or []:
        (art if en.get("kind") in ("article", "user-article") else web).append(en.get("text", ""))
    if not art and not web:
        try:
            import key_fact_coverage as kfc
            own = " ".join(kfc.own_prose_sentences(ev or "", title))
        except Exception:  # pragma: no cover
            own = ""
        art = [own] if own else []
        web = [ev or ""]
    return " ".join(art), " ".join(web)


def resolve_measure_conflicts(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                              log: Optional[Callable] = None) -> str:
    """A body measure ("11 meters high") whose stop evidence holds ANOTHER value for the same dimension ("7 meters high"):
    the article's value wins (the number is rewritten); with no article value and web values that disagree the measure is
    omitted (the clause, else the sentence). Logged."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import leftovers_906f as f
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text

        def fn(st: Dict, _all: List[Dict]):
            title = st["title"]
            ev = rc._ev_for(ev_map, title) or ""
            if not ev.strip():
                return {}
            art, web = _article_text(ev, title, c._entries_for(title))
            a_by, w_by = {}, {}
            for mm in measures(art):
                a_by.setdefault(mm["dim"], []).append(mm)
            for mm in measures(web + " " + art):
                w_by.setdefault(mm["dim"], []).append(mm)
            edits = {}
            for i, j, x in st["flat"]:
                new, changed = x, False
                for mm in reversed(measures(x)):
                    dim = mm["dim"]
                    av = a_by.get(dim, [])
                    wv = w_by.get(dim, [])
                    if any(_same(mm["m"], v["m"]) for v in av):
                        continue
                    def _distinct(vs):
                        out_ = []
                        for v in vs:
                            if not any(_same(v["m"], d["m"]) for d in out_):
                                out_.append(v)
                        return out_
                    if av and len(_distinct(av)) == 1:
                        v = av[0]
                        s, e = mm["span"]
                        emit(f'  {TAG} Stop {st["num"]}: conflicting {dim} ({mm["raw"]} vs {v["raw"]}): the article value is used')
                        new = new[:s] + v["raw"] + new[e:]
                        changed = True
                        continue
                    if not av and len(_distinct(wv)) < 2:
                        continue                  # no disagreement (or no evidence value at all): not this guard's business
                    # omitted: the measure's clause (", and 11 meters high"), else the sentence
                    s, e = mm["span"]
                    cut = re.sub(r"(?i)\s*(?:,\s*)?(?:and|but)\s+$", "", new[:s])
                    tail = new[e:]
                    if re.search(r"(?i)\b(?:and|but)\s*$", new[:s]) and cut.strip() and len(cut.split()) >= 5:
                        new = cut.rstrip(" ,") + tail.lstrip(" ,") if tail.strip(" .") == "" else cut.rstrip(" ,") + tail
                        emit(f'  {TAG} Stop {st["num"]}: {dim} measure {mm["raw"]} disagrees across web pages only -> omitted')
                        changed = True
                    else:
                        emit(f'  {TAG} Stop {st["num"]}: {dim} measure {mm["raw"]} disagrees across web pages only -> '
                             f'sentence dropped: "{x[:70]}"')
                        new, changed = "", True
                        break
                if changed:
                    new = new.strip()
                    if new and new[-1:] not in ".!?":
                        new += "."
                    edits[(i, j)] = [new] if new else []
            return edits
        return f._each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} measure-conflict guard skipped (non-fatal): {err}")
        return tour_text


def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    t = fix_mode_words(tour_text, log)
    t = resolve_measure_conflicts(t, evidence_by_title, log)
    return t
