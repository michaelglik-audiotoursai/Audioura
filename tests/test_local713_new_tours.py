#!/usr/bin/env python3
"""test_local713_new_tours.py — LOCAL-713 / D675.

Proves the server's /communities/new-tours read: across the caller's ACTIVE
memberships (and the communities it owns), the NEW community tours since the
last sync, newest first, each with its languages list (original first, then the
finished translations).

Hermetic (a scripted fake cursor, no Postgres, writes NO rows — the same style
as test_local710b_community_tours_payload.py). A single FakeCursor answers each
query by matching the SQL text, from a small in-memory fixture of communities,
memberships and audio_tours rows. Asserts:

  * active vs expired vs non-member: only ACTIVE memberships (and owned
    communities) contribute; an expired pass contributes nothing, never an
    error (D675 §4);
  * `since` filters to tours created strictly after it;
  * the languages list is the original's language FIRST, then the finished
    (non-draft) translations — a draft translation is excluded;
  * short_title falls back to tour_name when NULL; stop_count and created_at
    are carried;
  * the merged list is newest first across communities;
  * _parse_since tolerates Z / offset / blank / garbage.

Run: python3 -m pytest tests/test_local713_new_tours.py -q
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


NOW = datetime.datetime(2026, 10, 18, 12, 0, 0)
PAST = NOW - datetime.timedelta(days=1)
FUTURE = NOW + datetime.timedelta(days=30)


def _dt(day, hour=9):
    return datetime.datetime(2026, 10, day, hour, 0, 0)


class FakeDB:
    """An in-memory fixture of the three tables the new-tours read touches.

    communities:  {id: (name, owner_user_id, disabled)}
    memberships:  list of (user_id, community_id, expires_at)
    tours:        list of dicts with the audio_tours columns used here.
    """

    def __init__(self, communities, memberships, tours):
        self.communities = communities
        self.memberships = memberships
        self.tours = tours


class FakeCursor:
    """Answers each SQL the helpers issue by matching on the normalised text.

    The helpers issue exactly four shapes:
      1. active-community-ids (a UNION of membership + owned);
      2. community name by id;
      3. a community's non-draft ORIGINAL tours (optionally since);
      4. a tour's finished translation languages.
    """

    def __init__(self, db):
        self.db = db
        self._result = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        params = params or ()

        # 1. active community ids: a UNION query joining memberships + owned.
        if "union" in s and "community_memberships" in s:
            user_id, now, owner_id = params
            ids = set()
            for (uid, cid, expires_at) in self.db.memberships:
                if uid != user_id:
                    continue
                name, owner, disabled = self.db.communities[cid]
                if disabled:
                    continue
                if expires_at is None or expires_at > now:
                    ids.add(cid)
            for cid, (name, owner, disabled) in self.db.communities.items():
                if owner == owner_id and not disabled:
                    ids.add(cid)
            self._result = [(cid,) for cid in sorted(ids)]
            return

        # 2. community name by id.
        if s.startswith("select name from communities where id"):
            (cid,) = params
            row = self.db.communities.get(cid)
            self._result = [(row[0],)] if row else []
            return

        # 4. a tour's finished translation languages.
        if "where original_tour_id = %s" in s and "language" in s:
            (tour_id,) = params
            langs = []
            for t in self.db.tours:
                if t.get("original_tour_id") == tour_id and not t.get("draft", False):
                    if t.get("language"):
                        langs.append((t["id"], t["language"]))
            langs.sort(key=lambda x: x[0])
            self._result = [(lang,) for (_id, lang) in langs]
            return

        # 3. a community's non-draft ORIGINAL tours (optionally since).
        if "from audio_tours" in s and "original_tour_id is null" in s:
            if "created_at > %s" in s:
                cid, since = params
            else:
                (cid,) = params
                since = None
            rows = []
            for t in self.db.tours:
                if t.get("community_id") != cid:
                    continue
                if t.get("original_tour_id") is not None:
                    continue
                if t.get("draft", False):
                    continue
                if since is not None and not (t.get("created_at") and t["created_at"] > since):
                    continue
                rows.append(t)
            # DB orders created_at DESC, id DESC.
            rows.sort(key=lambda t: (t.get("created_at") or datetime.datetime.min, t["id"]),
                      reverse=True)
            self._result = [
                (t["id"], t["tour_name"], t.get("short_title"),
                 t.get("stops_count", 0), t.get("created_at"), t.get("language"))
                for t in rows
            ]
            return

        raise AssertionError(f"unexpected SQL: {s!r}")

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None


def _fixture():
    """Two communities the device is ACTIVE in (c1 by membership, c3 owned), one
    EXPIRED (c2), one it is NOT a member of (c4). Tours tagged across them, with
    translations (finished + one draft)."""
    communities = {
        1: ("Boston Walkers", "owner-1", False),
        2: ("Expired Club", "owner-2", False),
        3: ("My Own Community", "device", False),   # device owns it
        4: ("Stranger Town", "owner-4", False),
    }
    memberships = [
        ("device", 1, FUTURE),   # active (unexpired)
        ("device", 2, PAST),     # expired → contributes nothing
        # c3 owned (no membership row needed); c4 no membership at all
    ]
    tours = [
        # c1 originals (en) + a finished es translation + a draft fr translation.
        {"id": 10, "tour_name": "Beacon Hill", "short_title": "Beacon Hill — Walk",
         "stops_count": 4, "created_at": _dt(18), "language": "en",
         "original_tour_id": None, "draft": False, "community_id": 1},
        {"id": 11, "tour_name": "Beacon Hill (es)", "short_title": None,
         "stops_count": 4, "created_at": _dt(18), "language": "es",
         "original_tour_id": 10, "draft": False, "community_id": 1},
        {"id": 12, "tour_name": "Beacon Hill (fr draft)", "short_title": None,
         "stops_count": 4, "created_at": _dt(18), "language": "fr",
         "original_tour_id": 10, "draft": True, "community_id": 1},
        {"id": 7, "tour_name": "Faneuil Hall", "short_title": None,
         "stops_count": 3, "created_at": _dt(1), "language": "en",
         "original_tour_id": None, "draft": False, "community_id": 1},
        # a DRAFT original in c1 — excluded.
        {"id": 9, "tour_name": "Unfinished", "short_title": None,
         "stops_count": 0, "created_at": _dt(19), "language": "en",
         "original_tour_id": None, "draft": True, "community_id": 1},
        # c2 (expired) has a tour — must NOT appear.
        {"id": 20, "tour_name": "Members Only", "short_title": None,
         "stops_count": 2, "created_at": _dt(17), "language": "en",
         "original_tour_id": None, "draft": False, "community_id": 2},
        # c3 (owned) tour — appears (organiser counts, D675).
        {"id": 30, "tour_name": "Owner Tour", "short_title": "Owner Tour — Walk",
         "stops_count": 5, "created_at": _dt(15), "language": "ru",
         "original_tour_id": None, "draft": False, "community_id": 3},
        # c4 (non-member) tour — never appears.
        {"id": 40, "tour_name": "Stranger", "short_title": None,
         "stops_count": 1, "created_at": _dt(16), "language": "en",
         "original_tour_id": None, "draft": False, "community_id": 4},
    ]
    return FakeDB(communities, memberships, tours)


class NewToursTest(unittest.TestCase):
    def setUp(self):
        self.cur = FakeCursor(_fixture())

    def test_active_vs_expired_vs_nonmember(self):
        out = ca.new_tours_for_user(self.cur, "device", since=None, now=NOW)
        cids = {t["community_id"] for t in out}
        # c1 (active membership) and c3 (owned) contribute; c2 (expired) and
        # c4 (non-member) do not.
        self.assertEqual(cids, {1, 3})
        tour_ids = {t["tour_id"] for t in out}
        self.assertIn(10, tour_ids)   # c1 original
        self.assertIn(7, tour_ids)    # c1 original
        self.assertIn(30, tour_ids)   # c3 owned
        self.assertNotIn(20, tour_ids)  # c2 expired
        self.assertNotIn(40, tour_ids)  # c4 non-member
        self.assertNotIn(9, tour_ids)   # draft original excluded
        self.assertNotIn(11, tour_ids)  # a translation is never a row

    def test_newest_first_across_communities(self):
        out = ca.new_tours_for_user(self.cur, "device", since=None, now=NOW)
        created = [t["created_at"] for t in out]
        self.assertEqual(created, sorted(created, reverse=True))
        # The most recent is Beacon Hill (Oct 18).
        self.assertEqual(out[0]["tour_id"], 10)

    def test_languages_original_first_then_finished_translations(self):
        out = ca.new_tours_for_user(self.cur, "device", since=None, now=NOW)
        beacon = next(t for t in out if t["tour_id"] == 10)
        # Original en first, then the finished es translation; the DRAFT fr is
        # excluded.
        self.assertEqual(beacon["languages"], ["en", "es"])
        faneuil = next(t for t in out if t["tour_id"] == 7)
        self.assertEqual(faneuil["languages"], ["en"])
        owner = next(t for t in out if t["tour_id"] == 30)
        self.assertEqual(owner["languages"], ["ru"])

    def test_short_title_fallback_and_fields(self):
        out = ca.new_tours_for_user(self.cur, "device", since=None, now=NOW)
        beacon = next(t for t in out if t["tour_id"] == 10)
        self.assertEqual(beacon["short_title"], "Beacon Hill — Walk")
        self.assertEqual(beacon["community_name"], "Boston Walkers")
        self.assertEqual(beacon["stop_count"], 4)
        faneuil = next(t for t in out if t["tour_id"] == 7)
        # short_title NULL → falls back to tour_name.
        self.assertEqual(faneuil["short_title"], "Faneuil Hall")

    def test_since_filters_strictly_after(self):
        # since = Oct 10 → only tours created after Oct 10 remain.
        since = _dt(10)
        out = ca.new_tours_for_user(self.cur, "device", since=since, now=NOW)
        ids = {t["tour_id"] for t in out}
        self.assertIn(10, ids)   # Oct 18 > Oct 10
        self.assertIn(30, ids)   # Oct 15 > Oct 10
        self.assertNotIn(7, ids)  # Oct 1 is NOT after Oct 10

    def test_since_at_exact_time_excludes(self):
        # since exactly equal to a tour's created_at excludes it (strictly
        # after). With since = Oct 18, every tour (Oct 18, Oct 15, Oct 1) is at
        # or before it, so nothing remains.
        out = ca.new_tours_for_user(self.cur, "device", since=_dt(18), now=NOW)
        ids = {t["tour_id"] for t in out}
        self.assertNotIn(10, ids)  # created_at == since → excluded
        self.assertNotIn(30, ids)  # Oct 15 is not after Oct 18
        self.assertEqual(out, [])

    def test_empty_for_unknown_device(self):
        out = ca.new_tours_for_user(self.cur, "nobody", since=None, now=NOW)
        self.assertEqual(out, [])


class ParseSinceTest(unittest.TestCase):
    def test_blank_and_none(self):
        self.assertIsNone(ca._parse_since(None))
        self.assertIsNone(ca._parse_since(""))
        self.assertIsNone(ca._parse_since("   "))

    def test_garbage(self):
        self.assertIsNone(ca._parse_since("not-a-date"))

    def test_plain_iso(self):
        dt = ca._parse_since("2026-10-18T09:00:00")
        self.assertEqual(dt, datetime.datetime(2026, 10, 18, 9, 0, 0))

    def test_trailing_z(self):
        dt = ca._parse_since("2026-10-18T09:00:00Z")
        self.assertEqual(dt, datetime.datetime(2026, 10, 18, 9, 0, 0))

    def test_offset_normalised_to_utc_naive(self):
        dt = ca._parse_since("2026-10-18T11:00:00+02:00")
        self.assertEqual(dt, datetime.datetime(2026, 10, 18, 9, 0, 0))
        self.assertIsNone(dt.tzinfo)


if __name__ == "__main__":
    unittest.main()
