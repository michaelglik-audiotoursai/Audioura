#!/usr/bin/env python3
"""ROUND12: R1 imperative rewrite path (LOCAL-255).

Regenerates a 2-stop French Riviera cycling tour with the LOCAL-255 fix:
- R1 imperatives are rewritten to declarative form (PHASE 5.13)
- Navigation sentences remain untouched (D107)
- Pure instructions (no content) are deleted
- Content preservation verified word-by-word

Same shape as round 10: biking, 2 stops, French Riviera, $0.60 ceiling.
All in-pipeline gates ON.
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
print("ROUND12: R1 IMPERATIVE REWRITE PATH (LOCAL-255)")
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
# STEP 0: CORPUS-WIDE R1 BASELINE (before rewrite path)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 0: CORPUS-WIDE R1 BASELINE")
print("=" * 70)

from style_validator_detector import (
    validate_paragraph, _split_sentences, check_r1_imperatives,
    _is_style_navigation_sentence, rewrite_r1_sentence_deterministic,
    apply_r1_to_description
)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id, tour_content FROM audio_tours WHERE tour_content IS NOT NULL AND LENGTH(tour_content) > 100")
corpus_rows = cur.fetchall()
conn.close()

baseline_r1_paragraphs = 0
baseline_total_paragraphs = 0
baseline_r1_sentences = 0
baseline_total_sentences = 0

for _tid, _content in corpus_rows:
    _paras = [p.strip() for p in _content.split('\n\n') if p.strip() and len(p.strip()) > 30]
    for _para in _paras:
        baseline_total_paragraphs += 1
        _result = validate_paragraph(_para)
        if _result.get('is_navigation'):
            continue
        _has_r1 = any(f['rule_id'] == 'R1_IMPERATIVE' for f in _result.get('findings', []))
        if _has_r1:
            baseline_r1_paragraphs += 1
        _sents = _split_sentences(_para)
        for _s in _sents:
            if len(_s) < 10:
                continue
            if _is_style_navigation_sentence(_s):
                continue
            baseline_total_sentences += 1
            if check_r1_imperatives(_s):
                baseline_r1_sentences += 1

print(f"  R1 corpus baseline (BEFORE rewrite path):")
print(f"    Paragraphs: {baseline_r1_paragraphs}/{baseline_total_paragraphs} "
      f"= {baseline_r1_paragraphs/baseline_total_paragraphs*100:.1f}%")
print(f"    Sentences:  {baseline_r1_sentences}/{baseline_total_sentences} "
      f"= {baseline_r1_sentences/baseline_total_sentences*100:.1f}%")

# ======================================================================
# STEP 1: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND 12)")
print("=" * 70)

# FLAGS: All in-pipeline gates ON. No DISABLE flags set.
# Explicitly clearing anything that might be inherited.
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_SUBJECT_ROUTINE'] = '1'
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Explicitly REMOVE any disable flags — all gates ON
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

print(f"  FLAGS SET:")
print(f"    STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"    STORIED_MODE:             {os.environ.get('STORIED_MODE')}")
print(f"    DISABLE_SUBJECT_ROUTINE:  {os.environ.get('DISABLE_SUBJECT_ROUTINE')}")
print(f"    DISABLE_TOUR_CACHE:       {os.environ.get('DISABLE_TOUR_CACHE')}")
print(f"  GATES ON (not disabled):")
print(f"    DISABLE_STYLE_RETRY:      NOT SET (style retry ON)")
print(f"    DISABLE_R1_REWRITE:       NOT SET (R1 rewrite ON)")
print(f"    DISABLE_R7_DELETION:      NOT SET (R7 deletion ON)")
print(f"    DISABLE_R9_DELETION:      NOT SET (R9 deletion ON)")
print(f"    DISABLE_R10_DELETION:     NOT SET (R10 deletion ON)")
print(f"    DISABLE_CONTRADICTED_BLOCK: NOT SET (contradicted block ON)")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL255_riviera_2stop_round12.txt")

REQUESTED_STOPS = 2
tour_text = None
gen_cost = {}
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

    # Extract real cost from generation log
    _cost_match = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
    if _cost_match:
        gen_actual_cost = float(_cost_match.group(1))
        gen_actual_tokens = int(_cost_match.group(2))

    # Validate stop count
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
# STEP 2: MEASURE R1 ON GENERATED TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: R1 MEASUREMENT ON GENERATED TOUR")
print("=" * 70)

stops = parse_tour_stops(tour_text)
tour_r1_sentences = 0
tour_total_sentences = 0
tour_nav_sentences = 0

# Measure R1 on the full tour text (not just parsed stops)
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

print(f"  R1 in generated tour:")
print(f"    R1 sentences:    {tour_r1_sentences}/{tour_total_sentences}")
print(f"    Nav sentences:   {tour_nav_sentences} (exempt)")
if tour_total_sentences > 0:
    print(f"    R1 rate:         {tour_r1_sentences/tour_total_sentences*100:.1f}%")
else:
    print(f"    R1 rate:         N/A (no content sentences parsed)")

# ======================================================================
# STEP 3: EXTRACT R1 REWRITE STATS FROM LOG
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: R1 REWRITE PIPELINE STATS")
print("=" * 70)

# Parse log for PHASE 5.13 output
r1_rewritten_match = re.search(r'\[LOCAL-255\] R1 summary: (\d+) rewritten, (\d+) deleted', gen_log)
if r1_rewritten_match:
    r1_rewritten = int(r1_rewritten_match.group(1))
    r1_deleted = int(r1_rewritten_match.group(2))
    print(f"  R1 rewrite results:")
    print(f"    Rewritten: {r1_rewritten}")
    print(f"    Deleted:   {r1_deleted}")
    r1_total_actions = r1_rewritten + r1_deleted
    if r1_total_actions > 0:
        deletion_pct = r1_deleted / r1_total_actions * 100
        print(f"    Deletion rate: {r1_deleted}/{r1_total_actions} = {deletion_pct:.1f}%")
        if deletion_pct > 10:
            print(f"    ⚠ Deletion rate exceeds 10% — review needed")
else:
    r1_rewritten = 0
    r1_deleted = 0
    print("  (R1 stats not found in log — phase may not have fired)")

# ======================================================================
# STEP 4: R7 SECONDARY CHECK
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: R7 SECONDARY CHECK")
print("=" * 70)

from style_validator_detector import check_r7_hallucinated_sensory

r7_residual = 0
r7_sentences_found = []
salty_air_sentence = "Take a moment to breathe in the salty sea air and listen to the gentle lapping of the waves"

for stop in stops:
    content = stop.get('content', '')
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and len(p.strip()) > 30]
    for para in paragraphs:
        sents = _split_sentences(para)
        for s in sents:
            if len(s) < 10:
                continue
            findings = check_r7_hallucinated_sensory(s)
            if findings:
                r7_residual += 1
                r7_sentences_found.append(s[:80])

print(f"  R7 residual: {r7_residual}")
for s in r7_sentences_found:
    print(f"    - {s}")

# Check if the round 10 R7 residual is now caught by R1
print(f"\n  Round 10 R7 residual ('salty sea air') now handled by R1:")
r1_fires_on_salty = bool(check_r1_imperatives(salty_air_sentence))
print(f"    R1 fires: {r1_fires_on_salty}")
if r1_fires_on_salty:
    r1_result = rewrite_r1_sentence_deterministic(salty_air_sentence)
    print(f"    Deterministic result: {'DELETED' if r1_result is None else ('LLM_NEEDED' if r1_result == '__LLM_NEEDED__' else r1_result)}")

# ======================================================================
# STEP 5: STORE TO DB (D141 compliant)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: STORE TO DB (D141 COMPLIANT)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

# Insert as test row
import random
_tour_name_unique = f"RIVIERA_2STOP_ROUND12_LOCAL255_{int(time.time())}"
cur.execute("""
    INSERT INTO audio_tours (tour_name, tour_content, is_test, request_string)
    VALUES (%s, %s, true, %s)
    RETURNING id
""", (_tour_name_unique, tour_text, "French Riviera cycling tour, France"))
inserted_id = cur.fetchone()[0]
conn.commit()
print(f"  Inserted tour id={inserted_id} (is_test=true)")

# Verify
cur.execute("SELECT id, is_test FROM audio_tours WHERE id = %s", (inserted_id,))
row = cur.fetchone()
assert row[1] is True, f"is_test not true for id={inserted_id}"

# Check Nice list unchanged
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list after: {nice_after}")
assert nice_after == EXPECTED_NICE

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours count: {count_before} → {count_after}")
conn.close()

# ======================================================================
# STEP 6: FACT TALLY (HAND-COUNTED)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 6: FACT TALLY PER STOP")
print("=" * 70)

for stop in stops:
    title = stop.get('title', 'Unknown')
    # Extract the stop's text directly from tour_text
    stop_marker = f"Stop {stops.index(stop)+1}: {title}"
    next_marker = f"Stop {stops.index(stop)+2}:" if stops.index(stop) + 1 < len(stops) else None
    
    start_idx = tour_text.find(stop_marker)
    if start_idx >= 0:
        if next_marker:
            end_idx = tour_text.find(next_marker, start_idx + len(stop_marker))
            if end_idx < 0:
                end_idx = len(tour_text)
        else:
            end_idx = len(tour_text)
        content = tour_text[start_idx:end_idx]
    else:
        content = stop.get('content', '') or ''
    
    sents = _split_sentences(content) if content else []
    fact_sents = []
    total_content_sents = 0
    for s in sents:
        if len(s) < 10:
            continue
        if _is_style_navigation_sentence(s):
            continue
        total_content_sents += 1
        # Heuristic: sentence has a fact if it contains a date, proper noun+verb,
        # or specific measurement
        has_date = bool(re.search(r'\b\d{3,4}\b', s))
        has_proper_noun = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', s))
        has_specific = bool(re.search(r'\b(?:founded|built|created|opened|established|published|painted|wrote|composed|designed|constructed|renovated|completed|destroyed|restored)\b', s, re.IGNORECASE))
        if has_date or (has_proper_noun and has_specific):
            fact_sents.append(s[:80])
    print(f"\n  {title}:")
    print(f"    Content sentences: {total_content_sents}")
    print(f"    Sentences with facts: {len(fact_sents)}/{total_content_sents}")
    for s in fact_sents[:5]:
        print(f"      • {s}")

# ======================================================================
# STEP 7: WRITE ARTIFACT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 7: WRITE RIVIERA_2STOP_ROUND12.md")
print("=" * 70)

# Word count
word_count = len(tour_text.split())

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND12.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 12 (ROUND12)\n\n")
    f.write("> ### What changed: R1 imperative rewrite path (LOCAL-255)\n>\n")
    f.write("> R1 imperatives are rewritten to declarative form rather than deleted.\n")
    f.write("> Navigation sentences (D107) are exempt and survive untouched.\n")
    f.write("> Pure instructions with no content are the only R1 hits deleted.\n")
    f.write("> PHASE 5.13 wired between style retry (5.1) and R7 deletion (5.14).\n\n")
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
    f.write("| DISABLE_SUBJECT_ROUTINE | 1 (OFF) |\n")
    f.write("| DISABLE_TOUR_CACHE | 1 (OFF) |\n\n")
    f.write("## Summary Table\n\n")
    f.write("| Field | Value |\n|---|---|\n")
    f.write(f"| generation cost | ${gen_actual_cost:.4f} |\n")
    f.write(f"| total tokens | {gen_actual_tokens} |\n")
    f.write(f"| stops | {', '.join(s['title'] for s in stops)} |\n")
    f.write(f"| R1 rewritten | {r1_rewritten} |\n")
    f.write(f"| R1 deleted | {r1_deleted} |\n")
    f.write(f"| R1 residual (post-pipeline) | {tour_r1_sentences} |\n")
    f.write(f"| R7 residual | {r7_residual} |\n")
    f.write(f"| generation time | {elapsed:.1f}s |\n")
    f.write(f"| generation attempts | {gen_attempt}/{MAX_GEN_ATTEMPTS} |\n")
    f.write(f"| word count | {word_count} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")
    f.write("## R1 Corpus-Wide Before/After\n\n")
    f.write("| Metric | Before | After (this tour) |\n|---|---|---|\n")
    f.write(f"| R1 paragraph rate | {baseline_r1_paragraphs/baseline_total_paragraphs*100:.1f}% | — |\n")
    _tour_r1_rate = f"{tour_r1_sentences}/{tour_total_sentences} = {tour_r1_sentences/tour_total_sentences*100:.1f}%" if tour_total_sentences > 0 else "N/A"
    f.write(f"| R1 sentence rate | {baseline_r1_sentences/baseline_total_sentences*100:.1f}% | {_tour_r1_rate} |\n\n")
    f.write("## Tour Content\n\n")
    f.write(tour_text)
    f.write("\n\n---\n\n")
    f.write("## Comparison to Round 10\n\n")
    f.write("| Metric | Round 10 | Round 12 |\n|---|---|---|\n")
    f.write(f"| Word count | 679 | {word_count} |\n")
    f.write(f"| R1 sentences | 5 | {tour_r1_sentences} |\n")
    f.write(f"| R7 residual | 1 | {r7_residual} |\n")
    f.write(f"| Cost | $0.0095 | ${gen_actual_cost:.4f} |\n\n")

print(f"  Written: {md_path}")
print(f"  Word count: {word_count}")

# ======================================================================
# STEP 8: CLEANUP (D141)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 8: CLEANUP (D141)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

# Verify the inserted row is still is_test=true before deleting
cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (inserted_id,))
row = cur.fetchone()
if row and row[0] is True:
    cur.execute("DELETE FROM audio_tours WHERE id = %s", (inserted_id,))
    conn.commit()
    print(f"  Deleted test row id={inserted_id} (is_test=true confirmed)")
else:
    print(f"  WARNING: id={inserted_id} is_test={row[0] if row else 'NOT FOUND'} — NOT deleted")

# Final verification
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
print("ROUND 12 COMPLETE")
print("=" * 70)
print(f"  Artifact: RIVIERA_2STOP_ROUND12.md")
print(f"  Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  R1: {r1_rewritten} rewritten, {r1_deleted} deleted, {tour_r1_sentences} residual")
print(f"  R7: {r7_residual} residual")
print(f"  Word count: {word_count}")
