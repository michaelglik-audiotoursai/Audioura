#!/usr/bin/env python3
"""run_local837_ab.py — [LOCAL-837] offline A/B of the museum story pass ALONE.

**What the ticket asks (Do #2).** "Measure the story pass model ALONE on both
models: per stop, gpt-4.1-mini vs gpt-4.1, on the SAME research. It is one call
per stop, so if gpt-4.1 clears the bar where mini does not, propose
STORY_PASS_MODEL=gpt-4.1 under the cheap arm (narration stays mini). Report the
cost per tour of each." Live budget for THIS A/B: <= $0.20.

**How "the same research" is guaranteed.** Research (Serper + ranking) is the
expensive part and it is built deep inside the production pipeline. Re-running it
per model would (a) cost twice and (b) not be the SAME research — retrieval is
not deterministic. So the live run writes each stop's already-paid
`{matrix, material}` to a JSONL via the LOCAL837_AB_DUMP hook in
generate_tour_text.py; this harness READS that JSONL and calls the story pass
(story_pass.generate_story_for_stop, works_mode=True) twice per stop — once on
gpt-4.1-mini, once on gpt-4.1 — on the IDENTICAL material. The only spend here is
two story-pass completions per stop (a few tenths of a cent each), so the whole
A/B stays far under $0.20, and both arms see byte-for-byte the same research.

**What it reports.** Per stop: does each arm's story clear Michael's bar
(story_opportunity_scan.verdict, the SAME judge the gate uses), and its cost.
Per tour and overall: how many stops each arm clears, and the cost per tour of
each arm. The recommendation line states whether gpt-4.1 clears stops mini does
not — the input to the STORY_PASS_MODEL proposal.

Usage:
    # Produce the research dump from a live run (task 6 wrapper does this):
    #   LOCAL837_AB_DUMP=/path/research.jsonl  <live run>
    # Then:
    python3 run_local837_ab.py --research reports/local837/research.jsonl \\
        --budget 0.20 --out reports/local837/ab_result.json

    # Dry run (no network, no key) — proves the harness logic and cost maths:
    python3 run_local837_ab.py --research <file> --dry-run
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_pass import generate_story_for_stop            # noqa: E402
from story_opportunity_scan import measure, verdict       # noqa: E402

MINI = "gpt-4.1-mini"
FULL = "gpt-4.1"


def clears_bar(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    try:
        return not verdict(measure(str(text))).get("needs_additional_story", True)
    except Exception:
        return False


def _load_research(path):
    """Load the per-stop {tour, stop, name, matrix, material} rows."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _dry_caller_for(model):
    """A no-network caller for --dry-run. It does NOT fabricate a story — it
    returns NO_STORY so the harness exercises its plumbing and cost maths without
    pretending to measure model quality. Real measurement requires --model/live."""
    def _c(prompt, _model=None):
        return "NO_STORY", 0.0
    return _c


def run_arm(rows, model, dry_run=False):
    """Run the story pass for every stop on one model. Returns per-stop records
    and the arm's total cost, grouped by tour."""
    caller = _dry_caller_for(model) if dry_run else None
    per_stop = []
    for r in rows:
        res = generate_story_for_stop(
            r.get("matrix") or {}, r.get("material") or [],
            caller=caller, model=model, works_mode=True)
        story = res.get("story", "") if res.get("ok") else ""
        per_stop.append({
            "tour": r.get("tour", ""),
            "stop": r.get("stop"),
            "name": r.get("name", ""),
            "ok": bool(res.get("ok")),
            "reason": res.get("reason", ""),
            "clears": clears_bar(story),
            "cost": float(res.get("cost") or 0.0),
            "story": story,
        })
    return per_stop


def _by_tour(per_stop):
    tours = {}
    for s in per_stop:
        tours.setdefault(s["tour"], []).append(s)
    return tours


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--research", required=True,
                   help="JSONL of per-stop {matrix, material} from LOCAL837_AB_DUMP")
    p.add_argument("--models", nargs="*", default=[MINI, FULL],
                   help="Models to compare (default: gpt-4.1-mini gpt-4.1)")
    p.add_argument("--budget", type=float, default=0.20,
                   help="Hard spend cap for the whole A/B (USD). Default 0.20.")
    p.add_argument("--dry-run", action="store_true",
                   help="No network/key: exercise the harness and cost maths only.")
    p.add_argument("--out", default="", help="Write the full result JSON here.")
    a = p.parse_args()

    rows = _load_research(a.research)
    if not rows:
        sys.exit(f"run_local837_ab: no research rows in {a.research}")
    print(f"Loaded {len(rows)} stop(s) of research from {a.research}")
    print(f"Comparing models: {', '.join(a.models)}   budget ${a.budget:.2f}"
          f"{'   [DRY RUN — NO NETWORK]' if a.dry_run else ''}\n")

    arms = {}
    spent = 0.0
    for model in a.models:
        per_stop = run_arm(rows, model, dry_run=a.dry_run)
        arm_cost = sum(s["cost"] for s in per_stop)
        spent += arm_cost
        arms[model] = {"per_stop": per_stop, "cost": arm_cost}
        if spent > a.budget and not a.dry_run:
            print(f"  [LOCAL-837] A/B spend ${spent:.4f} exceeded budget "
                  f"${a.budget:.2f} after model {model} — stopping.")
            break

    # ── Report ──────────────────────────────────────────────────────────────
    print("=" * 74)
    print("STORY-PASS A/B — per stop, same research, one call per stop")
    print("=" * 74)
    all_tours = []
    for model, arm in arms.items():
        all_tours += [s["tour"] for s in arm["per_stop"]]
    tour_order = list(dict.fromkeys(all_tours))

    for tour in tour_order:
        print(f"\n{tour}")
        print(f"  {'stop':34} " + "  ".join(f"{m:>14}" for m in arms))
        # align per stop
        stops = sorted({(s["stop"], s["name"])
                        for arm in arms.values() for s in arm["per_stop"]
                        if s["tour"] == tour})
        for (stop_no, name) in stops:
            cells = []
            for model, arm in arms.items():
                hit = next((s for s in arm["per_stop"]
                            if s["tour"] == tour and s["stop"] == stop_no), None)
                if hit:
                    cells.append(f"{'CLEAR' if hit['clears'] else 'no':>7} "
                                 f"${hit['cost']:.4f}")
                else:
                    cells.append(f"{'—':>14}")
            print(f"  {(str(stop_no) + ' ' + name)[:34]:34} " + "  ".join(cells))
        # per-tour clearance + cost per model
        for model, arm in arms.items():
            t_stops = [s for s in arm["per_stop"] if s["tour"] == tour]
            clears = sum(1 for s in t_stops if s["clears"])
            cost = sum(s["cost"] for s in t_stops)
            print(f"    {model}: {clears}/{len(t_stops)} clear the bar   "
                  f"tour cost ${cost:.4f}")

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    for model, arm in arms.items():
        clears = sum(1 for s in arm["per_stop"] if s["clears"])
        total = len(arm["per_stop"])
        print(f"  {model:14}: {clears}/{total} stops clear   "
              f"total A/B cost ${arm['cost']:.4f}")
    print(f"\n  A/B total spend: ${spent:.4f} / budget ${a.budget:.2f} -> "
          f"{'OK' if spent <= a.budget else 'OVER'}")

    # Recommendation: does FULL clear stops MINI does not?
    if MINI in arms and FULL in arms:
        mini_clear = {(s["tour"], s["stop"]) for s in arms[MINI]["per_stop"]
                      if s["clears"]}
        full_clear = {(s["tour"], s["stop"]) for s in arms[FULL]["per_stop"]
                      if s["clears"]}
        gained = full_clear - mini_clear
        lost = mini_clear - full_clear
        print(f"\n  gpt-4.1 clears {len(full_clear)} / gpt-4.1-mini clears "
              f"{len(mini_clear)}")
        if gained:
            print(f"  gpt-4.1 clears {len(gained)} stop(s) mini does NOT: "
                  f"{sorted(gained)}")
            print("  -> PROPOSE STORY_PASS_MODEL=gpt-4.1 under the cheap arm "
                  "(narration stays mini) IF the cost per tour stays within bar.")
        else:
            print("  gpt-4.1 clears no stop mini misses -> keep mini for the "
                  "story pass; the prompt change alone carries the bar.")
        if lost:
            print(f"  (note: mini clears {len(lost)} stop(s) gpt-4.1 does not: "
                  f"{sorted(lost)})")

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump({"models": a.models, "budget": a.budget, "spent": spent,
                   "arms": arms}, open(a.out, "w"),
                  ensure_ascii=False, indent=2, default=str)
        print(f"\n  wrote {a.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
