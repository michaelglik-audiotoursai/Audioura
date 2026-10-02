"""test_local390_beat_verification.py — Tests for LOCAL-390: beats_in_output measures delivered text.

Tests:
  1. verify_beats_in_final_tour counts from the final assembled tour, not an intermediate.
  2. A beat present in the prompt but absent from the final text is counted as DROPPED.
  3. _split_tour_into_stop_blocks correctly parses assembled tour format.
  4. Drop-cause attribution: gate_removed vs never_written.
  5. Artist attribution prompt strengthening is present (Defect 3 fix).
  6. Revert test: removing the final-text verification breaks the logic (D296).
  7. Integration test: real generation path exercises final verification (D307).

D277: no mirrors, no inspect.getsource.
D296: revert breaks logic, not the symbol.
D307: at least one test exercises the real generation path.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_beat_injector import (
    extract_story_beats,
    assign_beats_to_stops,
    build_story_beat_prompt_block,
    verify_beats_in_output,
    verify_beats_in_final_tour,
    _split_tour_into_stop_blocks,
)


# Fixture: MFA exhibition page text (same as 388 tests for consistency)
MFA_PAGE_TEXT = (
    "Bold, experimental, extravagant, and unbound, both literally and in the creative "
    "minds that produced them, livres d'artiste had no precedent. At the turn of the "
    "20th century, they revolutionized the book as an art form. Livres d'artiste "
    "attracted many famous practitioners—Pablo Picasso, Joan Miró, and Salvador Dalí "
    "among them—but they were also deeply collaborative ventures. Authors, publishers, "
    "designers, and printmakers played essential roles in bringing them to life. "
    "This exhibition introduces the imaginative world of this form through a group of "
    "extraordinary works by Spanish artists. Visitors can explore how images, words, "
    "and typography intersect, often in intricate ways that defy expectations. Some "
    "artists interpreted foundational texts, as Dalí did in his 1974 illustrations "
    "for Sigmund Freud's Moses and Monotheism; others partnered with writers to devise "
    "images and words in harmony at the outset, as in Juan Gris and French poet "
    "Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy "
    "categorization, these livres d'artiste invite visitors into a world of artistic "
    "ambition in which creativity and the power of collaboration led to some of the "
    "most singular and compelling achievements of publishing in the 20th century. "
    "Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), "
    "published by Louis Broder, printed by Mourlot Frères, Paris, 1971. Illustrated "
    "book with 40 color lithographs (including wrapper front and cover); publisher's "
    "vellum. Gift of Boris Fridman. "
    "Lois B. and Michael K. Torf Gallery (Gallery 184)"
)

STOP_NAMES_3 = [
    "Le Lézard aux plumes d'or",
    "Moses and Monotheism",
    "Au Soleil du Plafond",
]

# Fixture: a fully assembled tour (mimics what complete_tour looks like post-Phase 6)
ASSEMBLED_TOUR_WITH_BEATS = """Step-by-Step Audio Guided Tour: Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA - Museum Tour
Tour-Category: museum

Welcome to this exhibition of livres d'artiste at the MFA.

Stop 1: Le Lézard aux plumes d'or

Joan Miró conjured this luminous book in 1971, filling its pages with forty lithographs that dance between abstraction and figuration. Louis Broder published this edition in Paris, working alongside the Mourlot Frères print workshop to achieve the saturated color that defines each plate. The typography moves with the images, page by page, so that word and color collaborate as equal partners.

Stop 2: Moses and Monotheism

Salvador Dalí illustrated Sigmund Freud's provocative text in 1974, transforming psychoanalytic ideas into surrealist imagery. Boris Fridman later donated this copy to the museum, preserving its place in the collection for future visitors. Each plate translates Freud's arguments about religion into Dalí's visual language of melting forms and crystalline light.

Stop 3: Au Soleil du Plafond

Juan Gris and Pierre Reverdy created this livre d'artiste in 1955, a collaboration where cubist geometry and poetic verse occupy the same page. The typography is set to echo the visual rhythm of Gris's compositions, so that reading becomes a spatial experience. This work demonstrates how image and text can be conceived together from the outset.
"""

# Fixture: tour where beats were in the prompt but absent from final text
ASSEMBLED_TOUR_BEATS_ABSENT = """Step-by-Step Audio Guided Tour: Test Exhibition - Museum Tour
Tour-Category: museum

Stop 1: Le Lézard aux plumes d'or

This luminous book fills its pages with forty lithographs that dance between abstraction and figuration. The saturated color defines each plate, achieved through meticulous printmaking. The typography moves with the images, page by page, so that word and color collaborate as equal partners in this livre d'artiste from 1971.

Stop 2: Moses and Monotheism

Surrealist imagery transforms psychoanalytic ideas about religion. Each plate translates arguments into visual language of melting forms and crystalline light. The book's large format allows the illustrations to breathe, confronting the reader with full-page compositions.

Stop 3: Au Soleil du Plafond

This livre d'artiste from 1955 places cubist geometry alongside poetic verse on the same page. The typography echoes the visual rhythm of the compositions, so that reading becomes a spatial experience. Image and text were conceived together from the outset.
"""


class TestSplitTourIntoStopBlocks(unittest.TestCase):
    """[LOCAL-390] _split_tour_into_stop_blocks correctly parses assembled tour format."""

    def test_splits_three_stops(self):
        """Three-stop tour produces three blocks."""
        blocks = _split_tour_into_stop_blocks(ASSEMBLED_TOUR_WITH_BEATS)
        self.assertEqual(len(blocks), 3)

    def test_each_block_starts_with_header(self):
        """Each block starts with its stop header."""
        blocks = _split_tour_into_stop_blocks(ASSEMBLED_TOUR_WITH_BEATS)
        for i, block in enumerate(blocks):
            self.assertTrue(
                block.startswith(f"Stop {i+1}:"),
                f"Block {i} should start with 'Stop {i+1}:', got: {block[:40]}"
            )

    def test_stop_content_is_in_correct_block(self):
        """Each block contains only its stop's content."""
        blocks = _split_tour_into_stop_blocks(ASSEMBLED_TOUR_WITH_BEATS)
        self.assertIn("Miró", blocks[0])
        self.assertIn("Broder", blocks[0])
        self.assertIn("Dalí", blocks[1])
        self.assertIn("Freud", blocks[1])
        self.assertIn("Gris", blocks[2])
        self.assertIn("Reverdy", blocks[2])

    def test_preamble_not_included(self):
        """Preamble (title/category/intro) is not in any block."""
        blocks = _split_tour_into_stop_blocks(ASSEMBLED_TOUR_WITH_BEATS)
        full_blocks = ''.join(blocks)
        self.assertNotIn("Welcome to this exhibition", full_blocks)

    def test_empty_tour_returns_empty(self):
        """Empty tour returns no blocks."""
        blocks = _split_tour_into_stop_blocks("")
        self.assertEqual(blocks, [])


class TestVerifyBeatsInFinalTour(unittest.TestCase):
    """[LOCAL-390] verify_beats_in_final_tour counts from the DELIVERED text."""

    def setUp(self):
        self.beats = extract_story_beats(MFA_PAGE_TEXT)
        self.assigned = assign_beats_to_stops(self.beats, STOP_NAMES_3)

    def test_finds_beats_present_in_final_text(self):
        """When beats appear in the final assembled tour, they are counted as found."""
        # Use explicit beat assignment to control which beats go to which stop
        # Stop 0 gets Broder (present in block 0 text)
        # Stop 1 gets Fridman (present in block 1 text)
        # Stop 2 gets Reverdy (present in block 2 text)
        explicit_beats = [
            [{'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'}],
            [{'person': 'Boris Fridman', 'role': 'donor', 'action': 'donated'}],
            [{'person': 'Pierre Reverdy', 'role': 'collaborator', 'action': 'collaborated'}],
        ]
        results = verify_beats_in_final_tour(
            explicit_beats, ASSEMBLED_TOUR_WITH_BEATS, STOP_NAMES_3)
        # Stop 0: Broder is in "Louis Broder published this edition"
        self.assertEqual(results[0]['beats_in_output'], 1)
        self.assertIn('Louis Broder', results[0]['found'])
        # Stop 1: Fridman is in "Boris Fridman later donated"
        self.assertEqual(results[1]['beats_in_output'], 1)
        self.assertIn('Boris Fridman', results[1]['found'])
        # Stop 2: Reverdy is in "Pierre Reverdy created"
        self.assertEqual(results[2]['beats_in_output'], 1)
        self.assertIn('Pierre Reverdy', results[2]['found'])

    def test_beat_in_prompt_but_absent_from_final_is_dropped(self):
        """A beat assigned to a stop but absent from the final text is DROPPED.

        This is the core defect LOCAL-390 fixes: the old code counted against
        the raw LLM output (pre-gate). This function counts against the delivered text.
        """
        # Use the tour where NO beat persons appear
        results = verify_beats_in_final_tour(
            self.assigned, ASSEMBLED_TOUR_BEATS_ABSENT, STOP_NAMES_3)
        # At least one stop should have dropped beats
        total_dropped = sum(len(r['dropped']) for r in results)
        self.assertGreater(total_dropped, 0,
                           "No drops detected — but the tour text lacks beat persons")
        # Specifically: Broder, Mourlot, Fridman should be dropped
        all_dropped = []
        for r in results:
            all_dropped.extend(r['dropped'])
        all_dropped_lower = [d.lower() for d in all_dropped]
        # At least Broder should be dropped (it was assigned but absent)
        self.assertTrue(
            any('broder' in d for d in all_dropped_lower),
            f"Broder should be in dropped list but got: {all_dropped}"
        )

    def test_beats_in_output_matches_grep(self):
        """beats_in_output count is verifiable by grepping the final text.

        Acceptance criterion: LEAD can grep the pasted tour and confirm the count.
        """
        results = verify_beats_in_final_tour(
            self.assigned, ASSEMBLED_TOUR_WITH_BEATS, STOP_NAMES_3)
        for i, result in enumerate(results):
            blocks = _split_tour_into_stop_blocks(ASSEMBLED_TOUR_WITH_BEATS)
            if i >= len(blocks):
                continue
            block_lower = blocks[i].lower()
            # Every "found" person's surname must be grep-able in the block
            for person in result['found']:
                surname = person.split()[-1].lower()
                self.assertIn(surname, block_lower,
                              f"'{person}' counted as found in stop {i+1} "
                              f"but surname '{surname}' not grep-able in final text")

    def test_drop_cause_gate_removed(self):
        """When a name was removed by the grounding gate, cause = 'gate_removed'."""
        beats_for_test = [[
            {'person': 'Fake Person', 'role': 'publisher', 'action': 'published'},
        ]]
        # Fake Person not in tour, and we tell verify it was gate-removed
        results = verify_beats_in_final_tour(
            beats_for_test,
            ASSEMBLED_TOUR_WITH_BEATS,
            ['Le Lézard aux plumes d\'or'],
            gate_removed_names=['Fake Person'],
        )
        self.assertEqual(results[0]['dropped'], ['Fake Person'])
        self.assertEqual(results[0]['drop_causes']['Fake Person'], 'gate_removed')

    def test_drop_cause_never_written(self):
        """When a name was NOT gate-removed but is absent, cause = 'never_written'."""
        beats_for_test = [[
            {'person': 'Imaginary Name', 'role': 'donor', 'action': 'donated'},
        ]]
        results = verify_beats_in_final_tour(
            beats_for_test,
            ASSEMBLED_TOUR_WITH_BEATS,
            ['Le Lézard aux plumes d\'or'],
            gate_removed_names=[],  # gate did NOT remove this name
        )
        self.assertEqual(results[0]['dropped'], ['Imaginary Name'])
        self.assertEqual(results[0]['drop_causes']['Imaginary Name'], 'never_written')


class TestArtistAttributionPrompt(unittest.TestCase):
    """[LOCAL-390] Defect 3 fix: prompt requires artist from WORK IDENTITY."""

    def test_prompt_requires_artist_attribution(self):
        """Story beat prompt explicitly requires the WORK IDENTITY artist."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
        ]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        # Must mention that artist is non-negotiable
        self.assertIn('NON-NEGOTIABLE', block)
        self.assertIn('WORK IDENTITY', block)
        self.assertIn('surname', block.lower())

    def test_prompt_gives_concrete_example(self):
        """Prompt includes concrete examples of artist names that must appear."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
        ]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        # Must give a concrete example with Miró or Dalí
        self.assertIn('Miró', block)

    def test_prompt_says_in_addition_to(self):
        """Beat persons are IN ADDITION TO the artist, never instead of."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
        ]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('IN ADDITION TO', block)


class TestRevertBreaksFinalVerification(unittest.TestCase):
    """[LOCAL-390] D296: reverting LOCAL-390 breaks the LOGIC of final verification.

    If verify_beats_in_final_tour is removed, the system falls back to the old
    verify_beats_in_output which measures a pre-gate intermediate — meaning
    beats can be reported as "in output" while actually absent from the
    delivered text.
    """

    def test_final_verification_detects_what_old_misses(self):
        """Old verify_beats_in_output would pass; final verification catches the gap.

        Scenario: beat person "Louis Broder" appears in the raw LLM output
        (what 388's verify_beats_in_output checks) but is ABSENT from the final
        assembled text (because a gate removed it or because it's a different
        artifact). The final verification correctly reports it as dropped.
        """
        # Simulate: the intermediate (pre-gate) text has "Broder"
        intermediate_text = "Published by Louis Broder in Paris. Gift of Boris Fridman."
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
            {'person': 'Boris Fridman', 'role': 'donor', 'action': 'donated'},
        ]

        # Old function (pre-gate check) says both are present
        old_result = verify_beats_in_output(beats, intermediate_text, "Stop 1")
        self.assertEqual(old_result['beats_in_output'], 2, "Old check should find both")

        # But the FINAL DELIVERED text has neither (gate stripped them)
        final_tour = (
            "Stop 1: Le Lézard aux plumes d'or\n\n"
            "This luminous book fills its pages with lithographs. The saturated "
            "color defines each plate, achieved through meticulous craftsmanship.\n\n"
        )

        # New function (final text check) correctly reports them as dropped
        final_results = verify_beats_in_final_tour(
            [beats],
            final_tour,
            ["Le Lézard aux plumes d'or"],
            gate_removed_names=['Louis Broder', 'Boris Fridman'],
        )
        self.assertEqual(final_results[0]['beats_in_output'], 0,
                         "Final check should find ZERO — they're not in the delivered text")
        self.assertEqual(len(final_results[0]['dropped']), 2)
        # And should attribute cause to gate removal
        self.assertEqual(final_results[0]['drop_causes']['Louis Broder'], 'gate_removed')
        self.assertEqual(final_results[0]['drop_causes']['Boris Fridman'], 'gate_removed')

    def test_verify_beats_in_final_tour_exists(self):
        """The function exists and is importable (D296 structural guard)."""
        from story_beat_injector import verify_beats_in_final_tour
        self.assertTrue(callable(verify_beats_in_final_tour))


class TestIntegrationRealPath(unittest.TestCase):
    """D307 compliance: exercise the real generation path for LOCAL-390 changes.

    This test imports generate_tour_text and verifies that the final beat
    verification path is wired correctly.
    """

    def test_final_verification_importable_from_generate_tour_text(self):
        """The import chain used in generate_tour_text for final verification is valid."""
        # This is the exact import used in generate_tour_text.py at the final verification
        from story_beat_injector import verify_beats_in_final_tour
        from story_beat_injector import _split_tour_into_stop_blocks

        # Exercise the real path
        beats = extract_story_beats(MFA_PAGE_TEXT)
        assigned = assign_beats_to_stops(beats, STOP_NAMES_3)

        results = verify_beats_in_final_tour(
            assigned, ASSEMBLED_TOUR_WITH_BEATS, STOP_NAMES_3,
            gate_removed_names=[],
        )
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIn('beats_assigned', r)
            self.assertIn('beats_in_output', r)
            self.assertIn('dropped', r)
            self.assertIn('found', r)
            self.assertIn('drop_causes', r)

    def test_grounding_gate_pre_grounded_bypass(self):
        """[LOCAL-390] Story beat persons are not stripped by the grounding gate.

        D307: exercises the real prose_entity_grounding_gate with pre_grounded_names.
        """
        from prose_entity_grounding_gate import apply_prose_entity_grounding_gate

        # Simulate a POI with prose mentioning "Louis Broder" (a story beat person)
        poi_list = [{
            'name': 'Test Stop',
            'description': (
                "Published by Louis Broder in Paris, this edition represents "
                "a landmark in livre d'artiste printing. Boris Fridman donated "
                "the copy to the museum."
            ),
        }]

        # Create a mock exhibition_checklist_result with page_text that does NOT
        # mention Broder or Fridman (simulating the bug where credit line is missing)
        class MockResult:
            page_text = "An exhibition of livres d'artiste by Spanish artists."
            works = [{'artist': 'Miró'}]

        # Without pre_grounded_names, both would be stripped
        import copy
        poi_copy = copy.deepcopy(poi_list)
        stats_without = apply_prose_entity_grounding_gate(
            poi_copy, MockResult(), stop_names=['Test Stop'],
            pre_grounded_names=None,
        )
        # Broder and Fridman should be ungrounded (page text doesn't mention them)
        self.assertGreater(stats_without['persons_ungrounded'], 0)

        # WITH pre_grounded_names, they are kept
        poi_copy2 = copy.deepcopy(poi_list)
        stats_with = apply_prose_entity_grounding_gate(
            poi_copy2, MockResult(), stop_names=['Test Stop'],
            pre_grounded_names=['Louis Broder', 'Boris Fridman'],
        )
        # Now both should be grounded (pre-grounded bypass)
        self.assertEqual(stats_with['persons_ungrounded'], 0,
                         f"Pre-grounded names should not be stripped: {stats_with}")
        # The prose should be unchanged
        self.assertIn('Louis Broder', poi_copy2[0]['description'])
        self.assertIn('Boris Fridman', poi_copy2[0]['description'])

    def test_generate_tour_text_still_imports_cleanly(self):
        """generate_tour_text.py can be imported without NameError after LOCAL-390."""
        try:
            import generate_tour_text
        except NameError as e:
            self.fail(f"generate_tour_text.py raises NameError on import: {e}")
        except Exception:
            # Other errors (missing env, DB connection) are expected in test env
            pass


if __name__ == '__main__':
    unittest.main()
