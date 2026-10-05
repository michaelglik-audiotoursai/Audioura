#!/usr/bin/env python3
"""exhibition_discovery.py — LOCAL-580: read a venue's REAL current exhibitions.

An "exhibition museum" (e.g. Griffin Museum of Photography) has no catalogued
collection in Wikidata — SPARQL returns 0 works. Its real content is the shows
it is currently running, published on its own site as a list of headings, each
LINKING to that show's own detail page (``/show/<slug>/``, ``/exhibition/<slug>/``,
or any per-item path on the venue's domain).

The old plaintext extractor (story_miner.extract_canonical_titles) ran on the
page's visible text and could not tell an exhibition heading from a FlipBook
viewer's button label — it returned "Toggle Fullscreen", "Next Page",
"Download PDF File", "Zoom Out", ... as "canonical titles" and missed every
real show.

This module extracts exhibitions STRUCTURALLY (D476 — no hardcoded list of show
names). The signal is the DOM shape, not the words:

    a heading (<h1>-<h4>) whose text is, or contains, a link to a detail page
    on the venue's own domain

and the rejections are UI/structure, not a blocklist of titles:

    * text inside an interactive widget — <button>, role="button",
      elements carrying aria-label, or any ancestor flagged as a
      viewer/flipbook/slider/toolbar/carousel control
    * text inside <nav> or <footer> (or elements whose role is navigation)
    * a heading that does not link anywhere, or links off the venue's domain

The result is a list of ``{'title', 'detail_url'}`` dicts, de-duplicated and in
document order. It is a pure function: HTML in, exhibitions out, no network.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

__all__ = ['extract_current_exhibitions']


# Headings that carry an exhibition title on a listing page.
_HEADING_TAGS = ('h1', 'h2', 'h3', 'h4')

# Ancestor tags/roles that mean "this text is UI chrome, not content".
# These are STRUCTURAL (how the browser treats the element), not a list of
# specific widget names, so a new viewer skin cannot slip titles past us.
_INTERACTIVE_TAGS = frozenset({'button', 'nav', 'footer', 'select', 'option',
                               'label', 'form', 'textarea', 'input'})
_INTERACTIVE_ROLES = frozenset({'button', 'navigation', 'toolbar', 'menu',
                                'menubar', 'menuitem', 'tab', 'tablist',
                                'slider', 'scrollbar', 'search', 'contentinfo',
                                'banner', 'dialog'})

# Class/id fragments that mark a viewer / flipbook / slider / carousel wrapper.
# Matched as substrings against an element's class and id. This is about the
# WIDGET KIND (an embedded control surface), not about any show's name.
_WIDGET_HINT_RE = re.compile(
    r'(?:flipbook|df-book|df-ui|dflip|3d-?flip|pageflip|turn-?js|'
    r'viewer|lightbox|carousel|slider|swiper|slick|owl-|'
    r'toolbar|controls?|nav(?:bar|igation)?|menu|footer|header|'
    r'cookie|consent|share|social|breadcrumb|pagination|pager|'
    r'widget|modal|popup|overlay|offcanvas|skip-link)',
    re.IGNORECASE,
)

# A detail-page path looks like a per-item page on the venue's own site.
# Generic across venues: /show/, /exhibition(s)/, /exhibit/, /on-view/,
# /whats-on/, /event(s)/, /display/ — plus any path that has a non-trivial
# slug segment after one of these roots. We DO NOT hardcode show names.
_DETAIL_PATH_RE = re.compile(
    r'/(?:show|exhibition|exhibitions|exhibit|exhibits|on-view|onview|'
    r'whats-on|whatson|display|installation|event|events|project|projects)/'
    r'[^/?#]+',
    re.IGNORECASE,
)

# A heading whose text is ONLY one of these generic listing-page labels is not
# itself an exhibition even if structural checks pass. These are page furniture
# that may wrap or sit beside the real list. Compared case-insensitively on the
# whole, trimmed heading text — NOT a substring blocklist of show words.
_GENERIC_HEADING_LABELS = frozenset({
    'current exhibitions', 'exhibitions', 'past exhibitions',
    'upcoming exhibitions', 'on view', 'whats on', "what's on",
    'current', 'upcoming', 'archive', 'exhibition catalog',
    'exhibition catalogue', 'galleries', 'virtual galleries',
    'winchester galleries', 'footer', 'header', 'menu', 'home',
})


def _collapse_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _same_domain(href_url: str, base_url: str) -> bool:
    """True when href resolves to the venue's own registrable domain."""
    try:
        h = urlparse(urljoin(base_url, href_url)).netloc.lower()
        b = urlparse(base_url).netloc.lower()
    except Exception:
        return False
    if not h or not b:
        return False
    h = h.split(':')[0].lstrip('www.')
    b = b.split(':')[0].lstrip('www.')
    # Accept exact host or a shared registrable tail (sub.griffinmuseum.org).
    return h == b or h.endswith('.' + b) or b.endswith('.' + h)


# ─── BeautifulSoup implementation (preferred) ────────────────────────────────

def _extract_with_bs4(html: str, base_url: str) -> Optional[List[Dict]]:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    def _in_interactive_context(node) -> bool:
        """Walk ancestors: is this heading inside a button/nav/footer/viewer?"""
        cur = node
        while cur is not None and getattr(cur, 'name', None):
            name = (cur.name or '').lower()
            if name in _INTERACTIVE_TAGS:
                return True
            attrs = cur.attrs or {}
            role = str(attrs.get('role', '')).lower()
            if role in _INTERACTIVE_ROLES:
                return True
            if attrs.get('aria-label') and name not in _HEADING_TAGS:
                # An aria-label on a non-heading ancestor is a control surface.
                return True
            cls = ' '.join(attrs.get('class', []) if isinstance(attrs.get('class'), list)
                           else [str(attrs.get('class', ''))])
            ident = str(attrs.get('id', ''))
            if _WIDGET_HINT_RE.search(cls) or _WIDGET_HINT_RE.search(ident):
                return True
            cur = cur.parent
        return False

    out: List[Dict] = []
    seen = set()
    for heading in soup.find_all(_HEADING_TAGS):
        if _in_interactive_context(heading):
            continue
        # The heading must itself be a link, or directly contain one, to a
        # per-item detail page on the venue's domain.
        anchor = heading if getattr(heading, 'name', '') == 'a' else heading.find('a', href=True)
        if anchor is None or not anchor.get('href'):
            continue
        # The anchor must not itself be a control.
        if _in_interactive_context(anchor):
            continue
        href = anchor.get('href', '').strip()
        if not href or href.startswith('#') or href.lower().startswith('javascript:'):
            continue
        if not _same_domain(href, base_url):
            continue
        resolved = urljoin(base_url, href)
        if not _DETAIL_PATH_RE.search(urlparse(resolved).path):
            continue
        title = _collapse_ws(unescape(heading.get_text(' ', strip=True)))
        if not title or len(title) < 2:
            continue
        if title.lower() in _GENERIC_HEADING_LABELS:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({'title': title, 'detail_url': resolved})
    return out


# ─── Regex fallback (no bs4) ─────────────────────────────────────────────────

_HEADING_BLOCK_RE = re.compile(
    r'<(h[1-4])\b[^>]*>(.*?)</\1>', re.DOTALL | re.IGNORECASE
)
_ANCHOR_RE = re.compile(
    r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r'<[^>]+>')


def _strip_tags(fragment: str) -> str:
    return _collapse_ws(unescape(_TAG_RE.sub(' ', fragment or '')))


def _extract_with_regex(html: str, base_url: str) -> List[Dict]:
    # Drop HTML comments first — a commented-out tag like "<h2>" would otherwise
    # corrupt greedy/non-greedy block matching below.
    scrubbed = re.sub(r'<!--.*?-->', ' ', html, flags=re.DOTALL)
    # Crudely blank out <nav>, <footer>, <button> and obvious widget wrappers so
    # headings inside them are never seen. Best-effort; bs4 is the real path.
    scrubbed = re.sub(r'<(nav|footer|button|form|select)\b.*?</\1>', ' ',
                      scrubbed, flags=re.DOTALL | re.IGNORECASE)
    out: List[Dict] = []
    seen = set()
    for _tag, inner in _HEADING_BLOCK_RE.findall(scrubbed):
        if 'aria-label' in inner.lower():
            continue
        m = _ANCHOR_RE.search(inner)
        if not m:
            continue
        href, anchor_inner = m.group(1).strip(), m.group(2)
        if not href or href.startswith('#') or href.lower().startswith('javascript:'):
            continue
        if not _same_domain(href, base_url):
            continue
        resolved = urljoin(base_url, href)
        if not _DETAIL_PATH_RE.search(urlparse(resolved).path):
            continue
        title = _strip_tags(inner) or _strip_tags(anchor_inner)
        if not title or len(title) < 2 or title.lower() in _GENERIC_HEADING_LABELS:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({'title': title, 'detail_url': resolved})
    return out


def extract_current_exhibitions(html: str, base_url: str) -> List[Dict]:
    """Return the venue's current exhibitions from a listing page's HTML.

    Args:
        html: raw HTML of the venue's current-exhibitions / on-view page.
        base_url: the URL that HTML was fetched from (used to resolve relative
            links and to decide which links are on the venue's own domain).

    Returns:
        A list of ``{'title': str, 'detail_url': str}`` in document order, one
        per exhibition, de-duplicated by title. Empty when the page has no
        structural exhibition links (the caller then falls back to other paths).
    """
    if not html or not base_url:
        return []
    result = _extract_with_bs4(html, base_url)
    if result is None:  # bs4 unavailable
        result = _extract_with_regex(html, base_url)
    return result
