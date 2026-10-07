"""
test_local615_paragraph_dedupe.py — [LOCAL-615 item 1]
======================================================

D626 calibration batch (tours 403 Lyon, 405 Bilbao): Stop 1's whole orientation
paragraph was printed TWICE, verbatim — the D611 opening fold plus the generator's
own orientation body both emitted it on the FRESH path.

These tests pin the deterministic fix:
  * paragraph_dedupe.dedupe_paragraphs removes the second verbatim copy, keeps the
    first, and is idempotent.
  * paragraph_dedupe.find_duplicate_paragraphs reports the duplicate (the detector
    content_qa_runner's "No duplicated paragraph" check uses).
  * content_qa_runner's "No duplicated paragraph" check FAILs on the raw 405 Stop 1
    and PASSes after the dedupe pass.
  * Structural repeats (Address:, Coordinates:) across stops are NOT flagged.

The fixture is the real duplicated Stop-1 orientation paragraph from tour_405
(Bilbao); the duplication is the exact 403/405 shape (one labelled "Orientation:"
copy, one bare copy).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paragraph_dedupe import (
    dedupe_paragraphs,
    find_duplicate_paragraphs,
    MIN_PARAGRAPH_CHARS,
)

# The verbatim orientation body duplicated in tour_405 Stop 1 (D626).
_ORIENT_405 = (
    'You are about to explore the Museo de Bellas Artes de Bilbao in Bilbao. '
    'Encounter "El sacrificio de Isaac" by Pedro Orrente, the "Portrait of Martin '
    'Zapater" by Francisco de Goya, "El beso de la reliquia" by Joaquin Sorolla, '
    '"La Venus de la poesia" by Julio Romero de Torres, and "Retrato del poeta '
    'Moratin" by Francisco Goya. The museum\'s origin merges collections, shaping '
    'it as a space deemed essential in modern society. Your first stop is El '
    'sacrificio de Isaac. The moment you step close enough to see the grain of the '
    'canvas in "El sacrificio de Isaac," you stand directly before a work that '
    'bridges centuries, best appreciated at eye level.'
)

# Stop 1 as it shipped in tour_405: the orientation body appears twice — once after
# the "Orientation:" label, once as a bare paragraph immediately after.
_TOUR_405_STOP1 = f"""Step-by-Step Audio Guided Tour: Museo de Bellas Artes de Bilbao, Bilbao, Spain - Museum Tour
Tour-Category: museum

Stop 1: El sacrificio de Isaac

Address: Museo de Bellas Artes de Bilbao, Museo Plaza, 2, 48009 Bilbao, Spain

Coordinates: 43.263, -2.934

Orientation: {_ORIENT_405}

{_ORIENT_405}

"El sacrificio de Isaac," painted in oil on canvas, is the biblical episode in which Abraham prepares to sacrifice his son Isaac before an angel intervenes. Pedro Orrente created this scene at a moment when Spanish painting was reaching for new storytelling power.

Directions: Continue through Museo de Bellas Artes de Bilbao — next is Portrait of Martin Zapater.

Stop 2: Portrait of Martin Zapater

Address: Museo de Bellas Artes de Bilbao, Museo Plaza, 2, 48009 Bilbao, Spain

Coordinates: 43.263, -2.934

Orientation: To best encounter Portrait of Martin Zapater, stand three paces back and slightly to the right of the canvas, where the light clarifies the brushwork around the face and hands.
"""


class TestParagraphDedupe(unittest.TestCase):
    def test_finds_the_405_duplicate(self):
        dupes = find_duplicate_paragraphs(_TOUR_405_STOP1)
        self.assertEqual(len(dupes), 1,
                         f"expected exactly one duplicated paragraph, got {len(dupes)}")
        self.assertIn("You are about to explore", dupes[0])

    def test_removes_second_copy_keeps_first(self):
        new_text, removed = dedupe_paragraphs(_TOUR_405_STOP1)
        self.assertEqual(len(removed), 1, f"expected one removal, got {removed}")
        # The orientation body must now appear exactly once in the whole tour.
        self.assertEqual(new_text.count("The moment you step close enough"), 1)
        # The labelled first copy is the one kept.
        self.assertIn("Orientation: You are about to explore", new_text)
        # And after dedupe, the detector sees no duplicates.
        self.assertEqual(find_duplicate_paragraphs(new_text), [])

    def test_idempotent(self):
        once, _ = dedupe_paragraphs(_TOUR_405_STOP1)
        twice, removed2 = dedupe_paragraphs(once)
        self.assertEqual(removed2, [], "second dedupe pass should remove nothing")
        self.assertEqual(once, twice)

    def test_structural_repeats_not_flagged(self):
        # Address: and Coordinates: repeat across every stop — that is correct and
        # must never be reported or removed.
        dupes = find_duplicate_paragraphs(_TOUR_405_STOP1)
        for d in dupes:
            self.assertNotIn("Address:", d)
            self.assertNotIn("Coordinates:", d)
        new_text, removed = dedupe_paragraphs(_TOUR_405_STOP1)
        for r in removed:
            self.assertFalse(r.startswith("Address:"))
            self.assertFalse(r.startswith("Coordinates:"))
        # Both Address lines survive.
        self.assertEqual(new_text.count("Address: Museo de Bellas Artes de Bilbao"), 2)

    def test_short_paragraph_below_threshold_kept(self):
        short = "Open daily."
        self.assertLess(len(short), MIN_PARAGRAPH_CHARS)
        text = f"{short}\n\n{short}\n\n"
        new_text, removed = dedupe_paragraphs(text)
        self.assertEqual(removed, [], "short paragraphs are exempt from dedupe")
        self.assertEqual(new_text.count("Open daily."), 2)


class TestQARunnerCheck(unittest.TestCase):
    def _run_qa_capture(self, text):
        """Run content_qa_runner.run_qa and return (pass_count, fail_count, output)."""
        import io
        import contextlib
        import content_qa_runner as cqr
        cqr.PASS_COUNT = 0
        cqr.FAIL_COUNT = 0
        cqr.FACTUAL_FAIL_COUNT = 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cqr.run_qa(text)
        return cqr.PASS_COUNT, cqr.FAIL_COUNT, buf.getvalue()

    def test_qa_fails_on_raw_405(self):
        _, _, out = self._run_qa_capture(_TOUR_405_STOP1)
        self.assertIn("FAIL: No duplicated paragraph", out,
                      "QA must FAIL the duplicated-paragraph check on raw 405")

    def test_qa_passes_after_dedupe(self):
        cleaned, _ = dedupe_paragraphs(_TOUR_405_STOP1)
        _, _, out = self._run_qa_capture(cleaned)
        self.assertIn("PASS: No duplicated paragraph", out,
                      "QA must PASS the duplicated-paragraph check after dedupe")


if __name__ == "__main__":
    unittest.main()
