#!/usr/bin/env python3
"""test_local822_meter_mount_guard.py — CONTAINER METER-MOUNT CONTRACT (LOCAL-822).

LOCAL-820 wired the .sh wrappers and isolated_test.py so a container's meter rows
reach the HOST, but its guard test only SCANS source files — it cannot see a
hand-typed ``docker run`` (LOCAL-818 launched its live tours that way), so the
next hand-typed run can still lose its rows inside the ``--rm`` container. LOCAL-817
made the whole-task budget mechanical by having the meter itself refuse; this does
the same for the meterlog mount.

The ticket asks these be proven, with NO network, NO DB and NO real container:

  1. REFUSES WITHOUT THE MOUNT. Inside a container, when the directory of
     PAID_API_LOG is not a bind mount, the raw meter door
     (paid_api_meter.check_meter_mount) raises MeterMountMissing and the refusal
     names ``meter_container_env.docker_meter_args``.
  2. REFUSES WITHOUT IDENTITY. Inside a container WITH the mount but with no
     METER_SERVICE / TASK_BUDGET_ID / METER_ROLE, it still refuses.
  3. PASSES WITH THE CONTRACT. Inside a container with the mount AND an identity,
     it allows.
  4. SHARED-STACK SERVICE ENV PASSES. The compose services mount /meterlogs and
     set METER_ROLE=listener (no METER_SERVICE) — that env must be allowed, so the
     shared stack is unaffected.
  5. HOST IS UNAFFECTED. With no /.dockerenv the guard never applies.
  6. ESCAPE HATCH. METER_MOUNT_GUARD=0 disables the guard for a deliberate
     no-mount diagnostic.
  7. END-TO-END THROUGH THE PATCHED CLIENT. A fake paid request routed through the
     meter's patched requests.Session.send is refused BEFORE it reaches the
     network when the mount is missing.
  8. HARNESS ENTRY. tests/live_run_meter.LiveRunMeter.__enter__ refuses (container,
     no mount) and passes (container, mount+identity) via the same door.
  9. FAIL-OPEN. A detection error allows the call (a guard bug must never block a
     tour).

Run: python3 -m pytest tests/test_local822_meter_mount_guard.py -q
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_METER = os.path.join(_ROOT, "_meter")
for _p in (_HERE, _ROOT, _METER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import paid_api_meter  # noqa: E402
import live_run_meter as lrm  # noqa: E402


# Env vars the guard reads; cleared around every test so the host environment
# cannot make a test pass or fail by accident.
_GUARD_ENVS = ("METER_SERVICE", "TASK_BUDGET_ID", "METER_ROLE",
               "METER_MOUNT_GUARD", "PAID_API_LOG",
               # LiveRunMeter construction also consults these; keep them clear so
               # __enter__ tests exercise only the mount guard.
               "TASK_BUDGET_USD", "AUDIOURA_TASK_BUDGET_DIR", "TEST_GEMINI_MAX_USD")


class _GuardTestBase(unittest.TestCase):
    """Clean env + restores the guard's two decision helpers (_in_container and
    _dir_is_bind_mount) after each test, so tests drive 'in a container' and
    'the dir is/ isn't a bind mount' WITHOUT a real container or mount."""

    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in _GUARD_ENVS}
        for k in _GUARD_ENVS:
            os.environ.pop(k, None)
        self._orig_in_container = paid_api_meter._in_container
        self._orig_dir_is_bind_mount = paid_api_meter._dir_is_bind_mount

    def tearDown(self):
        paid_api_meter._in_container = self._orig_in_container
        paid_api_meter._dir_is_bind_mount = self._orig_dir_is_bind_mount
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ── fixtures that fake the container / mount state ────────────────────────
    def _fake_container(self, inside):
        paid_api_meter._in_container = lambda: inside

    def _fake_mount(self, mounted):
        paid_api_meter._dir_is_bind_mount = lambda path: mounted

    def _set_identity_service(self, task="LOCAL-822"):
        os.environ["METER_SERVICE"] = task

    def _set_shared_stack_env(self):
        """The compose services' env: the meterlogs bind-mount is present and
        METER_ROLE=listener is set, but NO METER_SERVICE. (The mount itself is
        faked separately with _fake_mount.)"""
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        os.environ["METER_ROLE"] = "listener"


# ─── 1 & 2. Refuses without the mount / without identity ──────────────────────
class TestRefuses(_GuardTestBase):
    def test_refuses_in_container_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._set_identity_service()           # identity present; mount is missing
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        with self.assertRaises(paid_api_meter.MeterMountMissing) as ctx:
            paid_api_meter.check_meter_mount()
        # The refusal must name the ONE helper that builds a correct run.
        self.assertIn("meter_container_env.docker_meter_args", str(ctx.exception))

    def test_refuses_in_container_with_mount_but_no_identity(self):
        self._fake_container(True)
        self._fake_mount(True)                 # mount present; identity missing
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        with self.assertRaises(paid_api_meter.MeterMountMissing):
            paid_api_meter.check_meter_mount()

    def test_refusal_message_names_both_missing_pieces(self):
        self._fake_container(True)
        self._fake_mount(False)                # neither mount nor identity
        with self.assertRaises(paid_api_meter.MeterMountMissing) as ctx:
            paid_api_meter.check_meter_mount()
        msg = str(ctx.exception)
        self.assertIn("bind-mount", msg)
        self.assertIn("identity", msg)


# ─── 3. Passes with the contract ──────────────────────────────────────────────
class TestPasses(_GuardTestBase):
    def test_passes_with_mount_and_service(self):
        self._fake_container(True)
        self._fake_mount(True)
        self._set_identity_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_passes_with_mount_and_task_budget_id(self):
        self._fake_container(True)
        self._fake_mount(True)
        os.environ["TASK_BUDGET_ID"] = "LOCAL-822"   # identity via the budget id
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 4. Shared-stack service env passes (the stack is unaffected) ─────────────
class TestSharedStackUnaffected(_GuardTestBase):
    def test_shared_stack_listener_env_with_mount_passes(self):
        # Exactly what docker-compose.subscribed-local.yml gives a service:
        # /meterlogs bind-mount present, METER_ROLE=listener, no METER_SERVICE.
        self._fake_container(True)
        self._fake_mount(True)
        self._set_shared_stack_env()
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_shared_stack_has_container_identity_via_role(self):
        # The identity half alone must accept METER_ROLE (the stack's identity).
        os.environ["METER_ROLE"] = "listener"
        self.assertTrue(paid_api_meter._has_container_identity())


# ─── 5. Host is unaffected ────────────────────────────────────────────────────
class TestHostUnaffected(_GuardTestBase):
    def test_not_in_container_always_allows(self):
        self._fake_container(False)
        self._fake_mount(False)                # no mount, no identity — still OK
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 6. Escape hatch ──────────────────────────────────────────────────────────
class TestEscapeHatch(_GuardTestBase):
    def test_guard_off_allows_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        os.environ["METER_MOUNT_GUARD"] = "0"
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_guard_on_by_default(self):
        self.assertTrue(paid_api_meter._mount_guard_on())
        os.environ["METER_MOUNT_GUARD"] = "false"
        self.assertFalse(paid_api_meter._mount_guard_on())


# ─── 7. End-to-end through the patched requests.Session.send ──────────────────
class TestEndToEndPatchedClient(_GuardTestBase):
    """A fake paid request through the meter's patched send() is refused BEFORE
    the original send runs when the container has no mount — proving the guard is
    on the real paid path, not just a standalone function."""

    def test_patched_send_refuses_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._set_identity_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"

        paid_api_meter.install()
        import requests

        wrapper_send = requests.Session.send
        req = requests.Request(
            "POST", "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o-mini"}).prepare()
        sess = requests.Session()
        # The guard runs before _orig, so a raise proves the call never reached
        # the network.
        with self.assertRaises(paid_api_meter.MeterMountMissing):
            wrapper_send(sess, req)

    def test_patched_send_allows_with_contract(self):
        # With the mount + identity the guard does NOT raise; we stop the call
        # from actually going out by faking the host check off AFTER the guard —
        # instead, assert the guard itself returns None for this env (the send
        # wrapper would then proceed to the real network, which we do not do).
        self._fake_container(True)
        self._fake_mount(True)
        self._set_identity_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 8. Harness entry (LiveRunMeter.__enter__) ────────────────────────────────
class TestHarnessEntry(_GuardTestBase):
    def test_enter_refuses_in_container_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._set_identity_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        # install_cap=False so construction does not touch story_leads/budget.
        m = lrm.LiveRunMeter("LOCAL-822", install_cap=False)
        with self.assertRaises(paid_api_meter.MeterMountMissing):
            with m:
                pass

    def test_enter_passes_with_contract(self):
        self._fake_container(True)
        self._fake_mount(True)
        self._set_identity_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        m = lrm.LiveRunMeter("LOCAL-822", install_cap=False)
        with m as entered:
            self.assertIs(entered, m)

    def test_enter_on_host_passes(self):
        self._fake_container(False)
        self._fake_mount(False)
        m = lrm.LiveRunMeter("LOCAL-822", install_cap=False)
        with m as entered:
            self.assertIs(entered, m)


# ─── 9. Fail-open on a detection error ────────────────────────────────────────
class TestFailOpen(_GuardTestBase):
    def test_detection_error_allows(self):
        # _in_container blowing up must NOT block the call (a guard bug can't wedge
        # a tour). check_meter_mount swallows it and returns None.
        def _boom():
            raise RuntimeError("boom")
        paid_api_meter._in_container = _boom
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── bind-mount detector smoke (uses the REAL helper, no container needed) ────
class TestBindMountDetector(_GuardTestBase):
    def test_root_is_a_mount(self):
        # "/" is always a mount point on any POSIX host — a cheap, real check that
        # os.path.ismount path of the detector works. (We pass a file under "/" so
        # the detector takes its dirname.)
        self.assertTrue(paid_api_meter._dir_is_bind_mount("/paid_api_calls.jsonl"))

    def test_plainly_unmounted_dir_is_not_a_mount(self):
        # A nested path under the repo is not a mount point.
        self.assertFalse(
            paid_api_meter._dir_is_bind_mount(
                os.path.join(_ROOT, "tests", "paid_api_calls.jsonl")))

    def test_empty_path_is_not_a_mount(self):
        self.assertFalse(paid_api_meter._dir_is_bind_mount(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
