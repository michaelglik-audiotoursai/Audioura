#!/usr/bin/env python3
"""test_local591_every_stop_has_coordinates.py — LOCAL-591 Fix #4.

Field defect (tours 395/396): King's Chapel was added LATE —
    [D556] ADDED 'King's Chapel'
by the LOCAL-576 replenishment loop, which runs AFTER the D559 geocoding phase.
Nothing geocoded it afterward, so it shipped with NO coordinates and had no map
marker.

A delivered stop with no coordinates cannot be placed on the map. The fix is a
final coordinate sweep, _geocode_missing_coordinates(), run just before PHASE 6
packs the tour: any stop lacking a parseable coordinate — whatever path added it
(LOCAL-576 replenishment, D556, LOCAL-577/589 refills) — is geocoded, or logged
if it cannot be. This suite proves the sweep, offline (the coordinate fetch is
injected).

D307: a test exercises the real generation path (the sweep is wired just before
PHASE 6, asserted by source).
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt


def _has_coords(poi):
    return bool(re.search(r'-?\d+\.?\d*\s*,\s*-?\d+\.?\d*', poi.get('coordinates', '') or ''))


class TestGeocodeMissingCoordinates(unittest.TestCase):

    def test_helper_exists(self):
        self.assertTrue(hasattr(gtt, "_geocode_missing_coordinates"))

    def test_late_added_stop_gets_coordinates(self):
        """A stop with no coordinates (as King's Chapel arrived) is geocoded."""
        poi_list = [
            {"name": "Boston Athenaeum", "coordinates": "42.3576, -71.0611"},
            {"name": "King's Chapel"},                 # late add — no coordinates
        ]

        def _fake_fetch(poi):
            # Deterministic stand-in for the geocoder/LLM.
            coords = {
                "King's Chapel": "42.3586, -71.0603",
            }.get(poi["name"], "")
            return poi, coords, 0

        n_fixed, still_missing, _tokens = gtt._geocode_missing_coordinates(
            poi_list, "Boston Athenaeum, Boston, MA", headers={}, coord_fetch=_fake_fetch)

        self.assertEqual(n_fixed, 1)
        self.assertEqual(still_missing, [])
        self.assertTrue(_has_coords(poi_list[1]),
                        "the late-added stop must have coordinates after the sweep")

    def test_every_delivered_stop_has_coordinates_after_sweep(self):
        poi_list = [
            {"name": "A", "coordinates": "1.0, 2.0"},
            {"name": "B"},
            {"name": "C", "coordinates": ""},
        ]

        def _fetch(poi):
            return poi, "3.0, 4.0", 0

        gtt._geocode_missing_coordinates(poi_list, "Somewhere", headers={}, coord_fetch=_fetch)
        for p in poi_list:
            self.assertTrue(_has_coords(p), f"stop {p['name']} still has no coordinates")

    def test_unresolvable_stop_is_reported_not_silently_dropped(self):
        """A stop the geocoder cannot place is reported in still_missing — the
        tour still delivers it (never DELETE), the gap is just announced."""
        poi_list = [
            {"name": "A", "coordinates": "1.0, 2.0"},
            {"name": "Nowhereville Phantom Annexe"},
        ]

        def _fetch(poi):
            return poi, "", 0        # geocoder could not place it

        n_fixed, still_missing, _ = gtt._geocode_missing_coordinates(
            poi_list, "Somewhere", headers={}, coord_fetch=_fetch)

        self.assertEqual(n_fixed, 0)
        self.assertEqual(still_missing, ["Nowhereville Phantom Annexe"])
        # The stop is NOT removed — never DELETE a stop.
        self.assertEqual(len(poi_list), 2)

    def test_existing_coordinates_are_not_refetched(self):
        poi_list = [{"name": "A", "coordinates": "1.0, 2.0"}]
        calls = []

        def _fetch(poi):
            calls.append(poi["name"])
            return poi, "9.9, 9.9", 0

        gtt._geocode_missing_coordinates(poi_list, "x", headers={}, coord_fetch=_fetch)
        self.assertEqual(calls, [], "a stop that already has coordinates must not be refetched")
        self.assertEqual(poi_list[0]["coordinates"], "1.0, 2.0")

    def test_latitude_longitude_fields_count_as_coordinates(self):
        # A stop carrying numeric latitude/longitude fields is NOT missing coords.
        poi_list = [{"name": "A", "latitude": 1.0, "longitude": 2.0}]
        calls = []

        def _fetch(poi):
            calls.append(poi["name"])
            return poi, "9.9, 9.9", 0

        n_fixed, still_missing, _ = gtt._geocode_missing_coordinates(
            poi_list, "x", headers={}, coord_fetch=_fetch)
        self.assertEqual(calls, [])
        self.assertEqual(n_fixed, 0)
        self.assertEqual(still_missing, [])


class TestWiredBeforePacking(unittest.TestCase):
    """D307: the sweep runs just before PHASE 6 assembly in the real path."""

    def setUp(self):
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "generate_tour_text.py")
        with open(gen_path, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_sweep_is_called(self):
        self.assertIn("_geocode_missing_coordinates(", self.src,
                      "the coordinate sweep must be wired into the generation path")

    def test_sweep_runs_before_phase_6_assembly(self):
        call_idx = self.src.find("_geocode_missing_coordinates(\n            poi_list")
        if call_idx < 0:
            call_idx = self.src.find("_geocode_missing_coordinates(poi_list")
        if call_idx < 0:
            # Any wired call that passes poi_list, however formatted.
            m = re.search(r'_geocode_missing_coordinates\(\s*poi_list', self.src)
            call_idx = m.start() if m else -1
        phase6_idx = self.src.find("PHASE 6: Assemble the complete tour")
        self.assertGreater(call_idx, 0, "sweep call (passing poi_list) not found")
        self.assertGreater(phase6_idx, 0, "PHASE 6 marker not found")
        self.assertLess(call_idx, phase6_idx,
                        "the coordinate sweep must run BEFORE PHASE 6 packs the tour")


if __name__ == "__main__":
    unittest.main(verbosity=2)
