"""test_local821_resume.py — LOCAL-821 part (A).

Proves a tour whose generation outlived its orchestrator instance (Cloud Run
SIGTERM) is finished by a fresh instance, exactly once, with a lease so two
instances cannot both finish it.

Evidence being closed (GCloud_Storied wave-4, 2026-10-30): Cloud Run sent
SIGTERM to orchestrator-subscribed while it was polling a Met museum tour. The
generator FINISHED (its result persisted in generator_jobs, LOCAL-775) but the
orchestrator was gone — no audio_tours row, tour_requests stuck at 'started'.
The orchestrator kept the generator job id and request params ONLY in memory, so
nothing could pick the job up.

The fix: a durable orchestrator_jobs row (the OrchestratorJobsStore) written at
/generate, carrying the generator job id and the full request params, plus a
resume-on-boot + periodic sweep that re-attaches to the EXISTING generator job
(no re-generation) under a lease.

Two layers are covered:

  Store (OrchestratorJobsStore, against a throwaway schema):
    1. a created job is 'resumable'; a lease is EXCLUSIVE (second acquire fails
       while the first holds it); after mark_completed it is terminal and no
       longer resumable.

  Resume flow (orchestrate_tour_async + _resume_one_job, with the generator HTTP
  and the delivery stubbed):
    2. killed mid-poll → a fresh orchestrator (no in-memory ACTIVE_JOBS entry)
       re-attaches to the completed generator job, SKIPS /generate, and delivers
       the tour exactly once; the record ends 'completed'.
    3. idempotency — if the tour was already stored (tour_requests 'completed'),
       a resume does NOT deliver again.
    4. a resume whose generator job FAILED marks the record 'error' and the
       tour_requests row 'failed' (no silent retry forever).

The store layer runs inside a throwaway Postgres schema (no shared row written).
The resume-flow layer stubs all I/O (no DB, no HTTP), so it runs anywhere.
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
import orchestrator_jobs as oj  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402

# orchestrator_jobs builds its own table via self-healing DDL, so we do not need
# to clone it; we only isolate so the row it writes lands in the throwaway
# schema, never public. tour_requests is cloned so the idempotency read works.
_ISO = IsolatedSchema(
    prefix="t821a",
    clone_tables=["tour_requests"],
    proof_tables=["tour_requests"],
    banner="LOCAL-821A",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


# ───────────────────────────────────────────────────────────────────────────
# Store-layer tests (need the DB)
# ───────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class OrchestratorJobsStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = oj.OrchestratorJobsStore()
        self.job_id = "job-" + uuid.uuid4().hex[:12]

    def test_1_create_lease_terminal_lifecycle(self):
        # Create → the job exists, non-terminal, no lease.
        self.store.create(
            self.job_id, location="Met Museum", tour_type="", total_stops=5,
            user_id="u1", request_string="Met Museum", language="en",
            store_mode="serve",
        )
        self.store.set_generator_job_id(self.job_id, "gen-123")
        row = self.store.get(self.job_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "processing")
        self.assertEqual(row["generator_job_id"], "gen-123")
        self.assertEqual(row["location"], "Met Museum")
        self.assertEqual(row["store_mode"], "serve")

        # It is resumable (min_idle 0 so a just-written row qualifies).
        resumable_ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertIn(self.job_id, resumable_ids)

        # Lease is EXCLUSIVE: the first acquire wins, a second (different owner)
        # fails while the lease is live.
        leased = self.store.acquire_lease(self.job_id, lease_seconds=300, owner="instance-A")
        self.assertIsNotNone(leased, "first instance should win the lease")
        self.assertEqual(leased["lease_owner"], "instance-A")
        again = self.store.acquire_lease(self.job_id, lease_seconds=300, owner="instance-B")
        self.assertIsNone(again, "a live lease must block a second instance")

        # A leased job is no longer offered as resumable (lease not expired).
        resumable_after_lease = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertNotIn(self.job_id, resumable_after_lease,
                         "a job with a live lease is not resumable")

        # Terminal success clears the lease and removes it from resumable.
        self.store.mark_completed(self.job_id)
        row2 = self.store.get(self.job_id)
        self.assertEqual(row2["status"], "completed")
        self.assertIsNone(row2["lease_owner"])
        resumable_done = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertNotIn(self.job_id, resumable_done, "completed job is never resumable")

    def test_2_expired_lease_is_reacquirable(self):
        self.store.create(self.job_id, location="X", request_string="X")
        # Acquire with a lease that is already expired (negative seconds).
        got = self.store.acquire_lease(self.job_id, lease_seconds=-1, owner="dead-instance")
        self.assertIsNotNone(got)
        # Because that lease is already in the past, a fresh instance can take it.
        retook = self.store.acquire_lease(self.job_id, lease_seconds=300, owner="live-instance")
        self.assertIsNotNone(retook, "an expired lease must be reacquirable")
        self.assertEqual(retook["lease_owner"], "live-instance")


# ───────────────────────────────────────────────────────────────────────────
# Resume-flow tests (all I/O stubbed — no DB, no HTTP)
# ───────────────────────────────────────────────────────────────────────────
class _FakeStore:
    """In-memory stand-in for OrchestratorJobsStore, recording terminal calls."""
    def __init__(self, row):
        self._row = dict(row)
        self.completed = []
        self.errored = []
        self.released = []

    def acquire_lease(self, job_id, lease_seconds=None, owner=None):
        return dict(self._row)

    def get(self, job_id):
        return dict(self._row)

    def mark_completed(self, job_id):
        self._row["status"] = "completed"
        self.completed.append(job_id)

    def mark_error(self, job_id, reason=None):
        self._row["status"] = "error"
        self.errored.append((job_id, reason))

    def set_generator_job_id(self, job_id, gen):
        self._row["generator_job_id"] = gen

    def release_lease(self, job_id, owner=None):
        self.released.append(job_id)


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class ResumeFlowTest(unittest.TestCase):
    def setUp(self):
        # Snapshot everything we monkeypatch so tearDown restores the module.
        self._saved = {
            name: getattr(orch, name) for name in (
                "ACTIVE_JOBS", "_tour_already_stored_for_job",
                "_generator_job_state", "_set_tour_request_status",
                "_release_generation_reservation", "_orch_jobs_store",
                "_authenticated_request", "orchestrate_tour_async",
            )
        }
        orch.ACTIVE_JOBS = {}
        self.set_status_calls = []
        orch._set_tour_request_status = lambda jid, st: self.set_status_calls.append((jid, st))
        orch._release_generation_reservation = lambda u, j, reason: None

    def tearDown(self):
        for name, val in self._saved.items():
            setattr(orch, name, val)

    def _job_row(self, gen_jid="gen-abc", store_mode="serve"):
        return {
            "job_id": "job-" + uuid.uuid4().hex[:8],
            "generator_job_id": gen_jid,
            "status": "processing",
            "params": {
                "location": "Met Museum", "tour_type": "", "total_stops": 3,
                "user_id": "u1", "request_string": "Met Museum",
                "language": "en", "store_mode": store_mode,
            },
        }

    def test_2_resume_finishes_completed_generator_job_once(self):
        """Killed mid-poll: a fresh orchestrator re-attaches to the completed
        generator job, SKIPS /generate, and delivers exactly once."""
        row = self._job_row()
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._tour_already_stored_for_job = lambda jid: False
        orch._generator_job_state = lambda gen: 'completed'

        # Capture the resumed orchestrate_tour_async call instead of running the
        # whole pipeline — we are proving the RESUME DECISION, not re-testing the
        # delivery pipeline (covered elsewhere).
        calls = []

        def _fake_orchestrate(job_id, *args, **kwargs):
            calls.append((job_id, kwargs))
            # Simulate a successful delivery finishing the record.
            store.mark_completed(job_id)
        orch.orchestrate_tour_async = _fake_orchestrate

        orch._resume_one_job(row)

        self.assertEqual(len(calls), 1, "resume should invoke delivery exactly once")
        _, kwargs = calls[0]
        self.assertEqual(kwargs.get("resume_generator_job_id"), "gen-abc",
                         "resume must re-attach to the EXISTING generator job (skip /generate)")
        self.assertEqual(kwargs.get("store_mode"), "serve")
        self.assertEqual(store._row["status"], "completed")

    def test_3_resume_is_idempotent_when_already_stored(self):
        """If the tour was already delivered, a resume must NOT deliver again."""
        row = self._job_row()
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._tour_already_stored_for_job = lambda jid: True  # already done
        orch._generator_job_state = lambda gen: 'completed'

        calls = []
        orch.orchestrate_tour_async = lambda job_id, *a, **k: calls.append(job_id)

        orch._resume_one_job(row)

        self.assertEqual(calls, [], "no re-delivery when the tour is already stored")
        self.assertIn(row["job_id"], store.completed, "record finished as completed")
        self.assertIn((row["job_id"], "completed"), self.set_status_calls)

    def test_4_resume_with_failed_generator_marks_failed(self):
        """A resume whose generator job FAILED → record 'error', tour_requests
        'failed' (reason recorded), not an endless retry."""
        row = self._job_row(gen_jid="gen-dead")
        store = _FakeStore(row)
        orch._orch_jobs_store = lambda: store
        orch._tour_already_stored_for_job = lambda jid: False
        orch._generator_job_state = lambda gen: 'error'

        calls = []
        orch.orchestrate_tour_async = lambda job_id, *a, **k: calls.append(job_id)

        orch._resume_one_job(row)

        self.assertEqual(calls, [], "a failed generator job is not delivered")
        self.assertTrue(store.errored, "record marked error with a reason")
        self.assertEqual(store.errored[0][0], row["job_id"])
        self.assertIn((row["job_id"], "failed"), self.set_status_calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
