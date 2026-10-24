#!/usr/bin/env python3
"""test_local753_member_translate.py — LOCAL-753 / D707 (RED first).

DECISION D707 (LEAD 2026-10-23): a MEMBER may translate a community tour.
Translation is not an edit (editing stays organiser-only, LOCAL-745); the
member chooses a language from the community page (or Listen → ⋮ → Translate)
and the result becomes part of the community (inherits community_id /
community_visibility, LOCAL-752 A1) so every member can download it free.

This UNDOES LOCAL-752 A3, which refused a member with 403 NOT_COMMUNITY_OWNER.
The new rule for TranslationService._community_translate_block(cursor, tour_id,
user_id):

  * ordinary tour (no community_id / columns absent)   → None  (anyone may);
  * community tour, caller is the OWNER                 → None  (allowed);
  * community tour, caller is an ACTIVE MEMBER          → None  (allowed, D707);
  * community tour, caller is NOT a member / expired    → (403, NOT_COMMUNITY_MEMBER);
  * community tour, NO user_id                          → (401, USER_ID_REQUIRED).

Membership is read the same way map_delivery._is_active_member reads it: a
community_memberships row with NULL (perpetual) or future expires_at, or the
owner. Hermetic: a scripted fake cursor, no Postgres. boto3 is stubbed so the
module imports off the service container.

Run: python3 -m pytest tests/test_local753_member_translate.py -q
"""
import datetime
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TRDIR = os.path.join(_ROOT, "translation-service")
if _TRDIR not in sys.path:
    sys.path.insert(0, _TRDIR)


class _FakeCursor:
    """communities: id→owner_user_id (disabled False).
    tours: id→community_id (None for ordinary).
    memberships: (user_id, community_id)→expires_at (None = perpetual,
                 datetime = explicit expiry)."""

    def __init__(self, communities, tours, memberships):
        self.communities = communities
        self.tours = tours
        self.memberships = memberships
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split()).lower()
        params = params or ()
        if "information_schema" in s:
            self._rows = [(1,)]  # community_id column present
            return
        if "community_id from audio_tours" in s and "where id" in s:
            (tid,) = params
            cid = self.tours.get(int(tid))
            self._rows = [(cid,)]
            return
        if "owner_user_id" in s and "from communities" in s:
            (cid,) = params
            owner = self.communities.get(int(cid))
            self._rows = [(owner, False)] if owner is not None else []
            return
        if "expires_at from community_memberships" in s:
            uid, cid = params
            key = (str(uid), int(cid))
            if key in self.memberships:
                self._rows = [(self.memberships[key],)]
            else:
                self._rows = []
            return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class MemberMayTranslateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "boto3" not in sys.modules:
            _boto3 = types.ModuleType("boto3")
            _boto3.client = lambda *a, **k: object()
            sys.modules["boto3"] = _boto3
        import translation_service as tr
        cls.tr = tr
        cls.svc = tr.TranslationService.__new__(tr.TranslationService)

    def _cur(self):
        future = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        return _FakeCursor(
            communities={10: "owner-10"},
            tours={736: 10, 500: None},
            memberships={
                ("member-free", 10): None,     # perpetual (free community)
                ("member-paid", 10): future,   # active paid pass
                ("member-expired", 10): past,  # expired pass
            },
        )

    def test_active_member_may_translate(self):
        decision = self.svc._community_translate_block(
            self._cur(), 736, "member-free")
        self.assertIsNone(
            decision,
            "an ACTIVE member must be allowed to translate a community tour "
            "(D707 undoes the 752 A3 member-403).")
        decision = self.svc._community_translate_block(
            self._cur(), 736, "member-paid")
        self.assertIsNone(decision, "a paid active member must be allowed.")

    def test_owner_may_translate(self):
        decision = self.svc._community_translate_block(
            self._cur(), 736, "owner-10")
        self.assertIsNone(decision, "the organiser must be allowed to translate.")

    def test_non_member_is_forbidden(self):
        decision = self.svc._community_translate_block(
            self._cur(), 736, "stranger")
        self.assertIsNotNone(decision, "a non-member must be refused.")
        status, body = decision
        self.assertEqual(status, 403)

    def test_expired_member_is_forbidden(self):
        decision = self.svc._community_translate_block(
            self._cur(), 736, "member-expired")
        self.assertIsNotNone(decision, "an expired member must be refused.")
        status, _body = decision
        self.assertEqual(status, 403)

    def test_ordinary_tour_translatable_by_anyone(self):
        decision = self.svc._community_translate_block(self._cur(), 500, "anyone")
        self.assertIsNone(decision, "an ordinary tour must stay translatable.")

    def test_missing_user_id_on_community_tour_is_401(self):
        decision = self.svc._community_translate_block(self._cur(), 736, None)
        self.assertIsNotNone(decision)
        status, body = decision
        self.assertEqual(status, 401)
        self.assertEqual(body.get("error_code"), "USER_ID_REQUIRED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
