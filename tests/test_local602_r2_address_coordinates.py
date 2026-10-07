#!/usr/bin/env python3
"""test_local602_r2_address_coordinates.py — LOCAL-602 r2 defect #2.

Wrong coordinates: the r1 WNDR Boston run shipped every stop at the chain's
Seaport-area point (42.3393, -71.0402) while the venue address geocodes ~1.9 km
away. That is "same city, wrong building" — inside the 50 km tour-radius guard,
so nothing caught it. These tests pin tour_coordinates.verify_against_address:
a coordinate > 300 m from the geocode of its own street address is rejected and
replaced by the address geocode. The geocoder is injected, so the test is offline
and deterministic.

Run: python3 -m pytest tests/test_local602_r2_address_coordinates.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_coordinates as tc


# WNDR Boston, 500 Washington St ~ (42.3545, -71.0616). The r1 run's wrong point
# is the Seaport area ~ (42.3393, -71.0402) — about 1.9 km away.
_ADDR = "500 Washington St, Boston, MA 02111"
_ADDR_GEOCODE = (42.3545, -71.0616)
_WRONG_SEAPORT = (42.3393, -71.0402)
_RIGHT_NEARBY = (42.3546, -71.0617)   # ~15 m from the address geocode


def _fixed_geocoder(_address):
    """Always returns the WNDR address geocode (offline stub)."""
    return _ADDR_GEOCODE


def _no_geocoder(_address):
    return None


class TestVerifyAgainstAddress(unittest.TestCase):

    def test_wrong_coordinate_is_rejected_and_corrected(self):
        coord, src = tc.verify_against_address(
            _WRONG_SEAPORT, _ADDR, geocoder=_fixed_geocoder)
        self.assertEqual(src, "address_corrected")
        self.assertAlmostEqual(coord[0], _ADDR_GEOCODE[0], places=4)
        self.assertAlmostEqual(coord[1], _ADDR_GEOCODE[1], places=4)

    def test_nearby_coordinate_is_kept(self):
        coord, src = tc.verify_against_address(
            _RIGHT_NEARBY, _ADDR, geocoder=_fixed_geocoder)
        self.assertEqual(src, "address_ok")
        # Kept the original candidate, not the address geocode.
        self.assertAlmostEqual(coord[0], _RIGHT_NEARBY[0], places=4)
        self.assertAlmostEqual(coord[1], _RIGHT_NEARBY[1], places=4)

    def test_threshold_boundary(self):
        # A point ~299 m away is kept; a point ~1900 m away is corrected.
        # 1 deg lat ~ 111 km, so 0.00269 deg ~ 299 m north of the address geocode.
        near = (_ADDR_GEOCODE[0] + 0.00269, _ADDR_GEOCODE[1])
        _, src_near = tc.verify_against_address(near, _ADDR, geocoder=_fixed_geocoder)
        self.assertEqual(src_near, "address_ok")
        _, src_far = tc.verify_against_address(
            _WRONG_SEAPORT, _ADDR, geocoder=_fixed_geocoder)
        self.assertEqual(src_far, "address_corrected")

    def test_no_address_geocode_keeps_candidate_unverified(self):
        coord, src = tc.verify_against_address(
            _WRONG_SEAPORT, _ADDR, geocoder=_no_geocoder)
        self.assertEqual(src, "unverified")
        self.assertAlmostEqual(coord[0], _WRONG_SEAPORT[0], places=4)

    def test_no_candidate_uses_address_geocode(self):
        coord, src = tc.verify_against_address(
            None, _ADDR, geocoder=_fixed_geocoder)
        self.assertEqual(src, "address_corrected")
        self.assertAlmostEqual(coord[0], _ADDR_GEOCODE[0], places=4)

    def test_no_candidate_and_no_address_is_none(self):
        coord, src = tc.verify_against_address(None, "", geocoder=_no_geocoder)
        self.assertEqual(src, "none")
        self.assertIsNone(coord[0])

    def test_custom_radius_respected(self):
        # With a very tight 10 m radius, even the ~15 m nearby point is corrected.
        _, src = tc.verify_against_address(
            _RIGHT_NEARBY, _ADDR, radius_m=10.0, geocoder=_fixed_geocoder)
        self.assertEqual(src, "address_corrected")

    def test_default_radius_is_300m(self):
        self.assertEqual(tc.ADDRESS_MATCH_RADIUS_M, 300.0)


if __name__ == '__main__':
    unittest.main()
