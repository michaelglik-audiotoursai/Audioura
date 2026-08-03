#!/bin/zsh
# Reap orphaned kiro-cli processes, and stop a dying task from re-dispatching
# forever.
#
# WHY: on 2026-08-01 LOCAL-112 and LOCAL-113 each died twice with no log file
# at all — killed before they could write. Swap was at 91% (2799MB of 3072MB)
# and there were 14 kiro-cli processes for 3 tasks. Every death leaked an
# orphaned kiro-cli-chat that never exited; five were found aged 5h, 2.5h and
# 1.5h, one pair per failed run.
#
# LOCAL-80's liveness check then re-dispatched each dead task straight back
# into the same wall, leaking another pair. The recovery mechanism was
# working as designed and feeding the problem. An automatic retry with no
# backoff turns a resource problem into a resource spiral.
#
# FIX (LOCAL-155, 2026-08-02): The original script had two bugs:
#   1. Global guard: only reaped when ZERO dispatcher workers were running,
#      meaning it never fired during an active stretch (always at least one
#      worker alive). Fix: check per-process parentage — an orphan is a
#      kiro-cli whose parent is NOT a dispatcher worker.
#   2. ps -o etimes= is Linux-only. macOS ps does not support it, so the age
#      calculation always failed and nothing was ever reaped. Fix: compute
#      age from lstart using date arithmetic.

REPO="$HOME/Audioura"
CD="$REPO/.continuous_dev"
LOG="$CD/autonomy.log"
SESSIONS="$REPO/kiro_sessions_ran.md"
MAX_DEATHS=3
# Minimum age in seconds before a kiro-cli process is eligible for reaping.
# Safety backstop: even if parentage says "orphan", we wait this long to
# avoid killing a process whose parent just exited a moment ago and whose
# task may still be recording its terminal status.
MIN_AGE_SECONDS=300

# --- Helper: compute elapsed seconds for a PID on macOS. ---
# macOS ps lacks etimes, so we parse `lstart` and do date math.
elapsed_seconds() {
  local pid=$1
  local lstart
  lstart=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs)
  [ -z "$lstart" ] && return 1
  local start_epoch
  start_epoch=$(date -j -f "%a %b %d %T %Y" "$lstart" "+%s" 2>/dev/null)
  [ -z "$start_epoch" ] && return 1
  local now_epoch
  now_epoch=$(date "+%s")
  echo $(( now_epoch - start_epoch ))
}

# --- Helper: determine which task a kiro-cli process belongs to. ---
# Looks at the process's cwd (worktree path) to extract the task ID.
task_for_pid() {
  local pid=$1
  # lsof -p is reliable for cwd on macOS
  local cwd
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | grep '^n' | head -1 | cut -c2-)
  if [ -n "$cwd" ]; then
    # Worktree paths look like .../audioura-worktrees/LOCAL-123
    local task_id
    task_id=$(echo "$cwd" | grep -o 'LOCAL-[0-9]*' | head -1)
    [ -n "$task_id" ] && echo "$task_id" && return 0
  fi
  # Fallback: check the process command line for the task file
  local cmdline
  cmdline=$(ps -o args= -p "$pid" 2>/dev/null)
  local task_id
  task_id=$(echo "$cmdline" | grep -o 'LOCAL-[0-9]*' | head -1)
  [ -n "$task_id" ] && echo "$task_id" && return 0
  echo "unknown"
}

# --- Helper: check if a PID's parent is a live dispatcher worker. ---
# A dispatcher worker is: python3 kiro_dispatcher.py --worker <file>
# A legitimate kiro-cli has such a process as its parent (or grandparent
# through the shell). An orphan has ppid=1 (reparented to launchd) because
# its dispatcher worker died.
parent_is_dispatcher_worker() {
  local pid=$1
  local ppid
  ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  [ -z "$ppid" ] && return 1

  # Walk up at most 3 levels to handle shell intermediaries
  local level=0
  local current_ppid="$ppid"
  while [ "$level" -lt 3 ]; do
    # ppid=1 means reparented to launchd — orphan
    [ "$current_ppid" -eq 1 ] && return 1

    # Check if this ancestor is a dispatcher worker
    local parent_cmd
    parent_cmd=$(ps -o args= -p "$current_ppid" 2>/dev/null)
    if grep -q "kiro_dispatcher.py --worker" <<< "$parent_cmd"; then
      return 0  # legitimate — parent is a dispatcher worker
    fi

    # Move up one level
    current_ppid=$(ps -o ppid= -p "$current_ppid" 2>/dev/null | tr -d ' ')
    [ -z "$current_ppid" ] && return 1
    level=$((level + 1))
  done
  return 1  # exhausted levels without finding a dispatcher worker
}

# --- 1. Reap kiro-cli processes whose dispatcher parent is gone. ---
# An orphan is a kiro-cli process whose parent chain does NOT include a
# live dispatcher worker. We also require MIN_AGE_SECONDS as a backstop.
#
# Safety: never kill zsh (kiro-cli-term) — those are interactive terminals.
# Never kill the kiro_cli_desktop process.
for pid in $(pgrep -f "kiro-cli" 2>/dev/null); do
  # Skip interactive terminals and the desktop app
  cmd=$(ps -o args= -p "$pid" 2>/dev/null)
  grep -q "kiro-cli-term" <<< "$cmd" && continue
  grep -q "kiro_cli_desktop" <<< "$cmd" && continue

  # Skip if parent is a live dispatcher worker (legitimate process)
  if parent_is_dispatcher_worker "$pid"; then
    continue
  fi

  # Orphan detected — check age backstop
  age=$(elapsed_seconds "$pid")
  if [ -z "$age" ] || [ "$age" -lt "$MIN_AGE_SECONDS" ]; then
    continue
  fi

  # Determine which task this belonged to for logging
  task=$(task_for_pid "$pid")

  kill -9 "$pid" 2>/dev/null && \
    echo "$(date -u +%FT%TZ) | reaped orphan kiro pid=$pid age=${age}s task=$task" >> "$LOG"
done

# --- 2. Quarantine a task that keeps dying. ---
# Three deaths means the task is not going to succeed by being retried; it
# needs a human or a smaller scope. Park it outside the dispatcher glob so
# the queue moves on instead of looping.
for f in "$REPO"/new_kiro_session_is_required_*.md; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  # grep -c prints 0 AND exits 1 on no match, so `|| echo 0` would append a
  # second 0 and break the integer test. Force a single clean number.
  deaths=$(grep -c "task=$base | .*worker_died" "$SESSIONS" 2>/dev/null; true)
  deaths=${deaths:-0}
  # Never quarantine a task that is currently running — it may yet succeed.
  running=$(pgrep -f "kiro_dispatcher.py --worker.*$base" | wc -l | tr -d ' ')
  # Nor one that has since SUCCEEDED. The death count is cumulative and never
  # resets, so a task that died three times and then completed would otherwise
  # be quarantined on the very next tick — which happened to LOCAL-113 on
  # 2026-08-01, minutes after it finished. Only the LAST status matters.
  last=$(grep "task=$base" "$SESSIONS" 2>/dev/null | tail -1 | sed 's/^- \([A-Z]*\).*/\1/')
  if [ "$deaths" -ge "$MAX_DEATHS" ] && [ "$running" -eq 0 ] && [ "$last" != "COMPLETED" ]; then
    mv "$f" "$REPO/QUARANTINED_${base}"
    echo "$(date -u +%FT%TZ) | *** QUARANTINED $base after $deaths deaths — needs LEAD ***" \
      >> "$CD/ALERTS.md"
    echo "$(date -u +%FT%TZ) | QUARANTINED $base after $deaths deaths" >> "$LOG"
  fi
done
