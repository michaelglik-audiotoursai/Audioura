#!/usr/bin/env python3
"""LOCAL-494 — the donor is never deleted from the tour.

**Michael, 2026-08-19, on `TOUR_MFA_RELEASE_20260819_0115.txt`:** *"one real
problem is that Fridman as a generous gifter is gone completely... The organizer,
charitable gifter, sponsor should not be dismissed, agree?"*

Reconstructed from `TOUR_MFA_RELEASE_RUN3.log`, every gate did its job:

  :235  checklist set `credit_line='Gift of Boris Fridman'`
  :364  LOCAL-423 correctly excluded two wrong Fridmans (a Mexican linguist and
        a New York gallery), leaving zero snippets about the real one
  :425  the unglossed gate searched corpus, asked the model, got nothing, and
        DEGRADED the name -> "The generous gift of this work to the museum..."

The defect is that the gate cannot distinguish a name carrying its own
provenance from a name the model asserted, and that it reads "no third-party web
page about this collector" as *unverified* rather than as *private individual, as
expected*.

These tests assert on BEHAVIOUR, not on prompt text: a provenance-backed name
survives the degrade path, the guard-failure path, and the no-gloss path.

Run: python3 -m pytest test_local494_provenance_never_degraded.py -q
"""
import unittest

import provenance_gloss as pg
from unglossed_reference_gate import (apply_glosses_to_text, supply_glosses,
                                      compose_glosses)


# The real stop record from the 2026-08-19 release run.
FRIDMAN_STOP = {
    'name': "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)",
    'credit_line': 'Published by Louis Broder. Gift of Boris Fridman',
    'artist': 'Joan Miró',
    'medium': 'Illustrated book with 40 color lithographs',
}

# The sentence as it stood before the gate ran (RUN3.log:520).
HOST = ("The museum's collection was significantly enriched when Boris Fridman "
        "donated this piece.")


class TestProvenanceExtraction(unittest.TestCase):

    def test_reads_the_donor_out_of_the_credit_line(self):
        roles = pg.extract_provenance_roles(FRIDMAN_STOP)
        self.assertEqual(roles.get('Boris Fridman'), 'donor')

    def test_reads_the_publisher_from_the_same_field(self):
        roles = pg.extract_provenance_roles(FRIDMAN_STOP)
        self.assertEqual(roles.get('Louis Broder'), 'publisher')

    def test_gloss_needs_no_network_and_names_the_act(self):
        gloss = pg.provenance_gloss_for('Boris Fridman', FRIDMAN_STOP)
        self.assertIsNotNone(gloss)
        self.assertIn('gave this work', gloss)

    def test_matches_a_shortened_surname_in_the_prose(self):
        """The text may say "Fridman" where the record says "Boris Fridman"."""
        self.assertIsNotNone(pg.provenance_gloss_for('Fridman', FRIDMAN_STOP))

    def test_does_not_match_an_unrelated_name(self):
        """The exemption must not become a blanket pass for every name."""
        self.assertIsNone(pg.provenance_gloss_for('Sigmund Freud', FRIDMAN_STOP))
        self.assertIsNone(pg.provenance_gloss_for('Salvador Dalí', FRIDMAN_STOP))

    def test_ignores_placeholder_records(self):
        """D486/LOCAL-491: 'Not specified' became a person once already."""
        for junk in ('Not specified', 'N/A', 'unknown', ''):
            self.assertEqual(
                pg.extract_provenance_roles({'credit_line': f'Gift of {junk}'}),
                {}, f'{junk!r} was read as a donor')

    def test_strips_the_collection_tail_museums_append(self):
        stop = {'credit_line': 'Gift of Boris Fridman in memory of his father'}
        self.assertIn('Boris Fridman', pg.extract_provenance_roles(stop))

    def test_empty_record_is_safe(self):
        self.assertEqual(pg.extract_provenance_roles({}), {})
        self.assertIsNone(pg.provenance_gloss_for('Anyone', {}))


class TestNeverDegraded(unittest.TestCase):
    """The behaviour Michael asked for: the gifter is not dismissed."""

    def test_provenance_ref_with_no_gloss_keeps_the_name(self):
        """The exact 2026-08-19 path: lookup failed, so the name was dropped."""
        ref = {'entity': 'Boris Fridman', 'sentence': HOST,
               'triage': 'gloss_needed', 'provenance': True}
        out, failures = apply_glosses_to_text(HOST, [ref])
        self.assertIn('Boris Fridman', out)
        self.assertEqual(ref['stage'], 'provenance_kept')

    def test_without_provenance_the_name_is_still_degraded(self):
        """Control: the gate's normal behaviour is unchanged for other names.

        Without this, the tests above would pass on a gate that had simply
        stopped degrading anything.
        """
        ref = {'entity': 'Boris Fridman', 'sentence': HOST,
               'triage': 'gloss_needed'}
        out, _ = apply_glosses_to_text(HOST, [ref])
        self.assertNotIn('Boris Fridman', out)

    def test_a_failing_guard_drops_the_gloss_not_the_person(self):
        """A malformed gloss is a reason to drop the GLOSS, not the human."""
        ref = {'entity': 'Boris Fridman', 'sentence': HOST,
               'triage': 'gloss_needed', 'provenance': True,
               # long enough to fail _guard_length
               'gloss': 'the collector who ' + 'very ' * 40 + 'generously gave it'}
        out, failures = apply_glosses_to_text(HOST, [ref])
        self.assertIn('Boris Fridman', out)
        self.assertEqual(ref['stage'], 'provenance_kept')

    def test_a_good_provenance_gloss_is_applied(self):
        ref = {'entity': 'Boris Fridman', 'sentence': HOST,
               'triage': 'gloss_needed', 'provenance': True,
               'gloss': 'the collector who gave this work to the museum'}
        out, failures = apply_glosses_to_text(HOST, [ref])
        self.assertIn('Boris Fridman', out)
        self.assertIn('the collector who gave this work', out)
        self.assertEqual(failures, [])


class TestPaidStagesAreSkipped(unittest.TestCase):
    """A documented name must not cost a corpus search or a model call."""

    def test_supply_glosses_skips_provenance_refs(self):
        refs = [{'entity': 'Boris Fridman', 'sentence': HOST,
                 'triage': 'gloss_needed', 'provenance': True,
                 'gloss': 'the collector who gave this work to the museum'}]
        out, tokens, cost, _ = supply_glosses(refs, [], api_key='sk-unused')
        self.assertEqual((tokens, cost), (0, 0.0))
        self.assertEqual(out[0]['gloss'],
                         'the collector who gave this work to the museum')

    def test_compose_glosses_skips_provenance_refs(self):
        """ROLE_GLOSSES are appositives already; recomposing can only distort,
        and a compose returning DROP would delete a documented name."""
        refs = [{'entity': 'Boris Fridman', 'sentence': HOST,
                 'triage': 'gloss_needed', 'provenance': True,
                 'raw_fact': 'the collector who gave this work to the museum',
                 'gloss': 'the collector who gave this work to the museum'}]
        out, tokens, cost, _ = compose_glosses(refs, api_key='sk-unused')
        self.assertEqual((tokens, cost), (0, 0.0))


class TestRoleGlossShape(unittest.TestCase):
    """LOCAL-492: a gloss is spliced in as an appositive and must fit."""

    def test_every_role_gloss_is_a_noun_phrase(self):
        for role, gloss in pg.ROLE_GLOSSES.items():
            self.assertEqual(gloss, gloss.lstrip(),
                             f'{role}: leading whitespace')
            self.assertFalse(gloss.endswith('.'), f'{role}: ends with a period')
            self.assertEqual(gloss, gloss.lower().replace('  ', ' '),
                             f'{role}: not lowercase')

    def test_the_sponsor_roles_michael_named_are_all_covered(self):
        """"The organizer, charitable gifter, sponsor should not be dismissed"."""
        for role in ('donor', 'patron', 'sponsor', 'founder'):
            self.assertIn(role, pg.ROLE_GLOSSES)


if __name__ == '__main__':
    unittest.main(verbosity=2)
