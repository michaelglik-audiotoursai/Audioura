"""LOCAL-784 / D722: the escalation ladder wired through the REAL replenish path.

This exercises `stop_existence_gate.replenish_with_escalation` end-to-end with the
recorded Serper Places capture LOCAL-783 used (Al Wadi / Bread Thyme / Stardust),
proving that the escalation wrapper:
  * forces the cheap tier to MISS (D722_FORCE_CHEAP_MISS=1 or a dead Nominatim),
  * escalates to Serper Places (tier b) and returns the real in-scope places in
    the SAME candidate shape the maps-first stops use,
  * fills the LOCAL-783 24 h cache (a repeat serves from cache, no 2nd Serper call),

Fixtures only — NO live web, NO DB. The DB seam (the escalation log + routing) is
replaced with an in-memory capture; the Serper transport is the recorded JSON.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import escalating_lookup as el
import places_search as ps
import stop_existence_gate as gate


# Recorded Serper Places JSON — the exact LOCAL-783 live capture (2026-10-26).
_SERPER_WR_MIDEAST = {
    "places": [
        {"position": 1, "title": "Al Wadi", "address": "1249 VFW Pkwy",
         "latitude": 42.27725, "longitude": -71.17266, "rating": 4.4,
         "category": "Middle Eastern", "cid": "1959986146669768908"},
        {"position": 2, "title": "Bread Thyme", "address": "1866 Centre St",
         "latitude": 42.285767, "longitude": -71.15497, "rating": 5,
         "category": "Lebanese", "cid": "6457763302365485083"},
        {"position": 3, "title": "Stardust: Inspired Mediterranean , Persian",
         "address": "1753 Centre St", "latitude": 42.28744, "longitude": -71.15047,
         "rating": 4.9, "category": "Restaurant", "cid": "6382196640288619178"},
    ]
}

_WR_CENTER_NOMINATIM = [{"lat": "42.2843", "lon": "-71.1627"}]


class _FakeNominatim:
    """Serves the scope-centre geocode only; it NEVER returns a place list, so the
    cheap (Nominatim) tier a always misses — exactly the West Roxbury situation."""
    def __init__(self, geocode):
        self.geocode = geocode

    def __call__(self, params, context=""):
        q = (params.get("q") or "")
        # A bare scope string ("West Roxbury, MA") is a geocode; a search query
        # ("... in West Roxbury, MA") returns nothing (the free-OSM miss).
        data = self.geocode if " in " not in q.lower() and "restaurant" not in q.lower() else []

        class _R:
            def __init__(self, d):
                self._d = d

            def json(self):
                return self._d
        return _R(data)


@pytest.fixture
def wired(monkeypatch):
    """Serper transport = recorded JSON; DB seam = in-memory capture."""
    logged = []
    monkeypatch.setattr(el, "_log_escalation", lambda row: (logged.append(dict(row)) or True))
    monkeypatch.setattr(el, "_routing_start_tier", lambda c, r: None)
    monkeypatch.setattr(el, "_record_cheap_miss", lambda c, r, t: None)
    monkeypatch.setattr(el, "_check_daily_limit", lambda: None)
    monkeypatch.setattr(el, "_grounding_guard_active", lambda: False)

    ps.clear_cache()
    calls = {"n": 0}

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        calls["n"] += 1
        q = (payload.get("q") or "").lower()
        if "middle eastern" in q or "mediterranean" in q:
            return 200, json.dumps(_SERPER_WR_MIDEAST).encode("utf-8")
        return 200, json.dumps({"places": []}).encode("utf-8")

    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    monkeypatch.setattr(gate, "_nominatim_request", _FakeNominatim(_WR_CENTER_NOMINATIM))
    # The Serper env is what serper_places_enabled() reads; the wrapper flips it
    # per tier, so we provide a key and let the wrapper choose the provider.
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    return {"logged": logged, "serper_calls": calls}


class TestReplenishEscalation:
    def test_cheap_miss_escalates_to_serper_and_logs(self, wired):
        """West Roxbury Middle Eastern: the cheap tier misses (free OSM empty),
        the ladder escalates to Serper Places and returns the 3 local ones."""
        out = gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            cuisine="middle eastern", request_text="middle eastern restaurants near me")
        names = [c["name"] for c in out]
        # Serper rescued the real West Roxbury Middle-Eastern places (the 3 are
        # Al Wadi / Bread Thyme / Stardust; `needed`=2 keeps the 2 nearest).
        _expected = {"Al Wadi", "Bread Thyme", "Stardust: Inspired Mediterranean , Persian"}
        assert any(any(e in n for e in _expected) for n in names), names
        assert len(out) >= 1
        # Each candidate carries coordinates + the verified shape the caller needs.
        for c in out:
            assert c.get("coordinates") and c.get("lat") and c.get("lng")
            assert c.get("verified") is True
        # An escalation row was logged for the rescue.
        assert wired["logged"], "a lookup_escalations row should be logged"
        assert wired["logged"][-1]["tier_found"] == "b"

    def test_second_run_served_from_places_cache(self, wired):
        """A repeat of the SAME search within 24 h is served from the LOCAL-783
        places cache — no second Serper transport call for the bulk query."""
        gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            cuisine="middle eastern")
        first = wired["serper_calls"]["n"]
        assert first >= 1
        gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            cuisine="middle eastern")
        # The identical bulk query (same ll) is cached; the 2nd run makes no NEW
        # transport call for it. (Allow for at most the same count — never more
        # than a small constant; the key assertion is "no re-bill of the bulk q".)
        assert wired["serper_calls"]["n"] == first

    def test_force_cheap_miss_flag_still_reaches_serper(self, wired, monkeypatch):
        """With D722_FORCE_CHEAP_MISS=1 the cheap tier is skipped entirely and the
        ladder goes straight to Serper — the live-proof path."""
        monkeypatch.setenv("D722_FORCE_CHEAP_MISS", "1")
        out = gate.replenish_with_escalation(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            cuisine="middle eastern")
        _expected = {"Al Wadi", "Bread Thyme", "Stardust: Inspired Mediterranean , Persian"}
        assert any(any(e in c["name"] for e in _expected) for c in out), out
        assert wired["logged"][-1]["tier_found"] == "b"
