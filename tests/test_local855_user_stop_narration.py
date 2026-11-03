#!/usr/bin/env python3
"""test_local855_user_stop_narration.py — LOCAL-855.

User-chosen stops were narrated about the wrong thing. The strings below are the
EXACT defects from LOCAL-852's own 7/7 reproduction of Michael's "Sophia's biking
tour in Ho Chi Minh City" (submission_artifacts/local852/live_tour_7stops.txt):

  1. Wrong subject: "Rambutan" (Restaurant and Bar) narrated as rambutan TREES;
     "Longan" (Bar) narrated as "this street, named Longan" + a dragon legend.
  2. Cross-tour leak: "Paris Street; Rainy Day," which you saw at the Art
     Institute of Chicago" — no Chicago stop in this tour.
  3. Filler unrelated to a thin venue (airport project, Cần Thơ merger, 1975
     offensive, Hồ Chí Minh pseudonyms): a thin user stop stays short & on-topic.
  4. Unsourced dated claims about a user venue: dropped.
  5. Invented street in directions: "intersection with Le Van Sy Street" between
     two stops ~150 m apart — distance + compass only when there is no route data.
  6. Mode: a transport word (biking) in the request sets the mode.

Deterministic; no network, no LLM. The narration-prompt defects (1/3/4) are
asserted on the prompt BLOCK that binds generation (fix-at-source), and the
callback/street defects (2/5) on the deterministic guards that fire on the exact
delivered sentences.

Run: python3 -m pytest tests/test_local855_user_stop_narration.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cross_stop_reference_guard as csrg
import directions_generator as dgen
import user_stop_narration as usn
import generate_tour_text as gtt


# The seven delivered stop titles for the Sophia tour, as headers.
_SOPHIA_TITLES = [
    "Rambutan", "Longan", "The Crazy street",
    "The LGBT bar 🌈Thi Bar Saigon", "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3", "An Spa",
]


class Defect6Mode(unittest.TestCase):
    """A transport word in the TOUR_TYPE sets mode=bike on the user-stops path."""

    def test_biking_tour_type_detects_bike(self):
        self.assertEqual(gtt._detect_transport_mode("Sophia's biking tour"), "bike")

    def test_cycling_word_detects_bike(self):
        self.assertEqual(gtt._detect_transport_mode("a cycling tour"), "bike")

    def test_plain_city_location_is_on_foot(self):
        # The field request's location alone does not carry the mode.
        self.assertEqual(
            gtt._detect_transport_mode("Ho Chi Minh City, Vietnam"), "on_foot")


class Defect1SubjectBinding(unittest.TestCase):
    """A bar named like a fruit/street is narrated as the VENUE, never the name's
    literal meaning."""

    def _block(self, name, type_specialty, examples=""):
        poi = {"name": name, "type_specialty": type_specialty,
               "specific_examples": examples, "user_explicit": True}
        return usn.user_stop_subject_block(poi, "Ho Chi Minh City, Vietnam")

    def test_rambutan_bar_not_fruit(self):
        block = self._block("Rambutan", "Restaurant and Bar",
                            "Tropical cocktails, live music")
        self.assertIn("Rambutan", block)
        self.assertIn("Restaurant and Bar", block)
        # The block forbids the fruit/tree reading and binds to the venue kind.
        self.assertIn("not a fruit", block)
        self.assertRegex(block, r"bar")

    def test_longan_bar_not_a_street(self):
        block = self._block("Longan", "Bar", "Signature cocktails, local beers")
        # Forbids "the street is named Longan" and the legend reading.
        self.assertIn('named Longan', block)
        self.assertIn("legend", block)
        self.assertIn("not a fruit", block)

    def test_non_user_stop_no_block(self):
        poi = {"name": "Rambutan", "type_specialty": "Restaurant and Bar"}
        self.assertEqual(usn.user_stop_subject_block(poi, "x"), "")


class Defect3And4SayLessNoUnsourced(unittest.TestCase):
    """A thin user venue stays SHORT and on-topic — no regional/national filler,
    no unsourced dated claim."""

    def test_thin_venue_short_stop_instruction(self):
        poi = {"name": "A Star is Born", "type_specialty": "Karaoke Bar",
               "user_explicit": True}  # no sourced material attached
        block = usn.user_stop_subject_block(poi, "Ho Chi Minh City, Vietnam")
        self.assertIn("SHORT", block)
        self.assertIn("2-4 sentences", block)

    def test_block_forbids_regional_history_filler(self):
        poi = {"name": "Longan", "type_specialty": "Bar", "user_explicit": True}
        block = usn.user_stop_subject_block(poi, "Ho Chi Minh City, Vietnam")
        # The airport project / provincial merger / 1975 offensive / national
        # figure fillers are exactly what "no … history that does not name this
        # venue" forbids.
        self.assertIn("STAY ON THE VENUE", block)
        self.assertIn("war", block.lower())

    def test_block_forbids_unsourced_dated_claims(self):
        # Thi Bar "emerged in 2016 … VietPride 2018", Acoustic Bar "2015",
        # An Spa address contradiction — all dated/address claims with no source.
        poi = {"name": "The LGBT bar 🌈Thi Bar Saigon",
               "type_specialty": "LGBT Bar", "user_explicit": True}
        block = usn.user_stop_subject_block(poi, "Ho Chi Minh City, Vietnam")
        self.assertIn("NO UNSOURCED DATED CLAIMS", block)

    def test_has_sourced_material_flips_when_present(self):
        poi = {"name": "X", "user_explicit": True, "_customer_voice": {"a": 1}}
        self.assertTrue(usn.has_sourced_material(poi))
        self.assertFalse(usn.has_sourced_material({"name": "X",
                                                   "user_explicit": True}))

    def test_scrub_drops_airport_filler_keeps_venue(self):
        poi = {"name": "Rambutan", "type_specialty": "Restaurant/Bar",
               "user_explicit": True}
        body = (
            "The sharp crackle of rambutan leaves offers a connection to the land. "
            "Since the Vietnamese government approved the construction of Long "
            "Thanh International Airport on January 4, 2021, development east of "
            "the city has accelerated. As the breeze shifts, the shade beneath "
            "the rambutan offers a brief respite.")
        out, dropped = usn.scrub_user_stop_body(body, poi, "Ho Chi Minh City, Vietnam")
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("Long Thanh", out)
        self.assertIn("rambutan leaves", out)

    def test_scrub_drops_can_tho_merger(self):
        poi = {"name": "Longan", "type_specialty": "Bar", "user_explicit": True}
        body = (
            "The rough bark recalls the longan tree. On June 12, 2025, the "
            "National Assembly passed Resolution No. 202/2025/QH15, merging Hậu "
            "Giang and Sóc Trăng provinces into the expanded Cần Thơ "
            "municipality. The quiet sweetness lingers here.")
        out, dropped = usn.scrub_user_stop_body(body, poi, "Ho Chi Minh City, Vietnam")
        self.assertTrue(dropped)
        self.assertNotIn("Resolution No. 202", out)

    def test_scrub_drops_vietpride_fabrication_even_with_material(self):
        # Thi Bar "2018 drag show" / "2019 VietPride" are unsourced dated claims;
        # they must be dropped even when the stop has some attached material.
        poi = {"name": "Thi Bar Saigon", "type_specialty": "LGBT Bar",
               "user_explicit": True, "_customer_voice": {"quotes": ["great"]}}
        body = (
            "The neon rainbow sign welcomes you. In 2018, this venue hosted the "
            "first drag show in a mainstream bar in Ho Chi Minh City. A year "
            "later, in 2019, Thi Bar Saigon took center stage during VietPride. "
            "Inside, the music and colored lights create a welcoming room.")
        out, dropped = usn.scrub_user_stop_body(body, poi, "Ho Chi Minh City, Vietnam")
        self.assertEqual(len(dropped), 2)
        self.assertNotIn("2018", out)
        self.assertNotIn("VietPride", out)
        self.assertIn("neon rainbow sign", out)

    def test_scrub_noop_for_non_user_stop(self):
        poi = {"name": "Longan", "type_specialty": "Bar"}  # not user_explicit
        body = ("On June 12, 2025, the National Assembly passed Resolution No. "
                "202/2025/QH15.")
        out, dropped = usn.scrub_user_stop_body(body, poi, "x")
        self.assertEqual(dropped, [])
        self.assertEqual(out, body)


class Defect2CrossTourCallback(unittest.TestCase):
    """No "you saw at <place not in the tour>" callback survives."""

    def test_art_institute_of_chicago_leak_dropped(self):
        text = (
            "Stop 3: The Crazy street\n\n"
            "Type/Specialty: Street\n\n"
            "The Crazy street earns its name from the swirl of activity. "
            "Like the intersecting streets in Gustave Caillebotte\u2019s 1877 "
            "painting \u201cParis Street; Rainy Day,\u201d which you saw at the "
            "Art Institute of Chicago, The Crazy street presents a shifting "
            "tableau where old patterns meet modern impulse."
        )
        out, n = csrg.strip_unseen_callbacks_in_text(text)
        self.assertEqual(n, 1)
        self.assertNotIn("Art Institute of Chicago", out)
        self.assertNotIn("which you saw at", out)
        # The on-topic opening sentence is kept.
        self.assertIn("The Crazy street earns its name", out)

    def test_saw_at_delivered_stop_is_kept(self):
        # A callback naming a DELIVERED stop is legitimate continuity.
        norms = csrg._delivered_title_norms(_SOPHIA_TITLES)
        self.assertIsNone(
            csrg._saw_at_unseen_place(
                "The energy you saw at the Acoustic Bar carries here.", norms))

    def test_external_place_flagged(self):
        norms = csrg._delivered_title_norms(_SOPHIA_TITLES)
        self.assertEqual(
            csrg._saw_at_unseen_place(
                "which you saw at the Art Institute of Chicago, the street", norms),
            "Art Institute of Chicago")


class Defect5InventedStreet(unittest.TestCase):
    """No invented street name in directions when there is no route data —
    distance + compass only."""

    def test_le_van_sy_street_is_flagged_when_no_addresses(self):
        # The exact invented-street sentence, no addresses on either stop.
        bad = ("Continue until you reach the intersection with Le Van Sy Street, "
               "where you'll find Longan just a short walk ahead on your right.")
        self.assertEqual(dgen.names_invented_street(bad, "", ""), "Le Van Sy Street")

    def test_real_street_in_address_is_kept(self):
        self.assertEqual(
            dgen.names_invented_street(
                "Head along Nguyen Hue Street to the next stop.",
                "12 Nguyen Hue Street, District 1", ""),
            "")

    def test_distance_and_compass_from_coordinates(self):
        # Rambutan -> Longan, the two pins ~150 m apart.
        metres, compass = dgen.distance_and_compass(
            {"coordinates": "10.7761, 106.6950"},
            {"coordinates": "10.7765, 106.6938"})
        self.assertIsNotNone(metres)
        self.assertLess(metres, 300)
        self.assertIn(compass, ("north", "northeast", "east", "southeast",
                                "south", "southwest", "west", "northwest"))

    def test_deterministic_fallback_is_distance_and_compass(self):
        line = gtt._directions_fallback_855(
            {"name": "Rambutan", "coordinates": "10.7761, 106.6950"},
            {"name": "Longan", "coordinates": "10.7765, 106.6938"})
        self.assertIn("Longan", line)
        self.assertRegex(line, r"Head (north|northeast|east|southeast|south|"
                               r"southwest|west|northwest)")
        # Never names a street.
        self.assertNotIn("Street", line)

    def test_fallback_without_coords_degrades_to_continue(self):
        line = gtt._directions_fallback_855({"name": "A"}, {"name": "B"})
        self.assertEqual(line, "Continue to B.")

    def test_bare_vietnamese_street_flagged_when_no_route_data(self):
        # Suffixless street names the no-route prompt must not produce.
        t = ("Start by cycling down Nguyễn Thị Diệu. When you reach the "
             "intersection, turn onto Võ Văn Tần. It is roughly 150 meters away.")
        nav = dgen.names_navigation_landmark(t, keep_names=("Longan",
                                                            "The Crazy street"))
        self.assertTrue(nav)

    def test_distance_compass_fallback_has_no_navigation_landmark(self):
        fb = "Head north to Longan — it is about a one- or two-minute walk away."
        self.assertEqual(
            dgen.names_navigation_landmark(fb, keep_names=("Rambutan", "Longan")),
            "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
