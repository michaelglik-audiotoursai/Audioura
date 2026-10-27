#!/usr/bin/env python3
"""LOCAL-786: scope radius too loose — a West Roxbury restaurant tour included
Byblos in Norwood (~10 km from West Roxbury's centre).

Evidence (GCloud Subscribed tour 454, 2026-10-26 ~22:10): "middle eastern
restaurants near me, west Roxbury, MA", 2 stops → Stardust (West Roxbury, correct)
+ Byblos Restaurant. The only nearby Byblos is in Norwood, MA, ~10 km away. Real
West Roxbury options exist (Al Wadi, Bread Thyme), so the in-scope check accepted a
place far outside the neighbourhood.

The fix (places_search is the ONE place-search provider; the radius/bbox/town-match
logic lives in its scope-binding step, the choke point every path routes through):

  * The radius follows scope PRECISION:
      NEIGHBOURHOOD (West Roxbury, North End, Jamaica Plain) ~ 2.5 km
      CITY ~ 8 km for a small city, up to 15 km for a large one
      REGION/COUNTRY unchanged (wide).
  * Prefer the geocoder's BOUNDING BOX when present (inside the bbox + a 500 m
    margin) over the fixed radius.
  * "near me" with device coordinates: within 3 km of the device by default.
  * TOWN-NAME MISMATCH: a place whose address carries a town different from the
    scope's town AND that lies outside the bbox is rejected even if a radius would
    allow it (Byblos "Norwood, MA" for a West Roxbury request).

Fixtures only — NO live web. The Serper transport is monkeypatched with recorded
Places JSON (the real West Roxbury capture, plus Byblos Norwood's real coords).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import places_search as ps


# ─────────────── recorded Serper Places JSON (real coordinates) ──────────────
# West Roxbury Middle Eastern — the real 3 local ones (LOCAL-783 capture) PLUS the
# out-of-neighbourhood Byblos (Norwood, MA) that Serper reaches past the scope for.
# West Roxbury centre ~ (42.2843, -71.1627). Byblos Norwood ~ (42.1945, -71.1997),
# which is ~10 km south — exactly the tour-454 defect.
_BYBLOS_NORWOOD = {
    "position": 4, "title": "Byblos Restaurant",
    "address": "678 Washington St, Norwood, MA 02062",
    "latitude": 42.1945, "longitude": -71.1997, "rating": 4.3,
    "category": "Middle Eastern", "cid": "byblos-norwood"}

_SERPER_WR_MIDEAST = {
    "places": [
        {"position": 1, "title": "Al Wadi", "address": "1249 VFW Pkwy",
         "latitude": 42.27725, "longitude": -71.17266, "rating": 4.4,
         "category": "Middle Eastern", "cid": "al-wadi"},
        {"position": 2, "title": "Bread Thyme", "address": "1866 Centre St",
         "latitude": 42.285767, "longitude": -71.15497, "rating": 5,
         "category": "Lebanese", "cid": "bread-thyme"},
        {"position": 3, "title": "Stardust: Inspired Mediterranean , Persian",
         "address": "1753 Centre St", "latitude": 42.28744, "longitude": -71.15047,
         "rating": 4.9, "category": "Restaurant", "cid": "stardust"},
        _BYBLOS_NORWOOD,
    ]
}

# North End Italian — unchanged from LOCAL-783 (the regression reference).
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
    ]
}

# Brookline gyms (CITY scope). Brookline is a town ~5 km across; a gym on its far
# side is still IN Brookline and must be kept by the city radius. The two coords
# straddle Brookline (Coolidge Corner ~ 42.342,-71.121; Chestnut Hill end
# ~ 42.325,-71.157), ~3 km apart — both inside the town.
_SERPER_BROOKLINE_GYMS = {
    "places": [
        {"position": 1, "title": "Coolidge Corner Fitness",
         "address": "1309 Beacon St, Brookline, MA", "latitude": 42.342,
         "longitude": -71.121, "category": "Gym", "cid": "bg1"},
        {"position": 2, "title": "Chestnut Hill Health Club",
         "address": "1180 Boylston St, Brookline, MA", "latitude": 42.325,
         "longitude": -71.157, "category": "Fitness center", "cid": "bg2"},
    ]
}

_WR_CENTER = (42.2843, -71.1627)         # West Roxbury
_NE_CENTER = (42.3647, -71.0542)         # North End
_BROOKLINE_CENTER = (42.3318, -71.1212)  # Brookline town centre

# Nominatim jsonv2 boundingbox is [south, north, west, east]. West Roxbury's real
# bbox is roughly 42.26-42.30 N, -71.18--71.13 W — it does NOT contain Norwood.
_WR_BBOX = ["42.255", "42.302", "-71.185", "-71.135"]
_BROOKLINE_BBOX = ["42.305", "42.350", "-71.178", "-71.106"]


def _install(monkeypatch, body_by_query):
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
    return state


# ───────────────────────── scope precision → radius ─────────────────────────
class TestScopePrecision:
    @pytest.mark.parametrize("scope,expected", [
        ("West Roxbury, MA", "NEIGHBOURHOOD"),
        ("North End, Boston", "NEIGHBOURHOOD"),
        ("Jamaica Plain, Boston", "NEIGHBOURHOOD"),
        ("Brookline, MA", "CITY"),
        ("Boston, MA", "CITY"),
    ])
    def test_precision_classification(self, scope, expected):
        assert ps._scope_precision(scope) == expected

    def test_neighbourhood_radius_is_tight(self):
        # NEIGHBOURHOOD ~ 2.5 km — tight enough to exclude a 10 km spillover.
        r = ps._radius_for_precision("NEIGHBOURHOOD", scope="West Roxbury, MA")
        assert 2.0 <= r <= 3.0

    def test_city_radius_small_city(self):
        # A small city ~ 8 km.
        r = ps._radius_for_precision("CITY", scope="Brookline, MA")
        assert 6.0 <= r <= 10.0

    def test_city_radius_large_city_wider(self):
        # A large city may reach up to ~15 km.
        r = ps._radius_for_precision("CITY", scope="Los Angeles, CA")
        assert r >= 12.0


# ───────────────── the Byblos Norwood defect (the headline) ─────────────────
class TestByblosNorwoodRejected:
    def test_byblos_norwood_dropped_for_west_roxbury(self, monkeypatch):
        _install(monkeypatch, [("middle eastern", _SERPER_WR_MIDEAST)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=_WR_CENTER, scope_bbox=_WR_BBOX, limit=10)
        names = [r["name"] for r in out]
        assert "Byblos Restaurant" not in names, (
            f"Byblos Norwood (~10 km) must be rejected for West Roxbury. Got {names}")

    def test_real_west_roxbury_places_kept(self, monkeypatch):
        _install(monkeypatch, [("middle eastern", _SERPER_WR_MIDEAST)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=_WR_CENTER, scope_bbox=_WR_BBOX, limit=10)
        names = [r["name"] for r in out]
        assert "Al Wadi" in names
        assert "Bread Thyme" in names
        assert any("Stardust" in n for n in names)

    def test_byblos_dropped_even_without_bbox(self, monkeypatch):
        # With no bbox the tight NEIGHBOURHOOD radius alone (~2.5 km) still drops
        # Byblos at ~10 km.
        _install(monkeypatch, [("middle eastern", _SERPER_WR_MIDEAST)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=_WR_CENTER, limit=10)
        names = [r["name"] for r in out]
        assert "Byblos Restaurant" not in names
        assert "Al Wadi" in names


# ──────────────────── town-name mismatch rejection ──────────────────────────
class TestTownNameMismatch:
    def test_norwood_address_rejected_for_west_roxbury(self, monkeypatch):
        # Byblos's address carries "Norwood, MA" — a different town than the scope
        # "West Roxbury" — and lies outside the West Roxbury bbox → rejected.
        _install(monkeypatch, [("middle eastern", {"places": [_BYBLOS_NORWOOD]})])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=_WR_CENTER, scope_bbox=_WR_BBOX, limit=10)
        assert out == [], f"A Norwood address must be rejected for West Roxbury. Got {out}"

    def test_in_town_place_inside_bbox_kept(self, monkeypatch):
        # A place whose address names the scope town and sits inside the bbox is kept.
        in_town = {"places": [{
            "title": "Centre St Grill", "address": "1800 Centre St, West Roxbury, MA",
            "latitude": 42.286, "longitude": -71.152, "category": "Middle Eastern",
            "cid": "cg"}]}
        _install(monkeypatch, [("middle eastern", in_town)])
        out = ps.places_search(
            "middle eastern restaurants West Roxbury MA", "West Roxbury, MA",
            scope_center=_WR_CENTER, scope_bbox=_WR_BBOX, limit=10)
        assert [r["name"] for r in out] == ["Centre St Grill"]


# ───────────────────── city-scope stays permissive ─────────────────────────
class TestCityScopeKeepsAcrossTown:
    def test_brookline_gyms_across_town_all_kept(self, monkeypatch):
        # "gyms in Brookline, MA" — both gyms are in Brookline but ~3 km apart; a
        # city radius (~8 km) keeps both. A neighbourhood radius would wrongly drop
        # the far one.
        _install(monkeypatch, [("gym", _SERPER_BROOKLINE_GYMS)])
        out = ps.places_search(
            "gyms Brookline MA", "Brookline, MA",
            scope_center=_BROOKLINE_CENTER, scope_bbox=_BROOKLINE_BBOX, limit=10)
        names = [r["name"] for r in out]
        assert "Coolidge Corner Fitness" in names
        assert "Chestnut Hill Health Club" in names


# ─────────────────────────── near-me 3 km ───────────────────────────────────
class TestNearMeRadius:
    def test_near_me_keeps_within_3km(self, monkeypatch):
        # Device at the West Roxbury centre. Al Wadi (~1 km) kept; Byblos (~10 km)
        # dropped by the 3 km near-me radius.
        _install(monkeypatch, [("middle eastern", _SERPER_WR_MIDEAST)])
        out = ps.places_search(
            "middle eastern restaurants", "West Roxbury, MA",
            near=_WR_CENTER, limit=10)
        names = [r["name"] for r in out]
        assert "Al Wadi" in names
        assert "Byblos Restaurant" not in names

    def test_near_me_drops_beyond_3km(self, monkeypatch):
        # A place ~4 km from the device is beyond the 3 km near-me radius.
        far = {"places": [{
            "title": "Four Km Away", "address": "1 Far St",
            "latitude": 42.248, "longitude": -71.1627,  # ~4 km south of WR centre
            "category": "Middle Eastern", "cid": "fk"}]}
        _install(monkeypatch, [("middle eastern", far)])
        out = ps.places_search(
            "middle eastern restaurants", "West Roxbury, MA",
            near=_WR_CENTER, limit=10)
        assert out == []


# ──────────────── North End Italian set unchanged (regression) ──────────────
class TestNorthEndUnchanged:
    def test_north_end_italian_all_kept(self, monkeypatch):
        _install(monkeypatch, [("italian", _SERPER_NE_ITALIAN)])
        out = ps.places_search(
            "italian restaurants North End Boston", "North End, Boston",
            scope_center=_NE_CENTER, limit=10)
        names = [r["name"] for r in out]
        assert "Pizzeria Regina" in names
        assert "Mamma Maria" in names
        assert "Carmelina's" in names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
