"""test_local847_area_scope_and_mixed_venues.py — LOCAL-847.

Two field defects from request 68ce1fe4 "Kiteboarding schools in Mui Ne beach
area, Vietnam" (GCloud_Storied wave 18 proof, gen 00023-9zz @ 2532fc1c, cheap
env), which REFUSED ("We could not find enough verified material…"):

  (1) SCOPE — LOCAL-843's ``_widen_generic_feature_scope`` stripped exactly ONE
      trailing feature word ("beach"), so "beach area", "area", "district",
      "town centre", "city centre", "old town area" all survived and the place
      did not geocode → refusal. LOCAL-847 strips the WHOLE trailing run of
      generic area/feature words and a leading "near", for a provider request,
      never past the city; and ``_geocode_scope_center`` / ``_geocode_scope_bbox``
      fall back to the next comma segment (town/ward/city) when the full scope
      does not geocode.

  (2) MIXED VENUES — LOCAL-835 dropped "Kitesurfing Mui Ne - Surf Bar" as
      class=restaurant (a real kite provider that also has a bar → false drop),
      because the food check fired before the activity signal. LOCAL-847: a name
      or type carrying a STRONG activity-provider token (a compound activity word
      like "kitesurfing"/"kiteboarding"/"diving", or a short root beside a
      provider noun / "&"-"and" construct like "Dive & Dine") is a provider even
      when it also says bar/café/restaurant. Only a venue whose name AND type lack
      the activity is off-category — "Kite Bar", "The Bar", "Blue Sky Restaurant"
      still drop.

All offline (no network, no key).

Run:
    python3 -m pytest tests/test_local847_area_scope_and_mixed_venues.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("OPENAI_API_KEY", "fake-key-for-test")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-test")

import generate_tour_text as gtt
import stop_existence_gate as seg
import category_match_guard as cmg


REQ = "Kiteboarding schools in Mui Ne beach area, Vietnam"


# ───────────── (1a) scope widening — generic area/feature phrases ────────────
class TestWidenGenericAreaScope:
    def test_mui_ne_beach_area_widens_to_town(self):
        assert gtt._widen_generic_feature_scope(
            "Mui Ne beach area, Vietnam", REQ) == "Mui Ne, Vietnam"

    def test_near_mui_ne_beach_widens_and_drops_near(self):
        # A leading locative "near" rode into the scope head; strip it AND the
        # trailing feature word → the town.
        assert gtt._widen_generic_feature_scope(
            "near Mui Ne beach, Vietnam", REQ) == "Mui Ne, Vietnam"

    def test_nha_trang_city_centre_widens_to_city(self):
        assert gtt._widen_generic_feature_scope(
            "Nha Trang city centre, Vietnam",
            "Kitesurfing schools in Nha Trang city centre, Vietnam"
        ) == "Nha Trang, Vietnam"

    def test_hoi_an_old_town_area_widens_to_town(self):
        # Strips the whole "old town area" generic run, leaving "Hoi An".
        assert gtt._widen_generic_feature_scope(
            "Hoi An old town area, Vietnam",
            "Dive centre in Hoi An old town area, Vietnam"
        ) == "Hoi An, Vietnam"

    def test_district_and_neighbourhood_widen(self):
        assert gtt._widen_generic_feature_scope(
            "Mui Ne district, Vietnam", REQ) == "Mui Ne, Vietnam"
        assert gtt._widen_generic_feature_scope(
            "Mui Ne neighbourhood, Vietnam", REQ) == "Mui Ne, Vietnam"
        assert gtt._widen_generic_feature_scope(
            "Mui Ne surroundings, Vietnam", REQ) == "Mui Ne, Vietnam"

    def test_single_feature_word_still_widens_local843(self):
        # The LOCAL-843 behaviour (one trailing feature word) is preserved.
        assert gtt._widen_generic_feature_scope(
            "Mui Ne beach, Vietnam", "Kitesurf lessons at Mui Ne beach, Vietnam"
        ) == "Mui Ne, Vietnam"
        assert gtt._widen_generic_feature_scope(
            "Nha Trang bay, Vietnam", "Scuba diving courses at Nha Trang bay"
        ) == "Nha Trang, Vietnam"

    def test_bare_generic_phrase_with_no_town_left_alone(self):
        # No real place token precedes the generic run → nothing to fall back to.
        assert gtt._widen_generic_feature_scope(
            "beach area, Vietnam", REQ) == "beach area, Vietnam"
        assert gtt._widen_generic_feature_scope(
            "city centre, Vietnam", REQ) == "city centre, Vietnam"

    def test_walking_tour_on_the_beach_is_not_widened(self):
        # A walking/area tour ON the beach keeps the beach — it is the subject,
        # not a provider's search centre.
        walk = "Walking tour on Mui Ne beach area, Vietnam"
        assert gtt._widen_generic_feature_scope(
            "Mui Ne beach area, Vietnam", walk) == "Mui Ne beach area, Vietnam"

    def test_never_widens_past_the_city(self):
        # The city/admin tail (", Vietnam") is always preserved; only the leading
        # segment's trailing qualifier run is removed.
        out = gtt._widen_generic_feature_scope("Mui Ne beach area, Vietnam", REQ)
        assert out.endswith(", Vietnam")


# ───────────── (1b) scope widening via _scope_from_request (intent path) ─────
class TestScopeFromRequestUsesIntent:
    def test_intent_scope_widened(self):
        for gs in ("Mui Ne beach area, Vietnam", "Mui Ne, Vietnam"):
            scope = gtt._scope_from_request(REQ, {"geographic_scope": gs})
            assert scope == "Mui Ne, Vietnam", (gs, scope)

    def test_city_centre_intent_widened(self):
        req = "Kitesurfing schools in Nha Trang city centre, Vietnam"
        scope = gtt._scope_from_request(
            req, {"geographic_scope": "Nha Trang city centre, Vietnam"})
        assert scope == "Nha Trang, Vietnam"


# ───────────── (2) comma-segment geocode fallback (pure part) ────────────────
class TestScopeFallbackCandidates:
    def test_full_then_enclosing_tail(self):
        assert seg._scope_fallback_candidates("Mui Ne beach area, Vietnam") == [
            "Mui Ne beach area, Vietnam", "Vietnam"]

    def test_three_segments_peel_leading(self):
        assert seg._scope_fallback_candidates(
            "Ham Tien ward, Mui Ne, Vietnam") == [
            "Ham Tien ward, Mui Ne, Vietnam", "Mui Ne, Vietnam", "Vietnam"]

    def test_single_segment(self):
        assert seg._scope_fallback_candidates("Boston") == ["Boston"]

    def test_empty(self):
        assert seg._scope_fallback_candidates("") == []

    def test_geocode_center_falls_back_when_full_fails(self, monkeypatch):
        # Full scope geocodes to nothing; the next comma segment resolves.
        calls = []

        class _Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        def _fake_request(params, context=""):
            q = params["q"]
            calls.append(q)
            if q == "Mui Ne beach area, Vietnam":
                return _Resp([])            # full scope: no hit
            if q == "Vietnam":
                return _Resp([{"lat": "16.0", "lon": "108.0"}])
            return _Resp([])

        monkeypatch.setattr(seg, "_nominatim_request", _fake_request)
        center = seg._geocode_scope_center("Mui Ne beach area, Vietnam")
        assert center == (16.0, 108.0)
        assert "Mui Ne beach area, Vietnam" in calls and "Vietnam" in calls

    def test_geocode_bbox_falls_back_when_full_fails(self, monkeypatch):
        class _Resp:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        def _fake_request(params, context=""):
            q = params["q"]
            if q == "Ham Tien ward, Mui Ne, Vietnam":
                return _Resp([])
            if q == "Mui Ne, Vietnam":
                return _Resp([{"boundingbox": ["10.9", "11.0", "108.2", "108.3"]}])
            return _Resp([])

        monkeypatch.setattr(seg, "_nominatim_request", _fake_request)
        bbox = seg._geocode_scope_bbox("Ham Tien ward, Mui Ne, Vietnam")
        assert bbox == ["10.9", "11.0", "108.2", "108.3"]


# ───────────── (3) mixed-venue provider classification ───────────────────────
class TestMixedVenueClassification:
    def test_kitesurfing_surf_bar_is_a_provider(self):
        # The exact false-drop from LOCAL-835 (field): a kite provider that also
        # has a bar. Its name carries the compound "Kitesurfing" → provider.
        act = cmg.requested_activity(REQ)
        assert cmg.candidate_is_activity_provider(
            {"name": "Kitesurfing Mui Ne - Surf Bar",
             "_serper_category": "Bar"}, act) is True

    def test_dive_and_dine_is_a_provider_for_a_dive_request(self):
        act = cmg.requested_activity("Scuba diving courses in Nha Trang, Vietnam")
        assert cmg.candidate_is_activity_provider(
            {"name": "Dive & Dine", "_serper_category": "Restaurant"}, act) is True

    def test_blue_sky_restaurant_dropped(self):
        # No activity token in name or type → off-category (835B 'The Blue Sky
        # Restaurant' correct refusal is preserved).
        act = cmg.requested_activity(REQ)
        assert cmg.candidate_is_activity_provider(
            {"name": "Blue Sky Restaurant",
             "_serper_category": "Restaurant"}, act) is False

    def test_kite_bar_still_dropped(self):
        # "Kite Bar" carries only the bare short root "kite" + a bar head noun,
        # no provider noun, no "&" — still a bar. (LOCAL-835 invariant.)
        act = cmg.requested_activity(REQ)
        assert cmg.candidate_is_activity_provider(
            {"name": "Kite Bar", "_serper_category": "Bar"}, act) is False

    def test_the_bar_and_pogo_beach_bar_still_dropped(self):
        act = cmg.requested_activity(REQ)
        for name in ("The Bar", "Pogo Beach Bar"):
            assert cmg.candidate_is_activity_provider(
                {"name": name, "_serper_category": "Bar"}, act) is False

    def test_dive_bar_without_provider_noun_dropped(self):
        # A "Dive Bar" is a bar (idiom), short root + food head, no provider noun,
        # no "&" → off-category for a dive-courses request.
        act = cmg.requested_activity("Scuba diving courses in Nha Trang, Vietnam")
        assert cmg.candidate_is_activity_provider(
            {"name": "Dive Bar", "_serper_category": "Bar"}, act) is False

    def test_surf_school_bar_kept(self):
        # A short root + a provider noun ("school") with a bar is still a provider.
        act = cmg.requested_activity("Surf school in Da Nang, Vietnam")
        assert cmg.candidate_is_activity_provider(
            {"name": "Da Nang Surf School & Bar",
             "_serper_category": "Bar"}, act) is True

    def test_only_name_and_type_lacking_activity_is_off_category(self):
        # The ticket's rule: only a venue whose name AND type lack the activity is
        # off-category. A type that carries the activity keeps a food-named venue.
        act = cmg.requested_activity(REQ)
        assert cmg.candidate_is_activity_provider(
            {"name": "Jibe's", "_serper_category": "Kitesurfing school"},
            act) is True


# ───────────── full filter on the request's mixed field list ─────────────────
class TestFilterOnFieldList:
    def test_field_list_keeps_providers_drops_food(self):
        rows = [
            {"name": "Kitesurfing Mui Ne - Surf Bar", "_serper_category": "Bar"},
            {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"},
            {"name": "Jibe's Beach Club", "_serper_category": "Kitesurfing school"},
            {"name": "C2Sky Kitesurfing", "_serper_category": ""},
            {"name": "Blue Sky Restaurant", "_serper_category": "Restaurant"},
            {"name": "Kite Bar", "_serper_category": "Bar"},
        ]
        kept, dropped = cmg.filter_off_category_activity(
            rows, REQ, log=lambda *_: None)
        kept_names = [r["name"] for r in kept]
        assert "Kitesurfing Mui Ne - Surf Bar" in kept_names
        assert "Source Kiteboarding" in kept_names
        assert "Blue Sky Restaurant" not in kept_names
        assert "Kite Bar" not in kept_names
        # At least four providers survive (PASS bar for the live run).
        assert len(kept) >= 4
        assert dropped == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
