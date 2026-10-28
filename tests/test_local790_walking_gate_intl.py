"""test_local790_walking_gate_intl.py — LOCAL-790 acceptance (offline + live).

Walking tours OUTSIDE the US/Europe rejected every real place and shipped
"no stops could be generated". The field evidence (GCloud_Storied, P4 Vietnam,
2026-10-27) was two Ho Chi Minh City requests, each failing twice:

  * "French colonial architecture and Vietnamese culture walk, District 1 and 3,
    Ho Chi Minh City"  (5 stops)
  * "Pagodas and temples of Ho Chi Minh City (Jade Emperor Pagoda, Thien Hau
    Temple)"  (5 stops)

Six root causes, each tested here with the EXACT request text:

  1. The walking existence gate called ONLY Wikidata + Nominatim — places_search
     (Serper) was never reached — so a real place with 0 Wikidata-in-area hits
     and no OSM coverage was rejected. The gate's OSM lookup now routes through
     _places_lookup (Serper first, Nominatim fallback) with the scope's geocoded
     centre + LOCAL-786 bbox. (Live, gated behind LOCAL790_LIVE=1.)
  2. Replenishment never ran from 0 candidates for a landmark/walking tour —
     only business/dining had a from-zero refill.
  3. D571 VENUE-PARTS treated "Pagodas and temples of HCMC" as ONE venue and
     asked for its parts. A plural category + area is a MULTI-VENUE walking tour.
  4. The area parser read "District 1 and 3" as a city, and the comma-less
     "Pagodas and temples of HCMC" as a city. It now parses the area and expands
     numbered districts into a union.
  5. A NAMED parenthetical anchor (Thien Hau Temple) was dropped — named_anchors
     only read "from X to Y via …" route grammar.
  6. "Ngoc Hoang Pagoda" (Vietnamese) and "Jade Emperor Pagoda" (English) are the
     same place but title-only dedup kept both; dedupe now collapses by QID or by
     geocoded location (<=60 m).

The offline tests (causes 3, 4, 5, 6) are deterministic — no network. The live
existence test (cause 1) hits Wikidata/Serper/Nominatim and is gated behind
LOCAL790_LIVE=1 (Serper is a PAID API — keep CI offline):
    LOCAL790_LIVE=1 python3 -m pytest tests/test_local790_walking_gate_intl.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
import area_resolver as ar
import identity_dedup as idd


# The two exact field requests.
REQ_ARCH = ("French colonial architecture and Vietnamese culture walk, "
            "District 1 and 3, Ho Chi Minh City")
REQ_PAGODAS = ("Pagodas and temples of Ho Chi Minh City "
               "(Jade Emperor Pagoda, Thien Hau Temple)")


# ── CAUSE 3: a plural category + area is MULTI-VENUE, not one building ────────
class TestCause3PluralCategoryNotOneVenue(unittest.TestCase):
    def test_pagodas_and_temples_of_city_is_not_worship_civic(self):
        self.assertIsNone(gtt._detect_venue_class(REQ_PAGODAS, ""))
        self.assertIsNone(gtt._detect_venue_class(
            "Pagodas and temples of Ho Chi Minh City", ""))

    def test_other_plural_categories(self):
        for req in ("Churches of Rome", "museums in Paris", "temples in Kyoto",
                    "Cathedrals and basilicas of Seville"):
            self.assertIsNone(gtt._detect_venue_class(req, ""),
                              f"{req!r} is a multi-venue category tour")

    def test_single_named_worship_venue_still_worship_civic(self):
        self.assertEqual('worship_civic',
                         gtt._detect_venue_class("St Nicholas Cathedral, Nice, France", ""))
        self.assertEqual('worship_civic',
                         gtt._detect_venue_class("Our Lady Help of Christians church, Newton MA", ""))

    def test_facility_unchanged(self):
        self.assertEqual('facility',
                         gtt._detect_venue_class("Boston Logan International Airport", ""))

    def test_cimiez_walking_tour_untouched(self):
        self.assertIsNone(gtt._detect_venue_class(
            "Walking tour around Cimiez District, Nice, France", ""))

    def test_should_force_museum_rejects_plural_category(self):
        intent = {'venue_name': 'Pagodas and temples of Ho Chi Minh City'}
        self.assertFalse(gtt._should_force_museum(
            REQ_PAGODAS, "walking", intent, transport_mode='on_foot'))

    def test_arch_walk_is_not_a_venue_class(self):
        self.assertIsNone(gtt._detect_venue_class(REQ_ARCH, ""))


# ── CAUSE 4: area parsing — districts and the comma-less category prefix ─────
class TestCause4AreaParsing(unittest.TestCase):
    def test_district_1_and_3_parses_to_city_plus_two_districts(self):
        nb, city = ar._parse_location("District 1 and 3, Ho Chi Minh City")
        self.assertEqual(city, "Ho Chi Minh City")
        self.assertEqual(nb, "District 1 and 3")
        self.assertEqual(
            ar.parse_districts(nb, city),
            ["District 1, Ho Chi Minh City", "District 3, Ho Chi Minh City"])

    def test_vietnamese_quan_district_clause(self):
        nb, city = ar._parse_location("Qu\u1eadn 1 v\u00e0 3, Ho Chi Minh City")
        self.assertEqual(city, "Ho Chi Minh City")
        self.assertEqual(
            ar.parse_districts(nb, city),
            ["Qu\u1eadn 1, Ho Chi Minh City", "Qu\u1eadn 3, Ho Chi Minh City"])

    def test_single_quan(self):
        nb, city = ar._parse_location("Qu\u1eadn 1, Ho Chi Minh City")
        self.assertEqual(city, "Ho Chi Minh City")
        self.assertEqual(ar.parse_districts(nb, city),
                         ["Qu\u1eadn 1, Ho Chi Minh City"])

    def test_comma_less_plural_category_strips_to_city(self):
        nb, city = ar._parse_location("Pagodas and temples of Ho Chi Minh City")
        self.assertEqual(city, "Ho Chi Minh City")
        self.assertEqual(nb, "")

    def test_comma_less_category_with_paren_anchors(self):
        nb, city = ar._parse_location(REQ_PAGODAS)
        self.assertEqual(city, "Ho Chi Minh City")

    def test_three_districts(self):
        nb, city = ar._parse_location("Districts 1, 3 and 5, Ho Chi Minh City")
        self.assertEqual(city, "Ho Chi Minh City")
        self.assertEqual(
            ar.parse_districts(nb, city),
            ["District 1, Ho Chi Minh City", "District 3, Ho Chi Minh City",
             "District 5, Ho Chi Minh City"])

    def test_plain_neighborhood_is_not_a_district_clause(self):
        nb, city = ar._parse_location("Beacon Hill, Boston")
        self.assertEqual(ar.parse_districts(nb, city), [])

    def test_danvers_clause_still_parses(self):
        nb, city = ar._parse_location(
            "Walking tour in Danvers, MA including Witchcraft Victims Memorial")
        self.assertEqual(nb, "Danvers")
        self.assertEqual(city, "MA")
        self.assertEqual(ar.parse_districts(nb, city), [])


# ── CAUSE 5: parenthetical NAMED anchors are extracted ───────────────────────
class TestCause5ParentheticalAnchors(unittest.TestCase):
    def test_paren_anchors_extracted_in_order(self):
        anchors = gtt.named_anchors(REQ_PAGODAS)['anchors']
        self.assertEqual(anchors, ["Jade Emperor Pagoda", "Thien Hau Temple"])

    def test_thien_hau_is_not_dropped(self):
        self.assertIn("Thien Hau Temple", gtt.named_anchors(REQ_PAGODAS)['anchors'])

    def test_route_grammar_still_works(self):
        a = gtt.named_anchors(
            "walking tour from Boston Common to Faneuil Hall via "
            "Granary Burying Ground and Old State House")['anchors']
        self.assertEqual(a[0], "Boston Common")
        self.assertEqual(a[-1], "Faneuil Hall")
        self.assertIn("Granary Burying Ground", a)

    def test_no_anchors_without_route_or_parens(self):
        self.assertEqual(gtt.named_anchors("walking tour in Newton, MA")['anchors'], [])
        self.assertEqual(gtt.named_anchors("restaurant tour of the North End")['anchors'], [])

    def test_arch_walk_has_no_paren_anchors(self):
        self.assertEqual(gtt.named_anchors(REQ_ARCH)['anchors'], [])

    def test_numbers_only_paren_not_an_anchor(self):
        self.assertEqual(gtt.named_anchors("Temples of Kyoto (2024)")['anchors'], [])


# ── CAUSE 6: dedupe by geocoded location (<=60 m) or Wikidata QID ────────────
class TestCause6LocationOrQidDedupe(unittest.TestCase):
    def test_ngoc_hoang_equals_jade_emperor_by_location(self):
        pool = [
            {'name': 'Jade Emperor Pagoda', 'latitude': 10.7925, 'longitude': 106.6906},
            {'name': 'Ngoc Hoang Pagoda', 'latitude': 10.79255, 'longitude': 106.69062},
        ]
        kept, dropped = idd.dedupe_by_location_or_qid(pool)
        self.assertEqual([k['name'] for k in kept], ['Jade Emperor Pagoda'])
        self.assertEqual(dropped, [('Ngoc Hoang Pagoda', 'Jade Emperor Pagoda')])

    def test_same_qid_collapses_across_languages(self):
        pool = [
            {'name': 'Jade Emperor Pagoda', 'qid': 'Q2351692'},
            {'name': 'Ch\u00f9a Ng\u1ecdc Ho\u00e0ng', 'qid': 'Q2351692'},
        ]
        kept, dropped = idd.dedupe_by_location_or_qid(pool)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)

    def test_distinct_places_are_kept(self):
        pool = [
            {'name': 'Jade Emperor Pagoda', 'latitude': 10.7925, 'longitude': 106.6906},
            {'name': 'Thien Hau Temple', 'latitude': 10.7510, 'longitude': 106.6610},
            {'name': 'Ben Thanh Market', 'coordinates': '10.7721,106.6983'},
        ]
        kept, dropped = idd.dedupe_by_location_or_qid(pool)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])

    def test_title_fallback_when_no_coords_or_qid(self):
        pool = [{'name': 'Notre-Dame Cathedral'}, {'name': 'Notre Dame Cathedral.'}]
        kept, dropped = idd.dedupe_by_location_or_qid(pool)
        self.assertEqual(len(kept), 1)

    def test_far_apart_same_type_not_merged_by_distance(self):
        pool = [
            {'name': 'A Pagoda', 'latitude': 10.7925, 'longitude': 106.6906},
            {'name': 'B Pagoda', 'latitude': 10.8100, 'longitude': 106.7100},
        ]
        kept, dropped = idd.dedupe_by_location_or_qid(pool)
        self.assertEqual(len(kept), 2)


# ── CAUSE 2: replenishment from 0 is allowed for landmark/walking tours ──────
class TestCause2ReplenishFromZeroClassification(unittest.TestCase):
    """The from-0 allowance keys on classify_business_vs_landmark=='landmark'.
    A pagodas/architecture walk classifies 'landmark', so the LOCAL-290 GPT->gate
    loop is permitted to run from an empty list (business/dining keep their own
    maps-first empty refill)."""

    def test_pagoda_poi_type_is_landmark(self):
        from stop_existence_gate import classify_business_vs_landmark as cbl
        self.assertEqual(cbl("pagodas and temples"), "landmark")
        self.assertEqual(cbl("landmarks"), "landmark")
        self.assertEqual(cbl("colonial architecture"), "landmark")

    def test_business_and_dining_are_not_landmark(self):
        from stop_existence_gate import classify_business_vs_landmark as cbl
        self.assertEqual(cbl("coffee shops"), "business")
        self.assertEqual(cbl("restaurants"), "dining")


# ── CAUSE 1 (LIVE): the walking existence gate now reaches places_search ─────
@unittest.skipUnless(os.environ.get("LOCAL790_LIVE") == "1",
                     "live Wikidata/Serper/Nominatim — set LOCAL790_LIVE=1 (Serper is paid)")
class TestCause1WalkingExistenceLive(unittest.TestCase):
    SCOPE = "District 1, Ho Chi Minh City"
    VENUE = ("French colonial architecture and Vietnamese culture walk, "
             "District 1 and 3, Ho Chi Minh City")

    def test_real_hcmc_places_verify(self):
        import stop_existence_gate as seg
        for name in ("Notre-Dame Cathedral Basilica of Saigon",
                     "Ben Thanh Market", "Jade Emperor Pagoda"):
            ok, ev = seg._check_walking_stop_existence(name, self.VENUE, scope=self.SCOPE)
            self.assertTrue(ok, f"{name!r} should verify in HCMC — got evidence {ev!r}")
            self.assertTrue(ev, "verified stop must carry evidence text")

    def test_fabricated_place_still_fails(self):
        import stop_existence_gate as seg
        ok, ev = seg._check_walking_stop_existence(
            "The Nonexistent Imaginary Pagoda of Nowhere", self.VENUE, scope=self.SCOPE)
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()
