#!/usr/bin/env python3
"""test_local822_meter_mount_guard.py — CONTAINER METER-MOUNT CONTRACT (LOCAL-822 / 822B).

LOCAL-820 wired the .sh wrappers and isolated_test.py so a container's meter rows
reach the HOST, but its guard test only SCANS source files — it cannot see a
hand-typed ``docker run`` (LOCAL-818 launched its live tours that way), so the
next hand-typed run can still lose its rows inside the ``--rm`` container. LOCAL-817
made the whole-task budget mechanical by having the meter itself refuse; this does
the same for the meterlog mount.

[LOCAL-822B — the BOUNCE]  The meter is baked into the generator image with
ENV PYTHONPATH=/opt/meter, so check_meter_mount runs in EVERY container built from
it: Cloud Run, the Mac shared stack, the Windows laptop — none of which are Kiro
task runs. The first cut armed on ANY container (/.dockerenv) and so could refuse a
PRODUCTION paid call. The guard now ARMS ONLY for a task run (TASK_BUDGET_ID set,
or METER_SERVICE ^LOCAL-), never on Cloud Run (K_SERVICE set), and ALLOWS every
other container. These tests prove the new matrix, with NO network, NO DB and NO
real container:

  1. REFUSES — TASK RUN WITHOUT THE MOUNT. A task run (TASK_BUDGET_ID /
     METER_SERVICE=LOCAL-…) inside a container, with PAID_API_LOG's dir not a bind
     mount, raises MeterMountMissing and the refusal names
     ``meter_container_env.docker_meter_args``.
  2. PASSES — TASK RUN WITH THE MOUNT. The same task run with the bind mount is
     allowed.
  3. CLOUD RUN ALLOWED. K_SERVICE set, /.dockerenv present, no mount -> allowed,
     even if a task env also leaked in (K_SERVICE always disarms).
  4. PLAIN CONTAINER ALLOWED. A container with NO task identity and no mount ->
     allowed (today's production behaviour).
  5. MAC SHARED-STACK ALLOWED. The compose service env (METER_ROLE=listener, no
     TASK_BUDGET_ID, METER_SERVICE not ^LOCAL-) -> allowed, mount or not.
  6. HOST IS UNAFFECTED. With no /.dockerenv the guard never applies.
  7. ESCAPE HATCH. METER_MOUNT_GUARD=0 disables the guard for a deliberate
     no-mount diagnostic.
  8. END-TO-END THROUGH THE PATCHED CLIENT. A fake paid request routed through the
     meter's patched requests.Session.send is refused BEFORE it reaches the
     network when it is a task run with no mount.
  9. HARNESS ENTRY. tests/live_run_meter.LiveRunMeter.__enter__ refuses (task run,
     container, no mount) and passes (task run, container, mount) via the same door.
 10. FAIL-OPEN. A detection error allows the call (a guard bug must never block a
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
               "METER_MOUNT_GUARD", "PAID_API_LOG", "K_SERVICE",
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

    def _arm_task_service(self, task="LOCAL-822"):
        """Arm the guard as a Kiro task run via METER_SERVICE=LOCAL-…."""
        os.environ["METER_SERVICE"] = task

    def _arm_task_budget(self, task="LOCAL-822"):
        """Arm the guard as a Kiro task run via TASK_BUDGET_ID."""
        os.environ["TASK_BUDGET_ID"] = task

    def _set_cloud_run_env(self):
        """Cloud Run always sets K_SERVICE; here with /.dockerenv present and no
        mount — the guard must still allow (K_SERVICE disarms)."""
        os.environ["K_SERVICE"] = "tour-generator"

    def _set_shared_stack_env(self):
        """The Mac compose services' env: /meterlogs bind-mount present and
        METER_ROLE=listener, but NO TASK_BUDGET_ID and METER_SERVICE is a host
        name that does NOT start with LOCAL-. Not a task run -> allowed."""
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        os.environ["METER_ROLE"] = "listener"
        os.environ["METER_SERVICE"] = "tour-generator"   # production service tag, not LOCAL-…


# ─── 1. Refuses — task run inside a container without the mount ───────────────
class TestRefuses(_GuardTestBase):
    def test_refuses_task_run_without_mount_via_service(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._arm_task_service()                # armed task run; mount missing
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        with self.assertRaises(paid_api_meter.MeterMountMissing) as ctx:
            paid_api_meter.check_meter_mount()
        # The refusal must name the ONE helper that builds a correct run.
        self.assertIn("meter_container_env.docker_meter_args", str(ctx.exception))
        self.assertIn("bind-mount", str(ctx.exception))

    def test_refuses_task_run_without_mount_via_budget_id(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._arm_task_budget()                 # armed via TASK_BUDGET_ID
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        with self.assertRaises(paid_api_meter.MeterMountMissing):
            paid_api_meter.check_meter_mount()


# ─── 2. Passes — task run with the mount ──────────────────────────────────────
class TestPasses(_GuardTestBase):
    def test_passes_task_run_with_mount_and_service(self):
        self._fake_container(True)
        self._fake_mount(True)
        self._arm_task_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_passes_task_run_with_mount_and_task_budget_id(self):
        self._fake_container(True)
        self._fake_mount(True)
        self._arm_task_budget()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 3. Cloud Run is NEVER refused (the bounce: production must go through) ────
class TestCloudRunUnaffected(_GuardTestBase):
    def test_cloud_run_no_mount_allowed(self):
        # K_SERVICE set, in a container, no mount -> allowed. This is the exact
        # production path the bounce is about.
        self._fake_container(True)
        self._fake_mount(False)
        self._set_cloud_run_env()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_cloud_run_disarms_even_with_task_env(self):
        # Even if a task env leaked in, K_SERVICE must still disarm the guard.
        self._fake_container(True)
        self._fake_mount(False)
        self._set_cloud_run_env()
        self._arm_task_budget()                 # task env present …
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())   # … but K_SERVICE wins
        self.assertFalse(paid_api_meter._guard_armed())


# ─── 4. A plain container with no task identity is allowed ────────────────────
class TestPlainContainerUnaffected(_GuardTestBase):
    def test_plain_container_no_identity_no_mount_allowed(self):
        self._fake_container(True)
        self._fake_mount(False)                 # no task env at all, no mount
        self.assertIsNone(paid_api_meter.check_meter_mount())
        self.assertFalse(paid_api_meter._guard_armed())


# ─── 5. Mac shared-stack service env is allowed (the stack is unaffected) ─────
class TestSharedStackUnaffected(_GuardTestBase):
    def test_shared_stack_listener_env_without_mount_passes(self):
        # Exactly what docker-compose.subscribed-local.yml gives a service:
        # METER_ROLE=listener, a production METER_SERVICE (not LOCAL-…), no
        # TASK_BUDGET_ID. Not a task run -> allowed even without the mount.
        self._fake_container(True)
        self._fake_mount(False)
        self._set_shared_stack_env()
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_shared_stack_is_not_armed(self):
        self._set_shared_stack_env()
        self.assertFalse(paid_api_meter._guard_armed())


# ─── 6. Host is unaffected ────────────────────────────────────────────────────
class TestHostUnaffected(_GuardTestBase):
    def test_not_in_container_task_run_still_allows(self):
        # Even an armed task run is allowed on the host (no /.dockerenv): the
        # mount contract is a container-only concern.
        self._fake_container(False)
        self._fake_mount(False)
        self._arm_task_service()
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 7. Escape hatch ──────────────────────────────────────────────────────────
class TestEscapeHatch(_GuardTestBase):
    def test_guard_off_allows_task_run_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._arm_task_service()
        os.environ["METER_MOUNT_GUARD"] = "0"
        self.assertIsNone(paid_api_meter.check_meter_mount())

    def test_guard_on_by_default(self):
        self.assertTrue(paid_api_meter._mount_guard_on())
        os.environ["METER_MOUNT_GUARD"] = "false"
        self.assertFalse(paid_api_meter._mount_guard_on())


# ─── 8. End-to-end through the patched requests.Session.send ──────────────────
class TestEndToEndPatchedClient(_GuardTestBase):
    """A fake paid request through the meter's patched send() is refused BEFORE
    the original send runs when it is a task run with no mount — proving the guard
    is on the real paid path, not just a standalone function."""

    def test_patched_send_refuses_task_run_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._arm_task_service()
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

    def test_patched_send_allows_task_run_with_mount(self):
        # With the mount the guard does NOT raise; we assert the guard itself
        # returns None for this env (the send wrapper would then proceed to the
        # real network, which we do not do).
        self._fake_container(True)
        self._fake_mount(True)
        self._arm_task_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        self.assertIsNone(paid_api_meter.check_meter_mount())


# ─── 9. Harness entry (LiveRunMeter.__enter__) ────────────────────────────────
class TestHarnessEntry(_GuardTestBase):
    def test_enter_refuses_task_run_without_mount(self):
        self._fake_container(True)
        self._fake_mount(False)
        self._arm_task_service()
        os.environ["PAID_API_LOG"] = "/meterlogs/paid_api_calls.jsonl"
        # install_cap=False so construction does not touch story_leads/budget.
        m = lrm.LiveRunMeter("LOCAL-822", install_cap=False)
        with self.assertRaises(paid_api_meter.MeterMountMissing):
            with m:
                pass

    def test_enter_passes_task_run_with_mount(self):
        self._fake_container(True)
        self._fake_mount(True)
        self._arm_task_service()
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


# ─── 10. Fail-open on a detection error ───────────────────────────────────────
class TestFailOpen(_GuardTestBase):
    def test_detection_error_allows(self):
        # _in_container blowing up must NOT block the call (a guard bug can't wedge
        # a tour). check_meter_mount swallows it and returns None. Arm first so the
        # guard reaches the _in_container call.
        self._arm_task_service()

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
