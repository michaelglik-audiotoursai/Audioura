"""junk_title_guard.py — [LOCAL-632] Reject web-page / CMS titles at candidate intake.

A tour stop title must be a THING A LISTENER LOOKS AT — an artwork, an on-view
exhibition, a named space. It must never be the raw ``<title>`` or a navigation
heading scraped off the venue's website.

Albertina (tour 497, Kiro 2/10): both stops were web-page titles —
"The ALBERTINA Museum Vienna" and "Profile « The ALBERTINA Museum Vienna". They
reached the tour because the site-first / JS-fallback candidate builders take
their names from scraped headings and the venue's page ``<title>``, and nothing
rejected a title that is plainly page chrome: a breadcrumb joined by ``«`` / ``|``
/ `` - ``, a section label ("Profile", "Home", "Visit", "Tickets"), or the venue's
own name.

This module provides ONE pure predicate, ``is_junk_page_title``, applied at every
candidate-intake chokepoint (``exhibition_site_first.build_site_first_candidates``
and its JS fallback, and the museum documented path). It subsumes the task's
explicit rule set:

    a stop title that contains the venue name, "Profile", "«", "|", " - ",
    "Home", "Visit", "Tickets", or reads as a page or section title is never a
    stop.

The venue-name case delegates to ``room_candidate_guard.is_venue_itself_title``
(already the LOCAL-626 authority) so the two guards never diverge; everything else
is handled here.

Pure: no network, no LLM, no I/O. Deterministic. Kept conservative so a real work
whose title merely *contains* a common word ("The Visit", a painting; "A Home in
the Country") is NOT rejected — a title is junk only when a page-chrome SEPARATOR
is present, or when the whole title IS a bare section/navigation label, or when it
is the venue itself.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["is_junk_page_title", "filter_out_junk_titles"]

# ─────────────────────────────────────────────────────────────────────────────
# 1. Page-chrome SEPARATORS. A venue's page <title> is almost always a breadcrumb
#    joined by one of these: "Profile « The ALBERTINA Museum Vienna",
#    "Exhibitions | Rijksmuseum", "Home - The Courtauld". A genuine artwork title
#    does not contain these glue characters, so their mere PRESENCE marks chrome.
#    "«"/"»" (guillemets as breadcrumb glue), "|" (pipe), " - " / " – " / " — "
#    (spaced dash joiner — spaced on BOTH sides so a hyphenated work title
#    "Marie-Antoinette" or an en-dash date range inside a work title is safe).
# ─────────────────────────────────────────────────────────────────────────────
_CHROME_SEPARATOR_RE = re.compile(
    r"[«»]|\|"              # guillemet or pipe anywhere
    r"|(?:\s[-–—]\s)"       # a dash with a space on BOTH sides (title joiner)
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Bare SECTION / NAVIGATION labels. When the WHOLE title (after a leading
#    article) is one of these, it is a nav item, not a work. Matched as the entire
#    title so a work called "The Kiss" is never touched by "kiss"; these are the
#    exact page-furniture words the task names plus the common siblings that ride
#    the same nav bar.
# ─────────────────────────────────────────────────────────────────────────────
_SECTION_LABELS = frozenset({
    # task-named
    "profile", "home", "visit", "tickets", "ticket",
    # common nav/section siblings that are equally page chrome
    "about", "about us", "contact", "contact us", "shop", "store",
    "search", "menu", "news", "press", "blog", "events", "calendar",
    "membership", "join", "donate", "support", "give", "faq", "faqs",
    "plan your visit", "whats on", "what's on", "exhibitions", "exhibition",
    "collection", "collections", "the collection", "learn", "education",
    "sitemap", "site map", "privacy", "privacy policy", "terms", "cookies",
    "accessibility", "directions", "opening hours", "hours", "admission",
    "page not found", "404", "error", "login", "log in", "sign in", "account",
    "newsletter", "subscribe", "gallery", "galleries", "venue hire",
    "group visits", "schools", "families", "getting here",
})

# Leading article across the live-venue languages (reuse the room-guard pattern).
_LEAD_ARTICLE_RE = re.compile(
    r"(?i)^\s*(?:the|le|la|les|das|der|die|il|lo|el|los|las|l['’])\s+")

# A "Profile"-style section word even when it leads a chrome breadcrumb that the
# separator test ALSO catches — kept as a belt-and-braces positive so a future
# title "Profile: our building" (colon joiner, no «/|) is still caught.
_SECTION_LEAD_RE = re.compile(
    r"(?i)^\s*(?:profile|home|visit|tickets?|about(?:\s+us)?|whats?\s*['’]?s?\s*on)"
    r"\s*(?:[:\-–—]\s|$)")


def _norm(text: str) -> str:
    """Lowercase, drop a leading article, collapse punctuation/whitespace to a
    single-spaced token string. Mirrors room_candidate_guard._norm_venue so the
    section-label membership test is punctuation-insensitive."""
    t = (text or "").strip()
    if not t:
        return ""
    t = _LEAD_ARTICLE_RE.sub("", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return " ".join(t.lower().split())


def is_junk_page_title(title: str, venue_name: str = "") -> bool:
    """True when ``title`` is a web-page / CMS / navigation title, never a stop.

    Rejects (deterministic, pure), per the LOCAL-632 rule set:
      1. the title contains a page-chrome separator («, », |, or a spaced dash
         joiner) — a breadcrumb such as "Profile « The ALBERTINA Museum Vienna" or
         "Exhibitions | Rijksmuseum";
      2. the WHOLE title (after a leading article) is a bare section/nav label
         ("Profile", "Home", "Visit", "Tickets", "About", …);
      3. the title leads with a section word joined by a colon/dash
         ("Profile: our story");
      4. the title names the VENUE ITSELF (delegated to
         ``room_candidate_guard.is_venue_itself_title`` so the two guards agree).

    Conservative: a real work whose title merely CONTAINS one of these words in a
    descriptive way ("The Visit", "A Home in the Country") is NOT rejected, because
    none of its text is a chrome separator, it is not EXACTLY a nav label, and it
    is not the venue. Only chrome shape triggers a reject.
    """
    t = (title or "").strip()
    if not t:
        return True  # an empty title can never be a stop

    # 1. page-chrome separator anywhere.
    if _CHROME_SEPARATOR_RE.search(t):
        return True

    # 2. the whole title is a bare section/navigation label.
    if _norm(t) in _SECTION_LABELS:
        return True

    # 3. a leading section word joined by a colon/dash.
    if _SECTION_LEAD_RE.search(t):
        return True

    # 4. the venue itself (reuse the LOCAL-626 authority; never diverge).
    try:
        from room_candidate_guard import is_venue_itself_title as _is_venue
        if _is_venue(t, venue_name):
            return True
    except Exception:  # pragma: no cover - defensive, never fatal
        pass

    # 4b. [LOCAL-632] A page <title> that is the VENUE NAME padded with generic
    #     institution/location words — "The ALBERTINA Museum Vienna" for venue
    #     "Albertina". is_venue_itself_title only strips a trailing institution
    #     noun; a scraped page title also carries the city and extra chrome words.
    #     When, after removing institution nouns AND the venue's own name tokens,
    #     nothing distinctive remains (only generic/location filler), the title
    #     names the venue, not a work. Conservative: requires the venue name to be
    #     fully present so a real work ("Vienna Woods") is never caught.
    if _title_is_venue_with_filler(t, venue_name):
        return True

    return False


# Generic words that pad a scraped venue page <title> around the proper name: the
# institution type, the city/qualifier, and museum-chrome tokens. When a title is
# ONLY the venue's name plus words from this set, it is the venue page, not a work.
_VENUE_FILLER_WORDS = frozenset({
    "museum", "museums", "gallery", "galleries", "collection", "collections",
    "institute", "foundation", "trust", "centre", "center", "haus", "musee",
    "musée", "museo", "pinakothek", "kunsthalle", "kunstmuseum", "galerie",
    "modern", "contemporary", "art", "arts", "fine", "national", "state",
    "royal", "official", "site", "website", "homepage", "home", "welcome",
    "vienna", "wien", "london", "amsterdam", "paris", "madrid", "berlin",
    "austria", "the",
})


def _title_is_venue_with_filler(title: str, venue_name: str) -> bool:
    """True when ``title`` consists of the venue's proper name plus only generic
    institution/location/chrome filler ("The ALBERTINA Museum Vienna" vs venue
    "Albertina"). Requires every venue-name token to be present in the title, and
    every REMAINING token to be filler. Pure."""
    vt = _norm(venue_name).split()
    tt = _norm(title).split()
    if not vt or not tt:
        return False
    # Every venue-name token must appear in the title (venue fully present).
    if not all(tok in tt for tok in vt):
        return False
    # Remove the venue-name tokens once each, then every leftover must be filler.
    leftover = list(tt)
    for tok in vt:
        if tok in leftover:
            leftover.remove(tok)
    if not leftover:
        return True  # title is exactly the venue name
    return all(tok in _VENUE_FILLER_WORDS for tok in leftover)


def filter_out_junk_titles(
    candidates: Sequence,
    venue_name: str = "",
    *,
    title_key: str = "title",
) -> Tuple[List, List]:
    """Return (kept, dropped): candidates split by ``is_junk_page_title``.

    ``candidates`` is a list of dicts (``title_key`` or ``name`` selects the
    title) or bare strings. Each dropped dict is a shallow copy carrying a
    ``_reject_reason`` key so a caller can print the before/after list. Order-
    preserving and pure.
    """
    kept: List = []
    dropped: List = []
    for c in candidates or []:
        if isinstance(c, dict):
            title = (c.get(title_key) or c.get("name") or "").strip()
        else:
            title = str(c or "").strip()
        if is_junk_page_title(title, venue_name):
            if isinstance(c, dict):
                d = dict(c)
                d["_reject_reason"] = "junk_page_title"
                dropped.append(d)
            else:
                dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped
