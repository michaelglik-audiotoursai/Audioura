#!/usr/bin/env python3
"""
LOCAL-305: Unit tests for MISSING stop split into PIPELINE_LOST / UNAVAILABLE.

Tests:
1. PIPELINE_LOST classification path (verified stop not delivered)
2. UNAVAILABLE classification path (positive tier-1 exhaustion signal)
3. Cannot-tell default → PIPELINE_LOST
4. No gate_log → all missing default to PIPELINE_LOST
5. FABRICATED at −3.0 × share (operator-only, weight increase, LOCAL-309)
6. Coverage and quality reported separately
7. Coverage = 1.0 when all delivered (no missing stops)
8. Achievable count excludes UNAVAILABLE stops
9. Full tour (8/8) coverage = 1.0 and total unchanged
10. Quality normalisation against available passages
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tour_rubric_scorer import (
    StopAnalysis,
    TourScore,
    compute_score,
    classify_stop,
    score_tour_file,
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


class TestPipelineLostClassification:
    """A stop that was verified and then lost is PIPELINE_LOST."""

    def test_verified_stop_not_delivered_is_pipeline_lost(self):
        """If gate verified a stop but it's not in delivered stops → PIPELINE_LOST."""
        stops = [_make_stop(1, "Delivered Stop")]
        gate_log = [
            {'stop_title': 'Delivered Stop', 'verified': True, 'evidence': 'corpus', 'source': 'venue_corpus'},
            {'stop_title': 'Lost Stop', 'verified': True, 'evidence': 'wikipedia', 'source': 'geographic_tier1'},
        ]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=gate_log)

        assert ts.n_delivered == 1
        assert ts.n_requested == 2
        assert len(ts.missing_classifications) == 1
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    def test_pipeline_lost_weight_is_minus_1(self):
        """PIPELINE_LOST costs −1.0 × share, same as old MISSING."""
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            {'stop_title': 'Stop B', 'verified': True, 'evidence': 'x', 'source': 'y'},
        ]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=gate_log)

        share = 100.0 / 2
        # The missing stop penalty should be -1.0 * share = -50.0
        # per_stop_base[1] is the missing stop entry
        assert abs(ts.per_stop_base[1] - (-1.0 * share)) < 0.001

    def test_multiple_pipeline_lost(self):
        """Multiple verified-but-missing stops all classify as PIPELINE_LOST."""
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            {'stop_title': 'Stop B', 'verified': True, 'evidence': 'x', 'source': 'y'},
            {'stop_title': 'Stop C', 'verified': True, 'evidence': 'x', 'source': 'y'},
        ]
        ts = compute_score(stops, n_requested=3, venue_identity_facts=[], gate_log=gate_log)

        assert len(ts.missing_classifications) == 2
        assert all(c == 'PIPELINE_LOST' for c in ts.missing_classifications)


class TestUnavailableClassification:
    """A stop genuinely absent from the world (tier-1 empty) is UNAVAILABLE."""

    def test_exhausted_signal_without_search_is_pipeline_lost(self):
        """[LOCAL-309] Gate 'exhausted' flag alone → PIPELINE_LOST without live search."""
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            # This entry signals exhaustion but without venue_name no search runs
            {'stop_title': '', 'verified': False, 'evidence': '', 'source': '', 'exhausted': True},
        ]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=gate_log)

        assert len(ts.missing_classifications) == 1
        # [LOCAL-309] Without live search → PIPELINE_LOST
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    def test_unavailable_signal_flag_without_search_is_pipeline_lost(self):
        """[LOCAL-309] Gate 'unavailable' flag alone → PIPELINE_LOST without live search."""
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            {'stop_title': '', 'verified': False, 'evidence': '', 'source': '', 'unavailable': True},
        ]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=gate_log)

        # [LOCAL-309] Without venue_name → no search → PIPELINE_LOST
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'

    def test_unavailable_weight_is_zero_when_search_confirmed(self):
        """[LOCAL-309] UNAVAILABLE costs 0.0 × share when search-confirmed."""
        from unittest.mock import patch
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
        ]
        # Mock the search to return no candidates (confirms area is thin)
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts = compute_score(stops, n_requested=2, venue_identity_facts=[],
                             gate_log=gate_log, venue_name="Tiny Village, Nowhere")

        share = 100.0 / 2
        # per_stop_base[1] is the UNAVAILABLE penalty — now 0.0
        assert abs(ts.per_stop_base[1] - (0.0 * share)) < 0.001

    def test_unavailable_is_zero_when_search_confirmed(self):
        """[LOCAL-309] UNAVAILABLE IS zero cost when search-confirmed."""
        from unittest.mock import patch
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
        ]
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts = compute_score(stops, n_requested=2, venue_identity_facts=[],
                             gate_log=gate_log, venue_name="Tiny Place")

        # [LOCAL-309] UNAVAILABLE penalty IS zero
        assert ts.per_stop_base[1] == 0.0

    def test_mixed_pipeline_lost_and_unavailable(self):
        """Both classifications can appear together (with live search)."""
        from unittest.mock import patch
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            {'stop_title': 'Stop B', 'verified': True, 'evidence': 'x', 'source': 'y'},
        ]
        # Mock: search finds nothing (remaining shortfall = UNAVAILABLE)
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts = compute_score(stops, n_requested=3, venue_identity_facts=[],
                             gate_log=gate_log, venue_name="Tiny Village")

        assert len(ts.missing_classifications) == 2
        assert 'PIPELINE_LOST' in ts.missing_classifications
        assert 'UNAVAILABLE' in ts.missing_classifications


class TestCannotTellDefault:
    """When we cannot determine the cause, default to PIPELINE_LOST."""

    def test_no_gate_log_defaults_to_pipeline_lost(self):
        """Without gate_log, all missing stops are PIPELINE_LOST."""
        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(stops, n_requested=3, venue_identity_facts=[])

        assert len(ts.missing_classifications) == 2
        assert all(c == 'PIPELINE_LOST' for c in ts.missing_classifications)

    def test_none_gate_log_defaults_to_pipeline_lost(self):
        """Explicit None gate_log → all PIPELINE_LOST."""
        stops = [_make_stop(1, "Stop A")]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=None)

        assert ts.missing_classifications == ['PIPELINE_LOST']

    def test_unverified_without_exhausted_flag_is_pipeline_lost(self):
        """An unverified stop without the 'exhausted' flag → blame ourselves."""
        stops = [_make_stop(1, "Stop A")]
        gate_log = [
            {'stop_title': 'Stop A', 'verified': True, 'evidence': 'x', 'source': 'y'},
            # Unverified but no exhausted/unavailable signal — could be a real place
            # we failed to verify. Per spec: "cannot tell → PIPELINE_LOST"
            {'stop_title': 'Unknown Stop', 'verified': False, 'evidence': '', 'source': ''},
        ]
        ts = compute_score(stops, n_requested=2, venue_identity_facts=[], gate_log=gate_log)

        # The missing stop defaults to PIPELINE_LOST because we cannot tell
        assert ts.missing_classifications[0] == 'PIPELINE_LOST'


class TestFabricatedWeight:
    """FABRICATED stays operator-only and now costs −1.5 × share."""

    def test_fabricated_weight_is_minus_3_0(self):
        """[LOCAL-309] FABRICATED = −3.0 × share (3× worse than PIPELINE_LOST)."""
        stops = [_make_stop(1, "Fabricated Stop", classification='FABRICATED')]
        ts = compute_score(stops, n_requested=1, venue_identity_facts=[])

        share = 100.0 / 1
        assert abs(ts.per_stop_base[0] - (-3.0 * share)) < 0.001

    def test_fabricated_costs_more_than_pipeline_lost(self):
        """Fabrication is worse than omission — must cost more."""
        # Score a tour with 1 FABRICATED stop
        fab_stops = [_make_stop(1, "Fab Stop", classification='FABRICATED')]
        ts_fab = compute_score(fab_stops, n_requested=2, venue_identity_facts=[])

        # Score a tour with 0 stops (1 PIPELINE_LOST)
        empty_stops = [_make_stop(1, "Good Stop")]
        ts_lost = compute_score(empty_stops, n_requested=2, venue_identity_facts=[])

        # FABRICATED's penalty per slot is worse than PIPELINE_LOST
        share = 100.0 / 2
        fab_penalty = ts_fab.per_stop_base[0]        # -1.5 * share
        lost_penalty = ts_lost.per_stop_base[1]      # -1.0 * share
        assert fab_penalty < lost_penalty

    def test_fabricated_is_not_computable(self):
        """classify_stop() never returns FABRICATED — it's operator-only."""
        sa = _make_stop(1, "Test")
        # Even with terrible signals, classify_stop won't produce FABRICATED
        sa.distinct_fact_count = 0
        sa.fact_density = 0.0
        sa.generic_filler_fraction = 1.0
        sa.content_sentences = 10
        sa.contradicted_share = 0.0

        cls, evidence = classify_stop(sa)
        assert cls != 'FABRICATED'


class TestCoverageAndQuality:
    """Coverage and quality are reported separately."""

    def test_full_delivery_coverage_is_1(self):
        """8 delivered of 8 requested → coverage = 1.0."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 9)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        assert ts.coverage == 1.0
        assert ts.n_delivered == 8
        assert ts.n_achievable == 8

    def test_partial_delivery_coverage(self):
        """5 delivered of 8 requested, all PIPELINE_LOST → coverage = 5/8."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        assert abs(ts.coverage - 5.0/8.0) < 0.001
        assert ts.n_achievable == 8  # all PIPELINE_LOST, so achievable = requested

    def test_unavailable_adjusts_achievable(self):
        """UNAVAILABLE stops reduce the achievable count."""
        from unittest.mock import patch
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        gate_log = [
            {'stop_title': f'Stop {i}', 'verified': True, 'evidence': 'x', 'source': 'y'}
            for i in range(1, 6)
        ]
        # [LOCAL-309] Mock search to confirm area is thin → UNAVAILABLE
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts = compute_score(stops, n_requested=8, venue_identity_facts=[],
                             gate_log=gate_log, venue_name="Tiny Village")

        assert ts.n_achievable == 5  # 8 - 3 UNAVAILABLE
        assert abs(ts.coverage - 5.0/5.0) < 0.001  # 5 delivered / 5 achievable = 1.0

    def test_quality_positive_for_adequate_stops(self):
        """Quality > 0 for a tour with all ADEQUATE stops."""
        stops = [_make_stop(i, f"Stop {i}", classification='ADEQUATE') for i in range(1, 9)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        assert ts.quality > 0

    def test_quality_perfect_for_all_rich(self):
        """Quality = 1.0 for all RICH stops with no structural defects."""
        stops = [_make_stop(i, f"Stop {i}", classification='RICH') for i in range(1, 9)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        assert abs(ts.quality - 1.0) < 0.001

    def test_requested_count_still_visible(self):
        """The requested count is always visible on TourScore."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        # "5 of 8" must be visible
        assert ts.n_requested == 8
        assert ts.n_delivered == 5


class TestFullTourUnchanged:
    """A full 8/8 tour must have coverage=1.0 and total unchanged by LOCAL-305."""

    def test_8_of_8_coverage_is_1(self):
        """8/8 delivered → coverage 1.0, no missing classifications."""
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 9)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        assert ts.coverage == 1.0
        assert ts.missing_classifications == []
        assert ts.n_achievable == 8

    def test_no_missing_stops_no_penalty_change(self):
        """When all stops delivered, base_score is identical to pre-305 behaviour."""
        stops = [_make_stop(i, f"Stop {i}", classification='ADEQUATE') for i in range(1, 9)]
        ts = compute_score(stops, n_requested=8, venue_identity_facts=[])

        share = 100.0 / 8
        expected_base = 8 * 0.75 * share  # all ADEQUATE
        assert abs(ts.base_score - expected_base) < 0.001


class TestScoreDifference:
    """UNAVAILABLE tour scores better than PIPELINE_LOST tour — the whole point."""

    def test_unavailable_tour_scores_higher_than_pipeline_lost_tour(self):
        """5/8 with 3 UNAVAILABLE should score higher than 5/8 with 3 PIPELINE_LOST."""
        from unittest.mock import patch
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]

        # All PIPELINE_LOST (no gate_log, defaults to blaming ourselves)
        ts_lost = compute_score(stops, n_requested=8, venue_identity_facts=[])

        # 3 UNAVAILABLE (confirmed by search)
        gate_log = [
            {'stop_title': f'Stop {i}', 'verified': True, 'evidence': 'x', 'source': 'y'}
            for i in range(1, 6)
        ]
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts_unavail = compute_score(stops, n_requested=8, venue_identity_facts=[],
                                      gate_log=gate_log, venue_name="Tiny Village")

        # UNAVAILABLE tour scores higher because penalty is 0.0 vs −1.0
        assert ts_unavail.total_score > ts_lost.total_score

    def test_score_difference_magnitude(self):
        """[LOCAL-309] Difference: 3 × (1.0 - 0.0) × share = 3 × 1.0 × 12.5 = 37.5."""
        from unittest.mock import patch
        stops = [_make_stop(i, f"Stop {i}") for i in range(1, 6)]
        share = 100.0 / 8

        ts_lost = compute_score(stops, n_requested=8, venue_identity_facts=[])

        gate_log = [
            {'stop_title': f'Stop {i}', 'verified': True, 'evidence': 'x', 'source': 'y'}
            for i in range(1, 6)
        ]
        with patch('shortfall_search._search_for_candidates_wikipedia', return_value=([], "no results", "")), \
             patch('shortfall_search._search_for_candidates_wikidata', return_value=([], "no results", "")):
            ts_unavail = compute_score(stops, n_requested=8, venue_identity_facts=[],
                                      gate_log=gate_log, venue_name="Tiny Village")

        # [LOCAL-309] Expected difference: 3 stops × (1.0 - 0.0) × share = 3 × 12.5 = 37.5
        expected_diff = 3 * 1.0 * share
        actual_diff = ts_unavail.total_score - ts_lost.total_score
        assert abs(actual_diff - expected_diff) < 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
