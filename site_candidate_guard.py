"""site_candidate_guard.py — [LOCAL-653] Site-listed candidates get the SAME guards
as Wikidata candidates.

The Courtauld (tours 586 OFF / 592 ON, 2026-10-09, fresh): both arms shipped
``Van Gogh's iconic Self-Portrait with Bandaged Ear``, ``Manet's A Bar at the
Folies-Bergère`` and ``Courtauld Institute`` as stops. The Wikidata path had
already dropped these as ``not_in_collection`` (artwork_selection_guard), but the
SITE-LISTED / venue_corpus canonical-title path fed them back in: that path only
filtered chrome, rooms and the venue ITSELF, so

  * a SIBLING institution ("Courtauld Institute" for "The Courtauld Gallery"),
  * an ARTIST NAME ALONE ("Paul Cézanne", "Georges Seurat", "Edgar Degas"),
  * and MARKETING PREFIXES ("Van Gogh's iconic …", "Manet's …") on otherwise-real
    titles

all slipped through. And ``room_candidate_guard.is_venue_itself_title`` /
``junk_title_guard.is_junk_page_title`` BOTH failed on "Courtauld Institute" and
even "Courtauld Gallery" once the venue name carried a location suffix
("The Courtauld Gallery, London, United Kingdom") — the suffix defeated the
venue-name token comparison, so even the venue's own name reached the pool.

This module is the deterministic lever against all three, and is pure (no network,
no LLM, no DB) so every rule is unit-testable and cannot drift at runtime.

  venue_core_name(venue_name)              -> str
      The venue's distinctive name with any trailing ", City, Country" location
      segments and institution-type tail stripped — "The Courtauld Gallery,
      London, United Kingdom" → "courtauld". Used so the venue / sibling guards
      compare against the real name, not the location-padded form.

  is_venue_or_sibling_title(title, venue)  -> bool
      True when ``title`` names the venue itself OR a sibling institution that
      shares the venue's distinctive name but a different institution noun
      ("Courtauld Institute" vs "The Courtauld Gallery"), OR a bare site brand.
      Location-suffix robust.

  is_artist_name_alone(title, artist_names) -> bool
      True when the whole title is just a PERSON / ARTIST name. The PRIMARY,
      precise signal is an exact match against one of the venue's own creator
      names (from the SPARQL works) — "Paul Cézanne", "Georges Seurat", "Edgar
      Degas". A bare-name SHAPE fallback is available but OFF by default
      (``allow_shape_fallback``) because real works are 2–3 capitalised tokens too
      ("Mont Sainte-Victoire", "Peach Trees"); the caller enables it only when it
      can afford the recall/precision trade. An artist name is not a work; the
      caller resolves it to a held work or drops it.

  strip_marketing_prefix(title, known_titles=None) -> (clean_title, artist)
      Strip a leading possessive-artist + optional adjective marketing prefix
      ("Van Gogh's iconic ", "Manet's ", "Édouard Manet's famous painting ",
      "Courbet's provocative ") when the REMAINDER still reads as a work title
      (and, when ``known_titles`` is given, matches one). Returns the cleaned
      title and the stripped artist (kept for the narration). A real possessive
      work title ("Whistlejacket", "A Lady's Portrait") is never touched — the
      prefix must be ``<Name>'s`` optionally followed by ONE adjective/noun of
      marketing filler, and the tail must survive as a plausible title.

  filter_site_candidates(titles, venue_name, artist_names=(), ...) -> (kept, dropped)
      Split a canonical-title set / candidate list by the three guards above plus
      junk_title_guard, returning kept and dropped-with-reason. Order-preserving
      and pure. SPARQL/Wikidata-confirmed titles can be protected via
      ``protected_titles`` so a legitimate work is never dropped by a heuristic.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = [
    "venue_core_name",
    "is_venue_or_sibling_title",
    "is_artist_name_alone",
    "strip_marketing_prefix",
    "filter_site_candidates",
]

# ─────────────────────────────────────────────────────────────────────────────
# Normalisation. Lowercase, strip accents to the base letter, drop a leading
# article, collapse punctuation/whitespace. Mirrors room_candidate_guard._norm_venue
# but accent-insensitive so "Cézanne" and "Cezanne" compare equal.
# ─────────────────────────────────────────────────────────────────────────────
_LEAD_ARTICLE_RE = re.compile(
    r"(?i)^\s*(?:the|le|la|les|das|der|die|il|lo|el|los|las|l['’])\s+")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("\xa0", " ").replace("\u202f", " ").strip()
    if not t:
        return ""
    t = _LEAD_ARTICLE_RE.sub("", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return " ".join(t.lower().split())


# Institution-type nouns that, trailing a venue's distinctive name, still name an
# INSTITUTION (not a work): "Gallery", "Institute", "Museum", "Foundation". Shared
# with room_candidate_guard's intent; kept here so this module is self-contained.
_INSTITUTION_NOUNS = frozenset({
    "museum", "museums", "gallery", "galleries", "collection", "collections",
    "institute", "institution", "foundation", "trust", "centre", "center",
    "haus", "musee", "musée", "museo", "pinakothek", "kunsthalle", "kunstmuseum",
    "gemaldegalerie", "gemäldegalerie", "galerie", "fundacion", "fundación",
    "society", "academy", "school", "university", "college",
})

# Location filler that pads a scraped venue string: cities/countries and generic
# geo words. Only used to STRIP a trailing ", City, Country" tail, never to match
# a work title.
_LOCATION_FILLER = frozenset({
    "united", "kingdom", "states", "america", "usa", "uk", "us",
    "england", "scotland", "wales", "ireland", "britain", "great",
    "london", "paris", "vienna", "wien", "amsterdam", "madrid", "berlin",
    "rome", "roma", "florence", "firenze", "venice", "venezia", "milan",
    "munich", "münchen", "munchen", "new", "york", "city", "boston",
    "washington", "dc", "baltimore", "austria", "france", "germany",
    "italy", "italia", "spain", "españa", "netherlands", "holland",
})


def venue_core_name(venue_name: str) -> str:
    """Return the venue's DISTINCTIVE name, lowercased/accent-stripped, with any
    trailing location segments (", London, United Kingdom") and the institution
    tail ("Gallery") removed. "The Courtauld Gallery, London, United Kingdom" →
    "courtauld". Pure.

    Robust to the production bug where the venue arg carried a city/country tail,
    which previously defeated every token-equality venue check downstream.
    """
    raw = str(venue_name or "")
    # 1. The venue's proper name is the FIRST comma-segment; a comma almost always
    #    introduces a location ("…, London, United Kingdom") or an institutional
    #    qualifier, never part of the distinctive name. Keep the first segment,
    #    but if trailing segments are plainly location filler peel them explicitly
    #    too (handles a name that itself contains a comma — rare).
    segs = [s.strip() for s in raw.split(",") if s.strip()]
    if len(segs) > 1:
        # Peel trailing pure-location segments; whatever remains, keep only the
        # first segment as the distinctive name (locations never lead).
        while len(segs) > 1:
            tail_tokens = _norm(segs[-1]).split()
            if tail_tokens and all(tok in _LOCATION_FILLER for tok in tail_tokens):
                segs = segs[:-1]
                continue
            break
        core = segs[0]
    else:
        core = segs[0] if segs else raw
    # 2. Normalise and strip the trailing institution noun(s).
    toks = _norm(core).split()
    while len(toks) > 1 and toks[-1] in _INSTITUTION_NOUNS:
        toks = toks[:-1]
    return " ".join(toks)


# Site-brand / marketing phrases that are never a work (a bare brand string the
# scraper lifted from the chrome). Matched as the WHOLE normalised title.
_SITE_BRAND_PHRASES = frozenset({
    "official site", "official website", "homepage", "home page", "website",
})

# Institution-GLUE words that connect an institution name to its type
# ("Institute OF ART", "Museum OF FINE ARTS", "Centre FOR THE Arts"). Allowed in a
# sibling remainder — alongside the institution nouns — so "Courtauld Institute of
# Art" is recognised as the sibling. Deliberately tiny: these never carry a work's
# distinctive content on their own.
_INSTITUTION_GLUE = frozenset({
    "of", "the", "for", "and", "art", "arts", "fine", "modern", "contemporary",
    "decorative", "applied", "visual",
})


def is_venue_or_sibling_title(title: str, venue_name: str = "") -> bool:
    """True when ``title`` names the VENUE itself or a SIBLING institution — an
    institution string that carries the venue's distinctive name plus a (possibly
    different) institution noun — or a bare site brand. Location-suffix robust.

    "Courtauld Institute" / "Courtauld Gallery" / "The Courtauld" → True for venue
    "The Courtauld Gallery, London, United Kingdom". A real work that merely begins
    with the venue name but continues with more, non-institution words
    ("Courtauld Family Portrait") → False. Pure.
    """
    nt = _norm(title)
    if not nt:
        return False
    if nt in _SITE_BRAND_PHRASES:
        return True

    core = venue_core_name(venue_name)
    if not core:
        return False
    core_toks = core.split()

    toks = nt.split()
    # The title must START with the full venue core name...
    if toks[: len(core_toks)] != core_toks:
        return False
    rest = toks[len(core_toks):]
    # No remainder → the venue itself. Otherwise it is a sibling only when the
    # remainder is institution noun(s) + optional institution-glue words and
    # contains AT LEAST ONE institution noun — nothing that could be a work word.
    # ("courtauld" + "institute"/"gallery" → sibling; "courtauld" + "institute of
    # art" → sibling; "courtauld" + "family portrait" → a work, kept.)
    if not rest:
        return True
    if any(tok not in _INSTITUTION_NOUNS and tok not in _INSTITUTION_GLUE
           for tok in rest):
        return False
    return any(tok in _INSTITUTION_NOUNS for tok in rest)


# ─────────────────────────────────────────────────────────────────────────────
# Artist name alone.
# ─────────────────────────────────────────────────────────────────────────────

# Work-signal words: if a title contains any of these it is NOT a bare personal
# name, however name-like its other tokens ("Portrait of a Man", "Madame X",
# "Lady with a Parasol"). Kept broad; the bare-name heuristic is a fallback only.
_WORK_SIGNAL_RE = re.compile(
    r"(?i)\b("
    r"portrait|self\s*portrait|madonna|virgin|christ|saint|st|study|sketch|"
    r"nude|landscape|still\s*life|view|interior|bust|statue|head|figure|"
    r"composition|untitled|allegory|triptych|panel|altarpiece|fresco|mural|"
    r"the|a|an|of|with|at|in|and|le|la|les|un|une|nature\s*morte"
    r")\b")

# A bare personal-name shape: 2–3 capitalised tokens, optionally a lowercase
# particle ("van", "de", "von"), nothing else. "Paul Cézanne", "Vincent van
# Gogh", "Georges Seurat", "Edgar Degas". Allows accented letters.
_NAME_PARTICLES = frozenset({
    "van", "von", "de", "del", "della", "di", "da", "la", "le", "du", "des",
    "der", "den", "el", "dos", "das", "ter", "ten", "van der", "van den",
})


def _looks_like_bare_person_name(title: str) -> bool:
    t = str(title or "").replace("\xa0", " ").replace("\u202f", " ").strip()
    if not t:
        return False
    # Reject anything with digits, parentheses, or sentence punctuation.
    if re.search(r"[0-9()\[\]:;!?]", t):
        return False
    tokens = t.split()
    if not (2 <= len(tokens) <= 4):
        return False
    cap_tokens = 0
    for tok in tokens:
        low = tok.lower().strip(".'’-")
        if low in _NAME_PARTICLES:
            continue
        # Each non-particle token must start with an uppercase (or accented
        # uppercase) letter and be alphabetic.
        first = tok[0]
        if not first.isalpha() or first.lower() == first:
            return False
        core = tok.strip(".'’-")
        if not core.replace("-", "").isalpha():
            return False
        cap_tokens += 1
    if cap_tokens < 2:
        return False
    # Must not carry a work-signal word.
    if _WORK_SIGNAL_RE.search(t):
        return False
    return True


def is_artist_name_alone(
    title: str,
    artist_names: Iterable[str] = (),
    *,
    allow_shape_fallback: bool = False,
) -> bool:
    """True when the whole title is just a PERSON / ARTIST name, not a work.

    PRIMARY (precise, default): the normalised title exactly matches one of
    ``artist_names`` — the venue's own creator labels, from the SPARQL works
    ("Paul Cézanne", "Georges Seurat", "Edgar Degas"). This is the only signal
    used by default because it cannot misfire on a real work.

    FALLBACK (``allow_shape_fallback=True``): the title also reads as a bare
    personal name (2–3 capitalised tokens, optional particle, no work-signal
    word). OFF by default — real works share this shape ("Mont Sainte-Victoire",
    "Peach Trees"), so enabling it trades precision for recall and must be a
    caller's explicit choice. Pure.
    """
    nt = _norm(title)
    if not nt:
        return False
    known = {_norm(a) for a in (artist_names or []) if a}
    known.discard("")
    if nt in known:
        return True
    if allow_shape_fallback:
        return _looks_like_bare_person_name(title)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Marketing prefix.
# ─────────────────────────────────────────────────────────────────────────────

# A leading possessive-artist prefix: a run of 1–3 capitalised name tokens
# (optionally with a lowercase particle) ending in "'s" / "’s", optionally
# followed by 1–3 lowercase "marketing" adjective/noun words
# ("iconic", "famous", "groundbreaking", "provocative", "famous painting",
# "groundbreaking depiction of modern life"). Non-greedy; the capture group 1 is
# the stripped artist, group 2 (the tail) is the remaining title.
_POSSESSIVE_PREFIX_RE = re.compile(
    r"^\s*"
    r"((?:[A-ZÀ-Ý][\w’'’.-]*\s+)?"            # optional given name(s)
    r"(?:(?:van|von|de|del|della|di|da|du|des|der|den|le|la)\s+)?"  # particle
    r"[A-ZÀ-Ý][\w’'’.-]*)"                    # surname (capitalised)
    r"['’]s\s+"                                # possessive 's
    r"((?:[a-zà-ÿ][\w’'’-]*\s+){0,5})"         # 0–5 lowercase filler words
    r"(?=[A-ZÀ-Ý0-9])",                        # tail must start capital/number
    re.UNICODE,
)

# Lowercase filler words allowed between the possessive and the real title. Any
# lowercase word that is NOT one of these aborts the strip (so a genuine lowercase
# start of a title is never swallowed). Kept to marketing adjectives/nouns and the
# articles/preposition glue they ride on.
_MARKETING_FILLER = frozenset({
    "iconic", "famous", "renowned", "celebrated", "groundbreaking", "seminal",
    "masterful", "provocative", "beloved", "legendary", "beautiful", "stunning",
    "remarkable", "extraordinary", "great", "greatest", "major", "monumental",
    "striking", "haunting", "radical", "revolutionary", "late", "early",
    "unfinished", "last", "final", "signature",
    "painting", "paintings", "masterpiece", "work", "canvas", "portrait",
    "depiction", "picture", "image", "composition", "scene", "study",
    "of", "the", "a", "an", "modern", "life", "famous painting",
})


def strip_marketing_prefix(
    title: str,
    known_titles: Optional[Iterable[str]] = None,
) -> Tuple[str, str]:
    """Strip a leading possessive-artist (+ optional marketing adjective) prefix
    when the REMAINDER still reads as a work title. Returns (clean_title, artist).

    "Van Gogh's iconic Self-Portrait with Bandaged Ear" →
        ("Self-Portrait with Bandaged Ear", "Van Gogh")
    "Édouard Manet's famous painting A Bar at the Folies-Bergère" →
        ("A Bar at the Folies-Bergère", "Édouard Manet")
    "Manet's  A Bar at the Folies-Bergère" → ("A Bar at the Folies-Bergère", "Manet")
    "Courbet's provocative The Hammock" → ("The Hammock", "Courbet")

    SAFE: a possessive work title with no plausible remainder, or whose lowercase
    filler is NOT marketing filler, is returned unchanged with artist "". When
    ``known_titles`` is given, the stripped remainder must match one of them (after
    normalisation) or the strip is rejected — so a real possessive title that
    happens to look like a prefix is never mangled.
    """
    original = str(title or "").replace("\xa0", " ").replace("\u202f", " ")
    original = re.sub(r"\s+", " ", original).strip()
    if not original:
        return original, ""

    m = _POSSESSIVE_PREFIX_RE.match(original)
    if not m:
        return original, ""

    artist = m.group(1).strip()
    filler = (m.group(2) or "").strip()
    tail = original[m.end():].strip()

    # The tail must be a plausible, non-trivial title.
    if len(tail) < 3 or len(tail.split()) < 1:
        return original, ""

    # Every lowercase filler word between possessive and title must be marketing
    # filler — otherwise we would be eating the real start of a lowercase title.
    if filler:
        for w in filler.lower().split():
            if w not in _MARKETING_FILLER:
                return original, ""

    # When a reference set is given, the stripped tail must match a known title.
    if known_titles is not None:
        allowed = {_norm(t) for t in known_titles if t}
        allowed.discard("")
        if allowed and _norm(tail) not in allowed:
            return original, ""

    return tail, artist


# ─────────────────────────────────────────────────────────────────────────────
# Combined filter.
# ─────────────────────────────────────────────────────────────────────────────

def filter_site_candidates(
    titles: Sequence,
    venue_name: str = "",
    artist_names: Iterable[str] = (),
    *,
    protected_titles: Iterable[str] = (),
    title_key: str = "title",
    allow_shape_fallback: bool = False,
) -> Tuple[List, List]:
    """Split site-listed candidates by the LOCAL-653 guards + junk_title_guard.

    Returns (kept, dropped). ``titles`` is a list of dicts (``title_key`` or
    ``name``) or bare strings. Each dropped dict is a shallow copy with a
    ``_reject_reason`` key; a dropped string is returned as-is. Order-preserving
    and pure.

    Rejects, per candidate:
      1. junk_title_guard.is_junk_page_title (chrome / nav / page title / the
         venue-with-filler) — delegated so this module never diverges from it;
      2. is_venue_or_sibling_title (the venue itself, a sibling institution, or a
         site brand) — location-suffix robust;
      3. is_artist_name_alone (a bare artist/person name — "Paul Cézanne").

    A title in ``protected_titles`` (e.g. a SPARQL/Wikidata-confirmed work label)
    is kept against the junk/sibling/shape heuristics so a legitimate work is
    never dropped. EXCEPTION: a bare title that exactly matches one of
    ``artist_names`` (a precise creator match) is dropped even when protected — an
    artist name is never a work, even when it leaked into the SPARQL label set (the
    "Georges Seurat"/"Edgar Degas" live leak).

    ``allow_shape_fallback`` extends the artist-name drop to a bare personal-name
    SHAPE (2–3 capitalised tokens, no work-signal word) for NON-protected titles —
    needed because a scraped artist link ("Georges Seurat") is often NOT one of the
    venue's SPARQL creator labels, yet is plainly not a work. Protected SPARQL
    works are shielded (the protection short-circuit runs first), so enabling it on
    a canonical set whose real works are SPARQL-confirmed is safe.

    The marketing-prefix strip is NOT applied here (it is a renaming, not a drop);
    callers apply ``strip_marketing_prefix`` when assigning the stop name.
    """
    try:
        from junk_title_guard import is_junk_page_title as _is_junk
    except Exception:  # pragma: no cover - defensive
        _is_junk = None

    # Pass the venue CORE name to junk_title_guard too, so its own venue checks are
    # location-suffix robust (they compare venue tokens against the title).
    _core = venue_core_name(venue_name)
    protected = {_norm(t) for t in (protected_titles or []) if t}
    protected.discard("")

    kept: List = []
    dropped: List = []
    _known_artists = {_norm(a) for a in (artist_names or []) if a}
    _known_artists.discard("")
    for c in titles or []:
        if isinstance(c, dict):
            title = (c.get(title_key) or c.get("name") or "").strip()
        else:
            title = str(c or "").strip()

        reason = ""
        # A bare title that EXACTLY matches one of the venue's own creator names is
        # an artist, never a work — even if it also leaked into the SPARQL label
        # set (a data quirk where an artist page is catalogued as a "work"). This
        # precise match beats protection; the heuristic/junk checks below do not.
        if title and _norm(title) in _known_artists:
            reason = "artist_name_alone"
        elif _norm(title) in protected:
            # SPARQL/Wikidata-confirmed label (and not a bare artist name): keep it,
            # so a legitimate work is never dropped by the junk/sibling heuristics.
            kept.append(c)
            continue
        elif _is_junk is not None and title and _is_junk(title, _core):
            reason = "junk_page_title"
        elif title and is_venue_or_sibling_title(title, venue_name):
            reason = "venue_or_sibling_institution"
        elif title and is_artist_name_alone(
                title, artist_names, allow_shape_fallback=allow_shape_fallback):
            reason = "artist_name_alone"

        if reason:
            if isinstance(c, dict):
                d = dict(c)
                d["_reject_reason"] = reason
                dropped.append(d)
            else:
                dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped
