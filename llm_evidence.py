"""[LOCAL-892] An LLM's own output is never EVIDENCE.

The 891 Saigon run shipped "In 1975 ... Bạch Đằng Pier was a significant evacuation point" and a
"1959 basilica" sentence because ``stop_knowledge_fallback.facts_as_snippets`` shapes an LLM's answer
about the stop like a search snippet (``source: knowledge_fallback:openai``); every evidence sink then
joined it into the stop's evidence blob and the gate and the audit read it as support. Circular
grounding: the narrator's memory vouching for the narrator.

Rule: material produced by a model (knowledge fallback, parametric, spine, fact-extractor output
without a source URL, an LLM extractor over fetched pages) may GUIDE what to look for (queries) and
may be shown to the narrator as a lead, but it is never put in front of the grounding judge or the
audit as support, never counts toward "this stop has enough sourced facts", and never makes a
sentence SUPPORTED.

Two layers, both here:

  * RECORD FILTER (``is_evidence_record`` / ``filter_records`` / ``lore_is_evidence``): every sink that
    turns snippet or lore dicts into an evidence string drops LLM records first.
  * TEXT REGISTRY (``register`` / ``scrub``): every LLM-generated passage is registered when it is
    produced; ``scrub`` removes registered passages from any evidence blob that still carries them
    (a path that joins strings before the record filter could run). The gate, the audit and
    ``aboutness.build_items`` all scrub their input.

PRODUCERS of LLM text that can reach an evidence sink (LOCAL-892 survey):

  1. stop_knowledge_fallback.facts_as_snippets       source 'knowledge_fallback:<provider>'
       -> _DIRECT_SNIPPETS_PER_STOP (D533 fallback, D545 restaurant lore, D537 place episodes)
  2. poi['_lore'] = fetch_stop_knowledge(...)['facts'] (D545/D548; {fact, confidence}, no url)
  3. spine_generator / spine text and fact_extractor.generate_fact_sheets_parallel (fact sheets are
       model-written; they feed the narrator, never the evidence blob)
  4. work_story_research._serper_fallback            LLM extractor over fetched pages (cached in
       work_story_research_cache; now marked, see that module)
  5. claim_provenance 'parametric' class             a sentence with NO source (by definition LLM)
  6. venue_parts 'lore' for the causal chain         seeded onto poi['_lore'] (like 2)
"""
from __future__ import annotations

import re
import threading
from typing import Dict, Iterable, List

LLM_SOURCE_RE = re.compile(
    r"(?i)^\s*(?:knowledge[_ -]?fallback|parametric|spine|fact[_ -]?extractor|fact[_ -]?sheet|llm|model|"
    r"generated|fallback|gemini|openai|gpt|claude|replenishment_rationale|rationale|internal)\b")

# explicit marker prefix for LLM-extracted passages stored in a cache that has no source column
LLM_CACHE_MARK = "\u2060[llm]\u2060 "

_lock = threading.Lock()
_REGISTRY: set = set()


def is_llm_source(source) -> bool:
    return bool(isinstance(source, str) and source.strip() and LLM_SOURCE_RE.match(source))


def _has_url(v) -> bool:
    return isinstance(v, str) and bool(re.search(r"https?://", v))


def is_evidence_record(rec) -> bool:
    """A snippet record (dict) or plain string. False when an LLM produced it."""
    if isinstance(rec, dict):
        if rec.get("llm") or rec.get("is_llm"):
            return False
        if is_llm_source(rec.get("source")) or is_llm_source(rec.get("origin")):
            return False
        t = " ".join(str(rec.get(k) or "") for k in ("snippet", "text", "fact"))
        if t.strip() and _registered(t):
            return False
        return True
    if isinstance(rec, str):
        return not _registered(rec)
    return True


def filter_records(recs: Iterable) -> List:
    return [r for r in (recs or []) if is_evidence_record(r)]


def lore_is_evidence(lf) -> bool:
    """``poi['_lore']`` entries. A page fact carries a source URL (thin-search ``_thin_search``); a bare
    ``{fact, confidence}`` from the knowledge fallback is the model's memory. Entries from other
    producers (venue-part chain facts) are kept unless marked or registered as LLM text."""
    if isinstance(lf, dict):
        if lf.get("llm") or is_llm_source(lf.get("source")):
            return False
        if _registered(str(lf.get("fact") or lf.get("text") or "")):
            return False
        has_src = (lf.get("_thin_search") or _has_url(lf.get("source")) or _has_url(lf.get("url"))
                   or _has_url(lf.get("link")))
        if "confidence" in lf and not has_src:
            return False                      # fetch_stop_knowledge fact: {fact, confidence}
        return True
    return isinstance(lf, str) and not _registered(lf)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip())


def _registered(text: str) -> bool:
    n = _norm(text)
    if not n:
        return False
    with _lock:
        if n in _REGISTRY:
            return True
        return any(r and r in n and len(r) >= 40 and len(n) <= len(r) + 80 for r in _REGISTRY)


def register(texts: Iterable[str], stop: str = "") -> int:
    """Remember LLM-generated passages (and their title-glued form) so ``scrub`` can remove them."""
    n = 0
    with _lock:
        for t in texts or []:
            t = _norm(t)
            if len(t) < 12:
                continue
            _REGISTRY.add(t)
            n += 1
            if stop:
                _REGISTRY.add(_norm(f"{stop} {t}"))
    return n


def registry_size() -> int:
    with _lock:
        return len(_REGISTRY)


def clear_registry() -> None:          # tests only
    with _lock:
        _REGISTRY.clear()


def scrub(evidence: str, extra: Iterable[str] = ()) -> str:
    """Remove every registered (or ``extra``) LLM passage from an evidence blob."""
    ev = evidence or ""
    if not ev:
        return ev
    with _lock:
        items = sorted(_REGISTRY | {_norm(x) for x in (extra or []) if x}, key=len, reverse=True)
    out = ev
    for t in items:
        if len(t) >= 12 and t in out:
            out = out.replace(t, " ")
    return re.sub(r"[ \t]{2,}", " ", out) if out != ev else ev


def scrub_map(evidence_by_title: Dict[str, str]) -> Dict[str, str]:
    return {k: scrub(v) for k, v in (evidence_by_title or {}).items()}


def split_cache_marked(passages: Iterable[str]):
    """(evidence_passages, llm_passages) from a cache row; marked passages are LLM-extracted."""
    ev, llm = [], []
    for p in passages or []:
        if isinstance(p, str) and p.startswith(LLM_CACHE_MARK):
            llm.append(p[len(LLM_CACHE_MARK):])
        else:
            ev.append(p)
    return ev, llm
