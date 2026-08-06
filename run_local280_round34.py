#!/usr/bin/env python3
"""ROUND34: LOCAL-280 closing recap — 2-stop and 8-stop Riviera tours.

Generates both a 2-stop and 8-stop French Riviera cycling tour to verify
the closing recap replaces the thank-you, states scale, and names real
content from the intrigue ranking.

All gates ON. $1.00 ceiling total (both tours combined).
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
CEILING = 1.00  # Combined ceiling for both tours
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND34: LOCAL-280 CLOSING RECAP — 2-STOP + 8-STOP RIVIERA")
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
# COMMON SETUP
# ======================================================================
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

print(f"\n  FLAGS SET:")
print(f"    STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"    STORIED_MODE:             {os.environ.get('STORIED_MODE')}")
print(f"    All DISABLE flags cleared")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

# Destination for plain-text files
DEST_DIR = "/Users/micha/Audioura/tours"
os.makedirs(DEST_DIR, exist_ok=True)

total_cost = 0.0
results = {}


def run_generation(label, requested_stops, output_filename):
    """Generate a tour, measure, and return results."""
    global total_cost

    print(f"\n{'='*70}")
    print(f"GENERATING: {label} ({requested_stops} stops)")
    print(f"{'='*70}")

    output_file = os.path.join(PROJECT_ROOT, "tours", output_filename)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    tour_text = None
    gen_actual_cost = 0
    gen_actual_tokens = 0
    elapsed = 0
    gen_log = ""

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

    for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
        print(f"\n  --- Generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")

        _orig_stdout = sys.stdout
        _captured = io.StringIO()
        sys.stdout = TeeWriter(_orig_stdout, _captured)

        start_time = time.time()
        try:
            result = generate_tour_text(
                location="French Riviera cycling tour, France",
                tour_type="biking",
                output_file=output_file,
                total_stops=requested_stops,
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
        print(f"  Stops generated: {len(stops_generated)} (requested: {requested_stops})")
        for stop in stops_generated:
            print(f"    - {stop['title']}")

        if len(stops_generated) >= requested_stops:
            print(f"  ✓ Stop count OK ({len(stops_generated)} >= {requested_stops})")
            break
        else:
            print(f"  ✗ Only {len(stops_generated)} stop(s) — retrying")
            if gen_attempt == MAX_GEN_ATTEMPTS:
                print(f"  WARNING: Using {len(stops_generated)}-stop output")
                break

    print(f"\n  Generation time: {elapsed:.1f}s")
    print(f"  Cost: ${gen_actual_cost:.4f} ({gen_actual_tokens} tokens)")
    total_cost += gen_actual_cost

    assert total_cost <= CEILING, f"Combined cost ${total_cost:.4f} exceeds ceiling ${CEILING}"

    # Copy to destination
    dest_file = os.path.join(DEST_DIR, output_filename)
    shutil.copy2(output_file, dest_file)
    print(f"  Copied to: {dest_file}")

    # Extract closing verbatim
    closing_text = ""
    if tour_text:
        # The closing is the last paragraph(s) after the last "Directions:" line
        # or the last section of the last stop
        parts = tour_text.split('\n\n')
        # Find the last non-empty part
        for p in reversed(parts):
            if p.strip() and len(p.strip()) > 20:
                closing_text = p.strip()
                break

    return {
        'tour_text': tour_text,
        'gen_log': gen_log,
        'cost': gen_actual_cost,
        'tokens': gen_actual_tokens,
        'elapsed': elapsed,
        'stops': parse_tour_stops(tour_text) if tour_text else [],
        'closing': closing_text,
        'output_file': output_file,
    }


# ======================================================================
# STEP 1: 2-STOP TOUR
# ======================================================================
results['2stop'] = run_generation("2-stop Riviera", 2, "LOCAL280_riviera_2stop_round34.txt")

# ======================================================================
# STEP 2: 8-STOP TOUR
# ======================================================================
results['8stop'] = run_generation("8-stop Riviera", 8, "LOCAL280_riviera_8stop_round34.txt")

# ======================================================================
# STEP 3: VERIFY CLOSING RECAP
# ======================================================================
print(f"\n{'='*70}")
print("STEP 3: CLOSING RECAP VERIFICATION")
print(f"{'='*70}")

from derepetition_guard import scan_for_repetition

for label, r in results.items():
    print(f"\n  --- {label.upper()} ---")
    tour_text = r['tour_text']
    if not tour_text:
        print(f"  ✗ No tour text generated")
        continue

    # Find the closing section (after the last stop's description)
    stops = r['stops']
    words_total = len(tour_text.split())
    print(f"  Words: {words_total}")
    print(f"  Stops: {len(stops)}")

    # Extract closing: everything after the last directions or last stop header
    closing_section = r['closing']
    print(f"\n  CLOSING VERBATIM:")
    print(f"  ─────────────────")
    for line in closing_section.split('\n'):
        print(f"    {line}")
    print(f"  ─────────────────")

    # Count sentences in closing
    closing_sentences = re.split(r'(?<=[.!?])\s+', closing_section.strip())
    closing_sentences = [s for s in closing_sentences if s.strip()]
    print(f"  Sentence count: {len(closing_sentences)}")

    # Check: no thank-you
    thank_patterns = [
        r'thank\s+you\s+for\s+taking',
        r'we\s+hope\s+you\s+enjoyed',
        r'leave\s+inspired',
        r'thank\s+you\s+for\s+joining',
    ]
    for tp in thank_patterns:
        if re.search(tp, closing_section, re.IGNORECASE):
            print(f"  ✗ FAIL: Thank-you pattern found: {tp}")
        else:
            print(f"  ✓ No '{tp}'")

    # Check: scale stated (stop count + km)
    if re.search(r"That's\s+\d+\s+stop", closing_section):
        print(f"  ✓ Scale (stop count) stated")
    else:
        print(f"  ✗ WARN: Scale not stated in closing")

    if re.search(r'\d+\s+kilomet', closing_section):
        print(f"  ✓ Distance in km stated")
    else:
        print(f"  ✗ WARN: Distance not in closing")

    # Check: Treats wording
    if 'Treat' in closing_section:
        if 'whether there are' in closing_section:
            print(f"  ✓ Treats wording correct ('whether there are')")
        elif 'for coupons' in closing_section or 'there are savings' in closing_section:
            print(f"  ✗ FAIL: Treats promises savings exist")
        else:
            print(f"  ? Treats mentioned but wording unclear")

    # Check: derepetition guard
    preaching_matches = scan_for_repetition(closing_section)
    if preaching_matches:
        print(f"  ✗ FAIL: Preaching detected in closing: {preaching_matches}")
    else:
        print(f"  ✓ No preaching in closing")

    # D177 verification: check that recap facts appear in delivered stops
    # Extract recap sentence (first sentence of closing if it starts with "That's")
    if closing_sentences and closing_sentences[0].startswith("That's"):
        recap_sent = closing_sentences[0]
        print(f"\n  RECAP SENTENCE: \"{recap_sent}\"")

        # Find fact fragments in the recap and verify against stop descriptions
        # The recap contains condensed clauses from stops — check each stop mentioned
        for stop in stops:
            stop_name = stop['title']
            if stop_name.lower() in recap_sent.lower():
                print(f"    Stop '{stop_name}' referenced in recap")


# ======================================================================
# STEP 4: CLEANUP (D141)
# ======================================================================
print(f"\n{'='*70}")
print("STEP 4: CLEANUP (D141)")
print(f"{'='*70}")

conn = get_connection()
cur = conn.cursor()

# Find rows created by this run (is_test = true, created recently)
cur.execute("""
    SELECT id, tour_name, is_test, created_at
    FROM audio_tours
    WHERE created_at > NOW() - INTERVAL '30 minutes'
    ORDER BY created_at DESC
""")
recent_rows = cur.fetchall()

deleted_ids = []
for row_id, tour_name, is_test, created_at in recent_rows:
    # D141: only delete if is_test = true
    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (row_id,))
    check = cur.fetchone()
    if check and check[0] is True:
        cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = true", (row_id,))
        deleted_ids.append(row_id)
        print(f"  Deleted: id={row_id} (is_test=true) '{tour_name}'")
    elif check and check[0] is False:
        print(f"  KEPT: id={row_id} (is_test=false) '{tour_name}' — NOT DELETING")

conn.commit()

# Verify Nice list preserved
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"\n  Nice list after: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list DAMAGED: {nice_after}"
print(f"  ✓ Nice list preserved")

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours count: before={count_before}, after={count_after}")
conn.close()

# ======================================================================
# STEP 5: SUMMARY
# ======================================================================
print(f"\n{'='*70}")
print("ROUND34 SUMMARY — LOCAL-280 CLOSING RECAP")
print(f"{'='*70}")

print(f"\n  Total cost: ${total_cost:.4f} (ceiling: ${CEILING})")
print(f"  2-stop: ${results['2stop']['cost']:.4f} / {results['2stop']['elapsed']:.1f}s")
print(f"  8-stop: ${results['8stop']['cost']:.4f} / {results['8stop']['elapsed']:.1f}s")
print(f"\n  Baselines:")
print(f"    2-stop: $0.0185–$0.0206 / 43s")
print(f"    8-stop: $0.0587 / ~118s")
print(f"\n  Files:")
print(f"    {results['2stop']['output_file']}")
print(f"    {results['8stop']['output_file']}")
print(f"    Copied to: {DEST_DIR}/")
print(f"\n  Deleted {len(deleted_ids)} test rows: {deleted_ids}")
print(f"  Nice list intact: {EXPECTED_NICE}")
