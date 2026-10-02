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
