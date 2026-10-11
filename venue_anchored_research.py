"""venue_anchored_research.py — LOCAL-668.

Deliverable #3: venue-anchored research for area / collection stops.

A thin-museum tour fills its empty slots with building and named collection-area
stops (LOCAL-667). Those stops have GENERIC titles — "Woodblock prints
collection", "Lacquer painting collection" — so the per-stop research
(work_story_searcher.synthesize_queries) correctly anchors the QUERY to the
museum ("<title>" <venue>), but the SERP still returns results about the SAME
MEDIUM at OTHER museums. On the HCMC cheap-arm run (hcmc_on_664.log) the
"Woodblock prints collection" stop pulled snippets about Japanese woodblock
prints at the Honolulu Museum of Art and the Saint Louis Art Museum, and
"Phil Guston … Saint Louis holdings … Holbein and Pippin" bled into the stop-5
narration. The post-generation LOCAL-652 pass removed most of it, but prevention
at the EVIDENCE stage is cleaner than cure at the prose stage: a snippet about
another museum should never reach the writer.

This module is the deterministic EVIDENCE FILTER for that. It is pure (no
network, no LLM, no DB) so every rule is unit-testable:

  mentions_this_venue(text, venue_name) -> bool
      True when the text names THIS venue (accent/case-insensitive, by the
      venue's distinctive content tokens — reuses LOCAL-652's token idea).

  names_foreign_museum(text, venue_name) -> Optional[str]
      Returns the foreign institution name when the text names a museum / gallery
      / art institute / collection whose proper name is NOT this venue; else None.

  drop_foreign_museum_snippets(snippets, venue_name, city="") -> (kept, report)
      Drop each snippet that names a foreign museum AND does not name this venue.
      A snippet that names this venue (even alongside another) is KEPT — it is
      about us. Order preserved. Returns (kept, report) with a dropped log.

HONESTY / SAFETY: the filter only ever REMOVES evidence that is about a different
institution; it never invents, rewrites, or reorders. When in doubt (the snippet
names this venue, or names no institution at all) it KEEPS the snippet.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "venue_content_tokens",
    "mentions_this_venue",
    "names_foreign_museum",
    "drop_foreign_museum_snippets",
]


def _fold(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Generic words that are NOT distinctive to any one venue — a venue match must
# rest on a distinctive token (e.g. "chi", "minh", "hoa"), never on "museum".
_VENUE_STOPWORDS = {
    "the", "of", "and", "a", "an", "to", "in", "on", "at", "for", "with", "by",
    "museum", "museums", "gallery", "galleries", "art", "arts", "fine", "modern",
    "contemporary", "collection", "collections", "institute", "institution",
    "foundation", "centre", "center", "city", "national", "state", "royal",
    "municipal", "palace", "house", "hall", "de", "la", "le", "les", "du", "des",
    "van", "von", "del", "della",
}


def venue_content_tokens(venue_name: str) -> set:
    """Distinctive, accent-folded content tokens of a venue name (len>=3, not a
    generic museum word). "Ho Chi Minh City Museum of Fine Arts" ->
    {'chi','minh'} ('ho' is <3; 'city','museum','fine','arts' are generic)."""
    out = set()
    for w in re.findall(r"[A-Za-zÀ-ÿ']+", venue_name or ""):
        wl = _fold(w.lower()).strip("'")
        if len(wl) >= 3 and wl not in _VENUE_STOPWORDS:
            out.add(wl)
    return out


def mentions_this_venue(text: str, venue_name: str) -> bool:
    """True when `text` names THIS venue by its distinctive tokens.

    Requires ALL distinctive venue tokens to be present (so "Ho Chi Minh City
    Museum of Fine Arts" is matched by a snippet carrying 'chi' AND 'minh', but a
    snippet that merely says 'fine arts museum' is not). When the venue name has
    no distinctive token (only generic words), we conservatively return False.
    """
    vtok = venue_content_tokens(venue_name)
    if not vtok:
        return False
    low = _fold(text or "")
    toks = set(re.findall(r"[a-zà-ÿ']+", low))
    return vtok <= toks


# An institution phrase: an (optional) proper-name run followed by an institution
# head word, OR an institution head word followed by "of <Proper>". Captures
# "Saint Louis Art Museum", "Honolulu Museum of Art", "Museum of Fine Arts,
# Boston", "Rijksmuseum", "Tate", "the Louvre". The proper-name run is one or more
# Capitalized tokens (allowing internal 'of/de/the').
_INSTITUTION_HEAD = (
    r"museum|museums|gallery|galleries|kunstmuseum|rijksmuseum|pinacoteca|"
    r"art\s+institute|art\s+museum|art\s+gallery|collection|foundation|"
    r"fondation|stiftung|academy|academie|conservatory|louvre|hermitage|tate|"
    r"met(?:ropolitan)?\s+museum|getty|smithsonian|guggenheim"
)

# Proper-noun run: Capitalized words possibly joined by of/de/the/da/van/von.
_PROPER_RUN = r"(?:[A-ZÀ-Ý][\wÀ-ÿ'’.-]+)(?:\s+(?:of|de|the|da|van|von|del|della|[A-ZÀ-Ý][\wÀ-ÿ'’.-]+)){0,4}"

_INSTITUTION_RE = re.compile(
    r"\b(" + _PROPER_RUN + r")\s+(" + _INSTITUTION_HEAD + r")\b"
    r"|\b((?:" + _INSTITUTION_HEAD + r"))\s+of\s+(" + _PROPER_RUN + r")\b",
    re.IGNORECASE,
)

# Lone famous-institution names that carry no generic head word.
_LONE_INSTITUTIONS = [
    "louvre", "rijksmuseum", "hermitage", "uffizi", "prado", "guggenheim",
    "tate", "getty", "smithsonian", "pompidou", "orsay", "moma",
]


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip(" ,.;:")).strip()


def names_foreign_museum(text: str, venue_name: str) -> Optional[str]:
    """Return the name of a museum/institution the text names that is NOT this
    venue, or None.

    A match is "foreign" only when its own distinctive tokens are not a subset of
    this venue's tokens (so "...Museum of Fine Arts, Ho Chi Minh City..." is NOT
    foreign) and it shares no distinctive token with the venue.
    """
    if not text:
        return None
    vtok = venue_content_tokens(venue_name)

    candidates: List[str] = []
    # Scan sentence-by-sentence so a proper-name run never spans a sentence
    # boundary ("…four national museums in Japan. Honolulu Museum of Art…").
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        for m in _INSTITUTION_RE.finditer(sent):
            if m.group(1) and m.group(2):            # "<Proper> <Head>"
                candidates.append(_clean_name(f"{m.group(1)} {m.group(2)}"))
            elif m.group(3) and m.group(4):          # "<Head> of <Proper>"
                candidates.append(_clean_name(f"{m.group(3)} of {m.group(4)}"))
    low = _fold(text)
    for lone in _LONE_INSTITUTIONS:
        if re.search(r"\b" + re.escape(lone) + r"\b", low):
            candidates.append(lone)

    for cand in candidates:
        ctok = venue_content_tokens(cand)
        if not ctok:
            # No distinctive token (e.g. a bare "Art Museum") — cannot tell it is
            # foreign; skip (conservative).
            continue
        # Shares a distinctive token with the venue → it IS this venue.
        if vtok and (ctok & vtok):
            continue
        return cand
    return None


def _snippet_text(snip: Dict) -> str:
    return f"{snip.get('title', '')}. {snip.get('snippet', '')}".strip()


def drop_foreign_museum_snippets(
    snippets: Sequence[Dict],
    venue_name: str,
    city: str = "",
) -> Tuple[List[Dict], Dict]:
    """[LOCAL-668 #3] Drop snippets whose subject is another museum.

    Rule, per snippet:
      • If it NAMES THIS venue → KEEP (it is about us, even if it also mentions
        another institution for comparison).
      • Else if it NAMES A FOREIGN museum/gallery/institution → DROP (its subject
        is a different institution; it is the Saint-Louis / Honolulu leak).
      • Else → KEEP (no competing institution; generic medium/technique evidence
        is fine).

    Order preserved. Pure. Returns (kept, report) where report has 'input',
    'dropped', 'output', and a 'dropped_log' of (title, foreign_name) pairs.
    """
    kept: List[Dict] = []
    dropped_log: List[Dict] = []
    for snip in snippets or []:
        text = _snippet_text(snip)
        if mentions_this_venue(text, venue_name):
            kept.append(snip)
            continue
        foreign = names_foreign_museum(text, venue_name)
        if foreign:
            dropped_log.append({
                "title": (snip.get("title", "") or "")[:80],
                "foreign": foreign,
                "url": snip.get("url", ""),
            })
            continue
        kept.append(snip)
    report = {
        "input": len(snippets or []),
        "dropped": len(dropped_log),
        "output": len(kept),
        "dropped_log": dropped_log,
    }
    return kept, report
