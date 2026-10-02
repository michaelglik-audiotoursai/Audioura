"""LOCAL-563 — Gemini call recorder + grounded-request budget harness.

Step 1 of the Serper-vs-Gemini comparison: record EXACTLY what Gemini does today,
twice per tour, so (a) we know the run-to-run noise and (b) step 2 can replay the
same grounded questions through Serper. No Serper here, no model changes.

TWO JOBS
--------
1. RECORD every Gemini call at the choke point. The only two sites that attach the
   `google_search` tool are ``story_leads._gemini(grounded=True)`` and
   ``story_leads.gemini_with_sources(grounded=True)`` — the same two the pipeline's
   own [LOCAL-533] counter guards. We wrap BOTH, so we also see the ungrounded
   Gemini calls (token-priced only, counted separately). For each call we keep:
     purpose    the immediate caller (file:function:line) walked up the stack past
                this module and story_leads, so it names the real call site
     prompt     the exact prompt text sent
     grounded   True/False
     response   the response text returned to the caller
     grounding  for gemini_with_sources: the chunks (domain + resolved URI),
                supports (which sentence came from which chunk) and web queries;
                for _gemini the raw google_search tool is attached but the function
                returns only text, so grounding metadata there is {} by design.

2. ENFORCE the hard budget. Michael's Gemini account has ~$15; grounded search is
   $0.035/request. We keep a PROCESS-WIDE, thread-safe cumulative counter of
   grounded requests, persisted to a JSON file on disk so it survives across the
   separate per-run processes the orchestrator spawns. ``would_exceed_cap`` lets the
   orchestrator refuse to START a tour that could cross $14.00 (400 requests). The
   per-run recorder also fails closed INSIDE a run: once the live cumulative total
   reaches the cap, a further grounded request raises ``BudgetExceeded`` rather than
   spend money we do not have.

The counter is incremented at the exact moment a grounded HTTP request is about to
be issued (grounded=True AND an API key present), mirroring story_leads'
``_count_grounding_request`` so our tally equals the pipeline's.
"""
import os
import json
import time
import fcntl
import inspect
import threading

HERE = os.path.dirname(os.path.abspath(__file__))

# $14.00 hard cap on grounded spend; $0.035 per grounded request => 400 requests.
GROUNDING_COST_PER_REQUEST = 0.035
HARD_CAP_USD = 14.00
HARD_CAP_REQUESTS = int(round(HARD_CAP_USD / GROUNDING_COST_PER_REQUEST))  # 400

# Process-wide cumulative counter persisted here so the orchestrator (which spawns
# one process per tour-run) and every run share one running total.
BUDGET_STATE_PATH = os.path.join(HERE, "budget_state.json")
BUDGET_LOG_PATH = os.path.join(HERE, "budget.log")


class BudgetExceeded(RuntimeError):
    """Raised when a grounded request would cross the hard cap mid-run."""


# ───────────────────────── persistent cumulative counter ─────────────────────
# A tiny file-locked JSON store. flock serialises concurrent readers/writers
# across processes; a threading.Lock serialises threads within one process.
_file_guard = threading.Lock()


def _read_state_locked(fh):
    fh.seek(0)
    raw = fh.read().strip()
    if not raw:
        return {"grounded_requests": 0, "updated": None}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"grounded_requests": 0, "updated": None}


def _write_state_locked(fh, state):
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(state, indent=2))
    fh.flush()
    os.fsync(fh.fileno())


def _open_state():
    # a+ so the file is created if missing and we can read and write.
    return open(BUDGET_STATE_PATH, "a+", encoding="utf-8")


def cumulative_grounded_requests():
    """Current process-wide cumulative grounded-request count (from disk)."""
    with _file_guard:
        fh = _open_state()
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            return int(_read_state_locked(fh).get("grounded_requests", 0))
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def add_grounded_requests(n):
    """Atomically add ``n`` to the cumulative counter; return the new total."""
    if n <= 0:
        return cumulative_grounded_requests()
    with _file_guard:
        fh = _open_state()
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            state = _read_state_locked(fh)
            total = int(state.get("grounded_requests", 0)) + int(n)
            state["grounded_requests"] = total
            state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _write_state_locked(fh, state)
            return total
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def reset_budget_state():
    """Zero the cumulative counter. Call once before the whole baseline begins."""
    with _file_guard:
        fh = _open_state()
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            _write_state_locked(fh, {"grounded_requests": 0,
                                     "updated": time.strftime("%Y-%m-%dT%H:%M:%S")})
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


def cumulative_cost_usd():
    return cumulative_grounded_requests() * GROUNDING_COST_PER_REQUEST


def would_exceed_cap(expected_requests):
    """True if starting a tour expected to issue ``expected_requests`` grounded
    requests would reach or cross the $14 cap. The orchestrator calls this BEFORE a
    tour; a conservative ``expected_requests`` keeps us from ever starting a tour we
    cannot finish inside the cap."""
    projected = cumulative_grounded_requests() + max(0, int(expected_requests))
    return projected * GROUNDING_COST_PER_REQUEST >= HARD_CAP_USD


def log_budget(line):
    """Append one line to budget.log (shared across runs, flock-serialised)."""
    with _file_guard:
        fh = open(BUDGET_LOG_PATH, "a", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.write(line.rstrip("\n") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()


# ───────────────────────── per-process call recorder ────────────────────────
class GeminiRecorder:
    """Wraps the two story_leads choke points for the lifetime of one run.

    Install once at the top of a run process. ``records`` accumulates one dict per
    Gemini call. ``grounded_count`` is this run's grounded requests (the delta this
    run contributed to the cumulative counter). On each grounded request we first
    check the LIVE cumulative total and raise BudgetExceeded if it is already at the
    cap, then increment both the live cumulative store and this run's tally.
    """

    def __init__(self, enforce_cap=True):
        self.records = []
        self.grounded_count = 0
        self.ungrounded_count = 0
        self._enforce_cap = enforce_cap
        self._lock = threading.Lock()
        self._sl = None
        self._orig_gemini = None
        self._orig_gws = None

    # Identify the real caller: climb the stack past this file and story_leads so
    # the recorded "purpose" names the pipeline module that wanted the answer.
    @staticmethod
    def _caller():
        for fr in inspect.stack()[2:]:
            base = os.path.basename(fr.filename)
            if base in ("gemini_recorder.py", "story_leads.py"):
                continue
            return f"{base}:{fr.function}:{fr.lineno}"
        return "unknown"

    def _charge_grounded(self):
        """Count one grounded request against the live cap; raise if over."""
        with self._lock:
            live = cumulative_grounded_requests()
            if self._enforce_cap and live * GROUNDING_COST_PER_REQUEST >= HARD_CAP_USD:
                raise BudgetExceeded(
                    f"cumulative grounded requests {live} "
                    f"(${live * GROUNDING_COST_PER_REQUEST:.2f}) at/over cap "
                    f"${HARD_CAP_USD:.2f}; refusing further grounded request")
            add_grounded_requests(1)
            self.grounded_count += 1

    def install(self):
        import story_leads as sl
        self._sl = sl
        self._orig_gemini = sl._gemini
        self._orig_gws = sl.gemini_with_sources

        orig_gemini = self._orig_gemini
        orig_gws = self._orig_gws
        rec = self

        def wrapped_gemini(prompt, model=None, grounded=False):
            caller = rec._caller()
            # Mirror story_leads: a grounded request is billable only when a key is
            # present (keyless returns '' without issuing anything).
            key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
            charged = False
            if grounded and key:
                rec._charge_grounded()
                charged = True
            t0 = time.time()
            err = None
            try:
                resp = orig_gemini(prompt, model=model, grounded=grounded)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                resp = ''
            dt = time.time() - t0
            if not grounded:
                with rec._lock:
                    rec.ungrounded_count += 1
            rec.records.append({
                "site": "story_leads._gemini",
                "caller": caller,
                "grounded": bool(grounded),
                "charged": charged,
                "model": model or os.environ.get('GEMINI_MODEL', 'gemini-flash-latest'),
                "prompt": prompt,
                "response": resp,
                "grounding": {},  # _gemini returns text only; no metadata exposed
                "wall_s": round(dt, 3),
                "error": err,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            return resp

        def wrapped_gws(prompt, model=None, resolve=True, timeout=90, grounded=True):
            caller = rec._caller()
            key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
            charged = False
            if grounded and key:
                rec._charge_grounded()
                charged = True
            t0 = time.time()
            err = None
            try:
                out = orig_gws(prompt, model=model, resolve=resolve,
                               timeout=timeout, grounded=grounded)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                out = {'text': '', 'sources': [], 'supports': [], 'queries': [],
                       'error': err}
            dt = time.time() - t0
            if not grounded:
                with rec._lock:
                    rec.ungrounded_count += 1
            out = out or {}
            rec.records.append({
                "site": "story_leads.gemini_with_sources",
                "caller": caller,
                "grounded": bool(grounded),
                "charged": charged,
                "model": model or os.environ.get('GEMINI_MODEL', 'gemini-flash-latest'),
                "prompt": prompt,
                "response": out.get('text', ''),
                "grounding": {
                    "sources": out.get('sources', []),
                    "supports": out.get('supports', []),
                    "queries": out.get('queries', []),
                    "error": out.get('error', ''),
                },
                "wall_s": round(dt, 3),
                "error": err,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            return out

        sl._gemini = wrapped_gemini
        sl.gemini_with_sources = wrapped_gws
        return self

    def uninstall(self):
        if self._sl is not None:
            if self._orig_gemini is not None:
                self._sl._gemini = self._orig_gemini
            if self._orig_gws is not None:
                self._sl.gemini_with_sources = self._orig_gws

    def __enter__(self):
        return self.install()

    def __exit__(self, exc_type, exc, tb):
        self.uninstall()
        return False
