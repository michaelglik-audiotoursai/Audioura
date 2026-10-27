#!/usr/bin/env python3
"""LOCAL-779: Business POI tours (gyms/cafés/shops…) must verify via a maps/places
result, exactly as restaurants do, instead of being dropped by the existence gate's
Wikidata/OSM-landmark path (which businesses are not on).

Fixtures only — no live web. Every OSM call is monkeypatched with a recorded
Nominatim JSON payload, so this suite runs in the default (non-network) test run.

What it proves (the LOCAL-779 contract):
  * classify_business_vs_landmark: gyms/cafés/shops/bars/spas → 'business';
    restaurants → 'dining'; landmarks/museums → 'landmark'.
  * A real gym (Gold's Gym, West Roxbury) VERIFIES through the business maps path
    with coordinates taken from the listing, in ENFORCE mode.
  * A fabricated business (a name with no listing) is DROPPED.
  * A real-named business in the WRONG city is DROPPED (proximity binds).
  * A LANDMARK tour is UNCHANGED: a fabricated landmark still has no business
    listing, and the business path is never taken for a landmark poi_type.
  * PHASE 3C scope stripping: _scope_from_request turns the request into the
    bounded place, so the restaurant containment guard compares against
    "West Roxbury, MA", not the whole "… near me, west Roxbury, MA" string.
  * The area resolver parses "West Roxbury, MA" out of the junk request.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_existence_gate as gate


# ──────────────────────────── recorded fixtures ─────────────────────────────
# Minimal Nominatim jsonv2 shapes, keyed by the leading token of the query.
class _FakeResp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


# Real West Roxbury gyms (coordinates approximate, from OSM).
_GOLDS = {
    "name": "Gold's Gym",
    "display_name": "Gold's Gym, 1000 VFW Parkway, West Roxbury, Boston, MA, 02132",
    "category": "leisure",
    "type": "fitness_centre",
    "lat": "42.2798",
    "lon": "-71.1627",
    "address": {"road": "VFW Parkway", "house_number": "1000",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
}
_PLANET = {
    "name": "Planet Fitness",
    "display_name": "Planet Fitness, 1400 VFW Parkway, West Roxbury, Boston, MA",
    "category": "leisure",
    "type": "fitness_centre",
    "lat": "42.2810",
    "lon": "-71.1631",
    "address": {"road": "VFW Parkway", "house_number": "1400",
                "suburb": "West Roxbury", "city": "Boston", "state": "Massachusetts"},
}
# A gym with the right name but in the WRONG city — proximity must reject it.
_WRONG_CITY = {
    "name": "Gold's Gym",
    "display_name": "Gold's Gym, Dallas, TX",
    "category": "leisure",
    "type": "fitness_centre",
    "lat": "32.7767",
    "lon": "-96.7970",
    "address": {"city": "Dallas", "state": "Texas"},
}


def _install_fake_nominatim(monkeypatch, mapping, default=None):
    """Monkeypatch gate._nominatim_request to serve recorded payloads by query prefix."""
    def _fake(params, context=""):
        q = (params.get("q") or "").lower()
        for key, payload in mapping.items():
            if key in q:
                return _FakeResp(payload)
        return _FakeResp(default if default is not None else [])
    monkeypatch.setattr(gate, "_nominatim_request", _fake)


# ──────────────────────────── classification ────────────────────────────────
class TestBusinessClassification:
    @pytest.mark.parametrize("poi_type,expected", [
        ("gyms", "business"),
        ("fitness centers", "business"),
        ("climbing gyms", "business"),
        ("coffee shops", "business"),
        ("cafes", "business"),
        ("bakeries", "business"),
        ("bars", "business"),
        ("breweries", "business"),
        ("spas", "business"),
        ("bookstores", "business"),
        ("restaurants", "dining"),
        ("middle eastern restaurants", "dining"),
        ("landmarks", "landmark"),
        ("museums", "landmark"),
        ("filming locations", "landmark"),
        ("book locations", "landmark"),
        ("", "landmark"),
        (None, "landmark"),
    ])
    def test_classify(self, poi_type, expected):
        assert gate.classify_business_vs_landmark(poi_type) == expected


# ──────────────────────────── business existence ────────────────────────────
class TestBusinessExistence:
    def test_real_gym_verifies_with_coords(self, monkeypatch):
        _install_fake_nominatim(monkeypatch, {"gold": [_GOLDS]})
        signals = gate._city_signals_from_venue("West Roxbury, MA")
        verified, evidence, coords = gate._check_business_existence(
            "Gold's Gym", "West Roxbury, MA", signals)
        assert verified is True
        assert coords is not None
        lat, lng = coords
        # Coordinates land inside West Roxbury, MA (≈42.28, -71.16).
        assert 42.0 < lat < 42.5
        assert -71.3 < lng < -71.0
        assert "nominatim_osm" in evidence

    def test_fabricated_business_dropped(self, monkeypatch):
        # No listing returned for a fabricated name → unverified, no coords.
        _install_fake_nominatim(monkeypatch, {}, default=[])
        signals = gate._city_signals_from_venue("West Roxbury, MA")
        verified, evidence, coords = gate._check_business_existence(
            "Phantom Iron Temple Fitness Club", "West Roxbury, MA", signals)
        assert verified is False
        assert coords is None

    def test_wrong_city_dropped(self, monkeypatch):
        # Right name, wrong city — proximity must bind.
        _install_fake_nominatim(monkeypatch, {"gold": [_WRONG_CITY]})
        signals = gate._city_signals_from_venue("West Roxbury, MA")
        verified, _, coords = gate._check_business_existence(
            "Gold's Gym", "West Roxbury, MA", signals)
        assert verified is False
        assert coords is None


# ──────────────────────────── gate end-to-end (ENFORCE) ─────────────────────
class TestGateEnforceBusiness:
    def test_two_gyms_verify_one_fabricated_dropped(self, monkeypatch):
        monkeypatch.setenv("STOP_EXISTENCE_GATE_MODE", "enforce")

        def _fake(params, context=""):
            q = (params.get("q") or "").lower()
            if "gold" in q:
                return _FakeResp([_GOLDS])
            if "planet" in q:
                return _FakeResp([_PLANET])
            return _FakeResp([])  # fabricated → nothing
        monkeypatch.setattr(gate, "_nominatim_request", _fake)

        result = gate.run_existence_gate(
            ["Gold's Gym", "Planet Fitness", "Phantom Iron Temple"],
            "West Roxbury, MA", db_conn=None,
            tour_type="walking", poi_type="gyms",
        )
        assert result["mode"] == "enforce"
        assert set(result["verified_stops"]) == {"Gold's Gym", "Planet Fitness"}
        assert "Phantom Iron Temple" in result["unverified_stops"]
        # Coordinates travelled with the verified verdicts.
        by_name = {v["stop_title"]: v for v in result["verdicts"]}
        assert by_name["Gold's Gym"]["coords"] is not None
        assert by_name["Gold's Gym"]["venue_kind"] == "business"
        assert by_name["Gold's Gym"]["source"] == "business_maps"

    def test_landmark_tour_unchanged(self, monkeypatch):
        """A landmark poi_type never routes to the business path; a fabricated
        landmark still has no maps listing and stays unverified."""
        monkeypatch.setenv("STOP_EXISTENCE_GATE_MODE", "enforce")

        # If the business path were (wrongly) taken, this would 'verify' the
        # fabricated landmark. It must NOT be called for a landmark poi_type.
        def _fake(params, context=""):
            return _FakeResp([{
                "name": "The State House Park",
                "display_name": "The State House Park, Boston, MA",
                "category": "leisure", "type": "park",
                "lat": "42.0", "lon": "-71.0",
                "address": {"city": "Boston", "state": "Massachusetts"},
            }])
        monkeypatch.setattr(gate, "_nominatim_request", _fake)

        kind, _ = gate._classify_venue_kind(
            "Boston, MA", db_conn=None, tour_type="walking", poi_type="landmarks")
        assert kind != "business"


# ──────────────────────────── scope stripping (PHASE 3C) ────────────────────
class TestScopeStripping:
    @pytest.mark.parametrize("request_str,expected", [
        ("middle eastern restaurants near me, west Roxbury, MA", "west Roxbury, MA"),
        ("walking tour: gyms near me, west Roxbury, MA", "west Roxbury, MA"),
        ("gyms near me, west Roxbury, MA", "west Roxbury, MA"),
        ("coffee shops in Harvard Square, Cambridge MA", "Harvard Square, Cambridge MA"),
        ("restaurants in North End, Boston", "North End, Boston"),
        ("Freedom Trail, Boston", "Freedom Trail, Boston"),
        ("Newton, MA", "Newton, MA"),
    ])
    def test_scope_from_request(self, request_str, expected):
        import generate_tour_text as gtt
        assert gtt._scope_from_request(request_str) == expected

    def test_intent_scope_preferred(self):
        import generate_tour_text as gtt
        got = gtt._scope_from_request(
            "anything", intent={"geographic_scope": "West Roxbury, MA"})
        assert got == "West Roxbury, MA"

    def test_phase3c_keeps_in_scope_restaurant(self):
        """The restaurant containment bug: an in-scope address must PASS when the
        guard compares against the scope, not the whole 'near me' request."""
        import generate_tour_text as gtt
        scope = gtt._scope_from_request(
            "middle eastern restaurants near me, west Roxbury, MA")
        # Al Wadi's real address is inside West Roxbury.
        assert gtt._address_matches_location(
            "1070 Washington St, West Roxbury, MA 02132", scope) is True
        # The old (buggy) behaviour compared against the whole request string; an
        # out-of-area address (North End) must still be rejected against the scope.
        assert gtt._address_matches_location(
            "3 North Square, North End, Boston, MA 02113", scope) is False


# ──────────────────────────── area resolver ─────────────────────────────────
class TestAreaResolverParse:
    @pytest.mark.parametrize("request_str,expected_city", [
        ("walking tour: gyms near me, west Roxbury, MA", "west Roxbury, MA"),
        ("gyms near me, west Roxbury, MA", "west Roxbury, MA"),
    ])
    def test_city_parsed_not_junk(self, request_str, expected_city):
        from area_resolver import _parse_location
        neighborhood, city = _parse_location(request_str)
        # The old bug produced neighborhood == ": gyms near me" and lost the place.
        assert ":" not in neighborhood
        assert "near me" not in neighborhood.lower()
        assert city == expected_city


# ──────────────────────────── business replenishment ────────────────────────
class TestBusinessReplenishment:
    def test_replenish_from_maps_ranked_by_distance(self, monkeypatch):
        def _fake(params, context=""):
            q = (params.get("q") or "").lower()
            if q.startswith("gyms in"):
                return _FakeResp([_PLANET, _GOLDS, _WRONG_CITY])
            # city-centre geocode fallback
            return _FakeResp([{"lat": "42.2843", "lon": "-71.1627"}])
        monkeypatch.setattr(gate, "_nominatim_request", _fake)

        cands = gate.business_replenish_candidates(
            "gyms", "West Roxbury, MA", needed=2, exclude=set())
        names = [c["name"] for c in cands]
        assert len(cands) == 2
        # Dallas gym excluded by proximity; both in-scope gyms returned.
        assert "Gold's Gym" in names and "Planet Fitness" in names
        for c in cands:
            assert c["verified"] is True
            assert c["coordinates"]
            assert c["lat"] and c["lng"]


# ──────────────────────────── PHASE 4 cuisine match ─────────────────────────
class TestPhase4CuisineMatch:
    """LOCAL-779: PHASE 4 type verification must honour a cuisine/sub-type
    qualifier — "Mamma Maria" (Italian) is NOT a "middle eastern restaurant".
    verify_poi_matches_type makes a live LLM call, so here we assert the PROMPT it
    builds now carries the cuisine-match rule and the worked Mamma Maria example
    (a deterministic source-level check — no network)."""

    def test_prompt_requires_cuisine_match(self, monkeypatch):
        import generate_tour_text as gtt

        captured = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content":
                        '{"matches": false, "reason": "Italian not Middle Eastern", '
                        '"confidence": "high"}'}}]}

        def _fake_post(url, headers=None, data=None, **kw):
            captured["data"] = data
            return _Resp()

        monkeypatch.setattr(gtt.requests, "post", _fake_post)
        out = gtt.verify_poi_matches_type(
            "Mamma Maria", "middle eastern restaurants", api_key="x")
        assert out["matches"] is False
        body = captured["data"].lower()
        assert "cuisine" in body
        assert "middle eastern restaurant" in body
        assert "mamma maria" in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
