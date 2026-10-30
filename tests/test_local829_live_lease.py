"""test_local829_live_lease.py — LOCAL-829.

Closes the double-store defect: LOCAL-821's periodic sweep resumed a job that
was STILL LIVE on the same instance, so the live thread and the resumer both
ran store_audio_tour and the tour landed in audio_tours TWICE (GCloud_Storied
wave 8: "Van Gogh Museum, Amsterdam" at rows 500 and 501, identical, 0.1 ms
apart). The live thread held no lease and never heartbeat, so once its row aged
past the sweep's min_idle it looked orphaned.

Two mechanisms, both exercised here against a throwaway Postgres schema (no
shared/production row is ever written):

  1. The LIVE path OWNS its orchestrator_jobs row — it takes the lease when a
     fresh orchestrate_tour_async starts and RENEWS it on every poll iteration
     and during store. A sweep only touches rows whose lease is free or expired,
     so a renewed live row is skipped.

  2. The store is idempotent per orchestrator job — an atomic claim_store right
     before store_audio_tour moves the row to 'storing' only when it is not
     already 'storing'/'completed'. Of two racers (live thread + sweep, or two
     resumers) exactly one wins and stores; the loser logs and stops. A store
     that then fails releases the claim back to 'processing' so a later sweep
     retries; a crash mid-store leaves 'storing' with an expired lease, still
     resumable.

Scenarios (task Do §3):
  (a) a live thread polling past min_idle with a sweep running on the same
      process → the sweep skips it; the tour is stored exactly once;
  (b) two resumers race on one row → exactly one store;
  (c) a crash after claim (status 'storing', lease expired) → a later sweep
      stores exactly once;
  (d) the store-layer lease/renew/claim primitives behave (unit level).

All store counting is done by patching tour_orchestrator_service.store_audio_tour
with a thread-safe counter, so no audio ZIP / TTS / HTTP is needed and the test
runs anywhere a dev Postgres is reachable. The existing LOCAL-821 suite
(test_local821_resume.py) covers the resume decision itself and still passes.
"""
import os
import sys
import threading
import time
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

# orchestrator_jobs self-heals its own table inside the throwaway schema; we
# clone tour_requests so the orchestrator's idempotency / status reads resolve
# to the schema copy and never touch public.
_ISO = IsolatedSchema(
    prefix="t829",
    clone_tables=["tour_requests"],
    proof_tables=["tour_requests"],
    banner="LOCAL-829",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


# ───────────────────────────────────────────────────────────────────────────
# (d) Store-layer primitives
# ───────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class StorePrimitivesTest(unittest.TestCase):
    def setUp(self):
        self.store = oj.OrchestratorJobsStore()
        self.job_id = "job-" + uuid.uuid4().hex[:12]
        self.store.create(self.job_id, location="Van Gogh Museum", request_string="Van Gogh Museum")
        self.store.set_generator_job_id(self.job_id, "gen-" + uuid.uuid4().hex[:8])

    def test_renew_keeps_live_row_out_of_resumable(self):
        owner = oj.make_owner()
        leased = self.store.acquire_lease(self.job_id, lease_seconds=2, owner=owner)
        self.assertIsNotNone(leased)
        # A renew under the SAME owner extends the lease and the row stays
        # non-resumable even at min_idle=0.
        self.assertTrue(self.store.renew_lease(self.job_id, owner, lease_seconds=60))
        ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertNotIn(self.job_id, ids, "a renewed live row must not be resumable")
        # A renew under a DIFFERENT owner does nothing (we do not own it).
        self.assertFalse(self.store.renew_lease(self.job_id, "someone-else", lease_seconds=60))

    def test_expired_lease_without_renew_becomes_resumable(self):
        owner = oj.make_owner()
        # Acquire with an already-expired lease (negative seconds) and do NOT
        # renew: the row is orphaned and offered to the sweep.
        self.assertIsNotNone(self.store.acquire_lease(self.job_id, lease_seconds=-1, owner=owner))
        ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertIn(self.job_id, ids, "an expired, un-renewed lease is resumable")

    def test_claim_store_is_exclusive(self):
        a = self.store.claim_store(self.job_id, "owner-A")
        b = self.store.claim_store(self.job_id, "owner-B")
        self.assertTrue(a, "first claimer wins")
        self.assertFalse(b, "second claimer loses — only one store")
        row = self.store.get(self.job_id)
        self.assertEqual(row["status"], "storing")

    def test_storing_with_expired_lease_is_resumable(self):
        # Winner claims (status 'storing') but its lease expires (simulate crash
        # mid-store by claiming with an expired lease), so a later sweep can
        # re-offer it.
        self.assertTrue(self.store.claim_store(self.job_id, "owner-A", lease_seconds=-1))
        ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertIn(self.job_id, ids,
                      "a 'storing' row with an expired lease must be resumable (crash case)")

    def test_release_store_claim_back_to_processing(self):
        self.assertTrue(self.store.claim_store(self.job_id, "owner-A", lease_seconds=300))
        self.store.release_store_claim(self.job_id, owner="owner-A")
        row = self.store.get(self.job_id)
        self.assertEqual(row["status"], "processing")
        self.assertIsNone(row["lease_owner"])
        # After release, the store can be claimed again (retry).
        self.assertTrue(self.store.claim_store(self.job_id, "owner-B", lease_seconds=300))


# ───────────────────────────────────────────────────────────────────────────
# (a) live thread polling past min_idle + sweep on the SAME process → ONE store
# (b) two resumers race on one row → ONE store
# (c) crash after claim → a later sweep stores ONCE
# ───────────────────────────────────────────────────────────────────────────
@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class DoubleStoreGuardTest(unittest.TestCase):
    def setUp(self):
        self.store = oj.OrchestratorJobsStore()
        # Count store_audio_tour calls thread-safely, and stub the whole delivery
        # so no audio/TTS/HTTP is needed — we are proving the store happens ONCE.
        self._store_calls = []
        self._store_lock = threading.Lock()
        self._saved = {
            name: getattr(orch, name) for name in (
                "store_audio_tour", "_tour_already_stored_for_job",
                "_generator_job_state", "_set_tour_request_status",
                "_release_generation_reservation", "ACTIVE_JOBS",
                "_run_delivery_after_text",
            ) if hasattr(orch, name)
        }
        orch.ACTIVE_JOBS = {}
        orch._tour_already_stored_for_job = lambda jid: False
        orch._generator_job_state = lambda gen: "completed"
        self._status_calls = []
        orch._set_tour_request_status = lambda jid, st: self._status_calls.append((jid, st))
        orch._release_generation_reservation = lambda u, j, reason: None

    def tearDown(self):
        for name, val in self._saved.items():
            setattr(orch, name, val)

    def _counting_store(self, *a, **k):
        with self._store_lock:
            self._store_calls.append(k.get("job_id"))
        return {"success": True, "action": "inserted", "existing_tour_id": None,
                "error": None, "version_no": 1, "replaced_version_no": None}

    def _run_store_phase(self, job_id, lease_owner):
        """Run just the claim→store→complete tail of orchestrate_tour_async for a
        job, under a given lease owner. This is the exact sequence the live thread
        and a resumer both execute around store_audio_tour; here we drive it
        directly so two 'paths' can race deterministically on the real DB claim.
        Returns True if THIS path stored."""
        store = oj.get_orchestrator_jobs_store()
        won = store.claim_store(job_id, lease_owner)
        if not won:
            print(f"[LOCAL-829][test] store already claimed for {job_id} — path stops.")
            return False
        orch.store_audio_tour(
            "Van Gogh Museum, Amsterdam", "Van Gogh Museum, Amsterdam",
            "/tmp/none.zip", 52.3584, 4.8811, "tour text",
            job_id=job_id, user_id="u1",
        )
        store.mark_completed(job_id)
        orch._set_tour_request_status(job_id, "completed")
        return True

    def test_a_live_past_min_idle_and_sweep_store_once(self):
        """The live thread polls past min_idle while a sweep runs on the same
        process. Because the live path RENEWS its lease, the sweep's
        list_resumable never offers the row, so only the live path stores."""
        orch.store_audio_tour = self._counting_store
        job_id = "job-" + uuid.uuid4().hex[:12]
        self.store.create(job_id, location="Van Gogh Museum, Amsterdam",
                          request_string="Van Gogh Museum, Amsterdam", user_id="u1")
        self.store.set_generator_job_id(job_id, "gen-" + uuid.uuid4().hex[:8])

        live_owner = oj.make_owner()
        self.assertIsNotNone(self.store.acquire_lease(job_id, lease_seconds=3, owner=live_owner))

        min_idle = 0  # most aggressive sweep: anything not lease-protected is fair game
        stop = threading.Event()
        swept = []

        def live_thread():
            # Poll for a while, renewing the lease each iteration (as the real
            # poll loop now does), then store exactly once.
            for _ in range(6):
                if stop.is_set():
                    break
                self.store.renew_lease(job_id, live_owner, lease_seconds=3)
                time.sleep(0.15)
            self._run_store_phase(job_id, live_owner)

        def sweep_thread():
            # Hammer the sweep while the live thread is polling. Scope to THIS
            # test's job so leftover resumable rows from other tests in the same
            # throwaway schema are not stored here.
            for _ in range(10):
                if stop.is_set():
                    break
                for job in self.store.list_resumable(min_age_seconds=min_idle):
                    if job["job_id"] != job_id:
                        continue
                    swept.append(job["job_id"])
                    # A resumer would claim+store; drive that tail.
                    r_owner = oj.make_owner()
                    leased = self.store.acquire_lease(job["job_id"], owner=r_owner)
                    if leased is not None:
                        self._run_store_phase(job["job_id"], r_owner)
                time.sleep(0.1)

        lt = threading.Thread(target=live_thread)
        st = threading.Thread(target=sweep_thread)
        lt.start(); st.start()
        lt.join(timeout=10); stop.set(); st.join(timeout=10)

        self.assertEqual(self._store_calls, [job_id],
                         f"expected exactly ONE store for the live job, got {self._store_calls}")
        self.assertNotIn(job_id, swept,
                         "the sweep must never offer a live, lease-renewed row")

    def test_b_two_resumers_race_store_once(self):
        """Two resumers see the same resumable row and race to store. The atomic
        claim_store lets exactly one through."""
        orch.store_audio_tour = self._counting_store
        job_id = "job-" + uuid.uuid4().hex[:12]
        self.store.create(job_id, location="Van Gogh Museum, Amsterdam",
                          request_string="Van Gogh Museum, Amsterdam", user_id="u1")
        self.store.set_generator_job_id(job_id, "gen-" + uuid.uuid4().hex[:8])

        results = []
        res_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def resumer():
            owner = oj.make_owner()
            # Both acquire the lease (one may lose the lease but the store claim
            # is the hard guard either way); then both attempt the store tail.
            self.store.acquire_lease(job_id, owner=owner)
            barrier.wait()  # maximise the race on claim_store
            stored = self._run_store_phase(job_id, owner)
            with res_lock:
                results.append(stored)

        threads = [threading.Thread(target=resumer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(self._store_calls, [job_id],
                         f"two resumers must store exactly once, got {self._store_calls}")
        self.assertEqual(sorted(results), [False, True],
                         "exactly one resumer wins the store claim")

    def test_c_crash_after_claim_then_sweep_stores_once(self):
        """A path claims the store (status 'storing') then 'crashes' before
        storing, leaving the lease to expire. A later sweep must re-offer the row
        and store exactly once — not zero (lost tour) and not twice."""
        orch.store_audio_tour = self._counting_store
        job_id = "job-" + uuid.uuid4().hex[:12]
        self.store.create(job_id, location="Van Gogh Museum, Amsterdam",
                          request_string="Van Gogh Museum, Amsterdam", user_id="u1")
        self.store.set_generator_job_id(job_id, "gen-" + uuid.uuid4().hex[:8])

        # Crash: claim with an already-expired lease, then do nothing (no store).
        crashed_owner = oj.make_owner()
        self.assertTrue(self.store.claim_store(job_id, crashed_owner, lease_seconds=-1))
        self.assertEqual(self._store_calls, [], "the crashed path stored nothing")

        # Later sweep: the 'storing' row with an expired lease is resumable.
        resumable_ids = {j["job_id"] for j in self.store.list_resumable(min_age_seconds=0)}
        self.assertIn(job_id, resumable_ids)
        for job in self.store.list_resumable(min_age_seconds=0):
            if job["job_id"] != job_id:
                continue
            r_owner = oj.make_owner()
            leased = self.store.acquire_lease(job["job_id"], owner=r_owner)
            self.assertIsNotNone(leased, "sweep re-acquires the expired lease")
            self._run_store_phase(job["job_id"], r_owner)

        self.assertEqual(self._store_calls, [job_id],
                         f"crash-after-claim must result in exactly one later store, got {self._store_calls}")
        row = self.store.get(job_id)
        self.assertEqual(row["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
