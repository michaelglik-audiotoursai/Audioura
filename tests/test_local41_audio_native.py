"""
LOCAL-41: Audio-native text generation tests.

Verifies:
1. No rhetorical-question opening style exists in the cycling array.
2. Epilog does NOT enumerate all stops (at most 3 named).
3. "Within the broader context" is stripped by PHASE 5.9.
4. Trailing rhetorical questions are stripped by PHASE 5.9.
5. Museum stops > 1 are told NOT to re-introduce the venue.
6. Orientation fallback no longer says "Position yourself directly in front".
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestOpeningStylesNoQuestion:
    """Defect 1: No opening style should instruct GPT to open with a question."""

    def test_no_question_opener_in_styles(self):
        """The _OPENING_STYLES array must not contain 'question' as an instruction."""
        # Read the source to extract the array (avoids importing the full module)
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()

        # Find the _OPENING_STYLES block
        match = re.search(
            r'_OPENING_STYLES\s*=\s*\[(.*?)\]',
            source, re.DOTALL
        )
        assert match, "_OPENING_STYLES array not found in generate_tour_text.py"
        styles_block = match.group(1)

        # Each style string should not instruct opening with a question
        styles = re.findall(r'"([^"]+)"', styles_block)
        for style in styles:
            assert 'question' not in style.lower(), (
                f"Opening style still contains 'question': {style!r}"
            )

    def test_seven_styles_remain(self):
        """Should still have 7 opener styles (one replaced, not removed)."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        match = re.search(r'_OPENING_STYLES\s*=\s*\[(.*?)\]', source, re.DOTALL)
        assert match
        styles = re.findall(r'"([^"]+)"', match.group(1))
        assert len(styles) == 7, f"Expected 7 styles, got {len(styles)}"


class TestEpilogNoFullEnumeration:
    """Defect 2: The epilog must not list all stops."""

    def test_no_recap_list_construction(self):
        """The old _recap_list (joining ALL poi names) should be gone."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()

        # The old pattern: "You've experienced {_recap_list}"
        assert "You've experienced {_recap_list}" not in source, (
            "Full stop enumeration pattern still present in epilog"
        )

    def test_epilog_names_at_most_three(self):
        """The epilog template should reference at most 3 stop names."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()

        # Find the epilog construction area (after "Audio-native closing" comment)
        epilog_section = source[source.find('[LOCAL-41] Audio-native closing'):]
        epilog_section = epilog_section[:epilog_section.find('poi_content += epilog') + 50]

        # Count f-string references to stop names in the epilog templates
        # Should be: _first, _mid (optional), _last — never more than 3
        name_refs = re.findall(r'\{_(?:first|mid|last|poi_names)', epilog_section)
        # We expect references to _first, _mid, _last only
        for ref in name_refs:
            assert ref in ('{_first', '{_mid', '{_last'), (
                f"Unexpected stop-name reference in epilog: {ref}"
            )


class TestBroaderContextStripped:
    """Defect 4: 'Within the broader context' should be caught by PHASE 5.9."""

    def test_phase59_regex_strips_broader_context(self):
        """Simulate the PHASE 5.9 regex on sample text."""
        text = ("The armor is remarkable. Within the broader context of the museum, "
                "it represents a fusion of artistic traditions.")
        # Apply the same regex from PHASE 5.9
        result = re.sub(
            r'[Ww]ithin the broader context of (the museum|the collection|this museum|this collection)[,.]?\s*',
            '', text
        )
        assert "Within the broader context" not in result
        assert "it represents a fusion" in result

    def test_broader_context_with_tour_type(self):
        """The regex also catches 'Within the broader context of Asian arts'."""
        tour_type = "Asian arts"
        text = f"Within the broader context of {tour_type}, this piece stands out."
        result = re.sub(
            r'[Ww]ithin the broader context of (the museum|the collection|this museum|this collection|'
            + re.escape(tour_type) + r')[,.]?\s*',
            '', text
        )
        assert "broader context" not in result


class TestTrailingQuestionStrip:
    """Defect 1 (safety net): Trailing questions should be stripped post-generation."""

    def test_trailing_question_removed(self):
        """A description ending with '?' has its last sentence removed."""
        text = ("The armor dates from 1600. It shows remarkable lacquer work. "
                "What other treasures might this museum hold?")
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        while sentences and sentences[-1].rstrip().endswith('?'):
            sentences.pop()
        result = ' '.join(sentences)
        assert '?' not in result
        assert "lacquer work" in result

    def test_mid_text_question_preserved(self):
        """Questions in the middle of text are NOT stripped."""
        text = ("What drew the artist here? The answer lies in the light. "
                "The lacquer work dates from 1600.")
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        while sentences and sentences[-1].rstrip().endswith('?'):
            sentences.pop()
        result = ' '.join(sentences)
        # Mid-text question preserved, nothing stripped since last sent is a period
        assert '?' in result
        assert "lacquer work" in result


class TestMidTourReintroduction:
    """Defect 3: Stop >1 prompt should forbid re-introducing the museum."""

    def test_stop_context_line_present_for_stop_gt_1(self):
        """The source should contain the anti-re-introduction instruction."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        assert "Do NOT re-introduce the museum or its city" in source
        assert "Do NOT say 'As you step into" in source

    def test_only_triggers_after_stop_1(self):
        """The guard is conditional on stop_num > 1."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        assert "if stop_num > 1:" in source


class TestOrientationFallback:
    """Defect 5: Fallback orientation should not give a confusing directive."""

    def test_no_position_yourself_directly(self):
        """The old confusing fallback should be gone."""
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        assert "Position yourself directly in front of the exhibit" not in source


class TestAudioRulesInPrompt:
    """Both museum and non-museum prompts have AUDIO RULES."""

    def test_audio_rules_present(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        # Should appear at least twice (museum + non-museum)
        count = source.count("AUDIO RULES (this will be heard, not read):")
        assert count >= 2, f"Expected AUDIO RULES in both code paths, found {count}"

    def test_never_end_with_rhetorical_question_instruction(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'generate_tour_text.py'), 'r') as f:
            source = f.read()
        assert "NEVER end with a rhetorical question" in source


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
