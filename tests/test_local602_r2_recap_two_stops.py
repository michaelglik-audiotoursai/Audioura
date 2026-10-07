#!/usr/bin/env python3
"""test_local602_r2_recap_two_stops.py — LOCAL-602 r2 / D617 item 12.

No "From X to X…" recap when the tour has fewer than 2 stops. The r1 WNDR overview
was a 1-stop pool delivery, so stop_pool_assembly._closing_recap emitted "From
WNDR Museum — Overview to WNDR Museum — Overview, you have followed the thread of
a single story." — first == last, nonsense.

These tests pin:
  * stop_pool_assembly._closing_recap: 1 stop → no From→to clause; >=2 → it has one;
  * tour_cache_layer1._repair_recap: trimming to 1 stop drops the From→to clause;
  * spoken_text_hygiene.strip_degenerate_from_to_recap: tour-wide safety net
    removes a From X to X sentence when the endpoints are identical, keeps a real
    multi-stop recap.

Run: python3 -m pytest tests/test_local602_r2_recap_two_stops.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_pool_assembly as asm
import tour_cache_layer1 as tcl
import spoken_text_hygiene as sth


_FROM_TO = re.compile(r'(?i)From\s+.+?\s+to\s+.+?,\s*you have followed')


class TestClosingRecap(unittest.TestCase):

    def test_single_stop_has_no_from_to(self):
        recap = asm._closing_recap(["WNDR Museum — Overview"])
        self.assertIsNone(_FROM_TO.search(recap),
                          f"1-stop recap must not say 'From X to X': {recap!r}")
        self.assertIn("That's 1 stop", recap)
        self.assertIn("WNDR Museum — Overview", recap)

    def test_two_stops_keep_from_to(self):
        recap = asm._closing_recap(["Flex", "WNDRWall"])
        self.assertIsNotNone(_FROM_TO.search(recap))
        self.assertIn("From Flex to WNDRWall", recap)
        self.assertIn("That's 2 stops", recap)

    def test_empty_titles_empty_recap(self):
        self.assertEqual(asm._closing_recap([]), "")


class TestRepairRecapTrimToOne(unittest.TestCase):

    def test_trim_to_one_drops_from_to(self):
        recap_block = ("From Flex to WNDRWall, you have followed the thread of a "
                       "single story.\n\nThat's 5 stops.")
        out = tcl._repair_recap(recap_block, "Flex", "Flex", target_stops=1)
        self.assertIsNone(_FROM_TO.search(out),
                          f"trim-to-1 recap must not say 'From X to X': {out!r}")
        self.assertIn("Flex", out)


class TestStripDegenerateRecap(unittest.TestCase):

    def test_identical_endpoints_removed(self):
        text = ("Stop 1: WNDR Museum — Overview\n\nSome content.\n\n"
                "From WNDR Museum — Overview to WNDR Museum — Overview, you have "
                "followed the thread of a single story.\n\nThat's 1 stop.\n")
        out, n = sth.strip_degenerate_from_to_recap(text)
        self.assertEqual(n, 1)
        self.assertIsNone(_FROM_TO.search(out))
        self.assertIn("Some content.", out)

    def test_distinct_endpoints_kept(self):
        text = ("From Flex to WNDRWall, you have followed the thread of a single "
                "story.\n\nThat's 2 stops.\n")
        out, n = sth.strip_degenerate_from_to_recap(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_no_recap_unchanged(self):
        text = "Stop 1: Flex\n\nAn immersive room.\n"
        out, n = sth.strip_degenerate_from_to_recap(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)


if __name__ == '__main__':
    unittest.main()
