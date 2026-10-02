#!/usr/bin/env python3
"""LOCAL-318: Generate a 5-stop restaurant tour to verify the dangling-demonstrative gate.

Generates under a NEW filename and reads it as prose to confirm no dangling
demonstratives remain.
"""
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
# D186: spine stays on gpt-4o
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

VENUE_NAME = "Old Nice, Nice, France"
TOUR_TYPE = "restaurant"
TOURS_DIR = os.path.join(PROJECT_ROOT, 'tours')
OUTPUT_FILE = os.path.join(TOURS_DIR, "LOCAL318_5stop_old_nice_restaurant.txt")

print("=" * 70)
print("LOCAL-318: 5-stop Old Nice restaurant tour generation")
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

# Read and display the tour
print(f"\n{'=' * 70}")
print("GENERATED TOUR TEXT (read as prose)")
print(f"{'=' * 70}")

with open(OUTPUT_FILE, 'r') as f:
    content = f.read()

print(content[:8000])
if len(content) > 8000:
    print(f"\n  ... [{len(content) - 8000} more chars]")

# Run the dangling-demonstrative detector on the generated tour
print(f"\n{'=' * 70}")
print("POST-GENERATION DANGLING-DEMONSTRATIVE CHECK")
print(f"{'=' * 70}")

from tour_rubric_scorer import parse_tour
from dangling_demonstrative_gate import detect_dangling_demonstratives

stops = parse_tour(content)
total_findings = 0
for stop in stops:
    body = stop.get('body', '')
    title = stop.get('title', '')
    if not body:
        continue
    findings = detect_dangling_demonstratives(body, title, stop.get('lines', []))
    if findings:
        total_findings += len(findings)
        for f in findings:
            print(f"  Stop {stop['index']} ({title}): '{f['demonstrative_np']}'")
            print(f"    → {f['sentence'][:120]}")

if total_findings == 0:
    print("  ✓ NO dangling demonstratives found in generated tour")
else:
    print(f"  ✗ {total_findings} dangling demonstrative(s) found")

print(f"\nDone.")
