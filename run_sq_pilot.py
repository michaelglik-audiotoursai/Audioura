"""Run SQ pilot on Chagall + Matisse. Saves evidence JSON artifacts."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

def run_pilot(stop, tour_type='contained'):
    title = stop['canonical_title']
    artist = stop['artist']
    print(f"\n{'='*60}")
    print(f"PILOT: {title} by {artist}")
    print(f"{'='*60}")
    
    # SQ2: Search
    search_result = search_stories_for_stop(stop, tour_type=tour_type, generation_tier='plus')
    print(f"Queries: {search_result['total_queries']}, Cost: ${search_result['estimated_cost']:.4f}")
    print(f"Status: {search_result['story_mining_status']}")
    print(f"Results (non-reject): {len(search_result['results'])}")
    for r in search_result['results'][:5]:
        print(f"  [{r['tier']}] {r['domain']} - {r['title'][:60]}")
    print(f"\nQuery log:")
    for q in search_result['query_log']:
        print(f"  {q['query'][:50]} -> {q['result_count']} results ({q['latency_ms']:.0f}ms)")
    
    # SQ3: Extract + Score
    print(f"\n--- Extraction ---")
    extract_result = extract_and_score_stop(search_result['results'], title, artist)
    print(f"Pages fetched: {extract_result['pages_fetched']}, Anchored: {extract_result['pages_anchored']}")
    print(f"Status: {extract_result['extraction_status']}")
    print(f"Elements: {len(extract_result['elements'])}")
    for e in extract_result['elements']:
        print(f"  [{e.get('corroboration_status', '?')}] ({e.get('type', '?')}): {e.get('text', '')[:80]}")
    
    return search_result, extract_result


# --- Chagall ---
chagall_stop = {'canonical_title': 'Le Cantique des Cantiques IV', 'artist': 'Marc Chagall', 'venue_city': 'Nice'}
chagall_search, chagall_extract = run_pilot(chagall_stop)

# --- Matisse ---
matisse_stop = {'canonical_title': 'Blue Nude II', 'artist': 'Henri Matisse', 'venue_city': 'Nice'}
matisse_search, matisse_extract = run_pilot(matisse_stop)

# Save evidence
for name, stop, search, extract in [
    ('chagall', chagall_stop, chagall_search, chagall_extract),
    ('matisse', matisse_stop, matisse_search, matisse_extract),
]:
    evidence = {
        'stop': stop,
        'search': search,
        'extraction': {k: v for k, v in extract.items() if k != 'elements'},
        'elements': extract['elements'],
    }
    path = f"tours/sq_pilot_{name}_evidence.json"
    with open(path, 'w') as f:
        json.dump(evidence, f, indent=2, default=str)
    print(f"\nEvidence saved: {path}")

print("\n\nPILOT COMPLETE")
