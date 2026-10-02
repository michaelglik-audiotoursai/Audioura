#!/usr/bin/env python3
"""LOCAL-495 — the detector must accept the stories the generator may now write.

**The mismatch this closes, and LEAD created it.** LOCAL-493 changed
`story_pass.py` so the generator may build a story around any acting subject —
"Build it around ONE NAMED SUBJECT", with Pompeii as the worked example. It did
not change `story_opportunity_scan.py`, which still required a PERSON:

  * `measure()` set `can_carry = (kind == 'proper noun')`, and `_PROPER_SPAN`
    needs TWO capitalised tokens, so "Pompeii", "Vesuvius" and "Herculaneum"
    were not handles at all — invisible, not merely rejected;
  * `_AGENCY_VERB` held no verb a non-human agent uses: no *erupted*, *buried*,
    *collapsed*, *flooded*, and none of the repair verbs Michael named
    (*restored*, *reconstructed*, *renovated*);
  * `_bridge_pronouns` extended a run across "he"/"she" for people and gave a
    place nothing, so a town subject could only score as high as its literal
    name was repeated while a person subject was bridged;
  * `verdict()` printed "the bar is 3 consecutive sentences about one person",
    and `generate_tour_text.py:13406` prints that string on every run.

A refusal here fires the LOCAL-487 retry, so the two halves would have disagreed
on every non-person stop and paid for a retry each time — D483's defect class
(two halves of one instrument reading different inputs), reintroduced by the very
session that keeps finding it.

**Michael, 2026-08-19:** *"I question that the story should be always about a
person; for example Pompeii was destroyed because of volcanic eruption is a
story... The same is true about reconstructions and renovation."*

**The controls matter more than the new cases.** A detector that has simply
become permissive would pass every test above. `TestStillRefusesNonStories`
is what proves it has not.
"""
import unittest

import story_opportunity_scan as s


def scan(text):
    m = s.measure(text)
    return m, s.verdict(m)


def is_story(text):
    _, v = scan(text)
    return not v['needs_additional_story']


# Michael's own example, written to the three-part shape.
POMPEII = ("Pompeii was a prosperous Roman town of some twelve thousand people. "
           "In AD 79 Vesuvius erupted and buried Pompeii under four metres of ash. "
           "The town stayed buried until excavation began in 1748, and nothing of "
           "the harbour survives.")

# "The same is true about reconstructions and renovation."
RENOVATION = ("The Old State House had stood since 1713 with its council chamber "
              "intact. The building was gutted in an 1830 renovation that "
              "demolished the chamber. The structure was only restored to its "
              "1713 plan in 1882, and nothing of the original panelling survives.")

RECONSTRUCTION = ("The reconstruction began in 1946 with almost no surviving "
                  "drawings. The reconstruction relied on tourist photographs and "
                  "one set of 18th-century paintings. The work was finished in "
                  "1984, although the eastern wing was never rebuilt.")

# The person case, which must keep working exactly as before.
PERSON_STORY = ("Broder spent three years persuading Miro. "
                "Miro refused twice. "
                "He relented only after Broder agreed to let him choose the printer.")

# Exposition: a named person, three sentences, nothing done and nothing at stake.
EXPOSITION = ("Joan Miro was a Catalan artist who worked in Paris. "
              "He was known for his surrealist imagery. "
              "His work is celebrated worldwide for its vibrant colour.")

# A list of credits about one place — the failure the "one subject" rule exists
# to catch, and it must NOT be rescued by any of this.
CATALOGUE = ("The gallery holds forty lithographs. "
             "The gallery is named for the Linde Family. "
             "The collection is displayed in rotation.")


class TestStoryWithoutAPerson(unittest.TestCase):

    def test_pompeii_is_a_story(self):
        self.assertTrue(is_story(POMPEII),
                        "Michael's own example is still refused")

    def test_pompeii_is_carried_by_the_place_not_a_person(self):
        m, _ = scan(POMPEII)
        self.assertEqual(m['longest_run']['handle'], 'Pompeii')

    def test_single_token_place_names_are_visible_at_all(self):
        """The prior failure was invisibility, not rejection."""
        surfaces = {h['surface'] for h in s.measure(POMPEII)['handles']}
        self.assertIn('Pompeii', surfaces)
        self.assertIn('Vesuvius', surfaces)

    def test_a_renovation_is_a_story(self):
        self.assertTrue(is_story(RENOVATION))

    def test_a_reconstruction_can_be_its_own_subject(self):
        self.assertTrue(is_story(RECONSTRUCTION))
        m, _ = scan(RECONSTRUCTION)
        self.assertEqual(m['longest_run']['handle'], 'reconstruction')

    def test_non_human_agency_verbs_are_recognised(self):
        for verb in ('erupted', 'buried', 'collapsed', 'flooded', 'razed'):
            self.assertRegex(f'The city {verb} in an afternoon.',
                             s._AGENCY_VERB,
                             f'{verb!r} not counted as agency')

    def test_repair_verbs_are_recognised(self):
        """Michael named reconstructions and renovation specifically."""
        for verb in ('restored', 'reconstructed', 'renovated', 'excavated',
                     'rediscovered'):
            self.assertRegex(f'The site was {verb} in 1955.', s._AGENCY_VERB,
                             f'{verb!r} not counted as agency')


class TestDefiniteAnaphorBridging(unittest.TestCase):
    """"The town" does for Pompeii what "he" does for Miro."""

    def test_the_town_continues_the_subject(self):
        m, _ = scan(POMPEII)
        pompeii = next(h for h in m['handles'] if h['surface'] == 'Pompeii')
        self.assertGreaterEqual(pompeii['run'], 3,
                                'run did not bridge across "The town"')

    def test_a_title_gets_no_bridging(self):
        """Only subjects that can carry a story get the benefit."""
        owner = {'kind': 'title', 'surface': 'Moses and Monotheism'}
        self.assertEqual(s._bridge_pronouns([0], ['a', 'the book was lost'],
                                            [owner], owner), [0])


class TestStillRefusesNonStories(unittest.TestCase):
    """The controls. Without these, a detector that passes everything passes."""

    def test_exposition_about_a_named_person_is_still_refused(self):
        self.assertFalse(is_story(EXPOSITION))

    def test_a_list_of_credits_is_still_refused(self):
        self.assertFalse(is_story(CATALOGUE))

    def test_subject_hopping_is_still_refused(self):
        """House -> renovation -> building is three subjects, not one story."""
        hopping = ("The Old State House had stood since 1713 with its original "
                   "council chamber intact. A 1830 renovation gutted the interior "
                   "and the chamber was demolished. The building was only restored "
                   "to its 1713 plan in 1882, and nothing survives.")
        self.assertFalse(is_story(hopping))

    def test_agency_without_stakes_is_still_exposition(self):
        flat = ("Vesuvius erupted in AD 79. "
                "Vesuvius erupted again in 1631. "
                "Vesuvius erupted most recently in 1944.")
        _, v = scan(flat)
        self.assertTrue(v['needs_additional_story'])

    def test_months_and_habit_capitals_are_not_subjects(self):
        text = ("The work arrived in March and was catalogued in April. "
                "The Gift was recorded in the Museum register in May. "
                "The Collection grew steadily.")
        surfaces = {h['surface'] for h in s.measure(text)['handles']}
        for junk in ('March', 'April', 'May', 'Gift', 'Museum', 'Collection'):
            self.assertNotIn(junk, surfaces, f'{junk!r} became a story candidate')


FULL_NAME_STORY = ("Louis Broder spent three years persuading Joan Miro. "
                   "Joan Miro refused twice. "
                   "He relented only after Louis Broder agreed to let him choose "
                   "the printer.")


class TestPersonPathUnchanged(unittest.TestCase):
    """LOCAL-487's behaviour on two-token names must survive bit-for-bit.

    Verified against HEAD before committing: `FULL_NAME_STORY` returns
    handle='Joan Miro', run=3, story=True on both trees, and `EXPOSITION`
    returns False on both. The person path is genuinely untouched.
    """

    def test_full_name_story_still_qualifies(self):
        self.assertTrue(is_story(FULL_NAME_STORY))

    def test_pronoun_bridging_still_works(self):
        m, _ = scan(FULL_NAME_STORY)
        self.assertGreaterEqual(m['longest_run']['run'], 3)


class TestSingleTokenNamesWerePreviouslyInvisible(unittest.TestCase):
    """A pre-existing defect this change also repairs, found by the red-check.

    `_PROPER_SPAN` requires TWO capitalised tokens. So a story about "Broder"
    and "Miro" — no first names — produced **zero handles** and scored run=0,
    handle=None. Not "refused": unmeasurable.

    That is not an edge case. Naming someone in full once and then by surname is
    how the prose is supposed to read, and it is what the story prompt asks for
    ("you may refer to them as he or she after the first naming"). Every stop
    whose story used a bare surname throughout was invisible to the instrument
    that decides whether a retry is needed.

    Found only because `TestPersonPathUnchanged` went red against HEAD when it
    should have been green — the red-check catching a wrong assumption in the
    test rather than in the code.
    """

    def test_surname_only_story_is_now_visible(self):
        self.assertTrue(is_story(PERSON_STORY))

    def test_surname_only_story_has_handles_at_all(self):
        m, _ = scan(PERSON_STORY)
        self.assertNotEqual(m['longest_run']['handle'], None,
                            'single-token names produce no handles')
        self.assertGreaterEqual(m['longest_run']['run'], 3)


class TestVerdictWording(unittest.TestCase):
    """This string is printed by generate_tour_text.py:13406 every run."""

    def test_bar_is_stated_as_subject_not_person(self):
        _, v = scan(CATALOGUE)
        self.assertIn('one subject', v['why'])
        self.assertNotIn('one person', v['why'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
