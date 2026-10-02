#!/usr/bin/env python3
"""LOCAL-313: Generate a 5-stop restaurant tour of Old Nice.

Proves the bug is fixed: before this fix, the existence gate dropped all
restaurants as unverified → FATAL. Now they verify via Nominatim/OSM and
the tour generates successfully.

Also generates a 2-stop Riviera walking tour to confirm museum/geographic
paths are unregressed.
"""
import os
import sys
import time
import re

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

# Force production DB for corpus reads
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

# D186: spine stays on gpt-4o
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'

import psycopg2

from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

# Protected IDs (Nice list from task spec)
_protected_ids = {1, 12, 14, 17, 24, 29, 152}

# ─── D141: Capture audio_tours BEFORE ─────────────────────────────────────────
_db_url = os.environ['DATABASE_URL']
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
    stop_count = len(stop_pattern.findall(tour_text))
    orientation_count = len(re.findall(r'^Orientation:', tour_text, re.MULTILINE))
    return max(stop_count, orientation_count)


def cleanup_test_rows():
    """Delete test rows created during this run."""
    _conn_post = psycopg2.connect(_db_url)
    _cur_post = _conn_post.cursor()
    _cur_post.execute("SELECT id FROM audio_tours")
    _post_ids = {r[0] for r in _cur_post.fetchall()}
    _new_ids = _post_ids - _pre_ids

    deleted = []
    for row_id in _new_ids:
        _cur_post.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
        r = _cur_post.fetchone()
        if r and r[0]:
            _cur_post.execute("DELETE FROM audio_tours WHERE id = %s", (row_id,))
            deleted.append(row_id)
    _conn_post.commit()

    # Verify protected IDs still present
    _cur_post.execute("SELECT id FROM audio_tours WHERE id = ANY(%s)", (list(_protected_ids),))
    _remaining = {r[0] for r in _cur_post.fetchall()}
    _cur_post.close()
    _conn_post.close()

    print(f"  Cleaned up {len(deleted)} test rows. Protected: {len(_remaining)}/{len(_protected_ids)}")
    return len(_post_ids) - len(deleted)


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR 1: 5-stop Old Nice restaurant tour (the bug scenario)
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TOUR 1: 5-stop Old Nice restaurant tour")
print(f"{'=' * 70}\n")

location_1 = "restaurant tour in Old Nice (Vieux Nice), France"
tour_type_1 = "restaurant"
total_stops_1 = 5
output_file_1 = os.path.join(TOURS_DIR, "LOCAL313_5stop_old_nice_restaurant.txt")

start_1 = time.time()
result_1 = generate_tour_text(
    location=location_1,
    tour_type=tour_type_1,
    output_file=output_file_1,
    total_stops=total_stops_1,
    persona=None,
)
elapsed_1 = time.time() - start_1

if not result_1 or not result_1[0]:
    print(f"\n  *** TOUR 1 FAILED (returned None) after {elapsed_1:.1f}s ***")
    cleanup_test_rows()
    sys.exit(1)

tour_text_1 = result_1[0]
delivered_1 = count_stops(tour_text_1)
words_1 = len(tour_text_1.split())

print(f"\n  TOUR 1 RESULT:")
print(f"    Requested: {total_stops_1} stops")
print(f"    Delivered: {delivered_1} stops")
print(f"    Words: {words_1}")
print(f"    Time: {elapsed_1:.1f}s")
print(f"    Output: {output_file_1}")

if delivered_1 >= total_stops_1:
    print(f"    ✓ SUCCESS — restaurant tour generated")
else:
    print(f"    ⚠ SHORT — {delivered_1}/{total_stops_1} stops")

# ═══════════════════════════════════════════════════════════════════════════════
# TOUR 2: 2-stop Riviera walking tour (unregression check)
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("TOUR 2: 2-stop Riviera walking tour (museum/geographic unregression)")
print(f"{'=' * 70}\n")

location_2 = "French Riviera walking tour along the coast, France"
tour_type_2 = "walking"
total_stops_2 = 2
output_file_2 = os.path.join(TOURS_DIR, "LOCAL313_2stop_riviera_unregression.txt")

start_2 = time.time()
result_2 = generate_tour_text(
    location=location_2,
    tour_type=tour_type_2,
    output_file=output_file_2,
    total_stops=total_stops_2,
    persona=None,
)
elapsed_2 = time.time() - start_2

if not result_2 or not result_2[0]:
    print(f"\n  *** TOUR 2 FAILED (returned None) after {elapsed_2:.1f}s ***")
    cleanup_test_rows()
    sys.exit(1)

tour_text_2 = result_2[0]
delivered_2 = count_stops(tour_text_2)
words_2 = len(tour_text_2.split())

print(f"\n  TOUR 2 RESULT:")
print(f"    Requested: {total_stops_2} stops")
print(f"    Delivered: {delivered_2} stops")
print(f"    Words: {words_2}")
print(f"    Time: {elapsed_2:.1f}s")
print(f"    Output: {output_file_2}")

if delivered_2 >= total_stops_2:
    print(f"    ✓ SUCCESS — Riviera tour unregressed")
else:
    print(f"    ⚠ SHORT — {delivered_2}/{total_stops_2} stops")

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("SUMMARY")
print(f"{'=' * 70}")
print(f"  Tour 1 (restaurant): {delivered_1}/{total_stops_1} stops, {words_1} words")
print(f"  Tour 2 (walking):    {delivered_2}/{total_stops_2} stops, {words_2} words")

# Report cost from api_call_logger
try:
    import api_call_logger
    cost = getattr(api_call_logger, '_total_cost', None)
    if cost is not None:
        print(f"  Total API cost: ${cost:.4f}")
except Exception:
    pass

# Try to get cost from generate_tour_text module
try:
    from generate_tour_text import _LAST_GENERATION_COST
    if _LAST_GENERATION_COST:
        print(f"  Last generation cost breakdown: {_LAST_GENERATION_COST}")
except (ImportError, AttributeError):
    pass

# Cleanup
final_count = cleanup_test_rows()
print(f"  Final audio_tours count: {final_count} (production: 29)")

# Verify production row count stayed at 29
_conn_verify = psycopg2.connect(_db_url)
_cur_verify = _conn_verify.cursor()
_cur_verify.execute("SELECT count(*) FROM audio_tours WHERE is_test = false")
prod_count = _cur_verify.fetchone()[0]
_cur_verify.close()
_conn_verify.close()
print(f"  Production real rows: {prod_count} (must be 29)")
assert prod_count == 29, f"Production row count changed! Expected 29, got {prod_count}"

success = delivered_1 >= total_stops_1 and delivered_2 >= total_stops_2
if success:
    print(f"\n  ✓ ALL ACCEPTANCE CRITERIA MET")
else:
    print(f"\n  ✗ SOME CRITERIA NOT MET")
sys.exit(0 if success else 1)
