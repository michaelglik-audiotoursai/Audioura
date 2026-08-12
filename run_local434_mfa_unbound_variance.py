#!/usr/bin/env python3
"""LOCAL-434: Measure MFA Unbound variance through the REAL pipeline.

No pinning. No monkeypatching find_exhibition_checklist. The venue page
is reachable via Wayback Machine (D381/D382/D387), so the production path
works without intervention.

Uses variance_harness.py — same shape as LOCAL-433's Palais measurement.
≥5 live runs, per-stop story_count, committed JSON, mean/min/max/stdev.
"""
import json
import os
import sys
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

# --- Import the harness (NO monkeypatching) ---
from variance_harness import (
    extract_per_stop_counts, compute_gate_verdicts, run_single_generation
)
from generate_tour_text import generate_tour_text

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
TOUR_TYPE = "contained"
TOTAL_STOPS = 3
NUM_RUNS = 5

OUTPUT_DIR = PROJECT_ROOT / "tours"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"{'#'*70}")
print(f"# LOCAL-434: MFA Unbound Variance — REAL PIPELINE (no pin)")
print(f"# Location: {LOCATION}")
print(f"# Tour type: {TOUR_TYPE}")
print(f"# Stops: {TOTAL_STOPS}, Runs: {NUM_RUNS}")
print(f"# No monkeypatching. Wayback fallback is the production path (D381).")
print(f"{'#'*70}")

runs = []
timestamps = []
provenance_lines = []
blocker4b_events = []

for i in range(NUM_RUNS):
    print(f"\n{'='*60}")
    print(f"RUN {i+1}/{NUM_RUNS}: {LOCATION}")
    print(f"{'='*60}")

    start = time.time()
    output_file = str(OUTPUT_DIR / f"local434_mfa_run_{i}.json")

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
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed, 'FAILED'))
        # Check if BLOCKER4b fired by looking at clean-fail evidence
        try:
            from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
            if _LAST_CLEAN_FAIL_EVIDENCE.get('error_type') == 'address_scatter':
                event = {
                    'run': i + 1,
                    'fired': True,
                    'unique_addresses': _LAST_CLEAN_FAIL_EVIDENCE.get('unique_addresses'),
                    'venue_name': _LAST_CLEAN_FAIL_EVIDENCE.get('venue_name'),
                    'tier': _LAST_CLEAN_FAIL_EVIDENCE.get('tier'),
                }
                blocker4b_events.append(event)
                print(f"  [BLOCKER4b] FIRED — {event['unique_addresses']} distinct addresses")
            else:
                blocker4b_events.append({
                    'run': i + 1,
                    'fired': False,
                    'failure_type': _LAST_CLEAN_FAIL_EVIDENCE.get('error_type', 'unknown'),
                })
        except (ImportError, AttributeError):
            blocker4b_events.append({'run': i + 1, 'fired': 'unknown'})
        continue

    tour_text = result[0]
    counts = extract_per_stop_counts(tour_text)

    # Look for Wayback provenance in the output
    prov_line = None
    if os.path.exists(output_file):
        try:
            with open(output_file) as f:
                content = f.read()
            # The JSON file from generate_tour_text may have provenance info
            # Also check stdout capture for Wayback markers
        except Exception:
            pass
    # Scan the tour text itself for provenance markers
    for line in tour_text.splitlines():
        if 'wayback' in line.lower() or 'web.archive.org' in line.lower():
            prov_line = line.strip()
            break

    if counts:
        runs.append(counts)
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed, 'OK'))
        blocker4b_events.append({'run': i + 1, 'fired': False, 'note': 'tour generated successfully'})

        for stop_name, count in counts.items():
            status = "✓" if count >= 3 else "✗"
            print(f"  {status} {stop_name[:55]:55s} story_count={count}")
        gate_pass = all(c >= 3 for c in counts.values())
        print(f"  Gate verdict: {'PASS' if gate_pass else 'FAIL'} "
              f"({sum(1 for c in counts.values() if c >= 3)}/{len(counts)} stops)")
        print(f"  Elapsed: {elapsed:.1f}s")
        if prov_line:
            provenance_lines.append(prov_line)
            print(f"  Provenance: {prov_line}")
    else:
        print(f"  No stops parsed (elapsed: {elapsed:.1f}s)")
        timestamps.append((time.strftime('%Y-%m-%dT%H:%M:%S'), elapsed, 'NO_STOPS'))

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

    # BLOCKER4b summary
    print(f"\nBLOCKER4b events:")
    b4b_fired = [e for e in blocker4b_events if e.get('fired') is True]
    b4b_not_fired = [e for e in blocker4b_events if e.get('fired') is False]
    print(f"  Fired: {len(b4b_fired)}/{NUM_RUNS} runs")
    print(f"  Did not fire: {len(b4b_not_fired)}/{NUM_RUNS} runs")
    for e in b4b_fired:
        print(f"    Run {e['run']}: {e.get('unique_addresses', '?')} distinct addresses")
else:
    stats = None
    print("\nNo successful runs — cannot compute statistics.")
    print("\nBLOCKER4b events (all runs failed):")
    for e in blocker4b_events:
        if e.get('fired') is True:
            print(f"  Run {e['run']}: FIRED — {e.get('unique_addresses', '?')} distinct addresses")
        else:
            print(f"  Run {e['run']}: {e}")

# Save JSON artifact
artifact = {
    'task': 'LOCAL-434',
    'venue': LOCATION,
    'tour_type': TOUR_TYPE,
    'total_stops': TOTAL_STOPS,
    'num_runs_attempted': NUM_RUNS,
    'num_runs_succeeded': len(runs),
    'runs': runs,
    'statistics': stats,
    'timestamps': timestamps,
    'blocker4b_events': blocker4b_events,
    'provenance_lines': provenance_lines,
    'note': 'REAL PIPELINE — no pinning, no monkeypatching. Wayback fallback is the production path.',
}
output_path = str(PROJECT_ROOT / "local434_variance_mfa_unbound.json")
with open(output_path, 'w') as f:
    json.dump(artifact, f, indent=2)
print(f"\nJSON artifact saved: {output_path}")
