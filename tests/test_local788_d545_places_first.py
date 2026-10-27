#!/usr/bin/env python3
"""LOCAL-788 item 4 — the D545 replenish (restaurant stop dropped as closed) must
use places_search (Serper Places + the LOCAL-786 bbox) FIRST, then the LOCAL-784
escalation ladder, and only its LAST tier an LLM name, each geo-verified.

ADDENDUM (tour 460 trace): the D545 replenish asked the LLM
(``restaurant_practicals.propose_replacements``) directly — Fairouz, Shawarma
Falafel, Byblos, Dino's, Sophia's Grotto, Kouzina, all rejected, none of them the
real Stardust / Bread Thyme — and NO bbox / places_search / Serper query line was
ever logged.

Two guards:
  1. The D545 block now calls ``replenish_with_escalation`` BEFORE the LLM
     ``propose_replacements`` loop (source-order invariant).
  2. ``replenish_with_escalation`` itself goes Serper-first and returns verified,
     coordinate-bearing candidates (exercised live against the recorded West
     Roxbury capture — proving the map path, not the LLM, produces the names).
"""
import inspect
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import escalating_lookup as el
import places_search as ps
import stop_existence_gate as gate
import generate_tour_text as gtt


# ───────────────── 1) source-order invariant: ladder BEFORE the LLM ──────────
class TestD545PlacesFirstOrdering:
    def test_escalation_ladder_called_before_llm_propose(self):
        src = inspect.getsource(gtt._generate_tour_text_impl)
        # The D545 block must reference the escalation ladder.
        assert "replenish_with_escalation" in src, (
            "D545 replenish must route through the escalation ladder (Serper first)")
        assert "propose_replacements" in src, "the LLM fallback should still exist"
        # The ladder call must come BEFORE the first LLM propose_replacements inside
        # the D545 region (places-first, LLM-last).
        # Find the D545 restaurant replenish region and check ordering within it.
        i_ladder = src.find("D545 places-first replenish")
        i_llm = src.find("propose_replacements", src.find("[D545] Replenish round"))
        assert i_ladder != -1, "the LOCAL-788 places-first D545 block is missing"
        assert i_llm != -1
        assert i_ladder < i_llm, (
            "places_search / escalation ladder must run BEFORE the LLM "
            "propose_replacements loop in the D545 replenish")

    def test_bbox_and_ll_reached_via_ladder(self):
        # The ladder's scope_center is wired through _geocode_scope_center and the
        # replenish uses scope_bbox — proving `ll` + bbox reach the map query.
        rsrc = inspect.getsource(gate.replenish_with_escalation)
        assert "_geocode_scope_center" in rsrc
        dsrc = inspect.getsource(gate.dining_replenish_candidates)
        assert "_geocode_scope_bbox" in dsrc and "scope_center" in dsrc


# ───────────── 2) the ladder is Serper-first and geo-verified ────────────────
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
    ]
}
_WR_CENTER_NOMINATIM = [{"lat": "42.2843", "lon": "-71.1627",
                         "boundingbox": ["42.255", "42.302", "-71.185", "-71.135"]}]


class _FakeNominatim:
    def __init__(self, geocode):
        self.geocode = geocode

    def __call__(self, params, context=""):
        q = (params.get("q") or "").lower()
        data = self.geocode if (" in " not in q and "restaurant" not in q) else []

        class _R:
            def __init__(self, d):
                self._d = d

            def json(self):
                return self._d
        return _R(data)


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(el, "_log_escalation", lambda row: True)
    monkeypatch.setattr(el, "_routing_start_tier", lambda c, r: None)
    monkeypatch.setattr(el, "_record_cheap_miss", lambda c, r, t: None)
    monkeypatch.setattr(el, "_check_daily_limit", lambda: None)
    monkeypatch.setattr(el, "_grounding_guard_active", lambda: False)
    ps.clear_cache()

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        q = (payload.get("q") or "").lower()
        if "middle eastern" in q or "mediterranean" in q:
            return 200, json.dumps(_SERPER_WR_MIDEAST).encode("utf-8")
        return 200, json.dumps({"places": []}).encode("utf-8")

    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    monkeypatch.setattr(gate, "_nominatim_request",
                        _FakeNominatim(_WR_CENTER_NOMINATIM))
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    yield


class TestLadderIsMapFirst:
    def test_ladder_returns_real_places_with_coords(self, wired):
        out = gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            cuisine="middle eastern",
            request_text="middle eastern restaurants near me, West Roxbury, MA")
        names = [c["name"] for c in out]
        assert names, "the map ladder must return real candidates, not an empty LLM reject list"
        assert any("Al Wadi" in n or "Bread Thyme" in n or "Stardust" in n
                   for n in names), names
        for c in out:
            assert c.get("coordinates") and c.get("lat") and c.get("lng")
            assert c.get("verified") is True

    def test_byblos_norwood_never_returned(self, wired):
        # The map path is scope-bound (LOCAL-786): a Norwood place is never a D545
        # replacement for a West Roxbury tour.
        out = gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 3,
            cuisine="middle eastern")
        assert all("Byblos" not in c["name"] for c in out)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
