#!/usr/bin/env python3
"""museum_overview.py — LOCAL-582: a sourced museum OVERVIEW when works can't be verified.

THE LADDER (LEAD, D607). When a tour request names a museum:
  1. Works / current exhibitions verified              → full tour (LOCAL-580).
  2. Exhibitions named but thin                         → same stops, hedged (D592).
  3. Nothing verifiable about what is on display, BUT   → a MUSEUM OVERVIEW  ← THIS.
     the venue resolved and its own site is reachable
  4. No usable site                                     → LOCAL-580 error + suggestion.

Rung 3 used to be a clean fail ("we could not find enough verified material").
Michael, 2026-10-05: "griffinmuseum.org tells us when it opens, what exhibitions
are there, and the price of entry. Maybe if there is no information at all we
should still generate a summary with the information available on the museum
link."

So this module builds ONE narrated stop at the venue's own location, 150–300
words, from the venue's OWN pages only (home, visit/hours/admission, current
exhibitions):
  * what the place is,
  * what is on now (exhibition NAMES only when that is all we have),
  * when it is open and what entry costs — ONLY WITH A SOURCE, and dated
    ("as listed on griffinmuseum.org, October 2026"),
  * where it is.

HOURS AND ADMISSION ONLY WITH A SOURCE (the D538 rule reused). A practical fact
is stated only if a snippet on the venue's OWN domain supports it, verified
through the existing machinery:
    visitor_facts_extractor.fetch_visitor_info_with_provenance  (LOCAL-35/39)
    practical_facts_gate.verify_claim_against_source            (LOCAL-36)
If a fact is missing, it is OMITTED. Nothing is estimated. This is the same
contract restaurant_practicals.py (D538) honours for dining practicals.

The module is deliberately dependency-light and testable offline: every network
touch goes through an injectable ``fetcher`` (and an injectable ``visitor_info``
provider), so the whole overview can be built from fixtures with no HTTP.

Returned object (``MuseumOverview``):
    narration      : str   the 150–300 word spoken overview (one stop)
    sources        : list  the on-domain URLs the facts came from (deduped)
    has_hours      : bool  True iff sourced hours made it into the narration
    has_admission  : bool  True iff sourced admission made it into the narration
    exhibitions    : list  exhibition names surfaced (may be empty)
    as_of          : str   the human month-year stamp used in the dateline
    facts_line     : str   the sourced-and-dated practical sentence ('' if none)
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

__all__ = ['MuseumOverview', 'build_museum_overview']


# A fetcher returns (html, links) for a URL. links are unused here but match the
# exhibition_site_first fetcher contract so the same fake can drive both.
Fetcher = Callable[[str], Tuple[str, List[Tuple[str, str]]]]


@dataclass
class MuseumOverview:
    narration: str = ''
    sources: List[str] = field(default_factory=list)
    has_hours: bool = False
    has_admission: bool = False
    exhibitions: List[str] = field(default_factory=list)
    as_of: str = ''
    facts_line: str = ''

    def is_empty(self) -> bool:
        return not self.narration.strip()


_TAG_RE = re.compile(r'<[^>]+>')
_SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b.*?</\1>', re.DOTALL | re.IGNORECASE)

# Pages on the venue's own domain that describe the place itself. Ordered so the
# highest-value pages (current exhibitions = "what is on now", visit = hours/
# admission, about = "what the place is") are reached within max_pages even on a
# site that puts everything behind trailing-slash variants.
_OVERVIEW_SEEDS = [
    '/current-exhibitions', '/current-exhibitions/', '/exhibitions',
    '/visit', '/plan-your-visit', '/hours-admission', '/hours-and-admission',
    '/hours', '/about', '/about-us',
]


def _visible_text(html: str) -> str:
    """Strip HTML to visible text (bs4 if available, else regex)."""
    if not html:
        return ''
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for t in soup(['script', 'style']):
            t.decompose()
        return re.sub(r'\s+\n', '\n', soup.get_text('\n', strip=True))
    except Exception:
        stripped = _SCRIPT_STYLE_RE.sub(' ', html)
        return re.sub(r'\s+', ' ', _TAG_RE.sub(' ', stripped)).strip()


def _domain_of(url: str) -> str:
    """Return a bare human domain ('griffinmuseum.org') for the dateline/source tag."""
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith('www.') else netloc


def _default_fetcher(url: str) -> Tuple[str, List[Tuple[str, str]]]:
    import requests
    try:
        resp = requests.get(url, headers={'User-Agent': 'Audioura/2.4 (+overview)'},
                            timeout=15, allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            return resp.text, []
    except Exception:
        pass
    return '', []


def _candidate_overview_urls(base_site_url: str) -> List[str]:
    """Ordered, de-duplicated venue-own-domain pages to read for the overview."""
    if '://' not in base_site_url:
        base_site_url = 'https://' + base_site_url
    parsed = urlparse(base_site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    urls: List[str] = []
    seen = set()
    # The resolved page itself first (small venues embed everything on one page),
    # then the generic about/visit/exhibition seeds under the same root.
    for u in [base_site_url.rstrip('/') or root] + [root + s for s in _OVERVIEW_SEEDS]:
        u = u or root
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _describe_place(venue_name: str, corpus_text: str) -> str:
    """One clause saying WHAT the place is, taken only from the venue's own words.

    We do not invent a mission statement. If the site's text contains a short
    self-description sentence that names the venue, we lift the opening of it;
    otherwise we fall back to the neutral, always-true phrasing built from the
    venue's own name (a museum IS a museum — that is not a fabricated claim).
    """
    if corpus_text:
        # First sentence that mentions the venue (or a leading noun phrase about it).
        _vn_core = re.sub(r',.*$', '', venue_name).strip()
        _vn_first = _vn_core.split()[0] if _vn_core else ''
        # Split on sentence boundaries AND newlines, so a heading with no final
        # period (e.g. an <h1>) does not glue itself onto the first real sentence.
        for sent in re.split(r'(?<=[.!?])\s+|\n+', corpus_text):
            s = sent.strip()
            # A real self-description is a full sentence that ends in punctuation;
            # a bare heading ("Griffin Museum of Photography") is skipped.
            if not s.endswith(('.', '!', '?')):
                continue
            if 40 <= len(s) <= 240 and _vn_first and _vn_first.lower() in s.lower():
                # Avoid nav/booking cruft.
                if not re.search(r'(?i)\b(cookie|menu|donate|subscribe|newsletter|'
                                 r'copyright|all rights reserved)\b', s):
                    return s.rstrip('.') + '.'
    return ''


def _collect_exhibitions(pages: List[Tuple[str, str]]) -> List[str]:
    """Structural exhibition NAMES from any fetched page (reuses LOCAL-580 D1).

    Returns the show titles in site order, deduped, or [] if none are published.
    Names only — this rung exists precisely because the works cannot be verified.
    """
    try:
        from exhibition_discovery import extract_current_exhibitions
    except Exception:
        return []
    names: List[str] = []
    seen = set()
    for html, url in pages:
        if not html:
            continue
        try:
            for ex in extract_current_exhibitions(html, url):
                t = (ex.get('title') or '').strip()
                k = t.lower()
                if t and k not in seen:
                    seen.add(k)
                    names.append(t)
        except Exception:
            continue
    return names


def _verified_facts_line(visitor_info, as_of: str, domain: str) -> Tuple[str, bool, bool, str]:
    """Build a sourced, dated practical sentence — hours/admission ONLY with a source.

    ``visitor_info`` is a VisitorInfoWithProvenance (LOCAL-39): it carries the
    structured facts AND the raw source text they were extracted from. Each
    practical claim is RE-VERIFIED against that source text through
    practical_facts_gate.verify_claim_against_source (the D538 contract). Any
    claim that cannot be traced to the source is DROPPED — never estimated.

    Returns (sentence, has_hours, has_admission, source_url). sentence == '' when
    nothing survives verification.
    """
    if visitor_info is None:
        return '', False, False, ''
    formatted = getattr(visitor_info, 'formatted_info', '') or ''
    source_text = getattr(visitor_info, 'source_text', '') or ''
    source_url = getattr(visitor_info, 'source_url', '') or ''
    if not formatted or not source_text:
        return '', False, False, source_url

    try:
        from practical_facts_gate import (_parse_info_text_into_claims,
                                          verify_claim_against_source)
    except Exception:
        # Without the gate we cannot verify — so we must NOT state anything.
        return '', False, False, source_url

    verified_hours: List[str] = []
    verified_admission: List[str] = []
    for claim in _parse_info_text_into_claims(formatted):
        if not verify_claim_against_source(claim, source_text):
            continue
        val = claim.value.strip().rstrip('.')
        if claim.claim_type in ('hours', 'closed_day'):
            verified_hours.append(val)
        elif claim.claim_type in ('admission', 'price_band'):
            verified_admission.append(val)

    has_hours = bool(verified_hours)
    has_admission = bool(verified_admission)
    if not has_hours and not has_admission:
        return '', False, False, source_url

    bits = verified_hours + verified_admission
    # One dated, attributed sentence — the dateline is the honesty signal.
    sentence = (f"As listed on {domain}, {as_of}, " + '; '.join(bits) + '.')
    return sentence, has_hours, has_admission, source_url


def _default_as_of() -> str:
    now = datetime.date.today()
    return now.strftime('%B %Y')


def _compose_narration(
    venue_name: str,
    locality: str,
    place_sentence: str,
    exhibitions: List[str],
    facts_line: str,
    domain: str,
    as_of: str,
) -> str:
    """Deterministic composer for the one overview stop (no LLM needed).

    The orientation is HONEST about why this is an overview: the venue's current
    displays could not be independently verified, so the overview is drawn from
    the venue's own published pages. 150–300 words, trimmed to the band.
    """
    _vn = re.sub(r',.*$', '', venue_name).strip() or venue_name
    where = f" in {locality}" if locality else ""

    sentences: List[str] = []
    # Honest orientation (this is WHY it is an overview, not a full tour).
    sentences.append(
        f"Welcome to {_vn}{where}. This is a short overview, not a full tour: we "
        f"could not independently verify the specific works on display right now, "
        f"so it is drawn entirely from the museum's own pages on {domain}, as "
        f"published in {as_of}.")
    if place_sentence:
        sentences.append(place_sentence)
    # What is on now — names only.
    if exhibitions:
        if len(exhibitions) == 1:
            sentences.append(f"The museum is currently presenting {exhibitions[0]}.")
        else:
            _shown = exhibitions[:6]
            _listed = '; '.join(_shown[:-1]) + f"; and {_shown[-1]}"
            sentences.append(
                f"According to the museum's current-exhibitions page, the shows on "
                f"view are {_listed}. We are naming them here rather than describing "
                f"their contents, because the museum's pages did not give us enough "
                f"to narrate each one responsibly.")
    else:
        sentences.append(
            "The museum's pages did not list the current shows in a form we could "
            "read, so we are not naming individual exhibitions here.")
    # Practical facts — ONLY when sourced and dated.
    if facts_line:
        sentences.append(facts_line)
    else:
        sentences.append(
            "We did not find opening hours or admission prices on the museum's own "
            "pages that we could confirm, so we are not stating any — please check "
            f"{domain} before you visit.")
    # Where / close.
    if locality:
        sentences.append(
            f"When you are ready, {_vn} is the place to see this work in person, "
            f"here in {locality}.")
    else:
        sentences.append(f"When you are ready, step inside {_vn} to see the work in person.")

    text = ' '.join(s.strip() for s in sentences if s and s.strip())
    return _trim_to_word_band(text, lo=150, hi=300)


def _trim_to_word_band(text: str, lo: int = 150, hi: int = 300) -> str:
    """Keep the overview within [lo, hi] words. Trim on a sentence boundary when over."""
    words = text.split()
    if len(words) <= hi:
        return text
    # Trim to <= hi words, then back up to the last sentence end for clean audio.
    clipped = ' '.join(words[:hi])
    m = list(re.finditer(r'[.!?]', clipped))
    if m:
        return clipped[:m[-1].end()]
    return clipped


def build_museum_overview(
    venue_name: str,
    base_site_url: str,
    locality: str = '',
    venue_language: str = 'en',
    as_of: Optional[str] = None,
    fetcher: Optional[Fetcher] = None,
    visitor_info_provider: Optional[Callable[[str, str], object]] = None,
    composer: Optional[Callable[..., str]] = None,
    max_pages: int = 8,
) -> Optional[MuseumOverview]:
    """Build a sourced museum overview (rung 3) from the venue's OWN site.

    Args:
        venue_name: the resolved venue name (e.g. "Griffin Museum of Photography").
        base_site_url: the venue's official URL (REQUIRED — no URL ⇒ rung 4, return None).
        locality: city/region tail for "where it is" (e.g. "Winchester, MA").
        venue_language: 'en'/'fr'/… passed through to the visitor-facts extractor.
        as_of: human month-year stamp for the dateline; defaults to the current month.
        fetcher: injectable (html, links) fetcher for the venue pages (fixtures in tests).
        visitor_info_provider: injectable (base_url, language) → VisitorInfoWithProvenance;
            defaults to visitor_facts_extractor.fetch_visitor_info_with_provenance.
        composer: injectable narration composer; defaults to the deterministic one.
        max_pages: cap on venue pages fetched for the place description/exhibitions.

    Returns:
        MuseumOverview, or None when there is no usable site (rung 4 — the caller
        then falls back to the LOCAL-580 structured error + suggestion). Returning
        None is the ONLY failure mode; a reachable site always yields an overview,
        even one that states no hours/price (those require a source).
    """
    if not base_site_url or not base_site_url.strip():
        # No usable site → rung 4. Never fabricate a venue page.
        return None

    as_of = as_of or _default_as_of()
    domain = _domain_of(base_site_url)
    fetch = fetcher or _default_fetcher

    # 1. Read the venue's own pages (home / about / visit / exhibitions).
    fetched: List[Tuple[str, str]] = []   # (html, url)
    tried = 0
    for url in _candidate_overview_urls(base_site_url):
        if tried >= max_pages:
            break
        tried += 1
        html, _links = fetch(url)
        if html and len(html) >= 80:
            fetched.append((html, url))

    if not fetched:
        # Site named but nothing reachable → treat as no usable site (rung 4).
        return None

    corpus_text = '\n\n'.join(_visible_text(h) for h, _ in fetched)

    # 2. What is on now — exhibition NAMES only (reuses LOCAL-580 structural D1).
    exhibitions = _collect_exhibitions(fetched)

    # 3. Sourced, dated practical facts — hours/admission ONLY with a source.
    provider = visitor_info_provider
    if provider is None:
        try:
            from visitor_facts_extractor import fetch_visitor_info_with_provenance
            provider = fetch_visitor_info_with_provenance
        except Exception:
            provider = None
    visitor_info = None
    if provider is not None:
        try:
            visitor_info = provider(base_site_url, venue_language)
        except Exception:
            visitor_info = None

    facts_line, has_hours, has_admission, facts_source = _verified_facts_line(
        visitor_info, as_of, domain)

    # 4. What the place is — from its own words.
    place_sentence = _describe_place(venue_name, corpus_text)

    # 5. Compose the single overview stop.
    compose = composer or _compose_narration
    narration = compose(
        venue_name=venue_name,
        locality=locality,
        place_sentence=place_sentence,
        exhibitions=exhibitions,
        facts_line=facts_line,
        domain=domain,
        as_of=as_of,
    )

    # Sources: the pages we actually used, venue-domain only, deduped in order.
    # Dedupe by normalized URL (ignore a trailing slash) so '/x' and '/x/' — which
    # a server usually serves identically — do not both appear.
    sources: List[str] = []
    _seen_norm = set()

    def _add_source(u: str):
        if not u or _domain_of(u) != domain:
            return
        norm = u.rstrip('/')
        if norm in _seen_norm:
            return
        _seen_norm.add(norm)
        sources.append(u)

    for _, url in fetched:
        _add_source(url)
    _add_source(facts_source)
    sources = sources[:6]

    return MuseumOverview(
        narration=narration,
        sources=sources,
        has_hours=has_hours,
        has_admission=has_admission,
        exhibitions=exhibitions,
        as_of=as_of,
        facts_line=facts_line,
    )
