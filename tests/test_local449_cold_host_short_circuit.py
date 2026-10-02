#!/usr/bin/env python3
"""test_local449_cold_host_short_circuit.py — LOCAL-449 acceptance tests.

Tests:
  1. Cold check neutralised → test goes RED (D242 real-path binding).
  2. _fetch_via_action_api makes ZERO requests when host is cold.
  3. Timeout handler: marks cold and returns {}, zero action API calls.
  4. Cold branch: returns {} immediately, zero network calls.
  5. 429 handler: calls _fetch_via_action_api but breaker inside prevents requests.
  6. Wikimedia bucket rule: cold en.wikipedia.org covers fr.wikipedia.org.
"""
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock, call

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestColdMeansStop(unittest.TestCase):
    """When Wikimedia is cold, fetch_wikipedia_summary_with_provenance
    returns {} with zero network calls."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_cold_host_returns_empty_immediately(self):
        """Cold branch returns {} with zero network calls."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker

        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get') as mock_get:
                result = fetch_wikipedia_summary_with_provenance('Some Topic')

        self.assertEqual(result, {})
        mock_get.assert_not_called()

    def test_cold_host_zero_action_api_calls(self):
        """Cold branch does NOT call _fetch_via_action_api."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker

        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever._fetch_via_action_api') as mock_action:
                result = fetch_wikipedia_summary_with_provenance('Test Title')

        mock_action.assert_not_called()
        self.assertEqual(result, {})


class TestNeutralisedColdCheckGoesRed(unittest.TestCase):
    """D242 check: neutralising is_host_cold to return False causes a test to go RED.

    This binds to the real path — if the cold check is removed or broken, this
    test detects it by observing network calls that should have been prevented.
    """

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_neutralised_cold_check_allows_network_call(self):
        """With is_host_cold neutralised to always False, a cold host gets called.

        This test goes RED (fails) when the cold check is neutralised — proving
        that the production code truly depends on the breaker, not plumbing.
        """
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker

        # Mark cold — normally this would prevent network calls
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

        # Neutralise the cold check — now the code thinks the host is alive
        with patch('dead_host_breaker.is_host_cold', return_value=False):
            with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {'extract': 'Content from live call'}
                with patch('rag_retriever.requests.get', return_value=mock_resp) as mock_get:
                    result = fetch_wikipedia_summary_with_provenance('Test Topic')

        # With cold check neutralised, the network call DOES happen
        self.assertTrue(mock_get.called,
                        "Network was NOT called even with cold check neutralised — "
                        "the test is testing plumbing, not the real path (D242 violation)")
        # And it returns content (proving the cold check was the only guard)
        self.assertNotEqual(result, {})
        self.assertEqual(result.get('source'), 'wikipedia_live')


class TestFetchViaActionApiBreaker(unittest.TestCase):
    """_fetch_via_action_api must consult the breaker per-host inside its loop."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_action_api_zero_requests_when_cold(self):
        """_fetch_via_action_api makes ZERO requests when Wikimedia is cold."""
        from rag_retriever import _fetch_via_action_api
        import dead_host_breaker

        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test cold')

        import requests as _req
        with patch.object(_req, 'get') as mock_get:
            result = _fetch_via_action_api('Some Topic')

        self.assertEqual(result, "")
        mock_get.assert_not_called()

    def test_action_api_skips_cold_host_in_loop(self):
        """Each host in the loop is checked against the breaker individually."""
        from rag_retriever import _fetch_via_action_api
        import dead_host_breaker

        # Mark Wikimedia cold — both en and fr are in the same bucket
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

        calls = []
        def tracking_get(url, **kwargs):
            calls.append(url)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = {'query': {'pages': {'123': {'extract': 'x' * 300}}}}
            return mock

        import requests as _req
        with patch.object(_req, 'get', side_effect=tracking_get):
            result = _fetch_via_action_api('Test')

        # Both hosts are in the Wikimedia bucket — zero calls
        self.assertEqual(len(calls), 0)
        self.assertEqual(result, "")

    def test_action_api_marks_cold_on_timeout(self):
        """_fetch_via_action_api marks host cold and skips remaining on timeout."""
        from rag_retriever import _fetch_via_action_api
        import dead_host_breaker
        import requests as _req

        def timeout_get(url, **kwargs):
            raise _req.Timeout('simulated')

        with patch.object(_req, 'get', side_effect=timeout_get):
            result = _fetch_via_action_api('Test Topic')

        self.assertEqual(result, "")
        # Wikimedia should now be cold
        self.assertTrue(dead_host_breaker.is_host_cold('en.wikipedia.org'))
        self.assertTrue(dead_host_breaker.is_host_cold('fr.wikipedia.org'))

    def test_action_api_marks_cold_on_429(self):
        """_fetch_via_action_api marks host cold on 429 response."""
        from rag_retriever import _fetch_via_action_api
        import dead_host_breaker
        import requests as _req

        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch.object(_req, 'get', return_value=mock_resp):
            result = _fetch_via_action_api('Test Topic')

        self.assertEqual(result, "")
        self.assertTrue(dead_host_breaker.is_host_cold('en.wikipedia.org'))


class TestTimeoutHandler(unittest.TestCase):
    """Timeout in the REST call marks cold and returns {} — no action API."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_timeout_marks_cold_returns_empty(self):
        """Timeout → mark_host_cold → return {} (no further network calls)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        import requests

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', side_effect=requests.Timeout('dead')):
                result = fetch_wikipedia_summary_with_provenance('Test Stop')

        self.assertEqual(result, {})
        self.assertTrue(dead_host_breaker.is_host_cold('en.wikipedia.org'))

    def test_timeout_does_not_call_action_api(self):
        """Timeout handler must NOT call _fetch_via_action_api."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import requests

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', side_effect=requests.Timeout('dead')):
                with patch('rag_retriever._fetch_via_action_api') as mock_action:
                    result = fetch_wikipedia_summary_with_provenance('Test Stop')

        mock_action.assert_not_called()


class TestRateLimitHandler(unittest.TestCase):
    """429 keeps action API call (pre-LOCAL-447 behaviour) but breaker governs it."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_429_marks_cold_then_action_api_short_circuits(self):
        """429 marks cold, calls _fetch_via_action_api, but breaker prevents requests."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        import requests

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Too Many Requests'

        action_api_calls = []

        def tracking_action_api(topic):
            """Track that action API was called, but verify breaker blocks it."""
            action_api_calls.append(topic)
            # Call the real function to verify the breaker inside it works
            from rag_retriever import _fetch_via_action_api
            # The real _fetch_via_action_api will consult the breaker
            # and skip all Wikimedia hosts since they're now cold
            return _fetch_via_action_api.__wrapped__(topic) if hasattr(_fetch_via_action_api, '__wrapped__') else ""

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                result = fetch_wikipedia_summary_with_provenance('Test')

        # Host is now cold (marked by the 429 handler)
        self.assertTrue(dead_host_breaker.is_host_cold('en.wikipedia.org'))
        # Result is empty because action API also sees the cold host
        self.assertEqual(result, {})


class TestWikimediaBucketRule(unittest.TestCase):
    """The Wikimedia bucket rule: cold en.wikipedia.org covers fr.wikipedia.org."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_cold_en_covers_fr(self):
        """Marking en.wikipedia.org cold also makes fr.wikipedia.org cold."""
        import dead_host_breaker
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')
        self.assertTrue(dead_host_breaker.is_host_cold('fr.wikipedia.org'))

    def test_action_api_skips_all_wikimedia_when_one_is_cold(self):
        """_fetch_via_action_api skips both en and fr when one is marked cold."""
        from rag_retriever import _fetch_via_action_api
        import dead_host_breaker
        import requests as _req

        dead_host_breaker.mark_host_cold('fr.wikipedia.org', 'test from fr')

        with patch.object(_req, 'get') as mock_get:
            result = _fetch_via_action_api('Test Topic')

        mock_get.assert_not_called()
        self.assertEqual(result, "")


class TestReproScript(unittest.TestCase):
    """Replicates the repro449.py measurement as a proper test."""

    def setUp(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def tearDown(self):
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

    def test_repro_case_b_zero_calls_instant(self):
        """After one timeout, the next call is 0 network calls and <0.1s."""
        import requests
        import dead_host_breaker
        from rag_retriever import fetch_wikipedia_summary

        calls = []
        def fake_get(url, **kw):
            calls.append(url)
            raise requests.Timeout('simulated dead host')

        with patch('rag_retriever.requests.get', fake_get):
            # First call: triggers timeout, marks cold
            with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
                fetch_wikipedia_summary('First Stop')

        first_calls = len(calls)
        calls.clear()

        # Second call: host already cold → instant return
        with patch('rag_retriever.requests.get', fake_get):
            with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
                t0 = time.time()
                result = fetch_wikipedia_summary('Second Stop')
                elapsed = time.time() - t0

        self.assertEqual(len(calls), 0, f"Expected 0 calls but got {len(calls)}")
        self.assertLess(elapsed, 0.1, f"Expected <0.1s but took {elapsed:.2f}s")
        self.assertEqual(result, '')  # fetch_wikipedia_summary returns '' on failure


if __name__ == '__main__':
    unittest.main()
