#!/usr/bin/env python3
"""test_local597_guard.py — LOCAL-597 grounding/SERP guard (pure, no DB).

Proves the guard that makes an L2 by-reference build spend ZERO on grounding and
SERP:

  * grounding_forbidden() makes a grounded Gemini request (story_leads._gemini and
    gemini_with_sources) AND a Serper query (work_story_searcher._serp_search)
    RAISE GroundingForbiddenError, before any network call.
  * Outside the guard, the same call sites do NOT raise from the guard.
  * An ungrounded Gemini call is never blocked by the guard.
  * Nested guard blocks compose (the flag lifts only when the outermost exits).
  * The guard is thread-aware: a grounded call on a worker thread is forbidden too.
  * The LOCAL-594 meter stays at 0 across a guarded block, and the refusal copy
    is exactly the D613 wording.

Run: python3 -m pytest tests/test_local597_guard.py -q
"""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l2_by_reference as l2
import story_leads
import work_story_searcher as wss


class TestGuardState(unittest.TestCase):
    def test_not_forbidden_outside_guard(self):
        self.assertFalse(l2.grounding_is_forbidden())

    def test_forbidden_inside_guard_then_lifts(self):
        with l2.grounding_forbidden():
            self.assertTrue(l2.grounding_is_forbidden())
        self.assertFalse(l2.grounding_is_forbidden())

    def test_nested_guards_compose(self):
        with l2.grounding_forbidden():
            with l2.grounding_forbidden():
                self.assertTrue(l2.grounding_is_forbidden())
            # Inner exit must NOT lift the guard while the outer is still active.
            self.assertTrue(l2.grounding_is_forbidden())
        self.assertFalse(l2.grounding_is_forbidden())


class TestGroundedCallsRaise(unittest.TestCase):
    def test_grounded_gemini_raises_under_guard(self):
        with l2.grounding_forbidden():
            with self.assertRaises(l2.GroundingForbiddenError):
                story_leads._gemini("anything", grounded=True)

    def test_gemini_with_sources_raises_under_guard(self):
        with l2.grounding_forbidden():
            with self.assertRaises(l2.GroundingForbiddenError):
                story_leads.gemini_with_sources("anything", grounded=True)

    def test_serp_search_raises_under_guard(self):
        with l2.grounding_forbidden():
            with self.assertRaises(l2.GroundingForbiddenError):
                wss._serp_search("anything")

    def test_ungrounded_gemini_not_blocked_by_guard(self):
        # An ungrounded call must never raise FROM THE GUARD. It may still return
        # '' (no key) or make a free call; either way, no GroundingForbiddenError.
        with l2.grounding_forbidden():
            try:
                story_leads._gemini("hi", grounded=False)
            except l2.GroundingForbiddenError:
                self.fail("ungrounded Gemini must not be blocked by the guard")

    def test_outside_guard_serp_does_not_raise_guard_error(self):
        # Outside the guard, _serp_search must not raise GroundingForbiddenError
        # (it may return [] with no key — that is fine).
        try:
            wss._serp_search("anything")
        except l2.GroundingForbiddenError:
            self.fail("_serp_search raised the guard error outside a guarded block")


class TestGuardAcrossThreads(unittest.TestCase):
    def test_grounded_call_on_worker_thread_is_forbidden(self):
        caught = {}

        def worker():
            try:
                story_leads._gemini("x", grounded=True)
                caught["result"] = "no-raise"
            except l2.GroundingForbiddenError:
                caught["result"] = "raised"
            except Exception as e:  # pragma: no cover
                caught["result"] = f"other:{type(e).__name__}"

        with l2.grounding_forbidden():
            t = threading.Thread(target=worker)
            t.start()
            t.join()
        self.assertEqual("raised", caught.get("result"))


class TestMeterAndCopy(unittest.TestCase):
    def test_meter_stays_zero_across_guarded_block(self):
        with l2.grounding_forbidden():
            # Attempting a grounded call raises (so it never counts); the meter
            # must therefore be 0 on exit.
            try:
                story_leads._gemini("x", grounded=True)
            except l2.GroundingForbiddenError:
                pass
        meter = l2.check_zero_grounding()
        self.assertEqual(0, meter["requests"])
        self.assertEqual(0, meter["queries"])

    def test_refusal_copy_exact(self):
        r = l2._refusal([{"id": 3, "name": "Nice Old Town"},
                         {"id": 9, "name": "MFA Boston"}])
        self.assertFalse(r["allowed"])
        self.assertEqual("by_reference_no_material", r["error_code"])
        self.assertEqual(
            "This place hasn't been researched yet on the free level.",
            r["message"])
        # Suggestion names up to 3 nearby tours as "<name> (#<id>)".
        self.assertIn("Buy a $10 pack for a freshly researched tour, or pick one "
                      "of these nearby tours:", r["suggestion"])
        self.assertIn("Nice Old Town (#3)", r["suggestion"])
        self.assertIn("MFA Boston (#9)", r["suggestion"])
        self.assertEqual(2, len(r["nearby_tours"]))

    def test_refusal_copy_no_nearby(self):
        r = l2._refusal([])
        self.assertEqual("Buy a $10 pack for a freshly researched tour.",
                         r["suggestion"])
        self.assertEqual([], r["nearby_tours"])

    def test_refusal_caps_at_three_nearby(self):
        many = [{"id": i, "name": f"Tour {i}"} for i in range(10)]
        r = l2._refusal(many)
        self.assertEqual(3, len(r["nearby_tours"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
