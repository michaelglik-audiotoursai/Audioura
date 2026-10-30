"""run_local848_container.py — LOCAL-848 in-container memory PROFILER.

Runs ONE museum tour (Rijks, 5) and/or ONE walking tour in-process on the
audioura-tour-generator image, with the LOCAL-848 per-phase RSS guard
(mem_guard + phase_timer) active and tracemalloc turned ON, so the log shows:

  * [LOCAL-848] peak RSS <phase> <MiB>         — one per phase (cheap guard)
  * [LOCAL-848] peak RSS process <MiB>         — process summary
  * [LOCAL-848] tracemalloc TOP 10 @ <label>   — per-phase allocation sites
  * a final [LOCAL-848] PROFILE SUMMARY block with the peak per phase and the
    top-10 Python allocation sites at the moment of the overall peak.

It is a PROFILER, not a pass/fail gate — but it still honours the metered task
budget so a runaway run cannot spend. Invoke via run_local848_live.sh.

  argv[1]: 'museum' | 'walking' | 'both'   (default 'museum')

DB: the isolated throwaway postgres only (seeded by the wrapper with the REAL
Rijks Q190804 + Orsay Q23402 rows). Never the shared/live DB, never an
audioura-* container.
"""
import gc
import io
import json
import os
import sys
import time
import tracemalloc
import contextlib

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

# Force the guard's tracemalloc snapshots on for the profile run.
os.environ.setdefault("LOCAL848_TRACEMALLOC", "1")
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("DISABLE_STOP_POOL", "1")
os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("SERPER_RESEARCH_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("WORK_STORY_RESEARCH", "1")

TASK_ID = os.environ.get("TASK_BUDGET_ID", "LOCAL-848") or "LOCAL-848"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

MUSEUM = ("Rijksmuseum, Amsterdam, Netherlands", "museum", 5)
WALKING = ("Beacon Hill, Boston, Massachusetts", "walking", 5)


def _which_tours():
    which = (sys.argv[1].strip().lower() if len(sys.argv) > 1 else "museum")
    if which == "both":
        return [MUSEUM, WALKING]
    if which == "walking":
        return [WALKING]
    return [MUSEUM]


def _profile_one(location, tour_type, n_stops):
    import mem_guard
    import generate_tour_text as g

    # Fresh peak tracker per tour so the per-phase peaks belong to THIS tour.
    mem_guard.reset_tracker()
    gc.collect()
    tracemalloc.start(25)

    print("\n" + "=" * 72, flush=True)
    print(f"=== [LOCAL-848] PROFILING {location} ({tour_type}, {n_stops}) ===",
          flush=True)
    base_rss = mem_guard.read_rss_mib()
    print(f"  baseline RSS before generation: {base_rss:.1f} MiB", flush=True)

    t0 = time.time()
    peak_snapshot = None
    peak_rss_py = 0.0
    text = None
    try:
        text, _out, _coords = g.generate_tour_text(location, tour_type, None, n_stops)
    except Exception as e:
        import traceback
        print(f"  [LOCAL-848] generation raised: {e}", flush=True)
        traceback.print_exc()
    finally:
        dt = time.time() - t0
        cur_py, peak_py = tracemalloc.get_traced_memory()
        peak_rss_py = peak_py / (1024.0 * 1024.0)
        # Top allocation sites at END of run (close to story/verification peak).
        snap = tracemalloc.take_snapshot()
        tracemalloc.stop()

    tracker = mem_guard.get_tracker()
    phase_peaks = tracker.phases()
    overall = tracker.peak_overall()

    print(f"\n  --- [LOCAL-848] PROFILE SUMMARY: {location} ({tour_type}) ---",
          flush=True)
    print(f"  wall={dt:.0f}s  stops_in_text={(text or '').count('Stop ')}", flush=True)
    print(f"  peak RSS process (cgroup-visible): {overall:.1f} MiB", flush=True)
    print(f"  peak Python-traced heap (tracemalloc): {peak_rss_py:.1f} MiB", flush=True)
    print("  peak RSS per phase (MiB), highest first:", flush=True)
    for name, mib in sorted(phase_peaks, key=lambda x: x[1], reverse=True):
        print(f"    {name:<24} {mib:7.1f}", flush=True)

    print("\n  top-10 Python allocation sites at end-of-run:", flush=True)
    stats = snap.statistics("lineno")
    top = []
    for stat in stats[:10]:
        frame = stat.traceback[0]
        fname = os.path.basename(frame.filename)
        line = f"{fname}:{frame.lineno}"
        mib = stat.size / (1024.0 * 1024.0)
        print(f"    {mib:7.2f} MiB  {stat.count:>8} blocks  {line}", flush=True)
        top.append({"site": line, "mib": round(mib, 2), "blocks": stat.count})

    # Grouped by file — the single biggest lever is usually one module.
    by_file = {}
    for stat in stats:
        fname = os.path.basename(stat.traceback[0].filename)
        by_file[fname] = by_file.get(fname, 0.0) + stat.size / (1024.0 * 1024.0)
    print("\n  top-10 allocation by FILE (MiB):", flush=True)
    for fname, mib in sorted(by_file.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {mib:7.2f} MiB  {fname}", flush=True)

    return {
        "location": location,
        "tour_type": tour_type,
        "n_stops": n_stops,
        "wall_s": round(dt, 1),
        "baseline_rss_mib": round(base_rss, 1),
        "peak_rss_process_mib": round(overall, 1),
        "peak_python_traced_mib": round(peak_rss_py, 1),
        "phase_peaks_mib": {name: round(mib, 1) for name, mib in phase_peaks},
        "top_alloc_sites": top,
        "top_alloc_by_file": {k: round(v, 2) for k, v in
                              sorted(by_file.items(), key=lambda kv: -kv[1])[:10]},
    }


def main():
    print("=" * 72, flush=True)
    print("=== LOCAL-848 MEMORY PROFILER (per-phase RSS + tracemalloc) ===", flush=True)
    print(f"  TASK_BUDGET_ID={TASK_ID!r} CAP=${HARD_CAP_USD:.2f}  meter={METER_LOG}",
          flush=True)
    print(f"  LOCAL848_TRACEMALLOC={os.environ.get('LOCAL848_TRACEMALLOC')} "
          f"STORY_PASS_MODEL={os.environ.get('STORY_PASS_MODEL', '(default)')} "
          f"DISABLE_STOP_POOL={os.environ.get('DISABLE_STOP_POOL')}", flush=True)

    # Metered budget guard — refuse to start if the ledger is already at the cap.
    meter = None
    try:
        from live_run_meter import LiveRunMeter
        meter = LiveRunMeter(TASK_ID)
        spent = 0.0
        try:
            spent = meter.total_usd()
        except Exception:
            spent = 0.0
        print(f"  ledger spent so far: ${spent:.3f} / ${HARD_CAP_USD:.2f}", flush=True)
        if spent >= HARD_CAP_USD:
            print(f"  [LOCAL-848] reserve gate: ${spent:.3f} >= cap — NOT running",
                  flush=True)
            return 2
    except Exception as e:
        print(f"  [LOCAL-848] live_run_meter unavailable ({e}); profiling without "
              f"ledger reserve (image budget env still enforces the hard cap)",
              flush=True)

    results = []
    for (location, tour_type, n_stops) in _which_tours():
        if meter is not None:
            try:
                if meter.total_usd() >= HARD_CAP_USD:
                    print(f"  [LOCAL-848] cap reached — skipping {location}", flush=True)
                    break
            except Exception:
                pass
        try:
            results.append(_profile_one(location, tour_type, n_stops))
        finally:
            if meter is not None:
                try:
                    import generate_tour_text as g
                    meter.add_generation(g)
                    meter.record()
                except Exception:
                    pass

    if meter is not None:
        try:
            print("\n  " + meter.summary().replace("\n", "\n  "), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    try:
        os.makedirs("/app/reports/local848", exist_ok=True)
        out_path = "/app/reports/local848/profile_result.json"
        json.dump({"cap": HARD_CAP_USD, "results": results}, open(out_path, "w"),
                  ensure_ascii=False, indent=2, default=str)
        print(f"\n  wrote {out_path}", flush=True)
    except Exception as e:
        print(f"  [LOCAL-848] could not write report: {e}", flush=True)

    print("\n=== [LOCAL-848] PROFILE DONE ===", flush=True)
    for r in results:
        print(f"  {r['location']} ({r['tour_type']}): "
              f"peak {r['peak_rss_process_mib']} MiB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
