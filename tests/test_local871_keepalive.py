"""test_local871_keepalive.py — LOCAL-871. No DB, no HTTP, no spend."""
import os
import sys
import threading
import time
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import requests  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402


def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class KeepaliveTests(unittest.TestCase):
    def setUp(self):
        orch._ACTIVE_RUNS.clear()
        self.pings = []
        self.env = mock.patch.dict(os.environ, {"K_SERVICE": "orch", "SELF_URL": "https://orch.example"})
        self.env.start()
        self.p1 = mock.patch.object(orch, "_keepalive_sleep", lambda s: time.sleep(0.02))
        self.p2 = mock.patch.object(orch, "_keepalive_ping", lambda: self.pings.append(1) or 200)
        self.p1.start(); self.p2.start()

    def tearDown(self):
        orch._ACTIVE_RUNS.clear()
        _wait(lambda: orch._KEEPALIVE_THREAD is None)
        self.p1.stop(); self.p2.stop(); self.env.stop()

    def test_interval_default_is_45(self):
        self.assertEqual(orch.KEEPALIVE_INTERVAL_SECONDS, 45)

    def test_sleep_uses_interval(self):
        seen = []
        self.p1.stop()
        with mock.patch.object(orch, "_keepalive_sleep", lambda s: (seen.append(s), time.sleep(0.02))):
            orch._job_run_started("j1")
            _wait(lambda: seen)
            orch._job_run_finished("j1")
        self.p1.start()
        self.assertEqual(seen[0], orch.KEEPALIVE_INTERVAL_SECONDS)

    def test_starts_and_stops_with_jobs(self):
        orch._job_run_started("j1")
        self.assertTrue(_wait(lambda: len(self.pings) >= 2))
        orch._job_run_finished("j1")
        self.assertTrue(_wait(lambda: orch._KEEPALIVE_THREAD is None))
        n = len(self.pings)
        time.sleep(0.15)
        self.assertEqual(len(self.pings), n)

    def test_stays_while_any_job_active(self):
        orch._job_run_started("a"); orch._job_run_started("b")
        orch._job_run_finished("a")
        n = len(self.pings)
        self.assertTrue(_wait(lambda: len(self.pings) > n))
        orch._job_run_finished("b")

    def test_no_keepalive_without_k_service(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("K_SERVICE", None)
            orch._job_run_started("j1")
            time.sleep(0.1)
            self.assertIsNone(orch._KEEPALIVE_THREAD)
            self.assertEqual(self.pings, [])
            orch._job_run_finished("j1")

    def test_no_keepalive_without_self_url(self):
        os.environ.pop("SELF_URL", None)
        orch._job_run_started("j1")
        time.sleep(0.1)
        self.assertIsNone(orch._KEEPALIVE_THREAD)
        orch._job_run_finished("j1")

    def test_log_line(self):
        with mock.patch("builtins.print") as pr:
            orch._job_run_started("j1")
            _wait(lambda: self.pings)
            orch._job_run_finished("j1")
        self.assertTrue(any("[LOCAL-871] keepalive 1 jobs" in str(c.args[0]) for c in pr.call_args_list if c.args))

    def test_ping_hits_self_health_and_never_raises(self):
        self.p2.stop()
        with mock.patch.object(orch, "_authenticated_request", side_effect=requests.ConnectionError("x")) as m:
            self.assertIsNone(orch._keepalive_ping())
        with mock.patch.object(orch, "_authenticated_request") as m:
            m.return_value.status_code = 200
            orch._keepalive_ping()
            self.assertEqual(m.call_args.args[1], "https://orch.example/health?keepalive=1")
        self.p2.start()

    def test_wrapper_registers_and_unregisters(self):
        seen = {}
        def impl(job_id, *a, **k):
            seen["active"] = job_id in orch._ACTIVE_RUNS
        with mock.patch.object(orch, "_orchestrate_tour_async_impl", impl):
            orch.orchestrate_tour_async("jw", "x", "walking", 3)
        self.assertTrue(seen["active"])
        self.assertNotIn("jw", orch._ACTIVE_RUNS)

    def test_wrapper_unregisters_on_exception(self):
        with mock.patch.object(orch, "_orchestrate_tour_async_impl", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                orch.orchestrate_tour_async("jx", "x", "walking", 3)
        self.assertNotIn("jx", orch._ACTIVE_RUNS)

    def test_health_keepalive_is_cheap(self):
        c = orch.app.test_client()
        r = c.get("/health?keepalive=1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["keepalive"])


class SigtermTests(unittest.TestCase):
    def setUp(self):
        orch._ACTIVE_RUNS.clear()
        orch.ACTIVE_JOBS["js"] = {"text_job_id": "gen-1"}

    def tearDown(self):
        orch._ACTIVE_RUNS.clear(); orch.ACTIVE_JOBS.pop("js", None)
        orch._SHUTTING_DOWN = False

    def test_sigterm_logs_checkpoints_and_releases(self):
        store = mock.Mock()
        orch._ACTIVE_RUNS["js"] = "owner-1"
        with mock.patch.object(orch, "_orch_jobs_store", return_value=store), \
             mock.patch.object(orch, "_ACTIVE_GENERATION_THREADS", []), \
             mock.patch("builtins.print") as pr:
            with self.assertRaises(SystemExit):
                orch._graceful_shutdown(15, None)
        out = " ".join(str(c.args[0]) for c in pr.call_args_list if c.args)
        self.assertIn("[LOCAL-871] SIGTERM with 1 active jobs", out)
        store.set_generator_job_id.assert_called_once_with("js", "gen-1")
        store.release_lease.assert_called_once_with("js", owner="owner-1")

    def test_sigterm_without_jobs_no_log(self):
        with mock.patch.object(orch, "_ACTIVE_GENERATION_THREADS", []), mock.patch("builtins.print") as pr:
            with self.assertRaises(SystemExit):
                orch._graceful_shutdown(15, None)
        self.assertNotIn("SIGTERM with", " ".join(str(c.args[0]) for c in pr.call_args_list if c.args))


class PollerResilienceTests(unittest.TestCase):
    """The generator poll loop must survive transport errors and 5xx, and poll
    at <= 45 s for the job's whole life."""

    def _run(self, responses):
        calls = []
        it = iter(responses)
        def fake(method, url, **kw):
            calls.append(url)
            r = next(it)
            if isinstance(r, Exception):
                raise r
            m = mock.Mock(); m.status_code = r[0]; m.text = "t"; m.json.return_value = r[1]
            return m
        done = {"status": "completed", "output_file": "f", "tour_content": None, "coordinates": [1, 2]}
        sleeps = []
        orch.ACTIVE_JOBS.pop("jp", None)
        with mock.patch.object(orch, "_authenticated_request", fake), \
             mock.patch.object(orch.time, "sleep", lambda s: sleeps.append(s)), \
             mock.patch.object(orch, "_orch_jobs_store", return_value=None), \
             mock.patch.object(orch, "_tour_already_stored_for_job", return_value=False), \
             mock.patch.object(orch, "log_job_update"):
            try:
                orch._orchestrate_tour_async_impl("jp", "x", "walking", 3, resume_generator_job_id="g1")
            except Exception:
                pass
        return calls, sleeps

    def test_survives_errors_and_5xx_then_completes(self):
        done = {"status": "completed", "output_file": "f", "coordinates": [1, 2]}
        calls, sleeps = self._run([
            requests.ReadTimeout("t"), requests.exceptions.ChunkedEncodingError("c"),
            (503, {}), (200, {"status": "processing", "progress": "PHASE 5"}), (200, done),
            RuntimeError("stop-after-completion"),
        ])
        gen = [c for c in calls if "/status/g1" in c]
        self.assertEqual(len(gen), 5)            # all 5 polls happened; poller never died
        self.assertTrue(sleeps)
        self.assertLessEqual(max(sleeps[:4]), 45)  # poll cadence + 30 s timeout stays <= 45 s gap


if __name__ == "__main__":
    unittest.main()
