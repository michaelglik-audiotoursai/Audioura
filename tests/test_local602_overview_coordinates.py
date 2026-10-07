#!/usr/bin/env python3
"""test_local602_overview_coordinates.py — LOCAL-602 root cause #3.

Field defect (tour 397): the overview/pool delivery path shipped a 1-stop
"Overview" with lat/lng NULL — invisible to tours-near, no map pin. LOCAL-591 #4
("every delivered stop has coordinates") is bypassed on this path.

The fix: _assemble_overview_tour_text geocodes the venue's address (or location)
and emits a Coordinates: line, and returns None (clean-fail) when no coordinate
can be produced — so a tour is NEVER delivered without a map point.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
from museum_overview import MuseumOverview

_COORD_RE = re.compile(r'Coordinates:\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)')


def _overview(address=''):
    return MuseumOverview(
        narration="WNDR Museum is an immersive art and technology experience. " * 8,
        sources=['https://www.wndrmuseum.com/boston'],
        has_hours=False, has_admission=False,
        exhibitions=[], as_of='October 2026', facts_line='',
        address=address,
    )


class TestOverviewHasCoordinates(unittest.TestCase):

    def test_address_is_geocoded_into_a_coordinates_line(self):
        ov = _overview(address='500 Atlantic Ave, Boston, MA 02210')

        def _fake_fetch(poi):
            # Deterministic geocoder stand-in: the Boston branch address.
            return poi, "42.3510, -71.0486", 0

        text = gtt._assemble_overview_tour_text(
            "WNDR Museum", "WNDR museum, Boston, MA", "museum", ov,
            coord_fetch=_fake_fetch)
        self.assertIsNotNone(text, "overview with a geocodable address must deliver")
        m = _COORD_RE.search(text)
        self.assertIsNotNone(m, "the overview stop must carry a Coordinates: line")
        lat, lng = float(m.group(1)), float(m.group(2))
        self.assertNotEqual((lat, lng), (0.0, 0.0))
        self.assertIn("Address: 500 Atlantic Ave", text)

    def test_clean_fail_when_no_coordinate_can_be_produced(self):
        ov = _overview(address='')

        def _no_coords(poi):
            return poi, "", 0        # geocoder cannot place it

        text = gtt._assemble_overview_tour_text(
            "Phantom Venue", "Phantom Venue, Nowhere", "museum", ov,
            coord_fetch=_no_coords)
        self.assertIsNone(
            text, "an overview that cannot be geocoded must clean-fail, not ship "
                  "a coordinate-less tour")

    def test_prebuilt_coordinates_are_used_without_geocoding(self):
        ov = _overview()
        ov.coordinates = "42.3510, -71.0486"
        calls = []

        def _should_not_be_called(poi):
            calls.append(poi)
            return poi, "", 0

        text = gtt._assemble_overview_tour_text(
            "WNDR Museum", "WNDR museum, Boston, MA", "museum", ov,
            coord_fetch=_should_not_be_called)
        self.assertIsNotNone(text)
        self.assertEqual(calls, [], "a prebuilt coordinate must not be re-geocoded")
        self.assertIn("Coordinates: 42.3510, -71.0486", text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
