#!/usr/bin/env python3
"""LOCAL-375: Generate additional tours (walking + restaurant) to fill coverage.

The main script (run_local375_classify_empty_sentences.py) generated:
  - Palais Lascaris (museum, 4)  ✓ 12 flagged
  - MFA Boston (museum, 8)       ✓ 19 flagged
  - MFA Unbound                  ✗ resolved to wrong museum
  - Old Nice walking             ✗ existence gate blocked (no corpus)
  - Old Nice restaurant          ✗ type gate blocked

This supplement generates:
  - French Riviera, France (biking, 2) — walking-register equivalent 
  - Musee Matisse, Nice, France (museum, 4) — additional museum
  - Boston Common walking area (walking, 4) — has corpus

Per D261: DISABLE_TOUR_CACHE=1, DATABASE_URL set.
"""
import os
import sys
import re
import time
import json

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
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

from db_connection import get_connection, check_db_available, get_database_url

os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
for k in ('DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
          'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION', 'DISABLE_R7_DELETION',
          'DISABLE_R1_REWRITE', 'DISABLE_R10_DELETION', 'DISABLE_CONTRADICTED_BLOCK',
          'DISABLE_COVERAGE_SELECTION', 'DISABLE_STOP_EXISTENCE_GATE',
          'ENABLE_STOP_EXISTENCE_GATE', 'DISABLE_SUBJECT_ROUTINE'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = get_database_url()

from generate_tour_text import generate_tour_text
from tour_rubric_scorer import parse_tour, analyze_stop, _is_empty_sentence, get_flagged_empty_sentences

VENUES = [
    {
        'location': 'French Riviera, France',
        'tour_type': 'biking',
        'total_stops': 2,
        'label': 'riviera_biking2',
    },
    {
        'location': 'Musee Matisse, Nice, France',
        'tour_type': 'museum',
        'total_stops': 4,
        'label': 'matisse_museum4',
    },
    {
        'location': 'Boston Common, Boston, MA',
        'tour_type': 'walking',
        'total_stops': 4,
        'label': 'boston_common_walking4',
    },
]

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'tours')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def main():
    print("=" * 70)
    print("LOCAL-375 SUPPLEMENT: ADDITIONAL TOUR TYPES")
    print("=" * 70)

    if not check_db_available():
        print("FATAL: Database unreachable")
        sys.exit(7)

    code_sha = os.popen("git rev-parse --short HEAD").read().strip()
    print(f"  code_sha: {code_sha}")
    print(f"  DATABASE_URL: {os.environ.get('DATABASE_URL', '(unset)')[:50]}...")
    print(f"  DISABLE_TOUR_CACHE: {os.environ.get('DISABLE_TOUR_CACHE')}")

    # Load existing results
    json_path = os.path.join(OUTPUT_DIR, "LOCAL375_flagged_sentences.json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            all_results = json.load(f)
        print(f"  Loaded {len(all_results)} existing flagged sentences")
    else:
        all_results = []

    for venue in VENUES:
        label = venue['label']
        print(f"\n{'─' * 70}")
        print(f"GENERATING: {venue['location']} ({venue['tour_type']}, {venue['total_stops']} stops)")
        print(f"{'─' * 70}")

        output_file = os.path.join(OUTPUT_DIR, f"LOCAL375_{label}.txt")

        t0 = time.time()
        try:
            tour_text, _, _ = generate_tour_text(
                location=venue['location'],
                tour_type=venue['tour_type'],
                output_file=output_file,
                total_stops=venue['total_stops'],
            )
        except Exception as e:
            print(f"  ERROR generating: {e}")
            import traceback
            traceback.print_exc()
            continue
        elapsed = time.time() - t0
        print(f"  Generated in {elapsed:.1f}s → {output_file}")

        if not tour_text:
            print("  WARNING: tour_text is empty/None, skipping")
            continue

        stops = parse_tour(tour_text)
        print(f"  Stops parsed: {len(stops)}")

        venue_count = 0
        for stop in stops:
            sa = analyze_stop(stop, stops)
            if sa.empty_sentence_count == 0:
                continue

            body = stop['body']
            for sent in get_flagged_empty_sentences(body):
                all_results.append({
                    'venue': venue['location'],
                    'tour_type': venue['tour_type'],
                    'stop_index': stop['index'],
                    'stop_title': stop['title'],
                    'sentence': sent,
                    'label': label,
                })
                venue_count += 1

        print(f"  Empty sentences flagged: {venue_count}")

    # Update JSON
    with open(json_path, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n  Total flagged sentences: {len(all_results)}")
    print(f"  JSON updated → {json_path}")
    print(f"  code_sha: {code_sha}")
    print("  DONE.")


if __name__ == '__main__':
    main()
