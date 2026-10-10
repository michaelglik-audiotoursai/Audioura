"""thin_wikidata_fallback.py — LOCAL-667.

A real museum with a THIN Wikidata catalogue (fewer documented works than the
visitor asked for stops) must not surrender at "1 of 5". Before giving up, this
module tries to VERIFY the works the model already proposed — the R4-dropped
candidates — against sources that Wikidata is not:

  (a) the museum's OWN site, in its local language and in English;
  (b) Wikipedia, local language and English, collection / notable-works sections;
  (c) a grounded search (the active research backend, story_leads.research_with_sources).

(a) and (b) are already fetched for the tour (story_miner's venue narrative
corpus — `combined_text` plus the per-page list), so verifying against them costs
NOTHING. (c) is the only paid step and is used only to reach the two-source bar
when the corpus alone names a work once.

THE HONESTY RULE (unchanged): a work is verified only when **two independent
sources** name it AT THIS MUSEUM. One mention is not enough; zero mentions never
becomes a stop. The module never invents a work — it only promotes works the
model proposed and the sources corroborate.

Independent source = a distinct origin among: the museum site, Wikipedia-EN,
Wikipedia-local, and each distinct web domain returned by the grounded search.
Two mentions on the same page/domain count once.

Pure logic is unit-tested (tests/test_local667_thin_museum.py); the only
side-effecting entry point, `verify_thin_candidates`, takes the grounded-search
callable as a parameter so tests inject a stub and run offline.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# A work must be named by at least this many INDEPENDENT sources to be verified.
MIN_INDEPENDENT_SOURCES = 2


def _norm(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return " ".join(stripped.split())


def _content_words(text: str) -> List[str]:
    _STOP = {"the", "of", "and", "a", "an", "to", "in", "on", "with", "for",
             "de", "la", "le", "les", "el", "il", "und", "der", "die", "das"}
    return [w for w in _norm(text).split() if len(w) >= 3 and w not in _STOP]


def title_in_text(title: str, text: str) -> bool:
    """True when `title` is named in `text` (accent/punct-insensitive).

    Matches either the full normalised title as a WHOLE-WORD span, OR — for a
    multi-word title — ALL of its content words present as whole words, so a
    local-language page that renders the title with different glue words still
    counts. Whole-word matching prevents a spurious hit of "Garden" inside
    "gardenia". A title whose only content word is one short word (< 4 letters)
    requires the full-title span, not the lone word, to avoid noise.
    """
    if not title or not text:
        return False
    nt = _norm(title)
    ntext = _norm(text)
    if not nt or not ntext:
        return False
    # Whole-word tokens of the text, for order-free content-word checks.
    tset = set(ntext.split())
    # (1) full normalised title as a contiguous whole-word span.
    _title_toks = nt.split()
    _text_toks = ntext.split()
    n, m = len(_text_toks), len(_title_toks)
    for i in range(0, n - m + 1):
        if _text_toks[i:i + m] == _title_toks:
            return True
    # (2) content-word coverage.
    cw = _content_words(title)
    if not cw:
        return False
    if len(cw) == 1:
        # A single content word: accept only if it is a distinctive word (>= 4
        # letters) and present as a whole word. Short lone words need the full
        # span (handled above).
        w = cw[0]
        return len(w) >= 4 and w in tset
    return all(w in tset for w in cw)


@dataclass
class SourceHit:
    """One source that names a work."""
    origin: str      # 'site', 'wikipedia_en', 'wikipedia_local', or a web domain
    detail: str = ""  # short human-readable note (url / snippet)


@dataclass
class ThinVerdict:
    name: str
    verified: bool
    sources: List[SourceHit] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len({s.origin for s in self.sources})


def _classify_page_origin(url: str, title: str, venue_language: str) -> str:
    """Map a fetched corpus page to an independent-source origin label."""
    u = (url or "").lower()
    t = (title or "").lower()
    if "wikipedia.org" in u or "wikipedia" in t:
        # Local-language wikipedia host looks like 'vi.wikipedia.org'.
        m = re.match(r"https?://([a-z-]+)\.wikipedia\.org", u)
        lang = m.group(1) if m else ""
        if lang and venue_language and lang == venue_language and lang != "en":
            return "wikipedia_local"
        if lang == "en":
            return "wikipedia_en"
        # Unknown wikipedia lang: treat local vs en by venue language.
        return "wikipedia_local" if (venue_language and venue_language != "en") else "wikipedia_en"
    return "site"


def corpus_hits_for_title(
    title: str,
    pages: Sequence[Dict],
    venue_language: str = "en",
) -> List[SourceHit]:
    """Independent corpus (site + Wikipedia EN/local) sources that name the title.

    Each distinct origin ('site', 'wikipedia_en', 'wikipedia_local') contributes
    at most one hit, so two mentions on the same page count once.
    """
    seen: Dict[str, SourceHit] = {}
    for pg in pages or []:
        if not isinstance(pg, dict):
            continue
        text = pg.get("text", "") or ""
        if not title_in_text(title, text):
            continue
        origin = _classify_page_origin(pg.get("url", ""), pg.get("title", ""),
                                       venue_language)
        if origin not in seen:
            seen[origin] = SourceHit(origin=origin, detail=pg.get("url", ""))
    return list(seen.values())


def grounded_hits_for_title(
    title: str,
    grounded_result: Dict,
) -> List[SourceHit]:
    """Independent web-domain sources (from a grounded-search result) that name
    the title. Uses the per-sentence `supports` attribution when present so a
    source only counts when it actually backs a sentence that names the work;
    otherwise falls back to the response text + its source list.

    grounded_result is the {text, sources, supports, queries, error} shape of
    story_leads.research_with_sources.
    """
    if not grounded_result or grounded_result.get("error"):
        return []
    hits: Dict[str, SourceHit] = {}

    # Preferred: a support segment that names the work, attributed to domains.
    for sup in grounded_result.get("supports", []) or []:
        seg = sup.get("text", "") or ""
        if not title_in_text(title, seg):
            continue
        for src in sup.get("sources", []) or []:
            dom = (src.get("domain") or src.get("url") or "").strip().lower()
            if dom and dom not in hits:
                hits[dom] = SourceHit(origin=dom, detail=src.get("url", ""))

    # Fallback: the answer text names the work → credit the listed sources (each
    # distinct domain once). Only used when support-level attribution found none,
    # so we never double-count.
    if not hits and title_in_text(title, grounded_result.get("text", "")):
        for src in grounded_result.get("sources", []) or []:
            dom = (src.get("domain") or src.get("url") or "").strip().lower()
            if dom and dom not in hits:
                hits[dom] = SourceHit(origin=dom, detail=src.get("url", ""))
    return list(hits.values())


def verify_thin_candidates(
    candidates: Sequence[Dict],
    pages: Sequence[Dict],
    venue_name: str,
    *,
    venue_language: str = "en",
    research_fn: Optional[Callable[[str], Dict]] = None,
    city: str = "",
    max_grounded: int = 6,
    min_sources: int = MIN_INDEPENDENT_SOURCES,
) -> Tuple[List[Dict], List[ThinVerdict]]:
    """Verify thin-museum candidates against site+Wikipedia and (optionally) a
    grounded search, with the two-independent-source rule.

    Args:
        candidates: proposed work POIs (dicts with 'name') — e.g. R4-dropped.
        pages: the venue corpus pages [{url,text,title}] (site + Wikipedia).
        venue_name / city / venue_language: for the grounded query.
        research_fn: callable(prompt)->grounded_result. When None, grounded search
            is skipped (corpus-only verification). Tests inject a stub.
        max_grounded: cap on grounded calls (cost control).
        min_sources: independent sources required (default 2).

    Returns (verified_pois, verdicts). verified_pois are dict copies of the input
    candidates that reached the source bar, with name preserved and
    verified=True + a 'thin_sources' list attached. verdicts covers EVERY
    candidate (verified or not) for logging and tests. Never invents a work.
    """
    verdicts: List[ThinVerdict] = []
    verified: List[Dict] = []
    _grounded_used = 0

    # De-dup candidate names (normalised) — the R4-dropped pool can repeat.
    _seen: set = set()
    for cand in candidates:
        name = (cand.get("name") or "").strip()
        if not name:
            continue
        nkey = _norm(name)
        if not nkey or nkey in _seen:
            continue
        _seen.add(nkey)

        sources: List[SourceHit] = list(
            corpus_hits_for_title(name, pages, venue_language))

        # If the corpus alone has not reached the bar, spend ONE grounded search
        # (within the cap) to look for independent web corroboration.
        if len({s.origin for s in sources}) < min_sources and research_fn is not None \
                and _grounded_used < max_grounded:
            _grounded_used += 1
            prompt = _grounded_prompt(name, venue_name, city)
            try:
                gres = research_fn(prompt)
            except Exception:
                gres = None
            for h in grounded_hits_for_title(name, gres or {}):
                if h.origin not in {s.origin for s in sources}:
                    sources.append(h)

        is_verified = len({s.origin for s in sources}) >= min_sources
        verdicts.append(ThinVerdict(name=name, verified=is_verified, sources=sources))
        if is_verified:
            p = dict(cand)
            p["name"] = name
            p["verified"] = True
            p["thin_sources"] = [{"origin": s.origin, "detail": s.detail} for s in sources]
            verified.append(p)

    return verified, verdicts


def _grounded_prompt(work: str, venue: str, city: str) -> str:
    _loc = f"{venue}, {city}" if city else venue
    return (
        f"Using Google Search, is there a work titled \"{work}\" in the permanent "
        f"collection of {_loc}? Answer only about THIS museum. If it is there, name "
        f"it and cite the sources that place it at this museum. If you are not sure "
        f"it is at this museum, say so — do not guess."
    )
