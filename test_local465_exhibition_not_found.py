#!/usr/bin/env python3
"""test_local465_exhibition_not_found.py — Unit tests for exhibition_resolution.py.

Tests all four verdicts (FOUND, NOT_FOUND city mismatch, NOT_FOUND zero coverage,
DID_YOU_MEAN) plus false-positive regression for ordinary input.

Run: python -m pytest test_local465_exhibition_not_found.py -v
"""
import os
import sys
import unittest

# Ensure repo root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exhibition_resolution import (
    resolve_request,
    ExhibitionNotFound,
    is_strict_mode,
    _extract_city_from_request,
    _extract_exhibition_term,
    _find_near_matches,
    _token_set_similarity,
)


class TestResolveRequest(unittest.TestCase):
    """Core decision function tests — all four verdicts."""

    # ─── FIXTURE DATA ─────────────────────────────────────────────────────

    def _mfa_boston_resolved(self):
        """A correctly resolved MFA Boston venue."""
        return {
            'name': 'Museum of Fine Arts, Boston',
            'qid': 'Q49133',
            'official_url': 'https://www.mfa.org/',
            'city': 'Boston',
        }

    def _mfa_houston_resolved(self):
        """MFA Houston — wrong venue when user asked for Boston."""
        return {
            'name': 'Museum of Fine Arts, Houston',
            'qid': 'Q1565911',
            'official_url': 'http://www.mfah.org/',
            'city': 'Houston',
        }

    def _full_coverage(self):
        """Coverage dict showing all stops COVERED."""
        return {
            'covered_count': 5,
            'total_selected': 5,
            'verdicts': {
                'Stop A': 'COVERED',
                'Stop B': 'COVERED',
                'Stop C': 'COVERED',
                'Stop D': 'COVERED',
                'Stop E': 'COVERED',
            },
            'fallback_reasons': [],
        }

    def _zero_coverage(self):
        """Coverage dict with 0 COVERED — all EMPTY or VENUE_ONLY."""
        return {
            'covered_count': 0,
            'total_selected': 3,
            'verdicts': {
                'Stop A': 'VENUE_ONLY',
                'Stop B': 'EMPTY',
                'Stop C': 'EMPTY',
            },
            'fallback_reasons': ['1×VENUE_ONLY', '2×EMPTY'],
        }

    def _unbound_candidates(self):
        """Real exhibition titles at MFA Boston (as the venue_corpus would have them)."""
        return [
            {'title': 'Picasso, Miró, Dalí: Unbound'},
            {'title': 'Women Take the Floor'},
            {'title': 'Monet and Boston: Lasting Impression'},
        ]

    # ─── VERDICT: NOT_FOUND — city mismatch ──────────────────────────────

    def test_city_mismatch_rejects(self):
        """The D523 bug: request says Boston, resolver returned Houston."""
        result = resolve_request(
            request='exhibition blue green and silva in MFA Boston, MA',
            resolved_venue=self._mfa_houston_resolved(),
            coverage=self._zero_coverage(),
            candidates=[],
        )
        self.assertEqual(result['verdict'], 'NOT_FOUND')
        self.assertIn('city mismatch', result['reason'])
        self.assertIn('Boston', result['user_message'])
        self.assertIn('Houston', result['user_message'])

    def test_city_mismatch_case_insensitive(self):
        """City comparison should be case-insensitive."""
        result = resolve_request(
            request='exhibition at museum, boston, ma',
            resolved_venue={
                'name': 'Some Museum, Houston',
                'qid': 'Q1',
                'official_url': '',
                'city': 'houston',
            },
            coverage=self._full_coverage(),
            candidates=[],
        )
        self.assertEqual(result['verdict'], 'NOT_FOUND')

    # ─── VERDICT: NOT_FOUND — zero coverage ──────────────────────────────

    def test_zero_coverage_rejects(self):
        """All candidates EMPTY/VENUE_ONLY with no near-matches → NOT_FOUND."""
        result = resolve_request(
            request='exhibition blue green and silva in MFA Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._zero_coverage(),
            candidates=[],  # No known titles to suggest
        )
        self.assertEqual(result['verdict'], 'NOT_FOUND')
        self.assertIn('zero coverage', result['reason'])
        self.assertEqual(result['suggestions'], [])

    # ─── VERDICT: DID_YOU_MEAN ────────────────────────────────────────────

    def test_did_you_mean_with_near_match(self):
        """Zero coverage BUT a near-match exists → DID_YOU_MEAN."""
        # "Picasso Miro Dali Unbound" misspelled slightly
        result = resolve_request(
            request='Picaso Miro Dali Unbound exhibition at MFA, Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._zero_coverage(),
            candidates=self._unbound_candidates(),
        )
        self.assertEqual(result['verdict'], 'DID_YOU_MEAN')
        self.assertTrue(len(result['suggestions']) > 0)
        # The real title should be the first suggestion
        self.assertIn('Unbound', result['suggestions'][0])

    def test_did_you_mean_bad_match_returns_not_found(self):
        """'blue green and silva' vs 'Picasso, Miró, Dalí: Unbound' → no suggestion."""
        result = resolve_request(
            request='exhibition blue green and silva in MFA Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._zero_coverage(),
            candidates=self._unbound_candidates(),
        )
        # "blue green and silva" has zero token overlap with any candidate
        # → should be NOT_FOUND, not DID_YOU_MEAN with a bad suggestion
        self.assertEqual(result['verdict'], 'NOT_FOUND')
        self.assertEqual(result['suggestions'], [])

    # ─── VERDICT: FOUND ───────────────────────────────────────────────────

    def test_found_with_full_coverage(self):
        """Real exhibition with good coverage → FOUND."""
        result = resolve_request(
            request='Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._full_coverage(),
            candidates=self._unbound_candidates(),
        )
        self.assertEqual(result['verdict'], 'FOUND')
        self.assertEqual(result['suggestions'], [])

    def test_found_when_coverage_partial(self):
        """Some COVERED candidates are enough — FOUND."""
        coverage = {
            'covered_count': 3,
            'total_selected': 5,
            'verdicts': {
                'A': 'COVERED', 'B': 'COVERED', 'C': 'COVERED',
                'D': 'EMPTY', 'E': 'VENUE_ONLY',
            },
            'fallback_reasons': ['1×VENUE_ONLY', '1×EMPTY'],
        }
        result = resolve_request(
            request='Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=coverage,
            candidates=self._unbound_candidates(),
        )
        self.assertEqual(result['verdict'], 'FOUND')

    # ─── FALSE-POSITIVE REGRESSION (D316 lesson) ─────────────────────────

    def test_ordinary_museum_tour_passes(self):
        """A general museum tour request must not be rejected.
        
        D316's standing lesson: 'France', 'The Treat Page' and 'visual tapestry'
        were each shipped as false positives. General requests must pass.
        """
        result = resolve_request(
            request='Museum of Fine Arts, Boston, MA',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._full_coverage(),
            candidates=[],
        )
        self.assertEqual(result['verdict'], 'FOUND')

    def test_city_same_as_resolved_passes(self):
        """When cities match, no rejection even with zero coverage."""
        # Zero coverage with matching city → zero coverage kicks in, not city mismatch
        result = resolve_request(
            request='some obscure show at MFA, Boston',
            resolved_venue=self._mfa_boston_resolved(),
            coverage=self._zero_coverage(),
            candidates=[],
        )
        # Should be NOT_FOUND via zero coverage, not city mismatch
        self.assertEqual(result['verdict'], 'NOT_FOUND')
        self.assertIn('zero coverage', result['reason'])

    def test_no_city_in_request_passes(self):
        """No city token in request → cannot mismatch → FOUND if covered."""
        result = resolve_request(
            request='Impressionist paintings at the museum',
            resolved_venue=self._mfa_houston_resolved(),
            coverage=self._full_coverage(),
            candidates=[],
        )
        self.assertEqual(result['verdict'], 'FOUND')

    def test_walking_tour_france_not_rejected(self):
        """'walking tour France' — D316 false positive regression."""
        result = resolve_request(
            request='walking tour of Nice, France',
            resolved_venue={
                'name': 'Musée Matisse, Nice',
                'qid': 'Q3329265',
                'official_url': 'https://www.musee-matisse-nice.org/',
                'city': 'Nice',
            },
            coverage=self._full_coverage(),
            candidates=[],
        )
        self.assertEqual(result['verdict'], 'FOUND')


class TestExhibitionStrictEnvVar(unittest.TestCase):
    """Test the EXHIBITION_STRICT=0 bypass."""

    def test_default_is_strict(self):
        """Default (no env var) means strict mode ON."""
        os.environ.pop('EXHIBITION_STRICT', None)
        self.assertTrue(is_strict_mode())

    def test_strict_1_is_on(self):
        os.environ['EXHIBITION_STRICT'] = '1'
        self.assertTrue(is_strict_mode())
        del os.environ['EXHIBITION_STRICT']

    def test_strict_0_disables(self):
        os.environ['EXHIBITION_STRICT'] = '0'
        self.assertFalse(is_strict_mode())
        del os.environ['EXHIBITION_STRICT']


class TestCityExtraction(unittest.TestCase):
    """Test _extract_city_from_request."""

    def test_boston_ma(self):
        city = _extract_city_from_request('exhibition blue green and silva in MFA Boston, MA')
        self.assertEqual(city, 'Boston')

    def test_nice_france(self):
        city = _extract_city_from_request('Matisse museum tour, Nice, France')
        self.assertEqual(city, 'Nice')

    def test_no_city(self):
        city = _extract_city_from_request('Impressionist paintings at the museum')
        self.assertEqual(city, '')

    def test_in_pattern(self):
        city = _extract_city_from_request('art exhibition in Chicago')
        self.assertEqual(city, 'Chicago')


class TestExhibitionTermExtraction(unittest.TestCase):
    """Test _extract_exhibition_term."""

    def test_strips_venue(self):
        term = _extract_exhibition_term('exhibition blue green and silva in MFA Boston, MA')
        self.assertEqual(term, 'blue green and silva')

    def test_preserves_colon_format(self):
        term = _extract_exhibition_term('Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA')
        self.assertEqual(term, 'Picasso, Miro, Dali: Unbound')

    def test_bare_name(self):
        term = _extract_exhibition_term('Women Take the Floor')
        self.assertEqual(term, 'Women Take the Floor')


class TestNearMatchSearch(unittest.TestCase):
    """Test near-match and similarity functions."""

    def test_exact_match_scores_high(self):
        sim = _token_set_similarity(
            'Picasso Miro Dali Unbound',
            'Picasso, Miró, Dalí: Unbound'
        )
        self.assertGreater(sim, 0.5)

    def test_unrelated_scores_low(self):
        sim = _token_set_similarity(
            'blue green and silva',
            'Picasso, Miró, Dalí: Unbound'
        )
        self.assertLess(sim, 0.30)

    def test_find_near_matches_returns_best(self):
        titles = [
            'Picasso, Miró, Dalí: Unbound',
            'Women Take the Floor',
            'Monet and Boston: Lasting Impression',
        ]
        matches = _find_near_matches('Picaso Miro Dali Unbound', titles)
        self.assertTrue(len(matches) > 0)
        self.assertIn('Unbound', matches[0])

    def test_find_near_matches_empty_for_garbage(self):
        titles = [
            'Picasso, Miró, Dalí: Unbound',
            'Women Take the Floor',
        ]
        matches = _find_near_matches('blue green and silva', titles)
        self.assertEqual(matches, [])


class TestExhibitionNotFoundExc(unittest.TestCase):
    """Test the typed exception."""

    def test_exception_carries_fields(self):
        exc = ExhibitionNotFound(
            verdict='NOT_FOUND',
            reason='test reason',
            user_message='test message',
            suggestions=['Suggestion A'],
        )
        self.assertEqual(exc.verdict, 'NOT_FOUND')
        self.assertEqual(exc.reason, 'test reason')
        self.assertEqual(exc.user_message, 'test message')
        self.assertEqual(exc.suggestions, ['Suggestion A'])
        self.assertEqual(str(exc), 'test message')

    def test_exception_is_catchable(self):
        with self.assertRaises(ExhibitionNotFound):
            raise ExhibitionNotFound(
                verdict='DID_YOU_MEAN',
                reason='near-match',
                user_message='Did you mean X?',
                suggestions=['X'],
            )


if __name__ == '__main__':
    unittest.main()
