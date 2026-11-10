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

# [LOCAL-884 §1] "No evidence" means "no factual claim", never "nothing to check".
# A stop whose evidence bundle is below this many characters is treated as having
# NO evidence: every FACTUAL sentence in it is UNSUPPORTED and dropped (it can
# only have come from the narrator's memory, since there is nothing to support
# it). Below this floor a bundle is too thin to ground anything — a stray token
# is not evidence for a date, a person or an event.
THIN_EVIDENCE_MIN_CHARS = int(os.environ.get("GROUNDING_THIN_EVIDENCE_CHARS", "20"))

# [LOCAL-884 §1] The D760 disclosure a stop gets when it has NO evidence at all
# and therefore no verified history to tell. It is honest and non-factual: it
# makes no checkable claim, so it never needs grounding.
NO_HISTORY_DISCLOSURE = (
    "We could not confirm verified historical details for this stop, so this "
    "part of the tour focuses on what you can see and sense here rather than on "
    "dates or events.")


def _evidence_is_thin(evidence: str) -> bool:
    """True when the stop's evidence bundle is empty or below the thin floor —
    i.e. there is effectively nothing to ground a factual claim against."""
    return len((evidence or "").strip()) < THIN_EVIDENCE_MIN_CHARS

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
    r"wars?|battles?|sieges?|coups?|revolutions?|independence|surrender|liberation|"  # [LOCAL-887] plurals
    r"invad\w+|invasions?|defeat\w*|victor(?:y|ies)|"
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


# [LOCAL-887] A sentence asserting what happens AT or FROM the stop ("Parties leaving
# from here set out to explore the tunnels", "Boats depart from this pier") is a
# checkable claim about the stop. The generic "from here" navigation cue must not
# exempt it.
_DEPARTURE_CUE_RE = re.compile(
    r"(?i)\b(?:(?:parties|groups?|tours?|trips?|cruises?|boats?|ferr(?:y|ies)|"
    r"buses|coaches|visitors|travell?ers|passengers|tourists|excursions?|"
    r"services?|speedboats?|waterbus(?:es)?|trains?)\b[^.!?]{0,60}?"
    r"\b(?:leav\w+|depart\w*|set(?:s|ting)?\s+(?:out|off|sail)|"
    r"embark\w*|board\w*|start\w*|begin\w*|sail\w*|run\w*|operate\w*)\b"
    r"[^.!?]{0,40}?\b(?:from|at|on)\s+(?:here|this\s+\w+)\b"
    r"|\bdepartures?\s+(?:from|at)\s+(?:here|this)\b"
    r"|\bfrom\s+here,?\s+(?:you\s+can\s+)?(?:take|catch|board|sail|"
    r"tours?|boats?|ferr(?:y|ies)|trips?|cruises?)\b)")


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
    # [LOCAL-887] "what happens from this stop" is a factual assertion.
    if _DEPARTURE_CUE_RE.search(s):
        return True
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
    "  SUPPORTED   — EVERY factual element in the sentence (each date, number, "
    "person, event, function and characterisation) is stated or directly implied "
    "by the evidence.\n"
    "  CONTRADICTED — the evidence states something that conflicts with it.\n"
    "  UNSUPPORTED — the evidence neither states nor implies it, OR the sentence "
    "mixes a supported fact with an extra claim/characterisation the evidence does "
    "NOT state (a partially-grounded sentence is UNSUPPORTED, not SUPPORTED).\n"
    "Also set \"legend\": true ONLY when the EVIDENCE itself frames the claim as a "
    "legend, myth, story or rumour (words like legend, myth, said to, reputedly, "
    "according to tradition). Otherwise \"legend\": false.\n"
    "Return STRICT JSON: {\"verdicts\": [{\"i\": <1-based index>, \"verdict\": "
    "\"SUPPORTED|CONTRADICTED|UNSUPPORTED\", \"evidence\": \"<short quote from the "
    "evidence, or empty>\", \"legend\": <bool>}]}. Judge conservatively: if ANY "
    "part of the sentence is not clearly in the evidence, it is UNSUPPORTED."
)


EVIDENCE_WINDOW = int(os.environ.get("GROUNDING_EVIDENCE_WINDOW", "6000"))
_TOKEN_RE = re.compile(r"[^\W_]{4,}", re.UNICODE)
_STOPW = frozenset({
    "that", "this", "with", "from", "were", "have", "been", "also", "their", "which",
    "there", "about", "where", "while", "after", "before", "into", "most", "more",
    "than", "when", "what", "they", "them", "then", "will", "your", "here", "still"})


def _fold_tok(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def key_tokens(sentences) -> set:
    """Checkable tokens of the sentences: years and content words (diacritics folded).
    A year or a name is exactly what the evidence must hold for the sentence to stand."""
    out = set()
    for sent in sentences or []:
        for t in _TOKEN_RE.findall(sent or ""):
            f = _fold_tok(t)
            if f not in _STOPW:
                out.add(f)
    return out


def evidence_chunks(evidence: str, max_len: int = 700) -> List[str]:
    """The evidence split into paragraph-sized chunks (a long line is split on
    sentence boundaries), in source order."""
    chunks: List[str] = []
    for ln in (evidence or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if len(ln) <= max_len:
            chunks.append(ln)
            continue
        cur = ""
        for sent in re.split(r"(?<=[.!?])\s+", ln):
            if cur and len(cur) + len(sent) + 1 > max_len:
                chunks.append(cur)
                cur = sent
            else:
                cur = (cur + " " + sent).strip()
        if cur:
            chunks.append(cur)
    return chunks


def _chunk_score(chunk: str, toks: set) -> float:
    ctoks = {_fold_tok(t) for t in _TOKEN_RE.findall(chunk)}
    hit = toks & ctoks
    years = {t for t in hit if t.isdigit()}
    return len(hit) + 3.0 * len(years)


def focus_evidence(evidence: str, sentences, cap: int = EVIDENCE_WINDOW,
                   exclude: str = "") -> str:
    """[LOCAL-887] The evidence window sent to the gate. When the whole bundle fits
    in ``cap`` it is sent unchanged. Otherwise the HEAD (lead) is kept and the rest
    of the window is filled with the chunks that share the most year/name tokens with
    the sentences being judged (kept in source order) -- NOT the first ``cap`` chars.
    A 17 KB City Hall bundle used to be cut at 6 KB, so the passage with
    "1898"/"1909"/Gardès never reached the judge. ``exclude`` drops chunks already
    sent (for the second look)."""
    ev = (evidence or "").strip()
    if len(ev) <= cap and not exclude:
        return ev
    chunks = evidence_chunks(ev)
    if exclude:
        seen = set(evidence_chunks(exclude))
        chunks = [c for c in chunks if c not in seen]
        head_n = 0
    else:
        head_n = 0
        used = 0
        while head_n < len(chunks) and used + len(chunks[head_n]) <= cap // 3:
            used += len(chunks[head_n]) + 1
            head_n += 1
    toks = key_tokens(sentences)
    chosen = set(range(head_n))
    used = sum(len(chunks[i]) + 1 for i in chosen)
    ranked = sorted(range(head_n, len(chunks)),
                    key=lambda i: (-_chunk_score(chunks[i], toks), i))
    for i in ranked:
        if _chunk_score(chunks[i], toks) <= 0:
            break
        if used + len(chunks[i]) + 1 > cap:
            continue
        chosen.add(i)
        used += len(chunks[i]) + 1
    return "\n".join(chunks[i] for i in sorted(chosen))


def classify_sentences(title: str, factual_sentences: List[str], evidence: str,
                       *, classify_fn: Optional[Callable] = None,
                       model: str = GROUNDING_MODEL, _no_focus: bool = False
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
    user = (f"STOP: {title}\n\nEVIDENCE:\n{(evidence or '').strip() if _no_focus else focus_evidence(evidence, factual_sentences)}\n\n"
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


def _second_look(title, factual_sentences, verdicts, evidence, *, classify_fn,
                 model, rep):
    """Re-check UNSUPPORTED (non-legend) verdicts against evidence chunks the first
    window left out. Returns the (possibly upgraded) verdict map; one extra call at
    most, only when such chunks exist."""
    drops = [i for i, v in verdicts.items()
             if v.get("verdict") == "UNSUPPORTED" and not v.get("legend")
             and 1 <= i <= len(factual_sentences)]
    if not drops:
        return verdicts
    first = focus_evidence(evidence, factual_sentences)
    if len((evidence or "").strip()) <= len(first):
        return verdicts                    # the judge already saw everything
    sents = [factual_sentences[i - 1] for i in drops]
    more = focus_evidence(evidence, sents, cap=EVIDENCE_WINDOW, exclude=first)
    if not more.strip():
        return verdicts
    v2, crep = classify_sentences(title, sents, more, classify_fn=classify_fn,
                                  model=model, _no_focus=True)
    rep["cost_usd"] = rep.get("cost_usd", 0.0) + crep.get("cost_usd", 0.0)
    out = dict(verdicts)
    for k, i in enumerate(drops, 1):
        nv = v2.get(k)
        if nv and nv["verdict"] == "SUPPORTED":
            out[i] = nv
            rep["second_look_saved"] = rep.get("second_look_saved", 0) + 1
    return out


# ── the gate over one body ────────────────────────────────────────────────────
def apply_grounding_gate(title: str, body_prose: str, evidence: str,
                         *, classify_fn: Optional[Callable] = None,
                         model: str = GROUNDING_MODEL,
                         log: Optional[Callable] = None
                         ) -> Tuple[str, Dict]:
    """Ground ONE stop's body prose against its evidence. Returns (new_prose,
    report). report carries kept/contradicted/unsupported/labelled counts, the
    dropped sentences, and cost. Deterministic apart from the single LLM call;
    never raises.

    [LOCAL-884 §1] "No evidence" means "no factual claim", never "nothing to
    check". When the stop's evidence bundle is empty or thin
    (< THIN_EVIDENCE_MIN_CHARS), every FACTUAL sentence is UNSUPPORTED and is
    dropped (it can only have come from the narrator's memory, since there is
    nothing to support it) — no LLM call is made. Non-factual sentences (sensory,
    directional, reflective) are always kept. When there IS evidence, each factual
    sentence is judged by the single LLM call: KEEP supported, DROP contradicted,
    DROP unsupported (unless the evidence frames it as a legend → disclose, D760).
    A sentence the LLM is silent on (judged against real evidence but no verdict
    returned) is KEPT. ``labelled`` counts every factual sentence the gate acted
    on (dropped or kept-after-judgement); it is > 0 whenever the body carries a
    factual sentence."""
    rep = {"title": title, "kept": 0, "contradicted": 0, "unsupported": 0,
           "disclosed": 0, "labelled": 0, "dropped": [], "cost_usd": 0.0,
           "called": False, "no_evidence": False,
           "sentences_before": 0, "sentences_after": 0}
    sents = _content_sentences(body_prose)
    rep["sentences_before"] = len(sents)
    if not sents:
        return body_prose, rep

    factual_idx = [i for i, s in enumerate(sents) if is_factual_sentence(s)]
    if not factual_idx:
        # no factual claim at all: nothing to ground, keep the atmospheric body.
        rep["kept"] = len(sents)
        rep["sentences_after"] = len(sents)
        return body_prose, rep

    # [LOCAL-884 §1] Factual sentences present but NO (or thin) evidence to back
    # them: every factual sentence is UNSUPPORTED and dropped. This is the main
    # wave-42 bug — the cloud shipped "founded in 1163" / "designed by Eiffel" /
    # "ordered by Diệm" precisely because the stop had no evidence and the gate
    # kept everything. No LLM call: there is nothing to check against.
    if _evidence_is_thin(evidence):
        rep["no_evidence"] = True
        out: List[str] = []
        for i, s in enumerate(sents):
            if i in factual_idx:
                rep["labelled"] += 1
                rep["unsupported"] += 1
                rep["dropped"].append(("UNSUPPORTED(no-evidence)", s[:80]))
            else:
                out.append(s)
                rep["kept"] += 1
        new_prose = " ".join(out).strip()
        rep["sentences_after"] = len(_content_sentences(new_prose))
        if log:
            log(f"  [LOCAL-884] grounding {title[:48]}: no evidence -> "
                f"labelled {rep['labelled']}, {rep['unsupported']} unsupported "
                f"(dropped), {rep['kept']} non-factual kept")
            for why, frag in rep["dropped"]:
                log(f"      [LOCAL-884] dropped ({why}): {frag}")
        return new_prose, rep

    factual_sentences = [sents[i] for i in factual_idx]
    verdicts, crep = classify_sentences(
        title, factual_sentences, evidence, classify_fn=classify_fn, model=model)
    rep["cost_usd"] = crep.get("cost_usd", 0.0)
    rep["called"] = crep.get("called", False)

    # [LOCAL-887] SECOND LOOK. Before an UNSUPPORTED sentence is dropped, search the
    # FULL evidence for its key tokens (years, names): chunks the first window did
    # not contain are shown to the judge once more, for those sentences only.
    try:
        verdicts = _second_look(title, factual_sentences, verdicts, evidence,
                                classify_fn=classify_fn, model=model, rep=rep)
    except Exception:
        pass

    out = []
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
        rep["labelled"] += 1
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
        log(f"  [LOCAL-883] grounding {title[:48]}: labelled {rep['labelled']}, "
            f"{rep['kept']} kept, "
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



# [LOCAL-888] Minimum sentences for a stop with no evidence: the disclosure plus
# non-factual sensory sentences. Nothing here states a date, a name or an event.
MIN_NO_EVIDENCE_SENTENCES = int(os.environ.get("GROUNDING_MIN_NO_EVIDENCE_SENTENCES", "4"))
_SENSORY_TEMPLATES = (
    "Take a moment at {t} and look around you at the street, the people and the "
    "pace of the place.",
    "Listen for the sounds that belong to this spot, and notice how the light "
    "falls across the buildings and the pavement.",
    "Stay a while if you can, and let the atmosphere here tell you what the "
    "records do not.",
    "Watch how people move through this part of the city, and notice what they "
    "stop to look at.",
)


def sensory_body(title: str, kept: List[str], target: int) -> List[str]:
    """Pad ``kept`` with non-factual sensory sentences until it holds ``target``
    content sentences. The disclosure (if present) stays last. Pure, free."""
    out = list(kept)
    disc = [s for s in out if _fold(NO_HISTORY_DISCLOSURE)[:30] in _fold(s)]
    base = [s for s in out if s not in disc]
    i = 0
    while len(base) + len(disc) < target and i < len(_SENSORY_TEMPLATES):
        cand = _SENSORY_TEMPLATES[i].format(t=title)
        i += 1
        if not any(_fold(cand)[:30] == _fold(b)[:30] for b in base):
            base.append(cand)
    return base + disc


def _issue_score(iss: Dict) -> int:
    return (len(iss.get("dangling") or []) + len(iss.get("bare_surname") or [])
            + (1 if iss.get("missing_event") else 0))


def _coherence_pass(title, sents, evidence, location, *, classify_fn, narrate_fn,
                    model, log):
    """[LOCAL-888] Returns (new_sentences|None, report). One re-narration from the
    KEPT sentences + evidence, gated once more, accepted only when it has fewer
    coherence defects and is not shorter than 4 sentences (or the original). Any
    defect left over is repaired deterministically: the evidence's own dated event
    sentence is inserted; a still-dangling opener is dropped if >= 4 remain."""
    import stop_coherence as sc
    rep = {"issues_before": 0, "issues_after": 0, "renarrated": False,
           "event_inserted": False, "dropped_dangling": 0, "cost_usd": 0.0}
    iss = sc.coherence_issues(sents, title, location, evidence)
    rep["issues_before"] = _issue_score(iss)
    if not sc.has_issues(iss):
        return None, rep
    cur = list(sents)
    out, r = sc.renarrate_from_kept(title, cur, evidence, location, issues=iss,
                                    narrate_fn=narrate_fn, log=log)
    rep["cost_usd"] += r.get("cost_usd", 0.0)
    if out:
        reg, rg = apply_grounding_gate(title, " ".join(out), evidence,
                                       classify_fn=classify_fn, model=model, log=log)
        rep["cost_usd"] += rg.get("cost_usd", 0.0)
        cand = _content_sentences(reg)
        ciss = sc.coherence_issues(cand, title, location, evidence)
        if (_issue_score(ciss) < _issue_score(iss)
                and len(cand) >= min(4, max(len(cur), 1)) and len(cand) >= 1):
            cur, iss = cand, ciss
            rep["renarrated"] = True
    ev_missing = iss.get("missing_event")
    if ev_missing:
        cur = sc.insert_event_sentence(cur, ev_missing)
        rep["event_inserted"] = True
    # still-dangling openers: drop them only when the stop keeps >= 4 sentences
    dang = sorted({i for i, _k, _f in sc.dangling_reference_issues(cur, title, location)},
                  reverse=True)
    for i in dang:
        if len(cur) - 1 >= 4:
            cur.pop(i)
            rep["dropped_dangling"] += 1
    rep["issues_after"] = _issue_score(sc.coherence_issues(cur, title, location, evidence))
    if log:
        log(f"  [LOCAL-888] coherence {title[:40]}: issues {rep['issues_before']} -> "
            f"{rep['issues_after']} (renarrated={rep['renarrated']}, "
            f"event_inserted={rep['event_inserted']}, "
            f"dropped_dangling={rep['dropped_dangling']})")
    return cur, rep


# ── the tour-level gate ───────────────────────────────────────────────────────
def ground_tour_text(tour_text: str, evidence_by_title: Dict[str, str],
                     *, location: str = "",
                     classify_fn: Optional[Callable] = None,
                     rebuild_fn: Optional[Callable] = None,
                     facts_by_title: Optional[Dict] = None,
                     model: str = GROUNDING_MODEL,
                     max_cost_usd: Optional[float] = None,
                     coherence: bool = False,
                     narrate_fn: Optional[Callable] = None,
                     log: Optional[Callable] = None) -> Tuple[str, Dict]:
    """Run the strict grounding gate over every 'Stop N:' block.

    [LOCAL-888] The shortfall rebuild is fed the stop's EVIDENCE sentences when it
    has no thin-fact list (it used to receive an empty list and silently do
    nothing), and ``coherence=True`` adds the post-gate coherence pass: dangling
    openers / bare surnames / a missing dated defining event trigger ONE
    re-narration from the kept sentences + evidence, gated once more.

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
           "total_labelled": 0, "no_history_stops": 0,
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
        rep["total_labelled"] += grep.get("labelled", 0)
        changed = grounded.strip() != body.strip()
        if changed:
            new_text = _replace_block_body(new_text, stop_num,
                                           _content_sentences(grounded))
            rep["grounded"] += 1

        # Shortfall → 873C narrated rebuild from evidence only, re-gated once.
        after = grep.get("sentences_after", 0)
        rebuilt_ok = False
        if (after < MIN_CONTENT_SENTENCES and rebuild_fn is not None
                and (max_cost_usd is None or rep["cost_usd"] < max_cost_usd)):
            facts = list(_lookup(norm_facts, title) or [])
            # [LOCAL-888] 873C did not run because most stops have NO thin-fact
            # list (their evidence is an article / snippets): the rebuild got [].
            # Feed it the evidence's own fact sentences.
            if len(facts) < 6 and not _evidence_is_thin(ev or ""):
                try:
                    from stop_coherence import evidence_fact_sentences
                    for _fs in evidence_fact_sentences(ev or "", limit=14):
                        if _fs not in facts:
                            facts.append(_fs)
                except Exception:
                    pass
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
                rep["total_labelled"] += rgrep.get("labelled", 0)
                if rgrep.get("sentences_after", 0) >= max(after, 1):
                    new_text = _replace_block_body(
                        new_text, stop_num, _content_sentences(reg))
                    rep["rebuilt"] += 1
                    rebuilt_ok = True
                    after = rgrep.get("sentences_after", 0)

        # [LOCAL-888] COHERENCE after drops: the kept sentences must read as prose.
        if (coherence and not grep.get("no_evidence")
                and not _evidence_is_thin(ev or "")
                and (max_cost_usd is None or rep["cost_usd"] < max_cost_usd)):
            try:
                _cur_block = _block_for(new_text, stop_num)
                _cur = _content_sentences(_block_body_prose(_cur_block or ""))
                _new, _crep = _coherence_pass(
                    title, _cur, ev or "", location, classify_fn=classify_fn,
                    narrate_fn=narrate_fn, model=model, log=log)
                rep["cost_usd"] += _crep.get("cost_usd", 0.0)
                if _new is not None and _new != _cur:
                    new_text = _replace_block_body(new_text, stop_num, _new)
                    rep["coherence_fixed"] = rep.get("coherence_fixed", 0) + 1
                rep.setdefault("coherence", []).append(
                    {"stop": stop_num, "title": title, **{
                        k: v for k, v in _crep.items() if k != "cost_usd"}})
            except Exception as _e:
                if log:
                    log(f"  [LOCAL-888] coherence pass skipped (non-fatal): {_e}")

        # [LOCAL-884 §1] A stop with NO evidence whose factual sentences were all
        # dropped, and which the evidence-only rebuild could not refill (there was
        # no evidence to rebuild from), must NOT be left with a bare or empty
        # body. Give it a short, honest, NON-FACTUAL body: whatever atmospheric /
        # orientation sentences survived, plus the D760 disclosure that no
        # verified history was found. It never gets the narrator's memory back.
        if grep.get("no_evidence") and not rebuilt_ok:
            cur_block = _block_for(new_text, stop_num)
            cur_prose = _block_body_prose(cur_block) if cur_block is not None else ""
            kept_sents = _content_sentences(cur_prose)
            disclosure = NO_HISTORY_DISCLOSURE
            if not any(_fold(disclosure)[:30] in _fold(s) for s in kept_sents):
                kept_sents = kept_sents + [disclosure]
            # [LOCAL-888] a no-evidence stop is not left a 2-sentence fragment: pad
            # with NON-FACTUAL sensory sentences (no date, name or claim) up to 4.
            kept_sents = sensory_body(title, kept_sents, MIN_NO_EVIDENCE_SENTENCES)
            new_text = _replace_block_body(new_text, stop_num, kept_sents)
            rep["no_history_stops"] += 1
            if log:
                log(f"  [LOCAL-884] Stop {stop_num} '{title[:40]}': no verified "
                    f"history; honest non-factual body + D760 disclosure "
                    f"({len(kept_sents)} sentence(s))")

        if log:
            log(f"  [LOCAL-884] Stop {stop_num} '{title[:40]}': labelled "
                f"{grep.get('labelled', 0)}"
                + (" (no-history disclosed)" if grep.get("no_evidence")
                   and not rebuilt_ok else ""))
        rep["details"].append({
            "stop": stop_num, "title": title, "labelled": grep.get("labelled", 0),
            "kept": grep["kept"], "contradicted": grep["contradicted"],
            "unsupported": grep["unsupported"], "disclosed": grep["disclosed"],
            "no_evidence": grep.get("no_evidence", False)})
    if log:
        log(f"  [LOCAL-883] grounding gate: {rep['stops']} stop(s), "
            f"{rep['grounded']} edited, {rep['rebuilt']} rebuilt, "
            f"{rep['no_history_stops']} no-history, "
            f"{rep['total_labelled']} labelled, "
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
