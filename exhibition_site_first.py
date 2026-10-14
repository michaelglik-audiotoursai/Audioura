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
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from exhibition_discovery import extract_current_exhibitions

__all__ = ['discover_site_exhibitions', 'build_site_first_candidates', 'SiteFirstResult']

# [LOCAL-589] Timeouts. The field defect was a swallowed ReadTimeout: a 15 s
# listing fetch timed out, the error was discarded, and the run reported an empty
# site. The listing fetch now retries once with a LONGER timeout before giving up.
_LISTING_TIMEOUT = 15
_LISTING_RETRY_TIMEOUT = 30
_DETAIL_TIMEOUT = 15
# HTTP statuses worth a retry: a transient server/network failure, not a 404.
_RETRYABLE_STATUSES = frozenset({0, 408, 429, 500, 502, 503, 504})


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


def _default_fetcher(url: str, timeout: int = _LISTING_TIMEOUT):
    """Fetch a page and LOG the attempt (URL, status, bytes, seconds, exception).

    Returns a 3-tuple ``(html, links, meta)`` where ``meta`` is
    ``{'status': int, 'error': str, 'bytes': int, 'seconds': float}``. The meta
    lets the caller tell a FETCH FAILURE (timeout / 5xx / exception → status 0 or
    5xx, non-empty error) from a page that was fetched fine but held nothing.

    status == 0 means the request never produced an HTTP response (timeout,
    DNS/connection error) — the exact Griffin ReadTimeout case that used to be
    swallowed. We ask for RAW HTML because the structural extractor needs the DOM.
    """
    import requests
    status = 0
    error = ''
    html = ''
    _t0 = time.time()
    try:
        resp = requests.get(url, headers={'User-Agent': 'Audioura/2.4 (+exhibitions)'},
                            timeout=timeout, allow_redirects=True)
        status = resp.status_code
        if resp.status_code == 200 and resp.text:
            html = resp.text
    except Exception as _e:
        error = f"{type(_e).__name__}: {_e}"
    seconds = time.time() - _t0
    nbytes = len(html.encode('utf-8', 'ignore')) if html else 0
    print(f"  [LOCAL-589][fetch] {url} -> status={status} bytes={nbytes} "
          f"{seconds:.2f}s{(' EXC=' + error) if error else ''}")
    return html, [], {'status': status, 'error': error, 'bytes': nbytes,
                      'seconds': round(seconds, 3)}


def _normalize_fetch(result) -> Tuple[str, list, dict]:
    """Accept a legacy 2-tuple ``(html, links)`` or a 3-tuple ``(html, links,
    meta)`` and always return the 3-tuple. For a legacy fetcher we synthesize a
    meta: status 200 when HTML came back, else status 0 (treated as a failure
    only when NO html — a legacy fetcher cannot distinguish timeout from empty).
    """
    if isinstance(result, tuple) and len(result) == 3:
        html, links, meta = result
        meta = dict(meta or {})
        meta.setdefault('status', 200 if html else 0)
        meta.setdefault('error', '')
        meta.setdefault('bytes', len(html.encode('utf-8', 'ignore')) if html else 0)
        meta.setdefault('seconds', 0.0)
        return html or '', links or [], meta
    if isinstance(result, tuple) and len(result) == 2:
        html, links = result
        return (html or '', links or [],
                {'status': 200 if html else 0, 'error': '', 'seconds': 0.0,
                 'bytes': len(html.encode('utf-8', 'ignore')) if html else 0})
    # Defensive: a fetcher that returned something unexpected.
    return '', [], {'status': 0, 'error': 'bad_fetcher_return', 'bytes': 0, 'seconds': 0.0}


def _fetch_with_retry(url: str, fetch, diagnostics: dict,
                      is_listing: bool = False) -> Tuple[str, list, dict]:
    """Call ``fetch`` and, for a LISTING fetch, retry ONCE on a transient failure
    (timeout / 5xx) with a longer timeout. Records every attempt in
    ``diagnostics['fetches']``. Returns the normalized ``(html, links, meta)``.

    The retry is the fix for the Griffin intermittent ReadTimeout: a single
    network hiccup no longer looks like an empty site.
    """
    try:
        html, links, meta = _normalize_fetch(fetch(url))
    except TypeError:
        # Legacy fetcher with a strict 1-arg signature and no timeout kw — call
        # bare. (_default_fetcher accepts timeout; injected fakes may not.)
        html, links, meta = _normalize_fetch(fetch(url))
    if diagnostics is not None:
        diagnostics.setdefault('fetches', []).append({
            'url': url, 'status': meta.get('status', 0),
            'bytes': meta.get('bytes', 0), 'seconds': meta.get('seconds', 0.0),
            'error': meta.get('error', ''), 'kind': 'listing' if is_listing else 'detail',
            'attempt': 1,
        })
    failed = (not html) and (meta.get('status', 0) in _RETRYABLE_STATUSES)
    if is_listing and failed:
        print(f"  [LOCAL-589] listing fetch failed (status={meta.get('status')} "
              f"err='{meta.get('error','')}') — RETRYING once with longer timeout")
        try:
            retry = fetch(url, _LISTING_RETRY_TIMEOUT)
        except TypeError:
            retry = fetch(url)
        html, links, meta = _normalize_fetch(retry)
        if diagnostics is not None:
            diagnostics.setdefault('fetches', []).append({
                'url': url, 'status': meta.get('status', 0),
                'bytes': meta.get('bytes', 0), 'seconds': meta.get('seconds', 0.0),
                'error': meta.get('error', ''), 'kind': 'listing', 'attempt': 2,
            })
    return html, links, meta


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
    fetcher: Optional[Callable] = None,
    max_listing_tries: int = 6,
    diagnostics: Optional[Dict] = None,
) -> Tuple[List[Dict], str]:
    """Find the venue's current exhibitions from its own site.

    Returns (exhibitions, listing_url) where exhibitions is a list of
    {'title', 'detail_url'} (from exhibition_discovery) and listing_url is the
    page they were found on ('' if none found).

    When ``diagnostics`` is given it is populated with:
      * ``reason``        — 'ok' / 'parsed_zero' / 'no_listing_found' /
                            'fetch_failed'
      * ``fetch_failed``  — True when EVERY attempted listing fetch failed
                            (timeout/5xx/exception) and none returned usable HTML.
      * ``fetches``       — per-attempt records (URL, status, bytes, seconds).
    This is what lets the caller refuse to fall through to GPT invention on a
    transient network failure (the Griffin field defect).
    """
    if diagnostics is None:
        diagnostics = {}
    diagnostics.setdefault('fetches', [])
    if not base_site_url:
        diagnostics['reason'] = 'no_listing_found'
        diagnostics['fetch_failed'] = False
        return [], ''
    fetch = fetcher or _default_fetcher
    tried = 0
    _any_html = False          # at least one seed returned usable HTML
    _any_fetch_failure = False  # at least one seed failed to fetch (timeout/5xx)
    for url in _candidate_listing_urls(base_site_url, venue_language):
        if tried >= max_listing_tries:
            break
        tried += 1
        html, _links, meta = _fetch_with_retry(url, fetch, diagnostics, is_listing=True)
        if not html or len(html) < 100:
            if meta.get('status', 0) in _RETRYABLE_STATUSES and not html:
                _any_fetch_failure = True
            continue
        _any_html = True
        exhibitions = extract_current_exhibitions(html, url)
        if exhibitions:
            print(f"  [LOCAL-580] Site exhibitions found on {url}: "
                  f"{len(exhibitions)} show(s)")
            diagnostics['reason'] = 'ok'
            diagnostics['fetch_failed'] = False
            diagnostics['listing_url'] = url
            return exhibitions, url
    # Nothing returned — say WHY.
    if _any_html:
        # A listing page was fetched but held no structural exhibitions.
        diagnostics['reason'] = 'parsed_zero'
        diagnostics['fetch_failed'] = False
    elif _any_fetch_failure:
        # Every seed that could carry the listing failed to fetch.
        diagnostics['reason'] = 'fetch_failed'
        diagnostics['fetch_failed'] = True
    else:
        diagnostics['reason'] = 'no_listing_found'
        diagnostics['fetch_failed'] = False
    print(f"  [LOCAL-589] discover_site_exhibitions: reason={diagnostics['reason']} "
          f"(tried {tried} seed(s), {len(diagnostics['fetches'])} fetch attempt(s))")
    return [], ''


def build_site_first_candidates(
    base_site_url: str,
    venue_language: str = 'en',
    total_stops: int = 5,
    fetcher: Optional[Callable] = None,
    fetch_detail_pages: bool = True,
    diagnostics: Optional[Dict] = None,
) -> List[Dict]:
    """Build site-first candidate stops for an exhibition museum.

    One candidate per current exhibition. Each candidate is sourced from its own
    detail page (fetched for the description). Returns up to ``total_stops * 2``
    candidates (headroom for grounding) in the site's published order.

    Returns [] when the site yields no exhibitions. When ``diagnostics`` is
    given it carries the honest reason (see discover_site_exhibitions) so the
    caller can distinguish 'fetch_failed' (retry / overview rung, NEVER GPT
    invention) from 'parsed_zero'/'no_listing_found'.
    """
    if diagnostics is None:
        diagnostics = {}
    fetch = fetcher or _default_fetcher
    exhibitions, listing_url = discover_site_exhibitions(
        base_site_url, venue_language, fetcher=fetch, diagnostics=diagnostics)
    if not exhibitions:
        # reason/fetch_failed already set by discover_site_exhibitions.
        return []

    # Fetch the listing page text once so a show with a thin detail page still
    # has SOME grounding text (its blurb on the listing).
    listing_text = ''
    if listing_url:
        _html, _, _ = _fetch_with_retry(listing_url, fetch, diagnostics, is_listing=False)
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
            _html, _, _ = _fetch_with_retry(detail_url, fetch, diagnostics, is_listing=False)
            page_text = _visible_text(_html)
        if not page_text:
            page_text = listing_text
        candidates.append({
            'name': title,
            'detail_url': detail_url,
            'page_text': page_text,
            'source': 'site_exhibition',
        })
    diagnostics['reason'] = 'ok'
    diagnostics['fetch_failed'] = False
    diagnostics['candidate_count'] = len(candidates)
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
