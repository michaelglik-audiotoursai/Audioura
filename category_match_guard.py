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
    # LOCAL-830 — business/activity off-category guard (reuse path).
    "is_food_request",
    "business_off_category_class",
    "filter_off_category_business",
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
    then the OSM type/category/cuisine fields the places path writes, then the
    POOLED-row ``type_specialty`` / ``category_text`` fields a reused stop carries
    (a pooled stop has no Serper record — LOCAL-830)."""
    for key in ("_serper_category", "serper_category", "category_text",
                "osm_category", "type_specialty"):
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


# ── [LOCAL-830] Business/activity off-category guard (reuse path) ─────────────
#
# WHY (LEAD, GCloud_Storied 2026-10-30 — tour 502 "Kitesurf schools … Mui Ne"):
# the tour returned four kite schools AND **Sandals Restaurant**. The restaurant
# came from the STOP POOL (reused from the previous night's run), not from fresh
# selection. The fresh path keeps a business/places tour on-category two ways:
#   * PHASE 4 ``_verify_against_intent`` (needs the LLM ``intent['poi_type']``),
#   * the LOCAL-791B ``filter_off_category`` (fires only on a plural CATEGORY
#     noun — "pagodas", "temples"; EMPTY for "kitesurf schools").
# Neither runs on a POOLED stop at reuse time, and neither is available cheaply
# there (``poi_type`` needs an LLM call; ``requested_categories`` is empty for a
# business request). So the pool served an off-category restaurant.
#
# This guard is the DETERMINISTIC, OFFLINE check the reuse path can run: for a
# request whose SUBJECT is a business/activity provider that is NOT about food
# (kite school, dive shop, yoga studio, gym, surfboard rental, …), a pooled stop
# that classifies as FOOD ("restaurant" class: restaurant/cafe/bar/bakery/…) is
# off-category and is SKIPPED for this tour. A FOOD request ("seafood
# restaurants", "cafes in District 1") is NOT a business-off-category request —
# the guard is a NO-OP and restaurants are kept. Non-business requests
# (museums, pagodas, a plain walking tour) are also a no-op here; those are
# covered by the LOCAL-791B category guard / scope checks.
#
# Category-scoped reuse (ticket item 2): this NEVER deletes a pool row. The row
# stays in the pool and is reusable for the categories it matches — it is only
# not SERVED for this off-category request.

# Food/dining words in the request SUBJECT — a request carrying any of these is
# ABOUT food, so a restaurant is on-category and must be kept. Mirrors the dining
# vocabulary in stop_existence_gate._DINING / generate_tour_text dining words.
_FOOD_REQUEST_WORDS = (
    "restaurant", "restaurants", "dining", "dine", "food", "foods", "eatery",
    "eateries", "cuisine", "cafe", "cafes", "coffee", "coffeehouse", "bakery",
    "bakeries", "bar", "bars", "pub", "pubs", "brewery", "breweries", "bistro",
    "bistros", "brasserie", "diner", "diners", "grill", "steakhouse",
    "pizzeria", "pizzerias", "noodle", "noodles", "seafood", "streetfood",
    "street food", "breakfast", "brunch", "lunch", "dinner", "snack", "snacks",
    "dessert", "desserts", "patisserie", "deli", "culinary",
)

# Locative connectors that END the SUBJECT of a request — everything after is the
# search centre / area, not part of what the tour is about. Mirrors
# generate_tour_text._SUBJECT_CONNECTOR_RE (kept local so this module stays
# dependency-free and importable at the reuse layer).
_SUBJECT_CONNECTOR_RE = re.compile(
    r"\b(?:near(?:\s+me)?|around|close\s+to|next\s+to|by|in|of|within|"
    r"at|on|along)\b",
    re.IGNORECASE,
)


def _request_subject(request: str) -> str:
    """The SUBJECT of a request — the text up to the first locative connector.

    "Kitesurf schools in Mui Ne" → "kitesurf schools"; "massage near Ben Thanh
    Market" → "massage". A string that opens with a connector, or has none, is
    its own subject. A leading "<type>:" label is stripped."""
    subj = re.sub(r"^\s*[\w\s-]*?:\s*", "", str(request or ""), count=1).strip()
    m = _SUBJECT_CONNECTOR_RE.search(subj)
    if m and m.start() > 0:
        subj = subj[:m.start()].strip(" ,:;-")
    return subj


def is_food_request(request: str) -> bool:
    """True when the request SUBJECT is about food/dining (so a restaurant stop is
    on-category and must be kept). Deterministic and offline."""
    subj = _fold(_request_subject(request))
    if not subj:
        return False
    for w in _FOOD_REQUEST_WORDS:
        if re.search(r"\b" + re.escape(_fold(w)) + r"\b", subj):
            return True
    return False


def business_off_category_class(request: str) -> Optional[str]:
    """When the request SUBJECT is a BUSINESS/ACTIVITY provider that is NOT about
    food, return the place CLASS that is off-category for it ("restaurant"); else
    None (guard is a no-op).

    "Kitesurf schools in Mui Ne", "dive shops", "yoga studios", "surfboard
    rentals", "gyms" → "restaurant" (a food stop is off-category). A food request
    ("seafood restaurants") → None. A non-business request (museums, pagodas, a
    plain walking tour) → None.

    Uses ``stop_existence_gate.classify_business_vs_landmark`` on the subject to
    decide business vs dining vs landmark — the SAME classifier the fresh places
    router (``_business_subject_of_request``) uses, so the reuse path and the
    fresh path agree on what "a business request" is. Best-effort: if the
    classifier is unavailable, returns None (no-op)."""
    subj = _request_subject(request)
    if not subj:
        return None
    # A walking/transport verb makes it an AREA walk, not a business request.
    if re.match(r"^\s*(?:walk|walking|stroll|wander|hike|hiking|ramble|"
                r"promenade|saunter)\b", subj, flags=re.IGNORECASE):
        return None
    if is_food_request(request):
        return None
    try:
        from stop_existence_gate import classify_business_vs_landmark as _cbl
        verdict = _cbl(subj)
    except Exception:
        return None
    # 'business' (NOT 'dining', NOT 'landmark') → food stops are off-category.
    if verdict == "business":
        return "restaurant"
    return None


def filter_off_category_business(
        rows: List[Dict],
        request: str,
        log: Optional[Callable[[str], None]] = None,
        named_anchors: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict], int]:
    """[LOCAL-830] SKIP (do not delete) pooled rows that are off-category for a
    business/activity request.

    For a request whose subject is a business/activity provider that is NOT about
    food, a row classified as FOOD ("restaurant" class) is skipped for THIS tour.
    The row is NEVER deleted from the pool (category-scoped reuse — it stays
    reusable for a food request). A row the user named by hand is always kept. An
    unclassifiable row (class None) is kept (we never drop a place we cannot
    classify). Returns ``(kept_rows, skipped_count)``.

    No-op (returns the rows unchanged, skipped=0) when the request is not a
    non-food business request. Best-effort: any error returns the rows unchanged
    (a guard bug must never empty a tour)."""
    emit = log or print
    if not rows:
        return list(rows), 0
    try:
        off_class = business_off_category_class(request)
    except Exception:
        return list(rows), 0
    if not off_class:
        return list(rows), 0

    anchor_keys = {_fold(a) for a in (named_anchors or []) if a}
    kept: List[Dict] = []
    skipped = 0
    for r in rows:
        title = _candidate_title(r)
        if anchor_keys and _fold(re.sub(r"\s*\([^)]*\)\s*", " ", title)) in anchor_keys:
            kept.append(r)
            continue
        try:
            cls = classify_place(title, _candidate_category_text(r))
        except Exception:
            cls = None
        if cls == off_class:
            skipped += 1
            emit(f"[LOCAL-830] off-category reuse skip {title!r} {cls} "
                 f"(request is non-food business; pool row kept)")
            continue
        kept.append(r)
    return kept, skipped
