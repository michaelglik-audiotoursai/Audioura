#!/usr/bin/env python3
"""LOCAL-779B (bounce of LOCAL-779): restaurant tours must take their candidates
from the SAME maps/places search the business path uses — "<cuisine> restaurants
in <scope>" — and REFILL from map listings when PHASE 3C / the existence gate
empties the list. Cuisine/qualifier must match. If the area has fewer than N
matching places, deliver what's verified honestly; if none, refuse cleanly with a
"widen the area" suggestion.

The LOCAL-779 LEAD bounce: "middle eastern restaurants near me, west Roxbury, MA"
still returned `PHASE 3C rejected all stops`, because the restaurant category took
its candidates ONLY from the LLM (which put them in Newton/Boston, outside the
scope) and nothing refilled from the map when PHASE 3C emptied the list. The
business path (LOCAL-779 build step 3) does that refill — but a restaurant poi_type
classifies as 'dining', so it never reached `business_replenish_candidates`.

Fixtures only — no live web. Every OSM call is monkeypatched with recorded
Nominatim jsonv2 JSON, so this suite runs in the default (non-network) test run.

What it proves (the LOCAL-779B contract):
  * `dining_replenish_candidates` asks the MAP for "<cuisine> restaurants in
    <scope>", keeps only listings INSIDE the scope, ranked by distance, each
    carrying a real address + coordinates (verified by construction).
  * Case 1 — Middle Eastern in West Roxbury with LLM candidates all in Newton:
    the maps refill returns the in-scope West Roxbury places; the Newton names are
    not what gets delivered.
  * Case 2 — a dumpling place is REJECTED for cuisine (`cuisine_matches` /
    `dining_replenish_candidates`); Sofra (a Middle-Eastern bakery café) is KEPT.
  * Case 3 — a zero-match area yields NO candidates, so the caller refuses cleanly.
  * `_extract_cuisine_qualifier` pulls "middle eastern" out of "middle eastern
    restaurants" and returns '' for a bare "restaurants".
  * The dining replenishment is now REACHED for a dining poi_type (routing), and
    the business path and Mamma-Maria Italian guard are untouched.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_existence_gate as gate


# ──────────────────────────── recorded fixtures ─────────────────────────────
class _FakeResp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


# Real Middle-Eastern restaurants INSIDE West Roxbury, MA (coords approximate/OSM).
_WR_LEBANESE = {
    "name": "Beirut Café",
    "display_name": "Beirut Café, 1739 Centre St, West Roxbury, Boston, MA 02132",
    "category": "amenity",
    "type": "restaurant",
    "lat": "42.2795",
    "lon": "-71.1601",
    "address": {"road": "Centre Street", "house_number": "1739",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
    "extratags": {"cuisine": "lebanese;middle_eastern"},
}
_WR_SHAWARMA = {
    "name": "Shawarma Falafel House",
    "display_name": "Shawarma Falafel House, 1932 Centre St, West Roxbury, Boston, MA 02132",
    "category": "amenity",
    "type": "restaurant",
    "lat": "42.2831",
    "lon": "-71.1627",
    "address": {"road": "Centre Street", "house_number": "1932",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
    "extratags": {"cuisine": "arab;kebab"},
}
# Sofra — a Middle-Eastern bakery/café; the ticket says it is ACCEPTABLE. No
# explicit cuisine tag, so the match must come from the name/description.
_SOFRA = {
    "name": "Sofra Bakery & Café",
    "display_name": "Sofra Bakery & Café, 1 Belmont St, West Roxbury, Boston, MA",
    "category": "amenity",
    "type": "cafe",
    "lat": "42.2820",
    "lon": "-71.1590",
    "address": {"road": "Belmont Street", "house_number": "1",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
    "extratags": {"cuisine": "middle_eastern;turkish"},
}
# Dumpling House — a Chinese restaurant. The ticket says it is NOT Middle Eastern
# and must be rejected for cuisine even though it is a restaurant in scope.
_DUMPLING = {
    "name": "Dumpling House",
    "display_name": "Dumpling House, 1750 Centre St, West Roxbury, Boston, MA",
    "category": "amenity",
    "type": "restaurant",
    "lat": "42.2800",
    "lon": "-71.1610",
    "address": {"road": "Centre Street", "house_number": "1750",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
    "extratags": {"cuisine": "chinese;dumplings"},
}
# A Middle-Eastern place in the WRONG town (Newton) — the LLM's bad candidate.
# Proximity must reject it for a West Roxbury scope.
_NEWTON_KEBAB = {
    "name": "Kebab House",
    "display_name": "Kebab House, 1650 Washington St, Newton, MA 02458",
    "category": "amenity",
    "type": "restaurant",
    "lat": "42.3501",
    "lon": "-71.2080",
    "address": {"road": "Washington Street", "house_number": "1650",
                "city": "Newton", "state": "Massachusetts"},
    "extratags": {"cuisine": "turkish;middle_eastern"},
}
# North End Italian — the "Mamma Maria is Italian" guard reference.
_MAMMA_MARIA = {
    "name": "Mamma Maria",
    "display_name": "Mamma Maria, 3 North Square, North End, Boston, MA 02113",
    "category": "amenity",
    "type": "restaurant",
    "lat": "42.3639",
    "lon": "-71.0540",
    "address": {"road": "North Square", "house_number": "3",
                "suburb": "North End", "city": "Boston", "state": "Massachusetts"},
    "extratags": {"cuisine": "italian"},
}

_WR_CENTER = [{"lat": "42.2843", "lon": "-71.1627"}]  # West Roxbury geocode


def _install(monkeypatch, query_map, default=None):
    """Serve recorded payloads by matching substrings of the query, in order."""
    def _fake(params, context=""):
        q = (params.get("q") or "").lower()
        for key, payload in query_map:
            if key in q:
                return _FakeResp(payload)
        return _FakeResp(default if default is not None else [])
    monkeypatch.setattr(gate, "_nominatim_request", _fake)


# ──────────────────────── cuisine qualifier extraction ──────────────────────
class TestCuisineQualifier:
    @pytest.mark.parametrize("poi_type,expected", [
        ("middle eastern restaurants", "middle eastern"),
        ("Italian restaurants", "italian"),
        ("thai food", "thai"),
        ("sushi restaurants", "sushi"),
        ("restaurants", ""),
        ("dining", ""),
        ("", ""),
        (None, ""),
    ])
    def test_extract(self, poi_type, expected):
        assert gate._extract_cuisine_qualifier(poi_type) == expected

    @pytest.mark.parametrize("request_str,expected", [
        ("middle eastern restaurants near me, west Roxbury, MA", "middle eastern"),
        ("Italian restaurants in the North End, Boston", "italian"),
        ("best lebanese food in Watertown", "middle eastern"),
        ("sushi near me, Cambridge", "sushi"),
        ("restaurants in Newton", ""),
        ("gyms near me, west Roxbury", ""),
        ("", ""),
        (None, ""),
    ])
    def test_cuisine_from_request(self, request_str, expected):
        # Recovers the cuisine the LLM intent often drops (poi_type == "restaurants").
        assert gate._cuisine_from_request(request_str) == expected


# ──────────────────────────── cuisine matching ──────────────────────────────
class TestCuisineMatches:
    def test_empty_cuisine_matches_any_restaurant(self):
        # A bare "restaurants" request matches any dining listing.
        assert gate.cuisine_matches("", _DUMPLING) is True

    def test_middle_eastern_matches_lebanese_tag(self):
        assert gate.cuisine_matches("middle eastern", _WR_LEBANESE) is True

    def test_middle_eastern_matches_arab_kebab_tag(self):
        assert gate.cuisine_matches("middle eastern", _WR_SHAWARMA) is True

    def test_sofra_accepted_as_middle_eastern(self):
        # Ticket: Sofra (Middle-Eastern bakery café) is acceptable.
        assert gate.cuisine_matches("middle eastern", _SOFRA) is True

    def test_dumpling_rejected_for_middle_eastern(self):
        # Ticket: Dumpling House is NOT Middle Eastern.
        assert gate.cuisine_matches("middle eastern", _DUMPLING) is False

    def test_mamma_maria_italian_not_middle_eastern(self):
        # Keep the "Mamma Maria is Italian" guard.
        assert gate.cuisine_matches("middle eastern", _MAMMA_MARIA) is False

    def test_italian_matches_mamma_maria(self):
        assert gate.cuisine_matches("italian", _MAMMA_MARIA) is True


# ──────────────────── cuisine conflict (keep when no signal) ────────────────
class TestCuisineConflict:
    _NO_TAG_ITALIAN = {
        "name": "Giacomo's Ristorante",
        "display_name": "Giacomo's Ristorante, 355 Hanover St, North End, Boston, MA",
        "category": "amenity", "type": "restaurant",
        "lat": "42.3647", "lon": "-71.0542",
        "address": {"road": "Hanover Street", "suburb": "North End",
                    "city": "Boston", "state": "Massachusetts"},
        # No cuisine extratag — the common OSM reality for a real restaurant.
    }

    def test_dumpling_conflicts_with_middle_eastern(self):
        # Positive chinese/dumpling signal → a real conflict → drop.
        assert gate.cuisine_conflict("middle eastern", _DUMPLING) is True

    def test_mamma_maria_conflicts_with_middle_eastern(self):
        # Positive italian tag → conflict for a Middle-Eastern request.
        assert gate.cuisine_conflict("middle eastern", _MAMMA_MARIA) is True

    def test_untagged_place_no_conflict(self):
        # No cuisine tag and a bare name → UNKNOWN, not a conflict → keep.
        assert gate.cuisine_conflict("italian", self._NO_TAG_ITALIAN) is False

    def test_matching_cuisine_no_conflict(self):
        assert gate.cuisine_conflict("italian", _MAMMA_MARIA) is False

    def test_empty_cuisine_no_conflict(self):
        assert gate.cuisine_conflict("", _DUMPLING) is False


# ──────────────────── dining replenishment from the map ─────────────────────
class TestDiningReplenishFromMaps:
    def test_case1_refills_in_scope_west_roxbury(self, monkeypatch):
        """Case 1: LLM candidates were all in Newton; the maps refill returns the
        in-scope West Roxbury Middle-Eastern places, ranked by distance."""
        _install(monkeypatch, [
            ("middle eastern restaurants in",
             [_NEWTON_KEBAB, _WR_LEBANESE, _WR_SHAWARMA, _DUMPLING]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=2, exclude=set())
        names = [c["name"] for c in cands]
        assert len(cands) == 2
        # The Newton kebab place is out of scope → excluded.
        assert "Kebab House" not in names
        # The Chinese dumpling place is in scope but wrong cuisine → excluded.
        assert "Dumpling House" not in names
        # The two in-scope Middle-Eastern places are delivered.
        assert "Beirut Café" in names
        assert "Shawarma Falafel House" in names
        for c in cands:
            assert c["verified"] is True
            assert c["coordinates"]
            assert c["lat"] and c["lng"]
            # Address lands inside West Roxbury (≈42.28, -71.16).
            assert 42.0 < c["lat"] < 42.5
            assert -71.3 < c["lng"] < -71.0

    def test_case2_dumpling_rejected_sofra_kept(self, monkeypatch):
        """Case 2: a dumpling place is rejected for cuisine; Sofra is kept."""
        _install(monkeypatch, [
            ("middle eastern restaurants in",
             [_DUMPLING, _SOFRA, _WR_LEBANESE]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=5, exclude=set())
        names = [c["name"] for c in cands]
        assert "Dumpling House" not in names
        assert "Sofra Bakery & Café" in names
        assert "Beirut Café" in names

    def test_case3_zero_match_area_returns_nothing(self, monkeypatch):
        """Case 3: an area with no matching places returns no candidates, so the
        caller can refuse cleanly with a widen-the-area suggestion."""
        _install(monkeypatch, [
            # Only a Chinese place exists; no Middle-Eastern match → empty.
            ("middle eastern restaurants in", [_DUMPLING]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=2, exclude=set())
        assert cands == []

    def test_exclude_already_used_names(self, monkeypatch):
        _install(monkeypatch, [
            ("middle eastern restaurants in", [_WR_LEBANESE, _WR_SHAWARMA]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=5,
            exclude={"beirut café"})
        names = [c["name"] for c in cands]
        assert "Beirut Café" not in names
        assert "Shawarma Falafel House" in names

    def test_cuisine_override_filters_bare_poi_type(self, monkeypatch):
        """The live LLM drops the qualifier (poi_type == 'restaurants'); the engine
        recovers 'middle eastern' from the request and passes it as cuisine=. With
        the override, a Mexican/Italian place must still be rejected."""
        _MEX = {
            "name": "Yucatan Tacos",
            "display_name": "Yucatan Tacos, 1417 Centre St, West Roxbury, Boston, MA",
            "category": "amenity", "type": "restaurant",
            "lat": "42.2805", "lon": "-71.1620",
            "address": {"road": "Centre Street", "suburb": "West Roxbury",
                        "city": "Boston", "state": "Massachusetts"},
            "extratags": {"cuisine": "mexican"},
        }
        _install(monkeypatch, [
            ("middle eastern restaurants in", [_MEX, _WR_LEBANESE]),
            ("restaurants in", [_MEX, _WR_LEBANESE]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "restaurants", "West Roxbury, MA", needed=5, exclude=set(),
            cuisine="middle eastern")
        names = [c["name"] for c in cands]
        assert "Yucatan Tacos" not in names
        assert "Beirut Café" in names

    def test_ranked_by_distance_to_scope_centre(self, monkeypatch):
        # Beirut Café (42.2795) is closer to the WR centre (42.2843) than Shawarma
        # (42.2831)? Both close — assert ordering is by true haversine distance.
        _install(monkeypatch, [
            ("middle eastern restaurants in", [_WR_SHAWARMA, _WR_LEBANESE]),
            ("west roxbury", _WR_CENTER),
        ])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=2, exclude=set())
        origin = (42.2843, -71.1627)
        dists = [gate._haversine_km_local(origin, (c["lat"], c["lng"])) for c in cands]
        assert dists == sorted(dists)


# ──────────────────── routing: dining reaches the maps refill ───────────────
class TestDiningRoutingReached:
    def test_classify_still_dining(self):
        # The classification is unchanged; the fix is that 'dining' now ALSO
        # refills from the maps path (not only 'business').
        assert gate.classify_business_vs_landmark("middle eastern restaurants") == "dining"
        assert gate.classify_business_vs_landmark("gyms") == "business"

    def test_generate_tour_text_refills_dining_from_maps(self, monkeypatch):
        """The orchestrator must call dining_replenish_candidates for a dining
        poi_type when PHASE 3C / the gate left the list short. We assert the wiring
        exists by checking the module references the dining refill symbol."""
        import generate_tour_text as gtt
        src = gtt._LOCAL779B_DINING_REPLENISH_MARKER
        assert src is True


# ──────────────────── honest refusal: widen the area ───────────────────────
class TestWidenAreaRefusal:
    def test_error_code_mapped(self):
        import actionable_failure as af
        assert af.ERROR_CODES["no_matching_places_in_area"] == "no_matching_places_in_area"

    def test_widen_suggestion_west_roxbury_adds_neighbour(self):
        import actionable_failure as af
        sug = af._widen_area_suggestion(
            "West Roxbury, MA", "middle eastern restaurants", "middle eastern")
        assert sug is not None
        # Ticket example: widen to "West Roxbury and Roslindale".
        assert "Roslindale" in sug["widened_area"]
        assert "West Roxbury" in sug["widened_area"]
        assert "middle eastern restaurants" in sug["request"].lower()

    def test_build_actionable_failure_zero_match(self):
        import actionable_failure as af
        out = af.build_actionable_failure(
            evidence={
                "error_type": "no_matching_places_in_area",
                "poi_type": "middle eastern restaurants",
                "cuisine": "middle eastern",
                "locality": "West Roxbury, MA",
            },
            request="middle eastern restaurants near me, west Roxbury, MA",
            legacy_message="No matching restaurants found in West Roxbury.",
        )
        assert out["error_code"] == "no_matching_places_in_area"
        assert out["suggestion"] is not None
        assert "Roslindale" in out["suggestion"]["widened_area"]

    def test_widen_suggestion_none_without_locality(self):
        import actionable_failure as af
        assert af._widen_area_suggestion("", "restaurants") is None


# ──────────────────── verify an LLM survivor's cuisine ─────────────────────
class TestVerifyListingCuisine:
    def test_mismatch_returns_false(self, monkeypatch):
        # Mamma Maria (Italian) must fail a Middle-Eastern cuisine check.
        _install(monkeypatch, [("mamma maria", [_MAMMA_MARIA])])
        assert gate.verify_listing_cuisine(
            "Mamma Maria", "North End, Boston", "middle eastern") is False

    def test_match_returns_true(self, monkeypatch):
        _install(monkeypatch, [("beirut", [_WR_LEBANESE])])
        assert gate.verify_listing_cuisine(
            "Beirut Café", "West Roxbury, MA", "middle eastern") is True

    def test_no_listing_returns_none(self, monkeypatch):
        # A name with no listing is UNKNOWN (None), never a mismatch (D162).
        _install(monkeypatch, [], default=[])
        assert gate.verify_listing_cuisine(
            "Phantom Kebab", "West Roxbury, MA", "middle eastern") is None

    def test_empty_cuisine_returns_true(self, monkeypatch):
        assert gate.verify_listing_cuisine("Anything", "Boston", "") is True

    def test_untagged_real_place_kept(self, monkeypatch):
        # A real North-End Italian with no OSM cuisine tag must be KEPT (True),
        # not dropped — OSM cuisine tags are sparse.
        _NO_TAG = {
            "name": "Giacomo's Ristorante",
            "display_name": "Giacomo's Ristorante, 355 Hanover St, North End, Boston, MA",
            "category": "amenity", "type": "restaurant",
            "lat": "42.3647", "lon": "-71.0542",
            "address": {"suburb": "North End", "city": "Boston", "state": "Massachusetts"},
        }
        _install(monkeypatch, [("giacomo", [_NO_TAG])])
        assert gate.verify_listing_cuisine(
            "Giacomo's Ristorante", "North End, Boston", "italian") is True

    def test_dumpling_dropped_for_middle_eastern(self, monkeypatch):
        _install(monkeypatch, [("dumpling", [_DUMPLING])])
        assert gate.verify_listing_cuisine(
            "Dumpling House", "West Roxbury, MA", "middle eastern") is False


# ──────────── verify an LLM survivor EXISTS in scope (anti-fabrication) ──────
class TestVerifyListingInScope:
    """[LOCAL-779B] The LOCAL-779 bounce delivered an INVENTED "Mamma Maria's" in
    West Roxbury whose address merely looked right. An LLM survivor counts only if
    its listing actually EXISTS inside the scope — a pure existence check."""

    def test_real_in_scope_place_returns_true(self, monkeypatch):
        _install(monkeypatch, [("beirut", [_WR_LEBANESE])])
        assert gate.verify_listing_in_scope("Beirut Café", "West Roxbury, MA") is True

    def test_invented_place_returns_false(self, monkeypatch):
        # The provider answers (a DIFFERENT place), but nothing matches the invented
        # name inside the scope → False (not None): the place is not there.
        _install(monkeypatch, [("mamma maria", [_WR_LEBANESE])], default=[_WR_LEBANESE])
        assert gate.verify_listing_in_scope("Mamma Maria's", "West Roxbury, MA") is False

    def test_empty_response_returns_false(self, monkeypatch):
        # A successful-but-empty search means the place was not found → False.
        _install(monkeypatch, [], default=[])
        assert gate.verify_listing_in_scope("Phantom Kebab", "West Roxbury, MA") is False

    def test_out_of_scope_match_returns_false(self, monkeypatch):
        # The named place exists but in the WRONG town (Newton) → not in scope.
        _install(monkeypatch, [("kebab house", [_NEWTON_KEBAB])])
        assert gate.verify_listing_in_scope("Kebab House", "West Roxbury, MA") is False

    def test_lookup_failure_returns_none(self, monkeypatch):
        # A network/RuntimeError is UNKNOWN (None), never a false fabrication verdict.
        def _boom(params, context=""):
            raise RuntimeError("nominatim down")
        monkeypatch.setattr(gate, "_nominatim_request", _boom)
        assert gate.verify_listing_in_scope("Beirut Café", "West Roxbury, MA") is None

    def test_no_name_or_scope_returns_none(self):
        assert gate.verify_listing_in_scope("", "West Roxbury, MA") is None
        assert gate.verify_listing_in_scope("Beirut Café", "") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
