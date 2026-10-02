#!/usr/bin/env python3
"""LOCAL-281: Generate a 3-stop restaurant tour in Nice and a 2-stop Riviera cycling tour.

The restaurant tour exercises the new 'dining' venue kind.
The cycling tour is a regression check for geographic_area.

Environment:
  - EXISTENCE_GATE_TOUR_TYPE=restaurant (for the restaurant tour)
  - STOP_EXISTENCE_GATE_MODE=enforce
  - STORIED_MODE=true
  - D186: spine on gpt-4o
"""
import os
import sys
import io
import re
import time
import json
import shutil
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env
_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

from db_connection import get_connection, check_db_available

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3
TOURS_DEST = os.path.expanduser("~/Audioura/tours")

print("=" * 70)
print("LOCAL-281: RESTAURANT VENUE KIND — GENERATION")
print("=" * 70)

# ======================================================================
# PRE-CHECKS
# ======================================================================
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_before = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_before}")
assert nice_before == EXPECTED_NICE, f"Nice list mismatch: {nice_before}"
conn.close()

# ======================================================================
# TOUR 1: 3-STOP RESTAURANT TOUR IN NICE
# ======================================================================
print("\n" + "=" * 70)
print("TOUR 1: 3-STOP RESTAURANT TOUR IN NICE")
print("=" * 70)

# Set environment for restaurant tour
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['EXISTENCE_GATE_TOUR_TYPE'] = 'restaurant'
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_SUBJECT_ROUTINE'] = '1'
os.environ['DISABLE_R10_DELETION'] = '1'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['TOUR_TEST_MODE'] = 'true'

for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"  EXISTENCE_GATE_TOUR_TYPE: {os.environ.get('EXISTENCE_GATE_TOUR_TYPE')}")
print(f"  STORIED_MODE: {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_TEST_MODE: {os.environ.get('TOUR_TEST_MODE')}")

from generate_tour_text import generate_tour_text

# Track cost
try:
    from generate_tour_text import _LAST_GENERATION_COST
except ImportError:
    _LAST_GENERATION_COST = {}

restaurant_output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL281_nice_restaurant_3stop.txt")
os.makedirs(os.path.dirname(restaurant_output_file), exist_ok=True)

RESTAURANT_STOPS = 3
restaurant_text = None
restaurant_cost = 0
restaurant_elapsed = 0

t0 = time.time()
for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n  --- Restaurant generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")
    try:
        result = generate_tour_text(
            location="Nice, France",
            tour_type="restaurant",
            output_file=restaurant_output_file,
            total_stops=RESTAURANT_STOPS,
        )
        if result and result[0]:
            restaurant_text = result[0]
            print(f"  Restaurant tour generated: {len(restaurant_text)} chars")
            break
        else:
            print(f"  Generation returned None (attempt {gen_attempt})")
    except Exception as e:
        print(f"  Generation error: {e}")
        traceback.print_exc()

restaurant_elapsed = time.time() - t0

# Get cost
try:
    restaurant_cost = _LAST_GENERATION_COST.get('total_cost_usd', 0)
except:
    restaurant_cost = 0

if not restaurant_text:
    print("FATAL: Restaurant tour generation failed after all attempts")
    sys.exit(1)

print(f"\n  Restaurant tour: {len(restaurant_text)} chars, cost=${restaurant_cost:.4f}, time={restaurant_elapsed:.1f}s")

# ======================================================================
# TOUR 2: 2-STOP RIVIERA CYCLING TOUR (REGRESSION CHECK)
# ======================================================================
print("\n" + "=" * 70)
print("TOUR 2: 2-STOP RIVIERA CYCLING TOUR (REGRESSION CHECK)")
print("=" * 70)

# Switch to geographic context (clear restaurant signal)
os.environ.pop('EXISTENCE_GATE_TOUR_TYPE', None)

cycling_output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL281_riviera_2stop_cycling.txt")

CYCLING_STOPS = 2
cycling_text = None
cycling_cost = 0
cycling_elapsed = 0

t0 = time.time()
for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n  --- Cycling generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")
    try:
        result = generate_tour_text(
            location="French Riviera",
            tour_type="biking",
            output_file=cycling_output_file,
            total_stops=CYCLING_STOPS,
        )
        if result and result[0]:
            cycling_text = result[0]
            print(f"  Cycling tour generated: {len(cycling_text)} chars")
            break
        else:
            print(f"  Generation returned None (attempt {gen_attempt})")
    except Exception as e:
        print(f"  Generation error: {e}")
        traceback.print_exc()

cycling_elapsed = time.time() - t0

try:
    cycling_cost = _LAST_GENERATION_COST.get('total_cost_usd', 0)
except:
    cycling_cost = 0

if not cycling_text:
    print("FATAL: Cycling tour generation failed after all attempts")
    sys.exit(1)

print(f"\n  Cycling tour: {len(cycling_text)} chars, cost=${cycling_cost:.4f}, time={cycling_elapsed:.1f}s")

# ======================================================================
# COPY TO ~/Audioura/tours/
# ======================================================================
print("\n" + "=" * 70)
print("COPYING TOURS TO ~/Audioura/tours/")
print("=" * 70)

os.makedirs(TOURS_DEST, exist_ok=True)

rest_dest = os.path.join(TOURS_DEST, "LOCAL281_nice_restaurant_3stop.txt")
cycl_dest = os.path.join(TOURS_DEST, "LOCAL281_riviera_2stop_cycling.txt")

shutil.copy2(restaurant_output_file, rest_dest)
print(f"  Copied: {rest_dest}")

shutil.copy2(cycling_output_file, cycl_dest)
print(f"  Copied: {cycl_dest}")

# ======================================================================
# POST-CHECKS
# ======================================================================
print("\n" + "=" * 70)
print("POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"[POST] audio_tours row count: {count_after} (was {count_before})")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"[POST] Nice list: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list changed: {nice_after}"

# D141: cleanup test rows
if count_after > count_before:
    # Find the new test rows
    cur.execute("SELECT id, tour_name, is_test FROM audio_tours WHERE id > %s ORDER BY id", (max(EXPECTED_NICE),))
    new_rows = cur.fetchall()
    test_ids_to_delete = []
    for row_id, tour_name, is_test in new_rows:
        if row_id not in EXPECTED_NICE and is_test:
            test_ids_to_delete.append(row_id)
            print(f"  [D141] Will delete test row id={row_id}: {tour_name}")
    
    if test_ids_to_delete:
        for tid in test_ids_to_delete:
            # D141: SELECT is_test before delete
            cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tid,))
            r = cur.fetchone()
            if r and r[0]:
                cur.execute("DELETE FROM audio_tours WHERE id = %s", (tid,))
                print(f"  [D141] Deleted test row id={tid}")
            else:
                print(f"  [D141] SKIPPED id={tid} (is_test={r[0] if r else None})")
        conn.commit()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_final = cur.fetchone()[0]
print(f"[POST] audio_tours final: {count_final} (started={count_before})")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
assert nice_final == EXPECTED_NICE, f"Nice list after cleanup: {nice_final}"
print(f"[POST] Nice list UNCHANGED: {nice_final}")
conn.close()

# ======================================================================
# READ AND REPORT
# ======================================================================
print("\n" + "=" * 70)
print("REPORT")
print("=" * 70)

total_cost = restaurant_cost + cycling_cost
print(f"\nTotal cost: ${total_cost:.4f} (ceiling: ${CEILING})")
assert total_cost <= CEILING, f"Cost ${total_cost:.4f} exceeds ceiling ${CEILING}"

# Parse stops from generated tours
from stop_anchor_detector_v2 import parse_tour_stops

restaurant_stops = parse_tour_stops(restaurant_text)
cycling_stops = parse_tour_stops(cycling_text)

print(f"\n--- Restaurant Tour (Nice, 3-stop) ---")
print(f"  Stops delivered: {len(restaurant_stops)}")
for i, s in enumerate(restaurant_stops, 1):
    print(f"    {i}. {s.get('title', s.get('name', '?'))}")
print(f"  Words: {len(restaurant_text.split())}")
print(f"  Generation time: {restaurant_elapsed:.1f}s")
print(f"  Cost: ${restaurant_cost:.4f}")

print(f"\n--- Cycling Tour (Riviera, 2-stop) ---")
print(f"  Stops delivered: {len(cycling_stops)}")
for i, s in enumerate(cycling_stops, 1):
    print(f"    {i}. {s.get('title', s.get('name', '?'))}")
print(f"  Words: {len(cycling_text.split())}")
print(f"  Generation time: {cycling_elapsed:.1f}s")
print(f"  Cost: ${cycling_cost:.4f}")

# D161: read delivered tour as prose
print(f"\n--- Restaurant tour first 500 chars (D161 prose check) ---")
print(restaurant_text[:500])
print("...")

print(f"\n--- Cycling tour first 500 chars (D161 prose check) ---")
print(cycling_text[:500])
print("...")

print("\n" + "=" * 70)
print("LOCAL-281 GENERATION COMPLETE")
print("=" * 70)
