"""phase_timer.py — LOCAL-445-B: Per-phase timing instrumentation.

Light, module-scope, testable phase timer that logs at each boundary in
generate_tour_text. Designed to be left on permanently (negligible overhead).

Usage:
    from phase_timer import PhaseTimer

    timer = PhaseTimer()
    timer.start('intent')
    ... do intent work ...
    timer.end('intent')
    timer.start('poi_selection')
    ... do POI selection ...
    timer.end('poi_selection')
    ...
    timer.summary()  # prints [TIMING] TOTAL summary

Output format (one line per phase end):
    [TIMING] phase=narration elapsed=312.4s cumulative=498.1s

Summary line:
    [TIMING] TOTAL wall=523.9s phases: narration=312.4s, story_first=40.1s, ...
"""
import time
from typing import Dict, List, Optional, Tuple


class PhaseTimer:
    """Lightweight phase timer for generate_tour_text boundaries.

    Thread-safe for reads (summary/get_phases), but start/end should be called
    from a single orchestrating thread (which is the case in generate_tour_text).
    """

    def __init__(self):
        self._wall_start: float = time.time()
        self._phases: Dict[str, float] = {}  # phase_name → elapsed_seconds
        self._phase_order: List[str] = []  # insertion order
        self._current_phase: Optional[str] = None
        self._current_start: float = 0.0

    def start(self, phase_name: str) -> None:
        """Mark the start of a phase. Ends previous phase if one is running."""
        if self._current_phase is not None:
            self.end(self._current_phase)
        self._current_phase = phase_name
        self._current_start = time.time()
        # LOCAL-651: attribute subsequent [TIMING-SUB] steps to this phase.
        set_current_phase(phase_name)

    def end(self, phase_name: Optional[str] = None) -> float:
        """Mark the end of a phase. Returns elapsed seconds for the phase.

        If phase_name is None, ends the current phase.
        If phase_name doesn't match current, logs a warning but records anyway.
        """
        if phase_name is None:
            phase_name = self._current_phase
        if phase_name is None:
            return 0.0

        elapsed = time.time() - self._current_start
        cumulative = time.time() - self._wall_start

        # Accumulate (allows a phase to be entered multiple times)
        if phase_name in self._phases:
            self._phases[phase_name] += elapsed
        else:
            self._phases[phase_name] = elapsed
            self._phase_order.append(phase_name)

        print(f"[TIMING] phase={phase_name} elapsed={elapsed:.1f}s "
              f"cumulative={cumulative:.1f}s")

        self._current_phase = None
        self._current_start = 0.0
        return elapsed

    def get_phases(self) -> Dict[str, float]:
        """Return a copy of phase timings (phase_name → total_seconds)."""
        return dict(self._phases)

    def get_wall_seconds(self) -> float:
        """Return total wall seconds since timer creation."""
        return time.time() - self._wall_start

    def summary(self) -> str:
        """Print and return the [TIMING] TOTAL summary line.

        Phases are listed sorted by cost (descending).
        """
        # End any running phase
        if self._current_phase is not None:
            self.end(self._current_phase)

        wall = time.time() - self._wall_start
        # Sort by cost descending
        sorted_phases = sorted(self._phases.items(), key=lambda x: x[1], reverse=True)
        phases_str = ', '.join(f"{name}={secs:.1f}s" for name, secs in sorted_phases)

        line = f"[TIMING] TOTAL wall={wall:.1f}s phases: {phases_str}"
        print(line)
        return line

    def get_phase_elapsed(self, phase_name: str) -> float:
        """Get elapsed seconds for a specific phase (0.0 if not recorded)."""
        return self._phases.get(phase_name, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL-651: Sub-phase (per network/LLM call) timing — [TIMING-SUB]
#
# A light, thread-safe sub-timer that records elapsed seconds for individual
# network / LLM calls (steps) and attributes each to the phase that is currently
# running. It emits one line per step:
#
#     [TIMING-SUB] phase=<phase> step=<name> elapsed=<s>
#
# and accumulates (phase, step) -> (total_seconds, count, max_seconds) so a
# summary table can be printed at the end of the run. Steps are measured by the
# SOURCE functions they wrap (resolve_venue, fetch_venue_works, the Gemini/Serper
# primitives, story_first per-step marks, the packing LLM passes). Those run
# inside whichever phase is active, so the current-phase attribution is correct
# even when stops run concurrently in a thread pool (every worker thread shares
# the same orchestrating phase for the duration of story_first/packing).
#
# This module is import-safe everywhere and never raises into a caller: a step
# that fails still records its elapsed time and re-raises the original error.
# ─────────────────────────────────────────────────────────────────────────────
import threading as _threading
from contextlib import contextmanager as _contextmanager

# Module-global "current phase" updated by PhaseTimer.start()/end(). Reads/writes
# are guarded by _SUB_LOCK. Defaults to 'unknown' before any phase begins.
_CURRENT_PHASE: str = 'unknown'
_SUB_LOCK = _threading.Lock()


def set_current_phase(phase_name: str) -> None:
    """Set the phase that subsequent [TIMING-SUB] steps are attributed to."""
    global _CURRENT_PHASE
    with _SUB_LOCK:
        _CURRENT_PHASE = phase_name or 'unknown'


def get_current_phase() -> str:
    with _SUB_LOCK:
        return _CURRENT_PHASE


class SubTimer:
    """Thread-safe accumulator of per-step (network/LLM) timings.

    Only start()/end() of the OWNING PhaseTimer should set the current phase;
    SubTimer itself just reads it. Multiple worker threads may record steps
    concurrently (story_first across-stop pool, external_lookups pool) — the
    accumulate step is lock-guarded.
    """

    def __init__(self):
        self._lock = _threading.Lock()
        # (phase, step) -> {'total': s, 'count': n, 'max': s}
        self._steps = {}

    def record(self, phase: str, step: str, elapsed: float) -> None:
        key = (phase, step)
        with self._lock:
            agg = self._steps.get(key)
            if agg is None:
                self._steps[key] = {'total': elapsed, 'count': 1, 'max': elapsed}
            else:
                agg['total'] += elapsed
                agg['count'] += 1
                if elapsed > agg['max']:
                    agg['max'] = elapsed
        print(f"[TIMING-SUB] phase={phase} step={step} elapsed={elapsed:.2f}s",
              flush=True)

    @_contextmanager
    def step(self, name: str, phase: str = None):
        """Context manager: time a block and record it under the current phase.

        phase defaults to the module-global current phase (set by PhaseTimer),
        so callers inside a phase do not need to pass it.
        """
        import time as _time
        if phase is None:
            phase = get_current_phase()
        t0 = _time.time()
        try:
            yield
        finally:
            self.record(phase, name, _time.time() - t0)

    def get_steps(self):
        """Return a copy of accumulated steps: {(phase, step): {...}}."""
        with self._lock:
            return {k: dict(v) for k, v in self._steps.items()}

    def summary(self):
        """Print and return the [TIMING-SUB] TOTAL table, sorted by total cost.

        Rows: phase, step, total_s (summed across calls — may exceed wall for
        parallel steps), calls, max_s (worst single call, ~critical path).
        """
        with self._lock:
            rows = sorted(self._steps.items(),
                          key=lambda kv: kv[1]['total'], reverse=True)
        lines = ["[TIMING-SUB] TOTAL (per step, summed across calls):"]
        for (phase, step), agg in rows:
            lines.append(
                f"[TIMING-SUB]   phase={phase} step={step} "
                f"total={agg['total']:.2f}s calls={agg['count']} "
                f"max={agg['max']:.2f}s")
        out = "\n".join(lines)
        print(out, flush=True)
        return out


# Process-wide singleton used by the instrumentation wrappers. A single tour
# generation runs in one process, so a module global is the natural home; tests
# can reset it via reset_sub_timer().
_SUB_TIMER = SubTimer()


def get_sub_timer() -> SubTimer:
    return _SUB_TIMER


def reset_sub_timer() -> None:
    """Replace the global sub-timer (used by tests to isolate measurements)."""
    global _SUB_TIMER
    _SUB_TIMER = SubTimer()


def timed_step(name: str):
    """Decorator: time a function call as a [TIMING-SUB] step under the current
    phase. Attribution uses the phase active when the call runs."""
    def _wrap(fn):
        import functools

        @functools.wraps(fn)
        def _inner(*args, **kwargs):
            with _SUB_TIMER.step(name):
                return fn(*args, **kwargs)
        return _inner
    return _wrap
