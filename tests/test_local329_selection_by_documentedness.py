"""tests/test_local329_selection_by_documentedness.py — LOCAL-329 tests.

Tests that:
  1. reason_has_substance correctly admits factual reasons and rejects hollow ones.
  2. _is_hollow detects ranking-only mentions.
  3. persist_selection_reasons writes to stop_corpus (integration, requires DB).
  4. The restaurant constraint prompt asks for notability with reasons.
  5. Walking tours also get the reason field in JSON schema.
"""

import json
import os
import sys
import re
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestReasonHasSubstance:
    """Unit tests for the substance detection in selection_reason_filter."""

    def setup_method(self):
        from selection_reason_filter import reason_has_substance, _is_hollow
        self.reason_has_substance = reason_has_substance
        self._is_hollow = _is_hollow

    # ─── Should PASS (substantive reasons) ────────────────────────────────

    def test_year_and_dish(self):
        """Acchiardo-style reason: year + dish = substance."""
        reason = "Founded in 1927 by the Acchiardo family; known for handmade ravioli and slow-cooked daube niçoise"
        assert self.reason_has_substance(reason) is True

    def test_technique_and_tradition(self):
        """Chez Thérésa-style: wood-fired + named dish."""
        reason = "Serves socca from a traditional wood-fired oven, a Niçoise street food tradition since the 1920s"
        assert self.reason_has_substance(reason) is True

    def test_named_person_and_year(self):
        """Chef + year = substance."""
        reason = "Chef Dominique Le Stanc opened this bistro in 2001 after leaving the Negresco"
        assert self.reason_has_substance(reason) is True

    def test_seasonal_menu_and_wine(self):
        """Le Panier-style: seasonal menu + natural wine."""
        reason = "Seasonal menu with natural and local wine list, focusing on farm-to-table cuisine"
        assert self.reason_has_substance(reason) is True

    def test_architectural_detail(self):
        """Historical building detail = substance."""
        reason = "Located in a 17th-century vaulted cellar near Place Rossetti"
        assert self.reason_has_substance(reason) is True

    def test_family_generations(self):
        """Multi-generational family = substance."""
        reason = "Run by the same family for three generations since 1958, serving traditional Niçoise fare"
        assert self.reason_has_substance(reason) is True

    def test_michelin_with_specifics(self):
        """Michelin star + specific dish = substance (not hollow because dish is named)."""
        reason = "One Michelin star since 2015, known for its tasting menu featuring local sea bass and ratatouille"
        assert self.reason_has_substance(reason) is True

    def test_price_range(self):
        """Price information = substance."""
        reason = "Three-course lunch menu for €22, focusing on seasonal Provençal dishes"
        assert self.reason_has_substance(reason) is True

    # ─── Should FAIL (hollow reasons) ─────────────────────────────────────

    def test_hollow_popular_ranking(self):
        """Pure ranking mention = hollow."""
        reason = "Appears frequently in top restaurant rankings for Nice"
        assert self.reason_has_substance(reason) is False

    def test_hollow_quality_offerings(self):
        """Vague quality claim = hollow."""
        reason = "Known for its quality offerings and warm atmosphere"
        assert self.reason_has_substance(reason) is False

    def test_hollow_highly_rated(self):
        """Rating-only = hollow."""
        reason = "Highly rated by visitors and consistently receives excellent reviews"
        assert self.reason_has_substance(reason) is False

    def test_hollow_must_visit(self):
        """Tourism cliché = hollow."""
        reason = "A must-visit spot popular among tourists and locals alike"
        assert self.reason_has_substance(reason) is False

    def test_hollow_beloved_locals(self):
        """Vague popularity = hollow."""
        reason = "Beloved by locals for its charming atmosphere and quality food"
        assert self.reason_has_substance(reason) is False

    def test_hollow_earned_reputation(self):
        """Reputation claim without specifics = hollow."""
        reason = "Has earned a reputation as one of the best restaurants in the area"
        assert self.reason_has_substance(reason) is False

    def test_hollow_earning_high_marks(self):
        """D233 example: blog rating laundered into prose."""
        reason = "Earning high marks in creativity and execution from food critics"
        assert self.reason_has_substance(reason) is False

    def test_hollow_short_vague(self):
        """Too short and vague = no substance."""
        reason = "Nice spot"
        assert self.reason_has_substance(reason) is False

    def test_hollow_widely_regarded(self):
        """Vague esteem claim = hollow."""
        reason = "Widely regarded as one of the top dining establishments in Old Nice"
        assert self.reason_has_substance(reason) is False

    # ─── Edge cases ───────────────────────────────────────────────────────

    def test_mixed_hollow_and_substance(self):
        """A reason that mixes hollow language with a real fact should pass."""
        reason = "Popular for its socca, a chickpea pancake they've made since 1927"
        assert self.reason_has_substance(reason) is True

    def test_empty_reason(self):
        """Empty string = no substance."""
        assert self.reason_has_substance("") is False

    def test_none_like_reason(self):
        """Very short = no substance."""
        assert self.reason_has_substance("good") is False


class TestIsHollow:
    """Directly test _is_hollow detection."""

    def setup_method(self):
        from selection_reason_filter import _is_hollow
        self._is_hollow = _is_hollow

    def test_pure_ranking_is_hollow(self):
        assert self._is_hollow("One of the best restaurants in the old town") is True

    def test_factual_is_not_hollow(self):
        assert self._is_hollow("Founded in 1927 by the Acchiardo family") is False

    def test_popular_with_dish_is_not_hollow(self):
        """Hollow phrase + substance = not hollow (substance saves it)."""
        assert self._is_hollow("Popular for its wood-fired socca since the 1920s") is False


class TestPromptChanges:
    """Verify the Phase 3A prompt includes documentedness guidance for restaurants."""

    def test_restaurant_constraint_asks_for_reasons(self):
        """The restaurant venue constraint must ask for notability with reasons."""
        # Read the actual source file
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        # The constraint must mention notability, documented, and reason
        assert 'NOTABLE and DOCUMENTED' in source
        assert "'reason' field explaining WHY" in source
        # Must reject vague phrases
        assert "Do NOT use vague phrases like 'popular'" in source

    def test_json_schema_includes_reason_for_restaurants(self):
        """JSON schema hint for restaurants must include a 'reason' field."""
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        # Find the restaurant JSON hint
        assert '"reason": "Founded in 1927' in source

    def test_json_schema_includes_reason_for_walking(self):
        """JSON schema hint for walking tours must include a 'reason' field."""
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        # Walking tours also get reason field
        assert '"reason": "Brief reason why this landmark is notable' in source

    def test_museum_tours_not_affected(self):
        """Museum tours must NOT get a reason field — they use deterministic fill."""
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'generate_tour_text.py'
        )
        with open(source_path, 'r') as f:
            source = f.read()

        # The else branch (non-restaurant, non-walking) should not have reason
        # Check the museum venue constraint doesn't mention "reason"
        # Find _museum_venue_constraint text
        museum_constraint_match = re.search(
            r'_museum_venue_constraint\s*=\s*\((.+?)\)',
            source, re.DOTALL
        )
        if museum_constraint_match:
            museum_text = museum_constraint_match.group(1)
            assert 'reason' not in museum_text.lower()


@pytest.mark.integration
class TestPersistSelectionReasons:
    """Integration tests: persist_selection_reasons writes to stop_corpus."""

    def setup_method(self):
        """Set up test database connection."""
        # Route to test database
        os.environ['AUDIOURA_DB_TARGET'] = 'test'
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        from db_connection import get_connection, check_db_available
        if not check_db_available():
            pytest.skip("Test database unavailable")
        self.conn = get_connection()
        self.cur = self.conn.cursor()

        # Create stop_corpus table in test DB if it doesn't exist
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_corpus (
                id SERIAL PRIMARY KEY,
                venue_name TEXT NOT NULL,
                stop_title TEXT NOT NULL,
                passages_json JSONB DEFAULT '[]'::jsonb NOT NULL,
                source_pages JSONB DEFAULT '[]'::jsonb NOT NULL,
                passage_count INTEGER DEFAULT 0 NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
                passage_roles JSONB,
                UNIQUE(venue_name, stop_title)
            )
        """)
        self.conn.commit()

        # Clean up any test data from previous runs
        self.cur.execute(
            "DELETE FROM stop_corpus WHERE venue_name = %s",
            ('_test_local329_venue',)
        )
        self.conn.commit()

    def teardown_method(self):
        """Clean up test data."""
        if hasattr(self, 'cur') and self.cur:
            self.cur.execute(
                "DELETE FROM stop_corpus WHERE venue_name = %s",
                ('_test_local329_venue',)
            )
            self.conn.commit()
            self.cur.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
        os.environ.pop('AUDIOURA_DB_TARGET', None)

    def test_persist_substantive_reason(self):
        """A substantive reason should be persisted to stop_corpus."""
        from selection_reason_filter import persist_selection_reasons

        # Override DB env to point to test database
        from db_connection import get_database_url
        os.environ['DATABASE_URL'] = get_database_url()

        reasons = {
            'test restaurant alpha': 'Founded in 1927 by the Alpha family, known for handmade ravioli'
        }
        surviving = ['Test Restaurant Alpha']
        count = persist_selection_reasons(reasons, surviving, '_test_local329_venue')
        assert count == 1

        # Verify it's in the database
        self.cur.execute(
            "SELECT passages_json, source_pages, passage_count FROM stop_corpus "
            "WHERE venue_name = %s AND stop_title = %s",
            ('_test_local329_venue', 'Test Restaurant Alpha')
        )
        row = self.cur.fetchone()
        assert row is not None
        assert row[2] == 1  # passage_count

        passages = row[0] if isinstance(row[0], list) else json.loads(row[0])
        assert len(passages) == 1
        assert 'Founded in 1927' in passages[0]['text']
        assert passages[0]['source_type'] == 'selection_reason'
        assert passages[0]['verified'] is False

        sources = row[1] if isinstance(row[1], list) else json.loads(row[1])
        assert sources[0]['url'] == 'llm:phase3a-selection'
        assert sources[0]['tier'] == 3

    def test_does_not_overwrite_existing_corpus(self):
        """If a stop already has corpus passages, don't overwrite."""
        from selection_reason_filter import persist_selection_reasons
        from db_connection import get_database_url
        os.environ['DATABASE_URL'] = get_database_url()

        # Insert existing corpus
        self.cur.execute(
            """INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
               VALUES (%s, %s, %s, %s, 3)""",
            ('_test_local329_venue', 'Test Restaurant Beta',
             json.dumps([{"text": "existing1"}, {"text": "existing2"}, {"text": "existing3"}]),
             json.dumps([{"url": "https://example.com"}]))
        )
        self.conn.commit()

        reasons = {
            'test restaurant beta': 'Chef Marie Dubois opened in 2005'
        }
        surviving = ['Test Restaurant Beta']
        count = persist_selection_reasons(reasons, surviving, '_test_local329_venue')
        assert count == 0  # Should NOT overwrite

        # Verify original data intact
        self.cur.execute(
            "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
            ('_test_local329_venue', 'Test Restaurant Beta')
        )
        row = self.cur.fetchone()
        assert row[0] == 3  # Original count preserved

    def test_only_persists_surviving_stops(self):
        """Reasons for stops that didn't survive gates should not be persisted."""
        from selection_reason_filter import persist_selection_reasons
        from db_connection import get_database_url
        os.environ['DATABASE_URL'] = get_database_url()

        reasons = {
            'test restaurant gamma': 'Since 1950, family-run trattoria with handmade pasta',
            'test restaurant delta': 'Founded in 1888, famous for its wood-fired socca',
        }
        # Only gamma survived; delta was dropped by existence gate
        surviving = ['Test Restaurant Gamma']
        count = persist_selection_reasons(reasons, surviving, '_test_local329_venue')
        assert count == 1

        # Delta should NOT be in the database
        self.cur.execute(
            "SELECT COUNT(*) FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
            ('_test_local329_venue', 'Test Restaurant Delta')
        )
        assert self.cur.fetchone()[0] == 0
