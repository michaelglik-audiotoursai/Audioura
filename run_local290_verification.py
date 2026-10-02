#!/usr/bin/env python3
"""LOCAL-290: Verify stop-loss fixes — 3×8-stop + 2×2-stop Riviera tours.

Reports for each:
  - stops requested / proposed / verified / delivered
  - every UNVERIFIED stop with reason + tier-1 fallback result
  - verify_landmarks match rate before/after normalization fix
  - whether replenishment fired and what it added

Copies tours to ~/Audioura/tours/.
"""
import os
import sys
import time
import json
import shutil
import re

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
                _k, _v = _k.strip(), _v.strip()
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'

# Force production DB for corpus reads
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

# D186: spine stays on gpt-4o
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'

from db_connection import get_connection

# Capture audio_tours BEFORE
_conn_pre = get_connection()
_cur_pre = _conn_pre.cursor()
_cur_pre.execute("SELECT id, is_test FROM audio_tours ORDER BY id")
_pre_rows = {r[0]: r[1] for r in _cur_pre.fetchall()}
_conn_pre.close()
print(f"audio_tours before: {len(_pre_rows)} rows, IDs: {sorted(_pre_rows.keys())[:20]}...")
_protected_ids = {1, 12, 14, 17, 24, 29, 152}
print(f"Protected IDs present: {_protected_ids.intersection(_pre_rows.keys())}")

from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

# Tour configurations: (stops, location, tour_type, description, iteration)
TOUR_CONFIGS = [
    (8, "French Riviera cycling tour, France", "biking", "8-stop cycling Riviera #1", 1),
    (8, "French Riviera walking tour along the coast, France", "walking", "8-stop walking Riviera #2", 2),
    (8, "French Riviera cycling tour from Nice to Cannes, France", "biking", "8-stop cycling Nice-Cannes #3", 3),
    (2, "Cap d'Antibes and Eze cycling tour, French Riviera", "biking", "2-stop Antibes+Eze #1", 1),
    (2, "Menton and Monaco walking tour, French Riviera", "walking", "2-stop Menton+Monaco #2", 2),
]

results = []
total_cost = 0.0
created_tour_ids = []

for stops, location, tour_type, label, iteration in TOUR_CONFIGS:
    print(f"\n{'='*70}")
    print(f"GENERATING: {label}")
    print(f"  Location: {location}")
    print(f"  Type: {tour_type}, Stops: {stops}")
    print(f"{'='*70}\n")

    output_file = os.path.join(TOURS_DIR, f"LOCAL290_{stops}stop_{iteration}.txt")
    start_time = time.time()

    try:
        result = generate_tour_text(
            location=location,
            tour_type=tour_type,
            output_file=output_file,
            total_stops=stops,
            persona=None,
        )
        elapsed = time.time() - start_time

        if not result or not result[0]:
            print(f"\n  *** GENERATION FAILED (returned None) after {elapsed:.1f}s ***")
            results.append({
                'config': label,
                'requested': stops,
                'delivered': 0,
                'status': 'FAILED',
                'cost': 0,
                'elapsed': elapsed,
            })
            continue

        tour_text = result[0]
        # Extract cost (result[2] is (tokens, cost) tuple in some paths)
        run_cost = 0.0
        if len(result) > 2 and result[2]:
            try:
                if isinstance(result[2], tuple):
                    run_cost = float(result[2][1]) if result[2][1] else 0
                else:
                    run_cost = float(result[2])
            except (TypeError, ValueError):
                pass
        total_cost += run_cost

        # Count delivered stops from tour text
        delivered_stops = len(re.findall(r'(?:^|\n)\s*Stop \d+', tour_text)) if tour_text else 0
        # Fallback: count section headers
        if delivered_stops == 0 and tour_text:
            delivered_stops = len(re.findall(r'(?:^|\n)#+\s+Stop \d+|(?:^|\n)\*\*Stop \d+', tour_text))
        if delivered_stops == 0 and tour_text:
            # Count numbered paragraphs that look like stops
            delivered_stops = len(re.findall(r'(?:^|\n)\d+\.\s+[A-Z]', tour_text))

        print(f"\n  Delivered: {delivered_stops}/{stops} stops")
        print(f"  Cost: ${run_cost:.4f}")
        print(f"  Time: {elapsed:.1f}s")
        print(f"  Saved: {output_file}")

        results.append({
            'config': label,
            'requested': stops,
            'delivered': delivered_stops,
            'status': 'OK' if delivered_stops >= stops else 'SHORT',
            'cost': run_cost,
            'elapsed': elapsed,
        })

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n  *** ERROR: {e} ***")
        import traceback
        traceback.print_exc()
        results.append({
            'config': label,
            'requested': stops,
            'delivered': 0,
            'status': f'ERROR: {str(e)[:50]}',
            'cost': 0,
            'elapsed': elapsed,
        })

# === CLEANUP (D141) ===
print(f"\n{'='*70}")
print("CLEANUP (D141)")
print(f"{'='*70}")

_conn_post = get_connection()
_cur_post = _conn_post.cursor()
_cur_post.execute("SELECT id, is_test FROM audio_tours ORDER BY id")
_post_rows = {r[0]: r[1] for r in _cur_post.fetchall()}

# Find new rows (created by this run)
_new_ids = set(_post_rows.keys()) - set(_pre_rows.keys())
print(f"New rows created: {sorted(_new_ids)}")

# Delete ONLY rows this run created AND that have is_test=true
_deleted = []
for _id in sorted(_new_ids):
    # Verify is_test before delete
    _cur_post.execute("SELECT is_test FROM audio_tours WHERE id = %s", (_id,))
    _row = _cur_post.fetchone()
    if _row and _row[0]:
        _cur_post.execute("DELETE FROM audio_tours WHERE id = %s", (_id,))
        _deleted.append(_id)
    else:
        print(f"  SKIPPED id={_id} (is_test={_row[0] if _row else 'NOT FOUND'})")

_conn_post.commit()
_conn_post.close()
print(f"Deleted {len(_deleted)} test rows: {_deleted}")

# Verify protected rows
_conn_verify = get_connection()
_cur_verify = _conn_verify.cursor()
_cur_verify.execute("SELECT id FROM audio_tours WHERE id IN %s ORDER BY id",
                    (tuple(_protected_ids),))
_surviving = {r[0] for r in _cur_verify.fetchall()}
_conn_verify.close()
assert _surviving == _protected_ids, f"PROTECTED ROWS MISSING: {_protected_ids - _surviving}"
print(f"Protected IDs verified intact: {sorted(_surviving)}")

# === SUMMARY ===
print(f"\n{'='*70}")
print("SUMMARY — LOCAL-290 Verification")
print(f"{'='*70}")
print(f"{'Config':<25s} {'Requested':>9s} {'Delivered':>9s} {'Status':<10s} {'Cost':>8s}")
print("-" * 70)
for r in results:
    print(f"{r['config']:<25s} {r['requested']:>9d} {r.get('delivered',0):>9d} "
          f"{r['status']:<10s} ${r.get('cost',0):>7.4f}")
print("-" * 70)
print(f"{'TOTAL':<25s} {sum(r['requested'] for r in results):>9d} "
      f"{sum(r.get('delivered',0) for r in results):>9d} "
      f"{'':10s} ${total_cost:>7.4f}")

any_short = any(r.get('delivered', 0) < r['requested'] for r in results)
if any_short:
    print("\n⚠️  One or more tours delivered SHORT — see per-tour output above for reasons.")
else:
    print("\n✓ All tours delivered at requested stop count.")
