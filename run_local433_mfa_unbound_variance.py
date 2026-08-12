#!/usr/bin/env python3
"""LOCAL-433: Run MFA Unbound variance measurement with pinned page fetch.

Same as variance_harness.py but applies the page-fetch pin from
run_mfa_unbound_pinned.py — mfa.org returns HTTP 429, so without the
captured page bytes the tour cannot resolve its works.

This is still a live run through the real pipeline: GPT-4o generates
fresh content each time. Only the exhibition page fetch is stubbed.
"""
import os
import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# --- Environment ---
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

# --- Apply page-fetch pin (same as run_mfa_unbound_pinned.py) ---
import exhibition_checklist
from exhibition_checklist import ExhibitionChecklistResult, prose_llm_extract_works

FIXTURE = str(PROJECT_ROOT / "tests" / "fixtures" / "mfa_unbound_page_text.txt")
PAGE_URL = "https://www.mfa.org/exhibition/picasso-miro-dali-unbound"

_real_find = exhibition_checklist.find_exhibition_checklist


def _pinned_find(venue_base_url, exhibition_name, venue_name='', venue_language='en'):
    """Try real lookup first; fall back to captured page if it fails."""
    try:
        res = _real_find(venue_base_url, exhibition_name, venue_name, venue_language)
        if res and res.works:
            return res
    except Exception:
        pass

    page_text = open(FIXTURE, encoding="utf-8").read()
    works = prose_llm_extract_works(page_text, "Picasso, Miró, Dalí: Unbound")

    res = ExhibitionChecklistResult()
    res.works = works
    res.path = 'prose_llm'
    res.page_shape = 'prose_llm_extraction'
    res.exhibition_url = PAGE_URL
    res.page_text = page_text
    res.reason = f'PINNED: {len(works)} works from captured page (HTTP 429 live)'
    return res


exhibition_checklist.find_exhibition_checklist = _pinned_find

# --- Now import the harness functions ---
from variance_harness import (
    extract_per_stop_counts, compute_gate_verdicts, run_single_generation
)
from generate_tour_text import generate_tour_text

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
TOUR_TYPE = "museum"
TOTAL_STOPS = 3
NUM_RUNS = 5

OUTPUT_DIR = PROJECT_ROOT / "tours"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"{'#'*70}")
print(f"# LOCAL-433: MFA Unbound Variance Measurement (page-fetch pinned)")
print(f"# Location: {LOCATION}")
print(f"# Stops: {TOTAL_STOPS}, Runs: {NUM_RUNS}")
print(f"{'#'*70}")

runs = []
timestamps = []

for i in range(NUM_RUNS):
    print(f"\n{'='*60}")
    print(f"RUN {i+1}/{NUM_RUNS}: {LOCATION}")
    print(f"{'='*60}")

    start = time.time()
    output_file = str(OUTPUT_DIR / f"mfa_unbound_variance_run_{i}.json")

    result = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        output_file=output_file,
        total_stops=TOTAL_STOPS,
        persona=None,
    )

    elapsed = time.time() - start

    if not result or not result[0]:
        print(f"  FAILED (elapsed: {elapsed:.1f}s)")
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed))
        continue

    tour_text = result[0]
    counts = extract_per_stop_counts(tour_text)

    if counts:
        runs.append(counts)
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed))

        for stop_name, count in counts.items():
            status = "✓" if count >= 3 else "✗"
            print(f"  {status} {stop_name[:55]:55s} story_count={count}")
        gate_pass = all(c >= 3 for c in counts.values())
        print(f"  Gate verdict: {'PASS' if gate_pass else 'FAIL'} "
              f"({sum(1 for c in counts.values() if c >= 3)}/{len(counts)} stops)")
        print(f"  Elapsed: {elapsed:.1f}s")
    else:
        print(f"  No stops parsed (elapsed: {elapsed:.1f}s)")
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed))

# --- Compute and report ---
if runs:
    stats = compute_gate_verdicts(runs)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {LOCATION}")
    print(f"{'='*60}")
    print(f"Runs completed: {len(runs)}/{NUM_RUNS}")
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
    artifact = {
        'venue': LOCATION,
        'tour_type': TOUR_TYPE,
        'total_stops': TOTAL_STOPS,
        'num_runs_attempted': NUM_RUNS,
        'num_runs_succeeded': len(runs),
        'runs': runs,
        'statistics': stats,
        'timestamps': timestamps,
        'note': 'page-fetch pinned (mfa.org HTTP 429); generation pipeline is live'
    }
    output_path = str(PROJECT_ROOT / "local433_variance_mfa_unbound.json")
    with open(output_path, 'w') as f:
        json.dump(artifact, f, indent=2)
    print(f"\nJSON artifact saved: {output_path}")
else:
    print("\nNo successful runs — cannot compute statistics.")
