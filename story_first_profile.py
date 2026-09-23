"""story_first_profile.py — LOCAL-3498: sub-phase instrumentation for story_first.

The top-level PhaseTimer (phase_timer.py) reports one number for the whole
`story_first` phase — but that phase wraps FAR more than the LOCAL-440 pipeline:
the per-stop description-generation loop (`_generate_description`, run in a
ThreadPoolExecutor) plus ~20 serial post-description gates. Nobody had measured
where inside that block the 110-150s actually goes. This module does.

Design goals (D261/D358 discipline — measure, do not guess):
  • ZERO behaviour change when off. Gated behind STORY_FIRST_PROFILE=1 so a
    normal run is untouched; every start/end is a cheap no-op when disabled.
  • Same output shape as the top-level line, one level indented:
        [STORY_FIRST] step=description_generation elapsed=41.3s cumulative=48.2s
  • Two axes of measurement:
        1. SERIAL sub-steps (the post-description gates) — wall time each, via
           start()/end(). These run one after another on the orchestrating
           thread, so wall time == the cost, and they are the parallelisation
           candidates.
        2. PER-STOP work inside _generate_description — recorded thread-safely
           by idx, because that function runs concurrently across stops. We
           report each stop's own wall time AND the span (max end - min start)
           so the report can say how much parallelism actually helped.

Public API:
    enabled() -> bool
    sub_start(name) / sub_end(name=None) -> float      # serial sub-steps
    record_stop(idx, elapsed_s, detail=None)           # per-stop wall time
    stop_scope(idx)                                    # context manager
    reset()
    summary() -> str                                   # prints [STORY_FIRST] TOTAL
    get_serial() -> dict     # name -> seconds (insertion order preserved)
    get_stops() -> dict      # idx -> {'elapsed': s, 'start': t, 'end': t, ...}
"""
import contextlib
import os
import threading
import time
from typing import Dict, List, Optional


def enabled() -> bool:
    """True when STORY_FIRST_PROFILE=1 — otherwise every hook is a no-op."""
    return os.environ.get('STORY_FIRST_PROFILE', '').strip() in ('1', 'true', 'True')


# --- Serial sub-step timing (single orchestrating thread) -------------------
_lock = threading.Lock()
_phase_start_wall: float = 0.0        # when the story_first phase itself began
_serial: Dict[str, float] = {}        # step name -> total seconds
_serial_order: List[str] = []
_current: Optional[str] = None
_current_start: float = 0.0

# --- Per-stop timing (concurrent threads) -----------------------------------
_stops: Dict[int, Dict] = {}          # idx -> {'elapsed','start','end','detail'}
_stop_starts: Dict[int, float] = {}   # idx -> worker start wall time


def reset() -> None:
    """Clear all state and mark the phase start. Call at story_first entry."""
    global _phase_start_wall, _serial, _serial_order, _current, _current_start, _stops
    with _lock:
        _phase_start_wall = time.time()
        _serial = {}
        _serial_order = []
        _current = None
        _current_start = 0.0
        _stops = {}
        _stop_starts.clear()


def sub_start(name: str) -> None:
    """Begin a serial sub-step. Ends the previous one if still running."""
    if not enabled():
        return
    global _current, _current_start
    if _current is not None:
        sub_end(_current)
    _current = name
    _current_start = time.time()


def sub_end(name: Optional[str] = None) -> float:
    """End the current serial sub-step; print + accumulate its wall time."""
    if not enabled():
        return 0.0
    global _current, _current_start
    if name is None:
        name = _current
    if name is None:
        return 0.0
    elapsed = time.time() - _current_start
    with _lock:
        if name in _serial:
            _serial[name] += elapsed
        else:
            _serial[name] = elapsed
            _serial_order.append(name)
        cumulative = time.time() - _phase_start_wall
    print(f"  [STORY_FIRST] step={name} elapsed={elapsed:.1f}s "
          f"cumulative={cumulative:.1f}s")
    _current = None
    _current_start = 0.0
    return elapsed


def record_stop(idx: int, elapsed_s: float, detail: Optional[Dict] = None,
                start_wall: Optional[float] = None,
                end_wall: Optional[float] = None) -> None:
    """Record one stop's own wall time (thread-safe; called from workers)."""
    if not enabled():
        return
    with _lock:
        _stops[idx] = {
            'elapsed': elapsed_s,
            'start': start_wall,
            'end': end_wall,
            'detail': detail or {},
        }


def mark_stop_start(idx: int) -> None:
    """Record the wall time a stop's worker actually began (thread-safe)."""
    if not enabled():
        return
    with _lock:
        _stop_starts[idx] = time.time()


def close_stop(idx: int, detail: Optional[Dict] = None) -> None:
    """Close a stop started with mark_stop_start(); record its wall time."""
    if not enabled():
        return
    with _lock:
        t0 = _stop_starts.get(idx)
    if t0 is None:
        return
    t1 = time.time()
    record_stop(idx, t1 - t0, detail=detail, start_wall=t0, end_wall=t1)


@contextlib.contextmanager
def stop_scope(idx: int, detail: Optional[Dict] = None):
    """Context manager that times a per-stop block and records it by idx."""
    if not enabled():
        yield
        return
    t0 = time.time()
    try:
        yield
    finally:
        t1 = time.time()
        record_stop(idx, t1 - t0, detail=detail, start_wall=t0, end_wall=t1)


def get_serial() -> Dict[str, float]:
    with _lock:
        return {name: _serial[name] for name in _serial_order}


def get_stops() -> Dict[int, Dict]:
    with _lock:
        return {k: dict(v) for k, v in _stops.items()}


def summary() -> str:
    """Print and return a [STORY_FIRST] TOTAL line summarising sub-steps.

    Reports serial sub-steps sorted by cost, and the per-stop block: sum of
    per-stop wall time (what a serial loop would have cost) vs the observed
    span (max end - min start), which exposes how much the ThreadPool helped.
    """
    if not enabled():
        return ''
    # Close any still-running serial step so the last gate is recorded.
    if _current is not None:
        sub_end(_current)
    with _lock:
        phase_wall = time.time() - _phase_start_wall
        serial_items = sorted(_serial.items(), key=lambda x: x[1], reverse=True)
        stops = {k: dict(v) for k, v in _stops.items()}

    lines = []
    if stops:
        per_stop_sum = sum(s['elapsed'] for s in stops.values())
        starts = [s['start'] for s in stops.values() if s.get('start')]
        ends = [s['end'] for s in stops.values() if s.get('end')]
        span = (max(ends) - min(starts)) if starts and ends else 0.0
        slowest = max(stops.values(), key=lambda s: s['elapsed'])
        lines.append(
            f"  [STORY_FIRST] per_stop: n={len(stops)} "
            f"sum_wall={per_stop_sum:.1f}s observed_span={span:.1f}s "
            f"slowest={slowest['elapsed']:.1f}s "
            f"(serial_would_cost={per_stop_sum:.1f}s vs parallel_span={span:.1f}s)"
        )
        for idx in sorted(stops):
            s = stops[idx]
            d = s.get('detail') or {}
            dstr = (' ' + ' '.join(f"{k}={v}" for k, v in d.items())) if d else ''
            lines.append(f"    [STORY_FIRST] stop={idx} elapsed={s['elapsed']:.1f}s{dstr}")

    serial_str = ', '.join(f"{n}={v:.1f}s" for n, v in serial_items)
    total_line = (f"  [STORY_FIRST] TOTAL phase_wall={phase_wall:.1f}s "
                  f"serial_steps: {serial_str}")
    for ln in lines:
        print(ln)
    print(total_line)
    return total_line
