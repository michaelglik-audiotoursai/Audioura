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
        self.assertTrue(any(d["reason"] == "stock recency callback" for d in dropped))
        self.assertNotIn("a moment ago", new[1]["narration"])
        self.assertIn("Goya shows an execution.", new[1]["narration"])

    def test_budget_scales_with_stops_D636(self):
        """D636: a couple of callbacks per tour are continuity: budget = max(1, (n+1)//3)."""
        self.assertEqual(g.callback_budget(3), 1)
        self.assertEqual(g.callback_budget(5), 2)
        self.assertEqual(g.callback_budget(8), 3)
        units = [{"title": t, "narration": "Work %s." % t} for t in "ABCDE"]
        units[1]["narration"] += " Earlier on this tour you met a gentler mood."
        units[3]["narration"] += " Like the earlier stop, it uses shadow."
        units[4]["narration"] += " Recall the still life and its glass."
        new, dropped = g.limit_thematic_bridges(units)   # 5 stops -> budget 2
        self.assertIn("Earlier on this tour", new[1]["narration"])
        self.assertIn("Like the earlier stop", new[3]["narration"])
        self.assertNotIn("Recall the still life", new[4]["narration"])

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
        self.assertTrue(any(d["reason"] == "callback over the per-tour budget"
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


class TestLimitThematicBridgesInText(unittest.TestCase):
    """[LOCAL-627 defect 9] The text-level guard catches recaps on the normal
    (non-pool) delivery path — the EXACT shapes the live Uffizi tour shipped."""

    UFFIZI_TEXT = (
        "Stop 1: Leda col cigno\n\n"
        "Coordinates: 43.7, 11.2\n\n"
        "Melzi reproduced Leonardo's lost Leda. It is oil on canvas.\n\n"
        "Stop 2: Adorazione dei Magi\n\n"
        "Orientation: Stand close to Leonardo's unfinished panel.\n\n"
        "Botticelli integrated a self-portrait, much like his \"Leda col cigno\" "
        "that you previously encountered, where divine and earthly realms "
        "intertwined. Leonardo left the panel unfinished.\n\n"
        "Stop 3: The Annunciation\n\n"
        "This divine encounter completes our journey, echoing themes seen in the "
        "\"Adorazione dei Magi\" you observed earlier. Gabriel kneels before Mary."
    )

    def test_live_recaps_dropped(self):
        cleaned, dropped = g.limit_thematic_bridges_in_text(self.UFFIZI_TEXT)
        # D636: 3 stops -> budget 1. The first named callback is kept (continuity),
        # the second is over budget and dropped.
        self.assertEqual(dropped, 1)
        self.assertIn("you previously encountered", cleaned)
        self.assertNotIn("you observed earlier", cleaned)
        # Real narration + headers + field lines survive.
        self.assertIn("Stop 2: Adorazione dei Magi", cleaned)
        self.assertIn("Leonardo left the panel unfinished.", cleaned)
        self.assertIn("Gabriel kneels before Mary.", cleaned)
        self.assertIn("Coordinates: 43.7, 11.2", cleaned)

    def test_clean_text_unchanged(self):
        clean = ("Stop 1: A\n\nA quiet still life.\n\n"
                 "Stop 2: B\n\nA portrait in black.")
        cleaned, dropped = g.limit_thematic_bridges_in_text(clean)
        self.assertEqual(dropped, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
