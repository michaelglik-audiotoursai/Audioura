#!/usr/bin/env python3
"""test_local626_invented_facts.py — LOCAL-626 item 5.

Tour 485 Stop 3 ("Footed Bowl with the Crucifixion" — a maiolica BOWL) carried
two invented-fact classes the existing checks missed:

  (a) OBJECT-TYPE bleed: "this Crucifixion PANEL was specifically created for a
      hospital chapel" — a panel is a different KIND of object from a bowl. The
      LOCAL-623 same-title guard binds TITLE→ARTIST and did not catch it.
  (b) DATE conflict within one stop: "between 1550 and 1570" (the corpus date)
      vs "created in Urbino during the period 1510-1571" (invented). One date
      per work, the corpus date wins.

Both passages below are VERBATIM from .continuous_dev/calib/critique/tour_485.txt.

Run: python3 -m pytest tests/test_local626_invented_facts.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import same_title_bleed_guard as stbg
import date_consistency_guard as dcg

# The real tour-485 Stop-3 bowl paragraph (trimmed to the relevant sentences).
BOWL_BODY = (
    "Footed Bowl with the Crucifixion, attributed to the workshop of Orazio "
    "Fontana or Antonio Patanazzi in Urbino, Italy, between 1550 and 1570, was "
    "once a piece crafted for liturgical or devotional use. The bowl itself is a "
    "work of painted ceramic, created in Urbino during the period 1510-1571, and "
    "likely intended for sacred rituals. The painting was not chosen at random: "
    "this Crucifixion panel was specifically created for a hospital chapel. "
    "Antonio Patanazzi, active from 1515 to 1587, operated at a moment when the "
    "boundaries between art, craft, and faith were fluid."
)
BOWL_TITLE = "Footed Bowl with the Crucifixion"


class TestObjectType(unittest.TestCase):
    def test_bowl_kind_is_vessel(self):
        self.assertEqual("vessel", stbg.object_kind_of(BOWL_TITLE))

    def test_panel_sentence_is_object_type_bleed(self):
        self.assertTrue(stbg.sentence_is_object_type_bleed(
            "this Crucifixion panel was specifically created for a hospital chapel",
            "vessel"))

    def test_compatible_vessel_sentences_are_kept(self):
        for s in ("The bowl itself is a work of painted ceramic.",
                  "Look beneath the rim of the footed bowl.",
                  "The painting was not chosen at random."):
            self.assertFalse(stbg.sentence_is_object_type_bleed(s, "vessel"),
                             f"{s!r} must not be flagged")

    def test_filter_drops_the_panel_sentence_keeps_bowl(self):
        new_body, rep = stbg.filter_stop_body_object_type(BOWL_BODY, BOWL_TITLE)
        self.assertTrue(rep["changed"])
        self.assertGreaterEqual(rep["dropped"], 1)
        self.assertNotIn("Crucifixion panel", new_body)
        self.assertIn("The bowl itself is a work of painted ceramic", new_body)


class TestDateConsistency(unittest.TestCase):
    def test_parse_range(self):
        self.assertEqual((1550, 1570), dcg.parse_date_range("between 1550 and 1570"))
        self.assertEqual((1510, 1571), dcg.parse_date_range("period 1510-1571"))
        self.assertEqual((1906, 1906), dcg.parse_date_range("painted in 1906"))

    def test_ranges_conflict(self):
        self.assertTrue(dcg.ranges_conflict((1550, 1570), (1510, 1571)))
        self.assertFalse(dcg.ranges_conflict((1906, 1906), (1904, 1906)))
        self.assertFalse(dcg.ranges_conflict((1550, 1570), (1550, 1570)))

    def test_corpus_date_wins_drops_the_invented_range(self):
        new_body, rep = dcg.filter_stop_body_date_consistency(
            BOWL_BODY, corpus_date="between 1550 and 1570")
        self.assertTrue(rep["changed"])
        self.assertEqual((1550, 1570), rep["kept_date"])
        self.assertNotIn("1510-1571", new_body)
        self.assertIn("between 1550 and 1570", new_body)

    def test_person_dates_are_not_touched(self):
        """A PERSON's dates ('Patanazzi, active from 1515 to 1587') must survive —
        the guard only reconciles the WORK's creation date."""
        new_body, _ = dcg.filter_stop_body_date_consistency(
            BOWL_BODY, corpus_date="between 1550 and 1570")
        self.assertIn("active from 1515 to 1587", new_body)

    def test_no_date_no_change(self):
        body = "The bowl is beautiful. Look at the rim. The glaze is bright."
        new_body, rep = dcg.filter_stop_body_date_consistency(body, "")
        self.assertFalse(rep["changed"])
        self.assertEqual(body, new_body)


class TestWiring(unittest.TestCase):
    def test_production_wires_both_guards(self):
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, "generate_tour_text.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("filter_tour_text_object_type", src)
        self.assertIn("filter_tour_text_date_consistency", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
