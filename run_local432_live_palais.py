#!/usr/bin/env python3
"""LOCAL-432: Live Palais Lascaris run with per-stop story_count reporting.

Generates a 4-stop Palais tour using current code with:
- STORIED_MODE=true
- story retry improvements (Part 1)
- Reports per-stop story_count via story_gate.extract_story_sentences

Also validates:
- Dates intact (1780, 1652, 1581, 1696)
- 4/4 coordinates
- framing=venue_purpose detected
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

LOCATION = "Palais Lascaris, Nice"
TOUR_TYPE = "museum"
TOTAL_STOPS = 4
OUTPUT_FILE = str(PROJECT_ROOT / "tours" / "palais_local432_live.json")

print(f"LOCAL-432 Live Palais Run")
print(f"{'='*60}")
print(f"Location: {LOCATION}")
print(f"Stops: {TOTAL_STOPS}")
print(f"Model: gpt-4o")
print(f"STORIED_MODE: true")
print(f"Output: {OUTPUT_FILE}")
print(f"{'='*60}")

start = time.time()

from generate_tour_text import generate_tour_text

result = generate_tour_text(
    location=LOCATION,
    tour_type=TOUR_TYPE,
    output_file=OUTPUT_FILE,
    total_stops=TOTAL_STOPS,
    persona=None,
)

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"Generation completed in {elapsed:.1f}s")

if not result or not result[0]:
    print("GENERATION FAILED")
    sys.exit(1)

# Load and analyze the result
tour_text = result[0]
print(f"\nTour length: {len(tour_text)} chars")

# --- Per-stop story count ---
from story_gate import extract_story_sentences
import re

stops = re.split(r'(?=^Stop\s+\d+:)', tour_text, flags=re.MULTILINE)
stops = [s for s in stops if s.strip() and re.match(r'Stop\s+\d+:', s.strip())]

print(f"\n{'='*60}")
print(f"PER-STOP STORY COUNTS (LOCAL-432)")
print(f"{'='*60}")

all_dates = ['1780', '1652', '1581', '1696']
dates_found = []
total_story_pass = 0

for i, stop_block in enumerate(stops):
    # Extract stop name
    header = re.match(r'Stop\s+\d+:\s*(.+?)(?:\n|$)', stop_block)
    stop_name = header.group(1).strip() if header else f"Stop {i+1}"

    # Extract description portion
    desc_match = re.search(
        r'(?:Orientation:.*?\n\n)(.+?)(?:\n\s*Directions:|\n\s*Sources:|\n\s*Closing:|\Z)',
        stop_block, re.DOTALL
    )
    desc = desc_match.group(1).strip() if desc_match else stop_block

    # Story sentences
    story_sents = extract_story_sentences(desc)
    story_count = len(story_sents)
    passed = story_count >= 3
    if passed:
        total_story_pass += 1

    # Check dates
    for d in all_dates:
        if d in stop_block and d not in dates_found:
            dates_found.append(d)

    status = "✓" if passed else "✗"
    print(f"  {status} {stop_name[:60]:60s} story_count={story_count}")
    if story_sents:
        for ss in story_sents[:3]:
            print(f"      → \"{ss[:100]}\"")
    if not passed:
        # Show what sentences exist but didn't qualify
        all_sents = re.split(r'(?<=[.!?])\s+', desc.strip())
        non_story = [s for s in all_sents if s and len(s) >= 30 and s not in story_sents]
        if non_story:
            print(f"      (non-story sentences: {len(non_story)})")

print(f"\n{'='*60}")
print(f"STORY GATE VERDICT: {total_story_pass}/{len(stops)} stops pass (≥3 story sentences)")
print(f"{'='*60}")

# --- Dates ---
print(f"\nDATES: {len(dates_found)}/4 found: {', '.join(sorted(dates_found))}")
missing_dates = [d for d in all_dates if d not in dates_found]
if missing_dates:
    print(f"  MISSING: {', '.join(missing_dates)}")

# --- Coordinates ---
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE) as f:
        tour_data = json.load(f)
    if isinstance(tour_data, dict):
        stops_data = tour_data.get('stops', [])
    elif isinstance(tour_data, list):
        stops_data = tour_data
    else:
        stops_data = []

    coords_count = sum(1 for s in stops_data
                       if s.get('latitude') and s.get('longitude'))
    print(f"COORDINATES: {coords_count}/{len(stops_data)}")
else:
    print("COORDINATES: output file not found")

# --- Venue purpose framing ---
if 'venue_purpose' in tour_text.lower() or any('collection' in s.lower() or 'instrument' in s.lower() for s in stops):
    print("FRAMING: venue_purpose (inferred from content)")

print(f"\n{'='*60}")
print(f"CONTROL VERDICT:")
print(f"  Stops: {len(stops)}/4")
print(f"  Dates: {len(dates_found)}/4")
print(f"  Story gate: {total_story_pass}/{len(stops)}")
print(f"{'='*60}")
