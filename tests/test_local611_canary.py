#!/usr/bin/env python3
"""tests/test_local611_canary.py — LOCAL-611 canary runner unit tests.

Covers the four acceptance checks, all offline (no live services):

  1. STRATIFIED PICK NEVER REPEATS — across many runs with a persisted tried
     ledger, no QID or route key is ever selected twice; each run draws across
     the famous/obscure/rotating strata.
  2. BUDGET STOP — run_canary stops submitting once cumulative cost reaches
     CANARY_MAX_USD; tours after the cap are not submitted.
  3. REPORT PARSING — a rendered CANARY.md block round-trips through
     parse_runs / run_count / pass_rate_history, and a failure writes
     '*** CANARY FAIL ***' to ALERTS.md.
  4. IS_TEST SET — with a stubbed orchestrator (and stubbed DB), a completed
     canary tour is recorded is_test=TRUE and its coordinates are nulled.

Run:  python3 tests/test_local611_canary.py
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

CANARY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "canary"))
sys.path.insert(0, CANARY_DIR)

import picker as pk          # noqa: E402
import report as rpt         # noqa: E402
import run_canary as rc      # noqa: E402


def _make_pool():
    """A small but strata-complete pool: famous US museums, obscure FR churches,
    non-English galleries, and two FR streets for a walking route."""
    pool = []
    for i in range(40):
        pool.append({"qid": f"QF{i}", "label": f"Famous {i}", "city": "New York City",
                     "country": "United States", "country_qid": "Q30",
                     "sitelinks": 45, "has_site": True, "kind": "museum",
                     "lat": 40.7 + i * 0.01, "lng": -74.0 - i * 0.01})
    for i in range(40):
        pool.append({"qid": f"QO{i}", "label": f"Obscure {i}", "city": "Lyon",
                     "country": "France", "country_qid": "Q142",
                     "sitelinks": 1, "has_site": False, "kind": "church",
                     "lat": 45.7 + i * 0.01, "lng": 4.8 + i * 0.01})
    for i in range(40):
        pool.append({"qid": f"QN{i}", "label": f"Galerie {i}", "city": "Lyon",
                     "country": "France", "country_qid": "Q142",
                     "sitelinks": 12, "has_site": True, "kind": "gallery",
                     "lat": 45.75 + i * 0.01, "lng": 4.85 + i * 0.01})
    for i in range(10):
        pool.append({"qid": f"QS{i}", "label": f"Rue {i}", "city": "Paris",
                     "country": "France", "country_qid": "Q142",
                     "sitelinks": 4, "has_site": False, "kind": "street",
                     "lat": 48.85 + i * 0.01, "lng": 2.35 + i * 0.01})
    return pool


class TestStratifiedPickNeverRepeats(unittest.TestCase):
    def test_no_repeat_across_runs_with_ledger(self):
        pool = _make_pool()
        tmp = tempfile.mkdtemp()
        ledger = os.path.join(tmp, "tried_venues.jsonl")

        seen = set()
        for run in range(12):
            tried = pk.load_tried(ledger)
            sel = pk.pick_new_venues(pool, tried, run_index=run, seed=run, n=3)
            self.assertTrue(len(sel) >= 1, "pool should yield selections")
            keys = [s["key"] for s in sel]
            # no dup within the run
            self.assertEqual(len(keys), len(set(keys)), f"dup within run {run}: {keys}")
            # no dup against anything previously selected
            for k in keys:
                self.assertNotIn(k, seen, f"repeat across runs: {k} (run {run})")
            seen.update(keys)
            pk.record_tried(sel, ledger)

        # The ledger must now contain exactly the keys we selected, no dups.
        persisted = pk.load_tried(ledger)
        self.assertEqual(persisted, seen)

    def test_strata_present_in_fresh_run(self):
        pool = _make_pool()
        sel = pk.pick_new_venues(pool, set(), run_index=0, seed=0, n=3)
        strata = {s["stratum"] for s in sel}
        self.assertIn("famous", strata)
        self.assertIn("obscure", strata)
        self.assertIn("rotating", strata)
        fam = next(s for s in sel if s["stratum"] == "famous")
        obs = next(s for s in sel if s["stratum"] == "obscure")
        self.assertGreaterEqual(fam["sitelinks"], pk.FAMOUS_SITELINKS)
        self.assertLessEqual(obs["sitelinks"], pk.OBSCURE_SITELINKS)

    def test_walking_route_format(self):
        pool = _make_pool()
        import random
        r = pk._synth_walking_route(pool, set(), random.Random(0))
        self.assertIsNotNone(r)
        self.assertTrue(r["key"].startswith("route:"))
        self.assertIn(" to ", r["location"])
        self.assertEqual(r["tour_type"], "walking")


class TestBudgetStop(unittest.TestCase):
    def test_run_stops_at_cap(self):
        pool = _make_pool()

        # Each tour "costs" $1.20 — the 3rd submission would exceed the $3 cap.
        calls = {"submit": 0}

        def fake_submit(location, tour_type, total_stops, request_string=None):
            calls["submit"] += 1
            return f"job-{calls['submit']}"

        def fake_poll(job_id, **kw):
            return {"status": "completed", "actual_stops": 2,
                    "coordinates": [1.0, 2.0], "final_tour_id": 999}

        def fake_cost(job_id):
            return {"total": 1.20, "breakdown": {"llm": 1.0, "tts": 0.2}, "rows": 1}

        def fake_run_one(name, location, tour_type, total_stops, **kw):
            # Mirror run_one_tour's shape but skip DB/HTTP; drive cost via fake_cost.
            jid = fake_submit(location, tour_type, total_stops)
            fake_poll(jid)
            return {"name": name, "location": location, "tour_type": tour_type,
                    "requested_stops": total_stops, "success": True,
                    "delivered_stops": 2, "coordinates_present": True,
                    "is_test": True, "url_in_audio": False, "check_site_count": 0,
                    "wall_s": 1.0, "cost": fake_cost(jid), "job_id": jid,
                    "tour_id": 999, "error_code": "", "error_message": ""}

        tmp = tempfile.mkdtemp()
        with mock.patch.object(rc, "CANARY_MAX_USD", 3.0), \
             mock.patch.object(rc, "run_one_tour", side_effect=fake_run_one), \
             mock.patch.object(rc, "seed_canary_device"), \
             mock.patch.object(rc, "count_audio_tours", return_value=0), \
             mock.patch.object(rc.vp, "load_pool", return_value=pool), \
             mock.patch.object(rc.pk, "load_tried", return_value=set()), \
             mock.patch.object(rc.pk, "record_tried"), \
             mock.patch.object(rc.rpt, "CANARY_MD", os.path.join(tmp, "CANARY.md")), \
             mock.patch.object(rc.rpt, "ALERTS_MD", os.path.join(tmp, "ALERTS.md")), \
             mock.patch.object(rc.rpt, "run_count", return_value=0), \
             mock.patch.object(rc.rpt, "git_sha", return_value="testsha"):
            rc.main(["--seed", "0"])

        # At $1.20/tour and a $3 cap: tours 1 and 2 run (cum $1.20, $2.40); before
        # tour 3 the cumulative ($2.40) is < 3 so tour 3 runs (cum $3.60) — then
        # the guard trips and no further tours submit. So 3 submissions max, and
        # strictly fewer than the full 8-tour plan.
        self.assertLessEqual(calls["submit"], 3)
        self.assertGreaterEqual(calls["submit"], 2)
        self.assertLess(calls["submit"], 8)


class TestReportParsing(unittest.TestCase):
    def _summary(self, idx, results, bs=False, cost=1.0):
        return {"run_index": idx, "timestamp": f"2026-10-07T10:0{idx}:00+00:00",
                "code_sha": "abc123", "cap_usd": 3.0, "total_cost": cost,
                "budget_stopped": bs, "count_before": 100,
                "count_after": 100 + len(results), "results": results,
                "pool_meta": {"rows": 21000, "countries": 64, "built_at": "2026-10-01"}}

    def _ok(self, name="known[0]", group="known"):
        return {"name": name, "group": group, "location": "Phu Quoc, Vietnam",
                "requested_stops": 2, "delivered_stops": 2, "success": True,
                "coordinates_present": True, "is_test": True, "url_in_audio": False,
                "check_site_count": 0, "wall_s": 60.0,
                "cost": {"total": 0.3, "breakdown": {"llm": 0.2, "tts": 0.1}},
                "error_code": "", "error_message": ""}

    def _bad(self):
        r = self._ok(name="new[0:obscure]", group="new")
        r.update(success=False, error_code="stop_count_mismatch",
                 error_message="requested 2 delivered 1", delivered_stops=1,
                 cost={"total": 0.15, "breakdown": {}})
        return r

    def test_roundtrip_and_history(self):
        tmp = tempfile.mkdtemp()
        cmd = os.path.join(tmp, "CANARY.md")
        alerts = os.path.join(tmp, "ALERTS.md")

        rpt.append_canary_report(self._summary(0, [self._ok(), self._ok()]), path=cmd)
        self.assertEqual(rpt.run_count(cmd), 1)

        rpt.append_canary_report(
            self._summary(1, [self._ok(), self._bad()], bs=True, cost=2.9), path=cmd)
        rpt.write_alert(
            self._summary(1, [self._ok(), self._bad()], bs=True), path=alerts)
        self.assertEqual(rpt.run_count(cmd), 2)

        runs = rpt.parse_runs(cmd)
        self.assertEqual(runs[0]["pass"], 2)
        self.assertEqual(runs[0]["total"], 2)
        self.assertEqual(runs[1]["pass"], 1)
        self.assertTrue(runs[1]["budget_stopped"])

        hist = rpt.pass_rate_history(cmd, last=10)
        self.assertEqual(hist["tours_passed"], 3)
        self.assertEqual(hist["tours_total"], 4)
        self.assertEqual(hist["per_run"], ["2/2", "1/2"])

        with open(alerts, encoding="utf-8") as _fh:
            alert_txt = _fh.read()
        self.assertIn("*** CANARY FAIL ***", alert_txt)
        self.assertIn("stop_count_mismatch", alert_txt)
        self.assertIn("budget stop", alert_txt)


class TestIsTestSet(unittest.TestCase):
    def test_completed_tour_is_marked_test_and_coords_nulled(self):
        """With a stubbed orchestrator + DB, a completed canary tour is recorded
        is_test=TRUE and its lat/lng are nulled by the runner."""
        nulled = {"ids": []}

        def fake_submit(location, tour_type, total_stops, request_string=None):
            return "job-xyz"

        def fake_poll(job_id, **kw):
            return {"status": "completed", "actual_stops": 2,
                    "coordinates": [42.3, -71.0], "final_tour_id": 4242}

        # DB row: (id, is_test, lat, lng, audio_bytes, tour_content)
        def fake_fetch(final_tour_id, request_string):
            return (4242, True, 42.3, -71.0, 50000,
                    "Visit the museum. For hours, check their website.")

        def fake_inspect(tour_id):
            return {"audio_files": 2, "url_hits": 1, "check_site_count": 1,
                    "text_chars": 100}

        def fake_null(tour_id):
            nulled["ids"].append(tour_id)
            return True

        with mock.patch.object(rc, "fetch_tour_row", side_effect=fake_fetch), \
             mock.patch.object(rc, "inspect_audio_text", side_effect=fake_inspect), \
             mock.patch.object(rc, "null_coords_for", side_effect=fake_null), \
             mock.patch.object(rc, "job_cost", return_value={"total": 0.3, "breakdown": {}, "rows": 1}):
            res = rc.run_one_tour("known[0]", "Phu Quoc, Vietnam", "", 2,
                                  submit=fake_submit, poll=fake_poll)

        self.assertTrue(res["success"])
        self.assertTrue(res["is_test"], "canary tour must be recorded is_test=TRUE")
        self.assertEqual(res["delivered_stops"], 2)
        self.assertTrue(res["coordinates_present"])
        self.assertTrue(res["url_in_audio"])
        self.assertEqual(res["check_site_count"], 1)
        self.assertEqual(res["tour_id"], 4242)
        # The runner must have nulled the coordinates for the created row.
        self.assertIn(4242, nulled["ids"])

    def test_submit_payload_carries_is_test_true(self):
        """The payload the runner POSTs must set is_test=true (the flag the
        orchestrator honours under TOUR_TEST_MODE_ALLOW_REQUEST)."""
        captured = {}

        class _Resp:
            status_code = 200
            def json(self):
                return {"job_id": "job-1", "status": "queued"}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

        fake_requests = mock.MagicMock()
        fake_requests.post = fake_post
        with mock.patch.dict("sys.modules", {"requests": fake_requests}):
            job_id = rc.submit_tour("Phu Quoc, Vietnam", "", 2)

        self.assertEqual(job_id, "job-1")
        self.assertTrue(captured["url"].endswith("/generate-complete-tour"))
        self.assertEqual(captured["json"]["is_test"], True)
        self.assertEqual(captured["json"]["user_id"], rc.CANARY_USER)
        self.assertEqual(captured["json"]["total_stops"], 2)
        self.assertEqual(captured["json"]["language"], "en")


if __name__ == "__main__":
    unittest.main(verbosity=2)
