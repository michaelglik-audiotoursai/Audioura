r"""
LOCAL-855E items 1 & 2 — the listener's own pin is authoritative, and no model
address stub ("Address: 15 Đ.") ever ships.
================================================================================
LEAD re-ran the 7-stop Sophia cycling tour at fb49c502 and found two defects the
earlier bounces had not fixed:

ITEM 1 — the listener's own coordinates were OVERRIDDEN.
  The input URLs carry `@lat,lng` (Acoustic Bar `@10.781195,106.68992`, An Spa
  `@10.7820,106.6935`, Rambutan `@10.7761,106.6962`). The delivered tour moved
  them (Rambutan shipped 10.7768,106.6888) and five District-1 venues collapsed
  to one point ~50 m apart. The cause was PHASE 3B's merge: it took the model's
  freshly-invented `coordinates` FIRST, over the resolved listener pin.
  Rule: a user stop's coordinate from the listener's link is authoritative; no
  geocode / pin-snap / landmark-reference / Places / PHASE-3B step may move it.

ITEM 2 — "Address: 15 Đ." still shipped ("6 Đ.", "8 Đ.", "29 Đ.", "36 Đ.").
  The 855D splitter fix (Đ. is not a sentence end) was correct but did not reach
  this: the stub is the model's INVENTED address ("<complete street address with
  ZIP>"), truncated to a bare *Đường* abbreviation. The listener gave a PIN, not
  an address, so a user stop must never take the model's address, and an
  abbreviation-only stub must be dropped at the source.

These tests exercise the real decision helper `_user_pin_merge_fields` and the
real address cleaner `_clean_user_stop_address` from generate_tour_text (the
single source the PHASE-3B merge now uses). RED on base, GREEN with the fix.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as g


# The real listener pins from the field request (run_local855d_live.py inputs).
USER_PIN = "10.776100, 106.696200"       # Rambutan @10.7761,106.6962
MODEL_GUESS = "10.7768, 106.6888"         # what PHASE 3B invented and overrode with


def _user_stop(name, coords):
    return {"name": name, "title": name, "user_explicit": True, "_anchor": True,
            "coord_source": "user_share_link", "coord_confidence": "resolved",
            "coordinates": coords, "address": ""}


class TestUserPinAuthoritative(unittest.TestCase):
    """Item 1 — the PHASE-3B merge keeps the listener's pin, never the model's."""

    def test_model_coordinate_cannot_override_user_pin(self):
        orig = _user_stop("Rambutan", USER_PIN)
        entry = {"name": "Rambutan", "coordinates": MODEL_GUESS,
                 "address": "3/2, Phường 12, District 10,"}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertTrue(out["is_user_pin"])
        self.assertTrue(out["coord_kept"])
        self.assertEqual(out["coordinates"], USER_PIN,
                         "model coordinate overrode the listener's own pin")

    def test_user_pin_detected_by_coord_source_when_flags_dropped(self):
        # A poi_list rebuild can drop user_explicit/_anchor; coord_source alone
        # must still mark the stop a user pin.
        orig = {"name": "An Spa", "coord_source": "user_share_link",
                "coordinates": "10.782000, 106.693500", "address": ""}
        entry = {"name": "An Spa", "coordinates": "10.7752, 106.6951"}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertTrue(out["is_user_pin"])
        self.assertEqual(out["coordinates"], "10.782000, 106.693500")

    def test_non_user_stop_keeps_model_precedence(self):
        # A normal (non-user) stop still takes the model's coordinate first — the
        # fix must not change the ordinary path.
        orig = {"name": "Some Museum", "coordinates": "1.0, 2.0"}
        entry = {"name": "Some Museum", "coordinates": "3.0, 4.0"}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertFalse(out["is_user_pin"])
        self.assertEqual(out["coordinates"], "3.0, 4.0")

    def test_user_stop_without_coordinate_falls_back(self):
        # A user stop that resolved to NO coordinate (website-only) may take the
        # model's value — there is no listener pin to protect.
        orig = {"name": "An Spa", "user_explicit": True, "coordinates": ""}
        entry = {"name": "An Spa", "coordinates": "10.78, 106.69"}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertTrue(out["is_user_pin"])
        self.assertFalse(out["coord_kept"])
        self.assertEqual(out["coordinates"], "10.78, 106.69")


class TestNoAddressStub(unittest.TestCase):
    """Item 2 — a user stop never takes the model's address; stubs are dropped."""

    def test_model_address_is_discarded_for_user_stop(self):
        orig = _user_stop("Rambutan", USER_PIN)   # orig address is empty
        entry = {"name": "Rambutan", "address": "3/2, Phường 12, District 10,",
                 "coordinates": MODEL_GUESS}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertEqual(out["address"], "",
                         "user stop took the model's invented address")

    def test_duong_stub_dropped(self):
        for stub in ("15 Đ.", "6 Đ.", "8 Đ.", "29 Đ.", "36 Đ.", "Đ."):
            self.assertEqual(g._clean_user_stop_address(stub), "",
                             f"abbreviation stub survived: {stub!r}")

    def test_real_full_address_survives_the_cleaner(self):
        addr = "15 Đ. Nguyễn Văn Tráng, Phường Bến Thành, Quận 1"
        self.assertEqual(g._clean_user_stop_address(addr), addr)

    def test_real_source_address_on_user_stop_is_kept(self):
        # If a real Places/geocode step DID set a full address on the stop, it is
        # kept (only the model's value and stubs are rejected).
        addr = "20 Đ. Lê Lợi, Phường Bến Nghé, Quận 1"
        orig = _user_stop("Thi Bar Saigon", "10.767660, 106.693960")
        orig["address"] = addr
        entry = {"name": "Thi Bar Saigon", "address": "Đ."}
        out = g._user_pin_merge_fields(entry, orig)
        self.assertEqual(out["address"], addr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
