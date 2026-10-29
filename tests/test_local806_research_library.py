#!/usr/bin/env python3
"""test_local806_research_library.py — LOCAL-806 P6 research library (DB).

The P6 pilot pre-researches the most-requested destinations cheaply and keeps the
research with a `fresh_until` date, so a customer's request there is BUILT from
stored research instead of researched from scratch. The one additive schema
change is stop_pool.fresh_until (museums/landmarks 90 days, businesses 30 days).

Proves:
  (1) A library write (store_delivered_tour(..., fresh_days=N)) stamps every stop
      with fresh_until ~ NOW()+N days and get_pool_stops returns them (a library
      HIT) while fresh.
  (2) A row whose fresh_until is in the PAST is IGNORED by get_pool_stops - it is
      not served stale (the refresh job re-researches it instead).
  (3) An ordinary delivery (fresh_days omitted) leaves fresh_until = NULL and the
      stop is ALWAYS returned - behaviour is byte-for-byte unchanged.
  (4) An ordinary re-pool over a library row KEEPS the existing fresh_until
      (COALESCE), so a real customer tour served from the library does not
      silently drop its freshness window.

ZERO PRODUCTION WRITES (LOCAL-601): the test runs inside a private throwaway
schema (tests/_isolated_db.IsolatedSchema) routed via PGOPTIONS; the schema is
dropped (CASCADE) at teardown and public row counts are proven unchanged. No
DELETE against public anywhere.

Run: python3 -m pytest tests/test_local806_research_library.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{_cfg['user']}:{_cfg['password']}@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}")
os.environ["DATABASE_URL"] = DB_URL

import psycopg2
import stop_pool_store as pool
from _isolated_db import IsolatedSchema


def _seed_tour(location, titles):
    """A minimal delivered-tour text in the pool store's parse format."""
    body = (f"Step-by-Step Audio Guided Tour: {location}\n"
            f"Tour-Category: museum\n\n")
    for i, t in enumerate(titles):
        body += f"Stop {i+1}: {t}\n\n"
        body += "Address: 1 Example St, Exampletown\n\n"
        body += f"Coordinates: 40.{i:04d}, -70.{i:04d}\n\n"
        body += f"Orientation: Stand before {t}.\n\n"
        body += f"This is the researched narration body for {t}.\n\n"
        if i < len(titles) - 1:
            body += f"Directions: Proceed to {titles[i+1]}.\n\n"
    body += (f"From {titles[0]} to {titles[-1]}, you have followed the thread.\n\n"
             f"That's {len(titles)} stops.\n\n"
             "Sources: This tour draws on information from example.org.\n")
    return body


_ISO = IsolatedSchema(
    prefix="t806",
    clone_tables=["stop_pool"],
    proof_tables=["stop_pool"],
    db_url=DB_URL,
    banner="LOCAL-806",
)


def _db_up():
    return _ISO.db_up()


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestResearchLibraryFreshUntil(unittest.TestCase):
    def setUp(self):
        self.ttype = "museum"

    def _expire(self, title):
        c = psycopg2.connect(DB_URL)
        c.autocommit = True
        try:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE stop_pool SET fresh_until = NOW() - interval '1 day' "
                    "WHERE title_norm = %s",
                    (pool._title_norm(title),))
        finally:
            c.close()

    # (1) A library write stamps fresh_until and the stops are served while fresh.
    def test_library_write_sets_fresh_until_and_is_served(self):
        loc = "ZZ806_LIB_" + uuid.uuid4().hex[:8]
        titles = ["Great Hall", "East Wing"]
        n = pool.store_delivered_tour(
            loc, self.ttype, _seed_tour(loc, titles), DB_URL, fresh_days=90)
        self.assertEqual(2, n)
        rows = pool.get_pool_stops(loc, self.ttype, DB_URL)
        self.assertEqual(2, len(rows), "fresh library stops must be served (a library hit)")
        self.assertTrue(all(r["fresh_until"] for r in rows),
                        "library rows must carry a fresh_until date")

    # (2) A stale (past fresh_until) row is IGNORED - refreshed, not served.
    def test_stale_library_row_is_ignored(self):
        loc = "ZZ806_STALE_" + uuid.uuid4().hex[:8]
        titles = ["Great Hall", "East Wing"]
        pool.store_delivered_tour(
            loc, self.ttype, _seed_tour(loc, titles), DB_URL, fresh_days=90)
        self._expire("Great Hall")
        rows = pool.get_pool_stops(loc, self.ttype, DB_URL)
        served = sorted(r["title"] for r in rows)
        self.assertEqual(["East Wing"], served,
                         "a stop past its fresh_until must not be served")

    # (3) An ordinary delivery leaves fresh_until NULL and is always served.
    def test_ordinary_delivery_is_never_aged_out(self):
        loc = "ZZ806_ORD_" + uuid.uuid4().hex[:8]
        titles = ["Alpha", "Beta"]
        pool.store_delivered_tour(loc, "walking", _seed_tour(loc, titles), DB_URL)
        rows = pool.get_pool_stops(loc, "walking", DB_URL)
        self.assertEqual(2, len(rows))
        self.assertTrue(all(r["fresh_until"] is None for r in rows),
                        "an ordinary delivered-tour stop must have fresh_until = NULL")

    # (4) An ordinary re-pool over a library row KEEPS the existing fresh_until.
    def test_ordinary_repool_keeps_library_fresh_until(self):
        loc = "ZZ806_KEEP_" + uuid.uuid4().hex[:8]
        titles = ["Great Hall"]
        pool.store_delivered_tour(
            loc, self.ttype, _seed_tour(loc, titles), DB_URL, fresh_days=90)
        before = pool.get_pool_stops(loc, self.ttype, DB_URL)[0]["fresh_until"]
        self.assertIsNotNone(before)
        # Re-pool the SAME stop as an ordinary delivery (no fresh_days).
        pool.store_delivered_tour(loc, self.ttype, _seed_tour(loc, titles), DB_URL)
        after = pool.get_pool_stops(loc, self.ttype, DB_URL)[0]["fresh_until"]
        self.assertEqual(before, after,
                         "an ordinary re-pool must not drop the library freshness window")


if __name__ == "__main__":
    unittest.main(verbosity=2)
