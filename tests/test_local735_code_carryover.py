#!/usr/bin/env python3
"""test_local735_code_carryover.py — LOCAL-735 / D703 code-switch carry-over.

Michael (2026-10-22): a code redeemed while a paid pack is active must NOT wipe
what is left — it carries over with the SAME rules as a purchase (LOCAL-733).
Before LOCAL-735, level_codes.claim_level_code hard-reset fresh_used/edits_used/
ops_used to zero on every l3/l4 switch, so a code to Curator thrown while a $10
Pack still had units left silently destroyed them (this broke D703).

The fix reuses entitlements_api._carry_over_used (the single LOCAL-733
implementation) via a carry_over callback injected by the /l2/claim route — the
framework-free level_codes module never copies that logic.

Headline case (the ticket): $10 Pack (l3) with 3 units left + a code to Curator
(l4) → 25 + 3 = 28 ops. Plus:
  * same paid level by code (l3 with 3 fresh + 1 edit left + l3 code) ADDS;
  * a code to Introduction / Free / tester still starts fresh (today's rule);
  * an EXPIRED pack + a paid code starts fresh (no carry-over);
  * RED test: the pre-LOCAL-735 hard reset would give 25 ops, not 28.

Exercises the self-contained entitlements blueprint via Flask's test client
against audiotours_test, the SAME harness/isolation as test_local604_plan.py and
test_local733_pack_carryover.py.

Run: python3 -m pytest tests/test_local735_code_carryover.py -q
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
os.environ["GATEWAY_API_KEY"] = "test-key-735"
os.environ["IAP_VERIFY_MODE"] = "stub"

import psycopg2
from flask import Flask
import entitlements_api as ea
import level_codes

# [LOCAL-676] throwaway-schema isolation — clone the tables this suite touches
# into a private schema, prove public unchanged in teardown.
from _isolated_db import IsolatedSchema

_ISO = IsolatedSchema(
    prefix="t735code",
    clone_tables=["plans", "device_entitlement", "purchases", "level_codes"],
    proof_tables=["device_entitlement", "purchases", "level_codes"],
    db_url=_DB_URL,
    banner="LOCAL-735-code-carryover",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


API_KEY = "test-key-735"
H = {"X-API-Key": API_KEY}


def _conn():
    return psycopg2.connect(_DB_URL)


def _ensure_schema():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 012 creates plans/device_entitlement/purchases; 016 adds level_codes.
    for path in ('012_subscription_levels.sql', '016_plan_display_level_codes.sql'):
        with open(os.path.join(here, 'migration', 'sql', path)) as f:
            sql = f.read()
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute(sql)
            c.commit()
        finally:
            c.close()


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class CodeCarryBase(unittest.TestCase):
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
        self.uid = 'CARRY735-' + uuid.uuid4().hex[:10]
        self.hashes = []

    def tearDown(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM purchases WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s",
                            (self.uid,))
                for h in self.hashes:
                    cur.execute("DELETE FROM level_codes WHERE code_hash = %s", (h,))
            c.commit()
        finally:
            c.close()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _buy(self, product):
        tx = 'TX735-' + uuid.uuid4().hex[:12]
        r = self.client.post('/purchases/verify', json={
            'store': 'stub', 'transaction_id': tx,
            'product': product, 'user_id': self.uid}, headers=H)
        return tx, r

    def _make_level_code(self, level):
        code = level_codes.generate_code()
        h = level_codes.hash_code(code)
        self.hashes.append(h)
        c = _conn()
        try:
            with c.cursor() as cur:
                level_codes.store_code_hash(cur, h, level)
            c.commit()
        finally:
            c.close()
        return code, h

    def _claim(self, code):
        return self.client.post('/l2/claim',
                                json={'user_id': self.uid, 'code': code}, headers=H)

    def _set_used(self, fresh=None, edits=None, ops=None):
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
        return self.client.get(
            f'/entitlements/me?user_id={self.uid}', headers=H).get_json()


class TestCodeToCuratorCarriesOver(CodeCarryBase):
    def test_l3_pack_with_3_left_plus_curator_code_gives_25_plus_3_ops(self):
        # $10 Pack: 5 fresh, 5 edits. Consume to leave 3 UNITS total
        # (2 fresh + 1 edit), matching the ticket's "$10 Pack with 3 left".
        _, r = self._buy('l3_pack_10')
        self.assertEqual(200, r.status_code, r.get_json())
        self._set_used(fresh=3, edits=4)   # 2 fresh + 1 edit = 3 units left
        me0 = self._me()
        self.assertEqual('l3', me0['level'])
        self.assertEqual(2, me0['allowances_left']['fresh_left'])
        self.assertEqual(1, me0['allowances_left']['edits_left'])

        # Redeem a Curator (l4) level code while the pack is active.
        code, _ = self._make_level_code('l4')
        rc = self._claim(code)
        self.assertEqual(200, rc.status_code, rc.get_json())
        j = rc.get_json()
        self.assertEqual('l4', j['level'])
        self.assertEqual('level_code', j['claim_kind'])
        # l3 -> l4 converts fresh_left + edits_left 1:1 into ops: 25 + 3 = 28.
        self.assertEqual(28, j['allowances_left']['ops_left'])
        self.assertNotIn('fresh_left', j['allowances_left'])

    def test_me_reports_the_carried_ops_after_the_code_switch(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)   # 3 units left
        code, _ = self._make_level_code('l4')
        self._claim(code)
        me = self._me()
        self.assertEqual('l4', me['level'])
        self.assertEqual(28, me['allowances_left']['ops_left'])


class TestSamePaidLevelByCodeAdds(CodeCarryBase):
    def test_l3_code_while_active_l3_pack_adds(self):
        # $10 Pack with 3 fresh + 1 edit left, then an l3 code -> 8 fresh, 6 edits.
        self._buy('l3_pack_10')
        self._set_used(fresh=2, edits=4)   # 3 fresh, 1 edit left
        code, _ = self._make_level_code('l3')
        j = self._claim(code).get_json()
        self.assertEqual('l3', j['level'])
        self.assertEqual(8, j['allowances_left']['fresh_left'])
        self.assertEqual(6, j['allowances_left']['edits_left'])


class TestFreeTierCodesStartFresh(CodeCarryBase):
    def test_code_to_introduction_clears_the_pack(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)
        code, _ = self._make_level_code('l1')
        j = self._claim(code).get_json()
        self.assertEqual('l1', j['level'])
        # Introduction has no pack window and no pack allowances.
        self.assertIsNone(j['anniversary_at'])

    def test_code_to_free_clears_the_pack(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)
        code, _ = self._make_level_code('l2')
        j = self._claim(code).get_json()
        self.assertEqual('l2', j['level'])
        self.assertIsNone(j['anniversary_at'])

    def test_code_to_tester_clears_the_pack(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)
        code, _ = self._make_level_code('tester')
        j = self._claim(code).get_json()
        self.assertEqual('tester', j['level'])
        self.assertIsNone(j['anniversary_at'])


class TestExpiredPackStartsFresh(CodeCarryBase):
    def test_expired_l3_pack_plus_curator_code_does_not_carry(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)   # would be 3 units if active
        self._expire()                     # now >= anniversary_at
        code, _ = self._make_level_code('l4')
        j = self._claim(code).get_json()
        self.assertEqual('l4', j['level'])
        self.assertEqual(25, j['allowances_left']['ops_left'])  # fresh, not 28


class TestNoPriorPackStartsFresh(CodeCarryBase):
    def test_introduction_device_plus_curator_code_starts_fresh(self):
        # A brand-new device (l1, no pack) redeeming a Curator code: 25 ops, no carry.
        code, _ = self._make_level_code('l4')
        j = self._claim(code).get_json()
        self.assertEqual('l4', j['level'])
        self.assertEqual(25, j['allowances_left']['ops_left'])


class TestRedAgainstOldReset(CodeCarryBase):
    """RED test: the pre-LOCAL-735 claim_level_code hard-reset the counters to
    0/0/0 on every l3/l4 switch, so the Curator code would have landed on 25
    ops, NOT 28. This test fails against that old reset and passes only with the
    carry-over."""

    def test_curator_code_carry_over_beats_the_old_hard_reset(self):
        self._buy('l3_pack_10')
        self._set_used(fresh=3, edits=4)   # 3 units left
        code, _ = self._make_level_code('l4')
        j = self._claim(code).get_json()
        ops = j['allowances_left']['ops_left']
        self.assertNotEqual(25, ops,
                            "old hard reset would give 25 — carry-over must add the 3 left")
        self.assertEqual(28, ops)


if __name__ == '__main__':
    unittest.main(verbosity=2)
