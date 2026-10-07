#!/usr/bin/env python3
"""test_local597_by_reference.py — LOCAL-597 by-reference build + caps (DB).

r2 — ZERO PRODUCTION WRITES (D141 / the tour-29 event).
=======================================================
r1 broke the binding CLAUDE.md rule: it INSERTed ``audio_tours`` rows with
``is_test = FALSE`` and real Boston lat/lng into the shared DB (visible to
Michael's app via ``tours-near`` while the test ran) and DELETEd them in
tearDown WITHOUT the mandatory ``SELECT is_test`` check. It also wrote ZZ597
``stop_pool`` rows into the shared pool.

r2 makes every DB-touching test write into a **private throwaway schema** and
drops that schema at the end, so no row is ever added to any shared table
(``public.*``). The mechanism (one line, no production-code change):

    PGOPTIONS = "-c search_path=<throwaway>,public"

libpq applies PGOPTIONS to EVERY new connection in the process — the ones the
by-reference module opens from ``db_url`` AND the env-var connections
``subscription_levels`` / ``entitlements`` open. With the throwaway schema first
on the search_path, an unqualified ``audio_tours`` / ``stop_pool`` /
``device_entitlement`` / ``tour_requests`` / ``users`` resolves to the schema
copy; ``public`` is never touched. The schema's tables are created
``LIKE public.<t> INCLUDING ALL`` so they are byte-compatible with the code's
INSERTs. ``tearDownModule`` proves ``public`` row counts for all four tables the
brief names are identical before and after, and prints them.

Because the writes land in a schema that ``tours-near`` (which queries
``public``) can never see, they are invisible to the app even mid-run. The few
INSERTs that remain still follow D141 belt-and-braces: ``is_test = TRUE``,
ids/keys captured at creation, and any cleanup is implicit in DROP SCHEMA
CASCADE — no name-pattern or date-range DELETE anywhere.

Proves:
  * POOL HIT (reusable >= N): zero grounding, new_cost == 0, no fresh research.
  * PARTIAL MATERIAL (reusable < N): a by_reference_no_material refusal carrying
    up to 3 nearby existing tours. "Nearby" now (c09eda6) means within
    NEARBY_MAX_KM (50 km) of a resolvable anchor; with no anchor the list is
    EMPTY and the suggestion drops the "pick one of these" clause.
  * EXISTING-TOUR MINING: stops of an existing non-test tour of the same venue
    are reused when the stop pool is empty.
  * CAPS (D613): L2 generate allowed with mode='by_reference'; daily cap (1/day)
    still refuses once a delivered tour is counted.

If the DB is unreachable the DB classes SKIP (guard logic is covered by
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

# ─────────────────────────────────────────────────────────────────────────────
# Throwaway-schema isolation (r2) — now via the shared helper (LOCAL-601)
# ─────────────────────────────────────────────────────────────────────────────
# The create-schema / clone-tables / PGOPTIONS / drop-schema / before-after-proof
# mechanism this suite pioneered (r2) is extracted to tests/_isolated_db.py so
# every DB-touching suite shares one implementation. The table lists are
# unchanged: clone stop_pool + the audio_tours CASCADE neighbours the code
# writes, and prove the four tables the brief names are unchanged in public.
from _isolated_db import IsolatedSchema

# Tables cloned into the throwaway schema. stop_pool (the shared pool r1
# polluted) + stop_metrics (audio_tours CASCADE target) make the copy
# self-contained for any cascade.
_ISOLATED_TABLES = [
    "audio_tours", "stop_pool", "device_entitlement",
    "tour_requests", "users", "stop_metrics",
]
# The four tables the brief asks to prove unchanged in production.
_PROOF_TABLES = ["audio_tours", "stop_pool", "device_entitlement", "tour_requests"]

_ISO = IsolatedSchema(
    prefix="t597",
    clone_tables=_ISOLATED_TABLES,
    proof_tables=_PROOF_TABLES,
    db_url=DB_URL,          # same DB the by-reference module + caps check use
    banner="LOCAL-597 r2",
)


def _admin_connect():
    """A connection with the DEFAULT search_path (public), for schema admin and
    for reading public row counts. Deliberately does NOT inherit PGOPTIONS.
    Delegates to the shared helper so there is one implementation."""
    return _ISO._admin_connect()


def _db_up():
    return _ISO.db_up()


def setUpModule():
    """Create the throwaway schema, mirror the tables into it, and route every
    connection in this process at it via PGOPTIONS. Capture public counts first."""
    _ISO.setup()


def tearDownModule():
    """Drop the throwaway schema and PROVE public row counts are unchanged."""
    _ISO.teardown()


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


# A fixed Boston anchor used to stub the venue resolver so the nearby-tours path
# has a resolvable coordinate (the c09eda6 rule: no anchor -> no list).
_BOSTON = (42.3601, -71.0589)


class _BostonVenue:
    """Minimal stand-in for venue_resolver.VenueEntity carrying lat/lng only —
    _resolve_coords reads getattr(ent, 'lat'/'lng')."""
    lat = _BOSTON[0]
    lng = _BOSTON[1]


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
        # Seed two nearby non-test tours (into the throwaway schema) so the refusal
        # can offer them. _nearby_existing_tours only surfaces is_test IS NOT TRUE
        # rows (it mirrors tours-near), so these MUST be is_test=FALSE — which is
        # exactly the r1 hazard. It is safe here ONLY because the rows live in the
        # throwaway schema, invisible to tours-near (which queries public), and are
        # dropped with the schema at teardown. ids are captured at creation (D141).
        self._nearby_ids = self._seed_nearby()
        # Stub the anchor lookup to Boston so "nearby" has a resolvable origin.
        # _resolve_coords does `from venue_resolver import resolve_venue` at call
        # time, so patch the source module's attribute.
        import venue_resolver
        self._orig_resolve = venue_resolver.resolve_venue
        venue_resolver.resolve_venue = lambda *a, **k: _BostonVenue()

    def _seed_nearby(self):
        ids = []
        # Unique suffix so re-seeding across test methods (which share this
        # class's throwaway schema) never collides on uq_audio_tours_original_name.
        sfx = uuid.uuid4().hex[:6]
        self._nearby_names = {f"LOCAL597 Nearby A {sfx}", f"LOCAL597 Nearby B {sfx}"}
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                for name, lat, lng in [(f"LOCAL597 Nearby A {sfx}", 42.3601, -71.0589),
                                       (f"LOCAL597 Nearby B {sfx}", 42.3611, -71.0599)]:
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
        import venue_resolver
        venue_resolver.resolve_venue = self._orig_resolve
        # No row DELETE anywhere: the throwaway schema (and every row in it) is
        # dropped in tearDownModule. D141's "SELECT is_test before DELETE" rule is
        # about cleanup DELETEs — there are none here. Instead, assert these rows
        # are confined to the throwaway schema (never public), which is what makes
        # is_test=FALSE rows safe: tours-near queries public and can never see them.
        c = _admin_connect()
        try:
            with c.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.audio_tours WHERE id = ANY(%s)",
                            (self._nearby_ids,))
                in_public = cur.fetchone()[0]
                assert in_public == 0, (
                    f"nearby rows leaked into public.audio_tours: {in_public}")
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
        # With a resolvable Boston anchor, the two Boston-coordinate tours we
        # seeded fall inside NEARBY_MAX_KM and must be offered.
        self.assertGreaterEqual(len(out["nearby_tours"]), 1)
        for t in out["nearby_tours"]:
            self.assertIn("id", t)
            self.assertIn("name", t)
        names = {t["name"] for t in out["nearby_tours"]}
        self.assertTrue(names & self._nearby_names)
        # The suggestion lists them ("pick one of these ...").
        self.assertIn("pick one of these", out["suggestion"])
        # Zero grounding even on the refusal path.
        self.assertEqual(0, out["grounding"]["requests"])
        self.assertEqual(0, out["grounding"]["queries"])

    def test_no_anchor_offers_empty_list(self):
        # c09eda6 rule: a venue that cannot be geocoded gets NO nearby list —
        # better than offering Nice/Abu Dhabi to a Boston listener. Stub the
        # resolver to None for this test (overriding the Boston stub from setUp).
        import venue_resolver
        venue_resolver.resolve_venue = lambda *a, **k: None
        out = l2.build_by_reference_tour(self.loc, self.ttype, 5, DB_URL)
        self.assertFalse(out["allowed"])
        self.assertEqual("by_reference_no_material", out["error_code"])
        # No anchor -> empty nearby list ...
        self.assertEqual([], out["nearby_tours"])
        # ... and the suggestion drops the "pick one of these" clause.
        self.assertNotIn("pick one of these", out["suggestion"])
        self.assertEqual(
            "Buy a $10 pack for a freshly researched tour.", out["suggestion"])
        self.assertEqual(0, out["grounding"]["requests"])

    def test_empty_pool_refuses(self):
        empty = "ZZ597_EMPTY_" + uuid.uuid4().hex[:8]
        out = l2.build_by_reference_tour(empty, "museum", 5, DB_URL)
        self.assertFalse(out["allowed"])
        self.assertEqual("by_reference_no_material", out["error_code"])


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestByReferenceExistingTourMining(unittest.TestCase):
    """Reuse stops of an existing non-test tour of the same venue when the stop
    pool itself is empty — the second reusable-material source D613 names.

    NOTE: _existing_tour_stops filters WHERE is_test IS NOT TRUE, so the mined
    tour must be is_test=FALSE. That is safe here ONLY because the row lives in
    the throwaway schema, invisible to tours-near (which queries public), and is
    dropped with the schema at teardown. The id is captured at creation."""

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

    # No tearDown DELETE: the row is in the throwaway schema, dropped with it.

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
    against the device_entitlement / tour_requests tables (in the throwaway
    schema — the env-var connection subscription_levels opens inherits PGOPTIONS,
    so it writes there, not to public)."""

    def setUp(self):
        import subscription_levels as sl
        self.sl = sl
        self.uid = "LOCAL597-" + uuid.uuid4().hex[:10]
        self._set_level("l2")

    # No tearDown cleanup: all rows are in the throwaway schema, dropped with it.

    def _conn(self):
        return psycopg2.connect(DB_URL)

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
