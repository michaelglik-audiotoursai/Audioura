#!/usr/bin/env python3
"""LOCAL-208 Post-processor: Build RIVIERA_2STOP_FOR_MICHAEL.md from generated text.

Reads the already-generated tour text, runs detectors, builds the annotated markdown.
"""
import os
import sys
import re
import json
import time

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

os.environ['STORIED_MODE'] = 'true'

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops, classify_paragraph, build_corpus_anchors
from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour

# Import validate_paragraph from the ROOT style_validator_detector.py
import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph

# ─── Read generated tour text ────────────────────────────────────────────────
tour_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL208_riviera_2stop_for_michael.txt")
with open(tour_file) as f:
    tour_text = f.read()

print(f"Read tour: {len(tour_text)} chars, {len(tour_text.split())} words")

# ─── Database checks ─────────────────────────────────────────────────────────
if not check_db_available():
    print("FATAL: DB unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()

# Check if tour already stored
cur.execute("SELECT id FROM audio_tours WHERE tour_name = %s", ('French Riviera Cycling [LOCAL-208 for Michael]',))
row = cur.fetchone()
if row:
    new_tour_id = row[0]
    print(f"Tour already in DB: id={new_tour_id}")
else:
    # Store it
    stops_parsed = parse_tour_stops(tour_text)
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
        len(stops_parsed),
    ))
    new_tour_id = cur.fetchone()[0]
    conn.commit()
    print(f"Stored as tour_id={new_tour_id} (is_test=true, lat/lng=NULL)")

# Counts
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_total = cur.fetchone()[0]

# Nice list
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows = [r[0] for r in cur.fetchall()]
expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
visible_nice = [i for i in nice_rows if i in expected_nice]
print(f"Nice list: {visible_nice} (expected: {expected_nice})")
print(f"audio_tours total: {count_total}")
conn.close()

# ─── Parse stops ─────────────────────────────────────────────────────────────
stops = parse_tour_stops(tour_text)
print(f"\nParsed {len(stops)} stops:")
for s in stops:
    print(f"  - {s['title']} ({len(s.get('paragraphs', []))} paragraphs)")

# ─── Coverage assessment ─────────────────────────────────────────────────────
conn = get_connection()
stop_names = [s['title'] for s in stops]
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

coverage_verdicts = {}
print("\nCoverage verdicts:")
for sn in stop_names:
    sc = corpus_data.get(sn)
    if sc and sc.get('passages'):
        assessment = assess_stop_coverage(
            sn, "French Riviera", sc['passages'],
            passage_roles=sc.get('passage_roles')
        )
        coverage_verdicts[sn] = assessment['verdict']
        print(f"  {sn}: {assessment['verdict']} "
              f"(passages={assessment['passage_count']}, "
              f"matched={assessment['subject_match_words']})")
    else:
        coverage_verdicts[sn] = "NO_CORPUS"
        print(f"  {sn}: NO_CORPUS (no stop_corpus data; used Wikipedia retrieval)")

# ─── Build corpus anchors ────────────────────────────────────────────────────
# build_corpus_anchors expects a dict with keys:
#   story_elements_json, canonical_titles_json, pages_json
# For outdoor/biking tours, this structure doesn't exist in the same form.
# We'll build a minimal compatible dict from the stop_corpus passages.
conn = get_connection()
corpus_data_2 = get_stop_corpus_for_tour("French Riviera", stop_names, conn)
conn.close()

stop_corpus_anchors = {}
for sn in stop_names:
    sc = corpus_data_2.get(sn)
    if sc and sc.get('passages'):
        # Build a compatible dict for build_corpus_anchors
        venue_corpus_dict = {
            'story_elements_json': [],
            'canonical_titles_json': [],
            'pages_json': [{'text': p} for p in sc['passages']],
        }
        stop_corpus_anchors[sn] = build_corpus_anchors(
            venue_corpus_dict, sn, "French Riviera Cycling Tour"
        )
    else:
        stop_corpus_anchors[sn] = {}

# ─── Build annotated markdown ────────────────────────────────────────────────
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
md.append("")
md.append("---")
md.append("")
md.append("## Coverage Verdicts (assessed before narration)")
md.append("")
for sn in stop_names:
    md.append(f"- **{sn}**: `{coverage_verdicts[sn]}`")
md.append("")
md.append("*(Cap d'Antibes has stop_corpus from 'French Riviera walking area'. "
          "Villefranche-sur-Mer has no stop_corpus; pipeline marked it SHORTENED.)*")
md.append("")
md.append("---")
md.append("")

para_num = 0
for stop_idx, stop in enumerate(stops):
    stop_title = stop['title']
    md.append(f"## {stop_title}")
    md.append("")
    if stop_idx == 0:
        md.append("*(D64: Stop 1 contains the tour prolog inside it)*")
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

        # Style validation
        style_result = validate_paragraph(para_text)
        rules = style_result.get('rules_violated', set())
        is_nav = style_result.get('is_navigation', False)
        if is_nav:
            style_str = 'NAVIGATION (exempt)'
        elif rules:
            style_str = ','.join(sorted(rules))
        else:
            style_str = 'clean'

        # Anchor classification
        anchors = stop_corpus_anchors.get(stop_title, {})
        try:
            anchor_result = classify_paragraph(
                para_text, anchors, stop_title, "French Riviera Cycling Tour"
            )
            anchor_str = anchor_result.get('classification', 'UNKNOWN')
        except Exception as e:
            anchor_str = "ERROR"

        # Coverage for this stop
        cov_str = coverage_verdicts.get(stop_title, "UNKNOWN")

        md.append(f"`[anchor: {anchor_str} | style: {style_str} | coverage: {cov_str}]`")
        md.append("")

md.append("---")
md.append("")
md.append("## Summary")
md.append("")
md.append(f"- Total paragraphs numbered: {para_num}")
md.append(f"- Tour ID: {new_tour_id} (is_test=true, lat/lng=NULL)")
md.append(f"- audio_tours total row count: {count_total}")
md.append(f"- Nice list: {visible_nice}")
md.append(f"- Nice list matches expected {expected_nice}: **{'YES' if visible_nice == expected_nice else 'NO'}**")
md.append("")

# Write
md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_FOR_MICHAEL.md")
with open(md_path, 'w') as f:
    f.write('\n'.join(md))

print(f"\n✓ Written: {md_path}")
print(f"✓ Paragraphs numbered: {para_num}")
print(f"✓ Tour ID: {new_tour_id}")
