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
    "filter_tour_text", "claim_span_lines", "is_borderline", "disclose",
    "contradicts_evidence", "fill_empty_stops", "ensure_evidence_dates", "correct_build_range", "evidence_fact_for", "minimal_body",
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
        # a name any source (or the stop's own names) gives as "<name> Temple/Lake/..."
        # is a PLACE ("crowned by Ngoc Son" = Ngoc Son Temple), not a person
        _pn = "|".join(x.lower() for x in _PLACE_NOUNS)
        _nf = re.escape(_fold(n))
        if re.search(r"\b" + _nf + r"\s+(?:" + _pn + r")\b", blob + " " + kn + " " + _fold(sentence)):
            continue
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
# [LOCAL-879 §4] A century ordinal, with an optional "beginning/early/mid/late/end
# of the" qualifier — "the 19th century", "the beginning of the 19th century".
_CENTURY_RE = re.compile(
    r"(?i)\b(?:(?:the\s+)?(?:beginning|start|early|mid(?:dle)?|late|end|turn)\s+of\s+)?"
    r"the\s+(\d{1,2})(?:st|nd|rd|th)\s+century\b")
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
    # [LOCAL-879 §4] A CENTURY-level date is a dated claim too. Tour 547's Pier
    # said "established at the beginning of the 19th century" — no year, so the
    # year scan above never saw it, and the claim shipped unsourced. A "Nth
    # century" attached to a construction/founding verb must appear in a source
    # (the century ordinal or an equivalent year inside it). Only flag when the
    # evidence does NOT mention that century at all.
    for cm in _CENTURY_RE.finditer(sentence):
        ordinal = cm.group(1)                  # "19"
        try:
            cnum = int(ordinal)
        except ValueError:
            continue
        # The century is sourced when the evidence names the same ordinal century
        # OR carries any year that falls inside it (e.g. 1805 for the 19th).
        folded_phrase = _fold(cm.group(0))
        if folded_phrase in hay:
            continue
        if re.search(r"(?<!\d)" + re.escape(ordinal) + r"\s*(?:st|nd|rd|th)\s+century", hay):
            continue
        lo, hi = (cnum - 1) * 100 + 1, cnum * 100
        if any(lo <= int(y) <= hi for y in _YEAR_RE.findall(hay)):
            continue
        bad.append(cm.group(0).strip())
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


# ---- 872B: disclosure over deletion for borderline claims ---------------------
# A plausible claim about the venue's OWN history (when it was built / opened /
# consecrated, who designed it) that no source holds is DISCLOSED (D760) instead of
# dropped.  A named production / performer / event / work stays a DROP: an invented
# show is worse than none.
_HISTORY_VERB_RE = re.compile(
    r"(?i)\b(built|construct\w+|complet\w+|finished|opened|inaugurat\w+|founded|establish\w+|"
    r"erected|designed|design|architect\w*|engineer\w*|consecrat\w+|dedicated|blessed|"
    r"renovat\w+|restor\w+|rebuilt|expanded|commissioned|renamed|named|began|begun|"
    r"started|unveiled|reopen\w*|destroyed|damaged)\b")
_PERFORMER_RE = re.compile(
    r"(?i)\b(perform\w*|sang|sing\w*|conduct\w*|starred|played|play|premier\w+|hosted|"
    r"attended|visited|toured|appeared|concert|recital|staged|screened|speech|spoke|"
    r"addressed|signed|met|stayed|lived|died|born|killed|arrested|escaped|fled)\b")
_LOWER_OK = frozenset("the a an it its this that these those built inside outside "
                      "today now from after before during since in on at as by another later then soon "
                      "eventually originally finally first next over with when while once "
                      "although though despite because there here some many most each every "
                      "several after-wards afterwards meanwhile initially later".split())


def is_borderline(sentence: str, claims: Sequence[Tuple[str, str]]) -> bool:
    """True when every unsourced claim is a date or an architect/builder-type person
    in a sentence about the venue's own history, with no performance cue."""
    if not claims:
        return False
    if any(k not in ("date", "person") for k, _ in claims):
        return False
    if _PERFORMER_RE.search(sentence) or not _HISTORY_VERB_RE.search(sentence):
        return False
    for k, c in claims:
        if k == "date":
            # [LOCAL-879 §4] Only a precise YEAR is a borderline (disclose-able)
            # claim about the venue's own history. A CENTURY-level founding date
            # ("established at the beginning of the 19th century") is speculation,
            # not a near-sourced fact — it is dropped, never laundered behind a
            # "sometimes said" hedge (Michael's Pier PASS criterion).
            if not re.fullmatch(r"\d{3,4}", c or ""):
                return False
            if not (1000 <= int(c) <= 2100):
                return False
    return True


# ---- 872C: a claim that CONTRADICTS the evidence is dropped, never disclosed ----
# Wave 35: "built in 1885" (evidence: 1962-1966, architect Ngo Viet Thu) was softened to
# "It is sometimes said ... 1885", laundering a false date.  Disclosure is only for what
# the evidence neither supports nor contradicts.
_CORE_BUILT_RE = re.compile(
    r"(?i)\b(built|construct\w*|completed|finished|opened|inaugurat\w+|erected|founded|"
    r"establish\w+)\b")
_DESIGN_CUE_RE = re.compile(
    r"(?i)\b(designed|design|architect\w*|plans?|blueprints?|drawn up|engineered|"
    r"built by|constructed by|created by)\b")


# [LOCAL-879 §4] EVIDENCE-TEXT CONTRADICTIONS.
#
# The gate's claim kinds (date/person/event/work/production) did not catch two
# false claims in tour 547 that the stop's OWN Wikipedia evidence contradicts:
#
#  (a) Stop 4 (Independence Palace): "This assassination … took place within the
#      walls of the still-unfinished palace." FALSE — the evidence says Diệm and
#      Nhu were killed in an armoured personnel carrier after fleeing to Cholon.
#  (b) Stop 5 (War Remnants Museum): "a building that once served as the U.S.
#      military's intelligence headquarters." The evidence names the United
#      States Information Agency building — "information", not "intelligence".
#
# Both are deterministic contradictions against the evidence blob and are DROPPED
# (an invented location / wrong identity is worse than silence). No disclosure.

# A violent-death / assassination placed AT the venue ("within the walls",
# "inside the palace", "here at <venue>", "in the building").
_DEATH_AT_VENUE_RE = re.compile(
    r"(?i)\b(assassinat\w+|killed|murder\w+|execut\w+|shot dead|died)\b[^.]*?"
    r"\b(?:within the walls|inside|in the (?:building|palace|grounds|compound)|"
    r"at (?:the )?(?:site|palace|building)|here)\b")
# Evidence markers that the death happened ELSEWHERE than the venue.
_DEATH_ELSEWHERE_RE = re.compile(
    r"(?i)\b(armou?red personnel carrier|\bapc\b|in a vehicle|in the back of|"
    r"cholon|chợ lớn|cho lon|after (?:they )?fled|having fled|outside the|"
    r"en route|on the way|in a convoy|at a church|in a truck|in the m113)\b")
# The "intelligence" vs "Information Agency" identity contradiction. Consume the
# "the U.S./US military's" prefix so the correction reads cleanly.
_INTEL_HQ_RE = re.compile(
    r"(?i)(?:the\s+)?(?:u\.?\s?s\.?(?:\s+military)?(?:'s|’s)?\s+|american\s+|"
    r"military(?:'s|’s)?\s+)?intelligence\s+(?:headquarters|hq|agency|service|building)\b")
_INFO_AGENCY_RE = re.compile(
    r"(?i)\b(information agency|united states information|u\.?\s?s\.?\s?i\.?\s?a\.?|usia)\b")


def evidence_text_contradiction(sentence: str, evidence_blob: str
                                ) -> Optional[Tuple[str, str, Optional[str]]]:
    """(kind, reason, replacement) when the sentence asserts something the evidence
    text itself contradicts. ``replacement`` is a corrected sentence when the
    contradiction can be fixed in place (the 'intelligence' -> 'Information
    Agency' identity), else None (drop the sentence — a death placed at the venue
    the evidence puts elsewhere). ``evidence_blob`` is the folded concatenation of
    the stop's evidence."""
    if not sentence or not evidence_blob:
        return None
    blob = evidence_blob
    # (a) Death-at-venue vs death-elsewhere — DROP (no honest in-place fix).
    if _DEATH_AT_VENUE_RE.search(sentence) and _DEATH_ELSEWHERE_RE.search(blob):
        return ("contradiction",
                "places a death at the venue the Wikipedia evidence puts elsewhere",
                None)
    # (b) "intelligence" where the evidence says "Information Agency". The former
    # use named by the sentence CONTRADICTS the former use named by the evidence.
    # [LOCAL-880 §1] Generalise LOCAL-879: DROP the contradicted sentence even when
    # the correct fact is also present. Wave 38 shipped BOTH "once housed the
    # United States Information Agency" (correct, sourced) AND "served as the US
    # military's intelligence headquarters" (false) in the same paragraph — the
    # old in-place correction turned the false sentence into a duplicate of the
    # correct one instead of removing it. When the evidence names the Information
    # Agency as the building's former use, a sentence that instead calls it an
    # intelligence HQ is dropped outright (the correct fact stands on its own).
    if (_INTEL_HQ_RE.search(sentence) and _INFO_AGENCY_RE.search(blob)):
        return ("contradiction",
                "calls the building an 'intelligence' HQ for the slot the evidence "
                "names the United States Information Agency",
                None)
    # (c) [LOCAL-880 §1] General FORMER-USE contradiction: a sentence that asserts
    # the building "served as / was / housed <role>" for a role that the evidence
    # contradicts with a DIFFERENT named role for the same slot. Only fires on the
    # specific intelligence/information clash above for now (kept deterministic and
    # evidence-bound); the structure is here so a future role clash extends (b).
    return None


# A hedge/attribution wrapper the narrator sometimes drapes over a claim.
_HEDGE_LEAD_RE = re.compile(
    r"(?i)^\s*(it is sometimes said that|it is said that|some say that|"
    r"according to (?:some|legend|local lore)|legend (?:has it|says) that|"
    r"it is believed that|some believe that|it is sometimes claimed that|"
    r"it is often said that)\s+")

def _has_century_claim(claims) -> bool:
    """True when any unsourced claim is a CENTURY-level date (not a 4-digit year).
    A century founding date is speculation and always drops, even in an otherwise
    well-sourced sentence (the Pier 'beginning of the 19th century')."""
    return any(k == "date" and not re.fullmatch(r"\d{3,4}", str(c or ""))
               for k, c in (claims or ()))



def _claim_well_sourced(sentence: str, evidence_blob: str) -> bool:
    """[LOCAL-879 §4] True when a distinctive cluster of the sentence's content
    words is in the evidence — the signal that its claim is sourced, used both to
    unwrap a hedge and to refuse to disclose (so the gate is idempotent).

    Matching is tolerant of accents and inflection: a sentence token counts as a
    hit when its 5-letter prefix begins a word in the evidence ("bombing" matches
    "bombed", "dissident" matches "dissident"). This keeps the signal from
    breaking on Vietnamese accents the fold leaves in place or on an -ing/-ed
    stem difference between the narration and the Wikipedia lead."""
    if not sentence or not evidence_blob:
        return False
    toks = [t for t in re.findall(r"[0-9a-zà-ÿđ]{4,}", _fold(sentence))
            if t not in _HEDGE_STOPWORDS]
    if len(toks) < 3:
        return False
    ev_words = set(re.findall(r"[0-9a-zà-ÿđ]{3,}", evidence_blob))
    ev_prefixes = {w[:5] for w in ev_words}
    hits = set()
    for t in set(toks):
        if t in ev_words or t[:5] in ev_prefixes:
            hits.add(t)
    return len(hits) >= 3


def unwrap_sourced_hedge(sentence: str, evidence_blob: str
                         ) -> Optional[str]:
    """[LOCAL-879 §4] Strip a 'sometimes said'/'it is said' hedge off a sentence
    whose claim the evidence SUPPORTS. Tour 547 hedged the SOURCED 1962 bombing of
    the palace by dissident pilots ("It is sometimes said that … damaged by
    bombing from dissident pilots"). A hedge laundering a sourced fact
    understates the evidence; remove it when the sentence's key content words are
    present in the evidence. Returns the de-hedged sentence, or None when the
    claim is NOT supported (then the hedge is honest and stays)."""
    m = _HEDGE_LEAD_RE.match(sentence or "")
    if not m:
        return None
    rest = sentence[m.end():].strip()
    if not rest:
        return None
    # Only a HISTORY/date hedge is unwrapped. A production/performer/event/work
    # hedge stays disclosed (D760): "It is sometimes said that the Opera House
    # staged productions of Miss Saigon" is a properly-disclosed unsourced claim
    # and must NOT be laundered into a bare assertion.
    if _PROD_CUE_RE.search(rest) or _PERFORMER_RE.search(rest):
        return None
    if not _HISTORY_VERB_RE.search(rest):
        return None
    if _claim_well_sourced(rest, evidence_blob or ""):
        return rest[0].upper() + rest[1:]
    return None


_HEDGE_STOPWORDS = frozenset(
    "this that these those with from into over under about after before during "
    "when while which were have been they them their there here then than also "
    "could would should still such many some most each every other another "
    "palace building site venue".split())


def contradicts_evidence(sentence: str, claims: Sequence[Tuple[str, str]],
                         auth: Optional[Dict]) -> Optional[Tuple[str, str]]:
    """(kind, claim) when an unsourced date / person in the sentence contradicts what the
    stop's Wikipedia evidence itself says (a different construction year; a different
    architect), else None.  ``auth`` is ``landmark_wikipedia_evidence.authority()``."""
    if not auth or not claims:
        return None
    for kind, claim in claims:
        if (kind == "date" and auth.get("years") and _CORE_BUILT_RE.search(sentence)
                and claim not in auth["years"]):
            return kind, claim
        if (kind == "person" and auth.get("architects") and _DESIGN_CUE_RE.search(sentence)):
            return kind, claim
    return None


_RANGE_RE = re.compile(
    r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(\s*(?:-|–|—|to|and)\s*)(1[0-9]{3}|20[0-9]{2})(?!\d)")


def correct_build_range(sentence: str, auth: Optional[Dict]) -> Optional[str]:
    """A construction sentence giving a year RANGE that overlaps, but is not, the range
    the evidence states ("constructed between 1877 and 1880" vs Wikipedia 1863-1880)
    gets the evidence's range.  None when nothing to correct."""
    if not auth or not auth.get("range") or not _CORE_BUILT_RE.search(sentence):
        return None
    a0, b0 = auth["range"]
    m = _RANGE_RE.search(sentence)
    if not m or (m.group(1), m.group(3)) == (a0, b0):
        return None
    a1, b1 = int(m.group(1)), int(m.group(3))
    if a1 > b1 or not (int(a0) <= a1 <= int(b0) and int(a0) <= b1 <= int(b0)):
        return None
    return sentence[:m.start()] + a0 + m.group(2) + b0 + sentence[m.end():]


def evidence_fact_for(kind: str, auth: Dict, name: str = "") -> str:
    """The evidence's own statement to put where a contradicted sentence stood."""
    if kind == "date":
        if auth.get("built_sentence"):
            return auth["built_sentence"]
        if auth.get("built_value"):
            return f"It was built {auth['built_value']}."
    if kind == "person":
        if auth.get("architect_sentence"):
            return auth["architect_sentence"]
        if auth.get("architect_value"):
            return f"Its architect was {auth['architect_value']}."
    return ""


_NONBODY_RE = re.compile(r"(?i)^\s*(Orientation|Directions|Coordinates|Address|Type(?:/Specialty)?|"
                         r"Specific Examples)\s*:")


def _has_real_sentence(body: str) -> bool:
    """True when the stop has at least one narration sentence of its own.  Orientation,
    Directions and label lines are not narration (wave 35/36: Bach Dang Pier shipped
    with an Orientation line and Directions only)."""
    for ln in (body or "").split("\n"):
        if _LABEL_RE.match(ln) or _NONBODY_RE.match(ln):
            continue
        for s in _sentences(ln):
            if len(s.split()) >= 4 and not _STRUCTURAL_RE.match(s):
                return True
    return False


def _insert_body(body: str, text: str) -> str:
    """Put ``text`` as its own paragraph before the Directions: line (else at the end)."""
    m = re.search(r"(?mi)^[ \t]*Directions\s*:", body)
    if m:
        return body[:m.start()].rstrip("\n") + "\n\n" + text + "\n\n" + body[m.start():]
    return body.rstrip() + "\n\n" + text + "\n"


def fill_empty_stops(tour_text: str, stop_titles: Optional[Dict[int, str]] = None,
                     stop_authority: Optional[Dict[int, List[str]]] = None,
                     stop_fallback: Optional[Dict[int, str]] = None,
                     location: str = "") -> Tuple[str, List[Dict]]:
    """D760 / LOCAL-872C: NO stop ships without a body, whichever pass emptied it.  Fill
    with the evidence short form (2-4 sentences from the Wikipedia lead/infobox), else the
    D759 grounded body, else a minimal name-and-place body.  Every stop, user stops
    included.  Idempotent."""
    filled: List[Dict] = []
    if not tour_text:
        return tour_text, filled
    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, filled
    out = [parts[0]]
    i, n = 1, 0
    while i < len(parts):
        header, body = parts[i], (parts[i + 1] if i + 1 < len(parts) else "")
        n += 1
        main, tail = body, ""
        if i + 2 >= len(parts):
            cut = _mcg._tail_cut(header + body) - len(header)
            if 0 <= cut < len(body):
                main, tail = body[:cut], body[cut:]
        if not _has_real_sentence(main):
            title = (stop_titles or {}).get(n) or re.sub(r"(?i)^\s*Stop\s+\d+\s*[:\-]\s*", "", header).strip()
            short, src = "", "wikipedia"
            try:
                import landmark_wikipedia_evidence as _lwe
                short = _lwe.short_form(title, (stop_authority or {}).get(n, []))
            except Exception:
                short = ""
            if not short:
                short, src = (stop_fallback or {}).get(n) or "", "grounded"
            if not short:
                short, src = minimal_body(title, location), "minimal"
            main = _insert_body(main, short)
            filled.append({"stop": n, "source": src, "text": short})
        out.extend([header, main + tail])
        i += 2
    return "".join(out), filled


def minimal_body(name: str, location: str = "") -> str:
    where = (location or "").split(",")[0].strip()
    first = f"{name} is one of the stops on this walk" + (f", in {where}." if where else ".")
    return first + " Take a moment to look at it and get your bearings before you move on."


def disclose(sentence: str) -> str:
    """'It is sometimes said that <sentence>' (D760).  Lower-cases the first letter only
    for a function word; a proper noun keeps its capital."""
    s = sentence.strip()
    first = re.match(r"[A-Za-z]+", s)
    if first and first.group(0).lower() in _LOWER_OK:
        s = s[0].lower() + s[1:]
    return "It is sometimes said that " + s


def claim_span_lines(kind: str, claim: str, sentence: str) -> str:
    """The research-log form the LOCAL-864 checker reads: ``UNSOURCED: '<span>'``."""
    span = claim
    if kind == "production":
        m = re.search(r"[^.;,]{0,40}" + re.escape(claim), sentence)
        span = _norm_ws(m.group(0)) if m else claim
    return f"UNSOURCED: '{span}'"


def _filter_stop_body_core(body: str, evidence: Sequence[str], stop_title: str = "",
                     known: Iterable[str] = (), location: str = "",
                     aliases: Iterable[str] = (), flagged: Iterable[str] = (),
                     disclose_borderline: bool = True,
                     disclosures: Optional[List[Dict]] = None,
                     authority_items: Sequence[str] = (),
                     protected: Sequence[str] = ()
                     ) -> Tuple[str, List[Dict]]:
    """Drop the sentences of one stop body that make an unsourced claim.
    Returns (new_body, [{'sentence','kind','claim','reason'}]).

    [LOCAL-880 §5] A sentence strongly supported by one of ``protected`` (the
    signature story's source sentence) is never dropped or softened."""
    removed: List[Dict] = []
    # [LOCAL-880 §5] distinctive-token sets of the protected source sentences.
    _prot_tok_sets = []
    for _ps in (protected or ()):
        _pt = {t for t in re.findall(r"[0-9a-zà-ÿđ]{4,}", _fold(_ps or ""))
               if t not in _HEDGE_STOPWORDS}
        if len(_pt) >= 3:
            _prot_tok_sets.append(_pt)

    def _is_protected(_sentence: str) -> bool:
        if not _prot_tok_sets:
            return False
        _st = {t for t in re.findall(r"[0-9a-zà-ÿđ]{4,}", _fold(_sentence or ""))
               if t not in _HEDGE_STOPWORDS}
        if len(_st) < 3:
            return False
        return any(len(_st & _pt) >= 3 for _pt in _prot_tok_sets)
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
    soften: Dict[int, Tuple[str, str]] = {}
    replace: Dict[int, str] = {}
    dehedge: Dict[int, Tuple[str, str]] = {}  # [LOCAL-879 §4] i -> (orig, de-hedged)
    auth: Dict = {}
    if authority_items:
        try:
            import landmark_wikipedia_evidence as _lwe
            auth = _lwe.authority(authority_items)
        except Exception:
            auth = {}
    used_facts: set = set()
    _ev_blob = _blob(evidence)
    for i, s in enumerate(sents):
        # [LOCAL-879 §4] A "sometimes said"/"it is said" hedge over a SOURCED fact
        # understates the evidence. It reads as DISCLOSED, so test it FIRST (before
        # the is_disclosed skip) and unwrap it when the claim's distinctive content
        # words are in the evidence. The de-hedged sentence is then screened for any
        # OTHER unsourced claim below.
        _dehedged = unwrap_sourced_hedge(s, _ev_blob)
        if _dehedged and _dehedged != s:
            dehedge[i] = (s, _dehedged)
            s = _dehedged
        if (is_disclosed(s) and i not in dehedge) or _STRUCTURAL_RE.match(s):
            continue
        # [LOCAL-880 §5] NEVER remove a sourced signature story. A sentence that is
        # strongly supported by a protected source sentence is kept as-is: the gate
        # does not drop, soften or disclose it. (A signature story's source is in
        # the evidence by construction, so this cannot shelter a contradiction.)
        if _is_protected(s):
            continue
        if any(_mcg._span_hit(f, s) for f in flagged_l):
            drop[i] = ("flagged", "flagged UNSOURCED by the verifier")
            continue
        fixed = correct_build_range(s, auth)
        if fixed:
            drop[i] = ("contradiction", f"construction range contradicts the Wikipedia evidence ({auth['range'][0]}-{auth['range'][1]})")
            replace[i] = fixed
            continue
        # [LOCAL-879 §4] Evidence-text contradictions the claim-kind scan misses:
        # a death placed at the venue the evidence puts elsewhere; an
        # "intelligence" identity the evidence records as "Information Agency".
        _etc = evidence_text_contradiction(s, _ev_blob)
        if _etc:
            _kind, _reason, _repl = _etc
            drop[i] = (_kind, _reason)
            if _repl and _repl != s:
                replace[i] = _repl      # correct in place (keeps the sourced identity)
            continue
        # [LOCAL-879 §4] A "sometimes said" hedge was handled above; screen the
        # (possibly de-hedged) sentence for any unsourced claim.
        cl = unsourced_claims(s, stop_title, evidence, known, location, aliases)
        if cl:
            span = "; ".join(c for _, c in cl)
            con = contradicts_evidence(s, cl, auth)
            if con:
                drop[i] = ("contradiction", f"{con[1]} (contradicts the Wikipedia evidence)")
                fact = evidence_fact_for(con[0], auth, stop_title)
                # state the evidence fact once, unless the body already states it
                already = (con[0] == "date" and any(
                    re.search(r"(?<!\d)" + y + r"(?!\d)", " ".join(sents[:i] + sents[i + 1:]))
                    for y in auth.get("years", ())))
                if con[0] == "person":
                    already = any(_fold(a.split()[-1]) in _fold(" ".join(sents[:i] + sents[i + 1:]))
                                  for a in auth.get("architects", ()) if a.split())
                if fact and not already and fact not in used_facts:
                    used_facts.add(fact)
                    replace[i] = fact
            elif (is_borderline(s, cl) and _claim_well_sourced(s, _ev_blob)
                  and not _has_century_claim(cl)
                  and all(k == "date" for k, _ in cl)):
                # A well-sourced history sentence whose ONLY unsourced claim is an
                # incidental precise year/decade (e.g. "early 1960s" beside a
                # sourced 1962 bombing): keep it plain. Disclosing it would launder
                # nothing and, on a de-hedged sentence, re-add a hedge on the next
                # pass (non-idempotent). A CENTURY date or a person/production claim
                # is NOT covered here.
                pass
            elif disclose_borderline and is_borderline(s, cl) and i not in dehedge:
                soften[i] = (cl[0][0], span)
            elif i in dehedge and not _has_century_claim(cl) \
                    and all(k in ("date", "person") for k, _ in cl):
                # Idempotency guard for an unwrapped sourced hedge (see above); not
                # extended to production/event/work (a fabricated show still drops).
                pass
            else:
                drop[i] = (cl[0][0], span)
    # dangling references left by a drop go with it
    for i in sorted(list(drop)):
        if i in replace:
            continue   # the evidence fact stands where it stood: nothing dangles
        j = i + 1
        while (j < len(sents) and j not in drop and not is_disclosed(sents[j])
               and (_mcg._PRONOUN_OPEN_RE.match(sents[j]) or _mcg._BACKREF_ANY_RE.search(sents[j])
                    or _DANGLING_RE.match(sents[j]))):
            drop[j] = ("dangling", "refers back to a dropped unsourced sentence")
            j += 1
    if not drop and not soften and not dehedge:
        return body, removed
    kill: Dict[int, List[str]] = {}
    swap: Dict[int, List[Tuple[str, str]]] = {}
    # [LOCAL-879 §4] De-hedge swaps first, but a sentence also marked drop/soften
    # is handled there (drop wins; soften re-hedges differently).
    for i, (orig, news) in dehedge.items():
        if i in drop or i in soften:
            continue
        pi, _s = flat[i]
        swap.setdefault(pi, []).append((orig, news))
        removed.append({"sentence": orig, "kind": "sourced-hedge",
                        "claim": "", "reason": "unwrapped 'sometimes said' hedge "
                        "over a sourced fact"})
    for i, (kind, claim) in drop.items():
        pi, s = flat[i]
        if i in replace:
            swap.setdefault(pi, []).append((s, replace[i]))
        else:
            kill.setdefault(pi, []).append(s)
        removed.append({"sentence": s, "kind": kind, "claim": claim,
                        "reason": f"unsourced {kind} claim: {claim}"})
    for i, (kind, claim) in soften.items():
        pi, s = flat[i]
        new_s = disclose(s)
        swap.setdefault(pi, []).append((s, new_s))
        if disclosures is not None:
            disclosures.append({"sentence": s, "disclosed_as": new_s, "kind": kind,
                                "claim": claim,
                                "reason": f"unsourced {kind} claim about the venue's own history: {claim}"})
    out = []
    for pi, seg in enumerate(paras):
        if pi not in kill and pi not in swap:
            out.append(seg)
            continue
        new = seg
        for s0, s1 in swap.get(pi, []):
            new = new.replace(s0, s1, 1)
        for s in kill.get(pi, []):
            new = new.replace(s, "", 1)
        new = re.sub(r"[ \t]{2,}", " ", new)
        new = re.sub(r"[ \t]+\n", "\n", new)
        new = re.sub(r"\n{2,}", "\n", new)
        out.append(new.strip(" "))
    text = "".join(out)
    text = re.sub(r"(\n[ \t]*){3,}", "\n\n", text)
    return text, removed


_CLAUSE = {"established": "established in {y}", "founded": "founded in {y}",
           "begun": "begun in {y}", "opened": "opened in {y}", "completed": "completed in {y}",
           "built": "built in {y}"}


def ensure_evidence_dates(body: str, auth: Optional[Dict]) -> Tuple[str, str]:
    """The evidence's own establishment / start / opening / completion years the stop
    never states are added once as 'It was ...' (only when the stop states no year at all).  Wave 36: the
    narrator wrote Notre-Dame 'completed 1880' and dropped the infobox's 'established
    1863'.  Returns (body, added_sentence or '')."""
    if not auth or not auth.get("dated"):
        return body, ""
    dated, seen_y = [], set()
    for k, y in auth["dated"]:
        if y not in seen_y:
            seen_y.add(y)
            dated.append((k, y))
    has = lambda y: re.search(r"(?<!\d)" + y + r"(?!\d)", body)
    none_stated = not any(has(y) for _, y in dated)
    # [LEAD 872C review] Add evidence dates only when the stop states NO year at all.
    # A stop that already says "constructed between 1877 and 1880" is right as written;
    # bolting "it was established in 1863" onto it reads like a footnote.
    missing = [(k, y) for k, y in dated if not has(y) and none_stated]
    if not missing:
        return body, ""
    passive = [_CLAUSE[k].format(y=y) for k, y in missing if k != "begun"]
    began = [y for k, y in missing if k == "begun"]
    parts = []
    if passive:
        parts.append("It was " + (" and ".join(passive) if len(passive) < 3
                     else ", ".join(passive[:-1]) + " and " + passive[-1]) + ".")
    if began:
        parts.append("Construction"
                     + f" began in {began[0]}.")
    sent = " ".join(parts)
    ys = set(auth.get("years") or ())
    # after the first PROSE sentence stating an evidence year; else at the end of the last
    # prose paragraph (before Directions:/labels); never inside a label line
    pos, last_end = 0, -1
    for ln in body.split("\n"):
        start, pos = pos, pos + len(ln) + 1
        st = ln.strip()
        if not st or _LABEL_RE.match(ln) or re.match(r"(?i)^(Directions|Orientation)\s*:", st):
            continue
        last_end = start + len(ln.rstrip())
        for m in re.finditer(r"[^.!?]+[.!?]", ln):
            if any(re.search(r"(?<!\d)" + y + r"(?!\d)", m.group(0)) for y in ys):
                at = start + m.end()
                return body[:at] + " " + sent + body[at:], sent
    if last_end >= 0:
        return body[:last_end] + " " + sent + body[last_end:], sent
    return body, ""


def filter_stop_body(body: str, evidence: Sequence[str], stop_title: str = "",
                     known: Iterable[str] = (), location: str = "",
                     aliases: Iterable[str] = (), flagged: Iterable[str] = (),
                     disclose_borderline: bool = True,
                     disclosures: Optional[List[Dict]] = None,
                     authority_items: Sequence[str] = (),
                     protected: Sequence[str] = ()
                     ) -> Tuple[str, List[Dict]]:
    new, removed = _filter_stop_body_core(
        body, evidence, stop_title, known, location, aliases, flagged,
        disclose_borderline, disclosures, authority_items, protected)
    if authority_items and _has_real_sentence(new):
        try:
            import landmark_wikipedia_evidence as _lwe
            new, _added = ensure_evidence_dates(new, _lwe.authority(authority_items))
        except Exception:
            pass
    return new, removed


def filter_tour_text(tour_text: str, stop_evidence: Optional[Dict[int, List[str]]] = None,
                     stop_known: Optional[Dict[int, List[str]]] = None,
                     stop_titles: Optional[Dict[int, str]] = None,
                     stop_flagged: Optional[Dict[int, List[str]]] = None,
                     stop_aliases: Optional[Dict[int, List[str]]] = None,
                     skip_stops: Iterable[int] = (), location: str = "",
                     disclose_borderline: bool = True,
                     stop_authority: Optional[Dict[int, List[str]]] = None,
                     stop_fallback: Optional[Dict[int, str]] = None,
                     stop_protected: Optional[Dict[int, List[str]]] = None
                     ) -> Tuple[str, Dict]:
    """Apply the gate to every ``Stop N:`` body.  ``skip_stops`` are stop numbers
    another verifier already covers (business user stops, LOCAL-855D).

    [LOCAL-880 §5] ``stop_protected`` maps a stop number to a list of PROTECTED
    source sentences (the signature story's ``source_sentence``): a body sentence
    strongly supported by one of them is NEVER dropped or softened. Gating must
    never remove a sourced signature story."""
    report = {"stops": 0, "scanned": 0, "dropped": 0, "changed": False, "removed": [],
              "disclosed": []}
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
        disc: List[Dict] = []
        new_main, removed = filter_stop_body(
            main, (stop_evidence or {}).get(n, []), title, (stop_known or {}).get(n, []),
            location, (stop_aliases or {}).get(n, []), (stop_flagged or {}).get(n, []),
            disclose_borderline=disclose_borderline, disclosures=disc,
            authority_items=(stop_authority or {}).get(n, []),
            protected=(stop_protected or {}).get(n, []))
        # 872C / D760: a stop never ships empty (see fill_empty_stops)
        if not _has_real_sentence(new_main):
            _one, _f = fill_empty_stops("Stop 1: " + title + "\n" + new_main + "\nStop 2: x\n",
                                        {1: title}, {1: (stop_authority or {}).get(n, [])},
                                        {1: (stop_fallback or {}).get(n, "")}, location)
            if _f:
                new_main = _STOP_HEADER_RE.split(_one)[2]
                report.setdefault("filled", []).append(dict(_f[0], stop=n))
        for d in disc:
            d["stop"] = n
            report["disclosed"].append(d)
        report["dropped"] += len(removed)
        for r in removed:
            r = dict(r)
            r["stop"] = n
            report["removed"].append(r)
        out.extend([header, new_main + tail])
        i += 2
    report["changed"] = bool(report["dropped"] or report["disclosed"] or report.get("filled"))
    return "".join(out), report
