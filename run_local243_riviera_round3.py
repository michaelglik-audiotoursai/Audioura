#!/usr/bin/env python3
"""LOCAL-243: End-to-end French Riviera 2-stop — R10 IN-PIPELINE verification.

The same generation as LOCAL-241, but this time PHASE 5.155 (R10) should
actually run INSIDE generate_tour_text because LEAD fixed the shim at
tests/style_validator_detector.py to forward all names dynamically.

KEY DIFFERENCE from LOCAL-241's script:
  - We do NOT apply R10 in post-processing.
  - R10 runs in-pipeline (PHASE 5.155) or not at all.
  - We capture stdout to verify PHASE 5.155 logged its execution.
"""
import os
import sys
import re
import io
import json
import time
import traceback

# --- Project root ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# --- Load .env for API keys (never hardcode) ---
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

# --- Environment: ALL GATES ON ---
os.environ['STORIED_MODE'] = 'true'
os.environ['ENABLE_STOP_EXISTENCE_GATE'] = '1'

# Remove any disable flags — all gates live
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION', 'DISABLE_R10_DELETION',
           'DISABLE_CONTRADICTED_BLOCK', 'DISABLE_SUBJECT_ROUTINE',
           'DISABLE_STOP_EXISTENCE_GATE'):
    if k in os.environ:
        del os.environ[k]

# Remove DATABASE_URL to bypass S20 tour cache (forces fresh generation)
_saved_db_url = os.environ.pop('DATABASE_URL', None)

# --- Imports ---
from db_connection import get_connection, check_db_available

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]

print("=" * 70)
print("LOCAL-243: French Riviera 2-Stop — R10 IN-PIPELINE VERIFICATION")
print("  All gates live: existence, subject routine, R10, R9, CONTRADICTED, style retry")
print("  Cache BYPASSED (DATABASE_URL removed)")
print("  Model: gpt-3.5-turbo (default, TOUR_LLM_MODEL unset)")
print("  PURPOSE: Verify PHASE 5.155 runs inside the generation loop")
print("=" * 70)

# --- Step 0: Pre-checks ---
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

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

# --- Step 1: Generate tour (fresh LLM call) with stdout capture ---
print("\n" + "-" * 70)
print("STEP 1: Generating 2-stop biking tour (all gates ON, capturing output)")
print("-" * 70)

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL243_riviera_2stop_round3.txt")

# Capture stdout during generation to find PHASE 5.155 log lines
_orig_stdout = sys.stdout
_captured = io.StringIO()

class TeeWriter:
    """Write to both captured buffer and original stdout."""
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
        total_stops=2,
        persona=None,
    )
except Exception as e:
    sys.stdout = _orig_stdout
    elapsed = time.time() - start_time
    print(f"FATAL: Generation failed after {elapsed:.1f}s: {e}")
    traceback.print_exc()
    # Restore original doc unchanged with failure note
    md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND3.md")
    with open(md_path, 'r') as f:
        original_content = f.read()
    with open(md_path, 'w') as f:
        f.write(f"**LOCAL-243 attempted {time.strftime('%Y-%m-%d %H:%M')} "
                f"— generation failed: {e}**\n\n{original_content}")
    sys.exit(1)

sys.stdout = _orig_stdout
elapsed = time.time() - start_time
gen_log = _captured.getvalue()

if not result or not result[0]:
    print(f"FATAL: Tour generation returned None after {elapsed:.1f}s")
    md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND3.md")
    with open(md_path, 'r') as f:
        original_content = f.read()
    with open(md_path, 'w') as f:
        f.write(f"**LOCAL-243 attempted {time.strftime('%Y-%m-%d %H:%M')} "
                f"— generation returned None**\n\n{original_content}")
    sys.exit(1)

tour_text = result[0]
from generate_tour_text import _LAST_GENERATION_COST
gen_cost = _LAST_GENERATION_COST.copy()
print(f"\n  Generated: {len(tour_text)} chars, {len(tour_text.split())} words in {elapsed:.1f}s")
print(f"  Cost: ${gen_cost.get('total_cost', 0):.4f}")
print(f"  Tokens: {gen_cost.get('total_tokens', 0)}")
print(f"  Cache hit: {gen_cost.get('cache_hit', False)}")

# Restore DATABASE_URL for DB operations
if _saved_db_url:
    os.environ['DATABASE_URL'] = _saved_db_url

# --- Step 1b: Analyze PHASE 5.155 log output ---
print("\n" + "-" * 70)
print("STEP 1b: PHASE 5.155 (R10 in-pipeline) — LOG ANALYSIS")
print("-" * 70)

r10_in_pipeline = False
r10_pipeline_deleted = 0
r10_pipeline_error = None
r10_pipeline_log_lines = []

for line in gen_log.split('\n'):
    if 'PHASE 5.155' in line or ('LOCAL-235' in line and 'R10' in line):
        r10_pipeline_log_lines.append(line.strip())
    if 'PHASE 5.155: R10 unfulfilled-promise deletion' in line:
        r10_in_pipeline = True
    if 'R10 NOT APPLIED' in line or 'ERROR' in line and 'R10' in line:
        r10_pipeline_error = line.strip()
    if 'R10 summary:' in line:
        m = re.search(r'(\d+) sentences? deleted', line)
        if m:
            r10_pipeline_deleted = int(m.group(1))

print(f"  R10 in-pipeline attempted: {r10_in_pipeline}")
print(f"  R10 in-pipeline error: {r10_pipeline_error}")
print(f"  R10 in-pipeline deletions: {r10_pipeline_deleted}")
print(f"  R10 log lines:")
for line in r10_pipeline_log_lines:
    print(f"    {line}")

if not r10_in_pipeline:
    print("\n  *** WARNING: PHASE 5.155 did NOT appear in the log! ***")
    # Check if disabled
    if 'DISABLE_R10_DELETION' in gen_log:
        print("  Reason: R10 was disabled by environment variable")
    elif 'R10 NOT APPLIED' in gen_log:
        print("  Reason: Import failed (check error above)")
    else:
        print("  Reason: Unknown — PHASE 5.155 section may not have been reached")

# --- Step 2: Parse stops + verify existence ---
print("\n" + "-" * 70)
print("STEP 2: Parse Stops + Existence Verification")
print("-" * 70)

from stop_anchor_detector_v2 import parse_tour_stops
from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour
from stop_existence_gate import verify_stop_existence, _classify_venue_kind

stops = parse_tour_stops(tour_text)
print(f"  Parsed {len(stops)} stops:")
for s in stops:
    print(f"    - {s['title']} ({len(s.get('paragraphs', []))} paragraphs)")

stop_names = [s['title'] for s in stops]

conn = get_connection()
corpus_data = get_stop_corpus_for_tour("French Riviera", stop_names, conn)

coverage_verdicts = {}
existence_verdicts = {}

for stop_name in stop_names:
    sc = corpus_data.get(stop_name)
    if sc and sc.get('passages'):
        assessment = assess_stop_coverage(
            stop_name, "French Riviera", sc['passages'],
            passage_roles=sc.get('passage_roles')
        )
        coverage_verdicts[stop_name] = assessment['verdict']
    else:
        coverage_verdicts[stop_name] = "NO_CORPUS"

    ev = verify_stop_existence(stop_name, "French Riviera walking area", conn)
    existence_verdicts[stop_name] = ev
    status = 'VERIFIED' if ev.get('verified') else 'UNVERIFIED'
    print(f"    {stop_name}: coverage={coverage_verdicts[stop_name]}, "
          f"existence={status} (kind={ev.get('venue_kind')})")
conn.close()

# --- Step 3: Subject validate/expand/remove ---
print("\n" + "-" * 70)
print("STEP 3: Subject Validate -> Expand -> Remove")
print("-" * 70)

from subject_validate_expand import process_paragraph, is_subject_routine_enabled
print(f"  Subject routine enabled: {is_subject_routine_enabled()}")

conn = get_connection()
subject_results = []
total_promises = 0
total_expanded = 0
total_deleted = 0
subject_cost = 0.0

processed_stops = []
for stop_idx, stop in enumerate(stops):
    stop_title = stop['title']
    is_verified = existence_verdicts.get(stop_title, {}).get('verified', False)
    paragraphs = stop.get('paragraphs', [])
    processed_paragraphs = []

    for para_idx, para in enumerate(paragraphs):
        para_text = para.strip()
        if not para_text:
            processed_paragraphs.append(para_text)
            continue
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

        for p in sr['promises_found']:
            subject_results.append({
                'stop': stop_title,
                'para_idx': para_idx + 1,
                'sentence': p['sentence'],
                'outcome': p['outcome'],
                'expansion': p.get('expansion'),
                'reason': p.get('reason'),
            })

        if sr['expanded_count'] > 0 or sr['deleted_count'] > 0:
            print(f"    [{stop_title}] Para {para_idx+1}: +{sr['expanded_count']} expanded, "
                  f"-{sr['deleted_count']} deleted")
            processed_paragraphs.append(sr['processed'])
        else:
            processed_paragraphs.append(para_text)

    processed_stops.append({'title': stop_title, 'paragraphs': processed_paragraphs})
conn.close()

print(f"\n  SUBJECT ROUTINE: promises={total_promises}, expanded={total_expanded}, "
      f"deleted={total_deleted}, cost=${subject_cost:.4f}")

# --- Step 4: R10/R9 post-processing — SKIPPED (the whole point of LOCAL-243) ---
print("\n" + "-" * 70)
print("STEP 4: R10/R9 post-processing — INTENTIONALLY SKIPPED")
print("  R10 should have run in PHASE 5.155 inside generate_tour_text.")
print("  We do NOT re-apply it here. This is the test.")
print("-" * 70)

# However, we still analyze what R10 WOULD catch to compare
import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph

try:
    apply_r10 = _svd_mod.apply_r10_to_description
except AttributeError:
    apply_r10 = None

# Check what R10 WOULD still catch (residual triggers)
r10_residual_deletions = []
if apply_r10:
    for stop in processed_stops:
        full_desc = '\n\n'.join(p for p in stop['paragraphs'] if p.strip())
        _new_desc, _deleted, _emptied = apply_r10(full_desc)
        if _deleted > 0:
            old_sentences = set()
            for p in full_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        old_sentences.add(s.strip())
            new_sentences_set = set()
            for p in _new_desc.split('\n\n'):
                for s in re.split(r'(?<=[.!?])\s+', p):
                    if s.strip():
                        new_sentences_set.add(s.strip())
            for s in old_sentences:
                if s not in new_sentences_set:
                    r10_residual_deletions.append({'stop': stop['title'], 'sentence': s})

    if r10_residual_deletions:
        print(f"  R10 residual check: {len(r10_residual_deletions)} sentences STILL "
              f"trigger R10 after pipeline processing.")
        print("  (These survived the in-pipeline pass but would be caught by a second pass)")
        for d in r10_residual_deletions:
            print(f"    [{d['stop']}] \"{d['sentence'][:80]}...\"")
    else:
        print("  R10 residual check: 0 sentences trigger R10. Pipeline cleaned everything.")

# --- Step 5: Style analysis of final text ---
print("\n" + "-" * 70)
print("STEP 5: Final Style Analysis")
print("-" * 70)

para_styles = []
for stop in processed_stops:
    for pidx, para in enumerate(stop['paragraphs']):
        if not para.strip():
            continue
        sr = validate_paragraph(para)
        rules = sr.get('rules_violated', set())
        style_str = ','.join(sorted(rules)) if rules else 'clean'
        para_styles.append({'stop': stop['title'], 'para_idx': pidx + 1, 'style': style_str})
        print(f"  [{stop['title']}] Para {pidx+1}: {style_str}")

# --- Step 6: Store in DB ---
print("\n" + "-" * 70)
print("STEP 6: Store in DB (is_test=true, lat/lng=NULL)")
print("-" * 70)

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
    f'French Riviera Cycling [LOCAL-243 Round 3 R10-PIPELINE {time.strftime("%H%M%S")}]',
    'French Riviera cycling tour, France',
    2,
    True,
    True,
    tour_text,
    len(stops),
))
new_tour_id = cur.fetchone()[0]
conn.commit()

cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]

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

print(f"  Stored as tour_id={new_tour_id} (is_test=true, lat=NULL, lng=NULL)")
print(f"  audio_tours: {count_before} -> {count_after} (delta: +{count_after - count_before})")
print(f"  Nice list: {visible_nice_post}")
assert visible_nice_post == EXPECTED_NICE, f"Nice list CHANGED! Got {visible_nice_post}"
print(f"  Nice list UNCHANGED")

# --- Step 7: Build RIVIERA_2STOP_ROUND3.md ---
print("\n" + "-" * 70)
print("STEP 7: Building RIVIERA_2STOP_ROUND3.md")
print("-" * 70)


def _build_riviera_md(**kw):
    """Assemble the markdown document."""
    md = []
    md.append("# French Riviera Cycling Tour - 2 Stops, Round 3 (LOCAL-243)")
    md.append("")
    md.append("**End-to-end regeneration with R10 running IN-PIPELINE (PHASE 5.155).**")
    md.append("")
    md.append(f"> Total words: **{kw['total_words']}** (round 2 was 819).")
    md.append("")

    # Summary table
    md.append("## Summary Table")
    md.append("")
    md.append("| Field | Value |")
    md.append("|---|---|")
    md.append("| gates active | stop-existence (ENFORCING, venue-kind), subject routine, "
              "**R10 (widened LOCAL-240)**, R9, CONTRADICTED block, style retry |")
    md.append(f"| model | gpt-3.5-turbo (default) |")
    md.append(f"| cost | ${kw['total_cost_usd']:.4f} "
              f"(generation ${kw['gen_cost'].get('total_cost',0):.4f} "
              f"+ subject ${kw['subject_cost']:.4f}) |")
    md.append(f"| tokens | {kw['gen_cost'].get('total_tokens', 0)} |")
    md.append(f"| cache hit | {kw['gen_cost'].get('cache_hit', False)} |")
    md.append(f"| venue kind | geographic_area |")
    md.append(f"| stops selected | {', '.join(kw['stop_names'])} |")
    for sn in kw['stop_names']:
        ev = kw['existence_verdicts'].get(sn, {})
        status = 'VERIFIED' if ev.get('verified') else 'UNVERIFIED'
        md.append(f"| -> {sn} | {status} - {ev.get('source', 'none')} |")
    md.append(f"| promises found (subject) | {kw['total_promises']} |")
    md.append(f"| expanded | {kw['total_expanded']} |")
    md.append(f"| deleted (subject) | {kw['total_deleted']} |")
    md.append(f"| **R10 in-pipeline deletions** | **{kw['r10_pipeline_deleted']}** |")
    md.append(f"| **R10 ran where** | **{kw['r10_status']}** |")
    md.append(f"| R10 residual (post-pipeline) | {len(kw['r10_residual_deletions'])} |")
    md.append(f"| generation time | {kw['elapsed']:.1f}s |")
    md.append(f"| date | {time.strftime('%Y-%m-%d %H:%M')} |")
    md.append(f"| tour ID | {kw['new_tour_id']} (is_test=true) |")
    md.append("")

    # Word counts
    md.append("## Word Counts")
    md.append("")
    md.append("| Paragraph | Stop | Words |")
    md.append("|---|---|---|")
    for pc in kw['para_word_counts']:
        md.append(f"| P{pc['idx']} | {pc['stop']} | {pc['words']} |")
    md.append(f"| **Total** | | **{kw['total_words']}** |")
    md.append(f"| Round 2 | | 819 |")
    md.append("")

    # Four-way comparison
    md.append("## Four-Way Word Count Comparison")
    md.append("")
    md.append("```")
    md.append(f"{'Run':<30} {'Words':>8}   {'R10 position'}")
    md.append(f"{'-'*30} {'-'*8}   {'-'*20}")
    md.append(f"{'Round 2':<30} {'819':>8}   (no R10)")
    md.append(f"{'LOCAL-240 re-applied':<30} {'191':>8}   (R10 on old text)")
    md.append(f"{'LOCAL-241 end-to-end':<30} {'393':>8}   (R10 post-processing)")
    md.append(f"{'LOCAL-243 (this run)':<30} {str(kw['total_words']):>8}   (R10 in-pipeline)")
    md.append("```")
    md.append("")
    # Comparison note
    diff_from_241 = kw['total_words'] - 393
    if abs(diff_from_241) < 50:
        md.append(f"**Finding:** {kw['total_words']} words vs 393 (LOCAL-241). "
                  f"Delta is {diff_from_241:+d} — close enough to suggest R10's position "
                  f"in the pipeline (in-loop vs post-processing) does not materially change "
                  f"the output length. The LLM's text varies between runs regardless.")
    elif kw['total_words'] < 393:
        md.append(f"**Finding:** {kw['total_words']} words vs 393 (LOCAL-241). "
                  f"Delta is {diff_from_241:+d} — R10 running in-pipeline produces shorter "
                  f"output, likely because deletions occur before later paragraphs are "
                  f"generated (the LLM sees shorter preceding context).")
    else:
        md.append(f"**Finding:** {kw['total_words']} words vs 393 (LOCAL-241). "
                  f"Delta is {diff_from_241:+d} — R10 running in-pipeline produces longer "
                  f"output. This could be LLM variance or a different interaction between "
                  f"R10-in-loop and style retry.")
    md.append("")

    md.append("---")
    md.append("")

    # The tour text
    md.append("## End-to-End Tour (generated text after all gates)")
    md.append("")

    para_global_idx = 0
    for stop_idx, stop in enumerate(kw['processed_stops']):
        stop_title = stop['title']
        md.append(f"### {stop_title}")
        md.append("")
        if stop_idx == 0:
            md.append("*(D64: Stop 1 contains the tour prolog)*")
            md.append("")
        ev = kw['existence_verdicts'].get(stop_title, {})
        md.append(f"**Existence:** {'VERIFIED' if ev.get('verified') else 'UNVERIFIED'} "
                  f"({ev.get('venue_kind', 'unknown')})")
        md.append(f"**Coverage:** {kw['coverage_verdicts'].get(stop_title, 'UNKNOWN')}")
        md.append("")

        for pidx, para in enumerate(stop['paragraphs']):
            para_text = para.strip()
            if not para_text:
                continue
            para_global_idx += 1
            wc = len(para_text.split())
            md.append(f"#### Paragraph {para_global_idx} ({wc} words)")
            md.append("")
            md.append(para_text)
            md.append("")
            style_entry = next(
                (ps for ps in kw['para_styles']
                 if ps['stop'] == stop_title and ps['para_idx'] == pidx + 1),
                None
            )
            style_str = style_entry['style'] if style_entry else 'unknown'
            if wc <= 10:
                md.append(f"`[style: {style_str} | NOTE: paragraph reduced to {wc} words]`")
            else:
                md.append(f"`[style: {style_str}]`")
            md.append("")

    md.append("---")
    md.append("")

    # Deletions section
    md.append("## Deletions (verbatim)")
    md.append("")

    # Subject routine
    if kw['subject_results']:
        md.append(f"### Subject Routine ({kw['total_promises']} promises -> "
                  f"{kw['total_expanded']} expanded, {kw['total_deleted']} deleted)")
        md.append("")
        expansions = [r for r in kw['subject_results'] if r['outcome'] == 'EXPANDED']
        if expansions:
            md.append("**Expansions:**")
            md.append("")
            for e in expansions:
                md.append(f"- [{e['stop']}, P{e['para_idx']}] *\"{e['sentence']}\"*")
                if e.get('expansion') and isinstance(e['expansion'], dict):
                    md.append(f"  -> *\"{e['expansion'].get('new_sentence', '')}\"*")
                md.append("")
        deletions_subj = [r for r in kw['subject_results']
                          if 'DELETED' in (r.get('outcome') or '')]
        if deletions_subj:
            md.append("**Deletions:**")
            md.append("")
            for d in deletions_subj:
                md.append(f"- [{d['stop']}, P{d['para_idx']}] *\"{d['sentence']}\"*")
                md.append(f"  Reason: {d.get('reason', 'no source')}")
                md.append("")
    else:
        md.append("### Subject Routine")
        md.append("")
        md.append("No unfulfilled-promise patterns detected.")
        md.append("")

    # R10 — in-pipeline
    md.append(f"### R10 In-Pipeline (PHASE 5.155) — {kw['r10_pipeline_deleted']} deletions")
    md.append("")
    md.append(f"**Status:** {kw['r10_status']}")
    md.append("")
    if kw['r10_pipeline_log_lines']:
        md.append("**Pipeline log lines (verbatim):**")
        md.append("```")
        for line in kw['r10_pipeline_log_lines']:
            md.append(line)
        md.append("```")
        md.append("")

    # R10 residual
    if kw['r10_residual_deletions']:
        md.append(f"### R10 Residual Triggers ({len(kw['r10_residual_deletions'])} sentences)")
        md.append("")
        md.append("These sentences survive the in-pipeline pass but would be caught "
                  "by a second R10 application:")
        md.append("")
        for d in kw['r10_residual_deletions']:
            md.append(f"- **[{d['stop']}]** *\"{d['sentence']}\"*")
        md.append("")

    md.append("---")
    md.append("")

    # Style retry / R10 interaction
    md.append("## Style Retry / R10 Interaction")
    md.append("")
    if kw['r10_in_pipeline'] and not kw.get('r10_pipeline_error'):
        md.append("R10 now runs IN-PIPELINE (PHASE 5.155), between style retry (PHASE 5.1) "
                  "and CONTRADICTED block (PHASE 5.16). This means:")
        md.append("")
        md.append("1. LLM generates paragraph")
        md.append("2. Style retry rewrites if R1/R3/R4 violations found")
        md.append("3. R9 deletes generic sentences")
        md.append("4. **R10 deletes unfulfilled-promise sentences** ← runs here now")
        md.append("5. CONTRADICTED block removes disproven claims")
        md.append("6. Subject routine expands/removes promises (post-gen)")
        md.append("")
        md.append(f"R10 deleted {kw['r10_pipeline_deleted']} sentence(s) in-pipeline. ")
        if kw['r10_residual_deletions']:
            md.append(f"However, {len(kw['r10_residual_deletions'])} sentence(s) still "
                      f"trigger R10 after subject routine processing — the subject routine "
                      f"may introduce new text that R10 would catch, or sentence splitting "
                      f"differences between in-pipeline and post-hoc application cause gaps.")
        else:
            md.append("No residual R10 triggers remain after the full pipeline — the "
                      "in-pipeline position caught everything.")
    else:
        md.append("**PHASE 5.155 (in-pipeline R10) status:** " + kw['r10_status'])
        md.append("")
        md.append("If R10 failed to run in-pipeline, this means the text was produced "
                  "WITHOUT R10 enforcement during generation. Compare with LOCAL-241 "
                  "(which also ran R10 only in post-processing) to assess the difference.")
    md.append("")

    md.append("---")
    md.append("")

    # Section 2: preserved old comparison
    md.append("## Section 2: Same Rule, Old Text (LOCAL-240 re-application, preserved)")
    md.append("")
    md.append("The previous RIVIERA_2STOP_ROUND3.md applied widened R10 to text generated "
              "BEFORE R10 existed. That produced 8 deletions and a 191-word tour. "
              "This section preserves that result for comparison.")
    md.append("")
    md.append("| Paragraph | Words |")
    md.append("|---|---|")
    md.append("| P1 | 5 |")
    md.append("| P2 | 56 |")
    md.append("| P3 | 107 |")
    md.append("| P4 | 8 |")
    md.append("| P5 | 7 |")
    md.append("| P6 | 8 |")
    md.append("| **Total** | **191** |")
    md.append("| Round 2 | 819 |")
    md.append("")
    md.append("### R10 deletions on old text (8 sentences, verbatim)")
    md.append("")
    md.append('1. *"You are about to embark on a journey through the French Riviera, where the '
              'sun-drenched coasts and ancient villages hold a tapestry woven with the glamour of '
              'modern allure and whispers of medieval roots."*')
    md.append('2. *"Cycling through winding paths, you\'ll discover a blend of architectural '
              'marvels and forgotten tales that shape its identity."*')
    md.append('3. *"The ancient fortifications of the Garoupe Lighthouse stand sentinel against '
              'opulent villas, revealing a juxtaposition of past and present."*')
    md.append('4. *"Discover how the idyllic beauty of the French Riviera masks the secrets of '
              'its past as you unravel its intricate story through each chapter of this '
              'enchanting journey."*')
    md.append('5. *"As you wander through the exotic Jardin Exotique d\'Eze, panoramic views '
              'whisper tales of ancient Provencal nobility and their long-lost gardens."*')
    md.append('6. *"Cap d\'Antibes, with its rich tapestry of landscapes and stories, serves as '
              'a window into the enduring charm of the Cote d\'Azur."*')
    md.append('7. *"The crisp sea air carries whispers of history, mingling with the '
              'contemporary pulse of yachting harbors and bustling town life."*')
    md.append('8. *"The ancient fortifications of the Garoupe Lighthouse, a sentinel of bygone '
              'eras, starkly contrast with the opulent villas that line the coastline, '
              'symbolizing the enduring allure of this coastal haven."*')
    md.append("")
    md.append("**Difference:** Deleting from old prose (written without awareness of R10) "
              "produced 191 words with 4 of 6 paragraphs reduced to a single line. A fresh "
              "generation under R10 produces the text above.")
    md.append("")

    md.append("---")
    md.append("")
    md.append("## Run Summary")
    md.append("")
    md.append(f"- Tour ID: {kw['new_tour_id']} (is_test=true, lat/lng=NULL)")
    md.append(f"- audio_tours: {kw['count_before']} -> {kw['count_after']} "
              f"(delta: +{kw['count_after'] - kw['count_before']})")
    md.append(f"- Nice list: {kw['visible_nice_post']} - UNCHANGED")
    md.append(f"- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)")
    md.append(f"- Total cost: ${kw['total_cost_usd']:.4f}")
    md.append(f"- Generation time: {kw['elapsed']:.1f}s")
    md.append(f"- Total words (final): {kw['total_words']}")
    md.append(f"- Style retry ran during generation (built-in)")
    md.append(f"- R10 in-pipeline: {kw['r10_status']}")
    md.append(f"- R10 residual triggers: {len(kw['r10_residual_deletions'])}")
    md.append("")

    with open(kw['md_path'], 'w') as f:
        f.write('\n'.join(md))

# Compute word counts per paragraph
para_word_counts = []
total_words = 0
para_global_idx = 0
for stop in processed_stops:
    for p in stop['paragraphs']:
        if p.strip():
            para_global_idx += 1
            wc = len(p.split())
            para_word_counts.append({'idx': para_global_idx, 'stop': stop['title'], 'words': wc})
            total_words += wc

total_cost_usd = gen_cost.get('total_cost', 0) + subject_cost

# Determine R10 pipeline status string
if r10_in_pipeline and not r10_pipeline_error:
    r10_status = f"IN-PIPELINE (PHASE 5.155) — {r10_pipeline_deleted} sentences deleted"
elif r10_pipeline_error:
    r10_status = f"FAILED in-pipeline: {r10_pipeline_error}"
else:
    r10_status = "DID NOT RUN (PHASE 5.155 not reached or not logged)"

# Build markdown
md_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND3.md")
_build_riviera_md(
    md_path=md_path,
    total_words=total_words,
    total_cost_usd=total_cost_usd,
    gen_cost=gen_cost,
    subject_cost=subject_cost,
    stop_names=stop_names,
    existence_verdicts=existence_verdicts,
    coverage_verdicts=coverage_verdicts,
    total_promises=total_promises,
    total_expanded=total_expanded,
    total_deleted=total_deleted,
    r10_pipeline_deleted=r10_pipeline_deleted,
    r10_status=r10_status,
    r10_in_pipeline=r10_in_pipeline,
    r10_pipeline_log_lines=r10_pipeline_log_lines,
    r10_pipeline_error=r10_pipeline_error,
    r10_residual_deletions=r10_residual_deletions,
    elapsed=elapsed,
    new_tour_id=new_tour_id,
    para_word_counts=para_word_counts,
    processed_stops=processed_stops,
    para_styles=para_styles,
    subject_results=subject_results,
    count_before=count_before,
    count_after=count_after,
    visible_nice_post=visible_nice_post,
)

print(f"\n  Written: {md_path}")
print(f"  Total words: {total_words} (round 2 was 819)")
print(f"  Total cost: ${total_cost_usd:.4f}")

# --- Final ---
print("\n" + "=" * 70)
print("LOCAL-243 R10 IN-PIPELINE VERIFICATION COMPLETE")
print(f"  Tour ID: {new_tour_id}")
print(f"  R10 in-pipeline: {r10_in_pipeline}")
print(f"  R10 pipeline deletions: {r10_pipeline_deleted}")
print(f"  R10 residual (would-be-caught): {len(r10_residual_deletions)}")
print(f"  audio_tours: {count_before} -> {count_after}")
print(f"  Nice list unchanged: {visible_nice_post == EXPECTED_NICE}")
print(f"  Deliverable: RIVIERA_2STOP_ROUND3.md")
print(f"  Cost: ${total_cost_usd:.4f} (ceiling $0.20)")
print("=" * 70)
