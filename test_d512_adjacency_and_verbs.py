#!/usr/bin/env python3
"""test_d512_adjacency_and_verbs.py — the two fixes Michael approved 2026-08-23.

  [1] adjacency — the action and the stake may be in adjacent sentences
  [2] domain verbs — discovered per museum type, additive only

RED-CHECK notes on each class. No network: verb discovery is tested through
`agency_pattern_with`, which is the part that must be correct; the SERP call is
exercised separately and by the live run.
"""
import re
import unittest

import material_kind as mk
import story_opportunity_scan as sos
from domain_verbs import agency_pattern_with, _NOT_AN_ACT, _PAST_TENSE
from material_kind import classify_material, KIND_EVENTFUL, KIND_RICH, KIND_INERT


# The story that failed on 2026-08-23. Action in sentence 1, stake in sentence 2
# — which is how stories are actually written.
FREUD = [
    "In 1939, shortly before his death, Sigmund Freud published Moses and "
    "Monotheism, arguing that the biblical leader was Egyptian rather than Hebrew.",
    "Decades later, in 1974, Salvador Dalí engaged in a posthumous dialogue with "
    "Freud's ideas by creating a series of illustrations.",
    "Dalí incorporated Freud's provocative thesis into his imagery.",
]


class TestAdjacency(unittest.TestCase):
    """RED-CHECK: change `if both or adjacent_pairs:` back to `if both:` in
    `classify_material`. `test_the_freud_story_is_eventful` goes red."""

    def test_the_freud_story_is_eventful(self):
        r = classify_material(FREUD)
        self.assertEqual(r['kind'], KIND_EVENTFUL)
        self.assertGreaterEqual(r['eventful_adjacent_pairs'], 1)

    def test_same_facts_in_one_sentence_still_work(self):
        # The pre-existing rule must be untouched: a single sentence carrying
        # both is still eventful, and by the same-sentence path.
        one = ["In 1938 Dalí travelled to London to meet Freud, the only time "
               "the two men ever met."]
        r = classify_material(one)
        self.assertEqual(r['kind'], KIND_EVENTFUL)
        self.assertGreaterEqual(r['eventful_sentences'], 1)

    def test_unrelated_subjects_are_not_a_story(self):
        # THE GUARD. Without the shared-subject test, adjacency would let a
        # stake about one person license an action by another — two unrelated
        # facts wearing the shape of a story.
        #
        # RED-CHECK: delete the `_share_a_subject` call. This goes red.
        unrelated = ["Mourlot printed the lithographs in Paris.",
                     "Reverdy never saw the finished book."]
        self.assertEqual(classify_material(unrelated)['kind'], KIND_RICH)

    def test_a_pronoun_bridges_the_subject(self):
        # "Freud published it. He never saw it in print." names Freud once.
        bridged = ["Freud published the book in 1939.",
                   "He never saw it in print."]
        self.assertEqual(classify_material(bridged)['kind'], KIND_EVENTFUL)

    def test_description_is_still_inert(self):
        desc = ["The book is bound in vellum.",
                "It measures 36 by 51 centimetres."]
        self.assertEqual(classify_material(desc)['kind'], KIND_INERT)

    def test_adjacency_is_reported_separately(self):
        # A kind that came only from adjacency is a weaker signal than one
        # carried by a single sentence, and a run must be able to tell which.
        r = classify_material(FREUD)
        self.assertIn('eventful_adjacent_pairs', r)
        self.assertEqual(r['eventful_sentences'], 0,
                         'fixture assumption changed: no single sentence carries both')

    def test_only_ADJACENT_sentences_count(self):
        # Two sentences at opposite ends of a passage are not one telling.
        far = ["Freud published the book in 1939.",
               "The volume is bound in green cloth.",
               "The paper is a wove stock.",
               "Freud never saw it in print."]
        r = classify_material(far)
        self.assertEqual(r['eventful_adjacent_pairs'], 0)


class TestDomainVerbs(unittest.TestCase):
    """RED-CHECK: make `agency_pattern_with` return `_AGENCY_VERB` unchanged.
    `test_discovered_verbs_are_matched` goes red."""

    def setUp(self):
        self._orig_sos = sos._AGENCY_VERB
        self._orig_mk = mk._AGENCY_VERB

    def tearDown(self):
        sos._AGENCY_VERB = self._orig_sos
        mk._AGENCY_VERB = self._orig_mk

    def test_the_measured_gap_is_real(self):
        # If these ever match out of the box, the module has no purpose.
        for s in ("Dalí scratched the illustrations onto gold plates.",
                  "Printers pulled the images onto sheepskin."):
            self.assertFalse(mk.has_agentive_action(s), s)

    def test_discovered_verbs_are_matched(self):
        sos._AGENCY_VERB = agency_pattern_with(['scratched', 'pulled'])
        mk._AGENCY_VERB = sos._AGENCY_VERB
        self.assertTrue(mk.has_agentive_action(
            "Dalí scratched the illustrations onto gold plates."))
        self.assertTrue(mk.has_agentive_action(
            "Printers pulled the images onto sheepskin."))

    def test_widening_never_narrows(self):
        # THE SAFETY PROPERTY. Everything the original matched must still match,
        # so a bad discovery can only make the scanner generous, never blind.
        widened = agency_pattern_with(['scratched', 'pulled', 'moistened'])
        for s in ("Broder refused the edition.", "Vesuvius erupted in 79 AD.",
                  "Bulfinch designed the square.", "Mourlot printed the plates."):
            self.assertTrue(self._orig_sos.search(s), f'fixture: {s}')
            self.assertTrue(widened.search(s), f'widening lost a verb: {s}')

    def test_description_still_has_no_action_after_widening(self):
        sos._AGENCY_VERB = agency_pattern_with(['scratched', 'pulled'])
        mk._AGENCY_VERB = sos._AGENCY_VERB
        self.assertFalse(mk.has_agentive_action("The book is bound in vellum."))

    def test_garbage_verbs_cannot_break_the_pattern(self):
        # A discovery is untrusted input; it must not be able to corrupt the
        # regex. Only bare lowercase words are accepted.
        p = agency_pattern_with(['scratched', ')|(', '.*', '', 'a', 'X9!'])
        self.assertTrue(p.search("Dalí scratched the plate."))
        # Only the one clean verb survives; the injection attempts are dropped.
        for junk in (')|(', '.*', 'X9!'):
            self.assertNotIn(re.escape(junk), p.pattern)
        # NOTE: asserting `not p.search("The book is bound in vellum.")` would be
        # wrong and was, in the first version of this test — `bound` IS in the
        # original alternation. The regex matching it is correct; what rejects
        # that sentence is `has_agentive_action`'s agent check, one layer up.
        sos._AGENCY_VERB = p
        mk._AGENCY_VERB = p
        self.assertFalse(mk.has_agentive_action("The book is bound in vellum."))

    def test_empty_discovery_returns_the_original(self):
        self.assertIs(agency_pattern_with([]), sos._AGENCY_VERB)

    def test_state_words_are_excluded_from_discovery(self):
        for w in ('used', 'located', 'displayed', 'exhibited', 'signed'):
            self.assertIn(w, _NOT_AN_ACT)

    def test_past_tense_pattern_finds_making_verbs(self):
        text = "the stone was moistened and the ink transferred and rolled"
        found = {m.group(1) for m in _PAST_TENSE.finditer(text)}
        self.assertTrue({'moistened', 'transferred', 'rolled'} <= found)


if __name__ == '__main__':
    unittest.main(verbosity=2)
