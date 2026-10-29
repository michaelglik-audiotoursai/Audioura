#!/usr/bin/env python3
"""test_local814_gemini_breaker.py — LOCAL-814.

Fully OFFLINE (no network, no DB; the Gemini HTTP POST is monkeypatched to a fake
response object). Proves:

  A. gemini_breaker
     1. a 402 trips it for ~30 min; a 429 for ~2 min; a 200 never trips it.
     2. is_open() is True while open and False after reset / expiry.
     3. a trip logs EXACTLY ONCE and records EXACTLY ONE failure_events row
        (re-confirming an already-open breaker is silent).
     4. the recorded row classifies as external/credit (failure_triage: budget
        for 402, external for 429).
     5. GEMINI_BREAKER_DISABLE=1 makes it a no-op.
     6. status_from_error extracts 402/429 from a requests-style exception.

  B. story_leads wiring
     7. a mocked 402 from gemini_with_sources trips the breaker; the NEXT call to
        _gemini and gemini_with_sources SKIPS the HTTP post (fallback), issuing
        zero further Gemini requests.

  C. leads path honours RESEARCH_BACKEND=serper
     8. available_providers() drops gemini on the serper arm (openai only).
     9. run() issues ZERO Gemini provider calls on the serper arm, even when an
        explicit providers=[...] list names gemini (asserted via a metered mock
        that counts PROVIDERS invocations).
    10. an open breaker likewise drops gemini from the leads path.
    11. default (gemini) arm with a closed breaker is unchanged (gemini offered
        and called).
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tests" else HERE
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import gemini_breaker as gb          # noqa: E402
import story_leads as sl             # noqa: E402
import failure_triage as ft          # noqa: E402


class _FakeResp:
    """Minimal stand-in for a requests.Response."""
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        }
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            err = requests.exceptions.HTTPError(f"{self.status_code} Error")
            err.response = self
            raise err


def _clean_breaker_env():
    for k in ("GEMINI_BREAKER_DISABLE", "GEMINI_BREAKER_402_MINUTES",
              "GEMINI_BREAKER_429_MINUTES", "DATABASE_URL", "DB_HOST", "DB_NAME"):
        os.environ.pop(k, None)


# ── A. breaker ────────────────────────────────────────────────────────────────
class BreakerCore(unittest.TestCase):
    def setUp(self):
        _clean_breaker_env()
        gb.reset()

    def tearDown(self):
        gb.reset()
        _clean_breaker_env()

    def test_402_trips_long_window(self):
        self.assertFalse(gb.is_open())
        gb.note_response(402, "prepayment credits are depleted")
        self.assertTrue(gb.is_open())
        st = gb.state()
        self.assertEqual(st["status"], 402)
        self.assertEqual(st["reason"], "credit depleted")
        # ~30 minutes.
        self.assertGreater(st["seconds_left"], 29 * 60)
        self.assertLessEqual(st["seconds_left"], 30 * 60 + 1)

    def test_429_trips_short_window(self):
        gb.note_response(429, "rate limit exceeded")
        self.assertTrue(gb.is_open())
        st = gb.state()
        self.assertEqual(st["reason"], "rate limited")
        self.assertGreater(st["seconds_left"], 60)
        self.assertLessEqual(st["seconds_left"], 2 * 60 + 1)

    def test_200_never_trips(self):
        gb.note_response(200, "ok")
        self.assertFalse(gb.is_open())

    def test_reset_closes(self):
        gb.note_response(402, "x")
        self.assertTrue(gb.is_open())
        gb.reset()
        self.assertFalse(gb.is_open())

    def test_expiry_closes(self):
        os.environ["GEMINI_BREAKER_402_MINUTES"] = "0.0001"  # ~6 ms
        import importlib
        importlib.reload(gb)
        gb.reset()
        gb.note_response(402, "x")
        self.assertTrue(gb.is_open())
        time.sleep(0.05)
        self.assertFalse(gb.is_open())
        # Restore defaults for later tests.
        os.environ.pop("GEMINI_BREAKER_402_MINUTES", None)
        importlib.reload(gb)

    def test_disable_flag_is_noop(self):
        os.environ["GEMINI_BREAKER_DISABLE"] = "1"
        gb.note_response(402, "x")
        self.assertFalse(gb.is_open())

    def test_status_from_error(self):
        import requests
        e = requests.exceptions.HTTPError("402 Client Error")
        e.response = _FakeResp(status_code=402)
        self.assertEqual(gb.status_from_error(e), 402)
        e2 = requests.exceptions.HTTPError("429 Too Many Requests")
        e2.response = _FakeResp(status_code=429)
        self.assertEqual(gb.status_from_error(e2), 429)
        self.assertEqual(gb.status_from_error(ValueError("nothing http here")), 0)


class BreakerLogsAndRecordsOnce(unittest.TestCase):
    """A trip logs once and records one failure_events row; re-confirming is
    silent. We capture the log line (stdout) and the failure_log.record call."""

    def setUp(self):
        _clean_breaker_env()
        gb.reset()
        self._rec_calls = []

        import failure_log
        self._orig_record = failure_log.record

        def _fake_record(**kw):
            self._rec_calls.append(kw)
            return "sig"
        failure_log.record = _fake_record
        self._failure_log = failure_log

    def tearDown(self):
        self._failure_log.record = self._orig_record
        gb.reset()
        _clean_breaker_env()

    def test_trip_records_once(self):
        gb.note_response(402, "prepayment credits are depleted")
        gb.note_response(402, "prepayment credits are depleted")  # still open
        gb.note_response(402, "prepayment credits are depleted")
        self.assertEqual(len(self._rec_calls), 1,
                         "exactly one failure_events row per trip edge")
        kw = self._rec_calls[0]
        self.assertEqual(kw["http_status"], 402)
        self.assertEqual(kw["service"], "generator")
        self.assertEqual(kw["surface"], "gemini")

    def test_recorded_row_is_external_credit(self):
        gb.note_response(402, "prepayment credits are depleted")
        kw = self._rec_calls[0]
        ev = dict(source="failure_events", service=kw["service"],
                  surface=kw.get("surface"), error_code=kw.get("error_code"),
                  exception_type=kw.get("exception_type"),
                  message=kw.get("message"), http_status=kw.get("http_status"),
                  triage="external", triage_source="auto")
        # external/credit == the `budget` class (credit sub-owner of external).
        self.assertEqual(ft.classify_event(ev), "budget")

    def test_429_recorded_row_is_external(self):
        gb.note_response(429, "rate limited")
        kw = self._rec_calls[0]
        ev = dict(source="failure_events", service=kw["service"],
                  surface=kw.get("surface"), error_code=kw.get("error_code"),
                  exception_type=kw.get("exception_type"),
                  message=kw.get("message"), http_status=kw.get("http_status"),
                  triage="external", triage_source="auto")
        self.assertEqual(ft.classify_event(ev), "external")


# ── B. story_leads wiring ──────────────────────────────────────────────────────
class StoryLeadsBreakerWiring(unittest.TestCase):
    """A 402 from the Gemini HTTP site trips the breaker; the next calls skip."""

    def setUp(self):
        _clean_breaker_env()
        gb.reset()
        os.environ["GEMINI_API_KEY"] = "fake-key"
        os.environ.pop("RESEARCH_BACKEND", None)
        self.post_calls = []

        import requests
        self._orig_post = requests.post

        def _fake_post(url, **kw):
            self.post_calls.append(url)
            # First call: a 402 (credit depleted). This simulates the live key.
            return _FakeResp(status_code=402,
                             text="prepayment credits are depleted")
        requests.post = _fake_post
        self._requests = requests

    def tearDown(self):
        self._requests.post = self._orig_post
        gb.reset()
        os.environ.pop("GEMINI_API_KEY", None)
        _clean_breaker_env()

    def test_402_trips_then_callers_skip(self):
        # First grounded gemini_with_sources call hits the (fake) 402 and trips.
        out = sl.gemini_with_sources("q", grounded=True, resolve=False)
        self.assertTrue(out["error"])
        self.assertEqual(len(self.post_calls), 1, "one real POST issued (the 402)")
        self.assertTrue(gb.is_open(), "402 must trip the breaker")

        # Subsequent calls must SKIP the HTTP post entirely.
        before = len(self.post_calls)
        out2 = sl.gemini_with_sources("q2", grounded=True, resolve=False)
        self.assertEqual(out2["text"], "")
        self.assertIn("breaker open", out2["error"])
        txt = sl._gemini("q3", grounded=False)
        self.assertEqual(txt, "")
        self.assertEqual(len(self.post_calls), before,
                         "no further Gemini POSTs once the breaker is open")


# ── C. leads path honours RESEARCH_BACKEND=serper ──────────────────────────────
class LeadsPathSerperRouting(unittest.TestCase):
    """The LEAD fan-out must issue ZERO Gemini provider calls on the serper arm."""

    def setUp(self):
        _clean_breaker_env()
        gb.reset()
        os.environ["OPENAI_API_KEY"] = "fake-openai"
        os.environ["GEMINI_API_KEY"] = "fake-gemini"
        os.environ.pop("RESEARCH_BACKEND", None)
        os.environ.pop("CHEAP_ARM_CATEGORIES", None)

        # Count provider invocations via a metered mock of PROVIDERS.
        self.calls = {"openai": 0, "gemini": 0, "gemini_grounded": 0}
        self._orig_providers = dict(sl.PROVIDERS)

        def _mk(name, text):
            def _fn(prompt, *a, **kw):
                self.calls[name] += 1
                return text
            return _fn
        sl.PROVIDERS = {
            "openai": _mk("openai", "1999 | openai said a thing happened"),
            "gemini": _mk("gemini", "1999 | gemini said a thing happened"),
            "gemini_grounded": _mk("gemini_grounded", "2000 | grounded thing"),
        }
        # verify() hits the network (serp); stub it so the test is offline.
        self._orig_verify = sl.verify
        sl.verify = lambda lead, work, subject: {**lead, "status": "UNVERIFIED",
                                                 "results": 0}

    def tearDown(self):
        sl.PROVIDERS = self._orig_providers
        sl.verify = self._orig_verify
        gb.reset()
        for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "RESEARCH_BACKEND",
                  "CHEAP_ARM_CATEGORIES"):
            os.environ.pop(k, None)

    def test_available_providers_default_keeps_gemini(self):
        os.environ.pop("RESEARCH_BACKEND", None)
        self.assertIn("gemini", sl.available_providers())

    def test_available_providers_serper_drops_gemini(self):
        os.environ["RESEARCH_BACKEND"] = "serper"
        self.assertEqual(sl.available_providers(), ["openai"])

    def test_run_serper_issues_zero_gemini_calls(self):
        os.environ["RESEARCH_BACKEND"] = "serper"
        # Even with an explicit list that names gemini, the serper arm drops it.
        r = sl.run("Joan Miró", "Le Lézard", "MFA Boston",
                   providers=["openai", "gemini", "gemini_grounded"],
                   verify_top=0)
        self.assertEqual(self.calls["gemini"], 0)
        self.assertEqual(self.calls["gemini_grounded"], 0)
        self.assertEqual(self.calls["openai"], 1)
        self.assertNotIn("gemini", r["providers"])

    def test_run_default_calls_gemini(self):
        os.environ.pop("RESEARCH_BACKEND", None)
        sl.run("Joan Miró", "Le Lézard", "MFA Boston",
               providers=["openai", "gemini"], verify_top=0)
        self.assertEqual(self.calls["gemini"], 1)
        self.assertEqual(self.calls["openai"], 1)

    def test_open_breaker_drops_gemini_from_leads(self):
        os.environ.pop("RESEARCH_BACKEND", None)
        gb.note_response(402, "prepayment credits are depleted")
        self.assertTrue(gb.is_open())
        self.assertEqual(sl.available_providers(), ["openai"])
        sl.run("Joan Miró", "Le Lézard", "MFA Boston",
               providers=["openai", "gemini"], verify_top=0)
        self.assertEqual(self.calls["gemini"], 0)
        self.assertEqual(self.calls["openai"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
