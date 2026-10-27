#!/usr/bin/env python3
"""LOCAL-783: business/restaurant place search via Serper Places (not the free
Nominatim endpoint) for the bulk search + refill.

The LOCAL-779B "Known limitation": the bulk `dining_replenish_candidates` /
business refill free-text query ("<cuisine> restaurants in <scope>") went to the
free Nominatim endpoint, which returned 0 live for both West Roxbury and the North
End. The refill — what rescues a tour when the LLM proposes the wrong town — was
therefore empty. Serper's Places endpoint returns the real, in-scope places.

Fixtures only — NO live web. The Serper transport (places_search._serper_post) is
monkeypatched with RECORDED Serper Places JSON (captured once live, 2026-10-26):
  "middle eastern restaurants West Roxbury MA" @ll 42.2794,-71.1595,14z →
     Al Wadi (1249 VFW Pkwy), Bread Thyme (1866 Centre St, Lebanese),
     Stardust: Inspired Mediterranean/Persian (1753 Centre St)
which is exactly what Google shows for that request.

What it proves (the LOCAL-783 contract):
  * places_search() calls Serper Places with the scope `ll` (town honoured), and
    normalises each result to the OSM jsonv2 shape the gate consumes.
  * dining_replenish_candidates refills from Serper Places (West Roxbury Middle
    Eastern → the 3 local ones), with cuisine matching on Serper's `category`.
  * The North End Italian refill fills from Places.
  * The Nominatim FALLBACK runs when there is no key (SERP_PROVIDER!=serper).
  * The meter (serper_post) is called ONCE per uncached query; a 2nd identical
    query within 24 h is served from cache (no 2nd call).
  * A Chinese place is rejected for a Middle-Eastern request (cuisine via Places).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import places_search as ps
import stop_existence_gate as gate


# ───────────────── recorded Serper Places JSON (captured live once) ─────────
# West Roxbury Middle Eastern — the exact live capture (2026-10-26). Serper's
# `address` carries only the street; the town is honoured via the `ll` centre.
_SERPER_WR_MIDEAST = {
    "places": [
        {"position": 1, "title": "Al Wadi", "address": "1249 VFW Pkwy",
         "latitude": 42.27725, "longitude": -71.17266, "rating": 4.4,
         "ratingCount": 869, "priceLevel": "$40\u201350",
         "category": "Middle Eastern",
         "website": "http://www.alwadiboston.com/", "cid": "1959986146669768908"},
        {"position": 2, "title": "Bread Thyme", "address": "1866 Centre St",
         "latitude": 42.285767, "longitude": -71.15497, "rating": 5,
         "ratingCount": 223, "priceLevel": "$10\u201320", "category": "Lebanese",
         "website": "https://breadthyme.com/", "cid": "6457763302365485083"},
        {"position": 3, "title": "Stardust: Inspired Mediterranean , Persian",
         "address": "1753 Centre St", "latitude": 42.28744, "longitude": -71.15047,
         "rating": 4.9, "ratingCount": 231, "priceLevel": "$10\u201320",
         "category": "Restaurant", "cid": "6382196640288619178"},
    ]
}

# North End Italian — recorded shape (representative Serper Places for the refill).
_SERPER_NE_ITALIAN = {
    "places": [
        {"position": 1, "title": "Pizzeria Regina", "address": "11 Thacher St",
         "latitude": 42.36535, "longitude": -71.05697, "rating": 4.5,
         "category": "Pizza restaurant", "cid": "111"},
        {"position": 2, "title": "Mamma Maria", "address": "3 North Square",
         "latitude": 42.36393, "longitude": -71.05402, "rating": 4.6,
         "category": "Italian restaurant", "cid": "222"},
        {"position": 3, "title": "Carmelina's", "address": "307 Hanover St",
         "latitude": 42.36502, "longitude": -71.05363, "rating": 4.5,
         "category": "Italian restaurant", "cid": "333"},
        # A spillover Chinese place Serper sometimes returns — must be cuisine-dropped.
        {"position": 4, "title": "China Pearl", "address": "9 Tyler St",
         "latitude": 42.36000, "longitude": -71.05500, "rating": 4.0,
         "category": "Chinese restaurant", "cid": "444"},
    ]
}

# West Roxbury gyms — a BUSINESS (non-dining) Places capture for the control.
_SERPER_WR_GYMS = {
    "places": [
        {"position": 1, "title": "Planet Fitness", "address": "1600 VFW Pkwy",
         "latitude": 42.2842, "longitude": -71.1485, "category": "Gym", "cid": "g1"},
        {"position": 2, "title": "YMCA West Roxbury", "address": "15 Bellevue St",
         "latitude": 42.2860, "longitude": -71.1428,
         "category": "Fitness center", "cid": "g2"},
    ]
}

# City geocode centres (Nominatim jsonv2 shape) — for the scope `ll`.
_WR_CENTER_NOMINATIM = [{"lat": "42.2843", "lon": "-71.1627"}]
_NE_CENTER_NOMINATIM = [{"lat": "42.3647", "lon": "-71.0542"}]


class _FakeNominatim:
    """A fake _nominatim_request that serves the city-geocode only (the Serper path
    never uses Nominatim for the place list, only for the scope centre)."""
    def __init__(self, geocode):
        self.geocode = geocode
        self.calls = []

    def __call__(self, params, context=""):
        self.calls.append(params.get("q", ""))

        class _R:
            def __init__(self, d):
                self._d = d

            def json(self):
                return self._d
        return _R(self.geocode)


def _install_serper(monkeypatch, body_by_query, geocode=_WR_CENTER_NOMINATIM):
    """Enable Serper Places and serve recorded bodies by query substring. Returns a
    dict with a call list so a test can assert the meter fires once per query."""
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    ps.clear_cache()
    state = {"calls": []}

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        state["calls"].append({"url": url, "payload": payload})
        q = (payload.get("q") or "").lower()
        for key, body in body_by_query:
            if key in q:
                return 200, json.dumps(body).encode("utf-8")
        return 200, json.dumps({"places": []}).encode("utf-8")

    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    # Scope-centre geocode still goes to Nominatim; serve a fixed centre.
    monkeypatch.setattr(gate, "_nominatim_request", _FakeNominatim(geocode))
    return state


# ──────────────────────────── provider selection ────────────────────────────
class TestProviderSelection:
    def test_enabled_when_key_and_serper(self, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "k")
        monkeypatch.setenv("SERP_PROVIDER", "serper")
        monkeypatch.setattr(ps, "_serper_post", lambda *a, **k: (200, b"{}"))
        assert ps.serper_places_enabled() is True

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("SERP_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.setenv("SERP_PROVIDER", "serper")
        assert ps.serper_places_enabled() is False

    def test_disabled_when_provider_not_serper(self, monkeypatch):
        monkeypatch.setenv("SERP_API_KEY", "k")
        monkeypatch.setenv("SERP_PROVIDER", "nominatim")
        assert ps.serper_places_enabled() is False


# ──────────────────────────── normalisation ─────────────────────────────────
class TestNormalise:
    def test_serper_place_to_osm_shape(self):
        rec = ps._normalize_serper_place(_SERPER_WR_MIDEAST["places"][0])
        assert rec["name"] == "Al Wadi"
        assert rec["type"] == "restaurant"
        assert rec["category"] == "amenity"
        assert float(rec["lat"]) == pytest.approx(42.27725)
        assert float(rec["lon"]) == pytest.approx(-71.17266)
        # Serper `category` text carried as the cuisine signal.
        assert "middle eastern" in rec["extratags"]["cuisine"]
        # Street parsed into address components.
        assert rec["address"]["house_number"] == "1249"
        assert "VFW" in rec["address"]["road"]

    def test_missing_coords_dropped(self):
        assert ps._normalize_serper_place({"title": "X"}) is None

    def test_missing_name_dropped(self):
        assert ps._normalize_serper_place(
            {"latitude": 1.0, "longitude": 2.0}) is None


# ──────────────────── places_search sources + scope-binds ───────────────────
class TestPlacesSearch:
    def test_west_roxbury_mideast_returns_three_local(self, monkeypatch):
        _install_serper(monkeypatch,
                        [("middle eastern", _SERPER_WR_MIDEAST)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=(42.2843, -71.1627), limit=10)
        names = [r["name"] for r in out]
        assert "Al Wadi" in names
        assert "Bread Thyme" in names
        assert any("Stardust" in n for n in names)
        # Scope locality stamped so the gate's in-scope check binds.
        for r in out:
            assert "west roxbury" in (r["display_name"].lower())

    def test_returns_empty_when_disabled(self, monkeypatch):
        monkeypatch.delenv("SERP_API_KEY", raising=False)
        monkeypatch.setenv("SERP_PROVIDER", "serper")
        assert ps.places_search("x", "West Roxbury, MA") == []

    def test_far_spillover_place_dropped_by_radius(self, monkeypatch):
        far = {"places": [
            {"title": "Faraway Grill", "address": "1 Main St", "latitude": 43.5,
             "longitude": -72.5, "category": "Middle Eastern", "cid": "z"}]}
        _install_serper(monkeypatch, [("middle eastern", far)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=(42.2843, -71.1627), limit=10)
        assert out == []


# ──────────────────────────── 24 h query cache ──────────────────────────────
class TestCacheMeterOnce:
    def test_identical_query_cached_meter_called_once(self, monkeypatch):
        state = _install_serper(monkeypatch,
                                [("middle eastern", _SERPER_WR_MIDEAST)])
        args = dict(scope="West Roxbury, MA", scope_center=(42.2843, -71.1627))
        a = ps.places_search("middle eastern restaurants West Roxbury MA", **args)
        b = ps.places_search("middle eastern restaurants West Roxbury MA", **args)
        assert [r["name"] for r in a] == [r["name"] for r in b]
        # Exactly ONE Serper call despite two identical queries → the 2nd is cached.
        assert len(state["calls"]) == 1

    def test_different_query_bills_again(self, monkeypatch):
        state = _install_serper(monkeypatch, [
            ("middle eastern", _SERPER_WR_MIDEAST),
            ("italian", _SERPER_NE_ITALIAN),
        ])
        ps.places_search("middle eastern restaurants West Roxbury MA",
                         scope="West Roxbury, MA", scope_center=(42.2843, -71.1627))
        ps.places_search("italian restaurants North End Boston",
                         scope="North End, Boston", scope_center=(42.3647, -71.0542))
        assert len(state["calls"]) == 2


# ──────────────── dining replenish via Serper Places (the fix) ──────────────
class TestDiningReplenishViaSerper:
    def test_west_roxbury_mideast_refills_from_places(self, monkeypatch):
        """The LOCAL-779B bounce case: Nominatim returned 0, Serper Places returns
        the 3 real Middle-Eastern places in West Roxbury."""
        _install_serper(monkeypatch, [("middle eastern", _SERPER_WR_MIDEAST)])
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=2, exclude=set())
        names = [c["name"] for c in cands]
        assert len(cands) == 2
        # The two nearest Middle-Eastern places are delivered, verified + with coords.
        assert any(n in ("Al Wadi", "Bread Thyme") or "Stardust" in n for n in names)
        for c in cands:
            assert c["verified"] is True
            assert c["lat"] and c["lng"]

    def test_north_end_italian_refill_drops_chinese(self, monkeypatch):
        """North End Italian refill fills from Places; a spillover Chinese place is
        dropped for cuisine."""
        _install_serper(monkeypatch, [("italian", _SERPER_NE_ITALIAN)],
                        geocode=_NE_CENTER_NOMINATIM)
        cands = gate.dining_replenish_candidates(
            "italian restaurants", "North End, Boston", needed=3, exclude=set())
        names = [c["name"] for c in cands]
        assert "China Pearl" not in names
        assert "Mamma Maria" in names or "Pizzeria Regina" in names

    def test_business_gyms_refill_from_places(self, monkeypatch):
        _install_serper(monkeypatch, [("gym", _SERPER_WR_GYMS)])
        cands = gate.business_replenish_candidates(
            "gyms", "West Roxbury, MA", needed=2, exclude=set())
        names = [c["name"] for c in cands]
        assert len(cands) == 2
        assert "Planet Fitness" in names
        assert "YMCA West Roxbury" in names


# ──────────────── Nominatim fallback when Serper is OFF ─────────────────────
class TestNominatimFallback:
    def test_fallback_runs_without_key(self, monkeypatch):
        """With no key, _places_lookup falls straight through to Nominatim — the
        existing LOCAL-779B behaviour. We serve a recorded Nominatim jsonv2 body."""
        monkeypatch.delenv("SERP_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.setenv("SERP_PROVIDER", "nominatim")
        _NOMINATIM_WR = {
            "name": "Beirut Café",
            "display_name": "Beirut Café, 1739 Centre St, West Roxbury, Boston, MA",
            "category": "amenity", "type": "restaurant",
            "lat": "42.2795", "lon": "-71.1601",
            "address": {"road": "Centre Street", "suburb": "West Roxbury",
                        "city": "Boston", "state": "Massachusetts"},
            "extratags": {"cuisine": "lebanese;middle_eastern"},
        }

        def _fake(params, context=""):
            q = (params.get("q") or "").lower()

            class _R:
                def __init__(self, d):
                    self._d = d

                def json(self):
                    return self._d
            if q.strip().startswith("west roxbury"):
                return _R([{"lat": "42.2843", "lon": "-71.1627"}])
            if "middle eastern" in q:
                return _R([_NOMINATIM_WR])
            return _R([])
        monkeypatch.setattr(gate, "_nominatim_request", _fake)
        cands = gate.dining_replenish_candidates(
            "middle eastern restaurants", "West Roxbury, MA", needed=2, exclude=set())
        names = [c["name"] for c in cands]
        assert "Beirut Café" in names


# ──────────────── per-name verification via Serper Places ──────────────────
class TestVerifyViaSerper:
    def test_in_scope_place_verifies_true(self, monkeypatch):
        _install_serper(monkeypatch, [("al wadi", _SERPER_WR_MIDEAST)])
        assert gate.verify_listing_in_scope("Al Wadi", "West Roxbury, MA") is True

    def test_cuisine_verified_via_places(self, monkeypatch):
        _install_serper(monkeypatch, [("bread thyme", _SERPER_WR_MIDEAST)])
        # Bread Thyme is Lebanese → matches Middle Eastern.
        assert gate.verify_listing_cuisine(
            "Bread Thyme", "West Roxbury, MA", "middle eastern") is True


# ──────────────────────────── pricing / cost card ──────────────────────────
class TestPlacesPricing:
    def test_places_cost_is_two_credits(self):
        import cost_rates
        assert cost_rates.SERPER_PLACES_COST_PER_QUERY == 0.002
        assert cost_rates.places_cost(3) == pytest.approx(0.006)

    def test_meter_prices_places_endpoint(self):
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_meter"))
        import paid_api_meter as m
        assert m.SERPER_PLACES_PER_QUERY == 0.002
        assert m.SERPER_PER_QUERY == 0.001


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
