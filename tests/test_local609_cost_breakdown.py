"""
test_local609_cost_breakdown.py — LOCAL-609 per-provider cost breakdown.
========================================================================

Covers the three things the ticket's "Tests" clause asks for:

  1. Each meter increments as its call happens (stubbed wires):
       * cost_accumulator.add_search_queries -> serper bucket
       * cost_accumulator.add_gemini_call    -> gemini_tokens + gemini_grounding
       * preflight_scope routes add_gemini_call -> preflight bucket
       * story_leads._meter_gemini_call reads usageMetadata + webSearchQueries
  2. The Serper meter counts REAL queries: a stubbed-network _serp_search call
     made inside a tour_scope increments search.queries by exactly one per call.
  3. The report sums correctly: tour_cost_report.build_report on synthetic ledger
     rows renders every provider line and the correct delivery / reused-research
     totals.

All offline — no DB, no network, no API keys. The one "real query" test
monkeypatches urllib so no packet leaves the box.
"""

import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cost_accumulator as ca
import cost_rates
import tour_cost_report as report


# ─── 1. Meters increment as their call happens ───────────────────────────────
class TestMetersIncrement(unittest.TestCase):

    def test_serper_meter_increments_in_scope(self):
        with ca.tour_scope("t") as acc:
            self.assertEqual(acc.search["queries"], 0)
            ca.add_search_queries(1)
            ca.add_search_queries(1)
            self.assertEqual(acc.search["queries"], 2)
            self.assertAlmostEqual(acc.search["usd"],
                                   2 * cost_rates.SERPER_COST_PER_QUERY, places=9)

    def test_serper_meter_noop_outside_scope(self):
        # No active scope: a stray call must be a harmless no-op (returns 0.0).
        self.assertEqual(ca.add_search_queries(5), 0.0)

    def test_gemini_call_splits_tokens_and_grounding(self):
        with ca.tour_scope("t") as acc:
            ca.add_gemini_call(input_tokens=1000, output_tokens=500,
                               num_queries=3, grounded=True)
            pb = acc.provider_breakdown()
        self.assertEqual(pb["gemini_tokens"]["input_tokens"], 1000)
        self.assertEqual(pb["gemini_tokens"]["output_tokens"], 500)
        self.assertAlmostEqual(pb["gemini_tokens"]["usd"],
                               cost_rates.gemini_tokens_cost(1000, 500), places=9)
        self.assertEqual(pb["gemini_grounding"]["queries"], 3)
        self.assertAlmostEqual(pb["gemini_grounding"]["usd"],
                               cost_rates.grounding_query_cost(3), places=9)
        # preflight untouched
        self.assertEqual(pb["preflight"]["calls"], 0)

    def test_ungrounded_gemini_call_adds_tokens_only(self):
        with ca.tour_scope("t") as acc:
            ca.add_gemini_call(input_tokens=800, output_tokens=200,
                               num_queries=0, grounded=False)
            pb = acc.provider_breakdown()
        self.assertEqual(pb["gemini_tokens"]["input_tokens"], 800)
        self.assertEqual(pb["gemini_grounding"]["queries"], 0)
        self.assertEqual(pb["gemini_grounding"]["usd"], 0.0)

    def test_preflight_scope_routes_to_preflight_bucket(self):
        with ca.tour_scope("t") as acc:
            with ca.preflight_scope():
                ca.add_gemini_call(input_tokens=1500, output_tokens=300,
                                   num_queries=2, grounded=True)
            pb = acc.provider_breakdown()
        # Everything landed in preflight, NOT in gemini_tokens/grounding.
        self.assertEqual(pb["preflight"]["calls"], 1)
        self.assertEqual(pb["preflight"]["queries"], 2)
        self.assertEqual(pb["preflight"]["input_tokens"], 1500)
        self.assertAlmostEqual(pb["preflight"]["usd"],
                               cost_rates.preflight_cost(2, 1500, 300), places=9)
        self.assertEqual(pb["gemini_tokens"]["usd"], 0.0)
        self.assertEqual(pb["gemini_grounding"]["usd"], 0.0)

    def test_openai_per_model_split(self):
        with ca.tour_scope("t") as acc:
            ca.add_llm_usage(1000, 500, "gpt-4o-mini")
            ca.add_llm_usage(200, 100, "gpt-4o")
            pb = acc.provider_breakdown()
        self.assertIn("gpt-4o-mini", pb["openai"]["by_model"])
        self.assertIn("gpt-4o", pb["openai"]["by_model"])
        self.assertEqual(pb["openai"]["calls"], 2)

    def test_tts_records_engine(self):
        with ca.tour_scope("t") as acc:
            ca.add_tts_characters(10000, engine="neural")
            pb = acc.provider_breakdown()
        self.assertEqual(pb["tts"]["engine"], "neural")
        self.assertEqual(pb["tts"]["characters"], 10000)

    def test_provider_breakdown_has_all_seven_keys(self):
        with ca.tour_scope("t") as acc:
            pb = acc.provider_breakdown()
        for k in ("openai", "gemini_grounding", "gemini_tokens",
                  "serper", "preflight", "tts"):
            self.assertIn(k, pb)


# ─── story_leads._meter_gemini_call reads usageMetadata + webSearchQueries ───
class TestStoryLeadsMeterWire(unittest.TestCase):

    def test_meter_gemini_call_reads_usage_and_queries(self):
        import story_leads
        d = {
            "usageMetadata": {"promptTokenCount": 1200,
                              "candidatesTokenCount": 400,
                              "thoughtsTokenCount": 50},
            "candidates": [{"groundingMetadata": {"webSearchQueries": ["a", "b"]}}],
        }
        with ca.tour_scope("t") as acc:
            story_leads._meter_gemini_call(d, grounded=True)
            pb = acc.provider_breakdown()
        self.assertEqual(pb["gemini_tokens"]["input_tokens"], 1200)
        # thoughtsTokenCount folds into output (billed as output).
        self.assertEqual(pb["gemini_tokens"]["output_tokens"], 450)
        self.assertEqual(pb["gemini_grounding"]["queries"], 2)

    def test_meter_gemini_call_ungrounded_counts_zero_queries(self):
        import story_leads
        d = {"usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 100},
             "candidates": [{}]}
        with ca.tour_scope("t") as acc:
            story_leads._meter_gemini_call(d, grounded=False)
            pb = acc.provider_breakdown()
        self.assertEqual(pb["gemini_tokens"]["input_tokens"], 500)
        self.assertEqual(pb["gemini_grounding"]["queries"], 0)


# ─── 2. The Serper meter counts REAL queries ─────────────────────────────────
class TestSerperMeterCountsRealQueries(unittest.TestCase):
    """A stubbed-network _serp_search call inside a tour_scope increments
    search.queries by exactly one — proving the meter sits on the real query path,
    not in a test-only stub."""

    def test_real_serp_search_increments_meter(self):
        import work_story_searcher as wss

        class _FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self):
                return json.dumps({"organic": [
                    {"title": "T", "link": "http://x", "snippet": "s"}]}).encode()

        _orig_key = wss.SERP_API_KEY
        _orig_urlopen = wss.urllib.request.urlopen
        wss.SERP_API_KEY = "test-key-not-real"
        wss.urllib.request.urlopen = lambda req, timeout=15: _FakeResp()
        try:
            with ca.tour_scope("t") as acc:
                self.assertEqual(acc.search["queries"], 0)
                results, _lat = wss._serp_search("Isabella Stewart Gardner Museum Boston")
                # One real query issued -> meter is exactly 1.
                self.assertEqual(acc.search["queries"], 1)
                self.assertAlmostEqual(acc.search["usd"],
                                       cost_rates.SERPER_COST_PER_QUERY, places=9)
                # Three queries -> three increments.
                wss._serp_search("q2")
                wss._serp_search("q3")
                self.assertEqual(acc.search["queries"], 3)
                # And the stubbed results flowed through unchanged.
                self.assertTrue(results)
        finally:
            wss.SERP_API_KEY = _orig_key
            wss.urllib.request.urlopen = _orig_urlopen

    def test_no_key_issues_no_query_and_no_meter(self):
        import work_story_searcher as wss
        _orig_key = wss.SERP_API_KEY
        wss.SERP_API_KEY = ""
        try:
            with ca.tour_scope("t") as acc:
                results, _lat = wss._serp_search("anything")
                self.assertEqual(results, [])
                self.assertEqual(acc.search["queries"], 0)  # no key -> no query -> no charge
        finally:
            wss.SERP_API_KEY = _orig_key


# ─── 3. The report sums correctly ────────────────────────────────────────────
class TestReportSums(unittest.TestCase):

    def _fresh_row(self, job="j", t=None):
        return {
            "operation_type": "tour_generate", "our_cost_usd": 0.42,
            "cache_hit": False, "job_id": job,
            "created_at": t or dt.datetime(2026, 10, 6, 23, 0, 0),
            "description": "Tour: Gardner",
            "breakdown": {
                "openai": {"usd": 0.30, "calls": 120, "input_tokens": 50000,
                           "output_tokens": 20000, "by_model": {}},
                "gemini_grounding": {"usd": 0.084, "requests": 3, "queries": 6},
                "gemini_tokens": {"usd": 0.012, "calls": 5, "input_tokens": 30000,
                                  "output_tokens": 4000},
                "serper": {"usd": 0.004, "queries": 4},
                "preflight": {"usd": 0.02, "calls": 1, "queries": 1,
                              "input_tokens": 1500, "output_tokens": 300},
                "tts": {"usd": 0.0, "engine": "kokoro", "characters": 12000, "calls": 3},
            },
        }

    def test_fresh_report_renders_all_providers(self):
        out = report.build_report([self._fresh_row()], {"tour_name": "Gardner",
                                                        "audio_tour_id": 1})
        for label in ("OpenAI", "Gemini grounding", "Gemini Flash tokens",
                      "Serper", "Preflight", "TTS"):
            self.assertIn(label, out)
        self.assertIn("DELIVERY TOTAL", out)
        self.assertIn("REUSED-RESEARCH TOTAL", out)
        self.assertIn("WALL TIME", out)

    def test_delivery_total_sums_rows(self):
        t0 = dt.datetime(2026, 10, 6, 23, 0, 0)
        t1 = dt.datetime(2026, 10, 6, 23, 1, 0)
        rows = [self._fresh_row(t=t0)]
        extra = [{
            "operation_type": "translation_generate", "our_cost_usd": 0.5,
            "cache_hit": False, "job_id": "jt", "created_at": t1, "description": "",
            "breakdown": {"translation": {"usd": 0.5, "engine": "neural",
                                          "characters": 16000}},
        }]
        out = report.build_report(rows, {"audio_tour_id": 1},
                                  extra_translation_rows=extra)
        # 0.42 (tour) + 0.50 (translation) = 0.92
        self.assertIn("$0.920000", out)
        self.assertIn("TRANSLATION", out)

    def test_pool_reuse_reports_reused_research(self):
        row = {
            "operation_type": "tour_generate", "our_cost_usd": 0.08,
            "cache_hit": False, "job_id": "j", "created_at": dt.datetime(2026, 10, 6, 23, 0, 0),
            "description": "",
            "breakdown": {
                "openai": {"usd": 0.08, "calls": 20, "input_tokens": 8000,
                           "output_tokens": 3000, "by_model": {}},
                "gemini_grounding": {"usd": 0, "requests": 0, "queries": 0},
                "gemini_tokens": {"usd": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0},
                "serper": {"usd": 0, "queries": 0},
                "preflight": {"usd": 0, "calls": 0, "queries": 0, "input_tokens": 0,
                              "output_tokens": 0},
                "tts": {"usd": 0, "engine": "", "characters": 0, "calls": 0},
                "pool_reuse": True, "reused_stops": 2, "new_stops": 1,
                "research_cost_reused": 0.28,
            },
        }
        out = report.build_report([row], {})
        self.assertIn("POOL REUSE", out)
        self.assertIn("Reused research", out)
        self.assertIn("$0.280000", out)  # reused-research total

    def test_cache_hit_preflight_says_did_not_run(self):
        row = {
            "operation_type": "tour_cache_hit", "our_cost_usd": 0.0,
            "cache_hit": True, "job_id": "j", "created_at": dt.datetime(2026, 10, 6, 23, 0, 0),
            "description": "",
            "breakdown": {
                "openai": {"usd": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0, "by_model": {}},
                "gemini_grounding": {"usd": 0, "requests": 0, "queries": 0},
                "gemini_tokens": {"usd": 0, "calls": 0, "input_tokens": 0, "output_tokens": 0},
                "serper": {"usd": 0, "queries": 0},
                "preflight": {"usd": 0, "calls": 0, "queries": 0, "input_tokens": 0, "output_tokens": 0},
                "tts": {"usd": 0, "engine": "", "characters": 0, "calls": 0},
            },
        }
        out = report.build_report([row], {})
        self.assertIn("CACHE HIT", out)
        self.assertIn("did not run", out)

    def test_empty_rows_message(self):
        out = report.build_report([], {})
        self.assertIn("No cost_ledger rows found", out)

    def test_legacy_four_key_breakdown_still_renders(self):
        row = {
            "operation_type": "tour_generate", "our_cost_usd": 0.05,
            "cache_hit": False, "job_id": "j", "created_at": dt.datetime(2026, 10, 6, 23, 0, 0),
            "description": "",
            "breakdown": {"llm": 0.04, "grounding": 0.01, "search": 0.0, "tts": 0.0},
        }
        out = report.build_report([row], {})
        self.assertIn("OpenAI", out)
        self.assertIn("Gemini grounding", out)


if __name__ == "__main__":
    unittest.main()
