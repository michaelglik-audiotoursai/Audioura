# SUBMISSION — LOCAL-822: make the meter contract mechanical

**Branch:** `LOCAL-822-meter-mount-guard`
**Base:** subscribed — LOCAL-820 `128c1de9` (verified: `git merge-base --is-ancestor 128c1de9 HEAD` → exit 0)

## Problem

LOCAL-820 wired the `.sh` wrappers and `isolated_test.py` so an isolated
container's paid-API meter rows reach the host (bind-mount `~/Audioura/meterlogs`
→ `/meterlogs`, canonical `PAID_API_LOG`, `METER_SERVICE=<task id>`). But its
guard test (`test_local820_meter_wiring.py`) only **scans source files** — it
cannot see a **hand-typed `docker run`** (LOCAL-818 launched its live tours that
way). So the next hand-typed run still writes its rows to `/meterlogs` *inside*
the container, where `--rm` destroys them. LOCAL-818's two tours left **zero**
rows on the host for exactly this reason.

LOCAL-817 solved the same class of problem for the whole-task **budget** by
making `LiveRunMeter` and the raw meter door itself refuse. LOCAL-822 does the
same for the **meterlog mount**.

## The mechanism

Before any paid call, when running **inside a container** (`/.dockerenv` exists),
the meter **refuses** unless the run has proven its rows will reach the host:

1. the directory of `PAID_API_LOG` is a **bind mount** (`os.path.ismount`, with a
   `/proc/self/mountinfo` fallback), AND
2. the container carries an **identity**: `METER_SERVICE` or `TASK_BUDGET_ID`
   (the isolated-task contract), **or** `METER_ROLE` (the shared compose stack's
   `listener` identity).

The refusal (`MeterMountMissing`) names **`meter_container_env.docker_meter_args`**
— the one helper that emits the correct args — so the fix is in the error itself.

**Fail-open**, exactly like the daily limit and whole-task budget doors: not in a
container → allow; any error deciding mount/identity → allow and log; off
entirely when `METER_MOUNT_GUARD=0` (a deliberate no-mount diagnostic).

**The shared stack is unaffected.** `docker-compose.subscribed-local.yml` services
bind-mount `/meterlogs` and set `METER_ROLE=listener` (no `METER_SERVICE`), so
both halves of the contract are satisfied — proven by a test.

## Changes

| File | Change |
|------|--------|
| `_meter/paid_api_meter.py` | New `MeterMountMissing`, `_in_container`, `_mount_guard_on`, `_paid_api_log_path`, `_dir_is_bind_mount`, `_has_container_identity`, `check_meter_mount()`. `check_meter_mount()` called after `check_task_budget()` at all 6 `install()` client patches (requests, urllib, httpx sync, httpx async, aiohttp, botocore). |
| `translation-service/_meter/paid_api_meter.py` | Byte-identical vendored copy kept in sync. |
| `tests/live_run_meter.py` | `LiveRunMeter.__enter__` now calls `check_meter_mount()` (via the raw door) so a harness-launched container refuses before any paid call. Soft import; fail-open. |
| `tests/test_local822_meter_mount_guard.py` | 19 unit tests (new). |
| `run_local822_container.py`, `run_local822_live.sh` | Live-proof harness (new). |

## Unit tests — `python3 -m pytest tests/test_local822_meter_mount_guard.py -q`

```
19 passed in 0.47s
```

Covers: refuses without the mount (and names `meter_container_env.docker_meter_args`);
refuses without identity; passes with mount + `METER_SERVICE`; passes with mount +
`TASK_BUDGET_ID`; **shared-stack `METER_ROLE=listener` env passes**; host (no
`/.dockerenv`) unaffected; `METER_MOUNT_GUARD=0` escape hatch; end-to-end through
the patched `requests.Session.send`; `LiveRunMeter.__enter__` refuse/pass/host;
fail-open on a detection error; the real bind-mount detector (`/` is a mount).

### No regression — `pytest tests/test_local817 tests/test_local819 tests/test_local820 tests/test_local822`

```
68 passed in 0.57s
```

The broader meter suite shows 3 failures in `test_local678` (double-record, 2
rows vs 1). **Proven pre-existing and change-independent:** `test_local678`
alone passes 12/12; running `test_local769 + test_local678` together reproduces
the identical 3 failures with the **HEAD (pre-LOCAL-822)** `paid_api_meter.py`
restored. It is a cross-file test-isolation bug (the httpx patch stacks across
files that each call `install()`), not a LOCAL-822 regression.

## Live run — BUDGET ENFORCED (`TASK_BUDGET_ID=LOCAL-822 TASK_BUDGET_USD=0.05`)

`./run_local822_live.sh` — two disposable `docker run --rm` containers on the
`audioura-tour-generator:latest` image, one tiny OpenAI call (`max_tokens=5`).
`DB_*` pointed at a dead `127.0.0.1:1` so the meter's best-effort `_db_write`
fails open — **the live DB was never written**; the row lands only in the
host-mounted JSONL log. No `audioura-*` container, no `-p audioura`.

**RUN 1 — WITHOUT the meterlogs mount** (`PAID_API_LOG=/tmp/ephemeral/...`, no
`-v …:/meterlogs`):

```
LOCAL822_PROBE: REFUSED_BY_MOUNT_GUARD: [LOCAL-822] refusing paid call: this
container has NOT proven its meter rows reach the host — the directory of
PAID_API_LOG (/tmp/ephemeral) is not a host bind-mount, so its rows die inside
the --rm container. Build the run with meter_container_env.docker_meter_args() …
```

→ **$0 spent, no row, no `/tmp/ephemeral` leak on the host.**

**RUN 2 — WITH the full contract** (`METER_SERVICE=LOCAL-822`,
`-v ~/Audioura/meterlogs:/meterlogs`):

```
LOCAL822_PROBE: CALL_SENT status=200
```

Exactly **one** row in `~/Audioura/meterlogs/paid_api_calls.jsonl`:

```json
{"ts": "2026-10-30T02:59:35Z", "kind": "openai", "status": 200,
 "rate_tag": "2026-10-10-r5", "service": "LOCAL-822",
 "caller": "run_local822_container.py:46",
 "url": "https://api.openai.com/v1/chat/completions",
 "role": null, "usd": 4.2e-06, "model": "gpt-4o-mini-2024-07-18",
 "tokens_in": 8, "tokens_out": 5, "rate_key": "gpt-4o-mini"}
```

`grep -c '"service": "LOCAL-822"'` → **1**. Both `--rm` containers cleaned up.

## `task_budget_report.py LOCAL-822`

```
$ python3 task_budget_report.py LOCAL-822
No ledger for task LOCAL-822 (/Users/micha/.audioura_task_budgets/LOCAL-822.json). No runs recorded yet.
```

The live proof is a **raw-door** probe (a single `requests.post`), not a
`LiveRunMeter` run, so it deliberately does not append to the whole-task JSON
ledger — only `LiveRunMeter.record()` does. The $0.05 whole-task budget was still
enforced on every call (via `check_task_budget`), and the one metered call
(`usd ≈ $0.0000042`) is far under it. The spend is recorded where LEAD sums it:
the shared `~/Audioura/meterlogs/paid_api_calls.jsonl` row above, tagged
`service=LOCAL-822`.
