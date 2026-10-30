#!/usr/bin/env python3
"""test_local827_container_budget.py — WHOLE-TASK budget ACROSS CONTAINERS (LOCAL-827).

The bug
=======
The whole-task cap (LOCAL-817) reads ``~/.audioura_task_budgets/<id>.json``, which
only ``LiveRunMeter`` writes and only at the END of a run. But the isolated
``docker run --rm`` task containers never bind-mounted that dir, so each run wrote
its ledger INSIDE the container, which ``--rm`` destroyed: every run started from
$0 and the cap never accumulated across runs. LOCAL-821B spent $0.81 against a
$0.40 cap; LOCAL-823/824 reported "No ledger … No runs recorded yet".

The fix, and what these tests prove (NO network, NO DB, NO real container)
=========================================================================
  1. docker_meter_args MOUNTS THE LEDGER DIR + ARMS THE BUDGET. The ONE shared
     contract now bind-mounts ~/.audioura_task_budgets -> /task_budgets, sets
     AUDIOURA_TASK_BUDGET_DIR there, and sets TASK_BUDGET_ID/TASK_BUDGET_USD from
     the arg or the caller env — so every isolated run shares ONE ledger and the
     cap is armed, without per-runner wiring. The five LOCAL-820 signals survive.

  2. TWO CONTAINERS UNDER ONE TASK ID ACCUMULATE. Two separate runs appending to
     the SAME shared meter log (what the bind-mount achieves) sum to the task's
     TRUE spend: the raw-door meter-log cap sees run1 + run2, not just the current
     run's.

  3. THE CALL THAT WOULD CROSS THE CAP IS REFUSED. Once the summed meter-log spend
     for service==TASK_BUDGET_ID reaches TASK_BUDGET_USD, check_task_budget_meter_log
     raises TaskBudgetExceeded — and so does the meter's patched requests.Session.send
     BEFORE the call reaches the network.

  4. PRODUCTION IS NOT ARMED. Cloud Run (K_SERVICE) and a non-task env (no
     TASK_BUDGET_ID) are never armed: a cap for Kiro task runs can never refuse a
     production paid call. The cap only counts the task's OWN rows (service match),
     so a shared-stack row in the same log never counts toward a task's cap.

  5. REPORT FALLS BACK TO THE METER LOG. task_budget_report, given an id with NO
     ledger, sums the meter log by service and reports the total / over-budget.

Run: python3 -m pytest tests/test_local827_container_budget.py -q
"""
import json
import os
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_METER = os.path.join(_ROOT, "_meter")
for _p in (_HERE, _ROOT, _METER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meter_container_env as mce  # noqa: E402
import paid_api_meter  # noqa: E402
import task_budget_report as report  # noqa: E402


_ENVS = ("TASK_BUDGET_ID", "TASK_BUDGET_USD", "AUDIOURA_TASK_BUDGET_DIR",
         "AUDIOURA_METERLOG_DIR", "PAID_API_LOG", "METER_SERVICE", "K_SERVICE",
         "METER_MOUNT_GUARD")


class _Base(unittest.TestCase):
    """Clean env, a throwaway meterlog dir, and a cleared meter-log cap around
    every test so one test's log/cache cannot leak into another."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENVS}
        for k in _ENVS:
            os.environ.pop(k, None)
        self._dir = tempfile.mkdtemp(prefix="l827-")
        self._log = os.path.join(self._dir, "paid_api_calls.jsonl")
        # Point BOTH the meter door (PAID_API_LOG) and the report fallback
        # (AUDIOURA_METERLOG_DIR) at the throwaway log/dir.
        os.environ["PAID_API_LOG"] = self._log
        os.environ["AUDIOURA_METERLOG_DIR"] = self._dir
        self._clear_cap_cache()

    def tearDown(self):
        self._clear_cap_cache()
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _clear_cap_cache(self):
        with paid_api_meter._meterlog_lock:
            paid_api_meter._meterlog_cap_cache.clear()

    def _append_row(self, service, usd, status=200, log=None):
        """Append one meter-log row exactly as the meter writes it (service, usd,
        status), to the shared log. Simulates one paid call recorded by one run."""
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "kind": "openai", "status": status, "service": service, "usd": usd}
        with open(log or self._log, "a") as f:
            f.write(json.dumps(row) + "\n")

    def _set_budget(self, task_id, usd):
        os.environ["TASK_BUDGET_ID"] = task_id
        os.environ["TASK_BUDGET_USD"] = str(usd)


# ─── 1. docker_meter_args mounts the ledger dir + arms the budget ─────────────
class TestDockerArgs(_Base):
    def test_mounts_ledger_dir_and_sets_env(self):
        bdir = os.path.join(self._dir, "budgets")
        args = mce.docker_meter_args(
            task_id="LOCAL-827", meter_dir="/repo/_meter",
            host_meter_dir=os.path.join(self._dir, "ml"),
            host_task_budget_dir=bdir, task_budget_usd="0.0002")
        joined = " ".join(args)
        # The NEW 827 signals:
        self.assertIn("%s:%s" % (bdir, mce.CONTAINER_TASK_BUDGET_DIR), joined)
        self.assertIn("AUDIOURA_TASK_BUDGET_DIR=%s" % mce.CONTAINER_TASK_BUDGET_DIR,
                      joined)
        self.assertIn("TASK_BUDGET_ID=LOCAL-827", joined)
        self.assertIn("TASK_BUDGET_USD=0.0002", joined)
        # The dir is created so the bind-mount never fails.
        self.assertTrue(os.path.isdir(bdir))

    def test_budget_falls_back_to_caller_env(self):
        os.environ["TASK_BUDGET_USD"] = "0.50"   # caller env, no explicit arg
        args = mce.docker_meter_args(
            task_id="LOCAL-827", meter_dir="/repo/_meter",
            host_meter_dir=os.path.join(self._dir, "ml"),
            host_task_budget_dir=os.path.join(self._dir, "b"))
        joined = " ".join(args)
        self.assertIn("TASK_BUDGET_ID=LOCAL-827", joined)
        self.assertIn("TASK_BUDGET_USD=0.50", joined)

    def test_no_budget_means_no_budget_env(self):
        # With no explicit budget and none in the caller env, the budget vars are
        # NOT emitted (the mount + AUDIOURA_TASK_BUDGET_DIR still are, so a run
        # that sets its own TASK_BUDGET_* elsewhere still shares the ledger).
        args = mce.docker_meter_args(
            task_id="LOCAL-827", meter_dir="/repo/_meter",
            host_meter_dir=os.path.join(self._dir, "ml"),
            host_task_budget_dir=os.path.join(self._dir, "b"),
            env={})   # explicit empty env -> no TASK_BUDGET_USD
        joined = " ".join(args)
        self.assertNotIn("TASK_BUDGET_USD=", joined)
        self.assertIn("AUDIOURA_TASK_BUDGET_DIR=", joined)

    def test_preserves_local820_contract(self):
        # The five LOCAL-820 meter-contract signals must survive the 827 change.
        ml = os.path.join(self._dir, "ml")
        args = mce.docker_meter_args(task_id="LOCAL-820", meter_dir="/repo/_meter",
                                     host_meter_dir=ml, key_suffix="k9sA",
                                     host_task_budget_dir=os.path.join(self._dir, "b"))
        joined = " ".join(args)
        self.assertIn("PYTHONPATH=/opt/meter", joined)
        self.assertIn("PAID_API_LOG=/meterlogs/paid_api_calls.jsonl", joined)
        self.assertIn("METER_SERVICE=LOCAL-820", joined)
        self.assertIn("%s:/meterlogs" % ml, joined)
        self.assertIn("/repo/_meter:/opt/meter:ro", joined)
        self.assertIn("METER_KEY_SUFFIX=k9sA", joined)


# ─── 2. Two containers under one task id accumulate in the shared meter log ───
class TestAccumulatesAcrossContainers(_Base):
    def test_two_runs_sum_in_meter_log(self):
        tid = "LOCAL-827"
        self._set_budget(tid, 0.0002)
        # "Container 1" records one tiny paid call.
        self._append_row(tid, 0.0001)
        self.assertAlmostEqual(
            paid_api_meter._sum_meter_log_usd_for_service(tid, self._log),
            0.0001, places=6)
        # "Container 2" (a SEPARATE run, same shared log) records another.
        self._append_row(tid, 0.0001)
        # The sum is run1 + run2 — the whole point of the shared mount.
        self.assertAlmostEqual(
            paid_api_meter._sum_meter_log_usd_for_service(tid, self._log),
            0.0002, places=6)

    def test_only_this_tasks_rows_count(self):
        tid = "LOCAL-827"
        self._set_budget(tid, 1.00)
        self._append_row(tid, 0.10)
        self._append_row("tour-generator", 5.00)     # shared-stack row, same log
        self._append_row("LOCAL-999", 9.00)          # another task, same log
        # Only service==LOCAL-827 rows count toward LOCAL-827's cap.
        self.assertAlmostEqual(
            paid_api_meter._sum_meter_log_usd_for_service(tid, self._log),
            0.10, places=6)

    def test_non_200_rows_excluded(self):
        tid = "LOCAL-827"
        self._append_row(tid, 0.10, status=200)
        self._append_row(tid, 0.99, status=429)   # errored call, not billed
        self.assertAlmostEqual(
            paid_api_meter._sum_meter_log_usd_for_service(tid, self._log),
            0.10, places=6)


# ─── 3. The call that would cross the cap is refused ──────────────────────────
class TestRefusesAtCap(_Base):
    def test_door_allows_under_budget(self):
        tid = "LOCAL-827"
        self._set_budget(tid, 0.0002)
        self._append_row(tid, 0.0001)   # one run, under budget
        self.assertIsNone(paid_api_meter.check_task_budget_meter_log())

    def test_door_refuses_once_sum_reaches_budget(self):
        tid = "LOCAL-827"
        self._set_budget(tid, 0.0002)
        # Two runs reach the $0.0002 cap in the shared log.
        self._append_row(tid, 0.0001)
        self._append_row(tid, 0.0001)
        self._clear_cap_cache()   # force a fresh read (new rows)
        with self.assertRaises(paid_api_meter.TaskBudgetExceeded) as ctx:
            paid_api_meter.check_task_budget_meter_log()
        self.assertIn("LOCAL-827", str(ctx.exception))
        self.assertIn("meter log", str(ctx.exception))

    def test_zero_budget_refuses_first_call(self):
        tid = "LOCAL-827-ZERO"
        self._set_budget(tid, 0)   # $0 cap: not one paid cent (0 >= 0)
        with self.assertRaises(paid_api_meter.TaskBudgetExceeded):
            paid_api_meter.check_task_budget_meter_log()

    def test_patched_send_refuses_before_network(self):
        # End-to-end: the meter's patched requests.Session.send refuses a paid
        # call BEFORE it reaches the network once the cap is reached.
        tid = "LOCAL-827"
        self._set_budget(tid, 0.0002)
        self._append_row(tid, 0.0002)   # already at the cap
        self._clear_cap_cache()
        paid_api_meter.install()
        import requests
        req = requests.Request(
            "POST", "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o-mini"}).prepare()
        sess = requests.Session()
        with self.assertRaises(paid_api_meter.TaskBudgetExceeded):
            requests.Session.send(sess, req)

    def test_cache_ttl_reads_at_most_every_10s(self):
        # The sum is cached: a row appended AFTER a read within the TTL is not
        # seen until the cache expires. Proves the 10 s re-read contract.
        tid = "LOCAL-827"
        self._set_budget(tid, 1.00)
        self._append_row(tid, 0.10)
        t0 = 1000.0
        self.assertAlmostEqual(
            paid_api_meter._meter_log_spent(tid, self._log, now=t0), 0.10, places=6)
        self._append_row(tid, 0.50)   # a new call lands…
        # …but within the 10 s window the cached $0.10 is still returned.
        self.assertAlmostEqual(
            paid_api_meter._meter_log_spent(tid, self._log, now=t0 + 5), 0.10,
            places=6)
        # After the TTL the file is re-read and the new total is seen.
        self.assertAlmostEqual(
            paid_api_meter._meter_log_spent(tid, self._log, now=t0 + 11), 0.60,
            places=6)


# ─── 4. Production is not armed ───────────────────────────────────────────────
class TestProductionNotArmed(_Base):
    def test_no_task_id_not_armed(self):
        # No TASK_BUDGET_ID -> cap off, whatever the log holds.
        self._append_row("tour-generator", 99.0)
        self.assertFalse(paid_api_meter._meter_log_cap_armed())
        self.assertIsNone(paid_api_meter.check_task_budget_meter_log())

    def test_cloud_run_disarms_even_with_task_env(self):
        tid = "LOCAL-827"
        self._set_budget(tid, 0)        # a $0 cap that WOULD refuse …
        os.environ["K_SERVICE"] = "tour-generator"   # … but Cloud Run disarms it
        self.assertFalse(paid_api_meter._meter_log_cap_armed())
        self.assertIsNone(paid_api_meter.check_task_budget_meter_log())

    def test_budget_unset_not_armed(self):
        os.environ["TASK_BUDGET_ID"] = "LOCAL-827"   # id but no budget
        self.assertFalse(paid_api_meter._meter_log_cap_armed())
        self.assertIsNone(paid_api_meter.check_task_budget_meter_log())

    def test_fail_open_on_unreadable_log(self):
        # A read error inside the summer must fail open (allow), never block.
        tid = "LOCAL-827"
        self._set_budget(tid, 0.0002)

        def _boom(task_id, log_path):
            raise RuntimeError("disk gone")
        orig = paid_api_meter._sum_meter_log_usd_for_service
        paid_api_meter._sum_meter_log_usd_for_service = _boom
        try:
            self._clear_cap_cache()
            # _meter_log_spent swallows the error -> 0.0 -> under budget -> allow.
            self.assertIsNone(paid_api_meter.check_task_budget_meter_log())
        finally:
            paid_api_meter._sum_meter_log_usd_for_service = orig


# ─── 5. Report falls back to the meter log when no ledger exists ──────────────
class TestReportFallback(_Base):
    def test_fallback_sums_meter_log_and_flags_over_budget(self):
        tid = "LOCAL-827"
        # No ledger dir for this id -> report must use the meter log.
        os.environ["AUDIOURA_TASK_BUDGET_DIR"] = os.path.join(self._dir, "no_ledger")
        self._set_budget(tid, 0.0002)
        self._append_row(tid, 0.0001)
        self._append_row(tid, 0.0002)   # total 0.0003 > 0.0002
        text, code = report.build_report_text(tid)
        self.assertIn("summing the meter log", text)
        self.assertIn("METERED TOTAL", text)
        self.assertIn("OVER BUDGET", text)
        self.assertEqual(code, 2)

    def test_fallback_within_budget_exit_0(self):
        tid = "LOCAL-827"
        os.environ["AUDIOURA_TASK_BUDGET_DIR"] = os.path.join(self._dir, "no_ledger")
        self._set_budget(tid, 1.00)
        self._append_row(tid, 0.10)
        text, code = report.build_report_text(tid)
        self.assertIn("METERED TOTAL", text)
        self.assertEqual(code, 0)

    def test_no_ledger_no_rows_exit_1(self):
        tid = "LOCAL-NOTHING"
        os.environ["AUDIOURA_TASK_BUDGET_DIR"] = os.path.join(self._dir, "no_ledger")
        text, code = report.build_report_text(tid)
        self.assertIn("No ledger", text)
        self.assertIn("No metered rows", text)
        self.assertEqual(code, 1)

    def test_sum_helper_counts_rows(self):
        tid = "LOCAL-827"
        self._append_row(tid, 0.10)
        self._append_row(tid, 0.20)
        self._append_row("other", 9.0)
        total, n = report.sum_meter_log_for_service(
            tid, log_glob=os.path.join(self._dir, "*.jsonl"))
        self.assertAlmostEqual(total, 0.30, places=6)
        self.assertEqual(n, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
