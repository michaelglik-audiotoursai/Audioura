"""[D558] The replenishment loop: propose -> validate -> substitute -> re-order.

Michael, 2026-08-30: "make sure that the stops we obtain by replenishment are
validated the same way as the original and then substituted if invalid — seems
like a loop to me. After we got all the stories we managed to obtain, then we
need to make sure that the path from stop to stop makes sense."

D556 replenished once, appended to the end, and left PHASE 5.6 to judge the result
thousands of lines later — too late to replace anything. So a replacement that was
itself out of area put the tour back to short, which is the 6-asked-4-delivered bug
one layer down.

These tests exercise the two pieces that can be tested without a key, a DB or a
network: the scope resolver both call sites now share, and the candidate-vetting
mode of `_validate_stops_within_scope`. The end-to-end loop needs a live run and is
proved in DECISIONS, not here — but if either piece below regresses, the loop is
broken and this suite says so.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402
import scope_memory  # noqa: E402

BAD_KEY = {'Authorization': 'Bearer INVALID-ON-PURPOSE'}


class TestSharedScopeResolver(unittest.TestCase):
    """Both call sites must derive the scope identically — that is what "the same
    way as the original" means. A second copy is how these two drift apart."""

    def test_district_scope_is_used(self):
        intent = {'geographic_scope': 'Cimiez District, Nice',
                  'scope_precision': 'DISTRICT', 'location': 'Nice, France'}
        self.assertEqual(
            gtt._resolve_scope_for_check(intent, 'Nice, France', 'walking', None),
            'Cimiez District, Nice')

    def test_a_loose_scope_is_refused(self):
        # CITY/REGION precision is too wide for a stop-by-stop containment check.
        intent = {'geographic_scope': 'France', 'scope_precision': 'COUNTRY',
                  'location': 'France'}
        self.assertEqual(
            gtt._resolve_scope_for_check(intent, 'France', 'walking', None), '')

    def test_museum_tours_keep_their_own_guard(self):
        """Michael: 'we did a good job with museums and I do not want to damage it.'"""
        intent = {'geographic_scope': 'Palais Lascaris',
                  'scope_precision': 'BUILDING', 'location': 'Nice'}
        self.assertEqual(
            gtt._resolve_scope_for_check(intent, 'Nice', 'museum', 'Palais Lascaris'),
            '', "a museum tour must not run the generic containment check")

    def test_no_intent_is_safe(self):
        self.assertEqual(gtt._resolve_scope_for_check(None, 'Nice', 'walking', None), '')


class TestCandidateVetting(unittest.TestCase):
    """`protect_first=False` is what makes the loop able to reject.

    The keep-stop-0 rule exists so a whole tour never empties. Applied to a batch
    of replenishment candidates it would wave through whatever name the proposer
    happened to return first — including the out-of-area one the loop exists to
    catch.
    """

    def setUp(self):
        scope_memory.reset_cache()

    def test_a_candidate_batch_can_be_rejected_entirely(self):
        cands = [{'name': 'Villa Leopolda', 'description': 'A grand villa.'},
                 {'name': 'Chapelle du Rosaire', 'description': 'Matisse chapel.'}]
        kept = gtt._validate_stops_within_scope(cands, 'Cimiez District, Nice',
                                                headers=BAD_KEY, protect_first=False)
        self.assertEqual(kept, [], "a batch of known out-of-area candidates was "
                                   "not fully rejected — protect_first is leaking")

    def test_the_tour_path_still_protects_stop_zero(self):
        """Same input, default mode: the anchor survives. Graceful degradation."""
        cands = [{'name': 'Villa Leopolda', 'description': 'A grand villa.'},
                 {'name': 'Chapelle du Rosaire', 'description': 'Matisse chapel.'}]
        kept = gtt._validate_stops_within_scope(cands, 'Cimiez District, Nice',
                                                headers=BAD_KEY)
        self.assertEqual([p['name'] for p in kept], ['Villa Leopolda'])

    def test_an_in_scope_candidate_survives(self):
        """Standing check: a vetter that rejects everything is not a vetter.

        No API key here, so the LLM branch errors and keeps the stop — which is
        the documented fail-open behaviour ('API error - keeping'). The point is
        that nothing in the memory path removes a stop it has no record of.
        """
        cands = [{'name': 'Arenes de Cimiez', 'description': 'Roman arena.'}]
        kept = gtt._validate_stops_within_scope(cands, 'Cimiez District, Nice',
                                                headers=BAD_KEY, protect_first=False)
        self.assertEqual([p['name'] for p in kept], ['Arenes de Cimiez'])


class TestTheLoopItself(unittest.TestCase):
    """The real `replenish_to_count`, not its ingredients.

    The first version of this suite tested `_validate_stops_within_scope` directly
    and stayed GREEN when `protect_first=False` was reverted at the production call
    site — D418/D421's defect, in a suite written the same day as a decision about
    it. These tests call the function production calls, so a regression in the loop
    shows up here.
    """

    def setUp(self):
        scope_memory.reset_cache()

    @staticmethod
    def _poi(name):
        return {'name': name, 'description': ''}

    def test_a_rejected_candidate_is_replaced_not_just_dropped(self):
        """The whole ask. Round 1 proposes an out-of-area stop; the tour must still
        come back at the requested count, not one short."""
        rounds_seen = []

        def propose(need, seen):
            rounds_seen.append(need)
            if len(rounds_seen) == 1:
                return [{'name': 'Villa Leopolda', 'why': 'famous villa'}]
            return [{'name': 'Arenes de Cimiez', 'why': 'roman arena'}]

        poi_list = [self._poi('Matisse Museum'), self._poi('Cimiez Monastery')]
        added, rejected, rounds = gtt.replenish_to_count(
            poi_list, want=3, scope='Cimiez District, Nice', headers=BAD_KEY,
            propose=propose, make_poi=self._poi)

        names = [p['name'] for p in poi_list]
        self.assertEqual(len(poi_list), 3, f"tour came back short: {names}")
        self.assertNotIn('Villa Leopolda', names, "the out-of-area candidate was kept")
        self.assertIn('Arenes de Cimiez', names, "the loop did not go round again")
        self.assertEqual((added, rejected), (1, 1))
        self.assertGreaterEqual(rounds, 2, "one-shot behaviour — this is D556 again")

    def test_a_rejected_candidate_is_never_re_proposed(self):
        """Without this the loop burns its rounds re-offering the same bad stop."""
        offered = []

        def propose(need, seen):
            offered.append(list(seen))
            return [{'name': 'Villa Leopolda', 'why': 'x'}]

        poi_list = [self._poi('Matisse Museum')]
        gtt.replenish_to_count(poi_list, want=2, scope='Cimiez', headers=BAD_KEY,
                               propose=propose, make_poi=self._poi)
        self.assertGreaterEqual(len(offered), 2)
        self.assertIn('villa leopolda', offered[1],
                      "the rejected name was not passed back as already-seen")

    def test_it_stops_instead_of_looping_forever(self):
        def propose(need, seen):
            return [{'name': 'Villa Leopolda', 'why': 'x'}]

        poi_list = [self._poi('Matisse Museum')]
        _, _, rounds = gtt.replenish_to_count(
            poi_list, want=6, scope='Cimiez', headers=BAD_KEY,
            propose=propose, make_poi=self._poi, max_rounds=3)
        self.assertEqual(rounds, 3)
        self.assertEqual(len(poi_list), 1, "an unfillable request must not pad the tour")

    def test_it_stops_when_the_proposer_is_empty(self):
        calls = []

        def propose(need, seen):
            calls.append(need)
            return []

        poi_list = [self._poi('Matisse Museum')]
        gtt.replenish_to_count(poi_list, want=4, scope='Cimiez', headers=BAD_KEY,
                               propose=propose, make_poi=self._poi)
        self.assertEqual(len(calls), 1, "kept asking a proposer that returned nothing")

    def test_it_never_overshoots_the_requested_count(self):
        def propose(need, seen):
            return [{'name': f'Place {i}', 'why': 'x'} for i in range(10)]

        poi_list = [self._poi('Matisse Museum')]
        gtt.replenish_to_count(poi_list, want=3, scope='', headers=BAD_KEY,
                               propose=propose, make_poi=self._poi)
        self.assertEqual(len(poi_list), 3)

    def test_no_scope_means_no_vetting_not_a_crash(self):
        """A tour whose scope is too wide to check still gets its stops."""
        def propose(need, seen):
            return [{'name': 'Villa Leopolda', 'why': 'x'}]

        poi_list = [self._poi('Matisse Museum')]
        added, rejected, _ = gtt.replenish_to_count(
            poi_list, want=2, scope='', headers=BAD_KEY,
            propose=propose, make_poi=self._poi)
        self.assertEqual((added, rejected), (1, 0))

    def test_on_add_fires_only_for_accepted_stops(self):
        seen_adds = []

        def propose(need, seen):
            if not seen_adds:
                return [{'name': 'Villa Leopolda', 'why': 'bad'},
                        {'name': 'Arenes de Cimiez', 'why': 'good'}]
            return []

        poi_list = [self._poi('Matisse Museum')]
        gtt.replenish_to_count(poi_list, want=3, scope='Cimiez District, Nice',
                               headers=BAD_KEY, propose=propose, make_poi=self._poi,
                               on_add=lambda p: seen_adds.append(p['name']))
        self.assertEqual(seen_adds, ['Arenes de Cimiez'],
                         "rationale was attached to a stop that was rejected")


class TestRouteOrderingIsAvailableAfterReplenishment(unittest.TestCase):
    """The zigzag fix depends on _compute_route_order actually reordering a list
    whose stops carry coordinates. If it silently no-ops, the D558 call after
    replenishment buys nothing."""

    @staticmethod
    def _path_km(names, by_name):
        import math
        total = 0.0
        for a, b in zip(names, names[1:]):
            (la, ga), (lb, gb) = by_name[a], by_name[b]
            total += math.hypot((lb - la) * 111.0, (gb - ga) * 111.0 * math.cos(math.radians(la)))
        return total

    def test_a_scrambled_route_comes_back_shorter(self):
        """The property that matters to the listener: less walking than the order
        replenishment left behind. NOT that the path is optimal — it is not, see
        test_route_ordering_is_not_optimal below."""
        by_name = {'A': (43.7109, 7.2784), 'B': (43.7152, 7.2797),
                   'C': (43.7190, 7.2813), 'D': (43.7200, 7.2823)}
        scrambled = ['D', 'A', 'C', 'B']
        pois = [{'name': n, 'coordinates': f'{by_name[n][0]}, {by_name[n][1]}'}
                for n in scrambled]
        out = [p['name'] for p in gtt._compute_route_order(pois)]
        self.assertLess(self._path_km(out, by_name), self._path_km(scrambled, by_name),
                        f"reordering did not shorten the walk: {scrambled} -> {out}")

    def test_route_ordering_is_not_optimal(self):
        """[D558] On record, not a passing grade.

        Four stops strung along one road, and the route is A-last: B->C->D->A, which
        climbs the hill and then walks all the way back down. `_compute_route_order`
        starts from the stop nearest the CENTROID and runs nearest-neighbour; 2-opt
        cannot repair a bad start on an open path, so a collinear route reliably
        strands one endpoint.

        This is LOCAL-7 behaviour, older than D558 and not introduced by it, but it
        is squarely on what Michael asked for ("so zigzags would not happen"). When
        it is fixed, this test fails and should be deleted.
        """
        by_name = {'A': (43.7109, 7.2784), 'B': (43.7152, 7.2797),
                   'C': (43.7190, 7.2813), 'D': (43.7200, 7.2823)}
        pois = [{'name': n, 'coordinates': f'{by_name[n][0]}, {by_name[n][1]}'}
                for n in ['D', 'A', 'C', 'B']]
        out = [p['name'] for p in gtt._compute_route_order(pois)]
        optimal = self._path_km(['A', 'B', 'C', 'D'], by_name)
        self.assertGreater(self._path_km(out, by_name), optimal * 1.2,
                           "route ordering got better than its documented behaviour "
                           "— good news; delete this test and update D558")

    def test_stops_without_coordinates_do_not_crash_it(self):
        pois = [
            {'name': 'A', 'coordinates': '43.7109, 7.2784'},
            {'name': 'new', 'coordinates': ''},          # a replenished stop
            {'name': 'C', 'coordinates': '43.7190, 7.2813'},
            {'name': 'B', 'coordinates': '43.7152, 7.2797'},
        ]
        out = [p['name'] for p in gtt._compute_route_order(pois)]
        self.assertEqual(sorted(out), ['A', 'B', 'C', 'new'],
                         "route ordering lost or duplicated a stop")


if __name__ == '__main__':
    unittest.main(verbosity=2)
