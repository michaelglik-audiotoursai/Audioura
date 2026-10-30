"""test_local832b_story_survival.py — [LOCAL-832B] survival-repair regression tests.

The story pass (LOCAL-490) writes a finished 3–5-sentence story for a museum stop
and the narration prompt is handed it with permission to "adjust wording to flow
into the surrounding text". On the cheap arm the narration model INTERLEAVES the
story with physical description, so the delivered prose's longest consecutive run
about one subject drops below 3 and its agency/stakes verbs scatter — and
story_opportunity_scan then reads the delivered text as storyless (agency=0
stakes=0). The story the pass wrote never reached the listener.

story_survival.repair_description re-seats a bar-clearing pass story as its own
leading block when the delivered prose lost it. These tests are built from the
real 828B Rijksmuseum trace: a flattened Night Watch delivered body (longest run
3, Rembrandt, agency 0 stakes 0) and a bar-clearing Miró-shaped pass story. They
exercise the scan through the real story_opportunity_scan (no network, no LLM).

Run: python3 -m pytest test_local832b_story_survival.py -q
 or: python3 -m unittest test_local832b_story_survival -v
"""
import unittest

from story_survival import (
    clears_bar,
    story_survived,
    repair_description,
    survival_log_line,
    RepairResult,
)

# ---- Fixtures from the 828B Rijksmuseum trace ------------------------------

# The DELIVERED Night Watch stop, cheap arm. Rembrandt is named across the body
# but the narration interleaved description, so the longest CONSECUTIVE run about
# him is 3 sentences carrying agency=0 stakes=0 — storyless by Michael's bar.
FLAT_NIGHT_WATCH = (
    "Rembrandt completed this colossal group portrait in 1642 for the "
    "Kloveniersdoelen, the guild hall of Amsterdam's civic guards. The painting, "
    "known as The Night Watch, is a large oil on canvas measuring approximately "
    "fourteen and a half feet wide by twelve feet tall, commanding attention in "
    "this gallery. It portrays Captain Frans Banning Cocq and his company of "
    "merchants and shopkeepers whose duties had shifted from municipal defense to "
    "ceremonial social gatherings. Instead of arranging the figures in static "
    "poses, Rembrandt set them in dynamic motion, scattering the members as they "
    "interact under shifting light and shadow. He used chiaroscuro to guide the "
    "viewer's eye toward the central captain and his lieutenant. This technique "
    "animates the scene and creates a sense of depth and drama."
)

# A bar-clearing pass story (Miró-shaped: commissioned / refused / destroyed /
# survived). This is the shape the pass writes and that clears the scan on its own.
PASS_STORY_CLEARS = (
    "Louis Broder commissioned Miro to make the lithographs for this portfolio. "
    "Miro refused the first proofs and destroyed them because the colors were "
    "wrong. He began again, and only the second set survived."
)

# A pass story that does NOT clear the bar on its own: a gift carries no stakes,
# so the scan reports stakes=0 even though the run is 3 sentences about one
# subject. The 828B Met log shows exactly this ("gifted ... donated").
PASS_STORY_WEAK = (
    "Washington Crossing the Delaware was gifted to The Metropolitan Museum of Art "
    "in 1897 by John Stewart Kennedy. Before this gift, the painting was part of a "
    "private collection. The museum has displayed it ever since."
)


class TestClearsBar(unittest.TestCase):
    def test_flattened_delivery_does_not_clear(self):
        self.assertFalse(clears_bar(FLAT_NIGHT_WATCH))

    def test_bar_clearing_story_clears(self):
        self.assertTrue(clears_bar(PASS_STORY_CLEARS))

    def test_weak_story_does_not_clear(self):
        self.assertFalse(clears_bar(PASS_STORY_WEAK))

    def test_empty_and_placeholder_never_clear(self):
        self.assertFalse(clears_bar(""))
        self.assertFalse(clears_bar("   "))
        self.assertFalse(clears_bar("[GENERATION_FAILED]"))


class TestRepairDescription(unittest.TestCase):
    def test_prepends_when_merge_dissolved_a_bar_clearing_story(self):
        res = repair_description(FLAT_NIGHT_WATCH,
                                 {"ok": True, "story": PASS_STORY_CLEARS})
        self.assertIsInstance(res, RepairResult)
        self.assertTrue(res.changed)
        self.assertTrue(res.description.startswith("Louis Broder commissioned"))
        # The real payoff: the repaired text now clears the bar the delivery failed.
        self.assertTrue(clears_bar(res.description))
        # And the original delivery body is preserved after the story block.
        self.assertIn("Rembrandt completed this colossal group portrait",
                      res.description)

    def test_does_not_prepend_when_delivery_already_clears(self):
        already = PASS_STORY_CLEARS + "\n\n" + FLAT_NIGHT_WATCH
        res = repair_description(already, {"ok": True, "story": PASS_STORY_CLEARS})
        self.assertFalse(res.changed)
        self.assertEqual(res.description, already)

    def test_does_not_prepend_when_pass_story_is_weak(self):
        # The stop is genuinely storyless; prepending a weak story would only add
        # words and fool nothing. Left for the reserve refill / honest shortfall.
        res = repair_description(FLAT_NIGHT_WATCH,
                                 {"ok": True, "story": PASS_STORY_WEAK})
        self.assertFalse(res.changed)
        self.assertFalse(res.story_clears)

    def test_no_ok_story_is_a_noop(self):
        res = repair_description(FLAT_NIGHT_WATCH, {"ok": False, "story": ""})
        self.assertFalse(res.changed)
        self.assertEqual(res.description, FLAT_NIGHT_WATCH)

    def test_missing_story_pass_is_a_noop(self):
        res = repair_description(FLAT_NIGHT_WATCH, None)
        self.assertFalse(res.changed)
        self.assertEqual(res.description, FLAT_NIGHT_WATCH)

    def test_placeholder_description_is_a_noop(self):
        res = repair_description("[GENERATION_FAILED]",
                                 {"ok": True, "story": PASS_STORY_CLEARS})
        self.assertFalse(res.changed)

    def test_accepts_bare_story_string(self):
        res = repair_description(FLAT_NIGHT_WATCH, PASS_STORY_CLEARS)
        self.assertTrue(res.changed)
        self.assertTrue(clears_bar(res.description))

    def test_does_not_double_tell_when_delivery_opens_with_story(self):
        # Delivery that already opens with the story but (contrived) still scans as
        # needing one must not have the same block stacked on top of itself.
        opens_with = PASS_STORY_CLEARS + " It is blue. It hangs here."
        res = repair_description(opens_with, {"ok": True, "story": PASS_STORY_CLEARS})
        # Either it already clears (no change) or the double-tell guard fires;
        # in both cases the story text appears exactly once at the front.
        self.assertFalse(res.description.count("Louis Broder commissioned") > 1)


class TestStorySurvived(unittest.TestCase):
    def test_survived_tracks_delivered_clearance(self):
        self.assertFalse(story_survived(FLAT_NIGHT_WATCH, PASS_STORY_CLEARS))
        self.assertTrue(story_survived(
            PASS_STORY_CLEARS + "\n\n" + FLAT_NIGHT_WATCH, PASS_STORY_CLEARS))


class TestSurvivalLogLine(unittest.TestCase):
    def test_changed_line(self):
        res = repair_description(FLAT_NIGHT_WATCH,
                                 {"ok": True, "story": PASS_STORY_CLEARS})
        line = survival_log_line("stop 1 'The Night Watch'", res)
        self.assertIn("[LOCAL-832B] story-survival", line)
        self.assertIn("prepended pass story", line)

    def test_unchanged_line(self):
        res = repair_description(FLAT_NIGHT_WATCH, None)
        line = survival_log_line("stop 1 'The Night Watch'", res)
        self.assertIn("no change", line)


if __name__ == "__main__":
    unittest.main()
