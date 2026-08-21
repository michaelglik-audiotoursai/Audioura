#!/usr/bin/env python3
"""test_d500_roles_and_placeholders.py — the matrix fix.

  [1] "Not specified" never reaches a slot
  [2] the credit-line signal stops scoring a placeholder as a fact
  [3] hero / sponsor / builder — the three agents, per tour category

RED-CHECK notes on each class. Sections were run against the pre-D500 tree first.
"""
import os
import re
import unittest

import story_roles
from story_roles import HERO, SPONSOR, BUILDER, roles_in, fields_for_role
from story_worthiness import assess_stop_worthiness, _credit_line_carries_a_fact
from text_fold import is_placeholder

HERE = os.path.dirname(os.path.abspath(__file__))


def gtt_source():
    with open(os.path.join(HERE, 'generate_tour_text.py')) as fh:
        return fh.read()


# The three stops of the 08-20 baseline, exactly as the checklist delivered them.
STOP1 = {'canonical_title': 'Le Lézard aux plumes d’or', 'artist': 'Joan Miró',
         'publisher': 'Louis Broder', 'printed_by': '',
         'credit_line': 'Gift of Boris Fridman. © Successió Miró',
         'medium': 'Illustrated book with 40 color lithographs'}
STOP2 = {'canonical_title': 'Au Soleil du Plafond', 'artist': 'Juan Gris',
         'publisher': 'Not specified', 'printed_by': '',
         'credit_line': 'Not specified', 'medium': 'Not specified'}
STOP3 = {'canonical_title': 'Moses and Monotheism', 'artist': 'Salvador Dalí',
         'publisher': 'Not specified', 'printed_by': '',
         'credit_line': 'Not specified', 'medium': 'Illustrations'}


# ─── [1] placeholders never reach a slot ─────────────────────────────────────
class TestPlaceholderNeverReachesASlot(unittest.TestCase):
    """RED-CHECK: delete the four `_d500_ph(...)` lines in the LOCAL-419
    enrichment. `test_enrichment_filters_at_the_source` goes red."""

    def test_enrichment_filters_at_the_source(self):
        # Filtered where the checklist values ENTER, not at each consumer.
        # Downstream there are four of them — query synthesis, the worthiness
        # scorer, the story matrix and the focus-fact rotation — and LOCAL-498
        # was the fix applied to one of them.
        src = gtt_source()
        for field in ('_s_publisher', '_s_credit_line', '_s_medium', '_s_artist'):
            self.assertIn(f"{field} = '' if _d500_ph({field}) else {field}", src,
                          f'{field} is not placeholder-filtered at the source')

    def test_the_filter_runs_before_the_poi_is_written(self):
        # If it ran after, the POI would keep the placeholder and every consumer
        # reading the POI rather than the local would still see it.
        src = gtt_source()
        filt = src.index("_s_publisher = '' if _d500_ph(_s_publisher)")
        write = src.index("for _mk, _mv in (('publisher', _s_publisher),")
        self.assertLess(filt, write)

    def test_not_specified_is_recognised(self):
        for v in ('Not specified', 'not specified', 'NOT SPECIFIED', 'Unknown'):
            self.assertTrue(is_placeholder(v), v)


# ─── [2] the credit-line signal ──────────────────────────────────────────────
class TestCreditLineSignal(unittest.TestCase):
    """RED-CHECK: remove the `is_placeholder(credit)` check from
    `_credit_line_carries_a_fact`. Both tests below go red.

    "Not specified" is 13 characters and the guard above it is len<12, so it
    cleared by one character."""

    def test_placeholder_is_not_a_fact(self):
        self.assertFalse(_credit_line_carries_a_fact({'credit_line': 'Not specified'}))

    def test_a_real_credit_line_still_is(self):
        self.assertTrue(_credit_line_carries_a_fact(
            {'credit_line': 'Gift of Boris Fridman. © Successió Miró'}))

    def test_the_baseline_scores_are_corrected(self):
        # What the 08-20 report should have said. Stop 2 was reported 3/4 and
        # stop 3 4/4; both were credited with a credit-line fact they lack.
        self.assertEqual(assess_stop_worthiness(STOP1)['score'], 4)
        self.assertEqual(assess_stop_worthiness(STOP2)['score'], 2)
        self.assertEqual(assess_stop_worthiness(STOP3)['score'], 3)

    def test_all_four_signals_agree_about_placeholders(self):
        # The defect was one function out of four. Pin the class, not the case.
        blank = {'canonical_title': 'Not specified', 'artist': 'Not specified',
                 'publisher': 'Not specified', 'printed_by': 'Not specified',
                 'medium': 'Not specified', 'credit_line': 'Not specified'}
        v = assess_stop_worthiness(blank)
        self.assertEqual(v['score'], 0, f"placeholders scored as signals: {v['signals']}")
        self.assertFalse(v['worth_mining'])


# ─── [3] the three agents ────────────────────────────────────────────────────
class TestRoles(unittest.TestCase):
    """RED-CHECK: make `roles_in` skip its `is_placeholder` check, or drop the
    `claimed` de-duplication. `test_placeholder_is_not_an_agent` and
    `test_one_person_in_two_slots_is_one_agent` go red respectively."""

    def test_the_baseline_agent_counts(self):
        # THE number this whole exercise produced. Stops 2 and 3 have one agent.
        self.assertEqual(sum(1 for r in story_roles.ROLES
                             if roles_in(STOP1, 'museum')[r]), 2)
        self.assertEqual(sum(1 for r in story_roles.ROLES
                             if roles_in(STOP2, 'museum')[r]), 1)
        self.assertEqual(sum(1 for r in story_roles.ROLES
                             if roles_in(STOP3, 'museum')[r]), 1)

    def test_hero_and_sponsor_on_stop_one(self):
        got = roles_in(STOP1, 'museum')
        self.assertEqual(got[HERO]['value'], 'Joan Miró')
        self.assertEqual(got[SPONSOR]['value'], 'Louis Broder')
        self.assertIsNone(got[BUILDER], 'printed_by has never been filled in production')

    def test_placeholder_is_not_an_agent(self):
        got = roles_in({'artist': 'Joan Miró', 'publisher': 'Not specified'}, 'museum')
        self.assertIsNone(got[SPONSOR])

    def test_one_person_in_two_slots_is_one_agent(self):
        # A chef who owns the restaurant is one agent. Counting two is how a
        # "story" becomes one person described twice.
        got = roles_in({'chef': 'Barbara Lynch', 'owner': 'Barbara Lynch'}, 'restaurant')
        self.assertEqual(got[HERO]['value'], 'Barbara Lynch')
        self.assertIsNone(got[SPONSOR])

    def test_roles_are_not_museum_specific(self):
        # The point of the generalisation: `printed_by` is a livre-d'artiste
        # field that a walking tour can never fill.
        self.assertIn('architect', fields_for_role(HERO, 'walking'))
        self.assertIn('chef', fields_for_role(HERO, 'restaurant'))
        self.assertIn('engineer', fields_for_role(BUILDER, 'walking'))
        self.assertIn('investor', fields_for_role(SPONSOR, 'restaurant'))

    def test_an_unknown_category_can_still_name_a_hero(self):
        got = roles_in({'artist': 'Someone'}, 'category-we-have-never-seen')
        self.assertIsNotNone(got[HERO])

    def test_wired_into_the_generator(self):
        self.assertIn('from story_roles import summarise', gtt_source())


if __name__ == '__main__':
    unittest.main(verbosity=2)
