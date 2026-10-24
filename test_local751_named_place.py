#!/usr/bin/env python3
"""test_local751_named_place.py — LOCAL-751 part B2 (D562: never silently drop).

A place the LISTENER NAMED (intent `named_places`) must never be silently
dropped. On baseline 027584b0 the Danvers walking tour dropped the
"Witchcraft Victims Memorial" without a word:

    "named_places": ["Witchcraft Victims Memorial"],
    [UNVERIFIED] 'Witchcraft Victims Memorial' — no evidence
    DROPPED: 'Witchcraft Victims Memorial'

D562: a user-named place goes through the existence check with the RESOLVED
area. If it verifies, it is KEPT. If it cannot be verified it is ANNOUNCED in
the Orientation ("We could not confirm <name>, so it is not part of this
tour."), never swapped silently.

This test covers the two pure, deterministic decisions that implement the rule:

  * `build_named_place_announcement(name)` — the exact Orientation sentence.
  * `apply_named_place_policy(poi_list, named_places, area, landmarks, new_poi_fn)`
    — keeps a named place that matches a discovered landmark (marked
    user_explicit + verified, at the FRONT of the list) and returns an
    announcement for one that does not, NEVER dropping it silently.

RED on 027584b0: both symbols are absent from `area_resolver` (ImportError).
GREEN after the fix: a verifiable named place is kept; an unverifiable one is
announced.

Run: python3 -m pytest test_local751_named_place.py -q
"""
import unittest

import area_resolver as ar
from area_resolver import AreaResolution, Landmark


def _new_poi(name, address=""):
    return {"name": name, "address": address}


DANVERS = AreaResolution(
    city_qid="Q49231", city_name="Danvers",
    center_lat=42.575, center_lng=-70.93,
    bounding_radius_km=2.0, language="en", resolved=True,
)

# The real memorial IS on OSM/Wikidata in Danvers. Represent it as a discovered
# landmark so the existence check verifies it.
MEMORIAL = Landmark(
    name="Salem Village Witchcraft Victims' Memorial",
    qid="Q7405321", lat=42.5719, lng=-70.9497, type_label="memorial",
)


class TestNamedPlaceAnnouncement(unittest.TestCase):
    def test_announcement_sentence_names_the_place_and_excludes_it(self):
        text = ar.build_named_place_announcement("Witchcraft Victims Memorial")
        self.assertIn("Witchcraft Victims Memorial", text)
        low = text.lower()
        self.assertIn("could not confirm", low)
        self.assertIn("not part of this tour", low)


class TestNamedPlacePolicy(unittest.TestCase):
    def test_verifiable_named_place_is_kept_never_announced(self):
        poi_list = [{"name": "Danvers Town Common"}]
        out, announcements = ar.apply_named_place_policy(
            poi_list,
            named_places=["Witchcraft Victims Memorial"],
            area=DANVERS,
            landmarks=[MEMORIAL],
            new_poi_fn=_new_poi,
        )
        names = [p.get("name") for p in out]
        self.assertTrue(
            any("memorial" in (n or "").lower() for n in names),
            f"the named memorial was not kept in the tour: {names}",
        )
        # Kept, so nothing is announced about it.
        self.assertEqual(
            [], [a for a in announcements if "memorial" in a.lower()],
            f"a verified named place must not be announced as missing: {announcements}",
        )
        # The kept stop carries the user_explicit flag so downstream never drops it.
        _kept = [p for p in out if "memorial" in (p.get("name") or "").lower()]
        self.assertTrue(_kept and _kept[0].get("user_explicit"),
                        "kept named place must be flagged user_explicit")

    def test_unverifiable_named_place_is_announced_never_silently_dropped(self):
        poi_list = [{"name": "Danvers Town Common"}]
        out, announcements = ar.apply_named_place_policy(
            poi_list,
            named_places=["Witchcraft Victims Memorial"],
            area=DANVERS,
            landmarks=[],  # nothing discovered → cannot verify from landmarks
            new_poi_fn=_new_poi,
        )
        # It must be announced — not vanished.
        self.assertTrue(
            any("Witchcraft Victims Memorial" in a for a in announcements),
            f"an unverifiable named place must be announced, got {announcements}",
        )
        joined = " ".join(announcements).lower()
        self.assertIn("could not confirm", joined)
        self.assertIn("not part of this tour", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
