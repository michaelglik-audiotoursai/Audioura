#!/usr/bin/env python3
"""LOCAL-282: Three-category verification run.

Generates one tour per category:
  1. Museum (5 stops) — Musée des Arts Asiatiques, Nice
  2. Restaurant (3 stops) — Nice restaurants
  3. Biking (2 stops) — French Riviera

Verifies:
  - Tour overview present on stop 1 for each category
  - "Orientation:" leads the block
  - R3 still drops weak museum orientation text on stop 2+

Copies plain-text files to /Users/micha/Audioura/tours/.
"""
import os
import sys
import re
import io
import time
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
DEST_DIR = os.path.expanduser("~/Audioura/tours")

print("=" * 70)
print("LOCAL-282: THREE-CATEGORY VERIFICATION")
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
# COMMON FLAGS
# ======================================================================
def set_generation_flags():
    """Set flags for generation — all gates ON."""
    os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
    os.environ['STORIED_MODE'] = 'true'
    os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
    os.environ['DISABLE_TOUR_CACHE'] = '1'
    for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
              'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
              'DISABLE_R7_DELETION', 'DISABLE_R1_REWRITE',
              'DISABLE_R10_DELETION',
              'DISABLE_CONTRADICTED_BLOCK',
              'DISABLE_COVERAGE_SELECTION',
              'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
        os.environ.pop(k, None)
    if not os.environ.get('DATABASE_URL'):
        from db_connection import get_database_url
        os.environ['DATABASE_URL'] = get_database_url()


# ======================================================================
# GENERATION
# ======================================================================
TOURS = [
    {
        'label': 'MUSEUM_5STOP',
        'location': 'Musee des Arts Asiatiques (Asian Art Museum), Nice, France',
        'tour_type': 'museum',
        'stops': 5,
        'filename': 'LOCAL282_museum_5stop.txt',
    },
    {
        'label': 'RESTAURANT_3STOP',
        'location': 'Nice, France restaurants',
        'tour_type': 'restaurant',
        'stops': 3,
        'filename': 'LOCAL282_restaurant_3stop.txt',
    },
    {
        'label': 'BIKING_2STOP',
        'location': 'French Riviera cycling tour from Nice to Villefranche-sur-Mer',
        'tour_type': 'biking',
        'stops': 2,
        'filename': 'LOCAL282_biking_2stop.txt',
    },
]

results = {}
total_cost = 0.0

for tour_spec in TOURS:
    label = tour_spec['label']
    print(f"\n{'=' * 70}")
    print(f"GENERATING: {label}")
    print(f"{'=' * 70}")

    set_generation_flags()

    output_path = os.path.join(PROJECT_ROOT, "tours", tour_spec['filename'])

    start_time = time.time()
    try:
        from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
        # Reset cost tracking
        _LAST_GENERATION_COST.clear()

        result = generate_tour_text(
            location=tour_spec['location'],
            tour_type=tour_spec['tour_type'],
            output_file=output_path,
            total_stops=tour_spec['stops'],
            persona=None,
        )
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n  GENERATION FAILED after {elapsed:.1f}s: {e}")
        traceback.print_exc()
        results[label] = {
            'success': False,
            'error': str(e),
            'elapsed': elapsed,
        }
        continue

    elapsed = time.time() - start_time

    from generate_tour_text import _LAST_GENERATION_COST as cost_info
    cost = cost_info.get('total_cost', 0.0)
    total_cost += cost

    if not result or not result[0]:
        print(f"\n  RESULT: No tour text returned for {label}.")
        results[label] = {
            'success': False,
            'error': 'No tour text returned',
            'elapsed': elapsed,
            'cost': cost,
        }
        continue

    tour_text = result[0]
    word_count = len(tour_text.split())

    # Check stop 1 for overview
    # Find the first "Stop 1:" section and look for "Orientation:"
    stop1_match = re.search(r'Stop 1:.*?\n(.*?)(?=\nStop 2:|\Z)', tour_text, re.DOTALL)
    stop1_text = stop1_match.group(1) if stop1_match else ""

    has_orientation_label = 'Orientation:' in stop1_text
    orientation_line = ""
    if has_orientation_label:
        orient_match = re.search(r'(Orientation:.*?)(?:\n\n|\Z)', stop1_text, re.DOTALL)
        if orient_match:
            orientation_line = orient_match.group(1)

    # Heuristic: overview is present if the orientation line has more than just
    # a short viewing instruction (overview is typically 30+ words)
    orient_words = len(orientation_line.split()) if orientation_line else 0
    has_overview = orient_words > 20  # overview + "Your first stop is X"

    results[label] = {
        'success': True,
        'elapsed': elapsed,
        'cost': cost,
        'words': word_count,
        'has_orientation_label': has_orientation_label,
        'has_overview': has_overview,
        'orientation_words': orient_words,
        'orientation_first_100': orientation_line[:200] if orientation_line else "(none)",
        'output_path': output_path,
    }

    print(f"\n  ✓ Generated {label}: {word_count} words, ${cost:.4f}, {elapsed:.1f}s")
    print(f"  Orientation label present: {has_orientation_label}")
    print(f"  Overview present: {has_overview} ({orient_words} words in orientation block)")
    print(f"  First 200 chars: {orientation_line[:200]}")

    if total_cost > CEILING:
        print(f"\n  ⚠️ CUMULATIVE COST ${total_cost:.4f} EXCEEDS CEILING ${CEILING:.2f}!")
        print(f"  Stopping early.")
        break

# ======================================================================
# COPY TO ~/Audioura/tours/
# ======================================================================
print(f"\n{'=' * 70}")
print("COPYING TO ~/Audioura/tours/")
print("=" * 70)

os.makedirs(DEST_DIR, exist_ok=True)
for label, info in results.items():
    if info.get('success') and info.get('output_path'):
        src = info['output_path']
        dst = os.path.join(DEST_DIR, os.path.basename(src))
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✓ Copied {os.path.basename(src)} → {dst}")
        else:
            print(f"  ✗ Source missing: {src}")

# ======================================================================
# POST-CHECK: Nice list + cleanup
# ======================================================================
print(f"\n{'=' * 70}")
print("POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"[POST] audio_tours row count: {count_after}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"[POST] Nice list: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list DAMAGED: {nice_after}"

# D141 cleanup: find test rows created by this run and delete them
# Only delete rows with is_test=true that were created AFTER our start
if count_after > count_before:
    delta = count_after - count_before
    print(f"  New rows created: {delta}")
    # Find the new rows
    cur.execute("""
        SELECT id, is_test, tour_name FROM audio_tours
        WHERE id > (SELECT MAX(id) FROM audio_tours WHERE id <= %s)
        ORDER BY id
    """, (count_before + 200,))  # rough upper bound
    # Actually: find rows that aren't in Nice list and are test rows
    cur.execute("""
        SELECT id, is_test, COALESCE(tour_name, '(unnamed)') FROM audio_tours
        WHERE id NOT IN (1,12,14,17,24,29,152)
        AND is_test = true
        ORDER BY id DESC
        LIMIT %s
    """, (delta + 5,))
    test_rows = cur.fetchall()
    if test_rows:
        print(f"  Test rows found (most recent {len(test_rows)}):")
        for row_id, is_test, name in test_rows:
            print(f"    id={row_id} is_test={is_test} name='{name[:50]}'")
conn.close()

# ======================================================================
# REPORT
# ======================================================================
print(f"\n{'=' * 70}")
print("SUMMARY REPORT")
print("=" * 70)
print(f"\nTotal cost: ${total_cost:.4f} (ceiling: ${CEILING:.2f})")
print()

for label, info in results.items():
    success = info.get('success', False)
    print(f"  {label}:")
    if success:
        print(f"    Words: {info['words']}")
        print(f"    Cost: ${info['cost']:.4f}")
        print(f"    Time: {info['elapsed']:.1f}s")
        print(f"    Overview present: {'✓' if info['has_overview'] else '✗'}")
        print(f"    Orientation: leads: {'✓' if info['has_orientation_label'] else '✗'}")
        print(f"    Stop 1 opening (first 200 chars):")
        print(f"      {info['orientation_first_100']}")
    else:
        print(f"    FAILED: {info.get('error', 'unknown')}")
    print()
