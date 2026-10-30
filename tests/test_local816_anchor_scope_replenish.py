"""test_local816_anchor_scope_replenish.py — LOCAL-816.

Walking tours delivered 4 of 5 stops. The catalog review (808/808B) scored four
walking tours down for a missing 5th stop:

  * 847 "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome"  4/5
  * 849 "Westminster walking tour, London"                               4/5
  * 851 "Lower Manhattan history walking tour, New York"                 4/5
  * 855 "Asakusa and Senso-ji walking tour, Tokyo"                       4/5

OFFLINE ROOT CAUSE (proven here, no network):
  A walking tour's only network-backed replenish-to-N is the D556 block, which
  validates every replenishment candidate against the containment scope from
  ``_resolve_scope_for_check``. For a MULTI-NAMED-ANCHOR request the LLM intent
  joins the named stops into geographic_scope — "Trevi Fountain, Pantheon and
  Piazza Navona, Rome" — and neither ``named_waypoints`` nor ``named_anchors``
  recognises the leading "A, B and C" list, so the D536 waypoint refusal never
  fires. That anchor-list scope is the STOP LIST, not a containable area: every
  on-category replenishment candidate (the Spanish Steps, Piazza Colonna, …) is
  judged "outside 'Trevi Fountain, Pantheon and Piazza Navona'" and rejected, so
  the tour can never refill and ships 4/5 with a needless shortfall apology —
  even though central Rome plainly has more than five real places.

THE FIX (``_anchor_list_enclosing_area`` wired into ``_resolve_scope_for_check``):
  When the scope's leading >= 2 comma/"and" segments are named anchors followed
  by at least one area segment, widen the containment scope to the enclosing area
  ("Rome"), exactly as LOCAL-805 widens a near-landmark scope. The named anchors
  are search seeds, not a boundary, so replenishment is judged against the real
  area and can reach N.

These tests pin, OFFLINE and deterministically:
  * the multi-anchor Trevi/Pantheon/Navona scope widens to the enclosing area;
  * the three genuine single/two-part district scopes (Westminster, Lower
    Manhattan, Asakusa) are UNCHANGED — no false widening;
  * a two-part AREA that merely looks like two names (Beacon Hill, Boston) is not
    widened;
  * the helper only fires with >= 2 leading anchors AND an area tail;
  * with the widened (real-area) scope, the real ``replenish_to_count`` loop can
    bring an anchor tour that dropped a stop back up to N (it could not before,
    because the anchor-list scope rejected every candidate).

Run: python3 -m pytest tests/test_local816_anchor_scope_replenish.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
import scope_memory

# An obviously bad key: the scope LLM judge cannot run, so the containment check
# degrades to its deterministic offline path (scope-memory + place-shape) — the
# same idiom as test_d558_replenish_loop.
BAD_KEY = {"Authorization": "Bearer sk-NOPE", "Content-Type": "application/json"}


class TestAnchorListEnclosingArea(unittest.TestCase):
    """The helper that recognises an anchor-list scope and names its area."""

    def test_trevi_three_anchor_scope_widens_to_rome(self):
        # named_places is EMPTY on purpose — the live trace (2026-10-30) showed the
        # LLM intent puts landmark/square anchors in geographic_scope, NOT in
        # named_places (that key is for business establishments). The detector is
        # STRUCTURAL: it reads the "A, B and C walking tour, City" shape from the
        # request itself, so it must still fire with no named_places.
        intent = {"named_places": [], "country_scope": "Italy"}
        area = gtt._anchor_list_enclosing_area(
            "Trevi Fountain, Pantheon and Piazza Navona, Rome",
            "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome",
            intent)
        self.assertEqual(area, "Rome")

    def test_trevi_scope_without_city_tail_recovers_rome_from_request(self):
        # The REAL field intent (live trace 2026-10-30): the LLM put ONLY the three
        # anchors in geographic_scope, with no city tail AND an empty named_places.
        # The enclosing area is the city the request names after the anchors.
        intent = {"named_places": [], "country_scope": "Italy"}
        area = gtt._anchor_list_enclosing_area(
            "Trevi Fountain, Pantheon and Piazza Navona",
            "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome",
            intent)
        self.assertEqual(area, "Rome")

    def test_structural_detector_reads_the_request_shape(self):
        anchors, city = gtt._leading_anchor_list(
            "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome")
        self.assertEqual(anchors, ["Trevi Fountain", "Pantheon", "Piazza Navona"])
        self.assertEqual(city, "Rome")

    def test_single_anchor_is_not_a_list(self):
        # "Westminster walking tour, London" — one place before "tour".
        anchors, city = gtt._leading_anchor_list("Westminster walking tour, London")
        self.assertEqual(anchors, ["Westminster"])
        self.assertEqual(city, "London")

    def test_real_two_part_district_is_not_an_anchor_list(self):
        # "Westminster, London" — one place + its city. Not an anchor list.
        self.assertIsNone(gtt._anchor_list_enclosing_area(
            "Westminster, London", "Westminster walking tour, London",
            {"named_places": []}))

    def test_lower_manhattan_is_not_an_anchor_list(self):
        self.assertIsNone(gtt._anchor_list_enclosing_area(
            "Lower Manhattan, New York",
            "Lower Manhattan history walking tour, New York",
            {"named_places": []}))

    def test_asakusa_district_is_not_an_anchor_list(self):
        # Only "Asakusa" is in geographic_scope (a real district), even though the
        # request names Senso-ji too. One leading segment is not >= 2 anchors.
        self.assertIsNone(gtt._anchor_list_enclosing_area(
            "Asakusa, Tokyo", "Asakusa and Senso-ji walking tour, Tokyo",
            {"named_places": ["Asakusa", "Senso-ji"]}))

    def test_two_capitalised_segments_that_are_not_named_anchors_are_not_widened(self):
        # "Beacon Hill, Boston" looks like two names but neither is a listener
        # anchor — must not be mistaken for an anchor list.
        self.assertIsNone(gtt._anchor_list_enclosing_area(
            "Beacon Hill, Boston", "Beacon Hill walking tour, Boston",
            {"named_places": []}))

    def test_anchors_without_an_area_tail_cannot_widen(self):
        # "Trevi Fountain, Pantheon" — two anchors, no enclosing area to widen to.
        self.assertIsNone(gtt._anchor_list_enclosing_area(
            "Trevi Fountain, Pantheon", "Trevi Fountain and Pantheon walking tour",
            {"named_places": ["Trevi Fountain", "Pantheon"]}))

    def test_empty_scope_is_none(self):
        self.assertIsNone(gtt._anchor_list_enclosing_area("", "x", {}))


class TestResolveScopeForCheck(unittest.TestCase):
    """The production entry point, across the exact four catalog cases."""

    CASES = {
        # location -> (intent, expected_scope_after_fix)
        "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome": (
            {"geographic_scope": "Trevi Fountain, Pantheon and Piazza Navona",
             "scope_precision": "DISTRICT",
             "named_places": [],
             "country_scope": "Italy"},
            "Rome"),
        "Westminster walking tour, London": (
            {"geographic_scope": "Westminster, London", "scope_precision": "DISTRICT",
             "named_places": []},
            "Westminster, London"),
        "Lower Manhattan history walking tour, New York": (
            {"geographic_scope": "Lower Manhattan, New York",
             "scope_precision": "DISTRICT", "named_places": []},
            "Lower Manhattan, New York"),
        "Asakusa and Senso-ji walking tour, Tokyo": (
            {"geographic_scope": "Asakusa, Tokyo", "scope_precision": "DISTRICT",
             "named_places": ["Asakusa", "Senso-ji"]},
            "Asakusa, Tokyo"),
    }

    def test_multi_anchor_rome_scope_widens_to_enclosing_area(self):
        loc = "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome"
        intent, expected = self.CASES[loc]
        scope = gtt._resolve_scope_for_check(intent, loc, "walking", None, quiet=True)
        self.assertEqual(scope, expected)
        # And it is NOT the anchor list any more.
        self.assertNotIn("Trevi Fountain", scope)

    def test_genuine_district_scopes_are_unchanged(self):
        for loc, (intent, expected) in self.CASES.items():
            if loc.startswith("Trevi"):
                continue
            with self.subTest(loc=loc):
                scope = gtt._resolve_scope_for_check(
                    intent, loc, "walking", None, quiet=True)
                self.assertEqual(scope, expected)


class TestReplenishReachesNWithWidenedScope(unittest.TestCase):
    """End behaviour: with the real area scope the real D558 loop refills to N,
    and with the anchor-list scope it CANNOT — the bug the fix removes.

    The production scope judge (``_validate_stops_within_scope``) needs a network
    LLM, so here it is replaced by a deterministic membership model that answers
    the way the real judge does: a candidate is "inside" a scope only when the
    scope names a real CONTAINING AREA of it, and "outside" when the scope is the
    anchor LIST (a set of specific sibling landmarks a new place is not within).
    That lets the test discriminate old scope (rejects → stays short) from the
    widened scope (accepts → reaches N), which the bad-key offline path alone
    cannot (the real judge errors OPEN on a 401 and would keep the candidate).
    """

    def setUp(self):
        scope_memory.reset_cache()
        self._orig_validate = gtt._validate_stops_within_scope

        # "Spanish Steps" is inside Rome; it is NOT inside the set of three named
        # sibling landmarks. Model exactly that.
        def _fake_validate(poi_list, scope_name, headers, max_check=12,
                           protect_first=True, **kw):
            kept = []
            for i, poi in enumerate(poi_list):
                if protect_first and i == 0:
                    kept.append(poi)
                    continue
                name = (poi.get("name") or "")
                inside = self._is_inside(name, scope_name)
                if inside:
                    kept.append(poi)
            return kept
        gtt._validate_stops_within_scope = _fake_validate

    def tearDown(self):
        gtt._validate_stops_within_scope = self._orig_validate

    @staticmethod
    def _is_inside(name, scope_name):
        s = (scope_name or "").lower()
        # The anchor-list scope names specific sibling landmarks: a *new* place is
        # not contained by it.
        if "trevi fountain" in s and "pantheon" in s:
            return False
        # A real area ("Rome") contains Rome-centre landmarks.
        if s.strip() == "rome":
            return True
        return False

    @staticmethod
    def _poi(name):
        return {"name": name, "description": ""}

    def _run(self, scope):
        poi_list = [self._poi(n) for n in
                    ("Trevi Fountain", "Pantheon", "Piazza Navona", "Piazza Colonna")]

        def propose(need, seen):
            return [{"name": "Spanish Steps", "why": "Rome landmark"}]

        gtt.replenish_to_count(poi_list, want=5, scope=scope, headers=BAD_KEY,
                               propose=propose, make_poi=self._poi)
        return [p["name"] for p in poi_list]

    def test_anchor_list_scope_cannot_refill_the_bug(self):
        names = self._run("Trevi Fountain, Pantheon and Piazza Navona, Rome")
        self.assertEqual(len(names), 4,
                         "anchor-list scope should reject the candidate (the bug)")
        self.assertNotIn("Spanish Steps", names)

    def test_widened_rome_scope_refills_to_five_the_fix(self):
        # The scope the production resolver now hands the loop for this request —
        # using the REAL field intent (anchors only, no city tail in the scope).
        loc = "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome"
        intent = {"geographic_scope": "Trevi Fountain, Pantheon and Piazza Navona",
                  "scope_precision": "DISTRICT",
                  "named_places": [],
                  "country_scope": "Italy"}
        scope = gtt._resolve_scope_for_check(intent, loc, "walking", None, quiet=True)
        self.assertEqual(scope, "Rome")
        names = self._run(scope)
        self.assertEqual(len(names), 5, f"tour still short with widened scope: {names}")
        self.assertIn("Spanish Steps", names)



if __name__ == "__main__":
    unittest.main(verbosity=2)
