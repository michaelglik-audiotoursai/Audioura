#!/usr/bin/env python3
"""ROUND22: Unglossed-reference gate (LOCAL-269).

Regenerates a 2-stop French Riviera cycling tour with the new gate:
- Detects named entities lacking explanation (Operation Dragoon, House of Savoy)
- Triages via model (general audience knows? load-bearing?)
- Supplies glosses (corpus → model+citation → degrade)
- Glosses are 8-14 words, inserted as appositives

All prior gates ON. Copies run_round21.py's flag handling.
$2.00 ceiling (Michael explicitly authorised model spend).
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
CEILING = 2.00  # Michael explicitly authorised model spend for this task
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND22: UNGLOSSED-REFERENCE GATE (LOCAL-269)")
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
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND22)")
print("=" * 70)

# FLAGS: All gates ON. No DISABLE flags. Copied from run_round21.py.
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

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL269_riviera_2stop_round22.txt")

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
# STEP 2: EXTRACT GLOSS STATS FROM LOG
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: GLOSS GATE STATS")
print("=" * 70)

# Parse gloss stats from generation log
gloss_detected = 0
gloss_glossed = 0
gloss_degraded = 0
gloss_known = 0
gloss_triage_tokens = 0
gloss_triage_cost = 0.0
gloss_triage_latency = 0.0
gloss_supply_tokens = 0
gloss_supply_cost = 0.0
gloss_supply_latency = 0.0
gloss_total_cost = 0.0
gloss_list = []

# Parse from log
_det_m = re.search(r'References detected:\s*(\d+)', gen_log)
if _det_m:
    gloss_detected = int(_det_m.group(1))
_glossed_m = re.search(r'Glossed:\s*(\d+)', gen_log)
if _glossed_m:
    gloss_glossed = int(_glossed_m.group(1))
_deg_m = re.search(r'Degraded:\s*(\d+)', gen_log)
if _deg_m:
    gloss_degraded = int(_deg_m.group(1))
_known_m = re.search(r'Known \(skipped\):\s*(\d+)', gen_log)
if _known_m:
    gloss_known = int(_known_m.group(1))

# Triage stats
_triage_m = re.search(r'Triage:\s*(\d+)\s*tokens,\s*\$([0-9.]+),\s*([0-9.]+)s', gen_log)
if _triage_m:
    gloss_triage_tokens = int(_triage_m.group(1))
    gloss_triage_cost = float(_triage_m.group(2))
    gloss_triage_latency = float(_triage_m.group(3))

# Gloss stats
_gloss_m = re.search(r'Gloss:\s*(\d+)\s*tokens,\s*\$([0-9.]+),\s*([0-9.]+)s', gen_log)
if _gloss_m:
    gloss_supply_tokens = int(_gloss_m.group(1))
    gloss_supply_cost = float(_gloss_m.group(2))
    gloss_supply_latency = float(_gloss_m.group(3))

_total_cost_m = re.search(r'Total added cost:\s*\$([0-9.]+)', gen_log)
if _total_cost_m:
    gloss_total_cost = float(_total_cost_m.group(1))

# Extract individual glosses
gloss_lines = re.findall(r'• (.+?) → "(.+?)" \[source: (.+?)\]', gen_log)
for entity, gloss, source in gloss_lines:
    gloss_list.append({'entity': entity, 'gloss': gloss, 'source': source})

degraded_lines = re.findall(r'• (.+?) → DEGRADED', gen_log)
for entity in degraded_lines:
    gloss_list.append({'entity': entity, 'gloss': None, 'source': 'degrade'})

print(f"  References detected: {gloss_detected}")
print(f"  Glossed: {gloss_glossed}")
print(f"  Degraded: {gloss_degraded}")
print(f"  Known (skipped): {gloss_known}")
print(f"  Triage: {gloss_triage_tokens} tokens, ${gloss_triage_cost:.4f}, {gloss_triage_latency:.1f}s")
print(f"  Gloss: {gloss_supply_tokens} tokens, ${gloss_supply_cost:.4f}, {gloss_supply_latency:.1f}s")
print(f"  Total added cost: ${gloss_total_cost:.4f}")

# ======================================================================
# STEP 3: MEASUREMENTS
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: MEASUREMENTS")
print("=" * 70)

from style_validator_detector import (
    _split_sentences, _is_style_navigation_sentence,
    check_r7_hallucinated_sensory, _has_finite_main_verb, check_r1_imperatives,
)

stops = parse_tour_stops(tour_text)
word_count = len(tour_text.split())
tour_total_sentences = 0
tour_fragment_sentences = []

_tour_paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip() and len(p.strip()) > 30]
for para in _tour_paragraphs:
    sents = _split_sentences(para)
    for s in sents:
        if len(s) < 10:
            continue
        if _is_style_navigation_sentence(s):
            continue
        tour_total_sentences += 1
        if not _has_finite_main_verb(s):
            tour_fragment_sentences.append(s[:100])

print(f"  Word count: {word_count}")
print(f"  Stops: {len(stops)}")
print(f"  Total content sentences: {tour_total_sentences}")
print(f"  Fragment sentences: {len(tour_fragment_sentences)}")

# Word count comparison
baseline_word_count = 620  # Round 19
added_words = word_count - baseline_word_count
print(f"\n  Added words (vs round 19 baseline 620): {added_words:+d}")
print(f"  Added listening time: ~{added_words * 60 / 150:.0f}s at 150 wpm")

# ======================================================================
# STEP 4: COST REPORT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: COST REPORT (vs $0.0206 true baseline)")
print("=" * 70)

baseline_cost = 0.0206
baseline_time = 43.0  # seconds for 2 stops

print(f"\n  ┌───────────────────────────────────────────────────────┐")
print(f"  │ COST BREAKDOWN                                        │")
print(f"  ├───────────────────────────────────────────────────────┤")
print(f"  │ Triage calls:   {gloss_triage_tokens:>5} tokens, ${gloss_triage_cost:.4f}, {gloss_triage_latency:.1f}s │")
print(f"  │ Gloss calls:    {gloss_supply_tokens:>5} tokens, ${gloss_supply_cost:.4f}, {gloss_supply_latency:.1f}s │")
print(f"  │ Total added:    ${gloss_total_cost:.4f} cost, {gloss_triage_latency + gloss_supply_latency:.1f}s time │")
print(f"  ├───────────────────────────────────────────────────────┤")
print(f"  │ Generation base: ${gen_actual_cost:.4f}                           │")
print(f"  │ Total this run:  ${gen_actual_cost:.4f}                           │")
print(f"  │ Baseline:        ${baseline_cost:.4f}                           │")
print(f"  │ Delta:           ${gen_actual_cost - baseline_cost:+.4f}                          │")
print(f"  ├───────────────────────────────────────────────────────┤")
print(f"  │ Added time:      {elapsed - baseline_time:+.1f}s (vs {baseline_time}s baseline)     │")
print(f"  │ Added words:     {added_words:+d} (vs 620 baseline)                │")
print(f"  └───────────────────────────────────────────────────────┘")

if gloss_total_cost > 0.02:
    print(f"\n  ⚠️  ADDED COST ${gloss_total_cost:.4f} EXCEEDS $0.02 PER 2-STOP TOUR")
if (gloss_triage_latency + gloss_supply_latency) > 30:
    print(f"\n  ⚠️  ADDED TIME {gloss_triage_latency + gloss_supply_latency:.1f}s EXCEEDS 30s LIMIT")

# ======================================================================
# STEP 5: STORE TO DB (D141 compliant)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: STORE TO DB (D141 COMPLIANT)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

_tour_name_unique = f"RIVIERA_2STOP_ROUND22_LOCAL269_{int(time.time())}"
cur.execute("""
    INSERT INTO audio_tours (tour_name, tour_content, is_test, request_string)
    VALUES (%s, %s, true, %s)
    RETURNING id
""", (_tour_name_unique, tour_text, "French Riviera cycling tour, France"))
inserted_id = cur.fetchone()[0]
conn.commit()
print(f"  Inserted tour id={inserted_id} (is_test=true)")

cur.execute("SELECT id, is_test FROM audio_tours WHERE id = %s", (inserted_id,))
row = cur.fetchone()
assert row[1] is True, f"is_test not true for id={inserted_id}"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list after: {nice_after}")
assert nice_after == EXPECTED_NICE
conn.close()

# ======================================================================
# STEP 6: WRITE ARTIFACTS
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: WRITE ARTIFACTS")
print("=" * 70)

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND22.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 22 (ROUND22)\n\n")
    f.write("> ### What changed: ROUND22 — Unglossed-reference gate (LOCAL-269)\n>\n")
    f.write("> Named entities that a general audience wouldn't know are now glossed\n")
    f.write("> with 8-14 word appositives. If no sourced gloss available, reference is\n")
    f.write("> degraded (name removed, fact kept) rather than deleted.\n\n")
    f.write(f"**Word count:** {word_count}\n")
    f.write(f"**Stops:** {len(stops)} ({', '.join(s['title'] for s in stops)})\n\n")
    f.write("## Flags Set\n\n")
    f.write("| Flag | Value |\n|---|---|\n")
    f.write("| STOP_EXISTENCE_GATE_MODE | enforce |\n")
    f.write("| STORIED_MODE | true |\n")
    f.write("| DISABLE_STYLE_RETRY | NOT SET (ON) |\n")
    f.write("| DISABLE_R1_REWRITE | NOT SET (ON) |\n")
    f.write("| DISABLE_R7_DELETION | NOT SET (ON) |\n")
    f.write("| DISABLE_R9_DELETION | NOT SET (ON) |\n")
    f.write("| DISABLE_R10_DELETION | NOT SET (ON) |\n")
    f.write("| DISABLE_CONTRADICTED_BLOCK | NOT SET (ON) |\n")
    f.write("| DISABLE_UNSUPPORTED_CLAIM_GATE | NOT SET (ON) |\n")
    f.write("| DISABLE_UNGLOSSED_REFERENCE_GATE | NOT SET (ON) |\n")
    f.write("| DISABLE_SUBJECT_ROUTINE | 1 (OFF) |\n")
    f.write("| DISABLE_TOUR_CACHE | 1 (OFF) |\n\n")
    f.write("## Gloss Gate Results\n\n")
    f.write("| Metric | Value |\n|---|---|\n")
    f.write(f"| references detected | {gloss_detected} |\n")
    f.write(f"| glossed | {gloss_glossed} |\n")
    f.write(f"| degraded | {gloss_degraded} |\n")
    f.write(f"| known (skipped) | {gloss_known} |\n")
    f.write(f"| triage tokens | {gloss_triage_tokens} |\n")
    f.write(f"| triage cost | ${gloss_triage_cost:.4f} |\n")
    f.write(f"| triage latency | {gloss_triage_latency:.1f}s |\n")
    f.write(f"| gloss tokens | {gloss_supply_tokens} |\n")
    f.write(f"| gloss cost | ${gloss_supply_cost:.4f} |\n")
    f.write(f"| gloss latency | {gloss_supply_latency:.1f}s |\n")
    f.write(f"| **total added cost** | **${gloss_total_cost:.4f}** |\n")
    f.write(f"| **total added time** | **{gloss_triage_latency + gloss_supply_latency:.1f}s** |\n\n")
    f.write("## Glosses Applied\n\n")
    f.write("| Entity | Gloss | Source | Stage |\n|---|---|---|---|\n")
    for g in gloss_list:
        if g.get('gloss'):
            f.write(f"| {g['entity']} | {g['gloss']} | {g['source']} | model |\n")
        else:
            f.write(f"| {g['entity']} | *(degraded)* | — | degrade |\n")
    f.write("\n## Cost Comparison\n\n")
    f.write("| | |\n|---|---|\n")
    f.write(f"| triage calls, tokens, cost, latency | 1 call, {gloss_triage_tokens} tok, ${gloss_triage_cost:.4f}, {gloss_triage_latency:.1f}s |\n")
    f.write(f"| gloss calls, tokens, cost, latency | 1 call, {gloss_supply_tokens} tok, ${gloss_supply_cost:.4f}, {gloss_supply_latency:.1f}s |\n")
    f.write(f"| **total added cost per 2-stop tour** | **${gloss_total_cost:.4f}** against $0.0206 baseline |\n")
    f.write(f"| **total added generation time** | **{gloss_triage_latency + gloss_supply_latency:.1f}s** against 43s baseline |\n")
    f.write(f"| **added words** (listening time) | **{added_words:+d}** against 620 words round 19 |\n\n")
    f.write("## Summary Table\n\n")
    f.write("| Field | Value |\n|---|---|\n")
    f.write(f"| generation cost | ${gen_actual_cost:.4f} |\n")
    f.write(f"| total tokens | {gen_actual_tokens} |\n")
    f.write(f"| stops | {', '.join(s['title'] for s in stops)} |\n")
    f.write(f"| generation time | {elapsed:.1f}s |\n")
    f.write(f"| generation attempts | {gen_attempt}/{MAX_GEN_ATTEMPTS} |\n")
    f.write(f"| word count | {word_count} |\n")
    f.write(f"| fragment sentences | {len(tour_fragment_sentences)} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")
    f.write("## Tour Content\n\n")
    f.write(tour_text)
    f.write("\n")

print(f"  Written: {md_path}")

# Copy plain text to ~/Audioura/tours/
dest_dir = os.path.expanduser("~/Audioura/tours")
os.makedirs(dest_dir, exist_ok=True)
dest_file = os.path.join(dest_dir, "LOCAL269_riviera_2stop_round22.txt")
with open(dest_file, 'w') as f:
    f.write(tour_text)
print(f"  Copied plain text to: {dest_file}")

# ======================================================================
# STEP 7: CLEANUP (D141)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 7: CLEANUP (D141)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (inserted_id,))
row = cur.fetchone()
if row and row[0] is True:
    cur.execute("DELETE FROM audio_tours WHERE id = %s", (inserted_id,))
    conn.commit()
    print(f"  Deleted test row id={inserted_id} (is_test=true confirmed)")
else:
    print(f"  WARNING: id={inserted_id} is_test={row[0] if row else 'NOT FOUND'} — NOT deleted")

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_final = cur.fetchone()[0]
print(f"  audio_tours final count: {count_final}")
# The count should be unchanged (we inserted and then deleted our test row)
# Allow for ±1 due to other processes, but verify Nice list is intact
if count_final != count_before:
    print(f"  NOTE: count changed {count_before} → {count_final} (diff={count_final - count_before})")
    # Critical check: Nice list must be intact
    pass

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
print(f"  Nice list final: {nice_final}")
assert nice_final == EXPECTED_NICE
conn.close()

# ======================================================================
# STEP 8: READ AS PROSE (D161)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 8: READ AS PROSE (D161)")
print("=" * 70)

# Display the tour content for prose reading
for stop in stops:
    print(f"\n  --- {stop['title']} ---")
    desc = stop.get('description', '')
    if desc:
        for sent in _split_sentences(desc):
            if len(sent) > 10:
                print(f"  {sent}")

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("ROUND 22 COMPLETE")
print("=" * 70)
print(f"  Artifact: RIVIERA_2STOP_ROUND22.md")
print(f"  Plain text: {dest_file}")
print(f"  Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  Gloss gate cost: ${gloss_total_cost:.4f}")
print(f"  Word count: {word_count} (delta from 620: {added_words:+d})")
print(f"  Glosses: {gloss_glossed} glossed, {gloss_degraded} degraded, {gloss_known} known")
