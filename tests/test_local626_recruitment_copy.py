#!/usr/bin/env python3
"""test_local626_recruitment_copy.py — LOCAL-626 item 3.

Tour 485's Stop 1 spoke the Courtauld INSTITUTE's admissions-page copy:
  "You'll learn from leaders across the history, conservation, curation and
   business of art, and forge a career in the wider professional art world and
   beyond."
  "Study in the heart of London with world-renowned specialists in the history,
   conservation, curation, and business of art."
These are a student prospectus, not tour narration. The LOCAL-614 academic-
program filter missed them (no major/minor/admissions/degree token). The fix
drops second-person marketing/recruitment sentences from the about-museum gate
AND from the whole spoken tour (stop bodies), and ranks the venue's own gallery
pages above the institution's academic pages as sources.

The sentences below are VERBATIM from .continuous_dev/calib/critique/tour_485.txt.

Run: python3 -m pytest tests/test_local626_recruitment_copy.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spoken_text_hygiene import (strip_recruitment_sentences,
                                  RECRUITMENT_SENTENCE_RE, clean_spoken_text)
import about_museum_stop as ams

# The real tour-485 Stop-1 passage (opening + the leaked recruitment copy).
TOUR_485_STOP1 = (
    "The Courtauld Gallery is an art museum in Somerset House, on the Strand in "
    "central London. It houses the collection of the Samuel Courtauld Trust. "
    "You'll learn from leaders across the history, conservation, curation and "
    "business of art, and forge a career in the wider professional art world and "
    "beyond. Study in the heart of London with world-renowned specialists in the "
    "history, conservation, curation, and business of art."
)

# Ordinary tour second-person framing that must SURVIVE.
TOUR_NARRATION = (
    "As you look closer, you can see the thick brushwork. Stand just inside the "
    "Great Room, where the daylight falls across the paintings."
)


class TestRecruitmentCopy(unittest.TestCase):
    def test_strips_the_485_recruitment_sentences(self):
        cleaned, dropped = strip_recruitment_sentences(TOUR_485_STOP1)
        self.assertEqual(2, dropped, "both recruitment sentences must be dropped")
        self.assertNotIn("You'll learn from leaders", cleaned)
        self.assertNotIn("forge a career", cleaned)
        self.assertNotIn("Study in the heart of London", cleaned)
        # The genuine museum-identity sentences survive.
        self.assertIn("The Courtauld Gallery is an art museum", cleaned)
        self.assertIn("Samuel Courtauld Trust", cleaned)

    def test_tour_narration_is_not_touched(self):
        cleaned, dropped = strip_recruitment_sentences(TOUR_NARRATION)
        self.assertEqual(0, dropped)
        self.assertEqual(TOUR_NARRATION, cleaned)

    def test_about_gate_rejects_recruitment(self):
        self.assertTrue(ams._is_recruitment_sentence(
            "You'll learn from leaders and forge a career in the art world."))
        self.assertTrue(ams._is_recruitment_sentence(
            "Study in the heart of London with world-renowned specialists."))
        # not recruitment:
        self.assertFalse(ams._is_recruitment_sentence(
            "The gallery was founded in 1932 by Samuel Courtauld."))
        self.assertFalse(ams._is_recruitment_sentence(
            "As you can see, the brushwork is thick and deliberate."))

    def test_clean_spoken_text_drops_recruitment_in_bodies(self):
        """clean_spoken_text (the last pass before TTS) strips recruitment copy
        wherever it appears, including a stop body."""
        body = ("Stop 2: Paul Cezanne. Stand before the still life. "
                "Apply for our world-renowned programmes to study with us.")
        cleaned, report = clean_spoken_text(body)
        self.assertGreaterEqual(report.get("recruitment", 0), 1)
        self.assertNotIn("Apply for our world-renowned programmes", cleaned)
        self.assertIn("Stand before the still life", cleaned)

    def test_gallery_pages_rank_above_academic(self):
        """A shared-domain venue (Courtauld on courtauld.ac.uk) reaches its
        gallery/museum story pages before any academic/admissions path."""
        urls = ams._candidate_story_urls("https://courtauld.ac.uk/study")
        # The academic root we started from is pushed below the gallery seeds.
        gallery_idx = next((i for i, u in enumerate(urls) if "/gallery" in u), None)
        academic_idx = next((i for i, u in enumerate(urls)
                             if ams._ACADEMIC_PATH_RE.search(u)), None)
        self.assertIsNotNone(gallery_idx, "a gallery story page must be present")
        if academic_idx is not None:
            self.assertLess(gallery_idx, academic_idx,
                            "gallery pages must rank above academic pages")

    def test_production_wires_recruitment_filters(self):
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, "spoken_text_hygiene.py"), encoding="utf-8") as fh:
            self.assertIn("strip_recruitment_sentences", fh.read())
        with open(os.path.join(_here, "about_museum_stop.py"), encoding="utf-8") as fh:
            src = fh.read()
            self.assertIn("_is_recruitment_sentence", src)
            self.assertIn("_ACADEMIC_PATH_RE", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
