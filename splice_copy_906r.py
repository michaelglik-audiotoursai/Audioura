"""[LOCAL-906R] Delivery guards from the 906Q Mac proof and the wave 56 cloud report. Pure, free, never raises. Generic names (D769).

* broken measure splice -- "stretching an impressive in length." (a pass took the number and left its phrase). The clause goes
                            (the sentence when the clause is its point). Logged. A stop left thin is refilled (``last_word``).
* day-trip / operator   -- "Many tours recommend ...", "Another choice is a half-day private tour ...", "Drive for around 1.5 hours
                            to <Town>, a coastal town known for ...", "... by private car with air conditioning", "Visitors often
                            combine this stop with ...", "The full tour ... starts at 8:00 a.m. and lasts eight hours.",
                            "You can't visit <City> without ...". A drive distance between stops is kept.
* passive restaurant    -- "Some of the best seafood is served nearby at <Name> restaurant ..." unless the stop IS that venue.
* disclosure            -- the no-history disclosure (and its sensory lead-in) goes when the stop already has >= 2 supported
                            sentences (body + the Orientation line).
* builder spelling      -- the stop's ARTICLE spelling of a person wins (also for the 880 signature story).
* geography boundary    -- "<Ward> lies with the <Sea> to the east, <Ward> and <Commune> to the west ..." is administrative copy.
* cable car numbers     -- a number kept in a cable car sentence must be in an ACCEPTED evidence passage (not a refused snippet).
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906R]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


# ══ stop plumbing: body sentences AND the Orientation line of a stop ═════════════════════════════════════
_ORI = re.compile(r"(?i)^(\s*Orientation\s*:\s*)(.*)$")


def _targets(st: Dict) -> Dict[int, Tuple[str, List[str]]]:
    out: Dict[int, Tuple[str, List[str]]] = {}
    for i in st["idx"]:
        out[i] = ("", rc.split_sentences(st["lines"][i]))
    for i, ln in enumerate(st["lines"]):
        m = _ORI.match(ln)
        if i > 0 and m and m.group(2).strip():
            out[i] = (m.group(1), rc.split_sentences(m.group(2)))
    return out


def _edit(text: str, fn: Callable[[Dict, Dict[int, Tuple[str, List[str]]]], Dict[Tuple[int, int], List[str]]],
          allow_empty_body: bool = False) -> str:
    """``fn(stop, targets)`` -> {(line, pos): replacement sentences ([] = dropped)} for every stop in turn."""
    n = len(c._stops_info(text))
    for k in range(n):
        infos = c._stops_info(text)
        if k >= len(infos):
            break
        st = infos[k]
        tg = _targets(st)
        edits = fn(st, tg)
        if not edits:
            continue
        lines = list(st["lines"])
        for i, (prefix, sents) in tg.items():
            if not any((i, j) in edits for j in range(len(sents))):
                continue
            new: List[str] = []
            for j, x in enumerate(sents):
                new.extend(edits[(i, j)] if (i, j) in edits else [x])
            if new:
                lines[i] = prefix + " ".join(new)
            elif prefix:
                continue                          # an Orientation line is never emptied
            else:
                lines[i] = None
        block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
        if not block.endswith("\n") and text[st["s"]:st["e"]].endswith("\n"):
            block += "\n"
        text = text[:st["s"]] + block + text[st["e"]:]
    return text


def _total(tg: Dict[int, Tuple[str, List[str]]]) -> int:
    return sum(len(s) for _p, s in tg.values())


# ══ 1. a broken measure splice ═══════════════════════════════════════════════════════════════════════════
_NUMWORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
            r"ninety|hundred|thousand|dozen|half)")
_HAS_NUMBER = re.compile(r"\d|(?i:\b" + _NUMWORD + r"\b)")
_ADJ = (r"(?:impressive|remarkable|staggering|towering|enormous|massive|whopping|stunning|total|overall|full|incredible|"
        r"great|considerable|significant|huge|giant|vast|long|tall|high)")
_SPLICE = [re.compile(p) for p in (
    r"(?i)\b(?:an?|the|its|their|this|that)\s+(?:" + _ADJ + r"\s+)?in\s+(?:length|height|width|depth|size|diameter)\b",   # LEAD: only an adjective, never "the largest in size"
    r"(?i)\b(?:total|overall|full)\s+(?:length|height|width|depth)\s+of\s*(?=[,.;!?]|$)",
    r"(?i)\bmeasur(?:ing|es|ed)\s+(?:about\s+|around\s+|nearly\s+|some\s+)?(?:meters|metres|kilometers|kilometres|feet|miles|km)\b",
    r"(?i)\b(?:an?|the)\s+" + _ADJ + r"\s+(?:long|high|tall|wide|deep)\s*(?=[.,;!?]|$)",
    r"(?i)\b(?:is|are|was|were|of|at|about|around|nearly|some)\s+(?:meters|metres|kilometers|kilometres|feet)\s+"
    r"(?:long|high|tall|wide|deep|in\s+length|in\s+height)\b",
    r"(?i)\b(?:stretch\w*|spann?\w*|extend\w*|reach\w*|measur\w*)\s+(?:an?\s+)?" + _ADJ + r"\s*(?=[.,;!?]|$)",
)]


def splice_span(x: str) -> Optional[Tuple[int, int]]:
    """Where a measure was removed from ``x`` without its phrase (``None`` = the sentence is whole)."""
    s = x or ""
    if _HAS_NUMBER.search(s):
        return None
    for rx in _SPLICE:
        m = rx.search(s)
        if m:
            return m.start(), m.end()
    return None


def cut_splice(x: str) -> Optional[str]:
    """The sentence without the clause that carries the broken splice: the clause between the commas around it; None when
    nothing whole is left (the sentence IS the broken clause)."""
    span = splice_span(x)
    if not span:
        return x
    a, b = span
    cut = max(x.rfind(",", 0, a), x.rfind(";", 0, a))
    if cut < 0:
        return None
    nxt = [p for p in (x.find(",", b), x.find(";", b)) if p >= 0]
    head, tail = x[:cut].rstrip(), (x[min(nxt):] if nxt else "")
    tail = re.sub(r"^[,;]\s*(?:and|but)\s+", " and ", tail) if tail else ""
    if tail and re.match(r"^[,;]\s*(?:which|that|stretching|measuring|reaching)\b", tail.strip()):
        tail = ""
    out = (head + tail).strip()
    out = re.sub(r"\s+([,.])", r"\1", out)
    if out[-1:] not in ".!?":
        out += "."
    if len(out.split()) < 5 or rc.is_fragment(out) or splice_span(out):
        return None
    return out


def drop_splice(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            edits, left = {}, _total(tg)
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    if not splice_span(x):
                        continue
                    new = cut_splice(x)
                    if new:
                        emit(f'  {TAG} Stop {st["num"]}: a measure was removed without its phrase -> clause cut: "{x[:90]}"')
                        edits[(i, j)] = [new]
                    elif left > 1:
                        emit(f'  {TAG} Stop {st["num"]}: a measure was removed without its phrase -> sentence dropped: "{x[:90]}"')
                        edits[(i, j)] = []
                        left -= 1
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} splice guard skipped (non-fatal): {err}")
        return tour_text


# ══ 2. day-trip / operator / travel-planning / promo copy ════════════════════════════════════════════════
_OPERATOR_VERB = r"(?:recommend|suggest|include|combine|offer|start|depart|last|visit|stop|run|cover|feature|take)\w*"
_OPERATOR = [re.compile(p) for p in (
    r"(?i)\b(?:many|most|some|several|popular|typical|organi[sz]ed|guided|group|private)\s+(?:[\w\-]+\s+){0,2}?tours\s+(?:[\w\-]+\s+){0,3}?"
    + _OPERATOR_VERB,
    r"(?i)\btours\s+(?:[\w\-]+\s+){0,3}?" + _OPERATOR_VERB + r"\s+(?:visiting|a\s+visit|both|stops?|the\b)",
    r"(?i)\b(?:another|an?\s+alternative|one)\s+(?:choice|option|alternative)\s+is\b",
    r"(?i)\b(?:an?|another)\s+(?:[\w\-]+\s+){0,2}?(?:half|full|one|two|three)-day\s+(?:[\w\-]+\s+){0,2}?(?:tour|trip|excursion)s?\b",
    r"(?i)\bprivate\s+(?:car|tour|transfer|driver|taxi|vehicle)\b",
    r"(?i)\bair[\s\-]+condition(?:ing|ed)\b",
    r"(?i)\b(?:visitors|tourists|travell?ers|people|many)\s+(?:often|usually|commonly|typically|frequently)?\s*"
    r"(?:combine|pair|add)\s+(?:this|it|the)\b",
    r"(?i)\b(?:often|usually|commonly|typically|frequently|also)\s+combine[sd]?\s+(?:this|it|the)\b[^.!?]{0,40}\bwith\b",
    r"(?i)\byou\s+(?:can(?:'|’)?t|cannot|can\s+not|couldn(?:'|’)t|simply\s+can(?:'|’)?t)\s+(?:really\s+|truly\s+)?"
    r"(?:visit|leave|come\s+to|go\s+to)\b[^.!?]{0,60}\bwithout\b",
    r"(?i)^(?:drive|travel|ride|head)\s+(?:for\s+)?(?:around|about|roughly|approximately|nearly)?\s*[\d.]+\s*(?:-\s*\d+\s*)?"
    r"(?:hours?|hrs?|minutes?|mins?)\s+to\s+[^.!?,]{2,50},\s+(?:an?|the)\b[^.!?]{0,80}\b(?:known|famous|popular|town|city|village|beach|resort)\b",
)]
_TOUR_TIME = re.compile(r"(?i)\btours?\b[^.!?]*\b(?:(?:typically\s+|usually\s+|generally\s+)?starts?\s+at\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m|p\.?m)|"
                        r"(?:typically\s+|usually\s+)?lasts?\s+(?:around|about|roughly|approximately|up\s+to)?\s*\w+\s+hours?)")
_CLAUSE_OPERATOR = re.compile(r"(?i)\bprivate\s+(?:car|vehicle|tour)\b|\bair[\s\-]+condition(?:ing|ed)\b")


def operator_reason(x: str) -> Optional[str]:
    s = (x or "").strip()
    if any(rx.search(s) for rx in _OPERATOR) or _TOUR_TIME.search(s):
        return "day-trip / operator / travel-planning copy"
    return None


def _clause_cut(x: str) -> Optional[str]:
    """\"The lighthouse is 45 km from the centre, which takes an hour by private car with air conditioning.\" -> the head only."""
    m = _CLAUSE_OPERATOR.search(x)
    if not m:
        return None
    cut = max(x.rfind(",", 0, m.start()), x.rfind(";", 0, m.start()))
    if cut < 0:
        return None
    head = x[:cut].rstrip()
    if len(head.split()) < 5:
        return None
    out = head + ("." if head[-1:] not in ".!?" else "")
    return out if not rc.is_fragment(out) and not operator_reason(out) else None


def drop_operator(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            edits, left = {}, _total(tg)
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    why = operator_reason(x)
                    if not why:
                        continue
                    new = _clause_cut(x)
                    if new:
                        emit(f'  {TAG} Stop {st["num"]}: {why} -> clause cut: "{x[:90]}"')
                        edits[(i, j)] = [new]
                    elif left > 1:
                        emit(f'  {TAG} Stop {st["num"]}: {why} dropped: "{x[:90]}"')
                        edits[(i, j)] = []
                        left -= 1
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} operator copy guard skipped (non-fatal): {err}")
        return tour_text


# ══ 3. a passive restaurant plug ═════════════════════════════════════════════════════════════════════════
_VENUE = r"(?i:restaurant|caf[eé]|cafe|bar|eatery)"
_RECO = re.compile(r"(?i)\b(?:best|served?|serves?|try|enjoy|delicious|famous\s+for|recommend\w*|must-try|tasty|freshest|specialt(?:y|ies))\b")
_VENUE_NAME = re.compile(r"(?P<n>(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+)(?:\s+(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+|(?i:of|de|la|le|du|and|&))){0,3})\s+"
                         + _VENUE + r"\b")
_GENERIC_N = frozenset("the a an this that some many one another each every our your their its".split())


def passive_plug(x: str, title: str = "") -> bool:
    s = x or ""
    if not _RECO.search(s):
        return False
    if re.search(r"(?i)\b(?:restaurant|caf[eé]|cafe|bar|eatery)\b", title or ""):
        return False
    import route_copy_906q as cp
    for m in _VENUE_NAME.finditer(s):
        toks = [w for w in re.split(r"\s+", m.group("n")) if w.lower() not in _GENERIC_N]
        if not toks:
            continue
        if cp._same_venue(" ".join(toks), title):
            continue
        return True
    return False


def drop_passive_plug(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            edits, left = {}, _total(tg)
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    if passive_plug(x, st["title"]) and left > 1:
                        emit(f'  {TAG} Stop {st["num"]}: restaurant plug (passive form) dropped: "{x[:90]}"')
                        edits[(i, j)] = []
                        left -= 1
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} restaurant plug guard skipped (non-fatal): {err}")
        return tour_text


# ══ 7. a geography / administrative-boundary list ════════════════════════════════════════════════════════
_COMPASS = re.compile(r"(?i)\b(?:to\s+the\s+)?(?:north|south|east|west)(?:ern)?\b")
_ADMIN = re.compile(r"(?i)\b(?:wards?|communes?|districts?|provinces?|counties|county|municipalit\w+|townships?|sea|ocean|prefectures?)\b")
_BORDER = re.compile(r"(?i)\b(?:lies\s+(?:with|between)|is\s+(?:bordered|bounded|surrounded)\s+by|borders?|adjoins?|abuts|geographically)\b")


def is_boundary_list(x: str) -> bool:
    s = x or ""
    return bool(_BORDER.search(s) and len(_COMPASS.findall(s)) >= 2 and len(_ADMIN.findall(s)) >= 2)


def drop_boundary(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, tg):
            edits, left = {}, _total(tg)
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    if is_boundary_list(x) and left > 1:
                        emit(f'  {TAG} Stop {st["num"]}: administrative-boundary list dropped: "{x[:90]}"')
                        edits[(i, j)] = []
                        left -= 1
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} boundary guard skipped (non-fatal): {err}")
        return tour_text


# ══ 4. the no-history disclosure on a stop that has facts ════════════════════════════════════════════════
_FILLER_RX: List = []


def _filler_regexes() -> List:
    """The sensory lead-in templates the tour itself writes (906C variants, 888 templates, 900 short names)."""
    if _FILLER_RX:
        return _FILLER_RX
    texts: List[str] = []
    try:
        for kind in c.FILLER_VARIANTS.values():
            for variant in kind:
                texts += [t for t in variant if isinstance(t, str)]
    except Exception:  # pragma: no cover
        pass
    for mod, attr in (("strict_grounding_gate", "_SENSORY_TEMPLATES"), ("place_names_900", "SENSORY_BY_KIND")):
        try:
            v = getattr(__import__(mod), attr, ())
            vals = v.values() if isinstance(v, dict) else v
            for item in vals:
                texts += [item] if isinstance(item, str) else [t for t in item if isinstance(t, str)]
        except Exception:  # pragma: no cover
            pass
    for t in texts:
        _FILLER_RX.append(re.compile("^" + r"[^.!?]{1,80}?".join(re.escape(p) for p in re.split(r"\{t\}", t)) + "$"))
    return _FILLER_RX


def _is_template_filler(x: str) -> bool:
    s = (x or "").strip()
    return rc.is_mood_filler(s, set()) or any(rx.match(s) for rx in _filler_regexes())


def _supported(x: str, ev: str) -> bool:
    if len(x.split()) < 6 or c._is_disclosure(x) or _is_template_filler(x):
        return False
    tx, te = rc._content_tokens(x), rc._content_tokens(ev)
    shared = tx & te
    return len(shared) >= 3 and len(shared) / max(len(tx), 1) >= 0.6


def drop_disclosure_with_facts(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                               log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text

        def fn(st: Dict, tg):
            ev = rc._ev_for(ev_map, st["title"]) or ""
            allx = [x for _i, (_p, s) in tg.items() for x in s]
            if not ev.strip() or not any(c._is_disclosure(x) for x in allx):
                return {}
            n_ok = sum(1 for x in allx if _supported(x, ev))
            if n_ok < 2:
                return {}
            edits = {}
            for i, (prefix, sents) in tg.items():
                if prefix:
                    continue
                for j, x in enumerate(sents):
                    if c._is_disclosure(x) or _is_template_filler(x):
                        edits[(i, j)] = []
            if edits:
                emit(f"  {TAG} Stop {st['num']}: the no-history disclosure (and its sensory lead-in) dropped: "
                     f"the stop has {n_ok} supported sentences")
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} disclosure guard skipped (non-fatal): {err}")
        return tour_text


# ══ 5. one builder, one spelling across tours: the stop's article wins ═══════════════════════════════════
_CAP = r"[A-ZÀ-Ỹ][\w'’\-]*"
_SEQ = re.compile(r"(?<![\wÀ-ỹ])(" + _CAP + r"(?:\s+" + _CAP + r"){2,3})(?![\wÀ-ỹ])")
_OPENERS = frozenset("after before in the by when then later born founded a an but and while since during according he she it this "
                     "his her as once until from with for at on".split())
_PERSON_VERB = r"(?:began|started|built|carved|sculpted|designed|founded|constructed|created|commissioned|completed|ordered|oversaw|died|was\s+born|lived|ruled|taught|restored|renovated|initiated)"
_PERSON_BEFORE = re.compile(r"(?i)\b(?:by|named|called|monk|master|sculptor|builder|founder|artist|architect|abbot|craftsman|carver|man|"
                            r"venerable|reverend|emperor|king)\s+(?:[a-z]+\s+)?$")
_PERSON_AFTER = re.compile(r"(?i)^\s*(?:,\s*)?(?:who\s+)?" + _PERSON_VERB + r"\b")


def person_spans(text: str) -> List[Tuple[int, int, str]]:
    """Capitalised 3-4 token names with a person cue (a role / \"by\" before, a building verb after), leading sentence openers trimmed."""
    out = []
    for m in _SEQ.finditer(text or ""):
        toks = list(re.finditer(_CAP, m.group(1)))
        lead = 0
        while lead < len(toks) - 2 and toks[lead].group(0).lower() in _OPENERS:
            lead += 1
        if len(toks) - lead < 3 or toks[lead].group(0).lower() in _OPENERS:
            continue
        s, e = m.start(1) + toks[lead].start(), m.start(1) + toks[-1].end()
        if _PERSON_BEFORE.search(text[max(0, s - 40):s]) or _PERSON_AFTER.match(text[e:e + 40]):
            out.append((s, e, text[s:e]))
    return out


def align_names(text: str, article: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Every person name of ``text`` that has the same first two tokens (and token count) as a person the ARTICLE names, under
    another spelling, takes the article's spelling. Returns (text, [(old, new)])."""
    if not text or not article:
        return text, []
    arts = []
    for _s, _e, nm in person_spans(article):
        if nm not in arts:
            arts.append(nm)
    if not arts:
        return text, []
    art_f = rc.fold(article)
    changes: List[Tuple[str, str]] = []
    for s, e, nm in sorted(person_spans(text), key=lambda z: -z[0]):
        tn = rc.fold(nm).split()
        for a in arts:
            ta = rc.fold(a).split()
            if a == nm or len(ta) != len(tn) or ta[:2] != tn[:2]:
                continue
            if ta == tn:                                            # same name, only the diacritics differ: the article's
                text, changes = text[:s] + a + text[e:], changes + [(nm, a)]
                break
            if re.search(r"(?<![\w])" + re.escape(rc.fold(nm)) + r"(?![\w])", art_f):
                break                                               # the article itself spells it this way too
            text, changes = text[:s] + a + text[e:], changes + [(nm, a)]
            break
    return text, changes


def unify_with_article(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                       log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import refill_quality_906k as _k906
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text

        def fn(st: Dict, tg):
            ev = rc._ev_for(ev_map, st["title"]) or ""
            if not ev.strip():
                return {}
            art = _k906._article_text(ev, st["title"], c._entries_for(st["title"]))[0] or ""
            if not art.strip():
                return {}
            edits = {}
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    new, ch = align_names(x, art)
                    if ch:
                        for old, nw in ch:
                            emit(f"  {TAG} Stop {st['num']}: builder spelling '{old}' -> '{nw}' (the article's)")
                        edits[(i, j)] = [new]
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} article spelling skipped (non-fatal): {err}")
        return tour_text


# ══ 8. a cable car number must be in ACCEPTED evidence ═══════════════════════════════════════════════════
def accepted_text(title: str, ev: str) -> str:
    """The sentences of the stop's evidence that pass the refill quality bar (an ellipsis-cut snippet is out)."""
    import refill_quality_906k as _k906
    keep = []
    for cand in rc.split_sentences(ev or ""):
        src = _k906.source_of(cand, ev, title)
        if not _k906.refill_reject(cand, title, None, src, "", False):
            keep.append(cand)
    return " ".join(keep)


def cable_car_accepted_numbers(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                               log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import owner_junk_906p as oj
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text

        def fn(st: Dict, tg):
            title = st["title"]
            ev = rc._ev_for(ev_map, title) or ""
            if not ev.strip():
                return {}
            all_vals = oj.evidence_values(ev)
            ok_vals = oj.evidence_values(accepted_text(title, ev))
            edits, left = {}, _total(tg)
            for i, (_p, sents) in tg.items():
                for j, x in enumerate(sents):
                    if not oj._CABLE.search(x):
                        continue
                    for m in oj._ANY_NUM.finditer(x):
                        v = oj._meters(m.group("n"), m.group("u"))
                        if not v or v < 100:
                            continue
                        if oj._traceable(v, ok_vals):
                            dom = ""
                            for en in c._entries_for(title):
                                if re.search(r"(?<!\d)" + re.escape(m.group("n")) + r"(?!\d)", en.get("text", "")):
                                    dom = en.get("domain") or en.get("kind") or ""
                                    break
                            emit(f'  {TAG} Stop {st["num"]}: cable car number {m.group(0)} kept (accepted source: {dom or "evidence passage"})')
                        elif left > 1:
                            why = "only in a refused snippet" if oj._traceable(v, all_vals) else "in no evidence"
                            emit(f'  {TAG} Stop {st["num"]}: cable car number {m.group(0)} {why} -> sentence dropped: "{x[:90]}"')
                            edits[(i, j)] = []
                            left -= 1
                            break
            return edits
        return _edit(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} cable car number guard skipped (non-fatal): {err}")
        return tour_text


# ══ the pass ═════════════════════════════════════════════════════════════════════════════════════════════
def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    t = unify_with_article(tour_text, evidence_by_title, log)
    t = drop_splice(t, log)
    t = drop_operator(t, log)
    t = drop_passive_plug(t, log)
    t = drop_boundary(t, log)
    t = cable_car_accepted_numbers(t, evidence_by_title, log)
    t = drop_disclosure_with_facts(t, evidence_by_title, log)
    return t


def last_word(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None, log: Optional[Callable] = None) -> str:
    """After every refill: the guards once more; a stop they left thin (< 3 body sentences) takes the same thin refill as any
    other, and the refilled text is guarded again."""
    emit = _emit(log)
    try:
        t = run_pass(tour_text, evidence_by_title, log)
        if t == tour_text:
            return tour_text
        import leftovers_906f as f
        t2 = f.refill_thin_stops(t, evidence_by_title, log)
        return run_pass(t2, evidence_by_title, log) if t2 != t else t
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} last word skipped (non-fatal): {err}")
        return tour_text
