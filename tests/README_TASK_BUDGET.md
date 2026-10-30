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

---

# Live runs MUST also meter to the shared log (LOCAL-820)

The whole-task **budget** above caps spend; the **meter** records where it went.
They are two halves of one contract and every new task needs BOTH. The budget
without the meter is how the ~16k unmetered OpenAI calls happened: LOCAL-818's
two live tours set `TASK_BUDGET_ID`/`TASK_BUDGET_USD` correctly but their
`docker run` did not mount the meter, so the paid-API meter wrote its rows to
`/meterlogs` **inside** the `--rm` container and they died with it — zero rows in
`~/Audioura/meterlogs`, nothing for `meter_report.py` to total.

## The meter contract (every isolated container carries these)

An isolated `docker run` that can make a paid call MUST carry the args
`meter_container_env.docker_meter_args()` returns:

```python
import meter_container_env as mce
docker_cmd += mce.docker_meter_args(
    task_id="LOCAL-NNN",                 # tags every row service=LOCAL-NNN
    meter_dir="<worktree>/_meter",       # mounted read-only at /opt/meter
    # host_meter_dir defaults to ~/Audioura/meterlogs
    key_suffix="k9sA",                   # optional, last few chars of the key
)
```

which is exactly these five signals:

| # | signal | why |
|---|--------|-----|
| 1 | `-e PYTHONPATH=/opt/meter` | sitecustomize installs the network meter |
| 2 | `-e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl` | the ONE canonical log every sweep reads |
| 3 | `-e METER_SERVICE=LOCAL-NNN` | tags rows so `meter_report.py` totals per task |
| 4 | `-v ~/Audioura/meterlogs:/meterlogs` | lands rows on the HOST (they survive `--rm`) |
| 5 | `-v <worktree>/_meter:/opt/meter:ro` | the metered code, in lock-step with the branch |

In a `.sh` wrapper, carry the same five args literally — see
`run_local818_live.sh` for the template. (`METER_SERVICE` may be omitted ONLY
when `TASK_BUDGET_ID` is set, because the meter defaults `service` to
`TASK_BUDGET_ID`; setting it explicitly is clearer and is what the guard test
checks.)

## Inspecting a task's metered spend

```bash
python3 meter_report.py --since 2026-10-29     # by day / service / model / key
```

Rows tagged `service=LOCAL-NNN` are this task's; the sum across all its runs is
the task's real paid-API spend, lined up against the provider usage page.

## Guard

`tests/test_local820_meter_wiring.py` FAILS if the shared runner
(`isolated_test.py`) stops using `docker_meter_args()`, or if any
`run_local*.sh` that launches the generator image is missing a contract signal —
so a new task cannot ship an un-metered container.
