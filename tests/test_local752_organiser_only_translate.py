#!/usr/bin/env python3
"""test_local752_organiser_only_translate.py — LOCAL-752 A3 (RED first).

The organiser can translate a community tour from the Listen page (⋮ →
Translate) like any own tour; the result is part of the community (A1). Members
cannot — the organiser-only rule (LOCAL-745) extends to translation, and the
server enforces it with 403.

The decision is a pure helper in the translation service:
    TranslationService._community_translate_block(cursor, tour_id, user_id)
returning None when allowed, or a (status, body) tuple (403 NOT_COMMUNITY_OWNER
/ 401 USER_ID_REQUIRED) when refused. It mirrors tour_editing_phase2.
_community_edit_block but is self-contained in the translation service (its own
DB reads, schema-guarded), so it adds no cross-container import.

Rules:
  * an ORDINARY tour (no community_id, or columns absent)   → None (anyone may);
  * a community tour, user IS the owner                      → None;
  * a community tour, user is a member/stranger             → (403, NOT_COMMUNITY_OWNER);
  * a community tour, NO user_id                            → (401, USER_ID_REQUIRED).

Hermetic: a scripted fake cursor, no Postgres. Stubs boto3 so the module
imports off the service container.

Run: python3 -m pytest tests/test_local752_organiser_only_translate.py -q
"""
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
    """communities: id→owner_user_id (disabled False). tours: id→community_id."""

    def __init__(self, communities, tours):
        self.communities = communities
        self.tours = tours
        self._rows = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split()).lower()
        params = params or ()
        if "information_schema" in s:
            self._rows = [(1,)]  # COUNT(*) of community_id column = 1
            return
        if "select community_id from audio_tours" in s or \
           ("community_id" in s and "from audio_tours" in s and "where id" in s):
            (tid,) = params
            cid = self.tours.get(int(tid))
            self._rows = [(cid,)] if cid is not None else [(None,)]
            return
        if "owner_user_id" in s and "from communities" in s:
            (cid,) = params
            row = self.communities.get(int(cid))
            # (owner_user_id, disabled)
            self._rows = [(row, False)] if row is not None else []
            return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class OrganiserOnlyTranslateTest(unittest.TestCase):
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
        return _FakeCursor(communities={10: "owner-10"},
                           tours={736: 10, 500: None})

    def test_helper_exists(self):
        self.assertTrue(
            hasattr(self.svc, "_community_translate_block"),
            "_community_translate_block is missing — a member can translate a "
            "community tour, which must be refused 403 (LOCAL-752 A3).")

    def test_member_translating_community_tour_is_forbidden(self):
        decision = self.svc._community_translate_block(self._cur(), 736, "member-99")
        self.assertIsNotNone(
            decision,
            "a member translating a community tour was ALLOWED — must be 403.")
        status, body = decision
        self.assertEqual(status, 403)
        self.assertEqual(body.get("error_code"), "NOT_COMMUNITY_OWNER")

    def test_owner_translating_community_tour_is_allowed(self):
        decision = self.svc._community_translate_block(self._cur(), 736, "owner-10")
        self.assertIsNone(decision, "the organiser must be allowed to translate.")

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
