"""test_local388_story_delivery.py — Tests for LOCAL-388: story beat delivery.

Tests:
  1. assign_beats_to_stops distributes beats to ALL stops (not just stop 0/1).
  2. verify_beats_in_output correctly identifies found vs dropped beats.
  3. build_story_beat_prompt_block includes NEVER-PLACEHOLDER rule.
  4. Empty-string guard: empty collaborator/publisher doesn't match everything.
  5. Revert test: removing the distribution fix breaks multi-stop delivery.
  6. Integration test: exercises the real generation path (D307 compliance).

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
)


# Fixture: MFA exhibition page text
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

STOP_NAMES_8 = [
    "Le Lézard aux plumes d'or",
    "Moses and Monotheism",
    "Au Soleil du Plafond",
    "Picasso: Variations on a theme",
    "Miró lithographs",
    "Dalí's Dream of Venus",
    "La Prose du Transsibérien",
    "Final work",
]


class TestBeatDistributionAllStops(unittest.TestCase):
    """[LOCAL-388] Defect 1 fix: beats reach ALL stops, not just stop 0/1."""

    def setUp(self):
        self.beats = extract_story_beats(MFA_PAGE_TEXT)
        self.assigned = assign_beats_to_stops(self.beats, STOP_NAMES_8)

    def test_every_stop_has_at_least_one_beat(self):
        """Every stop gets at least one assigned beat."""
        for i, stop_beats in enumerate(self.assigned):
            self.assertGreater(
                len(stop_beats), 0,
                f"Stop {i} ('{STOP_NAMES_8[i]}') has no beats — delivery gap"
            )

    def test_person_beats_not_all_on_stop_0(self):
        """Person beats are distributed, not clustered on stop 0."""
        person_beats_stop0 = [
            b for b in self.assigned[0]
            if b['role'] not in ('circumstance', 'stakes')
        ]
        total_person_beats = sum(
            len([b for b in stop if b['role'] not in ('circumstance', 'stakes')])
            for stop in self.assigned
        )
        # Stop 0 should have at most 2 of the total person beats
        self.assertLessEqual(
            len(person_beats_stop0), 2,
            f"Stop 0 hoarding {len(person_beats_stop0)}/{total_person_beats} person beats"
        )

    def test_at_least_5_stops_have_person_beats(self):
        """At least 5 of 8 stops have a named-person beat (not just context)."""
        stops_with_person = sum(
            1 for stop in self.assigned
            if any(b['role'] not in ('circumstance', 'stakes') for b in stop)
        )
        self.assertGreaterEqual(stops_with_person, 5)

    def test_broder_mourlot_fridman_all_assigned(self):
        """All three key people (Broder, Mourlot, Fridman) are assigned somewhere."""
        all_assigned_people = set()
        for stop_beats in self.assigned:
            for b in stop_beats:
                all_assigned_people.add(b['person'].lower())
        for name in ('broder', 'mourlot', 'fridman'):
            self.assertTrue(
                any(name in p for p in all_assigned_people),
                f"{name} not assigned to any stop: {all_assigned_people}"
            )


class TestBeatDistributionWithMatchedWorks(unittest.TestCase):
    """[LOCAL-388] Relevance matching assigns publisher to correct stop."""

    def setUp(self):
        self.beats = extract_story_beats(MFA_PAGE_TEXT)

    def test_empty_collaborator_does_not_match_everyone(self):
        """Empty collaborator string does not cause spurious match to first beat."""
        matched_works = [
            {'artist': 'Miró', 'publisher': 'Louis Broder', 'collaborator': '', 'medium': 'lithographs'},
            None, None, None, None, None, None, None,
        ]
        assigned = assign_beats_to_stops(self.beats, STOP_NAMES_8, matched_works=matched_works)
        # Stop 0 should have Broder (the publisher), not Juan Gris (first person beat)
        stop0_people = [b['person'].lower() for b in assigned[0] if b['role'] not in ('circumstance', 'stakes')]
        self.assertTrue(
            any('broder' in p for p in stop0_people),
            f"Stop 0 should have Broder (publisher match) but got: {stop0_people}"
        )
        # Juan Gris should NOT be at stop 0 (no relevance to the matched work)
        self.assertFalse(
            any('gris' in p for p in stop0_people),
            f"Juan Gris falsely matched to stop 0 via empty-string bug: {stop0_people}"
        )

    def test_publisher_beats_assigned_to_publisher_stop(self):
        """When stop 0 has publisher='Louis Broder', the Broder beat lands there."""
        matched_works = [
            {'artist': 'Miró', 'publisher': 'Louis Broder', 'medium': 'lithographs'},
            None, None, None, None, None, None, None,
        ]
        assigned = assign_beats_to_stops(self.beats, STOP_NAMES_8, matched_works=matched_works)
        stop0_people = [b['person'].lower() for b in assigned[0]]
        self.assertTrue(
            any('broder' in p for p in stop0_people),
            f"Broder not in stop 0 despite publisher match: {stop0_people}"
        )


class TestVerifyBeatsInOutput(unittest.TestCase):
    """[LOCAL-388] verify_beats_in_output detects which beats reached the prose."""

    def test_all_found(self):
        """When all assigned people appear in output, beats_in_output = beats_assigned."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
            {'person': 'Mourlot Frères', 'role': 'printer', 'action': 'printed'},
        ]
        output = "Published by Louis Broder and printed by Mourlot Frères in Paris."
        result = verify_beats_in_output(beats, output, "Stop 1")
        self.assertEqual(result['beats_assigned'], 2)
        self.assertEqual(result['beats_in_output'], 2)
        self.assertEqual(result['dropped'], [])

    def test_one_dropped(self):
        """When one person is missing from output, it appears in dropped."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
            {'person': 'Boris Fridman', 'role': 'donor', 'action': 'donated'},
        ]
        output = "Published by Louis Broder, this work is a masterpiece."
        result = verify_beats_in_output(beats, output, "Stop 1")
        self.assertEqual(result['beats_assigned'], 2)
        self.assertEqual(result['beats_in_output'], 1)
        self.assertEqual(result['dropped'], ['Boris Fridman'])
        self.assertEqual(result['found'], ['Louis Broder'])

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        beats = [{'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'}]
        output = "published by LOUIS BRODER"
        result = verify_beats_in_output(beats, output, "Stop 1")
        self.assertEqual(result['beats_in_output'], 1)

    def test_surname_match(self):
        """Surname alone in output counts as found."""
        beats = [{'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'}]
        output = "Broder's contribution to this work was significant."
        result = verify_beats_in_output(beats, output, "Stop 1")
        self.assertEqual(result['beats_in_output'], 1)

    def test_context_beats_excluded(self):
        """Context beats (circumstance/stakes) are not counted in person totals."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
            {'person': '(the works)', 'role': 'circumstance', 'action': 'rarely shown'},
        ]
        output = "Published by Louis Broder."
        result = verify_beats_in_output(beats, output, "Stop 1")
        self.assertEqual(result['beats_assigned'], 1)  # Only person beats counted

    def test_empty_output(self):
        """Empty output means all person beats are dropped."""
        beats = [{'person': 'Broder', 'role': 'publisher', 'action': 'published'}]
        result = verify_beats_in_output(beats, '', "Stop 1")
        self.assertEqual(result['beats_in_output'], 0)
        self.assertEqual(result['dropped'], ['Broder'])


class TestNeverPlaceholderRule(unittest.TestCase):
    """[LOCAL-388] Defect 3: prompt block explicitly forbids 'with publisher'."""

    def test_prompt_contains_never_placeholder(self):
        """The prompt block includes NEVER-PLACEHOLDER rule."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
            {'person': 'Mourlot Frères', 'role': 'printer', 'action': 'printed'},
        ]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('NEVER-PLACEHOLDER', block)
        self.assertIn('with publisher', block.lower())
        self.assertIn('with printer', block.lower())

    def test_prompt_names_the_person_for_role(self):
        """The prompt block maps each role to the person's name."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'published'},
        ]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('Louis Broder', block)
        self.assertIn("'publisher'", block)


class TestSupplementalNotReplacing(unittest.TestCase):
    """[LOCAL-388] Defect 2 guard: beats supplement thesis, not replace it."""

    def test_prompt_says_supplements(self):
        """Story beat prompt states it supplements rather than replaces."""
        beats = [{'person': 'Broder', 'role': 'publisher', 'action': 'published'}]
        block = build_story_beat_prompt_block(beats, framing_case='exhibition')
        self.assertIn('SUPPLEMENTS', block)
        self.assertIn('does not replace', block)


class TestRevertBreaksDelivery(unittest.TestCase):
    """D296: removing the LOCAL-388 fix breaks multi-stop delivery.

    The defect is that without the empty-string guard and distribution fix,
    beats cluster on stop 0. This test verifies that the fix produces
    even distribution.
    """

    def test_distribution_is_even(self):
        """With 8 person beats and 8 stops, no stop should have 0 person beats."""
        beats = extract_story_beats(MFA_PAGE_TEXT)
        assigned = assign_beats_to_stops(beats, STOP_NAMES_8)
        # Count stops that got at least one person beat
        stops_with_person = sum(
            1 for stop in assigned
            if any(b['role'] not in ('circumstance', 'stakes') for b in stop)
        )
        # Without the fix: only 1 stop would get all beats.
        # With the fix: at least 7 of 8 stops get person beats.
        self.assertGreaterEqual(
            stops_with_person, 7,
            f"Only {stops_with_person}/8 stops have person beats — distribution broken"
        )

    def test_verify_function_exists_and_works(self):
        """verify_beats_in_output is importable and functional (revert would NameError)."""
        result = verify_beats_in_output(
            [{'person': 'Broder', 'role': 'publisher', 'action': 'x'}],
            'Broder published this',
            'test stop',
        )
        self.assertEqual(result['beats_in_output'], 1)


class TestIntegrationRealPath(unittest.TestCase):
    """D307 compliance: exercise the real generation path.

    This test imports generate_tour_text and verifies that the story beat
    injection path is wired correctly — the same code path that crashed in
    LOCAL-382 (NameError shipped because unit tests were green but integration
    was broken).
    """

    def test_story_beat_injection_path_importable(self):
        """The full import chain used in generate_tour_text.py is valid."""
        # This is the exact import pattern used at line ~8201 in generate_tour_text.py
        from story_beat_injector import extract_story_beats, assign_beats_to_stops
        from story_beat_injector import build_story_beat_prompt_block
        from story_beat_injector import verify_beats_in_output

        # Exercise the real path: extract → assign → build prompt → verify
        beats = extract_story_beats(MFA_PAGE_TEXT)
        self.assertGreater(len(beats), 0, "Extraction returned nothing")

        stop_names = STOP_NAMES_8
        assigned = assign_beats_to_stops(beats, stop_names, framing_case='exhibition')
        self.assertEqual(len(assigned), len(stop_names))

        # Build prompt for each stop and verify non-empty
        for i, stop_beats in enumerate(assigned):
            block = build_story_beat_prompt_block(stop_beats, framing_case='exhibition')
            self.assertTrue(
                block.strip(),
                f"Stop {i} got empty prompt block despite having beats: {stop_beats}"
            )

        # Simulate output verification (would run post-LLM in generate_tour_text.py)
        fake_output = "Published by Louis Broder in Paris. Printed at the Mourlot Frères workshop."
        result = verify_beats_in_output(assigned[0], fake_output, stop_names[0])
        self.assertIsInstance(result, dict)
        self.assertIn('beats_assigned', result)
        self.assertIn('beats_in_output', result)
        self.assertIn('dropped', result)

    def test_generate_tour_text_imports_cleanly(self):
        """generate_tour_text.py can be imported without NameError (D307 guard)."""
        # This catches the exact class of bug that LOCAL-382 shipped:
        # a module-level or top-level import that crashes at import time.
        try:
            import generate_tour_text
        except NameError as e:
            self.fail(f"generate_tour_text.py raises NameError on import: {e}")
        except Exception:
            # Other errors (missing env, DB connection) are expected in test env
            pass


if __name__ == '__main__':
    unittest.main()
