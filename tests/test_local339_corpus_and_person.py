"""Tests for LOCAL-339: Stop corpus matching and person model fixes.

These tests verify:
1. Stop-title-first corpus matching (Defect 1): Chez Pipo finds its passages
   even when the tour venue string doesn't match the corpus venue_name.
2. Person model structural guards (Defect 2): false positives from leading
   prepositions, articles, and place names in object position are excluded.

Per D242: tests import production code and must fail against the unfixed version.
"""
import os
import sys
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))


class TestStopCorpusMatching:
    """Defect 1: venue-scoped lookup misses stops whose corpus is under a
    different venue_name than the tour header suggests."""

    @pytest.fixture
    def db_conn(self):
        from tests.db_connection import get_connection, check_db_available
        # Use production DB for read-only corpus lookups
        old_target = os.environ.get('AUDIOURA_DB_TARGET')
        os.environ['AUDIOURA_DB_TARGET'] = 'production'
        try:
            if not check_db_available():
                pytest.skip("Database not available")
            conn = get_connection()
            yield conn
            conn.close()
        finally:
            if old_target is None:
                os.environ.pop('AUDIOURA_DB_TARGET', None)
            else:
                os.environ['AUDIOURA_DB_TARGET'] = old_target

    def test_chez_pipo_found_via_title_first_matching(self, db_conn):
        """Chez Pipo has 10 passages under 'Old Nice, Nice, France' but the
        tour header says 'restaurant tour in Old Nice (Vieux Nice), France'.
        The title-first strategy must find it regardless of venue mismatch."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_conn,
        )

        assert result['Chez Pipo'] is not None, (
            "Chez Pipo should be found — it has 10 passages in stop_corpus"
        )
        assert len(result['Chez Pipo']['passages']) > 0, (
            "Chez Pipo should have passages after sludge filtering"
        )

    def test_prolog_place_applied_to_venue(self, db_conn):
        """The venue string should be cleaned via _prolog_place before matching.
        'restaurant tour in Old Nice (Vieux Nice), France' → 'Old Nice (Vieux Nice), France'."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        # Even with the full header string, all stops should be found
        result = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ["L'Escalinada", 'Chez Pipo'],
            db_conn,
        )

        # L'Escalinada exists under the matched venue
        assert result["L'Escalinada"] is not None, (
            "L'Escalinada should be found in stop_corpus"
        )

    def test_accent_folded_stop_title_matching(self, db_conn):
        """Accent-folded matching (D243): 'Robe de prêtre taoïste' must find
        corpus stored as 'Robe de pretre taoiste'."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            'Musée des Arts Asiatiques, Nice - Museum Tour',
            ['Robe de prêtre taoïste'],
            db_conn,
        )

        assert result['Robe de prêtre taoïste'] is not None, (
            "Accent-folded matching should find 'Robe de pretre taoiste' in corpus"
        )

    def test_tie_breaking_prefers_richest_corpus(self, db_conn):
        """When a stop_title exists under multiple venues, prefer the row with
        the most passages (after sludge filtering)."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        # Chez Palmyre exists under 3 venues with different passage counts
        result = get_stop_corpus_for_tour(
            'Old Nice, Nice, France',
            ['Chez Palmyre'],
            db_conn,
        )

        assert result['Chez Palmyre'] is not None


class TestPersonModelStructuralGuards:
    """Defect 2: person model over-fires on place names, dish names, and
    venue references that happen to appear near person-context words."""

    def _get_people_for_text(self, stop_title, body_text, all_titles=None):
        """Helper: extract named_people from a stop body."""
        from tour_rubric_scorer import parse_tour, analyze_stop

        if all_titles is None:
            all_titles = [stop_title]

        tour_text = f"Stop 1: {stop_title}\n\n{body_text}"
        for i, title in enumerate(all_titles[1:], 2):
            tour_text += f"\n\nStop {i}: {title}\n\nSome body text."

        stops = parse_tour(tour_text)
        sa = analyze_stop(stops[0], stops)
        return sa.named_people

    def test_at_chez_pipo_excluded_via_title_strip(self):
        """'At Chez Pipo' has a leading preposition — stripping it yields
        'Chez Pipo' which matches the stop title exactly → excluded."""
        people = self._get_people_for_text(
            'Chez Pipo',
            "At Chez Pipo, the Socca embodies the community traditions of Old Nice.",
            all_titles=['Chez Pipo'],
        )
        assert 'At Chez Pipo' not in people, (
            "'At Chez Pipo' should be excluded — strip leading 'At' → matches title"
        )

    def test_old_nice_excluded_via_preposition_guard(self):
        """'Old Nice' preceded by 'of' is an object, not a person, even though
        'embodies' appears in the context window."""
        people = self._get_people_for_text(
            'Chez Pipo',
            "the Socca embodies the community traditions of Old Nice. The sizzling griddle.",
            all_titles=['Chez Pipo'],
        )
        assert 'Old Nice' not in people, (
            "'Old Nice' preceded by 'of' should be blocked by the preposition guard"
        )

    def test_the_socca_excluded_via_article_guard(self):
        """'The Socca' is a 2-word phrase starting with 'The' — structurally a
        thing reference, not a person name."""
        people = self._get_people_for_text(
            'Chez Pipo',
            "The Socca, a simple yet flavorful chickpea pancake, takes center stage.",
            all_titles=['Chez Pipo'],
        )
        assert 'The Socca' not in people, (
            "'The Socca' with leading article 'The' should be blocked"
        )

    def test_chez_palmyre_excluded_via_not_a_person(self):
        """'Chez Palmyre' contains 'chez' — a structural French venue prefix
        that is never part of a person's name."""
        people = self._get_people_for_text(
            'Chez Pipo',
            "Established in 1926 as Chez Palmyre by Palmyre Moni, the founder.",
            all_titles=['Chez Pipo'],
        )
        assert 'Chez Palmyre' not in people, (
            "'Chez Palmyre' should be blocked — 'chez' is a venue prefix"
        )

    def test_palmyre_moni_still_detected(self):
        """'Palmyre Moni' is a real person — preceded by 'by' (agent), with
        'Established' in context. Must NOT be lost."""
        people = self._get_people_for_text(
            'Chez Pipo',
            "Established in 1926 as Chez Palmyre by Palmyre Moni, the founder from Tuscany.",
            all_titles=['Chez Pipo'],
        )
        assert 'Palmyre Moni' in people, (
            "'Palmyre Moni' is a real person and must be detected"
        )

    def test_ulysses_grant_still_detected(self):
        """D247: 'Ulysses Grant' named within 'Ulysses Grant au Japon' must
        stay detected — a person inside a longer title."""
        people = self._get_people_for_text(
            'Ulysses Grant au Japon',
            "In 1879, the American general turned statesman, Ulysses Grant, embarked upon "
            "his historic visit to Japan. The xylogravure was crafted by Toyohara Chikanobu.",
            all_titles=['Ulysses Grant au Japon'],
        )
        assert 'Ulysses Grant' in people, (
            "D247: 'Ulysses Grant' named inside a longer title must be kept"
        )

    def test_ando_naoyuki_still_detected(self):
        """D247: 'Andô Naoyuki' named within 'L'Armure d'Andô Naoyuki' must
        stay detected — a person inside a longer title."""
        people = self._get_people_for_text(
            "L'Armure d'Andô Naoyuki",
            "Historically, Andô Naoyuki, heir to the Tanabe domain and destined for "
            "the title of baron, wore this armor at a pivotal moment in his life.",
            all_titles=["L'Armure d'Andô Naoyuki"],
        )
        assert 'Andô Naoyuki' in people or 'Ando Naoyuki' in people, (
            "D247: 'Andô Naoyuki' named inside a longer title must be kept"
        )

    def test_nice_coastal_city_no_person(self):
        """'Nice, a coastal city, offers…' must yield no person — the
        appositive contains 'city', a place noun."""
        people = self._get_people_for_text(
            'Promenade des Anglais',
            "Nice, a coastal city, offers stunning views of the Mediterranean.",
            all_titles=['Promenade des Anglais'],
        )
        assert 'Nice' not in str(people), (
            "'Nice, a coastal city' should be blocked by the place-noun guard"
        )

    def test_filler_yields_nothing(self):
        """Filler text with no structural person indicators yields empty."""
        people = self._get_people_for_text(
            'Le Cafe',
            "A mix of laughter and clinking glasses fills the air as you step inside.",
            all_titles=['Le Cafe'],
        )
        assert people == [], (
            "Filler text should yield no named people"
        )


class TestFullTourIntegration:
    """Integration test: score the restaurant tour and verify both fixes."""

    @pytest.fixture
    def db_conn(self):
        from tests.db_connection import get_connection, check_db_available
        # Use production DB for read-only corpus lookups
        old_target = os.environ.get('AUDIOURA_DB_TARGET')
        os.environ['AUDIOURA_DB_TARGET'] = 'production'
        try:
            if not check_db_available():
                pytest.skip("Database not available")
            conn = get_connection()
            yield conn
            conn.close()
        finally:
            if old_target is None:
                os.environ.pop('AUDIOURA_DB_TARGET', None)
            else:
                os.environ['AUDIOURA_DB_TARGET'] = old_target

    def test_chez_pipo_groundedness_measured(self, db_conn):
        """Stop 4 (Chez Pipo) must have groundedness measured, not None."""
        from tour_rubric_scorer import score_tour_file

        tour_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL336_restaurant_4stop.txt'
        )
        if not os.path.exists(tour_path):
            pytest.skip("Tour file not available")

        # score_tour_file creates its own DB connection internally;
        # AUDIOURA_DB_TARGET is already set to 'production' by the fixture.
        ts = score_tour_file(tour_path, 4)
        stop4 = [s for s in ts.stops if s.title == 'Chez Pipo'][0]

        assert stop4.groundedness_fraction is not None, (
            "Chez Pipo groundedness must be measured (not None) — corpus exists"
        )
        assert getattr(stop4, 'corpus_available', False) is True, (
            "Chez Pipo must have corpus_available=True"
        )

    def test_chez_pipo_only_palmyre_moni(self, db_conn):
        """Stop 4 named_people must contain only 'Palmyre Moni'."""
        from tour_rubric_scorer import score_tour_file

        tour_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL336_restaurant_4stop.txt'
        )
        if not os.path.exists(tour_path):
            pytest.skip("Tour file not available")

        ts = score_tour_file(tour_path, 4)
        stop4 = [s for s in ts.stops if s.title == 'Chez Pipo'][0]

        assert stop4.named_people == ['Palmyre Moni'], (
            f"Expected only 'Palmyre Moni', got: {stop4.named_people}"
        )
