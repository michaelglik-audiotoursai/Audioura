#!/usr/bin/env python3
"""run_local327_groundedness_audit.py — LOCAL-327: Measure ungrounded ADEQUATE stops.

For every scoreable stop in tours/*.txt:
  - classification (computed from density/filler/facts)
  - fact count
  - corpus passage count (from stop_corpus DB via stop_corpus_reader)
  - measured groundedness fraction

Reports how many ADEQUATE-or-better stops have groundedness at or near zero.

[LOCAL-327 bounce fix] Uses stop_corpus_reader._find_corpus_venue_name and
get_stop_corpus_for_tour for proper accent-folded, suffix-stripped venue
matching — fixing the broken ILIKE '%venue[:40]%' predicate that returned
0 rows for accented/suffixed venue names.
"""
import os
import sys
import json
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tour_rubric_scorer import (
    parse_tour,
    analyze_stop,
    classify_stop,
    StopAnalysis,
    RICH_MIN_GROUNDEDNESS,
)
from stop_corpus_reader import get_stop_corpus_for_tour


def extract_venue_from_tour(text: str) -> str:
    """Extract venue name from tour header."""
    first_line = text.split('\n')[0] if text else ''
    m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
    if m:
        return m.group(1).strip()
    return ''


def audit_tour_file(filepath: str, conn) -> list:
    """Audit a single tour file. Returns list of stop records."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    stops = parse_tour(text)
    if not stops:
        return []

    venue_name = extract_venue_from_tour(text)
    stop_titles = [s['title'] for s in stops]

    # [LOCAL-327 bounce fix] Use the production corpus reader which handles
    # accent folding, suffix stripping, and multi-strategy matching.
    corpus_data = get_stop_corpus_for_tour(venue_name, stop_titles, conn)

    records = []
    for stop in stops:
        sa = analyze_stop(stop, stops)
        classification, evidence = classify_stop(sa)

        # Count passages for this stop from the corpus reader result
        stop_corpus = corpus_data.get(stop['title'])
        passage_count = 0
        if stop_corpus and stop_corpus.get('passages'):
            passage_count = len(stop_corpus['passages'])

        records.append({
            'file': os.path.basename(filepath),
            'venue': venue_name,
            'stop_index': stop['index'],
            'stop_title': stop['title'],
            'classification': classification,
            'fact_count': sa.distinct_fact_count,
            'content_sentences': sa.content_sentences,
            'fact_density': sa.fact_density,
            'filler_fraction': sa.generic_filler_fraction,
            'corpus_passages': passage_count,
            'groundedness_fraction': sa.groundedness_fraction,
            'evidence': evidence,
        })

    return records


def main():
    # Connect to database
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests')
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from db_connection import get_connection, log_db_target
    conn = get_connection()
    log_db_target(conn)

    tours_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tours')

    # Find all .txt tour files
    tour_files = sorted([
        os.path.join(tours_dir, f) for f in os.listdir(tours_dir)
        if f.endswith('.txt') and not f.startswith('.')
    ])

    print(f"Found {len(tour_files)} tour text files to audit")
    print("=" * 100)

    all_records = []
    files_scored = 0

    for filepath in tour_files:
        try:
            records = audit_tour_file(filepath, conn)
            if records:
                all_records.extend(records)
                files_scored += 1
        except Exception as e:
            print(f"  SKIP {os.path.basename(filepath)}: {e}")

    conn.close()

    print(f"\nScored {files_scored} tour files, {len(all_records)} total stops")
    print("=" * 100)

    # ─── Distribution analysis ────────────────────────────────────────────────

    # Filter to ADEQUATE or better
    adequate_plus = [r for r in all_records if r['classification'] in ('ADEQUATE', 'RICH')]
    zero_corpus = [r for r in adequate_plus if r['corpus_passages'] == 0]
    has_corpus = [r for r in adequate_plus if r['corpus_passages'] > 0]

    print(f"\n{'═' * 100}")
    print(f"DISTRIBUTION: ADEQUATE-or-better stops")
    print(f"{'═' * 100}")
    print(f"  Total ADEQUATE+ stops:       {len(adequate_plus)}")
    print(f"  With corpus passages > 0:    {len(has_corpus)}")
    print(f"  With corpus passages = 0:    {len(zero_corpus)}  ← UNVERIFIED")
    if adequate_plus:
        print(f"  Fraction unverified:         {len(zero_corpus)/len(adequate_plus):.1%}")

    print(f"\n{'─' * 100}")
    print(f"ZERO-CORPUS ADEQUATE+ STOPS (claiming quality on unverified facts):")
    print(f"{'─' * 100}")
    print(f"{'File':<45} {'Stop':<35} {'Cls':<10} {'Facts':<6} {'Density':<8}")
    print(f"{'─' * 100}")
    for r in sorted(zero_corpus, key=lambda x: (x['file'], x['stop_index'])):
        print(f"{r['file']:<45} {r['stop_title'][:34]:<35} {r['classification']:<10} {r['fact_count']:<6} {r['fact_density']:.2f}")

    # ─── Fact count distribution for zero-corpus stops ─────────────────────────
    print(f"\n{'─' * 100}")
    print(f"FACT COUNT DISTRIBUTION — zero-corpus ADEQUATE+ stops:")
    print(f"{'─' * 100}")
    fact_counts = [r['fact_count'] for r in zero_corpus]
    if fact_counts:
        from statistics import median, mean
        fact_counts_sorted = sorted(fact_counts)
        print(f"  n = {len(fact_counts)}")
        print(f"  min = {min(fact_counts)}, max = {max(fact_counts)}")
        print(f"  mean = {mean(fact_counts):.1f}, median = {median(fact_counts)}")
        # Histogram
        for threshold in [3, 4, 5, 6, 7, 8, 10]:
            count = sum(1 for f in fact_counts if f >= threshold)
            print(f"  facts >= {threshold}: {count} stops")

    # ─── Corpus passage distribution for ADEQUATE+ stops that HAVE corpus ─────
    print(f"\n{'─' * 100}")
    print(f"CORPUS PASSAGE DISTRIBUTION — ADEQUATE+ stops WITH corpus:")
    print(f"{'─' * 100}")
    passage_counts = [r['corpus_passages'] for r in has_corpus]
    if passage_counts:
        from statistics import median, mean
        passage_sorted = sorted(passage_counts)
        print(f"  n = {len(passage_counts)}")
        print(f"  min = {min(passage_counts)}, max = {max(passage_counts)}")
        print(f"  mean = {mean(passage_counts):.1f}, median = {median(passage_counts)}")
        # Show counts at various thresholds
        for threshold in [1, 2, 3, 5, 10]:
            count = sum(1 for p in passage_counts if p >= threshold)
            print(f"  passages >= {threshold}: {count} stops")

    # ─── By classification breakdown ──────────────────────────────────────────
    print(f"\n{'─' * 100}")
    print(f"ALL STOPS BY CLASSIFICATION:")
    print(f"{'─' * 100}")
    by_cls = defaultdict(list)
    for r in all_records:
        by_cls[r['classification']].append(r)
    for cls in ['RICH', 'ADEQUATE', 'THIN', 'CONTRADICTED']:
        stops_in_cls = by_cls[cls]
        zero_in_cls = [r for r in stops_in_cls if r['corpus_passages'] == 0]
        print(f"  {cls:<15}: {len(stops_in_cls):>4} total, {len(zero_in_cls):>4} zero-corpus ({len(zero_in_cls)/max(len(stops_in_cls),1):.0%})")

    # ─── Per-venue breakdown ──────────────────────────────────────────────────
    print(f"\n{'─' * 100}")
    print(f"PER-VENUE: ADEQUATE+ stops with/without corpus:")
    print(f"{'─' * 100}")
    by_venue = defaultdict(lambda: {'total': 0, 'with_corpus': 0, 'without_corpus': 0})
    for r in adequate_plus:
        v = r['venue'] or r['file']
        by_venue[v]['total'] += 1
        if r['corpus_passages'] > 0:
            by_venue[v]['with_corpus'] += 1
        else:
            by_venue[v]['without_corpus'] += 1
    for v, counts in sorted(by_venue.items()):
        print(f"  {v[:60]:<62} {counts['with_corpus']:>2} grounded, {counts['without_corpus']:>2} unverified / {counts['total']:>2} total")

    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'═' * 100}")
    print(f"SUMMARY")
    print(f"{'═' * 100}")
    print(f"  {len(zero_corpus)} of {len(adequate_plus)} ADEQUATE+ stops ({len(zero_corpus)/max(len(adequate_plus),1):.0%})")
    print(f"  reach their band on ZERO corpus passages.")
    print(f"  These facts came entirely from parametric memory — nothing checked.")
    if len(zero_corpus) < len(adequate_plus) * 0.5:
        print(f"  The problem is smaller than the 96% initially reported (that was")
        print(f"  a venue-matching artifact). But {len(zero_corpus)} unverified stops")
        print(f"  still inflate reported quality.")


if __name__ == '__main__':
    main()
