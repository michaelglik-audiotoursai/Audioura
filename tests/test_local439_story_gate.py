"""tests/test_local439_story_gate.py — LOCAL-439: Story gate unit tests.

D394: The unit of evaluation is the STORY, not the sentence.
D394 addendum: Classification is an AI question, not a verb list.
D394 third addendum: Additive interest scoring with ranged axes.

Tests mock the LLM layer with live verdicts (D242 pattern).
Live verdicts were obtained from gpt-4o-mini temperature=0 on 2026-08-12
and are committed here as deterministic fixtures.

Binding per D242 #1, D277, D376: functions are at module scope, imported by
tests. Neutralisation proof per function below.
"""
import json
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from story_gate import (
    classify_story_unit,
    score_story_interest,
    extract_candidate_story_units,
    verify_stop_story,
    get_classification_cost,
    reset_classification_cost,
    load_verdict_cache,
    get_verdict_cache,
    _verdict_cache,
    _cache_key,
    _is_obvious_non_prose,
)
from story_selection import score_story_quality


# ─── Live verdicts from gpt-4o-mini (2026-08-12, temperature=0) ─────────────
# These are the exact responses from the live run, committed as fixtures.

MIRO_STORY = (
    "In 1967, Joan Miró completed a full set of lithographs for Le Lézard, but the entire "
    "edition was destroyed because a chemical reaction caused the inks to bleed into the "
    "paper. Miró recreated the work on new plates, while printers spent years perfecting "
    "the paper chemistry to prevent further degradation. The final 1971 masterpiece stands "
    "as a symbol of artistic and printmaking resilience following the scrapped original "
    "attempt."
)

ATMOSPHERIC_FILLER = (
    "The collection serves as a window to the musical traditions of 18th-century Nice. "
    "It connects us to a time when music played a central role in both sacred and secular life. "
    "It invites you to consider how these instruments shaped the cultural identity of the region."
)

DEDUCTION_FIRES_TEXT = (
    "This experimental work forces visitors to look closely at how art lives in the margins. "
    'It proves to visitors that an "unbound" artist\'s book is a living laboratory. '
    "The unconventional binding technique challenges traditional bookmaking assumptions."
)

NO_DEDUCTION_TEXT = MIRO_STORY  # "stands as a symbol of resilience" characterizes WORK

# Pinned LLM verdicts from the live run
_LIVE_VERDICTS = {
    _cache_key(MIRO_STORY): {
        'is_story': True,
        'reason': "The text describes Joan Miró's actions in creating and recreating his work, "
                  "presenting a clear arc of struggle with the chemical reaction and resolution "
                  "with the final masterpiece.",
        'emotional_content': 3,
        'new_information': 2,
        'deduction': 0,
        'cost_usd': 9.285e-05,
        'from_cache': False,
    },
    _cache_key(ATMOSPHERIC_FILLER): {
        'is_story': False,
        'reason': "The text does not contain a named person, real actions, or an arc; "
                  "it is purely atmospheric and evaluative.",
        'emotional_content': 0,
        'new_information': 2,
        'deduction': 1,
        'cost_usd': 8.235e-05,
        'from_cache': False,
    },
    _cache_key(DEDUCTION_FIRES_TEXT): {
        'is_story': False,
        'reason': "The text does not contain a named person, real actions, or an arc; "
                  "it consists of evaluative statements about the artwork.",
        'emotional_content': 0,
        'new_information': 1,
        'deduction': 2,
        'cost_usd': 8.235e-05,
        'from_cache': False,
    },
}


@pytest.fixture(autouse=True)
def preload_verdict_cache():
    """Load live verdicts into cache so tests don't hit the real API."""
    _verdict_cache.clear()
    load_verdict_cache(_LIVE_VERDICTS)
    yield
    _verdict_cache.clear()


# ─── Michael's acceptance fixtures ───────────────────────────────────────────

class TestMirosStoryPassesAsOneUnit:
    """PASS as one story-unit — Michael's 3-sentence Miró story."""

    def test_classify_passes(self):
        """The Miró story is classified as a story (named person, actions, arc)."""
        verdict = classify_story_unit(MIRO_STORY)
        assert verdict['is_story'] is True

    def test_verify_stop_passes(self):
        """verify_stop_story passes with at least 1 story-unit."""
        result = verify_stop_story(description=MIRO_STORY)
        assert result['passed'] is True
        assert result['story_unit_count'] >= 1

    def test_resolution_sentence_valid_inside_unit(self):
        """'stands as a symbol of...' is valid INSIDE a story-unit (D394)."""
        verdict = classify_story_unit(MIRO_STORY)
        assert verdict['is_story'] is True
        # The resolution sentence is part of the arc, not rejected


class TestAtmosphericFillerFailsAsZeroUnits:
    """FAIL as zero story-units — three adjacent atmospheric sentences."""

    def test_classify_fails(self):
        """Atmospheric filler is NOT classified as a story."""
        verdict = classify_story_unit(ATMOSPHERIC_FILLER)
        assert verdict['is_story'] is False

    def test_verify_stop_fails(self):
        """verify_stop_story fails — no story-units."""
        result = verify_stop_story(description=ATMOSPHERIC_FILLER)
        assert result['passed'] is False
        assert result['story_unit_count'] == 0
        assert any('story_units=0' in f for f in result['failures'])


class TestDeductionFires:
    """Deduction fires for text that directs the VISITOR."""

    def test_deduction_score_is_positive(self):
        """'forces visitors to...' and 'proves to visitors that...' trigger deduction."""
        verdict = classify_story_unit(DEDUCTION_FIRES_TEXT)
        assert verdict['deduction'] >= 1, f"Expected deduction ≥1, got {verdict['deduction']}"

    def test_interest_score_penalized(self):
        """Interest score is reduced by the deduction."""
        interest = score_story_interest(DEDUCTION_FIRES_TEXT)
        # deduction=2 should subtract from interest
        raw = interest['emotional_content'] + interest['new_information']
        assert interest['interest_score'] == raw - interest['deduction']
        assert interest['deduction'] == 2


class TestDeductionDoesNotFire:
    """Deduction does NOT fire for text characterizing the WORK."""

    def test_no_deduction_for_work_characterization(self):
        """'stands as a symbol of resilience' characterizes the work, not the visitor."""
        verdict = classify_story_unit(NO_DEDUCTION_TEXT)
        assert verdict['deduction'] == 0, (
            f"Expected deduction=0 (characterizes work), got {verdict['deduction']}"
        )


# ─── Interest scoring ────────────────────────────────────────────────────────

class TestScoreStoryInterest:
    """D394 third addendum: emotional content 0-4, new information 0-3, deduction 0-2."""

    def test_miro_story_has_emotional_content(self):
        """The Miró story has tension/conflict/resolution — emotional_content > 0."""
        interest = score_story_interest(MIRO_STORY)
        assert interest['emotional_content'] >= 2

    def test_miro_story_has_new_information(self):
        """The Miró story has facts beyond the visible — new_information > 0."""
        interest = score_story_interest(MIRO_STORY)
        assert interest['new_information'] >= 1

    def test_atmospheric_has_no_emotional_content(self):
        """Atmospheric filler has no story arc — emotional_content = 0."""
        interest = score_story_interest(ATMOSPHERIC_FILLER)
        assert interest['emotional_content'] == 0

    def test_interest_score_composition(self):
        """interest_score = emotional + new_info - deduction."""
        interest = score_story_interest(MIRO_STORY)
        expected = interest['emotional_content'] + interest['new_information'] - interest['deduction']
        assert interest['interest_score'] == expected


# ─── Quality scoring integration with story_selection ────────────────────────

class TestQualityScoreWithInterest:
    """score_story_quality uses the new trust+interest formula when _interest is set."""

    def test_with_interest_data(self):
        """When _interest is pre-computed, uses trust + emotional + new_info - deduction."""
        story = {
            'text': MIRO_STORY,
            'source_type': 'museum_official',  # provenance 3.0 → trust 5.0
            '_interest': {
                'emotional_content': 3,
                'new_information': 2,
                'deduction': 0,
            },
        }
        score = score_story_quality(story)
        # trust 5.0 + emotional 3 + new_info 2 - deduction 0 = 10.0
        assert score == 10.0, f"Expected 10.0, got {score}"

    def test_deduction_reduces_score(self):
        """Deduction from 'telling visitors what to feel' reduces score."""
        story = {
            'text': DEDUCTION_FIRES_TEXT,
            'source_type': 'museum_official',  # trust 5.0
            '_interest': {
                'emotional_content': 0,
                'new_information': 1,
                'deduction': 2,
            },
        }
        score = score_story_quality(story)
        # trust 5.0 + 0 + 1 - 2 = 4.0
        assert score == 4.0, f"Expected 4.0, got {score}"

    def test_trust_from_web_search_is_low(self):
        """Web search provenance gives low trust (0.83)."""
        story = {
            'text': MIRO_STORY,
            'source_type': 'web_search',  # provenance 0.5 → trust 0.83
            '_interest': {
                'emotional_content': 3,
                'new_information': 2,
                'deduction': 0,
            },
        }
        score = score_story_quality(story)
        # trust 0.83 + 3 + 2 - 0 = 5.83
        assert score == 5.83, f"Expected 5.83, got {score}"

    def test_michaels_worked_example_rounded_story_wins(self):
        """D394 third addendum: trust-3 story with max emotion+novelty beats trust-only.

        trust-only story: trust 5 + 0 + 0 = 5
        trust-3 story with max emotion+novelty: trust 3.33 + 4 + 3 = 10.33
        The rounded story wins.
        """
        trust_only = {
            'text': 'X ' * 50,
            'source_type': 'museum_official',
            '_interest': {'emotional_content': 0, 'new_information': 0, 'deduction': 0},
        }
        rounded = {
            'text': 'Y ' * 50,
            'source_type': 'external_verified',  # provenance 2.0 → trust 3.33
            '_interest': {'emotional_content': 4, 'new_information': 3, 'deduction': 0},
        }
        score_trust_only = score_story_quality(trust_only)
        score_rounded = score_story_quality(rounded)
        assert score_rounded > score_trust_only, (
            f"Rounded story ({score_rounded}) should beat trust-only ({score_trust_only})"
        )


# ─── Candidate extraction ────────────────────────────────────────────────────

class TestExtractCandidateStoryUnits:
    """extract_candidate_story_units finds ≥3-sentence blocks."""

    def test_three_sentence_block(self):
        """A 3-sentence text produces at least one candidate."""
        candidates = extract_candidate_story_units(MIRO_STORY)
        assert len(candidates) >= 1

    def test_short_text_no_candidates(self):
        """Text with fewer than 3 sentences produces no candidates."""
        candidates = extract_candidate_story_units("Hello. World.")
        assert candidates == []

    def test_empty_text(self):
        assert extract_candidate_story_units("") == []
        assert extract_candidate_story_units(None) == []

    def test_structural_markers_rejected(self):
        """Headings and structural markers are filtered."""
        text = "# Stop 1: Title\nDirections: Go left.\nSources: Wikipedia."
        candidates = extract_candidate_story_units(text)
        assert candidates == []


# ─── Caching ─────────────────────────────────────────────────────────────────

class TestVerdictCache:
    """Verdict cached alongside the unit; re-scoring never re-asks."""

    def test_same_text_uses_cache(self):
        """Second call for same text returns from_cache=True."""
        v1 = classify_story_unit(MIRO_STORY)
        v2 = classify_story_unit(MIRO_STORY)
        assert v2['from_cache'] is True
        assert v2['cost_usd'] == 0.0

    def test_different_text_different_verdict(self):
        """Different text gets its own verdict."""
        v1 = classify_story_unit(MIRO_STORY)
        v2 = classify_story_unit(ATMOSPHERIC_FILLER)
        assert v1['is_story'] != v2['is_story']


# ─── Neutralisation proofs (D242 #1) ────────────────────────────────────────

class TestNeutralisation:
    """Prove each function is bound: neutralising it makes tests go red."""

    def test_classify_not_always_true(self):
        """If classify_story_unit always returned is_story=True, this fails."""
        verdict = classify_story_unit(ATMOSPHERIC_FILLER)
        assert verdict['is_story'] is False

    def test_classify_not_always_false(self):
        """If classify_story_unit always returned is_story=False, this fails."""
        verdict = classify_story_unit(MIRO_STORY)
        assert verdict['is_story'] is True

    def test_verify_not_always_pass(self):
        """If verify_stop_story always passed, this fails."""
        result = verify_stop_story(description=ATMOSPHERIC_FILLER)
        assert result['passed'] is False

    def test_verify_not_always_fail(self):
        """If verify_stop_story always failed, this fails."""
        result = verify_stop_story(description=MIRO_STORY)
        assert result['passed'] is True

    def test_score_interest_not_constant(self):
        """If score_story_interest returned constant scores, this fails."""
        i1 = score_story_interest(MIRO_STORY)
        i2 = score_story_interest(ATMOSPHERIC_FILLER)
        assert i1['emotional_content'] != i2['emotional_content']

    def test_deduction_not_always_zero(self):
        """If deduction was always 0, this fails."""
        verdict = classify_story_unit(DEDUCTION_FIRES_TEXT)
        assert verdict['deduction'] > 0

    def test_deduction_not_always_nonzero(self):
        """If deduction was always >0, this fails."""
        verdict = classify_story_unit(MIRO_STORY)
        assert verdict['deduction'] == 0


# ─── Entity check applies to stop text as whole (D393 fix) ───────────────────

class TestEntitiesBlurred:
    """entities_blurred applies to the STOP TEXT, not to a story-unit."""

    def test_artist_present_passes(self):
        """Stop text mentioning the artist surname passes."""
        from story_gate import check_named_entities_present
        ok, found, missing = check_named_entities_present(
            description="Joan Miró created this work in 1967.",
            credit_line="Joan Miró (Spanish, 1893–1983)",
        )
        assert ok is True
        assert len(found) >= 1

    def test_dropping_donor_is_ok(self):
        """A story that drops the donor (Fridman) for concision is correct (D393)."""
        from story_gate import check_named_entities_present
        ok, found, missing = check_named_entities_present(
            description="Miró recreated the work on new plates.",
            credit_line="Gift of Boris Fridman. Joan Miró (Spanish, 1893–1983)",
        )
        # Should NOT demand Fridman — only the artist is checked
        # But the primary artist pattern here would match "Joan Miró"
        # and check for Miró in the text
        assert ok is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
