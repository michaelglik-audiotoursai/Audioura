#!/usr/bin/env python3
"""test_local591_one_scope_per_tour.py — LOCAL-591 Fix #2.

Field defect (tours 395/396): because the Athenaeum request was mis-classified
as a WALKING tour (Fix #1), the generator picked city-wide stops (MFA, Trinity,
BPL, Gardner, State House, Granary) and then scope-checked each of them against
the BUILDING scope 'Boston Athenaeum, Boston, Massachusetts'. Six were removed
for being "outside" the building. The scope checked did not match the tour: a
city walking tour's stops were judged against one building's walls.

The invariant: ONE SCOPE PER TOUR. The scope a tour is checked against must be
the tour's OWN extent —
  - a museum/facility (contained-venue) tour is validated by its venue guard, so
    _resolve_scope_for_check returns '' (no second, mismatched stop-by-stop
    scope);
  - a walking/biking tour is checked against the AREA the listener bounded it to
    (its own geographic_scope), never a tighter single building that is not the
    tour's declared extent.

_assert_one_scope_per_tour() encodes this, and _resolve_scope_for_check() runs it
on every scope it returns, so a mismatch can never again be handed to the
containment check.

Deterministic and offline — no network.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt


class TestOneScopePerTour(unittest.TestCase):

    def test_museum_building_tour_has_no_stopwise_scope(self):
        """A contained-venue (museum) tour uses its venue guard — the resolver
        returns '' so no second, different scope is ever checked."""
        intent = {
            "venue_name": "Boston Athenaeum",
            "geographic_scope": "Boston Athenaeum, Boston, Massachusetts",
            "scope_precision": "BUILDING",
            "location": "Boston, Massachusetts",
        }
        scope = gtt._resolve_scope_for_check(
            intent, "Art and Architecture tour in Boston Athenaeum, Boston, MA",
            tour_category="museum", museum_venue_name="Boston Athenaeum", quiet=True)
        self.assertEqual(scope, "",
                         "a museum building tour must not get a stop-by-stop scope here")

    def test_walking_tour_checked_against_its_own_area(self):
        """A walking tour bounded to a district is checked against THAT district."""
        intent = {
            "venue_name": None,
            "geographic_scope": "Beacon Hill, Boston, MA",
            "scope_precision": "DISTRICT",
            "location": "Boston, MA",
        }
        scope = gtt._resolve_scope_for_check(
            intent, "walking tour of Beacon Hill, Boston, MA",
            tour_category="walking", museum_venue_name="", quiet=True)
        self.assertEqual(scope, "Beacon Hill, Boston, MA")

    def test_city_walking_tour_has_no_building_scope(self):
        """A whole-city walking tour (scope_precision CITY) must NOT be checked
        against any single building — the resolver returns '' (too wide)."""
        intent = {
            "venue_name": None,
            "geographic_scope": "Boston, MA",
            "scope_precision": "CITY",
            "location": "Boston, MA",
        }
        scope = gtt._resolve_scope_for_check(
            intent, "walking tour of Boston, MA",
            tour_category="walking", museum_venue_name="", quiet=True)
        self.assertEqual(scope, "")


class TestInvariantHelper(unittest.TestCase):
    """_assert_one_scope_per_tour is the explicit invariant."""

    def test_helper_exists(self):
        self.assertTrue(hasattr(gtt, "_assert_one_scope_per_tour"))

    def test_building_scope_on_city_walking_tour_is_rejected(self):
        """The exact 395/396 defect: a walking tour whose declared extent is the
        whole city, handed a single-BUILDING scope, is a mismatch. The invariant
        rejects it (returns '' — no cross-scope check)."""
        intent = {
            "venue_name": None,
            "geographic_scope": "Boston, MA",       # the tour's own extent: a city
            "scope_precision": "CITY",
            "location": "Boston, MA",
        }
        # Someone tries to check city-wide stops against one building.
        out = gtt._assert_one_scope_per_tour(
            "walking", "Boston Athenaeum, Boston, Massachusetts", intent)
        self.assertEqual(out, "",
                         "a city walking tour must never be checked against one building")

    def test_matching_area_scope_passes_through(self):
        intent = {
            "venue_name": None,
            "geographic_scope": "Beacon Hill, Boston, MA",
            "scope_precision": "DISTRICT",
            "location": "Boston, MA",
        }
        out = gtt._assert_one_scope_per_tour(
            "walking", "Beacon Hill, Boston, MA", intent)
        self.assertEqual(out, "Beacon Hill, Boston, MA")

    def test_museum_tour_never_carries_a_stopwise_scope(self):
        intent = {
            "venue_name": "Boston Athenaeum",
            "geographic_scope": "Boston Athenaeum, Boston, Massachusetts",
            "scope_precision": "BUILDING",
            "location": "Boston, MA",
        }
        out = gtt._assert_one_scope_per_tour(
            "museum", "Boston Athenaeum, Boston, Massachusetts", intent)
        self.assertEqual(out, "",
                         "a museum tour's containment is its venue guard, not a stop-by-stop scope")


class TestWiring(unittest.TestCase):
    def test_resolver_runs_the_invariant(self):
        src = __import__("inspect").getsource(gtt._resolve_scope_for_check)
        self.assertIn("_assert_one_scope_per_tour(", src,
                      "_resolve_scope_for_check must run the one-scope-per-tour invariant")


if __name__ == "__main__":
    unittest.main(verbosity=2)
