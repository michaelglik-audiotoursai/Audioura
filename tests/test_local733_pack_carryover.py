#!/usr/bin/env python3
"""test_local733_pack_carryover.py — LOCAL-733 / D703 pack carry-over.

A pack bought while the current pack is still active ADDS to what is left
(same level) or converts the remainder 1:1 into the new level's units
(different level). An expired pack or a first purchase starts fresh. Buying
the same transaction twice still grants once (idempotency unchanged).

Exercises the self-contained entitlements blueprint via Flask's test client
against audiotours_test, the SAME harness as test_local595_api.py:
  * same-level carry-over (3 fresh + 1 edit left, buy $10 Pack -> 8 fresh, 6 edits);
  * expired pack starts fresh (no carry-over);
  * l3 -> l4 conversion (fresh_left + edits_left become extra ops);
  * l4 -> l3 conversion (ops_left become extra fresh);
  * idempotent replay does not add twice;
  * /entitlements/me reports the new *_left;
  * RED test: with the OLD hard reset the same-level carry-over fails.

Run: python3 -m pytest tests/test_local733_pack_carryover.py -q
"""
import os
import sys
import uuid
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user-tracking'))

from db_connection import get_db_config

_cfg = get_db_config()
_DB_URL = (
    f"postgresql://{_cfg['user']}:{_cfg['password']}"
    f"@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}"
)
os.environ["DATABASE_URL"] = _DB_URL
os.environ["GATEWAY_API_KEY"] = "test-key-733"
os.environ["IAP_VERIFY_MODE"] = "stub"

import psycopg2
from flask import Flask
import entitlements_api as ea

# [LOCAL-676] throwaway-schema isolation, exactly as the 595 api suite: clone
# the three tables we touch into a private schema so sibling suites never
# perturb our counts, and prove public unchanged in teardown.
from _isolated_db import IsolatedSchema

_ISO = IsolatedSchema(
    prefix="t733carry",
    clone_tables=["plans", "device_entitlement", "purchases"],
    proof_tables=["device_entitlement", "purchases"],
    db_url=_DB_URL,
    banner="LOCAL-733-carryover",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


API_KEY = "test-key-733"
H = {"X-API-Key": API_KEY}


def _conn():
    return psycopg2.connect(_DB_URL)


def _ensure_schema():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'migration', 'sql',
                           '012_subscription_levels.sql')) as f:
        sql = f.read()
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()
    finally:
        c.close()


class CarryBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["GATEWAY_API_KEY"] = API_KEY
        ea.API_KEY = API_KEY
        os.environ["IAP_VERIFY_MODE"] = "stub"
        ea.IAP_VERIFY_MODE = "stub"
        _ensure_schema()
        app = Flask(__name__)
        app.register_blueprint(ea.entitlements_bp)
        cls.client = app.test_client()

    def setUp(self):
        self.uid = 'CARRY733-' + uuid.uuid4().hex[:10]

    def tearDown(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM purchases WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s",
                            (self.uid,))
            c.commit()
        finally:
            c.close()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _buy(self, product):
        tx = 'TX-' + uuid.uuid4().hex[:12]
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': product, 'user_id': self.uid}, headers=H)
        return tx, r

    def _set_used(self, fresh=None, edits=None, ops=None):
        """Directly set used counters to simulate consumption during the pack."""
        sets, vals = [], []
        for col, v in (('fresh_used', fresh), ('edits_used', edits),
                       ('ops_used', ops)):
            if v is not None:
                sets.append(f"{col} = %s")
                vals.append(v)
        if not sets:
            return
        vals.append(self.uid)
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    f"UPDATE device_entitlement SET {', '.join(sets)} "
                    f"WHERE user_id = %s", vals)
            c.commit()
        finally:
            c.close()

    def _expire(self):
        """Push the anniversary into the past so the current pack is expired."""
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE device_entitlement SET anniversary_at = %s "
                    "WHERE user_id = %s",
                    (datetime.utcnow() - timedelta(days=1), self.uid))
            c.commit()
        finally:
            c.close()

    def _me(self):
        r = self.client.get(f'/entitlements/me?user_id={self.uid}', headers=H)
        return r.get_json()


class TestSameLevelCarryOver(CarryBase):
    def test_same_level_pack_adds_to_what_is_left(self):
        # First $10 Pack: 5 fresh, 5 edits. Consume so 3 fresh + 1 edit remain.
        _, r1 = self._buy('l3_pack_10')
        self.assertEqual(200, r1.status_code, r1.get_json())
        self.assertEqual('l3', r1.get_json()['granted_level'])
        self._set_used(fresh=2, edits=4)  # 3 fresh left, 1 edit left
        # Confirm the starting point the member sees.
        me0 = self._me()
        self.assertEqual(3, me0['allowances_left']['fresh_left'])
        self.assertEqual(1, me0['allowances_left']['edits_left'])

        # Buy another $10 Pack while active -> ADD: 3+5=8 fresh, 1+5=6 edits.
        _, r2 = self._buy('l3_pack_10')
        self.assertEqual(200, r2.status_code, r2.get_json())
        left = r2.get_json()['allowances_left']
        self.assertEqual(8, left['fresh_left'])
        self.assertEqual(6, left['edits_left'])

    def test_me_reports_the_new_left_after_carry_over(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh, 1 edit left
        self._buy('l3_pack_10')            # +5/+5
        me = self._me()
        self.assertEqual(8, me['allowances_left']['fresh_left'])
        self.assertEqual(6, me['allowances_left']['edits_left'])

    def test_full_pack_bought_again_doubles(self):
        # Nothing consumed: 5 left + 5 new = 10.
        self._buy('l3_pack_10')
        _, r2 = self._buy('l3_pack_10')
        self.assertEqual(10, r2.get_json()['allowances_left']['fresh_left'])
        self.assertEqual(10, r2.get_json()['allowances_left']['edits_left'])


class TestExpiredStartsFresh(CarryBase):
    def test_expired_pack_does_not_carry_over(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh, 1 edit left
        self._expire()                     # now >= anniversary_at
        _, r2 = self._buy('l3_pack_10')
        left = r2.get_json()['allowances_left']
        self.assertEqual(5, left['fresh_left'])   # fresh, not 8
        self.assertEqual(5, left['edits_left'])   # fresh, not 6


class TestCrossLevelConversion(CarryBase):
    def test_l3_to_l4_converts_one_for_one_into_ops(self):
        # $10 Pack with 3 fresh + 1 edit left -> Curator: 4 carried ops + 25.
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh + 1 edit left = 4 units
        _, r2 = self._buy('l4_round_25')
        j = r2.get_json()
        self.assertEqual('l4', j['granted_level'])
        self.assertEqual(29, j['allowances_left']['ops_left'])  # 25 + 4
        # l4 has no fresh/edit allowance.
        self.assertNotIn('fresh_left', j['allowances_left'])

    def test_l4_to_l3_converts_ops_into_fresh(self):
        # Curator with 6 ops left -> $10 Pack: 6 carried fresh + 5, edits fresh.
        self._buy('l4_round_25')
        self._set_used(ops=19)             # 6 ops left
        _, r2 = self._buy('l3_pack_10')
        j = r2.get_json()
        self.assertEqual('l3', j['granted_level'])
        self.assertEqual(11, j['allowances_left']['fresh_left'])  # 5 + 6
        self.assertEqual(5, j['allowances_left']['edits_left'])   # fresh


class TestIdempotentReplay(CarryBase):
    def test_replayed_transaction_does_not_add_twice(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh, 1 edit left
        tx, r2 = self._buy('l3_pack_10')   # -> 8 fresh, 6 edits
        self.assertEqual(8, r2.get_json()['allowances_left']['fresh_left'])
        # Replay the SECOND transaction id: must 409 and not add again.
        replay = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': 'l3_pack_10', 'user_id': self.uid}, headers=H)
        self.assertEqual(409, replay.status_code)
        self.assertEqual('already_verified', replay.get_json()['error'])
        me = self._me()
        self.assertEqual(8, me['allowances_left']['fresh_left'])   # still 8
        self.assertEqual(6, me['allowances_left']['edits_left'])   # still 6


class TestRedAgainstOldReset(CarryBase):
    """RED test: proves the new behaviour. The OLD grant hard-reset the
    counters to zero on every purchase (fresh_used=0, edits_used=0), so a
    same-level repurchase landed on 5 fresh / 5 edits, NOT 8 / 6. This test
    fails against that old reset and passes only with the carry-over."""

    def test_carry_over_beats_the_old_hard_reset(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh, 1 edit left
        _, r2 = self._buy('l3_pack_10')
        left = r2.get_json()['allowances_left']
        # Old reset would give 5 / 5 here; carry-over gives 8 / 6.
        self.assertNotEqual(5, left['fresh_left'],
                            "old hard reset would give 5 — carry-over must add")
        self.assertEqual(8, left['fresh_left'])
        self.assertEqual(6, left['edits_left'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
