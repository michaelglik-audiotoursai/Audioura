"""
LOCAL-607 unit tests — pooled-tour coherence defects (McMullen tour 399).
=========================================================================
These tests CALL the real functions (D418/D421 — never grep source). No database
is required: epilog/opening-section stripping, the conclusion builder, and the
cross-stop fact dedupe are all pure.

Coverage maps to Michael's five defects:
  1. Epilog embedded mid-tour  → stop_pool_store.strip_epilog /
                                  parse_delivered_stops on a pooled Stop-2 fixture
                                  made from tour 399's Ideal Portrait block.
  2. Stub conclusion           → stop_pool_assembly._closing_recap names the
                                  thread, recaps three stops, ends on the
                                  restaurant offer.
  3. Same story every stop     → cross_stop_fact_dedupe.dedupe_tour_facts /
                                  dedupe_stop_units on tour 399's text; the QA
                                  check count_repeated_facts_across_stops.
  5. Stop-1 "check hours on bc.edu" → stop_pool_store.strip_opening_section.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stop_pool_store as sp
import stop_pool_assembly as asm
import cross_stop_fact_dedupe as dd


# A pooled Stop-2 fixture taken verbatim from tour 399's Ideal Portrait block.
# Ideal Portrait was the LAST stop of an earlier tour, so it was stored with that
# tour's full epilog ("That's 7 stops … If you would like to eat nearby …")
# attached to the end of its own narration — the defect-1 artefact.
TOUR399_STOP2 = """Step-by-Step Audio Guided Tour: McMullen Museum of Art, Boston College, Boston, MA
Tour-Category: museum

Stop 2: Ideal Portrait

Address: 2101 Commonwealth Ave, Chestnut Hill, MA 02467

Coordinates: 42.3451, -71.1623

Orientation: Observe the "Ideal Portrait" by Harriet Cany Peale closely from a comfortable distance.

In 1993, under the direction of Professor Nancy Netzer, the Boston College Museum of Art was established in Devlin Hall. Peale, an accomplished artist of her era, chose oil paint for its depth and luminous quality. The painting's inclusion in the McMullen Museum collection underscores the institution's commitment to preserving and showcasing significant American art.

In September 2016, the museum relocated to 2101 Commonwealth Avenue on Boston College's Brighton Campus. That's 7 stops — Dura-Europos: Jewish artists depicted narratives in ancient art, Ideal Portrait: Signage change signaled museum's new mission, and Grace Hoops: Homer captured human emotion with oil on canvas. If you would like to eat nearby we can build you a restaurant tour.
"""

# A compact Stop-1 fixture carrying the OPENING SECTION (About prolog + the stale
# "Check opening hours and admission on bc.edu before you go." fallback) that
# LOCAL-603's preflight now supersedes with real hours.
TOUR399_STOP1 = """Stop 1: Grace Hoops

Address: 140 Commonwealth Avenue, Boston College, Boston

Before we look at anything on the walls, here is the story of McMullen Museum of Art in Boston College, Boston itself — who created it, why it exists, and what it is known for. McMullen Museum of Art is the university art museum of Boston College in Brighton, Massachusetts.

Check opening hours and admission on bc.edu before you go.

In 1872 the American artist Winslow Homer painted "Grace Hoops" in oil on canvas, immersing viewers in a scene where two young women play the game of graces.
"""


def _load_full_tour399():
    """Read the full tour 399 text if present on the host (/tmp/t399.txt); else
    build an equivalent multi-stop fixture that repeats the donor/founding story
    across stops so the dedupe tests still exercise cross-stop repetition."""
    path = "/tmp/t399.txt"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    # Fallback fixture: the McMullen donor/founding story retold in 3 stops.
    return """Step-by-Step Audio Guided Tour: McMullen Museum of Art, Boston College, Boston, MA
Tour-Category: museum

Stop 1: Grace Hoops

In 1996, John and Jacqueline McMullen donated to the museum, leading to its renaming as the McMullen Museum of Art. Grace Hoops shows two young women at play.

Stop 2: Ideal Portrait

In 1996, the McMullens' gift renamed the Boston College Museum of Art. Peale chose oil paint for its luminous quality.

Stop 3: Landscape with Woman in Red

In 1996, John and Jacqueline McMullen made a financial donation, prompting the renaming of the institution. Dupre painted a serene rural farmhouse.
"""


class TestEpilogStripping(unittest.TestCase):
    """Defect 1: a pooled stop must end at the stop, never carrying a prior tour's
    epilog ("That's N stops …", "If you would like to eat nearby …")."""

    def setUp(self):
        self.units = sp.parse_delivered_stops(TOUR399_STOP2)

    def test_one_unit(self):
        self.assertEqual(len(self.units), 1)
        self.assertEqual(self.units[0]["title"], "Ideal Portrait")

    def test_epilog_removed_from_narration(self):
        n = self.units[0]["narration"]
        self.assertNotIn("That's 7 stops", n)
        self.assertNotIn("you have followed the thread", n)
        self.assertNotIn("eat nearby", n)
        self.assertNotIn("restaurant tour", n)

    def test_last_real_sentence_preserved(self):
        # The stop's own final sentence (the relocation) must survive the strip.
        n = self.units[0]["narration"]
        self.assertIn("relocated to 2101 Commonwealth Avenue", n)

    def test_strip_epilog_is_idempotent(self):
        once = sp.strip_epilog(TOUR399_STOP2)
        twice = sp.strip_epilog(once)
        self.assertEqual(once, twice)

    def test_strip_epilog_leaves_clean_text_unchanged(self):
        clean = "Peale chose oil paint for its luminous quality."
        self.assertEqual(sp.strip_epilog(clean), clean)


class TestOpeningSectionStripping(unittest.TestCase):
    """Defect 5: the About prolog + 'Check … bc.edu' fallback are a per-tour
    opener regenerated fresh; they must not live in the pooled Stop-1 narration."""

    def setUp(self):
        self.units = sp.parse_delivered_stops(TOUR399_STOP1)

    def test_about_prolog_removed(self):
        n = self.units[0]["narration"]
        self.assertNotIn("Before we look at anything on the walls", n)

    def test_stale_hours_fallback_removed(self):
        n = self.units[0]["narration"]
        self.assertNotIn("Check opening hours and admission on bc.edu", n)
        self.assertNotIn("before you go", n)

    def test_work_body_preserved(self):
        n = self.units[0]["narration"]
        self.assertIn("Winslow Homer painted", n)
        self.assertTrue(n.lstrip().startswith("In 1872"))

    def test_strip_opening_section_idempotent(self):
        once = sp.strip_opening_section(TOUR399_STOP1)
        twice = sp.strip_opening_section(once)
        self.assertEqual(once, twice)


class TestConclusionBuilder(unittest.TestCase):
    """Defect 2: a real conclusion — names the thread, recaps three stops one line
    each, ends with the restaurant offer as the very last sentence."""

    def setUp(self):
        tour = _load_full_tour399()
        units = sp.parse_delivered_stops(tour)
        self.stops = [{"title": u["title"], "narration": u["narration"]}
                      for u in units]
        self.recap = asm._closing_recap(self.stops,
                                        venue_name="McMullen Museum of Art")

    def test_names_the_thread(self):
        self.assertIn("McMullen Museum of Art", self.recap)
        self.assertIn("you have followed the thread", self.recap)

    def test_recaps_up_to_three_stops_one_line_each(self):
        # Up to three one-line recap bullets, never one per stop for a big tour.
        bullet_lines = [ln for ln in self.recap.split("\n") if ln.startswith("- ")]
        self.assertGreaterEqual(len(bullet_lines), 1)
        self.assertLessEqual(len(bullet_lines), 3)

    def test_restaurant_offer_is_the_last_sentence(self):
        self.assertTrue(
            self.recap.rstrip().endswith(
                "If you would like to eat nearby we can build you a restaurant tour."))

    def test_empty_input_is_empty(self):
        self.assertEqual(asm._closing_recap([]), "")


class TestCrossStopFactDedupe(unittest.TestCase):
    """Defect 3: the donor/founding/relocation story told once, in Stop 1 — not in
    every stop. The dedupe keeps the first occurrence and removes later repeats."""

    def setUp(self):
        self.tour = _load_full_tour399()

    def test_repeats_present_before_dedupe(self):
        before = dd.count_repeated_facts_across_stops(self.tour)
        self.assertGreater(len(before), 0,
                           "fixture should contain at least one repeated fact")

    def test_dedupe_removes_cross_stop_repeats(self):
        res = dd.dedupe_tour_facts(self.tour)
        after = dd.count_repeated_facts_across_stops(res.tour_text)
        self.assertEqual(len(after), 0,
                         f"repeats survived: {after}")
        self.assertGreater(res.dropped_count, 0)

    def test_dedupe_is_deterministic(self):
        a = dd.dedupe_tour_facts(self.tour).tour_text
        b = dd.dedupe_tour_facts(self.tour).tour_text
        self.assertEqual(a, b)

    def test_foundation_is_not_mistaken_for_founding(self):
        # "the foundation of its past contributions" is NOT a museum-history fact.
        s = ("This evolution mirrors Paris, where the museum continues to build "
             "its future on the foundation of its past contributions.")
        self.assertFalse(dd.is_museum_history(s))

    def test_year_plus_proper_noun_fingerprints(self):
        s = ("In 1996, John and Jacqueline McMullen donated to the Boston College "
             "Museum of Art.")
        self.assertIsNotNone(dd.fact_fingerprint(s))

    def test_plain_description_has_no_fingerprint(self):
        s = "Two young women play the game of graces with wooden hoops."
        self.assertIsNone(dd.fact_fingerprint(s))

    def test_museum_history_belongs_to_stop1(self):
        # A founding sentence first appearing in Stop 2 is dropped (Stop 1 owns it).
        units = [
            {"title": "Work A", "narration": "Work A is an oil on canvas."},
            {"title": "Work B", "narration":
                "In 1993 the Boston College Museum of Art was founded in Devlin Hall. "
                "Work B is a bronze."},
        ]
        new_units, dropped = dd.dedupe_stop_units(units, stop1_owns_history=True)
        self.assertTrue(any(d["stop"] == 2 for d in dropped))
        self.assertNotIn("founded in Devlin Hall", new_units[1]["narration"])
        self.assertIn("Work B is a bronze", new_units[1]["narration"])


class TestQACheckRepeatedStory(unittest.TestCase):
    """The 'No repeated story across stops' QA check counts surviving duplicates."""

    def test_qa_check_flags_repeats_then_passes_after_dedupe(self):
        tour = _load_full_tour399()
        before = dd.count_repeated_facts_across_stops(tour)
        self.assertGreater(len(before), 0)
        cleaned = dd.dedupe_tour_facts(tour).tour_text
        after = dd.count_repeated_facts_across_stops(cleaned)
        self.assertEqual(len(after), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
