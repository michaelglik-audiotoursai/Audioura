#!/usr/bin/env python3
"""LOCAL-395: Palais Lascaris regression confirmation.

Read-only diagnostics: generate Palais Lascaris n=4 three times on current
`storied` (2f60210) and three times on pre-chain (d91a5c6), score all six,
report means and ranges.

No production code is modified. This script runs from the host.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
PRE_CHAIN_ROOT = Path("/tmp/palais-pre-chain")
TOURS_DIR = PROJECT_ROOT / "tours"
TOURS_DIR.mkdir(exist_ok=True)

# --- Environment setup ---
_env_path = Path.home() / "Audioura" / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Parameters matching the control runs
LOCATION = "Palais Lascaris, Nice"
TOUR_TYPE = "museum"
TOTAL_STOPS = 4
N_RUNS = 3


def generate_one_tour(code_root: Path, output_file: Path, run_label: str):
    """Generate a single tour using code from `code_root`."""
    print(f"\n{'='*70}")
    print(f"  GENERATING: {run_label}")
    print(f"  Code root: {code_root}")
    print(f"  Output: {output_file}")
    print(f"{'='*70}")

    # We run generation as a subprocess with the correct sys.path
    script = f"""
import sys, os
sys.path.insert(0, {str(code_root)!r})
os.chdir({str(code_root)!r})

# Env vars are inherited from parent
from generate_tour_text import generate_tour_text

result = generate_tour_text(
    location={LOCATION!r},
    tour_type={TOUR_TYPE!r},
    output_file={str(output_file)!r},
    total_stops={TOTAL_STOPS},
    persona=None,
)

if result and result[0]:
    print("SUCCESS")
    sys.exit(0)
else:
    print("FAILED")
    sys.exit(1)
"""
    env = os.environ.copy()
    env['PYTHONPATH'] = str(code_root)

    start = time.time()
    proc = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True, text=True, timeout=600,
        env=env, cwd=str(code_root)
    )
    elapsed = time.time() - start

    if proc.returncode != 0:
        print(f"  FAILED after {elapsed:.1f}s")
        print(f"  STDOUT (last 2000): {proc.stdout[-2000:]}")
        print(f"  STDERR (last 1000): {proc.stderr[-1000:]}")
        return False

    print(f"  Generated in {elapsed:.1f}s")
    # Count gate removals and beat retries from stdout
    stdout = proc.stdout
    gate_removals = stdout.count("REMOVED") + stdout.count("stripped")
    beat_retries = stdout.count("beat retry") + stdout.count("RETRY") + stdout.count("regenerat")
    word_floor_retries = stdout.count("word floor") + stdout.count("WORD_FLOOR") + stdout.count("under 120")
    print(f"  Gate removals (approx): {gate_removals}")
    print(f"  Beat retries (approx): {beat_retries}")
    print(f"  Word-floor retries (approx): {word_floor_retries}")

    # Save log
    log_file = output_file.with_suffix('.log')
    with open(log_file, 'w') as f:
        f.write(stdout)
        if proc.stderr:
            f.write("\n\n=== STDERR ===\n")
            f.write(proc.stderr)

    return True


def score_one_tour(tour_file: Path) -> dict:
    """Score a tour file and return the results."""
    sys.path.insert(0, str(PROJECT_ROOT))
    # Import fresh each time to avoid stale state
    from tour_rubric_scorer import score_tour_file, print_score
    
    try:
        ts = score_tour_file(str(tour_file), TOTAL_STOPS)
        return {
            'base_score': ts.base_score,
            'per_stop_base': ts.per_stop_base,
            'quality': getattr(ts, 'quality', None),
            'total_score': ts.total_score,
            'n_delivered': ts.n_delivered,
        }
    except Exception as e:
        return {'error': str(e)}


def main():
    print("="*70)
    print("LOCAL-395: PALAIS LASCARIS REGRESSION CONFIRMATION")
    print("="*70)
    print(f"  Location: {LOCATION}")
    print(f"  Stops: {TOTAL_STOPS}")
    print(f"  Runs per commit: {N_RUNS}")
    print(f"  Current commit: 2f60210 (code at {PROJECT_ROOT})")
    print(f"  Pre-chain commit: d91a5c6 (code at {PRE_CHAIN_ROOT})")
    print()

    # Verify pre-chain worktree exists
    if not (PRE_CHAIN_ROOT / "generate_tour_text.py").exists():
        print(f"ERROR: Pre-chain worktree not found at {PRE_CHAIN_ROOT}")
        print("Run: git worktree add /tmp/palais-pre-chain d91a5c6 --detach")
        sys.exit(1)

    results = {
        'current': [],   # 2f60210
        'pre_chain': [], # d91a5c6
    }

    # --- Generate on CURRENT (2f60210) ---
    print("\n" + "="*70)
    print("PHASE 1: Generating 3 runs on CURRENT storied (2f60210)")
    print("="*70)

    for i in range(1, N_RUNS + 1):
        output = TOURS_DIR / f"LOCAL395_palais_current_run{i}.txt"
        ok = generate_one_tour(PROJECT_ROOT, output, f"current run {i}/{N_RUNS}")
        if ok and output.exists():
            score = score_one_tour(output)
            results['current'].append({
                'run': i,
                'file': str(output),
                'score': score,
            })
            print(f"  → base_score = {score.get('base_score', 'ERROR')}")
        else:
            results['current'].append({'run': i, 'file': str(output), 'score': {'error': 'generation failed'}})

    # --- Generate on PRE-CHAIN (d91a5c6) ---
    print("\n" + "="*70)
    print("PHASE 2: Generating 3 runs on PRE-CHAIN (d91a5c6)")
    print("="*70)

    for i in range(1, N_RUNS + 1):
        output = TOURS_DIR / f"LOCAL395_palais_prechain_run{i}.txt"
        ok = generate_one_tour(PRE_CHAIN_ROOT, output, f"pre-chain run {i}/{N_RUNS}")
        if ok and output.exists():
            score = score_one_tour(output)
            results['pre_chain'].append({
                'run': i,
                'file': str(output),
                'score': score,
            })
            print(f"  → base_score = {score.get('base_score', 'ERROR')}")
        else:
            results['pre_chain'].append({'run': i, 'file': str(output), 'score': {'error': 'generation failed'}})

    # --- REPORT ---
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)

    def extract_scores(group):
        return [r['score']['base_score'] for r in group
                if 'base_score' in r.get('score', {})]

    current_scores = extract_scores(results['current'])
    prechain_scores = extract_scores(results['pre_chain'])

    print(f"\n  CURRENT (2f60210) — {len(current_scores)} successful runs:")
    for r in results['current']:
        s = r['score']
        if 'base_score' in s:
            print(f"    run {r['run']}: base={s['base_score']:.1f}  per_stop={s.get('per_stop_base', [])}")
        else:
            print(f"    run {r['run']}: ERROR — {s.get('error', 'unknown')}")

    if current_scores:
        print(f"    MEAN: {sum(current_scores)/len(current_scores):.1f}")
        print(f"    RANGE: [{min(current_scores):.1f}, {max(current_scores):.1f}]")

    print(f"\n  PRE-CHAIN (d91a5c6) — {len(prechain_scores)} successful runs:")
    for r in results['pre_chain']:
        s = r['score']
        if 'base_score' in s:
            print(f"    run {r['run']}: base={s['base_score']:.1f}  per_stop={s.get('per_stop_base', [])}")
        else:
            print(f"    run {r['run']}: ERROR — {s.get('error', 'unknown')}")

    if prechain_scores:
        print(f"    MEAN: {sum(prechain_scores)/len(prechain_scores):.1f}")
        print(f"    RANGE: [{min(prechain_scores):.1f}, {max(prechain_scores):.1f}]")

    # --- VERDICT ---
    print(f"\n  {'='*50}")
    if current_scores and prechain_scores:
        current_mean = sum(current_scores) / len(current_scores)
        prechain_mean = sum(prechain_scores) / len(prechain_scores)
        delta = current_mean - prechain_mean
        print(f"  DELTA (current - pre_chain): {delta:+.1f}")

        # Is the drop within normal variance?
        # Earlier evening range was 68.8–81.2 (spread of 12.4)
        # If delta is less than half the observed range, it's plausibly variance
        observed_spread = 12.4  # from the task description
        if abs(delta) <= observed_spread / 2:
            print(f"  VERDICT: Delta ({delta:+.1f}) is WITHIN normal variance (±{observed_spread/2:.1f})")
            print(f"           The drop is likely random LLM variation, not a code regression.")
        else:
            print(f"  VERDICT: Delta ({delta:+.1f}) EXCEEDS normal variance (±{observed_spread/2:.1f})")
            print(f"           This suggests a real regression introduced between d91a5c6 and 2f60210.")
    else:
        print("  VERDICT: Insufficient data — some runs failed.")
    print(f"  {'='*50}")

    # Save structured results
    results_file = TOURS_DIR / "LOCAL395_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full results saved: {results_file}")

    return results


if __name__ == "__main__":
    main()
