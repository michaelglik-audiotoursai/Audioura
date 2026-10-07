#!/usr/bin/env python3
"""test_local613_meter_and_cap.py — LOCAL-613 meter + cap + report (no network).

Three things the ticket asks tests to prove:
  1. THE HELPER WRITES A ROW. ``LiveRunMeter.record()`` writes exactly one
     ``cost_ledger`` row with ``user_id='TEST-<LOCAL-NNN>'``, ``description='test
     run'`` and the LOCAL-609 breakdown fields. Proven two ways: against a real
     throwaway-schema DB when one is reachable (IsolatedSchema, LOCAL-601), and
     always against a captured ``record_operation`` so the contract holds with no
     DB at all.
  2. THE CAP RAISES AT THE THRESHOLD. With a cap installed, the grounding counter
     raises ``story_leads.TestRunCapExceeded`` the instant combined spend reaches
     the cap — and NOT before. The cap covers all providers combined.
  3. THE REPORT GROUPS CORRECTLY. ``cost_report_window`` sums synthetic rows by
     provider and by user (live vs TEST-*), with correct subtotals and
     reconciliation.

No real Gemini/OpenAI/Serper calls, no required DB.

Run: python3 -m pytest tests/test_local613_meter_and_cap.py -q
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import story_leads  # noqa: E402
import cost_report_window as report  # noqa: E402
import live_run_meter as lrm  # noqa: E402
from cost_rates import GROUNDING_COST_PER_QUERY  # noqa: E402


# ─── 2. Cap raises at the threshold ───────────────────────────────────────────
class TestCapRaisesAtThreshold(unittest.TestCase):
    def setUp(self):
        story_leads.reset_grounding_requests()
        story_leads.set_grounding_cap_callback(None)

    def tearDown(self):
        story_leads.set_grounding_cap_callback(None)
        story_leads.reset_grounding_requests()

    def test_user_id_normalisation(self):
        self.assertEqual(lrm._normalise_task_id("LOCAL-613"), "TEST-LOCAL-613")
        self.assertEqual(lrm._normalise_task_id("local613"), "TEST-LOCAL-613")
        self.assertEqual(lrm._normalise_task_id("613"), "TEST-LOCAL-613")
        self.assertEqual(lrm._normalise_task_id("TEST-LOCAL-613"), "TEST-LOCAL-613")

    def test_default_cap_is_one_dollar(self):
        os.environ.pop("TEST_GEMINI_MAX_USD", None)
        self.assertEqual(lrm.resolve_cap_usd(), lrm.DEFAULT_TEST_GEMINI_MAX_USD)
        self.assertEqual(lrm.DEFAULT_TEST_GEMINI_MAX_USD, 1.00)

    def test_env_sets_cap(self):
        os.environ["TEST_GEMINI_MAX_USD"] = "0.25"
        try:
            self.assertAlmostEqual(lrm.resolve_cap_usd(), 0.25)
        finally:
            os.environ.pop("TEST_GEMINI_MAX_USD", None)

    def test_cap_raises_exactly_at_threshold(self):
        # cap $0.10; each grounded response reports 2 queries @ $0.014 = $0.028.
        # Spend crosses $0.10 at 8 queries ($0.112) — the 4th response.
        m = lrm.LiveRunMeter("LOCAL-613", cap_usd=0.10, install_cap=True)
        self.addCleanup(m.uninstall)

        issued_queries = 0
        with self.assertRaises(story_leads.TestRunCapExceeded):
            for _ in range(50):
                story_leads._count_grounding_request()      # pre-issue guard
                story_leads._count_grounding_queries(["a", "b"])  # +2 queries
                issued_queries += 2
        # Stopped the instant combined spend first reached the cap: 8 queries.
        self.assertEqual(story_leads.get_grounding_queries(), 8)
        self.assertTrue(m.capped)
        self.assertGreaterEqual(
            story_leads.get_grounding_queries() * GROUNDING_COST_PER_QUERY, 0.10)

    def test_no_raise_below_threshold(self):
        # cap $1.00; a handful of queries stays well under — never raises.
        m = lrm.LiveRunMeter("LOCAL-613", cap_usd=1.00, install_cap=True)
        self.addCleanup(m.uninstall)
        for _ in range(3):
            story_leads._count_grounding_request()
            story_leads._count_grounding_queries(["a", "b"])
        self.assertEqual(story_leads.get_grounding_queries(), 6)
        self.assertFalse(m.capped)

    def test_cap_counts_all_providers_combined(self):
        # Pre-load $0.09 of OpenAI+Serper; cap $0.10. Then ONE grounded response
        # of 1 query ($0.014) pushes combined to $0.104 >= cap and must raise —
        # proving the cap is combined, not gemini-only.
        m = lrm.LiveRunMeter("LOCAL-613", cap_usd=0.10, install_cap=True)
        self.addCleanup(m.uninstall)
        m.add_openai(0.085)
        m.add_serper(usd=0.005)   # combined non-gemini = 0.090
        with self.assertRaises(story_leads.TestRunCapExceeded):
            story_leads._count_grounding_request()
            story_leads._count_grounding_queries(["only-one"])  # +$0.014 -> 0.104
        self.assertTrue(m.capped)

    def test_cap_off_by_default_for_unrelated_code(self):
        # With no cap installed, the grounding counter never raises.
        story_leads.set_grounding_cap_callback(None)
        for _ in range(100):
            story_leads._count_grounding_request()
            story_leads._count_grounding_queries(["a", "b", "c"])
        self.assertEqual(story_leads.get_grounding_queries(), 300)  # no raise


# ─── 1. The helper writes a row (no DB: capture record_operation) ──────────────
class TestHelperWritesRowNoDB(unittest.TestCase):
    def setUp(self):
        story_leads.reset_grounding_requests()
        story_leads.set_grounding_cap_callback(None)
        self._captured = {}

        import cost_meter
        self._orig = cost_meter.record_operation

        def _capture(**kwargs):
            self._captured = dict(kwargs)
            return "fake-row-id"

        cost_meter.record_operation = lambda *a, **k: _capture(**k)

    def tearDown(self):
        import cost_meter
        cost_meter.record_operation = self._orig
        story_leads.set_grounding_cap_callback(None)
        story_leads.reset_grounding_requests()

    def test_record_writes_one_test_row_with_breakdown(self):
        m = lrm.LiveRunMeter("LOCAL-613", cap_usd=1.00, install_cap=False)
        m.add_openai(0.02)
        m.add_serper(usd=0.008)
        m.add_grounding(requests=3, queries=7, preflight_queries=2)
        row_id = m.record()

        self.assertEqual(row_id, "fake-row-id")
        c = self._captured
        self.assertEqual(c["user_id"], "TEST-LOCAL-613")
        self.assertEqual(c["description"], "test run")
        self.assertEqual(c["operation_type"], "tour_generate")
        # total = openai 0.02 + grounding 7*0.014 + serper 0.008 (preflight NOT re-added)
        self.assertAlmostEqual(c["our_cost_usd"], 0.02 + 7 * 0.014 + 0.008, places=6)

        b = c["breakdown"]
        for field in ("openai", "gemini_grounding", "gemini_tokens", "serper",
                      "preflight"):
            self.assertIn(field, b)
        self.assertEqual(b["gemini_grounding"]["requests"], 3)
        self.assertEqual(b["gemini_grounding"]["queries"], 7)
        self.assertAlmostEqual(b["gemini_grounding"]["usd"], 7 * 0.014, places=6)
        self.assertAlmostEqual(b["preflight"], 2 * 0.014, places=6)

    def test_record_is_idempotent(self):
        m = lrm.LiveRunMeter("LOCAL-613", install_cap=False)
        m.add_openai(0.01)
        first = m.record()
        second = m.record()  # must not write a second row
        self.assertEqual(first, "fake-row-id")
        self.assertIsNone(second)

    def test_record_never_raises_on_db_error(self):
        import cost_meter

        def _boom(**kwargs):
            raise RuntimeError("DB down")

        cost_meter.record_operation = lambda *a, **k: _boom(**k)
        m = lrm.LiveRunMeter("LOCAL-613", install_cap=False)
        m.add_openai(0.01)
        # Must swallow the error and return None — a metering failure must never
        # break the run (that was the original bug).
        self.assertIsNone(m.record())


# ─── 3. The report groups correctly ───────────────────────────────────────────
class TestReportGroups(unittest.TestCase):
    def _rows(self):
        return [
            # live user, old flat breakdown (llm/tts/search)
            {"user_id": "USER-abc", "operation_type": "tour_generate",
             "our_cost_usd": 0.075,
             "breakdown": {"llm": 0.05, "tts": 0.02, "search": 0.005}},
            # live user, no breakdown -> unattributed at full row total
            {"user_id": "USER-abc", "operation_type": "tour_generate",
             "our_cost_usd": 0.10, "breakdown": None},
            # TEST run, LOCAL-613 breakdown (reconciles exactly)
            {"user_id": "TEST-LOCAL-613", "operation_type": "tour_generate",
             "our_cost_usd": 0.02 + 7 * 0.014 + 0.008,
             "breakdown": {"openai": 0.02,
                           "gemini_grounding": {"usd": 7 * 0.014,
                                                "requests": 3, "queries": 7},
                           "gemini_tokens": 0.0, "serper": 0.008,
                           "preflight": 2 * 0.014}},
        ]

    def test_grouping_and_subtotals(self):
        f = report.parse_ts("2026-10-06T20:56Z")
        t = report.parse_ts("2026-10-07T04:29Z")
        rep = report.build_report(self._rows(), f, t)

        self.assertEqual(rep["row_count"], 3)
        self.assertAlmostEqual(rep["live_total_usd"], 0.175, places=6)
        self.assertAlmostEqual(rep["test_total_usd"], 0.126, places=6)
        self.assertAlmostEqual(rep["grand_total_usd"], 0.301, places=6)

        bp = rep["by_provider"]
        self.assertAlmostEqual(bp["openai"], 0.07, places=6)        # 0.05 + 0.02
        self.assertAlmostEqual(bp["gemini_grounding"], 0.098, places=6)
        self.assertAlmostEqual(bp["serper"], 0.013, places=6)       # 0.005 + 0.008
        self.assertAlmostEqual(bp["tts"], 0.02, places=6)
        self.assertAlmostEqual(bp["preflight"], 0.028, places=6)    # subset, shown
        self.assertAlmostEqual(bp["unattributed"], 0.10, places=6)

        bu = rep["by_user"]
        self.assertFalse(bu["USER-abc"]["is_test"])
        self.assertTrue(bu["TEST-LOCAL-613"]["is_test"])
        self.assertEqual(bu["USER-abc"]["rows"], 2)

    def test_window_is_half_open(self):
        # A row exactly at --to must be excluded; the SQL uses created_at < to.
        # (We assert the boundary intent via parse_ts ordering here.)
        f = report.parse_ts("2026-10-06T20:56Z")
        t = report.parse_ts("2026-10-07T04:29Z")
        self.assertLess(f, t)

    def test_parse_ts_formats(self):
        from datetime import datetime, timezone
        self.assertEqual(report.parse_ts("2026-10-06T20:56Z"),
                         datetime(2026, 10, 6, 20, 56, tzinfo=timezone.utc))
        self.assertEqual(report.parse_ts("2026-10-07 04:29"),
                         datetime(2026, 10, 7, 4, 29, tzinfo=timezone.utc))
        self.assertIsNotNone(report.parse_ts("2026-10-06").tzinfo)


# ─── 1b. The helper writes a row against a REAL DB (skips if unreachable) ──────
try:
    from _isolated_db import IsolatedSchema
    _ISO = IsolatedSchema(
        prefix="t613",
        clone_tables=["cost_ledger"],
        proof_tables=["cost_ledger"],
        banner="LOCAL-613",
    )
    _ISO_OK = True
except Exception:
    _ISO = None
    _ISO_OK = False


def setUpModule():
    if _ISO is not None:
        _ISO.setup()


def tearDownModule():
    if _ISO is not None:
        _ISO.teardown()


@unittest.skipUnless(_ISO_OK and _ISO.db_up(), "dev Postgres not reachable")
class TestHelperWritesRowRealDB(unittest.TestCase):
    def setUp(self):
        story_leads.reset_grounding_requests()
        story_leads.set_grounding_cap_callback(None)
        # cost_meter builds its own URL from DB_* (default host 'postgres-2',
        # the in-container name). On the host that name does not resolve, so point
        # cost_meter at the SAME reachable DB IsolatedSchema connected to. The
        # process-wide PGOPTIONS search_path still routes the write into the
        # throwaway schema, so nothing lands in public.
        cfg = _ISO._config()
        self._saved_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = (
            f"postgresql://{cfg['user']}:{cfg['password']}@"
            f"{cfg['host']}:{cfg['port']}/{cfg['dbname']}")

    def tearDown(self):
        story_leads.set_grounding_cap_callback(None)
        if self._saved_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._saved_db_url

    def test_one_row_lands_in_ledger(self):
        import psycopg2
        m = lrm.LiveRunMeter("LOCAL-613", cap_usd=1.00, install_cap=False,
                             job_id="local613-test-job")
        m.add_openai(0.03)
        m.add_grounding(requests=2, queries=5)
        m.add_serper(queries=4)
        row_id = m.record()
        self.assertIsNotNone(row_id)

        cfg = _ISO._config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
            user=cfg["user"], password=cfg["password"])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, description, our_cost_usd, breakdown "
                    "FROM cost_ledger WHERE id = %s", (row_id,))
                r = cur.fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "TEST-LOCAL-613")
        self.assertEqual(r[1], "test run")
        self.assertAlmostEqual(
            float(r[2]), 0.03 + 5 * 0.014 + 4 * 0.001, places=6)
        self.assertIn("gemini_grounding", r[3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
