#!/usr/bin/env python3
"""test_local743_stop_header_split.py — LOCAL-743.

The live "episode 1 of season 1 biking tour, Salem, MA" (audio_tours id 716, job
ad5f966f) requested 5 stops. The generator reported
``[LOCAL-394] Stop count invariant: OK (5 selected == 5 delivered)``, yet the
shipped ZIP had audio_1..4 only and the orchestrator logged
``STOP COUNT MISMATCH: requested 5 stops, delivered 4`` (stops_count=4). Stop 1
(Salem Maritime National Historic Site) had NO audio.

Root cause: the model wrote Stop 1's header as a SENTENCE —

    Stop 1 is the Salem Maritime National Historic Site.

— while stops 2–5 used "Stop N: <name>". The live modernized splitter
(tour_generation_modernized.parse_tour_content_to_modernized) and the stop
counter (tour_conclusion.count_delivered_stops) both key on "Stop N:" (colon), so
the sentence form was never a header: the split folded it into the pre-stop title
part and dropped it, so only 4 stops reached TTS and stop 1 lost its audio.

A second live defect: stop 1's Directions line swallowed the NEXT stop's
"Type/Specialty:" / "Specific Examples:" fields onto one physical line, so those
structural labels could reach the spoken text (a synthesiser would read
"Type/Specialty:" aloud).

Fix (deterministic, offline):
  1. tour_conclusion.normalize_heading_variants rewrites "Stop N is the X." /
     "Stop N is X" / "Stop N - X" (and en/em dash) → "Stop N: X".
  2. normalise_stop_headers calls it first, so count_delivered_stops and the
     generator's final-text guard see the colon header.
  3. The modernized splitter normalises the same variants before its split.
  4. The field-line invariant now re-breaks Type/Specialty and Specific Examples
     too, and find_leaked_field_labels asserts spoken text carries no mid-line
     structural label.

Red today: the raw fixture splits into 4 stops. Green after the fix: 5.

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local743_stop_header_split.py -q
"""
import os
import re
import unittest

import tour_conclusion as tc
import tour_generation_modernized as tgm


_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "tour716_stop1_sentence_header.txt")

with open(_FIXTURE, "r", encoding="utf-8") as _f:
    _TOUR_716 = _f.read()

_LINE_START_HEADER = re.compile(r'^Stop (\d+):', re.M)


class TestTour716SplitsIntoFiveStops(unittest.TestCase):
    """The headline red→green: 5 stops written, 4 delivered today."""

    def test_defect_present_in_raw_fixture(self):
        # Stop 1 is a sentence, not a "Stop 1:" header — only 2..5 are at line-start.
        self.assertIn("Stop 1 is the Salem Maritime National Historic Site.", _TOUR_716)
        self.assertEqual(_LINE_START_HEADER.findall(_TOUR_716), ["2", "3", "4", "5"])

    def test_raw_fixture_counts_four_stops_before_normalisation(self):
        # The exact defect: the colon-form counter/splitter see 4, not 5.
        raw_headers = len(re.findall(r'^Stop \d+:', _TOUR_716, re.M))
        self.assertEqual(raw_headers, 4)

    def test_count_delivered_is_five_after_fix(self):
        self.assertEqual(tc.count_delivered_stops(_TOUR_716), 5)

    def test_modernized_splitter_yields_five_stops(self):
        parsed = tgm.parse_tour_content_to_modernized(_TOUR_716)
        self.assertEqual(len(parsed["text_content"]), 5)

    def test_stop_one_is_salem_maritime_in_split(self):
        parsed = tgm.parse_tour_content_to_modernized(_TOUR_716)
        first = parsed["text_content"][0]
        # The splitter strips the "Stop N:" prefix, so each stop's content begins
        # with its title. Stop 1 is now a real stop whose title is Salem Maritime
        # (not folded into the pre-stop title part and dropped).
        self.assertTrue(first.lstrip().startswith("Salem Maritime National Historic Site"),
                        first[:60])
        # The sentence form must not survive anywhere in stop 1's content.
        self.assertNotIn("Stop 1 is the", first)

    def test_normalised_stop1_is_colon_header(self):
        fixed = tc.normalise_stop_headers(_TOUR_716)
        self.assertEqual(_LINE_START_HEADER.findall(fixed), ["1", "2", "3", "4", "5"])
        self.assertIn("Stop 1: Salem Maritime National Historic Site", fixed)
        self.assertNotIn("Stop 1 is the Salem Maritime", fixed)


class TestHeadingVariants(unittest.TestCase):
    """Each connective form the model might write normalises to "Stop N: X"."""

    def test_is_the(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 1 is the Old State House."),
            "Stop 1: Old State House")

    def test_is(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 2 is Faneuil Hall."),
            "Stop 2: Faneuil Hall")

    def test_hyphen(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 3 - Paul Revere House"),
            "Stop 3: Paul Revere House")

    def test_en_dash(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 4 \u2013 Old North Church"),
            "Stop 4: Old North Church")

    def test_em_dash(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 5 \u2014 Bunker Hill Monument"),
            "Stop 5: Bunker Hill Monument")

    def test_multi_digit(self):
        self.assertEqual(
            tc.normalize_heading_variants("Stop 10 is the Last Place."),
            "Stop 10: Last Place")

    def test_colon_form_untouched(self):
        s = "Stop 1: Salem Maritime National Historic Site"
        self.assertEqual(tc.normalize_heading_variants(s), s)

    def test_overview_em_dash_title_untouched(self):
        # The orientation overview header "Stop 1: X — Overview" (colon form, with
        # an em dash INSIDE the title) must be left exactly as-is.
        s = "Stop 1: Salem Maritime \u2014 Overview"
        self.assertEqual(tc.normalize_heading_variants(s), s)

    def test_interior_punctuation_preserved(self):
        # A real title with interior punctuation keeps it; only ONE trailing
        # terminator is dropped.
        self.assertEqual(
            tc.normalize_heading_variants("Stop 2 is the No. 14 Gallery."),
            "Stop 2: No. 14 Gallery")

    def test_idempotent(self):
        once = tc.normalize_heading_variants(_TOUR_716)
        self.assertEqual(tc.normalize_heading_variants(once), once)

    def test_body_sentence_not_at_line_start_untouched(self):
        # A "Stop N is" reference MID-sentence (not line-start) is NOT a header
        # and must be left alone.
        s = "The next stop is the highlight of the ride."
        self.assertEqual(tc.normalize_heading_variants(s), s)


class TestFieldLabelLeak(unittest.TestCase):
    """The Directions line must never carry another stop's field labels, and the
    spoken text must contain no mid-line structural label."""

    def test_raw_fixture_has_leak(self):
        self.assertNotEqual(tc.find_leaked_field_labels(_TOUR_716), [])

    def test_leak_cleared_after_normalisation(self):
        fixed = tc.normalise_stop_headers(_TOUR_716)
        self.assertEqual(tc.find_leaked_field_labels(fixed), [])

    def test_labels_on_own_lines_after_fix(self):
        fixed = tc.normalise_stop_headers(_TOUR_716)
        # Every Type/Specialty and Specific Examples label now starts a line.
        for label in ("Type/Specialty:", "Specific Examples:", "Coordinates:"):
            for m in re.finditer(re.escape(label), fixed):
                start = m.start()
                # The char before the label is a newline (line-start) — never a space.
                self.assertTrue(start == 0 or fixed[start - 1] == "\n",
                                f"{label} not at line-start near {fixed[start-20:start+20]!r}")

    def test_detector_finds_each_leak_label(self):
        sample = ("Directions: Go north. Coordinates: 1,2 "
                  "Type/Specialty: X Specific Examples: Y.")
        leaks = tc.find_leaked_field_labels(sample)
        self.assertIn("Coordinates:", leaks)
        self.assertIn("Type/Specialty:", leaks)
        self.assertIn("Specific Examples:", leaks)

    def test_clean_text_has_no_leak(self):
        clean = ("Stop 1: A\n\nNarration.\n\nDirections: Go north.\n\n"
                 "Coordinates: 1,2\n\nStop 2: B\n\nNarration two.\n")
        self.assertEqual(tc.find_leaked_field_labels(clean), [])


class TestExistingSplitUnaffected(unittest.TestCase):
    """A clean colon-form tour splits and counts exactly as before."""

    _CLEAN = (
        "Step-by-Step Audio Guided Tour: A Town - Biking Tour\n"
        "Tour-Category: biking\n\n"
        "Stop 1: Work One\n\nCoordinates: 1,2\n\nNarration one.\n\n"
        "Directions: Continue to Work Two.\n\n"
        "Stop 2: Work Two\n\nNarration two.\n\n"
        "That's 2 stops in all.\n"
    )

    def test_clean_counts_two(self):
        self.assertEqual(tc.count_delivered_stops(self._CLEAN), 2)

    def test_clean_splitter_two(self):
        parsed = tgm.parse_tour_content_to_modernized(self._CLEAN)
        self.assertEqual(len(parsed["text_content"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
