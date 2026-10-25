#!/usr/bin/env python3
"""test_local762_tour_role_and_pricing.py — LOCAL-762 (D711).

Server pieces for the owner-only Price/Re-score Listen ⋮ menu, the role line, and
pricing a community tour:

PART A — hermetic (a scripted fake cursor, no Postgres):
  * the organiser-audio publish (communities_api.build_audio_tour) now stamps
    audio_tours.creator_user_id = the organiser on the NEW INSERT. Without it
    ownership can never be resolved for an organiser-audio tour (there is no
    tour_requests row to fall back on), which is why the organiser was refused
    Price/Re-score on his OWN tour. RED on the pre-LOCAL-762 code, where the
    INSERT column list has no creator_user_id.

PART B — DB-backed (own is_test rows, TEST-762- prefix, prefix-scoped cleanup,
D141-safe — mirrors test_local677_paid_tours):
  * tour_role reports is_owner / is_broadcast / is_community / is_organiser /
    community_visibility for every case the role line distinguishes;
  * [LOCAL-763 / D711 addendum 1] set_price on ANY community tour (members-only
    OR public) is refused community_tour_no_price (mapped to HTTP 400 by the
    route); clearing (tier=None) is still allowed;
  * GET /tour/<id>/role returns the role block.

Run: python3 -m pytest tests/test_local762_tour_role_and_pricing.py -q
"""
import os
import sys
import unittest

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_UT, _ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)


# ════════════════════════════════════════════════════════════════════════════
# PART A — organiser-audio publish stamps creator_user_id (hermetic)
# ════════════════════════════════════════════════════════════════════════════
import communities_api  # noqa: E402  (user-tracking/)


class _FakeCursor:
    """Scripted cursor (same shape as test_local754b). Each execute matches the
    FIRST (needle, result) whose needle is a substring of the normalised SQL;
    result is a list of rows OR callable(params)->rows. Captured writes land in
    self.writes so a test can assert the SQL + params that were stored."""

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


_OWNER = 'TEST-762-owner'
_COMMUNITY_ID = 7


def _community_row_rows(owner):
    """The communities row _community_row reads (order matches
    communities_api._community_row). Only owner_user_id + disabled matter."""
    return [(
        _COMMUNITY_ID, owner, 'The Owls', 'desc', 'Org', None, None, None,
        None, None, False, True, 'listed', 42.1, -71.2, 'CODE1234', None, False,
        'active', None, None, None, None, None, 'week',
    )]


class OrganiserAudioStampsCreatorTest(unittest.TestCase):
    def setUp(self):
        communities_api.API_KEY = ''
        os.environ['ALLOW_UNAUTHENTICATED_ENTITLEMENTS'] = 'true'
        from flask import Flask
        flask_app = Flask(__name__)
        flask_app.register_blueprint(communities_api.communities_bp)
        self.client = flask_app.test_client()
        self._orig_get_db = communities_api._get_db
        communities_api._audio_url_check = lambda url: (True, 'audio/mpeg', 1000)

    def tearDown(self):
        communities_api._get_db = self._orig_get_db

    def _install(self, plan):
        writes = []
        communities_api._get_db = lambda: _FakeConn(plan, writes)
        return writes

    def _body(self, **over):
        body = {
            'user_id': _OWNER,
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

    def test_new_publish_stamps_creator_user_id_as_the_organiser(self):
        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
            ("insert into audio_tours", lambda params: [(99,)]),
            ("max(version_no)", [(None,)]),
        ]
        writes = self._install(plan)
        r = self.client.post(f'/communities/{_COMMUNITY_ID}/build-audio-tour',
                             json=self._body())
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

        insert_write = next(
            w for w in writes if 'insert into audio_tours' in w[0])
        sql, params = insert_write
        # The INSERT column list must name creator_user_id …
        self.assertIn('creator_user_id', sql,
                      "organiser-audio INSERT must stamp creator_user_id")
        # … and the organiser's user_id must be among the bound params.
        self.assertIn(_OWNER, list(params),
                      "creator_user_id must be bound to the organiser's id")

    def test_public_publish_with_price_tier_is_refused_400(self):
        # [LOCAL-763 / D711 addendum 1] A community tour of ANY visibility
        # carries no per-tour price, so a PUBLIC build with a price_tier is now
        # refused community_tour_no_price (400) before any row is created.
        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
        ]
        writes = self._install(plan)
        r = self.client.post(
            f'/communities/{_COMMUNITY_ID}/build-audio-tour',
            json=self._body(visibility='public', price_tier=3))
        self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
        self.assertEqual(r.get_json()['error'], 'community_tour_no_price')
        self.assertFalse(
            any('insert into audio_tours' in w[0] for w in writes),
            "a refused price must not create a tour")

    def test_members_only_publish_with_price_tier_is_refused_400(self):
        # [LOCAL-763 / D711 addendum 1] A members-only community tour cannot be
        # priced either — refused community_tour_no_price.
        plan = [
            ("from communities where id", _community_row_rows(_OWNER)),
        ]
        writes = self._install(plan)
        r = self.client.post(
            f'/communities/{_COMMUNITY_ID}/build-audio-tour',
            json=self._body(visibility='members', price_tier=3))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()['error'], 'community_tour_no_price')
        self.assertFalse(
            any('insert into audio_tours' in w[0] for w in writes),
            "a refused price must not create a tour")


# ════════════════════════════════════════════════════════════════════════════
# PART B — tour_role, members-only pricing, role endpoint (DB-backed)
# ════════════════════════════════════════════════════════════════════════════
from db_connection import get_connection, check_db_available  # noqa: E402
import tour_pricing_service as pricing_svc  # noqa: E402

TEST_PREFIX = "TEST-762-"


@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(conn):
    cur = conn.cursor()
    for table, col in (
        ("tour_unlocks", "user_id"),
        ("tour_requests", "secret_id"),
        ("device_entitlement", "user_id"),
        ("users", "secret_id"),
    ):
        try:
            cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE %s",
                        (TEST_PREFIX + "%",))
            keys = [row[0] for row in cur.fetchall()
                    if row[0] and str(row[0]).startswith(TEST_PREFIX)]
            for k in keys:
                cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (k,))
            conn.commit()
        except Exception:
            conn.rollback()
    # Tours: only our TEST-762- named, is_test rows, by exact id (D141).
    try:
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name LIKE %s AND is_test = TRUE",
            (TEST_PREFIX + "%",))
        for (tid,) in cur.fetchall():
            cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE",
                        (tid,))
        conn.commit()
    except Exception:
        conn.rollback()
    # Communities we made (name prefixed); tours pointing at them are gone above.
    try:
        cur.execute("SELECT id FROM communities WHERE name LIKE %s",
                    (TEST_PREFIX + "%",))
        for (cid,) in cur.fetchall():
            cur.execute("DELETE FROM communities WHERE id = %s", (cid,))
        conn.commit()
    except Exception:
        conn.rollback()
    cur.close()


def _seed_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (secret_id) VALUES (%s) "
                "ON CONFLICT (secret_id) DO NOTHING", (user_id,))
    conn.commit()
    cur.close()


def _set_level(conn, user_id, level):
    _seed_user(conn, user_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
        "VALUES (%s, %s, NOW()) "
        "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level, "
        "updated_at = NOW()",
        (user_id, level))
    conn.commit()
    cur.close()


def _make_curator(conn, user_id):
    """A device whose level has can_sell=TRUE. l4 is a Curator level (D613)."""
    _set_level(conn, user_id, "l4")


def _seed_community(conn, owner_user_id, name):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO communities (owner_user_id, name, visibility) "
        "VALUES (%s, %s, 'private') RETURNING id",
        (owner_user_id, name))
    cid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return cid


def _seed_tour(conn, name, creator_user_id=None, community_id=None,
               community_visibility=None, source_kind=None, price_tier=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, content_language,
                                 language, creator_user_id, community_id,
                                 community_visibility, source_kind, price_tier,
                                 is_test)
        VALUES (%s, %s, 'en', 'en', %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (name, name, creator_user_id, community_id, community_visibility,
         source_kind, price_tier))
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return tid


# ─── tour_role ────────────────────────────────────────────────────────────────

def test_role_plain_owned_tour(db):
    _cleanup(db)
    try:
        owner = f"{TEST_PREFIX}role-owner"
        _seed_user(db, owner)
        tid = _seed_tour(db, f"{TEST_PREFIX}plain", creator_user_id=owner)
        role = pricing_svc.tour_role(owner, tid)
        assert role["is_owner"] is True
        assert role["is_community"] is False
        assert role["is_broadcast"] is False
        assert role["is_organiser"] is False
    finally:
        _cleanup(db)


def test_role_member_on_community_tour_is_not_owner(db):
    _cleanup(db)
    try:
        organiser = f"{TEST_PREFIX}org"
        member = f"{TEST_PREFIX}member"
        _seed_user(db, organiser)
        _seed_user(db, member)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}Salem")
        tid = _seed_tour(db, f"{TEST_PREFIX}ctour", creator_user_id=organiser,
                         community_id=cid, community_visibility='members')
        role = pricing_svc.tour_role(member, tid)
        assert role["is_owner"] is False
        assert role["is_community"] is True
        assert role["is_organiser"] is False
        assert role["community_id"] == cid
        assert role["community_name"] == f"{TEST_PREFIX}Salem"
        assert role["community_visibility"] == 'members'
    finally:
        _cleanup(db)


def test_role_organiser_on_own_community_tour(db):
    _cleanup(db)
    try:
        organiser = f"{TEST_PREFIX}org2"
        _seed_user(db, organiser)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}Owls")
        tid = _seed_tour(db, f"{TEST_PREFIX}ctour2", creator_user_id=organiser,
                         community_id=cid, community_visibility='public')
        role = pricing_svc.tour_role(organiser, tid)
        assert role["is_owner"] is True
        assert role["is_community"] is True
        assert role["is_organiser"] is True
        assert role["is_broadcast"] is False
        assert role["community_visibility"] == 'public'
    finally:
        _cleanup(db)


def test_role_broadcast_tour(db):
    _cleanup(db)
    try:
        organiser = f"{TEST_PREFIX}org3"
        member = f"{TEST_PREFIX}member3"
        _seed_user(db, organiser)
        _seed_user(db, member)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}TV funs")
        tid = _seed_tour(db, f"{TEST_PREFIX}bcast", creator_user_id=organiser,
                         community_id=cid, community_visibility='members',
                         source_kind='organiser_audio')
        # The member sees a Broadcast community tour, is not owner/organiser.
        role_m = pricing_svc.tour_role(member, tid)
        assert role_m["is_broadcast"] is True
        assert role_m["is_owner"] is False
        assert role_m["is_organiser"] is False
        # The organiser owns it and the community.
        role_o = pricing_svc.tour_role(organiser, tid)
        assert role_o["is_broadcast"] is True
        assert role_o["is_owner"] is True
        assert role_o["is_organiser"] is True
    finally:
        _cleanup(db)


# ─── pricing a community tour (members-only refuse, public ok) ────────────────

def test_members_only_community_tour_cannot_be_priced(db):
    _cleanup(db)
    try:
        organiser = f"{TEST_PREFIX}price-org"
        _make_curator(db, organiser)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}dues")
        tid = _seed_tour(db, f"{TEST_PREFIX}members tour",
                         creator_user_id=organiser, community_id=cid,
                         community_visibility='members')
        with pytest.raises(pricing_svc.PricingError) as ei:
            pricing_svc.set_price(organiser, tid, 3)
        # [LOCAL-763 / D711 addendum 1] renamed error code.
        assert ei.value.code == "community_tour_no_price"
        # Clearing (tier=None) is still allowed on a community tour.
        cleared = pricing_svc.set_price(organiser, tid, None)
        assert cleared["is_paid"] is False
    finally:
        _cleanup(db)


def test_public_community_tour_cannot_be_priced_either(db):
    # [LOCAL-763 / D711 addendum 1] A PUBLIC community tour is also refused — a
    # community tour of any visibility is included with membership.
    _cleanup(db)
    try:
        organiser = f"{TEST_PREFIX}price-org2"
        _make_curator(db, organiser)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}public")
        tid = _seed_tour(db, f"{TEST_PREFIX}public tour",
                         creator_user_id=organiser, community_id=cid,
                         community_visibility='public')
        with pytest.raises(pricing_svc.PricingError) as ei:
            pricing_svc.set_price(organiser, tid, 3)
        assert ei.value.code == "community_tour_no_price"
        # Clearing (tier=None) is still allowed.
        cleared = pricing_svc.set_price(organiser, tid, None)
        assert cleared["is_paid"] is False
    finally:
        _cleanup(db)


# ─── role endpoint ────────────────────────────────────────────────────────────

def test_role_endpoint_returns_block(db):
    _cleanup(db)
    try:
        from flask import Flask
        organiser = f"{TEST_PREFIX}ep-org"
        _seed_user(db, organiser)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}EP")
        tid = _seed_tour(db, f"{TEST_PREFIX}ep tour", creator_user_id=organiser,
                         community_id=cid, community_visibility='public')
        app = Flask(__name__)
        pricing_svc.register_pricing_routes(app)
        client = app.test_client()
        r = client.get(f'/tour/{tid}/role?user_id={organiser}')
        assert r.status_code == 200
        j = r.get_json()
        assert j["is_owner"] is True
        assert j["is_organiser"] is True
        assert j["community_visibility"] == 'public'
    finally:
        _cleanup(db)


def test_set_price_route_maps_community_tour_to_400(db):
    _cleanup(db)
    try:
        from flask import Flask
        organiser = f"{TEST_PREFIX}ep-org2"
        _make_curator(db, organiser)
        cid = _seed_community(db, organiser, f"{TEST_PREFIX}EP2")
        tid = _seed_tour(db, f"{TEST_PREFIX}ep2 tour", creator_user_id=organiser,
                         community_id=cid, community_visibility='members')
        app = Flask(__name__)
        pricing_svc.register_pricing_routes(app)
        client = app.test_client()
        r = client.post(f'/tour/{tid}/price',
                        json={'user_id': organiser, 'tier': 3})
        assert r.status_code == 400
        assert r.get_json()["error"] == "community_tour_no_price"
    finally:
        _cleanup(db)


if __name__ == "__main__":
    unittest.main()
