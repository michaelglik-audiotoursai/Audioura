r"""
LOCAL-614 item 5 — robust fact fingerprint: same year + same key noun = same
fact; stops after Stop 1 keep at most one museum-history sentence, about their
own work.
=========================================================================
The kiro-cli critique of McMullen tour 399 found the 2016 relocation told four
times, the 1993 opening and the donors retold in stops 2, 3, 4 and 7. LOCAL-607's
fingerprint keyed on (year, PROPER NOUNS), so reworded versions with different
(or no) proper nouns slipped through:

  "the museum's relocation to its current address at 2101 Commonwealth Avenue
   in 2016 …"                                   → (2016, 'commonwealth', …)
  "… relocation to its current Brighton Campus location in 2016."
                                                 → (2016, 'brighton', …)
  "… nearly doubled the museum's exhibition capacity in 2016 …"
                                                 → (2016) with NO proper noun → None

Fix: a sentence that carries a YEAR and a museum-history KEY NOUN
(relocat*/renam*/donat*/found*/open*) fingerprints to (year, key-noun), wording-
and proper-noun-independent, so every 2016-relocation retelling collapses to one
fact. And a later stop keeps at most ONE museum-history sentence, only when it is
about that stop's OWN work.

These tests CALL the real functions (D418/D421). RED on base (reworded repeats
survive; year-without-proper-noun has no fingerprint), GREEN after.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cross_stop_fact_dedupe as dd


class TestRobustFingerprint(unittest.TestCase):
    """year + key noun → one wording-independent fingerprint."""

    def test_year_plus_key_noun_fingerprints_without_proper_noun(self):
        # "nearly doubled the museum's exhibition capacity in 2016" has a year but
        # no proper noun — on base it had NO fingerprint. A relocation keyword +
        # year must fingerprint even with no proper noun.
        s = ("The museum relocated to a larger home in 2016, expanding its "
             "galleries.")
        self.assertIsNotNone(dd.fact_fingerprint(s))

    def test_reworded_relocations_share_one_fingerprint(self):
        a = ("The museum's relocation to its current address at 2101 Commonwealth "
             "Avenue in 2016 facilitated the exhibition of such pieces.")
        b = ("… a narrative that reflects the museum's rich history and relocation "
             "to its current Brighton Campus location in 2016.")
        self.assertEqual(dd.fact_fingerprint(a), dd.fact_fingerprint(b),
                         "reworded 2016 relocations must share one fingerprint")

    def test_renaming_1996_collapses_regardless_of_names(self):
        a = "In 1996 the museum was renamed for Charles and Isabella McMullen."
        b = ("In 1996, the institution was officially renamed following the "
             "family's gift.")
        self.assertEqual(dd.fact_fingerprint(a), dd.fact_fingerprint(b))

    def test_different_years_do_not_collide(self):
        a = "The museum relocated in 2016."
        b = "The museum relocated in 1993."
        self.assertNotEqual(dd.fact_fingerprint(a), dd.fact_fingerprint(b))

    def test_different_key_nouns_do_not_collide(self):
        a = "The museum relocated in 2016."
        b = "The museum was renamed in 2016."
        self.assertNotEqual(dd.fact_fingerprint(a), dd.fact_fingerprint(b))

    def test_plain_description_still_has_no_fingerprint(self):
        s = "Two young women play the game of graces with wooden hoops."
        self.assertIsNone(dd.fact_fingerprint(s))


class TestRewordedRepeatsRemoved(unittest.TestCase):
    """The dedupe removes reworded cross-stop repeats of the same fact."""

    def _tour(self):
        return (
            "Step-by-Step Audio Guided Tour: McMullen Museum of Art\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Paris Along the Seine\n\n"
            "The museum's relocation to its current address at 2101 Commonwealth "
            "Avenue in 2016 facilitated the exhibition. Marquet painted the Seine "
            "in 1946.\n\n"
            "Stop 2: Landscape with Woman in Red\n\n"
            "This exhibition reflects the museum's rich history and relocation to "
            "its current Brighton Campus location in 2016. Dupre painted a rural "
            "farmhouse.\n\n"
            "Stop 3: Roman in the Provinces\n\n"
            "This exhibition, facilitated by the newly expanded space, relocated "
            "the collection in 2016. The mosaics testify to provincial life.\n")

    def test_only_first_relocation_survives(self):
        res = dd.dedupe_tour_facts(self._tour())
        # Every 2016-relocation retelling after the first is gone.
        self.assertEqual(res.tour_text.count("in 2016"), 1,
                         f"reworded 2016 repeats survived:\n{res.tour_text}")
        # The works' own sentences are kept.
        self.assertIn("Marquet painted the Seine", res.tour_text)
        self.assertIn("Dupre painted a rural farmhouse", res.tour_text)
        self.assertIn("The mosaics testify", res.tour_text)

    def test_qa_check_passes_after_dedupe(self):
        res = dd.dedupe_tour_facts(self._tour())
        after = dd.count_repeated_facts_across_stops(res.tour_text)
        self.assertEqual(len(after), 0, f"repeats survived: {after}")


class TestAtMostOneHistoryPerLaterStop(unittest.TestCase):
    """A stop after Stop 1 keeps at most one museum-history sentence, and only
    about its own work."""

    def test_later_stop_keeps_at_most_one_own_work_history(self):
        units = [
            {"title": "Grace Hoops", "narration":
                "Grace Hoops shows two women at play."},
            {"title": "Ideal Portrait", "narration":
                "In 1996 the museum was renamed for the McMullens. "
                "The museum relocated to Brighton in 2016. "
                "Ideal Portrait entered the collection as a 1990 gift from a "
                "donor. Peale chose oil for its luminous depth."},
        ]
        new_units, dropped = dd.dedupe_stop_units(units, stop1_owns_history=True)
        n = new_units[1]["narration"]
        # The renaming and the relocation (not about Ideal Portrait) are dropped.
        self.assertNotIn("renamed for the McMullens", n)
        self.assertNotIn("relocated to Brighton", n)
        # The work's own description survives.
        self.assertIn("Peale chose oil", n)


if __name__ == "__main__":
    unittest.main(verbosity=2)
