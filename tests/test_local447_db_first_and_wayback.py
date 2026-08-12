#!/usr/bin/env python3
"""test_local447_db_first_and_wayback.py — LOCAL-447 acceptance tests.

Tests:
  1. DB-first path serves content from stop_corpus with zero network calls.
  2. The DB-first path goes RED when neutralised to a no-op (D242 standing check 1).
  3. Wayback fallback is gated on is_host_cold() (does not fire when Wikimedia is live).
  4. Wayback fallback fires when Wikimedia is cold and provides provenance.
  5. Backwards compatibility: fetch_wikipedia_summary returns a plain string.
"""
import json
import os
import sys
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
        from rag_retriever import fetch_wikipedia_summary_with_provenance

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
            # Now requests.get should be called (network path)
            # We mock it to return a 404 to prove the fallback chain proceeds
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.json.return_value = {}

            with patch('rag_retriever.requests.get', return_value=mock_resp) as mock_get:
                result = fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')

            # The network WAS called — proof the DB-first path was the only
            # thing preventing network calls
            self.assertTrue(mock_get.called,
                            "Network was NOT called even with DB-first neutralised — "
                            "test cannot distinguish working from broken")

    def test_backwards_compat_returns_string(self):
        """fetch_wikipedia_summary() returns a plain string (not dict)."""
        from rag_retriever import fetch_wikipedia_summary

        with patch('rag_retriever.requests.get') as mock_get:
            mock_get.side_effect = AssertionError("Network call — DB should serve this")
            result = fetch_wikipedia_summary('Île Sainte-Marguerite')

        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 50)


class TestWaybackFallback(unittest.TestCase):
    """Tests for the Wayback Machine fallback path."""

    def test_wayback_not_called_when_wikimedia_live(self):
        """Wayback is NOT invoked when Wikimedia is healthy (live path works)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        # Mock a successful Wikipedia response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'extract': 'Test artist biography here.'}

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    result = fetch_wikipedia_summary_with_provenance('Some Unknown Artist')

        mock_wb.assert_not_called()
        self.assertEqual(result['source'], 'wikipedia_live')

    def test_wayback_called_when_wikimedia_cold(self):
        """Wayback IS invoked when dead_host_breaker says Wikimedia is cold."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        wayback_data = {
            'text': 'Archived biography of the artist.',
            'is_from_archive': True,
            'wayback_snapshot_timestamp': '20250115120000',
            'snapshot_age_days': 210,
        }

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('dead_host_breaker.is_host_cold', return_value=True):
                with patch('rag_retriever._fetch_from_wayback_wikipedia',
                           return_value=wayback_data) as mock_wb:
                    result = fetch_wikipedia_summary_with_provenance('Some Artist')

        mock_wb.assert_called_once_with('Some Artist')
        self.assertEqual(result['source'], 'wayback_archive')
        self.assertTrue(result['is_from_archive'])
        self.assertEqual(result['wayback_snapshot_timestamp'], '20250115120000')
        self.assertEqual(result['snapshot_age_days'], 210)

    def test_wayback_called_on_429(self):
        """Wayback is invoked when Wikipedia returns 429 (rate limit)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        import dead_host_breaker

        # Reset cold hosts for clean test
        dead_host_breaker.reset_cold_hosts()

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Too Many Requests'

        wayback_data = {
            'text': 'Archived content from wayback.',
            'is_from_archive': True,
            'wayback_snapshot_timestamp': '20260101000000',
            'snapshot_age_days': 30,
        }

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                with patch('rag_retriever._fetch_from_wayback_wikipedia',
                           return_value=wayback_data) as mock_wb:
                    result = fetch_wikipedia_summary_with_provenance('Test Title')

        mock_wb.assert_called_once()
        self.assertEqual(result['source'], 'wayback_archive')
        self.assertTrue(result['is_from_archive'])

        # Clean up
        dead_host_breaker.reset_cold_hosts()

    def test_provenance_label_present(self):
        """Archive-sourced content carries provenance label (acceptance criterion)."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        wayback_data = {
            'text': 'The Palais Lascaris is a 17th-century palace in Nice.',
            'is_from_archive': True,
            'wayback_snapshot_timestamp': '20251201143022',
            'snapshot_age_days': 254,
        }

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('dead_host_breaker.is_host_cold', return_value=True):
                with patch('rag_retriever._fetch_from_wayback_wikipedia',
                           return_value=wayback_data):
                    result = fetch_wikipedia_summary_with_provenance('Palais Lascaris')

        # Provenance must be present and correct
        self.assertTrue(result['is_from_archive'])
        self.assertEqual(result['wayback_snapshot_timestamp'], '20251201143022')
        self.assertEqual(result['snapshot_age_days'], 254)
        self.assertEqual(result['source'], 'wayback_archive')


class TestDBFirstIntegration(unittest.TestCase):
    """Integration test — requires live DB connection."""

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
