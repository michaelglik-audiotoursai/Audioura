#!/usr/bin/env python3
"""LOCAL-882 task C — venue_canonical_resolver: resolve a SHORT user name + pin to
the canonical venue AT THE PIN, from Wikidata-around (then Places), with the
canonical label derived at RUNTIME (no place-name table in code). Fully offline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import venue_canonical_resolver as vcr  # noqa: E402

CITY = "Ho Chi Minh City"
CITY_HALL_PIN = (10.776470, 106.700970)


def _around_city_hall(lat, lng, radius_m, local_lang):
    # Two Wikidata items near the City Hall pin: the People's Committee Building
    # (right at the pin) and the Gia Long Palace (~600 m away → out of 300 m).
    return [
        {"qid": "Q1", "label_en": "Ho Chi Minh City Hall",
         "label_local": "Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh",
         "aliases": ["Hôtel de Ville de Saïgon", "People's Committee Building"],
         "lat": 10.776480, "lng": 106.700975},
        {"qid": "Q2", "label_en": "Gia Long Palace",
         "label_local": "Dinh Gia Long", "aliases": [],
         "lat": 10.7770, "lng": 106.6955},   # ~600 m west, out of range
    ]


def test_city_hall_resolves_to_hotel_de_ville_not_gia_long():
    got = vcr.resolve_canonical("City Hall", CITY_HALL_PIN, city=CITY,
                                local_lang="vi", around_fn=_around_city_hall)
    assert got is not None
    assert got["canonical_en"] == "Ho Chi Minh City Hall", got
    assert "gia long" not in got["canonical_en"].lower()
    assert got["source"] == "wikidata_around"
    assert "Ủy ban" in got["canonical_local"]
    low = " ".join(a.lower() for a in got["aliases"])
    assert "hotel de ville" in vcr._fold(low)


def test_distinctive_word_match_beats_nearer_generic():
    def around(lat, lng, r, ll):
        return [
            {"qid": "QA", "label_en": "Ferry Terminal", "label_local": "",
             "aliases": [], "lat": lat, "lng": lng},
            {"qid": "QB", "label_en": "Bạch Đằng Wharf", "label_local": "Bến Bạch Đằng",
             "aliases": [], "lat": lat + 0.0005, "lng": lng},
        ]
    got = vcr.resolve_canonical("Bạch Đằng Pier", (10.77524, 106.707002),
                                city=CITY, around_fn=around)
    assert got["qid"] == "QB", got
    assert got["match_tier"] == 0


def test_kind_word_match_when_no_distinctive():
    def around(lat, lng, r, ll):
        return [
            {"qid": "QX", "label_en": "Caravelle Hotel", "label_local": "",
             "aliases": [], "lat": lat, "lng": lng},
            {"qid": "QY", "label_en": "Municipal Theatre", "label_local": "Nhà hát Thành phố",
             "aliases": ["Saigon Opera House"], "lat": lat + 0.0008, "lng": lng},
        ]
    got = vcr.resolve_canonical("Opera House", (10.77639, 106.70278),
                                city=CITY, around_fn=around)
    assert got["qid"] == "QY", got
    assert got["match_tier"] in (0, 1)


def test_nothing_in_range_falls_back_to_places():
    def around(lat, lng, r, ll):
        return [{"qid": "QF", "label_en": "Far Place", "label_local": "",
                 "aliases": [], "lat": lat + 0.02, "lng": lng}]
    def places(lat, lng, hint):
        return [{"name": "The Cafe Apartment", "lat": lat, "lng": lng}]
    got = vcr.resolve_canonical("Café Apartments 42", (10.774089, 106.704056),
                                city=CITY, around_fn=around, places_fn=places)
    assert got is not None and got["source"] == "places"
    assert got["canonical_en"] == "The Cafe Apartment"


def test_none_when_nothing_anywhere():
    got = vcr.resolve_canonical("Nowhere", (10.0, 106.0),
                                around_fn=lambda *a: [], places_fn=lambda *a: [])
    assert got is None


def test_no_pin_returns_none():
    assert vcr.resolve_canonical("City Hall", None) is None


def test_query_builder_is_wellformed():
    q = vcr._build_around_query(10.7, 106.7, 0.3, "vi")
    assert "wikibase:around" in q and 'Point(106.7 10.7)' in q
    assert 'wikibase:radius "0.3"' in q
    assert 'FILTER(LANG(?locLabel)="vi")' in q


if __name__ == "__main__":
    _p = _f = 0
    for _n, _fn in sorted(globals().items()):
        if _n.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_n}")
                _p += 1
            except Exception as e:
                import traceback
                print(f"FAIL {_n}: {e}")
                traceback.print_exc()
                _f += 1
    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)
