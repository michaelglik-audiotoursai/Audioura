#!/usr/bin/env python3
"""test_local651_fast_pipeline.py — unit tests for the FAST_PIPELINE overlap.

Pure, offline, fast. Covers:
  * run_parallel: order preservation, exception re-raise, inline for 0/1 jobs;
  * TIMING PROOF — concurrent run of N slow fake jobs finishes in ~1 unit, not N
    (so the overlap is real), while the serial baseline takes ~N units;
  * thread-safety — concurrent jobs writing distinct keys do not clobber;
  * flag default OFF;
  * stop_editor.edit_tour_text: flag ON vs OFF produce the IDENTICAL text with a
    fake per-stop LLM (equal output), and ON actually overlaps the per-stop waits.
"""
import os
import threading
import time
import unittest

import fast_pipeline as fp


def _slow(value, delay=0.2):
    def _job():
        time.sleep(delay)
        return value
    return _job


class TestRunParallel(unittest.TestCase):
    def test_default_off(self):
        os.environ.pop('FAST_PIPELINE', None)
        self.assertFalse(fp.is_enabled())

    def test_flag_on(self):
        old = os.environ.get('FAST_PIPELINE')
        try:
            os.environ['FAST_PIPELINE'] = '1'
            self.assertTrue(fp.is_enabled())
        finally:
            if old is None:
                os.environ.pop('FAST_PIPELINE', None)
            else:
                os.environ['FAST_PIPELINE'] = old

    def test_order_preserved(self):
        jobs = [(lambda i=i: i * i) for i in range(6)]
        self.assertEqual(fp.run_parallel(jobs), [0, 1, 4, 9, 16, 25])

    def test_empty_and_single(self):
        self.assertEqual(fp.run_parallel([]), [])
        self.assertEqual(fp.run_parallel([lambda: 42]), [42])

    def test_exception_reraised(self):
        def boom():
            raise ValueError('kaboom')
        with self.assertRaises(ValueError):
            fp.run_parallel([lambda: 1, boom, lambda: 3])

    def test_timing_overlap_is_real(self):
        # 5 jobs that each sleep 0.2s. Serial would take ~1.0s; concurrent ~0.2s.
        jobs = [_slow(i, 0.2) for i in range(5)]
        t0 = time.time()
        out = fp.run_parallel(jobs, max_workers=5)
        elapsed = time.time() - t0
        self.assertEqual(out, [0, 1, 2, 3, 4])
        # Allow generous headroom for CI jitter, but it MUST be far below serial 1.0s.
        self.assertLess(elapsed, 0.6, f"overlap not real: {elapsed:.2f}s")

    def test_serial_baseline_is_slow(self):
        # Confirms the fakes really do sleep (so the overlap test is meaningful).
        jobs = [_slow(i, 0.1) for i in range(5)]
        t0 = time.time()
        _ = [j() for j in jobs]
        self.assertGreater(time.time() - t0, 0.45)

    def test_concurrent_distinct_keys_no_clobber(self):
        shared = {}
        lock = threading.Lock()

        def make(k):
            def _job():
                time.sleep(0.02)
                with lock:
                    shared[k] = k * 10
                return k
            return _job

        out = fp.run_parallel([make(k) for k in range(20)], max_workers=6)
        self.assertEqual(out, list(range(20)))
        self.assertEqual(shared, {k: k * 10 for k in range(20)})


# ── stop_editor: equal output ON vs OFF + real overlap ────────────────────────

_TOUR = """Audio Tour: Test Museum

Stop 1: First Work
This is the first stop body with enough words to be edited by the pass here now.

Stop 2: Second Work
This is the second stop body with enough words to be edited by the pass today.

Stop 3: Third Work
This is the third stop body with enough words to be edited by the pass as well.
"""


class TestStopEditorOverlap(unittest.TestCase):
    def setUp(self):
        import stop_editor
        self.se = stop_editor
        # Enable the editor regardless of env default for the test.
        os.environ['STOP_EDITOR'] = '1'
        os.environ['STOP_EDITOR_ENABLED'] = '1'
        self._fp_old = os.environ.get('FAST_PIPELINE')

    def tearDown(self):
        if self._fp_old is None:
            os.environ.pop('FAST_PIPELINE', None)
        else:
            os.environ['FAST_PIPELINE'] = self._fp_old

    def _fake_llm(self, delay=0.0):
        # A deterministic "editor": returns the body unchanged but SLEEPS, so we
        # can time the overlap. Deterministic ⇒ ON and OFF yield identical text.
        def _llm(prompt, api_key):
            if delay:
                time.sleep(delay)
            # The editor prompt embeds the body; echo a stable canned reply so the
            # validator keeps the original (equal output both ways).
            return None  # None ⇒ editor keeps the original block (safe, deterministic)
        return _llm

    def test_off_vs_on_identical_text(self):
        if not self.se.is_enabled():
            self.skipTest('stop_editor disabled in this env')
        os.environ.pop('FAST_PIPELINE', None)
        off = self.se.edit_tour_text(_TOUR, venue_name='Test Museum',
                                     llm_fn=self._fake_llm())
        os.environ['FAST_PIPELINE'] = '1'
        on = self.se.edit_tour_text(_TOUR, venue_name='Test Museum',
                                    llm_fn=self._fake_llm())
        self.assertEqual(off, on, "FAST_PIPELINE ON changed the editor output")

    def test_on_overlaps_per_stop_waits(self):
        if not self.se.is_enabled():
            self.skipTest('stop_editor disabled in this env')
        # Each per-stop edit sleeps 0.2s. 3 stops serial ≈ 0.6s; parallel ≈ 0.2s.
        os.environ.pop('FAST_PIPELINE', None)
        t0 = time.time()
        self.se.edit_tour_text(_TOUR, venue_name='Test Museum',
                               llm_fn=self._fake_llm(delay=0.2))
        serial = time.time() - t0

        os.environ['FAST_PIPELINE'] = '1'
        t0 = time.time()
        self.se.edit_tour_text(_TOUR, venue_name='Test Museum',
                               llm_fn=self._fake_llm(delay=0.2))
        parallel = time.time() - t0

        self.assertGreater(serial, 0.5, f"serial baseline too fast: {serial:.2f}s")
        self.assertLess(parallel, serial * 0.75,
                        f"no overlap: serial={serial:.2f}s parallel={parallel:.2f}s")


if __name__ == '__main__':
    unittest.main(verbosity=2)
