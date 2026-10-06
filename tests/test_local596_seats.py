#!/usr/bin/env python3
"""test_local596_seats.py — LOCAL-596 L2 seat core.

Exercises l2_seats directly against audiotours_test:
  * install auto-grant threshold edge (49 → L2, 50 → L1),
  * two parallel installs at threshold-1 can't both pass (advisory lock),
  * the 100-seat cap on claim (99 free → granted, 100 full → refused),
  * eviction at exactly inactivity_days vs just under it,
  * offer expiry → requeue, then drop after max misses,
  * claim validation (wrong device, expired, bad code),
  * run_seat_cycle idempotency.

The threshold / cap / inactivity numbers live in the DB (l2_settings, plans.l2).
To test the edges without seeding 100 real rows, each test TEMPORARILY sets a
small value and restores it in tearDown — the code reads these at runtime so the
edge is exercised honestly. All synthetic rows use a 'LOCAL596-' prefix and are
removed in tearDown.

Run: python3 -m pytest tests/test_local596_seats.py -q
"""
import os
import sys
import uuid
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
_DB_URL = (
    f"postgresql://{_cfg['user']}:{_cfg['password']}"
    f"@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}"
)
os.environ["DATABASE_URL"] = _DB_URL

import psycopg2
import l2_seats


def _conn():
    return psycopg2.connect(_DB_URL)


def _apply_migration(path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'migration', 'sql', path)) as f:
        sql = f.read()
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()
    finally:
        c.close()


class SeatTestBase(unittest.TestCase):
    PREFIX = 'LOCAL596-SEAT-'

    @classmethod
    def setUpClass(cls):
        _apply_migration('012_subscription_levels.sql')  # device_entitlement, plans
        _apply_migration('015_l2_seats_queue.sql')        # l2_queue, l2_offers, l2_settings

    def setUp(self):
        self.ids = []
        self.c = _conn()
        self.cur = self.c.cursor()
        # Snapshot the config we may mutate so tearDown can restore it exactly.
        self.cur.execute("SELECT auto_grant_threshold, offer_expiry_hours, max_offer_misses FROM l2_settings WHERE id=TRUE")
        self._settings0 = self.cur.fetchone()
        self.cur.execute("SELECT seat_cap, inactivity_days FROM plans WHERE plan_id='l2'")
        self._plan0 = self.cur.fetchone()
        self.c.commit()

    def tearDown(self):
        # Restore config.
        self.cur.execute(
            "UPDATE l2_settings SET auto_grant_threshold=%s, offer_expiry_hours=%s, max_offer_misses=%s WHERE id=TRUE",
            self._settings0)
        self.cur.execute(
            "UPDATE plans SET seat_cap=%s, inactivity_days=%s WHERE plan_id='l2'",
            self._plan0)
        # Remove synthetic rows.
        for u in self.ids:
            self.cur.execute("DELETE FROM l2_offers WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM l2_queue WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (u,))
        self.c.commit()
        self.cur.close()
        self.c.close()

    def _uid(self, tag=''):
        u = self.PREFIX + tag + uuid.uuid4().hex[:8]
        self.ids.append(u)
        return u

    def _seats_now(self):
        return l2_seats.seats_in_use(self.cur)

    def _set_threshold(self, n):
        self.cur.execute("UPDATE l2_settings SET auto_grant_threshold=%s WHERE id=TRUE", (n,))
        self.c.commit()

    def _set_cap(self, n):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (n,))
        self.c.commit()

    def _set_inactivity(self, days):
        self.cur.execute("UPDATE plans SET inactivity_days=%s WHERE plan_id='l2'", (days,))
        self.c.commit()


class TestInstallThreshold(SeatTestBase):
    def test_below_threshold_empty_queue_grants_l2(self):
        # threshold = current seats + 2 → a new install is strictly below it.
        self._set_threshold(self._seats_now() + 2)
        uid = self._uid('BELOW-')
        lvl = l2_seats.grant_on_install(self.cur, uid)
        self.c.commit()
        self.assertEqual('l2', lvl)

    def test_at_threshold_grants_l1(self):
        # threshold = current seats → NOT strictly below → L1.
        self._set_threshold(self._seats_now())
        uid = self._uid('AT-')
        lvl = l2_seats.grant_on_install(self.cur, uid)
        self.c.commit()
        self.assertEqual('l1', lvl)

    def test_waiting_queue_blocks_autogrant_even_below_threshold(self):
        self._set_threshold(self._seats_now() + 10)  # plenty of room
        waiter = self._uid('WAIT-')
        l2_seats.join_queue(self.cur, waiter)  # creates a 'waiting' row
        self.c.commit()
        uid = self._uid('BLOCKED-')
        lvl = l2_seats.grant_on_install(self.cur, uid)
        self.c.commit()
        self.assertEqual('l1', lvl)  # queue not empty → L1 even with seats free


class TestTwoInstallsConcurrency(SeatTestBase):
    def test_two_parallel_installs_at_one_free_seat_only_one_wins(self):
        # Exactly ONE seat below threshold: seats + 1 == threshold.
        base = self._seats_now()
        self._set_threshold(base + 1)
        u1 = self._uid('RACE1-')
        u2 = self._uid('RACE2-')
        results = {}

        def install(uid):
            c = _conn()
            try:
                cur = c.cursor()
                lvl = l2_seats.grant_on_install(cur, uid)
                c.commit()
                results[uid] = lvl
            finally:
                c.close()

        t1 = threading.Thread(target=install, args=(u1,))
        t2 = threading.Thread(target=install, args=(u2,))
        t1.start(); t2.start(); t1.join(); t2.join()
        granted = [u for u, lvl in results.items() if lvl == 'l2']
        # The advisory lock serializes the count-and-insert: with one free seat,
        # exactly one install may be granted L2, the other must get L1.
        self.assertEqual(1, len(granted),
                         f"expected exactly one L2 grant, got {results}")


class TestClaimCapEdge(SeatTestBase):
    def _make_offer(self, uid):
        """Put uid in the queue and hand it a live offer; return the code."""
        l2_seats.join_queue(self.cur, uid)
        self.c.commit()
        offered = l2_seats.offer_free_seats(self.cur)
        self.c.commit()
        for u, code in offered:
            if u == uid:
                return code
        return None

    def test_claim_with_one_free_seat_succeeds_then_full_refuses(self):
        base = self._seats_now()
        # First claimer: cap = base + 1 → exactly one free seat.
        self._set_cap(base + 1)
        u1 = self._uid('CLAIM1-')
        code1 = self._make_offer(u1)
        self.assertIsNotNone(code1)
        r1 = l2_seats.claim_seat(self.cur, u1, code1)
        self.c.commit()
        self.assertTrue(r1['ok'], r1)
        self.assertEqual('l2', self._level(u1))

        # Now seats == cap (full). Offer another device, lower nothing, claim must
        # refuse claim_seats_full. We must craft an offer while a seat looks free
        # to the offer step, so bump cap by 1 for the offer then drop it back.
        u2 = self._uid('CLAIM2-')
        self._set_cap(base + 2)
        code2 = self._make_offer(u2)
        self.assertIsNotNone(code2)
        self._set_cap(base + 1)  # now full again
        r2 = l2_seats.claim_seat(self.cur, u2, code2)
        self.c.commit()
        self.assertFalse(r2['ok'])
        self.assertEqual(l2_seats.CLAIM_SEATS_FULL, r2['code'])
        self.assertEqual('l1', self._level(u2) or 'l1')

    def _level(self, uid):
        self.cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (uid,))
        row = self.cur.fetchone()
        return row[0] if row else None


class TestClaimValidation(SeatTestBase):
    def _offer_to(self, uid):
        self._set_cap(self._seats_now() + 5)
        l2_seats.join_queue(self.cur, uid)
        self.c.commit()
        offered = l2_seats.offer_free_seats(self.cur)
        self.c.commit()
        return dict(offered).get(uid)

    def _level(self, uid):
        self.cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (uid,))
        r = self.cur.fetchone()
        return r[0] if r else None

    def test_bad_code(self):
        u = self._uid('BAD-')
        r = l2_seats.claim_seat(self.cur, u, 'NOPE-NOPE')
        self.assertFalse(r['ok'])
        self.assertEqual(l2_seats.CLAIM_BAD_CODE, r['code'])

    def test_wrong_device(self):
        owner = self._uid('OWNER-')
        other = self._uid('OTHER-')
        code = self._offer_to(owner)
        r = l2_seats.claim_seat(self.cur, other, code)
        self.assertFalse(r['ok'])
        self.assertEqual(l2_seats.CLAIM_WRONG_DEVICE, r['code'])

    def test_expired_offer(self):
        u = self._uid('EXP-')
        code = self._offer_to(u)
        # Backdate the offer past expiry.
        self.cur.execute("UPDATE l2_offers SET expires_at = NOW() - INTERVAL '1 hour' WHERE code=%s", (code,))
        self.c.commit()
        r = l2_seats.claim_seat(self.cur, u, code)
        self.assertFalse(r['ok'])
        self.assertEqual(l2_seats.CLAIM_EXPIRED, r['code'])


class TestEviction(SeatTestBase):
    def _level(self, uid):
        self.cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (uid,))
        return self.cur.fetchone()[0]

    def test_evict_at_exactly_inactivity_days(self):
        self._set_inactivity(7)
        uid = self._uid('IDLE7-')
        self.cur.execute(
            "INSERT INTO device_entitlement (user_id,level,last_activity_at) VALUES (%s,'l2',NOW()-INTERVAL '7 days')",
            (uid,))
        self.c.commit()
        evicted = l2_seats.evict_idle(self.cur)
        self.c.commit()
        self.assertIn(uid, evicted)
        self.assertEqual('l1', self._level(uid))

    def test_not_evicted_just_under_window(self):
        self._set_inactivity(7)
        uid = self._uid('IDLE6-')
        self.cur.execute(
            "INSERT INTO device_entitlement (user_id,level,last_activity_at) VALUES (%s,'l2',NOW()-INTERVAL '6 days 23 hours')",
            (uid,))
        self.c.commit()
        evicted = l2_seats.evict_idle(self.cur)
        self.c.commit()
        self.assertNotIn(uid, evicted)
        self.assertEqual('l2', self._level(uid))


class TestOfferExpiry(SeatTestBase):
    def _qstatus(self, uid):
        self.cur.execute("SELECT status, offer_misses FROM l2_queue WHERE user_id=%s", (uid,))
        return self.cur.fetchone()

    def test_expired_offer_requeues_then_drops_after_max_misses(self):
        self.cur.execute("UPDATE l2_settings SET max_offer_misses=2 WHERE id=TRUE")
        self._set_cap(self._seats_now() + 5)
        self.c.commit()
        uid = self._uid('MISS-')
        l2_seats.join_queue(self.cur, uid)
        self.c.commit()

        # Miss #1: offer, backdate past expiry, expire → requeued (waiting).
        l2_seats.offer_free_seats(self.cur); self.c.commit()
        self.cur.execute("UPDATE l2_offers SET expires_at=NOW()-INTERVAL '1 hour' WHERE user_id=%s AND status='offered'", (uid,))
        self.c.commit()
        res1 = l2_seats.expire_offers(self.cur); self.c.commit()
        self.assertIn(uid, res1['requeued'])
        self.assertEqual('waiting', self._qstatus(uid)[0])

        # Miss #2: offer again, backdate, expire → now dropped ('expired').
        l2_seats.offer_free_seats(self.cur); self.c.commit()
        self.cur.execute("UPDATE l2_offers SET expires_at=NOW()-INTERVAL '1 hour' WHERE user_id=%s AND status='offered'", (uid,))
        self.c.commit()
        res2 = l2_seats.expire_offers(self.cur); self.c.commit()
        self.assertIn(uid, res2['dropped'])
        self.assertEqual('expired', self._qstatus(uid)[0])


class TestCycleIdempotency(SeatTestBase):
    def test_run_seat_cycle_twice_no_double_offer(self):
        self._set_cap(self._seats_now() + 5)
        uid = self._uid('CYC-')
        l2_seats.join_queue(self.cur, uid)
        self.c.commit()
        s1 = l2_seats.run_seat_cycle(self.cur); self.c.commit()
        offered1 = [u for (u, _c) in s1['offered']]
        self.assertIn(uid, offered1)
        s2 = l2_seats.run_seat_cycle(self.cur); self.c.commit()
        offered2 = [u for (u, _c) in s2['offered']]
        self.assertNotIn(uid, offered2)  # already 'offered' — not offered twice


if __name__ == '__main__':
    unittest.main(verbosity=2)
