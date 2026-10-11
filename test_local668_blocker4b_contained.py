"""test_local668_blocker4b_contained.py — LOCAL-668.

Normal-arm fixture from ~/Audioura/.continuous_dev/bench/AB11/hcmc_off_rejected.log
(2026-10-10 20:00). On that run BLOCKER4b reported "2 distinct addresses for 5
stops" and rejected the tour as "a city-wide museum tour". The two distinct
addresses came from:

  * the Phase-3A verified work "North Central South Spring Garden", carrying the
    museum address "97A Phó Đức Chính, …, Ho Chi Minh City, Vietnam";
  * the thin-verified work "The Red Boat" (promoted from the R4-dropped pool),
    which carried a DIFFERENT model-guessed address;

plus three LOCAL-667 fallback stops (building + lacquer + silk) with EMPTY
addresses. Both the stray thin-tier address and the empty fallback addresses are
wrong: every stop is INSIDE the museum. This test locks in the LOCAL-668 fix —
every contained stop is bound to the venue address, so the tour has ONE address
and BLOCKER4b does not fire.

The test reproduces the exact BLOCKER4b arithmetic and the module-level helper
(_dominant_poi_address) and binding step from generate_tour_text.py.
"""
import unittest

import generate_tour_text as G
from about_museum_stop import venue_bound_address
from museum_fallback_stops import build_fallback_stops


_VENUE = "Ho Chi Minh City Museum of Fine Arts"
_ADDR = "97A Phó Đức Chính, Nguyễn Thái Bình, Quận 1, Ho Chi Minh City, Vietnam"
# A plausible stray address a replenishment round could assign to The Red Boat.
_STRAY = "12 Nguyen Hue Boulevard, District 1, Ho Chi Minh City, Vietnam"

_CORPUS = """
The Ho Chi Minh City Museum of Fine Arts occupies the former Hui Bon Hoa mansion,
built in the late 1920s, a landmark of colonial architecture in Quận 1.
The museum is renowned for its lacquer painting collection (sơn mài) and its silk
painting works, as well as woodblock prints and ceramics from southern Vietnam.
"""


def _blocker4b_unique_addresses(poi_list):
    uniq = set()
    for p in poi_list:
        addr = (p.get('address') or '').strip().lower()
        if addr and len(addr) > 10:
            uniq.add(addr[:30])
    return uniq


def _blocker4b_fires(poi_list):
    uniq = _blocker4b_unique_addresses(poi_list)
    return len(uniq) >= len(poi_list) // 2 and len(poi_list) >= 5


def _bind_contained(poi_list, single_venue=True):
    """The LOCAL-668 binding pass, mirroring generate_tour_text.py."""
    venue_addr = G._dominant_poi_address(poi_list)
    if not (venue_addr and len(venue_addr) > 10):
        return poi_list
    for cp in poi_list:
        contained = (
            single_venue
            or cp.get('_stop_kind') in ('building', 'collection_area')
            or cp.get('_fallback_source')
            or 'thin_sources' in cp
            or not (cp.get('address') or '').strip()
        )
        if not contained:
            continue
        new = venue_bound_address(cp.get('address', ''), venue_addr,
                                  cp.get('_source_page_text', '') or '')
        if new:
            cp['address'] = new
    return poi_list


def _hcmc_fixture():
    """The 5-stop poi_list exactly as the rejected run built it."""
    poi = [
        {"name": "North Central South Spring Garden", "address": _ADDR,
         "verified": True},
        {"name": "The Red Boat", "address": _STRAY, "verified": True,
         "thin_sources": [{"origin": "baotangmythuattphcm.com.vn"},
                          {"origin": "vietnamtourism.gov.vn"}]},
    ]
    fb = build_fallback_stops(_VENUE, [], _CORPUS, needed=3,
                              exclude_names=[p["name"] for p in poi])
    poi.extend(fb)
    return poi


class DominantAddress(unittest.TestCase):
    def test_picks_majority_address(self):
        pois = [{"name": "A", "address": _ADDR}, {"name": "B", "address": _ADDR},
                {"name": "C", "address": ""}]
        self.assertEqual(G._dominant_poi_address(pois), _ADDR)

    def test_empty_when_no_usable_address(self):
        pois = [{"name": "A", "address": ""}, {"name": "B", "address": "short"}]
        self.assertEqual(G._dominant_poi_address(pois), "")


class Blocker4bContained(unittest.TestCase):
    def test_fixture_reproduces_rejection_before_binding(self):
        """RED: raw fixture → 2 distinct addresses → BLOCKER4b fires."""
        poi = _hcmc_fixture()
        self.assertEqual(len(poi), 5)
        uniq = _blocker4b_unique_addresses(poi)
        self.assertEqual(len(uniq), 2, f"fixture must have 2 addresses, got {uniq}")
        self.assertTrue(_blocker4b_fires(poi),
                        "fixture must reproduce the real rejection")

    def test_binding_yields_one_address_and_no_rejection(self):
        """GREEN: after binding, one address → BLOCKER4b does NOT fire."""
        poi = _bind_contained(_hcmc_fixture())
        uniq = _blocker4b_unique_addresses(poi)
        self.assertEqual(len(uniq), 1, f"contained tour must have ONE address, got {uniq}")
        self.assertFalse(_blocker4b_fires(poi),
                         "BLOCKER4b must NOT fire on a contained, single-address tour")
        for p in poi:
            self.assertEqual((p["address"] or "").strip(), _ADDR)

    def test_two_verified_works_with_different_addresses_collapse(self):
        """Live NORMAL-arm case: two thin-verified works carried DIFFERENT
        model-guessed addresses; binding every stop of a single named venue
        collapses them to ONE so BLOCKER4b does not fire."""
        poi = [
            {"name": "Lotus Pond", "address": _ADDR, "verified": True,
             "thin_sources": [{"origin": "vnfam.vn"}]},
            {"name": "Mother and Child", "address": _STRAY, "verified": True,
             "thin_sources": [{"origin": "baotangmythuattphcm.com.vn"}]},
            {"name": "The Ho Chi Minh City Museum of Fine Arts building",
             "address": "", "_stop_kind": "building"},
            {"name": "Lacquer painting collection", "address": "",
             "_stop_kind": "collection_area"},
            {"name": "Silk painting collection", "address": "",
             "_stop_kind": "collection_area"},
        ]
        self.assertEqual(len(_blocker4b_unique_addresses(poi)), 2)
        _bind_contained(poi, single_venue=True)
        uniq = _blocker4b_unique_addresses(poi)
        self.assertEqual(len(uniq), 1,
                         f"single named venue must collapse to ONE address, got {uniq}")
        self.assertFalse(_blocker4b_fires(poi))

    def test_binding_keeps_a_page_sourced_satellite_address(self):
        """A stop whose OWN page states a satellite address keeps it (D611)."""
        poi = _hcmc_fixture()
        poi[1]["_source_page_text"] = (
            "The Red Boat hangs in the museum annex at " + _STRAY + ".")
        _bind_contained(poi)
        # venue_bound_address keeps the page-literal satellite address.
        self.assertEqual(poi[1]["address"], _STRAY)

    def test_fallback_stops_are_inside_the_museum(self):
        fb = build_fallback_stops(_VENUE, [], _CORPUS, needed=3, exclude_names=[])
        kinds = {s.get("_stop_kind") for s in fb}
        self.assertTrue(kinds <= {"building", "collection_area"}, f"kinds: {kinds}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
