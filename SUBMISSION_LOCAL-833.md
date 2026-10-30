# SUBMISSION — LOCAL-833

**A generator job that goes silent stays `processing` forever, and its
`orchestrator_jobs` row is re-swept endlessly.**

Base: subscribed `175c5f8b` (contains `4a954c70`).
Branch: `LOCAL-833-stuck-job-terminal`.
`git merge-base --is-ancestor 175c5f8b HEAD` → exit 0 (correct base, branched
from local HEAD, not `origin/*`).

---

## The defect (GCloud_Storied wave 9, orchestrator 00009-7ht)

The Kunsthistorisches proof's generator job **ac864a08** went silent after
07:54Z and stayed `generator_jobs.status='processing'`. Its Cloud Run instance
was recycled mid-job — the worker thread died with the instance, so no code path
ever advanced the row. The orchestrator cancelled the request at 09:15
(`tour_requests` 298 → `failed`), but **orchestrator_jobs 03ec8b1a never went
terminal**, so the LOCAL-821/829 sweep re-took its lease every cycle and polled a
dead job forever. $0 in spend, but it never ends — and every silent job adds
another perpetually-swept row.

Two independent gaps:

1. **Generator side** — a `processing` generator job has no way to become
   terminal once its worker dies. Nothing flips it.
2. **Orchestrator side** — a request can go terminal (`tour_requests` →
   `failed` on cancel/stall) while its durable `orchestrator_jobs` record stays
   non-terminal, so the sweep keeps re-taking it. There was also no cap on how
   many times a stubborn row could be resumed.

---

## The fix

### 1. Generator marks a silent job terminal (`job_store.py`, `generate_tour_text_service.py`)

* `GEN_JOB_STALE_SECONDS` (default **1800 s** = 30 min; env-overridable). A
  non-terminal generator job (`queued`/`processing`) whose `updated_at` has not
  advanced for that long is **stale** — its worker died with a recycled instance.
* **Stale-on-read**: `GeneratorJobsStore.get` flips a stale row to `status='error'`
  (`error_code='stale'`, reason `"stale: no progress since …"`) so the very next
  `/status` poll returns a TERMINAL job. Staleness is computed **in SQL against
  the DB clock** (`updated_at < NOW() - interval`), not with Python
  `datetime.now()` — the DB stores `updated_at` in its own timezone and a local
  wall-clock comparison silently skewed by hours. `_mark_stale` is a conditional
  UPDATE (fires only while still non-terminal AND still stale), so a job that
  completed or wrote progress between the read and the write is never clobbered.
* **Generator stale sweep**: `GeneratorJobsStore.sweep_stale` is a single
  set-based UPDATE flipping every stale non-terminal row; a daemon
  (`_gen_stale_sweep_loop`, `GEN_JOB_SWEEP_ENABLED` default true,
  `GEN_JOB_SWEEP_INTERVAL_SECONDS` default 300 s) runs it so a job becomes
  terminal even if **nothing ever polls it again**.
* The generator's `POST /cancel/<job_id>` now flips a still-running job to a
  TERMINAL `error` (not just a progress string), so a deliberate orchestrator
  give-up makes the generator row terminal immediately.

Why `ac864a08` went silent: a Cloud Run instance recycled mid-job and the
generation thread died with it. The job id survived in `generator_jobs`
(LOCAL-775) but no thread was left to advance it; the stale rule is the mechanism
that now retires exactly that row.

### 2. Orchestrator maps a stale generator job to terminal (`tour_orchestrator_service.py`)

`_generator_job_state` now returns `'error'` for a generator job still reporting
`processing`/`queued` whose `updated_at` is older than `GEN_JOB_STALE_SECONDS`
and that has **no live `heartbeat_at`** (a live worker's heartbeat vetoes
staleness, so a slow-but-alive tour is never killed). This is the orchestrator's
independent backstop; the generator's own stale rule is the primary mechanism.

### 3. Every tour_requests-terminal path makes the durable record terminal

* New `GeneratorGiveUpError`: the deliberate give-up (a real 5-minute no-progress
  stall or the 40-minute absolute cap, after which the orchestrator cancels the
  generator) now raises this typed exception. The exception handler marks the
  `orchestrator_jobs` row `error` **immediately** instead of leaving it resumable
  — that endless re-sweep of a cancelled row is the exact defect. A genuinely
  transient error (poll blip, this instance torn down) with a still-live/completed
  generator job still releases the lease and stays resumable, so a tour the
  generator actually produced is never lost.
* The `no-audio-files`, `store-failed`, exception, and success paths already
  marked the record terminal (`mark_error` / `mark_completed`, which clear the
  lease); this change closes the remaining give-up path.

### 4. Sweep never re-takes a dead row; max 3 resume attempts (`orchestrator_jobs.py`, `tour_orchestrator_service.py`)

`_resume_one_job` now, in order:

* **tour_requests already terminal** (`_tour_request_is_terminal` → `completed`/
  `failed`) → `mark_error` and stop. Directly retires the 298/03ec8b1a case.
* **resume-attempt cap**: `resume_attempts` is a new persisted column
  (`increment_resume_attempts` bumps it and returns the new count). Past
  `ORCH_MAX_RESUME_ATTEMPTS` (default **3**) → `mark_error`, `tour_requests`
  `failed`, reservation released. A stubborn row is never re-taken forever.
* **generator job error/missing/stale** (`_generator_job_state`) → `mark_error`,
  `failed`, reservation released. `error` now covers a silent `processing` job.

A terminal (`completed`/`error`) row is never offered by `list_resumable` — the
lease is cleared and the status is terminal — so the sweep goes quiet.

---

## Tests — `tests/test_local833_stuck_job_terminal.py` (19 tests)

Store-layer legs run inside a throwaway Postgres schema (`IsolatedSchema`, no
shared/production row is ever written — teardown asserts `public` counts
unchanged). Orchestrator-flow legs stub all I/O (no DB, no HTTP).

* **Generator staleness** — `_is_stale_job` (fresh/old/terminal/no-updated_at);
  stale-on-read flips `processing`→`error` against a real schema; a fresh job
  survives a read; `sweep_stale` flips only old non-terminal rows.
* **`_generator_job_state`** — a stale `processing` job maps to `error`; a live
  `heartbeat_at` keeps `processing`; a recent `processing` stays; `completed`/
  `error` pass through.
* **Resume disposition** — already-terminal `tour_requests` → record `error`, no
  delivery; a dead generator job → record `error` + `failed`; exceeding the cap →
  record `error`; under the cap still resumes (attempt counted); a terminal row
  is never resumable; `increment_resume_attempts` persists and returns the new
  count. `GeneratorGiveUpError` is a distinct exception whose disposition marks
  error (no resumable release).

```
$ python3 -m pytest tests/test_local833_stuck_job_terminal.py \
      tests/test_local821_resume.py tests/test_local829_live_lease.py -q
32 passed in 2.40s
```

19 new (833) + 5 (821) + 8 (829) — the LOCAL-821/829 suites still pass unchanged.
The one failing LOCAL-775 test (`test_orchestrator_tolerates_transient_404_then_succeeds`)
is **pre-existing** — confirmed via `git stash` that it fails identically on the
clean base; this change is regression-clean for it.

---

## Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-833 TASK_BUDGET_USD=0.30`)

`run_local833_live.sh` + `docker-compose.local833-proof.yml` — an OWN compose
project (`-p local833`, ports 559xx, OWN postgres volume). Never touches the
shared `audioura-*` containers, never the live DB (`down -v` on its own volume
only). Every service builds from THIS worktree, so the run measures the LOCAL-833
code. Staleness windows are shortened for the test (`GEN_JOB_STALE_SECONDS=30`,
`GEN_JOB_SWEEP_INTERVAL_SECONDS=15`) — production keeps the 1800 s default.

The run **kills the GENERATOR mid-job** (not the orchestrator), then brings a
fresh generator up on the same DB so `/status` answers again and the stale rule
fires:

```
1. fresh_used BEFORE submit = 0
   submit 3-stop walking tour → job_id 979bbb84…
2. generator_job_id=8111754b…  fresh_used after reserve = 1  generator_jobs.status = processing
3. docker kill generator → generator_jobs.status still 'processing' (silent)
   bring a FRESH generator up on the SAME DB
4a. generator_jobs: processing → error
    8111754b…|error|stale|stale: no progress since 2026-10-30T12:12:30 …
4b/c. orchestrator_jobs=error  tour_requests=failed
     979bbb84…|error|0|Error in tour text generation: stale: no progress since …
4d. fresh_used AFTER failure = 0   (pack unit refunded: 1 → 0)
4e. orchestrator_jobs.status=error across 8 cycles (~40 s);
    stored audio_tours = 0; '[sweep] resuming job 979bbb84…' lines = 0

VERDICT: PASS — silent generator job went 'error' (generator stale rule), the
orchestrator_jobs row went terminal 'error', tour_requests 'failed' with the
pack unit refunded, and the sweep stayed QUIET (no re-take, no stored tour).
```

All five required proofs hold: **generator job → error**, **orchestrator row
terminal**, **tour_requests failed + pack unit refunded**, **sweep goes quiet**.
Spend: **$0** — the generator was killed before any paid call completed; the
meter log shows 0 rows under `service=LOCAL-833`, well under the $0.30 cap. Full
transcript in `LOCAL833_LIVE_RUN.log`. The stack was torn down with `down -v`
(own volume); no `local833` container or volume remains.

---

## Files

Changed:
* `job_store.py` — `GEN_JOB_STALE_SECONDS`, `_parse_iso`/`_is_stale_job`/
  `_fmt_duration` helpers, `GeneratorJobsStore` stale-on-read + `_mark_stale` +
  `sweep_stale`, `LayeredJobStore.sweep_stale`.
* `generate_tour_text_service.py` — generator stale-sweep daemon
  (`_gen_stale_sweep_loop` / `_start_gen_stale_sweep_thread`); `/cancel` flips a
  running job to terminal `error`.
* `tour_orchestrator_service.py` — `GEN_JOB_STALE_SECONDS` +
  `ORCH_MAX_RESUME_ATTEMPTS`; `GeneratorGiveUpError`; `_generator_job_state`
  staleness mapping; `_tour_request_is_terminal`; terminal-record disposition in
  the exception handler; resume-attempt cap + terminal-request short-circuit in
  `_resume_one_job`.
* `orchestrator_jobs.py` — `resume_attempts` column (DDL + `ALTER … IF NOT
  EXISTS`), carried in reads, `increment_resume_attempts`.

Added:
* `tests/test_local833_stuck_job_terminal.py` — the 19-test suite.
* `docker-compose.local833-proof.yml`, `run_local833_live.sh`,
  `LOCAL833_LIVE_RUN.log` — the isolated live proof and its transcript.

No `DELETE` anywhere; the live DB is never written (throwaway schema in tests /
own compose volume in the live run). None of DECISIONS.md, CLAUDE.md, BACKLOG.md,
WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md were touched. Committed by
explicit path (never `git add -A`).
