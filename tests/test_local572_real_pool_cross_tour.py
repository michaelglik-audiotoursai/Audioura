"""test_local572_real_pool_cross_tour.py — LOCAL-572 r2 behaviour test.

The r1 bounce reason: most Wikipedia/Wikidata fetches run inside the per-stop
parallel pools (LOCAL-441/445). A pool worker that did not copy the tour context
marked the host cold in the PROCESS-LEVEL default set, so a 429 from a stop
worker in tour 1 poisoned every later tour in the same long-lived process.

This test uses the REAL helper pool — dead_host_breaker.tour_executor — exactly
as generate_tour_text()'s per-stop fan-out now does, and pins:

  * tour 1 marks a host cold from INSIDE a pool worker;
  * that mark is visible to the rest of tour 1 (across stops);
  * tour 2, run afterwards in the SAME process, does NOT see the host cold.

RED on a2a10c5 / GREEN after: this test imports `tour_executor`, which does not
exist on a2a10c5, so to show RED the SAME scenario is reproduced on a2a10c5
using only its base public API (a raw per-stop ThreadPoolExecutor whose worker
calls mark_host_cold with no context copy — exactly what the per-stop pools did
there). That raw-pool scenario leaks the cold mark into tour 2 via the
process-level set. The exact commands and output are pasted in
SUBMISSION_LOCAL-572.md (## r2). On this branch, `tour_executor` keeps the mark
inside tour 1 and this test is GREEN.
"""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dead_host_breaker
from dead_host_breaker import (
    mark_host_cold, is_host_cold, begin_tour_scope, reset_cold_hosts,
    tour_executor,
)

HOST = "https://query.wikidata.org"


def _run_tour_in_thread(fn):
    """Run fn() as a fresh tour: its own thread (default contextvar state) with
    begin_tour_scope() at entry — mirroring how the services launch each tour in
    a daemon Thread and how generate_tour_text() opens the scope."""
    box = {}

    def _entry():
        begin_tour_scope()
        box["result"] = fn()

    t = threading.Thread(target=_entry)
    t.start()
    t.join()
    return box.get("result")


class TestRealPoolCrossTour(unittest.TestCase):
    def setUp(self):
        # Make sure no prior test left the process default set populated.
        reset_cold_hosts()

    def test_tour_executor_no_cross_tour_leak(self):
        """GREEN after: a cold mark made inside a tour_executor worker in tour 1
        stays within tour 1 and does NOT leak into tour 2 in the same process."""

        def tour1():
            # Fan stops out exactly like generate_tour_text()'s per-stop pool.
            def stop_worker(stop_idx):
                if stop_idx == 0:
                    # First stop hits a 429 and marks the Wikimedia bucket cold.
                    mark_host_cold(HOST, reason="429 in tour1 stop worker")
                # Every stop checks before fetching; later stops must see cold.
                return is_host_cold(HOST)

            with tour_executor(max_workers=4) as ex:
                seen = list(ex.map(stop_worker, range(4)))
            # The tour's own thread must also see it cold.
            return seen, is_host_cold(HOST)

        def tour2():
            # A brand-new tour in the same process. It never marked anything;
            # the host must be reachable again.
            def stop_worker(stop_idx):
                return is_host_cold(HOST)

            with tour_executor(max_workers=4) as ex:
                seen = list(ex.map(stop_worker, range(4)))
            return seen, is_host_cold(HOST)

        t1_seen, t1_main = _run_tour_in_thread(tour1)
        t2_seen, t2_main = _run_tour_in_thread(tour2)

        # Within tour 1: once stop 0 marks cold, all stops + main thread see cold.
        self.assertTrue(all(t1_seen),
                        f"within tour1 all stops must see cold, got {t1_seen}")
        self.assertTrue(t1_main, "tour1 main thread must see the worker's mark")

        # Across tours: tour 2 must NOT inherit tour 1's cold mark.
        self.assertFalse(any(t2_seen),
                         f"tour1 cold mark LEAKED into tour2 pool workers: {t2_seen}")
        self.assertFalse(t2_main,
                         "tour1 cold mark LEAKED into tour2 main thread")

        # And nothing leaked to the process-level default set either.
        self.assertEqual(dead_host_breaker.get_cold_hosts(), set())


if __name__ == "__main__":
    unittest.main()
