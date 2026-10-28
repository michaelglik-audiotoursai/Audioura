# SUBMISSION — LOCAL-775: Generator job status lives in memory → a second instance answers "Job not found" and the tour is lost

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-775-generator-job-store`
**Base:** `subscribed` @ `e75e698f840f18d1032230b42ee59ba136533ee4`
**Decision:** D718 (GCloud_Storied, 2026-10-26 ~19:48Z)

`git merge-base --is-ancestor e75e698f HEAD` → exit 0 (branched from the correct base).

---

## The defect (D718)

`tour-generator-subscribed` briefly ran 2 instances during a revision rollout
(Cloud Run can exceed `maxScale=1` for a moment). The orchestrator's status poll
landed on the instance that did **not** own the job and got
`{"error":"Job not found"}` 404 (`generate_tour_text_service.py` `get_job_status`).
The orchestrator treated that 404 as fatal and failed the job, while the owning
instance kept generating until 19:50:41 (~$0.35 metered) — and **no tour was
stored**. Job status lived only in the in-memory `ACTIVE_JOBS` dict, so it was
invisible to any other instance. Stable's `tour-generator-storied` has the same
design.

Two independent faults combined:
1. **Generator:** job status was in-memory only, so a second instance had no way
   to know the job existed.
2. **Orchestrator:** any non-200 from the generator `/status` (including a 404)
   raised immediately — no tolerance for a rollover gap.

---

## The fix (per the D718 ruling)

### 1. `generator_jobs` table — `migration/sql/058_generator_jobs.sql` (additive)
`job_id` PK, `status`, `progress`, `location`, `tour_type`, `total_stops`,
`result` JSONB, `error` JSONB, `instance_id`, `created_at`, `updated_at`, and
`idx_generator_jobs_created` for ageing out old rows (no cleanup job in this
task, as ruled).
- `result` JSONB holds everything the orchestrator needs to deliver from any
  instance: `output_file`, **`tour_content`** (the full tour text — the
  HTTP/Cloud-Run-safe path the orchestrator already prefers), `coordinates`,
  `tour_kind`, `i_con_avg`, `qa_style_warning`.
- `error` JSONB holds the structured refusal (LOCAL-580/597/774): `error`,
  `error_code`, `error_type`, `message`, `suggestion`, `nearby_tours`,
  `evidence_summary`, `coordinate_path`.
- Purely additive: `CREATE TABLE/INDEX IF NOT EXISTS` + guarded `ALTER ADD
  COLUMN`. **No `DROP`, no `DELETE`.** Verified it applies clean, is idempotent
  (applied twice = no-op), and builds the table from scratch in a fresh DB.
- A note on the pre-existing `job_status` table (migrations 002/010): that was
  the old all-or-nothing `JOB_STORE_MODE='database'` design (write memory **or**
  DB, never both; no `instance_id`). D718 asks for a cache-with-source-of-truth
  layering and an owning-instance column, so 058 adds a purpose-built table
  rather than overloading `job_status`. `job_status` is left untouched.

### 2. `LayeredJobStore` — `job_store.py`
The in-memory dict stays **only as a cache** in front of the table:
- **Write-through:** every `create`/`update`/`setitem` writes the in-memory
  cache **and** upserts `generator_jobs` (cheap, at exactly the points the
  generator updates the dict today). The `result`/`error` JSONB are MERGED
  (`jsonb ||`) so a later partial update (a progress tick) never wipes earlier
  keys.
- **Read:** memory first, then the table. A **terminal** (`completed`/`error`)
  cache entry is immutable and returned directly; a **non-terminal** cache entry
  re-consults the table and prefers it when it has advanced. This last point
  matters — see "A bug the live test caught" below.
- The DB layer is **best-effort**: a DB error is logged and swallowed, so a
  transient database problem degrades to the old in-memory behaviour and never
  breaks generation.
- `instance_id` records the owning container (explicit `INSTANCE_ID` env →
  `K_REVISION` → `HOSTNAME`), for diagnosing the exact 2-instance overlap.
- Self-healing DDL (`_ensure_table`) identical in shape to migration 058, so the
  store converges whether or not the migration was applied.

The generator (`generate_tour_text_service.py`) now defaults to the layered
store (`JOB_STORE_MODE` env still overrides), and its `/status` and `/download`
endpoints read through `ACTIVE_JOBS.get(job_id)` — a single memory-first-then-
table lookup. **A job the table knows is never "Job not found".**

### 3. Result retrievable from any instance (ruling point 3)
The completed-job write already stores `tour_content` (the full tour text) in the
job dict, and the orchestrator already delivers from `status_data["tour_content"]`
(HTTP-based, Cloud-Run-safe) rather than a local disk file. Storing `tour_content`
in `generator_jobs.result` is therefore sufficient: the finished tour is readable
from the instance that did not generate it. (`output_file` is still carried for
the legacy volume path.) No new orchestrator plumbing was needed.

### 4. Orchestrator tolerates a 404 for 60 s — `tour_orchestrator_service.py`
In the text-generation poll loop, a `404` is no longer fatal on sight: it is
tolerated for up to **60 s** (retry every 5 s) before failing, which covers a
rollover gap. A good `200` clears the window. Any other non-200 (e.g. 500) still
fails fast, and the existing timeout/connection-error resilience (30 consecutive
failures) is unchanged.

---

## Tests — red first

`tests/test_local775_generator_job_store.py` (8 tests). Two `LayeredJobStore`
objects = two generator instances with separate in-memory caches sharing ONE DB.

Store/Flask (need a DB; skip cleanly when none is configured):
- `test_job_started_on_A_is_visible_on_B_not_job_not_found` — the 404 that lost
  the tour: B reads A's job from the table.
- `test_A_finishes_and_B_returns_the_result` — B returns `tour_content` after A
  completes.
- `test_structured_refusal_survives_across_instances` — error_code/message/
  suggestion/nearby_tours survive to B.
- `test_partial_updates_merge_not_clobber` — a progress tick doesn't wipe an
  earlier result key.
- `test_cached_in_progress_does_not_mask_completion_on_another_instance` — the
  staleness case the live test caught (below).
- `test_generator_status_endpoint_answers_from_other_instance` — the generator's
  HTTP `/status` answers on the non-owning instance (the exact request that 404'd).

Orchestrator (drive the real `orchestrate_tour_async` poll loop):
- `test_orchestrator_tolerates_transient_404_then_succeeds` — a 404 then a 200
  survives (4 polls).
- `test_orchestrator_fails_after_404_grace_exhausted` — a persistent 404 beyond
  60 s fails with "Job not found".

**Red on base / green on branch — proven:**
- Store/Flask tests on the base tree: `AttributeError: module 'job_store' has no
  attribute 'LayeredJobStore'` → 5 FAILED. On branch: all pass.
- Orchestrator tests on the base orchestrator: it raises
  `Error checking text generation status: {'error': 'Job not found'}` on the
  FIRST 404 — the D718 bug reproduced — → 2 FAILED. On branch: both pass.

**No regressions** (branch, with a throwaway DB):
`test_local775_generator_job_store` (8), `test_poll_resilience_production` (4),
`test_local774_refusal_status_forwarding` (4),
`test_local774_worker_background_refusal`, `test_local717_job_status_version`,
`test_local64_cost_ceiling`, `test_orchestrator_storied_wiring`
→ **30 passed**. Without a DB the 6 DB-dependent tests skip cleanly (skipif guard).

### A bug the live test caught (and the fix)
The kill-owner live run exposed a cache-staleness fault: once instance B had
polled a job while it was `processing`, B cached `processing` in its own memory;
after A finished and wrote the tour, B kept serving its stale `processing` — the
tour would be lost one step later. Fixed: `LayeredJobStore.get` re-consults the
table for NON-terminal cached entries (terminal states are immutable and served
from cache). Pinned by
`test_cached_in_progress_does_not_mask_completion_on_another_instance`.

---

## Live test — own stack only (`-p local775`), **zero live-DB writes**

`docker-compose.local775-proof.yml` + `local775-gen-lb.conf`: a throwaway
Postgres (host port 55775), two generator instances (`generator-a` 55701,
`generator-b` 55702) sharing that DB, and an nginx `gen-lb` (55700) round-robin
so a poll can land on either instance. Brought up with `-p local775` on spare
ports. **`audioura-*` and `development-*` were never touched** (verified still
up with their original uptimes); the stack was torn down with `down -v`.

1. **Crossing proof.** `generator-a` created a job (its `LayeredJobStore`);
   `generator-b`'s HTTP `/status` returned the real `processing` — **not**
   "Job not found". A genuinely unknown job still correctly 404s.
2. **Kill-owner proof.** A `processing` → B polls and caches `processing` → A
   completes storing `tour_content` + `output_file` → **`docker kill generator-a`**
   → B's `/status` returns `completed` with the full `tour_content` and
   `output_file`, served from `generator_jobs` after the owner is dead.
3. **One real 1-stop tour, end to end.** DeCordova Sculpture Park, Lincoln MA,
   `STORIED_MODE=true`, Gemini research. Generated on `generator-a` and polled
   **live from `generator-b` (the non-owner)** throughout `processing →
   completed`. Result on B: `tour_content` 2231 chars, `coordinates`
   `[42.4264, -71.2901]`, `output_file` set.
   **Cost: `tour_generate` $0.295118 + `spine_generate` $0.005558 = $0.3007
   ≤ $0.40 budget.**

**Row counts for live-DB tables written: none.** Every `generator_jobs` and
`cost_ledger` row (30 total in `generator_jobs`, 10 completed) lived in the
throwaway `-p local775` DB and was dropped with `down -v`. I also created and
dropped a throwaway `ls775_fresh` database to prove migration 058 builds from
scratch — never a live table.

---

## `storied`? — subscribed only (as ruled)

Not applied to `storied` in this task; Stable gets it at the next Stable
promotion. Cherry-pick cleanliness of this commit onto local `storied`
(`cece3763`):

- **`migration/sql/058_generator_jobs.sql`** — new file, applies cleanly.
- **`job_store.py`** — **identical** between the subscribed base and `storied`
  (`git diff` = no change), so the entire `LayeredJobStore` addition applies
  cleanly.
- **`generate_tour_text_service.py`** and **`tour_orchestrator_service.py`** —
  the anchor code exists in `storied` with the same structure (same
  `get_job_store('tour-generator')`, same `/status` "Job not found" 404, same
  `status_response.status_code == 200` / "Error checking text generation status"
  poll loop), **but** the surrounding lines differ (storied's generator `/status`
  body predates the LOCAL-622/heartbeat additions my edit preserves, and the
  `ACTIVE_JOBS =` line differs — storied has no `mode=` kwarg). A literal
  `git cherry-pick` would therefore **conflict in these two files** and need a
  small manual re-apply; the change is conceptually identical and the job-store
  module (the substance) ports verbatim.

---

## Process / safety
- Committed to `LOCAL-775-generator-job-store`; files staged explicitly (no
  `git add -A`).
- No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- No `DELETE`/`DROP` of any kind. Migration is additive and idempotent.
- Heavy builds run one at a time.

## Files
- `migration/sql/058_generator_jobs.sql` (new)
- `job_store.py`
- `generate_tour_text_service.py`
- `tour_orchestrator_service.py`
- `tests/test_local775_generator_job_store.py` (new)
- `docker-compose.local775-proof.yml` (new, proof infra)
- `local775-gen-lb.conf` (new, proof infra)
