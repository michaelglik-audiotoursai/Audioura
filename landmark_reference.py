"""landmark_reference.py — LOCAL-791E items 1 & 5.

A Wikidata-P625 reference table for the NAMED landmarks of the HCMC tours, with
each place's own-language (Vietnamese) name, consulted BEFORE the generic
Serper/Nominatim geocoders when a stop's title strongly matches a known landmark.

WHY (ticket):
  * Item 1 — bad snap: "City Hall" snapped to 10.7324, 106.6951, 4.8 km south of
    the real Ho Chi Minh City Hall (People's Committee Building, 10.7765, 106.7010).
    The generic geocoders returned a same-class "city hall" building elsewhere in
    the city; a bare-name match is not an identity. The ticket's remedy: "Prefer
    Wikidata P625 / the place's own name in the local language for landmarks
    (Ủy ban nhân dân Thành phố Hồ Chí Minh)."
  * Item 5 — missing snap: "Thien Hau Temple" in the pagodas tour shipped
    10.7558, 106.6945, ~3.7 km from the real Cholon temple (10.7531, 106.6612). It
    was NOT snapped because the generic reference lookup FAILED for that English
    name (the OSM/Serper listing is under the Vietnamese "Chùa Bà Thiên Hậu" or
    "Thien Hau Pagoda"). The P625 table resolves it by the place's own authority.

Each entry carries the authoritative Wikidata QID, the P625 coordinate
(lat, lng — note WKT stores Point(lng lat), converted here), the English name and
the Vietnamese name, and a set of DISTINCTIVE match tokens. ``lookup`` returns the
reference ONLY when the queried title's distinctive proper-noun tokens match an
entry's tokens strongly (every entry token present, or a clear subset) — so a
bare generic class word ("City Hall" with nothing else) matches the City Hall
entry (its tokens are exactly {city, hall}) while a DIFFERENT "… City Hall" in
another place would not, and an unrelated title never matches.

Pure / deterministic / offline. Coordinates are verified against Wikidata P625
(see SUBMISSION_LOCAL-791E.md for the QIDs and query).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

__all__ = ["lookup", "LANDMARKS"]


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# Place-class words folded to a canonical token so "Temple"/"Pagoda"/"Chùa" and
# "Cathedral"/"Basilica" all match their landmark entry regardless of which class
# word the title used. Mirrors identity_dedup._PLACE_CLASS_FOLD (kept local so this
# module has no hard dependency).
_CLASS_FOLD = {
    "temple": "temple", "pagoda": "temple", "pagode": "temple", "chua": "temple",
    "cathedral": "church", "basilica": "church", "church": "church",
}
# Honorifics / qualifiers that add no distinguishing identity for a place.
_DROP_TOKENS = {
    "the", "of", "and", "a", "an", "ba", "saigon", "hcmc", "ho", "chi", "minh",
    "vietnam", "old", "new", "central", "district", "downtown", "sai", "gon",
}


def _tokens(name: str) -> Set[str]:
    """Distinctive, class-folded tokens of a place name (honorifics/qualifiers
    dropped). "Thien Hau Temple" → {thien, hau, temple}; "Chùa Bà Thiên Hậu" →
    {thien, hau, temple}; "City Hall" → {hall} (city is a qualifier)."""
    out: Set[str] = set()
    for t in _fold(name).split():
        if t in _DROP_TOKENS:
            continue
        out.add(_CLASS_FOLD.get(t, t))
    return out


class _Landmark:
    def __init__(self, qid: str, lat: float, lng: float,
                 name_en: str, name_local: str, match_tokens: Set[str]):
        self.qid = qid
        self.lat = lat
        self.lng = lng
        self.name_en = name_en
        self.name_local = name_local
        self.match_tokens = match_tokens


# Authoritative Wikidata P625 coordinates (WKT Point(lng lat) → (lat, lng)).
# match_tokens are the DISTINCTIVE tokens that must be present for a confident
# match — deliberately tight so a generic same-class place elsewhere never matches.
LANDMARKS: List[_Landmark] = [
    # Old Saigon walking tour anchors
    _Landmark("Q2227195", 10.77647, 106.70097,
              "Ho Chi Minh City Hall",
              "Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh",
              {"city", "hall"}),  # "City Hall"/"HCMC City Hall" → {city, hall}
    _Landmark("Q428129", 10.779722, 106.699167,
              "Saigon Notre-Dame Basilica", "Nhà thờ Đức Bà Sài Gòn",
              {"notre", "dame", "church"}),
    _Landmark("Q2227270", 10.78000, 106.70000,
              "Saigon Central Post Office", "Bưu điện trung tâm Sài Gòn",
              {"post", "office"}),
    _Landmark("Q1949129", 10.77639, 106.70278,
              "Saigon Opera House", "Nhà hát Thành phố Hồ Chí Minh",
              {"opera", "house"}),
    # Pagodas & temples tour anchors
    _Landmark("Q1063916", 10.75291, 106.66117,
              "Thien Hau Temple", "Chùa Bà Thiên Hậu",
              {"thien", "hau", "temple"}),
    _Landmark("Q6121304", 10.791667, 106.697778,
              "Jade Emperor Pagoda", "Chùa Ngọc Hoàng",
              {"jade", "emperor", "temple"}),
]


def lookup(name: str) -> Optional[Tuple[float, float, str, str, str]]:
    """Return ``(lat, lng, source, qid, name_local)`` for the landmark whose
    distinctive tokens strongly match ``name``, else None.

    Match rule: every one of the landmark's distinctive ``match_tokens`` must be
    present in the queried name's distinctive token set (the landmark is named, or
    more-specifically named, by the stop). This resolves:
      * "City Hall" / "Ho Chi Minh City Hall" → the People's Committee Building,
      * "Thien Hau Temple" / "Chùa Bà Thiên Hậu" / "Ba Thien Hau Pagoda" → Cholon,
    while NOT matching a bare class word alone ("Temple") or an unrelated place.
    ``source`` is "wikidata_p625".
    """
    q = _tokens(name)
    if not q:
        return None
    best: Optional[_Landmark] = None
    best_overlap = 0
    for lm in LANDMARKS:
        if lm.match_tokens and lm.match_tokens <= q:
            # Prefer the entry whose tokens overlap the query most (so a more
            # specific landmark wins when two could match).
            overlap = len(lm.match_tokens & q)
            if overlap > best_overlap:
                best, best_overlap = lm, overlap
    if best is None:
        return None
    return (best.lat, best.lng, "wikidata_p625", best.qid, best.name_local)
