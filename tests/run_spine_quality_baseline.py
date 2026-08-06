#!/usr/bin/env python3
"""
LOCAL-111: Baseline measurement — score real spines before wiring the quality gate.

Runs 5 spine generations, scores each with score_spine(), and reports the 
distribution. This determines what threshold makes sense.

Usage:
    source .env && python3 tests/test_spine_quality_baseline.py
"""
import sys
import os
import json
import time

# Resolve imports from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STORIED_MODE", "true")

from spine_generator import generate_spine
from spine_quality_scorer import score_spine

API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not set")
    sys.exit(1)

# Test venues — diverse categories to see score variance
TEST_CASES = [
    {
        "venue_name": "Musée Matisse, Nice, France",
        "poi_list": ["Blue Nude II", "The Sorrows of the King", "Still Life with Pomegranates", 
                     "Interior with Egyptian Curtain", "Woman Reading"],
        "tour_category": "museum",
    },
    {
        "venue_name": "Old Montreal Walking Tour",
        "poi_list": ["Notre-Dame Basilica", "Place Jacques-Cartier", "Bonsecours Market",
                     "Old Port Clock Tower", "Château Ramezay", "Place d'Armes"],
        "tour_category": "walking",
    },
    {
        "venue_name": "Uffizi Gallery, Florence",
        "poi_list": ["Birth of Venus", "Primavera", "Annunciation", 
                     "Doni Tondo", "Venus of Urbino", "Medusa"],
        "tour_category": "museum",
    },
    {
        "venue_name": "Greenwich Village, New York",
        "poi_list": ["Washington Square Arch", "Stonewall Inn", "Bleecker Street",
                     "Jefferson Market Library", "Minetta Lane"],
        "tour_category": "walking",
    },
    {
        "venue_name": "Chagall Museum, Nice",
        "poi_list": ["Song of Songs I", "Song of Songs II", "Song of Songs III",
                     "Song of Songs IV", "Song of Songs V", "The Creation"],
        "tour_category": "museum",
    },
]

print("=" * 70)
print("LOCAL-111: Spine Quality Baseline Measurement")
print("=" * 70)
print(f"Generating {len(TEST_CASES)} spines and scoring each...\n")

results = []
total_cost = 0.0

for i, tc in enumerate(TEST_CASES, 1):
    print(f"\n--- Run {i}/{len(TEST_CASES)}: {tc['venue_name']} ({tc['tour_category']}) ---")
    start = time.time()
    
    spine = generate_spine(
        venue_name=tc["venue_name"],
        poi_list=tc["poi_list"],
        tour_category=tc["tour_category"],
        api_key=API_KEY,
    )
    
    elapsed = time.time() - start
    
    if spine is None:
        print(f"  FAILED: generate_spine returned None")
        results.append({"venue": tc["venue_name"], "score": None, "breakdown": {}, "elapsed": elapsed})
        continue
    
    score, breakdown = score_spine(spine, total_stops=len(tc["poi_list"]))
    
    print(f"  Score: {score}/4")
    print(f"  Breakdown: {json.dumps(breakdown)}")
    print(f"  Arc entries: {len(spine.get('arc', []))}")
    print(f"  Climax stop: {spine.get('climax_stop', '?')}")
    print(f"  Tour hook: {spine.get('tour_hook', '')[:80]}...")
    print(f"  Closing revelation: {spine.get('closing_revelation', '')[:80]}...")
    print(f"  Time: {elapsed:.1f}s")
    
    results.append({
        "venue": tc["venue_name"],
        "score": score,
        "breakdown": breakdown,
        "elapsed": elapsed,
        "arc_count": len(spine.get("arc", [])),
        "climax_stop": spine.get("climax_stop"),
        "total_stops": len(tc["poi_list"]),
    })

print("\n" + "=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)

scores = [r["score"] for r in results if r["score"] is not None]
if scores:
    print(f"\nScores: {scores}")
    print(f"Mean: {sum(scores)/len(scores):.2f}")
    print(f"Min: {min(scores)}, Max: {max(scores)}")
    print(f"Distribution: " + ", ".join(f"{s}/4" for s in scores))
    
    # Per-criterion pass rates
    criteria = ["climax_position", "unique_emotional_beats", "valid_callbacks", "closing_revelation_length"]
    print(f"\nPer-criterion pass rate:")
    for c in criteria:
        passes = sum(1 for r in results if r["breakdown"].get(c, False))
        print(f"  {c}: {passes}/{len(scores)} ({passes/len(scores)*100:.0f}%)")
else:
    print("No successful generations!")

print(f"\nTotal generations: {len(results)}")
print(f"Failures: {sum(1 for r in results if r['score'] is None)}")
print(f"Total time: {sum(r['elapsed'] for r in results):.1f}s")
