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
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import leftovers_906c as c
import refill_quality_906k as _k906
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
          r"dr|mr|mrs|ms|carver|craftsman|mason|engineer|designer|monarch|ruler|governor|missionary|mayor|president|premier|chancellor|senator|captain|colonel|admiral")
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


_PRONOUN_WORDS = frozenset("he she they it we i you his her him them this that these those there here who".split())


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
            if not ws or ws[0] in _MONTHS or ws[0] in rc._NOISE or ws[0] in _PRONOUN_WORDS:
                continue
            out.append(n)
    return out


_ALIAS_RX = re.compile(
    r"(?P<n>" + _NAME + r")\s*,?\s*(?:also\s+)?(?:known|called|named|referred\s+to)\s+(?:by\s+|as\s+)?(?:(?:his|her|the)\s+)?"
    r"(?:(?:Dharma|religious|monastic|birth|given|pen|art|stage|temple)\s+)?(?:name|title)?\s*(?P<a>" + _NAME + r")"
    r"(?:\s*(?:,|and)\s*(?:(?:his|her)\s+)?(?:(?:Dharma|religious|monastic)\s+)?(?:name|title)?\s*(?P<b>" + _NAME + r"))?")
_ALIAS_STOP = frozenset("the a an in on at of his her their its this that".split())


def _key(n: str) -> Tuple[str, ...]:
    """A name as folded tokens (diacritics and case folded; a <Placeholder> by its words)."""
    return tuple(rc._words(re.sub(r"[<>]", " ", n or "")))


def _ascii(n: str) -> str:
    """The plain spoken form of a name: diacritics removed, case kept."""
    out = []
    for ch in n:
        if ch in "đĐ":
            out.append("d" if ch == "đ" else "D")
            continue
        d = unicodedata.normalize("NFD", ch)
        out.append("".join(x for x in d if not unicodedata.combining(x)) or ch)
    return "".join(out)


def _alias_pairs(text: str) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """[LOCAL-906I] \"<X>, known by his Dharma name <Y> and title <Z>\" / \"also called <Y>\": X, Y and Z are one person."""
    out = []
    for m in _ALIAS_RX.finditer(text or ""):
        n = _key(m.group("n"))
        for g in ("a", "b"):
            v = m.group(g)
            if v and n and _key(v) and _key(v)[0] not in _ALIAS_STOP:
                out.append((n, _key(v)))
    return out


def _distinct(names: Sequence[str], title: str, context: str = "", prefer: str = "") -> List[str]:
    """[LOCAL-906I] One entry per PERSON. Names are folded (diacritics, case); a name whose tokens are a subset of another's
    is the same person; a name the ``context`` introduces as \"known by his Dharma name / title / also called <X>\" is an
    alias. The entry is the plain spoken form: the longest folded-ASCII variant that ``prefer`` (the tour text) uses, else
    the longest variant. The stop's own title words are set aside."""
    tt = set(rc._words(re.sub(r"[<>]", " ", title or "")))
    items: List[Tuple[str, Tuple[str, ...]]] = []
    for n in names:
        k = _key(n)
        if not k:
            continue
        if not n.startswith("<") and set(k) <= tt:
            continue
        if all(n != x for x, _k in items):
            items.append((n, k))
    if not items:
        return []
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i, (_n, ki) in enumerate(items):
        for j, (_m, kj) in enumerate(items):
            if i < j and (set(ki) <= set(kj) or set(kj) <= set(ki)):
                union(i, j)
    for ka, kb in _alias_pairs(context):
        ia = [i for i, (_n, k) in enumerate(items) if set(k) <= set(ka) or set(ka) <= set(k)]
        ib = [i for i, (_n, k) in enumerate(items) if set(k) <= set(kb) or set(kb) <= set(k)]
        for i in ia + ib:
            union(i, (ia + ib)[0])
    pref = rc.fold(prefer or "")
    groups: Dict[int, List[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for _r, members in sorted(groups.items(), key=lambda kv: min(kv[1])):
        def rank(i):
            n, k = items[i]
            used = bool(pref) and (" ".join(k) in pref)
            return (used, len(k), len(n))
        best = items[max(members, key=rank)][0]
        out.append(best if best.startswith("<") else _ascii(best))
    return out


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
            n = re.sub(r"['’]s?$", "", m.group(0))          # [LOCAL-906I] "Orla Mountain's" is the title
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
            # [LEAD 906L] "the Linh Son Truong Tho Pagoda": a long name the place noun follows, or "the <Name>", is a place
            nxt = re.match(r"\s+([A-Za-z]+)", s[m.end():])
            if nxt and nxt.group(1).lower() in _PLACE_END:
                continue
            if re.search(r"(?i)\bthe\s+$", s[:m.start()]):
                continue
            return True
    return False


# ══ 2. a person pronoun with no referent ═════════════════════════════════════════════════════════════════
_SHIP = re.compile(r"(?i)\b(?:ship|vessel|boat|steamer|schooner|yacht|ferry|frigate|nation|country)\b")
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
                if m.group(1).lower() in ("her", "hers", "she", "herself") and _SHIP.search(before + " " + x + " " + title):
                    before += " " + x                      # a ship / vessel / nation is a referent for her / she
                    continue
                if _persony_names(seen, title) or _ROLE_NOUN.search(seen) or _distinct(_cand_names(title), title):
                    before += " " + x
                    continue
                rest = " ".join(y for _i, _j, y in flat[pos + 1:])
                ctx = before + " " + " ".join(y for _i, _j, y in flat) + " " + ev
                cands = _distinct(_cand_names(rest), title, ctx, tour_text)
                src = "the stop's own text"
                if not cands:
                    cands = _distinct(_cand_names(ev), title, ctx, tour_text)
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


_GENERIC_TITLE = frozenset(
    "room hall museum gallery church park square street road avenue plaza garden gardens center centre house site "
    "old new great grand upper lower north south east west central main city town village national royal saint "
    "st way trail path market station tour stop visit view point".split())
_SCOPE_PH = frozenset("country region town city province district state area place village island".split())


def _title_toks(title: str) -> set:
    return {t.rstrip("s") for t in rc._content_tokens(c._plain(title))}


def _distinctive(title: str) -> set:
    """A title's identifying words: not a generic head (_OBJECT_NOUNS), not a generic place / venue word."""
    return {t for t in _title_toks(title) if t not in _OBJECT_NOUNS and t not in _GENERIC_TITLE and len(t) >= 3}


def _placeholders(title: str) -> set:
    """``<Statue>`` stands for one specific name; the same placeholder in two titles is the same named thing."""
    return {m.strip().lower().rstrip("s") for m in re.findall(r"<([^>]{1,40})>", title or "")
            if m.strip().lower() not in _SCOPE_PH and not _PERSON_PH.fullmatch("<" + m + ">")}


def _link_token(ta: str, tb: str, xa: str, xb: str) -> Optional[str]:
    """The token that makes two stops one object, or None. Generic heads and shared place words never link on their own."""
    da, db = _distinctive(ta), _distinctive(tb)
    shared = (da & db) | (_placeholders(ta) & _placeholders(tb))
    if shared:
        return sorted(shared)[0]
    sa = {t.rstrip("s") for t in rc._content_tokens(c._plain(xa))}
    sb = {t.rstrip("s") for t in rc._content_tokens(c._plain(xb))}
    hit = (da - db) & sb or (db - da) & sa            # one stop's sentence names the OTHER stop's distinctive title word
    return sorted(hit)[0] if hit else None


def _titles_linked(ta: str, tb: str, xa: str, xb: str) -> bool:
    return _link_token(ta, tb, xa, xb) is not None


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
                    link = _link_token(infos[claims[a][0]]["title"], infos[claims[b][0]]["title"],
                                       claims[a][3], claims[b][3])
                    if not link or not (ca["thing"] & cb["thing"] or len(ca["obj"] & cb["obj"]) >= 2):
                        continue                              # different objects: generic heads / place words never link
                    yc, bc = _year_conflict(ca, cb), _builder_conflict(ca, cb)
                    if yc or bc:
                        hit = (a, b, yc, bc, link)
                        break
                if hit:
                    break
            if not hit:
                break
            a, b, yc, bc, link = hit
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
                 f"\"{xb[:60]}\" ({what}; linked by '{link}'): {verdict}")
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
    # [LOCAL-906M] tour-operator / review copy
    r"(?i)\bmany\s+(?:local\s+)?(?:tour\s+operators?|travel\s+agenc\w+|operators)\b[^.!?]{0,80}?"
    r"\b(?:advertis\w*|offer|run|sell|organi[sz]e|promote|market)\b",
    r"(?i)\byou\s+(?:can|could|may)\s+(?:also\s+)?join\s+(?:an?\s+|the\s+|one\s+of\s+the\s+)?(?:[\w\-]+\s+){0,3}?tours?\b",
    r"(?i)\b(?:many|most|some)\s+(?:of\s+the\s+)?tours?\s+(?:often\s+|usually\s+|typically\s+)?combine\b",
    r"(?i)\bflexible\s+options\s+(?:are\s+)?available\b[^.!?]{0,60}\btours?\b",
    r"(?i)\bwithin\s+walking\s+distance\s+(?:from|of)\s+(?:some|several|many|a\s+few)\s+(?:of\s+the\s+)?hotels\b",
    r"(?i)\bif\s+you\s+(?:stay|are\s+staying)\s+(?:nearby|near|close|in\s+the\s+area)\b[^.!?]{0,60}\bhotel\s+rooms?\b",
    r"(?i)\bsome\s+hotel\s+rooms?\s+(?:offer|have|provide|boast)\b",
    r"(?i)\b(?:getting|reaching|climbing|driving)\s+(?:to|up|here)\b[^.!?]{0,60}\bwas\s+an\s+adventure\b",
    r"(?i)\bwas\s+an\s+adventure,?\s+(?:and\s+)?(?:it\s+was\s+|it's\s+|that\s+was\s+)?(?:well\s+)?worth\s+it\b",
    r"(?i)\b(?:we|i)\s+(?:absolutely\s+|really\s+|totally\s+|all\s+)?(?:loved|enjoyed|adored)\b",
    r"(?i)\bi\s+(?:would\s+|'d\s+)?(?:highly\s+|strongly\s+)?recommend\b",
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
                elif _k906.is_venue_promo(x, st["title"]):             # [LOCAL-906K] a venue plug / "with or without a guide"
                    emit(f'  [LOCAL-906K] Stop {st["num"]}: venue promo dropped: "{x[:80]}"')
                    edits[(i, j)] = []
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} promo guard skipped (non-fatal): {err}")
        return tour_text


# ══ 5b. [LOCAL-909] driving tour: public-transport directions and scheduling advice ════════════════════════
_TRANSIT = [re.compile(p) for p in (
    r"(?i)\b(?:take|takes|taking|catch|catching|board|ride|riding)\s+(?:the\s+|a\s+|an\s+)?"
    r"(?:(?:public|local|city|express|shuttle)\s+)?(?:bus|buses|minibus|metro|subway|underground|tram|train|trolley|coach)\b",
    r"(?i)\b(?:bus|metro|tram|train|subway)\s+(?:line\s+|route\s+|number\s+|no\.?\s*)?\d+\b",
    r"(?i)\bfrom\s+the\s+(?:mall|bus\s+(?:station|stop|terminal)|train\s+station|metro\s+station|tram\s+stop)\b",
    r"(?i)\bpublic\s+(?:transport|transportation|transit)\b",
    r"(?i)\bmaking\s+sure\s+you\s+are\s+heading\s+in\s+the\s+right\s+direction\b",
)]
_SCHEDULE = [re.compile(p) for p in (
    r"(?i)\b(?:morning\s+or\s+(?:in\s+the\s+)?afternoon|afternoon\s+or\s+(?:in\s+the\s+)?morning)\b",
    r"(?i)\bdepending\s+on\s+your\s+(?:schedule|plans?|itinerary|time|preferences?|mood)\b",
    r"(?i)\byou\s+(?:can|could|may)\s+(?:choose|decide)\s+to\s+visit\b",
    r"(?i)\bwhichever\s+(?:suits|fits|works\s+(?:best\s+)?for)\s+(?:you|your\s+schedule)\b",
)]
_OPTION_ADVICE = re.compile(
    r"(?i)^\s*you\s+(?:can|could|may)\s+(?:either\s+)?(?:take|ride|use|choose)\s+(?:a|an|the)\s+(?:[\w\-]+\s+){0,3}?"
    r"(?:cable\s*car|gondola|shuttle|bus|train|funicular|lift|tram)\s+or\s+(?:walk|hike|climb|trek|take|ride)\b")


def is_driving_practical(sentence: str) -> str:
    """'' when the sentence is fine on a driving tour, else why it goes (transit / schedule / option advice)."""
    x = sentence or ""
    if any(rx.search(x) for rx in _TRANSIT):
        return "public-transport directions"
    if any(rx.search(x) for rx in _SCHEDULE):
        return "scheduling advice"
    if _OPTION_ADVICE.search(x):
        return "how-to-get-up options"
    return ""


def drop_driving_practical(tour_text: str, log: Optional[Callable] = None, force: bool = False) -> str:
    """[LOCAL-909] On a DRIVING tour a stop body carries no bus / metro / train directions, no \"from the mall\", no
    \"morning or afternoon depending on your schedule\" and no \"you can take X or walk\" advice. A walking tour is
    untouched (``force`` only for tests that do not set the job state)."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import route_order_909 as r909
        if not (force or r909.is_driving()):
            return tour_text

        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                why = is_driving_practical(x)
                if why:
                    emit(f'  [LOCAL-909] Stop {st["num"]}: {why} dropped on a driving tour: "{x[:80]}"')
                    edits[(i, j)] = []
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  [LOCAL-909] driving practical guard skipped (non-fatal): {err}")
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


_LEAD_REST = re.compile(r"\b(?:located|situated|found|lying|lies|sits|set)\s+(?P<rest>(?:off|in|on|at|near|along|about|just|some|above|"
                        r"beside|outside)\b[^\n]*)$")


def _spoken_lead(sentence: str, title: str) -> Optional[str]:
    """[LOCAL-906I] \"<X> is a mountain located off of Route 1 in the town of <T>.\" -> \"<X> lies off Route 1 in the town of
    <T>.\" (a subject that ends in the generic head \"Mount\" takes the stop's title when that is the same name)."""
    m = _LEAD.match(sentence)
    r = _LEAD_REST.search(sentence)
    if not m or not r or r.start() < m.end() - 12:
        return None
    subj = m.group("subj").strip()
    words = subj.split()
    if words and rc.fold(words[-1]) in ("mount", "mt", "mountain") and len(words) > 1:
        tw = rc._words(title)
        if tw and rc._words(" ".join(words[:-1])) == tw[:len(words) - 1] and rc.fold(title.split()[-1]) in (
                "mount", "mountain", "mt"):
            subj = title.strip()
    rest = re.sub(r"(?i)^(off|outside|near|beside)\s+of\b", r"\1", r.group("rest").strip())
    if len(rest.split()) < 3:
        return None
    return _clean_names(f"{subj} lies {rest}")


def drop_encyclopedia_leads(tour_text: str, log: Optional[Callable] = None) -> str:
    """6c / [LOCAL-906I] An encyclopedia lead \"<X> is a mountain located off ...\" (anywhere in the body): dropped when
    another sentence of the stop already says where the place is (and the stop keeps at least two sentences); otherwise
    spoken as a location (\"<X> lies off ...\")."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            flat = st["flat"]
            edits: Dict[Tuple[int, int], List[str]] = {}
            left = len(flat)
            for k, (i, j, x) in enumerate(flat):
                if not _LEAD.match(x):
                    continue
                if left >= 3 and any(_WHERE.search(y) for kk, (_a, _b, y) in enumerate(flat) if kk != k
                                     and (_a, _b) not in edits):
                    emit(f'  {TAG} Stop {st["num"]}: encyclopedia lead dropped (the stop already says where it is): '
                         f'"{x[:80]}"')
                    edits[(i, j)] = []
                    left -= 1
                    continue
                spoken = _spoken_lead(x, st["title"])
                if spoken:
                    emit(f'  {TAG} Stop {st["num"]}: [LOCAL-906I] encyclopedia lead spoken as a location: "{x[:70]}" -> '
                         f'"{spoken[:70]}"')
                    edits[(i, j)] = [spoken]
            return edits
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
_GENERIC_HEADS = frozenset(w for aliases, _h in _HEAD_GROUPS for w in aliases) | {
    "mountain", "mount", "temple", "pagoda", "island", "lake", "river", "beach", "bay", "bridge", "tower", "castle",
    "palace", "park", "garden", "museum", "church", "cathedral", "shrine", "mosque", "cave", "waterfall", "hill",
    "square", "street", "road", "market", "statue", "buddha", "fort", "gate", "monastery", "village", "city", "town"}
_DUP_WORD = re.compile(r"\b([A-ZÀ-Ỹ][\wÀ-ỹ]{2,})(\s+)\1\b")


def _clean_names(x: str) -> str:
    y = _DUP_WORD.sub(lambda m: m.group(1) if rc.fold(m.group(1)) in _GENERIC_HEADS else m.group(0), x)
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


# ══ [LOCAL-906I] 4. no "The <Proper Name>" ═══════════════════════════════════════════════════════════════
_GEO_HEAD = r"(?:Mountain|Mount|Mt\.?|Hill|Peak|Volcano|Lake|Island|Beach)"
_PLAIN_ADJ = frozenset("great old new little holy sacred big high grand royal golden white black blue red green upper lower "
                       "northern southern eastern western central reclining sleeping standing".split())
_THE_PROPER = re.compile(r"\b(?P<the>[Tt]he)\s+(?P<name>(?:[A-ZÀ-Ỹ][\wÀ-ỹ'’\-]*\s+){1,3}" + _GEO_HEAD + r")\b(?![\wÀ-ỹ])")
_THE_PH = re.compile(r"(?:(?<=^)|(?<=[.!?]\s))The\s+(?P<name><[^>]{1,40}>)")


def strip_proper_article(sentence: str) -> str:
    """A proper name takes no article: \"The Ta Cu Mountain's most striking feature\" -> \"Ta Cu Mountain's most ...\",
    \"The <Mountain>'s\" -> \"<Mountain>'s\". A common-noun head (\"The Reclining Buddha\") and a name that starts with a plain
    adjective (\"The Great Hill\") keep it."""
    def _real(m):
        first = rc.fold(m.group("name").split()[0])
        if first in _PLAIN_ADJ:
            return m.group(0)
        return m.group("name")
    y = _THE_PROPER.sub(_real, sentence)
    y = _THE_PH.sub(lambda m: m.group("name") if m.group("name").strip("<>").strip().lower() not in _SCOPE_PH
                    and not _COMMON_PH.match(m.group("name").strip("<>").strip().lower()) else m.group(0), y)
    if y != sentence and y[:1].islower():
        y = y[0].upper() + y[1:]
    return y


_COMMON_PH = re.compile(r"^(?:statue|cave|cable car|tower|bridge|market|gate|wall)s?\b")


def fix_proper_article(tour_text: str, log: Optional[Callable] = None) -> str:
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        def fn(st: Dict, _all: List[Dict]):
            edits = {}
            for i, j, x in st["flat"]:
                y = strip_proper_article(x)
                if y != x:
                    emit(f'  {TAG} Stop {st["num"]}: [LOCAL-906I] article before a proper name removed: "{x[:60]}" -> '
                         f'"{y[:60]}"')
                    edits[(i, j)] = [y]
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} proper-article repair skipped (non-fatal): {err}")
        return tour_text


# ══ [LOCAL-906I] 3. one fact, one stop ═══════════════════════════════════════════════════════════════════
_NUM_UNIT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:\s|-)*([A-Za-z]{2,})")
_TRAIL_CLAUSE = re.compile(r"\s*,\s*(?:which|that|measuring|spanning|standing|reaching)\b[^,]*\d[^,]*?(?=[.!?]?$)")
_UNITLESS = frozenset("the and of in at on to a an as is was by or for from with".split())


def _facts(sentence: str) -> frozenset:
    """{(number, unit stem)} a sentence states: \"49 meters long\" / \"49-meter-long\" -> (49, mete)."""
    out = set()
    for m in _NUM_UNIT.finditer(sentence or ""):
        u = rc.fold(m.group(2))
        if u in _UNITLESS or re.fullmatch(r"(?:st|nd|rd|th)", u):
            continue
        out.add((m.group(1).replace(",", ""), u[:4]))
    return frozenset(out)


def _title_words(title: str) -> List[str]:
    return [w for w in rc._words(re.sub(r"[<>]", " ", title or "")) if w not in _UNITLESS and len(w) >= 3]


_CONTAINER_WORDS = frozenset("mountain mount mountains hill hills peak park island islands beach lake river valley bay district "
                             "province city town village area region coast plateau range reserve forest garden gardens".split())


def _is_container_title(title: str) -> bool:
    """[LOCAL-906P] A title naming the PLACE that holds other things (a mountain, a park, an island ...)."""
    return any(w in _CONTAINER_WORDS for w in _title_words(title))


def _owner(sentence: str, titles: Sequence[str]) -> Optional[int]:
    """The stop whose title object the number in ``sentence`` is about: the title with a word closest before the first
    number (ties: the longer title). [LOCAL-906P] A fact about the object a stop is NAMED for belongs to that stop even when
    the sentence also names the enclosing place ("the statue here on <Mountain>"): of the titles the sentence names, the
    more specific one (an object, not a container place) wins over the containing place."""
    m = _NUM_UNIT.search(sentence)
    if not m:
        return None
    before = rc._words(sentence[:m.start()])
    whole = rc._words(sentence)
    cands = []
    for k, t in enumerate(titles):
        tw = _title_words(t)
        if not tw or not all(w in whole for w in tw):
            continue
        pos = max((i for i, w in enumerate(before) if w in tw), default=-1)
        cands.append((k, pos, len(tw)))
    if len(cands) > 1 and any(not _is_container_title(titles[k]) for k, _p, _n in cands):
        cands = [cd for cd in cands if not _is_container_title(titles[cd[0]])]      # [LOCAL-906P] the object, not its place
        if len(cands) == 1:
            return cands[0][0]
    cands = [cd for cd in cands if cd[1] >= 0]
    return max(cands, key=lambda cd: (cd[1], cd[2]))[0] if cands else None


def drop_cross_stop_fact(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                         log: Optional[Callable] = None) -> str:
    """[LOCAL-906I] A sentence of stop A whose numbers (with their unit nouns) are the main fact of stop B's title object --
    B says the same numbers about the same object -- is B's fact: the trailing clause is cut from A (or the sentence is
    dropped when nothing remains of it), unless A would be left with nothing else. Generic; ``same_fact`` also counts."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        infos = _stops(tour_text)
        if len(infos) < 2:
            return tour_text
        titles = [st["title"] for st in infos]

        def fn(st: Dict, all_: List[Dict]):
            me = next((k for k, o in enumerate(all_) if o["num"] == st["num"] and o["title"] == st["title"]), None)
            edits: Dict[Tuple[int, int], List[str]] = {}
            left = len(st["flat"])
            for i, j, x in st["flat"]:
                fx = _facts(x)
                if not fx or me is None:
                    continue
                own = _owner(x, titles)
                if own is None or own == me:
                    continue
                other = all_[own]
                if not any(fx <= _facts(y) and (_owner(y, titles) in (own, None) or rc.same_fact(x, y, other["title"]))
                           for _a, _b, y in other["flat"]):
                    continue
                cut = _TRAIL_CLAUSE.sub("", x)
                if cut != x and len(cut.split()) >= 5 and not _facts(cut) & fx:
                    cut = cut if cut[-1:] in ".!?" else cut + "."
                    emit(f'  {TAG} Stop {st["num"]}: [LOCAL-906I] fact belongs to stop {other["num"]} '
                         f'("{other["title"][:30]}"): clause cut: "{x[:70]}" -> "{cut[:70]}"')
                    edits[(i, j)] = [cut]
                elif left > 1:
                    emit(f'  {TAG} Stop {st["num"]}: [LOCAL-906I] fact belongs to stop {other["num"]} '
                         f'("{other["title"][:30]}") -> sentence dropped: "{x[:80]}"')
                    edits[(i, j)] = []
                    left -= 1
            return edits
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} cross-stop fact guard skipped (non-fatal): {err}")
        return tour_text


# ══ [LOCAL-906I] 6. a thin stop is refilled from its evidence ═════════════════════════════════════════
THIN_MAX, THIN_TARGET = 3, 5
_FIRST_PERSON = re.compile(r"(?i)\b(?:i|we|our|us|you|your)\b")


def refill_thin_stops(tour_text: str, evidence_by_title: Optional[Dict[str, str]] = None,
                      log: Optional[Callable] = None) -> str:
    """[LOCAL-906I] A stop with <= 3 body sentences after the 906C/F removals gets supported evidence sentences (one that
    is not denied, not a blocked claim, not the same fact as a sentence already in the tour, no person pronoun, no promo)
    up to 5 sentences. Evidence order; nothing is invented, so a stop with no usable evidence stays as it is."""
    emit = _emit(log)
    if not tour_text:
        return tour_text
    try:
        import key_fact_coverage as kfc
        ev_map = c._ev_map(evidence_by_title)
        if not ev_map:
            return tour_text
        titles = [st["title"] for st in _stops(tour_text)]

        def fn(st: Dict, all_: List[Dict]):
            flat = st["flat"]
            if not flat or len(flat) > THIN_MAX:
                return {}
            title = st["title"]
            blob = rc._ev_for(ev_map, title) or ""
            if not blob.strip():
                return {}
            pool = kfc.own_prose_sentences(blob, title)
            _src = "article"
            if not pool:
                pool, _src = rc.split_sentences(blob), "snippet"        # [LOCAL-906K] a search snippet must clear a higher bar
            have = [x for _i, _j, x in flat]
            if any(re.search(r"(?i)could\s+not\s+confirm\s+verified|no\s+verified\s+(?:history|historical)", x) for x in have):
                emit(f"  {TAG} Stop {st['num']}: thin but carries the no-history disclosure -> no refill (it would contradict it)")
                return {}                          # [LEAD 906L] D760 disclosure: adding "built in 1955" would contradict it
            others = [y for o in all_ if o["title"] != title for _a, _b, y in o["flat"]]
            added: List[str] = []
            for cand in pool:
                if len(have) + len(added) >= THIN_TARGET:
                    break
                n = len(cand.split())
                if not (6 <= n <= 40) or cand[-1:] not in ".!?" or rc.is_fragment(cand) or rc.is_mood_filler(cand, set()):
                    continue
                if _PRON.search(cand) or _FIRST_PERSON.search(cand) or is_promo(cand) or _LEAD.match(cand):
                    continue
                if _k906.reject_logged(cand, title, tour_text, emit, st["num"], _src, st.get("type", ""), True):
                    continue                       # [LOCAL-906K] the refill quality bar (reason logged)
                if kfc.is_denied(title, cand, blob) or kfc.deterministic_unsupported(cand, blob, title):
                    continue
                if c.record_claim(cand) and c.record_support(cand, blob, title, c._entries_for(title)) == "bad":
                    continue                       # [LOCAL-906J] a record the sources do not carry is not a refill either
                if c.check_claim(cand, blob, title)[0] == "bad":
                    continue
                cur = have + added
                if any(rc.same_fact(cand, y, title) for y in cur + others):
                    continue
                fc = _facts(cand)
                me = next((k for k, o in enumerate(all_) if o["num"] == st["num"]), None)
                if fc and any(fc <= _facts(y) for y in others) and _owner(cand, titles) != me:
                    continue
                added.append(cand)
            if not added:
                return {}
            i, j, last = flat[-1]
            emit(f"  {TAG} Stop {st['num']} '{title[:40]}': [LOCAL-906I] thin after removals ({len(flat)} body sentence(s)) "
                 f"-> {len(added)} supported evidence sentence(s) added")
            return {(i, j): [last] + added}
        return _each_stop(tour_text, fn)
    except Exception as err:  # pragma: no cover
        emit(f"  {TAG} thin-stop refill skipped (non-fatal): {err}")
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
    try:   # [LOCAL-906M] other-site landmarks in a generic-title stop; Directions name only the leg's own end
        import anchor_evidence_906m as _a906m
        t = _a906m.drop_other_site_landmarks(t, evidence_by_title, log)
        t = _a906m.trim_directions(t, log)
    except Exception as _e906m:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906M] pass skipped (non-fatal): {_e906m}")
    t = drop_driving_practical(t, log)
    try:   # [LOCAL-906O] a stop "actually located in" another city, ticket / hours / queue / half-day-tour copy, and the
        import scope_906o as _s906o       # template closing on EVERY route / drive path (the 906M closing guard only ran in content_pass)
        t = _s906o.run_pass(t, log)
    except Exception as _e906o:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906O] pass skipped (non-fatal): {_e906o}")
    try:   # [LOCAL-906N] one builder, one spelling (before the cross-stop check sees "Tri" vs "Y" as a conflict)
        import nits_906n as _n906n
        t = _n906n.unify_builder_names(t, evidence_by_title, log)
    except Exception as _e906n:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906N] builder unify skipped (non-fatal): {_e906n}")
    t = resolve_cross_stop(t, evidence_by_title, log)
    t = drop_cross_stop_fact(t, evidence_by_title, log)
    t = drop_encyclopedia_leads(t, log)
    t = fix_duplicate_names(t, log)
    t = fix_proper_article(t, log)
    t = fix_orphan_compounds(t, log)
    t = repair_person_pronoun(t, evidence_by_title, log)
    t = _k906.run_pass(t, evidence_by_title, log)          # [LOCAL-906K] mode words, conflicting measures
    try:   # [LOCAL-906N] a proper name lowercased by an earlier rewrite gets its capitals back
        import nits_906n as _n906n
        t = _n906n.restore_proper_case(t, log)
    except Exception as _e906n:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906N] case guard skipped (non-fatal): {_e906n}")
    try:   # [LOCAL-906P] captions / list stubs, a glued sentence, cable-car numbers, a raw measure splice, the closing's superlatives
        import owner_junk_906p as _o906p
        t = _o906p.run_pass(t, evidence_by_title, log)
    except Exception as _e906p:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906P] pass skipped (non-fatal): {_e906p}")
    try:   # [LOCAL-906Q] restaurant plug, day-trip / operator copy, resort promo, filler, two communes, a dangling "for,"
        import route_copy_906q as _c906q
        t = _c906q.run_pass(t, evidence_by_title, log)
    except Exception as _e906q:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906Q] pass skipped (non-fatal): {_e906q}")
    try:   # [LOCAL-906R] a measure splice, new day-trip / operator wording, the passive restaurant plug, the disclosure on a stop with facts
        import splice_copy_906r as _r906r
        t = _r906r.run_pass(t, evidence_by_title, log)
    except Exception as _e906r:  # pragma: no cover
        _emit(log)(f"  [LOCAL-906R] pass skipped (non-fatal): {_e906r}")
    return t
