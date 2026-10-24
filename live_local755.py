#!/usr/bin/env python3
"""live_local755.py — LOCAL-755 live end-to-end on the TEST database.

No OpenAI, no simulator, no third-party host, $0.00: it serves its OWN 3-stop
RSS test feed from a local HTTP server, then runs the REAL LOCAL-755 server
pieces end to end against audiotours_test:

  1. The REAL build_audio_tour endpoint (communities_api) builds an
     organiser-audio tour from the feed → an audio_tours row with
     source_kind='organiser_audio' (is_test), version 1, NO archive row.
  2. Rule 1 — the REAL tour-editing guard refuses an edit of that tour:
     tour_editing_phase2._organiser_audio_edit_block(cur, tour_id) returns
     (409, organiser_audio_not_editable). A generated row returns None.
  3. Rule 2 — the REAL build_audio_tour EDIT, WITHOUT the checkbox:
     notify_members absent → version STAYS 1, NO new audio_tour_versions row
     (a silent typo fix).
  4. Rule 2 — the REAL build_audio_tour EDIT, WITH the checkbox:
     notify_members=true → the old content is archived (version_no 1 appears)
     and the response version rises to 2 (members get the opt-in Re-download).
  5. Row counts (audio_tours, communities, audio_tour_versions) before/after;
     every row created is is_test=true; cleanup removes ONLY this run's rows
     (D141) — no purchase-bearing rows touched (D690).

Run: python3 live_local755.py
"""
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'user-tracking'))
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', 'true')
os.environ['DATABASE_URL'] = (
    'postgresql://admin:password123@localhost:5433/audiotours_test')
# tour_editing_phase2 reads DB_* for its own connection.
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5433')
os.environ.setdefault('DB_NAME', 'audiotours_test')
os.environ.setdefault('DB_USER', 'admin')
os.environ.setdefault('DB_PASSWORD', 'password123')

import communities_api  # noqa: E402
import community_tours_service as cts  # noqa: E402
import tour_editing_phase2 as p2  # noqa: E402
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


def _conn():
    return psycopg2.connect(
        host='localhost', port='5433', dbname='audiotours_test',
        user='admin', password='password123')


def _counts(cur):
    out = {}
    for tbl in ('audio_tours', 'communities', 'audio_tour_versions'):
        cur.execute(f'SELECT COUNT(*) FROM {tbl}')
        out[tbl] = cur.fetchone()[0]
    return out


def _archive_versions(cur, tour_id):
    cur.execute(
        "SELECT version_no FROM audio_tour_versions WHERE tour_id = %s "
        "ORDER BY version_no", (tour_id,))
    return [r[0] for r in cur.fetchall()]


def main():
    srv, port = _start_server()
    communities_api.API_KEY = ''
    communities_api._audio_url_check = lambda url: (True, 'audio/mpeg', 200)

    flask_app = Flask(__name__)
    flask_app.register_blueprint(communities_api.communities_bp)
    client = flask_app.test_client()

    conn = _conn()
    conn.autocommit = True
    cur = conn.cursor()

    owner = f'L755-OWNER-{RUN}'
    member = f'L755-MEMBER-{RUN}'
    community_id = None
    tour_id = None
    gen_tour_id = None
    failures = []

    def check(name, ok, detail=''):
        mark = 'PASS' if ok else 'FAIL'
        print(f'  [{mark}] {name}{(" — " + detail) if detail else ""}')
        if not ok:
            failures.append(name)

    try:
        before = _counts(cur)
        print(f'Row counts BEFORE: {before}')

        # A community owned by `owner`.
        cur.execute(
            "INSERT INTO communities (name, owner_user_id, disabled) "
            "VALUES (%s, %s, FALSE) RETURNING id",
            (f'L755 {RUN}', owner))
        community_id = cur.fetchone()[0]

        stops = [
            {'name': 'Town Square', 'lat': 42.10, 'lng': -71.20,
             'text': 'Heart of town.', 'audio_url': f'http://127.0.0.1:{port}/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.11, 'lng': -71.21,
             'text': 'A mill.', 'audio_url': f'http://127.0.0.1:{port}/a2.mp3'},
            {'name': 'River Bend', 'lat': 42.12, 'lng': -71.22,
             'text': 'The river.', 'audio_url': f'http://127.0.0.1:{port}/a3.mp3'},
        ]

        def body(**over):
            b = {'user_id': owner, 'tour_name': f'L755 Walk {RUN}',
                 'tour_type': 'walking', 'visibility': 'members',
                 'rights_accepted': True, 'stops': stops}
            b.update(over)
            return b

        # 1) OWNER builds the organiser-audio tour.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json=body())
        check('1. build organiser-audio tour → 201',
              r.status_code == 201, f'status={r.status_code}')
        j = r.get_json()
        tour_id = j and j.get('tour_id')
        check('1. source_kind=organiser_audio', j and j.get('source_kind') == 'organiser_audio')
        check('1. new tour version == 1', j and j.get('version') == 1)
        # Mark our rows is_test so cleanup is D141-safe.
        if tour_id:
            cur.execute("UPDATE audio_tours SET is_test = TRUE WHERE id = %s",
                        (tour_id,))

        # A plain generated community tour (control) for the guard contrast.
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, is_test, "
            "community_id, community_visibility, audio_tour, stops_count) "
            "VALUES (%s, %s, TRUE, %s, 'members', %s, 2) RETURNING id",
            (f'L755 generated {RUN}', 'gen', community_id,
             psycopg2.Binary(b'PKGEN')))
        gen_tour_id = cur.fetchone()[0]

        # 2) Rule 1 — the tour-editing guard refuses the organiser-audio tour.
        cts._HAS_SOURCE_KIND_COLUMN = None  # force a fresh probe on the live DB
        block = p2._organiser_audio_edit_block(cur, str(tour_id))
        check('2. edit guard refuses organiser-audio (409)',
              block is not None and block[0] == 409
              and block[1].get('error_code') == 'organiser_audio_not_editable',
              detail=str(block[1].get('error_code') if block else None))
        gen_block = p2._organiser_audio_edit_block(cur, str(gen_tour_id))
        check('2. edit guard ALLOWS a generated tour', gen_block is None)

        # 3) Rule 2 — EDIT without the checkbox keeps the version, no archive.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json=body(tour_id=tour_id,
                                  tour_name=f'L755 Walk {RUN} (typo)'))
        j = r.get_json()
        check('3. silent edit (no checkbox) → 200', r.status_code == 200,
              f'status={r.status_code}')
        check('3. version STAYS 1', j and j.get('version') == 1,
              detail=f'version={j.get("version") if j else None}')
        check('3. notify_members echoed false', j and j.get('notify_members') is False)
        check('3. NO archive row yet', _archive_versions(cur, tour_id) == [],
              detail=str(_archive_versions(cur, tour_id)))

        # 4) Rule 2 — EDIT WITH the checkbox bumps the version + archives.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json=body(tour_id=tour_id, notify_members=True,
                                  tour_name=f'L755 Walk {RUN} (new audio)'))
        j = r.get_json()
        check('4. notify edit (checkbox) → 200', r.status_code == 200,
              f'status={r.status_code}')
        check('4. version RISES to 2', j and j.get('version') == 2,
              detail=f'version={j.get("version") if j else None}')
        check('4. notify_members echoed true', j and j.get('notify_members') is True)
        check('4. archive row version_no 1 written',
              _archive_versions(cur, tour_id) == [1],
              detail=str(_archive_versions(cur, tour_id)))

        after = _counts(cur)
        print(f'Row counts AFTER (pre-cleanup): {after}')
        print(f'  Δ audio_tours={after["audio_tours"]-before["audio_tours"]} '
              f'(2: organiser-audio + generated control), '
              f'Δ communities={after["communities"]-before["communities"]} (1), '
              f'Δ audio_tour_versions='
              f'{after["audio_tour_versions"]-before["audio_tour_versions"]} (1)')

    finally:
        # D141 cleanup — ONLY this run's is_test rows + its own community.
        try:
            if tour_id:
                cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s",
                            (tour_id,))
                cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                            (tour_id,))
            if gen_tour_id:
                cur.execute("DELETE FROM audio_tour_versions WHERE tour_id = %s",
                            (gen_tour_id,))
                cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                            (gen_tour_id,))
            if community_id:
                cur.execute("DELETE FROM communities WHERE id = %s", (community_id,))
            after_clean = _counts(cur)
            print(f'Row counts AFTER cleanup: {after_clean}')
        except Exception as e:
            print(f'cleanup error: {e}')
        cur.close()
        conn.close()
        srv.shutdown()

    print()
    if failures:
        print(f'LOCAL-755 LIVE: FAIL ({len(failures)} checks failed: {failures})')
        sys.exit(1)
    print('LOCAL-755 LIVE: ALL CHECKS PASSED (budget $0.00, no AI, is_test only)')


if __name__ == '__main__':
    main()
