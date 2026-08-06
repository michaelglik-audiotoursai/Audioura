#!/usr/bin/env python3
"""
LOCAL-309: Unit tests for verified-unavailable shortfall search.

Michael's ruling (2026-08-06):
  - FABRICATED: -3.0 × share (was -1.5)
  - PIPELINE_LOST: -1.0 × share (unchanged)
  - UNAVAILABLE, search-confirmed: 0.0 × share (was -0.15)
  - UNAVAILABLE, unverified: -1.0 × share (treat as PIPELINE_LOST)
  - On search failure → PIPELINE_LOST (never a free pass)

Tests:
1. FABRICATED weight = -3.0 × share (tripled)
2. UNAVAILABLE search-confirmed = 0.0 × share
3. PIPELINE_LOST = -1.0 × share (unchanged)
4. Search failure → PIPELINE_LOST (fail closed)
5. No venue_name → PIPELINE_LOST (cannot search)
6. Cache hit on repeat search (same area, same day)
7. Full 8/8 tour unaffected
8. Search is bounded (max 5 per tour)
9. Evidence is recorded for every verdict
10. Existence gate NOT weakened (fabricated still rejected)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from tour_rubric_scorer import (
    StopAnalysis,
    TourScore,
    compute_score,
    classify_stop,
    score_tour_file,
)
from shortfall_search import (
    search_for_shortfall,
    clear_cache,
    get_cache_stats,
    ShortfallVerdict,
    TourShortfallResult,
    MAX_QUERIES_PER_TOUR,
    QUERY_TIMEOUT_SECONDS,
)


def _make_stop(index, title, classification='ADEQUATE', groundedness=1.0):
    """Create a minimal StopAnalysis for testing compute_score."""
    sa = StopAnalysis(
        index=index,
        title=title,
        text="Test stop body text with some facts about history in 1888.",
        word_count=50,
        content_sentences=4,
        distinct_fact_count=3,
        fact_density=0.75,
        generic_filler_fraction=0.1,
        groundedness_fraction=groundedness,
    )
    sa.classification = classification
    sa.classification_evidence = "test fixture"
    return sa


@pytest.fixture(autouse=True)
def clear_shortfall_cache():
    """Clear the shortfall search cache before each test."""
    clear_cache()
    yield
    clear_cache()


# =============================================================================
# 1. FABRICATED weight = -3.0 × share
# =============================================================================

class TestFabricatedTripled:
    """FABRICATED now costs -3.0 × share (tripled from -1.5)."""

    def test_fabricated_weight_is_minus_3(self):
        """FABRICATED = -3.0 × share."""
        stops = [_make_stop(1, "Fabricated Stop", classification='FABRICATED')]
        ts = compute_score(stops, n_requested=1, venue_identity_facts=[])

        share = 100.0 / 1
        assert abs(ts.per_stop_base[0] - (-3.0 * share)) < 0.001

    def test_fabricated_costs_3x_pipeline_lost(self):
        """Fabrication costs exactly 3× what a pipeline loss costs."""
        share = 100.0 / 8

        # One FABRICATED stop in an 8-stop tour
        fab_stops = [_make_stop(1, "Fab", classification='FABRICATED')]
        ts_fab = compute_score(fab_stops, n_requested=8, venue_identity_facts=[])
        fab_penalty = ts_fab.per_stop_base[0]  # -3.0 * share

        # One PIPELINE_LOST in the same 8-stop tour (no gate_log, no venue_name)
        good_stops = [_make_stop(1, "Good")]
        ts_lost = compute_score(good_stops, n_requested=8, venue_identity_facts=[])
        lost_penalty = ts_lost.per_stop_base[1]  # -1.0 * share (first missing slot)

        # FABRICATED / PIPELINE_LOST = 3.0
        ratio = fab_penalty / lost_penalty
        assert abs(ratio - 3.0) < 0.001

    def test_fabricated_still_operator_only(self):
        """classify_stop() never returns FABRICATED."""
        sa = _make_stop(1, "Test")
        sa.distinct_fact_count = 0
        sa.fact_density = 0.0
        sa.generic_filler_fraction = 1.0
        sa.content_sentences = 10
        sa.contradicted_share = 0.0

        cls, _ = classify_stop(sa)
        assert cls != 'FABRICATED'


# =============================================================================
# 2. UNAVAILABLE search-confirmed = 0.0 × share
# =============================================================================

class TestUnavailableSearchConfirmed:
    """UNAVAILABLE with live search confirmation costs 0.0 × share."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_unavailable_search_confirmed_zero_cost(self, mock_wd, mock_wp):
        """When search finds nothing → UNAVAILABLE → 0.0 penalty."""
        # Mock: Wikipedia finds nothing
        mock_wp.return_value = ([], "searched: no results", "")
        # Mock: Wikidata finds nothing
        mock_wd.return_value = ([], "wikidata: no results", "")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="Remote Saharan Oasis, Algeria"
        )

        # The missing stop should be UNAVAILABLE with zero cost
        assert len(ts.missing_classifications) == 1
        assert ts.missing_classifications[0] == 'UNAVAILABLE'
        # per_stop_base[1] is the missing stop penalty
        assert ts.per_stop_base[1] == 0.0

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_unavailable_with_evidence(self, mock_wp):
        """UNAVAILABLE verdict must have recorded search evidence."""
        mock_wp.return_value = ([], "searched: 'notable landmarks saharan', got 0 results", "")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="Remote Saharan Oasis, Algeria"
        )

        # Evidence must be recorded
        assert len(ts.shortfall_evidence) == 1
        assert ts.shortfall_evidence[0]['classification'] == 'UNAVAILABLE'
        assert ts.shortfall_evidence[0]['search_query'] != ''
        assert ts.shortfall_evidence[0]['evidence'] != ''


# =============================================================================
# 3. PIPELINE_LOST = -1.0 × share (unchanged)
# =============================================================================

class TestPipelineLostUnchanged:
    """PIPELINE_LOST still costs -1.0 × share."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_pipeline_lost_when_search_finds_candidates(self, mock_wp):
        """When search finds real candidates → PIPELINE_LOST → full penalty."""
        mock_wp.return_value = (
            ["Eze Village", "Cap Ferrat", "Villa Ephrussi"],
            "searched: found 3 candidates",
            ""
        )

        stops = [_make_stop(1, "Stop A")]
        share = 100.0 / 2
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        assert ts.missing_classifications[0] == 'PIPELINE_LOST'
        assert abs(ts.per_stop_base[1] - (-1.0 * share)) < 0.001

    def test_pipeline_lost_without_venue_name(self):
        """No venue_name → cannot search → PIPELINE_LOST."""
        stops = [_make_stop(1, "Stop A")]
        share = 100.0 / 2
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name=None
        )

        assert ts.missing_classifications[0] == 'PIPELINE_LOST'
        assert abs(ts.per_stop_base[1] - (-1.0 * share)) < 0.001


# =============================================================================
# 4. Search failure → PIPELINE_LOST (fail closed)
# =============================================================================

class TestSearchFailureFailsClosed:
    """Infrastructure failure never buys a free pass."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_timeout_is_pipeline_lost(self, mock_wp):
        """Network timeout → PIPELINE_LOST, not UNAVAILABLE."""
        mock_wp.return_value = ([], "", "wikipedia_timeout")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_rate_limit_429_is_pipeline_lost(self, mock_wp):
        """HTTP 429 rate limit → PIPELINE_LOST."""
        mock_wp.return_value = ([], "", "wikipedia_429_rate_limited")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_connection_error_is_pipeline_lost(self, mock_wp):
        """Connection error → PIPELINE_LOST."""
        mock_wp.return_value = ([], "", "wikipedia_connection_error")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="Nice, France"
        )

        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_search_error_records_evidence(self, mock_wp):
        """Search failure still records evidence (auditable)."""
        mock_wp.return_value = ([], "", "wikipedia_429_rate_limited")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="Nice, France"
        )

        assert len(ts.shortfall_evidence) == 1
        assert 'rate_limited' in ts.shortfall_evidence[0]['search_error']


# =============================================================================
# 5. No venue_name → PIPELINE_LOST
# =============================================================================

class TestNoVenueName:
    """Without venue_name, search cannot run → PIPELINE_LOST for all."""

    def test_no_venue_name_no_gate_log(self):
        """Missing venue_name and gate_log → all PIPELINE_LOST."""
        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=3, venue_identity_facts=[],
            venue_name=None
        )

        assert len(ts.missing_classifications) == 2
        assert all(c == 'PIPELINE_LOST' for c in ts.missing_classifications)

    def test_empty_venue_name_treated_as_none(self):
        """Empty string venue_name → same as None."""
        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name=""
        )

        # Empty string is falsy → no search runs
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'


# =============================================================================
# 6. Cache hit on repeat search
# =============================================================================

class TestCaching:
    """Two tours of the same area on the same day must not both pay."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_cache_hit_on_repeat(self, mock_wd, mock_wp):
        """Second search for same area reuses cached verdict."""
        mock_wp.return_value = ([], "no results", "")
        mock_wd.return_value = ([], "no results", "")

        # First call
        result1 = search_for_shortfall(
            venue_name="Remote Island, Pacific",
            n_requested=5,
            delivered_titles=["Stop A", "Stop B"],
        )
        assert result1.cache_hits == 0
        assert mock_wp.call_count == 1

        # Second call — should hit cache
        result2 = search_for_shortfall(
            venue_name="Remote Island, Pacific",
            n_requested=5,
            delivered_titles=["Stop A", "Stop B"],
        )
        assert result2.cache_hits == 3  # 3 missing stops
        # Wikipedia NOT called again
        assert mock_wp.call_count == 1

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_cache_stats_populated(self, mock_wp):
        """Cache stats reflect stored entries."""
        mock_wp.return_value = (["Real Place"], "found 1", "")

        search_for_shortfall(
            venue_name="Nice, France",
            n_requested=5,
            delivered_titles=["Stop A"],
        )

        stats = get_cache_stats()
        assert stats['entries'] >= 1


# =============================================================================
# 7. Full 8/8 tour unaffected
# =============================================================================

class TestFullTourUnaffected:
    """A tour delivering all requested stops is not affected by LOCAL-309."""

    def test_8_of_8_no_search_triggered(self):
        """8/8 delivery → no search, no shortfall evidence."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 9)]
        ts = compute_score(
            stops, n_requested=8, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        assert ts.n_delivered == 8
        assert ts.missing_classifications == []
        assert ts.shortfall_evidence == []
        assert ts.coverage == 1.0

    def test_real_8stop_tour_unchanged(self):
        """Score the real 8-stop museum tour — must be unchanged."""
        ts = score_tour_file(
            'tours/LOCAL262_asian_arts_8stop_restored.txt', 8,
            venue_name="Musee des Arts Asiatiques (Asian Art Museum), Nice, France"
        )
        assert ts.n_delivered == 8
        assert ts.coverage == 1.0
        assert ts.missing_classifications == []
        # Score should be positive and reasonable
        assert ts.total_score > 50


# =============================================================================
# 8. Search is bounded
# =============================================================================

class TestSearchBounds:
    """Search is capped at MAX_QUERIES_PER_TOUR."""

    def test_max_queries_constant(self):
        """MAX_QUERIES_PER_TOUR is 5."""
        assert MAX_QUERIES_PER_TOUR == 5

    def test_timeout_constant(self):
        """QUERY_TIMEOUT_SECONDS is 10."""
        assert QUERY_TIMEOUT_SECONDS == 10

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_many_missing_stops_bounded(self, mock_wd, mock_wp):
        """Even with 10 missing stops, queries are bounded."""
        mock_wp.return_value = ([], "no results", "")
        mock_wd.return_value = ([], "no results", "")

        result = search_for_shortfall(
            venue_name="Tiny Village, Nowhere",
            n_requested=15,
            delivered_titles=["Stop A", "Stop B", "Stop C", "Stop D", "Stop E"],
        )

        # All 10 missing slots get verdicts (via single search + replication)
        assert len(result.verdicts) == 10
        # But total queries are bounded
        assert result.total_queries <= MAX_QUERIES_PER_TOUR


# =============================================================================
# 9. Evidence is recorded for every verdict
# =============================================================================

class TestEvidenceRecorded:
    """A zero-cost UNAVAILABLE with no recorded search is a bug."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_unavailable_has_evidence(self, mock_wd, mock_wp):
        """Every UNAVAILABLE verdict has non-empty evidence."""
        mock_wp.return_value = ([], "searched: 'notable landmarks tiny', got 0 results", "")
        mock_wd.return_value = ([], "wikidata searched: 'tiny landmark', got 0 results", "")

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=3, venue_identity_facts=[],
            venue_name="Tiny Village, Nowhere"
        )

        for ev in ts.shortfall_evidence:
            if ev['classification'] == 'UNAVAILABLE':
                assert ev['evidence'] != '', "UNAVAILABLE must have evidence"
                assert ev['search_query'] != '', "UNAVAILABLE must record what was searched"

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_pipeline_lost_has_evidence(self, mock_wp):
        """PIPELINE_LOST from search also records what was found."""
        mock_wp.return_value = (
            ["Villa Ephrussi", "Cap Ferrat Lighthouse"],
            "searched: 'notable landmarks riviera', found 2",
            ""
        )

        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        assert len(ts.shortfall_evidence) == 1
        ev = ts.shortfall_evidence[0]
        assert ev['classification'] == 'PIPELINE_LOST'
        assert len(ev['candidates_found']) >= 1


# =============================================================================
# 10. Existence gate NOT weakened
# =============================================================================

class TestExistenceGateNotWeakened:
    """Shortfall search does NOT weaken the existence gate."""

    def test_fabricated_place_still_fails_gate(self):
        """A fabricated place has no Wikipedia article — gate still rejects it.
        
        This test verifies the conceptual separation: shortfall_search is for
        scoring MISSING stops, not for verifying whether a proposed stop is real.
        The existence gate (stop_existence_gate.py) is unchanged.
        """
        # The shortfall search finds candidates in an area — it doesn't verify
        # individual stops. A fabricated stop that reaches the scorer as FABRICATED
        # (operator override) still costs -3.0 × share.
        stops = [_make_stop(1, "Fake Museum That Doesn't Exist", classification='FABRICATED')]
        ts = compute_score(
            stops, n_requested=1, venue_identity_facts=[],
            venue_name="Nice, France"
        )

        share = 100.0 / 1
        assert abs(ts.per_stop_base[0] - (-3.0 * share)) < 0.001

    def test_unverified_shortfall_is_not_free(self):
        """Without search confirmation, shortfall is NOT free — it's PIPELINE_LOST.
        
        This is the inversion of incentive: it is now cheaper to SEARCH than to
        assume. An unverified UNAVAILABLE is treated as our failure.
        """
        # Simulate: gate_log says shortfall happened but no search confirms it
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            # Unverified, no exhausted flag, no search
            {'stop_title': 'Missing', 'verified': False, 'evidence': '', 'source': ''},
        ]
        # No venue_name → cannot search → PIPELINE_LOST
        ts = compute_score(
            stops, n_requested=2, venue_identity_facts=[],
            gate_log=gate_log, venue_name=None
        )

        # Must be PIPELINE_LOST, not UNAVAILABLE
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'
        share = 100.0 / 2
        assert abs(ts.per_stop_base[1] - (-1.0 * share)) < 0.001


# =============================================================================
# Integration: score difference between rich and thin areas
# =============================================================================

class TestScoreDifference:
    """Tours in rich vs thin areas should score differently."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    def test_rich_area_shortfall_penalised(self, mock_wp):
        """5/8 in a rich area (search finds candidates) → penalised."""
        mock_wp.return_value = (
            ["Eze Village", "Cap Ferrat", "Villa Ephrussi"],
            "found 3 candidates",
            ""
        )

        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        ts = compute_score(
            stops, n_requested=8, venue_identity_facts=[],
            venue_name="French Riviera walking area"
        )

        # All missing are PIPELINE_LOST → full penalty
        assert all(c == 'PIPELINE_LOST' for c in ts.missing_classifications)
        share = 100.0 / 8
        expected_penalty = 3 * (-1.0 * share)  # -37.5
        missing_penalty = sum(ts.per_stop_base[5:])
        assert abs(missing_penalty - expected_penalty) < 0.001

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_thin_area_shortfall_not_penalised(self, mock_wd, mock_wp):
        """5/8 in a thin area (search finds nothing) → no penalty."""
        mock_wp.return_value = ([], "no results", "")
        mock_wd.return_value = ([], "no results", "")

        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        ts = compute_score(
            stops, n_requested=8, venue_identity_facts=[],
            venue_name="Tiny Remote Village, Sahara"
        )

        # All missing are UNAVAILABLE → zero penalty
        assert all(c == 'UNAVAILABLE' for c in ts.missing_classifications)
        missing_penalty = sum(ts.per_stop_base[5:])
        assert missing_penalty == 0.0

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_rich_area_scores_lower_than_thin_area(self, mock_wd_thin, mock_wp_thin):
        """Same delivery count: rich area (penalised) < thin area (not penalised)."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]

        # Rich area — search finds candidates
        with patch('shortfall_search._search_for_candidates_wikipedia',
                   return_value=(["Found Place"], "found 1", "")):
            ts_rich = compute_score(
                stops, n_requested=8, venue_identity_facts=[],
                venue_name="French Riviera walking area"
            )

        # Thin area — search finds nothing
        clear_cache()
        mock_wp_thin.return_value = ([], "no results", "")
        mock_wd_thin.return_value = ([], "no results", "")
        ts_thin = compute_score(
            stops, n_requested=8, venue_identity_facts=[],
            venue_name="Tiny Remote Village, Sahara"
        )

        assert ts_thin.total_score > ts_rich.total_score


# =============================================================================
# Cost measurement
# =============================================================================

class TestCostMeasurement:
    """Cost per tour must be reported."""

    @patch('shortfall_search._search_for_candidates_wikipedia')
    @patch('shortfall_search._search_for_candidates_wikidata')
    def test_cost_is_zero_for_free_apis(self, mock_wd, mock_wp):
        """Wikipedia/Wikidata APIs are free — cost = $0."""
        mock_wp.return_value = ([], "no results", "")
        mock_wd.return_value = ([], "no results", "")

        result = search_for_shortfall(
            venue_name="Test Area",
            n_requested=5,
            delivered_titles=["Stop A"],
        )

        assert result.cost_usd == 0.0

    def test_full_tour_no_cost(self):
        """A tour delivering N of N costs nothing extra."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 9)]
        ts = compute_score(
            stops, n_requested=8, venue_identity_facts=[],
            venue_name="French Riviera"
        )

        # No search triggered → no cost
        assert ts.shortfall_evidence == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
