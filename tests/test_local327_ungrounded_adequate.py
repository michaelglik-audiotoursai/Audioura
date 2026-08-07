#!/usr/bin/env python3
"""tests/test_local327_ungrounded_adequate.py — LOCAL-327: Ungrounded ADEQUATE ceiling.

Tests that:
1. A stop with zero corpus passages and adequate density cannot reach ADEQUATE
   when corpus_lookup_attempted is True.
2. A stop WITH corpus passages reaching ADEQUATE is unaffected.
3. A stop without corpus lookup attempted (corpus_data=None) is unaffected.
4. The ceiling never pushes below THIN (no penalty for absence of corpus).
5. RICH is also capped for zero-corpus stops.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import (
    classify_stop,
    compute_score,
    score_tour_file,
    StopAnalysis,
    RICH_MIN_GROUNDEDNESS,
    ADEQUATE_MIN_FACTS,
    ADEQUATE_MIN_DENSITY,
    RICH_MIN_FACTS,
    RICH_MIN_DENSITY,
)


def _make_stop(
    facts=5,
    density=0.50,
    filler=0.15,
    groundedness=1.0,
    corpus_available=False,
    corpus_lookup_attempted=True,
):
    """Helper to build a StopAnalysis with controlled signals."""
    sa = StopAnalysis(index=1, title='Test Stop', text='...')
    sa.distinct_fact_count = facts
    sa.content_sentences = max(1, int(facts / density)) if density > 0 else 10
    sa.fact_density = density
    sa.generic_filler_fraction = filler
    sa.groundedness_fraction = groundedness
    sa.contradicted_share = 0.0
    sa.corpus_available = corpus_available
    sa.corpus_lookup_attempted = corpus_lookup_attempted
    return sa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Zero corpus → capped at ADEQUATE (LEAD decision, LOCAL-331 bounce)
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroCorpusCap:
    """A stop with zero corpus passages caps at ADEQUATE when lookup was attempted.
    
    [LOCAL-331 bounce] LEAD decision: unmeasured stops cap at ADEQUATE, not THIN.
    "We hold no sources" is about our corpus, not about the venue (D162).
    Absence of a check is not evidence of fabrication. A stop we cannot verify
    should not reach RICH, but should not be penalised below ADEQUATE.
    """

    def test_adequate_metrics_zero_corpus_stays_adequate(self):
        """Stop meets ADEQUATE criteria but has no corpus → stays ADEQUATE."""
        sa = _make_stop(
            facts=5,
            density=0.50,
            filler=0.15,
            corpus_available=False,
            corpus_lookup_attempted=True,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE', f"Expected ADEQUATE, got {cls}"
        assert 'no corpus passages' in evidence
        assert 'unverified' in evidence

    def test_rich_metrics_zero_corpus_capped_to_adequate(self):
        """Stop meets RICH criteria but has no corpus → ADEQUATE.

        [LOCAL-331 bounce] LEAD decision: RICH is capped to ADEQUATE (not THIN).
        An unmeasured stop cannot demonstrate RICH quality but is not penalised
        for our own harvesting backlog.
        """
        sa = _make_stop(
            facts=6,
            density=0.70,
            filler=0.10,
            corpus_available=False,
            corpus_lookup_attempted=True,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE', f"Expected ADEQUATE, got {cls}"
        assert 'capped' in evidence
        assert 'no corpus passages' in evidence

    def test_five_facts_zero_corpus_is_adequate(self):
        """The exact scenario from the task: 5 facts, 0 corpus → ADEQUATE.

        [LOCAL-331 bounce] Previously capped to THIN. LEAD changed to ADEQUATE.
        'Robe de prêtre taoïste' and 'Masque du vieillard kojô' had 5 facts
        each with zero corpus. They cap at ADEQUATE now, not THIN.
        """
        sa = _make_stop(
            facts=5,
            density=0.40,
            filler=0.20,
            corpus_available=False,
            corpus_lookup_attempted=True,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'
        assert 'no corpus passages' in evidence


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Grounded ADEQUATE is unaffected
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundedAdequateUnaffected:
    """A well-grounded ADEQUATE stop (with corpus) remains ADEQUATE."""

    def test_adequate_with_corpus_stays_adequate(self):
        """Stop meets ADEQUATE criteria and HAS corpus → ADEQUATE."""
        sa = _make_stop(
            facts=5,
            density=0.50,
            filler=0.15,
            corpus_available=True,
            corpus_lookup_attempted=True,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'
        assert 'capped' not in evidence

    def test_rich_with_corpus_stays_rich(self):
        """Stop meets RICH criteria and has corpus with high groundedness → RICH."""
        sa = _make_stop(
            facts=6,
            density=0.70,
            filler=0.10,
            groundedness=0.80,
            corpus_available=True,
            corpus_lookup_attempted=True,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'RICH'
        assert 'capped' not in evidence


# ═══════════════════════════════════════════════════════════════════════════════
# 3. No corpus lookup → no ceiling applied
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoLookupNoEffect:
    """When corpus_data was not provided (no lookup attempted), no ceiling."""

    def test_adequate_without_lookup_stays_adequate(self):
        """No corpus lookup attempted → ADEQUATE classification preserved."""
        sa = _make_stop(
            facts=5,
            density=0.50,
            filler=0.15,
            corpus_available=False,
            corpus_lookup_attempted=False,  # No lookup attempted
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'

    def test_rich_without_lookup_stays_rich(self):
        """No corpus lookup attempted → RICH classification preserved."""
        sa = _make_stop(
            facts=6,
            density=0.70,
            filler=0.10,
            corpus_available=False,
            corpus_lookup_attempted=False,
        )
        cls, evidence = classify_stop(sa)
        assert cls == 'RICH'


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Never pushes below THIN
# ═══════════════════════════════════════════════════════════════════════════════

class TestNeverBelowThin:
    """Absence of corpus is not a penalty — caps but never pushes below THIN."""

    def test_thin_stop_stays_thin(self):
        """A stop that's already THIN is not pushed lower."""
        sa = _make_stop(
            facts=1,
            density=0.10,
            filler=0.60,
            corpus_available=False,
            corpus_lookup_attempted=True,
        )
        cls, _ = classify_stop(sa)
        assert cls == 'THIN'

    def test_cap_never_produces_fabricated(self):
        """No-corpus never produces FABRICATED — that's an operator judgement."""
        sa = _make_stop(
            facts=5,
            density=0.50,
            filler=0.15,
            corpus_available=False,
            corpus_lookup_attempted=True,
        )
        cls, _ = classify_stop(sa)
        assert cls != 'FABRICATED'
        assert cls != 'CONTRADICTED'


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Score impact — RICH capped to ADEQUATE costs 0.25 × share
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreImpact:
    """Verify the numerical score impact of the ceiling."""

    def test_score_drops_for_unverified_stop(self):
        """A 1-stop tour: RICH → ADEQUATE costs 25 points.

        RICH weight = 1.0 × share = 100.0
        ADEQUATE weight = 0.75 × share = 75.0
        Difference = 25 points
        
        [LOCAL-331 bounce] Updated from ADEQUATE→THIN (25pt drop) to RICH→ADEQUATE
        (25pt drop). The cap is now at ADEQUATE, not THIN.
        """
        # With corpus → RICH (100 points base, given high enough density)
        sa_grounded = _make_stop(
            facts=6, density=0.70, filler=0.10,
            groundedness=0.80,
            corpus_available=True, corpus_lookup_attempted=True,
        )
        sa_grounded.classification, sa_grounded.classification_evidence = classify_stop(sa_grounded)
        ts_grounded = compute_score([sa_grounded], n_requested=1, venue_identity_facts=[])

        # Without corpus → ADEQUATE (75 points base)
        sa_unverified = _make_stop(
            facts=6, density=0.70, filler=0.10,
            corpus_available=False, corpus_lookup_attempted=True,
        )
        sa_unverified.classification, sa_unverified.classification_evidence = classify_stop(sa_unverified)
        ts_unverified = compute_score([sa_unverified], n_requested=1, venue_identity_facts=[])

        # Score should drop
        assert ts_grounded.base_score > ts_unverified.base_score
        assert ts_grounded.base_score - ts_unverified.base_score == pytest.approx(25.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Integration with score_tour_file
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegrationScoreTourFile:
    """Integration test: score_tour_file with corpus_data marks stops correctly."""

    def test_corpus_data_triggers_ceiling(self):
        """When corpus_data is provided, stops without entries are capped at ADEQUATE."""
        tour_text = (
            "Stop 1: Grounded Stop\n"
            "Claude Monet painted magnificent water lilies here in 1899. "
            "Pierre-Auguste Renoir visited in 1900 and admired the garden. "
            "The Japanese bridge was designed by architect Hans Meyer in 1895. "
            "Louis Leroy wrote criticism of the garden scene. "
            "Gustave Caillebotte donated funds for the renovation in 1894.\n"
            "\n"
            "Stop 2: Ungrounded Stop\n"
            "Henri Matisse worked in this studio from 1917 to 1954. "
            "Pablo Picasso visited Matisse here in 1946 and discussed technique. "
            "Raoul Dufy painted nearby coastline scenes in 1928. "
            "André Derain established a studio in the neighbourhood around 1905. "
            "The building was constructed by Pierre Lefebvre in 1880.\n"
        )
        # corpus_data has passages for Stop 1 but NOT Stop 2
        corpus_data = {
            'Grounded Stop': {
                'passages': ['Monet painted water lilies in 1899.', 'Renoir admired the garden.']
            }
            # 'Ungrounded Stop' is deliberately absent → no corpus
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(tour_text)
            filepath = f.name

        try:
            ts = score_tour_file(filepath, 2, corpus_data=corpus_data)
            # Stop 1 should have corpus_available = True, Stop 2 = False
            assert ts.stops[0].corpus_lookup_attempted is True
            assert ts.stops[1].corpus_lookup_attempted is True
            assert ts.stops[1].corpus_available is False
            # [LOCAL-331 bounce] Stop 2 capped at ADEQUATE (not THIN)
            assert ts.stops[1].classification == 'ADEQUATE'
            assert 'no corpus passages' in ts.stops[1].classification_evidence
        finally:
            os.unlink(filepath)

    def test_no_corpus_data_no_ceiling(self):
        """When corpus_data is None (not provided), no ceiling is applied."""
        tour_text = (
            "Stop 1: Dense Stop\n"
            "Claude Monet painted water lilies in 1899. "
            "Pierre-Auguste Renoir visited in 1900. "
            "The Japanese bridge was designed by architect Hans Meyer in 1895. "
            "Louis Leroy wrote criticism in 1874. "
            "Gustave Caillebotte donated funds in 1894.\n"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(tour_text)
            filepath = f.name

        try:
            # No corpus_data → no ceiling
            ts = score_tour_file(filepath, 1)
            # corpus_lookup_attempted should be False
            assert ts.stops[0].corpus_lookup_attempted is False
            # Classification should be based on density/facts alone
            # (ADEQUATE or higher if density is sufficient)
        finally:
            os.unlink(filepath)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Integration with evaluate() — the default scoring path
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluatePathCeiling:
    """[LOCAL-327 bounce fix] The ceiling must fire in evaluate() when conn is provided."""

    def test_evaluate_with_corpus_data_applies_ceiling(self):
        """evaluate() with corpus_data applies the ceiling before classification."""
        from tour_evaluator import evaluate

        tour_text = (
            "Step-by-Step Audio Guided Tour: Test Venue\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Grounded Stop\n\n"
            "Claude Monet painted magnificent water lilies here in 1899. "
            "Pierre-Auguste Renoir visited in 1900 and admired the garden. "
            "The Japanese bridge was designed by architect Hans Meyer in 1895. "
            "Louis Leroy wrote criticism of the garden scene. "
            "Gustave Caillebotte donated funds for the renovation in 1894.\n\n"
            "Stop 2: Ungrounded Stop\n\n"
            "Henri Matisse worked in this studio from 1917 to 1954. "
            "Pablo Picasso visited Matisse here in 1946 and discussed technique. "
            "Raoul Dufy painted nearby coastline scenes in 1928. "
            "André Derain established a studio in the neighbourhood around 1905. "
            "The building was constructed by Pierre Lefebvre in 1880.\n"
        )
        # corpus_data has passages for Stop 1 but NOT Stop 2
        corpus_data = {
            'Grounded Stop': {
                'passages': ['Monet painted water lilies in 1899.', 'Renoir admired the garden.']
            }
            # 'Ungrounded Stop' is deliberately absent → no corpus
        }

        # With corpus_data, evaluate() should apply the ceiling
        evaluation = evaluate(tour_text, 2, corpus_data=corpus_data)
        assert evaluation is not None

        # [LOCAL-331 bounce] Stop 2 caps at ADEQUATE (not THIN)
        stop2 = evaluation.per_stop[1]
        assert stop2['classification'] == 'ADEQUATE', \
            f"Expected ADEQUATE, got {stop2['classification']}"

    def test_evaluate_without_conn_or_corpus_no_ceiling(self):
        """evaluate() without conn or corpus_data does NOT apply ceiling."""
        from tour_evaluator import evaluate

        tour_text = (
            "Step-by-Step Audio Guided Tour: Test Venue\n"
            "Tour-Category: museum\n\n"
            "Stop 1: Dense Stop\n\n"
            "Claude Monet painted magnificent water lilies here in 1899. "
            "Pierre-Auguste Renoir visited in 1900 and admired the garden. "
            "The Japanese bridge was designed by architect Hans Meyer in 1895. "
            "Louis Leroy wrote criticism of the garden scene. "
            "Gustave Caillebotte donated funds for the renovation in 1894.\n"
        )

        # Without corpus_data or conn, no ceiling is applied
        evaluation = evaluate(tour_text, 1)
        assert evaluation is not None
        # Stop should classify on density/facts alone (ADEQUATE or higher)
        stop1 = evaluation.per_stop[0]
        assert stop1['classification'] in ('ADEQUATE', 'RICH'), \
            f"Expected ADEQUATE or RICH without ceiling, got {stop1['classification']}"
