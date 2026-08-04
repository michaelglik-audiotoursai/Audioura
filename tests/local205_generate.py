#!/usr/bin/env python3
"""LOCAL-205: Model A/B on Musée Matisse (COVERED stops).

This script runs INSIDE the tour-generator container via docker exec.
It bypasses the S20 cache by unsetting DATABASE_URL.
It captures the generated text paragraphs for each arm/run.

Usage (from host):
    docker exec -e DATABASE_URL= -e STORIED_MODE=true \
        -e TOUR_LLM_MODEL=gpt-3.5-turbo \
        audioura-tour-generator-1 python3 /app/tests/local205_generate.py A 1
"""
import os
import sys
import json
import time

# Force cache bypass: unset DATABASE_URL if somehow still present
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

# Ensure STORIED_MODE=true
os.environ['STORIED_MODE'] = 'true'

def main():
    arm = sys.argv[1]  # 'A' or 'B'
    run_num = sys.argv[2]  # '1', '2', '3'
    
    model = os.environ.get('TOUR_LLM_MODEL', 'gpt-3.5-turbo')
    print(f"=== LOCAL-205: Arm {arm}, Run {run_num}, Model: {model} ===")
    print(f"DATABASE_URL set: {'DATABASE_URL' in os.environ}")
    print(f"STORIED_MODE: {os.environ.get('STORIED_MODE')}")
    print(f"TOUR_LLM_MODEL: {model}")
    
    from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
    
    start = time.time()
    
    tour_text, output_file, coordinates = generate_tour_text(
        location="Musée Matisse, Nice, France",
        tour_type="museum",
        output_file=f"/tmp/local205_arm{arm}_run{run_num}.txt",
        total_stops=2,
        persona=None,
    )
    
    elapsed = time.time() - start
    
    # Get cost info
    cost_info = _LAST_GENERATION_COST.copy()
    
    # Output structured result
    result = {
        "arm": arm,
        "run": int(run_num),
        "model": model,
        "elapsed_seconds": round(elapsed, 1),
        "cost_info": cost_info,
        "tour_text_length": len(tour_text) if tour_text else 0,
        "success": tour_text is not None,
    }
    
    print(f"\n{'='*60}")
    print(f"RESULT_JSON: {json.dumps(result)}")
    print(f"{'='*60}")
    
    if tour_text:
        print(f"\nTOUR_TEXT_START")
        print(tour_text)
        print(f"TOUR_TEXT_END")
    else:
        print("ERROR: No tour text generated!")
        sys.exit(1)

if __name__ == '__main__':
    main()
