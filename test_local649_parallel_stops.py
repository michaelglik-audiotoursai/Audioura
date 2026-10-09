#!/usr/bin/env python3
"""
LOCAL-649 — PARALLEL_STOPS (plan → parallel write → stitch) tests.

Covers the five contract points the task names:
  1. PLAN SCHEMA        — validate_plan accepts a good plan, repairs angles,
                          rejects wrong shapes.
  2. CALLBACK BUDGET    — enforce_callback_budget obeys D636 max(1,(n+1)//3),
                          earlier-only targets, ≤1 per stop; and the budget
                          delegates to the canonical cross_stop_reference_guard.
  3. NO CROSS-STOP      — derive_do_not_tell gives each stop every OTHER stop's
     REPETITION           owned facts and never its own; and the shipped tour's
                          D636 text guard drops over-budget callbacks (the
                          prototype's 2-when-1-allowed flaw) and self-repetition.
  4. DIRECTIONS ORDER   — write_stops_parallel preserves stop order regardless of
                          the order futures COMPLETE, so the fixed-order directions
                          in stitch still bind the right neighbours.
  5. FLAG OFF UNCHANGED — is_enabled() is False by default; the generate_tour_text
                          wiring is purely additive (0 deletions) and the plan
                          branch is skipped when the flag is unset.

Run: python3 -m pytest test_local649_parallel_stops.py -q
 or: python3 test_local649_parallel_stops.py
"""
import os
import subprocess
import unittest

import parallel_stops as ps


class TestFlagDefaultOff(unittest.TestCase):
    def test_default_off(self):
        os.environ.pop("PARALLEL_STOPS", None)
        self.assertFalse(ps.is_enabled())

    def test_only_exactly_1_enables(self):
        for val, want in (("1", True), ("0", False), ("true", False), ("", False)):
            os.environ["PARALLEL_STOPS"] = val
            self.assertEqual(ps.is_enabled(), want, val)
        os.environ.pop("PARALLEL_STOPS", None)

    @unittest.skipUnless(os.environ.get("LOCAL649_DIFF_CHECK") == "1",
                         "LEAD 2026-10-09: diff-vs-base check is only meaningful on the task branch; after merge it counts other tasks' changes")
    def test_wiring_is_additive_only(self):
        """The generate_tour_text.py change must add lines, delete none — the
        guarantee that OFF is byte-identical."""
        root = os.path.dirname(os.path.abspath(__file__))
        try:
            out = subprocess.check_output(
                ["git", "diff", "--numstat", "2e420fcf", "--", "generate_tour_text.py"],
                cwd=root, text=True).strip()
        except Exception as e:  # not a git checkout in some CI sandboxes
            self.skipTest(f"git unavailable: {e}")
        if not out:
            self.skipTest("no diff against base (already merged?)")
        added, removed, _ = out.split("\t", 2)
        self.assertEqual(removed, "0",
                         f"generate_tour_text.py must have 0 deletions, got {removed}")
        self.assertGreater(int(added), 0)


class TestCallbackBudget(unittest.TestCase):
    def test_budget_formula(self):
        self.assertEqual(ps.callback_budget(1), 1)
        self.assertEqual(ps.callback_budget(3), 1)
        self.assertEqual(ps.callback_budget(5), 2)
        self.assertEqual(ps.callback_budget(8), 3)

    def test_budget_matches_canonical(self):
        from cross_stop_reference_guard import callback_budget as canonical
        for n in range(0, 20):
            self.assertEqual(ps.callback_budget(n), canonical(n), n)

    def test_forward_and_self_refs_dropped(self):
        stops = [
            {"callbacks": [{"target": 1, "note": "forward"}]},   # forward → drop
            {"callbacks": [{"target": 1, "note": "self"}]},      # self → drop
            {"callbacks": [{"target": 0, "note": "ok"}]},        # earlier → ok
        ]
        out = ps.enforce_callback_budget(stops, 3)  # budget 1
        self.assertEqual(out[0]["callbacks"], [])
        self.assertEqual(out[1]["callbacks"], [])
        self.assertEqual(out[2]["callbacks"], [{"target": 0, "note": "ok"}])

    def test_tour_wide_budget_cap(self):
        # 3 stops → budget 1. Two legal earlier-callbacks offered; only 1 kept.
        stops = [
            {"callbacks": []},
            {"callbacks": [{"target": 0, "note": "a"}]},
            {"callbacks": [{"target": 1, "note": "b"}]},
        ]
        out = ps.enforce_callback_budget(stops, 3)
        kept = sum(len(s["callbacks"]) for s in out)
        self.assertEqual(kept, 1)

    def test_at_most_one_per_stop(self):
        stops = [
            {"callbacks": []},
            {"callbacks": []},
            {"callbacks": [{"target": 0, "note": "a"}, {"target": 1, "note": "b"}]},
        ]
        # 8 stops → budget 3, so the tour-wide cap is not the limiter here.
        out = ps.enforce_callback_budget(stops, 8)
        self.assertLessEqual(len(out[2]["callbacks"]), 1)


class TestPlanSchema(unittest.TestCase):
    def _good_plan(self):
        return {
            "thread": "a single connecting thread",
            "stops": [
                {"index": 0, "title": "A", "assigned_story": "s0",
                 "angle": "same", "owned_facts": ["f0"], "callbacks": []},
                {"index": 1, "title": "B", "assigned_story": "s1",
                 "angle": "same", "owned_facts": ["f1"],
                 "callbacks": [{"target": 0, "note": "n"}]},
                {"index": 2, "title": "C", "assigned_story": "s2",
                 "angle": "same", "owned_facts": ["f2"], "callbacks": []},
            ],
        }

    def test_valid_plan_normalises(self):
        v = ps.validate_plan(self._good_plan(), 3)
        self.assertEqual(v["thread"], "a single connecting thread")
        self.assertEqual(len(v["stops"]), 3)
        for s in v["stops"]:
            self.assertTrue(s["assigned_story"])
            self.assertTrue(s["angle"])
            self.assertIn("do_not_tell", s)

    def test_angles_repaired_distinct(self):
        """Fix 3: every stop 'same' angle must become distinct."""
        v = ps.validate_plan(self._good_plan(), 3)
        angles = [s["angle"].lower() for s in v["stops"]]
        self.assertEqual(len(set(angles)), 3, angles)

    def test_rejects_wrong_count(self):
        with self.assertRaises(ps.PlanValidationError):
            ps.validate_plan(self._good_plan(), 4)

    def test_rejects_empty_thread(self):
        p = self._good_plan()
        p["thread"] = ""
        with self.assertRaises(ps.PlanValidationError):
            ps.validate_plan(p, 3)

    def test_rejects_empty_assigned_story(self):
        p = self._good_plan()
        p["stops"][1]["assigned_story"] = ""
        with self.assertRaises(ps.PlanValidationError):
            ps.validate_plan(p, 3)

    def test_plan_tour_with_injected_llm(self):
        """plan_tour wires an injected llm_fn, parses JSON, validates, legalises."""
        import json

        def fake_llm(prompt, api_key):
            return json.dumps({
                "thread": "makers and their patrons",
                "stops": [
                    {"index": 0, "title": "A", "assigned_story": "a story",
                     "angle": "transformation", "owned_facts": ["x"], "callbacks": []},
                    {"index": 1, "title": "B", "assigned_story": "b story",
                     "angle": "transformation", "owned_facts": ["y"],
                     "callbacks": [{"target": 0, "note": "echo A"}]},
                    {"index": 2, "title": "C", "assigned_story": "c story",
                     "angle": "transformation", "owned_facts": ["z"],
                     # over budget + forward ref — must be legalised away
                     "callbacks": [{"target": 5, "note": "bad"}]},
                ],
            })

        research = [{"title": "A", "research": "ra"},
                    {"title": "B", "research": "rb"},
                    {"title": "C", "research": "rc"}]
        plan = ps.plan_tour("Test Museum", research, "KEY", llm_fn=fake_llm)
        # angles distinct (fix 3)
        self.assertEqual(len({s["angle"].lower() for s in plan["stops"]}), 3)
        # callbacks within budget (3 stops → 1) and earlier-only (fix 1)
        kept = sum(len(s["callbacks"]) for s in plan["stops"])
        self.assertLessEqual(kept, ps.callback_budget(3))
        for i, s in enumerate(plan["stops"]):
            for cb in s["callbacks"]:
                self.assertLess(cb["target"], i)

    def test_plan_tour_bad_json_raises(self):
        research = [{"title": "A", "research": "ra"}]
        with self.assertRaises(ps.PlanValidationError):
            ps.plan_tour("M", research, "KEY", llm_fn=lambda p, k: "not json")


class TestNoCrossStopRepetition(unittest.TestCase):
    def test_do_not_tell_has_others_not_self(self):
        """Fix: no two stops tell the same thing — each stop is told the OTHER
        stops' owned facts and never its own."""
        stops = [
            {"assigned_story": "s0", "owned_facts": ["f0"]},
            {"assigned_story": "s1", "owned_facts": ["f1"]},
            {"assigned_story": "s2", "owned_facts": ["f2"]},
        ]
        out = ps.derive_do_not_tell(stops)
        dnt0 = set(out[0]["do_not_tell"])
        self.assertIn("s1", dnt0)
        self.assertIn("f2", dnt0)
        self.assertNotIn("s0", dnt0)
        self.assertNotIn("f0", dnt0)

    def test_text_guard_drops_over_budget_callback(self):
        """The prototype shipped 2 callbacks when 1 was allowed. The D636 text
        guard reused in stitch must drop the extra."""
        from cross_stop_reference_guard import limit_thematic_bridges_in_text
        tour = (
            "Stop 1: Alpha\n"
            "This is the first stop with its own content and nothing to recall.\n\n"
            "Stop 2: Beta\n"
            "As you saw earlier on this tour, Alpha set the scene for what follows here.\n\n"
            "Stop 3: Gamma\n"
            "Echoing a theme from a previous stop, this closes the loop nicely here.\n"
        )
        cleaned, dropped = limit_thematic_bridges_in_text(tour)  # 3 stops → budget 1
        self.assertGreaterEqual(dropped, 1, "a 2nd callback over budget must be dropped")


class TestWriteOrderPreserved(unittest.TestCase):
    def test_parallel_write_preserves_stop_order(self):
        """Futures may COMPLETE out of order; the result must still land at the
        right index so stitch's fixed-order directions bind the right neighbours."""
        import concurrent.futures as cf

        class _Exec:
            def __init__(self, max_workers=None):
                self._tp = cf.ThreadPoolExecutor(max_workers=max_workers or 1)

            def __enter__(self):
                return self._tp

            def __exit__(self, *a):
                self._tp.shutdown(wait=True)
                return False

        poi_list = [{"name": f"Stop{i}"} for i in range(4)]
        spine_arc = [{"emotional_beat": f"b{i}", "unique_angle": f"a{i}",
                      "callback": "", "cliffhanger": ""} for i in range(4)]

        def gen(args):
            i, poi, spine_stop, fact_sheet, story_type = args
            # Narrate the index so we can prove it landed at the right slot. The
            # spine_stop that each stop received is echoed too.
            return (i, f"orient{i}", f"NARR {i} :: {spine_stop['emotional_beat']}",
                    10 + i, 0, 0.0)

        out = ps.write_stops_parallel(poi_list, spine_arc, gen, _Exec, max_workers=4)
        for i in range(4):
            self.assertEqual(out[i]["orientation"], f"orient{i}")
            self.assertTrue(out[i]["description"].startswith(f"NARR {i} ::"))
            self.assertIn(f"b{i}", out[i]["description"])

    def test_spine_arc_callback_names_earlier_stop(self):
        """plan_to_spine_arc must name the EARLIER stop by its poi title in the
        callback channel so the narration references a delivered stop BY NAME."""
        plan = {
            "thread": "t",
            "stops": [
                {"index": 0, "title": "A", "assigned_story": "s0", "angle": "x",
                 "owned_facts": [], "do_not_tell": [], "callbacks": []},
                {"index": 1, "title": "B", "assigned_story": "s1", "angle": "y",
                 "owned_facts": [], "do_not_tell": ["s0"],
                 "callbacks": [{"target": 0, "note": "the opening"}]},
            ],
        }
        poi_list = [{"name": "The Bathers"}, {"name": "Young Woman"}]
        arc = ps.plan_to_spine_arc(plan, poi_list)
        self.assertEqual(len(arc), 2)
        self.assertIn("The Bathers", arc[1]["callback"])
        # do_not_tell folded into the angle channel
        self.assertIn("Do NOT tell", arc[1]["unique_angle"])


class TestWorkNameFix(unittest.TestCase):
    def test_artist_title_resolved_to_work(self):
        """Fix 2: a stop stored under the ARTIST name narrates the WORK."""
        poi = {"name": "Georges Seurat"}
        rec = {"title": "Young Woman Powdering Herself", "creator": "Georges Seurat"}
        self.assertEqual(ps.resolve_stop_work_name(poi, rec),
                         "Young Woman Powdering Herself")

    def test_work_title_not_overridden(self):
        poi = {"name": "Young Woman Powdering Herself"}
        rec = {"title": "Young Woman Powdering Herself", "creator": "Georges Seurat"}
        self.assertIsNone(ps.resolve_stop_work_name(poi, rec))

    def test_no_record_no_change(self):
        self.assertIsNone(ps.resolve_stop_work_name({"name": "X"}, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
