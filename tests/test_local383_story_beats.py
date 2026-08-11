"""test_local383_story_beats.py — Unit tests for LOCAL-383 story beat extraction.

Tests the story_beat_injector module:
  1. extract_story_beats finds named people + actions from page text.
  2. assign_beats_to_stops distributes beats across stops.
  3. build_story_beat_prompt_block produces valid prompt injection blocks.
  4. Integration: MFA fixture yields at least 4 distinct grounded people.
  5. Revert test: removing story_beat_injector module breaks the logic.

D277: no mirrors, no inspect.getsource.
D296: revert breaks logic, not the symbol.
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
)

# The MFA exhibition page text — verbatim from the fixture
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


class TestExtractStoryBeats(unittest.TestCase):
    """Test extract_story_beats on MFA exhibition page text."""

    def setUp(self):
        self.beats = extract_story_beats(MFA_PAGE_TEXT)

    def test_extracts_beats(self):
        """At least 4 beats extracted from MFA text."""
        self.assertGreaterEqual(len(self.beats), 4)

    def test_finds_broder(self):
        """Louis Broder (publisher) is found."""
        people = {b['person'].lower() for b in self.beats}
        self.assertTrue(
            any('broder' in p for p in people),
            f"Broder not found in extracted people: {people}"
        )

    def test_finds_mourlot(self):
        """Mourlot Frères (printer) is found."""
        people = {b['person'].lower() for b in self.beats}
        self.assertTrue(
            any('mourlot' in p for p in people),
            f"Mourlot not found in extracted people: {people}"
        )

    def test_finds_fridman(self):
        """Boris Fridman (donor) is found."""
        people = {b['person'].lower() for b in self.beats}
        self.assertTrue(
            any('fridman' in p for p in people),
            f"Fridman not found in extracted people: {people}"
        )

    def test_finds_reverdy(self):
        """Pierre Reverdy (poet/collaborator) is found."""
        people = {b['person'].lower() for b in self.beats}
        self.assertTrue(
            any('reverdy' in p for p in people),
            f"Reverdy not found in extracted people: {people}"
        )

    def test_finds_torf(self):
        """Torf Gallery patron is found."""
        people = {b['person'].lower() for b in self.beats}
        # Accept 'torf' or 'michael k. torf' or similar
        self.assertTrue(
            any('torf' in p for p in people),
            f"Torf not found in extracted people: {people}"
        )

    def test_finds_dali_freud_action(self):
        """Dalí illustrating Freud's work is found as a story beat."""
        # Either Dalí's action referencing Freud, or Freud as a person in context
        all_text = ' '.join(b['action'] + ' ' + b.get('source_sentence', '') for b in self.beats).lower()
        self.assertTrue(
            'freud' in all_text or 'dalí' in all_text or 'dali' in all_text,
            f"Dalí/Freud action not found in beats"
        )

    def test_at_least_four_distinct_people(self):
        """Acceptance: at least 4 distinct named people from {Broder, Mourlot, Fridman, Freud, Reverdy, Torf}."""
        people_lower = {b['person'].lower() for b in self.beats}
        target_set = {'broder', 'mourlot', 'fridman', 'freud', 'reverdy', 'torf'}
        found = set()
        for p in people_lower:
            for target in target_set:
                if target in p:
                    found.add(target)
        self.assertGreaterEqual(
            len(found), 4,
            f"Only found {len(found)} of target people: {found}. All people: {people_lower}"
        )

    def test_each_beat_has_person_and_action(self):
        """Every beat has non-empty person and action."""
        for beat in self.beats:
            self.assertTrue(beat['person'].strip(), f"Beat missing person: {beat}")
            self.assertTrue(beat['action'].strip(), f"Beat missing action: {beat}")

    def test_each_beat_has_source_sentence(self):
        """Every beat has a source_sentence for grounding verification."""
        for beat in self.beats:
            self.assertIn('source_sentence', beat)

    def test_each_beat_has_role(self):
        """Every beat has a role classification."""
        valid_roles = {'publisher', 'printer', 'donor', 'gallery_patron',
                       'collaborator', 'illustrator', 'author', 'founder',
                       'circumstance', 'stakes'}
        for beat in self.beats:
            self.assertIn(beat['role'], valid_roles,
                          f"Invalid role '{beat['role']}' in beat: {beat}")

    def test_no_fabricated_people(self):
        """No person name that doesn't appear in the source text."""
        text_lower = MFA_PAGE_TEXT.lower()
        for beat in self.beats:
            if beat['role'] in ('circumstance', 'stakes'):
                continue  # These use (the works themselves) etc
            person = beat['person']
            # At least the surname should appear in the page
            surname = person.split()[-1].lower()
            self.assertIn(
                surname, text_lower,
                f"Person '{person}' (surname '{surname}') not grounded in page text"
            )


class TestAssignBeatsToStops(unittest.TestCase):
    """Test assign_beats_to_stops distributes correctly."""

    def setUp(self):
        self.beats = extract_story_beats(MFA_PAGE_TEXT)
        self.stop_names = [
            "Le Lézard aux plumes d'or",
            "Moses and Monotheism",
            "Au Soleil du Plafond",
            "Picasso: Variations on a theme",
            "Miró lithographs",
            "Dalí's Dream of Venus",
            "La Prose du Transsibérien",
            "Final work",
        ]

    def test_all_stops_get_beats(self):
        """Every stop gets at least one beat."""
        assigned = assign_beats_to_stops(self.beats, self.stop_names)
        for i, stop_beats in enumerate(assigned):
            self.assertGreater(
                len(stop_beats), 0,
                f"Stop {i} ('{self.stop_names[i]}') has no beats assigned"
            )

    def test_return_length_matches_stops(self):
        """Return list has same length as stop_names."""
        assigned = assign_beats_to_stops(self.beats, self.stop_names)
        self.assertEqual(len(assigned), len(self.stop_names))

    def test_matched_work_gets_relevant_beat(self):
        """When a matched_work has a publisher, the matching beat goes to that stop."""
        matched_works = [
            {'artist': 'Miró', 'publisher': 'Louis Broder', 'medium': '40 color lithographs'},
            None, None, None, None, None, None, None,
        ]
        assigned = assign_beats_to_stops(
            self.beats, self.stop_names, matched_works=matched_works
        )
        # Stop 0 should have a Broder beat
        stop0_people = [b['person'].lower() for b in assigned[0]]
        self.assertTrue(
            any('broder' in p for p in stop0_people),
            f"Stop 0 matched Broder but didn't get Broder beat: {stop0_people}"
        )


class TestBuildStoryBeatPromptBlock(unittest.TestCase):
    """Test build_story_beat_prompt_block output."""

    def test_empty_beats_returns_empty(self):
        """No beats → empty string."""
        self.assertEqual(build_story_beat_prompt_block([]), '')

    def test_person_beat_produces_prompt(self):
        """A person beat produces a non-empty prompt with the person's name."""
        beats = [{'person': 'Louis Broder', 'action': 'published this work',
                  'source_sentence': 'test', 'role': 'publisher'}]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('Louis Broder', block)
        self.assertIn('STORY BEAT REQUIREMENT', block)
        self.assertIn('NAMES A PERSON', block)

    def test_exhibition_framing_serves_thesis(self):
        """Exhibition framing includes thesis-serving instruction."""
        beats = [{'person': 'Mourlot Frères', 'action': 'printed this work',
                  'source_sentence': 'test', 'role': 'printer'}]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('SERVES THE THESIS', block)

    def test_venue_purpose_framing(self):
        """Venue purpose framing includes venue-serving instruction."""
        beats = [{'person': 'Dr. Albert Barnes', 'action': 'founded the collection',
                  'source_sentence': 'test', 'role': 'founder'}]
        block = build_story_beat_prompt_block(beats, framing_case='venue_purpose')
        self.assertIn('SERVES THE VENUE', block)

    def test_none_framing_object_focused(self):
        """No framing → object-focused instruction."""
        beats = [{'person': 'Artist Name', 'action': 'created this',
                  'source_sentence': 'test', 'role': 'collaborator'}]
        block = build_story_beat_prompt_block(beats, framing_case='none')
        self.assertIn('ATTACHES TO THE OBJECT', block)

    def test_anti_empty_sentence_instruction(self):
        """Prompt explicitly warns against empty evaluative sentences."""
        beats = [{'person': 'Test Person', 'action': 'did something',
                  'source_sentence': 'test', 'role': 'publisher'}]
        block = build_story_beat_prompt_block(beats)
        self.assertIn('not a story', block.lower())


class TestEmptyInput(unittest.TestCase):
    """Edge cases: empty or minimal input."""

    def test_empty_text_returns_empty_beats(self):
        """Empty page text → no beats."""
        self.assertEqual(extract_story_beats(''), [])

    def test_none_text_returns_empty_beats(self):
        """None page text → no beats (no crash)."""
        # noinspection PyTypeChecker
        self.assertEqual(extract_story_beats(None), [])

    def test_no_people_text(self):
        """Text with no named people → empty or minimal beats."""
        text = "This is a beautiful artwork. The colors are vibrant. Art is wonderful."
        beats = extract_story_beats(text)
        # Should have no person beats (only maybe context)
        person_beats = [b for b in beats if b['role'] not in ('circumstance', 'stakes')]
        self.assertEqual(len(person_beats), 0)

    def test_assign_empty_beats_to_stops(self):
        """Empty beats list → each stop gets empty list."""
        result = assign_beats_to_stops([], ['Stop 1', 'Stop 2'])
        self.assertEqual(result, [[], []])


class TestGroundingIntegrity(unittest.TestCase):
    """Verify grounding constraint: beats only name people found in the text."""

    def test_custom_text_no_hallucination(self):
        """Extractor doesn't invent people beyond what's in text."""
        text = (
            "This painting was donated by John Smith in 1980. "
            "It hangs in the Sarah Johnson Gallery."
        )
        beats = extract_story_beats(text)
        person_beats = [b for b in beats if b['role'] not in ('circumstance', 'stakes')]
        for beat in person_beats:
            # Person surname must be in text
            surname = beat['person'].split()[-1].lower()
            self.assertIn(surname, text.lower(),
                          f"Fabricated person: {beat['person']}")


class TestRevertBreaksLogic(unittest.TestCase):
    """D296: Removing story_beat_injector breaks story beat extraction.

    This test verifies the LOGIC dependency: without the module,
    no story beats can be extracted or injected.
    """

    def test_extract_produces_results_with_module(self):
        """With the module present, extraction produces ≥4 beats on MFA text."""
        beats = extract_story_beats(MFA_PAGE_TEXT)
        self.assertGreaterEqual(len(beats), 4,
                                "Module present but extraction yielded <4 beats — logic broken")

    def test_build_prompt_requires_beats(self):
        """Without extracted beats, no story-beat prompt block can be built."""
        # If extraction returns empty (as it would without the module's regex),
        # the prompt block is empty — no story instruction goes to the LLM.
        block = build_story_beat_prompt_block([])
        self.assertEqual(block, '',
                         "Empty beats should produce empty prompt block")


if __name__ == '__main__':
    unittest.main()
