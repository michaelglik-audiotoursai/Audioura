#!/usr/bin/env python3
"""test_local745_organiser_only.py — LOCAL-745 requirement 2 (RED first).

Michael: "we should not allow anyone who is not the community organizer edit the
tours." A save/edit of a tour that carries audio_tours.community_id must be
refused (403) unless the editing user is the community's owner
(communities.owner_user_id). An ordinary (non-community) tour keeps today's
rule: anyone may edit.

The decision lives in a pure helper tour_editing_phase2._community_edit_block(
cur, tour_id, user_id) so the service and the test exercise the exact same code
without standing up Flask. It returns None when the edit is allowed, or a
(status_code, body) tuple (403 forbidden / 401 user_id_required) when refused.

DB-backed: creates its own community + tours + membership rows in audiotours_test
(pytest auto-selects the test DB; conftest blocks production writes) and removes
them in tearDown.

Run: python3 -m pytest tests/test_local745_organiser_only.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
os.environ.setdefault("DB_HOST", _cfg["host"])
os.environ.setdefault("DB_PORT", _cfg["port"])
os.environ.setdefault("DB_NAME", _cfg["dbname"])
os.environ.setdefault("DB_USER", _cfg["user"])
os.environ.setdefault("DB_PASSWORD", _cfg["password"])

import psycopg2
import tour_editing_phase2 as p2


def _conn():
    return psycopg2.connect(
        host=_cfg["host"], port=_cfg["port"], dbname=_cfg["dbname"],
        user=_cfg["user"], password=_cfg["password"],
    )


class OrganiserOnlyEditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = f"OWNER-{uuid.uuid4().hex[:8]}"
        cls.member = f"MEMBER-{uuid.uuid4().hex[:8]}"
        cls.conn = _conn()
        cls.conn.autocommit = True
        cur = cls.conn.cursor()

        cur.execute(
            "INSERT INTO communities (name, owner_user_id, disabled) "
            "VALUES (%s, %s, FALSE) RETURNING id",
            (f"L745 test {uuid.uuid4().hex[:6]}", cls.owner))
        cls.community_id = cur.fetchone()[0]

        # A community tour (tagged) and an ordinary tour (not tagged).
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, is_test, "
            "community_id, community_visibility) "
            "VALUES (%s, %s, TRUE, %s, 'members') RETURNING id",
            (f"L745 community tour {uuid.uuid4().hex[:6]}", "l745 req",
             cls.community_id))
        cls.community_tour_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, is_test) "
            "VALUES (%s, %s, TRUE) RETURNING id",
            (f"L745 ordinary tour {uuid.uuid4().hex[:6]}", "l745 req"))
        cls.ordinary_tour_id = cur.fetchone()[0]

        # An active (perpetual) membership for the member.
        cur.execute(
            "INSERT INTO community_memberships (user_id, community_id, expires_at) "
            "VALUES (%s, %s, NULL) ON CONFLICT DO NOTHING",
            (cls.member, cls.community_id))
        cur.close()

    @classmethod
    def tearDownClass(cls):
        cur = cls.conn.cursor()
        cur.execute("DELETE FROM community_memberships WHERE community_id = %s",
                    (cls.community_id,))
        cur.execute("DELETE FROM audio_tours WHERE id = ANY(%s) AND is_test = TRUE",
                    ([cls.community_tour_id, cls.ordinary_tour_id],))
        cur.execute("DELETE FROM communities WHERE id = %s", (cls.community_id,))
        cur.close()
        cls.conn.close()

    def test_member_editing_community_tour_is_forbidden(self):
        """A member (not the owner) editing a community tour → 403."""
        cur = self.conn.cursor()
        try:
            decision = p2._community_edit_block(
                cur, str(self.community_tour_id), self.member)
        finally:
            cur.close()
        self.assertIsNotNone(
            decision,
            "member editing a community tour was ALLOWED — it must be refused 403 "
            "(LOCAL-745 req 2).")
        status, body = decision
        self.assertEqual(status, 403)
        self.assertEqual(body.get("error_code"), "NOT_COMMUNITY_OWNER")

    def test_owner_editing_community_tour_is_allowed(self):
        """The community owner editing their community tour → allowed (None)."""
        cur = self.conn.cursor()
        try:
            decision = p2._community_edit_block(
                cur, str(self.community_tour_id), self.owner)
        finally:
            cur.close()
        self.assertIsNone(
            decision,
            "the community owner must be allowed to edit their own tour.")

    def test_ordinary_tour_edit_is_allowed_for_anyone(self):
        """A non-community tour keeps today's rule: anyone may edit."""
        cur = self.conn.cursor()
        try:
            decision = p2._community_edit_block(
                cur, str(self.ordinary_tour_id), self.member)
        finally:
            cur.close()
        self.assertIsNone(
            decision,
            "an ordinary (non-community) tour must stay editable by anyone.")


if __name__ == '__main__':
    unittest.main()
