"""
[LOCAL-522] Order and connect the stops the user chose.

Each test class maps to one acceptance criterion:

  AC1  A deliberately jumbled list comes back in a walkable order.
  AC2  Every stop has Directions naming the NEXT stop; the last one closes.
  AC3  The user can force their own order and it is honoured verbatim.
  AC4  No stop points at a stop that is not in the list.

Pure, offline, deterministic — no network, no API key.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stop_route_sequencer import sequence_stops, route_length_km


# Four stops strung along one road in Cimiez, Nice (the D559 zigzag fixture).
# In geographic order they are A - B - C - D (or its reverse).
_ROAD = {
    'A': (43.7109, 7.2784),
    'B': (43.7152, 7.2797),
    'C': (43.7190, 7.2813),
    'D': (43.7200, 7.2823),
}


def _road_pois(order):
    return [{'name': n, 'coordinates': f'{_ROAD[n][0]}, {_ROAD[n][1]}'} for n in order]


class AC1_JumbledComesBackWalkable(unittest.TestCase):
    def test_scrambled_list_is_shorter_after_sequencing(self):
        scrambled = ['D', 'A', 'C', 'B']
        before = route_length_km(_road_pois(scrambled))
        out = sequence_stops(_road_pois(scrambled), tour_category='walking')
        after = route_length_km(out)
        self.assertLess(after, before,
                        f"sequencing did not shorten the walk: {before:.3f}km -> {after:.3f}km")

    def test_result_is_the_optimal_line_either_direction(self):
        for scrambled in (['D', 'A', 'C', 'B'], ['C', 'A', 'D', 'B'],
                          ['B', 'D', 'A', 'C'], ['A', 'C', 'B', 'D']):
            out_names = [s['name'] for s in
                         sequence_stops(_road_pois(scrambled), tour_category='walking')]
            self.assertIn(out_names, (['A', 'B', 'C', 'D'], ['D', 'C', 'B', 'A']),
                          f"{scrambled} -> {out_names}: not the walkable line")

    def test_ordering_is_deterministic_regardless_of_input_order(self):
        routes = set()
        for scrambled in (['A', 'B', 'C', 'D'], ['D', 'C', 'B', 'A'],
                          ['B', 'D', 'A', 'C'], ['C', 'A', 'D', 'B']):
            out = [s['name'] for s in
                   sequence_stops(_road_pois(scrambled), tour_category='walking')]
            routes.add(tuple(min(out, out[::-1])))
        self.assertEqual(len(routes), 1, f"itinerary varied by input order: {routes}")

    def test_no_stop_is_dropped_or_duplicated(self):
        out = sequence_stops(_road_pois(['D', 'A', 'C', 'B']), tour_category='walking')
        self.assertEqual(sorted(s['name'] for s in out), ['A', 'B', 'C', 'D'])

    def test_building_tour_orders_by_venue_flow_not_geography(self):
        # Rooms given out of order; venue flow (floor, then flow_index) is the truth.
        stops = [
            {'name': 'Rooftop Terrace', 'floor': 2, 'flow_index': 0},
            {'name': 'Grand Hall',      'floor': 0, 'flow_index': 0},
            {'name': 'Portrait Gallery','floor': 1, 'flow_index': 1},
            {'name': 'Ceramics Room',   'floor': 1, 'flow_index': 0},
        ]
        out = [s['name'] for s in sequence_stops(stops, tour_category='museum')]
        self.assertEqual(out, ['Grand Hall', 'Ceramics Room',
                               'Portrait Gallery', 'Rooftop Terrace'])


class AC2_DirectionsNameNextAndLastCloses(unittest.TestCase):
    def setUp(self):
        self.out = sequence_stops(_road_pois(['D', 'A', 'C', 'B']),
                                  tour_category='walking', venue_name='Cimiez')

    def test_every_non_last_stop_names_its_actual_successor(self):
        for i in range(len(self.out) - 1):
            nxt = self.out[i + 1]['name']
            self.assertIn('directions', self.out[i])
            self.assertIn(nxt, self.out[i]['directions'],
                          f"stop {i} directions do not name successor {nxt!r}: "
                          f"{self.out[i]['directions']!r}")

    def test_last_stop_has_a_closing_and_no_directions(self):
        last = self.out[-1]
        self.assertIn('closing', last)
        self.assertNotIn('directions', last)
        self.assertTrue(last['closing'].strip())

    def test_only_the_last_stop_closes(self):
        closers = [s for s in self.out if 'closing' in s]
        self.assertEqual(len(closers), 1)
        self.assertIs(closers[0], self.out[-1])

    def test_positions_are_sequential_from_one(self):
        self.assertEqual([s['position'] for s in self.out], [1, 2, 3, 4])


class AC3_ForcedOrderHonouredVerbatim(unittest.TestCase):
    def test_forced_order_is_used_exactly(self):
        forced = ['C', 'A', 'D', 'B']
        out = [s['name'] for s in
               sequence_stops(_road_pois(['A', 'B', 'C', 'D']),
                              tour_category='walking', forced_order=forced)]
        self.assertEqual(out, forced,
                         "forced order was re-optimised instead of honoured")

    def test_forced_order_overrides_geographic_optimisation(self):
        # A->B->C->D is the short route; the user insists on the long zigzag.
        forced = ['A', 'D', 'B', 'C']
        out = [s['name'] for s in
               sequence_stops(_road_pois(['A', 'B', 'C', 'D']),
                              tour_category='walking', forced_order=forced)]
        self.assertEqual(out, forced)

    def test_forced_order_is_case_and_space_insensitive(self):
        stops = [{'name': 'Old Mill'}, {'name': 'Town Green'}, {'name': 'Stone Bridge'}]
        forced = ['stone bridge', 'OLD MILL', 'town  green']
        out = [s['name'] for s in
               sequence_stops(stops, tour_category='walking', forced_order=forced)]
        self.assertEqual(out, ['Stone Bridge', 'Old Mill', 'Town Green'])

    def test_stops_not_named_in_forced_order_are_appended_not_dropped(self):
        stops = [{'name': 'One'}, {'name': 'Two'}, {'name': 'Three'}]
        out = [s['name'] for s in
               sequence_stops(stops, tour_category='walking', forced_order=['Three'])]
        self.assertEqual(out[0], 'Three')
        self.assertEqual(sorted(out), ['One', 'Three', 'Two'])
        self.assertEqual(len(out), 3, "a forced order dropped a stop")

    def test_seams_follow_the_forced_order(self):
        forced = ['C', 'A', 'D', 'B']
        out = sequence_stops(_road_pois(['A', 'B', 'C', 'D']),
                             tour_category='walking', forced_order=forced)
        for i in range(len(out) - 1):
            self.assertIn(out[i + 1]['name'], out[i]['directions'])


class AC4_NoSeamPointsOutsideTheList(unittest.TestCase):
    def _all_names(self, out):
        return {s['name'] for s in out}

    def test_every_directions_target_is_a_stop_in_the_list(self):
        out = sequence_stops(_road_pois(['D', 'A', 'C', 'B']), tour_category='walking')
        names = self._all_names(out)
        for i in range(len(out) - 1):
            target = out[i + 1]['name']
            self.assertIn(target, names)
            self.assertIn(target, out[i]['directions'])

    def test_a_removed_stop_is_never_referenced(self):
        # Build a full tour, then imagine 'C' was cut; nothing may name it.
        full = ['A', 'B', 'C', 'D']
        kept = [p for p in _road_pois(full) if p['name'] != 'C']
        out = sequence_stops(kept, tour_category='walking')
        blob = ' '.join(s.get('directions', '') + ' ' + s.get('closing', '') for s in out)
        self.assertNotIn('C.', blob, "a seam pointed at a stop that is not in the list")
        self.assertEqual(sorted(self._all_names(out)), ['A', 'B', 'D'])

    def test_forced_order_seams_stay_inside_the_list(self):
        out = sequence_stops(_road_pois(['A', 'B', 'C', 'D']),
                             tour_category='walking', forced_order=['B', 'D', 'A', 'C'])
        names = self._all_names(out)
        for i in range(len(out) - 1):
            self.assertIn(out[i + 1]['name'], names)

    def test_single_stop_tour_has_no_dangling_directions(self):
        out = sequence_stops([{'name': 'Only Stop'}], tour_category='walking')
        self.assertEqual(len(out), 1)
        self.assertNotIn('directions', out[0])
        self.assertIn('closing', out[0])


class InputIsNeverMutated(unittest.TestCase):
    def test_caller_dicts_are_left_untouched(self):
        original = _road_pois(['D', 'A', 'C', 'B'])
        snapshot = [dict(p) for p in original]
        sequence_stops(original, tour_category='walking')
        self.assertEqual(original, snapshot,
                         "sequence_stops mutated the caller's list")


if __name__ == '__main__':
    unittest.main(verbosity=2)
