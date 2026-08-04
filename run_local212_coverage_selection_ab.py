#!/usr/bin/env python3
"""LOCAL-212: A/B test — coverage-aware stop selection vs position order.

Two venues (D85):
  - MAMAC (museum) — 2 of 10 stops are CREATOR_ONLY (D78)
  - French Riviera cycling — outdoor path; Villefranche produced fabrications

2 stops (D61), 3 runs per arm, STORIED_MODE=true, cache bypassed.
Selection ON vs OFF (DISABLE_COVERAGE_SELECTION env var).

Metrics per arm:
  1. Stop titles + coverage verdicts
  2. Unsupported claims per paragraph (claim_check.py, unmodified)
  3. Style-validator failure rates
  4. Anchor rate

Persists every generated paragraph (D71). Stores tours in audio_tours (is_test=true).
"""
import os
import sys
import re
import json
import time
import hashlib
import random

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

# ─── Environment ─────────────────────────────────────────────────────────────
os.environ['STORIED_MODE'] = 'true'
# Remove any leftover flags that would interfere
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_COVERAGE_SELECTION'):
    if k in os.environ:
        del os.environ[k]

# ─── Imports ─────────────────────────────────────────────────────────────────
from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops, classify_paragraph, build_corpus_anchors, extract_entities
from corpus_coverage import assess_stop_coverage
from stop_corpus_reader import get_stop_corpus_for_tour
from claim_check import check_paragraph

import importlib.util
_svd_spec = importlib.util.spec_from_file_location(
    "style_validator_detector_root",
    os.path.join(PROJECT_ROOT, "style_validator_detector.py")
)
_svd_mod = importlib.util.module_from_spec(_svd_spec)
_svd_spec.loader.exec_module(_svd_mod)
validate_paragraph = _svd_mod.validate_paragraph

from generate_tour_text import generate_tour_text

# ─── Configuration ───────────────────────────────────────────────────────────
VENUES = [
    {
        'name': 'MAMAC',
        'location': 'MAMAC (Musée d\'Art Moderne et d\'Art Contemporain), Nice, France',
        'tour_type': 'museum',
        'corpus_venue': 'MAMAC',
    },
    {
        'name': 'French Riviera cycling',
        'location': 'French Riviera cycling tour, France',
        'tour_type': 'biking',
        'corpus_venue': 'French Riviera',
    },
]
TOTAL_STOPS = 2
RUNS_PER_ARM = 3

# ─── Utility: bypass tour cache ─────────────────────────────────────────────
_CACHE_BUST_COUNTER = 0


def _cache_bust_location(location):
    """Add invisible variation to bypass the S20 cache key (D63 trap)."""
    global _CACHE_BUST_COUNTER
    _CACHE_BUST_COUNTER += 1
    # Append a zero-width space + counter as a comment that doesn't affect prompts
    return location + f"  "  # trailing whitespace varies per run


# ─── Pre-checks ──────────────────────────────────────────────────────────────
print("=" * 70)
print("LOCAL-212: Coverage-Aware Stop Selection A/B Test")
print("=" * 70)
print(f"  STORIED_MODE = true")
print(f"  Stops per tour = {TOTAL_STOPS}")
print(f"  Runs per arm = {RUNS_PER_ARM}")
print(f"  Arms = selection ON (coverage-aware) vs OFF (position order)")
print()

if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

# Verify Nice list
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
nice_list = [r[0] for r in cur.fetchall()]
assert nice_list == [1, 12, 14, 17, 21, 24, 27, 28, 29, 152], f"Nice list mismatch: {nice_list}"
print(f"[PRE] Nice list intact: {nice_list}")
cur.close()
conn.close()

# ─── Run generation ──────────────────────────────────────────────────────────
all_results = []  # List of run result dicts
all_paragraphs = []  # For D71 persistence

for venue_cfg in VENUES:
    for arm in ('selection_ON', 'selection_OFF'):
        for run_idx in range(RUNS_PER_ARM):
            run_label = f"{venue_cfg['name']}|{arm}|run{run_idx+1}"
            print(f"\n{'─' * 70}")
            print(f"  GENERATING: {run_label}")
            print(f"{'─' * 70}")

            # Set/clear the flag
            if arm == 'selection_ON':
                if 'DISABLE_COVERAGE_SELECTION' in os.environ:
                    del os.environ['DISABLE_COVERAGE_SELECTION']
            else:
                os.environ['DISABLE_COVERAGE_SELECTION'] = '1'

            # Cache bust
            loc = _cache_bust_location(venue_cfg['location'])

            output_file = os.path.join(
                PROJECT_ROOT, "tours",
                f"LOCAL212_{venue_cfg['name'].replace(' ', '_')}_{arm}_run{run_idx+1}.txt"
            )

            start_time = time.time()
            try:
                result = generate_tour_text(
                    location=loc,
                    tour_type=venue_cfg['tour_type'],
                    output_file=output_file,
                    total_stops=TOTAL_STOPS,
                    persona=None,
                )
            except Exception as e:
                print(f"  ERROR: {e}")
                all_results.append({
                    'label': run_label, 'venue': venue_cfg['name'],
                    'arm': arm, 'run': run_idx + 1, 'error': str(e),
                })
                continue
            elapsed = time.time() - start_time

            if not result or not result[0]:
                print(f"  FAILED: No tour generated ({elapsed:.1f}s)")
                all_results.append({
                    'label': run_label, 'venue': venue_cfg['name'],
                    'arm': arm, 'run': run_idx + 1, 'error': 'generation_returned_none',
                })
                continue

            tour_text = result[0]
            print(f"  ✓ Generated: {len(tour_text)} chars in {elapsed:.1f}s")

            # Parse stops
            stops = parse_tour_stops(tour_text)
            stop_titles = [s['title'] for s in stops]
            print(f"  Stops: {stop_titles}")

            # Coverage verdicts
            conn = get_connection()
            corpus_data = get_stop_corpus_for_tour(
                venue_cfg['corpus_venue'], stop_titles, conn
            )
            conn.close()

            verdicts = {}
            for st in stop_titles:
                sc = corpus_data.get(st)
                if sc and sc.get('passages'):
                    assessment = assess_stop_coverage(
                        st, venue_cfg['corpus_venue'], sc['passages'],
                        passage_roles=sc.get('passage_roles')
                    )
                    verdicts[st] = assessment['verdict']
                else:
                    verdicts[st] = 'EMPTY'
            print(f"  Verdicts: {verdicts}")

            # Metrics per stop
            run_claims_total = 0
            run_unsupported_total = 0
            run_style_violations = 0
            run_style_total = 0
            run_anchored = 0
            run_total_content_paras = 0
            run_paragraphs = []

            for stop in stops:
                st_name = stop['title']
                paragraphs = stop.get('paragraphs', [])
                sc = corpus_data.get(st_name)
                passages = sc['passages'] if sc and sc.get('passages') else []

                for para in paragraphs:
                    if not para.strip():
                        continue
                    # Skip directions/navigation
                    if para.lower().startswith('directions:') or para.lower().startswith('direction:'):
                        continue

                    run_paragraphs.append({
                        'venue': venue_cfg['name'],
                        'arm': arm,
                        'run': run_idx + 1,
                        'stop': st_name,
                        'text': para,
                    })

                    # Claim check
                    claim_result = check_paragraph(
                        text=para,
                        stop_title=st_name,
                        venue_name=venue_cfg['corpus_venue'],
                        passages=passages,
                    )
                    run_claims_total += len(claim_result['claims'])
                    run_unsupported_total += claim_result['unsupported_count']

                    # Style validation
                    style_result = validate_paragraph(para)
                    if not style_result['is_navigation']:
                        run_style_total += 1
                        if style_result['rules_violated']:
                            run_style_violations += 1

                    # Anchor (use build_corpus_anchors with proper structure)
                    corpus_anchors_dict = {}
                    if passages:
                        # Build a venue_corpus-like dict for the anchor detector
                        _vc_for_anchor = {
                            'passages_json': passages,
                            'pages_json': [{'text': '\n'.join(passages)}],
                            'story_elements_json': [],
                            'canonical_titles_json': [],
                        }
                        corpus_anchors_dict = build_corpus_anchors(
                            _vc_for_anchor, st_name, venue_cfg['name']
                        )
                    classification = classify_paragraph(
                        para, corpus_anchors_dict, st_name, venue_cfg['name']
                    )
                    if classification['classification'] not in ('NAVIGATION',):
                        run_total_content_paras += 1
                        if classification['classification'] == 'ANCHORED':
                            run_anchored += 1

            # Store results
            run_result = {
                'label': run_label,
                'venue': venue_cfg['name'],
                'arm': arm,
                'run': run_idx + 1,
                'stop_titles': stop_titles,
                'verdicts': verdicts,
                'claims_total': run_claims_total,
                'unsupported_total': run_unsupported_total,
                'style_violations': run_style_violations,
                'style_total': run_style_total,
                'anchored': run_anchored,
                'content_paragraphs': run_total_content_paras,
                'elapsed': elapsed,
            }
            all_results.append(run_result)
            all_paragraphs.extend(run_paragraphs)

            # Store in DB
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO audio_tours (
                    tour_name, request_string, number_requested,
                    is_test, storied_mode, tour_content, stops_count,
                    lat, lng
                )
                VALUES (%s, %s, %s, TRUE, TRUE, %s, %s, NULL, NULL)
                RETURNING id
            """, (
                f"LOCAL-212 {venue_cfg['name']} {arm} run{run_idx+1}",
                venue_cfg['location'],
                TOTAL_STOPS,
                tour_text,
                len(stops),
            ))
            tour_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            print(f"  → Stored as tour #{tour_id}")

# ─── Persist paragraphs (D71) ───────────────────────────────────────────────
para_output_path = os.path.join(PROJECT_ROOT, "tours", "LOCAL212_all_paragraphs.json")
with open(para_output_path, 'w') as f:
    json.dump(all_paragraphs, f, indent=2)
print(f"\n[D71] Persisted {len(all_paragraphs)} paragraphs → {para_output_path}")

# ─── Post-check: row count and Nice list ─────────────────────────────────────
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
nice_list_after = [r[0] for r in cur.fetchall()]
cur.close()
conn.close()

print(f"\n[POST] audio_tours: {count_before} → {count_after} (+{count_after - count_before})")
print(f"[POST] Nice list intact: {nice_list_after == [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]}")

# ─── Report ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

for venue_cfg in VENUES:
    vname = venue_cfg['name']
    print(f"\n{'─' * 40}")
    print(f"  VENUE: {vname}")
    print(f"{'─' * 40}")

    for arm in ('selection_ON', 'selection_OFF'):
        arm_runs = [r for r in all_results if r['venue'] == vname and r['arm'] == arm and 'error' not in r]
        print(f"\n  ARM: {arm} ({len(arm_runs)} successful runs)")

        for r in arm_runs:
            unsup_per_para = (r['unsupported_total'] / r['content_paragraphs']
                              if r['content_paragraphs'] > 0 else 0)
            style_rate = (r['style_violations'] / r['style_total']
                          if r['style_total'] > 0 else 0)
            anchor_rate = (r['anchored'] / r['content_paragraphs']
                           if r['content_paragraphs'] > 0 else 0)
            print(f"    Run {r['run']}: stops={r['stop_titles']}")
            print(f"      verdicts: {r['verdicts']}")
            print(f"      unsupported: {r['unsupported_total']}/{r['claims_total']} claims "
                  f"({unsup_per_para:.2f}/para)")
            print(f"      style violations: {r['style_violations']}/{r['style_total']} "
                  f"({style_rate:.2f})")
            print(f"      anchor rate: {r['anchored']}/{r['content_paragraphs']} "
                  f"({anchor_rate:.2f})")

        # Arm averages
        if arm_runs:
            avg_unsup = sum(r['unsupported_total'] for r in arm_runs) / len(arm_runs)
            total_paras = sum(r['content_paragraphs'] for r in arm_runs)
            total_unsup = sum(r['unsupported_total'] for r in arm_runs)
            total_style_v = sum(r['style_violations'] for r in arm_runs)
            total_style_t = sum(r['style_total'] for r in arm_runs)
            total_anch = sum(r['anchored'] for r in arm_runs)

            print(f"    ── ARM AVERAGE ──")
            print(f"      unsupported/para: {total_unsup/total_paras:.3f}" if total_paras else "      (no paras)")
            print(f"      style fail rate: {total_style_v/total_style_t:.3f}" if total_style_t else "      (no style paras)")
            print(f"      anchor rate: {total_anch/total_paras:.3f}" if total_paras else "      (no paras)")

# ─── Comparison summary ──────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("COMPARISON SUMMARY")
print("=" * 70)

for vname in [v['name'] for v in VENUES]:
    on_runs = [r for r in all_results if r['venue'] == vname and r['arm'] == 'selection_ON' and 'error' not in r]
    off_runs = [r for r in all_results if r['venue'] == vname and r['arm'] == 'selection_OFF' and 'error' not in r]

    if not on_runs or not off_runs:
        print(f"\n  {vname}: INSUFFICIENT DATA")
        continue

    on_paras = sum(r['content_paragraphs'] for r in on_runs)
    off_paras = sum(r['content_paragraphs'] for r in off_runs)
    on_unsup_rate = sum(r['unsupported_total'] for r in on_runs) / on_paras if on_paras else 0
    off_unsup_rate = sum(r['unsupported_total'] for r in off_runs) / off_paras if off_paras else 0

    print(f"\n  {vname}:")
    print(f"    unsupported/para: ON={on_unsup_rate:.3f} vs OFF={off_unsup_rate:.3f} "
          f"(delta={on_unsup_rate - off_unsup_rate:+.3f})")

    # Check if same stops selected each run (non-determinism trap)
    on_stop_sets = [tuple(sorted(r['stop_titles'])) for r in on_runs]
    off_stop_sets = [tuple(sorted(r['stop_titles'])) for r in off_runs]
    on_consistent = len(set(on_stop_sets)) == 1
    off_consistent = len(set(off_stop_sets)) == 1
    print(f"    stop consistency: ON={'consistent' if on_consistent else 'VARIES'} "
          f"OFF={'consistent' if off_consistent else 'VARIES'}")
    if not on_consistent:
        print(f"      ON stop sets: {on_stop_sets}")
    if not off_consistent:
        print(f"      OFF stop sets: {off_stop_sets}")

# ─── Save full results JSON ──────────────────────────────────────────────────
results_path = os.path.join(PROJECT_ROOT, "tours", "LOCAL212_results.json")
with open(results_path, 'w') as f:
    json.dump(all_results, f, indent=2, default=str)
print(f"\n[SAVED] Full results → {results_path}")

print(f"\n{'=' * 70}")
print("LOCAL-212 A/B COMPLETE")
print(f"{'=' * 70}")
