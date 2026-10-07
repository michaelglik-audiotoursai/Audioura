"""
test_local615_preflight_metered.py — [LOCAL-615 item 4]
========================================================

D626: the venue preflight showed `preflight: calls 0` in every tour's breakdown
although it ran (`[LOCAL-603] preflight … hours=y`). The preflight runs in the
generate_tour_text WRAPPER, BEFORE the per-generation accumulator scope opens, so
its grounded-Gemini call was attributed to no accumulator and its cost was wiped.

Fix:
  * the wrapper opens a dedicated tour_scope + preflight_scope JUST around the
    preflight call, so cost_accumulator.add_gemini_call lands in the preflight
    bucket, and snapshots that bucket into _LAST_PREFLIGHT_COST; and
  * _fold_preflight_cost_into_record folds that captured cost into the delivering
    tour's _LAST_GENERATION_COST (pool AND normal paths), so the ledger breakdown
    carries preflight calls/queries/$ and tour_total_cost includes it.

Offline/deterministic: drives the real CostAccumulator (preflight_scope routing)
and the real fold helper — no DB, no network, no keys.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cost_accumulator as ca
import cost_rates
import generate_tour_text as gtt


class TestPreflightBucketCaptured(unittest.TestCase):
    """A grounded Gemini call made inside preflight_scope lands in the preflight
    bucket — the snapshot the wrapper captures into _LAST_PREFLIGHT_COST."""

    def test_preflight_scope_populates_bucket(self):
        acc = ca.CostAccumulator(job_id="t615-4")
        with ca.tour_scope(job_id="t615-4", accumulator=acc):
            with ca.preflight_scope():
                ca.add_gemini_call(input_tokens=2000, output_tokens=400,
                                   num_queries=2, grounded=True)
        snap = acc.snapshot()
        pf = (snap.get("provider_breakdown") or {}).get("preflight") or {}
        self.assertEqual(pf["calls"], 1)
        self.assertEqual(pf["queries"], 2)
        self.assertEqual(pf["input_tokens"], 2000)
        self.assertGreater(pf["usd"], 0.0)
        self.assertAlmostEqual(pf["usd"],
                               cost_rates.preflight_cost(2, 2000, 400), places=9)
        # Preflight did NOT bleed into the ordinary gemini channels.
        self.assertEqual(snap["provider_breakdown"]["gemini_tokens"]["usd"], 0.0)
        self.assertEqual(snap["provider_breakdown"]["gemini_grounding"]["usd"], 0.0)


class TestFoldPreflightCostIntoRecord(unittest.TestCase):
    def test_fold_adds_dollars_and_breakdown_line(self):
        rec = {
            "cache_hit": False,
            "total_cost": 0.5237,
            "tour_total_cost": 0.5237 + 0.126 + 0.044 + 0.061,
            "breakdown": {"openai": {"usd": 0.5237}},
        }
        before_total = rec["tour_total_cost"]
        pf_cost = {"usd": 0.012, "calls": 1, "queries": 2,
                   "input_tokens": 2000, "output_tokens": 400}
        gtt._fold_preflight_cost_into_record(rec, pf_cost)
        # tour_total_cost grew by exactly the preflight dollars.
        self.assertAlmostEqual(rec["tour_total_cost"], before_total + 0.012, places=9)
        # The breakdown now carries a preflight line with the counted units.
        self.assertEqual(rec["breakdown"]["preflight"]["calls"], 1)
        self.assertEqual(rec["breakdown"]["preflight"]["queries"], 2)
        self.assertAlmostEqual(rec["breakdown"]["preflight"]["usd"], 0.012, places=9)
        self.assertAlmostEqual(rec["preflight_cost"], 0.012, places=9)

    def test_zero_preflight_still_records_line(self):
        # A cache-hit preflight ($0) still gets a breakdown line (uniform shape),
        # and the total is unchanged.
        rec = {"tour_total_cost": 0.40, "breakdown": {"openai": {"usd": 0.40}}}
        gtt._fold_preflight_cost_into_record(
            rec, {"usd": 0.0, "calls": 0, "queries": 0,
                  "input_tokens": 0, "output_tokens": 0})
        self.assertIn("preflight", rec["breakdown"])
        self.assertEqual(rec["breakdown"]["preflight"]["usd"], 0.0)
        self.assertEqual(rec["breakdown"]["preflight"]["calls"], 0)
        self.assertAlmostEqual(rec["tour_total_cost"], 0.40, places=9)

    def test_fold_is_noop_on_empty_record(self):
        rec = {}
        gtt._fold_preflight_cost_into_record(rec, {"usd": 0.1, "calls": 1})
        # Nothing to fold into — left empty, no crash.
        self.assertEqual(rec, {})

    def test_fold_handles_none_preflight_cost(self):
        rec = {"tour_total_cost": 0.3, "breakdown": {}}
        gtt._fold_preflight_cost_into_record(rec, None)
        self.assertEqual(rec["breakdown"]["preflight"]["usd"], 0.0)
        self.assertAlmostEqual(rec["tour_total_cost"], 0.3, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
