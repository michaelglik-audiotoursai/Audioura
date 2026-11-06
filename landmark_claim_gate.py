#!/usr/bin/env python3
"""landmark_claim_gate.py -- LOCAL-872: a claim about a landmark stop that no
source for that stop contains must not ship.

Evidence (GCloud_Storied_1, 2026-11-06, tour 544, Michael's 10-stop HCMC list):
after LOCAL-870 the Saigon Opera House user stop takes the landmark story path
and has real facts (built 1900, architects Ferret and Olivier) -- and a false
one: the Opera House "staged productions of Miss Saigon" (Miss Saigon has never
been staged in Vietnam).  Nothing checked it:

  * the LOCAL-855D/862 verifier guards BUSINESS user stops and skips the
    "documented kind" (landmark) stops;
  * the LOCAL-864 museum claim gate runs for tour_category == 'museum' only.

This module is that gate for the WALKING / landmark story path, user stops and
ordinary walking stops alike.  It reuses the LOCAL-864 primitives
(``museum_claim_gate``: sentence splitting, D760 disclosure test, stop headers,
dangling-pronoun cleanup) and adds the claim kinds a landmark narration makes:

  1. NAMED PRODUCTION / PERFORMANCE at the venue ("staged productions of Miss
     Saigon").  Saying a specific show was staged at a venue requires a source
     that names BOTH the show and the venue, close together.  A source about the
     show alone, or the venue alone, is not enough.
  2. NAMED PEOPLE doing something checkable (architect, designer, performer,
     conductor, commissioner...).  The surname must appear in a source.
  3. NAMED EVENTS (festival, conference, treaty, battle, ...).
  4. NAMED WORKS (a film, novel, song, ... the place is tied to).
  5. DATED claims: a year attached to a construction/opening/event verb must be
     in a source.

A sentence making any unsourced claim is dropped, unless it is DISCLOSED as
unverified (D760: "It is sometimes said ...").  A sentence whose claims are all
sourced is kept ("built in 1900 by Eugene Ferret" when a source says so), as is
any sentence making no checkable claim.  Pronoun sentences left dangling by a
drop go with it.

Pure: no network, no LLM, no DB.  Deterministic and idempotent.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import museum_claim_gate as _mcg

__all__ = [
    "venue_aliases", "production_claims", "named_person_claims", "named_event_claims",
    "named_work_claims", "dated_claims", "unsourced_claims", "filter_stop_body",
    "filter_tour_text", "claim_span_lines",
]

_fold = _mcg._fold
_sentences = _mcg._sentences
is_disclosed = _mcg.is_disclosed
_STOP_HEADER_RE = _mcg._STOP_HEADER_RE

# A capitalised token (accents allowed) and a capitalised phrase with connectors.
_UP = "A-ZÀ-ÖØ-ÞĀ-ŽẠ-Ỹ"
_LO = "a-zà-ÿā-žạ-ỹ"
_TOK = "[" + _UP + "][" + _LO + "'’\\-]*"
_CONN = r"(?:of|the|a|an|in|on|and|de|du|la|le|des|von|van|di|da|del)"
_PHRASE_RE = re.compile(r"\b(" + _TOK + r"(?:\s+(?:" + _CONN + r"\s+){0,2}" + _TOK + r"){0,6})\b")
_QUOTED_RE = re.compile(r"[\"“‘']([^\"”’']{2,60})[\"”’']")

# Words that are not a title on their own.
_STOP_CAPS = frozenset(_mcg._NOT_PERSON) | frozenset("""
Opera House Theatre Theater Hall Municipal City Province District Old New Great Grand
Royal Imperial National Central Colonial Modern Revival Style Era War Republic
Empire Kingdom Dynasty Republic Today Built Inside Outside Over Under During After
Before Since When While Where Many Some Most Both Each Every Visitors Visitor Guests
It Its He She They We You His Her Their Our Your One Two Three Four Five
Vietnamese Vietnam Saigon Hanoi Hue Annam Tonkin Cochinchina Indochina French France
Europe European Asia Asian Paris Ho Chi Minh Nam Bo Street Road Lane Square Park Lake
Bridge Gate Market Pagoda Temple Church Cathedral Palace Tower Museum Library Station
Quarter Bank Hotel
""".split())

# ---- 1. named production / performance --------------------------------------
_PROD_CUE_RE = re.compile(
    r"(?i)\b(stag(?:e|ed|es|ing)|perform(?:ed|s|ing|ance|ances)|premier(?:e|ed|es)|"
    r"debut(?:ed|s)?|productions?|mounted|put on|screened|presented|hosted|"
    r"played host to|home to|housed|showed|showcas(?:ed|ing)|opened with|"
    r"concerts? of|recitals? of|season of)\b")
_PROD_NOUN_RE = re.compile(
    r"(?i)\b(production|performance|show|musical|opera|ballet|play|premiere|premiered|"
    r"staged|stage[sd]?|performed|screened|concert|recital|season|debut(?:ed)?)\b")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def venue_aliases(stop_title: str, extra: Iterable[str] = ()) -> List[str]:
    """Folded names a source may use for the stop's venue: the full title, the
    title without parentheticals, the last two words when >= 2 words after
    dropping a leading city word ("Saigon Opera House" -> "opera house"), and any
    alias supplied (the user's own wording, the Places name)."""
    out: List[str] = []

    def add(x: str) -> None:
        x = " ".join(re.findall(r"[a-z0-9]+", _fold(x)))
        if len(x) >= 5 and x not in out:
            out.append(x)

    base = re.sub(r"\s*\([^)]*\)", " ", stop_title or "")
    base = re.sub(r"(?i)^\s*stop\s+\d+\s*[:\-]\s*", "", base)
    add(base)
    toks = re.findall(r"[a-z0-9]+", _fold(base))
    if len(toks) >= 3:
        add(" ".join(toks[-2:]))
        add(" ".join(toks[1:]))
    for a in extra or []:
        if a:
            add(str(a))
    return out


def _title_tokens(stop_title: str, location: str = "") -> set:
    return set(re.findall(r"[a-z0-9]{3,}", _fold(f"{stop_title} {location}")))


def _candidate_titles(sentence: str, stop_tokens: set) -> List[str]:
    """Titles a sentence may be naming: quoted spans, plus capitalised phrases that
    are not the venue / its city / a bare generic word."""
    out: List[str] = []
    for m in _QUOTED_RE.finditer(sentence):
        q = m.group(1).strip()
        if 2 <= len(q) <= 60 and re.search(r"[A-Za-z]", q) and q not in out:
            out.append(q)
    for m in _PHRASE_RE.finditer(sentence):
        ph = m.group(1)
        toks = [t for t in re.findall(_TOK, ph)]
        # strip leading/trailing generic words
        while toks and (toks[0] in _STOP_CAPS):
            toks.pop(0)
        while toks and (toks[-1] in _STOP_CAPS):
            toks.pop()
        if not toks:
            continue
        folded = [_fold(t) for t in toks]
        if all(f in stop_tokens for f in folded):
            continue
        # a sentence-initial single word is just capitalisation
        if len(toks) == 1 and m.start() == 0:
            continue
        # keep the span from first to last kept token
        a = ph.find(toks[0])
        b = ph.rfind(toks[-1]) + len(toks[-1])
        t = ph[a:b].strip()
        if t and t not in out:
            out.append(t)
    return out


def _after_cue_titles(sentence: str, stop_tokens: set) -> List[str]:
    """Titles in the part of the sentence at/after the first production cue, plus
    quoted ones anywhere; for a passive ("Miss Saigon was staged here") the whole
    sentence is searched."""
    m = _PROD_CUE_RE.search(sentence)
    if not m:
        return []
    passive = re.search(r"(?i)\b(was|were|is|are|has been|have been|been)\s+"
                        r"(?:\w+\s+)?(staged|performed|premiered|presented|screened|"
                        r"mounted|hosted|shown|debuted)\b", sentence)
    region = sentence if passive else sentence[m.start():]
    cands = _candidate_titles(region, stop_tokens)
    # the cue itself ("Productions of") is not a title
    return [c for c in cands if _fold(c) not in ("productions", "performances")]


def _source_names_both(title: str, evidence: Sequence[str], aliases: Sequence[str],
                       window: int = 250) -> bool:
    """True when ONE evidence item holds the title and a venue alias within
    ``window`` characters of each other."""
    tf = " ".join(re.findall(r"[a-z0-9]+", _fold(title)))
    if len(tf) < 3:
        return True
    for ev in evidence:
        e = " ".join(re.findall(r"[a-z0-9]+", _fold(ev)))
        start = 0
        while True:
            i = e.find(tf, start)
            if i < 0:
                break
            seg = e[max(0, i - window): i + len(tf) + window]
            if any(a in seg for a in aliases):
                return True
            start = i + len(tf)
    return False


def production_claims(sentence: str, stop_title: str, evidence: Sequence[str],
                      location: str = "", aliases: Iterable[str] = ()) -> List[str]:
    """Named productions/performances the sentence says happened at the venue that
    no single source ties to the venue.  [] when the sentence names none or all are
    sourced."""
    if not _PROD_CUE_RE.search(sentence) or not _PROD_NOUN_RE.search(sentence):
        return []
    stop_tokens = _title_tokens(stop_title, location)
    al = venue_aliases(stop_title, aliases)
    bad: List[str] = []
    sentence = re.sub(r"(\w)['’]s\b", r"\1", sentence)
    for t in _after_cue_titles(sentence, stop_tokens):
        # a person's name is handled as a person; a date or generic word is not a show
        if re.fullmatch(r"[\d\W]+", t):
            continue
        if not _source_names_both(t, evidence, al):
            bad.append(t)
    return bad


# ---- 2. named people ---------------------------------------------------------
_NAME = "(?:[" + _UP + "][" + _LO + "'’]+(?:-[" + _UP + "]?[" + _LO + "]+)*)"
_FULLNAME = (_NAME + r"(?:\s+(?:van|von|de|del|di|du|da|bin|ibn|le|la)\s+" + _NAME +
             r"|(?:\s+" + _NAME + r"){1,2})")
_ROLE = (r"(?i:architects?|designers?|engineers?|sculptors?|conductors?|composers?|"
         r"sopranos?|tenors?|singers?|pianists?|violinists?|dancers?|director|choreographers?|"
         r"emperor|king|queen|governor|governor-general|mayor|general|president|monk|abbot|"
         r"sir|dr|bishop|father|reverend|sultan|admiral|minister|colonel|captain)")
_PERSON_VERBS = (r"(?:performed|sang|conducted|played|starred|directed|designed|built|founded|"
                 r"opened|ordered|commissioned|inaugurated|composed|choreographed|painted|"
                 r"sculpted|led|ruled|signed|declared|proclaimed|restored|renovated|"
                 r"visited|attended|hosted|premiered|created|funded|established)")
_PERSON_PATTERNS = [
    # "by Eugene Ferret", "by Ferret and Olivier", "designed by X"
    re.compile(r"\bby\s+(" + _FULLNAME + r"|" + _NAME + r")(?:\s*(?:,|and|&)\s*(" +
               _FULLNAME + r"|" + _NAME + r"))*"),
    re.compile(r"\b" + _ROLE + r"s?\s+(" + _FULLNAME + r"|" + _NAME + r")(?:\s*(?:,|and|&)\s*(" +
               _FULLNAME + r"|" + _NAME + r"))*"),
    re.compile(r"\b(" + _FULLNAME + r")(?:'s|’s)?\s*,?\s+(?:the\s+)?(?:\w+\s+){0,2}" + _ROLE + r"\b"),
    re.compile(r"\b(" + _FULLNAME + r")\s+(?:\w+\s+){0,1}" + _PERSON_VERBS + r"\b"),
    re.compile(r"\b(" + _FULLNAME + r")\s+and\s+(" + _FULLNAME + r")\s+(?:\w+\s+){0,1}" + _PERSON_VERBS + r"\b"),
]
_NAME_BAD_TOKS = _STOP_CAPS | frozenset("""
Miss Mister Mr Mrs Ms Madame Monsieur Lady Lord Saint St
Gothic Renaissance Romanesque Baroque Neoclassical Classical Byzantine Moorish Neo Art Deco
Nouveau Modernist Brutalist General Post Office Journal Revue Architecte Constructeur
Buddhist Confucian Catholic Christian Communist Colonial Socialist Democratic
Government Ministry Committee Council Department Administration Authority Party Army
Navy Police Embassy Consulate Bureau Company Society Association Foundation University
Reunification Independence Liberation Unification Declaration Constitution
""".split())


_PLACE_NOUNS = frozenset("""
Temple Pagoda Lake Bridge Market Street Road Palace Cathedral Church Museum Hall Square Gate
Tower River Island Park Garden Gardens Station Quarter Hotel Bank Theatre Theater Opera
House Mosque Mausoleum Citadel Fort Pier Harbour Harbor Beach Mountain Hill Bay Canal
Avenue Boulevard Alley Library University School Hospital Monastery Shrine Memorial
""".split())


def _names_in(sentence: str, stop_tokens: set) -> List[str]:
    found: List[str] = []
    s = re.sub(r"(\w)['’]s\b", r"\1", sentence)
    for pi, rx in enumerate(_PERSON_PATTERNS):
        for m in rx.finditer(s):
            for g in m.groups():
                if not g:
                    continue
                raw = g.split()
                if any(t in _PLACE_NOUNS for t in raw[1:]) or (
                        len(raw) > 1 and raw[-1] in _PLACE_NOUNS):
                    continue  # "Ngoc Son Temple" is a place, not a person
                toks = [t for t in raw if t not in _NAME_BAD_TOKS]
                toks = [t for t in toks if _fold(t) not in stop_tokens]
                if not toks:
                    continue
                if len(toks) == 1 and (len(toks[0]) < 4 or pi > 1):
                    continue  # a lone word is a surname only after "by"/a role
                n = " ".join(toks)
                if n not in found:
                    found.append(n)
    return found


def named_person_claims(sentence: str, blob: str, stop_title: str, location: str = "",
                        known: Iterable[str] = ()) -> List[str]:
    """Named people a sentence attributes an act to (built, designed, performed,
    conducted...) whose surname appears in no source for the stop."""
    stop_tokens = _title_tokens(stop_title, location)
    kn = _fold(" ".join(k for k in known if k))
    bad = []
    for n in _names_in(sentence, stop_tokens):
        sur = _fold(n.split()[-1])
        # accents folded; a surname in any source sources the person
        if re.search(r"\b" + re.escape(sur) + r"\b", blob) or re.search(r"\b" + re.escape(sur) + r"\b", kn):
            continue
        bad.append(n)
    return bad


# ---- 3. named events ---------------------------------------------------------
_EVENT_NOUN = (r"(?:Festival|Concert|Exhibition|Ceremony|Games|Conference|Summit|Expo|Treaty|"
               r"Battle|Uprising|Siege|Revolution|Offensive|Coup|Fair|Parade|Gala|Championships?|"
               r"Olympics|Congress|Tournament|Awards|Assembly|Accords|Agreement|Massacre|Rebellion|"
               r"Insurrection|Incident|Protests?|Riots?)")
_EVENT_RE = re.compile(
    r"\b((?:The\s+)?(?:" + _TOK + r"\s+){1,3}" + _EVENT_NOUN + r"(?:\s+of\s+(?:" + _TOK + r"\s*){1,3})?"
    r"|" + _EVENT_NOUN + r"\s+of\s+(?:" + _TOK + r"\s*){1,3})\b")
_EVENT_CUE_RE = re.compile(
    r"(?i)\b(hosted|held|staged|witnessed|saw|site of|scene of|took place|taking place|signed|"
    r"celebrated|launched|opened|inaugurat\w+|gathered|announced|proclaimed|declared|"
    r"home to|during|at the)\b")


def named_event_claims(sentence: str, blob: str, stop_title: str = "",
                       location: str = "") -> List[str]:
    if not _EVENT_CUE_RE.search(sentence):
        return []
    stop_tokens = _title_tokens(stop_title, location)
    bad = []
    for m in _EVENT_RE.finditer(sentence):
        ev = m.group(1).strip()
        core = re.sub(r"^(?:The\s+)", "", ev).strip()
        toks = [_fold(t) for t in re.findall(_TOK, core)]
        if toks and all(t in stop_tokens for t in toks):
            continue
        cf = " ".join(re.findall(r"[a-z0-9]+", _fold(core)))
        bf = " ".join(re.findall(r"[a-z0-9]+", blob))
        if cf and cf not in bf:
            bad.append(core)
    return bad


# ---- 4. named works ----------------------------------------------------------
_WORK_CUE_RE = re.compile(
    r"\b(?:the\s+)?(?:film|movie|novel|book|poem|song|painting|documentary|series|album|memoir|"
    r"musical|play|opera|ballet|show|story)s?\s+(?:called|titled|entitled|named)?\s*"
    r"(?:[\"“‘']\s*)?(" + _TOK + r"(?:\s+(?:" + _CONN + r"\s+){0,2}" + _TOK + r"){0,5})")
_WORK_INTRO_RE = re.compile(
    r"(?i)\b(featured in|appeared in|appears in|was filmed|were filmed|shot at|inspired|"
    r"inspiration for|immortali[sz]ed|depicted in|set in|wrote|written|painted|made famous)\b")


def named_work_claims(sentence: str, blob: str, stop_title: str = "",
                      location: str = "") -> List[str]:
    """A film/novel/song/... the sentence ties to the place that no source names."""
    stop_tokens = _title_tokens(stop_title, location)
    cands: List[str] = []
    for m in _WORK_CUE_RE.finditer(sentence):
        cands.append(m.group(1))
    if _WORK_INTRO_RE.search(sentence):
        cands += [q for q in (m.group(1) for m in _QUOTED_RE.finditer(sentence))]
    bad = []
    bf = " ".join(re.findall(r"[a-z0-9]+", blob))
    for c in cands:
        toks = [t for t in re.findall(_TOK, c) if t not in _STOP_CAPS]
        if not toks and not _QUOTED_RE.search(f'"{c}"'):
            continue
        folded = [_fold(t) for t in re.findall(_TOK, c)]
        if folded and all(f in stop_tokens for f in folded):
            continue
        cf = " ".join(re.findall(r"[a-z0-9]+", _fold(c)))
        if len(cf) >= 3 and cf not in bf and c not in bad:
            bad.append(c)
    return bad


# ---- 5. dated claims ---------------------------------------------------------
_YEAR_RE = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?![\d])")
_DATE_CUE_RE = re.compile(
    r"(?i)\b(built|construct\w+|completed|finished|opened|reopen\w*|inaugurat\w+|founded|"
    r"establish\w+|erected|designed|renovat\w+|restor\w+|destroyed|burn\w*|damaged|rebuilt|"
    r"staged|hosted|held|premier\w+|performed|signed|declared|proclaimed|designated|"
    r"named|renamed|became|moved|relocated|dedicated|consecrated|unveiled|launched|"
    r"expanded|demolished|captured|seized|occupied|fell|took place|since)\b")


def dated_claims(sentence: str, blob: str, known: str = "") -> List[str]:
    if not _DATE_CUE_RE.search(sentence):
        return []
    bad = []
    hay = blob + " " + _fold(known)
    for y in _YEAR_RE.findall(sentence):
        if not re.search(r"(?<!\d)" + y + r"(?!\d)", hay):
            bad.append(y)
    return bad


# ---- the gate ----------------------------------------------------------------
_STRUCTURAL_RE = _mcg._STRUCTURAL_RE
_LABEL_RE = re.compile(r"\s*(Coordinates|Address|Type(?:/Specialty)?|Specific Examples|Directions)\s*:")


_DANGLING_RE = re.compile(
    r"(?i)^\s*(?:(?:this|that|these|those|such)\s+(?:production|performance|show|staging|run|season|"
    r"musical|event|festival|ceremony|premiere|concert|recital|film|novel|work|"
    r"success|tradition|legacy|fame|reputation)s?\b|"
    r"(?:the|these)\s+(?:productions|performances|shows)\b)")


def _blob(evidence: Iterable[str], known: Iterable[str] = ()) -> str:
    return _fold(" \n ".join([e for e in evidence if e] + [k for k in known if k]))


def unsourced_claims(sentence: str, stop_title: str, evidence: Sequence[str],
                     known: Iterable[str] = (), location: str = "",
                     aliases: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """[(kind, claim_span)] for every claim in the sentence no source supports."""
    blob = _blob(evidence)
    kn = [k for k in known if k]
    out: List[Tuple[str, str]] = []
    for t in production_claims(sentence, stop_title, evidence, location, aliases):
        out.append(("production", t))
    for n in named_person_claims(sentence, blob + " " + _fold(" ".join(kn)), stop_title, location):
        out.append(("person", n))
    for e in named_event_claims(sentence, blob + " " + _fold(" ".join(kn)), stop_title, location):
        out.append(("event", e))
    for w in named_work_claims(sentence, blob + " " + _fold(" ".join(kn)), stop_title, location):
        out.append(("work", w))
    for y in dated_claims(sentence, blob, " ".join(kn)):
        out.append(("date", y))
    return out


def claim_span_lines(kind: str, claim: str, sentence: str) -> str:
    """The research-log form the LOCAL-864 checker reads: ``UNSOURCED: '<span>'``."""
    span = claim
    if kind == "production":
        m = re.search(r"[^.;,]{0,40}" + re.escape(claim), sentence)
        span = _norm_ws(m.group(0)) if m else claim
    return f"UNSOURCED: '{span}'"


def filter_stop_body(body: str, evidence: Sequence[str], stop_title: str = "",
                     known: Iterable[str] = (), location: str = "",
                     aliases: Iterable[str] = (), flagged: Iterable[str] = ()
                     ) -> Tuple[str, List[Dict]]:
    """Drop the sentences of one stop body that make an unsourced claim.
    Returns (new_body, [{'sentence','kind','claim','reason'}])."""
    removed: List[Dict] = []
    paras = re.split(r"(\n\s*\n)", body)
    flat: List[Tuple[int, str]] = []
    for pi, seg in enumerate(paras):
        if seg.strip() and not re.fullmatch(r"\n\s*\n", seg):
            for ln_i, ln in enumerate(seg.split("\n")):
                if _LABEL_RE.match(ln):
                    continue
                for s in _sentences(ln):
                    flat.append((pi, s))
    sents = [s for _, s in flat]
    flagged_l = [f for f in flagged if f and f.strip()]
    drop: Dict[int, Tuple[str, str]] = {}
    for i, s in enumerate(sents):
        if is_disclosed(s) or _STRUCTURAL_RE.match(s):
            continue
        if any(_mcg._span_hit(f, s) for f in flagged_l):
            drop[i] = ("flagged", "flagged UNSOURCED by the verifier")
            continue
        cl = unsourced_claims(s, stop_title, evidence, known, location, aliases)
        if cl:
            drop[i] = (cl[0][0], cl[0][1])
            if len(cl) > 1:
                drop[i] = (cl[0][0], "; ".join(c for _, c in cl))
    # dangling references left by a drop go with it
    for i in sorted(list(drop)):
        j = i + 1
        while (j < len(sents) and j not in drop and not is_disclosed(sents[j])
               and (_mcg._PRONOUN_OPEN_RE.match(sents[j]) or _mcg._BACKREF_ANY_RE.search(sents[j])
                    or _DANGLING_RE.match(sents[j]))):
            drop[j] = ("dangling", "refers back to a dropped unsourced sentence")
            j += 1
    if not drop:
        return body, removed
    kill: Dict[int, List[str]] = {}
    for i, (kind, claim) in drop.items():
        pi, s = flat[i]
        kill.setdefault(pi, []).append(s)
        removed.append({"sentence": s, "kind": kind, "claim": claim,
                        "reason": f"unsourced {kind} claim: {claim}"})
    out = []
    for pi, seg in enumerate(paras):
        if pi not in kill:
            out.append(seg)
            continue
        new = seg
        for s in kill[pi]:
            new = new.replace(s, "", 1)
        new = re.sub(r"[ \t]{2,}", " ", new)
        new = re.sub(r"[ \t]+\n", "\n", new)
        new = re.sub(r"\n{2,}", "\n", new)
        out.append(new.strip(" "))
    text = "".join(out)
    text = re.sub(r"(\n[ \t]*){3,}", "\n\n", text)
    return text, removed


def filter_tour_text(tour_text: str, stop_evidence: Optional[Dict[int, List[str]]] = None,
                     stop_known: Optional[Dict[int, List[str]]] = None,
                     stop_titles: Optional[Dict[int, str]] = None,
                     stop_flagged: Optional[Dict[int, List[str]]] = None,
                     stop_aliases: Optional[Dict[int, List[str]]] = None,
                     skip_stops: Iterable[int] = (), location: str = ""
                     ) -> Tuple[str, Dict]:
    """Apply the gate to every ``Stop N:`` body.  ``skip_stops`` are stop numbers
    another verifier already covers (business user stops, LOCAL-855D)."""
    report = {"stops": 0, "scanned": 0, "dropped": 0, "changed": False, "removed": []}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report
    skip = set(skip_stops or ())
    out = [parts[0]]
    i, n = 1, 0
    while i < len(parts):
        header, body = parts[i], (parts[i + 1] if i + 1 < len(parts) else "")
        n += 1
        report["stops"] += 1
        title = (stop_titles or {}).get(n) or re.sub(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*", "", header).strip()
        if n in skip:
            out.extend([header, body])
            i += 2
            continue
        # keep a trailing conclusion / sources block (last stop) untouched
        main, tail = body, ""
        if i + 2 >= len(parts):
            cut = _mcg._tail_cut(header + body) - len(header)
            if 0 <= cut < len(body):
                main, tail = body[:cut], body[cut:]
        report["scanned"] += 1
        new_main, removed = filter_stop_body(
            main, (stop_evidence or {}).get(n, []), title, (stop_known or {}).get(n, []),
            location, (stop_aliases or {}).get(n, []), (stop_flagged or {}).get(n, []))
        report["dropped"] += len(removed)
        for r in removed:
            r = dict(r)
            r["stop"] = n
            report["removed"].append(r)
        out.extend([header, new_main + tail])
        i += 2
    report["changed"] = bool(report["dropped"])
    return "".join(out), report
