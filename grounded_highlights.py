"""grounded_highlights.py — LOCAL-669.

A thin-Wikidata museum (fewer catalogued works than the visitor asked stops for)
used to be filled, under LOCAL-667, by proposing R4 candidates and then spending
ONE grounded/Serper VERIFICATION QUERY PER TITLE to reach the two-source bar — up
to ~10 paid queries a tour. Michael's observation (2026-10-10): asking a grounded
model ONE question — *"please describe at least 5 paintings from the Ho Chi Minh
City Museum of Fine Arts"* — already returns exactly what a listener wants (named
works, artist, year, medium, a fact), at the price of ONE grounded request.

This module makes that the candidate source for thin museums:

  1. ONE grounded "highlights" call (the active research backend — Gemini grounded
     or, under RESEARCH_BACKEND=serper, Serper + gpt-4.1-mini): "List the 8 most
     notable works in the PERMANENT collection of <museum>, <city>: title (local
     and English), artist, year, medium, one fact. Cite sources." Its answer is
     parsed into up to 8 candidate works.

  2. VERIFICATION FROM THE CITATIONS the same call returned. A candidate is
     verified when EITHER
       * ≥1 cited source on the museum's OWN domain names it, OR
       * ≥2 INDEPENDENT cited sources (distinct domains) name it at this museum.
     Otherwise, at most ONE Serper query per still-unverified candidate
     (`"<title>" "<artist>" "<museum>"`) may supply the second independent source.
     An UNCITED candidate is NEVER accepted — items 3–5 in Michael's list must be
     proven, not assumed.

  3. COST: ≤ 1 grounded request + ≤ 8 Serper queries per tour, and the result is
     cached per venue for 30 days (thin_verify_cache). This REPLACES LOCAL-667's
     per-title thin-verify searches where it applies. The run logs
     `[LOCAL-669] highlights: N candidates, M verified, cost …`.

HONESTY: nothing is invented here. A work ships only when the grounded call's own
citations (optionally topped up by one Serper query) place it at THIS museum by
the rule above. The grounded model naming a work with NO usable citation does not
make it a stop.

The two side-effecting inputs — the grounded research callable and the Serper
callable — are parameters, so the whole module is unit-tested offline with stubs
(tests/… / test_local669_grounded_highlights.py). ``title_in_text`` and the
independent-source accounting are reused verbatim from thin_wikidata_fallback so
LOCAL-669 and LOCAL-667 judge "names this work" and "independent source"
identically.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# Reuse LOCAL-667's title-matching and source primitives so both paths agree on
# what "a source names this work" and "an independent source" mean.
from thin_wikidata_fallback import (
    MIN_INDEPENDENT_SOURCES,
    SourceHit,
    title_in_text,
)

# Default count of works to request / parse. Michael asked for "at least 5"; the
# ticket asks for the 8 most notable, giving headroom so 5 survive verification.
DEFAULT_HIGHLIGHTS = 8
# Per-tour Serper second-source cap (ticket: ≤ 8 Serper queries per tour).
MAX_SECOND_SOURCE_QUERIES = 8


def _norm(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return " ".join(stripped.split())


def _domain(url_or_domain: str) -> str:
    """Registrable-ish domain: strip scheme/www, lowercase, drop path/query."""
    d = (url_or_domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split("?")[0]
    return d


def _same_domain(a: str, b: str) -> bool:
    """True when domain `a` equals `b` or is a subdomain of it (either way)."""
    a, b = _domain(a), _domain(b)
    if not a or not b:
        return False
    return a == b or a.endswith("." + b) or b.endswith("." + a)


# ── 1. the ONE grounded highlights prompt ─────────────────────────────────────

def build_highlights_prompt(venue: str, city: str = "",
                            n: int = DEFAULT_HIGHLIGHTS) -> str:
    """The single grounded request. Asks for the N most notable PERMANENT-
    collection works with the fields a listener wants, and — crucially — for
    sources, because the citations are what we verify against."""
    loc = f"{venue}, {city}" if city else venue
    return (
        f"Using Google Search, list the {n} most notable works in the PERMANENT "
        f"collection of {loc}. For EACH work give, on its own numbered line: the "
        f"title (local language and English if different), the artist, the year, "
        f"the medium, and ONE interesting fact. Only include works actually held "
        f"at THIS museum — if you are not sure a work is in this collection, leave "
        f"it out rather than guess. Cite the sources that place each work at this "
        f"museum."
    )


# ── parsing the grounded answer into candidates ───────────────────────────────

# A numbered or bulleted list line begins a new work. We split the answer into
# per-work blocks on these markers, then pull labelled or positional fields.
_ITEM_SPLIT = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*•])\s+")
_YEAR = re.compile(r"\b(1[0-9]\d{2}|20[0-3]\d)\b")

# Common "Title — Artist — medium, year" / "Title by Artist (year)" shapes, plus
# explicit "Artist:" / "Year:" / "Medium:" labels when the model uses them.
_LABEL_ARTIST = re.compile(r"(?i)\bartist\s*:\s*([^\n;|]+)")
_LABEL_YEAR = re.compile(r"(?i)\byear\s*:\s*([^\n;|]+)")
_LABEL_MEDIUM = re.compile(r"(?i)\bmedium\s*:\s*([^\n;|]+)")
_LABEL_TITLE = re.compile(r"(?i)\btitle\s*:\s*([^\n;|]+)")

# Dash variants used as field separators.
_DASHES = "—–‑-"


def _split_fields(line: str) -> List[str]:
    """Split an item line into fields on dash separators that are SURROUNDED BY
    WHITESPACE (field separators), so an intra-word hyphen like 'Y-shaped' is not
    a boundary. Em/en dashes separate even without spaces; a bare ASCII hyphen
    only separates when spaced."""
    # Normalise spaced em/en/hyphen separators to a sentinel, then split.
    s = re.sub(r"\s+[—–‑-]\s+", "\u0001", line)
    s = re.sub(r"[—–]", "\u0001", s)  # unspaced em/en dash still separates
    return [p.strip() for p in s.split("\u0001") if p.strip()]


def _first_segment(line: str) -> str:
    """The title segment of an item line: text up to the first field separator
    (spaced dash / em-dash / ' by ' / '(' / ':'), with any 'Title:' label
    removed. Intra-word hyphens are preserved ('Y-shaped Bridge Battlefield')."""
    s = line.strip()
    m = _LABEL_TITLE.search(s)
    if m:
        return _clean_title(m.group(1))
    # First field separator wins among: spaced/em dash, ' by ', '(', ':'.
    head = _split_fields(s)[0] if _split_fields(s) else s
    for sep in (r"\bby\b", r"\(", r":"):
        parts = re.split(sep, head, maxsplit=1)
        if len(parts) == 2 and parts[0].strip():
            head = parts[0]
            break
    return _clean_title(head)


def _clean_title(t: str) -> str:
    t = (t or "").strip().strip("*_\"'“”‘’ ")
    # Drop a leading enumerator the split may have left (defensive).
    t = re.sub(r"^\s*\d+[.)]\s*", "", t)
    # A parenthetical English gloss stays as-is in the stored title; callers that
    # want the bare title use title_in_text which is gloss-tolerant.
    return t.strip()


def _extract_artist(line: str) -> str:
    m = _LABEL_ARTIST.search(line)
    if m:
        return _clean_field(m.group(1))
    # "... by Nguyen Gia Tri ..." / "Title — Artist — ..."
    bym = re.search(r"(?i)\bby\s+([A-ZÀ-Ý][^\n;,|(]+)", line)
    if bym:
        return _clean_field(bym.group(1))
    segs = _split_fields(line)
    if len(segs) >= 2:
        # Second field-segment is usually the artist in "Title — Artist — medium".
        cand = segs[1]
        if not _YEAR.search(cand) and len(cand.split()) <= 5:
            return _clean_field(cand)
    return ""


def _extract_year(line: str) -> str:
    m = _LABEL_YEAR.search(line)
    if m and _YEAR.search(m.group(1)):
        return _YEAR.search(m.group(1)).group(1)
    ym = _YEAR.search(line)
    return ym.group(1) if ym else ""


def _extract_medium(line: str) -> str:
    m = _LABEL_MEDIUM.search(line)
    if m:
        return _clean_field(m.group(1))
    # Heuristic: a dash-segment that names a known medium word.
    low = line.lower()
    for kw in ("lacquer", "oil on canvas", "oil", "silk", "woodblock",
               "woodcut", "bronze", "ceramic", "watercolor", "watercolour",
               "ink", "gouache", "sculpture", "tempera", "acrylic"):
        if kw in low:
            return kw
    return ""


def _clean_field(v: str) -> str:
    return (v or "").strip().strip("*_\"'“”‘’.,; ").strip()


def parse_highlights(grounded_result: Dict, max_items: int = DEFAULT_HIGHLIGHTS
                     ) -> List[Dict]:
    """Parse the grounded answer text into candidate works.

    Returns up to ``max_items`` dicts {name, artist, year, medium, fact,
    _raw_line}. Deterministic; no network. An answer with no parseable item lines
    yields []. Never fabricates — a field absent from the text is "".
    """
    if not grounded_result or grounded_result.get("error"):
        return []
    text = grounded_result.get("text", "") or ""
    if not text.strip():
        return []

    # Split into per-item blocks on numbered/bulleted markers. The first chunk
    # before the first marker is preamble and dropped.
    chunks = _ITEM_SPLIT.split(text)
    items = chunks[1:] if len(chunks) > 1 else []
    if not items:
        # No list markers — fall back to non-empty lines that look like entries.
        items = [ln for ln in text.splitlines() if ln.strip()]

    out: List[Dict] = []
    seen = set()
    for raw in items:
        line = " ".join(raw.strip().splitlines()).strip()
        if not line:
            continue
        title = _first_segment(line)
        if not title or len(_norm(title)) < 2:
            continue
        nkey = _norm(title)
        if nkey in seen:
            continue
        seen.add(nkey)
        out.append({
            "name": title,
            "artist": _extract_artist(line),
            "year": _extract_year(line),
            "medium": _extract_medium(line),
            "fact": "",
            "_raw_line": line,
        })
        if len(out) >= max_items:
            break
    return out


# ── 2. verification from the citations ────────────────────────────────────────

@dataclass
class HighlightVerdict:
    name: str
    verified: bool
    sources: List[SourceHit] = field(default_factory=list)
    second_source_query_used: bool = False

    @property
    def source_count(self) -> int:
        return len({s.origin for s in self.sources})

    @property
    def own_domain(self) -> bool:
        return any(s.detail == "own_domain" or s.origin == "__own__"
                   for s in self.sources)


def _cited_sources_for_title(title: str, grounded_result: Dict,
                             own_domains: Sequence[str]
                             ) -> Tuple[List[SourceHit], bool]:
    """Independent CITED sources (distinct domains) from the grounded result that
    name `title`, plus a flag for whether any is on the museum's own domain.

    Prefers per-sentence `supports` attribution (a domain counts only when it
    backs a sentence that actually names the work); falls back to the whole-answer
    text + its source list when there is no support-level attribution — mirroring
    thin_wikidata_fallback.grounded_hits_for_title, but tracking own-domain.
    """
    hits: Dict[str, SourceHit] = {}
    own = False

    def _add(src: Dict):
        nonlocal own
        dom = _domain(src.get("domain") or src.get("url") or "")
        if not dom:
            return
        is_own = any(_same_domain(dom, od) for od in own_domains if od)
        if is_own:
            own = True
        if dom not in hits:
            hits[dom] = SourceHit(origin=dom,
                                  detail="own_domain" if is_own else src.get("url", ""))

    # Per-sentence attribution is the honest signal: a source counts for THIS
    # work only when it backs a sentence that names it. We credit those first.
    supports = (grounded_result or {}).get("supports", []) or []
    for sup in supports:
        seg = sup.get("text", "") or ""
        if not title_in_text(title, seg):
            continue
        for src in sup.get("sources", []) or []:
            _add(src)

    # Whole-answer fallback — ONLY when the result carries NO per-sentence
    # attribution AT ALL (e.g. an older flat {text, sources} response). If the
    # result HAS supports but none names this work, the work is UNCITED and gets
    # no sources here: that is the items-3–5 guard (a work the model listed but
    # did not attribute is never silently credited with the global source list).
    any_support_sources = any(sup.get("sources") for sup in supports)
    if not any_support_sources and title_in_text(title, (grounded_result or {}).get("text", "")):
        for src in (grounded_result or {}).get("sources", []) or []:
            _add(src)

    return list(hits.values()), own


def _is_verified(sources: Sequence[SourceHit], own_domain: bool,
                 min_sources: int = MIN_INDEPENDENT_SOURCES) -> bool:
    """The LOCAL-669 rule: ≥1 own-domain cited source, OR ≥ min_sources distinct
    independent cited domains."""
    if own_domain:
        return True
    return len({s.origin for s in sources}) >= min_sources


def _second_source_query(title: str, artist: str, venue: str) -> str:
    """The single Serper query that may supply a second independent source."""
    parts = [f'"{title}"']
    if artist:
        parts.append(f'"{artist}"')
    if venue:
        parts.append(f'"{venue}"')
    return " ".join(parts)


def verify_highlights(
    candidates: Sequence[Dict],
    grounded_result: Dict,
    venue_name: str,
    *,
    own_domains: Sequence[str] = (),
    serper_fn: Optional[Callable[[str], List[Dict]]] = None,
    max_second_source_queries: int = MAX_SECOND_SOURCE_QUERIES,
    min_sources: int = MIN_INDEPENDENT_SOURCES,
) -> Tuple[List[Dict], List[HighlightVerdict], int]:
    """Verify highlight candidates against the grounded call's OWN citations, with
    at most one Serper query per still-unverified candidate for a 2nd source.

    Args:
        candidates: parsed works (dicts with 'name'; optional 'artist').
        grounded_result: the {text, sources, supports, …} shape the ONE grounded
            call returned (its citations are the primary evidence).
        venue_name: the museum (used in the Serper 2nd-source query).
        own_domains: the museum's own domain(s) — a single cited source here
            verifies a work. Empty is allowed (then only the 2-independent rule).
        serper_fn: callable(query)->[{url/link, …}] for the 2nd-source top-up.
            When None, no top-up is done (citations-only verification). The caller
            passes a metered Serper callable; tests pass a stub.
        max_second_source_queries: per-tour cap on Serper 2nd-source queries
            (ticket: ≤ 8).
        min_sources: independent sources required when there is no own-domain hit.

    Returns (verified_works, verdicts, serper_queries_used). verified_works are
    dict copies with verified=True and a 'highlight_sources' list. verdicts covers
    EVERY candidate. Never accepts an uncited candidate.
    """
    verdicts: List[HighlightVerdict] = []
    verified: List[Dict] = []
    serper_used = 0
    seen = set()

    for cand in candidates:
        name = (cand.get("name") or "").strip()
        if not name:
            continue
        nkey = _norm(name)
        if not nkey or nkey in seen:
            continue
        seen.add(nkey)

        sources, own = _cited_sources_for_title(name, grounded_result, own_domains)
        second_used = False

        # UNCITED candidate: the grounded model named it but gave no usable
        # citation that names it. Never accepted; no Serper rescue (there is no
        # first source to be independent OF). This is the items 3–5 guard.
        has_any_citation = len(sources) > 0

        if (has_any_citation and not _is_verified(sources, own, min_sources)
                and serper_fn is not None and serper_used < max_second_source_queries):
            # Exactly ONE Serper query to look for a 2nd independent domain.
            serper_used += 1
            second_used = True
            q = _second_source_query(name, (cand.get("artist") or "").strip(), venue_name)
            try:
                results = serper_fn(q) or []
            except Exception:
                results = []
            existing = {s.origin for s in sources}
            for r in results:
                dom = _domain(r.get("url") or r.get("link") or "")
                if not dom or dom in existing:
                    continue
                # A Serper result counts as a 2nd source only when its snippet/
                # title actually names the work (honesty: a bare URL is not proof).
                blob = f"{r.get('title','')} {r.get('snippet','')}"
                if not title_in_text(name, blob):
                    continue
                existing.add(dom)
                is_own = any(_same_domain(dom, od) for od in own_domains if od)
                if is_own:
                    own = True
                sources.append(SourceHit(
                    origin=dom, detail="own_domain" if is_own else r.get("url", "")))

        ok = has_any_citation and _is_verified(sources, own, min_sources)
        verdicts.append(HighlightVerdict(
            name=name, verified=ok, sources=sources,
            second_source_query_used=second_used))
        if ok:
            p = dict(cand)
            p["name"] = name
            p["verified"] = True
            p["highlight_sources"] = [{"origin": s.origin, "detail": s.detail}
                                      for s in sources]
            p.pop("_raw_line", None)
            verified.append(p)

    return verified, verdicts, serper_used


# ── 3. orchestration: one grounded call → parse → verify → log ────────────────

@dataclass
class HighlightsResult:
    verified_works: List[Dict]
    verdicts: List[HighlightVerdict]
    grounded_requests: int          # 0 or 1
    serper_queries: int             # 0 … ≤ MAX_SECOND_SOURCE_QUERIES
    log_line: str
    error: str = ""


def grounded_highlights(
    venue_name: str,
    city: str = "",
    *,
    research_fn: Optional[Callable[[str], Dict]] = None,
    serper_fn: Optional[Callable[[str], List[Dict]]] = None,
    own_domains: Sequence[str] = (),
    n: int = DEFAULT_HIGHLIGHTS,
    max_second_source_queries: int = MAX_SECOND_SOURCE_QUERIES,
    min_sources: int = MIN_INDEPENDENT_SOURCES,
) -> HighlightsResult:
    """Run the LOCAL-669 flow: ONE grounded highlights call, parse ≤ n candidates,
    verify from the citations (own-domain-1 OR 2-independent, else one Serper 2nd
    source per candidate), and return the verified works plus a cost/verdict log.

    ``research_fn(prompt)->grounded_result`` is the ONE grounded request (the
    active backend). When None, there is no candidate source and the result is
    empty (the caller then keeps LOCAL-667/668 fallbacks). Pure given the two
    injected callables; tests supply stubs so no network is touched.
    """
    if research_fn is None:
        return HighlightsResult([], [], 0, 0,
                                "[LOCAL-669] highlights: no research backend; skipped")

    prompt = build_highlights_prompt(venue_name, city, n=n)
    try:
        gres = research_fn(prompt) or {}
    except Exception as e:
        return HighlightsResult([], [], 1, 0,
                                f"[LOCAL-669] highlights: grounded call failed ({e})",
                                error=str(e))

    grounded_requests = 1
    if gres.get("error"):
        return HighlightsResult(
            [], [], grounded_requests, 0,
            f"[LOCAL-669] highlights: grounded call error ({gres.get('error')})",
            error=str(gres.get("error")))

    candidates = parse_highlights(gres, max_items=n)
    verified, verdicts, serper_used = verify_highlights(
        candidates, gres, venue_name,
        own_domains=own_domains, serper_fn=serper_fn,
        max_second_source_queries=max_second_source_queries,
        min_sources=min_sources)

    log_line = (
        f"[LOCAL-669] highlights: {len(candidates)} candidates, "
        f"{len(verified)} verified, cost {grounded_requests} grounded request + "
        f"{serper_used} Serper queries")
    return HighlightsResult(verified, verdicts, grounded_requests, serper_used,
                            log_line)
