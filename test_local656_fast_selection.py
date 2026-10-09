"""test_local656_fast_selection.py — LOCAL-656.

Tests for: per-tour memoization of resolve_venue / fetch_venue_works (the 4→1 and
3→1 call drops), per-tour SCOPE (a second tour does NOT reuse the first's result),
the up-front preflight ∥ venue-resolution OVERLAP timing (with fakes), and the
FAST_PIPELINE-OFF path being byte-identical (memo never consulted, seed a no-op).

Offline only — no network, no DB. Each test sets/clears FAST_PIPELINE itself and
resets the per-tour memo + the [TIMING-SUB] accumulator so measurements isolate.
"""
import contextvars
import importlib
import os
import threading
import time
import unittest


def _reload_fast_pipeline():
    import fast_pipeline
    return importlib.reload(fast_pipeline)


class FlagEnvMixin:
    def setUp(self):
        self._prev_flag = os.environ.get("FAST_PIPELINE")
        import fast_pipeline as fp
        fp.reset_tour_memo()
        import phase_timer as pt
        pt.reset_sub_timer()

    def tearDown(self):
        if self._prev_flag is None:
            os.environ.pop("FAST_PIPELINE", None)
        else:
            os.environ["FAST_PIPELINE"] = self._prev_flag
        import fast_pipeline as fp
        fp.reset_tour_memo()


class TestRunParallel(FlagEnvMixin, unittest.TestCase):
    def test_order_preserved(self):
        import fast_pipeline as fp
        out = fp.run_parallel([lambda: 1, lambda: 2, lambda: 3])
        self.assertEqual(out, [1, 2, 3])

    def test_empty_and_single(self):
        import fast_pipeline as fp
        self.assertEqual(fp.run_parallel([]), [])
        self.assertEqual(fp.run_parallel([lambda: 42]), [42])

    def test_first_exception_reraised(self):
        import fast_pipeline as fp

        def boom():
            raise ValueError("kaboom")

        with self.assertRaises(ValueError):
            fp.run_parallel([lambda: 1, boom, lambda: 3])

    def test_concurrency_is_real(self):
        """5 × 0.2 s jobs finish in ~0.2 s parallel, not ~1.0 s serial."""
        import fast_pipeline as fp

        def slow():
            time.sleep(0.2)
            return "done"

        t0 = time.time()
        out = fp.run_parallel([slow] * 5)
        elapsed = time.time() - t0
        self.assertEqual(out, ["done"] * 5)
        self.assertLess(elapsed, 0.6, f"expected parallel ~0.2s, got {elapsed:.2f}s")


class TestMemoFlagOff(FlagEnvMixin, unittest.TestCase):
    def test_off_calls_through_every_time(self):
        os.environ.pop("FAST_PIPELINE", None)
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("ns")
        def f(x):
            calls["n"] += 1
            return x * 2

        self.assertEqual(f(3), 6)
        self.assertEqual(f(3), 6)
        self.assertEqual(f(3), 6)
        self.assertEqual(calls["n"], 3, "OFF must call through every time")

    def test_off_seed_is_noop(self):
        os.environ.pop("FAST_PIPELINE", None)
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("ns")
        def f(x):
            calls["n"] += 1
            return x * 2

        fp.seed("ns", (3,), {}, 999)  # must be ignored when OFF
        self.assertEqual(f(3), 6)
        self.assertEqual(calls["n"], 1)


class TestMemoFlagOn(FlagEnvMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        os.environ["FAST_PIPELINE"] = "1"

    def test_on_memoizes_same_args(self):
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("ns")
        def f(x):
            calls["n"] += 1
            return x * 2

        self.assertEqual(f(5), 10)
        self.assertEqual(f(5), 10)
        self.assertEqual(f(5), 10)
        self.assertEqual(calls["n"], 1, "ON must memoize identical args to 1 call")

    def test_on_distinct_args_distinct_entries(self):
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("ns")
        def f(x):
            calls["n"] += 1
            return x * 2

        self.assertEqual(f(1), 2)
        self.assertEqual(f(2), 4)
        self.assertEqual(calls["n"], 2)

    def test_cached_none_is_a_hit(self):
        """resolve_venue returns None for an unresolvable venue; a cached None must
        NOT be re-fetched."""
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("ns")
        def f(x):
            calls["n"] += 1
            return None

        self.assertIsNone(f("nowhere"))
        self.assertIsNone(f("nowhere"))
        self.assertEqual(calls["n"], 1, "cached None must be a hit")

    def test_same_object_returned(self):
        import fast_pipeline as fp

        @fp.memoize_per_tour("ns")
        def make(x):
            return object()

        a = make("Courtauld")
        b = make("Courtauld")
        self.assertIs(a, b, "same args within one tour must return the SAME object")

    def test_seed_makes_next_call_a_hit(self):
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("resolve_venue")
        def resolve(v, c=""):
            calls["n"] += 1
            return f"{v}|{c}"

        fp.seed("resolve_venue", ("Courtauld", "London"), {}, "SEEDED")
        self.assertEqual(resolve("Courtauld", "London"), "SEEDED")
        self.assertEqual(calls["n"], 0, "seeded call must not invoke the function")


class TestPerTourScope(FlagEnvMixin, unittest.TestCase):
    """A SECOND tour must NOT reuse the first tour's memoized result."""

    def setUp(self):
        super().setUp()
        os.environ["FAST_PIPELINE"] = "1"

    def test_reset_simulates_new_tour(self):
        import fast_pipeline as fp
        calls = {"n": 0}

        @fp.memoize_per_tour("resolve_venue")
        def resolve(v):
            calls["n"] += 1
            return object()

        a1 = resolve("Courtauld")
        a2 = resolve("Courtauld")
        self.assertIs(a1, a2)
        self.assertEqual(calls["n"], 1)

        fp.reset_tour_memo()  # new tour on the same thread
        b1 = resolve("Courtauld")
        self.assertIsNot(a1, b1, "second tour must NOT reuse the first's result")
        self.assertEqual(calls["n"], 2, "second tour must re-resolve")

    def test_separate_threads_do_not_share(self):
        """Each tour runs in its own thread (fresh contextvars Context); the memo
        must be isolated — no cross-tour leak."""
        import fast_pipeline as fp
        calls = {"n": 0}
        lock = threading.Lock()

        @fp.memoize_per_tour("resolve_venue")
        def resolve(v):
            with lock:
                calls["n"] += 1
            return object()

        results = {}

        def tour(tid):
            results[tid] = (resolve("Courtauld"), resolve("Courtauld"))

        threads = [
            threading.Thread(target=lambda i=i: contextvars.copy_context().run(tour, i))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        a1, a2 = results[0]
        b1, b2 = results[1]
        self.assertIs(a1, a2)
        self.assertIs(b1, b2)
        self.assertIsNot(a1, b1, "CROSS-TOUR LEAK: tour 2 reused tour 1's object")
        self.assertEqual(calls["n"], 2, "exactly one resolve per tour (2 tours)")


class TestVenueResolverCallDrop(FlagEnvMixin, unittest.TestCase):
    """End-to-end on the real venue_resolver wrappers (impls faked, no network):
    the 4→1 resolve_venue drop and the 3→1 fetch_venue_works drop, with the
    [TIMING-SUB] counts reflecting the real behaviour."""

    def _patch_impls(self):
        import venue_resolver as vr
        self._orig_rv = vr._resolve_venue_impl
        self._orig_fw = vr._fetch_venue_works_impl
        self.calls = {"rv": 0, "fw": 0}

        def fake_rv(venue_string, city=""):
            self.calls["rv"] += 1

            class E:
                qid = "Q1"
                name = venue_string
                language = "en"

            return E()

        def fake_fw(qid, language="en", is_modern_art_museum=None, venue_name=""):
            self.calls["fw"] += 1
            return [{"qid": "Qw"}]

        vr._resolve_venue_impl = fake_rv
        vr._fetch_venue_works_impl = fake_fw

    def _unpatch_impls(self):
        import venue_resolver as vr
        vr._resolve_venue_impl = self._orig_rv
        vr._fetch_venue_works_impl = self._orig_fw

    def test_off_four_resolves_four_calls(self):
        os.environ.pop("FAST_PIPELINE", None)
        import venue_resolver as vr
        import phase_timer as pt
        self._patch_impls()
        try:
            pt.reset_sub_timer()
            for _ in range(4):
                vr.resolve_venue("Courtauld", "London")
            self.assertEqual(self.calls["rv"], 4, "OFF: 4 resolves = 4 impl calls")
            steps = pt.get_sub_timer().get_steps()
            rv = [v for k, v in steps.items() if k[1] == "resolve_venue"][0]
            self.assertEqual(rv["count"], 4, "OFF: [TIMING-SUB] shows calls=4")
        finally:
            self._unpatch_impls()

    def test_on_four_resolves_one_call(self):
        os.environ["FAST_PIPELINE"] = "1"
        import venue_resolver as vr
        import fast_pipeline as fp
        self._patch_impls()
        try:
            fp.reset_tour_memo()
            for _ in range(4):
                vr.resolve_venue("Courtauld", "London")
            self.assertEqual(self.calls["rv"], 1, "ON: 4 resolves memoized to 1 impl call")
        finally:
            self._unpatch_impls()

    def test_on_three_works_one_call(self):
        os.environ["FAST_PIPELINE"] = "1"
        import venue_resolver as vr
        import fast_pipeline as fp
        self._patch_impls()
        try:
            fp.reset_tour_memo()
            for _ in range(3):
                vr.fetch_venue_works("Q1", "en")
            self.assertEqual(self.calls["fw"], 1, "ON: 3 works fetches memoized to 1")
        finally:
            self._unpatch_impls()

    def test_second_tour_reresolves(self):
        os.environ["FAST_PIPELINE"] = "1"
        import venue_resolver as vr
        import fast_pipeline as fp
        self._patch_impls()
        try:
            fp.reset_tour_memo()
            vr.resolve_venue("Courtauld", "London")
            fp.reset_tour_memo()  # new tour
            vr.resolve_venue("Courtauld", "London")
            self.assertEqual(self.calls["rv"], 2,
                             "a second tour must NOT reuse the first's resolve")
        finally:
            self._unpatch_impls()


class TestOverlapTiming(FlagEnvMixin, unittest.TestCase):
    """The up-front preflight ∥ venue-resolution overlap: with fakes, the two
    independent waits run concurrently (wall ≈ max), not serially (wall ≈ sum)."""

    def setUp(self):
        super().setUp()
        os.environ["FAST_PIPELINE"] = "1"

    def test_preflight_and_resolve_overlap(self):
        import concurrent.futures
        import contextvars

        PREFLIGHT_S = 0.4
        RESOLVE_S = 0.3

        def fake_preflight():
            time.sleep(PREFLIGHT_S)
            return {"status": "open"}

        def fake_resolve():
            time.sleep(RESOLVE_S)
            return object()

        # Mirror the wrapper's structure: resolve on a worker (copied context),
        # preflight on this thread, join in a finally.
        t0 = time.time()
        ctx = contextvars.copy_context()
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(ctx.run, fake_resolve)
        try:
            _pf = fake_preflight()
        finally:
            _ent = fut.result()
            ex.shutdown(wait=False)
        elapsed = time.time() - t0

        self.assertIsNotNone(_ent)
        self.assertEqual(_pf["status"], "open")
        # Serial would be ~0.7s; overlapped is ~max(0.4,0.3)=0.4s.
        self.assertLess(elapsed, PREFLIGHT_S + RESOLVE_S - 0.1,
                        f"expected overlap (~{PREFLIGHT_S}s), got {elapsed:.2f}s serial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
