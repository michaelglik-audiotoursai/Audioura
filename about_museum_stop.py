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
    "extract_venue_address",
    "venue_bound_address",
    "build_shortfall_sentence",
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
#
# [LOCAL-599C] Also accept a pure IDENTITY claim that carries no founding keyword
# but states what the institution IS — "<Venue> is Boston's only free contemporary
# art museum", "… is the first / largest / leading … museum/gallery". MassArt's
# real About sentence ("The MassArt Art Museum (MAAM) is Boston's only free
# contemporary art museum …") has no 'founded/mission' token, so the r2 selector
# missed it and lifted the land acknowledgment instead; this verb matches it.
_STORY_VERBS = (
    r"is\s+(?:a|an|the|one|home|dedicated|devoted|located|among|housed|"
    r"new\s+england)|"
    r"is\s+[\w'’]+(?:\s+[\w'’]+){0,4}\s+"
    r"(?:only|first|oldest|largest|leading|premier|foremost|flagship)\b|"
    r"is\s+(?:the\s+)?(?:only|first|oldest|largest|leading|premier|foremost)\b|"
    r"was\s+(?:founded|established|built|created|incorporated|"
    r"the\s+first|designed)|were\s+founded|founded\s+(?:in|by)|established\s+(?:in|by)|"
    r"houses?|holds?|presents?|exhibits?|showcases?|preserves?|celebrates?|"
    r"is\s+devoted|offers?\s+|became\s+|opened\s+(?:in|its)|"
    r"has\s+(?:been|grown|championed)|champions?|promotes?|dedicated\s+to"
)

# [LOCAL-599C] NON-STORY institutional boilerplate that is NOT the museum's story:
# a land acknowledgment, a DEI / equity / accessibility statement, a cookie /
# privacy banner, a newsletter / email sign-up. These sentences often carry a
# story-signal word ("history", "mission", "community") and so slipped past the
# r2 selector — MassArt's land acknowledgment ("We make this land acknowledgment …
# the painful history of erasure …") was lifted as the museum's story. This is a
# deterministic CONTENT rule (what the sentence is ABOUT), run before any sentence
# is accepted as the institution's story. It is a vocabulary of boilerplate kinds,
# not a blocklist of any museum's words.
_NON_STORY_RE = re.compile(
    r"(?i)("
    r"land\s+acknowledg|acknowledge?ment\s+of\s+(?:the\s+)?(?:land|territor)|"
    r"traditional\s+(?:lands?|territor)|indigenous\s+(?:people|communit|tribe|land)|"
    r"ancestral\s+(?:lands?|homelands?)|unceded\s+(?:territor|lands?)|"
    r"we\s+(?:make|offer|recognize|acknowledge)\s+this\s+(?:land\s+)?acknowledg|"
    r"\bdiversity,?\s+equity|\bequity,?\s+(?:and\s+)?inclusion\b|\bDEI\b|"
    r"anti-?racis|accessibility\s+statement|committed\s+to\s+(?:accessibility|making)|"
    r"we\s+are\s+committed\s+to\s+(?:diversity|equity|inclusion|accessibility|anti)|"
    r"cookie|privacy\s+policy|your\s+privacy|"
    r"newsletter|sign\s*up|subscribe|email\s+(?:list|updates?)|mailing\s+list"
    r")")

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
    site_domain: str = ""      # [LOCAL-592 r2] venue domain for the visiting-info fallback pointer
    as_of: str = ""            # [LOCAL-592 r4] month-year honesty stamp ("October 2026")

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


# [LOCAL-602 r2 / D617 item 11] A FOUNDER-BIOGRAPHY sentence describes a PERSON,
# not the museum. The About stop must describe the institution. Two deterministic
# helpers decide: is the sentence's SUBJECT a person, and does the sentence state
# the MUSEUM'S OWN identity? Only the second rescues a person-subject sentence.

# Words that mark the kind of thing a museum IS — used to tell an institutional
# identity statement ("<Venue> is a contemporary art museum") from a person
# biography ("<Person> is an entrepreneur").
_MUSEUM_KIND_RE = re.compile(
    r"(?i)\b(museum|gallery|galleries|exhibition|experience|art\s+space|"
    r"installation|collection|library|archive|athenaeum|institute|institution|"
    r"foundation|center|centre|attraction|exhibit|exhibits|nonprofit|non-?profit|"
    r"organization|organisation)\b")

# A role/biography noun that marks the sentence subject as a PERSON (a founder,
# artist, executive), not an institution. "entrepreneur", "co-founder", "CEO" …
_PERSON_ROLE_RE = re.compile(
    r"(?i)\b(entrepreneur|businessman|businesswoman|investor|philanthropist|"
    r"founder|co-?founder|artist|designer|architect|collector|curator|director|"
    r"ceo|chief\s+executive|chairman|chairwoman|chairperson|president|"
    r"he\s+was|she\s+was|he\s+is|she\s+is|born\s+in|grew\s+up|"
    r"graduated|studied|earned\s+(?:a|his|her)\s+degree)\b")

# A trailing-honorific / given-name shape used to recognise a person as the
# leading subject: one-to-three Capitalised tokens, or a leading honorific.
_PERSON_SUBJECT_LEAD_RE = re.compile(
    r"^\s*(?:Mr|Mrs|Ms|Dr|Sir|Dame|Prof)\.?\s+[A-Z][a-z]+"
    r"|^\s*[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")


def _subject_is_person(sent: str, venue_first: str) -> bool:
    """Best-effort: is the sentence's grammatical SUBJECT a PERSON (not the venue)?

    Deterministic and conservative. True when the sentence LEADS with a
    person-name shape (optionally an honorific) that is NOT the venue's leading
    word, OR when it carries an explicit person-role / biography marker
    ("entrepreneur", "co-founder", "he was", "grew up", "studied") while NOT
    opening with the venue name. Used only to reject a founder biography that
    carries a story verb; a false negative merely leaves the existing behaviour.
    """
    s = (sent or "").strip()
    if not s:
        return False
    first = s.split()[0] if s.split() else ""
    vf = (venue_first or "").strip().lower()
    opens_with_venue = bool(vf and first.lower().strip(",.;:") == vf)
    if opens_with_venue:
        return False  # the venue is the subject — not a person
    lead_is_person = bool(_PERSON_SUBJECT_LEAD_RE.match(s))
    has_person_role = bool(_PERSON_ROLE_RE.search(s))
    # A participial founder lead ("Founded by Bradley Keywell, …") still describes
    # the museum's founding, so it is NOT a person subject by itself; require an
    # actual person lead or a biography marker.
    return lead_is_person or has_person_role


def _states_museum_identity(sent: str, venue_first: str) -> bool:
    """True when the sentence states the MUSEUM'S identity: it names the venue AND
    links it to a museum-kind word ("<Venue> is an immersive art museum").

    This is what rescues a sentence that also mentions a person — a genuine
    institutional identity statement is kept even if a founder is named in it.
    """
    s = (sent or "").strip()
    vf = (venue_first or "").strip().lower()
    names_venue = bool(vf and vf in s.lower())
    return names_venue and bool(_MUSEUM_KIND_RE.search(s))


def _is_story_sentence(sent: str, venue_core: str, venue_first: str) -> bool:
    s = sent
    if not (40 <= len(s) <= 300):
        return False
    if _CRUFT_RE.search(s):
        return False
    if _DANGLING_FINAL_RE.search(s):
        return False  # [r2] truncated object — never lift a half sentence
    # [LOCAL-599C] Reject institutional boilerplate that is NOT the museum's story:
    # a land acknowledgment, a DEI/accessibility statement, a cookie/privacy or
    # newsletter banner. These often carry a story-signal word ("history",
    # "community") and must be excluded BEFORE the signal/verb check, or the land
    # acknowledgment is lifted as the museum's story (the r2 defect).
    if _NON_STORY_RE.search(s):
        return False
    # [LOCAL-602 r2 / D617 item 11] Reject a FOUNDER BIOGRAPHY sentence: one whose
    # subject is a PERSON (the founder) and that describes the person, not the
    # museum. WNDR's About page was the Bradley Keywell biography — "Bradley
    # Keywell is a serial entrepreneur …", "Keywell co-founded …" — every such
    # sentence carries a story verb ("founded") yet says nothing about what the
    # MUSEUM is. The About stop describes an institution, not a person. A sentence
    # is kept only if it states the museum's own identity (names the venue AND an
    # institutional "is a/the <museum-kind>"); a person-subject sentence that does
    # not is dropped here, before the signal/verb check can rescue it on "founded".
    if _subject_is_person(s, venue_first) and not _states_museum_identity(s, venue_first):
        return False
    # Must be grammatically ABOUT the institution: either names the venue (or its
    # leading word) OR carries an institutional story verb. This keeps a stray
    # marketing fragment from being lifted as the museum's story.
    names_venue = bool(venue_first and venue_first.lower() in s.lower())
    has_story_verb = bool(re.search(r"(?i)\b(" + _STORY_VERBS + r")\b", s))
    # [LOCAL-599C] A genuine IDENTITY sentence that names the venue AND states what
    # it is ("<Venue> is Boston's only free contemporary art museum") qualifies as
    # the museum's story even with no founding/mission keyword — _STORY_SIGNAL_RE
    # is no longer a hard gate for a venue-named identity statement.
    if names_venue and has_story_verb:
        return True
    if not _STORY_SIGNAL_RE.search(s):
        return False
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
        if _NON_STORY_RE.search(s):
            continue  # [LOCAL-599C] land-ack / DEI / cookie boilerplate, not story
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
    as_of: str = "",
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
        site_domain=domain,
        as_of=(as_of or "").strip() or _default_month_stamp(),
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


# ── [LOCAL-592 r2] venue-bound address provenance ───────────────────────────
#
# Michael, tour 391 (D611): the Griffin's Stop 1 showed "Address: 1 Washington
# St, Winchester, MA 01890" — the Griffin is at 67 Shore Road. That address was a
# per-stop LLM/geocode GUESS (Phase 3B asks GPT for a "complete street address")
# that drifted to a town-centre address no source supports. For a CONTAINED venue
# (one museum/library building) every exhibition stop is physically at the venue,
# so its address is the VENUE's address — unless the exhibition's own page states
# a different (satellite) gallery address, in which case we keep that and the
# narration says so. These two pure functions encode that rule; they are
# unit-testable and have no network/LLM dependency.

# A US street address: "<house-number> <Capitalized street words> <suffix>
# [, City] [, ST] [ZIP]". The street-name words must be Capitalized tokens
# IMMEDIATELY between the number and the suffix — no lowercase connectors
# ("to", "a", "on", "where") — so a NARRATIVE sentence that happens to contain a
# year and a street name ("…moved in 1822 to a mansion on Pearl Street, where it
# remained…") is NOT mistaken for an address. The house number allows the common
# half/fraction and unit forms (10½, 10 1/2, 164, 2-4).
_STREET_SUFFIX = (
    r"street|st|road|rd|avenue|ave|boulevard|blvd|lane|ln|drive|dr|way|place|pl|"
    r"square|sq|court|ct|terrace|ter|highway|hwy|parkway|pkwy|circle|cir|row"
)
_STREET_ADDRESS_RE = re.compile(
    r"(\d{1,5}(?:\s*\u00bd|\s*1/2|(?:\s*[-–/]\s*\d{1,4}))?"      # house number (+ ½ / 1/2 / range)
    r"\s+(?:[A-Z][A-Za-z0-9.'’]*\.?\s+){1,3}"                    # 1–3 Capitalized street-name words
    r"(?:" + _STREET_SUFFIX + r")\.?)"                           # a street suffix
    r"(?:\s*,\s*([A-Z][A-Za-z.'’]+(?:\s+[A-Z][A-Za-z.'’]+){0,3}))?"  # optional , City
    r"(?:\s*,\s*([A-Za-z]{2}))?"                                  # optional , ST
    r"(?:\s+(\d{5}(?:-\d{4})?))?",                               # optional ZIP
    re.IGNORECASE,
)

# Case-insensitive suffix set used to confirm a candidate really ends in a street
# word (the regex above is IGNORECASE so "Street"/"street" both match).
_SUFFIX_WORDS = frozenset(_STREET_SUFFIX.split("|"))


def extract_venue_address(page_text: str, locality: str = "") -> str:
    """Lift the venue's OWN street address from its page text, or "".

    Scans the venue's visible page text for the FIRST genuine street address
    (house number + Capitalized street name + suffix) and returns it as a clean
    "<street>, <City>, <ST> <ZIP>" string when those tails are present. Pure and
    best-effort: anything not on the page is absent (nothing invented — D584). The
    Griffin "Main Gallery Address / 67 Shore Road, Winchester, Ma 01890" footer and
    the Athenaeum "located at 10½ Beacon Street" sentence are the canonical cases;
    a narrative clause with a stray year + street name is rejected.

    When ``locality`` is given and the matched address has no city/state tail, the
    locality is appended (properly cased) so the stop still carries a complete,
    page-grounded address.
    """
    if not page_text:
        return ""
    m = _STREET_ADDRESS_RE.search(page_text)
    if not m:
        return ""
    street = re.sub(r"\s+", " ", (m.group(1) or "")).strip().rstrip(",")
    city = (m.group(2) or "").strip()
    state = (m.group(3) or "").strip().upper()
    zipc = (m.group(4) or "").strip()
    parts = [street]
    tail = []
    if city:
        tail.append(city)
    if state:
        tail.append(state + (f" {zipc}" if zipc else ""))
    elif zipc:
        tail.append(zipc)
    addr = ", ".join([street] + tail) if tail else street
    has_tail = bool(city or state or zipc)
    if not has_tail and locality:
        addr = f"{street}, {normalise_locality(locality)}"
    return addr


def venue_bound_address(stop_address: str, venue_address: str,
                        stop_page_text: str = "") -> str:
    """Return the address a contained-venue stop should carry (provenance-safe).

    Rule (D611):
      • If ``stop_address`` is literally supported by this stop's own page
        (``stop_page_text`` — a satellite gallery address the exhibition states),
        keep it: it is sourced for THIS stop.
      • Otherwise prefer the sourced ``venue_address`` (the building everyone is
        standing in).
      • If there is no venue address, fall back to the stop_address unchanged
        (we never erase an address, but we never invent one either).

    A pure function: no network, no LLM. ``stop_page_text`` is matched
    case-insensitively on the address's informative tokens (the street number and
    first street word), so paraphrase/whitespace differences do not reject a real
    satellite address.
    """
    sa = (stop_address or "").strip()
    va = (venue_address or "").strip()
    if not va:
        return sa
    if not sa:
        return va
    if _address_supported_by_page(sa, stop_page_text):
        return sa
    return va


def _address_supported_by_page(address: str, page_text: str) -> bool:
    """True when the address's key tokens (number + first street word) are on the page."""
    if not address or not page_text:
        return False
    low = page_text.lower()
    m = re.match(r"\s*(\d{1,5})\s+([A-Za-z][A-Za-z.'’]*)", address)
    if not m:
        return False
    number, first_word = m.group(1), m.group(2).lower()
    return number in low and first_word in low


# ── [LOCAL-592] opening-section composer (the Stop-1 prolog, not a stop) ──────

# A short, natural lead-in to the practical facts so the opening does not read as
# a bare label. Mirrors the walking-tour prolog voice.
_PRACTICAL_LEAD = "Before you go in, a few practical notes."


def _visiting_fallback_sentence(domain: str) -> str:
    """[LOCAL-592 r2] The one-sentence website pointer used when the venue's own
    pages yield NO hours/admission the gate will pass.

    Michael (D611): opening hours and admission are "very important". When they
    cannot be sourced we must NOT invent them (D584) — we say so in a single
    sentence that points the listener at the venue's site, e.g.
    "Check opening hours and admission on bostonathenaeum.org before you go."
    With no known domain the pointer stays generic ("…on the museum's website…").
    """
    where = domain.strip() if domain and domain.strip() else "the museum's website"
    return f"Check opening hours and admission on {where} before you go."


# [LOCAL-592 r3] What a gated practical-facts string already STATES, so the website
# pointer covers ONLY the gap. Hours without a price (or a price without hours) is
# still worth saying (D611); the pointer must not repeat a field we already have.
_HOURS_PRESENT_RE = re.compile(
    r"(?i)(\bnoon\b|\bmidnight\b|\d\s*(?:am|pm)\b|\d{1,2}\s*[-–:]\s*\d|"
    r"open\s+daily|\bhours?\b|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|daily)"
)
_ADMISSION_PRESENT_RE = re.compile(
    r"(?i)([$€£]\s?\d|\b\d+\s?(?:usd|eur|gbp|dollars?|euros?)\b|"
    r"\bfree\b|\badmission\b|\bentry\b|\bticket)"
)


def _facts_state_hours(facts: str) -> bool:
    """True when the gated facts string already states opening hours / closed days."""
    return bool(_HOURS_PRESENT_RE.search(facts or ""))


def _facts_state_admission(facts: str) -> bool:
    """True when the gated facts string already states admission (a price or free)."""
    return bool(_ADMISSION_PRESENT_RE.search(facts or ""))


def _partial_pointer_sentence(facts: str, domain: str) -> str:
    """[LOCAL-592 r3] A website pointer that covers ONLY the field the venue's own
    pages did NOT give.

    - hours known, admission missing  → "Admission prices are listed on <site>."
    - admission known, hours missing  → "Opening hours are listed on <site>."
    - both known                      → "" (nothing to point to)
    - neither known                   → "" (the caller uses the full fallback)

    Never repeats a field we already stated, and never invents a value (D584).
    """
    where = domain.strip() if domain and domain.strip() else "the museum's website"
    has_hours = _facts_state_hours(facts)
    has_adm = _facts_state_admission(facts)
    if has_hours and not has_adm:
        return f"Admission prices are listed on {where}."
    if has_adm and not has_hours:
        return f"Opening hours are listed on {where}."
    return ""


# ── [LOCAL-592 r4] Spoken visiting composition (sentences, not a note) ───────

_CLOSED_SEG_RE = re.compile(r"(?i)^\s*closed\b")
_ADMISSION_SEG_RE = re.compile(
    r"(?i)([$€£]\s?\d|\bfree\b|\badmission\b|\bentry\b|\bticket)")
# An hours segment names a weekday range or a time, or opens with "open".
_HOURS_SEG_RE = re.compile(
    r"(?i)(\bnoon\b|\bmidnight\b|\d\s*(?:am|pm)\b|\bopen\b|\bdaily\b|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)")


def _short_venue(venue_name: str) -> str:
    """A natural spoken short name: 'the Griffin', 'the Boston Athenaeum'.

    Strips a trailing descriptor ("Museum of Photography", "Library") to the
    distinctive leading proper noun so the sentence reads aloud, and prefixes
    "the" when the name is not already article-led. Falls back to the full name.
    """
    vn = _venue_core(venue_name) or (venue_name or "").strip()
    if not vn:
        return "the museum"
    # Keep leading proper-noun words up to a generic descriptor.
    _GENERIC = {"museum", "gallery", "galleries", "library", "collection",
                "institute", "foundation", "center", "centre", "house", "society",
                "of", "the", "for", "and", "art", "arts", "photography"}
    words = vn.split()
    kept = []
    for w in words:
        if w.lower() in _GENERIC and kept:
            break
        kept.append(w)
    short = " ".join(kept) if kept else vn
    if short.lower().startswith(("the ", "a ", "an ")):
        return short
    return f"the {short}"


def _full_venue_for_hours(venue_name: str) -> str:
    """[LOCAL-599C] The museum's FULL name for the hours sentence, article-led.

    LEAD, r3: the hours sentence must name the museum in full — "The MassArt Art
    Museum is open …", never the stripped "The MassArt" (which read as a wrong
    name in r2). This keeps the venue's whole proper name (its ', City, ST' tail
    removed) and prefixes "The" when the name is not already article-led. Falls
    back to the spoken short name only when no full name is known.
    """
    vn = _venue_core(venue_name) or (venue_name or "").strip()
    if not vn:
        return "The museum"
    if vn.lower().startswith(("the ", "a ", "an ")):
        return vn[:1].upper() + vn[1:]
    return f"The {vn}"


def _lower_lead(seg: str) -> str:
    """Lower-case the first word of a mid-sentence clause unless it is a proper
    noun / acronym (keeps weekday names, '$', currency intact)."""
    s = seg.strip()
    if not s:
        return s
    first = s.split()[0]
    # Keep capitalised proper nouns (weekdays, Month names) and symbol/number leads.
    if first[:1].isupper() and not first.isupper() and first[1:].islower():
        # Weekday/Month proper nouns stay capitalised; a plain word like "Open"
        # becomes lower-case to continue the sentence.
        _KEEP = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday", "Daily"}
        if first in _KEEP:
            return s
        return s[:1].lower() + s[1:]
    return s


def _compose_hours_sentence(venue_short: str, hours_segs: List[str],
                            closed_segs: List[str]) -> str:
    """One spoken sentence: '<Venue> is open <days, time[; day group…]>, and closed
    on <day>.' Segments are kept VERBATIM (page-faithful), only stripped of a
    leading 'Open'/'Opening hours' label so the sentence does not stutter."""
    if not hours_segs and not closed_segs:
        return ""
    hours_body = ""
    if hours_segs:
        cleaned = []
        for seg in hours_segs:
            s = seg.strip().rstrip(".")
            # Drop a leading "Open"/"Opening hours"/"Hours" label — the sentence
            # already says "is open".
            s = re.sub(r"(?i)^\s*(?:opening\s+hours?|open(?:ing)?|hours?)\s*[:,]?\s*", "", s)
            if s:
                cleaned.append(s)
        hours_body = "; ".join(cleaned)
    closed_body = ""
    if closed_segs:
        parts = []
        for seg in closed_segs:
            s = seg.strip().rstrip(".")
            s = re.sub(r"(?i)^\s*closed\s*(?:on\s+)?", "", s)
            if s:
                parts.append(s)
        closed_body = ", ".join(parts)

    if hours_body and closed_body:
        return f"{venue_short} is open {hours_body}, and closed on {closed_body}."
    if hours_body:
        return f"{venue_short} is open {hours_body}."
    # Closed-day only: say it plainly (hours themselves were not sourced).
    return f"{venue_short} is closed on {closed_body}."


def _compose_admission_sentence(admission_segs: List[str]) -> str:
    """One spoken sentence stating admission, categories kept verbatim (never
    invented). 'Admission is $12 for adults and $8 for seniors, students and
    teachers.' A bare 'free' reads 'Admission is free.'"""
    if not admission_segs:
        return ""
    body = "; ".join(s.strip().rstrip(".") for s in admission_segs if s.strip())
    if not body:
        return ""
    low = body.lower()
    # If the segment already begins with "Admission"/"Entry", keep its own lead.
    if re.match(r"(?i)^\s*(?:admission|entry|tickets?)\b", body):
        sent = body
    elif low.startswith("free") or low == "free":
        sent = f"Admission is {body}"
    else:
        sent = f"Admission is {body}"
    return sent.rstrip(".") + "."


def _default_month_stamp() -> str:
    """The current month-year stamp ('October 2026') for the honesty signal.

    Reuses museum_overview._default_as_of so the Stop-1 visiting signal and the
    rung-3 overview dateline share one source of truth; falls back to a local
    strftime if that module is unavailable at import time.
    """
    try:
        from museum_overview import _default_as_of
        return _default_as_of()
    except Exception:
        import datetime
        return datetime.date.today().strftime("%B %Y")


def _source_month_signal(domain: str, as_of: str) -> str:
    """The D584/D582 honesty signal, spoken: 'as listed on <domain> in <month>'."""
    where = domain.strip() if domain and domain.strip() else "the museum's website"
    stamp = (as_of or "").strip()
    if stamp:
        return f"as listed on {where} in {stamp}"
    return f"as listed on {where}"


def _compose_visiting_sentences(facts: str, venue_name: str, domain: str,
                                as_of: str) -> str:
    """[LOCAL-592 r4] Turn the gated practical-facts string into SPOKEN sentences.

    r3 emitted a note: "Before you go in, a few practical notes. Closed on Monday.
    Noon–4 PM. $12." r4 composes it as speech, keeps the day range WITH the hours
    (bound by the extractor), keeps the admission categories the page gives, and
    closes with the source + month honesty signal:

        "The Griffin is open Tuesday through Sunday, Noon–4 PM, and closed on
         Monday. Admission is $12 for adults and $8 for seniors, students and
         teachers, as listed on griffinmuseum.org in October 2026."

    Nothing is invented: every weekday, time, price and category is carried
    verbatim from the gated ``facts`` (built upstream under the D584 contract).
    """
    facts = (facts or "").strip()
    if not facts:
        return ""
    # Split into top-level segments on sentence boundaries. Keep ';' inside a
    # segment so an hours line with several day groups stays one segment.
    segs = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\.\s+", facts) if s.strip()]
    if not segs:
        segs = [facts]

    hours_segs: List[str] = []
    closed_segs: List[str] = []
    admission_segs: List[str] = []
    for seg in segs:
        if _CLOSED_SEG_RE.search(seg):
            closed_segs.append(seg)
        elif _ADMISSION_SEG_RE.search(seg) and not _HOURS_SEG_RE.search(
                re.sub(r"(?i)admission|entry|ticket|free", "", seg)):
            admission_segs.append(seg)
        elif _HOURS_SEG_RE.search(seg):
            hours_segs.append(seg)
        else:
            # Unclassifiable — keep it as an admission-ish trailing note only if it
            # carries a price; otherwise drop (never invent).
            if _ADMISSION_SEG_RE.search(seg):
                admission_segs.append(seg)

    # [LOCAL-599C] The HOURS sentence names the museum in FULL ("The MassArt Art
    # Museum is open …"), per LEAD r3 — never the stripped short name.
    venue_full = _full_venue_for_hours(venue_name)
    hours_sentence = _compose_hours_sentence(venue_full, hours_segs, closed_segs)
    adm_sentence = _compose_admission_sentence(admission_segs)
    signal = _source_month_signal(domain, as_of)

    out_sentences: List[str] = []
    if hours_sentence:
        out_sentences.append(hours_sentence)
    if adm_sentence:
        # Attach the honesty signal to the admission sentence (it carries the price,
        # the most volatile fact). "… teachers, as listed on <domain> in <month>."
        adm_sentence = adm_sentence.rstrip(".") + f", {signal}."
        out_sentences.append(adm_sentence)
    elif hours_sentence:
        # No admission to carry the signal → attach it to the hours sentence.
        out_sentences[-1] = out_sentences[-1].rstrip(".") + f", {signal}."
    composed = " ".join(out_sentences).strip()
    # The visiting block opens its own paragraph — capitalise its first letter
    # ("the Griffin is open" → "The Griffin is open") without touching a leading
    # price/number or an already-capital proper noun.
    if composed and composed[0].islower():
        composed = composed[0].upper() + composed[1:]
    return composed


def build_shortfall_sentence(venue_name: str, exhibitions_on_view: int,
                             delivered_stops: int,
                             requested_stops: Optional[int]) -> str:
    """[LOCAL-600 / D616] One plain sentence telling the listener, honestly, why a
    site-first exhibition tour delivers fewer stops than they asked for.

    LEAD (D616): "When verified on-view material can't reach N, deliver the verified
    stops and say so in Stop 1's opening section. One plain sentence, from the real
    counts: 'MassArt Art Museum currently has 3 exhibitions on view, so this tour
    has 5 stops rather than the 7 you asked for.'"

    Returns that sentence, or "" when there is no shortfall to announce:
      * ``requested_stops`` is unknown/zero, or
      * ``delivered_stops`` >= ``requested_stops`` (the ask was met — D611's exact
        N holds and NO sentence is emitted), or
      * the counts are not positive integers.

    Pure and deterministic; no network, no LLM. The venue name is used as given
    (its ', City, ST' tail trimmed) so the sentence names the museum, not the raw
    request string.
    """
    try:
        req = int(requested_stops) if requested_stops is not None else 0
        delivered = int(delivered_stops)
        shows = int(exhibitions_on_view)
    except (TypeError, ValueError):
        return ""
    if req <= 0 or delivered <= 0:
        return ""
    if delivered >= req:
        return ""  # the ask was met — D611 exact N, no sentence
    vn = _venue_core(venue_name) or (venue_name or "").strip() or "This museum"
    # "has 1 exhibition on view" / "has 3 exhibitions on view"
    if shows >= 1:
        show_clause = (f"{vn} currently has {shows} "
                       f"exhibition{'s' if shows != 1 else ''} on view, so ")
    else:
        # No distinct on-view show count available: still be honest about the gap
        # without inventing a show count.
        show_clause = f"{vn} has a limited number of exhibitions on view, so "
    stop_word_d = "stop" if delivered == 1 else "stops"
    return (f"{show_clause}this tour has {delivered} {stop_word_d} "
            f"rather than the {req} you asked for.")


def build_opening_section(about: Optional["AboutStop"],
                          shortfall_sentence: str = "") -> str:
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
    carried on ``about.practical_facts``; they are appended verbatim.

    [r2] Visiting information is "very important" (D611). When the venue's own pages
    yield NO gate-passing hours/admission, the section does NOT go silent on them:
    it appends a single honest pointer to the venue's website
    ("Check opening hours and admission on <domain> before you go.") rather than
    inventing any hours or prices (D584).

    [r3] STATE WHAT IS KNOWN. Hours without a price (or a price without hours) is
    still stated. The website pointer then covers ONLY what is missing
    ("Admission prices are listed on <site>." / "Opening hours are listed on
    <site>."), and is omitted entirely when both are known. When ``about`` is None
    the section is empty.

    [r4] IT READS AS SPEECH, with the day range bound to the hours. The gated facts
    are no longer appended as a note ("… a few practical notes. Noon–4 PM. $12.")
    but composed into sentences by ``_compose_visiting_sentences``:
    "<Venue> is open <days, time>, and closed on <day>. Admission is <price> for
    <categories>, as listed on <domain> in <month>." The source + month honesty
    signal (D584/D582) and the admission categories the page gives are preserved;
    nothing is invented.

    The caller folds the returned text into Stop 1 as its opening SECTION (rendered
    before the Orientation), so a request for N stops still delivers exactly N: this
    section adds zero stops.

    [LOCAL-600 / D616] ``shortfall_sentence`` — when the site-first exhibition path
    could not reach the requested N from verified on-view material, the caller
    passes the one honest sentence from build_shortfall_sentence (e.g. "MassArt Art
    Museum currently has 3 exhibitions on view, so this tour has 5 stops rather than
    the 7 you asked for."). It is placed as its OWN paragraph right after the About
    story and before the practical notes, so the listener hears the scope up front.
    Empty string (the default, and whenever the ask was met) adds nothing.
    """
    if about is None:
        return ""
    parts: List[str] = []
    narration = (about.narration or "").strip()
    if narration:
        parts.append(narration)
    _shortfall = (shortfall_sentence or "").strip()
    if _shortfall:
        parts.append(_shortfall)
    facts = (about.practical_facts or "").strip()
    domain = getattr(about, "site_domain", "")
    as_of = getattr(about, "as_of", "") or ""
    venue_name = getattr(about, "museum_name", "") or ""
    if facts:
        # [r4] Compose the visiting information as spoken sentences (day range bound
        # to the hours, source + month honesty signal).
        practical = _compose_visiting_sentences(facts, venue_name, domain, as_of)
        if not practical:
            # Defensive: if composition yields nothing, fall back to a plain
            # statement of the gated facts (still never invented).
            practical = facts if facts.endswith((".", "!", "?")) else facts + "."
        # [r3] Point to the site ONLY for the field the page did not give.
        pointer = _partial_pointer_sentence(facts, domain)
        if pointer:
            practical = f"{practical} {pointer}"
        parts.append(practical)
    else:
        # [r2] No sourced hours/admission → honest website pointer, never invented.
        parts.append(_visiting_fallback_sentence(domain))
    section = "\n\n".join(p for p in parts if p).strip()
    # Belt-and-braces: the opening section must never read as an artwork label.
    if section and looks_like_artwork_framing(section):
        # Drop only the offending About narration; keep the shortfall note and the
        # practical facts, which are page-literal and cannot be artwork-framed.
        _rebuilt: List[str] = []
        if _shortfall:
            _rebuilt.append(_shortfall)
        if facts:
            practical = _compose_visiting_sentences(facts, venue_name, domain, as_of)
            if not practical:
                practical = facts if facts.endswith((".", "!", "?")) else facts + "."
            pointer = _partial_pointer_sentence(facts, domain)
            _rebuilt.append(f"{practical} {pointer}".strip() if pointer else practical)
        else:
            _rebuilt.append(_visiting_fallback_sentence(domain))
        return "\n\n".join(p for p in _rebuilt if p).strip()
    return section
