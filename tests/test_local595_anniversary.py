#!/usr/bin/env python3
"""test_local595_anniversary.py — LOCAL-595 anniversary arithmetic.

Pure, no database. Verifies:
  * payment date + 1 calendar month, clamped to the month's last day
  * Jan 31 -> Feb 28, and Feb 29 in a leap year
  * May 31 -> Jun 30; May 1 -> Jun 1; Michael's May 1 / Jun 1 / Jun 13 example
  * renewal_due is inclusive at the anniversary instant
  * the 3-day warning window

Run: python3 -m pytest tests/test_local595_anniversary.py -q
"""
import os
import sys
import unittest
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from subscription_levels import add_one_calendar_month, is_renewal_due, warn_renewal


class TestAddOneCalendarMonth(unittest.TestCase):
    def test_jan31_non_leap_clamps_to_feb28(self):
        self.assertEqual(date(2026, 2, 28), add_one_calendar_month(date(2026, 1, 31)))

    def test_jan31_leap_year_clamps_to_feb29(self):
        self.assertEqual(date(2024, 2, 29), add_one_calendar_month(date(2024, 1, 31)))

    def test_may31_clamps_to_jun30(self):
        self.assertEqual(date(2026, 6, 30), add_one_calendar_month(date(2026, 5, 31)))

    def test_may1_to_jun1(self):
        self.assertEqual(date(2026, 6, 1), add_one_calendar_month(date(2026, 5, 1)))

    def test_michael_jun1_to_jul1(self):
        # Michael's example: a May 1 payment renews Jun 1; a Jun 1 payment Jul 1.
        self.assertEqual(date(2026, 7, 1), add_one_calendar_month(date(2026, 6, 1)))

    def test_michael_jun13_to_jul13(self):
        self.assertEqual(date(2026, 7, 13), add_one_calendar_month(date(2026, 6, 13)))

    def test_december_rolls_year(self):
        self.assertEqual(date(2027, 1, 15), add_one_calendar_month(date(2026, 12, 15)))

    def test_jan30_leap_clamps_to_feb29(self):
        self.assertEqual(date(2024, 2, 29), add_one_calendar_month(date(2024, 1, 30)))

    def test_datetime_preserves_time_of_day(self):
        got = add_one_calendar_month(datetime(2026, 1, 31, 14, 30, 5))
        self.assertEqual(datetime(2026, 2, 28, 14, 30, 5), got)


class TestRenewalDue(unittest.TestCase):
    def test_due_exactly_at_anniversary_inclusive(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertTrue(is_renewal_due(ann, ann))

    def test_not_due_one_second_before(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertFalse(is_renewal_due(ann, ann - timedelta(seconds=1)))

    def test_due_after_anniversary(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertTrue(is_renewal_due(ann, ann + timedelta(days=5)))

    def test_none_anniversary_never_due(self):
        # A device that never bought a pack (L1/L2) has no anniversary.
        self.assertFalse(is_renewal_due(None, datetime(2026, 6, 1)))


class TestWarnRenewal(unittest.TestCase):
    def test_warn_within_three_days(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertTrue(warn_renewal(ann, ann - timedelta(days=2)))

    def test_warn_at_exactly_three_days(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertTrue(warn_renewal(ann, ann - timedelta(days=3)))

    def test_no_warn_four_days_before(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertFalse(warn_renewal(ann, ann - timedelta(days=4)))

    def test_no_warn_once_due(self):
        ann = datetime(2026, 6, 1, 12, 0, 0)
        self.assertFalse(warn_renewal(ann, ann))

    def test_none_anniversary_no_warn(self):
        self.assertFalse(warn_renewal(None, datetime(2026, 6, 1)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
