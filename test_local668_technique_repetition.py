"""test_local668_technique_repetition.py — LOCAL-668 deliverable #5.

No retelling: the D533/S27 repetition pass must cover TECHNIQUE explanations —
the lacquer-layering story told once. A thin-museum tour fills slots with
collection-area stops (Lacquer / Silk / Woodblock); the writer tends to re-explain
how lacquer is layered at the silk and woodblock stops. fact_signatures needs a
year and keyphrase_signatures needs a rare adjacent bigram, so a REWORDED
technique explanation slips past both. The LOCAL-668 near-duplicate pass
(distinctive-word Jaccard) catches it.
"""
import unittest

import derepetition_guard as d

# Two REWORDED tellings of the same lacquer-layering technique. The wording is
# shuffled enough that NO identical adjacent distinctive bigram survives (so
# keyphrase_signatures is blind) and there is no year (so fact_signatures is
# blind) — but the distinctive vocabulary overlaps heavily.
_S1 = ("The lacquer, translucent and patient, receives burnishing between dozens "
       "of coats; abrading each coat, the maker lets one harden, polishing, before "
       "another.")
_S2 = ("Patiently the maker burnishes lacquer, abrading one translucent coat, "
       "polishing, letting it harden between dozens of successive coats, each "
       "layered.")

_TOUR = (
    "\nStop 1: Lacquer painting collection\n\n"
    + _S1 + " It anchors the museum's southern holdings.\n\n"
    "Stop 2: Silk painting collection\n\n"
    + _S2 + " Silk painting instead relies on delicate washes drawn across woven fabric.\n"
)


class TechniqueRepetition(unittest.TestCase):
    def test_reworded_technique_not_caught_by_year_or_keyphrase(self):
        # Neither year-fact nor rare-bigram signatures share across the two
        # reworded sentences (the baseline that motivates the new pass).
        sig1 = d.fact_signatures(_S1) | d.keyphrase_signatures(_S1)
        sig2 = d.fact_signatures(_S2) | d.keyphrase_signatures(_S2)
        self.assertEqual(sig1 & sig2, set(),
                         "fixture must NOT be caught by year/keyphrase alone")

    def test_near_duplicate_catches_reworded_technique(self):
        reps = d.check_cross_stop_fact_repetition(_TOUR)
        nd = [r for r in reps if r['signature'] == 'technique/near-duplicate'
              and r['repeat_stop'] == 2]
        self.assertTrue(nd, "reworded technique retelling must be flagged")

    def test_strip_removes_the_second_telling(self):
        out, acts = d.strip_repeated_facts(_TOUR, min_remaining_words=5)
        self.assertTrue(any(a.get('removed') for a in acts))
        stop2 = out.split("Stop 2:")[1]
        # the silk-specific sentence survives; the re-told lacquer one is gone
        self.assertIn("delicate washes", stop2)
        self.assertNotIn("abraded and burnished", stop2)

    def test_distinct_explanations_are_not_flagged(self):
        tour = (
            "\nStop 1: Lacquer painting collection\n\n"
            + _S1 + "\n\n"
            "Stop 2: Woodblock prints collection\n\n"
            "Woodblock printing cuts the design into a plank, inks the raised "
            "surface, and presses dampened paper against it by hand.\n"
        )
        reps = [r for r in d.check_cross_stop_fact_repetition(tour)
                if r['signature'] == 'technique/near-duplicate']
        self.assertEqual(reps, [], "genuinely different techniques must NOT collapse")


if __name__ == "__main__":
    unittest.main(verbosity=2)
