r"""
LOCAL-855D item 3 — fact-sheet + ONE cheap verification call for user stops.
============================================================================
The bounce proved regexes cannot win the fabrication fight. This replaces the
approach: build a FACT SHEET from what is KNOWN, run ONE batched gpt-4.1-mini
call that labels each body sentence SUPPORTED / SENSORY / UNSUPPORTED, drop the
UNSUPPORTED ones, and fall back to grounded_user_stop_body() when fewer than 2
survive. Logs "[LOCAL-855D] verify <stop> kept K dropped D".

These tests run OFFLINE by monkeypatching the single network call
(user_stop_verify._call_openai) with a canned label set — the real call is
exercised live in the submission run. They assert the *decision logic* (drop /
grounded / preserve), the fact sheet, the log line, and the cost accounting.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_verify as usv


SOPHIA = """Step-by-Step Audio Guided Tour: Ho Chi Minh City, Vietnam - Cycling Tour

Stop 1: Longan

Address: 8 Đ. Lê Lợi, Phường Bến Thành, Quận 1

Coordinates: 10.7791, 106.6996

Type/Specialty: Fruit Cafe

Specific Examples: Fresh fruit juices, tropical fruit salads, local desserts

Orientation: Step inside and pause near the counter of dark lacquered wood. Here, the longan's translucent flesh offers a quiet homage to that mythic past. Hagimex, a Vietnamese company, handpicks longan at its peak ripeness. Though not directly tied to this café, the process reflects the region's care.

Directions: Head east. It is roughly 500 meters away.

Stop 2: Acoustic Bar

Address: 1 Ngô Thời Nhiệm, Quận 3

Coordinates: 10.7812, 106.6899

Type/Specialty: Acoustic Music Bar

Specific Examples: Intimate performances, local artist showcases

Orientation: The unassuming façade gives way to an intimate room. The bar has played a critical role for many local artists who might otherwise remain unheard. One account that lingers among regulars tells of a fledgling artist discovered here.

Directions: Head north. It is roughly 550 meters away.
"""


def _fake_labels(label_map):
    """Return a _call_openai stand-in yielding the given {stop_id:{i:label}}."""
    def _fake(system, user, api_key, model, timeout=40):
        stops = []
        for sid, labs in label_map.items():
            stops.append({"id": sid,
                          "labels": [{"i": i, "label": l} for i, l in labs.items()]})
        return {"stops": stops}, 900, 120
    return _fake


class TestFactSheet(unittest.TestCase):
    def test_fact_sheet_has_known_fields_only(self):
        poi = {"name": "Longan", "type_specialty": "Fruit Cafe",
               "address": "8 Đ. Lê Lợi, Phường Bến Thành, Quận 1",
               "specific_examples": "Fresh fruit juices"}
        fs = usv.build_fact_sheet(poi, "Ho Chi Minh City, Vietnam")
        self.assertEqual(fs["name"], "Longan")
        self.assertEqual(fs["kind"], "Fruit Cafe")
        self.assertIn("Quận 1", fs["district"])
        self.assertEqual(fs["city"], "Ho Chi Minh City")
        # No fabricated keys.
        self.assertNotIn("history", fs)
        self.assertNotIn("retrieved_sources", fs)

    def test_fact_sheet_lists_retrieved_sources(self):
        poi = {"name": "Notre-Dame", "type_specialty": "Cathedral"}
        fs = usv.build_fact_sheet(poi, "Saigon",
                                  outdoor_facts=["Built between 1863 and 1880."])
        self.assertIn("retrieved_sources", fs)
        self.assertIn("1863", fs["retrieved_sources"][0])


class TestVerifyDrops(unittest.TestCase):
    def setUp(self):
        self._orig = usv._call_openai

    def tearDown(self):
        usv._call_openai = self._orig

    def test_unsupported_sentences_dropped_supported_kept(self):
        # Longan: s0 SENSORY, s1 UNSUPPORTED (mythic past), s2 UNSUPPORTED
        # (Hagimex), s3 UNSUPPORTED (no direct tie). Acoustic: s0 SENSORY,
        # s1 UNSUPPORTED (critical role), s2 UNSUPPORTED (anecdote).
        usv._call_openai = _fake_labels({
            0: {0: "SENSORY", 1: "UNSUPPORTED", 2: "UNSUPPORTED", 3: "UNSUPPORTED"},
            1: {0: "SENSORY", 1: "UNSUPPORTED", 2: "UNSUPPORTED"},
        })
        out, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["Longan", "Acoustic Bar"], "Ho Chi Minh City, Vietnam",
            api_key="x")
        self.assertTrue(rep["ran"])
        # Fabrications gone.
        for bad in ["mythic past", "Hagimex", "not directly tied",
                    "critical role", "lingers among regulars", "fledgling artist"]:
            self.assertNotIn(bad, out, f"fabrication survived: {bad}")

    def test_fewer_than_two_survive_uses_grounded_body(self):
        # Longan: only 1 SENSORY survives (< 2) -> grounded body replaces it.
        usv._call_openai = _fake_labels({
            0: {0: "SENSORY", 1: "UNSUPPORTED", 2: "UNSUPPORTED", 3: "UNSUPPORTED"},
            1: {0: "SUPPORTED", 1: "SUPPORTED", 2: "UNSUPPORTED"},
        })
        logs = []
        out, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["Longan", "Acoustic Bar"], "Ho Chi Minh City, Vietnam",
            api_key="x", log=logs.append)
        longan = next(s for s in rep["stops"] if s["stop"] == "Longan")
        self.assertTrue(longan["grounded"], rep["stops"])
        # Grounded body names the venue + kind, carries no fabrication.
        self.assertIn("Longan is", out)
        self.assertNotIn("mythic past", out)
        self.assertTrue(any("verify Longan kept" in m for m in logs), logs)

    def test_log_line_format(self):
        usv._call_openai = _fake_labels({
            0: {0: "SENSORY", 1: "SUPPORTED", 2: "UNSUPPORTED", 3: "UNSUPPORTED"},
            1: {0: "SENSORY", 1: "SUPPORTED", 2: "UNSUPPORTED"},
        })
        logs = []
        usv.verify_user_stops_in_text(
            SOPHIA, ["Longan", "Acoustic Bar"], "Ho Chi Minh City",
            api_key="x", log=logs.append)
        self.assertTrue(any("[LOCAL-855D] verify Longan kept 2 dropped 2" in m
                            for m in logs), logs)

    def test_cost_is_reported_and_cheap(self):
        usv._call_openai = _fake_labels({0: {0: "SENSORY"}, 1: {0: "SENSORY"}})
        _, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["Longan", "Acoustic Bar"], "Ho Chi Minh City", api_key="x")
        self.assertGreater(rep["cost_usd"], 0.0)
        self.assertLess(rep["cost_usd"], 0.005, rep)

    def test_no_api_key_leaves_text_unchanged(self):
        out, rep = usv.verify_user_stops_in_text(
            SOPHIA, ["Longan"], "Ho Chi Minh City", api_key="")
        self.assertFalse(rep["ran"])
        self.assertEqual(out, SOPHIA)

    def test_structure_lines_preserved(self):
        usv._call_openai = _fake_labels({
            0: {0: "SENSORY", 1: "UNSUPPORTED", 2: "UNSUPPORTED", 3: "UNSUPPORTED"},
            1: {0: "SENSORY", 1: "SUPPORTED", 2: "UNSUPPORTED"},
        })
        out, _ = usv.verify_user_stops_in_text(
            SOPHIA, ["Longan", "Acoustic Bar"], "Ho Chi Minh City", api_key="x")
        # Field lines and directions untouched.
        self.assertIn("Address: 8 Đ. Lê Lợi, Phường Bến Thành, Quận 1", out)
        self.assertIn("Coordinates: 10.7791, 106.6996", out)
        self.assertIn("Type/Specialty: Fruit Cafe", out)
        self.assertIn("Directions: Head east.", out)


class TestModeDetectionNotApplicable(unittest.TestCase):
    pass


class TestDocumentedKindAndConclusion(unittest.TestCase):
    def setUp(self):
        self._orig = usv._call_openai

    def tearDown(self):
        usv._call_openai = self._orig

    def test_documented_monument_is_skipped_dates_kept(self):
        # A cathedral stop must be skipped so a dated sentence survives even if
        # the model would (wrongly) call it UNSUPPORTED.
        tour = (
            "Audio Guided Tour: Saigon - Walking Tour\n\n"
            "Stop 1: Notre-Dame Cathedral Basilica of Saigon\n\n"
            "Coordinates: 10.7797, 106.6992\n\n"
            "Type/Specialty: Cathedral\n\n"
            "Orientation: The red-brick towers rise above the square. "
            "The cathedral was built between 1863 and 1880.\n\n")
        # Model would label everything UNSUPPORTED — but the stop is skipped.
        usv._call_openai = _fake_labels({0: {0: "UNSUPPORTED", 1: "UNSUPPORTED"}})
        logs = []
        out, rep = usv.verify_user_stops_in_text(
            tour, ["Notre-Dame Cathedral Basilica of Saigon"], "Saigon",
            api_key="x", log=logs.append)
        self.assertIn("1863 and 1880", out, "monument date was over-scrubbed")
        self.assertTrue(any("skipped (documented monument" in m for m in logs), logs)

    def test_conclusion_paragraph_not_counted_as_body(self):
        # The trailing tour-conclusion absorbed into the last stop block must not
        # be verified; a thin stop with 1 real sentence -> grounded body.
        tour = (
            "Audio Guided Tour: HCMC - Cycling Tour\n\n"
            "Stop 1: Acoustic Bar\n\n"
            "Coordinates: 10.7705, 106.6890\n\n"
            "Type/Specialty: Live music bar\n\n"
            "Specific Examples: Acoustic sets, open mic nights\n\n"
            "Orientation: Approach the narrow doorway marked by wooden panels.\n\n"
            "Across these stops, one thread runs through: the places you chose. "
            "That's 1 stop in all.\n\n")
        usv._call_openai = _fake_labels({0: {0: "SENSORY"}})
        out, rep = usv.verify_user_stops_in_text(
            tour, ["Acoustic Bar"], "Ho Chi Minh City", api_key="x")
        ab = next(s for s in rep["stops"] if s["stop"] == "Acoustic Bar")
        # Only 1 body sentence (conclusion excluded) -> grounded body.
        self.assertTrue(ab["grounded"], rep["stops"])
        self.assertIn("Acoustic Bar is", out)
        # Conclusion text is left in place (not treated as stop narration).
        self.assertIn("Across these stops", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
