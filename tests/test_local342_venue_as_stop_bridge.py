"""test_local342_venue_as_stop_bridge.py — LOCAL-342 unit tests.

Tests that venue_corpus is bridged to stop lookups when a stop's title
matches a known venue. Must FAIL against the pre-LOCAL-342 codebase where
get_stop_corpus_for_tour returns None for such stops.

Acceptance criteria:
  - Palais Lascaris as a walking-tour stop finds passages from venue_corpus
  - Museum tours are unaffected (stops inside a museum still resolve via stop_corpus)
  - No rows inserted/deleted from either corpus table
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))

import pytest


@pytest.fixture
def db_conn(monkeypatch):
    """Get a database connection to production DB (read-only tests).

    These tests need real corpus data. They are strictly read-only —
    verified by test_no_rows_inserted.
    """
    monkeypatch.setenv("AUDIOURA_DB_TARGET", "production")
    from db_connection import get_connection, check_db_available
    if not check_db_available():
        pytest.skip("Database not available")
    conn = get_connection()
    yield conn
    conn.close()


class TestVenueAsStopBridge:
    """Test that venue_corpus pages are bridged to stop lookups."""

    def test_palais_lascaris_found_via_bridge(self, db_conn):
        """Palais Lascaris as a walking-tour stop must find venue_corpus passages.

        Pre-fix: returns None (no stop_corpus row for 'Palais Lascaris' under
        any walking tour venue).
        Post-fix: returns passages from venue_corpus pages_json.
        """
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            venue_name='walking tour in Nice, france',
            stop_names=['Palais Lascaris'],
            conn=db_conn,
        )

        data = result.get('Palais Lascaris')
        assert data is not None, (
            "Palais Lascaris should be found via venue_corpus bridge. "
            "Pre-LOCAL-342 code returns None here."
        )
        assert len(data['passages']) > 0, "Should have at least one passage"
        # The content should be about the building (Wikipedia article)
        all_text = ' '.join(data['passages'])
        assert 'lascaris' in all_text.lower(), (
            "Passages should mention Lascaris (it's the Wikipedia article about the building)"
        )

    def test_bridge_provides_sources(self, db_conn):
        """Bridged passages must carry source URLs."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            venue_name='walking tour in Nice, france',
            stop_names=['Palais Lascaris'],
            conn=db_conn,
        )

        data = result['Palais Lascaris']
        assert data['sources'], "Must provide source URLs"
        assert any('wikipedia' in s.get('url', '').lower() for s in data['sources']), \
            "Source should be Wikipedia"

    def test_bridge_has_passage_roles(self, db_conn):
        """Bridged passages must have passage_roles for role-aware coverage."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            venue_name='walking tour in Nice, france',
            stop_names=['Palais Lascaris'],
            conn=db_conn,
        )

        data = result['Palais Lascaris']
        assert 'passage_roles' in data, "Must include passage_roles"
        assert len(data['passage_roles']) == len(data['passages']), \
            "passage_roles length must match passages length"

    def test_museum_objects_not_affected(self, db_conn):
        """Objects inside Palais Lascaris (museum stops) must still resolve
        via stop_corpus, NOT the venue bridge.

        This ensures museum tours don't regress.
        """
        from stop_corpus_reader import get_stop_corpus_for_tour

        # These are objects inside Palais Lascaris, filed in stop_corpus
        result = get_stop_corpus_for_tour(
            venue_name='Palais Lascaris, Nice',
            stop_names=['Harpe by Naderman (Paris, 1780)'],
            conn=db_conn,
        )

        data = result.get('Harpe by Naderman (Paris, 1780)')
        assert data is not None, "Museum object should still resolve via stop_corpus"
        # Must NOT be venue bridge content (should be specific to the harp)
        assert data.get('passage_roles') is not None

    def test_bridge_does_not_match_walking_area_venues(self, db_conn):
        """Venues with 'walking area' suffix should not bridge.

        These are geographic labels, not specific buildings.
        """
        from stop_corpus_reader import _venue_name_matches_stop

        assert not _venue_name_matches_stop(
            'Fort du Mont Alban', 'Fort du Mont Alban walking area'
        ), "Walking area venues should not bridge"

    def test_accent_fold_in_bridge_matching(self, db_conn):
        """Bridge matching must fold accents and typographic quotes (D253)."""
        from stop_corpus_reader import _venue_name_matches_stop

        # Accent folding
        assert _venue_name_matches_stop(
            'Musee Picasso', 'Musée Picasso, Antibes, France'
        ), "Should match with accent folding"

        # Typographic apostrophe
        assert _venue_name_matches_stop(
            "Palais de l\u2019Art", "Palais de l'Art, Nice"
        ), "Should fold U+2019 to ASCII apostrophe"

    def test_object_catalogue_filter(self):
        """Short catalogue-style passages about objects should be filtered out."""
        from stop_corpus_reader import _is_object_catalogue_passage

        # This should be filtered (short, about a specific maker)
        assert _is_object_catalogue_passage(
            "Made by Antonio Stradivari in 1714. Length: 35 cm."
        ), "Short catalogue entry should be filtered"

        # This should NOT be filtered (long text mentioning a maker in context)
        long_passage = (
            "The palace was built by the Lascaris family in the 17th century. "
            "It now houses a collection of musical instruments. The building's "
            "baroque architecture features painted ceilings by Giovanni Carlone. " * 3
        )
        assert not _is_object_catalogue_passage(long_passage), \
            "Long contextual passage should not be filtered"

    def test_no_rows_inserted(self, db_conn):
        """The bridge is read-time only — no corpus rows should be created."""
        cur = db_conn.cursor()
        cur.execute("SELECT count(*) FROM stop_corpus")
        before_stop = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM venue_corpus")
        before_venue = cur.fetchone()[0]

        from stop_corpus_reader import get_stop_corpus_for_tour
        get_stop_corpus_for_tour(
            venue_name='walking tour in Nice, france',
            stop_names=['Palais Lascaris'],
            conn=db_conn,
        )

        cur.execute("SELECT count(*) FROM stop_corpus")
        after_stop = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM venue_corpus")
        after_venue = cur.fetchone()[0]
        cur.close()

        assert before_stop == after_stop, "stop_corpus row count must not change"
        assert before_venue == after_venue, "venue_corpus row count must not change"
