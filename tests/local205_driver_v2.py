#!/usr/bin/env python3
"""LOCAL-205 v2 driver: run all 6 generations and save paragraphs.

Runs from the HOST (not inside Docker). Invokes docker exec for each run.
Saves tour text to tests/local205_paragraphs_v2/.
"""
import subprocess
import os
import json
import time
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local205_paragraphs_v2')
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODELS = {
    'A': 'gpt-3.5-turbo',
    'B': 'gpt-4o-mini',
}

RUNS_PER_ARM = 3


def run_generation(arm, run_num):
    """Run one generation via docker exec. Returns (tour_text, result_json, raw_output)."""
    model = MODELS[arm]
    print(f"\n{'='*60}")
    print(f"  ARM {arm} ({model}), Run {run_num}")
    print(f"{'='*60}")

    cmd = [
        'docker', 'exec',
        '-e', 'DATABASE_URL=',
        '-e', 'STORIED_MODE=true',
        '-e', f'TOUR_LLM_MODEL={model}',
        'audioura-tour-generator-1',
        'python3', '/app/local205_gen_v2.py', arm, str(run_num)
    ]

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - t0

    raw_output = result.stdout
    if result.returncode != 0:
        print(f"  ERROR (exit {result.returncode}): {result.stderr[:200]}")
        return None, None, raw_output

    # Extract RESULT_JSON
    result_json = None
    for line in raw_output.split('\n'):
        if line.startswith('RESULT_JSON:'):
            result_json = json.loads(line.replace('RESULT_JSON: ', ''))
            break

    # Extract tour text
    tour_text = None
    if 'TOUR_TEXT_START' in raw_output and 'TOUR_TEXT_END' in raw_output:
        start = raw_output.index('TOUR_TEXT_START') + len('TOUR_TEXT_START\n')
        end = raw_output.index('TOUR_TEXT_END')
        tour_text = raw_output[start:end].strip()

    if tour_text:
        # Save to file
        out_path = os.path.join(OUTPUT_DIR, f'{arm}{run_num}_tour_text.txt')
        with open(out_path, 'w') as f:
            f.write(tour_text)
        print(f"  Saved: {out_path}")
        print(f"  Elapsed: {elapsed:.1f}s, Chars: {len(tour_text)}")
    else:
        print(f"  WARNING: No tour text extracted!")
        # Save raw output for debugging
        debug_path = os.path.join(OUTPUT_DIR, f'{arm}{run_num}_raw_output.txt')
        with open(debug_path, 'w') as f:
            f.write(raw_output)
        print(f"  Raw output saved to {debug_path}")

    return tour_text, result_json, raw_output


def main():
    print("LOCAL-205 v2: Model A/B on Musée Matisse (COVERED stops)")
    print(f"  ARM A: {MODELS['A']}")
    print(f"  ARM B: {MODELS['B']}")
    print(f"  Runs per arm: {RUNS_PER_ARM}")
    print(f"  Output: {OUTPUT_DIR}")

    # Check container is running
    check = subprocess.run(
        ['docker', 'exec', 'audioura-tour-generator-1', 'echo', 'ok'],
        capture_output=True, text=True
    )
    if check.returncode != 0:
        print("ERROR: tour-generator container not running!")
        sys.exit(1)

    # Ensure gen script is in container
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local205_gen_v2.py')
    subprocess.run(['docker', 'cp', script_path, 'audioura-tour-generator-1:/app/local205_gen_v2.py'], check=True)
    print("  Script copied to container.")

    all_results = {}
    total_cost = 0.0

    for arm in ['A', 'B']:
        all_results[arm] = []
        for run_num in range(1, RUNS_PER_ARM + 1):
            tour_text, result_json, raw_output = run_generation(arm, run_num)
            all_results[arm].append({
                'tour_text': tour_text,
                'result_json': result_json,
                'raw_output_len': len(raw_output) if raw_output else 0,
            })

            # Track cost from result_json (if available)
            if result_json and result_json.get('cost_info'):
                ci = result_json['cost_info']
                # The container reports 0 cost due to D68; we'll compute real cost later
                pass

    # Save all results metadata
    meta_path = os.path.join(OUTPUT_DIR, 'generation_metadata.json')
    meta = {
        'models': MODELS,
        'runs_per_arm': RUNS_PER_ARM,
        'venue': 'Musée Matisse, Nice, France',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    for arm in ['A', 'B']:
        meta[f'arm_{arm}_results'] = [
            r['result_json'] for r in all_results[arm] if r['result_json']
        ]
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"\nMetadata saved: {meta_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*60}")
    for arm in ['A', 'B']:
        successes = sum(1 for r in all_results[arm] if r['tour_text'])
        print(f"  ARM {arm} ({MODELS[arm]}): {successes}/{RUNS_PER_ARM} successful")
    print(f"\n  Files in {OUTPUT_DIR}:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        print(f"    {f}")


if __name__ == '__main__':
    main()
