#!/usr/bin/env python3
"""test_local846_stale_tracking_rows.py — LOCAL-846.

Closes the stale-'tracking'-row defect.

Evidence (GCloud_Storied, 2026-10-30 15:39 EDT): request 300 (USER-41659366, the
09:02:07Z double tap) was source='tracking' — the app's tracking row, not an
orchestrator generation. It stayed 'started' for 6 h until set failed by hand.
27 rows across all users were 'started' and > 1 h old.

Root cause: the orchestrator writes TWO tour_requests rows per generation — its
own (source='orchestrator', tour_id=job_id, finalised by the orchestrator) and
an app-facing tracking row (source='tracking', tour_id='tour_'+job_id[:8],
created via track_user_tour → user-tracking PUT) that is only ever closed if the
app sends a tour_status_update — which it frequently does not. So tracking rows
sat at 'started' forever.

The fix has two legs, both proven here against a throwaway Postgres schema (no
shared/production row is ever written — IsolatedSchema asserts public counts are
identical before/after):

  Finalise-time mirror (_set_tour_request_status):
    1. When the orchestrator flips its OWN row to 'completed'/'failed', the
       linked tracking row inherits that status in the same transaction. A
       tracking row the app already closed is never overwritten.

  Orchestrator sweep (_sweep_stale_tracking_rows), idempotent, DELETE-free:
    2. MIRROR a tracking row whose linked orchestrator row is already terminal
       (covers rows written before the mirror existed).
    3. ORPHAN: a tracking row 'started' > 2 h with no terminal linked
       orchestrator row → 'failed', reason 'stale tracking row'.
    4. DUPLICATE: two tracking rows sharing (secret_id, tour_id) — the 830 double
       tap — keep the newest, fail the older with reason 'duplicate tracking row'.
    5. Idempotent: a second sweep pass changes nothing.
    6. A fresh tracking row (< 2 h, no terminal partner) is left alone.
"""
import os
import sys
import unittest
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_connection import get_db_config  # noqa: E402

_CFG = get_db_config()
os.environ["DB_HOST"] = _CFG["host"]
os.environ["DB_PORT"] = str(_CFG["port"])
os.environ["DB_NAME"] = _CFG["dbname"]
os.environ["DB_USER"] = _CFG["user"]
os.environ["DB_PASSWORD"] = _CFG["password"]

from _isolated_db import IsolatedSchema  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402

# Clone only tour_requests: every write the code under test issues is to that
# table, so nothing can escape to public. IsolatedSchema proves it.
_ISO = IsolatedSchema(
    prefix="t846",
    clone_tables=["tour_requests"],
    proof_tables=["tour_requests"],
    banner="LOCAL-846",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


def _connect():
    """A connection that resolves to the throwaway schema (PGOPTIONS is set by
    IsolatedSchema.setup, so an unqualified tour_requests shadows public)."""
    import psycopg2
    cfg = get_db_config()
    return psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"], connect_timeout=5,
    )


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class StaleTrackingRowTest(unittest.TestCase):
    # ── row helpers ──────────────────────────────────────────────────────────
    def _insert_orchestrator(self, job_id, status, secret_id):
        with _connect() as c:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source) "
                "VALUES (%s, %s, %s, NOW(), 'orchestrator') RETURNING id",
                (secret_id, job_id, status),
            )
            rid = cur.fetchone()[0]
            c.commit()
            return rid

    def _insert_tracking(self, tour_id, secret_id, status="started",
                         age_seconds=0, request_string="see Nice"):
        with _connect() as c:
            cur = c.cursor()
            cur.execute(
                "INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at, source) "
                "VALUES (%s, %s, %s, %s, NOW() - (%s || ' seconds')::interval, 'tracking') "
                "RETURNING id",
                (secret_id, tour_id, request_string, status, str(int(age_seconds))),
            )
            rid = cur.fetchone()[0]
            c.commit()
            return rid

    def _row(self, rid):
        with _connect() as c:
            cur = c.cursor()
            cur.execute(
                "SELECT status, finished_at, request_string FROM tour_requests WHERE id = %s",
                (rid,),
            )
            r = cur.fetchone()
            return {"status": r[0], "finished_at": r[1], "request_string": r[2]}

    def _new_ids(self):
        job_id = uuid.uuid4().hex  # 32-char hex, like a real orchestrator job id
        secret_id = "SID-" + uuid.uuid4().hex[:10]
        tracking_tour_id = orch._tracking_tour_id_for(job_id)
        return job_id, secret_id, tracking_tour_id

    # ── Leg 1 — finalise-time mirror ──────────────────────────────────────────
    def test_mirror_completed_at_finalize(self):
        job_id, secret_id, tt = self._new_ids()
        self._insert_orchestrator(job_id, "started", secret_id)
        trk = self._insert_tracking(tt, secret_id, status="started")
        orch._set_tour_request_status(job_id, "completed")
        self.assertEqual(self._row(trk)["status"], "completed",
                         "tracking row must inherit the orchestrator's 'completed'")
        self.assertIsNotNone(self._row(trk)["finished_at"])

    def test_mirror_failed_at_finalize(self):
        job_id, secret_id, tt = self._new_ids()
        self._insert_orchestrator(job_id, "started", secret_id)
        trk = self._insert_tracking(tt, secret_id, status="started")
        orch._set_tour_request_status(job_id, "failed")
        self.assertEqual(self._row(trk)["status"], "failed",
                         "tracking row must inherit the orchestrator's 'failed'")

    def test_mirror_never_overwrites_app_reported_terminal(self):
        # If the app already reported its own terminal state, the mirror must not
        # clobber it (idempotent, app-authoritative).
        job_id, secret_id, tt = self._new_ids()
        self._insert_orchestrator(job_id, "started", secret_id)
        trk = self._insert_tracking(tt, secret_id, status="completed")
        orch._set_tour_request_status(job_id, "failed")
        self.assertEqual(self._row(trk)["status"], "completed",
                         "an app-closed tracking row must not be reopened/overwritten")

    # ── Leg 2 — sweep ─────────────────────────────────────────────────────────
    def test_sweep_mirrors_terminal_orchestrator_onto_tracking(self):
        # Pre-fix style: orchestrator row already terminal, tracking row stuck.
        job_id, secret_id, tt = self._new_ids()
        self._insert_orchestrator(job_id, "completed", secret_id)
        trk = self._insert_tracking(tt, secret_id, status="started", age_seconds=60)
        counts = orch._sweep_stale_tracking_rows(_connect=_connect)
        self.assertEqual(self._row(trk)["status"], "completed")
        self.assertGreaterEqual(counts["mirrored"], 1)

    def test_orphan_started_over_2h_is_failed_with_reason(self):
        _job_id, secret_id, _tt = self._new_ids()
        tour_id = "tour_" + uuid.uuid4().hex[:8]  # no matching orchestrator row
        trk = self._insert_tracking(tour_id, secret_id, status="started",
                                    age_seconds=2 * 60 * 60 + 120)  # > 2h
        counts = orch._sweep_stale_tracking_rows(_connect=_connect)
        row = self._row(trk)
        self.assertEqual(row["status"], "failed", "a >2h orphan tracking row → failed")
        self.assertIn("stale tracking row", row["request_string"])
        self.assertGreaterEqual(counts["orphaned"], 1)

    def test_orphan_under_2h_is_left_alone(self):
        _job_id, secret_id, _tt = self._new_ids()
        tour_id = "tour_" + uuid.uuid4().hex[:8]
        trk = self._insert_tracking(tour_id, secret_id, status="started",
                                    age_seconds=60 * 60)  # 1h — under threshold
        orch._sweep_stale_tracking_rows(_connect=_connect)
        self.assertEqual(self._row(trk)["status"], "started",
                         "a fresh (<2h) tracking row must stay 'started'")

    def test_duplicate_older_row_is_failed_with_reason(self):
        _job_id, secret_id, _tt = self._new_ids()
        tour_id = "tour_" + uuid.uuid4().hex[:8]
        older = self._insert_tracking(tour_id, secret_id, status="started", age_seconds=10)
        newer = self._insert_tracking(tour_id, secret_id, status="started", age_seconds=5)
        counts = orch._sweep_stale_tracking_rows(_connect=_connect)
        older_row = self._row(older)
        newer_row = self._row(newer)
        self.assertEqual(older_row["status"], "failed",
                         "the older duplicate tracking row → failed")
        self.assertIn("duplicate tracking row", older_row["request_string"])
        self.assertEqual(newer_row["status"], "started",
                         "the newest duplicate row is kept non-terminal")
        self.assertGreaterEqual(counts["duplicates"], 1)

    def test_sweep_is_idempotent(self):
        # Build one of each case, sweep twice, assert the second pass is a no-op.
        job_id, secret_id, tt = self._new_ids()
        self._insert_orchestrator(job_id, "completed", secret_id)
        mirror_trk = self._insert_tracking(tt, secret_id, status="started", age_seconds=60)

        orphan_tour = "tour_" + uuid.uuid4().hex[:8]
        orphan_trk = self._insert_tracking(orphan_tour, secret_id, status="started",
                                          age_seconds=3 * 60 * 60)

        dup_tour = "tour_" + uuid.uuid4().hex[:8]
        dup_old = self._insert_tracking(dup_tour, secret_id, status="started", age_seconds=10)
        dup_new = self._insert_tracking(dup_tour, secret_id, status="started", age_seconds=5)

        first = orch._sweep_stale_tracking_rows(_connect=_connect)
        self.assertGreaterEqual(sum(first.values()), 3)
        snapshot = {rid: self._row(rid) for rid in (mirror_trk, orphan_trk, dup_old, dup_new)}

        second = orch._sweep_stale_tracking_rows(_connect=_connect)
        self.assertEqual(second, {"mirrored": 0, "orphaned": 0, "duplicates": 0},
                         "a second sweep must change nothing")
        for rid, before in snapshot.items():
            self.assertEqual(self._row(rid)["status"], before["status"],
                             f"row {rid} must be unchanged by the idempotent second pass")

    def test_orchestrator_rows_are_never_touched_by_sweep(self):
        # The sweep only finalises source='tracking'. An orchestrator row stuck at
        # 'started' is the LOCAL-833 sweep's job, not this one.
        job_id, secret_id, _tt = self._new_ids()
        orch_rid = self._insert_orchestrator(job_id, "started", secret_id)
        orch._sweep_stale_tracking_rows(_connect=_connect)
        self.assertEqual(self._row(orch_rid)["status"], "started",
                         "the sweep must not touch source='orchestrator' rows")


if __name__ == "__main__":
    unittest.main(verbosity=2)
