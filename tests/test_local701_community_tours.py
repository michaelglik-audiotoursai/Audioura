#!/usr/bin/env python3
"""test_local701_community_tours.py — LOCAL-701 / D663 §2 + §3.

Proves community tours end to end:

  §2 WHO MAY CHARGE (live DB, migration 035 applied):
    * plans.can_sell is TRUE for l2, l3, l4, tester and FALSE for l1.

  §3 A TOUR MADE FOR A COMMUNITY:
    Service (live DB, community_tours_service):
      * tag_community_tour stores community_id + visibility on the tour;
      * only the OWNER may tag (not_owner for a stranger);
      * a PUBLIC tour needs coordinates (public_needs_location);
      * community_tours_for_member lists the tours for an active member/owner
        and returns an EMPTY list for a non-member (members-only hidden);
      * the community download decision allows a member (200) and refuses a
        non-member with 402 membership_required {community_id, tour_id};
      * D660 does not touch a community tour (its price_tier stays NULL).

    Listing (hermetic, map_delivery/app.py through a scripted fake cursor — no
    Postgres, writes NO rows, the same style as test_local687_content_rating):
      * a MEMBERS-ONLY community tour is HIDDEN from /tours-near and /search;
      * a PUBLIC community tour is LISTED with the community badge
        (badge='community', community_id, community_name);
      * the download gate returns 402 membership_required for a non-member of a
        community tour and 200 for an active member;
      * content rating STILL applies to a community tour (a not_allowed public
        community tour is hidden even though it is public).

Run: python3 -m pytest tests/test_local701_community_tours.py -q
"""
import os
import sys
import uuid
import datetime
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
for p in (_ROOT, _HERE, _MAPDIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import app as map_app  # noqa: E402  (map_delivery/app.py)
import community_tours_service as cts  # noqa: E402  (repo root)
from db_connection import get_connection, get_database_url  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# PART A — hermetic listing + download gate (fake cursor, no DB)
# ════════════════════════════════════════════════════════════════════════════
class _FakeCursor:
    """A scripted cursor: each execute matches the FIRST (needle, result) whose
    needle is a substring of the normalised SQL. result is a list of rows the
    following fetchone/fetchall drain. A needle may map to a callable taking the
    params, for queries whose answer depends on the id (membership/tag)."""

    def __init__(self, plan):
        self._plan = plan
        self._rows = []
        self.connection = self

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
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


def _install_db(plan):
    map_app.get_db_connection = lambda: _FakeConn(plan)


_COL_RATING = ("content_rating'", [(1,)])        # _has_content_rating_column probe
_COL_COMMUNITY = ("'community_id', 'community_visibility'", [(2,)])  # community cols probe

_CREATED = datetime.datetime(2026, 10, 1, 8, 30, 0)


def _row(tid, name, *, lat=43.70, lng=7.26, content_rating=None, review_status=None):
    """A 24-column /tours-near-shaped row (same shape as test_local687).
    [LOCAL-711] short_title SELECTed just after price_tier (None here)."""
    return (tid, name, name.lower(), lat, lng, 3,
            "en", None, None, None, _CREATED, None, None,
            None, None, None, None, False, None,
            None,                 # [LOCAL-711] short_title
            "en", None,
            content_rating, review_status)


def _reset_caches():
    for attr in ("_HAS_CONTENT_RATING_COLUMN", "_HAS_SOURCE_VERSION",
                 "_HAS_TOUR_RATINGS", "_HAS_VERIFIED_COLUMN",
                 "_HAS_IS_PAID_COLUMN", "_HAS_PRICE_TIER_COLUMN",
                 "_HAS_COMMUNITY_COLUMNS"):
        setattr(map_app, attr, None)


class ListingVisibilityTest(unittest.TestCase):
    """Members-only hidden, public badged — through the real /tours-near code."""

    def setUp(self):
        self._orig_db = map_app.get_db_connection
        _reset_caches()
        self.client = map_app.app.test_client()

    def tearDown(self):
        map_app.get_db_connection = self._orig_db
        _reset_caches()

    def _near(self, rows, tags, names, adult=False):
        plan = [
            _COL_RATING,
            _COL_COMMUNITY,
            # The batch community-tags query (id = ANY): return the scripted tags.
            ("from audio_tours where id = any", tags),
            # Community name lookup.
            ("select name from communities where id =",
             lambda p: [(names.get(int(p[0])),)] if p and int(p[0]) in names else []),
            # The main list query must come AFTER the more specific needles above.
            ("from audio_tours t", rows),
        ]
        _install_db(plan)
        q = "/tours-near/43.70/7.26?radius=50" + ("&adult=1" if adult else "")
        resp = self.client.get(q)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["tours"]

    def test_members_only_hidden_public_listed_with_badge(self):
        rows = [
            _row(1, "Ordinary Tour"),
            _row(2, "Members Tour"),
            _row(3, "Public Community Tour"),
        ]
        tags = [(2, 7, "members"), (3, 7, "public")]  # 1 is not a community tour
        names = {7: "The Owls"}
        tours = self._near(rows, tags, names)
        by_id = {t["id"]: t for t in tours}
        # Members-only (2) hidden; ordinary (1) and public (3) listed.
        self.assertIn(1, by_id)
        self.assertNotIn(2, by_id)
        self.assertIn(3, by_id)
        # The public community tour carries the badge.
        self.assertEqual(by_id[3]["badge"], "community")
        self.assertEqual(by_id[3]["community_id"], 7)
        self.assertEqual(by_id[3]["community_name"], "The Owls")
        self.assertEqual(by_id[3]["community_visibility"], "public")
        # The ordinary tour has no community fields.
        self.assertNotIn("badge", by_id[1])

    def test_content_rating_still_applies_to_public_community_tour(self):
        """A public community tour that is not_allowed is still hidden (D656
        content rating applies to community tours too)."""
        rows = [
            _row(1, "Good Public", content_rating="general"),
            _row(2, "Blocked Public", content_rating="not_allowed",
                 review_status="pending"),
        ]
        tags = [(1, 7, "public"), (2, 7, "public")]
        tours = self._near(rows, tags, {7: "The Owls"})
        ids = {t["id"] for t in tours}
        self.assertEqual(ids, {1})  # not_allowed hidden despite being public


class DownloadGateTest(unittest.TestCase):
    """The community download gate: member 200, non-member 402."""

    def tearDown(self):
        _reset_caches()

    def _gate(self, user_id, *, tag, owner, member_expiry, member_present):
        _reset_caches()
        plan = [
            _COL_COMMUNITY,
            # _community_tag (COALESCE … LEFT JOIN) → (community_id, visibility)
            ("coalesce(orig.community_id, t.community_id)", [tag]),
            # _is_active_member: owner lookup, then membership expiry lookup.
            ("select owner_user_id from communities", [(owner,)]),
            ("select expires_at from community_memberships",
             ([(member_expiry,)] if member_present else [])),
        ]
        cur = _FakeCursor(plan)
        return map_app._download_gate(cur, user_id, 3)

    def test_non_member_gets_402_membership_required(self):
        allowed, deny = self._gate(
            "stranger", tag=(7, "public"), owner="owner-x",
            member_expiry=None, member_present=False)
        self.assertFalse(allowed)
        self.assertEqual(deny["error"], "membership_required")
        self.assertEqual(deny["community_id"], 7)
        self.assertEqual(deny["tour_id"], 3)

    def test_owner_allowed(self):
        allowed, deny = self._gate(
            "owner-x", tag=(7, "members"), owner="owner-x",
            member_expiry=None, member_present=False)
        self.assertTrue(allowed)
        self.assertIsNone(deny)

    def test_active_member_allowed(self):
        future = datetime.datetime.utcnow() + datetime.timedelta(days=5)
        allowed, deny = self._gate(
            "member-y", tag=(7, "public"), owner="owner-x",
            member_expiry=future, member_present=True)
        self.assertTrue(allowed)
        self.assertIsNone(deny)

    def test_expired_member_refused(self):
        past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        allowed, deny = self._gate(
            "member-y", tag=(7, "public"), owner="owner-x",
            member_expiry=past, member_present=True)
        self.assertFalse(allowed)
        self.assertEqual(deny["error"], "membership_required")

    def test_non_community_tour_falls_through(self):
        # tag (None, None) → not relevant; the gate returns (True, None) for a
        # free row (the price-tier path then runs; here it's not a community
        # tour and _row_price_tier reads NULL → allowed).
        _reset_caches()
        plan = [
            _COL_COMMUNITY,
            ("coalesce(orig.community_id, t.community_id)", [(None, None)]),
            # price_tier column probe + value → free
            ("column_name = 'price_tier'", [(1,)]),
            ("select price_tier from audio_tours", [(None,)]),
            ("select original_tour_id from audio_tours", [(None,)]),
        ]
        cur = _FakeCursor(plan)
        allowed, deny = map_app._download_gate(cur, "anyone", 1)
        self.assertTrue(allowed)
        self.assertIsNone(deny)


# ════════════════════════════════════════════════════════════════════════════
# PART B — live DB: can_sell per plan + the service (needs audiotours_test)
# ════════════════════════════════════════════════════════════════════════════
def _db_up():
    try:
        c = get_connection()
        c.close()
        return True
    except SystemExit:
        return False
    except Exception:
        return False


TEST_PREFIX = "TEST-701-"


@unittest.skipUnless(_db_up(), "test Postgres not reachable")
class CanSellPerPlanTest(unittest.TestCase):
    """D663 §2: can_sell TRUE for l2/l3/l4/tester, FALSE for l1."""

    def test_can_sell_per_plan(self):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT plan_id, can_sell FROM plans "
                "WHERE plan_id IN ('l1','l2','l3','l4','tester')")
            got = {pid: bool(cs) for pid, cs in cur.fetchall()}
            self.assertFalse(got.get("l1"), "l1 (Introduction) must NOT sell")
            for lvl in ("l2", "l3", "l4", "tester"):
                self.assertTrue(got.get(lvl), f"{lvl} must have can_sell=TRUE")
        finally:
            conn.close()


@unittest.skipUnless(_db_up(), "test Postgres not reachable")
class CommunityTourServiceTest(unittest.TestCase):
    """D663 §3 service behaviour against the live test DB. Every row created here
    is cleaned up in tearDown; only TEST-701- rows are touched."""

    def setUp(self):
        # Fresh module-level schema probe each test (the column set is stable).
        cts._HAS_COMMUNITY_COLUMNS = None
        self.conn = get_connection()
        self.cur = self.conn.cursor()
        self._owner = TEST_PREFIX + "owner-" + uuid.uuid4().hex[:8]
        self._member = TEST_PREFIX + "member-" + uuid.uuid4().hex[:8]
        self._stranger = TEST_PREFIX + "stranger-" + uuid.uuid4().hex[:8]
        self._community_id = None
        self._tour_ids = []

    def tearDown(self):
        try:
            if self._community_id is not None:
                self.cur.execute(
                    "DELETE FROM community_memberships WHERE community_id = %s",
                    (self._community_id,))
            for tid in self._tour_ids:
                self.cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
            if self._community_id is not None:
                self.cur.execute("DELETE FROM communities WHERE id = %s",
                                 (self._community_id,))
            self.conn.commit()
        finally:
            self.cur.close()
            self.conn.close()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _make_community(self, name_suffix="A"):
        self.cur.execute(
            "INSERT INTO communities (owner_user_id, name, is_paid, visibility) "
            "VALUES (%s, %s, FALSE, 'private') RETURNING id",
            (self._owner, TEST_PREFIX + name_suffix + "-" + uuid.uuid4().hex[:6]))
        self._community_id = self.cur.fetchone()[0]
        self.conn.commit()
        return self._community_id

    def _make_tour(self, name, lat=43.70, lng=7.26):
        self.cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, lat, lng) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (TEST_PREFIX + name, name, lat, lng))
        tid = self.cur.fetchone()[0]
        self.conn.commit()
        self._tour_ids.append(tid)
        return tid

    def _join_member(self, expires_at=None):
        self.cur.execute(
            "INSERT INTO community_memberships (user_id, community_id, expires_at) "
            "VALUES (%s, %s, %s)",
            (self._member, self._community_id, expires_at))
        self.conn.commit()

    # ── tests ────────────────────────────────────────────────────────────────
    def test_tag_stores_community_and_visibility(self):
        cid = self._make_community()
        tid = self._make_tour("tagged")
        ok = cts.tag_community_tour(self.cur, tid, cid, visibility="members",
                                    owner_user_id=self._owner)
        self.conn.commit()
        self.assertTrue(ok)
        tag = cts.community_tour_tag(self.cur, tid)
        self.assertEqual(tag["community_id"], cid)
        self.assertEqual(tag["community_visibility"], "members")
        # D660 does not touch a community tour: price_tier stays NULL.
        self.cur.execute("SELECT price_tier FROM audio_tours WHERE id = %s", (tid,))
        self.assertIsNone(self.cur.fetchone()[0])

    def test_only_owner_may_tag(self):
        cid = self._make_community()
        tid = self._make_tour("owned")
        with self.assertRaises(cts.CommunityTourError) as ctx:
            cts.tag_community_tour(self.cur, tid, cid, visibility="members",
                                   owner_user_id=self._stranger)
        self.conn.rollback()
        self.assertEqual(ctx.exception.code, "not_owner")

    def test_public_tour_needs_location(self):
        cid = self._make_community()
        tid = self._make_tour("nocoords", lat=None, lng=None)
        with self.assertRaises(cts.CommunityTourError) as ctx:
            cts.tag_community_tour(self.cur, tid, cid, visibility="public",
                                   owner_user_id=self._owner)
        self.conn.rollback()
        self.assertEqual(ctx.exception.code, "public_needs_location")

    def test_member_sees_tours_non_member_sees_none(self):
        cid = self._make_community()
        tid = self._make_tour("members-list")
        cts.tag_community_tour(self.cur, tid, cid, visibility="members",
                               owner_user_id=self._owner)
        self.conn.commit()
        # The owner always sees the list.
        owner_view = cts.community_tours_for_member(self._owner, cid)
        self.assertTrue(owner_view["is_member"])
        self.assertEqual([t["id"] for t in owner_view["tours"]], [tid])
        # A non-member sees an empty list (members-only hidden).
        stranger_view = cts.community_tours_for_member(self._stranger, cid)
        self.assertFalse(stranger_view["is_member"])
        self.assertEqual(stranger_view["tours"], [])
        # An active member sees it.
        self._join_member(expires_at=None)  # free membership never expires
        member_view = cts.community_tours_for_member(self._member, cid)
        self.assertTrue(member_view["is_member"])
        self.assertEqual([t["id"] for t in member_view["tours"]], [tid])

    def test_download_decision_member_200_non_member_402(self):
        cid = self._make_community()
        tid = self._make_tour("dl-gate")
        cts.tag_community_tour(self.cur, tid, cid, visibility="public",
                               owner_user_id=self._owner)
        self.conn.commit()
        # Non-member → 402 membership_required.
        relevant, allowed, deny = cts.community_download_decision(
            self.cur, self._stranger, tid)
        self.assertTrue(relevant)
        self.assertFalse(allowed)
        self.assertEqual(deny["error"], "membership_required")
        self.assertEqual(deny["community_id"], cid)
        self.assertEqual(deny["tour_id"], tid)
        # Active member → allowed (200), no D660 consumption.
        self._join_member(expires_at=None)
        relevant, allowed, deny = cts.community_download_decision(
            self.cur, self._member, tid)
        self.assertTrue(relevant)
        self.assertTrue(allowed)
        self.assertIsNone(deny)

    def test_ordinary_tour_not_relevant_to_community_gate(self):
        tid = self._make_tour("ordinary")  # never tagged
        relevant, allowed, deny = cts.community_download_decision(
            self.cur, self._stranger, tid)
        self.assertFalse(relevant)
        self.assertTrue(allowed)
        self.assertIsNone(deny)


if __name__ == "__main__":
    unittest.main(verbosity=2)
