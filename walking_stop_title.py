"""walking_stop_title.py — LOCAL-791E item 1 (the module LOCAL-791C's title step
expected but never shipped).

A walking stop is a PLACE, not a part of one. LOCAL-791C wired a title step in
``generate_tour_text`` that imports ``strip_feature_word`` / ``is_bare_feature_word``
/ ``dedupe_place_titles`` from THIS module — but the module did not exist, so the
``try: from walking_stop_title import …`` set the three callables to ``None`` and
the whole feature-strip / reject / dedupe step SILENTLY no-opped on the walking
path. That is why the Old Saigon live run still shipped "Notre-Dame Cathedral
Basilica facade" (feature word not stripped), a duplicate Notre-Dame (dedupe not
run) and a "Grand" junk stop (bare-feature reject not run). Creating the module is
the fix for items 2, 3 and (the walking half of) 4.

THREE PURE, DETERMINISTIC, OFFLINE functions — no model, no network:

``strip_feature_word(title)``
    Remove a trailing architectural FEATURE word a narration title appended
    ("Notre-Dame Cathedral Basilica facade" → "Notre-Dame Cathedral Basilica";
    "Saigon Opera House grand staircase" → "Saigon Opera House"). Conservative:
    only a KNOWN feature word (optionally with a leading qualifier like "grand"/
    "main") at the very END is removed, and the strip never reduces a title to a
    bare qualifier ("Grand foyer" is NOT turned into "Grand").

``is_bare_feature_word(title)``
    True when the WHOLE title is a feature/room word (optionally a qualifier +
    feature: "vestibule", "the courtyard", "Grand foyer", "Main hall",
    "Grand staircase") — never a proper place name. A real civic landmark the
    listener named ("City Hall", "Opera House", "Saigon Opera House") is NOT a
    bare feature even though it ends in "hall"/"house", because it carries a
    distinctive proper-noun token.

``dedupe_place_titles(pois, log=…)``
    Collapse stops that name the SAME place — by the LOCAL-790/791 identity key
    (Wikidata QID / ≤60 m proximity / language-folded title), by a subset of the
    distinctive proper-noun tokens ("Notre-Dame Cathedral Basilica" ⊇
    "Saigon Notre-Dame Basilica"), or by an identical street ADDRESS (the bilingual
    twin case: same door, titles share no tokens). A stop flagged ``_anchor`` (a
    place the listener NAMED) is NEVER dropped as a duplicate. Order-preserving.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "strip_feature_word",
    "is_bare_feature_word",
    "dedupe_place_titles",
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature / room words a narration title may append to a building name, or stand
# alone as a non-place "stop". Kept to the words the Old Saigon field run shipped
# plus their obvious siblings. Multi-word features are listed longest-first so the
# regex prefers "grand staircase" over "staircase".
# ─────────────────────────────────────────────────────────────────────────────
_FEATURE_WORDS = [
    "grand staircase", "main staircase", "grand foyer", "main hall",
    "great hall", "main entrance", "grand hall",
    "facade", "façade", "portico", "staircase", "vestibule", "nave",
    "courtyard", "altar", "dome", "spire", "colonnade", "forecourt",
    "atrium", "rotunda", "foyer", "lobby", "entrance", "interior",
    "exterior", "rooftop", "roof", "steps", "balcony", "terrace",
    "hall", "tower",
]

# Leading qualifiers that, with a feature word, still name only a part/feature
# ("Grand foyer", "Main hall", "Great hall"). They never make a place on their own,
# so a title that is "<qualifier> <feature>" is a bare feature (rejected whole) and
# the strip must not leave the lone qualifier behind.
_QUALIFIERS = {"grand", "main", "great", "central", "upper", "lower", "inner",
               "outer", "north", "south", "east", "west", "front", "rear", "old"}

# Leading article, multilingual (same set the other guards use).
_LEAD_ARTICLE_RE = re.compile(
    r"(?i)^\s*(?:the|le|la|les|das|der|die|il|lo|el|los|las|l['’])\s+")

# A trailing feature word, optionally preceded by a qualifier, anchored to the end.
# Built from _FEATURE_WORDS (longest first so multi-word features win).
_FEATURE_ALT = "|".join(re.escape(w) for w in _FEATURE_WORDS)
_TRAILING_FEATURE_RE = re.compile(
    r"(?i)\s+(?:(?:grand|main|great|central|upper|lower|front|rear)\s+)?"
    r"(?:" + _FEATURE_ALT + r")\s*$")


def _strip_accents_lower(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm_words(text: str) -> List[str]:
    """Accent-folded, punctuation→space, lowercased word list (no leading article)."""
    t = _LEAD_ARTICLE_RE.sub("", str(text or "").strip())
    s = _strip_accents_lower(t)
    s = re.sub(r"[^\w\s]", " ", s)
    return s.split()


# Set of every single feature token (for the bare-feature membership test).
_FEATURE_TOKENS: Set[str] = set()
for _w in _FEATURE_WORDS:
    for _t in _strip_accents_lower(_w).split():
        _FEATURE_TOKENS.add(_t)
# Words that, as the FINAL token of a longer proper name, do NOT make the title a
# bare feature even though they appear in _FEATURE_TOKENS — a real civic landmark
# the listener named ends in one ("City Hall", "Opera House", "Bitexco Tower").
# These are only "features" when the WHOLE title is the word (or qualifier+word).
_PLACE_TAIL_SAFE = {"hall", "house", "tower"}


def strip_feature_word(title: str) -> str:
    """Remove a trailing architectural FEATURE word from a stop title.

    "Notre-Dame Cathedral Basilica facade"  → "Notre-Dame Cathedral Basilica"
    "Saigon Central Post Office portico"     → "Saigon Central Post Office"
    "Saigon Opera House grand staircase"     → "Saigon Opera House"
    "Bitexco Financial Tower"                → "Bitexco Financial"

    Conservative:
      * only a KNOWN feature word (optionally with a leading qualifier) at the very
        END is removed;
      * a title with no trailing feature word is returned unchanged;
      * the strip never reduces a title to a bare qualifier — "Grand foyer" is a
        bare feature (handled by ``is_bare_feature_word``); stripping "foyer" would
        leave "Grand", an adjective, so the strip is REFUSED and the title returned
        unchanged for the reject path to drop.
    """
    t = (title or "").strip()
    if not t:
        return t
    m = _TRAILING_FEATURE_RE.search(t)
    if not m:
        return t
    candidate = t[: m.start()].strip()
    if not candidate:
        return t  # whole title was the feature word — nothing to strip to
    # Never reduce to a lone qualifier ("Grand foyer" → "Grand"): if everything
    # that remains is a single qualifier word, refuse the strip.
    rem_words = _norm_words(candidate)
    if len(rem_words) == 1 and rem_words[0] in _QUALIFIERS:
        return t
    # Never strip a SAFE place-tail word ("hall"/"house"/"tower") down to a single
    # remaining token — "City Hall" would become the bare generic "City". A
    # distinctive multi-token head ("Bitexco Financial" from "… Tower") still
    # strips. The matched feature is the last matched word group.
    _matched = _strip_accents_lower(m.group(0)).split()
    if _matched and _matched[-1] in _PLACE_TAIL_SAFE and len(rem_words) <= 1:
        return t
    return candidate


def is_bare_feature_word(title: str) -> bool:
    """True when the WHOLE title is a feature / room word — never a place.

    Rejected (True):
      "vestibule", "the courtyard", "Grand foyer", "Main hall", "Great hall",
      "Main entrance", "Grand staircase", "Main staircase".
    Kept (False):
      a real place that merely CONTAINS/ENDS in a feature token but carries a
      distinctive proper-noun token — "City Hall", "Opera House", "Saigon Opera
      House", "Notre-Dame Cathedral Basilica", "Jade Emperor Pagoda".
    """
    words = _norm_words(title)
    if not words:
        return True  # empty title is not a place
    # (1) single feature word: "vestibule", "courtyard", "foyer", "hall", …
    if len(words) == 1:
        return words[0] in _FEATURE_TOKENS
    # (2) qualifier + feature word: "grand foyer", "main hall", "grand staircase".
    if len(words) == 2 and words[0] in _QUALIFIERS and words[1] in _FEATURE_TOKENS:
        return True
    # (3) "<qualifier> <feature> <feature>" is still just a feature phrase, but we
    #     keep this tight: only when EVERY token is a qualifier or feature token.
    if all((w in _QUALIFIERS or w in _FEATURE_TOKENS) for w in words):
        # A real landmark ("Opera House", "City Hall") has a distinctive token,
        # so it never reaches here; a phrase made only of qualifier/feature tokens
        # ("main entrance hall") is a feature, with one exception: a two-word
        # place whose tail is a SAFE place tail and whose head is a real noun — but
        # that head would not be in the qualifier/feature sets, so it is already
        # excluded. Safe to reject.
        return True
    return False


# ── dedupe ───────────────────────────────────────────────────────────────────

# City / district qualifier tokens that do not distinguish two names of the SAME
# place ("Saigon Notre-Dame Basilica" vs "Notre-Dame Cathedral Basilica"). Dropped
# from the distinctive set before the subset test so a city-prefixed twin collapses.
_PLACE_QUALIFIER_TOKENS = {
    "saigon", "hcmc", "hochiminh", "ho", "chi", "minh", "city", "vietnam",
    "old", "new", "central", "downtown", "district",
}


def _distinctive_core(name: str) -> Set[str]:
    """The proper-noun core of a place name: language-folded distinctive tokens
    (via identity_dedup when available) MINUS city/district qualifier tokens, so
    "Saigon Notre-Dame Basilica" and "Notre-Dame Cathedral Basilica" share the same
    core {dame, notre}."""
    try:
        from identity_dedup import _distinctive_tokens as _dt
        core = set(_dt(name))
    except Exception:
        core = {w for w in _norm_words(name)
                if w not in _FEATURE_TOKENS and len(w) >= 2}
    return {t for t in core if t not in _PLACE_QUALIFIER_TOKENS}


def _norm_address(addr: str) -> str:
    """Accent-folded, punctuation-collapsed address key. '' for an empty address
    (an empty address never matches, so missing addresses never collapse)."""
    s = _strip_accents_lower(addr or "")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _same_place(a: Dict, b: Dict) -> bool:
    """True when two place candidates name the SAME place:
      * same identity (QID / ≤60 m proximity / language-folded title), OR
      * identical non-empty street address, OR
      * one's distinctive proper-noun core is a (non-empty) subset of the other's.
    """
    # (1) identity_dedup authority (QID / proximity / exact fold).
    try:
        from identity_dedup import dedupe_by_location_or_qid as _dloq
        kept, dropped = _dloq([a, b])
        if len(kept) == 1:
            return True
    except Exception:
        pass
    # (2) identical street address.
    aa, ba = _norm_address(a.get("address", "")), _norm_address(b.get("address", ""))
    if aa and ba and aa == ba:
        return True
    # (3) distinctive-core subset (city/district qualifier dropped).
    ca, cb = _distinctive_core(a.get("name") or a.get("title") or ""), \
        _distinctive_core(b.get("name") or b.get("title") or "")
    if ca and cb and (ca <= cb or cb <= ca):
        return True
    return False


def _is_anchor(poi: Dict) -> bool:
    """A stop the listener NAMED by hand — never dropped as a duplicate. Only the
    explicit ``_anchor`` flag protects from a drop (``user_explicit`` does not:
    a replenished user_explicit twin of an anchor is still collapsed)."""
    return bool(poi.get("_anchor"))


def dedupe_place_titles(
    pois: Sequence[Dict],
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """Collapse stops that name the SAME place, keeping the FIRST occurrence in
    order. A stop flagged ``_anchor`` is never dropped as a duplicate (it is always
    kept, even when it duplicates an earlier stop). Returns the deduped list.

    Same-place test (``_same_place``): identity_dedup authority (QID / ≤60 m
    proximity / language-folded title), an identical street address, or a subset
    of the distinctive proper-noun core (city/district qualifier ignored).

    Pure — operates on the dicts as given, returns a new list; order preserved.
    """
    emit = log or (lambda _m: None)
    kept: List[Dict] = []
    for cand in pois or []:
        if not isinstance(cand, dict):
            kept.append(cand)
            continue
        # A hand-named anchor is always kept, even if it duplicates an earlier stop.
        if _is_anchor(cand):
            kept.append(cand)
            continue
        dup_of = None
        for k in kept:
            if not isinstance(k, dict):
                continue
            if _same_place(cand, k):
                dup_of = k
                break
        if dup_of is not None:
            emit(f"[LOCAL-791E] title dedupe dropped "
                 f"'{cand.get('name') or cand.get('title')}' "
                 f"(same place as '{dup_of.get('name') or dup_of.get('title')}')")
            continue
        kept.append(cand)
    return kept
