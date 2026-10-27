#!/usr/bin/env python3
"""LOCAL-788 item 2/B — a request naming a neighbourhood or "near me" must not end
at CITY precision.

ROOT CAUSE (tour 460, GCloud 2026-10-27): the LLM intent returned
``scope_precision = CITY`` for "middle eastern restaurants near me, West Roxbury,
MA"; CITY precision makes ``_assert_one_scope_per_tour`` DROP the stop-by-stop
containment scope, so a place up to city-wide is accepted. The same code on the
Mac returned DISTRICT — the LLM verdict is not deterministic, and an Overpass 502
on GCloud coincided.

``generate_tour_text._correct_scope_precision`` corrects this DETERMINISTICALLY,
independent of the LLM and of Overpass, reusing the LOCAL-786 scope classifier.
It only ever tightens a CITY verdict; a genuine whole-city request stays CITY.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt


def _intent(scope, precision, location=None):
    return {
        "geographic_scope": scope,
        "scope_precision": precision,
        "location": location if location is not None else scope,
    }


class TestPrecisionCorrection:
    @pytest.mark.parametrize("request_text,scope", [
        ("middle eastern restaurants near me, West Roxbury, MA", "West Roxbury, MA"),
        ("restaurants in West Roxbury", "West Roxbury, MA"),
        ("coffee shops in Jamaica Plain, Boston", "Jamaica Plain, Boston"),
        ("tour of the North End, Boston", "North End, Boston"),
    ])
    def test_neighbourhood_city_corrected_to_district(self, request_text, scope):
        out = gtt._correct_scope_precision(_intent(scope, "CITY"), request_text)
        assert out["scope_precision"] == "DISTRICT", (
            f"{scope!r} should be DISTRICT, got {out['scope_precision']}")

    def test_near_me_city_scope_corrected(self):
        # "near me" with only a city-level scope still deserves a tight check.
        out = gtt._correct_scope_precision(
            _intent("Boston, MA", "CITY"),
            "coffee shops near me, Boston, MA")
        assert out["scope_precision"] == "DISTRICT"

    def test_genuine_city_stays_city(self):
        out = gtt._correct_scope_precision(
            _intent("Newton, MA", "CITY"), "walking tour in Newton, MA")
        assert out["scope_precision"] == "CITY"

    def test_brookline_stays_city(self):
        # Brookline is a single-word locality (a town) — CITY, not a neighbourhood.
        out = gtt._correct_scope_precision(
            _intent("Brookline, MA", "CITY"), "gyms in Brookline, MA")
        assert out["scope_precision"] == "CITY"

    def test_building_precision_untouched(self):
        out = gtt._correct_scope_precision(
            _intent("Fairbanks House", "BUILDING"),
            "Fairbanks House Tour in Dedham, MA")
        assert out["scope_precision"] == "BUILDING"

    def test_corridor_precision_untouched(self):
        out = gtt._correct_scope_precision(
            _intent("Beacon St, Brookline", "CORRIDOR"),
            "walking tour over Beacon St in Brookline, MA")
        assert out["scope_precision"] == "CORRIDOR"

    def test_already_district_untouched(self):
        out = gtt._correct_scope_precision(
            _intent("West Roxbury, MA", "DISTRICT"),
            "restaurants in West Roxbury")
        assert out["scope_precision"] == "DISTRICT"

    def test_empty_precision_corrected_for_neighbourhood(self):
        out = gtt._correct_scope_precision(
            _intent("West Roxbury, MA", ""), "restaurants in West Roxbury")
        assert out["scope_precision"] == "DISTRICT"

    def test_non_dict_returned_as_is(self):
        assert gtt._correct_scope_precision(None, "x") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
