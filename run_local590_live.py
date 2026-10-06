#!/usr/bin/env python3
"""run_local590_live.py — LOCAL-590 isolated live driver (ONE step per call).

Runs INSIDE a disposable container (see run_local590_live.sh) so it never touches
the audioura-* services. Each invocation performs ONE generation step and appends
a JSON result line to /host_out/local590_results.jsonl, so three light container
runs (step1, step2, baseline) share the pool via the DB without a single
long-lived process accumulating three full generations (which OOMs a capped box).

Steps (scenario in SCENARIOS):
  step1     full generation of N1 stops          → seeds the pool (baseline cost/time)
  step2     request N2 (> N1): pool reuses N1, generates only N2-N1 new ones
  baseline  full generation of N2 with pooling DISABLED → the comparison cost

Usage (inside container):
    python run_local590_live.py <scenario> <step>
    e.g. python run_local590_live.py griffin step1
"""
import os
import re
import sys
import time
import json

os.environ.setdefault("STORIED_MODE", "true")

SCENARIOS = {
    "griffin": {"location": "Griffin museum of photography, Winchester, MA",
                "tour_type": "museum", "n1": 5, "n2": 7},
    "boston_common": {"location": "Boston Common, Boston, MA",
                      "tour_type": "walking", "n1": 4, "n2": 6},
}

RESULTS_PATH = "/host_out/local590_results.jsonl"


def _count_stops(text):
    return len(re.findall(r'^Stop\s+\d+:', text or "", re.M))


def main():
    scenario = sys.argv[1]
    step = sys.argv[2]
    sc = SCENARIOS[scenario]
    loc, tt, n1, n2 = sc["location"], sc["tour_type"], sc["n1"], sc["n2"]

    if step == "step1":
        stops, disable_pool = n1, False
    elif step == "step2":
        stops, disable_pool = n2, False
    elif step == "baseline":
        stops, disable_pool = n2, True
    else:
        print(f"unknown step {step!r}")
        sys.exit(2)

    if disable_pool:
        os.environ["DISABLE_STOP_POOL"] = "1"
    else:
        os.environ.pop("DISABLE_STOP_POOL", None)

    git_sha = open("/app/.git_sha").read().strip() if os.path.exists("/app/.git_sha") else "?"
    print(f"\n#################### LOCAL-590 {scenario}/{step} (git {git_sha}) ####################")
    print(f"[driver] location={loc!r} type={tt!r} stops={stops} disable_pool={disable_pool}")

    import generate_tour_text as g
    out_path = f"/host_out/local590_{scenario}_{step}.txt"
    t0 = time.monotonic()
    text, _out, _ = g.generate_tour_text(loc, tt, out_path, stops)
    dt = time.monotonic() - t0

    rec = dict(getattr(g, "_LAST_GENERATION_COST", {}) or {})
    bd = rec.get("breakdown", {}) or {}
    n = _count_stops(text) if text else 0
    stop_titles = re.findall(r'^Stop\s+\d+:\s*(.+)$', text or "", re.M)

    result = {
        "scenario": scenario, "step": step, "git_sha": git_sha,
        "requested": stops, "delivered": n, "time_s": round(dt, 1),
        "total_cost": round(float(rec.get("total_cost", 0.0)), 4),
        "pool_reuse": bool(rec.get("pool_reuse", False)),
        "reused_stops": bd.get("reused_stops", 0),
        "new_stops": bd.get("new_stops", 0),
        "rewritten_transitions": bd.get("rewritten_transitions", 0),
        "stop_titles": [s.strip() for s in stop_titles],
    }
    print(f"\n===== RESULT {scenario}/{step} =====")
    print(json.dumps(result, indent=2))
    try:
        with open(RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    except Exception as e:
        print(f"[driver] could not append result: {e}")
    print(f"#################### END {scenario}/{step} ####################\n")


if __name__ == "__main__":
    main()
