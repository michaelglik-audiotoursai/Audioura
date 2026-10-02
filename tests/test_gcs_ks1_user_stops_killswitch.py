#!/usr/bin/env python3
"""GCS-KS1 — the user-chosen-stops kill switch (D591).

These tests fail if the switch is removed or weakened (D242). They exercise the
real gate at all three server entry points plus the pure helper, and one grep-based
test asserts no other server path reads the incoming stops field unguarded.

No paid calls, no network, no DB: the helper is pure, and the entry-point tests
stub the generation thread and quota/DB so only the switch logic runs.
"""
import os
import re
import sys
import json
import importlib
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stops_flag as usf

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMED = ["Bell Tower", "Rose Window", "Crypt"]


class _FlagEnv:
    """Context manager: set/clear USER_STOPS_ENABLED and restore afterwards."""

    def __init__(self, value):
        self.value = value
        self._had = None
        self._prev = None

    def __enter__(self):
        self._had = usf.ENV_VAR in os.environ
        self._prev = os.environ.get(usf.ENV_VAR)
        if self.value is None:
            os.environ.pop(usf.ENV_VAR, None)
        else:
            os.environ[usf.ENV_VAR] = self.value
        return self

    def __exit__(self, *exc):
        if self._had:
            os.environ[usf.ENV_VAR] = self._prev
        else:
            os.environ.pop(usf.ENV_VAR, None)


class TestFlagHelper(unittest.TestCase):
    """The pure gate: default OFF, only 'true' turns it on, ignore-path logs once."""

    def test_default_is_off_when_unset(self):
        with _FlagEnv(None):
            self.assertFalse(usf.user_stops_enabled())

    def test_only_true_enables(self):
        for val, expected in [("true", True), ("TRUE", True), ("True", True),
                              ("false", False), ("1", False), ("yes", False),
                              ("", False), ("  true  ", True)]:
            with _FlagEnv(val):
                self.assertEqual(usf.user_stops_enabled(), expected, f"value={val!r}")

    def test_off_neutralizes_and_logs_once_with_count(self):
        lines = []
        with _FlagEnv("false"):
            out = usf.neutralize_if_disabled(
                NAMED, request_id="req-1", field="user_stops", log=lines.append)
        self.assertIsNone(out, "OFF must drop the stops entirely")
        self.assertEqual(len(lines), 1, "exactly one log line when OFF and present")
        self.assertIn("USER_STOPS_DISABLED", lines[0])
        self.assertIn("count=3", lines[0])
        self.assertIn("user_stops", lines[0])

    def test_off_but_absent_field_is_silent(self):
        lines = []
        with _FlagEnv("false"):
            self.assertIsNone(usf.neutralize_if_disabled(None, log=lines.append))
            self.assertIsNone(usf.neutralize_if_disabled([], log=lines.append))
        self.assertEqual(lines, [], "no log line when there was nothing to ignore")

    def test_on_passes_through_unchanged_and_silent(self):
        lines = []
        with _FlagEnv("true"):
            out = usf.neutralize_if_disabled(NAMED, log=lines.append)
        self.assertEqual(out, NAMED)
        self.assertEqual(lines, [], "no ignore line when the feature is ON")


def _load_orchestrator(flag_value):
    """Import a fresh orchestrator with the flag set and paid deps stubbed."""
    if flag_value is None:
        os.environ.pop(usf.ENV_VAR, None)
    else:
        os.environ[usf.ENV_VAR] = flag_value

    import tour_orchestrator_service as orch
    importlib.reload(orch)

    orch.check_tour_quota = lambda uid, stops=10: {
        "allowed": True, "clamped_stops": stops, "used": 0, "remaining": 100}
    import entitlements
    entitlements.check_tour_quota = orch.check_tour_quota
    orch.track_user_tour = lambda *a, **k: None
    orch.log_job_update = lambda *a, **k: None
    try:
        import psycopg2
        psycopg2.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no DB in test"))
    except Exception:
        pass
    return orch


class TestOrchestratorEntryPoint(unittest.TestCase):
    """The /generate-complete-tour boundary: the field the mobile app sends."""

    def _run(self, flag_value):
        orch = _load_orchestrator(flag_value)
        captured = {"stops": "<<uncalled>>"}

        def _thread(job_id, location, tour_type, total_stops, user_id=None,
                    request_string=None, language='en', persona=None,
                    is_test=None, stops=None):
            captured["stops"] = stops
        orch.orchestrate_tour_async = _thread

        orch.app.testing = True
        client = orch.app.test_client()
        payload = {
            "location": "Old North Church, Boston", "tour_type": "",
            "user_id": "tester", "request_string": "a tour",
            "user_stops": NAMED,
        }
        resp = client.post("/generate-complete-tour", data=json.dumps(payload),
                           content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return captured["stops"]

    def test_flag_off_by_default_ignores_user_stops(self):
        # This is the assertion that FAILS if the switch is removed: with the flag
        # unset, the app-sent user_stops must NOT reach generation.
        self.assertIsNone(self._run(None),
                          "with the switch removed, user_stops would reach generation")

    def test_flag_off_explicit_ignores_user_stops(self):
        self.assertIsNone(self._run("false"))

    def test_flag_on_honours_user_stops(self):
        self.assertEqual(self._run("true"), NAMED)


class TestGeneratorEntryPoint(unittest.TestCase):
    """The generator /generate boundary: stops -> forced_stops -> engine."""

    def _run(self, flag_value):
        if flag_value is None:
            os.environ.pop(usf.ENV_VAR, None)
        else:
            os.environ[usf.ENV_VAR] = flag_value
        import generate_tour_text_service as gen
        importlib.reload(gen)

        captured = {"forced_stops": "<<uncalled>>"}
        real_thread = gen.threading.Thread

        class _StubThread:
            def __init__(self, target=None, args=(), **kw):
                # args = (job_id, location, tour_type, total_stops, user_id, forced_stops)
                captured["forced_stops"] = args[5] if len(args) > 5 else None

            def start(self):
                pass

            @property
            def daemon(self):
                return True

            @daemon.setter
            def daemon(self, v):
                pass
        gen.threading.Thread = _StubThread
        try:
            gen.app.testing = True
            client = gen.app.test_client()
            payload = {"location": "Old North Church", "tour_type": "",
                       "user_id": "tester", "stops": NAMED}
            resp = client.post("/generate", data=json.dumps(payload),
                               content_type="application/json")
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        finally:
            gen.threading.Thread = real_thread
        return captured["forced_stops"]

    def test_flag_off_ignores_stops(self):
        self.assertIsNone(self._run(None))

    def test_flag_on_honours_stops(self):
        self.assertEqual(self._run("true"), NAMED)


class TestNoUnguardedReader(unittest.TestCase):
    """AC#4 — grep-based: every server-side read of the incoming stops field must
    pass through the kill switch. If a new code path reads data.get('user_stops')
    or data.get('stops') on a request without neutralizing, this fails.
    """

    # The three services that accept the field over HTTP. Their reads must be
    # gated. (Library modules that receive an already-vetted list as a function
    # argument — user_stops_validate, stop_route_sequencer, generate_tour_text —
    # never read the request field themselves and are out of scope.)
    SERVICE_FILES = [
        "tour_orchestrator_service.py",
        "generate_tour_text_service.py",
        "tour_worker_service.py",
    ]

    READ_RE = re.compile(r"""data\.get\(\s*['"](?:user_stops|stops)['"]\s*\)""")

    def test_every_request_field_read_is_guarded(self):
        offenders = []
        for fname in self.SERVICE_FILES:
            path = os.path.join(REPO_ROOT, fname)
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not self.READ_RE.search(line):
                    continue
                # 1) Comments are not code paths.
                if stripped.startswith("#"):
                    continue
                # 2) Diagnostic-only reads: the raw value copied into a log/dict
                #    under an explicit *_raw key is never fed to generation.
                if "_raw" in line:
                    continue
                # 3) Guarded if the read is the direct argument to the neutralizer,
                #    OR if the variable it is assigned to is neutralized within the
                #    next few lines (the orchestrator reads into _raw_stops first,
                #    then neutralizes it before validate_stops).
                window = "".join(lines[max(0, i - 1): i + 6])
                if ("_neutralize_user_stops(" in window
                        or "neutralize_if_disabled(" in window):
                    continue
                offenders.append(f"{fname}:{i + 1}: {stripped}")
        self.assertEqual(
            offenders, [],
            "unguarded read(s) of the incoming stops field:\n" + "\n".join(offenders))

    def test_each_service_imports_the_switch(self):
        for fname in self.SERVICE_FILES:
            path = os.path.join(REPO_ROOT, fname)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            self.assertIn("from user_stops_flag import", src,
                          f"{fname} does not import the kill switch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
