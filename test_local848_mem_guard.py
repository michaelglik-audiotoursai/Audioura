"""test_local848_mem_guard.py — LOCAL-848 unit tests for the per-phase RSS guard.

Covers mem_guard (RSS reader + PeakTracker + tracemalloc gate) and the
phase_timer wiring that emits the '[LOCAL-848] peak RSS <phase> <MiB>' lines.
These are pure, offline, deterministic tests — no network, no DB, no container.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mem_guard  # noqa: E402
import phase_timer  # noqa: E402


# ── read_rss_mib ──────────────────────────────────────────────────────────────

def test_read_rss_is_positive_and_finite():
    rss = mem_guard.read_rss_mib()
    assert isinstance(rss, float)
    assert rss > 0.0, "a running process must have non-zero RSS"
    assert rss < 1_000_000.0, "RSS in MiB should be a sane magnitude"


def test_read_rss_never_raises_even_if_proc_unavailable(monkeypatch):
    # Force the /proc path to fail and the resource fallback to fail too; the
    # reader must swallow everything and return 0.0 rather than raise.
    import builtins

    real_open = builtins.open

    def _boom_open(path, *a, **k):
        if isinstance(path, str) and path.startswith("/proc/"):
            raise OSError("simulated: /proc unavailable")
        return real_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", _boom_open)
    monkeypatch.setitem(sys.modules, "resource", None)  # import resource -> None attr err
    # Should degrade to 0.0, never raise.
    val = mem_guard.read_rss_mib()
    assert val == 0.0


# ── PeakTracker ───────────────────────────────────────────────────────────────

def test_peak_tracker_tracks_max_overall_and_per_phase(monkeypatch):
    tracker = mem_guard.PeakTracker()
    seq = iter([100.0, 150.0, 120.0, 300.0, 250.0])
    monkeypatch.setattr(mem_guard, "read_rss_mib", lambda: next(seq))

    tracker.sample("intent")        # 100
    tracker.sample("intent")        # 150  -> intent peak 150
    tracker.sample("narration")     # 120  -> narration peak 120
    tracker.sample("narration")     # 300  -> narration peak 300
    tracker.sample("narration")     # 250  -> unchanged

    assert tracker.peak_for("intent") == 150.0
    assert tracker.peak_for("narration") == 300.0
    assert tracker.peak_overall() == 300.0


def test_peak_tracker_preserves_phase_order(monkeypatch):
    tracker = mem_guard.PeakTracker()
    monkeypatch.setattr(mem_guard, "read_rss_mib", lambda: 42.0)
    for ph in ("intent", "poi_selection", "narration", "intent"):
        tracker.sample(ph)
    phases = [p for p, _ in tracker.phases()]
    assert phases == ["intent", "poi_selection", "narration"]  # first-seen, no dupes


def test_peak_for_unknown_phase_is_zero():
    tracker = mem_guard.PeakTracker()
    assert tracker.peak_for("never_sampled") == 0.0


def test_sample_without_phase_updates_only_overall(monkeypatch):
    tracker = mem_guard.PeakTracker()
    monkeypatch.setattr(mem_guard, "read_rss_mib", lambda: 55.0)
    tracker.sample(None)
    assert tracker.peak_overall() == 55.0
    assert tracker.phases() == []


def test_get_and_reset_tracker_singleton():
    t1 = mem_guard.get_tracker()
    t1.sample("x")
    mem_guard.reset_tracker()
    t2 = mem_guard.get_tracker()
    assert t1 is not t2
    assert t2.peak_for("x") == 0.0


# ── tracemalloc gate ──────────────────────────────────────────────────────────

def test_tracemalloc_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LOCAL848_TRACEMALLOC", raising=False)
    assert mem_guard.tracemalloc_enabled() is False
    # maybe_snapshot must be a silent no-op (and never raise) when disabled.
    mem_guard.maybe_snapshot("label")


@pytest.mark.parametrize("val,expected", [
    ("1", True), ("true", True), ("yes-anything", True),
    ("0", False), ("false", False), ("", False),
])
def test_tracemalloc_gate_reads_env(monkeypatch, val, expected):
    if val == "":
        monkeypatch.delenv("LOCAL848_TRACEMALLOC", raising=False)
    else:
        monkeypatch.setenv("LOCAL848_TRACEMALLOC", val)
    assert mem_guard.tracemalloc_enabled() is expected


# ── release_memory / malloc_trim (the core memory fix) ────────────────────────

def test_release_memory_never_raises():
    # On any platform this must be a safe no-op-or-trim; never raise.
    mem_guard.release_memory()
    mem_guard.release_memory(collect=False, trim=True)
    mem_guard.release_memory(collect=True, trim=False)


def test_malloc_trim_returns_bool():
    # True on glibc Linux, False on macOS/musl — but always a bool, never raise.
    assert isinstance(mem_guard.malloc_trim(0), bool)


def test_release_memory_calls_gc_and_trim(monkeypatch):
    calls = {"gc": 0, "trim": 0}
    import gc as _gc
    monkeypatch.setattr(_gc, "collect", lambda *a, **k: calls.__setitem__("gc", calls["gc"] + 1))
    monkeypatch.setattr(mem_guard, "malloc_trim",
                        lambda pad=0: calls.__setitem__("trim", calls["trim"] + 1) or True)
    mem_guard.release_memory()
    assert calls["gc"] == 1
    assert calls["trim"] == 1


def test_release_memory_swallows_trim_failure(monkeypatch):
    def _boom(pad=0):
        raise RuntimeError("trim blew up")
    monkeypatch.setattr(mem_guard, "malloc_trim", _boom)
    # Must not propagate.
    mem_guard.release_memory()


# ── phase_timer wiring ────────────────────────────────────────────────────────

def test_phase_timer_emits_local848_guard_lines(monkeypatch, capsys):
    mem_guard.reset_tracker()
    # Deterministic growing RSS so the guard lines have known values.
    seq = iter([100.0, 140.0, 140.0, 220.0, 220.0, 260.0, 260.0, 260.0])

    def _fake_rss():
        try:
            return next(seq)
        except StopIteration:
            return 260.0

    monkeypatch.setattr(mem_guard, "read_rss_mib", _fake_rss)

    t = phase_timer.PhaseTimer()
    t.start("intent")
    t.end("intent")
    t.start("narration")
    t.end("narration")
    t.summary()

    out = capsys.readouterr().out
    assert "[LOCAL-848] peak RSS intent" in out
    assert "[LOCAL-848] peak RSS narration" in out
    assert "[LOCAL-848] peak RSS process" in out
    # Four boundary samples fire (start+end per phase): 100,140 for intent,
    # 140,220 for narration. The process summary carries the overall max (220).
    assert "220.0 MiB" in out


def test_phase_timer_guard_survives_mem_guard_failure(monkeypatch, capsys):
    # If sampling blows up, timing must still work and no exception escapes.
    monkeypatch.setattr(mem_guard, "read_rss_mib",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    mem_guard.reset_tracker()
    t = phase_timer.PhaseTimer()
    t.start("intent")
    elapsed = t.end("intent")
    assert elapsed >= 0.0
    # Timing line is still printed.
    assert "[TIMING] phase=intent" in capsys.readouterr().out


def test_phase_timer_end_releases_memory_by_default(monkeypatch):
    monkeypatch.delenv("LOCAL848_RELEASE", raising=False)
    released = {"n": 0}
    monkeypatch.setattr(mem_guard, "release_memory",
                        lambda *a, **k: released.__setitem__("n", released["n"] + 1))
    t = phase_timer.PhaseTimer()
    t.start("intent")
    t.end("intent")
    assert released["n"] == 1


def test_phase_timer_release_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL848_RELEASE", "0")
    released = {"n": 0}
    monkeypatch.setattr(mem_guard, "release_memory",
                        lambda *a, **k: released.__setitem__("n", released["n"] + 1))
    t = phase_timer.PhaseTimer()
    t.start("intent")
    t.end("intent")
    assert released["n"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
