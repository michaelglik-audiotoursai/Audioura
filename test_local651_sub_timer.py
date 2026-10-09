#!/usr/bin/env python3
"""test_local651_sub_timer.py — unit tests for the [TIMING-SUB] sub-timer.

Covers the Step-1 profiling infrastructure added in phase_timer.py:
  * steps are attributed to the phase that PhaseTimer last started;
  * concurrent recording from many threads does not lose or corrupt entries
    (thread-safe accumulate);
  * the timed_step decorator preserves the wrapped function's identity;
  * summary() returns a table sorted by total cost.

These are pure, offline, fast tests — no network, no LLM.
"""
import threading
import time
import unittest

import phase_timer as pt


class TestSubTimerAttribution(unittest.TestCase):
    def setUp(self):
        pt.reset_sub_timer()
        pt.set_current_phase('unknown')

    def test_phase_set_by_phase_timer(self):
        timer = pt.PhaseTimer()
        timer.start('poi_selection')
        self.assertEqual(pt.get_current_phase(), 'poi_selection')
        timer.start('story_first')
        self.assertEqual(pt.get_current_phase(), 'story_first')

    def test_step_attributed_to_current_phase(self):
        timer = pt.PhaseTimer()
        st = pt.get_sub_timer()
        timer.start('poi_selection')
        with st.step('resolve_venue'):
            time.sleep(0.01)
        timer.start('story_first')
        with st.step('serp_search'):
            time.sleep(0.01)
        steps = st.get_steps()
        self.assertIn(('poi_selection', 'resolve_venue'), steps)
        self.assertIn(('story_first', 'serp_search'), steps)
        self.assertEqual(steps[('poi_selection', 'resolve_venue')]['count'], 1)

    def test_explicit_phase_overrides_current(self):
        st = pt.get_sub_timer()
        pt.set_current_phase('packing')
        with st.step('x', phase='external_lookups'):
            pass
        self.assertIn(('external_lookups', 'x'), st.get_steps())

    def test_decorator_preserves_identity_and_records(self):
        @pt.timed_step('my_step')
        def add(a, b):
            """docstring kept?"""
            return a + b
        self.assertEqual(add.__name__, 'add')
        self.assertEqual(add.__doc__, 'docstring kept?')
        pt.set_current_phase('fact_sheets')
        self.assertEqual(add(2, 3), 5)
        self.assertIn(('fact_sheets', 'my_step'), pt.get_sub_timer().get_steps())

    def test_decorator_reraises_and_still_records(self):
        @pt.timed_step('boom')
        def boom():
            raise ValueError('kaboom')
        pt.set_current_phase('story_first')
        with self.assertRaises(ValueError):
            boom()
        # Elapsed is still recorded even though the call raised.
        self.assertIn(('story_first', 'boom'), pt.get_sub_timer().get_steps())


class TestSubTimerThreadSafety(unittest.TestCase):
    def setUp(self):
        pt.reset_sub_timer()

    def test_concurrent_record_no_loss(self):
        st = pt.get_sub_timer()
        n_threads = 16
        per_thread = 50

        def worker(tid):
            # All threads record under the SAME (phase, step) key to maximise
            # contention on the accumulate path.
            for _ in range(per_thread):
                st.record('story_first', 'classify_verify', 0.001)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        agg = st.get_steps()[('story_first', 'classify_verify')]
        # No increment may be lost under the lock.
        self.assertEqual(agg['count'], n_threads * per_thread)
        self.assertAlmostEqual(agg['total'], n_threads * per_thread * 0.001,
                               places=3)

    def test_concurrent_distinct_keys(self):
        st = pt.get_sub_timer()

        def worker(tid):
            st.record('poi_selection', f'step_{tid}', 0.01)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        steps = st.get_steps()
        self.assertEqual(sum(1 for (p, s) in steps if p == 'poi_selection'), 32)


class TestSubTimerSummary(unittest.TestCase):
    def setUp(self):
        pt.reset_sub_timer()

    def test_summary_sorted_by_total_desc(self):
        st = pt.get_sub_timer()
        st.record('story_first', 'cheap', 0.1)
        st.record('poi_selection', 'expensive', 5.0)
        st.record('packing', 'medium', 1.0)
        out = st.summary()
        # The most expensive step must appear before the cheapest in the table.
        self.assertLess(out.index('expensive'), out.index('medium'))
        self.assertLess(out.index('medium'), out.index('cheap'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
