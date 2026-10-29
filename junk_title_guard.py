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

__all__ = ["is_junk_page_title", "filter_out_junk_titles",
           "is_commerce_url", "is_shop_product_title"]

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
    # [LEAD 2026-10-09] St Louis 548 "Collection Guide"
    "collection guide", "audio guide", "highlights", "collection highlights", "floor plan", "map", "museum map",
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

# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-721] CALL-TO-ACTION / imperative site-phrase intake reject. The Courtauld
# site (and any modern museum CMS) wraps each work's image in a link whose anchor
# text is a visitor instruction — "Explore this painting in our virtual tour",
# "Explore this sculpture in our virtual tour". That anchor text is scraped into
# the venue corpus / candidate-works list as if it were a work title (it appears
# ~80× in a single Courtauld generation log) and, lacking any chrome separator or
# bare-nav shape, it sailed past every existing junk rule and became a STOP.
#
# A CTA is not a thing on a wall; it is an instruction ABOUT the website. Two
# deterministic, venue-agnostic signatures identify one without ever touching a
# real work title:
#
#   (a) IMPERATIVE OPENER — the title STARTS with a base-form action verb that is
#       followed by MORE words ("Explore this …", "View our …", "Discover the …",
#       "Book your tickets", "Learn more", "Plan your visit", "Join and support",
#       "Sign up …", "Watch the video"). The follow-on requirement is what keeps a
#       one-word noun title that merely LOOKS verb-like ("Explosion", "Discover" as
#       a bare exhibition name, "Visitation") safe: a lone word is never an
#       instruction, and a real work almost never opens "Verb + this/our/your/us".
#
#   (b) WEBSITE-OBJECT PHRASE — the title contains an unambiguous online/marketing
#       object anywhere ("virtual tour", "online collection", "e-newsletter",
#       "gift shop", "buy tickets", "download the app"). These name a website
#       feature, not an artwork, so their presence is itself the reject.
#
# Both are kept deliberately tight (a closed verb list, an explicit object list)
# so a descriptive work title is never caught: "A Bar at the Folies-Bergère",
# "Self-Portrait with Bandaged Ear", "Explosion", "The Card Players", "Still Life
# with Pears", "Virgin and Child" all fail BOTH tests.

# (a) The CTA imperative verbs a museum site uses for its visitor-action links.
#     Base form only; the opener must be FOLLOWED by an instruction object/
#     connective (enforced in the pattern) so a bare one-word title is never
#     matched. Split into two tiers by false-positive risk:
#       STRONG verbs practically never open a real work title, so verb + a generic
#         connective ("this/our/your/more/…") is enough to reject.
#       WEAK verbs ("take"/"make"/"give"/… ) DO open real work titles ("Take Your
#         Son, Sir!", "Giving Alms", "Make Believe"), so they reject ONLY when the
#         title also carries an explicit website/marketing OBJECT (rule b).
_CTA_VERB_STRONG = (
    r"explore|discover|browse|book|buy|purchase|order|reserve|"
    r"learn|join|donate|subscribe|register|shop|plan|download|"
    r"sign|view|visit|read")

# A title that OPENS with a STRONG CTA verb and then continues with an instruction
# connective/object — "Explore this painting in our virtual tour", "Book your
# tickets", "Learn more", "Plan your visit", "Join and Support", "Sign up". A lone
# verb ("Explore") or a verb that ends the title is NOT matched. The connective
# set is instruction-specific so a work whose second word is a plain content noun
# is never caught.
_CTA_IMPERATIVE_RE = re.compile(
    r"(?i)^\s*(?:" + _CTA_VERB_STRONG + r")\b"
    r"\s+(?:this|that|these|those|our|your|my|us|the\s+museum|the\s+gallery|"
    r"more|now|here|today|online|up|in\b|to\s+(?:our|the|a)\b|"
    r"and\s+(?:support|donate|give|save)|"
    r"tickets?|a\s+ticket|the\s+(?:tour|video|app|collection|newsletter|catalogue|catalog))\b")

# (b) Website / marketing OBJECTS — a phrase naming an online feature, never an
#     artwork. Matched anywhere in the title.
_CTA_OBJECT_RE = re.compile(
    r"(?i)\b("
    r"virtual\s+tours?|online\s+(?:collection|shop|store|tours?|exhibition)|"
    r"e[-\s]?newsletter|newsletter\s+sign\s*up|mailing\s+list|"
    r"gift\s+shop|museum\s+shop|online\s+shop|"
    # [LOCAL-811B] "the shop" as a BARE object was dropped: it is a substring of
    # real artwork titles ("The Shop Girl", Tissot), and the LEAD rule forbids a
    # commerce match on a substring of a title. The genuine website-feature "shop"
    # CTAs are covered by "gift/museum/online shop" above and the imperative
    # "shop the collection/catalogue" below — never a bare "the shop".
    r"buy\s+tickets?|book\s+tickets?|book\s+(?:now|online|your\s+visit)|"
    r"download\s+the\s+app|mobile\s+app|audio\s+guide\s+app|"
    r"shop\s+the\s+(?:catalogue|catalog|collection)|"
    r"create\s+your\s+own\s+gallery|join\s+and\s+support"
    r")\b")


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-809] SHOP / COMMERCE reject. A gift-shop PRODUCT is never an exhibit.
#
# Met Store (tour 850, score 3.0): stops 2 and 3 were store merchandise written
# up as exhibits — "Empire State Building Custom Print" and "Wall Calendar 2027 —
# The Met Store". They reached the tour because the candidate came from a store /
# shop page on the museum's commerce subdomain, and nothing rejected either the
# product TITLE (a calendar, a print, a poster) or the SOURCE URL
# (store.metmuseum.org / …/shop/ / …/products/…).
#
# Two deterministic, venue-agnostic signatures identify shop merchandise without
# touching a real artwork title:
#
#   (a) COMMERCE SOURCE URL — the candidate's page URL is a store/shop/product
#       page: a ``store.``/``shop.`` host, or a ``/shop/`` ``/store/``
#       ``/products/`` ``/product/`` ``/cart``/``/basket``/``/checkout`` path, or
#       a query that carries a product/SKU/variant id. A page under commerce is a
#       catalogue of things-to-BUY, not things-to-look-at.
#
#   (b) SHOP-PRODUCT TITLE — the title names a retail product type a museum shop
#       sells (calendar, print, poster, tote, mug, gift, …) or carries a price /
#       "add to cart" / SKU token. "Wall Calendar 2027", "Empire State Building
#       Custom Print", "Van Gogh Tote Bag", "Starry Night Mug — $24.95".
#
# Both are kept tight so a real work is never caught: a PRINT as an original
# artwork medium (etching/engraving/woodcut) lives in the SPARQL works set with a
# P31 print class and a creator and is admitted by artwork_selection_guard BEFORE
# any title test; this title rule only bites a retail "… Print"/"Fine Art Print"/
# "Custom Print" product-name shape, and a one-word title "Print" is NOT matched.

# (a) Commerce SOURCE-URL signatures.
_COMMERCE_HOST_RE = re.compile(r"(?i)^(?:https?://)?(?:www\.)?(?:store|shop|shops|"
                               r"webshop|eshop|e-shop|boutique|giftshop)\.")
_COMMERCE_PATH_RE = re.compile(
    r"(?i)/(?:shop|store|stores|products?|product-category|collections?/[^/]+/products|"
    r"cart|basket|checkout|catalog(?:ue)?|merchandise|gift[-_]?shop|boutique)(?:/|$|\?)")
_COMMERCE_QUERY_RE = re.compile(
    r"(?i)[?&](?:add-to-cart|sku|product_id|productid|variant|variant_id|pid)=")


def is_commerce_url(url: str) -> bool:
    """[LOCAL-809] True when ``url`` is a store/shop/product page — a commerce
    source that can only yield merchandise, never an exhibit. Pure; venue-agnostic.

    Matches a ``store.``/``shop.`` host, a ``/shop/`` ``/store/`` ``/products/`` …
    path segment, a cart/checkout path, or an add-to-cart/SKU/variant query. An
    ordinary content URL on the museum's main domain (``/collection/…``,
    ``/exhibitions/…``, ``/art/…``) is NOT matched."""
    u = (url or "").strip()
    if not u:
        return False
    if _COMMERCE_HOST_RE.search(u):
        return True
    if _COMMERCE_PATH_RE.search(u):
        return True
    if _COMMERCE_QUERY_RE.search(u):
        return True
    return False


# (b) Retail PRODUCT-TYPE nouns a museum shop sells. Matched only as a product-
# name shape (see _is_shop_product_title), never as a bare single word, so a work
# whose title merely contains one ("The Printmaker", a painting; "Posterity") is
# safe. "poster" excludes the art-history sense via the product-name requirement.
#
# STRONG nouns are retail-specific enough that a product-name shape (noun + a
# qualifier) is a shop item: "Wall Calendar 2027", "Custom Print", "Van Gogh Tote
# Bag", "Starry Night Mug". WEAK nouns (hat, cap, tie, bag, socks, scarf, tee …)
# also appear in real artwork titles ("Self-Portrait with a Straw Hat", "The Blue
# Boy"), so they count ONLY alongside an explicit retail signal (price / add-to-
# cart / SKU / shop brand), never on the product-name shape alone.
_SHOP_PRODUCT_NOUN_RE = re.compile(
    r"(?i)\b("
    r"calendars?|wall\s+calendar|desk\s+calendar|"
    r"posters?|art\s+print|fine[-\s]?art\s+print|custom\s+print|giclee\s+print|"
    r"printed\s+(?:tote|mug|scarf|t-?shirt)|"
    r"tote\s+bags?|totes?|backpacks?|"
    r"mugs?|tumblers?|coaster(?:s|\s+set)?|"
    r"hoodie|sweatshirts?|"
    r"notebooks?|journals?|stationery|magnets?|stickers?|"
    r"keychains?|keyrings?|bookmarks?|jigsaw\s+puzzles?|puzzles?|playing\s+cards?|"
    r"ornaments?|figurines?|snow\s+globe|"
    r"gift\s+(?:set|card|box|wrap|guide)|holiday\s+gift|"
    r"mousepad|phone\s+case|"
    r"reproduction\s+print|boxed\s+(?:set|notecards?)|note\s*cards?|greeting\s+cards?"
    r")\b")

# WEAK apparel/accessory nouns — real art titles use them, so they only indicate
# merchandise together with an explicit retail signal below.
_SHOP_WEAK_NOUN_RE = re.compile(
    r"(?i)\b(bags?|pouch(?:es)?|t-?shirts?|tee|scarf|scarves|tie|socks?|cap|hat|"
    r"apron|umbrella|water\s+bottles?|pencils?|pens?|jewel(?:le)?ry|earrings?|"
    r"necklaces?|bracelets?|brooch(?:es)?|cufflinks?)\b")

# A price token, "add to cart", a SKU/item number — plain retail signals in a
# title or its scraped line. Any one marks merchandise.
_SHOP_PRICE_RE = re.compile(
    r"(?i)(?:[$£€¥]\s?\d[\d.,]*|\b\d+[.,]\d{2}\s?(?:usd|eur|gbp|dollars?|euros?)\b)")
_SHOP_CART_RE = re.compile(
    r"(?i)\b(add\s+to\s+(?:cart|bag|basket)|in\s+stock|out\s+of\s+stock|"
    r"sold\s+out|buy\s+now|shop\s+now|free\s+shipping|"
    r"sku[:#]?\s*\w+|item\s*(?:no\.?|number|#)\s*\w+)\b")

# The retail descriptor that, combined with a shop noun, confirms a product NAME
# rather than a chance occurrence of the noun ("Wall Calendar 2027", "Custom
# Print", "Van Gogh Tote Bag", "The Met Store" brand suffix).
_SHOP_BRAND_SUFFIX_RE = re.compile(
    r"(?i)\b(?:the\s+)?(?:met|museum|gallery|gift|online)\s+(?:store|shop)\b")


def is_shop_product_title(title: str) -> bool:
    """[LOCAL-809] True when ``title`` names a museum-shop PRODUCT — merchandise,
    never an exhibit. Pure; venue-agnostic.

    Rejects on any of:
      * a PRICE token, an "add to cart"/stock phrase, or a SKU/item number
        anywhere ("Starry Night Mug — $24.95", "Add to cart", "SKU 80012345");
      * a store/shop BRAND suffix ("… — The Met Store", "Museum Shop");
      * a STRONG retail PRODUCT-TYPE noun (calendar/print/poster/tote/mug/gift/…)
        used as a product name — the title is more than the bare noun (it carries
        a qualifier such as a year, "custom", "wall", a subject);
      * a WEAK apparel/accessory noun (hat/tie/cap/bag/socks/…) ONLY when an
        explicit retail signal (price/cart/SKU/brand) is also present.

    Conservative: a bare one-word product noun ("Print", "Bag") is NOT rejected
    here, a weak noun on its own is NOT rejected ("Self-Portrait with a Straw
    Hat", "The Blue Boy" are safe), and an original-artwork PRINT from the SPARQL
    works set is admitted by class/creator upstream before any title test runs."""
    t = (title or "").strip()
    if not t:
        return False
    _retail_signal = bool(_SHOP_PRICE_RE.search(t) or _SHOP_CART_RE.search(t)
                          or _SHOP_BRAND_SUFFIX_RE.search(t))
    if _retail_signal:
        return True
    m = _SHOP_PRODUCT_NOUN_RE.search(t)
    if m:
        # Require the title to be a PRODUCT NAME, not just the bare noun: there
        # must be at least one more meaningful token besides the matched noun
        # (a year, "custom"/"wall", a subject, a brand). A lone product noun is
        # left to the generic-word rule so a real work is never caught here.
        _rest = (t[:m.start()] + t[m.end():]).strip(" -–—:,·|")
        if _rest and len(_rest) >= 2:
            return True
    return False


def _is_call_to_action_title(title: str) -> bool:
    """[LOCAL-721] True when ``title`` is website call-to-action / link text, not a
    work: an imperative visitor instruction ("Explore this painting in our virtual
    tour", "Book your tickets", "Learn more", "Plan your visit") or a phrase naming
    an online/marketing feature ("virtual tour", "gift shop", "create your own
    gallery"). Pure; venue-agnostic.

    Conservative on purpose: a real work title that merely STARTS with a verb-like
    word is safe because the imperative test requires an instruction object/
    connective after the verb — a lone "Explosion"/"Discover" or a descriptive
    noun phrase is never matched — and the object test only fires on an explicit
    website-feature phrase.
    """
    t = (title or "").strip()
    if not t:
        return False
    if _CTA_OBJECT_RE.search(t):
        return True
    if _CTA_IMPERATIVE_RE.search(t):
        return True
    return False


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


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-791 defect 4] GENERIC WORD / HEADING / HEADLINE reject. A stop title must
# be a PROPER NAME of a place or exhibit. Three shapes are never a stop:
#   (a) a bare GENERIC common word — a room/feature/adjective that names no place
#       ("Balcony", "Interesting", "View", "Entrance"). Matched only when the WHOLE
#       title (after a leading article) is one generic word, so a real place that
#       merely CONTAINS one ("Balcony Bar", "The Interesting House Museum") is safe.
#   (b) a NEWS HEADLINE — a sentence-shaped line (many words, often with a verb and
#       a trailing ellipsis) scraped from a news page ("Khai mạc Hội thảo Quốc tế
#       …"). Identified by sentence shape: long, ends in an ellipsis, or reads as a
#       clause rather than a name.
#   (c) a HEADING — an all-lower / generic section heading not already in the nav
#       label set.
# Conservative: tuned so a real multi-word proper name of a place is never caught.
# ─────────────────────────────────────────────────────────────────────────────

# Bare generic common words — a room, a feature, an adjective, a direction. None
# names a place on its own. Kept to the words the field runs actually shipped plus
# their obvious siblings; a title is rejected ONLY when it is EXACTLY one of these
# (after a leading article), never when it contains one.
_GENERIC_WORD_TITLES = frozenset({
    # the field-run junk
    "balcony", "interesting",
    # rooms / features that are not a place by themselves
    "entrance", "exit", "lobby", "foyer", "hall", "hallway", "corridor",
    "terrace", "patio", "courtyard", "garden", "yard", "roof", "rooftop",
    "basement", "attic", "staircase", "stairs", "elevator", "lift", "toilet",
    "toilets", "restroom", "restrooms", "bathroom", "parking", "car park",
    "view", "views", "viewpoint", "overview", "area", "room", "rooms", "space",
    "spaces", "building", "buildings", "floor", "wall", "walls", "window",
    "windows", "door", "doors", "gate", "fence", "bridge",
    # bare adjectives / fillers
    "interesting", "beautiful", "amazing", "nice", "lovely", "stunning",
    "historic", "historical", "famous", "popular", "local", "traditional",
    "modern", "old", "new", "scenic", "various", "miscellaneous", "other",
    "others", "more", "misc", "general", "overview", "introduction", "intro",
    "untitled", "unknown", "none", "test", "sample", "example", "placeholder",
    # [LOCAL-791E defect 4] bare architectural QUALIFIERS the Old Saigon venue-parts
    # path shipped as one-word "stops" ("Grand" — left after a "Grand foyer" split).
    # An adjective-qualifier alone names no place.
    "grand", "main", "great", "upper", "lower", "inner", "outer", "front",
    "rear", "central", "northern", "southern", "eastern", "western", "royal",
})

# Words that make a title read as a sentence/clause rather than a proper name:
# auxiliary / common finite verbs. Their presence (with enough words) signals a
# headline, not a name. English only — a foreign headline is caught by the
# length/ellipsis signals below.
_HEADLINE_VERB_RE = re.compile(
    r"(?i)\b(?:is|are|was|were|has|have|had|will|would|can|could|should|"
    r"announce[sd]?|open(?:s|ed|ing)?|launch(?:es|ed|ing)?|host(?:s|ed|ing)?|"
    r"hold[s]?|held|unveil(?:s|ed)?|celebrat(?:es|ed)|mark(?:s|ed)|"
    r"present(?:s|ed)?|reveal(?:s|ed)?|say[s]?|said|report(?:s|ed)?)\b")


def _is_generic_or_headline_title(title: str) -> bool:
    """[LOCAL-791 defect 4] True when ``title`` is a bare generic word, a heading,
    or a news headline — never a proper name of a place/exhibit. Pure."""
    t = (title or "").strip()
    if not t:
        return True

    # (a) bare generic word (after a leading article), ignoring trailing punctuation.
    bare = _norm(t)
    if bare in _GENERIC_WORD_TITLES:
        return True

    words = t.split()
    n_words = len(words)

    # [LOCAL-811B] QUOTED-TITLE exemption. A title that carries a quoted span is a
    # normal artwork title — a line of verse or speech the work is named for, e.g.
    # Waterhouse's '"I am half sick of shadows," said the Lady of Shalott'. The
    # LEAD rule is explicit: quoted titles are normal. A quote mark means the
    # sentence-shape signals below (a finite verb like "said", trailing sentence
    # punctuation) are the TITLE's own wording, not a scraped news headline, so
    # those two heuristics are skipped. The trailing-ellipsis tell (a truncated
    # scrape) still applies — an ellipsis is not quotation.
    _has_quote = bool(re.search(r"[\"'\u2018\u2019\u201c\u201d\u00ab\u00bb]", t))

    # (b) NEWS HEADLINE / sentence shape.
    #   * a trailing ellipsis is the classic scraped-headline tell ("Khai mạc Hội
    #     thảo Quốc tế …") — reject at 4+ words so a short name ending in "…" from
    #     a truncated list is only cut when it is clearly a clause.
    if re.search(r"(?:\u2026|\.\.\.)\s*$", t) and n_words >= 4:
        return True
    #   * a long, sentence-shaped line with a finite verb is a headline, not a name.
    if not _has_quote and n_words >= 6 and _HEADLINE_VERB_RE.search(t):
        return True
    #   * ends with sentence punctuation and is long (a scraped sentence).
    if not _has_quote and n_words >= 8 and re.search(r"[.!?]\s*$", t):
        return True

    return False


def is_junk_page_title(title: str, venue_name: str = "",
                       source_url: str = "") -> bool:
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

    # 0. [LOCAL-809] SHOP / COMMERCE. A gift-shop product is never an exhibit.
    #    Reject when the candidate's SOURCE URL is a store/shop/product page
    #    (store.metmuseum.org, …/shop/, …/products/…), or when the TITLE names a
    #    shop product (calendar/print/poster/tote/mug/gift/…) or carries a price /
    #    "add to cart" / SKU. This catches the Met Store merchandise written up as
    #    exhibits ("Empire State Building Custom Print", "Wall Calendar 2027 — The
    #    Met Store") at candidate intake, whatever else the title looks like.
    if source_url and is_commerce_url(source_url):
        return True
    if is_shop_product_title(t):
        return True

    # 1. page-chrome separator anywhere. [LEAD 2026-10-08] A spaced DASH alone is NOT chrome:
    # real titles use it ("Rain, Steam and Speed – The Great Western Railway", "Nocturne: Blue
    # and Gold – Old Battersea Bridge", "Landscape – Capriccio"), and rejecting them cost the NG
    # 2 of 3 stops in Bench R3. A dash is chrome only when one side is a section label, the
    # venue, or a site brand. A pipe stays unconditional (never a quote mark).
    if "|" in t:
        return True
    # [LOCAL-811B] Guillemets « » are breadcrumb GLUE in a page <title>
    # ("Profile « The ALBERTINA Museum Vienna") but are also French QUOTATION marks
    # wrapping an artwork's own title ("Pendule « L'Amitié voilant les heures »").
    # The LEAD rule (item 1) is explicit — a quoted title is normal and must not be
    # rejected as chrome. Distinguish the two by SHAPE: a BALANCED pair (an opening
    # « followed later by a closing ») that WRAPS a span, with real title text left
    # OUTSIDE the quotes, is a quoted title → keep. A separator guillemet (an
    # unbalanced « or », or a pair with nothing outside it) is breadcrumb chrome →
    # reject.
    if "«" in t or "»" in t:
        _o, _c = t.find("«"), t.rfind("»")
        _balanced_wrap = (_o != -1 and _c != -1 and _c > _o)
        _outside = (t[:_o] + t[_c + 1:]).strip() if _balanced_wrap else ""
        if not (_balanced_wrap and _outside):
            return True  # a bare/separator guillemet — page chrome
    _dash = re.split(r"\s[-–—]\s", t)
    if len(_dash) > 1:
        _vn = _norm(venue_name)
        for _side in _dash:
            _ns = _norm(_side)
            if (_ns in _SECTION_LABELS or (_vn and (_ns == _vn or _vn in _ns))
                    or re.search(r"(?i)\b(official (site|website)|home ?page|website|choose [a-z]+|visit [a-z]+)\b", _side)):
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

    # 5. [LOCAL-721] website call-to-action / link text ("Explore this painting in
    #    our virtual tour", "Book your tickets", "Learn more", "Create your own
    #    gallery"). Modern museum CMS wraps each work's image in a visitor-action
    #    link; that anchor text is scraped as a work title and, lacking any chrome
    #    separator or bare-nav shape, slipped past rules 1–4. Venue-agnostic and
    #    conservative — a real work that merely starts with a verb-like word
    #    ("Explosion") is not caught.
    if _is_call_to_action_title(t):
        return True

    # 6. [LOCAL-791 defect 4] GENERIC WORD / HEADING / HEADLINE. A stop title must
    #    be a PROPER NAME of a place or exhibit. The HCMC field run shipped stops
    #    that are none of those: a bare common word ("Balcony" — a café terrace,
    #    461; "Interesting", 463), a page/section heading, and a news headline
    #    ("Khai mạc Hội thảo Quốc tế …", 463). These slipped past rules 1–5 because
    #    they carry no chrome separator, are not nav labels, and are not CTAs.
    if _is_generic_or_headline_title(t):
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
    url_keys: Sequence[str] = ("source_url", "detail_url", "url", "page_url"),
) -> Tuple[List, List]:
    """Return (kept, dropped): candidates split by ``is_junk_page_title``.

    ``candidates`` is a list of dicts (``title_key`` or ``name`` selects the
    title; ``url_keys`` selects an optional source URL for the [LOCAL-809]
    commerce check) or bare strings. Each dropped dict is a shallow copy carrying
    a ``_reject_reason`` key so a caller can print the before/after list. Order-
    preserving and pure.
    """
    kept: List = []
    dropped: List = []
    for c in candidates or []:
        if isinstance(c, dict):
            title = (c.get(title_key) or c.get("name") or "").strip()
            src = ""
            for _uk in url_keys:
                if c.get(_uk):
                    src = str(c.get(_uk))
                    break
        else:
            title = str(c or "").strip()
            src = ""
        if is_junk_page_title(title, venue_name, source_url=src):
            if isinstance(c, dict):
                d = dict(c)
                d["_reject_reason"] = "junk_page_title"
                dropped.append(d)
            else:
                dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped
