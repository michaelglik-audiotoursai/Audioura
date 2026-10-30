# SUBMISSION — LOCAL-817: Enforce the WHOLE-TASK paid-API cap mechanically

**Branch:** `LOCAL-817-task-budget` (from `subscribed` = 7e687d9b)
**Problem:** Task files say "Paid-API cap $X **TOTAL across all runs**", but the
only enforcement — `tests/live_run_meter.LiveRunMeter` — capped spend **per run**
(`TEST_GEMINI_MAX_USD`). Re-runs during debugging each got the full per-run cap
again, so the total quietly ran past the task-file number every time
(LOCAL-810 $2.88 vs $1.00, LOCAL-816 $1.47 vs $0.60, LOCAL-814B $0.68 vs $0.60,
LOCAL-802 $1.29 vs $1.20). Instructions alone did not hold (Kiro overspent 3× on
2026-10-29). This makes the whole-task cap mechanical.

## What was built

### 1. `task_budget.py` — the ledger + cap (new, repo root)
- Reads the env contract **`TASK_BUDGET_ID`** + **`TASK_BUDGET_USD`**.
- Append-only JSON ledger per task at `~/.audioura_task_budgets/<id>.json`
  (dir overridable with `AUDIOURA_TASK_BUDGET_DIR` for tests). One entry per run:
  `{"ts", "usd", "note", "capped"}`.
- `spent_so_far(id)`, `record_run(id, usd, …)` (atomic temp-file + rename),
  `check_task_budget(pending, …)` → raises **`BudgetExceeded`** when
  `spent_so_far + pending > budget`, else returns remaining headroom.
- **Fail philosophy:** the cap is a hard stop (raises); a corrupt/missing ledger
  reads as `$0` (fail-open on read) so a disk glitch can't wedge a task; writes
  are best-effort and never raise into a run. A `$0` budget is a real cap.

### 2. `LiveRunMeter` wiring (`tests/live_run_meter.py`)
- **Refuse to START:** `__init__` resolves the task budget and raises
  `BudgetExceeded` when `spent_so_far + reserve > budget` (before the cap is
  installed, so no grounded work happens on an over-budget task).
- **Abort mid-run:** the existing `story_leads` grounding-counter guard
  (`_cap_guard`) now checks the whole-task budget **first** (using the run's
  combined spend as `pending`), raising `BudgetExceeded` before the per-run cap.
- **Record on exit:** `record()` appends this run's total to the task ledger
  (independently of, and before, the DB `cost_ledger` write — so the next run's
  cap sees it even when the shared DB is unreachable from an isolated container).
- The per-run `TEST_GEMINI_MAX_USD` cap (LOCAL-613) is untouched; the two caps
  compose, whichever bites first.

### 3. Raw-door catch (`_meter/paid_api_meter.py` + mirror)
- Added self-contained `check_task_budget()` + `TaskBudgetExceeded`, reading the
  **same** env + **same** JSON ledger (no import of repo-root `task_budget.py`,
  because the meter ships to containers via `PYTHONPATH=/opt/meter` with nothing
  else on the path). Called alongside `check_daily_limit()` at **every** paid
  door: `requests`, `urllib`, `httpx` sync/async, `aiohttp`, and the `botocore`
  path — so a paid call made **outside** `LiveRunMeter` is refused once the task's
  recorded total reaches the budget. Fail-open on any error, exactly like the
  daily limit.
- Mirrored byte-identically into `translation-service/_meter/paid_api_meter.py`
  (`tests/test_translation_meter_copy.py` still passes).

### 4. `task_budget_report.py <id>` (new)
- Prints each recorded run, the running total, the budget, and remaining
  headroom. Exit `0` within budget, `2` over budget, `1` no ledger / bad usage.

### 5. Docs — `tests/README_TASK_BUDGET.md` (new)
- States that **every task's live runs MUST export `TASK_BUDGET_ID` /
  `TASK_BUDGET_USD`** (LEAD puts them in the task file), with the why, the
  behaviour, the no-env fallback, and the report command.

## Tests — `tests/test_local817_task_budget.py` (19 cases, no network, no DB)
- **Two runs whose sum exceeds the budget → second refuses to START** (both the
  budget-consumed and the reserve-headroom shapes).
- **A run crossing mid-way → `BudgetExceeded` at the grounding counter**, and the
  per-run cap still fires independently when the task budget is generous.
- **Raw-door refusal** (`paid_api_meter.check_task_budget`), and the door + the
  ledger module agree on the file path and the computed total.
- **Ledger round-trip** (append-only, read-back, corrupt-file fail-open) + report
  over-budget exit code.
- **No env → old behaviour:** cap off, grounding uses only the per-run cap, no
  ledger written.
- **Paid-API cap `$0` with a FAKE paid call:** a `$0` budget refuses a fake
  `requests.Session.send` to `api.openai.com` through the meter's patched client
  **before** it reaches the network, and refuses a `LiveRunMeter` run at start.

### Verification (local)
```
python3 -m pytest tests/test_local817_task_budget.py -q      → 19 passed
python3 -m pytest tests/test_local613_meter_and_cap.py        → 14 passed (no regression)
python3 -m pytest tests/test_translation_meter_copy.py        → 2 passed (mirror in sync)
python3 -m pytest …673_daily_paid_limit …678_meter_httpx…     → all passed
python3 task_budget.py                                         → self-check OK
python3 task_budget_report.py <id>                             → report + exit codes OK
```

## Files
- **new:** `task_budget.py`, `task_budget_report.py`,
  `tests/test_local817_task_budget.py`, `tests/README_TASK_BUDGET.md`
- **changed:** `tests/live_run_meter.py`, `_meter/paid_api_meter.py`,
  `translation-service/_meter/paid_api_meter.py`

## Notes / limits
- The raw door refuses once `spent_so_far >= budget` (it cannot know a call's cost
  before it happens); the precise `spent + current-run` accounting lives in
  `LiveRunMeter`'s grounding guard. The door is the belt-and-suspenders catch for
  calls outside `LiveRunMeter`.
- No protected files were edited (DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
  `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, etc.). No deletes.
  Staged only the seven files above (never `git add -A`).
