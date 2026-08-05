#!/usr/bin/env python3
"""LOCAL-208: Generate a 2-stop French Riviera cycling tour for Michael.

Deliverable for Michael to read paragraph by paragraph.
- STORIED_MODE=true
- 2 stops (D61)
- All gates ON (corpus coverage gate, style retry, etc.)
- Default model (gpt-3.5-turbo, TOUR_LLM_MODEL unset)
- biking tour_type (same as tours 29 and 152)

Usage:
    python run_local208_riviera_2stop.py
"""
import os
import sys
import re
import json
import time

# ─── Project root (this file is at repo root) ───────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# ─── Load .env for API keys (never hardcode) ─────────────────────────────────
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

# ─── Environment ─────────────────────────────────────────────────────────────
os.environ['STORIED_MODE'] = 'true'

# Ensure TOUR_LLM_MODEL is NOT set (use default gpt-3.5-turbo)
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
    if k in os.environ:
        del os.environ[k]

# ─── Database connection ─────────────────────────────────────────────────────
from db_connection import get_connection, check_db_available

print("=" * 70)
print("LOCAL-208: French Riviera 2-Stop Cycling Tour for Michael")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset → gpt-3.5-turbo)')}")
print(f"  DISABLE_CORPUS_GATE = {os.environ.get('DISABLE_CORPUS_GATE', '(unset → ON)')}")
print(f"  DISABLE_STYLE_RETRY = {os.environ.get('DISABLE_STYLE_RETRY', '(unset → ON)')}")
print()

# ─── Step 0: Pre-checks ─────────────────────────────────────────────────────
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

# Nice list via lat/lng range (avoids PostGIS dependency issues)
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_pre = [r[0] for r in cur.fetchall()]
expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
# Filter to the known set (exclude translated duplicates like 19,20,22,23,30,31,32,33)
visible_nice = [i for i in nice_rows_pre if i in expected_nice]
print(f"[PRE] Nice visible tour IDs: {visible_nice}")
conn.close()

# ─── Step 1: Corpus coverage pre-assessment ──────────────────────────────────
print("\n" + "─" * 70)
print("STEP 1: Corpus Coverage Pre-Assessment")
print("─" * 70)
print("  Biking tours use Wikipedia retrieval (outdoor POIs).")
print("  stop_corpus has 'French Riviera walking area' (15 stops).")
print("  The pipeline matches stops by name at runtime if they overlap.")

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT stop_title FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
    ORDER BY stop_title
""")
riviera_corpus_stops = [r[0] for r in cur.fetchall()]
print(f"  Available corpus stops: {riviera_corpus_stops}")
print(f"  (Coverage verdicts depend on which 2 stops the pipeline selects)")
conn.close()

# ─── Step 2: Generate the tour ───────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 2: Generating 2-stop biking tour (all gates ON)")
print("─" * 70)

from generate_tour_text import generate_tour_text

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL208_riviera_2stop_for_michael.txt")

start_time = time.time()
result = generate_tour_text(
    location="French Riviera cycling tour, France",
    tour_type="biking",
    output_file=output_file,
    total_stops=2,
    persona=None,
)
elapsed = time.time() - start_time

if not result or not result[0]:
    print(f"FATAL: Tour generation returned None after {elapsed:.1f}s")
    sys.exit(1)

tour_text = result[0]
print(f"\n  ✓ Generated: {len(tour_text)} chars, {len(tour_text.split())} words in {elapsed:.1f}s")
print(f"  ✓ Output: {output_file}")

# ─── Step 3: Parse stops and assess coverage ─────────────────────────────────
print("\n" + "─" * 70)
print("STEP 3: Parse + Coverage Assessment")
print("─" * 70)

from stop_anchor_detector_v2 import parse_tour_stops

# Import validate_paragraph from the ROOT style_validator_detector.py (not tests/)
import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph

from corpus_coverage import assess_stop_coverage

stops = parse_tour_stops(tour_text)
print(f"  Parsed {len(stops)} stops")
for s in stops:
    print(f"    - {s['title']} ({len(s.get('paragraphs', []))} paragraphs)")

# Assess coverage for each stop using stop_corpus
from stop_corpus_reader import get_stop_corpus_for_tour

conn = get_connection()
stop_names = [s['title'] for s in stops]
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

coverage_verdicts = {}
print("\n  Coverage verdicts:")
for stop_name in stop_names:
    sc = corpus_data.get(stop_name)
    if sc and sc.get('passages'):
        assessment = assess_stop_coverage(
            stop_name, "French Riviera", sc['passages'],
            passage_roles=sc.get('passage_roles')
        )
        coverage_verdicts[stop_name] = assessment['verdict']
        print(f"    {stop_name}: {assessment['verdict']} "
              f"(passages={assessment['passage_count']}, "
              f"matched_words={assessment['subject_match_words']})")
    else:
        coverage_verdicts[stop_name] = "NO_CORPUS"
        print(f"    {stop_name}: NO_CORPUS (outdoor/biking — uses Wikipedia retrieval)")

# ─── Step 4: Store in audio_tours ────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 4: Store in DB (is_test=true, lat/lng=NULL)")
print("─" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    INSERT INTO audio_tours (
        tour_name, request_string, number_requested,
        is_test, storied_mode, tour_content, stops_count,
        lat, lng
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL)
    RETURNING id
""", (
    'French Riviera Cycling [LOCAL-208 for Michael]',
    'French Riviera cycling tour, France',
    2,
    True,
    True,
    tour_text,
    len(stops),
))
new_tour_id = cur.fetchone()[0]
conn.commit()
conn.close()
print(f"  ✓ Stored as tour_id={new_tour_id} (is_test=true, lat=NULL, lng=NULL)")

# ─── Step 5: Anchor detection ────────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 5: Style + Anchor Analysis")
print("─" * 70)

try:
    from stop_anchor_detector_v2 import classify_paragraph, build_corpus_anchors
    anchor_available = True
    print("  ✓ Anchor detector (v2) loaded")
except ImportError as e:
    anchor_available = False
    print(f"  ⚠ Anchor detector unavailable: {e}")
    # Define a fallback
    def classify_paragraph(para, anchors, stop, tour):
        return {'classification': 'UNAVAILABLE'}

# Build corpus anchors per stop
stop_corpus_anchors = {}
if anchor_available:
    conn = get_connection()
    corpus_data_anchors = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
    conn.close()
    for sn in stop_names:
        sc = corpus_data_anchors.get(sn)
        if sc and sc.get('passages'):
            stop_corpus_anchors[sn] = build_corpus_anchors(
                sc['passages'], sn, "French Riviera Cycling Tour"
            )
        else:
            stop_corpus_anchors[sn] = {}

# ─── Step 6: Build RIVIERA_2STOP_FOR_MICHAEL.md ─────────────────────────────
print("\n" + "─" * 70)
print("STEP 6: Building Annotated Markdown")
print("─" * 70)

md = []
md.append("# French Riviera Cycling Tour — 2 Stops (LOCAL-208)")
md.append("")
md.append("**Generated for Michael to read paragraph by paragraph.**")
md.append("")
md.append(f"- Date: {time.strftime('%Y-%m-%d %H:%M')}")
md.append(f"- Tour ID: {new_tour_id}")
md.append(f"- Model: gpt-3.5-turbo (default, TOUR_LLM_MODEL unset)")
md.append(f"- STORIED_MODE: true")
md.append(f"- All gates: ON (corpus coverage, style retry)")
md.append(f"- Stops: {len(stops)}")
md.append(f"- Total words: {len(tour_text.split())}")
md.append(f"- Generation time: {elapsed:.1f}s")
md.append("")
md.append("---")
md.append("")
md.append("## Coverage Verdicts (pre-generation)")
md.append("")
for sn in stop_names:
    md.append(f"- **{sn}**: `{coverage_verdicts[sn]}`")
md.append("")
md.append("---")
md.append("")

para_num = 0
for stop_idx, stop in enumerate(stops):
    stop_title = stop['title']
    md.append(f"## {stop_title}")
    md.append("")
    if stop_idx == 0:
        md.append("*(D64: Stop 1 contains the tour prolog stapled inside it)*")
        md.append("")

    paragraphs = stop.get('paragraphs', [])
    for para in paragraphs:
        para_text = para.strip()
        if not para_text:
            continue
        para_num += 1

        md.append(f"### Paragraph {para_num}")
        md.append("")
        md.append(para_text)
        md.append("")

        # Style
        style_result = validate_paragraph(para_text)
        rules = style_result.get('rules_violated', set())
        style_str = ','.join(sorted(rules)) if rules else 'clean'

        # Anchor
        anchors = stop_corpus_anchors.get(stop_title, {})
        try:
            anchor_result = classify_paragraph(
                para_text, anchors, stop_title, "French Riviera Cycling Tour"
            )
            anchor_str = anchor_result.get('classification', 'UNKNOWN')
        except Exception as e:
            anchor_str = f"ERROR"

        # Coverage
        cov_str = coverage_verdicts.get(stop_title, "UNKNOWN")

        md.append(f"`[anchor: {anchor_str} | style: {style_str} | coverage: {cov_str}]`")
        md.append("")

md.append("---")
md.append("")
md.append("## Summary")
md.append("")
md.append(f"- Total paragraphs numbered: {para_num}")
md.append(f"- Tour ID: {new_tour_id} (is_test=true, lat/lng=NULL)")
md.append(f"- audio_tours count before: {count_before}")

# Final count
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
md.append(f"- audio_tours count after: {count_after} (delta: +{count_after - count_before})")

# Verify Nice list unchanged
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_post = [r[0] for r in cur.fetchall()]
visible_nice_post = [i for i in nice_rows_post if i in expected_nice]
md.append(f"- Nice list: {visible_nice_post} (expected: {expected_nice})")
if visible_nice_post == expected_nice:
    md.append(f"- ✓ Nice list UNCHANGED")
else:
    md.append(f"- ✗ Nice list CHANGED!")
conn.close()

md.append("")

# Write
md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_FOR_MICHAEL.md")
with open(md_path, 'w') as f:
    f.write('\n'.join(md))
print(f"  ✓ Written: {md_path}")
print(f"  ✓ Raw text: {output_file}")

# ─── Final Report ────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("LOCAL-208 COMPLETE")
print(f"  Tour ID: {new_tour_id}")
print(f"  audio_tours: {count_before} → {count_after}")
print(f"  Nice list unchanged: {visible_nice_post == expected_nice}")
print(f"  Deliverables:")
print(f"    - RIVIERA_2STOP_FOR_MICHAEL.md (annotated)")
print(f"    - tours/LOCAL208_riviera_2stop_for_michael.txt (raw D71)")
print("=" * 70)
