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
        '(GROUP_CONCAT(DISTINCT ?alias; separator="||") AS ?aliases) WHERE { '
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
        out.append({
            "qid": qid,
            "label_en": (b.get("en") or {}).get("value", "") or "",
            "label_local": (b.get("loc") or {}).get("value", "") or "",
            "aliases": aliases, "lat": lat_v, "lng": lng_v})
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
    label_words: set = set()
    for l in [cand.get("label_en", ""), cand.get("label_local", "")] + list(cand.get("aliases") or []):
        label_words |= _words(l)
    dist = _haversine_m(pin, (cand["lat"], cand["lng"]))
    if _distinctive_words(user_name, city) & label_words:
        return (0, dist)
    if _kind_words_in(user_name) & label_words:
        return (1, dist)
    return (2, dist)


def resolve_canonical(user_name: str, pin: Optional[Tuple[float, float]],
                      city: str = "", local_lang: str = "",
                      *, around_fn: Optional[Callable] = None,
                      places_fn: Optional[Callable] = None,
                      radius_m: float = DEFAULT_RADIUS_M) -> Optional[Dict]:
    """Resolve ``user_name`` + ``pin`` to the canonical venue at the pin. Returns
    ``None`` when nothing authoritative sits within ``radius_m``; the caller then
    keeps the user's name. See the module docstring for the contract."""
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
        best = min(in_range, key=lambda c: _score(c, (lat, lng), user_name, city))
        tier, dist = _score(best, (lat, lng), user_name, city)
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
        if d <= radius_m and rec.get("name") and d < best_d:
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
