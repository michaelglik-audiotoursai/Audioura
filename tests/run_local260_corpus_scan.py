#!/usr/bin/env python3
"""
LOCAL-260: Corpus-wide prolog structure scan.

Reads ALL tours from audio_tours (read-only), extracts the prolog,
and reports how many have a conforming four-part opening.

Expected result: near zero conformance (the four-part specification
was not enforced by any prior check).

This is DETERMINISTIC and FREE — no LLM calls.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection, check_db_available
from prolog_structure_validator import (
    validate_prolog_structure,
    extract_prolog_from_tour_content,
    extract_stop_names_from_tour_content,
    extract_transport_mode_from_tour_content,
)


def run_corpus_scan():
    """Scan all tours in audio_tours and report prolog conformance."""
    print("=" * 70)
    print("LOCAL-260: CORPUS-WIDE PROLOG STRUCTURE SCAN")
    print("=" * 70)
    print()
    
    if not check_db_available():
        print("  DATABASE UNAVAILABLE — cannot run corpus scan.")
        print("  This is expected if Docker is not running.")
        sys.exit(0)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Count BEFORE (prove read-only)
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_before = cur.fetchone()[0]
    print(f"  audio_tours row count BEFORE: {count_before}")
    
    # Fetch all tours with content
    cur.execute("""
        SELECT id, tour_name, tour_content, request_string
        FROM audio_tours 
        WHERE tour_content IS NOT NULL 
          AND LENGTH(tour_content) > 100
        ORDER BY id
    """)
    tours = cur.fetchall()
    print(f"  Tours with content: {len(tours)}")
    print()
    
    conforming = 0
    non_conforming = 0
    no_prolog = 0
    results = []
    
    for tour_id, tour_name, tour_content, request_string in tours:
        # Extract prolog
        prolog = extract_prolog_from_tour_content(tour_content)
        
        if not prolog or len(prolog.strip()) < 20:
            no_prolog += 1
            results.append({
                'id': tour_id,
                'name': tour_name or request_string or f'tour_{tour_id}',
                'status': 'NO_PROLOG',
                'errors': 0,
                'violations': [],
            })
            continue
        
        # Extract meta
        stop_names = extract_stop_names_from_tour_content(tour_content)
        transport_mode = extract_transport_mode_from_tour_content(tour_content)
        
        meta = {
            'transport_mode': transport_mode,
            'tour_name': tour_name or request_string or '',
            'stop_names': stop_names,
        }
        
        # Validate
        violations = validate_prolog_structure(prolog, meta)
        errors = [v for v in violations if v['severity'] == 'error']
        
        if len(errors) == 0:
            conforming += 1
            status = 'CONFORMING'
        else:
            non_conforming += 1
            status = 'NON_CONFORMING'
        
        results.append({
            'id': tour_id,
            'name': tour_name or request_string or f'tour_{tour_id}',
            'status': status,
            'errors': len(errors),
            'violations': violations,
        })
    
    # Report
    print("─" * 70)
    print("RESULTS SUMMARY")
    print("─" * 70)
    total_scanned = conforming + non_conforming + no_prolog
    print(f"  Total tours scanned: {total_scanned}")
    print(f"  Conforming (0 errors):  {conforming} ({conforming*100//max(total_scanned,1)}%)")
    print(f"  Non-conforming:         {non_conforming} ({non_conforming*100//max(total_scanned,1)}%)")
    print(f"  No prolog detected:     {no_prolog}")
    print()
    
    # Per-tour detail
    print("─" * 70)
    print("PER-TOUR DETAIL")
    print("─" * 70)
    for r in results:
        status_marker = '✓' if r['status'] == 'CONFORMING' else '✗' if r['status'] == 'NON_CONFORMING' else '—'
        print(f"  {status_marker} Tour {r['id']:>4} [{r['status']:<15}] {r['name'][:50]}")
        if r['violations']:
            for v in r['violations']:
                if v['severity'] == 'error':
                    print(f"        Part {v['part']}: {v['code']}")
    print()
    
    # Violation frequency
    print("─" * 70)
    print("VIOLATION FREQUENCY (errors only)")
    print("─" * 70)
    from collections import Counter
    violation_counts = Counter()
    for r in results:
        for v in r['violations']:
            if v['severity'] == 'error':
                violation_counts[v['code']] += 1
    for code, count in violation_counts.most_common():
        print(f"  {code:<30} {count:>4} tours")
    print()
    
    # Count AFTER (prove read-only)
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_after = cur.fetchone()[0]
    print(f"  audio_tours row count AFTER: {count_after}")
    assert count_before == count_after, \
        f"ROW COUNT CHANGED! {count_before} → {count_after} — THIS MUST NEVER HAPPEN"
    print(f"  ✓ Row count unchanged ({count_before} == {count_after})")
    
    # Cost report
    print()
    print("─" * 70)
    print("COST REPORT")
    print("─" * 70)
    print("  LLM calls: 0")
    print("  Total cost: $0.00")
    print("  This check is DETERMINISTIC AND FREE — pure regex/NLP, no model calls.")
    print()
    
    conn.close()
    
    return {
        'conforming': conforming,
        'non_conforming': non_conforming,
        'no_prolog': no_prolog,
        'total': total_scanned,
    }


if __name__ == '__main__':
    run_corpus_scan()
