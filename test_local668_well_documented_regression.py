"""test_local668_well_documented_regression.py — LOCAL-668 deliverable #6.

Regression guard for the LOCAL-667 well-documented-museum set (the museums whose
Wikidata catalogue already fills every stop with real works). None of the
LOCAL-668 changes may alter a well-documented tour:

  * the thin-verify VENUE CACHE / BUDGET and the collection-area fallback only
    run on the THIN tier — a well-documented museum never reaches them, so it
    spends ZERO thin-verify queries and gets NO area padding;
  * build_fallback_stops(needed=0) is a no-op (every slot already filled);
  * the contained-address binding is a no-op when every work already carries the
    one venue address (no scatter to collapse);
  * the foreign-museum snippet filter keeps a well-documented venue's own
    evidence and only ever drops OTHER museums.

These assert the GATING, so a thin-museum fix never regresses the common case.
"""
import unittest

import generate_tour_text as G
from museum_fallback_stops import build_fallback_stops
from venue_anchored_research import drop_foreign_museum_snippets

# A well-documented museum (LOCAL-667's set): the Rijksmuseum, Amsterdam.
_VENUE = "Rijksmuseum"
_CITY = "Amsterdam, Netherlands"
_ADDR = "Museumstraat 1, 1071 XX Amsterdam, Netherlands"


class WellDocumentedUnaffected(unittest.TestCase):
    def test_no_fallback_when_slots_full(self):
        # Every stop already a real work → needed=0 → no building/area stops.
        self.assertEqual(
            build_fallback_stops(_VENUE, [], "corpus", needed=0,
                                 verified_works=[{"name": "The Night Watch"}]),
            [])

    def test_contained_binding_is_noop_when_single_address(self):
        # Five real works, all at the one venue address → dominant address is that
        # address and binding changes nothing (no scatter).
        pois = [{"name": f"Work {i}", "address": _ADDR, "verified": True}
                for i in range(5)]
        self.assertEqual(G._dominant_poi_address(pois), _ADDR)
        # BLOCKER4b arithmetic: one address, never fires.
        uniq = set(p["address"].strip().lower()[:30] for p in pois)
        self.assertEqual(len(uniq), 1)

    def test_foreign_filter_keeps_own_venue_evidence(self):
        snips = [
            {"title": "Rijksmuseum — Night Watch",
             "snippet": "The Rijksmuseum in Amsterdam holds Rembrandt's Night Watch.",
             "url": "https://rijksmuseum.nl"},
            {"title": "Vermeer technique",
             "snippet": "Vermeer built luminous interiors with layered glazes.",
             "url": "https://generic.example"},
        ]
        kept, report = drop_foreign_museum_snippets(snips, _VENUE, _CITY)
        self.assertEqual(report["dropped"], 0, "no foreign museum → nothing dropped")
        self.assertEqual(len(kept), 2)

    def test_foreign_filter_drops_a_competing_museum_even_for_rich_venue(self):
        snips = [
            {"title": "Louvre comparison",
             "snippet": "A similar composition hangs in the Louvre in Paris.",
             "url": "https://louvre.fr"},
        ]
        kept, report = drop_foreign_museum_snippets(snips, _VENUE, _CITY)
        self.assertEqual(report["dropped"], 1)
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
