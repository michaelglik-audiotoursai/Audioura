"""[LOCAL-901] Durable job heartbeat for the tour generator.

Why: the orchestrator watchdog (LOCAL-622/833) gives up on a generator job when
none of (progress, updated_at, heartbeat_at) changes for 5 minutes. The engine
never changes the progress text mid-run, and ``heartbeat_at`` used to be added to
the /status reply only when the worker thread was alive IN THE INSTANCE THAT
ANSWERED. With two generator instances, most polls hit the instance without the
thread, whose DB fallback carried no heartbeat -> the watchdog killed a healthy
tour (GCloud_Storied wave 48).

What this module does (no new service, no schema change):

* ``HeartbeatTicker`` - a small daemon thread, started with the job and stopped
  when it ends, that writes ``heartbeat_at`` through the existing job store every
  <= 30 s. The store's upsert also bumps ``updated_at`` (generator_jobs row), and
  ``heartbeat_at`` is merged into the row's ``result`` JSONB, which
  ``GeneratorJobsStore.get`` flattens back out, so ANY instance's /status DB
  fallback returns it.
* ``beat(job_id, label)`` - phase/stop-level heartbeat callable from anywhere in
  the engine (including parallel worker threads). It is a cheap no-op when no
  sink is registered for the job (CLI runs, tests), and never raises.
"""

import threading
import time
from datetime import datetime

TICK_SECONDS = 30.0        # background ticker period (<= 30 s per LOCAL-901)
MIN_WRITE_GAP = 5.0        # production sink writes at most once per N s per job

_SINKS = {}                # job_id -> callable(label)
_LOCK = threading.Lock()


def now_iso():
    """Same naive-local ISO convention as the existing /status heartbeat_at."""
    return datetime.now().isoformat()


def register_sink(job_id, sink):
    with _LOCK:
        _SINKS[job_id] = sink


def unregister_sink(job_id):
    with _LOCK:
        _SINKS.pop(job_id, None)


def beat(job_id, label=""):
    """Record that job `job_id` is alive at phase/stop `label`. Never raises."""
    if not job_id:
        return
    with _LOCK:
        sink = _SINKS.get(job_id)
    if sink is None:
        return
    try:
        sink(label)
    except Exception:
        pass


class HeartbeatTicker:
    """Durably stamps heartbeat_at on a job row while the worker runs.

    `store` is any object with ``update(job_id, **fields)`` (the ACTIVE_JOBS
    LayeredJobStore in production, a fake in tests). `clock` is injectable.
    """

    def __init__(self, store, job_id, interval=TICK_SECONDS,
                 min_gap=MIN_WRITE_GAP, clock=time.monotonic):
        self.store = store
        self.job_id = job_id
        self.interval = interval
        self.min_gap = min_gap
        self._clock = clock
        self._stop = threading.Event()
        self._thread = None
        self._last_write = None
        self._wlock = threading.Lock()
        self.writes = 0

    def write(self, label="", force=False):
        """Write a heartbeat now (throttled unless force). Never raises."""
        with self._wlock:
            t = self._clock()
            if (not force and self._last_write is not None
                    and t - self._last_write < self.min_gap):
                return False
            self._last_write = t
        fields = {"heartbeat_at": now_iso()}
        if label:
            fields["heartbeat_note"] = str(label)[:120]
        try:
            self.store.update(self.job_id, **fields)
            self.writes += 1
            return True
        except Exception:
            return False

    def _run(self):
        while not self._stop.wait(self.interval):
            self.write("tick", force=True)

    def start(self):
        self.write("start", force=True)
        register_sink(self.job_id, self.write)
        self._thread = threading.Thread(
            target=self._run, name=f"hb-{str(self.job_id)[:8]}", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        unregister_sink(self.job_id)
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2.0)
