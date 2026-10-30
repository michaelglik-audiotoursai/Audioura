#!/usr/bin/env python3
"""test_local838_walk_beats_805.py — LOCAL-838.

An explicit app tour_type (walking/driving/biking/museum…) OR a walking word in
the request (walk, walking tour, stroll, promenade, wander, in en/vi/fr/de/es/ru)
must BEAT the LOCAL-805 business-subject routing.

Field defect (GCloud_Storied wave 14 proof, gen 00020-2q6 @ ce18fca3, cheap env):
  request "Ben Thanh Market walk, Ho Chi Minh City – proof" with tour_type=walking
  → LOCAL-805's business/near-landmark routing classified the SUBJECT ("Ben Thanh
    Market": a market, so a business) and sent the request down the PLACES path as
    category='restaurant', OVERRIDING the app's explicit walking type. LOCAL-836's
    walkable-area widening never ran, so the tour shipped 2/4 (a market plus a
    Bánh Bèo stall).

805 still owns a request whose SUBJECT asks for businesses with NO walking signal
("coffee near Ben Thanh Market", "spas near X", "kite schools") — those carry
neither an explicit walking tour_type nor a walking word.

Pure, offline, deterministic (no network, no model, no DB). Run with:

    python3 -m pytest tests/test_local838_walk_beats_805.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402


# ─────────────────── 1. THE TICKET STRINGS — classifier precedence ──────────
class TestTicketStrings:
    """The exact strings named in the LOCAL-838 Do item 2."""

    def test_ben_thanh_market_walk_hcmc_is_walking(self):
        # "walk" word in the request beats 805 even with empty tour_type.
        assert gtt._classify_tour_category("Ben Thanh Market walk, HCMC", "") == "walking"

    def test_ben_thanh_market_walking_tour_hcmc_is_walking(self):
        assert gtt._classify_tour_category(
            "Ben Thanh Market walking tour, HCMC", "") == "walking"

    def test_walk_around_dong_xuan_market_hanoi_is_walking(self):
        assert gtt._classify_tour_category(
            "walk around Dong Xuan Market, Hanoi", "") == "walking"

    def test_coffee_near_ben_thanh_market_stays_places(self):
        # No walking signal → 805 still owns it (the places/restaurant path).
        assert gtt._classify_tour_category(
            "coffee near Ben Thanh Market", "") == "restaurant"

    def test_ben_thanh_market_with_walking_tour_type_is_walking(self):
        # THE field defect: explicit app tour_type=walking beats the market
        # being a business subject.
        assert gtt._classify_tour_category("Ben Thanh Market", "walking") == "walking"

    def test_ben_thanh_market_walk_with_walking_tour_type_is_walking(self):
        # The full field request: walking word AND explicit tour_type.
        assert gtt._classify_tour_category(
            "Ben Thanh Market walk, Ho Chi Minh City", "walking") == "walking"


# ─────────────────── 2. EXPLICIT APP tour_type beats 805 ─────────────────────
class TestExplicitTourTypeBeats805:
    """A business-subject location that arrives WITH an explicit app tour_type
    for an on-itinerary mode is routed by that type, not by 805."""

    @pytest.mark.parametrize("tt", ["walking", "driving", "biking", "cycling"])
    def test_business_subject_location_with_explicit_mode_is_walking(self, tt):
        # Even "Ben Thanh Market" (a market → business subject) honours the mode.
        assert gtt._classify_tour_category("Ben Thanh Market", tt) == "walking"

    def test_no_tour_type_business_subject_still_places(self):
        # Control: with NO explicit mode and NO walking word, 805 owns it.
        assert gtt._classify_tour_category("Ben Thanh Market", "") == "restaurant"

    def test_helper_true_for_explicit_mode(self):
        assert gtt._request_has_walking_signal("Ben Thanh Market", "walking") is True
        assert gtt._request_has_walking_signal("Ben Thanh Market", "driving") is True

    def test_helper_false_for_business_only(self):
        assert gtt._request_has_walking_signal("coffee near Ben Thanh Market", "") is False
        assert gtt._request_has_walking_signal("Ben Thanh Market", "") is False
        assert gtt._request_has_walking_signal("Ben Thanh Market", "restaurant") is False


# ─────────────────── 3. WALKING WORD in six languages beats 805 ──────────────
class TestMultilingualWalkingWord:
    """A walking word anywhere in the request text (en/vi/fr/de/es/ru) keeps the
    request on the walking path even when its subject is a market/business."""

    @pytest.mark.parametrize("req", [
        "Ben Thanh Market walk, Ho Chi Minh City",          # en: walk
        "stroll around Ben Thanh Market, HCMC",             # en: stroll
        "promenade near Ben Thanh Market, HCMC",            # en/fr: promenade
        "wander the lanes by Ben Thanh Market, HCMC",       # en: wander
        "đi bộ quanh chợ Bến Thành, HCMC",                  # vi: đi bộ (walk)
        "dạo quanh chợ Bến Thành, HCMC",                    # vi: dạo (stroll)
        "balade autour du marché Ben Thanh, HCMC",          # fr: balade
        "Spaziergang um den Ben-Thanh-Markt, HCMC",         # de: spaziergang
        "paseo por el mercado Ben Thanh, HCMC",             # es: paseo
        "прогулка вокруг рынка Бен Тхань, HCMC",            # ru: прогулка
    ])
    def test_walking_word_beats_business_subject(self, req):
        assert gtt._classify_tour_category(req, "") == "walking"

    def test_walking_word_in_tour_type_field_also_counts(self):
        # Some callers put the mode word in tour_type as free text.
        assert gtt._classify_tour_category("Ben Thanh Market", "stroll") == "walking"


# ─────────────────── 4. 805 STILL OWNS a pure business request ───────────────
class TestBusinessRequestsStayPlaces:
    """No explicit mode, no walking word → the LOCAL-805/791 business-subject
    routing is unchanged (regression guard)."""

    @pytest.mark.parametrize("req", [
        "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City",
        "coffee near Ben Thanh Market",
        "coffee near Boston Common",
        "seafood restaurants around Mui Ne fishing village",
        "gyms near me, West Roxbury",
        "bars near Fenway Park, Boston",
        "cafes close to the Louvre, Paris",
        "Kitesurfing schools in Mui Ne, Vietnam",
    ])
    def test_business_subject_still_places(self, req):
        assert gtt._classify_tour_category(req, "") == "restaurant"


# ─────────────────── 5. REGRESSIONS — 805/805B/830/835/836 strings ──────────
class TestNeighbouringTicketsUnchanged:
    """Strings pinned by 805/805B/830/835/836 still classify as before — the
    LOCAL-838 guard is narrow and must not move any of them."""

    def test_805_walking_requests_still_walking(self):
        # These already carried a walking word/phrase; stay walking.
        assert gtt._classify_tour_category("walk near Ben Thanh Market", "") == "walking"
        assert gtt._classify_tour_category(
            "stroll around the Old Market Square, Nottingham", "") == "walking"
        assert gtt._classify_tour_category(
            "walking tour around Cimiez District, Nice", "") == "walking"
        assert gtt._classify_tour_category(
            "Boston Freedom Trail walking tour, Boston MA", "") == "walking"

    def test_805_area_and_category_requests_unchanged(self):
        # No walking word, no business subject → routed by the area/category scans.
        assert gtt._classify_tour_category(
            "French colonial architecture, District 1 and 3, Ho Chi Minh City", "") == "walking"
        assert gtt._classify_tour_category(
            "Pagodas and temples of Ho Chi Minh City", "") == "walking"

    def test_805_museum_specialized_subjects_unchanged(self):
        assert gtt._classify_tour_category("art center in Cambridge", "") == "museum"
        assert gtt._classify_tour_category("MFA, Boston", "") == "museum"
        assert gtt._classify_tour_category("botanical garden in Boston", "") == "specialized"

    def test_836_single_anchor_walking_tour_still_walking(self):
        # LOCAL-836's canonical string — a named-anchor WALKING tour.
        assert gtt._classify_tour_category(
            "Ben Thanh Market walking tour, Ho Chi Minh City", "") == "walking"

    def test_facility_still_wins_over_walk_word(self):
        # LOCAL-480: a facility errand is NOT a sightseeing walk. The facility
        # detector sits ABOVE the LOCAL-838 guard, so "Walking tour around Logan
        # Airport" stays 'facility' (a walk word does not demote it).
        assert gtt._classify_tour_category(
            "Walking tour around Logan Airport", "") == "facility"

    def test_restaurant_keyword_subject_unchanged(self):
        # An explicit dining subject is still 'restaurant' (food keywords sit
        # above the LOCAL-838 guard). A walk word does not turn a food tour into
        # a place-walk.
        assert gtt._classify_tour_category("restaurant tour, Hanoi", "") == "restaurant"


# ─────────────────── 6. CALL-SITE: explicit walking tour_type survives ───────
class TestCallSiteSuppressionGuard:
    """The generate_tour_text impl suppresses tour_type ('Touchpoint 1') when the
    pre-category is restaurant/specialized/facility. LOCAL-838 must EXEMPT an
    explicit walking signal from that suppression, else _pre_category=='restaurant'
    (the market subject) blanks the walking type before the classifier sees it.
    This pins the source of the exemption so the regression cannot silently return.
    """

    def test_suppression_exempts_walking_signal(self):
        import inspect
        src = inspect.getsource(gtt._generate_tour_text_impl)
        # The exemption references the LOCAL-838 helper in the _effective_tour_type
        # computation (both the intent-ok and fallback branches).
        assert "_request_has_walking_signal(location, tour_type)" in src
        assert src.count("_request_has_walking_signal(location, tour_type)") >= 2


# ─────────────────── 7. SCOPE WIDENING — "<feature> walk" resolves its area ──
class TestWalkFormWidensToArea:
    """The second half of the field defect: once the request is classified
    'walking', the trailing verb "walk" (no "tour" keyword) must NOT block
    LOCAL-836's single-anchor walkable-area widening. Before the fix
    _leading_anchor_list saw no "tour" separator, returned [], the market point
    stayed the containment scope, and every real nearby District-1 landmark was
    rejected — the tour shipped 2/4. _TRAILING_WALK_VERB_RE restores the anchor."""

    def test_leading_anchor_list_recognises_trailing_walk(self):
        anchors, city = gtt._leading_anchor_list("Ben Thanh Market walk, Ho Chi Minh City")
        assert anchors == ["Ben Thanh Market"]
        assert city == "Ho Chi Minh City"

    def test_leading_anchor_list_recognises_trailing_stroll(self):
        anchors, city = gtt._leading_anchor_list("Hoan Kiem Lake stroll, Hanoi")
        assert anchors == ["Hoan Kiem Lake"]
        assert city == "Hanoi"

    def test_leading_verb_is_not_a_trailing_separator(self):
        # "walk near X" — the verb LEADS the subject, not trails the anchor.
        assert gtt._leading_anchor_list("walk near Ben Thanh Market") == ([], None)
        assert gtt._leading_anchor_list("coffee near Ben Thanh Market") == ([], None)

    def test_walking_tour_form_still_recognised(self):
        # Regression: the "walking tour" keyword path (LOCAL-816/836) is unchanged.
        anchors, city = gtt._leading_anchor_list(
            "Ben Thanh Market walking tour, Ho Chi Minh City")
        assert anchors == ["Ben Thanh Market"]
        assert city == "Ho Chi Minh City"

    def test_single_anchor_area_widens_for_walk_form_district(self):
        # DISTRICT intent → the admin tail is the enclosing area.
        area = gtt._single_anchor_enclosing_area(
            "Ben Thanh Market, District 1, Ho Chi Minh City",
            "Ben Thanh Market walk, Ho Chi Minh City",
            {"scope_precision": "DISTRICT"})
        assert area == "District 1, Ho Chi Minh City"

    def test_single_anchor_area_widens_for_walk_form_building(self):
        # BUILDING intent (bare anchor) → the city the request names.
        area = gtt._single_anchor_enclosing_area(
            "Ben Thanh Market",
            "Ben Thanh Market walk, Ho Chi Minh City",
            {"scope_precision": "BUILDING"})
        assert area == "Ho Chi Minh City"

    def test_transport_strip_removes_orphan_walk_verb(self):
        # Area resolution must not keep the orphan "walk" ("Ben Thanh Market walk"
        # had no Wikidata match and poisoned resolution). Intent still sees the
        # original request (D536); only the normalized area string is stripped.
        stripped = gtt._TRANSPORT_STRIP_RE.sub(
            "", "Ben Thanh Market walk, Ho Chi Minh City")
        assert "walk" not in stripped.lower()
        assert "Ben Thanh Market" in stripped


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
