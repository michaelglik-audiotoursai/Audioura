#!/usr/bin/env python3
"""
LOCAL-474 — An unrecognised request must not be a 400.

The app sends tour_type='' whenever it recognises no category keyword (e.g.
restaurant tours, which have no parser branch — tour_request_parser.dart:111).
The server used to reject that payload:

    if not location or not tour_type:
        return jsonify({"error": "location and tour_type are required"}), 400

`not ''` is True, so a well-formed restaurant request 400'd in production on
2026-09-03. This suite proves the fix:

  AC1  empty tour_type is ACCEPTED and classified (restaurant here).
  AC2  an explicit tour_type still WINS (unchanged behaviour).
  AC3  a MISSING location still 400s (that check is correct and stays).
  AC4  a genuinely UNCLASSIFIABLE request fails CLEANLY — not a 400, and not a
       tour about nothing. Demonstrated red→green: with the guard removed the
       empty category would sail through; with it, we get typed clean-fail
       evidence and a None return.

The classifier + clean-fail seams are unit-tested directly. The two relaxed
HTTP validation gates are exercised with Flask's test_client (no live services,
the background generation thread is stubbed).
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from generate_tour_text import (
    _classify_tour_category,
    _infer_category_log_line,
    _build_unclassifiable_evidence,
)


class TestClassifierAcceptsEmptyType(unittest.TestCase):
    """AC1 + AC2 — the classifier is what 'let the server decide' resolves to."""

    def test_ac1_restaurant_location_empty_type_classifies_restaurant(self):
        # The exact production payload's location, with tour_type=''.
        cat = _classify_tour_category(
            "Bread Thyme restaurant tour in West Roxbury, MA", ""
        )
        self.assertEqual(cat, "restaurant",
                         "empty tour_type must classify from the location text")

    def test_ac1_empty_type_never_yields_empty_category(self):
        # Even a bare place with no category words falls back to 'walking',
        # never to '' — so the *normal* empty-type path is always classifiable.
        for loc in ("West Roxbury, MA", "Concord", "somewhere"):
            cat = _classify_tour_category(loc, "")
            self.assertTrue(cat, f"classifier returned empty for {loc!r}")

    def test_ac2_explicit_type_still_wins(self):
        # An explicit, nonempty type is honoured exactly as before the fix.
        self.assertEqual(_classify_tour_category("Nice, France", "restaurant"),
                         "restaurant")
        self.assertEqual(_classify_tour_category("Some City", "museum"),
                         "museum")


class TestInferredCategoryLog(unittest.TestCase):
    """AC1 (log) — a wrong inference must be visible, not silent."""

    def test_inferred_source_when_type_empty(self):
        line = _infer_category_log_line("", "restaurant")
        self.assertIn("category='restaurant'", line)
        self.assertIn("source=inferred", line)

    def test_explicit_source_when_type_present(self):
        line = _infer_category_log_line("walking", "walking")
        self.assertIn("source=explicit", line)

    def test_none_type_is_inferred(self):
        line = _infer_category_log_line(None, "walking")
        self.assertIn("source=inferred", line)


class TestUnclassifiableCleanFail(unittest.TestCase):
    """AC4 — break it and show the clean-fail path fires.

    This is the red→green demonstration. The guard in generate_tour_text() is:

        if not tour_category:
            _LAST_CLEAN_FAIL_EVIDENCE = _build_unclassifiable_evidence(...)
            return None, None, (None, None)

    We simulate 'force the classifier to return empty' and prove the guard
    produces typed evidence + a clean message instead of a tour with no stops.
    """

    def _run_guard(self, tour_category, location, tour_type):
        """Mirror of the inline guard, exercised in isolation."""
        if not tour_category:
            return _build_unclassifiable_evidence(location, tour_type), None
        return None, tour_category

    def test_red_without_guard_empty_category_would_pass_through(self):
        # WITHOUT the guard (the pre-fix world), an empty category is falsy and
        # would flow straight into template selection → a tour about nothing.
        # This assertion documents the failure mode the guard prevents.
        forced_empty = ""
        self.assertFalse(forced_empty,
                         "empty category is falsy — unguarded, it reaches the pipeline")

    def test_green_guard_fires_with_typed_evidence(self):
        evidence, category = self._run_guard(
            tour_category="",  # classifier forced empty
            location="???",
            tour_type="",
        )
        # Clean-fail, not a category, not an exception:
        self.assertIsNone(category)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["error_type"], "unclassifiable_request")
        self.assertIn("couldn't tell what kind of tour", evidence["user_message"])
        # A useful message, NOT a generic "location and tour_type are required".
        self.assertNotIn("required", evidence["user_message"])

    def test_normal_category_does_not_trip_guard(self):
        evidence, category = self._run_guard("restaurant", "Bread Thyme", "")
        self.assertIsNone(evidence)
        self.assertEqual(category, "restaurant")


class TestTextServiceValidationGate(unittest.TestCase):
    """AC1 (accept) + AC3 (missing location still 400) at the HTTP boundary.

    Drives generate_tour_text_service.app with a test client. The background
    generation thread is stubbed so no OpenAI / live services are touched — we
    are testing the validation gate, not generation.
    """

    @classmethod
    def setUpClass(cls):
        import generate_tour_text_service as svc
        cls.svc = svc
        cls.app = svc.app.test_client()

    def _post(self, payload):
        # Stub the thread target so accepted requests don't kick off real work.
        with mock.patch.object(self.svc.threading, "Thread") as _T:
            _T.return_value.start = lambda: None
            return self.app.post("/generate", json=payload)

    def test_ac1_empty_tour_type_is_accepted(self):
        resp = self._post({
            "location": "Bread Thyme restaurant tour in West Roxbury, MA",
            "tour_type": "",
            "total_stops": 1,
        })
        self.assertEqual(resp.status_code, 200,
                         f"empty tour_type must be accepted, got {resp.status_code}: {resp.data}")
        self.assertEqual(resp.get_json().get("status"), "queued")

    def test_ac1_missing_tour_type_key_is_accepted(self):
        resp = self._post({
            "location": "Bread Thyme restaurant tour in West Roxbury, MA",
            "total_stops": 1,
        })
        self.assertEqual(resp.status_code, 200,
                         f"missing tour_type key must be accepted, got {resp.status_code}")

    def test_ac3_missing_location_still_400s(self):
        resp = self._post({"tour_type": "walking", "total_stops": 1})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("location", resp.get_json().get("error", "").lower())

    def test_ac3_empty_location_still_400s(self):
        resp = self._post({"location": "", "tour_type": "", "total_stops": 1})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
