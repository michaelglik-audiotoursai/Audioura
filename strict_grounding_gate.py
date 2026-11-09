#!/usr/bin/env python3
"""strict_grounding_gate.py — LOCAL-883 (D771): every factual sentence must be
backed by the stop's OWN evidence.

WHY THIS MODULE EXISTS
    Five cloud proofs in a row (waves 37–41) each fixed the previous run's false
    claims with a pattern-specific gate, and each run produced NEW ones from the
    narrator's own memory:
      * City Hall — "In 1945 … the declaration of independence" (that was Ba Đình,
        Hanoi);
      * Pier — a Fall-of-Saigon evacuation "from this very platform" (unsourced);
      * Post Office — "an earlier structure completed … by Gustave Eiffel";
      * Palace — the 30 April 1975 tank lost again.
    Pattern gates cannot keep up. This gate changes the MECHANISM: instead of
    chasing each false claim, it requires that every FACTUAL sentence in a stop's
    delivered body be SUPPORTED by that stop's own evidence bundle (its article(s),
    the 873 page facts, the 873 geo/name-gated snippets). A sentence the evidence
    does not support is dropped — whatever city, whatever claim.

WHAT IT DOES, per stop (landmark, user, business), AFTER narration + every gate:
    1. Split the delivered body into sentences.
    2. Mark each FACTUAL (states a date, a number, a named person, an event, a
       function, a "first/only/largest") or NON-FACTUAL (sensory, directional,
       reflective) — a deterministic cue list, confirmed/overridden by the LLM
       label.
    3. ONE gpt-4.1-mini call per stop (temperature 0, JSON) is given the stop's
       evidence bundle and the FACTUAL sentences; for each it returns
       SUPPORTED / CONTRADICTED / UNSUPPORTED plus the supporting evidence quote.
    4. KEEP supported. DROP contradicted. DROP unsupported — UNLESS the evidence
       itself frames the claim as a legend/story, then DISCLOSE it (D760).
    5. If the stop falls below 5 content sentences, rebuild from evidence only
       (the 873C narrated rebuild) and run the rebuilt body back through the gate
       ONCE.

COST
    One gpt-4.1-mini call per stop, temperature 0, bounded tokens → well under the
    $0.003/stop cap. A stop with no factual sentences and no evidence makes no
    call. The LLM backend is injectable (``classify_fn``) so the module is fully
    offline-testable; every deterministic helper is pure and never raises.

LOGGING
    ``[LOCAL-883] grounding <stop>: K kept, C contradicted, U unsupported`` and,
    for each dropped sentence, its first 80 characters.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple

from sentence_split import split_sentences

__all__ = [
    "MIN_CONTENT_SENTENCES", "GROUNDING_MODEL",
    "is_factual_sentence", "classify_sentences", "apply_grounding_gate",
    "ground_tour_text",
]

# A stop must keep at least this many content sentences; below it, the 873C
# narrated rebuild runs from evidence only and the result is re-gated once.
MIN_CONTENT_SENTENCES = int(os.environ.get("GROUNDING_MIN_CONTENT_SENTENCES", "5"))

# The checker model. gpt-4.1-mini, temperature 0, JSON — one call per stop.
GROUNDING_MODEL = os.environ.get("GROUNDING_GATE_MODEL", "gpt-4.1-mini")
_TEMPERATURE = float(os.environ.get("GROUNDING_GATE_TEMP", "0"))
_MAX_TOKENS = int(os.environ.get("GROUNDING_GATE_MAX_TOKENS", "900"))

# A content sentence is non-trivial prose (not a one-word fragment).
_MIN_CONTENT_LEN = 15

# ── block grammar (mirrors signature_story / spoken_text_hygiene exactly) ─────
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+?)\s*$")
_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
    r"Tour-Category|Address|Museum Information|Operational Details|Sources?)\s*:")
_ORIENT_RE = re.compile(r"(?i)^orientation:\s*(.*)$")
_DIRECTIONS_RE = re.compile(r"(?i)^directions:")

# ── FACTUAL / NON-FACTUAL deterministic cues ──────────────────────────────────
# A sentence is a FACTUAL ASSERTION when it states something checkable: a date or
# year, a number/measurement, a named person, a documented event or function, a
# superlative-of-record ("first/only/largest"). The LLM label then confirms or
# overrides this; the deterministic cue is the floor so a factual sentence is
# never skipped just because the model called it atmospheric.
_YEAR_RE = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")
# A digit, or a spelled-out small number, bound to a magnitude/count noun — a
# measurement or a count is a checkable fact. "58 metres", "six bronze bells",
# "three storeys".
_MAG_NOUN = (r"metres?|meters?|km|kilomet\w+|feet|foot|ft|yards?|"
             r"storeys?|stor(?:y|ies)|floors?|rooms?|seats?|hectares?|acres?|"
             r"years?|centur\w+|decades?|people|visitors?|tonnes?|tons?|"
             r"bells?|towers?|statues?|columns?|arches?|steps?|gates?|bays?|wings?")
_SPELLED_NUM = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                r"dozen|hundred|thousand")
_NUMBER_RE = re.compile(
    r"(?i)(?:\b\d[\d,\.]*|\b(?:" + _SPELLED_NUM + r"))\s+"
    r"(?:\w+\s+){0,2}(?:" + _MAG_NOUN + r")\b")
# A proper name: a capitalised multi-word run, or a title + name.
_PERSON_CUE_RE = re.compile(
    r"\b(?:King|Queen|Emperor|President|Bishop|Archbishop|Governor|General|"
    r"Mayor|architect|engineer|designer|builder|founder|artist|sculptor|"
    r"Mr|Mrs|Ms|Dr|Sir|Lord|Lady|Saint|St)\b")
_EVENT_FUNCTION_CUE_RE = re.compile(
    r"(?i)\b(?:built|constructed?|completed|opened|founded|established|"
    r"designed|commissioned|inaugurated|renovat\w+|restored|destroyed|"
    r"demolished|rebuilt|named after|named for|dedicated|consecrated|"
    r"serves? as|served as|housed?|houses|used as|became|functioned|"
    r"war|battle|siege|coup|revolution|independence|surrender|liberation|"
    r"assassinat\w+|proclamation|declaration|signed|capital|headquarters|"
    r"dynasty|colonial|reign|reunification)\b")
_RECORD_CUE_RE = re.compile(
    r"(?i)\b(?:first|only|largest|biggest|tallest|oldest|smallest|longest|"
    r"highest|earliest|unique|sole|the\s+most)\b")

# NON-FACTUAL cues: sensory, directional, reflective, second-person invitation.
# These are atmosphere/navigation and are NEVER grounded (a listener's "you stand
# before the red brick façade" is not a checkable claim). Deterministic exemption.
_NONFACTUAL_CUE_RE = re.compile(
    r"(?i)\b(?:you\s+(?:stand|see|notice|feel|sense|hear|find yourself|can\s+see|"
    r"may\s+notice|will\s+see|are\s+standing|now\s+stand)|"
    r"as\s+you\s+(?:walk|stroll|approach|stand|look|continue|arrive)|"
    r"take\s+(?:a\s+)?moment|imagine|picture|notice\s+how|look\s+(?:up|around|"
    r"across|for)|turn\s+your|before\s+you|around\s+you|to\s+your\s+(?:left|right))\b")
# Pure navigation/direction sentences (D107): never grounded. A directions line
# names where to go next and may carry a computed distance — neither is a
# checkable historical claim, so a distance number must not make it factual.
_NAV_CUE_RE = re.compile(
    r"(?i)(?:^|\b)(?:head(?:ing)?\s+(?:north|south|east|west|straight|towards?|"
    r"along|back|for|to|over|across)|"
    r"continue\s+(?:to|along|on|onto|past|for|north|south|east|west|straight|"
    r"towards?|walking)|"
    r"turn\s+(?:left|right|onto|toward|back|around|north|south|east|west)|"
    r"walk\s+(?:along|to|toward|towards|past|for|back|straight|north|south|east|west)|"
    r"proceed\s+(?:to|along|toward|north|south|east|west)|make\s+your\s+way|"
    r"cross\s+(?:the|over|at)|follow\s+the|from\s+here|"
    r"it\s+is\s+(?:a\s+)?(?:short|brief|\d)[\w\s-]*walk)")


def _content_sentences(prose: str) -> List[str]:
    return [s for s in split_sentences(prose or "")
            if len(s.strip()) >= _MIN_CONTENT_LEN]


def is_factual_sentence(sentence: str) -> bool:
    """Deterministic FACTUAL/NON-FACTUAL floor. True when the sentence states a
    date, a number/measurement, a named person, a documented event/function, or a
    superlative-of-record — and is not a pure navigation line. A sensory/reflective
    sentence with no checkable claim returns False. Pure; never raises."""
    s = (sentence or "").strip()
    if len(s) < _MIN_CONTENT_LEN:
        return False
    # A pure navigation line is exempt (D107) even if it mentions a distance.
    if _NAV_CUE_RE.search(s) and not (_PERSON_CUE_RE.search(s)
                                      or _EVENT_FUNCTION_CUE_RE.search(s)
                                      or _YEAR_RE.search(s)):
        return False
    has_claim = bool(
        _YEAR_RE.search(s) or _NUMBER_RE.search(s) or _PERSON_CUE_RE.search(s)
        or _EVENT_FUNCTION_CUE_RE.search(s) or _RECORD_CUE_RE.search(s)
        or _capitalised_proper_name(s))
    if not has_claim:
        return False
    # A sentence that is ONLY a sensory/second-person invitation, with no event
    # verb or date/number/person, is non-factual even if it name-drops the venue.
    if (_NONFACTUAL_CUE_RE.search(s)
            and not (_YEAR_RE.search(s) or _NUMBER_RE.search(s)
                     or _EVENT_FUNCTION_CUE_RE.search(s) or _RECORD_CUE_RE.search(s)
                     or _PERSON_CUE_RE.search(s))):
        return False
    return True


def _capitalised_proper_name(s: str) -> bool:
    """True when the sentence carries a proper name: two+ consecutive capitalised
    words not at the very start, or a known honorific+name. A single leading
    capital (sentence start) does not count."""
    # strip the leading capital of the first word so "The palace…" is not a name
    body = re.sub(r"^\W*\w+\s+", "", s)
    return bool(re.search(r"\b([A-ZÀ-Ý][\wÀ-ÿ'’.-]+\s+){1,}[A-ZÀ-Ý][\wÀ-ÿ'’.-]+", body))


# ── LLM classification (one call per stop) ────────────────────────────────────
def _default_classify(system: str, user: str, model: str,
                      temperature: float = _TEMPERATURE,
                      timeout: int = 40, max_tokens: int = _MAX_TOKENS
                      ) -> Tuple[Optional[dict], int, int]:
    """ONE gpt-4.1-mini JSON call. Returns (parsed|None, in_tok, out_tok). Billed
    by the project meter (requests.post is intercepted). Never raises; returns
    (None, 0, 0) with no key or on any failure. Mirrors
    thin_stop_delivery._default_narrate so the live meter accounts for it."""
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


_SYSTEM = (
    "You are a strict fact-checker for an audio walking tour. You are given one "
    "stop's EVIDENCE (its own encyclopedia article text, page facts and sourced "
    "snippets) and a numbered list of FACTUAL sentences from the stop's narration. "
    "For EACH sentence decide, using ONLY the evidence provided — never your own "
    "knowledge:\n"
    "  SUPPORTED   — the evidence states this fact (a date, number, person, event "
    "or function that matches).\n"
    "  CONTRADICTED — the evidence states something that conflicts with it.\n"
    "  UNSUPPORTED — the evidence neither states nor implies it.\n"
    "Also set \"legend\": true ONLY when the EVIDENCE itself frames the claim as a "
    "legend, myth, story or rumour (words like legend, myth, said to, reputedly, "
    "according to tradition). Otherwise \"legend\": false.\n"
    "Return STRICT JSON: {\"verdicts\": [{\"i\": <1-based index>, \"verdict\": "
    "\"SUPPORTED|CONTRADICTED|UNSUPPORTED\", \"evidence\": \"<short quote from the "
    "evidence, or empty>\", \"legend\": <bool>}]}. Judge conservatively: if the "
    "evidence does not clearly state the fact, it is UNSUPPORTED."
)


def classify_sentences(title: str, factual_sentences: List[str], evidence: str,
                       *, classify_fn: Optional[Callable] = None,
                       model: str = GROUNDING_MODEL
                       ) -> Tuple[Dict[int, Dict], Dict]:
    """Classify each factual sentence against the evidence with ONE LLM call.
    Returns ({index: {"verdict", "evidence", "legend"}}, cost_report). A missing
    or failed call yields an empty verdict map (caller keeps sentences it cannot
    judge rather than inventing a drop). Index is 1-based matching the prompt."""
    rep = {"in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0, "called": False}
    if not factual_sentences or not (evidence or "").strip():
        return {}, rep
    fn = classify_fn or _default_classify
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(factual_sentences, 1))
    user = (f"STOP: {title}\n\nEVIDENCE:\n{(evidence or '').strip()[:6000]}\n\n"
            f"FACTUAL SENTENCES:\n{numbered}\n\n"
            f"Return the JSON verdicts now.")
    parsed, in_tok, out_tok = fn(_SYSTEM, user, model)
    rep["called"] = True
    rep["in_tokens"], rep["out_tokens"] = in_tok, out_tok
    rep["cost_usd"] = _estimate_cost(model, in_tok, out_tok)
    out: Dict[int, Dict] = {}
    if isinstance(parsed, dict):
        for v in parsed.get("verdicts", []) or []:
            try:
                idx = int(v.get("i"))
            except (TypeError, ValueError):
                continue
            verdict = str(v.get("verdict", "")).strip().upper()
            if verdict not in ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED"):
                continue
            out[idx] = {"verdict": verdict,
                        "evidence": str(v.get("evidence", "") or "")[:300],
                        "legend": bool(v.get("legend", False))}
    return out, rep


def _estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    """Rough USD for a gpt-4.1-mini call (for the per-stop cap log; the live meter
    is authoritative)."""
    # gpt-4.1-mini published ~$0.40/1M input, ~$1.60/1M output.
    return round((in_tok / 1e6) * 0.40 + (out_tok / 1e6) * 1.60, 6)


# ── legend disclosure (D760) ──────────────────────────────────────────────────
_DISCLOSURE_PREFIX_RE = re.compile(
    r"(?i)^(?:a\s+(?:story|legend|local\s+legend)|according\s+to|legend\s+(?:has|holds)|"
    r"it\s+is\s+said|visitors?\s+(?:say|tell)|one\s+story)\b")


def _disclose_legend(sentence: str) -> str:
    """Rewrite a legend claim as a neutral disclosure (D760), no invented date.
    If the sentence already discloses itself, keep it."""
    s = (sentence or "").strip()
    if not s:
        return s
    if _DISCLOSURE_PREFIX_RE.match(s):
        return s
    core = s[0].lower() + s[1:] if s[:1].isupper() else s
    return "According to local legend, " + core


# ── the gate over one body ────────────────────────────────────────────────────
def apply_grounding_gate(title: str, body_prose: str, evidence: str,
                         *, classify_fn: Optional[Callable] = None,
                         model: str = GROUNDING_MODEL,
                         log: Optional[Callable] = None
                         ) -> Tuple[str, Dict]:
    """Ground ONE stop's body prose against its evidence. Returns (new_prose,
    report). report carries kept/contradicted/unsupported counts, the dropped
    sentences, and cost. Deterministic apart from the single LLM call; never
    raises. A sentence the gate cannot judge (no evidence, no LLM answer) is KEPT
    — the gate removes only what it can show is contradicted or unsupported."""
    rep = {"title": title, "kept": 0, "contradicted": 0, "unsupported": 0,
           "disclosed": 0, "dropped": [], "cost_usd": 0.0, "called": False,
           "sentences_before": 0, "sentences_after": 0}
    sents = _content_sentences(body_prose)
    rep["sentences_before"] = len(sents)
    if not sents:
        return body_prose, rep

    factual_idx = [i for i, s in enumerate(sents) if is_factual_sentence(s)]
    if not factual_idx or not (evidence or "").strip():
        # nothing checkable, or no evidence to check against: keep the body as-is.
        rep["kept"] = len(sents)
        rep["sentences_after"] = len(sents)
        return body_prose, rep

    factual_sentences = [sents[i] for i in factual_idx]
    verdicts, crep = classify_sentences(
        title, factual_sentences, evidence, classify_fn=classify_fn, model=model)
    rep["cost_usd"] = crep.get("cost_usd", 0.0)
    rep["called"] = crep.get("called", False)

    out: List[str] = []
    for i, s in enumerate(sents):
        if i not in factual_idx:
            out.append(s)                 # non-factual: always kept
            continue
        one_based = factual_idx.index(i) + 1
        v = verdicts.get(one_based)
        if v is None:
            out.append(s)                 # unjudged (LLM silent): keep
            rep["kept"] += 1
            continue
        verdict = v["verdict"]
        if verdict == "SUPPORTED":
            out.append(s)
            rep["kept"] += 1
        elif verdict == "CONTRADICTED":
            rep["contradicted"] += 1
            rep["dropped"].append(("CONTRADICTED", s[:80]))
        else:  # UNSUPPORTED
            if v.get("legend"):
                out.append(_disclose_legend(s))
                rep["disclosed"] += 1
                rep["kept"] += 1
            else:
                rep["unsupported"] += 1
                rep["dropped"].append(("UNSUPPORTED", s[:80]))

    new_prose = " ".join(out).strip()
    rep["sentences_after"] = len(_content_sentences(new_prose))
    if log:
        log(f"  [LOCAL-883] grounding {title[:48]}: {rep['kept']} kept, "
            f"{rep['contradicted']} contradicted, {rep['unsupported']} unsupported"
            + (f", {rep['disclosed']} disclosed" if rep['disclosed'] else ""))
        for why, frag in rep["dropped"]:
            log(f"      [LOCAL-883] dropped ({why}): {frag}")
    return new_prose, rep


# ── block parsing / rebuild (same grammar as signature_story) ─────────────────
def _split_blocks(text: str):
    titles = _STOP_HEADER_RE.findall(text or "")
    parts = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    out = []
    for (n, t), body in zip(titles, parts[1:]):
        out.append((int(n), t.strip(), body))
    return out


def _block_body_prose(block_text: str) -> str:
    out = []
    for line in block_text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = _ORIENT_RE.match(s)
        if m:
            continue                      # Orientation is a short gated label, not body
        if _FIELD_RE.match(s):
            continue
        out.append(s)
    return " ".join(out)


def _replace_block_body(tour_text: str, stop_num: int, new_sentences: List[str]
                        ) -> str:
    """Replace the narration body of one 'Stop N:' block with new_sentences,
    keeping the header, field lines, Orientation line/paragraph and the trailing
    Directions line. Returns the original text on any parse miss. (Mirrors
    signature_story._replace_block_body.)"""
    lines = tour_text.split("\n")
    hdr_idx = None
    for i, ln in enumerate(lines):
        m = re.match(r"(?i)^Stop\s+(\d+):\s*(.+)$", ln.strip())
        if m and int(m.group(1)) == stop_num:
            hdr_idx = i
            break
    if hdr_idx is None:
        return tour_text
    end_idx = len(lines)
    for j in range(hdr_idx + 1, len(lines)):
        if re.match(r"(?i)^Stop\s+\d+:", lines[j].strip()):
            end_idx = j
            break
    head_keep = []
    directions = []
    k = hdr_idx
    head_keep.append(lines[k])
    k += 1
    while k < end_idx:
        s = lines[k].strip()
        if _FIELD_RE.match(s) or not s:
            head_keep.append(lines[k])
            k += 1
            if re.match(r"(?i)^orientation:", s):
                while k < end_idx and lines[k].strip():
                    head_keep.append(lines[k])
                    k += 1
        else:
            break
    for j in range(end_idx - 1, k - 1, -1):
        if re.match(r"(?i)^Directions:", lines[j].strip()):
            directions = lines[j:end_idx]
            break
    new_block = list(head_keep)
    if new_block and new_block[-1].strip():
        new_block.append("")
    new_block.append(" ".join(new_sentences))
    if directions:
        new_block.append("")
        new_block.extend(d for d in directions if d.strip())
    return "\n".join(lines[:hdr_idx] + new_block + lines[end_idx:])


# ── the tour-level gate ───────────────────────────────────────────────────────
def ground_tour_text(tour_text: str, evidence_by_title: Dict[str, str],
                     *, location: str = "",
                     classify_fn: Optional[Callable] = None,
                     rebuild_fn: Optional[Callable] = None,
                     facts_by_title: Optional[Dict] = None,
                     model: str = GROUNDING_MODEL,
                     max_cost_usd: Optional[float] = None,
                     log: Optional[Callable] = None) -> Tuple[str, Dict]:
    """Run the strict grounding gate over every 'Stop N:' block.

    ``evidence_by_title`` maps a stop title (as it appears in the header, or a
    foldable variant) to that stop's joined evidence text (article + 873 facts +
    873 snippets). For each stop:
      * ground its body against its evidence (one LLM call);
      * if the grounded body falls below MIN_CONTENT_SENTENCES, call
        ``rebuild_fn(title, facts) -> [sentences]`` (the 873C narrated rebuild)
        and re-ground the rebuilt body ONCE; keep the rebuild only if it ends with
        at least as many content sentences as the grounded body.

    ``max_cost_usd`` caps spend: once the running cost would exceed it, remaining
    stops are left untouched (logged). Returns (new_tour_text, report)."""
    rep = {"stops": 0, "grounded": 0, "rebuilt": 0, "total_dropped": 0,
           "cost_usd": 0.0, "details": []}
    if not tour_text:
        return tour_text or "", rep
    facts_by_title = facts_by_title or {}
    norm_ev = {_fold(k): v for k, v in (evidence_by_title or {}).items()}
    norm_facts = {_fold(k): v for k, v in facts_by_title.items()}

    new_text = tour_text
    for stop_num, title, _block in _split_blocks(tour_text):
        rep["stops"] += 1
        if max_cost_usd is not None and rep["cost_usd"] >= max_cost_usd:
            if log:
                log(f"  [LOCAL-883] grounding budget ${max_cost_usd:.4f} reached; "
                    f"skipping Stop {stop_num} '{title[:40]}'")
            continue
        ev = _lookup(norm_ev, title)
        # Re-read the block from the (possibly already-edited) text.
        block = _block_for(new_text, stop_num)
        if block is None:
            continue
        body = _block_body_prose(block)
        if not body.strip():
            continue
        grounded, grep = apply_grounding_gate(
            title, body, ev or "", classify_fn=classify_fn, model=model, log=log)
        rep["cost_usd"] += grep.get("cost_usd", 0.0)
        rep["total_dropped"] += len(grep.get("dropped", []))
        changed = grounded.strip() != body.strip()
        if changed:
            new_text = _replace_block_body(new_text, stop_num,
                                           _content_sentences(grounded))
            rep["grounded"] += 1

        # Shortfall → 873C narrated rebuild from evidence only, re-gated once.
        after = grep.get("sentences_after", 0)
        if (after < MIN_CONTENT_SENTENCES and rebuild_fn is not None
                and (max_cost_usd is None or rep["cost_usd"] < max_cost_usd)):
            facts = _lookup(norm_facts, title) or []
            try:
                rebuilt_sents = rebuild_fn(title, facts) or []
            except Exception:
                rebuilt_sents = []
            if rebuilt_sents:
                rebuilt_prose = " ".join(rebuilt_sents)
                reg, rgrep = apply_grounding_gate(
                    title, rebuilt_prose, ev or "", classify_fn=classify_fn,
                    model=model, log=log)
                rep["cost_usd"] += rgrep.get("cost_usd", 0.0)
                if rgrep.get("sentences_after", 0) >= after:
                    new_text = _replace_block_body(
                        new_text, stop_num, _content_sentences(reg))
                    rep["rebuilt"] += 1
        rep["details"].append({
            "stop": stop_num, "title": title,
            "kept": grep["kept"], "contradicted": grep["contradicted"],
            "unsupported": grep["unsupported"], "disclosed": grep["disclosed"]})
    if log:
        log(f"  [LOCAL-883] grounding gate: {rep['stops']} stop(s), "
            f"{rep['grounded']} edited, {rep['rebuilt']} rebuilt, "
            f"{rep['total_dropped']} sentence(s) dropped; cost ${rep['cost_usd']:.4f}")
    return new_text, rep


def _block_for(text: str, stop_num: int) -> Optional[str]:
    for n, _t, body in _split_blocks(text):
        if n == stop_num:
            return body
    return None


def _fold(s: str) -> str:
    import unicodedata
    raw = str(s or "").lower().replace("đ", "d").replace("Đ", "d")
    nfkd = unicodedata.normalize("NFKD", raw)
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    out = re.sub(r"[^\w\s]", " ", out)
    return " ".join(out.split())


def _lookup(norm_map: Dict, title: str):
    key = _fold(title)
    if key in norm_map:
        return norm_map[key]
    for nk, v in norm_map.items():
        if nk and (nk in key or key in nk):
            return v
    return None
