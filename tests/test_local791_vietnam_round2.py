"""test_local791_vietnam_round2.py — LOCAL-791.

One unit test per defect from the Vietnam round-2 ticket (tours 461–468 on the
Subscribed Preview), each using the EXACT strings the ticket names. Pure, offline
(every network seam is stubbed/injected); run with:

    python3 -m pytest tests/test_local791_vietnam_round2.py -q

Defects:
  1  dining parser drops the city; "street food" read as a cuisine
  2  business/activity providers ("kitesurfing schools") route to the places path
  3  stop coordinates inherited from a neighbour instead of geocoded
  4  junk stop titles (generic words, headings, news headlines)
  5  cross-language duplicates ("Chợ Bình Tây" == "Binh Tay Market")
  6  foreign-script marketing tag lists in titles
  7  safety/scam note placed before the place is introduced
  8  a requested named place ("White Sand Dunes") missed by named_places
  9  wrong-museum / long-coastal-strip bbox (Mui Ne addendum)
 10  Google category suffix (": <list>") on a places title
 11  "Thien Hau Temple" == "Ba Thien Hau Pagoda" survived dedup
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────── Defect 1 ───────────────────────────────────────
class TestDefect1DiningKeepsCity:
    def test_district_city_not_dropped(self):
        from area_resolver import _parse_location
        nb, city = _parse_location(
            "Vietnamese restaurants and street food, District 1, Ho Chi Minh City")
        # The old bug set city="District 1" and dropped the parent city.
        assert nb == "District 1"
        assert city == "Ho Chi Minh City"

    def test_street_food_is_not_a_cuisine(self):
        from stop_existence_gate import (_extract_cuisine_qualifier,
                                         _cuisine_from_request)
        assert _extract_cuisine_qualifier(
            "Vietnamese restaurants and street food") == "vietnamese"
        assert _cuisine_from_request(
            "Vietnamese restaurants and street food, District 1, "
            "Ho Chi Minh City") == "vietnamese"
        # A bare "restaurants" still has no cuisine constraint.
        assert _extract_cuisine_qualifier("restaurants") == ""


# ─────────────────────────── Defect 2 ───────────────────────────────────────
class TestDefect2BusinessActivityRouting:
    def test_kitesurfing_schools_classifies_as_business(self):
        from stop_existence_gate import classify_business_vs_landmark
        assert classify_business_vs_landmark("Kitesurfing schools") == "business"
        assert classify_business_vs_landmark("dive shops") == "business"
        assert classify_business_vs_landmark("surfboard rentals") == "business"

    def test_empty_tour_type_routes_to_places_path(self):
        import generate_tour_text as gtt
        from stop_existence_gate import is_place_type_tour
        # Empty tour_type: the request subject is a business/activity provider.
        cat = gtt._classify_tour_category("Kitesurfing schools in Mui Ne, Vietnam", "")
        assert cat == "restaurant"  # the maps-first / places template
        assert is_place_type_tour(cat, "", None,
                                  "Kitesurfing schools in Mui Ne, Vietnam") is True

    def test_walking_and_museum_unaffected(self):
        import generate_tour_text as gtt
        assert gtt._classify_tour_category(
            "Old Saigon walking tour, District 1, Ho Chi Minh City", "") == "walking"
        assert gtt._classify_tour_category("art center in Cambridge", "") == "museum"


# ─────────────────────────── Defect 3 ───────────────────────────────────────
class TestDefect3InheritedCoordinates:
    def test_inherited_pin_regeocoded(self):
        import geocode_stops as gs
        # Stop 2 inherited stop 1's coordinate (within 50 m) but its OWN geocode
        # is > 200 m away — it must take the geocode (the ticket's unit-test rule).
        poi_list = [
            {"name": "Saigon Opera House", "address": "7 Lam Son Square, District 1",
             "coordinates": "10.776900, 106.703000"},
            {"name": "War Remnants Museum", "address": "28 Vo Van Tan, District 3",
             "coordinates": "10.777200, 106.702800"},  # within 50 m of stop 1
        ]
        truth = {
            "saigon opera house": (10.7769, 106.7030),
            "war remnants museum": (10.7795, 106.6921),  # the REAL museum, ~1.2 km
        }

        def fake_geocode(q):
            ql = q.lower()
            for k, v in truth.items():
                if k.split(",")[0] in ql:
                    return v
            return None

        rec = gs.repair_inherited_coordinates(
            poi_list, "Ho Chi Minh City, Vietnam",
            tour_anchor=(10.78, 106.70), geocoder=fake_geocode)
        assert rec["action"] == "corrected"
        assert poi_list[1]["coordinates"].startswith("10.7795")

    def test_genuinely_close_pair_left_alone(self):
        import geocode_stops as gs
        poi_list = [
            {"name": "Cafe A", "address": "1 X St", "coordinates": "10.776900, 106.703000"},
            {"name": "Cafe B", "address": "2 X St", "coordinates": "10.777000, 106.703100"},
        ]

        def fake_geocode(q):
            if "cafe a" in q.lower():
                return (10.7769, 106.7030)
            if "cafe b" in q.lower():
                return (10.7770, 106.7031)
            return None

        rec = gs.repair_inherited_coordinates(
            poi_list, "X City", tour_anchor=(10.78, 106.70), geocoder=fake_geocode)
        assert rec["action"] == "none"
        assert poi_list[1]["coordinates"] == "10.777000, 106.703100"


# ─────────────────────────── Defect 4 & 10 ──────────────────────────────────
class TestDefect4JunkTitles:
    @pytest.mark.parametrize("junk", [
        "Balcony",                     # 461 café terrace, not a place
        "Interesting",                 # 463
        "View",                        # a bare generic feature word
        "Khai mạc Hội thảo Quốc tế về Bảo tồn Di sản …",   # 463 news headline
    ])
    def test_junk_rejected(self, junk):
        from junk_title_guard import is_junk_page_title
        assert is_junk_page_title(junk) is True

    @pytest.mark.parametrize("real", [
        "Ben Thanh Market", "War Remnants Museum", "Jade Emperor Pagoda",
        "Balcony Bar", "White Sand Dunes", "Red Canyon", "Fairy Stream",
        "Notre-Dame Cathedral Basilica of Saigon", "Independence Palace",
    ])
    def test_real_names_kept(self, real):
        from junk_title_guard import is_junk_page_title
        assert is_junk_page_title(real) is False


class TestDefect10GoogleCategorySuffix:
    def test_strip_category_tail(self):
        from places_search import clean_place_title
        # West Roxbury Mac e2e: "Stardust: Inspired Mediterranean , Persian".
        assert clean_place_title(
            "Stardust: Inspired Mediterranean , Persian") == "Stardust"

    def test_real_colon_title_not_truncated(self):
        from places_search import clean_place_title
        # A real colon-titled work has no comma tail and is NOT cut.
        assert clean_place_title("Blue: A Study of Light") == "Blue: A Study of Light"


# ─────────────────────────── Defect 5 & 11 ──────────────────────────────────
class TestDefect5And11Dedup:
    def test_cho_binh_tay_equals_binh_tay_market(self):
        from identity_dedup import dedupe_by_location_or_qid
        pool = [{"name": "Chợ Bình Tây"}, {"name": "Binh Tay Market"}]
        kept, dropped = dedupe_by_location_or_qid(pool)
        assert len(kept) == 1
        assert dropped == [("Binh Tay Market", "Chợ Bình Tây")]

    def test_thien_hau_temple_equals_ba_thien_hau_pagoda(self):
        from identity_dedup import dedupe_by_location_or_qid
        # Chùa Bà Thiên Hậu, Cholon — the two listings geocode ~150 m apart and
        # share the distinctive core "thien hau".
        pool = [
            {"name": "Thien Hau Temple", "coordinates": "10.753000, 106.661000"},
            {"name": "Ba Thien Hau Pagoda", "coordinates": "10.754000, 106.661200"},
        ]
        kept, dropped = dedupe_by_location_or_qid(pool)
        assert len(kept) == 1
        assert dropped == [("Ba Thien Hau Pagoda", "Thien Hau Temple")]

    def test_two_different_pagodas_not_merged(self):
        from identity_dedup import dedupe_by_location_or_qid
        pool = [
            {"name": "Thien Hau Temple", "coordinates": "10.753000, 106.661000"},
            {"name": "Jade Emperor Pagoda", "coordinates": "10.790000, 106.695000"},
        ]
        kept, dropped = dedupe_by_location_or_qid(pool)
        assert len(kept) == 2
        assert dropped == []


# ─────────────────────────── Defect 6 ───────────────────────────────────────
class TestDefect6ForeignScriptTagList:
    def test_strip_korean_tag_list(self):
        from places_search import clean_place_title
        got = clean_place_title(
            "An Spa - Healing & Relax (Massage Mũi Né - 샴푸와 컨디셔너, 마사지)")
        assert got == "An Spa - Healing & Relax"

    def test_latin_gloss_parenthetical_kept(self):
        from places_search import clean_place_title
        # A same-script (Latin/Vietnamese) gloss is NOT stripped.
        assert clean_place_title(
            "Ngoc Hoang Pagoda (Chua Ngoc Hoang)") == "Ngoc Hoang Pagoda (Chua Ngoc Hoang)"


# ─────────────────────────── Defect 7 ───────────────────────────────────────
class TestDefect7SafetyNoteOrder:
    def test_scam_opener_moved_to_end_as_tip(self):
        from safety_note_order import reframe_opening_safety_note
        body = ("Their smiles are welcoming, but their true intent becomes clear "
                "when they later demand a 'guide fee'. Red Canyon is a striking "
                "ravine of ochre and crimson sandstone carved by erosion. The short "
                "walk through it is one of Mui Ne's natural highlights.")
        new, moved = reframe_opening_safety_note(body)
        assert moved is True
        # The place is introduced first; the scam note is now a trailing tip.
        assert new.startswith("Red Canyon is a striking ravine")
        assert "A practical tip: their smiles are welcoming" in new

    def test_descriptive_opener_untouched(self):
        from safety_note_order import reframe_opening_safety_note
        body = ("Red Canyon is a striking ravine. The walk is short and scenic.")
        new, moved = reframe_opening_safety_note(body)
        assert moved is False
        assert new == body

    def test_one_sentence_stop_untouched(self):
        from safety_note_order import reframe_opening_safety_note
        new, moved = reframe_opening_safety_note(
            "Watch out for aggressive vendors here.")
        assert moved is False


# ─────────────────────────── Defect 8 ───────────────────────────────────────
class TestDefect8NamedPlaceExtracted:
    @pytest.mark.parametrize("request_str", [
        "Mui Ne, Vietnam including Red Canyon, White Sand Dunes and Fairy Stream",
        "Mui Ne, Vietnam visiting the White Sand Dunes and Red Canyon",
        "Mui Ne tour stopping at White Sand Dunes, Fairy Stream",
        "Mui Ne, Vietnam such as White Sand Dunes and Red Canyon",
    ])
    def test_white_sand_dunes_extracted(self, request_str):
        from area_resolver import extract_named_places_from_clause
        names = extract_named_places_from_clause(request_str)
        assert "White Sand Dunes" in names

    def test_area_loses_the_named_clause(self):
        from area_resolver import _parse_location
        nb, city = _parse_location(
            "Mui Ne, Vietnam including Red Canyon, White Sand Dunes and Fairy Stream")
        assert nb == "Mui Ne"
        assert city == "Vietnam"

    def test_danvers_regression_still_works(self):
        from area_resolver import extract_named_places_from_clause
        names = extract_named_places_from_clause(
            "Walking tour in Danvers, MA including Witchcraft Victims Memorial")
        assert names == ["Witchcraft Victims Memorial"]


# ─────────────────────────── Defect 9 ───────────────────────────────────────
class TestDefect9CoastalStripBbox:
    def _resolver_with_stubs(self, monkeypatch, bbox_for):
        import area_resolver as ar
        monkeypatch.setattr(ar, "_resolve_city",
                            lambda c: ("Q123", (10.982, 108.2512)))
        monkeypatch.setattr(ar, "_is_city_type", lambda q: True)
        monkeypatch.setattr(ar, "_is_region_type", lambda q: False)
        monkeypatch.setattr(ar, "_detect_language", lambda q: "vi")
        monkeypatch.setattr(ar, "_get_country", lambda q: "Q881")
        monkeypatch.setattr(ar, "_nominatim_bbox", bbox_for)
        return ar

    def test_long_coastal_strip_adopts_bbox(self, monkeypatch):
        # Mui Ne / Hàm Tiến: a ~5 km coastal strip, not a 2 km circle.
        ar = self._resolver_with_stubs(
            monkeypatch,
            lambda q: [10.93, 10.96, 108.19, 108.30] if "mui ne" in q.lower() else None)
        res = ar.resolve_area("Mui Ne, Vietnam")
        assert res is not None
        assert res.union_bbox == [10.93, 10.96, 108.19, 108.30]
        assert res.bounding_radius_km > 3.0   # widened well past the 2 km circle
        assert abs(res.center_lat - 10.945) < 0.01

    def test_compact_town_keeps_circle(self, monkeypatch):
        # A small, compact town's bbox is tiny — the tuned circle is kept.
        ar = self._resolver_with_stubs(
            monkeypatch,
            lambda q: [10.970, 10.990, 108.240, 108.260])
        res = ar.resolve_area("Compact Town, Vietnam")
        assert res is not None
        assert res.union_bbox is None
        assert res.bounding_radius_km <= 2.0 + 0.01


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
