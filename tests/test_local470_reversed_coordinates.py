"""[LOCAL-470 / BETA-5, wdvrdaxqte] Whole-tour reversed-coordinate repair on the
Storied path.

Beta had `fix_reversed_coordinates` (text form) inside `correct_stops`; Storied
never calls `correct_stops`. `generate_tour_text.py` resolves each POI through
`resolve_poi`, so the whole-tour reversal check is ported as
`fix_reversed_poi_list` and must run before per-POI resolution.

The failure it repairs: a Madagascar tour emitted every stop longitude-first —
"47.5224, -18.9110" for the Rova of Antananarivo, ~9,899 km out (Indian Ocean
off Somalia); swapped it is 3.9 km. Found in 2 of 16 scanned tours.

The geocoder is stubbed, so these are deterministic and need no network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geocode_stops as g  # noqa: E402

# Real anchors used by the tests.
ANTANANARIVO = (-18.8792, 47.5079)     # lat, lng — Madagascar's capital
SYDNEY = (-33.8568, 151.2153)          # negative latitude, high positive longitude
KYOTO = (35.0116, 135.7681)            # high longitude, normal-range latitude


class GeocodeStub:
    """Replaces `geocode` with a prefix-keyed dict lookup, recording queries."""

    def __init__(self, answers):
        self.answers, self.queries = answers, []

    def __call__(self, query):
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


def poi(name, address, lat, lng):
    return {'name': name, 'address': address, 'coordinates': f"{lat}, {lng}"}


class TestMadagascarIsCorrected(_StubbedCase):
    """AC1: a reversed tour is detected and corrected, with a naming log line."""

    def _reversed_madagascar(self):
        # Written longitude-first: the "lat" slot holds the longitude (47.52...)
        # and vice-versa. As written every stop is ~9,900 km from Antananarivo.
        return [
            poi('Rova of Antananarivo', 'Rova, Antananarivo, Madagascar', 47.5224, -18.9110),
            poi('Andafiavaratra Palace', 'Andafiavaratra, Antananarivo, Madagascar', 47.5300, -18.9080),
            poi('Lake Anosy', 'Anosy, Antananarivo, Madagascar', 47.5180, -18.9200),
        ]

    def test_reversed_tour_is_swapped_to_antananarivo(self):
        self.stub({'Antananarivo': ANTANANARIVO})
        pois = self._reversed_madagascar()
        rec = g.fix_reversed_poi_list(pois)
        self.assertEqual(rec['action'], 'swapped', rec)
        self.assertEqual(rec['city'], 'Antananarivo')
        # After the swap every stop must sit within a few km of the real city.
        for p in pois:
            lat, lng = g._parse_coords_pair(p['coordinates'])
            self.assertLess(g.haversine_m((lat, lng), ANTANANARIVO) / 1000.0, 20.0,
                            f"{p['name']} still far from Antananarivo after swap")

    def test_the_reason_names_the_reversal_and_the_city(self):
        self.stub({'Antananarivo': ANTANANARIVO})
        rec = g.fix_reversed_poi_list(self._reversed_madagascar())
        self.assertIn('reversed', rec['reason'].lower())
        self.assertIn('Antananarivo', rec['reason'])


class TestCorrectToursAreLeftAlone(_StubbedCase):
    """AC2: the false-positive that would destroy working tours. Correct tours,
    including tricky sign/magnitude shapes, must never be 'corrected'."""

    def test_sydney_negative_latitude_is_untouched(self):
        self.stub({'Sydney': SYDNEY})
        pois = [
            poi('Sydney Opera House', 'Bennelong Point, Sydney NSW 2000, Australia', -33.8568, 151.2153),
            poi('Sydney Harbour Bridge', 'Sydney Harbour Bridge, Sydney NSW, Australia', -33.8523, 151.2108),
            poi('The Rocks', 'The Rocks, Sydney NSW 2000, Australia', -33.8599, 151.2090),
        ]
        before = [p['coordinates'] for p in pois]
        rec = g.fix_reversed_poi_list(pois)
        self.assertNotEqual(rec['action'], 'swapped', rec)
        self.assertEqual([p['coordinates'] for p in pois], before,
                         "a correct Sydney tour was mangled")

    def test_kyoto_high_longitude_is_untouched(self):
        self.stub({'Kyoto': KYOTO})
        pois = [
            poi('Kinkaku-ji', '1 Kinkakujicho, Kita Ward, Kyoto, Japan', 35.0394, 135.7292),
            poi('Fushimi Inari', '68 Fukakusa, Fushimi Ward, Kyoto, Japan', 34.9671, 135.7727),
            poi('Kiyomizu-dera', '1-294 Kiyomizu, Higashiyama Ward, Kyoto, Japan', 34.9949, 135.7850),
        ]
        before = [p['coordinates'] for p in pois]
        rec = g.fix_reversed_poi_list(pois)
        self.assertNotEqual(rec['action'], 'swapped', rec)
        self.assertEqual([p['coordinates'] for p in pois], before,
                         "a correct Kyoto tour was mangled")


class TestImpossibleLatitude(_StubbedCase):
    """AC3: latitude outside +/-90 is rejected/repaired outright."""

    def test_impossible_latitude_with_no_city_is_swapped(self):
        # No geocodable city, but lat 151.21 is impossible: must still be fixed.
        self.stub({})
        pois = [poi('Somewhere', 'no city here', 151.2153, -33.8568)]
        rec = g.fix_reversed_poi_list(pois)
        self.assertEqual(rec['action'], 'swapped', rec)
        self.assertEqual(rec.get('impossible_latitude'), 1)
        self.assertEqual(pois[0]['coordinates'], '-33.856800, 151.215300')

    def test_impossible_latitude_is_counted_even_with_a_city(self):
        self.stub({'Sydney': SYDNEY})
        pois = [
            poi('A', 'A, Sydney, Australia', 151.2153, -33.8568),   # reversed & impossible lat
            poi('B', 'B, Sydney, Australia', 151.2090, -33.8599),
            poi('C', 'C, Sydney, Australia', 151.2108, -33.8523),
        ]
        rec = g.fix_reversed_poi_list(pois)
        self.assertEqual(rec['action'], 'swapped', rec)
        self.assertEqual(rec.get('impossible_latitude'), 3)


class TestBreakTheFix(_StubbedCase):
    """AC5: disable detection and confirm the Madagascar list stays reversed —
    proof the test is actually exercising the fix, not passing vacuously."""

    def test_with_factor_impossibly_high_nothing_is_swapped(self):
        # REVERSAL_FACTOR is the knob. Setting it absurdly high disables the
        # majority-vote branch; the reversed tour must then come out unchanged.
        self.stub({'Antananarivo': ANTANANARIVO})
        pois = [
            poi('Rova of Antananarivo', 'Rova, Antananarivo, Madagascar', 47.5224, -18.9110),
            poi('Andafiavaratra Palace', 'Andafiavaratra, Antananarivo, Madagascar', 47.5300, -18.9080),
            poi('Lake Anosy', 'Anosy, Antananarivo, Madagascar', 47.5180, -18.9200),
        ]
        before = [p['coordinates'] for p in pois]
        saved = g.REVERSAL_FACTOR
        try:
            g.REVERSAL_FACTOR = 1e9
            rec = g.fix_reversed_poi_list(pois)
        finally:
            g.REVERSAL_FACTOR = saved
        self.assertNotEqual(rec['action'], 'swapped',
                            "detection still fired with the rule disabled")
        self.assertEqual([p['coordinates'] for p in pois], before,
                         "the reversed tour was 'corrected' with detection disabled")


class TestEdgeCases(_StubbedCase):
    def test_empty_list_is_a_clean_no_op(self):
        self.stub({})
        self.assertEqual(g.fix_reversed_poi_list([])['action'], 'none')

    def test_no_coordinates_is_a_clean_no_op(self):
        self.stub({'Antananarivo': ANTANANARIVO})
        pois = [{'name': 'X', 'address': 'Antananarivo, Madagascar', 'coordinates': ''}]
        self.assertEqual(g.fix_reversed_poi_list(pois)['action'], 'none')

    def test_city_that_will_not_geocode_is_left_alone(self):
        self.stub({})   # nothing resolves
        pois = [poi('Rova', 'Rova, Antananarivo, Madagascar', 47.5224, -18.9110)]
        before = pois[0]['coordinates']
        rec = g.fix_reversed_poi_list(pois)
        self.assertNotEqual(rec['action'], 'swapped')
        self.assertEqual(pois[0]['coordinates'], before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
