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

from exhibition_discovery import (extract_current_exhibitions,
                                  extract_classified_exhibitions)

# [LOCAL-602] JS-only / chain-venue helpers (identical-shell detection, sitemap/
# robots URLs, branch-page pick, embedded-JSON + Serper fallbacks, no-other-city
# filter). Imported defensively so a missing module degrades to the pre-602
# behaviour rather than crashing a tour.
try:
    import exhibition_site_js as _js
    _shell_fingerprint = _js.shell_fingerprint
except Exception:                                   # pragma: no cover
    _js = None

    def _shell_fingerprint(html):
        return ''

__all__ = ['discover_site_exhibitions', 'build_site_first_candidates',
           'discover_classified_exhibitions', 'SiteFirstResult']

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

# [LOCAL-599B] For an EXHIBITION museum, a detail link whose FIRST path segment is
# one of these is a program / event / class / studio / shop / membership page —
# NOT an exhibition. The structural extractor (_DETAIL_PATH_RE) accepts /event/…
# as a "detail page" so programs can be surfaced for event-driven venues; here, on
# the exhibition path, we keep only true exhibition detail links. MassArt's
# "Make with MAAM" (/event/make-maam-222) — a hands-on Studio program, not a show
# — is dropped by this rule. The policy is a path-segment classifier (deterministic),
# never a blocklist of titles.
_NON_EXHIBITION_FIRST_SEGMENTS = frozenset({
    'event', 'events', 'program', 'programs', 'programme', 'programmes',
    'class', 'classes', 'workshop', 'workshops', 'studio', 'studios',
    'shop', 'store', 'membership', 'join', 'donate', 'support', 'give',
    'rental', 'rentals', 'cafe', 'calendar', 'news', 'blog', 'press',
    'tour', 'tours', 'camp', 'camps', 'course', 'courses',
})
# Path roots that positively mark an EXHIBITION detail page. When a listing yields
# a mix of exhibition and non-exhibition detail links, those under one of these
# roots are preferred (and are the only ones kept on the exhibition path).
_EXHIBITION_FIRST_SEGMENTS = frozenset({
    'exhibition', 'exhibitions', 'exhibit', 'exhibits', 'show', 'shows',
    'on-view', 'onview', 'display', 'installation',
})


def _first_path_segment(detail_url: str) -> str:
    """Lower-cased first path segment of a URL ('/exhibition/x' → 'exhibition')."""
    try:
        path = urlparse(detail_url).path.strip('/')
    except Exception:
        return ''
    return path.split('/', 1)[0].lower() if path else ''


def _is_exhibition_detail(detail_url: str) -> bool:
    """True when a detail URL is an EXHIBITION page (not a program/event/shop…)."""
    seg = _first_path_segment(detail_url)
    if seg in _NON_EXHIBITION_FIRST_SEGMENTS:
        return False
    # When the path has a recognised exhibition root, it is clearly a show.
    if seg in _EXHIBITION_FIRST_SEGMENTS:
        return True
    # Unknown root (a venue that files shows elsewhere): accept it — the structural
    # extractor already proved it is an on-domain detail page, and this policy only
    # EXCLUDES the known non-exhibition roots.
    return True


_STATUS_ORDER = {'on_view': 0, 'upcoming': 1, 'past': 2}



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
            'attempt': 1, 'fingerprint': _shell_fingerprint(html),
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
                'fingerprint': _shell_fingerprint(html),
            })
    return html, links, meta


def _candidate_listing_urls(base_site_url: str, venue_language: str = 'en') -> List[str]:
    """Build an ordered, de-duplicated list of listing-page URLs to try.

    [LOCAL-599B] The dedicated exhibition-listing seeds (``/exhibitions``,
    ``/current-exhibitions`` …) are tried BEFORE the home page. The home page is a
    poor exhibition listing: it mixes shows with events/programs and often links
    its exhibition teasers as image-only anchors with no heading (so the
    structural extractor misses them), while surfacing a hands-on PROGRAM
    (MassArt's "Make with MAAM" → /event/…) that is NOT an exhibition. Reaching
    ``/exhibitions`` first — and accumulating across every seed (see
    discover_site_exhibitions) — is what gets the real shows instead of the one
    program. The home page is kept as a LAST resort for small single-page venues.
    """
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
    # Dedicated listing seeds FIRST, then the base/home page as a fallback.
    for u in [root + s for s in seeds] + [base_site_url]:
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
    # [LOCAL-599B] ACCUMULATE across seeds instead of returning the FIRST seed that
    # yields any show. The home page is tried last (poor exhibition listing) and
    # a dedicated /exhibitions index — which carries the real shows — wins. The
    # best listing is the one that yields the MOST on-domain exhibition detail
    # links; ties go to the first (dedicated-seed) page in try order.
    _best_exhibitions: List[Dict] = []
    _best_url = ''
    _best_score = -1
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
        if not exhibitions:
            continue
        # Score a listing by how many TRUE exhibition detail links it carries, so a
        # dedicated /exhibitions index beats a home page that links one program.
        _n_shows = sum(1 for e in exhibitions
                       if _is_exhibition_detail(e.get('detail_url', '')))
        _score = _n_shows if _n_shows > 0 else 0
        print(f"  [LOCAL-580] Site exhibitions on {url}: {len(exhibitions)} "
              f"detail-linked ({_n_shows} true exhibition{'s' if _n_shows != 1 else ''})")
        if _score > _best_score:
            _best_score = _score
            _best_exhibitions = exhibitions
            _best_url = url
        # A listing with several true exhibitions is authoritative — stop early.
        if _n_shows >= 2:
            break
    if _best_exhibitions:
        diagnostics['reason'] = 'ok'
        diagnostics['fetch_failed'] = False
        diagnostics['listing_url'] = _best_url
        return _best_exhibitions, _best_url
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


def discover_classified_exhibitions(
    base_site_url: str,
    venue_language: str = 'en',
    fetcher: Optional[Callable] = None,
    max_listing_tries: int = 8,
    diagnostics: Optional[Dict] = None,
    today=None,
    supplement_past: bool = False,
) -> Tuple[List[Dict], str]:
    """[LOCAL-599B] Like discover_site_exhibitions, but returns exhibitions WITH a
    deterministic status, ordered on_view → upcoming → past, with programs/events
    EXCLUDED (exhibition-museum policy).

    [LOCAL-599C] ``supplement_past`` defaults to False: r3 never ships a past show
    as a stop, so the dedicated past-archive page is NOT fetched by default (it was
    only ever used to pad to N with past shows, which is withdrawn). It is kept as
    an opt-in for any caller that still wants the full archive (e.g. an archive
    view), but the site-first stop builder leaves it off.

    Returns (exhibitions, listing_url). Each exhibition carries
    {'title', 'detail_url', 'status', 'dates'}. On-view shows come first (the tour
    opens with the current exhibitions), then upcoming, then past — the honest
    fill order of D611. The home page is tried last; the dedicated /exhibitions
    index (which cleanly splits on-view vs past) wins and provides the authoritative
    status via its CMS sections.
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
    _any_html = False
    _any_fetch_failure = False
    _best: List[Dict] = []
    _best_url = ''
    _best_score = -1
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
        classified = extract_classified_exhibitions(html, url, today=today)
        # Keep only TRUE exhibitions (drop programs/events/shop/membership…).
        shows = [e for e in classified if _is_exhibition_detail(e.get('detail_url', ''))]
        if not shows:
            continue
        _n_on_view = sum(1 for e in shows if e.get('status') == 'on_view')
        # Prefer the listing with the most TRUE shows; a tie prefers more on-view.
        _score = len(shows) * 100 + _n_on_view
        print(f"  [LOCAL-599B] {url}: {len(shows)} exhibition(s) "
              f"(on_view={_n_on_view}, "
              f"upcoming={sum(1 for e in shows if e.get('status')=='upcoming')}, "
              f"past={sum(1 for e in shows if e.get('status')=='past')})")
        if _score > _best_score:
            _best_score = _score
            _best = shows
            _best_url = url
        if len(shows) >= 2:
            break
    if _best:
        # [LOCAL-599B/599C] Supplement PAST shows from a dedicated archive page
        # ONLY when the caller opts in (``supplement_past``). r3 never ships a past
        # show, so the stop builder leaves this off and the archive is not fetched.
        if supplement_past:
            _best = _supplement_past_exhibitions(
                base_site_url, _best, fetch, diagnostics, today=today)
        # Order on_view → upcoming → past, preserving document order within a group.
        _best_sorted = sorted(
            _best, key=lambda e: _STATUS_ORDER.get(e.get('status', 'on_view'), 0))
        diagnostics['reason'] = 'ok'
        diagnostics['fetch_failed'] = False
        diagnostics['listing_url'] = _best_url
        diagnostics['status_counts'] = {
            s: sum(1 for e in _best_sorted if e.get('status') == s)
            for s in ('on_view', 'upcoming', 'past')}
        return _best_sorted, _best_url
    if _any_html:
        diagnostics['reason'] = 'parsed_zero'
        diagnostics['fetch_failed'] = False
    elif _any_fetch_failure:
        diagnostics['reason'] = 'fetch_failed'
        diagnostics['fetch_failed'] = True
    else:
        diagnostics['reason'] = 'no_listing_found'
        diagnostics['fetch_failed'] = False
    return [], ''


# Dedicated past/archive listing seeds — a full past-exhibitions page that many
# venues keep separate from their main /exhibitions index.
_PAST_SEEDS = ['/exhibitions/past', '/past-exhibitions', '/exhibitions/archive',
               '/exhibitions-archive', '/archive/exhibitions']


def _supplement_past_exhibitions(base_site_url, exhibitions, fetch,
                                 diagnostics, today=None) -> List[Dict]:
    """[LOCAL-599B] Add PAST exhibitions from a dedicated past-exhibitions page.

    The main /exhibitions index usually shows only the few most recent past shows;
    a venue's full archive lives at /exhibitions/past (etc). We fetch the first
    such page that resolves and merge any NEW past exhibitions (de-duplicated by
    detail_url) after the ones already found. Every added entry is a real,
    structural, detail-linked PAST show — nothing is invented. Best-effort: any
    fetch/parse failure returns the input unchanged.
    """
    if not base_site_url:
        return exhibitions
    parsed = urlparse(base_site_url if '://' in base_site_url
                      else 'https://' + base_site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    have_urls = {e.get('detail_url') for e in exhibitions}
    merged = list(exhibitions)
    for seed in _PAST_SEEDS:
        url = root + seed
        # Skip if this seed IS the page we already parsed.
        if url == diagnostics.get('listing_url'):
            continue
        html, _, meta = _fetch_with_retry(url, fetch, diagnostics, is_listing=False)
        if not html or len(html) < 100 or meta.get('status', 0) != 200:
            continue
        classified = extract_classified_exhibitions(html, url, today=today)
        added = 0
        for e in classified:
            du = e.get('detail_url')
            if not du or du in have_urls:
                continue
            if not _is_exhibition_detail(du):
                continue
            # A dedicated past page lists past shows; force the past label unless
            # classification already found it on-view/upcoming (it won't here).
            if e.get('status') not in ('on_view', 'upcoming'):
                e['status'] = 'past'
            have_urls.add(du)
            merged.append(e)
            added += 1
        if added:
            print(f"  [LOCAL-599B] +{added} past exhibition(s) from {url}")
            break  # one archive page is enough
    return merged


def build_site_first_candidates(
    base_site_url: str,
    venue_language: str = 'en',
    total_stops: int = 5,
    fetcher: Optional[Callable] = None,
    fetch_detail_pages: bool = True,
    diagnostics: Optional[Dict] = None,
    today=None,
    city: str = '',
    serper: Optional[Callable] = None,
) -> List[Dict]:
    """Build site-first candidate stops for an exhibition museum, filled toward N.

    [LOCAL-599C] The candidate list is assembled from WHAT IS ON VIEW, in the
    honest fill order (r3, LEAD 2026-10-06 — the r2 "past shows pad to N" order
    is WITHDRAWN):
      (a) each CURRENT (on-view) exhibition is SPLIT into the works/rooms its own
          detail page names — the show itself (artist + named title) as the
          primary stop, then the specific NAMED WORKS the page credits — so three
          current shows yield 2–3 stops each (``extract_exhibition_works``);
      (b) the museum's own NAMED SPACES / building features from /visit and /about
          (lobby, galleries by floor, the building) — each with a source URL;
      (c) at most ONE UPCOMING exhibition, labelled "opening <date>".
    PAST exhibitions are NEVER emitted: a listener standing in the museum must not
    be sent to a show that is off the walls. Programs/events/studios/shop are never
    exhibitions and are dropped (``_is_exhibition_detail``). Every candidate carries
    a ``source_url`` (its own detail page or the /visit|/about page it was read
    from), a ``status`` and a ``kind``. Nothing is invented: a work is only emitted
    when the show's own page names it, a space only when the venue's own page names
    it; if (a)-(c) cannot reach N the list is simply shorter and the caller logs the
    honest shortfall (D611 — don't pad).

    Returns [] when the site yields no on-view exhibition AND no named space. When
    ``diagnostics`` is given it carries the honest reason (see
    discover_classified_exhibitions) plus ``status_counts`` and ``kind_counts``.
    """
    if diagnostics is None:
        diagnostics = {}
    fetch = fetcher or _default_fetcher
    exhibitions, listing_url = discover_classified_exhibitions(
        base_site_url, venue_language, fetcher=fetch, diagnostics=diagnostics,
        today=today)

    # Fetch the listing page text once so a show with a thin detail page still
    # has SOME grounding text (its blurb on the listing).
    listing_text = ''
    if listing_url:
        _html, _, _ = _fetch_with_retry(listing_url, fetch, diagnostics, is_listing=False)
        listing_text = _visible_text(_html)

    def _fetch_detail(ex: Dict) -> Tuple[str, str]:
        """Return (detail_html, visible_text) for an exhibition's detail page."""
        detail_url = (ex.get('detail_url') or '').strip()
        if fetch_detail_pages and detail_url:
            _html, _, _ = _fetch_with_retry(detail_url, fetch, diagnostics, is_listing=False)
            return _html or '', _visible_text(_html)
        return '', ''

    def _mk_exhibition_candidate(ex: Dict, label_upcoming: bool = False) -> Optional[Dict]:
        title = (ex.get('title') or '').strip()
        detail_url = (ex.get('detail_url') or '').strip()
        if not title:
            return None
        _html, page_text = _fetch_detail(ex)
        if not page_text:
            page_text = listing_text
        status = ex.get('status', 'on_view')
        name = title
        if label_upcoming and status == 'upcoming':
            dates = (ex.get('dates') or '').strip()
            # Derive the opening date from the show's date range when present.
            opening = ''
            if dates:
                m = re.match(r'\s*([A-Za-z]{3,9}\.?\s+\d{0,2}\s*,?\s*\d{4})', dates)
                opening = (m.group(1).strip() if m else dates.split('–')[0].split('-')[0].strip())
            name = f"{title} (opening {opening})" if opening else f"{title} (upcoming)"
        return {
            'name': name,
            'detail_url': detail_url,
            'source_url': detail_url or listing_url,
            'page_text': page_text,
            'source': 'site_exhibition',
            'kind': 'exhibition',
            'status': status,
            'dates': ex.get('dates', ''),
        }

    def _work_candidates(ex: Dict, detail_html: str, detail_text: str,
                         exclude: set) -> List[Dict]:
        """Per-work stops split from ONE on-view show's detail page.

        The show's artist (its listing title) + named work read "Artist: Work",
        so a stop is a specific thing on the wall ("Robert Lazzarini: American
        flag"). The show's own named title is NOT re-emitted here (the primary
        exhibition candidate already carries it); only distinct WORKS are added.
        """
        from exhibition_discovery import extract_exhibition_works
        artist = (ex.get('title') or '').strip()
        detail_url = (ex.get('detail_url') or '').strip()
        works = extract_exhibition_works(
            detail_html, base_url=detail_url, artist=artist, max_works=4)
        out: List[Dict] = []
        _local_seen = set()
        for w in works:
            if w.get('kind') != 'work':
                continue  # the exhibition_title is the primary stop, not a work
            wname = w['name'].strip()
            full = f"{artist}: {wname}" if artist else wname
            fkey = full.lower()
            # Only skip against names ALREADY placed (``exclude``) and local repeats;
            # the shared ``_names`` set is updated by ``_append`` alone, so a work is
            # never silently dropped by a double-add.
            if fkey in exclude or fkey in _local_seen:
                continue
            _local_seen.add(fkey)
            out.append({
                'name': full,
                'detail_url': detail_url,
                'source_url': detail_url or listing_url,
                'page_text': detail_text or listing_text,
                'source': 'site_exhibition',
                'kind': 'work',
                'status': 'on_view',
                'dates': ex.get('dates', ''),
            })
        return out

    # Split by status. PAST is dropped entirely (r3): never a stop.
    on_view = [e for e in exhibitions if e.get('status') == 'on_view']
    upcoming = [e for e in exhibitions if e.get('status') == 'upcoming']

    cap = max(total_stops * 2, total_stops)
    candidates: List[Dict] = []
    _names = set()

    def _append(c: Optional[Dict]) -> bool:
        if not c or len(candidates) >= cap:
            return False
        key = c['name'].lower()
        if key in _names:
            return False
        _names.add(key)
        candidates.append(c)
        return True

    # (a) current exhibitions, each SPLIT into the works/rooms its page names.
    # First pass: the show itself (artist + named title) as the primary stop,
    # with its detail page fetched once and reused for the works split.
    for ex in on_view:
        if len(candidates) >= cap:
            break
        detail_html, detail_text = _fetch_detail(ex)
        c = _mk_exhibition_candidate(ex)
        if c:
            # Reuse the already-fetched detail text (avoid a second fetch).
            if detail_text:
                c['page_text'] = detail_text
            _append(c)
        # Then the show's specific named works, interleaved per show so each
        # current exhibition contributes 2–3 stops before we move on.
        for wc in _work_candidates(ex, detail_html, detail_text, _names):
            if len(candidates) >= cap:
                break
            _append(wc)

    # (b) museum's own named spaces / building features (/visit, /about), only to
    # fill toward N and only when the venue's own pages name them.
    if len(candidates) < total_stops:
        space_candidates = _discover_museum_spaces(
            base_site_url, fetch, diagnostics,
            want=total_stops - len(candidates),
            exclude_titles=set(_names))
        for sc in space_candidates:
            if len(candidates) >= cap:
                break
            _append(sc)

    # (c) at most ONE upcoming exhibition, labelled "opening <date>". NEVER past.
    if len(candidates) < total_stops and upcoming:
        _append(_mk_exhibition_candidate(upcoming[0], label_upcoming=True))

    if not candidates:
        # [LOCAL-602] The structural extractor found nothing. For a JS-only site
        # (every path returns the same client-side shell) or a CHAIN venue (branch
        # pages per city), try the no-headless fallbacks before giving up:
        # branch page → sitemap/robots URLs → embedded JSON → Serper site:<domain>.
        js_candidates = _build_js_fallback_candidates(
            base_site_url, city, total_stops, fetch, serper, diagnostics)
        if js_candidates:
            diagnostics['reason'] = 'ok'
            diagnostics['fetch_failed'] = False
            diagnostics['candidate_count'] = len(js_candidates)
            diagnostics['via'] = 'js_fallback'
            return js_candidates
        # reason/fetch_failed already set by discover_classified_exhibitions.
        return []

    diagnostics['reason'] = 'ok'
    diagnostics['fetch_failed'] = False
    diagnostics['candidate_count'] = len(candidates)
    diagnostics['kind_counts'] = {
        k: sum(1 for c in candidates if c.get('kind') == k)
        for k in ('exhibition', 'work', 'museum_space')}
    diagnostics['status_counts'] = {
        s: sum(1 for c in candidates if c.get('status') == s)
        for s in ('on_view', 'upcoming', 'past', 'space')}
    # r3 invariant: a past show must never leave this function as a stop.
    assert diagnostics['status_counts']['past'] == 0, \
        "LOCAL-599C: past exhibition leaked into site-first candidates"
    return candidates


def _build_js_fallback_candidates(base_site_url, city, total_stops, fetch,
                                  serper, diagnostics) -> List[Dict]:
    """[LOCAL-602] Candidates for a JS-only / chain venue, no headless browser.

    Only runs when the structural extractor found nothing. In order:
      1. If a CHAIN with a known ``city``, find the branch page (sitemap or
         conventional slug) and read the EMBEDDED JSON it ships.
      2. Read embedded JSON from the shell(s) already fetched (via a re-fetch of
         the root / branch page).
      3. Serper ``site:<domain> <city>`` — each organic result is a candidate with
         its own URL as the source.
    Every candidate is passed through the no-other-city filter so a Boston tour
    never carries a Chicago-only installation. Returns [] (never raises) when the
    JS helpers are unavailable or nothing is found. Diagnostics record the path.
    """
    if _js is None or not base_site_url:
        return []
    diagnostics.setdefault('fetches', [])
    identical = _js.detect_identical_shell(diagnostics.get('fetches', []))
    diagnostics['identical_shell'] = identical
    root = _js._root_of(base_site_url)
    domain = urlparse(root).netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]

    seeds_tried: List[str] = []
    raw_items: List[Dict] = []

    # 1 + 2. Branch page (city) and the root shell → embedded JSON.
    branch_url = ''
    if city:
        try:
            sm = _js.sitemap_urls(base_site_url, fetch)
        except Exception:
            sm = []
        if sm:
            diagnostics['sitemap_url_count'] = len(sm)
        try:
            branch_url = _js.pick_branch_url(base_site_url, city, sm)
        except Exception:
            branch_url = ''

    # Build the ordered list of shell pages to read embedded JSON from: branch
    # page first (its JSON is the city's), then the conventional branch seeds,
    # then the root.
    json_pages: List[str] = []
    if branch_url:
        json_pages.append(branch_url)
    if city:
        try:
            json_pages.extend(_js.branch_url_seeds(base_site_url, city))
        except Exception:
            pass
    json_pages.append(root)
    # De-dup, keep order, cap the number of fetches.
    seen_pg = set()
    json_pages = [u for u in json_pages
                  if not (u in seen_pg or seen_pg.add(u))][:6]

    for pg in json_pages:
        html, _, _ = _fetch_with_retry(pg, fetch, diagnostics, is_listing=False)
        if not html:
            continue
        seeds_tried.append(pg)
        try:
            items = _js.extract_embedded_json(html, pg, city=city)
        except Exception:
            items = []
        if items:
            if pg == branch_url and branch_url:
                diagnostics['branch_url'] = branch_url
                print(f"  [LOCAL-602] branch page for {city!r}: {branch_url} "
                      f"→ {len(items)} embedded-JSON item(s)")
            raw_items.extend(items)
            # A branch page with several items is authoritative; stop early.
            if len([i for i in raw_items]) >= max(total_stops, 2):
                break

    # 3. Serper site:<domain> <city> — only if we still need more and have a key.
    if len(raw_items) < total_stops and city and serper is not None:
        try:
            serp_items = _js.serper_site_city(domain, city, serper,
                                              max_results=total_stops * 2)
        except Exception:
            serp_items = []
        if serp_items:
            diagnostics['serper_hit'] = len(serp_items)
            print(f"  [LOCAL-602] Serper site:{domain} {city} → "
                  f"{len(serp_items)} result(s)")
            raw_items.extend(serp_items)

    if not raw_items:
        diagnostics['js_fallback'] = 'empty'
        return []

    # No-other-city filter: drop anything attested only on another branch.
    if city:
        before = len(raw_items)
        raw_items = _js.filter_other_city(raw_items, city)
        if len(raw_items) != before:
            print(f"  [LOCAL-602] no-other-city filter dropped "
                  f"{before - len(raw_items)} item(s) attested only off-{city}")

    # Junk-stop filter: a stop must be a thing you look at, not a ticket / gift-card
    # / shop / membership / events / FAQ / contact page or the branch INDEX page
    # itself. Deterministic path-only rule (LOCAL-602 r2 — the r1 run shipped
    # "/tickets/boston/gift-cards" and "/location/boston" as stops).
    before = len(raw_items)
    raw_items = _js.reject_non_stop_urls(raw_items, city)
    if len(raw_items) != before:
        diagnostics['non_stop_dropped'] = before - len(raw_items)
        print(f"  [LOCAL-602] junk-stop filter dropped {before - len(raw_items)} "
              f"non-stop page(s) (tickets/gift-cards/shop/branch-index/…)")

    # Materialise candidates (de-dup by title), capped at ~2x N.
    cap = max(total_stops * 2, total_stops)
    out: List[Dict] = []
    names = set()
    for it in raw_items:
        if len(out) >= cap:
            break
        title = (it.get('title') or '').strip()
        if not title:
            continue
        key = title.lower()
        if key in names:
            continue
        names.add(key)
        src = it.get('source_url') or it.get('detail_url') or branch_url or root
        out.append({
            'name': title,
            'detail_url': it.get('detail_url', '') or src,
            'source_url': src,
            'page_text': it.get('snippet', '') or '',
            'source': it.get('source', 'js_fallback'),
            'kind': 'exhibition',
            'status': 'on_view',
            'dates': '',
        })
    diagnostics['js_fallback'] = diagnostics.get('via', 'js_fallback')
    diagnostics['js_candidate_count'] = len(out)
    return out


# Pages whose named sections make honest "museum space" stops (lobby, galleries by
# floor, the building). /visit and /about are the D611-named sources.
_SPACE_SEEDS = ['/visit', '/plan-your-visit', '/about', '/about-us',
                '/the-building', '/architecture', '/galleries', '/floor-plan']

# A heading on a /visit or /about page names a MUSEUM SPACE when it reads like a
# room / gallery / floor / building feature. Deterministic token test — not a
# blocklist of names. Kept conservative so page furniture ("Plan Your Visit",
# "Hours & Admission", "Membership") is never emitted as a space.
_SPACE_TOKEN_RE = re.compile(
    r'(?i)\b(gallery|galleries|lobby|atrium|hall|wing|floor|mezzanine|'
    r'rotunda|court|courtyard|terrace|pavilion|studio|theater|theatre|'
    r'auditorium|library|reading\s+room|sculpture\s+garden|'
    r'ground\s+floor|first\s+floor|second\s+floor|third\s+floor|'
    r'main\s+gallery|project\s+space|entrance|building)\b')
# Space headings that are actually page furniture — never a stop.
_SPACE_FURNITURE_RE = re.compile(
    r'(?i)\b(plan\s+your\s+visit|hours|admission|tickets?|membership|directions|'
    r'parking|accessib|getting\s+here|contact|map|faq|group\s+visits?|'
    r'book\s+a|buy\b|shop|cafe|store)\b')


def _discover_museum_spaces(base_site_url: str, fetch, diagnostics: Dict,
                            want: int, exclude_titles: set) -> List[Dict]:
    """[LOCAL-599B] Read the museum's OWN named spaces from /visit and /about.

    Returns up to ``want`` candidate dicts of kind 'museum_space', each with a
    ``source_url`` (the /visit or /about page it was found on) and the page text as
    grounding. A space is emitted only when a heading on the venue's own page names
    a room/gallery/floor/building feature (``_SPACE_TOKEN_RE``) and is not page
    furniture (``_SPACE_FURNITURE_RE``) — nothing is invented. Pure w.r.t. the
    injected fetcher; de-duplicated against ``exclude_titles`` and within itself.
    """
    if want <= 0 or not base_site_url:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    parsed = urlparse(base_site_url if '://' in base_site_url else 'https://' + base_site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    out: List[Dict] = []
    seen = set(t.lower() for t in (exclude_titles or set()))
    for seed in _SPACE_SEEDS:
        if len(out) >= want:
            break
        url = root + seed
        html, _, _ = _fetch_with_retry(url, fetch, diagnostics, is_listing=False)
        if not html or len(html) < 100:
            continue
        page_text = _visible_text(html)
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            continue
        for h in soup.find_all(('h1', 'h2', 'h3', 'h4')):
            if len(out) >= want:
                break
            title = re.sub(r'\s+', ' ', h.get_text(' ', strip=True)).strip()
            if not title or len(title) < 3 or len(title) > 80:
                continue
            if _SPACE_FURNITURE_RE.search(title):
                continue
            if not _SPACE_TOKEN_RE.search(title):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({
                'name': title,
                'detail_url': url,
                'source_url': url,
                'page_text': page_text,
                'source': 'museum_space',
                'kind': 'museum_space',
                'status': 'space',
                'dates': '',
            })
    if out:
        print(f"  [LOCAL-599B] museum spaces from /visit+/about: "
              f"{len(out)} named space(s) — {[c['name'] for c in out]}")
    return out


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
