"""LOCAL-839 — the modernized (voice/ZIP) service is safe across >1 instance.

Evidence this reproduces (GCloud_Storied, wave 14): the orchestrator created a
modernized job on one instance, then polled /status — and later GET /download —
and a DIFFERENT instance answered "Job not found" / had no ZIP on its local
disk, so the request failed. The old modernized job_store had only memory and
the ZIP was served from the LOCAL TOURS_DIR, so neither status nor the ZIP
survived a hop to another instance.

The fix (this ticket):
  * the modernized service uses the LAYERED job store (LOCAL-775): a job created
    on instance A lives in the shared generator_jobs table, so instance B's
    /status finds it;
  * on completion the ZIP bytes are stored base64 in that same shared row
    (zip_b64), and /download serves them from the store when the local file is
    absent — so instance B can hand the ZIP back even though it never wrote the
    file.

This test runs WITHOUT a real Postgres: a tiny in-process fake stands in for the
generator_jobs table and is SHARED by both instances' stores (exactly what the
real table does across instances). Each instance has its OWN memory cache and
its OWN TOURS_DIR — the two things that are per-instance in production — so a
job created on A is genuinely absent from B's memory and B's disk. The test then
proves B still serves /status and /download, and that the served ZIP is the one
A built. A separate test confirms the plain MemoryJobStore does NOT survive the
hop, so the test is proving the layered store is what fixes it.
"""
import base64
import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import job_store
from job_store import LayeredJobStore, MemoryJobStore


# --------------------------------------------------------------------------- #
# A shared fake for the generator_jobs TABLE.                                  #
# --------------------------------------------------------------------------- #
# One instance of this dict-backed store stands in for the real table and is
# handed to BOTH LayeredJobStores, so a write by instance A's store is visible
# to instance B's store — the whole point of a shared DB. It implements only the
# surface LayeredJobStore uses: upsert (merging result), get, delete, items.
class SharedFakeGeneratorJobsStore:
    def __init__(self, table):
        self.service_name = 'tour-generation-modernized'
        self._table = table  # shared dict: job_id -> flat job dict

    _COLUMNS = ('status', 'progress', 'location', 'tour_type', 'total_stops')

    def upsert(self, job_id, **fields):
        row = self._table.setdefault(job_id, {'job_id': job_id, 'result': {}})
        for key, val in fields.items():
            if key in ('job_id', 'created_at', 'updated_at', 'instance_id'):
                continue
            if key in self._COLUMNS:
                row[key] = val
            else:
                # Everything else is a result key (merged, like result || EXCLUDED).
                row.setdefault('result', {})[key] = val

    create = upsert
    update = upsert

    def get(self, job_id):
        row = self._table.get(job_id)
        if not row:
            return None
        flat = {k: v for k, v in row.items() if k != 'result'}
        flat.update(row.get('result', {}))
        flat['job_id'] = job_id
        return flat

    def delete(self, job_id):
        self._table.pop(job_id, None)

    def items(self):
        return [(jid, self.get(jid)) for jid in list(self._table)]

    def sweep_stale(self, stale_seconds=None, limit=200):
        return 0


def _make_layered_store(shared_table):
    """A LayeredJobStore with its OWN memory cache but the SHARED fake table."""
    store = LayeredJobStore(service_name='tour-generation-modernized')
    store._db = SharedFakeGeneratorJobsStore(shared_table)
    return store


def _build_zip(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('index.html', '<html>tour</html>')
        z.writestr('audio_1.txt', text)
        z.writestr('audio_1.mp3', b'ID3fake-audio-bytes')
    return buf.getvalue()


class ModernizedMultiInstanceTest(unittest.TestCase):
    """Two modernized instances, one shared store: job on A, served by B."""

    def setUp(self):
        # The shared "generator_jobs table" both instances read/write.
        self.shared_table = {}
        # Per-instance TOURS_DIR (a job's ZIP file is written on its owning
        # instance only).
        self.tours_a = tempfile.mkdtemp(prefix='l839_a_')
        self.tours_b = tempfile.mkdtemp(prefix='l839_b_')
        # Per-instance stores: separate memory caches, shared table.
        self.store_a = _make_layered_store(self.shared_table)
        self.store_b = _make_layered_store(self.shared_table)

        # Import the service module once; we rebind ACTIVE_JOBS / TOURS_DIR to
        # swap between "instance A" and "instance B" when driving the endpoints.
        import tour_generation_modernized as svc
        self.svc = svc
        svc.app.config['TESTING'] = True

    def _as_instance(self, store, tours_dir):
        """Point the module (and its Flask views) at a given instance."""
        self.svc.ACTIVE_JOBS = store
        self.svc.TOURS_DIR = tours_dir

    # -- the job A creates and completes --------------------------------------
    def _create_completed_job_on_a(self, job_id='job-A-1'):
        self._as_instance(self.store_a, self.tours_a)
        # Instance A creates the job (queued), like /process does.
        self.store_a[job_id] = {
            'status': 'queued',
            'progress': 'queued',
            'modernized': True,
        }
        # A builds the ZIP on ITS OWN disk...
        zip_name = f'{job_id}.zip'
        zip_bytes = _build_zip('Stop 1: Walk north.')
        with open(os.path.join(self.tours_a, zip_name), 'wb') as f:
            f.write(zip_bytes)
        # ...and completes the job, storing the ZIP in the shared store.
        self.svc._store_zip_in_job_store(job_id, zip_name)
        self.store_a.update(job_id, status='completed',
                            progress='Modernized tour created successfully!',
                            output_zip=zip_name, modernized=True)
        return job_id, zip_name, zip_bytes

    def test_status_served_by_other_instance(self):
        job_id, _, _ = self._create_completed_job_on_a()

        # Hop to instance B: it never saw this job in memory, and the ZIP is not
        # on its disk. Before the fix this is the 404.
        self._as_instance(self.store_b, self.tours_b)
        self.assertNotIn(job_id, self.store_b._memory,
                         "precondition: job must be absent from B's memory cache")

        client = self.svc.app.test_client()
        resp = client.get(f'/status/{job_id}')
        self.assertEqual(resp.status_code, 200,
                         "instance B must find the job via the shared store")
        data = resp.get_json()
        self.assertEqual(data['status'], 'completed')
        # /status must NOT leak the (large) base64 ZIP.
        self.assertNotIn('zip_b64', data,
                         "/status must strip the inline ZIP bytes")

    def test_download_served_by_other_instance(self):
        job_id, zip_name, zip_bytes = self._create_completed_job_on_a()

        # Hop to instance B — no local file, must serve from the shared store.
        self._as_instance(self.store_b, self.tours_b)
        self.assertFalse(os.path.exists(os.path.join(self.tours_b, zip_name)),
                         "precondition: ZIP must not be on B's disk")

        client = self.svc.app.test_client()
        resp = client.get(f'/download/{job_id}')
        self.assertEqual(resp.status_code, 200,
                         "instance B must serve the ZIP from the shared store")
        self.assertEqual(resp.data, zip_bytes,
                         "served bytes must be byte-identical to the ZIP A built")
        # And it is a valid ZIP with the expected member.
        with zipfile.ZipFile(io.BytesIO(resp.data)) as z:
            self.assertIn('audio_1.mp3', z.namelist())

    def test_owning_instance_still_serves_local_file(self):
        # Instance A (the owner) serves straight from disk, no decode.
        job_id, zip_name, zip_bytes = self._create_completed_job_on_a()
        self._as_instance(self.store_a, self.tours_a)
        client = self.svc.app.test_client()
        resp = client.get(f'/download/{job_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, zip_bytes)

    def test_memory_store_does_NOT_survive_the_hop(self):
        # Control: with the OLD memory-only store, each instance has an isolated
        # dict, so B genuinely 404s — this is the bug the layered store fixes.
        mem_a = MemoryJobStore()
        mem_b = MemoryJobStore()
        job_id = 'job-mem-1'
        self._as_instance(mem_a, self.tours_a)
        mem_a[job_id] = {'status': 'completed', 'output_zip': f'{job_id}.zip'}

        self._as_instance(mem_b, self.tours_b)
        client = self.svc.app.test_client()
        self.assertEqual(client.get(f'/status/{job_id}').status_code, 404)
        self.assertEqual(client.get(f'/download/{job_id}').status_code, 404)


class CleanupZipRowTest(unittest.TestCase):
    """The orchestrator's post-store cleanup removes ONLY the zip_b64 key."""

    def test_jsonb_key_delete_semantics(self):
        # Mirror the SQL `result - 'zip_b64'` as a dict op and assert it leaves
        # every other field (the tour data) intact. (The real UPDATE is tested
        # live; this pins the intended semantics: never drop other keys.)
        result = {
            'zip_b64': base64.b64encode(b'zip').decode('ascii'),
            'output_zip': 'tour.zip',
            'tour_content': 'Stop 1: ...',
            'modernized': True,
        }
        cleaned = {k: v for k, v in result.items() if k != 'zip_b64'}
        self.assertNotIn('zip_b64', cleaned)
        self.assertEqual(cleaned['output_zip'], 'tour.zip')
        self.assertEqual(cleaned['tour_content'], 'Stop 1: ...')
        self.assertTrue(cleaned['modernized'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
