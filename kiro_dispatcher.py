#!/usr/bin/env python3
"""
Watches for new_kiro_session_is_required_*.md task files and launches a
headless `kiro-cli chat` session per unclaimed file, concurrently (bounded
by a concurrency semaphore -- see continuous_dev_lib.py).

Two modes, same script:
  - dispatch (default): scan for unclaimed task files, claim + fork each as
    a detached worker, return immediately. Safe to run on a schedule (cron/
    launchd) -- overlapping invocations and already-claimed files are both
    handled via kiro_sessions_ran.md acting as the single source of truth.
  - --worker <file>: internal. Runs kiro-cli synchronously for one task
    file, captures output, and appends a COMPLETED/FAILED/TIMEOUT record.

Control surface (PAUSE file, STATUS.md, reboot recovery) is documented in
CLAUDE.md under "CONTINUOUS DEVELOPMENT — CONTROL INTERFACE".

Usage:
  python3 kiro_dispatcher.py                 # dispatch mode (what cron calls)
  python3 kiro_dispatcher.py --worker <path>  # do not call this directly
"""
import argparse
import fcntl
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import continuous_dev_lib as cdl

WATCH_DIR = cdl.WATCH_DIR
WORKTREE_BASE = WATCH_DIR.parent / "audioura-worktrees"
LOG_FILE = WATCH_DIR / "kiro_sessions_ran.md"
LOCK_FILE = WATCH_DIR / ".kiro_dispatcher.lock"
SESSION_LOG_DIR = WATCH_DIR / "kiro_session_logs"
TASK_FILE_RE = re.compile(r"^new_kiro_session_is_required_(.+)\.md$")
MAX_RUNTIME_SECONDS = 60 * 60  # kill a runaway headless session after 1 hour
MAX_CONCURRENT_KIRO_SESSIONS = 3
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
STATUS_LINE_RE = re.compile(r"^-\s*(\w+)\s*\|\s*task=(\S+)")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def locked_append(text):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch(exist_ok=True)
    with open(LOCK_FILE, "r+") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            if not LOG_FILE.exists():
                LOG_FILE.write_text(
                    "# Kiro session dispatch log\n\n"
                    "One line per lifecycle event. Do not hand-edit while the "
                    "dispatcher may be running -- appends are lock-protected, "
                    "manual edits are not.\n\n"
                )
            with open(LOG_FILE, "a") as fh:
                fh.write(text if text.endswith("\n") else text + "\n")
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def last_status_for(task_filename):
    """Returns (status, full_line) of the most recent log line for this task, or (None, None)."""
    if not LOG_FILE.exists():
        return None, None
    last = (None, None)
    for line in LOG_FILE.read_text().splitlines():
        m = STATUS_LINE_RE.match(line)
        if m and m.group(2) == task_filename:
            last = (m.group(1), line)
    return last


def already_claimed(task_filename):
    """
    Claimed = currently in flight or already ran to a terminal state.
    ABANDONED (reboot recovery) is deliberately NOT claimed -- it should be
    picked up again fresh.
    """
    status, _ = last_status_for(task_filename)
    return status in ("STARTED", "COMPLETED", "FAILED", "TIMEOUT")


def find_task_files():
    if not WATCH_DIR.is_dir():
        return []
    matches = []
    for p in sorted(WATCH_DIR.glob("new_kiro_session_is_required_*.md")):
        if TASK_FILE_RE.match(p.name):
            matches.append(p)
    return matches


def recover_abandoned_tasks():
    """
    Called once per dispatch tick after a reboot is detected. Any task whose
    last known status is STARTED (i.e. a worker was forked but never reached
    a terminal state) had its process die with the reboot -- mark it
    ABANDONED so it's eligible for re-dispatch. The task file itself was
    never touched, so nothing is lost, only the in-flight attempt.
    """
    recovered = []
    for task_path in find_task_files():
        status, _ = last_status_for(task_path.name)
        if status == "STARTED":
            locked_append(
                f"- ABANDONED | task={task_path.name} | at={now_iso()} | "
                f"reason=reboot_detected_mid_flight"
            )
            recovered.append(task_path.name)
    return recovered


def render_status(candidates, launched, paused, reboot_recovered):
    cdl.ensure_control_dir()
    lines = [
        f"_Last dispatch tick: {now_iso()}_",
        "",
        f"- Paused: {'YES' if paused else 'no'}",
        f"- Active kiro-cli sessions: {cdl.active_slot_count('kiro_dispatch', MAX_CONCURRENT_KIRO_SESSIONS)} / {MAX_CONCURRENT_KIRO_SESSIONS}",
        f"- Task files known: {len(candidates)}",
        f"- Newly dispatched this tick: {len(launched)}" + (f" ({', '.join(launched)})" if launched else ""),
    ]
    if reboot_recovered:
        lines.append(
            f"- Reboot detected this tick -- re-armed for redispatch: {', '.join(reboot_recovered)}"
        )
    block = "\n".join(lines)

    existing = cdl.STATUS_FILE.read_text() if cdl.STATUS_FILE.exists() else (
        "# Continuous Development Status\n\n"
        "<!-- DISPATCH STATUS START -->\n<!-- DISPATCH STATUS END -->\n\n"
        "<!-- REVIEW STATUS START -->\n(no review activity recorded yet)\n<!-- REVIEW STATUS END -->\n"
    )
    new_dispatch_block = f"<!-- DISPATCH STATUS START -->\n{block}\n<!-- DISPATCH STATUS END -->"
    updated = re.sub(
        r"<!-- DISPATCH STATUS START -->.*?<!-- DISPATCH STATUS END -->",
        new_dispatch_block,
        existing,
        flags=re.DOTALL,
    )
    cdl.STATUS_FILE.write_text(updated)


def dispatch():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        locked_append("")  # creates the file with its header, no-op otherwise

    reboot_recovered = []
    if cdl.check_and_record_reboot():
        reboot_recovered = recover_abandoned_tasks()

    paused = cdl.is_paused()
    candidates = find_task_files()

    if paused:
        render_status(candidates, [], paused=True, reboot_recovered=reboot_recovered)
        print("Paused -- skipping dispatch.")
        return

    launched = []
    for task_path in candidates:
        if already_claimed(task_path.name):
            continue

        started_at = now_iso()
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(task_path)]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach: survives the dispatcher process exiting
            cwd=str(WATCH_DIR),
        )
        locked_append(
            f"- STARTED   | task={task_path.name} | at={started_at} | "
            f"dispatcher_pid={proc.pid}"
        )
        launched.append(task_path.name)

    render_status(candidates, launched, paused=False, reboot_recovered=reboot_recovered)

    if launched:
        print(f"Dispatched {len(launched)} new task(s): {', '.join(launched)}")
    else:
        print("Nothing new.")


def strip_ansi(text):
    return ANSI_RE.sub("", text)


def find_session_id(prompt_title_prefix, cwd):
    try:
        out = subprocess.run(
            ["kiro-cli", "chat", "--list-sessions", "--format", "json"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        data = json.loads(out)
    except Exception:
        return None
    best = None
    for entry in data:
        if entry.get("cwd") != str(cwd):
            continue
        for sess in entry.get("sessions", []):
            title = sess.get("title", "")
            if title.startswith(prompt_title_prefix[:80]):
                if best is None or sess.get("updatedAt", "") > best.get("updatedAt", ""):
                    best = sess
    return best.get("sessionId") if best else None


BRANCH_LINE_RE = re.compile(r"\*\*Branch:\*\*\s*(\S+)")


def branch_name_for(task_id, prompt):
    m = BRANCH_LINE_RE.search(prompt)
    if m:
        return m.group(1)
    return f"kiro/{task_id.lower()}"


def setup_worktree(task_id, branch):
    """
    Isolates one task's work in its own git worktree + branch, checked out
    from current storied HEAD. This is the fix for a real collision found
    2026-07-29: two concurrent worker() runs sharing WATCH_DIR as their cwd
    mixed their file edits together mid-flight. Each task gets its own
    directory now -- no shared mutable working-tree state between tasks.
    """
    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
    path = WORKTREE_BASE / task_id
    if path.exists():
        return path  # reused from a prior attempt (e.g. a bounce/retry)

    branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=str(WATCH_DIR), capture_output=True,
    ).returncode == 0

    if branch_exists:
        cmd = ["git", "worktree", "add", str(path), branch]
    else:
        cmd = ["git", "worktree", "add", "-b", branch, str(path), "storied"]
    subprocess.run(cmd, cwd=str(WATCH_DIR), capture_output=True, text=True, check=True)
    return path


def worker(task_path_str):
    task_path = Path(task_path_str)
    task_filename = task_path.name
    m = TASK_FILE_RE.match(task_filename)
    task_id = m.group(1) if m else task_filename

    if not task_path.exists():
        locked_append(f"- FAILED    | task={task_filename} | reason=file_missing_at_worker_start")
        return

    prompt = task_path.read_text()
    if not prompt.strip():
        locked_append(f"- FAILED    | task={task_filename} | reason=empty_task_file")
        return

    branch = branch_name_for(task_id, prompt)
    try:
        worktree_path = setup_worktree(task_id, branch)
    except subprocess.CalledProcessError as e:
        locked_append(
            f"- FAILED    | task={task_filename} | reason=worktree_setup_failed: {e.stderr.strip()[:200]}"
        )
        return

    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts_slug = datetime.now().strftime("%Y%m%dT%H%M%S")
    session_log_path = SESSION_LOG_DIR / f"{task_id}_{ts_slug}.log"

    sem = cdl.Semaphore("kiro_dispatch", MAX_CONCURRENT_KIRO_SESSIONS)
    sem.acquire()  # blocks (polling) until one of the concurrent slots frees up
    try:
        start_time = time.monotonic()
        start_iso = now_iso()
        cmd = ["kiro-cli", "chat", "--trust-all-tools", "--no-interactive", prompt]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=MAX_RUNTIME_SECONDS,
            )
            exit_code = result.returncode
            raw_output = result.stdout + result.stderr
            status = "COMPLETED" if exit_code == 0 else "FAILED"
        except subprocess.TimeoutExpired as e:
            exit_code = -1
            raw_output = (e.stdout or "") + (e.stderr or "")
            status = "TIMEOUT"
    finally:
        sem.release()

    session_log_path.write_text(strip_ansi(raw_output))
    duration_s = int(time.monotonic() - start_time)

    session_id = None
    if status == "COMPLETED":
        session_id = find_session_id(prompt.strip(), worktree_path)

    locked_append(
        f"- {status:<10}| task={task_filename} | id=T{task_id} | "
        f"branch={branch} | worktree={worktree_path} | "
        f"session={session_id or 'unknown'} | started={start_iso} | "
        f"duration={duration_s}s | exit={exit_code} | log={session_log_path}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", metavar="TASK_FILE", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.worker:
        worker(args.worker)
    else:
        dispatch()


if __name__ == "__main__":
    main()
