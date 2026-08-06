#!/usr/bin/env python3
"""run_local291_adjudication.py — LOCAL-291 Tier 3: External adjudication.

For claims still UNGROUNDED after groundedness check, performs batched
Wikipedia/Wikidata verification to determine:
- SUPPORTED: claim verified by external source → remains UNGROUNDED (not false)
- CONTRADICTED: external source contradicts claim → upgrades to CONTRADICTED
- NOT_FOUND: no external evidence either way → remains UNGROUNDED

Only CONTRADICTED maps to the CONTRADICTED classification. NOT_FOUND stays
UNGROUNDED. SUPPORTED stays UNGROUNDED (unverified by our corpus).

Budget: ~2-3 claims per stop. Reports actual cost per tour.
Hard limit: if measured cost exceeds $0.05/tour, stop and report.
"""
import os
import sys
import json
import re
import time
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_connection
from groundedness_check import measure_tour_groundedness, extract_fact_claims
from stop_corpus_reader import get_stop_corpus_for_tour
from tour_rubric_scorer import parse_tour


# ─── Cost tracking ──────────────────────────────────────────────────────────

# Serper API cost per query (from cost_rates.py)
try:
    from cost_rates import SERPER_COST_PER_QUERY
except ImportError:
    SERPER_COST_PER_QUERY = 0.001  # $0.001 per query (Serper Google Search)

# GPT-4o cost for evaluation (not used — we use rule-based matching)
# The task specification says "one batched call per stop against fetched
# Wikipedia/Wikidata" — this means Serper search + fetch, not LLM evaluation.
COST_PER_STOP_BUDGET = 3  # max claims adjudicated per stop


def adjudicate_claims(
    ungrounded_claims: List[Dict],
    stop_title: str,
    venue_context: str = "",
    max_claims: int = COST_PER_STOP_BUDGET,
) -> Dict:
    """Adjudicate ungrounded claims against Wikipedia/Wikidata.

    Uses external_claim_verify.verify_unsupported_claims which:
    - Builds search queries from claim + context
    - Fetches Wikipedia/Wikidata pages
    - Evaluates evidence with rule-based matching (no LLM cost)

    Returns:
        {
            'results': [{claim_text, verdict, url, evidence}],
            'queries_issued': int,
            'cost': float,
            'supported_count': int,
            'contradicted_count': int,
            'not_found_count': int,
        }
    """
    try:
        from external_claim_verify import (
            verify_unsupported_claims,
            is_external_verify_enabled,
        )
    except ImportError as e:
        return {
            'results': [],
            'queries_issued': 0,
            'cost': 0.0,
            'supported_count': 0,
            'contradicted_count': 0,
            'not_found_count': len(ungrounded_claims),
            'error': f'external_claim_verify not available: {e}',
        }

    if not is_external_verify_enabled():
        return {
            'results': [],
            'queries_issued': 0,
            'cost': 0.0,
            'supported_count': 0,
            'contradicted_count': 0,
            'not_found_count': len(ungrounded_claims),
            'error': 'DISABLE_EXTERNAL_VERIFY=1 is set',
        }

    # Limit to max_claims per stop
    claims_to_check = ungrounded_claims[:max_claims]

    # Format claims for verify_unsupported_claims
    formatted_claims = []
    for claim_info in claims_to_check:
        formatted_claims.append({
            'text': claim_info['claim_text'],
            'type': claim_info.get('claim_type', 'DATE').upper(),
            'sentence': claim_info.get('sentence', ''),
            'verdict': 'UNSUPPORTED',
        })

    if not formatted_claims:
        return {
            'results': [],
            'queries_issued': 0,
            'cost': 0.0,
            'supported_count': 0,
            'contradicted_count': 0,
            'not_found_count': 0,
        }

    # Run external verification
    result = verify_unsupported_claims(
        claims=formatted_claims,
        stop_title=stop_title,
        venue_name=venue_context,
        query_budget=max_claims,  # one query per claim max
    )

    # Map verdicts: SUPPORTED_EXTERNAL → supported, else not_found
    # (only "contradicted" from external sources would map to CONTRADICTED)
    supported = 0
    contradicted = 0
    not_found = 0
    adjudicated_results = []

    for r in result.get('results', []):
        ext_verdict = r.get('verdict', 'UNSUPPORTED')
        if ext_verdict == 'SUPPORTED_EXTERNAL':
            supported += 1
            adjudicated_results.append({
                'claim_text': r['claim_text'],
                'external_verdict': 'SUPPORTED',
                'url': r.get('url', ''),
                'evidence': r.get('supporting_sentence', ''),
            })
        elif ext_verdict == 'CONTRADICTED_EXTERNAL':
            contradicted += 1
            adjudicated_results.append({
                'claim_text': r['claim_text'],
                'external_verdict': 'CONTRADICTED',
                'url': r.get('url', ''),
                'evidence': r.get('supporting_sentence', ''),
            })
        else:
            not_found += 1
            adjudicated_results.append({
                'claim_text': r['claim_text'],
                'external_verdict': 'NOT_FOUND',
                'url': '',
                'evidence': '',
            })

    # Add remaining claims that weren't checked
    not_found += len(ungrounded_claims) - len(claims_to_check)

    return {
        'results': adjudicated_results,
        'queries_issued': result.get('queries_issued', 0),
        'cost': result.get('cost', 0.0),
        'supported_count': supported,
        'contradicted_count': contradicted,
        'not_found_count': not_found,
    }


def run_adjudication_measurement():
    """Run adjudication on the measured tours and report cost."""
    print("=" * 70)
    print("LOCAL-291 Tier 3: External Adjudication (cost measurement)")
    print("=" * 70)

    conn = get_connection()
    tours_dir = '/Users/micha/Audioura/tours'

    # Use a small sample for cost measurement (2 tours)
    sample_tours = [
        ('LOCAL289_riviera_8stop_round35.txt', 'French Riviera walking area'),
        ('Asian_arts_museum__nice__France_museum_tour_20260801_105029.txt',
         'Musee des Arts Asiatiques (Asian Art Museum), Nice, France'),
    ]

    total_cost = 0.0
    total_queries = 0
    total_adjudicated = 0
    total_supported = 0
    total_contradicted = 0
    total_not_found = 0

    for filename, venue_name in sample_tours:
        filepath = os.path.join(tours_dir, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP: {filename} not found")
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            tour_text = f.read()

        print(f"\n  Tour: {filename}")

        # Get groundedness data
        result = measure_tour_groundedness(tour_text, venue_name, conn)
        if 'error' in result:
            print(f"  ERROR: {result['error']}")
            continue

        tour_cost = 0.0
        tour_queries = 0

        for stop_result in result['stops']:
            if not stop_result.corpus_worklist:
                continue

            adj = adjudicate_claims(
                stop_result.corpus_worklist,
                stop_result.stop_title,
                venue_context=venue_name,
                max_claims=COST_PER_STOP_BUDGET,
            )

            tour_cost += adj['cost']
            tour_queries += adj['queries_issued']
            total_adjudicated += len(adj['results'])
            total_supported += adj['supported_count']
            total_contradicted += adj['contradicted_count']
            total_not_found += adj['not_found_count']

            if adj.get('error'):
                print(f"    {stop_result.stop_title[:30]}: {adj['error']}")
            elif adj['queries_issued'] > 0:
                print(f"    {stop_result.stop_title[:30]}: "
                      f"queries={adj['queries_issued']}, cost=${adj['cost']:.4f}, "
                      f"supported={adj['supported_count']}, "
                      f"contradicted={adj['contradicted_count']}, "
                      f"not_found={adj['not_found_count']}")

        total_cost += tour_cost
        total_queries += tour_queries
        print(f"  Tour cost: ${tour_cost:.4f} ({tour_queries} queries)")

        # Check hard limit
        if tour_cost > 0.05:
            print(f"\n  ⚠ COST LIMIT EXCEEDED: ${tour_cost:.4f} > $0.05/tour")
            print(f"  Stopping adjudication measurement.")
            break

    print(f"\n{'═' * 70}")
    print(f"  ADJUDICATION COST REPORT")
    print(f"{'═' * 70}")
    print(f"  Tours sampled: {len(sample_tours)}")
    print(f"  Total queries: {total_queries}")
    print(f"  Total cost: ${total_cost:.4f}")
    print(f"  Avg cost per tour: ${total_cost / max(1, len(sample_tours)):.4f}")
    print(f"  Claims adjudicated: {total_adjudicated}")
    print(f"    Supported: {total_supported}")
    print(f"    Contradicted: {total_contradicted}")
    print(f"    Not found: {total_not_found}")

    if total_cost / max(1, len(sample_tours)) > 0.05:
        print(f"\n  ⛔ EXCEEDS $0.05/tour limit — not shipping adjudication live.")
    else:
        print(f"\n  ✓ Within $0.05/tour budget.")

    conn.close()
    return {
        'total_cost': total_cost,
        'avg_cost_per_tour': total_cost / max(1, len(sample_tours)),
        'total_queries': total_queries,
        'adjudicated': total_adjudicated,
        'supported': total_supported,
        'contradicted': total_contradicted,
        'not_found': total_not_found,
    }


if __name__ == '__main__':
    run_adjudication_measurement()
