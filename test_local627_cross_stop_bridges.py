#!/usr/bin/env python3
"""test_local627_cross_stop_bridges.py — LOCAL-627 defect 9.

Tour 487 recapped the previous stop in every stop ("…you stopped at a moment ago",
"think of the Portrait… you stopped at earlier"). Michael's rule: at most ONE
light thematic bridge per tour, and never a recap of the PREVIOUS stop.
cross_stop_reference_guard.limit_thematic_bridges enforces it.

Run: python3 -m pytest test_local627_cross_stop_bridges.py -q
"""
import unittest

import cross_stop_reference_guard as g


class TestLimitThematicBridges(unittest.TestCase):
    def test_previous_stop_recap_always_dropped(self):
        units = [
            {"title": "Las Meninas", "narration": "Velazquez painted the royal family."},
            {"title": "The Third of May",
             "narration": ("Goya shows an execution. Think of the Portrait you "
                           "stopped at a moment ago, with its calm gaze.")},
        ]
        new, dropped = g.limit_thematic_bridges(units)
        self.assertTrue(any(d["reason"] == "previous-stop recap" for d in dropped))
        self.assertNotIn("a moment ago", new[1]["narration"])
        self.assertIn("Goya shows an execution.", new[1]["narration"])

    def test_at_most_one_bridge_kept(self):
        units = [
            {"title": "A", "narration": "A quiet still life opens the tour."},
            {"title": "B",
             "narration": ("A dramatic scene. Earlier on this tour you met a "
                           "gentler mood.")},
            {"title": "C",
             "narration": ("A third work. Like the earlier stop, it uses shadow "
                           "to tell its story.")},
        ]
        new, dropped = g.limit_thematic_bridges(units, max_bridges=1)
        # First bridge kept, second dropped.
        self.assertIn("Earlier on this tour", new[1]["narration"])
        self.assertTrue(any(d["reason"] == "more than one thematic bridge"
                            for d in dropped))
        self.assertNotIn("Like the earlier stop", new[2]["narration"])

    def test_no_callback_untouched(self):
        units = [
            {"title": "A", "narration": "A still life of fruit and glass."},
            {"title": "B", "narration": "A portrait of a nobleman in black."},
        ]
        new, dropped = g.limit_thematic_bridges(units)
        self.assertEqual(dropped, [])
        self.assertEqual(new[1]["narration"], units[1]["narration"])

    def test_recap_dropped_even_when_it_is_the_only_bridge(self):
        units = [
            {"title": "A", "narration": "An opening work."},
            {"title": "B",
             "narration": ("A second work. Recall the painting you just saw a "
                           "moment ago.")},
        ]
        new, dropped = g.limit_thematic_bridges(units)
        self.assertNotIn("you just saw", new[1]["narration"])
        self.assertIn("A second work.", new[1]["narration"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
