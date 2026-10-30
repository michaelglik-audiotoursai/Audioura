# SUBMISSION — LOCAL-839: the modernized (voice/ZIP) service is safe with more than one Cloud Run instance

**Base:** subscribed (`ce18fca3`)
**Branch:** `LOCAL-839-modernized-multi-instance`

## The defect

Evidence (GCloud_Storied, 2026-10-30, wave 14): the orchestrator created modernized
job `d7d98f2f`, then its `/status` poll landed on a **different** modernized instance
14 s later and got `"Job not found"`, so request 306 failed. The cloud modernized image
(`3c0cfae6`) had a job_store with only `memory`/`database`, and even with a shared job
store the orchestrator next does `GET /download/<id>` (tour_orchestrator_service.py
~2313) which the modernized service served from its **local** `TOURS_DIR` — so the 404
just moves to the download. The cloud stop-gap was `max-instances=1` on
`modernized-subscribed`, which caps voice throughput at one instance.

Two things are per-instance and broke the hop:
1. **job status** lived only in the in-memory dict;
2. the **ZIP** lived only on the owning instance's disk.

## The fix

### 1. Modernized uses the LAYERED job store (same table as LOCAL-775)

`tour_generation_modernized.py` now builds its store with the mode from the environment:

```python
JOB_STORE_MODE = os.getenv('JOB_STORE_MODE', 'memory')
ACTIVE_JOBS = get_job_store('tour-generation-modernized', mode=JOB_STORE_MODE)
```

Set `JOB_STORE_MODE=layered` (and the `DB_*` env) on the deployment and every instance
reads job status from the shared `generator_jobs` table (LOCAL-775 / migration 058),
keyed by `service_name='tour-generation-modernized'`. Default `memory` keeps the exact
single-instance behaviour for local Docker, so nothing changes for anyone who does not
opt in.

### 2. Instance-surviving ZIP handoff — option (b): modernized writes the ZIP to the shared store, `/download` reads it there

The task offered (a) hand the ZIP bytes back to the orchestrator in the completion
response / a new DB row, or (b) modernized writes the ZIP to the shared store and
`/download` reads it from there — "pick the simpler one that adds no new
infrastructure."

**Chosen: (b).** It reuses the `generator_jobs.result` JSONB the layered store already
round-trips across instances (LOCAL-775). No new table, no new column, no change to the
orchestrator's download contract. (a) would have meant either a new bytea row/table or
streaming multi-MB ZIP bytes through the status/completion JSON — more moving parts for
no benefit, since the shared row already crosses instances.

On completion the modernized service stores the ZIP base64 under `result.zip_b64`
(`_store_zip_in_job_store`, best-effort, size-capped at 64 MB, logged). `/download` now:

1. serves the local `TOURS_DIR` file when present (the owning instance — no copy, no
   decode); else
2. rebuilds the ZIP from `result.zip_b64` and serves it from memory (any other
   instance). `/status` strips `zip_b64` so a poll response never carries megabytes.

### 3. `psycopg2-binary` added to `requirements-modernized.txt`

The modernized image had no Postgres driver, so the layered store could not reach the DB.
Added `psycopg2-binary==2.9.9` (same pin as the generator/orchestrator). The two proof
composes set `JOB_STORE_MODE=layered` + `DB_*` on both modernized instances.

### 4. Orchestrator cleans the stale ZIP row after a successful store

After the tour is in `audio_tours`, the inline ZIP in the modernized row is dead weight.
`_cleanup_modernized_zip_row(modernized_job_id)` (tour_orchestrator_service.py, called
right after store success, ~line 2771) runs:

```sql
UPDATE generator_jobs SET result = result - 'zip_b64', updated_at = CURRENT_TIMESTAMP
WHERE job_id = %s AND result ? 'zip_b64'
```

A JSONB **key delete** — never a row/data `DELETE`, never touches `audio_tours`. The job
row, its status and every other result field stay intact. Best-effort: a DB error is
logged and swallowed and never affects an already-delivered tour.

## Tests

`test_local839_modernized_multi_instance.py` (5/5 pass) — two `LayeredJobStore`-backed
instances sharing one fake `generator_jobs` table, each with its **own** memory cache and
**own** `TOURS_DIR`:

- `test_status_served_by_other_instance` — job created on A, `/status` served by B (200,
  `completed`, `zip_b64` stripped).
- `test_download_served_by_other_instance` — B (no file on disk) serves the ZIP from the
  shared store; bytes are byte-identical to A's ZIP and it is a valid ZIP with `audio_1.mp3`.
- `test_owning_instance_still_serves_local_file` — A serves straight from disk.
- `test_memory_store_does_NOT_survive_the_hop` — control: with the old `MemoryJobStore`,
  B genuinely 404s on both `/status` and `/download` (the bug the layered store fixes).
- `test_jsonb_key_delete_semantics` — the cleanup removes only `zip_b64`, leaving tour
  data intact.

```
$ python3 -m pytest test_local839_modernized_multi_instance.py -q
5 passed in 0.28s
```

## Live — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-839 TASK_BUDGET_USD=0.40`)

Two isolated compose projects (own Postgres volume, spare ports, never the shared
`audioura-*` containers or the live DB). Both are **budget-safe**: TTS is the local
kokoro server (≈$0 paid) and the only paid generation path is replaced in the e2e run by
a zero-cost fake generator. Net paid spend of the two proof runs: **$0.0000**.

### Proof 1 — the cross-instance hop (`run_local839_direct.sh`, `docker-compose.local839-proof.yml`)

TWO real modernized instances (separate tours dirs, shared Postgres,
`JOB_STORE_MODE=layered`) behind an nginx round-robin. `/process`, `/status`, `/download`
driven through the round-robin. Result (`LOCAL839_DIRECT_RUN.log`):

- the job's ZIP physically landed on **instance A only** (A tours dir = 1 file, B = 0);
- download #5 was served by **instance B** (`served-from-store=1` in B's log) — a ZIP B
  never wrote, rebuilt from the shared layered store;
- the downloaded ZIP has **3 real MP3 files** (ID3/MPEG headers, 75 549 / 66 765 / 61 293
  bytes) — audio plays;
- `generator_jobs.status=completed`, `has_zip_b64=t`, `owning_instance=modernized-A`.
- **VERDICT: PASS.**

### Proof 2 — stored once, through the real orchestrator (`run_local839_e2e.sh`, `docker-compose.local839-e2e.yml`)

REAL orchestrator → zero-cost fake generator (canned 3-stop walking tour) → TWO
modernized instances (round-robin) → store. Result (`LOCAL839_E2E_RUN.log`):

- orchestrator job **completed**;
- tour **stored EXACTLY ONCE** (`audio_tours` rows=1, `stops_count=3`, zip_bytes≈179 k);
- the stored ZIP (DB bytes **and** the on-disk copy) holds **3 real MP3 files** (ID3/MPEG
  headers) — audio plays;
- orchestrator logged **`Cleared stale inline ZIP` ×1** and `generator_jobs` rows carrying
  `zip_b64` = **0** afterwards — the cleanup works end-to-end.
- **VERDICT: PASS.**

### Budget note

Total metered `service=LOCAL-839` spend today is **$0.4234**, entirely from an **earlier
full-paid generator run that errored during generation** (a generator/budget-config
artifact, unrelated to this fix — no modernized ZIP ever ran). That budget-busting
harness was removed; the authoritative, in-budget proofs above added **$0.0000** paid
spend and cleaned up all their containers and volumes (`down -v`).

## Files

- `tour_generation_modernized.py` — layered store via `JOB_STORE_MODE`; `_store_zip_in_job_store`; `/download` store fallback; `/status` strips `zip_b64`.
- `tour_orchestrator_service.py` — `_cleanup_modernized_zip_row` + its call after store success.
- `requirements-modernized.txt` — `psycopg2-binary==2.9.9`.
- `test_local839_modernized_multi_instance.py` — the two-instance tests (5/5).
- `docker-compose.local839-proof.yml`, `run_local839_direct.sh`, `local839-modernized-lb.conf` — cross-instance hop proof.
- `docker-compose.local839-e2e.yml`, `run_local839_e2e.sh`, `fake_generator_local839.py`, `Dockerfile.fake-generator-local839` — stored-once end-to-end proof.
- `LOCAL839_DIRECT_RUN.log`, `LOCAL839_E2E_RUN.log` — captured run output.
