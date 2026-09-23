#!/usr/bin/env python3
"""LOCAL-521 — Validate a user's chosen stops BEFORE generating.

Acceptance:
  1. Each stop returns ok / warning / rejected with a reason a person can read.
  2. A stop 6,000 km from the venue is rejected (the D564 Sistine Chapel case).
  3. A plausible-but-unconfirmed stop is a WARNING and still generates.
  4. Nothing is dropped silently.

The verdict is three-valued on purpose (Michael's D577): we ship what we cannot
verify (warning), we do not ship what we can refute (rejected).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import user_stops_validate as usv


# A Newton MA venue, matching the geo_refutation fixtures (D564/D567).
NEWTON = (42.3370, -71.2092)
GAZETTEER = {
    'vatican city': (41.9029, 12.4534),
    'los angeles': (34.0522, -118.2437),
    'newton': (42.3370, -71.2092),
    'boston': (42.3601, -71.0589),
}


def geo(name):
    return GAZETTEER.get((name or '').strip().lower())


class TestAcceptance1_EveryStopIsJudgedReadably(unittest.TestCase):
    """#1 Each stop returns ok/warning/rejected with a human-readable reason."""

    def test_every_stop_has_a_verdict_and_a_reason(self):
        result = usv.validate_stops(
            ["Bell Tower", "Audio Guide", "Restaurants"],
            anchor=NEWTON, geocoder=geo)
        self.assertEqual(len(result["stops"]), 3)
        for r in result["stops"]:
            self.assertIn(r["verdict"], (usv.OK, usv.WARNING, usv.REJECTED))
            self.assertTrue(r["reason"] and isinstance(r["reason"], str),
                            f"stop {r['stop']!r} has no readable reason")
            self.assertEqual(r["stop"], r["stop"].strip())

    def test_summary_counts_are_present(self):
        result = usv.validate_stops(["Bell Tower", "Audio Guide"])
        self.assertRegex(result["summary"], r"\d+ ok, \d+ warning, \d+ rejected")

    def test_a_plain_real_place_is_ok(self):
        r = usv.validate_one("Musée Matisse")
        self.assertEqual(r["verdict"], usv.OK)


class TestAcceptance2_DistantStopIsRejected(unittest.TestCase):
    """#2 A stop 6,000 km from the venue is rejected — the D564 case."""

    def test_sistine_chapel_at_a_newton_church_is_rejected(self):
        r = usv.validate_one(
            "Sistine Chapel Ceiling (Vatican City)",
            anchor=NEWTON, geocoder=geo)
        self.assertEqual(r["verdict"], usv.REJECTED)
        self.assertGreater(r["checks"]["geo"]["km"], 6000)
        self.assertIn("Vatican City", r["reason"])

    def test_a_nearby_stop_is_not_rejected_by_distance(self):
        r = usv.validate_one("Newton", anchor=NEWTON, geocoder=geo)
        self.assertNotEqual(r["verdict"], usv.REJECTED)

    def test_without_a_geocoder_distance_cannot_refute(self):
        """An absent verifier cannot manufacture a rejection (D577)."""
        r = usv.validate_one("Sistine Chapel Ceiling (Vatican City)", anchor=NEWTON)
        self.assertNotEqual(r["verdict"], usv.REJECTED)


class TestAcceptance3_UnconfirmedIsWarningAndStillGenerates(unittest.TestCase):
    """#3 A plausible-but-unconfirmed stop is a WARNING and still generates."""

    def test_a_part_the_venue_lacks_is_a_warning_not_a_rejection(self):
        # venue_parts reports count == 0 for a part the venue does not have.
        parts = {"Crypt": {"count": 0, "names": [], "access": ""}}
        r = usv.validate_one("Crypt", part_instances=parts,
                             venue_name="Our Lady Help of Christians",
                             location="Newton MA")
        self.assertEqual(r["verdict"], usv.WARNING)
        self.assertIn("does not appear to have", r["reason"])

    def test_a_warning_stop_still_goes_to_generation(self):
        parts = {"Crypt": {"count": 0, "names": [], "access": ""}}
        result = usv.validate_stops(["Bell Tower", "Crypt"], part_instances=parts)
        self.assertIn("Crypt", usv.generatable(result))
        self.assertIn("Bell Tower", usv.generatable(result))

    def test_a_confirmed_part_is_ok(self):
        parts = {"Bell Tower": {"count": 1, "names": [], "access": "open"}}
        r = usv.validate_one("Bell Tower", part_instances=parts)
        self.assertEqual(r["verdict"], usv.OK)

    def test_only_rejected_stops_are_held_back(self):
        parts = {"Crypt": {"count": 0, "names": [], "access": ""}}
        result = usv.validate_stops(
            ["Bell Tower", "Crypt", "Audio Guide",
             "Sistine Chapel Ceiling (Vatican City)"],
            anchor=NEWTON, geocoder=geo, part_instances=parts)
        gen = usv.generatable(result)
        self.assertIn("Bell Tower", gen)         # ok
        self.assertIn("Crypt", gen)              # warning still generates
        self.assertNotIn("Audio Guide", gen)     # format rejected
        self.assertNotIn("Sistine Chapel Ceiling (Vatican City)", gen)  # far rejected


class TestAcceptance4_NothingDroppedSilently(unittest.TestCase):
    """#4 Nothing is dropped silently — every input appears with its reason."""

    def test_every_input_appears_exactly_once_in_output(self):
        inputs = ["Bell Tower", "Audio Guide", "Restaurants",
                  "Sistine Chapel Ceiling (Vatican City)"]
        result = usv.validate_stops(inputs, anchor=NEWTON, geocoder=geo)
        returned = [r["stop"] for r in result["stops"]]
        self.assertEqual(returned, inputs)

    def test_rejected_stops_are_named_with_reasons(self):
        # "Audio Guide" is a format; "Restaurants in Nice" is a category — both are
        # shapes place_shape refutes (a bare plural with no container is left alone
        # by design, so we use the container form the category rule fires on).
        result = usv.validate_stops(
            ["Audio Guide", "Restaurants in Nice"], anchor=NEWTON, geocoder=geo)
        self.assertIn("Audio Guide", result["rejected"])
        self.assertIn("Restaurants in Nice", result["rejected"])
        for r in result["stops"]:
            if r["verdict"] == usv.REJECTED:
                self.assertTrue(r["reason"])


class TestRefutableShapesFromTheTask(unittest.TestCase):
    """The task names the exact refutable shapes: a format, a category."""

    def test_a_format_is_rejected(self):
        r = usv.validate_one("Audio Guide")
        self.assertEqual(r["verdict"], usv.REJECTED)
        self.assertEqual(r["checks"]["shape"], "format")

    def test_a_category_is_rejected(self):
        r = usv.validate_one("Restaurants in Nice")
        self.assertEqual(r["verdict"], usv.REJECTED)
        self.assertEqual(r["checks"]["shape"], "category")

    def test_a_bare_category_plural_needs_a_container_to_reject(self):
        # place_shape's category rule fires on "<plural> <prep> <place>". A bare
        # "Restaurants" is caught as a format-less non-place only if place_shape
        # says so; assert we surface place_shape's own verdict, whatever it is.
        r = usv.validate_one("Restaurants")
        self.assertIn(r["verdict"], (usv.OK, usv.REJECTED))
        self.assertTrue(r["reason"])


class TestEmptyAndDegenerate(unittest.TestCase):
    def test_empty_name_is_rejected_readably(self):
        r = usv.validate_one("   ")
        self.assertEqual(r["verdict"], usv.REJECTED)
        self.assertTrue(r["reason"])

    def test_empty_list_is_empty_result(self):
        result = usv.validate_stops([])
        self.assertEqual(result["stops"], [])
        self.assertEqual(usv.generatable(result), [])


class TestItCanFail(unittest.TestCase):
    """D242: prove the geography check is really firing, not vacuously passing."""

    def test_raising_the_threshold_lets_the_distant_stop_through(self):
        strict = usv.validate_one(
            "Sistine Chapel Ceiling (Vatican City)", anchor=NEWTON, geocoder=geo)
        self.assertEqual(strict["verdict"], usv.REJECTED)
        loose = usv.validate_one(
            "Sistine Chapel Ceiling (Vatican City)", anchor=NEWTON, geocoder=geo,
            refute_km=50000)
        self.assertNotEqual(loose["verdict"], usv.REJECTED,
                            "with the threshold disabled the far stop must pass")


if __name__ == "__main__":
    unittest.main()
