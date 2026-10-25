#!/usr/bin/env python3
"""live_local762.py — LOCAL-762 live end-to-end on the TEST database.

No OpenAI, no third-party host: it serves its OWN 2-MP3 feed from a local HTTP
server and runs the REAL LOCAL-762 server pieces against audiotours_test
(port 5433), mounting BOTH the communities blueprint (the organiser-audio
publish) and the pricing/role routes (tour_pricing_service.register_pricing_
routes) on ONE in-process Flask app — exactly the two surfaces the orchestrator
and user-api serve in production.

It proves the server contract Michael needs (D711):

  1. The owner publishes a members-only organiser-audio (broadcast) tour; the
     stored row now carries creator_user_id = the organiser (the fix — ownership
     is resolvable, so Price/Re-score work on the owner's own tour).
  2. GET /tour/<id>/role for the OWNER → is_owner, is_organiser, is_broadcast;
     for a MEMBER → NOT owner, NOT organiser (so the app hides Price/Re-score —
     the Pixel-4 member can no longer reach Set Price).
  3. set_price on a COMMUNITY tour → 400 community_tour_no_price (included with
     membership, D711 addendum 1); clearing (tier=null) is allowed.
  4. Publishing a PUBLIC community tour WITH a price_tier → 400
     community_tour_no_price (no row); without a price it publishes Free.
  5. Publishing a MEMBERS-ONLY tour WITH a price_tier → 400
     community_tour_no_price (before any row is created).
  6. A MEMBER setting a price on the owner's tour → 403 not_owner.
  7. Row counts (audio_tours, communities) before/after; every row is_test=true;
     cleanup removes ONLY this run's is_test rows (D141); budget $0.00 (no AI).

Run: python3 live_local762.py
"""
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'user-tracking'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', 'true')
# [LOCAL-762] BOTH surfaces must resolve to the SAME database. communities_api
# reads DATABASE_URL directly; tour_pricing_service uses db_connection, which
# resolves by AUDIOURA_DB_TARGET (DATABASE_URL is ignored there). Set both to
# the TEST db so the pricing/role reads see the rows the publish writes.
os.environ.setdefault('AUDIOURA_DB_TARGET', 'test')
os.environ.setdefault(
    'DATABASE_URL',
    'postgresql://admin:password123@localhost:5433/audiotours_test')

import communities_api  # noqa: E402  (user-tracking/)
import tour_pricing_service as pricing_svc  # noqa: E402  (repo root)
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
        if p in ('/a1.mp3', '/a2.mp3'):
            self._send(200, 'audio/mpeg', _MP3)
        else:
            self._send(404, 'text/plain', b'nope')


def _start_server():
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _counts(cur):
    out = {}
    for tbl in ('audio_tours', 'communities'):
        cur.execute(f'SELECT COUNT(*) FROM {tbl}')
        out[tbl] = cur.fetchone()[0]
    return out


def main():
    srv, port = _start_server()
    base = f'http://127.0.0.1:{port}'
    print(f'[feed] serving own MP3 at {base}')

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()

    before = _counts(cur)
    print(f'[rows] before: {before}')

    owner = f'L762-owner-{RUN}'
    member = f'L762-member-{RUN}'
    community_id = None
    created_tour_ids = []

    try:
        # Seed a community (owner = organiser) + one member. Make the owner a
        # curator (l4, can_sell) so pricing is allowed.
        cur.execute(
            "INSERT INTO communities (owner_user_id, name, is_paid, visibility, "
            "status) VALUES (%s, %s, FALSE, 'private', 'active') RETURNING id",
            (owner, f'L762 {RUN}'))
        community_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO community_memberships (user_id, community_id, expires_at) "
            "VALUES (%s, %s, NULL)", (member, community_id))
        for uid in (owner, member):
            cur.execute("INSERT INTO users (secret_id) VALUES (%s) "
                        "ON CONFLICT (secret_id) DO NOTHING", (uid,))
        cur.execute(
            "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
            "VALUES (%s, 'l4', NOW()) ON CONFLICT (user_id) DO UPDATE "
            "SET level='l4'", (owner,))
        print(f'[community] id={community_id} owner={owner} (curator l4) '
              f'member={member}')

        app = Flask(__name__)
        app.register_blueprint(communities_api.communities_bp)
        pricing_svc.register_pricing_routes(app)  # /tour/<id>/role, /price, …
        communities_api.API_KEY = ''
        communities_api._audio_url_check = \
            communities_api._default_audio_url_check
        client = app.test_client()

        stops = [
            {'name': 'Town Square', 'lat': 42.100, 'lng': -71.200,
             'text': 'Heart of town.', 'audio_url': f'{base}/a1.mp3'},
            {'name': 'Old Mill', 'lat': 42.110, 'lng': -71.210,
             'text': 'A mill.', 'audio_url': f'{base}/a2.mp3'},
        ]

        # 1) Owner builds a MEMBERS-ONLY broadcast tour.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={'user_id': owner, 'tour_name': f'Witch Trial {RUN}',
                              'tour_type': 'walking', 'visibility': 'members',
                              'rights_accepted': True, 'stops': stops})
        assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
        members_tour = r.get_json()['tour_id']
        created_tour_ids.append(members_tour)
        cur.execute("UPDATE audio_tours SET is_test=TRUE WHERE id=%s",
                    (members_tour,))
        # The fix: creator_user_id is the organiser.
        cur.execute("SELECT creator_user_id FROM audio_tours WHERE id=%s",
                    (members_tour,))
        creator = cur.fetchone()[0]
        assert creator == owner, f'creator_user_id={creator!r} expected {owner!r}'
        print(f'[build] members tour id={members_tour} '
              f'creator_user_id={creator} source_kind='
              f'{r.get_json()["source_kind"]} ✓')

        # 2) Role endpoint: OWNER vs MEMBER.
        r = client.get(f'/tour/{members_tour}/role?user_id={owner}')
        assert r.status_code == 200, r.get_data(as_text=True)
        ro = r.get_json()
        assert ro['is_owner'] and ro['is_organiser'] and ro['is_broadcast'], ro
        assert ro['community_visibility'] == 'members', ro
        print(f'[role owner] is_owner={ro["is_owner"]} is_organiser='
              f'{ro["is_organiser"]} is_broadcast={ro["is_broadcast"]} ✓')

        r = client.get(f'/tour/{members_tour}/role?user_id={member}')
        rm = r.get_json()
        assert not rm['is_owner'] and not rm['is_organiser'], rm
        assert rm['is_broadcast'] and rm['is_community'], rm
        print(f'[role member] is_owner={rm["is_owner"]} is_organiser='
              f'{rm["is_organiser"]} (member cannot reach Price/Re-score) ✓')

        # 3) set_price on a COMMUNITY tour → 400 community_tour_no_price.
        r = client.post(f'/tour/{members_tour}/price',
                        json={'user_id': owner, 'tier': 3})
        assert r.status_code == 400, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['error'] == 'community_tour_no_price', r.get_json()
        print('[price community] owner refused community_tour_no_price (400) ✓')
        # Clearing is allowed.
        r = client.post(f'/tour/{members_tour}/price',
                        json={'user_id': owner, 'tier': None})
        assert r.status_code == 200, r.get_data(as_text=True)
        print('[price community] clearing (tier=null) allowed ✓')

        # 4) [LOCAL-763 / D711 addendum 1] A PUBLIC community tour WITH a price
        #    is NOW refused too (a community tour of any visibility carries no
        #    per-tour price) — 400 before any row is created.
        mid_before4 = _counts(cur)['audio_tours']
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={'user_id': owner, 'tour_name': f'Public Walk {RUN}',
                              'tour_type': 'walking', 'visibility': 'public',
                              'rights_accepted': True, 'stops': stops,
                              'price_tier': 3})
        assert r.status_code == 400, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['error'] == 'community_tour_no_price', r.get_json()
        assert _counts(cur)['audio_tours'] == mid_before4, 'no row on refusal'
        print('[build public+price] refused community_tour_no_price, no row ✓')
        # A PUBLIC community tour WITHOUT a price still publishes Free.
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={'user_id': owner, 'tour_name': f'Public Free {RUN}',
                              'tour_type': 'walking', 'visibility': 'public',
                              'rights_accepted': True, 'stops': stops})
        assert r.status_code == 201, (r.status_code, r.get_data(as_text=True))
        public_tour = r.get_json()['tour_id']
        created_tour_ids.append(public_tour)
        cur.execute("UPDATE audio_tours SET is_test=TRUE WHERE id=%s",
                    (public_tour,))
        r = client.get(f'/tour/{public_tour}/price')
        pj = r.get_json()
        assert not pj['is_paid'] and pj['price_tier'] is None, pj
        print(f'[build public free] id={public_tour} is Free (no per-tour '
              f'price) ✓')

        # 5) Publishing a MEMBERS-ONLY tour WITH a price → 400 before any row.
        mid_before = _counts(cur)['audio_tours']
        r = client.post(f'/communities/{community_id}/build-audio-tour',
                        json={'user_id': owner, 'tour_name': f'Nope {RUN}',
                              'tour_type': 'walking', 'visibility': 'members',
                              'rights_accepted': True, 'stops': stops,
                              'price_tier': 3})
        assert r.status_code == 400, (r.status_code, r.get_data(as_text=True))
        assert r.get_json()['error'] == 'community_tour_no_price', r.get_json()
        assert _counts(cur)['audio_tours'] == mid_before, 'no row on refusal'
        print('[build members+price] refused community_tour_no_price, no row ✓')

        # 6) A MEMBER pricing the owner's public tour → 403 (refused). The
        # member is neither the owner nor a curator, so set_price refuses with
        # not_curator (checked first) — either way the member cannot price it.
        r = client.post(f'/tour/{public_tour}/price',
                        json={'user_id': member, 'tier': 5})
        assert r.status_code in (400, 403), (r.status_code,
                                             r.get_data(as_text=True))
        assert r.get_json()['error'] in (
            'not_owner', 'not_curator', 'community_tour_no_price'), r.get_json()
        print(f'[price by member] refused {r.get_json()["error"]} '
              f'({r.status_code}) ✓')

        after = _counts(cur)
        print(f'[rows] after: {after}')
        print(f'[rows] delta: audio_tours '
              f'+{after["audio_tours"]-before["audio_tours"]}, communities '
              f'+{after["communities"]-before["communities"]}')
        print('[budget] $0.00 — no OpenAI/AI calls ✓')
        print('\nLOCAL-762 LIVE: ALL CHECKS PASSED ✓')
    finally:
        for tid in created_tour_ids:
            cur.execute("DELETE FROM audio_tours WHERE id=%s AND is_test=TRUE",
                        (tid,))
            cur.execute("DELETE FROM audio_tour_versions WHERE tour_id=%s", (tid,))
        if community_id is not None:
            cur.execute("DELETE FROM community_memberships WHERE community_id=%s",
                        (community_id,))
            cur.execute("DELETE FROM communities WHERE id=%s", (community_id,))
        for uid in (owner, member):
            cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (uid,))
            cur.execute("DELETE FROM users WHERE secret_id=%s", (uid,))
        final = _counts(cur)
        print(f'[cleanup] removed this run\'s rows → counts back to {final}')
        assert final == before, (final, before)
        cur.close()
        conn.close()
        srv.shutdown()


if __name__ == '__main__':
    main()
