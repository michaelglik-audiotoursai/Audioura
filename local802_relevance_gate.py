#!/usr/bin/env python3
"""local802_relevance_gate.py — LOCAL-802

Four pure, unit-testable concerns found by the P1 blind A/B (cheap arm, Serper):

  1. RELEVANCE GATE on injected passages (interpretive/background passages and
     search snippets). The d3 Mui Ne seafood tour carried a Permian–Triassic
     extinction paragraph (251.9 Mya, 81% of marine species) inside a seafood-
     restaurant stop; the b1 Ben Thanh massage tour carried a reality-TV
     digression ("The Race", 42,000 km). Both are passages that mention NEITHER
     the stop, its place, nor its theme/category — they are the LLM free-
     associating from a thin thread. A passage must mention the stop, its place,
     or its theme/category; otherwise it is dropped and logged
     ``[LOCAL-802] off-topic passage dropped <stop> <first words>``.

  2. SAME-BUILDING DEDUPE. The r2 Arnold Arboretum tour delivered the Visitor
     Center AND the Hunnewell Building as two separate stops with contradictory
     founding dates — they are the SAME building (the Visitor Center IS the
     Hunnewell Building). Two stops that are aliases of one building (Wikidata
     "located in" / same coords ≤ 60 m / alias names) collapse to one.

  3. STOP-COUNT WIDENING for business/places tours. The b1 tour delivered 1 of 3
     requested stops. When the places path finds fewer in-scope places than
     requested, widen the search once (radius ×2, bbox grown about its centre,
     within the city) before delivering fewer.

  4. FALSE COVERAGE (addendum 4). A named NATURAL FEATURE / landmark ("White Sand
     Dunes") is covered only by a stop of the SAME KIND — never by a
     hotel/resort/restaurant/shop that merely borrows its name ("Mui Ne Sand
     Dunes Resort"). ``natural_feature_covered_by`` is the predicate
     area_resolver's reconciler consults before it calls a named feature covered.

Each function here is deterministic and offline (no network, no LLM, no DB), so
the P1-fixture unit tests run without a paid API.  Addendum 5 (named places in
driving/nature tours become stops) is wired in generate_tour_text.py by extending
the same walking-path named-anchor insertion to the driving/nature categories;
the scope predicate ``is_place_anchor_tour_category`` lives here.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Set, Tuple

__all__ = [
    "fold",
    "theme_tokens_for_category",
    "passage_is_relevant",
    "relevance_report",
    "off_topic_drop_log_line",
    "filter_injected_passages",
    "scrub_off_domain_sentences",
    "same_building",
    "dedupe_same_building_stops",
    "natural_feature_kind",
    "stop_kind",
    "natural_feature_covered_by",
    "is_place_anchor_tour_category",
    "widen_bbox",
    "widen_radius_km",
]


# ─── text folding ────────────────────────────────────────────────────────────

def fold(text: str) -> str:
    """Lowercase, strip accents, collapse non-word runs to single spaces.

    Mirrors the folding used by story_relevance / area_resolver so this gate
    behaves the same way on diacritics ("Mũi Né" == "mui ne")."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped.lower())
    return " ".join(stripped.split())


_RELEVANCE_STOPWORDS = {
    "the", "and", "for", "with", "from", "des", "les", "del", "aux", "sur",
    "dans", "une", "que", "qui", "por", "con", "para", "nel", "dei", "this",
    "that", "was", "were", "his", "her", "its", "their", "been", "have", "you",
    "your", "our", "are", "not", "but", "all", "any", "has", "had",
    # Tour-generic filler that is never a distinctive match on its own.
    "tour", "stop", "stops", "visit", "place", "places", "area", "street",
    "road", "avenue", "city", "town", "near", "located", "local", "locals",
}


def _content_tokens(text: str, min_len: int = 4) -> Set[str]:
    """Distinctive content tokens of ``text`` (folded, length ≥ min_len,
    not a stopword)."""
    return {
        w for w in fold(text).split()
        if len(w) >= min_len and w not in _RELEVANCE_STOPWORDS
    }


# ─── 1. relevance gate on injected passages ──────────────────────────────────

# Theme/category vocabulary per tour category. A passage is on-theme when it
# names any of the stop's own tokens, the place's tokens, OR a theme word for the
# tour's category. Deliberately generous (retrieval is scarce; the cost of a
# wrong drop is a real fact lost) — the Permian / reality-TV passages fail even
# this generous bar because they share NO token with the stop, the place, or the
# category vocabulary.
_CATEGORY_THEME_WORDS: Dict[str, Set[str]] = {
    "restaurant": {
        "restaurant", "dining", "food", "seafood", "crab", "prawn", "oyster",
        "fish", "shellfish", "menu", "dish", "dishes", "kitchen", "chef", "cook",
        "cooking", "grill", "grilled", "cuisine", "meal", "eat", "eating",
        "flavor", "flavour", "taste", "fresh", "catch", "market", "terrace",
        "diner", "diners", "price", "prices", "vnd", "dong", "reservation",
        "fisherman", "fishing", "boat", "boats", "shore", "sea", "coast",
        "coastal", "harvest", "tide", "tides", "wine", "beer", "drink",
    },
    "dining": set(),  # resolved to 'restaurant' below
    "business": {
        "spa", "massage", "wellness", "treatment", "therapy", "relax",
        "relaxation", "sauna", "steam", "herbal", "skincare", "salon", "studio",
        "shop", "store", "service", "services", "staff", "appointment",
        "booking", "price", "prices", "open", "hours", "gym", "fitness",
        "clinic", "practice",
    },
    "walking": {
        "street", "square", "plaza", "quarter", "district", "neighbourhood",
        "neighborhood", "building", "architecture", "facade", "monument",
        "landmark", "church", "cathedral", "temple", "pagoda", "market",
        "colonial", "historic", "history", "heritage", "founded", "built",
        "century", "war", "trail", "route", "path", "walk",
    },
    "nature": {
        "garden", "gardens", "collection", "tree", "trees", "shrub", "shrubs",
        "plant", "plants", "flower", "flowers", "bloom", "blooms", "botanical",
        "arboretum", "park", "forest", "grove", "species", "horticulture",
        "landscape", "lilac", "rose", "roses", "path", "trail", "nature",
        "dune", "dunes", "sand", "beach", "canyon", "stream", "waterfall",
        "mountain", "hill", "valley", "coast", "nursery",
    },
    "neighbourhood": {
        "neighbourhood", "neighborhood", "street", "square", "building",
        "architecture", "historic", "history", "heritage", "founded", "built",
        "century", "residents", "community", "district", "quarter",
    },
    "driving": {
        "drive", "driving", "road", "route", "scenic", "coast", "coastal",
        "cape", "harbor", "harbour", "village", "beach", "lighthouse", "view",
        "viewpoint", "overlook", "shore", "bay", "point", "island", "dune",
        "dunes", "sand", "canyon", "stream", "waterfall", "mountain", "hill",
    },
    "museum": {
        "museum", "collection", "gallery", "exhibit", "exhibition", "work",
        "works", "painting", "sculpture", "artist", "artwork", "curator",
        "gallery", "room", "display", "masterpiece",
    },
}
_CATEGORY_THEME_WORDS["dining"] = _CATEGORY_THEME_WORDS["restaurant"]


def theme_tokens_for_category(category: Optional[str]) -> Set[str]:
    """Theme/category vocabulary tokens for a tour category (folded, lowercase).

    Unknown/empty categories return an empty set: the passage must then earn
    relevance from the stop name or the place, not the category."""
    cat = fold(category or "")
    if not cat:
        return set()
    # Match on the first word of the category label ("restaurant tour" -> ...).
    for key, words in _CATEGORY_THEME_WORDS.items():
        if key in cat:
            return set(words)
    return set()


def passage_is_relevant(
    passage: str,
    stop_title: str = "",
    place: str = "",
    category: Optional[str] = None,
    theme: Optional[str] = None,
    extra_terms: Optional[Sequence[str]] = None,
) -> bool:
    """True when an injected passage is ABOUT this stop, its place, or its theme.

    A passage earns relevance (any ONE is enough — a generous, asymmetric bar):
      * it shares a distinctive content token with the STOP title;
      * it shares a distinctive content token with the PLACE (city/area/venue);
      * it shares a token with the TOUR THEME phrase (when one is given);
      * it shares a token with the CATEGORY vocabulary
        (``theme_tokens_for_category``);
      * it shares a token with any caller-supplied ``extra_terms``.

    Otherwise it is off-topic and the caller drops it. The Permian-extinction and
    "The Race" passages share none of these with their seafood / spa stops, so
    both are rejected; the on-topic seafood/spa passages around them are kept.
    """
    p_tokens = _content_tokens(passage)
    if not p_tokens:
        # Nothing distinctive to judge — treat as off-topic (an empty/placeholder
        # passage carries no fact worth injecting).
        return False

    allowed: Set[str] = set()
    allowed |= _content_tokens(stop_title)
    allowed |= _content_tokens(place)
    if theme:
        allowed |= _content_tokens(theme)
    for t in (extra_terms or []):
        allowed |= _content_tokens(t)
    allowed |= theme_tokens_for_category(category)

    if not allowed:
        # No anchors supplied at all — cannot judge; keep (do not drop blindly).
        return True

    if not (p_tokens & allowed):
        return False

    # The passage DOES share a token with the stop/place/theme. But the P1
    # reality-TV digression ("… contestants might have brushed past this spa. The
    # competition, spanning over 42,000 kilometres across continents …") name-drops
    # the stop ("spa") and the country ("Vietnam") and then is ABOUT a television
    # race — it shares a token yet is a digression. Drop a passage that is
    # DOMINATED by an off-domain spectacle (a TV show / sporting race / geological
    # epoch) even when it mentions the stop in passing.
    if _is_off_domain_digression(passage):
        return False

    return True


# Off-domain "spectacle" markers: a passage dominated by these is a digression
# (a TV competition, a long-distance race, a mass-extinction / geological epoch),
# not content about a tour stop — even when it name-drops the stop.
_OFF_DOMAIN_MARKERS = (
    r"reality\s+(?:competition|show|series|tv)",
    r"\bgame\s+show\b",
    r"\bcontestants?\b",
    r"\bthe\s+race\b",
    r"\b\d{2,3},\d{3}\s*(?:-?\s*)?(?:kilomet|kilom_|km|mile)",  # 42,000 km
    r"across\s+(?:three|four|five|\d+)\s+continents",
    r"extinction\s+event",
    r"permian|triassic|jurassic|cretaceous|cambrian",
    r"\bmillion\s+years\s+ago\b",
    r"\bmya\b",
    r"\d+\s*%\s+of\s+(?:marine|all|the)\s+species",
)
_OFF_DOMAIN_RE = re.compile("|".join(_OFF_DOMAIN_MARKERS), re.IGNORECASE)


def _is_off_domain_digression(passage: str) -> bool:
    """True when a passage is dominated by an off-domain spectacle (a TV
    competition, a long-distance race, a mass-extinction / geological epoch) — the
    P1 reality-TV ("The Race", 42,000 km) and Permian-extinction digressions. Two
    or more distinct off-domain markers, OR one strong marker (a reality
    competition / extinction event / geological period) is enough; a single
    incidental number is not."""
    text = passage or ""
    hits = _OFF_DOMAIN_RE.findall(text)
    # findall on an alternation returns the matched substrings; count non-empty.
    n = sum(1 for h in hits if (h if isinstance(h, str) else "".join(h)).strip())
    if n >= 2:
        return True
    # One STRONG marker alone is decisive.
    strong = re.compile(
        r"reality\s+(?:competition|show|series|tv)|\bgame\s+show\b|"
        r"extinction\s+event|permian|triassic|\bmya\b|"
        r"\d+\s*%\s+of\s+(?:marine|all|the)\s+species",
        re.IGNORECASE)
    return bool(strong.search(text))


def relevance_report(
    passage: str,
    stop_title: str = "",
    place: str = "",
    category: Optional[str] = None,
    theme: Optional[str] = None,
    extra_terms: Optional[Sequence[str]] = None,
) -> Dict:
    """``passage_is_relevant`` with the matched/overlap tokens, for logging/tests."""
    p_tokens = _content_tokens(passage)
    allowed: Set[str] = set()
    allowed |= _content_tokens(stop_title)
    allowed |= _content_tokens(place)
    if theme:
        allowed |= _content_tokens(theme)
    for t in (extra_terms or []):
        allowed |= _content_tokens(t)
    allowed |= theme_tokens_for_category(category)
    hits = sorted(p_tokens & allowed)
    if not p_tokens:
        kept = False
    elif not allowed:
        kept = True
    else:
        kept = bool(hits)
    return {"kept": kept, "hits": hits, "passage_tokens": sorted(p_tokens)}


def off_topic_drop_log_line(stop_title: str, passage: str) -> str:
    """The exact mandated log line for a dropped off-topic passage.

    ``[LOCAL-802] off-topic passage dropped <stop> <first words>``
    (the first ~6 words of the passage, so a reviewer can find it)."""
    first_words = " ".join((passage or "").split()[:6])
    return (f"[LOCAL-802] off-topic passage dropped "
            f"{(stop_title or '?').strip()} {first_words}")


def _passage_text(p) -> str:
    """Text of a passage given as a dict ({'text': ...}) or a bare string."""
    if isinstance(p, dict):
        return p.get("text") or p.get("snippet") or p.get("passage") or ""
    return str(p or "")


# A sentence that carries an off-domain marker is a digression even when the
# surrounding stop body is on-topic. The P1 d3 run wove the Permian–Triassic
# extinction through a seafood stop sentence-by-sentence ("flood basalt
# eruptions", "400 to 2,500 ppm", "wiping out marine species", "oceans
# post-extinction"), and b1 wove the reality-TV race — neither came through a
# retrieved passage the injection gate sees; the narration LLM generated them
# from its own knowledge. This is the post-generation text scrub that removes
# those sentences from the delivered stop body.
_OFF_DOMAIN_SENTENCE_RE = re.compile(
    r"permian|triassic|jurassic|cretaceous|cambrian|devonian|ordovician"
    r"|extinction\s+event|mass\s+extinction|post-?extinction"
    r"|flood\s+basalt|\bppm\b|million\s+years\s+ago|\bmya\b"
    r"|\d+\s*%\s+of\s+(?:marine|all|the)\s+(?:species|life)"
    r"|wiping?\s+out\s+(?:marine|all|the)\s+(?:species|life)"
    r"|reality\s+(?:competition|show|series|tv)|\bgame\s+show\b"
    r"|\bcontestants?\b|\bthe\s+race\b"
    r"|\d{2,3},\d{3}\s*(?:-?\s*)?(?:kilomet|km|mile)"
    r"|across\s+(?:three|four|five|\d+)\s+continents",
    re.IGNORECASE)


def _split_sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def scrub_off_domain_sentences(text: str, stop_title: str = "", log=None):
    """Remove sentences that are off-domain digressions (a mass-extinction /
    geological epoch, a reality-TV race) from a delivered stop body.

    Returns ``(scrubbed_text, dropped_sentences)``. A sentence is dropped when it
    carries an off-domain marker (``_OFF_DOMAIN_SENTENCE_RE``). Never empties the
    text: if EVERY sentence would be dropped (the whole body is the digression),
    the text is returned unchanged so the caller still has something — a caller
    that wants to drop the stop entirely can inspect ``dropped_sentences``. Pure;
    logs each drop with the mandated line when ``log`` is given.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return text, []
    kept, dropped = [], []
    for s in sentences:
        if _OFF_DOMAIN_SENTENCE_RE.search(s):
            dropped.append(s)
            if log:
                log(off_topic_drop_log_line(stop_title, s))
        else:
            kept.append(s)
    if not kept:
        # The entire body is off-domain — leave it (never empty); the caller sees
        # the drops and can act (e.g. regenerate the stop).
        return text, dropped
    if not dropped:
        return text, []
    return " ".join(kept).strip(), dropped



def filter_injected_passages(
    passages: Sequence,
    stop_title: str = "",
    place: str = "",
    category: Optional[str] = None,
    theme: Optional[str] = None,
    extra_terms: Optional[Sequence[str]] = None,
    log=None,
) -> Tuple[List, List[str]]:
    """Keep only passages relevant to the stop/place/theme; log every drop.

    Returns ``(kept, dropped_log_lines)``. ``passages`` may be dicts or strings;
    kept items are returned unchanged (same type) and in order. ``log`` is an
    optional callable (e.g. ``print``) invoked once per dropped passage with the
    mandated log line.
    """
    kept: List = []
    dropped: List[str] = []
    for p in passages or []:
        text = _passage_text(p)
        if passage_is_relevant(text, stop_title, place, category, theme, extra_terms):
            kept.append(p)
        else:
            line = off_topic_drop_log_line(stop_title, text)
            dropped.append(line)
            if log:
                log(line)
    return kept, dropped


# ─── 2. same-building dedupe ──────────────────────────────────────────────────

_SAME_BUILDING_METERS = 60.0

# [LOCAL-802] Curated same-building alias groups — a deterministic, offline
# bridge for well-documented building-alias relationships that Wikidata may not
# resolve by name (or that the delivered coordinates place far apart because they
# were fabricated). Each group is a set of folded names that are ONE building; a
# stop whose folded name is in a group is treated as carrying every other name in
# the group as an alias. Seeded from the P1 r2 evidence: the Arnold Arboretum
# Visitor Center IS the Hunnewell Building. Add only facts, never guesses.
_CURATED_BUILDING_ALIASES = [
    {
        "the arnold arboretum visitor center",
        "arnold arboretum visitor center",
        "hunnewell building",
        "the hunnewell building",
        "arnold arboretum hunnewell building",
    },
]


def _curated_aliases_for(folded_name: str) -> Set[str]:
    """Every folded name in a curated same-building group that contains
    ``folded_name`` (by exact membership or containment)."""
    out: Set[str] = set()
    if not folded_name:
        return out
    for group in _CURATED_BUILDING_ALIASES:
        if folded_name in group or any(
                g in folded_name or folded_name in g for g in group):
            out |= group
    return out


# Building-type / generic words stripped before an alias-name comparison. "The
# Arnold Arboretum Visitor Center" and "Hunnewell Building" share no token, so
# name-only matching is not enough — the alias list and the located-in / coords
# signals carry the match.
_BUILDING_NOISE = {
    "the", "building", "hall", "house", "center", "centre", "visitor",
    "visitors", "information", "office", "wing", "annex", "pavilion", "block",
    "a", "an", "of", "and",
}


def _haversine_m(a, b) -> float:
    """Metres between two (lat, lng) pairs; inf when either is missing/zero."""
    try:
        import math
        lat1, lng1 = float(a[0]), float(a[1])
        lat2, lng2 = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError):
        return float("inf")
    if (lat1 == 0.0 and lng1 == 0.0) or (lat2 == 0.0 and lng2 == 0.0):
        return float("inf")
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _stop_latlng(stop: Dict):
    """Best (lat, lng) for a stop across the keys the pipeline stamps."""
    if not isinstance(stop, dict):
        return None
    for lat_k, lng_k in (("wikidata_lat", "wikidata_lng"),
                         ("latitude", "longitude"), ("lat", "lng"),
                         ("lat", "lon")):
        lat, lng = stop.get(lat_k), stop.get(lng_k)
        if lat is None or lng is None:
            continue
        try:
            flat, flng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        if flat == 0.0 and flng == 0.0:
            continue
        return (flat, flng)
    # "lat,lng" packed in a coordinates string.
    coords = stop.get("coordinates")
    if isinstance(coords, str) and "," in coords:
        try:
            a, b = coords.split(",", 1)
            flat, flng = float(a.strip()), float(b.strip())
            if not (flat == 0.0 and flng == 0.0):
                return (flat, flng)
        except (ValueError, TypeError):
            pass
    return None


def _aliases_of(stop: Dict) -> Set[str]:
    """Folded alias set for a stop: its name plus any 'aliases'/'also_known_as'
    list it carries (from Wikidata labels/aliases)."""
    out: Set[str] = set()
    if not isinstance(stop, dict):
        return out
    name = stop.get("name") or stop.get("title") or ""
    if name:
        out.add(fold(name))
    for key in ("aliases", "also_known_as", "alt_names", "alias"):
        val = stop.get(key)
        if isinstance(val, str):
            out.add(fold(val))
        elif isinstance(val, (list, tuple, set)):
            for v in val:
                if v:
                    out.add(fold(v))
    # [LOCAL-802] Curated same-building alias bridge (offline, deterministic) — a
    # stop in a known group carries every other name in that group as an alias.
    for a in list(out):
        out |= _curated_aliases_for(a)
    return {a for a in out if a}


def _name_tokens_no_building(name: str) -> Set[str]:
    return {w for w in fold(name).split()
            if len(w) >= 4 and w not in _BUILDING_NOISE}


def same_building(a: Dict, b: Dict) -> bool:
    """True when two stops are the SAME physical building.

    Any ONE signal is sufficient (ticket: aliases / located-in / coords ≤ 60 m):

      1. ALIAS: a name of one stop appears in the other's alias set (or vice
         versa) — "Hunnewell Building" is listed among the Visitor Center's
         aliases, or they share the same Wikidata QID.
      2. LOCATED-IN: one stop's ``located_in`` / ``part_of`` QID equals the
         other's Wikidata QID (the Visitor Center is "located in" the Hunnewell
         Building).
      3. COORDS: both carry coordinates within ``_SAME_BUILDING_METERS``.

    Pure; missing signals simply don't fire (never a false merge on absence).
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False

    # Same Wikidata QID → unquestionably the same entity.
    qa = (a.get("wikidata_qid") or a.get("qid") or "").strip()
    qb = (b.get("wikidata_qid") or b.get("qid") or "").strip()
    if qa and qb and qa == qb:
        return True

    # 1. Alias overlap.
    aliases_a = _aliases_of(a)
    aliases_b = _aliases_of(b)
    if aliases_a & aliases_b:
        return True
    name_a = fold(a.get("name") or a.get("title") or "")
    name_b = fold(b.get("name") or b.get("title") or "")
    if name_a and name_a in aliases_b:
        return True
    if name_b and name_b in aliases_a:
        return True

    # 2. located-in / part-of QID equals the other's entity QID.
    def _located_qids(s: Dict) -> Set[str]:
        out = set()
        for key in ("located_in", "located_in_qid", "part_of", "part_of_qid"):
            v = s.get(key)
            if isinstance(v, str) and v.strip():
                out.add(v.strip())
            elif isinstance(v, (list, tuple, set)):
                out |= {str(x).strip() for x in v if x}
        return out
    if qb and qb in _located_qids(a):
        return True
    if qa and qa in _located_qids(b):
        return True

    # 3. Coordinates within 60 m. Require it to be a genuine point match AND a
    #    shared non-building name token, OR a very close (<= 60 m) coincidence
    #    with no evidence they differ — two numbered rooms of one museum can be
    #    < 60 m apart and are NOT the same building, so pure coords alone is not
    #    enough unless the names also overlap on a content token or one name is
    #    a subset of the other.
    pa, pb = _stop_latlng(a), _stop_latlng(b)
    if pa and pb and _haversine_m(pa, pb) <= _SAME_BUILDING_METERS:
        ta = _name_tokens_no_building(a.get("name") or "")
        tb = _name_tokens_no_building(b.get("name") or "")
        if ta and tb and (ta & tb or ta <= tb or tb <= ta):
            return True
    return False


def _merge_pref(primary: Dict, dup: Dict) -> Dict:
    """Merge ``dup`` into ``primary`` without losing identity data (QID/coords/
    aliases). Destination values win; the duplicate's alias/name is recorded."""
    merged = dict(primary)
    for key in ("wikidata_qid", "qid", "wikidata_lat", "wikidata_lng",
                "latitude", "longitude", "coordinates", "address"):
        if not merged.get(key) and dup.get(key):
            merged[key] = dup[key]
    # Fold the duplicate's name into aliases so a later pass still recognises it.
    aliases = set()
    for s in (primary, dup):
        a = s.get("aliases")
        if isinstance(a, (list, tuple, set)):
            aliases |= {str(x) for x in a if x}
        elif isinstance(a, str) and a:
            aliases.add(a)
    dup_name = dup.get("name") or dup.get("title")
    if dup_name and fold(dup_name) != fold(primary.get("name") or ""):
        aliases.add(dup_name)
    if aliases:
        merged["aliases"] = sorted(aliases)
    return merged


def dedupe_same_building_stops(stops: Sequence[Dict], log=None):
    """Collapse stops that are the same building (``same_building``) to one.

    Order-preserving: the FIRST occurrence survives and absorbs the later
    duplicate's identity data (``_merge_pref``); a hand-named / user-explicit stop
    is always preferred as the survivor over a non-explicit duplicate. Returns
    ``(deduped, removed_names)``.
    """
    kept: List[Dict] = []
    removed: List[str] = []
    for s in stops or []:
        if not isinstance(s, dict):
            kept.append(s)
            continue
        match_idx = None
        for i, k in enumerate(kept):
            if isinstance(k, dict) and same_building(k, s):
                match_idx = i
                break
        if match_idx is None:
            kept.append(s)
            continue
        existing = kept[match_idx]
        s_explicit = bool(s.get("user_explicit") or s.get("_anchor"))
        e_explicit = bool(existing.get("user_explicit") or existing.get("_anchor"))
        if s_explicit and not e_explicit:
            # The new one is user-named — it becomes the survivor.
            merged = _merge_pref(s, existing)
            removed.append(existing.get("name") or existing.get("title") or "?")
            kept[match_idx] = merged
        else:
            merged = _merge_pref(existing, s)
            removed.append(s.get("name") or s.get("title") or "?")
            kept[match_idx] = merged
        if log:
            log(f"[LOCAL-802] same-building dedupe: merged "
                f"{s.get('name') or s.get('title')!r} into "
                f"{kept[match_idx].get('name')!r}")
    return kept, removed


# ─── 4. false coverage (addendum 4) ───────────────────────────────────────────

# A named NATURAL FEATURE / landmark is covered only by a stop of the SAME KIND.
# A hotel/resort/restaurant/shop that borrows the feature's name does NOT cover
# it ("Mui Ne Sand Dunes Resort" is a hotel, not the White Sand Dunes).
_NATURAL_FEATURE_WORDS = {
    "dune", "dunes", "beach", "canyon", "stream", "waterfall", "falls",
    "mountain", "mount", "hill", "valley", "cave", "grotto", "lake", "lagoon",
    "bay", "cove", "cliff", "cliffs", "gorge", "river", "spring", "springs",
    "forest", "grove", "island", "peninsula", "cape", "point", "peak", "summit",
    "ridge", "plateau", "marsh", "wetland", "reef", "rock", "rocks", "pond",
    "meadow", "glacier", "crater", "oasis", "desert", "park", "reserve",
    "garden", "gardens", "arboretum", "trail",
}

# Commercial / built-venue words that mark a stop as a BUSINESS borrowing a
# feature's name — never a cover for the natural feature itself.
_COMMERCIAL_VENUE_WORDS = {
    "resort", "hotel", "motel", "hostel", "inn", "lodge", "villa", "villas",
    "restaurant", "cafe", "bar", "pub", "bistro", "diner", "grill", "eatery",
    "shop", "store", "boutique", "market", "mall", "spa", "salon", "club",
    "lounge", "guesthouse", "guest", "homestay", "apartments", "apartment",
    "residence", "residences", "bungalow", "bungalows", "camp", "campground",
    "restaurant", "coffee", "bakery", "resorts",
}


def natural_feature_kind(name: str) -> Optional[str]:
    """If ``name`` names a natural feature, return its feature word (folded),
    else None. 'White Sand Dunes' -> 'dunes'; 'Fairy Stream' -> 'stream'."""
    toks = fold(name).split()
    for t in toks:
        if t in _NATURAL_FEATURE_WORDS:
            return t
    return None


def stop_kind(stop) -> str:
    """Coarse kind of a stop: 'commercial' (hotel/resort/restaurant/shop/…),
    'natural' (its name/type is a natural feature), or 'other'.

    Reads the stop NAME and any explicit type fields ('type', 'poi_type',
    'category', 'osm_type'). A commercial marker anywhere wins over a natural one
    (a "Sand Dunes Resort" is commercial), because the ticket's failure is a
    hotel borrowing a feature's name."""
    if isinstance(stop, dict):
        name = stop.get("name") or stop.get("title") or ""
        type_blob = " ".join(
            str(stop.get(k) or "") for k in
            ("type", "poi_type", "category", "osm_type", "type_label",
             "Type/Specialty", "specialty"))
    else:
        name = str(stop or "")
        type_blob = ""
    toks = set(fold(name).split()) | set(fold(type_blob).split())
    if toks & _COMMERCIAL_VENUE_WORDS:
        return "commercial"
    if toks & _NATURAL_FEATURE_WORDS:
        return "natural"
    return "other"


def natural_feature_covered_by(feature_name: str, stop) -> bool:
    """Addendum 4 predicate: does ``stop`` legitimately COVER the named natural
    feature ``feature_name``?

    When ``feature_name`` is a natural feature, the stop covers it only if the
    stop is NOT a commercial venue (hotel/resort/restaurant/shop). A stop that is
    commercial borrows the feature's name and does not cover it. When
    ``feature_name`` is NOT a natural feature, this predicate imposes no
    restriction (returns True) — the caller's normal name/geocode match decides.
    """
    if not natural_feature_kind(feature_name):
        return True  # not a natural feature → no same-kind restriction
    return stop_kind(stop) != "commercial"


# ─── 5. named places become stops for driving/nature (addendum 5) ─────────────

# Categories whose named anchors become STOPS (geocode in scope; if it exists, it
# is a stop) — the same rule LOCAL-790 applies to walking, extended here to
# driving and nature per addendum 5.
_PLACE_ANCHOR_CATEGORIES = {
    "walking", "driving", "nature", "neighbourhood", "neighborhood",
}


def is_place_anchor_tour_category(category: Optional[str]) -> bool:
    """True for tour categories where a user-named place becomes a STOP when it
    geocodes in scope (walking — LOCAL-790 — plus driving and nature — LOCAL-802
    addendum 5). Business/dining/museum are excluded: those have their own
    maps-first / corpus paths."""
    cat = fold(category or "")
    if not cat:
        return False
    return any(k in cat for k in _PLACE_ANCHOR_CATEGORIES)


# ─── 3. stop-count widening (geometry helpers) ────────────────────────────────

def widen_radius_km(radius_km: float, factor: float = 2.0,
                    cap_km: float = 25.0) -> float:
    """Widen a search radius by ``factor`` (default ×2), capped at ``cap_km``
    so widening within a city never balloons to a region."""
    try:
        r = float(radius_km)
    except (TypeError, ValueError):
        return 0.0
    if r <= 0:
        return 0.0
    return min(r * float(factor), float(cap_km))


def widen_bbox(bbox, factor: float = 2.0):
    """Grow a ``[south, north, west, east]`` bbox about its centre by ``factor``.

    Each half-extent (latitude and longitude) is multiplied by ``factor``, so a
    ×2 widening doubles the box's width and height around the same centre — the
    "radius ×2 within the city" widening for a bbox-scoped places search.
    Latitudes are clamped to [-90, 90]. Returns a new list; None/invalid → None.
    """
    try:
        s, n, w, e = (float(bbox[0]), float(bbox[1]),
                      float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError, IndexError):
        return None
    f = float(factor)
    clat = (s + n) / 2.0
    clng = (w + e) / 2.0
    half_lat = (n - s) / 2.0 * f
    half_lng = (e - w) / 2.0 * f
    new_s = max(-90.0, clat - half_lat)
    new_n = min(90.0, clat + half_lat)
    new_w = clng - half_lng
    new_e = clng + half_lng
    return [new_s, new_n, new_w, new_e]
