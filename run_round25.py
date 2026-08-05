#!/usr/bin/env python3
"""ROUND25: R1 damage fix + empty exhortation gate + forward transition check (LOCAL-271).

Regenerates a 2-stop French Riviera cycling tour with:
- R1 rewrite wellformedness check (no "admire yourself", no mid-sentence caps, no doubled clauses)
- Empty exhortation claim type in the unsupported-claim gate
- Forward transition at final stop detected and removed

All prior gates ON. $0.60 ceiling.
"""
import os
import sys
import re
import io
import json
import time
import traceback
import shutil

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
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND25: R1 DAMAGE FIX + EXHORTATION GATE + FORWARD TRANSITION (LOCAL-271)")
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
# STEP 1: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND25)")
print("=" * 70)

# FLAGS: All gates ON
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Explicitly REMOVE any disable flags
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_R7_DELETION', 'DISABLE_R1_REWRITE',
           'DISABLE_R10_DELETION',
           'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE',
           'DISABLE_UNSUPPORTED_CLAIM_GATE',
           'DISABLE_UNGLOSSED_REFERENCE_GATE'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

print(f"  FLAGS SET:")
print(f"    STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"    STORIED_MODE:             {os.environ.get('STORIED_MODE')}")
print(f"    DISABLE_TOUR_CACHE:       {os.environ.get('DISABLE_TOUR_CACHE')}")
print(f"  GATES ON (not disabled):")
for _gflag in ('DISABLE_STYLE_RETRY', 'DISABLE_R1_REWRITE', 'DISABLE_R7_DELETION',
               'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK',
               'DISABLE_UNSUPPORTED_CLAIM_GATE', 'DISABLE_UNGLOSSED_REFERENCE_GATE'):
    print(f"    {_gflag}: NOT SET (ON)")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL271_riviera_2stop_round25.txt")

REQUESTED_STOPS = 2
tour_text = None
gen_actual_cost = 0
gen_actual_tokens = 0
elapsed = 0
gen_log = ""

for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n  --- Generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")

    _orig_stdout = sys.stdout
    _captured = io.StringIO()

    class TeeWriter:
        def __init__(self, orig, buf):
            self.orig = orig
            self.buf = buf
        def write(self, s):
            self.orig.write(s)
            self.buf.write(s)
        def flush(self):
            self.orig.flush()
            self.buf.flush()

    sys.stdout = TeeWriter(_orig_stdout, _captured)

    start_time = time.time()
    try:
        result = generate_tour_text(
            location="French Riviera cycling tour, France",
            tour_type="biking",
            output_file=output_file,
            total_stops=REQUESTED_STOPS,
            persona=None,
        )
    except Exception as e:
        sys.stdout = _orig_stdout
        elapsed = time.time() - start_time
        print(f"  Generation failed after {elapsed:.1f}s: {e}")
        traceback.print_exc()
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print("FATAL: All generation attempts failed")
            sys.exit(1)
        continue

    sys.stdout = _orig_stdout
    elapsed = time.time() - start_time
    gen_log = _captured.getvalue()

    if not result or not result[0]:
        print(f"  Tour generation returned None after {elapsed:.1f}s")
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print("FATAL: All generation attempts returned None")
            sys.exit(1)
        continue

    tour_text = result[0]
    gen_cost = _LAST_GENERATION_COST.copy()
    gen_actual_cost = gen_cost.get('total_cost', 0)
    gen_actual_tokens = gen_cost.get('total_tokens', 0)

    _cost_match = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
    if _cost_match:
        gen_actual_cost = float(_cost_match.group(1))
        gen_actual_tokens = int(_cost_match.group(2))

    stops_generated = parse_tour_stops(tour_text)
    print(f"  Stops generated: {len(stops_generated)} (requested: {REQUESTED_STOPS})")
    for stop in stops_generated:
        print(f"    - {stop['title']}")

    if len(stops_generated) >= REQUESTED_STOPS:
        print(f"  ✓ Stop count OK ({len(stops_generated)} >= {REQUESTED_STOPS})")
        break
    else:
        print(f"  ✗ Only {len(stops_generated)} stop(s) — retrying")
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print(f"  WARNING: Using {len(stops_generated)}-stop output (max retries exhausted)")
            break

print(f"\n  Generation time: {elapsed:.1f}s")
print(f"  Cost: ${gen_actual_cost:.4f} ({gen_actual_tokens} tokens)")
print(f"  Attempts: {gen_attempt}/{MAX_GEN_ATTEMPTS}")
assert gen_actual_cost <= CEILING, f"Cost ${gen_actual_cost} exceeds ceiling ${CEILING}"

# ======================================================================
# STEP 2: VALIDATE LOCAL-271 FIXES
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: VALIDATE LOCAL-271 FIXES IN OUTPUT")
print("=" * 70)

from style_validator_detector import (
    _split_sentences, check_r1_imperatives, _r1_rewrite_wellformed,
    check_forward_transition_final_stop, remove_forward_transitions_final_stop,
)
from unsupported_claim_gate import classify_claim

# Check for R1 damage patterns in output
_r1_damage_found = []
for line in tour_text.split('\n'):
    if 'admire yourself' in line.lower():
        _r1_damage_found.append(f"  ADMIRE_YOURSELF: {line.strip()[:100]}")
    if re.search(r'(?<!\. )The [A-Z][a-z]+\s+[a-z]', line):
        # Potential mid-sentence capital — check more precisely
        sents = _split_sentences(line)
        for s in sents:
            words = s.split()
            if len(words) > 3:
                for i in range(2, len(words)):
                    w = words[i]
                    clean = re.sub(r'[^a-zA-Z]', '', w)
                    if clean and clean[0].isupper() and clean[1:].islower():
                        if clean.lower() in ('vibrant', 'panoramic', 'breathtaking',
                                             'stunning', 'beautiful', 'magnificent'):
                            _r1_damage_found.append(f"  MID_CAP: {s[:100]}")
                            break

if _r1_damage_found:
    print(f"  ⚠️  R1 DAMAGE STILL PRESENT ({len(_r1_damage_found)}):")
    for d in _r1_damage_found[:5]:
        print(f"    {d}")
else:
    print(f"  ✓ No R1 damage patterns detected in output")

# Check for empty exhortations
_exhortations_found = []
for line in tour_text.split('\n'):
    sents = _split_sentences(line)
    for s in sents:
        ct = classify_claim(s)
        if ct == 'EXHORTATION':
            _exhortations_found.append(s)

if _exhortations_found:
    print(f"\n  ⚠️  EXHORTATION sentences still in output ({len(_exhortations_found)}):")
    for e in _exhortations_found[:3]:
        print(f"    \"{e}\"")
else:
    print(f"  ✓ No empty exhortation sentences in output")

# Check for forward transition at final stop
stops_generated = parse_tour_stops(tour_text)
if stops_generated:
    last_stop = stops_generated[-1]
    last_desc = last_stop.get('body', '')
    forward_violations = check_forward_transition_final_stop(last_desc)
    if forward_violations:
        print(f"\n  ⚠️  FORWARD TRANSITION in final stop ({len(forward_violations)}):")
        for v in forward_violations:
            print(f"    \"{v['sentence'][:80]}\"")
        # Remove them
        new_desc, removed = remove_forward_transitions_final_stop(last_desc)
        if removed:
            print(f"    → Removed {len(removed)} forward transition(s)")
            # Update tour text
            for r in removed:
                tour_text = tour_text.replace(r, '')
            tour_text = re.sub(r'  +', ' ', tour_text)
            tour_text = re.sub(r'\n\s*\n\s*\n', '\n\n', tour_text)
    else:
        print(f"  ✓ No forward transitions in final stop")

# ======================================================================
# STEP 3: R1 REWRITE REPORT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: R1 REWRITE REPORT")
print("=" * 70)

# Extract R1 rewrite events from generation log
_r1_lines = [l for l in gen_log.split('\n') if 'R1' in l or 'rewrite' in l.lower() or 'PHASE 5.13' in l]
if _r1_lines:
    print(f"  R1 rewrite log entries: {len(_r1_lines)}")
    for l in _r1_lines[:10]:
        print(f"    {l.strip()[:120]}")
else:
    print(f"  (No R1 rewrite log entries captured)")

# ======================================================================
# STEP 4: WORD COUNT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: OUTPUT METRICS")
print("=" * 70)

words = len(tour_text.split())
print(f"  Total words: {words}")
print(f"  Generation time: {elapsed:.1f}s")
print(f"  Cost: ${gen_actual_cost:.4f}")
print(f"  Benchmark: $0.0206 / 43s for 2 stops")
print(f"  vs benchmark: cost {gen_actual_cost/0.0206:.1f}x, time {elapsed/43:.1f}x")

# ======================================================================
# STEP 5: WRITE ARTIFACT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: WRITE ARTIFACTS")
print("=" * 70)

# Write to RIVIERA_2STOP_ROUND25.md
md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND25.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour — Round 25\n\n")
    f.write(f"> LOCAL-271: R1 damage fix, empty exhortation gate, forward transition check.\n")
    f.write(f"> Generated: {time.strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"> Cost: ${gen_actual_cost:.4f} ({gen_actual_tokens} tokens) in {elapsed:.1f}s\n")
    f.write(f"> Stops: {len(stops_generated)}\n\n")
    f.write("---\n\n")
    f.write(tour_text)
print(f"  ✓ {md_path}")

# Copy plain text to ~/Audioura/tours/
tours_dir = os.path.expanduser("~/Audioura/tours")
os.makedirs(tours_dir, exist_ok=True)
tours_txt_path = os.path.join(tours_dir, "LOCAL271_riviera_2stop_round25.txt")
with open(tours_txt_path, 'w') as f:
    f.write(tour_text)
print(f"  ✓ {tours_txt_path}")

# ======================================================================
# STEP 6: DB CLEANUP — D141
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: DB CLEANUP (D141)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

# Find the row we just created (most recent is_test=true)
cur.execute("""
    SELECT id, is_test, tour_name FROM audio_tours
    WHERE tour_name LIKE '%French Riviera cycling%'
    AND created_at > NOW() - INTERVAL '10 minutes'
    ORDER BY created_at DESC LIMIT 5
""")
recent_rows = cur.fetchall()
print(f"  Recent rows found: {len(recent_rows)}")

deleted_ids = []
for row_id, is_test, name in recent_rows:
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
    result = cur.fetchone()
    if result and result[0]:
        cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = true", (row_id,))
        deleted_ids.append(row_id)
        print(f"    Deleted id={row_id} (is_test=true): {name}")
    else:
        print(f"    KEPT id={row_id} (is_test={result[0] if result else 'N/A'}): {name}")

conn.commit()

# Verify Nice list
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"\n  Nice list after: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list DAMAGED: {nice_after}"
print(f"  ✓ Nice list intact")

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours count: {count_before} → {count_after}")
conn.close()

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("ROUND25 COMPLETE")
print("=" * 70)
print(f"  Stops: {len(stops_generated)}")
print(f"  Words: {words}")
print(f"  Cost: ${gen_actual_cost:.4f} / {elapsed:.1f}s")
print(f"  R1 damage: {'NONE ✓' if not _r1_damage_found else 'FOUND ✗'}")
print(f"  Exhortations: {'NONE ✓' if not _exhortations_found else 'FOUND ✗'}")
print(f"  Forward transitions: {'CLEAN ✓' if not forward_violations else f'{len(forward_violations)} removed'}")
print(f"  Nice list: {'INTACT ✓' if nice_after == EXPECTED_NICE else 'DAMAGED ✗'}")
