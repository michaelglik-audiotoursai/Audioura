#!/usr/bin/env python3
"""test_local638_practical_facts_opening.py — LOCAL-638 Note 1.

Michael listened to Frick tour 523 (D640):
    "Logical order is broken: it starts telling about the painting, then the museum
     information, how much it costs and when it is open, then goes back to the
     painting. Location, price, open hours should be part of the general
     description."

The composed practical-facts sentence (LOCAL-633) had landed INSIDE Stop 1's
Orientation paragraph. Practical facts must live in the OPENING general
description (the About sentences, before the first stop's Orientation) and NEVER
inside any stop's Orientation or narration.

Contract (binding test): after the deterministic final guarantee runs, there are
ZERO hours/price sentences at or after the first stop's first Orientation sentence
(``count_practical_facts_after_first_orientation`` is 0), and the moved facts are
present in the opening section.

Run: python3 -m pytest test_local638_practical_facts_opening.py -q
"""
import re
import unittest

import practical_facts_gate as pfg


# A delivered-text fixture reproducing the Frick 523 defect: the composed hours +
# admission sentence sits INSIDE Stop 1's Orientation paragraph, between the About
# story and the stop's own narration.
_FRICK_523_DEFECT = """Step-by-Step Audio Guided Tour: The Frick Collection - Museum Tour
Tour-Category: museum

Stop 1: Hans Holbein — Sir Thomas More

The Frick Collection is a museum housed in Henry Clay Frick's Gilded Age mansion on Fifth Avenue, dedicated to Old Master paintings.

Orientation: You are in the West Gallery. The Frick is open Tuesday to Sunday, and closed on Mondays. Admission is 22 dollars for adults. Look to the portrait on the north wall.

Holbein painted Sir Thomas More in 1527, when More was a rising statesman in the court of Henry the Eighth.

Directions: Walk south into the Living Hall to find your next stop.

Stop 2: Giovanni Bellini — St. Francis in the Desert

Orientation: You are now in the Living Hall. Bellini's panel hangs opposite the fireplace.

Bellini shows St. Francis stepping out of his cell into the morning light.

Directions: Continue into the Oval Room for your final stop.

Stop 3: Jean-Honoré Fragonard — The Progress of Love

Orientation: You are in the Fragonard Room.

These panels were painted for Madame du Barry.

That's 3 stops on this tour of The Frick Collection.
"""


class TestDetectorFindsTheDefect(unittest.TestCase):
    def test_defect_is_detected_before_the_fix(self):
        # The fixture has hours AND admission inside Stop 1's Orientation → counted.
        n = pfg.count_practical_facts_after_first_orientation(_FRICK_523_DEFECT)
        self.assertGreaterEqual(n, 2,
                                "fixture must reproduce the 523 defect (facts after first Orientation)")


class TestRelocationGuarantee(unittest.TestCase):
    def setUp(self):
        self.fixed, self.n_moved = pfg.relocate_practical_facts_to_opening(
            _FRICK_523_DEFECT)

    def test_moved_at_least_the_two_sentences(self):
        self.assertGreaterEqual(self.n_moved, 2)

    def test_zero_practical_facts_after_first_orientation(self):
        # The binding Note-1 contract.
        self.assertEqual(
            pfg.count_practical_facts_after_first_orientation(self.fixed), 0)

    def test_facts_now_in_opening_before_first_orientation(self):
        opening = self.fixed.split("Orientation:")[0]
        low = opening.lower()
        self.assertIn("open tuesday to sunday", low)
        self.assertIn("22 dollars", low)

    def test_orientation_keeps_its_own_non_practical_content(self):
        # The Orientation's real guidance survives; only the facts were pulled.
        stop1 = self.fixed.split("Stop 2:")[0]
        self.assertIn("West Gallery", stop1)
        self.assertIn("north wall", stop1)

    def test_narration_and_directions_untouched(self):
        self.assertIn("Holbein painted Sir Thomas More in 1527", self.fixed)
        self.assertIn("Walk south into the Living Hall", self.fixed)

    def test_idempotent(self):
        twice, n2 = pfg.relocate_practical_facts_to_opening(self.fixed)
        self.assertEqual(n2, 0)
        self.assertEqual(twice, self.fixed)

    def test_no_fact_invented_or_dropped(self):
        # Every practical sentence that was present is still present somewhere.
        self.assertIn("open Tuesday to Sunday", self.fixed)
        self.assertIn("22 dollars", self.fixed)


class TestCleanTourUnchanged(unittest.TestCase):
    """A tour that already has its facts in the opening section is a no-op."""

    _CLEAN = """Step-by-Step Audio Guided Tour: The Frick Collection - Museum Tour
Tour-Category: museum

Stop 1: Hans Holbein — Sir Thomas More

The Frick Collection is Henry Clay Frick's mansion museum. The Frick is open Tuesday to Sunday, and closed on Mondays. Admission is 22 dollars for adults.

Orientation: You are in the West Gallery. Look to the portrait on the north wall.

Holbein painted Sir Thomas More in 1527.

Directions: Walk south into the Living Hall.

Stop 2: Giovanni Bellini — St. Francis

Orientation: You are in the Living Hall.

Bellini shows St. Francis in the morning light.

That's 2 stops on this tour.
"""

    def test_clean_tour_has_zero_after_orientation(self):
        self.assertEqual(
            pfg.count_practical_facts_after_first_orientation(self._CLEAN), 0)

    def test_clean_tour_is_unchanged(self):
        fixed, n = pfg.relocate_practical_facts_to_opening(self._CLEAN)
        self.assertEqual(n, 0)
        self.assertEqual(fixed, self._CLEAN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
