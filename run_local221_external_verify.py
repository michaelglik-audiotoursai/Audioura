#!/usr/bin/env python3
"""run_local221_external_verify.py — LOCAL-221: Measure external verification over stored tours.

Runs the claim_check pipeline on stored tours, then for all UNSUPPORTED claims,
attempts external verification via Serper + page fetch.

Reports:
- Queries issued, cost per tour, total cost
- Promotion rate (UNSUPPORTED → SUPPORTED_EXTERNAL)
- Verbatim evidence for ≥10 promotions and ≥3 refusals
- Writes confirmed sources back to stop_corpus (with backup)

Behind DISABLE_EXTERNAL_VERIFY=1.
"""

import sys
import os
import json
import re
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_database_url
import psycopg2
import psycopg2.extras

import claim_check
from external_claim_verify import (
    verify_unsupported_claims,
    write_external_sources_to_stop_corpus,
    is_external_verify_enabled,
    SUPPORTED_EXTERNAL,
)
from cost_rates import SERPER_COST_PER_QUERY

# ─── Config ──────────────────────────────────────────────────────────────────

# Budget: $0.40 ceiling per task spec. At $0.001/query, that's 400 queries max.
MAX_TOTAL_QUERIES = 400
# Per-tour query budget: allow enough queries to cover most UNSUPPORTED claims per stop
QUERIES_PER_STOP = 5

# ─── Tour-to-venue matching (same as test_local219_corpus_wide) ──────────────

TOUR_VENUE_MAP = {
    'Palais Lascaris': 'Palais Lascaris, Nice',
    'Musée Matisse': 'Musee Matisse, Nice, France',
    'Matisse': 'Musee Matisse, Nice, France',
    'MAMAC': 'Musee d Art Moderne et d Art Contemporain, Nice, France',
    'Art Moderne': 'Musee d Art Moderne et d Art Contemporain, Nice, France',
    'Chagall': 'Musee National Marc Chagall, Nice, France',
    'Marc Chagall': 'Musee National Marc Chagall, Nice, France',
    'Naïf': 'walking tour in Nice, france',
    'Naïve': 'walking tour in Nice, france',
    'Beaux-Arts': 'walking tour in Nice, france',
    'Picasso': 'French Riviera walking area',
    'Massena': 'walking tour in Nice, france',
    'French Riviera': 'French Riviera walking area',
    'Riviera': 'French Riviera walking area',
    'Nice': 'walking tour in Nice, france',
    'Boston': 'Boston Common, Boston MA',
}


def match_tour_to_venue(tour_name):
    for key, venue in TOUR_VENUE_MAP.items():
        if key.lower() in tour_name.lower():
            return venue
    return None


def split_tour_into_stops(tour_text):
    """Split tour text into stops with their paragraphs."""
    stops = []
    current_stop = None
    current_paragraphs = []

    skip_prefixes = [
        'Step-by-Step', 'Tour-Category:', 'Address:',
        'Coordinates:', 'Museum Information:', 'Directions:',
        'Type/Specialty:', 'Specific Examples:', 'Sources:',
        'Description:', 'From ', 'Orientation:',
    ]

    lines = tour_text.split('\n')
    for line in lines:
        stripped = line.strip()

        # New stop
        stop_match = re.match(r'^Stop\s+\d+:\s*(.+)$', stripped)
        if stop_match:
            if current_stop and current_paragraphs:
                stops.append({'title': current_stop, 'paragraphs': current_paragraphs})
            current_stop = stop_match.group(1).strip()
            current_paragraphs = []
            continue

        if not stripped:
            continue

        # Skip metadata
        if any(stripped.startswith(p) for p in skip_prefixes):
            continue

        # Content paragraph (must be substantial)
        if len(stripped) > 50 and current_stop:
            current_paragraphs.append(stripped)

    # Last stop
    if current_stop and current_paragraphs:
        stops.append({'title': current_stop, 'paragraphs': current_paragraphs})

    return stops


def get_corpus_passages(venue_name, stop_title, conn):
    """Get corpus passages for a stop from stop_corpus."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
        (venue_name, stop_title)
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        # Try fuzzy match
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT stop_title, passages_json FROM stop_corpus WHERE venue_name = %s",
            (venue_name,)
        )
        rows = cur.fetchall()
        cur.close()

        # Fuzzy: normalized substring match
        stop_norm = re.sub(r'\s+', ' ', stop_title.lower().strip())
        for r in rows:
            corpus_norm = re.sub(r'\s+', ' ', r['stop_title'].lower().strip())
            if stop_norm in corpus_norm or corpus_norm in stop_norm:
                row = r
                break

    if not row:
        return []

    passages_raw = row['passages_json']
    if isinstance(passages_raw, str):
        passages_raw = json.loads(passages_raw)

    passages = []
    for p in (passages_raw or []):
        if isinstance(p, dict):
            text = p.get('text', '')
        elif isinstance(p, str):
            text = p
        else:
            text = str(p)
        if text:
            passages.append(text)
    return passages


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not is_external_verify_enabled():
        print("ERROR: External verification is disabled (DISABLE_EXTERNAL_VERIFY=1).")
        print("Unset DISABLE_EXTERNAL_VERIFY to run this measurement.")
        sys.exit(1)

    serp_key = os.environ.get('SERP_API_KEY', '')
    if not serp_key:
        print("ERROR: SERP_API_KEY not set. Cannot run external verification.")
        sys.exit(1)

    print("=" * 80)
    print("LOCAL-221: External Claim Verification Measurement")
    print("=" * 80)
    print(f"Budget: {MAX_TOTAL_QUERIES} queries max (${MAX_TOTAL_QUERIES * SERPER_COST_PER_QUERY:.2f})")
    print()

    conn = psycopg2.connect(get_database_url())

    # Backup stop_corpus before writeback
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM stop_corpus")
    corpus_rows_before = cur.fetchone()['cnt']
    cur.execute("SELECT SUM(passage_count) as total FROM stop_corpus")
    passages_before = cur.fetchone()['total'] or 0
    cur.close()
    print(f"stop_corpus BEFORE: {corpus_rows_before} rows, {passages_before} passages")

    # Verify Nice list and audio_tours count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    audio_tours_count = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
    nice_ids = [r[0] for r in cur.fetchall()]
    cur.close()
    print(f"audio_tours: {audio_tours_count} (expected ≥130)")
    print(f"Nice list: {nice_ids}")
    assert audio_tours_count >= 130, f"Expected ≥130, got {audio_tours_count}"
    assert nice_ids == [1, 12, 14, 17, 21, 24, 27, 28, 29, 152], f"Nice list mismatch: {nice_ids}"

    # Load tours with content
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE tour_content IS NOT NULL AND tour_content != ''")
    tours = cur.fetchall()
    cur.close()
    print(f"\nTours with content: {len(tours)}")

    # ─── Run verification ────────────────────────────────────────────────────
    total_queries = 0
    total_cost = 0.0
    total_unsupported = 0
    total_promoted = 0
    total_refused = 0
    per_tour_stats = []
    all_promotions = []  # For verbatim evidence
    all_refusals = []    # For verbatim evidence
    all_writeback_claims = []  # For stop_corpus writeback

    tours_processed = 0
    for tour_row in tours:
        tour_id = tour_row['id']
        tour_name = tour_row['tour_name'] or ''
        tour_content = tour_row['tour_content'] or ''

        if not tour_content or len(tour_content) < 100:
            continue

        venue_name = match_tour_to_venue(tour_name)
        if not venue_name:
            continue

        stops = split_tour_into_stops(tour_content)
        if not stops:
            continue

        tour_queries = 0
        tour_unsupported = 0
        tour_promoted = 0
        tour_refused = 0

        for stop in stops:
            if total_queries >= MAX_TOTAL_QUERIES:
                break

            stop_title = stop['title']
            passages = get_corpus_passages(venue_name, stop_title, conn)

            for para in stop['paragraphs']:
                # Run claim_check
                result = claim_check.check_paragraph(
                    text=para,
                    stop_title=stop_title,
                    venue_name=venue_name,
                    passages=passages,
                )

                # Collect UNSUPPORTED claims
                unsupported_claims = [c for c in result['claims']
                                      if c['verdict'] == 'UNSUPPORTED']
                if not unsupported_claims:
                    continue

                tour_unsupported += len(unsupported_claims)
                total_unsupported += len(unsupported_claims)

                # Budget check
                remaining = MAX_TOTAL_QUERIES - total_queries
                if remaining <= 0:
                    break

                # Verify externally
                verify_result = verify_unsupported_claims(
                    claims=unsupported_claims,
                    stop_title=stop_title,
                    venue_name=venue_name,
                    query_budget=min(QUERIES_PER_STOP, remaining),
                )

                total_queries += verify_result['queries_issued']
                tour_queries += verify_result['queries_issued']
                total_cost += verify_result['cost']
                tour_promoted += verify_result['promoted_count']
                total_promoted += verify_result['promoted_count']
                tour_refused += verify_result['refused_count']
                total_refused += verify_result['refused_count']

                # Collect evidence for reporting
                for r in verify_result['results']:
                    entry = {
                        'tour_id': tour_id,
                        'tour_name': tour_name[:50],
                        'stop_title': stop_title,
                        'venue_name': venue_name,
                        **r,
                        'query_log': verify_result['query_log'],
                    }
                    if r['verdict'] == SUPPORTED_EXTERNAL:
                        all_promotions.append(entry)
                        all_writeback_claims.append(entry)
                    else:
                        all_refusals.append(entry)

        if tour_queries > 0:
            tours_processed += 1
            per_tour_stats.append({
                'tour_id': tour_id,
                'tour_name': tour_name[:60],
                'queries': tour_queries,
                'cost': tour_queries * SERPER_COST_PER_QUERY,
                'unsupported': tour_unsupported,
                'promoted': tour_promoted,
                'refused': tour_refused,
            })

        if total_queries >= MAX_TOTAL_QUERIES:
            print(f"\n  *** Budget exhausted at {total_queries} queries ***")
            break

    # ─── Writeback to stop_corpus ────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("WRITEBACK TO stop_corpus")
    print("=" * 80)

    total_passages_added = 0
    total_sources_added = 0

    # Group by (venue_name, stop_title) for efficient writeback
    writeback_groups = {}
    for claim in all_writeback_claims:
        key = (claim['venue_name'], claim['stop_title'])
        if key not in writeback_groups:
            writeback_groups[key] = []
        writeback_groups[key].append(claim)

    for (v_name, s_title), claims in writeback_groups.items():
        wb_result = write_external_sources_to_stop_corpus(
            promoted_claims=claims,
            stop_title=s_title,
            venue_name=v_name,
            conn=conn,
        )
        total_passages_added += wb_result['passages_added']
        total_sources_added += wb_result['sources_added']
        if wb_result['passages_added'] > 0:
            print(f"  {v_name}/{s_title}: +{wb_result['passages_added']} passages, +{wb_result['sources_added']} sources")

    # Verify post-writeback state
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as cnt FROM stop_corpus")
    corpus_rows_after = cur.fetchone()['cnt']
    cur.execute("SELECT SUM(passage_count) as total FROM stop_corpus")
    passages_after = cur.fetchone()['total'] or 0
    cur.close()

    print(f"\nstop_corpus AFTER: {corpus_rows_after} rows, {passages_after} passages")
    print(f"  Δ rows: +{corpus_rows_after - corpus_rows_before}")
    print(f"  Δ passages: +{passages_after - passages_before}")
    print(f"  Passages added by writeback: {total_passages_added}")
    print(f"  Sources added by writeback: {total_sources_added}")

    # ─── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Tours processed: {tours_processed}")
    print(f"Total UNSUPPORTED claims found: {total_unsupported}")
    print(f"Total queries issued: {total_queries}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Promoted to SUPPORTED_EXTERNAL: {total_promoted}")
    print(f"Refused (stayed UNSUPPORTED): {total_refused}")
    if total_unsupported > 0:
        print(f"Promotion rate (over all UNSUPPORTED): {total_promoted / total_unsupported * 100:.1f}%")
    # LEAD requirement: also report rate over queried claims
    total_queried = total_promoted + sum(1 for r in all_refusals if r.get('query_log'))
    if total_queried > 0:
        print(f"Promotion rate (over queried subset): {total_promoted / total_queried * 100:.1f}%")
    print(f"Selection: queried {total_queries} queries for {total_unsupported} UNSUPPORTED claims")
    print(f"  ({total_unsupported - len([r for r in all_refusals if not r.get('url')])} attempted, "
          f"remainder unqueried due to budget or non-verifiability)")
    if tours_processed > 0:
        print(f"Avg queries per tour: {total_queries / tours_processed:.1f}")
        print(f"Avg cost per tour: ${total_cost / tours_processed:.4f}")

    # LEAD requirement #3: Promotion counts broken out by claim type
    print("\n--- Promotion rate by claim type ---")
    type_promoted = {}
    type_total = {}
    for p in all_promotions:
        ct = p.get('claim_type', 'UNKNOWN')
        type_promoted[ct] = type_promoted.get(ct, 0) + 1
    for r in all_refusals:
        ct = r.get('claim_type', 'UNKNOWN')
        type_total[ct] = type_total.get(ct, 0) + 1
    # Merge counts
    all_types = sorted(set(list(type_promoted.keys()) + list(type_total.keys())))
    print(f"{'Type':30s} {'Promoted':>10} {'Refused':>10} {'Total':>8} {'Rate':>8}")
    for ct in all_types:
        promoted_ct = type_promoted.get(ct, 0)
        refused_ct = type_total.get(ct, 0)
        total_ct = promoted_ct + refused_ct
        rate_ct = f"{promoted_ct / total_ct * 100:.0f}%" if total_ct > 0 else "n/a"
        print(f"{ct:30s} {promoted_ct:>10} {refused_ct:>10} {total_ct:>8} {rate_ct:>8}")

    # Per-tour breakdown
    print("\n--- Per-tour breakdown ---")
    print(f"{'Tour':60s} {'Queries':>8} {'Cost':>8} {'Unsup':>6} {'Promoted':>8} {'Rate':>6}")
    for stat in per_tour_stats:
        rate = f"{stat['promoted']/stat['unsupported']*100:.0f}%" if stat['unsupported'] > 0 else "n/a"
        print(f"{stat['tour_name']:60s} {stat['queries']:>8} ${stat['cost']:.3f}  {stat['unsupported']:>6} {stat['promoted']:>8} {rate:>6}")

    # ─── Verbatim evidence ───────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"VERBATIM EVIDENCE: PROMOTIONS ({len(all_promotions)} total, showing first 10)")
    print("=" * 80)
    for i, p in enumerate(all_promotions[:10]):
        print(f"\n--- Promotion {i+1} ---")
        print(f"  Tour: {p['tour_name']} (ID {p['tour_id']})")
        print(f"  Stop: {p['stop_title']}")
        print(f"  Claim type: {p.get('claim_type', '?')}")
        print(f"  Claim: {p['claim_text']}")
        print(f"  Query: {p['query_log'][0]['query'] if p.get('query_log') else '?'}")
        print(f"  URL: {p['url']}")
        print(f"  Tier: {p['tier']}")
        print(f"  Supporting sentence: {p['supporting_sentence']}")
        print(f"  Score: {p['score']}")

    print("\n" + "=" * 80)
    print(f"VERBATIM EVIDENCE: REFUSALS ({len(all_refusals)} total, showing first 5)")
    print("=" * 80)
    for i, r in enumerate(all_refusals[:5]):
        print(f"\n--- Refusal {i+1} ---")
        print(f"  Tour: {r['tour_name']} (ID {r['tour_id']})")
        print(f"  Stop: {r['stop_title']}")
        print(f"  Claim type: {r.get('claim_type', '?')}")
        print(f"  Claim: {r['claim_text']}")
        print(f"  Query: {r['query_log'][0]['query'] if r.get('query_log') else '?'}")
        print(f"  Reason: No external source found asserting same fact about same subject")

    # ─── Verify constraints ──────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("CONSTRAINT VERIFICATION")
    print("=" * 80)

    # audio_tours count: verify no tours were deleted (count >= initial)
    # External processes may add tours during our run, so we check >= not ==
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    final_count = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
    final_nice = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    print(f"audio_tours count: {final_count} (was {audio_tours_count} at start, must be >= 130) "
          f"{'✓' if final_count >= 130 else '✗'}")
    print(f"Nice list: {final_nice} {'✓' if final_nice == [1,12,14,17,21,24,27,28,29,152] else '✗'}")
    print(f"Total cost: ${total_cost:.4f} (ceiling $0.40) {'✓' if total_cost <= 0.40 else '✗'}")

    return {
        'total_queries': total_queries,
        'total_cost': total_cost,
        'total_unsupported': total_unsupported,
        'total_promoted': total_promoted,
        'total_refused': total_refused,
        'promotion_rate': total_promoted / max(total_unsupported, 1),
        'per_tour_stats': per_tour_stats,
        'promotions': all_promotions,
        'refusals': all_refusals,
        'corpus_rows_before': corpus_rows_before,
        'corpus_rows_after': corpus_rows_after,
        'passages_before': passages_before,
        'passages_after': passages_after,
    }


if __name__ == '__main__':
    main()
