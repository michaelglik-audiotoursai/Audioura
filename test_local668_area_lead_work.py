"""test_local668_area_lead_work.py — LOCAL-668 deliverable #2.

Prefer works over areas: thin-verify runs to its bar first; area stops only fill
the slots the verified works could not. Each collection-area stop must NAME at
least one VERIFIED work (or artist) of THIS museum and lead with it. This test
exercises museum_fallback_stops.assign_lead_works / build_fallback_stops.
"""
import unittest

from museum_fallback_stops import build_fallback_stops, assign_lead_works

_VENUE = "Ho Chi Minh City Museum of Fine Arts"
_CORPUS = """
The Ho Chi Minh City Museum of Fine Arts occupies the former Hui Bon Hoa mansion.
It is renowned for its lacquer painting collection (sơn mài) and its silk painting
works, as well as woodblock prints.
"""

# The verified pool from the HCMC run: works confirmed at THIS museum.
_VERIFIED = [
    {"name": "North Central South Spring Garden", "artist": "Nguyễn Gia Trí",
     "medium": "lacquer", "verified": True},
    {"name": "The Red Boat", "artist": "", "verified": True,
     "thin_sources": [{"origin": "baotangmythuattphcm.com.vn"}]},
]


class AssignLeadWorks(unittest.TestCase):
    def test_every_area_stop_names_a_verified_work(self):
        areas = [
            {"name": "Lacquer painting collection", "_stop_kind": "collection_area"},
            {"name": "Silk painting collection", "_stop_kind": "collection_area"},
            {"name": "Woodblock prints collection", "_stop_kind": "collection_area"},
        ]
        assign_lead_works(areas, _VERIFIED)
        verified_names = {w["name"] for w in _VERIFIED}
        for a in areas:
            self.assertIn("_lead_work", a, f"{a['name']} has no lead work")
            self.assertIn(a["_lead_work"]["name"], verified_names,
                          "lead work must be a VERIFIED work of this museum")

    def test_medium_match_leads_lacquer_with_lacquer_work(self):
        areas = [{"name": "Lacquer painting collection", "_stop_kind": "collection_area"}]
        assign_lead_works(areas, _VERIFIED)
        # The lacquer-medium work is matched to the lacquer area.
        self.assertEqual(areas[0]["_lead_work"]["name"],
                         "North Central South Spring Garden")

    def test_no_verified_pool_is_safe(self):
        areas = [{"name": "Lacquer painting collection", "_stop_kind": "collection_area"}]
        assign_lead_works(areas, [])
        self.assertNotIn("_lead_work", areas[0])  # ships without a lead, no crash

    def test_build_fallback_attaches_lead_works(self):
        fb = build_fallback_stops(_VENUE, [], _CORPUS, needed=4, exclude_names=[],
                                  verified_works=_VERIFIED)
        area_stops = [s for s in fb if s.get("_stop_kind") == "collection_area"]
        self.assertTrue(area_stops, "expected at least one collection-area stop")
        for a in area_stops:
            self.assertTrue((a.get("_lead_work") or {}).get("name"),
                            f"{a['name']} must lead with a verified work")


if __name__ == "__main__":
    unittest.main(verbosity=2)
