#!/usr/bin/env python3
"""test_local591_verdict_equals_reasoning.py — LOCAL-591 Fix #3.

Field defect (tours 395/396), the exact log line:

    OK 'King's Chapel' — inside 'Boston Athenaeum, Boston, Massachusetts':
       King's Chapel is located outside the bounds of Boston Athenaeum,
       Boston, Massachusetts. (conf=high)

The containment judge returned {"inside_scope": true, ...} with a REASON that
says the stop is OUTSIDE. The code trusted the boolean and recorded a stop as
inside that its own reasoning placed outside.

The fix: the verdict IS its reasoning. _reconcile_scope_verdict() flips a
boolean that contradicts its reason toward NOT inside — a reasoning text that
says "outside" can never be recorded as inside.

Deterministic and offline — no network, no LLM.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt


# The EXACT reason text from the tour-395 log.
KINGS_CHAPEL_REASON = (
    "King's Chapel is located outside the bounds of Boston Athenaeum, "
    "Boston, Massachusetts."
)


class TestReconcileVerdict(unittest.TestCase):

    def test_helper_exists(self):
        self.assertTrue(hasattr(gtt, "_reconcile_scope_verdict"))

    def test_exact_kings_chapel_line_is_not_inside(self):
        """inside_scope=true + a reason saying 'outside' → NOT inside."""
        reconciled = gtt._reconcile_scope_verdict(True, KINGS_CHAPEL_REASON)
        self.assertFalse(
            reconciled,
            "a reason that says 'located outside the bounds' can never be recorded as inside")

    def test_plain_outside_variants_flip_to_false(self):
        for reason in [
            "This is outside the venue.",
            "The site is not inside the building.",
            "It is located elsewhere, in a different building.",
            "Not within the bounds of the museum.",
        ]:
            self.assertFalse(gtt._reconcile_scope_verdict(True, reason),
                             f"reason {reason!r} says outside — must not be inside")

    def test_genuine_inside_reason_stays_inside(self):
        for reason in [
            "The reading room is inside the Athenaeum.",
            "This gallery is part of the building.",
            "Housed within the main hall.",
            "",  # empty reason — do not invent a contradiction
        ]:
            self.assertTrue(gtt._reconcile_scope_verdict(True, reason),
                            f"reason {reason!r} does not say outside — keep the inside verdict")

    def test_false_verdict_is_left_false(self):
        # A removal verdict is never weakened by this reconciliation.
        self.assertFalse(gtt._reconcile_scope_verdict(False, "clearly outside"))
        self.assertFalse(gtt._reconcile_scope_verdict(False, "inside the building"))


class TestCheckOneAppliesReconciliation(unittest.TestCase):
    """The real _validate_stops_within_scope path reconciles the verdict.

    We drive _check_one through _validate_stops_within_scope with a stubbed HTTP
    layer that returns the exact King's Chapel contradiction, and assert the stop
    is REMOVED (verdict reconciled to outside, high confidence → removal), not
    kept as "inside".
    """

    def test_kings_chapel_contradiction_removes_the_stop(self):
        import json as _json

        # A stop name NOT in scope-memory, so ONLY the reconciled judge verdict
        # can remove it. (King's Chapel itself is already recorded in
        # known_out_of_scope.json from the field run, which would remove it
        # deterministically before the judge — that would pass this test for the
        # wrong reason. The exact King's Chapel reason text is still asserted by
        # test_exact_kings_chapel_line_is_not_inside above.)
        _novel_stop = "Zzyzx Reading Room Annexe 2591"
        _reason = (f"{_novel_stop} is located outside the bounds of Boston "
                   f"Athenaeum, Boston, Massachusetts.")

        class _Resp:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": _json.dumps({
                    "inside_scope": True,                      # the backwards boolean
                    "confidence": "high",
                    "reason": _reason,                         # the reason says outside
                })}}]}

        import requests as _rq
        _orig_post = _rq.post
        # Isolate the judge: no scope-memory shortcut, no scope-memory WRITE (we
        # must not pollute known_out_of_scope.json from a test), and treat the
        # name as a real place so only the reconciled verdict decides.
        import scope_memory as _sm
        import place_shape as _ps
        _o_known, _o_record = _sm.known_out_of_scope, _sm.record_out_of_scope
        _o_classify = _ps.classify_stop_name
        try:
            _rq.post = lambda *a, **k: _Resp()
            _sm.known_out_of_scope = lambda n, s: (False, "")
            _sm.record_out_of_scope = lambda *a, **k: (False, None)
            _ps.classify_stop_name = lambda n: {"is_place": True, "shape": "place", "reason": ""}
            poi_list = [
                {"name": "Boston Athenaeum"},                  # stop 0 (protected)
                {"name": _novel_stop},                         # the contradiction
            ]
            kept = gtt._validate_stops_within_scope(
                poi_list, "Boston Athenaeum, Boston, Massachusetts",
                headers={"Authorization": "Bearer test"})
        finally:
            _rq.post = _orig_post
            _sm.known_out_of_scope, _sm.record_out_of_scope = _o_known, _o_record
            _ps.classify_stop_name = _o_classify

        kept_names = [p["name"] for p in kept]
        self.assertIn("Boston Athenaeum", kept_names, "stop 0 is protected")
        self.assertNotIn(
            _novel_stop, kept_names,
            "a stop whose reason says it is OUTSIDE must be removed, never recorded as inside")


if __name__ == "__main__":
    unittest.main(verbosity=2)
