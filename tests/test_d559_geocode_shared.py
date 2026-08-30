"""[D559] The coordinate decision, now shared between Beta and Storied.

`geocode_stops.resolve_stop()` is deployed in Beta production (audioura:v33,
revision tour-modernized-00009-99b) and had NO tests. D559 refactored its body out
into `resolve_point()` so the Storied generator — which holds POI dicts, not
rendered stop text — could call the same rule instead of a second copy.

Refactoring untested production code is how behaviour changes by accident. These
tests pin the rule first, then check the two new entry points agree with it. The
geocoder is stubbed, so they are deterministic and need no network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geocode_stops as g  # noqa: E402

# Cimiez, and a point ~3.4 km away in Villefranche — the real Villa Leopolda gap.
CIMIEZ = (43.7109, 7.2784)
CIMIEZ_NEAR = (43.71095, 7.27845)      # ~7 m: inside AGREEMENT_M
VILLEFRANCHE = (43.709376, 7.320883)


def stop_text(name, address, pt):
    """The shape `correct_stops` actually receives.

    `tour_generation_modernized.py` splits on the "Stop N:" markers and passes what
    follows, so line 0 is the venue name — NOT "Stop 1: <name>". Getting this wrong
    silently changes which query `_candidates` builds.
    """
    return f"{name}\nAddress: {address}\nCoordinates: {pt[0]}, {pt[1]}\n"


class GeocodeStub:
    """Replaces `geocode` with a dict lookup, and records what was asked."""

    def __init__(self, answers):
        self.answers, self.queries = answers, []

    def __call__(self, query):
        # PREFIX match, not substring. `_candidates` asks two questions — "{name},
        # {city}" and the full address — and with substring matching the address
        # "Avenue de la Villa Leopolda, 06000 Nice" also matched the key
        # "Villa Leopolda", so both lookups returned the same point and the stub
        # manufactured the agreement the test was written to rule out.
        self.queries.append(query)
        q = (query or '').lower()
        for key, val in self.answers.items():
            if q.startswith(key.lower()):
                return val
        return None


class _StubbedCase(unittest.TestCase):
    def setUp(self):
        self._real = g.geocode
        self._enabled = g.GEOCODE_ENABLED
        g.GEOCODE_ENABLED = True

    def tearDown(self):
        g.geocode = self._real
        g.GEOCODE_ENABLED = self._enabled

    def stub(self, answers):
        g.geocode = GeocodeStub(answers)
        return g.geocode


class TestTheRule(_StubbedCase):
    """The documented rule, pinned before anything else."""

    def test_two_sources_agreeing_replace_the_model(self):
        self.stub({'Musee Matisse': CIMIEZ_NEAR, '164 Avenue': CIMIEZ_NEAR})
        pt, rec = g.resolve_point('Musee Matisse', '164 Avenue des Arenes, 06000 Nice',
                                  (43.7187, 7.2768), 'Nice, France')
        self.assertEqual(rec['confidence'], 'high')
        self.assertEqual(rec['action'], 'replaced')
        self.assertEqual(pt, CIMIEZ_NEAR)

    def test_disagreement_keeps_the_model_and_flags_low(self):
        """Beta measured the model right and the ADDRESS wrong in every large
        disagreement, so a lone dissenting lookup must not overwrite it."""
        self.stub({'Villa Leopolda': VILLEFRANCHE})
        pt, rec = g.resolve_point('Villa Leopolda', 'Avenue de la Villa Leopolda, 06000 Nice',
                                  CIMIEZ, 'Nice, France')
        self.assertIsNone(pt, "a single disagreeing lookup overwrote the model")
        self.assertEqual(rec['confidence'], 'low')
        self.assertEqual(rec['action'], 'kept')
        self.assertGreater(rec['spread_m'], 3000)

    def test_no_lookup_succeeds_is_low_not_a_crash(self):
        self.stub({})
        pt, rec = g.resolve_point('Nowhere', '', CIMIEZ, 'Nice, France')
        self.assertIsNone(pt)
        self.assertEqual(rec['confidence'], 'low')

    def test_a_match_far_from_the_tour_is_discarded(self):
        """The Central Islands case: a name that matches somewhere unrelated."""
        self.stub({'Leslie': (51.5, -0.12)})       # London, for a Toronto tour
        _, rec = g.resolve_point('Leslie Spit', '', (43.65, -79.38),
                                 'Toronto', tour_anchor=(43.65, -79.38))
        self.assertIn('rejected', rec, "a match on another continent was not discarded")

    def test_agreement_already_at_the_model_changes_nothing(self):
        self.stub({'X': CIMIEZ, '1 Main': CIMIEZ})
        pt, rec = g.resolve_point('X', '1 Main St', CIMIEZ, 'Nice')
        self.assertIsNone(pt, "returned a 'correction' to the coordinate it already had")
        self.assertEqual(rec['confidence'], 'high')

    def test_disabled_is_a_clean_no_op(self):
        g.GEOCODE_ENABLED = False
        pt, rec = g.resolve_point('X', '1 Main St', CIMIEZ, 'Nice')
        self.assertIsNone(pt)
        self.assertEqual(rec['reason'], 'geocoding disabled')


class TestResolveStopUnchanged(_StubbedCase):
    """Beta's entry point. Its behaviour must survive the extraction."""

    def test_it_rewrites_the_coordinates_line_in_place(self):
        self.stub({'Musee Matisse': CIMIEZ_NEAR, '164 Avenue': CIMIEZ_NEAR})
        text = stop_text('Musee Matisse', '164 Avenue des Arenes, 06000 Nice', (43.7187, 7.2768))
        new, rec = g.resolve_stop(text, 'Nice, France')
        self.assertEqual(rec['action'], 'replaced')
        self.assertIn(f"Coordinates: {CIMIEZ_NEAR[0]:.6f}, {CIMIEZ_NEAR[1]:.6f}", new)
        self.assertIn('Address: 164 Avenue des Arenes, 06000 Nice', new,
                      "the rewrite damaged another line")

    def test_text_is_untouched_when_nothing_corroborates(self):
        self.stub({'Villa Leopolda': VILLEFRANCHE})
        text = stop_text('Villa Leopolda', 'Avenue de la Villa Leopolda, 06000 Nice', CIMIEZ)
        new, rec = g.resolve_stop(text, 'Nice, France')
        self.assertEqual(new, text)
        self.assertEqual(rec['confidence'], 'low')

    def test_a_stop_with_no_coordinates_line_is_skipped(self):
        self.stub({})
        text = "Stop 1: X\nAddress: 1 Main St\n"
        new, rec = g.resolve_stop(text, 'Nice')
        self.assertEqual(new, text)
        self.assertEqual(rec['action'], 'skipped')
        self.assertIn('no Coordinates line', rec['reason'])


class TestResolvePoi(_StubbedCase):
    """The Storied entry point — same rule, POI-dict shape."""

    def test_it_writes_back_a_high_confidence_correction(self):
        self.stub({'Musee Matisse': CIMIEZ_NEAR, '164 Avenue': CIMIEZ_NEAR})
        poi = {'name': 'Musee Matisse', 'address': '164 Avenue des Arenes, 06000 Nice',
               'coordinates': '43.7187, 7.2768'}
        rec = g.resolve_poi(poi, 'Nice, France')
        self.assertEqual(rec['confidence'], 'high')
        self.assertEqual(poi['coordinates'], f"{CIMIEZ_NEAR[0]:.6f}, {CIMIEZ_NEAR[1]:.6f}")
        self.assertEqual(poi['_geo_confidence'], 'high')

    def test_it_marks_low_confidence_without_touching_the_coordinate(self):
        """This is the flag the scope judge reads before deciding whether the
        address may outrank what it knows."""
        self.stub({'Villa Leopolda': VILLEFRANCHE})
        poi = {'name': 'Villa Leopolda', 'address': 'Avenue de la Villa Leopolda, 06000 Nice',
               'coordinates': '43.7109, 7.2784'}
        rec = g.resolve_poi(poi, 'Nice, France')
        self.assertEqual(poi['_geo_confidence'], 'low')
        self.assertEqual(poi['coordinates'], '43.7109, 7.2784')
        self.assertGreater(rec['spread_m'], 3000)

    def test_a_poi_with_no_coordinate_is_marked_not_crashed(self):
        self.stub({})
        poi = {'name': 'New Stop', 'address': '', 'coordinates': ''}
        rec = g.resolve_poi(poi, 'Nice')
        self.assertEqual(rec['action'], 'skipped')
        self.assertEqual(poi['_geo_confidence'], 'low')

    def test_both_entry_points_reach_the_same_verdict(self):
        """The point of the extraction. If these ever diverge, there are two rules
        again and one of them is wrong."""
        for answers in ({'X': CIMIEZ_NEAR, '1 Main': CIMIEZ_NEAR},
                        {'X': VILLEFRANCHE},
                        {}):
            self.stub(answers)
            _, rec_text = g.resolve_stop(stop_text('X', '1 Main St', CIMIEZ), 'Nice')
            self.stub(answers)
            rec_poi = g.resolve_poi({'name': 'X', 'address': '1 Main St',
                                     'coordinates': '43.7109, 7.2784'}, 'Nice')
            self.assertEqual(rec_text['confidence'], rec_poi['confidence'], answers)
            self.assertEqual(rec_text['action'], rec_poi['action'], answers)


class TestCoordParsing(unittest.TestCase):
    def test_it_reads_what_the_generator_writes(self):
        self.assertEqual(g._parse_coords_pair('43.7187, 7.2768'), (43.7187, 7.2768))
        self.assertEqual(g._parse_coords_pair('  -33.85 ,  151.21 '), (-33.85, 151.21))

    def test_it_rejects_what_cannot_be_a_place(self):
        for bad in ('', None, 'unknown', '0, 0', '200, 500', 'lat, lng'):
            self.assertIsNone(g._parse_coords_pair(bad), bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
