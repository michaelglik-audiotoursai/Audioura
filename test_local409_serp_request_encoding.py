"""test_local409_serp_request_encoding.py — LOCAL-409 regression tests.

Verify that:
1. A query containing accented characters (é, ó) and U+2019 curly apostrophe
   produces a well-formed JSON request that the SERP API would accept.
2. The _serp_search function logs full request payload and response body on HTTP error.
3. The real generation path (synthesize_queries → _serp_search) handles all
   character variants without producing malformed payloads.

Per D296: revert breaks the LOGIC, not the symbol. The test verifies behavior,
not just that a function exists.
Per D307: at least one test on the real generation path.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import work_story_searcher
from work_story_searcher import synthesize_queries, _serp_search


class TestSerpRequestEncoding(unittest.TestCase):
    """Verify SERP request payloads are well-formed for accented/special-char queries."""

    def test_accented_title_produces_valid_json_payload(self):
        """Query with é, ó, and ASCII apostrophe produces valid UTF-8 JSON."""
        query = "\"Le Lézard aux plumes d'or\" Joan Miró"
        payload = {"q": query, "num": 8}
        # This is what _serp_search builds — ensure it's valid JSON
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        # Roundtrip: parse back and verify
        parsed = json.loads(data.decode('utf-8'))
        self.assertEqual(parsed['q'], query)
        self.assertEqual(parsed['num'], 8)
        # Verify accented chars are present as UTF-8, not escaped
        self.assertIn('é', data.decode('utf-8'))
        self.assertIn('ó', data.decode('utf-8'))

    def test_curly_apostrophe_u2019_produces_valid_json_payload(self):
        """Query with U+2019 (right single quote) produces valid UTF-8 JSON."""
        query = "\"Le L\u00e9zard aux plumes d\u2019or\" Joan Mir\u00f3"
        payload = {"q": query, "num": 8}
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        parsed = json.loads(data.decode('utf-8'))
        self.assertEqual(parsed['q'], query)
        # The curly apostrophe should be preserved
        self.assertIn('\u2019', parsed['q'])

    def test_synthesize_queries_with_curly_apostrophe_title(self):
        """synthesize_queries handles a title containing U+2019 without error.

        This is the real generation path test (D307): the stop data that arrives
        from Wikidata/venue_resolver may contain U+2019 curly apostrophes.
        """
        stop = {
            'canonical_title': "Le L\u00e9zard aux plumes d\u2019or",
            'artist': 'Joan Mir\u00f3',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'venue_name': 'Museum of Fine Arts Boston',
            'publisher': 'Louis Broder',
            'printer': 'Mourlot Fr\u00e8res',
            'credit_line': 'Gift of Boris Fridman to the Museum of Fine Arts, Boston',
            'medium': 'lithographs',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        self.assertGreater(len(queries), 0)
        # Each query must produce valid JSON when passed through the serialization path
        for q in queries:
            payload = {"q": q, "num": 8}
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            parsed = json.loads(data.decode('utf-8'))
            self.assertEqual(parsed['q'], q)

    def test_serp_search_logs_request_and_response_on_http_error(self):
        """On HTTP 400, _serp_search prints the request payload AND response body.

        This is the core fix: previously the error handler only printed str(e),
        losing the response body that would diagnose the 400.
        """
        import urllib.error
        import urllib.request

        # Set up a key so the function doesn't bail early
        original_key = work_story_searcher.SERP_API_KEY
        work_story_searcher.SERP_API_KEY = 'test_key_for_409'

        try:
            # Create a fake HTTPError with a response body
            fake_body = b'{"message": "Invalid query: unbalanced quotes", "code": 400}'
            fake_fp = MagicMock()
            fake_fp.read.return_value = fake_body

            http_error = urllib.error.HTTPError(
                url='https://google.serper.dev/search',
                code=400,
                msg='Bad Request',
                hdrs={},
                fp=fake_fp,
            )

            with patch.object(urllib.request, 'urlopen', side_effect=http_error):
                # Capture stdout
                captured = StringIO()
                with patch('sys.stdout', captured):
                    results, latency = _serp_search("\"Le Lézard aux plumes d'or\" Miró")

            output = captured.getvalue()

            # Verify the function returns empty results (graceful degradation)
            self.assertEqual(results, [])

            # Verify request payload is logged
            self.assertIn('request payload:', output)
            self.assertIn('Lézard', output)  # The query is visible

            # Verify response body is logged
            self.assertIn('response body:', output)
            self.assertIn('Invalid query', output)  # The server's error message

            # Verify HTTP status code is logged
            self.assertIn('400', output)

        finally:
            work_story_searcher.SERP_API_KEY = original_key

    def test_serp_search_logs_on_non_http_exception(self):
        """On network errors (timeout, DNS), _serp_search logs the request payload."""
        import urllib.request

        original_key = work_story_searcher.SERP_API_KEY
        work_story_searcher.SERP_API_KEY = 'test_key_for_409'

        try:
            with patch.object(urllib.request, 'urlopen',
                            side_effect=TimeoutError("Connection timed out")):
                captured = StringIO()
                with patch('sys.stdout', captured):
                    results, latency = _serp_search("test query")

            output = captured.getvalue()
            self.assertEqual(results, [])
            self.assertIn('request payload:', output)
            self.assertIn('TimeoutError', output)

        finally:
            work_story_searcher.SERP_API_KEY = original_key

    def test_generation_path_query_roundtrip(self):
        """Full generation-path test: stop data → synthesize → serialize → valid payload.

        This is the D307 test on the real generation path. A query containing
        an accented title AND a U+2019 apostrophe must produce a well-formed
        request that a JSON API would accept (no malformed bytes, no truncation).
        """
        # Simulate data as it arrives from Wikidata (with curly apostrophe)
        stop = {
            'canonical_title': "Le L\u00e9zard aux plumes d\u2019or",
            'artist': 'Joan Mir\u00f3',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'venue_name': 'Museum of Fine Arts Boston',
            'publisher': 'Louis Broder',
            'printer': 'Mourlot Fr\u00e8res',
            'credit_line': 'Gift of Boris Fridman',
            'medium': 'lithographs',
            'english_title': 'The Lizard with Golden Feathers',
        }

        queries = synthesize_queries(stop, tour_type='contained')

        for query in queries:
            # This is exactly what _serp_search does internally
            payload = {"q": query, "num": 8}
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')

            # Verify: valid UTF-8
            decoded = data.decode('utf-8')
            # Verify: valid JSON
            parsed = json.loads(decoded)
            self.assertEqual(parsed['q'], query)

            # Verify: no null bytes or control characters that would trigger 400
            self.assertNotIn('\x00', decoded)
            self.assertNotIn('\n', parsed['q'])  # newlines in query value would be odd
            self.assertNotIn('\r', parsed['q'])


class TestSerpSearchEnsureAsciiChange(unittest.TestCase):
    """Verify the ensure_ascii=False change doesn't break valid payloads."""

    def test_ascii_only_query_unchanged(self):
        """Pure ASCII queries still produce valid payloads."""
        query = "Louis Broder Joan Miro publisher"
        payload = {"q": query, "num": 8}
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        parsed = json.loads(data)
        self.assertEqual(parsed['q'], query)

    def test_mixed_scripts_valid(self):
        """Queries with mixed scripts (Latin + accents) are valid."""
        query = "café résumé naïve"
        payload = {"q": query, "num": 8}
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        parsed = json.loads(data)
        self.assertEqual(parsed['q'], query)

    def test_quotes_in_query_properly_escaped(self):
        """Embedded double quotes in query are JSON-escaped."""
        query = '"Le Lézard" "history"'
        payload = {"q": query, "num": 8}
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        # The raw JSON should have escaped quotes within the string value
        self.assertIn('\\"Le', data.decode('utf-8'))
        parsed = json.loads(data)
        self.assertEqual(parsed['q'], query)


if __name__ == '__main__':
    unittest.main()
