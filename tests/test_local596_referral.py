#!/usr/bin/env python3
"""test_local596_referral.py — LOCAL-596 referral → L2 seat grant.

Covers the referrer allowance (L3 3 lifetime, L4 5/month, Tester 3) read from
plans, self/duplicate refusals, the full-cap refusal, and the HTTP endpoint
contract (granted_level=l2 vs structured refusal).

Run: python3 -m pytest tests/test_local596_referral.py -q
"""
import os
import sys
import uuid
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
os.environ["GATEWAY_API_KEY"] = "test-key-596"

import psycopg2
import referral_engine as rengine
import l2_seats

API_KEY = "test-key-596"
H = {"X-API-Key": API_KEY}


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


def _ensure_referral_tables():
    """Create the referral tables + UNIQUE(referral_code,new_user_id) constraint
    if they are not already present. Idempotent (unlike migration 009's bare
    ALTER ADD CONSTRAINT). referral_engine._ensure_tables builds the base tables;
    we add the unique guard the engine relies on as its race backstop."""
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referral_codes (
                    code VARCHAR(6) PRIMARY KEY,
                    referrer_user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    redemption_count INTEGER DEFAULT 0
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referral_redemptions (
                    id SERIAL PRIMARY KEY,
                    referral_code VARCHAR(6) NOT NULL REFERENCES referral_codes(code),
                    new_user_id TEXT NOT NULL,
                    redeemed_at TIMESTAMP DEFAULT NOW()
                )""")
            cur.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'uq_referral_redemptions_code_user'
                    ) THEN
                        ALTER TABLE referral_redemptions
                            ADD CONSTRAINT uq_referral_redemptions_code_user
                            UNIQUE (referral_code, new_user_id);
                    END IF;
                END $$;""")
        c.commit()
    finally:
        c.close()


class RefBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _apply_migration('012_subscription_levels.sql')
        _apply_migration('015_l2_seats_queue.sql')
        _ensure_referral_tables()

    def setUp(self):
        self.ids = []
        self.codes = []
        self.c = _conn()
        self.cur = self.c.cursor()
        self.cur.execute("SELECT seat_cap FROM plans WHERE plan_id='l2'")
        self._cap0 = self.cur.fetchone()[0]
        self.c.commit()

    def tearDown(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._cap0,))
        for code in self.codes:
            self.cur.execute("DELETE FROM referral_redemptions WHERE referral_code=%s", (code,))
            self.cur.execute("DELETE FROM referral_codes WHERE code=%s", (code,))
        for u in self.ids:
            self.cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (u,))
        self.c.commit()
        self.cur.close()
        self.c.close()

    def _uid(self, tag=''):
        u = 'REF596-' + tag + uuid.uuid4().hex[:8]
        self.ids.append(u)
        return u

    def _make_referrer(self, level):
        ref = self._uid('REFR-')
        self.cur.execute(
            "INSERT INTO device_entitlement (user_id,level,last_activity_at) VALUES (%s,%s,NOW())",
            (ref, level))
        code = 'R' + uuid.uuid4().hex[:5].upper()
        self.codes.append(code)
        self.cur.execute("INSERT INTO referral_codes (code,referrer_user_id) VALUES (%s,%s)", (code, ref))
        self.c.commit()
        return ref, code

    def _seats_now(self):
        return l2_seats.seats_in_use(self.cur)

    def _level(self, uid):
        self.cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (uid,))
        r = self.cur.fetchone()
        return r[0] if r else None


class TestAllowanceCounting(RefBase):
    def test_l3_grants_exactly_three_then_refuses(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 10,))
        self.c.commit()
        ref, code = self._make_referrer('l3')  # 3 lifetime
        granted = 0
        for i in range(4):
            u = self._uid(f'R{i}-')
            res = rengine.redeem_referral_for_seat(code, u, _DB_URL)
            if res['ok']:
                granted += 1
                self.assertEqual('l2', self._level(u))
            else:
                self.assertEqual(rengine.REDEEM_ALLOWANCE_SPENT, res['code'])
        self.assertEqual(3, granted)

    def test_l4_allows_five(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 10,))
        self.c.commit()
        ref, code = self._make_referrer('l4')  # 5 / month
        granted = sum(
            1 for i in range(6)
            if rengine.redeem_referral_for_seat(code, self._uid(f'R{i}-'), _DB_URL)['ok']
        )
        self.assertEqual(5, granted)

    def test_tester_allows_three(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 10,))
        self.c.commit()
        ref, code = self._make_referrer('tester')  # 3 / month
        granted = sum(
            1 for i in range(4)
            if rengine.redeem_referral_for_seat(code, self._uid(f'R{i}-'), _DB_URL)['ok']
        )
        self.assertEqual(3, granted)


class TestRefusals(RefBase):
    def test_self_referral_refused(self):
        ref, code = self._make_referrer('l3')
        res = rengine.redeem_referral_for_seat(code, ref, _DB_URL)
        self.assertFalse(res['ok'])
        self.assertEqual(rengine.REDEEM_SELF, res['code'])

    def test_duplicate_refused(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 10,))
        self.c.commit()
        ref, code = self._make_referrer('l3')
        u = self._uid('DUP-')
        first = rengine.redeem_referral_for_seat(code, u, _DB_URL)
        self.assertTrue(first['ok'])
        second = rengine.redeem_referral_for_seat(code, u, _DB_URL)
        self.assertFalse(second['ok'])
        self.assertEqual(rengine.REDEEM_DUPLICATE, second['code'])

    def test_unknown_code_refused(self):
        res = rengine.redeem_referral_for_seat('ZZZZZZ', self._uid('X-'), _DB_URL)
        self.assertFalse(res['ok'])
        self.assertEqual(rengine.REDEEM_UNKNOWN, res['code'])

    def test_full_cap_refuses(self):
        ref, code = self._make_referrer('l3')
        # Set the cap to the current seat count → no free seat.
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now(),))
        self.c.commit()
        res = rengine.redeem_referral_for_seat(code, self._uid('FULL-'), _DB_URL)
        self.assertFalse(res['ok'])
        self.assertEqual(rengine.REDEEM_SEATS_FULL, res['code'])


class TestEndpoint(RefBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from flask import Flask
        import referral_endpoints as rep
        rep.API_KEY = API_KEY
        rep.DATABASE_URL = _DB_URL
        app = Flask(__name__)
        app.register_blueprint(rep.referral_bp)
        cls.client = app.test_client()

    def test_redeem_endpoint_grants_l2(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 10,))
        self.c.commit()
        ref, code = self._make_referrer('l3')
        u = self._uid('EP-')
        r = self.client.post('/referral/redeem',
                             json={'referral_code': code, 'new_user_id': u}, headers=H)
        self.assertEqual(200, r.status_code)
        j = r.get_json()
        self.assertTrue(j['redeemed'])
        self.assertEqual('l2', j['granted_level'])
        self.assertEqual('l2', self._level(u))

    def test_redeem_endpoint_full_cap_409(self):
        ref, code = self._make_referrer('l3')
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now(),))
        self.c.commit()
        u = self._uid('EPFULL-')
        r = self.client.post('/referral/redeem',
                             json={'referral_code': code, 'new_user_id': u}, headers=H)
        self.assertEqual(409, r.status_code)
        self.assertEqual('referral_seats_full', r.get_json()['error_code'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
