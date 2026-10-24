#!/usr/bin/env python3
"""test_local754b_organiser_audio.py — LOCAL-754B (RED first on 027584b0).

The organiser builds a REAL tour from their OWN hosted audio (RSS/MP3 links); on
Listen it is indistinguishable from a generated Audioura tour. These tests prove
the SERVER pieces, all hermetically (no Postgres, no network — a fake cursor and
an injected URL checker), so they are fast and deterministic.

They FAIL on 027584b0 because neither organiser_audio_tours (the pure builder /
validator / translation gate) nor the /communities/<id>/build-audio-tour
endpoint exist there. They pass once LOCAL-754B lands.

PART A — the pure builder/validator module (organiser_audio_tours):
  * keep_audio_enclosures keeps only audio items and counts the skipped ones;
  * validate_stops / validate_audio_urls name the FIRST failing stop;
  * build_package writes remote_audio.json and NO .mp3, and its index.html has
    the SAME per-stop markup as a generated page (compared with
    tour_html_map.build_tour_page_html);
  * translation_not_offered is True only for source_kind='organiser_audio'.

PART B — the Flask endpoint (communities_api.build_audio_tour), through a
scripted fake cursor (same hermetic style as test_local701_community_tours):
  * a MEMBER (not the owner) gets 403 and no tour is built;
  * the OWNER builds the tour → 201, the audio_tours row carries source_kind
    'organiser_audio' and the community tags, and the stored ZIP has
    remote_audio.json + no .mp3;
  * a publish with an unreachable URL returns 422 naming the failing stop;
  * editing bumps the version (an audio_tour_versions row is archived).

Run: python3 -m pytest tests/test_local754b_organiser_audio.py -q
"""
import io
import json
import os
import sys
import zipfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_UT, _ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import organiser_audio_tours as oat  # noqa: E402  (user-tracking/)
import tour_html_map  # noqa: E402  (repo root — the shared renderer)


# ════════════════════════════════════════════════════════════════════════════
# PART A — pure module
# ════════════════════════════════════════════════════════════════════════════
class KeepAudioEnclosuresTest(unittest.TestCase):
    def test_keeps_audio_only_and_counts_skipped(self):
        episodes = [
            {'title': 'One', 'audio_url': 'https://h/one.mp3'},
            {'title': 'Doc', 'audio_url': 'https://h/notes.pdf'},  # skipped
            {'title': 'Two', 'audio_url': 'https://h/two.m4a'},
            {'title': 'Typed', 'audio_url': 'https://h/stream',
             'content_type': 'audio/mpeg'},
            {'title': 'Page', 'audio_url': 'https://h/page.html'},  # skipped
        ]
        kept, skipped = oat.keep_audio_enclosures(episodes)
        self.assertEqual([k['title'] for k in kept], ['One', 'Two', 'Typed'])
        self.assertEqual([k['position'] for k in kept], [1, 2, 3])
        self.assertEqual(skipped, 2)


class ValidateStopsTest(unittest.TestCase):
    def test_walking_requires_location_and_names_stop(self):
        stops = [
            {'name': 'Square', 'lat': 42.1, 'lng': -71.2,
             'audio_url': 'https://h/1.mp3'},
            {'name': 'Station', 'lat': None, 'lng': None,
             'audio_url': 'https://h/2.mp3'},
        ]
        with self.assertRaises(oat.StopValidationError) as ctx:
            oat.validate_stops(stops, 'walking')
        self.assertEqual(ctx.exception.code, 'stop_needs_location')
        self.assertEqual(ctx.exception.stop_name, 'Station')

    def test_other_tour_allows_missing_location(self):
        stops = [{'name': 'Anywhere', 'lat': None, 'lng': None,
                  'audio_url': 'https://h/1.mp3'}]
        self.assertIsNone(oat.validate_stops(stops, 'other'))

    def test_empty_list_rejected(self):
        with self.assertRaises(oat.StopValidationError) as ctx:
            oat.validate_stops([], 'walking')
        self.assertEqual(ctx.exception.code, 'no_stops')


class ValidateAudioUrlsTest(unittest.TestCase):
    def test_unreachable_url_names_failing_stop(self):
        stops = [
            {'name': 'Good', 'audio_url': 'https://h/good.mp3'},
            {'name': 'Broken Stop', 'audio_url': 'https://h/bad.mp3'},
        ]

        def checker(url):
            if 'bad' in url:
                return (False, None, None)
            return (True, 'audio/mpeg', 1000)

        with self.assertRaises(oat.StopValidationError) as ctx:
            oat.validate_audio_urls(stops, checker)
        self.assertEqual(ctx.exception.code, 'audio_unreachable')
        self.assertEqual(ctx.exception.stop_name, 'Broken Stop')

    def test_too_large_url_rejected_by_name(self):
        stops = [{'name': 'Huge', 'audio_url': 'https://h/huge.mp3'}]
        checker = lambda u: (True, 'audio/mpeg', oat.MAX_AUDIO_BYTES + 1)  # noqa: E731
        with self.assertRaises(oat.StopValidationError) as ctx:
            oat.validate_audio_urls(stops, checker)
        self.assertEqual(ctx.exception.code, 'audio_too_large')
        self.assertEqual(ctx.exception.stop_name, 'Huge')

    def test_all_good_passes(self):
        stops = [{'name': 'A', 'audio_url': 'https://h/a.mp3'},
                 {'name': 'B', 'audio_url': 'https://h/b.m4a'}]
        self.assertIsNone(
            oat.validate_audio_urls(stops, lambda u: (True, 'audio/mpeg', 10)))


class BuildPackageTest(unittest.TestCase):
    def _stops(self):
        return [
            {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
             'text': 'The heart of town.', 'audio_url': 'https://host/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
             'text': 'A 19th-century mill.', 'audio_url': 'https://host/a2.mp3'},
        ]

    def test_package_has_remote_audio_and_no_mp3(self):
        data = oat.build_package('River Walk', self._stops(), 'walking')
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = set(zf.namelist())
        self.assertIn('remote_audio.json', names)
        self.assertIn('index.html', names)
        self.assertIn('audio_1.txt', names)
        self.assertIn('audio_2.txt', names)
        self.assertIn('tour_content.txt', names)
        self.assertIn('manifest.json', names)
        # No MP3 whatsoever — Audioura never stores the audio (D658 addendum 2).
        self.assertFalse(any(n.endswith('.mp3') for n in names),
                         f"package must contain NO mp3, got {names}")
        # remote_audio.json maps stop N → the organiser's URL.
        remote = json.loads(zf.read('remote_audio.json'))
        self.assertEqual(remote['1'], 'https://host/a1.mp3')
        self.assertEqual(remote['2'], 'https://host/a2.mp3')

    def test_index_html_matches_generated_stop_markup(self):
        """The package's index.html is byte-for-byte what the SHARED renderer
        produces for the same stops — so a generated and an organiser-audio page
        have the identical ": Audio N" headings, map buttons and voice script."""
        stops = self._stops()
        data = oat.build_package('River Walk', stops, 'walking')
        zf = zipfile.ZipFile(io.BytesIO(data))
        got_html = zf.read('index.html').decode('utf-8')

        stop_texts = [oat.stop_text_block(s) for s in stops]
        expected = tour_html_map.build_tour_page_html(
            'River Walk', stop_texts, 'walking')
        self.assertEqual(got_html, expected)
        # Spot-check the generated-page markers are present.
        self.assertIn('Town Square: Audio 1', got_html)
        self.assertIn('openMap(1)', got_html)                 # map button
        self.assertIn('audio_1.mp3', got_html)                # audio ref
        self.assertIn('window.nextStop', got_html)            # voice control


class TranslationGateTest(unittest.TestCase):
    def test_organiser_audio_not_offered(self):
        self.assertTrue(oat.translation_not_offered('organiser_audio'))

    def test_generated_tour_is_offered(self):
        self.assertFalse(oat.translation_not_offered(None))
        self.assertFalse(oat.translation_not_offered(''))


# ════════════════════════════════════════════════════════════════════════════
# PART B — the Flask endpoint through a scripted fake cursor
# ════════════════════════════════════════════════════════════════════════════
import communities_api  # noqa: E402  (user-tracking/)


class _FakeCursor:
    """A scripted cursor (same pattern as test_local701). Each execute matches
    the FIRST (needle, result) whose needle is a substring of the normalised
    SQL; result is a list of rows OR a callable(params)->rows. INSERT …
    RETURNING id yields a row via the 'returning_id' key. Captured writes land
    in `self.writes` so a test can assert what was stored."""

    def __init__(self, plan, writes):
        self._plan = plan
        self._rows = []
        self.writes = writes
        self.connection = self

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        self.writes.append((text, params))
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result(params) if callable(result) else result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass

    def rollback(self):
        pass


class _FakeConn:
    def __init__(self, plan, writes):
        self._plan = plan
        self.writes = writes

    def cursor(self):
        return _FakeCursor(self._plan, self.writes)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


_OWNER = 'owner-123'
_MEMBER = 'member-456'
_COMMUNITY_ID = 7


def _community_row_rows(owner):
    """The 25-column SELECT communities row _community_row reads (order matches
    communities_api._community_row). Only owner_user_id and name matter here."""
    return [(
        _COMMUNITY_ID, owner, 'The Owls', 'desc', 'Org', None, None, None,
        None, None, False, True, 'listed', 42.1, -71.2, 'CODE1234', None, False,
        'active', None, None, None, None, None, 'week',
    )]


class BuildAudioTourEndpointTest(unittest.TestCase):
    def setUp(self):
        communities_api.API_KEY = ''  # unauthenticated allowed in test
        os.environ['ALLOW_UNAUTHENTICATED_ENTITLEMENTS'] = 'true'
        self.app = communities_api.communities_bp
        from flask import Flask
        flask_app = Flask(__name__)
        flask_app.register_blueprint(self.app)
        self.client = flask_app.test_client()
        self._orig_get_db = communities_api._get_db
        # A generous URL checker: every URL ok, audio, small. Overridable.
        communities_api._audio_url_check = lambda url: (True, 'audio/mpeg', 1000)

    def tearDown(self):
        communities_api._get_db = self._orig_get_db

    def _install(self, plan):
        writes = []
        communities_api._get_db = lambda: _FakeConn(plan, writes)
        return writes

    def _body(self, user_id, **over):
        body = {
            'user_id': user_id,
            'tour_name': 'River Walk',
            'tour_type': 'walking',
            'rights_accepted': True,
            'visibility': 'members',
            'stops': [
                {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
                 'text': 'Heart of town.', 'audio_url': 'https://host/a1.mp3'},
                {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
                 'text': 'A mill.', 'audio_url': 'https://host/a2.mp3'},
            ],
        }
        body.update(over)
        return body

    def test_member_gets_403_and_builds_nothing(self):
        plan = [("from communities where id", _community_row_rows(_OWNER))]
        writes = self._install(plan)
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._body(_MEMBER))
        self.assertEqual(r.status_code, 403)
        # No audio_tours INSERT was attempted by a non-owner.
        self.assertFalse(
            any('insert into audio_tours' in w[0] for w in writes),
            "a non-owner must not build a tour")

    def test_owner_builds_tour_with_source_kind_and_remote_audio(self):
        inserted = {}

        def cap_insert(params):
            inserted['params'] = params
            return [(99,)]  # RETURNING id

        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
            ("insert into audio_tours", cap_insert),
            ("max(version_no)", [(None,)]),
        ]
        writes = self._install(plan)
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._body(_OWNER))
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        j = r.get_json()
        self.assertEqual(j['tour_id'], 99)
        self.assertEqual(j['source_kind'], 'organiser_audio')
        self.assertEqual(j['community_id'], _COMMUNITY_ID)
        # The stored ZIP (the audio_tour BYTEA param) has remote_audio.json, no mp3.
        insert_write = next(w for w in writes if 'insert into audio_tours' in w[0])
        zip_bytes = None
        for p in insert_write[1]:
            # psycopg2.Binary wraps the bytes in an adapter; unwrap it.
            raw = getattr(p, 'adapted', p)
            if isinstance(raw, (bytes, bytearray, memoryview)):
                b = bytes(raw)
                if b[:2] == b'PK':
                    zip_bytes = b
                    break
        self.assertIsNotNone(zip_bytes, "the audio_tour ZIP must be an INSERT param")
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = set(zf.namelist())
        self.assertIn('remote_audio.json', names)
        self.assertFalse(any(n.endswith('.mp3') for n in names))

    def test_unreachable_url_returns_422_named_stop(self):
        communities_api._audio_url_check = \
            lambda url: (False, None, None) if 'a2' in url else (True, 'audio/mpeg', 10)
        plan = [("from communities where id", _community_row_rows(_OWNER))]
        self._install(plan)
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._body(_OWNER))
        self.assertEqual(r.status_code, 422)
        j = r.get_json()
        self.assertEqual(j['error'], 'audio_unreachable')
        self.assertEqual(j.get('stop_name'), 'Old Mill')

    def test_edit_bumps_version(self):
        """Editing an existing organiser-audio tour WITH the "tell my members"
        checkbox (notify_members, LOCAL-755/D709) archives the old content to
        audio_tour_versions (version bump) — the same mechanism a generated edit
        uses so LOCAL-748/750 refresh reaches members. (Without the checkbox the
        save is silent and the version stays — see
        test_local755_organiser_audio_updates.)"""
        def cap_update(params):
            return []

        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
            # The existing tour row read for the edit (id, source_kind, content).
            ("select id, source_kind", [(99, 'organiser_audio', 'old content')]),
            ("coalesce(max(version_no), 0)", [(0,)]),
            ("insert into audio_tour_versions", [(1,)]),
            ("update audio_tours", cap_update),
        ]
        writes = self._install(plan)
        body = self._body(_OWNER)
        body['tour_id'] = 99
        body['notify_members'] = True  # [LOCAL-755] the version bump is gated on this
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=body)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(
            any('insert into audio_tour_versions' in w[0] for w in writes),
            "an edit WITH notify_members must archive the old content (version bump)")
        j = r.get_json()
        self.assertEqual(j['version'], 2)  # MAX(0)+1 archived → new live is v2


if __name__ == '__main__':
    unittest.main(verbosity=2)
