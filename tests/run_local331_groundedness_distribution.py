#!/usr/bin/env python3
"""
LOCAL-331: Measure real groundedness distribution across all scorable tours.

Connects to the DB, loads tour_content for every tour that has a matching
venue in stop_corpus, scores with corpus loaded, and reports the distribution.

Uses accent-folded matching (D243) via stop_corpus_reader._match_stop_to_corpus.
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection, check_db_available
from tour_rubric_scorer import parse_tour, analyze_stop, classify_stop, compute_score, \
    detect_venue_identity, _compute_groundedness_for_stop, StopAnalysis
from stop_corpus_reader import get_stop_corpus_for_tour
from tour_evaluator import evaluate

import re


def extract_venue_name(tour_text):
    """Extract venue name from tour header."""
    first_line = tour_text.split('\n')[0] if tour_text else ''
    m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
    return m.group(1).strip() if m else ''


def main():
    if not check_db_available():
        print("ERROR: Database not reachable")
        sys.exit(1)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all tours with content
    cur.execute("""
        SELECT id, tour_name, number_requested, tour_content 
        FROM audio_tours 
        WHERE tour_content IS NOT NULL 
          AND number_requested > 0
          AND content_language = 'en'
        ORDER BY id
    """)
    tours = cur.fetchall()
    
    print(f"Found {len(tours)} English tours with content")
    print("=" * 80)
    
    all_stop_groundedness = []  # (tour_id, tour_name, stop_title, groundedness, classification)
    tour_summaries = []
    
    for tour_id, tour_name, n_requested, tour_content in tours:
        if not tour_content or not tour_content.strip():
            continue
        
        venue_name = extract_venue_name(tour_content)
        if not venue_name:
            continue
        
        # Parse stops
        stops = parse_tour(tour_content)
        if not stops:
            continue
        
        # Try to load corpus
        stop_names = [s['title'] for s in stops]
        corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)
        
        # Check if ANY stop has corpus
        has_any_corpus = any(v is not None for v in corpus_data.values())
        if not has_any_corpus:
            continue
        
        # Score with corpus
        groundedness_values = []
        stop_details = []
        
        for stop in stops:
            sa = analyze_stop(stop, stops)
            sa.corpus_lookup_attempted = True
            _compute_groundedness_for_stop(sa, stop, corpus_data)
            sa.classification, sa.classification_evidence = classify_stop(sa)
            
            g = sa.groundedness_fraction
            groundedness_values.append(g)
            all_stop_groundedness.append((
                tour_id, tour_name, sa.title, g, sa.classification,
                sa.corpus_available
            ))
            stop_details.append({
                'title': sa.title,
                'groundedness': g,
                'classification': sa.classification,
                'corpus_available': sa.corpus_available,
            })
        
        # Tour-level summary
        measured = [g for g in groundedness_values if g is not None]
        if measured:
            tour_avg = sum(measured) / len(measured)
        else:
            tour_avg = None
        
        # Score the tour
        result = evaluate(tour_content, n_requested, corpus_data=corpus_data)
        total_score = result.score.total_score if result else None
        
        tour_summaries.append({
            'id': tour_id,
            'name': tour_name,
            'n_stops': len(stops),
            'n_with_corpus': sum(1 for s in stop_details if s['corpus_available']),
            'avg_groundedness': tour_avg,
            'score': total_score,
            'stops': stop_details,
        })
    
    conn.close()
    
    # Report
    print(f"\n{'=' * 80}")
    print(f"GROUNDEDNESS DISTRIBUTION — {len(tour_summaries)} tours with corpus")
    print(f"{'=' * 80}")
    
    # Collect all measured groundedness values
    measured_values = [
        (tour_id, tour_name, stop_title, g, cls)
        for tour_id, tour_name, stop_title, g, cls, corpus_avail
        in all_stop_groundedness
        if g is not None and corpus_avail
    ]
    
    if not measured_values:
        print("No stops with measured groundedness found.")
        return
    
    values_only = [g for _, _, _, g, _ in measured_values]
    values_only.sort()
    
    print(f"\nTotal stops with measured groundedness: {len(values_only)}")
    print(f"  Mean:   {sum(values_only)/len(values_only):.3f}")
    print(f"  Median: {values_only[len(values_only)//2]:.3f}")
    print(f"  Min:    {min(values_only):.3f}")
    print(f"  Max:    {max(values_only):.3f}")
    
    # Percentiles
    def percentile(data, p):
        k = (len(data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        return data[f] + (data[c] - data[f]) * (k - f)
    
    print(f"  p10:    {percentile(values_only, 10):.3f}")
    print(f"  p25:    {percentile(values_only, 25):.3f}")
    print(f"  p50:    {percentile(values_only, 50):.3f}")
    print(f"  p75:    {percentile(values_only, 75):.3f}")
    print(f"  p90:    {percentile(values_only, 90):.3f}")
    
    # Distribution buckets
    buckets = defaultdict(int)
    for v in values_only:
        if v == 0.0:
            buckets['0.00 (zero)'] += 1
        elif v < 0.25:
            buckets['0.01-0.24'] += 1
        elif v < 0.40:
            buckets['0.25-0.39'] += 1
        elif v < 0.50:
            buckets['0.40-0.49'] += 1
        elif v < 0.75:
            buckets['0.50-0.74'] += 1
        elif v < 1.00:
            buckets['0.75-0.99'] += 1
        else:
            buckets['1.00 (perfect)'] += 1
    
    print(f"\n  Distribution buckets:")
    for bucket in ['0.00 (zero)', '0.01-0.24', '0.25-0.39', '0.40-0.49', '0.50-0.74', '0.75-0.99', '1.00 (perfect)']:
        count = buckets.get(bucket, 0)
        pct = count / len(values_only) * 100
        bar = '█' * int(pct / 2)
        print(f"    {bucket:>15}: {count:3d} ({pct:5.1f}%) {bar}")
    
    # Stops at 0.00
    zero_stops = [(tid, tn, st, g, cls) for tid, tn, st, g, cls in measured_values if g == 0.0]
    if zero_stops:
        print(f"\n  Stops at 0.00 groundedness ({len(zero_stops)} total):")
        for tid, tn, st, g, cls in zero_stops:
            print(f"    tour={tid} [{cls:>10}] {st}")
    
    # By classification
    print(f"\n  Groundedness by classification:")
    by_cls = defaultdict(list)
    for _, _, _, g, cls in measured_values:
        by_cls[cls].append(g)
    for cls in ['RICH', 'ADEQUATE', 'THIN', 'CONTRADICTED']:
        if cls in by_cls:
            vals = by_cls[cls]
            print(f"    {cls:>12}: n={len(vals):3d}  mean={sum(vals)/len(vals):.3f}  "
                  f"min={min(vals):.3f}  max={max(vals):.3f}")
    
    # Per-tour scores with corpus
    print(f"\n{'=' * 80}")
    print(f"PER-TOUR SCORES (with corpus loaded)")
    print(f"{'=' * 80}")
    
    for t in sorted(tour_summaries, key=lambda x: x['id']):
        score_str = f"{t['score']:.1f}" if t['score'] is not None else "N/A"
        avg_g = f"{t['avg_groundedness']:.3f}" if t['avg_groundedness'] is not None else "N/A"
        print(f"\n  Tour {t['id']:3d}: {t['name'][:60]}")
        print(f"    Score: {score_str}  |  Avg groundedness: {avg_g}  |  "
              f"Corpus: {t['n_with_corpus']}/{t['n_stops']} stops")
        for s in t['stops']:
            g_str = f"{s['groundedness']:.3f}" if s['groundedness'] is not None else "None"
            corpus_str = "✓" if s['corpus_available'] else "✗"
            print(f"      [{s['classification']:>10}] g={g_str} corpus={corpus_str}  {s['title'][:45]}")
    
    # Threshold proposal
    print(f"\n{'=' * 80}")
    print(f"THRESHOLD PROPOSAL FOR ADEQUATE")
    print(f"{'=' * 80}")
    
    p25 = percentile(values_only, 25)
    adequate_vals = by_cls.get('ADEQUATE', [])
    if adequate_vals:
        adequate_p25 = percentile(sorted(adequate_vals), 25)
    else:
        adequate_p25 = None
    
    rounded_p25 = round(p25 * 20) / 20
    
    print(f"\nCurrent state:")
    print(f"  - RICH requires groundedness >= 0.40 (RICH_MIN_GROUNDEDNESS)")
    print(f"  - ADEQUATE has NO groundedness floor — any groundedness is accepted")
    print(f"  - {len(zero_stops)} stops sit at 0.00 groundedness and remain ADEQUATE")
    print(f"\nDistribution-based proposal:")
    print(f"  - Overall p25 = {p25:.3f}")
    if adequate_p25 is not None:
        print(f"  - ADEQUATE stops p25 = {adequate_p25:.3f}")
    print(f"  - Proposed ADEQUATE floor: p25 of measured distribution = {p25:.3f}")
    print(f"    (round to nearest 0.05: {rounded_p25:.2f})")
    print(f"")
    print(f"  A floor at {rounded_p25:.2f} would cap to THIN any stop whose")
    print(f"  measured groundedness falls below that — meaning our corpus does not")
    print(f"  support even a quarter of its claims.")
    print(f"")
    print(f"  NOTE: A 0.00 stop is NOT proven fabricated (LOCAL-309). It means our")
    print(f"  sources do not support its claims — which may mean the claim is wrong,")
    print(f"  or that our corpus is thin for that stop.")


if __name__ == '__main__':
    main()
