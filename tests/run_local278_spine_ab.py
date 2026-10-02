#!/usr/bin/env python3
"""
LOCAL-278: Spine model A/B comparison.
========================================
Runs the same spine generation across multiple models (gpt-4o, gpt-4o-mini,
gpt-3.5-turbo) with identical inputs. Measures cost, latency, and output
quality using existing quality infrastructure.

Acceptance: ≥3 models, ≥3 runs each, with cost, latency, and measured quality.
"""
import json
import os
import sys
import time
from pathlib import Path

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from cost_rates import llm_cost
from spine_generator import generate_spine, LAST_SPINE_COST
from spine_quality_scorer import score_spine

# ─── Configuration ───────────────────────────────────────────────────────────

# Load API key from environment or from Audioura .env
def _load_api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env_path = Path.home() / "Audioura" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY not found in env or ~/Audioura/.env")


# A/B parameters — same location & stops across all models (D183 baseline pair)
VENUE_NAME = "Cap d'Antibes"
POI_LIST = ["Villa Eilenroc", "Sentier du Littoral"]
TOUR_CATEGORY = "walking"
TOTAL_STOPS = len(POI_LIST)

# Models to test
MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

# Runs per model
RUNS_PER_MODEL = 4

# ─── Quality measurement ─────────────────────────────────────────────────────

def measure_quality(spine: dict) -> dict:
    """Measure spine output quality using existing infrastructure.
    
    Returns dict with:
        - spine_score: 0-4 from spine_quality_scorer
        - spine_breakdown: per-criterion results
        - has_tour_hook: bool
        - has_connecting_thread: bool
        - has_closing_revelation: bool
        - arc_count: number of arc entries
        - four_part_present: all required fields present
        - hook_length: character length of tour_hook
        - revelation_length: character length of closing_revelation
        - unique_angles: count of non-empty unique_angle fields
    """
    if not spine:
        return {"spine_score": 0, "error": "spine is None"}
    
    score, breakdown = score_spine(spine, total_stops=TOTAL_STOPS)
    
    arc = spine.get("arc", [])
    required_fields = ["tour_hook", "connecting_thread", "arc", 
                       "climax_stop", "resolution_stop", "closing_revelation"]
    four_part = all(spine.get(f) for f in required_fields)
    
    unique_angles = sum(1 for stop in arc if stop.get("unique_angle", "").strip())
    
    return {
        "spine_score": score,
        "spine_breakdown": breakdown,
        "has_tour_hook": bool(spine.get("tour_hook", "").strip()),
        "has_connecting_thread": bool(spine.get("connecting_thread", "").strip()),
        "has_closing_revelation": bool(spine.get("closing_revelation", "").strip()),
        "arc_count": len(arc),
        "four_part_present": four_part,
        "hook_length": len(spine.get("tour_hook", "")),
        "revelation_length": len(spine.get("closing_revelation", "")),
        "unique_angles": unique_angles,
    }


# ─── Main A/B runner ─────────────────────────────────────────────────────────

def run_ab():
    api_key = _load_api_key()
    print(f"LOCAL-278 Spine Model A/B Comparison")
    print(f"=" * 60)
    print(f"Venue: {VENUE_NAME}")
    print(f"Stops: {POI_LIST} ({TOTAL_STOPS} stops)")
    print(f"Models: {MODELS}")
    print(f"Runs per model: {RUNS_PER_MODEL}")
    print(f"=" * 60)
    print()
    
    results = {}  # model -> list of run results
    
    for model in MODELS:
        print(f"\n{'─' * 60}")
        print(f"Model: {model}")
        print(f"{'─' * 60}")
        results[model] = []
        
        for run_idx in range(RUNS_PER_MODEL):
            print(f"\n  Run {run_idx + 1}/{RUNS_PER_MODEL}...")
            
            start = time.time()
            spine = generate_spine(
                venue_name=VENUE_NAME,
                poi_list=POI_LIST,
                tour_category=TOUR_CATEGORY,
                api_key=api_key,
                model=model,
            )
            wall_time = time.time() - start
            
            cost_info = LAST_SPINE_COST.copy()
            quality = measure_quality(spine)
            
            run_result = {
                "run": run_idx + 1,
                "model": model,
                "cost_usd": cost_info["cost_usd"],
                "input_tokens": cost_info["input_tokens"],
                "output_tokens": cost_info["output_tokens"],
                "total_tokens": cost_info["total_tokens"],
                "latency_s": cost_info["latency_s"],
                "wall_time_s": wall_time,
                "quality": quality,
                "spine_valid": spine is not None,
            }
            results[model].append(run_result)
            
            print(f"    Cost: ${cost_info['cost_usd']:.4f} | "
                  f"Latency: {cost_info['latency_s']:.1f}s | "
                  f"Score: {quality.get('spine_score', '?')}/4 | "
                  f"Tokens: {cost_info['total_tokens']}")
            
            # Brief pause between runs to avoid rate limiting
            if run_idx < RUNS_PER_MODEL - 1:
                time.sleep(1)
        
        # Brief pause between models
        time.sleep(2)
    
    # ─── Summary report ──────────────────────────────────────────────────────
    print(f"\n\n{'=' * 60}")
    print(f"SUMMARY — LOCAL-278 Spine Model A/B")
    print(f"{'=' * 60}")
    print(f"\nVenue: {VENUE_NAME} | Stops: {TOTAL_STOPS} | Runs per model: {RUNS_PER_MODEL}")
    print()
    
    # Table header
    print(f"{'Model':<16} {'Cost (mean)':<12} {'Cost (range)':<16} "
          f"{'Latency':<10} {'Score':<12} {'Valid':<6}")
    print(f"{'─' * 16} {'─' * 12} {'─' * 16} {'─' * 10} {'─' * 12} {'─' * 6}")
    
    for model in MODELS:
        runs = results[model]
        costs = [r["cost_usd"] for r in runs]
        latencies = [r["latency_s"] for r in runs]
        scores = [r["quality"]["spine_score"] for r in runs if r["spine_valid"]]
        valid_count = sum(1 for r in runs if r["spine_valid"])
        
        mean_cost = sum(costs) / len(costs) if costs else 0
        min_cost = min(costs) if costs else 0
        max_cost = max(costs) if costs else 0
        mean_latency = sum(latencies) / len(latencies) if latencies else 0
        mean_score = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0
        
        print(f"{model:<16} ${mean_cost:.4f}     "
              f"${min_cost:.4f}-${max_cost:.4f}  "
              f"{mean_latency:.1f}s      "
              f"{mean_score:.1f} ({min_score}-{max_score})  "
              f"{valid_count}/{len(runs)}")
    
    # Cost comparison
    print(f"\n{'─' * 60}")
    print(f"COST RATIOS (relative to gpt-4o):")
    gpt4o_mean = sum(r["cost_usd"] for r in results["gpt-4o"]) / len(results["gpt-4o"])
    for model in MODELS:
        model_mean = sum(r["cost_usd"] for r in results[model]) / len(results[model])
        ratio = model_mean / gpt4o_mean if gpt4o_mean > 0 else 0
        print(f"  {model:<16}: {ratio:.2f}x ({ratio*100:.0f}% of gpt-4o cost)")
    
    # Quality detail
    print(f"\n{'─' * 60}")
    print(f"QUALITY DETAIL (per run):")
    for model in MODELS:
        print(f"\n  {model}:")
        for r in results[model]:
            q = r["quality"]
            status = "✓" if r["spine_valid"] else "✗"
            print(f"    Run {r['run']}: {status} score={q.get('spine_score', '?')}/4 "
                  f"hook={q.get('hook_length', 0)}ch "
                  f"revelation={q.get('revelation_length', 0)}ch "
                  f"angles={q.get('unique_angles', 0)} "
                  f"4-part={'✓' if q.get('four_part_present') else '✗'}")
    
    # Save raw results
    output_path = _ROOT / "tours" / "LOCAL278_spine_ab_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "config": {
                "venue": VENUE_NAME,
                "poi_list": POI_LIST,
                "tour_category": TOUR_CATEGORY,
                "models": MODELS,
                "runs_per_model": RUNS_PER_MODEL,
            },
            "results": results,
        }, f, indent=2, default=str)
    print(f"\n\nRaw results saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_ab()
