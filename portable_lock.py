#!/usr/bin/env python3
"""Cross-platform advisory file locking for the continuous-development tooling.

WHY THIS EXISTS
`kiro_dispatcher.py` and `continuous_dev_lib.py` used `fcntl` directly, which is
Unix-only. On Windows they did not merely misbehave -- they failed at import:

    python kiro_dispatcher.py
    ModuleNotFoundError: No module named 'fcntl'

The lock is not decorative. It is what makes `kiro_sessions_ran.md` the single
source of truth for claiming task files, and the one time claim-tracking went
wrong the dispatcher re-dispatched a task whose agent was still mid-generation
and burned ~35 minutes of live OpenAI and Serper calls reproducing work already
in hand (kiro_dispatcher.py:162-168). A best-effort replacement is not good
enough; this has to actually hold.

ONE CODE PATH, NOT TWO
Both machines import this module and call the same two functions. Forking the
callers per platform would mean the Mac Mini path stops being exercised by any
Windows testing and vice versa.

WINDOWS SEMANTICS THAT DIFFER FROM flock, AND HOW THEY ARE HANDLED
  * `msvcrt.locking` locks a byte range from the CURRENT file position, not the
    whole file. We seek to 0 and lock exactly one byte -- every participant
    agrees on that byte, so it behaves as a whole-file lock. Locking past EOF is
    legal, which matters because the semaphore's slot files are empty.
  * `msvcrt.locking(LK_LOCK)` retries for ~10 seconds and then gives up. That is
    neither "block forever" nor "fail immediately", so it is never used here --
    blocking mode is a retry loop around the non-blocking primitive.
  * A failed Windows lock raises OSError (EACCES / EDEADLOCK), not
    BlockingIOError. Callers already catch BlockingIOError, so it is translated.
  * Windows locks are mandatory rather than advisory, and are released when the
    handle closes. Unlocking the same one-byte range is still done explicitly so
    behaviour matches POSIX for a caller that reuses the handle.
"""
import os
import sys
import time

_WINDOWS = sys.platform.startswith("win")

if _WINDOWS:
    import msvcrt
else:
    import fcntl

# Every participant must lock the SAME byte for the lock to mean anything.
_LOCK_OFFSET = 0
_LOCK_LENGTH = 1

# Windows has no blocking whole-file lock, so blocking mode polls. Fast enough
# that contention is not noticeable, slow enough not to spin a core.
_POLL_SECONDS = 0.05


def lock_exclusive(fh, blocking=True, timeout=None):
    """Take an exclusive lock on `fh`.

    Blocking mode waits (forever by default, or until `timeout` seconds).
    Non-blocking mode raises BlockingIOError immediately if the lock is held,
    on both platforms.
    """
    if not _WINDOWS:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        if blocking and timeout is not None:
            deadline = time.time() + timeout
            while True:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except (BlockingIOError, OSError):
                    if time.time() >= deadline:
                        raise BlockingIOError("timed out waiting for lock")
                    time.sleep(_POLL_SECONDS)
        fcntl.flock(fh, flags)
        return

    deadline = None if timeout is None else time.time() + timeout
    while True:
        try:
            fh.seek(_LOCK_OFFSET)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, _LOCK_LENGTH)
            return
        except OSError as e:
            # EACCES (13) and EDEADLOCK (36) both mean "someone else holds it".
            if not blocking:
                raise BlockingIOError(str(e)) from e
            if deadline is not None and time.time() >= deadline:
                raise BlockingIOError("timed out waiting for lock") from e
            time.sleep(_POLL_SECONDS)


def unlock(fh):
    """Release a lock taken with lock_exclusive. Never raises."""
    try:
        if not _WINDOWS:
            fcntl.flock(fh, fcntl.LOCK_UN)
        else:
            fh.seek(_LOCK_OFFSET)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _LOCK_LENGTH)
    except OSError:
        # Closing the handle releases the lock on both platforms, so a failure
        # here is not worth propagating into a caller's finally block.
        pass


def boot_time():
    """Machine boot epoch as a string, or None. Used for reboot detection.

    macOS reads it from sysctl; Windows derives it from the uptime counter,
    which needs no extra dependency. Both are stable across calls within a boot,
    which is the only property the caller relies on.
    """
    if _WINDOWS:
        try:
            import ctypes

            uptime_ms = ctypes.windll.kernel32.GetTickCount64()
            # Rounded to the minute: GetTickCount64 drifts by milliseconds
            # against wall-clock time, and an unrounded value would look like a
            # reboot on every single tick.
            return str(int((time.time() - uptime_ms / 1000.0) // 60))
        except Exception:
            return None

    import re
    import subprocess

    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5
        ).stdout
        m = re.search(r"sec\s*=\s*(\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def detached_popen_kwargs():
    """Keyword arguments that detach a child so it survives the parent exiting.

    `start_new_session=True` is POSIX-only. Python does not error on Windows --
    it silently ignores it, which would leave every dispatched worker tied to
    the dispatcher's console and killed when a scheduled run ends. That failure
    is invisible until a worker dies halfway through a paid session.
    """
    if not _WINDOWS:
        return {"start_new_session": True}
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    return {"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}


def link_or_copy(src, dst):
    """Point `dst` at `src` without duplicating secrets where possible.

    The .env symlink exists so ~30 worktrees share one source of truth rather
    than each holding a copy of the keys. On Windows an unprivileged symlink
    needs Developer Mode, so a hard link is tried next -- same inode, same
    single-source-of-truth property. A copy is the last resort and says so.
    """
    try:
        dst.symlink_to(src)
        return "symlink"
    except OSError:
        pass
    try:
        os.link(str(src), str(dst))
        return "hardlink"
    except OSError:
        pass
    import shutil

    shutil.copy2(str(src), str(dst))
    return "copy"
