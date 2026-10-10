"""candidate_collapse_guard.py — LOCAL-667.

A single canonical work title that reads like a list of place/clause words gets
atomised by the Phase-3A model into several "works". The Ho Chi Minh City Museum
of Fine Arts (Q2756351) has ONE SPARQL work whose English Wikidata label is
literally "North Central South Spring Garden" (a reordered translation of the
Vietnamese "Vườn xuân Bắc Trung Nam"; the EN altLabel is
"Central South and North Spring Garden"). gpt-4.1-mini, handed that as a guidance
hint, returned FIVE candidate POIs — North / Central / South / Spring Garden /
Garden — so D1v2 verified only the one fragment that happened to cover enough of
the canonical ("Spring Garden") and dropped the other four. One real work became
"1 of 5 delivered".

THE FIX (deterministic, no network, no LLM): before verification, detect when a
run of candidate names are all fragments — contiguous word-subsequences, or an
"and"/comma split — of ONE known canonical/SPARQL title, and COLLAPSE them into a
single candidate carrying that canonical title. The whole title then verifies as
one work and the wasted slots are freed for genuine replenishment.

Invariants this guard must never break:
  * It only ever collapses INTO a title that is already in the known set
    (SPARQL/canonical). It never invents a title and never merges two DIFFERENT
    real works.
  * A candidate that is itself a full, distinct work (the Courtauld's
    "A Bar at the Folies-Bergère", "Self-Portrait with Bandaged Ear") is left
    untouched: those are not fragments of one another.
  * Collapsing requires at least TWO fragments of the same title (a lone
    "Spring Garden" is left for the ordinary matcher — collapsing a single
    candidate would change nothing and risks hiding a real one-word work).

Pure functions only; unit-tested in tests/test_local667_title_split.py.
"""
from __future__ import annotations

import unicodedata
import re
from typing import Dict, List, Optional, Sequence, Tuple

# Words that carry no distinguishing content when deciding whether a candidate is
# a fragment of a title. Kept small and multilingual-light: the test is positional
# (is this candidate a span of that title), not semantic.
_GLUE = {
    "the", "of", "and", "a", "an", "to", "in", "on", "with", "for",
    "de", "del", "della", "la", "le", "les", "el", "il", "lo",
    "und", "der", "die", "das", "von",
}


def _norm_tokens(text: str) -> List[str]:
    """Lowercase, strip accents and punctuation, split to word tokens."""
    if not text:
        return []
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return stripped.split()


def _content_tokens(text: str) -> List[str]:
    return [t for t in _norm_tokens(text) if t not in _GLUE and len(t) >= 2]


def _is_fragment_of(candidate: str, title_tokens: List[str],
                    title_content: List[str]) -> bool:
    """True when `candidate` is a fragment of a title.

    A fragment is EITHER:
      * a contiguous run of the title's tokens (so "Spring Garden" ⊂
        "North Central South Spring Garden", and "North" ⊂ it), OR
      * entirely built from the title's CONTENT tokens (so a comma/"and" split
        clause such as "Central South and North" of
        "Central South and North Spring Garden" counts),
    AND the candidate is strictly SHORTER (in content tokens) than the title — a
    candidate equal to the whole title is the title itself, not a fragment.
    """
    cand_tokens = _norm_tokens(candidate)
    if not cand_tokens or not title_tokens:
        return False
    cand_content = _content_tokens(candidate)
    if not cand_content:
        return False
    # A fragment must be shorter than the title it is a piece of.
    if len(cand_content) >= len(title_content):
        return False

    # (a) contiguous token-subsequence of the full title token list
    n, m = len(title_tokens), len(cand_tokens)
    for i in range(0, n - m + 1):
        if title_tokens[i:i + m] == cand_tokens:
            return True

    # (b) every content token of the candidate is a content token of the title
    #     (covers an "and"/comma reordering such as "Central South and North")
    title_content_set = set(title_content)
    if all(t in title_content_set for t in cand_content):
        return True

    return False


def collapse_split_title_candidates(
    poi_list: Sequence[Dict],
    known_titles: Sequence[str],
    *,
    min_title_content_words: int = 3,
) -> Tuple[List[Dict], List[Dict]]:
    """Collapse candidate POIs that are fragments of ONE known title.

    Args:
        poi_list: the Phase-3A candidate POIs (dicts with at least 'name').
        known_titles: canonical/SPARQL titles for THIS venue (the only titles a
            collapse may produce). Short titles (< min_title_content_words content
            words) are ignored as collapse targets — a two-word title does not get
            atomised the way a long list-like one does, and using it as a target
            would risk merging two short works.
        min_title_content_words: a title must have at least this many content
            words to be a collapse target (default 3). This is what distinguishes
            "North Central South Spring Garden" (5 content words, atomisable) from
            an ordinary two-word work title.

    Returns:
        (new_poi_list, collapses) where new_poi_list has each fragment-run
        replaced by a SINGLE POI carrying the canonical title (keeping the first
        fragment's address and other fields), and collapses is a list of
        {'title', 'fragments': [...], 'poi': <collapsed poi>} records for logging
        and tests. Order of the surviving POIs follows the first occurrence of
        each group; non-fragment POIs are left exactly where they were.
    """
    pois = [dict(p) for p in poi_list]
    # Pre-compute token lists for the eligible target titles.
    targets: List[Tuple[str, List[str], List[str]]] = []
    for t in known_titles:
        toks = _norm_tokens(t)
        content = _content_tokens(t)
        if len(content) >= min_title_content_words:
            targets.append((t, toks, content))
    if not targets:
        return pois, []

    # Map each POI index → the title it is a fragment of (first eligible match).
    frag_of: Dict[int, str] = {}
    for idx, p in enumerate(pois):
        name = p.get("name", "")
        if not name:
            continue
        for title, toks, content in targets:
            if _is_fragment_of(name, toks, content):
                frag_of[idx] = title
                break

    # Group fragment indices by title; only collapse groups with >= 2 fragments.
    groups: Dict[str, List[int]] = {}
    for idx, title in frag_of.items():
        groups.setdefault(title, []).append(idx)

    collapsible = {t: idxs for t, idxs in groups.items() if len(idxs) >= 2}
    if not collapsible:
        return pois, []

    # Build the collapsed list, preserving order. The group is represented at the
    # position of its FIRST fragment; later fragments are removed.
    collapsed_titles_at: Dict[int, str] = {}
    drop: set = set()
    for title, idxs in collapsible.items():
        first = min(idxs)
        collapsed_titles_at[first] = title
        for i in idxs:
            if i != first:
                drop.add(i)

    new_list: List[Dict] = []
    collapses: List[Dict] = []
    for idx, p in enumerate(pois):
        if idx in drop:
            continue
        if idx in collapsed_titles_at:
            title = collapsed_titles_at[idx]
            frags = [pois[i].get("name", "") for i in sorted(groups[title])]
            collapsed_poi = dict(p)
            collapsed_poi["name"] = title
            collapsed_poi["_collapsed_from"] = frags
            new_list.append(collapsed_poi)
            collapses.append({"title": title, "fragments": frags,
                              "poi": collapsed_poi})
        else:
            new_list.append(p)
    return new_list, collapses


def quote_multiword_hint_titles(titles: Sequence[str]) -> List[str]:
    """Return hint titles with any multi-word title wrapped in double quotes, so a
    list-like title ("North Central South Spring Garden") reads to the model as a
    SINGLE unit rather than an enumeration to atomise. Single-word titles are left
    unquoted (quoting them adds nothing). Deterministic; used by the Phase-3A hint
    builder."""
    out: List[str] = []
    for t in titles:
        t = (t or "").strip()
        if not t:
            continue
        if len(t.split()) >= 2 and not (t.startswith('"') and t.endswith('"')):
            out.append(f'"{t}"')
        else:
            out.append(t)
    return out
