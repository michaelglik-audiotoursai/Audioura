#!/usr/bin/env python3
"""test_local879_claim_gate_false_facts.py — LOCAL-879 §4.

Four false/mis-stated claims shipped past the LOCAL-872 landmark claim gate in
tour 547. Each is fixed against the stop's own Wikipedia evidence:

  * Stop 4 (Palace): "This assassination, which took place within the walls of
    the still-unfinished palace" — FALSE (Diệm/Nhu killed in an armoured
    personnel carrier after fleeing to Cholon). DROPPED.
  * Stop 5 (War Remnants): "served as the U.S. military's intelligence
    headquarters" — the evidence names the United States Information Agency.
    CORRECTED in place ("intelligence" -> "Information Agency").
  * Stop 9 (Pier): "established at the beginning of the 19th century" — unsourced
    century founding. DROPPED.
  * Stop 4 (Palace): "It is sometimes said that … damaged by bombing from
    dissident pilots" — a SOURCED fact (the 1962 bombing is on Wikipedia) must
    not carry a hedge. UNWRAPPED.

Run: python3 -m pytest tests/test_local879_claim_gate_false_facts.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import landmark_claim_gate as lg

PALACE_EV = (
    "Independence Palace. Designed by architect Ngô Viết Thụ, construction began "
    "in 1962 and was completed in 1966. In 1962 two dissident Republic of Vietnam "
    "Air Force pilots bombed the palace. During the November 1963 coup, Ngô Đình "
    "Diệm and his brother Ngô Đình Nhu fled to Cholon and were killed in an "
    "armoured personnel carrier (an M113).")
WAR_EV = (
    "War Remnants Museum. Established in 1975, the museum occupies a building that "
    "formerly housed the United States Information Agency. It contains exhibits on "
    "the Vietnam War.")
PIER_EV = (
    "Bạch Đằng Pier is a wharf on the Saigon River in District 1, used for ferries "
    "and sightseeing boats.")


def _run(tour):
    kw = dict(
        stop_evidence={1: [PALACE_EV], 2: [WAR_EV], 3: [PIER_EV]},
        stop_authority={1: [PALACE_EV], 2: [WAR_EV], 3: [PIER_EV]},
        stop_titles={1: "Independence Palace", 2: "War Remnants Museum",
                     3: "Bạch Đằng Pier"},
        location="Ho Chi Minh City, Vietnam")
    return lg.filter_tour_text(tour, **kw)


TOUR = """Stop 1: Independence Palace
It is sometimes said that a turning point came in the early 1960s, when President Ngô Đình Diệm ordered the palace reconstruction after the previous building was damaged by bombing from dissident pilots. This assassination, which took place within the walls of the still-unfinished palace, marked a violent rupture.

Stop 2: War Remnants Museum
It occupies a building that once served as the U.S. military's intelligence headquarters during the Vietnam War. Established in 1975, the museum centers on the Vietnam War.

Stop 3: Bạch Đằng Pier
Bạch Đằng Pier was established at the beginning of the 19th century, making it one of Saigon's earliest formal river landings. The pier is a departure point for boat tours.
"""


class TestFalseFactsGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.out, cls.rep = _run(TOUR)

    def test_palace_death_location_dropped(self):
        self.assertNotIn("within the walls", self.out)
        self.assertNotIn("took place within the walls of the still-unfinished",
                         self.out)

    def test_war_museum_information_not_intelligence(self):
        self.assertNotIn("intelligence", self.out.lower())
        self.assertIn("United States Information Agency building", self.out)

    def test_pier_unsourced_century_dropped(self):
        self.assertNotIn("19th century", self.out)
        self.assertNotIn("established at the beginning", self.out)
        # the sourced generic sentence survives
        self.assertIn("departure point for boat tours", self.out)

    def test_sourced_bombing_hedge_unwrapped(self):
        self.assertNotIn("sometimes said", self.out.lower())
        self.assertIn("damaged by bombing from dissident pilots", self.out)

    def test_idempotent(self):
        out2, _ = _run(self.out)
        self.assertEqual(out2, self.out)


class TestUnitHelpers(unittest.TestCase):

    def test_dated_claims_catches_century(self):
        bad = lg.dated_claims(
            "Bạch Đằng Pier was established at the beginning of the 19th century.",
            lg._fold(PIER_EV))
        self.assertTrue(any("19th century" in b for b in bad),
                        f"century claim must be flagged: {bad}")

    def test_dated_claims_keeps_sourced_century(self):
        ev = lg._fold("The pier dates from the 19th century.")
        bad = lg.dated_claims("It was established in the 19th century.", ev)
        self.assertEqual(bad, [], f"a sourced century must not be flagged: {bad}")

    def test_evidence_contradiction_death(self):
        r = lg.evidence_text_contradiction(
            "This assassination took place within the walls of the palace.",
            lg._fold(PALACE_EV))
        self.assertIsNotNone(r)
        self.assertIsNone(r[2], "death contradiction is a DROP (no replacement)")

    def test_evidence_contradiction_intelligence(self):
        r = lg.evidence_text_contradiction(
            "a building that once served as the U.S. military's intelligence headquarters.",
            lg._fold(WAR_EV))
        self.assertIsNotNone(r)
        self.assertIn("Information Agency", r[2])

    def test_unwrap_sourced_hedge(self):
        de = lg.unwrap_sourced_hedge(
            "It is sometimes said that the palace was damaged by bombing from "
            "dissident pilots in 1962.", lg._fold(PALACE_EV))
        self.assertIsNotNone(de)
        self.assertFalse(de.lower().startswith("it is sometimes said"))

    def test_unwrap_leaves_unsourced_hedge(self):
        de = lg.unwrap_sourced_hedge(
            "It is sometimes said that a dragon once guarded this gate.",
            lg._fold(PIER_EV))
        self.assertIsNone(de, "an UNsourced hedge stays hedged")


if __name__ == "__main__":
    unittest.main(verbosity=2)
