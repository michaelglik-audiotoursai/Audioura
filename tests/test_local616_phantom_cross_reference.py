r"""
test_local616_phantom_cross_reference.py — [LOCAL-616 item 4]
=============================================================
Tour 414 (Musée Fabre) shipped, inside Stop 1:

    "…mirrors … the earlier stops of this tour, such as La Vue du village…"

"La Vue du village" is NOT a stop in tour 414 — the sentence was carried over in a
pooled stop's narration from the earlier tour it was reused from. Strip or
regenerate any cross-stop reference that names a title not present in the delivered
tour. These tests pin the deterministic guard
(cross_stop_reference_guard.strip_phantom_references) and its integration into
stop_pool_assembly.assemble_building_tour. RED on base (the sentence ships), GREEN
after.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cross_stop_reference_guard as g
import stop_pool_assembly as asm


class TestStripPhantomReferences(unittest.TestCase):
    def test_phantom_sentence_dropped(self):
        units = [{
            "title": "Saint Agatha",
            "narration": ("This work mirrors the surreal clarity found in the "
                          "earlier stops of this tour, such as La Vue du village. "
                          "It is a devotional painting."),
        }]
        new, dropped = g.strip_phantom_references(units)
        self.assertEqual(len(dropped), 1)
        self.assertIn("La Vue du village", dropped[0]["phantom"])
        self.assertNotIn("La Vue du village", new[0]["narration"])
        # The real sentence stays.
        self.assertIn("It is a devotional painting.", new[0]["narration"])

    def test_valid_cross_reference_kept(self):
        # A cross-reference to a title that IS delivered must NOT be dropped.
        units = [
            {"title": "The Oath of the Horatii", "narration": "A neoclassical work."},
            {"title": "Saint Agatha",
             "narration": ("Earlier on your tour you paused at The Oath of the "
                           "Horatii, which set the tone.")},
        ]
        new, dropped = g.strip_phantom_references(units)
        self.assertEqual(dropped, [])
        self.assertIn("The Oath of the Horatii", new[1]["narration"])

    def test_quoted_phantom_dropped(self):
        units = [{
            "title": "Saint Agatha",
            "narration": ('Recall the themes you saw at "The Village View" a few '
                          'stops ago. The saint holds a palm.'),
        }]
        new, dropped = g.strip_phantom_references(units)
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("The Village View", new[0]["narration"])
        self.assertIn("The saint holds a palm.", new[0]["narration"])

    def test_no_cue_no_drop(self):
        # A sentence that happens to name a capitalised phrase but makes no
        # cross-stop reference is untouched.
        units = [{"title": "Saint Agatha",
                  "narration": "The painting La Vue du village hangs nearby."}]
        new, dropped = g.strip_phantom_references(units)
        self.assertEqual(dropped, [])
        self.assertEqual(new[0]["narration"],
                         "The painting La Vue du village hangs nearby.")

    def test_title_core_matching(self):
        # Delivered title "Jacques-Louis David: The Oath of the Horatii" — a
        # reference to "The Oath of the Horatii" matches on the work core.
        units = [
            {"title": "Jacques-Louis David: The Oath of the Horatii, 1784",
             "narration": "A founding work of neoclassicism."},
            {"title": "Saint Agatha",
             "narration": ("Like The Oath of the Horatii seen earlier on this "
                           "tour, it uses dramatic light.")},
        ]
        new, dropped = g.strip_phantom_references(units)
        self.assertEqual(dropped, [])


class TestAssemblyIntegration(unittest.TestCase):
    """The building assembler must route pooled narration through the phantom
    guard, so a reused stop's dangling reference never reaches the delivered text."""

    def test_phantom_absent_from_delivered_tour(self):
        pooled = [{
            "title": "Saint Agatha",
            "narration": ("Zurbarán's saint gazes outward. This mirrors the earlier "
                          "stops of this tour, such as La Vue du village, in its "
                          "quiet intensity."),
            "orientation": "You stand before Saint Agatha.",
        }]
        result = asm.assemble_building_tour(
            location="Musée Fabre, Montpellier, France",
            tour_type="Museum Tour",
            tour_category="museum",
            header_category="museum",
            display_category="Museum Tour",
            venue_name="Musée Fabre",
            new_stops=[],
            pooled_stops=pooled,
        )
        self.assertNotIn("La Vue du village", result.tour_text)
        # The guard's drop is surfaced on the result log.
        self.assertTrue(any("phantom-ref" in ln for ln in result.dedupe_log))
        # The rest of the stop survives.
        self.assertIn("Zurbarán's saint gazes outward", result.tour_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
