"""LOCAL-427: Test persistent retry, backoff, and per-host page cache.

Tests bind directly to module-scope symbols (D242 #1) — no mirrors,
no `inspect.getsource` assertions.
"""
import time
import unittest
from unittest.mock import patch, MagicMock

# Import module-scope symbols directly
from exhibition_checklist import (
    _fetch_page,
    _cache_get,
    _cache_put,
    clear_page_cache,
    get_page_cache_stats,
    _polite_wait,
    _record_request,
    FETCH_RETRY_BUDGET_SECONDS,
    FETCH_INITIAL_BACKOFF_SECONDS,
    FETCH_MAX_BACKOFF_SECONDS,
    FETCH_JITTER_FRACTION,
    FETCH_POLITE_DELAY_SECONDS,
    PAGE_CACHE_TTL_SECONDS,
    _PAGE_CACHE,
    _HOST_LAST_REQUEST,
)


class TestPageCache(unittest.TestCase):
    """Test per-host page cache operations."""

    def setUp(self):
        clear_page_cache()

    def tearDown(self):
        clear_page_cache()

    def test_cache_roundtrip(self):
        """Stored value is retrievable."""
        _cache_put('https://mfa.org/exhibitions/unbound', 'page text here', [('link', '/foo')])
        result = _cache_get('https://mfa.org/exhibitions/unbound')
        self.assertIsNotNone(result)
        text, links = result
        self.assertEqual(text, 'page text here')
        self.assertEqual(links, [('link', '/foo')])

    def test_cache_miss(self):
        """Unknown URL returns None."""
        self.assertIsNone(_cache_get('https://unknown.org/page'))

    def test_cache_empty_stored(self):
        """Empty string (429 failure) is cached and returned as ('', [])."""
        _cache_put('https://mfa.org/blocked', '', [])
        result = _cache_get('https://mfa.org/blocked')
        self.assertIsNotNone(result)
        text, links = result
        self.assertEqual(text, '')
        self.assertEqual(links, [])

    def test_cache_stats(self):
        """Stats report entry count and URLs."""
        _cache_put('https://a.org/p1', 'a', [])
        _cache_put('https://b.org/p2', 'b', [])
        stats = get_page_cache_stats()
        self.assertEqual(stats['entries'], 2)
        self.assertIn('https://a.org/p1', stats['urls'])

    def test_clear_cache(self):
        """clear_page_cache empties the cache."""
        _cache_put('https://x.org/y', 'data', [])
        clear_page_cache()
        self.assertIsNone(_cache_get('https://x.org/y'))


class TestFetchPageRetry(unittest.TestCase):
    """Test _fetch_page retry behaviour with mocked HTTP."""

    def setUp(self):
        clear_page_cache()

    def tearDown(self):
        clear_page_cache()

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 5.0)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_success_on_first_try(self, mock_get):
        """200 on first attempt returns page text."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html><p>Exhibition works: Le Lézard aux plumes d\'or</p></html>'
        mock_get.return_value = mock_resp

        text, links = _fetch_page('https://mfa.org/exhibition/unbound')
        self.assertIn('Le Lézard', text)
        self.assertEqual(mock_get.call_count, 1)

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 10.0)
    @patch('exhibition_checklist.FETCH_INITIAL_BACKOFF_SECONDS', 0.01)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_429_then_success(self, mock_get):
        """429 followed by 200 on retry succeeds."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = '<html><p>The exhibition page content</p></html>'

        mock_get.side_effect = [mock_429, mock_200]

        text, links = _fetch_page('https://mfa.org/exhibition/unbound')
        self.assertIn('exhibition page content', text)
        self.assertEqual(mock_get.call_count, 2)

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 3.0)
    @patch('exhibition_checklist.FETCH_INITIAL_BACKOFF_SECONDS', 0.01)
    @patch('exhibition_checklist.FETCH_MAX_BACKOFF_SECONDS', 0.05)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_persistent_429_exhausts_budget(self, mock_get):
        """Persistent 429 exhausts the time budget and returns empty."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {}
        mock_get.return_value = mock_429

        start = time.monotonic()
        text, links = _fetch_page('https://mfa.org/blocked')
        elapsed = time.monotonic() - start

        self.assertEqual(text, '')
        self.assertEqual(links, [])
        # Should have tried multiple times (min wait is 0.5s, budget is 3s)
        self.assertGreater(mock_get.call_count, 1)
        # Total elapsed should be within budget + overhead
        self.assertLess(elapsed, 5.0)  # generous bound

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 10.0)
    @patch('exhibition_checklist.FETCH_INITIAL_BACKOFF_SECONDS', 0.01)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_retry_after_header_honoured(self, mock_get):
        """Retry-After header value is used as the wait time."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {'Retry-After': '0.05'}

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = '<html><p>Success after waiting</p></html>'

        mock_get.side_effect = [mock_429, mock_200]

        text, links = _fetch_page('https://mfa.org/retry-after-test')
        self.assertIn('Success after waiting', text)

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_404_not_retried(self, mock_get):
        """404 is not retried — it's a genuine absence."""
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_get.return_value = mock_404

        text, links = _fetch_page('https://mfa.org/does-not-exist')
        self.assertEqual(text, '')
        self.assertEqual(mock_get.call_count, 1)

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_cache_hit_skips_fetch(self, mock_get):
        """Cached result is returned without making any HTTP request."""
        # Pre-populate cache
        _cache_put('https://mfa.org/cached', 'cached content', [('link', '/x')])

        text, links = _fetch_page('https://mfa.org/cached')
        self.assertEqual(text, 'cached content')
        self.assertEqual(links, [('link', '/x')])
        # No HTTP request should be made
        mock_get.assert_not_called()

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 5.0)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_successful_fetch_cached(self, mock_get):
        """Successful fetch result is cached for subsequent calls."""
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.text = '<html><p>This is the exhibition page content with enough characters to pass the length filter</p></html>'
        mock_get.return_value = mock_200

        # First call fetches
        _fetch_page('https://mfa.org/cache-test')
        self.assertEqual(mock_get.call_count, 1)

        # Second call hits cache
        text, links = _fetch_page('https://mfa.org/cache-test')
        self.assertIn('exhibition page content', text)
        self.assertEqual(mock_get.call_count, 1)  # Still just 1

    @patch('exhibition_checklist.requests.get')
    @patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 0.5)
    @patch('exhibition_checklist.FETCH_INITIAL_BACKOFF_SECONDS', 0.01)
    @patch('exhibition_checklist.FETCH_POLITE_DELAY_SECONDS', 0.0)
    def test_failed_fetch_cached_as_empty(self, mock_get):
        """429 that exhausts budget is cached as empty (prevents re-fetch)."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {}
        mock_get.return_value = mock_429

        _fetch_page('https://mfa.org/rate-limited')
        call_count_first = mock_get.call_count

        # Second call should hit cache — no new requests
        text, links = _fetch_page('https://mfa.org/rate-limited')
        self.assertEqual(text, '')
        self.assertEqual(mock_get.call_count, call_count_first)


class TestPoliteDelay(unittest.TestCase):
    """Test per-host polite delay."""

    def test_polite_wait_enforces_gap(self):
        """Polite wait enforces minimum gap between requests to same host."""
        import exhibition_checklist
        # Save and override
        original = exhibition_checklist.FETCH_POLITE_DELAY_SECONDS
        exhibition_checklist.FETCH_POLITE_DELAY_SECONDS = 0.1

        try:
            _record_request('test-host.org')
            start = time.monotonic()
            _polite_wait('test-host.org')
            elapsed = time.monotonic() - start
            # Should have waited approximately 0.1s
            self.assertGreater(elapsed, 0.05)
        finally:
            exhibition_checklist.FETCH_POLITE_DELAY_SECONDS = original


class TestConfigAtModuleScope(unittest.TestCase):
    """Verify retry/cache config is at module scope and directly importable."""

    def test_retry_budget_default(self):
        self.assertEqual(FETCH_RETRY_BUDGET_SECONDS, 30.0)

    def test_initial_backoff_default(self):
        self.assertEqual(FETCH_INITIAL_BACKOFF_SECONDS, 2.0)

    def test_max_backoff_default(self):
        self.assertEqual(FETCH_MAX_BACKOFF_SECONDS, 15.0)

    def test_jitter_fraction_default(self):
        self.assertEqual(FETCH_JITTER_FRACTION, 0.3)

    def test_polite_delay_default(self):
        self.assertEqual(FETCH_POLITE_DELAY_SECONDS, 1.5)

    def test_cache_ttl_default(self):
        self.assertEqual(PAGE_CACHE_TTL_SECONDS, 3600.0)


class TestVerifyStopClaimsWithVenueSource(unittest.TestCase):
    """Test that verify_stop_claims uses venue page text as a snippet."""

    def test_venue_text_corroborates_claim(self):
        """A claim present in venue page text is marked SOURCED."""
        from generate_tour_text import verify_stop_claims

        story = (
            "The book was published by Louis Broder, who was renowned for his "
            "commitment to the livre d'artiste."
        )
        # Snippet from venue page that contains the claim
        snippets = [{
            'title': 'Venue Exhibition Page — Le Lézard',
            'snippet': (
                "Le Lézard aux plumes d'or is a livre d'artiste published by "
                "Louis Broder. The printing was handled by Mourlot Frères. "
                "Gift of Boris Fridman."
            ),
            'url': 'https://mfa.org/exhibition/unbound',
        }]

        result = verify_stop_claims(
            story_text=story,
            snippets=snippets,
            credit_line='Published by Louis Broder. Printed by Mourlot Frères. Gift of Boris Fridman.',
            stop_name='Le Lézard aux plumes d\'or',
        )
        # With the venue text as a snippet, "Louis Broder" claim should be sourced
        self.assertGreater(result['claims_sourced'], 0)


if __name__ == '__main__':
    unittest.main()
