#!/usr/bin/env python3
"""test_local448_db_first_correctness.py — LOCAL-448 acceptance tests.

Tests:
  1. The three LEAD examples that proved wrong-corpus serving all return None.
  2. Neutralising _fetch_from_stop_corpus goes RED (D242 standing check).
  3. DB-first still serves exact accent-folded matches correctly.
  4. DB import failure logs at WARNING (not silent).
  5. Wayback is NOT called from the production retrieval chain.
"""
import json
import os
import sys
import logging
import unittest
from unittest.mock import patch, MagicMock

# Enable the LOCAL-447 chain for testing
os.environ['L447_RETRIEVAL_CHAIN'] = 'true'

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))

# Set test database target
os.environ.setdefault('AUDIOURA_DB_TARGET', 'production')  # read-only, safe


class TestDefect1WrongCorpusRejection(unittest.TestCase):
    """Defect 1: The containment match served the WRONG stop's corpus.

    These three examples from LEAD's live run must all return None.
    They previously matched via substring containment:
      - "The Dream" substring of "The Dream of Saint Ursula by Carpaccio"
      - "Adam and Eve" substring of "Adam and Eve by Albrecht Durer"
      - "Le Panier" substring of "Le Panier district of Marseille"
    """

    def _make_corpus_rows(self):
        """Build mock stop_corpus rows that demonstrate the wrong-match pattern."""
        return [
            # "The Dream" is a short title in stop_corpus for a DIFFERENT stop
            ('The Dream', json.dumps([{'text': 'Musée international d\'Art naïf Anatole Jakovsky content that is about a completely different museum ' * 5}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/The_Dream'}])),
            # "Adam and Eve" is a short title for DIFFERENT content
            ('Adam and Eve', json.dumps([{'text': 'A list of unrelated Adam-and-Eve paintings from various museums ' * 30}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Adam_and_Eve'}])),
            # "Le Panier" is a short title for DIFFERENT content
            ('Le Panier', json.dumps([{'text': 'Hôtel-Dieu and La Vieille Charité passages about a different district ' * 8}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Le_Panier'}])),
            # "Raquel" and "Fenocchio" — other short titles
            ('Raquel', json.dumps([{'text': 'Content about Raquel restaurant ' * 10}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Raquel'}])),
            ('Fenocchio', json.dumps([{'text': 'Content about Fenocchio ice cream ' * 10}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Fenocchio'}])),
        ]

    def _patch_db_and_call(self, topic):
        """Call _fetch_from_stop_corpus with mocked DB returning our test rows."""
        from rag_retriever import _fetch_from_stop_corpus

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = self._make_corpus_rows()

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            result = _fetch_from_stop_corpus(topic)
        return result

    def test_dream_of_saint_ursula_returns_none(self):
        """'The Dream of Saint Ursula by Carpaccio' must NOT match 'The Dream'."""
        result = self._patch_db_and_call("The Dream of Saint Ursula by Carpaccio")
        self.assertIsNone(result,
                          "DEFECT 1: 'The Dream of Saint Ursula by Carpaccio' incorrectly "
                          "matched 'The Dream' via substring containment")

    def test_adam_and_eve_by_durer_returns_none(self):
        """'Adam and Eve by Albrecht Durer' must NOT match 'Adam and Eve'."""
        result = self._patch_db_and_call("Adam and Eve by Albrecht Durer")
        self.assertIsNone(result,
                          "DEFECT 1: 'Adam and Eve by Albrecht Durer' incorrectly "
                          "matched 'Adam and Eve' via substring containment")

    def test_le_panier_district_of_marseille_returns_none(self):
        """'Le Panier district of Marseille' must NOT match 'Le Panier'."""
        result = self._patch_db_and_call("Le Panier district of Marseille")
        self.assertIsNone(result,
                          "DEFECT 1: 'Le Panier district of Marseille' incorrectly "
                          "matched 'Le Panier' via substring containment")

    def test_exact_match_still_works(self):
        """Exact match 'Le Panier' → 'Le Panier' must still serve content."""
        result = self._patch_db_and_call("Le Panier")
        self.assertIsNotNone(result,
                             "Exact match 'Le Panier' should serve content")

    def test_exact_match_adam_and_eve(self):
        """Exact match 'Adam and Eve' → 'Adam and Eve' must still serve content."""
        result = self._patch_db_and_call("Adam and Eve")
        self.assertIsNotNone(result,
                             "Exact match 'Adam and Eve' should serve content")

    def test_accent_folded_exact_match(self):
        """Accent-folded exact match still works: 'Île X' matches 'Ile X'."""
        rows = [
            ('Île Sainte-Marguerite',
             json.dumps([{'text': 'The island of Sainte-Marguerite is located off the coast of Cannes in the south of France ' * 3}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Ile_Sainte-Marguerite'}])),
        ]
        from rag_retriever import _fetch_from_stop_corpus
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = rows

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            # Query without accents should match via folding
            result = _fetch_from_stop_corpus("Ile Sainte-Marguerite")
        self.assertIsNotNone(result, "Accent-folded exact match should work")
        self.assertIn("Sainte-Marguerite", result)


class TestDefect1NeutralisedGoesRed(unittest.TestCase):
    """D242 standing check: test goes RED when _fetch_from_stop_corpus is neutralised.

    Unlike the Wayback tests (which patched the very function they tested),
    this test exercises the REAL DB code path. It mocks the DB connection to
    provide controlled data, then verifies the matching logic actually runs.
    """

    def test_neutralised_db_first_causes_network_call(self):
        """When _fetch_from_stop_corpus is a no-op, the network path fires."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        # Neutralise DB-first
        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            # Mock network to prove it gets called
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'extract': 'Fallback content from network.'}
            with patch('rag_retriever.requests.get', return_value=mock_resp) as mock_get:
                result = fetch_wikipedia_summary_with_provenance('Some Known Title')
            self.assertTrue(mock_get.called,
                            "Network was NOT called with DB-first neutralised — "
                            "cannot distinguish working from broken")

    def test_real_matching_logic_runs(self):
        """The matching logic inside _fetch_from_stop_corpus actually executes.

        If the function is neutralised to `return None`, this test fails because
        it verifies the cursor.execute was called (real code path runs).
        """
        from rag_retriever import _fetch_from_stop_corpus

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ('Test Title',
             json.dumps([{'text': 'Meaningful passage content about the test title ' * 3}]),
             json.dumps([{'type': 'wikipedia', 'url': 'https://en.wikipedia.org/wiki/Test'}])),
        ]

        with patch('rag_retriever._get_db_connection', return_value=mock_conn):
            result = _fetch_from_stop_corpus('Test Title')

        # The cursor.execute MUST have been called (real code path ran)
        mock_cursor.execute.assert_called_once()
        # And it should have returned content for the exact match
        self.assertIsNotNone(result, "Exact match should return content")
        self.assertIn("test title", result.lower())


class TestDefect2LoudImportFailure(unittest.TestCase):
    """Defect 2: DB import failure must be LOUD (logged at WARNING), not silent."""

    def test_db_connection_failure_logs_warning(self):
        """When DB connection fails, a WARNING is logged (not swallowed)."""
        from rag_retriever import _fetch_from_stop_corpus

        with patch('rag_retriever._get_db_connection',
                   side_effect=Exception("Connection refused")):
            with self.assertLogs('rag_retriever', level='WARNING') as cm:
                result = _fetch_from_stop_corpus('Any Topic')

        self.assertIsNone(result)
        # Verify the warning mentions the connection failure
        warning_text = '\n'.join(cm.output)
        self.assertIn('cannot connect', warning_text.lower())

    def test_no_tests_import_in_production_code(self):
        """Production code must NOT import from tests/ directory."""
        import inspect
        from rag_retriever import _fetch_from_stop_corpus

        source = inspect.getsource(_fetch_from_stop_corpus)
        self.assertNotIn("from db_connection import", source,
                         "_fetch_from_stop_corpus still imports from tests/db_connection")
        self.assertNotIn("sys.path.insert", source,
                         "_fetch_from_stop_corpus still manipulates sys.path to find tests/")


class TestDefect3WaybackRemoved(unittest.TestCase):
    """Defect 3: Wayback is NOT called from the production retrieval chain."""

    def test_wayback_never_called_when_wikimedia_cold(self):
        """Even when Wikimedia is cold, Wayback is NOT invoked."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('dead_host_breaker.is_host_cold', return_value=True):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    with patch('rag_retriever._fetch_via_action_api') as mock_action:
                        result = fetch_wikipedia_summary_with_provenance('Some Topic')

        mock_wb.assert_not_called()
        # LOCAL-449: Cold means STOP — no action API call, returns empty dict
        mock_action.assert_not_called()
        self.assertEqual(result, {})

    def test_wayback_never_called_on_429(self):
        """On 429, the chain falls to action API, NOT Wayback."""
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
                    with patch('rag_retriever._fetch_via_action_api', return_value='Action result'):
                        result = fetch_wikipedia_summary_with_provenance('Test')

        mock_wb.assert_not_called()

    def test_wayback_never_called_on_timeout(self):
        """On timeout, the chain marks cold and returns {} — NOT Wayback, NOT action API."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance
        try:
            import dead_host_breaker
            dead_host_breaker.reset_cold_hosts()
        except Exception:
            pass

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', side_effect=__import__('requests').Timeout):
                with patch('rag_retriever._fetch_from_wayback_wikipedia') as mock_wb:
                    with patch('rag_retriever._fetch_via_action_api') as mock_action:
                        result = fetch_wikipedia_summary_with_provenance('Test Topic')

        mock_wb.assert_not_called()
        # LOCAL-449: timeout marks cold and returns {} — no action API call
        mock_action.assert_not_called()
        self.assertEqual(result, {})

    def test_no_archive_source_in_chain(self):
        """The production chain never returns source='wayback_archive'."""
        from rag_retriever import fetch_wikipedia_summary_with_provenance

        # Test with a successful Wikipedia response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'extract': 'Normal Wikipedia content.'}

        with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
            with patch('rag_retriever.requests.get', return_value=mock_resp):
                result = fetch_wikipedia_summary_with_provenance('Test')

        self.assertNotEqual(result.get('source'), 'wayback_archive')
        self.assertFalse(result.get('is_from_archive', False))


class TestDBFirstIntegration(unittest.TestCase):
    """Integration test — requires live DB connection."""

    def setUp(self):
        """Set host-side DB env vars for _get_db_connection() to find the DB."""
        # On the host, the DB is at localhost:5433 (docker-compose-master.yml maps it).
        # Inside containers, DATABASE_URL is set. This setUp ensures host tests work.
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

    def test_live_db_first_exact_match(self):
        """Live integration: DB-first serves an exact title match."""
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))
            from db_connection import check_db_available
            if not check_db_available():
                self.skipTest("Database not available")
        except Exception:
            self.skipTest("Cannot check DB availability")

        from rag_retriever import _fetch_from_stop_corpus

        # Get a title we know is in stop_corpus with Wikipedia source
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT stop_title FROM stop_corpus
            WHERE source_pages::text LIKE '%%wikipedia%%'
              AND passages_json IS NOT NULL
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()

        if not row:
            self.skipTest("No Wikipedia-sourced entries in stop_corpus")

        title = row[0]
        result = _fetch_from_stop_corpus(title)
        self.assertIsNotNone(result, f"Exact match for '{title}' should return content")
        self.assertGreater(len(result), 20)
        print(f"\n  ✓ DB-first served '{title}' ({len(result)} chars) via exact match")

    def test_live_lead_examples_return_none(self):
        """Live: LEAD's three failure examples return None from _fetch_from_stop_corpus."""
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))
            from db_connection import check_db_available
            if not check_db_available():
                self.skipTest("Database not available")
        except Exception:
            self.skipTest("Cannot check DB availability")

        from rag_retriever import _fetch_from_stop_corpus

        # These three topics must NOT match any short title in stop_corpus
        lead_examples = [
            "The Dream of Saint Ursula by Carpaccio",
            "Adam and Eve by Albrecht Durer",
            "Le Panier district of Marseille",
        ]

        for topic in lead_examples:
            result = _fetch_from_stop_corpus(topic)
            self.assertIsNone(result,
                              f"LEAD example '{topic}' must return None, got content")
            print(f"  ✓ '{topic}' → None (correct)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
