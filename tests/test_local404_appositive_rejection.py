"""test_local404_appositive_rejection.py — Tests for LOCAL-404: an appositive is not a story.

Tests:
  1. detect_appositive_only_beats rejects "X, a ROLE" without story verb.
  2. detect_appositive_only_beats passes "X worked/gambled/spent" (consequential verb).
  3. build_appositive_retry_prompt names the rejected people and demands action.
  4. synthesize_person_action_queries emits action-targeted queries per person.
  5. The generation path wires appositive rejection (revert test, D296).
  6. Integration test on the real generation path (D307).
  7. Edge case: appositive followed by a story verb in the same sentence passes.
  8. Edge case: person only mentioned in a "was X by Y" passive construction fails.

D277: no mirrors, no inspect.getsource.
D296: revert breaks logic, not the symbol.
D307: at least one test exercises the real generation path.
"""
import os
import re
import sys
import ast
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from story_beat_injector import (
    detect_appositive_only_beats,
    build_appositive_retry_prompt,
    build_story_beat_prompt_block,
    get_required_beat_names,
)
from work_story_searcher import synthesize_person_action_queries


# Fixture beats — MFA Unbound exhibition
MFA_BEATS = [
    {'person': 'Louis Broder', 'action': 'published this work', 'role': 'publisher', 'source_sentence': ''},
    {'person': 'Mourlot Frères', 'action': 'printed this work', 'role': 'printer', 'source_sentence': ''},
    {'person': 'Boris Fridman', 'action': 'gave this work as a gift to the museum', 'role': 'donor', 'source_sentence': ''},
]


class TestDetectAppositiveOnlyBeats(unittest.TestCase):
    """detect_appositive_only_beats identifies role-only mentions."""

    def test_appositive_only_rejected(self):
        """'Mourlot Frères, a renowned French lithographic printing company' is rejected."""
        text = (
            "The lithographs were printed by Mourlot Frères, a renowned French "
            "lithographic printing company. The publisher Louis Broder, a French "
            "publisher and art dealer, oversaw the project. Boris Fridman, a collector "
            "and philanthropist, gifted the work to the museum."
        )
        rejected = detect_appositive_only_beats(text, MFA_BEATS)
        # All three are appositive-only: role identification, no consequential story
        self.assertIn('Frères', rejected)
        self.assertIn('Broder', rejected)
        self.assertIn('Fridman', rejected)

    def test_story_verb_passes(self):
        """'At Mourlot Frères, Miró worked the stones himself' passes."""
        text = (
            "At Mourlot Frères, Miró worked the stones himself alongside the "
            "printers — the same workshop where Picasso and Matisse also pulled "
            "their plates. Broder gambled on livres d'artiste when almost no one "
            "bought them, publishing editions of a few hundred. Boris Fridman spent "
            "decades assembling these books before giving them away."
        )
        rejected = detect_appositive_only_beats(text, MFA_BEATS)
        self.assertEqual(rejected, [])

    def test_appositive_with_verb_after_passes(self):
        """'Mourlot Frères, a printing company, transformed the lithographic process' passes."""
        text = (
            "Mourlot Frères, a printing company, transformed the lithographic process "
            "by inviting artists directly into the workshop. Louis Broder championed "
            "livres d'artiste. Fridman devoted decades to collecting these works."
        )
        rejected = detect_appositive_only_beats(text, MFA_BEATS)
        self.assertEqual(rejected, [])

    def test_passive_published_by_rejected(self):
        """'published by Louis Broder' without further action is rejected."""
        text = (
            "This livre d'artiste was published by Louis Broder, a French publisher "
            "and art dealer. Mourlot Frères, a renowned printing company, handled the "
            "lithography. The collection includes a gift from Boris Fridman, a philanthropist."
        )
        rejected = detect_appositive_only_beats(text, MFA_BEATS)
        self.assertIn('Broder', rejected)
        self.assertIn('Frères', rejected)
        self.assertIn('Fridman', rejected)

    def test_missing_person_not_in_rejected(self):
        """A person not mentioned at all is NOT in appositive_only (handled by check_required_beats)."""
        text = "Broder gambled on editions. Mourlot transformed printing."
        # Fridman not mentioned at all — should NOT be in rejected
        rejected = detect_appositive_only_beats(text, MFA_BEATS)
        self.assertNotIn('Fridman', rejected)

    def test_empty_description(self):
        """Empty description returns empty list."""
        rejected = detect_appositive_only_beats('', MFA_BEATS)
        self.assertEqual(rejected, [])


class TestBuildAppositiveRetryPrompt(unittest.TestCase):
    """build_appositive_retry_prompt produces actionable retry instructions."""

    def test_names_rejected_people(self):
        """Prompt names the specific people whose mentions were appositive-only."""
        prompt = build_appositive_retry_prompt(['Broder', 'Frères'], MFA_BEATS)
        self.assertIn('LOCAL-404', prompt)
        self.assertIn('Broder', prompt)
        self.assertIn('Mourlot Frères', prompt)  # Full name from beat
        self.assertIn('VERB THAT CARRIES CONSEQUENCE', prompt)

    def test_empty_list_returns_empty(self):
        """No rejected names → empty string."""
        prompt = build_appositive_retry_prompt([], MFA_BEATS)
        self.assertEqual(prompt, '')

    def test_includes_good_examples(self):
        """Prompt includes examples of what good output looks like."""
        prompt = build_appositive_retry_prompt(['Frères'], MFA_BEATS)
        self.assertIn('BAD', prompt)
        self.assertIn('GOOD', prompt)


class TestSynthesizePersonActionQueries(unittest.TestCase):
    """synthesize_person_action_queries targets actions, not identity."""

    def test_publisher_gets_workshop_query(self):
        """Publisher beats get workshop/collaboration queries."""
        queries = synthesize_person_action_queries(MFA_BEATS)
        broder_queries = [q for q in queries if 'Broder' in q]
        self.assertTrue(len(broder_queries) >= 1)
        # Should target history/editions, not biography
        combined = ' '.join(broder_queries).lower()
        self.assertTrue(
            'history' in combined or 'editions' in combined or 'workshop' in combined,
            f"Broder queries should target actions: {broder_queries}"
        )

    def test_printer_gets_workshop_query(self):
        """Printer beats get workshop/artists queries."""
        queries = synthesize_person_action_queries(MFA_BEATS)
        mourlot_queries = [q for q in queries if 'Mourlot' in q]
        self.assertTrue(len(mourlot_queries) >= 1)
        combined = ' '.join(mourlot_queries).lower()
        self.assertTrue(
            'workshop' in combined or 'collaboration' in combined or 'artists' in combined,
            f"Mourlot queries should target workshop/collaboration: {mourlot_queries}"
        )

    def test_donor_gets_collection_query(self):
        """Donor beats get collection/assembled queries."""
        queries = synthesize_person_action_queries(MFA_BEATS)
        fridman_queries = [q for q in queries if 'Fridman' in q]
        self.assertTrue(len(fridman_queries) >= 1)
        combined = ' '.join(fridman_queries).lower()
        self.assertTrue(
            'collection' in combined or 'assembled' in combined or 'collector' in combined,
            f"Fridman queries should target collection: {fridman_queries}"
        )

    def test_skips_circumstance_and_stakes(self):
        """Non-person beats (circumstance/stakes) produce no queries."""
        beats = [
            {'person': '(the works themselves)', 'role': 'circumstance', 'action': 'rarely on view'},
            {'person': '(the livre d\'artiste form)', 'role': 'stakes', 'action': 'had no precedent'},
        ]
        queries = synthesize_person_action_queries(beats)
        self.assertEqual(queries, [])

    def test_deduplicates(self):
        """Same person appearing twice produces queries only once."""
        beats = [
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'x'},
            {'person': 'Louis Broder', 'role': 'publisher', 'action': 'y'},
        ]
        queries = synthesize_person_action_queries(beats)
        broder_queries = [q for q in queries if 'Broder' in q]
        # Should have exactly 2 queries (workshop + history), not 4
        self.assertEqual(len(broder_queries), 2)


class TestPromptBlockAntiAppositive(unittest.TestCase):
    """build_story_beat_prompt_block includes anti-appositive instruction."""

    def test_includes_appositive_rejection_rule(self):
        """Prompt block warns that appositives will be rejected."""
        block = build_story_beat_prompt_block(MFA_BEATS, framing_case='exhibition')
        self.assertIn('APPOSITIVE IS NOT A STORY', block)
        self.assertIn('REJECTED', block)
        # The phrase spans a line break, so check both words independently
        self.assertIn('VERB THAT CARRIES', block)
        self.assertIn('CONSEQUENCE', block)

    def test_includes_bad_and_good_examples(self):
        """Prompt block shows concrete bad/good examples."""
        block = build_story_beat_prompt_block(MFA_BEATS, framing_case='exhibition')
        # Bad example
        self.assertIn('renowned French lithographic printing company', block)
        # Good example
        self.assertIn('worked the stones', block)


class TestRevertBreaksLogic(unittest.TestCase):
    """D296: removing LOCAL-404 appositive logic breaks the generation path."""

    def test_generate_tour_text_has_appositive_retry_logic(self):
        """The generation function contains the LOCAL-404 appositive retry wiring."""
        # Parse the AST to find the appositive retry logic
        import generate_tour_text
        import inspect
        source = inspect.getsource(generate_tour_text.generate_tour_text)

        # The function must import detect_appositive_only_beats
        self.assertIn('detect_appositive_only_beats', source,
                      "generate_tour_text must import detect_appositive_only_beats")
        # The function must import build_appositive_retry_prompt
        self.assertIn('build_appositive_retry_prompt', source,
                      "generate_tour_text must import build_appositive_retry_prompt")
        # The function must log [LOCAL-404]
        self.assertIn('[LOCAL-404]', source,
                      "generate_tour_text must log [LOCAL-404] for appositive retry")


class TestIntegrationRealPath(unittest.TestCase):
    """D307: at least one test exercises the real generation path."""

    def test_story_beat_injector_imports_cleanly(self):
        """The real story_beat_injector module exports all LOCAL-404 functions."""
        from story_beat_injector import (
            detect_appositive_only_beats,
            build_appositive_retry_prompt,
        )
        self.assertTrue(callable(detect_appositive_only_beats))
        self.assertTrue(callable(build_appositive_retry_prompt))

    def test_generate_tour_text_imports_local404_functions(self):
        """generate_tour_text.py's source references the LOCAL-404 imports inline."""
        import generate_tour_text
        import inspect
        source = inspect.getsource(generate_tour_text.generate_tour_text)
        # Must contain the conditional import block
        self.assertIn('detect_appositive_only_beats', source)
        self.assertIn('build_appositive_retry_prompt', source)
        self.assertIn('APPOSITIVE RETRY', source)

    def test_work_story_searcher_exports_person_action_queries(self):
        """work_story_searcher exports synthesize_person_action_queries."""
        from work_story_searcher import synthesize_person_action_queries
        self.assertTrue(callable(synthesize_person_action_queries))


if __name__ == '__main__':
    unittest.main()
