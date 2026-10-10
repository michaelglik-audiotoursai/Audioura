#!/usr/bin/env python3
"""test_local667_building_stops.py — LOCAL-667 building + collection-area stops.

When a thin-Wikidata museum is still short after source verification, a museum
tour's legitimate stops include the historic BUILDING (HCMC occupies the Hui Bon
Hoa mansion, 1929-1934) and NAMED COLLECTION AREAS (lacquer, Champa sculpture, Óc
Eo). These tests pin that such stops are produced ONLY when the corpus grounds
them — never invented — and are typed so the assembler renders them as area /
building stops.

Run: python3 -m pytest test_local667_building_stops.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from museum_fallback_stops import (  # noqa: E402
    build_fallback_stops,
    detect_building_stop,
    detect_collection_area_stops,
)

_VENUE = "Ho Chi Minh City Museum of Fine Arts"

# Corpus modelled on the real HCMC Wikipedia + site content.
_HCMC_CORPUS = (
    "The Ho Chi Minh City Museum of Fine Arts is housed in the former Hui Bon Hoa "
    "mansion, a building constructed between 1929 and 1934 in a blend of French "
    "colonial and Chinese architecture. The permanent collection includes lacquer "
    "painting, silk painting, and Champa sculpture, as well as Óc Eo antiquities "
    "excavated in the Mekong Delta. The ceramics gallery displays Vietnamese "
    "porcelain."
)


class TestBuildingStop(unittest.TestCase):
    def test_named_building_from_corpus(self):
        stop = detect_building_stop(_VENUE, combined_text=_HCMC_CORPUS)
        self.assertIsNotNone(stop)
        self.assertIn("Hui Bon Hoa mansion", stop["name"])
        self.assertEqual(stop["_stop_kind"], "building")
        self.assertTrue(stop["verified"])

    def test_building_qid_forces_stop(self):
        stop = detect_building_stop(_VENUE, combined_text="A plain museum.",
                                    building_qid="Q12345")
        self.assertIsNotNone(stop)
        self.assertEqual(stop["_stop_kind"], "building")

    def test_no_building_when_corpus_silent(self):
        stop = detect_building_stop(_VENUE, combined_text="It has nice paintings.")
        self.assertIsNone(stop)

    def test_architecture_described_generic_building(self):
        stop = detect_building_stop(_VENUE,
                                    combined_text="The museum's neoclassical facade is admired.")
        self.assertIsNotNone(stop)
        self.assertIn(_VENUE, stop["name"])


class TestCollectionAreas(unittest.TestCase):
    def test_areas_grounded_in_corpus(self):
        stops = detect_collection_area_stops(combined_text=_HCMC_CORPUS)
        labels = [s["name"] for s in stops]
        self.assertIn("Lacquer painting collection", labels)
        self.assertIn("Silk painting collection", labels)
        self.assertIn("Champa sculpture collection", labels)
        self.assertIn("Óc Eo antiquities collection", labels)
        self.assertIn("Ceramics collection", labels)
        for s in stops:
            self.assertEqual(s["_stop_kind"], "collection_area")
            self.assertTrue(s["verified"])

    def test_absent_area_not_invented(self):
        stops = detect_collection_area_stops(combined_text=_HCMC_CORPUS)
        labels = [s["name"] for s in stops]
        # The corpus never mentions Khmer sculpture → it must not appear.
        self.assertNotIn("Khmer sculpture collection", labels)

    def test_empty_corpus_no_areas(self):
        self.assertEqual(detect_collection_area_stops(combined_text=""), [])


class TestBuildFallback(unittest.TestCase):
    def test_building_first_then_areas_capped_to_needed(self):
        stops = build_fallback_stops(_VENUE, combined_text=_HCMC_CORPUS, needed=3)
        self.assertEqual(len(stops), 3)
        self.assertEqual(stops[0]["_stop_kind"], "building")   # building leads
        self.assertTrue(all(s["_stop_kind"] in ("building", "collection_area")
                            for s in stops))

    def test_needed_zero_returns_empty(self):
        self.assertEqual(build_fallback_stops(_VENUE, combined_text=_HCMC_CORPUS, needed=0), [])

    def test_excludes_existing_names(self):
        # If 'Lacquer painting collection' is already in the tour, it is not re-added.
        stops = build_fallback_stops(
            _VENUE, combined_text=_HCMC_CORPUS, needed=5,
            exclude_names=["Lacquer painting collection"])
        labels = [s["name"] for s in stops]
        self.assertNotIn("Lacquer painting collection", labels)

    def test_nothing_grounded_returns_empty(self):
        stops = build_fallback_stops(_VENUE, combined_text="Just a museum.", needed=4)
        # No building, no areas grounded → honest shortfall preserved.
        self.assertEqual(stops, [])

    def test_hcmc_reaches_five_with_one_work(self):
        """The end-to-end shape: 1 verified work + building + areas → 5 stops."""
        existing = ["North Central South Spring Garden"]  # the one verified work
        stops = build_fallback_stops(
            _VENUE, combined_text=_HCMC_CORPUS, needed=4, exclude_names=existing)
        self.assertEqual(len(stops), 4)
        total = len(existing) + len(stops)
        self.assertEqual(total, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
