#!/usr/bin/env python3
"""test_local580_actionable_failure.py — Deliverable 4 (LOCAL-580).

When a tour truly cannot be built, the job error must be ACTIONABLE: a stable
error_code, a plain-language message, and a machine-usable suggestion object
derived from the venue's resolved locality — while the old human string stays
in `error` for pre-LOCAL-581 app builds.

Run: python3 -m pytest test_local580_actionable_failure.py -q
"""
import unittest

from actionable_failure import build_actionable_failure, derive_locality, ERROR_CODES


class TestDeriveLocality(unittest.TestCase):
    def test_us_city_state_from_request_with_venue_prefix(self):
        self.assertEqual(
            'Winchester, MA',
            derive_locality('Griffin museum of photography, Winchester, MA'))

    def test_strips_stop_count_and_tour_words(self):
        self.assertEqual(
            'Winchester, MA',
            derive_locality('Griffin Museum of Photography, Winchester, MA, museum, 5 stops'))

    def test_non_us_locality(self):
        self.assertEqual('Nice, France',
                         derive_locality('Palais Lascaris, Nice, France'))

    def test_evidence_locality_wins(self):
        self.assertEqual(
            'Winchester, MA',
            derive_locality('anything at all', {'locality': 'Winchester, MA'}))

    def test_no_locality_returns_empty(self):
        self.assertEqual('', derive_locality('Griffin Museum of Photography'))


class TestBuildActionableFailure(unittest.TestCase):
    def test_griffin_thin_evidence_is_actionable(self):
        evidence = {
            'error_type': 'thin_evidence',
            'venue': 'Griffin Museum of Photography',
            'locality': 'Winchester, MA',
            'sparql_works': 0,
        }
        legacy = ('We could not find enough verified material about '
                  '"Griffin Museum of Photography" to build a tour.')
        out = build_actionable_failure(evidence, 'Griffin Museum of Photography, Winchester, MA', legacy)

        self.assertEqual('venue_no_verifiable_content', out['error_code'])
        self.assertEqual(legacy, out['error'])        # old builds unchanged
        self.assertEqual(legacy, out['message'])
        self.assertEqual(
            {'label': 'Walking tour of Winchester, MA',
             'request': 'walking tour of Winchester, MA',
             'tour_type': 'walking'},
            out['suggestion'])

    def test_suggestion_derived_from_request_when_evidence_lacks_locality(self):
        out = build_actionable_failure(
            {'error_type': 'thin_evidence', 'venue': 'Griffin Museum of Photography'},
            'Griffin museum of photography, Winchester, MA',
            'legacy string')
        self.assertEqual('walking tour of Winchester, MA', out['suggestion']['request'])
        self.assertEqual('walking', out['suggestion']['tour_type'])

    def test_no_locality_yields_no_suggestion_but_still_coded(self):
        out = build_actionable_failure(
            {'error_type': 'thin_evidence', 'venue': 'Some Museum'},
            'Some Museum', 'legacy')
        self.assertEqual('venue_no_verifiable_content', out['error_code'])
        self.assertIsNone(out['suggestion'])

    def test_unknown_error_type_maps_to_generation_failed(self):
        out = build_actionable_failure({'error_type': 'something_new'}, 'X', 'legacy')
        self.assertEqual('generation_failed', out['error_code'])
        self.assertIsNone(out['suggestion'])

    def test_empty_evidence_does_not_crash(self):
        out = build_actionable_failure(None, 'X, Boston, MA', 'legacy')
        self.assertEqual('generation_failed', out['error_code'])
        self.assertEqual('legacy', out['error'])

    def test_error_code_table_is_stable(self):
        # The documented contract LOCAL-581 consumes.
        self.assertEqual('venue_no_verifiable_content', ERROR_CODES['thin_evidence'])
        self.assertEqual('exhibition_not_found', ERROR_CODES['exhibition_not_found'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
