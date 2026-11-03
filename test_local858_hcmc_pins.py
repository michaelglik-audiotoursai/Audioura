#!/usr/bin/env python3
"""test_local858_hcmc_pins.py — LOCAL-858.

HCMC (and every Vietnamese-city) walking-tour stop was collapsing to the CITY
CENTRE pin. Field evidence (GCloud_Storied_1, wave 24, gen 00030-c98): tour 527
"Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City" delivered 3/3
stops but ALL 3 pins ≈ 10.776,106.695 (the HCMC centroid), and ROUTE-ORDER logged
"0 stops with coordinates". Real pins: Ben Thanh Market ≈ 10.7725,106.6980;
Saigon Opera House ≈ 10.7766,106.7031.

ROOT CAUSE: PHASE-3B asks the model for each stop's coordinate; for a landmark it
cannot place it returns the CITY CENTROID for every stop. Nothing downstream
distinguished that centroid from a real pin, so a stop with no authoritative
reference kept the centroid and shipped it as if it were real.

THE FIX (asserted here, fully offline — the live Wikidata/Serper calls are
injected):

  1. A well-known landmark in a Vietnamese city gets its REAL pin from the
     authoritative Wikidata-P625 lookup, resolving by the place's own name in the
     TOUR language AND the LOCAL language (Vietnamese for HCMC/Hanoi). Every
     delivered pin is within 150 m of the real landmark.
  2. A stop with NO real coordinate is never silently given the centroid: its pin
     is CLEARED and it is announced '[LOCAL-858] no coordinate <name>'.
  3. The control (Boston, English scope) is unaffected: its landmarks still get
     their real pins and no centroid ships.

Built from the EXACT request strings in the ticket:
  - "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"
  - "Hoan Kiem Lake and Temple of Literature walk, Hanoi"
  - "Boston Common and Old North Church walk, Boston"

Run: python3 -m pytest test_local858_hcmc_pins.py -q
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pin_snap
import wikidata_landmark_lookup as wl


# ─────────────────────────── ground truth (P625) ────────────────────────────
# Authoritative Wikidata P625 coordinates (what the live lookup returns). Used
# both as the injected landmark answers and as the "real" position each pin must
# land within 150 m of.
REAL = {
    "Ben Thanh Market": (10.772521, 106.698019),
    "Saigon Opera House": (10.776390, 106.702780),
    "War Remnants Museum": (10.779500, 106.692000),
    "Hoan Kiem Lake": (21.028889, 105.852500),
    "Temple of Literature": (21.028611, 105.835556),
    "Boston Common": (42.355000, -71.065556),
    "Old North Church": (42.366389, -71.054444),
}

HCMC_CENTROID = (10.776000, 106.695000)   # the tour-527 pin, verbatim
HANOI_CENTROID = (21.028500, 105.854200)
BOSTON_CENTROID = (42.360100, -71.058900)

HCMC_CENTER = (10.7769, 106.7009)
HANOI_CENTER = (21.0285, 105.8542)
BOSTON_CENTER = (42.3601, -71.0589)

# The exact request strings from the ticket.
REQ_HCMC = "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"
REQ_HANOI = "Hoan Kiem Lake and Temple of Literature walk, Hanoi"
REQ_BOSTON = "Boston Common and Old North Church walk, Boston"


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _landmark_fn(name):
    """Injected authoritative landmark lookup — the offline stand-in for the live
    wikidata_landmark_lookup.lookup. Returns (lat, lng, source) for a known
    landmark, None otherwise. This is the ``landmark_fn`` seam pin_snap exposes
    for exactly this (the live suite is offline)."""
    pt = REAL.get(name)
    if pt is None:
        return None
    return (pt[0], pt[1], "wikidata_p625")


def _centroid_pois(names, centroid):
    """The tour as the model shipped it: every stop stamped the city centroid."""
    cs = f"{centroid[0]:.6f}, {centroid[1]:.6f}"
    return [{"name": n, "coordinates": cs} for n in names]


class TestBenThanhOperaHousePins(unittest.TestCase):
    """The exact tour-527 request: centroid-collapsed stops get their real pins."""

    def _snap(self):
        pois = _centroid_pois(
            ["Ben Thanh Market", "Saigon Opera House", "War Remnants Museum"],
            HCMC_CENTROID)
        logs = []
        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City, Vietnam", scope_center=HCMC_CENTER,
            tour_language="en", city_centroid=HCMC_CENTER,
            landmark_fn=_landmark_fn, log=logs.append)
        return out, rows, logs

    def test_every_pin_within_150m_of_the_real_landmark(self):
        out, _rows, _logs = self._snap()
        for p in out:
            pt = pin_snap._parse_coord(p["coordinates"])
            self.assertIsNotNone(pt, f"{p['name']} lost its coordinate")
            d = _hav_m(pt, REAL[p["name"]])
            self.assertLessEqual(
                d, 150.0,
                f"{p['name']} pin {d:.0f} m from the real landmark (> 150 m)")

    def test_no_pin_is_the_city_centroid(self):
        out, _rows, _logs = self._snap()
        for p in out:
            pt = pin_snap._parse_coord(p["coordinates"])
            self.assertGreater(
                _hav_m(pt, HCMC_CENTROID), 150.0,
                f"{p['name']} still ships the HCMC centroid")

    def test_all_three_snapped_to_authority(self):
        _out, rows, _logs = self._snap()
        self.assertEqual(sum(1 for r in rows if r.get("snapped")), 3)


class TestNoCoordinateIsAnnouncedNeverCentroided(unittest.TestCase):
    """A stop with no real reference must be CLEARED and announced, never left on
    the city centroid as if it were a real pin."""

    def test_unresolvable_stop_cleared_and_logged(self):
        pois = _centroid_pois(
            ["Ben Thanh Market", "A Totally Made Up Nonexistent Spot XYZ"],
            HCMC_CENTROID)
        logs = []
        out, _rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City, Vietnam", scope_center=HCMC_CENTER,
            tour_language="en", city_centroid=HCMC_CENTER,
            landmark_fn=_landmark_fn, log=logs.append)
        by_name = {p["name"]: p for p in out}
        # The real landmark is placed.
        ben = pin_snap._parse_coord(by_name["Ben Thanh Market"]["coordinates"])
        self.assertLessEqual(_hav_m(ben, REAL["Ben Thanh Market"]), 150.0)
        # The unplaceable stop has NO coordinate (not the centroid) and is marked.
        made_up = by_name["A Totally Made Up Nonexistent Spot XYZ"]
        self.assertEqual(made_up["coordinates"], "")
        self.assertTrue(made_up.get("_no_coordinate"))
        # And it is announced exactly as the ticket requires.
        self.assertIn(
            "[LOCAL-858] no coordinate A Totally Made Up Nonexistent Spot XYZ",
            logs)

    def test_all_centroid_stops_cleared_when_no_reference_available(self):
        """Nominatim/Wikidata unreachable (reference_fn returns None): three stops
        sharing the one centroid are 'coordinates unknown' — all cleared, none
        kept as a fake pin."""
        pois = _centroid_pois(["Stop A", "Stop B", "Stop C"], HCMC_CENTROID)
        logs = []
        out, _rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City, Vietnam", scope_center=HCMC_CENTER,
            reference_fn=lambda n: None, city_centroid=HCMC_CENTER,
            log=logs.append)
        for p in out:
            self.assertEqual(p["coordinates"], "", f"{p['name']} kept a fake pin")
            self.assertTrue(p.get("_no_coordinate"))
        self.assertEqual(
            sum(1 for m in logs if m.startswith("[LOCAL-858] no coordinate")), 3)

    def test_distinct_well_placed_stops_are_never_cleared(self):
        """Two genuinely distinct, already-correct pins (within threshold of their
        own injected reference) must be preserved — the guard clears only the
        shared centroid, not real neighbours."""
        pois = [
            {"name": "Place A", "coordinates": "10.772521, 106.698019"},
            {"name": "Place B", "coordinates": "10.776390, 106.702780"},
        ]
        refs = {
            "Place A": (10.772521, 106.698019, "serper", "Place A"),
            "Place B": (10.776390, 106.702780, "serper", "Place B"),
        }
        out, _rows = pin_snap.snap_poi_coordinates(
            pois, scope="Ho Chi Minh City", scope_center=HCMC_CENTER,
            reference_fn=lambda n: refs.get(n), city_centroid=HCMC_CENTER)
        for p in out:
            self.assertNotEqual(p["coordinates"], "")
            self.assertFalse(p.get("_no_coordinate"))


class TestHanoiNotWiderThanHCMC(unittest.TestCase):
    """The exact Hanoi request: the fix is general across Vietnamese cities."""

    def test_hanoi_pins_within_150m_and_no_centroid(self):
        pois = _centroid_pois(
            ["Hoan Kiem Lake", "Temple of Literature"], HANOI_CENTROID)
        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Hanoi, Vietnam", scope_center=HANOI_CENTER,
            tour_language="en", city_centroid=HANOI_CENTER,
            landmark_fn=_landmark_fn, log=lambda _m: None)
        for p in out:
            pt = pin_snap._parse_coord(p["coordinates"])
            self.assertIsNotNone(pt)
            self.assertLessEqual(_hav_m(pt, REAL[p["name"]]), 150.0)
            self.assertGreater(_hav_m(pt, HANOI_CENTROID), 150.0)


class TestBostonControl(unittest.TestCase):
    """The non-Vietnam control: English scope, still gets real pins, no centroid,
    and the local-language pass stays off."""

    def test_boston_pins_within_150m_and_no_centroid(self):
        pois = _centroid_pois(
            ["Boston Common", "Old North Church"], BOSTON_CENTROID)
        out, _rows = pin_snap.snap_poi_coordinates(
            pois, scope="Boston, Massachusetts", scope_center=BOSTON_CENTER,
            tour_language="en", city_centroid=BOSTON_CENTER,
            landmark_fn=_landmark_fn, log=lambda _m: None)
        for p in out:
            pt = pin_snap._parse_coord(p["coordinates"])
            self.assertIsNotNone(pt)
            self.assertLessEqual(_hav_m(pt, REAL[p["name"]]), 150.0)
            self.assertGreater(_hav_m(pt, BOSTON_CENTROID), 150.0)


class TestLocalLanguageForScope(unittest.TestCase):
    """Vietnamese cities search Wikidata in Vietnamese too (so "Chợ Bến Thành" /
    "Nhà hát Thành phố" resolve); Boston stays English-only."""

    def test_hcmc_and_hanoi_are_vietnamese(self):
        self.assertEqual(wl.local_lang_for_scope(REQ_HCMC), "vi")
        self.assertEqual(wl.local_lang_for_scope(REQ_HANOI), "vi")
        self.assertEqual(wl.local_lang_for_scope("Hanoi, Vietnam"), "vi")

    def test_boston_is_english(self):
        self.assertEqual(wl.local_lang_for_scope(REQ_BOSTON), "")
        self.assertEqual(wl.local_lang_for_scope("Boston, Massachusetts"), "")


class TestEstablishLandmarkCoordinatesBeforeRouteOrder(unittest.TestCase):
    """[LOCAL-858] The early pass stamps real P625 BEFORE route ordering, so
    ROUTE-ORDER counts every stop instead of logging '0 stops with coordinates'."""

    def test_centroid_stops_get_real_coords_before_routing(self):
        import generate_tour_text as g
        pois = _centroid_pois(
            ["Ben Thanh Market", "Saigon Opera House", "War Remnants Museum"],
            HCMC_CENTROID)
        # _establish_landmark_coordinates imports wikidata_landmark_lookup.lookup
        # at call time; inject a fake so the test stays offline.
        import wikidata_landmark_lookup as _wl

        def _fake_lookup(name, scope="", scope_center=None, scope_bbox=None,
                         tour_language="en", **kw):
            pt = REAL.get(name)
            return (pt[0], pt[1], "wikidata_p625", "Q1") if pt else None

        _saved = _wl.lookup
        _wl.lookup = _fake_lookup
        try:
            n = g._establish_landmark_coordinates(
                pois, scope="Ho Chi Minh City, Vietnam",
                scope_center=HCMC_CENTER, tour_language="en",
                city_centroid=HCMC_CENTER, log=lambda _m: None)
        finally:
            _wl.lookup = _saved

        self.assertEqual(n, 3)
        placed = g._compute_route_order(pois)
        with_coords = 0
        for p in placed:
            pt = pin_snap._parse_coord(p.get("coordinates", ""))
            if pt and _hav_m(pt, HCMC_CENTROID) > 150.0:
                with_coords += 1
        self.assertEqual(with_coords, 3,
                         "every stop must carry a real (non-centroid) coordinate "
                         "before route ordering")


class TestAuthorityOffScopeGuard(unittest.TestCase):
    """[LOCAL-858] A Wikidata P625 'authority' reference that is a SAME-NAME place
    in another region must still be refused when a scope centre is known. The live
    Hanoi run snapped 'St. Joseph's Cathedral' to the cathedral in BAGHDAD (6,144
    km) because the lookup had no scope centre; the guard refuses it."""

    def test_authority_reference_in_another_country_is_refused(self):
        from pin_snap import snap_pin
        baghdad = (33.338833, 44.396583)   # the real wrong P625 the live run hit
        shipped = (21.0285, 105.8542)      # the stop's Hanoi-area shipped pin
        row = snap_pin(
            "St. Joseph's Cathedral", shipped,
            scope="Hanoi", scope_center=HANOI_CENTER,
            landmark_fn=lambda n: (baghdad[0], baghdad[1], "wikidata_p625"))
        self.assertFalse(row["snapped"])
        self.assertIsNone(row["new_coordinate"])
        self.assertIn("another region", row["reason"])

    def test_authority_reference_in_scope_still_snaps(self):
        from pin_snap import snap_pin
        real = REAL["Hoan Kiem Lake"]
        shipped = HANOI_CENTROID
        row = snap_pin(
            "Hoan Kiem Lake", shipped,
            scope="Hanoi", scope_center=HANOI_CENTER,
            landmark_fn=lambda n: (real[0], real[1], "wikidata_p625"))
        self.assertTrue(row["snapped"])
        self.assertLessEqual(_hav_m(row["new_coordinate"], real), 150.0)


if __name__ == "__main__":
    unittest.main()
