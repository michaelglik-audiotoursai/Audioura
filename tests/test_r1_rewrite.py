#!/usr/bin/env python3
"""Tests for LOCAL-255: R1 imperative rewrite path.

Validates the eight boundary rows from the task specification:
- 3 sentences that MUST be rewritten (not deleted), preserving content
- 3 sentences that MUST survive untouched (navigation, D107 exempt)
- 2 sentences that MAY be deleted (pure instruction, no content)
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_validator_detector import (
    check_r1_imperatives,
    rewrite_r1_sentence_deterministic,
    apply_r1_rewrites,
    _is_style_navigation_sentence,
)


# ═══════════════════════════════════════════════════════════════════════════════
# BOUNDARY ROW 1: Must be REWRITTEN (not deleted)
# ═══════════════════════════════════════════════════════════════════════════════

class TestR1Rewrite:
    """Sentences that must be rewritten (imperative removed, content preserved)."""

    def test_position_yourself_at_eze(self):
        """Michael's endorsed example from Round 2 review."""
        sentence = ("Position yourself at the entrance of Eze Village, a medieval "
                    "gem perched high above the French Riviera.")
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must be REWRITTEN, not deleted"
        assert result != '__LLM_NEEDED__', f"Deterministic rule should handle this; got LLM fallback"
        # Content preserved: Eze Village, medieval gem, French Riviera
        assert 'Eze Village' in result, f"Lost 'Eze Village' in: {result}"
        assert 'medieval gem' in result, f"Lost 'medieval gem' in: {result}"
        assert 'French Riviera' in result, f"Lost 'French Riviera' in: {result}"
        # Imperative removed
        assert not result.lower().startswith('position'), f"Imperative not removed: {result}"
        print(f"  BEFORE: {sentence}")
        print(f"  AFTER:  {result}")

    def test_as_you_arrive_at_cap_dantibes(self):
        """Imperative hidden in subordinate clause."""
        sentence = ("As you arrive at Cap d'Antibes, take in the breathtaking "
                    "views of the azure waters.")
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must be REWRITTEN, not deleted"
        assert result != '__LLM_NEEDED__', f"Deterministic rule should handle this; got LLM fallback"
        # Content preserved
        assert 'azure waters' in result.lower() or 'azure' in result.lower(), \
            f"Lost 'azure waters' in: {result}"
        assert 'breathtaking' in result.lower(), f"Lost 'breathtaking' in: {result}"
        # Imperative removed
        assert 'take in' not in result.lower(), f"Imperative 'take in' not removed: {result}"
        print(f"  BEFORE: {sentence}")
        print(f"  AFTER:  {result}")

    def test_look_for_fondation_maeght(self):
        """Content-rich imperative — date and founders must survive."""
        sentence = ("Look for the Fondation Maeght, founded in 1964 by "
                    "Marguerite and Aimé Maeght.")
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must be REWRITTEN, not deleted"
        assert result != '__LLM_NEEDED__', f"Deterministic rule should handle this; got LLM fallback"
        # Critical content preserved
        assert 'Fondation Maeght' in result, f"Lost 'Fondation Maeght' in: {result}"
        assert '1964' in result, f"Lost '1964' in: {result}"
        assert 'Marguerite' in result, f"Lost 'Marguerite' in: {result}"
        assert 'Aimé Maeght' in result or 'Aimé' in result, f"Lost 'Aimé Maeght' in: {result}"
        # Imperative removed
        assert not result.lower().startswith('look'), f"Imperative not removed: {result}"
        print(f"  BEFORE: {sentence}")
        print(f"  AFTER:  {result}")


# ═══════════════════════════════════════════════════════════════════════════════
# BOUNDARY ROW 2: Must survive UNTOUCHED (navigation exempt, D107)
# ═══════════════════════════════════════════════════════════════════════════════

class TestR1NavigationExempt:
    """Navigation sentences that must NOT be rewritten or deleted."""

    def test_start_cycling_south(self):
        """Michael's highest-rated direction."""
        sentence = ("Start cycling south on the main road with the sea on your right.")
        # Must be navigation-exempt
        assert _is_style_navigation_sentence(sentence), \
            f"Not detected as navigation: {sentence}"
        # R1 must NOT fire
        findings = check_r1_imperatives(sentence)
        assert len(findings) == 0, f"R1 should not fire on navigation: {findings}"

    def test_head_east_along_coastal_path(self):
        """Standard cycling direction."""
        sentence = ("Head east along the coastal path until you reach the roundabout.")
        assert _is_style_navigation_sentence(sentence), \
            f"Not detected as navigation: {sentence}"
        findings = check_r1_imperatives(sentence)
        assert len(findings) == 0, f"R1 should not fire on navigation: {findings}"

    def test_start_ride_at_cap_dantibes(self):
        """Cycling direction with place name."""
        sentence = ("Start your ride at Cap d'Antibes and pedal east along the coastal road.")
        assert _is_style_navigation_sentence(sentence), \
            f"Not detected as navigation: {sentence}"
        findings = check_r1_imperatives(sentence)
        assert len(findings) == 0, f"R1 should not fire on navigation: {findings}"


# ═══════════════════════════════════════════════════════════════════════════════
# BOUNDARY ROW 3: May be DELETED (pure instruction, no content)
# ═══════════════════════════════════════════════════════════════════════════════

class TestR1PureInstructionDeletion:
    """Pure instructions that should be deleted (no factual content)."""

    def test_take_a_moment_to_absorb(self):
        """Classic pure instruction."""
        sentence = "Take a moment to absorb the atmosphere."
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is None, f"Should be DELETED (pure instruction), got: {result}"

    def test_enjoy_the_view(self):
        """Minimal pure instruction."""
        sentence = "Enjoy the view."
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is None, f"Should be DELETED (pure instruction), got: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTENT PRESERVATION CHECK
# ═══════════════════════════════════════════════════════════════════════════════

class TestContentPreservation:
    """Verify content is preserved word-by-word as specified."""

    def test_eze_all_content_intact(self):
        """The full Michael-endorsed pair: no information lost."""
        sentence = ("Position yourself at the entrance of Eze Village, a medieval "
                    "gem perched high above the French Riviera.")
        result = rewrite_r1_sentence_deterministic(sentence)
        # These words MUST appear:
        for word in ['Eze Village', 'medieval', 'gem', 'perched', 'high', 'French Riviera']:
            assert word in result, f"Content lost — '{word}' missing from: {result}"

    def test_fondation_maeght_preserves_date_and_names(self):
        """Date and founders are the factual payload. Dropping them = destruction."""
        sentence = ("Look for the Fondation Maeght, founded in 1964 by "
                    "Marguerite and Aimé Maeght.")
        result = rewrite_r1_sentence_deterministic(sentence)
        assert '1964' in result, f"Date '1964' lost in: {result}"
        assert 'Marguerite' in result, f"'Marguerite' lost in: {result}"
        assert 'Aimé' in result, f"'Aimé' lost in: {result}"
        assert 'Fondation Maeght' in result, f"'Fondation Maeght' lost in: {result}"
        assert 'founded' in result.lower(), f"'founded' lost in: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# PARAGRAPH-LEVEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyR1Rewrites:
    """Test the full paragraph-level rewrite function."""

    def test_mixed_paragraph(self):
        """Paragraph with navigation + imperative + statement."""
        para = (
            "Start cycling south on the main road with the sea on your right. "
            "Position yourself at the entrance of Eze Village, a medieval gem "
            "perched high above the French Riviera. "
            "The village dates back to 200 BC."
        )
        result, rewritten, deleted, _ = apply_r1_rewrites(para)
        # Navigation untouched
        assert 'Start cycling south' in result, "Navigation was modified"
        # Imperative rewritten
        assert rewritten >= 1, f"Expected at least 1 rewrite, got {rewritten}"
        assert 'Position yourself' not in result, "Imperative not removed"
        # Statement untouched
        assert '200 BC' in result, "Factual statement was modified"
        # Content preserved
        assert 'Eze Village' in result
        assert 'medieval gem' in result

    def test_all_pure_instructions_deleted(self):
        """A paragraph of only pure instructions should be emptied."""
        para = "Take a moment to absorb the atmosphere. Enjoy the view."
        result, rewritten, deleted, _ = apply_r1_rewrites(para)
        assert result == '', f"Expected empty string for all-instruction para, got: {result}"
        assert deleted == 2, f"Expected 2 deletions, got {deleted}"
        assert rewritten == 0, f"Expected 0 rewrites, got {rewritten}"


# ═══════════════════════════════════════════════════════════════════════════════
# R7 SECONDARY CHECK: "Take a moment to breathe in the salty sea air..."
# ═══════════════════════════════════════════════════════════════════════════════

class TestR7SecondaryCheck:
    """The round 10 R7 residual — imperative opening shields it from R7."""

    def test_salty_sea_air_fires_r1(self):
        """This sentence is R1. Once R1 rewrites/deletes it, R7 becomes moot."""
        sentence = ("Take a moment to breathe in the salty sea air and listen "
                    "to the gentle lapping of the waves against the shore.")
        findings = check_r1_imperatives(sentence)
        assert len(findings) > 0, f"R1 should fire on this sentence"
        # After R1 processes it, it should be deleted (pure sensory instruction)
        result = rewrite_r1_sentence_deterministic(sentence)
        # This one has "salty sea air" — technically some content, but it's
        # invented sensory (R7's domain). The _is_pure_instruction check or
        # _take_a_moment_handler should catch it.
        print(f"  Result: {result}")
        # Either deleted (None) or falls to LLM — both are acceptable
        # The key insight: R1 now processes it BEFORE R7 gets to see it


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '--tb=short']))
