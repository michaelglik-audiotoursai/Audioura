#!/usr/bin/env python3
"""LOCAL-788 item 3/B — an Overpass outage must never silently shrink the
candidate list.

Evidence: GCloud tour 460 logged Overpass **502**. The old client logged the 5xx
and returned None — no mirror, no alternative provider — so a candidate path that
leaned on Overpass lost those candidates to an infrastructure outage.

The contract:
  1. a 5xx / timeout retries once on a second public MIRROR
     (osm_venue_facts._overpass_request walks primary + mirror endpoints);
  2. if every Overpass endpoint fails, continue with Serper Places using `ll` at
     the scope centre (overpass_fallback.query_pois_with_fallback).

Fixtures only — the HTTP layer and the Serper call are stubbed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osm_venue_facts
import overpass_fallback as ofb


# ─────────────── fake requests module driving the Overpass HTTP ─────────────
class _Resp:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"elements": []}
        self.text = "stub"

    def json(self):
        return self._body


class _FakeRequests:
    """Returns a per-endpoint status so a 502 primary + 200 mirror can be driven."""
    def __init__(self, by_url):
        self.by_url = by_url
        self.calls = []

        class _Exc:
            Timeout = type("Timeout", (Exception,), {})
            ConnectionError = type("ConnectionError", (Exception,), {})
        self.exceptions = _Exc

    def post(self, url, **kwargs):
        self.calls.append(url)
        status, body = self.by_url.get(url, (502, {"elements": []}))
        if isinstance(status, Exception):
            raise status
        return _Resp(status, body)


PRIMARY = "https://primary.example/api/interpreter"
MIRROR1 = "https://overpass.kumi.systems/api/interpreter"
MIRROR2 = "https://overpass.private.coffee/api/interpreter"


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(osm_venue_facts, "_OVERPASS_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(osm_venue_facts, "_overpass_last_request_time", 0.0)
    monkeypatch.setattr(osm_venue_facts, "_OVERPASS_URL", PRIMARY)
    monkeypatch.setattr(osm_venue_facts, "_OVERPASS_MIRRORS", [MIRROR1, MIRROR2])


# ──────────────────── 1) 502 primary → mirror is tried ──────────────────────
class TestMirrorRetry:
    def test_502_primary_falls_to_mirror(self, monkeypatch):
        body = {"elements": [{"type": "node", "lat": 42.28, "lon": -71.16,
                              "tags": {"name": "Al Wadi"}}]}
        fake = _FakeRequests({
            PRIMARY: (502, None),          # primary down
            MIRROR1: (200, body),          # mirror answers
        })
        monkeypatch.setitem(sys.modules, "requests", fake)
        out = osm_venue_facts._overpass_request("[out:json];node;out;", context="t")
        assert out == body
        assert fake.calls[0] == PRIMARY
        assert MIRROR1 in fake.calls  # the mirror WAS tried

    def test_all_endpoints_502_returns_none(self, monkeypatch):
        fake = _FakeRequests({
            PRIMARY: (502, None), MIRROR1: (502, None), MIRROR2: (503, None)})
        monkeypatch.setitem(sys.modules, "requests", fake)
        out = osm_venue_facts._overpass_request("[out:json];node;out;", context="t")
        assert out is None
        # Every endpoint was attempted — nothing silently skipped.
        assert PRIMARY in fake.calls and MIRROR1 in fake.calls and MIRROR2 in fake.calls

    def test_timeout_primary_falls_to_mirror(self, monkeypatch):
        fake = _FakeRequests({})  # default 502 for unknown; override with exc
        fake.by_url[PRIMARY] = (fake.exceptions.Timeout("slow"), None)
        fake.by_url[MIRROR1] = (200, {"elements": [
            {"type": "node", "lat": 42.28, "lon": -71.16,
             "tags": {"name": "Bread Thyme"}}]})
        monkeypatch.setitem(sys.modules, "requests", fake)
        out = osm_venue_facts._overpass_request("[out:json];node;out;", context="t")
        assert out and out["elements"][0]["tags"]["name"] == "Bread Thyme"


# ─────────── 2) all Overpass down → Serper fallback keeps candidates ─────────
class TestSerperFallback:
    def test_overpass_none_falls_to_serper(self):
        def _overpass_always_down(query, context=""):
            return None  # every endpoint failed

        def _fake_serper(query, scope, near=None, limit=25,
                         scope_center=None, scope_bbox=None):
            # Serper with `ll` at the scope centre returns the real in-scope places.
            return [
                {"name": "Al Wadi", "lat": 42.27725, "lon": -71.17266,
                 "address": {"road": "VFW Pkwy"}},
                {"name": "Stardust", "lat": 42.28744, "lon": -71.15047,
                 "address": {"road": "Centre St"}},
            ]

        out = ofb.query_pois_with_fallback(
            overpass_query="[out:json];node;out;",
            serper_query="middle eastern restaurants West Roxbury MA",
            scope="West Roxbury, MA",
            scope_center=(42.2843, -71.1627),
            overpass_request=_overpass_always_down,
            places_search_fn=_fake_serper)
        names = [c["name"] for c in out]
        assert names, "candidate list must be non-empty after Serper fallback"
        assert "Al Wadi" in names and "Stardust" in names
        assert all(c["source"] == "serper" for c in out)

    def test_overpass_hit_used_without_serper(self):
        def _overpass_hit(query, context=""):
            return {"elements": [{"type": "node", "lat": 42.28, "lon": -71.16,
                                  "tags": {"name": "Al Wadi"}}]}

        def _serper_must_not_run(*a, **k):
            raise AssertionError("Serper must not be called when Overpass answers")

        out = ofb.query_pois_with_fallback(
            overpass_query="[out:json];node;out;",
            serper_query="x", scope="West Roxbury, MA",
            overpass_request=_overpass_hit, places_search_fn=_serper_must_not_run)
        assert [c["name"] for c in out] == ["Al Wadi"]
        assert out[0]["source"] == "osm"

    def test_both_down_returns_empty_not_partial(self):
        out = ofb.query_pois_with_fallback(
            overpass_query="q", serper_query="q", scope="West Roxbury, MA",
            overpass_request=lambda q, context="": None,
            places_search_fn=lambda *a, **k: [])
        assert out == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
