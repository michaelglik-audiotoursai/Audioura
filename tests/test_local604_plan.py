#!/usr/bin/env python3
"""test_local604_plan.py — LOCAL-604 plan-page server behaviour.

Drives the user-api entitlements blueprint via Flask's test client against
audiotours_test. Covers Michael's plan-page requests + the LEAD rulings (D619):

  * hidden levels (tester, admin) are NOT returned in /entitlements/me levels;
  * the visible levels carry the right display names, in plan order;
  * the queue email is stored on join and NULLED on claim, leave and expiry;
  * the offer TTL is 10 MINUTES (migration 016 / l2_settings.offer_ttl_minutes);
  * /l2/claim routes all THREE code kinds (level code, queue offer, referral);
  * a level code switches to EVERY level, including tester and admin;
  * a l3/l4 level code starts a test pack (anniversary set);
  * a REVOKED level code is refused with 403 level_code_revoked;
  * level codes store HASHES ONLY (the table has no plaintext column).

Run: python3 -m pytest tests/test_local604_plan.py -q
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
os.environ["GATEWAY_API_KEY"] = "test-key-604"
os.environ.setdefault("EMAIL_MODE", "log")

import psycopg2
from flask import Flask
import entitlements_api as ea
import l2_seats
import level_codes

API_KEY = "test-key-604"
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


def _ensure_referral_tables(conn):
    """Create the referral tables the engine uses (mirrors referral_engine)."""
    with conn.cursor() as cur:
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
    conn.commit()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _apply_migration('012_subscription_levels.sql')
        _apply_migration('014_admin_level.sql')
        _apply_migration('015_l2_seats_queue.sql')
        _apply_migration('016_plan_display_level_codes.sql')
        app = Flask(__name__)
        app.register_blueprint(ea.entitlements_bp)
        cls.client = app.test_client()

    def setUp(self):
        self.ids = []
        self.hashes = []
        self.ref_codes = []
        self.c = _conn()
        self.cur = self.c.cursor()
        _ensure_referral_tables(self.c)
        self.cur.execute("SELECT seat_cap FROM plans WHERE plan_id='l2'")
        self._cap0 = self.cur.fetchone()[0]
        self.c.commit()

    def tearDown(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'", (self._cap0,))
        for code in self.ref_codes:
            self.cur.execute("DELETE FROM referral_redemptions WHERE referral_code=%s", (code,))
            self.cur.execute("DELETE FROM referral_codes WHERE code=%s", (code,))
        for u in self.ids:
            self.cur.execute("DELETE FROM referral_redemptions WHERE new_user_id=%s", (u,))
            self.cur.execute("DELETE FROM l2_offers WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM l2_queue WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM purchases WHERE user_id=%s", (u,))
            self.cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (u,))
        for h in self.hashes:
            self.cur.execute("DELETE FROM level_codes WHERE code_hash=%s", (h,))
        self.c.commit()
        self.cur.close()
        self.c.close()

    def _uid(self, tag=''):
        u = 'LOCAL604-' + tag + uuid.uuid4().hex[:8]
        self.ids.append(u)
        return u

    def _make_level_code(self, level):
        """Create a level code, return the plaintext (hash tracked for cleanup)."""
        code = level_codes.generate_code()
        h = level_codes.hash_code(code)
        self.hashes.append(h)
        with self.c.cursor() as cc:
            level_codes.store_code_hash(cc, h, level)
        self.c.commit()
        return code, h

    def _me(self, uid):
        return self.client.get(f'/entitlements/me?user_id={uid}', headers=H).get_json()

    def _free_a_seat(self):
        self.cur.execute("UPDATE plans SET seat_cap=%s WHERE plan_id='l2'",
                         (l2_seats.seats_in_use(self.cur) + 5,))
        self.c.commit()

    def _make_offer(self, uid, email=None):
        self._free_a_seat()
        self.client.post('/l2/queue/join', json={'user_id': uid, 'email': email}, headers=H)
        offered = l2_seats.offer_free_seats(self.cur)
        self.c.commit()
        return dict(offered).get(uid)


# ───────────────────────────────────────────────────────────────────────────
# /entitlements/me — display names + hidden levels
# ───────────────────────────────────────────────────────────────────────────
class TestVisibleLevels(Base):
    def test_me_returns_only_visible_levels_in_order(self):
        uid = self._uid('VIS-')
        me = self._me(uid)
        ids = [l['plan_id'] for l in me['levels']]
        self.assertEqual(['l1', 'l2', 'l3', 'l4'], ids)

    def test_hidden_levels_never_returned(self):
        uid = self._uid('HID-')
        me = self._me(uid)
        ids = [l['plan_id'] for l in me['levels']]
        self.assertNotIn('tester', ids)
        self.assertNotIn('admin', ids)

    def test_display_names_are_correct(self):
        uid = self._uid('NAME-')
        me = self._me(uid)
        names = {l['plan_id']: l['display_name'] for l in me['levels']}
        self.assertEqual('Introduction', names['l1'])
        self.assertEqual('Free', names['l2'])
        self.assertEqual('$10 Pack', names['l3'])
        self.assertEqual('Curator', names['l4'])

    def test_current_display_name_in_payload(self):
        uid = self._uid('CUR-')
        me = self._me(uid)  # new device defaults to l1
        self.assertEqual('Introduction', me['display_name'])

    def test_curator_can_sell_and_pack_curator_referrals(self):
        uid = self._uid('SELL-')
        me = self._me(uid)
        by = {l['plan_id']: l for l in me['levels']}
        self.assertTrue(by['l4']['can_sell'])
        self.assertFalse(by['l1']['can_sell'])
        self.assertGreater(by['l3']['referrals_allowed'], 0)
        self.assertGreater(by['l4']['referrals_allowed'], 0)


# ───────────────────────────────────────────────────────────────────────────
# Level codes: switch to every level, pack start, reusable, revoke, hashes-only
# ───────────────────────────────────────────────────────────────────────────
class TestLevelCodes(Base):
    def test_level_code_switches_to_every_level(self):
        for level in ('l1', 'l2', 'l3', 'l4', 'tester', 'admin'):
            uid = self._uid(f'SW-{level}-')
            code, _ = self._make_level_code(level)
            r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
            self.assertEqual(200, r.status_code, (level, r.get_json()))
            j = r.get_json()
            self.assertEqual(level, j['level'], (level, j))
            self.assertEqual('level_code', j['claim_kind'])
            self.assertEqual(level, j['granted_level'])

    def test_level_code_l3_l4_starts_test_pack(self):
        for level in ('l3', 'l4'):
            uid = self._uid(f'PACK-{level}-')
            code, _ = self._make_level_code(level)
            j = self.client.post('/l2/claim', json={'user_id': uid, 'code': code},
                                 headers=H).get_json()
            self.assertIsNotNone(j['anniversary_at'], (level, j))
            # A purchases row records the switch with store='level_code'.
            self.cur.execute(
                "SELECT store FROM purchases WHERE user_id=%s ORDER BY id DESC LIMIT 1", (uid,))
            self.assertEqual('level_code', self.cur.fetchone()[0])

    def test_level_code_is_reusable(self):
        uid = self._uid('REUSE-')
        code, h = self._make_level_code('admin')
        self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.client.post('/l2/claim', json={'user_id': uid, 'code': 'AUD-' + 'this is wrong'}, headers=H)
        self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.cur.execute("SELECT uses FROM level_codes WHERE code_hash=%s", (h,))
        self.assertEqual(2, self.cur.fetchone()[0])

    def test_revoked_level_code_refused_403(self):
        uid = self._uid('REV-')
        code, h = self._make_level_code('l4')
        with self.c.cursor() as cc:
            level_codes.revoke_code_hash(cc, h)
        self.c.commit()
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.assertEqual(403, r.status_code)
        self.assertEqual('level_code_revoked', r.get_json()['error_code'])

    def test_level_codes_store_hashes_only(self):
        self.cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'level_codes'
        """)
        cols = {r[0] for r in self.cur.fetchall()}
        # The only code-bearing column is the hash. No plaintext column exists.
        self.assertIn('code_hash', cols)
        self.assertNotIn('code', cols)
        self.assertNotIn('plaintext', cols)
        self.assertNotIn('plain_code', cols)

    def test_level_code_hash_is_sha256_of_the_plaintext(self):
        import hashlib
        code, h = self._make_level_code('l2')
        canon = level_codes.normalise_code(code)
        self.assertEqual(hashlib.sha256(canon.encode()).hexdigest(), h)
        self.assertEqual(64, len(h))


# ───────────────────────────────────────────────────────────────────────────
# Queue email: stored on join, nulled on claim / leave / expiry
# ───────────────────────────────────────────────────────────────────────────
class TestQueueEmail(Base):
    def _email(self, uid):
        self.cur.execute("SELECT email FROM l2_queue WHERE user_id=%s", (uid,))
        row = self.cur.fetchone()
        return row[0] if row else None

    def test_email_stored_on_join(self):
        uid = self._uid('EJOIN-')
        self.client.post('/l2/queue/join',
                         json={'user_id': uid, 'email': 'a@example.com'}, headers=H)
        self.cur.execute("SELECT email FROM l2_queue WHERE user_id=%s", (uid,))
        self.assertEqual('a@example.com', self.cur.fetchone()[0])

    def test_email_nulled_on_claim(self):
        uid = self._uid('ECLAIM-')
        code = self._make_offer(uid, email='b@example.com')
        self.assertIsNotNone(code)
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': code}, headers=H)
        self.assertEqual(200, r.status_code)
        self.cur.execute("SELECT email, status FROM l2_queue WHERE user_id=%s", (uid,))
        email, status = self.cur.fetchone()
        self.assertIsNone(email)
        self.assertEqual('claimed', status)

    def test_email_nulled_on_leave(self):
        uid = self._uid('ELEAVE-')
        self.client.post('/l2/queue/join',
                         json={'user_id': uid, 'email': 'c@example.com'}, headers=H)
        self.client.post('/l2/queue/leave', json={'user_id': uid}, headers=H)
        self.cur.execute("SELECT email, status FROM l2_queue WHERE user_id=%s", (uid,))
        email, status = self.cur.fetchone()
        self.assertIsNone(email)
        self.assertEqual('left', status)

    def test_email_nulled_on_expiry(self):
        uid = self._uid('EEXP-')
        code = self._make_offer(uid, email='d@example.com')
        self.assertIsNotNone(code)
        # Force the offer past its TTL, then run the expiry primitive.
        self.cur.execute("UPDATE l2_offers SET expires_at = NOW() - INTERVAL '1 minute' WHERE code=%s", (code,))
        self.c.commit()
        l2_seats.expire_offers(self.cur)
        self.c.commit()
        self.cur.execute("SELECT email FROM l2_queue WHERE user_id=%s", (uid,))
        self.assertIsNone(self.cur.fetchone()[0])


# ───────────────────────────────────────────────────────────────────────────
# Offer TTL is 10 minutes (migration 016)
# ───────────────────────────────────────────────────────────────────────────
class TestOfferTtl(Base):
    def test_offer_ttl_is_ten_minutes(self):
        uid = self._uid('TTL-')
        code = self._make_offer(uid, email='t@example.com')
        self.assertIsNotNone(code)
        self.cur.execute(
            "SELECT EXTRACT(EPOCH FROM (expires_at - offered_at))/60 FROM l2_offers WHERE code=%s",
            (code,))
        minutes = float(self.cur.fetchone()[0])
        self.assertAlmostEqual(10.0, minutes, delta=0.5)

    def test_settings_report_ten_minutes(self):
        s = l2_seats.get_settings(self.cur)
        self.assertEqual(10, s['offer_ttl_minutes'])


# ───────────────────────────────────────────────────────────────────────────
# Claim routes all three code kinds
# ───────────────────────────────────────────────────────────────────────────
class TestClaimRouting(Base):
    def test_claim_routes_level_code(self):
        uid = self._uid('RK-LC-')
        code, _ = self._make_level_code('l4')
        j = self.client.post('/l2/claim', json={'user_id': uid, 'code': code},
                             headers=H).get_json()
        self.assertEqual('level_code', j['claim_kind'])
        self.assertEqual('l4', j['level'])

    def test_claim_routes_queue_offer(self):
        uid = self._uid('RK-OF-')
        code = self._make_offer(uid, email='o@example.com')
        j = self.client.post('/l2/claim', json={'user_id': uid, 'code': code},
                             headers=H).get_json()
        self.assertEqual('offer', j['claim_kind'])
        self.assertEqual('l2', j['level'])

    def test_claim_routes_referral(self):
        # A referrer at l3 (3 lifetime invitations) with a referral code.
        referrer = self._uid('RK-REFR-')
        self.cur.execute(
            "INSERT INTO device_entitlement (user_id, level) VALUES (%s, 'l3')", (referrer,))
        ref_code = 'R' + uuid.uuid4().hex[:5].upper()
        self.ref_codes.append(ref_code)
        self.cur.execute(
            "INSERT INTO referral_codes (code, referrer_user_id) VALUES (%s, %s)",
            (ref_code, referrer))
        self.c.commit()
        self._free_a_seat()
        redeemer = self._uid('RK-RE-')
        r = self.client.post('/l2/claim', json={'user_id': redeemer, 'code': ref_code}, headers=H)
        self.assertEqual(200, r.status_code, r.get_json())
        j = r.get_json()
        self.assertEqual('referral', j['claim_kind'])
        self.assertEqual('l2', j['level'])

    def test_claim_unknown_code_400(self):
        uid = self._uid('RK-BAD-')
        r = self.client.post('/l2/claim', json={'user_id': uid, 'code': 'NOTACODE'}, headers=H)
        self.assertEqual(400, r.status_code)
        self.assertEqual('claim_invalid_code', r.get_json()['error_code'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
