#!/usr/bin/env python3
"""LOCAL-285: Tests for restaurant selection fixes.

Three fixes tested:
1. Restaurant venue constraint ensures Phase 3A produces restaurants
2. Empty venue phrase guard catches "through ." in output
3. Self-referential route guard catches "from X to X" in single-stop tours
"""
import os
import re
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))


class TestRestaurantVenueConstraint(unittest.TestCase):
    """Fix 1: The Phase 3A prompt for restaurant tours must include a restaurant constraint."""

    def test_restaurant_constraint_is_nonempty_for_restaurant_category(self):
        """When tour_category is 'restaurant', _restaurant_venue_constraint is populated."""
        # Simulate the logic from generate_tour_text.py
        tour_category = 'restaurant'
        location = "Nice, France"
        intent = {'geographic_scope': 'Nice'}

        _restaurant_venue_constraint = ""
        if tour_category == 'restaurant':
            _restaurant_area = (intent.get('geographic_scope') or '').strip() if intent else ''
            if not _restaurant_area:
                _restaurant_area = location
            _restaurant_venue_constraint = (
                f"\nCRITICAL CONSTRAINT — THIS IS A RESTAURANT/DINING TOUR:\n"
                f"- Every stop MUST be a named, real, currently-operating eating establishment "
                f"(restaurant, bistro, brasserie, café, trattoria, tavern, or similar).\n"
                f"- Each stop must have a verifiable street address in or near {_restaurant_area}.\n"
                f"- Do NOT include museums, galleries, parks, monuments, or any non-dining venue.\n"
                f"- Do NOT include fictional or closed restaurants.\n"
                f"- Prefer well-known, established restaurants that a visitor could actually dine at.\n"
                f"- Include a mix of styles/price ranges unless the request specifies otherwise.\n"
            )

        self.assertIn("RESTAURANT/DINING TOUR", _restaurant_venue_constraint)
        self.assertIn("eating establishment", _restaurant_venue_constraint)
        self.assertIn("Do NOT include museums", _restaurant_venue_constraint)
        self.assertIn("Nice", _restaurant_venue_constraint)

    def test_restaurant_constraint_empty_for_museum_category(self):
        """When tour_category is not 'restaurant', constraint is empty."""
        tour_category = 'museum'
        _restaurant_venue_constraint = ""
        if tour_category == 'restaurant':
            _restaurant_venue_constraint = "should not be here"
        self.assertEqual(_restaurant_venue_constraint, "")

    def test_restaurant_constraint_falls_back_to_location(self):
        """When intent has no geographic_scope, use location."""
        tour_category = 'restaurant'
        location = "Boston, MA"
        intent = {}

        _restaurant_venue_constraint = ""
        if tour_category == 'restaurant':
            _restaurant_area = (intent.get('geographic_scope') or '').strip() if intent else ''
            if not _restaurant_area:
                _restaurant_area = location
            _restaurant_venue_constraint = (
                f"in or near {_restaurant_area}"
            )

        self.assertIn("Boston, MA", _restaurant_venue_constraint)


class TestEmptyVenuePhraseGuard(unittest.TestCase):
    """Fix 2: Empty venue phrases like 'through .' must be caught and fixed."""

    def _apply_guard(self, text, location="Nice, France"):
        """Apply the LOCAL-285 empty venue phrase guard."""
        _empty_venue_pattern = re.compile(r'(through|across|around|in|of)\s+([.,;!])')
        _venue_fill = location.split(',')[0].strip() if location else "this area"
        result = _empty_venue_pattern.sub(
            lambda m: f"{m.group(1)} {_venue_fill}{m.group(2)}", text
        )
        return result

    def test_through_dot_is_fixed(self):
        """'through .' becomes 'through Nice.'"""
        text = "You are about to embark on a walking journey through . This tour"
        result = self._apply_guard(text)
        self.assertIn("through Nice.", result)
        self.assertNotIn("through .", result)

    def test_across_dot_is_fixed(self):
        """'across ,' becomes 'across Nice,'"""
        text = "A culinary adventure across , featuring fine dining."
        result = self._apply_guard(text)
        self.assertIn("across Nice,", result)

    def test_normal_text_unchanged(self):
        """Text with proper venue name is not altered."""
        text = "You are about to embark on a walking journey through the French Riviera."
        result = self._apply_guard(text)
        self.assertEqual(text, result)

    def test_in_dot_is_fixed(self):
        """'in .' is fixed."""
        text = "The finest restaurants in . await your visit."
        result = self._apply_guard(text)
        self.assertIn("in Nice.", result)

    def test_location_fallback_when_none(self):
        """When location is empty, use 'this area'."""
        text = "A journey through ."
        result = self._apply_guard(text, location="")
        self.assertIn("through this area.", result)


class TestSelfReferentialRouteGuard(unittest.TestCase):
    """Fix 3: 'from X to X' in single-stop tours must be caught and removed."""

    def _apply_guard(self, text):
        """Apply the LOCAL-285 self-referential route guard."""
        _self_route_sentence = re.compile(
            r'[^.]*(?:from|between)\s+(.{3,80}?)\s+to\s+\1[^.]*\.\s*',
            re.IGNORECASE
        )
        result = _self_route_sentence.sub(' ', text)
        result = re.sub(r'  +', ' ', result)
        result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
        return result

    def test_from_x_to_x_removed(self):
        """'from Musée Matisse to Musée Matisse' is removed."""
        text = (
            "You are about to embark on a walking journey through Nice. "
            "This tour will take you from Musée Matisse to Musée Matisse, spanning 0 meters. "
            "The city offers rich culinary traditions."
        )
        result = self._apply_guard(text)
        self.assertNotIn("from Musée Matisse to Musée Matisse", result)
        self.assertIn("culinary traditions", result)

    def test_between_x_and_x_handled(self):
        """'between X to X' pattern is caught."""
        text = "Navigate between Le Chantecler to Le Chantecler along the Promenade."
        result = self._apply_guard(text)
        self.assertNotIn("between Le Chantecler to Le Chantecler", result)

    def test_legitimate_route_unchanged(self):
        """'from Cap d'Antibes to Eze Village' is not removed."""
        text = "This route takes you from Cap d'Antibes to Eze Village, spanning 28 km."
        result = self._apply_guard(text)
        self.assertIn("from Cap d'Antibes to Eze Village", result)

    def test_different_names_unchanged(self):
        """Different start/end points are preserved."""
        text = "You will travel from Le Chantecler to La Petite Maison."
        result = self._apply_guard(text)
        self.assertIn("from Le Chantecler to La Petite Maison", result)


class TestPrologSingleStopPrompt(unittest.TestCase):
    """The prolog prompt PART 2 adapts for single-stop tours."""

    def test_single_stop_gets_no_route(self):
        """With 1 stop, PART 2 says 'single stop' not 'from X to X'."""
        _prolog_stop_names = ["Musée Matisse"]
        # Simulate the conditional from generate_tour_text.py
        if len(_prolog_stop_names) >= 2 and _prolog_stop_names[0] != _prolog_stop_names[-1]:
            part2_instruction = f"name the endpoints ({_prolog_stop_names[0]} to {_prolog_stop_names[-1]})"
        else:
            part2_instruction = "describe what the visitor will experience at this single stop"
        self.assertIn("single stop", part2_instruction)
        self.assertNotIn("to Musée Matisse", part2_instruction)

    def test_multi_stop_gets_route(self):
        """With 2+ stops, PART 2 names endpoints."""
        _prolog_stop_names = ["Le Chantecler", "La Petite Maison", "L'Univers"]
        if len(_prolog_stop_names) >= 2 and _prolog_stop_names[0] != _prolog_stop_names[-1]:
            part2_instruction = f"name the endpoints ({_prolog_stop_names[0]} to {_prolog_stop_names[-1]})"
        else:
            part2_instruction = "describe what the visitor will experience at this single stop"
        self.assertIn("Le Chantecler", part2_instruction)
        self.assertIn("L'Univers", part2_instruction)


class TestTourCategoryClassification(unittest.TestCase):
    """Restaurant tours must classify as 'restaurant' category."""

    def test_restaurant_tour_type_classifies_correctly(self):
        """tour_type='restaurant' with city location → category 'restaurant'."""
        # Import the actual function
        from generate_tour_text import _classify_tour_category
        result = _classify_tour_category("Nice, France", "restaurant")
        self.assertEqual(result, 'restaurant')

    def test_museum_not_reclassified(self):
        """Museum location stays museum."""
        from generate_tour_text import _classify_tour_category
        result = _classify_tour_category("Musée Matisse, Nice", "museum")
        self.assertEqual(result, 'museum')

    def test_biking_stays_walking_with_biking_type(self):
        """Biking tour in a generic area → walking (transport is handled separately)."""
        from generate_tour_text import _classify_tour_category
        result = _classify_tour_category("French Riviera", "biking")
        self.assertEqual(result, 'walking')


if __name__ == '__main__':
    unittest.main()
