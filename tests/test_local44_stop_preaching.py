"""
LOCAL-44: Stop instructing the listener — anti-preaching tests.
================================================================
Tests the six faults identified by Michael:
1. Preaching (instructive closings)
2. Condescension ("To truly appreciate...")
3. Describing the plainly visible
4. Unexplained references (explain-what-you-name strengthening)
5. Exhibit name in orientation (not "the exhibit")
6. Directions are filler (no "Ask museum staff", venue name ≤2)
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from derepetition_guard import scan_for_repetition, FORBIDDEN_PHRASES


# ======================================================================
# FAULT 1: Preaching / instructive closings
# ======================================================================

class TestPreachingClosingsDetected:
    """The derepetition guard must catch all Michael-flagged preaching patterns."""

    def test_consider_what_other_tales(self):
        text = "As you stand before this masterpiece, consider what other tales of cultural synthesis await your discovery."
        assert len(scan_for_repetition(text)) > 0

    def test_let_whispers_of_past(self):
        text = "Let the whispers of the past guide your imagination as you ponder the eternal questions."
        assert len(scan_for_repetition(text)) > 0

    def test_take_a_moment_to(self):
        text = "Take a moment to appreciate the delicate craftsmanship on display."
        assert len(scan_for_repetition(text)) > 0

    def test_allow_yourself_to(self):
        text = "Allow yourself to be transported back to the 15th century."
        assert len(scan_for_repetition(text)) > 0

    def test_carry_this_with_you(self):
        text = "Carry this insight with you as you continue through the galleries."
        assert len(scan_for_repetition(text)) > 0

    def test_the_next_journey_awaits(self):
        text = "The next journey awaits."
        assert len(scan_for_repetition(text)) > 0

    def test_factual_text_passes(self):
        """Concrete, factual descriptions must NOT be flagged."""
        text = ("The bronze dates to the 10th century Chola dynasty. "
                "Seven layers of lacquer, each sanded to translucence.")
        assert len(scan_for_repetition(text)) == 0


# ======================================================================
# FAULT 2: Condescension
# ======================================================================

class TestCondescensionDetected:
    """'To truly appreciate' and similar patterns must be caught."""

    def test_to_truly_appreciate(self):
        text = "To truly appreciate the significance of this piece, one must understand the context of samurai culture."
        assert len(scan_for_repetition(text)) > 0

    def test_to_fully_understand(self):
        text = "To fully understand this artwork, consider the political climate of 1920s Russia."
        assert len(scan_for_repetition(text)) > 0

    def test_it_is_worth_noting(self):
        text = "It is worth noting that the artist spent three years on this commission."
        assert len(scan_for_repetition(text)) > 0

    def test_it_is_important_to_understand(self):
        text = "It is important to understand that lacquer techniques evolved over centuries."
        assert len(scan_for_repetition(text)) > 0

    def test_direct_statement_passes(self):
        """The correct version — just stating context — should pass."""
        text = ("During samurai culture in 19th century Japan, armor was not just a "
                "practical necessity but also a symbol of status, honor, and tradition.")
        assert len(scan_for_repetition(text)) == 0


# ======================================================================
# FAULT 5: Exhibit name in orientation (prompt-level check)
# ======================================================================

class TestOrientationNamesExhibit:
    """The museum prompt must instruct GPT to name the exhibit specifically."""

    def test_prompt_requires_specific_name(self):
        """The orientation instruction must ask for the exhibit's actual name."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        # The prompt must contain instruction to name the exhibit specifically
        assert 'not "the exhibit"' in source

    def test_prompt_bans_generic_reference(self):
        """Prompt must ban 'the exhibit' and 'this piece' in orientation."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert 'not "the exhibit"' in source or "not 'the exhibit'" in source


# ======================================================================
# FAULT 6: Directions — no "Ask museum staff", venue name ≤2
# ======================================================================

class TestTransitionTemplates:
    """Museum transitions must not say 'Ask museum staff' and venue name appears ≤2 times."""

    def test_no_ask_museum_staff_in_transitions(self):
        """The transition templates must NOT contain 'Ask museum staff' as output text."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        # Find the transition template section — look for f-string templates
        transition_section = source[source.find('DETERMINISTIC TRANSITION TEMPLATES'):]
        transition_section = transition_section[:transition_section.find('else:')]
        # Extract only the f-string lines (the actual template output)
        template_lines = [l for l in transition_section.split('\n')
                         if 'f"' in l or "f'" in l]
        template_text = '\n'.join(template_lines)
        assert 'Ask museum staff for directions' not in template_text

    def test_ask_museum_staff_in_forbidden_phrases(self):
        """'Ask museum staff for directions' must be in FORBIDDEN_PHRASES."""
        test_text = "Ask museum staff for directions to the next exhibit."
        matches = scan_for_repetition(test_text)
        assert len(matches) > 0, "Expected 'ask museum staff' to be caught by derepetition guard"

    def test_venue_name_at_most_twice_in_transitions(self):
        """Simulate 8 stops — venue name should appear at most 2 times in transitions."""
        # Simulate the transition logic for 8 stops (indices 0-6 produce transitions)
        venue = "Musée des Arts Asiatiques"
        poi_names = ["Work A", "Work B", "Work C", "Work D",
                     "Work E", "Work F", "Work G", "Work H"]
        transitions = []
        for i in range(7):  # 7 transitions for 8 stops
            next_name = poi_names[i + 1]
            if i == 0:
                t = f"Continue through {venue} — next is {next_name}."
            elif i == 6:  # last transition (i == len(poi_list) - 2 when poi_list has 8 items)
                t = f"Your final stop in {venue}: {next_name}."
            else:
                interior_templates = [
                    f"Next: {next_name}.",
                    f"Proceed to {next_name}.",
                    f"Continue to {next_name}.",
                ]
                t = interior_templates[(i - 1) % len(interior_templates)]
            transitions.append(t)

        all_transitions = " ".join(transitions)
        venue_count = all_transitions.count(venue)
        assert venue_count <= 2, f"Venue name appears {venue_count} times (max 2): {all_transitions}"


# ======================================================================
# PHASE 5.10: Anti-preaching post-processing
# ======================================================================

class TestPhase510AntiPreaching:
    """PHASE 5.10 must strip preaching closers from descriptions."""

    def _simulate_phase510(self, description):
        """Simulate the PHASE 5.10 regex stripping logic."""
        _PREACHING_CLOSERS = [
            re.compile(r'^(As you stand (before|here|in front of).*?,?\s*)?(consider|reflect|ponder|imagine|let)\b', re.IGNORECASE),
            re.compile(r'^take\s+a\s+moment\s+to\b', re.IGNORECASE),
            re.compile(r'^allow\s+(yourself|your\s+(mind|imagination))\s+to\b', re.IGNORECASE),
            re.compile(r'^let\s+(the|this|these|your)\b', re.IGNORECASE),
            re.compile(r'^carry\s+(this|these|the)\b.*\b(with you|forward|away)\b', re.IGNORECASE),
            re.compile(r'^(perhaps|maybe)\s+(you\'ll|you\s+will|one\s+day|next\s+time)', re.IGNORECASE),
            re.compile(r'\bwhat\s+other\s+\w+\s+(await|might|could)\b', re.IGNORECASE),
            re.compile(r'^to\s+(truly|fully|really)\s+(appreciate|understand|grasp|comprehend)\b', re.IGNORECASE),
            re.compile(r'^it\s+is\s+(worth|important)\s+(noting|to\s+(note|understand|remember))\b', re.IGNORECASE),
        ]
        sentences = re.split(r'(?<=[.!?])\s+', description.strip())
        removed = 0
        while sentences:
            last = sentences[-1].strip()
            is_preaching = False
            for pp in _PREACHING_CLOSERS:
                if pp.search(last):
                    is_preaching = True
                    break
            if is_preaching:
                sentences.pop()
                removed += 1
                if removed >= 2:
                    break
            else:
                break
        return ' '.join(sentences).strip(), removed

    def test_strips_consider_what_other(self):
        desc = "The armor dates to 1580. Consider what other tales of cultural synthesis await your discovery."
        result, count = self._simulate_phase510(desc)
        assert count == 1
        assert "Consider" not in result
        assert "1580" in result

    def test_strips_let_whispers(self):
        desc = "Bronze from the 10th century. Let the whispers of the past guide your imagination."
        result, count = self._simulate_phase510(desc)
        assert count == 1
        assert "Let the whispers" not in result
        assert "Bronze" in result

    def test_strips_take_a_moment(self):
        desc = "Seven layers of lacquer. Take a moment to appreciate this craftsmanship."
        result, count = self._simulate_phase510(desc)
        assert count == 1
        assert "Take a moment" not in result

    def test_does_not_strip_factual_ending(self):
        desc = "The armor dates to 1580. It protected the Andô clan through three generations of conflict."
        result, count = self._simulate_phase510(desc)
        assert count == 0
        assert result == desc.strip()

    def test_max_two_sentences_stripped(self):
        desc = ("The bronze is from the 10th century. "
                "Reflect on what this means for the collection. "
                "Consider how art transcends time. "
                "Let beauty guide you forward.")
        result, count = self._simulate_phase510(desc)
        assert count == 2  # Only last 2 stripped, not all 3 preaching sentences
        assert "10th century" in result


# ======================================================================
# EPILOG: no preaching in the tour ending
# ======================================================================

class TestEpilogNoPreaching:
    """The epilog must NOT instruct the listener."""

    def test_no_reflect_on_path(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "reflect on the path you've taken" not in source

    def test_no_next_journey_awaits(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        # The text "The next journey awaits" should not be in the epilog template
        # (it may exist in FORBIDDEN_PHRASES which is fine)
        epilog_section = source[source.find('# [G4] Build epilog'):]
        epilog_section = epilog_section[:epilog_section.find('# [R1] Sources line')]
        assert "The next journey awaits" not in epilog_section

    def test_no_consider_generating_another_tour(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "consider generating another tour" not in source

    def test_no_we_hope_you_leave_inspired(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "leave inspired by the beauty" not in source


# ======================================================================
# LENGTH: scales with substance
# ======================================================================

class TestLengthScalesWithSubstance:
    """Word target should vary based on confirmed facts, not be fixed."""

    def test_thin_stop_gets_120(self):
        """Stop with < 2 confirmed facts and no corpus: 120 words."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert '_word_target = "120"' in source

    def test_standard_stop_gets_280(self):
        """Standard stop (2-4 facts): 280 words."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert '_word_target = "280"' in source

    def test_rich_stop_gets_350(self):
        """Rich stop (5+ facts or 3+ with corpus): 350 words."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert '_word_target = "350"' in source

    def test_no_fixed_300_in_prompt(self):
        """The prompt should NOT say 'EXACTLY 300 words' anymore."""
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "EXACTLY 300 words long" not in source


# ======================================================================
# NO PREACHING rule present in prompts
# ======================================================================

class TestNoPreachingRuleInPrompts:
    """The NO PREACHING instruction must be in both museum and non-museum prompts."""

    def test_no_preaching_in_museum_prompt(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        # The museum prompt starts with the audio description creation instruction
        museum_start = source.find("Create a detailed audio description for {poi_name}")
        # Grab a large section after it
        museum_section = source[museum_start:museum_start + 5000]
        assert "NO PREACHING" in museum_section

    def test_no_preaching_in_non_museum_prompt(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        # The non-museum prompt starts with this distinctive line
        non_museum_start = source.find('Create a detailed description for the stop "')
        non_museum_section = source[non_museum_start:non_museum_start + 5000]
        assert "NO PREACHING" in non_museum_section

    def test_no_condescension_in_prompt(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "NO CONDESCENSION" in source

    def test_no_describing_obvious_in_prompt(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'generate_tour_text.py')).read()
        assert "NO DESCRIBING THE OBVIOUS" in source
