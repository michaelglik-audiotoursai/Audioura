#!/usr/bin/env python3
"""D489 step (a) — the instrument that asks what KIND the material is.

Every existing "is there enough material" instrument counts things:
`generate_tour_text.py:613` counts QIDs, `:9120` counts characters, LOCAL-487's
retry counts words. On the 2026-08-19 01:15 tour all three stops cleared the
volume test with 140/143/249 words and the story detector still refused all
three. **The material was sufficient and useless**, and replenishment could not
fire because by its own instrument nothing was wrong.

This measures the missing property: does the material contain **an active change
of state** — Prince's middle event, which D487 settled need not involve a person.

**It reports and never gates.** LEAD's claim that the two verdicts disagree
constantly is the same shape as LOCAL-410's false zero (D423), which was nearly
published. The disagreement rate over real runs decides whether the re-query loop
gets built.
"""
import unittest

from material_kind import (classify_material, summarise_stop, has_agentive_action,
                           KIND_EVENTFUL, KIND_RICH, KIND_INERT)


# Catalogue prose: the 01:15 tour's actual failure mode.
INERT = ['Joan Miro was a Catalan artist known for his surrealist imagery.',
         'The book contains forty colour lithographs and was published in 1971.',
         'It is displayed in the Linde Family gallery.']

# Something happens, nothing is at stake.
ACTIVE = ['Louis Broder published the book in 1971.',
          'Mourlot Freres printed the lithographs.']

# Something happens AND something is lost — the material a story needs.
EVENTFUL = ['For technical reasons, Miro decided to destroy the lithographs.',
            'Gris died in 1927, leaving the project unfinished.']

# D487: an agent need not be human.
NON_HUMAN = ['Vesuvius erupted in AD 79 and buried the town under four metres '
             'of ash, and nothing of the harbour survives.']


class TestClassification(unittest.TestCase):

    def test_catalogue_prose_is_inert(self):
        self.assertEqual(classify_material(INERT)['kind'], KIND_INERT)

    def test_action_without_stakes_is_active_not_eventful(self):
        """The distinction that matters: Broder publishing is not a story."""
        self.assertEqual(classify_material(ACTIVE)['kind'], KIND_RICH)

    def test_action_with_stakes_is_eventful(self):
        self.assertEqual(classify_material(EVENTFUL)['kind'], KIND_EVENTFUL)

    def test_a_non_human_agent_counts(self):
        """D487: a volcano acts. Prince requires 'active', not 'human'."""
        self.assertEqual(classify_material(NON_HUMAN)['kind'], KIND_EVENTFUL)

    def test_volume_and_kind_are_independent(self):
        """The whole point: lots of characters, no event."""
        bulky = INERT * 12
        m = classify_material(bulky)
        self.assertGreater(m['chars'], 1000)
        self.assertEqual(m['kind'], KIND_INERT)
        self.assertEqual(m['active_sentences'], 0)

    def test_reports_the_sentence_it_found(self):
        """An instrument reporting only a number is one nobody can check (D423)."""
        m = classify_material(EVENTFUL)
        self.assertTrue(m['best_sentence'], 'no sentence reported')
        self.assertIn(m['best_sentence'][:30],
                      ' '.join(EVENTFUL),
                      'reported a sentence that is not in the input')

    def test_empty_and_junk_inputs_are_safe(self):
        for junk in ([], None, [''], [None], ['   ']):
            self.assertEqual(classify_material(junk)['kind'], KIND_INERT)


class TestDisagreementFlag(unittest.TestCase):
    """The line that will decide whether the re-query loop gets built."""

    def test_flags_enough_material_of_the_wrong_kind(self):
        line = summarise_stop('stop', INERT, volume_verdict='rich')
        self.assertIn('DISAGREE', line)

    def test_does_not_flag_when_both_agree_it_is_poor(self):
        line = summarise_stop('stop', INERT, volume_verdict='thin')
        self.assertNotIn('DISAGREE', line)

    def test_does_not_flag_when_the_material_is_eventful(self):
        line = summarise_stop('stop', EVENTFUL, volume_verdict='rich')
        self.assertNotIn('DISAGREE', line)

    def test_line_carries_both_verdicts(self):
        line = summarise_stop('stop', ACTIVE, volume_verdict='medium')
        self.assertIn('kind=active', line)
        self.assertIn('volume=medium', line)


class TestAgentlessPassive(unittest.TestCase):
    """"The passive voice is eating the actors" — 2026-08-19 review, defect #1.

    An agentless passive is a state wearing an action's clothes. Prince's middle
    event needs an AGENT, so "the book was published in 1971" is not material for
    a story however many agency verbs it contains.
    """

    def test_agentless_passive_is_not_an_action(self):
        self.assertFalse(has_agentive_action('The book was published in 1971.'))

    def test_the_sentence_the_review_singled_out(self):
        """From the 01:15 tour: the one human act, reported without an actor."""
        self.assertFalse(has_agentive_action(
            'Their collaboration was posthumously realized in 1955.'))

    def test_a_passive_that_keeps_its_agent_still_counts(self):
        self.assertTrue(has_agentive_action(
            'The book was published by Louis Broder in 1971.'))

    def test_active_voice_counts(self):
        self.assertTrue(has_agentive_action(
            'Louis Broder published the book in 1971.'))

    def test_an_infinitive_after_decided_counts(self):
        """"Miro decided to destroy the lithographs" — the best consequence in
        the MFA tour, and `destroy` was missing from the vocabulary entirely."""
        self.assertTrue(has_agentive_action(
            'For technical reasons, Miro decided to destroy the lithographs.'))

    def test_pure_description_is_not_an_action(self):
        self.assertFalse(has_agentive_action('Joan Miro was a Catalan artist.'))

    def test_passive_count_is_reported_separately(self):
        """So a run shows how much material is action with the actor removed."""
        m = classify_material(['The book was published in 1971.',
                               'The edition was printed in Paris.'])
        self.assertEqual(m['agentless_passive_sentences'], 2)
        self.assertEqual(m['active_sentences'], 0)
        self.assertEqual(m['kind'], KIND_INERT)


class TestMakingVerbs(unittest.TestCase):
    """LOCAL-497: verbs describing how an object came to exist were absent.

    The scanner's own comment says the list "was tuned on museum material —
    refused, PRINTED, donated". `printed` was never in it, and neither was
    `published`. On an exhibition whose subject is publishers and printers, the
    two commonest actions both scored agency=0.
    """

    def test_publishing_and_printing_are_actions(self):
        for s in ('Louis Broder published the book.',
                  'Mourlot Freres printed the lithographs.',
                  'Maeght issued the edition in 1971.'):
            self.assertTrue(has_agentive_action(s), s)

    def test_making_verbs_reach_the_classifier(self):
        m = classify_material(['Louis Broder published the book in 1971.'])
        self.assertEqual(m['kind'], KIND_RICH)


class TestSharesOneVocabulary(unittest.TestCase):
    """Two modules disagreeing about what an action is would be D483's defect."""

    def test_reuses_the_scanner_vocabularies(self):
        import material_kind
        import story_opportunity_scan as scan
        self.assertIs(material_kind._AGENCY_VERB, scan._AGENCY_VERB)
        self.assertIs(material_kind._STAKES, scan._STAKES)


if __name__ == '__main__':
    unittest.main(verbosity=2)


class TestPilotFoundBugs(unittest.TestCase):
    """Two defects the first live pilot exposed, both in this instrument.

    Both would have made it report ZERO disagreements on every run — i.e.
    "LEAD's claim is wrong" — for reasons having nothing to do with the claim.
    A report-only pilot earning its keep before anything was gated on it.
    """

    def test_attributive_participles_are_not_actions(self):
        """The pilot's first stop reported its best sentence as:

            "Illustrated book with forty lithographs (including wrapper front
             and cover)."

        The purest catalogue line in the tour, scored as an action, by the
        instrument built to tell catalogue prose from stories.
        """
        for s in ('Illustrated book with forty lithographs.',
                  'Printed matter from the Broder archive.',
                  'A bound volume in publisher vellum.',
                  'Engraved plates, forty in number.'):
            self.assertFalse(has_agentive_action(s), s)

    def test_making_verbs_still_count_with_an_agent(self):
        """The narrowing must not undo LOCAL-497."""
        for s in ('Louis Broder published the book in 1971.',
                  'The lithographs were printed by Mourlot Freres.',
                  'He published it himself after the war.'):
            self.assertTrue(has_agentive_action(s), s)

    def test_non_making_verbs_are_unaffected(self):
        """Only the making verbs need agent evidence."""
        self.assertTrue(has_agentive_action('Vesuvius erupted and buried the town.'))
        self.assertTrue(has_agentive_action('Miro refused twice.'))

    def test_disagree_fires_on_the_coverage_vocabulary(self):
        """`needs_replenishment` returns COVERED/EMPTY/VENUE_ONLY, not
        rich/medium/thin. The first version compared against the wrong
        vocabulary, so the flag could never fire."""
        line = summarise_stop('s', INERT, volume_verdict='COVERED')
        self.assertIn('DISAGREE', line)

    def test_disagree_accepts_both_vocabularies(self):
        for verdict in ('COVERED', 'covered', 'rich', 'medium'):
            self.assertIn('DISAGREE', summarise_stop('s', INERT, volume_verdict=verdict),
                          f'{verdict!r} not recognised as a satisfied volume verdict')

    def test_unknown_verdict_does_not_flag(self):
        """Fail silent, not false-positive, on a vocabulary we do not know."""
        for verdict in ('UNKNOWN', 'EMPTY', 'VENUE_ONLY', '', None):
            self.assertNotIn('DISAGREE', summarise_stop('s', INERT, volume_verdict=verdict))

    def test_action_without_stakes_also_disagrees(self):
        """Material that acts but risks nothing is the 01:15 failure exactly."""
        self.assertIn('DISAGREE', summarise_stop('s', ACTIVE, volume_verdict='COVERED'))


class TestEventlessTriggersReplenishment(unittest.TestCase):
    """D492(b) — replenishment now fires on KIND, not only on volume.

    Measured, not assumed. Three clean runs of the MFA exhibition on
    2026-08-19 11:20-11:32: the volume test returned COVERED on **9 of 9**
    stop-observations while the kind test found no eventful sentence in
    **6 of 9** — the same two stops failing every run and the same one passing,
    with no run-to-run variance. Both failing stops carried 46-113 sentences of
    retrieved material. They were not thin. They were thin IN KIND, and
    `needs_replenishment` could not see it, so the loop never fired on the stops
    that most needed it.
    """

    COVERED = {'verdict': 'COVERED'}
    BULKY_INERT = ['Joan Miro was a Catalan artist known for surrealism. ' * 40]
    BULKY_EVENTFUL = ['Miro decided to destroy the lithographs and only '
                      'twelve survive. ' * 40]

    def setUp(self):
        from story_replenish import needs_replenishment
        self.n = needs_replenishment

    def test_bulky_but_eventless_now_needs_more(self):
        r = self.n(self.BULKY_INERT, self.COVERED)
        self.assertTrue(r['needs_more'])
        self.assertTrue(r['eventless'])
        self.assertFalse(r['thin'], 'this stop is NOT thin by volume')

    def test_bulky_and_eventful_does_not(self):
        """The control: the gate must not fire on everything."""
        r = self.n(self.BULKY_EVENTFUL, self.COVERED)
        self.assertFalse(r['needs_more'])
        self.assertFalse(r['eventless'])

    def test_genuinely_thin_still_fires(self):
        r = self.n(['short.'], self.COVERED)
        self.assertTrue(r['needs_more'])
        self.assertTrue(r['thin'])

    def test_the_reason_is_reported_separately(self):
        """The log must say WHICH test fired, or the next session cannot tell
        a volume failure from a kind failure — which is the whole distinction."""
        r = self.n(self.BULKY_INERT, self.COVERED)
        self.assertIn('eventless', r)
        self.assertIn('kind', r)
        self.assertEqual(r['kind'], KIND_INERT)

    def test_a_missing_classifier_degrades_to_no_opinion(self):
        """A false `needs_more` spends money on every stop, so an unavailable
        classifier must never manufacture one."""
        import builtins
        import story_replenish
        real_import = builtins.__import__

        def blocked(name, *a, **k):
            if name == 'material_kind':
                raise ImportError('simulated')
            return real_import(name, *a, **k)

        builtins.__import__ = blocked
        try:
            r = story_replenish.needs_replenishment(self.BULKY_INERT, self.COVERED)
        finally:
            builtins.__import__ = real_import
        self.assertFalse(r['eventless'], 'unavailable classifier invented a verdict')
        self.assertFalse(r['needs_more'])
        self.assertEqual(r['kind'], 'unknown')


class TestPlaceholderQueries(unittest.TestCase):
    """LOCAL-498 — a placeholder must never become a search term.

    Exposed the moment D492b made the eventless trigger fire. The 12:05 run
    issued, for stop 3, all three of:

        "Not specified" "Moses and Monotheism" history
        "Salvador Dali" "Not specified" collaboration
        "Not specified" "Moses and Monotheism" collection

    Three of three follow-up queries poisoned, on the stop the new trigger
    exists to rescue: the loop fired correctly and then spent its entire capped
    budget searching for a placeholder.

    Exactly D486/LOCAL-491's defect — `story_focus_fact` built the focus fact
    "Not specified published Moses and Monotheism." — and `text_fold`'s
    `is_placeholder` was written that same night to end it. `story_replenish`
    simply never called it.
    """

    STOP3 = {'canonical_title': 'Moses and Monotheism',
             'english_title': 'Moses and Monotheism',
             'artist': 'Salvador Dali',
             'publisher': 'Not specified',
             'printed_by': 'Not specified',
             'credit_line': 'Not specified',
             'venue_name': 'Museum of Fine Arts, Boston'}

    STOP1 = {'canonical_title': 'Le Lezard aux plumes d or',
             'english_title': 'The Lizard with Golden Feathers',
             'artist': 'Joan Miro',
             'publisher': 'Louis Broder',
             'printed_by': 'Mourlot Freres',
             'credit_line': 'Gift of Boris Fridman',
             'venue_name': 'Museum of Fine Arts, Boston'}

    def setUp(self):
        from story_replenish import build_followup_queries
        self.b = build_followup_queries

    def test_no_query_contains_a_placeholder(self):
        for q in self.b(self.STOP3):
            self.assertNotIn('Not specified', q)
            self.assertNotIn('not specified', q.lower())

    def test_falls_back_to_an_honest_query(self):
        """Losing the poisoned queries must not leave the stop with nothing."""
        qs = self.b(self.STOP3)
        self.assertTrue(qs, 'no follow-up at all for a stop that needs one')
        self.assertIn('Moses and Monotheism', qs[0])

    def test_real_matrix_values_are_untouched(self):
        """The control: the filter must not eat legitimate agents."""
        qs = self.b(self.STOP1)
        joined = ' '.join(qs)
        self.assertIn('Louis Broder', joined)
        self.assertIn('Mourlot Freres', joined)
        self.assertIn('Joan Miro', joined)

    def test_placeholder_variants_are_all_caught(self):
        for junk in ('Not specified', 'not specified', 'N/A', 'unknown',
                     'None', 'TBD'):
            m = dict(self.STOP3, publisher=junk)
            for q in self.b(m):
                self.assertNotIn(junk.lower(), q.lower(),
                                 f'{junk!r} reached a query')
