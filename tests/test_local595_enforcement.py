#!/usr/bin/env python3
"""test_local595_enforcement.py — LOCAL-595 check_operation enforcement.

Runs against the database (audiotours_test under pytest). Verifies every limit
in the levels table at BOTH edges (at the limit = allowed, one over = refused),
L1 refused generation with a structured error, and the renewal gate.

Run: python3 -m pytest tests/test_local595_enforcement.py -q
"""
import os
import sys
import uuid
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
# Point the service modules (which read DB_* with Docker defaults) at the same
# host DB the test helper resolves (audiotours_test on host port 5433).
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

import psycopg2
import subscription_levels as sl

STRUCTURED_KEYS = {'allowed', 'error_code', 'error', 'message', 'suggestion'}


def _conn():
    return psycopg2.connect(
        host=_cfg["host"], port=_cfg["port"], dbname=_cfg["dbname"],
        user=_cfg["user"], password=_cfg["password"],
    )


def _ensure_schema():
    """Ensure the 012 plans columns + device_entitlement exist (idempotent)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = os.path.join(here, 'migration', 'sql', '012_subscription_levels.sql')
    with open(sql_path) as f:
        sql = f.read()
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()
    finally:
        c.close()


class LevelsTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_schema()

    def setUp(self):
        self.uid = 'L595-' + uuid.uuid4().hex[:10]
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (self.uid,))
                cur.execute("DELETE FROM users WHERE secret_id = %s", (self.uid,))
            c.commit()
        finally:
            c.close()

    def _set_level(self, level):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO device_entitlement (user_id, level) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level
                """, (self.uid, level))
            c.commit()
        finally:
            c.close()

    def _add_tour_requests(self, n, when_sql="NOW()"):
        """Insert n orchestrator tour_requests rows for this device.
        tour_requests.secret_id FK -> users.secret_id, so ensure the user exists."""
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (secret_id, plan) VALUES (%s, 'l2')
                    ON CONFLICT (secret_id) DO NOTHING
                """, (self.uid,))
                for _ in range(n):
                    cur.execute(f"""
                        INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
                        VALUES (%s, %s, 'started', {when_sql}, 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8]))
            c.commit()
        finally:
            c.close()

    def assertStructuredRefusal(self, result, error_code):
        self.assertFalse(result['allowed'])
        self.assertEqual(error_code, result['error_code'])
        self.assertTrue(STRUCTURED_KEYS.issubset(result.keys()))
        self.assertTrue(result['message'])
        self.assertIsNotNone(result['suggestion'])


class TestL1(LevelsTestBase):
    def test_l1_generate_refused_structured(self):
        # Default device (no row) is L1.
        r = sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertStructuredRefusal(r, 'level_cannot_generate')

    def test_l1_edit_add_stops_refused(self):
        r = sl.check_operation(self.uid, 'edit_add_stops', new_stops=1)
        self.assertStructuredRefusal(r, 'level_cannot_generate')

    def test_l1_listen_always_allowed(self):
        self.assertTrue(sl.check_operation(self.uid, 'listen')['allowed'])

    def test_l1_text_edit_always_allowed(self):
        self.assertTrue(sl.check_operation(self.uid, 'edit_text')['allowed'])


class TestL2(LevelsTestBase):
    def setUp(self):
        super().setUp()
        self._set_level('l2')

    def test_l2_generate_by_reference_unavailable(self):
        r = sl.check_operation(self.uid, 'generate', requested_stops=3)
        self.assertStructuredRefusal(r, 'by_reference_unavailable')

    def test_l2_stops_over_plan_at_edge(self):
        # max_stops = 5. 5 is allowed-through-to-by_reference; 6 is over.
        r = sl.check_operation(self.uid, 'generate', requested_stops=6)
        self.assertStructuredRefusal(r, 'stops_over_plan')

    def test_l2_daily_cap_one_over(self):
        # tours_per_day = 1. One request today -> daily cap hit.
        self._add_tour_requests(1)
        r = sl.check_operation(self.uid, 'generate', requested_stops=3)
        self.assertStructuredRefusal(r, 'plan_limit_daily')

    def test_l2_cannot_add_stops(self):
        r = sl.check_operation(self.uid, 'edit_add_stops', new_stops=1)
        self.assertStructuredRefusal(r, 'level_cannot_generate')


class TestL3(LevelsTestBase):
    def setUp(self):
        super().setUp()
        sl.grant_pack(self.uid, 'l3')  # fresh pack, anniversary +1 month

    def test_l3_generate_at_stop_limit_allowed(self):
        r = sl.check_operation(self.uid, 'generate', requested_stops=10)  # max_stops=10
        self.assertTrue(r['allowed'])
        self.assertEqual(10, r['clamped_stops'])

    def test_l3_generate_one_over_stop_limit_refused(self):
        r = sl.check_operation(self.uid, 'generate', requested_stops=11)
        self.assertStructuredRefusal(r, 'stops_over_plan')

    def test_l3_fresh_pack_edges(self):
        # 5 fresh per pack: first 5 allowed, 6th pack_exhausted.
        for i in range(5):
            r = sl.check_operation(self.uid, 'generate', requested_stops=5)
            self.assertTrue(r['allowed'], f"generation {i+1} should be allowed")
            sl.consume(self.uid, 'generate')
        r = sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertStructuredRefusal(r, 'pack_exhausted')

    def test_l3_edit_add_stops_edge(self):
        # max_new_stops_per_edit = 10: 10 allowed, 11 refused.
        self.assertTrue(sl.check_operation(self.uid, 'edit_add_stops', new_stops=10)['allowed'])
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'edit_add_stops', new_stops=11), 'stops_over_plan')

    def test_l3_edits_pack_exhaust(self):
        # 5 edits per pack.
        for _ in range(5):
            self.assertTrue(sl.check_operation(self.uid, 'edit_add_stops', new_stops=1)['allowed'])
            sl.consume(self.uid, 'edit_add_stops', new_stops=1)
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'edit_add_stops', new_stops=1), 'pack_exhausted')


class TestL4(LevelsTestBase):
    def setUp(self):
        super().setUp()
        sl.grant_pack(self.uid, 'l4')

    def test_l4_stop_limit_edges(self):
        self.assertTrue(sl.check_operation(self.uid, 'generate', requested_stops=25)['allowed'])
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=26), 'stops_over_plan')

    def test_l4_new_stops_per_edit_edge(self):
        self.assertTrue(sl.check_operation(self.uid, 'edit_add_stops', new_stops=10)['allowed'])
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'edit_add_stops', new_stops=11), 'stops_over_plan')

    def test_l4_combined_ops_pool_exhausts_on_mix(self):
        # 25 ops shared across new + edit. Mix 20 generate + 5 edit = 25, 26th refused.
        for _ in range(20):
            self.assertTrue(sl.check_operation(self.uid, 'generate', requested_stops=5)['allowed'])
            sl.consume(self.uid, 'generate')
        for _ in range(5):
            self.assertTrue(sl.check_operation(self.uid, 'edit_add_stops', new_stops=1)['allowed'])
            sl.consume(self.uid, 'edit_add_stops', new_stops=1)
        # 26th op (either kind) is refused.
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=5), 'pack_exhausted')
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'edit_add_stops', new_stops=1), 'pack_exhausted')


class TestTester(LevelsTestBase):
    def setUp(self):
        super().setUp()
        self._set_level('tester')

    def test_tester_daily_cap_edges(self):
        # tours_per_day = 10. 9 used -> 10th allowed; 10 used -> 11th refused daily.
        self._add_tour_requests(9)
        self.assertTrue(sl.check_operation(self.uid, 'generate', requested_stops=5)['allowed'])
        self._add_tour_requests(1)  # now 10 today
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=5), 'plan_limit_daily')

    def test_tester_stop_limit_edge(self):
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=6), 'stops_over_plan')

    def test_tester_new_stops_per_edit_edge(self):
        self.assertTrue(sl.check_operation(self.uid, 'edit_add_stops', new_stops=5)['allowed'])
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'edit_add_stops', new_stops=6), 'stops_over_plan')


class TestRenewalGate(LevelsTestBase):
    def test_renewal_due_blocks_generate_but_not_listen(self):
        # Grant L3, then force the anniversary into the past.
        sl.grant_pack(self.uid, 'l3')
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE device_entitlement SET anniversary_at = %s WHERE user_id = %s",
                    (datetime.utcnow() - timedelta(days=1), self.uid))
            c.commit()
        finally:
            c.close()
        r = sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertStructuredRefusal(r, 'renewal_due')
        # Listening is still allowed past the anniversary.
        self.assertTrue(sl.check_operation(self.uid, 'listen')['allowed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
