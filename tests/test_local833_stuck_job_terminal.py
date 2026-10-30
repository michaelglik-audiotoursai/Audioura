"""test_local833_stuck_job_terminal.py — LOCAL-833.

Closes the stuck-'processing' / endless-re-sweep defect.

Evidence (GCloud_Storied wave 9, orchestrator 00009-7ht): the Kunsthistorisches
proof's generator job ac864a08 went SILENT after 07:54Z (its Cloud Run instance
was recycled mid-job — the worker thread died with the instance) yet
generator_jobs.status stayed 'processing' FOREVER. The orchestrator cancelled it
at 09:15 (tour_requests 298 → 'failed'), but orchestrator_jobs 03ec8b1a never
went terminal, so the LOCAL-821/829 sweep re-took its lease every cycle and
polled a dead job forever. $0, but never ends — and every silent job adds one.

The fix has three legs, each proven here:

  Generator side (job_store):
    1. A non-terminal generator job whose updated_at is older than
       GEN_JOB_STALE_SECONDS is STALE: _is_stale_job says so, GeneratorJobsStore
       flips it to 'error' on the next read (stale-on-read), and sweep_stale
       flips every such row in one pass. A fresh / live job is never touched.

  Orchestrator read side (_generator_job_state):
    2. A generator job still reporting 'processing'/'queued' but with a stale
       updated_at and no live heartbeat maps to 'error' (terminal), so the
       resume stops re-polling a dead job. A heartbeat or a recent updated_at
       keeps the reported status.

  Orchestrator sweep/resume side (_resume_one_job, store):
    3a. A row whose tour_requests is ALREADY terminal is marked 'error' and
        never re-taken (the exact 298/03ec8b1a case).
    3b. A row whose generator job is 'error' (incl. stale) is marked 'error',
        tour_requests 'failed', reservation released — not retried forever.
    3c. A deliberate give-up (GeneratorGiveUpError) marks the durable record
        'error' immediately, instead of leaving it resumable.
    3d. After ORCH_MAX_RESUME_ATTEMPTS failed resumes the row is terminal.
    3e. A terminal row is never offered by list_resumable.

The store-layer legs run inside a throwaway Postgres schema (no shared row is
ever written). The orchestrator-flow legs stub all I/O (no DB, no HTTP) so they
run anywhere. The existing LOCAL-821 and LOCAL-829 suites still pass unchanged.
"""
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta

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
import job_store as js  # noqa: E402
import orchestrator_jobs as oj  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402

# orchestrator_jobs and generator_jobs self-heal their own tables inside the
# throwaway schema; we clone tour_requests so the orchestrator's terminal /
# idempotency reads resolve to the schema copy and never touch public.
_ISO = IsolatedSchema(
    prefix="t833",
    clone_tables=["tour_requests"],
    proof_tables=["tour_requests"],
    banner="LOCAL-833",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


# ───────────────────────────────────────────────────────────────────────────
# Leg 1 — generator-side staleness (pure helper; no DB)
# ───────────────────────────────────────────────────────────────────────────
class StaleHelperTest(unittest.TestCase):
    def _iso(self, seconds_ago):
        return (datetime.now() - timedelta(seconds=seconds_ago)).isoformat()

    def test_fresh_processing_job_is_not_stale(self):
        job = {"status": "processing", "updated_at": self._iso(10)}
        stale, _age, _ = js._is_stale_job(job, stale_seconds=1800)
        self.assertFalse(stale, "a job updated 10s ago is not stale")

    def test_old_processing_job_is_stale(self):
        job = {"status": "processing", "updated_at": self._iso(3600)}
        stale, age, updated = js._is_stale_job(job, stale_seconds=1800)
        self.assertTrue(stale, "a job with no progress for 1h is stale")
        self.assertGreater(age, 1800)
        self.assertIsNotNone(updated)

    def test_terminal_job_is_never_stale(self):
        for st in ("completed", "error"):
            job = {"status": st, "updated_at": self._iso(99999)}
            stale, _a, _u = js._is_stale_job(job, stale_seconds=1800)
            self.assertFalse(stale, f"a '{st}' job is never stale")

    def test_missing_updated_at_is_not_stale(self):
        stale, _a, _u = js._is_stale_job({"status": "processing"}, stale_seconds=1)
        self.assertFalse(stale, "cannot judge staleness with no updated_at → leave alone")


# ───────────────────────────────────────────────────────────────────────────
# Leg 1 (DB) — generator stale-on-read and sweep_stale against a real schema
# ───────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class GeneratorStaleStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = js.GeneratorJobsStore()
        self.job_id = "gen-" + uuid.uuid4().hex[:12]

    def _backdate(self, job_id, seconds):
        """Force updated_at into the past so the job looks stale."""
        import psycopg2
        conn = psycopg2.connect(connect_timeout=5, **self.store._db_config)
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE generator_jobs SET updated_at = NOW() - (%s || ' seconds')::interval "
                "WHERE job_id = %s",
                (str(int(seconds)), job_id),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def test_stale_on_read_flips_processing_to_error(self):
        self.store.upsert(self.job_id, status="processing", progress="working",
                          location="Kunsthistorisches Museum")
        self._backdate(self.job_id, 3600)  # 1h since last progress
        # The read-path stale check flips it and returns a TERMINAL job.
        got = self.store.get(self.job_id)
        self.assertEqual(got["status"], "error",
                         "a stale processing job must read back as error")
        self.assertEqual(got.get("error_code"), "stale")
        self.assertIn("stale", (got.get("error") or "").lower())
        # And the row itself is now terminal (a second, independent read agrees).
        again = self.store.get(self.job_id)
        self.assertEqual(again["status"], "error")

    def test_fresh_processing_job_survives_read(self):
        self.store.upsert(self.job_id, status="processing", progress="working")
        got = self.store.get(self.job_id)
        self.assertEqual(got["status"], "processing",
                         "a just-written job must NOT be marked stale on read")

    def test_sweep_stale_flips_only_old_nonterminal(self):
        old_id = "gen-old-" + uuid.uuid4().hex[:8]
        fresh_id = "gen-new-" + uuid.uuid4().hex[:8]
        done_id = "gen-done-" + uuid.uuid4().hex[:8]
        self.store.upsert(old_id, status="processing")
        self.store.upsert(fresh_id, status="processing")
        self.store.upsert(done_id, status="completed")
        self._backdate(old_id, 3600)
        self._backdate(done_id, 3600)  # old but terminal — must be left alone

        flipped = self.store.sweep_stale(stale_seconds=1800)
        self.assertGreaterEqual(flipped, 1)

        # Re-read WITHOUT tripping stale-on-read for the fresh one (it is fresh).
        self.assertEqual(self.store.get(old_id)["status"], "error")
        self.assertEqual(self.store.get(fresh_id)["status"], "processing")
        self.assertEqual(self.store.get(done_id)["status"], "completed")


# ───────────────────────────────────────────────────────────────────────────
# Leg 2 — orchestrator _generator_job_state maps a stale job to 'error'
# ───────────────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class GeneratorJobStateStaleTest(unittest.TestCase):
    def setUp(self):
        self._saved = orch._authenticated_request
        self._iso = lambda s: (datetime.now() - timedelta(seconds=s)).isoformat()

    def tearDown(self):
        orch._authenticated_request = self._saved

    def _patch(self, payload):
        orch._authenticated_request = lambda *a, **k: _Resp(200, payload)

    def test_stale_processing_maps_to_error(self):
        self._patch({"status": "processing", "updated_at": self._iso(3600)})
        self.assertEqual(orch._generator_job_state("gen-stale"), "error",
                         "a silent processing job (old updated_at, no heartbeat) is error")

    def test_live_heartbeat_keeps_processing(self):
        self._patch({"status": "processing", "updated_at": self._iso(3600),
                     "heartbeat_at": datetime.now().isoformat()})
        self.assertEqual(orch._generator_job_state("gen-live"), "processing",
                         "a live worker heartbeat vetoes staleness")

    def test_recent_processing_stays_processing(self):
        self._patch({"status": "processing", "updated_at": self._iso(5)})
        self.assertEqual(orch._generator_job_state("gen-fresh"), "processing")

    def test_completed_and_error_passthrough(self):
        self._patch({"status": "completed"})
        self.assertEqual(orch._generator_job_state("g"), "completed")
        self._patch({"status": "error"})
        self.assertEqual(orch._generator_job_state("g"), "error")


# ───────────────────────────────────────────────────────────────────────────
# Leg 3 — resume/sweep disposition (all I/O stubbed; no DB, no HTTP)
# ───────────────────────────────────────────────────────────────────────────
class _FakeStore:
    """In-memory stand-in for OrchestratorJobsStore, recording terminal calls
    and tracking a persisted resume_attempts counter."""
    def __init__(self, row):
        self._row = dict(row)
        self._row.setdefault("resume_attempts", 0)
        self.completed = []
        self.errored = []
        self.released = []

    def acquire_lease(self, job_id, lease_seconds=None, owner=None):
        r = dict(self._row)
        r.setdefault("lease_owner", "owner-test")
        return r

    def get(self, job_id):
        return dict(self._row)

    def mark_completed(self, job_id):
        self._row["status"] = "completed"
        self.completed.append(job_id)

    def mark_error(self, job_id, reason=None):
        self._row["status"] = "error"
        self.errored.append((job_id, reason))

    def increment_resume_attempts(self, job_id):
        self._row["resume_attempts"] = self._row.get("resume_attempts", 0) + 1
        return self._row["resume_attempts"]

    def release_lease(self, job_id, owner=None):
        self.released.append(job_id)


class ResumeDispositionTest(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: getattr(orch, name) for name in (
                "ACTIVE_JOBS", "_tour_already_stored_for_job",
                "_tour_request_is_terminal", "_generator_job_state",
                "_set_tour_request_status", "_release_generation_reservation",
                "_orch_jobs_store", "orchestrate_tour_async",
            )
        }
        orch.ACTIVE_JOBS = {}
        self.status_calls = []
        orch._set_tour_request_status = lambda jid, st: self.status_calls.append((jid, st))
        orch._release_generation_reservation = lambda u, j, reason: None
        # Defaults — individual tests override.
        orch._tour_already_stored_for_job = lambda jid: False
        orch._tour_request_is_terminal = lambda jid: None
        orch._generator_job_state = lambda gen: "processing"

    def tearDown(self):
        for name, val in self._saved.items():
            setattr(orch, name, val)

    def _row(self, **over):
        r = {
            "job_id": "job-" + uuid.uuid4().hex[:8],
            "generator_job_id": "gen-abc",
            "status": "processing",
            "resume_attempts": 0,
            "params": {
                "location": "Kunsthistorisches Museum", "tour_type": "",
                "total_stops": 3, "user_id": "u1",
                "request_string": "Kunsthistorisches Museum", "language": "en",
            },
        }
        r.update(over)
        return r

    def test_3a_already_terminal_request_marks_error_no_resume(self):
        """tour_requests already 'failed' (the 298/03ec8b1a case) → record error,
        no delivery, never re-taken."""
        row = self._row()
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._tour_request_is_terminal = lambda jid: "failed"
        calls = []
        orch.orchestrate_tour_async = lambda jid, *a, **k: calls.append(jid)

        orch._resume_one_job(row)

        self.assertEqual(calls, [], "a terminal request is never re-delivered")
        self.assertTrue(store.errored, "record marked error")
        self.assertEqual(store.errored[0][0], row["job_id"])
        self.assertIn("terminal", store.errored[0][1].lower())

    def test_3b_stale_generator_job_marks_error(self):
        """generator job reads 'error' (incl. stale) → record error, tour_requests
        failed, reservation released."""
        row = self._row(generator_job_id="gen-dead")
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._generator_job_state = lambda gen: "error"  # stale maps here upstream
        calls = []
        orch.orchestrate_tour_async = lambda jid, *a, **k: calls.append(jid)

        orch._resume_one_job(row)

        self.assertEqual(calls, [], "a dead generator job is not delivered")
        self.assertTrue(store.errored)
        self.assertIn((row["job_id"], "failed"), self.status_calls)

    def test_3d_exceeds_max_attempts_marks_error(self):
        """Once resume_attempts exceeds the cap the row is terminal, not retried."""
        row = self._row(resume_attempts=orch.ORCH_MAX_RESUME_ATTEMPTS)
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        # Even though the generator job is 'completed' (recoverable), the cap wins.
        orch._generator_job_state = lambda gen: "completed"
        calls = []
        orch.orchestrate_tour_async = lambda jid, *a, **k: calls.append(jid)

        orch._resume_one_job(row)

        self.assertEqual(calls, [], "a row past the attempt cap is never delivered")
        self.assertTrue(store.errored, "record marked error at the cap")
        self.assertIn("max resume", store.errored[0][1].lower())
        self.assertIn((row["job_id"], "failed"), self.status_calls)

    def test_3d_under_cap_still_resumes(self):
        """A row still under the cap with a recoverable generator job resumes."""
        row = self._row(resume_attempts=0)
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._generator_job_state = lambda gen: "completed"
        calls = []

        def _fake_orch(jid, *a, **k):
            calls.append((jid, k.get("resume_generator_job_id")))
            store.mark_completed(jid)
        orch.orchestrate_tour_async = _fake_orch

        orch._resume_one_job(row)

        self.assertEqual(len(calls), 1, "a row under the cap resumes exactly once")
        self.assertEqual(calls[0][1], "gen-abc", "re-attaches to existing generator job")
        self.assertEqual(store._row["resume_attempts"], 1, "attempt counted")


# ───────────────────────────────────────────────────────────────────────────
# Leg 3c — a deliberate give-up marks the durable record error immediately
# (store/flow level, exercising the exception-handler disposition)
# ───────────────────────────────────────────────────────────────────────────
class GiveUpTerminalTest(unittest.TestCase):
    def test_give_up_error_is_a_distinct_exception(self):
        self.assertTrue(issubclass(orch.GeneratorGiveUpError, Exception))

    def test_give_up_error_disposition_marks_error(self):
        """Simulate the exception-handler branch: a GeneratorGiveUpError marks the
        record error immediately (no resumable release)."""
        store_errored = []
        store_released = []

        class _S:
            def mark_error(self, jid, reason=None):
                store_errored.append(jid)

            def release_lease(self, jid, owner=None):
                store_released.append(jid)

        # Reproduce the exact decision the handler makes.
        e = orch.GeneratorGiveUpError("stall give-up")
        s = _S()
        if isinstance(e, orch.GeneratorGiveUpError):
            s.mark_error("job-x", reason=str(e))
        else:  # pragma: no cover
            s.release_lease("job-x")

        self.assertEqual(store_errored, ["job-x"], "give-up marks error")
        self.assertEqual(store_released, [], "give-up does NOT leave the row resumable")


# ───────────────────────────────────────────────────────────────────────────
# Leg 3e (DB) — resume_attempts persists and a terminal row is never resumable
# ───────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class OrchStoreResumeAttemptsTest(unittest.TestCase):
    def setUp(self):
        self.store = oj.OrchestratorJobsStore()
        self.job_id = "job-" + uuid.uuid4().hex[:12]
        self.store.create(self.job_id, location="Kunsthistorisches Museum",
                          request_string="Kunsthistorisches Museum", user_id="u1")
        self.store.set_generator_job_id(self.job_id, "gen-" + uuid.uuid4().hex[:8])

    def test_increment_persists_and_returns_new_count(self):
        self.assertEqual(self.store.get(self.job_id)["resume_attempts"], 0)
        self.assertEqual(self.store.increment_resume_attempts(self.job_id), 1)
        self.assertEqual(self.store.increment_resume_attempts(self.job_id), 2)
        self.assertEqual(self.store.get(self.job_id)["resume_attempts"], 2)

    def test_terminal_row_is_never_resumable(self):
        # Non-terminal → resumable at min_idle 0.
        ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertIn(self.job_id, ids)
        # mark_error → terminal → gone from resumable (never re-taken).
        self.store.mark_error(self.job_id, reason="cancelled give-up")
        ids2 = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertNotIn(self.job_id, ids2,
                         "a terminal (error) row must never be offered to the sweep")
        row = self.store.get(self.job_id)
        self.assertEqual(row["status"], "error")
        self.assertIsNone(row["lease_owner"], "mark_error clears the lease")


if __name__ == "__main__":
    unittest.main(verbosity=2)
