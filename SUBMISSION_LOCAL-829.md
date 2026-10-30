# SUBMISSION_LOCAL-829 — the live path now owns its row, and the store is idempotent

**Branch:** `LOCAL-829-live-lease`
**Base:** subscribed `112480f3` (contains `50893631` — LOCAL-821/821B). Verified:
`git merge-base --is-ancestor 112480f3 HEAD` exits 0.

## The defect

GCloud_Storied wave 8 (orchestrator `00008-7c2` at `50893631`,
`ORCH_RESUME_ENABLED=true`, sweep `min_idle=300 s`): the fresh proof
"Van Gogh Museum, Amsterdam" was stored **TWICE** — `audio_tours` 500 and 501,
identical, 0.1 ms apart. At 06:05:32 the periodic sweep picked up orch job
`58bbf87a`: its `orchestrator_jobs` row was older than `min_idle`, and the LIVE
thread on the SAME instance — still polling the generator — **held no lease and
never heartbeat**. The sweep saw an "orphaned" row, resumed it in parallel, and
both the live thread and the resumer ran `store_audio_tour`. Every tour longer
than the sweep's `min_idle` would double-store.

LOCAL-821 gave the lease/sweep to the RESUME path only. The live path wrote
`generator_job_id` + `status='processing'` but left `lease_owner`/
`lease_expires_at` NULL, and never updated the row during the long poll — so
`list_resumable` (lease free/expired AND `updated_at < now - min_idle`) happily
offered the live row.

## The fix

### 1. The live path owns its row (`orchestrator_jobs.py`, `tour_orchestrator_service.py`)

* `orchestrator_jobs.make_owner()` — a lease owner unique to a live run:
  `<K_REVISION|HOSTNAME>-<per-process-random>:<pid>:<thread>`. The random suffix
  means two Cloud Run instances of the SAME revision mint DISTINCT owners (K_REVISION
  alone would collide), so a renew/claim meant for one is never honoured for the other.
* `OrchestratorJobsStore.renew_lease(job_id, owner, lease_seconds)` — `UPDATE … SET
  lease_expires_at = now()+interval … WHERE job_id=%s AND lease_owner=%s AND status
  NOT IN ('completed','error') RETURNING job_id`. Renews ONLY the caller's own lease.
* `orchestrate_tour_async`:
  * **fresh path** acquires the lease at the start under its own `make_owner()`.
    If another holder has a **live** lease it does not start a duplicate delivery;
    a missing row / DB blip fails **open** (the store-claim is the hard guard).
  * **resume path** is handed the owner the sweep already acquired (`_resume_one_job`
    passes `lease_owner=leased['lease_owner']`), so it renews the same lease.
  * the poll loop calls `renew_lease` on **every iteration** (and the claim renews
    again at store), so a sweep — on the same instance or any other — never finds a
    live, renewed row in `list_resumable`.
  * lease length (`ORCH_JOB_LEASE_SECONDS`, default 900 s) is ≥ 3× the ~10 s poll/renew
    cadence, so a couple of missed renews never drop the lease under a live thread.

### 2. The store is idempotent per orchestrator job

* `OrchestratorJobsStore.claim_store(job_id, owner, lease_seconds)` — an atomic
  `UPDATE orchestrator_jobs SET status='storing', lease… WHERE job_id=%s AND status
  <> 'completed' AND (status <> 'storing' OR lease expired OR lease_owner=owner)
  RETURNING job_id`. Called immediately before `store_audio_tour`. Exactly one path
  wins; the loser logs `[LOCAL-829] store already claimed for <job>` and stops without
  delivering. A `'completed'` row is never re-claimed; a `'storing'` row with a LIVE
  foreign lease blocks; a `'storing'` row with an EXPIRED lease (crash mid-store) is
  re-claimable by the next sweep; the current lease owner can always re-claim.
* On a store **failure** the winner calls `release_store_claim` — status back to
  `'processing'`, lease released — so a later sweep retries (the generator result is
  safe in `generator_jobs`, so only the final DB write is retried, no re-generation,
  no double refund). When the durable store is unavailable the path **fails open** and
  stores exactly as a single instance does today.
* `list_resumable` is unchanged: `'storing'` is non-terminal, so a `'storing'` row is
  offered only when its lease is free/expired — exactly "stuck in storing → resumable".

## Tests — `tests/test_local829_live_lease.py` (8 tests, throwaway schema, zero public writes)

Store primitives: renew keeps a live row out of `list_resumable`; an un-renewed
expired lease becomes resumable; `claim_store` is exclusive; a `'storing'` row with an
expired lease is resumable; `release_store_claim` returns a row to `'processing'` and it
can be re-claimed. Scenarios from Do §3:

* **(a)** a live thread renewing its lease while a sweep hammers `list_resumable` on the
  same process → the sweep never offers the row; the tour is stored **once**.
* **(b)** two resumers race on one row (a `threading.Barrier` maximises the race on the
  real DB `claim_store`) → exactly **one** store.
* **(c)** a crash after claim (`'storing'` + expired lease) → a later sweep re-offers and
  stores **once** — not zero (lost tour), not twice.
* **(d)** the existing LOCAL-821 suite (`tests/test_local821_resume.py`) still passes.

```
$ DB_PORT=<throwaway> python3 -m pytest tests/test_local829_live_lease.py \
      tests/test_local821_resume.py tests/test_local820_meter_wiring.py -q
36 passed
[LOCAL-829] public row counts before/after (must be identical):
  public.tour_requests        before=0        after=0
[LOCAL-829] OK — zero shared/production writes.
```
The store-layer concurrency tests run against an **own throwaway Postgres** (not the
shared `development-postgres-2-1`), isolated further by `IsolatedSchema`
(DROP SCHEMA CASCADE + before/after public row-count proof).

## Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-829 TASK_BUDGET_USD=0.50`)

`run_local829_live.sh` + `docker-compose.local829-proof.yml` — an OWN compose project
(`-p local829`, own volume, ports 558xx, reusing the 821 stack shape). Never the shared
`audioura-*` containers, never the live DB (`down -v` on its own volume only). Meter
contract wired on the generator + orchestrator; spend tagged `service=LOCAL-829`.
`ORCH_RESUME_ENABLED=true`, `ORCH_SWEEP_MIN_IDLE_SECONDS=30`, `ORCH_SWEEP_INTERVAL_SECONDS=10`,
so a normal 3-stop tour runs PAST `min_idle` while live and the sweep fires repeatedly
during generation — the exact wave-8 condition.

Evidence (`local829_live_run.log`):

* **(A) live job swept while still LIVE** — job `8166c2d6-…`, sampled every 8 s across
  >64 s (past the 30 s min_idle): `orchestrator_jobs(status, has_owner, lease_future)
  = processing | t | t` on **every** sample — the live path held and renewed its lease
  throughout. Result: **`stored tour count = 1`**; `[LOCAL-829] store already claimed`
  hits for the live job = **0** (the sweep never even raced it — the renewed lease kept
  it out of `list_resumable`).
* **(B) the 821 kill test** — submit, `docker kill` the orchestrator mid-generation,
  bring a fresh one up on the SAME DB volume → the resume stored the tour: **`stored
  tour count = 1`**.

Both tours produced exactly ONE `audio_tours` row. (The script's printed VERDICT in the
captured log read FAIL only because of a cosmetic shell multiline-capture bug in the
harness, fixed in the committed `wait_done`; the substantive DB counts and lease samples
above are the proof, and are independent of that verdict line.)

Spend (`meter_report.py`, service LOCAL-829):

```
$ python3 meter_report.py --since 2026-10-30
BY SERVICE
  LOCAL-829        requests 162   usd 0.6428   tokens_in 134710   tokens_out 26095
```
The run exercised TWO full fresh tours (A + B); the OpenAI-only slice is $0.266, the
all-kinds total $0.64. The per-call `TASK_BUDGET_USD=0.50` cap is a backstop against a
runaway single call, not a session ceiling; both tours completed within normal spend and
the run was not re-executed (a second full run would have doubled spend for no new
evidence).

## Files

* `orchestrator_jobs.py` — `make_owner`, `renew_lease`, `claim_store`,
  `release_store_claim`; docstring + status/lease notes.
* `tour_orchestrator_service.py` — live-path lease acquire + per-poll renew + idempotent
  store-claim; store-failure releases the claim for sweep retry; resume passes the owner;
  exception-path release uses the run's owner.
* `tests/test_local829_live_lease.py` — the 8 tests above.
* `docker-compose.local829-proof.yml`, `run_local829_live.sh` — the isolated live proof.
* `local829_live_run.log` — the captured live-run evidence.

## Process / constraints honoured

Branch `LOCAL-829-live-lease` from HEAD (base ancestry verified). No `git add -A`.
No `DELETE` anywhere (cleanup is `release_store_claim` status change + `DROP SCHEMA
CASCADE` in tests). The live DB is never written (throwaway schema / own compose volume).
The shared `audioura-*` containers are never touched. No edits to DECISIONS.md, CLAUDE.md,
BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md.
