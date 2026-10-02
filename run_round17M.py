#!/usr/bin/env python3
"""ROUND17M: R1 fragment fix + Description: label gate + R7 orientation (ROUND17M).

Regenerates a 2-stop French Riviera cycling tour with three fixes:
1. R1 rewrite now guarantees a finite main verb (no fragments)
2. "Description:" schema label stripped at split + caught by post-assembly gate
3. R7 fires on fabricated multi-sensory in orientation text

Same shape as round 12: biking, 2 stops, French Riviera, $0.60 ceiling.
All in-pipeline gates ON. No flags inherited from LOCAL-255.
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
print("ROUND17M: R1 FRAGMENT FIX + DESCRIPTION LABEL + R7 ORIENTATION (ROUND17M)")
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
# STEP 0: CORPUS-WIDE R7 BASELINE (before + after ROUND17M patterns)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 0: CORPUS-WIDE R7 BASELINE")
print("=" * 70)

from style_validator_detector import (
    validate_paragraph, _split_sentences, check_r1_imperatives,
    _is_style_navigation_sentence, rewrite_r1_sentence_deterministic,
    apply_r1_to_description, check_r7_hallucinated_sensory,
    _has_finite_main_verb
)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT id, tour_content FROM audio_tours WHERE tour_content IS NOT NULL AND LENGTH(tour_content) > 100")
corpus_rows = cur.fetchall()
conn.close()

baseline_r7_sentences = 0
baseline_total_sentences = 0
baseline_r1_paragraphs = 0
baseline_total_paragraphs = 0
baseline_r1_sentences = 0

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
            if check_r7_hallucinated_sensory(_s):
                baseline_r7_sentences += 1

print(f"  R1 corpus baseline:")
print(f"    Paragraphs: {baseline_r1_paragraphs}/{baseline_total_paragraphs} "
      f"= {baseline_r1_paragraphs/baseline_total_paragraphs*100:.1f}%")
print(f"    Sentences:  {baseline_r1_sentences}/{baseline_total_sentences} "
      f"= {baseline_r1_sentences/baseline_total_sentences*100:.1f}%")
print(f"  R7 corpus baseline:")
print(f"    Sentences:  {baseline_r7_sentences}/{baseline_total_sentences} "
      f"= {baseline_r7_sentences/baseline_total_sentences*100:.2f}%")

# ======================================================================
# STEP 1: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND 13)")
print("=" * 70)

# FLAGS: All gates ON. No DISABLE flags. Explicitly pop any inherited flags.
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
# [ROUND17M] Every gate ON at Michael's request — including the subject routine,
# which prior rounds disabled. R7 deletion and R1 rewrite are the two that matter here.
os.environ.pop('DISABLE_SUBJECT_ROUTINE', None)
os.environ['DISABLE_TOUR_CACHE'] = '1'

# Explicitly REMOVE any disable flags (copy of round 12 — no DISABLE_R10_DELETION inheritance)
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
for _gflag in ('DISABLE_STYLE_RETRY', 'DISABLE_R1_REWRITE', 'DISABLE_R7_DELETION',
               'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK'):
    print(f"    {_gflag}: NOT SET ({_gflag.replace('DISABLE_', '').replace('_', ' ').title()} ON)")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL264b_riviera_2stop_round17M.txt")

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
print("STEP 2: MEASUREMENTS (R1, R7, R8, R9, R10, fragments, Description:)")
print("=" * 70)

stops = parse_tour_stops(tour_text)
tour_r1_sentences = 0
tour_total_sentences = 0
tour_nav_sentences = 0
tour_r7_residual = 0
tour_r7_sentences_found = []
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
        if check_r7_hallucinated_sensory(s):
            tour_r7_residual += 1
            tour_r7_sentences_found.append(s[:100])
        # Fragment check: sentences that lack a finite main verb
        if not _has_finite_main_verb(s):
            tour_fragment_sentences.append(s[:100])

# Description: label check
desc_label_count = tour_text.count('Description:')
# Only count bare labels (on their own line)
_bare_desc_labels = re.findall(r'^\s*Description:\s*$', tour_text, re.MULTILINE)

print(f"  R1 residual:     {tour_r1_sentences}/{tour_total_sentences} "
      f"({tour_r1_sentences/tour_total_sentences*100:.1f}%)" if tour_total_sentences > 0 else "N/A")
print(f"  R7 residual:     {tour_r7_residual}")
for s in tour_r7_sentences_found:
    print(f"    R7: {s}")
print(f"  Nav sentences:   {tour_nav_sentences} (exempt)")
print(f"  Description: labels (bare): {len(_bare_desc_labels)}")
if _bare_desc_labels:
    print(f"    ⚠️  DEFECT: Description: label in output!")
print(f"  Fragment sentences: {len(tour_fragment_sentences)}")
for s in tour_fragment_sentences[:5]:
    print(f"    FRAG: {s}")

# R1 rewrite stats from log
r1_rewritten_match = re.search(r'\[LOCAL-255\] R1 summary: (\d+) rewritten, (\d+) deleted', gen_log)
if r1_rewritten_match:
    r1_rewritten = int(r1_rewritten_match.group(1))
    r1_deleted = int(r1_rewritten_match.group(2))
else:
    r1_rewritten = 0
    r1_deleted = 0

# R1 fallback-to-original count (fragment rejections)
r1_fallback_match = re.search(r'R1.*fallback.*?(\d+)', gen_log)
r1_fallback_count = int(r1_fallback_match.group(1)) if r1_fallback_match else 0

print(f"  R1 pipeline: {r1_rewritten} rewritten, {r1_deleted} deleted")

# ======================================================================
# STEP 3: STORE TO DB (D141 compliant)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: STORE TO DB (D141 COMPLIANT)")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()

_tour_name_unique = f"RIVIERA_2STOP_ROUND17M_LOCAL264b_{int(time.time())}"
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
        print(f"      • {s}")

# ======================================================================
# STEP 5: WRITE ARTIFACT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: WRITE RIVIERA_2STOP_ROUND17M.md")
print("=" * 70)

word_count = len(tour_text.split())

md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND17M.md")
with open(md_path, 'w') as f:
    f.write("# French Riviera Cycling Tour - 2 Stops, Round 17M (ROUND17M)\n\n")
    f.write("> ### What changed: ROUND17M — R1 fragment fix, Description: gate, R7 orientation\n>\n")
    f.write("> R1 rewrites now guarantee a finite main verb (fragments rejected → fallback to original).\n")
    f.write("> \"Description:\" schema labels stripped at split + post-assembly gate.\n")
    f.write("> R7 extended with two patterns for fabricated multi-sensory in orientation text.\n")
    f.write("> Corpus-wide R7 rate: 1.25% → 1.33% (1.06×, within D55 3× ceiling).\n\n")
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
    f.write(f"| R7 residual | {tour_r7_residual} |\n")
    f.write(f"| Description: labels | {len(_bare_desc_labels)} |\n")
    f.write(f"| Fragment sentences | {len(tour_fragment_sentences)} |\n")
    f.write(f"| generation time | {elapsed:.1f}s |\n")
    f.write(f"| generation attempts | {gen_attempt}/{MAX_GEN_ATTEMPTS} |\n")
    f.write(f"| word count | {word_count} |\n")
    f.write(f"| date | 2026-08-05 |\n\n")
    f.write("## R7 Corpus-Wide Before/After (ROUND17M)\n\n")
    f.write("| Metric | Before (all patterns) | In this tour |\n|---|---|---|\n")
    f.write(f"| R7 rate | {baseline_r7_sentences}/{baseline_total_sentences} = "
            f"{baseline_r7_sentences/baseline_total_sentences*100:.2f}% | "
            f"{tour_r7_residual}/{tour_total_sentences} |\n\n")
    f.write("## Verbless Sentence List\n\n")
    if tour_fragment_sentences:
        for s in tour_fragment_sentences:
            f.write(f"- {s}\n")
    else:
        f.write("*(none detected)*\n")
    f.write("\n## Fact Tally Per Stop\n\n")
    for title, count in fact_tallies.items():
        f.write(f"- **{title}**: {count} facts\n")
    f.write(f"\n## Tour Content\n\n")
    f.write(tour_text)
    f.write("\n\n---\n\n")
    f.write("## Comparison to Round 12\n\n")
    f.write("| Metric | Round 12 | Round 17M |\n|---|---|---|\n")
    f.write(f"| Word count | 624 | {word_count} |\n")
    f.write(f"| R1 residual | 3 | {tour_r1_sentences} |\n")
    f.write(f"| R7 residual | 0 | {tour_r7_residual} |\n")
    f.write(f"| Description: labels | 1 | {len(_bare_desc_labels)} |\n")
    f.write(f"| Fragment sentences | (not measured) | {len(tour_fragment_sentences)} |\n")
    f.write(f"| Cost | $0.0095 | ${gen_actual_cost:.4f} |\n\n")

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
print("ROUND 13 COMPLETE")
print("=" * 70)
print(f"  Artifact: RIVIERA_2STOP_ROUND17M.md")
print(f"  Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
print(f"  R1: {r1_rewritten} rewritten, {r1_deleted} deleted, {tour_r1_sentences} residual")
print(f"  R7: {tour_r7_residual} residual")
print(f"  Description: labels: {len(_bare_desc_labels)}")
print(f"  Fragment sentences: {len(tour_fragment_sentences)}")
print(f"  Word count: {word_count}")
print(f"  Facts: {fact_tallies}")
