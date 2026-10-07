#!/usr/bin/env python3
"""test_local603_meter_and_l2.py — LOCAL-603 (D618), meter + L2 guard cases.

  * THE METER COUNTS THE PREFLIGHT. The one grounded preflight call flows through
    story_leads.gemini_with_sources(grounded=True), so the LOCAL-594 grounding
    meter (requests AND queries) counts it, and cost_rates prices the queries.
  * AN L2 BUILD MAKES NO PREFLIGHT CALL. Inside the l2_by_reference
    `grounding_forbidden()` guard, preflight() raises GroundingForbiddenError
    (it must never spend on grounding in a by-reference build) and safe_preflight()
    turns that into an explicit "skipped" marker with ZERO grounded requests.

The Gemini wire is stubbed; no network, no real key.

Run: python3 -m pytest tests/test_local603_meter_and_l2.py -q
"""
import json as _json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

import story_leads  # noqa: E402
import l2_by_reference  # noqa: E402
import venue_preflight as vp  # noqa: E402
from cost_rates import grounding_query_cost  # noqa: E402


class _FakeResp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _Wire:
    """Fake requests.post minting N webSearchQueries per grounded request."""

    def __init__(self, answer, queries_per_request=3):
        self.answer = answer
        self.qpr = queries_per_request
        self.grounded_requests = 0

    def post(self, url, headers=None, json=None, timeout=None, **kwargs):
        body = json or {}
        tools = body.get("tools") or []
        grounded = any("google_search" in (t or {}) for t in tools)
        gm = {}
        if grounded:
            self.grounded_requests += 1
            gm = {"webSearchQueries": [f"q{i}" for i in range(self.qpr)],
                  "groundingChunks": [
                      {"web": {"title": "src", "uri": "https://redir/0"}}],
                  "groundingSupports": []}
        text = _json.dumps(self.answer)
        return _FakeResp({"candidates": [{"content": {"parts": [{"text": text}]},
                                          "groundingMetadata": gm}]})

    def head(self, url, allow_redirects=True, timeout=20):
        return type("H", (), {"url": "https://museum.org/visit"})()


OPEN_ANSWER = {
    "status": "open", "closed_since": "", "address": "", "hours": "Mon-Fri 9-5",
    "admission": "Free", "current_exhibitions_or_highlights": [],
}


class TestMeterCountsPreflight(unittest.TestCase):
    """The preflight is counted by the LOCAL-594 grounding meter."""

    def setUp(self):
        import requests
        self._orig_post = requests.post
        self._orig_head = requests.head
        self.wire = _Wire(OPEN_ANSWER, queries_per_request=3)
        requests.post = self.wire.post
        requests.head = self.wire.head
        story_leads.reset_grounding_requests()

    def tearDown(self):
        import requests
        requests.post = self._orig_post
        requests.head = self._orig_head

    def test_preflight_increments_requests_and_queries(self):
        vp.preflight("Open Museum", "Boston", db_url=None, use_cache=False)
        # One grounded request, three search queries — counted on the meter.
        self.assertEqual(story_leads.get_grounding_requests(), 1)
        self.assertEqual(story_leads.get_grounding_queries(), 3)
        # And the dollar figure follows the queries (the invoice unit).
        self.assertAlmostEqual(
            grounding_query_cost(story_leads.get_grounding_queries()),
            3 * 0.014, places=6)

    def test_two_preflights_accumulate_on_the_meter(self):
        vp.preflight("Museum A", "Boston", db_url=None, use_cache=False)
        vp.preflight("Museum B", "Boston", db_url=None, use_cache=False)
        self.assertEqual(story_leads.get_grounding_requests(), 2)
        self.assertEqual(story_leads.get_grounding_queries(), 6)
        self.assertEqual(self.wire.grounded_requests, 2)


class TestL2BuildMakesNoPreflightCall(unittest.TestCase):
    """Inside the L2 by-reference guard, the preflight must not spend on grounding."""

    def setUp(self):
        import requests
        self._orig_post = requests.post
        self._orig_head = requests.head
        self.wire = _Wire(OPEN_ANSWER)
        requests.post = self.wire.post
        requests.head = self.wire.head
        story_leads.reset_grounding_requests()

    def tearDown(self):
        import requests
        requests.post = self._orig_post
        requests.head = self._orig_head

    def test_preflight_raises_inside_guard(self):
        with l2_by_reference.grounding_forbidden():
            with self.assertRaises(l2_by_reference.GroundingForbiddenError):
                vp.preflight("Any Museum", "Boston", db_url=None, use_cache=False)
        # No grounded request ever reached the wire.
        self.assertEqual(self.wire.grounded_requests, 0)
        self.assertEqual(story_leads.get_grounding_requests(), 0)

    def test_safe_preflight_skips_inside_guard(self):
        with l2_by_reference.grounding_forbidden():
            res = vp.safe_preflight("Any Museum", "Boston",
                                    db_url=None, use_cache=False)
        self.assertEqual(res.get("skipped"), "l2_by_reference")
        self.assertEqual(res["status"], "unknown")
        # The gate on a skipped preflight never refuses.
        self.assertIsNone(vp.gate("Any Museum", "Boston", res))
        self.assertEqual(self.wire.grounded_requests, 0)
        self.assertEqual(story_leads.get_grounding_requests(), 0)

    def test_outside_guard_the_call_resumes(self):
        # Sanity: the guard is scoped — outside it, the preflight calls normally.
        res = vp.safe_preflight("Open Museum", "Boston",
                                db_url=None, use_cache=False)
        self.assertEqual(res["status"], "open")
        self.assertEqual(self.wire.grounded_requests, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
