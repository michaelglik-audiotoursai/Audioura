#!/usr/bin/env python3
"""test_local805_near_landmark.py — LOCAL-805.

A request whose SUBJECT is a kind of business/activity provider must go to the
PLACES path whatever follows it ("near X", "around X", "close to X", "in X"), and
the landmark X is the SEARCH CENTRE (geocoded, ~1.5 km walkable radius), never a
stop. The regression (since 788B/790/791): "Massage and spa near Ben Thanh Market,
District 1, Ho Chi Minh City" classified as a WALKING tour because the generic
walking-keyword scan saw "District"/"City" and fired before the business check, so
the places path never ran and the real spas were lost.

Pure, offline, deterministic (no network, no model, no DB). Run with:

    python3 -m pytest tests/test_local805_near_landmark.py -q

Covers the exact ticket strings:
  * "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City"
  * "coffee near Boston Common"
  * "seafood restaurants around Mui Ne fishing village"
  * "gyms near me, West Roxbury"   (near-me unchanged)
  * "walk near Ben Thanh Market"   (a WALKING request stays walking)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402
import places_search as ps  # noqa: E402


# ─────────────────── 1. ROUTING — business subject → places path ─────────────
class TestRoutingBusinessSubjectGoesToPlaces:
    """`_classify_tour_category` returns 'restaurant' (the maps-first/places
    category dining and business share) for a business/activity SUBJECT, whatever
    locative phrase follows it — and NOT 'walking'."""

    def test_massage_spa_near_ben_thanh_market(self):
        # THE field defect: "District"/"City" in the tail must not steal it.
        assert gtt._classify_tour_category(
            "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City",
            "") == "restaurant"

    def test_coffee_near_boston_common(self):
        assert gtt._classify_tour_category("coffee near Boston Common", "") == "restaurant"

    def test_seafood_restaurants_around_fishing_village(self):
        assert gtt._classify_tour_category(
            "seafood restaurants around Mui Ne fishing village", "") == "restaurant"

    def test_gyms_near_me_west_roxbury_unchanged(self):
        # near-me still routes to places (LOCAL-788B behaviour preserved).
        assert gtt._classify_tour_category("gyms near me, West Roxbury", "") == "restaurant"

    @pytest.mark.parametrize("req", [
        "bars near Fenway Park, Boston",
        "cafes close to the Louvre, Paris",
        "spas around the Grand Palace, Bangkok",
        "bakeries next to Union Square, San Francisco",
    ])
    def test_landmark_name_keyword_does_not_mislead(self, req):
        # "Park"/"Palace"/"Square" inside the LANDMARK name must not flip the
        # request to walking/specialized/museum — the SUBJECT is a business.
        assert gtt._classify_tour_category(req, "") == "restaurant"


class TestRoutingWalkingStaysWalking:
    """A genuine WALKING request near the SAME landmark stays walking — the
    business word is inside the landmark name, not the subject."""

    def test_walk_near_ben_thanh_market_stays_walking(self):
        assert gtt._classify_tour_category("walk near Ben Thanh Market", "") == "walking"

    @pytest.mark.parametrize("req", [
        "stroll around the Old Market Square, Nottingham",
        "walking tour around Cimiez District, Nice",
        "Boston Freedom Trail walking tour, Boston MA",
        "French colonial architecture, District 1 and 3, Ho Chi Minh City",
        "Pagodas and temples of Ho Chi Minh City",
    ])
    def test_walking_and_area_requests_unchanged(self, req):
        assert gtt._classify_tour_category(req, "") == "walking"

    def test_museum_and_specialized_subjects_unchanged(self):
        assert gtt._classify_tour_category("art center in Cambridge", "") == "museum"
        assert gtt._classify_tour_category("MFA, Boston", "") == "museum"
        assert gtt._classify_tour_category("botanical garden in Boston", "") == "specialized"

    def test_kitesurfing_schools_still_places(self):
        # LOCAL-791 defect 2 preserved.
        assert gtt._classify_tour_category(
            "Kitesurfing schools in Mui Ne, Vietnam", "") == "restaurant"


# ─────────────────── 2. SUBJECT helper (the keying primitive) ────────────────
class TestBusinessSubjectHelper:
    def test_business_subject_true(self):
        assert gtt._business_subject_of_request(
            "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City") is True
        assert gtt._business_subject_of_request("coffee near Boston Common") is True
        assert gtt._business_subject_of_request("gyms near me, West Roxbury") is True

    def test_walking_verb_subject_false(self):
        # The business word ("market") is only in the landmark; subject is "walk".
        assert gtt._business_subject_of_request("walk near Ben Thanh Market") is False
        assert gtt._business_subject_of_request("stroll around the Night Market") is False

    def test_landmark_only_subject_false(self):
        # A pure non-commercial landmark name has no business subject.
        assert gtt._business_subject_of_request("Boston Common") is False
        assert gtt._business_subject_of_request("Notre-Dame Cathedral") is False
        # Note: a bare "Ben Thanh Market" IS a market (a commercial place), so it
        # legitimately classes as business on its own — the near-landmark guard
        # keys on the subject BEFORE the connector, so "walk near Ben Thanh Market"
        # is still correctly walking (covered in test_walking_verb_subject_false).


# ─────────────────── 3. SCOPE — landmark is the search centre ────────────────
class TestScopeIsTheLandmark:
    """The deterministic `_scope_from_request` fallback returns the LANDMARK (the
    search centre) for a "<business> near <landmark>" request — the business words
    and the connector are dropped, the landmark (and any city tail) is kept."""

    def test_ben_thanh_market_is_the_centre(self):
        scope = gtt._scope_from_request(
            "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City", None)
        assert scope.startswith("Ben Thanh Market")
        assert "massage" not in scope.lower()
        assert "spa" not in scope.lower()
        assert "Ho Chi Minh City" in scope

    def test_boston_common_is_the_centre(self):
        assert gtt._scope_from_request("coffee near Boston Common", None) == "Boston Common"

    def test_fishing_village_is_the_centre(self):
        assert gtt._scope_from_request(
            "seafood restaurants around Mui Ne fishing village", None) == "Mui Ne fishing village"

    def test_near_me_unchanged(self):
        # "near me" has no landmark — the device-coordinate path still resolves the
        # trailing locality, not a landmark.
        assert gtt._scope_from_request("gyms near me, West Roxbury", None) == "West Roxbury"

    def test_walk_request_scope_untouched(self):
        # Not a business subject → no landmark-centre rewrite.
        assert gtt._scope_from_request(
            "walk near Ben Thanh Market", None) == "walk near Ben Thanh Market"


# ─────────────────── 4. LANDMARK is never a STOP ─────────────────────────────
class TestLandmarkIsNotAStop:
    """A "near <landmark>" request does NOT register the landmark as a named-place
    stop — "near"/"around" is not a named-stop clause (unlike "including X")."""

    @pytest.mark.parametrize("req", [
        "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City",
        "coffee near Boston Common",
        "seafood restaurants around Mui Ne fishing village",
    ])
    def test_no_named_place_extracted(self, req):
        import area_resolver as ar
        assert ar.extract_named_places_from_clause(req) == []

    @pytest.mark.parametrize("req", [
        "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City",
        "coffee near Boston Common",
    ])
    def test_no_named_anchor_extracted(self, req):
        assert gtt.named_anchors(req)["anchors"] == []


# ─────────────────── 5. RADIUS — ~1.5 km walkable, ×2 widen ──────────────────
class TestLandmarkRadius:
    def test_landmark_precision_and_radius(self):
        assert ps._scope_precision("Ben Thanh Market, District 1, Ho Chi Minh City") == "LANDMARK"
        assert ps._scope_precision("Boston Common") == "LANDMARK"
        assert ps._radius_for_precision("LANDMARK") == pytest.approx(1.5)

    def test_widen_x2_once_reaches_3km(self):
        import local802_relevance_gate as l802
        widened = l802.widen_radius_km(ps._LANDMARK_RADIUS_KM, factor=2.0)
        assert widened == pytest.approx(3.0)

    def test_known_neighbourhood_not_misread_as_landmark(self):
        # A residential neighbourhood that ends in a landmark-class word
        # ("Hyde Park") stays NEIGHBOURHOOD — the neighbourhood markers win.
        assert ps._scope_precision("Hyde Park") == "NEIGHBOURHOOD"
        assert ps._scope_precision("West Roxbury, MA") == "NEIGHBOURHOOD"


# ─────────────────── 6. CONTAINMENT scope is the AREA, not the landmark ──────
class TestContainmentScopeIsTheArea:
    """The field defect (tour 469): scope-memory rejected every nearby spa because
    the containment scope was the landmark BUILDING ("Ben Thanh Market"), so a spa
    "near but not inside the market" was dropped. For a business-near-landmark
    request the containment scope is the ENCLOSING AREA; the landmark is only the
    search centre. `_near_landmark_enclosing_area` is the primitive that decides it."""

    def test_enclosing_area_is_the_admin_tail(self):
        assert gtt._near_landmark_enclosing_area(
            "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City"
        ) == "District 1, Ho Chi Minh City"

    def test_no_enclosing_area_means_radius_only(self):
        # "coffee near Boston Common" has no admin tail — the containment check is
        # skipped (empty string) and the ~1.5 km radius stands on its own.
        assert gtt._near_landmark_enclosing_area("coffee near Boston Common") == ""
        assert gtt._near_landmark_enclosing_area(
            "seafood restaurants around Mui Ne fishing village") == ""

    def test_walking_request_not_touched(self):
        # Not a business subject → the helper returns None (no correction).
        assert gtt._near_landmark_enclosing_area("walk near Ben Thanh Market") is None

    def test_near_me_keeps_the_locality(self):
        assert gtt._near_landmark_enclosing_area("gyms near me, West Roxbury") == "West Roxbury"

    def test_resolve_scope_widens_landmark_to_area(self):
        # The containment-scope resolver replaces a landmark geographic_scope with
        # the enclosing area for a business-near-landmark request.
        intent = {
            "geographic_scope": "Ben Thanh Market, District 1, Ho Chi Minh City",
            "scope_precision": "DISTRICT",
        }
        scope = gtt._resolve_scope_for_check(
            intent,
            "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City",
            "restaurant", None, quiet=True)
        # The landmark name must NOT be the containment scope; the area must be.
        assert "ben thanh market" not in scope.lower()
        assert "district 1" in scope.lower()

    def test_resolve_scope_point_landmark_has_no_boundary(self):
        # "coffee near Boston Common" — no enclosing area, so the stop-by-stop
        # containment check is skipped (empty scope), leaving the radius to bound it.
        intent = {
            "geographic_scope": "Boston Common, Boston, MA",
            "scope_precision": "DISTRICT",
        }
        scope = gtt._resolve_scope_for_check(
            intent, "coffee near Boston Common", "restaurant", None, quiet=True)
        assert scope == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
