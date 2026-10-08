#!/usr/bin/env python3
"""test_local627_orientation_phantom_name.py — LOCAL-627 defect 7.

Tour 488's orientation named "Gentileschi and Ejlerskov" — but Ejlerskov is in no
delivered stop. The orientation preview may name only delivered stops' artists and
works. orientation_pretell.strip_phantom_preview_names drops a preview sentence
naming a proper noun absent from every delivered stop's title + narration.

Run: python3 -m pytest test_local627_orientation_phantom_name.py -q
"""
import unittest

import orientation_pretell as op


DELIVERED_NAMES = [
    "Judith Slaying Holofernes",
    "The Birth of Venus",
    "Venus of Urbino",
]
DELIVERED_TEXTS = [
    "Artemisia Gentileschi painted this violent scene around 1620.",
    "Sandro Botticelli composed this mythological masterpiece.",
    "Titian reclined his Venus across a Venetian bedchamber.",
]


class TestStripPhantomPreviewNames(unittest.TestCase):
    def test_phantom_artist_sentence_dropped(self):
        orientation = ("Orientation: On this tour you will meet the great painters "
                       "Gentileschi and Ejlerskov. Your first stop is Judith "
                       "Slaying Holofernes.")
        cleaned, dropped = op.strip_phantom_preview_names(
            orientation, DELIVERED_NAMES, DELIVERED_TEXTS)
        self.assertEqual(dropped, 1)
        self.assertNotIn("Ejlerskov", cleaned)
        # The pointer survives.
        self.assertIn("Judith Slaying Holofernes", cleaned)

    def test_all_delivered_names_kept(self):
        orientation = ("Orientation: You will see works by Gentileschi, Botticelli "
                       "and Titian. Your first stop is Judith Slaying Holofernes.")
        cleaned, dropped = op.strip_phantom_preview_names(
            orientation, DELIVERED_NAMES, DELIVERED_TEXTS)
        self.assertEqual(dropped, 0)
        self.assertIn("Botticelli", cleaned)
        self.assertIn("Titian", cleaned)

    def test_no_proper_noun_sentence_kept(self):
        orientation = ("Orientation: These works share a bold use of light and "
                       "shadow. Your first stop is The Birth of Venus.")
        cleaned, dropped = op.strip_phantom_preview_names(
            orientation, DELIVERED_NAMES, DELIVERED_TEXTS)
        self.assertEqual(dropped, 0)

    def test_never_empties(self):
        orientation = "Orientation: Meet Ejlerskov and Phantomsson on this tour."
        cleaned, dropped = op.strip_phantom_preview_names(
            orientation, DELIVERED_NAMES, DELIVERED_TEXTS)
        self.assertTrue(cleaned.strip())

    def test_label_preserved(self):
        orientation = ("Orientation: You will meet Ejlerskov here. Your first stop "
                       "is The Birth of Venus.")
        cleaned, dropped = op.strip_phantom_preview_names(
            orientation, DELIVERED_NAMES, DELIVERED_TEXTS)
        self.assertTrue(cleaned.lower().startswith("orientation:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
