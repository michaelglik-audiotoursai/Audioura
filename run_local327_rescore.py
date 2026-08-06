#!/usr/bin/env python3
"""run_local327_rescore.py — LOCAL-327: Rescore tours with corpus availability ceiling.

Shows before/after scores for the tour corpus. The "before" is computed with
corpus_lookup_attempted=False (pre-fix behavior). The "after" uses the actual
corpus data from the database (corpus_lookup_attempted=True).
"""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tour_rubric_scorer import (
    parse_tour,
    analyze_stop,
    classify_stop,
    compute_score,
    detect_venue_identity,
    StopAnalysis,
    score_tour_file,
)
from stop_corpus_reader import get_stop_corpus_for_tour


def extract_venue_from_tour(text: str) -> str:
    first_line = text.split('\n')[0] if text else ''
    m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
    return m.group(1).strip() if m else ''


def score_tour_with_corpus(filepath: str, n_requested: int, conn) -> dict:
    """Score a tour with corpus data loaded from the DB."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stops = parse_tour(text)
    if not stops:
        return None
    
    venue_name = extract_venue_from_tour(text)
    stop_titles = [s['title'] for s in stops]
    
    # Get corpus from DB via the production reader
    corpus_data_raw = get_stop_corpus_for_tour(venue_name, stop_titles, conn)
    
    # Convert to format expected by score_tour_file (only entries with passages)
    corpus_for_scorer = {}
    for title, data in corpus_data_raw.items():
        if data and data.get('passages'):
            corpus_for_scorer[title] = data
    
    # Score WITH corpus (post-fix behavior)
    ts_after = score_tour_file(filepath, n_requested, corpus_data=corpus_for_scorer)
    
    # Score WITHOUT corpus (pre-fix: no corpus_lookup_attempted)
    ts_before = score_tour_file(filepath, n_requested, corpus_data=None)
    
    return {
        'file': os.path.basename(filepath),
        'venue': venue_name,
        'n_stops': len(stops),
        'before_score': ts_before.base_score,
        'after_score': ts_after.base_score,
        'delta': ts_after.base_score - ts_before.base_score,
        'before_stops': [(s.title, s.classification) for s in ts_before.stops],
        'after_stops': [(s.title, s.classification, s.corpus_available) for s in ts_after.stops],
    }


def main():
    from tests.db_connection import get_connection, log_db_target
    conn = get_connection()
    log_db_target(conn)
    
    tours_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tours')
    
    # Key tours to score (including the two named in the task)
    target_tours = [
        ('LOCAL262_asian_arts_8stop_restored.txt', 8),
        ('LOCAL317_5stop_old_nice_restaurant.txt', 5),
        ('LOCAL318_5stop_old_nice_restaurant.txt', 5),
        ('matisse_nice.txt', 8),
        ('pilot_chagall_resubmit.txt', 5),
        ('Palais_Lascaris__Nice_museum_tour_20260727_174018.txt', 5),
    ]
    
    # Also score some riviera tours
    riviera_tours = [
        ('LOCAL208_riviera_2stop_for_michael.txt', 2),
        ('LOCAL222_riviera_run1.txt', 2),
        ('LOCAL250_riviera_2stop_round7.txt', 2),
    ]
    
    all_tours = target_tours + riviera_tours
    
    print("=" * 110)
    print(f"{'File':<55} {'N':<3} {'Before':<8} {'After':<8} {'Delta':<8}")
    print("=" * 110)
    
    results = []
    for filename, n in all_tours:
        filepath = os.path.join(tours_dir, filename)
        if not os.path.exists(filepath):
            print(f"{filename:<55} — FILE NOT FOUND")
            continue
        
        result = score_tour_with_corpus(filepath, n, conn)
        if result:
            results.append(result)
            delta_str = f"{result['delta']:+.1f}"
            print(f"{result['file']:<55} {n:<3} {result['before_score']:<8.1f} {result['after_score']:<8.1f} {delta_str:<8}")
    
    conn.close()
    
    # ─── Detailed stop-level comparison for key tours ─────────────────────────
    print(f"\n{'═' * 110}")
    print("DETAILED STOP-LEVEL CHANGES")
    print(f"{'═' * 110}")
    
    for result in results:
        changes = []
        for (t_b, c_b), (t_a, c_a, corpus) in zip(result['before_stops'], result['after_stops']):
            if c_b != c_a:
                corpus_str = "corpus=yes" if corpus else "corpus=NO"
                changes.append(f"  {t_b[:50]}: {c_b} → {c_a}  ({corpus_str})")
        
        if changes:
            print(f"\n{result['file']}:")
            for c in changes:
                print(c)
    
    # ─── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'═' * 110}")
    print("SUMMARY")
    print(f"{'═' * 110}")
    tours_that_dropped = [r for r in results if r['delta'] < 0]
    tours_unchanged = [r for r in results if r['delta'] == 0]
    tours_that_rose = [r for r in results if r['delta'] > 0]
    
    print(f"  Tours scored:       {len(results)}")
    print(f"  Scores dropped:     {len(tours_that_dropped)}")
    print(f"  Scores unchanged:   {len(tours_unchanged)}")
    print(f"  Scores rose:        {len(tours_that_rose)} (should be 0 — investigate if > 0)")
    
    if tours_that_dropped:
        total_drop = sum(r['delta'] for r in tours_that_dropped)
        avg_drop = total_drop / len(tours_that_dropped)
        print(f"  Average drop:       {avg_drop:.1f} points")


if __name__ == '__main__':
    main()
