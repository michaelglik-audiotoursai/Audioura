#!/usr/bin/env python3
"""LOCAL-437: Palais Lascaris control run (D302/D326).

The correct control venue. D302/D326 specify Palais Lascaris, Nice — the
musical-instrument museum — stops: Harpe by Naderman / Violes gambe /
Sacqueboute ténor / Basse de violon, dates 1780/1652/1581/1696.

Gate mode: enforce. This is the enforcement run — stops survive the gate because
they ARE independently verifiable (permanent collection of a real museum).
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
OUTPUT_FILE = str(PROJECT_ROOT / "tours" / "local437_palais_lascaris_control.json")

REQUIRED_DATES = ['1780', '1652', '1581', '1696']
EXPECTED_STOPS = ['Harpe', 'Violes gambe', 'Sacqueboute', 'Basse de violon']

print(f"{'#'*70}")
print(f"# LOCAL-437: Palais Lascaris Control (D302/D326)")
print(f"# Location: {LOCATION}")
print(f"# Stops: {TOTAL_STOPS}")
print(f"# Gate mode: enforce")
print(f"# Expected: 4/4 stops, dates 1780/1652/1581/1696")
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

print(f"\n{'='*70}")
print(f"PALAIS LASCARIS CONTROL RESULTS")
print(f"{'='*70}")
print(f"Elapsed: {elapsed:.1f}s")
print(f"Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)")

checks_passed = 0
checks_total = 3

if not result or not result[0]:
    print("FAIL: No tour generated")
    sys.exit(1)

tour_text = result[0]

# Check 1: 4/4 stops
counts = extract_per_stop_counts(tour_text)
num_stops = len(counts)
if num_stops >= 4:
    print(f"✓ Stops: {num_stops}/4")
    checks_passed += 1
else:
    print(f"✗ Stops: {num_stops}/4 (expected 4)")

# Check 2: Dates intact
dates_found = []
for date in REQUIRED_DATES:
    if date in tour_text:
        dates_found.append(date)

if len(dates_found) == 4:
    print(f"✓ Dates: {'/'.join(dates_found)} all present")
    checks_passed += 1
else:
    missing = [d for d in REQUIRED_DATES if d not in dates_found]
    print(f"✗ Dates: {len(dates_found)}/4 (missing: {missing})")
    print(f"  Found: {dates_found}")

# Check 3: Coordinates
coords_found = 0
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE) as f:
        output_data = json.load(f)
    if isinstance(output_data, dict) and 'stops' in output_data:
        for stop in output_data['stops']:
            if stop.get('lat') and stop.get('lng'):
                coords_found += 1
    elif isinstance(output_data, list):
        for item in output_data:
            if isinstance(item, dict) and item.get('lat') and item.get('lng'):
                coords_found += 1

coord_pattern = re.compile(r'[-+]?\d+\.\d+,\s*[-+]?\d+\.\d+')
coord_matches = coord_pattern.findall(tour_text)
if coords_found >= 4 or len(coord_matches) >= 4:
    actual = max(coords_found, len(coord_matches))
    print(f"✓ Coordinates: {actual}/4")
    checks_passed += 1
else:
    actual = max(coords_found, len(coord_matches))
    print(f"✗ Coordinates: {actual}/4")

# Per-stop detail
print(f"\nPer-stop detail:")
for stop_name, count in counts.items():
    status = "✓" if count >= 3 else "✗"
    print(f"  {status} {stop_name[:55]:55s} story_count={count}")

# Look for expected stop keywords
print(f"\nExpected stops check:")
for expected in EXPECTED_STOPS:
    found = expected.lower() in tour_text.lower()
    status = "✓" if found else "✗"
    print(f"  {status} '{expected}' {'found' if found else 'NOT FOUND'} in tour text")

print(f"\n{'='*70}")
print(f"VERDICT: {'PASS' if checks_passed == checks_total else 'FAIL'} "
      f"({checks_passed}/{checks_total} checks)")
print(f"Gate mode: enforce")
print(f"{'='*70}")
