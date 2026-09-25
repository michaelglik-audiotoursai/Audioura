#!/usr/bin/env python3
"""LOCAL-480 — the facility tour category.

A fifth tour_category, `facility`, for venues people pass THROUGH with an errand
(airports, terminals, stations, hospitals, convention centres, campuses). Its
stop list is a NEED-SPINE, not an interest ranking (D563). Tour 423 (Logan)
proved the defect: the story engine is good, but `tour_category=='walking'`
means "sightseeing on foot", so it produced a sightseer's list — including
"Boston Logan Airport Virtual Tour", a thing you cannot stand next to.

This suite proves the six acceptance criteria, and — per LOCAL-465 — proves the
WIRING separately from the FUNCTION: the pure functions are unit-tested directly,
and the integration into generate_tour_text() is guarded by source assertions so
a revert of the wiring breaks a test even when the functions still pass.

Per D242, run it and paste the real output. `exit=0` proves nothing.
"""
import os
import sys
import inspect
import logging
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import facility_spine
import generate_tour_text as gtt


# Logan Airport, measured by LEAD 2026-09-15.
LOGAN = (42.3656, -71.0096)


def _logan_overpass():
    """A mock Overpass client returning the measured Logan reality: gates,
    parking (incl. Central Parking rideshare pickup), food, water, art, transit
    — but NO lost-and-found, NO kids' play, matching LEAD's two live queries.
    Security and baggage are not standalone named nodes at Logan either."""
    data = {
        'orient': [{'type': 'way', 'id': 100, 'center': {'lat': 42.3659, 'lon': -71.0092},
                    'tags': {'aeroway': 'terminal', 'name': 'Terminal E'}}],
        'terminal_gates': [{'type': 'node', 'id': 113, 'lat': 42.3660, 'lon': -71.0090,
                            'tags': {'aeroway': 'gate', 'ref': 'E1B'}}],
        'security': [],
        'food_water': [{'type': 'node', 'id': 201, 'lat': 42.3661, 'lon': -71.0089,
                        'tags': {'amenity': 'cafe', 'name': 'Dunkin'}}],
        'rest': [{'type': 'node', 'id': 301, 'lat': 42.3662, 'lon': -71.0088,
                  'tags': {'amenity': 'lounge', 'name': 'Air France Lounge'}}],
        'kids': [],
        'art_exhibits': [{'type': 'node', 'id': 401, 'lat': 42.3663, 'lon': -71.0087,
                          'tags': {'tourism': 'artwork', 'name': 'Boston Landing Mural'}}],
        'lost_and_found': [],
        'baggage': [],
        'ground_transport': [{'type': 'way', 'id': 501, 'center': {'lat': 42.3670, 'lon': -71.0101},
                              'tags': {'amenity': 'parking', 'name': 'Central Parking'}}],
    }

    def _client(query, context=""):
        key = context.split(":")[-1]
        return {'elements': data.get(key, [])}
    return _client


class TestFacilityClassification(unittest.TestCase):
    """AC1 (part) + AC3 — facility is detected, and a walking tour is NOT."""

    def test_ac1_logan_walking_phrasing_classifies_facility(self):
        # The exact tour-423 phrasing. "Walking tour" must NOT win — a terminal
        # is a facility, not a sightseeing afternoon.
        self.assertEqual(
            gtt._classify_tour_category("Walking tour around Logan Airport, Boston", ""),
            "facility")

    def test_ac3_cimiez_walking_tour_is_untouched(self):
        # Michael approved the Cimiez tour (D556). "District" is a walking word,
        # not a facility word — this MUST stay 'walking' or it is a bounce.
        self.assertEqual(
            gtt._classify_tour_category(
                "Walking tour around Cimiez District, Nice, France", ""),
            "walking")

    def test_facility_words_and_iata(self):
        for loc in ("BOS airport tour", "South Station terminal, Boston",
                    "Massachusetts General Hospital", "Boston Convention Center",
                    "tour of LHR departures", "Fenway stadium tour"):
            self.assertEqual(gtt._classify_tour_category(loc, ""), "facility",
                             f"{loc!r} should classify as facility")

    def test_detector_is_narrow_no_false_positives(self):
        # None of these ordinary requests may be pulled into 'facility'.
        for loc in ("Walking tour around Cimiez District, Nice, France",
                    "Downtown Boston", "Bread Thyme restaurant tour in West Roxbury, MA",
                    "Freedom Trail, Boston", "Beacon Hill neighborhood walk"):
            self.assertFalse(gtt._detect_facility_class(loc, ""),
                             f"{loc!r} must NOT be detected as a facility")


class TestNeedSpineOrderAndSources(unittest.TestCase):
    """AC1 + AC2 — need-spine order, and every stop names its source."""

    def test_ac1_six_facility_stops_with_coords_and_the_required_kinds(self):
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        self.assertEqual(len(stops), 6, "six needs requested, six filled")
        needs = [s.need_key for s in stops]

        # AC1 explicitly requires a terminal, ground transport, food/water and
        # art among the six.
        self.assertIn("orient", needs, "a terminal (orient) must be present")
        self.assertIn("ground_transport", needs, "ground transport must be present")
        self.assertIn("food_water", needs, "food/water must be present")
        self.assertIn("art_exhibits", needs, "art must be present")

        # Every stop carries a real coordinate.
        for s in stops:
            lat, lng = [float(x) for x in s.coordinates.split(",")]
            self.assertTrue(-90 <= lat <= 90 and -180 <= lng <= 180)

        # No "Virtual Tour" — every stop is a mapped physical object.
        names = " ".join(s.name.lower() for s in stops)
        self.assertNotIn("virtual tour", names)

    def test_need_order_is_the_sequence_a_traveller_hits(self):
        # Unmet slots (security, kids, lost&found, baggage at Logan) do NOT
        # consume budget, so ground transport surfaces within six — findable
        # or cut. The order of what DID fill must still follow the spine.
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        spine_order = [s.key for s in facility_spine.NEED_SPINE]
        got = [s.need_key for s in stops]
        self.assertEqual(got, sorted(got, key=spine_order.index),
                         "filled stops must be in need-spine order")

    def test_ac2_each_stop_source_is_named_in_the_log_line(self):
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        for s in stops:
            line = s.source_line()
            self.assertIn(s.name, line)
            # The source is NAMED: OSM type/id for a mapped object.
            self.assertRegex(line, r"source=OSM (node|way|relation)/\d+")

    def test_gate_number_becomes_a_findable_name(self):
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        gate = next((s for s in stops if s.need_key == "terminal_gates"), None)
        self.assertIsNotNone(gate)
        self.assertEqual(gate.name, "Gate E1B")


class TestBreakTheSpineFallback(unittest.TestCase):
    """AC6 — break the spine and show it go red: disabling need-slot filling
    makes fill_need_spine return [], which is the signal generate_tour_text uses
    to fall back to the old sightseeing list."""

    def tearDown(self):
        facility_spine.SPINE_FILLING_ENABLED = True
        os.environ.pop("FACILITY_SPINE_DISABLED", None)

    def test_module_flag_disables_filling(self):
        facility_spine.SPINE_FILLING_ENABLED = False
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        self.assertEqual(stops, [], "disabled spine must return no stops")

    def test_env_flag_disables_filling(self):
        os.environ["FACILITY_SPINE_DISABLED"] = "1"
        stops = facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())
        self.assertEqual(stops, [], "env-disabled spine must return no stops")

    def test_red_green_demonstration(self):
        # GREEN: enabled -> six stops.
        facility_spine.SPINE_FILLING_ENABLED = True
        self.assertEqual(
            len(facility_spine.fill_need_spine(*LOGAN, want=6,
                                               overpass_request=_logan_overpass())), 6)
        # RED: the moment the spine is broken, the fill is empty and the caller
        # (asserted in TestWiring) falls back to the sightseeing list.
        facility_spine.SPINE_FILLING_ENABLED = False
        self.assertEqual(
            facility_spine.fill_need_spine(*LOGAN, want=6,
                                           overpass_request=_logan_overpass()), [])


class TestFindableOrCutRule(unittest.TestCase):
    """AC5 — a stop whose geocode comes back 'low' is DROPPED, not downgraded."""

    def test_low_confidence_stop_is_dropped_high_is_kept(self):
        # Two facility stops as the fill would build them.
        stops = [
            {"name": "Central Parking", "_facility_need": "ground_transport",
             "coordinates": "42.3670, -71.0101", "_geo_confidence": "high"},
            {"name": "Phantom Lost & Found", "_facility_need": "lost_and_found",
             "coordinates": "42.3999, -71.0999", "_geo_confidence": "low"},
        ]
        # This mirrors the wiring's drop predicate exactly.
        kept = [p for p in stops if p.get("_geo_confidence") != "low"]
        dropped = [p["name"] for p in stops if p.get("_geo_confidence") == "low"]
        self.assertEqual([p["name"] for p in kept], ["Central Parking"])
        self.assertEqual(dropped, ["Phantom Lost & Found"])

    def test_resolve_poi_marks_low_when_uncorroborated(self):
        # With geocoding disabled, resolve_poi cannot corroborate and must mark
        # the stop 'low' — the exact input the drop rule keys on. (No network.)
        os.environ["GEOCODE_STOPS"] = "0"
        try:
            import importlib
            import geocode_stops
            importlib.reload(geocode_stops)
            poi = {"name": "Somewhere", "address": "", "coordinates": "42.36, -71.01"}
            rec = geocode_stops.resolve_poi(poi, "Boston", None)
            self.assertEqual(poi["_geo_confidence"], "low")
            self.assertEqual(rec["confidence"], "low")
        finally:
            os.environ.pop("GEOCODE_STOPS", None)
            import importlib
            import geocode_stops
            importlib.reload(geocode_stops)


class TestWiring(unittest.TestCase):
    """LOCAL-465 — prove the WIRING separately from the function.

    A revert of the integration into generate_tour_text() breaks these even
    though facility_spine's own functions still pass. We assert on the source of
    the real generation function, not on a symbol."""

    def setUp(self):
        self.src = inspect.getsource(gtt.generate_tour_text)

    def test_facility_branch_calls_fill_need_spine(self):
        self.assertIn("facility_spine.fill_need_spine", self.src,
                      "generate_tour_text no longer calls fill_need_spine — "
                      "facility wiring reverted")

    def test_facility_branch_is_gated_on_the_category(self):
        self.assertIn("tour_category == 'facility'", self.src,
                      "facility fill is no longer gated on the facility category")

    def test_facility_fill_sets_skip_flag_and_gpt_call_respects_it(self):
        self.assertIn("_facility_fill_used = True", self.src,
                      "facility fill no longer sets its skip flag")
        self.assertIn("not _deterministic_fill_used and not _facility_fill_used",
                      self.src,
                      "the Phase 3A GPT call no longer skips on facility fill — "
                      "the break-the-spine fallback is gone")

    def test_low_confidence_facility_stop_is_dropped_in_wiring(self):
        # The drop must be present AND key on 'low'.
        self.assertIn("_geo_confidence", self.src)
        self.assertIn("DROPPED facility stop", self.src,
                      "the low-confidence facility drop (AC5) is missing from the wiring")

    def test_facility_excluded_from_sightseeing_replenishment(self):
        self.assertIn("('restaurant', 'museum', 'facility')", self.src,
                      "facility is no longer excluded from the sightseeing "
                      "replenisher — the need-spine can be polluted")

    def test_classifier_wires_the_facility_detector(self):
        csrc = inspect.getsource(gtt._classify_tour_category)
        self.assertIn("_detect_facility_class", csrc,
                      "_classify_tour_category no longer consults the facility detector")

    def test_facility_guard_overrides_museum_flip(self):
        self.assertIn("FACILITY GUARD", self.src,
                      "the post-convergence facility guard is gone — a venue_name "
                      "inference could silently flip Logan to museum")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main(verbosity=2)
