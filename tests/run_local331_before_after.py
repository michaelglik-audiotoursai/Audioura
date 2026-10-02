#!/usr/bin/env python3
"""
LOCAL-331: Before/after groundedness vectors for the museum 8-stop tour.

Shows the groundedness vector (a) without corpus loaded (old default=1.0) and
(b) with corpus loaded (real measured values).

Also rescores the museum tour and Old Nice restaurant tour with the new default.
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection, check_db_available
from tour_rubric_scorer import parse_tour, analyze_stop, classify_stop, _compute_groundedness_for_stop
from stop_corpus_reader import get_stop_corpus_for_tour
from tour_evaluator import evaluate


def extract_venue_name(tour_text):
    first_line = tour_text.split('\n')[0] if tour_text else ''
    m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
    return m.group(1).strip() if m else ''


def score_and_report(tour_id, tour_name, n_requested, tour_content, conn):
    """Score a tour both ways and show groundedness vectors."""
    print(f"\n{'─' * 70}")
    print(f"Tour {tour_id}: {tour_name}")
    print(f"  n_requested={n_requested}")
    print(f"{'─' * 70}")
    
    venue_name = extract_venue_name(tour_content)
    stops = parse_tour(tour_content)
    stop_names = [s['title'] for s in stops]
    
    # --- BEFORE: evaluate without corpus (old behavior would show 1.0) ---
    print(f"\n  WITHOUT CORPUS (old default would report 1.00):")
    result_no_corpus = evaluate(tour_content, n_requested)
    if result_no_corpus:
        groundedness_vec = [s['groundedness'] for s in result_no_corpus.per_stop]
        print(f"    score = {result_no_corpus.score.total_score:.1f}")
        print(f"    groundedness = {groundedness_vec}")
        for s in result_no_corpus.per_stop:
            g_str = f"{s['groundedness']:.2f}" if s['groundedness'] is not None else "None (unmeasured)"
            print(f"      [{s['classification']:>10}] g={g_str:<20} {s['title']}")
    
    # --- AFTER: evaluate with corpus loaded ---
    corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)
    print(f"\n  WITH CORPUS LOADED (accent-folded matching):")
    result_with_corpus = evaluate(tour_content, n_requested, corpus_data=corpus_data)
    if result_with_corpus:
        groundedness_vec = [s['groundedness'] for s in result_with_corpus.per_stop]
        print(f"    score = {result_with_corpus.score.total_score:.1f}")
        print(f"    groundedness = {groundedness_vec}")
        for s in result_with_corpus.per_stop:
            g_str = f"{s['groundedness']:.3f}" if s['groundedness'] is not None else "None (unmeasured)"
            print(f"      [{s['classification']:>10}] g={g_str:<20} {s['title']}")
    
    # Show delta
    if result_no_corpus and result_with_corpus:
        delta = result_with_corpus.score.total_score - result_no_corpus.score.total_score
        print(f"\n  SCORE DELTA: {delta:+.1f}")
        print(f"    Before (no corpus): {result_no_corpus.score.total_score:.1f}")
        print(f"    After (with corpus): {result_with_corpus.score.total_score:.1f}")


def main():
    if not check_db_available():
        print("ERROR: Database not reachable")
        sys.exit(1)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Museum tour (Asian Arts Museum, 8 stops)
    cur.execute("SELECT id, tour_name, number_requested, tour_content FROM audio_tours WHERE id = 21")
    row = cur.fetchone()
    if row:
        score_and_report(*row, conn)
    
    # Also score with n=8 (as the task describes: "evaluate(txt, 8)")
    if row:
        print(f"\n\n{'=' * 70}")
        print(f"SAME TOUR SCORED WITH n=8 (as per the finding)")
        print(f"{'=' * 70}")
        tour_id, tour_name, _, tour_content = row
        
        venue_name = extract_venue_name(tour_content)
        stops = parse_tour(tour_content)
        stop_names = [s['title'] for s in stops]
        
        # Without corpus
        print(f"\n  evaluate(txt, 8) — no corpus:")
        result = evaluate(tour_content, 8)
        if result:
            g_vec = [s['groundedness'] for s in result.per_stop]
            print(f"    base={result.score.total_score:.1f}")
            print(f"    groundedness = {g_vec}")
        
        # With corpus  
        print(f"\n  evaluate(txt, 8, corpus_data=...) — with corpus:")
        corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)
        result = evaluate(tour_content, 8, corpus_data=corpus_data)
        if result:
            g_vec = [s['groundedness'] for s in result.per_stop]
            print(f"    base={result.score.total_score:.1f}")
            print(f"    groundedness = {g_vec}")
    
    # Old Nice restaurant tour
    cur.execute("SELECT id, tour_name, number_requested, tour_content FROM audio_tours WHERE id = 17")
    row = cur.fetchone()
    if row:
        score_and_report(*row, conn)
    
    # Also check if there's a restaurant tour in the "restaurant tour in Old Nice" venue
    cur.execute("""
        SELECT id, tour_name, number_requested, tour_content 
        FROM audio_tours 
        WHERE tour_name ILIKE '%old nice%' OR tour_name ILIKE '%vieux nice%'
        AND tour_content IS NOT NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    for row in rows:
        if row[0] != 17:  # Skip if already shown
            score_and_report(*row, conn)
    
    conn.close()


if __name__ == '__main__':
    main()
