"""run_local848_accept.py — LOCAL-848 512 MiB acceptance (before/after the fix).

Generates ONE Rijks (5) museum tour in-process under the container's --memory
limit, with the LOCAL-848 cheap per-phase RSS guard ON (tracemalloc OFF, so the
measurement reflects REAL production memory). Prints the per-phase guard lines
and a single PASS/FAIL verdict:

    PASS  = generation COMPLETED (stops produced) AND peak RSS <= PEAK_TARGET_MIB
    FAIL  = OOM-killed, raised, produced no stops, or peak > target

Under --memory=512m this reproduces the Cloud Run OOM BEFORE the fix (the
container is SIGKILL'd, rc=137, no summary) and proves the fix AFTER (completes
with peak <= 350 MiB).

Metered to the enforced task budget; refuses to start if the ledger is at cap.
Isolated throwaway DB only. Never an audioura-* container.
"""
import gc
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

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
# tracemalloc OFF for the acceptance measurement (it inflates RSS).
os.environ["LOCAL848_TRACEMALLOC"] = "0"

TASK_ID = os.environ.get("TASK_BUDGET_ID", "LOCAL-848") or "LOCAL-848"
HARD_CAP_USD = float(os.environ.get("TASK_BUDGET_USD", "0.60") or "0.60")
PEAK_TARGET_MIB = float(os.environ.get("PEAK_TARGET_MIB", "350") or "350")
METER_LOG = os.environ.get("PAID_API_LOG", "/meterlogs/paid_api_calls.jsonl")
os.environ.setdefault("TEST_GEMINI_MAX_USD", str(HARD_CAP_USD))
os.environ.setdefault("COST_HARD_LIMIT_USD", str(HARD_CAP_USD))

TOUR = ("Rijksmuseum, Amsterdam, Netherlands", "museum", 5)


def main():
    location, tour_type, n_stops = TOUR
    print("=" * 72, flush=True)
    print("=== LOCAL-848 512 MiB ACCEPTANCE — Rijks(5), peer-phase RSS guard ===",
          flush=True)
    print(f"  TASK_BUDGET_ID={TASK_ID!r} CAP=${HARD_CAP_USD:.2f} "
          f"PEAK_TARGET={PEAK_TARGET_MIB:.0f} MiB  meter={METER_LOG}", flush=True)
    print(f"  STORY_PASS_MODEL={os.environ.get('STORY_PASS_MODEL', '(default)')} "
          f"DISABLE_STOP_POOL={os.environ.get('DISABLE_STOP_POOL')}", flush=True)

    import mem_guard
    mem_guard.reset_tracker()

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
        print(f"  [LOCAL-848] live_run_meter unavailable ({e}); image budget env "
              f"still enforces the hard cap", flush=True)

    import generate_tour_text as g

    base = mem_guard.read_rss_mib()
    print(f"  baseline RSS: {base:.1f} MiB", flush=True)
    gc.collect()

    t0 = time.time()
    text = None
    raised = None
    try:
        text, _out, _coords = g.generate_tour_text(location, tour_type, None, n_stops)
    except Exception as e:
        import traceback
        raised = str(e)
        print(f"  [LOCAL-848] generation raised: {e}", flush=True)
        traceback.print_exc()
    finally:
        if meter is not None:
            try:
                meter.add_generation(g)
                meter.record()
                print("  " + meter.summary().replace("\n", "\n  "), flush=True)
                meter.uninstall()
            except Exception:
                pass

    dt = time.time() - t0
    n_in_text = (text or "").count("Stop ")
    peak = mem_guard.get_tracker().peak_overall()

    completed = (text is not None and n_in_text >= 1 and raised is None)
    peak_ok = (peak > 0.0 and peak <= PEAK_TARGET_MIB)
    verdict = completed and peak_ok

    print("\n" + "=" * 72, flush=True)
    print("=== LOCAL-848 ACCEPTANCE RESULT ===", flush=True)
    print(f"  wall={dt:.0f}s  stops_in_text={n_in_text}  raised={raised}", flush=True)
    print(f"  peak RSS process: {peak:.1f} MiB  (target <= {PEAK_TARGET_MIB:.0f})",
          flush=True)
    print(f"  completed={completed}  peak_ok={peak_ok}", flush=True)
    print(f"  VERDICT: {'PASS' if verdict else 'FAIL'}", flush=True)

    try:
        os.makedirs("/app/reports/local848", exist_ok=True)
        tag = os.environ.get("LOCAL848_RESULT_TAG", "accept")
        out = f"/app/reports/local848/accept_{tag}.json"
        json.dump({"location": location, "n_stops": n_stops, "wall_s": round(dt, 1),
                   "stops_in_text": n_in_text, "raised": raised,
                   "peak_rss_process_mib": round(peak, 1),
                   "peak_target_mib": PEAK_TARGET_MIB,
                   "completed": completed, "peak_ok": peak_ok, "pass": verdict},
                  open(out, "w"), ensure_ascii=False, indent=2, default=str)
        print(f"  wrote {out}", flush=True)
    except Exception as e:
        print(f"  [LOCAL-848] could not write report: {e}", flush=True)

    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
