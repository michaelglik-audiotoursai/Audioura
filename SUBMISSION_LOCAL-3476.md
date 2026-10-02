# SUBMISSION — LOCAL-3476: Test the service the app actually calls

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3476-orchestrator-empty-type-test`
**Base:** `storied` (verified: `git merge-base --is-ancestor e1341e6 HEAD` → exit 0)
**Supersedes:** `LOCAL-474-empty-tour-type` — its production code is correct and kept as-is.

## The problem being closed

LOCAL-474 relaxed the same validation guard in **two** services so that an empty
`tour_type` means "classify it" rather than a 400:

| Service | Endpoint | Guard (correct) |
|---|---|---|
| `generate_tour_text_service.py` | `/generate` | `if not location:` |
| `tour_orchestrator_service.py` | `/generate-complete-tour` | `if not location:` |

LOCAL-474's suite only drove the **text generator's** `test_client()`. LEAD's
break-the-code check (D242) restored the old guard
(`if not location or not tour_type:`) in the **orchestrator** and the suite
**stayed green** — the endpoint the app actually calls (the one Michael's phone
hit, that returned his 400 on 2026-09-03, that LEAD reproduced against
production) had **no coverage**. That is D418/D421 again: green tests over the
unverified path.

## What this task delivers

`tests/test_local476_orchestrator_empty_type.py` drives
`tour_orchestrator_service.app` with a Flask `test_client()` and asserts the
`/generate-complete-tour` validation gate directly, mirroring how LOCAL-474's
suite drives the text service. All real side effects downstream of the gate are
stubbed so nothing real runs:

- `entitlements.check_tour_quota` → always allowed (no plan/DB lookup)
- `psycopg2.connect` → usage-recording `INSERT` is a no-op
- `track_user_tour` → no user-tracking side effect
- `threading.Thread` → the background generation thread never starts

A request that clears the gate returns the queued `200` without touching a live
service; a gate rejection returns `400` before any stub is reached.

### Coverage on the ORCHESTRATOR (`/generate-complete-tour`)

| Test | Expectation |
|---|---|
| `test_ac1_empty_tour_type_is_accepted` | empty `tour_type` → **200 queued** |
| `test_ac1_missing_tour_type_key_is_accepted` | missing `tour_type` key → **200 queued** |
| `test_ac3_missing_location_still_400s_and_names_location` | missing `location` → **400**, message names `location` |
| `test_ac3_empty_location_still_400s` | empty `location` → **400** |
| `test_ac2_explicit_tour_type_still_wins` | explicit `tour_type` → **200 queued** |

## Break-the-code evidence (D242)

**No production behaviour was changed.** The two edits below were made only to
prove the tests can fail, then reverted. Final `git diff` on both service files
is empty.

### GREEN baseline (unbroken)

```
$ python3 -m pytest tests/test_local476_orchestrator_empty_type.py tests/test_local474_empty_tour_type.py
======================== 18 passed, 1 warning in 0.38s =========================
```

### BREAK 1 — restore the bug in `tour_orchestrator_service.py` (THE WHOLE TASK)

Restored `if not location or not tour_type:` at line 1505:

```
FAILED tests/test_local476_orchestrator_empty_type.py::TestOrchestratorValidationGate::test_ac1_empty_tour_type_is_accepted
FAILED tests/test_local476_orchestrator_empty_type.py::TestOrchestratorValidationGate::test_ac1_missing_tour_type_key_is_accepted
=================== 2 failed, 16 passed, 1 warning in 0.31s ====================
```

Failure detail (the endpoint now 400s the well-formed empty-type request):

```
E  AssertionError: 400 != 200 : missing tour_type key must be accepted by the
   orchestrator, got 400: b'{"error":"location and tour_type are required"}\n'
```

→ **Breaking the orchestrator turns tests RED. AC1 satisfied — this is the whole task.**
Guard then restored to `if not location:`.

### BREAK 2 — restore the bug in `generate_tour_text_service.py` (LOCAL-474 coverage kept)

Restored `if not location or not tour_type:` at line 554:

```
FAILED tests/test_local474_empty_tour_type.py::TestTextServiceValidationGate::test_ac1_empty_tour_type_is_accepted
FAILED tests/test_local474_empty_tour_type.py::TestTextServiceValidationGate::test_ac1_missing_tour_type_key_is_accepted
=================== 2 failed, 16 passed, 1 warning in 0.26s ====================
```

→ **Breaking the text service still turns tests RED. AC2 satisfied.**
Guard then restored to `if not location:`.

### GREEN restored (both fixes back in place)

```
$ git diff --stat tour_orchestrator_service.py generate_tour_text_service.py
(empty — no production changes remain)

$ grep -n "if not location" tour_orchestrator_service.py generate_tour_text_service.py
tour_orchestrator_service.py:1505:    if not location:
generate_tour_text_service.py:554:    if not location:

$ python3 -m pytest tests/test_local476_orchestrator_empty_type.py tests/test_local474_empty_tour_type.py
======================== 18 passed, 1 warning in 0.22s =========================
```

## Acceptance criteria — status

1. Breaking `tour_orchestrator_service.py` turns tests red — **PASS** (Break 1, 2 red).
2. Breaking `generate_tour_text_service.py` still turns tests red — **PASS** (Break 2, 2 red).
3. All tests pass unbroken — **PASS** (18 passed).
4. Both break-runs pasted, red and green — **PASS** (above).

## Live verification (LEAD, post-merge)

```
{"location":"Bread Thyme restaurant tour in West Roxbury, MA","tour_type":"","total_stops":1}
```

against `/generate-complete-tour` — expected: accepted (queued), not a 400. Unit
coverage of the validation gate is what was missing and is now closed; no tour is
generated here (that costs money/time).

## Process notes

- Verified base with `git merge-base --is-ancestor e1341e6 HEAD` (exit 0); branch
  created from local `storied` HEAD, never `origin/*`.
- No production behaviour changed. No Docker rebuild. No protected docs touched
  (`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `BUILD_NUMBERS.md`).
- Deliverable committed on-branch so it cannot be pruned (the prior attempt lost
  its work by never committing).
