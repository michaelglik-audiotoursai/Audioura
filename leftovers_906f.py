"""[LOCAL-906F] Wave 53 leftovers. Pure, offline, name-free (D769). Every function returns the text unchanged on error.

  1. superlative scope in every form  -> ``leftovers_906c.scoped_claim`` / ``check_claim`` (in all of / across all of /
     in the whole of / anywhere in / <area>'s largest / hedged "one of the largest ... in the world")
  2. ``repair_person_pronoun``   a his/her/he/she/him with no person named before it: name the person when the stop's
                                 text or evidence names exactly one, else drop the sentence
  3. ``strip_blocked``           a claim LOCAL-229 (or any contradiction gate) blocked stays blocked: checked against the
                                 job-scoped deny-set (``key_fact_coverage.deny_*``) at delivery, on every path
  4. ``resolve_cross_stop``      two stops giving a different year / builder for the same object: keep the supported one,
                                 disclose when the sources differ, drop both when neither is supported
  5. ``drop_promo``              tour-operator / ticket copy ("You can take a half-day tour ...", "book ...")
  6. cosmetics: ``fix_orphan_compounds`` ("a -long cable car"), ``drop_encyclopedia_leads`` ("<X> is a mountain
     located ..." when the stop already says where), ``fix_duplicate_names`` ("<Mountain> Mount")
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import leftovers_906c as c
import route_content_896 as rc

TAG = "[LOCAL-906F]"


def _emit(log: Optional[Callable]) -> Callable:
    return log or (lambda _m: None)


# ══ stop plumbing: every body sentence of a stop with its (line, position) so an edit keeps the paragraphs ═══
def _stops(text: str) -> List[Dict]:
    out = []
    for info in c._stops_info(text):
        per_line = {i: rc.split_sentences(info["lines"][i]) for i in info["idx"]}
        flat = [(i, j, x) for i in info["idx"] for j, x in enumerate(per_line[i]) if not rc._CLOSING_LINE.match(x)]
        out.append({**info, "per_line": per_line, "flat": flat})
    return out


def _apply(text: str, info: Dict, edits: Dict[Tuple[int, int], List[str]]) -> str:
    """``edits[(line, pos)]`` = the sentences that replace that sentence ([] = dropped)."""
    if not edits:
        return text
    lines = list(info["lines"])
    for i, sents in info["per_line"].items():
        new: List[str] = []
        for j, x in enumerate(sents):
            new.extend(edits[(i, j)] if (i, j) in edits else [x])
        lines[i] = " ".join(new) if new else None
    block = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in lines if x is not None))
    if not block.endswith("\n") and info["lines"] and text[info["s"]:info["e"]].endswith("\n"):
        block += "\n"
    return text[:info["s"]] + block + text[info["e"]:]


def _each_stop(text: str, fn: Callable[[Dict, List[Dict]], Dict[Tuple[int, int], List[str]]]) -> str:
    """Run ``fn(stop, all_stops)`` -> edits for every stop in turn (offsets re-read after each edit)."""
    n = len(c._stops_info(text))
    for k in range(n):
        infos = _stops(text)
        if k >= len(infos):
            break
        text = _apply(text, infos[k], fn(infos[k], infos))
    return text


# ══ names ════════════════════════════════════════════════════════════════════════════════════════════════
_N = r"(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]+)"
_NAME = _N + r"(?:\s+(?:(?:de|da|del|di|van|von|bin|al|le|la|du)\s+)?" + _N + r"){0,3}"
_PERSON_PH = re.compile(r"<(?:Person|Monk|Founder|Master|Abbot|Sculptor|Architect|King|Emperor|Queen|Builder|Artist|"
                        r"Saint|Teacher|Man|Woman|Creator|Carver)[^>]{0,30}>")
_ROLES = (r"monk|master|founder|abbot|sculptor|architect|emperor|king|queen|prince|princess|saint|builder|artist|"
          r"bishop|priest|abbess|nun|general|sage|teacher|poet|painter|patriarch|reverend|venerable|lord|sir|"
          r"dr|mr|mrs|ms|carver|craftsman|mason|engineer|designer|monarch|ruler|governor|missionary")
_ROLE_RX = re.compile(r"(?i:\b(?:" + _ROLES + r")\s+)(?P<n>" + _NAME + r")")
_CUE_AFTER = re.compile(r"(?P<n>" + _NAME + r")\s+(?:died|was\s+born|founded|established|built|began|started|carved|sculpted|"
                        r"designed|commissioned|taught|lived|ruled|spent|completed|constructed|created)\b")
_CUE_POSS = re.compile(r"(?P<n>" + _NAME + r")['’]s\s+(?:death|life|birth|followers|disciples|students|teachings|legacy|"
                       r"successors|tomb|ashes|body|remains|vision|dream)\b")
_ROLE_NOUN = re.compile(r"(?i)\b(?:a|an|the|its|this|that|local|one)\s+(?:[\w\-]+\s+){0,2}?(?:" + _ROLES +
                        r"|man|woman|hermit|pilgrim|nobleman|villager|craftsman|ancestor|owner|resident|worshipper)\b")
_MONTHS = frozenset("january february march april may june july august september october november december "
                    "monday tuesday wednesday thursday friday saturday sunday".split())
_PLACE_END = frozenset("temple pagoda mountain mount hill lake river island beach bay bridge tower castle palace market "
                       "museum park garden gate fort monastery shrine mosque church cathedral cave waterfall square "
                       "street road station hotel statue buddha city town village province region district".split())
_PLACE_PREP = re.compile(r"(?i)\b(?:in|at|near|from|to|off|on|of|across|around|toward|towards|into|within|by|outside)\s+(?:the\s+)?$")


def _cand_names(text: str) -> List[str]:
    """Person names the text states with a cue (a role word before, a person verb after, a possessive person noun)."""
    out: List[str] = []
    for m in _PERSON_PH.finditer(text or ""):
        out.append(m.group(0))
    for rx in (_ROLE_RX, _CUE_AFTER, _CUE_POSS):
        for m in rx.finditer(text or ""):
            n = m.group("n").strip()
            if n.startswith("<") and not _PERSON_PH.fullmatch(n):
                continue
            ws = rc._words(n)
            if not ws or ws[0] in _MONTHS or ws[0] in rc._NOISE:
                continue
            out.append(n)
    return out


def _distinct(names: Sequence[str], title: str) -> List[str]:
    """Merge names whose tokens are a subset of another's; set aside names that are the stop's own title words."""
    tt = set(rc._words(title))
    uniq: List[str] = []
    for n in names:
        toks = set(rc._words(n)) if not n.startswith("<") else {n}
        if not n.startswith("<") and toks and toks <= tt:
            continue
        for i, u in enumerate(uniq):
            ut = set(rc._words(u)) if not u.startswith("<") else {u}
            if toks <= ut:
                break
            if ut <= toks:
                uniq[i] = n
                break
        else:
            uniq.append(n)
    return uniq


def _persony_names(text: str, title: str) -> bool:
    """A person is named in ``text``: a cue name, or a capitalised name that is not the stop's own title, a month, a
    place (after a place preposition or ending in a place noun) or a lone sentence opener."""
    if _distinct(_cand_names(text), title):
        return True
    tt = set(rc._words(title))
    for sm in re.finditer(r"[^.!?]+[.!?]?", text or ""):
        s = sm.group(0)
        lead = len(s) - len(s.lstrip())
        for m in re.finditer(r"(?<![\w<])" + _NAME + r"(?![\w>])", s):
            n = m.group(0)
            if n.startswith("<"):
                continue
            toks = n.split()
            ws = rc._words(n)
            if not ws or set(ws) <= tt or ws[0] in _MONTHS or ws[-1] in _PLACE_END:
                continue
            if m.start() == lead and len(toks) == 1:
                continue                                  # a lone sentence opener ("Today", "After")
            if len(toks) == 1 and ws[0] in rc._NOISE:
                continue
            if _PLACE_PREP.search(s[:m.start()]):
                continue
            return True
    return False


# ══ 2. a person pronoun with no referent ═════════════════════════════════════════════════════════════════
_PRON = re.compile(r"(?i)\b(his|hers|her|he|she|him|himself|herself)\b")
_NOT_POSS_NEXT = frozenset("to in at on for with and by from as than or but the a an that which who is was".split())


def _name_pronoun(sentence: str, name: str) -> Optional[str]:
    """Replace the FIRST person pronoun of ``sentence`` by ``name`` ('s for his/her)."""
    m = _PRON.search(sentence)
    if not m:
        return None
    p = m.group(1).lower()
    if p in ("himself", "herself"):
        return None
    poss = p in ("his", "hers")
    if p == "her":
        nxt = re.match(r"\s+([A-Za-z]+)", sentence[m.end():])
        poss = bool(nxt) and nxt.group(1).lower() not in _NOT_POSS_NEXT
    rep = (name + ("'" if name.endswith(("s", "S")) else "'s")) if poss else name
    return sentence[:m.start()] + rep + sentence[m.end():]


def repair_person_pronoun(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                          log: Optional[Callable] = None) -> str:
    """Item 2. A body sentence with his/her/he/she/him and no person named before it (earlier in the stop, or earlier in
    the sentence): when exactly one person is named by the stop's other sentences, else by its evidence, the first
    pronoun becomes the name ("After his death" -> "After <Person>'s death"); otherwise the sentence is dropped."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)

        def fn(st: Dict, _all: List[Dict]):
            title, num = st["title"], st["num"]
            ev = rc._ev_for(ev_map, title) or ""
            flat = st["flat"]
            edits: Dict[Tuple[int, int], List[str]] = {}
            before = ""
            for pos, (i, j, x) in enumerate(flat):
                m = _PRON.search(x)
                if not m:
                    before += " " + x
                    continue
                seen = before + " " + x[:m.start()]
                if _persony_names(seen, title) or _ROLE_NOUN.search(seen) or _distinct(_cand_names(title), title):
                    before += " " + x
                    continue
                rest = " ".join(y for _i, _j, y in flat[pos + 1:])
                cands = _distinct(_cand_names(rest), title)
                src = "the stop's own text"
                if not cands:
                    cands = _distinct(_cand_names(ev), title)
                    src = "the evidence"
                new = _name_pronoun(x, cands[0]) if len(cands) == 1 else None
                if new and new != x:
                    emit(f'  {TAG} Stop {num}: person pronoun had no referent; named from {src} ({cands[0]}): "{x[:80]}"')
                    edits[(i, j)] = [new]
                    before += " " + new
                else:
                    emit(f'  {TAG} Stop {num}: person pronoun with no referent and no unambiguous name -> '
                         f'sentence dropped: "{x[:80]}"')
                    edits[(i, j)] = []
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} person-pronoun repair skipped (non-fatal): {err}")
        return tour_text


# ══ 3. a blocked claim stays blocked ═════════════════════════════════════════════════════════════════════
def strip_blocked(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                  log: Optional[Callable] = None) -> str:
    """Item 3. Every body sentence that repeats a claim on the job's deny-set (LOCAL-229's CONTRADICTED block, the
    grounding gate's verdicts, the deterministic / contested drops) is removed again, whichever path put it back
    (key-fact injection, signature regeneration, refill, recap)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import key_fact_coverage as kfc
        ev_map = c._ev_map(evidence_by_title)

        def fn(st: Dict, _all: List[Dict]):
            if not kfc.deny_claims(st["title"]):
                return {}
            ev = rc._ev_for(ev_map, st["title"]) or ""
            edits = {}
            for i, j, x in st["flat"]:
                hit = kfc.is_denied(st["title"], x, ev)
                if hit:
                    emit(f'  {TAG} Stop {st["num"]}: a blocked claim came back -> removed again: "{x[:80]}" '
                         f'(blocked by {hit.get("source") or "a gate"}: "{hit["text"][:60]}")')
                    edits[(i, j)] = []
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} blocked-claim check skipped (non-fatal): {err}")
        return tour_text


# ══ 4. cross-stop consistency for one object ═════════════════════════════════════════════════════════════
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-4][0-9])\b")
_START_V = r"begun|began|begin|started|start|commenced|broke\s+ground|laid"
_END_V = r"completed|finished|opened|inaugurated|dedicated|unveiled|consecrated"
_GEN_V = r"built|constructed|erected|founded|established|carved|sculpted|created|cast|made|designed|commissioned|raised"
_ANY_V = re.compile(r"(?i)\b(?:" + _START_V + "|" + _END_V + "|" + _GEN_V + r"|carving|building|constructing)\b")
_BY = re.compile(r"\bby\s+(?:(?:the|a|an)\s+)?(?:[a-z]+\s+){0,2}?(?P<n>" + _NAME + r")")
_BEFORE_V = re.compile(r"(?P<n>" + _NAME + r")\s+(?:" + _START_V + "|" + _END_V + "|" + _GEN_V + r"|carved|built)\b")
_SUBJ_NOUN = re.compile(r"(?i)\b(?:the|this|that)\s+(?:[\w\-]+\s+){0,2}?([a-z]{4,})\b")
_OBJECT_NOUNS = frozenset(
    "statue buddha pagoda temple church cathedral shrine mosque tower bridge castle palace monument mausoleum "
    "fountain gate wall arch building structure hall tomb lighthouse column obelisk memorial dome spire".split())


def _role(sentence: str) -> str:
    low = sentence.lower()
    if re.search(r"\b(?:" + _START_V + r")\b", low):
        return "start"
    if re.search(r"\b(?:" + _END_V + r")\b", low):
        return "end"
    return "gen"


def _claim_of(sentence: str, title: str) -> Optional[Dict]:
    """{'years', 'builders', 'role', 'obj'} for a sentence that gives a year and/or a builder of the stop's object."""
    if not _ANY_V.search(sentence):
        return None
    years = sorted(set(_YEAR.findall(sentence)))
    names: List[str] = []
    for rx in (_BY, _BEFORE_V):
        for m in rx.finditer(sentence):
            n = m.group("n").strip()
            if n.startswith("<") and not _PERSON_PH.fullmatch(n):
                continue
            ws = rc._words(n)
            if ws and ws[0] not in _MONTHS and ws[0] not in rc._NOISE and n not in names \
                    and not set(ws) <= set(rc._words(title)):
                names.append(n)
    names = _distinct(names, title)
    if not years and not names:
        return None
    skip = set()
    for n in names:
        skip |= set(rc._words(n))
    obj = {t for t in rc._content_tokens(re.sub(r"<[^>]*>", " ", sentence)) if not t.isdigit() and t not in skip}
    obj = {t for t in obj if not _ANY_V.fullmatch(t) and t not in c._NOISE_C and len(t) >= 4}
    # the physical object noun the sentence builds/carves ("the statue", "this pagoda", "a 49-meter reclining buddha")
    thing = set()
    for m in _SUBJ_NOUN.finditer(sentence):
        w = m.group(1)
        if w in _OBJECT_NOUNS:
            thing.add(w.rstrip("s"))
    for w in _OBJECT_NOUNS:
        if re.search(r"(?i)\b" + w + r"s?\b", re.sub(r"<[^>]*>", " ", sentence)):
            thing.add(w)
    title_toks = {t.rstrip("s") for t in rc._content_tokens(re.sub(r"<[^>]*>", " ", title))}
    thing |= (title_toks & _OBJECT_NOUNS)
    obj = {o.rstrip("s") for o in obj} | thing
    return {"years": years, "builders": names, "role": _role(sentence), "obj": obj, "thing": thing}


def _title_toks(title: str) -> set:
    return {t.rstrip("s") for t in rc._content_tokens(c._plain(title))}


def _titles_linked(ta: str, tb: str, xa: str, xb: str) -> bool:
    """Two stops are about one object when their titles share a distinctive word, or one claim names the other's title."""
    a, b = _title_toks(ta), _title_toks(tb)
    if a & b:
        return True
    sa = {t.rstrip("s") for t in rc._content_tokens(c._plain(xa))}
    sb = {t.rstrip("s") for t in rc._content_tokens(c._plain(xb))}
    return bool(a & sb - _OBJECT_NOUNS) or bool(b & sa - _OBJECT_NOUNS)


def _supported_year(y: str, ev: str) -> bool:
    return y in set(re.findall(r"\d{3,4}", ev or ""))


def _supported_name(n: str, ev: str) -> bool:
    if n.startswith("<"):
        return n in (ev or "")
    words = set(rc._words(ev))
    return all(w in words for w in rc._words(n))


def _year_conflict(a: Dict, b: Dict) -> bool:
    if not a["years"] or not b["years"] or set(a["years"]) & set(b["years"]):
        return False
    ra, rb = a["role"], b["role"]
    if ra == rb:
        return True
    if "gen" in (ra, rb):                                   # a generic "built in Y" next to a start / end year
        g, o = (a, b) if ra == "gen" else (b, a)
        gy, oy = int(g["years"][0]), int(o["years"][0])
        return gy < oy if o["role"] == "start" else gy > oy
    return False                                            # begun in one year, completed in another: both can hold


def _builder_conflict(a: Dict, b: Dict) -> bool:
    if not a["builders"] or not b["builders"]:
        return False
    sa = {rc.fold(n) for n in a["builders"]}
    sb = {rc.fold(n) for n in b["builders"]}
    return not any(x == y or set(x.split()) <= set(y.split()) or set(y.split()) <= set(x.split()) for x in sa for y in sb)


def resolve_cross_stop(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                       log: Optional[Callable] = None) -> str:
    """Item 4. Two stops of one tour that give a different year or builder for the same object: the sentence the evidence
    supports stays, the other goes; when the evidence supports both ("sources differ") one sentence stays and the
    disclosure "Sources differ on the date: 1958 or 1963." follows it; when neither is supported both go."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text                                 # no evidence handed in: nothing to judge by
        text = tour_text
        for _round in range(8):
            infos = _stops(text)
            claims: List[Tuple[int, int, int, str, Dict]] = []         # (stop idx, line, pos, sentence, claim)
            for k, st in enumerate(infos):
                for i, j, x in st["flat"]:
                    cl = _claim_of(x, st["title"])
                    if cl:
                        claims.append((k, i, j, x, cl))
            hit = None
            for a in range(len(claims)):
                for b in range(a + 1, len(claims)):
                    if claims[a][0] == claims[b][0]:
                        continue
                    ca, cb = claims[a][4], claims[b][4]
                    same_thing = bool(ca["thing"] & cb["thing"]) and _titles_linked(
                        infos[claims[a][0]]["title"], infos[claims[b][0]]["title"], claims[a][3], claims[b][3])
                    if not same_thing and len(ca["obj"] & cb["obj"]) < 2:
                        continue
                    yc, bc = _year_conflict(ca, cb), _builder_conflict(ca, cb)
                    if yc or bc:
                        hit = (a, b, yc, bc)
                        break
                if hit:
                    break
            if not hit:
                break
            a, b, yc, bc = hit
            (ka, ia, ja, xa, ca), (kb, ib, jb, xb, cb) = claims[a], claims[b]
            sa, sb = infos[ka], infos[kb]
            ev = " ".join(filter(None, (rc._ev_for(ev_map, sa["title"]), rc._ev_for(ev_map, sb["title"]))))

            def ok(cl: Dict, _ev=ev) -> bool:
                return (all(_supported_year(y, _ev) for y in cl["years"]) and
                        all(_supported_name(n, _ev) for n in cl["builders"]))
            oa, ob = ok(ca), ok(cb)
            shared = " ".join(sorted(ca["obj"] & cb["obj"]))[:40]
            what = " and ".join(w for w, f in (("year", yc), ("builder", bc)) if f)
            verdict = ("evidence supports both" if oa and ob else
                       f"evidence supports Stop {sa['num'] if oa else sb['num']}" if (oa or ob) else
                       "evidence supports neither -> both dropped")
            emit(f"  {TAG} cross-stop conflict on '{shared}': Stop {sa['num']} \"{xa[:60]}\" vs Stop {sb['num']} "
                 f"\"{xb[:60]}\" ({what}): {verdict}")
            ea: Dict[Tuple[int, int], List[str]] = {}
            eb: Dict[Tuple[int, int], List[str]] = {}
            if oa and ob:
                disc = []
                if yc:
                    disc.append("Sources differ on the date: " + " or ".join(sorted(set(ca["years"]) | set(cb["years"]))) + ".")
                if bc:
                    disc.append("Sources differ on the builder: " +
                                " or ".join(dict.fromkeys(ca["builders"] + cb["builders"])) + ".")
                ea[(ia, ja)] = [xa] + disc
                eb[(ib, jb)] = []
            elif oa:
                eb[(ib, jb)] = []
            elif ob:
                ea[(ia, ja)] = []
            else:
                ea[(ia, ja)] = []
                eb[(ib, jb)] = []
            # a stop's block changes length: edit the later stop first, then re-read the earlier one
            text = _apply(text, infos[kb], eb)
            text = _apply(text, _stops(text)[ka], ea)
        return text
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} cross-stop check skipped (non-fatal): {err}")
        return tour_text


# ══ 5. promo copy ════════════════════════════════════════════════════════════════════════════════════════
_PROMO = [re.compile(p) for p in (
    r"(?i)\byou\s+(?:can|could|may)\s+(?:also\s+)?(?:take|join|book|go\s+on|sign\s+up\s+for|opt\s+for)\s+(?:a|an|the|one\s+of\s+the)\s+"
    r"(?:[\w\-]+\s+){0,3}?(?:half-day|full-day|day|guided|private|group|organi[sz]ed|packaged|\d+-hour|\w+-hour|\w+-day)\s+"
    r"(?:[\w\-]+\s+){0,2}?(?:tours?|excursions?|trips?|packages?)\b",
    r"(?i)\byou\s+(?:can|could|may)\s+(?:also\s+)?(?:take|join|book)\s+(?:a|an|the)\s+(?:[\w\-]+\s+){0,2}?"
    r"(?:guided\s+)?(?:tours?|excursions?)\s+(?:here|there|of|to|that|which|with)\b",
    r"(?:^|(?<=[.!?]\s))(?:Book|Reserve)\b",
    r"(?i)\byou\s+(?:can|may|should|could|will\s+need\s+to)\s+(?:also\s+)?(?:book|reserve)\b",
    r"(?i)\bbook\s+(?:ahead|in\s+advance|online|your|tickets?|a\s+(?:tour|spot|table|room))\b",
    r"(?i)\btickets?\s+(?:cost|costs|are\s+(?:sold|available|priced)|start|from|can\s+be\s+(?:bought|purchased|booked))\b",
    r"(?i)\b(?:tour\s+operators?|travel\s+agenc\w+|local\s+operators?)\s+(?:offer|run|organi[sz]e|provide|sell|arrange)\b",
    r"(?i)\btours?\s+(?:are\s+)?(?:available|offered|depart|leave|start\s+from|can\s+be\s+booked)\b",
    r"(?i)\bprices?\s+(?:start|begin)\s+(?:at|from)\b",
    r"(?i)\bfor\s+more\s+information,?\s+(?:visit|contact|call|check)\b",
)]
_TICKETED = re.compile(r"(?i)\b(?:museum|gallery|castle|palace|temple|pagoda|cable\s*car|observatory|zoo|aquarium|garden|"
                       r"theme\s+park|attraction|monument|cathedral|fort|cave|tower|theat(?:er|re)|opera|exhibition)\b")


def is_promo(sentence: str) -> bool:
    return any(rx.search(sentence or "") for rx in _PROMO)


def _verified_fact(sentence: str, evidence: str) -> bool:
    nums = re.findall(r"\d[\d,.]*\d|\d", sentence)
    if not nums:
        return False
    have = {n.replace(",", "") for n in re.findall(r"\d[\d,.]*\d|\d", evidence or "")}
    return all(n.replace(",", "") in have for n in nums)


def drop_promo(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
               log: Optional[Callable] = None) -> str:
    """Item 5. A sentence selling a tour, a booking or tickets is dropped, unless the stop is a ticketed venue (its
    title / Type names one) and the sentence gives a figure the stop's evidence holds."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        ev_map = c._ev_map(evidence_by_title)

        def fn(st: Dict, _all: List[Dict]):
            ev = rc._ev_for(ev_map, st["title"]) or ""
            venue = bool(_TICKETED.search(st["title"] + " " + st.get("type", "")))
            edits = {}
            for i, j, x in st["flat"]:
                if is_promo(x) and not (venue and _verified_fact(x, ev)):
                    emit(f'  {TAG} Stop {st["num"]}: promo copy dropped: "{x[:80]}"')
                    edits[(i, j)] = []
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} promo guard skipped (non-fatal): {err}")
        return tour_text


# ══ 6. cosmetics ═════════════════════════════════════════════════════════════════════════════════════════
_UNITS = (r"long|high|tall|wide|deep|thick|old|meters?|metres?|kilomet\w+|miles?|foot|feet|ft|km|minutes?|hours?|days?|"
          r"years?|stor(?:y|ey)|floors?|tons?|tonnes?|acres?|hectares?|step|steps")
_ORPHAN = re.compile(r"(?i)(?P<art>\b(?:a|an)\s+)?(?<![\w\d)\]>])-(?:" + _UNITS + r")\b(?:-(?:" + _UNITS + r")\b)*[ \t]*")


def fix_orphan_compounds(tour_text: str, log: Optional[Callable] = None) -> str:
    """6a. A number cut left its hyphen: "taking a -long cable car" -> "taking a cable car"."""
    emit = _emit(log)
    if not tour_text or "-" not in tour_text:
        return tour_text
    try:
        def sub(m: "re.Match") -> str:
            emit(f'  {TAG} orphan compound removed: "{m.group(0).strip()}"')
            art = m.group("art")
            return art.replace("an ", "a ").replace("An ", "A ") if art else ""
        out_lines = []
        for ln in tour_text.split("\n"):
            if ln.lstrip().startswith("<!--") or rc._KEYED.match(ln) or not re.search(r"(?<![\w\d)\]>])-[A-Za-z]", ln):
                out_lines.append(ln)
                continue
            out_lines.append(_ORPHAN.sub(sub, ln))
        return "\n".join(out_lines)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} orphan-compound repair skipped (non-fatal): {err}")
        return tour_text


_WHERE = re.compile(r"(?i)\b(?:located|situated|lies|lying|sits|nestled|set|found|stands|perched|reached)\s+"
                    r"(?:of\s+)?(?:in|on|at|near|off|along|about|just|some|above|beside|outside|from|to)\b|"
                    r"\b\d[\d.,]*\s*(?:km|kilomet\w+|miles?|minutes?)\s+(?:from|away|north|south|east|west|off|by)\b|"
                    r"\b(?:near|outside|on\s+the\s+outskirts\s+of)\s+(?:the\s+)?(?:\w+\s+){0,2}?(?:city|town|village|coast|<)")
_LEAD = re.compile(
    r"^(?P<subj>(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]*)(?:\s+(?:<[^>]{1,40}>|[A-ZÀ-Ỹ][\w'’\-]*|of|de|the|and)){0,5})\s+(?:is|are|was)\s+"
    r"(?:a|an|the)\s+(?:[\w\-]+\s+){0,3}?(?P<kind>mountain|hill|peak|volcano|town|city|village|district|ward|commune|province|"
    r"region|island|lake|river|beach|bay|valley|suburb|neighbou?rhood|municipality|county|park|area|peninsula)\b[^.]{0,100}?"
    r"\b(?:located|situated|found|lying|lies|sits|set)\b")


def drop_encyclopedia_leads(tour_text: str, log: Optional[Callable] = None) -> str:
    """6c. The first body sentence "<X> is a mountain located off ..." (an encyclopedia lead) goes when another sentence of
    the stop already says where the place is, and the stop keeps at least two sentences."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            flat = st["flat"]
            if len(flat) < 3 or not _LEAD.match(flat[0][2]):
                return {}
            if not any(_WHERE.search(x) for _i, _j, x in flat[1:]):
                return {}
            emit(f'  {TAG} Stop {st["num"]}: encyclopedia lead dropped (the stop already says where it is): '
                 f'"{flat[0][2][:80]}"')
            return {(flat[0][0], flat[0][1]): []}
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} lead guard skipped (non-fatal): {err}")
        return tour_text


_HEAD_GROUPS = (
    ({"mount", "mountain", "mt", "mont", "monte", "montana", "montaña", "berg", "nui", "núi", "gunung", "peak", "volcano"},
     r"Mount|Mountain|Mt\.?"),
    ({"lake", "lac", "lago", "ho", "hồ"}, r"Lake"),
    ({"river", "rio", "río", "fleuve", "song", "sông", "sungai"}, r"River"),
    ({"pagoda", "temple", "chua", "chùa", "wat", "pura"}, r"Pagoda|Temple"),
    ({"island", "dao", "đảo", "koh", "isla", "insel"}, r"Island"),
)
_DUP_WORD = re.compile(r"\b([A-ZÀ-Ỹ][\wÀ-ỹ]{2,})(\s+)\1\b")


def _clean_names(x: str) -> str:
    y = _DUP_WORD.sub(lambda m: m.group(1), x)
    for aliases, heads in _HEAD_GROUPS:
        alt = "|".join(sorted((re.escape(a) for a in aliases), key=len, reverse=True))
        # a placeholder named for the head ("<Mountain> Mount") already says it
        y = re.sub(r"(?i:<(?:" + alt + r")>)\s+(?:" + heads + r")\b\.?(?=[\s,;:!?]|$)",
                   lambda m: m.group(0).split(">")[0] + ">", y)
        # a native head word inside the name ("Nui Ba Mount") already says it
        y = re.sub(r"\b((?:[A-ZÀ-Ỹ][\wÀ-ỹ'’\-]*\s+){0,2}(?i:" + alt + r")(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ'’\-]*){0,2})\s+(?:" + heads +
                   r")\b(?=[\s,.;:!?]|$)",
                   lambda m: m.group(1) if rc.fold(m.group(1).split()[-1]) not in {rc.fold(h) for h in heads.split("|")}
                   or len(m.group(1).split()) > 1 else m.group(0), y)
    return y


def fix_duplicate_names(tour_text: str, log: Optional[Callable] = None) -> str:
    """6c. A name whose own head word is repeated by a generic head: "<Mountain> Mount", "Nui Ba Mount", "Mount Mount".
    The generic repeat is removed (body prose only; headers and keyed lines are never touched)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                y = _clean_names(x)
                if y != x:
                    emit(f'  {TAG} Stop {st["num"]}: duplicate-word name fixed: "{x[:60]}" -> "{y[:60]}"')
                    edits[(i, j)] = [y]
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} name repair skipped (non-fatal): {err}")
        return tour_text


# ══ the pass ═════════════════════════════════════════════════════════════════════════════════════════════
def run_pass(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
             log: Optional[Callable] = None) -> str:
    """Everything above, in the order that lets each step see the previous step's result: removals first (blocked claims,
    promo, cross-stop conflicts, encyclopedia leads), then the repairs (names, hyphens), then the person pronoun (it
    must see what is left of the stop). Idempotent; never raises."""
    t = tour_text
    t = strip_blocked(t, evidence_by_title, log)
    t = drop_promo(t, evidence_by_title, log)
    t = resolve_cross_stop(t, evidence_by_title, log)
    t = drop_encyclopedia_leads(t, log)
    t = fix_duplicate_names(t, log)
    t = fix_orphan_compounds(t, log)
    t = repair_person_pronoun(t, evidence_by_title, log)
    return t
