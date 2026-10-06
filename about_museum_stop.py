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
    "build_opening_section",
    "looks_like_artwork_framing",
    "should_count_toward_n",
    "request_wants_architecture",
    "clean_venue_request_name",
    "default_wiki_provider",
    "has_dangling_object_sentence",
    "dedupe_sentences",
    "normalise_locality",
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

# ── Sentence hygiene (LOCAL-585 r2) ───────────────────────────────────────────
#
# A sentence whose final content word still expects an object was truncated by
# the extractor — the object lived in a clause the sentence splitter dropped. The
# Athenaeum ship had "…a group of Bostonians who produced a magazine called." The
# object ("The Monthly Anthology") was gone, so the sentence ended mid-thought.
# These tokens, when they are the LAST word before the terminal period, mean the
# object is missing: name/call/title it X, known/such/referred-to AS X, etc.
_DANGLING_FINAL_RE = re.compile(
    r"(?i)(?:^|\s)("
    r"called|named|titled|entitled|dubbed|nicknamed|"       # "called X"
    r"known\s+as|referred\s+to\s+as|such\s+as|"             # "known as X"
    r"including|featuring|comprising|consisting\s+of|containing|"  # "including X"
    r"designed\s+by|built\s+by|founded\s+by|created\s+by|"  # "designed by X"
    r"and|or|but|with|the|an"                               # bare trailing connector/article
    r")\s*[.!?]?\s*$"
)

# US state-abbreviation → full name, so a request tail like "boston, ma" is spoken
# as "Boston, Massachusetts" (mirrors geocode_stops._STATE_ABBR, extended).
_US_STATE_ABBR = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas",
    "ut": "Utah", "vt": "Vermont", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming", "dc": "D.C.",
}


def has_dangling_object_sentence(text: str) -> bool:
    """True when ANY sentence in `text` ends mid-thought (object was cut).

    The last content token of the sentence is a verb/preposition/determiner that
    still expects an object (e.g. "…a magazine called."). Such a sentence was
    truncated by extraction and must be completed from the source or dropped — it
    is never shipped. Pure and side-effect free so tests and callers can assert it.
    """
    for sent in _hygiene_split(text):
        if _DANGLING_FINAL_RE.search(sent):
            return True
    return False


def _hygiene_split(text: str) -> List[str]:
    """Abbreviation-safe sentence split, reusing the shared helper when available."""
    try:
        from sentence_split import split_sentences as _ss
        return [s for s in _ss(text or "") if s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def _dedup_key(sentence: str) -> str:
    """Normalised comparison key: lowercase, punctuation/whitespace-flattened."""
    s = (sentence or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def dedupe_sentences(sentences: List[str]) -> List[str]:
    """Drop near-identical (normalised) repeats, keeping first occurrence order.

    Cross-section: the same architect sentence appearing once in the history and
    again in the architecture block collapses to one. Also drops any sentence that
    ends mid-thought (a truncated object) rather than shipping it.
    """
    out: List[str] = []
    seen = set()
    for sent in sentences:
        s = (sent or "").strip()
        if not s:
            continue
        if _DANGLING_FINAL_RE.search(s):
            continue  # truncated object — never ship a half sentence
        key = _dedup_key(s)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def normalise_locality(locality: str) -> str:
    """Properly case a locality tail and expand a US state abbreviation.

    "boston, ma" → "Boston, Massachusetts"; "nice, france" → "Nice, France".
    An empty/blank input returns "". Non-US tails are title-cased but otherwise
    left as the request gave them (we only expand recognised US state codes).
    """
    loc = (locality or "").strip()
    if not loc:
        return ""
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    out: List[str] = []
    for p in parts:
        low = p.lower()
        if low in _US_STATE_ABBR:
            out.append(_US_STATE_ABBR[low])
        elif re.fullmatch(r"[A-Za-z.]{2,4}", p) and "." in p:
            out.append(p.upper())            # keep dotted acronyms like U.S.A.
        else:
            out.append(_titlecase_place(p))
    return ", ".join(out)


def _titlecase_place(word: str) -> str:
    """Title-case a place word, keeping small connectors lower unless leading."""
    small = {"of", "the", "and", "upon", "on", "de", "la", "le", "du", "des"}
    toks = word.split()
    cased = []
    for i, t in enumerate(toks):
        if i > 0 and t.lower() in small:
            cased.append(t.lower())
        elif t.isupper() and len(t) <= 3:
            cased.append(t)                  # already an acronym (NY handled above)
        else:
            cased.append(t[:1].upper() + t[1:].lower() if t else t)
    return " ".join(cased)


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
    practical_facts: str = ""  # [LOCAL-592] gated opening-hours/admission/closed-days

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
    """[LOCAL-592] The About content is NEVER a stop — so it never counts.

    Michael, 2026-10-06 (binding): "If a user asks for x number of stops, we are
    supposed to generate exactly x number of stops. In Walking tours we have the
    Overall section and that section is the start of Stop 1 … The same must be
    true with museum, restaurant, etc." The museum's About story and the practical
    facts are the OPENING SECTION of Stop 1 (mirroring the walking-tour prolog),
    not a standalone stop. They cannot add to or subtract from the requested N.

    This supersedes the LOCAL-585 "extra opener / thin-exhibitions" branch: the
    function now returns False for every input. It is kept (always-False) so the
    orchestrator can keep calling it and existing imports do not break, and so a
    request for N always delivers exactly N stops. The two arguments are accepted
    and ignored.
    """
    return False


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
    if _DANGLING_FINAL_RE.search(s):
        return False  # [r2] truncated object — never lift a half sentence
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
        if _DANGLING_FINAL_RE.search(s):
            continue  # [r2] truncated object — never lift a half sentence
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

    [r2] Sentence hygiene: the locality is properly cased / state-expanded, the
    story and architecture sentences are de-duplicated ACROSS sections (so the
    architect sentence can never appear twice), and any sentence truncated to a
    dangling object is dropped before it is spoken.
    """
    vn = _venue_core(museum_name) or museum_name
    where = f" in {normalise_locality(locality)}" if locality else ""
    parts: List[str] = []

    # Opening orientation: this is the museum's story, not an object label.
    parts.append(
        f"Before we look at anything on the walls, here is the story of {vn}{where} "
        f"itself — who created it, why it exists, and what it is known for.")

    # [r2] Build the body as ONE de-duplicated pool so a sentence shared between
    # the history (story) and the building (architecture) section is spoken once.
    wiki_sents = _hygiene_split(wiki_summary.strip()) if wiki_summary else []
    body_story = dedupe_sentences(wiki_sents + list(story_sentences))
    seen_body = {_dedup_key(s) for s in body_story}
    body_arch = [s for s in dedupe_sentences(list(arch_sentences))
                 if _dedup_key(s) not in seen_body]

    parts.extend(body_story)

    if body_arch:
        parts.append("A word about the building you are standing in.")
        parts.extend(body_arch)

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
    practical_facts: str = "",
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
        practical_facts: [LOCAL-592] an ALREADY-GATED practical-facts string
            (opening hours, admission, closed days) sourced and venue-bound by the
            caller through the LOCAL-584 gate (practical_facts_gate.gate_formatted_facts).
            It is carried verbatim onto the AboutStop and placed in the opening
            section by build_opening_section. Nothing here invents or re-sources
            it: the honesty contract (state only what the venue's page supports)
            is enforced upstream, exactly as for the restaurant/museum facts.

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
        practical_facts=(practical_facts or "").strip(),
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


# ── [LOCAL-592] opening-section composer (the Stop-1 prolog, not a stop) ──────

# A short, natural lead-in to the practical facts so the opening does not read as
# a bare label. Mirrors the walking-tour prolog voice.
_PRACTICAL_LEAD = "Before you go in, a few practical notes."


def build_opening_section(about: Optional["AboutStop"]) -> str:
    """[LOCAL-592] Compose the OPENING SECTION of Stop 1 for a single-venue tour.

    Michael, 2026-10-06 (binding): the museum's "About" content and the practical
    facts (opening hours, admission, closed days) are the FIRST SECTION of Stop 1 —
    exactly as the walking tour's Overall section is the start of Stop 1 — never a
    standalone stop. This function returns that section as a single block of
    prose:

        <About story: founder, why it exists, history, architecture when relevant>
        Before you go in, a few practical notes. <hours. admission. closed days.>

    The About narration is already sourced and artwork-framing-free (build_about_stop).
    The practical facts are already gated/venue-bound (LOCAL-584) by the caller and
    carried on ``about.practical_facts``; they are appended verbatim. Nothing is
    invented: when ``about`` is None the section is empty; when there are no
    practical facts, only the About story is returned (silence is correct — D584).

    The caller folds the returned text into Stop 1 (its narration/orientation lead),
    so a request for N stops still delivers exactly N: this section adds zero stops.
    """
    if about is None:
        return ""
    parts: List[str] = []
    narration = (about.narration or "").strip()
    if narration:
        parts.append(narration)
    facts = (about.practical_facts or "").strip()
    if facts:
        # Ensure the facts end as a clean sentence group.
        facts_block = facts if facts.endswith((".", "!", "?")) else facts + "."
        parts.append(f"{_PRACTICAL_LEAD} {facts_block}")
    section = "\n\n".join(p for p in parts if p).strip()
    # Belt-and-braces: the opening section must never read as an artwork label.
    if section and looks_like_artwork_framing(section):
        # Drop only the offending About narration; keep the practical facts, which
        # are page-literal and cannot be artwork-framed.
        if facts:
            return f"{_PRACTICAL_LEAD} {facts if facts.endswith(('.', '!', '?')) else facts + '.'}"
        return ""
    return section
