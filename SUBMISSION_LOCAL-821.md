# SUBMISSION — LOCAL-821

**Branch:** `LOCAL-821-resume-and-no-overwrite`  (base: subscribed = `128c1de9`)

Two production defects on the Subscribed orchestrator, both reproduced in a live
run and both fixed here:

- **(A)** Cloud Run sends SIGTERM to the orchestrator while a tour is still
  generating → the finished tour is lost (no `audio_tours` row, `tour_requests`
  stuck at `started`). The generator result is already safe in `generator_jobs`
  (LOCAL-775); only the orchestrator's delivery was lost.
- **(B)** A new request whose request string matched an existing tour (465)
  **overwrote** that tour's stops (and flagged its translation stale). A new
  request must never rewrite an existing tour's content.

---

## (A) Resume after SIGTERM — durable job record + resume-on-boot + sweep

### Root cause
`orchestrate_tour_async` runs in a daemon thread. It POSTs the tour-generator
`/generate`, gets back the generator's text job id (`job_id_1`), and keeps it —
with every request parameter — **only in the in-memory `ACTIVE_JOBS` dict**. The
SIGTERM handler (`_graceful_shutdown`) joins in-flight threads for at most 240 s
and then `sys.exit(0)`; a tour longer than that (any large museum) dies with the
process. Nothing durable linked the orchestrator job to its generator job, so no
fresh instance could finish it — even though the generator's result was already
persisted in `generator_jobs` and is readable from any instance (LOCAL-775/D718).

### Fix
A durable record of every orchestrator job plus a resume-on-boot and periodic
sweep that re-attaches to the **existing** generator job (no re-generation):

- **`migration/sql/061_orchestrator_jobs.sql`** + **`orchestrator_jobs.py`**
  (`OrchestratorJobsStore`): one row per orchestrator job —
  `job_id` (PK), `generator_job_id`, `status`, `params` (JSONB: the full
  `orchestrate_tour_async` argument set, incl. `store_mode`), `error`,
  `lease_owner`, `lease_expires_at`. Additive, self-healing DDL (same pattern as
  `generator_jobs`); best-effort throughout so a DB blip never breaks live
  generation.
- **`/generate`** writes the row (`status=queued`) **before** generation starts;
  `orchestrate_tour_async` persists `generator_job_id` the moment `/generate`
  returns it — this is what lets a fresh instance re-attach.
- **`orchestrate_tour_async(..., resume_generator_job_id=…)`**: when set, it
  **skips `/generate`** and re-polls the existing generator job. A completed
  generator job returns its `tour_content`, so the normal poll→modernized→store
  delivery path is reused verbatim. An idempotency guard
  (`_tour_already_stored_for_job`, reads `tour_requests.status == 'completed'`)
  makes a double-resume a no-op.
- **Resume-on-boot + sweep** (`_resume_and_sweep_loop`, daemon thread started in
  `__main__`, gated by `ORCH_RESUME_ENABLED`): find non-terminal rows, take a
  **lease** (`acquire_lease` — one atomic `UPDATE … WHERE lease free/expired
  RETURNING`, so two instances can never both finish a job), then: generator
  `completed`/`processing`/`queued` → resume delivery; generator `error`/
  `missing` → mark the record `error`, flip `tour_requests` to `failed`, and give
  back the device's reserved pack unit. Resume-on-boot uses `min_idle=0`; the
  periodic sweep uses `ORCH_SWEEP_MIN_IDLE_SECONDS` so a healthy in-flight job on
  another live instance is left alone.
- The SIGTERM handler is unchanged in spirit but is **no longer the only path**:
  if the 240 s wait is not enough, the next instance's resume/sweep finishes the
  job.

---

## (B) A new request never overwrites an existing tour

### Root cause
`store_audio_tour`'s existing-tour lookup keys on `(lower(tour_name),
creator_user_id, track)` — **not** on `request_string`. When a new request
resolved to the same name/creator/track with **different** text it fell into the
LOCAL-606 / D622 "replace-on-change" branch, which archived the old content and
**overwrote the row's stops/content/zip** and flagged its translations stale.
That branch was meant only for an explicit creator regeneration, but it fired for
any serving request — so a proof request silently rewrote tour 465.

### Fix
`store_audio_tour` gains a **`store_mode`** parameter:

- **`serve`** (default — every normal generation/serving request): **never
  replaces.** Byte-identical text is still a cache hit (`number_requested++`,
  action `already_exists`). Different text **inserts a NEW, separate tour** under
  a disambiguated name (`<name> [<jobid8>]`, action `inserted`) and leaves the
  existing tour byte-for-byte unchanged.
- **`regenerate`** (explicit admin path only): keeps the LOCAL-606 replace,
  archiving the previous content to `audio_tour_versions` **first** (reversible).

The normal `orchestrate_tour_async` store call passes `store_mode='serve'`. A new
admin endpoint **`POST /admin/regenerate-tour`** is the only path that replaces:
it is fail-closed admin-gated (`_require_admin_key` / `ADMIN_API_KEY` via
`X-API-Key`, 503 when unset, 401 on mismatch), reads the existing tour's identity,
and runs the pipeline with `store_mode='regenerate'`.

---

## Tests

New, both isolated in a throwaway Postgres schema (zero shared/production writes,
asserted before/after):

- **`tests/test_local821_resume.py`** (A) — 5 tests. Store layer:
  create → `list_resumable` → **exclusive** lease (a live lease blocks a second
  instance) → expired lease is reacquirable → `mark_completed` is terminal and no
  longer resumable. Resume flow (I/O stubbed): a killed-mid-poll job is resumed
  and delivered **exactly once** with `resume_generator_job_id` set (so
  `/generate` is skipped); a resume is **idempotent** when the tour is already
  stored; a **failed** generator job → record `error` + `tour_requests` `failed`.
- **`tests/test_local821_no_overwrite.py`** (B) — 3 tests.
  (1) identical request twice → the first tour is **byte-for-byte unchanged**
  (cache hit, `number_requested++`, no version archived);
  (2) a serve request with different text → a **new separate tour** is inserted
  and the original's content/zip/stops are unchanged and **no version archived**;
  (3) an explicit `regenerate` → the tour **is** replaced with the old content
  archived to `audio_tour_versions` **first**.

Pre-existing replace-mechanism tests were updated to opt into
`store_mode='regenerate'` (they test the replace path, which now requires the
explicit mode): `test_local606_replace_on_change.py`,
`test_local718_tour_creator.py`, `test_local737_track_subscribed.py`,
`test_local727_track_name_key.py`.

```
tests/test_local821_resume.py ........ 5 passed
tests/test_local821_no_overwrite.py ... 3 passed
tests/test_local718/737/727 (replace cases, regenerate mode) ... 26 passed
```

Regression note: `test_local606_replace_on_change.py` has 4 failures that are
**pre-existing on the base commit** (`128c1de9`) — a NULL-creator lookup quirk in
the throwaway schema, unrelated to LOCAL-821. Verified the failure set is
identical on base and this branch (4 failed / 23 passed both ways): this change
introduces **zero** new failures.

---

## Live proof — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-821 TASK_BUDGET_USD=0.60`)

Own compose project (`-p local821`, `docker-compose.local821-proof.yml`,
`local821-initdb/`, `run_local821_live.sh`), spare ports, OWN postgres volume —
never the shared `audioura-*` containers, never the live DB. The meter contract
(`meter_container_env`) tagged every paid call `service=LOCAL-821`.

**(A) kill mid-generation → fresh instance resumes → stored once.** Submitted a
3-stop walking tour (`Public art walk near Salem Common, Salem, MA`). Once
`orchestrator_jobs.status=processing` with `generator_job_id` persisted
(generation in flight), `docker kill`ed the orchestrator (→ `Exited (137)`).
Right after the kill: `tour_requests='started'`, `audio_tours` count `0`, the
generator still `processing` (it was never killed). Brought up a **fresh**
orchestrator on the same volume — log:
`[LOCAL-821] RESUME — skipping /generate, re-polling generator job adcc506e…`.
Final state: **one** `audio_tours` row, `tour_requests='completed'`,
`orchestrator_jobs='completed'` with the lease cleared. The tour was stored
**exactly once**.

**(B) identical request → existing tour untouched.** Captured the stored tour
(`id=1`, `md5=197bd78d…`, `stops=2`, `number_requested=1`), then submitted the
**identical** request. The regenerated text differed, so serve mode inserted a
**new separate** tour under `… [744a6ea5]`; the original `id=1` was
**byte-for-byte unchanged** (`md5` still `197bd78d…`, `stops=2`,
`number_requested=1`) and `audio_tour_versions` for tour 1 = **0** (no
replacement). The overwrite that hit 465 cannot happen.

### `python3 task_budget_report.py LOCAL-821`

```
Task budget report: LOCAL-821
Ledger: /Users/micha/.audioura_task_budgets/LOCAL-821.json

  when (UTC)                      usd  note
  ----------------------------------------------------------
  2026-10-30T03:28:17Z        $0.4109  live proof: kill/resume 3-stop walking tour + identical-request-untouched (local821 compose, metered service=LOCAL-821, 106 rows)
  ----------------------------------------------------------
  TOTAL (1 runs)              $0.4109

Budget:    $0.6000
Remaining: $0.1891
```

106 paid-API rows tagged `service=LOCAL-821` in `~/Audioura/meterlogs/paid_api_calls.jsonl`.
Teardown: `docker compose -p local821 … down -v` (own volume only); zero
`local821-*` containers remain.

---

## Files changed

- `tour_orchestrator_service.py` — resume params on `orchestrate_tour_async`
  (`resume_generator_job_id`, `store_mode`); `_generator_job_state`,
  `_tour_already_stored_for_job`; durable-record writes + terminal transitions;
  resume/sweep (`_resume_one_job`, `_sweep_resumable_jobs`,
  `_resume_and_sweep_loop`, `_start_resume_sweep_thread`); `/generate` writes the
  durable record; `store_audio_tour` `store_mode`; `POST /admin/regenerate-tour`.
- `orchestrator_jobs.py` — new durable store (lease, resumable scan).
- `migration/sql/061_orchestrator_jobs.sql` — new additive table.
- `Dockerfile.orchestrator` — ship `orchestrator_jobs.py` in the image.
- `tests/test_local821_resume.py`, `tests/test_local821_no_overwrite.py` — new.
- `tests/test_local606_replace_on_change.py`, `tests/test_local718_tour_creator.py`,
  `tests/test_local737_track_subscribed.py`, `tests/test_local727_track_name_key.py`
  — opt into `store_mode='regenerate'` for the replace cases.
- `docker-compose.local821-proof.yml`, `local821-initdb/*`, `run_local821_live.sh`
  — the isolated live-proof stack.
