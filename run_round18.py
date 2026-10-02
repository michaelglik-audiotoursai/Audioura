#!/usr/bin/env python3
"""ROUND18: Unsupported-claim gate (LOCAL-263).

Regenerates a 2-stop French Riviera cycling tour with the unsupported-claim
gate active. One gate, four claim types, one shared substantiation test.
D166: a claim survives only if something adjacent substantiates it.

Same shape: biking, 2 stops, French Riviera. Ceiling raised to $1.20 per task spec.
All in-pipeline gates ON. Subject routine ON. Unsupported-claim gate ON.
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
CEILING = 1.20  # Raised deliberately per task spec §Escalation
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND18: UNSUPPORTED-CLAIM GATE (LOCAL-263)")
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
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND18)")
print("=" * 70)

# FLAGS: All gates ON. Subject routine ON. Unsupported-claim gate ON.
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Explicitly REMOVE any disable flags
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_R7_DELETION', 'DISABLE_R1_REWRITE',
           'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION', 'DISABLE_STOP_EXISTENCE_GATE',
           'ENABLE_STOP_EXISTENCE_GATE', 'DISABLE_UNSUPPORTED_CLAIM_GATE',
           'DISABLE_R2_DELETION', 'DISABLE_R3_DELETION',
           'DISABLE_R4_DELETION', 'DISABLE_R8_DELETION'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

print(f"  FLAGS SET:")
print(f"    STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"    STORIED_MODE:             {os.environ.get('STORIED_MODE')}")
print(f"    DISABLE_SUBJECT_ROUTINE:  {os.environ.get('DISABLE_SUBJECT_ROUTINE', 'NOT SET (ON)')}")
print(f"    DISABLE_TOUR_CACHE:       {os.environ.get('DISABLE_TOUR_CACHE')}")
print(f"  GATES ON (not disabled):")
for _gflag in ('DISABLE_STYLE_RETRY', 'DISABLE_R1_REWRITE', 'DISABLE_R7_DELETION',
               'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK',
               'DISABLE_UNSUPPORTED_CLAIM_GATE'):
    print(f"    {_gflag}: NOT SET ({_gflag.replace('DISABLE_', '').replace('_', ' ').title()} ON)")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST
from style_validator_detector import (
    validate_paragraph, _split_sentences, check_r1_imperatives,
    _is_style_navigation_sentence, check_r7_hallucinated_sensory,
    check_r4_prescribed_feeling, check_r9_generic, check_r10_unfulfilled_promise,
    _has_finite_main_verb
)
from unsupported_claim_gate import classify_claim

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL263_riviera_2stop_round18.txt")

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
# STEP 2: MEASUREMENTS
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: MEASUREMENTS")
print("=" * 70)

stops = parse_tour_stops(tour_text)
tour_total_sentences = 0
tour_nav_sentences = 0
tour_r1_residual = 0
tour_r7_residual = 0
tour_r4_residual = 0
tour_r9_residual = 0
tour_r10_residual = 0
tour_fragment_sentences = []
tour_claim_gate_would_fire = 0

_tour_paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip() and len(p.strip()) > 30]
for para in _tour_paragraphs:
    sents = _split_sentences(para)
    for i, s in enumerate(sents):
        if len(s) < 10:
            continue
        if _is_style_navigation_sentence(s):
            tour_nav_sentences += 1
            continue
        tour_total_sentences += 1
        if check_r1_imperatives(s):
            tour_r1_residual += 1
        if check_r7_hallucinated_sensory(s):
            tour_r7_residual += 1
        if check_r4_prescribed_feeling(s):
            tour_r4_residual += 1
        if check_r9_generic(s):
            tour_r9_residual += 1
        r10_result = check_r10_unfulfilled_promise(sents, i)
        if r10_result:
            tour_r10_residual += 1
        if not _has_finite_main_verb(s):
            tour_fragment_sentences.append(s[:100])
        # Check claim gate classification
        ct = classify_claim(s)
        if ct is not None:
            tour_claim_gate_would_fire += 1

# Extract UCG stats from log
_ucg_removed_match = re.search(r'\[LOCAL-263\].*Sentences removed: (\d+)', gen_log)
_ucg_removed = int(_ucg_removed_match.group(1)) if _ucg_removed_match else 0
_ucg_kept_match = re.search(r'\[LOCAL-263\].*Sentences kept \(substantiated\): (\d+)', gen_log)
_ucg_kept = int(_ucg_kept_match.group(1)) if _ucg_kept_match else 0
_ucg_escalation_match = re.search(r'\[LOCAL-263\].*Escalation calls: (\d+)', gen_log)
_ucg_escalation = int(_ucg_escalation_match.group(1)) if _ucg_escalation_match else 0
_ucg_cost_match = re.search(r'\[LOCAL-263\].*Escalation cost: \$([0-9.]+)', gen_log)
_ucg_cost = float(_ucg_cost_match.group(1)) if _ucg_cost_match else 0.0
_ucg_rate_match = re.search(r'\[LOCAL-263\].*Deletion rate: ([0-9.]+)%', gen_log)
_ucg_rate = float(_ucg_rate_match.group(1)) if _ucg_rate_match else 0.0

# R1 rewrite stats
r1_match = re.search(r'\[LOCAL-255\] R1 summary: (\d+) rewritten, (\d+) deleted', gen_log)
r1_rewritten = int(r1_match.group(1)) if r1_match else 0
r1_deleted = int(r1_match.group(2)) if r1_match else 0

print(f"  Total content sentences: {tour_total_sentences}")
print(f"  Navigation sentences: {tour_nav_sentences}")
print(f"  R1 residual: {tour_r1_residual}")
print(f"  R4 residual: {tour_r4_residual}")
print(f"  R7 residual: {tour_r7_residual}")
print(f"  R9 residual: {tour_r9_residual}")
print(f"  R10 residual: {tour_r10_residual}")
print(f"  Fragment sentences: {len(tour_fragment_sentences)}")
print(f"  Claim gate removed: {_ucg_removed}")
print(f"  Claim gate kept (substantiated): {_ucg_kept}")
print(f"  Escalation calls: {_ucg_escalation}")
print(f"  Escalation cost: ${_ucg_cost:.4f}")

# ======================================================================
# STEP 3: FACT TALLY PER STOP
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: FACT TALLY PER STOP")
print("=" * 70)

fact_tallies = {}
for idx, stop in enumerate(stops):
    title = stop.get('title', 'Unknown')
    stop_marker_search = f"Stop {idx+1}: {title}"
    next_marker = f"Stop {idx+2}:" if idx + 1 < len(stops) else None

    start_idx = tour_text.find(stop_marker_search)
    if start_idx >= 0:
        end_idx = tour_text.find(next_marker, start_idx + len(stop_marker_search)) if next_marker else len(tour_text)
        if end_idx < 0:
            end_idx = len(tour_text)
        content = tour_text[start_idx:end_idx]
    else:
        content = ''

    sents = _split_sentences(content) if content else []
    fact_sents = []
    total_content_sents = 0
    for s in sents:
        if len(s) < 10:
            continue
        if _is_style_navigation_sentence(s):
            continue
        total_content_sents += 1
        has_date = bool(re.search(r'\b\d{3,4}\b', s))
        has_proper_noun = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', s))
        has_specific = bool(re.search(
            r'\b(?:founded|built|created|opened|established|published|painted|'
            r'wrote|composed|designed|constructed|renovated|completed|destroyed|'
            r'restored|visited|experimented|discovered|transformed|voted|seized|'
            r'fortified|winding|kilometers?)\b', s, re.IGNORECASE))
        if has_date or (has_proper_noun and has_specific):
            fact_sents.append(s[:100])

    fact_tallies[title] = len(fact_sents)
    print(f"\n  {title}:")
    print(f"    Content sentences: {total_content_sents}")
    print(f"    Facts: {len(fact_sents)}")
    for s in fact_sents[:8]:
        print(f"      • {s}")

# ======================================================================
# STEP 4: STORE TO DB (D141 COMPLIANT)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: STORE TO DB (D141 COMPLIANT)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

_tour_name_unique = f"RIVIERA_2STOP_ROUND18_LOCAL263_{int(time.time())}"
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
# STEP 5: WRITE ARTIFACT + COPY
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: WRITE RIVIERA_2STOP_ROUND18.md + tours/")
print("=" * 70)

word_count = len(tour_text.split())

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND18.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 18 (LOCAL-263)\n\n")
    f.write("> ### What changed: ROUND18 — Unsupported-claim gate (LOCAL-263)\n>\n")
    f.write("> One gate, four claim types (PROMISE, SENSORY, FEELING, QUALITY),\n")
    f.write("> one shared substantiation test. D166: a claim survives only if\n")
    f.write("> something adjacent substantiates it with a concrete payload.\n>\n")
    f.write("> Subsumes R4/R7/R9/R10 for the adjacency test. Old detectors\n")
    f.write("> kept reporting — nothing silently regresses.\n\n")
    f.write(f"**Word count:** {word_count}\n")
    f.write(f"**Stops:** {len(stops)} ({', '.join(s['title'] for s in stops)})\n\n")
    f.write("## Summary Table\n\n")
    f.write("| Field | Value |\n|---|---|\n")
    f.write(f"| generation cost | ${gen_actual_cost:.4f} |\n")
    f.write(f"| total tokens | {gen_actual_tokens} |\n")
    f.write(f"| stops | {', '.join(s['title'] for s in stops)} |\n")
    f.write(f"| R1 rewritten | {r1_rewritten} |\n")
    f.write(f"| R1 deleted | {r1_deleted} |\n")
    f.write(f"| R1 residual | {tour_r1_residual} |\n")
    f.write(f"| R4 residual | {tour_r4_residual} |\n")
    f.write(f"| R7 residual | {tour_r7_residual} |\n")
    f.write(f"| R9 residual | {tour_r9_residual} |\n")
    f.write(f"| R10 residual | {tour_r10_residual} |\n")
    f.write(f"| Fragment sentences | {len(tour_fragment_sentences)} |\n")
    f.write(f"| UCG sentences removed | {_ucg_removed} |\n")
    f.write(f"| UCG sentences kept (substantiated) | {_ucg_kept} |\n")
    f.write(f"| UCG escalation calls | {_ucg_escalation} |\n")
    f.write(f"| UCG escalation cost | ${_ucg_cost:.4f} |\n")
    f.write(f"| UCG deletion rate | {_ucg_rate:.1f}% |\n")
    f.write(f"| generation time | {elapsed:.1f}s |\n")
    f.write(f"| word count | {word_count} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")
    f.write("## Comparison to Round 16\n\n")
    f.write("| Metric | Round 16 | Round 18 |\n|---|---|---|\n")
    f.write(f"| Word count | 652 | {word_count} |\n")
    f.write(f"| R1 residual | ? | {tour_r1_residual} |\n")
    f.write(f"| R7 residual | 0 | {tour_r7_residual} |\n")
    f.write(f"| Cost | ~$0.0206 | ${gen_actual_cost:.4f} |\n\n")
    f.write("## Fact Tally Per Stop\n\n")
    for title, count in fact_tallies.items():
        f.write(f"- **{title}**: {count} facts\n")
    f.write(f"\n## Tour Content\n\n")
    f.write(tour_text)
    f.write("\n")

print(f"  Written: {md_path}")
print(f"  Word count: {word_count}")

# Write plain text to tours/
tours_dir = os.path.join(PROJECT_ROOT, "tours")
os.makedirs(tours_dir, exist_ok=True)
txt_path = os.path.join(tours_dir, "LOCAL263_riviera_2stop_round18.txt")
with open(txt_path, 'w') as f:
    f.write(tour_text)
print(f"  Written: {txt_path}")

# Copy to ~/Audioura/tours/ (Michael reads it there)
audioura_tours = os.path.expanduser("~/Audioura/tours")
if os.path.isdir(audioura_tours):
    dest = os.path.join(audioura_tours, "LOCAL263_riviera_2stop_round18.txt")
    shutil.copy2(txt_path, dest)
    print(f"  Copied to: {dest}")
else:
    os.makedirs(audioura_tours, exist_ok=True)
    dest = os.path.join(audioura_tours, "LOCAL263_riviera_2stop_round18.txt")
    shutil.copy2(txt_path, dest)
    print(f"  Created and copied to: {dest}")

# ======================================================================
# STEP 6: CLEANUP (D141)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: CLEANUP (D141)")
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
assert count_final == count_before, f"Row count changed: {count_before} → {count_final}"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
print(f"  Nice list final: {nice_final}")
assert nice_final == EXPECTED_NICE
conn.close()

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("ROUND 18 COMPLETE")
print("=" * 70)
print(f"  Artifact: RIVIERA_2STOP_ROUND18.md")
print(f"  Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  Word count: {word_count}")
print(f"  Facts: {fact_tallies}")
print(f"  UCG removed: {_ucg_removed}, kept: {_ucg_kept}")
print(f"  Escalation: {_ucg_escalation} calls, ${_ucg_cost:.4f}")
print(f"  R1: {r1_rewritten} rewritten, {r1_deleted} deleted, {tour_r1_residual} residual")
print(f"  R7 residual: {tour_r7_residual}")
print(f"  Fragments: {len(tour_fragment_sentences)}")
