#!/usr/bin/env python3
"""test_local520_cache_key_normalise.py — LOCAL-520 acceptance (unit level).

LOCAL-520 is the same defect class as LOCAL-500: two phrasings of one venue that
differ only by accents / punctuation / spacing must NOT mint two paid generations.
The string-normalisation fix lives in tour_cache_layer1._normalize_location, added
under LOCAL-500 (commit 1788205). This suite is the LOCAL-520 acceptance harness:
it CALLS the real cache-key functions (no source grep for a marker string —
D418/D421), and encodes every acceptance criterion from the LOCAL-520 ticket.

  1. The two Picasso rows from tour_cache produce the SAME key — real strings.
  2. A list of pairs that must NOT merge, each tested.
  3. Legacy (pre-normalisation) keys still resolve, so old cached rows are not
     orphaned (migration-by-fallback in get_cached_tour).

Goes red the instant the accent-fold / punctuation-strip normalisation is removed.
"""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_cache_layer1 as c


class TestPicassoPairMerges(unittest.TestCase):
    """Acceptance 1: the two real tour_cache rows collapse to one key."""

    # Exact strings from tour_cache, differing ONLY by accents.
    A = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
    B = "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"

    def test_accented_pair_produces_same_key(self):
        self.assertEqual(
            c._cache_key(self.A, "museum", 3),
            c._cache_key(self.B, "museum", 3),
            "Accent-only difference must collapse to one key",
        )

    def test_old_key_split_them(self):
        # The defect being fixed: the pre-LOCAL-500 key split these two.
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
    """Acceptance 2: genuinely different venues must stay distinct.

    Serving one listener another venue's tour is worse than paying twice, so the
    SAFE half deliberately stops at string normalisation — no fuzzy/coordinate
    identity.
    """

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
    """The classes of difference the ticket says must fold together."""

    def test_state_suffix_spacing(self):
        # 'Boston, MA' vs 'Boston MA' -> one form.
        self.assertEqual(
            c._cache_key("Boston, MA", "walking", 5),
            c._cache_key("Boston MA", "walking", 5),
        )

    def test_accent_comma_and_double_space_all_fold(self):
        variants = [
            "Musée Matisse, Nice",
            "Musee  Matisse , Nice",
            "musee matisse nice",
            "Musée Matisse. Nice",
        ]
        keys = {c._cache_key(v, "museum", 8) for v in variants}
        self.assertEqual(len(keys), 1, f"expected 1 key, got {keys}")


class TestLegacyFallbackKeyStable(unittest.TestCase):
    """Acceptance 3: old rows still resolve via the retained legacy key."""

    def test_legacy_key_matches_pre_local500_formula(self):
        loc, tt, n = "Some Place, MA", "museum", 4
        raw = f"{loc.strip().lower()}|{tt.strip().lower()}|{n}"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(c._legacy_cache_key(loc, tt, n), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
