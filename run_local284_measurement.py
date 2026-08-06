#!/usr/bin/env python3
"""LOCAL-284: Measure corpus-depth tiebreak for museum selector.

Generates:
  1. 5-stop Musée des Arts Asiatiques tour (target case)
  2. ≥3 2-stop Riviera walking tours (regression check)
  3. 1 8-stop Riviera walking tour (regression check)

Reports:
  - Museum: objects chosen, corpus depth per object, facts per stop
  - Riviera: facts/stop, total facts, word count, distinct stops across runs

CEILING: $1.00 total
"""
import os
import sys
import re
import time
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ── Load .env ──────────────────────────────────────────────────────────────
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

os.environ['STORIED_MODE'] = 'true'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Clear overrides — use defaults
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R10_DELETION'):
    if k in os.environ:
        del os.environ[k]

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 1.00

print("=" * 70)
print("LOCAL-284: CORPUS-DEPTH TIEBREAK — MEASUREMENT RUN")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset -> default)')}")
print(f"  CEILING = ${CEILING:.2f}")
print()

# ── Pre-checks ─────────────────────────────────────────────────────────────
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT current_database()")
db_name = cur.fetchone()[0]
print(f"[PRE] Connected to: {db_name}")
assert db_name == "audiotours", f"Expected audiotours, got {db_name}"

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours: {count_before}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_pre = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_pre}")
assert nice_pre == EXPECTED_NICE, f"Nice list mismatch: {nice_pre}"

# Show corpus state for Asian Arts
print("\n[PRE] Corpus depth for Asian Arts Museum:")
cur.execute("""
    SELECT stop_title, passage_count FROM stop_corpus
    WHERE LOWER(venue_name) LIKE '%arts%' AND LOWER(venue_name) LIKE '%asiatiques%'
    ORDER BY passage_count DESC
""")
corpus_depth_asian = {}
for r in cur.fetchall():
    print(f"  {r[1]:2d} passages | {r[0]}")
    corpus_depth_asian[r[0].lower().strip()] = r[1]
print(f"  TOTAL: {sum(corpus_depth_asian.values())} passages across {len(corpus_depth_asian)} stops")
conn.close()

# ── Import generation function ──────────────────────────────────────────────
from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

total_cost = 0.0
tours_dir = os.path.join(PROJECT_ROOT, "tours")
os.makedirs(tours_dir, exist_ok=True)

# Copy destination
dest_dir = "/Users/micha/Audioura/tours"
os.makedirs(dest_dir, exist_ok=True)


def count_facts(tour_text):
    """Count facts per stop using the standard method."""
    stops = parse_tour_stops(tour_text)
    facts_per_stop = []
    for stop in stops:
        desc = stop.get('description', '')
        # Count factual claims (sentences with specific details)
        sentences = [s.strip() for s in re.split(r'[.!?]+', desc) if s.strip()]
        fact_count = 0
        for s in sentences:
            # A fact contains: a year, a name, a measurement, a specific detail
            if re.search(r'\b\d{3,4}\b|\b\d+\s*(m|km|kg|metres|meters|feet|cm)\b', s):
                fact_count += 1
            elif re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', s) and len(s) > 30:
                fact_count += 1
            elif re.search(r'\b(built|designed|created|founded|established|commissioned|completed)\b', s, re.I):
                fact_count += 1
            elif re.search(r'\b(century|siècle|période|dynasty|era|epoch)\b', s, re.I):
                fact_count += 1
        facts_per_stop.append({'name': stop.get('name', ''), 'facts': fact_count, 'words': len(desc.split())})
    return stops, facts_per_stop


# ════════════════════════════════════════════════════════════════════════════
# PART 1: 5-stop Musée des Arts Asiatiques
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 1: 5-stop Musée des Arts Asiatiques")
print("=" * 70)

museum_output = os.path.join(tours_dir, "LOCAL284_asian_arts_5stop.txt")

start_time = time.time()
try:
    result = generate_tour_text(
        location='Musee des Arts Asiatiques, Nice, France',
        tour_type='museum',
        output_file=museum_output,
        total_stops=5,
        persona=None,
    )
except Exception as e:
    elapsed = time.time() - start_time
    print(f"\n  GENERATION FAILED after {elapsed:.1f}s: {e}")
    import traceback
    traceback.print_exc()
    result = None

elapsed = time.time() - start_time
museum_cost = _LAST_GENERATION_COST.get("total_cost", 0.0) if _LAST_GENERATION_COST else 0.0
total_cost += museum_cost
print(f"\n  Museum tour: {elapsed:.1f}s, cost=${museum_cost:.4f}")

museum_tour_text = None
if result and result[0]:
    museum_tour_text = result[0]
    # Copy to destination
    import shutil
    if os.path.exists(museum_output):
        dest_file = os.path.join(dest_dir, "LOCAL284_asian_arts_5stop.txt")
        shutil.copy2(museum_output, dest_file)
        print(f"  Copied to {dest_file}")

    stops, facts_data = count_facts(museum_tour_text)
    print(f"\n  MUSEUM RESULTS ({len(stops)} stops):")
    print(f"  {'Stop':<50} {'Corpus':>7} {'Facts':>5} {'Words':>5}")
    print(f"  {'-'*50} {'-'*7} {'-'*5} {'-'*5}")
    total_facts = 0
    for fd in facts_data:
        # Look up corpus depth
        stop_lower = fd['name'].lower().strip()
        depth = corpus_depth_asian.get(stop_lower, 0)
        # Try fuzzy match if exact doesn't work
        if depth == 0:
            for k, v in corpus_depth_asian.items():
                if k in stop_lower or stop_lower in k:
                    depth = v
                    break
        print(f"  {fd['name'][:50]:<50} {depth:>7} {fd['facts']:>5} {fd['words']:>5}")
        total_facts += fd['facts']
    avg_facts = total_facts / len(facts_data) if facts_data else 0
    print(f"\n  FACTS/STOP: {avg_facts:.1f} (baseline: 1.6)")
    print(f"  TOTAL FACTS: {total_facts}")
else:
    print("  MUSEUM TOUR FAILED — no output")

# ════════════════════════════════════════════════════════════════════════════
# PART 2: 2-stop Riviera walking tours (≥3 runs)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2: 2-stop Riviera walking tours (3 runs)")
print("=" * 70)

riviera_2stop_results = []
riviera_all_stops = set()

for run_idx in range(3):
    print(f"\n  --- Run {run_idx + 1}/3 ---")
    output_file = os.path.join(tours_dir, f"LOCAL284_riviera_2stop_run{run_idx+1}.txt")
    
    start_time = time.time()
    try:
        result = generate_tour_text(
            location='French Riviera, Nice, France',
            tour_type='walking',
            output_file=output_file,
            total_stops=2,
            persona=None,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n    FAILED after {elapsed:.1f}s: {e}")
        result = None
    
    elapsed = time.time() - start_time
    run_cost = _LAST_GENERATION_COST.get("total_cost", 0.0) if _LAST_GENERATION_COST else 0.0
    total_cost += run_cost
    
    if result and result[0]:
        tour_text = result[0]
        # Copy
        import shutil
        if os.path.exists(output_file):
            dest_file = os.path.join(dest_dir, f"LOCAL284_riviera_2stop_run{run_idx+1}.txt")
            shutil.copy2(output_file, dest_file)
        
        stops, facts_data = count_facts(tour_text)
        total_facts_run = sum(fd['facts'] for fd in facts_data)
        total_words_run = sum(fd['words'] for fd in facts_data)
        avg_facts_run = total_facts_run / len(facts_data) if facts_data else 0
        stop_names = [fd['name'] for fd in facts_data]
        riviera_all_stops.update(stop_names)
        
        riviera_2stop_results.append({
            'run': run_idx + 1,
            'stops': stop_names,
            'facts_per_stop': avg_facts_run,
            'total_facts': total_facts_run,
            'words': total_words_run,
            'elapsed': elapsed,
            'cost': run_cost,
        })
        print(f"    Stops: {', '.join(stop_names)}")
        print(f"    Facts/stop: {avg_facts_run:.1f}, Words: {total_words_run}, Time: {elapsed:.1f}s")
    else:
        print(f"    FAILED")

    # Cost check
    if total_cost > CEILING:
        print(f"\n  CEILING EXCEEDED: ${total_cost:.4f} > ${CEILING:.2f}")
        break

# ════════════════════════════════════════════════════════════════════════════
# PART 3: 8-stop Riviera walking tour (1 run)
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 3: 8-stop Riviera walking tour (1 run)")
print("=" * 70)

if total_cost < CEILING - 0.20:  # Leave margin for 8-stop
    output_file = os.path.join(tours_dir, "LOCAL284_riviera_8stop.txt")
    
    start_time = time.time()
    try:
        result = generate_tour_text(
            location='French Riviera, Nice, France',
            tour_type='walking',
            output_file=output_file,
            total_stops=8,
            persona=None,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n  FAILED after {elapsed:.1f}s: {e}")
        result = None
    
    elapsed = time.time() - start_time
    run_cost = _LAST_GENERATION_COST.get("total_cost", 0.0) if _LAST_GENERATION_COST else 0.0
    total_cost += run_cost
    
    if result and result[0]:
        tour_text = result[0]
        import shutil
        if os.path.exists(output_file):
            dest_file = os.path.join(dest_dir, "LOCAL284_riviera_8stop.txt")
            shutil.copy2(output_file, dest_file)
        
        stops, facts_data = count_facts(tour_text)
        total_facts_8 = sum(fd['facts'] for fd in facts_data)
        total_words_8 = sum(fd['words'] for fd in facts_data)
        avg_facts_8 = total_facts_8 / len(facts_data) if facts_data else 0
        stop_names_8 = [fd['name'] for fd in facts_data]
        riviera_all_stops.update(stop_names_8)
        
        print(f"  8-STOP RESULTS:")
        print(f"  Stops: {', '.join(stop_names_8)}")
        print(f"  Facts/stop: {avg_facts_8:.1f} (baseline: 8.8)")
        print(f"  Total facts: {total_facts_8} (baseline: 53)")
        print(f"  Total words: {total_words_8}")
        print(f"  Time: {elapsed:.1f}s, Cost: ${run_cost:.4f}")
    else:
        print("  8-STOP TOUR FAILED")
        avg_facts_8 = 0
        total_facts_8 = 0
else:
    print(f"  SKIPPED (cost already ${total_cost:.4f}, near ceiling)")
    avg_facts_8 = 0
    total_facts_8 = 0

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SUMMARY — LOCAL-284 MEASUREMENT")
print("=" * 70)

print(f"\n  Total cost: ${total_cost:.4f} (ceiling: ${CEILING:.2f})")

print(f"\n  MUSEUM (5-stop Musée des Arts Asiatiques):")
if museum_tour_text:
    print(f"    Facts/stop: {avg_facts:.1f} (baseline: 1.6)")
else:
    print(f"    FAILED")

print(f"\n  RIVIERA 2-stop ({len(riviera_2stop_results)} runs):")
for r in riviera_2stop_results:
    print(f"    Run {r['run']}: {r['facts_per_stop']:.1f} f/stop, {r['words']} words | {', '.join(r['stops'])}")
if riviera_2stop_results:
    avg_2stop = sum(r['facts_per_stop'] for r in riviera_2stop_results) / len(riviera_2stop_results)
    print(f"    Average: {avg_2stop:.1f} f/stop (baseline: 6.0)")

print(f"\n  RIVIERA 8-stop:")
if avg_facts_8 > 0:
    print(f"    Facts/stop: {avg_facts_8:.1f} (baseline: 8.8)")
    print(f"    Total facts: {total_facts_8} (baseline: 53)")

print(f"\n  STOP VARIETY (distinct stops across ALL Riviera runs): {len(riviera_all_stops)}")
for s in sorted(riviera_all_stops):
    print(f"    - {s}")

# ── Cleanup: D141 ──────────────────────────────────────────────────────────
print("\n" + "-" * 70)
print("CLEANUP (D141)")
print("-" * 70)

conn = get_connection()
cur = conn.cursor()

# Find rows created by this run
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
new_rows = count_after - count_before
print(f"  audio_tours: was {count_before}, now {count_after} ({new_rows} new)")

if new_rows > 0:
    # Get the IDs of new rows (created after our run started)
    cur.execute(
        "SELECT id, is_test FROM audio_tours ORDER BY id DESC LIMIT %s",
        (new_rows + 5,)
    )
    rows_to_check = cur.fetchall()
    deleted_ids = []
    for row_id, is_test in rows_to_check:
        if row_id > max(EXPECTED_NICE):
            # Verify is_test before deleting
            cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
            check = cur.fetchone()
            if check and check[0]:
                cur.execute("DELETE FROM audio_tours WHERE id = %s", (row_id,))
                deleted_ids.append(row_id)
    if deleted_ids:
        conn.commit()
        print(f"  Deleted {len(deleted_ids)} test rows: {deleted_ids}")
    else:
        print(f"  No test rows to delete (rows may not have is_test=true)")

# Verify Nice list preserved
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_post = [r[0] for r in cur.fetchall()]
print(f"  Nice list after: {nice_post}")
assert nice_post == EXPECTED_NICE, f"Nice list CORRUPTED: {nice_post}"
print(f"  ✓ Nice list preserved")

conn.close()
print(f"\nDONE. Total cost: ${total_cost:.4f}")
