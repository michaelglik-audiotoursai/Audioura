"""Run the post-F1-F6 pilot for Chagall Song of Songs (with refinement round)."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

# Use broader title to improve search yield (the specific "IV" suffix limits results)
stop = {'canonical_title': 'Le Cantique des Cantiques', 'artist': 'Marc Chagall', 'venue_city': 'Nice', 'venue_lang': 'fr'}
print("=== Chagall: Le Cantique des Cantiques (Song of Songs cycle) ===")
r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
print(f"Queries: {r['total_queries']}, Results: {len(r['results'])}, Status: {r['story_mining_status']}")
t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
print(f"T1/T2 count: {len(t1t2)}")
for x in t1t2[:8]:
    print(f"  [{x['tier']}] {x['domain']} - {x['title'][:60]}")

# Check if refinement round was triggered
refined = [q for q in r['query_log'] if q.get('refinement')]
if refined:
    print(f"\nRefinement round triggered: {len(refined)} refined queries")
    for q in refined:
        print(f"  {q['query'][:60]} -> {q['result_count']} results")

print("\n--- Extraction ---")
ext = extract_and_score_stop(r['results'], 'Le Cantique des Cantiques', 'Marc Chagall')
print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
print(f"Elements: {len(ext['elements'])}")
for e in ext['elements'][:8]:
    status = e.get('corroboration_status', '?')
    etype = e.get('type', '?')
    text = e.get('text', '')[:80]
    print(f"  [{status}] ({etype}): {text}")

# Check for Vava dedication specifically
vava_elements = [e for e in ext['elements'] if 'vava' in e.get('text', '').lower() or 'vava' in str(e.get('people', [])).lower()]
print(f"\nVava-related elements: {len(vava_elements)}")
for e in vava_elements:
    print(f"  [{e.get('corroboration_status','?')}] {e.get('text','')[:100]}")

evidence = {
    'stop': stop,
    'search': r,
    'extraction_meta': {k: v for k, v in ext.items() if k != 'elements'},
    'elements': ext['elements'],
    'vava_elements': vava_elements,
    'acceptance_criterion_1': len(vava_elements) > 0 and any(e.get('corroboration_status') == 'documented' for e in vava_elements),
}
os.makedirs('tours', exist_ok=True)
with open('tours/sq_pilot_chagall_f1f6.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print(f"\nSaved: tours/sq_pilot_chagall_f1f6.json")
print(f"Acceptance criterion #1 met: {evidence['acceptance_criterion_1']}")
