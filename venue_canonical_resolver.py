#!/usr/bin/env python3
"""venue_canonical_resolver.py — LOCAL-882 task C.

Resolve a SHORT user stop name plus its pin to the CANONICAL venue AT THAT PIN,
deriving the canonical label at RUNTIME from authorities — never from a table of
place names in the code (D769). This is what the cloud quick path needs: a
listener types "City Hall" and a pin, and we must find the one real building on
that spot (the Hôtel de Ville / People's Committee Building), not a same-named
building elsewhere and not a different nearby venue.

CONTRACT
    resolve_canonical(user_name, pin, city="", local_lang="",
                      around_fn=None, places_fn=None, radius_m=300) -> dict | None

    Returns, on success::

        {"canonical_en":   "<English label of the item at the pin>",
         "canonical_local":"<local-language label, '' if none>",
         "qid":            "Q…" | "",
         "lat": float, "lng": float, "distance_m": float,
         "source": "wikidata_around" | "places",
         "match_tier": int,
         "aliases": ["<every label/alias found, deduped>"]}

    or ``None`` when nothing authoritative sits within ``radius_m`` of the pin.

WHY A PIN, NOT A NAME
    A bare name is ambiguous ("Opera House", "City Hall"); a PIN is not. We ask
    "what notable thing is HERE?" and then confirm it is the kind the user meant:

      1. Wikidata ``SERVICE wikibase:around`` lists every item within ``radius_m``
         (300 m) of the pin, with its English + local label and aliases. Among
         those we PREFER, in order:
           a. an item whose label/alias shares a DISTINCTIVE word with the user's
              name (its own name, not a kind word nor the city);
           b. an item whose label/alias shares a KIND word ("hall", "palace",
              "opera", "pier" …) — the right kind of place at the pin;
           c. the NEAREST item (something notable is exactly here).
         Ties break on distance.
      2. If Wikidata returns nothing in range, a Google/OSM Places lookup AT THE
         PIN (injectable) gives the establishment name there.

    The chosen English + local label become the stop's ``match_name`` and an
    alias for evidence and signature stories; the USER's typed name stays the
    spoken title. No place name is ever written in this file.

Every network edge is injected (``around_fn``, ``places_fn``) so the module is
unit-tested fully offline. The live defaults use the WDQS SPARQL endpoint and the
existing places_search provider, both metered/throttled by their own modules.
"""
from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

__all__ = ["resolve_canonical", "DEFAULT_RADIUS_M"]

DEFAULT_RADIUS_M = float(os.environ.get("CANONICAL_RESOLVE_RADIUS_M", "300"))
WDQS_ENDPOINT = os.environ.get("WDQS_ENDPOINT", "https://query.wikidata.org/sparql")

# Words that name a KIND of place, not a specific one. These are English /
# transliterated common nouns for venue kinds, so the list is NOT a table of
# place names (D769-safe). Mirrors the generic lists in
# landmark_wikipedia_evidence / itinerary_import.
_KIND_WORDS = frozenset({
    "the", "of", "and", "a", "an", "de", "du", "la", "le", "des",
    "city", "town", "hall", "palace", "house", "building", "museum",
    "cathedral", "basilica", "church", "opera", "theatre", "theater",
    "square", "street", "road", "avenue", "boulevard", "bridge", "tower",
    "gate", "park", "pier", "wharf", "quay", "station", "market", "monument",
    "memorial", "centre", "center", "office", "post", "central", "committee",
    "people", "peoples", "government", "national", "municipal", "provincial",
    "trade", "commercial", "old", "new", "bar", "pub", "club", "cafe", "coffee",
    "restaurant", "temple", "pagoda", "garden", "hotel", "apartments", "apartment",
    "walking", "boat", "ferry", "waterfront", "riverside", "book", "books",
})


def _fold(text: str) -> str:
    raw = str(text or "").lower().replace("đ", "d").replace("Đ", "d")
    nfkd = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _words(text: str) -> set:
    return {w for w in _fold(text).split() if len(w) >= 2}


def _distinctive_words(name: str, city: str = "") -> set:
    """Words of ``name`` that are NOT kind words and NOT the city's own words —
    the words that pick out THIS venue."""
    cw = _words(city)
    return {w for w in _words(name)
            if len(w) >= 3 and w not in _KIND_WORDS and w not in cw}


def _kind_words_in(name: str) -> set:
    return {w for w in _words(name) if w in _KIND_WORDS}


# [LOCAL-883] The tighter radius for the category-only-name path. A bare
# "Cathedral"/"City Hall"/"Opera House" shares no distinctive token, so it may
# only be matched to a candidate of the SAME KIND within this radius (plus a
# Wikidata P31 of the same kind, when P31 is available).
CATEGORY_RADIUS_M = float(os.environ.get("CANONICAL_CATEGORY_RADIUS_M", "150"))

# [LOCAL-883] Kind word -> the Wikidata P31 (instance-of) QIDs that realise that
# kind. Derived from the generic venue-kind vocabulary, NOT a table of place
# names (D769-safe): the keys are common nouns, the values are the class items
# those nouns denote. A category-only user name is confirmed against a
# candidate's P31 so "City Hall" can only bind an item that IS a city/town hall
# or seat of local government, never a palace or a hotel that merely sits nearby.
_KIND_P31 = {
    "cathedral": {"Q2977", "Q56242250"},                       # cathedral, co-cathedral
    "basilica": {"Q163687", "Q2977"},
    "church": {"Q16970", "Q2977"},
    "hall": {"Q543654", "Q16831714", "Q1021645"},              # city/town hall, govt building
    "palace": {"Q16560", "Q751876"},                            # palace, château
    "opera": {"Q153562", "Q24354"},                             # opera house, theatre
    "theatre": {"Q24354", "Q153562"},
    "theater": {"Q24354", "Q153562"},
    "museum": {"Q33506"},
    "pier": {"Q863454", "Q16831714", "Q2080521"},              # pier, wharf, harbour
    "wharf": {"Q863454", "Q2080521"},
    "quay": {"Q863454", "Q2080521"},
    "bridge": {"Q12280"},
    "tower": {"Q12518", "Q41176"},
    "gate": {"Q82117", "Q52052"},
    "park": {"Q22698"},
    "square": {"Q174782"},                                      # town square / plaza
    "market": {"Q330284", "Q132510"},
    "station": {"Q55488", "Q928830"},
    "temple": {"Q44539", "Q61908480"},
    "pagoda": {"Q199451", "Q44539"},
    "post": {"Q35054", "Q829277"},                              # post office
    "office": {"Q35054", "Q4830453"},
    "hotel": {"Q27686"},
    "bar": {"Q187456", "Q30022"},                               # bar, café/pub
    "pub": {"Q212198", "Q187456"},
    "restaurant": {"Q11707"},
    "cafe": {"Q30022"},
    "coffee": {"Q30022"},
}


def _p31_for_kinds(kinds: set) -> set:
    out = set()
    for k in kinds:
        out |= _KIND_P31.get(k, set())
    return out


def _is_category_only(user_name: str, city: str = "") -> bool:
    """True when the user's name carries NO distinctive token — it is a pure
    category ("Cathedral", "Post Office", "City Hall", "Opera House"). Such a name
    may only be matched by kind + proximity (+ P31), never by nearest-notable."""
    return not _distinctive_words(user_name, city)


def _label_words(cand: Dict) -> set:
    words: set = set()
    for l in ([cand.get("label_en", ""), cand.get("label_local", "")]
              + list(cand.get("aliases") or [])
              + [cand.get("name", "")]):
        words |= _words(l)
    return words


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


# ── live network defaults (injectable) ───────────────────────────────────────

def _build_around_query(lat: float, lng: float, radius_km: float,
                        local_lang: str) -> str:
    """The WDQS ``wikibase:around`` query string for the point query."""
    loc_label = ""
    alias_langs = '"en"'
    if local_lang and local_lang != "en":
        loc_label = (f'OPTIONAL {{ ?item rdfs:label ?locLabel. '
                     f'FILTER(LANG(?locLabel)="{local_lang}") }} ')
        alias_langs = f'"en","{local_lang}"'
    return (
        "SELECT ?item ?lat ?lng "
        "(SAMPLE(?enLabel) AS ?en) (SAMPLE(?locLabel) AS ?loc) "
        '(GROUP_CONCAT(DISTINCT ?alias; separator="||") AS ?aliases) '
        # [LOCAL-883] P31 (instance-of) QIDs for the category-only name path: a
        # bare "Cathedral"/"City Hall"/"Opera House" may match a candidate only
        # when that candidate's P31 is the same KIND as the user's category.
        '(GROUP_CONCAT(DISTINCT ?p31; separator="||") AS ?p31s) WHERE { '
        "SERVICE wikibase:around { "
        "?item wdt:P625 ?coord. "
        f'bd:serviceParam wikibase:center "Point({lng} {lat})"^^geo:wktLiteral. '
        f'bd:serviceParam wikibase:radius "{radius_km}". '
        "bd:serviceParam wikibase:distance ?dist. } "
        "?item p:P625/psv:P625 ?coordNode. "
        "?coordNode wikibase:geoLatitude ?lat. ?coordNode wikibase:geoLongitude ?lng. "
        'OPTIONAL { ?item rdfs:label ?enLabel. FILTER(LANG(?enLabel)="en") } '
        + loc_label +
        "OPTIONAL { ?item skos:altLabel ?alias. "
        f"FILTER(LANG(?alias) IN ({alias_langs})) }} "
        "OPTIONAL { ?item wdt:P31 ?p31. } "
        "} GROUP BY ?item ?lat ?lng")


def _default_around(lat: float, lng: float, radius_m: float,
                    local_lang: str) -> List[Dict]:
    """Every Wikidata item within ``radius_m`` of (lat,lng), via WDQS. Returns
    [{qid, label_en, label_local, aliases[], lat, lng}]. Fails soft (``[]``)."""
    radius_km = max(0.01, radius_m / 1000.0)
    query = _build_around_query(lat, lng, radius_km, local_lang)
    try:
        from venue_resolver import _request_with_backoff, _USER_AGENT
        r = _request_with_backoff(
            WDQS_ENDPOINT, params={"query": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT,
                     "Accept": "application/sparql-results+json"},
            timeout=20, host_for_cold="https://query.wikidata.org",
            label="LOCAL-882 around")
        if r is None or getattr(r, "status_code", 0) != 200:
            return []
        rows = (r.json().get("results") or {}).get("bindings") or []
    except Exception:
        return []
    out = []
    for b in rows:
        try:
            uri = (b.get("item") or {}).get("value", "")
            qid = uri.rsplit("/", 1)[-1] if uri else ""
            lat_v = float((b.get("lat") or {}).get("value"))
            lng_v = float((b.get("lng") or {}).get("value"))
        except (TypeError, ValueError):
            continue
        aliases = [a for a in ((b.get("aliases") or {}).get("value", "") or "").split("||") if a]
        p31s = [p.rsplit("/", 1)[-1] for p in
                ((b.get("p31s") or {}).get("value", "") or "").split("||") if p]
        out.append({
            "qid": qid,
            "label_en": (b.get("en") or {}).get("value", "") or "",
            "label_local": (b.get("loc") or {}).get("value", "") or "",
            "aliases": aliases, "lat": lat_v, "lng": lng_v, "p31": p31s})
    return out


def _default_places(lat: float, lng: float, name_hint: str) -> List[Dict]:
    """Establishment(s) at the pin from the existing Places provider (metered).
    Returns [{name, lat, lng}]. Fails soft."""
    try:
        import places_search as ps
        if not ps.serper_places_enabled():
            return []
        ll = f"@{lat},{lng},18z"
        recs = ps._serper_places_call(name_hint or "", ll, location=None) or []
    except Exception:
        return []
    out = []
    for rec in recs:
        try:
            plat = float(rec.get("lat", rec.get("latitude")))
            plng = float(rec.get("lon", rec.get("lng", rec.get("longitude"))))
        except (TypeError, ValueError):
            continue
        nm = str(rec.get("title") or rec.get("name") or "").strip()
        if nm:
            out.append({"name": nm, "lat": plat, "lng": plng})
    return out


# ── the resolver ─────────────────────────────────────────────────────────────

def _score(cand: Dict, pin: Tuple[float, float], user_name: str,
           city: str) -> Tuple[int, float]:
    """Rank key for a candidate: (tier, distance_m). Lower wins. Tier 0 = shares a
    distinctive word; 1 = shares a kind word; 2 = neither (nearest-notable)."""
    label_words = _label_words(cand)
    dist = _haversine_m(pin, (cand["lat"], cand["lng"]))
    if _distinctive_words(user_name, city) & label_words:
        return (0, dist)
    if _kind_words_in(user_name) & label_words:
        return (1, dist)
    return (2, dist)


def _is_acceptable(cand: Dict, pin: Tuple[float, float], user_name: str,
                   city: str, dist: float, *, is_places: bool = False) -> bool:
    """[LOCAL-883] A canonical pick is accepted ONLY when it is genuinely THIS
    venue, not merely the nearest notable thing at the pin. The rule:

      * it shares a DISTINCTIVE token with the user's name (tier 0) — always
        accepted; OR
      * the user's name is a pure CATEGORY ("Cathedral", "City Hall", "Opera
        House") and the candidate is the SAME KIND within 150 m: it shares the
        user's kind word AND (when the candidate carries P31 data) a P31 of that
        kind. When no P31 is available (a Places pick, or a Wikidata item with no
        instance-of), the kind word + 150 m is required on its own.

    Everything else — a nearest-notable item that shares neither a distinctive
    token nor the user's kind (tier 2), or a kind match that is beyond 150 m, or a
    category name matched to the wrong kind by P31 — is REJECTED, so the caller
    keeps the user's own name (Book Street never becomes "22 Gia Long Street";
    Thi Bar never becomes "DDA Hotel 183 De Tham")."""
    label_words = _label_words(cand)
    # Tier 0: a shared distinctive token — the candidate is named for this venue.
    if _distinctive_words(user_name, city) & label_words:
        return True
    # Category-only name: kind + 150 m (+ P31 when present). The shared kind must
    # be a recognised VENUE kind (one with a P31 class), so two different streets
    # are never equated on the bare word "street" (Book Street ≠ 22 Gia Long
    # Street) and a generic thoroughfare/qualifier word cannot carry a match.
    user_kinds = _kind_words_in(user_name)
    shared_kinds = user_kinds & label_words
    venue_kinds = {k for k in shared_kinds if k in _KIND_P31}
    if (_is_category_only(user_name, city) and venue_kinds
            and dist <= CATEGORY_RADIUS_M):
        want_p31 = _p31_for_kinds(venue_kinds)
        cand_p31 = set(cand.get("p31") or [])
        if want_p31 and cand_p31:
            return bool(want_p31 & cand_p31)   # P31 present → must be same kind
        return True                            # no P31 to check → kind + 150 m
    return False


def _user_link_names(cand: Dict, user_link: str) -> bool:
    """[LOCAL-883] True when the user's OWN link/pin text names this candidate —
    a distinctive token of the candidate's label appears in the link the listener
    pasted. Then the canonical is the venue the user themselves pointed at."""
    if not user_link:
        return False
    link_words = _words(user_link)
    cand_dist = _distinctive_words(
        " ".join([cand.get("label_en", ""), cand.get("label_local", ""),
                  cand.get("name", "")] + list(cand.get("aliases") or [])), "")
    return bool(cand_dist & link_words)


def resolve_canonical(user_name: str, pin: Optional[Tuple[float, float]],
                      city: str = "", local_lang: str = "",
                      *, around_fn: Optional[Callable] = None,
                      places_fn: Optional[Callable] = None,
                      radius_m: float = DEFAULT_RADIUS_M,
                      user_link: str = "") -> Optional[Dict]:
    """Resolve ``user_name`` + ``pin`` to the canonical venue at the pin. Returns
    ``None`` when nothing authoritative that is genuinely THIS venue sits within
    range; the caller then keeps the user's name. See the module docstring.

    [LOCAL-883] A pick is accepted only when it shares a DISTINCTIVE token with
    the user's name, OR the user's name is a pure category matched by kind + 150 m
    (+ Wikidata P31 of the same kind), OR the user's own ``user_link`` names it.
    A nearest-notable pick that satisfies none of these is rejected (None)."""
    if not pin:
        return None
    try:
        lat, lng = float(pin[0]), float(pin[1])
    except (TypeError, ValueError, IndexError):
        return None

    around = around_fn or _default_around
    try:
        cands = around(lat, lng, radius_m, local_lang) or []
    except Exception:
        cands = []
    in_range = []
    for c in cands:
        try:
            d = _haversine_m((lat, lng), (float(c["lat"]), float(c["lng"])))
        except (TypeError, ValueError, KeyError):
            continue
        if d <= radius_m and (c.get("label_en") or c.get("label_local") or c.get("aliases")):
            in_range.append(c)
    if in_range:
        # Rank by (tier, distance), then accept the best ONLY if it genuinely
        # names this venue (distinctive token / category+kind+150m+P31 / user link).
        best = min(in_range, key=lambda c: _score(c, (lat, lng), user_name, city))
        tier, dist = _score(best, (lat, lng), user_name, city)
        accept = (_is_acceptable(best, (lat, lng), user_name, city, dist)
                  or _user_link_names(best, user_link))
        if accept:
            aliases = _dedupe([best.get("label_en", ""), best.get("label_local", "")]
                              + list(best.get("aliases") or []))
            return {
                "canonical_en": best.get("label_en", "") or best.get("label_local", ""),
                "canonical_local": best.get("label_local", ""),
                "qid": best.get("qid", ""),
                "lat": round(best["lat"], 6), "lng": round(best["lng"], 6),
                "distance_m": round(dist, 1),
                "source": "wikidata_around", "match_tier": tier,
                "aliases": aliases}
        # best candidate is not THIS venue → fall through to Places (then None).

    places = places_fn or _default_places
    try:
        recs = places(lat, lng, user_name) or []
    except Exception:
        recs = []
    best_p, best_d = None, radius_m + 1
    for rec in recs:
        try:
            d = _haversine_m((lat, lng), (float(rec["lat"]), float(rec["lng"])))
        except (TypeError, ValueError, KeyError):
            continue
        # [LOCAL-883] A Places pick must ALSO be this venue: it shares a
        # distinctive token, or (category name) its kind within 150 m, or the
        # user's own link names it. A nearest establishment that shares nothing
        # (Café Apartments 42 → "The Reverie Saigon") is rejected.
        if not rec.get("name") or d > radius_m or d >= best_d:
            continue
        if (_is_acceptable(rec, (lat, lng), user_name, city, d, is_places=True)
                or _user_link_names(rec, user_link)):
            best_p, best_d = rec, d
    if best_p:
        return {
            "canonical_en": best_p["name"], "canonical_local": "",
            "qid": "", "lat": round(best_p["lat"], 6), "lng": round(best_p["lng"], 6),
            "distance_m": round(best_d, 1), "source": "places", "match_tier": 3,
            "aliases": [best_p["name"]]}
    return None


def _dedupe(items) -> List[str]:
    seen, out = set(), []
    for a in items:
        if not a:
            continue
        k = _fold(a)
        if k and k not in seen:
            seen.add(k)
            out.append(a)
    return out
