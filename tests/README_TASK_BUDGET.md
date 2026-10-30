# Live runs MUST set a WHOLE-TASK paid-API budget (LOCAL-817)

**Every task's live runs MUST be started with `TASK_BUDGET_ID` and
`TASK_BUDGET_USD` exported.** LEAD puts these two lines in the task file; the
run harness inherits them from the environment. This is not optional — it is the
mechanism that keeps a task's TOTAL paid-API spend inside the "Paid-API cap $X
TOTAL across all runs" number the task file states.

```bash
export TASK_BUDGET_ID=LOCAL-816     # which task's ledger this run belongs to
export TASK_BUDGET_USD=0.60         # the WHOLE-TASK cap in dollars (all runs summed)
# then run the task's live harness exactly as before, e.g.:
python3 run_localNNN_live.py        # or docker run … the isolated generator
```

## Why (the bug this prevents)

`tests/live_run_meter.py` (`LiveRunMeter`) has always enforced a **per-run** cap,
`TEST_GEMINI_MAX_USD` (default $1.00). But a task is re-run many times while it is
debugged, and each re-run was allowed the full per-run cap again — so the TOTAL
quietly ran past the task-file number every time:

| Task       | Spent  | Cap in task file |
|------------|--------|------------------|
| LOCAL-810  | $2.88  | $1.00            |
| LOCAL-816  | $1.47  | $0.60            |
| LOCAL-814B | $0.68  | $0.60            |
| LOCAL-802  | $1.29  | $1.20            |

Instructions alone did not hold (Kiro overspent 3× on 2026-10-29). The whole-task
budget makes it mechanical.

## What it does

With `TASK_BUDGET_ID` + `TASK_BUDGET_USD` set, each run:

1. **Records** its spend into an append-only JSON ledger at
   `~/.audioura_task_budgets/<id>.json` (one entry per run).
2. **Refuses to START** when `spent_so_far + this run's reserve > budget`
   (`LiveRunMeter(...)` raises `task_budget.BudgetExceeded` at construction).
3. **Aborts mid-run** at the grounding/LLM counter the instant
   `spent_so_far + this run's spend` would cross the budget (`BudgetExceeded`,
   raised at the same counter the per-run cap uses) — the tour clean-fails and
   the **submission must report it**.
4. **Catches raw paid calls** made outside `LiveRunMeter`: the metered paid door
   (`_meter/paid_api_meter.py`, shipped to containers via `PYTHONPATH=/opt/meter`)
   reads the same env + ledger and refuses any paid request once the recorded
   total has reached the budget (`TaskBudgetExceeded`).

The two caps compose: a run stops at whichever bites first — the per-run
`TEST_GEMINI_MAX_USD` or the whole-task `TASK_BUDGET_USD`.

## When the env is NOT set

If `TASK_BUDGET_ID` is unset (or `TASK_BUDGET_USD` is unset/negative) the
whole-task cap is **OFF** and behaviour is exactly as before: only the per-run
`TEST_GEMINI_MAX_USD` cap applies, and no ledger is written. This keeps every
existing harness working untouched — but a live run started this way has NO
whole-task protection, which is why the two env vars are **required**.

A budget of exactly `$0` is a real cap: it means *no paid spend is allowed*, used
by the LOCAL-817 `$0` test (a fake paid call is refused without a network round
trip).

## Inspecting a task's spend

```bash
python3 task_budget_report.py LOCAL-816
```

Prints every recorded run, the running total, the budget, and the remaining
headroom. Exit status `2` means the recorded total is already over budget.

## Tests

`tests/test_local817_task_budget.py` proves, with no network and no DB: two runs
whose sum exceeds the budget (second refuses to start), a run crossing the budget
mid-way (aborts at the grounding counter), raw-door refusal, ledger round-trip,
no-env old behaviour, and the `$0` budget refusing a fake paid call end-to-end.
