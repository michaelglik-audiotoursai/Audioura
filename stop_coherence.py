#!/usr/bin/env python3
"""stop_coherence.py — LOCAL-888: after the grounding gate drops sentences, the
stop must still read as PROSE, and must still state its defining dated event.

Root causes found in the 887 parity run (Saigon, cloud snapshot):

  * The gate drops unsupported sentences one by one. What is left is a set of
    sentences that were written to follow each other: "Installed in 1959, this
    statue replaced..." (the statue sentence was dropped), "The echoes of that
    upheaval remain..." (the upheaval sentence was dropped), a bare surname
    (the full-name sentence was dropped), "those final hours".
  * The gate's shortfall rebuild (873C) was handed ONLY the thin-stop facts. Most
    stops have none (their evidence is an article / snippets), so the rebuild had
    nothing to narrate from and silently did nothing ("0 rebuilt").
  * The stop's own retrieved snippets were never visible to the main-thread gate
    (job-scoped state), so a stop with rich retrieval but no thin-fact entry
    looked like a no-evidence stop and lost all its history (the Cafe regression).

This module is generic (no venue name, D769) and offline-testable: every LLM call
goes through an injectable ``narrate_fn(system, user, model) -> (parsed, in, out)``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from sentence_split import split_sentences

__all__ = [
    "snippets_as_evidence_texts", "evidence_fact_sentences",
    "dangling_reference_issues", "bare_surname_issues", "signature_event",
    "states_event", "coherence_issues", "has_issues", "renarrate_from_kept",
    "insert_event_sentence",
]

_MIN_LEN = 15


# ── evidence helpers ─────────────────────────────────────────────────────────
def snippets_as_evidence_texts(snippets) -> List[str]:
    """Flatten the per-stop direct snippets (dicts with title/snippet, or plain
    strings) into evidence strings. Pure; never raises."""
    out: List[str] = []
    try:
        import llm_evidence as _le892
        snippets = _le892.filter_records(snippets)      # [LOCAL-892] an LLM's output is never evidence
    except Exception:
        pass
    for s in snippets or []:
        try:
            if isinstance(s, dict):
                t = " ".join(x for x in (str(s.get("title", "") or "").strip(),
                                         str(s.get("snippet", "") or "").strip()) if x)
            else:
                t = str(s or "").strip()
            if t and t not in out:
                out.append(t)
        except Exception:
            continue
    return out


_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_CLEAN_BAD = re.compile(r"(?i)(https?://|www\.|\bcookie|\bsubscribe\b|\bclick here\b|©)")
_CAP = r"[A-ZÀ-Ý][\wÀ-ÿ'’-]+"


def evidence_fact_sentences(evidence: str, limit: int = 14) -> List[str]:
    """Candidate FACT sentences drawn from a stop's evidence blob, for the
    evidence-only re-narration when the stop has no thin-fact list. Keeps
    sentences of plausible length that carry a year or a proper name, ranks the
    year-bearing ones first, preserves source order. Pure."""
    seen = set()
    scored: List[Tuple[int, int, str]] = []
    for i, s in enumerate(split_sentences(re.sub(r"\s+", " ", evidence or ""))):
        s = s.strip()
        if not (30 <= len(s) <= 320) or _CLEAN_BAD.search(s):
            continue
        key = re.sub(r"\W+", "", s.lower())[:70]
        if key in seen:
            continue
        seen.add(key)
        score = 2 if _YEAR.search(s) else 0
        if re.search(rf"\b{_CAP}\s+{_CAP}", s):
            score += 1
        if score == 0:
            continue
        scored.append((-score, i, s))
    scored.sort()
    picked = sorted(scored[:limit], key=lambda t: t[1])
    return [s for _, _, s in picked]


# ── dangling references ──────────────────────────────────────────────────────
_DEMO_RE = re.compile(
    r"(?i)\b(this|that|these|those)\s+((?:[a-zà-ỹ'’-]+\s+){0,2}?)([a-zà-ỹ'’-]{3,})\b")
# Nouns that point at the stop itself or the scene the listener stands in, so
# they need no antecedent sentence.
_DEIXIS_NOUNS = frozenset({
    "spot", "place", "site", "location", "stop", "address", "venue", "square",
    "street", "corner", "area", "point", "moment", "day", "time", "way",
    "building", "pier", "park", "garden", "bridge", "road", "avenue", "plaza",
    "church", "temple", "museum", "palace", "hall", "house", "tower", "market",
    "station", "district", "neighbourhood", "neighborhood", "city", "town",
    "year", "years", "decade", "century", "kind", "sort", "very", "one", "same",
    "was", "were", "has", "had", "will", "can", "may", "would", "and", "for",
    "the", "with", "from", "not", "also", "still", "now", "once", "then", "only",
    "even", "ever", "just", "who", "which", "what", "when", "where", "while",
    "which", "because", "they", "she", "his", "her", "its", "are", "been",
})
_LEADIN_RE = re.compile(
    r"(?i)^\s*(?:together,?\s+(?:these|those|they|both|all)\b|"
    r"in\s+(?:this|that)\s+way\b|taken\s+together\b|"
    r"(?:all\s+of\s+)?(?:these|those)\s+(?:landmarks|sites|places|stops|buildings|"
    r"monuments|stories|moments|events)\b)")
_FIRST_WORDS = 9


def _toks(s: str) -> set:
    return set(re.findall(r"[a-zà-ỹ]{3,}", (s or "").lower()))


def dangling_reference_issues(sentences: List[str], title: str = "",
                              location: str = "") -> List[Tuple[int, str, str]]:
    """Sentences whose OPENING points at something no kept sentence supplies.
    Returns [(index, kind, fragment)]. Kinds:
      * ``lead-in``       "Together, these landmarks..." (a roll-up of other stops);
      * ``demonstrative`` this/that/these/those + noun in the first words where
        the noun appears in no EARLIER sentence of the stop and is not the stop's
        own deixis ("this spot", "this building") nor part of its title.
    Pure; never raises."""
    out: List[Tuple[int, str, str]] = []
    title_toks = _toks(title) | _toks(location)
    earlier: set = set()
    for i, s in enumerate(sentences or []):
        s = (s or "").strip()
        if not s:
            continue
        if _LEADIN_RE.search(s):
            out.append((i, "lead-in", s[:60]))
            earlier |= _toks(s)
            continue
        head = " ".join(s.split()[:_FIRST_WORDS])
        for m in _DEMO_RE.finditer(head):
            noun = m.group(3).lower()
            if noun in _DEIXIS_NOUNS or noun in title_toks:
                continue
            stem = noun[:-1] if noun.endswith("s") and len(noun) > 4 else noun
            if any(stem in w for w in earlier):
                continue
            out.append((i, "demonstrative", m.group(0)))
            break
        earlier |= _toks(s)
    return out


# ── bare surnames ────────────────────────────────────────────────────────────
_KIND_WORDS = frozenset({
    "river", "city", "street", "palace", "hall", "cathedral", "church", "temple",
    "museum", "square", "market", "bridge", "gate", "tower", "park", "garden",
    "pier", "station", "boulevard", "avenue", "road", "bank", "house", "office",
    "republic", "kingdom", "army", "party", "war", "empire", "university",
})
_NOT_NAMES = frozenset({
    "the", "and", "but", "its", "his", "her", "their", "our", "this", "that",
    "these", "those", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december", "monday",
    "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today",
    "now", "here", "there", "when", "while", "after", "before", "during", "once",
    "later", "then", "from", "with", "built", "opened", "completed", "inside",
    "outside", "behind", "beside", "across", "along", "under", "over", "near",
    "french", "american", "vietnamese", "english", "german", "chinese", "japanese",
    "you", "your", "his", "she", "they", "what", "why", "how",
    "north", "south", "east", "west", "northern", "southern", "eastern", "western",
    "new", "old", "great", "united", "soviet", "national", "royal", "central",
    "grand", "upper", "lower", "greater", "free", "democratic", "people",
})
_FULLNAME_RE = re.compile(rf"\b({_CAP}(?:\s+{_CAP}){{1,3}})\b")


def _fold_basic(s: str) -> str:
    raw = (s or "").lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", raw)
                   if not unicodedata.combining(c))


def _evidence_person_names(evidence: str) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for m in _FULLNAME_RE.finditer(evidence or ""):
        parts = m.group(1).split()
        if any(_fold_basic(p) in _KIND_WORDS or _fold_basic(p) in _NOT_NAMES
               for p in parts):
            continue
        names.setdefault(_fold_basic(parts[-1]), m.group(1))
    return names


def bare_surname_issues(sentences: List[str], evidence: str = "", title: str = "",
                        location: str = "") -> List[Tuple[int, str]]:
    """A person introduced by SURNAME ONLY: the stop uses a bare capitalised word
    while its evidence carries a full multi-word name ending in it, and no earlier
    sentence of the stop gives that full name. Place/kind names never count.
    Returns [(index, word)]."""
    ev_names = _evidence_person_names(evidence)
    if not ev_names:
        return []
    skip = _toks(_fold_basic(title)) | _toks(_fold_basic(location))
    out: List[Tuple[int, str]] = []
    seen_full: set = set()
    for i, s in enumerate(sentences or []):
        s = (s or "").strip()
        spans = [(m.start(), m.end()) for m in _FULLNAME_RE.finditer(s)]
        for m in _FULLNAME_RE.finditer(s):
            seen_full.add(_fold_basic(m.group(1).split()[-1]))
        for m in re.finditer(rf"(?<![\wÀ-ÿ])({_CAP})", s):
            if any(a <= m.start() < b for a, b in spans):
                continue
            w = _fold_basic(m.group(1))
            if w in skip or w in _NOT_NAMES or w in _KIND_WORDS or len(w) < 3:
                continue
            if w in ev_names and w not in seen_full:
                out.append((i, m.group(1)))
                break
    return out


# ── the signature (defining, dated) event ────────────────────────────────────
_MONTHS = ("january february march april may june july august september "
           "october november december").split()
_MON = r"(?:" + "|".join(m[:3] + r"[a-z]*" for m in _MONTHS) + r")"
_DMY = re.compile(rf"(?i)\b(\d{{1,2}})\s+({_MON})\.?,?\s+(\d{{4}})\b")
_MDY = re.compile(rf"(?i)\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b")
_EVENT_VERB = re.compile(
    r"(?i)\b(captur\w+|crash\w+|bomb\w+|surrender\w*|storm\w*|fell|fall of|"
    r"assassinat\w+|declared|signed|burn\w+|destroy\w+|liberat\w+|seiz\w+|"
    r"overthr\w+|invad\w+|attack\w+|collaps\w+|erupt\w+|massacre\w*|coup|"
    r"proclaim\w+|inaugurat\w+|consecrat\w+|opened|unveil\w+|ended|"
    r"rammed|entered|occupied|evacuat\w+|execut\w+|shot|sank|exploded)\b")
_WIKI_LEAD = re.compile(r"(?i)\s-\s*Wikipedia\s*\([a-z-]+\)\.?\s")


def _norm_month(m: str) -> str:
    return (m or "").lower()[:3]


def _date_of(sentence: str) -> Optional[Tuple[int, str, int]]:
    m = _DMY.search(sentence)
    if m:
        return int(m.group(1)), _norm_month(m.group(2)), int(m.group(3))
    m = _MDY.search(sentence)
    if m:
        return int(m.group(2)), _norm_month(m.group(1)), int(m.group(3))
    return None


def _lead_segments(evidence: str, width: int = 900) -> List[str]:
    """The LEAD of each article-shaped evidence item ('<title> - Wikipedia (xx).
    <lead>'), else the first ``width`` chars of the blob."""
    ev = evidence or ""
    segs = [ev[m.end():m.end() + width] for m in _WIKI_LEAD.finditer(ev)]
    return segs or [ev[:width]]


def signature_event(evidence: str) -> Optional[Dict]:
    """The dated defining event stated in the evidence LEAD: the first lead
    sentence carrying a full date (day month year) and an event verb. Returns
    {sentence, day, month, year} or None. Pure, generic."""
    for seg in _lead_segments(evidence):
        for s in split_sentences(re.sub(r"\s+", " ", seg)):
            s = s.strip()
            if len(s) < 25 or len(s) > 400:
                continue
            d = _date_of(s)
            if d and _EVENT_VERB.search(s):
                return {"sentence": s, "day": d[0], "month": d[1], "year": d[2]}
    return None


def states_event(sentences: List[str], event: Dict) -> bool:
    """True when ONE kept sentence carries the event's full date (day, month and
    year): a plain statement, not an allusion."""
    for s in sentences or []:
        if _date_of(s) == (event["day"], event["month"], event["year"]):
            return True
    return False


# ── the combined check + the re-narration ────────────────────────────────────
def coherence_issues(sentences: List[str], title: str = "", location: str = "",
                     evidence: str = "") -> Dict:
    """All coherence defects of a kept-sentence list."""
    ev = signature_event(evidence) if evidence else None
    return {
        "dangling": dangling_reference_issues(sentences, title, location),
        "bare_surname": bare_surname_issues(sentences, evidence, title, location),
        "missing_event": (ev if ev and not states_event(sentences, ev) else None),
    }


def has_issues(iss: Dict) -> bool:
    return bool(iss.get("dangling") or iss.get("bare_surname")
                or iss.get("missing_event"))


_RENARRATE_SYSTEM = (
    "You repair ONE stop of a spoken walking audio tour. Some sentences were "
    "removed because they were unsupported, so the remaining ones may refer back "
    "to things no longer said. You get the KEPT sentences and the stop's EVIDENCE. "
    "Rewrite the stop as 4 to 7 short spoken sentences, in CHRONOLOGICAL order, "
    "addressing the listener in the second person where natural. Rules: use ONLY "
    "what the KEPT sentences or the EVIDENCE state; add nothing from memory, no "
    "invented date, person or figure. Every sentence must stand alone: no "
    "'this/that/these/those + noun' unless the noun was introduced in an earlier "
    "sentence of YOUR text; no 'Together, these...' roll-ups; no 'the echoes "
    "of...' summaries. Give a person's FULL name the first time and the surname "
    "only afterwards. If a REQUIRED EVENT is given, state it in one plain "
    "sentence WITH its full date. Skip anything you cannot support. No marketing "
    'words. Return ONLY JSON: {"sentences":["<sentence>", ...]}')


def _build_user(title, kept, evidence_sents, location, required_event, full_names):
    lines = [f'PLACE: "{title}"' + (f" in {location}" if location else ""), ""]
    lines.append("KEPT SENTENCES (supported; keep only what the evidence backs):")
    for i, s in enumerate(kept, 1):
        lines.append(f"  {i}. {s}")
    lines += ["", "EVIDENCE:"]
    for i, s in enumerate(evidence_sents, 1):
        lines.append(f"  E{i}. {s}")
    if required_event:
        lines += ["", "REQUIRED EVENT (state plainly, with the full date): "
                  + required_event["sentence"]]
    if full_names:
        lines += ["", "FULL NAMES to use at first mention: "
                  + "; ".join(sorted(set(full_names)))]
    lines += ["", "Write the repaired stop. JSON only."]
    return "\n".join(lines)


def renarrate_from_kept(
        title: str, kept: List[str], evidence: str, location: str = "", *,
        issues: Optional[Dict] = None, narrate_fn: Optional[Callable] = None,
        model: str = "gpt-4.1-mini", log: Optional[Callable] = None,
        ) -> Tuple[Optional[List[str]], Dict]:
    """ONE mini call: re-narrate a stop from its KEPT sentences plus its evidence,
    chronologically, standalone sentences, full names first, the required dated
    event stated plainly. Returns (sentences|None, report). The CALLER gates the
    result once more. Never raises."""
    rep = {"called": False, "cost_usd": 0.0, "in": 0, "out": 0}
    log = log or (lambda *_a, **_k: None)
    try:
        if narrate_fn is None:
            from thin_stop_delivery import _default_narrate as narrate_fn
        iss = issues if issues is not None else coherence_issues(
            kept, title, location, evidence)
        ev_sents = evidence_fact_sentences(evidence, limit=14)
        full_names = []
        names = _evidence_person_names(evidence)
        for _i, w in iss.get("bare_surname", []) or []:
            full = names.get(_fold_basic(w))
            if full:
                full_names.append(full)
        user = _build_user(title, kept, ev_sents, location,
                           iss.get("missing_event"), full_names)
        parsed, in_tok, out_tok = narrate_fn(_RENARRATE_SYSTEM, user, model)
        rep["called"] = True
        rep["in"], rep["out"] = int(in_tok or 0), int(out_tok or 0)
        try:
            from cost_rates import llm_cost
            rep["cost_usd"] = round(llm_cost(rep["in"], rep["out"], model), 6)
        except Exception:
            rep["cost_usd"] = round(rep["in"] / 1e6 * 0.40 + rep["out"] / 1e6 * 1.60, 6)
        if not parsed:
            return None, rep
        raw = parsed.get("sentences") or []
        if isinstance(raw, str):
            raw = [raw]
        out: List[str] = []
        for item in raw:
            for s in split_sentences(str(item or "")):
                s = s.strip()
                if len(s) >= _MIN_LEN and s not in out:
                    out.append(s)
        return (out or None), rep
    except Exception as e:  # never raise
        log(f"  [LOCAL-888] re-narration skipped {title!r}: {e}")
        return None, rep


def insert_event_sentence(sentences: List[str], event: Dict) -> List[str]:
    """Deterministic last resort: the evidence's own event sentence, placed in
    chronological position by year among the dated kept sentences."""
    out = list(sentences)
    pos = len(out)
    for i, s in enumerate(out):
        ys = [int(y) for y in _YEAR.findall(s)]
        if ys and min(ys) > event["year"]:
            pos = i
            break
    out.insert(pos, event["sentence"].strip())
    return out
