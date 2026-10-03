"""test_local572_cold_host_per_tour.py — LOCAL-572 verification tests.

Michael's dead-host rule (BINDING, 2026-08-12): the FIRST 429/timeout marks a
host cold "for the remainder of the run". LOCAL-572 clarifies (2026-10-03) that
"the run" is ONE TOUR, not the lifetime of the long-lived container/Cloud-Run
process. These tests pin that scoping:

  (a) a host marked cold in tour 1 is NOT cold in tour 2 run afterwards in the
      SAME process — this is the release fix; it is RED on storied, where the
      cold set is a single process-level set that never resets per tour.
  (b) within one tour a cold host stays cold across stops, including when the
      mark is made from a worker thread (per-stop parallelism).
  (c) two tours generated CONCURRENTLY each have their own cold set — a cold
      mark in one does not leak into the other.

The public API (mark_host_cold / is_host_cold / get_cold_hosts /
reset_cold_hosts) is unchanged; scoping is driven by begin_tour_scope() /
tour_scope() plus context propagation into worker threads.
"""
import os
import sys
import threading
import time
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dead_host_breaker
from dead_host_breaker import (
    mark_host_cold, is_host_cold, get_cold_hosts, reset_cold_hosts,
    begin_tour_scope, end_tour_scope, tour_scope,
    copy_tour_context, run_in_tour_context, _WIKIMEDIA_GROUP,
)


def _run_tour(fn, *args, **kwargs):
    """Run fn as a brand-new tour in a fresh thread.

    A new threading.Thread starts with its own (default) contextvar state, which
    is exactly how the services run each tour (generate_tour_async in a daemon
    Thread). Inside the thread we call begin_tour_scope() to install this tour's
    cold set — mirroring generate_tour_text()'s entry.
    """
    box = {}

    def _entry():
        begin_tour_scope()
        box['result'] = fn(*args, **kwargs)

    t = threading.Thread(target=_entry)
    t.start()
    t.join()
    return box.get('result')


class TestColdHostPerTour(unittest.TestCase):

    def setUp(self):
        # Clean module-level default set between tests.
        reset_cold_hosts()

    def tearDown(self):
        reset_cold_hosts()

    # --- (a) cold in tour 1 is not cold in tour 2 (same process) ---------------

    def test_cold_mark_does_not_persist_across_tours(self):
        """RED on storied: a 429 in tour 1 must not disable the host in tour 2.

        On storied the cold set is one process-level set with no per-tour reset,
        so after tour 1 marks Wikidata cold, tour 2 sees it cold and museum stops
        clean-fail as 'unresolvable'. With LOCAL-572 each tour starts fresh.
        """
        # Tour 1: a Wikimedia 429 marks the whole bucket cold for THIS tour.
        def tour1():
            mark_host_cold('https://query.wikidata.org', reason='simulated 429')
            return is_host_cold('https://query.wikidata.org')

        self.assertTrue(_run_tour(tour1), "host should be cold within tour 1")

        # Tour 2: run afterwards in the same process — must start clean.
        def tour2():
            return is_host_cold('https://query.wikidata.org')

        self.assertFalse(
            _run_tour(tour2),
            "host marked cold in tour 1 must NOT be cold in a later tour "
            "(this is the LOCAL-572 release fix; RED on storied)",
        )

    def test_wikipedia_recovers_next_tour(self):
        """en.wikipedia.org cold in tour 1 is reachable again in tour 2."""
        self.assertTrue(_run_tour(
            lambda: (mark_host_cold('https://en.wikipedia.org/wiki/X'),
                     is_host_cold('https://en.wikipedia.org'))[1]
        ))
        self.assertFalse(_run_tour(lambda: is_host_cold('https://en.wikipedia.org')))
        self.assertFalse(_run_tour(lambda: is_host_cold('https://fr.wikipedia.org')))

    # --- (b) within a tour it stays cold across stops, incl. worker threads ----

    def test_cold_persists_within_tour_across_stops(self):
        """One tour, several stops run serially: the first 429 keeps the host
        cold for every later stop in the SAME tour."""
        def tour():
            seen = []
            # stop 1: hits a 429
            mark_host_cold('https://query.wikidata.org', reason='429')
            # stops 2..4: should all observe the host as cold (no retry)
            for _ in range(3):
                seen.append(is_host_cold('https://query.wikidata.org'))
            return seen

        seen = _run_tour(tour)
        self.assertEqual(seen, [True, True, True])

    def test_cold_mark_from_worker_thread_visible_tour_wide(self):
        """A cold mark made inside a per-stop WORKER THREAD is visible to the
        rest of the tour. Worker threads don't inherit context vars, so the pool
        must copy the tour context (copy_tour_context / run_in_tour_context)."""
        def tour():
            # The tour captures its context and fans stops out to a pool, exactly
            # like story_first_pipeline_batch does.
            ctx = copy_tour_context()

            def stop_marks_cold():
                mark_host_cold('https://query.wikidata.org', reason='429 in worker')
                return is_host_cold('https://query.wikidata.org')

            def stop_checks_cold():
                return is_host_cold('https://query.wikidata.org')

            with ThreadPoolExecutor(max_workers=2) as ex:
                f1 = ex.submit(run_in_tour_context, ctx, stop_marks_cold)
                worker_saw_cold = f1.result()
                # A later stop, also on a worker thread, must see it cold.
                f2 = ex.submit(run_in_tour_context, ctx, stop_checks_cold)
                later_stop_saw_cold = f2.result()

            # And the tour's own (main) thread must see it cold too.
            main_saw_cold = is_host_cold('https://query.wikidata.org')
            return worker_saw_cold, later_stop_saw_cold, main_saw_cold

        worker_saw_cold, later_stop_saw_cold, main_saw_cold = _run_tour(tour)
        self.assertTrue(worker_saw_cold, "marking thread should see its own mark")
        self.assertTrue(later_stop_saw_cold, "later stop (worker) must see cold")
        self.assertTrue(main_saw_cold, "tour main thread must see worker's mark")

    def test_wikimedia_bucket_still_shared_within_tour(self):
        """Within a tour the Wikimedia bucket rule is unchanged: a 429 on
        en.wikipedia.org makes query.wikidata.org cold too."""
        def tour():
            mark_host_cold('https://en.wikipedia.org/wiki/Foo')
            return (is_host_cold('https://query.wikidata.org'),
                    is_host_cold('https://fr.wikipedia.org'),
                    _WIKIMEDIA_GROUP in get_cold_hosts())
        wikidata_cold, fr_cold, group_in_set = _run_tour(tour)
        self.assertTrue(wikidata_cold)
        self.assertTrue(fr_cold)
        self.assertTrue(group_in_set)

    # --- (c) two concurrent tours do not leak into each other ------------------

    def test_concurrent_tours_isolated(self):
        """Two tours generated at the same time in one process each keep their
        own cold set; a cold mark in tour A does not leak into tour B."""
        barrier = threading.Barrier(2)
        results = {}

        def tour_a():
            begin_tour_scope()
            mark_host_cold('https://query.wikidata.org', reason='429 in tour A')
            # Wait so tour B is definitely running concurrently.
            barrier.wait(timeout=5)
            time.sleep(0.05)
            results['a_self_cold'] = is_host_cold('https://query.wikidata.org')

        def tour_b():
            begin_tour_scope()
            barrier.wait(timeout=5)
            # Tour B never marked anything cold; it must see Wikidata as reachable
            # even though tour A marked it cold concurrently.
            time.sleep(0.05)
            results['b_sees_cold'] = is_host_cold('https://query.wikidata.org')
            results['b_other'] = is_host_cold('https://example.com')

        ta = threading.Thread(target=tour_a)
        tb = threading.Thread(target=tour_b)
        ta.start(); tb.start()
        ta.join(); tb.join()

        self.assertTrue(results['a_self_cold'], "tour A must see its own mark")
        self.assertFalse(results['b_sees_cold'],
                         "tour A's cold mark must NOT leak into concurrent tour B")
        self.assertFalse(results['b_other'])

    def test_concurrent_tours_via_real_batch(self):
        """End-to-end: drive two tours concurrently through the real
        story_first_pipeline_batch fan-out and confirm cold isolation.

        Each stop's 'pipeline' marks Wikidata cold if its stop_data says so, and
        reports whether it already saw Wikidata as cold BEFORE marking. Tour A's
        stops mark cold; tour B's stops only observe. Because the batch propagates
        the per-tour context into its worker threads, tour B's stops must never
        observe tour A's cold mark.
        """
        import story_first

        story_first.parallelise_across_stops()

        def fake_pipeline(stop_data, fact_sheet='', snippets=None,
                          credit_line='', existing_search_results=None):
            saw_cold_before = is_host_cold('https://query.wikidata.org')
            if stop_data.get('mark_cold'):
                mark_host_cold('https://query.wikidata.org', reason='429')
            time.sleep(0.05)
            return {
                'stories': [], 'anchor_facts': {}, 'seeking_result': {},
                'fullpage_fetch_result': {}, 'evaluation_count': 0,
                'prefilter_input_count': 0, 'verified_count': 0,
                'elapsed_seconds': 0.0, 'cost_usd': 0.0, 'fallback': False,
                'budget_exhausted': False,
                'saw_cold_before': saw_cold_before,
            }

        def make_stops(mark_cold):
            return [
                {'name': f'stop_{i}',
                 'stop_data': {'canonical_title': f'stop_{i}', 'mark_cold': mark_cold},
                 'snippets': [], 'credit_line': '', 'existing_search_results': []}
                for i in range(4)
            ]

        box = {}
        barrier = threading.Barrier(2)

        def run_tour(key, mark_cold):
            begin_tour_scope()
            barrier.wait(timeout=5)
            with unittest.mock.patch('story_first.story_first_pipeline',
                                     side_effect=fake_pipeline):
                res = story_first.story_first_pipeline_batch(
                    make_stops(mark_cold), tour_budget_seconds=10.0)
            box[key] = res

        ta = threading.Thread(target=run_tour, args=('a', True))
        tb = threading.Thread(target=run_tour, args=('b', False))
        ta.start(); tb.start()
        ta.join(); tb.join()

        # Tour B never marked cold, so NO stop in tour B should have seen Wikidata
        # cold — even though tour A was marking it cold concurrently.
        b_saw_cold = [r['saw_cold_before'] for r in box['b'].values()]
        self.assertFalse(any(b_saw_cold),
                         f"concurrent tour B leaked cold state: {b_saw_cold}")


if __name__ == '__main__':
    import unittest.mock  # noqa: F401  (used in test_concurrent_tours_via_real_batch)
    unittest.main(verbosity=2)
