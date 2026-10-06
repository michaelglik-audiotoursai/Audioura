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

__all__ = ['extract_current_exhibitions', 'is_chrome_title', 'reject_chrome_titles']


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
# Matched per class/id TOKEN (tokens split on -, _, whitespace) so a decorative
# page class like "header-image" is not mistaken for a navigation header. This
# is about the WIDGET KIND (an embedded control surface), not any show's name.
#
# Two tiers:
#   * exact widget TOKENS — a standalone class token that names a control
#     surface (toolbar, controls, carousel, slider, lightbox, viewer, flipbook,
#     dropdown, modal, popup, overlay, offcanvas, pagination, pager, breadcrumb).
#     Bare 'nav'/'menu'/'header'/'footer' are deliberately NOT here — those are
#     handled by the <nav>/<footer> structural tags and ARIA roles, so that a
#     decorative "header-image" column does not suppress real content.
#   * compound widget prefixes — vendor viewer/flipbook class families
#     (flipbook, dflip, df-ui, df-book, pageflip, turnjs, swiper, slick, owl).
_WIDGET_TOKENS = frozenset({
    'toolbar', 'control', 'controls', 'carousel', 'slider', 'lightbox',
    'viewer', 'flipbook', 'dropdown', 'modal', 'popup', 'overlay',
    'offcanvas', 'pagination', 'pager', 'breadcrumb', 'breadcrumbs',
    'navbar', 'navigation', 'megamenu', 'submenu',
})
_WIDGET_COMPOUND_RE = re.compile(
    r'(?:flipbook|dflip|df-?ui|df-?book|pageflip|turn-?js|swiper|slick|owl-)',
    re.IGNORECASE,
)
_TOKEN_SPLIT_RE = re.compile(r'[\s\-_]+')


def _tokens_hit_widget(attrs: dict) -> bool:
    """True when an element's class/id names a control-surface widget."""
    raw_cls = attrs.get('class', [])
    if not isinstance(raw_cls, list):
        raw_cls = [str(raw_cls)]
    blob = ' '.join(raw_cls) + ' ' + str(attrs.get('id', ''))
    if _WIDGET_COMPOUND_RE.search(blob):
        return True
    for tok in _TOKEN_SPLIT_RE.split(blob.lower()):
        if tok in _WIDGET_TOKENS:
            return True
    return False

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


# ─── Title-level chrome rejection (LOCAL-583) ────────────────────────────────
# The DOM-structural rejection above needs HTML. But the venue_corpus cache
# stores canonical TITLES as bare strings — and the old plaintext extractor
# (story_miner.extract_canonical_titles) wrote site chrome into them: "Our Team",
# "Calls For Entry", "Terms Conditions", "Griffin Museum Board Of Directors 2",
# "Membership Levels" … These are page furniture (navigation / account /
# membership / legal / institutional-governance / support labels), the string
# residue of the SAME <nav>/<footer>/widget structure the DOM pass rejects.
#
# This is a vocabulary of PAGE FURNITURE, deliberately NOT a blocklist of show
# names. An exhibition title names a show ("Intertidal : Field Notes",
# "Earth, Wind & Fire", "TLC"); it does not read like a site-chrome label.
# Matching is on whole-title generic labels and on chrome LEXICON tokens, so a
# real show whose title happens to contain an ordinary word is not caught.

# A title that is ONLY one of these generic labels is page furniture, never a
# show. Whole-title match (case-insensitive, punctuation-insensitive), not a
# substring blocklist. Extends _GENERIC_HEADING_LABELS with the account /
# membership / legal / governance / support labels seen in the cache residue.
_CHROME_EXACT_LABELS = frozenset({
    'our team', 'terms conditions', 'terms and conditions', 'privacy policy',
    'membership levels', 'membership account', 'members bulletin',
    'member bulletin', 'calls for entry', 'call for entry', 'function rentals',
    'leave a legacy', 'your support matters', 'portfolio development',
    'exhibition closed', 'exhibition archive', 'contact us', 'about us',
    'hours admission', 'hours and admission', 'donate', 'support us',
    'newsletter', 'sign up', 'log in', 'login', 'my account', 'cart',
    'board of directors', 'staff', 'press', 'shop', 'store',
    # [LOCAL-589] Plurals of existing labels that escaped in the field (tour 394):
    # the Griffin listing published "Exhibitions Closed" / "Exhibitions Archive"
    # (plural), while LOCAL-583 only carried the singular forms.
    'exhibitions closed', 'exhibitions archive', 'closed exhibitions',
    'past exhibitions archive',
})

# [LOCAL-589] Institutional-SECTION tokens: when one of these is the LAST word of
# a venue-branded title, the title names a SECTION of the institution (its
# archive, its salon, its travel programme, its rentals desk, its board
# bulletin) — not a show. These are a strict subset of _CHROME_TOKENS; the extra
# power is only used by the terminal-section rule in is_chrome_title, which also
# requires a venue-name word to be present, so a real show that merely ends in
# an ordinary word is never caught. ("Arthur Griffin Archive" → founder name
# 'Arthur' + venue word 'Griffin' + section token 'archive'.)
_CHROME_SECTION_TERMINAL = frozenset({
    'archive', 'archives', 'salon', 'travel', 'rentals', 'rental',
    'bulletin', 'directors', 'governance', 'bylaws',
})

# Chrome LEXICON tokens. A title whose words are DOMINATED by these (and carry no
# distinctive content word) is a navigation / account / membership / legal /
# governance label, not a show. These are site-furniture words, generic across
# museum sites — not any specific exhibition's name.
_CHROME_TOKENS = frozenset({
    'membership', 'member', 'members', 'account', 'login', 'signup',
    'subscribe', 'newsletter', 'donate', 'donation', 'legacy', 'bequest',
    'rentals', 'rental', 'rent', 'directors', 'director', 'board', 'trustees',
    'trustee', 'staff', 'team', 'volunteer', 'volunteers', 'policy', 'policies',
    'terms', 'conditions', 'privacy', 'copyright', 'sitemap', 'faq', 'faqs',
    'contact', 'about', 'press', 'media', 'careers', 'jobs', 'support',
    'sponsor', 'sponsors', 'sponsorship', 'cart', 'checkout', 'shop', 'store',
    'tickets', 'admission', 'hours', 'directions', 'parking', 'accessibility',
    'calls', 'entry', 'entries', 'submission', 'submissions', 'review',
    'reviews', 'scheduled', 'bulletin', 'salon', 'travel', 'archive',
    'governance', 'bylaws', 'rentals',
    # [LOCAL-589] page-state / listing-furniture words. "Closed" is a status
    # label the Griffin site renders beside its exhibitions list ("Exhibitions
    # Closed"); paired with the generic listing word "exhibitions" it is pure
    # furniture, never a show name. "archives" is the plural section token.
    'closed', 'archives',
})

# Words that mark a title as PAGE FURNITURE even alongside institutional nouns —
# the question-form and marketing-slogan residue ("When Are The … Scheduled",
# "Your Support Matters").
_CHROME_FUNCTION_WORDS = frozenset({
    'when', 'how', 'why', 'where', 'what', 'who', 'are', 'is', 'do', 'does',
    'your', 'our', 'my', 'the', 'a', 'an', 'to', 'for', 'of', 'and', 'in',
    'on', 'at', 'be', 'this', 'that', 'matters', 'scheduled',
})

_CHROME_PUNCT_RE = re.compile(r'[^\w\s]')


def _chrome_norm(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for whole-title match."""
    t = _CHROME_PUNCT_RE.sub(' ', (title or '').lower())
    return ' '.join(t.split())


def is_chrome_title(title: str, venue_name: str = "") -> bool:
    """True when a bare title string is site chrome, not an exhibition.

    Pure function, no network, no HTML. Rejects:
      * an empty / 1-char title,
      * a whole-title generic label (nav/account/membership/legal/governance),
      * a title whose content words are ALL chrome-lexicon, venue-name, or
        function words (e.g. "Membership Levels", "Our Team",
        "Griffin Museum Board Of Directors 2", "Griffin Travel").

    `venue_name`, when supplied, lets the venue's own name words count as
    non-distinctive filler, so a venue-branded chrome label ("Griffin Travel")
    is caught while a venue-branded SHOW carrying a further distinctive word is
    not.

    Does NOT reject a title that carries a distinctive content word — a real
    show name ("Intertidal Field Notes", "Earth Wind Fire", "Lua Kobayashi")
    survives, so this is safe to run over a mixed canonical union.
    """
    norm = _chrome_norm(title)
    if not norm or len(norm) < 2:
        return True
    if norm in _GENERIC_HEADING_LABELS or norm in _CHROME_EXACT_LABELS:
        return True
    words = norm.split()
    # FAQ / help-text residue: a title that READS AS A QUESTION — it begins with
    # an interrogative word ("When Are The Member Portfolio Reviews Scheduled",
    # "How Do I Join") — is page help text, not a show title. Structural (opening
    # function word), not a blocklist of question topics.
    _INTERROGATIVES = {'when', 'how', 'why', 'where', 'what', 'who', 'can', 'do',
                       'does', 'is', 'are', 'should', 'will'}
    if len(words) >= 3 and words[0] in _INTERROGATIVES:
        return True
    _venue_words = set(_chrome_norm(venue_name).split()) if venue_name else set()
    # [LOCAL-589] Terminal institutional-SECTION rule. A venue-branded title whose
    # LAST word names an institutional section (archive / salon / travel /
    # rentals / bulletin / directors / governance) is a section of the venue, not
    # a show — "Arthur Griffin Archive", "Griffin Salon", "Griffin Travel". The
    # rule fires only when the title also carries a venue-name word, so the venue
    # is clearly its subject; a real show that merely ends in an ordinary word is
    # untouched (and none of the published Griffin shows end in a section token).
    # It catches the founder-name case ("Arthur Griffin Archive") that the
    # all-words-are-chrome loop below misses, because "Arthur" reads as a
    # distinctive content word there.
    if (len(words) >= 2
            and words[-1] in _CHROME_SECTION_TERMINAL
            and _venue_words
            and any(w in _venue_words for w in words[:-1])):
        return True
    # A title is chrome when EVERY word is a chrome-lexicon token, a venue-name
    # word, or a function/filler word AND at least one chrome-lexicon token is
    # present. Numbers alone (e.g. a year) count as filler, not distinctive
    # content, so "Membership Levels 2026" is still chrome.
    has_chrome_token = False
    for w in words:
        if w in _CHROME_TOKENS:
            has_chrome_token = True
            continue
        if w in _CHROME_FUNCTION_WORDS:
            continue
        if w in _venue_words:
            continue
        if w.isdigit():
            continue
        # A distinctive content word → not chrome.
        return False
    return has_chrome_token


def reject_chrome_titles(titles, venue_name: str = ""):
    """Filter site chrome out of a canonical-title union.

    Accepts any iterable of strings (set, list). Returns a NEW list in input
    order with chrome removed and blanks dropped. `venue_name` (optional) lets
    venue-branded chrome labels be caught. Used before writing the
    canonical-title union to venue_corpus (LOCAL-583 D2) so the cache can never
    again store "Our Team" / "Calls For Entry" / "Terms Conditions" as a work.
    """
    out = []
    seen = set()
    for t in (titles or []):
        if not isinstance(t, str):
            continue
        s = t.strip()
        if not s or is_chrome_title(s, venue_name):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


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
            # Page-root elements are never "widgets" — their classes describe the
            # whole page (e.g. body class "header-image full-width-content") and
            # must not be read as a control surface.
            if name in ('html', 'body'):
                cur = cur.parent
                continue
            if name in _INTERACTIVE_TAGS:
                return True
            attrs = cur.attrs or {}
            role = str(attrs.get('role', '')).lower()
            if role in _INTERACTIVE_ROLES:
                return True
            if _tokens_hit_widget(attrs):
                return True
            cur = cur.parent
        return False

    def _detail_href(anchor) -> str:
        """Return a resolved on-domain detail URL for an anchor, or ''."""
        if anchor is None:
            return ''
        href = (anchor.get('href') or '').strip()
        if not href or href.startswith('#') or href.lower().startswith('javascript:'):
            return ''
        if _in_interactive_context(anchor):
            return ''
        if not _same_domain(href, base_url):
            return ''
        resolved = urljoin(base_url, href)
        if not _DETAIL_PATH_RE.search(urlparse(resolved).path):
            return ''
        return resolved

    def _find_detail_url_for(heading) -> str:
        """A heading titles an exhibition when it is LINKED to a detail page.

        The link may be, in order of preference:
          1. the heading itself (<h2><a> or <a><h2>),
          2. a link INSIDE the heading,
          3. an ANCESTOR link wrapping the heading (card-level <a> — the shape
             Griffin uses: <a class="new-show-item" href="/show/..."><h2>..</h2>),
          4. a link elsewhere in the nearest enclosing card/article.
        """
        # 1 & 2: heading is / contains an anchor.
        if getattr(heading, 'name', '') == 'a':
            u = _detail_href(heading)
            if u:
                return u
        inner = heading.find('a', href=True)
        u = _detail_href(inner)
        if u:
            return u
        # 3: an ancestor anchor (card link wrapping the heading). This is the
        # shape Griffin uses: <a class="new-show-item" href="/show/..."><h2>..</h2>.
        # We deliberately do NOT fall back to "any link inside the nearest card":
        # a layout heading that merely sits in the same container as a show card
        # (e.g. "Satellite Galleries") is not itself a show. The heading must be
        # INSIDE the show's own link.
        cur = heading.parent
        hops = 0
        while cur is not None and getattr(cur, 'name', None) and hops < 6:
            if cur.name == 'a':
                u = _detail_href(cur)
                if u:
                    return u
            cur = cur.parent
            hops += 1
        return ''

    out: List[Dict] = []
    seen = set()
    for heading in soup.find_all(_HEADING_TAGS):
        if _in_interactive_context(heading):
            continue
        resolved = _find_detail_url_for(heading)
        if not resolved:
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
