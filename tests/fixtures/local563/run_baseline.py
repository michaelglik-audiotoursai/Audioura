"""LOCAL-563 — baseline orchestrator: 10 tours x 2 runs, hard $14 Gemini cap.

Runs each tour's run1 and run2, interleaved so a cap stop ALWAYS leaves complete
pairs — a tour's two runs are dispatched together and we never begin a new tour
unless the cumulative grounded spend can afford a whole pair. The two runs of a
tour execute concurrently (two subprocesses); that is the parallelism, kept at the
pair boundary so cap behaviour stays simple and pairs stay atomic (well within the
"up to 3 in parallel" budget).

Each run is a separate process (run_one.py) so per-run grounded counts and the
LOCAL-562 cost accumulator never cross-contaminate; the $14 cap is enforced through
the shared on-disk cumulative counter in gemini_recorder, which every process
increments under an flock, and which this orchestrator reads before each tour.

Budget protocol (budget.log, appended after EVERY run and every pair):
  * Before a tour: read cumulative; if starting the pair could reach $14, STOP.
  * Grounded search is $0.035/req; $14 = 400 req. We reserve a conservative
    PER_RUN_ESTIMATE grounded requests per run so a pair we start can finish.

Usage:
  python3 run_baseline.py                 # run all remaining pairs (resumable)
  python3 run_baseline.py sail_loft buttermilk   # run only these slugs (in order)
  python3 run_baseline.py --reset         # zero the cumulative counter first
  python3 run_baseline.py --status        # print budget + which pairs are done

Resumable: a pair whose run1.json and run2.json both exist with status 'ok' is
skipped, so re-invoking after a 60-minute session limit continues where it stopped.
"""
import os
import sys
import json
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
sys.path.insert(0, HERE)
import gemini_recorder as gr  # noqa: E402

# Interleave order: restaurants first (cheap, 1-2 stops), then the 4-stop tours.
# Pairs are processed strictly in this order; a cap stop leaves earlier pairs whole.
ORDER = [
    "sail_loft", "buttermilk", "chart_house", "sycamore", "la_maree",
    "logan", "our_lady", "lascaris", "riviera_bike", "faneuil",
]

# Conservative reserve per run for the pre-tour cap check. The task observed 12-15
# grounded requests per tour; reserve 20 so we never start a pair (2 runs) we might
# not finish under the cap. This only gates STARTING a tour; the real spend is the
# counted requests, and run_one also fails closed at the cap mid-run.
PER_RUN_ESTIMATE = 20
PER_PAIR_ESTIMATE = PER_RUN_ESTIMATE * 2


def _run_json(slug, run_label):
    p = os.path.join(RUNS, f"{slug}_{run_label}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _pair_done(slug):
    r1, r2 = _run_json(slug, "run1"), _run_json(slug, "run2")
    return bool(r1 and r2 and r1.get("status") == "ok" and r2.get("status") == "ok")


def _spawn(slug, run_label):
    """Launch one run_one.py subprocess; return the Popen."""
    log = open(os.path.join(RUNS, f"{slug}_{run_label}.spawn.log"), "w")
    return subprocess.Popen(
        [sys.executable, os.path.join(HERE, "run_one.py"), slug, run_label],
        stdout=log, stderr=subprocess.STDOUT, cwd=HERE,
    ), log


def _status():
    cum = gr.cumulative_grounded_requests()
    print(f"cumulative grounded requests: {cum}  "
          f"(${cum*gr.GROUNDING_COST_PER_REQUEST:.2f} of ${gr.HARD_CAP_USD:.2f})")
    for slug in ORDER:
        state = "done" if _pair_done(slug) else "pending"
        r1, r2 = _run_json(slug, "run1"), _run_json(slug, "run2")
        extra = ""
        if r1 or r2:
            def g(r):
                return "-" if not r else f"{r.get('status')}({r.get('gemini_calls',{}).get('grounded_this_run','?')}gr)"
            extra = f"  run1={g(r1)} run2={g(r2)}"
        print(f"  {slug:14s} {state}{extra}")


def main():
    args = sys.argv[1:]
    if "--status" in args:
        _status()
        return 0
    if "--reset" in args:
        gr.reset_budget_state()
        gr.log_budget(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] RESET cumulative counter to 0")
        args = [a for a in args if a != "--reset"]
        print("cumulative counter reset to 0")

    slugs = [a for a in args if not a.startswith("--")] or ORDER
    # Keep ORDER's sequence even when a subset is given.
    slugs = [s for s in ORDER if s in slugs]

    os.makedirs(RUNS, exist_ok=True)
    gr.log_budget(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] SESSION START; "
                  f"cumulative={gr.cumulative_grounded_requests()} "
                  f"(${gr.cumulative_cost_usd():.2f}); queue={slugs}")

    for slug in slugs:
        if _pair_done(slug):
            print(f"[{slug}] pair already complete — skipping")
            continue

        cum = gr.cumulative_grounded_requests()
        cost = cum * gr.GROUNDING_COST_PER_REQUEST
        # Pre-tour cap gate: never START a tour whose pair could cross $14.
        if gr.would_exceed_cap(PER_PAIR_ESTIMATE):
            msg = (f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] CAP STOP before '{slug}': "
                   f"cumulative={cum} (${cost:.2f}); a pair reserves "
                   f"{PER_PAIR_ESTIMATE} req (${PER_PAIR_ESTIMATE*gr.GROUNDING_COST_PER_REQUEST:.2f}) "
                   f"which would reach the ${gr.HARD_CAP_USD:.2f} cap. Stopping with complete pairs only.")
            print(msg)
            gr.log_budget(msg)
            break

        print(f"\n{'='*72}\n[{slug}] starting pair — cumulative={cum} (${cost:.2f})\n{'='*72}")
        gr.log_budget(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] PAIR START '{slug}'; "
                      f"cumulative_before={cum} (${cost:.2f})")

        t0 = time.time()
        procs = []
        for run_label in ("run1", "run2"):
            p, log = _spawn(slug, run_label)
            procs.append((run_label, p, log))
            # Small stagger so the two runs do not reset/scope in lockstep.
            time.sleep(2)

        for run_label, p, log in procs:
            p.wait()
            log.close()

        pair_wall = time.time() - t0
        cum_after = gr.cumulative_grounded_requests()
        r1, r2 = _run_json(slug, "run1"), _run_json(slug, "run2")

        def _gr(r):
            return (r or {}).get("gemini_calls", {}).get("grounded_this_run", "?")

        def _st(r):
            return (r or {}).get("status", "missing")

        line = (f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] PAIR DONE '{slug}' "
                f"wall={pair_wall:.0f}s run1={_st(r1)}({_gr(r1)}gr) run2={_st(r2)}({_gr(r2)}gr) "
                f"cumulative_after={cum_after} (${cum_after*gr.GROUNDING_COST_PER_REQUEST:.2f} "
                f"of ${gr.HARD_CAP_USD:.2f})")
        print(line)
        gr.log_budget(line)

        # If a run hit the cap mid-pair, stop after finishing this pair's processes.
        if _st(r1) == "budget_exceeded" or _st(r2) == "budget_exceeded":
            stop = (f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] CAP reached DURING '{slug}'. "
                    f"Pair finished; stopping.")
            print(stop)
            gr.log_budget(stop)
            break

    gr.log_budget(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] SESSION END; "
                  f"cumulative={gr.cumulative_grounded_requests()} "
                  f"(${gr.cumulative_cost_usd():.2f})")
    print("\n--- final status ---")
    _status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
