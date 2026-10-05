#!/usr/bin/env python3
"""exhibition_site_first.py — LOCAL-580 D2: site-first candidates for exhibition museums.

When Wikidata/SPARQL returns 0 catalogued works for a museum but the venue's own
site publishes current exhibitions, the tour's candidate stops must come from
those exhibitions — one stop per show — not from GPT's imagination.

This module ties the structural extractor (exhibition_discovery) to the venue's
site:
  1. discover the current-exhibitions listing page on the venue's domain,
  2. extract the shows structurally (headings linking to on-domain detail pages),
  3. fetch each show's own detail page for its description (artist, dates, works).

It returns a list of candidate dicts:
    {'name', 'detail_url', 'page_text', 'source': 'site_exhibition'}

The caller (generate_tour_text) turns these into POIs. GPT may later ORDER or
CHOOSE among them, but the names come only from the site — never invented.

Pure-ish: the only side effect is HTTP GETs, done through
exhibition_checklist._fetch_page (which caches and backs off politely). The
discovery/extraction logic is unit-testable by injecting a fake fetcher.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from exhibition_discovery import extract_current_exhibitions

__all__ = ['discover_site_exhibitions', 'build_site_first_candidates', 'SiteFirstResult']


class SiteFirstResult:
    """Minimal stand-in for ExhibitionChecklistResult.

    The exhibit-museum grounding path in generate_tour_text only reads
    ``.page_text`` off the exhibition result object. Site-first candidates carry
    their own per-show text; this carrier concatenates them so the grounding
    check (title_appears_in_page) can confirm every stop against the site text
    it was extracted from.
    """

    def __init__(self, page_text: str = ''):
        self.page_text = page_text or ''
        self.path = 'site_exhibition'
        self.exhibition_url = ''
        self.content_url = ''
        self.is_third_party = False
        self.is_from_archive = False
        self.works = []

    @property
    def has_works(self) -> bool:
        return False

# Listing-page paths to try, in addition to whatever the base page links to.
# Generic across venues; language-specific seeds are reused from
# exhibition_checklist when available.
_LISTING_SEEDS_EN = [
    '/current-exhibitions', '/current-exhibitions/',
    '/exhibitions', '/exhibitions/current', '/exhibition',
    '/whats-on', '/on-view', '/on-display', '/current',
    '/en/exhibitions', '/en/whats-on',
    '/exhibitions-events', '/visit/exhibitions',
]


def _default_fetcher(url: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Fetch a page via exhibition_checklist's polite/cached fetcher.

    Returns (html_or_text, links). We ask for RAW HTML because the structural
    extractor needs the DOM, not stripped text. exhibition_checklist._fetch_page
    returns visible text + links; to get HTML we do our own request here and
    fall back to the shared fetcher's links.
    """
    import requests
    try:
        resp = requests.get(url, headers={'User-Agent': 'Audioura/2.4 (+exhibitions)'},
                            timeout=15, allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            return resp.text, []
    except Exception:
        pass
    return '', []


def _candidate_listing_urls(base_site_url: str, venue_language: str = 'en') -> List[str]:
    """Build an ordered, de-duplicated list of listing-page URLs to try."""
    parsed = urlparse(base_site_url)
    if not parsed.scheme:
        base_site_url = 'https://' + base_site_url
        parsed = urlparse(base_site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    seeds: List[str] = []
    # Language-specific first (reuse exhibition_checklist's seed table if present).
    try:
        from exhibition_checklist import _EXHIBITION_PATH_SEEDS_BY_LANG
        lang = (venue_language or 'en').lower()[:2]
        seeds.extend(_EXHIBITION_PATH_SEEDS_BY_LANG.get(lang, []))
    except Exception:
        pass
    seeds.extend(_LISTING_SEEDS_EN)

    urls: List[str] = []
    seen = set()
    # The base page itself can be the listing (small venues).
    for u in [base_site_url] + [root + s for s in seeds]:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def discover_site_exhibitions(
    base_site_url: str,
    venue_language: str = 'en',
    fetcher: Optional[Callable[[str], Tuple[str, List[Tuple[str, str]]]]] = None,
    max_listing_tries: int = 6,
) -> Tuple[List[Dict], str]:
    """Find the venue's current exhibitions from its own site.

    Returns (exhibitions, listing_url) where exhibitions is a list of
    {'title', 'detail_url'} (from exhibition_discovery) and listing_url is the
    page they were found on ('' if none found).
    """
    if not base_site_url:
        return [], ''
    fetch = fetcher or _default_fetcher
    tried = 0
    for url in _candidate_listing_urls(base_site_url, venue_language):
        if tried >= max_listing_tries:
            break
        tried += 1
        html, _links = fetch(url)
        if not html or len(html) < 100:
            continue
        exhibitions = extract_current_exhibitions(html, url)
        if exhibitions:
            print(f"  [LOCAL-580] Site exhibitions found on {url}: "
                  f"{len(exhibitions)} show(s)")
            return exhibitions, url
    return [], ''


def build_site_first_candidates(
    base_site_url: str,
    venue_language: str = 'en',
    total_stops: int = 5,
    fetcher: Optional[Callable[[str], Tuple[str, List[Tuple[str, str]]]]] = None,
    fetch_detail_pages: bool = True,
) -> List[Dict]:
    """Build site-first candidate stops for an exhibition museum.

    One candidate per current exhibition. Each candidate is sourced from its own
    detail page (fetched for the description). Returns up to ``total_stops * 2``
    candidates (headroom for grounding) in the site's published order.

    Returns [] when the site yields no exhibitions — the caller then falls back
    to its existing paths (never turns a working tour into no tour, D577).
    """
    fetch = fetcher or _default_fetcher
    exhibitions, listing_url = discover_site_exhibitions(
        base_site_url, venue_language, fetcher=fetch)
    if not exhibitions:
        return []

    # Fetch the listing page text once so a show with a thin detail page still
    # has SOME grounding text (its blurb on the listing).
    listing_text = ''
    if listing_url:
        _html, _ = fetch(listing_url)
        listing_text = _visible_text(_html)

    cap = max(total_stops * 2, total_stops)
    candidates: List[Dict] = []
    for ex in exhibitions[:cap]:
        title = ex.get('title', '').strip()
        detail_url = ex.get('detail_url', '').strip()
        if not title:
            continue
        page_text = ''
        if fetch_detail_pages and detail_url:
            _html, _ = fetch(detail_url)
            page_text = _visible_text(_html)
        if not page_text:
            page_text = listing_text
        candidates.append({
            'name': title,
            'detail_url': detail_url,
            'page_text': page_text,
            'source': 'site_exhibition',
        })
    return candidates


_TAG_RE = re.compile(r'<[^>]+>')
_SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b.*?</\1>', re.DOTALL | re.IGNORECASE)


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
