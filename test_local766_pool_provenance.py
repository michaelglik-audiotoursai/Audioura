"""
LOCAL-766 — the stop pool never rebuilds a paid or community tour for someone else.
====================================================================================
D713 (Michael, 2026-10-25): reuse is welcome, "unless it is a community or paid
tour… users should not bypass payment by naming their tour the same way". Whole-
tour reuse is already creator-scoped (LOCAL-727); the STOP POOL (LOCAL-590) was the
remaining bypass — it stored stops by venue identity with no link to the tour they
were made for, so an identical request by ANOTHER user was served the same stops
(`[LOCAL-590] POOL DELIVERY: reused=N`), a free rebuild of a priced/community tour.

These are the RED tests written first (they fail on pre-LOCAL-766 code, where
`maybe_generate_with_pool` reuses every pooled stop regardless of its source tour):

  1. pool row from a PRICED tour → another user gets a FRESH stop; the CREATOR
     still gets reuse.
  2. same for a COMMUNITY tour.
  3. a tour priced AFTER pooling → protected from then on (checked at delivery).
  4. a FREE, non-community tour → reused as today (Michael wants identical
     requests to reuse).
  5. UNPROVEN-provenance rows (no stop_pool_sources row) → shared.
  6. organiser-audio tours never enter the pool (so never produce provenance).

ZERO PRODUCTION WRITES (LOCAL-601)
==================================
Every DB test runs inside a private throwaway schema (tests/_isolated_db.py):
`PGOPTIONS=-c search_path=<schema>,public` routes every connection — this file's
AND the ones stop_pool_store / stop_pool_sources / the orchestrator open
internally — at a schema whose `stop_pool` / `audio_tours` shadow `public`. The
new `stop_pool_sources` table is self-healed by the module INSIDE that schema
(migration 051 need not have run on the test DB). `tearDownModule` drops the
schema (CASCADE) and asserts `public` row counts are identical before and after.
No row lands in `public`; there is no DELETE anywhere. DB classes SKIP when the
DB is unreachable.
"""
import os
import sys
import uuid
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

from db_connection import get_db_config
from _isolated_db import IsolatedSchema

_cfg = get_db_config()
os.environ.setdefault("DB_HOST", _cfg["host"])
os.environ.setdefault("DB_PORT", _cfg["port"])
DB_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{_cfg['user']}:{_cfg['password']}@{_cfg['host']}:{_cfg['port']}/{_cfg['dbname']}")

import stop_pool_store as pool
import stop_pool_orchestrator as orch
import stop_pool_sources as provenance

# Clone stop_pool + audio_tours; stop_pool_sources is self-healed by the module
# inside the throwaway schema (it does not exist in public on the test DB).
_ISO = IsolatedSchema(
    prefix="t766",
    clone_tables=["stop_pool", "audio_tours"],
    proof_tables=["stop_pool", "audio_tours"],
    db_url=DB_URL,
    banner="LOCAL-766",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


def _db_up():
    return _ISO.db_up()


# A delivered museum tour to seed the pool (same shape as the LOCAL-590 suite).
def _seed_tour(venue, titles):
    body = f"Step-by-Step Audio Guided Tour: {venue}\nTour-Category: museum\n\n"
    for i, t in enumerate(titles):
        body += f"Stop {i+1}: {t}\n\n"
        body += "Address: 1 Test St\n\n"
        body += f"Orientation: Stand before {t}.\n\n"
        body += f"This is the pooled narration body for {t}. It is reusable prose.\n\n"
        if i < len(titles) - 1:
            body += f"Directions: Proceed to {titles[i+1]}.\n\n"
    body += (f"From {titles[0]} to {titles[-1]}, you have followed the thread.\n\n"
             f"That's {len(titles)} stops.\n\n"
             "Sources: This tour draws on information from example.org.\n")
    return body


def _insert_tour(db_url, tour_name, request_string, tour_content, *,
                 price_tier=None, community_id=None, creator_user_id=None,
                 source_kind=None):
    """Insert an ORIGINAL audio_tours row (is_test row; lat/lng NULL) and return id.

    is_paid is GENERATED from price_tier by the DB, so it is never set here.
    """
    import psycopg2
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audio_tours "
                "(tour_name, request_string, tour_content, price_tier, community_id, "
                " creator_user_id, source_kind, is_test) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
                (tour_name, request_string, tour_content, price_tier, community_id,
                 creator_user_id, source_kind),
            )
            tid = cur.fetchone()[0]
        conn.commit()
        return tid
    finally:
        conn.close()


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestProvenanceDeliveryRule(unittest.TestCase):
    """The core delivery rule: a protected source tour withholds its pooled stops
    from everyone but its creator."""

    def setUp(self):
        self.venue = "ZZ_766_" + uuid.uuid4().hex[:8]
        self.ttype = "museum"
        self.titles = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        self.content = _seed_tour(self.venue, self.titles)
        # Seed the pool exactly as a delivery would.
        pool.store_delivered_tour(self.venue, self.ttype, self.content, DB_URL)

    def _record(self, tour_id):
        provenance.record_pool_sources(
            DB_URL, self.venue, self.ttype, tour_id, self.content)

    def test_1_priced_tour_blocks_other_user_creator_keeps_reuse(self):
        tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                            self.content, price_tier=3, creator_user_id="creatorA")
        self._record(tid)

        # Another user: ALL five pooled stops are protected → none allowed.
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed_other, skipped_other = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed_other), 0,
                         "a priced tour's pooled stops must not be reusable by another user")
        self.assertEqual(len(skipped_other), 5)
        self.assertTrue(all(reason == "paid" for _r, _tid, reason in skipped_other))

        # The creator still gets full reuse.
        allowed_creator, skipped_creator = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="creatorA")
        self.assertEqual(len(allowed_creator), 5,
                         "the creator keeps reuse of their own priced tour's stops")
        self.assertEqual(len(skipped_creator), 0)

    def test_2_community_tour_blocks_other_user(self):
        tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                            self.content, community_id=42, creator_user_id="creatorA")
        self._record(tid)

        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed), 0)
        self.assertEqual(len(skipped), 5)
        self.assertTrue(all(reason == "community" for _r, _tid, reason in skipped))

    def test_3_tour_priced_AFTER_pooling_is_protected_from_then_on(self):
        # Tour is FREE at pool time: provenance recorded, but not protected yet.
        tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                            self.content, price_tier=None, creator_user_id="creatorA")
        self._record(tid)
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed_before, _ = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed_before), 5,
                         "a free tour's stops are shareable before it is priced")

        # Price it AFTER pooling. The delivery-time check now protects it.
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("UPDATE audio_tours SET price_tier = 2 WHERE id = %s", (tid,))
        conn.commit()
        conn.close()

        allowed_after, skipped_after = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed_after), 0,
                         "pricing the tour later protects its pooled stops from then on")
        self.assertEqual(len(skipped_after), 5)

    def test_4_free_non_community_tour_is_reused_as_today(self):
        tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                            self.content, price_tier=None, community_id=None,
                            creator_user_id="creatorA")
        self._record(tid)
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed), 5,
                         "a free, non-community tour keeps sharing exactly as today")
        self.assertEqual(len(skipped), 0)

    def test_5_unproven_provenance_rows_are_shared(self):
        # No provenance recorded at all (unproven). Must stay shareable.
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        self.assertEqual(len(allowed), 5,
                         "a pooled stop with no proven source stays shareable")
        self.assertEqual(len(skipped), 0)

    def test_6_mixed_one_protected_source_protects_the_shared_stop(self):
        # Two tours share the venue's pool: a FREE tour (all 5) and a PAID tour
        # that only delivered the first 2. The 2 shared-with-paid stops are
        # protected for another user; the other 3 stay shareable.
        free_tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                                self.content, creator_user_id="creatorFree")
        self._record(free_tid)
        paid_content = _seed_tour(self.venue, self.titles[:2])
        paid_tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                                paid_content, price_tier=1, creator_user_id="creatorPaid")
        provenance.record_pool_sources(
            DB_URL, self.venue, self.ttype, paid_tid, paid_content)

        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="someoneElse")
        allowed_titles = {r["title"] for r in allowed}
        skipped_titles = {r["title"] for r, _t, _rsn in skipped}
        self.assertEqual(skipped_titles, {"Alpha", "Beta"},
                         "stops a paid tour delivered are protected")
        self.assertEqual(allowed_titles, {"Gamma", "Delta", "Epsilon"},
                         "stops only a free tour delivered stay shareable")

    def test_7_provenance_recorded_under_loc_key_is_found_under_qid_key(self):
        # Regression (D582 dual-key): the live record path stores provenance under
        # the loc: pool key (qid=None), but a delivery that resolves a Wikidata QID
        # reads/filters under the qid: key. The two keys share the same title_norm,
        # so the protection must still be found. Seed the pool under BOTH keys for
        # one venue (as resolver flakiness would), record provenance for a PRICED
        # tour under the loc key only, then filter as a qid-resolving delivery.
        qid = "Q" + uuid.uuid4().hex[:6].upper()
        # Store the same stops under the qid identity too, so the qid: pool key
        # holds the rows a qid-resolving get_pool_stops would return.
        pool.store_delivered_tour(self.venue, self.ttype, self.content, DB_URL, qid=qid)
        tid = _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                           self.content, price_tier=2, creator_user_id="creatorA")
        # Record provenance exactly as the live store path does: qid defaulted to
        # None → loc: key only.
        provenance.record_pool_sources(DB_URL, self.venue, self.ttype, tid, self.content)

        # Delivery resolves the qid: get_pool_stops + partition both pass qid.
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL, qid=qid)
        self.assertTrue(len(rows) >= 5, "qid-key pool holds the venue's stops")
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, qid=qid, user_id="someoneElse")
        self.assertEqual(len(allowed), 0,
                         "loc-recorded protection must apply when read under the qid key")
        self.assertTrue(len(skipped) >= 5)
        self.assertTrue(all(reason == "paid" for _r, _t, reason in skipped))
        # The creator still reuses under the qid-key delivery.
        allowed_c, skipped_c = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, qid=qid, user_id="creatorA")
        self.assertEqual(len(skipped_c), 0,
                         "the creator keeps reuse regardless of which key is read")


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestOrchestratorEndToEnd(unittest.TestCase):
    """maybe_generate_with_pool must drop the protected stops from the reusable
    pool for a non-creator (so they are generated fresh) while the creator keeps
    full reuse. An outdoor (walking) venue is used so the path stays in the pool
    reuse branch with K>0 (contained museums take a separate About-stop path when
    the pool is empty, which needs a sourceable venue)."""

    def setUp(self):
        self.venue = "ZZ_766E_" + uuid.uuid4().hex[:8]
        self.ttype = "walking"
        self.titles = ["Aa", "Bb", "Cc"]
        self.content = _seed_tour(self.venue, self.titles)
        pool.store_delivered_tour(self.venue, self.ttype, self.content, DB_URL)
        # A PAID tour that delivered only the first stop ("Aa"): that one stop is
        # protected for a non-creator; "Bb"/"Cc" stay shareable.
        paid_content = _seed_tour(self.venue, self.titles[:1])
        tid = _insert_tour(DB_URL, f"{self.venue} - Walking Tour", self.venue,
                           paid_content, price_tier=2, creator_user_id="owner")
        provenance.record_pool_sources(
            DB_URL, self.venue, self.ttype, tid, paid_content)
        # A FREE tour covers all three (so the creator-of-the-free case is moot;
        # the paid tour is the only protector, of "Aa" only).
        free_tid = _insert_tour(DB_URL, f"{self.venue} - Walking Tour", self.venue,
                                self.content, creator_user_id="freeOwner")
        provenance.record_pool_sources(
            DB_URL, self.venue, self.ttype, free_tid, self.content)

    def test_other_user_gets_fresh_for_protected_stop_only(self):
        calls = {}

        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            calls["total_stops"] = total_stops
            calls["exclude_titles"] = list(exclude_titles or [])
            return _seed_tour(location, ["FreshAa"]), output_file, (None, None)

        out = orch.maybe_generate_with_pool(
            self.venue, self.ttype, 3, DB_URL, generate_fn=fake_generate,
            user_id="otherUser")
        self.assertIsNotNone(out)
        # Pool held 3; "Aa" is protected for the other user → K=2 reusable; N=3 →
        # the generator is asked for exactly 1 fresh stop.
        self.assertEqual(out["reused_stops"], 2,
                         "only the two unprotected pooled stops are reused")
        self.assertEqual(calls.get("total_stops"), 1,
                         "the one protected stop is generated fresh")

    def test_creator_still_reuses_all_pooled_stops(self):
        def fake_generate(location, tour_type, output_file, total_stops,
                          user_id=None, job_id=None, exclude_titles=None):
            raise AssertionError("generator must not be called when the creator "
                                 "can reuse all pooled stops")

        out = orch.maybe_generate_with_pool(
            self.venue, self.ttype, 3, DB_URL, generate_fn=fake_generate,
            user_id="owner")
        self.assertIsNotNone(out)
        self.assertEqual(out["reused_stops"], 3,
                         "the creator of the paid tour reuses all 3 pooled stops")
        self.assertEqual(out["new_stops"], 0)


@unittest.skipUnless(_db_up(), "dev Postgres not reachable")
class TestBackfill(unittest.TestCase):
    """Backfill attributes existing pooled stops to existing tours by content;
    organiser-audio tours never enter the pool."""

    def setUp(self):
        self.venue = "ZZ_766B_" + uuid.uuid4().hex[:8]
        self.ttype = "museum"
        self.titles = ["One", "Two", "Three"]
        self.content = _seed_tour(self.venue, self.titles)
        pool.store_delivered_tour(self.venue, self.ttype, self.content, DB_URL)

    def test_backfill_proves_matching_tour_and_counts(self):
        # A priced tour whose content matches the pooled stops exists but has no
        # provenance yet (the pre-LOCAL-766 state). Backfill must attribute it.
        _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                     self.content, price_tier=2, creator_user_id="creatorA")

        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed_before, _ = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="other")
        self.assertEqual(len(allowed_before), 3,
                         "before backfill the stops are unproven → shareable")

        counts = provenance.backfill_from_tours(DB_URL, verbose=False)
        self.assertGreaterEqual(counts["links_written"], 3)

        allowed_after, skipped_after = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="other")
        self.assertEqual(len(allowed_after), 0,
                         "after backfill the priced tour's pooled stops are protected")
        self.assertEqual(len(skipped_after), 3)

    def test_backfill_is_idempotent(self):
        _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                     self.content, price_tier=1, creator_user_id="creatorA")
        c1 = provenance.backfill_from_tours(DB_URL, verbose=False)
        c2 = provenance.backfill_from_tours(DB_URL, verbose=False)
        self.assertEqual(c2["links_written"], 0,
                         "a second backfill writes no new links")
        self.assertEqual(c1["pool_rows_proven"], c2["pool_rows_proven"])

    def test_organiser_audio_tour_is_not_attributed(self):
        # An organiser-audio tour never enters the pool; even if its content
        # happened to match, the backfill skips it (source_kind filter).
        _insert_tour(DB_URL, f"{self.venue} - Museum Tour", self.venue,
                     self.content, price_tier=5, creator_user_id="organiser",
                     source_kind="organiser_audio")
        provenance.backfill_from_tours(DB_URL, verbose=False)
        rows = pool.get_pool_stops(self.venue, self.ttype, DB_URL)
        allowed, skipped = provenance.partition_pool_rows(
            rows, self.venue, self.ttype, DB_URL, user_id="other")
        self.assertEqual(len(skipped), 0,
                         "an organiser-audio tour must not protect pooled stops "
                         "(it never enters the pool)")
        self.assertEqual(len(allowed), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
