"""[D557] Regression suite for the scope-rejection memory.

`known_out_of_scope.json` holds every stop that was proposed for a tour and turned
out to be outside the requested area. This suite replays them, so a rejection
reality has already made can never silently come back — the same shape as
test_d539_closure_regression.py.

Standing check 1 (D242): every test here must go RED if the production code is
broken. `test_lookup_can_fail` proves the lookup is not a rubber stamp, and
`test_guard_actually_consults_the_corpus` monkeypatches the module to prove
generate_tour_text really calls it rather than merely importing it.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scope_memory  # noqa: E402

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'known_out_of_scope.json')


class TestCorpusShape(unittest.TestCase):
    def setUp(self):
        with open(CORPUS, encoding='utf-8') as fh:
            self.doc = json.load(fh)

    def test_every_entry_has_the_required_keys(self):
        for v in self.doc['venues']:
            for key in ('name', 'scope', 'expect', 'ground_truth', 'recorded'):
                self.assertIn(key, v, f"{v.get('name')} is missing '{key}'")
            self.assertIn(v['expect'], ('outside', 'verify'),
                          f"{v['name']}: expect must be 'outside' or 'verify'")

    def test_scope_is_never_blank(self):
        # An entry keyed on the name alone would drop a venue from EVERY tour.
        # Villa Leopolda is out of scope for Cimiez and perfectly in scope for a
        # tour of the Riviera corniches.
        for v in self.doc['venues']:
            self.assertTrue(v['scope'].strip(),
                            f"{v['name']} has no scope — it would drop everywhere")


class TestReplayKnownRejections(unittest.TestCase):
    """Every recorded rejection must still be rejected."""

    def setUp(self):
        scope_memory.reset_cache()
        with open(CORPUS, encoding='utf-8') as fh:
            self.venues = json.load(fh)['venues']

    def test_outside_entries_are_dropped(self):
        for v in self.venues:
            if v['expect'] != 'outside':
                continue
            hit, reason = scope_memory.known_out_of_scope(v['name'], v['scope'])
            self.assertTrue(hit, f"{v['name']} is recorded outside '{v['scope']}' "
                                 f"but the lookup did not find it")
            self.assertIn('known_out_of_scope.json', reason)

    def test_aliases_are_dropped_too(self):
        for v in self.venues:
            if v['expect'] != 'outside':
                continue
            for alias in v.get('aliases', []):
                hit, _ = scope_memory.known_out_of_scope(alias, v['scope'])
                self.assertTrue(hit, f"alias '{alias}' of {v['name']} was not matched")

    def test_verify_entries_never_drop_a_stop(self):
        for v in self.venues:
            if v['expect'] != 'verify':
                continue
            hit, _ = scope_memory.known_out_of_scope(v['name'], v['scope'])
            self.assertFalse(hit, f"{v['name']} is only a SUSPICION and must not drop")

    def test_the_real_request_string_still_matches(self):
        """[D542] The caller passes the tour's scope string, not a bare token.

        Exact comparison is what made the closure lookup skip every entry inside a
        real tour while passing when called directly.
        """
        for asked in ("Cimiez", "Cimiez District, Nice",
                      "Cimiez District, Nice, France", "the Cimiez district"):
            hit, _ = scope_memory.known_out_of_scope("Villa Leopolda", asked)
            self.assertTrue(hit, f"scope string '{asked}' failed to match")

    def test_accents_do_not_defeat_the_lookup(self):
        # D243: exact match on French titles silently reports absence.
        hit, _ = scope_memory.known_out_of_scope("Chapelle du Rosaire", "Cimiez")
        self.assertTrue(hit)


class TestLookupCanFail(unittest.TestCase):
    """Standing check 1: a lookup that says yes to everything is not evidence."""

    def setUp(self):
        scope_memory.reset_cache()

    def test_an_in_scope_stop_is_not_dropped(self):
        for name in ("Arenes de Cimiez", "Musee Matisse", "Monastere de Cimiez",
                     "Jardin des Arenes de Cimiez"):
            hit, _ = scope_memory.known_out_of_scope(name, "Cimiez")
            self.assertFalse(hit, f"'{name}' is IN Cimiez and must not be dropped")

    def test_a_recorded_venue_is_in_scope_somewhere_else(self):
        """The pair is the key. Villa Leopolda belongs on a Villefranche tour."""
        hit, _ = scope_memory.known_out_of_scope("Villa Leopolda", "Villefranche-sur-Mer")
        self.assertFalse(hit, "the entry is keyed on the name alone — it would "
                              "drop the villa from its own town's tour")

    def test_short_names_do_not_collide(self):
        # 'Villa' must not match 'Villa Leopolda' by substring.
        hit, _ = scope_memory.known_out_of_scope("Villa", "Cimiez")
        self.assertFalse(hit, "one-word substring collision")

    def test_empty_inputs_are_safe(self):
        for name, scope in (("", "Cimiez"), ("Villa Leopolda", ""), ("", "")):
            hit, _ = scope_memory.known_out_of_scope(name, scope)
            self.assertFalse(hit)


class TestRecording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'tests', 'known_out_of_scope.json')
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, 'w', encoding='utf-8') as fh:
            json.dump({'venues': []}, fh)
        self._orig = scope_memory._candidate_paths
        scope_memory._candidate_paths = lambda: [self.path]
        scope_memory.reset_cache()

    def tearDown(self):
        scope_memory._candidate_paths = self._orig
        scope_memory.reset_cache()

    def test_a_rejection_persists_to_the_next_run(self):
        """This is the whole point of D557."""
        hit, _ = scope_memory.known_out_of_scope("Villa Leopolda", "Cimiez")
        self.assertFalse(hit, "fixture should start empty")

        written, entry = scope_memory.record_out_of_scope(
            "Villa Leopolda", "Cimiez District, Nice",
            reason="located in Villefranche-sur-Mer")
        self.assertTrue(written)
        self.assertEqual(entry['expect'], 'outside')

        # Simulate the NEXT run: fresh process, nothing in memory.
        scope_memory.reset_cache()
        hit, reason = scope_memory.known_out_of_scope("Villa Leopolda", "Cimiez District, Nice")
        self.assertTrue(hit, "the rejection did not stick — this is D556 all over again")
        self.assertIn("Villefranche", reason)

    def test_recording_the_same_pair_twice_is_a_no_op(self):
        scope_memory.record_out_of_scope("Villa Leopolda", "Cimiez", reason="x")
        written, _ = scope_memory.record_out_of_scope("Villa Leopolda", "Cimiez", reason="x")
        self.assertFalse(written, "duplicate entry appended")
        with open(self.path, encoding='utf-8') as fh:
            self.assertEqual(len(json.load(fh)['venues']), 1)

    def test_the_file_stays_valid_json_after_a_write(self):
        scope_memory.record_out_of_scope("Somewhere Else", "Cimiez", reason="x")
        with open(self.path, encoding='utf-8') as fh:
            json.load(fh)   # raises if the write corrupted it

    def test_blank_input_is_never_recorded(self):
        written, _ = scope_memory.record_out_of_scope("", "Cimiez")
        self.assertFalse(written)
        written, _ = scope_memory.record_out_of_scope("Villa Leopolda", "")
        self.assertFalse(written)


class TestGuardActuallyConsultsTheCorpus(unittest.TestCase):
    """D421: a suite that greps the source proves nothing. Call the guard.

    `_validate_stops_within_scope` is module-scope and needs no key or DB as long
    as the corpus answers first — a memory hit returns before the HTTP call. If
    the production wiring is removed, `_check_one` falls through to
    `requests.post` and this test errors or keeps the stop. Either way it is RED.
    """

    def test_a_remembered_stop_is_removed_without_an_api_call(self):
        import generate_tour_text as gtt

        poi_list = [
            {'name': 'Monastere de Cimiez', 'description': 'The monastery.'},
            {'name': 'Villa Leopolda', 'description': 'A grand villa.'},
        ]
        kept = gtt._validate_stops_within_scope(
            poi_list, 'Cimiez District, Nice',
            headers={'Authorization': 'Bearer THIS-KEY-IS-INVALID-ON-PURPOSE'})

        names = [p['name'] for p in kept]
        self.assertIn('Monastere de Cimiez', names)
        self.assertNotIn('Villa Leopolda', names,
                         "the guard did not consult scope_memory — the corpus is "
                         "loaded but nothing in production calls it")


if __name__ == '__main__':
    unittest.main(verbosity=2)
