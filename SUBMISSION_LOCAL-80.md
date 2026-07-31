##### READY FOR REVIEW

**Commit:** `bf0513e`
**Branch:** `kiro/local80-dispatcher-base-branch`
**Base:** `storied` (at `ccd93e4`)

---

## Changes

### `kiro_dispatcher.py` (+578 lines net)

| Change | Detail |
|--------|--------|
| `BASE_LINE_RE` | New regex: `\*\*Base:\*\*\s*(\S+)` |
| `base_branch_for(prompt)` | Parses `**Base:**` from task header; returns `"storied"` when absent |
| `validate_base_branch(base, cwd)` | Verifies branch exists via `git rev-parse --verify`; returns `(ok, error_message)` with clear diagnostics including available branches on failure |
| `setup_worktree(task_id, branch, base)` | Now takes `base` parameter; `git worktree add -b <branch> <path> <base>` instead of hardcoded `"storied"` |
| `dispatch()` → STARTED line | Reads task file to extract base; records `base=<value>` in the log |
| `worker()` | Calls `validate_base_branch()` before `setup_worktree()`; FAILED with clear message on bad base |
| `worker()` → terminal line | Includes `base=<value>` in COMPLETED/FAILED/TIMEOUT record |
| `pid_is_alive(pid)` | `os.kill(pid, 0)` liveness probe |
| `PID_FROM_STARTED_RE` | Regex to extract `dispatcher_pid=(\d+)` from log lines |
| `check_worker_liveness()` | Runs every dispatch tick: for tasks stuck at STARTED, checks if the PID is dead; appends `ABANDONED \| reason=worker_died` if so |
| `dispatch()` integration | Calls `check_worker_liveness()` before the main loop (after reboot recovery) |
| `render_status()` | Displays dead-worker abandonments in STATUS.md |

### `scratch/test_local80_dispatcher_fixes.py` (unit tests, 13 cases)

### `scratch/test_local80_integration.py` (integration tests, 5 cases)

---

## Evidence

### Criterion 1: `**Base:** subscribed` → worktree cut from subscribed

```
--- Test: worktree from subscribed base ---
  Confirmed: branch is at subscribed (3411407e), NOT storied (ccd93e42)
  git merge-base kiro/test-local80-sub-base subscribed = 3411407e
  PASS: worktree cut from subscribed, proven via merge-base
```

### Criterion 2: No `**Base:**` → still cuts from storied (existing files unaffected)

```
--- Test: worktree from storied (default) base ---
  git merge-base kiro/test-local80-stor-base storied = ccd93e42
  PASS: worktree cut from storied, proven via merge-base
```

### Criterion 3: Bad base name → fails at dispatch with clear error, no worktree

```
--- Test: bad base name fails, no worktree created ---
  Error message: Base branch 'nonexistent-typo-xyz' does not exist. Available local branches: (none, kiro/local10-sto
  PASS: bad base fails at validation, no worktree created
```

### Criterion 4: Liveness — kill a worker mid-flight, ABANDONED appears, task re-dispatches

```
--- Test: liveness check detects dead worker ---
  Killed PID 35661, check_worker_liveness() detected it
  PASS: dead worker produces ABANDONED record, task eligible for re-dispatch

--- Test: worktree reused on retry (not deleted) ---
  PASS: worktree reused on retry, in-flight work preserved
```

### Criterion 5: STARTED lines include the base

New format:
```
- STARTED   | task=<file> | at=<iso> | base=<base> | dispatcher_pid=<pid>
```

Terminal record also includes `base=`:
```
- COMPLETED | task=<file> | id=T<id> | branch=<branch> | base=<base> | worktree=<path> | ...
```

---

## Full test output (18/18 pass)

```
=== LOCAL-80 dispatcher tests ===

  PASS: base_branch_for() parses **Base:** subscribed
  PASS: base_branch_for() defaults to 'storied' when absent
  PASS: validate_base_branch() accepts existing 'storied'
  PASS: validate_base_branch() accepts existing 'subscribed'
  PASS: validate_base_branch() rejects bad branch with clear error
  PASS: pid_is_alive() returns True for self
  PASS: pid_is_alive() returns False for killed PID
  PASS: STARTED line format includes base= and STATUS_LINE_RE still parses it
  PASS: liveness check logic validated
  PASS: setup_worktree() accepts (task_id, branch, base)
  PASS: integration - task with Base: subscribed parses correctly
  PASS: integration - task with no Base: defaults to storied
  PASS: integration - bad base fails with clear error

Results: 13 passed, 0 failed

=== LOCAL-80 Integration Tests ===

  PASS: worktree cut from subscribed, proven via merge-base
  PASS: worktree cut from storied, proven via merge-base
  PASS: bad base fails at validation, no worktree created
  PASS: dead worker produces ABANDONED record, task eligible for re-dispatch
  PASS: worktree reused on retry, in-flight work preserved

Integration Results: 5 passed, 0 failed
```
