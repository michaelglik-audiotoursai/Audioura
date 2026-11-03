"""
test_local856_is_test_preservation.py — is_test survives every store path
=========================================================================
LOCAL-856 bug 2: a tour requested with is_test=true was stored is_test=false
on the Background / Cloud-Tasks path (Sophia's re-run, tour 525). The flag was
carried correctly on the in-memory THREAD path (via ACTIVE_JOBS and the
orchestrator_jobs params) but was SILENTLY DROPPED the moment Cloud Tasks was
the transport: the orchestrator's _enqueue_cloud_task / _create_job_in_db did
not carry it, and the tour-worker's store_audio_tour ignored the request and
read only the TOUR_TEST_MODE env (unset in production → false).

These tests pin the flag at every hand-off so the drop cannot come back:

  THREAD path:
    - orchestrator_jobs.PARAM_KEYS includes 'is_test' (guard against a silent
      drop of the durable resume param — the LOCAL-547 failure mode).

  BACKGROUND / CLOUD-TASKS path:
    - orchestrator._enqueue_cloud_task puts is_test in the task payload when
      True, and omits it when falsy.
    - orchestrator._create_job_in_db persists is_test in job_status.output_data
      when True, and omits it when falsy.
    - worker.run_job reads is_test from the payload and forwards it to
      run_generation → store_audio_tour.

  store_audio_tour PRECEDENCE (worker, LOCAL-103 parity):
    - request is_test=True wins over an unset/false TOUR_TEST_MODE env.
    - request is_test=None falls back to the TOUR_TEST_MODE env.

No live DB / network: psycopg2 and the Cloud Tasks client are mocked, so the
test asserts on the exact SQL parameters and payloads the code would send.

Exit 0 = all pass. Exit 1 = any failure.

Usage:
    python3 tests/test_local856_is_test_preservation.py
"""
import os
import sys
import json
import types
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS: {name}")
        PASS += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL += 1


# ─── Minimal psycopg2 cursor/conn capture double ──────────────────────────────
class _CaptureCursor:
    """Records every execute() as (sql, params). fetchone() returns a canned row."""
    def __init__(self, fetch_rows=None):
        self.calls = []
        self._fetch_rows = list(fetch_rows or [])
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
    def fetchone(self):
        return self._fetch_rows.pop(0) if self._fetch_rows else None
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _CaptureConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
    def cursor(self):
        return self._cursor
    def commit(self):
        self.committed = True
    def close(self):
        pass


@contextlib.contextmanager
def _patched_psycopg2_connect(module, cursor):
    """Patch `module`'s psycopg2.connect to hand back a conn wrapping `cursor`.

    Both the orchestrator and the worker do `import psycopg2` inside the
    function, so patching the already-imported psycopg2 module's `connect` (and
    `Binary`) covers them."""
    import psycopg2
    orig_connect = psycopg2.connect
    orig_binary = getattr(psycopg2, "Binary", None)
    psycopg2.connect = lambda *a, **k: _CaptureConn(cursor)
    psycopg2.Binary = lambda b: b
    try:
        yield
    finally:
        psycopg2.connect = orig_connect
        if orig_binary is not None:
            psycopg2.Binary = orig_binary


# ═══════════════════════════════════════════════════════════════════════════════
# THREAD path — durable resume param list must include is_test
# ═══════════════════════════════════════════════════════════════════════════════
def test_thread_param_keys_include_is_test():
    print("\n[THREAD] orchestrator_jobs.PARAM_KEYS carries is_test")
    import orchestrator_jobs
    check("PARAM_KEYS includes 'is_test'",
          "is_test" in orchestrator_jobs.PARAM_KEYS,
          f"PARAM_KEYS={orchestrator_jobs.PARAM_KEYS}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLOUD-TASKS path — enqueue payload carries is_test
# ═══════════════════════════════════════════════════════════════════════════════
def _install_fake_cloud_tasks():
    """Inject a fake google.cloud.tasks_v2 + google.protobuf.timestamp_pb2 so
    _enqueue_cloud_task runs without the real SDK, and capture the task body."""
    captured = {}

    class _FakeClient:
        def queue_path(self, *a, **k):
            return "queue/path"
        def create_task(self, request=None):
            captured["task"] = request["task"]
            return types.SimpleNamespace(name="projects/x/tasks/1")

    class _HttpMethod:
        POST = "POST"

    tasks_v2 = types.SimpleNamespace(
        CloudTasksClient=lambda *a, **k: _FakeClient(),
        HttpMethod=_HttpMethod,
    )
    google_mod = sys.modules.get("google") or types.ModuleType("google")
    cloud_mod = types.ModuleType("google.cloud")
    cloud_mod.tasks_v2 = tasks_v2
    protobuf_mod = types.ModuleType("google.protobuf")
    protobuf_mod.timestamp_pb2 = types.SimpleNamespace(Timestamp=object)
    google_mod.cloud = cloud_mod
    google_mod.protobuf = protobuf_mod
    sys.modules["google"] = google_mod
    sys.modules["google.cloud"] = cloud_mod
    sys.modules["google.cloud.tasks_v2"] = tasks_v2
    sys.modules["google.protobuf"] = protobuf_mod
    sys.modules["google.protobuf.timestamp_pb2"] = protobuf_mod.timestamp_pb2
    return captured


def _payload_from_captured(captured):
    body = captured["task"]["http_request"]["body"]
    return json.loads(body.decode() if isinstance(body, (bytes, bytearray)) else body)


def test_enqueue_cloud_task_carries_is_test():
    print("\n[CLOUD-TASKS] _enqueue_cloud_task payload carries is_test")
    import tour_orchestrator_service as orch

    captured = _install_fake_cloud_tasks()
    ok = orch._enqueue_cloud_task(
        "job-1", "Boston", "walking", 2, "user-1", "Boston walking tour",
        "en", stops=None, is_test=True)
    check("_enqueue_cloud_task returned True (enqueued)", ok is True, f"got {ok!r}")
    payload = _payload_from_captured(captured)
    check("payload has is_test=True when requested",
          payload.get("is_test") is True, f"payload={payload}")

    captured2 = _install_fake_cloud_tasks()
    orch._enqueue_cloud_task(
        "job-2", "Boston", "walking", 2, "user-1", "Boston walking tour",
        "en", stops=None, is_test=None)
    payload2 = _payload_from_captured(captured2)
    check("payload omits is_test when not a test",
          "is_test" not in payload2, f"payload={payload2}")


def test_create_job_in_db_persists_is_test():
    print("\n[CLOUD-TASKS] _create_job_in_db persists is_test in output_data")
    import tour_orchestrator_service as orch

    cur = _CaptureCursor()
    with _patched_psycopg2_connect(orch, cur):
        orch._create_job_in_db("job-3", "Boston", "walking", 2, "user-1",
                               "Boston walking tour", "en", is_test=True)
    insert = next((c for c in cur.calls if "INSERT INTO job_status" in c[0]), None)
    check("_create_job_in_db issued the job_status INSERT", insert is not None)
    if insert is not None:
        output_data = json.loads(insert[1][-1])  # output_data is the last param
        check("output_data.is_test is True when requested",
              output_data.get("is_test") is True, f"output_data={output_data}")

    cur2 = _CaptureCursor()
    with _patched_psycopg2_connect(orch, cur2):
        orch._create_job_in_db("job-4", "Boston", "walking", 2, "user-1",
                               "Boston walking tour", "en", is_test=None)
    insert2 = next((c for c in cur2.calls if "INSERT INTO job_status" in c[0]), None)
    if insert2 is not None:
        output_data2 = json.loads(insert2[1][-1])
        check("output_data omits is_test when not a test",
              "is_test" not in output_data2, f"output_data={output_data2}")


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER store_audio_tour — request precedence over env (LOCAL-103 parity)
# ═══════════════════════════════════════════════════════════════════════════════
def _worker_insert_is_test(cur):
    """Return the is_test value bound in the worker's audio_tours INSERT, or raise."""
    insert = next((c for c in cur.calls if "INSERT INTO audio_tours" in c[0]), None)
    assert insert is not None, f"no audio_tours INSERT found in {[c[0][:40] for c in cur.calls]}"
    params = insert[1]
    # INSERT columns: (..., zip_filename, is_test, stops_count) — is_test is 2nd-last.
    return params[-2]


def _make_zip(tmpdir):
    import zipfile
    path = os.path.join(tmpdir, "tour.zip")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.txt", "hello")
    return path


def test_worker_store_request_wins_over_env():
    print("\n[WORKER] store_audio_tour: request is_test wins over unset env")
    import tempfile
    import tour_worker_service as worker

    with tempfile.TemporaryDirectory() as td:
        zip_path = _make_zip(td)
        # Env explicitly OFF (production shape). fetchone() -> None so the
        # "existing tour" check misses and the INSERT branch runs.
        old_env = os.environ.pop("TOUR_TEST_MODE", None)
        try:
            cur = _CaptureCursor(fetch_rows=[None])
            with _patched_psycopg2_connect(worker, cur):
                ok = worker.store_audio_tour(
                    "Boston Walking Tour [TEST]", "Boston walking tour",
                    zip_path, 42.36, -71.06, tour_content="t", stops_count=2,
                    is_test=True)
            check("store_audio_tour returned True", ok is True, f"got {ok!r}")
            check("INSERT bound is_test=True from the request (env unset)",
                  _worker_insert_is_test(cur) is True)
        finally:
            if old_env is not None:
                os.environ["TOUR_TEST_MODE"] = old_env


def test_worker_store_env_fallback_when_request_none():
    print("\n[WORKER] store_audio_tour: env fallback when request is None")
    import tempfile
    import tour_worker_service as worker

    with tempfile.TemporaryDirectory() as td:
        zip_path = _make_zip(td)
        old_env = os.environ.get("TOUR_TEST_MODE")
        try:
            os.environ["TOUR_TEST_MODE"] = "true"
            cur = _CaptureCursor(fetch_rows=[None])
            with _patched_psycopg2_connect(worker, cur):
                worker.store_audio_tour(
                    "Real Tour", "real request", zip_path, 42.36, -71.06,
                    tour_content="t", stops_count=2, is_test=None)
            check("INSERT bound is_test=True from env when request None",
                  _worker_insert_is_test(cur) is True)

            os.environ["TOUR_TEST_MODE"] = "false"
            cur2 = _CaptureCursor(fetch_rows=[None])
            with _patched_psycopg2_connect(worker, cur2):
                worker.store_audio_tour(
                    "Real Tour 2", "real request 2", zip_path, 42.36, -71.06,
                    tour_content="t", stops_count=2, is_test=None)
            check("INSERT bound is_test=False from env when request None and env off",
                  _worker_insert_is_test(cur2) is False)
        finally:
            if old_env is None:
                os.environ.pop("TOUR_TEST_MODE", None)
            else:
                os.environ["TOUR_TEST_MODE"] = old_env


def test_worker_run_job_forwards_is_test():
    print("\n[WORKER] run_job reads is_test from payload and forwards it")
    import tour_worker_service as worker

    seen = {}

    def _fake_run_generation(job_id, location, tour_type, total_stops, user_id=None,
                             request_string=None, language='en', stops=None, is_test=None):
        seen["is_test"] = is_test
        return True

    orig = worker.run_generation
    worker.run_generation = _fake_run_generation
    try:
        app = worker.app
        app.config["TESTING"] = True
        client = app.test_client()
        resp = client.post("/run-job", json={
            "job_id": "job-5", "location": "Boston", "tour_type": "walking",
            "total_stops": 2, "user_id": "u1", "request_string": "Boston walking",
            "language": "en", "is_test": True,
        })
        check("run_job returned 200", resp.status_code == 200, f"status={resp.status_code}")
        check("run_job forwarded is_test=True to run_generation",
              seen.get("is_test") is True, f"seen={seen}")

        seen.clear()
        resp2 = client.post("/run-job", json={
            "job_id": "job-6", "location": "Boston", "tour_type": "walking",
            "total_stops": 2, "user_id": "u1", "request_string": "Boston walking",
            "language": "en",
        })
        check("run_job forwards is_test=None when payload has no flag",
              seen.get("is_test") is None, f"seen={seen}")
    finally:
        worker.run_generation = orig


# ═══════════════════════════════════════════════════════════════════════════════
# shared_tours.audio_tour_id ensure (bug 1) — read & write services heal column
# ═══════════════════════════════════════════════════════════════════════════════
def test_map_delivery_startup_ensures_audio_tour_id():
    print("\n[SHARE-SCHEMA] map_delivery/app.py ensures shared_tours.audio_tour_id at start")
    import importlib.util

    md_dir = os.path.join(ROOT, "map_delivery")
    if md_dir not in sys.path:
        sys.path.insert(0, md_dir)

    cur = _CaptureCursor()
    import psycopg2
    orig_connect = psycopg2.connect
    psycopg2.connect = lambda *a, **k: _CaptureConn(cur)
    try:
        spec = importlib.util.spec_from_file_location(
            "md_app_local856", os.path.join(md_dir, "app.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        psycopg2.connect = orig_connect

    altered = any(
        "shared_tours" in (sql or "") and "ADD COLUMN IF NOT EXISTS audio_tour_id" in (sql or "")
        for sql, _ in cur.calls)
    check("startup ran additive ALTER shared_tours ADD COLUMN IF NOT EXISTS audio_tour_id",
          altered, f"calls={[c[0][:60] for c in cur.calls]}")

    destructive = any(
        ("DROP" in (sql or "").upper() or "DELETE" in (sql or "").upper())
        and "shared_tours" in (sql or "")
        for sql, _ in cur.calls)
    check("no DROP/DELETE on shared_tours in the ensure", not destructive)


def test_tour_sharing_schema_ensure_adds_audio_tour_id():
    print("\n[SHARE-SCHEMA] tour_sharing.ensure_shared_tours_schema is additive")
    import tour_sharing

    cur = _CaptureCursor()
    import psycopg2
    orig_connect = psycopg2.connect
    psycopg2.connect = lambda *a, **k: _CaptureConn(cur)
    try:
        ok = tour_sharing.ensure_shared_tours_schema(
            "postgresql://admin:admin@localhost:5432/audiotours")
    finally:
        psycopg2.connect = orig_connect

    check("ensure_shared_tours_schema returned True", ok is True, f"got {ok!r}")
    altered = any("ADD COLUMN IF NOT EXISTS audio_tour_id" in (sql or "")
                  for sql, _ in cur.calls)
    check("write-side ensure ran the additive audio_tour_id ALTER", altered,
          f"calls={[c[0][:50] for c in cur.calls]}")
    creates_table = any("CREATE TABLE IF NOT EXISTS shared_tours" in (sql or "")
                        for sql, _ in cur.calls)
    check("write-side ensure still creates the table idempotently", creates_table)


def main():
    print("=" * 70)
    print("LOCAL-856 — is_test preservation across every store path")
    print("=" * 70)
    test_thread_param_keys_include_is_test()
    test_enqueue_cloud_task_carries_is_test()
    test_create_job_in_db_persists_is_test()
    test_worker_store_request_wins_over_env()
    test_worker_store_env_fallback_when_request_none()
    test_worker_run_job_forwards_is_test()
    test_map_delivery_startup_ensures_audio_tour_id()
    test_tour_sharing_schema_ensure_adds_audio_tour_id()
    print("\n" + "=" * 70)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
