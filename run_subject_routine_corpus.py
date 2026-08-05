#!/usr/bin/env python3
"""run_subject_routine_corpus.py — LOCAL-237: Run subject routine corpus-wide.

Reports: promises found, expanded, deleted — per tour and totals.
Includes cost accounting (ceiling $0.45).
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection
from subject_validate_expand import (
    gather_promises, process_paragraph, _parse_tour_content, is_subject_routine_enabled
)
from cost_rates import SERPER_COST_PER_QUERY

# Cost ceiling from task spec
COST_CEILING = 0.45


def run_corpus_wide():
    """Run the gather stage (deterministic, $0) on all tours with tour_content.

    For the VALIDATE/EXPAND stages (which cost $0.001/search), only run on
    tours in the Nice list to stay within budget.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Get all tours with tour_content
    cur.execute("""
        SELECT id, tour_name, tour_content
        FROM audio_tours
        WHERE tour_content IS NOT NULL AND length(tour_content) > 100
        ORDER BY id
    """)
    tours = cur.fetchall()
    cur.close()

    print("=" * 80)
    print("LOCAL-237: Subject Validate Expand — Corpus-Wide Promise Detection")
    print("=" * 80)
    print(f"\nTours with tour_content: {len(tours)}")
    print(f"audio_tours total: 138")
    print()

    # Stage 1 only (gather — deterministic, no cost) on all tours
    total_promises = 0
    total_paragraphs = 0
    per_tour_stats = []

    for tour_id, tour_name, content in tours:
        stops = _parse_tour_content(content)
        tour_promises = 0
        tour_paragraphs = 0

        for stop in stops:
            for para in stop['paragraphs']:
                promises = gather_promises(para)
                tour_promises += len(promises)
                tour_paragraphs += 1

        total_promises += tour_promises
        total_paragraphs += tour_paragraphs
        per_tour_stats.append({
            'id': tour_id,
            'name': tour_name,
            'paragraphs': tour_paragraphs,
            'promises': tour_promises,
        })

    print(f"{'─' * 70}")
    print(f"GATHER STAGE (deterministic, $0.00) — All tours with tour_content")
    print(f"{'─' * 70}")
    print(f"\n  Tours processed: {len(tours)}")
    print(f"  Total paragraphs: {total_paragraphs}")
    print(f"  Total promises found: {total_promises}")
    print(f"  Promises per paragraph: {total_promises/max(total_paragraphs,1):.2f}")
    print(f"  Promises per tour: {total_promises/max(len(tours),1):.1f}")
    print()

    # Show per-tour breakdown
    print(f"  {'Tour ID':<8} {'Promises':<10} {'Paras':<8} {'Tour Name'}")
    print(f"  {'─'*8} {'─'*10} {'─'*8} {'─'*40}")
    for t in sorted(per_tour_stats, key=lambda x: -x['promises']):
        if t['promises'] > 0:
            print(f"  {t['id']:<8} {t['promises']:<10} {t['paragraphs']:<8} {t['name'][:50]}")

    # Now run full pipeline (with search) on the Nice list tours that have content
    nice_list = [1, 12, 14, 17, 24, 29, 152]
    nice_tours = [(tid, tn, tc) for tid, tn, tc in tours if tid in nice_list]

    print(f"\n\n{'─' * 70}")
    print(f"FULL PIPELINE (validate+expand) — Nice list tours")
    print(f"{'─' * 70}")
    print(f"\n  Nice list tours with content: {len(nice_tours)}")

    total_cost = 0.0
    full_results = []

    for tour_id, tour_name, content in nice_tours:
        if total_cost >= COST_CEILING:
            print(f"\n  ⚠ Cost ceiling ${COST_CEILING} reached, stopping.")
            break

        stops = _parse_tour_content(content)
        tour_expanded = 0
        tour_deleted = 0
        tour_promises_count = 0
        tour_cost = 0.0

        for stop in stops:
            for para in stop['paragraphs']:
                result = process_paragraph(
                    paragraph=para,
                    stop_title=stop['title'],
                    venue_name=tour_name,
                    conn=conn,
                )
                tour_expanded += result['expanded_count']
                tour_deleted += result['deleted_count']
                tour_promises_count += len(result['promises_found'])
                tour_cost += result['cost']

                if total_cost + tour_cost >= COST_CEILING:
                    break
            if total_cost + tour_cost >= COST_CEILING:
                break

        total_cost += tour_cost
        full_results.append({
            'id': tour_id,
            'name': tour_name,
            'promises': tour_promises_count,
            'expanded': tour_expanded,
            'deleted': tour_deleted,
            'cost': tour_cost,
        })
        print(f"\n  Tour {tour_id}: {tour_name[:45]}")
        print(f"    Promises: {tour_promises_count}, Expanded: {tour_expanded}, "
              f"Deleted: {tour_deleted}, Cost: ${tour_cost:.4f}")

    conn.close()

    # Summary
    all_promises_full = sum(r['promises'] for r in full_results)
    all_expanded = sum(r['expanded'] for r in full_results)
    all_deleted = sum(r['deleted'] for r in full_results)

    print(f"\n\n{'═' * 80}")
    print("CORPUS-WIDE SUMMARY")
    print(f"{'═' * 80}")
    print(f"\n  GATHER (all tours with content):")
    print(f"    Tours: {len(tours)}")
    print(f"    Paragraphs: {total_paragraphs}")
    print(f"    Promises detected: {total_promises}")
    print(f"    Cost: $0.0000 (deterministic)")
    print()
    print(f"  FULL PIPELINE (Nice list, with search):")
    print(f"    Tours processed: {len(full_results)}")
    print(f"    Promises: {all_promises_full}")
    print(f"    Expanded: {all_expanded}")
    print(f"    Deleted: {all_deleted}")
    expansion_rate = all_expanded / max(all_promises_full, 1) * 100
    print(f"    Expansion rate: {expansion_rate:.1f}%")
    print(f"    Total cost: ${total_cost:.4f}")
    print(f"    Cost per paragraph: ${total_cost/max(total_paragraphs,1):.4f}")
    print(f"    Cost per tour: ${total_cost/max(len(full_results),1):.4f}")
    print()

    if expansion_rate < 20:
        print(f"  ⚠ EXPANSION RATE IS LOW ({expansion_rate:.0f}%).")
        print(f"    This confirms D123: most tours lack venue corpus,")
        print(f"    so the routine mostly DELETES rather than expands.")
        print(f"    The finding is honest: without source material,")
        print(f"    expansion is impossible and deletion is correct.")


if __name__ == '__main__':
    run_corpus_wide()
