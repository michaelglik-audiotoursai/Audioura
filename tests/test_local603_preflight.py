#!/usr/bin/env python3
"""test_local603_preflight.py — LOCAL-603 (D618) venue preflight, module level.

The six cases the ticket requires, with the Gemini WIRE stubbed (no network, no
real key). This file covers the ones that live in venue_preflight itself; the
meter-count and L2-skip cases live in test_local603_meter_and_l2.py.

  1. THE WNDR ANSWER → venue_closed, and ZERO further calls.
     A permanently_closed answer whose grounding source carries a closure word
     produces a `venue_closed` gate; exactly ONE grounded request is issued (the
     preflight itself) and nothing after it.
  3. A CLOSURE CLAIM WITHOUT A CLOSURE-WORD SOURCE → unknown, and continue.
     The model says permanently_closed but no grounding source (title/url) and no
     answer text carries a closure word → status downgraded to unknown, no gate.
  6. A CACHE HIT MAKES NO CALL.
     A second preflight for the same (venue, city) within the TTL is served from
     the DB cache and issues zero grounded requests.

Also: an OPEN museum with hours yields spoken hours (plan_b_opening_practicals),
and the per-field sources are attached.

Run: python3 -m pytest tests/test_local603_preflight.py -q
"""
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# A key must be present or the Gemini wrapper short-circuits before issuing a
# request. The network is faked below, so the value never reaches Google.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

import story_leads  # noqa: E402
import venue_preflight as vp  # noqa: E402


# ─── a fake Gemini wire ──────────────────────────────────────────────────────
class _FakeResp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _Wire:
    """Fake requests.post that returns a Gemini-shaped grounded response. The
    answer JSON and the grounding chunks (whose resolved URLs may or may not carry
    a closure word) are set per test. Counts grounded requests independently."""

    def __init__(self, answer_json, chunk_urls, queries=None):
        self.answer_json = answer_json
        self.chunk_urls = chunk_urls           # resolved URLs (post-redirect)
        self.queries = queries or ["q1", "q2"]
        self.grounded_requests = 0

    def post(self, url, headers=None, json=None, timeout=None, **kwargs):
        import json as _json
        body = json or {}
        tools = body.get("tools") or []
        grounded = any("google_search" in (t or {}) for t in tools)
        gm = {}
        if grounded:
            self.grounded_requests += 1
            gm = {
                "webSearchQueries": self.queries,
                "groundingChunks": [
                    {"web": {"title": f"src{i}", "uri": f"https://redir/{i}"}}
                    for i in range(len(self.chunk_urls))
                ],
                "groundingSupports": [],
            }
        text = _json.dumps(self.answer_json) if isinstance(self.answer_json, dict) \
            else str(self.answer_json)
        return _FakeResp({"candidates": [{"content": {"parts": [{"text": text}]},
                                          "groundingMetadata": gm}]})

    def head(self, url, allow_redirects=True, timeout=20):
        # Map redirect uri -> resolved URL (which may contain a closure word).
        try:
            i = int(url.rsplit("/", 1)[-1])
            resolved = self.chunk_urls[i]
        except (ValueError, IndexError):
            resolved = url
        return type("H", (), {"url": resolved})()


def _install(wire):
    import requests
    orig_post, orig_head = requests.post, requests.head
    requests.post = wire.post
    requests.head = wire.head
    story_leads.reset_grounding_requests()
    return orig_post, orig_head


def _restore(orig):
    import requests
    requests.post, requests.head = orig


# Keep tests hermetic: never read or write the real known_closed_venues.json.
# `_corpus` is a controllable in-memory set of folded (name, city) pairs that the
# known-closed short-circuit consults; `record_confirmed_closure` is a no-op that
# just records into `_corpus` so a "next request skips the call" assertion works.
class _CorpusPatch:
    def __init__(self, seed=None):
        self._seed = set(seed or [])

    def __enter__(self):
        self._orig_known = vp.already_known_closed
        self._orig_record = vp.record_confirmed_closure
        store = self._seed

        def fake_known(venue, city):
            return (vp._fold(venue), vp._fold(city)) in store \
                or any(vp._fold(venue) == n for (n, c) in store)

        def fake_record(venue, city, result):
            store.add((vp._fold(venue), vp._fold(city)))
            return {"name": venue, "city": city}

        vp.already_known_closed = fake_known
        vp.record_confirmed_closure = fake_record
        return self

    def __exit__(self, *a):
        vp.already_known_closed = self._orig_known
        vp.record_confirmed_closure = self._orig_record
        return False


WNDR_ANSWER = {
    "status": "permanently_closed",
    "closed_since": "August 30, 2026",
    "address": "500 Washington St, Boston, MA",
    "hours": "",
    "admission": "$29.99 adult / $26.99 child",
    "current_exhibitions_or_highlights": [
        {"title": "Light Floor", "artist": "", "note": "closing installation"},
    ],
}


class TestWndrClosedGate(unittest.TestCase):
    """Case 1: WNDR → venue_closed, exactly one grounded call, nothing after."""

    def test_wndr_permanently_closed_gates(self):
        wire = _Wire(WNDR_ANSWER,
                     chunk_urls=["https://boston.com/wndr-permanently-closed",
                                 "https://wndrmuseum.com/"])
        orig = _install(wire)
        try:
            with _CorpusPatch():   # not pre-known → the grounded call fires
                res = vp.preflight("WNDR Museum", "Boston, MA",
                                   db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "permanently_closed")
        self.assertEqual(res["closed_since"], "August 30, 2026")
        # Exactly ONE grounded request — the preflight itself, nothing more.
        self.assertEqual(wire.grounded_requests, 1)
        self.assertEqual(story_leads.get_grounding_requests(), 1)
        # The gate fires with the exact contract.
        g = vp.gate("WNDR Museum", "Boston", res)
        self.assertIsNotNone(g)
        self.assertEqual(g["error_code"], "venue_closed")
        self.assertIn("closed permanently", g["message"])
        self.assertIn("WNDR Museum", g["message"])
        self.assertEqual(g["suggestion"],
                         "Try a nearby museum, or a walking tour of the area.")

    def test_known_closed_short_circuits_with_zero_calls(self):
        """Case 1 corollary: once a venue is in the known-closed corpus, a fresh
        request issues ZERO grounded calls (the deterministic skip, D539/D547)."""
        wire = _Wire({"status": "open"}, chunk_urls=[])
        orig = _install(wire)
        try:
            with _CorpusPatch(seed={(vp._fold("La Maree"), vp._fold("Monaco"))}):
                res = vp.preflight("La Maree", "Monaco",
                                   db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "permanently_closed")
        self.assertTrue(res.get("_from_known_closed"))
        self.assertEqual(wire.grounded_requests, 0,
                         "a known-closed venue must not issue a grounded call")
        self.assertIsNotNone(vp.gate("La Maree", "Monaco", res))


class TestFalseClosureDowngrade(unittest.TestCase):
    """Case 3: closure claim with no closure-word source → unknown, continue."""

    def test_closed_without_closure_source_downgrades(self):
        # Model SAYS permanently_closed, but neither the answer text nor any
        # grounding source URL/title carries a closure word.
        answer = {
            "status": "permanently_closed",
            "closed_since": "2024",
            "address": "1 Rue de Rivoli, Paris",
            "hours": "", "admission": "",
            "current_exhibitions_or_highlights": [],
        }
        wire = _Wire(answer, chunk_urls=["https://example.com/about",
                                         "https://example.com/visit"])
        orig = _install(wire)
        try:
            with _CorpusPatch():
                res = vp.preflight("Some Gallery", "Paris", db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "unknown",
                         "no closure-word source → status must downgrade to unknown")
        self.assertEqual(res.get("_downgraded_from"), "permanently_closed")
        self.assertEqual(res["closed_since"], "")
        # No gate — generation continues.
        self.assertIsNone(vp.gate("Some Gallery", "Paris", res))

    def test_temporarily_closed_with_reopen_date_does_not_gate(self):
        answer = {
            "status": "temporarily_closed",
            "closed_since": "reopening 2027-01-15",
            "address": "", "hours": "", "admission": "",
            "current_exhibitions_or_highlights": [],
        }
        wire = _Wire(answer, chunk_urls=["https://museum.org/closed-for-renovation"])
        orig = _install(wire)
        try:
            with _CorpusPatch():
                res = vp.preflight("Renovating Museum", "Rome", db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "temporarily_closed")
        # Has a reopen date → do NOT refuse (the listener can take it then).
        self.assertIsNone(vp.gate("Renovating Museum", "Rome", res))

    def test_temporarily_closed_no_reopen_gates(self):
        answer = {
            "status": "temporarily_closed", "closed_since": "",
            "address": "", "hours": "", "admission": "",
            "current_exhibitions_or_highlights": [],
        }
        wire = _Wire(answer, chunk_urls=["https://museum.org/temporarily-closed"])
        orig = _install(wire)
        try:
            with _CorpusPatch():
                res = vp.preflight("Shut Museum", "Berlin", db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "temporarily_closed")
        g = vp.gate("Shut Museum", "Berlin", res)
        self.assertIsNotNone(g)
        self.assertEqual(g["error_code"], "venue_closed")


class TestOpenMuseumHours(unittest.TestCase):
    """An open museum with hours → the Plan B opening practicals SPEAK the hours,
    with the source in the text view only (D617)."""

    def test_open_hours_spoken_source_in_text_only(self):
        answer = {
            "status": "open", "closed_since": "",
            "address": "465 Huntington Ave, Boston, MA",
            "hours": "Tue-Sun 10am-5pm, closed Mon",
            "admission": "Adults $27",
            "current_exhibitions_or_highlights": [
                {"title": "A Show", "artist": "", "note": "on view"}],
        }
        wire = _Wire(answer, chunk_urls=["https://mfa.org/visit"])
        orig = _install(wire)
        try:
            with _CorpusPatch():
                res = vp.preflight("Open Museum", "Boston", db_url=None, use_cache=False)
        finally:
            _restore(orig)
        self.assertEqual(res["status"], "open")
        self.assertIsNone(vp.gate("Open Museum", "Boston", res))
        # Per-field sources attached.
        self.assertIn("hours", res["sources"])
        self.assertIn("https://mfa.org/visit", res["sources"]["hours"])

        planb = vp.plan_b_opening_practicals(res)
        # Hours + admission are SPOKEN.
        self.assertIn("Tue-Sun 10am-5pm", planb["speak"])
        self.assertIn("Adults $27", planb["speak"])
        # D617: the source is NOT in the spoken text; it is in the text-view note.
        self.assertNotIn("mfa.org", planb["speak"])
        self.assertIn("mfa.org", planb["source_note"])


class TestCacheHitMakesNoCall(unittest.TestCase):
    """Case 6: a cache hit issues ZERO grounded requests. Uses a fake DB layer so
    the test needs no Postgres."""

    def setUp(self):
        # In-memory stand-in for the DB cache: patch _cache_get / _cache_put.
        self._store = {}
        self._orig_get = vp._cache_get
        self._orig_put = vp._cache_put

        def fake_get(venue, city, db_url):
            key = vp._cache_key(venue, city)
            v = self._store.get(key)
            if v is None:
                return None
            r = json.loads(v)
            r["cached"] = True
            return r

        def fake_put(venue, city, result, db_url):
            if result.get("error"):
                return
            stored = dict(result)
            stored["cached"] = False
            self._store[vp._cache_key(venue, city)] = json.dumps(stored)

        vp._cache_get = fake_get
        vp._cache_put = fake_put

    def tearDown(self):
        vp._cache_get = self._orig_get
        vp._cache_put = self._orig_put

    def test_second_call_served_from_cache(self):
        answer = {
            "status": "open", "closed_since": "", "address": "", "hours": "9-5",
            "admission": "", "current_exhibitions_or_highlights": [],
        }
        wire = _Wire(answer, chunk_urls=["https://museum.org/visit"])
        orig = _install(wire)
        try:
            with _CorpusPatch():
                # First call: a real (stubbed) grounded request, written to cache.
                r1 = vp.preflight("Cached Museum", "Oslo",
                                  db_url="postgres://fake", use_cache=True)
                self.assertEqual(wire.grounded_requests, 1)
                self.assertFalse(r1.get("cached"))

                # Second call: served from cache, ZERO new grounded requests.
                story_leads.reset_grounding_requests()
                r2 = vp.preflight("Cached Museum", "Oslo",
                                  db_url="postgres://fake", use_cache=True)
                self.assertEqual(wire.grounded_requests, 1,
                                 "a cache hit must not issue a new grounded request")
                self.assertEqual(story_leads.get_grounding_requests(), 0)
                self.assertTrue(r2.get("cached"))
                self.assertEqual(r2["status"], "open")
                self.assertEqual(r2["hours"], "9-5")
        finally:
            _restore(orig)


class TestPlanBStopCandidates(unittest.TestCase):
    """Plan B stop candidates seed only a short list, and only when sourced."""

    def test_candidates_only_when_below_want(self):
        res = {
            "current_exhibitions_or_highlights": [
                {"title": "Show A", "artist": "", "note": ""},
                {"title": "Show B", "artist": "", "note": ""},
                {"title": "Show C", "artist": "", "note": ""},
            ],
            "sources": {"current_exhibitions_or_highlights": ["https://v/exh"]},
        }
        # Have 1, want 3 → seed 2, each carrying the source.
        cands = vp.plan_b_stop_candidates(res, have=1, want=3)
        self.assertEqual(len(cands), 2)
        for c in cands:
            self.assertEqual(c["source_url"], "https://v/exh")
            self.assertTrue(c["_preflight_seed"])
        # Already at want → no candidates.
        self.assertEqual(vp.plan_b_stop_candidates(res, have=3, want=3), [])

    def test_no_candidates_without_source(self):
        res = {
            "current_exhibitions_or_highlights": [{"title": "X", "artist": "", "note": ""}],
            "sources": {},   # no source → cannot seed a sourced stop (D618)
        }
        self.assertEqual(vp.plan_b_stop_candidates(res, have=0, want=3), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
