#!/usr/bin/env python3
"""test_local858b_cloud_pins.py — LOCAL-858B.

Bounce of LOCAL-858: on Cloud Run the HCMC landmark pins were STILL wrong for
tour 532 ("Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City").

ROOT CAUSE (from the cloud log): the LLM intent's ``geographic_scope`` was
"Ben Thanh Market and Saigon Opera House walk" — the CITY was lost. area_resolver
logged "Could not resolve city"; the scope-less string geocoded to Vietnam's
COUNTRY centroid (15.93,107.97); pin-snap took that as its centre, so the centroid
guard cleared 0 pins and the 858 landmark lookup was skipped SILENTLY. The three
stops shipped ~700 m off, all within ~150 m of one another (NOT ≤ 30 m, so the
LOCAL-858 equality test missed them).

This suite, fully offline, asserts the LOCAL-858B fixes:

  Item 0 — ``_city_center_for_request`` NEVER returns a country/state centroid
           and resolves the city from the ORIGINAL request's city tail even when
           the scope (geographic_scope) dropped it. ``geocode_stops.is_city_like``
           rejects a country/state Nominatim result.
  Item 2 — ``landmark_second_authority.lookup_second_authority`` resolves a
           landmark via Serper /places (then Nominatim) when Wikidata is blocked,
           name-matched and in-scope; and pin_snap uses it.
  Item 3 — CLUSTER detection: the exact tour-532 shipped pins (≈150 m apart, no
           reference) are a collapse — all cleared + announced — while genuinely
           same-building and user pins are exempt.

Run: python3 -m pytest test_local858b_cloud_pins.py -q
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pin_snap
import geocode_stops
import landmark_second_authority as l2a


# ─────────────────────────── the EXACT tour-532 data ────────────────────────
# The request string the listener typed (carries the city tail).
REQ_532 = "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"
# The intent's geographic_scope on the cloud — the CITY was lost.
SCOPE_532_CITYLESS = "Ben Thanh Market and Saigon Opera House walk"

# Real P625 pins.
REAL = {
    "Ben Thanh Market": (10.7725, 106.6980),
    "Saigon Opera House": (10.7764, 106.7028),
}
# The WRONG pins tour 532 shipped (from the ClickUp log) — ~700 m off the real
# places, and all three within ~150 m of EACH OTHER.
SHIPPED_532 = {
    "Ben Thanh Market": (10.7768, 106.6943),
    "Saigon Opera House": (10.7763, 106.6956),
    "Saigon Notre-Dame Basilica": (10.7797, 106.6990),
}
VIETNAM_COUNTRY_CENTROID = (15.93, 107.97)
HCMC_CENTER = (10.7769, 106.7009)


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


# ══════════════════════════════ item 0 ══════════════════════════════════════
class TestIsCityLikeRejectsCountryCentroid(unittest.TestCase):
    """``geocode_stops.is_city_like`` tells a city from a country/state centroid
    by Nominatim's own classification."""

    def test_country_is_not_city_like(self):
        self.assertFalse(geocode_stops.is_city_like({
            "addresstype": "country", "class": "boundary",
            "type": "administrative"}))

    def test_state_and_region_are_not_city_like(self):
        for at in ("state", "province", "region", "county"):
            self.assertFalse(geocode_stops.is_city_like(
                {"addresstype": at, "class": "boundary",
                 "type": "administrative"}),
                f"{at} wrongly accepted as a city")

    def test_city_and_landmark_are_city_like(self):
        self.assertTrue(geocode_stops.is_city_like({
            "addresstype": "city", "class": "place", "type": "city"}))
        self.assertTrue(geocode_stops.is_city_like({
            "addresstype": "suburb", "class": "place", "type": "suburb"}))
        self.assertTrue(geocode_stops.is_city_like({
            "addresstype": "amenity", "class": "amenity", "type": "marketplace"}))

    def test_empty_is_not_city_like(self):
        self.assertFalse(geocode_stops.is_city_like(None))
        self.assertFalse(geocode_stops.is_city_like({}))


class TestCityCenterNeverCountryCentroid(unittest.TestCase):
    """[LOCAL-858B item 0] The exact tour-532 failure: the scope (geographic_scope)
    lost the city and geocodes to the COUNTRY centroid, while the ORIGINAL request
    carries "…, Ho Chi Minh City". ``_city_center_for_request`` must REJECT the
    country centroid and return the real city centre from the request's city tail.
    Fully offline — ``geocode_detailed``/``geocode`` are monkeypatched."""

    def _run(self, monkeypatched_detailed):
        import generate_tour_text as g
        import geocode_stops as gs
        _saved_d = gs.geocode_detailed
        _saved_g = gs.geocode
        gs.geocode_detailed = monkeypatched_detailed

        def _plain(q):
            det = monkeypatched_detailed(q)
            return (det["lat"], det["lng"]) if det else None
        gs.geocode = _plain
        try:
            intent = {"geographic_scope": SCOPE_532_CITYLESS}
            return g._city_center_for_request(
                REQ_532, scope=SCOPE_532_CITYLESS, intent=intent)
        finally:
            gs.geocode_detailed = _saved_d
            gs.geocode = _saved_g

    def test_returns_city_not_country_centroid(self):
        # A fake geocoder: the city-less scope resolves to the COUNTRY centroid;
        # only a query that contains "Ho Chi Minh City" resolves to the city.
        def _fake_detailed(q):
            ql = (q or "").lower()
            if "ho chi minh city" in ql or ql.strip() == "ho chi minh city":
                return {"lat": HCMC_CENTER[0], "lng": HCMC_CENTER[1],
                        "type": "city", "class": "place", "addresstype": "city",
                        "display_name": "Ho Chi Minh City, Vietnam"}
            # Anything else (the city-less scope, the walk phrase) → Vietnam.
            return {"lat": VIETNAM_COUNTRY_CENTROID[0],
                    "lng": VIETNAM_COUNTRY_CENTROID[1],
                    "type": "administrative", "class": "boundary",
                    "addresstype": "country", "display_name": "Vietnam"}

        center = self._run(_fake_detailed)
        self.assertIsNotNone(center, "no city centre resolved")
        self.assertGreater(
            _hav_m(center, VIETNAM_COUNTRY_CENTROID), 100000.0,
            "returned the Vietnam COUNTRY centroid as the city centre")
        self.assertLessEqual(
            _hav_m(center, HCMC_CENTER), 5000.0,
            "did not resolve the real Ho Chi Minh City centre from the city tail")

    def test_no_city_tail_returns_none_not_country(self):
        """When NOTHING resolves to a city (only the country centroid is on
        offer), the resolver returns None rather than a country centroid."""
        def _only_country(q):
            return {"lat": VIETNAM_COUNTRY_CENTROID[0],
                    "lng": VIETNAM_COUNTRY_CENTROID[1],
                    "type": "administrative", "class": "boundary",
                    "addresstype": "country", "display_name": "Vietnam"}
        center = self._run(_only_country)
        self.assertIsNone(
            center, "a country centroid must never be returned as a city centre")


# ══════════════════════════════ item 3 ══════════════════════════════════════
class TestTour532ClusterCollapse(unittest.TestCase):
    """[LOCAL-858B item 3] The exact tour-532 shipped pins — Ben Thanh Market and
    the Saigon Opera House ship ~152 m apart (NOT ≤ 30 m) with NO reference — are a
    cluster collapse: both pins are cleared and announced. (≤ 30 m equality would
    have missed them.)"""

    def _pois(self):
        return [{"name": n, "coordinates": f"{c[0]:.6f}, {c[1]:.6f}"}
                for n, c in (("Ben Thanh Market", SHIPPED_532["Ben Thanh Market"]),
                             ("Saigon Opera House",
                              SHIPPED_532["Saigon Opera House"]))]

    def test_the_two_shipped_pins_are_between_30m_and_250m_apart(self):
        d = _hav_m(SHIPPED_532["Ben Thanh Market"],
                   SHIPPED_532["Saigon Opera House"])
        self.assertGreater(d, 30.0,
                           "pins must be > 30 m apart to prove the CLUSTER test "
                           "(not the ≤30 m equality test) is what fires")
        self.assertLessEqual(d, 250.0,
                             "pins must be within the 250 m cluster radius")

    def test_cluster_collapse_clears_and_announces_both(self):
        logs = []
        # No reference available anywhere (Wikidata blocked, no Serper/Nominatim):
        # reference_fn + landmark_fn both return None, so every stop is
        # reference-less and the cluster test is what clears them.
        out, rows = pin_snap.snap_poi_coordinates(
            self._pois(), scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
            reference_fn=lambda n: None, landmark_fn=lambda n: None,
            city_centroid=None, log=logs.append)
        for p in out:
            self.assertEqual(p["coordinates"], "",
                             f"{p['name']} kept a collapsed cluster pin")
            self.assertTrue(p.get("_no_coordinate"))
        self.assertEqual(sum(1 for r in rows if r.get("cluster_collapsed")), 2)
        self.assertTrue(any("cluster collapse" in m for m in logs))
        self.assertEqual(
            sum(1 for m in logs if m.startswith("[LOCAL-858] no coordinate")), 2)

    def test_cluster_collapse_fires_without_city_centroid(self):
        """The cloud centre was the COUNTRY centroid ~700 m from the cluster, so
        the city_centroid test could not fire. Cluster detection must stand on its
        own (no city_centroid supplied)."""
        out, rows = pin_snap.snap_poi_coordinates(
            self._pois(), scope="Ho Chi Minh City",
            scope_center=VIETNAM_COUNTRY_CENTROID,  # the cloud's wrong centre
            reference_fn=lambda n: None, landmark_fn=lambda n: None,
            city_centroid=None, log=lambda _m: None)
        self.assertEqual(sum(1 for r in rows if r.get("cluster_collapsed")), 2)


class TestClusterExemptions(unittest.TestCase):
    """Same-building adjacency and user pins are NOT a cluster collapse."""

    def test_same_building_stalls_are_not_collapsed(self):
        # Two stalls in one market: same Wikidata QID → same_building → exempt.
        pois = [
            {"name": "Stall 14, Ben Thanh Market",
             "coordinates": "10.772600, 106.698100", "wikidata_qid": "Q999"},
            {"name": "Stall 30, Ben Thanh Market",
             "coordinates": "10.772650, 106.698150", "wikidata_qid": "Q999"},
        ]
        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
            reference_fn=lambda n: None, landmark_fn=lambda n: None,
            city_centroid=None, log=lambda _m: None)
        for p in out:
            self.assertNotEqual(p["coordinates"], "",
                                f"{p['name']} wrongly cleared (same building)")
        self.assertEqual(sum(1 for r in rows if r.get("cluster_collapsed")), 0)

    def test_user_pins_in_a_cluster_are_never_cleared(self):
        pois = [
            {"name": "Bar A", "coordinates": "10.776800, 106.694300",
             "user_explicit": True, "coord_source": "user_share_link"},
            {"name": "Bar B", "coordinates": "10.776300, 106.695600",
             "user_explicit": True, "coord_source": "user_share_link"},
        ]
        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
            reference_fn=lambda n: None, landmark_fn=lambda n: None,
            city_centroid=None, log=lambda _m: None)
        self.assertEqual(out[0]["coordinates"], "10.776800, 106.694300")
        self.assertEqual(out[1]["coordinates"], "10.776300, 106.695600")
        self.assertFalse(out[0].get("_no_coordinate"))
        self.assertFalse(out[1].get("_no_coordinate"))

    def test_a_referenced_stop_in_a_cluster_is_not_cleared(self):
        """A stop that resolves to a real in-scope reference (even if within
        threshold, so not snapped) is well-placed and must survive even when it
        sits inside the 250 m cluster disc with a reference-less neighbour."""
        # Place A has a matching reference ON its pin (within threshold → kept,
        # not snapped, but reference present). Place B has none.
        a_pt = (10.772500, 106.698000)
        pois = [
            {"name": "Ben Thanh Market",
             "coordinates": f"{a_pt[0]:.6f}, {a_pt[1]:.6f}"},
            {"name": "Mystery Spot",
             "coordinates": "10.772600, 106.698200"},
        ]

        def _ref(n):
            if n == "Ben Thanh Market":
                return (a_pt[0], a_pt[1], "serper", "Ben Thanh Market")
            return None

        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
            reference_fn=_ref, landmark_fn=lambda n: None,
            city_centroid=None, log=lambda _m: None)
        by = {p["name"]: p for p in out}
        self.assertNotEqual(by["Ben Thanh Market"]["coordinates"], "",
                            "a referenced, in-scope stop was wrongly cleared")


# ══════════════════════════════ item 2 ══════════════════════════════════════
class TestSecondAuthority(unittest.TestCase):
    """[LOCAL-858B item 2] When Wikidata is blocked, Serper /places (then
    Nominatim) resolves the landmark — name-matched and in-scope — and pin_snap
    uses it."""

    def test_serper_places_resolves_in_scope_name_matched(self):
        real = REAL["Ben Thanh Market"]

        def _places(name):
            # Serper returns the right place plus an out-of-scope same-name decoy.
            return [
                {"name": "Ben Thanh Market", "lat": real[0], "lon": real[1]},
                {"name": "Ben Thanh Market", "lat": 21.03, "lon": 105.85},
            ]
        hit = l2a.lookup_second_authority(
            "Ben Thanh Market", scope="Ho Chi Minh City",
            scope_center=HCMC_CENTER, places_fn=_places,
            nominatim_fn=lambda n: [], use_cache=False)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[2], "serper_places")
        self.assertLessEqual(_hav_m((hit[0], hit[1]), real), 150.0)

    def test_name_mismatch_is_rejected(self):
        def _places(name):
            return [{"name": "Totally Different Cafe", "lat": REAL[
                "Ben Thanh Market"][0], "lon": REAL["Ben Thanh Market"][1]}]
        hit = l2a.lookup_second_authority(
            "Ben Thanh Market", scope="Ho Chi Minh City",
            scope_center=HCMC_CENTER, places_fn=_places,
            nominatim_fn=lambda n: [], use_cache=False)
        self.assertIsNone(hit)

    def test_nominatim_fallback_when_serper_empty(self):
        real = REAL["Saigon Opera House"]
        hit = l2a.lookup_second_authority(
            "Saigon Opera House", scope="Ho Chi Minh City",
            scope_center=HCMC_CENTER, places_fn=lambda n: [],
            nominatim_fn=lambda n: [(real[0], real[1], "Saigon Opera House")],
            use_cache=False)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[2], "nominatim")
        self.assertLessEqual(_hav_m((hit[0], hit[1]), real), 150.0)

    def test_out_of_scope_hit_is_refused(self):
        # A same-name place far outside the metro radius is refused.
        def _places(name):
            return [{"name": "Saigon Opera House", "lat": 48.8, "lon": 2.35}]
        hit = l2a.lookup_second_authority(
            "Saigon Opera House", scope="Ho Chi Minh City",
            scope_center=HCMC_CENTER, places_fn=_places,
            nominatim_fn=lambda n: [], use_cache=False)
        self.assertIsNone(hit)


class TestPinSnapUsesSecondAuthorityWhenWikidataBlocked(unittest.TestCase):
    """[LOCAL-858B] End-to-end through pin_snap: Wikidata returns nothing (blocked),
    the second authority supplies the landmark, and the stop snaps to its real pin
    — NOT cleared, NOT the centroid."""

    def test_wikidata_blocked_second_authority_snaps(self):
        import landmark_second_authority as _l2a
        _saved = _l2a.lookup_second_authority

        def _fake_2nd(name, scope="", scope_center=None, scope_bbox=None,
                      places_fn=None, nominatim_fn=None, use_cache=True):
            pt = REAL.get(name)
            return (pt[0], pt[1], "serper_places") if pt else None

        _l2a.lookup_second_authority = _fake_2nd
        try:
            pois = [
                {"name": "Ben Thanh Market",
                 "coordinates": f"{SHIPPED_532['Ben Thanh Market'][0]:.6f}, "
                                f"{SHIPPED_532['Ben Thanh Market'][1]:.6f}"},
                {"name": "Saigon Opera House",
                 "coordinates": f"{SHIPPED_532['Saigon Opera House'][0]:.6f}, "
                                f"{SHIPPED_532['Saigon Opera House'][1]:.6f}"},
            ]
            # landmark_fn stays None so pin_snap takes the LIVE path and reaches
            # the (patched) second authority; Wikidata itself is offline here.
            out, rows = pin_snap.snap_poi_coordinates(
                pois, scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
                city_centroid=None, log=lambda _m: None)
        finally:
            _l2a.lookup_second_authority = _saved

        for p in out:
            pt = pin_snap._parse_coord(p["coordinates"])
            self.assertIsNotNone(pt, f"{p['name']} was cleared instead of snapped")
            self.assertLessEqual(_hav_m(pt, REAL[p["name"]]), 150.0)


class TestPhase3BPreservesEstablishedLandmarkPin(unittest.TestCase):
    """[LOCAL-858B] The PHASE-3B rebuild must NOT overwrite the authority pin the
    early landmark pass established with the model's fresh centroid guess. Cloud
    tour 532: Ben Thanh fell back toward the HCMC centroid AFTER 3B because the
    merge took the model's ``coordinates`` first. A stop marked ``_landmark_coord``
    keeps its established pin, exactly like a user pin."""

    def test_established_landmark_coordinate_survives_merge(self):
        import generate_tour_text as g
        real = f"{REAL['Ben Thanh Market'][0]:.6f}, {REAL['Ben Thanh Market'][1]:.6f}"
        orig = {"name": "Ben Thanh Market", "coordinates": real,
                "_landmark_coord": True, "_coord_source": "wikidata_p625"}
        # The PHASE-3B model re-guesses the HCMC centroid for the same stop.
        entry = {"name": "Ben Thanh Market",
                 "coordinates": "10.776000, 106.695000"}
        upm = g._user_pin_merge_fields(entry, orig)
        self.assertTrue(upm["landmark_kept"])
        self.assertEqual(upm["coordinates"], real,
                         "the model's centroid guess overwrote the established "
                         "landmark pin in the 3B merge")

    def test_non_landmark_stop_still_takes_model_coordinate(self):
        import generate_tour_text as g
        orig = {"name": "Some Cafe", "coordinates": "10.70, 106.70"}
        entry = {"name": "Some Cafe", "coordinates": "10.78, 106.70"}
        upm = g._user_pin_merge_fields(entry, orig)
        self.assertFalse(upm.get("landmark_kept"))
        self.assertEqual(upm["coordinates"], "10.78, 106.70")


if __name__ == "__main__":
    unittest.main()