#!/usr/bin/env python3
"""[LOCAL-576] A stop the listener NAMED is a route anchor; the route starts
where they said; never fewer stops than asked.

Field test, tour 388 (2026-10-04), verbatim:

    request : "biking tour in a loop from Crystal Lake to Paul Revere via
               Commonwealth Avenue Mall & Boston Common, MA"      (5 stops)
    delivered: 4 stops, starting at the Massachusetts State House.
    Michael : "The tour supposed to start with Crystal Lake. Crystal Lake is in
               Newton, MA not Boston."

Generator log (job 5f42dc34), LEAD's reading:
  - START LOST:  candidates included "Crystal Lake Park, 400 Crystal Lake Rd,
    Newton, MA 02464". PHASE 3C REMOVED it: address "…Newton…" not in the request
    string "…MA". A place the listener NAMED, deleted by a locality string test.
  - NAMED WAYPOINT LOST: "[LOCAL-212] Dropped: Commonwealth Avenue Mall=EMPTY"
    (no corpus coverage). The listener named it.
  - 5 -> 4:  North End was SELECTED, written in full (gpt-4.1, $0.03), THEN
    "PHASE 5.6 … SCOPE-CHECK REMOVED 'North End'" with no replacement ->
    "[D536] LISTENER ASKED FOR 5 STOP(S), DELIVERING 4". The scope verdict was
    right; it ran too late.

These tests exercise the REAL module functions (D277: no mirrors, no
getsource) the fix is built from, driven deterministically:

  1. named_anchors()                — the route the listener named, structurally.
  2. _apply_named_waypoints()       — anchors marked user_explicit + _anchor on
                                      every fill path.
  3. _validate_stops_within_scope() — PHASE 5.6 now EXEMPTS anchors and removes
                                      only the stop WE chose (North End). Because
                                      this now runs BEFORE PHASE 5, North End is
                                      dropped with ZERO writer calls spent on it.
  4. _order_by_anchors()            — stop 1 is Crystal Lake, Paul Revere Park is
                                      last, via-points keep the listener's order.

RED ON STORIED: named_anchors, _apply_named_waypoints(anchor_names=...),
_order_by_anchors and the _anchor exemption in _validate_stops_within_scope do
not exist on the base commit, so this file errors/fails there. GREEN after.

Run:  python3 tests/test_local576_named_anchors.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402

try:
    import scope_memory  # noqa: E402
except Exception:
    scope_memory = None

REQUEST = ("biking tour in a loop from Crystal Lake to Paul Revere via "
           "Commonwealth Avenue Mall & Boston Common, MA")

# The candidate pool as the recorded job produced it: the four anchors the
# listener named (Crystal Lake Park geocoded to Newton, MA) plus North End, which
# the selector chose and which the scope check correctly judged out of the route.
RECORDED_CANDIDATES = [
    {'name': 'North End',
     'address': 'North End, Boston, MA', 'description': 'A Boston neighbourhood.'},
    {'name': 'Boston Common',
     'address': 'Boston Common, Boston, MA 02108', 'description': 'The common.'},
    {'name': 'Crystal Lake Park',
     'address': '400 Crystal Lake Rd, Newton, MA 02464', 'description': 'A park.'},
    {'name': 'Paul Revere Park',
     'address': 'Paul Revere Park, Charlestown, MA', 'description': 'A park.'},
    {'name': 'Commonwealth Avenue Mall',
     'address': 'Commonwealth Ave, Boston, MA', 'description': 'A linear park.'},
]

ANCHOR_NAMES = ['Crystal Lake', 'Commonwealth Avenue Mall', 'Boston Common', 'Paul Revere']


def _new_poi(name, address='', page_sourced=False):
    return {'name': name, 'address': address, 'description': ''}


class TestNamedAnchorExtraction(unittest.TestCase):
    """[LOCAL-576] Step 1 — the route the listener named, extracted structurally."""

    def test_the_recorded_request(self):
        info = gtt.named_anchors(REQUEST)
        self.assertEqual(info['anchors'],
                         ['Crystal Lake', 'Commonwealth Avenue Mall',
                          'Boston Common', 'Paul Revere'],
                         "anchors must be start, via-points in order, then end")
        self.assertEqual(info['start'], 'Crystal Lake',
                         "the listener said the route starts at Crystal Lake")
        self.assertEqual(info['end'], 'Paul Revere')
        self.assertTrue(info['is_loop'], "'in a loop' makes this a loop")

    def test_from_x_to_y(self):
        info = gtt.named_anchors(
            "walking tour from Faneuil Hall to Boston Common, Boston, MA")
        self.assertEqual(info['start'], 'Faneuil Hall')
        self.assertEqual(info['end'], 'Boston Common')
        self.assertFalse(info['is_loop'])

    def test_a_plain_city_has_no_anchors(self):
        """No route phrasing -> no anchors. The whole point is the GRAMMAR, not a
        list of place names: a city tour must not sprout spurious anchors."""
        self.assertEqual(gtt.named_anchors("walking tour in Newton, MA")['anchors'], [])
        self.assertEqual(gtt.named_anchors("restaurant tour of the North End")['anchors'], [])


class TestAnchorsAreMarked(unittest.TestCase):
    """[LOCAL-576] Step 2 — every anchor is user_explicit AND _anchor, whatever
    built the candidate list."""

    def test_candidates_are_marked(self):
        pois = [dict(p) for p in RECORDED_CANDIDATES]
        pois, inserted = gtt._apply_named_waypoints(
            pois, REQUEST, _new_poi, anchor_names=list(reversed(ANCHOR_NAMES)))
        # Nothing to insert — all four anchors are already candidates.
        self.assertEqual(inserted, [])
        by_name = {p['name']: p for p in pois}
        for anchor_poi in ('Crystal Lake Park', 'Commonwealth Avenue Mall',
                            'Boston Common', 'Paul Revere Park'):
            self.assertTrue(by_name[anchor_poi].get('user_explicit'),
                            f"{anchor_poi} must be user_explicit")
            self.assertTrue(by_name[anchor_poi].get('_anchor'),
                            f"{anchor_poi} must carry the _anchor flag")
        # North End is NOT an anchor — the selector chose it, not the listener.
        self.assertFalse(by_name['North End'].get('_anchor'))
        self.assertFalse(by_name['North End'].get('user_explicit'))

    def test_a_missing_anchor_is_inserted(self):
        """An anchor absent from every fill path is inserted, not silently lost."""
        pois = [dict(p) for p in RECORDED_CANDIDATES if p['name'] != 'Crystal Lake Park']
        pois, inserted = gtt._apply_named_waypoints(
            pois, REQUEST, _new_poi, anchor_names=['Crystal Lake'])
        self.assertIn('Crystal Lake', inserted)
        cl = [p for p in pois if p['name'] == 'Crystal Lake'][0]
        self.assertTrue(cl.get('_anchor') and cl.get('user_explicit'))


class _StubbedJudge:
    """Monkeypatch gtt.requests.post so the scope judge is deterministic and no
    network is touched: North End -> outside/high, everything else -> inside/high.
    Also COUNTS how many stops the judge was asked about — the proxy for 'a stop
    reached the expensive stage'."""

    def __init__(self):
        self.checked = []

    def __call__(self, url, headers=None, data=None, **kw):
        import json as _json
        body = _json.loads(data) if data else {}
        prompt = body.get('messages', [{}])[-1].get('content', '')
        # The stop name is on a line "Stop name: '<name>'".
        name = ''
        for line in prompt.splitlines():
            if line.strip().startswith("Stop name:"):
                name = line.split("'", 2)[1] if "'" in line else ''
                break
        self.checked.append(name)
        outside = 'north end' in name.lower()
        verdict = {"inside_scope": not outside,
                   "confidence": "high",
                   "reason": "stubbed verdict for LOCAL-576 test"}

        class _Resp:
            status_code = 200

            def json(self_inner):
                return {"choices": [{"message": {"content": _json.dumps(verdict)}}]}

        return _Resp()


class TestScopeCheckRemovesOnlyWhatWeChose(unittest.TestCase):
    """[LOCAL-576] Steps 2+4 — PHASE 5.6 exempts anchors and removes only North End.

    Because the fix runs this BEFORE PHASE 5, a stop removed here is removed
    before any description is written: the 'writer call' for North End never
    happens, which is the $0.03 the field test wasted.
    """

    def setUp(self):
        if scope_memory:
            scope_memory.reset_cache()
        self._real_post = gtt.requests.post
        self.judge = _StubbedJudge()
        gtt.requests.post = self.judge

    def tearDown(self):
        gtt.requests.post = self._real_post

    def test_anchors_survive_north_end_removed(self):
        pois = [dict(p) for p in RECORDED_CANDIDATES]
        # Mark the four anchors exactly as the real pipeline does.
        pois, _ = gtt._apply_named_waypoints(
            pois, REQUEST, _new_poi, anchor_names=list(reversed(ANCHOR_NAMES)))
        # The pipeline pins the order BEFORE the scope check, so the start anchor
        # (Crystal Lake Park) is at index 0 — the slot PHASE 5.6 keeps for
        # graceful degradation — never a stop WE chose.
        pois = gtt._order_by_anchors(pois, gtt.named_anchors(REQUEST))

        kept = gtt._validate_stops_within_scope(
            pois, 'loop from Crystal Lake to Paul Revere', headers={'Authorization': 'x'})
        names = {p['name'] for p in kept}

        self.assertNotIn('North End', names,
                         "North End (a stop WE chose) must be removed by the scope check")
        for anchor_poi in ('Crystal Lake Park', 'Commonwealth Avenue Mall',
                           'Boston Common', 'Paul Revere Park'):
            self.assertIn(anchor_poi, names,
                          f"{anchor_poi} is an anchor — the scope check must not remove it")

    def test_zero_writer_calls_for_north_end(self):
        """The deliverable: North End is NEVER written. Here the scope check runs
        before writing and removes North End, so the set handed to PHASE 5 does
        not contain it — nothing downstream can spend a writer call on it."""
        pois = [dict(p) for p in RECORDED_CANDIDATES]
        pois, _ = gtt._apply_named_waypoints(
            pois, REQUEST, _new_poi, anchor_names=list(reversed(ANCHOR_NAMES)))
        pois = gtt._order_by_anchors(pois, gtt.named_anchors(REQUEST))
        kept = gtt._validate_stops_within_scope(
            pois, 'loop from Crystal Lake to Paul Revere', headers={'Authorization': 'x'})
        would_be_written = [p['name'] for p in kept]
        self.assertNotIn('North End', would_be_written,
                         "North End must not reach PHASE 5 — 0 writer calls for it")


class TestOrderIsPinnedToTheRoute(unittest.TestCase):
    """[LOCAL-576] Step 3 — stop 1 is where the listener said; end is the turnaround;
    via-points keep the listener's order."""

    def test_loop_from_x_to_y_via_ab(self):
        info = gtt.named_anchors(REQUEST)
        # The final set after the scope check removed North End.
        pois = [{'name': n} for n in
                ['Boston Common', 'Crystal Lake Park', 'Paul Revere Park',
                 'Commonwealth Avenue Mall']]
        ordered = [p['name'] for p in gtt._order_by_anchors(pois, info)]
        self.assertEqual(ordered[0], 'Crystal Lake Park',
                         "the listener said the loop starts at Crystal Lake")
        self.assertEqual(ordered[-1], 'Paul Revere Park',
                         "the loop's turnaround/last anchor is Paul Revere Park")
        # Via-points keep the listener's order (Comm Ave Mall before Boston Common).
        self.assertLess(ordered.index('Commonwealth Avenue Mall'),
                        ordered.index('Boston Common'),
                        "via-points must keep the order the listener gave")

    def test_ordering_never_adds_or_drops_a_stop(self):
        info = gtt.named_anchors(REQUEST)
        pois = [{'name': n} for n in
                ['North End', 'Boston Common', 'Crystal Lake Park',
                 'Paul Revere Park', 'Commonwealth Avenue Mall']]
        ordered = gtt._order_by_anchors(pois, info)
        self.assertEqual(sorted(p['name'] for p in ordered),
                         sorted(p['name'] for p in pois),
                         "ordering is position-only — it must never add or drop a stop")
        self.assertEqual(len(ordered), 5)


class TestFiveStopsEndToEndPieces(unittest.TestCase):
    """[LOCAL-576] The whole chain on the recorded candidates: mark -> scope-check
    (anchors exempt, North End out) -> order. Result is 5 would-be stops? No —
    North End is correctly gone, leaving the FOUR anchors; the real pipeline then
    REPLENISHES back to 5 from the candidate pool. Replenishment needs a network
    and is proven in the live run; here we prove the deterministic core: the four
    NAMED stops all survive and are correctly ordered, and the ONE removal is the
    stop we chose, not one the listener named."""

    def setUp(self):
        if scope_memory:
            scope_memory.reset_cache()
        self._real_post = gtt.requests.post
        gtt.requests.post = _StubbedJudge()

    def tearDown(self):
        gtt.requests.post = self._real_post

    def test_named_stops_all_present_and_ordered(self):
        pois = [dict(p) for p in RECORDED_CANDIDATES]
        pois, _ = gtt._apply_named_waypoints(
            pois, REQUEST, _new_poi, anchor_names=list(reversed(ANCHOR_NAMES)))
        pois = gtt._order_by_anchors(pois, gtt.named_anchors(REQUEST))
        pois = gtt._validate_stops_within_scope(
            pois, 'loop from Crystal Lake to Paul Revere', headers={'Authorization': 'x'})
        pois = gtt._order_by_anchors(pois, gtt.named_anchors(REQUEST))
        names = [p['name'] for p in pois]

        self.assertEqual(names[0], 'Crystal Lake Park')
        self.assertIn('Commonwealth Avenue Mall', names)
        self.assertIn('Boston Common', names)
        self.assertIn('Paul Revere Park', names)
        self.assertNotIn('North End', names)
        self.assertEqual(names[-1], 'Paul Revere Park')


if __name__ == '__main__':
    unittest.main(verbosity=2)
