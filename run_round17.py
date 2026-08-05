#!/usr/bin/env python3
"""ROUND17: R2/R3/R4/R8 deletion paths (LOCAL-261, D165).

Regenerates a 2-stop French Riviera cycling tour with four new deletion phases:
  PHASE 5.141 — R2 question deletion
  PHASE 5.142 — R3 suggestive-exploration deletion
  PHASE 5.143 — R4 prescribed-feeling deletion
  PHASE 5.144 — R8 prompt-leakage deletion

Same shape as round 15: biking, 2 stops, French Riviera, $0.60 ceiling.
All in-pipeline gates ON. No flags inherited.
"""
import os
import sys
import re
import io
import json
import time
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
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND17: R2/R3/R4/R8 DELETION PATHS (LOCAL-261, D165)")
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
# STEP 0: CORPUS-WIDE BASELINE (R2, R3, R4, R8 — before)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 0: CORPUS-WIDE BASELINE (R2, R3, R4, R8)")
print("=" * 70)

from style_validator_detector import (
    validate_paragraph, _split_sentences, check_r1_imperatives,
    _is_style_navigation_sentence, rewrite_r1_sentence_deterministic,
    apply_r1_to_description, check_r7_hallucinated_sensory,
    _has_finite_main_verb,
    check_r2_questions, check_r3_suggestive_exploration,
    check_r4_prescribed_feeling, check_r8_prompt_leakage
)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id, tour_content FROM audio_tours WHERE tour_content IS NOT NULL AND LENGTH(tour_content) > 100")
corpus_rows = cur.fetchall()
conn.close()

baseline_total_sentences = 0
baseline_r2_fires = 0
baseline_r3_fires = 0
baseline_r4_fires = 0
baseline_r8_fires = 0

for _tid, _content in corpus_rows:
    _paras = [p.strip() for p in _content.split('\n\n') if p.strip() and len(p.strip()) > 30]
    for _para in _paras:
        _sents = _split_sentences(_para)
        for _s in _sents:
            if len(_s) < 10:
                continue
            if _is_style_navigation_sentence(_s):
                continue
            baseline_total_sentences += 1
            r2_f = check_r2_questions(_s)
            if any(f['severity'] == 'error' for f in r2_f):
                baseline_r2_fires += 1
            if check_r3_suggestive_exploration(_s):
                baseline_r3_fires += 1
            if check_r4_prescribed_feeling(_s):
                baseline_r4_fires += 1
            if check_r8_prompt_leakage(_s):
                baseline_r8_fires += 1

print(f"  Corpus: {len(corpus_rows)} tours, {baseline_total_sentences} non-nav sentences")
print(f"  R2 (question, error):    {baseline_r2_fires}/{baseline_total_sentences} = {baseline_r2_fires/baseline_total_sentences*100:.2f}%")
print(f"  R3 (suggestive):         {baseline_r3_fires}/{baseline_total_sentences} = {baseline_r3_fires/baseline_total_sentences*100:.2f}%")
print(f"  R4 (prescribed feeling): {baseline_r4_fires}/{baseline_total_sentences} = {baseline_r4_fires/baseline_total_sentences*100:.2f}%")
print(f"  R8 (prompt leakage):     {baseline_r8_fires}/{baseline_total_sentences} = {baseline_r8_fires/baseline_total_sentences*100:.2f}%")
print(f"  Total deletion pressure: {(baseline_r2_fires+baseline_r3_fires+baseline_r4_fires+baseline_r8_fires)/baseline_total_sentences*100:.2f}%")

# ======================================================================
# STEP 1: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND 17)")
print("=" * 70)

# FLAGS: All gates ON. No DISABLE flags.
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Explicitly REMOVE any disable flags — all gates ON
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_R7_DELETION', 'DISABLE_R1_REWRITE',
           'DISABLE_R10_DELETION',
           'DISABLE_R2_DELETION', 'DISABLE_R3_DELETION',
           'DISABLE_R4_DELETION', 'DISABLE_R8_DELETION',
           'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
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
               'DISABLE_R2_DELETION', 'DISABLE_R3_DELETION', 'DISABLE_R4_DELETION',
               'DISABLE_R8_DELETION', 'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION',
               'DISABLE_CONTRADICTED_BLOCK'):
    print(f"    {_gflag}: NOT SET ({_gflag.replace('DISABLE_', '').replace('_', ' ').title()} ON)")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL261_riviera_2stop_round17.txt")

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
# STEP 2: MEASUREMENTS ON GENERATED TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: MEASUREMENTS (R1-R4, R7-R10, fragments)")
print("=" * 70)

stops = parse_tour_stops(tour_text)
tour_r1_sentences = 0
tour_r2_sentences = 0
tour_r3_sentences = 0
tour_r4_sentences = 0
tour_r7_sentences = 0
tour_r8_sentences = 0
tour_total_sentences = 0
tour_nav_sentences = 0
tour_fragment_sentences = []

_tour_paragraphs = [p.strip() for p in tour_text.split('\n\n') if p.strip() and len(p.strip()) > 30]
for para in _tour_paragraphs:
    sents = _split_sentences(para)
    for s in sents:
        if len(s) < 10:
            continue
        if _is_style_navigation_sentence(s):
            tour_nav_sentences += 1
            continue
        tour_total_sentences += 1
        if check_r1_imperatives(s):
            tour_r1_sentences += 1
        r2_f = check_r2_questions(s)
        if any(f['severity'] == 'error' for f in r2_f):
            tour_r2_sentences += 1
        if check_r3_suggestive_exploration(s):
            tour_r3_sentences += 1
        if check_r4_prescribed_feeling(s):
            tour_r4_sentences += 1
        if check_r7_hallucinated_sensory(s):
            tour_r7_sentences += 1
        if check_r8_prompt_leakage(s):
            tour_r8_sentences += 1
        if not _has_finite_main_verb(s):
            tour_fragment_sentences.append(s[:100])

print(f"  Total non-nav sentences: {tour_total_sentences}")
print(f"  Nav sentences (exempt):  {tour_nav_sentences}")
print(f"  R1 residual: {tour_r1_sentences}")
print(f"  R2 residual: {tour_r2_sentences}")
print(f"  R3 residual: {tour_r3_sentences}")
print(f"  R4 residual: {tour_r4_sentences}")
print(f"  R7 residual: {tour_r7_sentences}")
print(f"  R8 residual: {tour_r8_sentences}")
print(f"  Fragments:   {len(tour_fragment_sentences)}")

# Pipeline action counts from log
for rule_tag in ('R2', 'R3', 'R4', 'R8'):
    match = re.search(rf'\[LOCAL-261\] {rule_tag} summary: (\d+) sentences deleted', gen_log)
    if match:
        print(f"  {rule_tag} deleted in pipeline: {match.group(1)}")

# ======================================================================
# STEP 3: STORE TO DB (D141 compliant)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: STORE TO DB (D141 COMPLIANT)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

_tour_name_unique = f"RIVIERA_2STOP_ROUND17_LOCAL261_{int(time.time())}"
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
# STEP 4: FACT TALLY
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: FACT TALLY PER STOP")
print("=" * 70)

fact_tallies = {}
for idx, stop in enumerate(stops):
    title = stop.get('title', 'Unknown')
    stop_marker = f"Stop {idx+1}: {title}"
    next_marker = f"Stop {idx+2}:" if idx + 1 < len(stops) else None

    start_idx = tour_text.find(stop_marker)
    if start_idx >= 0:
        end_idx = tour_text.find(next_marker, start_idx + len(stop_marker)) if next_marker else len(tour_text)
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
        print(f"      * {s}")

# ======================================================================
# STEP 5: WRITE ARTIFACT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: WRITE RIVIERA_2STOP_ROUND17.md")
print("=" * 70)

word_count = len(tour_text.split())

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND17.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 17 (LOCAL-261)\n\n")
    f.write("> ### What changed: ROUND17 — R2/R3/R4/R8 deletion paths (D165)\n>\n")
    f.write("> Four detectors that could see but not act now delete.\n")
    f.write("> PHASE 5.141 (R2 questions), 5.142 (R3 suggestive), 5.143 (R4 prescribed feeling), 5.144 (R8 prompt leakage).\n")
    f.write("> No detector widened. $0.00 added cost — all four phases are deterministic.\n\n")
    f.write(f"**Word count:** {word_count} (round 15: 708)\n")
    f.write(f"**Stops:** {len(stops)} ({', '.join(s['title'] for s in stops)})\n\n")
    f.write("## Corpus-Wide Rates (Before = After — detectors unchanged)\n\n")
    f.write("| Rule | Fires | Rate | D55 ceiling (3x) |\n|---|---|---|---|\n")
    f.write(f"| R2 (question) | {baseline_r2_fires}/{baseline_total_sentences} | {baseline_r2_fires/baseline_total_sentences*100:.2f}% | {baseline_r2_fires/baseline_total_sentences*100*3:.2f}% |\n")
    f.write(f"| R3 (suggestive) | {baseline_r3_fires}/{baseline_total_sentences} | {baseline_r3_fires/baseline_total_sentences*100:.2f}% | {baseline_r3_fires/baseline_total_sentences*100*3:.2f}% |\n")
    f.write(f"| R4 (prescribed) | {baseline_r4_fires}/{baseline_total_sentences} | {baseline_r4_fires/baseline_total_sentences*100:.2f}% | {baseline_r4_fires/baseline_total_sentences*100*3:.2f}% |\n")
    f.write(f"| R8 (leakage) | {baseline_r8_fires}/{baseline_total_sentences} | {baseline_r8_fires/baseline_total_sentences*100:.2f}% | {baseline_r8_fires/baseline_total_sentences*100*3:.2f}% |\n")
    f.write(f"| **Total** | {baseline_r2_fires+baseline_r3_fires+baseline_r4_fires+baseline_r8_fires} | {(baseline_r2_fires+baseline_r3_fires+baseline_r4_fires+baseline_r8_fires)/baseline_total_sentences*100:.2f}% | — |\n\n")
    f.write("Before = After because no detector was widened. Only the action path was added.\n\n")
    f.write("## Pipeline Residuals (in generated tour)\n\n")
    f.write("| Rule | Residual in output |\n|---|---|\n")
    f.write(f"| R1 | {tour_r1_sentences} |\n")
    f.write(f"| R2 | {tour_r2_sentences} |\n")
    f.write(f"| R3 | {tour_r3_sentences} |\n")
    f.write(f"| R4 | {tour_r4_sentences} |\n")
    f.write(f"| R7 | {tour_r7_sentences} |\n")
    f.write(f"| R8 | {tour_r8_sentences} |\n\n")
    f.write("## Fact Tally Per Stop\n\n")
    for title, count in fact_tallies.items():
        f.write(f"- **{title}**: {count} facts\n")
    f.write(f"\n## Summary\n\n")
    f.write("| Field | Value |\n|---|---|\n")
    f.write(f"| generation cost | ${gen_actual_cost:.4f} |\n")
    f.write(f"| total tokens | {gen_actual_tokens} |\n")
    f.write(f"| word count | {word_count} |\n")
    f.write(f"| round 15 words | 708 |\n")
    f.write(f"| generation time | {elapsed:.1f}s |\n")
    f.write(f"| attempts | {gen_attempt}/{MAX_GEN_ATTEMPTS} |\n")
    f.write(f"| fragments | {len(tour_fragment_sentences)} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")
    f.write("## Flags\n\n")
    f.write("All gates ON. No DISABLE flags set. Phases 5.141–5.144 active.\n\n")
    f.write(f"## Tour Content\n\n")
    f.write(tour_text)
    f.write("\n")

print(f"  Written: {md_path}")
print(f"  Word count: {word_count}")

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
assert count_final == count_before, f"Row count changed: {count_before} -> {count_final}"

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_final = [r[0] for r in cur.fetchall()]
print(f"  Nice list final: {nice_final}")
assert nice_final == EXPECTED_NICE
conn.close()

# ======================================================================
# DONE
# ======================================================================
print("\n" + "=" * 70)
print("ROUND 17 COMPLETE")
print("=" * 70)
print(f"  Artifact: RIVIERA_2STOP_ROUND17.md")
print(f"  Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  Word count: {word_count} (round 15: 708)")
print(f"  Residuals: R2={tour_r2_sentences} R3={tour_r3_sentences} R4={tour_r4_sentences} R8={tour_r8_sentences}")
print(f"  Facts: {fact_tallies}")
if word_count < 450:
    print(f"  *** WORD COUNT BELOW 450 — tour is thin. Answer is corpus depth (D153), not looser rules. ***")
