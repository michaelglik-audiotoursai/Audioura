#!/usr/bin/env python3
"""test_local591_contained_venue.py — LOCAL-591 Fix #1.

Field test (Michael's phone, tours 395/396): the request
    "Art and Architectual tour in Boston Athenaeum, boston, ma"
was turned into a city WALKING tour and then cut to 3 stops by the building's
walls. The log showed:

    [S15] venue_name='Boston Athenaeum' overridden — location contains explicit
          non-museum phrase
    [LOCAL-474] tour_type='' → category='walking'

The "explicit non-museum phrase" that fired was the THEME word "architectural".
But a theme word is not a different PLACE: "…tour IN/INSIDE/AT <named building>"
is a tour OF that building, whatever the theme ("art", "architecture",
"history"). It must be a contained-venue tour (museum/facility category, venue =
the building), not a city walking tour.

This suite proves:
  1. The non-museum phrase set is split into THEME words (architecture, art,
     history, literary, …) and ACTIVITY/mobility words (walking, food, bike, …).
  2. A theme word does NOT block the museum flip when the request names a tour
     INSIDE one building (interior preposition + a BUILDING-scope venue).
  3. The legitimate cases S15 was built for are preserved:
       - "architectural walking tour of Boston" stays walking (ACTIVITY word
         'walking tour' present).
       - "walking tour around Boston Athenaeum" is NOT 'inside' — 'around' is a
         perimeter/approach preposition, so it stays a city walking tour.
  4. The real S15 wiring in generate_tour_text.py consults the helper, so a
     revert of the wiring (not just a symbol rename) breaks a test.

D277/D307: at least one test reads the real generation path; the logic — not a
symbol — is what breaks on revert.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt


# The exact field request (verbatim, including the typo Michael typed).
ATHENAEUM = "Art and Architectual tour in Boston Athenaeum, boston, ma"
# A corrected spelling of the same request shape.
ATHENAEUM_FIXED = "Art and Architecture tour in Boston Athenaeum, Boston, MA"


def _building_intent(name="Boston Athenaeum", scope="Boston Athenaeum, Boston, Massachusetts"):
    """Intent as PHASE 1 returns it for a single-building request."""
    return {
        "venue_name": name,
        "geographic_scope": scope,
        "scope_precision": "BUILDING",
        "location": "Boston, Massachusetts",
        "poi_type": "",
        "named_places": [],
    }


class TestThemeVsActivitySplit(unittest.TestCase):
    """Fix #1 (1): the non-museum phrase set is split into theme vs activity."""

    def test_theme_and_activity_regexes_exist(self):
        self.assertTrue(hasattr(gtt, "_THEME_TOUR_RE"),
                        "generate_tour_text must expose _THEME_TOUR_RE")
        self.assertTrue(hasattr(gtt, "_ACTIVITY_NON_MUSEUM_TOUR_RE"),
                        "generate_tour_text must expose _ACTIVITY_NON_MUSEUM_TOUR_RE")

    def test_architecture_is_a_theme_not_an_activity(self):
        self.assertIsNotNone(gtt._THEME_TOUR_RE.search("architectural tour"))
        self.assertIsNotNone(gtt._THEME_TOUR_RE.search("architecture tour"))
        self.assertIsNotNone(gtt._THEME_TOUR_RE.search("history tour"))
        self.assertIsNotNone(gtt._THEME_TOUR_RE.search("art tour"))
        # These theme words are NOT mobility/activity words.
        self.assertIsNone(gtt._ACTIVITY_NON_MUSEUM_TOUR_RE.search("architectural tour"))
        self.assertIsNone(gtt._ACTIVITY_NON_MUSEUM_TOUR_RE.search("art tour"))

    def test_walking_and_food_are_activities(self):
        self.assertIsNotNone(gtt._ACTIVITY_NON_MUSEUM_TOUR_RE.search("walking tour"))
        self.assertIsNotNone(gtt._ACTIVITY_NON_MUSEUM_TOUR_RE.search("food tour"))
        self.assertIsNotNone(gtt._ACTIVITY_NON_MUSEUM_TOUR_RE.search("bike tour"))


class TestContainedVenueDetector(unittest.TestCase):
    """Fix #1 (2) + (3): the in/inside/at <building> detector."""

    def test_in_named_building_is_contained(self):
        self.assertTrue(gtt._is_contained_venue_request(ATHENAEUM, _building_intent()))
        self.assertTrue(gtt._is_contained_venue_request(ATHENAEUM_FIXED, _building_intent()))

    def test_inside_and_at_are_contained(self):
        self.assertTrue(gtt._is_contained_venue_request(
            "History tour inside Boston Athenaeum, Boston, MA", _building_intent()))
        self.assertTrue(gtt._is_contained_venue_request(
            "Art tour at Boston Athenaeum, Boston, MA", _building_intent()))

    def test_around_is_not_contained(self):
        # "walking tour around X" ≠ inside X — this is the perimeter case S15/D536
        # were built to respect. Even with a BUILDING-scope intent, 'around' must
        # not be read as 'inside'.
        self.assertFalse(gtt._is_contained_venue_request(
            "walking tour around Boston Athenaeum, Boston, MA", _building_intent()))

    def test_city_scope_is_not_contained(self):
        # A whole-city architectural tour is not a single-building tour.
        city_intent = {
            "venue_name": None,
            "geographic_scope": "Boston, MA",
            "scope_precision": "CITY",
            "location": "Boston, MA",
        }
        self.assertFalse(gtt._is_contained_venue_request(
            "Architectural tour of Boston, MA", city_intent))


class TestClassificationOutcome(unittest.TestCase):
    """Fix #1 end-to-end on the classifier seams (no network)."""

    def test_contained_venue_overrides_theme_word_block(self):
        """The whole point: a theme word must NOT force the Athenaeum to walking.

        _should_force_museum encapsulates the S15 decision. With a BUILDING-scope
        venue and an interior preposition, the theme word 'architectural' no
        longer blocks the museum flip.
        """
        self.assertTrue(
            gtt._should_force_museum(ATHENAEUM, "", _building_intent(),
                                     transport_mode="on_foot"),
            "contained-venue request with a theme word must force museum")

    def test_architectural_walking_tour_of_city_stays_non_museum(self):
        # ACTIVITY word 'walking tour' present AND no single building → not museum.
        city_intent = {
            "venue_name": None, "geographic_scope": "Boston, MA",
            "scope_precision": "CITY", "location": "Boston, MA",
        }
        self.assertFalse(
            gtt._should_force_museum("Architectural walking tour of Boston, MA", "",
                                     city_intent, transport_mode="on_foot"))

    def test_walking_tour_around_building_stays_non_museum(self):
        # 'around' is not 'inside'; a walking tour around the Athenaeum is a city
        # walking tour, not a contained-venue tour.
        self.assertFalse(
            gtt._should_force_museum("walking tour around Boston Athenaeum, Boston, MA",
                                     "", _building_intent(), transport_mode="on_foot"))


class TestRealWiring(unittest.TestCase):
    """Fix #1 (4): the real S15 block consults the helper (D307 revert guard)."""

    def test_s15_block_calls_should_force_museum(self):
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "generate_tour_text.py")
        with open(gen_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("_should_force_museum(", source,
                      "S15 block must call _should_force_museum (wiring, not a copy)")


class TestGenericThemeIsNotAnExhibition(unittest.TestCase):
    """[LOCAL-591] A theme word in `requirements` is not a named exhibition.

    The live run exposed a second layer of the same bug: PHASE 1 returned
    requirements='Art and Architectural tour' for the Athenaeum, and LOCAL-362
    read that as a scoped EXHIBITION request, searched the venue for an
    exhibition by that name, found none, and clean-failed — discarding the six
    documented works SPARQL had already returned. A generic theme must fall back
    to the venue's documented works, not an exhibition search.
    """

    def test_generic_theme_phrases_are_generic(self):
        for r in ["Art and Architectural tour", "art", "architecture",
                  "history", "general overview", "art and history tour",
                  "self-guided tour", "highlights of the collection"]:
            self.assertTrue(gtt._is_generic_theme_requirement(r),
                            f"{r!r} is a generic theme, not an exhibition")

    def test_named_exhibitions_and_artists_are_not_generic(self):
        for r in ["Picasso, Miró, Dalí: Unbound", "works by Chagall",
                  "Monet and the Impressionists exhibition", "the Degas retrospective"]:
            self.assertFalse(gtt._is_generic_theme_requirement(r),
                             f"{r!r} names an exhibition/artist — must stay scoped")

    def test_empty_requirement_is_not_generic_theme(self):
        # Empty is handled separately by the caller (no scope at all).
        self.assertFalse(gtt._is_generic_theme_requirement(""))
        self.assertFalse(gtt._is_generic_theme_requirement(None))

    def test_scope_detection_gated_on_generic_theme_in_source(self):
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "generate_tour_text.py")
        with open(gen_path, "r", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("_is_generic_theme_requirement(", source,
                      "exhibition-scope detection must consult the generic-theme guard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
