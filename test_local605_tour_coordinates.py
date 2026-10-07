#!/usr/bin/env python3
"""test_local605_tour_coordinates.py — LOCAL-605.

Every delivered tour must carry real tour-level coordinates, on EVERY delivery
path. generate_tour_text returns ``(None, None)`` for the pool fast-path, the
by-reference short-circuit (LOCAL-597) and the site-first/overview path
(LOCAL-582), and even for a cache hit; only the fresh path parsed Stop 1. The
service now resolves a real coordinate for all of them — the venue's own
coordinates for a contained venue (resolver P625 / D611 address) else Stop 1's
``Coordinates:`` line — and FAILS CLOSED when none resolves.

This suite proves the resolver returns a present ``(lat, lng)`` for each path,
stubbed and offline (no network, no DB): the venue lookup is monkeypatched, and
Stop-1 content is synthetic. It also proves the fail-closed sentinel: a tour with
no venue hit and no Stop-1 line resolves to ``(None, None)`` with source "none".

D307: a wiring test asserts the service calls resolve_tour_coordinates at the
completion choke point and fails closed on an unresolved coordinate.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tour_coordinates as tc


# A delivered contained-venue tour: Stop 1 leads with a Coordinates line.
_CONTAINED_CONTENT = """McMullen Museum of Art, Boston College - museum Tour

Stop 1: About the McMullen Museum of Art
Directions from entrance: Enter via the main lobby.
Coordinates: 42.3360, -71.1686
The McMullen Museum anchors Boston College's Brighton campus...

Stop 2: Carl Beam: The Columbus Suite
Coordinates: 42.3361, -71.1687
This show gathers...
"""

# A delivered outdoor tour: Stop 1 has a hemisphere-format coordinate.
_OUTDOOR_CONTENT = """Beacon Hill, Boston - walking Tour

Stop 1: Louisburg Square
Coordinates: 42.3589° N, 71.0637° W
A private square...

Stop 2: Acorn Street
Coordinates: 42.3584, -71.0704
The most photographed street...
"""

# A delivered tour whose text carries NO coordinate line at all.
_NO_COORD_CONTENT = """Somewhere - walking Tour

Stop 1: A Place
Just narration, no coordinate line.
"""


def _present(coord):
    return tc.coordinates_present(coord)


class _VenueStub:
    """Stand-in for a venue_resolver entity with P625 lat/lng."""
    def __init__(self, lat, lng, name="Stub Venue", url="https://example.org"):
        self.lat = lat
        self.lng = lng
        self.name = name
        self.official_url = url
        self.address = "123 Example St"


class TestEveryPathReturnsPresentCoordinates(unittest.TestCase):
    """lat/lng present in the resolved tuple, per delivery path (stubbed)."""

    def test_fresh_path_generator_coords_passthrough(self):
        # Fresh path: generator already parsed Stop 1 → coords arrive non-null.
        coord, source = tc.resolve_tour_coordinates(
            _OUTDOOR_CONTENT, "Beacon Hill, Boston", [42.3589, -71.0637],
            contained=False, path="fresh")
        self.assertTrue(_present(coord))
        self.assertEqual(source, "generator")
        self.assertAlmostEqual(coord[0], 42.3589, places=4)
        self.assertAlmostEqual(coord[1], -71.0637, places=4)

    def test_cache_path_stop1_fallback(self):
        # Cache hit: generator returns (None, None); Stop 1 carries the coordinate.
        coord, source = tc.resolve_tour_coordinates(
            _OUTDOOR_CONTENT, "Beacon Hill, Boston", (None, None),
            contained=False, path="cache")
        self.assertTrue(_present(coord))
        self.assertEqual(source, "stop1")

    def test_pool_path_stop1_fallback(self):
        # Stop-pool reuse: generator returns (None, None); Stop 1 (hemisphere) parsed.
        coord, source = tc.resolve_tour_coordinates(
            _OUTDOOR_CONTENT, "Beacon Hill, Boston", (None, None),
            contained=False, path="pool")
        self.assertTrue(_present(coord))
        self.assertEqual(source, "stop1")
        # Hemisphere W must be negated.
        self.assertLess(coord[1], 0)

    def test_by_reference_path_stop1_fallback(self):
        # By-reference (LOCAL-597): built from reused material, coords (None, None).
        coord, source = tc.resolve_tour_coordinates(
            _OUTDOOR_CONTENT, "Beacon Hill, Boston", (None, None),
            contained=False, path="by_reference")
        self.assertTrue(_present(coord))
        self.assertEqual(source, "stop1")

    def test_overview_path_stop1_fallback(self):
        # Overview (LOCAL-582): one orientation stop; its Coordinates line is used.
        coord, source = tc.resolve_tour_coordinates(
            _CONTAINED_CONTENT, "McMullen Museum of Art, Boston College",
            (None, None), contained=False, path="overview")
        self.assertTrue(_present(coord))
        self.assertEqual(source, "stop1")

    def test_contained_venue_prefers_venue_coordinates(self):
        # Contained venue: the venue's OWN coordinates (resolver P625) win over
        # Stop 1. Stub the resolver so there is no network.
        import venue_resolver
        _orig = venue_resolver.resolve_venue
        venue_resolver.resolve_venue = lambda name: _VenueStub(42.3350, -71.1680)
        try:
            coord, source = tc.resolve_tour_coordinates(
                _CONTAINED_CONTENT, "McMullen Museum of Art, Boston College",
                (None, None), contained=True, path="pool")
        finally:
            venue_resolver.resolve_venue = _orig
        self.assertTrue(_present(coord))
        self.assertEqual(source, "venue")
        self.assertAlmostEqual(coord[0], 42.3350, places=4)

    def test_contained_venue_falls_back_to_stop1_when_resolver_empty(self):
        # Contained venue whose resolver yields nothing usable: Stop 1 is the pin.
        import venue_resolver
        _orig = venue_resolver.resolve_venue
        venue_resolver.resolve_venue = lambda name: _VenueStub(0.0, 0.0)  # (0,0) = absent
        try:
            coord, source = tc.resolve_tour_coordinates(
                _CONTAINED_CONTENT, "McMullen Museum of Art, Boston College",
                (None, None), contained=True, path="pool")
        finally:
            venue_resolver.resolve_venue = _orig
        self.assertTrue(_present(coord))
        self.assertEqual(source, "stop1")


class TestFailClosedSentinel(unittest.TestCase):
    """A tour with no resolvable coordinate resolves to (None, None)/'none'."""

    def test_no_coordinate_anywhere_resolves_to_none(self):
        import venue_resolver
        _orig = venue_resolver.resolve_venue
        venue_resolver.resolve_venue = lambda name: _VenueStub(0.0, 0.0)
        try:
            coord, source = tc.resolve_tour_coordinates(
                _NO_COORD_CONTENT, "Somewhere", (None, None),
                contained=False, path="pool")
        finally:
            venue_resolver.resolve_venue = _orig
        self.assertFalse(_present(coord))
        self.assertEqual(source, "none")

    def test_zero_zero_is_absent(self):
        self.assertFalse(tc.coordinates_present((0, 0)))
        self.assertFalse(tc.coordinates_present((None, None)))
        self.assertFalse(tc.coordinates_present(None))
        self.assertFalse(tc.coordinates_present((91.0, 10.0)))  # out of range
        self.assertTrue(tc.coordinates_present((42.3, -71.1)))


class TestCoordinateParsers(unittest.TestCase):

    def test_decimal_pair(self):
        self.assertEqual(tc.parse_coordinates_text("42.364459, -71.055797"),
                         (42.364459, -71.055797))

    def test_hemisphere_pair_negates_s_and_w(self):
        lat, lng = tc.parse_coordinates_text("10.2231° N, 103.9600° E")
        self.assertAlmostEqual(lat, 10.2231)
        self.assertAlmostEqual(lng, 103.96)
        lat2, lng2 = tc.parse_coordinates_text("33.8688° S, 151.2093° W")
        self.assertLess(lat2, 0)
        self.assertLess(lng2, 0)

    def test_stop1_is_the_first_coordinates_line(self):
        self.assertEqual(tc.parse_stop1_coordinates(_CONTAINED_CONTENT),
                         (42.3360, -71.1686))

    def test_no_coordinate_line_returns_none(self):
        self.assertEqual(tc.parse_stop1_coordinates(_NO_COORD_CONTENT), (None, None))


class TestServiceWiring(unittest.TestCase):
    """D307: the service resolves coordinates at completion and fails closed."""

    def setUp(self):
        svc = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "generate_tour_text_service.py")
        with open(svc, "r", encoding="utf-8") as f:
            self.src = f.read()

    def test_service_calls_resolver(self):
        self.assertIn("resolve_tour_coordinates(", self.src)

    def test_service_fails_closed_with_error_code(self):
        self.assertIn("missing_tour_coordinates", self.src)
        self.assertIn("coordinate_path", self.src)

    def test_resolver_runs_before_completed_status(self):
        resolve_idx = self.src.find("resolve_tour_coordinates(")
        completed_idx = self.src.find('status="completed"', resolve_idx)
        self.assertGreater(resolve_idx, 0)
        self.assertGreater(completed_idx, resolve_idx,
                           "resolution must run BEFORE the job is marked completed")

    def test_delivery_path_recorded_in_generator(self):
        gen = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "generate_tour_text.py")
        with open(gen, "r", encoding="utf-8") as f:
            gsrc = f.read()
        for marker in ("_LAST_DELIVERY_PATH = 'pool'",
                       "_LAST_DELIVERY_PATH = 'by_reference'",
                       "_LAST_DELIVERY_PATH = 'cache'",
                       "_LAST_DELIVERY_PATH = 'overview'"):
            self.assertIn(marker, gsrc, f"missing delivery-path marker: {marker}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
