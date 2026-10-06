#!/usr/bin/env python3
"""about_museum_stop.py — LOCAL-585: a museum tour opens with the museum's OWN story.

Michael, tour 391 (2026-10-05): the Griffin tour's real first-stop content was the
museum's history — Arthur Griffin, the founding board, non-profit since 1992 — but
it was framed as an ARTWORK ("Griffin Museum Board Of Directors 2 consists of a
series of frames…"). That framing is invented: a page about the institution is not
a work hanging on a wall.

LOCAL-583/589 already REJECT that chrome title from the artwork/exhibition set
(exhibition_discovery.is_chrome_title). This module is the POSITIVE mirror: the
same founding content SHOULD be delivered — as a proper **"About <museum>"** STORY
stop, sourced like any stop, and NEVER presented as an artwork or exhibition.

WHAT THIS BUILDS
----------------
One stop unit (a plain dict the stop-pool assembler understands) that opens a
museum tour:

    {
      "title": "About <Museum>",
      "narration": "<the founder / why-it-exists / what-it-is-known-for story>",
      "orientation": "<one-line position aid>",
      "sources": [...on-domain + wiki URLs...],
      "address": "<venue address if known>",
      "coordinates": "<lat, lng if known>",
      "_about_stop": True,       # marks this as the About stop
      "_pool_reused": False,     # it is freshly composed, placed FIRST
      "_counts_toward_n": <bool> # see "COUNT SEMANTICS" below
    }

Crucially the unit carries NO artist, NO year, NO "Type/Specialty", NO
"Specific Examples" — the fields that make a block read as an artwork. The
assembler's museum/facility branch already omits those for museum stops, and the
About stop never populates them. A guard (``looks_like_artwork_framing``) is
exposed so tests and callers can assert the narration never slips into
work-description language ("this work", "consists of a series of frames", "oil on
canvas", "the artist depicts…").

SOURCING (same honesty contract as museum_overview.py / D538)
-------------------------------------------------------------
The story is drawn from the venue's OWN About / history / mission pages (and, when
available, Wikipedia/Wikidata). Every network touch goes through an injectable
``fetcher`` and an injectable ``wiki_provider`` so the whole stop can be built from
fixtures with no HTTP. Nothing is invented: if the venue's pages and the wiki
sources yield no story sentences, ``build_about_stop`` returns None and the caller
simply does not prepend an About stop (the tour is unchanged — D577: never turn a
working tour into no tour).

ARCHITECTURE COVERAGE
---------------------
When the REQUEST names architecture ("architecture tour", "architectural"), or the
building is architecturally notable (a Wikipedia/Wikidata/site sentence names its
architect or its building/landmark status), the About stop covers the building:
who designed it, when, what style — sourced. This is what the Boston Athenaeum
case (LOCAL-591) asked for: 5 artworks inside the building, plus a stop about the
building itself.

COUNT SEMANTICS
---------------
The About stop counts toward the requested N stops ONLY when the listener asked for
N and there is NOT enough exhibition material to fill N on its own. Otherwise it is
the orientation, enriched — an extra opening stop that does not consume an
exhibition slot. ``should_count_toward_n`` encodes the rule as a pure function so
the generator can decide how many exhibition stops to still request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

__all__ = [
    "AboutStop",
    "build_about_stop",
    "about_stop_unit",
    "looks_like_artwork_framing",
    "should_count_toward_n",
    "request_wants_architecture",
    "clean_venue_request_name",
    "default_wiki_provider",
]


# A fetcher returns (html, links) for a URL — same contract as museum_overview.
Fetcher = Callable[[str], Tuple[str, List[Tuple[str, str]]]]

# A wiki provider returns a dict (or None) with any of:
#   {"summary": str, "architect": str, "inception": str, "sources": [url, ...],
#    "architecturally_notable": bool}
# It is injectable so tests run offline and production can wire Wikipedia/Wikidata.
WikiProvider = Callable[[str], Optional[dict]]


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)

# Pages on the venue's own domain that tell the institution's STORY (founder, why
# it exists, mission, history, the building). Ordered so the highest-value "story"
# pages are reached first. These mirror the real Griffin IA: /about-us, /mission,
# /history, the founder archive, "your-support-matters" (Griffin's Mission page).
_STORY_SEEDS = [
    "/about", "/about-us", "/about-the-museum", "/our-story", "/history",
    "/our-history", "/mission", "/your-support-matters", "/who-we-are",
    "/the-building", "/architecture", "/visit", "/plan-your-visit",
]

# Request phrases that make the building/architecture a first-class subject.
# Includes the misspelling "architectual" seen in the real Athenaeum field request
# ("Art and Architectual tour in Boston Athenaeum", LOCAL-591) so the listener's
# intent is honoured even when the word is typed as it was in the ticket.
_ARCH_REQUEST_RE = re.compile(
    r"(?i)\b(architect|architectural|architectual|architecture|building|edifice|"
    r"landmark building|historic building)\b"
)

# Narration patterns that would (wrongly) frame the About stop as an ARTWORK.
# If any match, the narration is treated as artwork-framing and rejected. This is
# the exact failure mode from tour 391 ("consists of a series of frames").
_ARTWORK_FRAMING_RE = re.compile(
    r"(?i)("
    r"consists of a series of frames|"
    r"\bthis (?:work|piece|painting|sculpture|photograph|artwork|canvas)\b|"
    r"\bthe (?:work|piece|artwork) (?:depicts|portrays|shows|measures|hangs)\b|"
    r"\boil on canvas\b|\bgelatin silver print\b|\bmixed media\b|"
    r"\bthe artist (?:depicts|portrays|renders|captures|painted|photographed)\b|"
    r"\bon (?:display|view) (?:in|on) (?:this|the) (?:gallery wall|pedestal|plinth)\b|"
    r"\bmeasures \d+\s*(?:by|x|×)\s*\d+|"
    r"\bbrushwork\b|\bchiaroscuro\b|\bimpasto\b"
    r")"
)

# Sentence-level identity grammar: a real self-description is "<Venue> is a/was/
# houses/presents/founded…". Reused idea from museum_overview._describe_place, but
# widened to the founding / institutional-story verbs this stop wants.
_STORY_VERBS = (
    r"is\s+(?:a|an|the|one|home|dedicated|devoted|located|among|housed|"
    r"new\s+england)|was\s+(?:founded|established|built|created|incorporated|"
    r"the\s+first|designed)|were\s+founded|founded\s+(?:in|by)|established\s+(?:in|by)|"
    r"houses?|holds?|presents?|exhibits?|showcases?|preserves?|celebrates?|"
    r"is\s+devoted|offers?\s+|became\s+|opened\s+(?:in|its)|"
    r"has\s+(?:been|grown|championed)|champions?|promotes?|dedicated\s+to"
)

# Cruft that is navigation / account / marketing / legal — never the story.
_CRUFT_RE = re.compile(
    r"(?i)(\bcookie|\bmenu\b|subscrib|newsletter|sign\s*up|log\s*in|"
    r"receive\s+(?:\w+\s+){0,2}emails?|marketing\s+emails?|submitting\s+this\s+form|"
    r"consent|i\s+would\s+like|email\s+address|\binbox\b|delivered\s+to\s+your|"
    r"follow\s+us|copyright|all\s+rights\s+reserved|privacy|\bterms\b|click\s+here|"
    r"buy\s+tickets?|shop\s+now|opt[\s-]?in|add\s+to\s+cart|choose\s+an\s+option|"
    r"please\s+select|quantity|checkout)"
)

# Founding / history signal words — a sentence carrying one of these is the kind of
# story content LOCAL-585 wants surfaced (founder, founding year, non-profit, etc).
_STORY_SIGNAL_RE = re.compile(
    r"(?i)\b(founded|founder|established|est\.?\s*\d{4}|since\s+\d{4}|in\s+\d{4}|"
    r"non-?profit|nonprofit|501\(c\)|mission|dedicated|first\s+museum|"
    r"premier|named\s+(?:for|after)|legacy|archive|collection\s+of|"
    r"opened|incorporated|charter|history)\b"
)

# Architecture signal words for building sentences.
_ARCH_SIGNAL_RE = re.compile(
    r"(?i)\b(architect|designed\s+by|building\s+was|edifice|fa\u00e7ade|facade|"
    r"neoclassical|greek\s+revival|gothic|beaux-?arts|romanesque|italianate|"
    r"renaissance\s+revival|brick|granite|limestone|marble\s+hall|rotunda|"
    r"landmark|national\s+register|listed\s+building|style)\b"
)


@dataclass
class AboutStop:
    """The composed About-stop result (before it becomes a plain assembler unit)."""
    museum_name: str = ""
    narration: str = ""
    orientation: str = ""
    sources: List[str] = field(default_factory=list)
    address: str = ""
    coordinates: str = ""
    covers_architecture: bool = False
    counts_toward_n: bool = False

    def is_empty(self) -> bool:
        return not self.narration.strip()


# ── small shared helpers (kept behaviour-identical to museum_overview) ───────

def _visible_text(html: str) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        return re.sub(r"\s+\n", "\n", soup.get_text("\n", strip=True))
    except Exception:
        stripped = _SCRIPT_STYLE_RE.sub(" ", html)
        return re.sub(r"\s+", " ", _TAG_RE.sub(" ", stripped)).strip()


def _domain_of(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _default_fetcher(url: str) -> Tuple[str, List[Tuple[str, str]]]:
    import requests
    try:
        resp = requests.get(url, headers={"User-Agent": "Audioura/2.4 (+about)"},
                            timeout=15, allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            return resp.text, []
    except Exception:
        pass
    return "", []


def _candidate_story_urls(base_site_url: str) -> List[str]:
    if "://" not in base_site_url:
        base_site_url = "https://" + base_site_url
    parsed = urlparse(base_site_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    urls: List[str] = []
    seen = set()
    for u in [base_site_url.rstrip("/") or root] + [root + s for s in _STORY_SEEDS]:
        u = u or root
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _venue_core(venue_name: str) -> str:
    """The venue's own name with any trailing ', City, ST' tail removed."""
    return re.sub(r",.*$", "", venue_name or "").strip() or (venue_name or "").strip()


# ── public predicates (pure, unit-testable) ──────────────────────────────────

def request_wants_architecture(request_text: str) -> bool:
    """True when the tour request names architecture / the building as a subject."""
    return bool(_ARCH_REQUEST_RE.search(request_text or ""))


def looks_like_artwork_framing(text: str) -> bool:
    """True when narration frames the subject as an ARTWORK (the tour-391 defect).

    The About stop must NEVER read like an object label. This guard is the
    behavioural contract: the composer's own output is checked against it, and
    tests assert it holds for the Griffin founding content.
    """
    return bool(_ARTWORK_FRAMING_RE.search(text or ""))


def should_count_toward_n(requested_stops: Optional[int],
                          available_exhibition_stops: int) -> bool:
    """Does the About stop consume one of the N requested stops?

    It counts toward N ONLY when the listener asked for N and there is not enough
    exhibition material to reach N without it. Otherwise it is a free, enriched
    orientation stop that sits in front of the full N exhibition stops.

        requested_stops None/0        → not count (no explicit N to fill)
        enough exhibitions (>= N)      → not count (About is a bonus opener)
        too few exhibitions (< N)      → count (About helps reach N)
    """
    try:
        n = int(requested_stops) if requested_stops else 0
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return False
    return available_exhibition_stops < n


# ── story extraction ─────────────────────────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    # Split on sentence boundaries AND newlines, so an <h1>/<h2> with no final
    # period does not glue onto the next real sentence.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _is_story_sentence(sent: str, venue_core: str, venue_first: str) -> bool:
    s = sent
    if not (40 <= len(s) <= 300):
        return False
    if _CRUFT_RE.search(s):
        return False
    if not _STORY_SIGNAL_RE.search(s):
        return False
    # Must be grammatically ABOUT the institution: either names the venue (or its
    # leading word) OR carries an institutional story verb. This keeps a stray
    # marketing fragment from being lifted as the museum's story.
    names_venue = bool(venue_first and venue_first.lower() in s.lower())
    has_story_verb = bool(re.search(r"(?i)\b(" + _STORY_VERBS + r")\b", s))
    return names_venue or has_story_verb


def _collect_story_sentences(corpus_text: str, venue_name: str,
                             limit: int = 4) -> List[str]:
    """Lift up to ``limit`` founding/history sentences from the venue's own pages."""
    venue_core = _venue_core(venue_name)
    venue_first = venue_core.split()[0] if venue_core else ""
    picked: List[str] = []
    seen = set()
    for sent in _split_sentences(corpus_text):
        s = sent.rstrip()
        # Require terminal punctuation so we lift whole sentences for clean audio.
        if not s.endswith((".", "!", "?")):
            # A heading like "New England's Premier Photography Museum, est. 1992"
            # has no period but is a genuine identity line — accept it if it carries
            # a founding signal and names the venue kind.
            if not (_STORY_SIGNAL_RE.search(s) and re.search(r"(?i)museum|gallery|library|athenaeum|collection", s)):
                continue
            s = s.rstrip() + "."
        if not _is_story_sentence(s, venue_core, venue_first):
            continue
        key = re.sub(r"\s+", " ", s.lower())
        if key in seen:
            continue
        seen.add(key)
        picked.append(s)
        if len(picked) >= limit:
            break
    return picked


def _collect_architecture_sentences(corpus_text: str, limit: int = 2) -> List[str]:
    picked: List[str] = []
    seen = set()
    for sent in _split_sentences(corpus_text):
        s = sent.rstrip()
        if not s.endswith((".", "!", "?")):
            continue
        if not (40 <= len(s) <= 300):
            continue
        if _CRUFT_RE.search(s):
            continue
        if not _ARCH_SIGNAL_RE.search(s):
            continue
        key = re.sub(r"\s+", " ", s.lower())
        if key in seen:
            continue
        seen.add(key)
        picked.append(s)
        if len(picked) >= limit:
            break
    return picked


# ── narration composer (deterministic, no LLM) ───────────────────────────────

def _trim_to_word_band(text: str, lo: int = 90, hi: int = 240) -> str:
    words = text.split()
    if len(words) <= hi:
        return text
    clipped = " ".join(words[:hi])
    m = list(re.finditer(r"[.!?]", clipped))
    if m:
        return clipped[:m[-1].end()]
    return clipped


def _compose_about_narration(
    museum_name: str,
    locality: str,
    story_sentences: List[str],
    arch_sentences: List[str],
    wiki_summary: str,
    domain: str,
) -> str:
    """Compose the About-stop narration from sourced story sentences.

    It is explicitly the MUSEUM'S OWN STORY — founder, why it exists, what it is
    known for — and, when present, the building. It never says "this work" or
    describes an object; it describes an institution.
    """
    vn = _venue_core(museum_name) or museum_name
    where = f" in {locality}" if locality else ""
    parts: List[str] = []

    # Opening orientation: this is the museum's story, not an object label.
    parts.append(
        f"Before we look at anything on the walls, here is the story of {vn}{where} "
        f"itself — who created it, why it exists, and what it is known for.")

    if wiki_summary:
        parts.append(wiki_summary.strip())

    parts.extend(story_sentences)

    if arch_sentences:
        parts.append("A word about the building you are standing in.")
        parts.extend(arch_sentences)

    # Honest sourcing close.
    if domain:
        parts.append(
            f"This account is drawn from the museum's own pages on {domain}"
            + (" and public reference sources." if wiki_summary else "."))

    text = " ".join(p.strip() for p in parts if p and p.strip())
    return _trim_to_word_band(text)


# ── public builder ────────────────────────────────────────────────────────────

def build_about_stop(
    venue_name: str,
    base_site_url: str = "",
    request_text: str = "",
    locality: str = "",
    address: str = "",
    coordinates: str = "",
    requested_stops: Optional[int] = None,
    available_exhibition_stops: int = 0,
    fetcher: Optional[Fetcher] = None,
    wiki_provider: Optional[WikiProvider] = None,
    corpus_text: Optional[str] = None,
    max_pages: int = 8,
) -> Optional[AboutStop]:
    """Build an "About <museum>" story stop, or None when no story can be sourced.

    Args:
        venue_name: resolved venue (e.g. "Griffin Museum of Photography").
        base_site_url: the venue's official URL (its own pages are the primary source).
        request_text: the raw tour request (drives architecture coverage).
        locality: "Winchester, MA" tail for a natural "in <place>" phrasing.
        address / coordinates: carried onto the stop unit when known.
        requested_stops / available_exhibition_stops: drive count semantics.
        fetcher: injectable (html, links) fetcher (fixtures in tests).
        wiki_provider: injectable venue→dict provider (Wikipedia/Wikidata); optional.
        corpus_text: pre-fetched visible text to use INSTEAD of fetching (tests may
            pass the venue corpus the generator already built). When given, the
            fetcher is not called.
        max_pages: cap on venue pages fetched when corpus_text is not supplied.

    Returns an AboutStop, or None when neither the venue's pages nor the wiki
    sources yield any story sentence (nothing is invented).
    """
    vn = _venue_core(venue_name) or (venue_name or "").strip()
    if not vn:
        return None

    domain = _domain_of(base_site_url)
    sources: List[str] = []
    _seen_src = set()

    def _add_source(u: str):
        if not u:
            return
        norm = u.rstrip("/")
        if norm in _seen_src:
            return
        _seen_src.add(norm)
        sources.append(u)

    # 1. Gather the venue's own story text (either supplied or fetched).
    text = ""
    if corpus_text is not None:
        text = corpus_text
        if base_site_url:
            _add_source(base_site_url)
    elif base_site_url:
        fetch = fetcher or _default_fetcher
        fetched: List[Tuple[str, str]] = []
        tried = 0
        for url in _candidate_story_urls(base_site_url):
            if tried >= max_pages:
                break
            tried += 1
            html, _links = fetch(url)
            if html and len(html) >= 80:
                fetched.append((html, url))
        text = "\n\n".join(_visible_text(h) for h, _ in fetched)
        for _, url in fetched:
            if _domain_of(url) == domain:
                _add_source(url)

    story_sentences = _collect_story_sentences(text, venue_name) if text else []

    # 2. Optional Wikipedia/Wikidata enrichment.
    wiki_summary = ""
    wiki_arch_notable = False
    wiki_arch_sentence = ""
    if wiki_provider is not None:
        try:
            wd = wiki_provider(venue_name) or {}
        except Exception:
            wd = {}
        wiki_summary = (wd.get("summary") or "").strip()
        wiki_arch_notable = bool(wd.get("architecturally_notable"))
        arch_bits = []
        if wd.get("architect"):
            arch_bits.append(f"{vn} was designed by {wd['architect']}")
        if wd.get("inception") and "architect" in " ".join(arch_bits).lower():
            arch_bits[-1] += f", and opened in {wd['inception']}"
        if arch_bits:
            wiki_arch_sentence = ". ".join(arch_bits) + "."
        for u in (wd.get("sources") or []):
            _add_source(u)

    # Nothing to tell → do NOT prepend an About stop (tour stays as-is).
    if not story_sentences and not wiki_summary:
        return None

    # 3. Decide architecture coverage.
    wants_arch = request_wants_architecture(request_text) or wiki_arch_notable
    arch_sentences: List[str] = []
    if wants_arch:
        if wiki_arch_sentence:
            arch_sentences.append(wiki_arch_sentence)
        arch_sentences.extend(_collect_architecture_sentences(text) if text else [])

    # 4. Compose; reject any narration that drifts into artwork framing.
    narration = _compose_about_narration(
        museum_name=venue_name, locality=locality,
        story_sentences=story_sentences, arch_sentences=arch_sentences,
        wiki_summary=wiki_summary, domain=domain)
    if not narration.strip():
        return None
    if looks_like_artwork_framing(narration):
        # Belt-and-braces: strip the offending sentence(s) and recompose. If the
        # offending content is unavoidable, drop the stop rather than ship an
        # artwork-framed About stop (the exact thing LOCAL-585 forbids).
        safe = [s for s in story_sentences if not looks_like_artwork_framing(s)]
        safe_arch = [s for s in arch_sentences if not looks_like_artwork_framing(s)]
        narration = _compose_about_narration(
            museum_name=venue_name, locality=locality,
            story_sentences=safe, arch_sentences=safe_arch,
            wiki_summary="" if looks_like_artwork_framing(wiki_summary) else wiki_summary,
            domain=domain)
        if not narration.strip() or looks_like_artwork_framing(narration):
            return None

    orientation = f"You are at {vn} — this opening stop is about the place itself."

    counts = should_count_toward_n(requested_stops, available_exhibition_stops)

    return AboutStop(
        museum_name=vn,
        narration=narration,
        orientation=orientation,
        sources=sources[:6],
        address=address,
        coordinates=coordinates,
        covers_architecture=bool(arch_sentences),
        counts_toward_n=counts,
    )


# Leading "<theme> tour in/at/of <building>" prefix to strip when a themed request
# is actually a tour held inside a named institution (the Athenaeum case).
_THEME_PREFIX_RE = re.compile(
    r"(?i)^.*?\btours?\s+(?:in|inside|within|at|of|through(?:out)?)\s+"
)


def clean_venue_request_name(location: str) -> str:
    """Extract the venue name from a themed-in-building request.

    "Art and Architectual tour in Boston Athenaeum, boston, ma" → "Boston Athenaeum".
    A plain venue string ("Griffin Museum of Photography, Winchester, MA") is left
    as-is apart from its trailing locality tail. Used so venue resolution and the
    About stop key on the building, not the theme words.
    """
    loc = (location or "").strip()
    m = _THEME_PREFIX_RE.search(loc)
    if m:
        loc = loc[m.end():].strip()
    # Keep only the leading (venue) comma-segment.
    return loc.split(",")[0].strip() or (location or "").split(",")[0].strip()


def default_wiki_provider(venue_name: str) -> Optional[dict]:
    """A dependency-light Wikipedia REST summary provider for the About stop.

    Returns {"summary", "sources", "architecturally_notable"} or None. Best-effort
    and fully optional: any network/parse failure yields None, so the About stop
    simply falls back to the venue's own pages. It never raises. Architecture
    notability is inferred from the summary text naming an architect / building
    style (a conservative signal, confirmed again from on-page sentences by the
    composer).
    """
    name = clean_venue_request_name(venue_name) or (venue_name or "").strip()
    if not name:
        return None
    try:
        import requests
        from urllib.parse import quote
        url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
               + quote(name.replace(" ", "_")))
        resp = requests.get(url, headers={"User-Agent": "Audioura/2.4 (+about)"},
                            timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        extract = (data.get("extract") or "").strip()
        if not extract:
            return None
        page_url = (((data.get("content_urls") or {}).get("desktop") or {}).get("page")
                    or f"https://en.wikipedia.org/wiki/{quote(name.replace(' ', '_'))}")
        notable = bool(_ARCH_SIGNAL_RE.search(extract))
        return {
            "summary": extract,
            "sources": [page_url],
            "architecturally_notable": notable,
        }
    except Exception:
        return None


def about_stop_unit(about: AboutStop) -> dict:
    """Convert an AboutStop into a plain stop-unit dict for stop_pool_assembly.

    The unit deliberately carries NO artist / year / type_specialty /
    specific_examples — the fields that make a block read as an artwork — so the
    assembler renders it as a museum story block, never an object label.
    """
    return {
        "title": f"About {about.museum_name}",
        "narration": about.narration,
        "orientation": about.orientation,
        "address": about.address or "",
        "coordinates": about.coordinates or "",
        "sources": list(about.sources),
        "_about_stop": True,
        "_pool_reused": False,
        "_counts_toward_n": about.counts_toward_n,
        "_covers_architecture": about.covers_architecture,
    }
