#!/usr/bin/env python3
"""test_local500_cache_key_normalise.py — LOCAL-500 acceptance (unit level).

These tests CALL the real cache-key functions in tour_cache_layer1; they do not
grep source for a marker string (D418/D421). No DB, no network.

The bar for LOCAL-500 (the SAFE half only — string normalisation, NOT coordinate
or fuzzy/semantic venue identity):

  1. Two phrasings of one venue differing only by accents produce the SAME key —
     proven with the real Picasso strings from the ticket.
  2. Genuinely different venues must NOT merge — each pair tested.
  3. Legacy (pre-normalisation) keys still resolve via _legacy_cache_key so old
     cached rows are not orphaned.

This suite goes red the moment the accent-fold / punctuation-strip normalisation
is removed from _normalize_location.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_cache_layer1 as c


class TestPicassoPairMerges(unittest.TestCase):
    # The exact strings from tour_cache, differing only by accents.
    A = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
    B = "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"

    def test_accented_pair_produces_same_key(self):
        self.assertEqual(
            c._cache_key(self.A, "museum", 3),
            c._cache_key(self.B, "museum", 3),
            "Accent-only difference must collapse to one key",
        )

    def test_they_differed_under_the_old_key(self):
        # Sanity: this is the defect we are fixing — old key split them.
        self.assertNotEqual(
            c._legacy_cache_key(self.A, "museum", 3),
            c._legacy_cache_key(self.B, "museum", 3),
        )

    def test_normalised_form_is_accent_free(self):
        norm = c._normalize_location(self.B)
        self.assertNotIn("ó", norm)
        self.assertNotIn("í", norm)
        self.assertEqual(norm, c._normalize_location(self.A))


class TestDifferentVenuesDoNotMerge(unittest.TestCase):
    PAIRS = [
        ("Musee Matisse, Nice", "Musee Marc Chagall, Nice"),
        ("Boston Logan International Airport", "Boston Common"),
        ("Sacred Heart Parish, Newton", "Our Lady Help of Christians, Newton"),
    ]

    def test_pairs_stay_distinct(self):
        for x, y in self.PAIRS:
            self.assertNotEqual(
                c._cache_key(x, "walking", 5),
                c._cache_key(y, "walking", 5),
                f"MUST NOT merge different venues: {x!r} vs {y!r}",
            )


class TestSafeNormalisationEquivalences(unittest.TestCase):
    def test_state_suffix_spacing(self):
        self.assertEqual(
            c._cache_key("Boston, MA", "walking", 5),
            c._cache_key("Boston MA", "walking", 5),
        )

    def test_double_space_and_trailing_punct(self):
        variants = [
            "Musée Matisse, Nice",
            "Musee  Matisse , Nice",
            "musee matisse nice",
            "Musée Matisse. Nice",
        ]
        keys = {c._cache_key(v, "museum", 8) for v in variants}
        self.assertEqual(len(keys), 1, f"expected 1 key, got {keys}")


class TestLegacyFallbackKeyStable(unittest.TestCase):
    def test_legacy_key_matches_old_formula(self):
        import hashlib

        loc, tt, n = "Some Place, MA", "museum", 4
        raw = f"{loc.strip().lower()}|{tt.strip().lower()}|{n}"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(c._legacy_cache_key(loc, tt, n), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
