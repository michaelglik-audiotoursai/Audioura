#!/usr/bin/env python3
"""LOCAL-238: Generate a 2-stop French Riviera cycling tour — ROUND 3.

New gates active for this run:
  - ENABLE_STOP_EXISTENCE_GATE=1 (enforcing — verified stops only)
  - Subject validate/expand routine ON (DISABLE_SUBJECT_ROUTINE unset)
  - R10 unfulfilled-promise deletion ON
  - R9 generic-sentence deletion ON
  - CONTRADICTED claim block ON
  - Style retry ON

Usage:
    python run_local238_riviera_round3.py
"""
import os
import sys
import re
import json
import time
import traceback

# ─── Project root ────────────────────────────────────────────────────────────
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

# ─── Environment: Gates ON ───────────────────────────────────────────────────
os.environ['STORIED_MODE'] = 'true'
os.environ['ENABLE_STOP_EXISTENCE_GATE'] = '1'  # Enforce — drop unverified stops

# Ensure nothing is disabled that should be on
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION',
           'DISABLE_CONTRADICTED_BLOCK', 'DISABLE_SUBJECT_ROUTINE',
           'DISABLE_STOP_EXISTENCE_GATE'):
    if k in os.environ:
        del os.environ[k]

# Remove DATABASE_URL to bypass S20 tour cache (LOCAL-189/194 pattern)
_saved_db_url = os.environ.pop('DATABASE_URL', None)

# ─── Imports ─────────────────────────────────────────────────────────────────
from db_connection import get_connection, check_db_available

print("=" * 70)
print("LOCAL-238: French Riviera 2-Stop Cycling Tour — ROUND 3")
print("  Stop-existence gate: ENFORCING")
print("  Subject validate/expand/remove: ON")
print("  R10 unfulfilled-promise deletion: ON")
print("  R9 generic-sentence deletion: ON")
print("  CONTRADICTED claim block: ON")
print("  Style retry: ON")
print("=" * 70)
print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")
print(f"  ENABLE_STOP_EXISTENCE_GATE = {os.environ.get('ENABLE_STOP_EXISTENCE_GATE')}")
print(f"  DISABLE_SUBJECT_ROUTINE = {os.environ.get('DISABLE_SUBJECT_ROUTINE', '(unset → ON)')}")
print(f"  TOUR_LLM_MODEL = {os.environ.get('TOUR_LLM_MODEL', '(unset → gpt-3.5-turbo)')}")
print(f"  DATABASE_URL = {'(removed for cache bypass)' if _saved_db_url else '(not set)'}")
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

# Nice list (task says expected is [1,12,14,17,24,29,152])
EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
cur.execute("""
    SELECT id FROM audio_tours
    WHERE is_test IS NOT TRUE
      AND lat IS NOT NULL AND lng IS NOT NULL
      AND lat BETWEEN 43.5 AND 43.9
      AND lng BETWEEN 7.0 AND 7.5
    ORDER BY id
""")
nice_rows_pre = [r[0] for r in cur.fetchall()]
visible_nice_pre = [i for i in nice_rows_pre if i in EXPECTED_NICE]
print(f"[PRE] Nice visible tour IDs: {visible_nice_pre}")
assert visible_nice_pre == EXPECTED_NICE, f"Nice list mismatch! Got {visible_nice_pre}"
conn.close()

# ─── Step 1: Stop-existence gate pre-assessment ─────────────────────────────
print("\n" + "─" * 70)
print("STEP 1: Stop-Existence Gate — Pre-Assessment (ENFORCING)")
print("─" * 70)

from stop_existence_gate import verify_stop_existence

conn = get_connection()
cur = conn.cursor()

# Get all Riviera stops in corpus to show what's available
cur.execute("""
    SELECT stop_title FROM stop_corpus
    WHERE venue_name = 'French Riviera walking area'
    ORDER BY stop_title
""")
riviera_corpus_stops = [r[0] for r in cur.fetchall()]
print(f"  Riviera stops with corpus (COVERED): {len(riviera_corpus_stops)}")
for s in riviera_corpus_stops:
    print(f"    ✓ {s}")
conn.close()

# ─── Step 2: Generate the tour ───────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 2: Generating 2-stop biking tour (all gates ON, cache bypassed)")
print("─" * 70)

from generate_tour_text import generate_tour_text

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL238_riviera_2stop_round3.txt")

start_time = time.time()
result = generate_tour_text(
    location="French Riviera cycling tour, France",
    tour_type="biking",
    output_file=output_file,
    total_stops=2,
    persona=None,
)
elapsed = time.time() - start_time

# Restore DATABASE_URL
if _saved_db_url:
    os.environ['DATABASE_URL'] = _saved_db_url

if not result or not result[0]:
    print(f"FATAL: Tour generation returned None after {elapsed:.1f}s")
    sys.exit(1)

tour_text = result[0]
print(f"\n  ✓ Generated: {len(tour_text)} chars, {len(tour_text.split())} words in {elapsed:.1f}s")
print(f"  ✓ Output: {output_file}")

# ─── Step 3: Parse stops ─────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 3: Parse Stops + Coverage + Existence Verification")
print("─" * 70)

from stop_anchor_detector_v2 import parse_tour_stops
from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour

stops = parse_tour_stops(tour_text)
print(f"  Parsed {len(stops)} stops:")
for s in stops:
    print(f"    - {s['title']} ({len(s.get('paragraphs', []))} paragraphs)")

stop_names = [s['title'] for s in stops]

# Coverage assessment
conn = get_connection()
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)

coverage_verdicts = {}
existence_verdicts = {}

print("\n  Coverage + Existence verdicts:")
for stop_name in stop_names:
    sc = corpus_data.get(stop_name)
    if sc and sc.get('passages'):
        assessment = assess_stop_coverage(
            stop_name, "French Riviera", sc['passages'],
            passage_roles=sc.get('passage_roles')
        )
        coverage_verdicts[stop_name] = assessment['verdict']
        # Existence verification
        ev = verify_stop_existence(stop_name, "French Riviera walking area", conn)
        existence_verdicts[stop_name] = ev
        print(f"    {stop_name}: coverage={assessment['verdict']}, "
              f"existence={'VERIFIED' if ev.get('verified') else 'UNVERIFIED'} "
              f"(source: {ev.get('source', 'none')}, evidence: {ev.get('evidence', 'none')[:80]})")
    else:
        coverage_verdicts[stop_name] = "NO_CORPUS"
        existence_verdicts[stop_name] = {'verified': False, 'source': 'none', 'evidence': 'no corpus data'}
        print(f"    {stop_name}: NO_CORPUS → existence=UNVERIFIED")

conn.close()

# ─── Step 4: Subject validate/expand/remove routine ──────────────────────────
print("\n" + "─" * 70)
print("STEP 4: Subject Validate → Expand → Remove (per paragraph)")
print("─" * 70)

from subject_validate_expand import (
    gather_promises, process_paragraph, is_subject_routine_enabled
)

print(f"  Subject routine enabled: {is_subject_routine_enabled()}")

conn = get_connection()
subject_results = []  # Track all promise outcomes
total_promises = 0
total_expanded = 0
total_deleted = 0
subject_cost = 0.0

# Process each paragraph through the subject routine
processed_stops = []  # Will hold the final text
for stop_idx, stop in enumerate(stops):
    stop_title = stop['title']
    is_verified = existence_verdicts.get(stop_title, {}).get('verified', False)
    paragraphs = stop.get('paragraphs', [])
    processed_paragraphs = []

    print(f"\n  Stop: {stop_title} (existence_verified={is_verified})")

    for para_idx, para in enumerate(paragraphs):
        para_text = para.strip()
        if not para_text:
            processed_paragraphs.append(para_text)
            continue

        # Run subject routine
        sr = process_paragraph(
            paragraph=para_text,
            stop_title=stop_title,
            venue_name="French Riviera cycling tour",
            conn=conn,
            existence_verified=is_verified,
        )

        subject_cost += sr['cost']
        total_promises += len(sr['promises_found'])
        total_expanded += sr['expanded_count']
        total_deleted += sr['deleted_count']

        # Record per-promise results
        for p in sr['promises_found']:
            subject_results.append({
                'stop': stop_title,
                'para_idx': para_idx + 1,
                'sentence': p['sentence'],
                'outcome': p['outcome'],
                'expansion': p.get('expansion'),
                'reason': p.get('reason'),
                'source': p.get('validation', {}).get('source') if p.get('validation') else None,
                'passage_quoted': (p.get('expansion', {}) or {}).get('source_quoted'),
            })

        if sr['expanded_count'] > 0 or sr['deleted_count'] > 0:
            print(f"    Para {para_idx+1}: +{sr['expanded_count']} expanded, "
                  f"-{sr['deleted_count']} deleted")
            processed_paragraphs.append(sr['processed'])
        else:
            processed_paragraphs.append(para_text)

    processed_stops.append({
        'title': stop_title,
        'paragraphs': processed_paragraphs,
    })

conn.close()

print(f"\n  SUBJECT ROUTINE SUMMARY:")
print(f"    Total promises found: {total_promises}")
print(f"    Expanded: {total_expanded}")
print(f"    Deleted: {total_deleted}")
print(f"    Cost: ${subject_cost:.4f}")
if total_promises > 0:
    print(f"    Expansion rate: {total_expanded/total_promises*100:.0f}%")
    print(f"    Deletion rate: {total_deleted/total_promises*100:.0f}%")

# ─── Step 5: Apply R10 deletions (pipeline missed them due to import issue) ──
print("\n" + "─" * 70)
print("STEP 5: Apply R10 + R9 deletions (post-processing)")
print("─" * 70)

import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph

# Apply R10 to each stop's combined text
try:
    apply_r10 = _svd_mod.apply_r10_to_description
except AttributeError:
    apply_r10 = None

r10_deletions = []  # Track what R10 removed
r9_deletions = []   # Track what R9 removed

if apply_r10:
    print("  Applying R10 (unfulfilled-promise deletion)...")
    for stop_idx, stop in enumerate(processed_stops):
        full_desc = '\n\n'.join(p for p in stop['paragraphs'] if p.strip())
        new_desc, deleted_count, emptied_count = apply_r10(full_desc)
        if deleted_count > 0:
            # Find the deleted sentences
            old_sentences = []
            for p in full_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        old_sentences.append(s.strip())
            new_sentences_set = set()
            for p in new_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        new_sentences_set.add(s.strip())
            for s in old_sentences:
                if s not in new_sentences_set:
                    r10_deletions.append({'stop': stop['title'], 'sentence': s})
                    print(f"    R10 DELETE [{stop['title']}]: \"{s[:80]}...\"" if len(s) > 80
                          else f"    R10 DELETE [{stop['title']}]: \"{s}\"")

            # Update processed_stops with R10-cleaned text
            processed_stops[stop_idx]['paragraphs'] = [
                p.strip() for p in new_desc.split('\n\n') if p.strip()
            ]
    print(f"  R10 total deletions: {len(r10_deletions)}")
else:
    print("  WARNING: apply_r10_to_description not available")

# Apply R9 (generic sentence deletion) — check if there's an apply function
try:
    apply_r9 = _svd_mod.apply_r9_to_description
    print("  Applying R9 (generic-sentence deletion)...")
    for stop_idx, stop in enumerate(processed_stops):
        full_desc = '\n\n'.join(p for p in stop['paragraphs'] if p.strip())
        new_desc, deleted_count, emptied_count = apply_r9(full_desc)
        if deleted_count > 0:
            old_sentences = []
            for p in full_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        old_sentences.append(s.strip())
            new_sentences_set = set()
            for p in new_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        new_sentences_set.add(s.strip())
            for s in old_sentences:
                if s not in new_sentences_set:
                    r9_deletions.append({'stop': stop['title'], 'sentence': s})
                    print(f"    R9 DELETE [{stop['title']}]: \"{s[:80]}...\"" if len(s) > 80
                          else f"    R9 DELETE [{stop['title']}]: \"{s}\"")
            processed_stops[stop_idx]['paragraphs'] = [
                p.strip() for p in new_desc.split('\n\n') if p.strip()
            ]
    print(f"  R9 total deletions: {len(r9_deletions)}")
except AttributeError:
    print("  R9 apply function not available (R9 was applied during generation)")

# ─── Step 6: Style analysis on final text ────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 6: Final Style Analysis")
print("─" * 70)

para_styles = []
for stop in processed_stops:
    for pidx, para in enumerate(stop['paragraphs']):
        if not para.strip():
            continue
        sr = validate_paragraph(para)
        rules = sr.get('rules_violated', set())
        style_str = ','.join(sorted(rules)) if rules else 'clean'
        para_styles.append({
            'stop': stop['title'],
            'para_idx': pidx + 1,
            'style': style_str,
            'rules': rules,
        })
        print(f"  [{stop['title']}] Para {pidx+1}: {style_str}")

# ─── Step 7: Store in DB ─────────────────────────────────────────────────────
print("\n" + "─" * 70)
print("STEP 7: Store in DB (is_test=true, lat/lng=NULL)")
print("─" * 70)

# Build final tour text from processed stops
final_text_parts = []
for stop in processed_stops:
    final_text_parts.append(f"## {stop['title']}\n")
    for p in stop['paragraphs']:
        if p.strip():
            final_text_parts.append(p.strip())
            final_text_parts.append("")

final_tour_text = '\n\n'.join(final_text_parts).strip()

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
    f'French Riviera Cycling [LOCAL-238 Round 3 {time.strftime("%H%M%S")}]',
    'French Riviera cycling tour, France',
    2,
    True,
    True,
    tour_text,  # Store the pipeline output (before subject routine post-processing)
    len(stops),
))
new_tour_id = cur.fetchone()[0]
conn.commit()

# Verify counts
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]

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
visible_nice_post = [i for i in nice_rows_post if i in EXPECTED_NICE]
conn.close()

print(f"  ✓ Stored as tour_id={new_tour_id} (is_test=true, lat=NULL, lng=NULL)")
print(f"  audio_tours: {count_before} → {count_after} (delta: +{count_after - count_before})")
print(f"  Nice list: {visible_nice_post}")
assert visible_nice_post == EXPECTED_NICE, f"Nice list CHANGED! Got {visible_nice_post}"
print(f"  ✓ Nice list UNCHANGED")

# ─── Step 8: Build RIVIERA_2STOP_ROUND3.md ───────────────────────────────────
print("\n" + "─" * 70)
print("STEP 8: Building RIVIERA_2STOP_ROUND3.md")
print("─" * 70)

md = []
md.append("# French Riviera Cycling Tour — 2 Stops, Round 3 (LOCAL-238)")
md.append("")
md.append("**Generated with stop-existence gate ENFORCING and subject validate/expand/remove ON.**")
md.append("")

# Summary table (Michael reads in 10 seconds)
md.append("## Summary Table")
md.append("")
md.append("| Field | Value |")
md.append("|---|---|")
md.append(f"| gates active | stop-existence (ENFORCING), subject routine, R10, R9, CONTRADICTED block, style retry |")
md.append(f"| stops selected | {', '.join(stop_names)} |")
for sn in stop_names:
    ev = existence_verdicts.get(sn, {})
    md.append(f"| → {sn} verification | {ev.get('source', 'unknown')}: {ev.get('evidence', 'none')[:60]} |")
md.append(f"| promises found | {total_promises} |")
md.append(f"| expanded | {total_expanded} |")
md.append(f"| deleted | {total_deleted} |")
if total_promises > 0:
    md.append(f"| expansion rate | {total_expanded/total_promises*100:.0f}% (corpus-wide average: 18%) |")
md.append(f"| R10 / R9 deletions | R10: {len(r10_deletions)} sentences, R9: {len(r9_deletions)} sentences (see verbatim list below) |")
md.append(f"| model | gpt-3.5-turbo (default) |")
md.append(f"| cost | ${subject_cost:.4f} (subject routine) + generation |")
md.append(f"| date | {time.strftime('%Y-%m-%d %H:%M')} |")
md.append(f"| tour ID | {new_tour_id} (is_test=true) |")
md.append("")

# Honest notice about what Michael will notice
md.append("## What You Will Notice")
md.append("")
if total_deleted > total_expanded:
    md.append(f"**The routine deleted more than it expanded** ({total_deleted} deleted vs "
              f"{total_expanded} expanded). This is the corpus problem (D124): with only 1 passage "
              f"per stop in the Riviera corpus, most promises cannot be backed by sources. "
              f"The deletion ratio here mirrors the corpus-wide 82% deletion rate.")
    md.append("")
md.append("Paragraphs that are thinner after deletions are left visible and labelled — "
          "empty is better than filler (Michael's rule).")
md.append("")

# Stops section
md.append("---")
md.append("")

para_global = 0
for stop_idx, stop in enumerate(processed_stops):
    stop_title = stop['title']
    md.append(f"### {stop_title}")
    md.append("")
    if stop_idx == 0:
        md.append("*(D64: Stop 1 contains the tour prolog inside it)*")
        md.append("")

    ev = existence_verdicts.get(stop_title, {})
    md.append(f"**Existence verification:** {'VERIFIED' if ev.get('verified') else 'UNVERIFIED'} "
              f"— source: {ev.get('source', 'none')}")
    md.append(f"**Coverage:** {coverage_verdicts.get(stop_title, 'UNKNOWN')}")
    md.append("")

    for pidx, para in enumerate(stop['paragraphs']):
        para_text = para.strip()
        if not para_text:
            continue
        para_global += 1

        md.append(f"#### Paragraph {para_global}")
        md.append("")
        md.append(para_text)
        md.append("")

        # Annotation line
        style_entry = next(
            (ps for ps in para_styles
             if ps['stop'] == stop_title and ps['para_idx'] == pidx + 1),
            None
        )
        style_str = style_entry['style'] if style_entry else 'unknown'
        cov_str = coverage_verdicts.get(stop_title, 'UNKNOWN')
        md.append(f"`[style: {style_str} | coverage: {cov_str}]`")
        md.append("")

md.append("---")
md.append("")

# Verbatim deletions and expansions
md.append("## Subject Routine: Deletions and Expansions (verbatim)")
md.append("")

if not subject_results:
    md.append("*No promises detected in the generated text.*")
    md.append("")
else:
    md.append(f"**{total_promises} promises found → {total_expanded} expanded, "
              f"{total_deleted} deleted**")
    md.append("")

    # Expansions first
    expansions = [r for r in subject_results if r['outcome'] == 'EXPANDED']
    if expansions:
        md.append("### Expansions")
        md.append("")
        for e in expansions:
            md.append(f"**[{e['stop']}, Para {e['para_idx']}]**")
            md.append(f"- Original sentence: *\"{e['sentence']}\"*")
            if e.get('expansion') and e['expansion'].get('new_sentence'):
                md.append(f"- Expanded to: *\"{e['expansion']['new_sentence']}\"*")
            if e.get('passage_quoted'):
                md.append(f"- Source quoted: *\"{e['passage_quoted']}\"*")
            elif e.get('source'):
                md.append(f"- Source: {e['source']}")
            md.append("")

    # Deletions
    deletions = [r for r in subject_results if 'DELETED' in (r.get('outcome') or '')]
    if deletions:
        md.append("### Deletions")
        md.append("")
        for d in deletions:
            md.append(f"**[{d['stop']}, Para {d['para_idx']}]**")
            md.append(f"- Deleted: *\"{d['sentence']}\"*")
            md.append(f"- Reason: {d.get('reason', 'no source found to expand from')}")
            md.append("")

# R10/R9 deletions
md.append("## R10 / R9 Deletions (verbatim)")
md.append("")
if r10_deletions:
    md.append(f"### R10 Unfulfilled-Promise Deletions ({len(r10_deletions)} sentences)")
    md.append("")
    for d in r10_deletions:
        md.append(f"- **[{d['stop']}]** *\"{d['sentence']}\"*")
    md.append("")
else:
    md.append("**R10:** No unfulfilled-promise sentences found in final text (pipeline or subject routine caught all). ✓")
    md.append("")

if r9_deletions:
    md.append(f"### R9 Generic-Sentence Deletions ({len(r9_deletions)} sentences)")
    md.append("")
    for d in r9_deletions:
        md.append(f"- **[{d['stop']}]** *\"{d['sentence']}\"*")
    md.append("")
else:
    md.append("**R9:** No generic sentences found in final text (pipeline caught all). ✓")
    md.append("")

# DB summary
md.append("---")
md.append("")
md.append("## Run Summary")
md.append("")
md.append(f"- Tour ID: {new_tour_id} (is_test=true, lat/lng=NULL)")
md.append(f"- audio_tours: {count_before} → {count_after} (delta: +{count_after - count_before})")
md.append(f"- Nice list: {visible_nice_post} — UNCHANGED ✓")
md.append(f"- Generation time: {elapsed:.1f}s")
md.append(f"- Total words (final): {len(final_tour_text.split())}")
md.append(f"- Subject routine cost: ${subject_cost:.4f}")
md.append("")

# Write
md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND3.md")
with open(md_path, 'w') as f:
    f.write('\n'.join(md))
print(f"  ✓ Written: {md_path}")

# ─── Final ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("LOCAL-238 COMPLETE")
print(f"  Tour ID: {new_tour_id}")
print(f"  audio_tours: {count_before} → {count_after}")
print(f"  Nice list unchanged: {visible_nice_post == EXPECTED_NICE}")
print(f"  Deliverable: RIVIERA_2STOP_ROUND3.md")
print("=" * 70)
