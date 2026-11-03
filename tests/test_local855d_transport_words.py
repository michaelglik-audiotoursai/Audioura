r"""
LOCAL-855D item 2 — a cycling tour must not describe the listener walking.
==========================================================================
Michael's delivered Sophia *cycling* tour contained walking words:

    "You might notice the vibrant street life as you walk."
    "… it is roughly 1.5 km (about a 19-minute walk) away."
    "… it is about a minute's walk away."
    "Acoustic Bar connects to your walk as a natural next step …"

Two fixes:
  * walking_directions_guard._approx_distance_phrase is transport-mode aware — on
    a bike tour it gives a distance / ride time, never "walk".
  * transport_word_guard.correct_transport_words rewrites a pedestrian movement
    word in the LLM body prose ("walk" -> "ride") on a wheeled tour, and is a
    no-op on a walking tour. It never touches "walkway/boardwalk/crosswalk".

These tests CALL the real functions (D418/D421). RED on base, GREEN with the fix.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import transport_word_guard as twg
from walking_directions_guard import (
    _approx_distance_phrase, _mode_from_text,
    ensure_walking_directions_lead_to_next,
)


class TestBikeDistancePhraseNeverWalks(unittest.TestCase):
    def test_short_hop_distance_only(self):
        p = _approx_distance_phrase(0.08, "bike")
        self.assertNotIn("walk", p.lower(), p)
        self.assertIn("meters", p)

    def test_long_leg_gives_ride_time_not_walk(self):
        p = _approx_distance_phrase(1.5, "bike")
        self.assertNotIn("walk", p.lower(), p)
        self.assertIn("ride", p.lower(), p)

    def test_walking_mode_unchanged(self):
        self.assertEqual(_approx_distance_phrase(0.08, "on_foot"),
                         "about a minute's walk away")
        self.assertIn("19-minute walk", _approx_distance_phrase(1.5, "on_foot"))

    def test_vehicle_mode_distance_only(self):
        p = _approx_distance_phrase(2.0, "vehicle")
        self.assertNotIn("walk", p.lower(), p)


class TestTransportWordGuard(unittest.TestCase):
    def test_body_walk_becomes_ride_on_bike(self):
        s = "You might notice the vibrant street life as you walk."
        out, n = twg.correct_transport_words(s, "bike")
        self.assertEqual(n, 1)
        self.assertNotIn("walk", out.lower())
        self.assertIn("as you ride", out)

    def test_your_walk_noun(self):
        s = "Acoustic Bar connects to your walk as a natural next step."
        out, n = twg.correct_transport_words(s, "bike")
        self.assertIn("your ride", out)
        self.assertNotIn("walk", out.lower())

    def test_stroll_rewritten(self):
        out, _ = twg.correct_transport_words("Take a short stroll here.", "bike")
        self.assertIn("ride", out.lower())
        self.assertNotIn("stroll", out.lower())

    def test_compound_words_untouched(self):
        s = "Use the crosswalk and the boardwalk; the walkway is lit."
        out, n = twg.correct_transport_words(s, "bike")
        self.assertEqual(n, 0, out)
        self.assertEqual(out, s)

    def test_capitalized_preserved(self):
        out, _ = twg.correct_transport_words("Walk north to the market.", "bike")
        self.assertTrue(out.startswith("Ride "), out)

    def test_walking_tour_is_noop(self):
        s = "You walk past the market and stroll onward."
        out, n = twg.correct_transport_words(s, "on_foot")
        self.assertEqual((out, n), (s, 0))


class TestModeDetectionFromHeader(unittest.TestCase):
    def test_cycling_header(self):
        h = ("Step-by-Step Audio Guided Tour: Ho Chi Minh City, Vietnam - "
             "Cycling Tour\n\nStop 1: X")
        self.assertEqual(_mode_from_text(h), "bike")

    def test_walking_header(self):
        self.assertEqual(
            _mode_from_text("Audio Guided Tour: Boston Walking Tour\nStop 1"),
            "on_foot")


class TestEndToEndBikeDirections(unittest.TestCase):
    def test_guard_produces_no_walk_phrase_on_bike_tour(self):
        tour = (
            "Step-by-Step Audio Guided Tour: Ho Chi Minh City - Cycling Tour\n\n"
            "Stop 1: Rambutan\n\nAddress: 15 Đ. Nguyễn Văn Tráng\n\n"
            "Coordinates: 10.7761, 106.6962\n\n"
            "Orientation: A quiet lobby.\n\n"
            "Directions: Head east.\n\n"
            "Stop 2: Longan\n\nAddress: 8 Đ. Lê Lợi\n\n"
            "Coordinates: 10.7791, 106.6996\n\n"
            "Orientation: A counter of dark wood.\n\n")
        fixed, rep = ensure_walking_directions_lead_to_next(
            tour, transport_mode="bike")
        self.assertNotIn("walk", fixed.lower(),
                         f"bike tour still contains a walk phrase: {fixed!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
