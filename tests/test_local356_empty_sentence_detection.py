#!/usr/bin/env python3
"""
Tests for LOCAL-356: Structural empty-sentence (filler) detection.

Verifies:
  1. The two filler examples from the task score HIGH under the new measure.
  2. A factual-control sentence scores LOW (not flagged).
  3. An orientation sentence is NOT flagged.
  4. Museum bounds (D258) are not regressed: 8-stop >= 75.0, 4-stop >= 81.2.

Per D242: tests import from production and must fail against the unfixed version.
"""
import os
import sys
import re
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tour_rubric_scorer import (
    _is_empty_sentence,
    analyze_stop,
    parse_tour,
    score_tour_file,
    StopAnalysis,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Filler examples must score HIGH under empty_sentence_fraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestFillerExamplesDetected:
    """The two filler examples from the task must be flagged as empty."""

    # Example 1: atmospheric, zero facts
    FILLER_SENTENCES_1 = [
        "the weight of centuries settles upon you…",
        "the faint strains of music emanate…",
        "these artifacts speak of heritage…",
        "the past lingers here.",
    ]

    # Example 2: atmospheric, zero facts
    FILLER_SENTENCES_2 = [
        "a mix of laughter and clinking glasses creating a symphony of conviviality…",
        "the warmth envelops you…",
        "time slows here.",
    ]

    def test_example1_sentences_are_empty(self):
        """Each sentence in example 1 must be detected as empty."""
        for sent in self.FILLER_SENTENCES_1:
            assert _is_empty_sentence(sent), (
                f"Expected empty but was NOT flagged: {sent!r}"
            )

    def test_example2_sentences_are_empty(self):
        """Each sentence in example 2 must be detected as empty."""
        for sent in self.FILLER_SENTENCES_2:
            assert _is_empty_sentence(sent), (
                f"Expected empty but was NOT flagged: {sent!r}"
            )

    def test_example1_high_fraction_as_stop(self):
        """Example 1 assembled as a stop body must have high empty_sentence_fraction."""
        body = " ".join(self.FILLER_SENTENCES_1)
        stop = {'index': 1, 'title': 'Test Stop', 'body': body}
        sa = analyze_stop(stop, [stop])
        assert sa.empty_sentence_fraction >= 0.7, (
            f"Expected >= 0.7, got {sa.empty_sentence_fraction:.2f}"
        )

    def test_example2_high_fraction_as_stop(self):
        """Example 2 assembled as a stop body must have high empty_sentence_fraction."""
        body = " ".join(self.FILLER_SENTENCES_2)
        stop = {'index': 1, 'title': 'Test Stop', 'body': body}
        sa = analyze_stop(stop, [stop])
        assert sa.empty_sentence_fraction >= 0.5, (
            f"Expected >= 0.5, got {sa.empty_sentence_fraction:.2f}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Factual control — real facts must NOT be flagged as empty
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactualControlNotFlagged:
    """Sentences with real facts must score LOW (not empty)."""

    FACTUAL_SENTENCES = [
        "Built in 1650 and consecrated in 1699, the cathedral dominates the skyline.",
        "The bell tower was added in 1757 using local red sandstone.",
        "The nave seats 400 worshippers.",
        "Designed by architect Jules Febvre in the Baroque style.",
        "The market has operated since the 13th century.",
    ]

    def test_factual_sentences_not_empty(self):
        """Each factual sentence must NOT be flagged as empty."""
        for sent in self.FACTUAL_SENTENCES:
            assert not _is_empty_sentence(sent), (
                f"Factual sentence wrongly flagged as empty: {sent!r}"
            )

    def test_factual_stop_low_fraction(self):
        """A stop made of factual sentences must have low empty_sentence_fraction."""
        body = " ".join(self.FACTUAL_SENTENCES)
        stop = {'index': 1, 'title': 'Cathedral', 'body': body}
        sa = analyze_stop(stop, [stop])
        assert sa.empty_sentence_fraction <= 0.1, (
            f"Expected <= 0.1, got {sa.empty_sentence_fraction:.2f}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Orientation sentences must NOT be flagged
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrientationNotFlagged:
    """Orientation/navigation sentences must survive — they tell listeners where to look."""

    ORIENTATION_SENTENCES = [
        "As you stand on Cours Saleya, the market stalls are ahead of you.",
        "Look to your left and you will see the Baroque facade of the chapel.",
        "Turn right at the fountain and continue along the promenade.",
        "The entrance to the museum is on your right as you face the square.",
        "Walk north along Rue Droite until you reach the cathedral.",
        "As you enter the courtyard, the main gallery is directly ahead of you.",
    ]

    def test_orientation_sentences_not_empty(self):
        """Each orientation sentence must NOT be flagged as empty."""
        for sent in self.ORIENTATION_SENTENCES:
            assert not _is_empty_sentence(sent), (
                f"Orientation sentence wrongly flagged: {sent!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. generic_filler_fraction was blind to the task examples (documents the bug)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOldMetricBlind:
    """Document that generic_filler_fraction scores 0% on the task examples.

    This proves the old metric is insufficient — it only catches 12 fixed phrases.
    """

    def test_old_metric_zero_on_example1(self):
        """generic_filler_fraction == 0 on example 1 (the documented bug)."""
        body = (
            "the weight of centuries settles upon you… the faint strains of "
            "music emanate… these artifacts speak of heritage… the past lingers here."
        )
        stop = {'index': 1, 'title': 'Test', 'body': body}
        sa = analyze_stop(stop, [stop])
        assert sa.generic_filler_fraction == 0.0, (
            f"Expected 0.0 (proving the bug), got {sa.generic_filler_fraction}"
        )
        # But the NEW metric catches it:
        assert sa.empty_sentence_fraction > 0.0, (
            f"New metric should catch what old metric misses"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Museum bounds (D258 regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMuseumBoundsUnaffected:
    """Museum tour scores must not regress.

    This task ONLY adds a new metric field (empty_sentence_fraction) to
    StopAnalysis — it does NOT change classification logic or score computation.
    Museum bounds should be entirely unaffected.

    8-stop >= 75.0, 4-stop >= 81.2 (D258 properties).
    """

    @pytest.fixture
    def scorer(self):
        return score_tour_file

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )),
        reason="8-stop museum tour file not available"
    )
    def test_museum_8stop_bound(self, scorer):
        """Museum 8-stop tour must score >= 75.0."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )
        result = scorer(tour_file, n_requested=8)
        assert result.total_score >= 75.0, (
            f"Museum 8-stop score {result.total_score} < 75.0 bound (D258)"
        )

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'Palais_Lascaris__Nice_museum_tour_20260727_174018.txt'
        )),
        reason="4-stop museum tour file not available"
    )
    def test_museum_4stop_bound(self, scorer):
        """Museum 4-stop (Palais Lascaris) must score >= 81.2."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'Palais_Lascaris__Nice_museum_tour_20260727_174018.txt'
        )
        result = scorer(tour_file, n_requested=4)
        assert result.total_score >= 81.2, (
            f"Museum 4-stop score {result.total_score} < 81.2 bound (D258)"
        )
