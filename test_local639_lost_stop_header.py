#!/usr/bin/env python3
"""test_local639_lost_stop_header.py — LOCAL-639 defect 1.

The live Uffizi tour (audio_tours id 488) delivered "That's 2 stops" and
stops_count=2 even though it HAS three stops. The Stop 3 header was not lost — it
was glued onto an EMPTY "Directions:" field label with no separating newline:

    …unfolds once more.\\n\\nDirections:Stop 3: Adamo ed Eva\\n\\nCoordinates: …

The stop-2→3 directions value came through empty, so a label-only "Directions:"
was emitted with no trailing newline and the next header was written straight
after it. Both existing guards missed it:

  * the LEAD empty-field sweep (``^(?:Address|Directions):[ \\t]*\\n``) only drops a
    label that is followed by a newline — here the label is followed by "Stop";
  * ``normalise_stop_headers`` only re-broke a header glued after sentence
    punctuation (``[.!?]``) — here the preceding char is a colon.

So the header slipped through, was never at line-start, and vanished from the
count. This test is grounded on the EXACT delivered 488 Stop-2→3 boundary.

Contract (binding):
  1. The defect text counts as 3 delivered stops after normalisation.
  2. The restored header "Stop 3: Adamo ed Eva" sits on its OWN line.
  3. The orphan empty "Directions:" label is gone (it had no value to speak).
  4. A real "Directions: <text>" hand-off before a header is UNTOUCHED.
  5. normalise_stop_headers is idempotent.

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local639_lost_stop_header.py -q
"""
import re
import unittest

import tour_conclusion as tc


# The exact delivered 488 boundary: Stop 2 narration ends, an EMPTY "Directions:"
# label is glued to the Stop 3 header, which is glued to its Coordinates line.
_UFFIZI_488_DEFECT = (
    "Step-by-Step Audio Guided Tour: Uffizi Gallery, Florence, Italy - Museum Tour\n\n"
    "Stop 1: Leda col cigno\n\n"
    "Coordinates: 43.7678, 11.255\n\n"
    "The panel known as Leda col cigno once belonged to the Spiridon collection.\n\n"
    "Directions: Continue through Uffizi Gallery — next is Adorazione dei Magi.\n\n"
    "Stop 2: Adorazione dei Magi\n\n"
    "Coordinates: 43.7678, 11.255\n\n"
    "In this painting, the centuries gather, and the transformation of the most "
    "human of stories unfolds once more.\n\n"
    "Directions:Stop 3: Adamo ed Eva\n\n"
    "Coordinates: 43.7678, 11.255\n\n"
    "The Uffizi, guardian to this double painting, now preserves both the risk he took.\n\n"
    "Together, these works illuminate the theme of transformation. That's 2 stops in all.\n\n"
    "Sources: This tour draws on information from www.uffizi.it.\n"
)

_LINE_START_HEADER = re.compile(r'^Stop (\d+):', re.M)


class TestLostStopHeaderRestored(unittest.TestCase):
    def setUp(self):
        self.fixed = tc.normalise_stop_headers(_UFFIZI_488_DEFECT)

    def test_defect_present_in_fixture(self):
        # Before the fix: only Stop 1 and Stop 2 are at line-start; Stop 3 is glued.
        self.assertEqual(_LINE_START_HEADER.findall(_UFFIZI_488_DEFECT), ["1", "2"])
        self.assertIn("Directions:Stop 3: Adamo ed Eva", _UFFIZI_488_DEFECT)

    def test_three_headers_after_fix(self):
        self.assertEqual(_LINE_START_HEADER.findall(self.fixed), ["1", "2", "3"])

    def test_count_delivered_is_three(self):
        self.assertEqual(tc.count_delivered_stops(_UFFIZI_488_DEFECT), 3)
        self.assertEqual(tc.count_delivered_stops(self.fixed), 3)

    def test_header_on_own_line(self):
        self.assertIn("\n\nStop 3: Adamo ed Eva\n\n", self.fixed)

    def test_orphan_empty_directions_label_dropped(self):
        self.assertNotIn("Directions:Stop 3", self.fixed)
        # No bare "Directions:" immediately before the restored header.
        self.assertNotRegex(self.fixed, r"(?m)^Directions:\s*$\n+Stop 3:")

    def test_real_directions_handoff_untouched(self):
        self.assertIn(
            "Directions: Continue through Uffizi Gallery — next is Adorazione dei Magi.",
            self.fixed)

    def test_narration_untouched(self):
        self.assertIn("the transformation of the most human of stories unfolds once more.",
                      self.fixed)
        self.assertIn("guardian to this double painting", self.fixed)

    def test_idempotent(self):
        twice = tc.normalise_stop_headers(self.fixed)
        self.assertEqual(twice, self.fixed)


class TestGluedAfterSentenceStillWorks(unittest.TestCase):
    """The pre-existing '…sentence.Stop N:' case (the Atelierwand defect) must
    still be re-broken — the new label case does not regress it."""

    _SENTENCE_GLUED = (
        "Stop 1: Atelierwand\n\n"
        "The artist painted the studio wall.\n\n"
        "Your final stop in A Museum: Atelierwand.Stop 2: Atelierwand\n\n"
        "A second view of the same wall.\n\n"
        "That's 2 stops in all.\n"
    )

    def test_sentence_glued_header_rebroken(self):
        fixed = tc.normalise_stop_headers(self._SENTENCE_GLUED)
        self.assertEqual(_LINE_START_HEADER.findall(fixed), ["1", "2"])
        self.assertEqual(tc.count_delivered_stops(self._SENTENCE_GLUED), 2)


class TestCleanTourUnchanged(unittest.TestCase):
    _CLEAN = (
        "Step-by-Step Audio Guided Tour: A Museum - Museum Tour\n\n"
        "Stop 1: Work One\n\n"
        "Narration one.\n\n"
        "Directions: Continue to Work Two.\n\n"
        "Stop 2: Work Two\n\n"
        "Narration two.\n\n"
        "That's 2 stops in all.\n"
    )

    def test_clean_unchanged(self):
        self.assertEqual(tc.normalise_stop_headers(self._CLEAN), self._CLEAN)
        self.assertEqual(tc.count_delivered_stops(self._CLEAN), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
