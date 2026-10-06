#!/usr/bin/env python3
"""test_local597_by_reference.py — LOCAL-597 by-reference build + caps (DB).

Runs against the dev/test Postgres with isolated UUID venue identities and
LOCAL597- device ids (never touches real rows; cleans up its own). Proves:

  * POOL HIT (reusable >= N): a tour is assembled from reused stops with the
    grounding meter at 0 (requests=0, queries=0) and new_cost == 0 — no fresh
    generation, no grounding, no SERP.
  * PARTIAL MATERIAL (reusable < N): a by_reference_no_material refusal, NOT a
    short tour, carrying up to 3 nearby existing tours (id + name).
  * EXISTING-TOUR MINING: stops of an existing non-test tour of the same venue
    are reused even when the stop pool is empty.
  * CAPS (D613): L2 generate is allowed with mode='by_reference'; the daily cap
    (1/day) still refuses once a delivered tour is counted.

If the DB is unreachable the DB classes SKIP (the guard logic is covered by
test_local597_guard.py, which needs no DB).

Run: python3 -m pytest tests/test_local597_by_reference.py -q
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

# Resolve the DB the test helper picks (audiotours_test under pytest) and point
# BOTH the pool/by-reference DATABASE_URL AND the subscription_levels DB_* env at
# it, so the caps check (which connects via DB_HOST/DB_NAME) hits the same DB.
_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{_cfg['user']}:{_cfg['password']}@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}")
# Point generate-side DB env + the by-reference module at the same DB.
os.environ["DATABASE_URL"] = DB_URL

import psycopg2
import l2_by_reference as l2
import stop_pool_store as pool


def _db_up():
    try:
        c = psycopg2.connect(DB_URL, connect_timeout=4)
        c.close()
        return True
    except Exception:
        return False


def _seed_tour(venue_title, titles):
    """A delivered museum tour body the pool store / parser understand."""
    body = f"Step-by-Step Audio Guided Tour: {venue_title}\nTour-Category: museum\n\n"
    for i, t in enumerate(titles):
        body += f"Stop {i+1}: {t}\n\n"
        body += "Address: 1 Test St\n\n"
        body += f"Orientation: Stand before {t}.\n\n"
        body += f"This is the reusable narration body for {t}. Already researched prose.\n\n"
        if i < len(titles) - 1:
            body += f"Directions: Proceed to {titles[i+1]}.\n\n"
    body += (f"From {titles[0]} to {titles[-1]}, you have followed the thread.\n\n"
             f"That's {len(titles)} stops.\n\n"
             "Sources: This tour draws on information from example.org.\n")
    return body


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestByReferencePoolHit(unittest.TestCase):
    def setUp(self):
        self.loc = "ZZ597_POOL_" + uuid.uuid4().hex[:8]
        self.ttype = "museum"
        self.titles = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        pool.store_delivered_tour(self.loc, self.ttype, _seed_tour(self.loc, self.titles), DB_URL)

    def test_pool_hit_assembles_zero_grounding_zero_cost(self):
        out = l2.build_by_reference_tour(self.loc, self.ttype, 5, DB_URL)
        self.assertTrue(out["allowed"], out)
        self.assertEqual("by_reference", out["mode"])
        self.assertEqual(5, out["reused_stops"])
        self.assertEqual(0, out["new_stops"])
        self.assertEqual(0.0, out["new_cost"])
        self.assertTrue(out["served_from_pool_only"])
        # ZERO grounding — the headline guarantee.
        self.assertEqual(0, out["grounding"]["requests"])
        self.assertEqual(0, out["grounding"]["queries"])
        # The reused narration bodies are present verbatim.
        for t in self.titles:
            self.assertIn(f"reusable narration body for {t}", out["text"])
        # Exactly 5 stops delivered.
        self.assertIn("Stop 5: Epsilon", out["text"])
        self.assertNotIn("Stop 6:", out["text"])

    def test_pool_hit_fewer_requested_than_available(self):
        # Request 3 of 5 pooled -> allowed, 3 reused.
        out = l2.build_by_reference_tour(self.loc, self.ttype, 3, DB_URL)
        self.assertTrue(out["allowed"])
        self.assertEqual(3, out["reused_stops"])
        self.assertIn("Stop 3: Gamma", out["text"])
        self.assertNotIn("Stop 4:", out["text"])


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestByReferencePartialRefusal(unittest.TestCase):
    def setUp(self):
        self.loc = "ZZ597_PARTIAL_" + uuid.uuid4().hex[:8]
        self.ttype = "museum"
        # Only 2 reusable stops, but the request asks for 5.
        pool.store_delivered_tour(self.loc, self.ttype,
                                  _seed_tour(self.loc, ["One", "Two"]), DB_URL)
        # Seed two nearby non-test tours so the refusal can offer them.
        self._nearby_ids = self._seed_nearby()

    def _seed_nearby(self):
        ids = []
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                for name, lat, lng in [("LOCAL597 Nearby A", 42.3601, -71.0589),
                                       ("LOCAL597 Nearby B", 42.3611, -71.0599)]:
                    cur.execute(
                        """
                        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                                 number_requested, is_test)
                        VALUES (%s, %s, %s, %s, %s, FALSE)
                        RETURNING id
                        """,
                        (name, name, lat, lng, 5))
                    ids.append(cur.fetchone()[0])
            c.commit()
        finally:
            c.close()
        return ids

    def tearDown(self):
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM audio_tours WHERE id = ANY(%s)", (self._nearby_ids,))
            c.commit()
        finally:
            c.close()

    def test_partial_material_refuses_with_nearby_tours(self):
        out = l2.build_by_reference_tour(self.loc, self.ttype, 5, DB_URL)
        self.assertFalse(out["allowed"])
        self.assertEqual("by_reference_no_material", out["error_code"])
        self.assertEqual(
            "This place hasn't been researched yet on the free level.",
            out["message"])
        # It REFUSED — no tour text was produced (never a short tour).
        self.assertNotIn("text", out)
        # Nearby tours carry id + name; the two we seeded must be reachable.
        self.assertGreaterEqual(len(out["nearby_tours"]), 1)
        for t in out["nearby_tours"]:
            self.assertIn("id", t)
            self.assertIn("name", t)
        names = {t["name"] for t in out["nearby_tours"]}
        self.assertTrue(names & {"LOCAL597 Nearby A", "LOCAL597 Nearby B"})
        # Zero grounding even on the refusal path.
        self.assertEqual(0, out["grounding"]["requests"])
        self.assertEqual(0, out["grounding"]["queries"])

    def test_empty_pool_refuses(self):
        empty = "ZZ597_EMPTY_" + uuid.uuid4().hex[:8]
        out = l2.build_by_reference_tour(empty, "museum", 5, DB_URL)
        self.assertFalse(out["allowed"])
        self.assertEqual("by_reference_no_material", out["error_code"])


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestByReferenceExistingTourMining(unittest.TestCase):
    """Reuse stops of an existing non-test tour of the same venue when the stop
    pool itself is empty — the second reusable-material source D613 names."""

    def setUp(self):
        self.venue = "LOCAL597 Mined Museum " + uuid.uuid4().hex[:6]
        self._tour_id = self._seed_existing_tour()

    def _seed_existing_tour(self):
        content = _seed_tour(self.venue, ["Hall One", "Hall Two", "Hall Three",
                                          "Hall Four", "Hall Five"])
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audio_tours (tour_name, request_string, tour_content,
                                             number_requested, is_test)
                    VALUES (%s, %s, %s, %s, FALSE)
                    RETURNING id
                    """,
                    (self.venue, self.venue, content, 1))
                return cur.fetchone()[0]
        finally:
            c.commit()
            c.close()

    def tearDown(self):
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM audio_tours WHERE id = %s", (self._tour_id,))
            c.commit()
        finally:
            c.close()

    def test_existing_tour_stops_are_reused(self):
        # The stop pool for this venue is empty; the five stops come from the
        # existing non-test tour's stored content.
        out = l2.build_by_reference_tour(self.venue, "museum", 5, DB_URL)
        self.assertTrue(out["allowed"], out)
        self.assertEqual(5, out["reused_stops"])
        self.assertEqual(0.0, out["new_cost"])
        self.assertEqual(0, out["grounding"]["requests"])
        self.assertIn("Hall One", out["text"])


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestByReferenceCaps(unittest.TestCase):
    """D613: L2 generate is allowed with mode='by_reference'; the daily cap still
    refuses once a delivered tour has been counted. Runs the real levels check
    against the device_entitlement / tour_requests tables."""

    def setUp(self):
        import subscription_levels as sl
        self.sl = sl
        self.uid = "LOCAL597-" + uuid.uuid4().hex[:10]
        self._cleanup()
        self._set_level("l2")

    def tearDown(self):
        self._cleanup()

    def _conn(self):
        return psycopg2.connect(DB_URL)

    def _cleanup(self):
        c = self._conn()
        try:
            with c.cursor() as cur:
                cur.execute("DELETE FROM device_entitlement WHERE user_id = %s", (self.uid,))
                cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (self.uid,))
                cur.execute("DELETE FROM users WHERE secret_id = %s", (self.uid,))
            c.commit()
        finally:
            c.close()

    def _set_level(self, level):
        c = self._conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO device_entitlement (user_id, level) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level
                """, (self.uid, level))
            c.commit()
        finally:
            c.close()

    def _add_completed_tour_today(self, n=1):
        c = self._conn()
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (secret_id, plan) VALUES (%s, 'l2')
                    ON CONFLICT (secret_id) DO NOTHING
                """, (self.uid,))
                for _ in range(n):
                    cur.execute("""
                        INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
                        VALUES (%s, %s, 'completed', NOW(), 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8]))
            c.commit()
        finally:
            c.close()

    def test_l2_generate_allowed_with_by_reference_mode(self):
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertTrue(r['allowed'])
        self.assertEqual('by_reference', r.get('mode'))
        self.assertEqual(5, r['clamped_stops'])

    def test_l2_daily_cap_refuses_after_one_delivered(self):
        self._add_completed_tour_today(1)   # 1/day used
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertFalse(r['allowed'])
        self.assertEqual('plan_limit_daily', r['error_code'])

    def test_l2_stops_over_plan_still_refuses(self):
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=6)
        self.assertFalse(r['allowed'])
        self.assertEqual('stops_over_plan', r['error_code'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
