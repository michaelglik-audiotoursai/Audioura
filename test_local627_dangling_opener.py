#!/usr/bin/env python3
"""test_local627_dangling_opener.py — LOCAL-627 defect 6.

Tour 488 Stop 3 opened "This move ensured the sculpture's preservation…". The
sentence that introduced "the move" was removed by an earlier gate (fact dedupe /
phantom guard), so the stop body's FIRST sentence opened on an unresolved
demonstrative referring to removed text. The final first-sentence dangling-opener
guard (dangling_demonstrative_gate.strip_dangling_openers), run AFTER those
removals, drops it.

Run: python3 -m pytest test_local627_dangling_opener.py -q
"""
import unittest

import dangling_demonstrative_gate as g


class TestStripDanglingOpeners(unittest.TestCase):
    def test_unresolved_opener_dropped(self):
        units = [{
            "title": "Laocoon and His Sons",
            "narration": ("This move ensured the sculpture's preservation for "
                          "centuries. The statue still stands in the gallery today."),
        }]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["head_noun"].lower(), "move")
        self.assertNotIn("This move ensured", new[0]["narration"])
        self.assertIn("The statue still stands", new[0]["narration"])

    def test_resolved_opener_kept(self):
        # "This move" IS introduced by the preceding sentence -> keep.
        units = [{
            "title": "Laocoon",
            "narration": ("Pope Julius II ordered the move of the statue to the "
                          "Vatican. This move ensured its preservation."),
        }]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(dropped, [])
        self.assertIn("This move ensured", new[0]["narration"])

    def test_generic_subject_opener_kept(self):
        # "This sculpture" at a sculpture stop refers to the stop's own subject.
        units = [{
            "title": "Laocoon",
            "narration": ("This sculpture depicts a Trojan priest and his sons. "
                          "It is carved from marble."),
        }]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(dropped, [])

    def test_setting_noun_opener_kept(self):
        units = [{
            "title": "The East Corridor",
            "narration": ("This gallery holds the museum's Renaissance collection. "
                          "Walk slowly."),
        }]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(dropped, [])

    def test_non_demonstrative_opener_untouched(self):
        units = [{
            "title": "Venus of Urbino",
            "narration": "Titian painted this reclining nude in 1538. It scandalised Venice.",
        }]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(dropped, [])
        self.assertEqual(new[0]["narration"], units[0]["narration"])

    def test_empty_narration_safe(self):
        units = [{"title": "X", "narration": ""}]
        new, dropped = g.strip_dangling_openers(units)
        self.assertEqual(dropped, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
