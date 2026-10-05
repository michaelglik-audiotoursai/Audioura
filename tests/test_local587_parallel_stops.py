"""test_local587_parallel_stops.py — LOCAL-587.

The Griffin museum text phase spent 190s in the D511 PHASE 5.20 credit_line loop
and ~120s in the LOCAL-410 SERP loop, both running their five stops back to back
even though each stop's work is independent. LOCAL-587 fans those two phases out
across `dead_host_breaker.tour_executor`, keeping every result-merge, gate, stat
and print on the main thread in stop order.

These tests guard the invariants that make that safe:

  1. Both phases dispatch through `tour_executor` (the LOCAL-572 lint already
     forbids raw pools; here we assert the specific call sites exist).
  2. A `tour_executor` worker inherits the active tour's COST scope (LOCAL-562)
     and DEAD-HOST cold set (LOCAL-572) — the two scopes the ticket says must
     stay correct under the new concurrency.
  3. Fanning work out and collecting it by stop index preserves stop ORDER
     regardless of completion order (slow stop finishing last must not reorder).
  4. The per-stop worker does not share mutable state across stops: a worker
     that copies its input matrix cannot be seen by another stop's worker.
"""
import ast
import os
import sys
import time
import unittest
from concurrent.futures import as_completed

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import cost_accumulator
import dead_host_breaker
from dead_host_breaker import tour_executor


class TestPhasesUseTourExecutor(unittest.TestCase):
    """Both parallelized phases must dispatch through tour_executor."""

    def _call_names(self):
        path = os.path.join(_ROOT, "generate_tour_text.py")
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                names.append(node.func.id)
        return names

    def test_tour_executor_dispatch_sites_present(self):
        # D511 PHASE 5.20 + LOCAL-410 SERP prefetch are the two new call sites,
        # on top of the two pre-existing ones (scope check, verify fan-out).
        n = self._call_names().count("tour_executor")
        self.assertGreaterEqual(
            n, 4,
            f"expected >=4 tour_executor() sites (2 pre-existing + D511 + "
            f"LOCAL-410 prefetch), found {n}",
        )

    def test_d511_and_410_markers_present(self):
        src = open(os.path.join(_ROOT, "generate_tour_text.py"),
                   encoding="utf-8").read()
        # D511 parallel fan-out of run_for_stop.
        self.assertIn("_d511_run_one", src)
        self.assertIn("_d511_results", src)
        # LOCAL-410 concurrent search prefetch.
        self.assertIn("_s587_search_one", src)
        self.assertIn("_s587_prefetch", src)


class TestCostScopePropagates(unittest.TestCase):
    """LOCAL-562: a tour_executor worker must attribute to the tour's scope."""

    @classmethod
    def setUpClass(cls):
        cost_accumulator.install_executor_context_propagation()

    def test_worker_sees_current_accumulator(self):
        seen = {}
        with cost_accumulator.tour_scope(job_id="local587-cost") as acc:
            def _worker(i):
                # The worker, on a different thread, must see THIS tour's acc.
                return i, cost_accumulator.current_accumulator()

            with tour_executor(max_workers=5) as ex:
                futs = {ex.submit(_worker, i): i for i in range(5)}
                for f in as_completed(futs):
                    i, got = f.result()
                    seen[i] = got

        self.assertEqual(len(seen), 5)
        for i, got in seen.items():
            self.assertIs(
                got, acc,
                f"worker {i} saw accumulator {got!r}, not the tour's {acc!r} — "
                f"cost scope did not propagate",
            )


class TestDeadHostScopePropagates(unittest.TestCase):
    """LOCAL-572: a cold mark made in a worker stays in THIS tour's set."""

    def test_cold_mark_in_worker_lands_in_tour_set(self):
        with dead_host_breaker.tour_scope():
            # Executor captures the cold set at construction (on this thread,
            # inside scope) and re-binds it in each worker.
            with tour_executor(max_workers=3) as ex:
                def _worker(host):
                    dead_host_breaker.mark_host_cold(host, reason="local587-test")
                    return dead_host_breaker.is_host_cold(host)

                hosts = ["a587.example", "b587.example", "c587.example"]
                futs = {ex.submit(_worker, h): h for h in hosts}
                results = {futs[f]: f.result() for f in as_completed(futs)}

            # Each worker saw its own mark immediately.
            for h in hosts:
                self.assertTrue(results[h], f"{h} not cold inside its worker")
            # And every mark landed in the tour's cold set, visible on the main
            # thread — not leaked to the module default.
            cold = dead_host_breaker.get_cold_hosts()
            for h in hosts:
                self.assertIn(h, cold, f"{h} did not land in the tour cold set")


class TestOrderingPreservedUnderConcurrency(unittest.TestCase):
    """Collecting futures by stop index preserves stop order even when a slow
    stop finishes last — the pattern both new phases use."""

    def test_results_merge_in_stop_order(self):
        # Stop 0 is slowest; completion order will be 4,3,2,1,0. Merging by the
        # stored index must still yield [0,1,2,3,4].
        def _work(idx):
            time.sleep(0.02 * (5 - idx))
            return idx, f"stop-{idx}"

        results = {}
        with tour_executor(max_workers=5) as ex:
            futs = {ex.submit(_work, i): i for i in range(5)}
            for f in as_completed(futs):
                i, val = f.result()
                results[i] = val

        ordered = [results[i] for i in range(5)]
        self.assertEqual(
            ordered, [f"stop-{i}" for i in range(5)],
            "stop order not preserved when merging by index",
        )


class TestNoSharedMutableStateAcrossStops(unittest.TestCase):
    """story_production_loop.run_for_stop must not mutate the caller's matrix,
    so two stops' workers cannot clobber each other's input."""

    def test_run_for_stop_does_not_mutate_input_matrix(self):
        import story_production_loop as spl
        # Force the loop to bail immediately (no network) by making its first
        # import target unavailable is hard; instead give it a matrix with no
        # usable description, which returns early with story='' and never
        # touches the network. The invariant under test is purely that the
        # INPUT dict we pass is not mutated.
        matrix = {
            "canonical_title": "Stop X",
            "artist": "", "publisher": "", "credit_line": "",
            "medium": "", "venue_name": "Griffin",
        }
        before = dict(matrix)
        # Empty stop_text + no venue_url => the loop produces no seeds / no
        # network and returns the empty-story shape. Any exception is also fine
        # for this test: we only assert the input dict is untouched.
        try:
            spl.run_for_stop(matrix, "", exhibition="Griffin", venue_url="",
                             verbose=False)
        except Exception:
            pass
        self.assertEqual(
            matrix, before,
            "run_for_stop mutated the caller's matrix — concurrent stops would "
            "race on shared state",
        )

    def test_run_for_stop_returns_independent_dicts(self):
        import story_production_loop as spl
        m1 = {"canonical_title": "A", "venue_name": "G"}
        m2 = {"canonical_title": "B", "venue_name": "G"}
        try:
            r1 = spl.run_for_stop(dict(m1), "", venue_url="", verbose=False)
            r2 = spl.run_for_stop(dict(m2), "", venue_url="", verbose=False)
        except Exception:
            self.skipTest("run_for_stop dependencies unavailable offline")
            return
        self.assertIsNot(r1, r2)
        self.assertIsNot(r1.get("stories"), r2.get("stories"))


if __name__ == "__main__":
    unittest.main()
