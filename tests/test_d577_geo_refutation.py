"""[D577] Never ship what we can refute — tested against the two real failures."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import geo_refutation as gr

NEWTON = (42.3370, -71.2092)      # Our Lady Help of Christians, Newton MA
GAZETTEER = {
    'los angeles': (34.0522, -118.2437),
    'vatican city': (41.9029, 12.4534),
    'milan': (45.4642, 9.1900),
    'boston': (42.3601, -71.0589),
    'ireland': (53.1424, -7.6921),
    'paris': (48.8566, 2.3522),
    'newton': (42.3370, -71.2092),
}
def geo(name):
    return GAZETTEER.get((name or '').strip().lower())


class TestTheTwoRealFailures(unittest.TestCase):
    def test_d567_archbishop_of_los_angeles_is_refuted(self):
        """The sentence that shipped in today's church tour at 100% reported confidence."""
        text = ("The parish was canonically recognized in 1966 by Cardinal James Francis "
                "McIntyre, Archbishop of Los Angeles.")
        rec = gr.refute_claims(text, NEWTON, geo)
        self.assertEqual(len(rec["refuted"]), 1, rec)
        self.assertEqual(rec["refuted"][0]["place"], "Los Angeles")
        self.assertGreater(rec["refuted"][0]["km"], 4000)

    def test_d564_sistine_chapel_stop_is_refuted(self):
        r = gr.refute_stop_by_distance("Sistine Chapel Ceiling (Vatican City)", NEWTON, geo)
        self.assertIsNotNone(r)
        self.assertGreater(r["km"], 6000)


class TestLegitimateHistoryKeepsShipping(unittest.TestCase):
    """D577: unverified ships. A distant place MENTIONED is not a binding claim."""

    def test_irish_immigrants_are_not_refuted(self):
        text = ("In the 1870s, this place of worship began as a refuge for Irish Catholic "
                "immigrants in Nonantum, who faced nativist prejudice.")
        self.assertEqual(gr.refute_claims(text, NEWTON, geo)["refuted"], [])

    def test_training_abroad_is_not_refuted(self):
        text = "The architect trained in Paris before returning to Massachusetts."
        self.assertEqual(gr.refute_claims(text, NEWTON, geo)["refuted"], [])

    def test_correct_jurisdiction_is_not_refuted(self):
        text = "The parish belongs to the Archdiocese of Boston."
        self.assertEqual(gr.refute_claims(text, NEWTON, geo)["refuted"], [])

    def test_unresolvable_place_is_unverified_not_refuted(self):
        text = "The parish was recognized by the Bishop of Nowherecester."
        rec = gr.refute_claims(text, NEWTON, geo)
        self.assertEqual(rec["refuted"], [])
        self.assertIn("Nowherecester", rec["unresolved"])

    def test_a_nearby_stop_is_not_refuted(self):
        self.assertIsNone(gr.refute_stop_by_distance("Cimiez Monastery (Newton)", NEWTON, geo))


class TestAgainstRealTourText(unittest.TestCase):
    """The fixture tests passed while the module FAILED on real prose: the name
    pattern swallowed "Los Angeles. His" across the sentence boundary and then could
    not geocode it, so the refuted claim shipped. Fixtures were too clean. This class
    uses sentences exactly as the generator emitted them."""

    REAL_CHURCH_SENTENCE = ("The parish was canonically recognized in 1966 by Cardinal "
                            "James Francis McIntyre, Archbishop of Los Angeles. His act "
                            "marked a significant transition from mission to parish status, "
                            "solidifying its place in the community.")

    def test_the_claim_that_actually_shipped_is_refuted(self):
        rec = gr.refute_claims(self.REAL_CHURCH_SENTENCE, NEWTON, geo)
        self.assertEqual([r["place"] for r in rec["refuted"]], ["Los Angeles"], rec)
        self.assertGreater(rec["refuted"][0]["km"], 4000)

    def test_place_name_never_spans_a_sentence_boundary(self):
        found = gr.find_bound_places(self.REAL_CHURCH_SENTENCE)
        self.assertEqual(found[0][0], "Los Angeles",
                         "the capture must stop at the full stop, not run into 'His'")

    def test_abbreviation_dots_still_survive(self):
        self.assertEqual(gr.find_bound_places("located in Washington D.C.")[0][0],
                         "Washington D.C.")


class TestItCanFail(unittest.TestCase):
    """D242: break it and watch it go red."""

    def test_raising_the_threshold_lets_los_angeles_through(self):
        text = "recognized by Cardinal McIntyre, Archbishop of Los Angeles."
        self.assertEqual(len(gr.refute_claims(text, NEWTON, geo)["refuted"]), 1)
        loose = gr.refute_claims(text, NEWTON, geo, refute_km=50000)
        self.assertEqual(loose["refuted"], [], "with the threshold disabled the LA claim "
                                               "must pass through — the red state")


if __name__ == '__main__':
    unittest.main()
