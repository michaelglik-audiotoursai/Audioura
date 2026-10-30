"""test_local836_single_anchor_scope.py — LOCAL-836.

A SINGLE-NAMED-ANCHOR walking tour delivered 2 of 4 stops:

  * "Ben Thanh Market walking tour, Ho Chi Minh City" (4)  ->  2/4
    (Saigon Square, Ben Thanh Market) — $0.096, no Gemini (wave 13 proof 508).

District 1 around Ben Thanh is one of the densest walkable areas in Vietnam
(Ben Thanh Market, Saigon Square, Ho Chi Minh City Museum, Bitexco Tower, Nguyen
Hue walking street, the Opera House, City Hall, Notre-Dame, the Central Post
Office — all within ~1.5 km), so 2/4 is never honest. LOCAL-816/818's refill did
not reach 4.

OFFLINE ROOT CAUSE (proven here, no network):
  "Ben Thanh Market" is a NAMED ANCHOR — a point feature (a market), not a
  containable area. The LLM intent echoes it into geographic_scope
  ("Ben Thanh Market, District 1, Ho Chi Minh City", precision DISTRICT, OR the
  bare "Ben Thanh Market", precision BUILDING). The D558 containment scope then
  becomes that market point, so every real nearby landmark (the Opera House,
  Bitexco, the Post Office, ...) is judged "near Ben Thanh Market but not INSIDE
  it" and rejected. Replenishment can never reach N and the tour ships 2/4.

  Neither prior fix covers it:
    * LOCAL-805 widens a "<business> near <landmark>" scope, but only when a
      locative connector ("near"/"around"/"in") sits in the subject segment.
      "Ben Thanh Market walking tour, HCMC" has NO connector, so LOCAL-805's
      ``_near_landmark_enclosing_area`` returns None and does not widen.
    * LOCAL-816 widens a LIST of >= 2 named anchors ("Trevi, Pantheon and
      Navona, Rome"); a single leading anchor is < 2 and is left alone.

THE FIX (``_single_anchor_enclosing_area`` wired into ``_resolve_scope_for_check``):
  When the request is "<Anchor> walking tour, <City>" with ONE leading anchor that
  is a POINT FEATURE (a landmark/POI class - lake, market, square, fountain,
  cathedral, temple, tower, bridge, palace, opera house, museum, ...), and the
  scope IS that anchor, widen the containment scope to the enclosing area (the
  admin tail of the scope, or the city the request names) - exactly as
  LOCAL-805/816 widen a seed point to its area. A GENUINE DISTRICT anchor
  (Westminster, Lower Manhattan, Asakusa, Beacon Hill) is NOT a point feature and
  is left unchanged. When the point anchor has no enclosing area at all, the
  stop-by-stop containment check is skipped (scope='') and the ~1.5 km radius
  stands on its own.

These tests pin, OFFLINE and deterministically:
  * the Ben Thanh single-anchor scope (both DISTRICT and BUILDING intents) widens
    to the enclosing area ("District 1, Ho Chi Minh City" / "Ho Chi Minh City"),
    never the market point;
  * Hoan Kiem Lake (the second live PASS case) widens the same way;
  * the three genuine district scopes (Westminster, Lower Manhattan, Asakusa) and
    a two-part district (Beacon Hill, Boston) are UNCHANGED - no false widening;
  * the helper fires ONLY for a single POINT-FEATURE anchor with an area to widen
    to; a point anchor with no enclosing area yields '' (radius only);
  * with the widened scope, the real ``replenish_to_count`` loop brings a dense
    single-anchor tour that dropped stops back up to N (it could not before,
    because the point-anchor scope rejected every nearby candidate).

Run: python3 -m pytest tests/test_local836_single_anchor_scope.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
import scope_memory

# An obviously bad key: the scope LLM judge cannot run, so the offline path is
# exercised - same idiom as test_local816/818.
BAD_KEY = {"Authorization": "Bearer sk-NOPE", "Content-Type": "application/json"}


class TestSingleAnchorEnclosingArea(unittest.TestCase):
    """The helper that recognises a single POINT-FEATURE anchor and names its
    enclosing area, or None for a genuine district / non-anchor scope."""

    def test_ben_thanh_district_scope_widens_to_area(self):
        # The field DISTRICT intent: scope carries the enclosing admin tail.
        area = gtt._single_anchor_enclosing_area(
            "Ben Thanh Market, District 1, Ho Chi Minh City",
            "Ben Thanh Market walking tour, Ho Chi Minh City",
            {"named_places": [], "country_scope": "Vietnam"})
        self.assertEqual(area, "District 1, Ho Chi Minh City")

    def test_ben_thanh_building_scope_recovers_city_from_request(self):
        # The BUILDING intent: scope is the bare market point, no tail of its own.
        # The enclosing area is the city the request names after the anchor.
        area = gtt._single_anchor_enclosing_area(
            "Ben Thanh Market",
            "Ben Thanh Market walking tour, Ho Chi Minh City",
            {"named_places": [], "country_scope": "Vietnam"})
        self.assertEqual(area, "Ho Chi Minh City")

    def test_hoan_kiem_lake_widens_to_hanoi(self):
        area = gtt._single_anchor_enclosing_area(
            "Hoan Kiem Lake, Hanoi",
            "Hoan Kiem Lake walking tour, Hanoi",
            {"named_places": [], "country_scope": "Vietnam"})
        self.assertEqual(area, "Hanoi")

    def test_hoan_kiem_lake_building_scope_recovers_city(self):
        area = gtt._single_anchor_enclosing_area(
            "Hoan Kiem Lake",
            "Hoan Kiem Lake walking tour, Hanoi",
            {"named_places": []})
        self.assertEqual(area, "Hanoi")

    # -- genuine districts must NOT widen -------------------------------------
    def test_westminster_district_is_not_widened(self):
        self.assertIsNone(gtt._single_anchor_enclosing_area(
            "Westminster, London", "Westminster walking tour, London",
            {"named_places": []}))

    def test_lower_manhattan_is_not_widened(self):
        self.assertIsNone(gtt._single_anchor_enclosing_area(
            "Lower Manhattan, New York",
            "Lower Manhattan history walking tour, New York",
            {"named_places": []}))

    def test_asakusa_district_is_not_widened(self):
        self.assertIsNone(gtt._single_anchor_enclosing_area(
            "Asakusa, Tokyo", "Asakusa and Senso-ji walking tour, Tokyo",
            {"named_places": ["Asakusa", "Senso-ji"]}))

    def test_beacon_hill_two_part_district_is_not_widened(self):
        self.assertIsNone(gtt._single_anchor_enclosing_area(
            "Beacon Hill, Boston", "Beacon Hill walking tour, Boston",
            {"named_places": []}))

    def test_multi_anchor_is_left_to_local816(self):
        # >= 2 leading anchors is LOCAL-816's job; this single-anchor helper
        # declines so the two fixes never fight over the same scope.
        self.assertIsNone(gtt._single_anchor_enclosing_area(
            "Trevi Fountain, Pantheon and Piazza Navona, Rome",
            "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome",
            {"named_places": []}))

    def test_point_anchor_without_area_tail_is_empty_not_none(self):
        # A point anchor whose request names no city -> no containment boundary,
        # so the helper returns '' (radius only), distinct from None (not an
        # anchor at all). "" means "skip the stop-by-stop check".
        area = gtt._single_anchor_enclosing_area(
            "Boston Common", "Boston Common walking tour",
            {"named_places": []})
        self.assertEqual(area, "")

    def test_empty_scope_is_none(self):
        self.assertIsNone(gtt._single_anchor_enclosing_area("", "x", {}))


class TestResolveScopeForCheck(unittest.TestCase):
    """The production entry point across the case and its must-not-break siblings."""

    def test_ben_thanh_district_intent_widens(self):
        scope = gtt._resolve_scope_for_check(
            {"geographic_scope": "Ben Thanh Market, District 1, Ho Chi Minh City",
             "scope_precision": "DISTRICT", "named_places": [],
             "country_scope": "Vietnam"},
            "Ben Thanh Market walking tour, Ho Chi Minh City",
            "walking", None, quiet=True)
        self.assertNotIn("ben thanh market", scope.lower())
        self.assertIn("ho chi minh city", scope.lower())

    def test_ben_thanh_building_intent_widens_to_city(self):
        scope = gtt._resolve_scope_for_check(
            {"geographic_scope": "Ben Thanh Market", "scope_precision": "BUILDING",
             "named_places": [], "country_scope": "Vietnam"},
            "Ben Thanh Market walking tour, Ho Chi Minh City",
            "walking", None, quiet=True)
        self.assertNotIn("market", scope.lower())
        self.assertIn("ho chi minh city", scope.lower())

    def test_hoan_kiem_lake_widens(self):
        scope = gtt._resolve_scope_for_check(
            {"geographic_scope": "Hoan Kiem Lake, Hanoi", "scope_precision": "DISTRICT",
             "named_places": [], "country_scope": "Vietnam"},
            "Hoan Kiem Lake walking tour, Hanoi", "walking", None, quiet=True)
        self.assertNotIn("lake", scope.lower())
        self.assertEqual(scope, "Hanoi")

    def test_genuine_districts_unchanged(self):
        CASES = {
            "Westminster walking tour, London": (
                {"geographic_scope": "Westminster, London",
                 "scope_precision": "DISTRICT", "named_places": []},
                "Westminster, London"),
            "Lower Manhattan history walking tour, New York": (
                {"geographic_scope": "Lower Manhattan, New York",
                 "scope_precision": "DISTRICT", "named_places": []},
                "Lower Manhattan, New York"),
            "Asakusa and Senso-ji walking tour, Tokyo": (
                {"geographic_scope": "Asakusa, Tokyo",
                 "scope_precision": "DISTRICT",
                 "named_places": ["Asakusa", "Senso-ji"]},
                "Asakusa, Tokyo"),
        }
        for loc, (intent, expected) in CASES.items():
            with self.subTest(loc=loc):
                scope = gtt._resolve_scope_for_check(
                    intent, loc, "walking", None, quiet=True)
                self.assertEqual(scope, expected)


class TestReplenishReachesNWithWidenedScope(unittest.TestCase):
    """End behaviour: with the widened (real-area) scope the real D558 loop
    refills a dense single-anchor tour to N; with the point-anchor scope it
    CANNOT - the bug the fix removes.

    The production scope judge needs a network LLM, so it is replaced by a
    deterministic membership model: a candidate is "inside" a scope only when the
    scope names a real CONTAINING AREA, and "outside" when the scope is the anchor
    POINT (a specific place a new landmark is not within)."""

    def setUp(self):
        scope_memory.reset_cache()
        self._orig_validate = gtt._validate_stops_within_scope

        def _fake_validate(poi_list, scope_name, headers, max_check=12,
                           protect_first=True, **kw):
            kept = []
            for i, poi in enumerate(poi_list):
                if protect_first and i == 0:
                    kept.append(poi)
                    continue
                if self._is_inside((poi.get("name") or ""), scope_name):
                    kept.append(poi)
            return kept
        gtt._validate_stops_within_scope = _fake_validate

    def tearDown(self):
        gtt._validate_stops_within_scope = self._orig_validate

    @staticmethod
    def _is_inside(name, scope_name):
        s = (scope_name or "").lower()
        # The anchor-POINT scope names the market itself: a new place is not
        # inside the market building.
        if "ben thanh market" in s:
            return False
        # A real area ("...Ho Chi Minh City") contains District-1 landmarks.
        if "ho chi minh city" in s:
            return True
        return False

    @staticmethod
    def _poi(name):
        return {"name": name, "description": ""}

    def _run(self, scope):
        poi_list = [self._poi(n) for n in
                    ("Ben Thanh Market", "Saigon Square")]

        def propose(need, seen):
            # Real District-1 landmarks within ~1.5 km of Ben Thanh.
            return [{"name": "Bitexco Financial Tower", "why": "D1 landmark"},
                    {"name": "Ho Chi Minh City Opera House", "why": "D1 landmark"}]

        gtt.replenish_to_count(poi_list, want=4, scope=scope, headers=BAD_KEY,
                               propose=propose, make_poi=self._poi)
        return [p["name"] for p in poi_list]

    def test_point_anchor_scope_cannot_refill_the_bug(self):
        names = self._run("Ben Thanh Market, District 1, Ho Chi Minh City")
        self.assertEqual(len(names), 2,
                         "point-anchor scope should reject the candidates (the bug)")

    def test_widened_scope_refills_to_four_the_fix(self):
        loc = "Ben Thanh Market walking tour, Ho Chi Minh City"
        intent = {"geographic_scope": "Ben Thanh Market, District 1, Ho Chi Minh City",
                  "scope_precision": "DISTRICT", "named_places": [],
                  "country_scope": "Vietnam"}
        scope = gtt._resolve_scope_for_check(intent, loc, "walking", None, quiet=True)
        names = self._run(scope)
        self.assertEqual(len(names), 4, f"tour still short with widened scope: {names}")
        self.assertIn("Bitexco Financial Tower", names)
        self.assertIn("Ho Chi Minh City Opera House", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
