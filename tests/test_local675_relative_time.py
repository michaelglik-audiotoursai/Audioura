"""LOCAL-675 item 2 — relative-time phrases must match the dates.

Boston 557 v12 said "Three years later, … In 1770" after a prior sentence dated
1742 — a 28-year gap, not three. The LOCAL-630 item 8 year-span check only
handled the digit form ("N years after/later"). This extends it to:
  * "<word-number> years later/after"   ("Three years later")
  * "a decade later / after"             (= 10 years)
  * "the following year" / "the next year" / "the year after" (= 1 year)
measured relative to the PREVIOUS dated sentence in the same stop. Each phrase is
recomputed from the dates, or dropped when the two anchor dates cannot be found.

Pure, offline. No network, no paid call.
"""
import unittest

import date_consistency_guard as dcg


class TestRelativeTimeSpans(unittest.TestCase):
    def test_boston557_three_years_later_corrected(self):
        # 1742 → 1770 is 28 years; "Three years later" is wrong.
        body = ("The regiment was founded in 1742. Three years later, in 1770, "
                "the city erupted in protest.")
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertNotIn("Three years later", out)
        self.assertIn("28 years later", out)

    def test_a_decade_later_corrected(self):
        # 1800 → 1823 is 23 years, not a decade.
        body = "The church opened in 1800. A decade later, in 1823, it was rebuilt."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertNotIn("decade", out.lower())
        self.assertIn("23 years later", out)

    def test_a_decade_later_within_tolerance_kept(self):
        # 1900 → 1910 is exactly 10 years → "a decade later" is right, keep it.
        body = "Built in 1900. A decade later, in 1910, it was expanded."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 0)
        self.assertEqual(rep["dropped"], 0)
        self.assertIn("A decade later", out)

    def test_following_year_correct_kept(self):
        # 1769 → 1770 is exactly one year → "the following year" is right.
        body = "He arrived in 1769. The following year, in 1770, he left."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 0)
        self.assertEqual(rep["dropped"], 0)
        self.assertIn("The following year", out)

    def test_following_year_wrong_corrected(self):
        # 1769 → 1774 is five years → "the following year" is wrong.
        body = "He arrived in 1769. The following year, in 1774, he left."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertNotIn("following year", out.lower())
        self.assertIn("5 years later", out)

    def test_year_after_phrase_matched(self):
        body = "Painted in 1900. The year after, in 1912, it toured."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertIn("12 years later", out)

    def test_unverifiable_relative_phrase_dropped(self):
        # The phrase sentence names no date of its own; only one anchor → drop,
        # and the sentence is left clean and capitalised.
        body = "Painted in 1888. Three years later it was praised."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["dropped"], 1)
        self.assertNotIn("Three years later", out)
        self.assertIn("It was praised.", out)

    def test_self_contained_sentence_anchors_in_sentence(self):
        # No previous dated sentence, but both anchors are present here.
        body = "The city changed in 1770, three years after 1742."
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertIn("28 years after", out)

    def test_relative_measured_from_previous_not_whole_body(self):
        # Three dated sentences; the phrase must anchor to the IMMEDIATELY
        # previous dated sentence (1820), not the earliest year in the body.
        body = ("Founded in 1700. Rebuilt in 1820. Three years later, in 1838, "
                "a tower was added.")
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        # 1838 - 1820 = 18, not 1838 - 1700 = 138.
        self.assertIn("18 years later", out)
        self.assertNotIn("138 years", out)

    def test_idempotent(self):
        body = ("The regiment was founded in 1742. Three years later, in 1770, "
                "the city erupted in protest.")
        once, _ = dcg.recompute_year_spans(body, context=body)
        twice, rep2 = dcg.recompute_year_spans(once, context=once)
        self.assertEqual(once, twice)
        self.assertEqual(rep2["corrected"], 0)
        self.assertEqual(rep2["dropped"], 0)

    def test_digit_form_still_works(self):
        # Regression: the original digit path (LOCAL-630 item 8) is unchanged.
        body = ("Velazquez painted it between 1647 and 1651. Nearly 247 years "
                "after it was painted, it was slashed in 1914.")
        out, rep = dcg.recompute_year_spans(body, context=body)
        self.assertEqual(rep["corrected"], 1)
        self.assertIn("267 years", out)

    def test_tour_level_per_stop(self):
        tour = (
            "Stop 1: A\n"
            "Founded in 1742. Three years later, in 1770, it grew.\n"
            "Stop 2: B\n"
            "Opened in 1900. A decade later, in 1910, expanded.\n"
        )
        out, rep = dcg.recompute_year_spans_in_tour(tour)
        self.assertIn("28 years later", out)        # Stop 1 corrected
        self.assertIn("A decade later", out)        # Stop 2 kept (exactly 10)
        self.assertEqual(rep["corrected"], 1)


if __name__ == "__main__":
    unittest.main()
