#!/usr/bin/env python3
"""tests/test_local331_groundedness_default.py — LOCAL-331: Groundedness default bug.

Tests that groundedness_fraction defaults to None (unmeasured), NOT 1.0.

The finding: when no corpus is loaded, groundedness previously defaulted to
1.00 — "perfectly grounded". An unchecked stop was scored as though every
claim were verified. This inflated all scores reported to Michael.

These tests verify:
  1. StopAnalysis.groundedness_fraction defaults to None, not 1.0
  2. classify_stop with None groundedness does not apply groundedness ceiling
  3. classify_stop with None groundedness reports "unmeasured" in evidence
  4. A stop with corpus_lookup_attempted=True but corpus_available=False
     and groundedness=None is correctly handled (capped by LOCAL-327 logic)
  5. score_tour_file auto-loads corpus from DB when available
  6. evaluate() reports None for unmeasured groundedness in per_stop data
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import (
    StopAnalysis,
    classify_stop,
    score_tour_file,
    RICH_MIN_GROUNDEDNESS,
)
from tour_evaluator import evaluate


# ═══════════════════════════════════════════════════════════════════════════════
# 1. The default is None (unmeasured), not 1.0
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundednessDefault:
    """The default groundedness must be None (unmeasured), not 1.0."""

    def test_default_is_none(self):
        """StopAnalysis.groundedness_fraction defaults to None, not 1.0."""
        sa = StopAnalysis(index=1, title='Test', text='some text')
        # LOCAL-331: This MUST be None. The old default was 1.0, which was
        # the root cause of inflated scores.
        assert sa.groundedness_fraction is None

    def test_default_is_not_one(self):
        """Explicitly verify the old default (1.0) is gone."""
        sa = StopAnalysis(index=1, title='Test', text='some text')
        assert sa.groundedness_fraction != 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. classify_stop handles None groundedness correctly
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifyStopNoneGroundedness:
    """classify_stop with None (unmeasured) groundedness."""

    def _make_rich_stop(self, groundedness=None):
        """Helper: a stop that meets RICH criteria on density/facts."""
        sa = StopAnalysis(index=1, title='Test Stop', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = groundedness
        return sa

    def test_none_groundedness_no_ceiling(self):
        """None groundedness does NOT trigger the RICH ceiling.
        
        Rationale: "we did not check" cannot penalise. The ceiling only fires
        when we measured and found the stop below floor.
        """
        sa = self._make_rich_stop(groundedness=None)
        # No corpus lookup attempted — this is the pure no-check path
        cls, _ = classify_stop(sa)
        assert cls == 'RICH'

    def test_measured_below_floor_caps_to_adequate(self):
        """A MEASURED groundedness below floor still caps RICH → ADEQUATE."""
        sa = self._make_rich_stop(groundedness=0.30)
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'
        assert 'capped by groundedness floor' in evidence

    def test_measured_above_floor_stays_rich(self):
        """A MEASURED groundedness above floor stays RICH."""
        sa = self._make_rich_stop(groundedness=0.80)
        cls, _ = classify_stop(sa)
        assert cls == 'RICH'

    def test_evidence_says_unmeasured(self):
        """Evidence string says 'unmeasured' when groundedness is None."""
        sa = self._make_rich_stop(groundedness=None)
        _, evidence = classify_stop(sa)
        assert 'unmeasured' in evidence

    def test_evidence_says_percentage_when_measured(self):
        """Evidence string shows percentage when groundedness is measured."""
        sa = self._make_rich_stop(groundedness=0.50)
        _, evidence = classify_stop(sa)
        assert '50%' in evidence
        assert 'unmeasured' not in evidence


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Interaction with LOCAL-327 corpus_lookup_attempted logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestLocal327InteractionWithNone:
    """LOCAL-327 caps (lookup attempted, no corpus) still work with None default."""

    def test_lookup_attempted_no_corpus_caps_rich_to_adequate(self):
        """When lookup was attempted but no corpus found, RICH is capped to ADEQUATE.
        
        [LOCAL-331 bounce] LEAD decision: unmeasured stops cap at ADEQUATE,
        matching LOCAL-291. "We hold no sources" is about our corpus, not the
        venue (D162). Absence of a check is not evidence of fabrication.
        """
        sa = StopAnalysis(index=1, title='Test', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = None  # No measurement possible
        sa.corpus_lookup_attempted = True
        sa.corpus_available = False
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'
        assert 'no corpus passages' in evidence

    def test_no_lookup_no_cap(self):
        """When no lookup was attempted, no cap is applied. groundedness=None is inert."""
        sa = StopAnalysis(index=1, title='Test', text='...')
        sa.distinct_fact_count = 5
        sa.content_sentences = 6
        sa.fact_density = 0.83
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = None
        sa.corpus_lookup_attempted = False
        sa.corpus_available = False
        cls, _ = classify_stop(sa)
        assert cls == 'RICH'


# ═══════════════════════════════════════════════════════════════════════════════
# 4. evaluate() reports None for unmeasured groundedness
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluateReportsUnmeasured:
    """evaluate() per_stop output distinguishes unmeasured from measured."""

    def test_no_corpus_reports_none_groundedness(self):
        """Without conn or corpus_data, per_stop groundedness is None."""
        tour_text = """Step-by-Step Audio Guided Tour: Test Museum
Stop 1: A Famous Painting
This painting was created in 1888 by Claude Monet. It depicts the harbor of Antibes at dawn. The canvas measures 65 by 92 centimeters. It was acquired by the museum in 1923 from a private collection.
"""
        result = evaluate(tour_text, 1)
        assert result is not None
        assert result.per_stop[0]['groundedness'] is None

    def test_with_corpus_reports_measured_value(self):
        """With corpus_data, per_stop groundedness is a float."""
        tour_text = """Step-by-Step Audio Guided Tour: Test Museum
Stop 1: A Famous Painting
This painting was created in 1888 by Claude Monet. It depicts the harbor of Antibes at dawn. The canvas measures 65 by 92 centimeters. It was acquired by the museum in 1923 from a private collection.
"""
        # Provide corpus that grounds some claims
        corpus_data = {
            'A Famous Painting': {
                'passages': ['Claude Monet painted this view of Antibes harbor in 1888.'],
                'sources': [],
            }
        }
        result = evaluate(tour_text, 1, corpus_data=corpus_data)
        assert result is not None
        groundedness = result.per_stop[0]['groundedness']
        assert groundedness is not None
        assert isinstance(groundedness, float)
        assert 0.0 <= groundedness <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. score_tour_file auto-loads corpus (integration test)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreTourFileAutoLoadsCorpus:
    """score_tour_file attempts DB corpus load when corpus_data is not provided."""

    @pytest.fixture
    def museum_tour_file(self, tmp_path):
        """Create a minimal tour file with a venue that has corpus in DB."""
        content = """Step-by-Step Audio Guided Tour: Asian Arts Museum, Nice
Stop 1: Statue de Bouddha
This golden Buddha statue dates from the 14th century. It was crafted in Thailand during the Sukhothai period. The statue stands 2 meters tall and weighs approximately 500 kilograms.
"""
        p = tmp_path / "test_tour.txt"
        p.write_text(content, encoding='utf-8')
        return str(p)

    def test_auto_loads_corpus_when_db_available(self, museum_tour_file):
        """When no corpus_data is passed, score_tour_file tries to load from DB.
        
        If the DB is reachable and has corpus for this venue, groundedness
        should be a measured value (not None).
        """
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))
            from db_connection import check_db_available
            if not check_db_available():
                pytest.skip("DB not available")
        except (ImportError, SystemExit):
            pytest.skip("DB not available")

        ts = score_tour_file(museum_tour_file, 1)
        # The stop should have had corpus_lookup_attempted = True
        # (because score_tour_file auto-loaded corpus)
        stop = ts.stops[0]
        assert stop.corpus_lookup_attempted is True

    def test_no_corpus_data_no_db_reports_unmeasured(self):
        """Without corpus_data AND no DB, groundedness stays None."""
        content = """Step-by-Step Audio Guided Tour: Nonexistent Museum on Mars
Stop 1: A Martian Rock
This rock was formed 4 billion years ago during the Noachian period.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(content)
            filepath = f.name

        try:
            # Even with DB available, "Nonexistent Museum on Mars" has no corpus
            ts = score_tour_file(filepath, 1)
            stop = ts.stops[0]
            # groundedness should be None (unmeasured) - no corpus found
            assert stop.groundedness_fraction is None
        finally:
            os.unlink(filepath)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
