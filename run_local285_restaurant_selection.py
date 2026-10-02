#!/usr/bin/env python3
"""LOCAL-285: Generate three tours to verify the restaurant selection fixes.

1. 3-stop restaurant tour in Nice (the main fix)
2. 2-stop Riviera cycling tour (regression baseline)
3. 5-stop museum tour (regression baseline)

Environment requirements:
  - OPENAI_API_KEY set (via ~/Audioura/.env)
  - PostgreSQL accessible on localhost:5433
  - D186: spine stays on gpt-4o
"""
import os
import sys
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
CEILING = 0.80
MAX_GEN_ATTEMPTS = 3
TOURS_DEST = os.path.expanduser("~/Audioura/tours")

print("=" * 70)
print("LOCAL-285: RESTAURANT SELECTION FIX — GENERATION")
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

# Common environment
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
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

from generate_tour_text import generate_tour_text

# Track total cost
total_cost_all = 0.0

# ======================================================================
# TOUR 1: 3-STOP RESTAURANT TOUR IN NICE
# ======================================================================
print("\n" + "=" * 70)
print("TOUR 1: 3-STOP RESTAURANT TOUR IN NICE")
print("=" * 70)

os.environ['EXISTENCE_GATE_TOUR_TYPE'] = 'restaurant'
print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"  EXISTENCE_GATE_TOUR_TYPE: {os.environ.get('EXISTENCE_GATE_TOUR_TYPE')}")

restaurant_output = os.path.join(PROJECT_ROOT, "tours", "LOCAL285_nice_restaurant_3stop.txt")
os.makedirs(os.path.dirname(restaurant_output), exist_ok=True)

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
            output_file=restaurant_output,
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

# Extract cost from file
try:
    from generate_tour_text import _LAST_GENERATION_COST
    restaurant_cost = _LAST_GENERATION_COST.get('total_cost_usd', 0)
except:
    restaurant_cost = 0

if not restaurant_text:
    print("FATAL: Restaurant tour generation failed after all attempts")
    sys.exit(1)

total_cost_all += restaurant_cost
print(f"\n  Restaurant tour: {len(restaurant_text)} chars, cost=${restaurant_cost:.4f}, time={restaurant_elapsed:.1f}s")

# ======================================================================
# TOUR 2: 2-STOP RIVIERA CYCLING TOUR (REGRESSION)
# ======================================================================
print("\n" + "=" * 70)
print("TOUR 2: 2-STOP RIVIERA CYCLING TOUR (REGRESSION)")
print("=" * 70)

os.environ.pop('EXISTENCE_GATE_TOUR_TYPE', None)

cycling_output = os.path.join(PROJECT_ROOT, "tours", "LOCAL285_riviera_2stop_cycling.txt")

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
            output_file=cycling_output,
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

total_cost_all += cycling_cost
print(f"\n  Cycling tour: {len(cycling_text)} chars, cost=${cycling_cost:.4f}, time={cycling_elapsed:.1f}s")

# ======================================================================
# TOUR 3: 5-STOP MUSEUM TOUR (REGRESSION)
# ======================================================================
print("\n" + "=" * 70)
print("TOUR 3: 5-STOP MUSEUM TOUR (REGRESSION)")
print("=" * 70)

museum_output = os.path.join(PROJECT_ROOT, "tours", "LOCAL285_museum_5stop.txt")

MUSEUM_STOPS = 5
museum_text = None
museum_cost = 0
museum_elapsed = 0

t0 = time.time()
for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n  --- Museum generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")
    try:
        result = generate_tour_text(
            location="Musée Matisse, Nice",
            tour_type="museum",
            output_file=museum_output,
            total_stops=MUSEUM_STOPS,
        )
        if result and result[0]:
            museum_text = result[0]
            print(f"  Museum tour generated: {len(museum_text)} chars")
            break
        else:
            print(f"  Generation returned None (attempt {gen_attempt})")
    except Exception as e:
        print(f"  Generation error: {e}")
        traceback.print_exc()
museum_elapsed = time.time() - t0

try:
    museum_cost = _LAST_GENERATION_COST.get('total_cost_usd', 0)
except:
    museum_cost = 0

if not museum_text:
    print("FATAL: Museum tour generation failed after all attempts")
    sys.exit(1)

total_cost_all += museum_cost
print(f"\n  Museum tour: {len(museum_text)} chars, cost=${museum_cost:.4f}, time={museum_elapsed:.1f}s")

# ======================================================================
# COPY TO ~/Audioura/tours/
# ======================================================================
print("\n" + "=" * 70)
print("COPYING TOURS TO ~/Audioura/tours/")
print("=" * 70)

os.makedirs(TOURS_DEST, exist_ok=True)

for src, name in [
    (restaurant_output, "LOCAL285_nice_restaurant_3stop.txt"),
    (cycling_output, "LOCAL285_riviera_2stop_cycling.txt"),
    (museum_output, "LOCAL285_museum_5stop.txt"),
]:
    dest = os.path.join(TOURS_DEST, name)
    if os.path.exists(src):
        shutil.copy2(src, dest)
        print(f"  Copied: {dest}")
    else:
        print(f"  WARNING: {src} not found")

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
    cur.execute("SELECT id, tour_name, is_test FROM audio_tours WHERE id > %s ORDER BY id",
                (max(EXPECTED_NICE),))
    new_rows = cur.fetchall()
    test_ids_to_delete = []
    for row_id, tour_name, is_test in new_rows:
        if row_id not in EXPECTED_NICE and is_test:
            test_ids_to_delete.append(row_id)
            print(f"  [D141] Will delete test row id={row_id}: {tour_name}")

    if test_ids_to_delete:
        for tid in test_ids_to_delete:
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
# VALIDATION + REPORT
# ======================================================================
print("\n" + "=" * 70)
print("VALIDATION")
print("=" * 70)

# Parse stops
from stop_anchor_detector_v2 import parse_tour_stops

restaurant_stops = parse_tour_stops(restaurant_text)
cycling_stops = parse_tour_stops(cycling_text)
museum_stops = parse_tour_stops(museum_text)

# --- Validation 1: Restaurant tour has restaurants ---
print("\n--- Restaurant Tour Validation ---")
_restaurant_keywords = {'restaurant', 'bistro', 'brasserie', 'café', 'cafe',
                         'trattoria', 'tavern', 'eatery', 'dining', 'cuisine',
                         'chef', 'menu', 'dish', 'food', 'cook', 'kitchen'}
_museum_keywords = {'museum', 'musée', 'gallery', 'exhibit', 'artwork', 'painting'}
restaurant_stop_names = [s.get('title', s.get('name', '')) for s in restaurant_stops]
museum_names_in_restaurant = []
for name in restaurant_stop_names:
    name_lower = name.lower()
    if any(kw in name_lower for kw in _museum_keywords):
        museum_names_in_restaurant.append(name)

if museum_names_in_restaurant:
    print(f"  ⚠️  MUSEUM NAMES IN RESTAURANT TOUR: {museum_names_in_restaurant}")
else:
    print(f"  ✓ No museum names in restaurant tour stops")

print(f"  Stops: {restaurant_stop_names}")

# --- Validation 2: No empty venue phrase ---
print("\n--- Empty Venue Phrase Check ---")
_empty_venue_check = re.search(r'(through|across|around|in|of)\s+[.,;!]', restaurant_text)
if _empty_venue_check:
    print(f"  ⚠️  EMPTY VENUE PHRASE FOUND: '{_empty_venue_check.group()}'")
else:
    print(f"  ✓ No empty venue phrases in restaurant tour")

# Check cycling and museum too
for name, text in [("cycling", cycling_text), ("museum", museum_text)]:
    _ev = re.search(r'(through|across|around|in|of)\s+[.,;!]', text)
    if _ev:
        print(f"  ⚠️  EMPTY VENUE in {name}: '{_ev.group()}'")
    else:
        print(f"  ✓ No empty venue phrases in {name} tour")

# --- Validation 3: No self-referential route ---
print("\n--- Self-Referential Route Check ---")
_self_route_check = re.compile(
    r'(?:from|between)\s+(.{3,80}?)\s+to\s+\1',
    re.IGNORECASE
)
for name, text in [("restaurant", restaurant_text), ("cycling", cycling_text), ("museum", museum_text)]:
    _sr = _self_route_check.search(text)
    if _sr:
        print(f"  ⚠️  SELF-ROUTE in {name}: '{_sr.group()}'")
    else:
        print(f"  ✓ No self-referential route in {name} tour")

# --- Facts per stop (cycling baseline) ---
print("\n--- Facts Per Stop (Cycling) ---")
# Count facts: sentences with dates or proper nouns
def count_facts(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    facts = 0
    for s in sentences:
        if len(s) < 15:
            continue
        has_date = bool(re.search(r'\b\d{3,4}\b', s))
        has_proper_verb = bool(re.search(r'[A-Z][a-z]+', s)) and bool(
            re.search(r'\b(?:built|founded|opened|painted|wrote|designed|constructed|'
                      r'visited|established|named|created|served|became|was|were)\b', s, re.IGNORECASE))
        if has_date or has_proper_verb:
            facts += 1
    return facts

cycling_facts_total = count_facts(cycling_text)
cycling_facts_per_stop = cycling_facts_total / max(len(cycling_stops), 1)
print(f"  Cycling: {cycling_facts_total} facts across {len(cycling_stops)} stops = {cycling_facts_per_stop:.1f} facts/stop")
print(f"  Baseline: 6.0 facts/stop")

# --- Museum overview check ---
print("\n--- Museum Tour Overview Check ---")
_has_orientation = bool(re.search(r'^Orientation:', museum_text, re.MULTILINE))
print(f"  Orientation present on stop 1: {_has_orientation}")

# ======================================================================
# FINAL REPORT
# ======================================================================
print("\n" + "=" * 70)
print("REPORT")
print("=" * 70)

print(f"\nTotal cost: ${total_cost_all:.4f} (ceiling: ${CEILING})")
if total_cost_all > CEILING:
    print(f"  ⚠️  OVER CEILING!")

print(f"\n--- Restaurant Tour (Nice, 3-stop) ---")
print(f"  Stops requested: {RESTAURANT_STOPS}")
print(f"  Stops delivered: {len(restaurant_stops)}")
for i, s in enumerate(restaurant_stops, 1):
    print(f"    {i}. {s.get('title', s.get('name', '?'))}")
print(f"  Words: {len(restaurant_text.split())}")
print(f"  Generation time: {restaurant_elapsed:.1f}s")
print(f"  Cost: ${restaurant_cost:.4f}")

print(f"\n--- Cycling Tour (Riviera, 2-stop) ---")
print(f"  Stops requested: {CYCLING_STOPS}")
print(f"  Stops delivered: {len(cycling_stops)}")
for i, s in enumerate(cycling_stops, 1):
    print(f"    {i}. {s.get('title', s.get('name', '?'))}")
print(f"  Words: {len(cycling_text.split())}")
print(f"  Facts/stop: {cycling_facts_per_stop:.1f}")
print(f"  Generation time: {cycling_elapsed:.1f}s")
print(f"  Cost: ${cycling_cost:.4f}")

print(f"\n--- Museum Tour (Matisse, 5-stop) ---")
print(f"  Stops requested: {MUSEUM_STOPS}")
print(f"  Stops delivered: {len(museum_stops)}")
for i, s in enumerate(museum_stops, 1):
    print(f"    {i}. {s.get('title', s.get('name', '?'))}")
print(f"  Words: {len(museum_text.split())}")
print(f"  Orientation on stop 1: {_has_orientation}")
print(f"  Generation time: {museum_elapsed:.1f}s")
print(f"  Cost: ${museum_cost:.4f}")

# D161: read as prose
print(f"\n--- Restaurant tour first 600 chars (D161) ---")
print(restaurant_text[:600])
print("...\n")

print(f"\n--- Cycling tour first 600 chars (D161) ---")
print(cycling_text[:600])
print("...\n")

print(f"\n--- Museum tour first 600 chars (D161) ---")
print(museum_text[:600])
print("...\n")

print("\n" + "=" * 70)
print("LOCAL-285 GENERATION COMPLETE")
print("=" * 70)
