#!/usr/bin/env python3
"""test_local634_provenance_namesake.py — [LOCAL-634] defect: invented role.

National Gallery (tour 495) shipped "John Arrowsmith, a notable 19th-century
cartographer, purchased it" — the buyer was John Arrowsmith the ART DEALER, not
the cartographer. The biographical gloss came from the corpus/model gloss path
(supply_glosses) binding the name to a NAMESAKE, because the person appears only
as a provenance AGENT (a buyer), not among the stop's own documented sources.

Rule (D-LOCAL-634): a gloss for a person in a provenance sentence must come from
that stop's OWN record. If no documented role exists (stage 2b found none), the
reference is DEGRADED rather than namesake-glossed from the open web.

Run: python3 -m pytest test_local634_provenance_namesake.py -q
"""
import unittest

import unglossed_reference_gate as u


class TestProvenanceSentenceDetector(unittest.TestCase):
    def test_purchase_is_provenance(self):
        self.assertTrue(u._is_provenance_sentence(
            "John Arrowsmith, a notable cartographer, purchased it in 1832."))

    def test_gift_bequest_acquired_are_provenance(self):
        for s in ("It was a gift of Samuel Courtauld.",
                  "The work was bequeathed by Roger Fry.",
                  "The museum acquired the panel in 1921.",
                  "It entered the collection of the gallery after the war.",
                  "Commissioned by the Duke, the altarpiece was finished in 1510."):
            self.assertTrue(u._is_provenance_sentence(s), s)

    def test_artwork_statement_is_not_provenance(self):
        for s in ("Velazquez painted the royal family in 1656.",
                  "Picasso condemned the bombing of Guernica.",
                  "The brushwork is loose and rapid."):
            self.assertFalse(u._is_provenance_sentence(s), s)


class TestSupplyGlossesDegradesProvenanceNamesake(unittest.TestCase):
    def test_provenance_buyer_without_record_is_degraded_not_glossed(self):
        # A reference to a buyer in a provenance sentence, with NO corpus fact and
        # NO documented role → must be DEGRADED here, never sent to the model for a
        # (namesake) gloss. We pass NO api_key and NO corpus so the only way it
        # could get a fact is the (now-blocked) namesake path.
        refs = [{
            "entity": "John Arrowsmith",
            "category": "person",
            "triage": "gloss_needed",
            "sentence": ("John Arrowsmith, a dealer, purchased it from the artist "
                         "in 1832."),
        }]
        out, tokens, cost, _lat = u.supply_glosses(refs, corpus_passages=[],
                                                   api_key="", model=None)
        self.assertEqual(out[0]["stage"], "degrade")
        self.assertIsNone(out[0]["raw_fact"])
        self.assertIn("LOCAL-634", out[0].get("degrade_reason", ""))
        self.assertEqual(tokens, 0)

    def test_provenance_record_ref_is_untouched(self):
        # A ref that stage 2b already glossed from the stop record carries
        # provenance=True and must NOT be degraded by this guard (LOCAL-494).
        refs = [{
            "entity": "Boris Fridman",
            "category": "person",
            "triage": "gloss_needed",
            "provenance": True,
            "gloss": "the collector who gave this work to the museum",
            "sentence": "It was a gift of Boris Fridman to the museum.",
        }]
        out, _t, _c, _l = u.supply_glosses(refs, corpus_passages=[],
                                           api_key="", model=None)
        # Untouched: still the provenance gloss, not degraded.
        self.assertTrue(out[0].get("provenance"))
        self.assertNotEqual(out[0].get("stage"), "degrade")

    def test_non_provenance_person_still_eligible_for_gloss(self):
        # A non-provenance person reference is NOT caught by this guard; with no
        # api_key/corpus it falls through to the normal stage-3c degrade, but
        # crucially WITHOUT the provenance degrade_reason (the guard did not fire).
        refs = [{
            "entity": "Diego Velazquez",
            "category": "person",
            "triage": "gloss_needed",
            "sentence": "Velazquez painted the royal family in 1656.",
        }]
        out, _t, _c, _l = u.supply_glosses(refs, corpus_passages=[],
                                           api_key="", model=None)
        self.assertNotIn("LOCAL-634", out[0].get("degrade_reason", "") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
