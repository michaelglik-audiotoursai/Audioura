r"""
test_local616_wrong_era.py — [LOCAL-616 item 5]
================================================
Tour 414 Stop 3 described an object dated 1782 with:

    "In the 13th century, such a combination of materials signified…"

The 13th century is ~500 years from 1782. Add a deterministic wrong-era check: in
a stop whose work date is KNOWN, drop any sentence asserting a century/year more
than 150 years away, UNLESS framed as an earlier tradition / influence / revival.
These tests pin wrong_era_guard and its integration into
stop_pool_assembly.assemble_building_tour. RED on base, GREEN after.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wrong_era_guard as w
import stop_pool_assembly as asm


class TestWorkYear(unittest.TestCase):
    def test_year_field(self):
        self.assertEqual(w.work_year({"title": "Rattle", "year": "1782"}), 1782)

    def test_title_trailing_year(self):
        self.assertEqual(w.work_year({"title": "Silver Rattle, 1782"}), 1782)

    def test_no_date_returns_none(self):
        self.assertIsNone(w.work_year({"title": "Untitled"}))


class TestSentenceIsWrongEra(unittest.TestCase):
    def test_413_case_dropped(self):
        self.assertEqual(
            w.sentence_is_wrong_era(
                "In the 13th century, such a combination of materials signified wealth.",
                1782),
            "13th century")

    def test_near_era_kept(self):
        # Late-18th-century phrasing around a 1782 work is correct.
        self.assertIsNone(
            w.sentence_is_wrong_era(
                "In the 18th century, portraiture flourished.", 1782))

    def test_earlier_tradition_framing_kept(self):
        self.assertIsNone(
            w.sentence_is_wrong_era(
                "The form revives a 13th-century medieval tradition of enamel work.",
                1782))

    def test_word_century_dropped(self):
        self.assertEqual(
            w.sentence_is_wrong_era(
                "This belongs to the thirteenth century entirely.", 1782),
            "thirteenth century")

    def test_bare_year_far_away_dropped(self):
        self.assertIsNotNone(
            w.sentence_is_wrong_era("It was first cast around 1250.", 1782))


class TestStripWrongEraSentences(unittest.TestCase):
    def test_contradicting_sentence_dropped_fact_kept(self):
        units = [{
            "title": "Silver Rattle, 1782", "year": "1782",
            "narration": ("This rattle was made in 1782. In the 13th century, such "
                          "a combination of materials signified wealth. The handle "
                          "is coral."),
        }]
        new, dropped = w.strip_wrong_era_sentences(units)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["era"], "13th century")
        self.assertEqual(dropped[0]["work_year"], 1782)
        self.assertNotIn("13th century", new[0]["narration"])
        self.assertIn("This rattle was made in 1782.", new[0]["narration"])
        self.assertIn("The handle is coral.", new[0]["narration"])

    def test_no_known_date_no_action(self):
        units = [{"title": "Untitled",
                  "narration": "In the 13th century this would be unusual."}]
        new, dropped = w.strip_wrong_era_sentences(units)
        self.assertEqual(dropped, [])
        self.assertIn("13th century", new[0]["narration"])


class TestAssemblyIntegration(unittest.TestCase):
    def test_wrong_era_absent_from_delivered_tour(self):
        pooled = [{
            "title": "Reliquary, 1782", "year": "1782",
            "narration": ("This reliquary dates to 1782. In the 13th century, such a "
                          "combination of materials signified wealth and devotion. "
                          "Its surface gleams with gold."),
            "orientation": "You stand before the reliquary.",
        }]
        result = asm.assemble_building_tour(
            location="Musée Fabre, Montpellier, France",
            tour_type="Museum Tour", tour_category="museum",
            header_category="museum", display_category="Museum Tour",
            venue_name="Musée Fabre", new_stops=[], pooled_stops=pooled)
        self.assertNotIn("In the 13th century", result.tour_text)
        self.assertTrue(any("wrong-era" in ln for ln in result.dedupe_log))
        self.assertIn("Its surface gleams with gold", result.tour_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
