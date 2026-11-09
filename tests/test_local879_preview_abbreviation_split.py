#!/usr/bin/env python3
"""test_local879_preview_abbreviation_split.py — LOCAL-879 §2.

Tour 547's intro preview shipped a sentence cut at the abbreviation "U.S.":

    "…learn about the building that once served as the U.S. Your first stop is
     Cathedral."

The orientation-preview guards in ``orientation_pretell`` split sentences with a
bare ``re.split(r"(?<=[.!?])\\s+", …)``, which treats "U.S." as a sentence end.
The Stop-5 fact ("…served as the U.S. military's intelligence headquarters") was
cut after "U.S.", strip_later_stop_facts dropped the tail as a later-stop fact,
and the stub "…served as the U.S." shipped. The guards now use the shared
abbreviation-safe splitter (``sentence_split.split_sentences``), so the sentence
stays whole and is never left as a dangling "U.S.".

Run: python3 -m pytest tests/test_local879_preview_abbreviation_split.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orientation_pretell as op
from sentence_split import split_sentences

_PREVIEW_FACT = ("In the stops ahead, you will witness the laying of the first "
                 "stone on October 7, 1877, at Cathedral and learn about the "
                 "building that once served as the U.S. military's intelligence "
                 "headquarters.")


class TestSharedSplitterHandlesAbbreviations(unittest.TestCase):

    def test_us_is_not_a_sentence_boundary(self):
        self.assertEqual(len(split_sentences(_PREVIEW_FACT)), 1,
                         "'U.S.' must not split the preview sentence in two")

    def test_common_abbreviations(self):
        for abbr, sent in [
            ("U.S.", "It is the U.S. Army base."),
            ("U.K.", "He moved to the U.K. last year."),
            ("St.", "She prayed at St. Mary's church."),
            ("Dr.", "We met Dr. Lee at noon."),
            ("Mt.", "They climbed Mt. Fuji together."),
            ("Jr.", "That is Martin Luther King Jr. Boulevard."),
        ]:
            self.assertEqual(len(split_sentences(sent)), 1,
                             f"'{abbr}' wrongly split: {sent!r} -> "
                             f"{split_sentences(sent)}")


class TestPreviewNoDanglingAbbreviation(unittest.TestCase):
    """The exact tour-547 defect: no 'served as the U.S.' stub survives."""

    def setUp(self):
        self.prolog = (
            "Orientation: This tour stretches approximately 5 km. "
            + _PREVIEW_FACT + " Your first stop is Cathedral.")
        self.later_names = ["War Remnants Museum"]
        self.later_texts = [
            "It occupies a building that once served as the U.S. military's "
            "intelligence headquarters during the Vietnam War."]

    def test_strip_later_stop_facts_leaves_no_us_stub(self):
        cleaned, _ = op.strip_later_stop_facts(
            self.prolog, self.later_names, self.later_texts,
            "Cathedral", "The cathedral, first stone laid October 7, 1877.")
        self.assertNotIn("served as the U.S. Your first stop", cleaned)
        self.assertFalse(cleaned.rstrip().endswith("the U.S."),
                         f"preview must not end on a bare 'U.S.': {cleaned!r}")
        self.assertIn("Your first stop is Cathedral", cleaned)

    def test_phantom_name_guard_leaves_no_us_stub(self):
        cleaned, _ = op.strip_phantom_preview_names(
            self.prolog, ["Cathedral", "War Remnants Museum"],
            ["The cathedral.", self.later_texts[0]])
        self.assertFalse(cleaned.rstrip().endswith("the U.S."),
                         f"phantom guard must not leave a 'U.S.' stub: {cleaned!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
