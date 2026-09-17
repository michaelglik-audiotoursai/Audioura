#!/usr/bin/env python3
"""test_local481_place_shape.py — LOCAL-481 Part 2 (a stop must be a place).

These tests CALL place_shape.classify_stop_name; they do not grep source for a
marker string (D418/D421). Deterministic, no network, no key.

The bar:
  1. The tour-423 fixture: 'Boston Bruins Bar' is a place; the other three
     ('Art Exhibits at Logan Airport', '…Virtual Tour', '…History Walk') are not.
  2. The approved Cimiez stop list (TOUR_CIMIEZ_WALKING_20260830.md) — Musée
     Matisse, Cimiez Monastery, and the rest — is NEVER flagged. Michael approved
     that tour; flagging any of its stops is a bounce.
  3. Conservative: singular proper names with prepositions (Museum of Modern Art,
     Cathedral of Notre-Dame) and named trails (Freedom Trail, Cliff Walk) survive.
  4. Break-the-detector: with the format/category rules neutralised, the three
     non-place names of 423 pass through as places — proving the suite can fail.
"""
import os
import sys
import unittest
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import place_shape as ps  # noqa: E402


# The tour-423 evidence, verbatim.
TOUR_423 = [
    ("Boston Bruins Bar", True, "place"),
    ("Art Exhibits at Logan Airport", False, "category"),
    ("Boston Logan Airport Virtual Tour", False, "format"),
    ("Boston Logan Airport History Walk", False, "format"),
]

# The approved Cimiez tour — every one must survive.
CIMIEZ_APPROVED = [
    "Matisse Museum", "Musée Matisse", "Cimiez Monastery", "Musée Marc Chagall",
    "Villa Leopolda", "Roman Ruins of Cemenelum", "Musée National du Sport",
]

# Proper singular names (some with prepositions) and named trails: NOT categories.
SURVIVORS = [
    "Arc de Triomphe", "Cathedral of Notre-Dame", "Museum of Modern Art",
    "Statue of Liberty", "Freedom Trail", "Cliff Walk", "Appalachian Trail",
    "Tower of London", "Palace of Versailles", "Church of the Gesù",
]

# Category labels: a genus + a containing place. NOT places.
CATEGORIES = [
    "Restaurants in Nice", "Museums of the Old Town", "Cafés around the Square",
    "Art Exhibits at Logan Airport", "Shops on the Waterfront",
    "Galleries in Chelsea",
]

# Formats: the tour's own medium named as a destination. NOT places.
FORMATS = [
    "Virtual Tour", "Audio Guide", "Self-Guided Tour", "History Walk",
    "Walking Tour", "Timeline", "Boston Logan Airport Virtual Tour",
    "Boston Logan Airport History Walk",
]


class TestTour423Fixture(unittest.TestCase):
    """AC1: Bruins Bar survives; the other three do not."""

    def test_each_423_name_classifies_as_expected(self):
        for name, is_place, shape in TOUR_423:
            res = ps.classify_stop_name(name)
            self.assertEqual(res["is_place"], is_place, f"{name!r} -> {res}")
            self.assertEqual(res["shape"], shape, f"{name!r} -> {res}")

    def test_bruins_bar_is_the_only_survivor(self):
        survivors = [n for n, _, _ in TOUR_423 if ps.is_a_place(n)]
        self.assertEqual(survivors, ["Boston Bruins Bar"],
                         f"exactly one of the four is a place: {survivors}")


class TestCimiezApprovedNotFlagged(unittest.TestCase):
    """AC2: the approved Cimiez list must never be flagged — a bounce otherwise."""

    def test_all_cimiez_stops_are_places(self):
        for enc in ("NFC", "NFD"):
            for name in CIMIEZ_APPROVED:
                n = unicodedata.normalize(enc, name)
                res = ps.classify_stop_name(n)
                self.assertTrue(res["is_place"],
                                f"{enc}: approved Cimiez stop {name!r} flagged: {res}")


class TestConservativeSurvivors(unittest.TestCase):
    """Singular proper names and named trails are not categories/formats."""

    def test_survivors_all_pass(self):
        for name in SURVIVORS:
            self.assertTrue(ps.is_a_place(name),
                            f"{name!r} was wrongly flagged as not-a-place")


class TestCategoryLabels(unittest.TestCase):
    def test_category_labels_are_rejected(self):
        for name in CATEGORIES:
            res = ps.classify_stop_name(name)
            self.assertFalse(res["is_place"], f"{name!r} -> {res}")
            self.assertEqual(res["shape"], "category", f"{name!r} -> {res}")


class TestFormats(unittest.TestCase):
    def test_formats_are_rejected(self):
        for name in FORMATS:
            res = ps.classify_stop_name(name)
            self.assertFalse(res["is_place"], f"{name!r} -> {res}")
            self.assertEqual(res["shape"], "format", f"{name!r} -> {res}")


class TestDetectorCanFail(unittest.TestCase):
    """AC5 (Part 2 half): the suite must be able to go red. Neutralise the two
    rules and the three 423 non-places pass through as places — the exact
    regression this file exists to catch."""

    def setUp(self):
        self._fmt = ps._FORMAT_HEADS
        self._std = ps._STANDALONE_NONPLACE
        self._cat = ps._CATEGORY_HEADS

    def tearDown(self):
        ps._FORMAT_HEADS = self._fmt
        ps._STANDALONE_NONPLACE = self._std
        ps._CATEGORY_HEADS = self._cat

    def test_disabling_the_rules_lets_423_nonplaces_through(self):
        ps._FORMAT_HEADS = set()
        ps._STANDALONE_NONPLACE = set()
        ps._CATEGORY_HEADS = set()
        broken = [n for n, _, _ in TOUR_423 if not ps.is_a_place(n)]
        self.assertEqual(broken, [],
                         "with the rules disabled a 423 non-place was STILL "
                         "flagged — the test can no longer distinguish fixed "
                         "from broken")


if __name__ == "__main__":
    unittest.main(verbosity=2)
