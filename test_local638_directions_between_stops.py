#!/usr/bin/env python3
"""test_local638_directions_between_stops.py — LOCAL-638 Note 4.

Michael listened to Frick tour 523 (D640):
    "The story stops abruptly and has no directions to the next exhibit."
In 523, Stop 2 had no "Your final stop…" transition before Stop 3.

Contract (binding test): after the deterministic final guarantee runs, every stop
except the last ends with a transition to the next stop
(``count_stops_missing_directions`` is 0), the last stop is never given one, and a
tour that already has all its hand-offs is unchanged.

Run: python3 -m pytest test_local638_directions_between_stops.py -q
"""
import re
import unittest

import directions_guarantee as dg


# Frick 523 defect: Stop 1 hands off, Stop 2 does NOT (ends abruptly), Stop 3 is
# the last stop and correctly has no transition.
_FRICK_523_DEFECT = """Step-by-step audio guided tour of The Frick Collection, museum tour.

Stop 1: Sir Thomas More

Holbein painted Sir Thomas More in 1527, when More was a rising statesman.

Continue through The Frick Collection — next is St. Francis in the Desert.

Stop 2: St. Francis in the Desert

Bellini shows St. Francis stepping out of his cell into the morning light. The panel has drawn visitors for centuries.

Stop 3: The Progress of Love

These Fragonard panels were painted for Madame du Barry.

That's 3 stops in all.
"""


class TestDetectorFindsMissingHandoff(unittest.TestCase):
    def test_defect_detected(self):
        n = dg.count_stops_missing_directions(_FRICK_523_DEFECT, "The Frick Collection")
        self.assertEqual(n, 1, "Stop 2 must be flagged as missing its hand-off")


class TestGuarantee(unittest.TestCase):
    def setUp(self):
        self.fixed, self.n_added = dg.ensure_directions_between_stops(
            _FRICK_523_DEFECT, "The Frick Collection")

    def test_added_one(self):
        self.assertEqual(self.n_added, 1)

    def test_zero_missing_after(self):
        self.assertEqual(
            dg.count_stops_missing_directions(self.fixed, "The Frick Collection"), 0)

    def test_stop2_now_hands_off_to_stop3(self):
        stop2 = self.fixed.split("Stop 2:")[1].split("Stop 3:")[0]
        # Penultimate stop → "Your final stop in <venue>: <next>."
        self.assertRegex(stop2, r"(?i)your final stop in The Frick Collection: The Progress of Love")

    def test_last_stop_gets_no_transition(self):
        stop3 = self.fixed.split("Stop 3:")[1]
        # Nothing after The Progress of Love narration pointing to a 4th stop.
        self.assertNotRegex(stop3, r"(?i)continue to|your final stop")

    def test_existing_stop1_handoff_preserved(self):
        self.assertIn("Continue through The Frick Collection — next is "
                      "St. Francis in the Desert.", self.fixed)

    def test_narration_untouched(self):
        self.assertIn("Bellini shows St. Francis stepping out of his cell", self.fixed)
        self.assertIn("Madame du Barry", self.fixed)

    def test_conclusion_untouched(self):
        self.assertIn("That's 3 stops in all.", self.fixed)

    def test_idempotent(self):
        twice, n2 = dg.ensure_directions_between_stops(self.fixed, "The Frick Collection")
        self.assertEqual(n2, 0)
        self.assertEqual(twice, self.fixed)


class TestCleanTourUnchanged(unittest.TestCase):
    _CLEAN = """Step-by-step audio guided tour of The Frick Collection, museum tour.

Stop 1: Sir Thomas More

Holbein painted Sir Thomas More in 1527.

Continue to St. Francis in the Desert.

Stop 2: St. Francis in the Desert

Bellini shows St. Francis in the morning light.

Your final stop in The Frick Collection: The Progress of Love.

Stop 3: The Progress of Love

Fragonard panels painted for Madame du Barry.

That's 3 stops in all.
"""

    def test_zero_missing(self):
        self.assertEqual(
            dg.count_stops_missing_directions(self._CLEAN, "The Frick Collection"), 0)

    def test_unchanged(self):
        fixed, n = dg.ensure_directions_between_stops(self._CLEAN, "The Frick Collection")
        self.assertEqual(n, 0)
        self.assertEqual(fixed, self._CLEAN)


class TestDirectionsLabelCounts(unittest.TestCase):
    """A 'Directions:'-labelled line (the field-label render path) also counts as a
    present hand-off."""

    _LABELLED = """Step-by-step audio guided tour of A Museum, museum tour.

Stop 1: Work One

Narration one.

Directions: Continue to Work Two.

Stop 2: Work Two

Narration two.

That's 2 stops in all.
"""

    def test_labelled_directions_counts(self):
        self.assertEqual(dg.count_stops_missing_directions(self._LABELLED, "A Museum"), 0)
        fixed, n = dg.ensure_directions_between_stops(self._LABELLED, "A Museum")
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
