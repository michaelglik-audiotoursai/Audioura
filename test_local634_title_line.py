#!/usr/bin/env python3
"""test_local634_title_line.py — [LOCAL-634] the title/header line is never edited.

Bench R1 (488, 505, 506): the delivered tour opened with a header line rewritten
into a spoken sentence —
    "Step-by-step audio guided tour of the Museo Reina Sofía in Madrid, Spain,
     is a museum tour."
title_line_guard.restore_title_line restores the canonical header. The stop
editor must also leave the title banner (and field lines) untouched.

Run: python3 -m pytest test_local634_title_line.py -q
"""
import os
import unittest

os.environ.setdefault("STOP_EDITOR", "1")

import title_line_guard as t
import stop_editor as se


class TestRestoreTitleLine(unittest.TestCase):
    def test_restores_rewritten_505_header(self):
        text = (
            "Step-by-step audio guided tour of the Museo Reina Sofia in Madrid, "
            "Spain, is a museum tour.\n\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Guernica\n\nPicasso condemned the bombing."
        )
        out, restored = t.restore_title_line(text)
        self.assertTrue(restored)
        self.assertTrue(out.split("\n")[0].startswith(
            "Step-by-Step Audio Guided Tour:"))
        self.assertIn("Museo Reina Sofia", out.split("\n")[0])
        self.assertIn("Museum Tour", out.split("\n")[0])
        # Field line and stop body preserved.
        self.assertIn("Tour-Category: museum", out)
        self.assertIn("Stop 1: Guernica", out)

    def test_canonical_header_is_noop(self):
        canon = ("Step-by-Step Audio Guided Tour: Museo Reina Sofia, Madrid, "
                 "Spain - Museum Tour\n\nStop 1: X\n\nBody.")
        out, restored = t.restore_title_line(canon)
        self.assertFalse(restored)
        self.assertEqual(out, canon)

    def test_idempotent(self):
        text = ("Step-by-step audio guided tour of the Uffizi in Florence, "
                "Italy, is a museum tour.\n\nStop 1: X\n\nBody.")
        once, r1 = t.restore_title_line(text)
        self.assertTrue(r1)
        twice, r2 = t.restore_title_line(once)
        self.assertFalse(r2)
        self.assertEqual(once, twice)

    def test_unrelated_first_line_untouched(self):
        text = "Welcome to the tour.\n\nStop 1: X\n\nBody."
        out, restored = t.restore_title_line(text)
        self.assertFalse(restored)
        self.assertEqual(out, text)

    def test_detect_parts(self):
        parsed = t.detect_rewritten_title(
            "Step-by-step audio guided tour of the Borghese Gallery in Rome, "
            "Italy, is a museum tour.")
        self.assertIsNotNone(parsed)
        venue, place, category = parsed
        self.assertEqual(venue, "Borghese Gallery")
        self.assertIn("Rome", place)
        self.assertEqual(category, "museum")


class TestStopEditorNeverEditsHeaderOrFields(unittest.TestCase):
    def test_title_banner_and_fields_preserved(self):
        tour = (
            "Step-by-Step Audio Guided Tour: Reina Sofia, Madrid, Spain - Museum Tour\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Guernica\n\n"
            "Address: Calle de Santa Isabel, 52\n\n"
            "Orientation: Stand before the mural.\n\n"
            "Picasso condemned the bombing of Guernica in this mural.\n\n"
            "Directions: Continue to the next room.\n"
        )
        # Identity edit (changes nothing in the body) — the banner and all field
        # lines must survive byte-for-byte.
        import re as _re
        def _identity(prompt, key):
            m = _re.search(r"STOP BODY:\n(.*)$", prompt, _re.S)
            return m.group(1).strip() if m else ""
        out = se.edit_tour_text(tour, venue_name="Reina Sofia",
                                llm_fn=_identity, log=lambda s: None)
        self.assertIn("Step-by-Step Audio Guided Tour: Reina Sofia, Madrid, "
                      "Spain - Museum Tour", out)
        self.assertIn("Tour-Category: museum", out)
        self.assertIn("Address: Calle de Santa Isabel, 52", out)
        self.assertIn("Orientation: Stand before the mural.", out)
        self.assertIn("Directions: Continue to the next room.", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
