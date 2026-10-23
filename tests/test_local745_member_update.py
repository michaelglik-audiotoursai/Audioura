#!/usr/bin/env python3
"""test_local745_member_update.py — LOCAL-745 requirement 3 (RED first).

"Members get the edit": after the organiser edits a community tour, a member's
phone must get the new version. The member downloads a community tour by its
NUMERIC id from map-delivery (/download-tour/<id>), which serves
audio_tours.audio_tour; and the LOCAL-657 version the app shows comes from
audio_tour_versions (MAX(version_no)+1). So for the edit to reach members the
edit must be written back ONTO the community tour row in place — not minted as a
new, untagged tour — archiving the old content and bumping version_no.

tour_editing_phase2._replace_community_tour_in_place(cur, tour_id, new_zip_bytes,
new_stops_count) performs that in-place replacement. This test proves it:
  * the audio_tours.audio_tour BYTEA becomes the new ZIP bytes (what members
    download);
  * the previous content is archived in audio_tour_versions with version_no 1
    (so map-delivery reports version 2 next).

DB-backed; creates its own is_test community tour row in audiotours_test and
removes it (plus its version-archive rows) in tearDown. Never touches a non-test
row (D141).

Run: python3 -m pytest tests/test_local745_member_update.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
for k, v in (("DB_HOST", _cfg["host"]), ("DB_PORT", _cfg["port"]),
             ("DB_NAME", _cfg["dbname"]), ("DB_USER", _cfg["user"]),
             ("DB_PASSWORD", _cfg["password"])):
    os.environ.setdefault(k, v)

import psycopg2
import tour_editing_phase2 as p2


def _conn():
    return psycopg2.connect(
        host=_cfg["host"], port=_cfg["port"], dbname=_cfg["dbname"],
        user=_cfg["user"], password=_cfg["password"],
    )


class MemberUpdateInPlaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = _conn()
        cls.conn.autocommit = True
        cur = cls.conn.cursor()
        cur.execute(
            "INSERT INTO communities (name, owner_user_id, disabled) "
            "VALUES (%s, %s, FALSE) RETURNING id",
            (f"L745 mu {uuid.uuid4().hex[:6]}", f"OWNER-{uuid.uuid4().hex[:8]}"))
        cls.community_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, is_test, "
            "community_id, community_visibility, audio_tour, zip_filename, "
            "stops_count) VALUES (%s, %s, TRUE, %s, 'members', %s, %s, 4) "
            "RETURNING id",
            (f"L745 member-update {uuid.uuid4().hex[:6]}", "l745 req",
             cls.community_id, psycopg2.Binary(b"OLD-ZIP-BYTES"),
             "l745_old.zip"))
        cls.tour_id = cur.fetchone()[0]
        cur.close()

    @classmethod
    def tearDownClass(cls):
        cur = cls.conn.cursor()
        cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s",
                    (cls.tour_id,))
        cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                    (cls.tour_id,))
        cur.execute("DELETE FROM communities WHERE id = %s", (cls.community_id,))
        cur.close()
        cls.conn.close()

    def test_in_place_replace_updates_bytea_and_archives_old_version(self):
        new_bytes = b"NEW-EDITED-ZIP-BYTES"
        cur = self.conn.cursor()
        try:
            p2._replace_community_tour_in_place(
                cur, str(self.tour_id), new_bytes, new_stops_count=5,
                new_zip_filename="l745_new.zip")
            self.conn.commit()

            cur.execute(
                "SELECT audio_tour, zip_filename, stops_count "
                "FROM audio_tours WHERE id = %s", (self.tour_id,))
            audio_tour, zip_filename, stops_count = cur.fetchone()
            self.assertEqual(
                bytes(audio_tour), new_bytes,
                "members download audio_tours.audio_tour — it must now be the "
                "edited ZIP bytes.")
            self.assertEqual(zip_filename, "l745_new.zip")
            self.assertEqual(stops_count, 5)

            cur.execute(
                "SELECT version_no FROM audio_tour_versions "
                "WHERE tour_id = %s ORDER BY version_no", (self.tour_id,))
            versions = [r[0] for r in cur.fetchall()]
            self.assertIn(
                1, versions,
                "the superseded content must be archived as version_no 1 so "
                "map-delivery reports version 2 next (LOCAL-657).")
        finally:
            cur.close()


if __name__ == '__main__':
    unittest.main()
