#!/usr/bin/env python3
"""test_local879_foreign_date_normalize.py — LOCAL-879 §3.

Tour 547's Stop 4 shipped Vietnamese dates in English narration:

    "began on 1 tháng 7 năm 1962 and was completed on 31 tháng 10 năm 1966"

``foreign_date_normalize.normalize_foreign_dates`` renders a date written in the
SOURCE language (vi/fr/es/ru/zh) into the TOUR language (English) — "1 tháng 7
năm 1962" -> "1 July 1962" — both before the narrator and as a final pass. It is
deterministic, offline, idempotent, and leaves English prose untouched.

Run: python3 -m pytest tests/test_local879_foreign_date_normalize.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foreign_date_normalize import normalize_foreign_dates, contains_foreign_date


class TestVietnamese(unittest.TestCase):
    """The exact tour-547 Stop-4 defect."""

    def test_exact_stop4_sentence(self):
        s = ("construction began on 1 tháng 7 năm 1962 and was completed on "
             "31 tháng 10 năm 1966")
        out, n = normalize_foreign_dates(s)
        self.assertEqual(out,
                         "construction began on 1 July 1962 and was completed "
                         "on 31 October 1966")
        self.assertEqual(n, 2)
        self.assertNotIn("tháng", out)
        self.assertNotIn("năm", out)

    def test_month_year_only(self):
        self.assertEqual(normalize_foreign_dates("tháng 10 năm 1966")[0],
                         "October 1966")

    def test_bare_month(self):
        self.assertEqual(normalize_foreign_dates("vào tháng 7")[0], "vào July")

    def test_bare_year(self):
        self.assertEqual(normalize_foreign_dates("năm 1975")[0], "1975")


class TestOtherLanguages(unittest.TestCase):

    def test_french(self):
        self.assertEqual(
            normalize_foreign_dates("inauguré le 1er juillet 1962")[0],
            "inauguré le 1 July 1962")
        self.assertEqual(normalize_foreign_dates("en juillet 1962")[0],
                         "en July 1962")

    def test_spanish(self):
        self.assertEqual(
            normalize_foreign_dates("el 1 de julio de 1962")[0],
            "el 1 July 1962")

    def test_russian(self):
        self.assertEqual(
            normalize_foreign_dates("1 июля 1962 года")[0], "1 July 1962")

    def test_chinese(self):
        self.assertEqual(
            normalize_foreign_dates("1962年7月1日")[0], "1 July 1962")
        self.assertEqual(normalize_foreign_dates("1962年7月")[0], "July 1962")


class TestSafety(unittest.TestCase):

    def test_english_untouched(self):
        for s in ["Opened in July 1962.", "1 July 1962", "It cost $26.5 million.",
                  "The year 1966 was pivotal."]:
            out, n = normalize_foreign_dates(s)
            self.assertEqual(out, s, f"English prose changed: {s!r} -> {out!r}")
            self.assertEqual(n, 0)

    def test_idempotent(self):
        s = "began on 1 tháng 7 năm 1962"
        out1, _ = normalize_foreign_dates(s)
        out2, n2 = normalize_foreign_dates(out1)
        self.assertEqual(out1, out2)
        self.assertEqual(n2, 0)

    def test_non_english_target_is_noop(self):
        s = "1 tháng 7 năm 1962"
        self.assertEqual(normalize_foreign_dates(s, lang="vi"), (s, 0))

    def test_contains_foreign_date(self):
        self.assertTrue(contains_foreign_date("1 tháng 7 năm 1962"))
        self.assertTrue(contains_foreign_date("1962年7月1日"))
        self.assertFalse(contains_foreign_date("1 July 1962"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
