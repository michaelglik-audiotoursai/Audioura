"""[LOCAL-906T] Delivery guards from the LEAD Mac proofs of 906S (the "<Origin> to <Mountain>" drive, 551, 552). Pure, free, never raises.
Generic names only (D769).

1. stub tail          -- a stop body never ends with a fragment that has no final punctuation or no verb ("... deities. This site").
2. ticket / price     -- any price, ticket, admission or entry-fee sentence goes, in every variant.
3. operator listing   -- "Visit historic <A>, <B> and <C> by cable car with a dedicated English-speaking guide." / "with a private guide".
4. filler             -- "Visitors from all over the world come here to ...".
5. closing variant    -- "Exploring these sites allows you to ...", "... creating lasting memories" (also in 906S ``_VARIANTS``).
6. unhedged record    -- "the longest reclining Buddha statue in Asia" when the job's evidence hedges it ("one of the largest ... in <Region>"),
                         or says it "was the longest ... up to <year>": hedged. Checked against the evidence of EVERY stop of the job, and on a
                         stop with no evidence at all. Comparatives ("even bigger than those at <X>", "surpassing the statues in <Y>") need an
                         evidence sentence that states the comparison with that name.
7. neighbour's fact   -- "Nearby, you can take a cable car up <Another Stop>..." names another stop of the tour: dropped.
8. direction conflict -- "28 kilometers south of <City>" against the stop's pin: a bearing more than 60 degrees off is dropped.
9. coarse pin         -- ``fix_coarse_pins``: a pin rounded to 1-2 decimals is replaced from a named-place geocode (the title, else the hill /
                         mountain / island the body names), logged with its source.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906T]"


def _emit(log: Optional[Callable]) -> Callable:
    return log if callable(log) else (lambda *_a, **_k: None)


# ══ 1. a stub at the end of a body ═══════════════════════════════════════════════════════════════════════
_WORD = re.compile(r"[^\W\d_][\w'’\-]*", re.UNICODE)
_SHORT_VERBS = frozenset("is are was were be been has have had do does did can could will would may might must shall should".split())


def _has_verb(x: str) -> bool:
    words = [w.lower() for w in _WORD.findall(x or "")]
    if any(w in _SHORT_VERBS or w in rc._VERBS_906B for w in words):
        return True
    try:
        import language_dest_906s as _s
        if _s._FINITE.search(x or ""):
            return True
    except Exception:  # pragma: no cover
        pass
    return any(len(w) > 4 and (w.endswith("ed") or w.endswith("ing")) for w in words) or \
        any(i > 0 and len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) for i, w in enumerate(words))


def stub_reason(x: str) -> Optional[str]:
    """Why ``x`` (the LAST sentence of a body) is a stub, or None. A stub has no final punctuation and is short or verbless, or is
    a verbless run of three words or fewer even with its full stop."""
    s = (x or "").strip()
    if not s:
        return None
    words = _WORD.findall(s)
    final = s[-1] in ".!?\"”)’'"
    verb = _has_verb(s)
    if not final:
        if len(words) < 5:
            return "no final punctuation and fewer than five words"
        if not verb:
            return "no final punctuation and no verb"
        if rc.is_fragment(s + "."):
            return "no final punctuation and not a whole sentence"
        return None
    if len(words) <= 3 and not verb:
        return "a verbless run of three words or fewer"
    return None


def drop_stub_tails(tour_text: str, log: Optional[Callable] = None) -> str:
    """Final delivery guard: the last sentence of a stop body goes when it is a stub (logged). A body is never emptied."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import splice_copy_906r as sp

        def fn(st: Dict, tg):
            body = [(i, tg[i][1]) for i in sorted(tg) if not tg[i][0]]
            if not body:
                return {}
            i, sents = body[-1]
            if len(sents) < 1 or sp._total(tg) < 2:
                return {}
            why = stub_reason(sents[-1])
            if not why:
                last = sents[-1].strip()
                if last and last[-1] not in ".!?\"”)’'":      # a whole sentence that only lost its full stop gets it back
                    emit(f'  {TAG} Stop {st["num"]}: full stop restored: "{last[:80]}"')
                    return {(i, len(sents) - 1): [last + "."]}
                return {}
            emit(f'  {TAG} Stop {st["num"]}: stub tail dropped ({why}): "{sents[-1][:80]}"')
            return {(i, len(sents) - 1): []}
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} stub-tail guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2-5. promo, listing, filler, closing ═════════════════════════════════════════════════════════════════
_PROMO = [(re.compile(p), why) for p, why in (
    (r"(?i)\b(?:buy|buying|purchase|purchasing|book|booking|reserve)\s+(?:your\s+|their\s+|the\s+)?(?:\w+\s+)?tickets?\b", "ticket sales copy"),
    (r"(?i)\btickets?\b", "ticket copy"),
    (r"(?i)\b(?:prices?|fares?|fees?|costs?)\b[^.!?]{0,40}\b(?:around|about|approximately|from|start(?:s|ing)?\s+at|of|is|are|range[sd]?|run|runs)\b[^.!?]{0,30}"
     r"(?:\$|€|£|USD|VND|dong|euros?|dollars?|\d)", "price copy"),
    (r"(?i)\bprices?\s+(?:around|are|is|start|range|vary|from|of)\b", "price copy"),
    (r"(?i)(?:[$€£]\s?\d|\b\d[\d.,]*\s?(?:usd|vnd|dollars?|euros?|dong(?!(?-i:\s+[A-Z])))\b)", "a price"),
    (r"(?i)\bfor\s+(?:entry|admission)\b|\b(?:entry|admission|entrance)\s+(?:fees?|prices?|costs?|charges?)\b|\badmission\b|\bentry\s+is\s+(?:free|\$)", "entry-fee copy"),
    (r"(?i)^visit\b[^.!?]*,[^.!?]*\band\b", "an imperative tour listing"),
    (r"(?i)^visit\s+(?:historic|famous|the|ancient|beautiful)\b[^.!?]{0,120}\b(?:by|with|via)\b", "an imperative tour listing"),
    (r"(?i)\bwith\s+an?\s+(?:[\w\-]+\s+){0,3}?(?:dedicated|private|English-speaking|professional|licensed|expert)\s+(?:[\w\-]+\s+){0,2}?guides?\b", "operator copy (guide)"),
    (r"(?i)\b(?:visitors|tourists|travell?ers|people|pilgrims|guests)\s+from\s+(?:all\s+over|around|across)\s+the\s+(?:world|globe)\b", "filler (from all over the world)"),
    (r"(?i)\bfrom\s+all\s+over\s+the\s+(?:world|globe)\b[^.!?]{0,40}\b(?:come|comes|visit|flock|travel|gather|arrive)\b", "filler (from all over the world)"),
    (r"(?i)^(?:exploring|visiting|seeing|discovering|experiencing)\s+(?:these|all\s+(?:of\s+)?these|the|all\s+the)\s+(?:sites|stops|places|spots|landmarks|locations|attractions)\b"
     r"[^.!?]{0,20}\b(?:allows?|lets?|helps?|gives?|offers?|enables?)\s+you\b", "template closing"),
    (r"(?i)\bcreating\s+(?:lasting|unforgettable|lifelong|lifetime|wonderful|precious)\s+memories\b", "template closing"),
    (r"(?i)^by\s+(?:exploring|visiting|seeing|discovering)\s+(?:these|all\s+(?:of\s+)?these|all\s+the)\b[^.!?]{0,80}?,?\s*you\s+(?:will\s+|can\s+)?(?:gain|get|discover|learn)\b", "template closing"),   # [LOCAL-906W]
    (r"(?i)\b(?:connect|connecting)\s+with\s+the\s+(?:region|area|country|city|town|island)[’']?s\s+(?:heritage|culture|history)\b", "template closing"),
)]


def promo_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    for rx, why in _PROMO:
        if rx.search(s):
            return why
    return None


# ══ 6. records and comparatives against ALL the evidence ═════════════════════════════════════════════════
_TEMPORAL = re.compile(r"(?i)\b(?:was|were|had\s+been|formerly|previously|once)\s+(?:the\s+)?(?:\w+\s+)?(?:largest|biggest|longest|tallest|highest|oldest|greatest)\b"
                       r"[^.!?]{0,80}?\b(?:up\s+to|until|till|before|prior\s+to|through)\s+(?:the\s+(?:year\s+)?)?\d{4}")
_CMP_CUE = re.compile(r"(?i)\b(?:(?:larger|bigger|taller|longer|older|higher|greater|wider|deeper)\s+than|surpass(?:es|ing|ed)?|exceed(?:s|ing|ed)?|"
                      r"outdo(?:es|ing)?|outsiz(?:es|ing|ed)|dwarf(?:s|ing|ed)?|eclips(?:es|ing|ed)|beat(?:s|ing)?|overtak(?:es|ing)|rival(?:s|ing|led)?)\b")
_CAPS = re.compile(r"\b[A-ZÀ-Ỹ][^\W\d_]{2,}(?:\s+[A-ZÀ-Ỹ][^\W\d_]{2,})*")


def _object_tokens(claim: Dict, title: str) -> set:
    return {t for t in claim.get("toks", set())} - set(rc._content_tokens(title))


def _evidence_sentences(ev: str) -> List[str]:
    return rc.split_sentences(ev or "")


def contested_record(x: str, st_title: str, ev_own: str, ev_other: Dict[str, str]) -> Optional[str]:
    """Why the unhedged size record in ``x`` is contested by the job's evidence ("hedge" / "temporal"), else None."""
    cl = c.scoped_claim(x)
    if not cl or cl["hedged"] or cl["cls"] not in c._SIZE_CLASSES or c._local_scope(cl, st_title):
        return None
    obj = _object_tokens(cl, st_title) | set(rc._content_tokens(st_title))
    pools = [(ev_own, True)] + [(v, False) for v in ev_other.values()]
    for text, own in pools:
        for es in _evidence_sentences(text):
            same_object = own or bool(obj & set(rc._content_tokens(es)))
            if not same_object:
                continue
            if _TEMPORAL.search(es):
                return "temporal"
            for e in c.scoped_claims(es, include_hedged=True):
                if e["hedged"] and c.cls_eq(e["cls"], cl["cls"]) and (own or obj & (set(e["toks"]) | set(rc._content_tokens(es)))):
                    return "hedge"
    return None


def narrower_scope(x: str, st_title: str, ev_own: str, ev_other: Dict[str, str]) -> Optional[str]:
    """[LOCAL-906W] The scope an evidence sentence of the job states for the SAME superlative (same size class, same object) when it is
    narrower than the one ``x`` claims (\"the longest ... in Asia\" against \"the longest ... in Southeast Asia\"). Two sources that disagree on
    a record's scope do not back the wider claim, hedged or not. None when no evidence does, or the claim is the stop's own venue."""
    cl = c.scoped_claim(x)
    if not cl or cl["hedged"] or cl["cls"] not in c._SIZE_CLASSES or c._local_scope(cl, st_title) or cl["rank"] is None:
        return None
    obj = _object_tokens(cl, st_title) | set(rc._content_tokens(st_title))
    best: Optional[Dict] = None
    for text, own in [(ev_own, True)] + [(v, False) for v in ev_other.values()]:
        for es in _evidence_sentences(text):
            if not (own or obj & set(rc._content_tokens(es))):
                continue
            for e in c.scoped_claims(es, include_hedged=True):
                if not c.cls_eq(e["cls"], cl["cls"]) or e["rank"] is None or e["rank"] >= cl["rank"] or not e["scope"]:
                    continue
                if not (set(e["toks"]) & set(cl["toks"]) or (obj & (set(e["toks"]) | set(rc._content_tokens(es))))):
                    continue
                if best is None or e["rank"] > best["rank"]:
                    best = e
    return best["scope"] if best else None


def comparative_unsupported(x: str, ev_own: str, ev_all: Sequence[str]) -> Optional[str]:
    """The named place a comparative sentence measures against, when no evidence sentence states that comparison."""
    m = _CMP_CUE.search(x or "")
    if not m:
        return None
    names = [n for n in _CAPS.findall(x[m.end():])]
    if not names:
        return None
    pools = [ev_own] + list(ev_all)
    for text in pools:
        for es in _evidence_sentences(text):
            if _CMP_CUE.search(es):
                f = rc.fold(es)
                if any(re.search(r"\b" + re.escape(rc.fold(n)) + r"\b", f) for n in names):
                    return None
    return names[0]


def _record_judgement(x: str, st: Dict, ctx: Dict) -> Optional[Tuple[str, str, str]]:
    ev_own = ctx["ev"].get(st["num"], "")
    cmp_name = comparative_unsupported(x, ev_own, [v for v in ctx["ev_all"].values() if v != ev_own])
    if cmp_name:
        return "drop", "", f"comparison with '{cmp_name}' that no evidence states"
    other = {k: v for k, v in ctx["ev_all"].items() if v != ev_own}      # the evidence of EVERY entry of the job, tour stop or not
    why = contested_record(x, st["title"], ev_own, other)
    nsc = narrower_scope(x, st["title"], ev_own, other)        # [LOCAL-906W] the job's evidence states it for a narrower scope
    if why or nsc:
        new = c._hedge_text(x)
        if new and nsc and not why:       # a hedge in the evidence keeps the claim's own scope (906T); only a narrower, unhedged statement narrows it
            cl0 = c.scoped_claim(x)
            sc0 = (cl0 or {}).get("scope") or ""
            if sc0 and rc.fold(sc0) != rc.fold(nsc):
                new = re.sub(r"(?<![\w-])" + re.escape(sc0) + r"(?![\w-])", nsc, new, count=1)
        if new and new != x:
            return "replace", new, (f"record contested by the evidence ({why or 'narrower scope: ' + str(nsc)}) -> hedged"
                                    + (f" for {nsc}" if nsc else ""))
        return "drop", "", f"record contested by the evidence ({why or 'narrower scope: ' + str(nsc)})"
    cl = c.scoped_claim(x)
    if cl and not cl["hedged"] and cl["cls"] in c._SIZE_CLASSES and not c._local_scope(cl, st["title"]) \
            and not ctx["any_ev"] and cl["rank"] is not None and cl["rank"] >= 3:
        new = c._hedge_text(x)
        if new and new != x:
            return "replace", new, "record claim with no evidence anywhere in the job -> hedged"
    return None


# ══ 7. a neighbour stop's fact on this stop ══════════════════════════════════════════════════════════════
_NEARBY = re.compile(r"(?i)^(?:nearby|close\s+by|not\s+far\s+(?:from\s+here|away)|just\s+(?:down|up)\s+the\s+(?:road|coast|way))\s*,?\s+(?:you\s+(?:can|could|may|will)|visitors\s+can|travell?ers\s+can)\b")
_GENERIC = frozenset("the a an of and in at on to for from with by mountain mount hill hills beach lake river island islands cave falls waterfall lighthouse tower towers "
                     "temple temples pagoda pagodas church cathedral museum market village town city park garden bridge fort fortress castle palace "
                     "view views summit peak valley forest bay coast road drive ride walk arrival arriving stop site old new great grand national".split())


def _core_tokens(title: str) -> List[str]:
    t = re.split(r"\s+[–—-]\s+", title or "")[0]
    return [w for w in (rc.fold(w) for w in _WORD.findall(t)) if w and w not in _GENERIC and len(w) > 1]


def names_other_stop(x: str, st: Dict, titles: Dict[int, str]) -> Optional[str]:
    f = rc.fold(x)
    own = set(_core_tokens(st["title"]))
    for num, title in titles.items():
        if num == st["num"]:
            continue
        core = _core_tokens(title)
        if not core or set(core) <= own:
            continue
        if all(re.search(r"\b" + re.escape(w) + r"\b", f) for w in core):
            return title
    return None


# ══ 8. a bearing that contradicts the pin ═════════════════════════════════════════════════════════════════
_DIRS = {"north": 0, "northeast": 45, "east": 90, "southeast": 135, "south": 180, "southwest": 225, "west": 270, "northwest": 315,
         "north-east": 45, "south-east": 135, "south-west": 225, "north-west": 315}
_BEARING = re.compile(r"(?i)\b(?:about|around|roughly|approximately|just|only|some)?\s*(?:\d+(?:\.\d+)?|[a-z\-]+)\s*(?:kilomet(?:er|re)s?|km|miles?)\s+"
                      r"(?P<d>north-?east|north-?west|south-?east|south-?west|north|south|east|west)(?:ward)?\s+of\s+(?:the\s+)?"
                      r"(?P<c>[A-ZÀ-Ỹ][\w'’\-]*(?:\s+[A-ZÀ-Ỹ][\w'’\-]*){0,3})")
_COORD_LINE = re.compile(r"(?mi)^\s*Coordinates\s*:\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)")
_CITY_CENTERS: Dict[str, Tuple[float, float]] = {}


def set_city_centers(centers: Optional[Dict[str, Tuple[float, float]]]) -> None:
    """The caller's {city name: (lat, lng)} (the pipeline's own place references); read by ``drop_bearing_conflicts``."""
    _CITY_CENTERS.clear()
    for k, v in (centers or {}).items():
        try:
            _CITY_CENTERS[rc.fold(k)] = (float(v[0]), float(v[1]))
        except Exception:
            continue


def bearing_deg(frm: Tuple[float, float], to: Tuple[float, float]) -> float:
    la1, la2 = math.radians(frm[0]), math.radians(to[0])
    dl = math.radians(to[1] - frm[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _angle_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def bearing_conflict(x: str, pin: Optional[Tuple[float, float]], centers: Dict[str, Tuple[float, float]],
                     limit: float = 60.0) -> Optional[str]:
    """The sentence's compass bearing "<N> km <dir> of <City>" vs the bearing City -> pin; a gap above ``limit`` degrees names the conflict."""
    if not pin:
        return None
    m = _BEARING.search(x or "")
    if not m:
        return None
    city = rc.fold(m.group("c"))
    ctr = centers.get(city)
    if ctr is None:
        for k, v in centers.items():
            if k and (k in city or city in k):
                ctr = v
                break
    if ctr is None or (abs(ctr[0] - pin[0]) < 1e-4 and abs(ctr[1] - pin[1]) < 1e-4):
        return None
    said = _DIRS.get(m.group("d").lower().replace("-", ""))
    if said is None:
        return None
    actual = bearing_deg(ctr, pin)
    gap = _angle_gap(said, actual)
    return f"says {m.group('d').lower()} of {m.group('c')}, the pin lies at {actual:.0f} degrees ({gap:.0f} off)" if gap > limit else None


def _stop_pin(st: Dict) -> Optional[Tuple[float, float]]:
    m = _COORD_LINE.search("\n".join(st["lines"]))
    return (float(m.group(1)), float(m.group(2))) if m else None


# ══ the sentence pass ════════════════════════════════════════════════════════════════════════════════════
def _judge(x: str, st: Dict, ctx: Dict) -> Optional[Tuple[str, str, str]]:
    why = promo_reason(x)
    if why:
        return "hard", "", why
    if _NEARBY.match(x.strip()):
        other = names_other_stop(x, st, ctx["titles"])
        if other:
            return "hard", "", f"a neighbour's fact (names the stop '{other[:40]}')"
    why = bearing_conflict(x, ctx["pins"].get(st["num"]), ctx["centers"])
    if why:
        return "hard", "", f"direction conflicts with the pin ({why})"
    return _record_judgement(x, st, ctx)


def drop_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None,
              centers: Optional[Dict[str, Tuple[float, float]]] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import splice_copy_906r as sp
        ev_map = c._ev_map(evidence_by_title)
        infos = c._stops_info(tour_text)
        ev = {st["num"]: (rc._ev_for(ev_map, st["title"]) or "") for st in infos}
        cen = {rc.fold(k): (float(v[0]), float(v[1])) for k, v in (centers or {}).items()}
        for k, v in _CITY_CENTERS.items():
            cen.setdefault(k, v)
        # a city named by a stop of the tour is located by that stop's pin
        for st in infos:
            p = _stop_pin(st)
            if p:
                for tok in {rc.fold(st["title"]), " ".join(_core_tokens(st["title"]))}:
                    if tok:
                        cen.setdefault(tok, p) if tok not in cen else None
        ctx = {"ev": ev, "ev_all": dict(ev_map), "any_ev": any(v.strip() for v in ev.values()) or bool(ev_map),
               "titles": {st["num"]: st["title"] for st in infos}, "pins": {st["num"]: _stop_pin(st) for st in infos},
               "centers": cen}

        def fn(st: Dict, tg):
            edits, before = {}, ""
            for i in sorted(tg):
                _p, sents = tg[i]
                for j, x in enumerate(sents):
                    got = _judge(x, st, ctx)
                    if not got:
                        before += " " + x
                        continue
                    action, new, why = got
                    if action == "replace":
                        emit(f'  {TAG} Stop {st["num"]}: {why}: "{x[:90]}" -> "{new[:90]}"')
                        edits[(i, j)] = [new]
                    else:
                        emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                        edits[(i, j)] = []
            return edits
        return sp._edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} sentence guard skipped (non-fatal): {err}")
        return tour_text


def drop_closing_promo(tour_text: str, log: Optional[Callable] = None) -> str:
    """The tour's closing lines (after the last stop's body): a promo / template closing sentence goes."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        blocks = rc._stop_blocks(tour_text)
        if not blocks:
            return tour_text
        s, e, _num, _title = blocks[-1]
        lines = tour_text[s:e].split("\n")
        body = set(c._stops_info(tour_text)[-1]["idx"])
        changed = False
        for i, ln in enumerate(lines):
            if i == 0 or not ln.strip() or rc._KEYED.match(ln) or i in body:
                continue
            keep = []
            for x in rc.split_sentences(ln):
                why = None if rc._CLOSING_LINE.match(x) else promo_reason(x)
                if why:
                    emit(f'  {TAG} closing: {why} dropped: "{x[:100]}"')
                    changed = True
                else:
                    keep.append(x)
            lines[i] = " ".join(keep) if keep else None
        if not changed:
            return tour_text
        new = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if not new.endswith("\n") and tour_text[s:e].endswith("\n"):
            new += "\n"
        return tour_text[:s] + new + tour_text[e:]
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} closing guard skipped (non-fatal): {err}")
        return tour_text


def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None,
             centers: Optional[Dict[str, Tuple[float, float]]] = None) -> str:
    t = drop_pass(tour_text, evidence_by_title, log, centers)
    t = drop_closing_promo(t, log)
    return drop_stub_tails(t, log)


# ══ 9. a coarse pin ═══════════════════════════════════════════════════════════════════════════════════════
def _coarse(v: float) -> bool:
    return abs(v * 100.0 - round(v * 100.0)) < 1e-6


def _pin_of(poi: Dict) -> Optional[Tuple[float, float]]:
    try:
        co = poi.get("coordinates")
        if isinstance(co, (list, tuple)) and len(co) >= 2:
            return float(co[0]), float(co[1])
        if isinstance(co, str):
            m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)", co)
            if m:
                return float(m.group(1)), float(m.group(2))
        if poi.get("latitude") is not None and poi.get("longitude") is not None:
            return float(poi["latitude"]), float(poi["longitude"])
    except Exception:
        pass
    return None


_BODY_PLACE = re.compile(r"\b(?:on|at|near|atop|beside|below|above)\s+(?:the\s+)?(?P<n>(?:[A-ZÀ-Ỹ][\w'’\-]*\s+){1,3}(?:Hill|Mountain|Mount|Island|Cape|Peak|Lake|Cliff|Point|Bay))\b"
                        r"|\b(?P<m>(?:Mount|Mt\.?|Cape)\s+[A-ZÀ-Ỹ][\w'’\-]*(?:\s+[A-ZÀ-Ỹ][\w'’\-]*){0,2})\b")


def named_places(poi: Dict) -> List[str]:
    """Names to geocode, best first: the stop name, then the hill / mountain / island its body names."""
    out: List[str] = []
    name = (poi.get("name") or "").strip()
    if name:
        out.append(name)
        short = re.sub(r"(?i)\b(?:cham|ancient|old|historic|the)\s+", "", name).strip()
        if short and short != name:
            out.append(short)
    for m in _BODY_PLACE.finditer(poi.get("description") or ""):
        n = (m.group("n") or m.group("m") or "").strip()
        if n and n not in out:
            out.append(n)
    return out


def fix_coarse_pins(poi_list: List[Dict], candidates_fn: Callable, province: str = "", country: str = "",
                    box: Optional[Sequence[float]] = None, log: Optional[Callable] = None, max_km: float = 80.0) -> List[int]:
    """A stop pin rounded to 1-2 decimals (a city / tour fallback) is replaced when a named-place geocode exists. ``candidates_fn(query)``
    -> [{"lat","lng",...}] (``geocode_stops.geocode_candidates``). A hit is accepted inside ``box`` (when given) and within ``max_km`` of the
    coarse pin. Returns the 0-based indices fixed; logs ``[LOCAL-906T] ... via <source>``."""
    emit = _emit(log)
    fixed: List[int] = []
    for i, poi in enumerate(poi_list or []):
        try:
            pin = _pin_of(poi)
            if pin is None or not (_coarse(pin[0]) and _coarse(pin[1])) or poi.get("_user_pin") or poi.get("user_explicit_pin"):
                continue
            done = False
            for place in named_places(poi):
                for q in ([f"{place}, {province}, {country}"] if province and country else []) + ([f"{place}, {province}"] if province else []) + [place]:
                    hits = candidates_fn(q) or []
                    for h in hits:
                        lat, lng = float(h["lat"]), float(h["lng"])
                        if (_coarse(lat) and _coarse(lng)) or _hav(pin, (lat, lng)) > max_km:
                            continue
                        if box and len(box) >= 4 and not (box[0] <= lat <= box[1] and box[2] <= lng <= box[3]):
                            continue
                        poi["coordinates"] = f"{lat:.6f}, {lng:.6f}"
                        if "latitude" in poi or "longitude" in poi:
                            poi["latitude"], poi["longitude"] = lat, lng
                        poi["coordinates_approximate"] = False
                        poi["_pin_source_906t"] = f"geocode:{q}"
                        poi.pop("_no_coordinate", None)
                        emit(f"  {TAG} stop={i + 1} pin {pin[0]:.4f},{pin[1]:.4f} is a coarse fallback -> {lat:.6f},{lng:.6f} "
                             f"via named-place geocode ({q!r})")
                        fixed.append(i)
                        done = True
                        break
                    if done:
                        break
                if done:
                    break
            if not done:
                emit(f"  {TAG} stop={i + 1} pin {pin[0]:.4f},{pin[1]:.4f} is a coarse fallback; no named-place geocode answered")
        except Exception as err:  # pragma: no cover
            emit(f"  {TAG} coarse-pin fix for stop={i + 1} skipped (non-fatal): {err}")
    return fixed


def _hav(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))
