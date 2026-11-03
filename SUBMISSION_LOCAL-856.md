# SUBMISSION — LOCAL-856

**Share codes 404 on the cloud (`shared_tours` lacks `audio_tour_id`), and `is_test` from the request is lost.**

- **Base:** subscribed = `ad716811` (contains 24671e41). `git merge-base --is-ancestor ad716811 HEAD` → exit 0.
- **Branch:** `LOCAL-856-share-codes-cloud`

---

## Bug 1 — every `/tour-by-code` 404s on the cloud

### Root cause
The share READ path (`/tour-by-code`) lives in **`map_delivery/app.py`** (map-delivery, port 5005).
Its query selects `shared_tours.audio_tour_id`. The `ADD COLUMN` that creates that
column, however, lived **only** in the WRITE path — `tour_sharing._ensure_shared_tours_table`
(repo root), used by `sharing_endpoints.py`, which is mounted in
`generate_tour_text_service.py`.

`map_delivery/app.py` is built from the `map_delivery/` Docker context (`COPY . .`),
so it **cannot import** the repo-root `tour_sharing` module and never ran the ALTER.
On the cloud the write path was never exercised, so the column was never created, and
the read query raised `UndefinedColumn` on every call — caught by the endpoint's
`except` and returned as a clean `404 tour not found`. That is why **every** share code
404'd on Subscribed Preview while the Mac DB (where the write path had run) had the
column (ST-1).

### Fix (idempotent, additive, logged — no DROP / DELETE / backfill)
- **`map_delivery/app.py`** (the service that reads the column):
  - `_ensure_shared_tours_audio_tour_id(cur)` — `ALTER TABLE shared_tours ADD COLUMN IF NOT EXISTS audio_tour_id INTEGER`, cached per-process (same self-healing pattern as `_ensure_tour_reports_table` / `_ensure_unlock_consumption_columns`). Logs `[LOCAL-856] shared_tours.audio_tour_id ensured` once on success.
  - `_ensure_shared_tours_audio_tour_id_at_start()` — runs the ensure **at module import** (so it fires under `python app.py` and any WSGI import), best-effort / non-fatal.
  - A lazy call inside `get_tour_by_code` **before** the `SELECT` as a safety net.
- **`tour_sharing.py`** (the write path): the existing ensure now logs the `[LOCAL-856]` marker, and a new `ensure_shared_tours_schema(db_url)` runs it once at service start.
- **`generate_tour_text_service.py`**: calls `ensure_shared_tours_schema(...)` right after `register_blueprint(sharing_bp)`.

Both the read and the write services now ensure the column at start, so it exists
regardless of which path runs first. Additive and nullable: the 3 legacy rows keep
working through `tour_text` with `audio_tour_id` NULL.

---

## Bug 2 — `is_test` from the request is lost on the background / Cloud-Tasks path

### Root cause
`is_test` was carried correctly on the **in-memory THREAD path**
(`/generate` → `ACTIVE_JOBS` → `orchestrate_tour_async(is_test=…)` →
`store_audio_tour(is_test=…)`; the durable resume params in `orchestrator_jobs.PARAM_KEYS`
already include `is_test`). It was **silently dropped** the moment **Cloud Tasks** was
the transport:

- `tour_orchestrator_service._enqueue_cloud_task(...)` and `_create_job_in_db(...)` did not carry `is_test`.
- `tour_worker_service.store_audio_tour(...)` had **no `is_test` parameter at all** — it read only the `TOUR_TEST_MODE` env (unset in production → `false`), and `run_generation` / `run_job` never forwarded a request flag.

So Sophia's re-run, which sent `is_test: true` through the Background path, was stored
`is_test=false` (tour 525).

### Fix (preserves the LOCAL-103 trust boundary)
- **Orchestrator**: `_enqueue_cloud_task(..., is_test=None)` adds `{"is_test": true}` to the Cloud Tasks payload when truthy (omitted otherwise); `_create_job_in_db(..., is_test=None)` persists `is_test` in `job_status.output_data` when truthy; `/generate` passes the already-resolved `is_test_override` into both.
- **Worker**: `store_audio_tour(..., is_test=None)` now applies request-param precedence over the env (the same LOCAL-103 rule the orchestrator's store uses); `run_generation(..., is_test=None)` forwards it; `run_job` reads `data.get('is_test')` from the payload.

The orchestrator only puts `is_test` in the payload when it already resolved `True`
under the `/generate` trust boundary (`TOUR_TEST_MODE` / `TOUR_TEST_MODE_ALLOW_REQUEST`),
so a truthy value reaching the worker is already authorised — a malicious caller still
cannot mark tours test on a production deployment.

---

## Files changed
- `map_delivery/app.py` — read-path ensure (startup + lazy) + marker log.
- `tour_sharing.py` — marker log + `ensure_shared_tours_schema(db_url)`.
- `generate_tour_text_service.py` — write-service startup ensure.
- `tour_orchestrator_service.py` — carry `is_test` through `_enqueue_cloud_task` / `_create_job_in_db` and the `/generate` call sites.
- `tour_worker_service.py` — `is_test` through `run_job` → `run_generation` → `store_audio_tour` (request precedence over env).
- `tests/test_local856_is_test_preservation.py` — **new**, 19 assertions, all pass.

All modified Python files `py_compile` clean.

---

## Unit tests — `python3 tests/test_local856_is_test_preservation.py` → 19 passed, 0 failed
- THREAD path: `orchestrator_jobs.PARAM_KEYS` includes `is_test`.
- Cloud-Tasks: `_enqueue_cloud_task` payload carries `is_test` when `True`, omits when falsy.
- Cloud-Tasks: `_create_job_in_db` persists `is_test` in `output_data` when `True`, omits when falsy.
- Worker `store_audio_tour`: request flag wins over unset env; env fallback when request `None` (True and False).
- Worker `run_job`: reads `is_test` from payload and forwards to `run_generation`; `None` when absent.
- Share schema: `map_delivery/app.py` startup runs the additive ALTER (and never a DROP/DELETE on `shared_tours`); `tour_sharing.ensure_shared_tours_schema` is additive.

(psycopg2 and the Cloud Tasks client are mocked, so the tests assert on the exact SQL
params / payloads the code sends — no DB or network required.)

---

## Live run — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-856 TASK_BUDGET_USD=0.40`)

**Spend: $0.00** — `cost_ledger` empty; no tour generation / paid APIs ran. Well under the $0.40 cap.

**Isolation:** OWN resources only — `local856-pg` (`postgres:15-alpine`, port 55432),
`local856-map` (built from `map_delivery/`, port 55005), network `local856-net`. OWN DB
loaded from `tests/schema_audiotours.sql`, in which `shared_tours` has **NO**
`audio_tour_id` (reproduces the cloud). The shared `audioura-*` containers and
`development-postgres-2-1` were never touched; the isolated resources were torn down
after the run. (The `postgres:15-alpine` container was switched to `md5` auth because the
`python:3.9-slim` map-delivery image's libpq predates SCRAM — an env-only quirk of the
local harness; the cloud uses a compatible libpq.)

### Proofs
1. **Column appears at start (Bug 1).** map-delivery started against the column-less DB →
   logged `[LOCAL-856] shared_tours.audio_tour_id ensured` → `\d shared_tours` then shows
   `audio_tour_id | integer` present.
2. **Share → resolve → download end-to-end.** Seeded `audio_tours` id=1 (2-stop,
   `is_test=true`, real ZIP bytea). Real `sharing_endpoints` `POST /tour/share {audio_tour_id:1}`
   → `200 {share_id: MLRP9Ywk}`; `shared_tours` row has `audio_tour_id=1`.
   `GET /tour-by-code/MLRP9Ywk` → **200**, `tours[0].id=1`, `via_share_code=MLRP9Ywk`
   (the endpoint that 404'd every cloud code). `GET /download-tour/1` → **200**, valid ZIP
   (`tour.json` + `stop1.mp3` + `stop2.mp3`). (An empty `audio_tour_versions` table had to
   be created in the test DB — a pre-existing join not present in the schema file; additive
   to the isolated DB only.)
3. **`is_test` on the Background/worker path (Bug 2).** With `TOUR_TEST_MODE` **unset**
   (the production shape that stored tour 525 as `is_test=false`), the fixed
   `worker.store_audio_tour(..., is_test=True)` stored `audio_tours` id=2 with `is_test=t`.

### Row counts BEFORE → AFTER (isolated DB)
| table / metric            | before | after |
|---------------------------|:------:|:-----:|
| `audio_tours`             |   0    |   2   |
| `shared_tours`            |   0    |   1   |
| `is_test = true` rows     |   0    |   2   |
| shares with `audio_tour_id` ref | 0 |   1   |
| `cost_ledger` (paid spend)|   0    |   0   |

---

## Process / constraints honoured
- Branched from `HEAD` (`ad716811`), never from `origin/*`; ancestry verified.
- Committed to `LOCAL-856-share-codes-cloud`; **no `git add -A`** (files staged explicitly).
- No `DELETE`; no DROP; no backfill rewriting rows. Never wrote the live DB; never touched the shared `audioura-*` containers. No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE / `.continuous_dev/` / SUBSCRIBED_COMMUNICATION_01.MD / `legal/` / GCLOUD_STORIED_START_HERE.md / TRAVEL_PROJECTS.md.
