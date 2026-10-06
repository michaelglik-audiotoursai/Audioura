#!/usr/bin/env python3
"""test_local595_api.py — LOCAL-595 user-api endpoints + transaction replay.

Exercises the self-contained entitlements blueprint via Flask's test client
against audiotours_test. Verifies auth, /entitlements/me, /app-open, /lapse,
and /purchases/verify including the idempotent-replay guard.

Run: python3 -m pytest tests/test_local595_api.py -q
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
os.environ["GATEWAY_API_KEY"] = "test-key-595"
os.environ["IAP_VERIFY_MODE"] = "stub"

import psycopg2
from flask import Flask
import entitlements_api as ea

API_KEY = "test-key-595"
H = {"X-API-Key": API_KEY}


def _conn():
    return psycopg2.connect(_DB_URL)


def _ensure_schema():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'migration', 'sql', '012_subscription_levels.sql')) as f:
        sql = f.read()
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()
    finally:
        c.close()


class ApiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_schema()
        app = Flask(__name__)
        app.register_blueprint(ea.entitlements_bp)
        cls.client = app.test_client()

    def setUp(self):
        self.uid = 'API595-' + uuid.uuid4().hex[:10]

    def tearDown(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM purchases WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s", (self.uid,))
            c.commit()
        finally:
            c.close()


class TestAuth(ApiTestBase):
    def test_me_requires_api_key(self):
        r = self.client.get(f'/entitlements/me?user_id={self.uid}')
        self.assertEqual(401, r.status_code)

    def test_verify_requires_api_key(self):
        r = self.client.post('/purchases/verify', json={})
        self.assertEqual(401, r.status_code)


class TestMeAndActivity(ApiTestBase):
    def test_me_new_device_is_l1(self):
        r = self.client.get(f'/entitlements/me?user_id={self.uid}', headers=H)
        self.assertEqual(200, r.status_code)
        j = r.get_json()
        self.assertEqual('l1', j['level'])
        self.assertFalse(j['renewal_prompt'])

    def test_app_open_records_and_returns_prompt(self):
        r = self.client.post('/entitlements/app-open', json={'user_id': self.uid}, headers=H)
        self.assertEqual(200, r.status_code)
        self.assertIn('renewal_prompt', r.get_json())

    def test_lapse_drops_to_l1(self):
        ea_resp = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': 'TX-' + uuid.uuid4().hex[:10],
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertEqual('l3', ea_resp.get_json()['granted_level'])
        r = self.client.post('/entitlements/lapse', json={'user_id': self.uid}, headers=H)
        self.assertEqual('l1', r.get_json()['level'])


class TestPurchaseVerify(ApiTestBase):
    def test_verify_grants_l3_with_anniversary_and_fresh(self):
        tx = 'TX-' + uuid.uuid4().hex[:10]
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertEqual(200, r.status_code)
        j = r.get_json()
        self.assertEqual('l3', j['granted_level'])
        self.assertIsNotNone(j['anniversary_at'])
        self.assertEqual(5, j['allowances_left']['fresh_left'])

    def test_verify_l4_grants_ops(self):
        tx = 'TX-' + uuid.uuid4().hex[:10]
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': 'l4_round_25', 'user_id': self.uid}, headers=H)
        j = r.get_json()
        self.assertEqual('l4', j['granted_level'])
        self.assertEqual(25, j['allowances_left']['ops_left'])

    def test_same_transaction_id_cannot_grant_twice(self):
        tx = 'TX-' + uuid.uuid4().hex[:10]
        first = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertEqual(200, first.status_code)
        replay = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertEqual(409, replay.status_code)
        self.assertEqual('already_verified', replay.get_json()['error'])

    def test_unknown_product_rejected(self):
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': 'TX-' + uuid.uuid4().hex[:10],
            'product': 'mystery_box', 'user_id': self.uid}, headers=H)
        self.assertEqual(400, r.status_code)

    def test_empty_transaction_rejected_by_stub(self):
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': '',
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertIn(r.status_code, (400, 402))


if __name__ == '__main__':
    unittest.main(verbosity=2)
