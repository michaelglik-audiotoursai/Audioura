#!/usr/bin/env python3
"""test_local589_chrome_field_names.py — LOCAL-589 Deliverable 3 (chrome).

The Griffin field defect (tour 394, 2026-10-05): R4 refill then "VERIFIED" these
site-chrome labels as exhibition stops —

    Function Rentals, Calls For Entry, Griffin Salon, Griffin Travel,
    Exhibitions Closed, Arthur Griffin Archive,
    Griffin Museum Board Of Directors 2

LOCAL-583's `is_chrome_title` already catches five of the seven, but TWO escaped
and shipped as "verified" stops:

    * "Exhibitions Closed"      — plural of the "exhibition closed" exact label
    * "Arthur Griffin Archive"  — a venue-branded institutional SECTION label
      (founder's name + the "archive" section token); "arthur" was read as a
      distinctive content word, so the title survived.

This test is RED before the LOCAL-589 chrome extension and GREEN after. It also
asserts the real Griffin shows still survive — the filter is page furniture
vocabulary, NOT a show blocklist.

Run: python3 -m pytest test_local589_chrome_field_names.py -q
"""
import unittest

from exhibition_discovery import is_chrome_title, reject_chrome_titles

VENUE = "griffin museum of photography , Winchester, MA"

# The exact seven chrome labels R4 "verified" in the field (tour 394).
FIELD_CHROME = [
    "Function Rentals", "Calls For Entry", "Griffin Salon", "Griffin Travel",
    "Exhibitions Closed", "Arthur Griffin Archive",
    "Griffin Museum Board Of Directors 2",
]

# The two that escaped LOCAL-583 and must now be caught.
NEWLY_CAUGHT = ["Exhibitions Closed", "Arthur Griffin Archive"]

# Real Griffin shows — must ALWAYS survive.
REAL_SHOWS = [
    "Lua Kobayashi | The Persistence of Memories",
    "Homage | Robert Frank: The Americans",
    "Tabitha Soren | An Artist Life",
    "Intertidal : Field Notes",
    "BU Masters Show 2026 | Traces: Pursuing Process",
    "Earth, Wind & Fire", "ULTRASOUND", "TLC",
    # Extra realism: a show whose title ends in an ordinary word, and a
    # person-named show, to prove the archive/section rule is not over-broad.
    "State Of Our Union 2026",
    "Robert Frank: The Americans",
]


class TestFieldChromeNames(unittest.TestCase):
    def test_all_seven_field_names_are_chrome(self):
        for t in FIELD_CHROME:
            self.assertTrue(
                is_chrome_title(t, VENUE),
                f"Field chrome '{t}' was NOT classified as chrome"
            )

    def test_the_two_escaped_names_now_caught(self):
        for t in NEWLY_CAUGHT:
            self.assertTrue(
                is_chrome_title(t, VENUE),
                f"'{t}' escaped the chrome filter (LOCAL-589 regression)"
            )

    def test_none_of_the_seven_is_verifiable(self):
        survivors = reject_chrome_titles(FIELD_CHROME, VENUE)
        self.assertEqual(
            [], survivors,
            f"Chrome survived reject_chrome_titles: {survivors}"
        )

    def test_real_shows_still_survive(self):
        for t in REAL_SHOWS:
            self.assertFalse(
                is_chrome_title(t, VENUE),
                f"Real show '{t}' was wrongly rejected as chrome"
            )
        survivors = reject_chrome_titles(REAL_SHOWS, VENUE)
        self.assertEqual(set(REAL_SHOWS), set(survivors))


if __name__ == '__main__':
    unittest.main(verbosity=2)
