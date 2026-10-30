#!/usr/bin/env python3
"""test_local823_title_body_dup.py — [LOCAL-823] a stop title is never a body copy.

Belvedere cheap-arm proof tour 474, Stop 1: the stop's BODY TEXT was duplicated
onto its TITLE line. This proves the delivery check:

    a stop title is NEVER a prefix copy of its body,

and that a SHORT proper-name title the body merely opens by naming
("Austrian State Treaty was signed…") is never touched. Pure/offline, idempotent.

Run: python3 -m pytest test_local823_title_body_dup.py -q
"""
import unittest

import stop_title_body_dup_guard as g


# The exact defect shape: Stop 1's title is the opening run of its own narration.
_DEFECT_BODY = (
    "Stand in the Marble Hall of the Upper Belvedere, where the Austrian State "
    "Treaty was signed on May 15, 1955, ending a decade of occupation."
)
_DEFECT_TITLE = ("Stand in the Marble Hall of the Upper Belvedere where the "
                 "Austrian State Treaty was signed on May 15 1955")


class TestTitleIsBodyPrefix(unittest.TestCase):
    def test_defect_detected(self):
        self.assertTrue(g.title_is_body_prefix(_DEFECT_TITLE, _DEFECT_BODY))

    def test_short_proper_name_title_not_flagged(self):
        # The body opens by naming the work — normal and wanted, NOT a duplicate.
        self.assertFalse(g.title_is_body_prefix(
            "Austrian State Treaty",
            "Austrian State Treaty was signed on May 15, 1955 at the Belvedere."))

    def test_short_name_not_in_body_not_flagged(self):
        self.assertFalse(g.title_is_body_prefix(
            "Belvedere Palace Chapel",
            "Stand before the altarpiece, a Baroque treasure of the Resurrection."))

    def test_empty_inputs_safe(self):
        self.assertFalse(g.title_is_body_prefix("", "anything"))
        self.assertFalse(g.title_is_body_prefix("Something", ""))


class TestRepairTitle(unittest.TestCase):
    def test_defect_shortened_to_banner(self):
        out, did = g.repair_title(_DEFECT_TITLE, _DEFECT_BODY)
        self.assertTrue(did)
        self.assertLess(len(out.split()), len(_DEFECT_TITLE.split()))
        # The repaired banner is still a prefix of the title text (a clean name).
        self.assertTrue(_DEFECT_TITLE.lower().startswith(out.lower().split(",")[0][:10].lower()))

    def test_fallback_used_when_given(self):
        out, did = g.repair_title(_DEFECT_TITLE, _DEFECT_BODY,
                                  fallback="Austrian State Treaty")
        self.assertTrue(did)
        self.assertEqual(out, "Austrian State Treaty")

    def test_noop_on_clean_title(self):
        out, did = g.repair_title("Austrian State Treaty", _DEFECT_BODY)
        self.assertFalse(did)
        self.assertEqual(out, "Austrian State Treaty")


class TestRepairTourText(unittest.TestCase):
    TOUR = (
        "Step-by-Step Audio Guided Tour: Belvedere, Vienna, Austria - Museum Tour\n\n"
        "Stop 1: Stand in the Marble Hall of the Upper Belvedere where the Austrian State Treaty was signed on May 15 1955\n\n"
        "Address:\n\n"
        "Coordinates: 48.2051, 16.3728\n\n"
        "Orientation: Stand in the Marble Hall of the Upper Belvedere, where the "
        "Austrian State Treaty was signed on May 15, 1955, ending a decade of "
        "occupation.\n\n"
        "The treaty restored Austrian sovereignty.\n\n"
        "Stop 2: Belvedere Palace Chapel\n\n"
        "Orientation: Stand before the altarpiece.\n\n"
        "A Baroque treasure of the Resurrection.\n"
    )

    def test_stop1_repaired_stop2_untouched(self):
        out, reps = g.repair_tour_text_title_body_dup(self.TOUR)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["num"], 1)
        # Stop 2's short proper-name title is preserved verbatim.
        self.assertIn("Stop 2: Belvedere Palace Chapel", out)
        # Stop 1's header is now a short banner, not the whole body sentence.
        orig_stop1_title = self.TOUR.split("Stop 1: ")[1].split("\n")[0]
        stop1_header = [l for l in out.split("\n") if l.startswith("Stop 1:")][0]
        new_stop1_title = stop1_header[len("Stop 1: "):]
        self.assertLess(len(new_stop1_title.split()), len(orig_stop1_title.split()))
        # The body is preserved byte-for-byte.
        self.assertIn("The treaty restored Austrian sovereignty.", out)

    def test_idempotent(self):
        once, reps1 = g.repair_tour_text_title_body_dup(self.TOUR)
        twice, reps2 = g.repair_tour_text_title_body_dup(once)
        self.assertTrue(reps1)
        self.assertEqual(reps2, [])
        self.assertEqual(once, twice)

    def test_clean_tour_unchanged(self):
        clean = (
            "Step-by-Step Audio Guided Tour: Belvedere, Vienna - Museum Tour\n\n"
            "Stop 1: Austrian State Treaty\n\n"
            "Orientation: Stand in the Marble Hall.\n\n"
            "The treaty was signed here in 1955.\n\n"
            "Stop 2: Belvedere Palace Chapel\n\n"
            "Orientation: Stand before the altarpiece.\n\nA Baroque treasure.\n"
        )
        out, reps = g.repair_tour_text_title_body_dup(clean)
        self.assertEqual(reps, [])
        self.assertEqual(out, clean)


if __name__ == "__main__":
    unittest.main(verbosity=2)
