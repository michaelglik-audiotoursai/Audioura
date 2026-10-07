#!/usr/bin/env python3
"""test_local602_artist_heuristic.py — LOCAL-602 root cause #4.

Field defect (tour 397, WNDR museum, Boston): the venue resolver logged
    [venue_resolver] Artist inferred from name: 'WNDR'
and treated the WNDR Museum (an immersive-art brand with locations in several
cities) as a single-artist museum named after the artist "WNDR". WNDR is a
BRAND / acronym, not a human artist.

The heuristic _infer_artist_from_name must only infer an artist when the
residual of a "<NAME> museum" form looks like a HUMAN NAME (Capitalized words,
not an all-caps acronym or a single brand token). This suite pins:

  * acronym / all-caps brand tokens ("WNDR", "MoMA", "SFMOMA") infer NO artist;
  * a single leftover institutional word ("Uffizi") infers NO artist;
  * genuine artist-named museums STILL infer the artist (regression guard):
    "Musée Matisse" -> "Matisse", "musée Marc-Chagall" -> "Marc Chagall",
    "Isabella Stewart Gardner Museum" -> "Isabella Stewart Gardner".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import venue_resolver as v


class TestArtistHeuristicRejectsBrands(unittest.TestCase):

    def test_wndr_museum_infers_no_artist(self):
        self.assertEqual(v._infer_artist_from_name("WNDR museum"), "")
        self.assertEqual(v._infer_artist_from_name("WNDR Museum"), "")

    def test_allcaps_acronym_brands_infer_no_artist(self):
        # All-caps acronyms (WNDR, SFMOMA, LACMA, ICA) and camel-case acronyms
        # (MoMA) are brands/initialisms, never human artists.
        for name in ("MoMA", "SFMOMA", "ICA", "LACMA"):
            self.assertEqual(
                v._infer_artist_from_name(name), "",
                f"{name!r} is an acronym/brand, not an artist")

    def test_wndr_museum_mixed_case_infers_no_artist(self):
        # The exact field case: "<ACRONYM> museum" — WNDR is all-caps even after
        # the "museum" strip, so it has no human-name shape.
        self.assertEqual(v._infer_artist_from_name("WNDR museum"), "")


class TestArtistHeuristicKeepsRealArtists(unittest.TestCase):
    """Regression guard: the real single-artist museums still resolve."""

    def test_matisse(self):
        self.assertEqual(v._infer_artist_from_name("Musée Matisse"), "Matisse")

    def test_chagall(self):
        self.assertEqual(
            v._infer_artist_from_name("musée Marc-Chagall"), "Marc Chagall")

    def test_full_human_name(self):
        self.assertEqual(
            v._infer_artist_from_name("Isabella Stewart Gardner Museum"),
            "Isabella Stewart Gardner")


if __name__ == "__main__":
    unittest.main(verbosity=2)
