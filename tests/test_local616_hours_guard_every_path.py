"""
test_local616_hours_guard_every_path.py — [LOCAL-616 item 1]
============================================================

Tour 414 (Musée Fabre, second run = POOL reuse + 3 new stops) shipped Stop 1 with
"Check opening hours and admission on museefabre.fr before you go." even though the
log shows the LOCAL-603 preflight supplied real hours
("Monday, Thursday, Friday: 12:00 PM – 6:00 PM; …").

Root cause: the LOCAL-615 belt-and-braces guard
(``stop_pool_orchestrator._fold_preflight_hours_into_text``) only ran on the
first-tour / fresh branch inside the orchestrator. The POOL path
(``generate_tour_text._LAST_DELIVERY_PATH == 'pool'``) returned ``_pool_out["text"]``
with no guard, so the fallback shipped — and the service reads the delivered tour
from the OUTPUT FILE, which was never rewritten.

Fix: ``generate_tour_text._apply_delivery_hours_guard`` runs the guard on the final
text of EVERY path at the single wrapper choke point, and rewrites the output file.
This pins it on 414's actual Stop 1 text + its preflight dict.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt


# Tour 414's Stop 1 as it shipped — the stale "check hours on <domain>" fallback.
_FABRE_414_STOP1 = """Step-by-Step Audio Guided Tour: Musée Fabre, Montpellier, France - Museum Tour
Tour-Category: museum

Stop 1: Saint Agatha

Address: Musée Fabre, 39 Boulevard Bonne Nouvelle, 34000 Montpellier, France

Before we look at anything on the walls, here is the story of Musée Fabre — who created it, why it exists, and what it is known for.

Check opening hours and admission on museefabre.fr before you go.

Orientation: You are about to explore the Musée Fabre in Montpellier.
"""

# The LOCAL-603 preflight that ran for 414 (hours per the log).
_FABRE_414_PREFLIGHT = {
    "hours": "Monday, Thursday, Friday: 12:00 PM – 6:00 PM; Saturday, Sunday: 10:00 AM – 6:00 PM",
    "admission": "8 euros, free on the first Sunday of each month",
    "sources": {"hours": ["https://museefabre.fr/visite"],
                "admission": ["https://museefabre.fr/visite"]},
}


class TestHoursGuardEveryPath(unittest.TestCase):
    def setUp(self):
        self._saved = getattr(gtt, "_LAST_VENUE_PREFLIGHT", {})
        gtt._LAST_VENUE_PREFLIGHT = dict(_FABRE_414_PREFLIGHT)

    def tearDown(self):
        gtt._LAST_VENUE_PREFLIGHT = self._saved

    def test_helper_exists(self):
        # The single wrapper choke point must exist (every path returns through it).
        self.assertTrue(hasattr(gtt, "_apply_delivery_hours_guard"))

    def test_pool_path_text_is_folded(self):
        # Simulate the POOL path return tuple (text, output_file, coords).
        folded, _out, _coords = gtt._apply_delivery_hours_guard(
            (_FABRE_414_STOP1, None, (None, None)))
        self.assertNotIn("Check opening hours and admission on museefabre.fr", folded)
        self.assertNotIn("before you go", folded)
        # The real hours from the preflight are spoken instead — now as the
        # LOCAL-633 COMPOSED sentence (the day LIST becomes an honest "daily except
        # Tuesday and Wednesday", not the raw row paste).
        self.assertIn("open daily except Tuesday and Wednesday", folded)
        self.assertIn("8 euros", folded)

    def test_output_file_is_rewritten(self):
        # The service reads the delivered tour from the FILE — it must be rewritten.
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(_FABRE_414_STOP1)
            folded, out_file, _ = gtt._apply_delivery_hours_guard(
                (_FABRE_414_STOP1, path, (None, None)))
            self.assertEqual(out_file, path)
            on_disk = open(path, encoding="utf-8").read()
            self.assertEqual(on_disk, folded)
            self.assertNotIn("Check opening hours and admission on museefabre.fr", on_disk)
            self.assertIn("open daily except Tuesday and Wednesday", on_disk)
        finally:
            os.unlink(path)

    def test_refusal_none_text_passes_through(self):
        res = gtt._apply_delivery_hours_guard((None, "x.txt", (None, None)))
        self.assertEqual(res, (None, "x.txt", (None, None)))

    def test_noop_when_preflight_has_no_hours(self):
        gtt._LAST_VENUE_PREFLIGHT = {"hours": "", "admission": "", "sources": {}}
        folded, _o, _c = gtt._apply_delivery_hours_guard(
            (_FABRE_414_STOP1, None, (None, None)))
        # Never invent HOURS: the guard must not fabricate opening hours when the
        # preflight has none. (The guard also rebuilds the conclusion per LOCAL-619,
        # so the whole text is no longer byte-identical — assert the hours no-op.)
        self.assertNotIn("Monday, Thursday, Friday: 12:00 PM", folded)
        self.assertNotIn("10:00 AM – 6:00 PM", folded)
        # The venue's Stop 1 story is untouched.
        self.assertIn("here is the story of Musée Fabre", folded)

    def test_idempotent(self):
        once, _o, _c = gtt._apply_delivery_hours_guard(
            (_FABRE_414_STOP1, None, (None, None)))
        twice, _o2, _c2 = gtt._apply_delivery_hours_guard((once, None, (None, None)))
        self.assertEqual(once, twice)


# [LOCAL-616 item 1] The every-path finalization guard also removes a duplicated
# paragraph (the orientation block printed twice when the orchestrator folds the
# D611 opening into Stop 1 after the inner QA ran — the live Granet/Groeninge
# runs showed exactly this).
_ORIENT = ("You are about to explore the Musée Granet in Aix-en-Provence, home to "
           "an array of artistic treasures spanning many periods and styles, a rich "
           "collection shaped by generations of patronage and care.")
_TOUR_WITH_DUP_ORIENTATION = (
    "Step-by-Step Audio Guided Tour: Musée Granet, Aix-en-Provence, France\n"
    "Tour-Category: museum\n\n"
    "Stop 1: Mon musée à la maison\n\n"
    "Address: Place Saint-Jean de Malte, 13100 Aix-en-Provence, France\n\n"
    f"Orientation: {_ORIENT}\n\n"
    f"{_ORIENT}\n\n"
    "The display itself is digital, echoing the museum's pale limestone halls.\n"
)


class TestDuplicateParagraphGuardEveryPath(unittest.TestCase):
    def setUp(self):
        self._saved = getattr(gtt, "_LAST_VENUE_PREFLIGHT", {})
        gtt._LAST_VENUE_PREFLIGHT = {}  # no hours → isolate the dedupe behaviour

    def tearDown(self):
        gtt._LAST_VENUE_PREFLIGHT = self._saved

    def test_duplicate_orientation_removed(self):
        folded, _o, _c = gtt._apply_delivery_hours_guard(
            (_TOUR_WITH_DUP_ORIENTATION, None, (None, None)))
        # The orientation body must appear exactly once now.
        self.assertEqual(folded.count(_ORIENT), 1)

    def test_output_file_rewritten_on_dedupe(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(_TOUR_WITH_DUP_ORIENTATION)
            folded, _o, _c = gtt._apply_delivery_hours_guard(
                (_TOUR_WITH_DUP_ORIENTATION, path, (None, None)))
            on_disk = open(path, encoding="utf-8").read()
            self.assertEqual(on_disk, folded)
            self.assertEqual(on_disk.count(_ORIENT), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
