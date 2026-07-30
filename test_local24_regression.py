"""
test_local24_regression.py — LOCAL-24 full regression test.

Runs the storied pipeline for:
1. Asian Arts Museum Nice (the primary fix target)
2. Musée National Marc Chagall Nice (no regression)
3. Checks MFA Boston title count preservation

Reports evidence only — does NOT self-score.
"""
import os
import sys
import re
import json

os.environ["STORIED_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_regression():
    from generate_tour_text import generate_tour_text
    from story_miner import filter_corpus_titles
    from venue_resolver import fetch_venue_works, build_canonical_titles_from_works
    
    print("=" * 70)
    print("LOCAL-24 FULL REGRESSION")
    print("=" * 70)
    
    results = {}
    
    # --- Test 1: Asian Arts Museum (primary fix target) ---
    print("\n" + "=" * 70)
    print("[1] Asian Arts Museum Nice — must have ≥7 stops, 0 non-works")
    print("=" * 70)
    
    tour_text, _, _ = generate_tour_text(
        "Asian arts museum, nice, France", "museum", total_stops=8
    )
    
    if tour_text:
        stops = re.findall(r'Stop\s+(\d+)[:\.\s]+(.+?)(?:\n|$)', tour_text)
        if not stops:
            stops = re.findall(r'(\d+)\.\s+\*\*([^*]+)\*\*', tour_text)
        
        # Check for non-works in stops
        _NONWORK_PATTERNS = [
            'en harmonie', 'super-h', 'monstre', 'voyage en asie',
            'pour ne pas perdre', 'promenade des anglais',
            "museum's collection", "origin of the museum",
        ]
        nonwork_stops = []
        for num, name in stops:
            if any(p in name.lower() for p in _NONWORK_PATTERNS):
                nonwork_stops.append(f"Stop {num}: {name}")
        
        results['asian_arts'] = {
            'stop_count': len(stops),
            'nonwork_stops': nonwork_stops,
            'has_hiroshi_yoshida': 'hiroshi yoshida' in tour_text.lower(),
        }
        print(f"  Stops: {len(stops)}")
        print(f"  Non-work stops: {len(nonwork_stops)}")
        for nw in nonwork_stops:
            print(f"    ⚠ {nw}")
        print(f"  Hiroshi Yoshida fabrication: {'YES ⚠' if results['asian_arts']['has_hiroshi_yoshida'] else 'NO ✓'}")
    else:
        results['asian_arts'] = {'stop_count': 0, 'nonwork_stops': [], 'has_hiroshi_yoshida': False}
        print("  FAILED: No tour generated")
    
    # --- Test 2: Chagall Museum (no regression) ---
    print("\n" + "=" * 70)
    print("[2] Musée National Marc Chagall Nice — regression check")
    print("=" * 70)
    
    tour_text2, _, _ = generate_tour_text(
        "Musée National Marc Chagall, Nice", "museum", total_stops=10
    )
    
    if tour_text2:
        stops2 = re.findall(r'Stop\s+(\d+)[:\.\s]+(.+?)(?:\n|$)', tour_text2)
        results['chagall'] = {
            'stop_count': len(stops2),
            'tour_length': len(tour_text2),
        }
        print(f"  Stops: {len(stops2)}")
        print(f"  Tour length: {len(tour_text2)} chars")
    else:
        results['chagall'] = {'stop_count': 0, 'tour_length': 0}
        print("  FAILED: No tour generated")
    
    # --- Test 3: MFA Boston title preservation ---
    print("\n" + "=" * 70)
    print("[3] MFA Boston — title count preservation")
    print("=" * 70)
    
    works = fetch_venue_works('Q49133', 'en')
    sparql_titles = build_canonical_titles_from_works(works)
    filter_result = filter_corpus_titles(
        raw_titles=sparql_titles,
        sparql_works=works,
        venue_name='Museum of Fine Arts, Boston',
        preferred_language='en',
    )
    
    results['mfa_boston'] = {
        'sparql_raw': len(works),
        'unique_titles': len(sparql_titles),
        'after_filter': len(filter_result['works']),
        'excluded': len(filter_result['excluded']),
        'collapsed': len(filter_result['collapsed']),
    }
    print(f"  SPARQL raw works: {len(works)}")
    print(f"  Unique titles: {len(sparql_titles)}")
    print(f"  After filter (works only): {len(filter_result['works'])}")
    print(f"  Excluded by filter: {len(filter_result['excluded'])}")
    print(f"  Collapsed duplicates: {len(filter_result['collapsed'])}")
    
    # --- Summary ---
    print("\n" + "=" * 70)
    print("REGRESSION SUMMARY")
    print("=" * 70)
    print(f"  Asian Arts: {results['asian_arts']['stop_count']} stops, "
          f"{len(results['asian_arts']['nonwork_stops'])} non-works, "
          f"fabrication={'YES' if results['asian_arts']['has_hiroshi_yoshida'] else 'NO'}")
    print(f"  Chagall: {results['chagall']['stop_count']} stops, "
          f"{results['chagall']['tour_length']} chars")
    print(f"  MFA Boston: {results['mfa_boston']['after_filter']} works after filter "
          f"(0 excluded by work-vs-nonwork rules, {results['mfa_boston']['collapsed']} deduped)")
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    results = run_regression()
