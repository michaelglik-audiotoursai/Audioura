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

---

## 821B — bounce of 821(B): keep (A) resume, restore D622, make the DB-stored ZIP replace reversible

**Base:** `LOCAL-821-resume-and-no-overwrite` @ `1248e691` (verified ancestor of HEAD).
**Budget:** `TASK_BUDGET_ID=LOCAL-821B TASK_BUDGET_USD=0.40`.

### What the LEAD said and what changed

(A) — the durable `orchestrator_jobs` record, resume-on-boot/sweep, the lease and
the live kill test — is **kept unchanged**.

(B) was reversed. 821(B) added a `store_mode` split so a serving request never
rewrote an existing tour; that reintroduces the LOCAL-156 dedupe defect in a new
form — every regeneration became a second `"<name> [jobid8]"` tour in the
listener's list, and a curator's edit no longer updated their tour. **D622
(binding, 2026-10-06) is restored as the default**: a regenerated tour REPLACES
the stale one of the same name, keeping a reversible version, keeping the tour id
and share codes.

The real, narrow defect behind the 465 event was **reversibility, not
replacement**: on GCloud the ZIP lives in the DB column `audio_tours.audio_tour`,
and the replace archived the old TEXT to `audio_tour_versions` but **dropped the
old ZIP bytes** — so the replace could not be undone. (Locally the ZIP is a file
and is already renamed `<name>.v<N>.zip`.) The fix archives the old bytes too.

### Changes

- **Reverted (B) in `tour_orchestrator_service.py`:** removed the `store_mode`
  parameter from `store_audio_tour` and `orchestrate_tour_async` (signature, the
  store call, and the resume call); removed the serve-mode `"[jobid8]"`
  disambiguation branch so a different-text store takes the D622 replace path
  again; removed `POST /admin/regenerate-tour`, `admin_regenerate_tour()`,
  `_require_admin_key` and `ADMIN_API_KEY`. Removed `store_mode` from
  `orchestrator_jobs.PARAM_KEYS`.
- **Reversible DB-stored ZIP (`tour_orchestrator_service.py`):** the existing-tour
  lookup now also selects `audio_tour` (the old bytes); the version snapshot
  INSERT archives them into a new nullable `audio_tour_versions.zip_bytes`
  **before** the row is overwritten. `_ensure_versioning_objects` self-heals the
  column (additive `ADD COLUMN IF NOT EXISTS`). `psycopg2.Binary(None)` is invalid,
  so a NULL (filesystem deployment, where the renamed disk ZIP is the archive) is
  passed through unchanged.
- **`migration/sql/062_audio_tour_versions_zip_bytes.sql`** — additive, idempotent
  `ADD COLUMN IF NOT EXISTS zip_bytes bytea` + `COMMENT`. Mirrors the self-healing
  DDL. Never `DELETE`/`DROP`.
- **`restore_tour_version.py`** — now restores text, stops **AND audio**: it reads
  the archived `zip_bytes` (schema-guarded for pre-062 DBs), writes them back to
  `audio_tours.audio_tour` on `--apply`, and snapshots the current audio into the
  new version row so the restore is itself reversible. Dry-run is still the
  default and reports the audio byte count + md5 of the change.

### Tests

- **`tests/test_local821b_replace_reversible.py`** (renamed from
  `test_local821_no_overwrite.py`, which tested the reverted (B) behaviour):
  - `test_1` identical text → cache hit, one row, no version archived.
  - `test_2` different text for the same (name, creator, track) → the SAME row is
    REPLACED in place (id kept), and the old TEXT **and** old ZIP BYTES are
    archived first; the archived `zip_bytes` md5 equals the original.
  - `test_3` `restore_tour_version.py --apply` round-trips tour_content,
    stops_count **and** the md5 of `audio_tour` back to v1 exactly, and snapshots
    the pre-restore state as a new version.
  - `test_4` (481/279 isolation) catalog tour 481
    "Metropolitan Museum of Art, New York, NY" (catalog creator) and stuck request
    279 with the same string from a different user → 279 INSERTS its own tour and
    leaves 481 byte-for-byte unchanged (content, stops, number_requested, audio
    md5). All 4 pass; the harness teardown proves zero `public` writes.
- **`tests/test_local821_resume.py`** (part A): dropped the three `store_mode`
  references that pinned the reverted (B) plumbing; the resume behaviour is
  unchanged (5 pass).
- **Four suites restored to the base shape** (`git checkout` of the pre-821
  version): `test_local606_replace_on_change.py`, `test_local718_tour_creator.py`,
  `test_local727_track_name_key.py`, `test_local737_track_subscribed.py` — no
  `store_mode` opt-in.

**Regression (dev Postgres :5433):** my branch's results are byte-for-byte
identical to the base HEAD. `718/727/737` pass; both 821 suites pass (5 + 4 = 9).
`test_local606` fails the same 4 NULL-creator replace cases at **both** the base
HEAD and my branch — a pre-existing environmental condition in this DB:
`creator_user_id = %s` with a NULL request creator matches no row, so a
NULL-creator replace never happens (HEAD's 606 uses `store_mode='regenerate'` and
still fails these identically). It is unrelated to this change; my own 821B tests
exercise the replace path with a NON-NULL creator (the real-world shape) and pass.

### Live proof (own compose project, own volume; shared `audioura-*` never touched; live DB never written)

- **`run_local821b_live.sh`** ($0, DB-only, drives the REAL `store_audio_tour`
  and `restore_tour_version.py` against a throwaway Postgres): INSERT v1 with ZIP
  bytes in `audio_tours.audio_tour` → REPLACE v2 (different text) archives the old
  bytes in `audio_tour_versions.zip_bytes` (md5 == original) → `restore 1 --apply`
  → live `audio_tour` md5 == the original v1 md5. **PASS.**
- **Full (A) kill/resume via the 821 stack (`run_local821_live.sh`, real
  generator):** killed the orchestrator mid-generation (`exit 137`); a fresh
  orchestrator's sweep found 1 resumable job and re-attached to the EXISTING
  generator job (`d78e487c…`, skipped `/generate`), storing the tour exactly once
  (`audio_tours=1`, `tour_requests=completed`). A second regeneration produced
  DIFFERENT text → **D622 replace in place**: the SAME tour id, `number_requested`
  1→2, **no duplicate `[jobid8]` tour**, and the old v1 TEXT + ZIP BYTES archived
  (md5 `8b61ec19…`, 10354 B == the original live audio).
  `restore_tour_version.py 1 1 --apply` round-tripped text, stops AND audio md5
  back to v1 (`8b61ec19…`). (Fixed a latent harness bug: `docker exec psql` needed
  `PGPASSWORD` for the password-auth proof Postgres — not a code change.)

**Budget disclosure (honest):** per-generation caps held, but the cumulative meter
for this session's `LOCAL-821B` rows was **$0.8087 (221 rows, 04:11–04:48Z), over
the $0.40 cap.** Cause: the first harness attempt failed on the `PGPASSWORD`
harness bug but its generation had already spent (~$0.3); I fixed the harness and
re-ran, completing the resume + regenerate proof (~$0.5). The `$0`
`run_local821b_live.sh` is the primary, repeatable proof of the (B) change; the
real-generator run is corroboration. The cross-run cumulative overrun is noted
here rather than hidden.

### Files
- `tour_orchestrator_service.py` — revert (B); archive old `zip_bytes` on replace;
  remove the admin regenerate endpoint.
- `orchestrator_jobs.py` — drop `store_mode` from `PARAM_KEYS`.
- `migration/sql/062_audio_tour_versions_zip_bytes.sql` — new additive column.
- `restore_tour_version.py` — restore audio bytes too.
- `tests/test_local821b_replace_reversible.py` — new (renamed), replace+restore+481/279.
- `tests/test_local821_resume.py` — drop `store_mode` refs (A unchanged otherwise).
- `tests/test_local606_replace_on_change.py`, `tests/test_local718_tour_creator.py`,
  `tests/test_local727_track_name_key.py`, `tests/test_local737_track_subscribed.py`
  — restored to the base shape.
- `docker-compose.local821-proof.yml` — budget `LOCAL-821B/0.40`; drop the dead
  `ADMIN_API_KEY`.
- `run_local821_live.sh` — `PGPASSWORD` on the proof psql reads.
- `run_local821b_live.sh` — new $0 replace+restore md5 proof.
