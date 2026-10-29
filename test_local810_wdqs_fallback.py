#!/usr/bin/env python3
"""test_local810_wdqs_fallback.py — LOCAL-810.

A slow Wikidata (WDQS SPARQL ReadTimeout / 429) must NOT fail a whole museum
tour. Evidence (LOCAL-809 live run, 2026-10-29): "Metropolitan Museum of Art,
New York" — the model's candidates were all real Met works, but
fetch_venue_works(Q160236) hit WDQS ReadTimeout ×4 → 0 canonical titles → the
tour cleanly FAILED.

LOCAL-810 fix, verified here:
  1. The bounded venue-works query raises WDQSUnavailable on timeout/429/5xx.
  2. fetch_venue_works then runs a fallback chain:
       (a) per-candidate P195/P276 checks (one small query per proposed title),
       (b) the museum's own site listing,
       (c) Wikipedia highlights.
     The FIRST source with works wins and logs
     `[LOCAL-810] venue works fallback <qid> <source> <n>`.
  3. A per-QID cache (venue_works_cache, 30-day expiry) is consulted first: a
     cache HIT skips the SPARQL query entirely.
  4. A clean SPARQL result (regression) is returned and cached unchanged.

These tests are fully offline: the WDQS transport and the DB cache are injected.

Run: python3 -m pytest test_local810_wdqs_fallback.py -q
"""
import types
import unittest

import venue_resolver as vr


MET_QID = "Q160236"
# The LOCAL-809 evidence: the model proposed REAL Met works.
MET_CANDIDATES = [
    "Washington Crossing the Delaware",
    "The Death of Socrates",
    "Self-Portrait with a Straw Hat",
    "Madame X",
    "The Harvesters",
]


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"results": {"bindings": []}}
        self.headers = {}

    def json(self):
        return self._payload


def _sparql_binding(work_qid, label, sitelinks=5, creator="A. Painter"):
    """One WDQS result row shaped like the per-candidate / full query output."""
    return {
        "work": {"value": f"http://www.wikidata.org/entity/{work_qid}"},
        "workLabel": {"value": label},
        "workLabel_en": {"value": label},
        "sitelinks": {"value": str(sitelinks)},
        "creators": {"value": creator},
        "instanceOfs": {"value": "http://www.wikidata.org/entity/Q3305213"},
    }


class _BaseHarness(unittest.TestCase):
    def setUp(self):
        self._saved = {}
        for name in ("venue_works_cache_get", "venue_works_cache_put",
                     "_request_with_backoff", "_fallback_museum_site",
                     "_fallback_wikipedia_highlights"):
            self._saved[name] = getattr(vr, name)
        # Default: DB cache is a no-op (miss on get, swallow put) so tests drive
        # the SPARQL/fallback path explicitly.
        vr.venue_works_cache_get = lambda qid, language="en": None
        self._puts = []
        vr.venue_works_cache_put = lambda qid, lang, works, source="sparql": \
            self._puts.append((qid, lang, list(works), source))
        # Keep site/wiki fallbacks inert unless a test opts in.
        vr._fallback_museum_site = lambda *a, **k: []
        vr._fallback_wikipedia_highlights = lambda *a, **k: []

    def tearDown(self):
        for name, val in self._saved.items():
            setattr(vr, name, val)


class _FakeRequests:
    """Minimal stand-in for the `requests` module used by the per-candidate
    check (vr.requests.get). Serves a Met-collection membership answer for a
    known real work, an empty result otherwise."""
    class exceptions:
        Timeout = vr.requests.exceptions.Timeout
        ConnectionError = vr.requests.exceptions.ConnectionError

    def __init__(self, known_titles):
        self._known = {t.lower() for t in known_titles}

    def get(self, url, *, params=None, headers=None, timeout=10):
        q = (params or {}).get("query", "")
        for cand in self._known:
            if cand in q.lower():
                # Recover the original-cased title for the label.
                return _FakeResp(200, {"results": {"bindings": [
                    _sparql_binding("Q" + str(abs(hash(cand)) % 99999), cand)]}})
        return _FakeResp(200, {"results": {"bindings": []}})


class TestTimeoutPerCandidate(_BaseHarness):
    """WDQS times out on the heavy query → per-candidate path delivers works."""

    def _install(self, known_titles):
        # Heavy query (via _request_with_backoff) → ReadTimeout (None).
        vr._request_with_backoff = lambda *a, **k: None
        # Per-candidate query (via requests.get) → real-WDQS-style answer.
        self._saved_requests = vr.requests
        vr.requests = _FakeRequests([t.lower() for t in known_titles])

    def tearDown(self):
        if hasattr(self, "_saved_requests"):
            vr.requests = self._saved_requests
        super().tearDown()

    def test_timeout_then_per_candidate_delivers_n_stops(self):
        self._install([t.lower() for t in MET_CANDIDATES])
        works = vr._fetch_venue_works_cached(
            MET_QID, "en", venue_name="Metropolitan Museum of Art",
            candidate_titles=MET_CANDIDATES)

        got = {w["label_en"].lower() for w in works}
        self.assertEqual({t.lower() for t in MET_CANDIDATES}, got,
                         f"per-candidate fallback must confirm every real Met "
                         f"work; got {sorted(got)}")
        # Every returned work carries the Met QID as its collection (P195/P276).
        for w in works:
            self.assertIn(MET_QID, w.get("collection_qids", []))
        # A non-empty fallback result is cached for the repeat tour.
        self.assertTrue(self._puts, "fallback works must be cached")
        self.assertEqual("fallback", self._puts[-1][3])

    def test_timeout_logs_fallback_source(self):
        self._install([MET_CANDIDATES[0].lower()])
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vr._fetch_venue_works_cached(
                MET_QID, "en", venue_name="Metropolitan Museum of Art",
                candidate_titles=MET_CANDIDATES[:1])
        out = buf.getvalue()
        self.assertIn(f"[LOCAL-810] venue works fallback {MET_QID} per_candidate",
                      out, "fallback must log the required line")


class TestCountOnlyCallDoesNotFallback(_BaseHarness):
    """A count-only ranking call (no candidate_titles/official_url/wiki_title)
    must NOT run or cache the fallback on WDQSUnavailable — it returns [] so the
    later candidate-aware corpus call still gets the precise per-candidate path."""

    def test_count_only_call_returns_empty_and_caches_nothing(self):
        vr._request_with_backoff = lambda *a, **k: None  # heavy query times out
        # If the fallback ran, these would raise.
        vr._fallback_museum_site = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("count-only call must not run the fallback"))
        vr._fallback_wikipedia_highlights = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("count-only call must not run the fallback"))
        works = vr._fetch_venue_works_cached(MET_QID, "en", venue_name="Met")
        self.assertEqual([], works)
        self.assertFalse(self._puts, "count-only call must cache nothing")


class TestTimeoutSiteThenWiki(_BaseHarness):
    """When there are no candidates, the chain falls through to site, then wiki."""

    def test_no_candidates_falls_through_to_site(self):
        def _fake_request(url, *, params=None, headers=None, timeout=10,
                          host_for_cold=None, label=""):
            return None  # heavy query times out; no per-candidate titles given

        vr._request_with_backoff = _fake_request
        vr._fallback_museum_site = lambda qid, name, url_, lang: \
            vr._works_from_titles(["The Great Hall", "European Paintings"], lang)

        works = vr._fetch_venue_works_cached(
            MET_QID, "en", venue_name="Met",
            candidate_titles=[], official_url="https://metmuseum.org/")
        labels = {w["label_en"] for w in works}
        self.assertEqual({"The Great Hall", "European Paintings"}, labels)

    def test_site_empty_falls_through_to_wikipedia(self):
        vr._request_with_backoff = lambda *a, **k: None
        vr._fallback_museum_site = lambda *a, **k: []
        vr._fallback_wikipedia_highlights = lambda qid, name, wiki, lang: \
            vr._works_from_titles(["Famous Painting"], lang)

        works = vr._fetch_venue_works_cached(
            MET_QID, "en", venue_name="Met", candidate_titles=[],
            wiki_title="Metropolitan Museum of Art")
        self.assertEqual(["Famous Painting"], [w["label_en"] for w in works])

    def test_all_sources_fail_returns_empty_not_crash(self):
        vr._request_with_backoff = lambda *a, **k: None
        # site + wiki already inert in the harness.
        works = vr._fetch_venue_works_cached(
            MET_QID, "en", venue_name="Met", candidate_titles=[])
        self.assertEqual([], works)
        # A fully-failed fallback is NOT cached (UNKNOWN; endpoint may recover).
        self.assertFalse(self._puts)


class TestCacheHitSkipsQuery(_BaseHarness):
    """A per-QID cache HIT returns immediately and never calls WDQS."""

    def test_cache_hit_skips_sparql(self):
        cached_works = [vr._works_from_titles(["Cached Work A", "Cached Work B"])][0]
        vr.venue_works_cache_get = lambda qid, language="en": list(cached_works)

        def _boom(*a, **k):
            raise AssertionError("SPARQL must NOT be called on a cache HIT")

        vr._request_with_backoff = _boom

        works = vr._fetch_venue_works_cached(
            MET_QID, "en", venue_name="Met", candidate_titles=MET_CANDIDATES)
        self.assertEqual(["Cached Work A", "Cached Work B"],
                         [w["label_en"] for w in works])


class TestCleanResultRegression(_BaseHarness):
    """A clean SPARQL result is returned unchanged and cached (no fallback)."""

    def test_clean_sparql_result_cached_and_returned(self):
        payload = {"results": {"bindings": [
            _sparql_binding("Q11111", "Starry Night", sitelinks=40),
            _sparql_binding("Q22222", "Sunflowers", sitelinks=30),
        ]}}

        def _fake_request(url, *, params=None, headers=None, timeout=10,
                          host_for_cold=None, label=""):
            return _FakeResp(200, payload)

        vr._request_with_backoff = _fake_request

        works = vr._fetch_venue_works_cached(
            "Q99999", "en", venue_name="Some Museum",
            candidate_titles=["irrelevant"])
        labels = {w["label_en"] for w in works}
        self.assertEqual({"Starry Night", "Sunflowers"}, labels)
        # Clean result is cached with source 'sparql' (not 'fallback').
        self.assertTrue(self._puts)
        self.assertEqual("sparql", self._puts[-1][3])

    def test_clean_empty_result_still_caches_sparql_source(self):
        """A genuine 0-work museum (clean 200, no bindings) returns [] and is
        cached as 'sparql' — NOT treated as a timeout, no fallback runs."""
        def _fake_request(url, *, params=None, headers=None, timeout=10,
                          host_for_cold=None, label=""):
            return _FakeResp(200, {"results": {"bindings": []}})

        vr._request_with_backoff = _fake_request
        # If the fallback ran, this would raise.
        vr._fallback_museum_site = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("fallback must not run on a clean empty result"))

        works = vr._fetch_venue_works_cached(
            "Q99999", "en", venue_name="Empty Museum", candidate_titles=["x"])
        self.assertEqual([], works)
        self.assertEqual("sparql", self._puts[-1][3])


class TestEndToEndMetTourDoesNotCleanFail(unittest.TestCase):
    """The LOCAL-809 scenario through the generator: WDQS blocked, the model's
    candidates are real Met works, and the tour MUST deliver verified stops
    (not tier 'unresolvable') because fetch_venue_works falls back."""

    def setUp(self):
        import generate_tour_text as g
        import story_miner as sm
        self.g = g
        self.sm = sm
        self._saved = {}

        def _save(mod, name):
            self._saved[(mod, name)] = getattr(mod, name)

        for mod, name in [
            (vr, "resolve_venue"),
            (vr, "fetch_venue_works"),
            (vr, "cache_get"),
            (sm, "fetch_venue_narrative_corpus"),
            (sm, "match_candidate_to_canonical"),
            (sm, "filter_corpus_titles"),
        ]:
            _save(mod, name)

        class _MetEntity:
            qid = MET_QID
            language = "en"
            official_url = "https://www.metmuseum.org/"
            name = "Metropolitan Museum of Art"
            artist_qid = ""
            artist_name = ""

        vr.resolve_venue = lambda *a, **k: _MetEntity()
        vr.cache_get = lambda qid: None  # venue_corpus cache miss

        # fetch_venue_works simulates the LOCAL-810 fallback result: WDQS timed
        # out, the per-candidate chain confirmed the real Met works.
        def _fallback_works(qid, language="en", is_modern_art_museum=None,
                            venue_name="", candidate_titles=None,
                            official_url="", wiki_title=""):
            return vr._works_from_titles(list(candidate_titles or []), language)

        vr.fetch_venue_works = _fallback_works

        # Narrative corpus has no extra site/wiki titles here (WDQS blocked path).
        sm.fetch_venue_narrative_corpus = lambda **k: {
            "canonical_titles": set(), "combined_text": "x" * 2000,
            "pages": [{"text": "x" * 2000, "url": _MetEntity.official_url}],
            "cycle_names": set(), "theme_words": set(),
            "source_urls": [_MetEntity.official_url], "per_work_contexts": {},
            "catalogue_works": [], "title_sources": {}}
        # Work/non-work filter: passthrough (the fallback titles ARE works).
        sm.filter_corpus_titles = lambda raw_titles, **k: {
            "works": set(raw_titles), "galleries": set(),
            "excluded": set(), "aliases": {}}

        # Exact-match verifier.
        def _match(candidate, canonical_titles, combined_text):
            for ct in (canonical_titles or []):
                if candidate.strip().lower() == ct.strip().lower():
                    return (ct, "confirmed in the Met collection (P195/P276)")
            return None

        sm.match_candidate_to_canonical = _match

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)

    def test_met_tour_delivers_stops_not_unresolvable(self):
        pois = [{"name": t} for t in MET_CANDIDATES]
        result = self.g._verify_works_v2(pois, "Metropolitan Museum of Art, New York, NY")
        self.assertIsNotNone(result, "verifier returned None (hard fail)")
        self.assertNotEqual(
            "unresolvable", result.tier,
            "WDQS timeout must NOT clean-fail the Met tour — the fallback "
            "delivered real works")
        self.assertGreaterEqual(
            len(result.pois), 5,
            f"expected >= 5 verified Met works from the fallback, got "
            f"{[p.get('name') for p in result.pois]}")
        _names = {(p.get('name') or '').strip() for p in result.pois}
        for cand in MET_CANDIDATES:
            self.assertIn(cand, _names)


class TestEndpointEnv(unittest.TestCase):
    """The WDQS endpoint is env-configurable so a live test can black-hole it."""

    def test_env_overrides_endpoint(self):
        import os
        saved = os.environ.get("WDQS_ENDPOINT")
        try:
            os.environ["WDQS_ENDPOINT"] = "http://10.255.255.1:9/sparql"
            self.assertEqual("http://10.255.255.1:9/sparql", vr._sparql_endpoint())
            del os.environ["WDQS_ENDPOINT"]
            self.assertEqual(vr._SPARQL_ENDPOINT, vr._sparql_endpoint())
        finally:
            if saved is not None:
                os.environ["WDQS_ENDPOINT"] = saved
            else:
                os.environ.pop("WDQS_ENDPOINT", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
