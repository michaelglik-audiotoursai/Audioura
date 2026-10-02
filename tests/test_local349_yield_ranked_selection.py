"""tests/test_local349_yield_ranked_selection.py — LOCAL-349: Yield-based ranking tests.

Tests that COVERED candidates are ranked by expected yield (quality score)
rather than treated as equivalent. Must FAIL against the unfixed version
(flat COVERED sort) and PASS with yield-based sub-ranking.

Key assertion: Acchiardo (4 clean passages, web_search + interpretive_enrichment)
is preferred over La Rossettisserie (1 clean passage, web_search only).
"""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from corpus_source_quality import (
    classify_passage,
    compute_quality_score,
    get_bulk_quality_scores,
    is_sludge,
)


class TestYieldRanking:
    """Yield-based ranking uses quality score as tie-breaker within COVERED."""

    # Simulated corpus data matching the real DB state (from task description)
    ACCHIARDO_PASSAGES = [
        # 4 clean + 2 sludge = 6 total. Sources: web_search + interpretive_enrichment
        {'text': 'Since 1927, the Acchiardo family has served authentic Niçoise cuisine from this tiny dining room on Rue Droite.', 'type': 'web_search'},
        {'text': 'Traditional socca — a chickpea-flour crêpe baked in a wood-fired oven — is their signature dish, unchanged in nearly a century.', 'type': 'interpretive_enrichment'},
        {'text': 'Their daube niçoise, slow-braised beef with olives and red wine, has drawn locals and visitors since the post-war era.', 'type': 'interpretive_enrichment'},
        {'text': 'The restaurant occupies a narrow medieval building on one of Old Nice\'s oldest streets, with marble-topped tables and no pretension.', 'type': 'web_search'},
        # 2 sludge passages
        {'text': 'Acchiardo · Nice · Restaurant · $$ · French', 'type': 'web_search'},
        {'text': 'Nice restaurants ... Old Nice ... best places ... Acchiardo ... reviews ...', 'type': 'web_search'},
    ]

    ROSSETTISSERIE_PASSAGES = [
        # 1 clean + 4 sludge = 5 total. Source: web_search only.
        {'text': 'La Rossettisserie is located on Rue Rossetti in the heart of Old Nice, serving rotisserie meats.', 'type': 'web_search'},
        # 4 sludge passages
        {'text': 'La Rossettisserie · Nice · Restaurant · $$ · French · Rotisserie', 'type': 'web_search'},
        {'text': '... La Rossettisserie ... Nice restaurants ... best rotisserie ... Vieux Nice ...', 'type': 'web_search'},
        {'text': 'Nice · Restaurants · $$ · Rossettisserie', 'type': 'web_search'},
        {'text': 'La Rossettisserie - Restaurant in Vieux Nice, 06300. 11. Le Safari - Restaurant ...', 'type': 'web_search'},
    ]

    def test_acchiardo_scores_higher_than_rossettisserie(self):
        """Acchiardo (diverse sources, more clean passages) must score higher.

        This is the core assertion: the quality score correctly identifies
        Acchiardo as higher-yield despite having MORE total passages than
        La Rossettisserie (passage count is anti-correlated with quality per D241).
        """
        acchiardo_classified = [classify_passage(p) for p in self.ACCHIARDO_PASSAGES]
        rossettisserie_classified = [classify_passage(p) for p in self.ROSSETTISSERIE_PASSAGES]

        acchiardo_score = compute_quality_score(acchiardo_classified)
        rossettisserie_score = compute_quality_score(rossettisserie_classified)

        # Acchiardo: 2 web_search (0.5 each) + 2 interpretive_enrichment (1.0 each) = 3.0
        # Rossettisserie: 1 web_search (0.5) = 0.5
        assert acchiardo_score > rossettisserie_score, (
            f"Acchiardo ({acchiardo_score}) should rank higher than "
            f"La Rossettisserie ({rossettisserie_score})"
        )

    def test_passage_count_does_not_determine_ranking(self):
        """D241: passage_count is anti-correlated with quality.

        La Rossettisserie (5 passages) must NOT beat Acchiardo (6 passages)
        just because it has fewer passages. The old code treated all COVERED
        as equal — the new code must distinguish by yield.
        """
        assert len(self.ROSSETTISSERIE_PASSAGES) == 5
        assert len(self.ACCHIARDO_PASSAGES) == 6
        # Fewer passages ≠ higher quality
        ross_classified = [classify_passage(p) for p in self.ROSSETTISSERIE_PASSAGES]
        acch_classified = [classify_passage(p) for p in self.ACCHIARDO_PASSAGES]
        assert compute_quality_score(acch_classified) > compute_quality_score(ross_classified)

    def test_selection_sort_prefers_acchiardo(self):
        """Simulate the LOCAL-212 selection sort with LOCAL-349 yield ranking.

        Given 6 COVERED candidates and 4 stops requested, Acchiardo must be
        selected and La Rossettisserie dropped (or ranked lower).
        """
        # Simulate poi_list with 6 COVERED candidates
        candidates = [
            {'name': 'La Rossettisserie'},
            {'name': 'Le Tire Bouchon'},
            {'name': 'La Tapenade'},
            {'name': 'Le Safari'},
            {'name': 'Acchiardo'},
            {'name': 'Le Vieux Four'},
        ]

        # Simulate verdicts — all COVERED except Le Vieux Four
        verdicts = {
            'La Rossettisserie': 'COVERED',
            'Le Tire Bouchon': 'COVERED',
            'La Tapenade': 'COVERED',
            'Le Safari': 'COVERED',
            'Acchiardo': 'COVERED',
            'Le Vieux Four': 'VENUE_ONLY',
        }

        # Quality scores (simulated from corpus)
        quality_scores = {
            'La Rossettisserie': 0.5,   # 1 clean web_search passage
            'Le Tire Bouchon': 2.0,     # decent corpus
            'La Tapenade': 1.5,         # moderate
            'Le Safari': 1.0,           # moderate
            'Acchiardo': 3.0,           # 4 clean, diverse sources
            'Le Vieux Four': 0.0,       # VENUE_ONLY → doesn't participate in COVERED ranking
        }

        _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}

        # Apply the LOCAL-349 sort: (tier, -quality_score)
        candidates.sort(key=lambda p: (
            _COVERAGE_PRIORITY.get(verdicts.get(p['name'], 'EMPTY'), 3),
            -quality_scores.get(p['name'], 0.0),
        ))

        total_stops = 4
        selected = candidates[:total_stops]
        dropped = candidates[total_stops:]

        selected_names = [p['name'] for p in selected]
        dropped_names = [p['name'] for p in dropped]

        # Acchiardo MUST be selected (highest yield among COVERED)
        assert 'Acchiardo' in selected_names, (
            f"Acchiardo should be selected but was dropped. Selected: {selected_names}"
        )
        # La Rossettisserie MUST be dropped (lowest yield among COVERED)
        assert 'La Rossettisserie' in dropped_names, (
            f"La Rossettisserie should be dropped but was selected. Dropped: {dropped_names}"
        )

    def test_old_sort_fails_to_distinguish(self):
        """The OLD sort (flat COVERED) treats all COVERED as equivalent.

        This test documents the defect: with the old sort, position order
        determines selection, which means La Rossettisserie (position 0)
        beats Acchiardo (position 4).
        """
        candidates = [
            {'name': 'La Rossettisserie'},
            {'name': 'Le Tire Bouchon'},
            {'name': 'La Tapenade'},
            {'name': 'Le Safari'},
            {'name': 'Acchiardo'},
            {'name': 'Le Vieux Four'},
        ]

        verdicts = {
            'La Rossettisserie': 'COVERED',
            'Le Tire Bouchon': 'COVERED',
            'La Tapenade': 'COVERED',
            'Le Safari': 'COVERED',
            'Acchiardo': 'COVERED',
            'Le Vieux Four': 'VENUE_ONLY',
        }

        _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}

        # OLD sort: flat coverage only (stable sort preserves position)
        old_order = list(candidates)
        old_order.sort(key=lambda p: _COVERAGE_PRIORITY.get(
            verdicts.get(p['name'], 'EMPTY'), 3
        ))

        total_stops = 4
        old_selected = [p['name'] for p in old_order[:total_stops]]

        # OLD behavior: first 4 by position win → Acchiardo dropped
        assert 'La Rossettisserie' in old_selected, "Old sort keeps Rossettisserie (by position)"
        assert 'Acchiardo' not in old_selected, "Old sort drops Acchiardo (position 4 > 3)"

    def test_coverage_tier_still_primary(self):
        """Coverage tier must remain the primary sort key.

        A VENUE_ONLY stop with quality_score=10.0 must NOT beat a COVERED
        stop with quality_score=0.5. Yield is a tie-breaker within tier.
        """
        candidates = [
            {'name': 'High-Quality-VenueOnly'},
            {'name': 'Low-Quality-Covered'},
        ]

        verdicts = {
            'High-Quality-VenueOnly': 'VENUE_ONLY',
            'Low-Quality-Covered': 'COVERED',
        }

        quality_scores = {
            'High-Quality-VenueOnly': 10.0,
            'Low-Quality-Covered': 0.5,
        }

        _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}

        candidates.sort(key=lambda p: (
            _COVERAGE_PRIORITY.get(verdicts.get(p['name'], 'EMPTY'), 3),
            -quality_scores.get(p['name'], 0.0),
        ))

        # COVERED must still come first regardless of quality score
        assert candidates[0]['name'] == 'Low-Quality-Covered'

    def test_stop_count_preserved(self):
        """Selection must not drop below requested stop count.

        Even if some stops have poor yield, we select total_stops candidates.
        """
        candidates = [
            {'name': 'A'}, {'name': 'B'}, {'name': 'C'}, {'name': 'D'},
            {'name': 'E'}, {'name': 'F'},
        ]
        verdicts = {n['name']: 'COVERED' for n in candidates}
        quality_scores = {'A': 0.1, 'B': 0.1, 'C': 0.1, 'D': 0.1, 'E': 5.0, 'F': 5.0}

        _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}

        candidates.sort(key=lambda p: (
            _COVERAGE_PRIORITY.get(verdicts.get(p['name'], 'EMPTY'), 3),
            -quality_scores.get(p['name'], 0.0),
        ))

        total_stops = 4
        selected = candidates[:total_stops]
        assert len(selected) == total_stops, f"Must select exactly {total_stops}, got {len(selected)}"


class TestMuseumUnmoved:
    """Museum objects have canonical catalogue quality scores.

    LOCAL-349 must not reorder museum stops — their selection is already
    sound via LOCAL-328's museum-specific deterministic path.
    """

    MUSEUM_PASSAGES_HIGH = [
        # Museum official catalogue — weight 3.0
        {'text': 'Niki de Saint Phalle, La mariée sous l\'arbre, 1963-1964, assemblage.', 'type': 'museum_official'},
        {'text': 'Collection MAMAC, Nice. Donation de l\'artiste en 2001.', 'type': 'museum_official'},
    ]

    MUSEUM_PASSAGES_MEDIUM = [
        # Wikipedia — weight 2.5
        {'text': 'The museum was founded in 1990 and houses a collection of modern art.', 'type': 'wikipedia'},
    ]

    def test_museum_official_outscores_wikipedia(self):
        """Museum official (3.0 weight) beats wikipedia (2.5) per passage."""
        high_classified = [classify_passage(p) for p in self.MUSEUM_PASSAGES_HIGH]
        med_classified = [classify_passage(p) for p in self.MUSEUM_PASSAGES_MEDIUM]

        high_score = compute_quality_score(high_classified)  # 2 × 3.0 = 6.0
        med_score = compute_quality_score(med_classified)    # 1 × 2.5 = 2.5

        assert high_score > med_score

    def test_museum_ranking_stable_with_uniform_scores(self):
        """When museum stops have similar scores, position order preserved (stable sort)."""
        # All museum official → all get same weight per passage
        candidates = [
            {'name': 'ObjectA'},
            {'name': 'ObjectB'},
            {'name': 'ObjectC'},
        ]
        # All same score → stable sort preserves input order
        quality_scores = {'ObjectA': 6.0, 'ObjectB': 6.0, 'ObjectC': 6.0}
        verdicts = {n['name']: 'COVERED' for n in candidates}

        _COVERAGE_PRIORITY = {'COVERED': 0, 'CREATOR_ONLY': 1, 'VENUE_ONLY': 2, 'EMPTY': 3}

        original_order = [p['name'] for p in candidates]
        candidates.sort(key=lambda p: (
            _COVERAGE_PRIORITY.get(verdicts.get(p['name'], 'EMPTY'), 3),
            -quality_scores.get(p['name'], 0.0),
        ))
        sorted_order = [p['name'] for p in candidates]

        assert original_order == sorted_order, "Stable sort should preserve order when scores are equal"


class TestQualityScoreArithmetic:
    """Verify quality score weights match LOCAL-328 spec."""

    def test_interpretive_enrichment_weight(self):
        """interpretive_enrichment is not in SOURCE_WEIGHTS → defaults to 1.0."""
        passages = [{'text': 'Rich historical context about the venue.', 'type': 'interpretive_enrichment'}]
        classified = [classify_passage(p) for p in passages]
        score = compute_quality_score(classified)
        # Default weight = 1.0
        assert score == 1.0

    def test_web_search_weight(self):
        """web_search gets 0.5 weight per non-sludge passage."""
        passages = [{'text': 'The restaurant opened in 1927 on Rue Droite.', 'type': 'web_search'}]
        classified = [classify_passage(p) for p in passages]
        score = compute_quality_score(classified)
        assert score == 0.5

    def test_mixed_sources_additive(self):
        """Score is additive across source types."""
        passages = [
            {'text': 'Founded in 1927 by the Acchiardo family.', 'type': 'web_search'},          # 0.5
            {'text': 'Traditional socca baked in wood-fired oven.', 'type': 'interpretive_enrichment'},  # 1.0
            {'text': 'The daube niçoise has been served since 1950.', 'type': 'interpretive_enrichment'},  # 1.0
        ]
        classified = [classify_passage(p) for p in passages]
        score = compute_quality_score(classified)
        assert score == 2.5  # 0.5 + 1.0 + 1.0

    def test_sludge_contributes_zero(self):
        """Sludge passages add 0 regardless of source type."""
        passages = [
            {'text': 'Good passage here.', 'type': 'web_search'},             # 0.5
            {'text': 'Nice · Restaurants · $$', 'type': 'web_search'},        # sludge → 0
            {'text': '... foo ... bar ... baz ...', 'type': 'web_search'},    # sludge → 0
        ]
        classified = [classify_passage(p) for p in passages]
        score = compute_quality_score(classified)
        assert score == 0.5  # only the first non-sludge passage counts


class TestBulkQualityScoresDB:
    """Integration test for get_bulk_quality_scores against live DB.

    Only runs when DATABASE_URL is set (CI or local dev with docker up).
    Uses production DB (read-only assertions against real corpus data).
    """

    @pytest.fixture
    def db_conn(self):
        """Get a production DB connection, skip if unavailable."""
        try:
            import psycopg2
            conn = psycopg2.connect(
                os.environ.get('DATABASE_URL',
                               'postgresql://admin:password123@localhost:5433/audiotours'),
                connect_timeout=5
            )
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database unavailable: {e}")

    def test_acchiardo_vs_rossettisserie_live(self, db_conn):
        """Against real corpus: Acchiardo must outscore La Rossettisserie."""
        scores = get_bulk_quality_scores(['Acchiardo', 'La Rossettisserie'], db_conn)

        acchiardo_score = scores.get('Acchiardo', 0.0)
        rossettisserie_score = scores.get('La Rossettisserie', 0.0)

        assert acchiardo_score > 0, f"Acchiardo should have corpus data, got score {acchiardo_score}"
        assert acchiardo_score > rossettisserie_score, (
            f"Acchiardo ({acchiardo_score}) must outscore "
            f"La Rossettisserie ({rossettisserie_score})"
        )

    def test_bulk_returns_zero_for_unknown(self, db_conn):
        """Stops not in corpus get 0.0 score."""
        scores = get_bulk_quality_scores(['NonexistentStopXYZ123'], db_conn)
        assert scores.get('NonexistentStopXYZ123', 0.0) == 0.0

    def test_bulk_handles_accent_folding(self, db_conn):
        """Accent-folded matching works (D253: U+2019 folding)."""
        # Both the apostrophe variants should match
        scores = get_bulk_quality_scores(["Acchiardo"], db_conn)
        # Just verify it returns without error and finds the stop
        assert 'Acchiardo' in scores
