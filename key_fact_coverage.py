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


def is_denied(title: str, sentence: str) -> Optional[Dict]:
    """The recorded claim ``sentence`` repeats, else None. A match needs >= 2 shared
    specific tokens and >= 60% of the smaller key (so 'military' + 'intelligence'
    match, one shared place name does not)."""
    cands = deny_claims(title)
    if not cands:
        return None
    key = claim_key(sentence, title)
    for e in cands:
        shared = key & e["key"]
        need = max(2, math.ceil(0.6 * min(len(key), len(e["key"]))))
        if len(shared) >= need and (shared & e["lower"]) and (shared & _lower_toks(sentence)):
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
        hit = is_denied(title, s)
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


def _lead_text(evidence: str, title: str, width: int = 1400) -> str:
    """The lead of the stop's own article: the article whose header shares the most
    tokens with the stop title (else the first), else the head of the blob."""
    ev = evidence or ""
    heads = list(_WIKI_HEAD.finditer(ev))
    if not heads:
        return ev[:width]
    ttoks = {t for t in _fold(title).split() if len(t) >= 3}
    best, best_n = heads[0], -1
    for m in heads:
        pre = ev[max(0, m.start() - 90):m.start()]
        pre = re.split(r"[\n.]\s", pre)[-1]
        n = len(ttoks & set(_fold(pre).split()))
        if n > best_n:
            best, best_n = m, n
    return ev[best.end():best.end() + width]


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
    art = _lead_text(evidence, title, width=4200)
    art_sents = [_clean_ev_sentence(x) for x in _sents(art)]
    art_sents = [x for x in art_sents if 25 <= len(x) <= 420]
    lead_sents = art_sents
    _NOT_BUILD = re.compile(r"(?i)\b(prize|born|died|award\w*|won|degree|graduat\w+)\b")
    built = [x for x in art_sents if _BUILD_VERB.search(x) and _YEAR.search(x)
             and not _NOT_BUILD.search(x)] \
        or [x for x in art_sents if _BUILD_WEAK.search(x) and _YEAR.search(x)
            and not _NOT_BUILD.search(x)]
    if built:
        ys = list(dict.fromkeys(_YEAR.findall(built[0])))
        sent = built[0]
        if len(ys) == 1:                       # start year + completion year
            for x in built[1:4]:
                extra = [y for y in dict.fromkeys(_YEAR.findall(x)) if y not in ys]
                if extra and len(ys) + len(extra) <= 3:
                    ys = sorted(ys + extra)
                    sent = x
                    break
        facts.append({"kind": "years", "years": ys[:3], "sentence": sent,
                      "sentences": [built[0], sent]})
    for s in lead_sents:
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
    ev_fact = _event_fact(evidence, lead_sents)
    if ev_fact:
        facts.append(ev_fact)
    return facts


def _event_fact(evidence: str, lead_sents: List[str]) -> Optional[Dict]:
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
    for c in cands:
        c = _clean_ev_sentence(c)
        if not (25 <= len(c) <= 420) or not _FAMOUS.search(c):
            continue
        ys = _YEAR.findall(c)
        if not ys:
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
    r"\blinking\s+people\b|\bconnect\w*\s+the\s+present\b|\bbridging\b|"
    r"\bpersonal\s+and\s+(?:the\s+)?political\b)")
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


def deterministic_unsupported(sentence: str, evidence: str) -> Optional[str]:
    """A reason when ``sentence`` is NOT supported by ``evidence`` on purely
    mechanical grounds (None otherwise):
      * a year the evidence never states;
      * a year RANGE (between X and Y / X-Y) with no single evidence sentence that
        states both ends;
      * a departure (fled/left) bound to a full date on which the evidence records a
        resignation and no departure: the sources disagree on what happened that day.
    Years are only judged when the evidence is non-empty."""
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
        if ev_sents is None:
            ev_sents = _sents(ev)
        if not any(a in x and b in x for x in ev_sents):
            return f"no evidence sentence states both {a} and {b}"
    d = _date_tuple(sentence)
    if d and _DEPART.search(sentence):
        if ev_sents is None:
            ev_sents = _sents(ev)
        same_day = [x for x in ev_sents if _date_tuple(x) == d]
        if same_day and any(_RESIGN.search(x) for x in same_day) and \
                not any(_DEPART.search(x) and _RESIGN.search(x) for x in same_day):
            return (f"departure dated {d[0]} {d[1]} {d[2]} but the evidence records a "
                    f"resignation on that date (a different act)")
    return None


# ═════════════ the finishing pass ═════════════
def _insert_pos(sentences: List[str], fact: Dict) -> int:
    if fact.get("kind") == "architect":
        ys = []
    elif fact.get("kind") == "years":
        ys = [int(y) for y in fact["years"]]
    else:
        ys = [int(fact["year"])] if str(fact.get("year", "")).isdigit() else []
    if not ys:
        return 1 if len(sentences) > 1 else len(sentences)
    for i, s in enumerate(sentences):
        sy = [int(y) for y in _YEAR.findall(s)]
        if sy and min(sy) > min(ys):
            return i
    if fact.get("kind") == "years":                 # construction facts come early
        return 1 if len(sentences) > 1 else len(sentences)
    return len(sentences)


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


def finalize_stop(title: str, sentences: List[str], evidence: str, *,
                  classify_fn=None, model: Optional[str] = None,
                  log: Optional[Callable] = None, where: str = "final",
                  min_sentences: int = 4) -> Tuple[List[str], Dict]:
    """Deny-set -> filler cap -> key-fact coverage (one gated plain sentence per
    missing fact). Returns (sentences, report)."""
    rep = {"title": title, "denied": 0, "filler": {}, "K": 0, "k_before": 0, "k": 0,
           "injected": [], "refused": [], "cost_usd": 0.0}
    cur = list(sentences)
    cur, dropped = strip_denied(title, cur, evidence, log, where)
    rep["denied"] = len(dropped)
    keep_ok = []
    for x in cur:                         # mechanical UNSUPPORTED rules (free)
        why = deterministic_unsupported(x, evidence)
        if why:
            rep["denied"] += 1
            deny_record(title, x, "gate:deterministic")
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
            for ps in _plain_sentences(f, title, evidence):
                hit = is_denied(title, ps)
                # a claim the judge only found UNSUPPORTED in a narrow window may be
                # restored from the stop's own LEAD sentence; one that was
                # CONTRADICTED, scrubbed or removed by an earlier regeneration may not.
                if not hit or hit.get("source") == "gate:UNSUPPORTED":
                    cands.append((f, ps))
                else:
                    rep["refused"].append(f"{f['kind']}: matches a removed claim "
                                          f"({hit.get('source')})")
        # one sentence can carry several missing facts (years + architect): inject once
        seen_s = set()
        cands = [(f, x) for f, x in cands if not (x in seen_s or seen_s.add(x))]
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
                if fact_present(cur, f) and f["kind"] != "years":
                    continue
                if _fold(x) in {_fold(c) for c in cur}:
                    continue
                cur.insert(_insert_pos(cur, {**f, "years": [y for y in _YEAR.findall(x)] or f.get("years")}
                                       if f["kind"] == "years" else f), x)
                rep["injected"].append(f"{f['kind']}: {x[:90]}")
    # the filler cap must not leave the stop below the floor: top up with plain,
    # evidence-stated sentences (gated once), never with filler
    if len(cur) < min_sentences:
        import stop_coherence as _sc
        have = [claim_key(x, title) for x in cur]
        extra = []
        for fs in _sc.evidence_fact_sentences(evidence, limit=14):
            fs = _clean_ev_sentence(fs)
            k2 = claim_key(fs, title)
            if (not fs.endswith((".", "!", "?")) or len(fs) > 300 or is_denied(title, fs)
                    or deterministic_unsupported(fs, evidence) or is_sensory(fs)
                    or is_reflective(fs) or _plain_sentence({"sentence": fs}, title, evidence) is None
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
    rep = {"stops": []}
    new_text = tour_text or ""
    norm = {sgg._fold(k): v for k, v in (evidence_by_title or {}).items()}
    for num, title, _b in sgg._split_blocks(tour_text or ""):
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
    return new_text, rep
