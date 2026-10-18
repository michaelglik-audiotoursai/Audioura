#!/usr/bin/env python3
"""test_local710b_community_tours_payload.py — LOCAL-710B / D672 addendum 1.

Proves the server community payload now carries the community's own tours, so
the app's invite screen can offer a "Tour to include" picker and the invite's
tour line can default to the latest tour.

Hermetic (a scripted fake cursor, no Postgres, writes NO rows — the same style
as test_local701_community_tours.py Part A). Asserts:

  * _tours_for returns rows shaped {id, name, stop_count, created_at};
  * the SQL filters on community_id, excludes drafts, and orders NEWEST FIRST
    (created_at DESC, id DESC);
  * owner MP3/RSS episodes (community_episodes) are NOT consulted;
  * _community_page includes a 'tours' key built from _tours_for.

Run: python3 -m pytest tests/test_local710b_community_tours_payload.py -q
"""
import os
import sys
import datetime
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_ROOT, _UT):
    if p not in sys.path:
        sys.path.insert(0, p)

import communities_api as ca  # noqa: E402  (user-tracking/communities_api.py)


class _ToursCursor:
    """Captures the SQL of the single _tours_for query and returns scripted
    audio_tours rows (newest first, as the DB's ORDER BY would)."""

    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())  # normalise whitespace
        self.last_params = params

    def fetchall(self):
        return list(self._rows)


class ToursForTest(unittest.TestCase):
    def test_shape_and_newest_first(self):
        # DB would return newest first; we feed rows in that order.
        rows = [
            (12, "Beacon Hill, Boston MA - Walking Tour", 4,
             datetime.datetime(2026, 10, 18, 9, 0, 0)),
            (7, "Faneuil Hall Marketplace - Walking Tour", 3,
             datetime.datetime(2026, 10, 1, 9, 0, 0)),
        ]
        cur = _ToursCursor(rows)
        out = ca._tours_for(cur, 2)

        # Row shape.
        self.assertEqual(out, [
            {'id': 12, 'name': 'Beacon Hill, Boston MA - Walking Tour',
             'stop_count': 4, 'created_at': '2026-10-18T09:00:00'},
            {'id': 7, 'name': 'Faneuil Hall Marketplace - Walking Tour',
             'stop_count': 3, 'created_at': '2026-10-01T09:00:00'},
        ])
        # Newest first is preserved (the first row is the most recent).
        self.assertEqual(out[0]['id'], 12)

    def test_query_filters_community_excludes_drafts_orders_desc(self):
        cur = _ToursCursor([])
        ca._tours_for(cur, 42)
        sql = cur.last_sql.lower()
        self.assertIn("from audio_tours", sql)
        self.assertIn("where community_id = %s", sql)
        self.assertIn("draft", sql)  # drafts excluded
        self.assertIn("order by created_at desc", sql)
        self.assertEqual(cur.last_params, (42,))
        # Owner episodes table is never consulted by the tours query.
        self.assertNotIn("community_episodes", sql)

    def test_empty_when_no_tours(self):
        self.assertEqual(ca._tours_for(_ToursCursor([]), 1), [])

    def test_null_created_at(self):
        cur = _ToursCursor([(5, "Untimed tour", 0, None)])
        out = ca._tours_for(cur, 1)
        self.assertEqual(out[0]['created_at'], None)


class CommunityPagePayloadTest(unittest.TestCase):
    def test_payload_includes_tours_from_tours_for(self):
        # Patch the leaf helpers _community_page depends on so we can run it
        # with a trivial cursor and assert ONLY the new 'tours' wiring.
        sentinel = [{'id': 99, 'name': 'X - Walking Tour',
                     'stop_count': 2, 'created_at': None}]
        originals = {}
        patches = {
            '_community_row': lambda cur, cid: {
                'id': cid, 'owner_user_id': 'owner', 'name': 'C',
                'description': None, 'organiser_name': None,
                'organiser_photo_url': None, 'organiser_bio': None,
                'organiser_contact': None, 'rules_text': None,
                'waiver_text': None, 'has_waiver': False, 'is_paid': True,
                'visibility': 'private', 'latitude': None, 'longitude': None,
                'disabled': False, 'status': ca.STATUS_ACTIVE,
                'stepped_down_at': None, 'archived_at': None,
                'join_code': 'FFush25U',
            },
            '_membership': lambda cur, uid, cid: None,
            '_passes_for': lambda cur, cid: [],
            '_episodes_for': lambda cur, cid: [],
            '_episode_count': lambda cur, cid: 0,
            '_active_member_count': lambda cur, cid, now=None: 0,
            '_launch_info': lambda c, cur=None, now=None: {},
            '_tours_for': lambda cur, cid: sentinel,
        }
        for name, fn in patches.items():
            originals[name] = getattr(ca, name)
            setattr(ca, name, fn)
        try:
            payload = ca._community_page(cur=object(), community_id=2,
                                         user_id='owner')
        finally:
            for name, fn in originals.items():
                setattr(ca, name, fn)

        self.assertIn('tours', payload)
        self.assertEqual(payload['tours'], sentinel)


if __name__ == "__main__":
    unittest.main()
