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


_LANDFORMS = {"beach": "beach", "beaches": "beach", "island": "island", "islands": "island", "lake": "lake", "lakes": "lake",
              "bay": "bay", "bays": "bay", "desert": "desert", "dune": "dune", "dunes": "dune", "lagoon": "lagoon",
              "waterfall": "waterfall", "waterfalls": "waterfall", "canyon": "canyon", "seaside": "seaside"}


def foreign_landform(cand: str, title: str, type_text: str = "") -> Optional[str]:
    """[LOCAL-906U] The landform a sentence names when the stop is not one (its title and type name none of them) and the sentence does
    not name the stop either. \"Wander the beautiful beaches in this relaxing area.\" on a mountain pagoda: 'beach'."""
    own = {_LANDFORMS.get(w, w) for w in rc._words(re.sub(r"[<>]", " ", (title or "") + " " + (type_text or "")))}
    words = rc._words(cand or "")
    named = {_LANDFORMS[w] for w in words if w in _LANDFORMS}
    named -= own
    if not named:
        return None
    toks = _title_tokens(title, "")
    stem = {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words}
    if toks & stem:
        return None                                  # the sentence is about the stop and mentions its setting
    return sorted(named)[0]


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
    try:   # [LOCAL-906P] an image caption / a list stub is never a refill
        import owner_junk_906p as _o
        _why = _o.junk_reason(x)
        if _why:
            return _why
    except Exception:  # pragma: no cover
        pass
    try:   # [LOCAL-906S] a sentence in another language is never a refill (a local-language encyclopedia lead)
        import language_dest_906s as _s906s
        _lang = _s906s.foreign_language(x)
        if _lang and (tour_text is None or _s906s.tour_is_english(tour_text)):
            return f"sentence in another language ({_lang})"
        if _s906s.caption_variant(x) or _s906s.variant_reason(x) or _s906s.fragment_reason(x) or _s906s.is_connects_filler(x):
            return "caption / operator / fragment / filler copy"
        import stub_promo_906t as _t906t      # [LEAD wave 59] a refill never brings back what 906T dropped
        _pr = _t906t.promo_reason(x)
        if _pr:
            return f"promo ({_pr})"
    except Exception:  # pragma: no cover
        pass
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
    # [LOCAL-906U] a sentence of the stop's own evidence is keyed to it already, EXCEPT one that names a landform the stop is not
    # (beaches on a mountain pagoda): that is off-topic on every path.
    if not own_evidence and not about_stop(x, title, type_text):
        return "not about this stop"
    lf = foreign_landform(x, title, type_text)
    if lf:
        return f"not about this stop (names a landform the stop is not: {lf})"
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


# [LOCAL-906P] An ELEVATION ("563 meters above sea level", "At the summit, 563 meters", "rises 563 meters") is the height of
# the PLACE above the sea, never the height / length of a structure on it.
_ELEV_AFTER = re.compile(r"(?i)^[\s,)]{0,3}(?:(?:above|over)\s+(?:the\s+)?(?:mean\s+)?(?:sea|ocean|level)|a\.?s\.?l\b|amsl|"
                         r"in\s+(?:elevation|altitude)\b|of\s+(?:elevation|altitude)\b)")
_ELEV_BEFORE = re.compile(r"(?i)(?:\b(?:elevation|altitude|summit|peak|top|crest|apex|highest\s+point)(?:['’]s)?\s*(?:of|is|at|reaches|stands\s+at|:|,|-|–)?\s*"
                          r"(?:the\s+|a\s+|an\s+)?(?:about\s+|around\s+|some\s+|nearly\s+|approximately\s+)?"
                          r"|\b(?:rises?|rising|climbs?|reaches|reach|soars?)\s+(?:up\s+)?(?:to\s+)?(?:about\s+|around\s+|some\s+|nearly\s+)?)$")


def is_elevation(text: str, start: int, end: int) -> bool:
    """[LOCAL-906P] The number at ``text[start:end]`` is an elevation (above sea level / altitude / summit height / "rises N")."""
    t = text or ""
    return bool(_ELEV_AFTER.search(t[end:end + 40]) or _ELEV_BEFORE.search(t[max(0, start - 60):start]))


def measures(text: str, keep_elevation: bool = False) -> List[Dict]:
    """Length / height / width / depth measures of ``text``. [LOCAL-906P] An elevation is not one (``keep_elevation`` keeps it)."""
    out: List[Dict] = []
    for rx in (_MEAS_A, _MEAS_B):
        for m in rx.finditer(text or ""):
            u = m.group("u").lower()
            if u not in _UNIT_M:
                continue
            if not keep_elevation and is_elevation(text, m.start(), m.end()):
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


def _object_words(x: str) -> set:
    """Content words of a sentence that name WHAT is measured (statue, reclining, buddha ...)."""
    stop = set("the a an and of in on at is are was were with this that which it its to for from by as has have had be "
               "long high tall wide deep meters metres meter metre feet foot km you see here there can one about around "
               "stretching measuring reaching standing behind main hall".split())
    return {w for w in re.findall(r"[a-z]{4,}", (x or "").lower()) if w not in stop}


def other_stops_article_values(st_title: str, sentence: str, dim: str, all_: List[Dict], ev_map: Dict,
                               min_shared: int = 2) -> List[Dict]:
    """[LOCAL-906O] This stop's evidence holds no article value for the dimension: the tour's OTHER stops' ARTICLE evidence
    about the same object (a sentence sharing >= ``min_shared`` object words with the sentence, same dimension)."""
    mine = _object_words(sentence)
    out: List[Dict] = []
    for o in all_:
        t = o.get("title", "")
        if t == st_title:
            continue
        ev = rc._ev_for(ev_map, t) or ""
        if not ev.strip():
            continue
        art, _web = _article_text(ev, t, c._entries_for(t))
        for sent in rc.split_sentences(art):
            if len(mine & _object_words(sent)) < min_shared:
                continue
            out.extend(mm for mm in measures(sent) if mm["dim"] == dim)
    return out


# [LOCAL-906P] A value is a measure of an object ONLY when the evidence sentence ties it to the same object noun.
_OBJ_NOUNS = frozenset("statue buddha tower bridge building pagoda temple church cathedral monument lighthouse mountain hill "
                       "peak mount castle wall gate palace dome spire column obelisk sculpture cave lake river waterfall fall dam "
                       "stadium arch tunnel hall cable gondola funicular island beach".split())
_BAD_SPLICE = re.compile(r"(?i)(?P<lead>,?\s*)\b(?:which|that)\s+(?:is|are|was|were)\s+(?:the\s+)?(?:height|length|width|depth)\s+of\s+"
                         r"(?:about\s+|around\s+|some\s+|nearly\s+)?(?:" + _NUM + r")\s*-?\s*(?:kilometres?|kilometers?|metres?|meters?|km|feet|foot|ft|m)\b"
                         r"(?P<tail>\s+and\s+)?")


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def object_nouns(x: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z]+", (x or "").lower()) if _stem(w) in _OBJ_NOUNS or w in _OBJ_NOUNS}


def tied_to_object(body_sentence: str, ev_sentence: str, title: str = "") -> bool:
    """[LOCAL-906P] The evidence sentence's value is about the object the body sentence measures: they share an object noun
    (statue / tower / bridge ...); an evidence sentence with no object noun of its own is tied through the stop's title. A body
    sentence that names no object noun cannot be tied to anything else, so nothing blocks it."""
    b = object_nouns(body_sentence)
    if not b:
        return True
    e = object_nouns(ev_sentence)
    if not e:
        e = object_nouns(title)
    return bool(b & e)


def sentence_measures(text: str) -> List[Dict]:
    """``measures`` of every sentence of ``text`` (elevations excluded), each carrying its sentence under ``sent``."""
    out: List[Dict] = []
    for sent in rc.split_sentences(text or ""):
        for mm in measures(sent):
            mm = dict(mm)
            mm["sent"] = sent
            out.append(mm)
    return out


_HYPHEN_UNIT = {"meters": "meter", "metres": "metre", "kilometers": "kilometer", "kilometres": "kilometre", "feet": "foot"}


def rewrite_measure(mm: Dict, v: Dict) -> str:
    """[LOCAL-906P] ``mm["raw"]`` with ONLY its number and unit replaced by ``v``'s: the body keeps its own wording
    ("7 meters high", "49-meter-long"); a raw evidence phrase ("height of 563 meters") is never spliced into a sentence."""
    raw = mm["raw"]
    unit = v["unit"]
    if "-" in raw:
        unit = _HYPHEN_UNIT.get(unit.lower(), unit)
    elif unit.lower() in _HYPHEN_UNIT.values() and v["num"] != "1":
        unit = {b: a for a, b in _HYPHEN_UNIT.items()}.get(unit.lower(), unit)
    out = raw.replace(mm["num"], v["num"], 1)
    return re.sub(r"(?i)(?<=[\d\s\-])" + re.escape(mm["unit"]) + r"(?=[\s\-]|$)", lambda _m: unit, out, count=1)


def fix_bad_splice(x: str) -> Tuple[str, bool]:
    """"..., which is height of 563 meters and one of the largest ..." (a measure noun spliced in as raw text): the clause is cut
    and the sentence stays grammatical ("..., which is one of the largest ...")."""
    m = _BAD_SPLICE.search(x)
    if not m:
        return x, False
    if m.group("tail"):
        verb = re.search(r"(?i)\b(?:which|that)\s+(?:is|are|was|were)\b", m.group(0)).group(0)
        new = x[:m.start()] + (m.group("lead") or "") + verb + " " + x[m.end():]
    else:
        new = x[:m.start()] + x[m.end():]
    new = re.sub(r"\s+([,.])", r"\1", new).strip()
    return new, True


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
            a_all = sentence_measures(art)                       # [LOCAL-906P] elevations are not measures
            w_all = sentence_measures(web + " " + art)
            edits = {}
            for i, j, x in st["flat"]:
                new, changed = x, False
                fixed, did = fix_bad_splice(new)
                if did:
                    emit(f'  [LOCAL-906P] Stop {st["num"]}: measure noun spliced as raw text ("height of N ...") -> clause cut: "{x[:80]}"')
                    new, changed = fixed, True
                for mm in reversed(measures(new)):
                    dim = mm["dim"]
                    av = [v for v in a_all if v["dim"] == dim and tied_to_object(new, v["sent"], title)]
                    wv = [v for v in w_all if v["dim"] == dim and tied_to_object(new, v["sent"], title)]
                    if any(_same(mm["m"], v["m"]) for v in av):
                        continue
                    def _distinct(vs):
                        out_ = []
                        for v in vs:
                            if not any(_same(v["m"], d["m"]) for d in out_):
                                out_.append(v)
                        return out_
                    if not av:       # [LOCAL-906O] no article value here: the same object's article value elsewhere in the tour
                        fb = _distinct(other_stops_article_values(title, x, dim, _all, ev_map))
                        if len(fb) == 1 and not any(_same(mm["m"], v["m"]) for v in fb):
                            av = fb
                            emit(f'  [LOCAL-906O] Stop {st["num"]}: no article value for the {dim} in its own evidence; '
                                 f'the same object\'s article value from another stop is used')
                    if av and len(_distinct(av)) == 1:
                        v = av[0]
                        s, e = mm["span"]
                        emit(f'  {TAG} Stop {st["num"]}: conflicting {dim} ({mm["raw"]} vs {v["raw"]}): the article value is used')
                        new = new[:s] + rewrite_measure(mm, v) + new[e:]
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
