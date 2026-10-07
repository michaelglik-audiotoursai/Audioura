"""
test_local615_cost_total.py — [LOCAL-615 item 3]
=================================================

D626 (tours 403 Lyon $0.5237, 405 Bilbao $0.5116): cost_ledger.our_cost_usd for a
freshly generated tour equalled the OpenAI channel ALONE. The breakdown also held
gemini_grounding ($0.126 / $0.112), gemini_tokens ($0.044 / $0.049) and serper
($0.061 / $0.076) — none of which were summed into the total.

Root cause: a first-tour-of-a-contained-venue is delivered through the stop-pool
orchestrator. The orchestrator read generate_tour_text._LAST_GENERATION_COST
['total_cost'] (OpenAI only) as the delivery cost and propagated it as new_cost →
tour_total_cost → our_cost_usd, dropping Serper + Gemini grounding + Flash tokens.

Fix: the reconcile sets tour_total_cost to the sum of ALL counted provider
channels; the orchestrator now reads tour_total_cost (not total_cost).

Offline/deterministic: drives the real CostAccumulator and the real reconcile
function with synthetic per-provider usage — no DB, no network, no keys.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cost_accumulator as ca
import cost_rates
import generate_tour_text as gtt


class TestTourTotalSumsAllProviders(unittest.TestCase):
    """The reconcile makes _LAST_GENERATION_COST['tour_total_cost'] the sum of
    every provider channel — not OpenAI alone."""

    def setUp(self):
        self._saved = gtt._LAST_GENERATION_COST

    def tearDown(self):
        gtt._LAST_GENERATION_COST = self._saved

    def _acc_with_all_providers(self):
        acc = ca.CostAccumulator(job_id="t615-3")
        # OpenAI (the only channel the buggy total counted)
        acc.add_llm(input_tokens=100000, output_tokens=20000, model="gpt-4o")
        # Serper search queries
        acc.add_search(num_queries=5)
        # Gemini grounding (search queries) + Gemini Flash tokens
        acc.add_grounding(num_requests=3, num_queries=4)
        acc.add_gemini_tokens(input_tokens=8000, output_tokens=1500)
        # TTS
        acc.add_tts(char_count=4000, engine="neural")
        return acc

    def test_tour_total_cost_is_sum_of_all_channels(self):
        acc = self._acc_with_all_providers()
        # The reconcile reads _LAST_GENERATION_COST and rewrites it; seed a fresh
        # (non-cache) record exactly as the impl does before reconcile.
        gtt._LAST_GENERATION_COST = {"cache_hit": False, "total_cost": 0.0,
                                     "breakdown": {}}
        gtt._reconcile_cost_record_from_accumulator(acc)
        rec = gtt._LAST_GENERATION_COST

        pb = acc.provider_breakdown()
        expected_total = (
            pb["openai"]["usd"] + pb["serper"]["usd"]
            + pb["gemini_grounding"]["usd"] + pb["gemini_tokens"]["usd"]
            + pb["tts"]["usd"] + pb["preflight"]["usd"]
        )
        # tour_total_cost must equal the sum of ALL providers...
        self.assertAlmostEqual(rec["tour_total_cost"], expected_total, places=9)
        # ...and must be STRICTLY greater than OpenAI alone (the old bug value),
        # since grounding + Flash tokens + serper are all non-zero here.
        self.assertGreater(rec["tour_total_cost"], pb["openai"]["usd"])
        # It equals the accumulator's own grand total.
        self.assertAlmostEqual(rec["tour_total_cost"], acc.total_usd(), places=9)

    def test_total_cost_still_means_openai_only(self):
        # The legacy scalar `total_cost` keeps its historical OpenAI-only meaning;
        # only `tour_total_cost` is the all-provider delivery total.
        acc = self._acc_with_all_providers()
        gtt._LAST_GENERATION_COST = {"cache_hit": False, "total_cost": 0.0,
                                     "breakdown": {}}
        gtt._reconcile_cost_record_from_accumulator(acc)
        rec = gtt._LAST_GENERATION_COST
        self.assertAlmostEqual(rec["total_cost"],
                               acc.provider_breakdown()["openai"]["usd"], places=9)
        self.assertLess(rec["total_cost"], rec["tour_total_cost"])


class TestOrchestratorReadsFullTotal(unittest.TestCase):
    """The orchestrator's first-tour cost must be the all-provider tour_total_cost,
    not total_cost. We assert on the source so the regression can't silently
    return (the orchestrator K==0 path needs a DB to run end-to-end)."""

    def test_orchestrator_reads_tour_total_cost(self):
        import inspect
        import stop_pool_orchestrator as orch
        src = inspect.getsource(orch.maybe_generate_with_pool)
        self.assertIn('tour_total_cost', src,
                      "orchestrator first-tour cost must read tour_total_cost")

    def test_first_cost_prefers_tour_total_over_total(self):
        # Reproduce the exact read the orchestrator does and prove it picks the
        # all-provider total over the OpenAI-only one.
        _nc = {"total_cost": 0.5237, "tour_total_cost": 0.5237 + 0.126 + 0.044 + 0.061}
        first_cost = float(
            _nc.get("tour_total_cost", _nc.get("total_cost", 0.0)) or 0.0)
        self.assertAlmostEqual(first_cost, 0.7547, places=4)
        self.assertGreater(first_cost, _nc["total_cost"])


class TestLiveRunMeterReads7KeyBreakdown(unittest.TestCase):
    """[LOCAL-615 item 3] tests/live_run_meter.add_generation must read the
    LOCAL-609 per-provider breakdown (openai/serper/gemini_tokens/
    gemini_grounding/preflight), not only the legacy flat llm/search keys — a live
    run otherwise records openai=$0 / serper=$0 even when it spent on both (D626
    TEST-* row showed grounding only)."""

    def test_add_generation_reads_provider_keys(self):
        import types
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
        import live_run_meter as lrm

        fake = types.SimpleNamespace()
        fake._LAST_GENERATION_COST = {
            "cache_hit": False,
            "tour_total_cost": 0.4042,
            "breakdown": {
                "openai": {"usd": 0.2541},
                "serper": {"usd": 0.0400},
                "gemini_tokens": {"usd": 0.0261},
                "gemini_grounding": {"usd": 0.0840, "requests": 6, "queries": 6},
                "preflight": {"usd": 0.0, "calls": 0, "queries": 0},
                "tts": {"usd": 0.0},
            },
        }
        m = lrm.LiveRunMeter("LOCAL-615", install_cap=False)
        m.add_generation(fake)
        self.assertAlmostEqual(m.openai_usd, 0.2541, places=6)
        self.assertAlmostEqual(m.serper_usd, 0.0400, places=6)
        self.assertAlmostEqual(m.gemini_tokens_usd, 0.0261, places=6)
        self.assertAlmostEqual(m.gemini_grounding_usd, 0.0840, places=6)
        # total == sum of provider lines (grounding counted once, preflight is a
        # labelled subset not re-added).
        self.assertAlmostEqual(m.total_usd(), 0.2541 + 0.0840 + 0.0261 + 0.0400,
                               places=6)
        bd = m.breakdown()
        self.assertAlmostEqual(bd["openai"], 0.2541, places=6)
        self.assertAlmostEqual(bd["serper"], 0.0400, places=6)

    def test_add_generation_legacy_keys_still_work(self):
        import types
        import live_run_meter as lrm
        fake = types.SimpleNamespace()
        fake._LAST_GENERATION_COST = {
            "cache_hit": False,
            "breakdown": {"llm": 0.30, "search": 0.02, "grounding": 0.05},
        }
        m = lrm.LiveRunMeter("LOCAL-615", install_cap=False)
        m.add_generation(fake)
        self.assertAlmostEqual(m.openai_usd, 0.30, places=6)
        self.assertAlmostEqual(m.serper_usd, 0.02, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)