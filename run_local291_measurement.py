#!/usr/bin/env python3
"""run_local291_measurement.py — LOCAL-291: Groundedness measurement post-289/290.

Re-measures the grounded/ungrounded split on ≥5 Riviera tours and ≥2 museum tours,
after LOCAL-289 and LOCAL-290 merges have changed the corpus.

Reports:
- Per-tour and aggregate groundedness fraction
- CONTRADICTED rate (from claim_check.py)
- Ungrounded claims as a corpus worklist
- Name normalisation effect (before vs after)
"""
import os
import sys
import json
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_connection
from groundedness_check import (
    measure_tour_groundedness,
    extract_fact_claims,
    check_claim_grounded,
    normalize_name,
    names_match,
    measure_stop_groundedness,
)
from stop_corpus_reader import get_stop_corpus_for_tour
from claim_check import check_paragraph, CONTRADICTED


TOURS_DIR = '/Users/micha/Audioura/tours'


def find_recent_riviera_tours(n=7):
    """Find the N most recent Riviera .txt tours."""
    candidates = []
    for f in os.listdir(TOURS_DIR):
        if not f.endswith('.txt'):
            continue
        if 'riviera' in f.lower() or 'Riviera' in f:
            path = os.path.join(TOURS_DIR, f)
            candidates.append((os.path.getmtime(path), f))
    candidates.sort(reverse=True)
    return [f for _, f in candidates[:n]]


def find_recent_museum_tours(n=4):
    """Find the N most recent museum .txt tours with corpus coverage."""
    # Prefer Asian arts museum and MAMAC as they have the best corpus
    preferred = []
    others = []
    for f in os.listdir(TOURS_DIR):
        if not f.endswith('.txt'):
            continue
        if 'museum' in f.lower() or 'Museum' in f:
            path = os.path.join(TOURS_DIR, f)
            if 'asian' in f.lower() or 'Asian' in f or 'matisse' in f.lower() or 'Matisse' in f:
                preferred.append((os.path.getmtime(path), f))
            elif 'mamac' in f.lower() or 'MAMAC' in f or 'Moderne' in f.lower():
                preferred.append((os.path.getmtime(path), f))
            else:
                others.append((os.path.getmtime(path), f))
    preferred.sort(reverse=True)
    others.sort(reverse=True)
    result = [f for _, f in preferred[:n]]
    if len(result) < n:
        result.extend([f for _, f in others[:n - len(result)]])
    return result


def detect_venue_name(filename: str, tour_text: str) -> str:
    """Detect the venue/area name for corpus lookup."""
    fname_lower = filename.lower()
    text_lower = tour_text[:500].lower()

    if 'riviera' in fname_lower or 'riviera' in text_lower:
        return 'French Riviera walking area'
    if 'asian' in fname_lower or 'asiatiques' in text_lower:
        return 'Musee des Arts Asiatiques (Asian Art Museum), Nice, France'
    if 'matisse' in fname_lower or 'matisse' in text_lower:
        return 'Musee Matisse, Nice, France'
    if 'mamac' in fname_lower or 'moderne' in fname_lower or 'contemporain' in text_lower:
        return 'Musee d Art Moderne et d Art Contemporain, Nice, France'
    if 'chagall' in fname_lower or 'chagall' in text_lower:
        return 'Musee National Marc Chagall, Nice, France'
    if 'lascaris' in fname_lower or 'lascaris' in text_lower:
        return 'Palais Lascaris, Nice'
    if 'naif' in fname_lower or 'naive' in fname_lower or 'naif' in text_lower:
        return "Musée d'art naïf (Museum of Naïve Art), Nice, France"
    if 'boston' in fname_lower or 'common' in fname_lower:
        return 'Boston Common, Boston MA'
    if 'constitution' in fname_lower or 'philadelphia' in fname_lower:
        return 'National Constitution Center, Philadelphia PA'
    # Default for riviera area tours
    if any(kw in text_lower for kw in ['nice', 'antibes', 'cannes', 'monaco', 'eze']):
        return 'French Riviera walking area'
    return ''


from typing import List


def run_contradicted_check(stop_text: str, stop_title: str, passages: List, venue_name: str = "") -> dict:
    """Run claim_check to get CONTRADICTED counts for a stop."""
    if not passages:
        return {'contradicted': 0, 'supported': 0, 'unsupported': 0, 'total': 0, 'claims': []}

    result = check_paragraph(
        text=stop_text,
        stop_title=stop_title,
        venue_name=venue_name,
        passages=passages,
    )
    return {
        'contradicted': result['verdict_counts']['contradicted'],
        'supported': result['verdict_counts']['supported'],
        'unsupported': result['verdict_counts']['unsupported'],
        'total': len(result['claims']),
        'claims': result['claims'],
    }


def main():
    print("=" * 70)
    print("LOCAL-291: Groundedness Measurement (post-289/290)")
    print("=" * 70)

    conn = get_connection()

    # Find tours
    riviera_tours = find_recent_riviera_tours(7)
    museum_tours = find_recent_museum_tours(4)

    print(f"\nRiviera tours found: {len(riviera_tours)}")
    for f in riviera_tours:
        print(f"  {f}")
    print(f"\nMuseum tours found: {len(museum_tours)}")
    for f in museum_tours:
        print(f"  {f}")

    all_tours = [(f, 'riviera') for f in riviera_tours] + [(f, 'museum') for f in museum_tours]

    if len(riviera_tours) < 5:
        print(f"\n⚠ Only {len(riviera_tours)} Riviera tours found (need ≥5)")
    if len(museum_tours) < 2:
        print(f"\n⚠ Only {len(museum_tours)} museum tours found (need ≥2)")

    # Aggregate counters
    all_claims = 0
    all_grounded = 0
    all_ungrounded = 0
    all_contradicted_groundedness = 0  # from groundedness check
    all_contradicted_claimcheck = 0    # from claim_check CONTRADICTED block
    all_stops_measured = 0
    per_stop_groundedness = []
    full_worklist = []
    name_norm_saves = 0  # claims rescued by name normalisation

    tour_results = []

    for filename, category in all_tours:
        filepath = os.path.join(TOURS_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            tour_text = f.read()

        venue_name = detect_venue_name(filename, tour_text)
        if not venue_name:
            print(f"\n  SKIP {filename}: cannot determine venue name")
            continue

        print(f"\n{'─' * 60}")
        print(f"  Tour: {filename}")
        print(f"  Category: {category}, Venue: {venue_name}")

        result = measure_tour_groundedness(tour_text, venue_name, conn)

        if 'error' in result:
            print(f"  ERROR: {result['error']}")
            continue

        # Also run claim_check CONTRADICTED check on each stop
        stop_names = [s.stop_title for s in result['stops']]
        corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)
        contradicted_from_claimcheck = 0

        for stop_result in result['stops']:
            corpus_entry = corpus_data.get(stop_result.stop_title)
            passages = corpus_entry['passages'] if corpus_entry else []
            if passages and stop_result.total_claims > 0:
                # Find the stop body text — reconstruct from the tour
                # (We need the original text for claim_check)
                cc_result = run_contradicted_check(
                    # Use the claims' sentences as proxy for stop text
                    ' '.join(d['sentence'] for d in stop_result.claims_detail),
                    stop_result.stop_title,
                    passages,
                    venue_name,
                )
                contradicted_from_claimcheck += cc_result['contradicted']

        all_contradicted_claimcheck += contradicted_from_claimcheck

        # Accumulate
        all_claims += result['total_claims']
        all_grounded += result['total_grounded']
        all_ungrounded += result['total_ungrounded']
        all_contradicted_groundedness += result['total_contradicted']
        full_worklist.extend(result['corpus_worklist'])

        for stop_result in result['stops']:
            if stop_result.total_claims > 0:
                all_stops_measured += 1
                per_stop_groundedness.append(stop_result.groundedness_fraction)

        print(f"  Stops: {len(result['stops'])}, "
              f"Claims: {result['total_claims']}, "
              f"Grounded: {result['total_grounded']}, "
              f"Ungrounded: {result['total_ungrounded']}, "
              f"Contradicted(corpus): {result['total_contradicted']}")
        print(f"  Groundedness: {result['overall_groundedness']:.1%}")
        print(f"  CONTRADICTED (claim_check): {contradicted_from_claimcheck}")

        # Per-stop detail
        for sr in result['stops']:
            if sr.total_claims > 0:
                corpus_entry = corpus_data.get(sr.stop_title)
                has_corpus = '✓' if corpus_entry else '✗'
                print(f"    {has_corpus} {sr.stop_title[:35]:35s}  "
                      f"{sr.grounded_claims}/{sr.total_claims} grounded "
                      f"({sr.groundedness_fraction:.0%})")

        tour_results.append({
            'filename': filename,
            'category': category,
            'venue': venue_name,
            'total_claims': result['total_claims'],
            'grounded': result['total_grounded'],
            'ungrounded': result['total_ungrounded'],
            'groundedness': result['overall_groundedness'],
            'contradicted_claimcheck': contradicted_from_claimcheck,
        })

    # ─── Aggregates ──────────────────────────────────────────────────────────
    print(f"\n{'═' * 70}")
    print(f"  AGGREGATE RESULTS")
    print(f"{'═' * 70}")
    print(f"  Tours measured: {len(tour_results)}")
    print(f"    Riviera: {sum(1 for t in tour_results if t['category'] == 'riviera')}")
    print(f"    Museum:  {sum(1 for t in tour_results if t['category'] == 'museum')}")
    print(f"  Stops measured: {all_stops_measured}")
    print(f"  Total claims: {all_claims}")
    print(f"  Grounded: {all_grounded} ({all_grounded/max(1,all_claims):.1%})")
    print(f"  Ungrounded: {all_ungrounded} ({all_ungrounded/max(1,all_claims):.1%})")
    print(f"  CONTRADICTED (claim_check): {all_contradicted_claimcheck}")
    print(f"  Overall groundedness: {all_grounded/max(1,all_claims):.1%}")

    # Per-stop distribution
    if per_stop_groundedness:
        sorted_g = sorted(per_stop_groundedness)
        n = len(sorted_g)
        p25 = sorted_g[int(n * 0.25)]
        p50 = sorted_g[int(n * 0.50)]
        p75 = sorted_g[int(n * 0.75)]
        p10 = sorted_g[int(n * 0.10)]
        print(f"\n  Per-stop groundedness distribution (n={n}):")
        print(f"    p10={p10:.2f}  p25={p25:.2f}  median={p50:.2f}  p75={p75:.2f}")

    # Contradicted rate
    if all_claims > 0:
        print(f"\n  CONTRADICTED rate: {all_contradicted_claimcheck}/{all_claims} "
              f"= {all_contradicted_claimcheck/all_claims:.2%}")

    # Corpus worklist summary
    print(f"\n  Corpus worklist: {len(full_worklist)} ungrounded claims")
    if full_worklist:
        # Group by stop
        by_stop = defaultdict(list)
        for item in full_worklist:
            by_stop[item['stop_title']].append(item)
        print(f"  Across {len(by_stop)} distinct stops")
        # Show top stops
        top_stops = sorted(by_stop.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        for stop_title, items in top_stops:
            print(f"    {stop_title[:40]:40s} — {len(items)} ungrounded claims")
            for item in items[:3]:
                print(f"      [{item['claim_type']}] {item['claim_text'][:50]}")

    # ─── Groundedness floor recommendation ───────────────────────────────────
    if per_stop_groundedness:
        # The floor is the threshold below which a stop cannot be RICH.
        # Choose based on the measured distribution: stops below p25 should not
        # be RICH. This is a ceiling, not a penalty.
        recommended_floor = p25
        print(f"\n  RECOMMENDED groundedness floor for RICH ceiling: {recommended_floor:.2f}")
        print(f"  (Based on p25 of per-stop distribution — "
              f"stops below this cannot be RICH)")
        # How many stops would be capped?
        capped = sum(1 for g in per_stop_groundedness if g < recommended_floor)
        print(f"  Would cap {capped}/{n} stops ({capped/n:.0%}) from reaching RICH")

    # Write worklist to file for LOCAL-283 harvester
    worklist_path = os.path.join(os.path.dirname(__file__), 'local291_corpus_worklist.json')
    with open(worklist_path, 'w') as f:
        json.dump(full_worklist, f, indent=2)
    print(f"\n  Worklist written to: {worklist_path}")

    conn.close()

    # Return data for use by the integration
    return {
        'tour_results': tour_results,
        'overall_groundedness': all_grounded / max(1, all_claims),
        'contradicted_rate': all_contradicted_claimcheck / max(1, all_claims),
        'per_stop_distribution': per_stop_groundedness,
        'recommended_floor': p25 if per_stop_groundedness else 0.5,
        'worklist_size': len(full_worklist),
    }


if __name__ == '__main__':
    main()
