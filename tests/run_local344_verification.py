#!/usr/bin/env python3
"""LOCAL-344 Verification: Measure the new D258 distribution and residual.

Reports:
1. Museum 8-stop base score (BEFORE vs AFTER comparison)
2. Chagall 4-stop base score  
3. New D258 distribution: stops with n=0, n=1, n>=2 claims
4. Residual: stops that still count facts with zero claims
5. Corpus row counts (must be unchanged)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tour_rubric_scorer import score_tour_file, parse_tour, analyze_stop
from groundedness_check import extract_fact_claims, measure_stop_groundedness
from tests.db_connection import get_connection, check_db_available
from stop_corpus_reader import get_stop_corpus_for_tour


def main():
    if not check_db_available():
        print("ERROR: DB not available")
        return

    conn = get_connection()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. Museum 8-stop
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("MUSEUM 8-STOP: Musée des Arts Asiatiques")
    print("=" * 70)
    ts = score_tour_file('tours/LOCAL262_asian_arts_8stop_restored.txt', 8)
    print(f"Base score: {ts.base_score}")
    print(f"Per-stop base: {ts.per_stop_base}")
    print()
    for s in ts.stops:
        print(f"  Stop {s.index}: {s.title}")
        print(f"    fact_count={s.distinct_fact_count}  claims_checked={s.groundedness_claims_checked}  "
              f"fraction={s.groundedness_fraction}")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. Chagall 4-stop
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("CHAGALL 4-STOP")
    print("=" * 70)
    ts4 = score_tour_file('tours/cil_chagall_cycle5.txt', 4)
    print(f"Base score: {ts4.base_score}")
    for s in ts4.stops:
        print(f"  Stop {s.index}: {s.title}")
        print(f"    fact_count={s.distinct_fact_count}  claims_checked={s.groundedness_claims_checked}  "
              f"fraction={s.groundedness_fraction}")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. D258 distribution across ALL scorable stops
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("D258 DISTRIBUTION: Claims per stop across all scorable stops")
    print("=" * 70)

    # Get all tours from DB
    cur = conn.cursor()
    cur.execute("SELECT id, tour_name, tour_content, number_requested FROM audio_tours WHERE tour_content IS NOT NULL AND tour_content != ''")
    tours = cur.fetchall()

    n0 = 0  # stops with 0 claims
    n1 = 0  # stops with exactly 1 claim
    n2plus = 0  # stops with 2+ claims
    total_stops = 0
    facts_without_claims = []  # residual

    for tour_id, tour_name, content, n_req in tours:
        if not content or len(content.strip()) < 100:
            continue
        try:
            stops = parse_tour(content)
        except Exception:
            continue
        if not stops:
            continue

        # Get corpus
        stop_names = [s['title'] for s in stops]
        try:
            corpus_data = get_stop_corpus_for_tour(tour_name, stop_names, conn)
        except Exception:
            corpus_data = {}

        for stop in stops:
            body = stop['body']
            title = stop['title']
            if len(body.strip()) < 50:
                continue

            total_stops += 1

            # Extract claims (the aligned version)
            claims = extract_fact_claims(body, title)
            n_claims = len(claims)

            if n_claims == 0:
                n0 += 1
            elif n_claims == 1:
                n1 += 1
            else:
                n2plus += 1

            # Check residual: does fact detector count facts that have no claim?
            sa = analyze_stop(stop, stops)
            if sa.distinct_fact_count > 0 and n_claims == 0:
                facts_without_claims.append({
                    'tour': tour_name,
                    'stop': title,
                    'fact_count': sa.distinct_fact_count,
                    'materials': sa.materials_techniques,
                    'measurements': sa.measurements_numbers,
                    'periods': sa.named_periods,
                    'dates': list(set(sa.dates_years)),
                    'people': sa.named_people,
                })

    print(f"Total scorable stops: {total_stops}")
    print(f"  n=0 claims: {n0} ({100*n0/max(1,total_stops):.1f}%)")
    print(f"  n=1 claims: {n1} ({100*n1/max(1,total_stops):.1f}%)")
    print(f"  n>=2 claims: {n2plus} ({100*n2plus/max(1,total_stops):.1f}%)")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. Residual: facts counted but no claims
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print(f"RESIDUAL: {len(facts_without_claims)} stops with facts>0 but claims=0")
    print("=" * 70)
    for item in facts_without_claims[:20]:
        print(f"  [{item['tour'][:40]}] {item['stop']}")
        print(f"    fact_count={item['fact_count']}  dates={item['dates']}  "
              f"people={item['people']}  materials={item['materials']}  "
              f"measurements={item['measurements']}  periods={item['periods']}")
    print()

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. Corpus row counts (must be unchanged)
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("CORPUS ROW COUNTS")
    print("=" * 70)
    cur.execute("SELECT COUNT(*) FROM stop_corpus")
    stop_corpus_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM venue_corpus")
    venue_corpus_count = cur.fetchone()[0]
    print(f"  stop_corpus: {stop_corpus_count}")
    print(f"  venue_corpus: {venue_corpus_count}")

    conn.close()


if __name__ == '__main__':
    main()
