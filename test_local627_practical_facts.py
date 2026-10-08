#!/usr/bin/env python3
"""test_local627_practical_facts.py — LOCAL-627 defect 2.

Tour 488 spoke the practical facts twice — once in Museum Information, again inside
Stop 1's Orientation as a RAW fare table ("admission is Single ticket purchased on
the day of entry: €25. Single ticket reserved… Reduced ticket…"). Practical facts
must be spoken ONCE, as at most two short sentences. And the Prado said "Opening
hours weren't published" though the Prado publishes hours — the preflight failed;
we must say NOTHING rather than that false sentence.

Run: python3 -m pytest test_local627_practical_facts.py -q
"""
import unittest

import practical_facts_gate as pfg


RAW_FARE = ("Welcome to the gallery. admission is Single ticket purchased on the "
            "day of entry: €25. Single ticket reserved online: €29. Reduced "
            "ticket: €2. (Discounts exist for various groups). The collection is "
            "magnificent.")


class TestCollapseFareTable(unittest.TestCase):
    def test_raw_fare_table_collapsed_to_one_sentence(self):
        out, n = pfg.collapse_fare_table(RAW_FARE)
        self.assertGreaterEqual(n, 1)
        self.assertIn("A ticket is €25.", out)
        # The downstream ticket lines are gone.
        self.assertNotIn("reserved online", out)
        self.assertNotIn("Reduced ticket", out)
        # Surrounding prose survives.
        self.assertIn("Welcome to the gallery.", out)
        self.assertIn("The collection is magnificent.", out)

    def test_clean_admission_sentence_untouched(self):
        clean = "A ticket is 25 euros; under-18s go free."
        out, n = pfg.collapse_fare_table(clean)
        self.assertEqual(n, 0)
        self.assertEqual(out, clean)

    def test_no_price_text_untouched(self):
        s = "The Uffizi is open Tuesday to Sunday."
        out, n = pfg.collapse_fare_table(s)
        self.assertEqual(n, 0)


class TestHoursGenuinelyAbsent(unittest.TestCase):
    HONEST = "Opening hours weren't published where we could read them."

    def _museum_text(self):
        return ("Stop 1: The Venus of Urbino\n\n"
                "Orientation: You are at the Prado museum.\n\n"
                "Titian painted this in 1538.")

    def test_says_nothing_when_preflight_not_confirmed(self):
        out, inserted = pfg.ensure_unpublished_hours_line(
            self._museum_text(), hours_genuinely_absent=False)
        self.assertFalse(inserted)
        self.assertNotIn(self.HONEST, out)

    def test_says_honest_line_when_genuinely_absent(self):
        out, inserted = pfg.ensure_unpublished_hours_line(
            self._museum_text(), hours_genuinely_absent=True)
        self.assertTrue(inserted)
        self.assertIn(self.HONEST, out)

    def test_default_preserves_local618_contract(self):
        # Default True = the original LOCAL-618 behaviour (insert once).
        out, inserted = pfg.ensure_unpublished_hours_line(self._museum_text())
        self.assertTrue(inserted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
