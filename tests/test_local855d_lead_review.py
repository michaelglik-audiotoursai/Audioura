"""LEAD review fixes on top of 855D: transport guard scope, empty Address capture."""
import os, re, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import transport_word_guard as twg
from user_stop_narration import grounded_user_stop_body
import user_stop_verify as usv


class TestTransportGuardScope(unittest.TestCase):
    def test_walking_street_proper_name_kept(self):
        s = "Bùi Viện Walking Street is loud at night."
        self.assertEqual(twg.correct_transport_words(s, "bike"), (s, 0))

    def test_walk_inside_kept(self):
        s = "Walk inside the cathedral to see the stained glass."
        self.assertEqual(twg.correct_transport_words(s, "bike")[1], 0)

    def test_driving_tour_noop(self):
        s = "Walk the trail to the falls; it is a short walk from the lot."
        self.assertEqual(twg.correct_transport_words(s, "vehicle"), (s, 0))

    def test_minute_walk_rewritten(self):
        out, n = twg.correct_transport_words("It is about a 19-minute walk away.", "bike")
        self.assertEqual(n, 1)
        self.assertIn("19-minute ride", out)


class TestEmptyAddressLine(unittest.TestCase):
    def test_empty_address_does_not_capture_next_line(self):
        block = "Stop 2: Thi Bar Saigon\nAddress:\nCoordinates: 10.767660, 106.693960\n"
        self.assertIsNone(usv._ADDRESS_LINE_RE.search(block))

    def test_grounded_body_never_uses_coordinates_as_district(self):
        body = grounded_user_stop_body(
            {"name": "Thi Bar Saigon", "type_specialty": "Bar",
             "address": "Coordinates: 10.767660, 106.693960"},
            "Ho Chi Minh City, Vietnam")
        self.assertNotIn("Coordinates", body)
        self.assertNotIn("10.76", body)


class TestVerifyPromptAntecedent(unittest.TestCase):
    def test_prompt_names_dangling_reference_rule(self):
        src = open(usv.__file__, encoding="utf-8").read()
        self.assertIn("His playing", src)


if __name__ == "__main__":
    unittest.main()
