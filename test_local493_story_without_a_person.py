#!/usr/bin/env python3
"""LOCAL-493 — a story does not require a person.

**Michael, 2026-08-19:** *"I question that the story should be always about a
person; for example Pompeii was destroyed because of volcanic eruption is a
story; especially with some facts, how many buildings were destroyed, what
inheritance did it leave to humanity... The same is true about reconstructions
and renovation."*

He is right, and the encyclopedic support is Prince, not Labov. Prince's minimal
story is three conjoined events, the first and third stative and **the second
active** — active, not human. "Pompeii was a living city / Vesuvius erupted /
Pompeii was buried" satisfies it exactly. Labov reads person-centric because he
studied people telling stories about their own lives; that is his domain, not his
definition.

The old prompt hard-coded the error in two places:

  * `"Build it around ONE NAMED PERSON and STAY WITH THEM"`, and
  * a refusal condition firing when *"the material names no person at all"*.

Pompeii returned NO_STORY. So did every reconstruction and every renovation.

**The repair is not to drop the constraint but to correct it.** The "person" rule
was never about people — it was there to stop subject-hopping, which is the
list-of-credits failure (a sentence each about the publisher, the printer and the
donor). The invariant that does that work is **continuity of subject**, not
humanity of subject.

Also bound here: Michael's ruling that **plot beats story** — the causal link is
the product, not the sequence — and the correction to the evaluation ban. The old
rule said "No evaluation", which named the one component Labov calls
indispensable. It meant *external* evaluation (the adjectives). Embedded
evaluation — the point shown through what was done, chosen, refused or lost — is
required, not banned.

These assert on the PROMPT TEXT because the prompt is the production artifact
here; `build_story_prompt` is what ships. Reverting either edit turns these red.
"""
import unittest

from story_pass import build_story_prompt, NO_STORY


MATRIX = {
    'canonical_title': 'Casa del Fauno',
    'venue_name': 'Pompeii Archaeological Park',
    'medium': 'Roman domus, mosaic floors',
}

MATERIAL = [
    'Vesuvius erupted in AD 79, burying Pompeii under several metres of ash.',
    'The site was rediscovered in 1748 and excavation has continued since.',
]


class TestSubjectNotPerson(unittest.TestCase):
    """The generator must not demand a human subject."""

    def setUp(self):
        self.prompt = build_story_prompt(MATRIX, MATERIAL)

    def test_does_not_demand_a_named_person(self):
        """The old instruction is gone, not merely softened."""
        self.assertNotIn('ONE NAMED PERSON', self.prompt)

    def test_still_demands_one_subject_held_throughout(self):
        """Continuity of subject is the real invariant and must survive."""
        self.assertIn('ONE NAMED SUBJECT', self.prompt)
        self.assertIn('STAY WITH THEM', self.prompt)

    def test_names_non_human_subjects_as_acceptable(self):
        """A place, an institution, an event or the object may carry the story."""
        low = self.prompt.lower()
        for subject in ('a place', 'an institution', 'the object'):
            self.assertIn(subject, low, f'{subject!r} not offered as a subject')

    def test_refusal_is_not_conditioned_on_a_person(self):
        """`NO_STORY` must key on 'nothing happened', never on 'nobody is named'.

        The exact failure: the material below has an eruption, a burial and a
        rediscovery, and not one person. Under the old rule that is NO_STORY.
        """
        self.assertNotIn('names no\n    person at all', self.prompt)
        self.assertNotIn('material names no person', self.prompt.replace('\n', ' '))
        self.assertIn('NOTHING THAT HAPPENED', self.prompt)
        self.assertIn('deliberately NOT a test for people', self.prompt)

    def test_instructs_writing_the_event_as_subject_when_no_person_exists(self):
        flat = ' '.join(self.prompt.split())
        self.assertIn('with the event as the subject', flat)
        for event in ('eruption', 'fire', 'war', 'rebuilding'):
            self.assertIn(event, flat.lower(), f'{event!r} not named as a story-bearer')

    def test_pompeii_shape_is_the_worked_example(self):
        """Michael's own example is in the prompt, so the shape is unambiguous."""
        self.assertIn('Pompeii', self.prompt)
        self.assertIn('Vesuvius', self.prompt)


class TestPlotNotSequence(unittest.TestCase):
    """Michael: plot beats story, because it carries causality not correlation."""

    def setUp(self):
        self.prompt = build_story_prompt(MATRIX, MATERIAL)

    def test_demands_causation_over_sequence(self):
        self.assertIn('BECAUSE', self.prompt)
        self.assertIn('NOT "AND THEN"', self.prompt.upper())

    def test_carries_forsters_worked_example(self):
        """One causal word is the entire distinction; the example makes it concrete."""
        flat = ' '.join(self.prompt.split())
        self.assertIn('the queen died OF GRIEF', flat)

    def test_outward_connection_must_state_why(self):
        """Michael's step 3 chain is only a plot if each link is a 'because'."""
        flat = ' '.join(self.prompt.split())
        self.assertIn('Say WHY that connection holds', flat)


class TestEvaluationIsShownNotBanned(unittest.TestCase):
    """Labov's evaluation is indispensable; only the EXTERNAL kind is filler."""

    def setUp(self):
        self.prompt = build_story_prompt(MATRIX, MATERIAL)

    def test_no_blanket_ban_on_evaluation(self):
        """The old rule literally read 'No evaluation'. That banned the point."""
        self.assertNotIn('No evaluation', self.prompt)

    def test_requires_the_point_to_be_shown(self):
        self.assertIn('SHOW THE POINT, DO NOT ANNOUNCE IT', self.prompt)

    def test_still_bans_every_external_evaluation_phrase(self):
        """Killing the blanket ban must not readmit the filler we measured."""
        for phrase in ('stands as a testament to', 'showcasing a unique',
                       'the transformative power of', 'transformative',
                       'vibrant', 'profound', 'revolutionary'):
            self.assertIn(phrase, self.prompt,
                          f'{phrase!r} no longer forbidden — filler can return')

    def test_offers_a_mechanical_test_for_external_evaluation(self):
        """Strip proper nouns and numbers; if praise remains, it is commentary."""
        flat = ' '.join(self.prompt.split())
        self.assertIn('delete every proper noun', flat)

    def test_carries_labovs_reportability_test(self):
        """'So what?' is the failure; 'It did?' is the pass — and 'It', not only 'He'."""
        self.assertIn('IT DID?', self.prompt)
        self.assertIn('so what?', self.prompt.lower())


class TestEventfulnessCriteria(unittest.TestCase):
    """Huhn/Schmid's five, which work for volcanoes and donors alike."""

    def setUp(self):
        self.prompt = build_story_prompt(MATRIX, MATERIAL)

    def test_asks_the_worthiness_questions_before_writing(self):
        flat = ' '.join(self.prompt.split())
        self.assertIn('IS IT WORTH TELLING?', flat)
        for criterion in ('consequences', 'unexpected', 'irreversible'):
            self.assertIn(criterion, flat.lower(), f'{criterion!r} criterion missing')

    def test_rejects_iterative_non_events(self):
        """'The press published many editions' is a routine, not an event."""
        flat = ' '.join(self.prompt.split())
        self.assertIn('is a routine, not an', flat)

    def test_asks_for_numbers(self):
        """Michael: how many destroyed, what inheritance — quantity earns 'It did?'"""
        flat = ' '.join(self.prompt.split())
        self.assertIn('how many were destroyed', flat)


class TestUnchangedInvariants(unittest.TestCase):
    """What this change must NOT have broken."""

    def setUp(self):
        self.prompt = build_story_prompt(MATRIX, MATERIAL)

    def test_never_invents(self):
        self.assertIn('must appear in the source material', self.prompt)
        self.assertIn('An invented story is the one unacceptable outcome',
                      self.prompt)

    def test_list_of_credits_still_called_out(self):
        flat = ' '.join(self.prompt.split())
        self.assertIn('is a list of credits, not a story', flat)

    def test_sentence_bounds_survive(self):
        self.assertIn('Between 3 and 5 sentences', self.prompt)

    def test_no_story_sentinel_still_reachable(self):
        self.assertIn(NO_STORY, self.prompt)

    def test_material_and_matrix_still_rendered(self):
        self.assertIn('Vesuvius erupted in AD 79', self.prompt)
        self.assertIn('Casa del Fauno', self.prompt)

    def test_spoken_register_preserved(self):
        self.assertIn('No markdown, no headings, no bullets', self.prompt)


if __name__ == '__main__':
    unittest.main(verbosity=2)
