#!/usr/bin/env python3
"""test_local752_listed_default_public.py — LOCAL-752 B (RED first).

DECISION D706 (LEAD 2026-10-23): for a LISTED community, a NEW tour's default
visibility is PUBLIC (it shows on /tours-near, /search and the map with the
community badge; download still needs an active membership → non-member 402
membership_required → join flow). Members-only stays a choice in Generate. A
PRIVATE community keeps the members-only default. The organiser can change an
existing tour's visibility from the community page — OWNER ONLY, server-enforced.

Three pure helpers in community_tours_service carry the decision so the
orchestrator (tagging), the visibility-change route and this test share one
implementation, hermetically (a scripted fake cursor, no Postgres):

  1. default_visibility_for_community(cur, community_id, explicit) —
       * explicit given ('members'/'public')  → that value (the organiser chose);
       * explicit absent + community 'listed'  → 'public'   (D706);
       * explicit absent + community 'private' → 'members'  (unchanged default);
       * unknown/disabled community             → 'members'  (safe default).
  2. set_tour_visibility(cur, tour_id, community_id, visibility, owner_user_id) —
       OWNER ONLY: raises CommunityTourError('not_owner') for a non-owner; writes
       the new visibility on the ORIGINAL row for the owner.
  3. community_download_decision — already returns 402 membership_required for a
       non-member of a community tour (regression guard that a PUBLIC community
       tour still gates download on membership).

Run: python3 -m pytest tests/test_local752_listed_default_public.py -q
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import community_tours_service as cts  # noqa: E402


class _FakeCursor:
    """A scripted cursor. `communities` maps id→(owner, disabled, visibility).
    `tours` maps id→dict(community_id, community_visibility, lat, lng,
    original_tour_id). `memberships` is a set of (user_id, community_id)."""

    def __init__(self, communities, tours, memberships):
        self.communities = communities
        self.tours = tours
        self.memberships = memberships
        self._rows = []
        self.connection = self
        # Record UPDATEs so the test can assert the written visibility.
        self.updates = []

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split()).lower()
        params = params or ()
        cts._HAS_COMMUNITY_COLUMNS = True  # force feature ON for the test

        if "information_schema" in s:
            self._rows = [(2,)]  # both community columns present
            return
        if s.startswith("select owner_user_id, disabled from communities"):
            (cid,) = params
            row = self.communities.get(int(cid))
            self._rows = [(row[0], row[1])] if row else []
            return
        if "select visibility from communities" in s:
            (cid,) = params
            row = self.communities.get(int(cid))
            self._rows = [(row[2],)] if row else []
            return
        if s.startswith("select 1 from audio_tours where id"):
            (tid,) = params
            self._rows = [(1,)] if int(tid) in self.tours else []
            return
        if "select lat, lng from audio_tours" in s:
            (tid,) = params
            t = self.tours.get(int(tid), {})
            self._rows = [(t.get("lat"), t.get("lng"))]
            return
        if s.startswith("update audio_tours set community_visibility"):
            # params: (visibility, tour_id)
            self.updates.append(params)
            self._rows = []
            return
        if "coalesce(orig.community_id" in s:
            (tid,) = params
            t = self.tours.get(int(tid), {})
            self._rows = [(t.get("community_id"), t.get("community_visibility"))]
            return
        if s.startswith("select expires_at from community_memberships"):
            uid, cid = params
            if (str(uid), int(cid)) in self.memberships:
                self._rows = [(None,)]  # perpetual membership
            else:
                self._rows = []
            return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def rollback(self):
        pass


def _cur():
    communities = {
        10: ("owner-10", False, "listed"),    # a LISTED community
        20: ("owner-20", False, "private"),   # a PRIVATE community
    }
    tours = {
        736: {"community_id": 10, "community_visibility": "public",
              "lat": 42.5, "lng": -70.9, "original_tour_id": None},
    }
    memberships = set()  # no members → download gate refuses non-members
    return _FakeCursor(communities, tours, memberships)


class DefaultVisibilityTest(unittest.TestCase):
    def setUp(self):
        cts._HAS_COMMUNITY_COLUMNS = True

    def test_helper_exists(self):
        self.assertTrue(
            hasattr(cts, "default_visibility_for_community"),
            "default_visibility_for_community is missing — a listed community's "
            "new tours cannot default to public (LOCAL-752 B / D706).")

    def test_listed_defaults_public_when_no_explicit(self):
        cur = _cur()
        self.assertEqual(
            cts.default_visibility_for_community(cur, 10, None), "public")
        self.assertEqual(
            cts.default_visibility_for_community(cur, 10, ""), "public")

    def test_private_defaults_members_when_no_explicit(self):
        cur = _cur()
        self.assertEqual(
            cts.default_visibility_for_community(cur, 20, None), "members")

    def test_explicit_choice_wins_on_listed(self):
        cur = _cur()
        # The organiser explicitly chose members-only on a listed community.
        self.assertEqual(
            cts.default_visibility_for_community(cur, 10, "members"), "members")
        self.assertEqual(
            cts.default_visibility_for_community(cur, 10, "public"), "public")

    def test_unknown_community_safe_default_members(self):
        cur = _cur()
        self.assertEqual(
            cts.default_visibility_for_community(cur, 999, None), "members")


class SetVisibilityOwnerOnlyTest(unittest.TestCase):
    def setUp(self):
        cts._HAS_COMMUNITY_COLUMNS = True

    def test_helper_exists(self):
        self.assertTrue(
            hasattr(cts, "set_tour_visibility"),
            "set_tour_visibility is missing — the organiser cannot change a "
            "tour's visibility from the community page (LOCAL-752 B).")

    def test_owner_may_change_visibility(self):
        cur = _cur()
        cts.set_tour_visibility(cur, 736, 10, "members", owner_user_id="owner-10")
        self.assertTrue(cur.updates, "owner's visibility change wrote nothing.")
        # The written visibility is 'members'.
        self.assertEqual(cur.updates[-1][0], "members")

    def test_non_owner_is_refused(self):
        cur = _cur()
        with self.assertRaises(cts.CommunityTourError) as ctx:
            cts.set_tour_visibility(cur, 736, 10, "public",
                                    owner_user_id="member-99")
        self.assertEqual(ctx.exception.code, "not_owner")
        self.assertEqual(cur.updates, [], "a non-owner must not write visibility.")


class PublicDownloadStillGatedTest(unittest.TestCase):
    def setUp(self):
        cts._HAS_COMMUNITY_COLUMNS = True

    def test_non_member_public_download_is_402(self):
        cur = _cur()  # tour 736 is community 10, public; no memberships
        relevant, allowed, deny = cts.community_download_decision(
            cur, "stranger", 736)
        self.assertTrue(relevant)
        self.assertFalse(allowed)
        self.assertEqual(deny["error"], "membership_required")
        self.assertEqual(deny["community_id"], 10)
        self.assertEqual(deny["tour_id"], 736)


if __name__ == "__main__":
    unittest.main(verbosity=2)
