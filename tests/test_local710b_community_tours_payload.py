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
    """Captures the SQL of the _tours_for query and returns scripted audio_tours
    rows (newest first, as the DB's ORDER BY would). [LOCAL-752 A2] _tours_for now
    also issues a per-row `_tour_languages` sub-query; this cursor answers it from
    an optional {tour_id: [languages after the original]} map."""

    def __init__(self, rows, translations=None):
        self._rows = rows
        self._translations = translations or {}
        self._result = None
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.last_sql = s
        self.last_params = params
        low = s.lower()
        # The per-tour finished-translation languages sub-query.
        if "where original_tour_id = %s" in low and "language" in low:
            (tour_id,) = params
            self._result = [(lang,) for lang in self._translations.get(tour_id, [])]
        else:
            # The main community-tours query.
            self._result = list(self._rows)

    def fetchall(self):
        return list(self._result if self._result is not None else self._rows)

    def fetchone(self):
        res = self._result if self._result is not None else []
        return res[0] if res else None


class ToursForTest(unittest.TestCase):
    def test_shape_and_newest_first(self):
        # DB would return newest first; we feed rows in that order. Columns now:
        # id, name, stop_count, created_at, version, language (LOCAL-748 + A2).
        rows = [
            (12, "Beacon Hill, Boston MA - Walking Tour", 4,
             datetime.datetime(2026, 10, 18, 9, 0, 0), 1, "en"),
            (7, "Faneuil Hall Marketplace - Walking Tour", 3,
             datetime.datetime(2026, 10, 1, 9, 0, 0), 1, "en"),
        ]
        cur = _ToursCursor(rows)
        out = ca._tours_for(cur, 2)

        # Row shape (version + languages carried; languages = [original] when no
        # finished translations).
        self.assertEqual(out, [
            {'id': 12, 'name': 'Beacon Hill, Boston MA - Walking Tour',
             'stop_count': 4, 'created_at': '2026-10-18T09:00:00',
             'version': 1, 'languages': ['en']},
            {'id': 7, 'name': 'Faneuil Hall Marketplace - Walking Tour',
             'stop_count': 3, 'created_at': '2026-10-01T09:00:00',
             'version': 1, 'languages': ['en']},
        ])
        # Newest first is preserved (the first row is the most recent).
        self.assertEqual(out[0]['id'], 12)

    def test_languages_include_finished_translations(self):
        rows = [
            (12, "Beacon Hill", 4, datetime.datetime(2026, 10, 18, 9, 0, 0),
             1, "en"),
        ]
        cur = _ToursCursor(rows, translations={12: ["ru", "es"]})
        out = ca._tours_for(cur, 2)
        self.assertEqual(out[0]['languages'], ['en', 'ru', 'es'])

    def test_query_filters_community_excludes_drafts_orders_desc(self):
        cur = _ToursCursor([])
        ca._tours_for(cur, 42)
        sql = cur.last_sql.lower()
        self.assertIn("from audio_tours", sql)
        self.assertIn("community_id = %s", sql)
        self.assertIn("draft", sql)  # drafts excluded
        self.assertIn("original_tour_id is null", sql)  # [LOCAL-752 A2] originals only
        self.assertIn("order by t.created_at desc", sql)
        self.assertEqual(cur.last_params, (42,))
        # Owner episodes table is never consulted by the tours query.
        self.assertNotIn("community_episodes", sql)

    def test_empty_when_no_tours(self):
        self.assertEqual(ca._tours_for(_ToursCursor([]), 1), [])

    def test_null_created_at(self):
        cur = _ToursCursor([(5, "Untimed tour", 0, None, 1, "en")])
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
