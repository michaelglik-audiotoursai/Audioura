#!/usr/bin/env python3
"""
LOCAL-494 — take total_stops out of the cache key (D581, step one).

Verifies the three moving parts of the bucketed cache, all as pure functions so
the suite needs no database:

  1. _stop_bucket / _cache_key   — a 4-stop and a 6-stop request for the same
     venue collapse onto ONE key; an 11+ request stays exact; a different venue
     or tour_type never collides.
  2. trim_tour_to_stops          — keeps stops 1..N in order, repairs the trailing
     seam (no hand-off to a trimmed stop), rewrites the closing recap to name only
     delivered stops, preserves Sources, and leaves an exact/undersized tour
     untouched.
  3. tour_quality.score_tour     — a tour trimmed 6→4 reports stops_delivered == 4
     and carries no `truncated` defect (acceptance criterion 3).

Acceptance criterion 2 — "no 'just ahead, the Crypt awaits' pointing at a stop
that was trimmed" — is the explicit `test_seam_does_not_name_trimmed_stop` below.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_cache_layer1 as cache
import tour_quality


VENUE = "Old North Church"

# A synthetic 6-stop museum tour in the exact shape the generator emits:
# title + Tour-Category, "Stop N:" blocks, deterministic transition templates
# (first "Continue through {venue} — next is", last "Your final stop in {venue}:"),
# then the closing recap ("From {first} to {last} ... That's N stops — ...") and
# a Sources line. Stop 6 is the "Crypt" — the acceptance-criterion trap: if the
# 4-stop trim still hands off to it, the seam is wrong.
def _make_six_stop_tour():
    return """Step-by-Step Audio Guided Tour: Old North Church, Boston, MA
Tour-Category: museum

Stop 1: The Steeple

Address: 193 Salem St, Boston, MA 02113

Coordinates: 42.3663, -71.0544

The steeple is where the lanterns were hung in 1775. Paul Revere arranged the signal here on the eve of the ride that warned the countryside.

Directions: Continue through Old North Church — next is The Bell Chamber.

Stop 2: The Bell Chamber

Address: 193 Salem St, Boston, MA 02113

The eight bells were cast in 1744 by Abel Rudhall of Gloucester, the oldest change-ringing bells in North America.

Directions: Next: The Box Pews.

Stop 3: The Box Pews

Address: 193 Salem St, Boston, MA 02113

The high box pews were owned by families who paid for their upkeep. Robert Newman's family pew sits near the front.

Directions: Proceed to The Organ.

Stop 4: The Organ

Address: 193 Salem St, Boston, MA 02113

The organ loft overlooks the nave. The instrument accompanied worship for generations of the congregation.

Directions: Continue to The Chandeliers.

Stop 5: The Chandeliers

Address: 193 Salem St, Boston, MA 02113

The brass chandeliers were donated in 1724 and are lit only on special occasions.

Directions: Your final stop in Old North Church: The Crypt.

Stop 6: The Crypt

Address: 193 Salem St, Boston, MA 02113

Beneath the church lie 37 tombs holding more than a thousand people, including Captain Samuel Nicholson.

From The Steeple to The Crypt, you have followed the thread of Signals and Silence. The church was built in 1723. That's 6 stops — The Steeple, where lanterns warned of the British, The Bell Chamber, home to America's oldest bells, and The Crypt, resting place of a thousand souls.

Sources: This tour draws on information from oldnorth.com and the Wikipedia article on the church.
"""


class TestStopBucket(unittest.TestCase):
    def test_bucket_edges(self):
        self.assertEqual(cache._stop_bucket(1), 3)
        self.assertEqual(cache._stop_bucket(3), 3)
        self.assertEqual(cache._stop_bucket(4), 6)
        self.assertEqual(cache._stop_bucket(6), 6)
        self.assertEqual(cache._stop_bucket(7), 10)
        self.assertEqual(cache._stop_bucket(10), 10)

    def test_eleven_plus_is_exact(self):
        self.assertEqual(cache._stop_bucket(11), 11)
        self.assertEqual(cache._stop_bucket(20), 20)


class TestCacheKeyBucketing(unittest.TestCase):
    def test_four_and_six_collide(self):
        """AC1: same venue at 4 and 6 stops → ONE key (one generation, one hit)."""
        k4 = cache._cache_key("Old North Church", "museum", 4)
        k6 = cache._cache_key("Old North Church", "museum", 6)
        self.assertEqual(k4, k6)

    def test_one_two_three_collide(self):
        keys = {cache._cache_key("X", "museum", n) for n in (1, 2, 3)}
        self.assertEqual(len(keys), 1)

    def test_seven_through_ten_collide(self):
        keys = {cache._cache_key("X", "museum", n) for n in (7, 8, 9, 10)}
        self.assertEqual(len(keys), 1)

    def test_eleven_plus_do_not_collide_with_bucket(self):
        self.assertNotEqual(cache._cache_key("X", "museum", 10),
                            cache._cache_key("X", "museum", 11))
        self.assertNotEqual(cache._cache_key("X", "museum", 11),
                            cache._cache_key("X", "museum", 12))

    def test_different_venue_or_type_never_collides(self):
        self.assertNotEqual(cache._cache_key("A", "museum", 4),
                            cache._cache_key("B", "museum", 4))
        self.assertNotEqual(cache._cache_key("A", "museum", 4),
                            cache._cache_key("A", "restaurant", 4))

    def test_key_normalizes_case_and_whitespace(self):
        self.assertEqual(cache._cache_key("  Old North Church ", "Museum", 4),
                         cache._cache_key("old north church", "museum", 6))


class TestTrimSeamRepair(unittest.TestCase):
    def setUp(self):
        self.tour = _make_six_stop_tour()
        self.trimmed = cache.trim_tour_to_stops(self.tour, 4)

    def _stop_names(self, text):
        return re.findall(r'^Stop \d+:\s*(.+)$', text, re.M)

    def test_keeps_first_n_stops_in_order(self):
        names = self._stop_names(self.trimmed)
        self.assertEqual(names, ["The Steeple", "The Bell Chamber",
                                 "The Box Pews", "The Organ"])

    def test_drops_trimmed_stops(self):
        self.assertNotIn("Stop 5:", self.trimmed)
        self.assertNotIn("Stop 6:", self.trimmed)

    def test_seam_does_not_name_trimmed_stop(self):
        """AC2 — the part most likely to be wrong.

        The 4-stop delivery must NOT hand off to The Chandeliers (stop 5) or
        The Crypt (stop 6). The last Directions line must be a clean terminal.
        """
        # No transition may name a trimmed stop.
        self.assertNotIn("The Chandeliers", self.trimmed)
        self.assertNotIn("The Crypt", self.trimmed)
        # The last Directions line is the generator's own final-stop form,
        # naming the delivered last stop.
        dirs = re.findall(r'^Directions:.*$', self.trimmed, re.M)
        self.assertTrue(dirs, "trimmed tour should still carry a Directions line")
        self.assertEqual(
            dirs[-1],
            f"Directions: Your final stop in {VENUE}: The Organ.",
        )

    def test_recap_names_only_delivered_stops(self):
        """AC2 — the closing recap must name only delivered stops."""
        self.assertIn("From The Steeple to The Organ, you have followed the thread",
                      self.trimmed)
        self.assertIn("That's 4 stops", self.trimmed)
        # The old endpoint and count are gone.
        self.assertNotIn("to The Crypt", self.trimmed)
        self.assertNotIn("That's 6 stops", self.trimmed)

    def test_sources_preserved(self):
        self.assertIn("Sources: This tour draws on information from oldnorth.com",
                      self.trimmed)

    def test_exact_match_unchanged(self):
        """AC4 — delivering the cached count (6) returns the tour verbatim."""
        self.assertEqual(cache.trim_tour_to_stops(self.tour, 6), self.tour)

    def test_undersized_request_unchanged(self):
        """A request larger than cached (should not happen for a bucket hit) is a no-op."""
        self.assertEqual(cache.trim_tour_to_stops(self.tour, 8), self.tour)


class TestTrimScoresClean(unittest.TestCase):
    def test_trimmed_tour_scores_clean(self):
        """AC3 — trimmed 6→4 reports stops_delivered == 4 and no `truncated`."""
        tour = _make_six_stop_tour()
        trimmed = cache.trim_tour_to_stops(tour, 4)
        result = tour_quality.score_tour(trimmed, requested_stops=4)
        self.assertEqual(result['metrics']['stops_delivered'], 4)
        self.assertNotIn('truncated', result['defects'])
        self.assertNotIn('thin', result['defects'])


class TestTrimRealCorpusTour(unittest.TestCase):
    """Exercise the trimmer on a real generated tour from the corpus."""

    FIXTURE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tours", "LOCAL262_asian_arts_8stop_restored.txt",
    )

    def test_asian_arts_8_to_4(self):
        if not os.path.exists(self.FIXTURE):
            self.skipTest("corpus fixture not present")
        text = open(self.FIXTURE, encoding='utf-8').read()
        trimmed = cache.trim_tour_to_stops(text, 4)
        names = re.findall(r'^Stop \d+:\s*(.+)$', trimmed, re.M)
        self.assertEqual(len(names), 4)
        # The real trimmed last stop is "Statue de Bouddha"; the trailing seam
        # must name it and nothing later.
        self.assertIn("Your final stop in", trimmed)
        self.assertIn("Statue de Bouddha", trimmed)
        self.assertNotIn("Stop 5:", trimmed)
        self.assertIn("Sources:", trimmed)
        result = tour_quality.score_tour(trimmed, requested_stops=4)
        self.assertEqual(result['metrics']['stops_delivered'], 4)
        self.assertNotIn('truncated', result['defects'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
