#!/usr/bin/env python3
"""test_local760_audio_tour_detail.py — LOCAL-760 / D709 (RED first).

The organiser reopens an EXISTING organiser-audio tour to change it (Michael,
2026-10-24: "The organiser cannot mark the tour as Modified, so the members can
re-download"). The builder prefills from the server, so it needs an owner-only
read of the stored tour's stops.

This proves the SERVER pieces, hermetically (no Postgres, no network):

PART A — parse_stops_from_package reverses build_package.
  organiser_audio_tours.parse_stops_from_package(zip_bytes) returns the ordered
  stops [{name, lat, lng, text, audio_url}] read back from the package's
  audio_N.txt (name / Coordinates line / body) + remote_audio.json ({N: url}).
  It is the exact inverse of build_package for a round trip.

PART B — GET /communities/<id>/audio-tours/<tour_id> is owner-only.
  * the OWNER gets 200 {tour_name, tour_type, visibility, stops:[…]} rebuilt
    from the stored audio_tours row (audio_tour ZIP + community_visibility);
  * a MEMBER (non-owner) gets 403 forbidden — the stops are the organiser's to
    edit, so only the organiser may read them for editing;
  * a tour that is NOT this community's organiser-audio tour → 404/409.

These FAIL before LOCAL-760: parse_stops_from_package does not exist and no GET
audio-tours route is registered.

Run: python3 -m pytest tests/test_local760_audio_tour_detail.py -q
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_UT, _ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import organiser_audio_tours as oat  # noqa: E402  (user-tracking/)


# ════════════════════════════════════════════════════════════════════════════
# PART A — parse_stops_from_package reverses build_package
# ════════════════════════════════════════════════════════════════════════════
class ParseStopsRoundTripTest(unittest.TestCase):
    def test_round_trip_recovers_every_field(self):
        stops = [
            {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
             'text': 'Heart of town.', 'audio_url': 'https://host/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
             'text': 'A mill on the river.', 'audio_url': 'https://host/a2.mp3'},
        ]
        zip_bytes = oat.build_package('River Walk', stops, 'walking')
        parsed = oat.parse_stops_from_package(zip_bytes)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]['name'], 'Town Square')
        self.assertEqual(parsed[0]['audio_url'], 'https://host/a1.mp3')
        self.assertAlmostEqual(parsed[0]['lat'], 42.10, places=4)
        self.assertAlmostEqual(parsed[0]['lng'], -71.20, places=4)
        self.assertEqual(parsed[0]['text'], 'Heart of town.')
        self.assertEqual(parsed[1]['name'], 'Old Mill')
        self.assertEqual(parsed[1]['audio_url'], 'https://host/a2.mp3')

    def test_stop_without_location_parses_with_none(self):
        stops = [
            {'name': 'Intro', 'text': 'Welcome.',
             'audio_url': 'https://host/intro.mp3'},
        ]
        zip_bytes = oat.build_package('Audio Only', stops, 'other')
        parsed = oat.parse_stops_from_package(zip_bytes)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]['name'], 'Intro')
        self.assertIsNone(parsed[0]['lat'])
        self.assertIsNone(parsed[0]['lng'])
        self.assertEqual(parsed[0]['audio_url'], 'https://host/intro.mp3')

    def test_empty_or_garbage_bytes_returns_empty(self):
        self.assertEqual(oat.parse_stops_from_package(b''), [])
        self.assertEqual(oat.parse_stops_from_package(b'not a zip'), [])


# ════════════════════════════════════════════════════════════════════════════
# PART B — owner-only GET endpoint
# ════════════════════════════════════════════════════════════════════════════
import communities_api  # noqa: E402  (user-tracking/)

_OWNER = 'owner-123'
_MEMBER = 'member-456'
_COMMUNITY_ID = 7
_TOUR_ID = 99


def _community_row_rows(owner):
    # Matches _community_row's 25-column SELECT order.
    return [(
        _COMMUNITY_ID, owner, 'The Owls', 'desc', 'Org', None, None, None,
        None, None, False, True, 'listed', 42.1, -71.2, 'CODE1234', None, False,
        'active', None, None, None, None, None, 'week',
    )]


class _FakeCursor:
    def __init__(self, plan):
        self._plan = plan
        self._rows = []

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        for needle, rows in self._plan:
            if needle.lower() in text:
                self._rows = list(rows(params) if callable(rows) else rows)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, plan):
        self._plan = plan

    def cursor(self):
        return _FakeCursor(self._plan)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class AudioTourDetailEndpointTest(unittest.TestCase):
    def setUp(self):
        communities_api.API_KEY = ''
        os.environ['ALLOW_UNAUTHENTICATED_ENTITLEMENTS'] = 'true'
        from flask import Flask
        flask_app = Flask(__name__)
        flask_app.register_blueprint(communities_api.communities_bp)
        self.client = flask_app.test_client()
        self._orig_get_db = communities_api._get_db
        # A real stored package for the owner read to parse back.
        self._zip = oat.build_package('River Walk', [
            {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
             'text': 'Heart of town.', 'audio_url': 'https://host/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
             'text': 'A mill.', 'audio_url': 'https://host/a2.mp3'},
        ], 'walking')

    def tearDown(self):
        communities_api._get_db = self._orig_get_db

    def _install(self, plan):
        communities_api._get_db = lambda: _FakeConn(plan)

    def _detail_plan(self):
        return [
            ("from communities where id", _community_row_rows(_OWNER)),
            # The tour row read: id, source_kind, tour_name, community_visibility,
            # audio_tour (ZIP bytes).
            ("from audio_tours",
             [(_TOUR_ID, 'organiser_audio', 'River Walk', 'members', self._zip)]),
        ]

    def test_owner_gets_stops_200(self):
        self._install(self._detail_plan())
        r = self.client.get(
            f'/communities/{_COMMUNITY_ID}/audio-tours/{_TOUR_ID}'
            f'?user_id={_OWNER}')
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body.get('tour_name'), 'River Walk')
        self.assertEqual(body.get('visibility'), 'members')
        stops = body.get('stops')
        self.assertIsInstance(stops, list)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]['name'], 'Town Square')
        self.assertEqual(stops[0]['audio_url'], 'https://host/a1.mp3')

    def test_member_is_refused_403(self):
        self._install(self._detail_plan())
        r = self.client.get(
            f'/communities/{_COMMUNITY_ID}/audio-tours/{_TOUR_ID}'
            f'?user_id={_MEMBER}')
        self.assertEqual(r.status_code, 403, r.get_data(as_text=True))

    def test_not_organiser_audio_tour_409(self):
        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
            ("from audio_tours",
             [(_TOUR_ID, None, 'Generated Tour', 'members', self._zip)]),
        ]
        self._install(plan)
        r = self.client.get(
            f'/communities/{_COMMUNITY_ID}/audio-tours/{_TOUR_ID}'
            f'?user_id={_OWNER}')
        self.assertIn(r.status_code, (404, 409), r.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
