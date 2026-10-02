#!/usr/bin/env python3
"""
LOCAL-356: Report empty-sentence distribution across all scorable tours.

Reads all production tours from the database (tour_content IS NOT NULL AND
LENGTH(tour_content) > 100 AND is_test IS NOT TRUE), parses and analyzes
each stop, and reports:
  - Per-tour summary: tour_id, tour_name, mean empty_sentence_fraction
  - Corpus-wide distribution statistics
  - Total empty sentences vs total content sentences
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_connection
from tour_rubric_scorer import parse_tour, analyze_stop

def main():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tour_name, tour_content, number_requested "
        "FROM audio_tours "
        "WHERE tour_content IS NOT NULL AND LENGTH(tour_content) > 100 "
        "AND is_test IS NOT TRUE "
        "ORDER BY id"
    )
    rows = cur.fetchall()
    conn.close()

    print(f"Scorable tours: {len(rows)}")
    print("=" * 90)

    total_content_sentences = 0
    total_empty_sentences = 0
    per_tour_fractions = []
    per_stop_fractions = []

    for tour_id, tour_name, tour_content, n_requested in rows:
        stops = parse_tour(tour_content)
        if not stops:
            continue

        tour_empty = 0
        tour_sentences = 0
        for stop in stops:
            sa = analyze_stop(stop, stops)
            tour_empty += sa.empty_sentence_count
            tour_sentences += sa.content_sentences
            if sa.content_sentences > 0:
                per_stop_fractions.append(sa.empty_sentence_fraction)

        total_content_sentences += tour_sentences
        total_empty_sentences += tour_empty

        tour_frac = tour_empty / max(1, tour_sentences)
        per_tour_fractions.append(tour_frac)
        # Show tours with significant filler
        if tour_frac >= 0.05:
            print(f"  ID {tour_id:3d}  {tour_frac:5.1%}  ({tour_empty}/{tour_sentences} sentences)  {tour_name[:60]}")

    print("=" * 90)
    print(f"\nCorpus totals:")
    print(f"  Total content sentences: {total_content_sentences}")
    print(f"  Total empty sentences:   {total_empty_sentences}")
    print(f"  Corpus-wide fraction:    {total_empty_sentences / max(1, total_content_sentences):.1%}")

    if per_tour_fractions:
        per_tour_fractions.sort()
        n = len(per_tour_fractions)
        print(f"\nPer-tour distribution (n={n}):")
        print(f"  Min:    {per_tour_fractions[0]:.1%}")
        print(f"  P25:    {per_tour_fractions[n // 4]:.1%}")
        print(f"  Median: {per_tour_fractions[n // 2]:.1%}")
        print(f"  P75:    {per_tour_fractions[3 * n // 4]:.1%}")
        print(f"  P90:    {per_tour_fractions[int(n * 0.9)]:.1%}")
        print(f"  Max:    {per_tour_fractions[-1]:.1%}")
        print(f"  Mean:   {sum(per_tour_fractions) / n:.1%}")

    if per_stop_fractions:
        per_stop_fractions.sort()
        n = len(per_stop_fractions)
        print(f"\nPer-stop distribution (n={n}):")
        print(f"  Min:    {per_stop_fractions[0]:.1%}")
        print(f"  P25:    {per_stop_fractions[n // 4]:.1%}")
        print(f"  Median: {per_stop_fractions[n // 2]:.1%}")
        print(f"  P75:    {per_stop_fractions[3 * n // 4]:.1%}")
        print(f"  P90:    {per_stop_fractions[int(n * 0.9)]:.1%}")
        print(f"  Max:    {per_stop_fractions[-1]:.1%}")
        print(f"  Mean:   {sum(per_stop_fractions) / n:.1%}")


if __name__ == '__main__':
    main()
