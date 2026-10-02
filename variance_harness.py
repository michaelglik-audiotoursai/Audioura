"""LOCAL-433: Measure story_count variance across repeated live runs.

Module-scope harness that:
  1. Runs generate_tour_text N times for a given venue
  2. Records per-stop story_count for each run
  3. Computes mean / min / max / stdev per stop
  4. Reports the distribution of the gate verdict (all-stops-pass frequency)

Import `compute_statistics` and `compute_gate_verdicts` for unit testing.
"""
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Statistics — testable at module scope with known inputs
# ---------------------------------------------------------------------------

def compute_statistics(values: List[int]) -> Dict[str, float]:
    """Compute mean, min, max, stdev for a list of integer values.

    Returns dict with keys: mean, min, max, stdev, count.
    Raises ValueError if values is empty.
    """
    if not values:
        raise ValueError("Cannot compute statistics on empty list")
    n = len(values)
    mean = sum(values) / n
    min_val = min(values)
    max_val = max(values)
    if n == 1:
        stdev = 0.0
    else:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stdev = math.sqrt(variance)
    return {
        'mean': round(mean, 2),
        'min': min_val,
        'max': max_val,
        'stdev': round(stdev, 2),
        'count': n,
    }


def compute_gate_verdicts(run_results: List[Dict[str, int]], threshold: int = 3) -> Dict[str, object]:
    """Compute gate verdict distribution across multiple runs.

    Args:
        run_results: list of dicts, each mapping stop_name -> story_count
        threshold: minimum story_count for a stop to pass (default: 3)

    Returns dict with:
        - per_stop_pass_rate: {stop_name: fraction of runs where stop >= threshold}
        - all_pass_count: number of runs where ALL stops passed
        - all_pass_rate: fraction of runs where ALL stops passed
        - total_runs: number of runs
        - per_stop_stats: {stop_name: {mean, min, max, stdev, count}}
    """
    if not run_results:
        raise ValueError("Cannot compute verdicts on empty run list")

    # Collect all stop names across runs (order by first appearance)
    all_stops = []
    seen = set()
    for run in run_results:
        for stop in run:
            if stop not in seen:
                all_stops.append(stop)
                seen.add(stop)

    total_runs = len(run_results)

    # Per-stop pass rate and statistics
    per_stop_pass_rate = {}
    per_stop_stats = {}
    for stop in all_stops:
        counts = [run.get(stop, 0) for run in run_results]
        passes = sum(1 for c in counts if c >= threshold)
        per_stop_pass_rate[stop] = round(passes / total_runs, 2)
        per_stop_stats[stop] = compute_statistics(counts)

    # All-stops-pass: every stop in that run >= threshold
    all_pass_count = 0
    for run in run_results:
        if all(count >= threshold for count in run.values()):
            all_pass_count += 1

    return {
        'per_stop_pass_rate': per_stop_pass_rate,
        'all_pass_count': all_pass_count,
        'all_pass_rate': round(all_pass_count / total_runs, 2),
        'total_runs': total_runs,
        'per_stop_stats': per_stop_stats,
    }


# ---------------------------------------------------------------------------
# Live run harness
# ---------------------------------------------------------------------------

def _load_env():
    """Load .env from ~/Audioura/.env if present."""
    env_path = Path.home() / "Audioura" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


def _set_generation_env():
    """Set environment variables for generation runs."""
    os.environ['STORIED_MODE'] = 'true'
    os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
    os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
    os.environ.pop('PYTEST_CURRENT_TEST', None)
    os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
    os.environ['AUDIOURA_DB_TARGET'] = 'production'
    os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
    os.environ['DISABLE_TOUR_CACHE'] = '1'


def extract_per_stop_counts(tour_text: str) -> Dict[str, int]:
    """Parse tour text and return {stop_name: story_count} using story_gate.

    This is the same logic as run_local432_live_palais.py but extracted for reuse.
    """
    from story_gate import extract_story_sentences

    stops = re.split(r'(?=^Stop\s+\d+:)', tour_text, flags=re.MULTILINE)
    stops = [s for s in stops if s.strip() and re.match(r'Stop\s+\d+:', s.strip())]

    result = {}
    for i, stop_block in enumerate(stops):
        header = re.match(r'Stop\s+\d+:\s*(.+?)(?:\n|$)', stop_block)
        stop_name = header.group(1).strip() if header else f"Stop {i+1}"

        # Extract description (the main content, not directions/sources/closing)
        desc_match = re.search(
            r'(?:Orientation:.*?\n\n)(.+?)(?:\n\s*Directions:|\n\s*Sources:|\n\s*Closing:|\Z)',
            stop_block, re.DOTALL
        )
        desc = desc_match.group(1).strip() if desc_match else stop_block

        story_sents = extract_story_sentences(desc)
        result[stop_name] = len(story_sents)

    return result


def run_single_generation(location: str, tour_type: str, total_stops: int,
                          output_dir: Path, run_index: int) -> Optional[Dict[str, int]]:
    """Run a single tour generation and return per-stop story counts.

    Returns None if generation fails.
    """
    from generate_tour_text import generate_tour_text

    output_file = str(output_dir / f"variance_run_{run_index}.json")

    result = generate_tour_text(
        location=location,
        tour_type=tour_type,
        output_file=output_file,
        total_stops=total_stops,
        persona=None,
    )

    if not result or not result[0]:
        return None

    tour_text = result[0]
    return extract_per_stop_counts(tour_text)


def run_variance_measurement(
    location: str,
    tour_type: str,
    total_stops: int,
    num_runs: int = 5,
    output_dir: Optional[Path] = None,
) -> Dict:
    """Run N generations of a venue and collect variance data.

    Returns a dict with:
        - venue: the location string
        - tour_type: museum/etc
        - total_stops: requested stops
        - num_runs: attempted runs
        - runs: list of {stop_name: story_count} per run
        - statistics: output of compute_gate_verdicts
        - timestamps: list of (start_time, elapsed_seconds) per run
    """
    if output_dir is None:
        output_dir = PROJECT_ROOT / "tours"
    output_dir.mkdir(parents=True, exist_ok=True)

    _load_env()
    _set_generation_env()

    runs = []
    timestamps = []

    for i in range(num_runs):
        print(f"\n{'='*60}")
        print(f"RUN {i+1}/{num_runs}: {location}")
        print(f"{'='*60}")

        start = time.time()
        counts = run_single_generation(location, tour_type, total_stops, output_dir, i)
        elapsed = time.time() - start

        if counts is None:
            print(f"  FAILED (elapsed: {elapsed:.1f}s)")
            timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed))
            continue

        runs.append(counts)
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed))

        # Print per-stop counts for this run
        for stop_name, count in counts.items():
            status = "✓" if count >= 3 else "✗"
            print(f"  {status} {stop_name[:55]:55s} story_count={count}")
        gate_pass = all(c >= 3 for c in counts.values())
        print(f"  Gate verdict: {'PASS' if gate_pass else 'FAIL'} "
              f"({sum(1 for c in counts.values() if c >= 3)}/{len(counts)} stops)")
        print(f"  Elapsed: {elapsed:.1f}s")

    # Compute statistics
    statistics = compute_gate_verdicts(runs) if runs else None

    return {
        'venue': location,
        'tour_type': tour_type,
        'total_stops': total_stops,
        'num_runs_attempted': num_runs,
        'num_runs_succeeded': len(runs),
        'runs': runs,
        'statistics': statistics,
        'timestamps': timestamps,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

VENUES = {
    'palais': {
        'location': 'Palais Lascaris, Nice',
        'tour_type': 'museum',
        'total_stops': 4,
    },
    'mfa_unbound': {
        'location': 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA',
        'tour_type': 'contained',
        'total_stops': 3,
    },
}


def main():
    """Run variance measurement for specified venues."""
    import argparse

    parser = argparse.ArgumentParser(description='Measure story_count variance')
    parser.add_argument('--venues', nargs='+', default=['palais', 'mfa_unbound'],
                        choices=list(VENUES.keys()),
                        help='Venues to measure')
    parser.add_argument('--runs', type=int, default=5,
                        help='Number of runs per venue')
    parser.add_argument('--output', type=str, default=None,
                        help='Output JSON file path')
    args = parser.parse_args()

    all_results = {}

    for venue_key in args.venues:
        venue = VENUES[venue_key]
        print(f"\n{'#'*70}")
        print(f"# VENUE: {venue['location']}")
        print(f"# Runs: {args.runs}")
        print(f"{'#'*70}")

        result = run_variance_measurement(
            location=venue['location'],
            tour_type=venue['tour_type'],
            total_stops=venue['total_stops'],
            num_runs=args.runs,
        )
        all_results[venue_key] = result

        # Print summary
        if result['statistics']:
            stats = result['statistics']
            print(f"\n{'='*60}")
            print(f"SUMMARY: {venue['location']}")
            print(f"{'='*60}")
            print(f"Runs completed: {result['num_runs_succeeded']}/{result['num_runs_attempted']}")
            print(f"All-stops-pass: {stats['all_pass_count']}/{stats['total_runs']} "
                  f"({stats['all_pass_rate']*100:.0f}%)")
            print(f"\nPer-stop statistics:")
            for stop_name, stop_stats in stats['per_stop_stats'].items():
                pass_rate = stats['per_stop_pass_rate'][stop_name]
                print(f"  {stop_name[:50]:50s} "
                      f"mean={stop_stats['mean']:.1f} "
                      f"min={stop_stats['min']} max={stop_stats['max']} "
                      f"stdev={stop_stats['stdev']:.2f} "
                      f"pass_rate={pass_rate*100:.0f}%")

    # Save JSON artifact
    output_path = args.output or str(PROJECT_ROOT / "local433_variance_data.json")
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nJSON artifact saved: {output_path}")


if __name__ == '__main__':
    main()
