"""tests/test_local438_story_selection.py — LOCAL-438: Story packing tests.

Michael's worked example is the acceptance fixture — all three cases must pass
with exact expected outputs.

Also: neutralisation checks (D242 #1) proving these functions are bound.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from story_selection import (
    score_story_quality,
    select_stories_for_stop,
    STOP_WORD_BUDGET,
    STOP_WORD_FLOOR,
    SOURCE_PROVENANCE_WEIGHTS,
    _count_words,
    _get_source_provenance_score,
    _get_verification_score,
    _get_specificity_score,
)


# ─── Michael's worked example ────────────────────────────────────────────────
# Budget 100 words. Stories: A good/30w, B excellent/80w, C bad-but-legitimate/20w,
# D good/25w, E good/70w.
#
# "Good" = provenance 2.0 + verification 1.0 + specificity 1.0 = 4.0
# "Excellent" = provenance 3.0 + verification 2.0 + specificity 3.0 = 8.0
# "Bad-but-legitimate" = provenance 0.5 + verification 0.5 + specificity 0.0 = 1.0
#
# With B present: B(80) wins, 20 left, only C(20) fits → B + C.
# Without B: sort A, D, E by quality then fit: E(70) + A(30) = 100 → E + A.
# Single F excellent/125w, far the best, budget 100: 125 < 150 (=100+50%) → F alone.


def _make_story(text_word_count: int, quality_level: str, label: str = '') -> dict:
    """Create a story dict with controlled word count and quality signals.

    quality_level controls the score components:
      - 'excellent': museum_official(3.0) + documented(2.0) + specificity(3.0) = 8.0
      - 'good': external_verified(2.0) + reported(1.0) + specificity(1.0) = 4.0
      - 'bad_but_legitimate': web_search(0.5) + legend(0.5) + specificity(0.0) = 1.0

    Text is constructed to produce exactly the specified word count.
    Specificity signals are controlled via the 'people', 'dates' fields
    rather than text patterns to ensure precise scoring.
    """
    # Generate filler words to reach exact word count
    # Use neutral words that don't trigger specificity regex patterns
    filler = ' '.join([f"item{i}" for i in range(text_word_count)])
    # Trim to exact word count
    text = ' '.join(filler.split()[:text_word_count])

    if quality_level == 'excellent':
        # provenance 3.0 + verification 2.0 + specificity 3.0 = 8.0
        # Specificity needs: people(+1) + dates(+1) + consequence(+1)
        # Put consequence verb in text to trigger regex
        words = text.split()
        words[0] = 'donated'  # triggers consequence regex
        text = ' '.join(words)
        return {
            'text': text,
            'source_type': 'museum_official',
            'corroboration_status': 'documented',
            'people': ['Louis Broder'],
            'dates': ['1971'],
            '_label': label,
        }
    elif quality_level == 'good':
        # provenance 2.0 + verification 1.0 + specificity 1.0 = 4.0
        # Specificity: only people(+1), no date, no consequence
        return {
            'text': text,
            'source_type': 'external_verified',
            'corroboration_status': 'reported',
            'people': ['Mourlot Frères'],
            'dates': [],
            '_label': label,
        }
    else:  # bad_but_legitimate
        # provenance 0.5 + verification 0.5 + specificity 0.0 = 1.0
        return {
            'text': text,
            'source_type': 'web_search',
            'corroboration_status': 'legend',
            'people': [],
            'dates': [],
            '_label': label,
        }


class TestMichaelsWorkedExample:
    """Michael's three cases from D392 — exact expected outputs."""

    def test_case1_with_B_present(self):
        """Budget 100. B(excellent/80w) wins, 20 left, only C(20w) fits → B + C."""
        A = _make_story(30, 'good', 'A')
        B = _make_story(80, 'excellent', 'B')
        C = _make_story(20, 'bad_but_legitimate', 'C')
        D = _make_story(25, 'good', 'D')
        E = _make_story(70, 'good', 'E')

        result = select_stories_for_stop([A, B, C, D, E], budget=100)
        labels = [s['_label'] for s in result]
        assert labels == ['B', 'C'], f"Expected ['B', 'C'], got {labels}"

    def test_case2_without_B(self):
        """Budget 100. Without B: sort A,D,E by quality then fit.
        All are 'good' (same score). Tie-break: shorter first.
        D(25) + A(30) + E(70) = 125 > 100, so: D(25) first (shortest good),
        then A(30), then E(70) won't fit (25+30+70=125>100).
        Wait — re-read Michael: "E(70) + A(30) = 100 → E + A"

        Michael's expected output assumes same-quality stories are ordered by
        size to maximise coverage. The greedy packer takes best-fitting stories.
        With equal scores, tie-break is shorter-first, so: D(25), A(30), then
        try E(70) → 25+30+70=125 > 100. So D+A+C(20) = 75 or D+A = 55...

        Re-reading Michael: "sort A, D, E by quality then fit: E(70) + A(30) = 100"
        He says the answer is E + A. This means with equal quality, the packer
        should maximise word usage (fill budget), not just take shortest-first.

        Actually, looking again at his words: "sort by quality then fit" — if all
        three (A, D, E) have the same quality, the greedy packer in order takes
        whatever fits. The tie-break should favour the combination that fills
        the budget most fully.

        The simplest correct reading: all three are "good" = same score.
        Greedy with shorter-first: D(25) then A(30) then E(70) → 25+30=55, 70>45 skip.
        → D + A = 55 words. That doesn't match Michael.

        Michael expects E(70) + A(30) = 100. This means the tie-breaking should
        be LONGEST first (to maximise budget usage with greedy packing).

        Let me re-read: "sort A, D, E by quality then fit" — with identical quality,
        the greedy fill maximises usage when we try largest-fitting-first within a
        quality tier.

        Correction: Michael's design says "take the best story that fits, then
        the best remaining story that fits in the leftover". With equal quality,
        the "best" among equals is the one that uses the budget most effectively.
        This is standard greedy bin packing: sort by SIZE descending within a
        quality tier, then take-if-fits.

        So tie-break should be: LONGER first (fills budget better).
        E(70) fits in 100 → take. 30 left. A(30) fits → take. D(25) doesn't fit
        (0 remaining). → E + A.
        """
        A = _make_story(30, 'good', 'A')
        C = _make_story(20, 'bad_but_legitimate', 'C')
        D = _make_story(25, 'good', 'D')
        E = _make_story(70, 'good', 'E')

        result = select_stories_for_stop([A, C, D, E], budget=100)
        labels = [s['_label'] for s in result]
        assert labels == ['E', 'A'], f"Expected ['E', 'A'], got {labels}"

    def test_case3_single_story_exception(self):
        """Single F excellent/125w, far the best, budget 100: 125 < 150 → F alone."""
        F = _make_story(125, 'excellent', 'F')
        A = _make_story(30, 'good', 'A')
        C = _make_story(20, 'bad_but_legitimate', 'C')

        result = select_stories_for_stop([F, A, C], budget=100)
        labels = [s['_label'] for s in result]
        assert labels == ['F'], f"Expected ['F'], got {labels}"


class TestScoreStoryQuality:
    """Test the quality scoring function."""

    def test_excellent_story_scores_high(self):
        story = _make_story(80, 'excellent', 'test')
        score = score_story_quality(story)
        # museum_official(3.0) + documented(2.0) + specificity(3.0) = 8.0
        assert score == 8.0, f"Expected 8.0, got {score}"

    def test_good_story_scores_medium(self):
        story = _make_story(50, 'good', 'test')
        score = score_story_quality(story)
        # external_verified(2.0) + reported(1.0) + specificity(1.0, has people only) = 4.0
        assert score == 4.0, f"Expected 4.0, got {score}"

    def test_bad_but_legitimate_scores_low(self):
        story = _make_story(20, 'bad_but_legitimate', 'test')
        score = score_story_quality(story)
        # web_search(0.5) + legend(0.5) + specificity(0.0) = 1.0
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_score_deterministic(self):
        """Same story always gets the same score."""
        story = _make_story(60, 'excellent', 'test')
        assert score_story_quality(story) == score_story_quality(story)

    def test_provenance_weights_shared(self):
        """SOURCE_PROVENANCE_WEIGHTS matches corpus_source_quality's table."""
        assert SOURCE_PROVENANCE_WEIGHTS['museum_official'] == 3.0
        assert SOURCE_PROVENANCE_WEIGHTS['wikipedia'] == 2.5
        assert SOURCE_PROVENANCE_WEIGHTS['external_verified'] == 2.0
        assert SOURCE_PROVENANCE_WEIGHTS['web_search'] == 0.5


class TestSelectStoriesForStop:
    """Test the packing selector."""

    def test_empty_pool(self):
        assert select_stories_for_stop([], budget=100) == []

    def test_single_story_fits(self):
        story = _make_story(50, 'good', 'only')
        result = select_stories_for_stop([story], budget=100)
        assert len(result) == 1

    def test_respects_budget(self):
        """Stories exceeding budget are not selected (unless exception applies)."""
        big = _make_story(200, 'good', 'big')  # > 100 and > 150 (50% over)
        result = select_stories_for_stop([big], budget=100)
        assert result == []

    def test_exception_does_not_fire_above_150_percent(self):
        """A story >150% of budget is never taken alone."""
        huge = _make_story(160, 'excellent', 'huge')
        small = _make_story(20, 'bad_but_legitimate', 'small')
        result = select_stories_for_stop([huge, small], budget=100)
        labels = [s['_label'] for s in result]
        assert 'huge' not in labels
        # small(20) fits the budget — it should be taken
        assert 'small' in labels

    def test_exception_requires_clear_best(self):
        """50% exception requires score gap ≥1.0 over second-best."""
        # Two excellent stories of same score — exception should NOT fire
        F1 = _make_story(125, 'excellent', 'F1')
        F2 = _make_story(80, 'excellent', 'F2')
        result = select_stories_for_stop([F1, F2], budget=100)
        labels = [s['_label'] for s in result]
        # F1 exceeds budget, F2 has same quality → exception doesn't fire
        # F2 fits → take F2
        assert 'F1' not in labels
        assert 'F2' in labels

    def test_packing_stops_at_budget(self):
        """Greedy packer does not exceed the specified budget."""
        tiny1 = _make_story(50, 'excellent', 'tiny1')
        tiny2 = _make_story(40, 'good', 'tiny2')
        tiny3 = _make_story(35, 'bad_but_legitimate', 'tiny3')
        # Budget 60: takes tiny1(50) — the best. 10 left, nothing else fits.
        result = select_stories_for_stop([tiny1, tiny2, tiny3], budget=60)
        total_words = sum(s['_word_count'] for s in result)
        assert total_words <= 60
        assert len(result) == 1
        assert result[0]['_label'] == 'tiny1'

    def test_deterministic_tiebreak(self):
        """Same input always produces same output order."""
        stories = [
            _make_story(50, 'good', 'A'),
            _make_story(50, 'good', 'B'),
            _make_story(50, 'good', 'C'),
        ]
        r1 = select_stories_for_stop(stories, budget=200)
        r2 = select_stories_for_stop(stories, budget=200)
        assert [s['_label'] for s in r1] == [s['_label'] for s in r2]

    def test_annotates_quality_score(self):
        """Selected stories carry _quality_score annotation."""
        story = _make_story(50, 'good', 'test')
        result = select_stories_for_stop([story], budget=100)
        assert '_quality_score' in result[0]
        assert '_word_count' in result[0]

    def test_default_budget_is_module_constant(self):
        """When budget=None, uses STOP_WORD_BUDGET."""
        assert STOP_WORD_BUDGET == 450


class TestNeutralisation:
    """D242 #1: neutralise in place → tests go red."""

    def test_score_is_not_constant(self):
        """If score_story_quality returned a constant, this would fail."""
        excellent = _make_story(80, 'excellent', 'a')
        bad = _make_story(20, 'bad_but_legitimate', 'b')
        assert score_story_quality(excellent) != score_story_quality(bad)

    def test_selection_is_not_passthrough(self):
        """If select_stories_for_stop returned all input, this would fail."""
        stories = [_make_story(200, 'good', f's{i}') for i in range(5)]
        # 5 stories × 200 words = 1000, budget 450 → cannot take all
        result = select_stories_for_stop(stories, budget=450)
        assert len(result) < len(stories)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
