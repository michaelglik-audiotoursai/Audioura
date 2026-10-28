"""place_title_naming.py — LOCAL-791B item 1.

English tour, foreign place: give the place its ENGLISH name with the LOCAL name
in parentheses.

WHY (LEAD, Mac e2e @ a72f5ec5 — "Pagodas and temples of HCMC"):
The pagoda tour shipped stop titles that were bare Vietnamese or a mix:
"Ngoc Hoang Pagoda", "Chùa Bà Ấn Độ", "Chùa Bà Thiên Hậu". An English-language
listener wants the English name first, with the local name kept in parentheses so
the place is still recognisable on the ground and on a sign:

    "Jade Emperor Pagoda (Chùa Ngọc Hoàng)"
    "Mariamman Hindu Temple (Chùa Bà Ấn Độ)"
    "Thien Hau Temple (Chùa Bà Thiên Hậu)"

For a RUSSIAN tour the SAME shape with the Russian label as the primary name and
the local name in parentheses.

SOURCES, IN PRIORITY ORDER (the ticket):
  1. THE USER'S OWN WORDING. A NAMED anchor — a place the request itself names —
     keeps EXACTLY the user's name. We never "correct" a name the user typed; a
     listener who asked for "Jade Emperor Pagoda" gets that title verbatim.
  2. THE WIKIDATA LABEL IN THE TOUR LANGUAGE. When the candidate carries a
     Wikidata label pairing (label_en / label_local, or a per-language
     labels dict), use the label in the tour language as the primary name and the
     local-language label in parentheses.
  3. THE SERPER PLACES ENGLISH TITLE. When neither of the above is available, the
     map listing's (cleaned) English title is the primary name; the local name, if
     we have one that differs, goes in parentheses.

PURE / DETERMINISTIC / OFFLINE. No model, no network. The caller supplies whatever
it already knows about the place (the user's named anchors, any Wikidata labels on
the candidate, the Serper title) and the tour language; this module only chooses
and formats. A place we have only one name for is returned as that one name (no
empty parentheses).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

__all__ = [
    "format_place_title",
    "title_for_candidate",
    "is_named_anchor",
    "anchor_for_title",
    "LANG_LOCAL",
]

# Languages whose label we treat as the "local" (place's own) language for the
# Vietnam field case and the common tour languages. Only used to pick which
# Wikidata label is the LOCAL one when a candidate carries a per-language labels
# dict; the label_en / label_local shape needs no table.
LANG_LOCAL = {
    "vi": "Vietnamese", "en": "English", "ru": "Russian", "fr": "French",
    "de": "German", "es": "Spanish", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese", "th": "Thai",
}


def _strip_accents_lower(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _norm_cmp(text: str) -> str:
    """Comparison key: accent-folded, lowercased, punctuation→space, collapsed.
    Two names with the same key are 'the same name' for the parenthetical test
    (so we never print 'X (X)')."""
    s = _strip_accents_lower(text)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _already_parenthesised(name: str) -> bool:
    """True when the name already carries a '(…)' gloss — the caller (or an
    upstream title) has already formatted it, so we must not double-wrap."""
    return bool(re.search(r"\([^)]+\)", name or ""))


def format_place_title(primary: str, local: str = "") -> str:
    """Format one title as ``English Name (Local Name)``.

    * ``primary`` is the name to show first (the English/tour-language name).
    * ``local`` is the place's own-language name, shown in parentheses.

    Rules (pure, deterministic):
      - A blank ``primary`` falls back to ``local`` (and vice-versa).
      - ``local`` is dropped when it is empty, equal to ``primary`` (accent- and
        case-insensitively), or already contained in ``primary`` (so a title that
        is already "A (B)" is not wrapped again).
      - Never returns empty-parentheses "Name ()".
    """
    primary = _clean(primary)
    local = _clean(local)
    if not primary:
        return local
    if not local:
        return primary
    # Don't double-wrap an already-formatted "English (Local)" primary.
    if _already_parenthesised(primary):
        return primary
    pk, lk = _norm_cmp(primary), _norm_cmp(local)
    if not lk or pk == lk:
        return primary
    # If the local name is already a substring of the primary (e.g. primary is a
    # longer official English form that embeds the transliteration), don't repeat.
    if lk and lk in pk:
        return primary
    return f"{primary} ({local})"


def is_named_anchor(name: str, named_anchors: Optional[List[str]]) -> Optional[str]:
    """Return the user's EXACT wording for ``name`` when it is one of the request's
    NAMED anchors, else None.

    A named anchor keeps exactly the user's name (priority 1): if the listener
    typed "Jade Emperor Pagoda", that is the title, verbatim, regardless of what
    Wikidata or Serper call it. Matching is accent- and case-insensitive and
    tolerant of a parenthetical gloss on either side, so "Jade Emperor Pagoda" in
    the request matches a "Jade Emperor Pagoda (Chùa Ngọc Hoàng)" candidate and
    vice-versa."""
    if not name or not named_anchors:
        return None

    # Compare on the bare name (drop any "(…)" gloss on either side).
    def _bare(s: str) -> str:
        return _norm_cmp(re.sub(r"\s*\([^)]*\)\s*", " ", s or ""))

    nk = _bare(name)
    if not nk:
        return None
    for anchor in named_anchors:
        if _bare(anchor) == nk:
            return _clean(anchor)
    return None


def anchor_for_title(name: str, named_anchors: Optional[List[str]]) -> Optional[str]:
    """Return the user's EXACT anchor wording for ``name`` by EXACT match first,
    then by CONTAINMENT, else None.

    The exact path is ``is_named_anchor``. The containment path handles the Old
    Saigon live case (LOCAL-791C): the model resolved the anchor "Notre-Dame
    Cathedral" to a candidate titled "Notre-Dame Cathedral Basilica facade" — a
    longer form with a trailing feature word. The user's anchor is a token-subset
    of the candidate, so we restore the stop to the user's own wording ("Notre-Dame
    Cathedral"), never shipping the "facade" sub-part as the title. Containment is
    whole-word and direction-aware: the user's anchor must be contained in the
    candidate (not the reverse), so a short candidate is never relabelled to a
    longer anchor it does not match."""
    exact = is_named_anchor(name, named_anchors)
    if exact:
        return exact
    if not name or not named_anchors:
        return None

    def _bare_words(s: str) -> List[str]:
        return [w for w in _norm_cmp(
            re.sub(r"\s*\([^)]*\)\s*", " ", s or "")).split() if w]

    cand_words = _bare_words(name)
    if not cand_words:
        return None
    cand_set = set(cand_words)
    best: Optional[str] = None
    best_len = 0
    for anchor in named_anchors:
        aw = _bare_words(anchor)
        if not aw or len(aw) < 2:
            # A single-word anchor is too weak for containment (would grab any
            # title sharing one common word); require the exact path for those.
            continue
        if set(aw) <= cand_set and len(aw) > best_len:
            best, best_len = _clean(anchor), len(aw)
    return best


def _labels_for_language(cand: Dict, lang: str) -> str:
    """Pull the candidate's Wikidata label in ``lang`` from whichever shape it
    carries: a per-language ``labels`` / ``wikidata_labels`` dict keyed by code
    (``{"en": …, "vi": …, "ru": …}``), or the label_en field when lang is English.
    Returns '' when absent."""
    lang = (lang or "").strip().lower()
    for key in ("labels", "wikidata_labels"):
        d = cand.get(key)
        if isinstance(d, dict):
            v = d.get(lang) or d.get(lang.split("-")[0])
            if isinstance(v, str) and v.strip():
                return v.strip()
    if lang in ("en", "english"):
        for key in ("label_en", "title_en", "english_title"):
            v = cand.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


def _label_local(cand: Dict) -> str:
    """The place's own-language (local) Wikidata label, from label_local/title_local
    or a 'local' labels-dict convention. Returns ''."""
    for key in ("label_local", "title_local", "local_title", "local_name"):
        v = cand.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def title_for_candidate(cand: Dict,
                        tour_language: str = "en",
                        named_anchors: Optional[List[str]] = None) -> str:
    """Choose and format a stop's display title for ``cand`` (LOCAL-791B item 1).

    ``cand`` is a stop/candidate dict that may carry any of:
      - ``name`` / ``title``          — the working name (often the Serper title).
      - ``serper_title`` / ``_serper_title`` — the raw Serper Places English title.
      - ``label_en`` / per-language ``labels`` dict — Wikidata label(s).
      - ``label_local`` / ``local_name``            — the place's own name.

    Priority:
      1. USER WORDING — if ``name`` matches a request ``named_anchors`` entry, return
         the user's exact wording (verbatim; never reformatted).
      2. WIKIDATA LABEL IN THE TOUR LANGUAGE — ``tour-language label (local label)``.
      3. SERPER ENGLISH TITLE — the cleaned map title, with the local name (if any,
         and different) in parentheses.

    Returns the formatted title string. Deterministic; no network. A candidate with
    a single known name is returned as that name (no empty parentheses)."""
    name = _clean(cand.get("name") or cand.get("title"))

    # ── Priority 1: the user's own wording (a NAMED anchor) ──────────────────
    anchor = is_named_anchor(name, named_anchors)
    if anchor:
        return anchor

    lang = (tour_language or "en").strip().lower()
    local_label = _label_local(cand)

    # ── Priority 2: the Wikidata label in the tour language ──────────────────
    tour_label = _labels_for_language(cand, lang)
    if tour_label:
        # A tour IN the place's own language needs no parenthetical: the label is
        # already the local name. For every other tour language, the local label
        # (when distinct) goes in parentheses.
        if lang in ("vi",):
            return format_place_title(tour_label, "")
        return format_place_title(tour_label, local_label)

    # ── Priority 3: the Serper Places English title ──────────────────────────
    serper_title = _clean(
        cand.get("serper_title") or cand.get("_serper_title")
        or cand.get("english_title") or name)
    if serper_title:
        return format_place_title(serper_title, local_label)

    # Last resort: whatever name we have (possibly just the local one).
    return format_place_title(name, local_label) or name
