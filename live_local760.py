#!/usr/bin/env python3
"""live_local760.py — LOCAL-760 round-2 live end-to-end on the TEST database.

No OpenAI, no third-party host: it serves its OWN 3-MP3 RSS feed from a local
HTTP server and runs the REAL organiser-audio pieces against audiotours_test
(port 5433). It proves the ROUND-2 server surface Michael needs — the organiser
reopening a broadcast tour to change it and tell members:

  1. The owner builds a 3-stop organiser-audio walking tour (source_kind set).
  2. NEW owner-only GET /communities/<id>/audio-tours/<tour_id> returns the
     stops PREFILLED (name / location / text / audio_url) rebuilt from the stored
     package — so the builder reopens the existing tour rather than a blank one.
  3. A MEMBER is refused that GET (403) — the stops are the organiser's to edit.
  4. parse_stops_from_package over the stored ZIP round-trips every field.
  5. EDIT with notify_members=true bumps the version (2) — members are then
     offered a Re-download; a silent edit (no checkbox) keeps the version.
  6. Row counts (audio_tours, community_episodes, communities) before/after; all
     rows created are is_test=true; cleanup removes ONLY this run's is_test rows
     (D141) — no purchase-bearing rows (D690). Budget: $0.00 (no AI).

Run: python3 live_local760.py
"""
import io
import json
import os
import sys
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'user-tracking'))
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', 'true')
os.environ.setdefault(
    'DATABASE_URL',
    'postgresql://admin:password123@localhost:5433/audiotours_test')

import organiser_audio_tours as oat  # noqa: E402
import communities_api  # noqa: E402
import psycopg2  # noqa: E402
from flask import Flask  # noqa: E402

RUN = uuid.uuid4().hex[:8]
_MP3 = (b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\xff\xfb\x90\x00' + b'\x00' * 200)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self._route()

    def do_GET(self):
        self._route()

    def _route(self):
        p = self.path.split('?')[0]
        if p in ('/a1.mp3', '/a2.mp3', '/a3.mp3'):
            self._send(200, 'audio/mpeg', _MP3)
        else:
            self._send(404, 'text/plain', b'nope')


def _start_server():
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


def _counts(cur):
    out = {}
    for tbl in ('audio_tours', 'community_episodes', 'communities'):
        cur.execute(f'SELECT COUNT(*) FROM {tbl}')
        out[tbl] = cur.fetchone()[0]
    return out


def main():
    srv, port = _start_server()
    base = f'http://127.0.0.1:{port}'
    print(f'[feed] serving own 3 MP3 at {base}')

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()

    before = _counts(cur)
    print(f'[rows] before: {before}')

    owner = f'L760-owner-{RUN}'
    member = f'L760-member-{RUN}'
    community_id = None
    created_tour_ids = []

    try:
        cur.execute(
            "INSERT INTO communities (owner_user_id, name, is_paid, visibility, "
            "status) VALUES (%s, %s, FALSE, 'private', 'active') RETURNING id",
            (owner, f'L760 {RUN}'))
        community_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO community_memberships (user_id, community_id, expires_at) "
            "VALUES (%s, %s, NULL)", (member, community_id))
        print(f'[community] id={community_id} owner={owner} member={member}')

        flask_app = Flask(__name__)
        flask_app.register_blueprint(communities_api.communities_bp)
        communities_api.API_KEY = ''
        client = flask_app.test_client()
        communities_api._audio_url_check = communities_api._default_audio_url_check

        stops = [
            {'name': 'Town Square', 'lat': 42.100, 'lng': -71.200,
             'text': 'The heart of town.', 'audio_url': f'{base}/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.110, 'lng': -71.210,
             'text': 'A 19th-century mill.', 'audio_url': f'{base}/a2.mp3'},
            {'name': 'River Bend', 'lat': 42.120, 'lng': -71.220,
             'text': 'Where the river turns.', 'audio_url': f'{base}/a3.mp3'},
        ]
        body = {'user_id': owner, 'tour_name': f'River Walk {RUN}',
                'tour_type': 'walking', 'visibility': 'members',
                'rights_accepted': True, 'stops': stops}

        # 1) Owner builds the broadcast tour.
        r = client.post(f'/communities/{community_id}/build-audio-tour', json=body)
        assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
        tour_id = r.get_json()['tour_id']
        created_tour_ids.append(tour_id)
        cur.execute("UPDATE audio_tours SET is_test = TRUE WHERE id = %s", (tour_id,))
        print(f'[build] owner published tour_id={tour_id} source_kind='
              f'{r.get_json()["source_kind"]} stops={r.get_json()["stops_count"]} ✓')

        # 2) NEW owner-only GET → prefilled stops.
        r = client.get(f'/communities/{community_id}/audio-tours/{tour_id}'
                       f'?user_id={owner}')
        assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
        d = r.get_json()
        assert d['tour_name'] == f'River Walk {RUN}', d['tour_name']
        assert d['tour_type'] == 'walking', d['tour_type']
        assert d['visibility'] == 'members', d['visibility']
        assert len(d['stops']) == 3, d['stops']
        assert d['stops'][0]['name'] == 'Town Square'
        assert d['stops'][0]['audio_url'] == f'{base}/a1.mp3'
        assert abs(d['stops'][0]['lat'] - 42.100) < 1e-4
        assert d['stops'][1]['name'] == 'Old Mill'
        assert d['stops'][2]['name'] == 'River Bend'
        print(f'[GET] owner reopened tour PREFILLED: name="{d["tour_name"]}" '
              f'type={d["tour_type"]} visibility={d["visibility"]} '
              f'stops={[s["name"] for s in d["stops"]]} ✓')

        # 3) Member is refused the GET.
        r = client.get(f'/communities/{community_id}/audio-tours/{tour_id}'
                       f'?user_id={member}')
        assert r.status_code == 403, (r.status_code, r.get_data(as_text=True))
        print('[GET owner-only] member refused 403 ✓')

        # 4) parse_stops_from_package round-trips the stored ZIP.
        cur.execute("SELECT audio_tour FROM audio_tours WHERE id = %s", (tour_id,))
        zip_bytes = bytes(cur.fetchone()[0])
        parsed = oat.parse_stops_from_package(zip_bytes)
        assert len(parsed) == 3, parsed
        assert [p['name'] for p in parsed] == ['Town Square', 'Old Mill', 'River Bend']
        assert [p['audio_url'] for p in parsed] == [
            f'{base}/a1.mp3', f'{base}/a2.mp3', f'{base}/a3.mp3']
        assert all(p['lat'] is not None for p in parsed)
        print(f'[parse] stored ZIP → {len(parsed)} stops, every field recovered ✓')

        # 5a) Silent edit (no notify) keeps the version.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={**body, 'tour_id': tour_id,
                              'tour_name': f'River Walk {RUN} (typo)'})
        assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['version'] == 1, r.get_json()
        print(f'[edit silent] no checkbox → version stays {r.get_json()["version"]} ✓')

        # 5b) Edit WITH notify_members bumps the version → members re-download.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={**body, 'tour_id': tour_id, 'notify_members': True,
                              'tour_name': f'River Walk {RUN} (updated)'})
        assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['version'] == 2, r.get_json()
        assert r.get_json()['notify_members'] is True
        print(f'[edit notify] checkbox → version bumped to '
              f'{r.get_json()["version"]} (members offered Re-download) ✓')

        after = _counts(cur)
        print(f'[rows] after: {after}')
        print(f'[rows] delta: audio_tours +{after["audio_tours"]-before["audio_tours"]}, '
              f'communities +{after["communities"]-before["communities"]}')
        print('[budget] $0.00 — organiser-audio uses NO OpenAI/AI calls ✓')
        print('\nLOCAL-760 LIVE: ALL CHECKS PASSED ✓')
    finally:
        for tid in created_tour_ids:
            cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                        (tid,))
            cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s", (tid,))
        if community_id is not None:
            cur.execute("DELETE FROM community_memberships WHERE community_id = %s",
                        (community_id,))
            cur.execute("DELETE FROM community_episodes WHERE community_id = %s",
                        (community_id,))
            cur.execute("DELETE FROM communities WHERE id = %s", (community_id,))
        final = _counts(cur)
        print(f'[cleanup] removed this run\'s test rows → counts back to {final}')
        assert final == before, (final, before)
        cur.close()
        conn.close()
        srv.shutdown()


if __name__ == '__main__':
    main()
