#!/usr/bin/env python3
"""test_local595_edit_gate.py — LOCAL-595B defect 4.

The add-stops edit gate must FAIL CLOSED: an edit that adds stops with NO
user_id/secret_id in the body is refused with 401 user_id_required, never
silently allowed. A text-only edit (no action='add') stays free and ungated.

The decision lives in subscription_levels.evaluate_edit_add_stops — the same
pure helper tour_editing_phase2._bulk_save_core calls — so these tests exercise
the exact production path without importing Flask/boto3.

Run: python3 -m pytest tests/test_local595_edit_gate.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

import psycopg2
import subscription_levels as sl


def _conn():
    return psycopg2.connect(
        host=_cfg["host"], port=_cfg["port"], dbname=_cfg["dbname"],
        user=_cfg["user"], password=_cfg["password"],
    )


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


class TestEditGateFailClosed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_schema()

    def setUp(self):
        self.uid = 'L595E-' + uuid.uuid4().hex[:10]
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        c = _conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s", (self.uid,))
            c.commit()
        finally:
            c.close()

    # ─── fail-closed: no id on an add-stops edit ─────────────────────────────
    def test_add_stops_without_user_id_refuses_401(self):
        d = sl.evaluate_edit_add_stops({'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'add'}]})
        self.assertFalse(d['proceed'])
        self.assertEqual(401, d['status'])
        self.assertEqual('user_id_required', d['body']['error_code'])
        self.assertFalse(d['body']['allowed'])

    def test_add_stops_blank_user_id_refuses_401(self):
        d = sl.evaluate_edit_add_stops({'user_id': '   ', 'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'add'}]})
        self.assertFalse(d['proceed'])
        self.assertEqual(401, d['status'])
        self.assertEqual('user_id_required', d['body']['error_code'])

    def test_secret_id_alias_is_accepted_as_id(self):
        # secret_id is the device id alias; present it on an L1 device → the gate
        # runs (not a 401) and refuses with the level error instead.
        d = sl.evaluate_edit_add_stops({'secret_id': self.uid, 'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'add'}]})
        self.assertFalse(d['proceed'])
        self.assertEqual(429, d['status'])
        self.assertEqual('level_cannot_generate', d['body']['error_code'])

    # ─── text-only edits are never gated ─────────────────────────────────────
    def test_text_only_edit_without_user_id_is_not_gated(self):
        d = sl.evaluate_edit_add_stops({'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'modify'}]})
        self.assertTrue(d['proceed'])
        self.assertFalse(d['gated'])
        self.assertEqual(0, d['new_stops'])

    def test_no_stops_is_not_gated(self):
        d = sl.evaluate_edit_add_stops({'stops': []})
        self.assertTrue(d['proceed'])
        self.assertEqual(0, d['new_stops'])

    # ─── gate runs end-to-end when an id IS supplied ─────────────────────────
    def test_add_stops_with_l1_user_id_refused_level(self):
        d = sl.evaluate_edit_add_stops({'user_id': self.uid, 'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'add'}]})
        self.assertFalse(d['proceed'])
        self.assertEqual(429, d['status'])
        self.assertEqual('level_cannot_generate', d['body']['error_code'])

    def test_add_stops_with_l3_user_id_allowed(self):
        sl.grant_pack(self.uid, 'l3')
        d = sl.evaluate_edit_add_stops({'user_id': self.uid, 'stops': [
            {'stop_number': 1, 'text': 'A', 'action': 'add'}]})
        self.assertTrue(d['proceed'])
        self.assertTrue(d['gated'])
        self.assertEqual(1, d['new_stops'])
        self.assertEqual(self.uid, d['user_id'])

    def test_add_stops_over_l3_edit_ceiling_refused(self):
        sl.grant_pack(self.uid, 'l3')  # max_new_stops_per_edit = 10
        stops = [{'stop_number': i, 'text': 'x', 'action': 'add'} for i in range(11)]
        d = sl.evaluate_edit_add_stops({'user_id': self.uid, 'stops': stops})
        self.assertFalse(d['proceed'])
        self.assertEqual(429, d['status'])
        self.assertEqual('stops_over_plan', d['body']['error_code'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
