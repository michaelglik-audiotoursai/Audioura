"""test_local835b_guard_every_path.py — LOCAL-835B (BOUNCE of LOCAL-835).

LOCAL-835 wired the activity-provider guard into the FRESH places path and ran it
ONCE. The field re-run (LEAD, Mac cheap arm, pool off — "Kiteboarding lessons in
Mui Ne, Vietnam" (5) → tour 868) still shipped FIVE stops, only ONE a kite
school: **Sea Horse Resort, Source Kiteboarding, Sandals Restaurant, The Bar,
Jibe's Beach Club**. Two ADD/KEEP paths bypassed the single guard:

  * the LOCAL-788B PHASE 4 MAP OVERRIDE — the LLM correctly excluded Sea Horse
    Resort ("a resort, not a kiteboarding lesson"), but places_search confirmed
    the resort EXISTS in scope and the override kept it anyway (log ~197:
    "OK Kept Sea Horse Resort — [LOCAL-788B] places_search confirms it …
    (LLM exclusion overridden: Sea Horse Resort is a resort, not a kiteboarding
    lesson)");
  * the D545 REPLENISH ladder — gated by tour_category=='restaurant' (the kite
    request misclassifies as a restaurant tour), it asked the map/LLM for
    'dining' with cuisine='kiteboarding lessons' and ADDED restaurants/bars
    (log ~441/535/570: "[D545] ADDED 'Sandals Restaurant'", "ADDED 'The Bar'",
    "ADDED \"Jibe's Beach Club\"").

These tests assert the guard's VERDICT on the EXACT venue + category strings from
the bounce log, so the 788B override is refused and none of the three D545
restaurants/bars can be ADDED. A structural test asserts the guard is wired at
every ADD/KEEP path (788B override, both D545 rounds, pool reuse, final pass).

Run:
    python3 -m pytest tests/test_local835b_guard_every_path.py -q
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ───────────── 788B map override — the Sea Horse Resort line ─────────────────
class TestSeaHorseOverrideRefused:
    """The four places the LLM excluded as off-category, that the 788B map
    override then KEPT because places_search confirms they exist (bounce log
    lines 193/197/198/199). Existence is not provider-hood: each must get a
    verdict of False so the override is refused."""

    REQUEST = "Kiteboarding lessons in Mui Ne, Vietnam"
    # name, Serper/OSM category text, LLM exclusion reason (from the log).
    OVERRIDDEN = [
        ("Sea Horse Resort", "Resort",
         "Sea Horse Resort is a resort, not a kiteboarding lesson"),
        ("Cham Garden Restaurant", "Restaurant",
         "Cham Garden Restaurant is a restaurant, not a kiteboarding lesson"),
        ("Joe's Cafe", "Cafe",
         "Joe's Cafe is a cafe, not a kiteboarding lesson"),
        ("Pogo Beach Bar", "Bar",
         "Pogo Beach Bar is a bar, not a kiteboarding lesson"),
    ]

    def test_each_overridden_place_is_off_category(self):
        from category_match_guard import (requested_activity,
                                           candidate_is_activity_provider)
        act = requested_activity(self.REQUEST)
        assert act is not None and not act["is_food"]
        for name, cat, _reason in self.OVERRIDDEN:
            poi = {"name": name, "_serper_category": cat}
            verdict = candidate_is_activity_provider(poi, act)
            assert verdict is False, (name, cat, verdict)

    def test_sea_horse_resort_without_category_still_off(self):
        # Even with NO category text, "Sea Horse Resort" reads as a resort by its
        # name — a generic landmark/leisure venue, not a kite provider.
        from category_match_guard import (requested_activity,
                                           candidate_is_activity_provider)
        act = requested_activity(self.REQUEST)
        poi = {"name": "Sea Horse Resort"}
        assert candidate_is_activity_provider(poi, act) is not True

    def test_real_kite_school_override_would_be_honoured(self):
        # The guard must NOT block a legitimate map override: a real kite school
        # the LLM wrongly doubted stays overridable (verdict True / None, not
        # False).
        from category_match_guard import (requested_activity,
                                           candidate_is_activity_provider)
        act = requested_activity(self.REQUEST)
        poi = {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"}
        assert candidate_is_activity_provider(poi, act) is True


# ───────────── D545 replenish — Sandals / The Bar / Jibe's ───────────────────
class TestD545ReplenishDropsRestaurants:
    """The three stops the D545 replenish ladder ADDED to the kite tour (bounce
    log lines 441/535/570), with the EXACT category/evidence text from the log.
    The guard must drop all three so none can be ADDED."""

    REQUEST = "Kiteboarding lessons in Mui Ne, Vietnam"
    D545_ADDED = [
        {"name": "Sandals Restaurant", "_serper_category": "Restaurant",
         "extratags": {"cuisine": "Vietnamese and international"}},
        {"name": "The Bar", "_serper_category": "Bar"},
        {"name": "Jibe's Beach Club", "_serper_category": "Beach club"},
    ]

    def test_all_three_d545_additions_dropped(self):
        from category_match_guard import filter_off_category_activity
        logs = []
        kept, dropped = filter_off_category_activity(
            list(self.D545_ADDED), self.REQUEST, log=logs.append)
        assert kept == []
        assert dropped == 3
        joined = " ".join(logs)
        for off in ("Sandals Restaurant", "The Bar", "Jibe's Beach Club"):
            assert off in joined, off
        assert "[LOCAL-835]" in joined

    def test_jibes_beach_club_is_off_category(self):
        # "Jibe's Beach Club" — a beach club is a leisure/food venue, off-category
        # for a kite-lessons provider request even though "beach" and water-sports
        # are nearby in meaning. (When its OWN type says it is a kitesurf school,
        # as in the LOCAL-835 kitesurf-schools case, it is on-category — type wins.)
        from category_match_guard import (requested_activity,
                                           candidate_is_activity_provider)
        act = requested_activity(self.REQUEST)
        poi = {"name": "Jibe's Beach Club", "_serper_category": "Beach club"}
        assert candidate_is_activity_provider(poi, act) is False

    def test_the_bar_is_off_category(self):
        from category_match_guard import (requested_activity,
                                           candidate_is_activity_provider)
        act = requested_activity(self.REQUEST)
        assert candidate_is_activity_provider(
            {"name": "The Bar", "_serper_category": "Bar"}, act) is False

    def test_full_tour868_reduced_to_providers_only(self):
        # The EXACT five delivered stops of tour 868 → only the kite school stays.
        from category_match_guard import filter_off_category_activity
        tour868 = [
            {"name": "Sea Horse Resort", "_serper_category": "Resort"},
            {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"},
            {"name": "Sandals Restaurant", "_serper_category": "Restaurant"},
            {"name": "The Bar", "_serper_category": "Bar"},
            {"name": "Jibe's Beach Club", "_serper_category": "Beach club"},
        ]
        kept, dropped = filter_off_category_activity(
            tour868, self.REQUEST, log=lambda *_: None)
        assert [r["name"] for r in kept] == ["Source Kiteboarding"]
        assert dropped == 4


# ───────────── scuba (the second live request) ──────────────────────────────
class TestScubaCoursesProvidersOnly:
    REQUEST = "Scuba diving courses in Nha Trang, Vietnam"

    def test_dive_providers_kept_food_and_landmark_dropped(self):
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Rainbow Divers", "_serper_category": "Scuba diving center"},
            {"name": "Vietnam Active", "_serper_category": "Dive shop"},
            {"name": "Sailing Club Nha Trang", "_serper_category": "Bar"},
            {"name": "Louisiane Brewhouse", "_serper_category": "Restaurant"},
            {"name": "Nha Trang Beach", "_serper_category": "Beach"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, self.REQUEST, log=lambda *_: None)
        assert [r["name"] for r in kept] == ["Rainbow Divers", "Vietnam Active"]
        assert dropped == 3


# ───────────── one guard, every path — structural wiring ─────────────────────
class TestGuardWiredAtEveryAddKeepPath:
    def _read(self, fname):
        with open(os.path.join(_REPO, fname), encoding="utf-8") as fh:
            return fh.read()

    def test_generate_tour_text_wires_every_add_keep_path(self):
        src = self._read("generate_tour_text.py")
        # 788B map override refusal.
        assert "[LOCAL-835B] map override REFUSED" in src
        # D545 places-first and LLM replenish guards.
        assert "D545 places-first replenish guard" in src
        assert "D545 LLM replenish guard" in src
        # Final pre-narration pass.
        assert "FINAL pre-narration guard" in src
        # The 835 fresh-path post-discovery + the two 835 replenish filters remain.
        assert "[LOCAL-835] activity-provider guard active" in src
        # The override refusal uses candidate_is_activity_provider on a single poi.
        assert "candidate_is_activity_provider" in src
        # At least six call sites reference the filter (post-discovery, PHASE3C,
        # widened, D545 places-first, D545 LLM, final pass).
        assert src.count("filter_off_category_activity") >= 6

    def test_pool_reuse_wires_activity_guard(self):
        src = self._read("stop_pool_orchestrator.py")
        assert "filter_off_category_activity" in src
        assert "[LOCAL-835B] category-scoped reuse" in src
        # The pre-existing LOCAL-830 business guard is still there alongside it.
        assert "filter_off_category_business" in src

    def test_override_block_precedes_the_keep(self):
        # The refusal flag must be CHECKED before the survivors.append keep, i.e.
        # the "map override REFUSED" branch gates the "_p4_map_saved = True" keep.
        src = self._read("generate_tour_text.py")
        i_refuse = src.find("map override REFUSED")
        i_keep = src.find("_p4_map_saved = True")
        assert i_refuse != -1 and i_keep != -1
        # The guard import for the override lives above the keep it protects.
        i_import = src.find("candidate_is_activity_provider as _cap835b")
        assert i_import != -1 and i_import < i_keep


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
