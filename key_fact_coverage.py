#!/usr/bin/env python3
"""key_fact_coverage.py — LOCAL-889.

Three generic, venue-free finishing rules for a grounded stop (D769: no venue name,
date or claim is hard-coded; everything is read from the stop's own evidence):

1. KEY-FACT COVERAGE. The stop's key facts are extracted deterministically from its
   evidence LEAD (construction/completion years, architect/designer, the dated
   defining event). After ALL passes (gate, refill, coherence) each key fact must
   appear in the stop; a missing one is repaired with ONE plain sentence built from
   the evidence sentence, gated once more. Variance between runs (the same stop
   lost "1898-1909" or the 1944 bombing in one run and kept it in the next) is
   closed by checking the end state, not by hoping the narrator repeats itself.
2. REMOVED CLAIMS STAY REMOVED. Every sentence a gate/scrub removed is recorded in
   a per-stop deny-set as a normalised claim key (its specific tokens). Any later
   pass that reintroduces a sentence matching a recorded claim drops it again, and
   the evidence line that "supports" it is logged.
3. FILLER CAP. At most ONE sensory sentence per stop (the most concrete/visible
   one); reflective sentences that state no fact and no visible detail are dropped,
   and a reflective trailing clause ("... , a reminder that ...") is trimmed off a
   sentence that does carry a fact.

Plus deterministic UNSUPPORTED rules the LLM judge kept missing: a year (or a year
RANGE) that no evidence sentence states, and a departure bound to a date on which
the evidence records a different act (a resignation).

Every LLM call goes through an injectable ``classify_fn`` (see strict_grounding_gate).
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from sentence_split import split_sentences

__all__ = [
    "deny_record", "deny_reset", "deny_claims", "claim_key", "is_denied",
    "strip_denied", "support_source", "record_removed_between",
    "key_facts", "fact_present", "coverage_report",
    "is_sensory", "is_reflective", "trim_reflective_tail", "cap_filler",
    "deterministic_unsupported", "finalize_stop", "finalize_tour",
]

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_MON = (r"January|February|March|April|May|June|July|August|September|October|"
        r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_DMY = re.compile(rf"(?i)\b(\d{{1,2}})\s+({_MON})\.?,?\s+(\d{{4}})\b")
_MDY = re.compile(rf"(?i)\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")


def _fold(s: str) -> str:
    raw = str(s or "").lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", raw)
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    out = re.sub(r"[^\w\s]", " ", out)
    return " ".join(out.split())


def _sents(text: str) -> List[str]:
    return [s.strip() for s in split_sentences(re.sub(r"\s+", " ", text or "")) if s.strip()]


# ═════════════ 2. per-stop deny-set of removed claims ═════════════
_GENERIC = frozenset("""
the and but for with from into onto over under about after before during while when where which that this
these those their there here then than also very just only even ever still once were was has had have been
being are its his her our your they them she you not can may will would could should who whom what why how
building buildings served serves serving occupies occupied occupy stands stand standing located known
called named place site today now later around across along between within without through became become
becomes remains remain one two three many most more some such each both other another same own
""".split())


def claim_key(sentence: str, title: str = "") -> frozenset:
    """The specific tokens of a claim: folded words of >= 4 letters (or any year)
    that are neither generic nor part of the stop's own title. Pure."""
    title_toks = set(_fold(title).split())
    toks = set()
    parts = _fold(sentence).split()
    for i, w in enumerate(parts):
        if w.isdigit() and len(w) == 4:
            toks.add(w)
            continue
        if len(w) < 5 or w in _GENERIC or w in title_toks:
            continue
        toks.add(w[:-1] if w.endswith("s") and len(w) > 5 else w)
    # the last token of a fragment cut mid-word ("...intelligence hea") is unreliable
    return frozenset(toks)


def _lower_toks(sentence: str) -> frozenset:
    """Folded words that appear in lower case in the original (the predicate side;
    capitalised place/person names are not evidence of the same claim)."""
    out = set()
    for w in re.findall(r"[^\W\d_]{4,}", sentence or ""):
        if w[0].islower():
            f = _fold(w)
            out.add(f[:-1] if f.endswith("s") and len(f) > 5 else f)
    return frozenset(out)


_DENY: Dict[str, List[Dict]] = {}
_DENY_LOCK = threading.Lock()


def deny_reset() -> None:
    with _DENY_LOCK:
        _DENY.clear()


def deny_record(title: str, sentence: str, source: str = "") -> bool:
    """Remember that ``sentence`` was REMOVED from stop ``title``. Returns True when
    a claim key was stored. A fragment (cut at ~100 chars) is fine."""
    s = (sentence or "").strip()
    if len(s) < 25:
        return False
    toks = claim_key(s, title)
    if not re.search(r"[.!?\u201d\"]$", s):          # a fragment cut mid-word: its last token is unreliable
        last = _fold(s).split()[-1:] or [""]
        toks = frozenset(t for t in toks if not last[0].startswith(t) and t != last[0])
    if len(toks) < 2:
        return False
    with _DENY_LOCK:
        lst = _DENY.setdefault(_fold(title), [])
        if any(e["key"] == toks for e in lst):
            return True
        lst.append({"key": toks, "text": s[:160], "source": source, "lower": _lower_toks(s)})
    return True


def deny_claims(title: str) -> List[Dict]:
    with _DENY_LOCK:
        return list(_DENY.get(_fold(title), []))


# Removal sources that are a VERDICT on the claim. Regeneration / style removals
# (Phase 5.17 "removed by gates", off-pin, foreign-entity, filler) are not: the 889
# live run showed them carrying the stop's sourced 30 April 1975 event and its
# architect credit, which a deny-set must never block.
_HARD = ("gate:deterministic", "contested", "880-scrub-former-use")
_SOFT = ("gate:CONTRADICTED", "gate:UNSUPPORTED")


def _near_verbatim(sentence: str, evidence: str, title: str) -> bool:
    """>= 85% of the sentence's specific tokens sit in ONE prose sentence of the
    stop's own article (a restatement of the article, not of a narrator claim)."""
    key = claim_key(sentence, title)
    if len(key) < 2 or not evidence:
        return False
    d = _date_tuple(sentence)
    nums = set(re.findall(r"\b\d+\b", sentence))
    for x in prose_sentences(evidence, title):
        if len(key & claim_key(x, title)) < math.ceil(0.85 * len(key)):
            continue
        # every date and number must be the article's own (1 May != 30 April)
        if d and _date_tuple(x) != d:
            continue
        if not nums <= set(re.findall(r"\b\d+\b", x)):
            continue
        return True
    return False


def is_denied(title: str, sentence: str, evidence: str = "") -> Optional[Dict]:
    """The recorded removed claim ``sentence`` repeats, else None. A match needs >= 2
    shared specific tokens, >= 60% of the recorded key and >= 50% of the new one, and
    a shared lower-case (predicate) token. An LLM-verdict entry (soft) does not block
    a near-verbatim sentence of the stop's own article: the article outranks a judge
    that flaked on it (889: the gate CONTRADICTED the article's own 30 April 1975
    sentence). Deterministic / contested / scrub entries (hard) always block."""
    cands = deny_claims(title)
    if not cands:
        return None
    key = claim_key(sentence, title)
    low = _lower_toks(sentence)
    verbatim = None
    for e in cands:
        if e.get("source") not in _HARD + _SOFT:
            continue
        shared = key & e["key"]
        if len(shared) < 2 or not (shared & e["lower"]) or not (shared & low):
            continue
        if len(shared) < math.ceil(0.6 * len(e["key"])) or len(shared) < math.ceil(0.5 * len(key)):
            continue
        if e.get("source") in _SOFT:
            if verbatim is None:
                verbatim = _near_verbatim(sentence, evidence, title)
            if verbatim:
                continue
        return e
    return None


def support_source(sentence: str, evidence: str, title: str = "") -> str:
    """Which evidence line 'supports' ``sentence`` (best token overlap), with the
    article header it sits under when there is one. For the diagnostic log."""
    key = claim_key(sentence, title)
    if not key or not evidence:
        return ""
    best, best_n, head = "", 0, ""
    cur_head = ""
    for part in re.split(r"(?<=[.!?])\s+|\n+", evidence):
        m = re.search(r"([^.\n]{3,80}?)\s-\sWikipedia\s*\(([a-z-]+)\)", part)
        if m:
            cur_head = f"{m.group(1).strip()} - Wikipedia ({m.group(2)})"
        n = len(key & claim_key(part, title))
        if n > best_n:
            best, best_n, head = part.strip(), n, cur_head
    if best_n < 2:
        return ""
    return f"{head or 'snippet/other source'}: \"{best[:200]}\""


def strip_denied(title: str, sentences: List[str], evidence: str = "",
                 log: Optional[Callable] = None, where: str = "") -> Tuple[List[str], List[str]]:
    """Drop every sentence repeating a recorded removed claim. Returns (kept, dropped)."""
    kept, dropped = [], []
    for s in sentences:
        hit = is_denied(title, s, evidence)
        if hit:
            dropped.append(s)
            if log:
                log(f"  [LOCAL-889] {where or 'pass'} re-dropped removed claim in '{title[:40]}': "
                    f"\"{s[:100]}\" (removed earlier by {hit.get('source') or 'a gate'}: "
                    f"\"{hit['text'][:70]}\")")
                src = support_source(s, evidence, title)
                log(f"      [LOCAL-889] evidence line backing it: {src or '(none found)'}")
        else:
            kept.append(s)
    return kept, dropped


def record_removed_between(before_text: str, after_text: str, source: str) -> int:
    """Record every sentence that vanished from a stop between two tour texts."""
    import strict_grounding_gate as sgg
    n = 0
    after = {num: _sents(sgg._block_body_prose(body)) for num, _t, body in sgg._split_blocks(after_text)}
    for num, title, body in sgg._split_blocks(before_text):
        left = {_fold(s) for s in after.get(num, [])}
        for s in _sents(sgg._block_body_prose(body)):
            if _fold(s) not in left and deny_record(title, s, source):
                n += 1
    return n


# ═════════════ 1. key facts ═════════════
_BUILD_VERB = re.compile(
    r"(?i)\b(built|constructed|construction|completed|completion|opened|inaugurated|"
    r"erected|broke\s+ground|commenced)\b")
_BUILD_WEAK = re.compile(r"(?i)\b(designed|founded|established|dedicated|consecrated|began|started)\b")
_PARTICLES = r"(?:de|da|del|della|di|van|von|der|den|le|la|du|bin|al)"
_NAME_TOK = r"[A-ZÀ-Ý][\wÀ-ÿ'’.-]+"
_ARCH_RE = re.compile(
    rf"(?:designed|built|constructed|planned|created|drawn\s+up|engineered)\s+by\s+"
    rf"(?:the\s+)?(?:[A-Za-z-]+\s+)?(?:architects?\s+|engineer\s+|firm\s+)?"
    rf"((?:{_NAME_TOK})(?:\s+(?:{_PARTICLES}\s+)?{_NAME_TOK}){{0,3}})"
    rf"|(?:architects?|designer|engineer)\s+((?:{_NAME_TOK})(?:\s+(?:{_PARTICLES}\s+)?{_NAME_TOK}){{1,3}})")
_NOT_PERSON = frozenset(_fold(w) for w in """
French American Vietnamese English German Chinese Japanese Italian Spanish British Soviet
Colonial Government Administration Committee Council Company Society Ministry Department
Republic Empire Kingdom Army Party The A An In On At By
""".split())
_KIND = frozenset(("river city street palace hall cathedral church temple museum square market "
                   "bridge gate tower park garden pier station boulevard avenue road bank house "
                   "office university school hotel theatre theater opera basilica").split())
_FAMOUS = re.compile(
    r"(?i)\b(tanks?|crashed\s+through|stormed|fall\s+of|captured|seized|surrender\w*|"
    r"assassinat\w+|coup|bomb(?:ed|ing|s)?|massacre|siege|uprising|riots?|executed|"
    r"escaped|burn(?:ed|t)|destroyed|collapsed|earthquake|hurricane|sank|shipwreck\w*|"
    r"occupied|liberated|damaged|shelled|invaded)\b")
_WIKI_HEAD = re.compile(r"(?i)\s-\s*Wikipedia\s*\([a-z-]+\)\.?\s")


_HEAD_RE = re.compile(r"([A-ZÀ-Ỹ0-9][^.\n]{1,90}?) - Wikipedia \(([A-Za-z-]+)\)\.\s")


def articles(evidence: str) -> List[Dict]:
    """The Wikipedia items inside a stop's evidence blob, each split into title, lang,
    lead, infobox and passages (landmark_wikipedia_evidence.format_item shape)."""
    ev = evidence or ""
    heads = list(_HEAD_RE.finditer(ev))
    out = []
    for i, m in enumerate(heads):
        seg = ev[m.start():heads[i + 1].start() if i + 1 < len(heads) else len(ev)]
        try:
            import landmark_wikipedia_evidence as lwe
            p = lwe.split_item(seg)
        except Exception:
            p = {"title": m.group(1), "lang": m.group(2), "lead": seg[m.end() - m.start():],
                 "infobox": "", "passages": ""}
        p["title"] = p.get("title") or m.group(1).strip()
        out.append(p)
    return out


def stop_article(evidence: str, title: str) -> Optional[Dict]:
    """The stop's OWN article: most title tokens shared with the article title (an
    English article wins a tie), else the first article of the bundle."""
    arts = articles(evidence)
    if not arts:
        return None
    ttoks = {t for t in _fold(title).split() if len(t) >= 3}

    def score(i_a):
        i, a = i_a
        return (len(ttoks & set(_fold(a["title"]).split())), a.get("lang") == "en", -i)
    return max(enumerate(arts), key=score)[1]


_OWN_STOP = frozenset(("the", "and", "of", "de", "la", "le", "du", "des", "in", "at", "on"))


def _own_tokens(name: str) -> set:
    return {t for t in _fold(name).split() if len(t) >= 3 and t not in _OWN_STOP}


def _lead_subject(lead: str) -> str:
    """The subject part of an article's first sentence (before 'is/was/are')."""
    first = (_sents(_clean_ev_sentence_loose(lead)) or [""])[0]
    m = re.search(r"\b(?:is|was|are|were)\b", first)
    if not m:
        return first[:120]
    # the subject, plus the kind noun of the predicate ("... is a cathedral in ...")
    pred = re.match(r"\s*(?:now\s+)?(?:an?|the)\s+((?:[\w'’-]+\s+){0,3}[\w'’-]+)", first[m.end():])
    return first[:m.start()] + " " + (pred.group(1) if pred else "")


def _clean_ev_sentence_loose(t: str) -> str:
    t = re.sub(r"\s*\([^()]{0,300}\)", "", t or "")
    return re.sub(r"\s+", " ", t).strip()


def own_article(evidence: str, title: str) -> Optional[Dict]:
    """[LOCAL-890] The stop's OWN article, or None.

    The bundle holds the articles the name/geo gate (878/883/887 ``_pick`` +
    ``title_covers_name``) accepted, but a bundle can hold a NEIGHBOUR's article too
    (the square that surrounds a cathedral). The own article is the one whose TITLE
    or whose lead's SUBJECT ("<X> is a ...") carries a distinctive token of the
    stop's name. A single-article bundle is that article (it was gated) unless its
    title fails ``title_covers_name``. Text that is not a Wikipedia article (a
    snippet, a thin fact, a signature page) is never an own article: a stop with
    only those has no key facts."""
    arts = articles(evidence)
    if not arts:
        return None
    t = _own_tokens(title)
    try:
        import landmark_wikipedia_evidence as lwe
        cov = lambda a: lwe.title_covers_name(title, a["title"])           # noqa: E731
    except Exception:
        cov = lambda a: True                                                # noqa: E731

    def score(i_a):
        i, a = i_a
        sc = 2 * len(t & _own_tokens(a["title"])) + len(t & _own_tokens(_lead_subject(a.get("lead", ""))))
        return (sc, a.get("lang") == "en", -i)
    ranked = sorted(((score(x), x[1]) for x in enumerate(arts)), key=lambda z: z[0], reverse=True)
    best_sc, best = ranked[0]
    # a single gated article is still the CITY's article when neither its title nor
    # its lead subject carries a token of the stop's name
    if best_sc[0] <= 0 or not cov(best):
        return None
    return best


_REF_NOUNS = frozenset(("building", "structure", "edifice", "complex", "site", "venue", "premises"))
_SUBJ_PRON = re.compile(
    r"(?i)^(?:(?:in|on|by|from|during|after|before|since|until|between)\b[^,]{0,45},\s*)?"
    r"(?:it|this|the\s+(?:building|structure|edifice|complex|site|venue))\s+"
    r"(?:was|is|has|had|were|became|remains?|served|stands?|housed|suffered|survived|reopened|opened|"
    r"hosted|saw|witnessed)\b")


def referent_tokens(title: str, art: Optional[Dict]) -> set:
    """Distinctive tokens that name the stop: its own name's, and its own article
    title's."""
    out = _own_tokens(title)
    if art:
        out |= _own_tokens(art.get("title", ""))
    return out - _KIND - set(_REF_NOUNS)


def about_stop(sentence: str, title: str, art: Optional[Dict]) -> bool:
    """[LOCAL-890] True when ``sentence`` is about THE STOP: it names the stop (or
    its own article's title, or the building/structure) or its subject is a
    pronoun ('It was ...', 'The building ...') whose antecedent is the own article's
    subject. 'renamed it X Square' (the stop is only a pronoun OBJECT) is not."""
    if art is None:
        return False
    ft = set(_fold(sentence).split())
    ref = referent_tokens(title, art)
    if ref & ft:
        return True
    if (_own_tokens(title) & _KIND) & ft:                  # the stop is just 'Cathedral', 'Pier'
        return True
    if re.search(r"(?i)\bthe\s+(?:building|structure|edifice|complex|theatre|theater|church|cathedral|"
                 r"basilica|temple|pagoda|mosque|museum|palace|castle|fortress|hall|hotel|station|tower|"
                 r"pier|market|library|gallery|opera|post\s+office)\b", sentence):
        return True
    return bool(_SUBJ_PRON.search(sentence.strip()))


def own_prose_sentences(evidence: str, title: str = "") -> List[str]:
    """Prose sentences of the stop's OWN article only ([] when it has none)."""
    art = own_article(evidence, title)
    if art is None:
        return []
    out = []
    for t in (art.get("lead", ""), art.get("passages", "")):
        for x in _sents(_strip_markers(t)):
            x = _clean_ev_sentence(x)
            if 25 <= len(x) <= 420 and not re.search(r"(?i)\binfobox\b|;\s*[a-z ]{2,25}:\s", x):
                out.append(x)
    return out


def _strip_markers(t: str) -> str:
    t = re.sub(r"\[[^\]\n]{1,60}\]\s*", " ", t or "")            # [History] section tags
    t = re.sub(r"={2,}[^=\n]{1,60}={2,}", " ", t)
    return t


def prose_sentences(evidence: str, title: str = "") -> List[str]:
    """Prose sentences of the stop's own article (lead first, then passages). Infobox
    field lists are NOT prose and never become narration. With no article in the
    blob, the blob's own sentences (minus any Infobox line)."""
    art = stop_article(evidence, title)
    if art is None:
        blob = re.sub(r"(?m)^\s*Infobox:.*$", " ", evidence or "")
        texts = [blob]
    else:
        texts = [art.get("lead", ""), art.get("passages", "")]
    out = []
    for t in texts:
        for x in _sents(_strip_markers(t)):
            x = _clean_ev_sentence(x)
            if 25 <= len(x) <= 420 and not re.search(r"(?i)\binfobox\b|;\s*[a-z ]{2,25}:\s", x):
                out.append(x)
    return out


def evidence_prose(evidence: str) -> str:
    """The whole evidence minus Infobox field lists (for mechanical support checks)."""
    return re.sub(r"(?m)^\s*Infobox:.*$", " ", evidence or "")


def _date_tuple(s: str) -> Optional[Tuple[int, str, int]]:
    m = _DMY.search(s)
    if m:
        return int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
    m = _MDY.search(s)
    if m:
        return int(m.group(2)), m.group(1).lower()[:3], int(m.group(3))
    return None


def _clean_ev_sentence(s: str) -> str:
    s = re.sub(r"={2,}[^=\n]{1,60}={2,}", " ", s)          # '== History ==' markers
    s = re.sub(r"\[[^\]]{0,12}\]", "", s)
    s = re.sub(r"\s*\([^()]{0,160}\)", "", s)           # (Vietnamese: ...) asides
    return re.sub(r"\s+", " ", s).strip(" ;")


def key_facts(evidence: str, title: str = "") -> List[Dict]:
    """Deterministic KEY FACTS of a landmark stop, read from its evidence lead:
      years     construction/completion years (all years of the first lead sentence
                with a building verb, <= 3);
      architect the designer named after 'designed by'/'architect';
      event     the dated defining event (full date + event verb, else the best
                famous-event sentence that carries a year).
    Each fact: {kind, sentence, ...match data}. Pure; [] when nothing is found."""
    facts: List[Dict] = []
    if not (evidence or "").strip():
        return facts
    art_sents = own_prose_sentences(evidence, title)       # [LOCAL-890] own article only
    lead_sents = art_sents
    if not art_sents:
        return facts
    _own = own_article(evidence, title)
    _NOT_BUILD = re.compile(r"(?i)\b(prize|born|died|award\w*|won|degree|graduat\w+|"
                            r"renovat\w+|restor\w+|refurbish\w+|rebuil\w+|repair\w*)\b")
    built = [x for x in art_sents if _BUILD_VERB.search(x) and _YEAR.search(x)
             and not _NOT_BUILD.search(x)] \
        or [x for x in art_sents if _BUILD_WEAK.search(x) and _YEAR.search(x)
            and not _NOT_BUILD.search(x)]
    if built:
        ys = list(dict.fromkeys(_YEAR.findall(built[0])))
        sent = built[0]
        if len(ys) == 1:                       # start year + completion year
            _near = re.compile(r"(?i)\b(?:completed|completion|inaugurated|opened|finished|"
                               r"built|constructed)\b[^.;]{0,45}?\b(1[0-9]{3}|20[0-9]{2})\b")
            for x in built[1:6]:
                extra = [m.group(1) for m in _near.finditer(x) if m.group(1) not in ys]
                extra = list(dict.fromkeys(extra))
                if extra and len(ys) + len(extra) <= 3:
                    ys = sorted(ys + extra)
                    sent = x
                    break
        facts.append({"kind": "years", "years": ys[:3], "sentence": sent,
                      "sentences": [built[0], sent]})
    built_years = [int(y) for f in facts if f["kind"] == "years" for y in f["years"]]
    for s in lead_sents:
        # a later redesign/extension ("In 2018 ... rear blocks ... designed by X") is
        # not the building's architect
        if built_years and any(int(y) > max(built_years) + 20 for y in _YEAR.findall(s)):
            continue
        if re.search(r"(?i)\b(renovat\w+|restor\w+|extension|annex\w*|rear\s+blocks?|new\s+design)\b", s):
            continue
        for m in _ARCH_RE.finditer(s):
            name = (m.group(1) or m.group(2) or "").strip(" .,'’")
            toks = [t for t in name.split() if t]
            if not toks:
                continue
            if all(_fold(t) in _NOT_PERSON or _fold(t) in _KIND for t in toks):
                continue
            while toks and (_fold(toks[0]) in _NOT_PERSON or _fold(toks[0]) in _KIND):
                toks = toks[1:]
            if not toks or any(_fold(t) in _KIND for t in toks):
                continue
            surname = _fold(toks[-1].strip(".,'’-"))
            if len(surname) >= 3:
                facts.append({"kind": "architect", "name": " ".join(toks),
                              "surname": surname, "sentence": s})
                break
        if any(f["kind"] == "architect" for f in facts):
            break
    ev_fact = _event_fact(" ".join(art_sents), lead_sents, title, _own)
    if ev_fact:
        facts.append(ev_fact)
    return facts


def _event_fact(evidence: str, lead_sents: List[str], title: str = "",
                art: Optional[Dict] = None) -> Optional[Dict]:
    """The dated defining event: a famous-event sentence (tank, bombing, coup, fall,
    damaged ...) with a full date or a year. 887/888's scorers (signature_event for
    full dates, landmark_wikipedia_evidence.event_sentences for the rest); a dated
    sentence with no event cue (a journal quote, an opening date) is not an event."""
    cands: List[str] = []
    try:
        import stop_coherence as sc
        e = sc.signature_event(evidence)
        if e:
            cands.append(e["sentence"])
    except Exception:
        pass
    try:
        import landmark_wikipedia_evidence as lwe
        cands += lwe.event_sentences(evidence, 4)
    except Exception:
        pass
    cands += [x for x in lead_sents if _FAMOUS.search(x) and _YEAR.search(x)]  # whole article text
    # a physical event to the building (bombed, damaged, burned, a tank at the gate) is
    # the stop's defining event before a political "After the Fall of ..." aftermath;
    # a full-dated signature sentence (first candidate) still leads
    _PHYS = re.compile(r"(?i)\b(bomb\w*|damag\w+|destroy\w*|burn(?:ed|t)|collaps\w+|earthquake|shell(?:ed|ing)|"
                       r"tanks?|crashed|stormed|massacre|siege|sank|shipwreck\w*|fire)\b")
    head, tail = cands[:1], cands[1:]
    if head and not _PHYS.search(head[0]) and not _DMY.search(head[0]) and not _MDY.search(head[0]):
        head, tail = [], cands
    cands = head + sorted(tail, key=lambda c: 0 if _PHYS.search(c) else 1)
    for c in cands:
        c = _clean_ev_sentence(c)
        if not (25 <= len(c) <= 420) or not _FAMOUS.search(c):
            continue
        ys = _YEAR.findall(c)
        if not ys:
            continue
        # [LOCAL-890] the event must be ABOUT THE STOP and well-formed
        if art is None or not about_stop(c, title, art):
            continue
        if garbled(c):
            continue
        return {"kind": "event", "date": _date_tuple(c), "year": ys[0], "sentence": c}
    return None


def fact_present(sentences: List[str], fact: Dict) -> bool:
    text = " ".join(sentences)
    k = fact["kind"]
    if k == "years":
        have = set(_YEAR.findall(text))
        return all(y in have for y in fact["years"])
    if k == "architect":
        return re.search(rf"\b{re.escape(fact['surname'])}\b", _fold(text)) is not None
    if k == "event":
        for s in sentences:
            if not _FAMOUS.search(s):
                continue
            if fact.get("date") and _date_tuple(s) == fact["date"]:
                return True
            if fact["year"] in _YEAR.findall(s):
                return True
        return False
    return True


def coverage_report(sentences: List[str], facts: List[Dict]) -> Dict:
    miss = [f for f in facts if not fact_present(sentences, f)]
    return {"K": len(facts), "k": len(facts) - len(miss), "missing": miss}


# ═════════════ 3. filler ═════════════
_SENSORY = re.compile(
    r"(?i)\b(hum(?:s|med|ming)?|murmur\w*|clatter\w*|rustl\w*|creak\w*|whisper\w*|echo(?:es|ed)?|"
    r"scent\w*|smell\w*|aroma\w*|fragran\w*|perfume\w*|breeze\w*|hush\w*|"
    r"sounds?\s+of|the\s+sound|calls?\s+of|tuning|footsteps|chatter|buzz\w*|"
    r"warmth\s+of|glint\w*|gleam\w*|shimmer\w*|glow\w*|sunlight|"
    r"weathered|worn\s+smooth|smoothed|bears?\s+the\s+wear|texture|"
    r"you\s+(?:can\s+)?(?:hear|smell|feel)|punctuate\w*)\b")
_VISIBLE = re.compile(
    r"(?i)\b(stone|concrete|brick|iron|marble|wood\w*|glass|arch\w*|vault\w*|roof|"
    r"fa[cç]ade|towers?|columns?|dome|spire|statue|clock|balcon\w+|gate|steps|stair\w*|"
    r"courtyard|mosaic|tiles?|painted|carved|red|white|golden|green|blue)\b")
_REFLECTIVE = re.compile(
    r"(?i)(\ba\s+(?:quiet\s+|stark\s+|poignant\s+|living\s+)?reminder\b|"
    r"\bpast\s+and\s+(?:the\s+)?present\b|\bpresent\s+with\s+its\s+(?:layered\s+)?past\b|"
    r"\bweight\s+of\b|\bconceals?\s+more\b|\bmore\s+than\s+(?:its|a|an)\b[^.]{0,60}\bsuggests?\b|"
    r"\btestament\s+to\b|\bspeaks?\s+(?:volumes|to\s+the)\b|\bechoes?\s+of\s+(?:the\s+)?(?:past|history)\b|"
    r"\bwhisper\w*\s+(?:of|stories)\b|\bidentity\s+as\s+a\s+place\b|\ba\s+threshold\s+between\b|"
    r"\blinking\s+(?:people|the\s+rhythms)\b|\bconnect\w*\s+the\s+present\b|\bbridging\b|"
    r"\bpersonal\s+and\s+(?:the\s+)?political\b|\bnot\s+merely\b|\bsymbolic\s+\w+\b|"
    r"\breflects?\s+the\s+(?:sharp\s+|complex\s+|layered\s+)?(?:intersection|interplay|story|spirit|"
    r"journey|legacy|essence|tension)\b|\bstands?\s+in\s+(?:stark\s+)?contrast\s+to\b|"
    r"\b(?:tells|holds|carries)\s+a\s+(?:vivid\s+)?story\s+of\b|\bstory\s+of\s+reinvention\b|"
    r"\bcaptures?\s+a\s+moment\b|\bthe\s+pulse\s+of\b)")
_TAIL = re.compile(
    r"(?i),\s*(?:serving\s+as\s+|standing\s+as\s+|acting\s+as\s+|a\s+|an\s+|bridging\b|linking\b|"
    r"connecting\b|uniting\b|blending\b|anchoring\b|symboli[sz]ing\b)[^.!?]*"
    r"(?:reminder|past|present|bridging|linking|connecting|uniting|identity|symbol|testament)[^.!?]*(?=[.!?]?$)")


def _has_fact(s: str) -> bool:
    return bool(_YEAR.search(s) or _DMY.search(s) or _MDY.search(s))


def is_sensory(s: str) -> bool:
    """A sensory/atmospheric sentence: sound/scent/light cue and NO date or year."""
    return bool(_SENSORY.search(s)) and not _has_fact(s)


def is_reflective(s: str) -> bool:
    return bool(_REFLECTIVE.search(s))


def trim_reflective_tail(s: str) -> str:
    """'<fact>, a reminder that ...' -> '<fact>.' when the head keeps >= 6 words and
    does not itself end on a dangling word. Otherwise unchanged."""
    m = _TAIL.search(s.rstrip())
    if not m:
        return s
    head = s[:m.start()].rstrip(" ,;")
    if len(head.split()) < 6 or re.search(r"(?i)\b(?:and|or|of|the|a|an|to|with|from|in|on|by)$", head):
        return s
    return head + "."


def _concrete(s: str) -> int:
    return 2 * len(_VISIBLE.findall(s)) - len(re.findall(
        r"(?i)\b(hum\w*|murmur\w*|scent\w*|smell\w*|aroma\w*|echo\w*|whisper\w*|hush\w*)\b", s))


def cap_filler(sentences: List[str], min_keep: int = 3) -> Tuple[List[str], Dict]:
    """(1) trim reflective tails off sentences that carry a fact; (2) drop reflective
    sentences that state no fact and no visible detail; (3) keep at most ONE sensory
    sentence per stop, the most concrete/visible one (earliest on a tie). Never
    shrinks the stop below ``min_keep`` sentences by dropping a REFLECTIVE sentence
    that is the only one left; sensory sentences beyond the first are always dropped."""
    rep = {"trimmed": 0, "reflective_dropped": 0, "sensory_dropped": 0}
    cur: List[str] = []
    for s in sentences:
        t = trim_reflective_tail(s) if (is_reflective(s) or _TAIL.search(s)) else s
        if t != s:
            rep["trimmed"] += 1
        cur.append(t)
    out = []
    for s in cur:
        if is_reflective(s) and not _has_fact(s) and not _VISIBLE.search(re.sub(_REFLECTIVE, " ", s)) \
                and len(cur) - rep["reflective_dropped"] > min_keep:
            rep["reflective_dropped"] += 1
            continue
        if is_reflective(s) and not _has_fact(s) and is_sensory(s) \
                and len(cur) - rep["reflective_dropped"] > min_keep:
            rep["reflective_dropped"] += 1
            continue
        out.append(s)
    sens = [i for i, s in enumerate(out) if is_sensory(s)]
    if sens:
        keep = max(sens, key=lambda i: (_concrete(out[i]), -i))
        # a sensory sentence with no concrete, visible detail is not worth the slot
        if _concrete(out[keep]) <= 0 and len(out) - len(sens) >= min_keep:
            keep = -1
        rep["sensory_dropped"] = len([i for i in sens if i != keep])
        out = [s for i, s in enumerate(out) if i not in sens or i == keep]
    return out, rep


# ═════════════ deterministic UNSUPPORTED rules ═════════════
_RANGE = re.compile(r"(?i)\b(?:between|from)\s+(1[0-9]{3}|20[0-9]{2})\s+(?:and|to|until|through)\s+"
                    r"(1[0-9]{3}|20[0-9]{2})\b|\b(1[0-9]{3}|20[0-9]{2})\s*[-–—]\s*(1[0-9]{3}|20[0-9]{2})\b")
_DEPART = re.compile(r"(?i)\b(?:fled|flee|flees|left|leaves|departed|escaped|went\s+into\s+exile|"
                     r"went\s+into\s+exile|exiled|abandoned)\b")
_RESIGN = re.compile(r"(?i)\b(?:resign\w*|stepped\s+down|step\w*\s+down|abdicat\w*)\b")


_ID_FORMER = re.compile(
    r"(?i)\b(?:located|housed|situated|based)\s+in\s+the\s+former\s+([^.,;()]{3,80}?)\s+"
    r"(?:building|compound|premises|site)\b")
_ID_WAS = re.compile(
    r"(?i)\b(?:the|this)\s+(?:building|structure|site)\s+(?:was|had\s+been|served\s+as|"
    r"once\s+housed|was\s+once|formerly\s+housed)\s+(?:the\s+|an?\s+)?([^.,;()]{3,80}?)"
    r"(?=\s+(?:during|in|from|until|before|after|for)\b|[.,;]|$)")
_FORMER_CUE = re.compile(
    r"(?i)\b(?:once|former(?:ly)?|previously|originally|served\s+as|used\s+to\s+be|"
    r"had\s+been|housed\s+in|was\s+the)\b")
_ID_STOP = frozenset({"former", "building", "united", "states", "vietnam", "american"})


def _id_toks(phrase: str) -> frozenset:
    out = set()
    for w in _fold(phrase).split():
        if len(w) >= 4 and w not in _GENERIC and w not in _ID_STOP:
            out.add(w[:-1] if w.endswith("s") and len(w) > 5 else w)
    return frozenset(out)


def contested_identities(evidence: str, title: str = "") -> List[Tuple[str, frozenset]]:
    """Former identities of the BUILDING that the stop's evidence gives, when it gives
    two or more that share no specific token (e.g. 'located in the former X building'
    and 'the building was the Y headquarters'). [] when the evidence is consistent."""
    ids: List[Tuple[str, frozenset]] = []
    for x in prose_sentences(evidence, title) or _sents(evidence_prose(evidence)):
        for rx in (_ID_FORMER, _ID_WAS):
            for m in rx.finditer(x):
                ph = m.group(1).strip()
                tk = _id_toks(ph)
                if len(tk) >= 2 and not any(tk & t for _p, t in ids):
                    ids.append((ph, tk))
    return ids if len(ids) >= 2 else []


def deterministic_unsupported(sentence: str, evidence: str, title: str = "") -> Optional[str]:
    """A reason when ``sentence`` is NOT supported by ``evidence`` on purely
    mechanical grounds (None otherwise):
      * a year the evidence never states;
      * a year RANGE (between X and Y / X-Y) with an end that the evidence PROSE never
        states (an infobox field list such as 'years built: *1860-1863 (Former
        building)' is not a narrative statement);
      * a departure (fled/left) bound to a full date on which the evidence records a
        resignation and no departure: the sources disagree on what happened that day;
      * a former identity of the building that the stop's own evidence CONTESTS (it
        names two different former identities): the narration states neither.
    Only judged when the evidence is non-empty."""
    ev = evidence or ""
    if not ev.strip():
        return None
    ev_years = set(_YEAR.findall(ev))
    for y in _YEAR.findall(sentence):
        if y not in ev_years:
            return f"year {y} is not stated in the evidence"
    ev_sents = None
    for m in _RANGE.finditer(sentence):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        prose_years = set(_YEAR.findall(evidence_prose(ev)))
        for y in (a, b):
            if y not in prose_years:
                return (f"range {a}-{b}: {y} is stated only in an infobox field list, "
                        f"not in the evidence prose")
    d = _date_tuple(sentence)
    if d and _DEPART.search(sentence):
        if ev_sents is None:
            ev_sents = _sents(evidence_prose(ev))
        same_day = [x for x in ev_sents if _date_tuple(x) == d]
        if same_day and any(_RESIGN.search(x) for x in same_day) and \
                not any(_DEPART.search(x) and _RESIGN.search(x) for x in same_day):
            return (f"departure dated {d[0]} {d[1]} {d[2]} but the evidence records a "
                    f"resignation on that date (a different act)")
    if _FORMER_CUE.search(sentence):
        ids = contested_identities(ev, title)
        if ids:
            st = _id_toks(sentence)
            for ph, tk in ids:
                if len(st & tk) >= max(2, math.ceil(0.6 * len(tk))):
                    others = "; ".join(p for p, t in ids if t != tk)
                    return (f"contested former identity: the evidence says both '{ph}' "
                            f"and '{others}'")
    return None



# ═════════════ LOCAL-890: well-formedness of what the pass writes ═════════════
_SAME_NOUN = re.compile(
    r"\b(?:[Tt]he\s+)?[Ss]ame\s+(?!as\b|time\b|day\b|year\b|month\b|week\b|period\b|way\b|"
    r"place\b|spot\b|site\b|name\s+(?:as|of)\b|manner\b|era\b|century\b|decade\b)"
    r"[a-zà-ỹ-]+\s+(?:[a-zà-ỹ-]+ed\b|[A-Z][\w.]*)")


def garbled(s: str) -> Optional[str]:
    """[LOCAL-890] A cheap deterministic well-formedness check. Returns the reason, or
    None. Catches what a parenthesis strip / a sentence split at an abbreviation
    leaves behind: an unbalanced bracket, a stray '(', a doubled word, a noun phrase
    'the same name assassinated U.S. President' (same + noun + participle with no
    preposition), a sentence that opens on a lower-case or closing-bracket fragment."""
    t = (s or "").strip()
    if not t:
        return "empty"
    if t.count("(") != t.count(")"):
        return "unbalanced bracket"
    if re.match(r"^[^A-Za-z0-9\u00c0-\u1ef9\"'\u201c]", t) or re.match(r"^[a-z]", t):
        return "opens on a fragment"
    if re.match(r"^[\w .'’-]{1,40}\)", t):
        return "opens on a closing bracket"
    if re.search(r"(?i)\b([a-z]{3,})\s+\1\b", t):
        return "doubled word"
    if _SAME_NOUN.search(t):
        return "garbled noun phrase ('the same <noun> <participle>')"
    return None


_NAME_GLUE_NEXT = (r"(?:On|In|At|During|After|Before|Since|From|By|As|When|While|Between|Following|"
                   r"Although|However|Later|Today|The|It|He|She|They|There|Here)")


def strip_title_prefix(sentence: str, title: str) -> Tuple[str, bool]:
    """[LOCAL-890] 'Book Street On February 1, ...' -> ('On February 1, ...', True):
    the stop name glued to the front of a sentence with no punctuation. Only a
    function word can follow (a name continues with 'Cathedral Basilica ...')."""
    s = (sentence or "").strip()
    t = (title or "").strip()
    if t and s.lower().startswith(t.lower()):
        rest = s[len(t):]
        m = re.match(rf"^\s+({_NAME_GLUE_NEXT})\b", rest)
        if m and not re.match(r"^\s*[,;:.'’]", rest):
            return rest.strip(), True
    return s, False


_PREVIEW = re.compile(
    r"(?i)^from\s+here,?\s+(?:the\s+(?:tour|walk|route)|you|we)\s+(?:can|could|will|may|should|continue|head|walk|go)\b|"
    r"^(?:the\s+(?:tour|walk|route))\s+(?:continues|moves|heads|leads)\s+(?:on\s+)?(?:to|toward|towards)\b|"
    r"^(?:as|when|once|after)\s+you\s+(?:move|walk|continue|head|leave|go|proceed|make\s+your\s+way|"
    r"set\s+off|travel)\s+(?:on|onward|onwards|along|ahead|forward|from\s+here|away|to)\b|"
    r"\bnext\s+(?:stop|up|on\s+(?:the|your)\s+(?:tour|route|walk))\b|"
    r"^(?:in\s+a\s+(?:few|short)\s+(?:minutes|steps)|a\s+short\s+walk\s+(?:from\s+here|away))\b[^.]{0,80}\b"
    r"(?:you(?:'ll|\s+will)\s+(?:find|reach|arrive)|waits?|lies)\b")


def is_preview(s: str) -> bool:
    """[LOCAL-890] A sentence that previews the NEXT stop ('As you move on, a nearby
    museum preserves ...'): the Directions line does that."""
    return bool(_PREVIEW.search((s or "").strip()))


_TACKED = re.compile(r"(?i)^(?:it|this)\s+(?:was|is|has|had)\s+also\b|^(?:also|additionally|moreover|furthermore)\b")
_CONNECTIVE = re.compile(r"(?i)^(?:however|later|then|also|additionally|moreover|furthermore|meanwhile|"
                         r"subsequently|afterwards?|eventually|finally|thus|therefore|consequently),?\s+")
_PLACE_NOUNS = frozenset(("building", "structure", "site", "square", "street", "area", "place", "spot",
                          "park", "garden", "gardens", "pier", "port", "bridge", "gate", "church",
                          "cathedral", "basilica", "temple", "palace", "museum", "hall", "theatre",
                          "theater", "market", "station", "tower", "monument", "memorial", "complex",
                          "riverfront", "waterfront", "river", "city", "bar", "cafe", "café", "house",
                          "opera", "post", "office", "wharves", "wharf", "walls", "grounds", "venue"))


def orphan_opener(sentences: List[str], title: str = "", location: str = "") -> List[int]:
    """[LOCAL-890] Indices of sentences that open on something NO kept sentence supplies:
    the 888 dangling-demonstrative / lead-in rules, plus (for the FIRST sentence of
    a stop) a definite abstract noun such as 'The connection supported commerce ...'
    that the stop's title, the place nouns and the listener's own view do not
    introduce. Pure."""
    bad: List[int] = []
    try:
        import stop_coherence as sc
        bad = [i for i, k, f in sc.dangling_reference_issues(sentences, title, location)
               # "It was not until 1959 that a new statue ..." is a cleft, not a demonstrative
               if not (k == "demonstrative" and re.match(r"(?i)^that\s+(?:a|an|the|it|he|she|they|his|her|their|its)\b", f))]
    except Exception:
        pass
    if sentences and 0 not in bad:
        first = sentences[0].strip()
        m = re.match(r"^(?:The|This|That|These|Those)\s+([a-zà-ỹ][a-zà-ỹ'’-]*)", first)
        if m:
            noun = _fold(m.group(1).split("’")[0].split("'")[0])
            if noun and noun not in _PLACE_NOUNS and noun not in _own_tokens(title) and \
                    not re.match(r"(?i)^(?:the\s+)?(?:first|last|same|only|next|old|new|oldest|earliest|"
                                 r"following|city|capital|country|region|year|day|name)\b", first):
                bad.append(0)
    return sorted(set(bad))


# ── header lines: the body is never glued onto them ─────────────────────────
_SPLICE_NEXT = (r"(?:The|This|It|Its|You|Your|In|On|At|As|Here|Today|Built|Completed|Originally|"
                r"Standing|Beyond|Inside|Along|Located|Designed|Opened|Between|Constructed|Founded|"
                r"After|Before|During|Since|From|When|Once|Named|Welcome|Designed|Rising)")
_HDR_SPLICE = re.compile(rf"^(Type/Specialty|Specific Examples|Tour-Category|Address)\s*:\s*(.*)$")


def repair_header_splices(tour_text: str) -> Tuple[str, int]:
    """[LOCAL-890] A body sentence glued onto a header line ("Specific Examples: ...,
    illuminated at night The building before you was designed by ...", or after the
    Coordinates numbers) is moved to its own body paragraph. Header lines keep
    only their value. Returns (text, number of splices repaired). Idempotent."""
    out: List[str] = []
    n = 0
    for ln in (tour_text or "").split("\n"):
        m = re.match(r"^(Coordinates\s*:\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?)\s+(\S.*)$", ln)
        if m and re.match(r"^[A-Z]", m.group(2)):
            out += [m.group(1), "", m.group(2)]
            n += 1
            continue
        h = _HDR_SPLICE.match(ln)
        if h:
            val = h.group(2)
            sp = re.search(rf"(?<=[a-z0-9)])[ \t]+(?={_SPLICE_NEXT}\b)", val)
            if sp and len(val[sp.end():].split()) >= 6 and val[sp.end():].rstrip().endswith((".", "!", "?")):
                out += [f"{h.group(1)}: {val[:sp.start()].strip()}", "", val[sp.end():].strip()]
                n += 1
                continue
        out.append(ln)
    return "\n".join(out), n


def ground_header_items(tour_text: str, evidence_by_title: Dict[str, str],
                        log: Optional[Callable] = None) -> Tuple[str, List[Tuple[str, str]]]:
    """[LOCAL-890] Every 'Specific Examples' item must be STATED by the stop's evidence:
    all of the item's content words in ONE evidence sentence. An item that is not
    (stained glass, gardens: a generic header) is dropped; a stop left with no item
    loses the line. Returns (text, [(title, dropped item)]). Pure/offline."""
    import strict_grounding_gate as sgg
    norm = {sgg._fold(k): v for k, v in (evidence_by_title or {}).items()}
    dropped: List[Tuple[str, str]] = []
    lines = (tour_text or "").split("\n")
    cur_title = ""
    out: List[str] = []
    skip_blank = False
    for ln in lines:
        if skip_blank:
            skip_blank = False
            if not ln.strip():
                continue
        mh = re.match(r"(?i)^Stop\s+\d+:\s*(.+?)\s*$", ln.strip())
        if mh:
            cur_title = mh.group(1)
        m = re.match(r"^(Specific Examples\s*:\s*)(.*)$", ln)
        if m and cur_title:
            ev = sgg._lookup(norm, cur_title) or ""
            ev_sents = [set(_stem_toks(x)) for x in _sents(evidence_prose(ev))]
            keep = []
            for item in [x.strip(" .") for x in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(2)) if x.strip(" .")]:
                toks = set(_stem_toks(item)) - {_stem(w) for w in _GENERIC}
                if toks and any(toks <= es for es in ev_sents):
                    keep.append(item)
                else:
                    dropped.append((cur_title, item))
                    if log:
                        log(f"  [LOCAL-890] header item not stated by the evidence, dropped in "
                            f"'{cur_title[:40]}': \"{item}\"")
            if not keep:
                skip_blank = True                         # the line itself goes
                continue
            ln = m.group(1) + ", ".join(keep)
        out.append(ln)
    return "\n".join(out), dropped


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


def _stem_toks(s: str) -> List[str]:
    return [_stem(w) for w in _fold(s).split() if len(w) >= 4 and w not in _GENERIC]


# ── a standalone, well-formed sentence for an injection ─────────────────────
_REPHRASE_SYSTEM = (
    "You rewrite ONE sentence from a Wikipedia article so that it stands alone inside a spoken "
    "walking-tour narration about a single stop. Use ONLY the facts in SENTENCE and CONTEXT. "
    "Keep every date, year and number exactly as written; add no other date, number or name. "
    "Name the stop in the sentence instead of using 'it', 'this', 'these', 'the former'. Do not "
    "start with a connective (However, Later, Also), do not write 'also', and do not refer to "
    "any other stop. One sentence, at most 45 words. "
    'Return ONLY JSON: {"sentence": "<the sentence>"}')


def _caps(s: str) -> set:
    return {_fold(w) for w in re.findall(r"\b[A-ZÀ-Ý][\wÀ-ÿ'’-]+", s or "")}


def rephrase_ok(out: str, source: str, context: str, title: str) -> Optional[str]:
    """Mechanical check of a rephrased sentence: same dates/numbers as the source (no
    extras), no capitalised name that neither the source, the context nor the stop
    title has, well-formed, not tacked-on, short."""
    out = (out or "").strip()
    if not (25 <= len(out) <= 360) or not out.endswith((".", "!", "?")):
        return "length/terminator"
    n_src, n_ctx = set(re.findall(r"\d+", source)), set(re.findall(r"\d+", context))
    n_out = set(re.findall(r"\d+", out))
    if not n_src <= n_out or not n_out <= (n_src | n_ctx):
        return "numbers differ"
    if not (_caps(out) - {"the", "in", "on", "at", "as", "by", "during", "after", "before", "it", "this"}
            ) <= (_caps(source) | _caps(context) | _caps(title) | _own_tokens(title)
                  | {"the", "in", "on", "at", "as", "by", "during", "after", "before", "it", "this",
                     "today", "when", "while", "then", "from", "since", "between", "with", "its", "his",
                     "her", "they", "he", "she", "there"}):
        return "new name"
    if garbled(out) or _TACKED.search(out) or _CONNECTIVE.match(out) or re.search(r"(?i)\balso\b", out):
        return "not well-formed / tacked-on"
    return None


def standalone_sentence(fact_sentence: str, title: str, art: Optional[Dict], evidence: str, *,
                        classify_fn=None, model: Optional[str] = None,
                        rep: Optional[Dict] = None) -> Tuple[Optional[str], str]:
    """[LOCAL-890] ONE well-formed, standalone sentence for a key fact, or (None, why).
    Deterministic when the evidence sentence is already standalone (a 'It was also
    the site' becomes 'The <stop> was the site', a glued stop-name prefix is cut). A
    connective/pronoun/demonstrative opener needs ONE mini rephrase call with the
    previous article sentence as context, checked mechanically; it fails closed."""
    s = _clean_ev_sentence(fact_sentence)
    why = garbled(s)
    if why:
        return None, f"garbled evidence sentence ({why})"
    s, _ = strip_title_prefix(s, title)
    s = _CONNECTIVE.sub("", s).strip()
    s = s[:1].upper() + s[1:]
    s = re.sub(r"^(?:It|This|The\s+(?:building|structure|edifice|site))\s+(?=(?:was|is|has|had|were|served)\b)",
               f"The {title} ", s)
    s = re.sub(r"(?i)\b(was|is|has|had|were)\s+also\s+", r"\1 ", s)
    s = re.sub(r"(?i)\balso\s+", "", s) if _TACKED.search(s) else s
    if len(s) > 300:
        s = s[:300].rsplit(",", 1)[0].rstrip(" ,;") + "."
    if not s.endswith((".", "!", "?")):
        s += "."
    needs_help = bool(re.match(r"(?i)^(he|she|they|his|her|their|these|those|such|it|this|that)\b", s)) \
        or bool(orphan_opener([s], title))
    if not needs_help:
        return s, "deterministic"
    prev = ""
    if art:
        sents = own_prose_sentences(evidence, title)
        key = _fold(_clean_ev_sentence(fact_sentence))
        for i, x in enumerate(sents):
            if _fold(x) == key and i > 0:
                prev = sents[i - 1]
                break
    fn = classify_fn
    if fn is None:
        try:
            import strict_grounding_gate as _g
            fn = _g._default_classify
        except Exception:
            return None, "no rephrase backend"
    user = f"STOP: {title}\nCONTEXT: {prev}\nSENTENCE: {_clean_ev_sentence(fact_sentence)}\n"
    try:
        parsed, i_tok, o_tok = fn(_REPHRASE_SYSTEM, user, model or "gpt-4.1-mini")
    except Exception as e:                                 # never break the tour
        return None, f"rephrase call failed: {e}"
    if rep is not None:
        try:
            import strict_grounding_gate as _g
            rep["cost_usd"] = rep.get("cost_usd", 0.0) + _g._estimate_cost(model or "gpt-4.1-mini", i_tok, o_tok)
        except Exception:
            pass
    cand = (parsed or {}).get("sentence") if isinstance(parsed, dict) else None
    bad = rephrase_ok(cand or "", _clean_ev_sentence(fact_sentence), prev, title)
    if bad:
        return None, f"rephrase rejected ({bad})"
    return cand.strip(), "rephrased"


# ═════════════ the finishing pass ═════════════
def _insert_pos(sentences: List[str], fact: Dict, text: str = "") -> int:
    """Chronological slot: before the first kept sentence whose earliest year is later,
    after the last one whose years are not later; construction facts default to
    second place, others to the end."""
    ys = [int(y) for y in _YEAR.findall(text)] if text else []
    if not ys and fact.get("kind") == "years":
        ys = [int(y) for y in fact["years"]]
    elif not ys and str(fact.get("year", "")).isdigit():
        ys = [int(fact["year"])]
    if not ys:
        return 1 if len(sentences) > 1 else len(sentences)
    y = min(ys)
    last_le = -1
    for i, s in enumerate(sentences):
        sy = [int(v) for v in _YEAR.findall(s)]
        if sy and min(sy) > y:
            return i
        if sy:
            last_le = i
    if last_le >= 0:
        return last_le + 1
    return (1 if len(sentences) > 1 else len(sentences)) if fact.get("kind") == "years" \
        else len(sentences)


_GREETING = re.compile(r"(?i)^(?:you\s+(?:are\s+standing|stand|have\s+arrived|are\s+now|are\s+at)|welcome|"
                       r"here\s+(?:you|we)|standing\s+(?:in|at|before))\b")


def _guard_greeting(sentences: List[str], pos: int) -> int:
    """Never put an injected sentence before the stop's opening 'You stand before ...'."""
    if pos <= 0 and sentences and _GREETING.search(sentences[0].strip()):
        return 1
    return pos


def _plain_sentences(fact: Dict, title: str, evidence: str) -> List[str]:
    """The evidence sentence(s) that carry the fact: for a start+completion year pair
    that no single sentence states, both sentences, each plain."""
    srcs = [fact["sentence"]]
    if fact.get("kind") == "years":
        full = [x for x in fact.get("sentences", []) if all(y in x for y in fact["years"])]
        srcs = full[:1] or list(dict.fromkeys(fact.get("sentences") or srcs))
    out = []
    for x in srcs:
        ps = _plain_sentence({**fact, "sentence": x}, title, evidence)
        if ps:
            out.append(ps)
    return out


def _plain_sentence(fact: Dict, title: str, evidence: str) -> Optional[str]:
    """ONE plain sentence built from the evidence sentence carrying the fact."""
    s = fact["sentence"]
    s = re.sub(r"^(?:It|This|The\s+(?:building|structure|edifice|site))\s+(?=(?:was|is|has|had|were|served)\b)",
               f"The {title} ", s)
    if re.match(r"(?i)^(he|she|they|his|her|their|these|those|such|however|thus|also|"
                r"later|then|after|before|following)\b", s):
        return None
    if len(s) > 300:
        s = s[:300].rsplit(",", 1)[0].rstrip(" ,;") + "."
    return s if s.endswith((".", "!", "?")) else s + "."


_RAW_FIELD = re.compile(r"(?i)\b(?:infobox|passages)\s*:|(?:;\s*[a-z][a-z ]{1,24}:\s*[^;]{1,80}){2,}|\s\*[A-Z]")


def finalize_stop(title: str, sentences: List[str], evidence: str, *,
                  classify_fn=None, model: Optional[str] = None,
                  log: Optional[Callable] = None, where: str = "final",
                  min_sentences: int = 4) -> Tuple[List[str], Dict]:
    """Deny-set -> filler cap -> key-fact coverage (one gated plain sentence per
    missing fact). Returns (sentences, report)."""
    rep = {"title": title, "denied": 0, "filler": {}, "K": 0, "k_before": 0, "k": 0,
           "injected": [], "refused": [], "cost_usd": 0.0}
    cur = []
    for x in sentences:                   # raw evidence fields are never narration
        if _RAW_FIELD.search(x):
            rep.setdefault("raw_dropped", 0)
            rep["raw_dropped"] = rep.get("raw_dropped", 0) + 1
            if log:
                log(f"  [LOCAL-889] {where} dropped raw evidence field in '{title[:40]}': \"{x[:90]}\"")
            continue
        cur.append(x)
    art = own_article(evidence, title)
    rep.update({"glued_prefix": 0, "foreign_dropped": 0, "preview_dropped": 0, "garbled_dropped": 0,
                "orphans_dropped": 0, "tacked_fixed": 0, "own_article": (art or {}).get("title", "")})
    cleaned = []
    for x in cur:
        x2, glued = strip_title_prefix(x, title)
        if glued:
            rep["glued_prefix"] += 1
            # a glued stop-name prefix marks an injected sentence: keep it only when the
            # stop's own article is its subject
            if art is None or not about_stop(x2, title, art):
                rep["foreign_dropped"] += 1
                deny_record(title, x2, "gate:deterministic")
                if log:
                    log(f"  [LOCAL-890] {where} dropped a sentence glued to the stop name that is not "
                        f"about '{title[:40]}': \"{x[:100]}\"")
                continue
            x = x2
        if is_preview(x):
            rep["preview_dropped"] += 1
            if log:
                log(f"  [LOCAL-890] {where} dropped a next-stop preview in '{title[:40]}': \"{x[:100]}\"")
            continue
        cleaned.append(x)
    cur = cleaned
    cur, dropped = strip_denied(title, cur, evidence, log, where)
    rep["denied"] = len(dropped)
    keep_ok = []
    for x in cur:                         # mechanical UNSUPPORTED rules (free)
        why = deterministic_unsupported(x, evidence, title)
        if why:
            rep["denied"] += 1
            deny_record(title, x, "contested" if why.startswith("contested") else "gate:deterministic")
            if log:
                log(f"  [LOCAL-889] {where} dropped unsupported claim in '{title[:40]}': {why}: \"{x[:100]}\"")
        else:
            keep_ok.append(x)
    cur = keep_ok
    import strict_grounding_gate as _sgg
    if _sgg._evidence_is_thin(evidence):
        rep["filler"] = {"skipped": "no evidence (honest non-factual body)"}
        if log:
            log(f"  [LOCAL-889] coverage {title[:40]}: no evidence -> no key facts, filler cap skipped")
        rep["k"] = rep["K"] = 0
        return cur, rep
    cur, rep["filler"] = cap_filler(cur)
    facts = key_facts(evidence, title)
    rep["K"] = len(facts)
    cov = coverage_report(cur, facts)
    rep["k_before"] = cov["k"]
    if cov["missing"]:
        import strict_grounding_gate as sgg
        cands: List[Tuple[Dict, str]] = []
        for f in cov["missing"]:
            srcs = [f["sentence"]]
            if f.get("kind") == "years":
                full = [x for x in f.get("sentences", []) if all(y in x for y in f["years"])]
                srcs = full[:1] or list(dict.fromkeys(f.get("sentences") or srcs))
            for src in srcs:
                ps, how = standalone_sentence(src, title, art, evidence, classify_fn=classify_fn,
                                              model=model, rep=rep)
                if not ps:
                    rep["refused"].append(f"{f['kind']}: {how}")
                    continue
                # the plain sentence IS the stop's own article sentence, so only a
                # hard (mechanical / contested / scrub) denial blocks it
                hit = is_denied(title, ps, evidence)
                if not hit:
                    cands.append((f, ps))
                else:
                    rep["refused"].append(f"{f['kind']}: matches a removed claim "
                                          f"({hit.get('source')})")
        # one sentence can carry several missing facts (years + architect): inject once
        seen_s = set()
        cands = [(f, x) for f, x in cands if not (x in seen_s or seen_s.add(x))]
        cands.sort(key=lambda fx: min([int(y) for y in _YEAR.findall(fx[1])] or [9999]))
        if cands:
            gate_kw = {"classify_fn": classify_fn, "log": log, "deny_check": False}
            if model:
                gate_kw["model"] = model
            reg, grep = sgg.apply_grounding_gate(title, " ".join(x for _f, x in cands),
                                                 evidence, **gate_kw)
            rep["cost_usd"] += grep.get("cost_usd", 0.0)
            ok = {_fold(x) for x in sgg._content_sentences(reg)}
            for f, x in cands:
                if _fold(x) not in ok:
                    rep["refused"].append(f"{f['kind']}: gate dropped the plain sentence")
                    continue
                if fact_present(cur, f):
                    continue
                if _fold(x) in {_fold(c) for c in cur}:
                    continue
                if f["kind"] == "years":
                    have = set(_YEAR.findall(" ".join(cur)))
                    if not (set(_YEAR.findall(x)) & (set(f["years"]) - have)):
                        continue                 # adds no missing year
                cur.insert(_guard_greeting(cur, _insert_pos(cur, f, x)), x)
                rep["injected"].append(f"{f['kind']}: {x[:90]}")
    # the filler cap must not leave the stop below the floor: top up with plain,
    # evidence-stated sentences (gated once), never with filler
    if len(cur) < min_sentences:
        import stop_coherence as _sc
        have = [claim_key(x, title) for x in cur]
        extra = []
        for fs in _sc.evidence_fact_sentences(" ".join(own_prose_sentences(evidence, title)), limit=14):
            fs = _clean_ev_sentence(fs)
            k2 = claim_key(fs, title)
            if (not fs.endswith((".", "!", "?")) or len(fs) > 300 or is_denied(title, fs, evidence)
                    or deterministic_unsupported(fs, evidence, title) or is_sensory(fs)
                    or is_reflective(fs) or is_preview(fs) or garbled(fs) or orphan_opener([fs], title)
                    or not about_stop(fs, title, art) or _plain_sentence({"sentence": fs}, title, evidence) is None
                    or any(len(k2 & h) >= max(2, int(0.5 * len(k2))) for h in have)):
                continue
            extra.append(fs)
            have.append(k2)
            if len(cur) + len(extra) >= min_sentences:
                break
        if extra:
            gate_kw = {"classify_fn": classify_fn, "log": log, "deny_check": False}
            if model:
                gate_kw["model"] = model
            reg, grep = _sgg.apply_grounding_gate(title, " ".join(extra), evidence, **gate_kw)
            rep["cost_usd"] += grep.get("cost_usd", 0.0)
            ok = {_fold(x) for x in _sgg._content_sentences(reg)}
            for fs in extra:
                if _fold(fs) in ok:
                    cur.append(fs)
                    rep["injected"].append(f"floor: {fs[:90]}")
    # [LOCAL-890] end-state hygiene on the refill/coverage output
    fixed = []
    for x in cur:
        if _TACKED.search(x) and _has_fact(x):
            ps, how = standalone_sentence(x, title, art, evidence, classify_fn=classify_fn,
                                          model=model, rep=rep)
            if ps and ps != x:
                rep["tacked_fixed"] += 1
                if log:
                    log(f"  [LOCAL-890] {where} tacked-on opener in '{title[:40]}' ({how}): "
                        f"\"{x[:70]}\" -> \"{ps[:90]}\"")
                # a rewritten dated sentence goes to its chronological slot
                rest = [y for y in cur if y is not x]
                fixed.append((x, ps))
                continue
    for old_s, new_s in fixed:
        pos_old = cur.index(old_s)
        cur.pop(pos_old)
        yrs = [int(y) for y in _YEAR.findall(new_s)]
        pos = _guard_greeting(cur, _insert_pos(cur, {"kind": "event"}, new_s)) if yrs else pos_old
        cur.insert(pos, new_s)
    for x in list(cur):
        why = garbled(x)
        if why and len(cur) > 2:
            cur.remove(x)
            rep["garbled_dropped"] += 1
            deny_record(title, x, "gate:deterministic")
            if log:
                log(f"  [LOCAL-890] {where} dropped a garbled sentence in '{title[:40]}' ({why}): \"{x[:100]}\"")
    bad_idx = orphan_opener(cur, title) if len(cur) > 2 else []
    for i in sorted(bad_idx, reverse=True):
        if len(cur) <= 2:
            break
        rep["orphans_dropped"] += 1
        if log:
            log(f"  [LOCAL-890] {where} dropped an orphan opener in '{title[:40]}': \"{cur[i][:100]}\"")
        cur.pop(i)
    cov2 = coverage_report(cur, facts)
    rep["k"] = cov2["k"]
    if log:
        log(f"  [LOCAL-889] coverage {title[:40]}: {rep['k']}/{rep['K']} key facts"
            f" (before {rep['k_before']}; injected {len(rep['injected'])}; "
            f"denied-dropped {rep['denied']}; filler trimmed {rep['filler'].get('trimmed', 0)}, "
            f"reflective -{rep['filler'].get('reflective_dropped', 0)}, "
            f"sensory -{rep['filler'].get('sensory_dropped', 0)})")
        for line in rep["injected"]:
            log(f"      [LOCAL-889] injected {line}")
        for line in rep["refused"]:
            log(f"      [LOCAL-889] not injected {line}")
        for f in cov2["missing"]:
            log(f"      [LOCAL-889] still missing {f['kind']}: {f['sentence'][:90]}")
    return cur, rep


def finalize_tour(tour_text: str, evidence_by_title: Dict[str, str], *,
                  classify_fn=None, model: Optional[str] = None,
                  log: Optional[Callable] = None, where: str = "final") -> Tuple[str, Dict]:
    """finalize_stop over every 'Stop N:' block of a tour."""
    import strict_grounding_gate as sgg
    rep = {"stops": [], "header_splices": 0, "header_dropped": []}
    new_text, rep["header_splices"] = repair_header_splices(tour_text or "")
    if log and rep["header_splices"]:
        log(f"  [LOCAL-890] {where} moved {rep['header_splices']} body sentence(s) off header line(s)")
    norm = {sgg._fold(k): v for k, v in (evidence_by_title or {}).items()}
    for num, title, _b in sgg._split_blocks(new_text):
        block = sgg._block_for(new_text, num)
        if block is None:
            continue
        sents = sgg._content_sentences(sgg._block_body_prose(block))
        if not sents:
            continue
        ev = sgg._lookup(norm, title) or ""
        try:
            new, r = finalize_stop(title, sents, ev, classify_fn=classify_fn, model=model,
                                   log=log, where=where)
        except Exception as e:                      # never break the tour
            if log:
                log(f"  [LOCAL-889] finalize skipped for '{title[:40]}' (non-fatal): {e}")
            continue
        rep["stops"].append(r)
        if new != sents:
            new_text = sgg._replace_block_body(new_text, num, new)
    new_text, rep["header_dropped"] = ground_header_items(new_text, evidence_by_title, log)
    new_text = re.sub(r"([^\n])\n(Stop\s+\d+:)", r"\1\n\n\2", new_text)      # blank line before each stop
    return new_text, rep
