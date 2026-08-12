"""run_local440_acceptance.py — LOCAL-440: Story-first generation acceptance.

Live run with:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true

Reports:
  1. MFA Unbound (3 stops): per-stop D394 gate results, target 3/3
  2. Palais Lascaris control: per-stop gate results + date checks
  3. Wall time (end-to-end, must not regress past ~336s baseline)
  4. Cost (LLM + fetch per tour)
"""
import json
import os
import sys
import time
import contextlib
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Environment for live run
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['STORIED_MODE'] = 'true'
os.environ['GENERATION_TIER'] = 'plus'

from generate_tour_text import generate_tour_text
from story_gate import verify_tour_stories, get_classification_cost, reset_classification_cost
from story_first import get_pipeline_cost, reset_pipeline_cost


def run_tour(location: str, num_stops: int, label: str) -> dict:
    """Run a tour and return generation result + timing."""
    print(f"\n{'='*70}")
    print(f"  {label}: {location}, {num_stops} stops")
    print(f"{'='*70}")

    reset_classification_cost()
    reset_pipeline_cost()

    output_file = str(PROJECT_ROOT / 'tours' / f'local440_{label.lower().replace(" ", "_")}.txt')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    captured = StringIO()
    start = time.time()

    with contextlib.redirect_stdout(captured):
        result = generate_tour_text(
            location=location,
            total_stops=num_stops,
            tour_type='contained',
            output_file=output_file,
        )

    elapsed = time.time() - start
    output_log = captured.getvalue()

    # Save the generation log
    log_path = str(PROJECT_ROOT / f'local440_{label.lower().replace(" ", "_")}_log.txt')
    with open(log_path, 'w') as f:
        f.write(output_log)
    print(f"  Generation log saved to: {log_path}")
    print(f"  Wall time: {elapsed:.1f}s")

    classification_cost = get_classification_cost()
    pipeline_cost = get_pipeline_cost()

    return {
        'label': label,
        'location': location,
        'result': result,
        'elapsed_seconds': elapsed,
        'classification_cost': classification_cost,
        'pipeline_cost': pipeline_cost,
        'output_log': output_log,
    }


def evaluate_gate(tour_text: str, label: str) -> dict:
    """Run story gate on tour text, report per-stop results."""
    if not tour_text:
        return {'label': label, 'stops_passed': 0, 'total_stops': 0, 'details': []}

    gate_result = verify_tour_stories(tour_text, credit_lines={})

    stop_results = gate_result.get('stop_results', [])
    total_stops = len(stop_results)
    stops_passed = sum(1 for s in stop_results if s.get('passed'))
    summary = gate_result.get('summary', '')

    print(f"\n  Story gate: {stops_passed}/{total_stops} stops passed")
    print(f"  Summary: {summary}")
    for stop in stop_results:
        status = '✓' if stop.get('passed') else '✗'
        name = stop.get('stop_name', 'unknown')[:50]
        print(f"    {status} {name}")

    return {
        'label': label,
        'stops_passed': stops_passed,
        'total_stops': total_stops,
        'details': stop_results,
        'summary': summary,
    }


def main():
    print("=" * 70)
    print("  LOCAL-440 ACCEPTANCE: Story-first generation")
    print("=" * 70)

    results = {}

    # ── MFA Unbound (3 stops) ──
    mfa = run_tour(
        location="Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA",
        num_stops=3,
        label="MFA Unbound",
    )
    results['mfa'] = mfa

    # Extract tour text for gate check
    mfa_text = ''
    if isinstance(mfa['result'], tuple):
        mfa_text = mfa['result'][0] or ''
    elif isinstance(mfa['result'], dict):
        mfa_text = mfa['result'].get('tour_text', '') or mfa['result'].get('text', '')
    elif isinstance(mfa['result'], str):
        mfa_text = mfa['result']
    # Fallback: read from output file
    if not mfa_text:
        mfa_file = str(PROJECT_ROOT / 'tours' / 'local440_mfa_unbound.txt')
        if os.path.exists(mfa_file):
            with open(mfa_file, 'r') as f:
                mfa_text = f.read()

    mfa_gate = evaluate_gate(mfa_text, "MFA Unbound")
    results['mfa_gate'] = mfa_gate

    # ── Palais Lascaris control ──
    palais = run_tour(
        location="Palais Lascaris, Nice, France",
        num_stops=4,
        label="Palais Lascaris",
    )
    results['palais'] = palais

    palais_text = ''
    if isinstance(palais['result'], tuple):
        palais_text = palais['result'][0] or ''
    elif isinstance(palais['result'], dict):
        palais_text = palais['result'].get('tour_text', '') or palais['result'].get('text', '')
    elif isinstance(palais['result'], str):
        palais_text = palais['result']
    # Fallback: read from output file
    if not palais_text:
        palais_file = str(PROJECT_ROOT / 'tours' / 'local440_palais_lascaris.txt')
        if os.path.exists(palais_file):
            with open(palais_file, 'r') as f:
                palais_text = f.read()

    palais_gate = evaluate_gate(palais_text, "Palais Lascaris")
    results['palais_gate'] = palais_gate

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    print(f"\n  MFA Unbound:")
    print(f"    Gate: {mfa_gate['stops_passed']}/{mfa_gate['total_stops']} (target: 3/3)")
    print(f"    Wall time: {mfa['elapsed_seconds']:.1f}s")
    print(f"    Story-first cost: ${mfa['pipeline_cost']['total_cost_usd']:.4f}")
    print(f"    Classification cost: ${mfa['classification_cost']['total_cost_usd']:.4f}")

    print(f"\n  Palais Lascaris:")
    print(f"    Gate: {palais_gate['stops_passed']}/{palais_gate['total_stops']}")
    print(f"    Wall time: {palais['elapsed_seconds']:.1f}s")
    print(f"    Story-first cost: ${palais['pipeline_cost']['total_cost_usd']:.4f}")
    print(f"    Classification cost: ${palais['classification_cost']['total_cost_usd']:.4f}")

    total_time = mfa['elapsed_seconds'] + palais['elapsed_seconds']
    print(f"\n  Total wall time: {total_time:.1f}s")
    print(f"  Baseline (D396): ~336s Palais alone")

    # Save results
    output = {
        'mfa_gate_result': f"{mfa_gate['stops_passed']}/{mfa_gate['total_stops']}",
        'palais_gate_result': f"{palais_gate['stops_passed']}/{palais_gate['total_stops']}",
        'mfa_wall_time_s': round(mfa['elapsed_seconds'], 1),
        'palais_wall_time_s': round(palais['elapsed_seconds'], 1),
        'mfa_story_first_cost': mfa['pipeline_cost']['total_cost_usd'],
        'palais_story_first_cost': palais['pipeline_cost']['total_cost_usd'],
    }

    output_path = str(PROJECT_ROOT / 'local440_acceptance_results.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to: {output_path}")


if __name__ == '__main__':
    main()
