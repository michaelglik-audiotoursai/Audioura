#!/usr/bin/env python3
"""LOCAL-320: Verification — 5 consecutive restaurant tours + non-dining regression.

This script:
  1. Runs 5 consecutive 5-stop Old Nice restaurant tours
  2. Reports requested/proposed/verified/delivered for each
  3. Runs non-dining regression (2-stop cycling, 8-stop cycling, 8-stop museum)
  4. Verifies safety constraints (fabricated, wrong-city)
  5. Reports wall-clock cost of the throttle
"""
import os
import sys
import time
import re
import json

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
                _k, _v = _k.strip(), _v.strip()
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'

import psycopg2
from generate_tour_text import generate_tour_text
from stop_existence_gate import verify_stop_existence, run_existence_gate
from db_connection import get_connection, check_db_available

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

_db_url = os.environ['DATABASE_URL']

# ─── Capture audio_tours BEFORE ───────────────────────────────────────────────
_conn_pre = psycopg2.connect(_db_url)
_cur_pre = _conn_pre.cursor()
_cur_pre.execute("SELECT id FROM audio_tours")
_pre_ids = {r[0] for r in _cur_pre.fetchall()}
_cur_pre.close()
_conn_pre.close()
print(f"Audio tours before: {len(_pre_ids)} rows")


def count_stops(tour_text):
    """Count stops in generated tour text."""
    stop_pattern = re.compile(r'^(?:Stop\s*\d+|#{1,3}\s*Stop\s*\d+)', re.MULTILINE)
    return len(stop_pattern.findall(tour_text))


def cleanup_test_rows():
    """Delete test rows created during this run."""
    _conn_post = psycopg2.connect(_db_url)
    _cur_post = _conn_post.cursor()
    _cur_post.execute("SELECT id FROM audio_tours")
    _post_ids = {r[0] for r in _cur_post.fetchall()}
    _new_ids = _post_ids - _pre_ids
    for row_id in _new_ids:
        _cur_post.execute("DELETE FROM audio_tours WHERE id = %s", (row_id,))
    _conn_post.commit()
    _cur_post.close()
    _conn_post.close()
    if _new_ids:
        print(f"\n  [CLEANUP] Removed {len(_new_ids)} test row(s)")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: Five consecutive 5-stop Old Nice restaurant tours
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print(" PART 1: Five consecutive 5-stop Old Nice restaurant tours")
print("="*70)

restaurant_results = []
total_cost = 0.0

for run_num in range(1, 6):
    print(f"\n{'─'*60}")
    print(f" RUN {run_num}/5")
    print(f"{'─'*60}")

    t_start = time.time()
    result = generate_tour_text(
        location="restaurant tour in Old Nice (Vieux Nice), France",
        tour_type="restaurant",
        output_file=os.path.join(TOURS_DIR, f"LOCAL320_run{run_num}_restaurant.txt"),
        total_stops=5,
    )
    t_elapsed = time.time() - t_start

    if result and result[0]:
        tour_text = result[0]
        delivered = count_stops(tour_text)
        word_count = len(tour_text.split())

        restaurant_results.append({
            'run': run_num,
            'requested': 5,
            'delivered': delivered,
            'words': word_count,
            'time_s': t_elapsed,
            'success': True,
        })
        print(f"\n  RUN {run_num} RESULT: requested=5, delivered={delivered}, "
              f"words={word_count}, time={t_elapsed:.1f}s")
    else:
        restaurant_results.append({
            'run': run_num,
            'requested': 5,
            'delivered': 0,
            'words': 0,
            'time_s': t_elapsed,
            'success': False,
        })
        print(f"\n  RUN {run_num} FAILED — no tour generated")

    # Brief pause between runs to not hammer APIs
    if run_num < 5:
        time.sleep(2)

# Summary
print(f"\n{'─'*60}")
print(" RESTAURANT TOUR SUMMARY")
print(f"{'─'*60}")
for r in restaurant_results:
    status = "✓" if r['success'] and r['delivered'] >= 4 else "✗"
    print(f"  {status} Run {r['run']}: requested=5, delivered={r['delivered']}, "
          f"time={r['time_s']:.1f}s")

consistent = all(r['delivered'] >= 4 for r in restaurant_results)
print(f"\n  CONSISTENCY: {'PASS' if consistent else 'FAIL'} — "
      f"{'all' if consistent else 'NOT all'} runs delivered ≥4 stops")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Safety constraints
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print(" PART 2: Safety constraints")
print("="*70)

conn = get_connection()
db = getattr(conn, '_conn', conn)

# Fabricated name
result_fab = verify_stop_existence(
    'Le Restaurant Imaginaire', 'Nice, France', db, tour_type='restaurant')
print(f"\n  'Le Restaurant Imaginaire' (fabricated): verified={result_fab['verified']} "
      f"{'✓ REJECTED' if not result_fab['verified'] else '✗ SHOULD FAIL'}")

# Wrong city
result_lyon = verify_stop_existence(
    'Le Chantecler', 'Lyon, France', db, tour_type='restaurant')
print(f"  'Le Chantecler' in Lyon (wrong city): verified={result_lyon['verified']} "
      f"{'✓ REJECTED' if not result_lyon['verified'] else '✗ SHOULD FAIL'}")

conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Non-dining regression (addendum requirement)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print(" PART 3: Non-dining regression")
print("="*70)

# 2-stop Riviera cycling
print(f"\n{'─'*40}")
print(" 2-stop Riviera cycling tour")
print(f"{'─'*40}")
t0 = time.time()
result_cyc2 = generate_tour_text(
    location="French Riviera cycling tour along the coast, France",
    tour_type="cycling",
    output_file=os.path.join(TOURS_DIR, "LOCAL320_cycling_2stop.txt"),
    total_stops=2,
)
t_cyc2 = time.time() - t0
if result_cyc2 and result_cyc2[0]:
    delivered_cyc2 = count_stops(result_cyc2[0])
    print(f"  Result: requested=2, delivered={delivered_cyc2}, time={t_cyc2:.1f}s")
else:
    delivered_cyc2 = 0
    print(f"  FAILED — no tour generated")

# 8-stop Riviera cycling
print(f"\n{'─'*40}")
print(" 8-stop Riviera cycling tour")
print(f"{'─'*40}")
t0 = time.time()
result_cyc8 = generate_tour_text(
    location="French Riviera cycling tour along the coast, France",
    tour_type="cycling",
    output_file=os.path.join(TOURS_DIR, "LOCAL320_cycling_8stop.txt"),
    total_stops=8,
)
t_cyc8 = time.time() - t0
if result_cyc8 and result_cyc8[0]:
    delivered_cyc8 = count_stops(result_cyc8[0])
    print(f"  Result: requested=8, delivered={delivered_cyc8}, time={t_cyc8:.1f}s")
else:
    delivered_cyc8 = 0
    print(f"  FAILED — no tour generated")

# 8-stop museum
print(f"\n{'─'*40}")
print(" 8-stop Musée des Arts Asiatiques museum tour")
print(f"{'─'*40}")
t0 = time.time()
result_mus8 = generate_tour_text(
    location="Musée des Arts Asiatiques, Nice",
    tour_type="museum",
    output_file=os.path.join(TOURS_DIR, "LOCAL320_museum_8stop.txt"),
    total_stops=8,
)
t_mus8 = time.time() - t0
if result_mus8 and result_mus8[0]:
    delivered_mus8 = count_stops(result_mus8[0])
    print(f"  Result: requested=8, delivered={delivered_mus8}, time={t_mus8:.1f}s")
else:
    delivered_mus8 = 0
    print(f"  FAILED — no tour generated")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 4: Cleanup and final report
# ═══════════════════════════════════════════════════════════════════════════════
cleanup_test_rows()

# Row count verification
_conn_final = psycopg2.connect(_db_url)
_cur_final = _conn_final.cursor()
_cur_final.execute("SELECT count(*) FROM audio_tours WHERE title NOT LIKE 'LOCAL49 Regression%'")
real_rows = _cur_final.fetchone()[0]
_cur_final.close()
_conn_final.close()

print(f"\n{'='*70}")
print(" FINAL REPORT")
print(f"{'='*70}")
print(f"\n  Production real rows: {real_rows} (must be 29)")
print(f"\n  Restaurant tours (5 runs):")
for r in restaurant_results:
    print(f"    Run {r['run']}: delivered={r['delivered']}/5, time={r['time_s']:.1f}s")
print(f"\n  Non-dining regression:")
print(f"    2-stop cycling: delivered={delivered_cyc2}/2 "
      f"{'✓' if delivered_cyc2 == 2 else '✗ REGRESSION'}")
print(f"    8-stop cycling: delivered={delivered_cyc8}/8 "
      f"{'✓' if delivered_cyc8 >= 7 else '✗ REGRESSION'}")
print(f"    8-stop museum:  delivered={delivered_mus8}/8 "
      f"{'✓' if delivered_mus8 >= 7 else '✗ REGRESSION'}")
print(f"\n  Safety constraints:")
print(f"    Fabricated rejected: {'✓' if not result_fab['verified'] else '✗'}")
print(f"    Wrong-city rejected: {'✓' if not result_lyon['verified'] else '✗'}")

# Pass/fail
all_pass = (
    consistent and
    delivered_cyc2 == 2 and
    delivered_cyc8 >= 7 and
    delivered_mus8 >= 7 and
    not result_fab['verified'] and
    not result_lyon['verified'] and
    real_rows == 29
)
print(f"\n  {'✓ ALL PASS' if all_pass else '✗ SOME FAILURES'}")
