#!/usr/bin/env python3
"""test_local637_resolver_robustness.py — venue resolution survives rate limits
and never takes a band for a museum.

Both failures reproduced from the real Bench R6 generator.log lines and QIDs,
with INJECTED 429s. Everything is offline/mocked (monkeypatch requests.get,
time.sleep, dead_host_breaker). No network.

Bench R6 evidence:
  1. National Gallery (Q180788, 389 works), resolved earlier in the same run:
       [DEAD-HOST] Marked cold: wikimedia (HTTP 429 on _search_entities)
       _search_entities failed: HTTP 429 for query 'London'
       Single candidate Q180788 (National Gallery) failed city validation for 'London'
       No Wikidata candidates
     A RATE LIMIT rejected a correct venue. Six tours ran at once.
  2. Wallace Collection resolved Q1516598 (the Belgian pop-rock BAND, enwiki
     'Wallace Collection (band)'), and story_miner accepted the band article as
     the museum's corpus "on venue-name match".

What is proven here:
  A. _request_with_backoff retries 429/5xx with backoff + Retry-After and only
     marks the host cold AFTER the retries are exhausted.
  B. _is_located_in / _validate_city_match are TRI-STATE: a 429 is UNKNOWN
     (None), not "wrong city" (False).
  C. resolve_venue KEEPS the already-resolved high-confidence National Gallery
     candidate (Q180788, 389 works) when city validation is UNKNOWN under a 429.
  D. The dead-host breaker's per-tour cold mark is a short COOL-DOWN: a cold host
     is retried once the cool-down elapses (one 429 is not a run-wide failure).
  E. A Wikipedia title with a non-museum parenthetical qualifier ('(band)', ...)
     is rejected for a museum venue; '(museum)'/'(London)'/no-qualifier accepted.

Run:  python3 -m pytest test_local637_resolver_robustness.py -q
"""
import time
import unittest

import requests

import dead_host_breaker as dhb
import story_miner as sm
import venue_resolver as vr


NG_QID = "Q180788"              # National Gallery, London — 389 works
WALLACE_MUSEUM = "Q1327919"     # Wallace Collection — art museum, 674 works
WALLACE_BAND = "Q1516598"       # "Wallace Collection" — Belgian pop-rock band


class _Resp:
    """Minimal fake requests.Response."""
    def __init__(self, code, payload=None, headers=None):
        self.status_code = code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload


# ─────────────────────────────────────────────────────────────────────────────
# A. _request_with_backoff: 429/5xx retry + Retry-After, cold only after exhaust
# ─────────────────────────────────────────────────────────────────────────────
class TestRequestBackoff(unittest.TestCase):
    def setUp(self):
        self._orig_get = requests.get
        self._orig_sleep = time.sleep
        self._slept = []
        time.sleep = lambda s=0, *_a, **_k: self._slept.append(s)

    def tearDown(self):
        requests.get = self._orig_get
        time.sleep = self._orig_sleep

    def test_429_then_200_recovers_without_cold(self):
        seq = [_Resp(429), _Resp(200, {"ok": 1})]
        state = {"i": 0, "cold": []}
        requests.get = lambda *a, **k: seq[min(state.__setitem__("i", state["i"] + 1) or state["i"] - 1, len(seq) - 1)]
        resp = vr._request_with_backoff(
            "https://www.wikidata.org/w/api.php",
            params={}, headers={}, timeout=10,
            host_for_cold="https://www.wikidata.org", label="t")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(state["i"], 2)  # retried once

    def test_all_429_marks_cold_after_exhaustion_only(self):
        state = {"i": 0, "cold": 0}

        def _get(*a, **k):
            state["i"] += 1
            return _Resp(429)

        requests.get = _get
        orig_mark = dhb.mark_host_cold
        dhb.mark_host_cold = lambda *a, **k: state.__setitem__("cold", state["cold"] + 1)
        try:
            resp = vr._request_with_backoff(
                "https://www.wikidata.org/w/api.php",
                params={}, headers={}, timeout=10,
                host_for_cold="https://www.wikidata.org", label="t")
        finally:
            dhb.mark_host_cold = orig_mark
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(state["i"], 4)       # first + 3 retries
        self.assertEqual(state["cold"], 1)    # cold ONLY after exhaustion

    def test_retry_after_header_is_honoured(self):
        seq = [_Resp(429, headers={"Retry-After": "3"}), _Resp(200, {"ok": 1})]
        state = {"i": 0}

        def _get(*a, **k):
            r = seq[min(state["i"], len(seq) - 1)]
            state["i"] += 1
            return r

        requests.get = _get
        resp = vr._request_with_backoff(
            "https://www.wikidata.org/w/api.php",
            params={}, headers={}, timeout=10,
            host_for_cold=None, label="t")
        self.assertEqual(resp.status_code, 200)
        # The injected Retry-After (3s) governs the wait, not the 2s schedule.
        self.assertTrue(self._slept, "expected a sleep between attempts")
        self.assertGreaterEqual(self._slept[0], 3.0)

    def test_parse_retry_after_seconds_and_bad(self):
        self.assertEqual(vr._parse_retry_after("5"), 5.0)
        self.assertEqual(vr._parse_retry_after("0"), 0.0)
        self.assertIsNone(vr._parse_retry_after(""))
        self.assertIsNone(vr._parse_retry_after("not-a-date"))


# ─────────────────────────────────────────────────────────────────────────────
# B + C. Tri-state city validation; NG kept under 429 UNKNOWN
# ─────────────────────────────────────────────────────────────────────────────
class TestCityValidationTriState(unittest.TestCase):
    def setUp(self):
        self._orig_sleep = time.sleep
        time.sleep = lambda *_a, **_k: None

    def tearDown(self):
        time.sleep = self._orig_sleep

    def test_is_located_in_network_failure_is_none(self):
        # Every request 429s → _is_located_in cannot verify → None (UNKNOWN),
        # NOT False (which the old code returned and which discarded the NG).
        orig = vr._request_with_backoff
        vr._request_with_backoff = lambda *a, **k: _Resp(429)
        try:
            self.assertIsNone(vr._is_located_in(NG_QID, "London"))
        finally:
            vr._request_with_backoff = orig

    def test_validate_city_match_unknown_on_geocode_failure(self):
        # P131 unknown (None) + geocode network failure (None,None) → UNKNOWN.
        orig_loc = vr._is_located_in
        orig_geo = vr._geocode_city
        vr._is_located_in = lambda q, c: None
        vr._geocode_city = lambda c: (None, None)
        try:
            self.assertIsNone(vr._validate_city_match(NG_QID, "London"))
        finally:
            vr._is_located_in = orig_loc
            vr._geocode_city = orig_geo

    def test_validate_city_match_false_is_verified_not_in_city(self):
        # P131 completed and said not-in-city (False) AND the city has coords but
        # the entity has none (0.0,0.0) → a real not-in-city verdict (False).
        orig_loc = vr._is_located_in
        orig_geo = vr._geocode_city
        orig_coord = vr._get_coordinates
        vr._is_located_in = lambda q, c: False
        vr._geocode_city = lambda c: (51.5, -0.12)
        vr._get_coordinates = lambda q: (0.0, 0.0)
        try:
            self.assertIs(vr._validate_city_match(NG_QID, "London"), False)
        finally:
            vr._is_located_in = orig_loc
            vr._geocode_city = orig_geo
            vr._get_coordinates = orig_coord

    def test_high_confidence_national_gallery_kept_when_unknown(self):
        # The exact Bench R6 case. One museum-typed candidate (NG, Q180788) is
        # resolved; city validation is UNKNOWN (429). Because the candidate is
        # high-confidence (label match + 389 works) it is KEPT, not discarded.
        orig = {
            "norm": vr._normalise_venue_name,
            "search": vr._search_entities,
            "disamb": vr._filter_disambiguation_pages,
            "inst": vr._get_instance_of,
            "subent": vr.prefer_parent_institution,
            "valid": vr._validate_city_match,
            "wc": vr._fetch_works_count,
            "props": vr._fetch_entity_properties,
        }
        vr._normalise_venue_name = lambda s: ["The National Gallery", "National Gallery"]
        vr._search_entities = lambda q: [(NG_QID, "National Gallery")]
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: "Q207694"  # art museum
        vr.prefer_parent_institution = lambda c, *a, **k: c
        vr._validate_city_match = lambda q, c: None        # UNKNOWN (429)
        vr._fetch_works_count = lambda q: (389, 5)          # large catalogue
        _built = {}

        def _props(qid, label):
            _built["qid"] = qid
            e = vr.VenueEntity(qid=qid, name=label)
            return e

        vr._fetch_entity_properties = _props
        try:
            ent = vr.resolve_venue("The National Gallery", "London")
        finally:
            vr._normalise_venue_name = orig["norm"]
            vr._search_entities = orig["search"]
            vr._filter_disambiguation_pages = orig["disamb"]
            vr._get_instance_of = orig["inst"]
            vr.prefer_parent_institution = orig["subent"]
            vr._validate_city_match = orig["valid"]
            vr._fetch_works_count = orig["wc"]
            vr._fetch_entity_properties = orig["props"]
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, NG_QID)

    def test_low_confidence_candidate_not_kept_when_unknown(self):
        # Same UNKNOWN validation, but the candidate holds NO collection (0 works)
        # → not high-confidence → NOT kept just because validation stalled. (It is
        # discarded; with no city-qualified replacement the resolve returns None.)
        orig = {
            "norm": vr._normalise_venue_name,
            "search": vr._search_entities,
            "disamb": vr._filter_disambiguation_pages,
            "inst": vr._get_instance_of,
            "subent": vr.prefer_parent_institution,
            "valid": vr._validate_city_match,
            "wc": vr._fetch_works_count,
        }
        vr._normalise_venue_name = lambda s: ["Imaginary Museum"]
        vr._search_entities = lambda q: [("Q99999999", "Imaginary Museum")] if "in" not in q else []
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: "Q33506"
        vr.prefer_parent_institution = lambda c, *a, **k: c
        vr._validate_city_match = lambda q, c: None
        vr._fetch_works_count = lambda q: (0, 0)
        try:
            ent = vr.resolve_venue("Imaginary Museum", "Nowhere")
        finally:
            vr._normalise_venue_name = orig["norm"]
            vr._search_entities = orig["search"]
            vr._filter_disambiguation_pages = orig["disamb"]
            vr._get_instance_of = orig["inst"]
            vr.prefer_parent_institution = orig["subent"]
            vr._validate_city_match = orig["valid"]
            vr._fetch_works_count = orig["wc"]
        self.assertIsNone(ent)


# ─────────────────────────────────────────────────────────────────────────────
# D. Dead-host breaker: short cool-down, retried after it elapses
# ─────────────────────────────────────────────────────────────────────────────
class TestDeadHostCooldown(unittest.TestCase):
    def test_tour_cold_is_a_cooldown_not_permanent(self):
        token = dhb.begin_tour_scope()
        try:
            dhb.mark_host_cold("https://www.wikidata.org", reason="HTTP 429")
            self.assertTrue(dhb.is_host_cold("https://www.wikidata.org"))
            # Simulate the cool-down elapsing by rewinding the stored mark time.
            cold = dhb._tour_cold_hosts.get()
            self.assertIsInstance(cold, dict)
            for h in list(cold):
                cold[h] -= (dhb._TOUR_COLD_COOLDOWN_SECONDS + 1.0)
            # After the cool-down the host is retriable (no longer cold).
            self.assertFalse(dhb.is_host_cold("https://www.wikidata.org"))
        finally:
            dhb.end_tour_scope(token)

    def test_within_cooldown_still_cold(self):
        token = dhb.begin_tour_scope()
        try:
            dhb.mark_host_cold("https://en.wikipedia.org", reason="HTTP 429")
            # Immediately after marking (well within the cool-down) it IS cold.
            self.assertTrue(dhb.is_host_cold("https://en.wikipedia.org"))
            # Wikimedia bucket: wikidata shares the same cold mark.
            self.assertTrue(dhb.is_host_cold("https://www.wikidata.org"))
        finally:
            dhb.end_tour_scope(token)


# ─────────────────────────────────────────────────────────────────────────────
# E. Disambiguation guard: a band/album/film title is never a museum corpus
# ─────────────────────────────────────────────────────────────────────────────
class TestParentheticalQualifierGuard(unittest.TestCase):
    def test_band_qualifier_rejected(self):
        self.assertTrue(sm._title_qualifier_rejects_museum("Wallace Collection (band)"))

    def test_creative_work_qualifiers_rejected(self):
        for t in ("X (album)", "Y (film)", "Z (song)", "W (TV series)",
                  "V (video game)", "U (novel)"):
            self.assertTrue(sm._title_qualifier_rejects_museum(t), t)

    def test_museum_and_place_qualifiers_accepted(self):
        for t in ("Wallace Collection", "Wallace Collection (museum)",
                  "Something (gallery)", "Something (London)", "Foo (Nice)",
                  "Bar (institution)"):
            self.assertFalse(sm._title_qualifier_rejects_museum(t), t)

    def test_parenthetical_extraction(self):
        self.assertEqual(sm._parenthetical_qualifier("Wallace Collection (band)"), "band")
        self.assertEqual(sm._parenthetical_qualifier("Wallace Collection"), "")


# ─────────────────────────────────────────────────────────────────────────────
# Wallace Collection: normalisation surfaces the museum, not the band
# ─────────────────────────────────────────────────────────────────────────────
class TestWallaceNormalisation(unittest.TestCase):
    def test_leading_the_stripped_variant_present(self):
        variants = vr._normalise_venue_name("The Wallace Collection")
        self.assertIn("The Wallace Collection", variants)
        self.assertIn("Wallace Collection", variants)

    def test_resolve_prefers_museum_type_over_band(self):
        # Candidate set as returned by the two searches ('The Wallace Collection'
        # → band + caricature; article-stripped 'Wallace Collection' → museum).
        # The band is NOT museum-typed; the museum is. The P31 filter must pick
        # the museum (Q1327919), never the band (Q1516598).
        _p31 = {
            WALLACE_BAND: None,          # musical group — not a museum type
            "Q106500505": None,          # caricature — not a museum type
            WALLACE_MUSEUM: "Q207694",   # art museum
            "Q133013000": None,
            "Q81165477": None,
        }
        orig = {
            "search": vr._search_entities,
            "disamb": vr._filter_disambiguation_pages,
            "inst": vr._get_instance_of,
            "subent": vr.prefer_parent_institution,
            "valid": vr._validate_city_match,
            "props": vr._fetch_entity_properties,
        }

        def _search(q):
            if q.strip().lower().startswith("the wallace collection") or q.strip() == "The Wallace Collection":
                return [(WALLACE_BAND, "Wallace Collection"), ("Q106500505", "The Wallace Collection")]
            if q.strip() == "Wallace Collection":
                return [(WALLACE_MUSEUM, "Wallace Collection"),
                        (WALLACE_BAND, "Wallace Collection")]
            return []

        vr._search_entities = _search
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: _p31.get(q)
        vr.prefer_parent_institution = lambda c, *a, **k: c
        vr._validate_city_match = lambda q, c: True
        vr._fetch_entity_properties = lambda qid, label: vr.VenueEntity(qid=qid, name=label)
        try:
            ent = vr.resolve_venue("The Wallace Collection", "London")
        finally:
            vr._search_entities = orig["search"]
            vr._filter_disambiguation_pages = orig["disamb"]
            vr._get_instance_of = orig["inst"]
            vr.prefer_parent_institution = orig["subent"]
            vr._validate_city_match = orig["valid"]
            vr._fetch_entity_properties = orig["props"]
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, WALLACE_MUSEUM)


if __name__ == "__main__":
    unittest.main(verbosity=2)
