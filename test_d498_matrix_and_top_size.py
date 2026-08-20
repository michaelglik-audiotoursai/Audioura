#!/usr/bin/env python3
"""test_d498_matrix_and_top_size.py — the last two amber rows of the 7-step matrix.

  [1] step 3a — one slot vocabulary, shared by producer and consumer
  [2] step 7c — the most valuable stop's larger allowance, which was unreachable
  [3] the trigger counter that reported a trigger which fired as zero

RED-CHECK notes are on each class. Every section was run against the pre-D498
tree first; a test that cannot fail is not evidence (D242).
"""
import ast
import os
import re
import unittest

import story_pass


HERE = os.path.dirname(os.path.abspath(__file__))
GTT = os.path.join(HERE, 'generate_tour_text.py')


def gtt_source():
    with open(GTT) as fh:
        return fh.read()


# ─── [1] step 3a ─────────────────────────────────────────────────────────────
class TestMatrixOneVocabulary(unittest.TestCase):
    """RED-CHECK: put a literal slot list back into `build_story_prompt` and drop
    a key from `MATRIX_SLOTS`. `test_prompt_reads_only_declared_slots` goes red."""

    def test_prompt_reads_only_declared_slots(self):
        # The prompt builder must read its keys from MATRIX_SLOTS, not from a
        # literal list. Proven by rendering with every declared slot filled and
        # checking each label appears — a slot dropped from the constant but
        # still hardcoded in the body would not be exercised by the constant.
        matrix = {k: f'VALUE_{k}' for k in story_pass.MATRIX_KEYS}
        prompt = story_pass.build_story_prompt(matrix, ['some material'])
        for label, key in story_pass.MATRIX_SLOTS:
            self.assertIn(f'{label}: VALUE_{key}', prompt, f'slot {key} not rendered')

    def test_production_fills_every_slot_the_prompt_reads(self):
        # The defect this closes: production built the dict inline from a
        # hand-copied list. A renamed key would have emptied a slot silently,
        # because `build_story_prompt` falls back to '' on a missing key.
        src = gtt_source()
        self.assertIn('_sp_matrix = {k: _sp_sources[k] for k in MATRIX_KEYS}', src,
                      'production must build the matrix FROM the shared vocabulary')
        m = re.search(r'_sp_sources = \{(.*?)\n                    \}', src, re.S)
        self.assertIsNotNone(m, 'could not find _sp_sources literal')
        supplied = set(re.findall(r"'([a-z_]+)':", m.group(1)))
        missing = set(story_pass.MATRIX_KEYS) - supplied
        self.assertEqual(missing, set(),
                         f'production does not supply slots the prompt reads: {missing}')

    def test_venue_slot_name_agrees_end_to_end(self):
        # `interrogation_matrix.SLOTS` calls this slot `venue`; the story pass
        # calls it `venue_name`. They are different modules answering different
        # questions from different inputs, and D498 deliberately did NOT unify
        # them. What must hold is that the PRODUCTION producer and consumer agree.
        self.assertIn('venue_name', story_pass.MATRIX_KEYS)
        self.assertIn("'venue_name': _museum_venue_name", gtt_source())


# ─── [2] step 7c ─────────────────────────────────────────────────────────────
class TestTopValueAllowance(unittest.TestCase):
    """RED-CHECK: delete the `poi_list[_top_value_idx]['_is_top_value_stop'] = True`
    assignment. `test_flag_is_written_somewhere` goes red — and that is the exact
    assertion whose absence let `MAX_SENTENCES_TOP` sit unreachable while the
    record credited step 7c as landed."""

    def test_flag_is_written_somewhere(self):
        src = gtt_source()
        writes = re.findall(r"\['_is_top_value_stop'\]\s*=", src)
        self.assertGreaterEqual(len(writes), 1,
                                '_is_top_value_stop is read but never written — '
                                'MAX_SENTENCES_TOP is unreachable again')

    def test_flag_is_still_read_by_the_story_pass(self):
        # Guards the other half: a write with no reader is equally dead.
        self.assertIn("poi.get('_is_top_value_stop')", gtt_source())

    def test_the_two_budgets_differ(self):
        self.assertGreater(story_pass.MAX_SENTENCES_TOP, story_pass.MAX_SENTENCES)

    def test_flag_is_set_after_the_index_exists(self):
        # The ordering problem IS the fix. If the assignment ever moves above
        # `apply_story_index`, the flag is set from an index that has not been
        # computed and the larger allowance goes to an arbitrary stop.
        src = gtt_source()
        idx_call = src.index('apply_story_index(poi_list, corpus=build_index_corpus(')
        flag_set = src.index("['_is_top_value_stop'] = True")
        self.assertLess(idx_call, flag_set,
                        'the top-value flag must be set AFTER the index is computed')

    def test_acceptance_is_the_index_not_length(self):
        # "It got longer" is the acceptance bug LOCAL-487 removed from the
        # storyless trigger. The 7c retry is allowed to add length by design, so
        # accepting on length would accept every time.
        src = gtt_source()
        self.assertIn('[D498] step 7c judged on the index, not on', src)
        self.assertIn('_accept = (isinstance(_after_ix, (int, float))', src)

    def test_unmeasurable_retry_is_rejected_not_accepted(self):
        # If the index cannot be computed, the longer draft must be dropped.
        # Accepting it unmeasured is how an unproven change ships as an
        # improvement.
        src = gtt_source()
        m = re.search(r"\[D498\] index unavailable.*?_accept = (\w+)", src, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'False')

    def test_it_can_be_switched_off(self):
        self.assertIn("DISABLE_STORY_TOP_SIZE", gtt_source())

    def test_the_budget_is_measured_against_the_story_not_the_description(self):
        """The live run caught what these tests could not.

        Stop 2's story pass wrote 5 sentences — at the cap, so the larger
        allowance was exactly the case 7c exists for — while its assembled
        description was 9, because the description also carries orientation,
        directions and transitions. Measuring the description made `_top_value`
        false for every stop, leaving 7c dead in a new way while the log
        cheerfully announced the allowance had been granted.

        RED-CHECK: change `_sp_r.get('story')` back to `_now` in the trigger.
        This goes red.
        """
        src = gtt_source()
        m = re.search(r"_top_value = bool\(_sp_r\) and 0 < _D498_sent\(\s*"
                      r"_sp_r\.get\('story'\)", src)
        self.assertIsNotNone(
            m, 'the 7c trigger must measure the story-pass output, not the '
               'assembled description')
        self.assertNotIn("_D498_sent(_now", src)

    def test_no_story_pass_result_means_do_not_spend(self):
        # An absent story pass is "cannot tell", and cannot-tell must not buy a
        # generation.
        self.assertIn('_top_value = bool(_sp_r) and', gtt_source())


# ─── [3] the trigger counter ─────────────────────────────────────────────────
class TestTriggerCounting(unittest.TestCase):
    """RED-CHECK: restore the ternary
    `_retry_stats['trigger_floor' if _hollowed else 'trigger_no_story'] += 1`.
    `test_overlapping_triggers_counted_separately` goes red.

    The 08-20 run detected 2 storyless stops and the summary printed
    '0 storyless', because both were also hollowed and a ternary can credit only
    one. A reader would have concluded step 7a was dead."""

    def test_overlapping_triggers_counted_separately(self):
        src = gtt_source()
        self.assertNotIn("_retry_stats['trigger_floor' if _hollowed else", src,
                         'the ternary can only credit one of two overlapping triggers')
        self.assertIn("if _hollowed:\n                _retry_stats['trigger_floor'] += 1", src)
        self.assertIn("if _storyless:\n                _retry_stats['trigger_no_story'] += 1", src)

    def test_summary_says_the_counts_overlap(self):
        # Counts that overlap and a total that does not sum is exactly the shape
        # that gets misread later, so the log has to say so itself.
        self.assertIn('Triggers overlap and are counted', gtt_source())


class TestStillCompiles(unittest.TestCase):
    def test_generate_tour_text_parses(self):
        ast.parse(gtt_source())


if __name__ == '__main__':
    unittest.main(verbosity=2)
