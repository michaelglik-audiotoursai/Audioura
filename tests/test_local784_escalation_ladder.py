"""LOCAL-784 / D722: the escalation ladder before "nothing found", the escalation
log, and learned routing.

Red-first, recorded fixtures only — NO live web, NO DB. The escalation ladder is
driven with stub tier callables; the DB seam (lookup_escalations insert, the
lookup_routing read/upsert) is replaced with an in-memory fake so the log rows
and routing state are asserted directly. The Serper Places transport, where a
test exercises the real replenish path, is the SAME recorded capture LOCAL-783
used (Al Wadi / Bread Thyme / Stardust), monkeypatched onto places_search.

What it proves (the LOCAL-784 contract, D722):
  * A cheap-tier MISS with a Serper (tier b) hit → tier b used, an escalation row
    is logged, and the result is the Serper set (which the LOCAL-783 cache fills).
  * Places empty with a grounded-Gemini (tier c) hit → tier c, EACH result is
    re-verified, and an UNVERIFIABLE Gemini name is DROPPED.
  * All tiers empty → an honest refusal (empty result) PLUS a logged 'none' row.
  * The per-request budget cap STOPS escalation before a tier it cannot afford.
  * The routing table kicks in: after >= 3 cheap-tier misses for a (category,
    region) the ladder STARTS at the tier that worked, skipping the cheap call.
  * A tier-a hit (cheap path sufficed) writes NO row (no escalation happened).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import escalating_lookup as el


# ───────────────────────── in-memory DB fake ────────────────────────────────
class FakeStore:
    """Captures lookup_escalations rows and holds a lookup_routing table in
    memory, so the ladder's log + routing are asserted without a database."""

    def __init__(self):
        self.escalations = []                 # list of row dicts
        self.routing = {}                     # (category, region_key) -> dict

    # -- escalation log --
    def log(self, row):
        self.escalations.append(dict(row))
        return True

    # -- routing read --
    def start_tier(self, category, region_key):
        r = self.routing.get((category, region_key))
        if not r:
            return None
        if int(r.get("misses_7d", 0)) >= el._ROUTE_MISS_THRESHOLD and \
                r.get("start_tier") in ("b", "c"):
            return r["start_tier"]
        return None

    # -- routing upsert on a cheap miss --
    def record_miss(self, category, region_key, worked_tier):
        key = (category, region_key)
        r = self.routing.get(key)
        misses = 1 if r is None else int(r.get("misses_7d", 0)) + 1
        start = worked_tier if misses >= el._ROUTE_MISS_THRESHOLD else "a"
        if r is not None and misses < el._ROUTE_MISS_THRESHOLD:
            start = r.get("start_tier", "a")
        self.routing[key] = {"start_tier": start, "misses_7d": misses}


@pytest.fixture
def store(monkeypatch):
    """Install the in-memory DB fake onto escalating_lookup and keep the budget at
    its default $0.10. Also neutralise the daily-limit check and the grounding
    guard so a unit test is deterministic."""
    s = FakeStore()
    monkeypatch.setattr(el, "_log_escalation", s.log)
    monkeypatch.setattr(el, "_routing_start_tier", s.start_tier)
    monkeypatch.setattr(el, "_record_cheap_miss", s.record_miss)
    monkeypatch.setattr(el, "_check_daily_limit", lambda: None)
    monkeypatch.setattr(el, "_grounding_guard_active", lambda: False)
    monkeypatch.delenv("D722_FORCE_CHEAP_MISS", raising=False)
    # Pin the budget to the documented default regardless of the dev env.
    monkeypatch.setattr(el, "_BUDGET_USD", 0.10)
    return s


# ───────────────────────── the five required cases ──────────────────────────
class TestLadder:
    def test_tier_a_suffices_writes_no_row(self, store):
        """The cheap path already returns >= needed → no escalation, no row."""
        r = el.escalating_lookup(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            tier_a=lambda: [{"name": "A"}, {"name": "B"}],
            tier_b=lambda: [{"name": "SHOULD-NOT-RUN"}])
        assert r.tier_found == "a"
        assert [x["name"] for x in r.results] == ["A", "B"]
        assert r.logged is False
        assert store.escalations == []          # tier-a hit writes NO row

    def test_cheap_miss_then_tier_b_logged(self, store):
        """Cheap miss + a Serper (tier b) hit → tier b, a row IS logged."""
        r = el.escalating_lookup(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            tier_a=lambda: [],                         # cheap OSM finds nothing
            tier_b=lambda: [{"name": "Al Wadi"}, {"name": "Bread Thyme"}],
            category="middle eastern",
            scope_center=(42.2794, -71.1595))
        assert r.tier_found == "b"
        assert [x["name"] for x in r.results] == ["Al Wadi", "Bread Thyme"]
        assert r.logged is True
        assert len(store.escalations) == 1
        row = store.escalations[0]
        assert row["tier_found"] == "b"
        assert row["kind"] == "dining"
        assert row["category"] == "middle eastern"
        # results_by_tier records what each tier returned (a empty, b the rescue).
        rbt = json.loads(row["results_by_tier"])
        assert rbt["a"] == [] and rbt["b"] == ["Al Wadi", "Bread Thyme"]
        assert row["cost_usd"] > 0              # tier b spent (metered/estimate)

    def test_tier_c_reverifies_and_drops_unverifiable(self, store, monkeypatch):
        """Places empty, grounded Gemini returns a list; EACH name is re-verified
        and an unverifiable one is DROPPED."""
        monkeypatch.setattr(el, "_tier_c_gemini", lambda cat, scope, lim: [
            {"name": "Stardust", "address": "1753 Centre St"},
            {"name": "Ghost Cafe", "address": "nowhere at all"},   # unverifiable
            {"name": "Rami's", "address": "1737 Centre St"},
        ])

        def verify(name):
            # The map confirms Stardust and Rami's; Ghost Cafe is not there.
            if name in ("Stardust", "Rami's"):
                return {"name": name, "verified": True,
                        "coordinates": "42.28,-71.15"}
            return None

        r = el.escalating_lookup(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            tier_a=lambda: [], tier_b=lambda: [], verify=verify,
            category="middle eastern", scope_center=(42.2794, -71.1595))
        assert r.tier_found == "c"
        assert [x["name"] for x in r.results] == ["Stardust", "Rami's"]
        # Ghost Cafe was dropped: it is NOT in the verified results, and the log
        # records only the verified names for tier c.
        rbt = json.loads(store.escalations[0]["results_by_tier"])
        assert "Ghost Cafe" not in rbt["c"]
        assert rbt["c"] == ["Stardust", "Rami's"]
        assert r.logged is True

    def test_all_tiers_empty_refusal_and_none_row(self, store, monkeypatch):
        """Nothing anywhere → empty result (honest refusal) + a logged 'none' row."""
        monkeypatch.setattr(el, "_tier_c_gemini", lambda cat, scope, lim: [])
        r = el.escalating_lookup(
            "dining", "yak-wool cafes", "West Roxbury, MA", 2,
            tier_a=lambda: [], tier_b=lambda: [],
            verify=lambda n: None, category="yak-wool cafe",
            scope_center=(42.2794, -71.1595))
        assert r.tier_found == "none"
        assert r.results == []
        assert r.logged is True
        row = store.escalations[0]
        assert row["tier_found"] == "none"
        rbt = json.loads(row["results_by_tier"])
        assert rbt.get("a") == [] and rbt.get("b") == [] and rbt.get("c") == []

    def test_budget_cap_stops_escalation(self, store, monkeypatch):
        """A tight budget stops the ladder before a tier it cannot afford."""
        # Budget below tier c's estimate (0.06): tier b runs (0.004), tier c is
        # blocked before the Gemini call.
        monkeypatch.setattr(el, "_BUDGET_USD", 0.005)
        tier_c_called = {"v": False}

        def gemini(cat, scope, lim):
            tier_c_called["v"] = True
            return [{"name": "X", "address": "y"}]
        monkeypatch.setattr(el, "_tier_c_gemini", gemini)

        verify_called = {"v": False}

        def verify(name):
            verify_called["v"] = True
            return {"name": name}

        r = el.escalating_lookup(
            "dining", "q", "West Roxbury, MA", 2,
            tier_a=lambda: [], tier_b=lambda: [], verify=verify,
            category="cat", scope_center=(42.2794, -71.1595))
        assert r.tier_found == "none"
        assert tier_c_called["v"] is False      # Gemini never called — budget cap
        assert verify_called["v"] is False

    def test_routing_kicks_in_after_three_misses(self, store):
        """After >= 3 cheap-tier misses for a (category, region), the ladder STARTS
        at the tier that worked and SKIPS the cheap call."""
        center = (42.2794, -71.1595)
        tier_a_calls = {"n": 0}

        def tier_a():
            tier_a_calls["n"] += 1
            return []                            # cheap tier keeps missing

        def tier_b():
            return [{"name": "Al Wadi"}, {"name": "Bread Thyme"}]

        # Misses 1, 2, 3 — tier a is CALLED each time (still learning), tier b
        # rescues each time.
        for i in range(3):
            r = el.escalating_lookup(
                "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
                tier_a=tier_a, tier_b=tier_b, category="middle eastern",
                scope_center=center)
            assert r.tier_found == "b"
        assert tier_a_calls["n"] == 3
        # The 4th lookup: routing is now promoted to 'b' (3 misses >= threshold),
        # so the ladder STARTS at tier b and does NOT call tier a again.
        r = el.escalating_lookup(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            tier_a=tier_a, tier_b=tier_b, category="middle eastern",
            scope_center=center)
        assert r.tier_found == "b"
        assert tier_a_calls["n"] == 3           # tier a was SKIPPED on the 4th
        # The routing row is a reversible lever.
        key = ("middle eastern", el.region_key_for(center, "West Roxbury, MA"))
        assert store.routing[key]["start_tier"] == "b"
        assert store.routing[key]["misses_7d"] >= 3


# ───────────────────── force-cheap-miss (live-proof flag) ────────────────────
class TestForceCheapMiss:
    def test_force_cheap_miss_env_empties_tier_a(self, store, monkeypatch):
        """D722_FORCE_CHEAP_MISS=1 forces tier a empty even when it would answer,
        so the ladder can be exercised live. tier b then rescues."""
        monkeypatch.setenv("D722_FORCE_CHEAP_MISS", "1")
        tier_a_called = {"v": False}

        def tier_a():
            tier_a_called["v"] = True
            return [{"name": "would-have-answered"}]

        r = el.escalating_lookup(
            "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
            tier_a=tier_a, tier_b=lambda: [{"name": "Al Wadi"}, {"name": "Bread Thyme"}],
            category="middle eastern", scope_center=(42.2794, -71.1595))
        assert tier_a_called["v"] is False       # forced miss → tier a not called
        assert r.tier_found == "b"


# ─────────────────────────── geohash / region_key ───────────────────────────
class TestRegionKey:
    def test_geohash5_west_roxbury(self):
        gh = el.geohash5(42.2794, -71.1595)
        assert len(gh) == 5
        # Stable value for West Roxbury (deterministic encoder).
        assert gh == "drt2s"

    def test_region_key_prefers_geohash(self):
        assert el.region_key_for((42.2794, -71.1595), "West Roxbury, MA") == "drt2s"

    def test_region_key_text_fallback_without_center(self):
        rk = el.region_key_for(None, "West Roxbury, MA")
        assert rk.startswith("t:") and "west roxbury" in rk


# ──────────────── tier-c JSON parsing (grounded Gemini output) ───────────────
class TestTierCParsing:
    def test_parses_plain_json_array(self):
        out = el._parse_tier_c_json(
            '[{"name":"Al Wadi","address":"1249 VFW Pkwy"}]')
        assert out == [{"name": "Al Wadi", "address": "1249 VFW Pkwy"}]

    def test_parses_fenced_json(self):
        text = '```json\n[{"name":"Bread Thyme","address":"1866 Centre St"}]\n```'
        out = el._parse_tier_c_json(text)
        assert out and out[0]["name"] == "Bread Thyme"

    def test_parses_json_with_prose_around_it(self):
        text = ('Here are the places:\n'
                '[{"name":"Stardust","address":"1753 Centre St"}]\nHope that helps!')
        out = el._parse_tier_c_json(text)
        assert out and out[0]["name"] == "Stardust"

    def test_unparseable_returns_empty(self):
        assert el._parse_tier_c_json("sorry, I could not find any") == []
        assert el._parse_tier_c_json("") == []


# ─────────── grounding guard: by-reference path skips tier c (and b) ─────────
class TestGroundingGuard:
    def test_allow_grounding_false_skips_tier_c(self, store, monkeypatch):
        monkeypatch.setattr(el, "_tier_c_gemini",
                            lambda *a: pytest.fail("tier c must not run"))
        r = el.escalating_lookup(
            "by_reference", "Some Named Place", "Some Named Place", 2,
            tier_a=lambda: [], tier_b=None,
            verify=lambda n: {"name": n}, allow_grounding=False,
            category="museum")
        assert r.tier_found == "none"
        assert r.logged is True
        assert store.escalations[0]["tier_found"] == "none"

    def test_active_grounding_guard_skips_tier_c(self, store, monkeypatch):
        monkeypatch.setattr(el, "_grounding_guard_active", lambda: True)
        monkeypatch.setattr(el, "_tier_c_gemini",
                            lambda *a: pytest.fail("tier c must not run under guard"))
        r = el.escalating_lookup(
            "dining", "q", "West Roxbury, MA", 2,
            tier_a=lambda: [], tier_b=lambda: [], verify=lambda n: {"name": n},
            category="cat", scope_center=(42.2794, -71.1595))
        assert r.tier_found == "none"
