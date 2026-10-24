#!/usr/bin/env python3
"""test_local751_named_place_delivery.py — LOCAL-751 B2 end-to-end splice.

The field DANVERS live run silently dropped "Witchcraft Victims Memorial": the
AI intent call returned HTTP 429, so `intent.named_places` was [] and the
existence gate removed the memorial without a word (D562 violation). The fix has
two halves and this test exercises the whole chain with the REAL helpers, no
paid API:

  1. The request's "including …" clause is parsed DETERMINISTICALLY into the
     named place(s) — independent of the intent model
     (area_resolver.extract_named_places_from_clause).
  2. The named-place policy ANNOUNCES an unverifiable named place
     (area_resolver.apply_named_place_policy → build_named_place_announcement).
  3. The announcement is spliced into the delivered tour's Orientation opening by
     the same call the every-path delivery guard makes
     (screen_work_tour.inject_orientation_disclosure) — so the LISTENER hears it.

The delivered-text fixture is the shape the generator produced in the field
(a walking tour with an "Orientation:" label), so this proves the sentence lands
at the opening of a real delivered tour.

RED on 027584b0: extract_named_places_from_clause / apply_named_place_policy /
build_named_place_announcement do not exist (ImportError).

Run: python3 -m pytest test_local751_named_place_delivery.py -q
"""
import unittest

import area_resolver as ar
import screen_work_tour as swt
from area_resolver import AreaResolution


def _new_poi(name, address=""):
    return {"name": name, "address": address}


# A delivered walking tour in the field shape (carries an "Orientation:" label,
# as the real Danvers delivery did).
DELIVERED = """Step-by-Step Audio Guided Tour: Walking tour in Danvers, MA including Witchcraft Victims Memorial
Tour-Category: walking

Stop 1: The Danvers Historical Society

Address: 11 Page St, Danvers, MA 01923

Orientation: We could confirm 2 stops along this route, so this tour has 2 stops rather than the 4 you asked for. From the Danvers MBTA station, head northeast on Maple St.

The Danvers Historical Society, founded in 1889, guards local heritage.

Stop 2: The Danvers State Hospital

Address: 18 Hospital Rd, Danvers, MA 01923
"""

DANVERS = AreaResolution(city_qid="Q1066487", city_name="Danvers",
                         center_lat=42.575, center_lng=-70.93,
                         bounding_radius_km=2.0, language="en", resolved=True)

REQUEST = "Walking tour in Danvers, MA including Witchcraft Victims Memorial"


class TestNamedPlaceDeliverySplice(unittest.TestCase):
    def test_clause_to_announcement_to_orientation(self):
        # (1) intent gave nothing (429 in the field) — recover names from the clause.
        names = ar.extract_named_places_from_clause(REQUEST)
        self.assertEqual(["Witchcraft Victims Memorial"], names)

        # (2) policy: the memorial is not among discovered landmarks → ANNOUNCE.
        poi_list, announcements = ar.apply_named_place_policy(
            [{"name": "The Danvers Historical Society"}],
            named_places=names, area=DANVERS, landmarks=[], new_poi_fn=_new_poi)
        self.assertTrue(announcements, "policy produced no announcement")
        np_text = " ".join(a.strip() for a in announcements if a.strip()).strip()
        self.assertIn("Witchcraft Victims Memorial", np_text)

        # (3) delivery splice: exactly what _apply_delivery_hours_guard does.
        before = DELIVERED
        final = swt.inject_orientation_disclosure(before, np_text)
        self.assertNotEqual(before, final, "announcement was not spliced in")

        # The sentence must land INSIDE the Orientation opening, before the route.
        orient_idx = final.index("Orientation:")
        ann_idx = final.index("We could not confirm Witchcraft Victims Memorial")
        route_idx = final.index("From the Danvers MBTA station")
        self.assertLess(orient_idx, ann_idx,
                        "announcement must come after the Orientation label")
        self.assertLess(ann_idx, route_idx,
                        "announcement must lead the Orientation, before the route text")
        self.assertIn("so it is not part of this tour", final)

    def test_splice_is_idempotent(self):
        names = ar.extract_named_places_from_clause(REQUEST)
        _, announcements = ar.apply_named_place_policy(
            [{"name": "X"}], named_places=names, area=DANVERS,
            landmarks=[], new_poi_fn=_new_poi)
        np_text = " ".join(announcements).strip()
        once = swt.inject_orientation_disclosure(DELIVERED, np_text)
        twice = swt.inject_orientation_disclosure(once, np_text)
        self.assertEqual(once, twice, "splice must not double the announcement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
