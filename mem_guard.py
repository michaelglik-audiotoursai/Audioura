"""mem_guard.py — LOCAL-848: cheap, always-on per-phase RSS guard.

The tour generator OOM-killed on Cloud Run (512 MiB) during museum tours
("Memory limit of 512 MiB exceeded with 531 MiB used", gen 00023-9zz / 00016-62s).
There was no per-phase memory signal in the logs, so the trend was invisible.

This module gives two things:

  1. ``read_rss_mib()`` — a CHEAP resident-set-size reader (no psutil dependency).
     On Linux it reads ``/proc/self/statm`` (one tiny file read); elsewhere it
     falls back to ``resource.getrusage`` (ru_maxrss, a high-water mark). It never
     raises — a failure returns 0.0 so the caller can log and move on.

  2. ``PeakTracker`` — accumulates the peak RSS seen, overall and per labelled
     phase, from samples taken at phase boundaries (and optionally more often).
     ``PhaseTimer`` (phase_timer.py) samples it at every start()/end(), so the
     cloud logs show one ``[LOCAL-848] peak RSS <phase> <MiB>`` line per phase
     plus a final ``[LOCAL-848] peak RSS process <MiB>`` summary.

An optional tracemalloc snapshot hook (``maybe_snapshot``) is gated behind the
``LOCAL848_TRACEMALLOC`` env var so it is OFF in production (tracemalloc roughly
doubles allocation cost) and only runs during deliberate profiling.

Design constraints (why it is safe to leave on permanently):
  * no third-party imports — stdlib only;
  * one ``/proc/self/statm`` read per phase boundary (~10 boundaries/tour);
  * every public function swallows its own errors and degrades to a no-op.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

__all__ = [
    "read_rss_mib",
    "PeakTracker",
    "get_tracker",
    "reset_tracker",
    "maybe_snapshot",
    "tracemalloc_enabled",
    "release_memory",
    "malloc_trim",
]

# Page size for /proc/self/statm (values are in pages). 4096 on virtually every
# Linux; resolved once at import.
try:
    _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")  # type: ignore[attr-defined]
    if not _PAGE_SIZE or _PAGE_SIZE <= 0:
        _PAGE_SIZE = 4096
except (ValueError, AttributeError, OSError):
    _PAGE_SIZE = 4096

_MIB = 1024.0 * 1024.0


def read_rss_mib() -> float:
    """Return the current process RSS in MiB. Cheap and best-effort.

    Linux: read field 2 (resident pages) of /proc/self/statm × page size.
    Fallback: resource.getrusage(RUSAGE_SELF).ru_maxrss — a high-water mark, in
    KiB on Linux and in BYTES on macOS/BSD (we normalise by platform). Returns
    0.0 if nothing works; never raises.
    """
    # Primary: Linux /proc — a true *current* RSS (what the cgroup OOM killer
    # watches), not a high-water mark.
    try:
        with open("/proc/self/statm", "r") as fh:
            fields = fh.readline().split()
        if len(fields) >= 2:
            resident_pages = int(fields[1])
            return (resident_pages * _PAGE_SIZE) / _MIB
    except (OSError, ValueError, IndexError):
        pass

    # Fallback: ru_maxrss (high-water mark). Units differ by platform.
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            # macOS reports bytes.
            return ru / _MIB
        # Linux/BSD report kilobytes.
        return ru / 1024.0
    except Exception:
        return 0.0


class PeakTracker:
    """Accumulate peak RSS overall and per labelled phase.

    Thread-safety: the orchestrating phase runs start()/end() from a single
    thread, so plain dict writes are fine; a stray concurrent sample can only
    lose a race on the max (never corrupt state). We keep it lock-free to stay
    cheap.
    """

    def __init__(self) -> None:
        self._peak_overall: float = 0.0
        self._peak_by_phase: Dict[str, float] = {}
        self._order: List[str] = []

    def sample(self, phase: Optional[str] = None) -> float:
        """Take one RSS sample, update the overall and (if given) phase peak,
        and return the sampled value in MiB."""
        rss = read_rss_mib()
        if rss > self._peak_overall:
            self._peak_overall = rss
        if phase:
            prev = self._peak_by_phase.get(phase)
            if prev is None:
                self._peak_by_phase[phase] = rss
                self._order.append(phase)
            elif rss > prev:
                self._peak_by_phase[phase] = rss
        return rss

    def peak_overall(self) -> float:
        return self._peak_overall

    def peak_for(self, phase: str) -> float:
        return self._peak_by_phase.get(phase, 0.0)

    def phases(self) -> List[Tuple[str, float]]:
        """Return (phase, peak_mib) pairs in first-seen order."""
        return [(p, self._peak_by_phase[p]) for p in self._order]


# Process-wide singleton (one tour generation per process, same discipline as
# phase_timer._SUB_TIMER).
_TRACKER = PeakTracker()


def get_tracker() -> PeakTracker:
    return _TRACKER


def reset_tracker() -> None:
    """Replace the global tracker (tests isolate measurements with this)."""
    global _TRACKER
    _TRACKER = PeakTracker()


# ── returning freed memory to the OS between phases (LOCAL-848 core fix) ───────
#
# The profile showed peak RSS = 463 MiB while the Python-traced heap peaked at
# only 68 MiB: the ~360 MiB of growth across phases is transient C-level churn
# (JSON parsing, SPARQL, Serper snippets, LLM response buffers) that Python frees
# but glibc keeps in its per-thread arenas instead of returning to the OS. RSS
# therefore only ever climbs, phase after phase, until the 512 MiB cgroup OOM
# killer fires.
#
# release_memory() closes that gap WITHOUT changing any output: it drops the
# garbage collector's cycles, then asks glibc to trim its arenas back to the OS
# (malloc_trim(0)). It is called at each phase boundary by PhaseTimer.end().

_LIBC = None
_LIBC_RESOLVED = False
_MALLOC_TRIM_OK = True  # set False once if the symbol is absent (musl, etc.)


def _get_libc():
    global _LIBC, _LIBC_RESOLVED
    if _LIBC_RESOLVED:
        return _LIBC
    _LIBC_RESOLVED = True
    if sys.platform != "linux":
        _LIBC = None
        return None
    try:
        import ctypes

        _LIBC = ctypes.CDLL(None)
    except Exception:
        _LIBC = None
    return _LIBC


def malloc_trim(pad: int = 0) -> bool:
    """Ask glibc to return free heap arenas to the OS. True if it ran.

    No-op (returns False) on non-glibc platforms (macOS dev, musl) or if the
    symbol is unavailable. Never raises.
    """
    global _MALLOC_TRIM_OK
    if not _MALLOC_TRIM_OK:
        return False
    libc = _get_libc()
    if libc is None:
        return False
    try:
        fn = libc.malloc_trim
    except AttributeError:
        _MALLOC_TRIM_OK = False
        return False
    try:
        fn(pad)
        return True
    except Exception:
        return False


def release_memory(collect: bool = True, trim: bool = True) -> None:
    """Drop freed Python objects and return their backing memory to the OS.

    Behaviour-neutral: it frees nothing that is still referenced, so generated
    output is identical. Called between phases to flatten the RSS growth curve.
    Never raises into the caller.
    """
    try:
        if collect:
            import gc

            gc.collect()
        if trim:
            malloc_trim(0)
    except Exception:
        pass



# ── optional tracemalloc snapshot (OFF unless LOCAL848_TRACEMALLOC set) ────────

def tracemalloc_enabled() -> bool:
    return os.environ.get("LOCAL848_TRACEMALLOC", "") not in ("", "0", "false", "False")


def maybe_snapshot(label: str, top: int = 10) -> None:
    """If LOCAL848_TRACEMALLOC is set, print the top-N allocation sites now.

    No-op (and cheap) otherwise. Used by the profiling runner to attribute the
    peak to specific allocation sites per phase. Never raises into the caller.
    """
    if not tracemalloc_enabled():
        return
    try:
        import tracemalloc

        if not tracemalloc.is_tracing():
            return
        snap = tracemalloc.take_snapshot()
        stats = snap.statistics("lineno")
        rss = read_rss_mib()
        print(f"[LOCAL-848] tracemalloc TOP {top} @ {label} (rss={rss:.1f} MiB):",
              flush=True)
        for stat in stats[:top]:
            frame = stat.traceback[0]
            fname = os.path.basename(frame.filename)
            print(f"[LOCAL-848]   {stat.size / _MIB:7.2f} MiB  "
                  f"{stat.count:>7} blocks  {fname}:{frame.lineno}", flush=True)
    except Exception:
        # Profiling aid only — never disturb generation.
        pass
