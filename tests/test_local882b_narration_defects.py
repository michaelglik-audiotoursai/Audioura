#!/usr/bin/env python3
"""test_local882b_narration_defects.py — LOCAL-882B.

Three narration defects left by LOCAL-882, fixed generically (no venue names in
code, D769):

  1. A foreign institutional name read literally. Tour 547's City Hall shipped
     "opened in 1909 as a hotel named Hotel de Ville … this hotel became a
     gathering place" — a literal read of the French "hôtel de ville" (= city
     hall). The claim gate drops a sentence that assigns the venue a FUNCTION the
     evidence does not support, backed by a false-friend glossary (DATA).
     CONTROL: a real hotel whose evidence says "hotel" keeps it.

  2. An orphan quantity. Tour 547's Opera House shipped "Designed by the French
     architect Félix Olivier to seat guests" — LOCAL-880C removed the number but
     left the purpose clause. spoken_text_hygiene now removes the whole capacity
     clause when the number is gone. CONTROL: "seat themselves" / "serves guests"
     are untouched.

  3. An unsourced political-institution claim. The Opera House shipped "became
     home to both the Lower House and the Senate" with nothing in its evidence to
     source it. A political-institution claim needs an evidence sentence; else the
     gate drops it. CONTROL: a sourced bicameral claim is kept.

Run: python3 -m pytest tests/test_local882b_narration_defects.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import landmark_claim_gate as lg
import spoken_text_hygiene as sth


# ── Evidence blobs (the stop's own sources). Generic city/venue-agnostic. ──────
CITY_HALL_EV = (
    "Ho Chi Minh City Hall, formerly the Hôtel de Ville de Saïgon, is the city "
    "hall of Ho Chi Minh City, Vietnam. It was built from 1902 to 1908 and "
    "designed by Fernand Gardès in a French colonial municipal style. Today it "
    "houses the People's Committee of Ho Chi Minh City.")
# A real hotel's evidence says "hotel" — the control must keep the word.
REAL_HOTEL_EV = (
    "The Hotel Continental Saigon is a historic hotel in Ho Chi Minh City, opened "
    "in 1880. It is one of the oldest hotels in the city and has hosted many "
    "famous guests.")
OPERA_EV = (
    "The Saigon Opera House (Nhà hát Thành phố) opened in 1900, designed by the "
    "French architect Félix Olivier. It is an opera house used for concerts and "
    "theatrical performances in District 1.")
OPERA_EV_BICAMERAL = OPERA_EV + (
    " From 1955 to 1962 the building served as the home of the Lower House, and "
    "from 1967 it housed the Senate of South Vietnam, a bicameral legislature.")


# ───────────────────────── Fix #1 — venue function ────────────────────────────
class VenueFunctionFalseFriend(unittest.TestCase):

    def test_city_hall_hotel_sentence_flagged(self):
        s = ("The building before you was completed in 1908, designed by Fernand "
             "Gardè, and opened in 1909 as a hotel named Hotel de Ville.")
        bad = lg.venue_function_claims(
            s, lg._fold(CITY_HALL_EV), "City Hall", ["Hôtel de Ville de Saïgon"])
        self.assertIn("hotel", bad)

    def test_this_hotel_followup_flagged(self):
        s = "This hotel became a gathering place for colonial officials and visitors."
        bad = lg.venue_function_claims(
            s, lg._fold(CITY_HALL_EV), "City Hall", ["Hôtel de Ville de Saïgon"])
        self.assertIn("hotel", bad)

    def test_real_hotel_keeps_hotel_CONTROL(self):
        s = "It opened in 1880 as a grand hotel for European travellers."
        bad = lg.venue_function_claims(
            s, lg._fold(REAL_HOTEL_EV), "Hotel Continental Saigon", [])
        self.assertEqual(bad, [])

    def test_glossary_is_data_covers_common_false_friends(self):
        # The glossary feeds the gate; it is a reference list, not code paths.
        for name in ("hotel de ville", "rathaus", "ayuntamiento",
                     "palazzo comunale", "mairie", "camara municipal"):
            self.assertIn(name, lg._FALSE_FRIEND_INSTITUTIONS)

    def test_gate_drops_both_hotel_sentences_end_to_end(self):
        tour = (
            "Stop 1: City Hall\n"
            "The building before you was completed in 1908, designed by Fernand "
            "Gardè, and opened in 1909 as a hotel named Hotel de Ville. This hotel "
            "became a gathering place for colonial officials and visitors. In the "
            "garden courtyard, a statue of Ho Chi Minh teaching a child was installed.\n")
        new, rep = lg.filter_tour_text(
            tour, stop_evidence={1: [CITY_HALL_EV]},
            stop_authority={1: [CITY_HALL_EV]}, stop_titles={1: "City Hall"},
            stop_aliases={1: ["Hôtel de Ville de Saïgon"]},
            location="Ho Chi Minh City, Vietnam")
        self.assertNotIn("hotel", new.lower())
        self.assertIn("statue of Ho Chi Minh", new)  # the real sentence stays

    def test_sourced_year_and_architect_survive_the_hotel_drop(self):
        # Excising the false-friend clause must keep the sentence's sourced date
        # and architect, so City Hall still states when it was built.
        tour = (
            "Stop 1: City Hall\n"
            "The building was completed in 1908, designed by Fernand Gardè, and "
            "opened in 1909 as a hotel named Hotel de Ville. Its Beaux-Arts façade "
            "frames the square. Today it is the seat of the People's Committee.\n")
        new, _ = lg.filter_tour_text(
            tour, stop_evidence={1: [CITY_HALL_EV]},
            stop_authority={1: [CITY_HALL_EV]}, stop_titles={1: "City Hall"},
            stop_aliases={1: ["Hôtel de Ville de Saïgon"]},
            location="Ho Chi Minh City, Vietnam")
        self.assertNotIn("hotel", new.lower())
        self.assertIn("1908", new)
        self.assertIn("Gardè", new)

    def test_correction_helper_excises_only_the_function_clause(self):
        s = ("The building was completed in 1908, designed by Fernand Gardè, and "
             "opened in 1909 as a hotel named Hotel de Ville.")
        out = lg.venue_function_correction(s, ["hotel"])
        self.assertIsNotNone(out)
        self.assertNotIn("hotel", out.lower())
        self.assertIn("1908", out)
        self.assertIn("1909", out)


# ───────────────────────── Fix #2 — orphan capacity ───────────────────────────
class OrphanCapacityClause(unittest.TestCase):

    def test_exact_opera_orphan_removed(self):
        s = ("Designed by the French architect Félix Olivier to seat guests, its "
             "architecture is a clear echo of French colonial style.")
        out, _ = sth.audit_seating_capacity(s)
        self.assertNotIn("to seat guests", out)
        self.assertIn("Félix Olivier, its architecture", out)

    def test_capacity_to_seat_removed(self):
        out, _ = sth.audit_seating_capacity("It is a grand venue with a capacity to seat.")
        self.assertNotIn("capacity to seat", out)
        self.assertEqual(out.strip(), "It is a grand venue.")

    def test_seating_guests_participle_removed(self):
        out, _ = sth.audit_seating_capacity("The theatre, seating guests, opened in 1900.")
        self.assertNotIn("seating guests", out)
        self.assertIn("The theatre, opened in 1900.", out)

    def test_idempotent(self):
        s = "The hall was built to seat guests."
        once, _ = sth.audit_seating_capacity(s)
        twice, _ = sth.audit_seating_capacity(once)
        self.assertEqual(once, twice)
        self.assertEqual(once.strip(), "The hall was built.")

    def test_seat_themselves_CONTROL(self):
        s = "Visitors come here to seat themselves for the show."
        out, _ = sth.audit_seating_capacity(s)
        self.assertEqual(out, s)

    def test_serves_guests_CONTROL(self):
        s = "The restaurant serves guests a warm welcome all day."
        out, _ = sth.audit_seating_capacity(s)
        self.assertEqual(out, s)

    def test_standalone_helper_exported(self):
        self.assertTrue(hasattr(sth, "strip_orphan_capacity_clause"))
        out, n = sth.strip_orphan_capacity_clause("Built to seat guests.")
        self.assertNotIn("to seat guests", out)
        self.assertGreaterEqual(n, 1)


# ─────────────────────── Fix #3 — political institution ───────────────────────
class PoliticalInstitutionClaim(unittest.TestCase):

    SENT = ("Later, when the government shifted to a bicameral system, the opera "
            "house became home to both the Lower House and the Senate.")

    def test_unsourced_bicameral_flagged(self):
        bad = lg.political_institution_claims(self.SENT, lg._fold(OPERA_EV), "Opera House")
        self.assertTrue(bad)

    def test_sourced_bicameral_kept_CONTROL(self):
        bad = lg.political_institution_claims(
            self.SENT, lg._fold(OPERA_EV_BICAMERAL), "Opera House")
        self.assertEqual(bad, [])

    def test_gate_drops_unsourced_keeps_sourced(self):
        tour = (
            "Stop 1: Opera House\n"
            "The building before you opened in 1900, designed by the French "
            "architect Félix Olivier. " + self.SENT + " The Opera House stands as "
            "a reminder that art and politics have shared the same stage.\n")
        kw = dict(stop_titles={1: "Opera House"},
                  location="Ho Chi Minh City, Vietnam")
        new_unsourced, _ = lg.filter_tour_text(
            tour, stop_evidence={1: [OPERA_EV]}, stop_authority={1: [OPERA_EV]}, **kw)
        self.assertNotIn("Lower House", new_unsourced)
        self.assertNotIn("Senate", new_unsourced)
        new_sourced, _ = lg.filter_tour_text(
            tour, stop_evidence={1: [OPERA_EV_BICAMERAL]},
            stop_authority={1: [OPERA_EV_BICAMERAL]}, **kw)
        self.assertIn("Lower House", new_sourced)
        self.assertIn("Senate", new_sourced)


if __name__ == "__main__":
    unittest.main()
