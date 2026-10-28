"""category_match_guard.py — LOCAL-791B item 2.

Keep a category tour ON its category. A "pagodas and temples" request must not
grow a PARK stop.

WHY (LEAD, Mac e2e @ a72f5ec5 — "Pagodas and temples of HCMC (Jade Emperor
Pagoda, Thien Hau Temple)"):
The pagoda tour returned, among its five stops, **Tao Dan Park** — a city park,
not a place of worship. A category request ("pagodas and temples", "churches of
Rome", "museums in Paris") asks for places of ONE CLASS; a candidate of another
class is off-category and must be rejected (BEFORE it becomes a stop), whether it
came from the model's first proposal OR from the maps/Serper replenish. The one
exception is a request that explicitly asks for a MIX ("temples and parks",
"pagodas, markets and parks") — then both classes are in scope.

WHAT THIS DOES (pure, deterministic, offline):
  * ``requested_categories(request)`` → the set of place CLASSES the request asks
    for, derived from the plural category nouns in the text (reusing the
    LOCAL-790 vocabulary). "pagodas and temples" → {"worship"}; "temples and
    parks" → {"worship", "park"}.
  * ``classify_place(title, category_text)`` → the place CLASS of one candidate,
    from its Serper/OSM category text first, then its title words. "Tao Dan Park"
    / category "Park" → "park"; "Jade Emperor Pagoda" / "Buddhist temple" →
    "worship".
  * ``candidate_matches_category(cand, requested)`` → True/False/None. True when
    the candidate's class is in the requested set; False when it is a KNOWN other
    class; None when the class is UNKNOWN (the caller keeps it — we never drop a
    place just because we could not classify it).
  * ``filter_off_category(cands, request, log)`` → the kept candidates, logging
    each rejection as ``[LOCAL-791B] off-category <title> <category>``.

NOT a category request (a plain "walking tour of District 1", a single named
venue, a restaurant/business tour) → ``requested_categories`` is empty and the
guard is a NO-OP (keeps everything). So it only ever acts on an explicit category
tour, and a mix request widens — never narrows — what is allowed.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "requested_categories",
    "classify_place",
    "candidate_matches_category",
    "filter_off_category",
    "CLASS_WORDS",
]


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


# ── Place CLASS vocabulary ───────────────────────────────────────────────────
# Each class maps to the words (category-text OR title tokens) that mark it. The
# worship set mirrors _WORSHIP_CIVIC_WORD_RE in generate_tour_text (the ticket's
# "places of worship") plus their Vietnamese local-name words so a Serper record
# whose category is "Buddhist temple" or whose title is "Chùa …" still classifies
# as worship. Order matters only for `classify_place`, which returns the FIRST
# class whose words appear — worship is checked before park/market so "temple
# garden" reads worship, not park.
CLASS_WORDS: "Dict[str, Tuple[str, ...]]" = {
    "worship": (
        "church", "cathedral", "basilica", "chapel", "abbey", "minster",
        "priory", "monastery", "convent", "friary", "parish", "shrine",
        "meetinghouse", "meeting house", "synagogue", "mosque", "masjid",
        "temple", "gurdwara", "pagoda", "place of worship", "worship",
        # Vietnamese local-name words for a pagoda/temple/shrine.
        "chua", "den", "mieu", "dinh", "thanh that",
    ),
    "museum": ("museum", "gallery", "exhibition", "exhibit", "art center",
               "art centre", "memorial museum"),
    "park": ("park", "garden", "gardens", "botanical", "playground",
             "green space", "recreation ground", "cong vien"),
    "market": ("market", "bazaar", "marketplace", "cho"),
    "restaurant": ("restaurant", "cafe", "coffee", "bar", "pub", "bistro",
                   "eatery", "diner", "food", "bakery"),
    "palace": ("palace", "castle", "citadel", "fortress", "mansion"),
    "monument": ("monument", "memorial", "statue", "tower", "obelisk",
                 "fountain", "landmark"),
    "beach": ("beach", "dunes", "lagoon", "bay", "cove"),
}

# The PLURAL category nouns a request uses, mapped to a place class. Mirrors
# LOCAL-790's _PLURAL_CATEGORY_NOUN so the two stay aligned.
_PLURAL_NOUN_TO_CLASS = {
    "pagodas": "worship", "temples": "worship", "churches": "worship",
    "cathedrals": "worship", "basilicas": "worship", "chapels": "worship",
    "abbeys": "worship", "mosques": "worship", "masjids": "worship",
    "synagogues": "worship", "shrines": "worship", "monasteries": "worship",
    "convents": "worship",
    "museums": "museum", "galleries": "museum",
    "parks": "park", "gardens": "park",
    "markets": "market",
    "palaces": "palace", "castles": "palace", "mansions": "palace",
    "monuments": "monument", "memorials": "monument", "fountains": "monument",
    "towers": "monument",
    "beaches": "beach",
}

# A request phrased as "places of worship" / "worship sites" names the worship
# class directly without a plural building noun.
_CLASS_PHRASES = {
    "places of worship": "worship",
    "place of worship": "worship",
    "worship sites": "worship",
    "religious sites": "worship",
}


def requested_categories(request: str) -> Set[str]:
    """The set of place CLASSES a request asks for, or an EMPTY set when the
    request is not a category request (so the guard is a no-op).

    Derived from the plural category nouns present ("pagodas and temples" →
    {"worship"}; "temples and parks" → {"worship","park"}) and the explicit
    "places of worship" phrasing. A single-class result means a strict category
    tour; a multi-class result is a MIX (all those classes allowed)."""
    text = _fold(request)
    if not text:
        return set()
    out: Set[str] = set()
    for phrase, cls in _CLASS_PHRASES.items():
        if _fold(phrase) in text:
            out.add(cls)
    for noun, cls in _PLURAL_NOUN_TO_CLASS.items():
        # Whole-word match on the plural noun.
        if re.search(r"\b" + re.escape(noun) + r"\b", text):
            out.add(cls)
    return out


def classify_place(title: str = "", category_text: str = "") -> Optional[str]:
    """Classify one place into a CLASS from its category text (preferred) and its
    title. Returns the class name, or None when nothing matches (UNKNOWN).

    Category text (Serper `_serper_category` / OSM type) is checked first because
    it is the authoritative label; the title is a fallback. Worship is tested
    before park/market so a "<name> Temple" in a "Temple Garden" style name reads
    worship."""
    cat = _fold(category_text)
    name = _fold(title)

    def _hit(blob: str, words: Sequence[str]) -> bool:
        return any(re.search(r"\b" + re.escape(_fold(w)) + r"\b", blob) for w in words)

    # 1. Category text — authoritative. Check every class; worship first.
    for cls in ("worship", "museum", "palace", "market", "restaurant",
                "park", "beach", "monument"):
        if cat and _hit(cat, CLASS_WORDS[cls]):
            return cls
    # 2. Title words — fallback.
    for cls in ("worship", "museum", "palace", "market", "restaurant",
                "park", "beach", "monument"):
        if name and _hit(name, CLASS_WORDS[cls]):
            return cls
    return None


def _candidate_category_text(cand: Dict) -> str:
    """Pull the best category signal a candidate carries: the raw Serper category,
    then the OSM type/category/cuisine fields the places path writes."""
    for key in ("_serper_category", "serper_category", "category_text",
                "osm_category"):
        v = cand.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    extr = cand.get("extratags")
    if isinstance(extr, dict) and isinstance(extr.get("cuisine"), str):
        if extr["cuisine"].strip():
            return extr["cuisine"].strip()
    # OSM `type` token ("restaurant", "park", "place_of_worship", …).
    for key in ("type", "category"):
        v = cand.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().replace("_", " ")
    return ""


def _candidate_title(cand: Dict) -> str:
    for key in ("name", "title", "label_en", "english_title", "label_local"):
        v = cand.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def candidate_matches_category(cand: Dict,
                               requested: Set[str]) -> Optional[bool]:
    """Does ``cand`` match the requested category set?

    * True  — the candidate's class is in ``requested`` (or ``requested`` is empty
              → not a category tour → everything matches).
    * False — the candidate's class is a KNOWN class NOT in ``requested``
              (off-category; the caller rejects + logs it).
    * None  — the candidate's class is UNKNOWN (we cannot classify it, so we do
              NOT reject it — a real place with an odd category is kept).
    """
    if not requested:
        return True
    cls = classify_place(_candidate_title(cand), _candidate_category_text(cand))
    if cls is None:
        return None
    return cls in requested


def filter_off_category(cands: List[Dict],
                        request: str,
                        log: Optional[Callable[[str], None]] = None,
                        named_anchors: Optional[Sequence[str]] = None,
                        ) -> List[Dict]:
    """Drop candidates whose place class does not match the request's category.

    Logs each rejection as ``[LOCAL-791B] off-category <title> <category>`` via
    ``log`` (defaults to ``print``). A NAMED anchor the user asked for by name is
    ALWAYS kept (the user chose it), even if it classifies oddly. A non-category
    request keeps everything. An unclassifiable candidate is kept."""
    emit = log or print
    requested = requested_categories(request)
    if not requested:
        return list(cands)

    anchor_keys = {_fold(a) for a in (named_anchors or []) if a}
    kept: List[Dict] = []
    for cand in cands:
        title = _candidate_title(cand)
        # User's own named place is never dropped by the category guard.
        if anchor_keys and _fold(re.sub(r"\s*\([^)]*\)\s*", " ", title)) in anchor_keys:
            kept.append(cand)
            continue
        verdict = candidate_matches_category(cand, requested)
        if verdict is False:
            cls = classify_place(title, _candidate_category_text(cand))
            emit(f"[LOCAL-791B] off-category {title} {cls or '?'}")
            continue
        kept.append(cand)
    return kept
