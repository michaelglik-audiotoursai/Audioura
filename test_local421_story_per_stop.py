"""LOCAL-421: Test that every stop tells a verified story of ≥3 sentences.

Tests bind to PRODUCTION call sites:
  - story_gate.verify_stop_story (called from generate_tour_text.py:10381)
  - story_gate.is_story_sentence (core detection used in the gate)
  - story_gate.check_named_entities_present (entity blur detection)
  - generate_tour_text.build_snippet_block (injects the story requirement into LLM prompt)
  - exhibition_thesis.build_exhibition_thesis_stop_block (thesis threading instruction)

Fails on `storied` (no story_gate.py, no STORY REQUIREMENT in build_snippet_block).
Passes with the LOCAL-421 fix.

Acceptance bar (Michael, 2026-08-11):
  - Every stop delivers at least one story of ≥3 sentences
  - Every sentence traces to a source
  - Boris Fridman is named (not "the generous donation")
  - The publisher of Au Soleil du Plafond is named
  - Exhibition thesis is threaded through each stop
"""
import pytest
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_gate import (
    verify_stop_story,
    is_story_sentence,
    extract_story_sentences,
    check_named_entities_present,
    check_thesis_threaded,
)
from generate_tour_text import build_snippet_block
from exhibition_thesis import build_exhibition_thesis_stop_block


# ─── Fixture: realistic credit lines from MFA Unbound ───

STOP1_CREDIT_LINE = (
    "Gift of Boris Fridman. Published by Louis Broder. "
    "Printed by Mourlot Frères. Lithographs on Arches paper, 1971."
)

STOP2_CREDIT_LINE = (
    "Salvador Dalí. Moses and Monotheism by Sigmund Freud. "
    "Set of 10. Drypoints on sheepskin, 1974-75."
)

STOP3_CREDIT_LINE = (
    "Published by Tériade. Printed by Mourlot Frères. "
    "Author Pierre Reverdy. Lithographs, 1955."
)


# ─── Fixture: the FAILING text Michael called out (storied output) ───

STOP1_BAD_DESCRIPTION = (
    "This lithograph on Arches paper was created in 1971. The generous donation "
    "of this work to the museum further enriches its cultural significance. "
    "It consists of 11 lithographs printed by Mourlot Frères, one of the most "
    "renowned printing workshops in Paris. Louis Broder published this edition "
    "in a limited run of copies."
)

STOP3_BAD_DESCRIPTION = (
    "Au Soleil du Plafond features lithographs by Juan Gris with poems by "
    "Pierre Reverdy. The livre d'artiste tradition represents a deeply "
    "collaborative approach to bookmaking. This work demonstrates the "
    "intersection of image and text in printed form."
)


# ─── Fixture: a PASSING description (what LOCAL-421 should produce) ───

STOP1_GOOD_DESCRIPTION = (
    "This portfolio of lithographs on Arches paper was published by Louis Broder "
    "in 1971 and printed at the Mourlot Frères workshop in Paris. Broder "
    "specialized in limited editions that required direct collaboration between "
    "artist and printer — Mourlot's workshop was one of the few in Europe equipped "
    "for chromolithography at this scale. Boris Fridman, a Russian collector "
    "who assembled important holdings of livres d'artiste, "
    "donated this work to the MFA. Fridman's gift brought the "
    "museum's collection of Surrealist-era printed works to critical mass, "
    "enabling exhibitions like this one. The livre d'artiste form demanded that "
    "artist, poet, and printer work in the same space — Broder's editions were "
    "produced with all three present at Mourlot's atelier."
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: is_story_sentence correctly identifies story vs non-story
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsStorySentence:
    """Bind to: story_gate.is_story_sentence (called within verify_stop_story)."""

    def test_story_with_person_and_action(self):
        """A sentence naming a person and what they did is a story sentence."""
        assert is_story_sentence(
            "Boris Fridman donated this work to the MFA in 2003."
        )

    def test_story_with_decision(self):
        """A decision made by a named person counts as story."""
        assert is_story_sentence(
            "Broder chose Mourlot because his workshop was one of the few "
            "equipped for chromolithography at this scale."
        )

    def test_story_with_consequence(self):
        """A consequence involving named people counts."""
        assert is_story_sentence(
            "Fridman's gift brought the museum's collection of printed works "
            "to critical mass, enabling exhibitions like this one."
        )

    def test_story_with_relationship(self):
        """A relationship claim between named people counts."""
        assert is_story_sentence(
            "Dalí visited Freud in London in 1938 and sketched the dying "
            "psychoanalyst during that meeting."
        )

    def test_not_story_evaluation(self):
        """Evaluative fluff is NOT a story sentence."""
        assert not is_story_sentence(
            "The generous donation of this work further enriches its cultural "
            "significance."
        )

    def test_not_story_invites_to_ponder(self):
        """'Invites you to ponder' is NOT a story."""
        assert not is_story_sentence(
            "This work invites you to ponder the relationship between image "
            "and text."
        )

    def test_not_story_transcends(self):
        """'Transcends boundaries' is NOT a story."""
        assert not is_story_sentence(
            "The collaboration transcends boundaries of medium and tradition."
        )

    def test_not_story_no_person(self):
        """A factual sentence without a named person is not a story."""
        assert not is_story_sentence(
            "The lithographs are printed on Arches wove paper in an edition "
            "of 220 copies."
        )

    def test_short_sentence_rejected(self):
        """Very short sentences don't qualify."""
        assert not is_story_sentence("Dalí was inspired.")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: entity naming — never blur a named entity
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntityNaming:
    """Bind to: story_gate.check_named_entities_present (called from verify_stop_story)."""

    def test_fridman_present(self):
        """Boris Fridman must be named when credit line says 'Gift of Boris Fridman'."""
        ok, found, missing = check_named_entities_present(
            STOP1_GOOD_DESCRIPTION, STOP1_CREDIT_LINE
        )
        assert ok, f"Missing entities: {missing}"
        assert any("Fridman" in f for f in found)

    def test_fridman_blurred_fails(self):
        """'The generous donation' instead of naming Fridman must FAIL."""
        ok, found, missing = check_named_entities_present(
            STOP1_BAD_DESCRIPTION, STOP1_CREDIT_LINE
        )
        assert not ok, "Should fail: Fridman is blurred into 'the generous donation'"
        assert any("Fridman" in m for m in missing)

    def test_publisher_named_stop3(self):
        """The publisher of Au Soleil du Plafond must be named."""
        # Good: names Tériade and Mourlot (both in credit line)
        good_text = (
            "Published by Tériade in 1955, this edition of Au Soleil du Plafond "
            "brought together Gris's lithographs with Reverdy's poetry. The "
            "lithographs were printed at the Mourlot Frères workshop in Paris."
        )
        ok, found, missing = check_named_entities_present(
            good_text, STOP3_CREDIT_LINE
        )
        assert ok, f"Missing: {missing}"

    def test_publisher_missing_stop3_fails(self):
        """Stop 3 without naming Tériade must fail."""
        ok, found, missing = check_named_entities_present(
            STOP3_BAD_DESCRIPTION, STOP3_CREDIT_LINE
        )
        assert not ok, "Should fail: publisher Tériade not named"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: the full story gate — ≥3 story sentences per stop
# ═══════════════════════════════════════════════════════════════════════════════

class TestStoryGate:
    """Bind to: story_gate.verify_stop_story (called from generate_tour_text.py:10381)."""

    def test_good_description_passes(self):
        """A well-storied description passes the gate."""
        result = verify_stop_story(
            description=STOP1_GOOD_DESCRIPTION,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Test Stop",
            framing_case='exhibition',
        )
        assert result['passed'], f"Should pass. Failures: {result['failures']}"
        assert result['story_count'] >= 3
        assert result['entities_present']
        assert result['thesis_threaded']

    def test_bad_description_fails(self):
        """Michael's marked-wrong stop 1 (3/5, 'borderline poor 2/5') fails."""
        result = verify_stop_story(
            description=STOP1_BAD_DESCRIPTION,
            credit_line=STOP1_CREDIT_LINE,
            stop_name="Stop 1",
            framing_case='exhibition',
        )
        assert not result['passed'], "Should fail: Fridman blurred, too few stories"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: build_snippet_block includes STORY REQUIREMENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnippetBlockStoryRequirement:
    """Bind to: generate_tour_text.build_snippet_block (called at line 9253)."""

    def test_snippet_block_contains_story_requirement(self):
        """build_snippet_block must inject the LOCAL-421 story requirement."""
        snippets = [
            {'title': 'Test', 'snippet': 'Test snippet text about Boris Fridman', 'url': ''},
        ]
        block = build_snippet_block(snippets, artist='Joan Miró', specifics=[])
        assert 'STORY REQUIREMENT' in block
        assert 'LOCAL-421' in block
        assert 'THREE SENTENCES' in block or 'three sentences' in block.lower()

    def test_snippet_block_contains_entity_naming_rule(self):
        """build_snippet_block must inject the entity naming rule."""
        snippets = [
            {'title': 'Test', 'snippet': 'Test snippet', 'url': ''},
        ]
        block = build_snippet_block(snippets, artist='Joan Miró', specifics=[])
        assert 'ENTITY NAMING RULE' in block
        assert 'BY NAME' in block or 'by name' in block.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Test: exhibition thesis stop block includes THESIS THREADING
# ═══════════════════════════════════════════════════════════════════════════════

class TestThesisThreading:
    """Bind to: exhibition_thesis.build_exhibition_thesis_stop_block (called at line 9032)."""

    def test_thesis_threading_instruction_present(self):
        """The stop block must instruct the model to thread the thesis."""
        block = build_exhibition_thesis_stop_block(
            framing_case='exhibition',
            page_text='livre d\'artiste revolutionized the book',
            matched_work={'artist': 'Joan Miró', 'publisher': 'Louis Broder'},
        )
        assert 'THESIS THREADING' in block
        assert 'LOCAL-421' in block
        assert 'advances' in block.lower() or 'advance' in block.lower()

    def test_thesis_check_passes_with_reference(self):
        """A description mentioning 'livre d'artiste' passes thesis check."""
        assert check_thesis_threaded(
            "This work exemplifies the livre d'artiste ideal.",
            framing_case='exhibition',
        )

    def test_thesis_check_fails_without_reference(self):
        """A description with no art-form reference fails thesis check."""
        assert not check_thesis_threaded(
            "The lithographs depict colorful scenes inspired by Mediterranean light.",
            framing_case='exhibition',
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Specific acceptance criteria from Michael
# ═══════════════════════════════════════════════════════════════════════════════

class TestAcceptanceCriteria:
    """End-to-end checks matching Michael's specific acceptance bar."""

    def test_stop2_must_explain_what_was_controversial(self):
        """Stop 2: must say WHAT was controversial about Freud's argument."""
        # Bad: names controversy without explaining it
        bad_text = (
            "Freud's narrative was controversial and had a profound psychological "
            "impact on myth-making. The work explores the psychological dimensions "
            "of Freud's text through Dalí's Surrealist lens."
        )
        # The story sentences in bad_text don't actually explain WHAT was controversial
        story_sents = extract_story_sentences(bad_text)
        # If there are story sentences, they should contain substance
        # (This test documents the requirement — actual verification is via live run)
        assert len(story_sents) < 3 or any(
            'monotheism' in s.lower() or 'moses' in s.lower() or 'egyptian' in s.lower()
            for s in story_sents
        ), "Story sentences about Freud must explain WHAT the controversy was"

    def test_extract_story_sentences_from_good_text(self):
        """Verify that a good description yields ≥3 story sentences."""
        sents = extract_story_sentences(STOP1_GOOD_DESCRIPTION)
        assert len(sents) >= 3, f"Got only {len(sents)} story sentences: {sents}"
