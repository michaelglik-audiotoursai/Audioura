"""
test_local615_preflight_hours_fresh.py — [LOCAL-615 item 2]
===========================================================

D626 (tour 405 Bilbao): Stop 1 still said "Check opening hours and admission on
museobilbao.com before you go." even though the LOCAL-603 preflight ran with
hours=y admission=y. LOCAL-607 folded the preflight hours into the POOL opening
only; on the FRESH path the opening section was built BEFORE generate_fn ran the
preflight, so the fallback shipped.

The fix has two parts, both pinned here (offline, deterministic):
  1. stop_pool_orchestrator._fold_preflight_hours_into_text — the belt-and-braces
     guard on the delivered text: it replaces a surviving "Check opening hours and
     admission on <domain> before you go." with the preflight's real hours when the
     preflight has them, and leaves the text untouched when it does not (never
     invent).
  2. Michael's rule: never say "check… on <domain>" when the preflight has hours.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt
import stop_pool_orchestrator as orch


# The Bilbao Stop 1 as it shipped (D626), carrying the stale fallback sentence.
_BILBAO_STOP1_WITH_FALLBACK = """Step-by-Step Audio Guided Tour: Museo de Bellas Artes de Bilbao, Bilbao, Spain - Museum Tour
Tour-Category: museum

Stop 1: El sacrificio de Isaac

Address: Museo de Bellas Artes de Bilbao, Museo Plaza, 2, 48009 Bilbao, Spain

Before we look at anything on the walls, here is the story of Bilbao Fine Arts Museum in Bilbao, Spain itself — who created it, why it exists, and what it is known for.

Check opening hours and admission on museobilbao.com before you go.

Orientation: You are about to explore the Museo de Bellas Artes de Bilbao in Bilbao.
"""


class TestFoldPreflightHoursIntoText(unittest.TestCase):
    def setUp(self):
        self._saved = getattr(gtt, "_LAST_VENUE_PREFLIGHT", {})

    def tearDown(self):
        gtt._LAST_VENUE_PREFLIGHT = self._saved

    def test_fallback_replaced_when_preflight_has_hours(self):
        gtt._LAST_VENUE_PREFLIGHT = {
            "hours": "Tuesday to Sunday, 10:00 to 20:00",
            "admission": "10 euros, free on Wednesdays",
            "sources": {"hours": ["https://museobilbao.com/visita"],
                        "admission": ["https://museobilbao.com/visita"]},
        }
        out = orch._fold_preflight_hours_into_text(_BILBAO_STOP1_WITH_FALLBACK)
        # The fallback is gone...
        self.assertNotIn("Check opening hours and admission on museobilbao.com", out)
        self.assertNotIn("before you go", out)
        # ...and the real hours (and admission) are spoken instead, now as the
        # LOCAL-633 COMPOSED sentence (short, one price, currency as a word) rather
        # than the raw preflight paste.
        self.assertIn("open Tuesday to Sunday", out)
        self.assertIn("10 euros", out)

    def test_unchanged_when_preflight_has_no_hours(self):
        # No hours/admission → never invent; the honest pointer stays.
        gtt._LAST_VENUE_PREFLIGHT = {"hours": "", "admission": "", "sources": {}}
        out = orch._fold_preflight_hours_into_text(_BILBAO_STOP1_WITH_FALLBACK)
        self.assertEqual(out, _BILBAO_STOP1_WITH_FALLBACK)

    def test_unchanged_when_preflight_skipped(self):
        gtt._LAST_VENUE_PREFLIGHT = {"skipped": True}
        out = orch._fold_preflight_hours_into_text(_BILBAO_STOP1_WITH_FALLBACK)
        self.assertEqual(out, _BILBAO_STOP1_WITH_FALLBACK)

    def test_unchanged_when_preflight_errored(self):
        gtt._LAST_VENUE_PREFLIGHT = {"error": "grounding forbidden", "hours": "x"}
        out = orch._fold_preflight_hours_into_text(_BILBAO_STOP1_WITH_FALLBACK)
        self.assertEqual(out, _BILBAO_STOP1_WITH_FALLBACK)

    def test_no_fallback_present_is_noop(self):
        gtt._LAST_VENUE_PREFLIGHT = {"hours": "10:00 to 18:00", "sources": {}}
        clean = "Stop 1: X\n\nThe museum is open 10:00 to 18:00.\n"
        self.assertEqual(orch._fold_preflight_hours_into_text(clean), clean)

    def test_idempotent(self):
        gtt._LAST_VENUE_PREFLIGHT = {
            "hours": "daily 09:00 to 17:00", "admission": "free", "sources": {}}
        once = orch._fold_preflight_hours_into_text(_BILBAO_STOP1_WITH_FALLBACK)
        twice = orch._fold_preflight_hours_into_text(once)
        self.assertEqual(once, twice)
        # Rule enforced: no "check ... on <domain>" survives when preflight has hours.
        self.assertNotIn("Check opening hours and admission on", once)


if __name__ == "__main__":
    unittest.main(verbosity=2)
