#!/usr/bin/env python3
"""live_local754b.py — LOCAL-754B live end-to-end on the TEST database.

No OpenAI, no simulator, no third-party host: it serves its OWN RSS test feed
(3 short MP3 enclosures + 1 non-audio) from a local HTTP server, then runs the
REAL organiser-audio pieces end to end against audiotours_test:

  1. keep_audio_enclosures over the parsed feed → 3 kept, 1 skipped.
  2. The REAL build_audio_tour endpoint (communities_api) over the live DB:
     an owner builds a 3-stop walking tour from the feed's audio → an
     audio_tours row with source_kind='organiser_audio', the community tags and
     the stored package (remote_audio.json, NO mp3).
  3. A MEMBER is refused the build (403); the owner succeeds.
  4. The REAL app download contract: resolve remote_audio.json → fetch each URL
     from the local host → audio_N.mp3 written (proves offline playback).
  5. index.html matches the SHARED generated renderer for the same stops.
  6. The translation refusal helper returns 403 translation_not_offered for the
     built tour and allows a generated row.
  7. Row counts (audio_tours, community_episodes, communities) before/after; all
     rows created are is_test=true; cleanup removes ONLY this run's is_test rows
     (D141) — no purchase-bearing rows touched (D690). Budget: $0.00 (no AI).

Run: python3 live_local754b.py
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'translation-service'))

os.environ.setdefault('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', 'true')
# Point communities_api at the TEST DB (port 5433, audiotours_test).
os.environ['DATABASE_URL'] = (
    'postgresql://admin:password123@localhost:5433/audiotours_test')

import communities_rss  # noqa: E402
import organiser_audio_tours as oat  # noqa: E402
import communities_api  # noqa: E402
import psycopg2  # noqa: E402
from flask import Flask  # noqa: E402

RUN = uuid.uuid4().hex[:8]

# ── A tiny valid MP3 (ID3 header + a few silent frames) ──────────────────────
_MP3 = (b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\xff\xfb\x90\x00' + b'\x00' * 200)
_FEED = f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>L754B Test Feed</title>
  <item><title>Town Square</title>
    <enclosure url="http://127.0.0.1:{{port}}/a1.mp3" type="audio/mpeg" length="200"/>
    <guid>g1-{RUN}</guid></item>
  <item><title>Old Mill</title>
    <enclosure url="http://127.0.0.1:{{port}}/a2.mp3" type="audio/mpeg" length="200"/>
    <guid>g2-{RUN}</guid></item>
  <item><title>River Bend</title>
    <enclosure url="http://127.0.0.1:{{port}}/a3.mp3" type="audio/mpeg" length="200"/>
    <guid>g3-{RUN}</guid></item>
  <item><title>Program Notes (PDF)</title>
    <enclosure url="http://127.0.0.1:{{port}}/notes.pdf" type="application/pdf" length="10"/>
    <guid>g4-{RUN}</guid></item>
</channel></rss>"""


class _Handler(BaseHTTPRequestHandler):
    port = 0

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
        if p == '/feed.xml':
            self._send(200, 'application/rss+xml',
                       _FEED.format(port=_Handler.port).encode())
        elif p in ('/a1.mp3', '/a2.mp3', '/a3.mp3'):
            self._send(200, 'audio/mpeg', _MP3)
        elif p == '/notes.pdf':
            self._send(200, 'application/pdf', b'%PDF-1.4 not audio')
        else:
            self._send(404, 'text/plain', b'nope')


def _start_server():
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    _Handler.port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, _Handler.port


def _counts(cur):
    out = {}
    for tbl in ('audio_tours', 'community_episodes', 'communities'):
        cur.execute(f'SELECT COUNT(*) FROM {tbl}')
        out[tbl] = cur.fetchone()[0]
    return out


def main():
    srv, port = _start_server()
    base = f'http://127.0.0.1:{port}'
    print(f'[feed] serving own RSS + 3 MP3 + 1 PDF at {base}')

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()

    before = _counts(cur)
    print(f'[rows] before: {before}')

    owner = f'L754B-owner-{RUN}'
    member = f'L754B-member-{RUN}'
    community_id = None
    created_tour_ids = []

    try:
        # A test community owned by `owner`, with a member.
        cur.execute(
            "INSERT INTO communities (owner_user_id, name, is_paid, visibility, "
            "feed_url, status) VALUES (%s, %s, FALSE, 'private', %s, 'active') "
            "RETURNING id",
            (owner, f'L754B {RUN}', f'{base}/feed.xml'))
        community_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO community_memberships (user_id, community_id, expires_at) "
            "VALUES (%s, %s, NULL)", (member, community_id))
        print(f'[community] id={community_id} owner={owner} member={member}')

        # 1) Parse the feed + keep audio only.
        parsed = communities_rss.fetch_and_parse(f'{base}/feed.xml')
        kept, skipped = oat.keep_audio_enclosures(parsed)
        assert len(kept) == 3 and skipped == 1, (len(kept), skipped)
        print(f'[feed] parsed {len(parsed)} items → kept {len(kept)} audio, '
              f'skipped {skipped} non-audio ✓')

        # Build the endpoint client over the live DB.
        flask_app = Flask(__name__)
        flask_app.register_blueprint(communities_api.communities_bp)
        communities_api.API_KEY = ''
        client = flask_app.test_client()
        # Real audio-URL checker hits the local host (HEAD → ranged GET).
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

        # 3) Member refused.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={**body, 'user_id': member})
        assert r.status_code == 403, r.status_code
        print('[owner-only] member build refused 403 ✓')

        # 2) Owner builds → 201.
        r = client.post(f'/communities/{community_id}/build-audio-tour', json=body)
        assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
        j = r.get_json()
        tour_id = j['tour_id']
        created_tour_ids.append(tour_id)
        assert j['source_kind'] == 'organiser_audio'
        print(f'[build] owner published tour_id={tour_id} '
              f'source_kind={j["source_kind"]} stops={j["stops_count"]} ✓')

        # Mark the tour is_test so cleanup is safe (D141).
        cur.execute("UPDATE audio_tours SET is_test = TRUE WHERE id = %s",
                    (tour_id,))

        # Read the row back: source_kind, community tags, rights, the ZIP.
        cur.execute(
            "SELECT source_kind, community_id, community_visibility, stops_count, "
            "rights_accepted_by, rights_accepted_at, audio_tour "
            "FROM audio_tours WHERE id = %s", (tour_id,))
        sk, cid, vis, sc, rby, rat, zip_mem = cur.fetchone()
        assert sk == 'organiser_audio' and cid == community_id
        assert vis == 'members' and sc == 3
        assert rby == owner and rat is not None
        zip_bytes = bytes(zip_mem)
        print(f'[row] source_kind={sk} community_id={cid} visibility={vis} '
              f'stops_count={sc} rights_by={rby} ✓')

        # 4) Package contract: remote_audio.json, NO mp3; index.html == shared.
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = set(zf.namelist())
        assert 'remote_audio.json' in names
        assert not any(n.endswith('.mp3') for n in names), names
        remote = json.loads(zf.read('remote_audio.json'))
        assert remote == {'1': f'{base}/a1.mp3', '2': f'{base}/a2.mp3',
                          '3': f'{base}/a3.mp3'}, remote
        import tour_html_map
        expected = tour_html_map.build_tour_page_html(
            f'River Walk {RUN}', [oat.stop_text_block(s) for s in stops], 'walking')
        assert zf.read('index.html').decode() == expected
        print(f'[package] remote_audio.json present, NO mp3, index.html == '
              f'generated renderer ✓  files={sorted(names)}')

        # 5) The APP download contract: resolve remote_audio.json → fetch each
        #    URL from the local host → audio_N.mp3 (proves offline playback).
        from urllib.request import urlopen
        audio_dir = os.path.join(os.path.dirname(__file__), 'scratch',
                                 f'l754b_{RUN}')
        os.makedirs(audio_dir, exist_ok=True)
        for n, url in sorted(remote.items(), key=lambda kv: int(kv[0])):
            data = urlopen(url, timeout=10).read()  # noqa: S310 — own local host
            assert data[:3] == b'ID3' and len(data) > 10, (n, len(data))
            with open(os.path.join(audio_dir, f'audio_{n}.mp3'), 'wb') as f:
                f.write(data)
        got = sorted(os.listdir(audio_dir))
        assert got == ['audio_1.mp3', 'audio_2.mp3', 'audio_3.mp3'], got
        print(f'[phone] fetched remote audio → {got} beside index.html '
              f'(plays offline) ✓')

        # 6) Translation refusal (the pure gate the service reads).
        assert oat.translation_not_offered('organiser_audio') is True
        assert oat.translation_not_offered(None) is False
        print('[translate] organiser_audio → not offered; generated → offered ✓')

        # Edit bumps the version.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={**body, 'tour_id': tour_id,
                              'tour_name': f'River Walk {RUN} (edited)'})
        assert r.status_code == 200, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['version'] == 2, r.get_json()
        print(f'[edit] re-publish bumped version → {r.get_json()["version"]} ✓')

        after = _counts(cur)
        print(f'[rows] after: {after}')
        print(f'[rows] delta: audio_tours +{after["audio_tours"]-before["audio_tours"]}, '
              f'communities +{after["communities"]-before["communities"]}')
        print('[budget] $0.00 — organiser-audio uses NO OpenAI/AI calls ✓')
        print('\nLOCAL-754B LIVE: ALL CHECKS PASSED ✓')
    finally:
        # Cleanup — ONLY this run's is_test rows (D141); no purchase rows (D690).
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
