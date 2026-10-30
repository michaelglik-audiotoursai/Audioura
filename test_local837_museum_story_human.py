#!/usr/bin/env python3
"""test_local837_museum_story_human.py — [LOCAL-837] the museum story pass must
write a HUMAN story, not provenance and not the artwork-as-subject.

**THE DEFECT (LOCAL-832B submission, "What does NOT pass").** On the cheap arm
(gpt-4.1-mini) Orsay and Rijks were 5/5 well-formed but 0/5 stops cleared the
D511 story bar (3+ consecutive sentences, one subject, an action, a stake):

  1. the story pass mostly wrote PROVENANCE — "the museum acquired it", "X gifted
     it" — which carries no stake, so the scan reported stakes=0;
  2. when it wrote an eventful story the subject was the ARTWORK ITSELF ("The
     Night Watch was evacuated… hidden in a bunker"), which
     `story_opportunity_scan.can_carry` refuses by design (kind=='title');
  3. the narration merge then split agency and stakes into different sentences.

**THE FIX under test.** `story_pass.build_story_prompt(..., works_mode=True)` —
the museum-works path — tells the writer the subject is a PERSON connected to the
work (painter, sitter, patron, thief, restorer, curator), says the work CANNOT be
the subject, declares PROVENANCE IS NOT A STORY, and keys NO_STORY on "no human
event" so a gift/bequest/acquisition returns NO_STORY instead of being dressed up
as a story. The DEFAULT path (works_mode=False, LOCAL-493 Pompeii) is unchanged:
there the subject may be a place or an event, because there the stop is a site the
scanner reads as a proper noun/event that `can_carry` accepts.

These tests assert on the PRODUCTION ARTIFACTS: the prompt text that ships, the
`generate_story_for_stop` contract (via an injected caller — no network, no key),
and the SAME `story_opportunity_scan` the gate uses — so the design is anchored to
`can_carry` without touching or gaming it. The 832B provenance/story fixtures are
reused verbatim.

Run: python3 -m pytest test_local837_museum_story_human.py -q
 or: python3 -m unittest test_local837_museum_story_human -v
"""
import unittest

from story_pass import (
    build_story_prompt,
    generate_story_for_stop,
    NO_STORY,
)
from story_opportunity_scan import measure, verdict


# ── A museum-work matrix + research with BOTH a human event and provenance ──────
WORK_MATRIX = {
    'canonical_title': 'The Night Watch',
    'artist': 'Rembrandt van Rijn',
    'venue_name': 'Rijksmuseum',
    'medium': 'oil on canvas',
}

# Research that CONTAINS a human event (van Schendel hid it) AND provenance noise
# (acquired in 1808). The works-mode prompt must steer to the former.
WORK_MATERIAL_HUMAN = [
    'In 1939 the curator Arie van Schendel had The Night Watch rolled onto a '
    'cylinder and moved to a bunker in Maastricht, fearing German bombing.',
    'He kept the painting hidden underground until 1945, when it returned to '
    'Amsterdam.',
    'The Rijksmuseum acquired the painting in 1808 from the city of Amsterdam.',
]

# Research with ONLY provenance / description — no human did anything at a cost.
WORK_MATERIAL_PROVENANCE_ONLY = [
    'Washington Crossing the Delaware was gifted to the Metropolitan Museum of '
    'Art in 1897 by John Stewart Kennedy.',
    'The painting measures twelve feet by twenty-one feet and hangs in the '
    'American Wing.',
    'It entered the collection as part of a bequest of nineteenth-century works.',
]

# ── 832B fixtures, verbatim — the provenance-vs-story cases this task inherits ──
# A delivered Night Watch body whose longest consecutive run about one subject is
# 3 sentences carrying agency=0 stakes=0 — storyless by the bar.
FLAT_NIGHT_WATCH = (
    "Rembrandt completed this colossal group portrait in 1642 for the "
    "Kloveniersdoelen, the guild hall of Amsterdam's civic guards. The painting, "
    "known as The Night Watch, is a large oil on canvas measuring approximately "
    "fourteen and a half feet wide by twelve feet tall, commanding attention in "
    "this gallery. It portrays Captain Frans Banning Cocq and his company of "
    "merchants and shopkeepers whose duties had shifted from municipal defense to "
    "ceremonial social gatherings. Instead of arranging the figures in static "
    "poses, Rembrandt set them in dynamic motion, scattering the members as they "
    "interact under shifting light and shadow. He used chiaroscuro to guide the "
    "viewer's eye toward the central captain and his lieutenant. This technique "
    "animates the scene and creates a sense of depth and drama."
)

# A HUMAN-subject story (curator hid it): one person, an action, a consequence.
HUMAN_STORY = (
    "In 1939 the curator Arie van Schendel had The Night Watch rolled onto a "
    "cylinder and moved to a bunker in Maastricht. He feared German bombing would "
    "destroy the painting, so he hid it underground for the duration of the war. "
    "He kept it concealed until 1945, when it was finally returned to Amsterdam."
)

# The ARTWORK as subject — can_carry refuses kind=='title'.
ARTWORK_STORY = (
    "The Night Watch was evacuated in 1939 when war threatened. It was rolled up "
    "and hidden in a bunker in Maastricht. It survived the war and returned to "
    "Amsterdam in 1945."
)

# Provenance — a gift carries no stake.
PROVENANCE_STORY = (
    "Washington Crossing the Delaware was gifted to the Metropolitan Museum of Art "
    "in 1897 by John Stewart Kennedy. Before this gift, the painting was part of a "
    "private collection. The museum has displayed it ever since."
)


class TestScannerAnchorsTheDesign(unittest.TestCase):
    """The bar (the SAME judge the gate uses) is what makes the human requirement
    necessary — not an opinion in the prompt. `can_carry` is read, never changed."""

    def _run(self, text):
        return verdict(measure(text))

    def test_human_subject_story_clears_the_bar(self):
        v = self._run(HUMAN_STORY)
        self.assertFalse(v['needs_additional_story'],
                         f"human story should clear the bar: {v['why']}")

    def test_artwork_as_subject_does_not_clear(self):
        """`can_carry` refuses kind=='title' — so the artwork can never carry it.
        This is WHY works_mode forbids the artwork as subject."""
        v = self._run(ARTWORK_STORY)
        self.assertTrue(v['needs_additional_story'],
                        "artwork-as-subject must NOT clear the bar (can_carry)")

    def test_provenance_does_not_clear(self):
        v = self._run(PROVENANCE_STORY)
        self.assertTrue(v['needs_additional_story'],
                        "a gift carries no stake — provenance must NOT clear")


class TestWorksModePromptDemandsAHuman(unittest.TestCase):
    def setUp(self):
        self.prompt = build_story_prompt(WORK_MATRIX, WORK_MATERIAL_HUMAN,
                                         works_mode=True)

    def test_demands_one_named_person(self):
        self.assertIn('ONE NAMED PERSON', self.prompt)

    def test_the_work_cannot_be_the_subject(self):
        flat = ' '.join(self.prompt.split())
        self.assertIn('work itself CANNOT be the subject', flat)

    def test_offers_the_human_roles(self):
        """painter / sitter / patron / thief / restorer / curator — the people
        the ticket names as the real subjects."""
        low = self.prompt.lower()
        for role in ('painter', 'sitter', 'patron', 'thief', 'restorer',
                     'hid it'):
            self.assertIn(role, low, f'role {role!r} not offered as a subject')

    def test_declares_provenance_is_not_a_story(self):
        self.assertIn('PROVENANCE IS NOT A STORY', self.prompt)

    def test_no_story_keyed_on_no_human_event_not_on_no_person_generally(self):
        """In works mode NO_STORY fires when there is no HUMAN EVENT — and a
        gift/bequest/acquisition is explicitly NOT a human event."""
        flat = ' '.join(self.prompt.split())
        self.assertIn('no\n    HUMAN EVENT'.replace('\n    ', ' '),
                      flat.replace('  ', ' '))
        self.assertIn('Provenance and transfers of ownership are NOT human events',
                      flat)
        self.assertIn(NO_STORY, self.prompt)

    def test_the_night_watch_worked_example_present(self):
        """Michael's own shape: van Schendel moved it to a bunker BECAUSE…"""
        flat = ' '.join(self.prompt.split())
        self.assertIn('van Schendel', flat)
        self.assertIn('bunker', flat)

    def test_matrix_and_material_still_rendered(self):
        self.assertIn('The Night Watch', self.prompt)
        self.assertIn('Arie van Schendel had The Night Watch rolled', self.prompt)

    def test_never_invents_survives(self):
        self.assertIn('must appear in the source material', self.prompt)
        self.assertIn('An invented story is the one unacceptable outcome',
                      self.prompt)


class TestDefaultPathUnchanged(unittest.TestCase):
    """works_mode=False must be the LOCAL-493 prompt — a place/event CAN carry a
    story there, and the human-only language must be ABSENT."""

    def setUp(self):
        self.prompt = build_story_prompt(WORK_MATRIX, WORK_MATERIAL_HUMAN,
                                         works_mode=False)

    def test_default_keeps_one_named_subject_not_one_named_person(self):
        self.assertIn('ONE NAMED SUBJECT', self.prompt)
        self.assertNotIn('ONE NAMED PERSON', self.prompt)

    def test_default_still_offers_non_human_subjects(self):
        low = self.prompt.lower()
        for subject in ('a place', 'an institution', 'the object'):
            self.assertIn(subject, low)

    def test_default_has_no_works_mode_blocks(self):
        self.assertNotIn('PROVENANCE IS NOT A STORY', self.prompt)
        self.assertNotIn('work itself CANNOT be the subject',
                         ' '.join(self.prompt.split()))

    def test_default_no_story_is_the_narrow_nothing_happened_test(self):
        self.assertIn('NOTHING THAT HAPPENED', self.prompt)
        self.assertIn('deliberately NOT a test for people', self.prompt)

    def test_default_is_byte_for_byte_the_no_arg_prompt(self):
        """The production default used to call build_story_prompt with no
        works_mode; that must be identical to works_mode=False."""
        self.assertEqual(
            build_story_prompt(WORK_MATRIX, WORK_MATERIAL_HUMAN),
            build_story_prompt(WORK_MATRIX, WORK_MATERIAL_HUMAN, works_mode=False))


class TestGenerateStoryForStopForwardsWorksMode(unittest.TestCase):
    """The pass runs with an injected caller — no network, no key. We assert the
    works_mode prompt reached the model, and that the pass accepts a human story
    and the scan clears it."""

    def test_works_mode_prompt_reaches_the_caller(self):
        seen = {}

        def _caller(prompt, model=None):
            seen['prompt'] = prompt
            return HUMAN_STORY, 0.0012

        res = generate_story_for_stop(WORK_MATRIX, WORK_MATERIAL_HUMAN,
                                      caller=_caller, works_mode=True)
        self.assertIn('ONE NAMED PERSON', seen['prompt'])
        self.assertIn('PROVENANCE IS NOT A STORY', seen['prompt'])
        self.assertTrue(res['ok'], res['reason'])
        self.assertEqual(res['story'], HUMAN_STORY)
        # The story the pass accepted clears the bar the gate enforces.
        self.assertFalse(verdict(measure(res['story']))['needs_additional_story'])

    def test_default_mode_does_not_get_the_human_block(self):
        seen = {}

        def _caller(prompt, model=None):
            seen['prompt'] = prompt
            return HUMAN_STORY, 0.0

        generate_story_for_stop(WORK_MATRIX, WORK_MATERIAL_HUMAN,
                                caller=_caller, works_mode=False)
        self.assertNotIn('ONE NAMED PERSON', seen['prompt'])
        self.assertNotIn('PROVENANCE IS NOT A STORY', seen['prompt'])

    def test_model_returning_no_story_is_a_recoverable_outcome(self):
        """When the model answers NO_STORY (provenance-only research), the pass
        reports not-ok and empty story — never a fabricated provenance story."""
        def _caller(prompt, model=None):
            return NO_STORY, 0.0

        res = generate_story_for_stop(WORK_MATRIX, WORK_MATERIAL_PROVENANCE_ONLY,
                                      caller=_caller, works_mode=True)
        self.assertFalse(res['ok'])
        self.assertEqual(res['story'], '')


class TestSurvivalStillWorks(unittest.TestCase):
    """The 832B re-seat backstop must keep working: a bar-clearing human story the
    merge dissolved is re-prepended; a provenance 'story' is not."""

    def test_human_story_is_reseated_when_merge_dissolved_it(self):
        from story_survival import repair_description, clears_bar
        res = repair_description(FLAT_NIGHT_WATCH, {"ok": True, "story": HUMAN_STORY})
        self.assertTrue(res.changed)
        self.assertTrue(clears_bar(res.description))
        self.assertIn("Rembrandt completed this colossal group portrait",
                      res.description)

    def test_provenance_story_is_not_reseated(self):
        from story_survival import repair_description
        res = repair_description(FLAT_NIGHT_WATCH,
                                 {"ok": True, "story": PROVENANCE_STORY})
        self.assertFalse(res.changed)
        self.assertFalse(res.story_clears)


if __name__ == "__main__":
    unittest.main(verbosity=2)
