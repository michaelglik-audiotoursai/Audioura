#!/usr/bin/env python3
"""
Shared primitives for the continuous-development control surface documented
in CLAUDE.md ("CONTINUOUS DEVELOPMENT — CONTROL INTERFACE"). Used by both
kiro_dispatcher.py and isolated_test.py so pause/reboot/concurrency behavior
stays consistent between the Kiro-dispatch side and the LEAD-review side.
"""
import os
import re
import subprocess
import time
from pathlib import Path

import portable_lock

def _default_watch_dir():
    """The repo root, found rather than assumed.

    This was hardcoded to ~/Audioura, which is the Mac Mini's layout. On the
    Windows laptop the clone lives under eclipse-workspace\\AudioTours\\development,
    so every invocation needed AUDIOURA_WATCH_DIR set by hand -- easy to forget,
    and forgetting it points the dispatcher at a directory that does not exist.

    Resolution order, first hit wins:
      1. AUDIOURA_WATCH_DIR, for anyone who wants to be explicit
      2. ~/Audioura if it exists -- so the Mac Mini is completely unaffected
      3. the directory this file sits in, which IS the repo root on the laptop
    """
    explicit = os.environ.get("AUDIOURA_WATCH_DIR")
    if explicit:
        return Path(explicit)
    mac_default = Path.home() / "Audioura"
    if mac_default.is_dir():
        return mac_default
    return Path(__file__).resolve().parent


WATCH_DIR = _default_watch_dir()
CONTROL_DIR = WATCH_DIR / ".continuous_dev"
PAUSE_FILE = CONTROL_DIR / "PAUSE"
STATUS_FILE = CONTROL_DIR / "STATUS.md"
BOOT_FILE = CONTROL_DIR / "last_boot.txt"


def ensure_control_dir():
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)


def is_paused():
    return PAUSE_FILE.exists()


def get_boot_time():
    """Returns the machine's boot epoch (as a string), or None if unavailable.

    Was sysctl-only, which returns None on Windows -- and a None boot time means
    check_and_record_reboot() can never fire, so reboot recovery silently never
    happens rather than failing visibly. portable_lock.boot_time() handles both.
    """
    return portable_lock.boot_time()


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
                    portable_lock.lock_exclusive(fh, blocking=False)
                    self._fh = fh
                    return True
                except BlockingIOError:
                    fh.close()
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(poll_seconds)

    def release(self):
        if self._fh is not None:
            portable_lock.unlock(self._fh)
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
            portable_lock.lock_exclusive(fh, blocking=False)
            portable_lock.unlock(fh)
        except BlockingIOError:
            held += 1
        finally:
            fh.close()
    return held
