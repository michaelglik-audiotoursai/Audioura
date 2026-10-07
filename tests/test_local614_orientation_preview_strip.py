r"""
LOCAL-614 item 2 — a tour-OPENING orientation / preview block never lives inside
a pooled stop body.
=========================================================================
The kiro-cli critique of McMullen tour 399 found a tour-opening orientation block
misfiled mid-tour (critique Stop 6):

    "You are about to explore the McMullen Museum of Art … Prepare to encounter
     seven distinct works, including … In the upcoming stops, you will see 'Meal
     at the House of Simon' … Your first stop is Dura-Europos …"

That is a Stop-1 orientation stored with (and reused by) a later stop. LOCAL-607
already strips a leaked EPILOG and the opening ABOUT section at store/read; this
extends the same strip-at-store/read layer to opening / preview orientation
sentences, using a deterministic pattern set:

    "Prepare to encounter", "In the upcoming stops", "You are about to explore",
    "Your first stop is", "Before we begin", "On this tour you will", …

These tests CALL the real functions (stop_pool_store.strip_orientation_preview and
parse_delivered_stops) — never grep source. RED on base (no such strip), GREEN
after.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_pool_store as sp


# A pooled stop whose narration body carries a leaked tour-OPENING orientation /
# preview block (verbatim shapes from tour 399's Stop 6), followed by the stop's
# OWN real narration.
LEAKED_ORIENTATION_STOP = """Stop 6: Dura-Europos: Crossroads of Antiquity

Address: 140 Commonwealth Avenue, Boston College, Boston

You are about to explore the McMullen Museum of Art at Boston College. Prepare to encounter seven distinct works, including Dura-Europos, Paris Along the Seine, and Ideal Portrait. In the upcoming stops, you will see 'Meal at the House of Simon the Pharisee,' focusing on Christ's serene presence. Your first stop is Dura-Europos: Crossroads of Antiquity.

Dura-Europos was a vibrant city at the crossroads of multiple empires. The exhibition showcases artifacts and murals from the site.
"""


class TestStripOrientationPreview(unittest.TestCase):
    """strip_orientation_preview removes opening/preview sentences, keeps the
    stop's own narration, and is idempotent and safe on clean text."""

    def test_preview_sentences_removed(self):
        out = sp.strip_orientation_preview(LEAKED_ORIENTATION_STOP)
        self.assertNotIn("Prepare to encounter", out)
        self.assertNotIn("In the upcoming stops", out)
        self.assertNotIn("You are about to explore", out)
        self.assertNotIn("Your first stop is", out)

    def test_real_narration_preserved(self):
        out = sp.strip_orientation_preview(LEAKED_ORIENTATION_STOP)
        self.assertIn("Dura-Europos was a vibrant city", out)
        self.assertIn("The exhibition showcases artifacts", out)

    def test_idempotent(self):
        once = sp.strip_orientation_preview(LEAKED_ORIENTATION_STOP)
        twice = sp.strip_orientation_preview(once)
        self.assertEqual(once, twice)

    def test_clean_text_unchanged(self):
        clean = ("Dura-Europos was a vibrant city at the crossroads of empires. "
                 "The exhibition showcases artifacts and murals.")
        self.assertEqual(sp.strip_orientation_preview(clean), clean)

    def test_does_not_strip_a_normal_sentence_mentioning_stops(self):
        # A real narration sentence that merely contains the word "stop" is kept.
        s = "The painting stops the eye with its vivid red cloak."
        self.assertEqual(sp.strip_orientation_preview(s), s)


class TestParseDeliveredStopsStripsPreview(unittest.TestCase):
    """parse_delivered_stops must apply the preview strip to each stop body, so a
    pooled stop never carries a tour-opening orientation block in its narration."""

    def setUp(self):
        self.units = sp.parse_delivered_stops(LEAKED_ORIENTATION_STOP)

    def test_one_unit(self):
        self.assertEqual(len(self.units), 1)

    def test_narration_has_no_preview(self):
        n = self.units[0]["narration"]
        self.assertNotIn("Prepare to encounter", n)
        self.assertNotIn("In the upcoming stops", n)
        self.assertNotIn("You are about to explore", n)
        self.assertNotIn("Your first stop is", n)

    def test_narration_keeps_the_work(self):
        n = self.units[0]["narration"]
        self.assertIn("Dura-Europos was a vibrant city", n)


if __name__ == "__main__":
    unittest.main(verbosity=2)
