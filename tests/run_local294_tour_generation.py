#!/usr/bin/env python3
"""LOCAL-294: Generate one 8-stop Riviera tour to confirm delivery has not regressed
from LOCAL-290's 8/8 result.

Also checks the D141 cleanup rule and reports the tour content.
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

import psycopg2 as _psycopg2_check  # verify import before proceeding
del _psycopg2_check

# ─── D141: Capture audio_tours BEFORE ─────────────────────────────────────────
import psycopg2
_db_url = os.environ['DATABASE_URL']
_conn_pre = psycopg2.connect(_db_url)
_cur_pre = _conn_pre.cursor()
_cur_pre.execute("SELECT id FROM audio_tours")
_pre_ids = {r[0] for r in _cur_pre.fetchall()}
_cur_pre.close()
_conn_pre.close()

# Protected IDs (Nice list from task spec)
_protected_ids = {1, 12, 14, 17, 24, 29, 152}
print(f"Protected IDs: {_protected_ids}")
print(f"Audio tours before: {len(_pre_ids)} rows")

from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)

# ─── Generate the tour ────────────────────────────────────────────────────────
location = "French Riviera walking tour along the coast, France"
tour_type = "walking"
total_stops = 8
output_file = os.path.join(TOURS_DIR, "LOCAL294_8stop_riviera.txt")

print(f"\n{'=' * 70}")
print(f"GENERATING: 8-stop Riviera walking tour")
print(f"  Location: {location}")
print(f"  Type: {tour_type}, Stops: {total_stops}")
print(f"{'=' * 70}\n")

start_time = time.time()
result = generate_tour_text(
    location=location,
    tour_type=tour_type,
    output_file=output_file,
    total_stops=total_stops,
    persona=None,
)
elapsed = time.time() - start_time

if not result or not result[0]:
    print(f"\n  *** GENERATION FAILED (returned None) after {elapsed:.1f}s ***")
    sys.exit(1)

tour_text = result[0]
print(f"\n  Generated in {elapsed:.1f}s")

# Count stops in generated tour
stop_pattern = re.compile(r'^(?:Stop\s*\d+|#{1,3}\s*Stop\s*\d+)', re.MULTILINE)
stop_count = len(stop_pattern.findall(tour_text))
# Alternative: count "Orientation:" lines which mark stop boundaries
orientation_count = len(re.findall(r'^Orientation:', tour_text, re.MULTILINE))
delivered = max(stop_count, orientation_count)

print(f"\n  DELIVERY: {delivered}/{total_stops} stops")
if delivered >= total_stops:
    print(f"  ✓ No regression from LOCAL-290's 8/8")
else:
    print(f"  ✗ REGRESSION — expected {total_stops}, got {delivered}")

# ─── Write tour file to destination ──────────────────────────────────────────
with open(output_file, 'w') as f:
    f.write(tour_text)
print(f"\n  Tour written to: {output_file} ({len(tour_text)} bytes)")

# ─── D141: Cleanup ───────────────────────────────────────────────────────────
_conn_post = psycopg2.connect(_db_url)
_cur_post = _conn_post.cursor()
_cur_post.execute("SELECT id, is_test FROM audio_tours")
_post_rows = {r[0]: r[1] for r in _cur_post.fetchall()}
_new_ids = set(_post_rows.keys()) - _pre_ids

print(f"\n  Audio tours after: {len(_post_rows)} rows")
print(f"  New rows created: {sorted(_new_ids)}")

# Delete only test rows we created
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
_remaining_protected = {r[0] for r in _cur_post.fetchall()}
_cur_post.close()
_conn_post.close()

print(f"  Deleted {len(deleted)} test rows: {sorted(deleted)}")
print(f"  Protected IDs verified: {sorted(_remaining_protected)}")
assert _remaining_protected == _protected_ids, (
    f"Protected IDs damaged! Missing: {_protected_ids - _remaining_protected}"
)

# ─── D161: Read the tour as prose ─────────────────────────────────────────────
print(f"\n{'─' * 70}")
print("TOUR CONTENT (first 2000 chars):")
print(f"{'─' * 70}")
print(tour_text[:2000])
if len(tour_text) > 2000:
    print(f"\n  ... ({len(tour_text)} total chars)")

print(f"\n{'═' * 70}")
print(f"RESULT: {'PASS' if delivered >= total_stops else 'FAIL'}")
print(f"  Stops: {delivered}/{total_stops}")
print(f"  Time: {elapsed:.1f}s")
print(f"  File: {output_file}")
print(f"{'═' * 70}")

if delivered < total_stops:
    sys.exit(1)
