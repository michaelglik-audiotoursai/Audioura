# SUBMISSION — LOCAL-846: stale `source='tracking'` tour_requests rows never finalised

**Branch:** `LOCAL-846-stale-request-rows`
**Base:** subscribed = `4afdfa3c` (`git merge-base --is-ancestor 4afdfa3c HEAD` → exit 0)

## Problem

On the cloud, 27 `tour_requests` rows were `'started'` and > 1 h old; one
(request 300, USER-41659366, the 09:02:07Z double tap) sat `'started'` for 6 h
until set `failed` by hand. All were `source='tracking'` — the app's tracking
rows, not orchestrator generations. Nothing reserved quota, but stale `'started'`
rows make the app/reports show phantom in-progress tours and can block a
"one generation at a time" check.

## Root cause

The orchestrator writes **two** `tour_requests` rows per generation:

| row | `source` | `tour_id` | finalised by |
|-----|----------|-----------|--------------|
| orchestrator's own | `orchestrator` | `job_id` (full UUID) | `_set_tour_request_status(job_id, …)` on completion/failure |
| app tracking row | `tracking` | `tour_` + `job_id[:8]` | **only** an app `tour_status_update` PUT |

The tracking row is created by the orchestrator itself — `track_user_tour()` is
called with `tour_id = f"tour_{job_id[:8]}"`, which PUTs to the user-tracking
service, which inserts a `source='tracking'` row at `'started'`
(`user-tracking/app.py`, `/user/<secret_id>` PUT).

`_set_tour_request_status` only ever updated `source='orchestrator'` rows. The
tracking row was closed **only** if the app later sent a `tour_status_update` —
which frequently never happens (app killed, double tap, network drop). So the
tracking row stayed `'started'` forever. The two rows were never linked, so the
orchestrator reaching a terminal state did nothing for the app's row.

The linkage that was missing but recoverable: `tracking.tour_id` is exactly
`'tour_' + LEFT(orchestrator.tour_id, 8)`.

## Fix

All changes are in `tour_orchestrator_service.py`. No DELETE anywhere; every
write is idempotent and guarded on the row still being non-terminal.

1. **Link + mirror at finalise time** — `_set_tour_request_status(job_id, status)`
   now, in the **same transaction** that flips its own row, mirrors the terminal
   status onto the linked tracking row
   (`tour_id = 'tour_'+job_id[:8]`, `source='tracking'`), but **only** when that
   row is still non-terminal. An app that already reported `completed`/`failed`
   is never overwritten. Helper `_tracking_tour_id_for(job_id)` centralises the
   one linkage key so the writer, the mirror and the sweep agree.

2. **Sweep rule on the LOCAL-833/821 orchestrator sweep** —
   `_sweep_stale_tracking_rows()` runs on the same cadence as the existing
   resume/sweep loop (resume-on-boot + each periodic pass). Three idempotent,
   DELETE-free SQL rules:
   - **MIRROR** — a non-terminal tracking row whose linked orchestrator row is
     already terminal inherits that status (covers rows written before the
     finalise-time mirror existed, or a mirror UPDATE that lost its connection).
   - **DUPLICATE** (the 830 double tap) — when several non-terminal tracking rows
     share one `(secret_id, tour_id)`, the newest is kept `'started'` and the
     older copies → `'failed'`, reason `[LOCAL-846: duplicate tracking row]`
     appended to the existing `request_string` (original text preserved).
   - **ORPHAN** — a tracking row `'started'` longer than
     `ORCH_TRACKING_STALE_SECONDS` (default **2 h**) with **no** terminal linked
     orchestrator row → `'failed'`, reason `[LOCAL-846: stale tracking row]`.
   A second pass changes nothing (every UPDATE is guarded on the row still being
   non-terminal). `source='orchestrator'` rows are never touched — those are the
   LOCAL-833 sweep's job.

3. **`stale_requests_report.py`** — read-only (SELECT only; no
   INSERT/UPDATE/DELETE/DDL) so it is safe on the live cloud DB. Counts by
   `(source, status)`, an age histogram of non-terminal rows, and the exact
   ticket population (`source='tracking'`, `status='started'`, age > 1 h / > 2 h).
   Resolves the connection from standard env vars; `--json` for machine output.

## Tests — `tests/test_local846_stale_tracking_rows.py` (9 tests, all pass)

Run against a throwaway Postgres schema via `IsolatedSchema` (`tests/_isolated_db.py`),
which asserts `public.tour_requests` row counts are identical before/after — a
hard proof that **zero** production rows are written.

- mirror `completed` / `failed` at finalise;
- mirror never overwrites an app-closed tracking row;
- sweep mirrors a terminal orchestrator row onto its tracking row;
- orphan `'started'` > 2 h → `failed` with `'stale tracking row'`;
- orphan < 2 h left `'started'`;
- duplicate older row → `failed` with `'duplicate tracking row'`, newest kept;
- sweep idempotent (second pass all-zero);
- `source='orchestrator'` rows untouched by the sweep.

```
9 passed in 0.45s
[LOCAL-846] public.tour_requests  before=62  after=62
[LOCAL-846] OK — zero shared/production writes.
```

Related suites unchanged: `test_local833/821/829` = **41/41 pass**. The only
failures in the broader quota/tracking suites (`test_user_tracking_fix`
ConnectionError; `test_local778` venue-resolver network; entitlements-gate
`device_entitlement does not exist` fixture errors; `billing_dry_run` psycopg2)
were confirmed **pre-existing on `4afdfa3c`** via `git stash` — each needs a
running HTTP service or a table absent from its isolated schema, and none touch
`tour_requests` finalisation.

## Live proof — budget enforced, `$0.00` of `$0.20`

`TASK_BUDGET_ID=LOCAL-846 TASK_BUDGET_USD=0.20`. Own compose project `local846`
(`docker-compose.local846-proof.yml`): `postgres:15-alpine` only, spare port
`55846`, own volume, seeded from the real schema (`local821-initdb`). NEVER the
live DB, NEVER a shared `audioura-*` container. LOCAL-846 is a DB-finalisation
fix, so no LLM call is made.

`run_local846_live.py` points the production psycopg2 connections at the isolated
DB and drives the **real** functions:

- **ARM 1 (short tour, happy path):** seed the orchestrator row + the app
  tracking row exactly as production does, call
  `_set_tour_request_status(job_id, 'completed')` → both rows `completed`,
  tracking `finished_at` set.
- **ARM 2 (simulated duplicate + orphan):** a second tracking row for the same
  `(secret_id, tour_id)` (the double tap), an orphan `'started'` > 2 h, and a
  fresh `'started'` 30-min row; call `_sweep_stale_tracking_rows()` → older
  duplicate `failed` (`duplicate tracking row`), newest kept `'started'`, orphan
  `failed` (`stale tracking row`), fresh left `'started'`.
- **ARM 3 (idempotency):** second sweep is a no-op.

```
OVERALL: PASS   (LLM spend $0.00 / cap $0.20)
  [PASS] ARM1 orchestrator completed
  [PASS] ARM1 tracking MIRRORED to completed
  [PASS] ARM1 tracking finished_at set
  [PASS] ARM2 duplicate older → failed
  [PASS] ARM2 duplicate reason recorded
  [PASS] ARM2 duplicate newer kept non-terminal
  [PASS] ARM2 orphan → failed
  [PASS] ARM2 orphan reason recorded
  [PASS] ARM2 fresh (<2h) left 'started'
  [PASS] ARM3 second sweep is a no-op
  [PASS] no phantom in-progress rows among finalised/swept rows
```

Shared `audioura-*` and `development-postgres-2-1` containers verified running
and untouched; the isolated project was torn down with `down -v`.

## How LEAD verifies on the cloud

```bash
DB_HOST=<cloud> DB_PORT=5432 DB_NAME=audiotours DB_USER=<u> DB_PASSWORD=<p> \
    python3 stale_requests_report.py
```

Watch `source='tracking'` / `status='started'` / age > 2 h fall to 0 as the
orchestrator sweep runs. New generations close their tracking row at finalise
time, so the backlog does not re-grow.

## Files

- `tour_orchestrator_service.py` — mirror at finalise + `_sweep_stale_tracking_rows` + wiring (modified)
- `stale_requests_report.py` — read-only report (new)
- `tests/test_local846_stale_tracking_rows.py` — tests (new)
- `docker-compose.local846-proof.yml` — isolated DB for the live proof (new)
- `run_local846_live.py` — budget-enforced live proof driver (new)

## Constraints honoured

No DELETE. Never wrote the live DB. Never touched the shared `audioura-*`
containers. Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md.
