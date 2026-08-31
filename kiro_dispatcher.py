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
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import continuous_dev_lib as cdl
import portable_lock

WATCH_DIR = cdl.WATCH_DIR
# Worktree root. On Windows the default path is long enough that `git worktree
# add` fails PART WAY THROUGH checkout on this repo's deeply-nested generated
# tour directories ("Filename too long"), leaving a half-created worktree that
# looks like a success to anything checking only the exit code. Verified
# 2026-08-18: it only succeeds from a short root. Overridable everywhere; the
# macOS default is unchanged.
WORKTREE_BASE = Path(
    os.environ.get("AUDIOURA_WORKTREE_BASE")
    or (Path("C:/adev-wt") if sys.platform.startswith("win")
        else WATCH_DIR.parent / "audioura-worktrees")
)
# Long paths must ALSO be enabled per-command; a short root alone is not enough.
GIT_LONGPATHS = ["-c", "core.longpaths=true"]
LOG_FILE = WATCH_DIR / "kiro_sessions_ran.md"
LOCK_FILE = WATCH_DIR / ".kiro_dispatcher.lock"
SESSION_LOG_DIR = WATCH_DIR / "kiro_session_logs"
TASK_FILE_RE = re.compile(r"^new_kiro_session_is_required_(.+)\.md$")
MAX_RUNTIME_SECONDS = 60 * 60  # kill a runaway headless session after 1 hour
# Reduced from 3 to 2 on 2026-08-01. Swap hit 91% (2783MB of 3072MB) with
# Docker plus three workers; container builds began failing with
# DeadlineExceeded and LOCAL-112 died four times, silently, before it could
# write a log. Two workers plus Docker is what this Mac Mini sustains. See D32.
MAX_CONCURRENT_KIRO_SESSIONS = 2
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
STATUS_LINE_RE = re.compile(r"^-\s*(\w+)\s*\|\s*task=(\S+)")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def locked_append(text):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.touch(exist_ok=True)
    with open(LOCK_FILE, "r+") as lock_fh:
        portable_lock.lock_exclusive(lock_fh)
        try:
            if not LOG_FILE.exists():
                LOG_FILE.write_text(
                    "# Kiro session dispatch log\n\n"
                    "One line per lifecycle event. Do not hand-edit while the "
                    "dispatcher may be running -- appends are lock-protected, "
                    "manual edits are not.\n\n"
                )
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(text if text.endswith("\n") else text + "\n")
        finally:
            portable_lock.unlock(lock_fh)


def last_status_for(task_filename):
    """Returns (status, full_line) of the most recent log line for this task, or (None, None)."""
    if not LOG_FILE.exists():
        return None, None
    last = (None, None)
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
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


def pid_is_alive(pid):
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


PID_FROM_STARTED_RE = re.compile(r"dispatcher_pid=(\d+)")


def check_worker_liveness():
    """
    For any task whose last record is STARTED, verify the recorded
    dispatcher_pid is still alive. If it is not, append ABANDONED so the
    task re-dispatches. The worktree is reused on retry, so in-flight work
    is preserved — do not delete it.

    This runs every dispatch tick (not only on reboot detection) so a worker
    that dies mid-flight between reboots is caught within one tick interval.
    """
    abandoned = []
    if not LOG_FILE.exists():
        return abandoned

    for task_path in find_task_files():
        status, line = last_status_for(task_path.name)
        if status != "STARTED":
            continue
        # Extract the PID from the STARTED line
        pid_m = PID_FROM_STARTED_RE.search(line or "")
        if not pid_m:
            continue
        pid = int(pid_m.group(1))
        if not pid_is_alive(pid):
            # [D352] The dispatcher_pid is a bookkeeping wrapper; the kiro-cli
            # agent is the actual work, and it SURVIVES the wrapper's death.
            # Testing the wrapper alone marked LOCAL-415 abandoned at 14:22
            # while its agent was mid-generation, re-dispatched it, and ran a
            # duplicate concurrently with LOCAL-417 -- ~35 minutes of live
            # OpenAI and Serper calls spent reproducing work already in hand.
            if worker_process_alive(task_path.name):
                continue
            locked_append(
                f"- ABANDONED | task={task_path.name} | at={now_iso()} | "
                f"reason=worker_died | dead_pid={pid}"
            )
            abandoned.append(task_path.name)
    return abandoned


def worker_process_alive(task_filename):
    """
    [D352] True if a kiro-cli agent for this task is still running.

    The agent is forked detached and outlives its dispatcher, so liveness must
    be asked of the agent. Matched on the task id (e.g. "LOCAL-415") because
    the task text is embedded in the agent's command line.
    """
    m = TASK_FILE_RE.match(task_filename)
    task_id = m.group(1) if m else task_filename
    try:
        result = subprocess.run(
            ["pgrep", "-f", task_id],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        # Cannot prove it is dead -> do not abandon. Re-dispatching live work
        # is far more expensive than leaving a dead task undetected one tick.
        return True


def render_status(candidates, launched, paused, reboot_recovered, liveness_abandoned=None):
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
    if liveness_abandoned:
        lines.append(
            f"- Dead workers detected this tick: {', '.join(liveness_abandoned)}"
        )
    block = "\n".join(lines)

    existing = cdl.STATUS_FILE.read_text(encoding="utf-8") if cdl.STATUS_FILE.exists() else (
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
    cdl.STATUS_FILE.write_text(updated, encoding="utf-8")


def dispatch():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        locked_append("")  # creates the file with its header, no-op otherwise

    reboot_recovered = []
    if cdl.check_and_record_reboot():
        reboot_recovered = recover_abandoned_tasks()

    # Liveness check: detect workers that died mid-flight (not only on reboot).
    liveness_abandoned = check_worker_liveness()

    paused = cdl.is_paused()
    candidates = find_task_files()

    if paused:
        render_status(candidates, [], paused=True, reboot_recovered=reboot_recovered,
                      liveness_abandoned=liveness_abandoned)
        print("Paused -- skipping dispatch.")
        return

    launched = []
    for task_path in candidates:
        if already_claimed(task_path.name):
            continue

        # Parse the base branch from the task file for the STARTED record.
        try:
            prompt_text = task_path.read_text(encoding="utf-8")
        except OSError:
            continue
        base = base_branch_for(prompt_text)

        started_at = now_iso()
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(task_path)]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Detach so the worker survives the dispatcher exiting. This is NOT
            # one flag: start_new_session is POSIX-only and Windows ignores it
            # SILENTLY, which would tie every worker to the scheduled run that
            # spawned it and kill it mid-session. See portable_lock.
            **portable_lock.detached_popen_kwargs(),
            cwd=str(WATCH_DIR),
        )
        locked_append(
            f"- STARTED   | task={task_path.name} | at={started_at} | "
            f"base={base} | dispatcher_pid={proc.pid}"
        )
        launched.append(task_path.name)

    render_status(candidates, launched, paused=False, reboot_recovered=reboot_recovered,
                  liveness_abandoned=liveness_abandoned)

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
            text=True, encoding="utf-8", errors="replace",
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
BASE_LINE_RE = re.compile(r"\*\*Base:\*\*\s*(\S+)")


def branch_name_for(task_id, prompt):
    m = BRANCH_LINE_RE.search(prompt)
    if m:
        return m.group(1)
    return f"kiro/{task_id.lower()}"


def base_branch_for(prompt):
    """
    Extracts the **Base:** field from a task file header. Defaults to
    'storied' when absent, so every existing task file keeps working.
    """
    m = BASE_LINE_RE.search(prompt)
    if m:
        return m.group(1)
    return "storied"


def validate_base_branch(base, cwd):
    """
    Verifies the base branch exists locally. Returns (ok, error_message).
    A typo must fail loudly at dispatch, not silently produce a worktree
    off the wrong branch.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", base],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return False, (
            f"Base branch '{base}' does not exist. "
            f"Available local branches: "
            + subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
            ).stdout.strip().replace("\n", ", ")
        )
    return True, None


def resolve_base_sha(base, cwd):
    """Return the sha the base branch points at right now, or '' if unknown."""
    r = subprocess.run(
        ["git", "rev-parse", "--short", base],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def base_preamble(base, base_sha):
    """
    Prepended to every dispatched prompt.

    [LOCAL-418 review, D358] LOCAL-418 branched from `origin/storied` and so did
    its work on a tree **18 commits stale** -- it never saw the 410-415 chain,
    and it re-created `run_mfa_unbound_eval.py` from scratch because the
    committed one did not exist at its base. The task file said "branch off
    `storied`", the agent resolved that to `origin/storied`, and nothing
    complained.

    `origin/storied` is stale BY DESIGN: local `storied` is held unpushed behind
    Michael's iPhone field-test gate, so the remote falls further behind every
    day. An agent that branches from origin is silently working in the past.

    The worktree the agent is handed is ALREADY on the correct commit, so the
    right move is always to branch from HEAD.
    """
    return (
        "# BASE — read before your first git command\n"
        "\n"
        f"Your worktree is already checked out at the correct base: **{base} = {base_sha}**.\n"
        "\n"
        "Create your branch from **HEAD**:\n"
        "\n"
        "    git checkout -b <branch-name>\n"
        "\n"
        "**Never branch from `origin/anything`.** `origin/storied` is many commits\n"
        "behind local `storied` — local is held unpushed behind a field-test gate.\n"
        "Branching from origin silently puts your work on a stale tree, and every\n"
        "live run you make there measures old code (D358).\n"
        "\n"
        f"Verify before you commit: `git merge-base --is-ancestor {base_sha} HEAD`\n"
        "must exit 0. If it does not, you are on the wrong base — fix it first.\n"
        "\n"
        "---\n"
        "\n"
    )


def setup_worktree(task_id, branch, base):
    """
    Isolates one task's work in its own git worktree + branch, checked out
    from the specified base branch. This is the fix for a real collision
    found 2026-07-29: two concurrent worker() runs sharing WATCH_DIR as
    their cwd mixed their file edits together mid-flight. Each task gets
    its own directory now -- no shared mutable working-tree state between
    tasks.

    The base branch is read from the task file's **Base:** field (defaults
    to 'storied' when absent). This fixes the hardcoded-base bug that
    caused subscribed-track tasks to silently branch from storied.
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
        cmd = ["git"] + GIT_LONGPATHS + ["worktree", "add", str(path), branch]
    else:
        cmd = ["git"] + GIT_LONGPATHS + ["worktree", "add", "-b", branch, str(path), base]
    subprocess.run(cmd, cwd=str(WATCH_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)

    # [LOCAL-412 review] Link .env into the worktree.
    # .env is gitignored, so `git worktree add` never brings it across and every
    # task landed in a tree with no OPENAI_API_KEY / SERP_API_KEY. Tasks then
    # honestly reported "SERP_API_KEY not available" and downgraded a live
    # acceptance run to an offline simulation -- which is exactly the evidence
    # the live-artifact gate exists to prevent. A symlink (not a copy) keeps one
    # source of truth and stops secrets proliferating into ~30 worktrees.
    env_src = WATCH_DIR / ".env"
    env_dst = path / ".env"
    if env_src.exists() and not env_dst.exists():
        try:
            # Windows refuses unprivileged symlinks unless Developer Mode is on,
            # so fall back to a hard link -- same inode, so the "one source of
            # truth" property the symlink existed for is preserved. A copy is
            # the last resort and is reported, because it does duplicate secrets.
            how = portable_lock.link_or_copy(env_src, env_dst)
            if how == "copy":
                print(f"[dispatcher] NOTE: .env COPIED into {path} (no symlink or "
                      f"hardlink possible) -- secrets are now duplicated there")
        except OSError as e:
            print(f"[dispatcher] WARNING: could not link .env into {path}: {e}")

    return path


def export_dotenv_into_environ():
    """[LOCAL-442 review] Export .env into this process's environment.

    LOCAL-412 symlinked .env INTO each worktree, which fixed file access but not
    process environment: the launchd tick's env has no OPENAI_API_KEY, so a task
    running `python3 -c "..."` still saw os.environ empty and every module that
    reads os.environ.get('OPENAI_API_KEY') fell into its no-key branch. LOCAL-442
    then reported "no OPENAI_API_KEY available in this worktree environment" and
    hand-wrote its acceptance fixtures instead of capturing live verdicts -- the
    file was right there, symlinked, unread. Exporting here means the kiro-cli
    child and everything it spawns inherit the keys without knowing the incantation.

    Existing environment always wins, so an explicitly-set key is never clobbered.
    """
    env_file = WATCH_DIR / ".env"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as e:
        print(f"[dispatcher] WARNING: could not export .env: {e}")


def worker(task_path_str):
    export_dotenv_into_environ()
    task_path = Path(task_path_str)
    task_filename = task_path.name
    m = TASK_FILE_RE.match(task_filename)
    task_id = m.group(1) if m else task_filename

    if not task_path.exists():
        locked_append(f"- FAILED    | task={task_filename} | reason=file_missing_at_worker_start")
        return

    prompt = task_path.read_text(encoding="utf-8")
    if not prompt.strip():
        locked_append(f"- FAILED    | task={task_filename} | reason=empty_task_file")
        return

    branch = branch_name_for(task_id, prompt)
    base = base_branch_for(prompt)

    # Validate the base branch exists before creating a worktree.
    # A typo must fail loudly, not silently produce a worktree off the wrong branch.
    ok, err_msg = validate_base_branch(base, WATCH_DIR)
    if not ok:
        locked_append(
            f"- FAILED    | task={task_filename} | reason=bad_base_branch: {err_msg[:200]}"
        )
        return

    base_sha = resolve_base_sha(base, WATCH_DIR)

    try:
        worktree_path = setup_worktree(task_id, branch, base)
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
        full_prompt = base_preamble(base, base_sha) + prompt
        cmd = ["kiro-cli", "chat", "--trust-all-tools", "--no-interactive", full_prompt]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
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

    session_log_path.write_text(strip_ansi(raw_output), encoding="utf-8", errors="replace")
    duration_s = int(time.monotonic() - start_time)

    session_id = None
    if status == "COMPLETED":
        session_id = find_session_id(full_prompt.strip(), worktree_path)

    # [D358] Report the base the work ACTUALLY sits on, not the one we asked for.
    # LOCAL-418's line said base=storied while its commits hung off origin/storied,
    # 18 commits back. The branch field is likewise a guess -- the agent names its
    # own branch -- so record what the worktree really has.
    real_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(worktree_path), capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.strip() or branch
    stale = ""
    if base_sha:
        on_base = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_sha, "HEAD"],
            cwd=str(worktree_path), capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).returncode
        if on_base != 0:
            behind = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..{base}"],
                cwd=str(worktree_path), capture_output=True, text=True, encoding="utf-8", errors="replace",
            ).stdout.strip() or "?"
            stale = f" | *** STALE BASE: work is {behind} commits behind {base} ***"

    locked_append(
        f"- {status:<10}| task={task_filename} | id=T{task_id} | "
        f"branch={real_branch} | base={base}@{base_sha or '?'} | worktree={worktree_path} | "
        f"session={session_id or 'unknown'} | started={start_iso} | "
        f"duration={duration_s}s | exit={exit_code} | log={session_log_path}{stale}"
    )


def kiro_login_state():
    """(logged_in, detail). Asks the CLI itself rather than inferring from config.

    CORRECTION 2026-08-28: an earlier version of this guard required a
    KIRO_API_KEY environment variable. That was wrong. `kiro-cli login --help`
    offers only Builder ID (--license free), Identity Center (--license pro),
    social providers and a device flow -- there is NO API-key authentication in
    this CLI, and KIRO_API_KEY appears nowhere in the codebase. The guard would
    have refused to start on a machine that was correctly logged in.

    Auth is a stored login session, which is why the detached headless workers
    work at all: they inherit the machine's session, not a variable.
    """
    exe = shutil.which("kiro-cli")
    if not exe:
        return False, "kiro-cli is not on PATH"
    try:
        r = subprocess.run([exe, "whoami"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:
        return False, f"could not run `kiro-cli whoami`: {e}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0 and "not logged in" not in out.lower():
        return True, out.splitlines()[0] if out else "logged in"
    return False, out.splitlines()[0] if out else "not logged in"


def require_kiro_login():
    """Refuse to start unless this machine has a usable kiro-cli login.

    Without it every forked worker starts, fails to authenticate and writes a
    FAILED line -- burning a concurrency slot and a worktree per task to
    discover one missing login. Failing here costs one message instead.
    """
    export_dotenv_into_environ()  # still needed: OPENAI_API_KEY, SERP_API_KEY, ...
    ok, detail = kiro_login_state()
    if ok:
        return
    sys.exit(
        f"[dispatcher] REFUSING TO START: {detail}.\n"
        "  Headless `kiro-cli chat --no-interactive` runs off this machine's stored\n"
        "  login session. Log in once, interactively:\n"
        "      kiro-cli login --license free          # Builder ID\n"
        "      kiro-cli login --license pro           # Identity Center\n"
        "      kiro-cli login --use-device-flow       # if browser redirect fails\n"
        "  Confirm with `kiro-cli whoami`, then re-run this dispatcher."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", metavar="TASK_FILE", help=argparse.SUPPRESS)
    parser.add_argument("--preflight", action="store_true",
                        help="Check this machine can dispatch, then exit without dispatching.")
    args = parser.parse_args()

    if args.preflight:
        preflight()
        return

    require_kiro_login()

    if args.worker:
        worker(args.worker)
    else:
        dispatch()


def preflight():
    """Report whether this machine can dispatch, WITHOUT forking anything.

    Exists because every other way of finding out costs a real dispatch, and a
    real dispatch costs money. Safe to run anywhere, any time.
    """
    ok = True

    def check(label, passed, detail=""):
        nonlocal ok
        if not passed:
            ok = False
        print(f"  [{'OK ' if passed else 'XX '}] {label}{(' -- ' + detail) if detail else ''}")

    print(f"[dispatcher] preflight on {sys.platform}, python {sys.version.split()[0]}")
    check("file locking imports and works", _selftest_lock())
    check("watch dir exists", WATCH_DIR.is_dir(), str(WATCH_DIR))
    check("watch dir is a git repo", (WATCH_DIR / ".git").exists(), str(WATCH_DIR / ".git"))
    check("worktree root is writable", _selftest_worktree_base(), str(WORKTREE_BASE))
    exe = shutil.which("kiro-cli")
    check("kiro-cli on PATH", exe is not None,
          exe or "install: irm https://cli.kiro.dev/install.ps1 | iex")
    logged_in, detail = kiro_login_state()
    check("kiro-cli logged in", logged_in,
          detail if logged_in else f"{detail} -- run: kiro-cli login --license free")
    export_dotenv_into_environ()
    print(f"[dispatcher] preflight {'PASSED' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


def _selftest_lock():
    """Take and release a real lock. Proves the platform primitive works here."""
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "preflight.lock"
            p.touch()
            with open(p, "r+") as a:
                portable_lock.lock_exclusive(a)
                try:
                    with open(p, "r+") as b:
                        try:
                            portable_lock.lock_exclusive(b, blocking=False)
                            portable_lock.unlock(b)
                            return False  # a second holder got in: the lock is a no-op
                        except BlockingIOError:
                            pass
                finally:
                    portable_lock.unlock(a)
        return True
    except Exception:
        return False


def _selftest_worktree_base():
    try:
        WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
        probe = WORKTREE_BASE / ".preflight_probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
