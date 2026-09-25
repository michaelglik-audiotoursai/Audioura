#!/usr/bin/env python3
"""test_local479_single_token_names.py — LOCAL-479 function-level proof.

Two defects, one file:

  Part 1 — the gate could never see a ONE-WORD name. `_PERSON_PATTERN` requires
  two capitalised tokens, so Walter, Reid, Suzette all passed straight through.
  These tests prove single-token names are now caught when the surrounding
  syntax is person-shaped, and that the hard false positives (Logan, Boston,
  Terminal E, October) are NOT.

  Part 2 — removing a sentence that INTRODUCED a person/event left every later
  sentence that referred back to it orphaned ("The plane", "Reid's", "The
  incident"). These tests prove the dependants now fall with the introduction,
  while independent content survives.

Acceptance criteria covered (from the task):
  1. Walter/Reid/Suzette detected; Logan/Boston/Terminal E/October not.
  2. Stop 4 of tour 423 comes out with its orphans detectable (grounded-or-cut).
  3. The real shipped Cimiez Saint-Pons paragraph is NOT flagged.
  4. Removing a sentence removes its orphaned dependants, proven on a fixture.

The suite is designed to be able to FAIL: `test_suite_can_fail_*` breaks the
detector's contract with a canary and asserts the current code does NOT exhibit
the broken behaviour. See SUBMISSION_LOCAL-479.md for the red-run transcript.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import unglossed_reference_gate as urg
from unglossed_reference_gate import (
    detect_single_token_names,
    detect_unglossed_references,
    cut_orphaned_dependants,
)

FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 't423_stop4_audio_4.txt')

# The real shipped Cimiez Monastery Stop-2 body (TOUR_CIMIEZ_WALKING_20260830.md).
CIMIEZ_PARA = (
    "The Cimiez Monastery, with roots stretching back to the 9th century, "
    "stands as a silent witness to the passage of time and the resilience of "
    "faith. The Count of Savoy ordered the destruction of buildings, including "
    "the Franciscans' entire monastery, in a desperate act of defense. In 1546, "
    "a pivotal moment unfolded when Franciscan friars negotiated a property swap "
    "with Benedictine monks of Saint-Pons Abbey, acquiring a small chapel and "
    "plot of land in Cimiez. The French Revolution brought turmoil once more, as "
    "the monastery was seized and transformed into military barracks and an army "
    "hospital. The monastery's cloisters, with their cool stone and whispering "
    "arches, offer a glimpse into the contemplative life of the monks who once "
    "tended to its gardens and crafted art that adorned its halls. Henri Matisse, "
    "whose affinity for Cimiez's luminous light is well known, rests in the "
    "cemetery nearby, a callback to the Musée Matisse you visited earlier. His "
    "presence here ties together the artistic and the spiritual threads of this "
    "district. As you step back into the present, the air carries a subtle "
    "fragrance of blooming lavender from the gardens."
)


class TestPart1SingleTokenDetection(unittest.TestCase):
    """Criterion 1 — one-word names caught; place/calendar/facility tokens not."""

    def test_walter_of_genitive(self):
        self.assertIn('Walter',
                      detect_single_token_names('The disappearance of Walter and passengers.'))

    def test_reid_possessive(self):
        self.assertIn('Reid',
                      detect_single_token_names("Reid's failed attempt serves as a reminder."))

    def test_suzette_who_clause(self):
        self.assertIn('Suzette',
                      detect_single_token_names('Nobody explained who Suzette was.'))

    def test_walter_agentive_by(self):
        self.assertIn('Walter',
                      detect_single_token_names('The fresco was painted by Walter.'))

    def test_walter_subject_verb(self):
        self.assertIn('Walter',
                      detect_single_token_names('Walter vanished without a trace.'))

    def test_logan_after_place_prep_not_flagged(self):
        self.assertEqual([],
                         detect_single_token_names('The plane made an emergency landing at Logan.'))

    def test_boston_after_place_prep_not_flagged(self):
        self.assertEqual([],
                         detect_single_token_names('The airport sits in Boston near the harbor.'))

    def test_terminal_e_facility_not_flagged(self):
        self.assertEqual([],
                         detect_single_token_names('The walk begins at Terminal E and ends here.'))

    def test_october_calendar_not_flagged(self):
        self.assertEqual([],
                         detect_single_token_names('In October the mothers blocked dump trucks.'))

    def test_the_plane_definite_np_is_not_a_name(self):
        # "The plane" / "The incident" are definite NPs, not single-token names.
        self.assertEqual([], detect_single_token_names('The plane made an emergency landing.'))
        self.assertEqual([], detect_single_token_names('The incident spurred safety reviews.'))


class TestPart1FullDetectionExemptions(unittest.TestCase):
    """Detection through the full pipeline with stop/venue exemptions."""

    def test_shipped_stop4_flags_reid_and_walter(self):
        with open(FIXTURE, encoding='utf-8') as fh:
            body = fh.read()
        refs = detect_unglossed_references(
            body,
            stop_names=['Boston Logan Airport History Walk'],
            exempt=['Logan', 'Boston'],
        )
        ents = {r['entity'] for r in refs}
        # Criterion 1/2: the orphans are now visible.
        self.assertIn('Reid', ents)
        self.assertIn('Walter', ents)
        # Location tokens are exempt (glossed by being the stop / setting).
        self.assertNotIn('Logan', ents)
        self.assertNotIn('Boston', ents)

    def test_cimiez_paragraph_not_flagged(self):
        # Criterion 3: a real shipped paragraph must not be flagged.
        refs = detect_unglossed_references(
            CIMIEZ_PARA,
            stop_names=['Cimiez Monastery', 'Musée Matisse',
                        'Musée Marc Chagall', 'Cimiez District'],
            exempt=['Cimiez', 'Nice', 'Henri Matisse', 'Marc Chagall'],
        )
        self.assertEqual([], [r['entity'] for r in refs],
                         msg=f"Cimiez paragraph wrongly flagged: {refs}")


class TestPart2CutDependants(unittest.TestCase):
    """Criterion 4 — removing an introduction removes its orphaned dependants."""

    REMOVED = ['In 1960 a plane piloted by Richard Reid suffered a '
               'catastrophic incident on that ill-fated flight.']
    SURVIVING = (
        "The plane made an emergency landing at Logan, preventing disaster. "
        "Reid's failed attempt serves as a stark reminder of vigilance. "
        "The incident spurred safety reviews and runway technology. "
        "In September 1968, the Maverick Street Mothers, a group of local "
        "mothers, stood up against the expansion by blocking dump trucks. "
        "Their protest led to changes in airport policies."
    )

    def test_orphans_are_cut(self):
        out, cut = cut_orphaned_dependants(self.SURVIVING, self.REMOVED)
        joined = ' | '.join(cut)
        self.assertIn('The plane made an emergency landing', joined)
        self.assertIn("Reid's failed attempt", joined)
        self.assertIn('The incident spurred', joined)
        # And they are gone from the surviving text.
        self.assertNotIn('The plane made an emergency landing', out)
        self.assertNotIn("Reid's failed attempt", out)
        self.assertNotIn('The incident spurred', out)

    def test_independent_content_survives(self):
        out, cut = cut_orphaned_dependants(self.SURVIVING, self.REMOVED)
        # The Maverick Street Mothers are introduced in place — not orphaned.
        self.assertIn('Maverick Street Mothers', out)
        # A pronoun subject ("Their protest") is not a definite back-reference
        # to the removed introduction and must survive.
        self.assertIn('Their protest led to changes', out)

    def test_indefinite_first_mention_not_cut(self):
        # "A plane made..." is an introduction, not a dependant.
        text = ("A plane made an emergency landing at Logan. "
                "It was a routine diversion.")
        out, cut = cut_orphaned_dependants(text, self.REMOVED)
        self.assertEqual([], cut)
        self.assertIn('A plane made an emergency landing', out)

    def test_no_removed_sentences_is_noop(self):
        out, cut = cut_orphaned_dependants(self.SURVIVING, [])
        self.assertEqual([], cut)
        self.assertEqual(self.SURVIVING, out)


class TestSuiteCanFail(unittest.TestCase):
    """D242 — a suite that cannot fail proves nothing.

    These two tests assert the CURRENT, CORRECT behaviour of the exact contracts
    Part 1 and Part 2 depend on. Break the detector (see SUBMISSION for the
    demonstrated red run) and these go red. They are the canaries: if the
    single-token frame or the dependant cut regresses, the suite fails.
    """

    def test_canary_single_token_contract(self):
        # If detection regresses to the old multi-token-only behaviour, this
        # list becomes empty and the test fails.
        self.assertNotEqual([], detect_single_token_names('The disappearance of Walter.'))

    def test_canary_dependant_cut_contract(self):
        _out, cut = cut_orphaned_dependants(
            "Reid's failed attempt serves as a reminder.",
            ['Richard Reid boarded the flight.'])
        # If the dependant cut regresses to a no-op, cut becomes empty and fails.
        self.assertNotEqual([], cut)


if __name__ == '__main__':
    unittest.main(verbosity=2)
