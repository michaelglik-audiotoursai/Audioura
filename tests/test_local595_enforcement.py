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

    def _add_tour_requests(self, n, when_sql="NOW()", status='completed'):
        """Insert n orchestrator tour_requests rows for this device.
        tour_requests.secret_id FK -> users.secret_id, so ensure the user exists.

        [LOCAL-595B defect 2] Default status is 'completed' because the L2/Tester
        daily/monthly caps now count ONLY delivered (completed) tours. Pass
        status='started' or 'failed' to simulate an in-flight or failed request
        that must NOT count against the allowance."""
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
                        VALUES (%s, %s, %s, {when_sql}, 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8], status))
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


class TestDefect2CompletedOnlyCounting(LevelsTestBase):
    """[LOCAL-595B defect 2] L2/Tester daily & monthly caps count only DELIVERED
    (status='completed') tours. A 'started' (in-flight) or 'failed' row must not
    spend the allowance."""

    def setUp(self):
        super().setUp()
        self._set_level('l2')  # tours_per_day = 1

    def test_started_row_does_not_count(self):
        # One in-flight ('started') request today — the daily cap of 1 is NOT hit.
        self._add_tour_requests(1, status='started')
        r = sl.check_operation(self.uid, 'generate', requested_stops=3)
        # L2 generate still refuses with by_reference_unavailable (597), but the
        # point is it is NOT plan_limit_daily — the allowance was not consumed.
        self.assertStructuredRefusal(r, 'by_reference_unavailable')

    def test_failed_row_does_not_count(self):
        self._add_tour_requests(1, status='failed')
        r = sl.check_operation(self.uid, 'generate', requested_stops=3)
        self.assertStructuredRefusal(r, 'by_reference_unavailable')

    def test_completed_row_counts_toward_daily_cap(self):
        # One DELIVERED tour today -> the daily cap of 1 IS hit.
        self._add_tour_requests(1, status='completed')
        r = sl.check_operation(self.uid, 'generate', requested_stops=3)
        self.assertStructuredRefusal(r, 'plan_limit_daily')

    def test_tester_mixed_statuses_only_completed_count(self):
        # Tester: tours_per_day = 10. 9 completed + several started/failed today.
        self._set_level('tester')
        self._add_tour_requests(9, status='completed')
        self._add_tour_requests(5, status='started')  # in-flight, must not count
        self._add_tour_requests(3, status='failed')   # failed, must not count
        # 9 completed -> 10th allowed.
        self.assertTrue(sl.check_operation(self.uid, 'generate', requested_stops=5)['allowed'])
        # Add the 10th completed -> 11th refused daily.
        self._add_tour_requests(1, status='completed')
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=5), 'plan_limit_daily')


class TestDefect2ReserveRelease(LevelsTestBase):
    """[LOCAL-595B defect 2/3] reserve() guards concurrency; release() gives the
    pack unit back on failure or a cache hit."""

    def _counters(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT fresh_used, ops_used, edits_used FROM device_entitlement WHERE user_id = %s",
                    (self.uid,))
                return cur.fetchone()
        finally:
            c.close()

    def test_l3_reserve_then_release_restores_fresh_used(self):
        sl.grant_pack(self.uid, 'l3')
        self.assertEqual((0, 0, 0), self._counters())
        sl.reserve(self.uid, 'generate')          # request time
        self.assertEqual(1, self._counters()[0])  # fresh_used reserved
        sl.release(self.uid, 'generate')          # generation failed / cache hit
        self.assertEqual(0, self._counters()[0])  # fresh_used restored

    def test_l3_reserve_without_release_stands(self):
        # A successful FRESH delivery leaves the reservation in place.
        sl.grant_pack(self.uid, 'l3')
        sl.reserve(self.uid, 'generate')
        self.assertEqual(1, self._counters()[0])

    def test_release_floors_at_zero(self):
        # A stray release (double release / no prior reserve) never goes negative.
        sl.grant_pack(self.uid, 'l3')
        sl.release(self.uid, 'generate')
        self.assertEqual(0, self._counters()[0])

    def test_l3_concurrency_guard_blocks_second_of_two(self):
        # fresh_per_pack = 5. Reserve 5 -> the 6th check is refused even though
        # no tour has completed yet (reservation is the concurrency guard).
        sl.grant_pack(self.uid, 'l3')
        for _ in range(5):
            self.assertTrue(sl.check_operation(self.uid, 'generate', requested_stops=5)['allowed'])
            sl.reserve(self.uid, 'generate')
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=5), 'pack_exhausted')

    def test_l4_reserve_release_ops_pool(self):
        sl.grant_pack(self.uid, 'l4')
        sl.reserve(self.uid, 'generate')
        self.assertEqual(1, self._counters()[1])  # ops_used reserved
        sl.release(self.uid, 'generate')
        self.assertEqual(0, self._counters()[1])  # ops_used restored


class TestDefect3CacheHitNotFresh(LevelsTestBase):
    """[LOCAL-595B defect 3] A cache hit / stop-pool-only tour costs ~$0: it must
    NOT consume fresh_used (L3) / ops_used (L4), but it STILL counts toward the
    L2/Tester volume caps (because it reached status='completed')."""

    def test_cache_hit_releases_fresh_used_l3(self):
        # Model the orchestrator sequence: reserve at request time, then release
        # because store_action == 'already_exists'.
        sl.grant_pack(self.uid, 'l3')
        sl.reserve(self.uid, 'generate')
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT fresh_used FROM device_entitlement WHERE user_id=%s", (self.uid,))
                self.assertEqual(1, cur.fetchone()[0])  # reserved
        finally:
            c.close()
        sl.release(self.uid, 'generate')  # cache hit -> give it back
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT fresh_used FROM device_entitlement WHERE user_id=%s", (self.uid,))
                self.assertEqual(0, cur.fetchone()[0])  # not consumed
        finally:
            c.close()

    def test_cache_hit_completed_row_still_counts_for_l2_volume(self):
        # A delivered cache-hit tour is a 'completed' row, so it counts toward the
        # L2 daily cap even though fresh_used was released.
        self._set_level('l2')  # tours_per_day = 1
        self._add_tour_requests(1, status='completed')  # the delivered cache hit
        self.assertStructuredRefusal(
            sl.check_operation(self.uid, 'generate', requested_stops=3), 'plan_limit_daily')


if __name__ == '__main__':
    unittest.main(verbosity=2)
