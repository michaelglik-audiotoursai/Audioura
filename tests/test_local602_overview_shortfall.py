#!/usr/bin/env python3
"""test_local602_overview_shortfall.py — LOCAL-602 root cause #6 (D616).

A 1-stop "Overview" delivered for a 7-stop request is acceptable ONLY when the
honest D616 shortfall sentence appears (and the stop has real coordinates). This
pins the sentence onto the overview path, and its ABSENCE when the ask is met.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
from museum_overview import MuseumOverview


def _overview():
    return MuseumOverview(
        narration="WNDR Museum is an immersive art and technology experience. " * 8,
        sources=['https://www.wndrmuseum.com/boston'],
        address='500 Atlantic Ave, Boston, MA', coordinates='42.3510, -71.0486',
        as_of='October 2026',
    )


class TestOverviewShortfall(unittest.TestCase):

    def test_shortfall_sentence_present_for_7_stop_request(self):
        text = gtt._assemble_overview_tour_text(
            "WNDR Museum", "WNDR museum, Boston, MA", "museum", _overview(),
            requested_stops=7)
        self.assertIsNotNone(text)
        low = text.lower()
        self.assertIn("rather than the 7 you asked for", low,
                      "the D616 shortfall sentence must appear for a 7-stop ask")
        self.assertIn("1 stop", low)

    def test_no_shortfall_sentence_when_one_stop_was_asked(self):
        text = gtt._assemble_overview_tour_text(
            "WNDR Museum", "WNDR museum, Boston, MA", "museum", _overview(),
            requested_stops=1)
        self.assertIsNotNone(text)
        self.assertNotIn("you asked for", text.lower(),
                         "no shortfall sentence when the single stop meets the ask")

    def test_no_shortfall_sentence_when_requested_unknown(self):
        text = gtt._assemble_overview_tour_text(
            "WNDR Museum", "WNDR museum, Boston, MA", "museum", _overview(),
            requested_stops=None)
        self.assertIsNotNone(text)
        self.assertNotIn("you asked for", text.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
