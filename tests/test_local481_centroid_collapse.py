#!/usr/bin/env python3
"""test_local481_centroid_collapse.py — LOCAL-481 Part 1 (centroid collapse).

These tests CALL geocode_stops.find_centroid_collapse / repair_centroid_collapse.
The resolver is INJECTED, so re-resolution is exercised deterministically with no
network and no key.

The bar:
  1. The tour-423 fixture (all four stops share lat 42.3656) is flagged; every
     stop is in the colliding set.
  2. Two artworks in one museum room are NOT flagged (category='museum' is exempt).
  3. repair_centroid_collapse sends colliding stops back through the resolver; a
     stop the resolver moves off the shared line is 'cured', one it cannot move is
     'still_colliding' — repair over deletion.
  4. Break-the-detector: with the collision precision coarsened away, the 423
     fixture passes through unflagged — proving the suite can go red.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geocode_stops as g  # noqa: E402


def pois(rows):
    return [{"name": n, "coordinates": f"{lat}, {lng}"} for n, lat, lng in rows]


# Tour 423, verbatim from the ticket. All four share latitude 42.3656.
TOUR_423 = pois([
    ("Boston Bruins Bar", 42.3656, -71.0188),
    ("Art Exhibits at Logan Airport", 42.3656, -71.0173),
    ("Boston Logan Airport Virtual Tour", 42.3656, -71.0096),
    ("Boston Logan Airport History Walk", 42.3656, -71.0189),
])

# Two artworks in one museum room: legitimately co-located.
MUSEUM_ROOM = pois([
    ("Mona Lisa", 48.8600, 2.3376),
    ("The Wedding at Cana", 48.8600, 2.3376),
])

# Four genuinely distinct stops along one district — no two share an axis to 4dp.
DISTINCT = pois([
    ("A", 43.7109, 7.2784),
    ("B", 43.7152, 7.2797),
    ("C", 43.7190, 7.2813),
    ("D", 43.7200, 7.2823),
])


class TestFind(unittest.TestCase):
    def test_423_all_four_flagged(self):
        rec = g.find_centroid_collapse(TOUR_423, category="facility")
        self.assertEqual(rec["action"], "collision", rec)
        self.assertEqual(rec["colliding_indices"], [0, 1, 2, 3], rec)
        self.assertTrue(any(grp["axis"] == "lat" and abs(grp["value"] - 42.3656) < 1e-9
                            for grp in rec["groups"]), rec)

    def test_museum_room_is_exempt(self):
        """AC3: two co-located artworks are not flagged for a museum tour."""
        rec = g.find_centroid_collapse(MUSEUM_ROOM, category="museum")
        self.assertEqual(rec["action"], "none", rec)
        self.assertEqual(rec["colliding_indices"], [], rec)

    def test_co_located_artworks_WOULD_collide_without_the_scope(self):
        """The scope is doing real work: the same two points collide when the
        category is one where stops are distinct destinations."""
        rec = g.find_centroid_collapse(MUSEUM_ROOM, category="walking")
        self.assertEqual(rec["action"], "collision", rec)

    def test_distinct_stops_are_clean(self):
        rec = g.find_centroid_collapse(DISTINCT, category="walking")
        self.assertEqual(rec["action"], "none", rec)

    def test_longitude_collision_is_caught_too(self):
        rows = pois([("A", 43.7109, 7.2800), ("B", 43.7152, 7.2800),
                     ("C", 43.7190, 7.2813)])
        rec = g.find_centroid_collapse(rows, category="walking")
        self.assertEqual(rec["action"], "collision", rec)
        self.assertEqual(rec["colliding_indices"], [0, 1], rec)


class TestRepair(unittest.TestCase):
    """The resolver is injected; no network."""

    def test_a_resolver_that_spreads_the_stops_cures_the_collision(self):
        """Every colliding stop is sent back and moved to a distinct point — all
        cured, none still colliding."""
        fresh = pois([
            ("Boston Bruins Bar", 42.3656, -71.0188),
            ("Art Exhibits at Logan Airport", 42.3656, -71.0173),
            ("Boston Logan Airport Virtual Tour", 42.3656, -71.0096),
        ])
        moved = {
            "Boston Bruins Bar": (42.3701, -71.0201),
            "Art Exhibits at Logan Airport": (42.3612, -71.0155),
            "Boston Logan Airport Virtual Tour": (42.3555, -71.0099),
        }

        def resolver(poi, tour_location, tour_anchor=None):
            pt = moved[poi["name"]]
            poi["coordinates"] = f"{pt[0]}, {pt[1]}"
            return {"confidence": "high", "action": "replaced"}

        rec = g.repair_centroid_collapse(fresh, "Boston, MA", category="facility",
                                         resolver=resolver)
        self.assertEqual(rec["action"], "collision", rec)
        self.assertEqual(sorted(rec["cured_indices"]), [0, 1, 2], rec)
        self.assertEqual(rec["still_colliding"], [], rec)

    def test_a_resolver_that_cannot_move_a_stop_leaves_it_still_colliding(self):
        """The 423 shape: the non-places have no real coordinate, so the resolver
        cannot move them — they stay on the shared line for the caller to drop."""
        fresh = pois([
            ("Boston Bruins Bar", 42.3656, -71.0188),
            ("Boston Logan Airport Virtual Tour", 42.3656, -71.0096),
            ("Boston Logan Airport History Walk", 42.3656, -71.0189),
        ])
        # Only the real place gets a new coordinate; the two formats are stuck.
        def resolver(poi, tour_location, tour_anchor=None):
            if poi["name"] == "Boston Bruins Bar":
                poi["coordinates"] = "42.3701, -71.0201"
                return {"confidence": "high", "action": "replaced"}
            return {"confidence": "low", "action": "kept"}

        rec = g.repair_centroid_collapse(fresh, "Boston, MA", category="facility",
                                         resolver=resolver)
        self.assertIn(0, rec["cured_indices"], rec)         # Bruins Bar cured
        self.assertEqual(sorted(rec["still_colliding"]), [1, 2], rec)

    def test_museum_repair_is_a_noop(self):
        calls = []

        def resolver(poi, tour_location, tour_anchor=None):
            calls.append(poi["name"])
            return {}

        rec = g.repair_centroid_collapse(list(MUSEUM_ROOM), "Paris",
                                         category="museum", resolver=resolver)
        self.assertEqual(rec["action"], "none", rec)
        self.assertEqual(calls, [], "a museum tour must not re-resolve co-located art")


class TestDetectorCanFail(unittest.TestCase):
    """AC5 (Part 1 half): with the detector disabled, the 423 fixture passes
    through UNFLAGGED; with it enabled, it is flagged. Same input, the knob
    decides — which is what proves the suite can go red."""

    def setUp(self):
        self._cats = g.COLLISION_CATEGORIES

    def tearDown(self):
        g.COLLISION_CATEGORIES = self._cats

    def test_disabled_detector_lets_423_through_unflagged(self):
        # Disable by removing 'facility' from the scoped set — the detector then
        # treats 423 like a museum and never looks. This is the real disable path
        # a regression would take (mis-scoping the check).
        g.COLLISION_CATEGORIES = set()
        disabled = g.find_centroid_collapse(TOUR_423, category="facility")
        self.assertEqual(disabled["action"], "none",
                         "with the detector disabled the 423 collapse must pass "
                         "through unflagged — the red state")

        # Re-enable: the very same fixture is now flagged. If this ever fails to
        # flip, the test can no longer distinguish fixed from broken.
        g.COLLISION_CATEGORIES = self._cats
        enabled = g.find_centroid_collapse(TOUR_423, category="facility")
        self.assertEqual(enabled["action"], "collision", enabled)
        self.assertEqual(enabled["colliding_indices"], [0, 1, 2, 3], enabled)


if __name__ == "__main__":
    unittest.main(verbosity=2)
