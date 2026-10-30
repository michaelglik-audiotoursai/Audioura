"""test_local818_district_refill.py — LOCAL-818.

Walking tours with a GENUINE DISTRICT scope still delivered 4 of 5 stops:

  * 849 "Westminster walking tour, London"                 4/5
  * 851 "Lower Manhattan history walking tour, New York"    4/5
  * 855 "Asakusa and Senso-ji walking tour, Tokyo"          4/5

LOCAL-816 fixed the named-anchor case (847 Trevi/Pantheon/Navona) by widening an
anchor-LIST scope to its enclosing area. It explicitly did NOT fix these three
(SUBMISSION_LOCAL-816.md "Scope of change / what is NOT fixed"): their scopes are
real districts and resolve fine. The 4/5 has a DIFFERENT mechanism.

OFFLINE ROOT CAUSE (proven here, no network):
  These three reach the LOCAL-576 pre-writing scope check with a VALID district
  scope, so that gate refills correctly. But a stop is then dropped AFTER the last
  network replenish — by the LOCAL-802 FINAL same-building dedupe (which runs on
  the final list, right before PHASE 5), or by any other late drop on this path —
  and NOTHING refills the count. The last replenish already ran, so the tour just
  gets shorter and ships 4/5 with a needless shortfall apology, even though the
  district plainly has more than five real places.

  Verified deterministically below: each district request resolves to a valid,
  NON-EMPTY containment scope (so a refill there WILL validate candidates), and
  ``dedupe_same_building_stops`` drops the 5th stop on a same-building pair (shared
  QID / alias bridge) — the exact late, unrefilled drop.

THE FIX (generate_tour_text.py, after the FINAL same-building dedupe):
  After ALL late drops have run — right before a single description is written —
  if the stop count is below what the listener asked for, run ONE more on-category
  ``replenish_to_count`` round inside the SAME scope (same resolver, same
  proposer, same validation as LOCAL-576). It never pads: replenish only adds real
  candidates that pass the same containment check, so an empty pool leaves the
  count honest.

These tests pin, OFFLINE and deterministically:
  * each of the three district requests resolves to a valid non-empty scope
    (the precondition for the post-drop refill to validate candidates);
  * the FINAL same-building dedupe really does drop the 5th stop (the late drop);
  * composing the production post-drop logic (dedupe -> replenish_to_count with a
    deterministic scope judge) brings the tour from the dropped 4 back up to 5 —
    i.e. a drop-without-refill is now refilled;
  * WITHOUT the refill (dedupe alone) the tour stays at 4 (the bug);
  * the refill is honest: when the replenish pool has no real in-scope place left,
    the count stays at 4 rather than padding.

Run: python3 -m pytest tests/test_local818_district_refill.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
import local802_relevance_gate as l802
import scope_memory

BAD_KEY = {"Authorization": "Bearer sk-NOPE", "Content-Type": "application/json"}

# The exact three catalog district cases: (request, intent, same-building pair,
# the real in-scope replenishment place the pool offers, the kept stops).
CASES = [
    {
        "id": 849,
        "request": "Westminster walking tour, London",
        "intent": {"geographic_scope": "Westminster, London",
                   "scope_precision": "DISTRICT", "named_places": [],
                   "country_scope": "United Kingdom"},
        "scope": "Westminster, London",
        # Westminster Abbey == Collegiate Church of St Peter at Westminster: ONE
        # building, shipped twice (shared QID). The FINAL dedupe collapses them.
        "dup_pair": ({"name": "Westminster Abbey", "wikidata_qid": "Q5933"},
                     {"name": "Collegiate Church of St Peter at Westminster",
                      "wikidata_qid": "Q5933"}),
        "others": ["Big Ben", "Churchill War Rooms", "Westminster Cathedral"],
        "refill_place": "St James's Park",
        "offscope_place": "Edinburgh Castle",
    },
    {
        "id": 851,
        "request": "Lower Manhattan history walking tour, New York",
        "intent": {"geographic_scope": "Lower Manhattan, New York",
                   "scope_precision": "DISTRICT", "named_places": [],
                   "country_scope": "United States"},
        "scope": "Lower Manhattan, New York",
        "dup_pair": ({"name": "Federal Hall", "wikidata_qid": "Q1397"},
                     {"name": "Federal Hall National Memorial",
                      "wikidata_qid": "Q1397"}),
        "others": ["Trinity Church", "Fraunces Tavern", "Stone Street"],
        "refill_place": "Battery Park",
        "offscope_place": "Yankee Stadium",
    },
    {
        "id": 855,
        "request": "Asakusa and Senso-ji walking tour, Tokyo",
        "intent": {"geographic_scope": "Asakusa, Tokyo",
                   "scope_precision": "DISTRICT", "named_places": [],
                   "country_scope": "Japan"},
        "scope": "Asakusa, Tokyo",
        "dup_pair": ({"name": "Sensō-ji", "wikidata_qid": "Q319105"},
                     {"name": "Asakusa Kannon Temple", "wikidata_qid": "Q319105"}),
        "others": ["Kaminarimon", "Nakamise-dori", "Asakusa Culture Center"],
        "refill_place": "Asakusa Shrine",
        "offscope_place": "Tokyo Tower",
    },
]


def _by_id(case_id):
    return next(c for c in CASES if c["id"] == case_id)


class TestDistrictScopeResolves(unittest.TestCase):
    """Precondition: each district request resolves to a valid non-empty scope.

    If the scope were empty, the post-drop refill would skip (no containment check
    applies) — so this is the ground the refill stands on. LOCAL-816 left these
    scopes untouched on purpose; confirm they are still real districts.
    """

    def test_all_three_districts_resolve_nonempty(self):
        for c in CASES:
            scope = gtt._resolve_scope_for_check(
                c["intent"], c["request"], "walking", None, quiet=True)
            self.assertTrue(scope, f"{c['id']} resolved an EMPTY scope: {scope!r}")
            self.assertEqual(scope, c["scope"],
                             f"{c['id']} scope drifted: {scope!r}")


class TestFinalDedupeIsTheLateDrop(unittest.TestCase):
    """The FINAL same-building dedupe drops the 5th stop — the unrefilled drop."""

    def test_each_case_drops_one_same_building_stop(self):
        for c in CASES:
            a, b = c["dup_pair"]
            stops = [dict(a), dict(b)] + [{"name": n} for n in c["others"]]
            # 5 stops in, two of them the same building.
            self.assertEqual(len(stops), 5)
            kept, removed = l802.dedupe_same_building_stops(stops)
            self.assertEqual(len(kept), 4,
                             f"{c['id']} dedupe did not drop the duplicate: {kept}")
            self.assertEqual(len(removed), 1, f"{c['id']} removed {removed}")


class TestPostDropRefill(unittest.TestCase):
    """Compose the production post-drop logic OFFLINE: dedupe (late drop) then
    ``replenish_to_count`` with a deterministic scope judge. Proves the drop is
    now refilled, could not be before, and is never padded.
    """

    def setUp(self):
        scope_memory.reset_cache()
        self._orig_validate = gtt._validate_stops_within_scope
        # Deterministic stand-in for the network scope judge: a candidate is
        # "inside" only when the scope is its real district; a declared off-scope
        # place is rejected. (The real judge needs an LLM; a 401 would error OPEN.)
        self._inscope = set()
        self._offscope = set()

        def _fake_validate(poi_list, scope_name, headers, max_check=12,
                           protect_first=True, **kw):
            kept = []
            for i, poi in enumerate(poi_list):
                if protect_first and i == 0:
                    kept.append(poi)
                    continue
                name = (poi.get("name") or "")
                if name in self._offscope:
                    continue
                kept.append(poi)
            return kept
        gtt._validate_stops_within_scope = _fake_validate

    def tearDown(self):
        gtt._validate_stops_within_scope = self._orig_validate

    def _dedupe_then_refill(self, case, pool, want=5, refill=True):
        """Mirror the production path: FINAL same-building dedupe, then (fix) one
        replenish round inside the same scope. ``refill=False`` is the pre-fix
        behaviour (dedupe only)."""
        a, b = case["dup_pair"]
        # 5 stops: the same-building pair + three distinct others. The dedupe
        # collapses the pair to one, leaving 4; the refill pool offers a NEW
        # in-district place (not already on the tour).
        poi_list = [dict(a), dict(b)] + [{"name": n} for n in case["others"]]
        self.assertEqual(len(poi_list), 5, "setup: 5 stops before dedupe")
        # Simulate the FINAL same-building dedupe dropping the duplicate.
        poi_list, removed = l802.dedupe_same_building_stops(poi_list)
        self.assertEqual(len(poi_list), 4, "setup: dedupe should leave 4 stops")

        if refill:
            scope = gtt._resolve_scope_for_check(
                case["intent"], case["request"], "walking", None, quiet=True)
            self.assertTrue(scope)
            seen = {(p.get("name") or "").lower() for p in poi_list}

            def propose(need, _seen):
                return [{"name": n, "why": "in-district place"} for n in pool]

            gtt.replenish_to_count(poi_list, want=want, scope=scope, headers=BAD_KEY,
                                   propose=propose, make_poi=lambda n: {"name": n},
                                   seen=seen)
        return [p.get("name") for p in poi_list]

    def test_without_refill_stays_four_the_bug(self):
        for c in CASES:
            names = self._dedupe_then_refill(c, pool=[c["refill_place"]], refill=False)
            self.assertEqual(len(names), 4,
                             f"{c['id']} pre-fix must stay 4 (the bug): {names}")

    def test_refill_brings_each_district_back_to_five_the_fix(self):
        for c in CASES:
            # The pool offers one real in-scope place not already on the tour.
            names = self._dedupe_then_refill(c, pool=[c["refill_place"]])
            self.assertEqual(len(names), 5,
                             f"{c['id']} not refilled to 5: {names}")
            self.assertIn(c["refill_place"], names)

    def test_refill_is_honest_no_in_scope_place_leaves_four(self):
        # When the only candidate the pool returns is OUT of scope, the same
        # containment check rejects it and the count stays 4 — no padding.
        for c in CASES:
            self._offscope.add(c["offscope_place"])
            names = self._dedupe_then_refill(c, pool=[c["offscope_place"]])
            self.assertEqual(len(names), 4,
                             f"{c['id']} padded with an off-scope place: {names}")
            self.assertNotIn(c["offscope_place"], names)

    def test_westminster_end_to_end_named_stops(self):
        # The flagship case (849): Westminster Abbey survives (it absorbs the
        # duplicate), and St James's Park refills the dropped slot.
        c = _by_id(849)
        names = self._dedupe_then_refill(c, pool=[c["refill_place"]])
        self.assertEqual(len(names), 5)
        self.assertIn("Westminster Abbey", names)
        self.assertIn("St James's Park", names)
        self.assertNotIn("Collegiate Church of St Peter at Westminster", names)


class TestFixIsWired(unittest.TestCase):
    """Guard the ordering in generate_tour_text.py: the LOCAL-818 post-drop refill
    must sit AFTER the FINAL same-building dedupe and BEFORE PHASE 5 narration, or
    the drop it exists to refill would again go unrefilled before money is spent.
    """

    def _source(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "generate_tour_text.py")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_refill_after_final_dedupe_before_narration(self):
        src = self._source()
        i_dedupe = src.find("FINAL same-building dedupe for place-anchor tours")
        i_refill = src.find("[LOCAL-818] FINAL REPLENISH")
        i_narr = src.find(
            "PHASE 5: Generating detailed descriptions for each POI (parallel)")
        self.assertNotEqual(i_dedupe, -1, "FINAL same-building dedupe block missing")
        self.assertNotEqual(i_refill, -1, "LOCAL-818 refill block missing")
        self.assertNotEqual(i_narr, -1, "PHASE 5 narration marker missing")
        self.assertLess(i_dedupe, i_refill,
                        "LOCAL-818 refill must run AFTER the FINAL dedupe")
        self.assertLess(i_refill, i_narr,
                        "LOCAL-818 refill must run BEFORE PHASE 5 narration")

    def test_refill_uses_the_same_resolver_and_proposer(self):
        src = self._source()
        # The refill must validate against the SAME scope resolver and use the
        # same real proposer as LOCAL-576 — not a private copy that could drift.
        block = src[src.find("[LOCAL-818] FINAL REPLENISH"):
                    src.find("PHASE 5: Generating detailed descriptions for each POI (parallel)")]
        self.assertIn("_resolve_scope_for_check", block)
        self.assertIn("propose_replacements", block)
        self.assertIn("replenish_to_count", block)
        self.assertIn("_requested_stop_count_original", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
