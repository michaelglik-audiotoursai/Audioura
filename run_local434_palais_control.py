#!/usr/bin/env python3
"""LOCAL-434: Palais Lascaris control run (D302/D326).

One live run. Checks:
- 4/4 stops generated
- Dates intact (1780, 1652, 1581, 1696)
- 4/4 coordinates
"""
import json
import os
import re
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

from generate_tour_text import generate_tour_text
from variance_harness import extract_per_stop_counts

LOCATION = "Palais Lascaris, Nice"
TOUR_TYPE = "museum"
TOTAL_STOPS = 4
OUTPUT_FILE = str(PROJECT_ROOT / "tours" / "local434_palais_control.json")

REQUIRED_DATES = ['1780', '1652', '1581', '1696']

print(f"{'#'*70}")
print(f"# LOCAL-434: Palais Lascaris Control (D302/D326)")
print(f"# Location: {LOCATION}")
print(f"# Stops: {TOTAL_STOPS}")
print(f"{'#'*70}")

start = time.time()
result = generate_tour_text(
    location=LOCATION,
    tour_type=TOUR_TYPE,
    output_file=OUTPUT_FILE,
    total_stops=TOTAL_STOPS,
    persona=None,
)
elapsed = time.time() - start

if not result or not result[0]:
    print(f"\nFAILED: No tour generated (elapsed: {elapsed:.1f}s)")
    sys.exit(1)

tour_text = result[0]
coords = result[2] if len(result) > 2 else None

# Check stops
stops = re.findall(r'^Stop\s+\d+:\s*(.+)$', tour_text, re.MULTILINE)
print(f"\nStops found: {len(stops)}/{TOTAL_STOPS}")
for i, s in enumerate(stops, 1):
    print(f"  Stop {i}: {s}")

# Check dates
dates_found = []
dates_missing = []
for d in REQUIRED_DATES:
    if d in tour_text:
        dates_found.append(d)
    else:
        dates_missing.append(d)
print(f"\nDates intact: {len(dates_found)}/{len(REQUIRED_DATES)}")
print(f"  Found: {', '.join(dates_found)}")
if dates_missing:
    print(f"  MISSING: {', '.join(dates_missing)}")

# Check coordinates
coord_count = 0
if coords:
    if isinstance(coords, tuple) and len(coords) == 2:
        # Single coordinate pair
        coord_count = 1
    elif isinstance(coords, (list, tuple)):
        coord_count = len([c for c in coords if c])
coord_lines = re.findall(r'Coordinates:\s*[\d.-]+', tour_text)
coord_count = max(coord_count, len(coord_lines))
print(f"\nCoordinates: {coord_count}/{TOTAL_STOPS}")

# Story counts
per_stop = extract_per_stop_counts(tour_text)
print(f"\nPer-stop story_count:")
for stop_name, count in per_stop.items():
    status = "✓" if count >= 3 else "✗"
    print(f"  {status} {stop_name[:55]:55s} story_count={count}")

gate_pass = all(c >= 3 for c in per_stop.values())
print(f"\nGate verdict: {'PASS' if gate_pass else 'FAIL'} "
      f"({sum(1 for c in per_stop.values() if c >= 3)}/{len(per_stop)} stops)")

# Summary verdict
all_ok = (
    len(stops) == TOTAL_STOPS and
    len(dates_found) == len(REQUIRED_DATES) and
    coord_count >= TOTAL_STOPS
)
print(f"\n{'='*60}")
print(f"CONTROL VERDICT: {'PASS' if all_ok else 'FAIL'}")
print(f"  Stops: {len(stops)}/{TOTAL_STOPS} {'✓' if len(stops) == TOTAL_STOPS else '✗'}")
print(f"  Dates: {len(dates_found)}/{len(REQUIRED_DATES)} {'✓' if len(dates_found) == len(REQUIRED_DATES) else '✗'}")
print(f"  Coords: {coord_count}/{TOTAL_STOPS} {'✓' if coord_count >= TOTAL_STOPS else '✗'}")
print(f"  Elapsed: {elapsed:.1f}s")
print(f"{'='*60}")

# Save artifact
artifact = {
    'task': 'LOCAL-434',
    'control': 'Palais Lascaris (D302/D326)',
    'stops_found': len(stops),
    'stops_required': TOTAL_STOPS,
    'dates_found': dates_found,
    'dates_missing': dates_missing,
    'coord_count': coord_count,
    'per_stop_story_count': per_stop,
    'gate_pass': gate_pass,
    'verdict': 'PASS' if all_ok else 'FAIL',
    'elapsed_seconds': elapsed,
}
output_path = str(PROJECT_ROOT / "local434_palais_control.json")
with open(output_path, 'w') as f:
    json.dump(artifact, f, indent=2)
print(f"\nJSON artifact saved: {output_path}")
