# SUBMISSION — LOCAL-820: isolated task containers write NO meter rows

**Branch:** `LOCAL-820-task-container-meter`  **Base:** subscribed @ `edc6fdda` (contains LOCAL-819)
`git merge-base --is-ancestor edc6fdda HEAD` → exit 0 (correct base).

## The bug

The meter's `usage` tokens since Oct 26 were 13.1 M; OpenAI's usage page showed
31.5 M tokens / 28,995 requests. ~16k calls / ~18 M tokens were logged nowhere.
LOCAL-818's two live tours (`run_local818_container.py`, $0.50) left **zero** rows
in `~/Audioura/meterlogs/`.

**Root cause (proven, no paid calls — `proof_local820_meter_rows.py`):** the
paid-API meter (`_meter/paid_api_meter.py`, baked into the generator image at
`PYTHONPATH=/opt/meter`) writes every call to
`LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")`.
LOCAL-818's `docker run` bind-mounted only `"$PWD":/app` — **no**
`-v ~/Audioura/meterlogs:/meterlogs` and **no** `PAID_API_LOG`. So the meter wrote
its rows to `/meterlogs` **inside** the `--rm` container, where they died with it.
`LiveRunMeter` recorded to the `cost_ledger` DB (the *isolated* postgres) and the
task-budget JSON (the *container's* home) — both also lost on `--rm`. Nothing
reached the host sweep.

```
$ python3 proof_local820_meter_rows.py
[A] LOCAL-818 AS SHIPPED: no -v meterlogs mount, LOG defaults to /meterlogs inside the container
    rows written to container path : 1
    after `docker run --rm` ... rows now visible to meter_report: 0   <-- THE BUG (rows died)
[B] LOCAL-820 FIX: docker_meter_args() mounts the host dir + tags METER_SERVICE=LOCAL-820
    rows written to HOST path : 1   host log survives the container : True
    kind=openai service='LOCAL-820' key_suffix='k9sA' tokens_in=11 tokens_out=3
VERDICT: PROVEN
```

Also unmetered on the shared stack: `coordinates-fromai` had an OpenAI key and no
meter mount.

## The fix — the meter contract on every isolated container

Every isolated `docker run` that can make a paid call now carries the five args
`meter_container_env.docker_meter_args()` returns:

| # | signal | why |
|---|--------|-----|
| 1 | `-e PYTHONPATH=/opt/meter` | sitecustomize installs the network meter |
| 2 | `-e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl` | the ONE canonical log every sweep reads |
| 3 | `-e METER_SERVICE=LOCAL-NNN` | tags rows so `meter_report.py` totals per task |
| 4 | `-v ~/Audioura/meterlogs:/meterlogs` | rows land on the HOST (survive `--rm`) |
| 5 | `-v <worktree>/_meter:/opt/meter:ro` | the metered code, in lock-step with the branch |

### Changes

- **`isolated_test.py`** (the shared runner every `run_local*_container.py`
  copies from) now imports `meter_container_env` and appends
  `docker_meter_args(task_id=args.task_id, meter_dir=<context>/_meter)` to its
  `docker run` command.
- **`run_local818_live.sh`** (new) — the correctly-wired wrapper LOCAL-818 never
  had; `run_local818_container.py`'s docstring now shows the meter-wired command.
- **All six generator `.sh` wrappers carry the full 5/5 contract** so the guard
  needs no allowlist: `run_local585/592_live.sh` (added the contract),
  `run_local779b/799/801_live.sh` (added `PYTHONPATH`, the `_meter` mount and
  `METER_SERVICE`; 799/801 switched a per-task log filename to the canonical
  `paid_api_calls.jsonl`), `run_local818_live.sh` and `run_local820_live.sh`.
- **`tests/test_local820_meter_wiring.py`** (new, guard) — FAILS if
  `isolated_test.py` stops using `docker_meter_args()`, or if any
  `run_local*.sh` launching the generator image is missing a contract signal.
  Verified it FAILS on an un-metered probe wrapper and PASSES once removed.
- **`tests/README_TASK_BUDGET.md`** — the meter contract is documented next to the
  budget contract, so every new task gets both.
- **`docker-compose.subscribed-local.yml`** — a `coordinates-fromai` override
  mirrors `tour-generator`'s meter wiring (`PYTHONPATH=/opt/meter`,
  `PAID_API_LOG`, the `_meter`/`meterlogs` mounts, and the listener role token).
  **Not applied here — LEAD rebuilds/recreates the container.**
- **`repin_tours.py`** — the test-isolation leak fix (below).

## Test-isolation leak (fixed at source)

`tests/test_local818_district_refill.py` failed (5 tests) only when run after
`tests/test_local815_repin_tours.py` in one pytest process. Cause:
`repin_tours.derive_museum_fallback` did
`os.environ.setdefault("LANDMARK_LIVE_LOOKUP", "1")`, which **permanently**
mutates the process env. `local802_relevance_gate._live_wikidata_aliases` then saw
the flag ON for every later test, so the same-building alias bridge over-merged
distinct stops (proven: clean env → dedupe keeps 4; `LANDMARK_LIVE_LOOKUP=1` →
keeps 3, wrongly merging "Westminster Cathedral" into the Abbey).

Fix: a scoped `_landmark_live_lookup()` context manager sets the flag only for the
Wikidata lookup call and restores/pops it afterwards. Verified:

```
815 then 818 (one process):  17 passed   (was 5 failed)
818 then 815 (one process):  17 passed
818 alone: 8 passed   815 alone: 9 passed
no regressions: 813 + 803 + 817 = 49 passed;  819 + 820 meter = 28 passed
```

## Live proof — BUDGET ENFORCED `TASK_BUDGET_ID=LOCAL-820 TASK_BUDGET_USD=0.10`

`./run_local820_live.sh` runs ONE isolated `docker run --rm` on
`audioura-tour-generator:latest` with the full meter contract (+ the task-budget
dir mounted at `/task_budgets` so the budget ledger survives `--rm` too). The
harness makes two tiny OpenAI calls (`gpt-4.1-mini`, `max_tokens=5`) via
`requests.post("https://api.openai.com/v1/chat/completions", ...)` — the SAME path
`generate_tour_text.py` uses — then records the spend. No tours.

The rows land on the **host** and survive the container (grepped from the host
after `--rm` removed `local820-tg`):

```
{"ts": "2026-10-30T02:32:02Z", "kind": "openai", "status": 200, "service": "LOCAL-820",
 "caller": "run_local820_container.py:91", "url": "https://api.openai.com/v1/chat/completions",
 "key_suffix": "k9sA", "usd": 7.2e-06, "model": "gpt-4.1-mini-2025-04-14",
 "tokens_in": 14, "tokens_out": 1, "rate_key": "gpt-4.1-mini"}
```

The `cost_ledger` DB write fails (postgres-2 is unreachable from the isolated
container) — non-fatal, and exactly the class this ticket fixes: DB-only recording
dies with the container, but the JSONL meter log and the task-budget JSON on the
host mounts survive.

### `meter_report.py --since 2026-10-30T02:29:00Z --kind openai`

```
meter_report — since 2026-10-30T02:29:00Z  (kinds=openai)
rows scanned=37833  kept=6  (billed only)

BY DAY (UTC)
                               requests          usd      tokens_in     tokens_out
----------------------------------------------------------------------------------
2026-10-30                            6       0.0000             84              6

BY SERVICE
                               requests          usd      tokens_in     tokens_out
----------------------------------------------------------------------------------
LOCAL-820                             6       0.0000             84              6

BY MODEL
                               requests          usd      tokens_in     tokens_out
----------------------------------------------------------------------------------
gpt-4.1-mini                          6       0.0000             84              6

BY KEY-SUFFIX
                               requests          usd      tokens_in     tokens_out
----------------------------------------------------------------------------------
k9sA                                  6       0.0000             84              6

TOTAL   requests=6  usd=$0.0000  tokens_in=84  tokens_out=6
```

(6 rows = 3 proof runs × 2 calls; combined cost ≈ $0.0000432, far under $0.10.
`usd=$0.0000` is the 4-dp display of that sub-cent total.)

### `task_budget_report.py LOCAL-820`

```
Task budget report: LOCAL-820
Ledger: /Users/micha/.audioura_task_budgets/LOCAL-820.json

  when (UTC)                      usd  note
  ----------------------------------------------------------
  2026-10-30T02:32:02Z        $0.0000  TEST-LOCAL-820
  ----------------------------------------------------------
  TOTAL (1 runs)              $0.0000

Budget:    $0.1000
Remaining: $0.1000
```

## Files changed

New: `proof_local820_meter_rows.py`, `run_local818_live.sh`,
`run_local820_container.py`, `run_local820_live.sh`,
`tests/test_local820_meter_wiring.py`.

Modified: `isolated_test.py`, `repin_tours.py`,
`docker-compose.subscribed-local.yml`, `tests/README_TASK_BUDGET.md`,
`run_local818_container.py`, `run_local585_live.sh`, `run_local592_live.sh`,
`run_local779b_live.sh`, `run_local799_live.sh`, `run_local801_live.sh`.

## Constraints honoured

No tours. ≤2 tiny OpenAI calls per run (`max_tokens=5`), under the $0.10 budget.
Never wrote the live DB; only counted. No `DELETE`. Never touched a shared
`audioura-*` container (the compose change is edit-only — LEAD applies it). No
protected file edited (DECISIONS/CLAUDE/BACKLOG/WORK_QUEUE/`.continuous_dev/`/
SUBSCRIBED_COMMUNICATION_01/`legal/`/GCLOUD_STORIED_START_HERE/TRAVEL_PROJECTS).
