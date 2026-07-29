#!/usr/bin/env python3
"""
Shared primitives for the continuous-development control surface documented
in CLAUDE.md ("CONTINUOUS DEVELOPMENT — CONTROL INTERFACE"). Used by both
kiro_dispatcher.py and isolated_test.py so pause/reboot/concurrency behavior
stays consistent between the Kiro-dispatch side and the LEAD-review side.
"""
import fcntl
import re
import subprocess
import time
from pathlib import Path

WATCH_DIR = Path.home() / "Audioura"
CONTROL_DIR = WATCH_DIR / ".continuous_dev"
PAUSE_FILE = CONTROL_DIR / "PAUSE"
STATUS_FILE = CONTROL_DIR / "STATUS.md"
BOOT_FILE = CONTROL_DIR / "last_boot.txt"


def ensure_control_dir():
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)


def is_paused():
    return PAUSE_FILE.exists()


def get_boot_time():
    """Returns the machine's boot epoch (as a string) via sysctl, or None if unavailable."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5
        ).stdout
        m = re.search(r"sec\s*=\s*(\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def check_and_record_reboot():
    """
    Returns True if a reboot was detected since the last recorded boot time
    (i.e. current boot time differs from what's on disk), then updates the
    recorded value regardless. First-ever run (no recorded value) is NOT
    treated as a reboot.
    """
    ensure_control_dir()
    current = get_boot_time()
    previous = BOOT_FILE.read_text().strip() if BOOT_FILE.exists() else None
    rebooted = previous is not None and current is not None and current != previous
    if current is not None:
        BOOT_FILE.write_text(current)
    return rebooted


class Semaphore:
    """
    Cross-process counting semaphore using flock on a fixed set of slot
    files. No daemon, no shared memory -- just N lockable files on disk.
    Safe to use from unrelated processes (kiro_dispatcher.py workers,
    isolated_test.py runs, review agents) as long as they agree on `name`
    and `max_slots`.
    """

    def __init__(self, name, max_slots):
        self.dir = CONTROL_DIR / f"{name}_slots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_slots = max_slots
        self._fh = None

    def acquire(self, poll_seconds=2, wait_seconds=None):
        """Blocks (polling) until a slot is free. wait_seconds=None waits forever."""
        deadline = None if wait_seconds is None else time.time() + wait_seconds
        while True:
            for i in range(self.max_slots):
                path = self.dir / f"slot_{i}.lock"
                fh = open(path, "w")
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._fh = fh
                    return True
                except BlockingIOError:
                    fh.close()
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(poll_seconds)

    def release(self):
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def active_slot_count(name, max_slots):
    """Best-effort count of currently-held slots, for status reporting."""
    held = 0
    slot_dir = CONTROL_DIR / f"{name}_slots"
    if not slot_dir.is_dir():
        return 0
    for i in range(max_slots):
        path = slot_dir / f"slot_{i}.lock"
        if not path.exists():
            continue
        fh = open(path, "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
        except BlockingIOError:
            held += 1
        finally:
            fh.close()
    return held
