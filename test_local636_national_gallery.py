#!/usr/bin/env python3
"""test_local636_national_gallery.py — issue 3: a famous museum must not be refused.

Bench R2 job 59b34f98 refused the National Gallery with "We could not find enough
verified material about 'The National Gallery'" during a provider-overload window
(33/108 Gemini calls failed, 23:03–23:25Z). It had worked in R1 (tour 495).

Two things are proven here, both offline/mocked (no network):

  1. The LOCAL-632 P195 collection rule does NOT over-reject the National Gallery.
     NG = Q180788; its works carry P195 = Q180788, so _work_collection_excludes_venue
     keeps them. A work with a FOREIGN-only P195 (a P276 loan leak, e.g. a Tate
     work) is still correctly rejected. The rule was never the cause.

  2. The real gap was resilience: entity search (_search_entities) was a single
     shot, so one transient Wikidata 5xx/timeout returned None and the whole
     resolve_venue failed → the famous museum was refused. It now retries
     transient 5xx/timeout (but still trips the dead-host breaker on 429), so a
     passing stall no longer sinks the build.

Run:  python3 -m pytest test_local636_national_gallery.py -q
"""
import unittest

import artwork_selection_guard as asg
import venue_resolver as vr


NG_QID = "Q180788"


class TestP195RuleKeepsNationalGallery(unittest.TestCase):
    def test_ng_work_with_venue_p195_is_kept(self):
        work = {"title": "The Hay Wain", "collection_qids": [NG_QID]}
        self.assertFalse(asg._work_collection_excludes_venue(work, NG_QID, ()))

    def test_ng_work_with_venue_plus_other_p195_is_kept(self):
        # Many NG works list two collections; the venue being ONE of them is enough.
        work = {"title": "Three Studies", "collection_qids": [NG_QID, "Q430682"]}
        self.assertFalse(asg._work_collection_excludes_venue(work, NG_QID, ()))

    def test_foreign_only_p195_is_rejected(self):
        # A P276-location leak whose real collection (P195) is Tate (Q430682).
        work = {"title": "Salisbury Cathedral from the Meadows",
                "collection_qids": ["Q430682"]}
        self.assertTrue(asg._work_collection_excludes_venue(work, NG_QID, ()))

    def test_work_without_p195_is_not_decided_here(self):
        # No P195 → the rule is a no-op (title/site check governs); never stranded.
        work = {"title": "Some Painting", "collection_qids": []}
        self.assertFalse(asg._work_collection_excludes_venue(work, NG_QID, ()))

    def test_enforce_membership_keeps_a_realistic_ng_set(self):
        works = [
            {"title": "The Hay Wain", "collection_qids": [NG_QID]},
            {"title": "The Mystical Nativity", "collection_qids": [NG_QID]},
            {"title": "Tiger in a Tropical Storm", "collection_qids": [NG_QID]},
            {"title": "A Tate loan", "collection_qids": ["Q430682"]},  # reject
        ]
        kept, dropped = asg.enforce_collection_membership(
            works, venue_name="National Gallery", venue_qid=NG_QID,
            is_art_museum=True)
        kept_titles = {w["title"] for w in kept}
        self.assertEqual(len(kept), 3)
        self.assertNotIn("A Tate loan", kept_titles)
        self.assertEqual(len(dropped), 1)


class TestSearchRetryResilience(unittest.TestCase):
    def _run_with_responses(self, codes):
        """Drive _search_entities with a scripted sequence of HTTP status codes,
        returning (result, attempt_count). dead_host breaker is bypassed."""
        import requests

        class _Resp:
            def __init__(self, code):
                self.status_code = code

            def json(self):
                return {"search": [{"id": NG_QID, "label": "National Gallery"}]}

        state = {"i": 0}

        def fake_get(*a, **k):
            code = codes[min(state["i"], len(codes) - 1)]
            state["i"] += 1
            return _Resp(code)

        # neutralise the dead-host breaker short-circuit + any sleeps
        import time
        import dead_host_breaker as _dhb
        orig_get, orig_sleep = requests.get, time.sleep
        orig_cold = _dhb.is_host_cold
        requests.get = fake_get
        time.sleep = lambda *_a, **_k: None
        _dhb.is_host_cold = lambda *_a, **_k: False
        orig_mark = _dhb.mark_host_cold
        _dhb.mark_host_cold = lambda *_a, **_k: None
        try:
            res = vr._search_entities("The National Gallery")
        finally:
            requests.get = orig_get
            time.sleep = orig_sleep
            _dhb.is_host_cold = orig_cold
            _dhb.mark_host_cold = orig_mark
        return res, state["i"]

    def test_transient_5xx_then_success(self):
        res, attempts = self._run_with_responses([503, 503, 200])
        self.assertEqual(res, [(NG_QID, "National Gallery")])
        self.assertEqual(attempts, 3)

    def test_immediate_success_does_not_retry(self):
        res, attempts = self._run_with_responses([200])
        self.assertEqual(res, [(NG_QID, "National Gallery")])
        self.assertEqual(attempts, 1)

    def test_429_does_not_retry(self):
        # 429 must trip the dead-host breaker, not spin retries.
        res, attempts = self._run_with_responses([429, 200, 200])
        self.assertIsNone(res)
        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
