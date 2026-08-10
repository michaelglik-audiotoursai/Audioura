#!/usr/bin/env python3
"""LOCAL-375: Classify residual empty_sentence_count hits.

Generates live tours (DISABLE_TOUR_CACHE=1, DATABASE_URL set) for at least 5
venues covering museum, walking, and restaurant tour types, then dumps every
sentence flagged by _is_empty_sentence with full context for classification.

Venues (from task):
  1. Palais Lascaris, Nice, France          (museum, 4 stops)
  2. Museum of Fine Arts, Boston, MA        (museum, 8 stops)
  3. Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (museum, 8)
  4. Walking tour, Old Nice, France         (walking, 4 stops)
  5. Restaurant tour, Old Nice, France      (restaurant, 3 stops)

Output: prints all flagged sentences with stop context. Does NOT change any
gates, scoring, prompts, or generation logic.
"""
import os
import sys
import re
import time
import json
import io

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

# Force live generation
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
# Clear disabling flags
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

# ─── Venues ──────────────────────────────────────────────────────────────────

VENUES = [
    {
        'location': 'Palais Lascaris, Nice, France',
        'tour_type': 'museum',
        'total_stops': 4,
        'label': 'palais_lascaris_museum4',
    },
    {
        'location': 'Museum of Fine Arts, Boston, MA',
        'tour_type': 'museum',
        'total_stops': 8,
        'label': 'mfa_boston_museum8',
    },
    {
        'location': 'Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA',
        'tour_type': 'museum',
        'total_stops': 8,
        'label': 'mfa_unbound_museum8',
    },
    {
        'location': 'Old Nice, France',
        'tour_type': 'walking',
        'total_stops': 4,
        'label': 'old_nice_walking4',
    },
    {
        'location': 'Old Nice, France',
        'tour_type': 'restaurant',
        'total_stops': 3,
        'label': 'old_nice_restaurant3',
    },
]

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'tours')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def main():
    print("=" * 70)
    print("LOCAL-375: CLASSIFY RESIDUAL EMPTY_SENTENCE_COUNT HITS")
    print("=" * 70)

    if not check_db_available():
        print("FATAL: Database unreachable")
        sys.exit(7)

    code_sha = os.popen("git rev-parse --short HEAD").read().strip()
    print(f"  code_sha: {code_sha}")
    print(f"  DATABASE_URL: {os.environ.get('DATABASE_URL', '(unset)')[:50]}...")
    print(f"  DISABLE_TOUR_CACHE: {os.environ.get('DISABLE_TOUR_CACHE')}")
    print(f"  STORIED_MODE: {os.environ.get('STORIED_MODE')}")
    print()

    all_results = []  # list of dicts: {venue, stop_title, stop_index, sentence, tour_type}

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

        # Parse and analyze
        stops = parse_tour(tour_text)
        print(f"  Stops parsed: {len(stops)}")

        for stop in stops:
            sa = analyze_stop(stop, stops)
            if sa.empty_sentence_count == 0:
                continue

            # Use the canonical helper to extract flagged sentences
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

        # Summary for this venue
        venue_count = sum(1 for r in all_results if r['label'] == label)
        print(f"  Empty sentences flagged: {venue_count}")

    # ─── Dump all flagged sentences ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"TOTAL FLAGGED SENTENCES: {len(all_results)}")
    print("=" * 70)

    for i, r in enumerate(all_results, 1):
        print(f"\n  [{i}] Tour: {r['venue']} ({r['tour_type']})")
        print(f"      Stop {r['stop_index']}: {r['stop_title']}")
        print(f"      Sentence: \"{r['sentence']}\"")

    # Write JSON for post-processing
    json_path = os.path.join(OUTPUT_DIR, "LOCAL375_flagged_sentences.json")
    with open(json_path, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON dump → {json_path}")

    print(f"\n  code_sha: {code_sha}")
    print("  DONE.")


if __name__ == '__main__':
    main()
