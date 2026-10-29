#!/usr/bin/env python3
"""test_local802_relevance_and_dedupe.py — LOCAL-802.

Unit tests with the EXACT P1 fixtures (p1/blind, subscribed eaade7d2):

  * d3 B (Mui Ne seafood): a Permian–Triassic extinction paragraph dropped into a
    seafood-restaurant stop.
  * b1 B (massage near Ben Thanh): a reality-TV digression ("The Race", 42,000 km).
  * r2 B (Arnold Arboretum): Visitor Center and Hunnewell Building shipped as two
    stops — the SAME building.
  * Addendum 4 (LOCAL-799, request 467): "White Sand Dunes" must NOT be covered by
    a stop "Mui Ne Sand Dunes Resort" (a hotel).
  * Addendum 5: a named place in a driving/nature tour that geocodes in scope
    becomes a STOP.

Everything here is offline (no network, no paid API): the relevance gate,
same-building dedupe, false-coverage predicate and widening geometry are pure;
the geocode-to-stop rescue is driven by an injected fake places_search_fn.

Run: python3 -m pytest test_local802_relevance_and_dedupe.py -q
"""
import unittest

import local802_relevance_gate as g
import area_resolver as ar
from area_resolver import AreaResolution


# ── Exact P1 off-topic passages (the discrete injected snippets) ──────────────

# d3 B — the Permian–Triassic extinction fact, as the injected background snippet
# (the unit the relevance gate sees, before the LLM weaves it into prose).
PERMIAN = ("The Permian–Triassic extinction event, some 251.9 million years ago, "
           "wiped out over 81% of marine species in the world's oceans.")
# An on-topic seafood fact from the same d3 stop.
SEAFOOD_ON_TOPIC = ("The owner here began as a fisherman, hauling in crabs, prawns, "
                    "and oysters each dawn off Mui Ne's coast; the prawn was caught "
                    "this morning.")
# b1 B — the reality-TV digression, as the injected snippet.
THE_RACE = ("The Race in the 2009 season brought teams through Vietnam as part of "
            "its 42,000-kilometre journey across three continents and seven "
            "countries.")
# An on-topic spa fact from the same b1 stop.
SPA_ON_TOPIC = ("Saigon Heritage Spa offers traditional Vietnamese massages, herbal "
                "steam baths, and skincare treatments in a historic French-colonial "
                "building.")


class TestRelevanceGateDropsP1OffTopic(unittest.TestCase):
    def test_permian_dropped_from_seafood_stop(self):
        self.assertFalse(
            g.passage_is_relevant(PERMIAN, stop_title="Bờ kè Mr.Crab 112",
                                  place="Mui Ne, Vietnam", category="restaurant"),
            "the Permian–Triassic extinction fact is off-topic in a seafood stop")

    def test_seafood_fact_kept(self):
        self.assertTrue(
            g.passage_is_relevant(SEAFOOD_ON_TOPIC, stop_title="Bờ kè Mr.Crab 112",
                                  place="Mui Ne, Vietnam", category="restaurant"),
            "a genuine seafood fact about the stop must be kept")

    def test_the_race_dropped_from_spa_stop(self):
        self.assertFalse(
            g.passage_is_relevant(THE_RACE, stop_title="Saigon Heritage Spa",
                                  place="Ben Thanh Market, Ho Chi Minh City",
                                  category="business"),
            "the reality-TV 'The Race' digression is off-topic in a spa stop")

    def test_spa_fact_kept(self):
        self.assertTrue(
            g.passage_is_relevant(SPA_ON_TOPIC, stop_title="Saigon Heritage Spa",
                                  place="Ben Thanh Market, Ho Chi Minh City",
                                  category="business"))

    def test_passage_mentioning_the_stop_name_is_kept(self):
        # A passage that names the stop is relevant even if otherwise generic.
        self.assertTrue(
            g.passage_is_relevant("Casa Muine opened its terrace in 2015.",
                                  stop_title="CASA MUINE - Sea & Food",
                                  place="Mui Ne, Vietnam", category="restaurant"))

    def test_passage_mentioning_the_place_is_kept(self):
        self.assertTrue(
            g.passage_is_relevant("Mui Ne is a fishing town on Vietnam's "
                                  "south-east coast.",
                                  stop_title="Some Stop", place="Mui Ne, Vietnam",
                                  category="restaurant"))

    def test_empty_passage_is_not_relevant(self):
        self.assertFalse(g.passage_is_relevant("", stop_title="X", place="Y",
                                               category="restaurant"))

    def test_no_anchors_keeps_passage(self):
        # With no stop/place/theme/category anchors to judge against, do not drop.
        self.assertTrue(g.passage_is_relevant(PERMIAN))


class TestOffDomainDigression(unittest.TestCase):
    """A passage that name-drops the stop but is DOMINATED by an off-domain
    spectacle (a TV race, a mass extinction) is still a digression — dropped."""

    REALITY = ("Local tales suggest that during the 2009 premiere of 'HaMerotz "
               "LaMillion', the Israeli reality competition, contestants might have "
               "brushed past this spa. The competition, spanning over 42,000 "
               "kilometres across continents, offered viewers a glimpse of the "
               "varied landscapes. As you step outside, the streets beckon you.")
    PERMIAN_IN_PROSE = ("As you taste the freshness here, you share a tradition shaped "
                        "by the tides, a victory over the chaos that swept the oceans "
                        "when, some 251.9 million years ago, the Permian–Triassic "
                        "extinction event wiped out over 81% of marine species.")

    def test_reality_tv_digression_dropped_even_though_it_names_the_spa(self):
        self.assertFalse(
            g.passage_is_relevant(self.REALITY, stop_title="Saigon Heritage Spa",
                                  place="Ho Chi Minh City", category="walking"),
            "the reality-TV digression name-drops 'spa' but is about a TV race")

    def test_permian_clause_in_seafood_prose_dropped(self):
        self.assertFalse(
            g.passage_is_relevant(self.PERMIAN_IN_PROSE,
                                  stop_title="Bờ kè Mr.Crab 112",
                                  place="Mui Ne, Vietnam", category="restaurant"))

    def test_genuine_on_topic_spa_story_kept(self):
        good = ("Nguyen Van Minh founded the Saigon Heritage Spa in 1998, training "
                "his staff in traditional Vietnamese massage over three generations. "
                "He insisted on herbal steam baths prepared fresh each morning. The "
                "spa drew a loyal local following.")
        self.assertTrue(
            g.passage_is_relevant(good, stop_title="Saigon Heritage Spa",
                                  place="Ho Chi Minh City", category="walking"))

    def test_detector_needs_a_real_marker(self):
        # A plain large number alone (no spectacle marker) is NOT a digression.
        self.assertFalse(g._is_off_domain_digression(
            "The spa has served over 42 guests a day since 1998."))
        self.assertTrue(g._is_off_domain_digression(
            "The reality competition spanned 42,000 kilometres across continents."))


class TestOffDomainSentenceScrub(unittest.TestCase):
    """The narration LLM wove the extinction/reality-TV fact sentence by sentence
    into the delivered body (no retrieved passage to gate) — the post-generation
    scrub must remove exactly those sentences and keep the on-topic ones."""

    # The EXACT shape the d3 cheap-arm live run delivered (id=13).
    D3_BODY = ("Inside the bustling kitchen, you'll find an embodiment of Mui Ne's "
               "vibrant seafood heritage. The owner, with roots tracing back to a "
               "lineage of fishermen, ensures the catch of the day arrives directly "
               "from the waters. Triggered by the cataclysmic flood basalt eruptions, "
               "the atmospheric carbon dioxide soared from 400 to 2,500 ppm, warping "
               "the oceans' ecosystems. It was Earth's own drastic menu change, "
               "wiping out marine species and opening room for new life forms. The "
               "menu, with dishes ranging from 100,000 to 600,000 dong, is a culinary "
               "voyage. And just like the oceans post-extinction, after a taste here, "
               "you'll leave transformed.")

    def test_scrub_removes_extinction_sentences_keeps_seafood(self):
        scrubbed, dropped = g.scrub_off_domain_sentences(
            self.D3_BODY, "Bờ kè Mr.Crab 112")
        self.assertEqual(3, len(dropped))
        self.assertNotIn("extinction", scrubbed.lower())
        self.assertNotIn("marine species", scrubbed.lower())
        self.assertNotIn("ppm", scrubbed.lower())
        # On-topic seafood sentences survive.
        self.assertIn("seafood heritage", scrubbed)
        self.assertIn("100,000 to 600,000 dong", scrubbed)

    def test_scrub_logs_each_drop(self):
        logs = []
        g.scrub_off_domain_sentences(self.D3_BODY, "Bờ kè Mr.Crab 112",
                                     log=logs.append)
        self.assertEqual(3, len(logs))
        self.assertTrue(all(l.startswith("[LOCAL-802] off-topic passage dropped")
                            for l in logs))

    def test_scrub_removes_reality_tv_race_sentences(self):
        body = ("Saigon Heritage Spa offers traditional Vietnamese massage. During "
                "the 2009 reality competition, contestants raced 42,000 kilometres "
                "across continents. Book ahead for the herbal steam bath.")
        scrubbed, dropped = g.scrub_off_domain_sentences(body, "Saigon Heritage Spa")
        self.assertEqual(1, len(dropped))
        self.assertIn("traditional Vietnamese massage", scrubbed)
        self.assertIn("herbal steam bath", scrubbed)
        self.assertNotIn("42,000", scrubbed)

    def test_scrub_is_noop_for_clean_text(self):
        clean = ("The Arnold Arboretum's Lilac Collection began in 1872. Charles "
                 "Sprague Sargent planted the first lilacs. Over 400 varieties bloom "
                 "each spring.")
        scrubbed, dropped = g.scrub_off_domain_sentences(clean, "Lilac Collection")
        self.assertEqual([], dropped)
        self.assertEqual(clean, scrubbed)

    def test_scrub_never_empties_the_body(self):
        all_off = ("The Permian–Triassic extinction event killed 81% of marine "
                   "species. It happened 251 million years ago.")
        scrubbed, dropped = g.scrub_off_domain_sentences(all_off, "X")
        # Every sentence is off-domain → body returned unchanged (never empty).
        self.assertEqual(all_off, scrubbed)
        self.assertEqual(2, len(dropped))


class TestFilterAndLogLine(unittest.TestCase):
    def test_filter_drops_off_topic_keeps_on_topic_and_logs(self):
        logs = []
        kept, dropped = g.filter_injected_passages(
            [{"snippet": SEAFOOD_ON_TOPIC}, {"snippet": PERMIAN}],
            stop_title="Bờ kè Mr.Crab 112", place="Mui Ne, Vietnam",
            category="restaurant", log=logs.append)
        self.assertEqual(1, len(kept))
        self.assertEqual(SEAFOOD_ON_TOPIC, kept[0]["snippet"])
        self.assertEqual(1, len(dropped))
        self.assertEqual(1, len(logs))
        self.assertTrue(logs[0].startswith("[LOCAL-802] off-topic passage dropped"))

    def test_log_line_format(self):
        line = g.off_topic_drop_log_line("Bờ kè Mr.Crab 112", PERMIAN)
        self.assertTrue(line.startswith(
            "[LOCAL-802] off-topic passage dropped Bờ kè Mr.Crab 112 "))
        # First words of the passage are included.
        self.assertIn("The Permian–Triassic extinction event, some", line)

    def test_filter_accepts_bare_strings(self):
        kept, dropped = g.filter_injected_passages(
            [SEAFOOD_ON_TOPIC, THE_RACE], stop_title="Saigon Heritage Spa",
            place="Ho Chi Minh City", category="business")
        # The seafood line shares no spa/HCMC token either — both off-topic for a
        # spa stop; this asserts the function runs on bare strings and returns
        # same-typed survivors.
        self.assertTrue(all(isinstance(k, str) for k in kept))


# ── Same-building dedupe (r2 Arnold Arboretum) ────────────────────────────────

class TestSameBuildingDedupe(unittest.TestCase):
    def _vc(self):
        # The Visitor Center carries "Hunnewell Building" among its Wikidata
        # aliases (as _fetch_aliases_and_location stamps).
        return {"name": "The Arnold Arboretum Visitor Center",
                "aliases": ["Hunnewell Building"],
                "latitude": 42.3355, "longitude": -71.1139,
                "wikidata_qid": "Q4793078"}

    def _hb(self):
        # The second, duplicate stop — the same building under its building name,
        # ~133 m away in the delivered (LLM) coords and sharing no name token.
        return {"name": "Hunnewell Building",
                "latitude": 42.3353, "longitude": -71.1155}

    def test_alias_bridges_visitor_center_and_hunnewell(self):
        self.assertTrue(g.same_building(self._vc(), self._hb()),
                        "Visitor Center alias 'Hunnewell Building' == the HB stop")

    def test_same_qid_is_same_building(self):
        a = {"name": "A", "wikidata_qid": "Q123"}
        b = {"name": "B", "qid": "Q123"}
        self.assertTrue(g.same_building(a, b))

    def test_located_in_qid(self):
        a = {"name": "Visitor Center", "located_in": ["Q4793078"]}
        b = {"name": "Hunnewell Building", "wikidata_qid": "Q4793078"}
        self.assertTrue(g.same_building(a, b))

    def test_coords_within_60m_and_shared_token(self):
        a = {"name": "Old Mill", "latitude": 42.0, "longitude": -71.0}
        b = {"name": "The Old Mill House", "latitude": 42.00005, "longitude": -71.0}
        self.assertTrue(g.same_building(a, b))

    def test_distinct_rooms_close_but_no_shared_token_not_merged(self):
        # Two different numbered rooms of one museum can be <60 m apart — they are
        # NOT the same building by coords alone (no shared distinctive name token).
        a = {"name": "Egyptian Gallery", "latitude": 42.0, "longitude": -71.0}
        b = {"name": "Roman Sculpture Hall", "latitude": 42.00005, "longitude": -71.0}
        self.assertFalse(g.same_building(a, b))

    def test_dedupe_collapses_r2_visitor_center_and_hunnewell(self):
        stops = [
            {"name": "The Arnold Arboretum's Lilac Collection",
             "latitude": 42.3353, "longitude": -71.1152},
            self._vc(),
            {"name": "The Rose Garden", "latitude": 42.3356, "longitude": -71.1138},
            self._hb(),
        ]
        deduped, removed = g.dedupe_same_building_stops(stops)
        names = [s["name"] for s in deduped]
        self.assertIn("The Arnold Arboretum Visitor Center", names)
        self.assertNotIn("Hunnewell Building", names,
                         "the duplicate Hunnewell stop must be collapsed")
        self.assertEqual(3, len(deduped))
        self.assertEqual(["Hunnewell Building"], removed)

    def test_dedupe_preserves_order_and_distinct_stops(self):
        stops = [{"name": "Lilac Collection"}, {"name": "Rose Garden"},
                 {"name": "Bonsai Pavilion"}]
        deduped, removed = g.dedupe_same_building_stops(stops)
        self.assertEqual([s["name"] for s in stops],
                         [s["name"] for s in deduped])
        self.assertEqual([], removed)

    def test_curated_alias_bridge_collapses_with_fabricated_far_coords(self):
        # The live r2 case: VC and HB shipped from replenishment with NO aliases
        # field and fabricated coordinates ~2 km apart. The curated same-building
        # alias group bridges them deterministically, offline.
        vc = {"name": "The Arnold Arboretum Visitor Center",
              "latitude": 42.3152, "longitude": -71.1147}
        hb = {"name": "Hunnewell Building",
              "latitude": 42.3350, "longitude": -71.1155}
        self.assertTrue(g.same_building(vc, hb))
        deduped, removed = g.dedupe_same_building_stops(
            [{"name": "Jamaica Pond"}, vc, {"name": "The Rose Garden"}, hb])
        self.assertEqual(["Hunnewell Building"], removed)
        self.assertNotIn("Hunnewell Building", [s["name"] for s in deduped])


# ── Addendum 4: false coverage (White Sand Dunes vs a Resort) ─────────────────

class TestFalseCoverageSameKind(unittest.TestCase):
    def test_resort_does_not_cover_white_sand_dunes(self):
        self.assertFalse(
            g.natural_feature_covered_by(
                "White Sand Dunes",
                {"name": "Mui Ne Sand Dunes Resort", "type": "hotel"}),
            "a hotel/resort that borrows the feature's name does not cover it")

    def test_same_kind_dunes_stop_covers(self):
        self.assertTrue(
            g.natural_feature_covered_by(
                "White Sand Dunes",
                {"name": "White Sand Dunes", "type": "natural feature"}))

    def test_non_feature_name_is_unrestricted(self):
        # "Opera House" is not a natural feature → no same-kind restriction here.
        self.assertTrue(
            g.natural_feature_covered_by("Opera House",
                                         {"name": "Saigon Opera House"}))

    def test_stop_kind_classification(self):
        self.assertEqual("commercial",
                         g.stop_kind({"name": "Mui Ne Sand Dunes Resort"}))
        self.assertEqual("natural", g.stop_kind({"name": "White Sand Dunes"}))
        self.assertEqual("natural", g.stop_kind({"name": "Fairy Stream"}))

    def test_named_place_is_covered_rejects_resort_for_dunes(self):
        # The area_resolver reconciler must NOT count a resort stop as covering the
        # named natural feature — even on a token subset.
        final = [{"name": "Mui Ne Sand Dunes Resort"}]
        self.assertFalse(
            ar._named_place_is_covered("White Sand Dunes", final),
            "LOCAL-799 bug: a hotel must not cover the natural feature")

    def test_named_place_is_covered_accepts_same_kind(self):
        final = [{"name": "White Sand Dunes"}]
        self.assertTrue(ar._named_place_is_covered("White Sand Dunes", final))

    def test_resort_near_dunes_by_geocode_still_not_covered(self):
        # Even geocoded within 300 m, a resort does not cover the feature.
        final = [{"name": "Mui Ne Sand Dunes Resort",
                  "latitude": 10.9400, "longitude": 108.2500}]
        coords = {"White Sand Dunes": (10.9402, 108.2501)}
        self.assertFalse(
            ar._named_place_is_covered("White Sand Dunes", final,
                                       name_coord=coords["White Sand Dunes"]))

    def test_reconcile_announces_white_sand_dunes_when_only_resort_present(self):
        # End-to-end through the reconciler: only a resort is in the final list, so
        # the natural feature the listener named is still UNCOVERED → announced.
        final = [{"name": "Mui Ne Sand Dunes Resort"},
                 {"name": "Red Sand Dunes"}, {"name": "Fairy Stream"}]
        uncovered = ar.reconcile_named_place_announcement(
            ["White Sand Dunes"], final)
        self.assertEqual(["White Sand Dunes"], uncovered)


# ── Addendum 5: named place in a driving/nature tour becomes a stop ───────────

class TestNamedPlaceGeocodeToStop(unittest.TestCase):
    AREA = AreaResolution(city_qid="Q1", city_name="Mui Ne",
                          center_lat=10.93, center_lng=108.29,
                          bounding_radius_km=8.0, resolved=True)

    @staticmethod
    def _new_poi(name, address=""):
        return {"name": name, "address": address}

    def test_place_anchor_categories(self):
        self.assertTrue(g.is_place_anchor_tour_category("walking"))
        self.assertTrue(g.is_place_anchor_tour_category("driving"))
        self.assertTrue(g.is_place_anchor_tour_category("nature"))
        self.assertFalse(g.is_place_anchor_tour_category("business"))
        self.assertFalse(g.is_place_anchor_tour_category("museum"))

    def test_geocoded_named_place_becomes_a_stop(self):
        calls = []

        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            calls.append(name)
            return [{"name": name, "latitude": 10.95, "longitude": 108.24,
                     "type": "natural feature"}]

        pois, announce = ar.apply_named_place_policy(
            [{"name": "Red Canyon"}], ["Red Sand Dunes"], self.AREA, [],
            self._new_poi, places_search_fn=fake_ps, scope="Mui Ne, Vietnam",
            geocode_to_stop=True)
        names = [p["name"] for p in pois]
        self.assertIn("Red Sand Dunes", names,
                      "a named place that geocodes in scope becomes a stop")
        self.assertEqual([], announce, "it is a stop, not an announcement")
        self.assertEqual(["Red Sand Dunes"], calls)
        # The inserted stop is user-explicit/verified with coordinates.
        rsd = next(p for p in pois if p["name"] == "Red Sand Dunes")
        self.assertTrue(rsd.get("user_explicit"))
        self.assertTrue(rsd.get("verified"))
        self.assertEqual(10.95, rsd.get("latitude"))

    def test_natural_feature_only_geocoding_to_a_resort_is_not_a_stop(self):
        # Addendum 4 inside addendum 5: a natural feature whose only geocode hit is
        # a commercial resort must NOT become a stop — it is announced instead.
        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            return [{"name": "Mui Ne Sand Dunes Resort", "latitude": 10.95,
                     "longitude": 108.24, "type": "hotel"}]

        pois, announce = ar.apply_named_place_policy(
            [{"name": "Red Canyon"}], ["White Sand Dunes"], self.AREA, [],
            self._new_poi, places_search_fn=fake_ps, scope="Mui Ne, Vietnam",
            geocode_to_stop=True)
        names = [p["name"] for p in pois]
        self.assertNotIn("White Sand Dunes", names)
        self.assertTrue(any("White Sand Dunes" in a for a in announce),
                        "a feature that only matches a resort is announced, "
                        "not inserted")

    def test_geocode_miss_still_announces(self):
        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            return []  # genuinely not on the map

        pois, announce = ar.apply_named_place_policy(
            [{"name": "Red Canyon"}], ["White Sand Dunes"], self.AREA, [],
            self._new_poi, places_search_fn=fake_ps, scope="Mui Ne, Vietnam",
            geocode_to_stop=True)
        self.assertNotIn("White Sand Dunes", [p["name"] for p in pois])
        self.assertTrue(any("White Sand Dunes" in a for a in announce))

    def test_without_opt_in_original_announce_behaviour(self):
        # geocode_to_stop defaults off → unchanged LOCAL-751 behaviour (announce).
        pois, announce = ar.apply_named_place_policy(
            [{"name": "Red Canyon"}], ["White Sand Dunes"], self.AREA, [],
            self._new_poi)
        self.assertNotIn("White Sand Dunes", [p["name"] for p in pois])
        self.assertTrue(any("White Sand Dunes" in a for a in announce))


# ── Do #3: stop-count widening geometry ───────────────────────────────────────

class TestWideningGeometry(unittest.TestCase):
    def test_widen_bbox_doubles_extent_about_centre(self):
        wide = g.widen_bbox([10.0, 10.1, 108.0, 108.1], factor=2.0)
        # Centre preserved.
        self.assertAlmostEqual((wide[0] + wide[1]) / 2.0, 10.05, places=6)
        self.assertAlmostEqual((wide[2] + wide[3]) / 2.0, 108.05, places=6)
        # Height and width doubled (0.1 → 0.2).
        self.assertAlmostEqual(wide[1] - wide[0], 0.2, places=6)
        self.assertAlmostEqual(wide[3] - wide[2], 0.2, places=6)

    def test_widen_bbox_none_and_invalid(self):
        self.assertIsNone(g.widen_bbox(None))
        self.assertIsNone(g.widen_bbox([1, 2, 3]))

    def test_widen_radius_caps(self):
        self.assertEqual(4.0, g.widen_radius_km(2.0))
        self.assertEqual(25.0, g.widen_radius_km(20.0))  # capped
        self.assertEqual(0.0, g.widen_radius_km(0.0))

    def test_widen_bbox_clamps_latitude(self):
        wide = g.widen_bbox([80.0, 89.0, 0.0, 10.0], factor=4.0)
        self.assertLessEqual(wide[1], 90.0)
        self.assertGreaterEqual(wide[0], -90.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
