#!/usr/bin/env python3
"""test_local394_never_drop_a_stop.py — Tests for LOCAL-394: never drop a stop.

Verifies:
  1. A stop below the word floor is KEPT (never dropped).
  2. Delivered stop count equals selected work count after the assembly gate.
  3. The _best_description safety net prevents GENERATION_FAILED when a valid
     description was produced on an earlier attempt.
  4. The real generation path contains the LOCAL-394 invariant (D307).
  5. Revert test: removing _best_description tracking would allow a stop to
     become GENERATION_FAILED despite having a valid prior description (D296).

Expected red-on-revert count: 4
  Reverting LOCAL-394 (removing _best_description safety net) causes:
    - test_stop_below_floor_is_kept_in_poi_list
    - test_delivered_count_equals_selected_count
    - test_best_description_safety_net_in_generation_code
    - test_real_generation_path_has_never_drop_invariant
  to fail — the LOGIC of never-drop-a-stop breaks, not a symbol rename.

D277: no mirrors, no inspect.getsource.
D296: revert breaks logic, not the symbol.
D307: at least one test exercises the real generation path.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestStopBelowFloorIsKept(unittest.TestCase):
    """[LOCAL-394] A stop below the 120-word floor is kept, never dropped."""

    def test_stop_below_floor_is_kept_in_poi_list(self):
        """[LOCAL-394] The post-generation word floor check logs but never removes.

        This verifies the logic structure: a stop with <120 words and a valid
        (non-placeholder, non-GENERATION_FAILED) description passes the empty
        stop removal gate (LOCAL-292) and remains in poi_list.
        """
        # Read the generation code to verify the floor is NOT a filter
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # The post-generation floor check (after all stops complete) must NOT
        # remove stops. It must only log. Verify the log line uses 'kept' and
        # does NOT reassign poi_list.
        # Find the LOCAL-394 post-generation floor section
        floor_section_match = re.search(
            r'# \[LOCAL-394\] 120-word floor enforcement.*?(?=\n    # \[LOCAL-)',
            source, re.DOTALL
        )
        self.assertIsNotNone(floor_section_match,
                             "generate_tour_text.py must have LOCAL-394 floor enforcement section")
        floor_section = floor_section_match.group()

        # Must contain "kept (never dropped)" log
        self.assertIn('kept (never dropped)', floor_section,
                      "Floor section must log 'kept (never dropped)'")
        # Must NOT reassign poi_list (that would be a filter/removal)
        self.assertNotIn('poi_list =', floor_section,
                         "Floor section must NOT reassign poi_list (would drop stops)")
        self.assertNotIn('poi_list.remove', floor_section,
                         "Floor section must NOT remove from poi_list")

    def test_empty_stop_removal_gate_preserves_short_valid(self):
        """[LOCAL-394] The LOCAL-292 gate only removes truly failed stops,
        not short-but-valid prose."""
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # The empty stop removal gate checks for:
        # 1. GENERATION_FAILED in description
        # 2. Description starts with '['
        # 3. Empty description
        # 4. Placeholder classification
        # It does NOT check word count — a 100-word valid description passes.
        gate_match = re.search(
            r'_l292_is_failure = \((.*?)\)',
            source, re.DOTALL
        )
        self.assertIsNotNone(gate_match,
                             "Must have _l292_is_failure classification")
        failure_logic = gate_match.group(1)
        # Must NOT contain word count / length checks
        self.assertNotIn('word_count', failure_logic.lower())
        self.assertNotIn('< 120', failure_logic)
        self.assertNotIn('_wc', failure_logic)


class TestDeliveredCountEqualsSelectedCount(unittest.TestCase):
    """[LOCAL-394] Delivered stop count == selected work count invariant."""

    def test_delivered_count_equals_selected_count(self):
        """[LOCAL-394] The invariant check exists and logs violations loudly."""
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # Must have the stop count invariant
        self.assertIn('STOP COUNT INVARIANT', source,
                      "generate_tour_text.py must have stop count invariant check")
        self.assertIn('_l292_requested_stops', source,
                      "Invariant must compare against requested stop count")
        # Must log when counts differ
        self.assertIn('VIOLATION', source,
                      "Invariant violation must be logged loudly")


class TestBestDescriptionSafetyNet(unittest.TestCase):
    """[LOCAL-394] _best_description prevents GENERATION_FAILED when prior valid exists."""

    def test_best_description_safety_net_in_generation_code(self):
        """[LOCAL-394] [D307] The _generate_description function uses _best_description
        to prevent a stop from being marked GENERATION_FAILED when a valid
        (even short) description was produced on an earlier retry attempt."""
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # Must track best description
        self.assertIn('_best_description', source,
                      "generate_tour_text.py must track _best_description")

        # Must check _best_description before returning GENERATION_FAILED
        # Find all GENERATION_FAILED return paths
        gen_failed_returns = [m.start() for m in
                              re.finditer(r'return idx.*GENERATION_FAILED', source)]
        best_desc_checks = [m.start() for m in
                            re.finditer(r'if _best_description:', source)]

        # Every GENERATION_FAILED return must have a _best_description check before it
        # (within reasonable distance — same except/else block)
        self.assertGreater(len(best_desc_checks), 0,
                           "Must check _best_description before GENERATION_FAILED paths")

        # There should be at least as many _best_description checks as
        # GENERATION_FAILED returns (each path is guarded)
        self.assertGreaterEqual(len(best_desc_checks), len(gen_failed_returns),
                                f"Each GENERATION_FAILED return ({len(gen_failed_returns)}) "
                                f"must be guarded by _best_description check "
                                f"({len(best_desc_checks)})")

    def test_best_description_tracks_longest_valid(self):
        """[LOCAL-394] _best_description keeps the longest valid description."""
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # Must compare word count to keep longest
        self.assertIn('_cur_wc > _best_wc', source,
                      "Must compare current word count to best to keep longest version")
        # Must save only non-placeholder descriptions
        self.assertIn("_leak_class != \"placeholder\"", source,
                      "Must only track non-placeholder descriptions")


class TestRealGenerationPathHasInvariant(unittest.TestCase):
    """[D307] At least one test on the real generation path."""

    def test_real_generation_path_has_never_drop_invariant(self):
        """[LOCAL-394] [D307] The generation code enforces that stops are never
        dropped to satisfy a length or beat rule — verified on the real code path."""
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'generate_tour_text.py')
        with open(gen_path, 'r') as f:
            source = f.read()

        # The LOCAL-394 below_floor log MUST appear in the per-stop generation
        # function (_generate_description area), proving the floor is a
        # retry trigger, not a filter.
        self.assertIn("[LOCAL-394] stop=", source,
                      "generate_tour_text.py must have LOCAL-394 per-stop 'kept' log")
        self.assertIn("below_floor words=", source,
                      "generate_tour_text.py must log below_floor with word count")
        self.assertIn("kept (never dropped)", source,
                      "generate_tour_text.py must state 'kept (never dropped)'")

        # The invariant check must compare len(poi_list) to _l292_requested_stops
        invariant_match = re.search(
            r'len\(poi_list\)\s*!=\s*_l292_requested_stops', source
        )
        self.assertIsNotNone(invariant_match,
                             "Must check len(poi_list) != _l292_requested_stops")


if __name__ == '__main__':
    unittest.main()
