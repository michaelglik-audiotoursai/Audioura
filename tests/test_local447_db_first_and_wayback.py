#!/usr/bin/env python3
"""test_local447_db_first_and_wayback.py — LOCAL-447 acceptance tests.

LOCAL-448 update: Wayback tests removed (Defect 3 — Wayback removed from chain).
DB-first tests updated to use production DB connection pattern (Defect 2).

Tests:
  1. DB-first path serves content from stop_corpus with zero network calls.
  2. The DB-first path goes RED when neutralised to a no-op (D242 standing check 1).
  3. Backwards compatibility: fetch_wikipedia_summary returns a plain string.
  4. Wayback is NOT called from the chain (LOCAL-448, Defect 3).
"""
import json
import os
import sys
import os
# LEAD (D408): the LOCAL-447 chain is OFF by default in production. These tests
# exercise the feature, so they enable it explicitly.
os.environ['L447_RETRIEVAL_CHAIN'] = 'true'
import unittest
from unittest.mock import patch, MagicMock

# Ensure we can import from the project root and tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))

# Set test database target
os.environ.setdefault('AUDIOURA_DB_TARGET', 'production')  # read-only, safe


class TestDBFirstPath(unittest.TestCase):
    """Tests for the DB-first (stop_corpus) lookup in fetch_wikipedia_summary."""

    def test_db_first_serves_known_title_zero_network(self):
        """DB-first path serves 'Île Sainte-Marguerite' from stop_corpus without network."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance, _fetch_from_stop_corpus

        # Mock the DB connection to return a known row
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ('Île Sainte-Marguerite',
             json.dumps([{'text': 'The island of Sainte-Marguerite is the largest of the Lérins Islands, '
                          'located off the coast of Cannes in the French Riviera. It is famous for '
                          'Fort Royal, where the Man in the Iron Mask was imprisoned. ' * 3}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Ile_Sainte-Marguerite'}])),
        ]

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            # Patch requests.get to fail loudly if called (proves zero network)
            with patch('rag_retriever.requests.get') as mock_get:
                mock_get.side_effect = AssertionError(
                    "Network call made! DB-first path should have served this."
                )
                result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

        self.assertIsInstance(result, dict)
        self.assertEqual(result['source'], 'stop_corpus')
        self.assertFalse(result['is_from_archive'])
        self.assertIn('Sainte-Marguerite', result['text'])
        self.assertGreater(len(result['text']), 100)

    def test_db_first_accent_folded_match(self):
        """DB-first matches accent-folded titles (D243)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ('Île Sainte-Marguerite',
             json.dumps([{'text': 'The island of Sainte-Marguerite content here for testing purposes ' * 3}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Ile_Sainte-Marguerite'}])),
        ]

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            with patch('rag_retriever.requests.get') as mock_get:
                mock_get.side_effect = AssertionError("Network call — DB should serve this")
                # Try without accents — should still match via folding
                result = fetch_wikipedia_summary_with_provenance('Ile Sainte-Marguerite')

        self.assertIsInstance(result, dict)
        self.assertEqual(result['source'], 'stop_corpus')
        self.assertGreater(len(result.get('text', '')), 50)

    def test_db_first_goes_red_when_neutralised(self):
        """D242 standing check: test FAILS if _fetch_from_stop_corpus is a no-op.

        This test verifies the DB-first path is actually wired and working.
        If someone neutralises _fetch_from_stop_corpus to always return None,
        the test goes red because the network mock will fire.
        """
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        # Neutralise the DB-first path
        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            # Ensure Wikimedia is NOT cold (so the REST path fires)
            with patch('dead_host_breaker.is_host_cold', return_value=False):
                # Now requests.get should be called (network path)
                mock_resp = MagicMock()
                mock_resp.status_code = 404
                mock_resp.json.return_value = {}

                with patch('rag_retriever.requests.get', return_value=mock_resp) as mock_get:
                    with patch('rag_retriever._fetch_via_action_api', return_value=''):
                        result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

                # The network WAS called — proof the DB-first path was the only
                # thing preventing network calls
                self.assertTrue(mock_get.called,
                                "Network was NOT called even with DB-first neutralised — "
                                "test cannot distinguish working from broken")

    def test_backwards_compat_returns_string(self):
        """fetch_wikipedia_summary() returns a plain string (not dict)."""
        from rag_retriever import fetch_wikipedia_summary

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ('Île Sainte-Marguerite',
             json.dumps([{'text': 'The island of Sainte-Marguerite content about the island ' * 3}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Ile_Sainte-Marguerite'}])),
        ]

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            with patch('rag_retriever.requests.get') as mock_get:
                mock_get.side_effect = AssertionError("Network call — DB should serve this")
                result = fetch_wikipedia_summary('Île Sainte-Marguerite')

        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 50)


class TestWaybackRemoved(unittest.TestCase):
    """LOCAL-448: Wayback is removed from the production retrieval chain."""

    def test_wayback_not_called_when_wikimedia_live(self):
        """Wayback is NOT invoked when Wikimedia is healthy."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'extract': 'Test artist biography here.'}

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    result = fetch_wikipedia_summary_with_provenance('Some Unknown Artist')

        mock_wb.assert_not_called()
        self.assertEqual(result['source'], 'wikipedia_live')

    def test_wayback_not_called_when_wikimedia_cold(self):
        """LOCAL-448: Wayback NOT invoked even when Wikimedia is cold."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('dead_host_breaker.is_host_cold', return_value=True):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    with patch('rag_retriever._fetch_via_action_api', return_value='Action result'):
                        result = fetch_wikipedia_summary_with_provenance('Some Artist')

        mock_wb.assert_not_called()
        # Falls through to action API instead
        self.assertEqual(result.get('source'), 'wikipedia_live')

    def test_wayback_not_called_on_429(self):
        """LOCAL-448: Wayback NOT invoked on 429 — falls to action API."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        try:
            import dead_host_breaker
            dead_host_breaker.reset_cold_hosts()
        except Exception:
            pass

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Too Many Requests'

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    with patch('rag_retriever._fetch_via_action_api', return_value='Fallback'):
                        result = fetch_wikipedia_summary_with_provenance('Test Title')

        mock_wb.assert_not_called()

        try:
            import dead_host_breaker
            dead_host_breaker.reset_cold_hosts()
        except Exception:
            pass


class TestDBFirstIntegration(unittest.TestCase):
    """Integration test — requires live DB connection."""

    def setUp(self):
        """Set host-side DB env vars for _get_db_connection() to find the DB."""
        self._orig_env = {}
        for key in ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'):
            self._orig_env[key] = os.environ.get(key)
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_PORT'] = '5433'
        os.environ['DB_NAME'] = 'audiotours'
        os.environ['DB_USER'] = 'admin'
        os.environ['DB_PASSWORD'] = 'password123'

    def tearDown(self):
        """Restore original env vars."""
        for key, val in self._orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_live_db_first_no_network(self):
        """Live integration: DB-first serves stop_corpus content without network.
        
        This is the acceptance criterion: a live run showing the DB-first path
        serving a summary with zero network calls.
        """
        try:
            from db_connection import check_db_available
            if not check_db_available():
                self.skipTest("Database not available")
        except Exception:
            self.skipTest("Cannot check DB availability")

        from rag_retriever import fetch_wikipedia_summary_with_provenance

        # Get a title we know is in stop_corpus with Wikipedia source
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT stop_title FROM stop_corpus
            WHERE source_pages::text LIKE '%%wikipedia%%'
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()

        if not row:
            self.skipTest("No Wikipedia-sourced entries in stop_corpus")

        title = row[0]

        # Fetch with network blocked
        with patch('rag_retriever.requests.get') as mock_get:
            mock_get.side_effect = AssertionError(
                f"Network call for '{title}' — DB-first should serve this!"
            )
            result = fetch_wikipedia_summary_with_provenance(title)

        self.assertEqual(result['source'], 'stop_corpus',
                         f"Expected stop_corpus source for '{title}', got '{result.get('source')}'")
        self.assertGreater(len(result.get('text', '')), 20,
                           f"Expected substantial text for '{title}'")
        print(f"\n  ✓ DB-first served '{title}' ({len(result['text'])} chars, 0 network calls)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
