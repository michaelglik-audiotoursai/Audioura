#!/usr/bin/env python3
"""test_local879_cross_stop_business_line.py — LOCAL-879 §1.

Tour 547 (wave 37) shipped Stop 10's (Thi Bar) opening-hours line under Stop 1
(Cathedral), right below the Coordinates field:

    Stop 1: Cathedral
    Coordinates: 10.779722, 106.699167
    The bar opens every day at 7pm and features live music from 10pm until late,
    except on Tuesdays when it is closed.
    Type/Specialty: Historical Landmark

A business/opening-hours line is bound to ONE venue — the stop whose venue it
describes. ``user_stop_verify.scrub_cross_stop_business_lines`` drops such a line
from any block whose venue it does not describe, and keeps it on the stop whose
Type/Specialty carries the subject kind (or whose name it states).

Run: python3 -m pytest tests/test_local879_cross_stop_business_line.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_stop_verify import (
    scrub_cross_stop_business_lines,
    _business_subject_kind,
)

_THI_HOURS = ("The bar opens every day at 7pm and features live music from 10pm "
              "until late, except on Tuesdays when it is closed.")

_TOUR_547 = f"""Step-by-step audio guided tour of Ho Chi Minh City, Vietnam, walking tour.

Stop 1: Cathedral
Coordinates: 10.779722, 106.699167
{_THI_HOURS}
Type/Specialty: Historical Landmark
Specific Examples: Stained glass windows, French colonial architecture
The cathedral before you was established in 1863 and completed in 1880.

Stop 10: Thi Bar
Coordinates: 10.767660, 106.693960
Type/Specialty: Gay bar
{_THI_HOURS}
You are standing outside Thi Bar, a cornerstone of the city's gay nightlife.
"""


class TestCrossStopBusinessLine(unittest.TestCase):

    def setUp(self):
        self.out, self.n = scrub_cross_stop_business_lines(_TOUR_547)
        # The two blocks, split at Stop 10.
        self.stop1 = self.out.split("Stop 10")[0]
        self.stop10 = "Stop 10" + self.out.split("Stop 10", 1)[1]

    def test_dropped_exactly_one(self):
        self.assertEqual(self.n, 1, f"should drop exactly the Stop-1 leak: {self.n}")

    def test_stop1_no_longer_carries_the_bar_hours(self):
        self.assertNotIn(_THI_HOURS, self.stop1,
                         "Thi Bar's hours must not appear under the Cathedral")
        self.assertNotIn("The bar opens every day at 7pm", self.stop1)

    def test_stop1_keeps_its_own_narration_and_fields(self):
        self.assertIn("Type/Specialty: Historical Landmark", self.stop1)
        self.assertIn("The cathedral before you was established in 1863",
                      self.stop1)
        self.assertIn("Coordinates: 10.779722, 106.699167", self.stop1)

    def test_stop10_keeps_its_own_hours(self):
        self.assertIn(_THI_HOURS, self.stop10,
                      "Thi Bar's own stop must keep its hours line")

    def test_idempotent(self):
        out2, n2 = scrub_cross_stop_business_lines(self.out)
        self.assertEqual(n2, 0, "second pass must be a no-op")
        self.assertEqual(out2, self.out)


class TestBusinessLineAttachesOnlyToItsOwnStop(unittest.TestCase):
    """The ticket's rule: a business line can only attach to its own stop."""

    def _run(self, kind, line):
        txt = (f"Stop 1: Somewhere\nType/Specialty: {kind}\n{line}\n"
               "It is a place on this route.\n")
        return scrub_cross_stop_business_lines(txt)

    def test_bar_hours_kept_under_a_bar(self):
        _out, n = self._run("Gay bar", _THI_HOURS)
        self.assertEqual(n, 0, "a bar's hours stay under a bar")

    def test_bar_hours_dropped_under_a_landmark(self):
        _out, n = self._run("Historical Landmark", _THI_HOURS)
        self.assertEqual(n, 1, "a bar's hours do not belong under a landmark")

    def test_cafe_hours_kept_under_a_coffee_shop(self):
        line = "The cafe opens daily from 8 am to 10 pm."
        _out, n = self._run("Coffee shop", line)
        self.assertEqual(n, 0)

    def test_cafe_hours_dropped_under_a_museum(self):
        line = "The cafe opens daily from 8 am to 10 pm."
        _out, n = self._run("Museum", line)
        self.assertEqual(n, 1)


class TestSubjectKind(unittest.TestCase):

    def test_bare_kind_subjects(self):
        self.assertEqual(_business_subject_kind("The bar opens at 7pm."), "bar")
        self.assertEqual(
            _business_subject_kind("The cafe is open from 8 am."), "cafe")

    def test_proper_name_subject_has_no_kind(self):
        self.assertEqual(
            _business_subject_kind("Longan welcomes guests nightly."), "")


class TestNonBusinessProseUntouched(unittest.TestCase):
    """A historical 'opened' sentence (not business hours) is never dropped."""

    def test_opera_opened_date_is_not_a_business_line(self):
        txt = ("Stop 6: Opera House\nType/Specialty: Cultural Venue\n"
               "This opera house opened its doors on January 1, 1900.\n")
        out, n = scrub_cross_stop_business_lines(txt)
        self.assertEqual(n, 0, "a historical opening DATE is not a business line")
        self.assertIn("opened its doors on January 1, 1900", out)


class TestRewordedRelocatedBarLine(unittest.TestCase):
    """The live tour-547 run (wave 37 re-run) relocated a REWORDED Thi Bar line
    into Stop 1's opening: 'It opens from 7pm until late and offers a happy hour
    every day. Inside, you find a vibrant atmosphere with live music starting at
    10pm.' Subject is 'It' (no venue-kind word) so the kind-subject rule misses
    it — the nightlife-cue rule catches it: a happy-hour / live-music / opens-at-
    Npm line in a non-hospitality (Historical Landmark) block is a leak."""

    def test_reworded_bar_line_dropped_from_landmark(self):
        txt = ("Stop 1: Notre-Dame Cathedral Basilica of Saigon\n"
               "Coordinates: 10.779785, 106.699020\n"
               "It opens from 7pm until late and offers a happy hour every day. "
               "Inside, you find a vibrant atmosphere with live music starting at "
               "10pm every night.\n"
               "Type/Specialty: Historical Landmark\n"
               "The cathedral was established in 1877.\n")
        out, n = scrub_cross_stop_business_lines(txt)
        self.assertEqual(n, 2)
        self.assertNotIn("happy hour", out)
        self.assertNotIn("live music", out)
        self.assertIn("The cathedral was established in 1877", out)

    def test_same_line_kept_under_a_bar(self):
        txt = ("Stop 10: Thi Bar\nType/Specialty: Gay bar\n"
               "It opens from 7pm until late and offers a happy hour every day. "
               "Inside, you find live music starting at 10pm.\n")
        out, n = scrub_cross_stop_business_lines(txt)
        self.assertEqual(n, 0, "a bar's own hours stay under the bar")
        self.assertIn("happy hour", out)



if __name__ == "__main__":
    unittest.main(verbosity=2)
