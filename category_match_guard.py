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
    # LOCAL-835 — activity-provider on-category guard (FRESH places path).
    "requested_activity",
    "candidate_is_activity_provider",
    "filter_off_category_activity",
    # LOCAL-845 — cheap Serper Places category resolver for the unknown tail.
    "serper_category_resolver",
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


# ── [LOCAL-835] Activity-provider on-category guard (FRESH places path) ───────
#
# WHY (LEAD, GCloud_Storied wave 12 proof 507, gen 00018-8vt, cheap arm —
# "Kiteboarding lessons in Mui Ne, Vietnam" (5)):
# the FRESH places path (the pool did not serve this request) returned Deja Vu
# Restaurant, Kite Bar, Sea Breeze Restaurant, Source Kiteboarding, Mui Ne
# Fishing Village — only ONE (Source Kiteboarding) is a kite school. The three
# gates that keep a tour on-category all MISS an activity-provider request:
#   * LOCAL-830 ``business_off_category_class`` only ever marks the "restaurant"
#     class off-category, AND ``classify_business_vs_landmark("kiteboarding
#     lessons")`` is 'landmark' (neither "lessons" nor "kiteboarding" is a
#     business keyword) — so it is a NO-OP and never even reaches the fresh path.
#   * LOCAL-791B ``filter_off_category`` fires only on a plural CATEGORY noun
#     ("pagodas", "temples"); "kiteboarding lessons" has none → empty → no-op.
#   * PHASE 4 ``_verify_against_intent`` needs the LLM ``poi_type`` and does not
#     run on the cheap arm's places path reliably.
# So food venues (Deja Vu, Sea Breeze, Kite Bar) AND a generic landmark (Mui Ne
# Fishing Village) all survived to narration, padding a kite-lessons tour.
#
# This guard is the DETERMINISTIC, OFFLINE on-category check the FRESH path runs,
# after candidate discovery (before narration) and inside the replenish loop.
# For an ACTIVITY-PROVIDER request (the subject is "<activity> lessons/classes/
# courses/school/rental/hire/instructor/centre/club/academy/…") it keeps ONLY a
# candidate that is a provider of THAT activity:
#   * on-category — the name or the Serper/OSM type/category carries the activity
#     word (or a known synonym: kiteboarding↔kitesurf↔kite, scuba↔dive,
#     bike↔bicycle↔cycling, …), OR a GENERIC provider noun for a physical
#     activity (school/academy/club/centre/rental/outfitter/"water sports");
#   * off-category — a FOOD/DRINK venue (restaurant/bar/café class), UNLESS the
#     request is itself about food;
#   * off-category — a GENERIC LANDMARK with no activity signal (fishing village,
#     beach, market, generic "tourist attraction"), UNLESS the user named it as
#     an anchor;
#   * UNKNOWN (None) candidates with no signal either way are KEPT only when they
#     are not a known-off class — see ``candidate_is_activity_provider``.
#
# Honest shortfall over padding: the guard only ever REMOVES off-category
# candidates. The caller delivers the on-category K it has with the honest
# shortfall line; it never refills the gap with a food/leisure place.

# Trigger nouns whose presence in the request SUBJECT marks an ACTIVITY-PROVIDER
# request: "<activity> <trigger>". A provider offers an activity (teaches it,
# rents the gear, guides it), as opposed to a venue you merely visit.
_ACTIVITY_PROVIDER_TRIGGERS = (
    "lesson", "lessons", "class", "classes", "course", "courses",
    "school", "schools", "academy", "academies",
    "rental", "rentals", "hire", "hires",
    "instructor", "instructors", "instruction", "tuition", "coaching",
    "lessons", "tour", "tours", "trip", "trips", "guide", "guides",
    "centre", "center", "centres", "centers",
    "club", "clubs", "outfitter", "outfitters", "rent",
)

# A bare "centre"/"center"/"club"/"tour" alone does NOT make a provider request —
# "city center", "art center", "book club", "walking tour" are not activity
# providers. These weak triggers only count when the word BEFORE them is a known
# physical ACTIVITY (surf, kite, dive, yoga, …). The strong triggers below mark a
# provider request on their own.
_WEAK_TRIGGERS = frozenset({
    "centre", "center", "centres", "centers", "club", "clubs",
    "tour", "tours", "trip", "trips", "guide", "guides",
})

# Physical activities a provider teaches / rents / guides. The leading words of a
# provider request ("kiteboarding lessons", "scuba diving courses", "bike
# rental") are one of these. Each maps to the set of synonym tokens that a real
# provider's NAME or TYPE uses for the same activity, so "Source Kiteboarding"
# and "Muine Kitesurf School" both read as kite providers, and "Blue Dive
# Center" reads as a scuba provider.
_ACTIVITY_SYNONYMS: "Dict[str, Tuple[str, ...]]" = {
    "kiteboarding": ("kiteboarding", "kiteboard", "kitesurf", "kitesurfing",
                     "kite", "kiting"),
    "kitesurfing": ("kitesurfing", "kitesurf", "kiteboarding", "kiteboard",
                    "kite", "kiting"),
    # [LOCAL-843] "Kitesurf lessons" folds the activity head to "kitesurf",
    # which was NOT a key here (only kiteboarding/kitesurfing/kite were), so the
    # token set collapsed to the single literal {"kitesurf"} and a real school
    # named "Mui Ne KITE School" / "KITEBOARDING Mui Ne" failed the on-category
    # match → yield loss. Give "kitesurf" its own full-family entry.
    "kitesurf": ("kitesurf", "kitesurfing", "kiteboarding", "kiteboard",
                 "kite", "kiting"),
    "windsurfing": ("windsurf", "windsurfing"),
    "surfing": ("surf", "surfing", "surfboard"),
    "surf": ("surf", "surfing", "surfboard"),
    "kite": ("kite", "kiteboarding", "kiteboard", "kitesurf", "kitesurfing",
             "kiting"),
    "scuba": ("scuba", "dive", "diving", "divers", "freedive", "freediving",
              "snorkel", "snorkeling", "snorkelling"),
    "dive": ("scuba", "dive", "diving", "divers", "freedive", "freediving",
             "snorkel", "snorkeling", "snorkelling"),
    "diving": ("scuba", "dive", "diving", "divers", "freedive", "freediving",
               "snorkel", "snorkeling", "snorkelling"),
    "sailing": ("sail", "sailing", "yacht", "yachting"),
    "kayaking": ("kayak", "kayaking", "canoe", "canoeing", "paddle",
                 "paddling", "paddleboard", "sup"),
    "paddleboarding": ("paddleboard", "paddleboarding", "sup", "paddle"),
    "paddle": ("paddle", "paddleboard", "paddleboarding", "sup", "kayak",
               "canoe"),
    "yoga": ("yoga", "yogic"),
    "pilates": ("pilates",),
    "cooking": ("cooking", "cookery", "culinary", "cook"),
    "dance": ("dance", "dancing"),
    "dancing": ("dance", "dancing"),
    "climbing": ("climb", "climbing", "bouldering", "boulder"),
    "cycling": ("cycle", "cycling", "bike", "biking", "bicycle", "bicycles"),
    "biking": ("bike", "biking", "bicycle", "bicycles", "cycle", "cycling"),
    "bike": ("bike", "biking", "bicycle", "bicycles", "cycle", "cycling"),
    "bicycle": ("bicycle", "bicycles", "bike", "biking", "cycle", "cycling"),
    "motorbike": ("motorbike", "motorcycle", "scooter", "moped"),
    "scooter": ("scooter", "moped", "motorbike", "motorcycle"),
    "golf": ("golf", "golfing"),
    "tennis": ("tennis",),
    "horse": ("horse", "horseback", "equestrian", "riding"),
    "fishing": ("fishing", "angling"),
    "skiing": ("ski", "skiing", "snowboard", "snowboarding"),
    "snowboarding": ("snowboard", "snowboarding", "ski", "skiing"),
    "rafting": ("raft", "rafting"),
    "paragliding": ("paraglide", "paragliding", "parasailing", "parasail",
                    "paraglider"),
    "boxing": ("boxing", "muay", "mma", "kickboxing"),
    "muaythai": ("muay", "muaythai", "boxing", "mma"),
    "language": ("language", "languages"),
}

# Generic PROVIDER nouns that, together with an activity subject, mark a stop as
# a provider even when its name does not repeat the activity word. "Water sports
# center", "dive academy", "surf outfitters". A pure dining/landmark class never
# reaches here (it is decided first).
_PROVIDER_NOUNS = (
    "school", "schools", "academy", "academies", "club", "clubs",
    "centre", "center", "centres", "centers",
    "rental", "rentals", "hire", "outfitter", "outfitters",
    "instructor", "instruction", "lessons", "course", "courses",
    "sports", "sport", "watersports", "water sports", "adventure",
    "adventures", "activities", "activity", "studio", "studios",
)

# Place classes that are a GENERIC LANDMARK (not an activity provider): a request
# for a provider must not keep these unless the user named them as an anchor.
_GENERIC_LANDMARK_CLASSES = frozenset({"beach", "market", "monument", "park"})

# Extra generic-landmark words a provider request must drop even when
# ``classify_place`` returns None — a "fishing village", a "viewpoint", a
# generic "tourist attraction" is a place you VISIT, not a provider.
_GENERIC_LANDMARK_WORDS = (
    "fishing village", "village", "viewpoint", "view point", "lookout",
    "sand dunes", "dunes", "waterfall", "falls", "cave", "caves", "island",
    "lake", "river", "hill", "mountain", "canyon", "national park",
    "tourist attraction", "point of interest", "sightseeing", "scenic spot",
    "landmark", "attraction", "monument", "memorial", "square", "plaza",
    "harbour", "harbor", "pier", "promenade", "boardwalk",
    # [LOCAL-835B] Lodging / leisure venues. A RESORT, hotel, guesthouse or spa
    # is a place you STAY or relax, not a provider of the activity — off-category
    # for an activity-provider request unless its OWN name/type carries the
    # activity word (checked first, so "X Kite School at Y Resort" is still kept).
    # Field defect (bounce, tour 868): the 788B map override kept "Sea Horse
    # Resort" on a kiteboarding-lessons tour because places_search confirmed the
    # resort exists — existence is not provider-hood.
    "resort", "resorts", "hotel", "hotels", "motel", "hostel", "guesthouse",
    "guest house", "homestay", "villa", "villas", "bungalow", "bungalows",
    "lodge", "inn", "spa", "beach club", "beach resort",
)


def requested_activity(request: str) -> Optional[Dict]:
    """Detect an ACTIVITY-PROVIDER request and return what it asks for.

    Returns ``{"activity": <leading activity word>, "tokens": <synonym tokens>,
    "trigger": <provider trigger noun>, "is_food": <bool>}`` when the request
    SUBJECT is "<activity> <provider-trigger>" (kiteboarding lessons, scuba diving
    courses, bike rental, yoga classes, surf school, dive centre); ``None`` when
    it is not a provider request (so the guard is a NO-OP).

    Deterministic and offline. The activity word is the token(s) before the
    trigger; ``tokens`` is the synonym set used to match a candidate's name/type
    (falls back to the activity word itself for an activity not in the synonym
    table). A food request ("cooking classes") is still detected as a provider
    request but flagged ``is_food`` so the caller keeps food venues.
    """
    subj = _fold(_request_subject(request))
    if not subj:
        return None
    toks = subj.split()
    if len(toks) < 2:
        # A one-word subject ("kiteboarding") has no trigger — not a provider
        # request shape (it is handled by the business router / other guards).
        return None

    # Find the FIRST provider trigger in the subject and the activity before it.
    for i in range(1, len(toks)):
        word = toks[i]
        if word not in _ACTIVITY_PROVIDER_TRIGGERS:
            continue
        # The activity is the run of words before the trigger.
        activity_words = [t for t in toks[:i] if t]
        if not activity_words:
            continue
        # A connector/stopword run is not an activity ("tours in …" handled by
        # _request_subject already, but guard anyway).
        activity_head = activity_words[-1]
        # Resolve synonyms: try the last word, then the full phrase, against the
        # synonym table; else use the activity words themselves as tokens.
        tokens: Set[str] = set()
        matched_known = False
        for aw in activity_words:
            if aw in _ACTIVITY_SYNONYMS:
                tokens.update(_ACTIVITY_SYNONYMS[aw])
                matched_known = True
        # [LOCAL-843] STEM fallback: a compound activity word that is not an exact
        # key ("kitesurf", "windsurf", "paddleboard") still belongs to a known
        # family. If no exact key matched, union every family that shares a stem
        # with an activity word — a family token that is a prefix of the word, or
        # whose word is a prefix of a family token (≥4 chars, so "ski"/"sup" short
        # tokens do not over-match). This keeps the on-category match wide enough
        # to recognise a provider named with any synonym of the activity.
        if not matched_known:
            for aw in activity_words:
                if len(aw) < 4:
                    continue
                for _key, _syns in _ACTIVITY_SYNONYMS.items():
                    for _tok in _syns:
                        if len(_tok) < 4:
                            continue
                        if aw.startswith(_tok) or _tok.startswith(aw):
                            tokens.update(_syns)
                            matched_known = True
                            break
        # "scuba diving" → head "diving" is known; "bike" → known. If neither
        # word is in the table, take the activity words as literal tokens (still a
        # provider request, matched by name containment).
        if not tokens:
            tokens.update(w for w in activity_words if len(w) >= 3)

        # A WEAK trigger (centre/club/tour) only counts when the activity is a
        # KNOWN physical activity — "art center", "book club", "walking tour",
        # "city tour" must NOT be treated as a provider request.
        if word in _WEAK_TRIGGERS and not matched_known:
            continue
        if not tokens:
            continue

        return {
            "activity": " ".join(activity_words),
            "activity_head": activity_head,
            "tokens": tuple(sorted(tokens)),
            "trigger": word,
            "is_food": is_food_request(request),
        }
    return None


# Food/drink words on a CANDIDATE's name or Serper/OSM type that mark it as a
# food venue for a provider request. Broader than the LOCAL-791B "restaurant"
# CLASS_WORDS (which a shared category tour depends on and must not be widened):
# a real Serper places `type` for food is often "Sandwich shop", "Street food",
# "Vietnamese restaurant", "Ice cream shop", "Juice bar". These are off-category
# for a non-food activity-provider request.
_FOOD_VENUE_WORDS = (
    "restaurant", "cafe", "coffee", "coffeehouse", "bar", "pub", "bistro",
    "eatery", "diner", "food", "bakery", "patisserie", "deli", "brasserie",
    "grill", "steakhouse", "pizzeria", "pizza", "noodle", "noodles", "seafood",
    "sandwich", "burger", "ice cream", "dessert", "juice bar", "smoothie",
    "brewery", "brewpub", "taproom", "winery", "teahouse", "tea house",
    "snack", "street food", "canteen", "buffet", "banh mi",
    # [LOCAL-845] Local-language food words so a venue named only in its own
    # language still reads as food. Vietnamese: "nhà hàng" (restaurant — folds to
    # "nha hang"), "quán" (eatery/bar — "quan"); "nha hang" catches a field
    # defect where "Nhà hàng Nha Trang Xưa" (a heritage-house RESTAURANT) was kept
    # on a scuba-diving-courses tour because its carried name/type had no English
    # food word. These are folded (accent-stripped, lowercased) before matching.
    "nha hang", "quan",
)


def _is_food_venue(name_blob: str, cat_blob: str) -> bool:
    """True when a candidate's name or type marks it as a food/drink venue."""
    for w in _FOOD_VENUE_WORDS:
        fw = _fold(w)
        if not fw:
            continue
        if " " in fw:
            if fw in cat_blob or fw in name_blob:
                return True
        elif len(fw) <= 4:
            if (re.search(r"\b" + re.escape(fw) + r"\b", cat_blob)
                    or re.search(r"\b" + re.escape(fw) + r"\b", name_blob)):
                return True
        elif fw in cat_blob or fw in name_blob:
            return True
    return False


# [LOCAL-847] The SHORT, bare activity roots. On their own in a name, these are
# WEAK — decorative ("Kite Bar", "Surf Café", "The Dive Bar"): the venue is a
# bar/café that merely borrows the activity word. They only make a provider when
# combined with a provider noun ("Surf School", "Dive Centre") or a compound/
# full activity word is present. A STRONG signal is either a compound activity
# word (kitesurf, kiteboarding, windsurfing, diving, paddleboard, snowboarding…)
# or a short root + a provider noun / "&"-"and" construct ("Dive & Dine").
_SHORT_ACTIVITY_ROOTS = frozenset({
    "kite", "surf", "dive", "sail", "yoga", "golf", "swim", "ski", "row",
    "paddle", "kayak", "canoe", "bike", "climb", "cycle",
})

# Provider nouns that, next to a short activity root, promote a mixed venue to a
# provider even when it also carries a food word ("Surf School & Bar", "Dive
# Centre Café"). A superset of the module's _PROVIDER_NOUNS tuned for the in-name
# bridge; kept local so the strong-signal test is self-contained.
_STRONG_PROVIDER_NOUNS = (
    "school", "schools", "academy", "academies", "club", "clubs",
    "centre", "center", "centres", "centers", "station",
    "rental", "rentals", "hire", "outfitter", "outfitters",
    "instructor", "instruction", "lessons", "lesson", "course", "courses",
    "sports", "watersports", "adventure", "adventures", "station", "shop",
)


def _strong_activity_provider_signal(name_blob: str, cat_blob: str,
                                     tokens: Sequence[str],
                                     raw_name: str = "") -> bool:
    """[LOCAL-847] True when the candidate's NAME or TYPE carries a STRONG
    activity-provider signal for the requested activity — strong enough to make it
    a provider even when the name ALSO says bar/café/restaurant ("Kitesurfing Mui
    Ne - Surf Bar", "Dive & Dine", "Surf School & Grill").

    A STRONG signal is any of:
      * a COMPOUND / full activity word among the request's synonym ``tokens``
        (len >= 6, e.g. "kitesurf", "kiteboarding", "windsurfing", "diving",
        "paddleboard", "snowboarding") present in the name/type — NOT a bare short
        root ("kite", "surf", "dive") which on its own is decorative;
      * a SHORT activity root present AND, right beside it, a provider noun
        (school/centre/club/rental/…) or an "&"/"and"/"-" construct that marks a
        combined venue ("Dive & Dine", "Surf School and Bar").

    A plain "Kite Bar" / "The Bar" / "Surf Café" (short root, food head noun, no
    provider noun, no "&") has NO strong signal → it stays a bar/café and is
    dropped by the food check. ``raw_name`` is the UNFOLDED title: ``_fold`` strips
    "&"/"-", so the combined-venue connector is detected on the raw name instead.
    Deterministic, offline."""
    blob = (name_blob + " " + cat_blob).strip()
    if not blob:
        return False
    toks = tokens or ()
    # (a) A compound/full activity word (not a bare short root).
    for t in toks:
        ft = _fold(t)
        if len(ft) < 6:
            continue
        if ft in _SHORT_ACTIVITY_ROOTS:
            continue
        # Substring on the compound word is safe: "kitesurf"/"kiteboarding"/
        # "diving" rarely occur spuriously; require >= 6 chars (above).
        if ft and ft in blob:
            return True
    # (b) A short activity root beside a provider noun or an "&"/"and"/"-"
    # combined-venue construct. Checked on the NAME (the type rarely has "&").
    name = name_blob
    short_roots = [_fold(t) for t in toks if _fold(t) in _SHORT_ACTIVITY_ROOTS]
    short_present = any(
        re.search(r"\b" + re.escape(r) + r"\b", name) for r in short_roots
    )
    if short_present:
        if _text_has_any(blob, _STRONG_PROVIDER_NOUNS):
            return True
        # A combined-venue connector ("Dive & Dine", "Surf - Bar", "Kite and
        # Surf") on the RAW name — fold strips "&"/"-", so use raw. Only when the
        # short root is ADJACENT to the connector, so "Blue Sky Restaurant & Bar"
        # (no activity root) never triggers.
        raw = (raw_name or "").lower()
        if raw and re.search(r"&|\band\b|-", raw):
            for r in short_roots:
                if (re.search(r"\b" + re.escape(r) + r"\b\s*(?:&|\band\b|-)", raw)
                        or re.search(r"(?:&|\band\b|-)\s*\b" + re.escape(r) + r"\b", raw)):
                    return True
    return False


def _text_has_any(blob: str, words: Sequence[str]) -> bool:
    """Whole-word (short) / substring (long) match of any ``words`` in ``blob``
    (both already folded)."""
    for w in words:
        fw = _fold(w)
        if not fw:
            continue
        if " " in fw:
            if fw in blob:
                return True
        elif len(fw) <= 4:
            if re.search(r"\b" + re.escape(fw) + r"\b", blob):
                return True
        elif fw in blob:
            return True
    return False


def candidate_is_activity_provider(
        cand: Dict,
        activity: Dict,
        category_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[bool]:
    """Is ``cand`` a provider of the requested activity?

    * True  — the candidate's name or Serper/OSM type carries the activity word
              (or a synonym), OR a GENERIC provider noun (school/club/centre/
              rental/outfitter/"water sports") — a real provider of the activity.
    * False — the candidate is a FOOD/DRINK class (restaurant/bar/café) and the
              request is NOT about food; OR it is a GENERIC LANDMARK (fishing
              village, beach, market, generic tourist attraction) with no activity
              signal.
    * None  — no signal either way (kept by the caller: we never drop a place we
              cannot classify).

    [LOCAL-845] ``category_resolver`` — an optional callable ``name -> category
    text`` the caller supplies to resolve a candidate whose carried fields give
    NO class signal (the field defect: "Nhà hàng Nha Trang Xưa" reached the guard
    with a name/type that carried no English food word, classified as UNKNOWN,
    and was kept on a scuba-courses tour). When the first pass is about to return
    None (unknown), the resolver is called ONCE with the candidate's title; its
    returned category text is re-classified. A restaurant/café/bar result →
    off-category (False); anything still unknown → None (kept — never drop on no
    evidence). The resolver is only ever called on the unknown tail, so a stop
    already decided by its own name/type costs nothing. The caller is responsible
    for the resolver being cheap (≤ one 24 h-cached Serper Places lookup)."""
    if not activity:
        return None
    title = _candidate_title(cand)
    cat = _candidate_category_text(cand)
    name_blob = _fold(title)
    cat_blob = _fold(cat)
    blob = (name_blob + " " + cat_blob).strip()
    tokens = activity.get("tokens") or ()
    is_food_req = bool(activity.get("is_food"))

    # (1) Strongest positive: the activity word / a synonym appears in the name or
    # the type. "Source Kiteboarding", "Muine Kitesurf School", type "Dive
    # center". This wins over the food/landmark checks ("Kite Bar" is caught in
    # (2) because it has NO activity-provider token — "kite" with "bar" is still a
    # bar; see the food check ordering below).
    has_activity_tok = _text_has_any(blob, tokens)

    # [LOCAL-847] A STRONG activity-provider signal (a COMPOUND activity word, or
    # a short activity root beside a provider noun / "&"-"and" combined-venue
    # construct) in the name/type makes the candidate a PROVIDER even when it also
    # says bar/café/restaurant — a mixed venue ("Kitesurfing Mui Ne - Surf Bar",
    # "Dive & Dine", "Surf School & Grill") that teaches/rents the activity is
    # on-category. A plain "Kite Bar" / "The Bar" / "Surf Café" (bare short root +
    # food head, no provider noun, no "&") has NO strong signal and stays a bar.
    has_strong_signal = _strong_activity_provider_signal(
        name_blob, cat_blob, tokens, raw_name=title)

    # (2) Classify the candidate's place CLASS (food / landmark / …).
    try:
        cls = classify_place(title, cat)
    except Exception:
        cls = None

    # FOOD/DRINK is off-category for a non-food provider request EVEN IF the name
    # also contains the activity word ("Kite Bar", "Surf Café"): the place is a
    # bar/café, not a provider. A food request keeps food venues. [LOCAL-847] A
    # STRONG activity-provider signal OVERRIDES this: a mixed venue that genuinely
    # provides the activity (compound activity word, or short root + provider
    # noun / "&") is kept even though it also carries a food word.
    if cls == "restaurant" or _is_food_venue(name_blob, cat_blob):
        if is_food_req:
            return True
        if has_strong_signal:
            return True
        return False

    # On-category: the activity word / synonym is present and the place is not a
    # food venue → a genuine provider ("Source Kiteboarding", "Jibe's … Kite").
    if has_activity_tok:
        return True

    # A generic provider noun (school/club/centre/rental/"water sports") with no
    # conflicting class → a provider of the activity (a water-sports centre that
    # does not repeat "kite" in its name). Only when NOT a generic landmark class.
    if cls not in _GENERIC_LANDMARK_CLASSES and _text_has_any(blob, _PROVIDER_NOUNS):
        return True

    # GENERIC LANDMARK — a place you visit, not a provider. Off-category for a
    # provider request (unless named-anchor, handled by the caller).
    if cls in _GENERIC_LANDMARK_CLASSES:
        return False
    if _text_has_any(blob, _GENERIC_LANDMARK_WORDS):
        return False

    # [LOCAL-845] UNKNOWN tail — no signal from the candidate's own name/type.
    # Before keeping it (the old behaviour, which let a restaurant with no English
    # food word survive a non-food provider tour), give the caller's resolver ONE
    # chance to supply the place's real category. A restaurant/café/bar result is
    # off-category; anything still unknown is kept (never drop on no evidence).
    if category_resolver is not None:
        try:
            resolved = category_resolver(title)
        except Exception:
            resolved = None
        if resolved:
            res_blob = _fold(resolved)
            # Food/drink type → off-category (the Nha Trang Xua case: resolver
            # returns "Vietnamese restaurant").
            if _is_food_venue("", res_blob):
                return False
            try:
                res_cls = classify_place(title, resolved)
            except Exception:
                res_cls = None
            if res_cls == "restaurant":
                return False
            # A resolved activity word / provider noun promotes to a provider.
            if _text_has_any(res_blob, tokens):
                return True
            if (res_cls not in _GENERIC_LANDMARK_CLASSES
                    and _text_has_any(res_blob, _PROVIDER_NOUNS)):
                return True
            # A resolved generic-landmark class/word → off-category.
            if res_cls in _GENERIC_LANDMARK_CLASSES:
                return False
            if _text_has_any(res_blob, _GENERIC_LANDMARK_WORDS):
                return False

    # No signal either way → UNKNOWN (kept).
    return None


def filter_off_category_activity(
        cands: List[Dict],
        request: str,
        log: Optional[Callable[[str], None]] = None,
        named_anchors: Optional[Sequence[str]] = None,
        category_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[List[Dict], int]:
    """[LOCAL-835] Keep only providers of the requested activity on the FRESH
    places path.

    For an ACTIVITY-PROVIDER request (``requested_activity`` is not None) that is
    NOT about food, drop every candidate that is a food/drink venue or a generic
    landmark with no activity signal; keep the activity's providers and any
    candidate we cannot classify. A candidate the user NAMED by hand is always
    kept. Returns ``(kept, dropped_count)``.

    [LOCAL-845] ``category_resolver`` — optional ``name -> category text`` passed
    through to ``candidate_is_activity_provider`` for the UNKNOWN tail only (a
    candidate whose own name/type gives no class signal). The caller supplies a
    cheap resolver (one 24 h-cached Serper Places lookup) so a restaurant that
    reached the guard without an English food word (the "Nhà hàng Nha Trang Xưa"
    field defect) is classified off-category instead of being kept on no evidence.

    NO-OP (rows unchanged, dropped=0) when the request is not a provider request,
    or is a food provider request (cooking classes keep food venues). Best-effort:
    any internal error returns the rows unchanged — a guard bug must never empty a
    tour; the honest shortfall is for when there are genuinely too few providers,
    not when the guard crashed.
    """
    emit = log or print
    if not cands:
        return list(cands), 0
    try:
        activity = requested_activity(request)
    except Exception:
        return list(cands), 0
    if not activity or activity.get("is_food"):
        return list(cands), 0

    anchor_keys = {_fold(a) for a in (named_anchors or []) if a}
    kept: List[Dict] = []
    dropped = 0
    for cand in cands:
        title = _candidate_title(cand)
        if anchor_keys and _fold(re.sub(r"\s*\([^)]*\)\s*", " ", title)) in anchor_keys:
            kept.append(cand)
            continue
        try:
            verdict = candidate_is_activity_provider(
                cand, activity, category_resolver=category_resolver)
        except Exception:
            verdict = None
        if verdict is False:
            dropped += 1
            try:
                cls = classify_place(title, _candidate_category_text(cand))
            except Exception:
                cls = None
            emit(f"[LOCAL-835] off-category provider drop {title!r} "
                 f"(class={cls or '?'}; request='{activity['activity']} "
                 f"{activity['trigger']}')")
            continue
        kept.append(cand)
    return kept, dropped


# ── [LOCAL-845] Cheap Serper Places category resolver for the unknown tail ────
def serper_category_resolver(
        scope: str,
        log: Optional[Callable[[str], None]] = None,
) -> Callable[[str], Optional[str]]:
    """Build a ``name -> category text`` resolver backed by ONE Serper Places
    lookup per name, scoped to ``scope``.

    Passed as ``category_resolver`` to ``filter_off_category_activity`` so the
    activity guard can classify a candidate whose own carried name/type gave NO
    class signal (the "Nhà hàng Nha Trang Xưa" field defect — a restaurant kept on
    a scuba-courses tour because its name had no English food word). Only the
    UNKNOWN tail reaches the resolver, so a stop already decided by its own fields
    costs nothing.

    Cheap by construction: ``places_search.places_search`` caches identical
    (query, ll) for 24 h, so a name already verified on the map during generation
    is a CACHE HIT and bills nothing; otherwise it is the ONE extra lookup the
    ticket allows (≤ one Places call, priced ≈ $0.002). Returns the resolved
    Serper category text (e.g. "Vietnamese restaurant"), or None when Serper is
    off / nothing matched. Never raises. An in-process memo avoids a second lookup
    for the same name within one tour."""
    emit = log or print
    memo: Dict[str, Optional[str]] = {}

    def _resolve(name: str) -> Optional[str]:
        key = _fold(name)
        if not key:
            return None
        if key in memo:
            return memo[key]
        resolved: Optional[str] = None
        try:
            import places_search as _ps
            if _ps.serper_places_enabled():
                scope_center = None
                try:
                    from stop_existence_gate import _geocode_scope_center as _gsc
                    scope_center = _gsc(scope)
                except Exception:
                    scope_center = None
                recs = _ps.places_search(name, scope, limit=1,
                                         scope_center=scope_center)
                if recs:
                    cat = (recs[0].get("_serper_category")
                           or recs[0].get("category") or "")
                    resolved = str(cat).strip() or None
                    if resolved:
                        emit(f"[LOCAL-845] category resolve {name!r} -> "
                             f"{resolved!r} (1 Serper Places lookup)")
        except Exception as _err:
            emit(f"[LOCAL-845] category resolve skipped for {name!r} "
                 f"(non-fatal): {_err}")
            resolved = None
        memo[key] = resolved
        return resolved

    return _resolve
