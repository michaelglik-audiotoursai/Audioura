#!/usr/bin/env python3
"""test_local447_db_first_and_wayback.py — LOCAL-447 acceptance tests.

LOCAL-448 update: Wayback tests removed (Defect 3 — Wayback removed from chain).
DB-first tests updated to use production DB connection pattern (Defect 2).

LOCAL-450 update: DB-first → DB-fallback. Tests now verify DB serves content when
live fails (cold host), not before live runs. Assertions encoding the old ordering
are updated; no tests are deleted.

Tests:
  1. DB fallback serves content from stop_corpus when live is cold (zero network).
  2. The DB fallback goes RED when neutralised to a no-op (D242 standing check 1).
  3. Live wins when Wikimedia is healthy (not DB).
  4. Backwards compatibility: fetch_wikipedia_summary returns a plain string.
  5. Wayback is NOT called from the chain (LOCAL-448, Defect 3).
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


class TestDBFallbackPath(unittest.TestCase):
    """Tests for the DB-fallback (stop_corpus) lookup in fetch_wikipedia_summary.

    LOCAL-450: DB is no longer first — it is consulted when live yields nothing.
    These tests verify the DB path serves content when live fails (cold host,
    timeout, network error). The assertions that encoded "DB before network"
    are updated to encode "DB when network fails".
    """

    def test_db_fallback_serves_known_title_when_cold(self):
        """Cold branch serves 'Île Sainte-Marguerite' from stop_corpus with zero network calls."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

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
                    "Network call made! Cold branch with DB fallback should have served this."
                )
                result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

        self.assertIsInstance(result, dict)
        self.assertEqual(result['source'], 'stop_corpus')
        self.assertFalse(result['is_from_archive'])
        self.assertIn('Sainte-Marguerite', result['text'])
        self.assertGreater(len(result['text']), 100)

        dead_host_breaker.reset_cold_hosts()

    def test_db_fallback_accent_folded_match_when_cold(self):
        """DB fallback matches accent-folded titles when live is cold (D243)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

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
                mock_get.side_effect = AssertionError("Network call — cold branch should use DB")
                # Try without accents — should still match via folding
                result = fetch_wikipedia_summary_with_provenance('Ile Sainte-Marguerite')

        self.assertIsInstance(result, dict)
        self.assertEqual(result['source'], 'stop_corpus')
        self.assertGreater(len(result.get('text', '')), 50)

        dead_host_breaker.reset_cold_hosts()

    def test_db_fallback_goes_red_when_neutralised(self):
        """D242 standing check: test FAILS if _fetch_from_stop_corpus is a no-op.

        LOCAL-450: With cold host, the DB fallback is the only path that serves
        content. Neutralising it → the cold branch returns {} instead of content.
        """
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

        # Neutralise the DB fallback path
        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get') as mock_get:
                mock_get.side_effect = AssertionError("Network call in cold branch!")
                result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

        # With DB neutralised + cold host, we get {} — proof the DB fallback
        # is what would have served content
        self.assertEqual(result, {},
                         "Expected {} when DB fallback is neutralised and host is cold — "
                         "test cannot distinguish working from broken")

        dead_host_breaker.reset_cold_hosts()

    def test_live_wins_when_wikimedia_healthy(self):
        """When Wikimedia is healthy, live content is served (not DB).

        LOCAL-450: This is the core design assertion — live first, DB only as fallback.
        """
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'extract': 'Rich live content from Wikipedia about the island ' * 10}

        with patch('rag_retriever.requests.get', return_value=mock_resp):
            with patch('rag_retriever._fetch_from_stop_corpus') as mock_db:
                result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

        # DB fallback should NOT have been consulted
        mock_db.assert_not_called()
        self.assertEqual(result['source'], 'wikipedia_live')
        self.assertIn('Rich live content', result['text'])

        dead_host_breaker.reset_cold_hosts()

    def test_backwards_compat_returns_string(self):
        """fetch_wikipedia_summary() returns a plain string (not dict)."""
        from rag_retriever import fetch_wikipedia_summary
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()

        # With live healthy, we get live content as a string
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'extract': 'The island of Sainte-Marguerite content about the island ' * 3}

        with patch('rag_retriever.requests.get', return_value=mock_resp):
            result = fetch_wikipedia_summary('Île Sainte-Marguerite')

        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 50)

        dead_host_breaker.reset_cold_hosts()


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
        """LOCAL-448/449: Wayback NOT invoked even when Wikimedia is cold.
        LOCAL-449: Cold means STOP — no action API either, returns {}."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('dead_host_breaker.is_host_cold', return_value=True):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    with patch('rag_retriever._fetch_via_action_api') as mock_action:
                        result = fetch_wikipedia_summary_with_provenance('Some Artist')

        mock_wb.assert_not_called()
        # LOCAL-449: Cold means stop — no action API, returns empty
        mock_action.assert_not_called()
        self.assertEqual(result, {})

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
    """Integration test — requires live DB connection.
    
    LOCAL-450: renamed from "DB-first" but tests the same underlying DB read.
    The integration test now exercises the fallback path (cold → DB serves).
    """

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

    def test_live_db_fallback_serves_when_cold(self):
        """Live integration: DB fallback serves stop_corpus content when host is cold.
        
        LOCAL-450: This is the acceptance criterion — a live run showing the DB
        fallback path serving a summary when the cold branch is taken.
        """
        try:
            from db_connection import check_db_available
            if not check_db_available():
                self.skipTest("Database not available")
        except Exception:
            self.skipTest("Cannot check DB availability")

        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker
        dead_host_breaker.reset_cold_hosts()
        dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')

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

        # Fetch with network blocked — cold branch should consult DB
        with patch('rag_retriever.requests.get') as mock_get:
            mock_get.side_effect = AssertionError(
                f"Network call for '{title}' — cold branch should use DB fallback!"
            )
            result = fetch_wikipedia_summary_with_provenance(title)

        self.assertEqual(result['source'], 'stop_corpus',
                         f"Expected stop_corpus source for '{title}', got '{result.get('source')}'")
        self.assertGreater(len(result.get('text', '')), 20,
                           f"Expected substantial text for '{title}'")
        print(f"\n  ✓ DB-fallback served '{title}' ({len(result['text'])} chars, 0 network calls)")

        dead_host_breaker.reset_cold_hosts()


if __name__ == '__main__':
    unittest.main(verbosity=2)
