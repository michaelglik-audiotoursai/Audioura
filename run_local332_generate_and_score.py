#!/usr/bin/env python3
"""run_local332_generate_and_score.py — Regenerate 5-stop restaurant tour and score it.

Generates after interpretive enrichment and measures fact density.
"""
import os
import sys
import time
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env for API keys
_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

VENUE_NAME = "Old Nice, Nice, France"
TOUR_TYPE = "restaurant"
TOURS_DIR = os.path.join(PROJECT_ROOT, 'tours')
OUTPUT_FILE = os.path.join(TOURS_DIR, "LOCAL332_5stop_old_nice_restaurant.txt")

print("=" * 70)
print("LOCAL-332: 5-stop Old Nice restaurant tour — POST-ENRICHMENT")
print("=" * 70)
print(f"  Location: {VENUE_NAME}")
print(f"  Type: {TOUR_TYPE}")
print(f"  Output: {OUTPUT_FILE}")
print()

from generate_tour_text import generate_tour_text

start_time = time.time()
result = generate_tour_text(
    location=VENUE_NAME,
    tour_type=TOUR_TYPE,
    output_file=OUTPUT_FILE,
    total_stops=5,
    persona=None,
)
elapsed = time.time() - start_time

if not result or not result[0]:
    print(f"\n  *** TOUR GENERATION FAILED after {elapsed:.1f}s ***")
    sys.exit(1)

print(f"\n  Tour generated in {elapsed:.1f}s → {OUTPUT_FILE}")

# Read and score
with open(OUTPUT_FILE, 'r') as f:
    content = f.read()

print(f"\n{'=' * 70}")
print("SCORING — Facts per stop (tour_rubric_scorer)")
print(f"{'=' * 70}")

from tour_rubric_scorer import parse_tour, analyze_stop

stops = parse_tour(content)
print(f"\n{'Stop':<25} {'Facts':<8} {'Classification':<15} {'Density':<8}")
print("-" * 56)

total_facts = 0
classifications = []
for stop in stops:
    sa = analyze_stop(stop, stops)
    facts = sa.distinct_fact_count
    total_facts += facts
    cls = sa.classification
    classifications.append(cls)
    print(f"  {sa.title[:22]:<25} {facts:<8} {cls:<15} {sa.fact_density:.2f}")

print(f"\n  TOTAL facts: {total_facts}")
print(f"  Classifications: {'/'.join(classifications)}")
print(f"  Average facts/stop: {total_facts / max(1, len(stops)):.1f}")

# Show the tour text (first 5000 chars)
print(f"\n{'=' * 70}")
print("TOUR TEXT (first 5000 chars)")
print(f"{'=' * 70}")
print(content[:5000])

# Report baseline comparison
print(f"\n{'=' * 70}")
print("COMPARISON vs BASELINE (from task description)")
print(f"{'=' * 70}")
print("  BASELINE: base 65.0, stops THIN/0, ADEQ/4, THIN/2, THIN/2, RICH/4")
print(f"  AFTER:    stops {'/'.join(f'{c}/{s.distinct_fact_count}' for c, s in zip(classifications, [analyze_stop(stop, stops) for stop in stops]))}")
print(f"  Total facts baseline: 0+4+2+2+4 = 12")
print(f"  Total facts after:    {total_facts}")
