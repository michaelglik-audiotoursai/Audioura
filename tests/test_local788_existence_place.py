#!/usr/bin/env python3
"""LOCAL-788 item 5 — existence verification must match the PLACE, not the NAME.

ADDENDUM (tour 460): "Kebab House had been 'verified' by a Wikipedia snippet about
Bitterne Park (UK)." Bitterne Park is a suburb of Southampton, England — a
same-named "Kebab House" on the other side of the Atlantic must NOT verify a
West Roxbury, MA stop. A snippet/page counts only if its location (the scope's
town / neighbourhood / postcode, or coords in scope) matches; a same-named place
in another country is a reject.

The guard: ``stop_existence_gate._text_contradicts_scope`` is applied at every
accept branch of ``_check_dining_existence`` — a title match alone (name, not
place) no longer verifies, and a snippet/summary that positively names a
contradicting place is rejected.

Fixtures only — the Wikipedia HTTP is stubbed.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_existence_gate as gate


# ──────────── unit: the contradiction guard in isolation ────────────────────
class TestContradictionGuard:
    def test_bitterne_park_uk_contradicts_west_roxbury(self):
        text = ("bitterne park is a suburb of southampton, hampshire, england, "
                "in the united kingdom. a kebab house operates on the parade.")
        sigs = {"west", "roxbury"}  # _city_signals for "West Roxbury, MA"
        assert gate._text_contradicts_scope(text, sigs) is True

    def test_in_scope_text_not_contradiction(self):
        text = ("kebab house is a middle eastern restaurant on centre street in "
                "west roxbury, a neighbourhood of boston, massachusetts.")
        sigs = {"west", "roxbury"}
        assert gate._text_contradicts_scope(text, sigs) is False

    def test_neutral_text_not_contradiction(self):
        # No geographic marker at all → not a contradiction (absence is not evidence).
        assert gate._text_contradicts_scope("a kebab house with great food", {"west", "roxbury"}) is False


# ──────────── integration: _check_dining_existence end-to-end ────────────────
# [LOCAL-788B] These integration cases use a DISTINCTIVELY-named place
# ("Sultan's Kebab", distinctive token "sultan") rather than the wholly generic
# "Kebab House". Under LOCAL-788B item 2 a generic-name place ("Kebab House") can
# NEVER be verified by a Wikipedia snippet/article — it must be found on the map —
# so the contradiction guard (item 5) is exercised here on a name that CAN carry
# Wikipedia evidence, keeping both rules co-tested.
_BITTERNE_SUMMARY = {
    "title": "Sultan's Kebab",
    "extract": ("Sultan's Kebab is a restaurant in Bitterne Park, a suburb of "
                "Southampton, Hampshire, England. It serves Middle Eastern food."),
    "description": "restaurant in Southampton, England",
}
_WR_SUMMARY_MISS = {"type": "https://mediawiki.org/wiki/HyperSwitch/errors/not_found"}

_WR_SEARCH_HIT = {
    "query": {"search": [{
        "title": "Centre Street, West Roxbury",
        "snippet": ("Sultan's Kebab is a Middle Eastern restaurant on Centre Street "
                    "in West Roxbury, Boston, Massachusetts."),
    }]}
}
_BITTERNE_SEARCH_HIT = {
    "query": {"search": [{
        "title": "Bitterne Park",
        "snippet": ("Sultan's Kebab is a restaurant in Bitterne Park, Southampton, "
                    "Hampshire, England, serving Middle Eastern cuisine."),
    }]}
}
_EMPTY_SEARCH = {"query": {"search": []}}


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _make_fake_requests(summary_payload, search_payload):
    class _FakeRequests:
        class exceptions:
            Timeout = type("Timeout", (Exception,), {})
            ConnectionError = type("ConnectionError", (Exception,), {})

        def get(self, url, **kwargs):
            if "/page/summary/" in url:
                if summary_payload is None:
                    return _FakeResp(404, _WR_SUMMARY_MISS)
                return _FakeResp(200, summary_payload)
            if "wikidata.org" in url:
                return _FakeResp(200, {"search": []})
            if "api.php" in url:
                # fr.wiki searches return empty; en.wiki returns the configured hit.
                if "fr.wikipedia.org" in url:
                    return _FakeResp(200, _EMPTY_SEARCH)
                return _FakeResp(200, search_payload)
            # Nominatim / OpenStreetMap structured search: an empty 200 (a clean
            # "searched, none found"), never a 404 that would raise RuntimeError.
            if "nominatim" in url or "openstreetmap" in url:
                return _FakeResp(200, [])
            return _FakeResp(200, [])

        def post(self, url, **kwargs):
            return _FakeResp(200, {})
    return _FakeRequests()


class TestDiningExistenceMatchesPlace:
    def test_bitterne_park_summary_does_not_verify_west_roxbury(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests",
                            _make_fake_requests(_BITTERNE_SUMMARY, _EMPTY_SEARCH))
        ok, evidence = gate._check_dining_existence(
            "Sultan's Kebab", "West Roxbury, MA", None)
        assert ok is False, f"a UK Bitterne Park article must NOT verify a West Roxbury stop (got {evidence})"

    def test_bitterne_park_snippet_does_not_verify(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests",
                            _make_fake_requests(None, _BITTERNE_SEARCH_HIT))
        ok, evidence = gate._check_dining_existence(
            "Sultan's Kebab", "West Roxbury, MA", None)
        assert ok is False, f"a Southampton/England snippet must not verify (got {evidence})"

    def test_real_west_roxbury_snippet_verifies(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests",
                            _make_fake_requests(None, _WR_SEARCH_HIT))
        ok, evidence = gate._check_dining_existence(
            "Sultan's Kebab", "West Roxbury, MA", None)
        assert ok is True, "a genuine West Roxbury snippet (distinctive token) must still verify"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
