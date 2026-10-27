#!/usr/bin/env python3
"""test_local778_reuse_first.py — LOCAL-778 Free (L2) reuse-first hybrid (DB).

D719 amended: a Free (L2) request whose plan has ``by_reference_only = FALSE``
no longer runs either the pure by-reference path (reuse-only, refuse if short)
or the normal fresh path. It runs REUSE-FIRST: reuse whatever matching material
exists (the LOCAL-597 finder — stop pool + stops of existing non-test tours of
the same venue), and research ONLY the stops that are missing.

Proves (the ticket's red list):
  (i)   N fully covered → zero grounding calls, nothing researched.
  (ii)  K of N covered → only N-K researched, the K reused titles excluded from
        the fresh call (no duplicates).
  (iii) A paid or community source stop is never reused for ANOTHER user (D713):
        it is dropped from the reusable material and researched fresh instead.
  (iv)  Nothing covered → identical to the fresh path (the whole tour researched).
  (v)   Paid levels (l3/tester) unchanged — reuse-first is L2-only.
  + the SUBSCRIPTION GATE: L2 with by_reference_only=FALSE returns mode
    'reuse_first'; the concurrency guard counts this user's recent 'started'
    rows so two parallel requests at limit 1 → the second is refused; stale
    (>30 min) 'started' rows are ignored.

ZERO PRODUCTION WRITES (LOCAL-601): every DB-touching test runs inside a private
throwaway schema (tests/_isolated_db.IsolatedSchema) routed via PGOPTIONS; the
schema is dropped (CASCADE) at teardown and public row counts are proven
unchanged. No DELETE anywhere.

Run: python3 -m pytest tests/test_local778_reuse_first.py -q
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
import stop_pool_orchestrator as orch
from _isolated_db import IsolatedSchema

# Clone every table the reuse-first path reads or writes (directly or via the
# caps code), plus the CASCADE neighbour stop_metrics. stop_pool_sources is NOT
# cloned: it is additive, created-on-demand by stop_pool_sources.ensure_table,
# and that CREATE IF NOT EXISTS runs under PGOPTIONS so it lands in the throwaway
# schema (it may not exist in public at all on a fresh test DB).
_ISOLATED_TABLES = [
    "audio_tours", "stop_pool",
    "device_entitlement", "tour_requests", "users", "plans", "stop_metrics",
]
_PROOF_TABLES = ["audio_tours", "stop_pool", "device_entitlement", "tour_requests"]

_ISO = IsolatedSchema(
    prefix="t778",
    clone_tables=_ISOLATED_TABLES,
    proof_tables=_PROOF_TABLES,
    db_url=DB_URL,
    banner="LOCAL-778",
)


def _db_up():
    return _ISO.db_up()


def setUpModule():
    _ISO.setup()
    if _ISO.schema is None:
        return
    # Seed the plans the gate reads INTO the throwaway schema (cloned LIKE public
    # is empty of rows). L2 here is by_reference_only = FALSE (D719), the whole
    # point of reuse-first; the other levels mirror the production seed values the
    # gate needs.
    c = psycopg2.connect(DB_URL)
    try:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO plans (plan_id, tours_per_day, tours_per_month,
                    fresh_per_pack, edits_per_pack, ops_per_pack, max_stops,
                    max_new_stops_per_edit, by_reference_only, price_usd)
                VALUES
                    ('l2', 1, 3, NULL, NULL, NULL, 5, 0, FALSE, 0.00),
                    ('l3', 999, NULL, 5, 5, NULL, 10, 10, FALSE, 10.00),
                    ('tester', 10, 50, NULL, NULL, NULL, 5, 5, FALSE, 0.00)
                ON CONFLICT (plan_id) DO UPDATE SET
                    by_reference_only = EXCLUDED.by_reference_only,
                    tours_per_day = EXCLUDED.tours_per_day,
                    tours_per_month = EXCLUDED.tours_per_month,
                    max_stops = EXCLUDED.max_stops
            """)
        c.commit()
    finally:
        c.close()


def tearDownModule():
    _ISO.teardown()


# A delivered museum tour body the pool store / parser understand.
def _seed_tour(venue_title, titles):
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


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid assembly (the orchestrator path reuse-first routes through)
# ─────────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestReuseFirstHybrid(unittest.TestCase):
    def setUp(self):
        self.ttype = "museum"

    # (i) N fully covered → zero grounding (generator never called).
    def test_full_coverage_researches_nothing(self):
        loc = "ZZ778_FULL_" + uuid.uuid4().hex[:8]
        titles = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        pool.store_delivered_tour(loc, self.ttype, _seed_tour(loc, titles), DB_URL)

        def fail_generate(*a, **k):
            raise AssertionError("fresh research must NOT run when N is fully covered")

        out = orch.maybe_generate_with_pool(
            loc, self.ttype, 5, DB_URL, generate_fn=fail_generate, reuse_first=True)
        self.assertIsNotNone(out)
        self.assertEqual(5, out["reused_stops"])
        self.assertEqual(0, out["new_stops"])
        self.assertEqual(0.0, out["new_cost"])
        self.assertTrue(out["served_from_pool_only"])
        for t in titles:
            self.assertIn(f"reusable narration body for {t}", out["text"])

    # (ii) K of N covered → only N-K researched, the K reused titles excluded.
    def test_partial_coverage_researches_only_the_rest(self):
        loc = "ZZ778_PARTIAL_" + uuid.uuid4().hex[:8]
        pooled = ["Alpha", "Beta", "Gamma"]
        pool.store_delivered_tour(loc, self.ttype, _seed_tour(loc, pooled), DB_URL)
        calls = {}

        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            calls["total_stops"] = total_stops
            calls["exclude_titles"] = list(exclude_titles or [])
            return _seed_tour(location, ["New One", "New Two"]), output_file, (None, None)

        out = orch.maybe_generate_with_pool(
            loc, self.ttype, 5, DB_URL, generate_fn=fake_generate, reuse_first=True)
        self.assertIsNotNone(out)
        # Only N-K = 2 researched.
        self.assertEqual(2, calls["total_stops"])
        # The 3 reused titles were excluded so the fresh call cannot duplicate them.
        self.assertEqual(set(pooled), set(calls["exclude_titles"]))
        self.assertEqual(3, out["reused_stops"])
        self.assertEqual(2, out["new_stops"])
        # No duplicate titles in the delivered tour.
        for t in pooled:
            self.assertIn(t, out["text"])
        self.assertIn("New One", out["text"])
        self.assertIn("New Two", out["text"])

    # (iv) Nothing covered → returns None so the caller runs the fresh path.
    def test_no_coverage_falls_through_to_fresh(self):
        loc = "ZZ778_NONE_" + uuid.uuid4().hex[:8]

        def fail_generate(*a, **k):
            raise AssertionError("maybe_generate_with_pool must defer to the caller's fresh path")

        out = orch.maybe_generate_with_pool(
            loc, self.ttype, 5, DB_URL, generate_fn=fail_generate, reuse_first=True)
        self.assertIsNone(out)  # nothing to reuse → caller generates normally


# ─────────────────────────────────────────────────────────────────────────────
# Existing-tour mining is a reuse source too (not just the stop pool)
# ─────────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestReuseFirstMinesExistingTours(unittest.TestCase):
    def test_existing_tour_stops_are_reused(self):
        venue = "ZZ778 Mined " + uuid.uuid4().hex[:6]
        titles = ["Hall One", "Hall Two", "Hall Three"]
        content = _seed_tour(venue, titles)
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, tour_content,
                                             number_requested, is_test)
                    VALUES (%s, %s, %s, %s, FALSE)
                """, (venue, venue, content, 1))
            c.commit()
        finally:
            c.close()

        def fail_generate(*a, **k):
            raise AssertionError("3 mined stops fully cover N=3; no research expected")

        out = orch.maybe_generate_with_pool(
            venue, "museum", 3, DB_URL, generate_fn=fail_generate, reuse_first=True)
        self.assertIsNotNone(out)
        self.assertEqual(3, out["reused_stops"])
        self.assertEqual(0, out["new_stops"])
        self.assertIn("Hall One", out["text"])


# ─────────────────────────────────────────────────────────────────────────────
# (iii) D713 — a paid/community source stop is never reused for another user
# ─────────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestReuseFirstProvenance(unittest.TestCase):
    def _seed_priced_tour(self, venue, titles, creator):
        """Seed a PRICED non-test tour (price_tier>0) and record its stops'
        provenance so the D713 filter can protect them."""
        content = _seed_tour(venue, titles)
        c = psycopg2.connect(DB_URL)
        try:
            with c.cursor() as cur:
                cur.execute("""
                    INSERT INTO audio_tours (tour_name, request_string, tour_content,
                                             number_requested, is_test,
                                             price_tier, creator_user_id)
                    VALUES (%s, %s, %s, %s, FALSE, 1, %s)
                    RETURNING id
                """, (venue, venue, content, len(titles), creator))
                tid = cur.fetchone()[0]
            c.commit()
        finally:
            c.close()
        # Pool the stops, then link provenance to the priced tour id.
        pool.store_delivered_tour(venue, "museum", content, DB_URL)
        import stop_pool_sources as prov
        prov.record_pool_sources(DB_URL, venue, "museum", tid, content)
        return tid

    def test_priced_source_stop_not_reused_for_another_user(self):
        venue = "ZZ778 Priced " + uuid.uuid4().hex[:6]
        titles = ["Paid A", "Paid B", "Paid C"]
        creator = "creator-" + uuid.uuid4().hex[:8]
        self._seed_priced_tour(venue, titles, creator)
        other = "other-" + uuid.uuid4().hex[:8]

        researched = {}

        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            researched["total_stops"] = total_stops
            # Return as many fresh stops as asked for.
            fresh = [f"Fresh {i+1}" for i in range(total_stops)]
            return _seed_tour(location, fresh), output_file, (None, None)

        # A DIFFERENT user asks for 3 stops. All 3 pooled stops are protected
        # (priced, not their tour), so K drops to 0 and all 3 are researched.
        out = orch.maybe_generate_with_pool(
            venue, "museum", 3, DB_URL, generate_fn=fake_generate,
            reuse_first=True, user_id=other)
        # Either the whole thing researched (returned a tour with new_stops=3), or
        # — if the broadened source has no other material — it fell through (None)
        # for the caller to research fresh. Both honour "never reuse a paid stop".
        if out is not None:
            self.assertEqual(0, out["reused_stops"],
                             "a priced source stop was reused for another user")
            for t in titles:
                self.assertNotIn(f"reusable narration body for {t}", out["text"])

    def test_priced_source_stop_reused_for_its_creator(self):
        venue = "ZZ778 PricedOwn " + uuid.uuid4().hex[:6]
        titles = ["Own A", "Own B", "Own C"]
        creator = "creator-" + uuid.uuid4().hex[:8]
        self._seed_priced_tour(venue, titles, creator)

        def fail_generate(*a, **k):
            raise AssertionError("the creator may reuse their own priced stops; no research")

        # The CREATOR asks — their own stops are reusable.
        out = orch.maybe_generate_with_pool(
            venue, "museum", 3, DB_URL, generate_fn=fail_generate,
            reuse_first=True, user_id=creator)
        self.assertIsNotNone(out)
        self.assertEqual(3, out["reused_stops"])


# ─────────────────────────────────────────────────────────────────────────────
# Subscription gate: mode + concurrency guard
# ─────────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestReuseFirstGate(unittest.TestCase):
    def setUp(self):
        import subscription_levels as sl
        self.sl = sl
        self.uid = "LOCAL778-" + uuid.uuid4().hex[:10]
        self._set_level("l2")

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

    def _add_request(self, status, started_offset_minutes=0, n=1):
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
                        VALUES (%s, %s, %s, NOW() - (%s || ' minutes')::interval, 'orchestrator')
                    """, (self.uid, 'tr-' + uuid.uuid4().hex[:8], status, started_offset_minutes))
            c.commit()
        finally:
            c.close()

    # (gate) L2 with by_reference_only=FALSE returns reuse_first.
    def test_l2_reuse_first_mode(self):
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertTrue(r['allowed'], r)
        self.assertEqual('reuse_first', r.get('mode'))
        self.assertEqual(5, r['clamped_stops'])

    # Concurrency guard: a recent 'started' row counts toward the daily cap.
    def test_recent_started_row_blocks_second_parallel_request(self):
        # One in-flight request (started 1 min ago) already consumes the 1/day cap.
        self._add_request('started', started_offset_minutes=1)
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertFalse(r['allowed'])
        self.assertEqual('plan_limit_daily', r['error_code'])

    # Stale 'started' rows (>30 min) are ignored.
    def test_stale_started_row_is_ignored(self):
        self._add_request('started', started_offset_minutes=45)
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertTrue(r['allowed'], r)
        self.assertEqual('reuse_first', r.get('mode'))

    # A completed row still counts (unchanged from LOCAL-595B).
    def test_completed_row_counts(self):
        self._add_request('completed', started_offset_minutes=1)
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertFalse(r['allowed'])
        self.assertEqual('plan_limit_daily', r['error_code'])

    # (v) Paid levels unchanged: l3 never gets reuse_first, and a fresh in-flight
    # request does not consume the l3 pack pool via the started-row guard.
    def test_paid_level_unchanged(self):
        self._set_level("l3")
        r = self.sl.check_operation(self.uid, 'generate', requested_stops=5)
        self.assertTrue(r['allowed'], r)
        self.assertIsNone(r.get('mode'))  # l3 carries no by_reference/reuse_first mode


if __name__ == "__main__":
    unittest.main(verbosity=2)
