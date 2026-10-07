#!/usr/bin/env python3
"""exhibition_site_js.py — LOCAL-602: read a JavaScript-only / chain venue site.

The field defect (tour 397, WNDR museum, Boston):

    [LOCAL-589][fetch] /current-exhibitions, /exhibitions, /exhibitions/current,
    /exhibition -> 200, bytes=210318 (ALL IDENTICAL)
    [LOCAL-580] Site-first found no current exhibitions — reason=parsed_zero

Every path on wndrmuseum.com returned the SAME 210 KB client-rendered shell, so
the structural extractor (which reads server-rendered HTML) found nothing. WNDR
is also a CHAIN (Chicago, Boston, Seattle …), so its single Wikidata item failed
city validation and carried another city's coordinates.

This module adds, with NO headless browser and nothing invented:

  1. ``shell_fingerprint`` / ``detect_identical_shell`` — recognise that several
     distinct paths returned the same client-side shell (a JS-only site).
  2. ``sitemap_urls`` — the URLs a site lists in ``/sitemap.xml`` and the
     ``Sitemap:`` lines of ``/robots.txt``.
  3. ``pick_branch_url`` — for a chain, the branch page for the requested city
     (``/<city>`` or ``/locations/<city>`` …), discovered from the sitemap or a
     ``site:<domain> <city>`` Serper query.
  4. ``extract_embedded_json`` — the data a JS site ships inside its shell:
     ``__NEXT_DATA__``, ``application/ld+json``, ``window.__INITIAL_STATE__`` —
     yielding ``{'title','detail_url','source_url'}`` items with a source URL.
  5. ``serper_site_city`` — ``site:<domain> <city>`` snippets, each kept with its
     own result URL as the source.
  6. ``filter_other_city`` — drop any item that is attested ONLY on another
     branch's page (a Boston tour must never describe Chicago's installation).

Every function is pure w.r.t. an injected ``fetch``/``serper`` callable, so the
whole flow is unit-testable with fixtures and no network.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

__all__ = [
    'shell_fingerprint', 'detect_identical_shell', 'sitemap_urls',
    'pick_branch_url', 'extract_embedded_json', 'serper_site_city',
    'filter_other_city', 'slug_variants', 'US_CHAIN_CITIES', 'default_serper',
    'is_stop_url', 'reject_non_stop_urls', 'NON_STOP_SEGMENTS',
    'is_exhibit_stop', 'is_exhibit_heading', 'STOP_PATH_SEGMENTS',
    'EXHIBIT_JSONLD_TYPES',
]

# Cities where immersive-art / experience chains commonly have branches. Used ONLY
# as the "other branches" set for the no-other-city filter and to seed branch-page
# slug guesses — never to invent content.
US_CHAIN_CITIES = (
    'chicago', 'boston', 'seattle', 'san diego', 'denver', 'dallas', 'houston',
    'atlanta', 'las vegas', 'los angeles', 'new york', 'san francisco', 'austin',
    'philadelphia', 'phoenix', 'miami', 'minneapolis', 'portland', 'scottsdale',
    'washington', 'nashville', 'orlando', 'san antonio',
)


# ── 1. identical-shell detection ─────────────────────────────────────────────

_WS_RE = re.compile(r'\s+')


def shell_fingerprint(html: str) -> str:
    """A stable fingerprint of a page's shell.

    Whitespace is collapsed so trivial formatting differences do not change the
    fingerprint, but the content is otherwise taken verbatim. Two client-rendered
    pages that ship the SAME shell for different routes get the SAME fingerprint.
    Empty/short HTML returns ''.
    """
    if not html or len(html) < 100:
        return ''
    norm = _WS_RE.sub(' ', html).strip()
    return hashlib.sha256(norm.encode('utf-8', 'ignore')).hexdigest()


def detect_identical_shell(fetch_records: List[Dict]) -> bool:
    """True when ≥2 DISTINCT URLs returned the same non-trivial shell.

    ``fetch_records`` is a list of ``{'url','fingerprint'}`` (or ``{'url','html'}``)
    dicts — e.g. the per-attempt records build_site_first_candidates already keeps
    in ``diagnostics['fetches']`` (augmented with a fingerprint). A JS-only site is
    one where several paths collapse to a single fingerprint.
    """
    by_fp: Dict[str, set] = {}
    for rec in fetch_records or []:
        fp = rec.get('fingerprint')
        if not fp and rec.get('html'):
            fp = shell_fingerprint(rec['html'])
        if not fp:
            continue
        url = (rec.get('url') or '').rstrip('/')
        by_fp.setdefault(fp, set()).add(url)
    return any(len(urls) >= 2 for urls in by_fp.values())


# ── 2. sitemap / robots URLs ─────────────────────────────────────────────────

_LOC_RE = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>', re.IGNORECASE)
_SITEMAP_LINE_RE = re.compile(r'(?im)^\s*sitemap:\s*(\S+)\s*$')


def _root_of(url: str) -> str:
    if '://' not in (url or ''):
        url = 'https://' + (url or '')
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def sitemap_urls(base_site_url: str, fetch: Callable,
                 max_urls: int = 400) -> List[str]:
    """Collect on-domain URLs from /sitemap.xml and /robots.txt-listed sitemaps.

    ``fetch(url)`` returns HTML/text (first element of the project fetcher's
    tuple is accepted too). Nested sitemap indexes are followed one level. Only
    on-domain URLs are returned, de-duplicated, order preserved. Best-effort:
    any failure yields what was gathered so far.
    """
    root = _root_of(base_site_url)
    netloc = urlparse(root).netloc.lower()
    seeds: List[str] = [root + '/sitemap.xml']

    # robots.txt may point at one or more sitemaps.
    robots = _fetch_text(root + '/robots.txt', fetch)
    for m in _SITEMAP_LINE_RE.finditer(robots or ''):
        sm = m.group(1).strip()
        if sm and sm not in seeds:
            seeds.append(sm)

    out: List[str] = []
    seen = set()
    nested_followed = 0
    i = 0
    while i < len(seeds):
        sm_url = seeds[i]
        i += 1
        text = _fetch_text(sm_url, fetch)
        if not text:
            continue
        locs = _LOC_RE.findall(text)
        for loc in locs:
            loc = loc.strip()
            lp = urlparse(loc)
            # A nested <sitemap> index: the loc itself ends in .xml → follow once.
            if loc.endswith('.xml') and nested_followed < 20:
                if loc not in seeds:
                    seeds.append(loc)
                    nested_followed += 1
                continue
            if lp.netloc.lower() != netloc:
                continue
            key = loc.rstrip('/')
            if key in seen:
                continue
            seen.add(key)
            out.append(loc)
            if len(out) >= max_urls:
                return out
    return out


def _fetch_text(url: str, fetch: Callable) -> str:
    """Call an injected fetcher and return its text/HTML, tolerating the project's
    tuple return shapes ((html, links) or (html, links, meta))."""
    try:
        res = fetch(url)
    except Exception:
        return ''
    if isinstance(res, tuple):
        return res[0] or '' if res else ''
    return res or ''


# ── 3. branch-page pick (chain → the requested city) ─────────────────────────

def slug_variants(city: str) -> List[str]:
    """Lower-case slug variants of a city name ('San Diego' → ['san-diego',
    'sandiego','san_diego','sandiego'])."""
    c = (city or '').strip().lower()
    if not c:
        return []
    base = re.sub(r'[^a-z0-9]+', ' ', c).strip()
    if not base:
        return []
    parts = base.split()
    variants = [
        '-'.join(parts),
        '_'.join(parts),
        ''.join(parts),
    ]
    # De-dup, keep order.
    seen = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


# Path shapes a chain uses for a city branch page. ``{slug}`` is substituted.
_BRANCH_PATH_TEMPLATES = (
    '/{slug}', '/locations/{slug}', '/location/{slug}', '/visit/{slug}',
    '/cities/{slug}', '/{slug}/', '/locations/{slug}/',
)


def pick_branch_url(base_site_url: str, city: str,
                    candidate_urls: Optional[List[str]] = None) -> str:
    """Pick the city BRANCH page URL for a chain venue, or ''.

    Preference order:
      1. an on-domain URL in ``candidate_urls`` (from the sitemap / Serper) whose
         path contains the city slug as a whole segment;
      2. a conventional branch path (``/<slug>``, ``/locations/<slug>`` …) built on
         the venue's own root (used as a seed to try fetching).
    The returned URL is always on the venue's own domain. Returns '' when no city
    is given.
    """
    slugs = slug_variants(city)
    if not slugs:
        return ''
    root = _root_of(base_site_url)
    netloc = urlparse(root).netloc.lower()

    # 1. A discovered URL whose path has the city slug as a segment.
    for url in candidate_urls or []:
        p = urlparse(url if '://' in url else 'https://' + url)
        if p.netloc.lower() != netloc:
            continue
        segs = [s for s in p.path.lower().strip('/').split('/') if s]
        if any(s in slugs for s in segs):
            return url

    # 2. A conventional branch path built on the root (a seed to fetch).
    slug = slugs[0]
    return root + _BRANCH_PATH_TEMPLATES[0].format(slug=slug)


def branch_url_seeds(base_site_url: str, city: str) -> List[str]:
    """All conventional branch-path seeds to try for a chain's city branch."""
    out: List[str] = []
    root = _root_of(base_site_url)
    for slug in slug_variants(city):
        for tmpl in _BRANCH_PATH_TEMPLATES:
            u = root + tmpl.format(slug=slug)
            if u not in out:
                out.append(u)
    return out


# ── 4. embedded-JSON extraction (data shipped inside the JS shell) ───────────

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE)
_LDJSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE)
_INITIAL_STATE_RE = re.compile(
    r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>',
    re.DOTALL)

# Keys whose string values are plausible exhibition/installation/room TITLES.
_TITLE_KEYS = ('name', 'title', 'headline', 'exhibitiontitle', 'label')
# JSON object "type" markers worth turning into a stop.
_EXHIBIT_TYPES = ('exhibitionevent', 'exhibition', 'visualartwork', 'event',
                  'creativework', 'artgallery', 'museum', 'place', 'room',
                  'installation')


def _walk_json(node, out: List[Tuple[str, str, str]], depth: int = 0):
    """Collect (title, url, jsonld_type) triples from a decoded JSON tree.

    Conservative: a title is a string value under a title-like key on an object
    that also looks like a content/place node (has a type/url/description), so
    navigation labels are not swept in. The object's ``@type``/``type`` is kept
    (lower-cased, '' when absent) so the allow-list in ``is_exhibit_stop`` can use
    a JSON-LD type as positive evidence that the item is an exhibit/work/room —
    [LOCAL-602 r3]."""
    if depth > 8:
        return
    if isinstance(node, dict):
        lowered = {str(k).lower(): v for k, v in node.items()}
        typ = str(lowered.get('@type') or lowered.get('type') or '').lower()
        title = ''
        for tk in _TITLE_KEYS:
            v = lowered.get(tk)
            if isinstance(v, str) and v.strip():
                title = v.strip()
                break
        url = ''
        for uk in ('url', 'detailurl', 'permalink', 'slug', 'href'):
            v = lowered.get(uk)
            if isinstance(v, str) and v.strip():
                url = v.strip()
                break
        looks_like_content = bool(
            typ in _EXHIBIT_TYPES or url or lowered.get('description')
            or lowered.get('startdate') or lowered.get('image'))
        if title and looks_like_content and 3 <= len(title) <= 120:
            out.append((title, url, typ))
        for v in node.values():
            _walk_json(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _walk_json(v, out, depth + 1)


def extract_embedded_json(html: str, base_url: str,
                          city: str = '') -> List[Dict]:
    """Extract candidate items from JSON embedded in a JS shell.

    Reads ``__NEXT_DATA__``, every ``application/ld+json`` block, and
    ``window.__INITIAL_STATE__``. Returns ``{'title','detail_url','source_url',
    'source'}`` dicts, de-duplicated by lower-cased title, order preserved. A
    relative URL is resolved against ``base_url``. Nothing is invented: only
    strings present in the shipped JSON become titles. ``city`` is advisory only
    (kept on each item for the no-other-city filter).
    """
    if not html:
        return []
    blobs: List[str] = []
    for m in _NEXT_DATA_RE.finditer(html):
        blobs.append(m.group(1))
    for m in _LDJSON_RE.finditer(html):
        blobs.append(m.group(1))
    for m in _INITIAL_STATE_RE.finditer(html):
        blobs.append(m.group(1))

    pairs: List[Tuple[str, str, str]] = []
    for blob in blobs:
        blob = blob.strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except Exception:
            # ld+json may hold several JSON objects concatenated; try array-wrap.
            try:
                data = json.loads('[' + blob + ']')
            except Exception:
                continue
        _walk_json(data, pairs)

    out: List[Dict] = []
    seen = set()
    for title, url, typ in pairs:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        detail_url = urljoin(base_url, url) if url else ''
        out.append({
            'title': title,
            'detail_url': detail_url,
            'source_url': detail_url or base_url,
            'source': 'embedded_json',
            'jsonld_type': typ,  # [LOCAL-602 r3] positive-ID evidence
            'city': city,
        })
    return out


# ── 5. Serper site:<domain> <city> ──────────────────────────────────────────

def serper_site_city(domain: str, city: str, serper: Callable,
                     max_results: int = 10) -> List[Dict]:
    """Run ``site:<domain> <city>`` and return the organic results as candidates.

    ``serper(query)`` returns the raw Serper JSON (dict). Each organic result
    becomes ``{'title','detail_url','source_url','snippet','source'}``. On-domain
    results only. Best-effort: any failure returns []. The snippet is kept so the
    caller can ground a stop in the search result's own text (no invention).
    """
    if not domain or not city or serper is None:
        return []
    query = f"site:{domain} {city}"
    try:
        data = serper(query) or {}
    except Exception:
        return []
    netloc = domain.lower().lstrip('www.')
    out: List[Dict] = []
    seen = set()
    for item in (data.get('organic') or [])[:max_results * 2]:
        link = (item.get('link') or '').strip()
        title = (item.get('title') or '').strip()
        snippet = (item.get('snippet') or '').strip()
        if not link or not title:
            continue
        host = urlparse(link).netloc.lower().lstrip('www.')
        if netloc not in host:
            continue
        key = link.rstrip('/')
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'title': title,
            'detail_url': link,
            'source_url': link,
            'snippet': snippet,
            'source': 'serper_site_city',
            'city': city,
        })
        if len(out) >= max_results:
            break
    return out


# ── 6. no-other-city filter ──────────────────────────────────────────────────

def filter_other_city(items: List[Dict], city: str,
                      other_cities: Optional[List[str]] = None) -> List[Dict]:
    """Drop items attested only on ANOTHER branch's page.

    An item is REMOVED when its title, detail_url or snippet names a DIFFERENT
    chain city (and not the requested ``city``). Items that mention the requested
    city, or no city at all, are KEPT. Deterministic string test; nothing fetched.

    This is the guard against a Boston tour describing a Chicago-only installation.
    """
    want = (city or '').strip().lower()
    others = [c for c in (other_cities or US_CHAIN_CITIES)
              if c.lower() != want]
    kept: List[Dict] = []
    for it in items or []:
        hay = ' '.join(str(it.get(k, '')) for k in
                       ('title', 'detail_url', 'source_url', 'snippet')).lower()
        mentions_other = any(_mentions_city(hay, oc) for oc in others)
        mentions_want = bool(want) and _mentions_city(hay, want)
        if mentions_other and not mentions_want:
            continue
        kept.append(it)
    return kept


def _mentions_city(haystack: str, city: str) -> bool:
    """Whole-token city match in a lower-cased haystack (handles 'san-diego',
    'san diego', 'sandiego')."""
    if not city:
        return False
    for v in slug_variants(city) + [city.lower()]:
        # Match the slug as a path segment or the words as whole tokens.
        if re.search(r'(?<![a-z0-9])' + re.escape(v) + r'(?![a-z0-9])', haystack):
            return True
    return False


# ── 7. stop identification — ALLOW-LIST (a stop must be positively an exhibit) ─
#
# [LOCAL-602 r3] r2 shipped a BLOCK-list: a page became a stop unless a path
# segment was in NON_STOP_SEGMENTS. A block-list can only ever reject the junk it
# has already seen, so the Meow Wolf live run shipped two pages whose junk words
# were simply not on the list:
#
#     Stop 1: Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out
#             /adulti-verse/santa-fe          (an event — "adulti-verse" unlisted)
#     Stop 2: Santa Fe City Guide: Top Attractions & Restaurants Near …
#             /destinations/santa-fe-city-guide   (a blog/guide — "destinations" unlisted)
#
# r3 inverts the rule: a page becomes a stop ONLY when it is POSITIVELY identified
# as an exhibit / installation / room / work. Everything that is not positively an
# exhibit is excluded by NOT MATCHING — events, "nights", guides, blogs, press,
# tickets and "destinations" fall away without having to be enumerated. The three
# kinds of positive evidence (any one suffices), all deterministic and local:
#
#   1. URL PATH SEGMENT — a path segment in STOP_PATH_SEGMENTS: /installations/,
#      /installation/, /exhibits/, /exhibit/, /exhibitions/, /exhibition/,
#      /rooms/, /room/, /artworks/, /artwork/, /works/, /collection/,
#      /collections/, /galleries/, /gallery/, /art/, /piece/, /pieces/.
#   2. JSON-LD @type — the item's ``jsonld_type`` (set by extract_embedded_json)
#      is one of EXHIBIT_JSONLD_TYPES: ExhibitionEvent, VisualArtwork, Artwork,
#      Installation, CreativeWork, or Place (a Place is accepted only when it is
#      ON the venue's own domain, i.e. a room within the venue, never an external
#      "place").
#   3. HEADING PATTERN — the item carries ``from_exhibit_heading=True`` (or an
#      ``exhibit_heading`` string), meaning it was lifted from the branch page's
#      own exhibit-list heading section by the caller.
#
# An item that carries NO URL and no type/heading evidence is still KEPT and left
# to be judged elsewhere (the r2 contract: a candidate with no URL is not dropped
# by this gate). The block-list NON_STOP_SEGMENTS / is_stop_url are retained below
# so the deterministic path-only rejection the r2 suite pins keeps working; the
# allow-list simply runs FIRST and is the authority on what becomes a stop.

# Path segments that POSITIVELY mark a page as an exhibit / installation / room /
# work. Compared case-insensitively; '-'/'_' normalised. Any ONE such segment
# anywhere in the path is sufficient positive evidence.
STOP_PATH_SEGMENTS = frozenset({
    'installations', 'installation', 'exhibits', 'exhibit', 'exhibitions',
    'exhibition', 'rooms', 'room', 'artworks', 'artwork', 'works', 'work',
    'collection', 'collections', 'galleries', 'gallery', 'art', 'artwork',
    'piece', 'pieces', 'object', 'objects', 'exhibitionevent',
})

# JSON-LD @type values that POSITIVELY mark an item as an exhibit / work / room.
# 'place' is conditional (venue-domain only) and handled in is_exhibit_stop.
EXHIBIT_JSONLD_TYPES = frozenset({
    'exhibitionevent', 'exhibition', 'visualartwork', 'artwork', 'installation',
    'creativework', 'collection', 'exhibit',
})
# A Place/Room JSON-LD type is positive ONLY when the URL is on the venue domain.
_PLACE_JSONLD_TYPES = frozenset({'place', 'room', 'touristattraction'})

# Path segments that mark a transactional / navigational / informational page
# rather than a thing-to-see. Retained for the deterministic path-only rejection
# the r2 suite pins (is_stop_url). Compared case-insensitively; '-' and '_' are
# normalised so 'gift-cards' and 'gift_cards' both match 'gift-cards'.
NON_STOP_SEGMENTS = frozenset({
    'tickets', 'ticket', 'gift-cards', 'gift-card', 'giftcard', 'giftcards',
    'shop', 'store', 'merch', 'merchandise', 'membership', 'member', 'members',
    'events', 'event', 'faq', 'faqs', 'locations', 'location', 'visit',
    'plan-your-visit', 'directions', 'hours', 'contact', 'contact-us', 'about',
    'about-us', 'cart', 'checkout', 'account', 'login', 'signin', 'sign-in',
    'register', 'careers', 'jobs', 'press', 'media', 'blog', 'news',
    'newsletter', 'privacy', 'terms', 'policy', 'policies', 'search', 'donate',
    'give', 'giving', 'support', 'book', 'booking', 'buy', 'rentals', 'rental',
    'private-events', 'groups', 'group', 'birthday', 'birthdays', 'parties',
    'party', 'faq-page', 'sitemap', 'home', 'index', 'destinations',
    'destination', 'adulti-verse', 'nights', 'night',
})

# "location(s)" are structural wrappers around a city slug (``/locations/boston``);
# a path made only of these plus the city is the branch index, never a stop.
_BRANCH_WRAPPER_SEGMENTS = frozenset({'locations', 'location', 'cities', 'city'})


def _path_segments(url: str) -> List[str]:
    """Lower-cased, '-'/'_'-normalised path segments of a URL (no query/fragment)."""
    if not url:
        return []
    u = url if '://' in url else 'https://' + url
    path = urlparse(u).path or ''
    out = []
    for seg in path.split('/'):
        seg = seg.strip().lower()
        if not seg:
            continue
        out.append(seg.replace('_', '-'))
    return out


def _url_has_stop_segment(url: str) -> bool:
    """True when any path segment of ``url`` is in STOP_PATH_SEGMENTS."""
    return any(seg in STOP_PATH_SEGMENTS for seg in _path_segments(url))


EXHIBIT_HEADING_RE = re.compile(
    r'\b(installations?|exhibit(?:ion)?s?|current\s+(?:shows?|exhibit(?:ion)?s?)|'
    r'on\s+view|galler(?:y|ies)|rooms?|artworks?|collection)\b', re.IGNORECASE)


def is_exhibit_heading(text: str) -> bool:
    """True when a branch-page section heading announces an exhibit list.

    Lets the caller mark items it lifted from the venue's own exhibit-list
    heading (``Installations``, ``Current Exhibitions``, ``On View``, ``Rooms``…)
    as positively identified. Deterministic, no fetch.
    """
    return bool(text and EXHIBIT_HEADING_RE.search(str(text)))


def is_exhibit_stop(item: Dict, city: str = '', venue_domain: str = '') -> bool:
    """True when ``item`` is POSITIVELY identified as an exhibit / work / room.

    [LOCAL-602 r3] ALLOW-LIST. An item is a stop only when at least one positive
    signal is present:

      * its ``detail_url``/``source_url`` contains a STOP_PATH_SEGMENTS segment
        (``/installations/…``, ``/exhibitions/…``, ``/rooms/…``, …); OR
      * its ``jsonld_type`` is an EXHIBIT_JSONLD_TYPES value (ExhibitionEvent,
        VisualArtwork, Installation, …), or a Place/Room type on the venue's own
        domain; OR
      * it carries ``from_exhibit_heading`` truthy, or an ``exhibit_heading``
        string that ``is_exhibit_heading`` recognises.

    An item with NO URL and no type/heading evidence is KEPT (returns True) so a
    candidate carrying no URL is judged by other means — the r2 contract. An item
    that HAS a URL but matches no positive signal is NOT a stop (returns False):
    this is what rejects the Meow Wolf ``/adulti-verse/santa-fe`` event and
    ``/destinations/santa-fe-city-guide`` guide that a block-list let through.
    """
    url = (item.get('detail_url') or item.get('source_url') or '').strip()

    # 1. URL path segment is the strongest, cheapest positive signal.
    if url and _url_has_stop_segment(url):
        return True

    # 2. JSON-LD @type positive evidence.
    typ = str(item.get('jsonld_type') or '').strip().lower()
    if typ:
        if typ in EXHIBIT_JSONLD_TYPES:
            return True
        if typ in _PLACE_JSONLD_TYPES:
            # A Place/Room is an exhibit only when it is ON the venue's domain.
            if venue_domain:
                host = urlparse(url if '://' in url else 'https://' + url).netloc
                if venue_domain.lower().lstrip('www.') in host.lower().lstrip('www.'):
                    return True
            elif url:  # no venue domain supplied → on-domain by construction
                return True

    # 3. Heading-pattern evidence from the branch page's own exhibit list.
    if item.get('from_exhibit_heading') or is_exhibit_heading(item.get('exhibit_heading', '')):
        return True

    # No URL at all and no other evidence → judged elsewhere (r2 contract: keep).
    if not url:
        return True

    # Has a URL but no positive exhibit evidence → not a stop.
    return False


def is_stop_url(url: str, city: str = '') -> bool:
    """Deterministic path-only rejection (retained from r2 for the r2 suite).

    Returns False for:
      * the bare domain / home / index page (no meaningful path);
      * any URL with a NON_STOP_SEGMENTS segment (tickets, gift-cards, shop,
        membership, events, faq, visit, contact, about, …);
      * the city BRANCH INDEX page — a path whose only segments are branch
        wrappers (locations/location/cities/city) and/or the requested city slug.

    Everything else (``/installations/boston/flex``, ``/exhibitions/mirror-room``)
    is allowed through. An empty/missing URL returns True so a candidate that
    carries no URL is judged by other means, not dropped here. NOTE: this is the
    r2 block-list; r3's authority on what becomes a stop is ``is_exhibit_stop`` /
    ``reject_non_stop_urls`` (allow-list), which runs first in the live packer.
    """
    if not url or not str(url).strip():
        return True
    segs = _path_segments(url)
    if not segs:
        return False  # bare domain / home page
    if any(seg in NON_STOP_SEGMENTS for seg in segs):
        return False
    # Branch index: nothing left once wrappers and the city slug are removed.
    city_slugs = set(slug_variants(city)) if city else set()
    residual = [s for s in segs
                if s not in _BRANCH_WRAPPER_SEGMENTS and s not in city_slugs]
    if not residual:
        return False
    return True


def reject_non_stop_urls(items: List[Dict], city: str = '',
                         venue_domain: str = '') -> List[Dict]:
    """Keep only candidates POSITIVELY identified as exhibits — [LOCAL-602 r3].

    ALLOW-LIST: an item survives only when ``is_exhibit_stop`` finds positive
    evidence (exhibit URL path segment, exhibit JSON-LD type, or an exhibit-list
    heading). Items with no URL and no type/heading evidence are kept (judged
    elsewhere — the r2 contract). Order preserved; deterministic; nothing fetched.

    This replaces the r2 block-list behaviour: a page is dropped because it was
    never shown to be an exhibit, NOT because its junk word happened to be on a
    list. ``venue_domain`` scopes the conditional Place/Room JSON-LD type.
    """
    kept: List[Dict] = []
    for it in items or []:
        if is_exhibit_stop(it, city, venue_domain):
            kept.append(it)
    return kept


# ── default Serper caller (project key SERP_API_KEY) ─────────────────────────

def default_serper(query: str) -> Dict:
    """Run a Serper.dev search for ``query`` and return the raw JSON dict.

    Uses the project's ``SERP_API_KEY`` env var (NOT ``SERPER_API_KEY`` — see
    preflight.py). Returns {} when no key is set or the call fails, so callers
    degrade gracefully. Costs ~$0.001 per call; only invoked on the JS/chain
    fallback path when cheaper routes found nothing.
    """
    import os
    key = os.environ.get('SERP_API_KEY')
    if not key:
        return {}
    try:
        import json as _json
        import urllib.request
        data = _json.dumps({'q': query, 'num': 10}).encode('utf-8')
        req = urllib.request.Request(
            'https://google.serper.dev/search', data=data,
            headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
            method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read().decode('utf-8', 'ignore')) or {}
    except Exception:
        return {}
