# SUBMISSION — LOCAL-827: the whole-task budget now accumulates across isolated run containers

**Branch:** `LOCAL-827-container-budget`
**Base:** subscribed — `50893631` (verified: `git merge-base --is-ancestor 50893631 HEAD` → exit 0)

## Problem

The whole-task paid-API cap (LOCAL-817) could not see spend made **inside** isolated
task containers, so a task ran past its budget every time:

- **Evidence:** LOCAL-821B spent **$0.81 against a $0.40 cap** (meter rows
  `service=LOCAL-821B`, 04:11–04:48Z). LOCAL-823/824 ran `task_budget_report.py`
  → *"No ledger … No runs recorded yet."*
- **Root cause:** `LiveRunMeter` writes the per-task ledger to
  `~/.audioura_task_budgets/<id>.json` **inside** the `docker run --rm` container.
  That directory was never bind-mounted, so `--rm` destroyed the ledger — every
  run started from **$0** and the whole-task cap never accumulated across runs.
  LOCAL-818 mounted it by hand (`AUDIOURA_TASK_BUDGET_DIR`); the shared contract
  (`meter_container_env.docker_meter_args`) did not. On 2026-10-29 Kiro overspent
  tasks **4×** this way.

## The fix (four parts, matching the ticket)

### 1. The ONE shared contract mounts the ledger dir and arms the cap
`meter_container_env.docker_meter_args()` now also:
- bind-mounts the host `~/.audioura_task_budgets` → `/task_budgets` (created if
  missing, so the mount never fails) and sets
  `AUDIOURA_TASK_BUDGET_DIR=/task_budgets`, so **every** isolated run of a task
  shares **one** ledger on the host;
- sets `TASK_BUDGET_ID=<task id>` and `TASK_BUDGET_USD=<budget>` (from the
  `task_budget_usd` arg or the caller's env), arming the whole-task cap — and
  keeping the LOCAL-822 mount guard armed — with zero per-runner wiring.

The five LOCAL-820 meter-contract signals are unchanged (a test pins them).

### 2. Budget from the meter itself — a mechanical cap at the raw door
New `check_task_budget_meter_log()` in `_meter/paid_api_meter.py`. When
`TASK_BUDGET_ID` is set, the raw meter door refuses a paid call once the **sum of
`usd` for rows whose `service == TASK_BUDGET_ID`** in the **canonical meter log**
(`PAID_API_LOG`) reaches `TASK_BUDGET_USD`. Because the meter log dir is
bind-mounted to the host and shared by every run of the task (the LOCAL-819/820
contract), that sum is the task's **true cross-run spend**, updated the instant
each call is recorded — independent of `LiveRunMeter`'s end-of-run ledger.

- The sum is **cached and re-read at most every 10 s** (like the daily-limit DB
  cache), keyed on `(log path, task id)`.
- **Fail-open** on any env/log read error (a meter bug must never block a tour).
- **Only** the task's own rows count (`service` match), so the shared stack's rows
  in the same log never count toward a task's cap, and vice-versa.
- **Never armed** without `TASK_BUDGET_ID`, and **never on Cloud Run**
  (`K_SERVICE` set) — the same arming gate as the LOCAL-822B mount guard, so a cap
  meant for Kiro task runs can never refuse a production paid call.
- Wired into **all 6** `install()` client patches (requests, urllib, httpx sync,
  httpx async, aiohttp, botocore), right after `check_task_budget()`.

### 3. `task_budget_report.py` falls back to the meter log
When no ledger exists for the id (the common case for a run whose container never
mounted the ledger dir — the very bug this fixes), the report sums the canonical
meter log by service and prints the metered total, the env budget, remaining
headroom, and `*** OVER BUDGET ***` (exit 2) when over. That is the same sum the
raw-door cap enforces, so the task's spend is answerable even when `LiveRunMeter`
never wrote a ledger row.

### 4. Tests — `tests/test_local827_container_budget.py` (20, all pass)
Two separate containers under one task id accumulate in the shared meter log; the
call that would cross the cap is refused (incl. end-to-end through the patched
`requests.Session.send`, before the network); `$0` budget refuses the first call;
the 10 s cache TTL is verified; **production is not armed** (no task id, Cloud Run
`K_SERVICE`, budget unset); fail-open on an unreadable log; the report fallback
over/under budget with exit codes.

## Changes

| File | Change |
|------|--------|
| `meter_container_env.py` | `docker_meter_args()` bind-mounts `~/.audioura_task_budgets` → `/task_budgets`, sets `AUDIOURA_TASK_BUDGET_DIR`, and arms `TASK_BUDGET_ID`/`TASK_BUDGET_USD` (arg or caller env). New `HOST_TASK_BUDGET_DIR` / `CONTAINER_TASK_BUDGET_DIR`. |
| `_meter/paid_api_meter.py` | New `check_task_budget_meter_log()` + helpers (`_sum_meter_log_usd_for_service`, `_meter_log_spent` with 10 s cache, `_meter_log_cap_armed`, `_meter_log_path_for_cap`). Called after `check_task_budget()` at all 6 `install()` client patches. |
| `translation-service/_meter/paid_api_meter.py` | Byte-identical vendored copy kept in sync (enforced by `test_translation_meter_copy.py`). |
| `task_budget_report.py` | Meter-log fallback when no ledger: `sum_meter_log_for_service()`, `_meter_log_fallback_text()`, `_meterlog_glob()`. |
| `tests/test_local827_container_budget.py` | 20 unit tests (new). |
| `run_local827_container.py`, `run_local827_live.sh` | Live-proof harness (new). |

## Unit tests

```
$ python3 -m pytest tests/test_local827_container_budget.py -q
20 passed in 0.33s

$ python3 -m pytest tests/test_local678_meter_httpx_aiohttp.py tests/test_local707_serper_metered.py \
    tests/test_local817_task_budget.py tests/test_local819_meter_gaps.py tests/test_local820_meter_wiring.py \
    tests/test_local822_meter_mount_guard.py tests/test_local827_container_budget.py \
    tests/test_translation_meter_copy.py -q
113 passed
```

(The full `tests/` run has ~196 pre-existing failures in unrelated suites —
`wallet_api`, `newsletter_*`, `entitlement_gate`, `zip_verification`,
`tour_editing` — that require a live DB/network; confirmed pre-existing by
stashing this change. The meter suites above pass in every grouping.)

## Live — BUDGET ENFORCED

`TASK_BUDGET_ID=LOCAL-827 TASK_BUDGET_USD=0.0002`, two `docker run --rm`
containers (`local827-tg-1`, `local827-tg-2` — never an `audioura-*` container,
never the live DB), tiny `gpt-4o` calls (`max_tokens=5`):

```
######## container run1 (local827-tg-1) ########
meter-log spend for LOCAL-827 BEFORE this container: $0.000000
  call 1: SENT  status=200
  call 2: SENT  status=200
  call 3: REFUSED by cap — TASK_BUDGET_USD reached (meter log): task LOCAL-827
          metered paid-API spend $0.0003 >= budget $0.0002. Refusing paid request
          (whole-task cap across all run containers, LOCAL-827).
meter-log spend for LOCAL-827 AFTER this container:  $0.000290

######## container run2 (local827-tg-2)  — a SEPARATE --rm container ########
meter-log spend for LOCAL-827 BEFORE this container: $0.000290   ← sees run1's spend
  call 1: REFUSED by cap — ... $0.0003 >= budget $0.0002 ...

--- meter_report.py --since today (BY SERVICE) ---
LOCAL-827                             2       0.0003            100              4

--- task_budget_report.py LOCAL-827 (meter-log fallback) ---
  metered rows (service=LOCAL-827): 2
  METERED TOTAL          $0.0003
  Budget:    $0.0002
  Remaining: $-0.0001
  *** OVER BUDGET by $0.0001 ***        exit=2
```

Container 1 crossed the cap on its **3rd** call; container 2 — a **separate**
`--rm` container — read container 1's spend from the shared host log and was
**refused on its first call**. This is the exact cross-container accumulation that
was broken before. The two SENT rows survived `--rm` on the host (meter_report
shows them), and `task_budget_report` reports the task over budget from the meter
log alone (no ledger). Real spend this proof: **~$0.0003**. Containers were removed
by the wrapper's trap; the shared `audioura-*` containers were never touched.

## Process / safety

- Committed only the files above to `LOCAL-827-container-budget` (no `git add -A`).
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`.
- No `DELETE`; the live DB was never written; the shared `audioura-*` containers
  were never touched.
