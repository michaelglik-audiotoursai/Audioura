#!/usr/bin/env python3
"""tests/test_local352_narrative_arc.py — LOCAL-352: Story not credential.

The defect: corpus contains narrative arcs (a person leaving, founding,
recommending) but the composition prompt only asks for "facts, dates, or
claims" (LOCAL-345). The LLM satisfies that by extracting a single credential
("Michelin-starred chef") rather than preserving the event sequence ("left
the Negresco to cook for twenty people").

These tests verify:
  1. format_passages_for_prompt includes a narrative-arc directive
  2. The directive explicitly mentions sequences of events, not just facts
  3. The directive is not restricted to owners — visitors/critics/chefs count
  4. The directive forbids inventing motivation or facts beyond corpus
  5. Museum 8-stop and 4-stop bounds remain stable (D258)

Tests MUST import production code and MUST fail against the pre-LOCAL-352
codebase (the NARRATIVE ARC RULE does not exist on the storied branch).
"""
import os
import sys
import re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. format_passages_for_prompt includes a narrative-arc directive
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarrativeArcDirectivePresent:
    """The injected corpus block must instruct the LLM to preserve event
    sequences from passages, not collapse them into credentials/attributes.

    This test fails on the unfixed code because the NARRATIVE ARC RULE
    string does not exist in stop_corpus_reader.py before LOCAL-352.
    """

    @pytest.fixture
    def corpus_block(self):
        """Generate a corpus prompt block with passages containing a narrative arc."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': [
                "Run since 1996 by chef Dominique Le Stanc. Le Stanc's position is "
                "more perverse than that. He used to be the head chef at the Negresco's "
                "infamous Chantecler with its airs and graces. He gave it all up to "
                "cook in a cramped kitchen for just twenty covers.",
                "In Niçois language, 'merenda' means workman's snack.",
            ],
            'sources': [
                {'url': 'https://example.com/nice-food', 'tier': 2, 'title': 'Nice Food Guide'}
            ],
            'passage_roles': [
                {'role': 'about_subject'},
                {'role': 'about_subject'},
            ],
        }
        return format_passages_for_prompt(corpus_data, "La Merenda")

    def test_narrative_arc_rule_exists(self, corpus_block):
        """The output must contain a NARRATIVE ARC RULE heading."""
        assert 'NARRATIVE ARC RULE' in corpus_block, (
            "format_passages_for_prompt must include a NARRATIVE ARC RULE directive. "
            "This fails on the unfixed code (pre-LOCAL-352) because the rule does not exist."
        )

    def test_directive_mentions_sequence(self, corpus_block):
        """The directive must explicitly ask for event sequences, not just facts."""
        block_lower = corpus_block.lower()
        sequence_terms = ['sequence', 'doing something', 'leaving', 'founding', 'what happened']
        has_sequence_language = any(term in block_lower for term in sequence_terms)
        assert has_sequence_language, (
            "NARRATIVE ARC RULE must ask for sequences of events, not just facts. "
            f"None of {sequence_terms} found in the directive."
        )

    def test_directive_not_owner_restricted(self, corpus_block):
        """The directive must explicitly cover visitors, critics, and chefs from elsewhere."""
        block_lower = corpus_block.lower()
        # Must mention that this applies beyond owners
        non_owner_terms = ['visitor', 'critic', 'chef', 'not only owner']
        has_non_owner = any(term in block_lower for term in non_owner_terms)
        assert has_non_owner, (
            "NARRATIVE ARC RULE must not be restricted to owners. "
            "Must mention visitors, critics, or chefs from elsewhere."
        )

    def test_directive_forbids_invention(self, corpus_block):
        """The directive must forbid inventing motivation or facts beyond corpus."""
        block_lower = corpus_block.lower()
        # Must mention grounding constraint — no invented motivation
        forbid_terms = ['must come from', 'not infer', 'not stated in']
        has_forbid = any(term in block_lower for term in forbid_terms)
        assert has_forbid, (
            "NARRATIVE ARC RULE must forbid inventing facts/motivation beyond corpus."
        )

    def test_credential_vs_story_example(self, corpus_block):
        """The directive must contrast credential-style vs story-style output."""
        # Must contain both a bad example (credential) and a good one (narrative)
        has_credential_example = 'credential' in corpus_block.lower() or 'adjective' in corpus_block.lower()
        has_narrative_example = 'story' in corpus_block.lower() or 'sequence' in corpus_block.lower()
        assert has_credential_example and has_narrative_example, (
            "NARRATIVE ARC RULE must contrast credential-style (bad) with "
            "narrative-style (good) output."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Passages with no narrative arc do NOT trigger extra requirements
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarrativeArcAlwaysPresent:
    """The NARRATIVE ARC RULE is always injected (it's a composition instruction,
    not conditional on passage content), but it only fires when the corpus
    actually contains events. A passage with just facts (dates, numbers) still
    gets the rule, which is fine — it's a no-op when there's nothing to narrate.
    """

    def test_factual_passages_still_get_rule(self):
        """Even purely factual passages get the NARRATIVE ARC RULE (it's unconditional)."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': [
                "The cathedral was built in 1650. Its dome is 28 meters high.",
            ],
            'sources': [{'url': 'https://example.com', 'tier': 2, 'title': 'Test'}],
            'passage_roles': [{'role': 'about_subject'}],
        }
        result = format_passages_for_prompt(corpus_data, "Nice Cathedral")
        assert 'NARRATIVE ARC RULE' in result, (
            "NARRATIVE ARC RULE must appear even for factual-only passages."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Le Safari case: critic recommendation must not be flattened
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeSafariNarrativeCase:
    """The Le Safari corpus contains 'Colman Andrews: A three-star chef
    introduced me to the pizza at Le Safari' — a named food writer recounting
    a named chef's recommendation. The directive must instruct the model to
    tell this as an EVENT, not flatten it to 'a popular restaurant'.
    """

    def test_recommending_verb_in_directive(self):
        """The directive must explicitly mention 'recommending' as a narrative trigger."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': [
                "Colman Andrews: A three-star chef introduced me to the pizza at Le Safari.",
            ],
            'sources': [{'url': 'https://example.com/food', 'tier': 2, 'title': 'Food Writer'}],
            'passage_roles': [{'role': 'about_subject'}],
        }
        result = format_passages_for_prompt(corpus_data, "Le Safari")
        assert 'NARRATIVE ARC RULE' in result
        # The rule must mention 'recommending' as a narrative trigger
        assert 'recommending' in result.lower(), (
            "NARRATIVE ARC RULE must list 'recommending' as one of the "
            "narrative actions that trigger arc preservation."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BODY USAGE RULE still present (LOCAL-345 not regressed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBodyUsageRuleNotRegressed:
    """LOCAL-345's BODY USAGE RULE must still be present alongside the new
    NARRATIVE ARC RULE. They serve different purposes:
    - BODY USAGE: corpus must reach the body (not just orientation)
    - NARRATIVE ARC: when corpus has a story, tell it as a story
    """

    def test_both_rules_present(self):
        """Both BODY USAGE RULE and NARRATIVE ARC RULE must coexist."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': ["The chef left his previous position in 1996."],
            'sources': [{'url': 'https://example.com', 'tier': 2, 'title': 'Test'}],
            'passage_roles': [{'role': 'about_subject'}],
        }
        result = format_passages_for_prompt(corpus_data, "Test Stop")
        assert 'BODY USAGE RULE' in result, "LOCAL-345 BODY USAGE RULE must not be removed"
        assert 'NARRATIVE ARC RULE' in result, "LOCAL-352 NARRATIVE ARC RULE must be present"
        assert 'GROUNDING RULE' in result, "D50 GROUNDING RULE must not be removed"

    def test_grounding_before_arc(self):
        """GROUNDING RULE and BODY USAGE come before NARRATIVE ARC
        (arc supplements, does not replace grounding)."""
        from stop_corpus_reader import format_passages_for_prompt

        corpus_data = {
            'passages': ["Chef left the Negresco in 1996."],
            'sources': [{'url': 'https://example.com', 'tier': 2, 'title': 'Test'}],
            'passage_roles': [{'role': 'about_subject'}],
        }
        result = format_passages_for_prompt(corpus_data, "La Merenda")
        grounding_pos = result.find('GROUNDING RULE')
        body_pos = result.find('BODY USAGE RULE')
        arc_pos = result.find('NARRATIVE ARC RULE')
        assert grounding_pos < body_pos < arc_pos, (
            f"Expected GROUNDING ({grounding_pos}) < BODY USAGE ({body_pos}) "
            f"< NARRATIVE ARC ({arc_pos})"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Museum bounds (D258 regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMuseumBoundsUnaffected:
    """Museum stops are objects, not people. The NARRATIVE ARC RULE should be
    largely a no-op for museum stops. Bounds: 8-stop >= 75.0, 4-stop >= 81.2.
    """

    @pytest.fixture
    def scorer(self):
        from tour_rubric_scorer import score_tour_file
        return score_tour_file

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )),
        reason="8-stop museum tour file not available"
    )
    def test_museum_8stop_bound(self, scorer):
        """Museum 8-stop tour must score >= 75.0 (D258)."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL262_asian_arts_8stop_restored.txt'
        )
        result = scorer(tour_file, n_requested=8)
        assert result.total_score >= 75.0, (
            f"Museum 8-stop scored {result.total_score}, expected >= 75.0"
        )

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL258_asian_arts_4stop.txt'
        )),
        reason="4-stop museum tour file not available"
    )
    def test_museum_4stop_bound(self, scorer):
        """Museum 4-stop tour must score >= 81.2 (D258)."""
        tour_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tours', 'LOCAL258_asian_arts_4stop.txt'
        )
        result = scorer(tour_file, n_requested=4)
        assert result.total_score >= 81.2, (
            f"Museum 4-stop scored {result.total_score}, expected >= 81.2"
        )
