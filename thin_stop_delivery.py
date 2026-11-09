#!/usr/bin/env python3
"""thin_stop_delivery.py — LOCAL-873B: the post-narration thin check.

LOCAL-873 counted "thin" BEFORE narration (at the LOCAL-872C evidence point) and
escalated only stops that were thin then. LEAD read the DELIVERED tour and found
that was not enough:

  * Bạch Đằng Pier had >= 3 sourced specifics at the pre-narration point (its
    geo-gated Wikipedia evidence), so LOCAL-873 did NOT escalate it — yet the
    DELIVERED body carried only ~2 concrete facts (end of the war; boats to Củ
    Chi). The rest was mood ("a tangible boundary where history pivoted").
  * Ho Chi Minh City Hall delivered 3 sentences.
  * Nguyễn Văn Bình Book Street WAS escalated to 13 facts, but the gates and the
    fact-sheet verify dropped them, leaving two content sentences in the body.

Michael's bar is on the DELIVERED text, so the check must be too. This module:

  1. Parses the assembled tour into "Stop N:" blocks (the same block grammar the
     855B final scrub and user_stop_verify use).
  2. For each stop, counts the SOURCED SPECIFICS actually present in the
     delivered body (a body sentence that carries a year or a concrete cue AND is
     traceable to a known/escalation fact, OR simply carries a concrete specific
     when no fact list is supplied). This is `count_delivered_specifics`.
  3. If a stop has fewer than ``MIN_SPECIFICS`` (3) and it was NOT already
     escalated, it ESCALATES NOW (``thin_stop_search.escalate_thin_stop``, same
     cost cap ~$0.01/stop). Whether escalated now or earlier, it then REBUILDS
     the body ONCE from the sourced facts: it appends plain fact sentences (each
     traceable to a fact) until the body carries at least ``MIN_SPECIFICS``
     fact-traceable sentences, without exceeding the facts available.

The rebuild is DETERMINISTIC — it composes from facts already extracted (no new
LLM call for the rewrite), so it adds no cost beyond a possible one-time
escalation. Everything is injectable (``escalate_fn``, ``facts_by_title``) so the
module is fully offline-testable; pure helpers never raise.

LOCAL-873C — THE REBUILD MUST READ LIKE AN AUDIO TOUR, NOT PASTED WEB COPY.
LEAD read the 873B rebuild on Book Street and found it (1) repeated the
Orientation verbatim as the body's first sentences, (2) appended the scraped
facts as raw copy with broken grammar and capitalisation ("Ho Chi Minh City Book
Street Known as Nguyen Van Binh Book Street, is a cultural hub…"), and (3) wrote
the Vietnamese names without diacritics while the rest of the tour used them.
When the rebuild now fires it makes ONE cheap gpt-4.1-mini call (temperature 0.3)
constrained to the given facts only, rewriting the body as 5–7 spoken sentences
in the tour's voice (second person, present tense). Every sentence must be
traceable to a fact; each is run back through the LOCAL-872 claim gate and the
873B fact-sheet verify. If the call fails or the gate rejects it, the rebuild
falls back to the deterministic append — now with the three fixes applied
(sentence-case repair, no "X Known as Y," fragments, local diacritic spelling
from the stop title). No body sentence may repeat an Orientation sentence
(normalised match, both directions). The cost cap stays ~$0.01/stop; the LLM
backend is injectable (``narrate_fn``) so the module is still fully offline."""
from __future__ import annotations

import json
import os
import re
import unicodedata as _ud
from typing import Callable, Dict, List, Optional, Tuple

from sentence_split import split_sentences
from thin_stop_search import count_specifics, fold

__all__ = [
    "MIN_SPECIFICS", "count_delivered_specifics", "fact_sentences",
    "narrate_stop_body", "repair_fact_sentence", "dedup_against_orientation",
    "rebuild_thin_delivered_stops",
]

MIN_SPECIFICS = int(os.environ.get("THIN_DELIVERED_MIN_SPECIFICS", "3"))

# [LOCAL-873C] the narration model + cap for the ONE rewrite call per rebuilt stop.
NARRATE_MODEL = os.environ.get("THIN_DELIVERED_NARRATE_MODEL", "gpt-4.1-mini")
NARRATE_TEMPERATURE = float(os.environ.get("THIN_DELIVERED_NARRATE_TEMP", "0.3"))

# Block grammar — mirrors user_stop_narration / user_stop_verify exactly.
_STOP_HDR_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_FIELD_LINE_RE = re.compile(
    r"(?mi)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
    r"Tour-Category|Address|Operational Details):")
_ORIENT_RE = re.compile(r"(?i)^orientation:")
_DIRECTIONS_RE = re.compile(r"(?i)^directions:")

# A year or a concrete cue — the same notion of "specific" as thin_stop_search,
# used to decide whether a DELIVERED body sentence carries a sourced fact.
_YEAR_RE = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
_TYPE_RE = re.compile(r"(?mi)^Type/Specialty:\s*(.+?)\s*$")
_SPECIFIC_CUE = re.compile(
    r"(?i)\b(built|construct\w*|completed|opened|founded|established|designed|"
    r"architect|renovat\w*|named after|named for|length|metres?|meters?|"
    r"kilomet\w*|wide|high|tall|capacity|population|dynasty|century|war|battle|"
    r"river|bridge|statue|monument|trade|port|ferry|market|temple|emperor|king|"
    r"french|colonial|reunification|stall|book|cafe|café|publisher|rating|"
    r"review|floor|storey|story building|apartment|band|events?)\b")


def _is_specific(sentence: str) -> bool:
    s = (sentence or "").strip()
    if len(s) < 15:
        return False
    return bool(_YEAR_RE.search(s) or _SPECIFIC_CUE.search(s))


def _fact_texts(facts) -> List[str]:
    out: List[str] = []
    for f in facts or []:
        if isinstance(f, dict):
            t = str(f.get("text") or f.get("fact") or f.get("snippet") or "")
        else:
            t = str(f or "")
        t = t.strip()
        if t:
            out.append(t)
    return out


def _content_tokens(text: str) -> set:
    return {w for w in fold(text).split() if len(w) >= 4}


def _safe_fact_ok(fact_filter: Callable, title: str, sentence: str,
                  block_text: str) -> bool:
    """Call an injected ``fact_filter(title, sentence, block)`` guarding against
    any exception (a filter must never crash the rebuild). True (keep) on error."""
    try:
        return bool(fact_filter(title, sentence, block_text))
    except Exception:
        return True


def _traceable(sentence: str, fact_token_sets: List[set]) -> bool:
    """True when a body sentence shares enough content with SOME fact to be
    considered drawn from it (>= 3 content tokens in common). With no facts
    supplied, any specific sentence counts (back-compat / standalone use)."""
    if not fact_token_sets:
        return _is_specific(sentence)
    stoks = _content_tokens(sentence)
    if not stoks:
        return False
    for ftoks in fact_token_sets:
        if len(stoks & ftoks) >= 3:
            return True
    return False


def count_delivered_specifics(body: str, facts=None) -> int:
    """Count the SOURCED specifics present in a delivered body.

    A body sentence counts when it carries a year/concrete cue AND (when a fact
    list is supplied) is traceable to one of the facts. Deterministic.

    With NO fact list supplied, this delegates to thin_stop_search.count_specifics
    over the body sentences — the SAME metric the live PASS check uses — so the
    rebuild trigger and the acceptance measure never disagree (the Pier shipped 7
    body sentences but only 2 sourced specifics; this must see 2, not a looser
    count)."""
    sents = split_sentences(body or "")
    fact_texts = _fact_texts(facts)
    if not fact_texts:
        return count_specifics(sents)
    fact_token_sets = [_content_tokens(t) for t in fact_texts]
    fact_token_sets = [s for s in fact_token_sets if s]
    n = 0
    seen = set()
    for sent in sents:
        if not _is_specific(sent):
            continue
        if fact_token_sets and not _traceable(sent, fact_token_sets):
            continue
        key = fold(sent)[:80]
        if key in seen:
            continue
        seen.add(key)
        n += 1
    return n


_FIELD_LABEL_RE = re.compile(
    r"(?i)^(address|coordinates|type/specialty|specific examples|directions|"
    r"operational details|sources|orientation|tour-category)\s*:\s*")


def _is_truncated(text: str) -> bool:
    """A fact cut mid-sentence (ends with '...', an ellipsis, a trailing comma,
    a dangling conjunction/preposition, or a mid-list clause) is unusable as a
    delivered sentence."""
    s = (text or "").strip()
    if not s:
        return True
    if s.endswith("...") or s.endswith("…") or s.endswith(",") or s.endswith(";"):
        return True
    # ends on a number + nothing ("each side has 9 floors," already caught; also
    # "Originally built in 1960's" with no real end) — require a terminal stop OR
    # a reasonably complete clause.
    core = s.rstrip(".!?")
    toks = core.split()
    last = toks[-1].lower().strip(",;:") if toks else ""
    _DANGLERS = {"and", "or", "but", "from", "to", "of", "with", "the", "a",
                 "an", "in", "on", "for", "as", "that", "which", "by", "at",
                 "including", "such", "like", "each", "both"}
    if last in _DANGLERS:
        return True
    return False


def _strip_field_label(text: str) -> str:
    """Remove a leading 'Address:' / 'Coordinates:' style label that would
    collide with the stop-block field grammar if appended to the body."""
    return _FIELD_LABEL_RE.sub("", (text or "").strip()).strip()


def fact_sentences(facts, limit: int = 6, require_specific: bool = True,
                   title: str = "") -> List[str]:
    """Turn sourced facts into plain delivered-body sentences. Each fact is one
    sentence; the extractor already returns a single sentence, so this normalises
    terminal punctuation. Drops TRUNCATED facts and strips any leading field
    label (a fact beginning "Address: …" must not be mistaken for a block field
    line). With ``require_specific`` (the default), keeps only facts carrying a
    year/concrete cue — those count toward sourced-specific coverage. With
    ``require_specific=False``, also keeps clean, substantial venue facts that
    lack a hard cue as sentence-floor filler. Deduped.

    [LOCAL-873C] Each kept fact is first run through ``repair_fact_sentence`` with
    the stop ``title`` so the deterministic fallback no longer ships raw scraped
    copy: sentence-case is repaired, an "X Known as Y, is …" fragment is
    normalised, and the local diacritic spelling from the stop title is restored
    (so "Nguyen Van Binh" reads "Nguyễn Văn Bình" as the rest of the tour does)."""
    out: List[str] = []
    seen = set()
    for t in _fact_texts(facts):
        s = _strip_field_label(t)
        if _is_truncated(s):
            continue
        # a fact that still carries an embedded field-label grammar is unreliable
        if _FIELD_LABEL_RE.search(s):
            continue
        s = repair_fact_sentence(s, title)
        if not s:
            continue
        if require_specific and not _is_specific(s):
            continue
        if not require_specific and len(s) < 25:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        key = fold(s)[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL-873C — deterministic fallback repair (fixes 2 and 3)
# ═══════════════════════════════════════════════════════════════════════════
# "Known as <Alias>," inserted mid-title: the scraped Book Street fact read
# "Ho Chi Minh City Book Street Known as Nguyen Van Binh Book Street, is a
# cultural hub …". Keep the local ALIAS (the tour's own name) as the subject and
# drop the generic prefix + "Known as", so the sentence reads
# "Nguyen Van Binh Book Street is a cultural hub …" (then local spelling restores
# the diacritics). Falls back to simply removing the "Known as <x>," aside when
# the alias is not followed by a verb.
_KNOWN_AS_KEEP_RE = re.compile(
    r"(?i)^.*?\bknown as\s+(?P<alias>[^,.]+?),\s*(?=is\b|was\b|has\b|lies\b|"
    r"sits\b|stretches\b|runs\b|gathers\b|offers\b|features\b)")
_KNOWN_AS_RE = re.compile(
    r"(?i)\s+known as\s+[^,.]+,\s*(?=is\b|was\b|has\b|lies\b|sits\b|stretches\b|"
    r"runs\b|gathers\b|offers\b|features\b)")
# A doubled venue phrase where a title is immediately re-stated as its alias:
# "Ho Chi Minh City Book Street Nguyen Van Binh Book Street" -> keep the first.
_CAP_RUN = r"(?:[A-ZÀ-Ỹ][\wÀ-ỹ'’.-]*(?:\s+|$)){2,}"


def _title_spelling_map(title: str) -> Dict[str, str]:
    """Map the diacritic-folded form of each distinctive word in the stop title
    to the title's own spelling, so a fact written without diacritics ("Nguyen
    Van Binh", "Hai Ba Trung") is restored to the local spelling the tour uses.
    Only multi-letter words are mapped, and only when folding actually changes
    the word (an ASCII word maps to itself and is skipped)."""
    out: Dict[str, str] = {}
    for w in re.findall(r"[^\s,.;:()\[\]]+", title or ""):
        core = w.strip(".,;:()[]'\"")
        if len(core) < 2:
            continue
        folded = fold(core)
        if folded and folded != core.lower() and folded not in out:
            out[folded] = core
    return out


def _apply_local_spelling(sentence: str, title: str) -> str:
    """Restore the stop title's local diacritic spelling on any word in the
    sentence whose diacritic-folded form matches a title word. Case-insensitive
    match; the title's own spelling (and case) is used for the replacement."""
    smap = _title_spelling_map(title)
    if not smap:
        return sentence

    def _repl(m):
        w = m.group(0)
        folded = fold(w)
        rep = smap.get(folded)
        if rep and fold(rep) == folded and w != rep:
            return rep
        return w

    return re.sub(r"[A-Za-zÀ-ỹĐđ][\wÀ-ỹĐđ'’]*", _repl, sentence)


def _sentence_case_repair(sentence: str) -> str:
    """Repair mid-sentence capitalisation that betrays pasted web copy. A run of
    Title-Cased words that is NOT a proper name ("… Book Street Known as …")
    keeps its real proper-noun capitals but a stray capitalised function word
    ("Known", "Located") that starts no sentence is lowercased."""
    s = (sentence or "").strip()
    if not s:
        return s
    # Lowercase an interior capitalised common connective that reads as a label
    # fragment ("Known as", "Located in", "Situated at") when it is not the first
    # word of the sentence.
    _CONNECTIVES = ("Known", "Located", "Situated", "Featuring", "Offering",
                    "Housing", "Comprising", "Including", "Consisting")
    for w in _CONNECTIVES:
        s = re.sub(r"(?<=[a-z,] )" + w + r"\b", w.lower(), s)
    return s


def repair_fact_sentence(text: str, title: str = "") -> str:
    """[LOCAL-873C fixes 2 and 3] Turn one raw scraped fact into a clean delivered
    sentence: drop a mid-title "Known as <alias>," fragment, repair stray interior
    capitalisation, and restore the stop title's local diacritic spelling. Never
    raises; returns '' only for empty input."""
    s = (text or "").strip()
    if not s:
        return ""
    # 1. "… Known as <Alias>, is …": keep the ALIAS as subject when it is
    #    followed by a verb; else just drop the "Known as <x>," aside.
    m = _KNOWN_AS_KEEP_RE.match(s)
    if m:
        alias = m.group("alias").strip()
        s = alias + " " + s[m.end():].lstrip()
    else:
        s = _KNOWN_AS_RE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    # 2. repair interior sentence-casing of connective/label words.
    s = _sentence_case_repair(s)
    # 3. restore local diacritic spelling from the stop title.
    s = _apply_local_spelling(s, title)
    # tidy a leading lowercase after the drop (the subject must open with a cap).
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s.strip()


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL-873C — Orientation ⇄ body dedup (both directions)
# ═══════════════════════════════════════════════════════════════════════════
def _norm_sent(s: str) -> str:
    """Normalised form of a sentence for duplicate matching: folded to lowercase
    ASCII words, terminal punctuation and stray spacing removed."""
    return " ".join(fold(s).split())


def dedup_against_orientation(body_sentences: List[str],
                              orientation: str) -> List[str]:
    """Drop any body sentence that repeats an Orientation sentence (normalised
    match). Both directions: a body sentence equal to, contained in, or
    containing an Orientation sentence is removed, so the verbatim-Orientation
    opening of the 873B Book Street body ("… is a book street …", "Take a moment
    at the entrance …") never survives in the body. Order preserved; pure."""
    if not orientation:
        return list(body_sentences)
    or_norms = [_norm_sent(s) for s in split_sentences(orientation) if s.strip()]
    or_norms = [n for n in or_norms if len(n) >= 8]
    if not or_norms:
        return list(body_sentences)
    out: List[str] = []
    for s in body_sentences:
        n = _norm_sent(s)
        if not n:
            continue
        dup = False
        for on in or_norms:
            if n == on or (len(n) >= 12 and (n in on or on in n)):
                dup = True
                break
        if not dup:
            out.append(s)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL-873C — the narrated rebuild (ONE gpt-4.1-mini call, gate + fact-sheet)
# ═══════════════════════════════════════════════════════════════════════════
_NARRATE_SYSTEM = (
    "You write ONE stop of a spoken walking audio tour. You are given a place "
    "name and a short list of SOURCED FACTS about it. Rewrite those facts as 5 "
    "to 7 short spoken sentences, in the tour's voice: SECOND PERSON and PRESENT "
    "TENSE, addressing the listener standing at the place now. Every sentence "
    "must state something the FACTS give — a date, a name, a size, a purpose, "
    "what is there. Do NOT add anything the facts do not state: no invented "
    "date, person, event or figure. Do NOT repeat the orientation line you are "
    "shown. Use the place name's spelling exactly as given (keep its diacritics). "
    "Plain sentences, no headings, no lists, no quotation of raw web copy.\n"
    'Return ONLY JSON of the exact shape: {"sentences":["<sentence>", ...]}')


def _build_narrate_user(title: str, facts_texts: List[str],
                        orientation: str, location: str) -> str:
    lines = [f'PLACE: "{title}"' + (f" in {location}" if location else ""), ""]
    if orientation:
        lines += ["ORIENTATION ALREADY SPOKEN (do not repeat): "
                  + orientation.strip(), ""]
    lines.append("SOURCED FACTS (rewrite only these, add nothing):")
    for i, f in enumerate(facts_texts, 1):
        lines.append(f"  {i}. {f}")
    lines += ["", "Write 5–7 spoken second-person present-tense sentences from "
              "these facts. JSON only."]
    return "\n".join(lines)


def _default_narrate(system: str, user: str, model: str,
                     temperature: float = NARRATE_TEMPERATURE,
                     timeout: int = 40, max_tokens: int = 600
                     ) -> Tuple[Optional[dict], int, int]:
    """One gpt-4.1-mini JSON call for the rewrite. Returns
    (parsed|None, in_tokens, out_tokens). Billed by the project meter. Never
    raises; returns (None, 0, 0) with no key or on any failure."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None, 0, 0
    try:
        import requests
    except Exception:
        return None, 0, 0
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": float(temperature), "max_tokens": int(max_tokens),
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, 0, 0
        body = resp.json()
        usage = body.get("usage", {}) or {}
        content = body["choices"][0]["message"]["content"]
        return (json.loads(content),
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)))
    except Exception:
        return None, 0, 0


def _traceable_to_facts(sentence: str, fact_token_sets: List[set]) -> bool:
    if not fact_token_sets:
        return False
    stoks = _content_tokens(sentence)
    if not stoks:
        return False
    return any(len(stoks & ft) >= 3 for ft in fact_token_sets)


def narrate_stop_body(
        title: str, facts, orientation: str = "", location: str = "", *,
        narrate_fn: Optional[Callable] = None,
        claim_gate_fn: Optional[Callable] = None,
        min_sentences: int = 5, max_sentences: int = 7,
        model: str = NARRATE_MODEL, log: Optional[Callable] = None,
        ) -> Tuple[Optional[List[str]], Dict]:
    """[LOCAL-873C] Rewrite a thin stop's body from its SOURCED facts with ONE
    cheap gpt-4.1-mini call (temperature 0.3), returning spoken second-person
    present-tense sentences. Every returned sentence is kept ONLY if it is:

      * traceable to a fact (>= 3 distinctive content tokens shared with some
        fact — the 873B fact-sheet verify notion), AND
      * free of unsourced claims per the LOCAL-872 claim gate
        (``claim_gate_fn(sentence, title, evidence, location)`` -> list of
        unsourced (kind, span); non-empty means reject the sentence).

    Surviving sentences are deduped against the Orientation (both directions).
    Returns ``(sentences, report)`` with ``sentences`` a list of >= ``min_sentences``
    clean sentences, or ``None`` when the call fails, the gate rejects too much, or
    too few traceable sentences remain — the caller then uses the deterministic
    fallback. Fully offline: with no ``narrate_fn`` and no key the default returns
    None and the rebuild falls back. Never raises."""
    log = log or (lambda *_a, **_k: None)
    report = {"ran": False, "model": model, "input_tokens": 0,
              "output_tokens": 0, "cost_usd": 0.0, "kept": 0, "rejected": 0}
    facts_texts = _fact_texts(facts)
    # feed the model clean facts (local spelling restored, no 'Known as' fragment)
    facts_texts = [repair_fact_sentence(t, title) for t in facts_texts]
    facts_texts = [t for t in facts_texts if t]
    if not facts_texts:
        return None, report

    narrate_fn = narrate_fn or _default_narrate
    user = _build_narrate_user(title, facts_texts, orientation, location)
    try:
        parsed, in_tok, out_tok = narrate_fn(_NARRATE_SYSTEM, user, model)
    except Exception as e:
        log(f"  [LOCAL-873C] narration call failed {title!r}: {e}")
        parsed, in_tok, out_tok = None, 0, 0
    report["input_tokens"] = int(in_tok or 0)
    report["output_tokens"] = int(out_tok or 0)
    try:
        from cost_rates import llm_cost
        report["cost_usd"] = round(llm_cost(report["input_tokens"],
                                            report["output_tokens"], model), 6)
    except Exception:
        report["cost_usd"] = round(report["input_tokens"] / 1e6 * 0.40
                                   + report["output_tokens"] / 1e6 * 1.60, 6)
    if not parsed:
        return None, report

    raw = parsed.get("sentences") or []
    if isinstance(raw, str):
        raw = split_sentences(raw)
    candidates: List[str] = []
    for item in raw:
        for s in split_sentences(str(item or "")):
            s = s.strip()
            if s:
                candidates.append(s)
    if not candidates:
        return None, report
    report["ran"] = True

    # evidence for the LOCAL-872 claim gate = the facts themselves.
    evidence = list(facts_texts)
    fact_token_sets = [_content_tokens(t) for t in facts_texts]
    fact_token_sets = [s for s in fact_token_sets if s]

    kept: List[str] = []
    seen = set()
    for s in candidates:
        if len(s) < 12:
            continue
        key = fold(s)[:80]
        if key in seen:
            continue
        # 873B fact-sheet verify: the sentence must be traceable to a fact.
        if not _traceable_to_facts(s, fact_token_sets):
            report["rejected"] += 1
            log(f"  [LOCAL-873C] rejected (not traceable): {s[:90]}")
            continue
        # LOCAL-872 claim gate: no unsourced named claim / date.
        if claim_gate_fn is not None:
            try:
                bad = claim_gate_fn(s, title, evidence, location)
            except Exception:
                bad = []
            if bad:
                report["rejected"] += 1
                log(f"  [LOCAL-873C] rejected (claim gate {bad}): {s[:90]}")
                continue
        seen.add(key)
        kept.append(s)

    # dedup against the Orientation, both directions.
    kept = dedup_against_orientation(kept, orientation)
    report["kept"] = len(kept)
    if len(kept) < min_sentences:
        log(f"  [LOCAL-873C] narration kept only {len(kept)} traceable "
            f"sentence(s) (< {min_sentences}) for {title!r}; falling back")
        return None, report
    return kept[:max_sentences], report


def _parse_blocks(tour_text: str):
    """Yield (header_line_index, stop_num, title, start, end) for each stop."""
    lines = tour_text.split("\n")
    headers = [(i, m) for i, ln in enumerate(lines)
               for m in [_STOP_HDR_RE.match(ln)] if m]
    for h_idx, (line_no, m) in enumerate(headers):
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        yield line_no, m.group(1), m.group(2).strip(), start, end


def _body_line_indices(lines: List[str], start: int, end: int) -> List[int]:
    """Indices of the stop's standalone narration paragraphs (NOT the Orientation
    label line, field lines, Directions or Sources)."""
    out = []
    for i in range(start, end):
        ln = lines[i]
        s = ln.strip()
        if not s:
            continue
        if (_FIELD_LINE_RE.match(ln) or _STOP_HDR_RE.match(ln)
                or _ORIENT_RE.match(s) or _DIRECTIONS_RE.match(s)
                or s.lower().startswith("sources")):
            continue
        out.append(i)
    return out


def _orientation_text(lines: List[str], start: int, end: int) -> str:
    """The stop's Orientation line value (text after 'Orientation:'), or '' when
    the stop has none. Used to dedup the body against the Orientation."""
    for i in range(start, end):
        s = lines[i].strip()
        if _ORIENT_RE.match(s):
            _, _, val = s.partition(":")
            return val.strip()
    return ""


def rebuild_thin_delivered_stops(
        tour_text: str, location: str = "", *,
        facts_by_title: Optional[Dict[str, List]] = None,
        escalate_fn: Optional[Callable] = None,
        pins_by_title: Optional[Dict[str, Tuple[float, float]]] = None,
        aliases_by_title: Optional[Dict[str, List[str]]] = None,
        types_by_title: Optional[Dict[str, str]] = None,
        min_specifics: int = MIN_SPECIFICS,
        min_sentences: int = 5,
        trigger_sentences: int = 4,
        fact_filter: Optional[Callable] = None,
        narrate_fn: Optional[Callable] = None,
        claim_gate_fn: Optional[Callable] = None,
        narrate: bool = True,
        cost_cap: float = 0.01, log: Optional[Callable] = None,
        ) -> Tuple[str, Dict]:
    """Post-narration thin check on the DELIVERED text.

    For each stop whose delivered body has fewer than ``min_specifics`` sourced
    specifics OR fewer than ``min_sentences`` content sentences: if we have no
    facts for it yet, escalate ONCE (``escalate_fn`` or
    ``thin_stop_search.escalate_thin_stop``, cost-capped); then REBUILD the body
    from the sourced facts. Returns ``(new_text, report)``.

    [LOCAL-873C] The rebuild is NARRATED first: one cheap gpt-4.1-mini call
    (``narrate_fn``, temperature 0.3, cost-capped, counted in ``added_cost_usd``)
    rewrites the facts as 5–7 spoken second-person present-tense sentences, each
    verified traceable to a fact and passed through the LOCAL-872 claim gate
    (``claim_gate_fn``). On success the stop body is REPLACED with that narration.
    If the call fails or the gate rejects too much, it falls back to the
    DETERMINISTIC append — now with the 873C repair fixes (sentence-case, no
    "X Known as Y," fragment, local diacritic spelling from the title). Either
    way, no body sentence repeats an Orientation sentence (both directions).
    Never raises."""
    report = {
        "ran": True, "checked": 0, "rebuilt": 0, "escalated": 0,
        "added_cost_usd": 0.0, "stops": [],
    }
    log = log or (lambda *_a, **_k: None)
    if not tour_text or not tour_text.strip():
        report["ran"] = False
        return tour_text or "", report
    facts_by_title = dict(facts_by_title or {})
    lines = tour_text.split("\n")

    def _facts_for(title):
        for k, v in facts_by_title.items():
            if fold(k) == fold(title):
                return v
        return None

    try:
        blocks = list(_parse_blocks(tour_text))
    except Exception:
        report["ran"] = False
        return tour_text, report

    for _hdr, stop_num, title, start, end in reversed(blocks):
        report["checked"] += 1
        body_idx = _body_line_indices(lines, start, end)
        body_text = "\n".join(lines[i] for i in body_idx)
        facts = _facts_for(title)
        before = count_delivered_specifics(body_text, facts)
        body_sent_n = len(split_sentences(body_text))
        # Trigger: thin on sourced specifics, OR fewer than trigger_sentences
        # content sentences. (The trigger is 4 so a healthy 4-sentence stop is not
        # disturbed; once a stop IS rebuilt it is filled to min_sentences=5 so a
        # rebuilt stop like Book Street clears the ticket's >= 5 bar.)
        if before >= min_specifics and body_sent_n >= trigger_sentences:
            continue

        # Escalate now if we have no facts for this stop yet.
        if not facts:
            _esc = escalate_fn
            if _esc is None and os.environ.get("THIN_STOP_SEARCH", "1").strip() != "0":
                try:
                    import thin_stop_search as _ts
                    _esc = _ts.escalate_thin_stop
                except Exception:
                    _esc = None
            if _esc is not None:
                _blk = "\n".join(lines[start:end])
                pin = (pins_by_title or {}).get(title)
                if pin is None:
                    _cm = _COORD_RE.search(_blk)
                    if _cm:
                        try:
                            pin = (float(_cm.group(1)), float(_cm.group(2)))
                        except Exception:
                            pin = None
                aliases = (aliases_by_title or {}).get(title) or []
                ptype = (types_by_title or {}).get(title) or ""
                if not ptype:
                    _tm = _TYPE_RE.search(_blk)
                    if _tm:
                        ptype = _tm.group(1).strip()
                try:
                    rep = _esc(title, location, existing_facts=[], pin=pin,
                               aliases=aliases, places_type=ptype,
                               cost_cap=cost_cap)
                except Exception as e:
                    log(f"  [LOCAL-873B] delivered escalate skipped {title!r}: {e}")
                    rep = None
                if rep and rep.get("facts"):
                    facts = rep["facts"]
                    facts_by_title[title] = facts
                    report["escalated"] += 1
                    report["added_cost_usd"] += float(rep.get("cost_usd", 0.0) or 0.0)

        if not facts:
            continue

        orientation = _orientation_text(lines, start, end)

        # ── LOCAL-873C: NARRATE the rebuild first ────────────────────────────
        # One cheap gpt-4.1-mini call rewrites the facts as 5–7 spoken sentences,
        # each verified traceable to a fact and cleared by the LOCAL-872 claim
        # gate, deduped against the Orientation. On success the body is REPLACED
        # by the narration (not appended), so no raw scraped copy and no repeated
        # Orientation ship. On any failure/rejection we fall back to the
        # deterministic append below.
        narrated = None
        if narrate and (narrate_fn is not None
                        or os.environ.get("OPENAI_API_KEY")):
            try:
                _sents, _nrep = narrate_stop_body(
                    title, facts, orientation, location,
                    narrate_fn=narrate_fn, claim_gate_fn=claim_gate_fn,
                    min_sentences=min_sentences, log=log)
            except Exception as e:
                log(f"  [LOCAL-873C] narration skipped {title!r}: {e}")
                _sents, _nrep = None, {"cost_usd": 0.0}
            report["added_cost_usd"] += float(_nrep.get("cost_usd", 0.0) or 0.0)
            # a narrated sentence may still name an off-pin landmark / admin
            # geography — run the same fact_filter the deterministic path uses.
            if _sents and fact_filter is not None:
                _blk = "\n".join(lines[start:end])
                _sents = [s for s in _sents
                          if _safe_fact_ok(fact_filter, title, s, _blk)]
                if len(_sents) < min_sentences:
                    _sents = None
            narrated = _sents

        if narrated:
            add_text = " ".join(narrated)
            # Replace the stop's body with the narration: first body paragraph
            # holds it, the rest are blanked. If the stop has no body paragraph,
            # insert one just before Directions.
            if body_idx:
                lines[body_idx[0]] = add_text
                for j in body_idx[1:]:
                    lines[j] = ""
            else:
                insert_at = end
                for i in range(start, end):
                    if _DIRECTIONS_RE.match(lines[i].strip()):
                        insert_at = i
                        break
                lines.insert(insert_at, add_text)
            report["rebuilt"] += 1
            report["narrated"] = report.get("narrated", 0) + 1
            report["stops"].append({
                "stop": stop_num, "title": title,
                "specifics_before": before,
                "specifics_after": count_delivered_specifics(add_text, facts),
                "added_sentences": len(narrated), "narrated": True,
            })
            log(f"  [LOCAL-873C] delivered-body thin check: stop {stop_num} "
                f"{title[:40]!r} NARRATED from facts -> {len(narrated)} spoken "
                f"sentence(s)")
            continue

        # ── deterministic fallback (873B append, with 873C repair fixes) ─────
        # Which fact sentences are not already in the body? Compare on DISTINCTIVE
        # content only — strip the venue-name tokens (which repeat in every
        # sentence of the stop) and generic words, or a fact that merely names the
        # venue is wrongly judged a duplicate (Book Street: every fact shares
        # {nguyen, binh, book, street} with the body, so all 14 were filtered).
        _name_toks = {w for w in fold(title).split() if len(w) >= 4}
        _GENERIC = {"this", "that", "with", "from", "into", "here", "there",
                    "street", "city", "book", "place", "space", "known", "years",
                    "recent", "which", "where", "their", "these", "those"}

        def _distinctive(s):
            return {w for w in _content_tokens(s)
                    if w not in _name_toks and w not in _GENERIC}

        # [LOCAL-873C] dedup the existing body against the Orientation too, so a
        # body that STARTS as a verbatim copy of the Orientation (873B Book Street)
        # is cleaned before we measure what to add.
        _existing_sents = split_sentences(body_text)
        _kept_existing = dedup_against_orientation(_existing_sents, orientation)
        _dropped_orient = [s for s in _existing_sents if s not in _kept_existing]
        present = [_distinctive(s) for s in _kept_existing]
        additions = []
        spec_added = 0

        def _try_add(candidates, *, counts_as_specific):
            nonlocal spec_added
            for fs in candidates:
                if (before + spec_added >= min_specifics
                        and body_sent_n + len(additions) >= min_sentences):
                    return
                if fact_filter is not None:
                    try:
                        if not fact_filter(title, fs, "\n".join(lines[start:end])):
                            continue
                    except Exception:
                        pass
                # never re-add a sentence that duplicates the Orientation
                if dedup_against_orientation([fs], orientation) == []:
                    continue
                ftoks = _distinctive(fs)
                if ftoks and any(len(ftoks & p) >= 3 for p in present):
                    continue
                if fs in additions:
                    continue
                additions.append(fs)
                present.append(ftoks)
                if counts_as_specific:
                    spec_added += 1

        # Phase 1 — SPECIFIC facts (cover the >= min_specifics sourced-specific bar).
        _try_add(fact_sentences(facts, limit=min_sentences + 6,
                                require_specific=True, title=title),
                 counts_as_specific=True)
        # Phase 2 — clean non-specific venue facts, only to reach the SENTENCE floor.
        if body_sent_n + len(additions) < min_sentences:
            _try_add(fact_sentences(facts, limit=min_sentences + 6,
                                    require_specific=False, title=title),
                     counts_as_specific=False)
        if not additions and not _dropped_orient:
            continue

        # If the body opened as a verbatim Orientation copy, rewrite the first
        # body paragraph to the deduped survivors before appending.
        if _dropped_orient and body_idx:
            lines[body_idx[0]] = " ".join(_kept_existing)
            for j in body_idx[1:]:
                lines[j] = ""

        if not additions:
            # Only the Orientation-dup cleanup happened; still count it as a rebuild.
            report["rebuilt"] += 1
            report["stops"].append({
                "stop": stop_num, "title": title,
                "specifics_before": before, "specifics_after": before,
                "added_sentences": 0, "narrated": False,
            })
            continue

        # Append the fact sentences to the stop's LAST body paragraph (or create
        # one just before Directions if the stop has no body paragraph).
        add_text = " ".join(additions)
        if body_idx:
            tgt = body_idx[-1] if not _dropped_orient else body_idx[0]
            cur = lines[tgt].rstrip()
            if not cur.strip():
                lines[tgt] = add_text
            else:
                sep = "" if cur.endswith((".", "!", "?")) else "."
                lines[tgt] = f"{cur}{sep} {add_text}".strip()
        else:
            # insert before the Directions line, else at end of block
            insert_at = end
            for i in range(start, end):
                if _DIRECTIONS_RE.match(lines[i].strip()):
                    insert_at = i
                    break
            lines.insert(insert_at, add_text)
            # indices after insert_at shift by 1; safe because we recompute blocks
            # only via stored start/end which we no longer use after this stop.
        report["rebuilt"] += 1
        report["stops"].append({
            "stop": stop_num, "title": title,
            "specifics_before": before,
            "specifics_after": before + spec_added,
            "added_sentences": len(additions), "narrated": False,
        })
        log(f"  [LOCAL-873B] delivered-body thin check: stop {stop_num} "
            f"{title[:40]!r} had {before} sourced specific(s) (< {min_specifics}); "
            f"rebuilt from facts -> +{len(additions)} fact sentence(s)")

    report["added_cost_usd"] = round(report["added_cost_usd"], 6)
    return "\n".join(lines), report
