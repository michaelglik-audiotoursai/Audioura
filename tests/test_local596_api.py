#!/usr/bin/env python3
"""test_local596_api.py — LOCAL-596 queue + claim endpoints.

Drives the user-api entitlements blueprint via Flask's test client against
audiotours_test: join (L1-only, idempotent), /entitlements/me queue_position +
pending_offer, leave, and claim (success + each structured refusal).

Run: python3 -m pytest tests/test_local596_api.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user-tracking'))

from db_connection import get_db_config

_cfg = get_db_config()
_DB_URL = (
    f"postgresql://{_cfg['user']}:{_cfg['password']}"
    f"@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}"
)
os.environ["DATABASE_URL"] = _DB_URL
os.environ["GATEWAY_API_KEY"] = "test-key-596"

import psycopg2
from flask import Flask
import entitlements_api as ea
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


class ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _apply_migration('012_subscription_levels.sql')
        _apply_migration('015_l2_seats_queue.sql')
        app = Flask(__name__)
        app.register_blueprint(ea.entitlements_bp)
        cls.client = app.test_client()

    def setUp(self):
        self.ids = []
        self.c = _conn()
        self.cur = self.c.cursor()
        self.cur.execute("SELECT seat_cap FROM plans WHERE plan_id='l2'")
        self._cap0 = self.cur.fetchone()[0]
        self.c.commit()

    def tearDown(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._cap0,))
        for u in self.ids:
            self.cur.execute("DELETE FROM l2_offers WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM l2_queue WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (u,))
        self.c.commit()
        self.cur.close()
        self.c.close()

    def _uid(self, tag=''):
        u = 'API596-' + tag + uuid.uuid4().hex[:8]
        self.ids.append(u)
        return u

    def _seats_now(self):
        return l2_seats.seats_in_use(self.cur)

    def _make_offer_api(self, uid):
        """Join via API, raise the cap so a seat is free, offer via the core,
        and return the live code."""
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now() + 5,))
        self.c.commit()
        self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H)
        offered = l2_seats.offer_free_seats(self.cur)
        self.c.commit()
        return dict(offered).get(uid)


class TestQueueJoinLeave(ApiBase):
    def test_join_requires_api_key(self):
        r = self.client.post('/l2/queue/join', json={'user_id': 'x'})
        self.assertEqual(401, r.status_code)

    def test_join_l1_then_me_shows_position(self):
        uid = self._uid('JOIN-')
        r = self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H)
        self.assertEqual(200, r.status_code)
        self.assertIsNotNone(r.get_json()['queue_position'])
        me = self.client.get(f'/entitlements/me?user_id={uid}', headers=H).get_json()
        self.assertEqual(me['queue_position'], r.get_json()['queue_position'])

    def test_join_is_idempotent(self):
        uid = self._uid('IDEM-')
        p1 = self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H).get_json()['queue_position']
        p2 = self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H).get_json()['queue_position']
        self.assertEqual(p1, p2)

    def test_join_refused_when_already_l2(self):
        uid = self._uid('ISL2-')
        self.cur.execute("INSERT INTO device_entitlement (user_id,level) VALUES (%s,'l2')", (uid,))
        self.c.commit()
        r = self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H)
        self.assertEqual(409, r.status_code)
        self.assertEqual('already_l2', r.get_json()['error'])

    def test_leave_clears_position(self):
        uid = self._uid('LEAVE-')
        self.client.post('/l2/queue/join', json={'user_id': uid}, headers=H)
        self.client.post('/l2/queue/leave', json={'user_id': uid}, headers=H)
        me = self.client.get(f'/entitlements/me?user_id={uid}', headers=H).get_json()
        self.assertIsNone(me['queue_position'])


class TestClaimApi(ApiBase):
    def test_me_shows_pending_offer(self):
        uid = self._uid('OFFER-')
        code = self._make_offer_api(uid)
        self.assertIsNotNone(code)
        me = self.client.get(f'/entitlements/me?user_id={uid}', headers=H).get_json()
        self.assertIsNotNone(me['pending_offer'])
        self.assertEqual(code, me['pending_offer']['code'])

    def test_claim_success_grants_l2(self):
        uid = self._uid('CLAIM-')
        code = self._make_offer_api(uid)
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.assertEqual(200, r.status_code)
        self.assertEqual('l2', r.get_json()['level'])

    def test_claim_bad_code_400(self):
        uid = self._uid('BAD-')
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': 'NOPE'}, headers=H)
        self.assertEqual(400, r.status_code)
        self.assertEqual('claim_invalid_code', r.get_json()['error_code'])

    def test_claim_wrong_device_403(self):
        owner = self._uid('OWN-')
        other = self._uid('OTH-')
        code = self._make_offer_api(owner)
        r = self.client.post('/l2/claim', json={'user_id': other, 'code': code}, headers=H)
        self.assertEqual(403, r.status_code)
        self.assertEqual('claim_wrong_device', r.get_json()['error_code'])

    def test_claim_expired_409(self):
        uid = self._uid('EXP-')
        code = self._make_offer_api(uid)
        self.cur.execute("UPDATE l2_offers SET expires_at=NOW()-INTERVAL '1 hour' WHERE code=%s", (code,))
        self.c.commit()
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.assertEqual(409, r.status_code)
        self.assertEqual('claim_expired', r.get_json()['error_code'])

    def test_claim_seats_full_409(self):
        uid = self._uid('FULL-')
        code = self._make_offer_api(uid)
        # Now slam the cap down to current seats → full.
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._seats_now(),))
        self.c.commit()
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.assertEqual(409, r.status_code)
        self.assertEqual('claim_seats_full', r.get_json()['error_code'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
