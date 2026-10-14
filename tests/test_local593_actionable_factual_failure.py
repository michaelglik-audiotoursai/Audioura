#!/usr/bin/env python3
"""test_local593_actionable_factual_failure.py — Deliverable 5 (LOCAL-593).

The factual-integrity rejection path (generate_tour_text_service.py) used to
set the job error to:

    "Tour failed factual integrity check (N factual failures). Please try again."

That is not actionable: it names an internal check, and retrying the identical
request produces the identical rejection. This deliverable routes the branch
through the LOCAL-580 contract so the job carries:

    error_code  == 'factual_integrity'   (stable enum the app branches on)
    message     — plain language, naming the venue, no mention of an internal
                  check, no "try again"
    suggestion  — a ready-to-fire smaller same-venue request the LOCAL-581
                  "Edit request" button can pre-fill

RED on 0315513:
  * ERROR_CODES has no 'factual_integrity' entry
  * the service source still contains the bare "Please try again." string
GREEN after fix: both hold.

Run: python3 -m pytest tests/test_local593_actionable_factual_failure.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actionable_failure import build_actionable_failure, ERROR_CODES


class TestFactualIntegrityContract(unittest.TestCase):
    def test_error_code_registered(self):
        self.assertIn('factual_integrity', ERROR_CODES)
        self.assertEqual('factual_integrity', ERROR_CODES['factual_integrity'])

    def test_harvard_fewer_stops_suggestion(self):
        """7-stop request → a smaller same-venue request (halved, floor, min 3)."""
        out = build_actionable_failure(
            {'error_type': 'factual_integrity', 'venue': 'Harvard Art Museums'},
            'Harvard Art Museums, Cambridge, MA, museum, 7 stops',
            'We couldn\u2019t verify enough facts about Harvard Art Museums to narrate it safely.')
        self.assertEqual('factual_integrity', out['error_code'])
        self.assertIsNotNone(out['suggestion'])
        self.assertEqual('museum', out['suggestion']['tour_type'])
        # The pre-fill request must be complete and have fewer stops than 7.
        _m = re.search(r'(\d+)\s*stops?', out['suggestion']['request'])
        self.assertIsNotNone(_m)
        self.assertLess(int(_m.group(1)), 7)
        self.assertIn('Harvard Art Museums', out['suggestion']['request'])

    def test_message_is_not_internal(self):
        """The message must not mention the internal check or 'try again'."""
        out = build_actionable_failure(
            {'error_type': 'factual_integrity', 'venue': 'Harvard Art Museums'},
            'Harvard Art Museums, Cambridge, MA, museum, 7 stops',
            'We couldn\u2019t verify enough facts about Harvard Art Museums to narrate it safely. '
            'Try the museum\u2019s full official name, or fewer stops.')
        low = out['message'].lower()
        self.assertNotIn('factual integrity check', low)
        self.assertNotIn('try again', low)
        self.assertNotIn('failures)', low)
        self.assertIn('harvard art museums', low)

    def test_suggestion_request_is_resubmittable(self):
        """The suggestion.request is what 'Edit request' pre-fills — it must be a
        non-empty, complete request string (not a fragment)."""
        out = build_actionable_failure(
            {'error_type': 'factual_integrity', 'venue': 'Harvard Art Museums'},
            'Harvard Art Museums, Cambridge, MA, museum, 7 stops', 'msg')
        req = out['suggestion']['request']
        self.assertTrue(req and len(req) > len('Harvard Art Museums'))
        self.assertIn('Cambridge', req)

    def test_no_stop_count_still_actionable(self):
        """A request without a stop count still yields an actionable suggestion."""
        out = build_actionable_failure(
            {'error_type': 'factual_integrity', 'venue': 'Harvard Art Museums'},
            'Harvard Art Museums, Cambridge, MA', 'msg')
        self.assertEqual('factual_integrity', out['error_code'])
        self.assertIsNotNone(out['suggestion'])


class TestServiceWiring(unittest.TestCase):
    """Prove the branch is actually wired, not just the pure module."""

    @classmethod
    def setUpClass(cls):
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, 'generate_tour_text_service.py'),
                  encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_bare_try_again_string_removed(self):
        self.assertNotIn(
            'Tour failed factual integrity check', self.src,
            "the non-actionable factual-integrity string must be gone")

    def test_branch_builds_actionable_failure(self):
        # The factual branch now imports and calls the LOCAL-580 builder.
        self.assertIn("'error_type': 'factual_integrity'", self.src)
        self.assertIn('build_actionable_failure', self.src)

    def test_error_code_attached_to_job(self):
        self.assertIn('_fi_extra["error_code"]', self.src)
        self.assertIn('_fi_extra["suggestion"]', self.src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
